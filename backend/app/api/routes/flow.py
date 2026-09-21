# -*- coding: utf-8 -*-
"""工单流转 API：状态迁移、流转历史、流转看板。

- `POST /api/cases/{id}/transition` 迁移（守卫校验：合法迁移 + 角色）
- `GET  /api/cases/{id}/flow`       流转历史
- `GET  /api/flow/board`            看板（按流转状态分组 + 临期/超期 + 可执行动作）
- `GET  /api/flow/states`           状态与迁移定义（前端渲染用，避免硬编码）

说明：角色目前支持通过请求头 `X-Actor` / `X-Role` 传入（轻量 RBAC 在下一步接入统一鉴权后，
改为从会话解析；此处保留显式传参以便演示越权拒绝）。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.repositories import cases as cases_repo
from app.repositories import flow as flow_repo
from app.services import auth
from app.services import deadline as deadline_svc
from app.services import workflow_state as ws

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["flow"])


class TransitionRequest(BaseModel):
    to: str = Field(description="目标流转状态")
    note: str = ""
    expected_from: str | None = Field(default=None, description="乐观并发校验：期望的当前状态")
    actor: str = Field(default="demo-user", description="操作者（姓名或工号，可中文）")
    role: str = Field(default="dispatcher", description="操作者角色（轻量 RBAC；接入统一鉴权后由会话解析）")


@router.get("/flow/states")
def list_states() -> dict:
    return {
        "states": [{"key": k, "label": v} for k, v in ws.STATES.items()],
        "main_flow": ws.MAIN_FLOW,
        "roles": list(ws.ROLES),
        "transitions": [
            {"from": f, "to": t, "from_label": ws.label(f), "to_label": ws.label(t),
             "action": meta[1], "description": meta[2], "required_roles": list(meta[0])}
            for (f, t), meta in ws.TRANSITIONS.items()
        ],
    }


@router.get("/flow/board")
def board() -> dict:
    """按流转状态分组的看板（含临期/超期标记，供督办）。"""
    groups = []
    for state in ws.MAIN_FLOW + ["returned", "suspended"]:
        items = flow_repo.cases_by_state(state)
        for it in items:
            dl = deadline_svc.compute(it["created_at"], it.get("urgency_level", "一般"),
                                      closed=(it["status"] == "completed"))
            it["deadline_state"] = dl["state"]
            it["due_at"] = dl["due_at"]
            it["remaining_hours"] = dl["remaining_hours"]
        groups.append({
            "state": state,
            "label": ws.label(state),
            "count": len(items),
            "items": items,
        })
    return {"groups": groups, "counts": flow_repo.counts(),
            "total_cases": sum(flow_repo.counts().values()),
            "listed": sum(g["count"] for g in groups)}


@router.get("/cases/{case_id}/flow")
def case_flow(case_id: str, x_role: str = Header(default="dispatcher")) -> dict:
    row = cases_repo.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="案件不存在")
    state = flow_repo.get_state(case_id) or "received"
    return {
        "case_id": case_id,
        "flow_state": state,
        "flow_label": ws.label(state),
        "next_actions": ws.next_actions(state, x_role),
        "history": flow_repo.history(case_id),
    }


@router.post("/cases/{case_id}/transition")
def transition(case_id: str, req: TransitionRequest, request: Request,
               authorization: str | None = Header(default=None)) -> dict:
    row = cases_repo.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="案件不存在")
    # RBAC 启用时以会话身份为准（请求体中的角色不可信）；关闭时沿用请求体（开发/演示态）
    actor, role = req.actor, req.role
    try:
        user = auth.current_user(authorization)
        if user.get("enforced"):
            actor = user.get("actor") or actor
            role = user.get("role") or role
    except HTTPException:
        raise
    current = flow_repo.get_state(case_id) or "received"
    ok, reason = ws.can_transition(current, req.to, role)
    if not ok:
        auth.audit(actor, role, "流转被拒", "case", case_id, {"from": current, "to": req.to, "reason": reason}, request)
        raise HTTPException(status_code=409, detail=reason)

    meta = ws.TRANSITIONS[(current, req.to)]
    ok2, reason2 = flow_repo.set_state(
        case_id, req.to, actor=actor, role=role, action=meta[1], note=req.note,
        expected_from=req.expected_from,
    )
    if not ok2:
        raise HTTPException(status_code=409, detail=reason2)
    auth.audit(actor, role, f"流转：{meta[1]}", "case", case_id,
               {"from": ws.label(current), "to": ws.label(req.to), "note": req.note}, request)
    return {
        "ok": True,
        "case_id": case_id,
        "from": current,
        "from_label": ws.label(current),
        "to": req.to,
        "to_label": ws.label(req.to),
        "action": meta[1],
        "next_actions": ws.next_actions(req.to, role),
    }
