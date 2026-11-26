# -*- coding: utf-8 -*-
"""Tests for cryptographic dice, deterministic TRPG state patches, legacy <status>, and stream parsing."""
from __future__ import annotations

import unittest

from backend.trpg.dice import roll_dice_expression
from backend.trpg.state_engine import apply_ai_output_to_state, empty_game_state
from backend.trpg.stream_parser import (
    build_prompt_frozen_content,
    detect_and_trim_stream_loop,
    extract_action_choices,
    extract_thinking_block,
)


class TrpgEngineTests(unittest.TestCase):
    def test_cryptographic_dice_variants(self) -> None:
        r1 = roll_dice_expression("1d20+3", ruleset="d20", difficulty=12, skill_name="潜行")
        self.assertEqual(len(r1["rolls"]), 1)
        self.assertEqual(r1["modifier"], 3)
        self.assertEqual(r1["total"], r1["rolls"][0] + 3)

        r_adv = roll_dice_expression("adv", ruleset="d20", difficulty=15)
        self.assertEqual(len(r_adv["rolls"]), 2)
        self.assertEqual(r_adv["kept"], [max(r_adv["rolls"])])

        r_dis = roll_dice_expression("dis", ruleset="d20", difficulty=15)
        self.assertEqual(len(r_dis["rolls"]), 2)
        self.assertEqual(r_dis["kept"], [min(r_dis["rolls"])])

        r_coc = roll_dice_expression("1d100", ruleset="d100", difficulty=60)
        self.assertTrue(1 <= r_coc["total"] <= 100)

        r_pbta = roll_dice_expression("2d6", ruleset="2d6")
        self.assertTrue(2 <= r_pbta["total"] <= 12)

    def test_state_patch_and_legacy_status_parsing(self) -> None:
        init = empty_game_state(
            {
                "resources": [{"key": "hp", "label": "生命", "current": 100, "max": 100}],
                "inventory": [{"name": "火把", "qty": 2, "desc": "照明"}],
                "npcs": [{"name": "希尔薇", "affinity": 40, "relation": "警惕"}],
            }
        )
        ai_patch_out = (
            "你闪避不及，肩头被划开。\n"
            "<state_patch>"
            '{"resources_delta":{"hp":-25},"inv_add":[{"name":"铜钥匙","qty":1}],"inv_remove":[{"name":"火把","qty":1}],'
            '"npc_upsert":[{"name":"希尔薇","affinity_delta":15,"status":"替你包扎"}],"equip":{"主手":"短剑"},'
            '"clock_delta":{"警戒度":2},'
            '"scene_set":{"location":"钟楼二层"}}'
            "</state_patch>\n"
            "1. 举剑迎敌 【🎲近战检定】\n"
            "2. 拉着希尔薇撤退"
        )
        next_st, patch = apply_ai_output_to_state(init, ai_patch_out)
        self.assertIsNotNone(patch)
        self.assertEqual(next_st["resources"][0]["current"], 75)
        self.assertEqual({x["name"]: x["qty"] for x in next_st["inventory"]}, {"火把": 1, "铜钥匙": 1})
        self.assertEqual(next_st["npcs"][0]["affinity"], 55)
        self.assertEqual(next_st["equipment"]["主手"]["name"], "短剑")
        self.assertEqual(next_st["clocks"][0]["current"], 2)
        self.assertEqual(next_st["scene"]["location"], "钟楼二层")

        # Legacy <status> fallback parsing
        legacy_out = (
            "<status>\n"
            "[主角状态]\n"
            "生命: 60/100\n"
            "[物品栏]\n"
            "急救包(止血)x1\n"
            "[角色关系]\n"
            "角色: 雷恩\n"
            "好感: 70/100\n"
            "</status>"
        )
        st_leg, patch_none = apply_ai_output_to_state(empty_game_state(), legacy_out)
        self.assertIsNone(patch_none)
        self.assertEqual(st_leg["resources"][0]["current"], 60)
        self.assertEqual(st_leg["inventory"][0]["name"], "急救包")
        self.assertEqual(st_leg["npcs"][0]["affinity"], 70)

    def test_stream_parser_think_freeze_choices_and_loop(self) -> None:
        raw = (
            "<think>先计算敌人伤害</think>\n"
            "风雪交加。<state_patch>{\"resources_delta\":{\"hp\":-5}}</state_patch>\n"
            "你打算怎么做？\n"
            "1. 冲入暴雪 【🎲体质检定】\n"
            "2. 躲进马厩"
        )
        think, rest = extract_thinking_block(raw)
        self.assertEqual(think, "先计算敌人伤害")
        self.assertIn("风雪交加", rest)

        frozen = build_prompt_frozen_content(raw)
        self.assertNotIn("<think>", frozen)
        self.assertNotIn("<state_patch>", frozen)

        choices = extract_action_choices(raw)
        self.assertEqual(len(choices), 2)
        self.assertEqual(choices[0]["dice_skill"], "体质检定")

        rep_line = "这是一段用于验证本地模型流式退化循环拦截的长句文本。"
        loop_text = "正常开头叙事……\n" + "\n".join([rep_line] * 18)
        trimmed, hit = detect_and_trim_stream_loop(loop_text)
        self.assertTrue(hit)
        self.assertLess(len(trimmed), len(loop_text))


if __name__ == "__main__":
    unittest.main()
