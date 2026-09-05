"""录音输入 API：上传音频 → 讯飞云端转写（首选）→ 本地 SenseVoice 兜底。"""
from __future__ import annotations

import logging
import shutil
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File

from app.services import asr, xf_asr

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/asr", tags=["asr"])

ALLOWED = {".mp3", ".wav", ".m4a", ".amr", ".aac", ".ogg", ".flac", ".wma"}


@router.post("")
async def transcribe_audio(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(status_code=400, detail=f"不支持的音频格式 {suffix}，允许：{sorted(ALLOWED)}")

    tmp_dir = Path(tempfile.mkdtemp(prefix="asr_"))
    tmp_path = tmp_dir / ("audio" + suffix)
    try:
        with tmp_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)

        # 双引擎策略链：讯飞云端（快、带标点纠错）→ 本地 SenseVoice（离线兜底）
        text = ""
        source = ""
        latency_ms = 0
        seg_count = 0
        fallback_error = ""
        if xf_asr.configured():
            t0 = time.monotonic()
            try:
                out = xf_asr.transcribe(tmp_path)
                text, source = out["text"], "xfyun"
                seg_count = out.get("segments", 1)
                latency_ms = int((time.monotonic() - t0) * 1000)
                logger.info("xf_asr ok file=%s segs=%d chars=%d %dms", file.filename, seg_count, len(text), latency_ms)
            except Exception as exc:  # noqa: BLE001 - 云端失败降级本地
                fallback_error = f"讯飞云端失败：{exc}"
                logger.warning("%s，降级本地 SenseVoice", fallback_error)
        if not text:
            t0 = time.monotonic()
            result = asr.transcribe(tmp_path)
            text, source = result["text"], "sensevoice"
            latency_ms = int((time.monotonic() - t0) * 1000)
        return {
            "filename": file.filename,
            "text": text,
            "source": source,
            "latency_ms": latency_ms,
            "segments": seg_count,
            "fallback_note": fallback_error,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception("asr failed")
        raise HTTPException(status_code=500, detail=f"转写失败：{e}") from e
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.get("/status")
def asr_status() -> dict:
    """双引擎可用性（前端可提示当前将使用哪个引擎）。"""
    return {
        "cloud": "xfyun" if xf_asr.configured() else None,
        "local_model_loaded": asr._model is not None,
    }
