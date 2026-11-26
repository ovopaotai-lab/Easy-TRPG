# -*- coding: utf-8 -*-
"""Model discovery, local engine lifecycle, HF-Mirror downloader, and connectivity test routes."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, Depends, HTTPException

from backend.config import MODEL_DIR, MODELS_DIR
from backend.core.auth import get_current_user
from backend.core.security import native_pick_path, open_directory_safely, require_loopback
from backend.engines.hardware import get_hardware_snapshot_async
from backend.engines.supervisor import (
    HF_DOWNLOAD_TASKS,
    HF_PRESET_CATALOG,
    build_hf_catalog_with_status,
    discover_local_models,
    load_saved_custom_model_paths,
    save_custom_model_paths,
    shutdown_local_engines,
    start_hf_download,
)
from backend.providers.router import (
    fetch_remote_models,
    test_model_connectivity,
)
from backend.storage.db import get_user_db

router = APIRouter()


@router.get("/api/models")
async def get_available_models(username: str = Depends(get_current_user)):
    db = get_user_db(username)
    settings = db.get_settings()
    local_models = await discover_local_models(settings)
    remote = await fetch_remote_models(settings)
    hw = await get_hardware_snapshot_async(use_cache=True)

    custom_models = [str(m).strip() for m in (settings.get("custom_models") or []) if str(m).strip()]
    all_remote = list(dict.fromkeys(custom_models + remote["models"]))
    favorites = list(settings.get("favorite_models") or [])

    pricing_map: Dict[str, Any] = {}
    for lm in local_models:
        pricing_map[lm["id"]] = {
            "id": lm["id"],
            "billing_type": "local",
            "short_price": "免费",
            "detail_price": lm.get("source_label", "本地"),
            "description": lm.get("description", ""),
            "groups": ["local"],
        }

    return {
        "models": all_remote,
        "local_models": local_models,
        "favorites": favorites,
        "favorite_models": favorites,
        "pricing": pricing_map,
        "remote_error": remote["error"],
        "used_direct_fallback": remote["used_direct_fallback"],
        "protocol": remote.get("protocol", "auto"),
        "hardware": hw,
    }


@router.post("/api/models/test")
async def test_model_endpoint(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    model_id = str(payload.get("model") or "").strip()
    if not model_id:
        raise HTTPException(status_code=400, detail="请先选择模型")
    db = get_user_db(username)
    settings = db.get_settings()
    # Allow testing unsaved base_url/api_key/protocol directly from onboarding/settings form
    temp_settings = dict(settings)
    for k in ("base_url", "api_key", "api_protocol", "proxy", "use_proxy"):
        if k in payload and payload[k] is not None and "****" not in str(payload[k]):
            temp_settings[k] = payload[k]
    await discover_local_models(temp_settings)
    proxy = (temp_settings.get("proxy") or "").strip() if temp_settings.get("use_proxy") else None
    return await test_model_connectivity(model_id, temp_settings, proxy_url=proxy)


@router.post("/api/models/favorite")
def toggle_favorite_model(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    model_id = str(payload.get("model") or "").strip()
    if not model_id:
        raise HTTPException(status_code=400, detail="缺少模型 ID")
    db = get_user_db(username)
    s = db.get_settings()
    favs = list(s.get("favorite_models") or [])
    if model_id in favs:
        favs.remove(model_id)
        is_fav = False
    else:
        favs.insert(0, model_id)
        is_fav = True
    s["favorite_models"] = favs
    db.save_settings(s)
    return {"status": "ok", "model": model_id, "is_favorite": is_fav, "favorite_models": favs}


@router.post("/api/local_models/unload")
async def unload_local_models_endpoint():
    await shutdown_local_engines()
    # Also politely ask external Ollama if running
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=2.0) as client:
            r = await client.get("http://127.0.0.1:11434/api/ps")
            if r.status_code == 200:
                for m in r.json().get("models", []):
                    if m.get("name"):
                        await client.post("http://127.0.0.1:11434/api/generate", json={"model": m["name"], "keep_alive": 0})
    except Exception:
        pass
    return {"status": "ok", "message": "已释放全部本地显存"}


def _build_custom_paths_detail(paths: List[str]) -> List[Dict[str, Any]]:
    out = []
    for cp in paths:
        p = Path(cp)
        ggufs = list(p.rglob("*.gguf")) if p.is_dir() else ([p] if p.is_file() else [])
        out.append({"path": str(p), "exists": p.exists(), "gguf_count": len(ggufs)})
    return out


@router.get("/api/local_models/manager_status")
async def local_models_manager_status(username: str = Depends(get_current_user)):
    db = get_user_db(username)
    settings = db.get_settings()
    detected = await discover_local_models(settings)
    cp = load_saved_custom_model_paths(settings.get("custom_model_paths"))
    hw = await get_hardware_snapshot_async(use_cache=True)
    tasks_out = [
        {k: v for k, v in t.items() if k not in ("pause_requested", "cancel_requested")}
        for t in HF_DOWNLOAD_TASKS.values()
    ]
    return {
        "status": "ok",
        "model_dir": str(MODEL_DIR),
        "models_dir": str(MODELS_DIR),
        "detected_models": detected,
        "custom_paths": _build_custom_paths_detail(cp),
        "hf_catalog": await asyncio.to_thread(build_hf_catalog_with_status, cp),
        "downloads": tasks_out,
        "hardware": hw,
    }


@router.post("/api/local_models/open_folder", dependencies=[Depends(require_loopback)])
def open_local_models_folder(payload: Dict[str, Any] = {}):
    target = str(payload.get("target") or "model")
    p = MODELS_DIR if target == "models" else MODEL_DIR
    p.mkdir(parents=True, exist_ok=True)
    open_directory_safely(p)
    return {"status": "ok", "path": str(p)}


@router.post("/api/local_models/pick_path", dependencies=[Depends(require_loopback)])
async def pick_local_model_path(payload: Dict[str, Any] = {}):
    mode = str(payload.get("mode") or "folder")
    chosen = await asyncio.to_thread(native_pick_path, mode, "选择模型目录或 GGUF 文件")
    return {"path": chosen}


@router.post("/api/local_models/add_path", dependencies=[Depends(require_loopback)])
async def add_custom_model_path(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    raw = str(payload.get("path") or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="路径为空")
    p = Path(raw)
    if not p.exists():
        raise HTTPException(status_code=400, detail="路径不存在")
    db = get_user_db(username)
    s = db.get_settings()
    cp = load_saved_custom_model_paths(s.get("custom_model_paths"))
    norm = str(p.resolve())
    if norm not in cp:
        cp.append(norm)
    cp = save_custom_model_paths(cp)
    s["custom_model_paths"] = cp
    db.save_settings(s)
    detected = await discover_local_models(s)
    return {
        "status": "ok",
        "added": norm,
        "custom_paths": _build_custom_paths_detail(cp),
        "detected_models": detected,
        "hf_catalog": build_hf_catalog_with_status(cp),
    }


@router.post("/api/local_models/remove_path", dependencies=[Depends(require_loopback)])
async def remove_custom_model_path(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    raw = str(payload.get("path") or "").strip()
    db = get_user_db(username)
    s = db.get_settings()
    cp = [c for c in load_saved_custom_model_paths(s.get("custom_model_paths")) if c != raw]
    cp = save_custom_model_paths(cp)
    s["custom_model_paths"] = cp
    db.save_settings(s)
    detected = await discover_local_models(s)
    return {"status": "ok", "custom_paths": _build_custom_paths_detail(cp), "detected_models": detected}


@router.get("/api/local_models/hf_repo_files")
async def fetch_hf_repo_files(author: str = "dongfangshuo", repo_id: str = "", mirror: str = "hf-mirror"):
    host = "https://hf-mirror.com" if mirror == "hf-mirror" else "https://huggingface.co"
    repos = [repo_id.strip().strip("/")] if repo_id.strip() else []
    results: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(trust_env=False, follow_redirects=True, timeout=10.0) as client:
        if not repos:
            try:
                r = await client.get(f"{host}/api/models?author={author.strip()}&limit=20")
                if r.status_code == 200:
                    repos = [m["id"] for m in r.json() if isinstance(m, dict) and m.get("id")]
            except Exception:
                repos = [p["repo_id"] for p in HF_PRESET_CATALOG]
        for rid in list(dict.fromkeys(repos))[:8]:
            try:
                r = await client.get(f"{host}/api/models/{rid}/tree/main")
                if r.status_code == 200:
                    ggufs = [
                        {"path": x["path"], "size": int(x.get("size") or 0)}
                        for x in r.json()
                        if str(x.get("path") or "").lower().endswith(".gguf")
                    ]
                    if ggufs:
                        results.append({"repo_id": rid, "files": ggufs})
            except Exception:
                pass
    return {"status": "ok", "repos": results}


@router.post("/api/local_models/hf_download")
async def trigger_hf_download(payload: Dict[str, Any]):
    preset_id = str(payload.get("preset_id") or "").strip()
    repo_id = str(payload.get("repo_id") or "").strip()
    files = payload.get("files") or []
    mirror = str(payload.get("mirror") or "hf-mirror")
    try:
        task = start_hf_download(preset_id=preset_id, repo_id=repo_id, files=files, mirror=mirror)
        return {"status": "ok", "task": {k: v for k, v in task.items() if k not in ("pause_requested", "cancel_requested")}}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/local_models/hf_control")
async def control_hf_download(payload: Dict[str, Any]):
    tid = str(payload.get("task_id") or "").strip()
    action = str(payload.get("action") or "").strip().lower()
    task = HF_DOWNLOAD_TASKS.get(tid)
    if not task:
        raise HTTPException(status_code=404, detail="下载任务不存在")
    if action == "pause":
        task["pause_requested"] = True
        task["status"] = "paused"
    elif action == "resume":
        task["pause_requested"] = False
        task["status"] = "downloading"
    elif action == "cancel":
        task["cancel_requested"] = True
        task["status"] = "cancelled"
    return {"status": "ok", "task": {k: v for k, v in task.items() if k not in ("pause_requested", "cancel_requested")}}
