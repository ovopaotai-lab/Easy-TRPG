# -*- coding: utf-8 -*-
"""Authentication endpoints."""
from __future__ import annotations

import time
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from backend.core.auth import (
    SESSIONS,
    _USERS_AUTH_LOCK,
    ensure_user_workspace,
    get_current_user,
    hash_password,
    load_users,
    perform_login,
    save_sessions,
    save_users,
    verify_password,
)
from backend.core.security import get_client_ip, parse_device_info

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/api/auth/login")
def api_login(req: LoginRequest, request: Request, response: Response):
    return perform_login(req.username, req.password, request, response)


@router.post("/api/auth/logout")
def api_logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        with _USERS_AUTH_LOCK:
            SESSIONS.pop(token, None)
            save_sessions()
    response.delete_cookie("session_token", path="/")
    return {"status": "ok"}


@router.post("/api/auth/password")
def api_change_password(req: ChangePasswordRequest, username: str = Depends(get_current_user)):
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少 6 位")
    with _USERS_AUTH_LOCK:
        users = load_users()
        if username not in users:
            raise HTTPException(status_code=400, detail="默认免登录模式未注册密码，请先登录/创建管理员账号")
        u = users[username]
        if not verify_password(req.old_password, u.get("password_hash", ""), u.get("salt", "")):
            raise HTTPException(status_code=400, detail="原密码错误")
        nh, ns = hash_password(req.new_password)
        u["password_hash"] = nh
        u["salt"] = ns
        save_users(users)
    return {"status": "ok"}


@router.get("/api/auth/me")
def api_me(request: Request, username: str = Depends(get_current_user)):
    users = load_users()
    u = users.get(username, {})
    return {
        "username": username,
        "role": u.get("role", "player" if username == "player" else "user"),
        "ip": get_client_ip(request),
        "device": parse_device_info(request.headers.get("user-agent", "")),
        "has_registered_accounts": bool(users),
        "login_history": (u.get("login_history") or [])[:30],
    }


@router.post("/api/auth/register")
def api_register(req: LoginRequest):
    with _USERS_AUTH_LOCK:
        users = load_users()
        if users:
            raise HTTPException(status_code=403, detail="注册已关闭")
        uname = req.username.strip()
        if not uname or len(req.password) < 6:
            raise HTTPException(status_code=400, detail="用户名必填，密码至少 6 位")
        pwd_hash, salt = hash_password(req.password)
        users[uname] = {
            "username": uname,
            "password_hash": pwd_hash,
            "salt": salt,
            "role": "admin",
            "created_at": time.time(),
            "login_history": [],
        }
        save_users(users)
    ensure_user_workspace(uname)
    return {"status": "ok", "username": uname}
