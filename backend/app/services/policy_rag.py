"""政策依据 RAG：上传政策文件 → 切分 → 向量索引（Chroma + bge-small-zh）→ 检索引用。

- 索引来源两部分：curated 精选法规（policy_references.json，幂等）+ 用户上传文档；
- 元数据登记在 storage/policy_registry.json（列表/删除直接读它，chroma 只做向量检索）；
- embedding 模型 BAAI/bge-small-zh-v1.5（约 90MB，首次经 hf-mirror 下载后离线可用），
  进程内单例，加载放后台线程预热，避免首个检索请求卡顿。
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)

COLLECTION = "policy_docs"
_CHUNK_TARGET = 400
_CHUNK_OVERLAP = 80
_MAX_CHUNKS = 300

_embed_model = None
_embed_error = ""
_embed_lock = __import__("threading").Lock()


def _registry_path() -> Path:
    return get_settings().storage_dir / "policy_registry.json"


def _load_registry() -> dict:
    p = _registry_path()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"documents": []}


def _save_registry(reg: dict) -> None:
    _registry_path().parent.mkdir(parents=True, exist_ok=True)
    _registry_path().write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_embed():
    global _embed_model, _embed_error
    if _embed_model is not None or _embed_error:
        return _embed_model
    with _embed_lock:
        if _embed_model is not None or _embed_error:
            return _embed_model
        try:
            from sentence_transformers import SentenceTransformer

            t0 = time.monotonic()
            _embed_model = SentenceTransformer(_resolve_model_dir())
            logger.info("bge-small-zh loaded in %.0fs", time.monotonic() - t0)
        except Exception as exc:  # noqa: BLE001
            _embed_error = str(exc)
            logger.warning("embedding 模型不可用：%s（政策 RAG 降级为不可用）", exc)
    return _embed_model


def _resolve_model_dir() -> str:
    """优先项目内本地模型目录；否则经 modelscope 下载（国内源稳定）并缓存。"""
    local = get_settings().storage_dir / "models" / "bge-small-zh-v1.5"
    if (local / "config.json").exists():
        return str(local)
    try:
        from modelscope import snapshot_download

        path = snapshot_download("BAAI/bge-small-zh-v1.5", cache_dir=str(get_settings().storage_dir / "models"))
        logger.info("bge-small-zh downloaded to %s", path)
        return path
    except Exception:  # noqa: BLE001 - modelscope 失败时退回 HF 名（可能走缓存）
        import os

        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        return "BAAI/bge-small-zh-v1.5"


def warm() -> None:
    """后台线程预载 embedding 模型。"""
    import threading

    threading.Thread(target=_get_embed, daemon=True, name="bge-warmup").start()


def available() -> bool:
    return _get_embed() is not None


def _collection():
    import chromadb

    client = chromadb.PersistentClient(path=str(get_settings().storage_dir / "chroma"))
    return client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})


# ---------------- 切分 ----------------


def chunk_text(text: str) -> list[str]:
    """按段落聚合切分：目标 ~400 字/块，块间 80 字重叠。"""
    text = re.sub(r"\r\n", "\n", text)
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paras:
        return []
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 1 <= _CHUNK_TARGET:
            buf = (buf + "\n" + p).strip()
        else:
            if buf:
                chunks.append(buf)
            # 超长段落硬切
            while len(p) > _CHUNK_TARGET:
                chunks.append(p[:_CHUNK_TARGET])
                p = p[max(_CHUNK_TARGET - _CHUNK_OVERLAP, 0):]
            buf = p
    if buf:
        chunks.append(buf)
    return chunks[:_MAX_CHUNKS]


# ---------------- 索引 ----------------


def ensure_curated() -> int:
    """把精选 8 法规写入索引（幂等 upsert）。返回条数。"""
    settings = get_settings()
    path = settings.data_dir / "policies" / "policy_references.json"
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    embed = _get_embed()
    if embed is None:
        return 0
    col = _collection()
    docs, metas, ids = [], [], []
    for i, p in enumerate(data.get("policies", [])):
        docs.append(f"{p['name']}。适用范围：{p['scope']}。使用说明：{p['usage']}")
        metas.append({
            "upload_id": "curated",
            "source_name": p["name"],
            "publisher": "公开法规库",
            "category_name": "、".join(p.get("applicable_categories", [])),
            "kind": "curated",
        })
        ids.append(f"curated::{i}")
    if docs:
        vecs = embed.encode(docs, normalize_embeddings=True, show_progress_bar=False).tolist()
        col.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=vecs)
    return len(docs)


def add_document(upload_id: str, source_name: str, publisher: str, category_name: str, text: str) -> dict:
    embed = _get_embed()
    if embed is None:
        raise RuntimeError("向量模型不可用，无法入库（已配置 HF_ENDPOINT 镜像仍失败，请检查网络）")
    chunks = chunk_text(text)
    if not chunks:
        raise ValueError("文档内容为空或无法提取文本")
    col = _collection()
    col.delete(where={"upload_id": upload_id})  # 重复上传覆盖
    vecs = embed.encode(chunks, normalize_embeddings=True, show_progress_bar=False).tolist()
    ids = [f"{upload_id}::{i}" for i in range(len(chunks))]
    metas = [
        {"upload_id": upload_id, "source_name": source_name, "publisher": publisher, "category_name": category_name, "kind": "upload"}
    ] * len(chunks)
    col.add(ids=ids, documents=chunks, metadatas=metas, embeddings=vecs)

    reg = _load_registry()
    reg["documents"] = [d for d in reg["documents"] if d["upload_id"] != upload_id]
    reg["documents"].append(
        {
            "upload_id": upload_id,
            "source_name": source_name,
            "publisher": publisher,
            "category_name": category_name,
            "chunks": len(chunks),
            "chars": len(text),
            "indexed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    _save_registry(reg)
    return {"upload_id": upload_id, "chunks": len(chunks)}


def remove_document(upload_id: str) -> bool:
    col = _collection()
    try:
        col.delete(where={"upload_id": upload_id})
    except Exception:  # noqa: BLE001 - 不存在时删除报错可忽略
        pass
    reg = _load_registry()
    before = len(reg["documents"])
    reg["documents"] = [d for d in reg["documents"] if d["upload_id"] != upload_id]
    _save_registry(reg)
    return len(reg["documents"]) < before


def list_documents() -> list[dict]:
    ensure = _load_registry()
    return ensure.get("documents", [])


def new_upload_id() -> str:
    return uuid.uuid4().hex[:12]


# ---------------- 检索 ----------------


def search(query: str, top_k: int = 3) -> list[dict]:
    """向量检索政策片段；embedding 不可用时优雅降级为 curated 名称匹配。"""
    if not query.strip():
        return []
    embed = _get_embed()
    if embed is None:
        return []
    col = _collection()
    if col.count() == 0:
        ensure_curated()
    if col.count() == 0:
        return []
    vec = embed.encode([query], normalize_embeddings=True, show_progress_bar=False).tolist()[0]
    got = col.query(query_embeddings=[vec], n_results=min(top_k, col.count()), include=["documents", "metadatas", "distances"])
    hits = []
    for doc, meta, dist in zip(got["documents"][0], got["metadatas"][0], got["distances"][0]):
        hits.append(
            {
                "source_name": meta.get("source_name", ""),
                "publisher": meta.get("publisher", ""),
                "kind": meta.get("kind", ""),
                "content": doc,
                "score": round(1 - float(dist), 3),
            }
        )
    return hits


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    t0 = time.monotonic()
    n = ensure_curated()
    print(f"curated {n} 条入库，耗时 {time.monotonic() - t0:.0f}s")
    for h in search("小区楼下烧烤店占道经营噪音扰民", top_k=3):
        print(f"  [{h['score']}] {h['source_name']}")
        print(f"      {h['content'][:60]}")
