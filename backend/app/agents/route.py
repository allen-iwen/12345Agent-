# -*- coding: utf-8 -*-
"""Agent 节点：承办单位推荐（支柱一：属地 + 部门双维派单）。

流程（规则锚定 + 模型复核，避免纯模型自由发挥）：
1. 规则引擎 `dispatch.decide()` 依据「属地管理、分级负责」原则与职责规则库，
   产出主办单位、协办/业务指导单位、依据链、退回风险——作为**锚点**；
2. LLM 在锚点基础上复核：确认主办、补充协办与理由；若认为主办有误须说明理由；
3. 规则与模型结论不一致时保留模型结论但标记 needs_human_judgment（分歧交人工），
   并在 note 中同时展示两个结论——这就是"可解释 + 交叉复核"。
"""
from __future__ import annotations

import json
import re

from app.core.config import get_settings
from app.schemas.models import Classification, Routing, WorkOrder
from app.services import dispatch, retrieval
from app.services.llm import chat_json


def _norm_name(name: str) -> str:
    """单位名归一：去括号补充说明（如「城管局（住建市政）」→「城管局」），用于模糊去重。"""
    return re.sub(r"[（(].*?[）)]", "", name or "").strip()


def _is_dup(name: str, seen_norms: list[str]) -> bool:
    """子串包含即视为同一单位（覆盖「属地社区（棠梅社区）」vs「社区」这类冗余）。"""
    n = _norm_name(name)
    if not n:
        return True
    return any(n in s or s in n for s in seen_norms)

SYSTEM = """你是芜湖市 12345 政务服务热线的"转派推荐"复核专员。
系统已由规则引擎按《安徽省12345热线诉求闭环办理工作规范》的「属地管理、分级负责」
原则给出主办单位建议（见"规则引擎判定"），你的任务是**复核**而非重新自由推荐：

1. 默认采纳规则引擎的主办单位（属地政府/开发区或专业直派单位）；
2. 只有当诉求事实明显表明主办单位错误时，才可提出不同主办单位，并必须在
   judgment_note 中写明分歧理由（此时系统会标记需人工裁断）；
3. 补充协办单位与业务指导单位（可参考职责规则与相似历史工单办理单位）；
4. 历史工单办理单位只是参考，须在 note 中注明"依据历史工单参考"，不得表述为现行正式权责；
5. 推荐 1~4 个单位，primary 为首要承办单位（一般应与规则引擎一致）；
6. 涉及紧急危险的，提示"同步启动应急响应，转人工处置"；
7. 职责交叉（多单位职责边界不清）/ 无法明确主管部门 / 与规则引擎分歧时，
   needs_human_judgment 填 true 并写明原因。

输出必须是 JSON 对象，字段：
{"departments": [{"name": str, "role": "建议承办单位|协办单位|业务指导单位|属地兜底", "reason": str}],
  "primary": str, "note": str,
  "needs_human_judgment": boolean, "judgment_note": str,
  "agrees_with_rule": boolean}"""


def run(
    work_order: WorkOrder,
    classification: Classification,
    raw_text: str,
    vision_signals: list[dict] | None = None,
    decision_signals: dict | None = None,
) -> Routing:
    settings = get_settings()
    rules_block = "承办单位职责规则：未录入"
    if settings.department_rules_path.exists():
        rules = json.loads(settings.department_rules_path.read_text(encoding="utf-8"))
        if rules.get("rules"):
            rules_block = "承办单位职责规则：\n" + json.dumps(rules["rules"], ensure_ascii=False)

    similar = retrieval.search_similar(f"{work_order.title} {work_order.event_description}", top_k=3)
    sim_lines = []
    for s in similar:
        if s.handling_departments:
            sim_lines.append(f"- 历史类别[{s.category}] 办理单位：{'、'.join(s.handling_departments)}")
    history_block = "历史工单办理单位参考：\n" + ("\n".join(sim_lines) if sim_lines else "暂无")

    # ---- 规则引擎锚点（支柱一）----
    decision = dispatch.decide(work_order, classification, raw_text, decision_signals=decision_signals)
    anchor_lines = [
        f"主办单位：{decision['primary']}（类型：{decision['primary_kind']}）",
        f"决策路径：{decision['path']}｜命中规则：{decision['matched_rule']}",
        f"规则置信度：{decision['confidence']}",
    ]
    if decision["co_units"]:
        anchor_lines.append(
            "建议协办/指导：" + "、".join(f"{u['name']}（{u['role']}）" for u in decision["co_units"])
        )
    if decision["return_risk"]:
        anchor_lines.append(f"退回风险：{decision['return_risk']}")
    anchor_lines.append("依据链：")
    for e in decision["evidence_chain"]:
        anchor_lines.append(f"  - [{e['type']}] {e['source']}：{e['detail']}")
    anchor_block = "规则引擎判定（请复核）：\n" + "\n".join(anchor_lines)

    vision_block = "现场照片证据：无"
    if vision_signals:
        vlines = ["现场照片证据（视觉模型结论，可作派单与急件判断参考）："]
        for i, v in enumerate(vision_signals, 1):
            if not v:
                continue
            vlines.append(f"- 照片{i}：隐患={v.get('hazard_type')}｜严重程度={v.get('severity')}｜摘要={v.get('summary')}")
        if len(vlines) > 1:
            vision_block = "\n".join(vlines)

    user = (
        anchor_block + "\n\n"
        + rules_block + "\n\n"
        + history_block + "\n\n"
        + vision_block + "\n\n"
        "标准化工单：\n" + work_order.model_dump_json(ensure_ascii=False) + "\n\n"
        "事项分类：\n" + classification.model_dump_json(ensure_ascii=False) + "\n\n"
        "群众诉求原文：\n" + raw_text + "\n\n"
        "请复核并输出承办单位推荐 JSON。"
    )
    data = chat_json(SYSTEM, user)

    # ---- 合并规则锚点与模型复核 ----
    rule_primary = decision["primary"]
    llm_primary = str(data.get("primary", "")).strip()
    agrees = bool(data.get("agrees_with_rule", True)) and (not llm_primary or llm_primary == rule_primary)
    primary = rule_primary if agrees else (llm_primary or rule_primary)

    departments: list[dict] = []
    seen: set[str] = set()
    seen_norms: list[str] = []
    for d in data.get("departments", []) or []:
        name = str(d.get("name", "")).strip()
        if not name or name in seen or _is_dup(name, seen_norms):
            continue
        seen.add(name)
        seen_norms.append(_norm_name(name))
        departments.append({
            "name": name,
            "role": str(d.get("role", "协办单位")).strip(),
            "reason": str(d.get("reason", "")).strip(),
        })
    # 规则锚点兜底：确保主办与规则协办在列（模型漏给时补齐；模糊去重避免与模型输出重复）
    if primary and not _is_dup(primary, seen_norms):
        departments.insert(0, {"name": primary, "role": "建议承办单位",
                               "reason": f"规则引擎按{decision['path']}判定（{decision['matched_rule']}）"})
        seen.add(primary)
        seen_norms.append(_norm_name(primary))
    for u in decision["co_units"]:
        if u["name"] in seen or _is_dup(u["name"], seen_norms):
            continue
        seen.add(u["name"])
        seen_norms.append(_norm_name(u["name"]))
        departments.append({"name": u["name"], "role": u["role"], "reason": u["reason"]})

    llm_judgment = bool(data.get("needs_human_judgment", False))
    # 职责交叉（协办 ≥2 家）属赛题明确要求提示人工判断的情形
    cross_duty = len(departments) >= 3
    needs_human = llm_judgment or not agrees or decision["path"] == "类别兜底" or cross_duty
    judgment_note = str(data.get("judgment_note", "")).strip()
    if not agrees and not judgment_note:
        judgment_note = f"规则引擎判定主办为「{rule_primary}」，模型复核建议「{llm_primary}」，两者分歧，请人工裁断。"
    elif cross_duty and not judgment_note:
        judgment_note = (f"职责交叉：本案涉及 {len(departments)} 个单位（{primary} 主办 + "
                         f"{len(departments) - 1} 家协办/指导），建议人工确认主办单位后再派件。")

    note_parts = [str(data.get("note", "")).strip()]
    note_parts.append(f"派单决策路径：{decision['path']}（规则锚点：{rule_primary}）")
    if not agrees:
        note_parts.append(f"⚠ 规则与模型结论不一致：规则={rule_primary}｜模型={llm_primary}")
    note = "；".join(p for p in note_parts if p)

    evidence = list(decision["evidence_chain"])
    if not agrees:
        evidence.append({"type": "模型复核异议", "source": "LLM 复核", "detail": judgment_note})

    return Routing(
        departments=[d for d in departments if d["name"]],
        primary=primary or None,
        note=note,
        needs_human_judgment=needs_human,
        judgment_note=judgment_note,
        dispatch_path=decision["path"],
        primary_kind=decision["primary_kind"],
        evidence_chain=evidence,
        return_risk=decision["return_risk"],
        rule_primary=rule_primary,
        rule_llm_agreement=agrees,
    )
