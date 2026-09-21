# -*- coding: utf-8 -*-
"""第二模型交叉复核（可量化的可信性设计）。

为什么需要：单一模型的判断无法自证可靠。这里让**另一个模型独立判断同一问题**，
- 一致 → 记录「复核一致」，提升结论可信度；
- 分歧 → 标记「需人工判断」并同时展示两个结论，把不确定性显式交给人。

与 Jev 的关系（可选叠加）：Jev 提供校准概率与置信度门控；本模块提供**模型间交叉验证**。
两者都能独立工作，也可同时启用（三者一致 / 两两分歧都会被记录）。

复核模型可指向不同厂商或局域网服务（配置 LLM_REVIEW_*；局域网 vLLM 常不支持
response_format，故按 base_url 是否为本地自动放宽 json_mode）。
"""
from __future__ import annotations

import logging

from app.core.config import get_settings
from app.schemas.models import WorkOrder
from app.services import retrieval
from app.services.llm import chat_json

logger = logging.getLogger(__name__)

_SYSTEM = """你是芜湖市 12345 热线的"事项分类复核员"。请**独立**判断标准化工单属于哪一类，
不要迎合任何既有结论（复核的意义在于独立）。

分类原则：先对照分类目录中每类的「定义/典型情形/辨析」，以诉求的核心事项为准。

输出必须是 JSON 对象，字段：
{"category_code": str|null, "category_name": str|null, "confidence": number, "reason": str,
 "needs_human_judgment": boolean}"""


def _is_local(base_url: str) -> bool:
    return any(h in (base_url or "") for h in ("127.0.0.1", "localhost", "192.168.", "10.", "172."))


def configured() -> bool:
    s = get_settings()
    return bool(s.llm_review_enabled and s.llm_review_model)


def status() -> dict:
    s = get_settings()
    return {
        "enabled": configured(),
        "model": s.llm_review_model or "(未配置)",
        "base_url": s.llm_review_base_url or "(同主模型)",
        "note": "复核模型应尽量与主判模型不同（不同厂商或不同规模），否则交叉验证意义有限",
    }


def classify_second_opinion(work_order: WorkOrder, raw_text: str) -> dict:
    """第二模型独立分类；未配置或调用失败时返回 available=False（调用方不改变既有结论）。"""
    s = get_settings()
    if not configured():
        return {"available": False, "note": "未启用第二模型复核（LLM_REVIEW_ENABLED/LLM_REVIEW_MODEL）"}

    catalog = retrieval.catalog_brief()
    user = (
        "事项分类目录：\n" + catalog + "\n\n"
        "标准化工单：\n" + work_order.model_dump_json(ensure_ascii=False) + "\n\n"
        "群众诉求原文：\n" + raw_text + "\n\n"
        "请独立输出分类 JSON。"
    )
    base_url = s.llm_review_base_url or None
    try:
        data = chat_json(
            _SYSTEM, user,
            model=s.llm_review_model,
            temperature=0.0,
            max_tokens=4096,
            base_url=base_url,
            api_key=s.llm_review_api_key or None,
            json_mode=False if _is_local(base_url or "") else None,
        )
    except Exception as exc:  # noqa: BLE001 - 复核失败不得影响主链路
        logger.warning("第二模型复核失败：%s", exc)
        return {"available": False, "note": f"复核模型调用失败：{exc}"}

    valid = {c["code"] for c in retrieval.load_category_catalog()}
    code = str(data.get("category_code") or "").strip() or None
    if code and code not in valid:
        code = None
    name = data.get("category_name")
    if code:
        name = next((c["name"] for c in retrieval.load_category_catalog() if c["code"] == code), name)
    return {
        "available": True,
        "model": s.llm_review_model,
        "base_url": s.llm_review_base_url or "(主模型端点)",
        "category_code": code,
        "category_name": str(name) if name else None,
        "confidence": max(0.0, min(1.0, float(data.get("confidence", 0.0) or 0.0))),
        "reason": str(data.get("reason", "")).strip(),
        "needs_human_judgment": bool(data.get("needs_human_judgment", False)),
    }


def compare(primary_code: str | None, secondary: dict) -> dict:
    """比较主判与复核结论，产出可统计的分歧记录。"""
    if not secondary.get("available"):
        return {"agreement": None, "note": secondary.get("note", "复核不可用")}
    sec_code = secondary.get("category_code")
    agree = bool(primary_code) and bool(sec_code) and primary_code == sec_code
    return {
        "agreement": agree,
        "primary_choice": primary_code,
        "secondary_choice": sec_code,
        "secondary_name": secondary.get("category_name"),
        "secondary_confidence": secondary.get("confidence"),
        "secondary_model": secondary.get("model"),
        "note": "" if agree else f"主判={primary_code or '未定'}｜复核={sec_code or '未定'}，两者不一致，建议人工复核",
    }
