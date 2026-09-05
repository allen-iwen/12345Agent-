"""本地语音识别服务：funasr SenseVoiceSmall（离线推理，无需外部 API）。

- 模型从 modelscope 国内源自动下载（约 230MB，仅首次）；
- 输出脱除 <|zh|><|NEUTRAL|> 等标记，仅保留正文；
- 进程内单例，首次调用有 10-30 秒冷启动。
"""
from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_model: Any = None
_LOAD_LOCK = __import__("threading").Lock()

_TAG_RE = re.compile(r"<\|[^|]*\|>")


def _get_model() -> Any:
    global _model
    if _model is not None:
        return _model
    with _LOAD_LOCK:
        if _model is not None:
            return _model
        from funasr import AutoModel

        logger.info("loading SenseVoiceSmall (首次加载含模型下载)…")
        _model = AutoModel(
            model="iic/SenseVoiceSmall",
            trust_remote_code=True,
            disable_update=True,
        )
        logger.info("SenseVoiceSmall ready")
        return _model


def _to_wav(src: Path) -> Path:
    """mp3/m4a/amr 等一律经 ffmpeg 转 16k 单声道 wav，避免后端解码差异。"""
    if src.suffix.lower() == ".wav":
        return src
    dst = Path(tempfile.gettempdir()) / (src.stem + "_asr.wav")
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(src),
            "-ac", "1", "-ar", "16000", str(dst),
        ],
        capture_output=True,
        check=True,
        timeout=120,
    )
    return dst


def transcribe(audio_path: str | Path) -> dict:
    """转写音频文件，返回 {text, source}。"""
    src = Path(audio_path)
    if not src.exists():
        raise FileNotFoundError(audio_path)

    wav = _to_wav(src)
    model = _get_model()
    res = model.generate(
        input=str(wav),
        cache={},
        language="zh",
        use_itn=True,
        batch_size_s=60,
        merge_vad=True,
        merge_length_s=5,
    )
    raw = res[0].get("text", "") if res else ""
    text = _TAG_RE.sub("", raw).strip()
    return {"text": text, "source_file": src.name}
