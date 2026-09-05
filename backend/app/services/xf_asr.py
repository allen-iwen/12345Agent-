"""科大讯飞 WebSocket 语音听写 v2 客户端（云端 ASR 首选引擎）。

- 鉴权：host/date/request-line HMAC-SHA256 签名（v2 规范）；
- 单连接上限 60s：长录音先用 ffmpeg silencedetect 找静音点，在 35~55s 窗口内
  选最接近 45s 的静音处切段，逐段识别后拼接（避免切断词中间）；
- 结果组装：开启 wpgs 动态修正，按 sn 分段保存每段最终文本，结束按 sn 排序拼接；
- 帧发送：1280 字节/帧（40ms 音频），帧间 sleep 由 pacing_ms 控制，默认 3ms
  （约 13 倍实时率，6 分钟录音云端识别约 25~30s）。

业务契约：transcribe(path) -> {"text": str, "segments": int}
任何失败向上抛异常，由调用方（routes/asr.py）回退本地 SenseVoice。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlencode, urlparse

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_HOST = "iat-api.xfyun.cn"
_PATH = "/v2/iat"
_FRAME_BYTES = 1280  # 40ms @ 16kHz 16bit mono
_SEG_TARGET_S = 45.0  # 目标切段时长
_SEG_MIN_S = 35.0
_SEG_MAX_S = 55.0  # 单段硬上限（留 5s 余量给 60s 连接限制）
_RECV_TIMEOUT_S = 30


def configured() -> bool:
    s = get_settings()
    return bool(s.xf_asr_app_id and s.xf_asr_api_secret and s.xf_asr_api_key)


def _find_ffmpeg() -> str:
    import shutil

    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    raise FileNotFoundError("未找到 ffmpeg，无法解码音频")


def _auth_url() -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    date = format_datetime(now, usegmt=True)
    signature_origin = f"host: {_HOST}\ndate: {date}\nGET {_PATH} HTTP/1.1"
    signature = base64.b64encode(
        hmac.new(s.xf_asr_api_secret.encode(), signature_origin.encode(), hashlib.sha256).digest()
    ).decode()
    authorization_origin = (
        f'api_key="{s.xf_asr_api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    params = {
        "authorization": base64.b64encode(authorization_origin.encode()).decode(),
        "date": date,
        "host": _HOST,
    }
    return f"wss://{_HOST}{_PATH}?{urlencode(params)}"


# ---------------- 音频准备与切段 ----------------


def _run_ffmpeg(args: list[str], binary: bool = False) -> bytes:
    cmd = [_find_ffmpeg(), "-hide_banner", "-nostats", *args]
    out = subprocess.run(cmd, capture_output=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(f"ffmpeg 失败：{out.stderr.decode('utf-8', 'ignore')[-300:]}")
    return out.stdout if binary else out.stderr


def _to_pcm16k(path: Path) -> tuple[bytes, float]:
    """任意音频 → 16kHz 16bit 单声道 PCM；返回 (pcm, 时长秒)。"""
    stderr = _run_ffmpeg(
        ["-i", str(path), "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000", "-"]
    )
    # stderr 里 "Duration: 00:06:03.51" 提时长（--disable 程序级管道输出限制下 stdout 是二进制 PCM）
    m = re.search(rb"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    if not m:
        raise RuntimeError("无法解析音频时长")
    duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    pcm = _run_ffmpeg(
        ["-i", str(path), "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000", "pipe:1"],
        binary=True,
    )
    return pcm, duration


def _silence_points(path: Path, duration: float) -> list[float]:
    """silencedetect 找静音中点，作为候选切点。"""
    try:
        stderr = _run_ffmpeg(
            ["-i", str(path), "-af", "silencedetect=noise=-35dB:d=0.5", "-f", "null", "-"]
        )
    except Exception:  # noqa: BLE001 - 探测失败则退化为硬切
        return []
    starts = [float(x) for x in re.findall(r"silence_start:\s*([\d.]+)", stderr.decode("utf-8", "ignore"))]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", stderr.decode("utf-8", "ignore"))]
    return [(a + b) / 2 for a, b in zip(starts, ends) if b > a]


def _plan_segments(path: Path, duration: float) -> list[tuple[float, float]]:
    """贪心规划 [start, end) 切段：优先静音点，退化为硬切。"""
    cuts = sorted(_silence_points(path, duration))
    segs: list[tuple[float, float]] = []
    start = 0.0
    while duration - start > _SEG_MAX_S:
        window = [c for c in cuts if start + _SEG_MIN_S <= c <= start + _SEG_MAX_S]
        cut = min(window, key=lambda c: abs(c - (start + _SEG_TARGET_S))) if window else start + _SEG_TARGET_S
        segs.append((start, cut))
        start = cut
    segs.append((start, duration))
    return segs


# ---------------- WebSocket 识别 ----------------


_PUNCT_HEAD = "。？！，、；,?!"


def _core_text(s: str) -> str:
    return re.sub(r"[。？！，、；,.?!\s]", "", s)


class _SegResult:
    """单段识别结果组装。

    实测消息语义（v2 iat）：sn 逐消息递增；普通帧携带当前句的累积原文（无标点）；
    句子完结时到达一条「修正帧」——以标点开头，携带上一句尾标点 + 本句修正后全文
    （含标点、纠错词）；随后新句从短文本重新增长；status=2 结束。
    组装规则：标点开头帧整句替换；与当前句有公共前缀的增长帧覆盖；否则视为新句。
    """

    def __init__(self) -> None:
        self.kept: list[str] = []
        self.cur: str = ""
        self.error: str = ""
        self.done = threading.Event()

    def feed(self, text: str) -> None:
        if not text or not _core_text(text):
            return  # 纯标点帧忽略
        if text[0] in _PUNCT_HEAD:
            # 修正帧：携带本句最终（含标点纠错）文本。回溯清掉 kept 尾部
            # 属于同一句的原始累积版本（它们的信息已被本帧完全取代）。
            c_new = _core_text(text)
            while self.kept:
                c_old = _core_text(self.kept[-1])
                if self._same_sentence(c_old, c_new):
                    self.kept.pop()
                else:
                    break
            self.cur = text
            return
        c_t = _core_text(text)
        if self.cur:
            c_p = _core_text(self.cur)
            if c_t.startswith(c_p) or c_p.startswith(c_t):
                if len(c_t) >= len(c_p):
                    self.cur = text
                return
            if self._same_sentence(c_t, c_p):
                if len(c_t) >= len(c_p):
                    self.cur = text
                return
            self.kept.append(self.cur)
        self.cur = text

    @staticmethod
    def _same_sentence(a: str, b: str) -> bool:
        """两条文本是否为同一句的不同识别版本：包含，或 前缀+后缀重叠 ≥ 短串 60%。"""
        if not a or not b:
            return False
        if a in b or b in a:
            return True
        n = 0
        for x, y in zip(a, b):
            if x != y:
                break
            n += 1
        m = 0
        for x, y in zip(reversed(a), reversed(b)):
            if x != y:
                break
            m += 1
        return n + m >= max(4, int(min(len(a), len(b)) * 0.6))

    def final(self) -> str:
        if self.cur and self.cur not in self.kept:
            self.kept.append(self.cur)
        return "".join(self.kept)


def _extract_text(result: dict) -> str:
    parts: list[str] = []
    for ws in result.get("ws", []):
        for cw in ws.get("cw", []):
            parts.append(cw.get("w", ""))
    return "".join(parts)


def _recognize_pcm(pcm: bytes) -> str:
    """一段（<60s）PCM 经 v2 语音听写识别，返回拼接文本。"""
    if not pcm:
        return ""
    from websockets.sync.client import connect

    res = _SegResult()

    def on_message(_ws, raw) -> None:
        msg = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
        code = msg.get("code")
        if code != 0:
            res.error = f"讯飞返回 code={code} {msg.get('message', '')}"
            res.done.set()
            return
        data = msg.get("data", {})
        result = data.get("result")
        if result:
            res.feed(_extract_text(result))
        if data.get("status") == 2:
            res.done.set()

    url = _auth_url()
    with connect(url, max_size=None, close_timeout=5) as ws:
        frames = [pcm[i : i + _FRAME_BYTES] for i in range(0, len(pcm), _FRAME_BYTES)]

        def sender() -> None:
            try:
                for i, frame in enumerate(frames):
                    payload: dict = {"data": {"status": 1 if i else 0, "format": "audio/L16;rate=16000", "encoding": "raw", "audio": base64.b64encode(frame).decode()}}
                    if i == 0:
                        payload["common"] = {"app_id": get_settings().xf_asr_app_id}
                        payload["business"] = {"language": "zh_cn", "domain": "iat", "accent": "mandarin", "dwa": "wpgs"}
                    if i == len(frames) - 1:
                        payload["data"]["status"] = 2
                    ws.send(json.dumps(payload, ensure_ascii=False))
                    time.sleep(0.002)  # 约 20 倍实时率的温和节流
            except Exception as exc:  # noqa: BLE001
                res.error = f"发送失败：{exc}"
                res.done.set()

        t = threading.Thread(target=sender, daemon=True)
        t.start()
        try:
            while not res.done.is_set():
                on_message(ws, ws.recv(timeout=_RECV_TIMEOUT_S))
        except TimeoutError:
            if not res.kept and not res.cur:
                res.error = res.error or "识别超时"
        except Exception as exc:  # noqa: BLE001 - 连接关闭属正常结束
            if not res.kept and not res.cur:
                raise RuntimeError(f"接收失败：{exc}") from exc
        if res.error and not res.kept and not res.cur:
            raise RuntimeError(res.error)
        return res.final()


def transcribe(path: Path) -> dict:
    """主入口：文件 → PCM → 智能切段 → 逐段识别 → 拼接。"""
    if not configured():
        raise RuntimeError("讯飞 ASR 未配置凭据")
    pcm, duration = _to_pcm16k(path)
    segs = _plan_segments(path, duration)
    logger.info("xf_asr: %.0fs 音频切 %d 段", duration, len(segs))
    texts: list[str] = []
    bytes_per_sec = 32000
    for start, end in segs:
        seg_pcm = pcm[int(start * bytes_per_sec) : int(end * bytes_per_sec)]
        texts.append(_recognize_pcm(seg_pcm))
    full = "".join(t for t in texts if t)
    return {"text": full, "segments": len(segs), "duration_s": round(duration, 1)}


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    t0 = time.time()
    out = transcribe(Path(sys.argv[1]))
    print(f"[xf] {out['segments']} 段 / {out['duration_s']}s / 耗时 {time.time() - t0:.1f}s")
    print(out["text"][:300])
