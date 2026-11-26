# -*- coding: utf-8 -*-
"""Tests for 3-layer KV-cache prefix stability, 25% chunked eviction, and ST preset import."""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

import backend.config as cfg
import backend.core.security as sec
from backend.core.prompt_builder import (
    _select_history_chunked,
    assemble_kv_friendly_prompt,
    import_sillytavern_preset,
)
from backend.storage.db import get_user_db, reset_db_cache


class KvCachePromptTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.users_dir = Path(self._tmp.name) / "users"
        self.users_dir.mkdir(parents=True, exist_ok=True)
        self._orig_cfg = cfg.USERS_DIR
        self._orig_sec = sec.USERS_DIR
        cfg.USERS_DIR = self.users_dir
        sec.USERS_DIR = self.users_dir
        reset_db_cache()

    def tearDown(self) -> None:
        reset_db_cache()
        cfg.USERS_DIR = self._orig_cfg
        sec.USERS_DIR = self._orig_sec
        self._tmp.cleanup()

    def test_layer0_prefix_remains_byte_identical_across_turns(self) -> None:
        db = get_user_db("kv_user")
        proj = cfg.normalize_project_schema(
            {
                "id": "proj_kv",
                "name": "灰钟剧本",
                "system_prompt": "你是灰钟小镇的严谨主持人。",
                "world_book": [
                    {
                        "id": "wb_const",
                        "name": "常驻铁律",
                        "constant": True,
                        "keys": [],
                        "content": "魔导蒸汽引擎消耗灰晶运行。",
                        "enabled": True,
                    },
                    {
                        "id": "wb_dyn",
                        "name": "密室暗门",
                        "constant": False,
                        "keys": ["机关铜钥匙"],
                        "content": "铜钥匙可以打开钟楼地下三层暗门。",
                        "enabled": True,
                    },
                ],
            }
        )
        db.save_project(proj)
        chat = db.create_chat("chat_kv_1", "proj_kv", title="KV稳定测试")
        cid = chat["id"]

        settings = dict(cfg.DEFAULT_SETTINGS)
        # Turn 1 (dynamic keyword NOT present)
        msgs1, log1, _ = asyncio.run(
            assemble_kv_friendly_prompt(
                db=db,
                username="kv_user",
                project_data=proj,
                chat_data=db.get_chat_full(cid),
                settings=settings,
                user_display_text="我先在广场观察四周人群。",
                turn_images=[],
                turn_char_cards=[],
            )
        )
        u_nid = db.append_node(
            cid,
            "",
            "user",
            "我先在广场观察四周人群。",
            "我先在广场观察四周人群。",
        )
        db.append_node(
            cid,
            u_nid,
            "assistant",
            "雾雨落在青石板上。",
            "雾雨落在青石板上。",
        )

        # Turn 2 (triggers dynamic worldbook keyword "机关铜钥匙")
        msgs2, log2, _ = asyncio.run(
            assemble_kv_friendly_prompt(
                db=db,
                username="kv_user",
                project_data=proj,
                chat_data=db.get_chat_full(cid),
                settings=settings,
                user_display_text="我掏出机关铜钥匙仔细端详。",
                turn_images=[],
                turn_char_cards=[],
            )
        )

        self.assertEqual(msgs1[0]["role"], "system")
        self.assertEqual(msgs2[0]["role"], "system")
        # Layer 0 prefix must be 100% byte-identical even though Turn 2 triggered dynamic worldbook!
        self.assertEqual(msgs1[0]["content"], msgs2[0]["content"])
        self.assertNotIn("钟楼地下三层暗门", msgs2[0]["content"])
        # Dynamic worldbook appears in Layer 2 tail instead
        joined_tail = "\n".join(str(m.get("content") or "") for m in msgs2[1:])
        self.assertIn("钟楼地下三层暗门", joined_tail)
        self.assertTrue(any(w.get("name") == "密室暗门" for w in log2["triggered_worldbooks"]))
        self.assertEqual(log1["immutable_prefix_tokens"], log2["immutable_prefix_tokens"])

    def test_chunked_eviction_watermarks_history(self) -> None:
        long_block = "这是一个足够长用来触发上下文预算淘汰机制的历史段落。" * 18
        hist = [
            {"role": "user" if i % 2 == 0 else "assistant", "prompt_content": f"Turn-{i}: {long_block}"}
            for i in range(16)
        ]
        # budget = 4*1024 - 3000 = 1096 tokens (~75% target = 822 tokens)
        selected = _select_history_chunked(
            hist,
            context_mode="tokens",
            max_turns=96,
            max_context_k=4,
            fixed_overhead_tokens=3000,
            keep_recent_msgs=4,
        )
        self.assertLess(len(selected), len(hist))
        self.assertGreaterEqual(len(selected), 4)
        self.assertEqual(selected[-1]["prompt_content"], hist[-1]["prompt_content"])

    def test_sillytavern_preset_import(self) -> None:
        raw = {
            "name": "ST-Clarity",
            "temperature": 0.85,
            "top_p": 0.92,
            "openai_max_tokens": 6000,
            "prompts": [
                {"identifier": "main", "name": "主规则", "role": "system", "content": "保持冷峻叙事"},
                {"identifier": "disabled_blk", "name": "停用块", "role": "system", "content": "不该出现"},
            ],
            "prompt_order": [
                {
                    "character_id": 100000,
                    "order": [
                        {"identifier": "main", "enabled": True},
                        {"identifier": "disabled_blk", "enabled": False},
                    ],
                }
            ],
        }
        preset = import_sillytavern_preset(raw)
        self.assertEqual(preset["name"], "ST-Clarity")
        self.assertEqual(preset["max_tokens"], 6000)
        self.assertEqual(len(preset["custom_blocks"]), 1)
        self.assertEqual(preset["custom_blocks"][0]["id"], "main")


if __name__ == "__main__":
    unittest.main()
