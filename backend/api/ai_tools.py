# -*- coding: utf-8 -*-
"""AI assistant creative tools: reroll choices, generate game card, polish prompts."""
from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from backend.config import normalize_project_schema
from backend.core.auth import get_current_user
from backend.core.security import sanitize_id
from backend.engines.supervisor import discover_local_models, ensure_local_engine_ready
from backend.providers.router import resolve_model_endpoint, stream_via_endpoint
from backend.storage.db import get_user_db
from backend.trpg.stream_parser import extract_action_choices, strip_thinking_blocks

router = APIRouter()


async def _run_single_ai_completion(username: str, model_id: str, messages: List[Dict[str, str]], max_tokens: int = 1600, temp: float = 0.72) -> str:
    db = get_user_db(username)
    s = db.get_settings()
    eff_model = str(model_id or s.get("model") or "").strip()
    if not eff_model:
        raise HTTPException(status_code=400, detail="请先配置或选择模型")
    await discover_local_models(s)
    ep = resolve_model_endpoint(eff_model, s)
    if ep["is_local"]:
        err = await ensure_local_engine_ready(eff_model, ep["local_meta"], settings=s)
        if err:
            raise HTTPException(status_code=503, detail=err.get("message", "本地引擎未就绪"))
    pieces: List[str] = []
    async for d in stream_via_endpoint(
        endpoint=ep,
        messages=messages,
        params={"temperature": temp, "max_tokens": max_tokens},
        proxy_url=(s.get("proxy") if s.get("use_proxy") else None),
        think_enabled=False,
    ):
        if d.text:
            pieces.append(d.text)
    return strip_thinking_blocks("".join(pieces)).strip()


@router.post("/api/ai/reroll_choices")
async def reroll_choices(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    db = get_user_db(username)
    cid = sanitize_id(payload.get("chat_id") or "")
    mid = sanitize_id(payload.get("msg_id") or "")
    chat = db.get_chat_full(cid)
    if not chat:
        raise HTTPException(status_code=404, detail="对话不存在")
    target = next((m for m in chat["messages"] if m["id"] == mid), None)
    if not target:
        raise HTTPException(status_code=404, detail="消息不存在")

    story_body = re.sub(r"\n*你打算怎么做？[\s\S]*$", "", str(target.get("content") or "")).strip()
    prompt = (
        f"基于以下最新剧情，重新生成 4 个截然不同的后续行动选项（高危检定项在末尾加 【🎲属性检定】），只输出「你打算怎么做？」和 1.~4.：\n\n{story_body[-2000:]}"
    )
    new_choices_txt = await _run_single_ai_completion(username, str(payload.get("model") or chat.get("model") or ""), [{"role": "user", "content": prompt}], 512, 0.82)
    if "你打算怎么做" not in new_choices_txt:
        new_choices_txt = "你打算怎么做？\n" + new_choices_txt
    updated = f"{story_body}\n\n{new_choices_txt}"
    db.update_active_swipe_content(cid, mid, updated, target.get("prompt_content"))
    return {
        "status": "ok",
        "msg_id": mid,
        "updated_content": updated,
        "new_choices": new_choices_txt,
        "choices": extract_action_choices(updated),
    }


@router.post("/api/ai/generate_game_card")
async def ai_generate_game_card(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    idea = str(payload.get("idea") or payload.get("prompt") or "").strip()
    if not idea:
        raise HTTPException(status_code=400, detail="请先填写剧本灵感")
    sys_p = (
        "你是顶级 TRPG 策划。请根据玩家灵感输出纯 JSON 游戏卡配置，包含："
        'name, category, ruleset ("d20"/"d100"/"2d6"), description, system_prompt, '
        'opening_greetings (含 {title, content} 数组), world_book (含 {name, keys, content} 数组)。'
    )
    raw = await _run_single_ai_completion(username, str(payload.get("model") or ""), [{"role": "system", "content": sys_p}, {"role": "user", "content": idea}], 2400, 0.75)
    body = raw[raw.find("{"): raw.rfind("}") + 1] if "{" in raw and "}" in raw else "{}"
    try:
        obj = json.loads(body)
    except Exception:
        obj = {"name": "AI 生成剧本", "description": idea, "system_prompt": raw}
    obj["id"] = f"proj_{uuid.uuid4().hex[:8]}"
    norm = normalize_project_schema(obj, {}, global_defaults=get_user_db(username).get_settings())
    return {"status": "ok", "project": norm}


@router.post("/api/ai/polish")
@router.post("/api/ai/polish_prompt")
async def ai_polish_field(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    text = str(payload.get("text") or payload.get("content") or "").strip()
    field = str(payload.get("field") or "设定").strip()
    if not text:
        raise HTTPException(status_code=400, detail="待润色内容为空")
    prompt = f"请优化以下跑团「{field}」文案，使其画面感更强、逻辑更紧凑、字数精炼，直接输出改写后正文：\n\n{text}"
    polished = await _run_single_ai_completion(username, str(payload.get("model") or ""), [{"role": "user", "content": prompt}], 1600, 0.7)
    return {"status": "ok", "polished": polished, "text": polished}
