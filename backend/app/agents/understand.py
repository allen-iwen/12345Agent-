"""Agent 节点：诉求理解（要素提取、紧急/重复判定、缺失字段、人工处置提示）。"""
from __future__ import annotations

import json

from app.schemas.models import Understanding
from app.services.llm import chat_json

SYSTEM = """你是芜湖市 12345 政务服务热线的"诉求理解"专员。
你的任务：把群众的来电/来信文本理解成结构化要素，供后续生成标准化工单。

判定规则（严格遵守）：
1. urgent=true 的情形：涉及人身安全、火灾、燃气泄漏、溺水、突发疾病、群体性事件、扬言极端行为等；
   此时必须在 manual_action 中给出对工作人员的危险处置提示，并写明"Agent 不替代报警或应急指挥"。
2. repeat_request=true 的情形：文本中出现"再次反映/又一次/上周已反映/多次反映/之前反映过"等重复诉求信号。
3. needs_clarification：当缺少影响派单的关键信息（具体区县/详细地址/涉事单位/时间/凭证/原工单号等）时为 true，
   并在 missing_fields 中逐条列出缺什么（用面向群众的简短问句）。
4. 只依据文本本身判断，不要臆测文本中没有的信息；缺失就留空或标"待确认"。

输出必须是 JSON 对象，字段：
{"summary": 一句话概括, "elements": {"requester": 诉求人, "contact": 联系方式, "location": 地点,
 "time": 发生时间, "event": 事件概述}, "urgent": bool, "repeat_request": bool,
 "needs_clarification": bool, "missing_fields": [str], "manual_action": str|null}"""


def run(raw_text: str, clarification_context: list[str]) -> Understanding:
    parts = [f"群众诉求原文：\n{raw_text}"]
    if clarification_context:
        parts.append("工作人员补充的信息：\n" + "\n".join(clarification_context))
    user = "\n\n".join(parts) + "\n\n请输出 JSON。"
    data = chat_json(SYSTEM, user)
    return Understanding(
        summary=str(data.get("summary", "")),
        elements=data.get("elements", {}) or {},
        urgent=bool(data.get("urgent", False)),
        repeat_request=bool(data.get("repeat_request", False)),
        needs_clarification=bool(data.get("needs_clarification", False)),
        missing_fields=[str(x) for x in data.get("missing_fields", []) if str(x).strip()],
        manual_action=(str(data["manual_action"]).strip() or None) if data.get("manual_action") else None,
    )
