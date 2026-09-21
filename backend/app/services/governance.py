# -*- coding: utf-8 -*-
"""支柱三：诉求治理——从"办单"到"治事"。

三条治理能力（全部规则式、可解释）：
1. 重复诉求督办：识别"再次反映/多次反映"等标记，提示督办风险
   （依据规范：群众多次反映、承办单位办理不到位的，热线联合政府督查机构专项督办）；
2. 并案聚集预警：同点位同类诉求 7 日内聚集（复用 early_warning），提示并案与
   未诉先办主动治理；
3. 退回风险提示：职责交叉工单提前标注退回风险与协调建议
   （依据规范：承办单位不得随意退回，3 次交办仍无法确定责任主体的由热线指定）。
"""
from __future__ import annotations

import logging

from app.repositories import cases as repository
from app.services import early_warning

logger = logging.getLogger(__name__)

# 重复诉求标记（口语与工单写法）
_REPEAT_MARKERS = ("再次反映", "多次反映", "又一次", "第二次反映", "再次投诉", "多次投诉",
                   "尚未解决", "仍未解决", "一直没解决", "还是没人", "又反映", "第3次", "第三次")


def _repeat(case) -> dict | None:
    """识别本案是否属重复诉求，并统计同点位同分类历史件数。"""
    text = f"{case.raw_text or ''} {getattr(case.work_order, 'title', '') or ''}"
    markers = [m for m in _REPEAT_MARKERS if m in text]

    # 同点位同分类历史件数（复用聚集检测的点位匹配口径）
    related = 0
    try:
        warning = early_warning.detect(case)
        related = len(warning["related"]) if warning else 0
    except Exception:  # noqa: BLE001 - 治理提示失败不影响案件返回
        logger.warning("repeat detection: 聚集检测失败", exc_info=True)

    if not markers and related == 0:
        return None
    parts = []
    if markers:
        parts.append(f"文本含重复诉求标记（{'、'.join(markers[:2])}）")
    if related:
        parts.append(f"近 {early_warning.WINDOW_DAYS} 日内同点位同分类另有 {related} 件")
    return {
        "is_repeat": bool(markers),
        "markers": markers[:3],
        "related_count": related,
        "message": "本案疑似重复诉求：" + "；".join(parts) +
                   "。建议核查前次办理结果，必要时按规范启动督办（多次反映、办理不到位的可联合督查机构专项督办）。",
    }


def _return_risk(case) -> dict | None:
    """从派单决策中提取退回风险（职责交叉等），转为治理提示。"""
    routing = case.routing
    if routing is None:
        return None
    risk = (getattr(routing, "return_risk", "") or "").strip()
    if not risk or "权责清晰" in risk:
        return None
    return {
        "level": "高" if "职责交叉" in risk else "中",
        "message": risk,
        "suggestion": "建议派件前明确主办单位并抄送属地热线主管部门督促协调，降低退回重派概率。",
    }


def assess(case, routing=None, deadline: dict | None = None) -> dict:
    """产出治理建议包（重复诉求 / 并案预警 / 退回风险 / 时限督办）。"""
    out: dict = {}
    try:
        warning = early_warning.detect(case)
    except Exception:  # noqa: BLE001
        logger.warning("governance: 聚集检测失败", exc_info=True)
        warning = None

    repeat = _repeat(case)
    risk = _return_risk(case if routing is None else case)

    if warning:
        out["aggregation"] = {
            "kind": warning.get("kind"),
            "message": warning.get("message"),
            "total": warning.get("total"),
            "window_days": warning.get("window_days"),
            "related": warning.get("related", []),
            "suggestion": "建议并案核查、转主动治理工单，避免同类诉求继续扩散。",
        }
    if repeat:
        out["repeat"] = repeat
    if risk:
        out["return_risk"] = risk
    # 支柱五：时限督办（临期/超期）
    if deadline and deadline.get("state") in ("临期", "超期"):
        out["overdue"] = {
            "level": "超期" if deadline["state"] == "超期" else "临期",
            "message": f"办理时限{deadline['state']}（到期 {deadline.get('due_at', '')}，"
                       f"剩余 {deadline.get('remaining_hours', 0)} 小时）",
            "suggestion": deadline.get("supervision", ""),
        }

    suggestions = []
    if out.get("aggregation"):
        suggestions.append("并案核查同点位同类诉求，评估是否转主动治理")
    if repeat and repeat.get("is_repeat"):
        suggestions.append("核查前次办理结果，办理不到位的按规范启动督办")
    if risk:
        suggestions.append("派前协调主办单位并抄送属地热线主管部门")
    if out.get("overdue"):
        suggestions.append(out["overdue"]["suggestion"] or "按时限要求督办承办单位")
    out["suggestions"] = suggestions
    out["has_governance_alert"] = bool(suggestions)
    return out
