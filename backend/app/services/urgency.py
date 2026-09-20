# -*- coding: utf-8 -*-
"""支柱二：急件识别与办理时限分级。

依据《安徽省12345热线诉求闭环办理工作规范》的差异化处理规则：
- 紧急事项（大面积停水停电、环境污染等）：第一时间处置 + 24 小时内反馈进展；
- 一般性诉求：规定时限内办结，复杂事项可「承诺办理」（不超过 9 个月）。

实现为确定性规则扫描（零 LLM 成本、可解释），并与诉求理解节点的 urgent 标记联动：
理解节点判定紧急而规则未命中隐患信号时，等级不低于「紧急」。
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_LEVEL_ORDER = {"特急": 2, "紧急": 1, "一般": 0}


@lru_cache
def _rules() -> dict:
    path = get_settings().data_dir / "dispatch" / "urgency_rules.json"
    if not path.exists():
        logger.warning("urgency_rules.json 缺失，急件分级降级为一般件")
        return {"levels": [], "legal_basis": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def assess(raw_text: str, understanding=None, work_order=None, classification=None) -> dict:
    """识别紧急等级、建议时限与即时处置动作，返回可审计的分级结论。"""
    rules = _rules()
    parts = [raw_text or ""]
    if work_order is not None:
        parts += [
            getattr(work_order, "title", "") or "",
            getattr(work_order, "event_description", "") or "",
            getattr(work_order, "handling_request", "") or "",
            getattr(work_order, "location", "") or "",
        ]
    if classification is not None:
        parts.append(getattr(classification, "category_name", "") or "")
    text = " ".join(parts)

    hits: list[dict] = []
    for lv in rules.get("levels", []):
        matched = []
        for s in lv.get("signals", []):
            if any(k in text for k in s.get("keywords", [])):
                matched.append(s["name"])
                continue
            # 正则模式匹配：覆盖"整栋楼停水两天"这类组合表述（比枚举关键词更通用）
            if any(re.search(p, text) for p in s.get("patterns", [])):
                matched.append(s["name"])
        if matched:
            hits.append({"level": lv["level"], "label": lv["label"], "limit_hint": lv["limit_hint"],
                         "actions": lv.get("actions", []), "signals": matched})

    urgent_flag = bool(getattr(understanding, "urgent", False)) if understanding is not None else False

    if hits:
        best = max(hits, key=lambda h: _LEVEL_ORDER.get(h["level"], 0))
    else:
        # 无隐患信号：urgent 标记 → 紧急；否则一般件
        default_level = "紧急" if urgent_flag else "一般"
        lv = next((x for x in rules.get("levels", []) if x["level"] == default_level), None)
        best = {
            "level": default_level,
            "label": (lv or {}).get("label", default_level),
            "limit_hint": (lv or {}).get("limit_hint", ""),
            "actions": (lv or {}).get("actions", []),
            "signals": ["诉求理解节点标记紧急"] if urgent_flag else [],
        }

    if urgent_flag and _LEVEL_ORDER.get(best["level"], 0) < 1:
        best["level"], best["label"] = "紧急", "紧急件（理解节点判定紧急）"

    legal = rules.get("legal_basis", {})
    basis = {
        "name": legal.get("name", ""),
        "clause": (legal.get("clauses") or [""])[0] if best["level"] != "一般" else (legal.get("clauses") or ["", ""])[1],
    }
    return {
        "level": best["level"],
        "label": best["label"],
        "limit_hint": best["limit_hint"],
        "actions": best["actions"],
        "signals": best["signals"],
        "basis": basis,
        "escalated_by_understanding": urgent_flag,
        "note": rules.get("escalation_note", ""),
    }
