"""Agent 节点：事项分类（12 大类 + 历史工单参考）。"""
from __future__ import annotations

from app.schemas.models import Classification, WorkOrder
from app.services import retrieval
from app.services.llm import chat_json

SYSTEM = """你是芜湖市 12345 政务服务热线的"事项分类"专员。
把标准化工单归入给定的 12 个一级事项类别之一，或判定无法确定。

分类原则：
1. 先对照分类目录中每类的"定义/典型情形/辨析"判断归属，再参考相似历史工单；
   类别边界争议时以"辨析"为准（如：培训机构退费归科教文体而非市场监管；
   宅基地审批归农林水土而非城乡建设；消防设施归公共安全而非城市管理）；
2. 以工单诉求的核心事项为准，而不是地点或主体类型；
3. 参考相似历史工单的类别，但历史仅作参考，与工单事实冲突时以事实为准；
3. confidence：0~1，表示你对 category_code 的把握；
4. 若文本信息完全不足以归类（如只说"噪声大"但无来源与地点），category_code 填 null，
   并在 reason 中说明缺什么信息、为何无法归类；
5. candidates 给出最可能的 1~3 个类别及各自得分（和为 1 左右）；
6. 遇到以下任一情形，needs_human_judgment 填 true，并在 judgment_note 写明具体原因：
   职责交叉（同时涉及多类且难分主次）/ 多类并存（一次反映多个不相关事项）/
   信息不足（无法可靠归类但有部分线索）。此时仍须给出最可能的 category_code 供参考。

输出必须是 JSON 对象，字段：
{"category_code": str|null, "category_name": str|null, "confidence": number,
  "reason": str, "candidates": [{"code": str, "name": str, "score": number, "reason": str}],
  "needs_human_judgment": boolean, "judgment_note": str}"""


def _vision_block(vision_signals: list[dict] | None) -> str:
    """图片证据块：视觉模型对现场照片的结构化结论。"""
    if not vision_signals:
        return "现场照片证据：无"
    lines = ["现场照片证据（视觉模型结论，仅作参考；与文本冲突时综合判断）："]
    for i, v in enumerate(vision_signals, 1):
        if not v:
            continue
        lines.append(
            f"- 照片{i}：隐患={v.get('hazard_type')}｜严重程度={v.get('severity')}｜"
            f"摘要={v.get('summary')}｜置信度={v.get('confidence')}"
        )
        if v.get("elements"):
            lines.append("  可见要素：" + "、".join(f"{k}={val}" for k, val in v["elements"].items()))
    return "\n".join(lines) if len(lines) > 1 else "现场照片证据：无"


def run(
    work_order: WorkOrder,
    raw_text: str,
    exclude_source_ids: tuple[str, ...] = (),
    vision_signals: list[dict] | None = None,
) -> Classification:
    catalog = retrieval.catalog_brief()
    similar = retrieval.search_similar(
        f"{work_order.title} {work_order.event_description}", top_k=3, exclude_source_ids=exclude_source_ids
    )
    if similar:
        sim_lines = []
        for s in similar:
            sim_lines.append(
                f"- 历史工单[{s.category}] {s.title}\n  内容摘要：{s.request_content}\n  历史办理单位：{'、'.join(s.handling_departments) or '无'}"
            )
        similar_block = "相似历史工单（来自官方样例）：\n" + "\n".join(sim_lines)
    else:
        similar_block = "相似历史工单：暂无"

    user = (
        "事项分类目录：\n" + catalog + "\n\n"
        "标准化工单：\n" + work_order.model_dump_json(ensure_ascii=False) + "\n\n"
        "群众诉求原文：\n" + raw_text + "\n\n"
        + similar_block + "\n\n"
        + _vision_block(vision_signals) + "\n\n"
        "请输出分类 JSON。"
    )
    data = chat_json(SYSTEM, user)
    code = data.get("category_code")
    code = str(code).strip() if code else None
    valid_codes = {c["code"] for c in retrieval.load_category_catalog()}
    if code is not None and code not in valid_codes:
        code = None
    # 确定性兜底：职责交叉/拿不准时 LLM 偶尔违反提示返回 null，
    # 但仍给出了 candidates——按首位候选回填，保证"仅供参考的类别"始终存在
    if code is None:
        for c in data.get("candidates", []) or []:
            cand = str(c.get("code", "")).strip()
            if cand in valid_codes:
                code = cand
                break
    name = data.get("category_name")
    if code:
        name = next((c["name"] for c in retrieval.load_category_catalog() if c["code"] == code), name)
    candidates = []
    for c in data.get("candidates", []) or []:
        candidates.append(
            {
                "code": str(c.get("code", "")),
                "name": str(c.get("name", "")),
                "score": float(c.get("score", 0.0) or 0.0),
                "reason": str(c.get("reason", "")),
            }
        )
    return Classification(
        category_code=code,
        category_name=str(name) if name else None,
        confidence=max(0.0, min(1.0, float(data.get("confidence", 0.0) or 0.0))),
        reason=str(data.get("reason", "")).strip(),
        candidates=candidates,
        needs_human_judgment=bool(data.get("needs_human_judgment", False)),
        judgment_note=str(data.get("judgment_note", "")).strip(),
    )
