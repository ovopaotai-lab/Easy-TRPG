# -*- coding: utf-8 -*-
"""Character cards CRUD, V2/V3 PNG/JSON import, and AI character generation."""
from __future__ import annotations

import base64
import json
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from backend.core.auth import get_current_user
from backend.core.card_codec import extract_png_card_json, parse_character_card_payload
from backend.core.media import auto_save_to_gallery
from backend.core.security import sanitize_id
from backend.providers.router import resolve_model_endpoint, stream_via_endpoint
from backend.storage.db import get_user_db

router = APIRouter()


@router.get("/api/character_cards")
def list_character_cards(username: str = Depends(get_current_user)):
    return get_user_db(username).list_cards()


@router.post("/api/character_cards")
def create_character_card(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    db = get_user_db(username)
    saved = db.save_card(payload)
    return {"status": "ok", "card": saved}


@router.put("/api/character_cards/{card_id}")
def update_character_card(card_id: str, payload: Dict[str, Any], username: str = Depends(get_current_user)):
    db = get_user_db(username)
    data = dict(payload)
    data["id"] = sanitize_id(card_id)
    saved = db.save_card(data)
    return {"status": "ok", "card": saved}


@router.delete("/api/character_cards/{card_id}")
def delete_character_card(card_id: str, username: str = Depends(get_current_user)):
    get_user_db(username).delete_card(sanitize_id(card_id))
    return {"status": "ok"}


@router.post("/api/character_cards/import")
async def import_character_card(file: UploadFile = File(...), username: str = Depends(get_current_user)):
    raw = await file.read()
    fname = (file.filename or "").lower()
    avatar_url = ""
    if fname.endswith(".png") or raw.startswith(b"\x89PNG"):
        parsed_raw = extract_png_card_json(raw)
        b64 = "data:image/png;base64," + base64.b64encode(raw).decode("utf-8")
        gid = auto_save_to_gallery(username, b64, file.filename, "角色立绘")
        avatar_url = f"/api/gallery/image/{gid}" if gid else ""
    else:
        parsed_raw = json.loads(raw.decode("utf-8-sig"))
    card = parse_character_card_payload(parsed_raw, avatar_url)
    card["id"] = f"card_{uuid.uuid4().hex[:8]}"
    saved = get_user_db(username).save_card(card)
    return {"status": "ok", "card": saved}


@router.post("/api/character_cards/ai_generate")
async def ai_generate_character_card(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    db = get_user_db(username)
    s = db.get_settings()
    model_id = str(payload.get("model") or s.get("model") or "")
    idea = str(payload.get("idea") or payload.get("prompt") or "").strip()
    if not idea:
        raise HTTPException(status_code=400, detail="请输入角色构思")
    ep = resolve_model_endpoint(model_id, s)
    if not ep["is_local"] and not ep.get("base_url"):
        raise HTTPException(status_code=400, detail="请先配置模型")
    if ep["is_local"]:
        from backend.engines.supervisor import discover_local_models, ensure_local_engine_ready
        await discover_local_models(s)
        ep = resolve_model_endpoint(model_id, s)
        err = await ensure_local_engine_ready(model_id, ep["local_meta"], settings=s)
        if err:
            raise HTTPException(status_code=503, detail=err.get("message", "本地引擎未就绪"))

    sys_p = (
        "请根据用户的角色灵感生成一个 JSON 格式角色卡，只输出纯 JSON 对象，字段包括："
        'name, description, personality, scenario, first_mes, tags (数组)。'
    )
    pieces = []
    async for d in stream_via_endpoint(
        endpoint=ep,
        messages=[{"role": "system", "content": sys_p}, {"role": "user", "content": idea}],
        params={"temperature": 0.75, "max_tokens": 1800},
        proxy_url=(s.get("proxy") if s.get("use_proxy") else None),
        think_enabled=False,
    ):
        if d.text:
            pieces.append(d.text)
    raw = "".join(pieces).strip()
    m = raw[raw.find("{"): raw.rfind("}") + 1] if "{" in raw and "}" in raw else raw
    try:
        card_data = json.loads(m)
    except Exception:
        card_data = {"name": "新角色", "description": raw, "personality": "", "scenario": "", "first_mes": ""}
    saved = db.save_card(card_data)
    return {"status": "ok", "card": saved}
