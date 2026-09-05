"""检索服务：基于 BM25 对官方标准化工单做相似检索（不依赖外部模型下载）。

用于：
- 事项分类：提供同类历史工单参考；
- 承办单位推荐：聚合历史办理单位；
- 回复建议：提供官方答复风格样例。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rank_bm25 import BM25Okapi

from app.core.config import get_settings


def _tokenize(text: str) -> list[str]:
    """中文按字符切分 + 英文/数字按词切分，兼顾 BM25。"""
    tokens = re.findall(r"[A-Za-z0-9]+", text)
    tokens += [ch for ch in text if ch.isalnum() and ord(ch) > 127]
    return tokens


@dataclass
class SimilarCase:
    source_id: str
    category: str
    title: str
    request_content: str
    handling_departments: list[str]
    reply_content: str
    region: str
    score: float


@lru_cache
def _load_orders() -> tuple[tuple[str, ...], tuple[tuple[str, dict], ...]]:
    settings = get_settings()
    path = settings.processed_orders_path
    if not path.exists():
        return (), ()
    rows: list[tuple[str, dict]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        doc = " ".join(
            [
                record.get("title", ""),
                record.get("request_content", ""),
                record.get("category", ""),
                " ".join(record.get("handling_departments", [])),
            ]
        )
        rows.append((doc, record))
    docs = tuple(doc for doc, _ in rows)
    return docs, tuple(rows)


def _build_index() -> tuple[BM25Okapi | None, list[tuple[str, dict]]]:
    docs, rows = _load_orders()
    if not docs:
        return None, []
    corpus = [_tokenize(d) for d in docs]
    if any(len(c) == 0 for c in corpus):
        corpus = [c or ["x"] for c in corpus]
    return BM25Okapi(corpus), list(rows)


def search_similar(query: str, top_k: int = 3) -> list[SimilarCase]:
    index, rows = _build_index()
    if index is None:
        return []
    scores = index.get_scores(_tokenize(query) or ["x"])
    ranked = sorted(range(len(rows)), key=lambda i: scores[i], reverse=True)[:top_k]
    results: list[SimilarCase] = []
    for i in ranked:
        if scores[i] <= 0:
            continue
        r = rows[i][1]
        results.append(
            SimilarCase(
                source_id=r.get("source_id", ""),
                category=r.get("category", ""),
                title=r.get("title", ""),
                request_content=r.get("request_content", "")[:300],
                handling_departments=list(r.get("handling_departments", [])),
                reply_content=r.get("reply_content", "")[:300],
                region=r.get("region", ""),
                score=round(float(scores[i]), 3),
            )
        )
    return results


@lru_cache
def load_category_catalog() -> list[dict]:
    settings = get_settings()
    path: Path = settings.category_catalog_path
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("categories", [])


def catalog_brief() -> str:
    lines = []
    for item in load_category_catalog():
        lines.append(f"- {item['code']}：{item['name']}")
    return "\n".join(lines)
