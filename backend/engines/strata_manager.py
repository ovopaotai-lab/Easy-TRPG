# -*- coding: utf-8 -*-
"""Strata v0.2.21 MoE engine manager with CUDA 13/12 auto-select, crash recovery, and diagnosis."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from backend.config import BASE_DIR, ENGINE_LOGS_DIR, atomic_write_json
from backend.engines.hardware import detect_free_ram_gib, get_hardware_snapshot_sync
from backend.engines.process_guard import (
    kill_processes_by_image_name,
    linux_pdeathsig_preexec,
    pick_available_port,
    read_log_tail,
    register_spawned_engine_proc,
)

logger = logging.getLogger("easy_trpg.strata")

ACTIVE_STRATA_PORT: int = 8080
ACTIVE_STRATA_MODEL: str = ""
ACTIVE_STRATA_PROC: Optional[subprocess.Popen] = None


def kill_strata_server() -> None:
    global ACTIVE_STRATA_MODEL, ACTIVE_STRATA_PROC
    if ACTIVE_STRATA_PROC is not None:
        from backend.engines.process_guard import terminate_process_tree_sync
        terminate_process_tree_sync(ACTIVE_STRATA_PROC)
        ACTIVE_STRATA_PROC = None
    kill_processes_by_image_name(("strata.exe", "strata-vision.exe", "strata"))
    ACTIVE_STRATA_MODEL = ""


def _resolve_strata_engine_dir(strata_root: Path, driver_num: float) -> Tuple[Path, str]:
    """Choose CUDA 13 engine (driver >= 580.65) or CUDA 12 fallback engine (driver >= 525)."""
    eng13 = strata_root / "engine"
    eng12 = strata_root / "engine_cuda12"
    if (driver_num <= 0 or driver_num >= 580.65) and (eng13 / ("strata.exe" if os.name == "nt" else "strata")).is_file():
        return eng13, "cuda13"
    if (eng12 / ("strata.exe" if os.name == "nt" else "strata")).is_file():
        return eng12, "cuda12"
    return eng13, "cuda13"


def translate_strata_crash(returncode: Optional[int], raw_tail: str, hw: Dict[str, Any]) -> Dict[str, Any]:
    """Translate cryptic Strata errors (including PCIe probe failed) into actionable Chinese recovery cards."""
    low = (raw_tail or "").lower()
    if "pcie probe failed" in low or "pcie_frac" in low:
        return {
            "code": "STRATA_PCIE_PROBE_FAILED",
            "engine": "strata",
            "title": "Flash-Next 显卡带宽探测失败",
            "message": (
                "Strata 引擎在您的电脑上未能通过 PCIe 带宽探测（常见于核显/双显卡笔记本、虚拟化环境或老驱动）。\n"
                "建议直接改用兼容性更好的「标准引擎 (Qwen3-8B / 27B)」或使用在线 API。"
            ),
            "raw_tail": raw_tail[-600:],
            "actions": [
                {"id": "switch_llama", "label": "下载标准轻量模型 (Qwen3-8B)", "action": "open_engine_downloads"},
                {"id": "switch_api", "label": "改用在线 API", "action": "open_api_setup"},
                {"id": "run_preflight", "label": "查看环境自检", "action": "run_preflight"},
            ],
        }
    if any(k in low for k in ("cuda driver", "insufficient", "nvml", "cublas", "cudnn")):
        return {
            "code": "STRATA_DRIVER_TOO_OLD",
            "engine": "strata",
            "title": "NVIDIA 显卡驱动版本不兼容",
            "message": f"当前驱动 {hw.get('driver_version') or '未知'} 无法运行 Flash-Next。请更新显卡驱动，或切换为「标准引擎 / 在线 API」。",
            "raw_tail": raw_tail[-600:],
            "actions": [
                {"id": "switch_llama", "label": "改用标准引擎", "action": "open_engine_downloads"},
                {"id": "switch_api", "label": "改用在线 API", "action": "open_api_setup"},
            ],
        }
    if any(k in low for k in ("out of memory", "failed to alloc", "bad_alloc")):
        return {
            "code": "STRATA_OOM",
            "engine": "strata",
            "title": "显存或系统内存不足",
            "message": f"当前设备 {hw.get('vram_total_mib', 0)//1024}G 显存 / {hw.get('ram_total_gib', 0)}G 内存不足以加载 Flash-Next MoE。",
            "raw_tail": raw_tail[-600:],
            "actions": [
                {"id": "switch_llama", "label": "下载 4B/8B 轻量模型", "action": "open_engine_downloads"},
                {"id": "switch_api", "label": "改用在线 API", "action": "open_api_setup"},
            ],
        }
    return {
        "code": "STRATA_CRASH",
        "engine": "strata",
        "title": "Flash-Next (Strata) 启动失败",
        "message": f"本地引擎退出 (code={returncode})。建议点击下方一键切换至更稳定的标准模型或在线 API。",
        "raw_tail": raw_tail[-600:],
        "actions": [
            {"id": "switch_llama", "label": "切换标准轻量模型", "action": "open_engine_downloads"},
            {"id": "switch_api", "label": "改用在线 API", "action": "open_api_setup"},
            {"id": "run_preflight", "label": "一键环境自检", "action": "run_preflight"},
        ],
    }


def _resolve_strata_pack_dir(strata_root: Path, gguf_p: Path, slug: str) -> Path:
    packs_root = strata_root / "data" / "packs"
    packs_root.mkdir(parents=True, exist_ok=True)
    candidate_roots = [packs_root]
    env_packs = os.environ.get("STRATA_PACKS_DIR", "").strip()
    if env_packs and Path(env_packs).is_dir():
        candidate_roots.append(Path(env_packs))
    if os.name == "nt" and Path(r"D:\Strata\data\packs").is_dir():
        candidate_roots.append(Path(r"D:\Strata\data\packs"))

    cands = [slug]
    low = gguf_p.name.lower()
    if "dongfangshuo" in low and "iq3_xxs" in low:
        cands.insert(0, "dongfangshuo-iq3_xxs")
    elif "swift" in low and "iq3_xxs" in low:
        cands.insert(0, "swift-iq3_xxs")

    def _pack_ready(pdir: Path) -> bool:
        return (
            (pdir / "index.txt").is_file()
            and (pdir / "native_experts.txt").is_file()
            and (pdir / "dense.bin").is_file()
            and (pdir / "tokenizer" / "vocab.json").is_file()
        )

    for root in candidate_roots:
        for cname in cands:
            cand = root / cname
            if _pack_ready(cand):
                return cand
        for sub in root.iterdir():
            if sub.is_dir() and _pack_ready(sub):
                if slug in sub.name.lower() or gguf_p.name.lower() in (sub / "native_experts.txt").read_text(encoding="utf-8", errors="ignore").lower():
                    return sub
    return packs_root / slug


async def _ensure_strata_pack_ready(
    strata_py: Path,
    strata_root: Path,
    gguf_p: Path,
    pack_dir: Path,
    *,
    status_callback=None,
) -> Optional[Dict[str, Any]]:
    """Build native Strata index/tokenizer pack via tools/iq_pack.py if not yet present."""
    if (
        (pack_dir / "index.txt").is_file()
        and (pack_dir / "native_experts.txt").is_file()
        and (pack_dir / "dense.bin").is_file()
        and (pack_dir / "tokenizer" / "vocab.json").is_file()
    ):
        return None

    iq_pack_script = strata_root / "tools" / "iq_pack.py"
    if not iq_pack_script.is_file():
        return {
            "code": "STRATA_PACK_TOOL_MISSING",
            "engine": "strata",
            "title": "缺少 Strata 索引构建脚本",
            "message": f"未找到 {iq_pack_script}，无法为首次加载构建模型索引。",
            "actions": [{"id": "api", "label": "改用在线 API", "action": "open_api_setup"}],
        }

    if status_callback:
        await status_callback(f"首次加载 {gguf_p.name}，正在构建 Strata 索引包...")

    ENGINE_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    iq_log = ENGINE_LOGS_DIR / f"iq-pack-{pack_dir.name}.log"
    env = os.environ.copy()
    for gguf_rel in (("third_party", "strata-gguf-py"), ("third_party", "llama.cpp", "gguf-py")):
        gp = strata_root.joinpath(*gguf_rel)
        if gp.is_dir():
            env["STRATA_GGUF_PY"] = str(gp)
            break

    cmd = [
        str(strata_py),
        "-c",
        "import runpy, sys; sys.path.insert(0, sys.argv[1]); sys.argv = sys.argv[2:]; runpy.run_path(sys.argv[0], run_name='__main__')",
        str(strata_root),
        str(iq_pack_script),
        "--gguf",
        str(gguf_p.resolve()),
        "--out",
        str(pack_dir),
        "--compat-bf16",
    ]
    kw: Dict[str, Any] = {
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.STDOUT,
        "cwd": str(strata_root),
        "env": env,
    }
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    proc = await asyncio.create_subprocess_exec(*cmd, **kw)
    out_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=1200.0)
    iq_text = (out_bytes or b"").decode("utf-8", errors="replace")
    iq_log.write_text(iq_text, encoding="utf-8", errors="ignore")
    if proc.returncode != 0 or not (pack_dir / "tokenizer" / "vocab.json").is_file():
        hw = get_hardware_snapshot_sync(use_cache=True)
        return translate_strata_crash(proc.returncode, iq_text[-600:], hw)
    return None


def _build_strata_config_sync(
    *,
    local_meta: Dict[str, Any],
    strata_root: Path,
    engine_dir: Path,
    port: int,
    safe_fallback: bool = False,
) -> Tuple[Optional[Path], Optional[str], Optional[Path]]:
    gguf_str = str(local_meta.get("gguf_path") or "")
    gguf_p = Path(gguf_str)
    if not gguf_str or not gguf_p.is_file():
        return None, "未找到 Flash-Next GGUF 模型文件", None

    hw = get_hardware_snapshot_sync(use_cache=False)
    vram_mib = hw["vram_total_mib"]
    vram_free_mib = hw.get("vram_free_mib") or vram_mib
    sys_ram_gib = hw["ram_total_gib"]
    free_ram_gib = detect_free_ram_gib()

    slug = re.sub(r"[^a-zA-Z0-9_\-]", "-", gguf_p.stem).strip("-").lower() or "flash-next"
    pack_dir = _resolve_strata_pack_dir(strata_root, gguf_p, slug)

    strata_exe = engine_dir / ("strata.exe" if os.name == "nt" else "strata")
    vision_exe = engine_dir / ("strata-vision.exe" if os.name == "nt" else "strata-vision")
    expert_profile = strata_root / "data" / "expert-profile.bin"

    args_out = ["--pack", str(pack_dir), "--native", str(gguf_p.resolve())]
    if expert_profile.is_file():
        args_out.extend(["--expert-profile", str(expert_profile)])

    if safe_fallback:
        max_ctx = "16384"
        kv_type = "int8"
        reserve_mib = "1200"
        args_out.extend(
            [
                "--expert-cache", "auto",
                "--prefill", "auto",
                "--max-context", max_ctx,
                "--kv", kv_type,
                "--kv-grow",
                "--vram-reserve-mib", reserve_mib,
            ]
        )
        if free_ram_gib > 10:
            budget_gib = max(6, min(16, int(free_ram_gib - 6)))
            args_out.extend(["--resident-budget-gib", str(budget_gib)])
    else:
        max_ctx = (
            "98304" if vram_free_mib >= 28000
            else ("65536" if vram_free_mib >= 18000 else ("32768" if vram_free_mib >= 12000 else "16384"))
        )
        kv_type = "fp16" if vram_free_mib >= 26000 else "int8"
        has_dflash2 = (strata_root / "data" / "dflash2").is_dir() and any((strata_root / "data" / "dflash2").glob("*.pack"))
        args_out.extend(
            [
                "--expert-cache", "auto",
                "--prefill", "auto",
                "--max-context", max_ctx,
                "--kv", kv_type,
                "--kv-grow",
            ]
        )
        if not has_dflash2:
            args_out.extend(["--spec", "4", "--spec-min-p", "0.5"])
        if vram_free_mib < 22000 and int(max_ctx) > 32768:
            args_out.extend(["--kv-resident", "32768"])
        if (pack_dir / "native_experts.txt").is_file() and free_ram_gib >= 44.0:
            args_out.append("--resident-experts")
        else:
            ram_budget = max(6, min(16, sys_ram_gib - 10)) if free_ram_gib <= 14 else max(8, min(28, int(free_ram_gib - 8)))
            args_out.extend(["--resident-budget-gib", str(ram_budget)])
        reserve_mib = "900" if vram_mib >= 16000 else "600"
        args_out.extend(["--vram-reserve-mib", reserve_mib])

    mmproj_path = str(local_meta.get("mmproj_path") or "")
    has_vision = bool(not safe_fallback and mmproj_path and Path(mmproj_path).is_file() and vision_exe.is_file())
    if has_vision and "--vision" not in args_out:
        args_out.append("--vision")

    ENGINE_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    eng_log = ENGINE_LOGS_DIR / f"strata-{slug}.log"
    cfg_path = ENGINE_LOGS_DIR / f"strata-cfg-{slug}.json"
    cfg_obj: Dict[str, Any] = {
        "exe": str(strata_exe),
        "args": args_out,
        "cwd": str(strata_root),
        "tokenizer": str(pack_dir / "tokenizer"),
        "log": str(eng_log),
        "model_name": str(local_meta.get("upstream_model") or local_meta.get("id") or "Flash-Next"),
        "port": port,
        "lib_dirs": [str(engine_dir)],
        "env": {
            "STRATA_ROUTE_TAIL_SKIP": "0" if vram_mib >= 22000 else "7",
            "STRATA_SPEC_COUPLED": "1",
            "STRATA_SPEC_GUMBEL": "1",
        },
        "gpu": 0,
        "gpus_asked": True,
        "reasoning_effort": "low",
    }
    if has_vision:
        cfg_obj["vision"] = {
            "exe": str(vision_exe),
            "mmproj": str(Path(mmproj_path).resolve()),
            "model": str(gguf_p.resolve()),
            "gpu": bool(vram_free_mib >= 18000),
            "max_tokens": 1024,
        }
    atomic_write_json(cfg_path, cfg_obj)
    return cfg_path, None, pack_dir


async def ensure_strata_ready(
    model_id: str,
    local_meta: Dict[str, Any],
    *,
    status_callback=None,
) -> Optional[Dict[str, Any]]:
    """Preflight, reuse running instance, or launch Strata v0.2.21 with adaptive safe-flag + CUDA12 fallback."""
    global ACTIVE_STRATA_PORT, ACTIVE_STRATA_MODEL, ACTIVE_STRATA_PROC

    hw = await asyncio.to_thread(get_hardware_snapshot_sync, True)
    if not hw["has_nvidia"]:
        return {
            "code": "NO_NVIDIA_FOR_STRATA",
            "engine": "strata",
            "title": "该模型需要 NVIDIA 独显",
            "message": "Flash-Next (Strata) 仅支持 NVIDIA 独立显卡；您的设备可免费使用标准引擎 (Qwen3-4B/8B) 或在线 API。",
            "actions": [
                {"id": "dl", "label": "下载兼容轻量模型", "action": "open_engine_downloads"},
                {"id": "api", "label": "改用在线 API", "action": "open_api_setup"},
            ],
        }
    if hw["ram_total_gib"] < 20:
        return {
            "code": "LOW_RAM_FOR_STRATA",
            "engine": "strata",
            "title": "系统内存不足以运行 Flash-Next",
            "message": f"Flash-Next 需要至少 24GB 内存（当前 {hw['ram_total_gib']}GB）。建议下载 Qwen3-4B / 8B 或改用在线 API。",
            "actions": [
                {"id": "dl", "label": "下载 4B/8B 轻量模型", "action": "open_engine_downloads"},
                {"id": "api", "label": "改用在线 API", "action": "open_api_setup"},
            ],
        }

    strata_root = BASE_DIR / "engine" / "strata"
    primary_dir, primary_cuda = _resolve_strata_engine_dir(strata_root, hw["driver_num"])
    strata_py = BASE_DIR / "runtime" / "python" / ("python.exe" if os.name == "nt" else "python3")
    if not strata_py.is_file():
        import sys
        strata_py = Path(sys.executable)
    strata_script = strata_root / "serve" / "server.py"
    if not strata_script.is_file():
        return {
            "code": "NO_STRATA_BUNDLE",
            "engine": "strata",
            "title": "未检测到 Strata 引擎文件",
            "message": "请使用完整的整合包，或切换至标准模型 / 在线 API。",
            "actions": [{"id": "api", "label": "改用在线 API", "action": "open_api_setup"}],
        }

    gguf_p = Path(str(local_meta.get("gguf_path") or ""))
    if not gguf_p.is_file():
        return {"code": "STRATA_CONFIG_ERR", "engine": "strata", "title": "模型文件缺失", "message": "未找到 Flash-Next GGUF 模型文件", "actions": []}

    resolved_gguf = gguf_p.resolve()
    gguf_key = f"{resolved_gguf}::{resolved_gguf.stat().st_size}"
    expected_model = str(local_meta.get("upstream_model") or local_meta.get("id") or "")

    # Reuse live Strata server when the same model is already resident in memory/VRAM
    if ACTIVE_STRATA_MODEL == gguf_key and (ACTIVE_STRATA_PROC is None or ACTIVE_STRATA_PROC.poll() is None):
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=2.5) as client:
                r = await client.get(f"http://127.0.0.1:{ACTIVE_STRATA_PORT}/v1/models")
                if r.status_code == 200:
                    local_meta["base_url"] = f"http://127.0.0.1:{ACTIVE_STRATA_PORT}/v1"
                    return None
        except Exception:
            pass
    elif not ACTIVE_STRATA_MODEL:
        # Adopt an orphan Strata server matching the target model (e.g. after Easy-TRPG server restart)
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=2.0) as client:
                r = await client.get(f"http://127.0.0.1:{ACTIVE_STRATA_PORT}/v1/models")
                if r.status_code == 200:
                    data = r.json() if r.headers.get("content-type", "").lower().startswith("application/json") else {}
                    ids = [str(m.get("id") or "") for m in (data.get("data") or []) if isinstance(m, dict)]
                    exp_low = expected_model.lower()
                    if any(mid.lower() == exp_low or (exp_low and exp_low in mid.lower()) for mid in ids):
                        ACTIVE_STRATA_MODEL = gguf_key
                        local_meta["base_url"] = f"http://127.0.0.1:{ACTIVE_STRATA_PORT}/v1"
                        return None
        except Exception:
            pass

    slug = re.sub(r"[^a-zA-Z0-9_\-]", "-", gguf_p.stem).strip("-").lower() or "flash-next"
    pack_dir = await asyncio.to_thread(_resolve_strata_pack_dir, strata_root, gguf_p, slug)
    pack_err = await _ensure_strata_pack_ready(strata_py, strata_root, gguf_p, pack_dir, status_callback=status_callback)
    if pack_err is not None:
        return pack_err

    # Kill any previous Strata instance BEFORE choosing a port so 8080 is reclaimed cleanly
    await asyncio.to_thread(kill_strata_server)
    await asyncio.sleep(0.8)

    port = pick_available_port(8080, range(8080, 8110))
    ACTIVE_STRATA_PORT = port
    local_meta["base_url"] = f"http://127.0.0.1:{port}/v1"

    attempts: List[Tuple[str, Path, bool]] = [
        (primary_cuda, primary_dir, False),
        (primary_cuda, primary_dir, True),
    ]
    eng12 = strata_root / "engine_cuda12"
    if primary_cuda != "cuda12" and (eng12 / ("strata.exe" if os.name == "nt" else "strata")).is_file():
        attempts.append(("cuda12", eng12, True))

    last_crash: Optional[Dict[str, Any]] = None
    for cuda_ver, eng_dir, safe_mode in attempts:
        if status_callback:
            lbl = f"尝试安全兼容参数重启 Strata ({cuda_ver})..." if safe_mode else f"启动 Flash-Next ({cuda_ver})，约 20~60 秒..."
            await status_callback(lbl)

        cfg_path, cfg_err, _ = await asyncio.to_thread(
            _build_strata_config_sync,
            local_meta=local_meta,
            strata_root=strata_root,
            engine_dir=eng_dir,
            port=port,
            safe_fallback=safe_mode,
        )
        if cfg_err or not cfg_path:
            return {"code": "STRATA_CONFIG_ERR", "engine": "strata", "title": "模型配置异常", "message": cfg_err or "配置文件失败", "actions": []}

        serve_log = ENGINE_LOGS_DIR / "strata-serve.log"
        eng_log = Path(json.loads(cfg_path.read_text(encoding="utf-8"))["log"])
        env = os.environ.copy()
        env["TRPG_PARENT_PID"] = str(os.getpid())
        env["TRPG_NO_AUTO_RESPAWN"] = "1"
        if os.name != "nt":
            env["LD_LIBRARY_PATH"] = f"{eng_dir}:{env.get('LD_LIBRARY_PATH', '')}"

        # Insert strata_root explicitly so Windows embeddable python._pth resolves `serve.server`.
        cli = [
            str(strata_py),
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); from serve import server; sys.exit(server.main(sys.argv[2:]))",
            str(strata_root),
            "--engine",
            "strata",
            "--config",
            str(cfg_path),
            "--port",
            str(port),
            "--no-api-key",
        ]
        kw: Dict[str, Any] = {
            "stdout": open(serve_log, "w", encoding="utf-8", errors="ignore"),
            "stderr": subprocess.STDOUT,
            "cwd": str(strata_root),
            "env": env,
        }
        if os.name == "nt":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            kw["startupinfo"] = si
        else:
            kw["preexec_fn"] = linux_pdeathsig_preexec

        proc = subprocess.Popen(cli, **kw)
        ACTIVE_STRATA_PROC = proc
        register_spawned_engine_proc(proc)
        try:
            kw["stdout"].close()
        except Exception:
            pass

        crashed = False
        for sec in range(300):
            await asyncio.sleep(1.0)
            if proc.poll() is not None:
                raw_tail = read_log_tail([serve_log, eng_log])
                last_crash = translate_strata_crash(proc.returncode, raw_tail, hw)
                crashed = True
                break
            if status_callback and sec > 0 and sec % 10 == 0:
                await status_callback(f"正在加载 Flash-Next ({cuda_ver})... ({sec}s)")
            try:
                async with httpx.AsyncClient(trust_env=False, timeout=2.0) as client:
                    r = await client.get(f"http://127.0.0.1:{port}/v1/models")
                    if r.status_code == 200:
                        ACTIVE_STRATA_MODEL = gguf_key
                        local_meta["base_url"] = f"http://127.0.0.1:{port}/v1"
                        return None
            except Exception:
                pass

        await asyncio.to_thread(kill_strata_server)
        if not crashed:
            last_crash = translate_strata_crash(-1, "启动超时", hw)
            break

    return last_crash
