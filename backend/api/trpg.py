# -*- coding: utf-8 -*-
"""v2.0 TRPG superpowers: Swipes, DAG Branch Tree, Cryptographic Dice, Deterministic State, Author's Note, Group Chat, Personas, Presets, Chapters, FTS5 Search, Tokenizer."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.api.chats import stream_trpg_generation
from backend.core.auth import get_current_user
from backend.core.prompt_builder import import_sillytavern_preset
from backend.core.security import sanitize_id
from backend.core.tokenizer import tokenize_text_async
from backend.engines.llama_manager import ACTIVE_LLAMA_MODEL, ACTIVE_LLAMA_PORT
from backend.storage.db import get_user_db
from backend.trpg.dice import roll_dice_expression
from backend.trpg.state_engine import apply_ai_output_to_state, empty_game_state

router = APIRouter()


@router.post("/api/chats/{chat_id}/messages/{message_id}/swipe")
async def generate_new_swipe(
    chat_id: str,
    message_id: str,
    payload: Dict[str, Any] = {},
    username: str = Depends(get_current_user),
):
    return await stream_trpg_generation(
        username=username,
        chat_id=sanitize_id(chat_id),
        user_text="",
        model_id=str(payload.get("model") or ""),
        raw_images=[],
        turn_cards=[],
        mode="swipe",
        target_node_id=sanitize_id(message_id),
    )


@router.put("/api/chats/{chat_id}/messages/{message_id}/active_swipe")
def switch_active_swipe(
    chat_id: str,
    message_id: str,
    payload: Dict[str, Any],
    username: str = Depends(get_current_user),
):
    db = get_user_db(username)
    cid = sanitize_id(chat_id)
    mid = sanitize_id(message_id)
    idx = int(payload.get("swipe_idx") or 0)
    chat = db.get_chat_full(cid)
    if not chat:
        raise HTTPException(status_code=404, detail="对话不存在")
    msgs = chat.get("messages") or []
    cur_i = next((i for i, m in enumerate(msgs) if m["id"] == mid), -1)
    if cur_i == -1:
        raise HTTPException(status_code=404, detail="消息不存在")
    target_node = msgs[cur_i]
    swipes = target_node.get("swipes") or []
    if idx < 0 or idx >= len(swipes):
        raise HTTPException(status_code=400, detail="候选索引越界")
    prev_state = msgs[cur_i - 1].get("state_snapshot") if cur_i > 0 else {}
    recomputed_state, _ = apply_ai_output_to_state(prev_state, swipes[idx]["content"])
    db.set_active_swipe(cid, mid, idx, recomputed_state)
    return {"status": "ok", "chat": db.get_chat_full(cid)}


@router.get("/api/chats/{chat_id}/tree")
def get_chat_tree(chat_id: str, username: str = Depends(get_current_user)):
    db = get_user_db(username)
    return db.get_branch_tree(sanitize_id(chat_id))


@router.post("/api/chats/{chat_id}/checkout")
def checkout_chat_node(chat_id: str, payload: Dict[str, Any], username: str = Depends(get_current_user)):
    db = get_user_db(username)
    cid = sanitize_id(chat_id)
    nid = sanitize_id(payload.get("node_id") or "")
    if not db.checkout_node(cid, nid):
        raise HTTPException(status_code=404, detail="分支节点不存在")
    return {"status": "ok", "chat": db.get_chat_full(cid), "tree": db.get_branch_tree(cid)}


@router.post("/api/chats/{chat_id}/roll")
def roll_dice_for_chat(chat_id: str, payload: Dict[str, Any], username: str = Depends(get_current_user)):
    db = get_user_db(username)
    cid = sanitize_id(chat_id)
    chat = db.get_chat_full(cid)
    if not chat:
        raise HTTPException(status_code=404, detail="对话不存在")
    proj = db.get_project(chat["project_id"]) or {}
    ruleset = str(payload.get("ruleset") or proj.get("ruleset") or "d20")
    expr = str(payload.get("expression") or ("1d100" if ruleset == "d100" else ("2d6" if ruleset == "2d6" else "1d20")))
    try:
        res = roll_dice_expression(
            expr,
            ruleset=ruleset,
            difficulty=payload.get("difficulty"),
            skill_name=str(payload.get("skill") or ""),
            hidden=bool(payload.get("hidden", False)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok", "roll": res}


@router.get("/api/chats/{chat_id}/state")
def get_chat_state(chat_id: str, username: str = Depends(get_current_user)):
    db = get_user_db(username)
    chat = db.get_chat_full(sanitize_id(chat_id))
    if not chat:
        raise HTTPException(status_code=404, detail="对话不存在")
    proj = db.get_project(chat["project_id"]) or {}
    return {"status": "ok", "state": empty_game_state(chat.get("active_state") or proj.get("initial_state"))}


@router.put("/api/chats/{chat_id}/state")
def update_chat_state(chat_id: str, payload: Dict[str, Any], username: str = Depends(get_current_user)):
    db = get_user_db(username)
    cid = sanitize_id(chat_id)
    chat = db.get_chat_full(cid)
    if not chat:
        raise HTTPException(status_code=404, detail="对话不存在")
    new_state = empty_game_state(payload.get("state") or payload)
    active_nid = chat.get("active_node_id")
    if active_nid:
        last_m = chat["messages"][-1] if chat.get("messages") else None
        if last_m:
            db.update_active_swipe_content(cid, active_nid, last_m["content"], last_m.get("prompt_content"), state_snapshot=new_state)
    return {"status": "ok", "state": new_state}


@router.get("/api/chats/{chat_id}/author_note")
def get_author_note(chat_id: str, username: str = Depends(get_current_user)):
    db = get_user_db(username)
    chat = db.get_chat_full(sanitize_id(chat_id))
    if not chat:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"status": "ok", "author_note": chat.get("author_note") or {}}


@router.put("/api/chats/{chat_id}/author_note")
def update_author_note(chat_id: str, payload: Dict[str, Any], username: str = Depends(get_current_user)):
    db = get_user_db(username)
    cid = sanitize_id(chat_id)
    an = {
        "content": str(payload.get("content") or ""),
        "depth": max(0, min(10, int(payload.get("depth") if payload.get("depth") is not None else 1))),
        "role": str(payload.get("role") or "system"),
        "enabled": bool(payload.get("enabled", True)),
    }
    updated = db.update_chat_meta(cid, {"author_note": an})
    if not updated:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"status": "ok", "author_note": updated["author_note"]}


@router.put("/api/chats/{chat_id}/group_config")
def update_group_config(chat_id: str, payload: Dict[str, Any], username: str = Depends(get_current_user)):
    db = get_user_db(username)
    cid = sanitize_id(chat_id)
    gc = {
        "enabled": bool(payload.get("enabled", False)),
        "mode": str(payload.get("mode") or "round_robin"),
        "members": list(payload.get("members") or []),
    }
    updated = db.update_chat_meta(cid, {"group_config": gc})
    if not updated:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"status": "ok", "group_config": updated["group_config"]}


@router.post("/api/chats/{chat_id}/group_turn")
async def trigger_group_turn(chat_id: str, payload: Dict[str, Any] = {}, username: str = Depends(get_current_user)):
    db = get_user_db(username)
    cid = sanitize_id(chat_id)
    chat = db.get_chat_full(cid)
    if not chat:
        raise HTTPException(status_code=404, detail="对话不存在")
    gc = chat.get("group_config") or {}
    members = [m for m in (gc.get("members") or []) if m.get("enabled", True)]
    cards = {c["id"]: c for c in db.list_cards()}
    speaker_cid = str(payload.get("card_id") or "").strip()
    if not speaker_cid and members:
        # Pick next speaker round-robin relative to last assistant speaker
        last_sp = next((m.get("speaker_card_id") for m in reversed(chat.get("messages") or []) if m.get("role") == "assistant" and m.get("speaker_card_id")), "")
        m_ids = [m["card_id"] for m in members if m.get("card_id") in cards]
        if m_ids:
            speaker_cid = m_ids[(m_ids.index(last_sp) + 1) % len(m_ids)] if last_sp in m_ids else m_ids[0]
    speaker_card = cards.get(speaker_cid)
    if not speaker_card:
        raise HTTPException(status_code=400, detail="请先在群聊面板添加并启用至少一张角色卡")
    return await stream_trpg_generation(
        username=username,
        chat_id=cid,
        user_text=str(payload.get("prompt") or ""),
        model_id=str(payload.get("model") or ""),
        raw_images=[],
        turn_cards=[speaker_card],
        mode="group_turn",
        speaker_card=speaker_card,
    )


@router.get("/api/chats/{chat_id}/chapters")
def list_chat_chapters(chat_id: str, username: str = Depends(get_current_user)):
    db = get_user_db(username)
    return {"status": "ok", "chapters": db.list_chapters(sanitize_id(chat_id))}


@router.post("/api/chats/{chat_id}/chapters")
def add_chat_chapter(chat_id: str, payload: Dict[str, Any], username: str = Depends(get_current_user)):
    db = get_user_db(username)
    cid = sanitize_id(chat_id)
    chaps = db.list_chapters(cid)
    ch = db.save_chapter(
        cid,
        len(chaps) + 1,
        str(payload.get("title") or f"第 {len(chaps)+1} 章"),
        str(payload.get("summary") or "").strip(),
        str(payload.get("up_to_node_id") or ""),
    )
    return {"status": "ok", "chapter": ch}


# -------------------- Personas --------------------
@router.get("/api/personas")
def list_personas(username: str = Depends(get_current_user)):
    return {"status": "ok", "personas": get_user_db(username).list_personas()}


@router.post("/api/personas")
@router.put("/api/personas/{persona_id}")
def save_persona(payload: Dict[str, Any], persona_id: Optional[str] = None, username: str = Depends(get_current_user)):
    data = dict(payload)
    if persona_id:
        data["id"] = sanitize_id(persona_id)
    saved = get_user_db(username).save_persona(data)
    return {"status": "ok", "persona": saved}


@router.delete("/api/personas/{persona_id}")
def delete_persona(persona_id: str, username: str = Depends(get_current_user)):
    get_user_db(username).delete_persona(sanitize_id(persona_id))
    return {"status": "ok"}


# -------------------- Prompt Presets & ST Import --------------------
@router.get("/api/presets")
def list_presets(username: str = Depends(get_current_user)):
    return {"status": "ok", "presets": get_user_db(username).list_presets()}


@router.post("/api/presets")
@router.put("/api/presets/{preset_id}")
def save_preset(payload: Dict[str, Any], preset_id: Optional[str] = None, username: str = Depends(get_current_user)):
    data = dict(payload)
    if preset_id:
        data["id"] = sanitize_id(preset_id)
    saved = get_user_db(username).save_preset(data)
    return {"status": "ok", "preset": saved}


@router.delete("/api/presets/{preset_id}")
def delete_preset(preset_id: str, username: str = Depends(get_current_user)):
    get_user_db(username).delete_preset(sanitize_id(preset_id))
    return {"status": "ok"}


@router.post("/api/presets/import_st")
def import_st_preset_route(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    raw = payload.get("preset") if isinstance(payload.get("preset"), dict) else payload
    if isinstance(raw, str):
        raw = json.loads(raw)
    converted = import_sillytavern_preset(raw, str(payload.get("name") or ""))
    saved = get_user_db(username).save_preset(converted)
    return {"status": "ok", "preset": saved}


# -------------------- FTS5 Search & Tokenize --------------------
@router.get("/api/search")
def search_workspace(q: str = "", scope: str = "all", chat_id: Optional[str] = None, limit: int = 20, username: str = Depends(get_current_user)):
    db = get_user_db(username)
    res = db.search_fts(q, scope=scope, chat_id=sanitize_id(chat_id) if chat_id else None, limit=min(50, max(1, limit)))
    return {"status": "ok", **res}


@router.post("/api/tokenize")
async def tokenize_endpoint(payload: Dict[str, Any]):
    txt = str(payload.get("text") or "")
    llama_url = f"http://127.0.0.1:{ACTIVE_LLAMA_PORT}" if ACTIVE_LLAMA_MODEL else None
    cnt = await tokenize_text_async(txt, llama_base_url=llama_url)
    return {"status": "ok", "tokens": cnt, "exact": bool(llama_url)}
