# -*- coding: utf-8 -*-
"""Unit tests for adaptive video frame scaling, audio transcode metadata, and provider routing."""
from __future__ import annotations

import unittest

from backend.core.video_processor import (
    choose_frame_encoding_profile,
    compute_target_frame_count,
    format_timestamp_mmss,
    format_video_text_summary,
)
from backend.providers.anthropic_adapter import build_anthropic_payload
from backend.providers.gemini_adapter import build_gemini_payload
from backend.providers.router import is_model_audio_capable, sanitize_messages_for_model


class VideoPipelineTests(unittest.TestCase):
    def test_duration_scaled_frame_count(self) -> None:
        self.assertEqual(compute_target_frame_count(0), 6)
        self.assertGreaterEqual(compute_target_frame_count(3.0), 4)
        self.assertLessEqual(compute_target_frame_count(3.0), 6)
        self.assertEqual(compute_target_frame_count(15.0), 11)
        self.assertEqual(compute_target_frame_count(34.0), 19)
        self.assertEqual(compute_target_frame_count(120.0), 31)
        self.assertEqual(compute_target_frame_count(600.0), 36)

        self.assertEqual(choose_frame_encoding_profile(10), (640, 4))
        self.assertEqual(choose_frame_encoding_profile(19), (512, 5))
        self.assertEqual(choose_frame_encoding_profile(30), (448, 5))
        self.assertEqual(format_timestamp_mmss(75.2), "01:15")

    def test_audio_and_vision_sanitization_per_model(self) -> None:
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "【视频音频识别】：你好"},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQ"}},
                    {"type": "input_audio", "input_audio": {"data": "//uQxAAA", "format": "mp3"}},
                    {"type": "text", "text": "分析视频"},
                ],
            }
        ]
        # Local/vision-only model: keeps image_url + transcript text, drops input_audio
        local_clean = sanitize_messages_for_model(msgs, supports_vision=True, supports_audio=False)
        types_local = [p["type"] for p in local_clean[0]["content"]]
        self.assertEqual(types_local, ["text", "image_url", "text"])

        # Audio+vision capable model (e.g., Gemini): keeps everything
        av_clean = sanitize_messages_for_model(msgs, supports_vision=True, supports_audio=True)
        types_av = [p["type"] for p in av_clean[0]["content"]]
        self.assertEqual(types_av, ["text", "image_url", "input_audio", "text"])

        # Text-only fallback collapses content cleanly to string
        txt_clean = sanitize_messages_for_model(msgs, supports_vision=False, supports_audio=False)
        self.assertIsInstance(txt_clean[0]["content"], str)
        self.assertIn("你好", txt_clean[0]["content"])
        self.assertIn("分析视频", txt_clean[0]["content"])

    def test_provider_audio_adapters_and_capability_detection(self) -> None:
        self.assertFalse(is_model_audio_capable("local/Dongfangshuo-Qwen3.8-Flash-Next", is_local=True))
        self.assertTrue(is_model_audio_capable("gemini-2.5-flash", native_protocol="gemini_native", is_local=False))
        self.assertTrue(is_model_audio_capable("gpt-4o-audio-preview", native_protocol="openai", is_local=False))

        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "查看视频"},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQ"}},
                    {"type": "input_audio", "input_audio": {"data": "SUQzAw==", "format": "mp3"}},
                ],
            }
        ]
        g_body = build_gemini_payload(model="gemini-2.5-flash", messages=msgs, params={})
        g_parts = g_body["contents"][0]["parts"]
        self.assertEqual(len(g_parts), 3)
        self.assertEqual(g_parts[1]["inlineData"]["mimeType"], "image/jpeg")
        self.assertEqual(g_parts[2]["inlineData"]["mimeType"], "audio/mp3")

        a_body, _ = build_anthropic_payload(model="claude-sonnet-4-5", messages=msgs, params={})
        a_blocks = a_body["messages"][0]["content"]
        self.assertEqual([b["type"] for b in a_blocks], ["text", "image"])

    def test_format_video_summary(self) -> None:
        s = format_video_text_summary(
            {
                "filename": "clip.mov",
                "duration_sec": 34.0,
                "duration_label": "00:34",
                "frame_count": 19,
                "has_audio": True,
                "audio_tags": ["语种:中文", "开心"],
                "transcript": "我们到了码头。",
            }
        )
        self.assertIn("clip.mov", s)
        self.assertIn("19 张关键画面", s)
        self.assertIn("我们到了码头。", s)
        self.assertIn("开心", s)


if __name__ == "__main__":
    unittest.main()
