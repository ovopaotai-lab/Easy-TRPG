# -*- coding: utf-8 -*-
"""Deterministic TRPG GameState machine with <state_patch> & legacy <status> fallback."""
from __future__ import annotations

import copy
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.config import safe_int

logger = logging.getLogger("easy_trpg.state")

GameState = Dict[str, Any]

_STATE_PATCH_RE = re.compile(r"<state_patch>\s*([\s\S]*?)\s*</state_patch>", re.IGNORECASE)
_STATUS_TAG_RE = re.compile(r"<status(?:\s+[^>]*)?>([\s\S]*?)</status>|＜status＞([\s\S]*?)＜/status＞", re.IGNORECASE)


def empty_game_state(initial: Optional[Dict[str, Any]] = None) -> GameState:
    base: GameState = {
        "resources": [],
        "attributes": {},
        "equipment": {},
        "inventory": [],
        "npcs": [],
        "quests": [],
        "clocks": [],
        "scene": {"time": "", "location": "", "condition": ""},
    }
    if isinstance(initial, dict):
        for k in base:
            if k in initial and initial[k] is not None:
                base[k] = copy.deepcopy(initial[k])
    return base


def extract_state_patch_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    m = _STATE_PATCH_RE.search(text)
    if not m:
        return None
    raw = m.group(1).strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I).strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError as exc:
        logger.debug("Invalid <state_patch> JSON ignored: %s", exc)
        return None


def strip_state_patch_tags(text: str) -> str:
    return _STATE_PATCH_RE.sub("", text or "").strip()


def apply_state_patch(prev_state: Optional[GameState], patch: Optional[Dict[str, Any]]) -> GameState:
    """Apply deterministic atomic operations onto a cloned GameState."""
    st = empty_game_state(prev_state)
    if not patch or not isinstance(patch, dict):
        return st

    # 1. Resources delta / set (supports dict {"hp": -10} or list)
    res_list: List[Dict[str, Any]] = list(st.get("resources") or [])
    res_by_key = {str(r.get("key") or r.get("label")): r for r in res_list if isinstance(r, dict)}

    for key, delta in (patch.get("resources_delta") or {}).items() if isinstance(patch.get("resources_delta"), dict) else []:
        r = res_by_key.get(str(key))
        if r is None:
            r = {"key": str(key), "label": str(key), "current": 100, "max": 100}
            res_list.append(r)
            res_by_key[str(key)] = r
        new_val = safe_int(r.get("current"), 0) + safe_int(delta, 0)
        mx = safe_int(r.get("max"), 0)
        if mx > 0:
            new_val = max(0, min(mx, new_val))
        else:
            new_val = max(0, new_val)
        r["current"] = new_val

    for key, val in (patch.get("resources_set") or {}).items() if isinstance(patch.get("resources_set"), dict) else []:
        r = res_by_key.get(str(key))
        if r is None:
            r = {"key": str(key), "label": str(key), "current": 0, "max": 100}
            res_list.append(r)
            res_by_key[str(key)] = r
        if isinstance(val, dict):
            if "current" in val:
                r["current"] = safe_int(val["current"], r.get("current", 0))
            if "max" in val:
                r["max"] = safe_int(val["max"], r.get("max", 100))
            if "label" in val:
                r["label"] = str(val["label"])
        else:
            r["current"] = safe_int(val, r.get("current", 0))
    st["resources"] = res_list

    # 2. Attributes
    attrs = dict(st.get("attributes") or {})
    if isinstance(patch.get("attrs_set"), dict):
        for k, v in patch["attrs_set"].items():
            attrs[str(k)] = v
    st["attributes"] = attrs

    # 3. Equipment
    equip = dict(st.get("equipment") or {})
    if isinstance(patch.get("equip"), dict):
        for slot, item_info in patch["equip"].items():
            if isinstance(item_info, dict):
                equip[str(slot)] = {"name": str(item_info.get("name") or ""), "desc": str(item_info.get("desc") or "")}
            else:
                equip[str(slot)] = {"name": str(item_info), "desc": ""}
    for slot in (patch.get("unequip") or []) if isinstance(patch.get("unequip"), list) else []:
        equip.pop(str(slot), None)
    st["equipment"] = equip

    # 4. Inventory
    inv: List[Dict[str, Any]] = [dict(x) for x in (st.get("inventory") or []) if isinstance(x, dict)]
    inv_map = {str(x.get("name")): x for x in inv if x.get("name")}
    for add_item in (patch.get("inv_add") or []) if isinstance(patch.get("inv_add"), list) else []:
        if isinstance(add_item, str):
            add_item = {"name": add_item, "qty": 1, "desc": ""}
        if not isinstance(add_item, dict) or not add_item.get("name"):
            continue
        nm = str(add_item["name"]).strip()
        qty = max(1, safe_int(add_item.get("qty"), 1))
        if nm in inv_map:
            inv_map[nm]["qty"] = safe_int(inv_map[nm].get("qty"), 0) + qty
            if add_item.get("desc"):
                inv_map[nm]["desc"] = str(add_item["desc"])
        else:
            entry = {"name": nm, "qty": qty, "desc": str(add_item.get("desc") or "")}
            inv.append(entry)
            inv_map[nm] = entry

    for rem_item in (patch.get("inv_remove") or []) if isinstance(patch.get("inv_remove"), list) else []:
        if isinstance(rem_item, str):
            rem_name, rem_qty = rem_item.strip(), 1
        elif isinstance(rem_item, dict):
            rem_name = str(rem_item.get("name") or "").strip()
            rem_qty = max(1, safe_int(rem_item.get("qty"), 1))
        else:
            continue
        if rem_name in inv_map:
            inv_map[rem_name]["qty"] = safe_int(inv_map[rem_name].get("qty"), 1) - rem_qty
    st["inventory"] = [x for x in inv if safe_int(x.get("qty"), 0) > 0]

    # 5. NPCs
    npcs = [dict(x) for x in (st.get("npcs") or []) if isinstance(x, dict)]
    npc_map = {str(n.get("name")): n for n in npcs if n.get("name")}
    for nup in (patch.get("npc_upsert") or []) if isinstance(patch.get("npc_upsert"), list) else []:
        if not isinstance(nup, dict) or not nup.get("name"):
            continue
        nm = str(nup["name"]).strip()
        if nm in npc_map:
            if "affinity_delta" in nup:
                npc_map[nm]["affinity"] = max(0, min(100, safe_int(npc_map[nm].get("affinity"), 50) + safe_int(nup["affinity_delta"], 0)))
            for fld in ("relation", "status", "mood", "notes", "affinity"):
                if fld in nup:
                    npc_map[nm][fld] = nup[fld]
        else:
            entry = {
                "name": nm,
                "affinity": safe_int(nup.get("affinity"), 50),
                "relation": str(nup.get("relation") or "中立"),
                "status": str(nup.get("status") or ""),
                "mood": str(nup.get("mood") or ""),
                "notes": str(nup.get("notes") or ""),
            }
            npcs.append(entry)
            npc_map[nm] = entry
    st["npcs"] = npcs

    # 6. Quests
    quests = [dict(x) for x in (st.get("quests") or []) if isinstance(x, dict)]
    q_map = {str(q.get("title")): q for q in quests if q.get("title")}
    for qup in (patch.get("quest_upsert") or []) if isinstance(patch.get("quest_upsert"), list) else []:
        if not isinstance(qup, dict) or not qup.get("title"):
            continue
        qt = str(qup["title"]).strip()
        if qt in q_map:
            q_map[qt].update(qup)
        else:
            nq = {"title": qt, "status": str(qup.get("status") or "进行中"), "progress": str(qup.get("progress") or "")}
            quests.append(nq)
            q_map[qt] = nq
    st["quests"] = quests

    # 7. Clocks (PbtA / Blades in the Dark progress/threat clocks)
    clocks = [dict(x) for x in (st.get("clocks") or []) if isinstance(x, dict)]
    clk_map = {str(c.get("name")): c for c in clocks if c.get("name")}
    for c_name, delta in (patch.get("clock_delta") or {}).items() if isinstance(patch.get("clock_delta"), dict) else []:
        c = clk_map.get(str(c_name))
        if c is None:
            c = {"name": str(c_name), "current": 0, "max": 6, "kind": "threat"}
            clocks.append(c)
            clk_map[str(c_name)] = c
        c["current"] = max(0, min(safe_int(c.get("max"), 6), safe_int(c.get("current"), 0) + safe_int(delta, 0)))
    st["clocks"] = clocks

    # 8. Scene
    scene = dict(st.get("scene") or {"time": "", "location": "", "condition": ""})
    if isinstance(patch.get("scene_set"), dict):
        for k, v in patch["scene_set"].items():
            scene[str(k)] = str(v)
    st["scene"] = scene

    return st


def parse_legacy_status_into_state(prev_state: Optional[GameState], ai_text: str) -> Optional[GameState]:
    """Backwards-compat parser: extract <status>[栏位]...</status> into structured GameState."""
    m = _STATUS_TAG_RE.search(ai_text or "")
    if not m:
        return None
    body = (m.group(1) or m.group(2) or "").strip()
    if not body:
        return None

    st = empty_game_state(prev_state)
    section = ""
    new_resources: List[Dict[str, Any]] = []
    new_equip: Dict[str, Any] = {}
    new_inv: List[Dict[str, Any]] = []
    new_npcs: List[Dict[str, Any]] = []
    cur_npc: Optional[Dict[str, Any]] = None

    for raw_line in body.splitlines():
        ln = raw_line.strip()
        if not ln:
            continue
        sec_m = re.match(r"^\[([^\]]+)\]$", ln)
        if sec_m:
            section = sec_m.group(1).strip()
            continue

        if "物品" in section or "背包" in section:
            if "暂无" in ln:
                continue
            im = re.match(r"^(.+?)(?:\(([^)]*)\))?\s*[x×]\s*(\d+)$", ln, re.I)
            if im:
                qty = int(im.group(3))
                if qty > 0:
                    new_inv.append({"name": im.group(1).strip(), "desc": (im.group(2) or "").strip(), "qty": qty})
            else:
                new_inv.append({"name": ln, "desc": "", "qty": 1})
            continue

        if ":" in ln or "：" in ln:
            k, v = re.split(r"[:：]", ln, maxsplit=1)
            k, v = k.strip(), v.strip()
            if "装备" in section:
                if v and v not in ("无", "暂无"):
                    new_equip[k] = {"name": v, "desc": ""}
            elif "角色" in section or "关系" in section:
                if k in ("角色", "姓名", "人物"):
                    cur_npc = {"name": v, "affinity": 50, "relation": "", "status": "", "mood": "", "notes": ""}
                    new_npcs.append(cur_npc)
                elif cur_npc is not None:
                    if k in ("好感", "好感度"):
                        num_m = re.search(r"(\d+)", v)
                        if num_m:
                            cur_npc["affinity"] = int(num_m.group(1))
                    elif k in ("态度", "关系"):
                        cur_npc["relation"] = v
                    elif k in ("动态", "状态"):
                        cur_npc["status"] = v
                    else:
                        cur_npc["notes"] = f"{k}: {v}"
            else:
                frac = re.match(r"^(\d+)\s*/\s*(\d+)", v)
                if frac:
                    new_resources.append({"key": k, "label": k, "current": int(frac.group(1)), "max": int(frac.group(2))})
                else:
                    st["attributes"][k] = v

    if new_resources:
        st["resources"] = new_resources
    if new_equip:
        st["equipment"] = new_equip
    if "物品" in section or new_inv:
        st["inventory"] = new_inv
    if new_npcs:
        st["npcs"] = new_npcs
    return st


def apply_ai_output_to_state(prev_state: Optional[GameState], ai_text: str) -> Tuple[GameState, Optional[Dict[str, Any]]]:
    patch = extract_state_patch_json(ai_text)
    if patch is not None:
        return apply_state_patch(prev_state, patch), patch
    legacy = parse_legacy_status_into_state(prev_state, ai_text)
    if legacy is not None:
        return legacy, None
    return empty_game_state(prev_state), None


def format_compact_state_for_prompt(state: Optional[GameState]) -> str:
    if not state:
        return ""
    lines: List[str] = []
    res = [f"{r.get('label', r.get('key'))}: {r.get('current')}/{r.get('max')}" for r in (state.get("resources") or []) if isinstance(r, dict)]
    if res:
        lines.append("数值: " + " | ".join(res))
    attrs = state.get("attributes") or {}
    if attrs:
        lines.append("属性: " + " | ".join(f"{k}={v}" for k, v in list(attrs.items())[:8]))
    clocks = [f"{c.get('name')} {c.get('current')}/{c.get('max')}" for c in (state.get("clocks") or []) if isinstance(c, dict)]
    if clocks:
        lines.append("进度时钟: " + " | ".join(clocks))
    equip = state.get("equipment") or {}
    if equip:
        eq_s = ", ".join(f"{k}:{(v.get('name') if isinstance(v, dict) else v)}" for k, v in equip.items())
        lines.append("装备: " + eq_s)
    inv = state.get("inventory") or []
    if inv:
        inv_s = ", ".join(f"{it.get('name')}x{it.get('qty', 1)}" for it in inv if isinstance(it, dict))
        lines.append("物品: " + inv_s)
    npcs = state.get("npcs") or []
    if npcs:
        npc_s = "; ".join(f"{n.get('name')}({n.get('relation', '')}, 好感{n.get('affinity', 50)})" for n in npcs[:6] if isinstance(n, dict))
        lines.append("关系: " + npc_s)
    scene = state.get("scene") or {}
    sc_parts = [str(scene.get(k) or "") for k in ("time", "location", "condition") if scene.get(k)]
    if sc_parts:
        lines.append("现场: " + " / ".join(sc_parts))
    if not lines:
        return ""
    return "【当前确定性状态快照（由引擎维护）】\n" + "\n".join(lines)
