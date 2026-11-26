# -*- coding: utf-8 -*-
"""KV-Cache-aware Worldbook (Lorebook) & CG Book evaluator."""
from __future__ import annotations

import logging
import random
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.config import normalize_worldbook_item, safe_float, safe_int
from backend.core.variables import interpolate_variables

logger = logging.getLogger("easy_trpg.worldbook")

_THINK_BLOCK_RE = re.compile(r"<think(?:ing)?>[\s\S]*?</think(?:ing)?>", re.IGNORECASE)


def _strip_thinking_light(text: str) -> str:
    return _THINK_BLOCK_RE.sub("", text or "").strip()


def _extract_msg_plain_text(m: Dict[str, Any]) -> str:
    c = m.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(str(p.get("text") or "") for p in c if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _match_wb_single_key(key: str, haystack: str, haystack_low: str, case_sensitive: bool, force_regex: bool) -> bool:
    k = str(key or "").strip()
    if not k:
        return False
    if force_regex or (k.startswith("/") and len(k) > 2 and k.rfind("/") > 0):
        pat = k
        flags = 0 if case_sensitive else re.IGNORECASE
        if pat.startswith("/") and pat.rfind("/") > 0:
            ls = pat.rfind("/")
            fstr = pat[ls + 1:]
            pat = pat[1:ls]
            if "i" in fstr:
                flags |= re.IGNORECASE
            if "m" in fstr:
                flags |= re.MULTILINE
        try:
            return bool(re.search(pat, haystack, flags))
        except re.error:
            return False
    if case_sensitive:
        return k in haystack
    return k.lower() in haystack_low


def evaluate_world_book_layered(
    project_data: Dict[str, Any],
    history_messages: List[Dict[str, Any]],
    current_user_text: str,
    *,
    chat_inputs: Optional[Dict[str, Any]] = None,
    visited_wb_ids: Optional[List[str]] = None,
    default_scan_depth: int = 5,
    user_name: str = "玩家",
    char_name: str = "",
) -> Dict[str, Any]:
    """
    Evaluate Worldbook separating CONSTANT entries (Layer 0 immutable prefix)
    from DYNAMIC entries (Layer 2 dynamic tail, preserving KV-cache!).
    """
    raw_wb = project_data.get("world_book") or []
    if not raw_wb:
        return {
            "constant_system": [],
            "dynamic_system": [],
            "prefix": [],
            "suffix": [],
            "triggered_logs": [],
        }

    norm_items: List[Dict[str, Any]] = []
    for idx, raw in enumerate(raw_wb):
        item = normalize_worldbook_item(raw, idx)
        if item and item.get("enabled", True) is not False:
            norm_items.append(item)

    norm_items.sort(key=lambda x: safe_int(x.get("sort"), 100))
    prompt_vars = project_data.get("prompt_variables") or []
    default_scan = max(0, min(50, safe_int(default_scan_depth, 5)))

    constant_system: List[str] = []
    dynamic_system: List[str] = []
    pre_injections: List[str] = []
    suf_injections: List[str] = []
    triggered_logs: List[Dict[str, Any]] = []

    matched_ids: set[str] = set()
    recursion_buffer: List[str] = []

    for pass_idx in range(4):
        newly_triggered = False
        for item in norm_items:
            iid = str(item["id"])
            if iid in matched_ids:
                continue
            if pass_idx > 0 and item.get("exclude_recursion"):
                continue

            is_constant = bool(item.get("constant", False))
            keys = list(item.get("keys") or [])
            if not is_constant and not keys:
                continue

            depth_turns = safe_int(item.get("scan_depth", item.get("depth", default_scan)), default_scan)
            depth_turns = max(0, min(50, depth_turns))
            msg_slice = history_messages[-(depth_turns * 2):] if depth_turns > 0 else []
            key_region = safe_int(item.get("key_region", 6), 6)

            scan_chunks: List[str] = []
            if pass_idx == 0:
                if key_region & 1:
                    scan_chunks.append(str(project_data.get("system_prompt") or ""))
                if (key_region & 2) or (key_region & 16):
                    scan_chunks.append(str(current_user_text or ""))
                    for m in msg_slice:
                        if isinstance(m, dict) and m.get("role") == "user":
                            scan_chunks.append(_extract_msg_plain_text(m))
                if (key_region & 4) or (key_region & 8):
                    for m in msg_slice:
                        if isinstance(m, dict) and m.get("role") == "assistant":
                            scan_chunks.append(_strip_thinking_light(_extract_msg_plain_text(m)))
            else:
                scan_chunks.extend(recursion_buffer)

            haystack = "\n".join(c for c in scan_chunks if c)
            if not haystack.strip() and not (is_constant and pass_idx == 0):
                continue
            haystack_low = haystack.lower()
            case_sens = bool(item.get("case_sensitive", False))

            raw_mt = item.get("match_type", 2)
            if isinstance(raw_mt, str):
                u = raw_mt.strip().upper()
                match_type = 1 if u in ("1", "AND") else (3 if u in ("3", "REGEX") else 2)
            else:
                match_type = safe_int(raw_mt, 2)

            matched = False
            matched_kw = ""
            if is_constant and pass_idx == 0:
                matched = True
                matched_kw = "常驻"
            elif match_type == 1:
                if keys and all(_match_wb_single_key(k, haystack, haystack_low, case_sens, False) for k in keys):
                    matched = True
                    matched_kw = " & ".join(keys)
            elif match_type == 2:
                for k in keys:
                    if _match_wb_single_key(k, haystack, haystack_low, case_sens, False):
                        matched = True
                        matched_kw = k
                        break
            elif match_type == 3:
                for k in keys:
                    if _match_wb_single_key(k, haystack, haystack_low, case_sens, True):
                        matched = True
                        matched_kw = k
                        break

            sec_keys = item.get("secondary_keys") or []
            if matched and not is_constant and sec_keys and item.get("selective", True):
                hits = [_match_wb_single_key(sk, haystack, haystack_low, case_sens, False) for sk in sec_keys]
                sel_logic = safe_int(item.get("selective_logic", 0), 0)
                if sel_logic == 0 and not any(hits):
                    matched = False
                elif sel_logic == 1 and all(hits):
                    matched = False
                elif sel_logic == 2 and any(hits):
                    matched = False
                elif sel_logic == 3 and not all(hits):
                    matched = False

            if not matched:
                continue

            prob = max(0, min(100, safe_int(item.get("probability", 100), 100)))
            if prob <= 0 or (prob < 100 and random.randint(1, 100) > prob):
                continue

            chosen = ""
            if safe_int(item.get("value_type", 0), 0) == 1:
                cfgs = [
                    c for c in (item.get("value_configs") or [])
                    if isinstance(c, dict) and c.get("value") and safe_float(c.get("probability", c.get("weight")), 0.0) > 0
                ]
                if cfgs:
                    weights = [safe_float(c.get("probability", c.get("weight")), 10.0) for c in cfgs]
                    chosen = str(random.choices(cfgs, weights=weights, k=1)[0].get("value") or "")
            if not chosen:
                chosen = str(item.get("content") or item.get("value") or "")
            chosen = interpolate_variables(chosen.strip(), prompt_vars, chat_inputs, user_name=user_name, char_name=char_name)
            if not chosen:
                continue

            matched_ids.add(iid)
            newly_triggered = True
            recursion_buffer.append(chosen)
            if visited_wb_ids is not None and iid not in visited_wb_ids:
                visited_wb_ids.append(iid)

            raw_vr = item.get("value_region", 1)
            if isinstance(raw_vr, str):
                vru = raw_vr.strip().upper()
                val_region = int(vru) if vru.isdigit() else (2 if vru == "PREFIX" else (4 if vru == "SUFFIX" else 1))
            else:
                val_region = safe_int(raw_vr, 1) or 1

            target_names: List[str] = []
            if (val_region & 1) or (val_region & 8) or (val_region & 16):
                if is_constant or item.get("force_system_top"):
                    constant_system.append(chosen)
                    target_names.append("常驻系统前缀")
                else:
                    dynamic_system.append(chosen)
                    target_names.append("动态尾部世界书")
            if val_region & 2:
                pre_injections.append(chosen)
                target_names.append("前置词")
            if val_region & 4:
                suf_injections.append(chosen)
                target_names.append("后置词")

            triggered_logs.append(
                {
                    "id": iid,
                    "name": item.get("name"),
                    "group": item.get("group"),
                    "keys": keys,
                    "constant": is_constant,
                    "matched_keyword": matched_kw if pass_idx == 0 else f"{matched_kw} (级联#{pass_idx})",
                    "target_regions": target_names,
                    "content_preview": chosen[:160] + ("..." if len(chosen) > 160 else ""),
                }
            )
        if not newly_triggered:
            break

    return {
        "constant_system": constant_system,
        "dynamic_system": dynamic_system,
        "prefix": pre_injections,
        "suffix": suf_injections,
        "triggered_logs": triggered_logs,
    }


def evaluate_world_book(
    project_data: Dict[str, Any],
    history_messages: List[Dict[str, Any]],
    current_user_text: str,
    system_prompt: str = "",
    prefix: str = "",
    suffix: str = "",
    chat_inputs: Optional[Dict[str, Any]] = None,
    visited_wb_ids: Optional[List[str]] = None,
    default_scan_depth: int = 5,
) -> Tuple[str, str, str, List[Dict[str, Any]]]:
    """Backwards-compatible wrapper around layered Worldbook evaluation."""
    res = evaluate_world_book_layered(
        project_data=project_data,
        history_messages=history_messages,
        current_user_text=current_user_text,
        chat_inputs=chat_inputs,
        visited_wb_ids=visited_wb_ids,
        default_scan_depth=default_scan_depth,
    )
    sys_parts = [system_prompt] if system_prompt else []
    all_sys = res["constant_system"] + res["dynamic_system"]
    if all_sys:
        sys_parts.append("【动态触发的世界书设定 (Worldbook Lore)】\n" + "\n\n".join(all_sys))
    final_sys = "\n\n".join(p for p in sys_parts if p).strip()
    final_pre = "\n".join(res["prefix"] + ([prefix] if prefix else [])).strip()
    final_suf = "\n".join(([suffix] if suffix else []) + res["suffix"]).strip()
    return final_sys, final_pre, final_suf, res["triggered_logs"]


def evaluate_cg_book(
    project_data: Dict[str, Any],
    text_to_scan: str,
    ai_only_text: str = "",
) -> Tuple[List[Dict[str, Any]], bool]:
    cg_list = project_data.get("cg_book") or []
    if not isinstance(cg_list, list) or not cg_list or not (text_to_scan or ai_only_text):
        return [], False
    unlocked: List[Dict[str, Any]] = []
    override_bg = False
    for idx, cg in enumerate(cg_list):
        if not isinstance(cg, dict) or cg.get("enabled") is False:
            continue
        keys = cg.get("keys") or cg.get("key") or []
        if isinstance(keys, str):
            keys = [k.strip() for k in re.split(r"[,，;；\n]+", keys) if k.strip()]
        if not keys:
            continue
        ai_only = bool(cg.get("ai_only", True))
        haystack = ai_only_text if ai_only else text_to_scan
        hay_low = haystack.lower()
        mt = safe_int(cg.get("match_type", 2), 2)
        hit = all(k.lower() in hay_low for k in keys) if mt == 1 else any(k.lower() in hay_low for k in keys)
        if hit and (cg.get("image") or cg.get("url")):
            img = cg.get("image") or cg.get("url")
            unlocked.append(
                {
                    "id": str(cg.get("id") or f"cg_{idx}"),
                    "title": str(cg.get("title") or cg.get("name") or f"CG #{idx+1}"),
                    "image": img,
                    "display_mode": str(cg.get("display_mode") or "inline"),
                }
            )
            if str(cg.get("display_mode") or "") == "background":
                override_bg = True
    return unlocked, override_bg
