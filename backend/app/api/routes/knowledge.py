"""知识库 API：官方历史工单浏览 + 12 大类目录，供前端知识库页展示。"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


@router.get("/orders")
def list_orders(q: str = "", category: str = "", limit: int = 50) -> dict:
    """官方历史工单列表，支持关键词与类别过滤。"""
    settings = get_settings()
    orders = _load_jsonl(settings.data_dir / "processed" / "work_orders.jsonl")
    if q:
        ql = q.lower()
        orders = [
            o for o in orders
            if ql in str(o.get("title", "")).lower()
            or ql in str(o.get("request_content", "")).lower()
            or ql in str(o.get("reply_content", "")).lower()
        ]
    if category:
        orders = [o for o in orders if o.get("category") == category]
    total = len(orders)
    return {"total": total, "orders": orders[:limit]}


@router.get("/categories")
def list_categories() -> dict:
    settings = get_settings()
    cat_path = settings.data_dir / "categories" / "category_catalog.json"
    if not cat_path.exists():
        raise HTTPException(status_code=404, detail="category_catalog.json 不存在")
    return json.loads(cat_path.read_text(encoding="utf-8"))


@router.get("/search")
def search_similar(text: str, top_k: int = 3) -> dict:
    """BM25 相似工单检索——工作台'一键复用'数据源。"""
    from app.services.retrieval import search_similar as bm25_search

    hits = bm25_search(text, top_k=top_k)
    return {
        "query": text,
        "hits": [
            {
                "source_id": h.source_id,
                "category": h.category,
                "title": h.title,
                "request_content": h.request_content,
                "handling_departments": h.handling_departments,
                "reply_content": h.reply_content,
                "region": h.region,
                "score": h.score,
            }
            for h in hits
        ],
    }


@router.get("/stats")
def stats() -> dict:
    """热点统计：官方 18 条样例 + 本系统已受理案件的类别分布与紧急/重复占比。"""
    from app.repositories import cases as repository

    orders = _load_jsonl(get_settings().data_dir / "processed" / "work_orders.jsonl")
    official: dict[str, int] = {}
    for o in orders:
        cat = o.get("category", "未知")
        official[cat] = official.get(cat, 0) + 1

    rows = repository.list_cases(limit=200)
    demo: dict[str, int] = {}
    urgent = 0
    repeat = 0
    completed = 0
    for r in rows:
        cls = r.get("classification") or {}
        cat = cls.get("category_name") or "未分类"
        demo[cat] = demo.get(cat, 0) + 1
        u = r.get("understanding") or {}
        urgent += 1 if u.get("urgent") else 0
        repeat += 1 if u.get("repeat_request") else 0
        completed += 1 if r.get("status") == "completed" else 0

    return {
        "official_total": len(orders),
        "official_by_category": official,
        "demo_total": len(rows),
        "demo_by_category": demo,
        "demo_urgent": urgent,
        "demo_repeat": repeat,
        "demo_completed": completed,
    }
