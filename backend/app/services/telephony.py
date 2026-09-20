# -*- coding: utf-8 -*-
"""运营商/呼叫中心对接服务。

目标：真实政务热线部署时，通话音频经呼叫平台（运营商 VOIP / CTI / FreeSWITCH）
到达本系统，自动完成 转写 → 降噪整理 → 建单 全链路。浏览器端不需要任何改动。

三种接入方式（详见 docs/telephony.md）：
  A. HTTP 回调（webhook）：运营商挂机后回调 POST /api/telephony/webhook/call-event，
     携带录音 URL（http(s) 或已共享的本地路径）；
  B. 录音目录投递：运营商把录音文件投放到约定目录，scripts/telephony_watcher.py
     轮询发现新文件自动建单；
  C. SIP 中继（规划位）：政府侧已有 PBX 时经 FreeSWITCH ESL 对接，音频流式进入，
     配置字段已预留（telephony_provider=sip）。
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests

from app.core.config import get_settings
from app.repositories import cases as case_repo
from app.repositories import telephony as repo
from app.services import asr as local_asr
from app.services import transcript_clean, xf_asr
from app.workflow.graph import run_chain

logger = logging.getLogger(__name__)

_DOWNLOAD_TIMEOUT = 60  # 秒


def ingest_recording(recording_url: str, call_id: str, channel: str = "电话（运营商接入）") -> dict:
    """按通话事件建单：定位/下载录音 → 双引擎转写 → 降噪 → 链路建单。

    同步执行（由后台任务/守护脚本调用），返回 {case_id, status, text}。
    """
    settings = get_settings()
    repo.update_status(call_id, "processing")

    # 1) 定位录音：http(s) 下载；本地/共享盘路径直接使用
    path = _resolve_recording(recording_url)
    try:
        # 2) 双引擎转写（与 /api/asr 同策略：讯飞云端优先，本地兜底）
        text = ""
        source = ""
        if xf_asr.configured():
            try:
                out = xf_asr.transcribe(path)
                text, source = out["text"], "xfyun"
            except Exception as exc:  # noqa: BLE001 - 云端失败降级本地
                logger.warning("telephony xfyun failed (%s), fallback local", exc)
        if not text:
            result = local_asr.transcribe(path)
            text, source = result["text"], "sensevoice"

        # 3) 降噪整理（失败自动回退原文）
        cleaned = transcript_clean.clean_transcript(text, 0.0)
        raw_text = cleaned["clean"] if cleaned["applied"] and cleaned["clean"] else text

        if not raw_text.strip():
            raise ValueError("录音转写结果为空（可能为静音或非语音）")

        # 4) 建单：与人工受理同一条链路，产物落库，全程白盒留痕
        case_id = f"tel-{call_id}"
        case_repo.create_case(case_id, case_id, raw_text, channel, "processing")
        values = run_chain(case_id, raw_text, channel)
        status = values.get("status", "failed")
        case_repo.save_state(
            case_id,
            status=status,
            thread_id=case_id,
            understanding=values.get("understanding"),
            work_order=values.get("work_order"),
            classification=values.get("classification"),
            routing=values.get("routing"),
            reply_draft=values.get("reply_draft"),
            assessment={"urgency": values.get("urgency")} if values.get("urgency") else None,
            error=values.get("error"),
            completed=status == "completed",
        )
        repo.update_status(call_id, "done", case_id=case_id,
                           detail=f"source={source} chars={len(raw_text)} case_status={status}")
        return {"case_id": case_id, "status": status, "text": raw_text, "asr_source": source}
    except Exception as exc:  # noqa: BLE001 - 运营商链路失败必须落状态，可重放
        logger.exception("telephony ingest failed for %s", call_id)
        repo.update_status(call_id, "failed", detail=str(exc))
        raise


def _resolve_recording(recording_url: str) -> Path:
    """录音定位：http(s) 下载到临时目录；file:// 或本地路径直接使用。"""
    parsed = urlparse(recording_url)
    if parsed.scheme in ("http", "https"):
        dest = Path(tempfile.mkdtemp(prefix="tel_")) / "recording.audio"
        resp = requests.get(recording_url, timeout=_DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return dest
    # file:///D:/share/calls/xxx.mp3 或 D:/share/calls/xxx.mp3 或相对路径
    p = Path(parsed.path if parsed.scheme == "file" else recording_url)
    if not p.exists():
        raise FileNotFoundError(f"录音不存在：{recording_url}")
    return p


def watch_dir() -> Path:
    """运营商录音投递目录（约定式对接），确保存在并返回。"""
    settings = get_settings()
    d = settings.telephony_recording_dir
    (d / "processed").mkdir(parents=True, exist_ok=True)
    return d
