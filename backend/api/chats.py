# -*- coding: utf-8 -*-
"""Chats CRUD, branching, prompt_log, summarize, and unified SSE streaming generation."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.config import is_free_chat_project, is_simple_trpg_project, safe_float, safe_int
from backend.core.auth import get_current_user
from backend.core.media import auto_save_images_to_gallery_async, optimize_images_async
from backend.core.prompt_builder import assemble_kv_friendly_prompt, strip_legacy_start_game_hint
from backend.core.regex_engine import apply_regex_scripts
from backend.core.security import sanitize_id
from backend.core.tokenizer import estimate_tokens
from backend.core.variables import interpolate_variables
from backend.core.video_processor import ensure_video_processed_async, format_video_text_summary, load_video_prompt_bundle
from backend.core.worldbook import evaluate_cg_book
from backend.engines.supervisor import discover_local_models, ensure_local_engine_ready
from backend.providers.router import resolve_model_endpoint, sanitize_messages_for_model, stream_via_endpoint
from backend.storage.db import get_user_db
from backend.trpg.dice import format_dice_for_prompt
from backend.trpg.state_engine import apply_ai_output_to_state, empty_game_state
from backend.trpg.stream_parser import (
    build_prompt_frozen_content,
    detect_and_trim_stream_loop,
    extract_action_choices,
    extract_thinking_block,
    strip_distilled_artifact_tags,
)

logger = logging.getLogger("easy_trpg.chats")
router = APIRouter()

ACTIVE_BG_TASKS: Dict[str, asyncio.Task] = {}
ACTIVE_PARTIAL_TEXT: Dict[str, str] = {}
ACTIVE_STATUS_TEXT: Dict[str, str] = {}
ACTIVE_LAST_ERROR: Dict[str, Dict[str, Any]] = {}
GEN_SEQ: Dict[str, int] = {}


def _bump_gen_seq(chat_id: str) -> int:
    nxt = GEN_SEQ.get(chat_id, 0) + 1
    GEN_SEQ[chat_id] = nxt
    return nxt


class SendMessageRequest(BaseModel):
    chat_id: str
    content: Optional[str] = ""
    model: Optional[str] = None
    image_base64: Optional[str] = None
    images_base64: Optional[List[str]] = []
    video_ids: Optional[List[str]] = []
    video_frame_images: Optional[List[str]] = []
    character_cards: Optional[List[Dict[str, Any]]] = []
    regenerate: Optional[bool] = False
    target_user_msg_id: Optional[str] = None
    auto_summarize: Optional[bool] = None
    erotic_enabled: Optional[bool] = None
    violence_enabled: Optional[bool] = None
    cot_enabled: Optional[bool] = None
    dice_roll: Optional[Dict[str, Any]] = None
    parent_node_id: Optional[str] = None


def _resolve_generation_params(settings: Dict[str, Any], project_data: Dict[str, Any], model_id: str) -> Dict[str, Any]:
    comp = dict(project_data.get("completion_params") or {})
    use_global = bool(project_data.get("use_global_params", True))
    model_overrides = (settings.get("model_params") or {}).get(model_id)
    if isinstance(model_overrides, dict) and model_overrides:
        comp.update(model_overrides)
    elif use_global:
        for k in ("temperature", "repetition_penalty", "frequency_penalty", "presence_penalty", "top_p", "top_k", "min_p", "max_tokens", "thinking_budget"):
            if k in settings and settings[k] is not None:
                comp[k] = settings[k]
    return comp


@router.get("/api/chats")
def list_chats(project_id: Optional[str] = None, username: str = Depends(get_current_user)):
    db = get_user_db(username)
    return db.list_chats(project_id=sanitize_id(project_id) if project_id else None)


@router.post("/api/chats")
def create_chat(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    db = get_user_db(username)
    settings = db.get_settings()
    chat_id = uuid.uuid4().hex[:8]
    proj_id = sanitize_id(payload.get("project_id") or settings.get("active_project_id", "proj_fast_trpg"))
    proj_data = db.get_project(proj_id) or {}
    chat_model = str(payload.get("model") or settings.get("model") or "")

    default_inputs = {
        str(v.get("key") or v.get("name")): v.get("default", "")
        for v in (proj_data.get("prompt_variables") or [])
        if isinstance(v, dict) and (v.get("key") or v.get("name"))
    }
    raw_in = payload.get("inputs") or payload.get("variables") or {}
    user_inputs = {**default_inputs, **(raw_in if isinstance(raw_in, dict) else {})}
    init_state = empty_game_state(proj_data.get("initial_state"))

    init_messages: List[Dict[str, Any]] = []
    opening = str(payload.get("opening_content") or proj_data.get("opening_statement") or "").strip()
    if not opening and payload.get("include_opening"):
        ogs = proj_data.get("opening_greetings") or []
        if ogs and isinstance(ogs[0], dict):
            opening = str(ogs[0].get("content") or "").strip()
    if opening and (payload.get("include_opening") or payload.get("opening_content")):
        rendered = interpolate_variables(opening, proj_data.get("prompt_variables"), user_inputs)
        init_messages.append(
            {
                "id": "msg_open_" + uuid.uuid4().hex[:6],
                "role": "assistant",
                "content": rendered,
                "prompt_content": rendered,
                "state_snapshot": init_state,
                "is_opening": True,
                "suggested_questions": proj_data.get("suggested_questions") or [],
                "timestamp": time.time(),
            }
        )

    personas = db.list_personas()
    def_persona = next((p["id"] for p in personas if p.get("is_default")), "")
    group_cfg = {"enabled": False, "members": [], "mode": "round_robin"}
    if (proj_data.get("group_defaults") or {}).get("enabled") and proj_data.get("bundled_cards"):
        cards = db.list_cards()
        by_name = {c.get("name"): c["id"] for c in cards}
        members = []
        for bc in proj_data["bundled_cards"]:
            cid = by_name.get(bc.get("name"))
            if cid:
                members.append({"card_id": cid, "enabled": True, "talkativeness": 0.7})
        if members:
            group_cfg = {"enabled": True, "members": members, "mode": "round_robin"}

    chat_obj = db.create_chat(
        chat_id=chat_id,
        project_id=proj_id,
        title=str(payload.get("title") or f"对话 {time.strftime('%m-%d %H:%M')}"),
        model=chat_model,
        variables=user_inputs,
        initial_state=init_state,
        group_config=group_cfg,
        persona_id=str(payload.get("persona_id") or def_persona),
        init_messages=init_messages,
    )
    return chat_obj


@router.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, username: str = Depends(get_current_user)):
    db = get_user_db(username)
    cid = sanitize_id(chat_id)
    chat = db.get_chat_full(cid)
    if not chat:
        raise HTTPException(status_code=404, detail="对话不存在")
    settings = db.get_settings()
    proj = db.get_project(chat["project_id"]) or {}
    est_tok = sum(estimate_tokens(str(m.get("prompt_content") or m.get("content") or "")) for m in chat["messages"])
    max_k = safe_int((proj.get("completion_params") or {}).get("max_context_k"), safe_int(settings.get("max_context_k"), 96))
    chat["context_tokens_est"] = est_tok
    chat["max_context_tokens"] = max_k * 1024
    task = ACTIVE_BG_TASKS.get(cid)
    chat["is_generating"] = bool(task and not task.done())
    if chat["is_generating"]:
        if cid in ACTIVE_PARTIAL_TEXT:
            chat["partial_text"] = ACTIVE_PARTIAL_TEXT[cid]
        if cid in ACTIVE_STATUS_TEXT:
            chat["generating_status"] = ACTIVE_STATUS_TEXT[cid]
    elif cid in ACTIVE_LAST_ERROR:
        chat["last_error"] = ACTIVE_LAST_ERROR.pop(cid)
    return chat


@router.post("/api/chats/{chat_id}/stop")
async def stop_chat_generation(chat_id: str, username: str = Depends(get_current_user)):
    cid = sanitize_id(chat_id)
    _bump_gen_seq(cid)
    task = ACTIVE_BG_TASKS.pop(cid, None)
    partial = ACTIVE_PARTIAL_TEXT.pop(cid, "")
    ACTIVE_STATUS_TEXT.pop(cid, None)
    ACTIVE_LAST_ERROR.pop(cid, None)
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.wait({task}, timeout=1.5)
        except Exception:
            pass
    return {"status": "ok", "partial_saved": bool(partial)}


@router.put("/api/chats/{chat_id}")
def update_chat(chat_id: str, payload: Dict[str, Any], username: str = Depends(get_current_user)):
    db = get_user_db(username)
    cid = sanitize_id(chat_id)
    if payload.get("clear_history"):
        db.clear_chat_messages(cid)
        return db.get_chat_full(cid)
    updated = db.update_chat_meta(cid, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="对话不存在")
    return updated


@router.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, username: str = Depends(get_current_user)):
    db = get_user_db(username)
    db.delete_chat(sanitize_id(chat_id))
    return {"status": "ok"}


@router.put("/api/chats/{chat_id}/messages/{message_id}")
def update_message(chat_id: str, message_id: str, payload: Dict[str, Any], username: str = Depends(get_current_user)):
    db = get_user_db(username)
    cid = sanitize_id(chat_id)
    mid = sanitize_id(message_id)
    content = str(payload.get("content") or "")
    ok = db.update_active_swipe_content(cid, mid, content, build_prompt_frozen_content(content))
    if not ok:
        raise HTTPException(status_code=404, detail="消息不存在")
    return {"status": "ok", "chat": db.get_chat_full(cid)}


@router.delete("/api/chats/{chat_id}/messages/{message_id}")
def delete_message(chat_id: str, message_id: str, username: str = Depends(get_current_user)):
    db = get_user_db(username)
    cid = sanitize_id(chat_id)
    mid = sanitize_id(message_id)
    if not db.delete_node_subtree(cid, mid):
        raise HTTPException(status_code=404, detail="消息不存在")
    return {"status": "ok", "chat": db.get_chat_full(cid)}


@router.post("/api/chats/{chat_id}/branch")
def create_chat_branch(chat_id: str, payload: Dict[str, Any], username: str = Depends(get_current_user)):
    """Create a branch either in-tree (new branch checkout) or as a legacy cloned chat."""
    db = get_user_db(username)
    cid = sanitize_id(chat_id)
    src = db.get_chat_full(cid)
    if not src:
        raise HTTPException(status_code=404, detail="源对话不存在")

    up_to = payload.get("up_to_msg_id") or payload.get("message_id") or payload.get("msg_id")
    if payload.get("in_tree"):
        if up_to and not db.checkout_node(cid, sanitize_id(up_to)):
            raise HTTPException(status_code=404, detail="目标节点不存在")
        return {"status": "ok", "chat": db.get_chat_full(cid)}

    msgs = src.get("messages") or []
    if up_to:
        idx = next((i for i, m in enumerate(msgs) if m["id"] == up_to), -1)
        if idx == -1:
            raise HTTPException(status_code=404, detail="指定节点不存在")
        msgs = msgs[: idx + 1]
    new_id = uuid.uuid4().hex[:8]
    new_chat = db.create_chat(
        chat_id=new_id,
        project_id=src["project_id"],
        title=str(payload.get("title") or f"{src['title'][:12]} (分支)"),
        model=src.get("model", ""),
        variables=src.get("variables") or {},
        author_note=src.get("author_note"),
        group_config=src.get("group_config"),
        persona_id=src.get("persona_id", ""),
        preset_id=src.get("preset_id", ""),
        parent_chat_id=cid,
        init_messages=msgs,
        summary=src.get("summary", "") if len(msgs) >= src.get("summarized_count", 0) else "",
        summarized_count=src.get("summarized_count", 0) if len(msgs) >= src.get("summarized_count", 0) else 0,
    )
    return {"status": "ok", "chat": new_chat}


@router.get("/api/chats/{chat_id}/prompt_log")
def get_prompt_log(chat_id: str, username: str = Depends(get_current_user)):
    db = get_user_db(username)
    log = db.get_latest_prompt_log(sanitize_id(chat_id))
    return {"status": "ok", "prompt_log": log or {}}


@router.post("/api/chats/import")
def import_chat(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    db = get_user_db(username)
    raw = payload.get("chat") if isinstance(payload.get("chat"), dict) else payload
    cid = uuid.uuid4().hex[:8]
    msgs = raw.get("messages") or []
    created = db.create_chat(
        chat_id=cid,
        project_id=sanitize_id(raw.get("project_id") or "proj_default"),
        title=str(raw.get("title") or "导入对话"),
        model=str(raw.get("model") or ""),
        variables=raw.get("variables") or raw.get("inputs") or {},
        init_messages=msgs,
        summary=str(raw.get("summary") or ""),
    )
    return {"status": "ok", "chat": created}


@router.post("/api/chats/{chat_id}/summarize")
async def summarize_chat_endpoint(chat_id: str, payload: Dict[str, Any] = {}, username: str = Depends(get_current_user)):
    db = get_user_db(username)
    cid = sanitize_id(chat_id)
    chat = db.get_chat_full(cid)
    if not chat:
        raise HTTPException(status_code=404, detail="对话不存在")
    msgs = chat.get("messages") or []
    if len(msgs) < 2:
        return {"status": "ok", "summary": chat.get("summary", ""), "message": "消息过少无需摘要"}

    settings = db.get_settings()
    model_id = str(payload.get("model") or chat.get("model") or settings.get("model") or "")
    await discover_local_models(settings)
    ep = resolve_model_endpoint(model_id, settings)
    if ep["is_local"]:
        err = await ensure_local_engine_ready(model_id, ep["local_meta"], settings=settings)
        if err:
            raise HTTPException(status_code=503, detail=err.get("message", "本地模型未就绪"))
        if ep.get("local_meta", {}).get("base_url"):
            ep["base_url"] = ep["local_meta"]["base_url"]

    transcript = "\n\n".join(f"{'玩家' if m['role']=='user' else '主持人'}: {m.get('prompt_content') or m.get('content')}" for m in msgs[-16:])
    prompt = f"请将以下剧情压缩为 250 字以内的紧凑章节纪要，保留关键事件、道具变化、NPC 关系与未解伏笔：\n\n{transcript}"
    pieces: List[str] = []
    async for delta in stream_via_endpoint(
        endpoint=ep,
        messages=[{"role": "user", "content": prompt}],
        params={"temperature": 0.3, "max_tokens": 512},
        proxy_url=(settings.get("proxy") if settings.get("use_proxy") else None),
        think_enabled=False,
    ):
        if delta.text:
            pieces.append(delta.text)
    summary_txt = "".join(pieces).strip()
    if summary_txt:
        db.update_chat_meta(cid, {"summary": summary_txt, "summarized_count": len(msgs)})
        if payload.get("archive_chapter"):
            chap_num = len(chat.get("chapters") or []) + 1
            last_nid = msgs[-1]["id"]
            db.save_chapter(cid, chap_num, f"第 {chap_num} 章", summary_txt, last_nid)
    return {"status": "ok", "summary": summary_txt}


async def stream_trpg_generation(
    *,
    username: str,
    chat_id: str,
    user_text: str,
    model_id: str,
    raw_images: List[str],
    turn_cards: List[Dict[str, Any]],
    mode: str = "send",  # send | regenerate | swipe | group_turn
    target_node_id: Optional[str] = None,
    dice_roll: Optional[Dict[str, Any]] = None,
    speaker_card: Optional[Dict[str, Any]] = None,
    cot_override: Optional[bool] = None,
    video_ids: Optional[List[str]] = None,
    video_frame_images: Optional[List[str]] = None,
) -> StreamingResponse:
    """Unified background-safe SSE streaming pipeline for normal turns, swipes, and group turns."""
    db = get_user_db(username)
    my_seq = _bump_gen_seq(chat_id)
    prev_task = ACTIVE_BG_TASKS.pop(chat_id, None)
    if prev_task and not prev_task.done():
        prev_task.cancel()
        try:
            await asyncio.wait({prev_task}, timeout=1.5)
        except Exception:
            pass
    ACTIVE_PARTIAL_TEXT.pop(chat_id, None)
    ACTIVE_STATUS_TEXT.pop(chat_id, None)
    ACTIVE_LAST_ERROR.pop(chat_id, None)

    chat = db.get_chat_full(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="对话不存在")
    settings = db.get_settings()
    proj = db.get_project(chat["project_id"]) or {}
    eff_model = str(model_id or chat.get("model") or settings.get("model") or "").strip()
    if not eff_model:
        raise HTTPException(status_code=400, detail="请先选择或配置 AI 模型")

    await discover_local_models(settings)
    ep = resolve_model_endpoint(eff_model, settings)
    if not ep["is_local"] and not ep.get("base_url") and not ep.get("api_key"):
        raise HTTPException(status_code=400, detail="未配置在线 API 地址或 Key，请在左上角点击「配置模型」")

    params = _resolve_generation_params(settings, proj, eff_model)
    think_enabled = bool(cot_override) if cot_override is not None else bool(proj.get("cot_enabled", True))
    thinking_budget = safe_int(params.get("thinking_budget"), 1024)

    msgs = chat.get("messages") or []
    prev_state = empty_game_state(chat.get("active_state") or proj.get("initial_state"))
    dice_telemetry = format_dice_for_prompt(dice_roll) if dice_roll else None

    # Determine parent node & history slice based on mode
    def _extract_vid_ids(urls: Optional[List[str]]) -> List[str]:
        found: List[str] = []
        for u in urls or []:
            m = re.search(r"(vid_[a-zA-Z0-9._-]+)", str(u or ""))
            if m:
                vid = sanitize_id(m.group(1))
                if vid and vid not in found:
                    found.append(vid)
        return found

    user_node_id = ""
    turn_video_ids: List[str] = []
    client_fallback_video_frames: List[str] = []
    user_display_base = ""

    if mode == "swipe" and target_node_id:
        idx_t = next((i for i, m in enumerate(msgs) if m["id"] == target_node_id), -1)
        if idx_t == -1:
            raise HTTPException(status_code=404, detail="目标消息不存在")
        history_for_prompt = msgs[:idx_t]
        prev_u = next((m for m in reversed(history_for_prompt) if m["role"] == "user"), None)
        eff_user_text = str(prev_u.get("content") or "继续") if prev_u else "继续剧情"
        prev_state = empty_game_state((msgs[idx_t - 1].get("state_snapshot") if idx_t > 0 else None) or proj.get("initial_state"))
        chat_for_prompt = {**chat, "messages": history_for_prompt[:-1] if prev_u and history_for_prompt and history_for_prompt[-1]["id"] == prev_u["id"] else history_for_prompt}
        turn_imgs = list(prev_u.get("images") or []) if prev_u else []
        turn_video_ids = _extract_vid_ids(prev_u.get("videos") if prev_u else [])
    elif mode == "regenerate":
        # Re-branch from the target user node (or last user node) WITHOUT destroying old branch!
        if target_node_id:
            idx_u = next((i for i, m in enumerate(msgs) if m["id"] == target_node_id), -1)
        else:
            idx_u = max((i for i, m in enumerate(msgs) if m["role"] == "user"), default=-1)
        if idx_u == -1:
            raise HTTPException(status_code=400, detail="未找到对应玩家消息")
        target_u = msgs[idx_u]
        user_node_id = target_u["id"]
        eff_user_text = strip_legacy_start_game_hint(user_text.strip() or str(target_u.get("content") or ""))
        user_display_base = eff_user_text
        if user_text.strip() and user_text.strip() != target_u.get("content"):
            db.update_active_swipe_content(chat_id, user_node_id, eff_user_text, eff_user_text)
        prev_state = empty_game_state(target_u.get("state_snapshot") or proj.get("initial_state"))
        chat_for_prompt = {**chat, "messages": msgs[:idx_u]}
        turn_imgs = list(target_u.get("images") or [])
        turn_video_ids = _extract_vid_ids(target_u.get("videos"))
    else:
        # Normal send or group_turn
        clean_video_ids = [
            sanitize_id(v) for v in (video_ids or []) if str(v or "").strip().startswith("vid_")
        ]
        eff_user_text = strip_legacy_start_game_hint(user_text.strip())
        if not eff_user_text and turn_cards:
            eff_user_text = f"【附带角色卡：{'、'.join(str(c.get('name','角色')) for c in turn_cards)}】"
        if not eff_user_text and clean_video_ids:
            eff_user_text = "【附带视频】"
        if not eff_user_text and raw_images:
            eff_user_text = "【附带图片】"
        if not eff_user_text and mode == "group_turn" and speaker_card:
            eff_user_text = f"请「{speaker_card['name']}」结合当前局势自然接话并推动剧情。"
        if not eff_user_text:
            raise HTTPException(status_code=400, detail="消息内容不能为空")

        opt_imgs = await optimize_images_async([im for im in raw_images if im])
        client_fallback_video_frames = await optimize_images_async(
            [im for im in (video_frame_images or [])[:36] if im],
            max_dim=640,
            quality=74,
            min_bytes=45_000,
        )
        asset_ids = await auto_save_images_to_gallery_async(username, opt_imgs)
        media_asset_ids = list(dict.fromkeys(asset_ids + clean_video_ids))
        parent_id = chat.get("active_node_id") or (msgs[-1]["id"] if msgs else "")
        user_display_base = eff_user_text
        user_node_id = db.append_node(
            chat_id=chat_id,
            parent_id=parent_id,
            role="user",
            content=eff_user_text,
            prompt_content=eff_user_text,
            state_snapshot=prev_state,
            dice_rolls=[dice_roll] if dice_roll else [],
            media_asset_ids=media_asset_ids,
            character_cards=turn_cards,
        )
        chat_for_prompt = chat
        turn_imgs = opt_imgs
        turn_video_ids = clean_video_ids

    event_queue: asyncio.Queue[Optional[Dict[str, Any]]] = asyncio.Queue()

    async def _worker() -> None:
        collected: List[str] = []
        thinking_buf: List[str] = []
        cache_hits = 0
        try:
            turn_video_bundles: List[Dict[str, Any]] = []
            eff_prompt_text = eff_user_text
            worker_turn_imgs = list(turn_imgs)

            if turn_video_ids:
                v_status = "正在处理视频画面与音频识别..."
                ACTIVE_STATUS_TEXT[chat_id] = v_status
                await event_queue.put({"status": v_status})
                for vid in turn_video_ids:
                    await ensure_video_processed_async(username, vid)
                    bundle = await asyncio.to_thread(load_video_prompt_bundle, username, vid)
                    if bundle and (bundle.get("frames") or bundle.get("audio_base64") or bundle.get("transcript")):
                        turn_video_bundles.append(bundle)

                if turn_video_bundles:
                    v_summaries = [format_video_text_summary(b) for b in turn_video_bundles]
                    if user_node_id and mode != "swipe":
                        frozen_u = "\n\n".join([user_display_base] + v_summaries).strip()
                        db.update_active_swipe_content(chat_id, user_node_id, user_display_base, frozen_u)
                elif client_fallback_video_frames:
                    worker_turn_imgs.extend(client_fallback_video_frames)
                    if "视频" not in eff_prompt_text:
                        eff_prompt_text = f"{eff_prompt_text}\n（附带上传视频的关键帧截图，按时间顺序）"
            elif client_fallback_video_frames:
                worker_turn_imgs.extend(client_fallback_video_frames)
                if "视频" not in eff_prompt_text:
                    eff_prompt_text = f"{eff_prompt_text}\n（附带上传视频的关键帧截图，按时间顺序）"

            api_messages, prompt_log_snap, _ = await assemble_kv_friendly_prompt(
                db=db,
                username=username,
                project_data=proj,
                chat_data=chat_for_prompt,
                settings=settings,
                user_display_text=eff_prompt_text,
                turn_images=worker_turn_imgs,
                turn_char_cards=turn_cards,
                active_state=prev_state,
                dice_telemetry=dice_telemetry,
                speaker_card=speaker_card,
                model_id=eff_model,
                turn_video_bundles=turn_video_bundles,
            )
            db.save_prompt_log(chat_id, user_node_id, prompt_log_snap)

            if ep["is_local"]:
                async def _cb(msg: str) -> None:
                    ACTIVE_STATUS_TEXT[chat_id] = msg
                    await event_queue.put({"status": msg})

                diag = await ensure_local_engine_ready(
                    eff_model, ep["local_meta"], settings=settings, status_callback=_cb
                )
                if diag:
                    err_obj = {"error": diag.get("message") or "本地引擎未就绪", "diagnosis": diag}
                    ACTIVE_LAST_ERROR[chat_id] = err_obj
                    await event_queue.put(err_obj)
                    return
                if ep.get("local_meta", {}).get("base_url"):
                    ep["base_url"] = ep["local_meta"]["base_url"]

            allow_vision = bool(ep.get("supports_vision", True))
            allow_audio = bool(ep.get("supports_audio", False))
            cur_msgs = sanitize_messages_for_model(api_messages, allow_vision, allow_audio)
            proxy = (settings.get("proxy") or "").strip() if settings.get("use_proxy") else None

            for _attempt in range(3):
                try:
                    in_think_stream = False
                    think_chars = 0
                    max_think_chars = max(600, int(thinking_budget * 2.2)) if think_enabled else 0
                    async for delta in stream_via_endpoint(
                        endpoint=ep,
                        messages=cur_msgs,
                        params=params,
                        proxy_url=proxy,
                        think_enabled=think_enabled,
                        thinking_budget=thinking_budget,
                        chat_id=chat_id,
                    ):
                        if GEN_SEQ.get(chat_id) != my_seq:
                            return
                        if delta.cache_read_tokens:
                            cache_hits = max(cache_hits, delta.cache_read_tokens)
                        if delta.thinking:
                            ACTIVE_STATUS_TEXT.pop(chat_id, None)
                            if think_enabled and think_chars < max_think_chars:
                                if not in_think_stream:
                                    in_think_stream = True
                                    collected.append("<think>\n")
                                    await event_queue.put({"chunk": "<think>\n"})
                                thinking_buf.append(delta.thinking)
                                think_chars += len(delta.thinking)
                                collected.append(delta.thinking)
                                ACTIVE_PARTIAL_TEXT[chat_id] = "".join(collected)
                                await event_queue.put({"chunk": delta.thinking})
                        if delta.text:
                            ACTIVE_STATUS_TEXT.pop(chat_id, None)
                            if in_think_stream:
                                in_think_stream = False
                                collected.append("\n</think>\n\n")
                                await event_queue.put({"chunk": "\n</think>\n\n"})
                            collected.append(delta.text)
                            await event_queue.put({"chunk": delta.text})
                            cur_full = "".join(collected)
                            ACTIVE_PARTIAL_TEXT[chat_id] = cur_full
                            if len(cur_full) % 200 < len(delta.text):
                                trimmed, looped = detect_and_trim_stream_loop(cur_full)
                                if looped:
                                    collected = [trimmed]
                                    ACTIVE_PARTIAL_TEXT[chat_id] = trimmed
                                    await event_queue.put({"replace": trimmed})
                                    break
                    if in_think_stream:
                        collected.append("\n</think>\n\n")
                        await event_queue.put({"chunk": "\n</think>\n\n"})
                    break
                except httpx.HTTPStatusError as he:
                    if he.response.status_code in (400, 422) and not collected:
                        if allow_audio:
                            allow_audio = False
                            cur_msgs = sanitize_messages_for_model(api_messages, allow_vision, allow_audio)
                            msg_retry = "当前模型不支持直传音频流，已保留画面与音频文字识别重试..."
                            ACTIVE_STATUS_TEXT[chat_id] = msg_retry
                            await event_queue.put({"status": msg_retry})
                            continue
                        if allow_vision:
                            allow_vision = False
                            cur_msgs = sanitize_messages_for_model(api_messages, allow_vision, allow_audio)
                            msg_retry = "当前模型不支持图片输入，已自动切换纯文本重试..."
                            ACTIVE_STATUS_TEXT[chat_id] = msg_retry
                            await event_queue.put({"status": msg_retry})
                            continue
                    ACTIVE_LAST_ERROR[chat_id] = {"error": str(he)}
                    await event_queue.put({"error": str(he)})
                    return

            raw_final = strip_distilled_artifact_tags("".join(collected)).strip()
            if not raw_final:
                ACTIVE_LAST_ERROR[chat_id] = {"error": "模型未返回有效文本，请重试"}
                await event_queue.put({"error": "模型未返回有效文本，请重试"})
                return

            final_text, _ = apply_regex_scripts(raw_final, proj.get("regex_scripts"), target_scope=1, only_persistent=True)
            think_extracted, _ = extract_thinking_block(final_text)
            new_state, state_patch = apply_ai_output_to_state(prev_state, final_text)
            frozen_prompt = build_prompt_frozen_content(final_text)
            choices = extract_action_choices(final_text)
            trig_wb = prompt_log_snap.get("triggered_worldbooks") or []
            trig_cgs, _ = evaluate_cg_book(proj, f"{eff_user_text}\n{final_text}", final_text)

            if mode == "swipe" and target_node_id:
                sw_idx = db.add_swipe(
                    chat_id,
                    target_node_id,
                    final_text,
                    frozen_prompt,
                    thinking=think_extracted,
                    state_snapshot=new_state,
                    state_patch=state_patch or {},
                    triggered_worldbooks=trig_wb,
                    triggered_cgs=trig_cgs,
                    suggested_questions=choices,
                    activate=True,
                )
                saved_msg_id = target_node_id
            else:
                saved_msg_id = db.append_node(
                    chat_id=chat_id,
                    parent_id=user_node_id,
                    role="assistant",
                    content=final_text,
                    prompt_content=frozen_prompt,
                    thinking=think_extracted,
                    speaker_card_id=str(speaker_card.get("id") or "") if speaker_card else "",
                    speaker_name=str(speaker_card.get("name") or "") if speaker_card else "",
                    state_snapshot=new_state,
                    state_patch=state_patch or {},
                    triggered_worldbooks=trig_wb,
                    triggered_cgs=trig_cgs,
                    suggested_questions=choices,
                )
                sw_idx = 0

            await event_queue.put(
                {
                    "done": True,
                    "msg_id": saved_msg_id,
                    "user_msg_id": user_node_id,
                    "swipe_idx": sw_idx,
                    "state": new_state,
                    "state_patch": state_patch,
                    "choices": choices,
                    "triggered_worldbooks": trig_wb,
                    "triggered_cgs": trig_cgs,
                    "cache_read_tokens": cache_hits,
                    "immutable_prefix_tokens": prompt_log_snap.get("immutable_prefix_tokens", 0),
                }
            )
        except asyncio.CancelledError:
            partial = "".join(collected).strip()
            if partial and mode != "swipe":
                db.append_node(
                    chat_id=chat_id,
                    parent_id=user_node_id,
                    role="assistant",
                    content=partial,
                    prompt_content=build_prompt_frozen_content(partial),
                    state_snapshot=prev_state,
                    interrupted=True,
                )
        except Exception as exc:
            logger.exception("Generation error for chat %s: %s", chat_id, exc)
            err_msg = str(exc).strip() or type(exc).__name__
            ACTIVE_LAST_ERROR[chat_id] = {"error": err_msg}
            await event_queue.put({"error": err_msg})
        finally:
            ACTIVE_BG_TASKS.pop(chat_id, None)
            ACTIVE_PARTIAL_TEXT.pop(chat_id, None)
            ACTIVE_STATUS_TEXT.pop(chat_id, None)
            await event_queue.put(None)

    ACTIVE_BG_TASKS[chat_id] = asyncio.create_task(_worker())

    async def _sse_gen():
        yield ": connected\n\n"
        while True:
            try:
                ev = await asyncio.wait_for(event_queue.get(), timeout=12.0)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            if ev is None:
                break
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _sse_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/chat/stream")
async def chat_stream(req: SendMessageRequest, username: str = Depends(get_current_user)):
    cid = sanitize_id(req.chat_id)
    imgs = [x for x in (req.images_base64 or []) if x]
    if not imgs and req.image_base64:
        imgs = [req.image_base64]
    return await stream_trpg_generation(
        username=username,
        chat_id=cid,
        user_text=req.content or "",
        model_id=req.model or "",
        raw_images=imgs,
        turn_cards=req.character_cards or [],
        mode="regenerate" if req.regenerate else "send",
        target_node_id=sanitize_id(req.target_user_msg_id) if req.target_user_msg_id else None,
        dice_roll=req.dice_roll,
        cot_override=req.cot_enabled,
        video_ids=req.video_ids or [],
        video_frame_images=req.video_frame_images or [],
    )
