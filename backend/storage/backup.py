# -*- coding: utf-8 -*-
"""Backup overview, export to folder, and import from v1.x/v2.0 backup folders."""
from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List

from backend.config import BACKUP_ROOT_DIR, atomic_write_json
from backend.core.security import get_user_dir, get_user_gallery_dir, sanitize_id
from backend.storage.db import get_user_db
from backend.storage.migrator import migrate_v1_directory_into_db

logger = logging.getLogger("easy_trpg.backup")


def get_backup_overview(username: str) -> Dict[str, Any]:
    db = get_user_db(username)
    projects = db.list_projects()
    chats = db.list_chats()
    gallery = db.list_gallery()
    presets = db.list_presets()
    return {
        "default_export_dir": str(BACKUP_ROOT_DIR / time.strftime("backup_%Y%m%d_%H%M%S")),
        "backup_root_dir": str(BACKUP_ROOT_DIR),
        "projects": [
            {"id": p["id"], "name": p["name"], "icon": p.get("icon") or p.get("avatar") or ""}
            for p in projects
        ],
        "chats": [
            {
                "id": c["id"],
                "title": c["title"],
                "project_id": c["project_id"],
                "msg_count": c.get("message_count", 0),
                "updated_at": c.get("updated_at", 0),
            }
            for c in chats
        ],
        "gallery_count": len(gallery),
        "presets_count": len(presets),
        "logs_count": len(chats),
    }


def export_backup_to_folder(username: str, target_dir: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    db = get_user_db(username)
    udir = get_user_dir(username)
    gallery_dir = get_user_gallery_dir(username)
    target_dir.mkdir(parents=True, exist_ok=True)

    include_projects = payload.get("include_projects", True)
    include_chats = payload.get("include_chats", True)
    include_gallery = payload.get("include_gallery", True)
    include_cards = payload.get("include_cards", True)
    include_settings = payload.get("include_settings", True)
    selected_proj_ids = set(payload.get("project_ids") or [])
    selected_chat_ids = set(payload.get("chat_ids") or [])

    stats = {"projects": 0, "chats": 0, "gallery": 0, "cards": 0}

    # Copy trpg.db snapshot directly via sqlite backup API for atomic consistency
    db_copy = target_dir / "trpg.db"
    import sqlite3
    with db._lock:
        dst_conn = sqlite3.connect(str(db_copy))
        db._conn.backup(dst_conn)
        dst_conn.close()

    # Also export portable v1-compatible JSON files for maximum cross-version safety
    if include_projects:
        p_out = target_dir / "projects"
        p_out.mkdir(parents=True, exist_ok=True)
        for p in db.list_projects():
            if selected_proj_ids and p["id"] not in selected_proj_ids:
                continue
            atomic_write_json(p_out / f"{sanitize_id(p['id'])}.json", p)
            stats["projects"] += 1

    if include_chats:
        c_out = target_dir / "chats"
        c_out.mkdir(parents=True, exist_ok=True)
        for cmeta in db.list_chats():
            if selected_chat_ids and cmeta["id"] not in selected_chat_ids:
                continue
            cfull = db.get_chat_full(cmeta["id"])
            if cfull:
                atomic_write_json(c_out / f"{sanitize_id(cmeta['id'])}.json", cfull)
                stats["chats"] += 1

    if include_cards:
        atomic_write_json(target_dir / "character_cards.json", db.list_cards())
        stats["cards"] = len(db.list_cards())

    if include_settings:
        s = db.get_settings()
        if payload.get("strip_secrets"):
            s["api_key"] = ""
            s["api_profiles"] = []
        atomic_write_json(target_dir / "settings.json", s)

    if include_gallery and gallery_dir.exists():
        g_out = target_dir / "gallery"
        g_out.mkdir(parents=True, exist_ok=True)
        for fp in gallery_dir.glob("*.*"):
            if fp.is_file():
                shutil.copy2(fp, g_out / fp.name)
                stats["gallery"] += 1
        thumbs_src = gallery_dir / "thumbs"
        if thumbs_src.exists():
            thumbs_dst = g_out / "thumbs"
            thumbs_dst.mkdir(parents=True, exist_ok=True)
            for fp in thumbs_src.glob("*.*"):
                if fp.is_file():
                    shutil.copy2(fp, thumbs_dst / fp.name)
        atomic_write_json(target_dir / "gallery.json", db.list_gallery())
        atomic_write_json(target_dir / "gallery_folders.json", db.list_gallery_folders())

    manifest = {
        "schema_version": 2,
        "exported_at": time.time(),
        "username": username,
        "stats": stats,
    }
    atomic_write_json(target_dir / "backup_manifest.json", manifest)
    return {"status": "ok", "export_dir": str(target_dir), "stats": stats}


def import_backup_from_folder(username: str, src_dir: Path) -> Dict[str, Any]:
    if not src_dir.exists() or not src_dir.is_dir():
        raise FileNotFoundError(f"备份目录不存在: {src_dir}")
    db = get_user_db(username)
    gallery_dir = get_user_gallery_dir(username)

    # Copy gallery image files first so migrator can hash & register them
    src_gallery = src_dir / "gallery"
    if src_gallery.is_dir():
        for fp in src_gallery.glob("*.*"):
            if fp.is_file():
                shutil.copy2(fp, gallery_dir / fp.name)
        src_thumbs = src_gallery / "thumbs"
        if src_thumbs.is_dir():
            for fp in src_thumbs.glob("*.*"):
                if fp.is_file():
                    shutil.copy2(fp, gallery_dir / "thumbs" / fp.name)

    counts = migrate_v1_directory_into_db(db, src_dir, force=True)
    return {"status": "ok", "imported": counts}
