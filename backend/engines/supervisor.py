# -*- coding: utf-8 -*-
"""Unified local model catalog (Low-Spec 4B/8B/14B + 27B/Flash-Next), GGUF scanner, HF-Mirror downloader."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from backend.config import CUSTOM_PATHS_FILE, MODEL_DIR, MODELS_DIR, atomic_write_json
from backend.engines.llama_manager import ensure_llama_ready, find_llama_server_exe, kill_llama_server
from backend.engines.strata_manager import ensure_strata_ready, kill_strata_server

logger = logging.getLogger("easy_trpg.supervisor")

_DISCOVERED_LOCK = threading.RLock()
DISCOVERED_LOCAL_MODELS: Dict[str, Dict[str, Any]] = {}
_ENGINE_SWITCH_LOCK = asyncio.Lock()

HF_DOWNLOAD_TASKS: Dict[str, Dict[str, Any]] = {}
HF_DOWNLOAD_ASYNC_TASKS: Dict[str, asyncio.Task] = {}

LOCAL_MODELS_CATALOG: List[Dict[str, Any]] = []

HF_PRESET_CATALOG: List[Dict[str, Any]] = [
    # ---- Qwen3 Small/Medium Fallbacks (Not Recommended) ----
    {
        "id": "qwen3_4b_q4_k_m",
        "series": "Qwen3",
        "subfolder": "Qwen3-Light",
        "series_title": "不推荐",
        "repo_id": "Qwen/Qwen3-4B-GGUF",
        "name": "Qwen3-4B (Q4_K_M)",
        "quant": "Q4_K_M",
        "engine": "llama",
        "tier": "C",
        "recommended": False,
        "not_recommended": True,
        "vram_hint": "不推荐 · 4G显存 / 轻薄本 / CPU",
        "desc": "不推荐，仅低配应急。",
        "files": [{"path": "Qwen3-4B-Q4_K_M.gguf", "size": 2497280256}],
    },
    {
        "id": "qwen3_8b_q4_k_m",
        "series": "Qwen3",
        "subfolder": "Qwen3-Light",
        "series_title": "不推荐",
        "repo_id": "Qwen/Qwen3-8B-GGUF",
        "name": "Qwen3-8B (Q4_K_M)",
        "quant": "Q4_K_M",
        "engine": "llama",
        "tier": "B",
        "recommended": False,
        "not_recommended": True,
        "vram_hint": "不推荐 · 6G~8G显存 (RTX 3060/4060)",
        "desc": "不推荐，仅低配应急。",
        "files": [{"path": "Qwen3-8B-Q4_K_M.gguf", "size": 5027783488}],
    },
    {
        "id": "qwen3_14b_q4_k_m",
        "series": "Qwen3",
        "subfolder": "Qwen3-Light",
        "series_title": "不推荐",
        "repo_id": "Qwen/Qwen3-14B-GGUF",
        "name": "Qwen3-14B (Q4_K_M)",
        "quant": "Q4_K_M",
        "engine": "llama",
        "tier": "A",
        "recommended": False,
        "not_recommended": True,
        "vram_hint": "不推荐 · 12G显存 (RTX 3060-12G / 4070)",
        "desc": "不推荐，仅备用。",
        "files": [{"path": "Qwen3-14B-Q4_K_M.gguf", "size": 9001752960}],
    },
    # ---- Flagship Dongfangshuo Series ----
    {
        "id": "v4_q3_k_m",
        "series": "Dongfangshuo-27B",
        "subfolder": "Dongfangshuo-27B",
        "series_title": "Dongfangshuo-27B",
        "repo_id": "dongfangshuo/Dongfangshuo-Qwen3.8-27B-NSFW-v4",
        "name": "Dongfangshuo-Qwen3.8-27B-NSFW-v4 (Q3_K_M)",
        "quant": "Q3_K_M",
        "engine": "llama",
        "tier": "A",
        "recommended": True,
        "vram_hint": "12G~16G显存 + 16G内存 (16G全显存首选)",
        "desc": "专精沉浸跑团、人物张力与多模态识图。",
        "files": [
            {"path": "Dongfangshuo-Qwen3.8-27B-NSFW-v4-Q3_K_M.gguf", "size": 13301443040},
            {"path": "mmproj-model-bf16.gguf", "size": 931145888},
        ],
    },
    {
        "id": "v4_q4_k_m",
        "series": "Dongfangshuo-27B",
        "subfolder": "Dongfangshuo-27B",
        "series_title": "Dongfangshuo-27B",
        "repo_id": "dongfangshuo/Dongfangshuo-Qwen3.8-27B-NSFW-v4",
        "name": "Dongfangshuo-Qwen3.8-27B-NSFW-v4 (Q4_K_M)",
        "quant": "Q4_K_M",
        "engine": "llama",
        "tier": "S",
        "recommended": True,
        "vram_hint": "24G+显存，或 16G显存 + 32G内存",
        "desc": "旗舰级文笔与多轮复杂推理。",
        "files": [
            {"path": "Dongfangshuo-Qwen3.8-27B-NSFW-v4-Q4_K_M.gguf", "size": 16547400160},
            {"path": "mmproj-model-bf16.gguf", "size": 931145888},
        ],
    },
    {
        "id": "novel_q3_k_m",
        "series": "Dongfangshuo-27B",
        "subfolder": "Dongfangshuo-27B",
        "series_title": "Dongfangshuo-27B",
        "repo_id": "dongfangshuo/Dongfangshuo-Qwen3.8-27B-NSFW-Novel",
        "name": "Dongfangshuo-Qwen3.8-27B-NSFW-Novel (Q3_K_M)",
        "quant": "Q3_K_M",
        "engine": "llama",
        "tier": "A",
        "recommended": False,
        "vram_hint": "16G显存 + 16G内存 (小说专精)",
        "desc": "长篇小说叙事优化版。",
        "files": [
            {"path": "Dongfangshuo-Qwen3.8-27B-NSFW-Novel-Q3_K_M.gguf", "size": 13301443008},
            {"path": "mmproj-Dongfangshuo-Qwen3.8-27B-NSFW-Novel-f16.gguf", "size": 931145888},
        ],
    },
    {
        "id": "flash_iq3_xxs",
        "series": "Flash-Next",
        "subfolder": "Flash-Next",
        "series_title": "Flash-Next (MoE)",
        "repo_id": "dongfangshuo/Dongfangshuo-Qwen3.8-Flash-Next-NSFW",
        "name": "Dongfangshuo-Qwen3.8-Flash-Next-NSFW (IQ3_XXS)",
        "quant": "IQ3_XXS",
        "engine": "strata",
        "tier": "S",
        "recommended": False,
        "vram_hint": "RTX 20系+ · 8G+显存 · 32G+内存 (77 GB)",
        "desc": "MoE 巨无霸架构，需 32G+ 系统内存。",
        "files": [
            {"path": "IQ3_XXS/Dongfangshuo-Qwen3.8-Flash-Next-NSFW-IQ3_XXS-00001-of-00002.gguf", "size": 40146300000},
            {"path": "IQ3_XXS/Dongfangshuo-Qwen3.8-Flash-Next-NSFW-IQ3_XXS-00002-of-00002.gguf", "size": 37043801280},
            {"path": "mmproj-Qwen3.8-Flash-Next-BF16.gguf", "size": 907543008},
        ],
    },
]


def load_saved_custom_model_paths(extra: Any = None) -> List[str]:
    paths: List[str] = []
    if CUSTOM_PATHS_FILE.is_file():
        try:
            raw = json.loads(CUSTOM_PATHS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                paths.extend(str(p).strip() for p in raw if str(p).strip())
        except Exception:
            pass
    if isinstance(extra, list):
        for p in extra:
            s = str(p or "").strip()
            if s and s not in paths:
                paths.append(s)
    return paths


def save_custom_model_paths(paths: List[str]) -> List[str]:
    clean = list(dict.fromkeys(str(p).strip() for p in paths if str(p).strip()))
    atomic_write_json(CUSTOM_PATHS_FILE, clean)
    return clean


def _check_gguf_shards_complete(gguf_path: Path) -> Tuple[bool, str]:
    m = re.search(r"-(\d{5})-of-(\d{5})\.gguf$", gguf_path.name, re.I)
    if not m:
        return True, ""
    total = int(m.group(2))
    prefix = gguf_path.name[: m.start()]
    missing = [
        f"{prefix}-{idx:05d}-of-{total:05d}.gguf"
        for idx in range(1, total + 1)
        if not (gguf_path.parent / f"{prefix}-{idx:05d}-of-{total:05d}.gguf").is_file()
    ]
    if missing:
        return False, f"缺少分片 {missing[0]}"
    return True, ""


def _find_best_mmproj(gguf_path: Path) -> str:
    for cand in sorted(gguf_path.parent.glob("*mmproj*.gguf")):
        if cand.is_file():
            return str(cand)
    return ""


def scan_local_models_sync(custom_paths: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    roots = [MODEL_DIR, MODELS_DIR] + [Path(p) for p in load_saved_custom_model_paths(custom_paths)]
    found: List[Dict[str, Any]] = []
    seen_files: set[str] = set()

    for root in roots:
        if not root.exists():
            continue
        gguf_list = [root] if (root.is_file() and root.suffix.lower() == ".gguf") else sorted(root.rglob("*.gguf"))
        for gpath in gguf_list:
            low = gpath.name.lower()
            if "mmproj" in low or low.startswith("."):
                continue
            m_sh = re.search(r"-(\d{5})-of-(\d{5})\.gguf$", gpath.name, re.I)
            if m_sh and int(m_sh.group(1)) != 1:
                continue
            try:
                canon = str(gpath.resolve())
            except OSError:
                canon = str(gpath)
            if canon in seen_files:
                continue
            seen_files.add(canon)

            ok_shards, shard_warn = _check_gguf_shards_complete(gpath)
            is_strata = "flash-next" in low or "strata" in str(gpath.parent).lower()
            engine = "strata" if is_strata else "llama"
            clean_stem = re.sub(r"-\d{5}-of-\d{5}$", "", gpath.stem, flags=re.I)
            mid = f"local/{clean_stem}"
            sz_gb = round(gpath.stat().st_size / (1024 ** 3), 2)
            mmproj = _find_best_mmproj(gpath)
            meta = {
                "id": mid,
                "name": f"{clean_stem} ({sz_gb} GB)",
                "group": "Local",
                "engine": engine,
                "upstream_model": clean_stem,
                "gguf_path": canon,
                "mmproj_path": mmproj,
                "supports_vision": bool(mmproj),
                "shards_complete": ok_shards,
                "shard_warning": shard_warn,
                "source_label": "Flash-Next (Strata)" if engine == "strata" else "本地标准引擎",
                "short_price": "免费",
                "detail_price": "本地算力",
                "description": f"{sz_gb} GB · {gpath.parent.name}",
                "aliases": [clean_stem, gpath.name],
            }
            found.append(meta)

    with _DISCOVERED_LOCK:
        DISCOVERED_LOCAL_MODELS.clear()
        for m in found:
            DISCOVERED_LOCAL_MODELS[m["id"]] = m
            for al in m.get("aliases") or []:
                DISCOVERED_LOCAL_MODELS.setdefault(al, m)
    return found


def get_discovered_models_snapshot() -> Dict[str, Dict[str, Any]]:
    with _DISCOVERED_LOCK:
        return dict(DISCOVERED_LOCAL_MODELS)


async def discover_local_models(settings: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    cp = settings.get("custom_model_paths") if isinstance(settings, dict) else None
    items = await asyncio.to_thread(scan_local_models_sync, cp)
    return items


def get_installed_local_model_ids(settings: Optional[Dict[str, Any]] = None) -> List[str]:
    return [m["id"] for m in scan_local_models_sync(settings.get("custom_model_paths") if settings else None)]


async def ensure_local_engine_ready(
    model_id: str,
    local_meta: Dict[str, Any],
    *,
    settings: Optional[Dict[str, Any]] = None,
    req_parallel: int = 1,
    slot_ctx_tokens: int = 0,
    status_callback=None,
) -> Optional[Dict[str, Any]]:
    """Ensure local inference server for model_id is running. Returns None or structured diagnosis dict."""
    async with _ENGINE_SWITCH_LOCK:
        engine = str(local_meta.get("engine") or "llama").lower()
        low_spec = str((settings or {}).get("low_spec_mode") or "auto").lower()
        if engine == "strata":
            await asyncio.to_thread(kill_llama_server)
            return await ensure_strata_ready(model_id, local_meta, status_callback=status_callback)
        else:
            await asyncio.to_thread(kill_strata_server)
            return await ensure_llama_ready(
                model_id,
                local_meta,
                req_parallel=req_parallel,
                slot_ctx_tokens=slot_ctx_tokens,
                low_spec_mode=low_spec,
                status_callback=status_callback,
            )


async def shutdown_local_engines() -> None:
    await asyncio.to_thread(kill_llama_server)
    await asyncio.to_thread(kill_strata_server)


def build_hf_catalog_with_status(custom_paths: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    installed_names = {Path(m["gguf_path"]).name.lower() for m in scan_local_models_sync(custom_paths) if m.get("gguf_path")}
    out = []
    for p in HF_PRESET_CATALOG:
        cp = dict(p)
        f0 = Path(p["files"][0]["path"]).name.lower() if p.get("files") else ""
        cp["installed"] = bool(f0 and f0 in installed_names)
        cp["not_recommended"] = bool(p.get("not_recommended", False))
        cp["total_size_gb"] = round(sum(f.get("size", 0) for f in p.get("files") or []) / (1024 ** 3), 2)
        out.append(cp)
    return out


async def _hf_download_worker(task_id: str, files: List[Dict[str, Any]], repo_id: str, target_dir: Path, mirror: str) -> None:
    task = HF_DOWNLOAD_TASKS[task_id]
    host = "https://hf-mirror.com" if mirror == "hf-mirror" else "https://huggingface.co"
    target_dir.mkdir(parents=True, exist_ok=True)
    total_all = sum(int(f.get("size") or 0) for f in files)
    done_prev = 0
    try:
        async with httpx.AsyncClient(trust_env=False, follow_redirects=True, timeout=httpx.Timeout(20.0, read=120.0)) as client:
            for f in files:
                if task.get("cancel_requested"):
                    task["status"] = "cancelled"
                    return
                rel_p = str(f["path"])
                dest = target_dir / Path(rel_p).name
                part = target_dir / f"{Path(rel_p).name}.part"
                if dest.is_file() and f.get("size") and dest.stat().st_size == int(f["size"]):
                    done_prev += int(f["size"])
                    continue
                existing = part.stat().st_size if part.is_file() else 0
                headers = {"User-Agent": "Easy-TRPG/2.0"}
                if existing > 0:
                    headers["Range"] = f"bytes={existing}-"
                url = f"{host}/{repo_id}/resolve/main/{rel_p}"
                task["current_file"] = dest.name
                t0 = time.perf_counter()
                async with client.stream("GET", url, headers=headers) as resp:
                    resp.raise_for_status()
                    mode = "ab" if (resp.status_code == 206 and existing > 0) else "wb"
                    cur_written = existing if mode == "ab" else 0
                    with open(part, mode) as wf:
                        async for chunk in resp.aiter_bytes(chunk_size=512 * 1024):
                            while task.get("pause_requested"):
                                task["status"] = "paused"
                                await asyncio.sleep(0.5)
                                if task.get("cancel_requested"):
                                    task["status"] = "cancelled"
                                    return
                            task["status"] = "downloading"
                            wf.write(chunk)
                            cur_written += len(chunk)
                            dt = max(0.1, time.perf_counter() - t0)
                            task["downloaded_bytes"] = done_prev + cur_written
                            task["total_bytes"] = max(total_all, task["downloaded_bytes"])
                            task["speed_mb_s"] = round((cur_written - (existing if mode == "ab" else 0)) / 1024 / 1024 / dt, 2)
                            task["progress"] = round(min(100.0, 100.0 * task["downloaded_bytes"] / max(1, task["total_bytes"])), 1)
                    done_prev += cur_written
                os.replace(part, dest)
        task["status"] = "completed"
        task["progress"] = 100.0
        scan_local_models_sync()
    except Exception as exc:
        task["status"] = "error"
        task["error"] = str(exc)


def start_hf_download(preset_id: str = "", repo_id: str = "", files: Optional[List[Dict[str, Any]]] = None, mirror: str = "hf-mirror") -> Dict[str, Any]:
    preset = next((p for p in HF_PRESET_CATALOG if p["id"] == preset_id), None)
    if preset:
        repo_id = preset["repo_id"]
        files = preset["files"]
        sub = preset.get("subfolder") or "Custom"
        target_dir = MODELS_DIR / sub
        title = preset["name"]
    else:
        target_dir = MODELS_DIR / re.sub(r"[^a-zA-Z0-9._-]", "_", repo_id.split("/")[-1] or "custom")
        files = files or []
        title = repo_id
    if not repo_id or not files:
        raise ValueError("缺少仓库 ID 或下载文件清单")

    tid = f"dl_{int(time.time()*1000)}"
    HF_DOWNLOAD_TASKS[tid] = {
        "id": tid,
        "preset_id": preset_id,
        "title": title,
        "repo_id": repo_id,
        "status": "downloading",
        "progress": 0.0,
        "downloaded_bytes": 0,
        "total_bytes": sum(int(f.get("size") or 0) for f in files),
        "speed_mb_s": 0.0,
        "current_file": "",
        "error": "",
        "pause_requested": False,
        "cancel_requested": False,
    }
    HF_DOWNLOAD_ASYNC_TASKS[tid] = asyncio.create_task(_hf_download_worker(tid, files, repo_id, target_dir, mirror))
    return HF_DOWNLOAD_TASKS[tid]
