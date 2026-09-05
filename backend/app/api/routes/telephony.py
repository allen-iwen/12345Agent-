# -*- coding: utf-8 -*-
"""运营商/呼叫中心对接 API。

- POST /api/telephony/webhook/call-event  运营商通话事件回调（挂机+录音URL 自动建单）
- GET  /api/telephony/calls/{call_id}     查询单通电话的处理状态与案件号
- GET  /api/telephony/status              对接配置与最近事件（联调排障用）

回调鉴权：请求头 X-Telephony-Secret 与 .env 的 TELEPHONY_WEBHOOK_SECRET 一致；
未配置 secret 时放行并告警（联调阶段），生产必须配置。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings
from app.repositories import telephony as repo
from app.services import telephony

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/telephony", tags=["telephony"])


class CallEvent(BaseModel):
    """运营商通话事件（字段与主流呼叫平台回调兼容，全部可选字段有缺省）。"""

    call_id: str
    event: str = "hangup"  # ringing / answered / hangup / recording_ready
    provider: str = "generic"
    caller: str = ""
    recording_url: str = ""  # http(s) 或共享盘路径；hangup/recording_ready 时提供
    timestamp: str = ""


def _check_secret(secret: str | None) -> None:
    expect = get_settings().telephony_webhook_secret
    if not expect:
        logger.warning("TELEPHONY_WEBHOOK_SECRET 未配置，回调未鉴权（生产环境必须配置）")
        return
    if secret != expect:
        raise HTTPException(status_code=401, detail="回调密钥校验失败（X-Telephony-Secret）")


@router.post("/webhook/call-event")
def call_event(
    ev: CallEvent,
    background: BackgroundTasks,
    x_telephony_secret: str | None = Header(default=None),
) -> dict:
    _check_secret(x_telephony_secret)
    repo.insert_event(ev.call_id, ev.provider, ev.event, ev.caller, ev.recording_url)

    if ev.event in ("hangup", "recording_ready") and ev.recording_url:
        # 后台执行：转写+建单约 1–2 分钟，运营商回调必须立刻返回 200
        background.add_task(_safe_ingest, ev.call_id, ev.recording_url)
        return {"ok": True, "call_id": ev.call_id, "accepted": True, "processing": "async"}
    return {"ok": True, "call_id": ev.call_id, "accepted": True, "processing": None}


def _safe_ingest(call_id: str, recording_url: str) -> None:
    try:
        telephony.ingest_recording(recording_url, call_id)
    except Exception:  # noqa: BLE001 - 状态已落库，异常不再上抛
        pass


@router.get("/calls/{call_id}")
def call_status(call_id: str) -> dict:
    row = repo.latest_by_call(call_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"无此通话事件：{call_id}")
    return row


@router.get("/status")
def telephony_status() -> dict:
    settings = get_settings()
    return {
        "provider": settings.telephony_provider,
        "webhook_secret_configured": bool(settings.telephony_webhook_secret),
        "recording_dir": str(settings.telephony_recording_dir),
        "recording_dir_ready": settings.telephony_recording_dir.exists(),
        "recent_events": repo.list_recent(10),
        "notes": "对接方式与联调步骤见 docs/telephony.md",
    }
