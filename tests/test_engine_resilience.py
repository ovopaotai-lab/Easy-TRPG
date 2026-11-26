# -*- coding: utf-8 -*-
"""Tests for low-spec hardware tiering, Strata PCIe/driver translation, and preflight diagnostics."""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import backend.engines.strata_manager as strata_manager
from backend.engines.hardware import classify_hardware_tier, run_preflight_checks_sync
from backend.engines.strata_manager import _build_strata_config_sync, ensure_strata_ready, translate_strata_crash
from backend.providers.router import stream_via_endpoint


class EngineResilienceTests(unittest.TestCase):
    def test_hardware_tier_classification(self) -> None:
        t_s = classify_hardware_tier(vram_mib=32607, ram_gib=64, has_nvidia=True)
        self.assertEqual(t_s["tier"], "S")
        self.assertFalse(t_s["low_spec_recommended"])
        self.assertTrue(t_s["supports_flash_next_strata"])

        t_b = classify_hardware_tier(vram_mib=8192, ram_gib=16, has_nvidia=True)
        self.assertEqual(t_b["tier"], "B")
        self.assertTrue(t_b["low_spec_recommended"])
        self.assertEqual(t_b["recommended_preset_id"], "qwen3_8b_q4_k_m")

        t_c = classify_hardware_tier(vram_mib=4096, ram_gib=16, has_nvidia=True)
        self.assertEqual(t_c["tier"], "C")
        self.assertEqual(t_c["recommended_preset_id"], "qwen3_4b_q4_k_m")

        t_cpu = classify_hardware_tier(vram_mib=0, ram_gib=8, has_nvidia=False)
        self.assertEqual(t_cpu["tier"], "CPU")
        self.assertFalse(t_cpu["supports_flash_next_strata"])

    def test_strata_pcie_probe_error_translation(self) -> None:
        hw = {"driver_version": "572.16", "vram_total_mib": 12288, "ram_total_gib": 32}
        diag = translate_strata_crash(
            1,
            "strata generate: PCIe probe failed -> pcie_frac default 0.55",
            hw,
        )
        self.assertEqual(diag["code"], "STRATA_PCIE_PROBE_FAILED")
        self.assertEqual(diag["engine"], "strata")
        self.assertIn("PCIe", diag["message"])
        self.assertTrue(any(a["action"] == "open_engine_downloads" for a in diag["actions"]))
        self.assertTrue(any(a["action"] == "open_api_setup" for a in diag["actions"]))

    def test_preflight_checks_structure(self) -> None:
        pre = run_preflight_checks_sync()
        self.assertIn("hardware", pre)
        self.assertIn("checks", pre)
        ids = {c["id"]: c for c in pre["checks"]}
        self.assertIn("llama_engine", ids)
        self.assertTrue(ids["llama_engine"]["ok"])

    def test_strata_reuses_running_model_without_kill(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            gguf = root / "models" / "Dongfangshuo-Qwen3.8-Flash-Next-NSFW-IQ3_XXS-00001-of-00002.gguf"
            gguf.parent.mkdir(parents=True, exist_ok=True)
            gguf.write_bytes(b"GGUF_TEST_HDR")
            strata_root = root / "engine" / "strata"
            (strata_root / "serve").mkdir(parents=True, exist_ok=True)
            (strata_root / "serve" / "server.py").write_text("# stub", encoding="utf-8")

            gguf_key = f"{gguf.resolve()}::{gguf.stat().st_size}"
            meta = {"id": "local/Dongfangshuo", "upstream_model": "Dongfangshuo", "gguf_path": str(gguf)}

            class _FakeClient:
                def __init__(self, *args, **kwargs) -> None:
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args) -> None:
                    pass

                async def get(self, url: str):
                    return SimpleNamespace(status_code=200, url=url)

            hw = {"has_nvidia": True, "driver_num": 610.88, "ram_total_gib": 62, "vram_total_mib": 32607, "vram_free_mib": 28000}
            with patch.object(strata_manager, "BASE_DIR", root), \
                 patch.object(strata_manager, "ACTIVE_STRATA_MODEL", gguf_key), \
                 patch.object(strata_manager, "ACTIVE_STRATA_PORT", 8083), \
                 patch.object(strata_manager, "ACTIVE_STRATA_PROC", None), \
                 patch.object(strata_manager, "get_hardware_snapshot_sync", return_value=hw), \
                 patch.object(strata_manager, "kill_strata_server") as mock_kill, \
                 patch("backend.engines.strata_manager.httpx.AsyncClient", _FakeClient):
                res = asyncio.run(ensure_strata_ready("local/Dongfangshuo", meta))

            self.assertIsNone(res)
            self.assertEqual(meta["base_url"], "http://127.0.0.1:8083/v1")
            mock_kill.assert_not_called()

    def test_strata_config_includes_vision_model_and_ram_budget(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            gguf = root / "model.gguf"
            gguf.write_bytes(b"GGUF")
            mmproj = root / "mmproj.gguf"
            mmproj.write_bytes(b"MMPROJ")
            eng_dir = root / "strata" / "engine"
            eng_dir.mkdir(parents=True, exist_ok=True)
            vis_exe = eng_dir / ("strata-vision.exe" if strata_manager.os.name == "nt" else "strata-vision")
            vis_exe.write_bytes(b"EXE")
            strata_root = root / "strata"
            pack_dir = strata_root / "data" / "packs" / "dongfangshuo-iq3_xxs"
            (pack_dir / "tokenizer").mkdir(parents=True, exist_ok=True)
            (pack_dir / "index.txt").write_text("idx", encoding="utf-8")
            (pack_dir / "native_experts.txt").write_text("model.gguf", encoding="utf-8")
            (pack_dir / "dense.bin").write_bytes(b"1")
            (pack_dir / "tokenizer" / "vocab.json").write_text("{}", encoding="utf-8")

            hw = {"has_nvidia": True, "driver_num": 610.88, "ram_total_gib": 62, "vram_total_mib": 32607, "vram_free_mib": 27000}
            meta = {"id": "local/Flash", "upstream_model": "Flash", "gguf_path": str(gguf), "mmproj_path": str(mmproj)}
            with patch.object(strata_manager, "ENGINE_LOGS_DIR", root / "logs"), \
                 patch.object(strata_manager, "get_hardware_snapshot_sync", return_value=hw), \
                 patch.object(strata_manager, "detect_free_ram_gib", return_value=30.0):
                cfg_path, err, _ = _build_strata_config_sync(
                    local_meta=meta,
                    strata_root=strata_root,
                    engine_dir=eng_dir,
                    port=8080,
                    safe_fallback=False,
                )
            self.assertIsNone(err)
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            self.assertIn("--kv-grow", cfg["args"])
            self.assertIn("--resident-budget-gib", cfg["args"])
            self.assertNotIn("--resident-experts", cfg["args"])
            self.assertEqual(cfg["vision"]["model"], str(gguf.resolve()))
            self.assertEqual(cfg["vision"]["mmproj"], str(mmproj.resolve()))

    def test_stream_via_endpoint_uses_fresh_local_meta_base_url(self) -> None:
        captured: dict = {}

        async def _fake_stream(client, *, base_url, headers, body):
            captured["base_url"] = base_url
            if False:
                yield None

        ep = {
            "is_local": True,
            "native_protocol": "openai",
            "upstream_model": "Flash",
            "base_url": "http://127.0.0.1:8080/v1",
            "local_meta": {"base_url": "http://127.0.0.1:8081/v1"},
            "headers": {"Content-Type": "application/json"},
        }

        async def _run() -> None:
            async for _ in stream_via_endpoint(endpoint=ep, messages=[{"role": "user", "content": "hi"}], params={}):
                pass

        with patch("backend.providers.router.stream_openai_chat", _fake_stream):
            asyncio.run(_run())

        self.assertEqual(captured["base_url"], "http://127.0.0.1:8081/v1")
        self.assertEqual(ep["base_url"], "http://127.0.0.1:8081/v1")


if __name__ == "__main__":
    unittest.main()
