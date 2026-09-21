# -*- coding: utf-8 -*-
"""工单流转状态机（借鉴 Jira/Plane 的状态与流转设计，贴合 12345 办理流程）。

设计要点：
1. 状态机与既有「链路状态」（cases.status）解耦：status 描述智能体链路进度，
   flow_state 描述工单在业务流程中的位置，两套状态通过映射表保持兼容，既有接口零回归；
2. 每次迁移都有**守卫**（合法迁移表 + 角色要求），非法迁移返回原因，不静默放行；
3. 全部迁移写入 case_flow_log，与白盒轨迹互补，形成可追责的流转记录；
4. 自动迁移（受理→已分类）只由系统触发；涉及派单、签收、审核、归档的迁移一律需人工。

状态流转图（→ 主线，⇢ 旁路）：
  received → triaged → dispatched → accepted → processing → replied → reviewed → closed
                 ↑                      ↓                                ↓
                 └────── returned ⇠─────┴────────────────────────────────┘
  processing/replied ⇢ suspended（承诺办理）⇢ processing
"""
from __future__ import annotations

STATES: dict[str, str] = {
    "received": "已受理",
    "triaged": "已分类（待审核派单）",
    "dispatched": "已派单",
    "accepted": "部门已签收",
    "processing": "办理中",
    "replied": "已回执",
    "reviewed": "审核通过",
    "closed": "已归档",
    "returned": "已退回（待重派）",
    "suspended": "承诺办理（挂起）",
}

# 角色：agent 坐席 / dispatcher 派单员 / reviewer 审核员 / dept 部门用户 / admin 管理员 / supervisor 监督员（只读）
ROLES = ("agent", "dispatcher", "reviewer", "dept", "admin", "supervisor")

# (from, to) -> (允许角色, 动作名, 说明)
TRANSITIONS: dict[tuple[str, str], tuple[tuple[str, ...], str, str]] = {
    ("received", "triaged"): (("system",), "自动分类完成", "智能体链路完成，工单进入待审核派单"),
    ("triaged", "dispatched"): (("dispatcher", "admin"), "确认派单", "工作人员确认承办单位后派单"),
    ("triaged", "returned"): (("reviewer", "dispatcher", "admin"), "退回重派", "分类或承办单位不可用，退回重派"),
    ("dispatched", "accepted"): (("dept", "admin"), "部门签收", "承办单位签收工单"),
    ("dispatched", "returned"): (("dept", "admin"), "部门退回", "职责不符或需协同，退回热线重派"),
    ("accepted", "processing"): (("dept", "admin"), "开始办理", "承办单位开始办理"),
    ("accepted", "suspended"): (("dept", "admin"), "承诺办理", "复杂事项申请承诺办理（不超过 9 个月）"),
    ("processing", "replied"): (("dept", "admin"), "提交回执", "承办单位提交办理结果与答复"),
    ("processing", "suspended"): (("dept", "admin"), "承诺办理", "办理中申请承诺办理"),
    ("suspended", "processing"): (("dept", "admin"), "恢复办理", "承诺办理事项恢复办理"),
    ("replied", "reviewed"): (("reviewer", "admin"), "审核通过", "答复与办理结果审核通过"),
    ("replied", "returned"): (("reviewer", "admin"), "答复退回", "答复不规范（如合规审查高风险），退回重办"),
    ("reviewed", "closed"): (("reviewer", "admin"), "归档", "工单归档，进入历史库供相似检索"),
    ("returned", "triaged"): (("dispatcher", "admin"), "重新分派", "重新确认承办单位"),
    # 兼容：链路完成即派单场景（人工确认链路结果后直接进入派单）
    ("triaged", "accepted"): (("dispatcher", "admin"), "直接派单（属地直办）", "属地直办等场景跳过单独派单步骤"),
}

MAIN_FLOW = ["received", "triaged", "dispatched", "accepted", "processing", "replied", "reviewed", "closed"]

# 链路状态（cases.status）→ 流转状态（自动推进用）
STATUS_TO_FLOW = {
    "processing": "received",
    "awaiting_review": "triaged",
    "needs_clarification": "received",
    "failed": "received",
}


def is_state(state: str) -> bool:
    return state in STATES


def label(state: str) -> str:
    return STATES.get(state, state)


def next_actions(state: str, role: str = "dispatcher") -> list[dict]:
    """当前状态下该角色可执行的迁移（用于前端按钮与看板）。"""
    out = []
    for (frm, to), (roles, action, desc) in TRANSITIONS.items():
        if frm != state:
            continue
        allowed = role in roles or role == "admin" or "admin" in roles
        out.append({
            "to": to,
            "to_label": label(to),
            "action": action,
            "description": desc,
            "allowed": allowed,
            "required_roles": list(roles),
        })
    return out


def can_transition(from_state: str, to_state: str, role: str = "admin") -> tuple[bool, str]:
    """校验迁移合法性；返回 (是否允许, 原因)。"""
    if not is_state(from_state) or not is_state(to_state):
        return False, f"未知状态：{from_state} → {to_state}"
    if from_state == to_state:
        return False, "目标状态与当前状态相同"
    rule = TRANSITIONS.get((from_state, to_state))
    if rule is None:
        legal = [to for (frm, to) in TRANSITIONS if frm == from_state]
        return False, f"不允许从「{label(from_state)}」迁移到「{label(to_state)}」；合法目标：{[label(s) for s in legal]}"
    roles, action, _ = rule
    if role not in roles and role != "admin":
        return False, f"角色 {role} 无权执行「{action}」（需要：{'/'.join(roles)}）"
    return True, ""


def auto_flow_state(chain_status: str) -> str | None:
    """由链路状态推导应自动推进到的流转状态（仅系统可触发）。"""
    return STATUS_TO_FLOW.get(chain_status)
