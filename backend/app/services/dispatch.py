# -*- coding: utf-8 -*-
"""支柱一：属地 + 部门双维派单决策。

设计要点（可解释、零 LLM 成本、可复现验证）：
1. 三层决策：专业直派 → 属地主办 → 类别兜底；
2. 依据《安徽省12345热线诉求闭环办理工作规范》「属地管理、分级负责」原则，
   并由官方样例工单的实际承办单位实证（属地政府/开发区 89%，市直部门 11%）；
3. 输出「决策包」：主办 + 协办/业务指导 + 依据链 + 退回风险，全部可追溯到规则条目；
4. 与 LLM 的关系：本模块产出的主办单位作为**规则锚点**交给 LLM 复核，
   分歧时标记人工判断（规则锚定 + 模型复核，避免纯模型自由发挥）。
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def _rules() -> dict:
    path: Path = get_settings().data_dir / "dispatch" / "dispatch_rules.json"
    if not path.exists():
        logger.warning("dispatch_rules.json 缺失，派单规则降级为空")
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    # 区划关键词按长度降序，避免"弋江区"抢走"高新区（弋江区）"
    data["district_map"] = sorted(data.get("district_map", []), key=lambda kv: -len(kv["keyword"]))
    return data


@lru_cache
def _dept_rules() -> dict:
    """部门职责规则库（category_code → 主办部门/协办部门/职责描述）。"""
    path = get_settings().department_rules_path
    if not path.exists():
        return {}
    rules = json.loads(path.read_text(encoding="utf-8")).get("rules", [])
    return {r.get("category_code"): r for r in rules}


def _text_of(work_order, raw_text: str) -> str:
    parts = [raw_text or ""]
    if work_order is not None:
        parts += [
            getattr(work_order, "title", "") or "",
            getattr(work_order, "location", "") or "",
            getattr(work_order, "event_description", "") or "",
            getattr(work_order, "region", "") or "",
            getattr(work_order, "handling_request", "") or "",
        ]
    return " ".join(parts)


def locate_district(text: str) -> dict | None:
    """识别诉求所属芜湖属地区划（区县/开发区）。"""
    for item in _rules().get("district_map", []):
        if item["keyword"] in text:
            return item
    return None


def specialist(text: str) -> dict | None:
    """专业直派：行业性极强的诉求直派专业承办单位（对应规范"权责清晰可直接转承办单位"）。"""
    for rule in _rules().get("specialist_rules", []):
        if any(k in text for k in rule["keywords"]):
            return rule
    return None


def _co_units(category_code: str | None, primary: str) -> list[dict]:
    """协办/业务指导单位：来自部门职责规则库（去重、排除主办自身）。"""
    if not category_code:
        return []
    rule = _dept_rules().get(category_code)
    if not rule:
        return []
    out: list[dict] = []
    seen = {primary}
    main_dept = rule.get("department") or ""
    if main_dept and main_dept not in seen:
        seen.add(main_dept)
        out.append({"name": main_dept, "role": "业务指导单位", "reason": rule.get("responsibilities", "")[:120]})
    for d in rule.get("co_departments", []) or []:
        if d and d not in seen:
            seen.add(d)
            out.append({"name": d, "role": "协办单位", "reason": f"按{rule.get('category_name', '')}职责分工协同处置"})
    return out


def decide(work_order, classification, raw_text: str, decision_signals: dict | None = None) -> dict:
    """三层派单决策，返回决策包（含依据链与退回风险）。

    decision_signals：System One 决策模型的职责交叉/退回风险判断（可选，参与风险定级）。
    """
    rules = _rules()
    text = _text_of(work_order, raw_text)
    category_code = getattr(classification, "category_code", None) if classification else None
    category_name = getattr(classification, "category_name", None) if classification else None

    evidence: list[dict] = []
    legal = rules.get("legal_basis", {})
    if legal:
        evidence.append({
            "type": "政策依据",
            "source": legal.get("name", ""),
            "detail": "；".join(legal.get("clauses", [])[:2]),
        })

    # 决策模型信号（可选）：职责交叉判断进入依据链
    model = (decision_signals or {}).get("conclusions") or {}
    model_available = bool((decision_signals or {}).get("available"))
    if model_available and model.get("cross_duty"):
        evidence.append({
            "type": "模型判断",
            "source": "System One 决策模型",
            "detail": f"判定为职责交叉（退回风险分 {model.get('return_risk_score')}），建议派前协调并抄送属地热线主管部门",
        })

    # ---- 第 1 层：专业直派 ----
    sp = specialist(text)
    if sp:
        primary = sp["units"][0]
        evidence.append({"type": "专业直派", "source": f"派单规则：{sp['name']}", "detail": sp["reason"]})
        co = [{"name": u, "role": "协办单位" if i else "专业协同", "reason": sp["reason"]}
              for i, u in enumerate(sp["units"][1:])]
        return {
            "path": "专业直派",
            "primary": primary,
            "primary_kind": "专业机构/市直部门",
            "district": None,
            "co_units": co,
            "evidence_chain": evidence,
            "return_risk": rules.get("return_risk", {}).get("low", ""),
            "confidence": 0.9,
            "matched_rule": sp["name"],
        }

    # ---- 第 2 层：属地主办 ----
    district = locate_district(text)
    if district:
        primary = district["unit"]
        evidence.append({
            "type": "属地判定",
            "source": "诉求文本地点识别",
            "detail": f"识别到属地区划「{district['keyword']}」（{district['kind']}）→ 按属地管理原则由 {primary} 主办",
        })
        co = _co_units(category_code, primary)
        dept_rule = _dept_rules().get(category_code or "", {})
        if dept_rule:
            evidence.append({
                "type": "职责依据",
                "source": "部门职责规则库",
                "detail": f"{dept_rule.get('category_name', '')}：{dept_rule.get('department', '')} 牵头业务指导；{dept_rule.get('responsibilities', '')[:100]}",
            })
        evidence.append({
            "type": "历史案例",
            "source": "官方样例工单（18 条）",
            "detail": "同批次样例中 89%（16/18）由属地政府/开发区承办，仅 11% 直派市直部门——与本判定一致",
        })
        # 职责交叉 → 退回风险（决策模型判定为职责交叉时直接按高风险管理）
        risk_key = "high" if (len(co) >= 2 or (model_available and model.get("cross_duty"))) else ("medium" if co else "low")
        risk = rules.get("return_risk", {}).get(risk_key, "")
        return {
            "path": "属地主办",
            "primary": primary,
            "primary_kind": f"属地{district['kind']}",
            "district": district["unit"],
            "co_units": co,
            "evidence_chain": evidence,
            "return_risk": risk.format(n=len(co) + 1) if "{n}" in risk else risk,
            "confidence": 0.85 if co else 0.9,
            "matched_rule": f"属地管理原则（{district['keyword']}）",
            "model_cross_duty": bool(model_available and model.get("cross_duty")),
            "model_return_risk_score": model.get("return_risk_score"),
        }

    # ---- 第 3 层：类别兜底（无地点线索时按事项类别推市直部门）----
    fallback = rules.get("category_city_dept", {}).get(category_code or "", "")
    co = _co_units(category_code, fallback)
    evidence.append({
        "type": "类别兜底",
        "source": "事项类别 → 市直主管部门映射",
        "detail": f"诉求文本未识别到属地区划，按事项类别「{category_name or '未知'}」推 {fallback or '待人工判断'}；建议人工确认属地后补派",
    })
    return {
        "path": "类别兜底",
        "primary": fallback or "待人工判断",
        "primary_kind": "市直部门",
        "district": None,
        "co_units": co,
        "evidence_chain": evidence,
        "return_risk": rules.get("return_risk", {}).get("medium", ""),
        "confidence": 0.6,
        "matched_rule": "类别映射",
    }
