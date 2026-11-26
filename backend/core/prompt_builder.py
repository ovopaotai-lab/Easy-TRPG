# -*- coding: utf-8 -*-
"""3-Layer KV-Cache-Friendly Prompt Builder, 25% Chunk Eviction & ST Preset Importer."""
from __future__ import annotations

import copy
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from backend.config import (
    DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT,
    build_ui_modules_spec_block,
    is_free_chat_project,
    is_simple_trpg_project,
    safe_float,
    safe_int,
)
from backend.core.media import optimize_images_async, resolve_gallery_ref_to_data_url
from backend.core.memory import (
    build_frozen_chapters_block,
    format_episodic_recall_block,
    recall_episodic_snippets,
)
from backend.core.regex_engine import apply_regex_scripts
from backend.core.tokenizer import estimate_tokens
from backend.core.variables import interpolate_variables
from backend.core.video_processor import format_video_text_summary
from backend.core.worldbook import evaluate_world_book_layered
from backend.storage.db import UserDatabase
from backend.trpg.state_engine import GameState, format_compact_state_for_prompt

_LEGACY_HINT_RE = re.compile(
    r"\s*[（(]请根据当前剧本世界观与角色设定，直接以第二人称代入感展开第一幕沉浸式场景描写[^）)]*[）)]\s*"
)


def strip_legacy_start_game_hint(text: str) -> str:
    return _LEGACY_HINT_RE.sub("", text or "").strip()


def format_character_cards_block(cards: List[Dict[str, Any]], for_system: bool = False) -> str:
    if not cards or not isinstance(cards, list):
        return ""
    blocks: List[str] = []
    for c in cards:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "未命名角色").strip()
        lines = [f"角色名：{name}"]
        for k, lbl in (("description", "设定"), ("personality", "性格"), ("scenario", "背景")):
            v = str(c.get(k) or "").strip()
            if v:
                lines.append(f"{lbl}：{v}")
        if for_system and c.get("mes_example"):
            lines.append(f"对话范例：{str(c['mes_example']).strip()[:800]}")
        blocks.append("\n".join(lines))
    if not blocks:
        return ""
    hdr = "【常驻角色卡设定】" if for_system else "【本回合涉及角色】"
    return f"{hdr}\n" + "\n---\n".join(blocks)


def import_sillytavern_preset(raw_preset: Dict[str, Any], name: str = "") -> Dict[str, Any]:
    """Convert SillyTavern Chat Completion Preset JSON into Easy-TRPG v2 preset."""
    prompts_raw = raw_preset.get("prompts") or []
    prompt_order_raw = raw_preset.get("prompt_order") or []
    order_ids: List[str] = []
    if isinstance(prompt_order_raw, list):
        for blk in prompt_order_raw:
            if isinstance(blk, dict) and isinstance(blk.get("order"), list):
                order_ids = [str(x.get("identifier") or "") for x in blk["order"] if isinstance(x, dict) and x.get("enabled", True)]
                if order_ids:
                    break

    custom_blocks: List[Dict[str, Any]] = []
    for p in prompts_raw:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("identifier") or p.get("name") or "")
        content = str(p.get("content") or "").strip()
        if not content or p.get("marker"):
            continue
        if order_ids and pid not in order_ids:
            continue
        custom_blocks.append(
            {
                "id": pid,
                "name": str(p.get("name") or pid),
                "role": str(p.get("role") or "system"),
                "content": content,
                "injection_position": safe_int(p.get("injection_position"), 0),
                "injection_depth": safe_int(p.get("injection_depth"), 4),
            }
        )

    return {
        "name": name or str(raw_preset.get("name") or "SillyTavern 预设"),
        "temperature": safe_float(raw_preset.get("temperature"), 0.7),
        "top_p": safe_float(raw_preset.get("top_p"), 0.9),
        "top_k": safe_int(raw_preset.get("top_k"), 40),
        "min_p": safe_float(raw_preset.get("min_p"), 0.05),
        "repetition_penalty": safe_float(raw_preset.get("repetition_penalty"), 1.05),
        "frequency_penalty": safe_float(raw_preset.get("frequency_penalty"), 0.0),
        "presence_penalty": safe_float(raw_preset.get("presence_penalty"), 0.0),
        "max_tokens": safe_int(raw_preset.get("openai_max_tokens"), 4096),
        "block_order": ["system", "persona", "cards", "constant_wb", "chapters", "memory_palace", "history", "dynamic_wb", "state", "author_note", "user_turn"],
        "custom_blocks": custom_blocks,
        "source": "sillytavern",
    }


def _select_history_chunked(
    history_messages: List[Dict[str, Any]],
    *,
    context_mode: str,
    max_turns: int,
    max_context_k: int,
    fixed_overhead_tokens: int,
    keep_recent_msgs: int,
) -> List[Dict[str, Any]]:
    """
    Chunked high-watermark eviction:
    Keep 100% of history until hitting budget; when exceeded, drop oldest ~25% in a single step
    so the next several turns retain an identical prefix for KV-cache hits!
    """
    if not history_messages:
        return []
    if context_mode == "turns":
        limit = max(2, max_turns * 2)
        if len(history_messages) <= limit:
            return list(history_messages)
        # Drop extra 25% batch when exceeding turn cap
        drop_n = max(2, (len(history_messages) - limit) + max(2, limit // 4))
        return list(history_messages[min(len(history_messages) - 2, drop_n):])

    budget = max(1024, (max_context_k * 1024) - fixed_overhead_tokens)
    msg_tokens = [estimate_tokens(str(m.get("prompt_content") or m.get("content") or "")) + 12 for m in history_messages]
    total_tok = sum(msg_tokens)
    if total_tok <= budget:
        return list(history_messages)

    # Exceeded budget -> evict oldest down to 75% target watermark (or at least keep_recent_msgs)
    target_tok = int(budget * 0.75)
    min_keep = min(len(history_messages), max(2, keep_recent_msgs))
    max_start = len(history_messages) - min_keep
    acc = total_tok
    start_idx = 0
    while start_idx < max_start and acc > target_tok:
        acc -= msg_tokens[start_idx]
        start_idx += 1
    # Ensure we start on a user boundary if possible for clean alternation
    if start_idx < max_start and history_messages[start_idx].get("role") == "assistant":
        start_idx += 1
    return list(history_messages[start_idx:])


async def assemble_kv_friendly_prompt(
    *,
    db: UserDatabase,
    username: str,
    project_data: Dict[str, Any],
    chat_data: Dict[str, Any],
    settings: Dict[str, Any],
    user_display_text: str,
    turn_images: List[str],
    turn_char_cards: List[Dict[str, Any]],
    active_state: Optional[GameState] = None,
    dice_telemetry: Optional[str] = None,
    speaker_card: Optional[Dict[str, Any]] = None,
    model_id: str = "",
    turn_video_bundles: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[str]]:
    """
    Build OpenAI-shape messages using 3-Layer KV-Cache-Friendly Architecture:
      Layer 0 (Immutable Prefix): System + Persona + Cards + Constant WB + Frozen Chapters + Memory Palace
      Layer 1 (Immutable History): Frozen prompt_content per historical node + chunked eviction
      Layer 2 (Dynamic Tail, Depth 0-2): Dynamic WB + FTS5 Recall + Live State + Author's Note + User Turn
    """
    comp_params = dict(project_data.get("completion_params") or {})
    use_global = bool(project_data.get("use_global_params", True))
    if use_global:
        for k in ("context_mode", "max_context_k", "keep_recent_messages", "worldbook_scan_depth", "kv_cache_mode"):
            if k in settings and settings[k] is not None:
                comp_params[k] = settings[k]

    context_mode = str(comp_params.get("context_mode") or "tokens").lower()
    max_turns = max(1, safe_int(comp_params.get("context", project_data.get("max_context_turns", 96)), 96))
    max_context_k = max(4, safe_int(comp_params.get("max_context_k"), 96))
    keep_recent_msgs = max(2, safe_int(comp_params.get("keep_recent_messages"), 6))
    wb_scan_depth = max(1, safe_int(comp_params.get("worldbook_scan_depth"), 5))

    chat_inputs = dict(chat_data.get("variables") or chat_data.get("inputs") or {})
    prompt_vars = project_data.get("prompt_variables") or []

    # Resolve User Persona
    personas = db.list_personas()
    persona_id = str(chat_data.get("persona_id") or "")
    persona = next((p for p in personas if p["id"] == persona_id), None) or next((p for p in personas if p.get("is_default")), None)
    user_name = str(persona.get("name") if persona else chat_inputs.get("user") or "玩家")
    persona_desc = str(persona.get("description") if persona else "")
    char_name = str(speaker_card.get("name") if speaker_card else project_data.get("name") or "主持人")

    # Gather permanent character cards + worldbooks
    all_cards = list(turn_char_cards or [])
    for bc in project_data.get("bundled_cards") or []:
        if isinstance(bc, dict) and bc.get("name") and bc.get("name") not in {c.get("name") for c in all_cards}:
            all_cards.append(bc)

    card_wb_entries = []
    for c in all_cards:
        if isinstance(c, dict) and isinstance(c.get("character_book"), list):
            card_wb_entries.extend(c["character_book"])
    merged_proj = dict(project_data)
    if card_wb_entries:
        merged_proj["world_book"] = list(project_data.get("world_book") or []) + card_wb_entries

    history_messages = list(chat_data.get("messages") or [])
    visited_wb_ids = list(chat_data.get("visited_wb_ids") or [])

    # Evaluate Worldbook into CONSTANT (Layer 0) vs DYNAMIC (Layer 2)
    wb_res = evaluate_world_book_layered(
        project_data=merged_proj,
        history_messages=history_messages,
        current_user_text=user_display_text,
        chat_inputs=chat_inputs,
        visited_wb_ids=visited_wb_ids,
        default_scan_depth=wb_scan_depth,
        user_name=user_name,
        char_name=char_name,
    )
    if visited_wb_ids != (chat_data.get("visited_wb_ids") or []):
        db.update_chat_meta(chat_data["id"], {"visited_wb_ids": visited_wb_ids})

    # ==================== LAYER 0: IMMUTABLE PREFIX ====================
    layer0_parts: List[str] = []
    raw_sys = interpolate_variables(
        str(project_data.get("system_prompt") or ""),
        prompt_vars,
        chat_inputs,
        user_name=user_name,
        char_name=char_name,
        persona_desc=persona_desc,
    ).strip()
    if raw_sys:
        layer0_parts.append(raw_sys)

    is_free = is_free_chat_project(project_data)
    is_simple = is_simple_trpg_project(project_data)
    if not is_free and not is_simple:
        proto = str(project_data.get("system_protocol_prompt") or "").strip()
        if not proto and project_data.get("status_panel_enabled", True):
            proto = DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT
        if proto:
            layer0_parts.append(proto)
        ui_block = build_ui_modules_spec_block(project_data)
        if ui_block:
            layer0_parts.append(ui_block)

    if persona and persona_desc:
        layer0_parts.append(f"【玩家人设：{user_name}】\n{persona_desc}")

    cards_sys = format_character_cards_block(all_cards, for_system=True)
    if cards_sys:
        layer0_parts.append(cards_sys)

    if wb_res["constant_system"]:
        layer0_parts.append("【核心世界观常驻设定】\n" + "\n\n".join(wb_res["constant_system"]))

    mem_palace = project_data.get("memory_palace") or []
    if mem_palace:
        mp_lines = [
            f"【{m.get('title') or m.get('key') or '长期记忆'}】：{interpolate_variables(str(m.get('content') or ''), prompt_vars, chat_inputs)}"
            for m in mem_palace
            if isinstance(m, dict) and str(m.get("content") or "").strip()
        ]
        if mp_lines:
            layer0_parts.append("【记忆宫殿】\n" + "\n".join(mp_lines))

    chapters_block = build_frozen_chapters_block(chat_data.get("chapters") or [])
    if chapters_block:
        layer0_parts.append(chapters_block)

    rolling_sum = str(chat_data.get("summary") or "").strip()
    if rolling_sum:
        layer0_parts.append(f"【前情摘要】\n{rolling_sum}")

    # Apply preset custom system blocks if active
    preset_id = str(chat_data.get("preset_id") or "")
    preset = db.get_preset(preset_id) if preset_id else None
    if preset:
        for cb in preset.get("custom_blocks") or []:
            if isinstance(cb, dict) and cb.get("injection_position", 0) == 0 and cb.get("content"):
                layer0_parts.append(str(cb["content"]))

    static_system_text = "\n\n".join(p for p in layer0_parts if p).strip()

    # ==================== LAYER 2 (pre-estimate overhead for Layer 1 sizing) ====================
    tail_injections: List[Dict[str, str]] = []
    if wb_res["dynamic_system"]:
        tail_injections.append(
            {
                "role": "system",
                "content": "【本回合关联世界书设定】\n" + "\n\n".join(wb_res["dynamic_system"]),
            }
        )

    # ==================== LAYER 1: IMMUTABLE HISTORY ====================
    fixed_tokens = estimate_tokens(static_system_text) + estimate_tokens(user_display_text) + 1200
    selected_history = _select_history_chunked(
        history_messages,
        context_mode=context_mode,
        max_turns=max_turns,
        max_context_k=max_context_k,
        fixed_overhead_tokens=fixed_tokens,
        keep_recent_msgs=keep_recent_msgs,
    )
    selected_ids = {str(m.get("id") or "") for m in selected_history}

    # Tier 3 Memory: FTS5 Episodic Recall from messages evicted outside active window
    if len(selected_history) < len(history_messages):
        recalled = recall_episodic_snippets(
            db,
            chat_data["id"],
            user_display_text,
            excluded_node_ids=selected_ids,
            limit=3,
        )
        recall_txt = format_episodic_recall_block(recalled)
        if recall_txt:
            tail_injections.append({"role": "system", "content": recall_txt})

    # Live Compact TRPG State Snapshot in Tail
    if active_state is not None and not is_free:
        state_txt = format_compact_state_for_prompt(active_state)
        if state_txt:
            tail_injections.append({"role": "system", "content": state_txt})

    # Group Chat Speaker Directive
    if speaker_card:
        sp_name = str(speaker_card.get("name") or "")
        sp_desc = str(speaker_card.get("personality") or speaker_card.get("description") or "")[:400]
        tail_injections.append(
            {
                "role": "system",
                "content": f"【本回合主视角发言角色：{sp_name}】\n请以「{sp_name}」的口吻、立场与行动逻辑主导本回合反应，同时自然推动场景。人物参考：{sp_desc}",
            }
        )

    assembled_msgs: List[Dict[str, Any]] = []
    if static_system_text:
        assembled_msgs.append({"role": "system", "content": static_system_text})

    # Build immutable history messages (NEVER retroactively mutating older messages!)
    last_user_idx = max((i for i, m in enumerate(selected_history) if m.get("role") == "user"), default=-1)
    for idx_h, h in enumerate(selected_history):
        role = str(h.get("role") or "user")
        if role == "user":
            txt = strip_legacy_start_game_hint(str(h.get("prompt_content") or h.get("content") or ""))
            if idx_h == last_user_idx:
                h_imgs = [
                    im for im in (
                        [resolve_gallery_ref_to_data_url(username, u) or u for u in (h.get("images") or [])]
                    ) if im
                ]
                if h_imgs:
                    opt = await optimize_images_async(h_imgs, max_dim=768, quality=75, min_bytes=45_000)
                    parts = [{"type": "image_url", "image_url": {"url": u}} for u in opt if u]
                    parts.append({"type": "text", "text": txt})
                    assembled_msgs.append({"role": "user", "content": parts})
                    continue
            assembled_msgs.append({"role": "user", "content": txt})
        elif role == "assistant":
            # Use frozen prompt_content saved when message was written -> 100% KV prefix stability!
            frozen_p = str(h.get("prompt_content") or h.get("content") or "")
            assembled_msgs.append({"role": "assistant", "content": frozen_p})

    # Insert Layer 2 Dynamic Tail injections BEFORE current user turn
    for inj in tail_injections:
        assembled_msgs.append(inj)

    # Author's Note (depth 0 = after user turn, depth >=1 = before user turn or deeper)
    author_note = chat_data.get("author_note") or {}
    an_text = str(author_note.get("content") or "").strip()
    an_enabled = author_note.get("enabled", True) is not False
    an_depth = max(0, min(10, safe_int(author_note.get("depth"), 1)))
    an_role = str(author_note.get("role") or "system")
    if an_enabled and an_text:
        an_msg = {"role": an_role if an_role in ("system", "user", "assistant") else "system", "content": f"【导演备注】{an_text}"}
        if an_depth > 0:
            ins_at = max(1 if static_system_text else 0, len(assembled_msgs) - max(0, an_depth - 1))
            assembled_msgs.insert(ins_at, an_msg)

    # Current user turn text (prefix + dice + user + suffix)
    base_prefix = interpolate_variables(str(project_data.get("prefix") or ""), prompt_vars, chat_inputs, user_name=user_name, char_name=char_name).strip()
    base_suffix = interpolate_variables(str(project_data.get("suffix") or ""), prompt_vars, chat_inputs, user_name=user_name, char_name=char_name).strip()
    pre_all = "\n".join(wb_res["prefix"] + ([base_prefix] if base_prefix else [])).strip()
    suf_all = "\n".join(([base_suffix] if base_suffix else []) + wb_res["suffix"]).strip()

    user_parts = []
    if pre_all:
        user_parts.append(pre_all)
    if dice_telemetry:
        user_parts.append(dice_telemetry)
    user_parts.append(user_display_text)
    if suf_all:
        user_parts.append(suf_all)
    user_final = "\n".join(p for p in user_parts if p).strip()

    # Apply prompt-only regex rules on user input
    regex_list = project_data.get("regex_scripts") or []
    user_final, applied_rx = apply_regex_scripts(user_final, regex_list, target_scope=2, only_prompt=True)

    resolved_turn_imgs = []
    for raw_im in turn_images or []:
        u = resolve_gallery_ref_to_data_url(username, raw_im) or raw_im
        if u:
            resolved_turn_imgs.append(u)
    for c in turn_char_cards or []:
        av = resolve_gallery_ref_to_data_url(username, str(c.get("avatar") or "")) or str(c.get("avatar") or "")
        if av.startswith("data:image/"):
            resolved_turn_imgs.append(av)

    if resolved_turn_imgs or turn_video_bundles:
        opt_imgs = await optimize_images_async(resolved_turn_imgs, max_dim=896, quality=76, min_bytes=70_000)
        parts: List[Dict[str, Any]] = [{"type": "image_url", "image_url": {"url": u}} for u in opt_imgs if u]
        for vb in turn_video_bundles or []:
            v_summary = format_video_text_summary(vb)
            if v_summary:
                parts.append({"type": "text", "text": v_summary})
            for fr in vb.get("frames") or []:
                ts_lbl = str(fr.get("timestamp_label") or "").strip()
                d_url = str(fr.get("data_url") or "").strip()
                if ts_lbl:
                    parts.append({"type": "text", "text": f"[{ts_lbl}]"})
                if d_url:
                    parts.append({"type": "image_url", "image_url": {"url": d_url}})
            audio_b64 = str(vb.get("audio_base64") or "").strip()
            if audio_b64:
                parts.append(
                    {
                        "type": "input_audio",
                        "input_audio": {"data": audio_b64, "format": str(vb.get("audio_format") or "mp3")},
                    }
                )
        parts.append({"type": "text", "text": user_final})
        assembled_msgs.append({"role": "user", "content": parts})
    else:
        assembled_msgs.append({"role": "user", "content": user_final})

    if an_enabled and an_text and an_depth == 0:
        assembled_msgs.append({"role": an_role if an_role in ("system", "user", "assistant") else "system", "content": f"【导演备注】{an_text}"})

    total_est = sum(
        estimate_tokens(m["content"] if isinstance(m["content"], str) else " ".join(p.get("text", "") for p in m["content"] if p.get("type") == "text"))
        for m in assembled_msgs
    )

    def _summarize_assembled_content(c: Any) -> str:
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            n_img = sum(1 for p in c if isinstance(p, dict) and p.get("type") == "image_url")
            n_aud = sum(1 for p in c if isinstance(p, dict) and p.get("type") == "input_audio")
            txts = [str(p.get("text") or "") for p in c if isinstance(p, dict) and p.get("type") == "text"]
            last_txt = txts[-1] if txts else ""
            aud_note = f", {n_aud} 段音频" if n_aud else ""
            return f"[多模态消息: {n_img} 张图片{aud_note}] {last_txt}".strip()
        return str(c or "")

    log_snap = {
        "timestamp": time.time(),
        "model": model_id,
        "estimated_context_tokens": total_est,
        "immutable_prefix_tokens": estimate_tokens(static_system_text),
        "history_turns_included": len(selected_history),
        "history_turns_total": len(history_messages),
        "triggered_worldbooks": wb_res["triggered_logs"],
        "applied_regex": applied_rx,
        "assembled_messages": [
            {
                "role": m["role"],
                "content": _summarize_assembled_content(m["content"]),
            }
            for m in assembled_msgs
        ],
    }
    return assembled_msgs, log_snap, resolved_turn_imgs
