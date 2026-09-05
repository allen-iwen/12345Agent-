"""Agent 节点：标准化工单生成。"""
from __future__ import annotations

from app.schemas.models import Understanding, WorkOrder
from app.services.llm import chat_json

SYSTEM = """你是芜湖市 12345 政务服务热线的"工单生成"专员。
基于群众诉求原文与已理解的结构化要素，生成一张规范、可直接流转的标准化工单。

要求：
1. title：格式为"关于+地点/主体+事项+的问题"，不超过 40 字，不出现群众姓名（用"某市民"）。
2. event_description：客观、中立、去口语化，按"时间-地点-事件-现状"组织，保留关键事实，不添加推断。
3. handling_request：群众明确提出的诉求/期望处理结果；文本未提及时写"请求相关部门核查处理并答复"。
4. 信息缺失的字段一律填"待确认"，禁止编造。
5. region 从以下取值：市本级、镜湖区、弋江区、鸠江区、繁昌区、湾沚区、南陵县、无为市；无法判断填"待确认"。

输出必须是 JSON 对象，字段：
{"title": str, "region": str, "requester": str, "contact": str, "location": str,
 "occurrence_time": str, "event_description": str, "handling_request": str}"""


def run(raw_text: str, understanding: Understanding) -> WorkOrder:
    user = (
        "群众诉求原文：\n"
        f"{raw_text}\n\n"
        "已理解的结构化要素：\n"
        f"{understanding.model_dump_json(ensure_ascii=False)}\n\n"
        "请生成标准化工单 JSON。"
    )
    data = chat_json(SYSTEM, user)
    return WorkOrder(
        title=str(data.get("title", "")).strip() or "工单标题待生成",
        region=str(data.get("region", "待确认")).strip() or "待确认",
        requester=str(data.get("requester", "匿名市民")).strip() or "匿名市民",
        contact=str(data.get("contact", "待确认")).strip() or "待确认",
        location=str(data.get("location", "待确认")).strip() or "待确认",
        occurrence_time=str(data.get("occurrence_time", "待确认")).strip() or "待确认",
        event_description=str(data.get("event_description", "")).strip(),
        handling_request=str(data.get("handling_request", "")).strip(),
    )
