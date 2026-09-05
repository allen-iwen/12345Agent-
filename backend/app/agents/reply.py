"""Agent 节点：回复建议（官方风格 + 回访话术 + 政策依据引用）。"""
from __future__ import annotations

import json

from app.core.config import get_settings
from app.schemas.models import Classification, ReplyDraft, Routing, WorkOrder
from app.services import retrieval
from app.services.llm import chat_json

SYSTEM = """你是芜湖市 12345 政务服务热线的"答复草拟"专员。
基于标准化工单、事项分类与承办单位推荐，草拟给群众的办理答复与回访话术。

风格要求（对齐官方答复）：
1. 开头"尊敬的市民：您好！您反映的"……"问题已收悉，现将有关情况答复如下："；
2. 正文分条说明：受理情况、核查/办理方向、依据或措施、后续安排；
3. 语气正式、耐心、规范；不承诺具体时限与结果，不代替承办部门作出处理决定；
4. 结尾"感谢您对政府工作的关心与支持！"；
5. 涉及紧急/危险事项的，答复中须包含安全提示（如远离现场、拨打 119/110/120 等）；
6. 全程使用"您"，不出现群众真实姓名（用"您"代替）；
7. 政策依据：仅可引用"政策依据库"中列出的文件，且仅在明显适用时引用（写明文件名）；
   政策库未覆盖的情形一律不引用，严禁虚构文件名；引用的文件名放入 policy_refs 数组。

回访话术（followup_script）：办理完毕后热线回访群众时使用的简短通话脚本，
以接线员口吻写 3-5 句：确认身份→说明办理情况→询问满意度→致谢。

输出必须是 JSON 对象，字段：
{"reply_text": str, "tone": str, "disclaimer": str,
 "followup_script": str, "policy_refs": [str]}"""


def _policy_block(work_order: WorkOrder) -> str:
    """政策依据块 = 精选法规库 + RAG 检索命中的上传政策片段。"""
    settings = get_settings()
    path = settings.data_dir / "policies" / "policy_references.json"
    lines: list[str] = []
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        lines.append("政策依据库（仅可引用以下文件）：")
        for p in data.get("policies", []):
            lines.append(f"- {p['name']}\n  适用：{p['usage']}")
    # RAG：检索与本案最相关的政策片段（含上传入库的芜湖政策文件）
    try:
        from app.services import policy_rag

        hits = policy_rag.search(f"{work_order.title} {work_order.event_description}", top_k=3)
    except Exception:  # noqa: BLE001 - RAG 不可用不影响答复
        hits = []
    if hits:
        lines.append("")
        lines.append("知识库检索命中的政策片段（引用时写 source_name 的文件名）：")
        for h in hits:
            lines.append(f"- 来源：{h['source_name']}（{h['publisher']}，相关度 {h['score']}）\n  内容：{h['content'][:200]}")
    if not lines:
        return "政策依据库：暂无（不引用任何政策）"
    return "\n".join(lines)


def run(
    work_order: WorkOrder,
    classification: Classification,
    routing: Routing,
    raw_text: str,
) -> ReplyDraft:
    similar = retrieval.search_similar(f"{work_order.title} {work_order.event_description}", top_k=2)
    style_block = "官方答复风格参考（节选）：\n"
    for s in similar:
        if s.reply_content:
            style_block += f"- {s.reply_content}\n"
    if similar and not any(s.reply_content for s in similar):
        style_block += "- 暂无\n"

    user = (
        style_block + "\n"
        + _policy_block(work_order) + "\n\n"
        "标准化工单：\n" + work_order.model_dump_json(ensure_ascii=False) + "\n\n"
        "事项分类：\n" + classification.model_dump_json(ensure_ascii=False) + "\n\n"
        "承办单位推荐：\n" + routing.model_dump_json(ensure_ascii=False) + "\n\n"
        "群众诉求原文：\n" + raw_text + "\n\n"
        "请草拟答复 JSON。"
    )
    data = chat_json(SYSTEM, user)
    policy_refs = [str(p).strip() for p in data.get("policy_refs", []) or [] if str(p).strip()]
    return ReplyDraft(
        reply_text=str(data.get("reply_text", "")).strip(),
        tone=str(data.get("tone", "正式、耐心、规范")).strip() or "正式、耐心、规范",
        disclaimer=str(data.get("disclaimer", "本回复由智能体草拟，发送前须经工作人员审核确认。")).strip(),
        followup_script=str(data.get("followup_script", "")).strip(),
        policy_refs=policy_refs,
    )
