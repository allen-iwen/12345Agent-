# -*- coding: utf-8 -*-
"""12345 领域决策问题集：把「判断」从提示词里抽出来，交给 System One 决策模型。

核心用法（官方建议的 speculative fan-out）：
**一次请求问完所有独立问题**——长 state 只发送一次，多问几个问题几乎不增加延迟与成本；
只对部分输入才有意义的问题（例如非隐患类案件的安全等级）同样先问，由代码决定取用哪些。

覆盖的判断点：
- 事项分类（Choice，12 大类 + 兜底）→ 带校准概率与置信度，供门控
- 安全隐患（Noul）与严重程度（Score）→ 语义识别，弥补关键词表只能字面匹配的短板
- 大面积影响（Noul）→ 紧急件判定
- 职责交叉（Noul）与退回风险（Score）→ 派单前风险提示
- 重复诉求（Noul）→ 督办提示
- 答复合规三维（Score：过度承诺 / 未正面回应 / 推诿）+ 隐私（Noul）→ 与规则审查互补

注意（官方「参差性」说明）：模型**不擅长算术与日期**，这两类一律留在代码里；
因此本模块只问语义判断，所有计数/到期计算仍由 `deadline.py` 等确定性代码完成。
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache

from app.core.config import get_settings
from app.services import decision, retrieval

logger = logging.getLogger(__name__)

STATE_CHAR_LIMIT = 1500  # 官方：state 臃肿会降低准确率，先过滤再发送


@lru_cache
def _category_catalog() -> list[dict]:
    return retrieval.load_category_catalog()


def category_criteria() -> dict[str, str]:
    """Choice 选项：用「定义 + 典型情形 + 易混淆辨析」描述每个类别，并留兜底选项。"""
    out: dict[str, str] = {}
    for c in _category_catalog():
        parts = [c.get("definition") or c.get("name", "")]
        if c.get("typical"):
            parts.append("典型：" + "、".join(c["typical"][:6]))
        if c.get("contrast"):
            parts.append(c["contrast"])
        out[c["code"]] = "；".join(parts)[:500]
    out["other"] = "以上 12 类均不适用，或信息不足无法归入任何类别"
    return out


def category_name(code: str | None) -> str | None:
    if not code or code == "other":
        return None
    return next((c["name"] for c in _category_catalog() if c["code"] == code), None)


def build_questions() -> dict[str, dict]:
    """全案决策问题集（一次请求问完）。"""
    q = {}
    q.update(route_questions())
    q.update(reply_questions())
    q["category"] = decision.choice(
        "这段群众诉求的核心事项属于哪一类？以诉求的核心事项为准，而不是地点或主体类型。",
        category_criteria(),
    )
    q["repeat_request"] = decision.noul(
        "诉求是否表明此前已反映过同类问题（再次反映、多次反映、至今未解决）？",
        {"true": "明确提到此前反映过或问题反复出现", "false": "首次反映，未提及历史投诉"},
    )
    return q


def route_questions() -> dict[str, dict]:
    """流转/决策阶段的问题（答复尚未生成时即可问）。"""
    return {
        "safety_hazard": decision.noul(
            "诉求中是否包含可能危害人身安全的情形（如燃气泄漏、电线坠落、井盖缺失、消防通道堵塞、危房、电梯困人）？",
            {"true": "描述了具体的即时人身安全风险", "false": "仅为生活不便、服务纠纷、咨询建议或一般环境问题"},
        ),
        "severity": decision.score(
            "若存在安全隐患，其严重程度处于哪个位置？（无隐患时按最低档）",
            [
                "无安全隐患或仅为轻微影响",
                "影响面较大或存在潜在风险，但无即时人身危险",
                "有人身安全风险，需立即处置",
            ],
        ),
        "mass_impact": decision.noul(
            "诉求是否涉及大面积或群体性影响（如整片停水停电、多人共同反映、整栋楼受影响）？",
            {"true": "明确提到大范围或多人受影响", "false": "仅单个住户或单个点位的问题"},
        ),
        "cross_duty": decision.noul(
            "该诉求的办理是否涉及两个及以上部门职责交叉、难以直接确定唯一主办单位？",
            {"true": "需要多部门协同或职责边界不清", "false": "职责清晰，可由单一单位主办"},
        ),
        "return_risk": decision.score(
            "该工单若直接派发，被承办单位退回重派的可能性有多大？",
            ["几乎不会被退回", "有可能被退回，需要说明依据", "很可能被退回，需要先协调"],
        ),
    }


def reply_questions() -> dict[str, dict]:
    """答复阶段的问题（需要草拟答复文本）。"""
    return {
        "reply_overpromise": decision.score(
            "草拟答复是否对办理结果作出超出职责的承诺（如保证解决、承诺具体时限）？",
            ["未作任何超出职责的承诺", "措辞偏乐观但未明确承诺", "明确承诺了结果或时限"],
        ),
        "reply_addresses_request": decision.noul(
            "草拟答复是否正面回应了群众的核心诉求（而非只讲流程或政策）？",
            {"true": "针对诉求给出了核查情况、办理方向或依据", "false": "仅泛泛说明流程，未回应当事诉求"},
        ),
        "reply_privacy": decision.noul(
            "草拟答复中是否出现了手机号、身份证号、门牌号等个人敏感信息？",
            {"true": "出现可定位到个人的敏感信息", "false": "未出现个人敏感信息"},
        ),
    }


def _conclusions(a: dict) -> dict:
    severity = (a.get("severity") or {}).get("value")
    return {
        "is_hazard": bool((a.get("safety_hazard") or {}).get("value")),
        # 严重度阈值经实测收紧：JEV 对非隐患文本（如烧烤油烟）也可能给出 0.85 的严重度，
        # 原 ≥0.8 升紧急会过度升级；改为 ≥1.0 升紧急、≥1.8 升特急（真实隐患如电线坠落/井盖缺失约在 1.8–2.0）
        "hazard_level": ("特急" if (severity or 0) >= 1.8 else "紧急" if (severity or 0) >= 1.0 else "一般"),
        "severity_score": severity,
        "mass_impact": bool((a.get("mass_impact") or {}).get("value")),
        "cross_duty": bool((a.get("cross_duty") or {}).get("value")),
        "return_risk_score": (a.get("return_risk") or {}).get("value"),
        "repeat_request": bool((a.get("repeat_request") or {}).get("value")),
        "reply_overpromise_score": (a.get("reply_overpromise") or {}).get("value"),
        "reply_addresses_request": (a.get("reply_addresses_request") or {}).get("value"),
        "reply_privacy": (a.get("reply_privacy") or {}).get("value"),
    }


def route_signals(raw_text: str, work_order=None, vision_summaries: list[str] | None = None) -> dict:
    """流转/决策阶段信号（一次调用，5 个问题）；未启用或失败时 available=False。"""
    state = build_state(raw_text, work_order, vision_summaries)
    result = decision.ask(state, route_questions())
    if not result.get("available"):
        return result
    result["conclusions"] = _conclusions(result.get("answers") or {})
    return result


def reply_signals(raw_text: str, reply_text: str, work_order=None) -> dict:
    """答复阶段信号（一次调用，3 个问题）；未启用或失败时 available=False。"""
    state = build_state(raw_text, work_order, None, reply_text)
    result = decision.ask(state, reply_questions())
    if not result.get("available"):
        return result
    result["conclusions"] = _conclusions(result.get("answers") or {})
    return result


def assess(raw_text: str, work_order=None, vision_summaries: list[str] | None = None,
           reply_text: str | None = None, questions: dict[str, dict] | None = None) -> dict:
    """一次调用完成全案判断（10 个问题）；返回带门控的决策包。未配置时 available=False。"""
    state = build_state(raw_text, work_order, vision_summaries, reply_text)
    result = decision.ask(state, questions or build_questions())
    if not result.get("available"):
        return result

    a = result["answers"]
    cat = a.get("category") or {}
    bundle = {
        "category_code": cat.get("value"),
        "category_name": category_name(cat.get("value")),
        "category_probabilities": cat.get("probabilities") or {},
        "category_confidence": cat.get("confidence"),
        "category_gate": cat.get("gate"),
        **_conclusions(a),
    }
    result["bundle"] = bundle
    result["conclusions"] = _conclusions(a)
    return result


def build_state(raw_text: str, work_order=None, vision_summaries: list[str] | None = None,
                reply_text: str | None = None) -> dict:
    """构造精简 state：只放判断需要的内容（不含无关历史，避免上下文腐化）。"""
    state: dict = {"诉求原文": (raw_text or "")[:STATE_CHAR_LIMIT]}
    if work_order is not None:
        state["工单标题"] = getattr(work_order, "title", "") or ""
        state["事发地点"] = getattr(work_order, "location", "") or ""
        state["事件描述"] = (getattr(work_order, "event_description", "") or "")[:600]
    if vision_summaries:
        state["现场照片结论"] = "；".join(s for s in vision_summaries if s)[:400]
    if reply_text:
        state["草拟答复"] = reply_text[:800]
    return {k: v for k, v in state.items() if v}


def classify_only(raw_text: str, work_order=None, vision_summaries: list[str] | None = None) -> dict:
    """仅用决策模型做事项分类（评测用：不调用生成模型，便于与外接 LLM 基线对比）。"""
    questions = {
        "category": decision.choice(
            "这段群众诉求的核心事项属于哪一类？以诉求的核心事项为准，而不是地点或主体类型。",
            category_criteria(),
        )
    }
    state = build_state(raw_text, work_order, vision_summaries)
    result = decision.ask(state, questions)
    if not result.get("available"):
        return result
    cat = (result["answers"] or {}).get("category") or {}
    result["category_code"] = cat.get("value")
    result["category_name"] = category_name(cat.get("value"))
    result["confidence"] = cat.get("confidence")
    result["gate"] = cat.get("gate")
    return result
