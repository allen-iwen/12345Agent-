# -*- coding: utf-8 -*-
"""认证与审计 API：登录/登出/当前用户、用户管理、审计查询。"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.repositories import auth as repo
from app.services import auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str = Field(min_length=6, description="初始密码（至少 6 位）")
    display_name: str = ""
    role: str = Field(default="agent", description="agent|dispatcher|reviewer|dept|admin|supervisor")
    org: str = ""


@router.post("/login")
def login(req: LoginRequest, request: Request) -> dict:
    ip = request.client.host if request.client else ""
    return auth.login(req.username, req.password, ip)


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)) -> dict:
    token = (authorization or "").replace("Bearer ", "").strip()
    auth.logout(token)
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(auth.require_role())) -> dict:
    return {
        "actor": user.get("actor"),
        "role": user.get("role"),
        "role_label": auth.ROLE_LABELS.get(user.get("role", ""), user.get("role")),
        "username": user.get("username"),
        "rbac_enabled": auth.rbac_enabled(),
    }


@router.get("/status")
def status() -> dict:
    """鉴权与审计概况（前端可据此提示「演示态：未启用鉴权」）。"""
    return auth.status()


@router.get("/users")
def list_users(user: dict = Depends(auth.require_role("admin", "supervisor"))) -> list[dict]:
    return [dict(u, role_label=auth.ROLE_LABELS.get(u["role"], u["role"])) for u in repo.list_users()]


@router.post("/users")
def create_user(req: CreateUserRequest, request: Request,
                user: dict = Depends(auth.require_role("admin"))) -> dict:
    if req.role not in auth.ROLE_LABELS:
        raise HTTPException(status_code=400, detail=f"未知角色：{req.role}")
    if repo.get_user(req.username):
        raise HTTPException(status_code=409, detail="用户名已存在")
    uid = repo.create_user(req.username, req.display_name or req.username,
                           auth.hash_password(req.password), req.role, req.org)
    auth.audit(user.get("actor", ""), user.get("role", ""), "创建账号", "user", req.username,
               {"role": req.role, "org": req.org}, request)
    return {"ok": True, "id": uid, "username": req.username}


@router.get("/audit")
def list_audit(limit: int = 100, target_id: str | None = None, actor: str | None = None,
               user: dict = Depends(auth.require_role("admin", "supervisor", "reviewer"))) -> dict:
    """操作审计查询（管理员/监督员/审核员可见）。"""
    return {
        "total": repo.count_audit(),
        "records": repo.list_audit(limit=min(limit, 500), target_id=target_id, actor=actor),
    }
