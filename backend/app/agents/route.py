"""Agent 节点：承办单位推荐（职责规则 + 历史工单办理单位）。"""
from __future__ import annotations

import json

from app.core.config import get_settings
from app.schemas.models import Classification, Routing, WorkOrder
from app.services import retrieval
from app.services.llm import chat_json

SYSTEM = """你是芜湖市 12345 政务服务热线的"转派推荐"专员。
根据事项分类与工单内容，推荐承办单位（主办）与协办单位。

要求：
1. 优先依据正式职责规则（若提供）；规则缺失时，参考相似历史工单的办理单位并结合常识推断；
2. 历史工单办理单位只是参考，必须在 note 中注明"依据历史工单参考"，不得表述为现行正式权责；
3. 推荐 1~3 个单位；primary 为首要承办单位；
4. 属地兜底：当无法明确主管部门时，推荐"属地街道办事处/乡镇人民政府"兜底协调；
5. 涉及紧急危险的，提示"同步启动应急响应，转人工处置"；
6. 遇到以下任一情形，needs_human_judgment 填 true，并在 judgment_note 写明具体原因：
   职责交叉（多单位职责边界不清）/ 无法明确主管部门 / 历史办理单位与常识推断冲突。
   此时仍须给出 primary 建议，但明确标注需人工裁断。

输出必须是 JSON 对象，字段：
{"departments": [{"name": str, "role": "建议承办单位|协办单位|属地兜底", "reason": str}],
  "primary": str, "note": str,
  "needs_human_judgment": boolean, "judgment_note": str}"""


def run(work_order: WorkOrder, classification: Classification, raw_text: str) -> Routing:
    settings = get_settings()
    rules_block = "承办单位职责规则：未录入"
    if settings.department_rules_path.exists():
        rules = json.loads(settings.department_rules_path.read_text(encoding="utf-8"))
        if rules.get("rules"):
            rules_block = "承办单位职责规则：\n" + json.dumps(rules["rules"], ensure_ascii=False)

    similar = retrieval.search_similar(f"{work_order.title} {work_order.event_description}", top_k=3)
    dept_history: dict[str, int] = {}
    sim_lines = []
    for s in similar:
        if s.handling_departments:
            for d in s.handling_departments:
                dept_history[d] = dept_history.get(d, 0) + 1
            sim_lines.append(f"- 历史类别[{s.category}] 办理单位：{'、'.join(s.handling_departments)}")
    history_block = "历史工单办理单位参考：\n" + ("\n".join(sim_lines) if sim_lines else "暂无")

    user = (
        rules_block + "\n\n"
        + history_block + "\n\n"
        "标准化工单：\n" + work_order.model_dump_json(ensure_ascii=False) + "\n\n"
        "事项分类：\n" + classification.model_dump_json(ensure_ascii=False) + "\n\n"
        "群众诉求原文：\n" + raw_text + "\n\n"
        "请输出承办单位推荐 JSON。"
    )
    data = chat_json(SYSTEM, user)
    departments = []
    for d in data.get("departments", []) or []:
        departments.append(
            {
                "name": str(d.get("name", "")).strip(),
                "role": str(d.get("role", "建议承办单位")).strip(),
                "reason": str(d.get("reason", "")).strip(),
            }
        )
    departments = [d for d in departments if d["name"]]
    return Routing(
        departments=departments,
        primary=str(data.get("primary", departments[0]["name"] if departments else "")).strip() or None,
        note=str(data.get("note", "")).strip(),
        needs_human_judgment=bool(data.get("needs_human_judgment", False)),
        judgment_note=str(data.get("judgment_note", "")).strip(),
    )
