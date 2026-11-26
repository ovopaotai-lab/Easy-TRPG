# -*- coding: utf-8 -*-
"""Async-safe hardware inspection, NVIDIA driver/VRAM probing, tiering, and preflight checks."""
from __future__ import annotations

import asyncio
import logging
import os
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.config import BASE_DIR, MODEL_DIR, MODELS_DIR

logger = logging.getLogger("easy_trpg.hardware")

_HW_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}


def _hidden_kw() -> dict:
    if os.name != "nt":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        "startupinfo": si,
    }


def detect_system_ram_gib() -> int:
    forced = os.environ.get("FORCE_SYS_RAM_GIB", "").strip()
    if forced.isdigit() and int(forced) > 0:
        return int(forced)
    try:
        import psutil
        return max(1, int(round(psutil.virtual_memory().total / (1024 ** 3))))
    except Exception:
        pass
    if os.name == "nt":
        try:
            import ctypes

            class _MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_uint32),
                    ("dwMemoryLoad", ctypes.c_uint32),
                    ("ullTotalPhys", ctypes.c_uint64),
                    ("ullAvailPhys", ctypes.c_uint64),
                    ("ullTotalPageFile", ctypes.c_uint64),
                    ("ullAvailPageFile", ctypes.c_uint64),
                    ("ullTotalVirtual", ctypes.c_uint64),
                    ("ullAvailVirtual", ctypes.c_uint64),
                    ("ullAvailExtendedVirtual", ctypes.c_uint64),
                ]

            stat = _MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return max(1, int(round(stat.ullTotalPhys / (1024 ** 3))))
        except Exception:
            pass
    elif Path("/proc/meminfo").is_file():
        for ln in Path("/proc/meminfo").read_text(encoding="utf-8", errors="ignore").splitlines():
            if ln.startswith("MemTotal:"):
                kb = int(re.findall(r"\d+", ln)[0])
                return max(1, int(round(kb / (1024 ** 2))))
    return 16


def detect_free_ram_gib() -> float:
    try:
        import psutil
        return round(psutil.virtual_memory().available / (1024 ** 3), 1)
    except Exception:
        return float(max(2, detect_system_ram_gib() // 2))


def probe_nvidia_gpu_sync() -> Dict[str, Any]:
    """Query nvidia-smi synchronously (call via asyncio.to_thread from async contexts)."""
    forced_vram = os.environ.get("FORCE_GPU_VRAM_MIB", "").strip()
    forced_drv = os.environ.get("FORCE_NVIDIA_DRIVER", "").strip()
    if forced_vram == "0" or os.environ.get("FORCE_NO_NVIDIA") == "1":
        return {"has_nvidia": False, "gpu_name": "", "driver_version": "", "driver_num": 0.0, "vram_total_mib": 0, "vram_free_mib": 0, "temp_c": 0, "power_w": 0.0}

    if not shutil.which("nvidia-smi"):
        if forced_vram.isdigit() and int(forced_vram) > 0:
            drv_num = float(forced_drv) if forced_drv else 580.65
            return {
                "has_nvidia": True,
                "gpu_name": "Simulated NVIDIA GPU",
                "driver_version": str(drv_num),
                "driver_num": drv_num,
                "vram_total_mib": int(forced_vram),
                "vram_free_mib": int(forced_vram) - 512,
                "temp_c": 45,
                "power_w": 25.0,
            }
        return {"has_nvidia": False, "gpu_name": "", "driver_version": "", "driver_num": 0.0, "vram_total_mib": 0, "vram_free_mib": 0, "temp_c": 0, "power_w": 0.0}

    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total,memory.free,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            stderr=subprocess.DEVNULL,
            timeout=3.0,
            **_hidden_kw(),
        ).decode("utf-8", errors="ignore").strip()
        first_line = next((ln for ln in out.splitlines() if ln.strip()), "")
        if not first_line:
            return {"has_nvidia": False, "gpu_name": "", "driver_version": "", "driver_num": 0.0, "vram_total_mib": 0, "vram_free_mib": 0, "temp_c": 0, "power_w": 0.0}
        parts = [p.strip() for p in first_line.split(",")]
        name = parts[0] if len(parts) > 0 else "NVIDIA GPU"
        drv = forced_drv or (parts[1] if len(parts) > 1 else "")
        m_drv = re.match(r"^(\d+(?:\.\d+)?)", drv)
        drv_num = float(m_drv.group(1)) if m_drv else 0.0
        v_tot = int(forced_vram) if (forced_vram.isdigit() and int(forced_vram) > 0) else int(float(parts[2])) if len(parts) > 2 and parts[2].replace(".", "", 1).isdigit() else 0
        v_free = int(float(parts[3])) if len(parts) > 3 and parts[3].replace(".", "", 1).isdigit() else max(0, v_tot - 512)
        if forced_vram.isdigit() and int(forced_vram) > 0:
            v_free = min(v_free, v_tot)
        temp_c = int(float(parts[4])) if len(parts) > 4 and parts[4].replace(".", "", 1).isdigit() else 0
        pwr_w = float(parts[5]) if len(parts) > 5 and parts[5].replace(".", "", 1).isdigit() else 0.0
        return {
            "has_nvidia": True,
            "gpu_name": name,
            "driver_version": drv,
            "driver_num": drv_num,
            "vram_total_mib": v_tot,
            "vram_free_mib": v_free,
            "temp_c": temp_c,
            "power_w": round(pwr_w, 1),
        }
    except Exception as exc:
        logger.debug("nvidia-smi query failed: %s", exc)
        return {"has_nvidia": False, "gpu_name": "", "driver_version": "", "driver_num": 0.0, "vram_total_mib": 0, "vram_free_mib": 0, "temp_c": 0, "power_w": 0.0}


def classify_hardware_tier(vram_mib: int, ram_gib: int, has_nvidia: bool, has_vulkan: bool = False) -> Dict[str, Any]:
    """Classify PC hardware into Tier S/A/B/C/CPU and recommend best-fit local model."""
    if has_nvidia and vram_mib >= 22000:
        tier = "S"
        tier_label = "旗舰独显"
        best_model_id = "v4_q4_k_m"
        best_model_label = "Dongfangshuo-27B (Q4_K_M · 15.4 GB)"
        low_spec = False
        max_ctx_k = 96
    elif has_nvidia and vram_mib >= 11500:
        tier = "A"
        tier_label = "主流大显存"
        best_model_id = "v4_q3_k_m" if vram_mib >= 15000 else "qwen3_14b_q4_k_m"
        best_model_label = "Dongfangshuo-27B (Q3_K_M)" if vram_mib >= 15000 else "Qwen3-14B (Q4_K_M · 不推荐)"
        low_spec = False
        max_ctx_k = 64 if vram_mib >= 15000 else 32
    elif (has_nvidia and vram_mib >= 5500) or (has_vulkan and ram_gib >= 16):
        tier = "B"
        tier_label = "轻量独显"
        best_model_id = "qwen3_8b_q4_k_m"
        best_model_label = "Qwen3-8B (Q4_K_M · 不推荐，建议在线 API)"
        low_spec = True
        max_ctx_k = 16
    elif vram_mib >= 3500 or ram_gib >= 12:
        tier = "C"
        tier_label = "入门 / 轻薄本"
        best_model_id = "qwen3_4b_q4_k_m"
        best_model_label = "Qwen3-4B (Q4_K_M · 不推荐，建议在线 API)"
        low_spec = True
        max_ctx_k = 8
    else:
        tier = "CPU"
        tier_label = "纯核显 / 极低配"
        best_model_id = "qwen3_4b_q4_k_m"
        best_model_label = "建议在线 API"
        low_spec = True
        max_ctx_k = 8

    return {
        "tier": tier,
        "tier_label": tier_label,
        "low_spec_recommended": low_spec,
        "recommended_preset_id": best_model_id,
        "recommended_preset_label": best_model_label,
        "recommended_max_context_k": max_ctx_k,
        "supports_flash_next_strata": bool(has_nvidia and vram_mib >= 7600 and ram_gib >= 24),
    }


def _static_cpu_info_sync() -> Tuple[str, int, str]:
    cpu_name = platform.processor() or platform.machine() or "CPU"
    threads = os.cpu_count() or 4
    os_name = f"{platform.system()} {platform.release()}"
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\Description\System\CentralProcessor\0") as k:
                cpu_name = str(winreg.QueryValueEx(k, "ProcessorNameString")[0] or cpu_name).strip()
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as k:
                prod = str(winreg.QueryValueEx(k, "ProductName")[0] or "")
                bld = str(winreg.QueryValueEx(k, "CurrentBuild")[0] or "")
                if bld.isdigit() and int(bld) >= 22000 and "Windows 10" in prod:
                    prod = prod.replace("Windows 10", "Windows 11")
                if prod:
                    os_name = prod
        except Exception:
            pass
    elif Path("/proc/cpuinfo").is_file():
        for ln in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore").splitlines():
            if "model name" in ln.lower() and ":" in ln:
                cpu_name = ln.split(":", 1)[1].strip()
                break
    return cpu_name, threads, os_name


def get_hardware_snapshot_sync(use_cache: bool = True) -> Dict[str, Any]:
    now = time.time()
    if use_cache and _HW_CACHE["data"] is not None and now - _HW_CACHE["ts"] < 4.0:
        return dict(_HW_CACHE["data"])

    cpu_name, threads, os_name = _static_cpu_info_sync()
    ram_gib = detect_system_ram_gib()
    free_ram_gib = detect_free_ram_gib()
    nv = probe_nvidia_gpu_sync()
    disk = shutil.disk_usage(str(BASE_DIR))
    free_disk_gb = round(disk.free / (1024 ** 3), 1)
    tier_info = classify_hardware_tier(
        vram_mib=nv["vram_total_mib"],
        ram_gib=ram_gib,
        has_nvidia=nv["has_nvidia"],
        has_vulkan=False,
    )
    snap = {
        "os_name": os_name,
        "cpu_name": cpu_name,
        "cpu_threads": threads,
        "ram_total_gib": ram_gib,
        "ram_free_gib": free_ram_gib,
        "free_disk_gb": free_disk_gb,
        "has_nvidia": nv["has_nvidia"],
        "gpu_name": nv["gpu_name"] or "集成显卡 / 无独立 N 卡",
        "driver_version": nv["driver_version"],
        "driver_num": nv["driver_num"],
        "vram_total_mib": nv["vram_total_mib"],
        "vram_free_mib": nv["vram_free_mib"],
        "gpu_temp_c": nv["temp_c"],
        "gpu_power_w": nv["power_w"],
        **tier_info,
    }
    _HW_CACHE["ts"] = now
    _HW_CACHE["data"] = snap
    return snap


async def get_hardware_snapshot_async(use_cache: bool = True) -> Dict[str, Any]:
    return await asyncio.to_thread(get_hardware_snapshot_sync, use_cache)


def run_preflight_checks_sync(settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run startup & local-engine preflight diagnostics with plain-Chinese actions."""
    hw = get_hardware_snapshot_sync(use_cache=False)
    checks: List[Dict[str, Any]] = []

    # 1. Llama Engine check
    llama_dir = BASE_DIR / "engine" / "llama"
    llama_exe = llama_dir / ("llama-server.exe" if os.name == "nt" else "llama-server")
    has_llama = llama_exe.is_file()
    cuda13_dll = llama_dir / "cuda_v13" / ("ggml-cuda.dll" if os.name == "nt" else "libggml-cuda.so")
    cuda12_dll = llama_dir / "cuda_v12" / ("ggml-cuda.dll" if os.name == "nt" else "libggml-cuda.so")
    vulkan_dll = llama_dir / "vulkan" / ("ggml-vulkan.dll" if os.name == "nt" else "libggml-vulkan.so")

    if has_llama:
        backends = ["CPU"]
        if vulkan_dll.is_file() or (llama_dir / "libggml-vulkan.so").is_file():
            backends.insert(0, "Vulkan")
        if hw["has_nvidia"]:
            if hw["driver_num"] >= 580.0 and (cuda13_dll.is_file() or (llama_dir / "libggml-cuda.so").is_file()):
                backends.insert(0, "CUDA 13")
            elif hw["driver_num"] >= 525.0 and cuda12_dll.is_file():
                backends.insert(0, "CUDA 12")
        checks.append({
            "id": "llama_engine",
            "name": "本地标准引擎 (llama.cpp)",
            "ok": True,
            "level": "ok",
            "detail": f"可用后端: {' / '.join(backends)}",
        })
    else:
        checks.append({
            "id": "llama_engine",
            "name": "本地标准引擎",
            "ok": False,
            "level": "warn",
            "detail": "当前为轻量 API 版（不含本地引擎），请用在线 API 或下载整合包",
        })

    # 2. NVIDIA Driver vs Strata check
    if hw["has_nvidia"]:
        drv = hw["driver_num"]
        if drv > 0 and drv < 525.0:
            checks.append({
                "id": "nvidia_driver",
                "name": "显卡驱动版本",
                "ok": False,
                "level": "warn",
                "detail": f"当前驱动 {hw['driver_version']} 过旧，建议更新至 535+ 或改用 Vulkan/API",
            })
        elif drv > 0 and drv < 580.65:
            checks.append({
                "id": "nvidia_driver",
                "name": "显卡驱动适配",
                "ok": True,
                "level": "ok",
                "detail": f"驱动 {hw['driver_version']} · 自动启用 CUDA 12 兼容模式",
            })
        else:
            checks.append({
                "id": "nvidia_driver",
                "name": "显卡驱动适配",
                "ok": True,
                "level": "ok",
                "detail": f"{hw['gpu_name']} · 驱动 {hw['driver_version']} (CUDA 13)",
            })
    else:
        checks.append({
            "id": "nvidia_driver",
            "name": "显卡环境",
            "ok": True,
            "level": "info",
            "detail": "无 NVIDIA 独显：标准引擎将自动启用 Vulkan / CPU 兼容模式",
        })

    # 3. RAM & Disk
    checks.append({
        "id": "memory_disk",
        "name": "内存与磁盘空间",
        "ok": hw["ram_total_gib"] >= 8 and hw["free_disk_gb"] >= 5.0,
        "level": "ok" if hw["ram_total_gib"] >= 8 else "warn",
        "detail": f"内存 {hw['ram_total_gib']} GB (可用 {hw['ram_free_gib']} GB) · 磁盘剩余 {hw['free_disk_gb']} GB",
    })

    # 4. Models or API readiness
    has_api = bool(settings and (settings.get("api_key") or settings.get("base_url")))
    ggufs = list(MODEL_DIR.glob("*.gguf")) + list(MODELS_DIR.rglob("*.gguf"))
    has_gguf = len(ggufs) > 0
    checks.append({
        "id": "ai_brain",
        "name": "AI 模型就绪状态",
        "ok": has_api or has_gguf,
        "level": "ok" if (has_api or has_gguf) else "warn",
        "detail": (
            f"检测到 {len(ggufs)} 个本地模型文件" if has_gguf else ""
        ) + (" + " if (has_gguf and has_api) else "") + ("已配置在线 API" if has_api else ("尚未配置本地模型或在线 API" if not has_gguf else "")),
    })

    return {
        "ok": all(c["ok"] for c in checks if c["id"] != "ai_brain"),
        "ready_to_play": has_api or has_gguf,
        "hardware": hw,
        "checks": checks,
    }
