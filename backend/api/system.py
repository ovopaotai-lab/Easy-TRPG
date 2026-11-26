# -*- coding: utf-8 -*-
"""System info, preflight diagnostics, backup, benchmarks, hot-reload, and updates."""
from __future__ import annotations

import asyncio
import os
import socket
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.config import BASE_DIR
from backend.core.auth import get_current_user
from backend.core.security import get_active_web_server_port, native_pick_path, open_directory_safely, require_loopback
from backend.core.updater import check_for_update, download_and_apply_update, get_local_version
from backend.engines.benchmark import get_benchmark_telemetry, run_benchmark_stream, run_parallel_benchmark_stream
from backend.engines.hardware import run_preflight_checks_sync
from backend.storage.backup import export_backup_to_folder, get_backup_overview, import_backup_from_folder
from backend.storage.db import get_user_db

router = APIRouter()
SERVER_BOOT_ID = uuid.uuid4().hex[:10]
_HOT_RELOAD_CALLBACK = None


def set_hot_reload_callback(fn) -> None:
    global _HOT_RELOAD_CALLBACK
    _HOT_RELOAD_CALLBACK = fn


def _get_local_ip() -> str:
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip.startswith(("192.168.", "10.")):
                return ip
    except Exception:
        pass
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


@router.get("/api/network_info")
def api_network_info():
    port = get_active_web_server_port()
    ip = _get_local_ip()
    pub_url = os.environ.get("PUBLIC_URL", "").strip()
    pub_file = BASE_DIR / "public_url.txt"
    if not pub_url and pub_file.is_file():
        pub_url = pub_file.read_text(encoding="utf-8", errors="ignore").strip()
    return {
        "local_url": f"http://127.0.0.1:{port}",
        "lan_url": f"http://{ip}:{port}",
        "public_url": pub_url,
    }


# -------------------- Backup --------------------
@router.get("/api/backup/overview")
def api_backup_overview(username: str = Depends(get_current_user)):
    return get_backup_overview(username)


@router.post("/api/backup/pick-folder", dependencies=[Depends(require_loopback)])
async def api_pick_backup_folder(payload: Dict[str, Any] = {}):
    chosen = await asyncio.to_thread(native_pick_path, "folder", str(payload.get("title") or "选择备份目录"))
    return {"folder_path": chosen}


@router.post("/api/backup/open-folder", dependencies=[Depends(require_loopback)])
def api_open_backup_folder(payload: Dict[str, Any]):
    p = Path(str(payload.get("folder_path") or BASE_DIR / "backups"))
    p.mkdir(parents=True, exist_ok=True)
    open_directory_safely(p)
    return {"status": "ok"}


@router.post("/api/backup/export-folder", dependencies=[Depends(require_loopback)])
def api_export_backup(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    dest = Path(str(payload.get("folder_path") or BASE_DIR / "backups" / "manual_export"))
    return export_backup_to_folder(username, dest, payload)


@router.post("/api/backup/import-folder", dependencies=[Depends(require_loopback)])
def api_import_backup(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    src = Path(str(payload.get("folder_path") or ""))
    try:
        return import_backup_from_folder(username, src)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/api/backup/import-uploaded-folder")
def api_import_uploaded_folder():
    raise HTTPException(status_code=400, detail="请使用本机目录导入功能")


# -------------------- System Version / Preflight / Hot Reload --------------------
@router.get("/api/system/version")
def api_system_version():
    return {"ok": True, "version": get_local_version(), "boot_id": SERVER_BOOT_ID}


@router.get("/api/system/preflight")
async def api_system_preflight(username: str = Depends(get_current_user)):
    s = get_user_db(username).get_settings()
    res = await asyncio.to_thread(run_preflight_checks_sync, s)
    return {"status": "ok", **res}


class DevHotReloadRequest(BaseModel):
    changed_files: List[str] = ["server.py"]
    target_version: str = ""


@router.post("/api/system/dev/hot_reload", dependencies=[Depends(require_loopback)])
async def api_dev_hot_reload(req: DevHotReloadRequest):
    if _HOT_RELOAD_CALLBACK is not None:
        info = _HOT_RELOAD_CALLBACK(req.changed_files, req.target_version)
        return {"ok": True, **info}
    return {"ok": True, "hot_updated": False, "reason": "热替换未挂接"}


@router.get("/api/system/update/check")
async def api_update_check():
    return await check_for_update()


@router.post("/api/system/update/apply", dependencies=[Depends(require_loopback)])
@router.post("/api/system/update/stream", dependencies=[Depends(require_loopback)])
async def api_update_apply():
    res = await download_and_apply_update()
    if res.get("ok") and res.get("updated") and _HOT_RELOAD_CALLBACK is not None:
        res["hot_reload"] = _HOT_RELOAD_CALLBACK(
            res.get("changed_files") or [],
            str(res.get("version") or ""),
        )
    return res


# -------------------- Benchmark --------------------
class BenchmarkStreamRequest(BaseModel):
    model: str
    mode: str = "quick"


class ParallelBenchmarkRequest(BaseModel):
    model: str
    concurrency: int = 2


@router.get("/api/system/benchmark/telemetry")
async def api_benchmark_telemetry():
    return await get_benchmark_telemetry()


@router.post("/api/system/benchmark/stream")
async def api_benchmark_stream(req: BenchmarkStreamRequest, username: str = Depends(get_current_user)):
    s = get_user_db(username).get_settings()
    return StreamingResponse(run_benchmark_stream(req.model, req.mode, s), media_type="application/x-ndjson")


@router.post("/api/system/benchmark/parallel_stream")
async def api_benchmark_parallel(req: ParallelBenchmarkRequest, username: str = Depends(get_current_user)):
    s = get_user_db(username).get_settings()
    return StreamingResponse(run_parallel_benchmark_stream(req.model, req.concurrency, s), media_type="application/x-ndjson")
