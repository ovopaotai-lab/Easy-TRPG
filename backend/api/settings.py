# -*- coding: utf-8 -*-
"""Settings, per-model params, hardware recommendations, and provider presets API."""
from __future__ import annotations

import copy
from typing import Any, Dict

from fastapi import APIRouter, Depends

from backend.config import sanitize_settings_numbers
from backend.core.auth import get_current_user
from backend.core.security import is_masked_api_key, is_self_workbench_url, mask_settings_for_client
from backend.engines.hardware import get_hardware_snapshot_async
from backend.providers.router import CLOUD_VENDOR_PRESETS
from backend.storage.db import get_user_db

router = APIRouter()


@router.get("/api/settings")
def get_settings(username: str = Depends(get_current_user)):
    db = get_user_db(username)
    return mask_settings_for_client(db.get_settings())


@router.post("/api/settings")
async def update_settings(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    payload = dict(payload or {})
    payload.pop("has_api_key", None)
    db = get_user_db(username)
    current = db.get_settings()
    preserved_key = str(current.get("api_key") or "")

    if "api_key" in payload:
        if is_masked_api_key(payload.get("api_key")):
            payload["api_key"] = preserved_key
        else:
            payload["api_key"] = str(payload.get("api_key") or "").strip()

    # Preserve masked keys inside api_profiles
    if isinstance(payload.get("api_profiles"), list):
        old_profiles = {str(p.get("id") or ""): p for p in (current.get("api_profiles") or []) if isinstance(p, dict)}
        fixed_profiles = []
        for pf in payload["api_profiles"]:
            if not isinstance(pf, dict):
                continue
            pfc = dict(pf)
            pfc.pop("has_api_key", None)
            pid = str(pfc.get("id") or "")
            if is_masked_api_key(pfc.get("api_key")) and pid in old_profiles:
                pfc["api_key"] = old_profiles[pid].get("api_key", "")
            fixed_profiles.append(pfc)
        payload["api_profiles"] = fixed_profiles

    current.update(payload)
    warnings = []
    if is_self_workbench_url(str(current.get("base_url") or "")):
        current["base_url"] = ""
        warnings.append("检测到填写了工作台自身地址，已自动清空")
    if is_self_workbench_url(str(current.get("local_base_url") or "")):
        current["local_base_url"] = ""
        current["local_mode"] = "auto"

    sanitize_settings_numbers(current)
    saved = db.save_settings(current)
    resp = mask_settings_for_client(saved)
    if warnings:
        resp["warnings"] = warnings
    return {"status": "ok", "settings": resp, **resp}


@router.post("/api/settings/model_params")
def update_model_params(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    model_id = str(payload.get("model") or "").strip()
    params = dict(payload.get("params") or {})
    db = get_user_db(username)
    s = db.get_settings()
    mp = copy.deepcopy(s.get("model_params") or {})
    if model_id:
        if payload.get("clear"):
            mp.pop(model_id, None)
        else:
            mp[model_id] = params
        s["model_params"] = mp
        db.save_settings(s)
    return {"status": "ok", "model": model_id, "model_params": mp}


@router.post("/api/settings/sync_params_to_projects")
def sync_params_to_projects(payload: Dict[str, Any] = {}, username: str = Depends(get_current_user)):
    db = get_user_db(username)
    s = db.get_settings()
    updated = 0
    for p in db.list_projects():
        comp = dict(p.get("completion_params") or {})
        for k in ("temperature", "repetition_penalty", "frequency_penalty", "presence_penalty", "top_p", "top_k", "min_p", "max_tokens", "max_context_k", "context_mode"):
            if k in s:
                comp[k] = s[k]
        p["completion_params"] = comp
        p["use_global_params"] = True
        db.save_project(p)
        updated += 1
    return {"status": "ok", "updated_projects": updated}


@router.post("/api/settings/hardware_recommend")
async def hardware_recommend(username: str = Depends(get_current_user)):
    hw = await get_hardware_snapshot_async(use_cache=False)
    rec = {
        "max_context_k": hw["recommended_max_context_k"],
        "low_spec_mode": "on" if hw["low_spec_recommended"] else "off",
        "temperature": 0.68,
        "top_p": 0.90,
        "min_p": 0.06,
        "repetition_penalty": 1.05,
        "max_tokens": 4096 if hw["low_spec_recommended"] else 8192,
    }
    return {"status": "ok", "hardware": hw, "recommended": rec}


@router.get("/api/providers/presets")
def get_provider_presets():
    return {"status": "ok", "presets": CLOUD_VENDOR_PRESETS}
