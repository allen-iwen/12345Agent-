# -*- coding: utf-8 -*-
"""图片证据附件 API：暂存上传 → 视觉分析 → 建单关联 → 原图回显。

流程：
1. `POST /api/attachments`（multipart）暂存图片并立即做视觉分析（可关），返回 id 与结论；
2. 建单时把 id 列表传给 `POST /api/cases`（attachment_ids），服务端关联到案件并把
   视觉结论注入链路（影响分类、派单与急件分级）；
3. `GET /api/attachments/{id}/raw` 原图回显；`GET /api/cases/{id}/attachments` 列表。
"""
from __future__ import annotations

import hashlib
import logging
import mimetypes
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.repositories import attachments as repo
from app.services import vision

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["attachments"])

ALLOWED_IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
ALLOWED_AUDIO = {".mp3", ".wav", ".m4a", ".amr", ".aac", ".ogg", ".flac", ".wma", ".webm", ".mp4"}
MAX_BYTES = 10 * 1024 * 1024


def _stage_dir() -> Path:
    d = get_settings().attachment_dir / "staging"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.post("/attachments")
async def upload_attachment(
    file: UploadFile = File(...),
    kind: str = Form(default="image"),
    context_text: str = Form(default=""),
    analyze: bool = Form(default=True),
) -> dict:
    """暂存证据文件；kind=image 时默认立即做视觉分析。"""
    suffix = Path(file.filename or "").suffix.lower()
    allowed = ALLOWED_IMAGE if kind == "image" else ALLOWED_AUDIO
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"不支持的{kind}格式 {suffix}，允许：{sorted(allowed)}")

    dest = _stage_dir() / f"{uuid.uuid4().hex[:10]}{suffix}"
    try:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"文件保存失败：{exc}") from exc

    size = dest.stat().st_size
    if size > MAX_BYTES:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="文件超过 10MB 上限，请压缩后重试")

    sha = hashlib.sha256(dest.read_bytes()).hexdigest()
    vision_result = None
    if kind == "image" and analyze:
        vision_result = vision.analyze(dest, context_text or "")
        if not vision_result.get("available"):
            logger.info("视觉分析不可用：%s", vision_result.get("note"))

    mime = file.content_type or mimetypes.guess_type(dest.name)[0] or "application/octet-stream"
    out = repo.create(kind, file.filename or dest.name, str(dest), mime, size, sha, vision_result)
    row = repo.get(out["id"])
    return {"id": out["id"], "kind": kind, "filename": file.filename, "size": size,
            "vision": vision_result, "vision_available": vision.available(),
            "attachment": _public(row)}


def _public(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "case_id": row["case_id"],
        "kind": row["kind"],
        "filename": row["filename"],
        "mime": row["mime"],
        "size": row["size"],
        "vision": row.get("vision"),
        "created_at": row["created_at"],
    }


@router.get("/cases/{case_id}/attachments")
def list_case_attachments(case_id: str) -> list[dict]:
    return [_public(r) for r in repo.list_by_case(case_id)]


@router.get("/attachments/{attachment_id}/raw")
def raw_attachment(attachment_id: str) -> FileResponse:
    row = repo.get(attachment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="附件不存在")
    path = Path(row["path"])
    if not path.exists():
        raise HTTPException(status_code=410, detail="附件文件已不存在")
    return FileResponse(str(path), media_type=row.get("mime") or "application/octet-stream")


@router.post("/attachments/{attachment_id}/analyze")
def reanalyze(attachment_id: str, context_text: str = Form(default="")) -> dict:
    row = repo.get(attachment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="附件不存在")
    if row["kind"] != "image":
        raise HTTPException(status_code=400, detail="仅图片支持视觉分析")
    result = vision.analyze(row["path"], context_text or "")
    if result.get("available"):
        repo.set_vision(attachment_id, result)
    return result


@router.delete("/attachments/{attachment_id}")
def delete_attachment(attachment_id: str) -> dict:
    row = repo.delete(attachment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="附件不存在")
    return {"ok": True, "id": attachment_id}


@router.get("/attachments/status")
def vision_status() -> dict:
    """视觉能力可用性（前端据此提示「AI 判读」或「人工判读」）。"""
    return {
        "available": vision.available(),
        "providers": [p["provider"] for p in vision._active_providers()],  # noqa: SLF001
        "max_bytes": MAX_BYTES,
    }
