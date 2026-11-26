# -*- coding: utf-8 -*-
"""End-to-end FastAPI TestClient verification in an isolated temp workspace."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import backend.config as cfg
import backend.core.auth as core_auth
import backend.core.security as sec
import backend.storage.backup as bkp
from backend.app import create_app
from backend.storage.db import reset_db_cache


class ApiE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name) / "data"
        self.users_dir = self.data_dir / "users"
        self.backup_dir = Path(self._tmp.name) / "backups"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.users_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self._saved = {
            "cfg_data": cfg.DATA_DIR,
            "cfg_users": cfg.USERS_DIR,
            "cfg_ufile": cfg.USERS_FILE,
            "cfg_sfile": cfg.SESSIONS_FILE,
            "sec_users": sec.USERS_DIR,
            "auth_ufile": core_auth.USERS_FILE,
            "auth_sfile": core_auth.SESSIONS_FILE,
            "bkp_root": bkp.BACKUP_ROOT_DIR,
        }
        cfg.DATA_DIR = self.data_dir
        cfg.USERS_DIR = self.users_dir
        cfg.USERS_FILE = self.data_dir / "users.json"
        cfg.SESSIONS_FILE = self.data_dir / "sessions.json"
        sec.USERS_DIR = self.users_dir
        core_auth.USERS_FILE = self.data_dir / "users.json"
        core_auth.SESSIONS_FILE = self.data_dir / "sessions.json"
        bkp.BACKUP_ROOT_DIR = self.backup_dir
        core_auth.SESSIONS.clear()
        reset_db_cache()

        self.client_ctx = TestClient(create_app())
        self.client = self.client_ctx.__enter__()
        self.hdr = {"Origin": "http://testserver"}

    def tearDown(self) -> None:
        self.client_ctx.__exit__(None, None, None)
        core_auth.SESSIONS.clear()
        reset_db_cache()
        cfg.DATA_DIR = self._saved["cfg_data"]
        cfg.USERS_DIR = self._saved["cfg_users"]
        cfg.USERS_FILE = self._saved["cfg_ufile"]
        cfg.SESSIONS_FILE = self._saved["cfg_sfile"]
        sec.USERS_DIR = self._saved["sec_users"]
        core_auth.USERS_FILE = self._saved["auth_ufile"]
        core_auth.SESSIONS_FILE = self._saved["auth_sfile"]
        bkp.BACKUP_ROOT_DIR = self._saved["bkp_root"]
        self._tmp.cleanup()

    def test_full_api_smoke_flow(self) -> None:
        r_root = self.client.get("/")
        self.assertEqual(r_root.status_code, 200)
        self.assertIn("/static/assets/", r_root.text)

        r_ver = self.client.get("/api/system/version")
        self.assertEqual(r_ver.status_code, 200)
        self.assertEqual(cfg.APP_VERSION, "alpha 2.0")
        self.assertEqual(r_ver.json()["version"], cfg.APP_VERSION)

        r_pre = self.client.get("/api/system/preflight")
        self.assertEqual(r_pre.status_code, 200)
        self.assertIn("hardware", r_pre.json())

        # Explore returns 5 handcrafted flagship campaigns
        r_exp = self.client.get("/api/explore")
        self.assertEqual(r_exp.status_code, 200)
        apps = r_exp.json()["apps"]
        self.assertEqual(len(apps), 5)

        r_inst = self.client.post("/api/explore/install", json={"app_id": "camp_ashbell"}, headers=self.hdr)
        self.assertEqual(r_inst.status_code, 200)
        inst_data = r_inst.json()
        self.assertEqual(inst_data["project"]["id"], "camp_ashbell")
        chat_id = inst_data["chat_id"]

        # Dice roll attached to chat
        r_roll = self.client.post(
            f"/api/chats/{chat_id}/roll",
            json={"expression": "1d20+2", "difficulty": 12, "skill": "潜行"},
            headers=self.hdr,
        )
        self.assertEqual(r_roll.status_code, 200)
        self.assertIn("total", r_roll.json()["roll"])

        # Models, settings, personas, presets
        self.assertEqual(self.client.get("/api/models").status_code, 200)
        r_set = self.client.get("/api/settings")
        self.assertEqual(r_set.status_code, 200)
        self.assertEqual(r_set.json()["experience_mode"], "simple")
        r_put_s = self.client.post("/api/settings", json={"experience_mode": "pro"}, headers=self.hdr)
        self.assertEqual(r_put_s.status_code, 200)
        self.assertEqual(self.client.get("/api/settings").json()["experience_mode"], "pro")

        self.assertEqual(self.client.get("/api/personas").status_code, 200)
        self.assertEqual(self.client.get("/api/presets").status_code, 200)

        # Create project & chat directly
        r_proj = self.client.post(
            "/api/projects",
            json={"name": "测试自定义剧本", "system_prompt": "测试主持"},
            headers=self.hdr,
        )
        self.assertEqual(r_proj.status_code, 200)
        new_pid = r_proj.json()["project"]["id"]
        r_chat = self.client.post("/api/chats", json={"project_id": new_pid, "title": "测试开局"}, headers=self.hdr)
        self.assertEqual(r_chat.status_code, 200)

        # Cross-origin POST must be blocked by CSRF guard (403)
        r_csrf = self.client.post("/api/settings", json={"theme": "lamplight-light"}, headers={"Origin": "https://evil.example"})
        self.assertEqual(r_csrf.status_code, 403)

        # Register + HttpOnly cookie login
        r_reg = self.client.post("/api/auth/register", json={"username": "admin1", "password": "secretpassword"}, headers=self.hdr)
        self.assertEqual(r_reg.status_code, 200)
        r_login = self.client.post("/api/auth/login", json={"username": "admin1", "password": "secretpassword"}, headers=self.hdr)
        self.assertEqual(r_login.status_code, 200)
        set_cookie = r_login.headers.get("set-cookie", "").lower()
        self.assertIn("session_token=", set_cookie)
        self.assertIn("httponly", set_cookie)

        # Video upload, Range/stream fetch, gallery listing, and cleanup
        sample_mp4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"VIDEO_DATA" * 8
        r_vid = self.client.post(
            "/api/gallery/upload_video",
            files={"file": ("clip.mp4", sample_mp4, "video/mp4")},
            data={"folder": "视频素材"},
            headers=self.hdr,
        )
        self.assertEqual(r_vid.status_code, 200)
        vid_info = r_vid.json()
        self.assertTrue(vid_info["id"].startswith("vid_"))
        self.assertEqual(vid_info["media_type"], "video")

        r_vid_get = self.client.get(vid_info["url"])
        self.assertEqual(r_vid_get.status_code, 200)
        self.assertEqual(r_vid_get.content, sample_mp4)

        gal = self.client.get("/api/gallery").json()
        self.assertTrue(any(g["id"] == vid_info["id"] and g.get("media_type") == "video" for g in gal))

        r_vid_del = self.client.delete(f"/api/gallery/{vid_info['id']}", headers=self.hdr)
        self.assertEqual(r_vid_del.status_code, 200)
        self.assertEqual(self.client.get(vid_info["url"]).status_code, 404)


if __name__ == "__main__":
    unittest.main()
