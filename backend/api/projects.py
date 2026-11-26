# -*- coding: utf-8 -*-
"""Projects (Game Cards), Explore Flagship Campaigns, Worldbook Import, and Card Export/Import."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile

from backend.config import WORLDBOOK_TEMPLATE_JSON, normalize_project_schema, normalize_worldbook_item
from backend.content.catalog import EXPLORE_PRESET_APPS
from backend.core.auth import get_current_user
from backend.core.card_codec import (
    extract_png_card_json,
    project_to_st_card_v3,
    render_game_card_poster_png,
    st_card_to_project,
)
from backend.core.media import auto_save_to_gallery
from backend.core.security import sanitize_id
from backend.core.variables import interpolate_variables
from backend.storage.db import get_user_db
from backend.trpg.state_engine import empty_game_state

router = APIRouter()


@router.get("/api/projects")
def get_projects(username: str = Depends(get_current_user)):
    db = get_user_db(username)
    return db.list_projects()


@router.get("/api/projects/{project_id}")
def get_project(project_id: str, username: str = Depends(get_current_user)):
    db = get_user_db(username)
    pid = sanitize_id(project_id)
    proj = db.get_project(pid)
    if not proj:
        raise HTTPException(status_code=404, detail="剧本不存在")
    return proj


@router.post("/api/projects")
def save_project(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    db = get_user_db(username)
    pid = sanitize_id(payload.get("id") or f"proj_{uuid.uuid4().hex[:8]}")
    payload = dict(payload)
    payload["id"] = pid
    saved = db.save_project(payload)
    s = db.get_settings()
    if not s.get("active_project_id"):
        s["active_project_id"] = pid
        db.save_settings(s)
    return {"status": "ok", "project": saved}


@router.delete("/api/projects/{project_id}")
def delete_project(project_id: str, username: str = Depends(get_current_user)):
    pid = sanitize_id(project_id)
    if pid in ("proj_fast_trpg", "proj_default", "proj_free_chat"):
        raise HTTPException(status_code=400, detail="默认剧本不可删除")
    db = get_user_db(username)
    db.delete_project(pid)
    s = db.get_settings()
    if s.get("active_project_id") == pid:
        s["active_project_id"] = "proj_default"
        db.save_settings(s)
    return {"status": "ok"}


@router.post("/api/projects/fork")
def fork_project(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    db = get_user_db(username)
    src_id = sanitize_id(payload.get("project_id") or payload.get("id"))
    src = db.get_project(src_id)
    if not src:
        src = next((a for a in EXPLORE_PRESET_APPS if a["id"] == src_id), None)
    if not src:
        raise HTTPException(status_code=404, detail="源剧本不存在")
    forked = dict(src)
    forked["id"] = f"proj_{uuid.uuid4().hex[:8]}"
    forked["name"] = payload.get("name") or f"{src['name']} (副本)"
    saved = db.save_project(forked)
    return {"status": "ok", "project": saved}


@router.get("/api/explore")
def list_explore_apps(request: Request, category: Optional[str] = None, q: Optional[str] = None):
    username = get_current_user(request)
    db = get_user_db(username)
    user_projects = [{**p, "_is_user_project": True} for p in db.list_projects()]
    results = list(EXPLORE_PRESET_APPS)
    if category and category != "全部":
        results = [a for a in results if a.get("category") == category]
    if q and q.strip():
        kw = q.strip().lower()
        results = [
            a for a in results
            if kw in a.get("name", "").lower()
            or kw in a.get("description", "").lower()
            or any(kw in t.lower() for t in a.get("tags", []))
        ]
    return {
        "status": "ok",
        "categories": ["全部", "我的剧本", "奇幻冒险", "悬疑克苏鲁", "古风仙侠", "赛博朋克", "TRPG跑团"],
        "user_projects": user_projects,
        "apps": results,
    }


@router.get("/api/explore/cg_preview/{cg_key}")
def get_explore_cg_preview(cg_key: str):
    title = cg_key.replace("_", " ")
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="#181a1f"/><stop offset="100%" stop-color="#2c2419"/></linearGradient></defs>'
        f'<rect width="800" height="450" fill="url(#g)"/>'
        f'<text x="40" y="380" fill="#d4a359" font-size="28" font-family="sans-serif">{title}</text></svg>'
    )
    return Response(content=svg, media_type="image/svg+xml")


@router.post("/api/explore/install")
def install_explore_app(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    app_id = str(payload.get("app_id") or "")
    template = next((a for a in EXPLORE_PRESET_APPS if a["id"] == app_id), None)
    if not template:
        raise HTTPException(status_code=404, detail="剧本模板不存在")

    db = get_user_db(username)
    saved_proj = db.save_project(template)

    # Install bundled character cards if not already present
    existing_card_names = {c.get("name") for c in db.list_cards()}
    installed_card_ids: List[str] = []
    for bc in template.get("bundled_cards") or []:
        if isinstance(bc, dict) and bc.get("name"):
            if bc["name"] not in existing_card_names:
                saved_c = db.save_card(bc)
                installed_card_ids.append(saved_c["id"])
            else:
                match_c = next((c for c in db.list_cards() if c.get("name") == bc["name"]), None)
                if match_c:
                    installed_card_ids.append(match_c["id"])

    s = db.get_settings()
    s["active_project_id"] = saved_proj["id"]
    db.save_settings(s)

    existing_chats = db.list_chats(project_id=saved_proj["id"])
    if existing_chats:
        chat_id = existing_chats[0]["id"]
    else:
        chat_id = uuid.uuid4().hex[:8]
        group_cfg = {"enabled": False, "members": [], "mode": "round_robin"}
        gd = template.get("group_defaults") or {}
        if gd.get("enabled") and installed_card_ids:
            group_cfg = {
                "enabled": True,
                "mode": gd.get("mode", "round_robin"),
                "members": [
                    {"card_id": cid, "enabled": True, "talkativeness": 0.7}
                    for cid in installed_card_ids
                ],
            }
        init_msgs = []
        ogs = saved_proj.get("opening_greetings") or []
        init_state = empty_game_state(saved_proj.get("initial_state"))
        if ogs and payload.get("with_opening", True):
            rendered = interpolate_variables(ogs[0]["content"], saved_proj.get("prompt_variables", []), {})
            init_msgs.append(
                {
                    "id": "msg_open_" + uuid.uuid4().hex[:6],
                    "role": "assistant",
                    "content": rendered,
                    "prompt_content": rendered,
                    "state_snapshot": init_state,
                    "is_opening": True,
                    "timestamp": time.time(),
                }
            )
        db.create_chat(
            chat_id=chat_id,
            project_id=saved_proj["id"],
            title=saved_proj["name"],
            model=s.get("model", ""),
            initial_state=init_state,
            group_config=group_cfg,
            init_messages=init_msgs,
        )

    return {"status": "ok", "project": saved_proj, "chat_id": chat_id}


@router.get("/api/worldbook/template")
def get_worldbook_template():
    return WORLDBOOK_TEMPLATE_JSON


@router.post("/api/projects/{project_id}/worldbook/import")
def import_worldbook(project_id: str, payload: Dict[str, Any], username: str = Depends(get_current_user)):
    db = get_user_db(username)
    pid = sanitize_id(project_id)
    proj = db.get_project(pid)
    if not proj:
        raise HTTPException(status_code=404, detail="剧本不存在")

    raw_wb = payload.get("world_book") if isinstance(payload.get("world_book"), list) else (
        list((payload.get("entries") or {}).values()) if isinstance(payload.get("entries"), dict) else []
    )
    if not raw_wb:
        raise HTTPException(status_code=400, detail="未检测到有效世界书条目")
    mode = str(payload.get("mode") or "append")
    existing = [] if mode == "replace" else list(proj.get("world_book") or [])
    base_idx = len(existing)
    for i, item in enumerate(raw_wb):
        norm = normalize_worldbook_item(item, base_idx + i)
        if norm:
            existing.append(norm)
    proj["world_book"] = existing
    saved = db.save_project(proj)
    return {"status": "ok", "count": len(existing), "project": saved}


@router.get("/api/projects/{project_id}/export_card")
def export_project_card(project_id: str, format: str = "png", username: str = Depends(get_current_user)):
    db = get_user_db(username)
    proj = db.get_project(sanitize_id(project_id))
    if not proj:
        raise HTTPException(status_code=404, detail="游戏卡不存在")
    safe_fn = quote(f"{proj.get('name', 'card')}.{'json' if format == 'json' else 'png'}")
    if format.lower() == "json":
        raw_bytes = json.dumps(project_to_st_card_v3(proj), ensure_ascii=False, indent=2).encode("utf-8")
        return Response(content=raw_bytes, media_type="application/json", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_fn}"})
    png_bytes = render_game_card_poster_png(proj, username)
    return Response(content=png_bytes, media_type="image/png", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_fn}"})


@router.post("/api/projects/export_draft_card")
def export_draft_card(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    fmt = str(payload.get("format") or "png").lower()
    proj = normalize_project_schema(payload.get("project") or payload)
    safe_fn = quote(f"{proj.get('name', 'draft')}.{'json' if fmt == 'json' else 'png'}")
    if fmt == "json":
        raw_bytes = json.dumps(project_to_st_card_v3(proj), ensure_ascii=False, indent=2).encode("utf-8")
        return Response(content=raw_bytes, media_type="application/json", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_fn}"})
    png_bytes = render_game_card_poster_png(proj, username)
    return Response(content=png_bytes, media_type="image/png", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_fn}"})


@router.post("/api/projects/import_card")
async def import_project_card(file: UploadFile = File(...), username: str = Depends(get_current_user)):
    raw = await file.read()
    fname = (file.filename or "").lower()
    cover_url = ""
    if fname.endswith(".png") or raw.startswith(b"\x89PNG"):
        card_json = extract_png_card_json(raw)
        import base64
        b64 = "data:image/png;base64," + base64.b64encode(raw).decode("utf-8")
        gid = auto_save_to_gallery(username, b64, file.filename, "导入封面")
        cover_url = f"/api/gallery/image/{gid}" if gid else ""
    else:
        card_json = json.loads(raw.decode("utf-8-sig"))
    db = get_user_db(username)
    proj = st_card_to_project(card_json, cover_url, global_defaults=db.get_settings())
    proj["id"] = f"proj_{uuid.uuid4().hex[:8]}"
    saved = db.save_project(proj)
    return {"status": "ok", "project": saved}
