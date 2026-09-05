"""政策文件 API：上传入库（切分+向量索引）、列表、删除、检索。"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services import policy_rag

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/policies", tags=["policies"])

PARSERS = {".txt", ".md", ".json", ".pdf", ".docx"}
MAX_BYTES = 20 * 1024 * 1024


def _extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".json"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    if suffix == ".docx":
        import docx2txt

        return docx2txt.process(str(path)) or ""
    raise ValueError(f"不支持的文件类型 {suffix}，允许：{sorted(PARSERS)}")


@router.post("")
async def upload_policy(
    file: UploadFile = File(...),
    source_name: str = Form(default=""),
    publisher: str = Form(default=""),
    category_name: str = Form(default="综合"),
) -> dict:
    """上传政策文件 → 提取文本 → 切分 → 向量入库。source_name 为引用时显示的正式名称。"""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in PARSERS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型 {suffix}，允许：{sorted(PARSERS)}")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="文件超过 20MB 上限")
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="空文件")

    import shutil
    import tempfile

    tmp_dir = Path(tempfile.mkdtemp(prefix="policy_"))
    tmp_path = tmp_dir / ("doc" + suffix)
    try:
        tmp_path.write_bytes(data)
        name = (source_name or "").strip() or re.sub(r"\.[^.]+$", "", file.filename or "") or file.filename
        text = _extract_text(tmp_path)
        if not text.strip():
            raise HTTPException(status_code=400, detail="未能从文件中提取到文本（扫描件 PDF 不支持）")
        result = policy_rag.add_document(
            policy_rag.new_upload_id(),
            source_name=name,
            publisher=(publisher or "").strip() or "未注明",
            category_name=(category_name or "").strip() or "综合",
            text=text,
        )
        result.update({"source_name": name, "filename": file.filename})
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception("policy upload failed")
        raise HTTPException(status_code=500, detail=f"入库失败：{e}") from e
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.get("")
def list_policies() -> dict:
    return {"documents": policy_rag.list_documents()}


@router.delete("/{upload_id}")
def delete_policy(upload_id: str) -> dict:
    ok = policy_rag.remove_document(upload_id)
    if not ok:
        raise HTTPException(status_code=404, detail="政策文件不存在")
    return {"deleted": upload_id}


@router.get("/search")
def search_policies(q: str, top_k: int = 3) -> dict:
    return {"query": q, "hits": policy_rag.search(q, top_k=top_k)}
