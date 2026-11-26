# -*- coding: utf-8 -*-
"""Adaptive llama-server (llama.cpp b12726+) manager with 4-way backend & low-spec safe mode."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from backend.config import BASE_DIR, ENGINE_LOGS_DIR
from backend.engines.hardware import (
    detect_system_ram_gib,
    get_hardware_snapshot_sync,
    probe_nvidia_gpu_sync,
)
from backend.engines.process_guard import (
    is_port_free,
    kill_processes_by_image_name,
    linux_pdeathsig_preexec,
    pick_available_port,
    read_log_tail,
    register_spawned_engine_proc,
)

logger = logging.getLogger("easy_trpg.llama")

_LLAMA_LOCK = asyncio.Lock()
_CACHED_BACKEND: Optional[Dict[str, str]] = None
ACTIVE_LLAMA_PORT: int = 11435
ACTIVE_LLAMA_MODEL: str = ""
ACTIVE_LLAMA_PARALLEL: int = 1
ACTIVE_LLAMA_CTX: int = 0
ACTIVE_LLAMA_PROC: Optional[subprocess.Popen] = None


def find_llama_server_exe() -> Optional[Path]:
    llama_dir = BASE_DIR / "engine" / "llama"
    cands = (
        [llama_dir / "llama-server.exe"]
        if os.name == "nt"
        else [llama_dir / "llama-server", llama_dir / "build" / "bin" / "llama-server"]
    )
    for p in cands:
        if p.is_file():
            return p
    return None


def get_optimal_ctx_tokens(requested_k: int, gguf_path: str = "", low_spec: bool = False) -> int:
    req_tok = max(4096, int(requested_k or 32) * 1024)
    nv = probe_nvidia_gpu_sync()
    vram_mib = nv["vram_total_mib"]
    if low_spec or (nv["has_nvidia"] and vram_mib <= 6500):
        return min(req_tok, 8192)
    if nv["has_nvidia"] and vram_mib <= 10500:
        return min(req_tok, 16384)
    if nv["has_nvidia"] and vram_mib <= 14500:
        return min(req_tok, 32768)
    if nv["has_nvidia"] and vram_mib <= 18500:
        return min(req_tok, 65536)
    return min(req_tok, 98304)


def select_adaptive_llama_backend_sync(llama_exe: Path) -> Dict[str, str]:
    """Select best GGML backend in priority: CUDA 13 -> CUDA 12 -> Vulkan -> CPU."""
    global _CACHED_BACKEND
    if _CACHED_BACKEND is not None and _CACHED_BACKEND.get("exe") == str(llama_exe):
        return dict(_CACHED_BACKEND)

    ls_dir = llama_exe.parent
    nv = probe_nvidia_gpu_sync()
    drv_num = nv["driver_num"]
    has_nv = nv["has_nvidia"]

    cf = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
    si = None
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
        si.wShowWindow = 0

    def _probe(dll_path: Path, expect: str) -> bool:
        if not dll_path.is_file():
            return False
        env = os.environ.copy()
        sep = ";" if os.name == "nt" else ":"
        env["PATH"] = sep.join(x for x in (str(dll_path.parent), str(ls_dir), env.get("PATH", "")) if x)
        if os.name != "nt":
            env["LD_LIBRARY_PATH"] = sep.join(x for x in (str(dll_path.parent), str(ls_dir), env.get("LD_LIBRARY_PATH", "")) if x)
        env["GGML_BACKEND_PATH"] = str(dll_path)
        try:
            r = subprocess.run(
                [str(llama_exe), "--list-devices"],
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                creationflags=cf,
                startupinfo=si,
                timeout=4.5,
            )
            out = (r.stdout or "") + "\n" + (r.stderr or "")
            return expect.lower() in out.lower()
        except Exception:
            return False

    backend_name = "cpu"
    backend_dll = ""
    extra_bin_dir = ""

    if os.name == "nt":
        cuda_cands: List[Path] = []
        if has_nv:
            # Only attempt CUDA 13 when driver >= 580; otherwise prefer CUDA 12 first
            if drv_num >= 580.0 or drv_num == 0.0:
                cuda_cands.append(ls_dir / "cuda_v13" / "ggml-cuda.dll")
            cuda_cands.append(ls_dir / "cuda_v12" / "ggml-cuda.dll")
            cuda_cands.append(ls_dir / "ggml-cuda.dll")
        for cdll in cuda_cands:
            if _probe(cdll, "cuda0"):
                backend_name = "cuda"
                backend_dll = str(cdll)
                extra_bin_dir = str(cdll.parent)
                break
        if backend_name == "cpu":
            for vdll in (ls_dir / "vulkan" / "ggml-vulkan.dll", ls_dir / "ggml-vulkan.dll"):
                if _probe(vdll, "vulkan0"):
                    backend_name = "vulkan"
                    backend_dll = str(vdll)
                    extra_bin_dir = str(vdll.parent)
                    break
    else:
        for cso in (ls_dir / "cuda_v13" / "libggml-cuda.so", ls_dir / "libggml-cuda.so", ls_dir / "ggml-cuda.so"):
            if _probe(cso, "cuda0"):
                backend_name = "cuda"
                backend_dll = str(cso)
                extra_bin_dir = str(cso.parent)
                break
        if backend_name == "cpu":
            for vso in (ls_dir / "vulkan" / "libggml-vulkan.so", ls_dir / "libggml-vulkan.so", ls_dir / "ggml-vulkan.so"):
                if _probe(vso, "vulkan0"):
                    backend_name = "vulkan"
                    backend_dll = str(vso)
                    extra_bin_dir = str(vso.parent)
                    break

    res = {
        "exe": str(llama_exe),
        "backend": backend_name,
        "backend_dll": backend_dll,
        "extra_bin_dir": extra_bin_dir,
    }
    _CACHED_BACKEND = dict(res)
    return res


def build_adaptive_llama_launch_plan(
    llama_exe: Path,
    gguf_path: Path,
    model_alias: str,
    port: int,
    mmproj_path: str = "",
    req_parallel: int = 1,
    slot_ctx_tokens: int = 0,
    low_spec_mode: str = "auto",
) -> Tuple[List[str], Dict[str, str], Dict[str, Any]]:
    """Build hardware-adaptive llama-server CLI command, including Low-Spec Safe Mode."""
    bk = select_adaptive_llama_backend_sync(llama_exe)
    has_gpu = bk["backend"] in ("cuda", "vulkan")
    hw = get_hardware_snapshot_sync(use_cache=True)
    vram_mib = hw["vram_total_mib"] if has_gpu else 0
    sys_ram_gib = hw["ram_total_gib"] or detect_system_ram_gib()
    eff_par = max(1, min(16, int(req_parallel or 1)))

    is_low_spec = (low_spec_mode == "on") or (
        low_spec_mode == "auto" and (not has_gpu or vram_mib <= 10240 or sys_ram_gib <= 16)
    )

    if is_low_spec and eff_par == 1:
        batch_sz = 512
        ubatch_sz = 256
    elif vram_mib >= 28000:
        batch_sz = 4096
        ubatch_sz = 2048 if eff_par <= 4 else 1024
    elif vram_mib >= 20000:
        batch_sz = 2048
        ubatch_sz = 1024 if eff_par <= 4 else 512
    elif vram_mib >= 14000:
        batch_sz = 2048
        ubatch_sz = 512
    else:
        batch_sz = 1024
        ubatch_sz = 512

    if eff_par == 1:
        base_ctx = get_optimal_ctx_tokens(96, str(gguf_path), low_spec=is_low_spec)
        total_ctx = max(base_ctx, int(slot_ctx_tokens or 0))
        kv_type = "q8_0" if (not is_low_spec and (vram_mib >= 14000 or not has_gpu)) else "q4_0"
    else:
        per_slot = max(8192, int(slot_ctx_tokens or 32768))
        total_ctx = min(524288, per_slot * eff_par)
        kv_type = "q8_0" if (vram_mib >= 28000 and total_ctx <= 185000) else "q4_0"

    fit_margin_mib = 1024 if vram_mib >= 20000 else (768 if vram_mib >= 12000 else 512)
    cache_ram_mib = 1024 if is_low_spec else (8192 if sys_ram_gib >= 48 else (4096 if sys_ram_gib >= 24 else 1024))
    http_threads = max(6, eff_par + 4)

    cmd: List[str] = [
        str(llama_exe),
        "-m", str(gguf_path),
        "-a", str(model_alias),
        "--host", "127.0.0.1",
        "--port", str(port),
        "--no-webui",
        "-c", str(total_ctx),
        "-np", str(eff_par),
        "-b", str(batch_sz),
        "-ub", str(ubatch_sz),
        "-ctk", kv_type,
        "-ctv", kv_type,
        "--no-reasoning-preserve",
        "--cache-ram", str(cache_ram_mib),
        "--threads-http", str(http_threads),
        "--repeat-penalty", "1.03",
        "--repeat-last-n", "1024",
        "--presence-penalty", "0.10",
        "--frequency-penalty", "0.0",
        "--dry-multiplier", "0.8",
        "--dry-base", "1.75",
        "--dry-allowed-length", "2",
        "--dry-penalty-last-n", "1024",
    ]
    if eff_par > 1:
        cmd.append("-kvu")
    if has_gpu:
        cmd.extend(["-fa", "on", "--fit", "on", "--fit-target", str(fit_margin_mib)])
    else:
        cpu_cnt = os.cpu_count() or 8
        phys_est = max(2, cpu_cnt // 2) if cpu_cnt >= 8 else max(1, cpu_cnt)
        cmd.extend(["-ngl", "0", "-t", str(phys_est), "-tb", str(max(phys_est, cpu_cnt - 1))])

    use_mmproj = bool(eff_par == 1 and not is_low_spec and mmproj_path and Path(mmproj_path).is_file())
    if use_mmproj:
        cmd.extend(["--mmproj", str(mmproj_path)])
        if not has_gpu or vram_mib < 22000:
            cmd.append("--no-mmproj-offload")

    env = os.environ.copy()
    ls_dir = str(llama_exe.parent)
    extra = bk.get("extra_bin_dir") or ""
    sep = ";" if os.name == "nt" else ":"
    env["PATH"] = sep.join(x for x in (extra, ls_dir, env.get("PATH", "")) if x)
    if os.name != "nt":
        strata_eng = str(BASE_DIR / "engine" / "strata" / "engine")
        env["LD_LIBRARY_PATH"] = sep.join(x for x in (extra, ls_dir, strata_eng, env.get("LD_LIBRARY_PATH", "")) if x)
    if bk.get("backend_dll"):
        env["GGML_BACKEND_PATH"] = bk["backend_dll"]

    meta = {
        "backend": bk["backend"],
        "total_ctx": total_ctx,
        "kv_type": kv_type,
        "batch_size": batch_sz,
        "ubatch_size": ubatch_sz,
        "cache_ram_mib": cache_ram_mib,
        "low_spec": is_low_spec,
        "use_mmproj": use_mmproj,
    }
    return cmd, env, meta


def translate_llama_crash(returncode: Optional[int], log_tail: str) -> Dict[str, Any]:
    low = (log_tail or "").lower()
    if any(k in low for k in ("out of memory", "cuda error: out of memory", "vk::outofdevicememory", "failed to allocate")):
        return {
            "code": "VRAM_OOM",
            "engine": "llama",
            "title": "显存或内存不足",
            "message": "当前模型的显存占用超出电脑上限。建议开启「低配安全模式」或改用 Qwen3-8B / Qwen3-4B 轻量模型。",
            "raw_tail": log_tail[-600:],
            "actions": [
                {"id": "enable_low_spec", "label": "开启低配安全模式重试", "action": "enable_low_spec"},
                {"id": "switch_small_model", "label": "去下载 4B/8B 轻量模型", "action": "open_engine_downloads"},
                {"id": "switch_api", "label": "改用在线 API", "action": "open_api_setup"},
            ],
        }
    return {
        "code": "LLAMA_LAUNCH_FAILED",
        "engine": "llama",
        "title": "本地标准引擎启动失败",
        "message": f"引擎退出 (exit code={returncode})。已自动收集日志到 data/engine_logs。",
        "raw_tail": log_tail[-600:],
        "actions": [
            {"id": "run_preflight", "label": "一键环境自检", "action": "run_preflight"},
            {"id": "enable_low_spec", "label": "强制低配安全模式重试", "action": "enable_low_spec"},
            {"id": "switch_api", "label": "改用在线 API", "action": "open_api_setup"},
        ],
    }


def kill_llama_server() -> None:
    global ACTIVE_LLAMA_MODEL, ACTIVE_LLAMA_CTX, ACTIVE_LLAMA_PROC
    if ACTIVE_LLAMA_PROC is not None:
        from backend.engines.process_guard import terminate_process_tree_sync
        terminate_process_tree_sync(ACTIVE_LLAMA_PROC)
        ACTIVE_LLAMA_PROC = None
    kill_processes_by_image_name(("llama-server.exe", "llama-server"))
    ACTIVE_LLAMA_MODEL = ""
    ACTIVE_LLAMA_CTX = 0


async def ensure_llama_ready(
    model_id: str,
    local_meta: Dict[str, Any],
    *,
    req_parallel: int = 1,
    slot_ctx_tokens: int = 0,
    low_spec_mode: str = "auto",
    status_callback=None,
) -> Optional[Dict[str, Any]]:
    """Launch or reuse llama-server; returns None on success or structured EngineDiagnosis dict on failure."""
    global ACTIVE_LLAMA_PORT, ACTIVE_LLAMA_MODEL, ACTIVE_LLAMA_PARALLEL, ACTIVE_LLAMA_CTX, ACTIVE_LLAMA_PROC

    gguf_raw = str(local_meta.get("gguf_path") or "")
    if not gguf_raw or not Path(gguf_raw).is_file():
        return {
            "code": "MISSING_GGUF",
            "engine": "llama",
            "title": "找不到模型文件",
            "message": "请把 .gguf 模型放入 model/ 文件夹，或在「引擎 → 下载模型」一键获取。",
            "actions": [{"id": "dl", "label": "去下载模型", "action": "open_engine_downloads"}],
        }

    llama_exe = find_llama_server_exe()
    if not llama_exe:
        return {
            "code": "NO_LOCAL_ENGINE",
            "engine": "llama",
            "title": "未检测到内置引擎",
            "message": "当前为纯 API 轻薄版，不含本地推理引擎，请配置在线 API 或下载 Windows/Linux 整合包。",
            "actions": [{"id": "api", "label": "配置在线 API", "action": "open_api_setup"}],
        }

    gguf_p = Path(gguf_raw).resolve()
    alias = str(local_meta.get("upstream_model") or local_meta.get("id") or model_id)
    gguf_key = f"{gguf_p}::{gguf_p.stat().st_size}"
    min_pool = (slot_ctx_tokens * req_parallel) if (slot_ctx_tokens > 0 and req_parallel > 1) else slot_ctx_tokens

    if ACTIVE_LLAMA_MODEL == gguf_key and ACTIVE_LLAMA_PARALLEL == req_parallel and ACTIVE_LLAMA_CTX >= min_pool:
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=2.0) as client:
                r = await client.get(f"http://127.0.0.1:{ACTIVE_LLAMA_PORT}/health")
                if r.status_code == 200:
                    local_meta["base_url"] = f"http://127.0.0.1:{ACTIVE_LLAMA_PORT}/v1"
                    return None
        except Exception:
            pass

    await asyncio.to_thread(kill_llama_server)
    await asyncio.sleep(0.8)

    port = pick_available_port(11435, range(11435, 11460))
    ACTIVE_LLAMA_PORT = port
    local_meta["base_url"] = f"http://127.0.0.1:{port}/v1"

    if status_callback:
        await status_callback(f"正在加载本地模型 ({gguf_p.name})...")

    mmproj_path = str(local_meta.get("mmproj_path") or "")
    cmd, env, plan_meta = await asyncio.to_thread(
        build_adaptive_llama_launch_plan,
        llama_exe,
        gguf_p,
        alias,
        port,
        mmproj_path,
        req_parallel,
        slot_ctx_tokens,
        low_spec_mode,
    )

    ENGINE_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = ENGINE_LOGS_DIR / "llama-server.log"
    kwargs: Dict[str, Any] = {
        "stdout": open(log_file, "w", encoding="utf-8", errors="ignore"),
        "stderr": subprocess.STDOUT,
        "cwd": str(llama_exe.parent),
        "env": env,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        kwargs["startupinfo"] = si
    else:
        kwargs["preexec_fn"] = linux_pdeathsig_preexec

    proc = subprocess.Popen(cmd, **kwargs)
    ACTIVE_LLAMA_PROC = proc
    register_spawned_engine_proc(proc)
    try:
        kwargs["stdout"].close()
    except Exception:
        pass

    for sec in range(240):
        await asyncio.sleep(1.0)
        if proc.poll() is not None:
            tail = read_log_tail([log_file])
            return translate_llama_crash(proc.returncode, tail)
        if status_callback and sec > 0 and sec % 10 == 0:
            await status_callback(f"加载引擎 [{plan_meta['backend'].upper()}]... ({sec}s)")
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=2.0) as client:
                r = await client.get(f"http://127.0.0.1:{port}/health")
                if r.status_code == 200:
                    ACTIVE_LLAMA_MODEL = gguf_key
                    ACTIVE_LLAMA_PARALLEL = req_parallel
                    ACTIVE_LLAMA_CTX = plan_meta["total_ctx"]
                    return None
        except Exception:
            pass

    return translate_llama_crash(-1, "启动超时 (240s)")
