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


def assess(
    raw_text: str,
    understanding=None,
    work_order=None,
    classification=None,
    vision_signals: list[dict] | None = None,
    decision_signals: dict | None = None,
) -> dict:
    """识别紧急等级、建议时限与即时处置动作，返回可审计的分级结论。

    vision_signals：图片证据的视觉结论；存在人类安全隐患判定时按险种定级。
    decision_signals：System One 决策模型结论（含 is_hazard / hazard_level / mass_impact）。
    """
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

    # 图片证据升级：按「险种定级表」确定等级（不采用模型自报 severity——实测其跨次不稳定），
    # 仅在险种无法映射时回退到模型分的 severity。
    hazard_levels = rules.get("hazard_levels", {})
    vision_levels: list[tuple[str, str]] = []  # (险种, 等级)
    for v in (vision_signals or []):
        if not (v and v.get("hazard")):
            continue
        htype = str(v.get("hazard_type") or "").strip()
        level = hazard_levels.get(htype) or v.get("severity") or "一般"
        if level not in _LEVEL_ORDER:
            level = "一般"
        vision_levels.append((htype or "其他", level))

    if vision_levels:
        top_type, top_level = max(vision_levels, key=lambda x: _LEVEL_ORDER.get(x[1], 0))
        if _LEVEL_ORDER.get(top_level, 0) > _LEVEL_ORDER.get(best["level"], 0):
            lv = next((x for x in rules.get("levels", []) if x["level"] == top_level), None)
            best = {
                "level": top_level,
                "label": (lv or {}).get("label", top_level) + "（图片证据定级）",
                "limit_hint": (lv or {}).get("limit_hint", ""),
                "actions": (lv or {}).get("actions", []),
                "signals": best.get("signals", []) + [f"图片证据：{top_type}（按险种定级）"],
            }
        else:
            # 险种等级未超过文本判定，仅补充可见证据说明
            best["signals"] = best.get("signals", []) + [
                "图片证据：" + "、".join(t for t, _ in vision_levels)
            ]

    # 决策模型信号（System One）：存在人身安全隐患 / 大面积影响时参与定级
    conclusions = (decision_signals or {}).get("conclusions") or {}
    if (decision_signals or {}).get("available") and conclusions:
        model_level = conclusions.get("hazard_level") if conclusions.get("is_hazard") else None
        if model_level and _LEVEL_ORDER.get(model_level, 0) > _LEVEL_ORDER.get(best["level"], 0):
            lv = next((x for x in rules.get("levels", []) if x["level"] == model_level), None)
            best = {
                "level": model_level,
                "label": (lv or {}).get("label", model_level) + "（决策模型判定）",
                "limit_hint": (lv or {}).get("limit_hint", ""),
                "actions": (lv or {}).get("actions", []),
                "signals": best.get("signals", []) + [
                    f"决策模型：疑似人身安全隐患（严重度 {conclusions.get('severity_score')}）"
                ],
            }
        elif conclusions.get("mass_impact") and _LEVEL_ORDER.get(best["level"], 0) < 1:
            lv = next((x for x in rules.get("levels", []) if x["level"] == "紧急"), None)
            best = {
                "level": "紧急",
                "label": (lv or {}).get("label", "紧急") + "（决策模型判定）",
                "limit_hint": (lv or {}).get("limit_hint", ""),
                "actions": (lv or {}).get("actions", []),
                "signals": best.get("signals", []) + ["决策模型：涉及大面积/群体性影响"],
            }
        else:
            best["signals"] = best.get("signals", []) + ["决策模型：未判定人身安全隐患"]

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
