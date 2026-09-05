"""Pydantic 模型：工单链路各阶段产物与 API 请求/响应。"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# ---------- 诉求理解 ----------


class Understanding(BaseModel):
    summary: str = Field(description="一句话概括诉求")
    elements: dict = Field(default_factory=dict, description="要素：人员/地点/时间/事件等")
    urgent: bool = Field(default=False, description="是否紧急")
    repeat_request: bool = Field(default=False, description="是否重复诉求")
    needs_clarification: bool = Field(default=False, description="是否需要补充信息")
    missing_fields: list[str] = Field(default_factory=list, description="缺失的关键字段")
    manual_action: Optional[str] = Field(
        default=None,
        description="紧急/危险情形下对工作人员的人工处置提示；Agent 不替代报警或应急指挥",
    )


# ---------- 标准化工单 ----------


class WorkOrder(BaseModel):
    title: str
    region: str = Field(default="待确认")
    requester: str = Field(default="匿名市民")
    contact: str = Field(default="待确认")
    location: str = Field(default="待确认")
    occurrence_time: str = Field(default="待确认")
    event_description: str = Field(description="标准化的诉求事实描述")
    handling_request: str = Field(description="群众希望得到的处理结果")


# ---------- 事项分类 ----------


class CategoryCandidate(BaseModel):
    code: str
    name: str
    score: float = 0.0
    reason: str = ""


class Classification(BaseModel):
    category_code: Optional[str] = Field(default=None, description="12 大类之一的 code，无法确定时为 null")
    category_name: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""
    candidates: list[CategoryCandidate] = Field(default_factory=list)
    needs_human_judgment: bool = Field(
        default=False,
        description="职责交叉/多类并存/信息不足时为 true，提示工作人员人工判断",
    )
    judgment_note: str = Field(default="", description="需要人工判断的具体原因")


# ---------- 承办单位推荐 ----------


class DepartmentRecommendation(BaseModel):
    name: str
    role: str = Field(default="建议承办单位", description="建议承办单位 / 协办单位 / 属地兜底")
    reason: str = ""


class Routing(BaseModel):
    departments: list[DepartmentRecommendation] = Field(default_factory=list)
    primary: Optional[str] = Field(default=None, description="首要承办单位名称")
    note: str = Field(default="", description="依据说明（历史工单参考 / 职责规则）")
    needs_human_judgment: bool = Field(
        default=False,
        description="职责交叉/无法明确主管部门时为 true，提示工作人员人工判断",
    )
    judgment_note: str = Field(default="", description="需要人工判断的具体原因")


# ---------- 回复建议 ----------


class ReplyDraft(BaseModel):
    reply_text: str
    tone: str = Field(default="正式、耐心、规范")
    disclaimer: str = "本回复由智能体草拟，发送前须经工作人员审核确认。"
    followup_script: str = Field(
        default="",
        description="回访参考话术：办理完毕后热线回访群众时使用的简短通话脚本",
    )
    policy_refs: list[str] = Field(
        default_factory=list,
        description="回复依据引用的政策文件名（仅限提示词提供的公开政策，不得虚构）",
    )


# ---------- 案件 ----------


class CaseSectionReview(BaseModel):
    work_order: str = "pending"  # pending | approved | modified
    classification: str = "pending"
    routing: str = "pending"
    reply: str = "pending"


class Case(BaseModel):
    case_id: str
    raw_text: str
    source_channel: str = "直接来电（呼入）"
    status: Literal["processing", "awaiting_review", "needs_clarification", "completed", "failed"]
    understanding: Optional[Understanding] = None
    work_order: Optional[WorkOrder] = None
    classification: Optional[Classification] = None
    routing: Optional[Routing] = None
    reply_draft: Optional[ReplyDraft] = None
    review: CaseSectionReview = Field(default_factory=CaseSectionReview)
    review_note: str = ""
    clarification_context: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None
    qc_checks: list[dict] = Field(default_factory=list, description="工单质量检查结果（规则式，只读）")


# ---------- API ----------


class CreateCaseRequest(BaseModel):
    text: str = Field(min_length=4, description="群众诉求原文（来电转写或文本录入）")
    source_channel: str = "直接来电（呼入）"


class ReviewAction(BaseModel):
    section: Literal["work_order", "classification", "routing", "reply", "final"]
    action: Literal["approve", "modify"]
    payload: Optional[dict] = Field(
        default=None,
        description="action=modify 时提交的修正内容（对应 section 的完整 JSON）",
    )
    note: str = ""


class ClarifyRequest(BaseModel):
    answers: str = Field(min_length=2, description="工作人员补充的信息（追加到诉求上下文）")
