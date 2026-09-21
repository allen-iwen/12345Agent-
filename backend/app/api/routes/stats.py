# -*- coding: utf-8 -*-
"""统计 API：交叉复核分歧统计、时限督办概况。

这些数字是「可信 AI」的可量化证据：复核一致率、分歧率、人工介入率，
以及临期/超期案件数——都直接来自案件数据，不依赖任何手工填报。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from app.repositories import cases as repository
from app.services import deadline as deadline_svc
from app.services import review

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/review")
def review_stats(limit: int = 300) -> dict:
    """第二模型交叉复核统计：一致率 / 分歧率 / 人工介入率。"""
    rows = repository.list_cases(limit=limit)
    checked = agreed = diverged = gated = 0
    divergence_samples: list[dict] = []
    for r in rows:
        cls = r.get("classification") or {}
        cc = cls.get("cross_check") or {}
        if not cc or cc.get("agreement") is None:
            continue
        checked += 1
        if cc.get("agreement"):
            agreed += 1
        else:
            diverged += 1
            if len(divergence_samples) < 10:
                wo = r.get("work_order") or {}
                divergence_samples.append({
                    "case_id": r["case_id"],
                    "title": wo.get("title") or (r.get("raw_text") or "")[:30],
                    "primary": cc.get("primary_choice"),
                    "secondary": cc.get("secondary_choice"),
                    "secondary_name": cc.get("secondary_name"),
                    "secondary_model": cc.get("secondary_model"),
                })
        if cls.get("needs_human_judgment"):
            gated += 1
    return {
        "config": review.status(),
        "checked_cases": checked,
        "agreed": agreed,
        "diverged": diverged,
        "agreement_rate": round(agreed / checked, 4) if checked else None,
        "divergence_rate": round(diverged / checked, 4) if checked else None,
        "human_gated": gated,
        "human_gate_rate": round(gated / checked, 4) if checked else None,
        "divergence_samples": divergence_samples,
        "note": "分歧即标记人工判断；样本来自真实案件，未做任何人工修饰",
    }


@router.get("/deadlines")
def deadline_stats() -> dict:
    """时限督办概况：正常/临期/超期分布 + 最紧迫案件。"""
    rows = repository.list_cases(limit=300)
    buckets = {"正常": 0, "临期": 0, "超期": 0, "已办结": 0}
    urgent: list[dict] = []
    for r in rows:
        level = ((r.get("assessment") or {}).get("urgency") or {}).get("level", "一般")
        dl = deadline_svc.compute(r["created_at"], level, closed=r["status"] == "completed")
        buckets[dl["state"]] = buckets.get(dl["state"], 0) + 1
        if dl["state"] in ("临期", "超期"):
            wo = r.get("work_order") or {}
            urgent.append({
                "case_id": r["case_id"],
                "title": wo.get("title") or (r.get("raw_text") or "")[:30],
                "level": level,
                "state": dl["state"],
                "due_at": dl["due_at"],
                "remaining_hours": dl["remaining_hours"],
                "supervision": dl.get("supervision", ""),
            })
    urgent.sort(key=lambda x: (x["state"] != "超期", x["remaining_hours"]))
    return {
        "total": len(rows),
        "buckets": buckets,
        "urgent": urgent[:20],
        "note": "临期阈值：剩余 ≤20% 或 ≤4 小时；一般件时限为建议值（待与芜湖细则核对）",
    }
