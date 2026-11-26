# -*- coding: utf-8 -*-
"""Tests for non-destructive v1.x -> SQLite WAL/FTS5 migration & real data compatibility."""
from __future__ import annotations

import base64
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import backend.config as cfg
import backend.core.security as sec
from backend.storage.db import get_user_db, reset_db_cache
from backend.storage.migrator import migrate_v1_directory_into_db


def _make_sample_data_uri(color: tuple[int, int, int] = (180, 40, 40)) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (24, 24), color=color).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


class MigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.users_dir = self.root / "users"
        self.users_dir.mkdir(parents=True, exist_ok=True)
        self._orig_cfg_users = cfg.USERS_DIR
        self._orig_sec_users = sec.USERS_DIR
        cfg.USERS_DIR = self.users_dir
        sec.USERS_DIR = self.users_dir
        reset_db_cache()

    def tearDown(self) -> None:
        reset_db_cache()
        cfg.USERS_DIR = self._orig_cfg_users
        sec.USERS_DIR = self._orig_sec_users
        self._tmp.cleanup()

    def test_synthetic_v1_migration_is_idempotent_and_non_destructive(self) -> None:
        u_dir = self.users_dir / "player"
        (u_dir / "projects").mkdir(parents=True, exist_ok=True)
        (u_dir / "chats").mkdir(parents=True, exist_ok=True)
        (u_dir / "presets").mkdir(parents=True, exist_ok=True)

        (u_dir / "settings.json").write_text(
            json.dumps({"model": "legacy-model-v1", "temperature": 0.72, "max_context_k": 32}),
            encoding="utf-8",
        )
        (u_dir / "gallery_folders.json").write_text(
            json.dumps([{"id": "默认图库", "name": "默认图库", "system": True}, {"id": "旧相册", "name": "旧相册"}]),
            encoding="utf-8",
        )
        (u_dir / "character_cards.json").write_text(
            json.dumps([{"id": "card_test1", "name": "艾琳", "description": "银发骑士"}]),
            encoding="utf-8",
        )
        (u_dir / "presets" / "preset_1.json").write_text(
            json.dumps({"id": "preset_1", "name": "叙事预设", "temperature": 0.65}),
            encoding="utf-8",
        )
        proj_path = u_dir / "projects" / "proj_legacy.json"
        proj_path.write_text(
            json.dumps(
                {
                    "id": "proj_legacy",
                    "name": "旧版黑塔剧本",
                    "system_prompt": "你是黑塔主持人",
                    "world_book": [{"id": "wb1", "keys": ["黑塔"], "content": "黑塔有三层封印"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        img_uri = _make_sample_data_uri()
        chat_path = u_dir / "chats" / "chat_old1.json"
        chat_path.write_text(
            json.dumps(
                {
                    "id": "chat_old1",
                    "project_id": "proj_legacy",
                    "title": "旧版黑塔探索",
                    "variables": {"user": "旅人"},
                    "messages": [
                        {"id": "m1", "role": "user", "content": "查看黑塔大门", "images": [img_uri]},
                        {
                            "id": "m2",
                            "role": "assistant",
                            "content": "<think>思考中</think>铁门缓缓开启，露出古代符文。\n1. 推门进入\n2. 原地警戒",
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        db = get_user_db("player")
        counts = migrate_v1_directory_into_db(db, u_dir)
        self.assertGreaterEqual(counts["projects"], 1)
        self.assertEqual(counts["chats"], 1)
        self.assertEqual(counts["messages"], 2)
        self.assertEqual(counts["cards"], 1)
        self.assertEqual(counts["presets"], 1)

        # Idempotent second run should skip
        second = migrate_v1_directory_into_db(db, u_dir)
        self.assertEqual(second.get("skipped"), 1)

        # Source JSON files must remain untouched on disk
        self.assertTrue(proj_path.is_file())
        self.assertTrue(chat_path.is_file())

        # Base64 images deduplicated & extracted to gallery
        gallery_items = db.list_gallery()
        self.assertEqual(len(gallery_items), 1)
        self.assertEqual(db.get_settings()["model"], "legacy-model-v1")
        chat = db.get_chat_full("chat_old1")
        self.assertIsNotNone(chat)
        self.assertEqual(len(chat["messages"]), 2)
        self.assertEqual(len(chat["messages"][0]["media_asset_ids"]), 1)

        # FTS5 search finds migrated dialogue
        search_res = db.search_fts("符文")
        self.assertGreaterEqual(len(search_res["messages"]), 1)

    def test_real_personal_workbench_data_migrates_in_temp_sandbox(self) -> None:
        raw_env = os.environ.get("EASY_TRPG_MIGRATION_SAMPLE_DIR", "").strip()
        if not raw_env:
            self.skipTest("Set EASY_TRPG_MIGRATION_SAMPLE_DIR to run real-data sandbox migration test")
        real_player_dir = Path(raw_env)
        if not real_player_dir.is_dir():
            self.skipTest("Configured migration sample directory not present on this machine")

        src_copy = self.root / "readonly_snapshot_player"
        shutil.copytree(
            real_player_dir,
            src_copy,
            ignore=shutil.ignore_patterns("trpg.db*", "*.db-wal", "*.db-shm"),
        )
        raw_projects = list((src_copy / "projects").glob("*.json")) if (src_copy / "projects").is_dir() else []
        raw_chats = list((src_copy / "chats").glob("*.json")) if (src_copy / "chats").is_dir() else []

        db = get_user_db("player_sandbox")
        counts = migrate_v1_directory_into_db(db, src_copy, force=True)

        self.assertGreaterEqual(counts["projects"], len(raw_projects))
        self.assertGreaterEqual(counts["chats"], len(raw_chats))
        migrated_chats = db.list_chats()
        self.assertEqual(len(migrated_chats), counts["chats"])
        if migrated_chats:
            sample = db.get_chat_full(migrated_chats[0]["id"])
            self.assertIsNotNone(sample)
            self.assertIn("messages", sample)
            ft = db.search_fts("a")
            self.assertIsInstance(ft, dict)


if __name__ == "__main__":
    unittest.main()
