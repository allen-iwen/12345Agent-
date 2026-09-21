# -*- coding: utf-8 -*-
"""知识词条（wiki）API：维护办理口径与案例经验，支持草稿→发布与版本回看。

- 坐席可建/改草稿；发布需审核员或管理员（口径对外生效前必须有人把关）
- 每次保存自动 +1 版本并留修订记录，可回看任一历史版本
- 智能体回写：案件定稿后可「沉淀为词条」（由答复与派单结论生成草稿，人工确认后发布）
- 已发布词条可选择性注入答复草拟（口径一致），默认关闭以免污染生成
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.repositories import cases as cases_repo
from app.repositories import wiki as repo
from app.services import auth, policy_rag

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wiki", tags=["wiki"])


class EntryRequest(BaseModel):
    slug: str = Field(description="词条标识（英文/数字/连字符）")
    title: str
    body_md: str = ""
    category: str = Field(default="办事指南", description="政策解读|部门职责|办事指南|案例经验|口径话术")
    tags: list[str] = Field(default_factory=list)
    note: str = Field(default="", description="本次修订说明")


class PublishRequest(BaseModel):
    note: str = ""


class DistillRequest(BaseModel):
    category: str = "案例经验"
    title: str | None = None


def _check_slug(slug: str) -> str:
    s = (slug or "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9\-]{1,60}", s):
        raise HTTPException(status_code=400, detail="slug 只允许小写字母、数字与连字符（2–61 位）")
    return s


@router.get("")
def list_entries(category: str | None = None, status: str | None = None, q: str | None = None) -> dict:
    items = repo.list_entries(category=category, status=status, q=q)
    for it in items:
        if len(it.get("body_md", "")) > 200:
            it["excerpt"] = it["body_md"][:200] + "…"
    return {"counts": repo.counts(), "categories": list(repo.CATEGORIES), "items": items}


@router.get("/{slug}")
def get_entry(slug: str) -> dict:
    entry = repo.get(slug)
    if entry is None:
        raise HTTPException(status_code=404, detail="词条不存在")
    entry["revisions"] = repo.revisions(slug)
    return entry


@router.get("/{slug}/revisions/{version}")
def get_revision(slug: str, version: int) -> dict:
    rev = repo.revision_body(slug, version)
    if rev is None:
        raise HTTPException(status_code=404, detail="该版本不存在")
    return rev


@router.post("")
def save_entry(req: EntryRequest, request: Request,
               user: dict = Depends(auth.require_role("agent", "reviewer", "dispatcher"))) -> dict:
    slug = _check_slug(req.slug)
    if req.category not in repo.CATEGORIES:
        raise HTTPException(status_code=400, detail=f"未知分类：{req.category}（可选：{'、'.join(repo.CATEGORIES)}）")
    out = repo.upsert(slug, req.title, req.body_md, req.category, req.tags,
                      author=user.get("actor", ""), note=req.note)
    auth.audit(user.get("actor", ""), user.get("role", ""), "保存词条", "wiki", slug,
               {"version": out["version"], "category": req.category}, request)
    return {"ok": True, **out}


@router.post("/{slug}/publish")
def publish_entry(slug: str, req: PublishRequest, request: Request,
                  user: dict = Depends(auth.require_role("reviewer"))) -> dict:
    if repo.get(slug) is None:
        raise HTTPException(status_code=404, detail="词条不存在")
    ok = repo.publish(slug, reviewer=user.get("actor", ""))
    auth.audit(user.get("actor", ""), user.get("role", ""), "发布词条", "wiki", slug, {"note": req.note}, request)
    return {"ok": ok, "slug": slug, "status": "published"}


@router.post("/{slug}/unpublish")
def unpublish_entry(slug: str, request: Request,
                    user: dict = Depends(auth.require_role("reviewer"))) -> dict:
    ok = repo.revise_status(slug, "draft", reviewer=user.get("actor", ""))
    if not ok:
        raise HTTPException(status_code=404, detail="词条不存在")
    auth.audit(user.get("actor", ""), user.get("role", ""), "下架词条", "wiki", slug, None, request)
    return {"ok": True, "slug": slug, "status": "draft"}


@router.delete("/{slug}")
def delete_entry(slug: str, request: Request,
                 user: dict = Depends(auth.require_role("admin"))) -> dict:
    ok = repo.delete(slug)
    if not ok:
        raise HTTPException(status_code=404, detail="词条不存在")
    auth.audit(user.get("actor", ""), user.get("role", ""), "删除词条", "wiki", slug, None, request)
    return {"ok": True}


@router.post("/distill/{case_id}")
def distill_from_case(case_id: str, req: DistillRequest, request: Request,
                      user: dict = Depends(auth.require_role("agent", "reviewer"))) -> dict:
    """智能体回写：把案件的派单与答复结论沉淀为词条草稿（人工确认后发布）。"""
    row = cases_repo.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="案件不存在")
    wo = row.get("work_order") or {}
    cls = row.get("classification") or {}
    rt = row.get("routing") or {}
    rd = row.get("reply_draft") or {}
    title = req.title or f"{wo.get('title') or '案例'} · 办理口径"
    co = [d.get("name") for d in (rt.get("departments") or []) if d.get("role") != "建议承办单位"]
    lines = [
        f"## 事项类别\n{cls.get('category_name') or '（未定）'}（置信度 {cls.get('confidence')}）",
        f"## 承办单位\n主办：{rt.get('primary') or '（未定）'}"
        + (f"\n协办/指导：{'、'.join(co)}" if co else "")
        + (f"\n派单路径：{rt.get('dispatch_path')}｜依据：{'；'.join(e.get('detail', '')[:60] for e in (rt.get('evidence_chain') or [])[:2])}"
           if rt.get("dispatch_path") else ""),
    ]
    if rt.get("return_risk"):
        lines.append(f"## 退回风险\n{rt['return_risk']}")
    if rd.get("reply_text"):
        lines.append(f"## 答复口径（节选）\n{rd['reply_text'][:600]}")
    if rd.get("policy_refs"):
        lines.append("## 政策依据\n" + "、".join(rd["policy_refs"]))
    body = "\n\n".join(lines)
    slug = f"case-{case_id[:8]}-{cls.get('category_code') or 'misc'}"
    out = repo.upsert(slug, title, body, req.category, tags=[cls.get("category_name") or "", "案例复盘"],
                      author=user.get("actor", ""), note=f"由案件 {case_id[:10]} 自动沉淀", source_case_id=case_id)
    auth.audit(user.get("actor", ""), user.get("role", ""), "沉淀词条", "wiki", slug,
               {"case_id": case_id, "version": out["version"]}, request)
    return {"ok": True, "slug": slug, "version": out["version"], "status": "draft",
            "preview": body[:300]}


@router.get("/search/published")
def search_published(q: str, limit: int = 3) -> dict:
    """供答复草拟引用：检索已发布口径（与政策 RAG 互补）。"""
    items = [it for it in repo.list_entries(status="published", q=q, limit=limit)]
    if not items:
        # 无精确命中时退化为向量检索名称匹配（口径层不阻塞主链路）
        try:
            hits = policy_rag.search(q, top_k=limit)
            return {"items": [], "rag_hits": hits, "note": "词条无命中，已回退政策 RAG"}
        except Exception:  # noqa: BLE001
            return {"items": [], "note": "无命中"}
    return {"items": [{"slug": it["slug"], "title": it["title"], "category": it["category"],
                       "excerpt": (it.get("body_md") or "")[:200]} for it in items]}
