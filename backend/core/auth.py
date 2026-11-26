# -*- coding: utf-8 -*-
"""Authentication, session management (HttpOnly cookies + Bearer), and workspace provisioning."""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
import threading
import time
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request, Response

from backend.config import SESSIONS_FILE, USERS_FILE, atomic_write_json, safe_float
from backend.core.security import (
    get_client_ip,
    get_user_chats_dir,
    get_user_dir,
    get_user_gallery_dir,
    get_user_presets_dir,
    get_user_projects_dir,
    parse_device_info,
)

logger = logging.getLogger("easy_trpg.auth")

_USERS_AUTH_LOCK = threading.RLock()
FAILED_LOGIN_TRACKER: Dict[str, List[float]] = {}


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000
    ).hex()
    return pwd_hash, salt


def verify_password(password: str, pwd_hash: str, salt: str) -> bool:
    calc_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(calc_hash, pwd_hash)


def load_users() -> Dict[str, Any]:
    with _USERS_AUTH_LOCK:
        if not USERS_FILE.exists():
            return {}
        try:
            return json.loads(USERS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed reading users.json: %s", exc)
            return {}


def save_users(users: Dict[str, Any]) -> None:
    with _USERS_AUTH_LOCK:
        atomic_write_json(USERS_FILE, users, ensure_ascii=False, indent=2)


def load_sessions() -> Dict[str, Any]:
    with _USERS_AUTH_LOCK:
        if not SESSIONS_FILE.exists():
            return {}
        try:
            data = json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed reading sessions.json: %s", exc)
            return {}


SESSIONS: Dict[str, Any] = load_sessions()


def save_sessions() -> None:
    with _USERS_AUTH_LOCK:
        atomic_write_json(SESSIONS_FILE, SESSIONS, ensure_ascii=False, indent=2)


def ensure_user_workspace(username: str) -> None:
    """Create user directories and initialize SQLite DB + v1.x auto-migration."""
    get_user_dir(username)
    get_user_projects_dir(username)
    get_user_chats_dir(username)
    get_user_gallery_dir(username)
    get_user_presets_dir(username)
    from backend.storage.migrator import ensure_user_migrated
    ensure_user_migrated(username)


def get_current_user(request: Request) -> str:
    """Resolve current user via HttpOnly cookie or Bearer token, defaulting to passwordless 'player'."""
    token = request.cookies.get("session_token")
    if not token:
        auth_hdr = request.headers.get("authorization") or ""
        if auth_hdr.startswith("Bearer "):
            token = auth_hdr[7:].strip()
    if token:
        with _USERS_AUTH_LOCK:
            sess = SESSIONS.get(token)
            if isinstance(sess, dict):
                now = time.time()
                if safe_float(sess.get("expires_at"), 0.0) > now:
                    uname = str(sess.get("username") or "").strip()
                    if uname:
                        sess["last_seen_at"] = now
                        ensure_user_workspace(uname)
                        return uname
                else:
                    SESSIONS.pop(token, None)
    ensure_user_workspace("player")
    return "player"


def perform_login(username: str, password: str, request: Request, response: Response) -> Dict[str, Any]:
    now = time.time()
    client_ip = get_client_ip(request)
    recent_fails = [t for t in FAILED_LOGIN_TRACKER.get(client_ip, []) if now - t < 60]
    if len(recent_fails) >= 8:
        raise HTTPException(status_code=429, detail="尝试过多，1 分钟后再试")

    users = load_users()
    uname = username.strip()
    if not uname or not password:
        raise HTTPException(status_code=400, detail="请输入账号和密码")

    with _USERS_AUTH_LOCK:
        if not users:
            if len(password) < 6:
                raise HTTPException(status_code=400, detail="密码至少 6 位")
            pwd_hash, salt = hash_password(password)
            users[uname] = {
                "username": uname,
                "password_hash": pwd_hash,
                "salt": salt,
                "role": "admin",
                "created_at": now,
                "login_history": [],
            }
            save_users(users)
        elif uname not in users:
            recent_fails.append(now)
            FAILED_LOGIN_TRACKER[client_ip] = recent_fails
            raise HTTPException(status_code=400, detail="账号或密码错误")

        user_data = users[uname]
        if not verify_password(password, user_data.get("password_hash", ""), user_data.get("salt", "")):
            recent_fails.append(now)
            FAILED_LOGIN_TRACKER[client_ip] = recent_fails
            raise HTTPException(status_code=400, detail="账号或密码错误")

        ensure_user_workspace(uname)
        FAILED_LOGIN_TRACKER.pop(client_ip, None)

        token = secrets.token_urlsafe(32)
        ua = request.headers.get("user-agent", "")
        device_name = parse_device_info(ua)
        login_entry = {
            "id": secrets.token_hex(4),
            "time": now,
            "ip": client_ip,
            "device": device_name,
            "user_agent": ua[:180],
        }
        history = list(user_data.get("login_history") or [])
        history.insert(0, login_entry)
        user_data["login_history"] = history[:50]
        user_data["last_login_at"] = now
        user_data["last_login_ip"] = client_ip
        user_data["last_login_device"] = device_name
        save_users(users)

        SESSIONS[token] = {
            "username": uname,
            "created_at": now,
            "last_seen_at": now,
            "ip": client_ip,
            "device": device_name,
            "user_agent": ua[:180],
            "expires_at": now + 30 * 24 * 3600,
        }
        save_sessions()

    response.set_cookie(
        key="session_token",
        value=token,
        max_age=30 * 24 * 3600,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return {
        "status": "ok",
        "user": {
            "username": uname,
            "role": user_data.get("role", "user"),
            "device": device_name,
            "current_device": device_name,
            "ip": client_ip,
            "current_ip": client_ip,
            "login_history": user_data.get("login_history", [])[:30],
        },
    }
