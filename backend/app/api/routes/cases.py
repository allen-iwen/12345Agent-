"""案件 API：创建、查询、人工审核、补充信息。"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException

from app.repositories import attachments as attachments_repo
from app.repositories import cases as repository
from app.repositories import flow as flow_repo
from app.services import workflow_state
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
from app.services import deadline as deadline_svc
from app.services import early_warning, governance, qc, reply_audit, tracing
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
    # 流转状态（工单在业务流程中的位置）
    try:
        fstate = flow_repo.get_state(case.case_id) or "received"
        case.flow_state = fstate
        case.flow_label = workflow_state.label(fstate)
        if enrich:
            case.flow_history = flow_repo.history(case.case_id)
    except Exception:  # noqa: BLE001
        logger.warning("flow state load failed", exc_info=True)
    case.urgency = assessment.get("urgency") or None
    # 证据附件（图片/音频）及其视觉结论
    try:
        case.attachments = [
            {
                "id": a["id"],
                "kind": a["kind"],
                "filename": a["filename"],
                "mime": a["mime"],
                "size": a["size"],
                "vision": a.get("vision"),
                "created_at": a["created_at"],
            }
            for a in attachments_repo.list_by_case(case.case_id)
        ]
    except Exception:  # noqa: BLE001
        logger.warning("attachments load failed", exc_info=True)
    # 支柱五：办理时限倒计时（纯规则，成本极低，列表与详情都返回，供队列临期/超期角标）
    try:
        case.deadline = deadline_svc.compute(
            case.created_at,
            (case.urgency or {}).get("level", "一般"),
            closed=case.status == "completed",
        )
    except Exception:  # noqa: BLE001
        logger.warning("deadline compute failed", exc_info=True)
    if enrich:
        try:
            case.agent_seconds = round(tracing.sum_case_ms(case.case_id) / 1000, 1) or None
            case.early_warning = early_warning.detect(case)
            # 支柱四：答复合规审查（读时计算）
            if case.reply_draft is not None:
                case.reply_audit = reply_audit.audit(
                    case.reply_draft.reply_text,
                    case.reply_draft.policy_refs or [],
                    {
                        "raw_text": case.raw_text,
                        "event_description": (case.work_order.event_description if case.work_order else ""),
                        "urgency": case.urgency,
                        "manual_action": (case.understanding.manual_action if case.understanding else None),
                    },
                )
            # 支柱三：诉求治理建议包（含时限督办）
            case.governance = governance.assess(case, deadline=case.deadline) or None
        except Exception:  # noqa: BLE001
            logger.warning("enrich failed", exc_info=True)
    return case


@router.post("", response_model=Case)
def create_case(req: CreateCaseRequest) -> Case:
    """录入诉求文本，运行全链路，停在人工审核点。"""
    case_id = uuid.uuid4().hex
    thread_id = case_id
    repository.create_case(case_id, thread_id, req.text, req.source_channel, "processing")
    # 关联证据附件并取出视觉结论（图片证据注入链路）
    vision_signals: list[dict] = []
    try:
        if req.attachment_ids:
            linked = attachments_repo.link_to_case(req.attachment_ids, case_id)
            logger.info("case %s linked %d attachments", case_id, linked)
        for a in attachments_repo.list_by_case(case_id):
            v = a.get("vision")
            if a["kind"] == "image" and v and v.get("available"):
                vision_signals.append(v)
    except Exception:  # noqa: BLE001 - 附件问题不阻断建单
        logger.warning("attachment link failed", exc_info=True)
    try:
        values = run_chain(case_id, req.text, req.source_channel, vision_signals=vision_signals or None)
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
    # 流转状态自动推进（仅系统触发）：链路完成 → 已分类（待审核派单）
    try:
        auto = workflow_state.auto_flow_state(status)
        if auto and (flow_repo.get_state(case_id) or "received") != auto:
            flow_repo.set_state(case_id, auto, actor="system", role="system",
                                action="智能体链路完成", note=f"链路状态：{status}")
    except Exception:  # noqa: BLE001 - 流转推进失败不影响建单
        logger.warning("flow auto advance failed", exc_info=True)
    row = repository.get_case(case_id)
    assert row is not None
    return _to_case(row)


@router.get("", response_model=list[Case])
def list_cases(limit: int = 50) -> list[Case]:
    return [_to_case(r, enrich=False) for r in repository.list_cases(limit=limit)]


@router.get("/deadlines")
def list_deadlines(window_hours: int = 24) -> list[dict]:
    """支柱五：临期与超期清单（供看板与督办使用）。

    含：已超期案件，以及剩余时长 ≤ window_hours 的案件（早期预警）。
    """
    out: list[dict] = []
    for row in repository.list_cases(limit=300):
        assessment = row.get("assessment") or {}
        level = (assessment.get("urgency") or {}).get("level", "一般")
        dl = deadline_svc.compute(row["created_at"], level, closed=row["status"] == "completed")
        if dl["state"] == "已办结":
            continue
        if dl["state"] == "超期" or dl["remaining_hours"] <= window_hours:
            wo = row.get("work_order") or {}
            out.append({
                "case_id": row["case_id"],
                "title": wo.get("title") or (row.get("raw_text") or "")[:30],
                "status": row["status"],
                "level": dl["level"],
                "state": dl["state"],
                "due_at": dl["due_at"],
                "remaining_hours": dl["remaining_hours"],
                "mode": dl["mode"],
                "supervision": dl.get("supervision", ""),
            })
    out.sort(key=lambda x: (x["state"] != "超期", x["remaining_hours"]))
    return out[:50]


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
        # 流转推进：人工放行 → 审核通过（记入流转日志，含操作者与角色）
        try:
            flow_repo.set_state(case_id, "reviewed", actor=action.note or "工作人员",
                                role="reviewer", action="最终放行", note=action.note or "工作人员最终审核通过")
        except Exception:  # noqa: BLE001
            logger.warning("flow advance on final review failed", exc_info=True)
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

