# -*- coding: utf-8 -*-
"""Per-user SQLite WAL + FTS5 database with DAG message tree and swipe support."""
from __future__ import annotations

import copy
import json
import logging
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.config import (
    DEFAULT_SETTINGS,
    SCHEMA_VERSION,
    normalize_project_schema,
    normalize_settings,
    safe_int,
)
from backend.core.security import get_user_dir

logger = logging.getLogger("easy_trpg.db")

_DB_CACHE_LOCK = threading.Lock()
_USER_DBS: Dict[str, "UserDatabase"] = {}


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _json_loads(raw: Optional[str], fallback: Any) -> Any:
    if not raw:
        return copy.deepcopy(fallback)
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return copy.deepcopy(fallback)


class UserDatabase:
    """Thread-safe SQLite WAL repository for a single user workspace."""

    def __init__(self, username: str) -> None:
        self.username = username
        self.user_dir: Path = get_user_dir(username)
        self.db_path: Path = self.user_dir / "trpg.db"
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=15.0,
        )
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            c = self._conn
            c.execute("PRAGMA journal_mode=WAL;")
            c.execute("PRAGMA synchronous=NORMAL;")
            c.execute("PRAGMA foreign_keys=ON;")
            c.execute("PRAGMA busy_timeout=5000;")
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS kv_settings (
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    data_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '跑团',
                    data_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    model TEXT NOT NULL DEFAULT '',
                    active_node_id TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    summarized_count INTEGER NOT NULL DEFAULT 0,
                    author_note_json TEXT NOT NULL DEFAULT '{}',
                    group_config_json TEXT NOT NULL DEFAULT '{}',
                    persona_id TEXT NOT NULL DEFAULT '',
                    preset_id TEXT NOT NULL DEFAULT '',
                    variables_json TEXT NOT NULL DEFAULT '{}',
                    visited_wb_json TEXT NOT NULL DEFAULT '[]',
                    cg_unlocked_json TEXT NOT NULL DEFAULT '[]',
                    parent_chat_id TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chats_proj_upd ON chats(project_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS message_nodes (
                    id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    parent_id TEXT NOT NULL DEFAULT '',
                    seq INTEGER NOT NULL DEFAULT 0,
                    role TEXT NOT NULL,
                    speaker_card_id TEXT NOT NULL DEFAULT '',
                    speaker_name TEXT NOT NULL DEFAULT '',
                    active_swipe_idx INTEGER NOT NULL DEFAULT 0,
                    state_snapshot_json TEXT NOT NULL DEFAULT '{}',
                    is_opening INTEGER NOT NULL DEFAULT 0,
                    interrupted INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_nodes_chat ON message_nodes(chat_id, seq);

                CREATE TABLE IF NOT EXISTS message_swipes (
                    id TEXT PRIMARY KEY,
                    node_id TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    swipe_idx INTEGER NOT NULL DEFAULT 0,
                    content TEXT NOT NULL DEFAULT '',
                    prompt_content TEXT NOT NULL DEFAULT '',
                    thinking TEXT NOT NULL DEFAULT '',
                    state_patch_json TEXT NOT NULL DEFAULT '{}',
                    dice_rolls_json TEXT NOT NULL DEFAULT '[]',
                    media_asset_ids_json TEXT NOT NULL DEFAULT '[]',
                    character_cards_json TEXT NOT NULL DEFAULT '[]',
                    triggered_worldbooks_json TEXT NOT NULL DEFAULT '[]',
                    triggered_cgs_json TEXT NOT NULL DEFAULT '[]',
                    suggested_questions_json TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    FOREIGN KEY(node_id) REFERENCES message_nodes(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_swipes_node ON message_swipes(node_id, swipe_idx);
                CREATE INDEX IF NOT EXISTS idx_swipes_chat ON message_swipes(chat_id);

                CREATE TABLE IF NOT EXISTS chapters (
                    id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    chapter_num INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    up_to_node_id TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS character_cards (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    avatar_asset_id TEXT NOT NULL DEFAULT '',
                    data_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS personas (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    avatar_asset_id TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    is_default INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS presets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    is_default INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS gallery_assets (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    folder TEXT NOT NULL DEFAULT '默认图库',
                    sha256 TEXT NOT NULL DEFAULT '',
                    vhash TEXT NOT NULL DEFAULT '',
                    width INTEGER NOT NULL DEFAULT 0,
                    height INTEGER NOT NULL DEFAULT 0,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_gallery_sha ON gallery_assets(sha256);

                CREATE TABLE IF NOT EXISTS gallery_folders (
                    name TEXT PRIMARY KEY,
                    sort_order INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS prompt_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    node_id TEXT NOT NULL DEFAULT '',
                    log_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_prompt_logs_chat ON prompt_logs(chat_id, id DESC);

                CREATE VIRTUAL TABLE IF NOT EXISTS fts_messages USING fts5(
                    node_id UNINDEXED,
                    chat_id UNINDEXED,
                    role UNINDEXED,
                    content,
                    tokenize='unicode61'
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_projects USING fts5(
                    project_id UNINDEXED,
                    name,
                    description,
                    tags,
                    tokenize='unicode61'
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_cards USING fts5(
                    card_id UNINDEXED,
                    name,
                    description,
                    tokenize='unicode61'
                );
                """
            )
            c.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            c.execute("INSERT OR IGNORE INTO gallery_folders(name, sort_order) VALUES ('默认图库', 0)")
            c.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def get_meta(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return str(row["value"]) if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )
            self._conn.commit()

    # -------------------- Settings --------------------
    def get_settings(self) -> Dict[str, Any]:
        with self._lock:
            row = self._conn.execute("SELECT data_json FROM kv_settings WHERE id=1").fetchone()
            if not row:
                return copy.deepcopy(DEFAULT_SETTINGS)
            return normalize_settings(_json_loads(row["data_json"], DEFAULT_SETTINGS))

    def save_settings(self, data: Dict[str, Any]) -> Dict[str, Any]:
        norm = normalize_settings(data)
        with self._lock:
            self._conn.execute(
                "INSERT INTO kv_settings(id, data_json, updated_at) VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET data_json=excluded.data_json, updated_at=excluded.updated_at",
                (_json_dumps(norm), time.time()),
            )
            self._conn.commit()
        return norm

    # -------------------- Projects --------------------
    def list_projects(self) -> List[Dict[str, Any]]:
        settings = self.get_settings()
        with self._lock:
            rows = self._conn.execute(
                "SELECT data_json FROM projects ORDER BY updated_at DESC"
            ).fetchall()
            return [
                normalize_project_schema(_json_loads(r["data_json"], {}), global_defaults=settings)
                for r in rows
            ]

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        settings = self.get_settings()
        with self._lock:
            row = self._conn.execute(
                "SELECT data_json FROM projects WHERE id=?", (project_id,)
            ).fetchone()
            if not row:
                return None
            raw = _json_loads(row["data_json"], {})
            return normalize_project_schema(raw, raw, global_defaults=settings)

    def save_project(self, data: Dict[str, Any]) -> Dict[str, Any]:
        settings = self.get_settings()
        existing = self.get_project(str(data.get("id") or "")) or {}
        norm = normalize_project_schema(data, existing, global_defaults=settings)
        pid = norm["id"]
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO projects(id, name, category, data_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, category=excluded.category, "
                "data_json=excluded.data_json, updated_at=excluded.updated_at",
                (pid, norm["name"], norm["category"], _json_dumps(norm), norm.get("created_at", now), now),
            )
            self._conn.execute("DELETE FROM fts_projects WHERE project_id=?", (pid,))
            self._conn.execute(
                "INSERT INTO fts_projects(project_id, name, description, tags) VALUES (?, ?, ?, ?)",
                (pid, norm["name"], norm.get("description", ""), " ".join(norm.get("tags") or [])),
            )
            self._conn.commit()
        return norm

    def delete_project(self, project_id: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE chats SET project_id='proj_default' WHERE project_id=?", (project_id,))
            self._conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
            self._conn.execute("DELETE FROM fts_projects WHERE project_id=?", (project_id,))
            self._conn.commit()

    # -------------------- Chats & DAG Tree --------------------
    def list_chats(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        settings = self.get_settings()
        default_model = settings.get("model", "")
        with self._lock:
            if project_id:
                rows = self._conn.execute(
                    "SELECT c.*, (SELECT COUNT(*) FROM message_nodes mn WHERE mn.chat_id=c.id) AS node_count "
                    "FROM chats c WHERE c.project_id=? ORDER BY c.updated_at DESC",
                    (project_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT c.*, (SELECT COUNT(*) FROM message_nodes mn WHERE mn.chat_id=c.id) AS node_count "
                    "FROM chats c ORDER BY c.updated_at DESC"
                ).fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                out.append(
                    {
                        "id": r["id"],
                        "title": r["title"],
                        "project_id": r["project_id"],
                        "model": r["model"] or default_model,
                        "active_node_id": r["active_node_id"],
                        "created_at": r["created_at"],
                        "updated_at": r["updated_at"],
                        "message_count": r["node_count"],
                        "has_summary": bool((r["summary"] or "").strip()),
                    }
                )
            return out

    def _get_active_chain_rows(self, chat_id: str, active_node_id: str) -> List[sqlite3.Row]:
        rows = self._conn.execute(
            "SELECT * FROM message_nodes WHERE chat_id=? ORDER BY seq ASC, created_at ASC",
            (chat_id,),
        ).fetchall()
        if not rows:
            return []
        by_id = {r["id"]: r for r in rows}
        leaf = by_id.get(active_node_id) or rows[-1]
        chain: List[sqlite3.Row] = []
        seen = set()
        curr: Optional[sqlite3.Row] = leaf
        while curr is not None and curr["id"] not in seen:
            seen.add(curr["id"])
            chain.append(curr)
            pid = curr["parent_id"]
            curr = by_id.get(pid) if pid else None
        chain.reverse()
        return chain

    def _build_message_dict(self, node_row: sqlite3.Row, swipes: List[sqlite3.Row]) -> Dict[str, Any]:
        active_idx = max(0, min(len(swipes) - 1, safe_int(node_row["active_swipe_idx"], 0))) if swipes else 0
        active_sw = swipes[active_idx] if swipes else None
        media_ids = _json_loads(active_sw["media_asset_ids_json"], []) if active_sw else []
        img_urls = [f"/api/gallery/image/{aid}" for aid in media_ids if not str(aid).startswith("vid_")]
        vid_urls = [f"/api/gallery/video/{aid}" for aid in media_ids if str(aid).startswith("vid_")]
        return {
            "id": node_row["id"],
            "parent_id": node_row["parent_id"],
            "seq": node_row["seq"],
            "role": node_row["role"],
            "speaker_card_id": node_row["speaker_card_id"],
            "speaker_name": node_row["speaker_name"],
            "content": active_sw["content"] if active_sw else "",
            "prompt_content": active_sw["prompt_content"] if active_sw else "",
            "thinking": active_sw["thinking"] if active_sw else "",
            "active_swipe_idx": active_idx,
            "swipe_count": len(swipes),
            "swipes": [
                {
                    "id": s["id"],
                    "swipe_idx": s["swipe_idx"],
                    "content": s["content"],
                    "thinking": s["thinking"],
                    "state_patch": _json_loads(s["state_patch_json"], {}),
                    "dice_rolls": _json_loads(s["dice_rolls_json"], []),
                    "media_asset_ids": _json_loads(s["media_asset_ids_json"], []),
                    "triggered_worldbooks": _json_loads(s["triggered_worldbooks_json"], []),
                    "triggered_cgs": _json_loads(s["triggered_cgs_json"], []),
                    "suggested_questions": _json_loads(s["suggested_questions_json"], []),
                    "created_at": s["created_at"],
                }
                for s in swipes
            ],
            "state_snapshot": _json_loads(node_row["state_snapshot_json"], {}),
            "state_patch": _json_loads(active_sw["state_patch_json"], {}) if active_sw else {},
            "dice_rolls": _json_loads(active_sw["dice_rolls_json"], []) if active_sw else [],
            "media_asset_ids": media_ids,
            "images": img_urls,
            "videos": vid_urls,
            "character_cards": _json_loads(active_sw["character_cards_json"], []) if active_sw else [],
            "triggered_worldbooks": _json_loads(active_sw["triggered_worldbooks_json"], []) if active_sw else [],
            "triggered_cgs": _json_loads(active_sw["triggered_cgs_json"], []) if active_sw else [],
            "suggested_questions": _json_loads(active_sw["suggested_questions_json"], []) if active_sw else [],
            "is_opening": bool(node_row["is_opening"]),
            "interrupted": bool(node_row["interrupted"]),
            "timestamp": node_row["created_at"],
        }

    def get_chat_full(self, chat_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()
            if not row:
                return None
            chain = self._get_active_chain_rows(chat_id, row["active_node_id"])
            node_ids = [n["id"] for n in chain]
            swipes_by_node: Dict[str, List[sqlite3.Row]] = {nid: [] for nid in node_ids}
            if node_ids:
                placeholders = ",".join("?" for _ in node_ids)
                sw_rows = self._conn.execute(
                    f"SELECT * FROM message_swipes WHERE node_id IN ({placeholders}) ORDER BY swipe_idx ASC",
                    node_ids,
                ).fetchall()
                for sw in sw_rows:
                    swipes_by_node.setdefault(sw["node_id"], []).append(sw)

            messages = [self._build_message_dict(n, swipes_by_node.get(n["id"], [])) for n in chain]
            active_state = messages[-1].get("state_snapshot") if messages else {}
            variables = _json_loads(row["variables_json"], {})
            chapters = self.list_chapters(chat_id)
            return {
                "id": row["id"],
                "title": row["title"],
                "project_id": row["project_id"],
                "model": row["model"],
                "active_node_id": row["active_node_id"] or (chain[-1]["id"] if chain else ""),
                "summary": row["summary"],
                "summarized_count": row["summarized_count"],
                "author_note": _json_loads(row["author_note_json"], {"content": "", "depth": 3, "role": "system", "enabled": True}),
                "group_config": _json_loads(row["group_config_json"], {"enabled": False, "members": [], "mode": "round_robin"}),
                "persona_id": row["persona_id"],
                "preset_id": row["preset_id"],
                "inputs": variables,
                "variables": variables,
                "visited_wb_ids": _json_loads(row["visited_wb_json"], []),
                "cg_unlocked": _json_loads(row["cg_unlocked_json"], []),
                "parent_chat_id": row["parent_chat_id"],
                "active_state": active_state or {},
                "chapters": chapters,
                "messages": messages,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

    def create_chat(
        self,
        chat_id: str,
        project_id: str,
        title: str,
        model: str = "",
        variables: Optional[Dict[str, Any]] = None,
        initial_state: Optional[Dict[str, Any]] = None,
        author_note: Optional[Dict[str, Any]] = None,
        group_config: Optional[Dict[str, Any]] = None,
        persona_id: str = "",
        preset_id: str = "",
        parent_chat_id: str = "",
        init_messages: Optional[List[Dict[str, Any]]] = None,
        summary: str = "",
        summarized_count: int = 0,
        created_at: Optional[float] = None,
        updated_at: Optional[float] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        c_ts = created_at if created_at is not None else now
        u_ts = updated_at if updated_at is not None else now
        vars_dict = dict(variables or {})
        an_dict = author_note or {"content": "", "depth": 3, "role": "system", "enabled": True}
        gc_dict = group_config or {"enabled": False, "members": [], "mode": "round_robin"}
        with self._lock:
            self._conn.execute(
                "INSERT INTO chats(id, project_id, title, model, active_node_id, summary, summarized_count, "
                "author_note_json, group_config_json, persona_id, preset_id, variables_json, visited_wb_json, "
                "cg_unlocked_json, parent_chat_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, '[]', '[]', ?, ?, ?)",
                (
                    chat_id,
                    project_id,
                    title,
                    model,
                    summary,
                    summarized_count,
                    _json_dumps(an_dict),
                    _json_dumps(gc_dict),
                    persona_id,
                    preset_id,
                    _json_dumps(vars_dict),
                    parent_chat_id,
                    c_ts,
                    u_ts,
                ),
            )
            parent_id = ""
            for idx, m in enumerate(init_messages or []):
                nid = str(m.get("id") or f"msg_{uuid.uuid4().hex[:8]}")
                snap = m.get("state_snapshot") if isinstance(m.get("state_snapshot"), dict) else (initial_state or {})
                self._insert_node_and_swipe_unlocked(
                    chat_id=chat_id,
                    node_id=nid,
                    parent_id=parent_id,
                    seq=idx + 1,
                    role=str(m.get("role") or "assistant"),
                    speaker_card_id=str(m.get("speaker_card_id") or ""),
                    speaker_name=str(m.get("speaker_name") or ""),
                    content=str(m.get("content") or ""),
                    prompt_content=str(m.get("prompt_content") or m.get("content") or ""),
                    thinking=str(m.get("thinking") or ""),
                    state_snapshot=snap,
                    state_patch=m.get("state_patch") or {},
                    dice_rolls=m.get("dice_rolls") or [],
                    media_asset_ids=m.get("media_asset_ids") or [],
                    character_cards=m.get("character_cards") or [],
                    triggered_worldbooks=m.get("triggered_worldbooks") or [],
                    triggered_cgs=m.get("triggered_cgs") or [],
                    suggested_questions=m.get("suggested_questions") or [],
                    is_opening=bool(m.get("is_opening", False)),
                    interrupted=bool(m.get("interrupted", False)),
                    created_at=float(m.get("timestamp") or c_ts),
                )
                parent_id = nid
            if parent_id:
                self._conn.execute("UPDATE chats SET active_node_id=? WHERE id=?", (parent_id, chat_id))
            self._conn.commit()
        return self.get_chat_full(chat_id) or {}

    def _insert_node_and_swipe_unlocked(
        self,
        *,
        chat_id: str,
        node_id: str,
        parent_id: str,
        seq: int,
        role: str,
        content: str,
        prompt_content: str,
        thinking: str = "",
        speaker_card_id: str = "",
        speaker_name: str = "",
        state_snapshot: Optional[Dict[str, Any]] = None,
        state_patch: Optional[Dict[str, Any]] = None,
        dice_rolls: Optional[List[Any]] = None,
        media_asset_ids: Optional[List[str]] = None,
        character_cards: Optional[List[Any]] = None,
        triggered_worldbooks: Optional[List[Any]] = None,
        triggered_cgs: Optional[List[Any]] = None,
        suggested_questions: Optional[List[Any]] = None,
        is_opening: bool = False,
        interrupted: bool = False,
        created_at: Optional[float] = None,
    ) -> None:
        ts = created_at if created_at is not None else time.time()
        swipe_id = f"sw_{uuid.uuid4().hex[:10]}"
        self._conn.execute(
            "INSERT INTO message_nodes(id, chat_id, parent_id, seq, role, speaker_card_id, speaker_name, "
            "active_swipe_idx, state_snapshot_json, is_opening, interrupted, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)",
            (
                node_id,
                chat_id,
                parent_id,
                seq,
                role,
                speaker_card_id,
                speaker_name,
                _json_dumps(state_snapshot or {}),
                1 if is_opening else 0,
                1 if interrupted else 0,
                ts,
            ),
        )
        self._conn.execute(
            "INSERT INTO message_swipes(id, node_id, chat_id, swipe_idx, content, prompt_content, thinking, "
            "state_patch_json, dice_rolls_json, media_asset_ids_json, character_cards_json, "
            "triggered_worldbooks_json, triggered_cgs_json, suggested_questions_json, created_at) "
            "VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                swipe_id,
                node_id,
                chat_id,
                content,
                prompt_content,
                thinking,
                _json_dumps(state_patch or {}),
                _json_dumps(dice_rolls or []),
                _json_dumps(media_asset_ids or []),
                _json_dumps(character_cards or []),
                _json_dumps(triggered_worldbooks or []),
                _json_dumps(triggered_cgs or []),
                _json_dumps(suggested_questions or []),
                ts,
            ),
        )
        self._conn.execute(
            "INSERT INTO fts_messages(node_id, chat_id, role, content) VALUES (?, ?, ?, ?)",
            (node_id, chat_id, role, content),
        )

    def append_node(
        self,
        chat_id: str,
        parent_id: str,
        role: str,
        content: str,
        prompt_content: str,
        *,
        node_id: Optional[str] = None,
        thinking: str = "",
        speaker_card_id: str = "",
        speaker_name: str = "",
        state_snapshot: Optional[Dict[str, Any]] = None,
        state_patch: Optional[Dict[str, Any]] = None,
        dice_rolls: Optional[List[Any]] = None,
        media_asset_ids: Optional[List[str]] = None,
        character_cards: Optional[List[Any]] = None,
        triggered_worldbooks: Optional[List[Any]] = None,
        triggered_cgs: Optional[List[Any]] = None,
        suggested_questions: Optional[List[Any]] = None,
        is_opening: bool = False,
        interrupted: bool = False,
        set_active: bool = True,
    ) -> str:
        nid = node_id or f"msg_{uuid.uuid4().hex[:8]}"
        now = time.time()
        with self._lock:
            row_max = self._conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS mseq FROM message_nodes WHERE chat_id=?", (chat_id,)
            ).fetchone()
            next_seq = (int(row_max["mseq"]) if row_max else 0) + 1
            self._insert_node_and_swipe_unlocked(
                chat_id=chat_id,
                node_id=nid,
                parent_id=parent_id,
                seq=next_seq,
                role=role,
                speaker_card_id=speaker_card_id,
                speaker_name=speaker_name,
                content=content,
                prompt_content=prompt_content,
                thinking=thinking,
                state_snapshot=state_snapshot,
                state_patch=state_patch,
                dice_rolls=dice_rolls,
                media_asset_ids=media_asset_ids,
                character_cards=character_cards,
                triggered_worldbooks=triggered_worldbooks,
                triggered_cgs=triggered_cgs,
                suggested_questions=suggested_questions,
                is_opening=is_opening,
                interrupted=interrupted,
                created_at=now,
            )
            if set_active:
                self._conn.execute(
                    "UPDATE chats SET active_node_id=?, updated_at=? WHERE id=?",
                    (nid, now, chat_id),
                )
            else:
                self._conn.execute("UPDATE chats SET updated_at=? WHERE id=?", (now, chat_id))
            self._conn.commit()
        return nid

    def add_swipe(
        self,
        chat_id: str,
        node_id: str,
        content: str,
        prompt_content: str,
        *,
        thinking: str = "",
        state_snapshot: Optional[Dict[str, Any]] = None,
        state_patch: Optional[Dict[str, Any]] = None,
        dice_rolls: Optional[List[Any]] = None,
        triggered_worldbooks: Optional[List[Any]] = None,
        triggered_cgs: Optional[List[Any]] = None,
        suggested_questions: Optional[List[Any]] = None,
        activate: bool = True,
    ) -> int:
        now = time.time()
        with self._lock:
            cnt_row = self._conn.execute(
                "SELECT COALESCE(MAX(swipe_idx), -1) AS mx FROM message_swipes WHERE node_id=?",
                (node_id,),
            ).fetchone()
            new_idx = (int(cnt_row["mx"]) if cnt_row else -1) + 1
            self._conn.execute(
                "INSERT INTO message_swipes(id, node_id, chat_id, swipe_idx, content, prompt_content, thinking, "
                "state_patch_json, dice_rolls_json, media_asset_ids_json, character_cards_json, "
                "triggered_worldbooks_json, triggered_cgs_json, suggested_questions_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', '[]', ?, ?, ?, ?)",
                (
                    f"sw_{uuid.uuid4().hex[:10]}",
                    node_id,
                    chat_id,
                    new_idx,
                    content,
                    prompt_content,
                    thinking,
                    _json_dumps(state_patch or {}),
                    _json_dumps(dice_rolls or []),
                    _json_dumps(triggered_worldbooks or []),
                    _json_dumps(triggered_cgs or []),
                    _json_dumps(suggested_questions or []),
                    now,
                ),
            )
            if activate:
                if state_snapshot is not None:
                    self._conn.execute(
                        "UPDATE message_nodes SET active_swipe_idx=?, state_snapshot_json=? WHERE id=?",
                        (new_idx, _json_dumps(state_snapshot), node_id),
                    )
                else:
                    self._conn.execute(
                        "UPDATE message_nodes SET active_swipe_idx=? WHERE id=?",
                        (new_idx, node_id),
                    )
                self._conn.execute("DELETE FROM fts_messages WHERE node_id=?", (node_id,))
                n_row = self._conn.execute("SELECT role FROM message_nodes WHERE id=?", (node_id,)).fetchone()
                if n_row:
                    self._conn.execute(
                        "INSERT INTO fts_messages(node_id, chat_id, role, content) VALUES (?, ?, ?, ?)",
                        (node_id, chat_id, n_row["role"], content),
                    )
            self._conn.execute("UPDATE chats SET updated_at=? WHERE id=?", (now, chat_id))
            self._conn.commit()
        return new_idx

    def set_active_swipe(self, chat_id: str, node_id: str, swipe_idx: int, new_state_snapshot: Optional[Dict[str, Any]] = None) -> bool:
        with self._lock:
            sw = self._conn.execute(
                "SELECT * FROM message_swipes WHERE node_id=? AND swipe_idx=?", (node_id, swipe_idx)
            ).fetchone()
            if not sw:
                return False
            if new_state_snapshot is not None:
                self._conn.execute(
                    "UPDATE message_nodes SET active_swipe_idx=?, state_snapshot_json=? WHERE id=? AND chat_id=?",
                    (swipe_idx, _json_dumps(new_state_snapshot), node_id, chat_id),
                )
            else:
                self._conn.execute(
                    "UPDATE message_nodes SET active_swipe_idx=? WHERE id=? AND chat_id=?",
                    (swipe_idx, node_id, chat_id),
                )
            self._conn.execute("DELETE FROM fts_messages WHERE node_id=?", (node_id,))
            n_row = self._conn.execute("SELECT role FROM message_nodes WHERE id=?", (node_id,)).fetchone()
            if n_row:
                self._conn.execute(
                    "INSERT INTO fts_messages(node_id, chat_id, role, content) VALUES (?, ?, ?, ?)",
                    (node_id, chat_id, n_row["role"], sw["content"]),
                )
            self._conn.execute("UPDATE chats SET updated_at=? WHERE id=?", (time.time(), chat_id))
            self._conn.commit()
            return True

    def checkout_node(self, chat_id: str, node_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM message_nodes WHERE id=? AND chat_id=?", (node_id, chat_id)
            ).fetchone()
            if not row:
                return False
            self._conn.execute(
                "UPDATE chats SET active_node_id=?, updated_at=? WHERE id=?",
                (node_id, time.time(), chat_id),
            )
            self._conn.commit()
            return True

    def update_active_swipe_content(
        self,
        chat_id: str,
        node_id: str,
        content: str,
        prompt_content: Optional[str] = None,
        state_snapshot: Optional[Dict[str, Any]] = None,
        extra_patch: Optional[Dict[str, Any]] = None,
    ) -> bool:
        with self._lock:
            node = self._conn.execute(
                "SELECT active_swipe_idx, role FROM message_nodes WHERE id=? AND chat_id=?",
                (node_id, chat_id),
            ).fetchone()
            if not node:
                return False
            sw_idx = safe_int(node["active_swipe_idx"], 0)
            p_content = prompt_content if prompt_content is not None else content
            self._conn.execute(
                "UPDATE message_swipes SET content=?, prompt_content=? WHERE node_id=? AND swipe_idx=?",
                (content, p_content, node_id, sw_idx),
            )
            if state_snapshot is not None:
                self._conn.execute(
                    "UPDATE message_nodes SET state_snapshot_json=? WHERE id=?",
                    (_json_dumps(state_snapshot), node_id),
                )
            if extra_patch:
                if "media_asset_ids" in extra_patch:
                    self._conn.execute(
                        "UPDATE message_swipes SET media_asset_ids_json=? WHERE node_id=? AND swipe_idx=?",
                        (_json_dumps(extra_patch["media_asset_ids"]), node_id, sw_idx),
                    )
                if "character_cards" in extra_patch:
                    self._conn.execute(
                        "UPDATE message_swipes SET character_cards_json=? WHERE node_id=? AND swipe_idx=?",
                        (_json_dumps(extra_patch["character_cards"]), node_id, sw_idx),
                    )
            self._conn.execute("DELETE FROM fts_messages WHERE node_id=?", (node_id,))
            self._conn.execute(
                "INSERT INTO fts_messages(node_id, chat_id, role, content) VALUES (?, ?, ?, ?)",
                (node_id, chat_id, node["role"], content),
            )
            self._conn.execute("UPDATE chats SET updated_at=? WHERE id=?", (time.time(), chat_id))
            self._conn.commit()
            return True

    def delete_node_subtree(self, chat_id: str, node_id: str) -> bool:
        with self._lock:
            target = self._conn.execute(
                "SELECT id, parent_id FROM message_nodes WHERE id=? AND chat_id=?",
                (node_id, chat_id),
            ).fetchone()
            if not target:
                return False
            rows = self._conn.execute(
                "SELECT id, parent_id FROM message_nodes WHERE chat_id=?", (chat_id,)
            ).fetchall()
            children_map: Dict[str, List[str]] = {}
            for r in rows:
                children_map.setdefault(r["parent_id"], []).append(r["id"])
            to_del = [node_id]
            stack = [node_id]
            while stack:
                cur = stack.pop()
                for ch in children_map.get(cur, []):
                    to_del.append(ch)
                    stack.append(ch)
            placeholders = ",".join("?" for _ in to_del)
            self._conn.execute(f"DELETE FROM fts_messages WHERE node_id IN ({placeholders})", to_del)
            self._conn.execute(f"DELETE FROM message_nodes WHERE id IN ({placeholders})", to_del)
            chat_row = self._conn.execute("SELECT active_node_id FROM chats WHERE id=?", (chat_id,)).fetchone()
            if chat_row and chat_row["active_node_id"] in to_del:
                self._conn.execute(
                    "UPDATE chats SET active_node_id=?, updated_at=? WHERE id=?",
                    (target["parent_id"], time.time(), chat_id),
                )
            else:
                self._conn.execute("UPDATE chats SET updated_at=? WHERE id=?", (time.time(), chat_id))
            self._conn.commit()
            return True

    def get_branch_tree(self, chat_id: str) -> Dict[str, Any]:
        with self._lock:
            chat_row = self._conn.execute("SELECT active_node_id FROM chats WHERE id=?", (chat_id,)).fetchone()
            if not chat_row:
                return {"active_node_id": "", "nodes": []}
            nodes = self._conn.execute(
                "SELECT mn.*, ms.content, ms.dice_rolls_json FROM message_nodes mn "
                "LEFT JOIN message_swipes ms ON ms.node_id=mn.id AND ms.swipe_idx=mn.active_swipe_idx "
                "WHERE mn.chat_id=? ORDER BY mn.seq ASC, mn.created_at ASC",
                (chat_id,),
            ).fetchall()
            active_chain_ids = {n["id"] for n in self._get_active_chain_rows(chat_id, chat_row["active_node_id"])}
            out = []
            for n in nodes:
                txt = str(n["content"] or "")
                preview = re.sub(r"<[^>]+>", "", txt).strip().replace("\n", " ")[:64]
                out.append(
                    {
                        "id": n["id"],
                        "parent_id": n["parent_id"],
                        "seq": n["seq"],
                        "role": n["role"],
                        "speaker_name": n["speaker_name"],
                        "preview": preview,
                        "on_active_branch": n["id"] in active_chain_ids,
                        "has_dice": bool(_json_loads(n["dice_rolls_json"], [])),
                        "created_at": n["created_at"],
                    }
                )
            return {"active_node_id": chat_row["active_node_id"], "nodes": out}

    def update_chat_meta(self, chat_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()
            if not row:
                return None
            sets = ["updated_at=?"]
            vals: List[Any] = [time.time()]
            direct_map = {
                "title": "title",
                "project_id": "project_id",
                "model": "model",
                "active_node_id": "active_node_id",
                "summary": "summary",
                "summarized_count": "summarized_count",
                "persona_id": "persona_id",
                "preset_id": "preset_id",
            }
            for k, col in direct_map.items():
                if k in patch:
                    sets.append(f"{col}=?")
                    vals.append(patch[k])
            json_map = {
                "author_note": "author_note_json",
                "group_config": "group_config_json",
                "variables": "variables_json",
                "inputs": "variables_json",
                "visited_wb_ids": "visited_wb_json",
                "cg_unlocked": "cg_unlocked_json",
            }
            for k, col in json_map.items():
                if k in patch:
                    sets.append(f"{col}=?")
                    vals.append(_json_dumps(patch[k]))
            vals.append(chat_id)
            self._conn.execute(f"UPDATE chats SET {', '.join(sets)} WHERE id=?", vals)
            self._conn.commit()
        return self.get_chat_full(chat_id)

    def delete_chat(self, chat_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM fts_messages WHERE chat_id=?", (chat_id,))
            self._conn.execute("DELETE FROM prompt_logs WHERE chat_id=?", (chat_id,))
            self._conn.execute("DELETE FROM chats WHERE id=?", (chat_id,))
            self._conn.commit()

    def clear_chat_messages(self, chat_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM fts_messages WHERE chat_id=?", (chat_id,))
            self._conn.execute("DELETE FROM message_nodes WHERE chat_id=?", (chat_id,))
            self._conn.execute("DELETE FROM chapters WHERE chat_id=?", (chat_id,))
            self._conn.execute(
                "UPDATE chats SET active_node_id='', summary='', summarized_count=0, visited_wb_json='[]', updated_at=? WHERE id=?",
                (time.time(), chat_id),
            )
            self._conn.commit()

    # -------------------- Chapters --------------------
    def list_chapters(self, chat_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM chapters WHERE chat_id=? ORDER BY chapter_num ASC", (chat_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def save_chapter(self, chat_id: str, chapter_num: int, title: str, summary: str, up_to_node_id: str = "") -> Dict[str, Any]:
        cid = f"chap_{uuid.uuid4().hex[:8]}"
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO chapters(id, chat_id, chapter_num, title, summary, up_to_node_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (cid, chat_id, chapter_num, title, summary, up_to_node_id, now),
            )
            self._conn.commit()
        return {"id": cid, "chat_id": chat_id, "chapter_num": chapter_num, "title": title, "summary": summary, "up_to_node_id": up_to_node_id, "created_at": now}

    # -------------------- Character Cards --------------------
    def list_cards(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT data_json FROM character_cards ORDER BY updated_at DESC").fetchall()
            return [_json_loads(r["data_json"], {}) for r in rows]

    def get_card(self, card_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT data_json FROM character_cards WHERE id=?", (card_id,)).fetchone()
            return _json_loads(row["data_json"], {}) if row else None

    def save_card(self, card: Dict[str, Any]) -> Dict[str, Any]:
        cid = str(card.get("id") or f"card_{uuid.uuid4().hex[:8]}")
        card_out = dict(card)
        card_out["id"] = cid
        now = time.time()
        card_out.setdefault("created_at", now)
        card_out["updated_at"] = now
        name = str(card_out.get("name") or "未命名角色")
        desc = str(card_out.get("description") or card_out.get("personality") or "")
        with self._lock:
            self._conn.execute(
                "INSERT INTO character_cards(id, name, avatar_asset_id, data_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
                "avatar_asset_id=excluded.avatar_asset_id, data_json=excluded.data_json, updated_at=excluded.updated_at",
                (cid, name, str(card_out.get("avatar_asset_id") or ""), _json_dumps(card_out), card_out["created_at"], now),
            )
            self._conn.execute("DELETE FROM fts_cards WHERE card_id=?", (cid,))
            self._conn.execute(
                "INSERT INTO fts_cards(card_id, name, description) VALUES (?, ?, ?)",
                (cid, name, desc),
            )
            self._conn.commit()
        return card_out

    def delete_card(self, card_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM character_cards WHERE id=?", (card_id,))
            self._conn.execute("DELETE FROM fts_cards WHERE card_id=?", (card_id,))
            self._conn.commit()

    # -------------------- Personas --------------------
    def list_personas(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM personas ORDER BY is_default DESC, updated_at DESC"
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "avatar_asset_id": r["avatar_asset_id"],
                    "description": r["description"],
                    "is_default": bool(r["is_default"]),
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                }
                for r in rows
            ]

    def save_persona(self, persona: Dict[str, Any]) -> Dict[str, Any]:
        pid = str(persona.get("id") or f"per_{uuid.uuid4().hex[:8]}")
        now = time.time()
        is_def = bool(persona.get("is_default", False))
        with self._lock:
            if is_def:
                self._conn.execute("UPDATE personas SET is_default=0")
            self._conn.execute(
                "INSERT INTO personas(id, name, avatar_asset_id, description, is_default, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
                "avatar_asset_id=excluded.avatar_asset_id, description=excluded.description, "
                "is_default=excluded.is_default, updated_at=excluded.updated_at",
                (
                    pid,
                    str(persona.get("name") or "冒险者"),
                    str(persona.get("avatar_asset_id") or ""),
                    str(persona.get("description") or ""),
                    1 if is_def else 0,
                    float(persona.get("created_at") or now),
                    now,
                ),
            )
            self._conn.commit()
        return next((p for p in self.list_personas() if p["id"] == pid), {})

    def delete_persona(self, persona_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM personas WHERE id=?", (persona_id,))
            self._conn.commit()

    # -------------------- Presets (Prompt Manager / ST Presets) --------------------
    def list_presets(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM presets ORDER BY is_default DESC, updated_at DESC").fetchall()
            out = []
            for r in rows:
                d = _json_loads(r["data_json"], {})
                d["id"] = r["id"]
                d["name"] = r["name"]
                d["is_default"] = bool(r["is_default"])
                out.append(d)
            return out

    def get_preset(self, preset_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            r = self._conn.execute("SELECT * FROM presets WHERE id=?", (preset_id,)).fetchone()
            if not r:
                return None
            d = _json_loads(r["data_json"], {})
            d["id"] = r["id"]
            d["name"] = r["name"]
            d["is_default"] = bool(r["is_default"])
            return d

    def save_preset(self, preset: Dict[str, Any]) -> Dict[str, Any]:
        pid = str(preset.get("id") or f"preset_{uuid.uuid4().hex[:8]}")
        now = time.time()
        is_def = bool(preset.get("is_default", False))
        p_out = dict(preset)
        p_out["id"] = pid
        name = str(p_out.get("name") or "默认预设")
        with self._lock:
            if is_def:
                self._conn.execute("UPDATE presets SET is_default=0")
            self._conn.execute(
                "INSERT INTO presets(id, name, data_json, is_default, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
                "data_json=excluded.data_json, is_default=excluded.is_default, updated_at=excluded.updated_at",
                (pid, name, _json_dumps(p_out), 1 if is_def else 0, float(p_out.get("created_at") or now), now),
            )
            self._conn.commit()
        return p_out

    def delete_preset(self, preset_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM presets WHERE id=?", (preset_id,))
            self._conn.commit()

    # -------------------- Gallery --------------------
    def list_gallery(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM gallery_assets ORDER BY created_at DESC").fetchall()
            out = []
            for r in rows:
                item = dict(r)
                is_vid = str(r["id"]).startswith("vid_")
                item["media_type"] = "video" if is_vid else "image"
                item["url"] = f"/api/gallery/video/{r['id']}" if is_vid else f"/api/gallery/image/{r['id']}"
                item["thumb_url"] = f"/api/gallery/thumb/{r['id']}"
                out.append(item)
            return out

    def find_gallery_by_sha256(self, sha: str) -> Optional[Dict[str, Any]]:
        if not sha:
            return None
        with self._lock:
            r = self._conn.execute("SELECT * FROM gallery_assets WHERE sha256=? LIMIT 1", (sha,)).fetchone()
            return dict(r) if r else None

    def upsert_gallery_asset(self, entry: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO gallery_assets(id, filename, folder, sha256, vhash, width, height, size_bytes, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "filename=excluded.filename, folder=excluded.folder, sha256=excluded.sha256, "
                "vhash=excluded.vhash, width=excluded.width, height=excluded.height, size_bytes=excluded.size_bytes",
                (
                    entry["id"],
                    entry.get("filename", f"{entry['id']}.jpg"),
                    entry.get("folder", "默认图库"),
                    entry.get("sha256", ""),
                    entry.get("vhash", ""),
                    int(entry.get("width", 0)),
                    int(entry.get("height", 0)),
                    int(entry.get("size_bytes", 0)),
                    float(entry.get("created_at", time.time())),
                ),
            )
            self._conn.commit()

    def delete_gallery_asset(self, img_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM gallery_assets WHERE id=?", (img_id,))
            self._conn.commit()

    def list_gallery_folders(self) -> List[str]:
        with self._lock:
            rows = self._conn.execute("SELECT name FROM gallery_folders ORDER BY sort_order ASC, name ASC").fetchall()
            folders = [r["name"] for r in rows]
            if "默认图库" not in folders:
                folders.insert(0, "默认图库")
            return folders

    def save_gallery_folders(self, folders: List[str]) -> List[str]:
        clean = ["默认图库"]
        for f in folders:
            s = str(f or "").strip()
            if s and s not in clean:
                clean.append(s)
        with self._lock:
            self._conn.execute("DELETE FROM gallery_folders")
            for idx, name in enumerate(clean):
                self._conn.execute("INSERT INTO gallery_folders(name, sort_order) VALUES (?, ?)", (name, idx))
            self._conn.commit()
        return clean

    def move_gallery_assets(self, ids: List[str], folder: str) -> int:
        if not ids:
            return 0
        with self._lock:
            self._conn.execute("INSERT OR IGNORE INTO gallery_folders(name, sort_order) VALUES (?, 99)", (folder,))
            placeholders = ",".join("?" for _ in ids)
            cur = self._conn.execute(
                f"UPDATE gallery_assets SET folder=? WHERE id IN ({placeholders})", [folder] + ids
            )
            self._conn.commit()
            return cur.rowcount

    # -------------------- Prompt Logs --------------------
    def save_prompt_log(self, chat_id: str, node_id: str, log_dict: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO prompt_logs(chat_id, node_id, log_json, created_at) VALUES (?, ?, ?, ?)",
                (chat_id, node_id, _json_dumps(log_dict), time.time()),
            )
            # Keep last 25 logs per chat
            self._conn.execute(
                "DELETE FROM prompt_logs WHERE chat_id=? AND id NOT IN "
                "(SELECT id FROM prompt_logs WHERE chat_id=? ORDER BY id DESC LIMIT 25)",
                (chat_id, chat_id),
            )
            self._conn.commit()

    def get_latest_prompt_log(self, chat_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            r = self._conn.execute(
                "SELECT log_json FROM prompt_logs WHERE chat_id=? ORDER BY id DESC LIMIT 1", (chat_id,)
            ).fetchone()
            return _json_loads(r["log_json"], None) if r else None

    # -------------------- Full-Text Search (FTS5 + CJK LIKE fallback) --------------------
    def search_fts(
        self,
        query: str,
        scope: str = "all",
        chat_id: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, List[Dict[str, Any]]]:
        q = str(query or "").strip()
        if not q:
            return {"messages": [], "projects": [], "cards": []}
        tokens = [re.sub(r'["\'*()]', "", t) for t in re.split(r"\s+", q) if t.strip()]
        fts_expr = " ".join(f'"{t}"*' for t in tokens if t)
        like_pat = f"%{q}%"
        results: Dict[str, List[Dict[str, Any]]] = {"messages": [], "projects": [], "cards": []}

        with self._lock:
            if scope in ("all", "messages"):
                rows: List[sqlite3.Row] = []
                if fts_expr:
                    try:
                        sql = (
                            "SELECT f.node_id, f.chat_id, f.role, f.content, c.title AS chat_title, c.project_id "
                            "FROM fts_messages f JOIN chats c ON c.id=f.chat_id "
                            "WHERE fts_messages MATCH ?"
                        )
                        params: List[Any] = [fts_expr]
                        if chat_id:
                            sql += " AND f.chat_id=?"
                            params.append(chat_id)
                        sql += " ORDER BY bm25(fts_messages) LIMIT ?"
                        params.append(limit)
                        rows = self._conn.execute(sql, params).fetchall()
                    except sqlite3.OperationalError:
                        rows = []
                if not rows:
                    sql = (
                        "SELECT mn.id AS node_id, mn.chat_id, mn.role, ms.content, c.title AS chat_title, c.project_id "
                        "FROM message_nodes mn "
                        "JOIN message_swipes ms ON ms.node_id=mn.id AND ms.swipe_idx=mn.active_swipe_idx "
                        "JOIN chats c ON c.id=mn.chat_id "
                        "WHERE ms.content LIKE ?"
                    )
                    params = [like_pat]
                    if chat_id:
                        sql += " AND mn.chat_id=?"
                        params.append(chat_id)
                    sql += " ORDER BY mn.created_at DESC LIMIT ?"
                    params.append(limit)
                    rows = self._conn.execute(sql, params).fetchall()
                results["messages"] = [
                    {
                        "node_id": r["node_id"],
                        "chat_id": r["chat_id"],
                        "chat_title": r["chat_title"],
                        "project_id": r["project_id"],
                        "role": r["role"],
                        "snippet": str(r["content"] or "")[:180],
                    }
                    for r in rows
                ]

            if scope in ("all", "projects"):
                prows = self._conn.execute(
                    "SELECT id, name, category FROM projects WHERE name LIKE ? OR data_json LIKE ? LIMIT ?",
                    (like_pat, like_pat, limit),
                ).fetchall()
                results["projects"] = [dict(r) for r in prows]

            if scope in ("all", "cards"):
                crows = self._conn.execute(
                    "SELECT id, name FROM character_cards WHERE name LIKE ? OR data_json LIKE ? LIMIT ?",
                    (like_pat, like_pat, limit),
                ).fetchall()
                results["cards"] = [dict(r) for r in crows]

        return results


def get_user_db(username: str) -> UserDatabase:
    with _DB_CACHE_LOCK:
        db = _USER_DBS.get(username)
        if db is None:
            db = UserDatabase(username)
            _USER_DBS[username] = db
        return db


def reset_db_cache() -> None:
    with _DB_CACHE_LOCK:
        for db in _USER_DBS.values():
            try:
                db.close()
            except Exception:
                pass
        _USER_DBS.clear()
