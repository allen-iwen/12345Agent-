"""案件 API：创建、查询、人工审核、补充信息。"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException

from app.repositories import cases as repository
from app.schemas.models import (
    Case,
    CaseSectionReview,
    Classification,
    ClarifyRequest,
    CreateCaseRequest,
    ReplyDraft,
    ReviewAction,
    Routing,
    Understanding,
    WorkOrder,
)
from app.services import early_warning, governance, qc, tracing
from app.workflow.graph import get_graph, run_chain
from langgraph.types import Command

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cases", tags=["cases"])


def _to_case(row: dict, *, enrich: bool = True) -> Case:
    case = Case(
        case_id=row["case_id"],
        raw_text=row["raw_text"],
        source_channel=row["source_channel"],
        status=row["status"],
        understanding=Understanding(**row["understanding"]) if row.get("understanding") else None,
        work_order=WorkOrder(**row["work_order"]) if row.get("work_order") else None,
        classification=Classification(**row["classification"]) if row.get("classification") else None,
        routing=Routing(**row["routing"]) if row.get("routing") else None,
        reply_draft=ReplyDraft(**row["reply_draft"]) if row.get("reply_draft") else None,
        review=CaseSectionReview(**row["review"]) if row.get("review") else CaseSectionReview(),
        review_note=row.get("review_note", ""),
        clarification_context=row.get("clarification_context", []),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        completed_at=row.get("completed_at") or "",
        error=row.get("error"),
    )
    assessment = row.get("assessment") or {}
    try:
        case.qc_checks = qc.run_qc(case)
    except Exception:  # noqa: BLE001 - QC 失败不影响案件返回
        logger.warning("qc failed", exc_info=True)
    case.urgency = assessment.get("urgency") or None
    if enrich:
        try:
            case.agent_seconds = round(tracing.sum_case_ms(case.case_id) / 1000, 1) or None
            case.early_warning = early_warning.detect(case)
            # 支柱三：诉求治理建议包（重复诉求 / 并案预警 / 退回风险）
            case.governance = governance.assess(case) or None
        except Exception:  # noqa: BLE001
            logger.warning("enrich failed", exc_info=True)
    return case


@router.post("", response_model=Case)
def create_case(req: CreateCaseRequest) -> Case:
    """录入诉求文本，运行全链路，停在人工审核点。"""
    case_id = uuid.uuid4().hex
    thread_id = case_id
    repository.create_case(case_id, thread_id, req.text, req.source_channel, "processing")
    try:
        values = run_chain(case_id, req.text, req.source_channel)
    except Exception as exc:  # noqa: BLE001
        logger.exception("create_case workflow error")
        repository.save_state(case_id, status="failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"工作流执行失败：{exc}") from exc

    status = values.get("status", "failed")
    repository.save_state(
        case_id,
        status=status,
        thread_id=thread_id,
        understanding=values.get("understanding"),
        work_order=values.get("work_order"),
        classification=values.get("classification"),
        routing=values.get("routing"),
        reply_draft=values.get("reply_draft"),
        assessment={"urgency": values.get("urgency")} if values.get("urgency") else None,
        error=values.get("error"),
        completed=status == "completed",
    )
    row = repository.get_case(case_id)
    assert row is not None
    return _to_case(row)


@router.get("", response_model=list[Case])
def list_cases(limit: int = 50) -> list[Case]:
    return [_to_case(r, enrich=False) for r in repository.list_cases(limit=limit)]


@router.get("/{case_id}", response_model=Case)
def get_case(case_id: str) -> Case:
    row = repository.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="案件不存在")
    return _to_case(row)


@router.post("/{case_id}/review", response_model=Case)
def review_case(case_id: str, action: ReviewAction) -> Case:
    """人工审核：
    - section=work_order|classification|routing|reply + approve/modify：分节确认或修正；
    - section=final + approve：最终放行，resume 工作流完成案件。
    """
    row = repository.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="案件不存在")
    if row["status"] == "completed":
        raise HTTPException(status_code=409, detail="案件已完成，无需再审核")

    if action.section == "final":
        if action.action != "approve":
            raise HTTPException(status_code=400, detail="final 仅支持 approve")
        graph = get_graph()
        config = {"configurable": {"thread_id": row["thread_id"]}}
        graph.invoke(
            Command(resume={"note": action.note or "工作人员最终审核通过"}),
            config,
        )
        repository.set_completed(case_id)
    else:
        section = action.section
        # review 分节名与数据库列名映射（reply -> reply_draft）
        column = "reply_draft" if section == "reply" else section
        current = row.get(column)
        if current is None:
            raise HTTPException(status_code=409, detail=f"案件尚无 {section} 结果，无法审核")
        if action.action == "modify":
            if not action.payload:
                raise HTTPException(status_code=400, detail="modify 必须携带 payload（修正后的完整 JSON）")
            # 用对应模型校验修正内容
            model_cls = {
                "work_order": WorkOrder,
                "classification": Classification,
                "routing": Routing,
                "reply": ReplyDraft,
            }[section]
            try:
                fixed = model_cls(**action.payload)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=422, detail=f"修正内容不符合 {section} 结构：{exc}") from exc
            repository.update_section(case_id, column, fixed.model_dump(), review_key=section)
        else:
            repository.approve_section(case_id, section, action.note)

    row = repository.get_case(case_id)
    assert row is not None
    return _to_case(row)


@router.post("/{case_id}/clarify", response_model=Case)
def clarify_case(case_id: str, req: ClarifyRequest) -> Case:
    """补充信息后重跑链路（适用于 needs_clarification 的案件）。"""
    row = repository.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="案件不存在")
    if row["status"] not in ("awaiting_review", "needs_clarification", "failed"):
        raise HTTPException(status_code=409, detail="当前状态不支持补充信息重跑")

    new_thread_id = f"{case_id}::r{len(row['clarification_context']) + 1}"
    ctx = repository.append_clarification(case_id, req.answers, new_thread_id)
    values = run_chain(new_thread_id, row["raw_text"], row["source_channel"], ctx)
    repository.save_state(
        case_id,
        status=values.get("status", "failed"),
        thread_id=new_thread_id,
        understanding=values.get("understanding"),
        work_order=values.get("work_order"),
        classification=values.get("classification"),
        routing=values.get("routing"),
        reply_draft=values.get("reply_draft"),
        assessment={"urgency": values.get("urgency")} if values.get("urgency") else None,
        clarification_context=ctx,
        error=values.get("error"),
        completed=values.get("status") == "completed",
    )
    row = repository.get_case(case_id)
    assert row is not None
    return _to_case(row)

