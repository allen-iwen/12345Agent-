# -*- coding: utf-8 -*-
"""轻量 RBAC 服务：登录、会话、角色守卫、审计写入与初始化。

渐进启用（`RBAC_ENABLED`）：
- 关闭（默认，开发态）：所有守卫放行，行为与未接入时完全一致，既有测试零回归；
- 开启（演示/部署态）：关键写操作要求 Bearer 会话，并按角色矩阵校验。

首启动引导：无任何用户时创建 `admin`，随机密码**只打印到控制台**（不写入代码与仓库）；
若 `SESSION_SECRET` 未配置，启动时生成临时密钥并告警。

审计：所有关键写操作（建单、审核、放行、流转、附件删除、用户管理）都落 audit_log，
记录操作者、角色、动作、对象与依据——这是「谁审的、谁改的」可追责的基础。
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Callable

from fastapi import Header, HTTPException, Request

from app.core.config import get_settings
from app.repositories import auth as repo

logger = logging.getLogger(__name__)

# 角色说明（与前端一致）
ROLE_LABELS = {
    "agent": "坐席",
    "dispatcher": "派单员",
    "reviewer": "审核员",
    "dept": "部门用户",
    "admin": "管理员",
    "supervisor": "监督员",
}

_PBKDF2_ROUNDS = 120_000


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds))
        return secrets.compare_digest(dk.hex(), digest)
    except Exception:  # noqa: BLE001 - 格式异常一律视为校验失败
        return False


def rbac_enabled() -> bool:
    return bool(get_settings().rbac_enabled)


def bootstrap() -> dict | None:
    """首次启动引导：创建管理员并返回一次性凭据（调用方负责打印，不落库明文）。"""
    if repo.count_users() > 0:
        return None
    s = get_settings()
    if not s.session_secret:
        logger.warning("SESSION_SECRET 未配置，已生成临时密钥（重启后既有会话失效）")
    pwd = s.auth_bootstrap_password or secrets.token_urlsafe(12)
    repo.create_user("admin", "系统管理员", hash_password(pwd), "admin", org="热线管理中心")
    # 便于演示：同时建一个坐席账号
    seat_pwd = "seat01-pass"
    repo.create_user("seat01", "坐席一号", hash_password(seat_pwd), "agent", org="受理岗")
    repo.add_audit("system", "system", "初始化账号", "user", "admin", {"note": "首次启动自动创建"})
    return {"username": "admin", "password": pwd if not s.auth_bootstrap_password else "(由 AUTH_BOOTSTRAP_PASSWORD 指定)",
            "also_created": f"seat01 / {seat_pwd}（坐席）"}


def login(username: str, password: str, ip: str = "") -> dict:
    user = repo.get_user(username)
    if user is None or not verify_password(password, user["password_hash"]):
        repo.add_audit(username or "unknown", "", "登录失败", "user", username, {"reason": "账号或密码错误"}, ip)
        raise HTTPException(status_code=401, detail="账号或密码错误")
    sess = repo.create_session(int(user["id"]), get_settings().session_ttl_hours)
    repo.add_audit(user["display_name"] or username, user["role"], "登录成功", "user", username, None, ip)
    return {
        "token": sess["token"],
        "expires_at": sess["expires_at"],
        "user": {
            "username": user["username"],
            "display_name": user["display_name"],
            "role": user["role"],
            "role_label": ROLE_LABELS.get(user["role"], user["role"]),
            "org": user.get("org") or "",
        },
    }


def logout(token: str, actor: str = "") -> None:
    repo.delete_session(token)
    repo.add_audit(actor or "unknown", "", "退出登录", "session", token[:8])


def current_user(authorization: str | None) -> dict:
    """从 Authorization 头解析当前用户；RBAC 关闭时返回开发态身份。"""
    s = get_settings()
    if not s.rbac_enabled:
        return {"actor": "开发模式（未启用鉴权）", "role": "admin", "username": "dev", "enforced": False}
    token = (authorization or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    sess = repo.resolve_session(token)
    if sess is None:
        raise HTTPException(status_code=401, detail="未登录或会话已过期，请重新登录")
    sess["enforced"] = True
    return sess


def require_role(*roles: str) -> Callable:
    """FastAPI 依赖：要求指定角色之一（管理员始终放行）。RBAC 关闭时不校验。"""

    def dep(authorization: str | None = Header(default=None)) -> dict:
        user = current_user(authorization)
        if not user.get("enforced"):
            return user
        if roles and user["role"] not in roles and user["role"] != "admin":
            need = "/".join(ROLE_LABELS.get(r, r) for r in roles)
            raise HTTPException(status_code=403, detail=f"当前角色「{ROLE_LABELS.get(user['role'], user['role'])}」无权执行该操作（需要：{need}）")
        return user

    return dep


def audit(actor: str, role: str, action: str, target_type: str = "", target_id: str = "",
          detail: dict | str | None = None, request: Request | None = None) -> None:
    """写审计日志（失败不阻断业务）。"""
    try:
        ip = ""
        if request is not None and request.client is not None:
            ip = request.client.host or ""
        repo.add_audit(actor, role, action, target_type, target_id, detail, ip)
    except Exception:  # noqa: BLE001 - 审计失败不应影响主流程
        logger.warning("审计写入失败：action=%s target=%s", action, target_id, exc_info=True)


def status() -> dict:
    return {
        "enabled": rbac_enabled(),
        "users": repo.count_users(),
        "audit_records": repo.count_audit(),
        "roles": ROLE_LABELS,
        "session_ttl_hours": get_settings().session_ttl_hours,
    }
