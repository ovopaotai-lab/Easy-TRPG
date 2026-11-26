# -*- coding: utf-8 -*-
"""Idempotent, non-destructive v1.x JSON -> SQLite WAL/FTS5 migrator."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

from backend.config import DEFAULT_SETTINGS, normalize_project_schema, safe_int
from backend.core.security import get_user_dir, sanitize_id
from backend.storage.db import UserDatabase, get_user_db

logger = logging.getLogger("easy_trpg.migrator")


def _extract_image_bytes(raw_b64: str) -> Optional[bytes]:
    if not raw_b64 or not isinstance(raw_b64, str):
        return None
    s = raw_b64.strip()
    if s.startswith("data:image"):
        m = re.match(r"^data:image/[^;]+;base64,(.+)$", s, flags=re.S)
        if not m:
            return None
        s = m.group(1)
    try:
        return base64.b64decode(re.sub(r"\s+", "", s))
    except Exception:
        return None


def _save_base64_to_gallery_db(
    db: UserDatabase,
    gallery_dir: Path,
    raw_b64: str,
    filename: Optional[str] = None,
    folder: str = "默认图库",
) -> Optional[str]:
    """Deduplicate & store base64 image on disk and register in gallery_assets."""
    img_bytes = _extract_image_bytes(raw_b64)
    if not img_bytes:
        return None
    sha = hashlib.sha256(img_bytes).hexdigest()
    existing = db.find_gallery_by_sha256(sha)
    if existing:
        return str(existing["id"])

    try:
        with Image.open(io.BytesIO(img_bytes)) as im_raw:
            im = im_raw.convert("RGB")
            img_id = f"img_{sha[:12]}"
            out_path = gallery_dir / f"{img_id}.jpg"
            thumbs_dir = gallery_dir / "thumbs"
            thumbs_dir.mkdir(parents=True, exist_ok=True)
            thumb_path = thumbs_dir / f"{img_id}.jpg"
            im.save(out_path, format="JPEG", quality=92, optimize=True)
            thumb = im.copy()
            thumb.thumbnail((320, 320))
            thumb.save(thumb_path, format="JPEG", quality=82, optimize=True)
            db.upsert_gallery_asset(
                {
                    "id": img_id,
                    "filename": filename or f"{img_id}.jpg",
                    "folder": folder or "默认图库",
                    "sha256": sha,
                    "vhash": "",
                    "width": im.width,
                    "height": im.height,
                    "size_bytes": out_path.stat().st_size,
                    "created_at": time.time(),
                }
            )
            return img_id
    except Exception as exc:
        logger.warning("Failed extracting embedded image during migration: %s", exc)
        return None


def _resolve_msg_media_ids(db: UserDatabase, gallery_dir: Path, msg: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    for aid in msg.get("media_asset_ids") or []:
        s = str(aid or "").strip()
        if s and s not in ids:
            ids.append(s)

    raw_imgs: List[str] = []
    if isinstance(msg.get("images"), list):
        raw_imgs.extend([str(x) for x in msg["images"] if x])
    elif msg.get("image"):
        raw_imgs.append(str(msg["image"]))

    for img in raw_imgs:
        m = re.search(r"/api/gallery/(?:image|thumb)/([a-zA-Z0-9._-]+)", img)
        if m:
            gid = sanitize_id(m.group(1))
            if gid not in ids:
                ids.append(gid)
            continue
        if img.startswith("data:image") or len(img) > 128:
            gid = _save_base64_to_gallery_db(db, gallery_dir, img)
            if gid and gid not in ids:
                ids.append(gid)
    return ids


def migrate_v1_directory_into_db(
    db: UserDatabase,
    source_user_dir: Path,
    *,
    force: bool = False,
) -> Dict[str, int]:
    """Import legacy v1.x JSON workspace files into SQLite without deleting source files."""
    if not force and db.get_meta("migrated_v1") == "1":
        return {"skipped": 1}

    counts = {"projects": 0, "chats": 0, "messages": 0, "cards": 0, "gallery": 0, "presets": 0}
    gallery_dir = get_user_dir(db.username) / "gallery"
    gallery_dir.mkdir(parents=True, exist_ok=True)

    # 1. Settings
    sfile = source_user_dir / "settings.json"
    if sfile.is_file():
        try:
            raw_s = json.loads(sfile.read_text(encoding="utf-8"))
            if isinstance(raw_s, dict):
                merged = dict(DEFAULT_SETTINGS)
                merged.update(raw_s)
                db.save_settings(merged)
        except Exception as exc:
            logger.warning("Settings migration warning (%s): %s", sfile, exc)

    # 2. Gallery folders & metadata
    gfolder_file = source_user_dir / "gallery_folders.json"
    if gfolder_file.is_file():
        try:
            gf = json.loads(gfolder_file.read_text(encoding="utf-8"))
            if isinstance(gf, list):
                db.save_gallery_folders([str(x) for x in gf])
        except Exception as exc:
            logger.warning("Gallery folders migration warning: %s", exc)

    gfile = source_user_dir / "gallery.json"
    if gfile.is_file():
        try:
            gitems = json.loads(gfile.read_text(encoding="utf-8"))
            if isinstance(gitems, list):
                for item in gitems:
                    if not isinstance(item, dict) or not item.get("id"):
                        continue
                    gid = sanitize_id(item["id"])
                    fpath = gallery_dir / f"{gid}.jpg"
                    sha = str(item.get("sha256") or "")
                    if not sha and fpath.is_file():
                        sha = hashlib.sha256(fpath.read_bytes()).hexdigest()
                    db.upsert_gallery_asset(
                        {
                            "id": gid,
                            "filename": item.get("filename") or f"{gid}.jpg",
                            "folder": item.get("folder") or "默认图库",
                            "sha256": sha,
                            "vhash": item.get("vhash") or "",
                            "width": safe_int(item.get("width"), 0),
                            "height": safe_int(item.get("height"), 0),
                            "size_bytes": safe_int(item.get("size_bytes"), 0),
                            "created_at": float(item.get("created_at") or time.time()),
                        }
                    )
                    counts["gallery"] += 1
        except Exception as exc:
            logger.warning("Gallery migration warning: %s", exc)

    # 3. Projects
    pdir = source_user_dir / "projects"
    if pdir.is_dir():
        for pf in sorted(pdir.glob("*.json")):
            try:
                raw_p = json.loads(pf.read_text(encoding="utf-8"))
                if isinstance(raw_p, dict):
                    raw_p.setdefault("id", pf.stem)
                    db.save_project(normalize_project_schema(raw_p, raw_p))
                    counts["projects"] += 1
            except Exception as exc:
                logger.warning("Project migration warning (%s): %s", pf.name, exc)

    # 4. Character cards
    ccfile = source_user_dir / "character_cards.json"
    if ccfile.is_file():
        try:
            cards = json.loads(ccfile.read_text(encoding="utf-8"))
            if isinstance(cards, list):
                for card in cards:
                    if isinstance(card, dict) and card.get("name"):
                        db.save_card(card)
                        counts["cards"] += 1
        except Exception as exc:
            logger.warning("Character cards migration warning: %s", exc)

    # 5. Presets
    pr_dir = source_user_dir / "presets"
    if pr_dir.is_dir():
        for prf in sorted(pr_dir.glob("*.json")):
            try:
                raw_pr = json.loads(prf.read_text(encoding="utf-8"))
                if isinstance(raw_pr, dict):
                    raw_pr.setdefault("id", prf.stem)
                    db.save_preset(raw_pr)
                    counts["presets"] += 1
            except Exception as exc:
                logger.warning("Preset migration warning (%s): %s", prf.name, exc)

    # 6. Chats & messages (preserving order, timestamps, variables, extracting base64 images)
    cdir = source_user_dir / "chats"
    if cdir.is_dir():
        existing_chat_ids = {c["id"] for c in db.list_chats()}
        with db._lock:
            seen_node_ids = {
                str(r[0]) for r in db._conn.execute("SELECT id FROM message_nodes").fetchall()
            }
        for cf in sorted(cdir.glob("*.json")):
            try:
                cdata = json.loads(cf.read_text(encoding="utf-8"))
                if not isinstance(cdata, dict):
                    continue
                cid = sanitize_id(cdata.get("id") or cf.stem)
                if cid in existing_chat_ids and not force:
                    continue
                if cid in existing_chat_ids and force:
                    db.delete_chat(cid)
                    with db._lock:
                        seen_node_ids = {
                            str(r[0]) for r in db._conn.execute("SELECT id FROM message_nodes").fetchall()
                        }

                raw_msgs = cdata.get("messages") or []
                norm_msgs: List[Dict[str, Any]] = []
                for m in raw_msgs:
                    if not isinstance(m, dict):
                        continue
                    media_ids = _resolve_msg_media_ids(db, gallery_dir, m)
                    content_str = str(m.get("content") or "")
                    raw_mid = str(m.get("id") or "").strip()
                    nid = raw_mid if (raw_mid and raw_mid not in seen_node_ids) else f"{cid}_{raw_mid}" if (raw_mid and f"{cid}_{raw_mid}" not in seen_node_ids) else f"msg_{uuid.uuid4().hex[:10]}"
                    seen_node_ids.add(nid)
                    norm_msgs.append(
                        {
                            "id": nid,
                            "role": str(m.get("role") or "user"),
                            "content": content_str,
                            "prompt_content": content_str,
                            "character_cards": m.get("character_cards") or [],
                            "triggered_worldbooks": m.get("triggered_worldbooks") or [],
                            "triggered_cgs": m.get("triggered_cgs") or [],
                            "suggested_questions": m.get("suggested_questions") or [],
                            "media_asset_ids": media_ids,
                            "is_opening": bool(m.get("is_opening", False)),
                            "interrupted": bool(m.get("interrupted", False)),
                            "timestamp": float(m.get("timestamp") or time.time()),
                        }
                    )
                vars_dict = cdata.get("inputs") or cdata.get("variables") or {}
                db.create_chat(
                    chat_id=cid,
                    project_id=sanitize_id(cdata.get("project_id") or "proj_default"),
                    title=str(cdata.get("title") or "未命名对话"),
                    model=str(cdata.get("model") or ""),
                    variables=vars_dict if isinstance(vars_dict, dict) else {},
                    parent_chat_id=str(cdata.get("parent_chat_id") or ""),
                    init_messages=norm_msgs,
                    summary=str(cdata.get("summary") or ""),
                    summarized_count=safe_int(cdata.get("summarized_count"), 0),
                    created_at=float(cdata.get("created_at") or time.time()),
                    updated_at=float(cdata.get("updated_at") or time.time()),
                )
                if cdata.get("last_prompt_log") and isinstance(cdata["last_prompt_log"], dict):
                    db.save_prompt_log(cid, "", cdata["last_prompt_log"])
                counts["chats"] += 1
                counts["messages"] += len(norm_msgs)
            except Exception as exc:
                logger.warning("Chat migration warning (%s): %s", cf.name, exc)

    # Seed default persona & default presets if empty
    if not db.list_personas():
        db.save_persona(
            {
                "id": "persona_default",
                "name": "旅人",
                "description": "随剧本世界观自适应身份的主角。",
                "is_default": True,
            }
        )

    db.set_meta("migrated_v1", "1")
    logger.info("Workspace %s v1->v2 migration complete: %s", db.username, counts)
    return counts


def ensure_user_migrated(username: str) -> None:
    """Ensure SQLite DB exists, v1 data is migrated if present, and core projects exist."""
    db = get_user_db(username)
    udir = get_user_dir(username)
    if db.get_meta("migrated_v1") != "1":
        migrate_v1_directory_into_db(db, udir)
    # Ensure default 3 workspaces always exist
    from backend.content.catalog import ensure_default_projects_in_db
    ensure_default_projects_in_db(db)
