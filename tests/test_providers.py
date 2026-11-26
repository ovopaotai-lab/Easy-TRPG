# -*- coding: utf-8 -*-
"""Tests for native Anthropic, Gemini (BLOCK_NONE), and protocol auto-routing adapters."""
from __future__ import annotations

import unittest

from backend.providers.anthropic_adapter import build_anthropic_payload
from backend.providers.gemini_adapter import GEMINI_SAFETY_NONE, build_gemini_payload
from backend.providers.router import normalize_api_endpoint_and_protocol


class ProviderAdapterTests(unittest.TestCase):
    def test_anthropic_payload_cache_control_and_thinking(self) -> None:
        msgs = [
            {"role": "system", "content": "你是严谨主持。"},
            {"role": "system", "content": "动态补充线索"},
            {"role": "user", "content": "我检查门锁"},
            {"role": "user", "content": "再检查窗台"},
            {"role": "assistant", "content": "锁孔有撬痕"},
        ]
        body, path = build_anthropic_payload(
            model="claude-sonnet-4-5",
            messages=msgs,
            params={"max_tokens": 4096, "temperature": 0.6},
            think_enabled=True,
            thinking_budget=2048,
        )
        self.assertEqual(path, "/messages")
        self.assertEqual(body["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertNotIn("cache_control", body["system"][1])
        # Consecutive user messages must be merged cleanly
        self.assertEqual([m["role"] for m in body["messages"]], ["user", "assistant"])
        # Extended thinking locks temperature to 1.0
        self.assertEqual(body["temperature"], 1.0)
        self.assertEqual(body["thinking"]["type"], "enabled")
        self.assertEqual(body["thinking"]["budget_tokens"], 2048)

    def test_gemini_payload_block_none_and_system_instruction(self) -> None:
        msgs = [
            {"role": "system", "content": "系统设定"},
            {"role": "user", "content": "前进"},
            {"role": "assistant", "content": "前方是雾海"},
        ]
        body = build_gemini_payload(
            model="gemini-2.5-flash",
            messages=msgs,
            params={"temperature": 0.7, "top_p": 0.9, "top_k": 40, "max_tokens": 8192},
            think_enabled=True,
            thinking_budget=1024,
        )
        self.assertEqual(body["systemInstruction"]["parts"][0]["text"], "系统设定")
        self.assertEqual([c["role"] for c in body["contents"]], ["user", "model"])
        self.assertEqual(body["safetySettings"], GEMINI_SAFETY_NONE)
        self.assertTrue(all(s["threshold"] == "BLOCK_NONE" for s in body["safetySettings"]))
        self.assertEqual(body["generationConfig"]["thinkingConfig"]["thinkingBudget"], 1024)

    def test_protocol_auto_routing(self) -> None:
        r_gem = normalize_api_endpoint_and_protocol("", "AIzaSyExampleKey", "auto")
        self.assertEqual(r_gem["protocol"], "gemini")
        self.assertEqual(r_gem["native_protocol"], "gemini_native")

        r_cla = normalize_api_endpoint_and_protocol("https://api.anthropic.com", "sk-ant-test", "auto")
        self.assertEqual(r_cla["protocol"], "claude")
        self.assertEqual(r_cla["native_protocol"], "claude_native")

        r_ol = normalize_api_endpoint_and_protocol("http://127.0.0.1:11434", "", "auto")
        self.assertEqual(r_ol["protocol"], "ollama")

        r_oai = normalize_api_endpoint_and_protocol("https://api.deepseek.com", "sk-ds-test", "auto")
        self.assertEqual(r_oai["protocol"], "openai")
        self.assertTrue(r_oai["base_url"].endswith("/v1"))


if __name__ == "__main__":
    unittest.main()
