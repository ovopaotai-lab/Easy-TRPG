import os
import sys
import math
import shutil
import json
import time
import uuid
import re
import random
import base64
import io
import hashlib
import asyncio
import subprocess
import threading
import ipaddress
import socket
import httpx
from pathlib import Path
from urllib.parse import urlparse
from typing import List, Dict, Any, Optional, Tuple, Callable, Awaitable
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse, Response
from PIL import Image, ImageDraw


# ==================== 通用安全工具：原子写入 JSON / 安全整数 / 仅本机访问 ====================
def _atomic_replace_with_retry(tmp: Path, target: Path) -> None:
    last_err: Optional[Exception] = None
    for attempt in range(10):
        try:
            os.replace(tmp, target)
            return
        except PermissionError as e:
            last_err = e
            time.sleep(0.05 * (attempt + 1))
    if last_err:
        raise last_err


def atomic_write_bytes(path, content: bytes) -> None:
    """原子写入二进制文件：先写同目录临时文件并 fsync，再 os.replace 覆盖目标"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        _atomic_replace_with_retry(tmp, p)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def atomic_write_text(path, content: str, encoding: str = "utf-8") -> None:
    """原子写入文本文件"""
    atomic_write_bytes(path, content.encode(encoding))


def atomic_write_json(path, data: Any, indent: Optional[int] = 2, ensure_ascii: bool = False) -> None:
    """原子写入 JSON：先写入同目录唯一临时文件并 fsync，再 os.replace 覆盖目标，杜绝断电/并发导致的半截文件。
    Windows 上目标文件被杀毒/索引短暂占用时会 PermissionError，这里做小幅重试。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        _atomic_replace_with_retry(tmp, p)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def safe_int(value: Any, default: int = 0) -> int:
    """容错整数转换：None / 空串 / 布尔值 / 非法值统一回退为默认值，避免导入外部世界书或配置空值时 500"""
    try:
        if value is None or value == "" or isinstance(value, bool):
            return default
        fval = float(value)
        if math.isnan(fval) or math.isinf(fval):
            return default
        return int(fval)
    except (TypeError, ValueError, OverflowError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """容错浮点数转换：None / 空串 / 布尔值 / NaN / Inf 统一回退为默认值"""
    try:
        if value is None or value == "" or isinstance(value, bool):
            return default
        fval = float(value)
        if math.isnan(fval) or math.isinf(fval):
            return default
        return fval
    except (TypeError, ValueError, OverflowError):
        return default


def open_directory_safely(target: Path) -> bool:
    """跨平台安全打开本地目录（兼容 Windows / macOS / Linux，拒绝 UNC 网络路径与非目录路径）"""
    raw_str = str(target or "").strip()
    if not raw_str or raw_str.startswith("\\\\") or raw_str.startswith("//"):
        raise HTTPException(status_code=400, detail="不支持打开网络共享或空路径")
    resolved = target.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"目录不存在: {resolved}")
    if os.name == "nt":
        try:
            os.startfile(str(resolved))
            return True
        except Exception:
            subprocess.Popen(["explorer.exe", str(resolved)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    if sys.platform == "darwin":
        if shutil.which("open"):
            subprocess.Popen(["open", str(resolved)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        return False
    if shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", str(resolved)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    return False


def require_loopback(request: Request) -> None:
    """仅允许本机 (127.0.0.1 / ::1) 调用的危险文件系统/系统级接口依赖（局域网手机端不可调用）"""
    host = ""
    try:
        host = (request.client.host if request.client else "") or ""
    except Exception:
        host = ""
    if host.startswith("::ffff:"):
        host = host[7:]
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="仅限本机操作")


def _get_process_image_name(pid: int) -> str:
    """通过 tasklist 查询 PID 对应的进程映像名（小写），失败返回空串"""
    if os.name != "nt":
        return ""
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {int(pid)}", "/FO", "CSV", "/NH"],
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            startupinfo=si,
            stderr=subprocess.DEVNULL,
            timeout=8,
        )
        text = out.decode("utf-8", errors="ignore") if isinstance(out, bytes) else str(out)
        if "," not in text:
            try:
                text = out.decode("gbk", errors="ignore")
            except Exception:
                pass
        for line in text.splitlines():
            line = line.strip()
            if line.startswith('"'):
                return line.split('","')[0].strip('"').lower()
        return ""
    except Exception:
        return ""


# 原生文件/文件夹选择器全局互斥锁（防止多次点击同时弹出多个对话框）
_NATIVE_PICKER_LOCK = threading.Lock()


def _ps_quote(text: str) -> str:
    """PowerShell 单引号字符串转义"""
    return str(text or "").replace("'", "''")


def _native_pick_path_powershell(mode: str = "file", title: str = "", file_filter: str = "") -> str:
    """PowerShell WinForms 原生选择器（嵌入式 Python 无 tkinter 时使用）。调用方负责持锁。"""
    if os.name != "nt":
        return ""
    try:
        enc_prefix = "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
        if mode in ("folder", "dir"):
            ps_cmd = (
                enc_prefix
                + "Add-Type -AssemblyName System.Windows.Forms; "
                "$top = New-Object System.Windows.Forms.Form -Property @{TopMost=$true}; "
                "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
                f"$f.Description = '{_ps_quote(title or '选择模型文件夹')}'; "
                "$f.ShowNewFolderButton = $true; "
                "if ($f.ShowDialog($top) -eq 'OK') { Write-Output $f.SelectedPath }; "
                "$top.Dispose()"
            )
        else:
            ps_cmd = (
                enc_prefix
                + "Add-Type -AssemblyName System.Windows.Forms; "
                "$top = New-Object System.Windows.Forms.Form -Property @{TopMost=$true}; "
                "$f = New-Object System.Windows.Forms.OpenFileDialog; "
                f"$f.Title = '{_ps_quote(title or '选择 .gguf 文件')}'; "
                f"$f.Filter = '{_ps_quote(file_filter or 'GGUF Models (*.gguf)|*.gguf|All Files (*.*)|*.*')}'; "
                "if ($f.ShowDialog($top) -eq 'OK') { Write-Output $f.FileName }; "
                "$top.Dispose()"
            )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-STA", "-Command", ps_cmd],
            encoding="utf-8",
            errors="ignore",
            timeout=600,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).strip()
        if out:
            return str(Path(out.splitlines()[-1].strip()))
    except Exception:
        pass
    return ""


def _native_pick_file_or_folder(mode: str = "file", title: str = "") -> str:
    """在 Windows 下调用系统原生文件/文件夹选择对话框（优先 tkinter，若嵌入式 Python 无 tkinter 则无缝回退 PowerShell WinForms）"""
    with _NATIVE_PICKER_LOCK:
        picked = ""
        tk_ok = False
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            try:
                root.attributes("-topmost", True)
            except Exception:
                pass
            if mode in ("folder", "dir"):
                picked = filedialog.askdirectory(
                    title=title or "选择模型文件夹"
                ) or ""
            else:
                picked = filedialog.askopenfilename(
                    title=title or "选择 .gguf 文件",
                    filetypes=[("GGUF 模型文件", "*.gguf"), ("所有文件", "*.*")],
                ) or ""
            tk_ok = True
            try:
                root.destroy()
            except Exception:
                pass
            if picked:
                return str(Path(picked))
        except Exception:
            pass

        # tkinter 正常弹出且用户主动取消时，不再重复弹出回退对话框
        if tk_ok:
            return ""
        if os.name == "nt":
            return _native_pick_path_powershell(mode, title)
        # Linux / macOS 原生文件选择器回退（zenity / kdialog / osascript）
        if sys.platform == "darwin" and shutil.which("osascript"):
            try:
                osa = (
                    f'POSIX path of (choose folder with prompt "{(title or "选择文件夹").replace(chr(34), "")}")'
                    if mode in ("folder", "dir")
                    else f'POSIX path of (choose file with prompt "{(title or "选择 .gguf 文件").replace(chr(34), "")}")'
                )
                out = subprocess.check_output(["osascript", "-e", osa], encoding="utf-8", errors="ignore", timeout=600).strip()
                if out:
                    return str(Path(out))
            except Exception:
                return ""
        if shutil.which("zenity"):
            try:
                cmd = ["zenity", "--file-selection", f"--title={title or '选择路径'}"]
                if mode in ("folder", "dir"):
                    cmd.append("--directory")
                else:
                    cmd.append("--file-filter=GGUF Models (*.gguf) | *.gguf")
                out = subprocess.check_output(cmd, encoding="utf-8", errors="ignore", timeout=600).strip()
                if out:
                    return str(Path(out.splitlines()[-1].strip()))
            except Exception:
                return ""
        if shutil.which("kdialog"):
            try:
                cmd = (
                    ["kdialog", "--getexistingdirectory", str(Path.home()), "--title", title or "选择文件夹"]
                    if mode in ("folder", "dir")
                    else ["kdialog", "--getopenfilename", str(Path.home()), "*.gguf", "--title", title or "选择 .gguf 文件"]
                )
                out = subprocess.check_output(cmd, encoding="utf-8", errors="ignore", timeout=600).strip()
                if out:
                    return str(Path(out.splitlines()[-1].strip()))
            except Exception:
                return ""
        return ""

# ==================== 本地模型目录、即插即用扫描、指定路径挂载与 HF 下载中心 ====================
LOCAL_MODELS_CATALOG: List[Dict[str, Any]] = []
DISCOVERED_LOCAL_MODELS: Dict[str, Dict[str, Any]] = {}
_DISCOVERED_MODELS_LOCK = threading.RLock()
_SPAWNED_ENGINE_PROCS: List[subprocess.Popen] = []
_BUNDLE_ROOT = Path(__file__).parent.resolve()
_CUSTOM_PATHS_FILE = _BUNDLE_ROOT / "data" / "custom_model_paths.json"
_ENGINE_LOGS_DIR = _BUNDLE_ROOT / "data" / "engine_logs"
_ACTIVE_STRATA_PORT: int = 8080
_ACTIVE_LLAMA_PORT: int = 11434
HF_DOWNLOAD_TASKS: Dict[str, Dict[str, Any]] = {}
HF_DOWNLOAD_ASYNC_TASKS: Dict[str, asyncio.Task] = {}

# 用户官方 HuggingFace 模型仓库预设清单（按 Dongfangshuo-27B 与 Flash-Next 两个子文件夹归类）
HF_PRESET_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "v4_q3_k_m",
        "series": "Dongfangshuo-27B",
        "subfolder": "Dongfangshuo-27B",
        "series_title": "Dongfangshuo-27B",
        "repo_id": "dongfangshuo/Dongfangshuo-Qwen3.8-27B-NSFW-v4",
        "name": "Dongfangshuo-Qwen3.8-27B-NSFW-v4 (Q3_K_M)",
        "quant": "Q3_K_M",
        "engine": "ollama",
        "recommended": True,
        "vram_hint": "推荐配置：12G~16G显存 + 16G内存（16G全显存高速长团首选）",
        "desc": "",
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
        "engine": "ollama",
        "recommended": True,
        "vram_hint": "推荐配置：24G显存，或 16G显存 + 32G内存（混合卸载）",
        "desc": "",
        "files": [
            {"path": "Dongfangshuo-Qwen3.8-27B-NSFW-v4-Q4_K_M.gguf", "size": 16547400160},
            {"path": "mmproj-model-bf16.gguf", "size": 931145888},
        ],
    },
    {
        "id": "v4_q5_k_m",
        "series": "Dongfangshuo-27B",
        "subfolder": "Dongfangshuo-27B",
        "series_title": "Dongfangshuo-27B",
        "repo_id": "dongfangshuo/Dongfangshuo-Qwen3.8-27B-NSFW-v4",
        "name": "Dongfangshuo-Qwen3.8-27B-NSFW-v4 (Q5_K_M)",
        "quant": "Q5_K_M",
        "engine": "ollama",
        "recommended": False,
        "vram_hint": "推荐配置：24G显存 + 32G内存",
        "desc": "",
        "files": [
            {"path": "Dongfangshuo-Qwen3.8-27B-NSFW-v4-Q5_K_M.gguf", "size": 19231099360},
            {"path": "mmproj-model-bf16.gguf", "size": 931145888},
        ],
    },
    {
        "id": "v4_q6_k",
        "series": "Dongfangshuo-27B",
        "subfolder": "Dongfangshuo-27B",
        "series_title": "Dongfangshuo-27B",
        "repo_id": "dongfangshuo/Dongfangshuo-Qwen3.8-27B-NSFW-v4",
        "name": "Dongfangshuo-Qwen3.8-27B-NSFW-v4 (Q6_K)",
        "quant": "Q6_K",
        "engine": "ollama",
        "recommended": False,
        "vram_hint": "推荐配置：24G~32G显存 + 32G内存",
        "desc": "",
        "files": [
            {"path": "Dongfangshuo-Qwen3.8-27B-NSFW-v4-Q6_K.gguf", "size": 22082529760},
            {"path": "mmproj-model-bf16.gguf", "size": 931145888},
        ],
    },
    {
        "id": "v4_q8_0",
        "series": "Dongfangshuo-27B",
        "subfolder": "Dongfangshuo-27B",
        "series_title": "Dongfangshuo-27B",
        "repo_id": "dongfangshuo/Dongfangshuo-Qwen3.8-27B-NSFW-v4",
        "name": "Dongfangshuo-Qwen3.8-27B-NSFW-v4 (Q8_0)",
        "quant": "Q8_0",
        "engine": "ollama",
        "recommended": False,
        "vram_hint": "推荐配置：32G+显存 + 32G内存",
        "desc": "",
        "files": [
            {"path": "Dongfangshuo-Qwen3.8-27B-NSFW-v4-Q8_0.gguf", "size": 28595763680},
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
        "engine": "ollama",
        "recommended": False,
        "vram_hint": "推荐配置：16G显存 + 16G内存",
        "desc": "",
        "files": [
            {"path": "Dongfangshuo-Qwen3.8-27B-NSFW-Novel-Q3_K_M.gguf", "size": 13301443008},
            {"path": "mmproj-Dongfangshuo-Qwen3.8-27B-NSFW-Novel-f16.gguf", "size": 931145888},
        ],
    },
    {
        "id": "novel_q4_k_m",
        "series": "Dongfangshuo-27B",
        "subfolder": "Dongfangshuo-27B",
        "series_title": "Dongfangshuo-27B",
        "repo_id": "dongfangshuo/Dongfangshuo-Qwen3.8-27B-NSFW-Novel",
        "name": "Dongfangshuo-Qwen3.8-27B-NSFW-Novel (Q4_K_M)",
        "quant": "Q4_K_M",
        "engine": "ollama",
        "recommended": False,
        "vram_hint": "推荐配置：16G~24G显存 + 16G内存",
        "desc": "",
        "files": [
            {"path": "Dongfangshuo-Qwen3.8-27B-NSFW-Novel-Q4_K_M.gguf", "size": 16547400128},
            {"path": "mmproj-Dongfangshuo-Qwen3.8-27B-NSFW-Novel-f16.gguf", "size": 931145888},
        ],
    },
    {
        "id": "novel_q5_k_m",
        "series": "Dongfangshuo-27B",
        "subfolder": "Dongfangshuo-27B",
        "series_title": "Dongfangshuo-27B",
        "repo_id": "dongfangshuo/Dongfangshuo-Qwen3.8-27B-NSFW-Novel",
        "name": "Dongfangshuo-Qwen3.8-27B-NSFW-Novel (Q5_K_M)",
        "quant": "Q5_K_M",
        "engine": "ollama",
        "recommended": False,
        "vram_hint": "推荐配置：24G显存 + 32G内存",
        "desc": "",
        "files": [
            {"path": "Dongfangshuo-Qwen3.8-27B-NSFW-Novel-Q5_K_M.gguf", "size": 19231099328},
            {"path": "mmproj-Dongfangshuo-Qwen3.8-27B-NSFW-Novel-f16.gguf", "size": 931145888},
        ],
    },
    {
        "id": "novel_q6_k",
        "series": "Dongfangshuo-27B",
        "subfolder": "Dongfangshuo-27B",
        "series_title": "Dongfangshuo-27B",
        "repo_id": "dongfangshuo/Dongfangshuo-Qwen3.8-27B-NSFW-Novel",
        "name": "Dongfangshuo-Qwen3.8-27B-NSFW-Novel (Q6_K)",
        "quant": "Q6_K",
        "engine": "ollama",
        "recommended": False,
        "vram_hint": "推荐配置：24G~32G显存 + 32G内存",
        "desc": "",
        "files": [
            {"path": "Dongfangshuo-Qwen3.8-27B-NSFW-Novel-Q6_K.gguf", "size": 22082529728},
            {"path": "mmproj-Dongfangshuo-Qwen3.8-27B-NSFW-Novel-f16.gguf", "size": 931145888},
        ],
    },
    {
        "id": "novel_q8_0",
        "series": "Dongfangshuo-27B",
        "subfolder": "Dongfangshuo-27B",
        "series_title": "Dongfangshuo-27B",
        "repo_id": "dongfangshuo/Dongfangshuo-Qwen3.8-27B-NSFW-Novel",
        "name": "Dongfangshuo-Qwen3.8-27B-NSFW-Novel (Q8_0)",
        "quant": "Q8_0",
        "engine": "ollama",
        "recommended": False,
        "vram_hint": "推荐配置：32G+显存 + 32G内存",
        "desc": "",
        "files": [
            {"path": "Dongfangshuo-Qwen3.8-27B-NSFW-Novel-Q8_0.gguf", "size": 28595763648},
            {"path": "mmproj-Dongfangshuo-Qwen3.8-27B-NSFW-Novel-f16.gguf", "size": 931145888},
        ],
    },
    {
        "id": "flash_iq3_xxs",
        "series": "Flash-Next",
        "subfolder": "Flash-Next",
        "series_title": "Flash-Next",
        "repo_id": "dongfangshuo/Dongfangshuo-Qwen3.8-Flash-Next-NSFW",
        "name": "Dongfangshuo-Qwen3.8-Flash-Next-NSFW (IQ3_XXS)",
        "quant": "IQ3_XXS",
        "engine": "strata",
        "recommended": True,
        "vram_hint": "推荐配置：RTX 20系+ · 8G+显存 · 32G+内存",
        "desc": "",
        "files": [
            {"path": "IQ3_XXS/Dongfangshuo-Qwen3.8-Flash-Next-NSFW-IQ3_XXS-00001-of-00002.gguf", "size": 40146300000},
            {"path": "IQ3_XXS/Dongfangshuo-Qwen3.8-Flash-Next-NSFW-IQ3_XXS-00002-of-00002.gguf", "size": 37043801280},
            {"path": "mmproj-Qwen3.8-Flash-Next-BF16.gguf", "size": 907543008},
        ],
    },
    {
        "id": "flash_iq2_xs",
        "series": "Flash-Next",
        "subfolder": "Flash-Next",
        "series_title": "Flash-Next",
        "repo_id": "dongfangshuo/Dongfangshuo-Qwen3.8-Flash-Next-NSFW",
        "name": "Dongfangshuo-Qwen3.8-Flash-Next-NSFW (IQ2_XS)",
        "quant": "IQ2_XS",
        "engine": "strata",
        "recommended": False,
        "vram_hint": "推荐配置：RTX 20系+ · 8G+显存 · 32G+内存",
        "desc": "",
        "files": [
            {"path": "IQ2_XS/Dongfangshuo-Qwen3.8-Flash-Next-NSFW-IQ2_XS-00001-of-00002.gguf", "size": 40236619264},
            {"path": "IQ2_XS/Dongfangshuo-Qwen3.8-Flash-Next-NSFW-IQ2_XS-00002-of-00002.gguf", "size": 29460720384},
            {"path": "mmproj-Qwen3.8-Flash-Next-BF16.gguf", "size": 907543008},
        ],
    },
    {
        "id": "flash_ud_q4_k_xl",
        "series": "Flash-Next",
        "subfolder": "Flash-Next",
        "series_title": "Flash-Next",
        "repo_id": "dongfangshuo/Dongfangshuo-Qwen3.8-Flash-Next-NSFW",
        "name": "Dongfangshuo-Qwen3.8-Flash-Next-NSFW (UD-Q4_K_XL)",
        "quant": "UD-Q4_K_XL",
        "engine": "strata",
        "recommended": False,
        "vram_hint": "推荐配置：RTX 20系+ · 16G+显存 · 64G+内存",
        "desc": "",
        "files": [
            {"path": "UD-Q4_K_XL/Dongfangshuo-Qwen3.8-Flash-Next-NSFW-UD-Q4_K_XL-00001-of-00004.gguf", "size": 10946624},
            {"path": "UD-Q4_K_XL/Dongfangshuo-Qwen3.8-Flash-Next-NSFW-UD-Q4_K_XL-00002-of-00004.gguf", "size": 49859583136},
            {"path": "UD-Q4_K_XL/Dongfangshuo-Qwen3.8-Flash-Next-NSFW-UD-Q4_K_XL-00003-of-00004.gguf", "size": 49376141504},
            {"path": "UD-Q4_K_XL/Dongfangshuo-Qwen3.8-Flash-Next-NSFW-UD-Q4_K_XL-00004-of-00004.gguf", "size": 12087983520},
            {"path": "mmproj-Qwen3.8-Flash-Next-BF16.gguf", "size": 907543008},
        ],
    },
]

GOLDEN_OLLAMA_TEMPLATE = '''{{- if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{- end }}
{{- range .Messages }}
{{- if eq .Role "system" }}<|im_start|>system
{{ .Content }}<|im_end|>
{{- else if eq .Role "user" }}<|im_start|>user
{{ .Content }}<|im_end|>
{{- else if eq .Role "assistant" }}<|im_start|>assistant
{{- if .Thinking }}
<think>
{{ .Thinking }}
</think>

{{ .Content }}<|im_end|>
{{- else }}
{{ .Content }}<|im_end|>
{{- end }}
{{- end }}
{{- end }}<|im_start|>assistant
'''


def _resolve_model_subfolder(repo_id: str = "", filename: str = "") -> str:
    """根据仓库或文件名自动归入 Dongfangshuo-27B 或 Flash-Next 子文件夹"""
    combined = f"{repo_id} {filename}".lower()
    if any(k in combined for k in ("flash-next", "flash_next", "qwen3.8-flash")):
        return "Flash-Next"
    return "Dongfangshuo-27B"


_BUNDLE_MODEL_DIRS_CACHE: Optional[Path] = None


def _run_hidden_mklink_junction(link_path: Path, target_path: Path) -> None:
    if os.name == "nt":
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link_path), str(target_path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
                startupinfo=si,
            )
        except Exception:
            pass
    else:
        try:
            os.symlink(str(target_path), str(link_path))
        except Exception:
            pass


def _ensure_bundle_model_dirs() -> Path:
    """确保整合包根目录下的 model/ 与 models/ 文件夹及两个标准系列子文件夹 (Dongfangshuo-27B / Flash-Next) 同时可用（纯 Python 目录创建，绝不在运行期调用 rmtree 或 cmd mklink 子进程以免触发资源管理器刷新抢焦点）"""
    global _BUNDLE_MODEL_DIRS_CACHE
    dir_model = _BUNDLE_ROOT / "model"
    dir_models = _BUNDLE_ROOT / "models"
    if _BUNDLE_MODEL_DIRS_CACHE is not None and _BUNDLE_MODEL_DIRS_CACHE.exists():
        return _BUNDLE_MODEL_DIRS_CACHE

    try:
        dir_models.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    try:
        if not dir_model.exists():
            dir_model.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    for sub in ("Dongfangshuo-27B", "Flash-Next"):
        try:
            (dir_models / sub).mkdir(parents=True, exist_ok=True)
            if dir_model.exists() and not dir_model.is_symlink():
                (dir_model / sub).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    try:
        if dir_model.exists() and dir_model.resolve() != dir_models.resolve():
            if any(dir_model.rglob("*.gguf")) and not any(dir_models.rglob("*.gguf")):
                _BUNDLE_MODEL_DIRS_CACHE = dir_model
                return dir_model
    except Exception:
        pass
    _BUNDLE_MODEL_DIRS_CACHE = dir_models if dir_models.exists() else dir_model
    return _BUNDLE_MODEL_DIRS_CACHE


def load_saved_custom_model_paths(extra_from_settings: Optional[List[str]] = None) -> List[str]:
    """读取用户通过『指定路径模型运行』挂载的外部 .gguf 文件或模型文件夹路径列表"""
    paths: List[str] = []
    if _CUSTOM_PATHS_FILE.exists():
        try:
            raw = json.loads(_CUSTOM_PATHS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                for p in raw:
                    s = str(p or "").strip()
                    if s and s not in paths:
                        paths.append(s)
        except Exception:
            pass
    if extra_from_settings and isinstance(extra_from_settings, list):
        for p in extra_from_settings:
            s = str(p or "").strip()
            if s and s not in paths:
                paths.append(s)
    return paths


def save_custom_model_paths(paths: List[str]) -> List[str]:
    cleaned: List[str] = []
    for p in paths:
        s = str(p or "").strip()
        if s and s not in cleaned:
            cleaned.append(s)
    try:
        _CUSTOM_PATHS_FILE.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(_CUSTOM_PATHS_FILE, cleaned, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return cleaned


def _find_strata_roots() -> List[Path]:
    """按优先级查找整合版内置 engine/strata、model、models 目录（及 Flash-Next 子目录）与环境变量 STRATA_DIR"""
    _ensure_bundle_model_dirs()
    roots: List[Path] = []
    env_strata = os.environ.get("STRATA_DIR", "").strip()
    candidates = [
        _BUNDLE_ROOT / "engine" / "strata",
        _BUNDLE_ROOT / "model" / "Flash-Next",
        _BUNDLE_ROOT / "models" / "Flash-Next",
        _BUNDLE_ROOT / "model",
        _BUNDLE_ROOT / "models",
    ]
    if env_strata:
        candidates.append(Path(env_strata))
    for candidate in candidates:
        if candidate.exists() and candidate not in roots:
            roots.append(candidate)
    return roots


def _resolve_real_ollama_dir(p: Path) -> Path:
    """解析 NTFS 目录联接 (Junction) / 符号链接为真实物理路径，避免 Ollama 0.40.5 (Go os.OpenRoot) 拒绝遍历联接目录报 bad manifest"""
    try:
        mf = p / "manifests"
        if mf.exists():
            return Path(os.path.realpath(mf)).parent
        return Path(os.path.realpath(p))
    except Exception:
        return p


def _find_ollama_models_dir() -> Optional[Path]:
    """按优先级查找整合版内置 models/ollama_models、model/ollama_models 或系统 OLLAMA_MODELS 目录"""
    env_ollama = os.environ.get("OLLAMA_MODELS", "").strip()
    candidates = [
        _BUNDLE_ROOT / "models" / "ollama_models",
        _BUNDLE_ROOT / "model" / "ollama_models",
        Path(env_ollama) if env_ollama else None,
    ]
    if os.environ.get("OLLAMA_NO_HOST_FALLBACK") != "1":
        candidates.append(Path.home() / ".ollama" / "models")
    for candidate in candidates:
        if candidate and candidate.exists():
            return _resolve_real_ollama_dir(candidate)
    default_bundled = _BUNDLE_ROOT / "models" / "ollama_models"
    try:
        default_bundled.mkdir(parents=True, exist_ok=True)
        return _resolve_real_ollama_dir(default_bundled)
    except Exception:
        return None


def _file_identity_key(p: Path) -> str:
    """用 (st_dev, st_ino, size) 去重硬链接与目录联接(Junction)，防止 model/ 与 models/ 重复显示同一模型"""
    try:
        st = p.stat()
        if getattr(st, "st_ino", 0) and getattr(st, "st_dev", 0):
            return f"ino:{st.st_dev}:{st.st_ino}:{st.st_size}"
        return f"path:{str(p.resolve()).lower()}:{st.st_size}"
    except Exception:
        return f"raw:{str(p).lower()}"


def _iter_gguf_in_path(target: Path, max_depth: int = 2) -> List[Path]:
    """在指定文件或目录（最多向下递归 max_depth 层，自动跳过 ollama_models 内部缓存）中收集所有 .gguf 文件"""
    found: List[Path] = []
    if not target.exists():
        return found
    if target.is_file():
        if target.suffix.lower() == ".gguf" and not target.name.endswith(".part"):
            found.append(target)
        return found

    skip_dirs = {"ollama_models", "blobs", "manifests", ".git", ".cache", "__pycache__", ".venv", "runtime", "static", "backups"}

    def _walk(cur_dir: Path, depth: int):
        try:
            entries = sorted(cur_dir.iterdir(), key=lambda x: x.name.lower())
        except Exception:
            return
        for entry in entries:
            try:
                if entry.is_file():
                    if entry.suffix.lower() == ".gguf" and not entry.name.endswith(".part"):
                        found.append(entry)
                elif entry.is_dir() and depth < max_depth and entry.name not in skip_dirs:
                    _walk(entry, depth + 1)
            except Exception:
                continue

    _walk(target, 0)
    return found


def _is_flash_next_gguf(gguf_path: Path) -> bool:
    """判断一个 .gguf 是否为 Qwen3.8-Flash-Next (MoE / Strata 引擎专用) 模型"""
    low_name = gguf_path.name.lower()
    low_parent = gguf_path.parent.name.lower()
    if any(k in low_name or k in low_parent for k in ("flash-next", "flash_next", "qwen3.8-flash", "qwen4exp", "gsq-rco")):
        return True
    if re.search(r"-00001-of-\d{5}\.gguf$", low_name):
        try:
            with open(gguf_path, "rb") as fh:
                head_bytes = fh.read(65536)
            if any(sig in head_bytes for sig in (b"qwen3next", b"qwen4exp", b"per_layer_token_embd")):
                return True
        except Exception:
            pass
    return False


def _clean_gguf_model_stem(gguf_path: Path) -> str:
    """剥离分片后缀 -00001-of-00002，返回干净的模型名称"""
    stem = re.sub(r"-\d{5}-of-\d{5}$", "", gguf_path.stem, flags=re.IGNORECASE)
    return stem.strip("-_") or gguf_path.stem


_HF_KNOWN_FILE_SIZES: Dict[str, int] = {
    Path(f["path"]).name.lower(): int(f["size"])
    for _preset in HF_PRESET_CATALOG
    for f in _preset.get("files", [])
    if isinstance(f, dict) and f.get("path") and f.get("size")
}


def _check_gguf_shards_complete(first_shard: Path) -> Tuple[bool, str]:
    """检查单文件或多分片 GGUF (-00001-of-0000N.gguf) 是否全部存在、无未完成后缀 (.part) 且字节完整"""
    if not first_shard or not first_shard.exists():
        return False, f"模型文件不存在 ({first_shard.name if first_shard else '未知'})"
    m = re.search(r"-(\d{5})-of-(\d{5})\.gguf$", first_shard.name, flags=re.IGNORECASE)
    if m:
        total = int(m.group(2))
        prefix = first_shard.name[: m.start()]
        shard_paths = [first_shard.with_name(f"{prefix}-{i:05d}-of-{total:05d}.gguf") for i in range(1, total + 1)]
    else:
        shard_paths = [first_shard]

    for idx_num, sp in enumerate(shard_paths, 1):
        for partial_ext in (".part", ".crdownload", ".aria2", ".downloading"):
            if sp.with_name(sp.name + partial_ext).exists():
                return False, f"第 {idx_num}/{len(shard_paths)} 分片仍在下载中 ({sp.name})"
        if not sp.is_file():
            return False, f"缺少第 {idx_num}/{len(shard_paths)} 分片 ({sp.name})"
        try:
            sz = sp.stat().st_size
        except OSError:
            return False, f"无法读取分片文件 ({sp.name})"
        if sz <= 0:
            return False, f"模型文件为空 0 字节 ({sp.name})"
        expected_sz = _HF_KNOWN_FILE_SIZES.get(sp.name.lower(), 0)
        if expected_sz > 0 and sz < int(expected_sz * 0.98):
            cur_gb = sz / (1024**3)
            exp_gb = expected_sz / (1024**3)
            return False, f"分片未下载完整: {sp.name} (当前 {cur_gb:.1f}GB / 需 {exp_gb:.1f}GB)"
        try:
            with open(sp, "rb") as fh:
                magic = fh.read(4)
            if magic != b"GGUF":
                return False, f"文件头损坏或并非有效 GGUF 模型 ({sp.name})"
        except OSError:
            pass
    return True, ""


def _find_best_mmproj_for_gguf(gguf_path: Path, is_flash_next: bool, all_mmprojs: List[Path]) -> str:
    """为指定 GGUF 自动匹配最佳视觉编码器 (mmproj*.gguf)"""
    candidates: List[Path] = []
    for search_dir in (
        gguf_path.parent,
        gguf_path.parent.parent if gguf_path.parent != _BUNDLE_ROOT else None,
        _BUNDLE_ROOT / "model",
        _BUNDLE_ROOT / "models",
        _BUNDLE_ROOT / "engine" / "strata" / "data" / "models",
    ):
        if search_dir and search_dir.exists() and search_dir.is_dir():
            try:
                for p in sorted(search_dir.glob("*mmproj*.gguf")):
                    if p not in candidates:
                        candidates.append(p)
            except Exception:
                pass
    for p in all_mmprojs:
        if p not in candidates:
            candidates.append(p)

    if not candidates:
        return ""

    if is_flash_next:
        low_model = gguf_path.name.lower()
        if "swift" in low_model:
            for c in candidates:
                if "swift" in c.name.lower() and "flash" in c.name.lower():
                    return str(c.absolute())
        for c in candidates:
            if any(k in c.name.lower() for k in ("flash-next", "flash_next", "qwen3.8-flash")):
                return str(c.absolute())
    else:
        if "novel" in gguf_path.name.lower():
            for c in candidates:
                if "novel" in c.name.lower():
                    return str(c.absolute())
        for c in candidates:
            if not any(k in c.name.lower() for k in ("flash-next", "flash_next", "qwen3.8-flash")):
                return str(c.absolute())

    return str(candidates[0].absolute())


def _locate_gguf_anywhere(filename_or_path: str, custom_paths: Optional[List[str]] = None) -> Optional[Path]:
    """当配置文件中的绝对路径失效（如整合包移动到其他电脑或盘符）时，自动在 model/、models/、内置目录与指定路径中寻找同名 GGUF"""
    if not filename_or_path:
        return None
    raw_p = Path(filename_or_path)
    if raw_p.exists() and raw_p.is_file():
        return raw_p
    target_name = raw_p.name.lower()
    search_roots = [
        _BUNDLE_ROOT / "model",
        _BUNDLE_ROOT / "models",
        _BUNDLE_ROOT / "engine" / "strata" / "data" / "models",
    ]
    for cp in load_saved_custom_model_paths(custom_paths):
        p = Path(cp)
        if p.exists():
            search_roots.append(p)
    for root in search_roots:
        for cand in _iter_gguf_in_path(root, max_depth=3):
            if cand.name.lower() == target_name:
                return cand
    return None


def _scan_local_strata_configs(custom_paths: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """自动扫描内置目录与 STRATA_DIR 下的 strata-*.json 配置文件，并自动重定位已迁移到 model/ 下的 GGUF 路径"""
    results: List[Dict[str, Any]] = []
    seen = set()
    for strata_root in _find_strata_roots():
        for cfg_path in sorted(strata_root.glob("strata-*.json")):
            if cfg_path.name.endswith(".shared-settings.json") or cfg_path.name.startswith("strata-auto-"):
                continue
            try:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                model_id = (cfg.get("model_name") or "").strip()
                if not model_id or model_id in seen:
                    continue
                args_list = cfg.get("args") or []
                native_gguf_str = ""
                if "--native" in args_list:
                    idx = args_list.index("--native")
                    if idx + 1 < len(args_list):
                        native_gguf_str = str(args_list[idx + 1])
                resolved_gguf = _locate_gguf_anywhere(native_gguf_str, custom_paths) if native_gguf_str else None
                if native_gguf_str and not resolved_gguf:
                    # 该配置文件指向的 GGUF 分片在当前电脑上不存在，跳过死配置避免误导用户
                    continue
                seen.add(model_id)
                cfg_port = safe_int(cfg.get("port"), 8080) or 8080
                port = _ACTIVE_STRATA_PORT if cfg_port == 8080 else cfg_port
                base_v1 = f"http://127.0.0.1:{port}/v1"
                gguf_abs = str(resolved_gguf.absolute()) if resolved_gguf else native_gguf_str
                shards_ok, shard_warn = _check_gguf_shards_complete(resolved_gguf) if resolved_gguf else (True, "")
                stem_alias = _clean_gguf_model_stem(resolved_gguf) if resolved_gguf else ""
                aliases = [stem_alias] if (stem_alias and stem_alias != model_id) else []
                display_name = f"{model_id} 【本地 · Flash-Next / Strata】"
                has_vision = bool(cfg.get("vision"))
                if not has_vision and resolved_gguf:
                    has_vision = bool(_find_best_mmproj_for_gguf(resolved_gguf, True, []))
                meta = {
                    "id": model_id,
                    "aliases": aliases,
                    "name": display_name,
                    "group": "Local",
                    "engine": "strata",
                    "base_url": base_v1,
                    "api_key": "local",
                    "upstream_model": model_id,
                    "strata_config": str(cfg_path),
                    "strata_port": port,
                    "gguf_path": gguf_abs,
                    "shards_complete": shards_ok,
                    "shard_warning": shard_warn,
                    "supports_vision": has_vision,
                    "billing_type": "local",
                    "short_price": "本地",
                    "detail_price": f"本地运行 (Strata {port})",
                    "description": f"本地 Strata 引擎 ({cfg_path.name})"
                }
                with _DISCOVERED_MODELS_LOCK:
                    DISCOVERED_LOCAL_MODELS[model_id] = meta
                    for al in aliases:
                        DISCOVERED_LOCAL_MODELS[al] = meta
                results.append(meta)
            except Exception:
                pass
    return results


def _scan_local_models_folder(custom_paths: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    自动扫描：
    1. <整合包根目录>/model/ 与 <整合包根目录>/models/（含子文件夹）下的所有 .gguf 模型（自动识别 Flash-Next 与 27B）
    2. 用户通过「指定路径模型运行」挂载的任意磁盘 .gguf 文件或模型文件夹
    3. 本地 Ollama manifests 离线注册表（自动校验 blob 完整性并与 model/ 下的 GGUF 智能合并去重）
    """
    _ensure_bundle_model_dirs()
    results: List[Dict[str, Any]] = []
    seen_ids = set()
    seen_file_keys = set()

    # 记录已注册在 Strata 配置中的 GGUF 文件 Identity，避免同一 Flash-Next 模型重复出现两次
    strata_configs = _scan_local_strata_configs(custom_paths)
    strata_by_file_key: Dict[str, Dict[str, Any]] = {}
    for sm in strata_configs:
        gp = sm.get("gguf_path")
        if gp and Path(gp).exists():
            strata_by_file_key[_file_identity_key(Path(gp))] = sm

    # 1. 预读取本地 Ollama manifests 离线列表（先尝试将 model/ 下标准 27B-v4-Q4_K_M 零拷贝硬链接至 ollama_models，再校验主模型 blob 是否真实存在）
    # 注意：整合包自身 model/ 与 models/ 文件夹中的模型优先级高于外部宿主机 ~/.ollama 历史残留模型，因此外部 manifests 延后追加
    _auto_link_discovered_v4_q4(custom_paths)
    ollama_manifest_by_from_name: Dict[str, Dict[str, Any]] = {}
    pending_ollama_manifests: List[Dict[str, Any]] = []
    seen_manifest_ids = set()
    ollama_models_dir = _find_ollama_models_dir()
    if ollama_models_dir:
        lib_dir = ollama_models_dir / "manifests" / "registry.ollama.ai" / "library"
        blobs_dir = ollama_models_dir / "blobs"
        if lib_dir.exists():
            for model_dir in sorted(lib_dir.iterdir()):
                if not model_dir.is_dir():
                    continue
                for tag_file in sorted(model_dir.iterdir()):
                    if not tag_file.is_file():
                        continue
                    mid = f"{model_dir.name}:{tag_file.name}"
                    if mid in seen_manifest_ids:
                        continue
                    from_gguf_name = ""
                    blob_ok = True
                    has_projector = False
                    try:
                        mf_data = json.loads(tag_file.read_text(encoding="utf-8"))
                        for layer in mf_data.get("layers", []):
                            mtype = str(layer.get("mediaType") or "")
                            if mtype == "application/vnd.ollama.image.model":
                                digest = str(layer.get("digest") or "")
                                from_path = str(layer.get("from") or "")
                                if from_path:
                                    from_gguf_name = Path(from_path).name.lower()
                                if digest.startswith("sha256:") and blobs_dir.exists():
                                    blob_file = blobs_dir / f"sha256-{digest[7:]}"
                                    if not blob_file.exists():
                                        blob_ok = False
                            elif mtype == "application/vnd.ollama.image.projector":
                                p_digest = str(layer.get("digest") or "")
                                if p_digest.startswith("sha256:") and blobs_dir.exists():
                                    if (blobs_dir / f"sha256-{p_digest[7:]}").exists():
                                        has_projector = True
                                else:
                                    has_projector = True
                    except Exception:
                        pass
                    if not blob_ok and not _locate_gguf_anywhere(from_gguf_name, custom_paths):
                        continue
                    seen_manifest_ids.add(mid)
                    meta = {
                        "id": mid,
                        "aliases": [],
                        "name": f"{mid} 【本地 · Ollama 11434】",
                        "group": "Local",
                        "engine": "ollama",
                        "base_url": "http://127.0.0.1:11434/v1",
                        "api_key": "local",
                        "upstream_model": mid,
                        "shards_complete": True,
                        "shard_warning": "",
                        "supports_vision": has_projector,
                        "billing_type": "local",
                        "short_price": "本地",
                        "detail_price": "本地运行 (Ollama 11434)",
                        "description": "本地 Ollama 引擎模型"
                    }
                    if from_gguf_name and from_gguf_name not in ollama_manifest_by_from_name:
                        ollama_manifest_by_from_name[from_gguf_name] = meta
                    with _DISCOVERED_MODELS_LOCK:
                        DISCOVERED_LOCAL_MODELS[mid] = meta
                    pending_ollama_manifests.append(meta)

    # 2. 最优先扫描 model/、models/ 与用户自定义挂载路径下的所有 .gguf 文件（即插即用，支持 Flash-Next 与 27B）
    scan_sources: List[Tuple[Path, str]] = [
        (_BUNDLE_ROOT / "model", "model文件夹"),
        (_BUNDLE_ROOT / "models", "model文件夹"),
    ]
    for cp in load_saved_custom_model_paths(custom_paths):
        p = Path(cp)
        if p.exists():
            scan_sources.append((p, f"指定路径 ({p.name})"))

    all_discovered_ggufs: List[Tuple[Path, str]] = []
    all_mmprojs: List[Path] = []
    for src_path, src_label in scan_sources:
        for gfile in _iter_gguf_in_path(src_path, max_depth=2):
            if "mmproj" in gfile.name.lower():
                if gfile not in all_mmprojs:
                    all_mmprojs.append(gfile)
            else:
                all_discovered_ggufs.append((gfile, src_label))

    for gguf_path, src_label in all_discovered_ggufs:
        fname_low = gguf_path.name.lower()
        # 多分片 GGUF 仅以第 1 分片 (-00001-of-0000N.gguf) 作为入口
        m_shard = re.search(r"-(\d{5})-of-(\d{5})\.gguf$", fname_low)
        if m_shard and int(m_shard.group(1)) != 1:
            continue

        fkey = _file_identity_key(gguf_path)
        if fkey in seen_file_keys:
            continue
        seen_file_keys.add(fkey)

        is_flash = _is_flash_next_gguf(gguf_path)
        best_mmproj = _find_best_mmproj_for_gguf(gguf_path, is_flash, all_mmprojs)
        clean_stem = _clean_gguf_model_stem(gguf_path)
        shards_ok, shard_warn = _check_gguf_shards_complete(gguf_path)

        if is_flash:
            # 若已有对应的 Strata 配置文件指向同一物理 GGUF，则直接更新其路径与显示标签并纳入返回结果，不重复生成第二条记录
            if fkey in strata_by_file_key:
                sm = strata_by_file_key[fkey]
                sm["gguf_path"] = str(gguf_path.absolute())
                sm["shards_complete"] = shards_ok
                sm["shard_warning"] = shard_warn
                if best_mmproj:
                    sm["mmproj_path"] = best_mmproj
                    sm["supports_vision"] = True
                sm["name"] = f"{sm['id']} 【本地 · {src_label} · Flash-Next】"
                sm["source_label"] = src_label
                with _DISCOVERED_MODELS_LOCK:
                    DISCOVERED_LOCAL_MODELS[sm["id"]] = sm
                    for al in sm.get("aliases", []):
                        DISCOVERED_LOCAL_MODELS[al] = sm
                if sm["id"] not in seen_ids:
                    seen_ids.add(sm["id"])
                    results.append(sm)
                continue

            mid = clean_stem
            if mid in seen_ids:
                continue
            seen_ids.add(mid)
            active_sp = _ACTIVE_STRATA_PORT
            meta = {
                "id": mid,
                "aliases": [f"{mid.lower()}:local"],
                "name": f"{clean_stem} 【本地 · {src_label} · Flash-Next】",
                "group": "Local",
                "engine": "strata",
                "base_url": f"http://127.0.0.1:{active_sp}/v1",
                "api_key": "local",
                "upstream_model": mid,
                "strata_port": active_sp,
                "gguf_path": str(gguf_path.absolute()),
                "mmproj_path": best_mmproj,
                "shards_complete": shards_ok,
                "shard_warning": shard_warn,
                "source_label": src_label,
                "supports_vision": bool(best_mmproj),
                "billing_type": "local",
                "short_price": "本地",
                "detail_price": f"本地运行 ({src_label} · Strata {active_sp})",
                "description": f"Flash-Next 模型 ({gguf_path.name})"
            }
            with _DISCOVERED_MODELS_LOCK:
                DISCOVERED_LOCAL_MODELS[mid] = meta
                DISCOVERED_LOCAL_MODELS[f"{mid.lower()}:local"] = meta
            results.append(meta)
        else:
            # 27B 或常规单文件 GGUF (Ollama 引擎)
            slug = re.sub(r"[^a-zA-Z0-9_\-\.]", "-", clean_stem).strip("-").lower()
            local_alias = f"{slug}:local"
            # 若该 GGUF 已在 ollama_models 中注册过（如 dongfangshuo-v4:q4），将文件路径绑定到该模型并优先排入结果列表
            if fname_low in ollama_manifest_by_from_name:
                existing_om = ollama_manifest_by_from_name[fname_low]
                existing_om["gguf_path"] = str(gguf_path.absolute())
                existing_om["shards_complete"] = shards_ok
                existing_om["shard_warning"] = shard_warn
                if best_mmproj:
                    existing_om["mmproj_path"] = best_mmproj
                    existing_om["supports_vision"] = True
                existing_om["source_label"] = src_label
                existing_om["name"] = f"{clean_stem} ({existing_om['id']}) 【本地 · {src_label}】"
                with _DISCOVERED_MODELS_LOCK:
                    for al in (local_alias, clean_stem):
                        if al not in existing_om.setdefault("aliases", []):
                            existing_om["aliases"].append(al)
                        DISCOVERED_LOCAL_MODELS[al] = existing_om
                if existing_om["id"] not in seen_ids:
                    seen_ids.add(existing_om["id"])
                    results.append(existing_om)
                continue

            mid = local_alias
            if mid in seen_ids:
                with _DISCOVERED_MODELS_LOCK:
                    if mid in DISCOVERED_LOCAL_MODELS:
                        DISCOVERED_LOCAL_MODELS[mid]["gguf_path"] = str(gguf_path.absolute())
                        DISCOVERED_LOCAL_MODELS[mid]["shards_complete"] = shards_ok
                        DISCOVERED_LOCAL_MODELS[mid]["shard_warning"] = shard_warn
                        if best_mmproj:
                            DISCOVERED_LOCAL_MODELS[mid]["mmproj_path"] = best_mmproj
                            DISCOVERED_LOCAL_MODELS[mid]["supports_vision"] = True
                continue
            seen_ids.add(mid)
            meta = {
                "id": mid,
                "aliases": [clean_stem],
                "name": f"{clean_stem} ({mid}) 【本地 · {src_label}】",
                "group": "Local",
                "engine": "ollama",
                "base_url": "http://127.0.0.1:11434/v1",
                "api_key": "local",
                "upstream_model": mid,
                "gguf_path": str(gguf_path.absolute()),
                "mmproj_path": best_mmproj,
                "shards_complete": shards_ok,
                "shard_warning": shard_warn,
                "source_label": src_label,
                "supports_vision": bool(best_mmproj),
                "billing_type": "local",
                "short_price": "本地",
                "detail_price": f"本地运行 ({src_label}/{gguf_path.name})",
                "description": f"{src_label} 直载模型 ({gguf_path.name})"
            }
            with _DISCOVERED_MODELS_LOCK:
                DISCOVERED_LOCAL_MODELS[mid] = meta
                DISCOVERED_LOCAL_MODELS[clean_stem] = meta
            results.append(meta)

    # 3. 追加其余未绑定整合包 model/ 目录 GGUF 的本机 Ollama manifests 模型
    for om in pending_ollama_manifests:
        if om["id"] not in seen_ids:
            seen_ids.add(om["id"])
            results.append(om)

    results.sort(key=lambda m: 0 if m.get("shards_complete", True) else 1)
    return results


def get_local_model_meta(
    model_id: str,
    custom_paths: Optional[List[str]] = None,
    allow_synthetic_ollama: bool = True,
) -> Optional[Dict[str, Any]]:
    if not model_id:
        return None
    m_clean = model_id.strip()
    low = m_clean.lower()
    for item in LOCAL_MODELS_CATALOG:
        if m_clean == item["id"] or m_clean in item.get("aliases", []):
            return item
    scanned = _scan_local_models_folder(custom_paths) + _scan_local_strata_configs(custom_paths)
    for item in scanned:
        if m_clean == item["id"] or m_clean in item.get("aliases", []):
            return item
    with _DISCOVERED_MODELS_LOCK:
        discovered_snapshot = list(DISCOVERED_LOCAL_MODELS.values())
        if m_clean in DISCOVERED_LOCAL_MODELS:
            return DISCOVERED_LOCAL_MODELS[m_clean]

    # 不区分大小写精确匹配 ID 与 aliases
    for item in LOCAL_MODELS_CATALOG + scanned + discovered_snapshot:
        item_id_low = str(item.get("id") or "").lower()
        alias_lows = [str(a).lower() for a in (item.get("aliases") or [])]
        if low == item_id_low or low in alias_lows:
            return item

    if any(k in low for k in ("flash-next", "flash_next", "iq3_xxs", "iq2_xs", "ud-q4_k_xl")):
        for item in scanned:
            if item.get("engine") == "strata":
                return item
    if any(tag in low for tag in (":q3", ":q4", ":q5", ":q6", ":q8", ":latest", ":fp16", ":local")):
        for item in discovered_snapshot + scanned:
            if item.get("engine") == "ollama" and str(item.get("id") or "").lower() == low:
                return item
        if allow_synthetic_ollama:
            return {
                "id": m_clean,
                "name": f"{m_clean} 【本地 · Ollama 11434】",
                "group": "Local",
                "engine": "ollama",
                "base_url": "http://127.0.0.1:11434/v1",
                "api_key": "local",
                "upstream_model": m_clean,
                "supports_vision": False,
                "billing_type": "local",
                "short_price": "本地",
                "detail_price": "本地运行 (Ollama 11434)",
                "description": "本地 Ollama 模型"
            }
    return None

def get_installed_local_model_ids(custom_paths: Optional[List[str]] = None) -> List[str]:
    """返回当前磁盘上真实已就绪的本地模型 ID 列表（零网络探测，毫秒级返回）"""
    scanned = _scan_local_models_folder(custom_paths) + _scan_local_strata_configs(custom_paths)
    out: List[str] = []
    for item in scanned:
        mid = str(item.get("id") or "").strip()
        if mid and mid not in out:
            out.append(mid)
    return out


def _find_system_ollama_exe() -> Optional[Path]:
    """优先查找整合包内置 engine/ollama/ollama.exe，其次查找系统已安装的 Ollama"""
    for cand_rel in ("ollama.exe", "ollama"):
        bundled = _BUNDLE_ROOT / "engine" / "ollama" / cand_rel
        if bundled.exists():
            return bundled
    if os.environ.get("OLLAMA_NO_HOST_FALLBACK") == "1":
        return None
    import shutil as _shutil
    which_path = _shutil.which("ollama")
    if which_path:
        p = Path(which_path)
        if p.exists():
            return p
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        candidate = Path(local_app_data) / "Programs" / "Ollama" / "ollama.exe"
        if candidate.exists():
            return candidate
    return None


def _find_bundled_llama_server_exe() -> Optional[Path]:
    """查找内置 engine/llama/llama-server(.exe) 或系统 PATH 中的 llama-server（用于无 Ollama 环境如 Linux 云服务器直跑 27B GGUF）"""
    for cand in (
        _BUNDLE_ROOT / "engine" / "llama" / ("llama-server.exe" if os.name == "nt" else "llama-server"),
        _BUNDLE_ROOT / "engine" / "llama" / "llama-server",
        _BUNDLE_ROOT / "engine" / "llama" / "llama-server.exe",
    ):
        if cand.exists():
            if os.name != "nt":
                try:
                    os.chmod(cand, 0o755)
                except Exception:
                    pass
            return cand
    import shutil as _shutil
    which_ls = _shutil.which("llama-server")
    if which_ls and Path(which_ls).exists():
        return Path(which_ls)
    return None


async def _try_auto_wake_ollama() -> bool:
    """当主动调用本地 Ollama 模型但服务未启动时，后台无窗口拉起 ollama serve"""
    ollama_exe = _find_system_ollama_exe()
    if not ollama_exe:
        return False
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
    si = None
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
        si.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
    env = os.environ.copy()
    models_dir = _find_ollama_models_dir()
    if models_dir:
        env["OLLAMA_MODELS"] = str(models_dir)
    env.setdefault("OLLAMA_HOST", "127.0.0.1:11434")
    env.setdefault("OLLAMA_FLASH_ATTENTION", "1")
    env.setdefault("OLLAMA_KV_CACHE_TYPE", "q8_0")
    forced_vram = os.environ.get("FORCE_GPU_VRAM_MIB", "").strip()
    if forced_vram.isdigit() and int(forced_vram) > 0:
        phys_vram = _detect_physical_gpu_vram_mib()
        if phys_vram > int(forced_vram) + 512:
            env.setdefault("LLAMA_ARG_FIT_TARGET", str(max(1024, phys_vram - int(forced_vram) + 1200)))
    try:
        subprocess.Popen(
            [str(ollama_exe), "serve"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
            startupinfo=si
        )
    except Exception:
        return False

    async with httpx.AsyncClient(trust_env=False, timeout=1.5) as client:
        for _ in range(12):
            await asyncio.sleep(0.5)
            try:
                r = await client.get("http://127.0.0.1:11434/api/tags")
                if r.status_code == 200:
                    return True
            except Exception:
                pass
    return False


async def discover_local_models(settings: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """支持【自动探测本机端口 + model/与models/文件夹即插即用 + 指定外部路径运行】与【手动填写本地接口】"""
    settings = settings or {}
    custom_paths = settings.get("custom_model_paths") if isinstance(settings.get("custom_model_paths"), list) else None
    if custom_paths:
        # 仅合并新增路径，绝不在只读扫描时用设置里的（可能为空的）列表覆盖已挂载路径
        saved_paths = load_saved_custom_model_paths()
        merged_paths = load_saved_custom_model_paths(custom_paths)
        if merged_paths != saved_paths:
            save_custom_model_paths(merged_paths)
    local_mode = (settings.get("local_mode") or "auto").strip().lower()
    manual_url = (settings.get("local_base_url") or "").strip().rstrip("/")
    if manual_url and not manual_url.endswith("/v1") and ":11434" in manual_url:
        manual_url = manual_url + "/v1"
    manual_model = (settings.get("local_model") or "").strip()

    # 先执行离线扫描，以便在线端口探测返回时能继承友好的显示名称与 gguf_path 元信息
    offline_strata = _scan_local_strata_configs(custom_paths) if local_mode == "auto" else []
    offline_folder = _scan_local_models_folder(custom_paths) if local_mode == "auto" else []
    offline_map: Dict[str, Dict[str, Any]] = {}
    for item in offline_strata + offline_folder:
        offline_map[item["id"]] = item
        for al in item.get("aliases", []):
            offline_map[al] = item

    probes = []
    if local_mode == "manual":
        if manual_url:
            eng_type = "ollama" if ":11434" in manual_url else "openai_local"
            root_u = manual_url[:-3] if manual_url.endswith("/v1") else manual_url
            if eng_type == "ollama":
                probes.append(("ollama", manual_url, f"{root_u}/api/tags", f"Manual ({root_u})"))
            probes.append((eng_type, manual_url, f"{manual_url}/models", f"Manual ({manual_url})"))
    elif local_mode == "auto":
        strata_probe_ports = [8080] if _ACTIVE_STRATA_PORT == 8080 else [_ACTIVE_STRATA_PORT, 8080]
        probes = [
            ("strata", f"http://127.0.0.1:{sp}/v1", f"http://127.0.0.1:{sp}/v1/models", f"Strata {sp}")
            for sp in strata_probe_ports
        ]
        if (_BUNDLE_ROOT / "engine" / "ollama" / "ollama.exe").exists() or _find_bundled_llama_server_exe() is not None or os.environ.get("OLLAMA_NO_HOST_FALLBACK") != "1":
            probes.append(("ollama", "http://127.0.0.1:11434/v1", "http://127.0.0.1:11434/api/tags", "Ollama 11434"))
            probes.append(("ollama", "http://127.0.0.1:11434/v1", "http://127.0.0.1:11434/v1/models", "LlamaServer 11434"))
        if os.environ.get("OLLAMA_NO_HOST_FALLBACK") != "1":
            probes.append(("openai_local", "http://127.0.0.1:1234/v1", "http://127.0.0.1:1234/v1/models", "LM Studio 1234"))

    found: List[Dict[str, Any]] = []
    seen_ids = set()

    # 0. 最优先放入整合包自身 model/ (models/) 文件夹与用户显式挂载路径下的模型，确保整合包开箱默认选中自带模型
    if local_mode == "auto":
        for folder_meta in offline_folder:
            mid = folder_meta["id"]
            if mid not in seen_ids:
                seen_ids.add(mid)
                for al in folder_meta.get("aliases", []):
                    seen_ids.add(al)
                found.append(folder_meta)

    if local_mode == "manual" and manual_model and manual_url:
        eng_type = "ollama" if ":11434" in manual_url else "openai_local"
        meta = {
            "id": manual_model,
            "name": f"{manual_model} 【本地 · 手动指定】",
            "group": "Local",
            "engine": eng_type,
            "base_url": manual_url,
            "api_key": "local",
            "upstream_model": manual_model,
            "supports_vision": True,
            "billing_type": "local",
            "short_price": "本地",
            "detail_price": f"本地运行 ({manual_url})",
            "description": f"手动配置的本地模型 ({manual_url})"
        }
        with _DISCOVERED_MODELS_LOCK:
            DISCOVERED_LOCAL_MODELS[manual_model] = meta
        found.append(meta)
        seen_ids.add(manual_model)

    async def _run_probes():
        async with httpx.AsyncClient(trust_env=False, timeout=1.2) as client:
            tasks = [client.get(p[2]) for p in probes]
            return await asyncio.gather(*tasks, return_exceptions=True)

    # 1. 优先探测正在运行的本地端口（Strata 8080 / Ollama 11434 / LM Studio 1234），将活跃模型排在第一位
    # 注意：打开网页自动扫描模型列表 (GET /api/models) 时绝不后台拉起 ollama serve 进程，避免网页打开几秒后被后台进程抢夺窗口焦点导致最小化；
    # 离线清单已能完整列出本地模型，真正发送消息时由 ensure_local_engine_ready 按需静默唤醒。
    if probes:
        results = await _run_probes()

        for (engine, base_v1, _, label), resp in zip(probes, results):
            if isinstance(resp, Exception) or resp.status_code != 200:
                continue
            try:
                data = resp.json()
                if "models" in data and isinstance(data["models"], list):
                    items = [m.get("name") for m in data.get("models", []) if m.get("name")]
                else:
                    items = [m.get("id") for m in data.get("data", []) if m.get("id")]
                for mid in items:
                    if mid in seen_ids:
                        continue
                    seen_ids.add(mid)
                    if mid in offline_map:
                        rich_meta = dict(offline_map[mid])
                        for al in rich_meta.get("aliases", []):
                            seen_ids.add(al)
                        seen_ids.add(rich_meta["id"])
                        with _DISCOVERED_MODELS_LOCK:
                            DISCOVERED_LOCAL_MODELS[mid] = rich_meta
                        found.append(rich_meta)
                    else:
                        meta = {
                            "id": mid,
                            "name": f"{mid} 【本地 · {label}】",
                            "group": "Local",
                            "engine": engine,
                            "base_url": base_v1,
                            "api_key": "local",
                            "upstream_model": mid,
                            "supports_vision": True,
                            "billing_type": "local",
                            "short_price": "本地",
                            "detail_price": f"本地运行 ({label})",
                            "description": f"本地模型 ({base_v1})"
                        }
                        with _DISCOVERED_MODELS_LOCK:
                            DISCOVERED_LOCAL_MODELS[mid] = meta
                        found.append(meta)
            except Exception:
                pass

    # 2. 补充离线扫描到的 Strata 配置文件（folder 模型已在步骤 0 最优先置入）
    if local_mode == "auto":
        for strata_meta in offline_strata:
            mid = strata_meta["id"]
            if mid not in seen_ids:
                seen_ids.add(mid)
                for al in strata_meta.get("aliases", []):
                    seen_ids.add(al)
                found.append(strata_meta)
    return found

def normalize_api_endpoint_and_protocol(
    raw_base_url: str,
    raw_api_key: str,
    raw_protocol: str = "auto"
) -> Dict[str, Any]:
    """智能识别或按指定协议归一化 API Base URL 与请求头（支持 auto / openai / gemini / claude / ollama）"""
    url = (raw_base_url or "").strip().rstrip("/")
    key = (raw_api_key or "").strip()
    proto = (raw_protocol or "auto").strip().lower()
    if proto not in ("auto", "openai", "gemini", "claude", "ollama"):
        proto = "auto"

    # 若用户误粘贴了完整接口后缀，自动剥离
    for suffix in (
        "/chat/completions",
        "/completions",
        "/messages",
        "/models",
        "/api/tags",
        "/api/chat"
    ):
        if url.lower().endswith(suffix):
            url = url[:-len(suffix)].rstrip("/")

    # 自动识别协议
    effective_proto = proto
    url_lower = url.lower()
    if effective_proto == "auto":
        if "generativelanguage.googleapis.com" in url_lower or (not url and key.startswith("AIza")):
            effective_proto = "gemini"
        elif "anthropic.com" in url_lower or (not url and key.startswith("sk-ant-")):
            effective_proto = "claude"
        elif ":11434" in url_lower:
            effective_proto = "ollama"
        else:
            effective_proto = "openai"

    # 根据协议归一化 Base URL
    if effective_proto == "gemini":
        if not url:
            norm_url = "https://generativelanguage.googleapis.com/v1beta/openai"
        elif url_lower.endswith("/v1beta/openai") or url_lower.endswith("/v1"):
            norm_url = url
        elif url_lower.endswith("/v1beta"):
            norm_url = f"{url}/openai"
        elif "generativelanguage.googleapis.com" in url_lower:
            norm_url = f"{url}/v1beta/openai"
        else:
            norm_url = f"{url}/v1beta/openai" if not re.search(r"/v\d+", url_lower) else url
    elif effective_proto == "claude":
        if not url:
            norm_url = "https://api.anthropic.com/v1"
        elif not re.search(r"/v\d+$", url_lower):
            norm_url = f"{url}/v1"
        else:
            norm_url = url
    elif effective_proto == "ollama":
        if not url:
            norm_url = "http://127.0.0.1:11434/v1"
        elif not url_lower.endswith("/v1"):
            norm_url = f"{url}/v1"
        else:
            norm_url = url
    else:
        # OpenAI 兼容协议：若填了域名但末尾未带 /v1、/v3、/v4 等版本路径，自动补全 /v1
        if url and not re.search(r"/v\d+(?:beta(?:/openai)?)?$", url_lower):
            norm_url = f"{url}/v1"
        else:
            norm_url = url

    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
        if effective_proto == "gemini":
            headers["x-goog-api-key"] = key
        elif effective_proto == "claude":
            headers["x-api-key"] = key
            headers["anthropic-version"] = "2023-06-01"

    return {
        "configured_protocol": proto,
        "protocol": effective_proto,
        "base_url": norm_url,
        "raw_clean_url": url,
        "api_key": key,
        "headers": headers
    }


def _is_local_host_url(url: str) -> bool:
    """按解析后的主机名判断是否为本机/局域网地址（localhost、回环、私有网段），避免 URL 中任意位置含 '10.' 被误判"""
    try:
        raw = str(url or "").strip()
        if not raw:
            return False
        if "://" not in raw:
            raw = "http://" + raw
        host = (urlparse(raw).hostname or "").strip().lower()
        if not host:
            return False
        if host == "localhost" or host.endswith(".localhost"):
            return True
        try:
            ip = ipaddress.ip_address(host)
            return bool(ip.is_loopback or ip.is_private or ip.is_link_local)
        except ValueError:
            return False
    except Exception:
        return False


def _infer_cloud_vision_support(model_id: str) -> bool:
    """对明确已知仅支持纯文本的主流云端模型返回 False，防止挂载 PNG 角色卡时自动塞入 image_url 触发 400"""
    low = str(model_id or "").strip().lower()
    if not low:
        return True
    if any(v in low for v in ("vl", "vision", "omni", "gemini", "claude-3", "claude-4", "claude-sonnet", "claude-opus", "gpt-4o", "gpt-4.1", "gpt-5", "pixtral", "grok-2-vision")):
        return True
    text_only_keywords = (
        "deepseek-chat",
        "deepseek-reasoner",
        "deepseek-v3",
        "deepseek-r1",
        "deepseek-coder",
        "qwq-",
        "qwq:",
        "qwen-turbo",
        "qwen-plus",
        "qwen-max",
        "glm-4-air",
        "glm-4-flash",
    )
    if any(k in low for k in text_only_keywords):
        return False
    return True


def _is_loopback_only_url(url: str) -> bool:
    try:
        raw = str(url or "").strip()
        if not raw:
            return False
        if "://" not in raw:
            raw = "http://" + raw
        host = (urlparse(raw).hostname or "").strip().lower()
        if host in ("localhost", "127.0.0.1", "::1"):
            return True
        try:
            return bool(ipaddress.ip_address(host).is_loopback)
        except ValueError:
            return False
    except Exception:
        return False


def resolve_model_endpoint(model_id: str, settings: Dict[str, Any]) -> Dict[str, Any]:
    settings = settings or {}
    custom_paths = settings.get("custom_model_paths") if isinstance(settings.get("custom_model_paths"), list) else None
    local_mode = (settings.get("local_mode") or "auto").strip().lower()
    manual_local_model = (settings.get("local_model") or "").strip()
    manual_local_url = (settings.get("local_base_url") or "").strip().rstrip("/")
    cfg_base_url = (settings.get("base_url") or "").strip()

    # 1. 手动指定本地地址模式优先，避免局域网远程 Ollama 的 :latest / :q4 标签被劫持回 127.0.0.1
    if local_mode == "manual" and manual_local_url and (model_id == manual_local_model or not settings.get("api_key")):
        norm_local = normalize_api_endpoint_and_protocol(
            manual_local_url,
            "local",
            "ollama" if ":11434" in manual_local_url else "openai"
        )
        return {
            "is_local": _is_loopback_only_url(norm_local["base_url"]),
            "protocol": norm_local["protocol"],
            "engine": "ollama" if ":11434" in manual_local_url else "openai_local",
            "base_url": norm_local["base_url"],
            "api_key": "local",
            "headers": norm_local["headers"],
            "upstream_model": model_id,
            "supports_vision": _infer_cloud_vision_support(model_id),
            "proxy": None
        }

    # 2. 查询真实本机已安装的本地模型（若用户已配置非本机的远程 base_url，则禁止凭 :latest 后缀凭空伪造本机 11434 端点）
    allow_synthetic = (not cfg_base_url) or _is_loopback_only_url(cfg_base_url)
    local_meta = get_local_model_meta(model_id, custom_paths=custom_paths, allow_synthetic_ollama=allow_synthetic)
    if local_meta:
        ak = local_meta.get("api_key") or "local"
        if local_meta.get("engine") == "strata":
            cfg_sp = safe_int(local_meta.get("strata_port"), 8080) or 8080
            eff_sp = _ACTIVE_STRATA_PORT if (not local_meta.get("strata_config") or cfg_sp in (8080, _ACTIVE_STRATA_PORT)) else cfg_sp
            ep_url = f"http://127.0.0.1:{eff_sp}/v1"
        elif local_meta.get("engine") == "ollama" and _ACTIVE_LLAMA_PORT != 11434:
            ep_url = f"http://127.0.0.1:{_ACTIVE_LLAMA_PORT}/v1"
        else:
            ep_url = local_meta.get("base_url", "http://127.0.0.1:11434/v1").rstrip("/")
        return {
            "is_local": _is_loopback_only_url(ep_url),
            "protocol": "ollama" if local_meta.get("engine") == "ollama" else "openai",
            "engine": local_meta.get("engine", "ollama"),
            "base_url": ep_url,
            "api_key": ak,
            "headers": {"Authorization": f"Bearer {ak}", "Content-Type": "application/json"},
            "upstream_model": local_meta.get("upstream_model", model_id),
            "gguf_path": local_meta.get("gguf_path", ""),
            "supports_vision": bool(local_meta.get("supports_vision", False)),
            "proxy": None
        }

    norm = normalize_api_endpoint_and_protocol(
        cfg_base_url,
        settings.get("api_key") or "",
        settings.get("api_protocol") or "auto"
    )
    base_url = norm["base_url"]
    raw_key = norm["api_key"]
    proto = norm["protocol"]
    is_lan_or_local = _is_local_host_url(base_url)
    is_loopback_engine = _is_loopback_only_url(base_url)
    effective_key = raw_key if raw_key else ("local" if (proto == "ollama" or is_lan_or_local) else "")
    headers = dict(norm["headers"])
    if effective_key and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {effective_key}"

    upstream_model = model_id
    if proto == "gemini" and upstream_model.startswith("models/"):
        upstream_model = upstream_model[len("models/"):]

    return {
        "is_local": is_loopback_engine,
        "protocol": proto,
        "engine": "ollama" if (proto == "ollama" or ":11434" in base_url) else "cloud",
        "base_url": base_url,
        "api_key": effective_key,
        "headers": headers,
        "upstream_model": upstream_model,
        "supports_vision": _infer_cloud_vision_support(upstream_model),
        "proxy": (settings.get("proxy") if settings.get("use_proxy") else None) if not is_lan_or_local else None
    }


def sanitize_messages_for_model(api_messages: List[Dict[str, Any]], supports_vision: bool) -> List[Dict[str, Any]]:
    """当所选模型为纯文本引擎时，自动剥离历史与当前消息中的 image_url 块，防止报 400 错误"""
    if supports_vision:
        return api_messages
    cleaned: List[Dict[str, Any]] = []
    for m in api_messages:
        content = m.get("content")
        if isinstance(content, list):
            text_parts = []
            img_cnt = 0
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text" and part.get("text"):
                        text_parts.append(part["text"])
                    elif part.get("type") == "image_url":
                        img_cnt += 1
            merged_text = "\n".join(text_parts).strip()
            if img_cnt > 0 and not merged_text:
                merged_text = f"[玩家附带了 {img_cnt} 张参考图]"
            cleaned.append({"role": m.get("role", "user"), "content": merged_text})
        else:
            cleaned.append(m)
    return cleaned

_CACHED_GPU_VRAM_MIB: Optional[int] = None


def _detect_physical_gpu_vram_mib() -> int:
    """检测本机物理独立显卡真实总显存 (MiB)；无 NVIDIA 卡时兼容 Linux DRM / Windows 注册表检测，失败时保守回退 8192 MiB 防止 OOM"""
    global _CACHED_GPU_VRAM_MIB
    if _CACHED_GPU_VRAM_MIB is not None:
        return _CACHED_GPU_VRAM_MIB
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
    si = None
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            encoding="utf-8",
            errors="ignore",
            stdin=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
            startupinfo=si,
            timeout=3.0,
        )
        vals = [int(x.strip()) for x in out.splitlines() if x.strip().isdigit()]
        if vals:
            _CACHED_GPU_VRAM_MIB = max(vals)
            return _CACHED_GPU_VRAM_MIB
    except Exception:
        pass

    # Linux AMD / Intel 显卡 sysfs 显存读取（零子进程开销）
    if os.name != "nt":
        try:
            drm_vals: List[int] = []
            for p in Path("/sys/class/drm").glob("card*/device/mem_info_vram_total"):
                raw_b = p.read_text(encoding="utf-8", errors="ignore").strip()
                if raw_b.isdigit() and int(raw_b) > 0:
                    drm_vals.append(int(raw_b) // (1024 * 1024))
            if drm_vals:
                _CACHED_GPU_VRAM_MIB = max(drm_vals)
                return _CACHED_GPU_VRAM_MIB
        except Exception:
            pass
    else:
        # Windows AMD / Intel / 独显 64 位显存注册表读取
        try:
            import winreg
            reg_vals: List[int] = []
            cls_path = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, cls_path) as root_key:
                idx = 0
                while True:
                    try:
                        sub_name = winreg.EnumKey(root_key, idx)
                        idx += 1
                    except OSError:
                        break
                    if not sub_name.startswith("0"):
                        continue
                    try:
                        with winreg.OpenKey(root_key, sub_name) as sk:
                            val, _ = winreg.QueryValueEx(sk, "HardwareInformation.qwMemorySize")
                            if isinstance(val, bytes) and len(val) == 8:
                                b_sz = int.from_bytes(val, "little")
                            elif isinstance(val, int):
                                b_sz = val
                            else:
                                b_sz = 0
                            if b_sz >= 512 * 1024 * 1024:
                                reg_vals.append(b_sz // (1024 * 1024))
                    except OSError:
                        continue
            if reg_vals:
                _CACHED_GPU_VRAM_MIB = max(reg_vals)
                return _CACHED_GPU_VRAM_MIB
        except Exception:
            pass

    _CACHED_GPU_VRAM_MIB = 8192
    return _CACHED_GPU_VRAM_MIB


def _detect_physical_free_gpu_vram_mib() -> int:
    """检测本机物理独立显卡当前空闲显存 (MiB)"""
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
    si = None
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            encoding="utf-8",
            errors="ignore",
            stdin=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
            startupinfo=si,
            timeout=3.0,
        )
        vals = [int(x.strip()) for x in out.splitlines() if x.strip().isdigit()]
        if vals:
            return max(vals)
    except Exception:
        pass
    return _detect_physical_gpu_vram_mib()


def detect_gpu_vram_mib() -> int:
    """自动检测本机最大独立显卡显存容量 (MiB)，用于对 8GB/12GB/16GB/24GB+ 显卡自动适配上下文与 KV 缓存精度"""
    forced_vram = os.environ.get("FORCE_GPU_VRAM_MIB", "").strip()
    if forced_vram.isdigit() and int(forced_vram) > 0:
        return int(forced_vram)
    return _detect_physical_gpu_vram_mib()


def _detect_system_ram_gib() -> int:
    """自动检测物理内存容量 (GiB)，用于动态规划 64K~100K 长上下文窗口与专家常驻预算"""
    sys_ram_gib = safe_int(os.environ.get("FORCE_SYSTEM_RAM_GIB"), 0)
    if sys_ram_gib > 0:
        return sys_ram_gib
    try:
        if os.name == "nt":
            import ctypes

            class _MEMSTAT(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            ms = _MEMSTAT()
            ms.dwLength = ctypes.sizeof(_MEMSTAT)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
                return round(ms.ullTotalPhys / (1024**3))
        elif Path("/proc/meminfo").exists():
            for line in Path("/proc/meminfo").read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / (1024**2))
    except Exception:
        pass
    return 0


def get_optimal_ollama_num_ctx(*args, **kwargs) -> int:
    """根据显卡显存与系统内存动态计算 Ollama / llama-server 27B 模型的安全 num_ctx 窗口（支持 96K/100K 超长跑团上下文）。
    兼容三种调用签名：
      - get_optimal_ollama_num_ctx()
      - get_optimal_ollama_num_ctx(requested_k, gguf_path="")
      - get_optimal_ollama_num_ctx(model_id, settings_dict, min_ctx=8192)
    """
    vram_mib = detect_gpu_vram_mib()
    sys_ram_gib = _detect_system_ram_gib()
    if vram_mib >= 22000 or sys_ram_gib >= 46:
        hw_cap = 102400
    elif sys_ram_gib >= 28 or vram_mib >= 15000:
        hw_cap = 98304
    elif sys_ram_gib >= 20 or vram_mib >= 11000:
        hw_cap = 65536
    else:
        hw_cap = 32768

    requested_tokens = 98304
    if args:
        first = args[0]
        if isinstance(first, (int, float)) and not isinstance(first, bool) and first > 0:
            val = int(first)
            requested_tokens = val * 1024 if val <= 512 else val
        elif len(args) >= 2 and isinstance(args[1], dict):
            req_k = safe_int(args[1].get("max_context_k"), 96)
            if req_k > 0:
                requested_tokens = req_k * 1024 if req_k <= 512 else req_k
    if "max_context_k" in kwargs and kwargs["max_context_k"] is not None:
        req_k = safe_int(kwargs["max_context_k"], 96)
        if req_k > 0:
            requested_tokens = req_k * 1024 if req_k <= 512 else req_k

    min_ctx = max(2048, safe_int(kwargs.get("min_ctx"), 8192))
    return max(min_ctx, min(requested_tokens, hw_cap))


def _build_v4_q4_prm_blob() -> Tuple[str, bytes]:
    target_num_ctx = get_optimal_ollama_num_ctx()
    prm_bytes = (
        f'{{"num_ctx":{target_num_ctx},"num_predict":4096,"temperature":0.68,"top_p":0.9,'
        f'"top_k":40,"min_p":0.06,"repeat_last_n":1024,"repeat_penalty":1.03,'
        f'"presence_penalty":0.10,"frequency_penalty":0.0,'
        f'"stop":["<|im_end|>","<|im_start|>","<|endoftext|>"]}}'
    ).encode("utf-8")
    prm_hash = "sha256-" + hashlib.sha256(prm_bytes).hexdigest()
    return prm_hash, prm_bytes


def _adapt_existing_v4_q4_manifest_for_vram(ollama_models_dir: Optional[Path]) -> bool:
    """若 ollama_models 目录中已存在 dongfangshuo-v4/q4 manifest，自动将其 params 层适配到当前显卡显存对应的安全 num_ctx"""
    if not ollama_models_dir or not ollama_models_dir.exists():
        return False
    try:
        mf_path = ollama_models_dir / "manifests" / "registry.ollama.ai" / "library" / "dongfangshuo-v4" / "q4"
        if not mf_path.exists():
            return False
        blobs_dir = ollama_models_dir / "blobs"
        blobs_dir.mkdir(parents=True, exist_ok=True)
        prm_hash, prm_bytes = _build_v4_q4_prm_blob()
        prm_blob_path = blobs_dir / prm_hash
        if not prm_blob_path.exists():
            prm_blob_path.write_bytes(prm_bytes)
        raw_text = mf_path.read_text(encoding="utf-8")
        mf_obj = json.loads(raw_text)
        changed = False
        target_digest = f"sha256:{prm_hash[7:]}"
        for layer in mf_obj.get("layers", []):
            if isinstance(layer, dict) and layer.get("mediaType") == "application/vnd.ollama.image.params":
                if layer.get("digest") != target_digest or layer.get("size") != len(prm_bytes):
                    layer["digest"] = target_digest
                    layer["size"] = len(prm_bytes)
                    changed = True
        if changed:
            atomic_write_text(mf_path, json.dumps(mf_obj, separators=(",", ":")), encoding="utf-8")
        return changed
    except Exception:
        return False


def _try_zero_copy_link_v4_q4_blobs(gguf_path: Path, mmproj_path: str, ollama_models_dir: Optional[Path]) -> bool:
    """若检测到标准 Dongfangshuo-Qwen3.8-27B-NSFW-v4-Q4_K_M.gguf，预先通过硬链接挂载到 ollama_models/blobs 并生成 manifest，实现 0 秒免复制注册"""
    if not ollama_models_dir or not gguf_path.exists():
        return False
    try:
        blobs_dir = ollama_models_dir / "blobs"
        blobs_dir.mkdir(parents=True, exist_ok=True)
        model_hash = "sha256-93269ebf9e0acf129ac2be12e1cf41d4c255eac8dce8732b2c0f79a5b4fb2cf7"
        mm_hash = "sha256-c9a09064683620bea3d3bfed5d4462e1a97a7d2fff7e5045d6862a0a85eeb5b5"
        cfg_hash = "sha256-f38c0388bbf93f1c2954be3c7ccfd197a5a1f39c63eb2e33a83005db40c55b6b"
        tpl_hash = "sha256-126dcf837d1eeab9baa4c46fcde855e70b09f3cc678f159df80232d2adfd068a"
        prm_hash, prm_bytes = _build_v4_q4_prm_blob()

        if gguf_path.stat().st_size == 16547400160:
            target_blob = blobs_dir / model_hash
            if not target_blob.exists():
                try:
                    os.link(str(gguf_path), str(target_blob))
                except Exception:
                    pass
        if mmproj_path and Path(mmproj_path).exists() and Path(mmproj_path).stat().st_size == 931145888:
            mm_blob = blobs_dir / mm_hash
            if not mm_blob.exists():
                try:
                    os.link(str(mmproj_path), str(mm_blob))
                except Exception:
                    pass

        # 若主模型 blob 已就绪，自动补齐 3 个微型元数据 blob 与 dongfangshuo-v4/q4 manifest，实现 0 秒免 ollama create 直连
        if (blobs_dir / model_hash).exists():
            tiny_blobs = {
                cfg_hash: b'{"model_format":"gguf","model_family":"qwen35","model_families":["qwen35"],"model_type":"26.9B","file_type":"Q4_K_M"}\n',
                tpl_hash: b'{{- if .System }}<|im_start|>system\nReasoning effort is set to low. Keep your thinking brief and focused, moving directly to the conclusion without unnecessary elaboration.\n\n{{ .System }}<|im_end|>\n{{- else }}<|im_start|>system\nReasoning effort is set to low. Keep your thinking brief and focused, moving directly to the conclusion without unnecessary elaboration.<|im_end|>\n{{- end }}\n{{- range .Messages }}\n{{- if eq .Role "system" }}<|im_start|>system\n{{ .Content }}<|im_end|>\n{{- else if eq .Role "user" }}<|im_start|>user\n{{ .Content }}<|im_end|>\n{{- else if eq .Role "assistant" }}<|im_start|>assistant\n{{- if .Thinking }}\n<think>\n{{ .Thinking }}\n</think>\n\n{{ .Content }}<|im_end|>\n{{- else }}\n{{ .Content }}<|im_end|>\n{{- end }}\n{{- end }}\n{{- end }}<|im_start|>assistant\n',
                prm_hash: prm_bytes,
            }
            for bname, bbytes in tiny_blobs.items():
                bp = blobs_dir / bname
                if not bp.exists():
                    bp.write_bytes(bbytes)

            layers = [
                {
                    "mediaType": "application/vnd.ollama.image.model",
                    "digest": f"sha256:{model_hash[7:]}",
                    "size": 16547400160,
                    "from": "Dongfangshuo-Qwen3.8-27B-NSFW-v4-Q4_K_M.gguf",
                }
            ]
            if (blobs_dir / mm_hash).exists():
                layers.append({
                    "mediaType": "application/vnd.ollama.image.projector",
                    "digest": f"sha256:{mm_hash[7:]}",
                    "size": 931145888,
                    "from": "mmproj-model-bf16.gguf",
                })
            layers.extend([
                {
                    "mediaType": "application/vnd.ollama.image.template",
                    "digest": f"sha256:{tpl_hash[7:]}",
                    "size": 779,
                },
                {
                    "mediaType": "application/vnd.ollama.image.params",
                    "digest": f"sha256:{prm_hash[7:]}",
                    "size": len(prm_bytes),
                },
            ])
            mf_obj = {
                "schemaVersion": 2,
                "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
                "config": {
                    "mediaType": "application/vnd.docker.container.image.v1+json",
                    "digest": f"sha256:{cfg_hash[7:]}",
                    "size": 118,
                },
                "layers": layers,
            }
            mf_path = ollama_models_dir / "manifests" / "registry.ollama.ai" / "library" / "dongfangshuo-v4" / "q4"
            new_mf_text = json.dumps(mf_obj, separators=(",", ":"))
            old_mf_text = mf_path.read_text(encoding="utf-8") if mf_path.exists() else ""
            if old_mf_text != new_mf_text:
                mf_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_text(mf_path, new_mf_text, encoding="utf-8")
                return True
        return False
    except Exception:
        return False


def _auto_link_discovered_v4_q4(custom_paths: Optional[List[str]] = None) -> bool:
    """扫描 model/、models/ 与指定路径，若存在标准 27B-v4-Q4_K_M.gguf 则自动硬链接至内置及系统 ollama_models，并适配显存上下文"""
    updated_any = False
    try:
        target_dirs: List[Optional[Path]] = [_find_ollama_models_dir()]
        env_om = os.environ.get("OLLAMA_MODELS", "").strip()
        if env_om:
            target_dirs.append(Path(env_om))
        if os.environ.get("OLLAMA_NO_HOST_FALLBACK") != "1":
            target_dirs.append(Path.home() / ".ollama" / "models")
            if os.name != "nt" and Path("/usr/share/ollama").exists():
                target_dirs.append(Path("/usr/share/ollama/.ollama/models"))

        gguf_loc = _locate_gguf_anywhere("Dongfangshuo-Qwen3.8-27B-NSFW-v4-Q4_K_M.gguf", custom_paths)
        has_gguf = bool(gguf_loc and gguf_loc.exists() and gguf_loc.stat().st_size == 16547400160)
        mm_loc = _locate_gguf_anywhere("mmproj-model-bf16.gguf", custom_paths) if has_gguf else None
        mm_str = str(mm_loc) if (mm_loc and mm_loc.exists()) else ""

        seen_d = set()
        for td in target_dirs:
            if td and str(td) not in seen_d:
                seen_d.add(str(td))
                if has_gguf and gguf_loc:
                    if _try_zero_copy_link_v4_q4_blobs(gguf_loc, mm_str, td):
                        updated_any = True
                else:
                    if _adapt_existing_v4_q4_manifest_for_vram(td):
                        updated_any = True
    except Exception:
        pass
    return updated_any


def _set_active_strata_port(new_port: int) -> None:
    """更新当前活跃 Strata 引擎端口，并同步刷新内存中已发现的本地 Strata 模型地址"""
    global _ACTIVE_STRATA_PORT
    old_port = _ACTIVE_STRATA_PORT
    _ACTIVE_STRATA_PORT = int(new_port)
    with _DISCOVERED_MODELS_LOCK:
        for _, m in DISCOVERED_LOCAL_MODELS.items():
            if isinstance(m, dict) and m.get("engine") == "strata":
                cur_sp = safe_int(m.get("strata_port"), 8080) or 8080
                if not m.get("strata_config") or cur_sp in (8080, old_port, _ACTIVE_STRATA_PORT):
                    m["strata_port"] = _ACTIVE_STRATA_PORT
                    m["base_url"] = f"http://127.0.0.1:{_ACTIVE_STRATA_PORT}/v1"


def _is_port_cleanly_available(port: int) -> bool:
    """检测本机回环端口是否真正空闲且可绑定（同时拦截 0.0.0.0 外部软件监听与 Windows Hyper-V 保留端口段 10013）"""
    try:
        probe_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe_sock.settimeout(0.15)
        try:
            if probe_sock.connect_ex(("127.0.0.1", int(port))) == 0:
                return False
        finally:
            probe_sock.close()
    except Exception:
        pass
    try:
        bind_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                bind_sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                bind_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            bind_sock.bind(("127.0.0.1", int(port)))
            return True
        finally:
            bind_sock.close()
    except OSError:
        return False


def _pick_available_strata_port(preferred_port: int = 8080) -> int:
    """优先使用 preferred_port (8080)；若被网盘/代理软件占用或处于 Windows 保留端口段，自动顺延至空闲端口"""
    candidates: List[int] = []
    for p in [preferred_port, _ACTIVE_STRATA_PORT] + list(range(8081, 8096)) + list(range(18080, 18096)) + [28080, 38080]:
        p_int = int(p)
        if 1024 <= p_int <= 65535 and p_int not in candidates:
            candidates.append(p_int)
    for cand in candidates:
        if _is_port_cleanly_available(cand):
            return cand
    try:
        ephem = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            ephem.bind(("127.0.0.1", 0))
            return int(ephem.getsockname()[1])
        finally:
            ephem.close()
    except Exception:
        return preferred_port


async def _probe_genuine_strata_server(port: int) -> Optional[List[str]]:
    """探测指定端口是否为真实的 Strata 推理服务（同时校验 /slots 与 /v1/models，防止误把占 8080 的其他软件当成 Strata）"""
    base = f"http://127.0.0.1:{int(port)}"
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=1.5) as client:
            r_slots, r_models = await asyncio.gather(
                client.get(f"{base}/slots"),
                client.get(f"{base}/v1/models"),
                return_exceptions=True,
            )
            if isinstance(r_slots, Exception) or isinstance(r_models, Exception):
                return None
            if getattr(r_slots, "status_code", 0) != 200 or getattr(r_models, "status_code", 0) != 200:
                return None
            m_json = r_models.json()
            if not isinstance(m_json, dict) or not isinstance(m_json.get("data"), list):
                return None
            return [str(m.get("id")) for m in m_json["data"] if isinstance(m, dict) and m.get("id")]
    except Exception:
        return None


def _read_log_tail(log_paths: List[Path], max_chars: int = 1800) -> str:
    chunks: List[str] = []
    for lp in log_paths:
        if lp and lp.exists() and lp.is_file():
            try:
                txt = lp.read_text(encoding="utf-8", errors="ignore").strip()
                if txt:
                    chunks.append(txt[-max_chars:])
            except Exception:
                pass
    combined = "\n".join(chunks).strip()
    return combined[-max_chars:] if len(combined) > max_chars else combined


def _translate_engine_crash_reason(engine_label: str, exit_code: Optional[int], raw_log: str) -> str:
    """将底层 C++/CUDA/Python 引擎退出码与英文日志转化为玩家一眼能懂的中文排障提示"""
    low = (raw_log or "").lower()
    last_lines = [ln.strip() for ln in (raw_log or "").splitlines() if ln.strip()]
    brief_detail = last_lines[-1][:220] if last_lines else ""

    if any(k in low for k in ("smart app control", "winerror 4551", "winerror 1260", "application-control policy")):
        return (
            f"本地引擎 ({engine_label}) 被 Windows「智能应用控制」或安全软件拦截。"
            "请前往「Windows 安全中心 → 应用和浏览器控制」或杀毒软件中放行 engine 目录下的可执行文件后重试。"
        )
    if any(k in low for k in ("missing model shards", "truncated tensor", "does not declare itself shard", "vocab.json", "split.tensors.count")):
        return (
            f"模型文件不完整或分片缺失：请打开左下角「模型 → 下载」检查所有分片是否已完整下载（确保没有 .part 未完成文件）。"
            + (f" 详情：{brief_detail}" if brief_detail else "")
        )
    if exit_code in (3221225781, -1073741515) or any(
        k in low for k in ("nvcuda", "cudart", "cublas", "cuda error", "driver version is insufficient", "no cuda-capable", "every card off", "no gpu")
    ):
        return (
            f"显卡或驱动不支持运行本地引擎 ({engine_label})：需要 NVIDIA 独立显卡且驱动支持 CUDA 13。"
            "请打开 NVIDIA App 将显卡驱动更新至最新版本后重试。"
            + (f" 详情：{brief_detail}" if brief_detail else "")
        )
    if any(k in low for k in ("1455", "页面文件", "頁面文件", "paging file", "page file", "out of memory", "not enough memory", "bad_alloc", "cannot map", "virtualalloc", "mmap")):
        return (
            f"系统内存或虚拟内存不足 ({engine_label})：加载大模型建议在 Windows「高级系统设置 → 性能 → 虚拟内存」中勾选"
            "「自动管理所有驱动器的分页文件大小」，并确保所在磁盘剩余空间充足。"
            + (f" 详情：{brief_detail}" if brief_detail else "")
        )
    if any(k in low for k in ("already in use", "10048", "10013", "cannot listen")):
        return f"本地引擎端口绑定受阻 ({engine_label})，请检查防火墙或本机安全软件网络限制。详情：{brief_detail}"

    code_str = f"exit code={exit_code}" if exit_code is not None else "启动超时"
    if brief_detail:
        return f"本地引擎 ({engine_label}) 未能正常就绪 ({code_str})：{brief_detail}（完整日志见 data/engine_logs 目录）"
    return f"本地引擎 ({engine_label}) 未能正常就绪 ({code_str})，请检查显卡驱动、虚拟内存或查看 data/engine_logs 日志。"


async def _prepare_portable_strata_config(
    local_meta: Dict[str, Any],
    strata_root: Path,
    strata_py: Path,
    port: int,
    creation_flags: int,
    status_callback: Optional[Callable[[str], Awaitable[None]]] = None,
) -> Tuple[Optional[Path], Optional[str]]:
    """
    动态生成 100% 适配当前电脑盘符与目录的 Strata 运行配置 (data/engine_logs/strata-auto-<slug>.json)。
    无论是把 Flash-Next 分片放进 model/、models/，还是通过『指定路径』挂载任意外部文件夹，都能自动校验分片、构建 pack 并启动！
    """
    base_cfg: Dict[str, Any] = {}
    raw_cfg_path = local_meta.get("strata_config") or ""
    if raw_cfg_path and Path(raw_cfg_path).exists():
        try:
            base_cfg = json.loads(Path(raw_cfg_path).read_text(encoding="utf-8"))
        except Exception:
            base_cfg = {}

    gguf_str = str(local_meta.get("gguf_path") or "").strip()
    if not gguf_str and "--native" in (base_cfg.get("args") or []):
        args_l = base_cfg["args"]
        idx = args_l.index("--native")
        if idx + 1 < len(args_l):
            gguf_str = str(args_l[idx + 1])

    gguf_shard1 = _locate_gguf_anywhere(gguf_str) if gguf_str else None
    if not gguf_shard1 or not gguf_shard1.exists():
        # 兜底：在 model/、models/ 与自定义路径中寻找任意 Flash-Next 第一分片
        for cand_meta in _scan_local_models_folder():
            if cand_meta.get("engine") == "strata" and cand_meta.get("gguf_path"):
                p = Path(cand_meta["gguf_path"])
                if p.exists():
                    gguf_shard1 = p
                    break
    if not gguf_shard1 or not gguf_shard1.exists():
        if raw_cfg_path and Path(raw_cfg_path).exists():
            return Path(raw_cfg_path), None
        return None, "未找到本地 Flash-Next 模型文件 (.gguf)，请确认模型已放入 models/Flash-Next 目录或已完成下载。"

    gguf_shard1 = gguf_shard1.absolute()
    shards_ok, shard_err = _check_gguf_shards_complete(gguf_shard1)
    if not shards_ok:
        return None, f"本地模型无法启动：{shard_err}。请打开左下角「模型 → 下载」补全所有分片后再试。"

    clean_stem = _clean_gguf_model_stem(gguf_shard1)
    slug = re.sub(r"[^a-zA-Z0-9_\-]", "-", clean_stem).strip("-").lower() or "flash-next"
    _ENGINE_LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # 匹配或创建 Strata Pack 目录
    packs_root = strata_root / "data" / "packs"
    packs_root.mkdir(parents=True, exist_ok=True)
    low_name = gguf_shard1.name.lower()
    if "dongfangshuo" in low_name and "iq3_xxs" in low_name and (packs_root / "dongfangshuo-iq3_xxs" / "index.txt").exists():
        pack_dir = packs_root / "dongfangshuo-iq3_xxs"
    elif "swift" in low_name and "iq3_xxs" in low_name and (packs_root / "swift-iq3_xxs" / "index.txt").exists():
        pack_dir = packs_root / "swift-iq3_xxs"
    else:
        pack_dir = packs_root / slug

    # 若新放入的 Flash-Next 模型尚未生成 Strata 索引包 (index.txt / native_experts.txt / dense.bin / tokenizer)，自动调用 iq_pack.py 构建
    # 注意：无需构建 43GB 的 experts.bin，Strata 引擎支持通过 native_experts.txt 直接原位映射 GGUF 分片并启用 --resident-experts！
    iq_pack_script = strata_root / "tools" / "iq_pack.py"
    if (
        iq_pack_script.exists()
        and strata_py.exists()
        and (
            not (pack_dir / "index.txt").exists()
            or not (pack_dir / "native_experts.txt").exists()
            or not (pack_dir / "dense.bin").exists()
            or not (pack_dir / "tokenizer" / "vocab.json").exists()
        )
    ):
        if status_callback:
            await status_callback(f"首次加载 {gguf_shard1.name}，正在构建 Strata 索引包（固态约 1~2 分钟，机械硬盘约 5~10 分钟）...")
        iq_log_file = _ENGINE_LOGS_DIR / f"iq-pack-{slug}.log"
        iq_fh = None
        try:
            pack_env = dict(os.environ)
            gguf_py_dir = strata_root / "third_party" / "llama.cpp" / "gguf-py"
            if gguf_py_dir.exists():
                pack_env["STRATA_GGUF_PY"] = str(gguf_py_dir)
            iq_cmd = [
                str(strata_py),
                str(iq_pack_script),
                "--gguf",
                str(gguf_shard1),
                "--out",
                str(pack_dir),
                "--compat-bf16",
            ]
            iq_fh = open(iq_log_file, "w", encoding="utf-8", errors="ignore")
            proc = await asyncio.create_subprocess_exec(
                *iq_cmd,
                cwd=str(strata_root),
                env=pack_env,
                stdout=iq_fh,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=creation_flags,
            )
            for iq_sec in range(1200):
                if proc.returncode is not None:
                    break
                await asyncio.sleep(1.0)
                if status_callback and iq_sec > 0 and iq_sec % 10 == 0:
                    await status_callback(f"首次运行正在构建模型索引包 ({gguf_shard1.name})... ({iq_sec}s)")
            else:
                try:
                    proc.kill()
                except Exception:
                    pass
                return None, "构建 Strata 索引包超时（超过 20 分钟），建议将模型移至固态硬盘 (SSD) 后重试。"
        except Exception as e:
            print(f"自动构建 Strata Pack 异常 ({pack_dir}): {e}")
            return None, f"构建模型索引包异常：{e}"
        finally:
            if iq_fh is not None:
                try:
                    iq_fh.close()
                except Exception:
                    pass

        if (
            proc.returncode != 0
            or not (pack_dir / "index.txt").exists()
            or not (pack_dir / "tokenizer" / "vocab.json").exists()
        ):
            iq_tail = _read_log_tail([iq_log_file])
            return None, _translate_engine_crash_reason("Strata 索引构建", proc.returncode, iq_tail)

    # 自动匹配视觉编码器 mmproj
    mmproj_str = str(local_meta.get("mmproj_path") or "").strip()
    if not mmproj_str and isinstance(base_cfg.get("vision"), dict):
        mmproj_str = str(base_cfg["vision"].get("mmproj") or "").strip()
    mmproj_resolved = _locate_gguf_anywhere(mmproj_str) if mmproj_str else None
    if not mmproj_resolved:
        best_mm = _find_best_mmproj_for_gguf(gguf_shard1, True, [])
        if best_mm and Path(best_mm).exists():
            mmproj_resolved = Path(best_mm)

    strata_exe = (strata_root / "engine" / "strata.exe") if os.name == "nt" else (strata_root / "engine" / "strata")
    if not strata_exe.exists() and (strata_root / "engine" / "strata.exe").exists():
        strata_exe = strata_root / "engine" / "strata.exe"
    vision_exe = (strata_root / "engine" / "strata-vision.exe") if os.name == "nt" else (strata_root / "engine" / "strata-vision")
    if not vision_exe.exists() and (strata_root / "engine" / "strata-vision.exe").exists():
        vision_exe = strata_root / "engine" / "strata-vision.exe"
    expert_profile = strata_root / "data" / "expert-profile.bin"

    args_out = [
        "--pack",
        str(pack_dir),
        "--native",
        str(gguf_shard1),
    ]
    if not re.search(r"-00001-of-(?!0000[12]\.gguf$)\d{5}\.gguf$", low_name):
        args_out.extend(["--ple-gguf", str(gguf_shard1)])
    if expert_profile.exists():
        args_out.extend(["--expert-profile", str(expert_profile)])

    vram_mib = detect_gpu_vram_mib()
    sys_ram_gib = _detect_system_ram_gib()
    if vram_mib >= 22000:
        strata_max_ctx = "102400"
        strata_kv_type = "fp16"
        use_kv_resident = False
        vision_on_gpu = True
    else:
        # 8GB / 12GB / 16GB 显卡统一开启 int8 + --kv-resident 32768 流式 KV：显存占用锁死在 32K (~6.88 GiB)，
        # 超出部分无缝暂存至主机内存，32G/64G 内存机器可零压力畅玩 96K~100K 超长跑团上下文且绝不爆显存！
        if sys_ram_gib >= 46:
            strata_max_ctx = "102400"
        elif sys_ram_gib >= 24 or sys_ram_gib == 0:
            strata_max_ctx = "98304"
        else:
            strata_max_ctx = "65536"
        strata_kv_type = "int8"
        use_kv_resident = True
        vision_on_gpu = False

    args_out.extend([
        "--expert-cache",
        "auto",
        "--prefill",
        "auto",
        "--spec",
        "4",
        "--spec-min-p",
        "0.5",
        "--max-context",
        strata_max_ctx,
        "--kv",
        strata_kv_type,
    ])
    if use_kv_resident:
        args_out.extend(["--kv-resident", "32768"])
    if 0 < sys_ram_gib <= 36:
        args_out.extend(["--resident-budget-gib", str(max(8, min(18, sys_ram_gib - 12)))])
    elif any(k in low_name for k in ("ud-q4", "ud-iq4", "q4_k")):
        args_out.extend(["--resident-budget-gib", "24"])
    elif (pack_dir / "native_experts.txt").exists() or (pack_dir / "experts.bin").exists():
        args_out.append("--resident-experts")

    has_vision = bool(mmproj_resolved and mmproj_resolved.exists() and vision_exe.exists())
    if vram_mib <= 10240:
        # 实测真机 8GB 显卡 (8188 MiB) 需预留 600 MiB 以容纳 prefill + speculative verify device arena (69 MiB)，同时保留 ~900 个 GPU 专家缓存槽位
        base_reserve_mib = 600
    elif vram_mib < 15000:
        base_reserve_mib = 900
    else:
        base_reserve_mib = 900
    phys_vram_mib = _detect_physical_gpu_vram_mib()
    if phys_vram_mib > vram_mib + 512:
        phys_free_mib = _detect_physical_free_gpu_vram_mib()
        usable_budget_mib = max(4800, vram_mib - 2200)
        base_reserve_mib = max(base_reserve_mib, phys_free_mib - usable_budget_mib)
    if has_vision:
        args_out.extend(["--vision", "--vram-reserve-mib", str(base_reserve_mib)])
    elif vram_mib < 15000 or phys_vram_mib > vram_mib + 512:
        args_out.extend(["--vram-reserve-mib", str(base_reserve_mib)])

    lib_dirs = [
        str(p)
        for p in (
            strata_root / "engine",
            strata_root / ".venv" / "Lib" / "site-packages" / "nvidia" / "cu13" / "bin" / "x86_64",
            Path("/usr/local/cuda/lib64") if os.name != "nt" else None,
        )
        if p and p.exists()
    ]

    model_name = str(local_meta.get("upstream_model") or local_meta.get("id") or base_cfg.get("model_name") or clean_stem)
    engine_log_file = _ENGINE_LOGS_DIR / f"strata-{slug}.log"
    runtime_cfg: Dict[str, Any] = {
        "exe": str(strata_exe),
        "args": args_out,
        "cwd": str(strata_root),
        "tokenizer": str(pack_dir / "tokenizer"),
        "model_name": model_name,
        "log": str(engine_log_file),
        "lib_dirs": lib_dirs,
        "port": safe_int(port, 8080) or 8080,
        "env": base_cfg.get("env") or {
            "STRATA_ROUTE_TAIL_SKIP": "0" if vram_mib >= 22000 else "7",
            "STRATA_SPEC_COUPLED": "1",
            "STRATA_SPEC_GUMBEL": "1",
        },
        "gpu": safe_int(base_cfg.get("gpu", 0), 0),
        "gpus_asked": True,
        "reasoning_effort": base_cfg.get("reasoning_effort", "medium"),
        "reasoning_budget_tokens": safe_int(base_cfg.get("reasoning_budget_tokens", 2048), 2048),
        "reasoning_loop_recovery": base_cfg.get("reasoning_loop_recovery", "recover"),
        "reasoning_close_retry": bool(base_cfg.get("reasoning_close_retry", True)),
        "repeat_stop_tokens": safe_int(base_cfg.get("repeat_stop_tokens", 48), 48),
        "sampling": base_cfg.get("sampling") or {
            "temperature": 0.68,
            "top_p": 0.9,
            "top_k": 40,
            "min_p": 0.06,
            "repetition_penalty": 1.05,
            "presence_penalty": 0.20,
            "frequency_penalty": 0.05,
            "penalty_last_n": 1024,
        },
        "cors_origins": ["*"],
    }
    if has_vision and mmproj_resolved:
        runtime_cfg["vision"] = {
            "exe": str(vision_exe),
            "mmproj": str(mmproj_resolved.absolute()),
            "model": str(gguf_shard1),
            "gpu": vision_on_gpu,
            "max_tokens": 1024,
        }

    auto_cfg_path = _ENGINE_LOGS_DIR / f"strata-auto-{slug}.json"
    try:
        atomic_write_text(auto_cfg_path, json.dumps(runtime_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return auto_cfg_path, None
    except Exception as e:
        print(f"写入便携式 Strata 配置失败: {e}")
        if raw_cfg_path and Path(raw_cfg_path).exists():
            return Path(raw_cfg_path), None
        return None, f"写入本地引擎运行配置失败：{e}"


_LOCAL_ENGINE_LOCK = asyncio.Lock()


async def shutdown_local_engines() -> None:
    """服务退出时优雅取消后台模型下载任务，并结束由本服务拉起的 Strata / llama-server 子进程释放显存"""
    for _, task in list(HF_DOWNLOAD_ASYNC_TASKS.items()):
        if task and not task.done():
            task.cancel()
    HF_DOWNLOAD_ASYNC_TASKS.clear()
    for proc in list(_SPAWNED_ENGINE_PROCS):
        try:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3.0)
                except Exception:
                    proc.kill()
        except Exception:
            pass
    _SPAWNED_ENGINE_PROCS.clear()


async def ensure_local_engine_ready(
    model_id: str,
    status_callback: Optional[Callable[[str], Awaitable[None]]] = None
) -> Optional[str]:
    """智能管理本地双引擎 (Strata 与 Ollama/llama-server)，自动避让占用端口并返回可读故障诊断（成功返回 None）"""
    async with _LOCAL_ENGINE_LOCK:
        return await _ensure_local_engine_ready_unlocked(model_id, status_callback)


async def _ensure_local_engine_ready_unlocked(
    model_id: str,
    status_callback: Optional[Callable[[str], Awaitable[None]]] = None
) -> Optional[str]:
    """内部无锁实现：按需静默拉起本地双引擎、端口冲突自动顺延避让、分片完整性校验与中文故障诊断"""
    local_meta = get_local_model_meta(model_id)
    if not local_meta:
        return None

    engine = local_meta.get("engine", "ollama")
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
    si = None
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
        si.wShowWindow = getattr(subprocess, "SW_HIDE", 0)

    def _kill_strata_on_port(target_port: int) -> None:
        if os.name != "nt":
            try:
                proc_root = Path("/proc")
                if proc_root.exists():
                    for pdir in proc_root.iterdir():
                        if not pdir.name.isdigit():
                            continue
                        pid = int(pdir.name)
                        if pid <= 1 or pid == os.getpid():
                            continue
                        try:
                            cmdline = (pdir / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="ignore").lower()
                            comm = (pdir / "comm").read_text(encoding="utf-8", errors="ignore").strip().lower()
                            if (
                                comm in ("strata", "strata-vision")
                                or ("strata/serve/server.py" in cmdline and str(target_port) in cmdline)
                                or "/engine/strata/engine/strata" in cmdline
                            ):
                                os.kill(pid, 9)
                        except Exception:
                            pass
            except Exception:
                pass
            try:
                subprocess.run(
                    ["pkill", "-9", "-f", "engine/strata"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
            except Exception:
                pass
            return
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "strata.exe", "/IM", "strata-vision.exe", "/T"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
                startupinfo=si,
                timeout=5
            )
        except Exception:
            pass
        try:
            out = subprocess.check_output(
                ["netstat", "-ano", "-p", "TCP"],
                encoding="gbk",
                errors="ignore",
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
                startupinfo=si
            )
            pids = set()
            suffix = f":{target_port}"
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[0].upper() == "TCP" and parts[1].endswith(suffix) and parts[3].upper() == "LISTENING":
                    if parts[4].isdigit() and int(parts[4]) > 0:
                        pids.add(int(parts[4]))
            for pid in pids:
                img_name = _get_process_image_name(pid)
                if not any(k in img_name for k in ("strata", "python", "llama")):
                    print(f"  [Warn] 端口 {target_port} 被非推理引擎进程占用 (PID {pid}, {img_name or '未知'})，已跳过强制结束")
                    continue
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid), "/T"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creation_flags,
                    startupinfo=si,
                    timeout=5
                )
        except Exception:
            pass

    def _kill_llama_server() -> None:
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", "llama-server.exe", "/T"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creation_flags,
                    startupinfo=si,
                    timeout=5,
                )
            except Exception:
                pass
        else:
            try:
                proc_root = Path("/proc")
                if proc_root.exists():
                    for pdir in proc_root.iterdir():
                        if not pdir.name.isdigit():
                            continue
                        pid = int(pdir.name)
                        if pid <= 1 or pid == os.getpid():
                            continue
                        try:
                            comm = (pdir / "comm").read_text(encoding="utf-8", errors="ignore").strip().lower()
                            cmdline = (pdir / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="ignore").lower()
                            if comm == "llama-server" or "engine/llama/llama-server" in cmdline:
                                os.kill(pid, 9)
                        except Exception:
                            pass
            except Exception:
                pass
            try:
                subprocess.run(
                    ["pkill", "-9", "-x", "llama-server"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
            except Exception:
                pass

    if engine == "strata":
        preferred_port = int(local_meta.get("strata_port") or 8080)
        target_upstream = local_meta.get("upstream_model") or model_id
        target_aliases = set([target_upstream, model_id] + list(local_meta.get("aliases") or []))

        for chk_port in list(dict.fromkeys([_ACTIVE_STRATA_PORT, preferred_port])):
            active_ids = await _probe_genuine_strata_server(chk_port)
            if active_ids is not None:
                if not active_ids or any(aid in target_aliases for aid in active_ids):
                    _set_active_strata_port(chk_port)
                    return None
                # 端口上正在运行另一个真实的 Strata 模型，先释放旧进程以完成热切换
                if status_callback:
                    await status_callback(f"切换至 {target_upstream}...")
                await asyncio.to_thread(_kill_strata_on_port, chk_port)
                await asyncio.sleep(3.0)

        env_strata = os.environ.get("STRATA_DIR", "").strip()
        if (_BUNDLE_ROOT / "engine" / "strata" / "serve" / "server.py").exists():
            strata_root = _BUNDLE_ROOT / "engine" / "strata"
        elif env_strata and (Path(env_strata) / "serve" / "server.py").exists():
            strata_root = Path(env_strata)
        else:
            strata_root = _BUNDLE_ROOT / "engine" / "strata"

        # 优先使用整合包内置便携版 runtime/python/python.exe（杜绝 .venv 硬编码宿主机路径在外部电脑失效）
        strata_py = _BUNDLE_ROOT / "runtime" / "python" / "python.exe"
        if not strata_py.exists():
            import sys as _sys
            for cand_py in (
                Path(_sys.executable),
                strata_root / ".venv" / "Scripts" / "python.exe",
                strata_root / ".venv" / "bin" / "python",
            ):
                if cand_py and cand_py.exists():
                    try:
                        chk = subprocess.run(
                            [str(cand_py), "-c", "import numpy, jinja2"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=creation_flags,
                            timeout=5,
                        )
                        if chk.returncode == 0:
                            strata_py = cand_py
                            break
                    except Exception:
                        continue
        strata_script = strata_root / "serve" / "server.py"
        strata_bin = (strata_root / "engine" / "strata.exe") if os.name == "nt" else (strata_root / "engine" / "strata")
        if not strata_bin.exists() and (strata_root / "engine" / "strata.exe").exists():
            strata_bin = strata_root / "engine" / "strata.exe"
        if os.name != "nt" and strata_bin.exists():
            try:
                os.chmod(strata_bin, 0o755)
            except Exception:
                pass

        if not (strata_py.exists() and strata_script.exists() and strata_bin.exists()):
            missing = []
            if not strata_py.exists():
                missing.append("运行环境 runtime/python")
            if not strata_bin.exists():
                missing.append(f"推理引擎 {strata_bin.name}")
            if not strata_script.exists():
                missing.append("启动脚本 serve/server.py")
            miss_str = "、".join(missing)
            print(f"Strata 引擎文件缺失，跳过启动等待: {miss_str}")
            err_text = (
                f"缺少本地推理引擎组件（{miss_str}）：若您下载的是几百 KB 的 API 纯净版，请改用 Windows/Linux 纯净整合包；"
                "若已使用整合包，请检查 engine/strata 目录下的文件是否被杀毒软件或 Windows 安全中心误删隔离。"
            )
            if status_callback:
                await status_callback(err_text)
            return err_text

        base_port = 8080 if not local_meta.get("strata_config") else preferred_port
        port = _pick_available_strata_port(base_port)
        _set_active_strata_port(port)
        models_url = f"http://127.0.0.1:{port}/v1/models"
        if port != base_port:
            print(f"  [Info] 默认端口 {base_port} 已被外部软件占用或处于系统保留范围，Strata 已自动避让至端口 {port}")
            if status_callback:
                await status_callback(f"检测到端口 {base_port} 被占用，已自动切换至空闲端口 {port}...")

        if status_callback:
            await status_callback(f"启动 Strata 引擎 ({target_upstream})，约 30~90 秒...")

        # 若 Ollama 正在占用显存，通知其卸载已驻留模型 (keep_alive: 0)；若 llama-server 正在占用 11434 端口，结束其进程释放显存
        ollama_unloaded = False
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=5.0) as client:
                ps_resp = await client.get("http://127.0.0.1:11434/api/ps")
                if ps_resp.status_code == 200:
                    ollama_unloaded = True
                    active_models = ps_resp.json().get("models", [])
                    for active_m in active_models:
                        m_name = active_m.get("name")
                        if m_name:
                            await client.post("http://127.0.0.1:11434/api/generate", json={"model": m_name, "keep_alive": 0})
                    if active_models:
                        await asyncio.sleep(2.0)
        except Exception:
            pass
        if not ollama_unloaded:
            await asyncio.to_thread(_kill_llama_server)
            await asyncio.sleep(1.5)

        strata_cfg, cfg_err = await _prepare_portable_strata_config(
            local_meta, strata_root, strata_py, port, creation_flags, status_callback
        )
        if cfg_err or not (strata_cfg and strata_cfg.exists()):
            err_out = cfg_err or "生成本地 Strata 运行配置失败"
            print(f"Strata 配置准备失败: {err_out}")
            if status_callback:
                await status_callback(err_out)
            return err_out

        _ENGINE_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        slug_for_log = re.sub(r"[^a-zA-Z0-9_\-]", "-", str(target_upstream)).strip("-").lower() or "flash-next"
        serve_log_file = _ENGINE_LOGS_DIR / f"strata-serve-{slug_for_log}.log"
        engine_log_file = _ENGINE_LOGS_DIR / f"strata-{slug_for_log}.log"
        try:
            cfg_log_val = json.loads(strata_cfg.read_text(encoding="utf-8")).get("log")
            if cfg_log_val:
                engine_log_file = Path(str(cfg_log_val))
        except Exception:
            pass
        strata_proc = None
        serve_lf = None
        try:
            serve_lf = open(serve_log_file, "w", encoding="utf-8", errors="ignore")
            st_env = os.environ.copy()
            if os.name != "nt":
                strata_eng_dir = str(_BUNDLE_ROOT / "engine" / "strata" / "engine")
                llama_eng_dir = str(_BUNDLE_ROOT / "engine" / "llama")
                old_ld = st_env.get("LD_LIBRARY_PATH", "")
                st_env["LD_LIBRARY_PATH"] = (
                    f"{strata_eng_dir}:{llama_eng_dir}:/usr/local/nvidia/lib64:/usr/local/nvidia/lib:/usr/local/cuda/lib64:/usr/lib/x86_64-linux-gnu"
                    + (f":{old_ld}" if old_ld else "")
                )
            strata_proc = subprocess.Popen(
                [str(strata_py), str(strata_script), "--engine", "strata", "--config", str(strata_cfg), "--port", str(port)],
                cwd=str(strata_root),
                env=st_env,
                stdout=serve_lf,
                stderr=subprocess.STDOUT,
                creationflags=creation_flags,
                startupinfo=si
            )
            _SPAWNED_ENGINE_PROCS.append(strata_proc)
        except Exception as e:
            err_msg = f"启动 Strata 引擎异常：{e}"
            print(err_msg)
            if status_callback:
                await status_callback(err_msg)
            return err_msg
        finally:
            if serve_lf is not None:
                try:
                    serve_lf.close()
                except Exception:
                    pass

        for wait_sec in range(600):
            await asyncio.sleep(1.0)
            if strata_proc is not None and strata_proc.poll() is not None:
                raw_tail = _read_log_tail([serve_log_file, engine_log_file])
                crash_msg = _translate_engine_crash_reason("Strata", strata_proc.returncode, raw_tail)
                print(f"Strata 引擎进程已提前退出 (exit code={strata_proc.returncode}): {crash_msg}")
                return crash_msg
            if status_callback and wait_sec > 0 and wait_sec % 10 == 0:
                hdd_hint = "（首次加载或机械硬盘读取较慢，请耐心等待）" if wait_sec >= 90 else ""
                await status_callback(f"正在加载 Strata 引擎 ({target_upstream})... ({wait_sec}s){hdd_hint}")
            try:
                async with httpx.AsyncClient(trust_env=False, timeout=2.0) as client:
                    r = await client.get(models_url)
                    if r.status_code == 200:
                        active_ids = [m.get("id") for m in r.json().get("data", []) if isinstance(m, dict)]
                        if not active_ids or any(aid in target_aliases for aid in active_ids):
                            return None
            except Exception:
                pass
        return "加载本地 Flash-Next 模型超时（已等待 10 分钟）：若模型放在机械硬盘 (HDD) 上，建议迁移至固态硬盘 (SSD) 后重试。"

    elif engine == "ollama":
        gguf_chk = local_meta.get("gguf_path")
        if gguf_chk and Path(gguf_chk).exists():
            shards_ok, shard_err = _check_gguf_shards_complete(Path(gguf_chk))
            if not shards_ok:
                return f"本地模型无法启动：{shard_err}。请打开左下角「模型 → 下载」补全文件后再试。"

        manifest_updated = _auto_link_discovered_v4_q4()
        target_ollama_id = local_meta.get("upstream_model") or local_meta.get("id") or model_id
        for chk_sp in list(dict.fromkeys([_ACTIVE_STRATA_PORT, 8080])):
            if await _probe_genuine_strata_server(chk_sp) is not None:
                if status_callback:
                    await status_callback("切换至 Ollama...")
                await asyncio.to_thread(_kill_strata_on_port, chk_sp)
                await asyncio.sleep(2.5)

        global _ACTIVE_LLAMA_PORT
        ollama_ready = False
        registered_models: List[str] = []
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=3.0) as client:
                r = await client.get("http://127.0.0.1:11434/api/tags")
                if r.status_code == 200:
                    ollama_ready = True
                    _ACTIVE_LLAMA_PORT = 11434
                    registered_models = [m.get("name", "") for m in r.json().get("models", []) if isinstance(m, dict)]
                    ps_resp = await client.get("http://127.0.0.1:11434/api/ps")
                    if ps_resp.status_code == 200:
                        for active_m in ps_resp.json().get("models", []):
                            m_name = active_m.get("name")
                            if m_name and (m_name not in (model_id, target_ollama_id) or manifest_updated):
                                await client.post("http://127.0.0.1:11434/api/generate", json={"model": m_name, "keep_alive": 0})
                                await asyncio.sleep(1.5)
        except Exception:
            pass

        if ollama_ready and target_ollama_id not in registered_models:
            _auto_link_discovered_v4_q4()
            try:
                async with httpx.AsyncClient(trust_env=False, timeout=2.0) as client:
                    r_re = await client.get("http://127.0.0.1:11434/api/tags")
                    if r_re.status_code == 200:
                        registered_models = [m.get("name", "") for m in r_re.json().get("models", []) if isinstance(m, dict)]
            except Exception:
                pass
            if target_ollama_id not in registered_models and os.name == "nt":
                # 仅当目标模型 manifest 确实已存在于本地 ollama_models 目录、而当前 11434 进程指向了其他模型库时，才重启内置 ollama.exe
                models_dir_chk = _find_ollama_models_dir()
                manifest_exists_on_disk = False
                if models_dir_chk and ":" in target_ollama_id:
                    m_repo, m_tag = target_ollama_id.split(":", 1)
                    cand_mf = models_dir_chk / "manifests" / "registry.ollama.ai" / "library" / m_repo / m_tag
                    manifest_exists_on_disk = cand_mf.exists()
                if manifest_exists_on_disk:
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/IM", "ollama.exe", "/T"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=creation_flags,
                            startupinfo=si,
                            timeout=5,
                        )
                        await asyncio.sleep(1.0)
                    except Exception:
                        pass
                    ollama_ready = False

        if not ollama_ready:
            if status_callback:
                await status_callback("启动 Ollama...")
            ollama_ready = await _try_auto_wake_ollama()
            if ollama_ready:
                _ACTIVE_LLAMA_PORT = 11434
                try:
                    async with httpx.AsyncClient(trust_env=False, timeout=3.0) as client:
                        r = await client.get("http://127.0.0.1:11434/api/tags")
                        if r.status_code == 200:
                            registered_models = [m.get("name", "") for m in r.json().get("models", []) if isinstance(m, dict)]
                except Exception:
                    pass

        # 若玩家将新 27B/.gguf 放入 model/ 文件夹或指定路径且尚未在 Ollama 中注册，自动生成黄金防复读 Modelfile 并注册
        gguf_path = local_meta.get("gguf_path")
        if ollama_ready and gguf_path and Path(gguf_path).exists() and target_ollama_id not in registered_models:
            _auto_link_discovered_v4_q4()
            try:
                async with httpx.AsyncClient(trust_env=False, timeout=2.0) as client:
                    r_re = await client.get("http://127.0.0.1:11434/api/tags")
                    if r_re.status_code == 200:
                        registered_models = [m.get("name", "") for m in r_re.json().get("models", []) if isinstance(m, dict)]
            except Exception:
                pass
        if ollama_ready and gguf_path and Path(gguf_path).exists() and target_ollama_id not in registered_models:
            ollama_exe = _find_system_ollama_exe()
            if ollama_exe:
                models_dir = _find_ollama_models_dir()
                mmproj_path = local_meta.get("mmproj_path") or ""
                _try_zero_copy_link_v4_q4_blobs(Path(gguf_path), mmproj_path, models_dir)
                if status_callback:
                    await status_callback(f"首次加载 {Path(gguf_path).name}，注册模型...")
                esc_gguf = str(Path(gguf_path).resolve()).replace("\\", "\\\\").replace('"', '\\"')
                mf_lines = [f'FROM "{esc_gguf}"']
                if mmproj_path and Path(mmproj_path).exists():
                    esc_mm = str(Path(mmproj_path).resolve()).replace("\\", "\\\\").replace('"', '\\"')
                    mf_lines.append(f'FROM "{esc_mm}"')
                mf_lines.append(f'TEMPLATE """{GOLDEN_OLLAMA_TEMPLATE}"""')
                mf_lines.extend([
                    "PARAMETER temperature 0.68",
                    "PARAMETER top_p 0.90",
                    "PARAMETER top_k 40",
                    "PARAMETER min_p 0.06",
                    "PARAMETER repeat_penalty 1.03",
                    "PARAMETER repeat_last_n 1024",
                    "PARAMETER presence_penalty 0.10",
                    "PARAMETER frequency_penalty 0.0",
                    "PARAMETER num_predict 4096",
                    f"PARAMETER num_ctx {get_optimal_ollama_num_ctx(96, gguf_path)}",
                    'PARAMETER stop "<|im_start|>"',
                    'PARAMETER stop "<|im_end|>"',
                    'PARAMETER stop "<|endoftext|>"',
                ])
                tmp_mf = _BUNDLE_ROOT / "data" / f"Modelfile.auto_{re.sub(r'[^a-zA-Z0-9_-]', '_', target_ollama_id)}"
                try:
                    tmp_mf.parent.mkdir(parents=True, exist_ok=True)
                    tmp_mf.write_text("\n".join(mf_lines) + "\n", encoding="utf-8")
                    env = os.environ.copy()
                    if models_dir:
                        env["OLLAMA_MODELS"] = str(models_dir)
                    env.setdefault("OLLAMA_HOST", "127.0.0.1:11434")
                    proc = await asyncio.create_subprocess_exec(
                        str(ollama_exe), "create", target_ollama_id, "-f", str(tmp_mf),
                        env=env,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                        creationflags=creation_flags
                    )
                    await asyncio.wait_for(proc.wait(), timeout=300.0)
                except Exception as e:
                    print(f"自动注册 GGUF 模型失败 ({target_ollama_id}): {e}")
                finally:
                    try:
                        if tmp_mf.exists():
                            tmp_mf.unlink()
                    except Exception:
                        pass
            return None
        elif not ollama_ready and gguf_path and Path(gguf_path).exists():
            # 无 Ollama 环境（如 Linux 云服务器）自动使用内置 engine/llama/llama-server 在 11434 端口直载 27B GGUF
            llama_srv_exe = _find_bundled_llama_server_exe()
            if llama_srv_exe and llama_srv_exe.exists():
                target_aliases = set([target_ollama_id, model_id] + list(local_meta.get("aliases") or []))
                for chk_lp in list(dict.fromkeys([_ACTIVE_LLAMA_PORT, 11434])):
                    try:
                        async with httpx.AsyncClient(trust_env=False, timeout=2.0) as client:
                            r_ls = await client.get(f"http://127.0.0.1:{chk_lp}/v1/models")
                            if r_ls.status_code == 200:
                                active_ids = [m.get("id") for m in r_ls.json().get("data", []) if isinstance(m, dict)]
                                if not active_ids or any(aid in target_aliases for aid in active_ids):
                                    _ACTIVE_LLAMA_PORT = chk_lp
                                    return None
                    except Exception:
                        pass
                await asyncio.to_thread(_kill_llama_server)
                await asyncio.sleep(1.5)
                ls_port = 11434 if _is_port_cleanly_available(11434) else _pick_available_strata_port(11435)
                _ACTIVE_LLAMA_PORT = ls_port
                if ls_port != 11434:
                    with _DISCOVERED_MODELS_LOCK:
                        for al_k in [model_id, target_ollama_id] + list(local_meta.get("aliases") or []):
                            if al_k in DISCOVERED_LOCAL_MODELS:
                                DISCOVERED_LOCAL_MODELS[al_k]["base_url"] = f"http://127.0.0.1:{ls_port}/v1"
                if status_callback:
                    await status_callback(f"启动 27B 引擎 ({Path(gguf_path).name})，约 15~30 秒...")
                mmproj_path = local_meta.get("mmproj_path") or ""
                if not mmproj_path:
                    best_mm = _find_best_mmproj_for_gguf(Path(gguf_path), False, [])
                    if best_mm and Path(best_mm).exists():
                        mmproj_path = str(best_mm)
                llama_cmd = [
                    str(llama_srv_exe),
                    "-m", str(gguf_path),
                    "-a", str(target_ollama_id),
                    "--host", "127.0.0.1",
                    "--port", str(ls_port),
                    "-c", str(get_optimal_ollama_num_ctx(96, gguf_path)),
                    "-np", "1",
                    "-fa", "on",
                    "-ctk", "q8_0",
                    "-ctv", "q8_0",
                    "--fit", "on",
                    "--fit-target", "1024",
                    "--reasoning-budget", "1024",
                    "--repeat-penalty", "1.03",
                    "--repeat-last-n", "1024",
                    "--presence-penalty", "0.10",
                    "--frequency-penalty", "0.0",
                    "--dry-multiplier", "0.8",
                    "--dry-base", "1.75",
                    "--dry-allowed-length", "2",
                    "--dry-penalty-last-n", "1024",
                ]
                if mmproj_path and Path(mmproj_path).exists():
                    llama_cmd.extend(["--mmproj", str(mmproj_path)])
                    if detect_gpu_vram_mib() < 22000:
                        llama_cmd.append("--no-mmproj-offload")
                _ENGINE_LOGS_DIR.mkdir(parents=True, exist_ok=True)
                log_file = _ENGINE_LOGS_DIR / "llama-server.log"
                ls_env = os.environ.copy()
                ls_dir_str = str(llama_srv_exe.parent)
                if os.name == "nt":
                    ls_env["PATH"] = ls_dir_str + ";" + ls_env.get("PATH", "")
                else:
                    strata_eng_dir = str(_BUNDLE_ROOT / "engine" / "strata" / "engine")
                    old_ld = ls_env.get("LD_LIBRARY_PATH", "")
                    ls_env["LD_LIBRARY_PATH"] = (
                        f"{ls_dir_str}:{strata_eng_dir}:/usr/local/nvidia/lib64:/usr/local/nvidia/lib:/usr/local/cuda/lib64:/usr/lib/x86_64-linux-gnu"
                        + (f":{old_ld}" if old_ld else "")
                    )
                lf = None
                try:
                    lf = open(log_file, "w", encoding="utf-8", errors="ignore")
                    ls_proc = subprocess.Popen(
                        llama_cmd,
                        cwd=ls_dir_str,
                        env=ls_env,
                        stdout=lf,
                        stderr=subprocess.STDOUT,
                        creationflags=creation_flags,
                        startupinfo=si,
                    )
                    _SPAWNED_ENGINE_PROCS.append(ls_proc)
                except Exception as e:
                    err_msg = f"启动 27B 引擎 (llama-server) 失败：{e}"
                    print(err_msg)
                    return err_msg
                finally:
                    if lf is not None:
                        try:
                            lf.close()
                        except Exception:
                            pass
                for wait_sec in range(300):
                    await asyncio.sleep(1.0)
                    if ls_proc.poll() is not None:
                        raw_tail = _read_log_tail([log_file])
                        crash_msg = _translate_engine_crash_reason("llama-server", ls_proc.returncode, raw_tail)
                        print(f"llama-server 已提前退出 (exit code={ls_proc.returncode}): {crash_msg}")
                        return crash_msg
                    if status_callback and wait_sec > 0 and wait_sec % 10 == 0:
                        await status_callback(f"正在加载 27B 模型 ({Path(gguf_path).name})... ({wait_sec}s)")
                    try:
                        async with httpx.AsyncClient(trust_env=False, timeout=2.0) as client:
                            r_ls = await client.get(f"http://127.0.0.1:{ls_port}/v1/models")
                            if r_ls.status_code == 200:
                                return None
                    except Exception:
                        pass
                return "加载本地 27B 模型超时（已等待 5 分钟），建议检查显存/虚拟内存或将模型迁移至固态硬盘。"
            return (
                "未检测到内置本地推理引擎或系统 Ollama 服务：若您下载的是 API 纯净版，请先安装并启动 Ollama，"
                "或改下 Windows/Linux 纯净整合包。"
            )
        elif not ollama_ready:
            return (
                "本地 Ollama 引擎 (127.0.0.1:11434) 未能启动：请确认已安装 Ollama 或改用纯净整合包，并在左下角「模型」重新选择有效模型。"
            )
    return None




# ==================== 世界书标准 JSON 模板 (纯净版通用空白模板) ====================
WORLDBOOK_TEMPLATE_JSON = {
    "_comment": {
        "usage": "用于导入世界书配置。请保留 world_book 数组结构，直接修改或新增其中的对象后导入。",
        "tips": [
            "每个对象代表一条世界书规则。",
            "match_type: 1=与(AND, 全部关键词同时出现), 2=或(OR, 任一关键词出现), 3=正则表达式(Regex)。",
            "keys 支持数组 ['词1','词2']，也兼容 '_and_词1@wb@词2' 与 '_or_词1@wb@词2' 字符串格式。",
            "key_region (触发区域位掩码): 1=系统, 2=用户消息, 4=AI消息, 6=用户+AI消息, 7=全部。",
            "value_region (影响范围位掩码): 1=提示词(System), 2=前置词(Prefix), 4=后置词(Suffix)，可相加组合。",
            "value_type=0 时使用 value(常规注入)；value_type=1 时使用 value_configs(多分支概率权重注入，概率总和建议为100)。"
        ]
    },
    "world_book": []
}

# ==================== 万物皆模块：标准功能栏预设库与默认配置 ====================
STANDARD_UI_MODULES: List[Dict[str, Any]] = [
    {
        "id": "mod_think",
        "key": "思考推演",
        "type": "thinking_fold",
        "enabled": True,
        "fields": "<think>\n1. 局势与环境因果分析\n2. 在场 NPC 真实动机与反应\n3. 检定判定与剧情走向推演\n</think>",
        "desc": "在正式输出剧情前，于 <think> 标签内分段推演当前场景因果、NPC独立动机、环境线索与检定难度阈值。",
        "v": 2
    },
    {
        "id": "mod_story",
        "key": "剧情正文",
        "type": "story_narrative",
        "enabled": True,
        "fields": "第二人称（你）电影感沉浸叙事，输出 1000~2000 字左右，按场景转换与人物对话自然分段",
        "desc": "保持第二人称电影感叙事，注重光影、声响、微表情与动作细节；严禁代替玩家做决定或抢写玩家台词，按游戏逻辑与真实性合理推演。",
        "v": 2
    },
    {
        "id": "mod_stats",
        "key": "主角状态",
        "type": "progress_stats",
        "enabled": True,
        "fields": "生命: 100/100\n理智: 80/100\n财富: 随时代背景自适应(如银元/金币/灵石/信用点)\n状态: 正常",
        "desc": "根据剧情受创、消耗、交易或休息实时增减生命、理智与世界观对应货币（如银元/金币/灵石/信用点），并动态更新当前 Buff/异常状态。",
        "v": 2
    },
    {
        "id": "mod_equip",
        "key": "装备栏",
        "type": "equipment_slots",
        "enabled": True,
        "fields": "主手: 随身份适配武器或工具(效果简述)\n副手: 无\n防具: 随时代适配衣着护具(防护简述)\n饰品: 关键随身信物(特征简述)",
        "desc": "记录主角当前穿戴的主副手器物、衣着防具与饰品槽位，装备名称必须严格匹配当前时代与世界观，每件装备后用括号标注3~10字微简介，穿脱或损毁时同步更新。",
        "v": 2
    },
    {
        "id": "mod_inv",
        "key": "物品栏",
        "type": "inventory_grid",
        "enabled": True,
        "fields": "应急补给(恢复体力或伤势)x2\n随身照明或工具(贴合时代背景)x1\n关键线索物(来源或用途简述)x1",
        "desc": "记录主角随身背包中的消耗品、工具与线索，格式为「物品名(简短效果)x数量」，道具名称必须严格符合当前时代背景（严禁在现代/悬疑/科幻/修仙局混入西幻金币或网游药剂），使用或获得道具时实时增减。",
        "v": 2
    },
    {
        "id": "mod_npc",
        "key": "角色关系",
        "type": "npc_affinity",
        "enabled": True,
        "fields": "角色: 关键角色\n好感: 50/100\n态度: 中立审视\n动态: 正注视着你的一举一动",
        "desc": "追踪在场或已结识关键 NPC 对主角的好感度(0~100)、当前态度倾向以及眼下的动作/心理动态。",
        "v": 2
    },
    {
        "id": "mod_info",
        "key": "情报卡",
        "type": "text_card",
        "enabled": True,
        "fields": "当前目标: 查明异常源头(推进主线)\n环境线索: 现场遗留可疑痕迹(可进一步调查)\n潜在危机: 暗处似有视线窥探(需保持警惕)",
        "desc": "每回合根据现场局势更新当前主线目标、关键环境线索与潜在危险提示，每个分项独占一行。",
        "v": 2
    },
    {
        "id": "mod_scale",
        "key": "内容尺度",
        "type": "content_scale",
        "enabled": True,
        "fields": "色情: 0纯爱 ➔ 1悸动 ➔ 2擦边 ➔ 3露骨 ➔ 4色情 ➔ 5极致\n暴力: 0全龄 ➔ 1擦伤 ➔ 2见血 ➔ 3残酷 ➔ 4血腥 ➔ 5极致",
        "desc": "状态栏内的色情/暴力(0–5档)双滑块模块，默认均处于关闭状态，在状态栏内开启或拖动后实时改变后续剧情描写程度。",
        "v": 2
    },
    {
        "id": "mod_choices",
        "key": "行动选项",
        "type": "action_choices",
        "enabled": True,
        "fields": "1. 稳健推进或现场调查交涉的具体行动\n2. 高风险高回报的险招博弈行动 【🎲属性检定】\n3. 利用现场环境细节或随身道具破局的具体行动\n4. 出人意料的逆反操作或脑洞奇招",
        "desc": "询问“你打算怎么做？”，结合当前现场局势分行给出 4 个差异化具体行动选项（稳健调查或交涉 / 险招博弈[需投骰时在句末挂🎲检定] / 环境道具破局 / 逆反奇招；直接写自然行动描述，无需带分类中括号前缀）。",
        "v": 2
    },
]

# 默认跑团功能栏（默认不含 CoT 思考推演栏与情报卡；玩家可在「添加栏位」中随时添加思考推演等标准功能栏）
CONTENT_SCALE_FEATURE_ENABLED = False

DEFAULT_UI_MODULES: List[Dict[str, Any]] = [
    dict(m) for m in STANDARD_UI_MODULES
    if m["id"] in ("mod_story", "mod_stats", "mod_equip", "mod_inv", "mod_npc", "mod_choices")
]

STATUS_SUBMODULE_TYPES = {"progress_stats", "equipment_slots", "inventory_grid", "npc_affinity", "text_card", "tags", "gear", "inventory", "relations"}

LEGACY_GLOBAL_PROTOCOL_PREFIX = "【全局底层系统提示词 & `<status>` 状态栏协议（全局生效）】：\n1. 【仅在关键节点触发检定"

DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT = (
    "【系统提示词 · 功能栏与跑团编写协议（可自由修改或清空）】：\n"
    "1. 【🎲 关键节点检定 & 失败推进原则（Fail Forward）】：\n"
    "   - 普通对话、日常观察、常规移动【绝对不挂检定标签】，直接顺畅推进剧情；\n"
    "   - 仅在涉及生死搏杀、高风险潜行、撬锁拆弹、识破关键谎言或逆天改命的【戏剧性分水岭】时，才在对应行动选项末尾标注 `【🎲属性检定】`（如 `【🎲潜行检定】`、`【🎲话术检定】`等，凡需投骰的选项必须包含 `🎲` 图标）；\n"
    "   - 当玩家投掷骰子后，根据事件难度与点数综合判定成败，并在回复开头简要展示检定结果；检定失败时严禁卡死剧情，须以“付出代价或触发新危机”继续推进。\n\n"
    "2. 【思考推演栏 (`<think>...</think>`) 编写规范】：\n"
    "   - 仅当下方功能栏中包含「思考推演」栏位时，才在 `<think>...</think>` 标签内推演当前局势因果、NPC 独立动机与检定阈值；\n"
    "   - 若功能栏中未添加「思考推演」栏位，严禁输出 `<think>` 或 `<thinking>` 标签，直接输出剧情正文。\n\n"
    "3. 【剧情正文栏（主线叙事模块）编写规范】：\n"
    "   - 每次回复必须【首先直接输出 1000~2000 字沉浸式剧情正文段落】，严禁跳过剧情正文直接输出 `<status>` 状态栏！\n"
    "   - 严禁在正文中手写 `剧情正文`、`【剧情正文】`、`[剧情正文]`、`<story>` 等标题行或伪标签，严禁将剧情正文写进 `<status>...</status>` 状态块内。\n\n"
    "4. 【状态类功能栏 (`<status>...</status>`) 编写与跨回合继承规范】：\n"
    "   - 若下方功能栏中包含状态类栏位（如主角状态、装备栏、物品栏、角色关系等），**每一回合**在剧情正文结束后、行动选项之前，都必须输出一个完整的 `<status>...</status>` 纯文本块，严格按功能栏顺序依次写出所有已启用的 `[栏位名]` 及对应分行内容（例如：`[主角状态]`、`[装备栏]`、`[物品栏]`、`[角色关系]`，所有栏位缺一不可！）；\n"
    "   - **【历史状态栏继承铁律】**：每回合必须在上一轮状态栏的基础上累积继承并更新！严禁因为开启新对话、切换场景或遇到新人物就删去历史状态栏信息（已结识的历史 NPC 关系、已有穿戴装备、未消耗的背包物品必须完整保留在对应栏位中，遇到新角色时在 `[角色关系]` 中追加或更新，绝不可清空历史记录！）；\n"
    "   - 若开局尚未结识任何 NPC，`[角色关系]` 栏位也必须保留并写明当前人物状态（如 `周围人物: 暂无其他在场NPC(独自行动中)`），绝不可省略 `[角色关系]` 或任何其他状态栏位；\n"
    "   - 每个槽位/部位/词条独占一行，写成 `字段名: 简短核心内容(补充细节微简介)`；物品栏写成 `物品名称(简短效果说明)x数量`（当某件物品在本回合消耗殆尽、丢弃或失去时，请在本回合将其标注为 `物品名称(已消耗)x0`，后续回合即可移除；若背包已无任何物品则写 `暂无随身物品`）；\n"
    "   - 功能栏中的『格式参考』仅作为排版样式示范，货币单位、装备防具与背包物品必须严格贴合当前剧本的时代与世界观（如民国银元、赛博信用点、修仙灵石、中世纪银币等），严禁跨题材照抄示例假词或混入违和的网游金币/药剂。\n\n"
    "5. 【行动选项栏（底部交互模块）编写规范】：\n"
    "   - 若下方功能栏中包含「行动选项」栏位，仅在 `</status>` 闭合标签之后的最底部输出【唯一一次】“你打算怎么做？”及 `1.` ~ `4.` 编号选项（严禁在 `<status>` 之前提前输出选项，严禁重复输出两遍选项！）；\n"
    "   - 若功能栏中未添加「行动选项」栏位，则结尾自然收束等待玩家自由输入，不输出编号选项。"
)

DEFAULT_STATUS_PANEL_PROMPT = DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT


def upgrade_legacy_global_protocol_prompt(raw_prompt: Optional[str], allow_empty: bool = True) -> str:
    """规范化系统提示词；当用户清空提示词或提交 null 时保持为空字符串，绝不自动复原默认提示词"""
    if raw_prompt is None:
        return ""
    cleaned = str(raw_prompt).strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"\s*\{\{UI_MODULES_SPEC\}\}\s*$", "", cleaned)
    cleaned = re.sub(r"\n*6\.\s*【🧩\s*当前模块出场顺序[\s\S]*$", "", cleaned).strip()
    cleaned = cleaned.replace(
        "在 `<status>...</status>` 块之后的最底部，必须先输出一句“你打算怎么做？”，随后另起新行按 `1.` ~ `4.` 分行给出结合当前现场局势的具体编号选项；",
        "仅在 `</status>` 闭合标签之后的最底部输出【唯一一次】“你打算怎么做？”及 `1.` ~ `4.` 编号选项（严禁在 `<status>` 之前提前输出选项，严禁重复输出两遍选项！）；",
    )
    old_sec4_header = "4. 【状态类功能栏 (`<status>...</status>`) 编写规范】："
    if old_sec4_header in cleaned:
        cleaned = cleaned.replace(
            old_sec4_header,
            "4. 【状态类功能栏 (`<status>...</status>`) 编写与跨回合继承规范】：",
        )
    old_inv_line = "- 每个槽位/部位/词条独占一行，写成 `字段名: 简短核心内容(补充细节微简介)`；物品栏写成 `物品名称(简短效果说明)x数量`；"
    new_inv_line = "- 每个槽位/部位/词条独占一行，写成 `字段名: 简短核心内容(补充细节微简介)`；物品栏写成 `物品名称(简短效果说明)x数量`（当某件物品在本回合消耗殆尽、丢弃或失去时，请在本回合将其标注为 `物品名称(已消耗)x0`，后续回合即可移除；若背包已无任何物品则写 `暂无随身物品`）；"
    if old_inv_line in cleaned:
        cleaned = cleaned.replace(old_inv_line, new_inv_line)
    old_ex_line = "- 功能栏中的『格式参考』仅作为排版样式示范，请结合当前剧本设定与实际剧情实时更新内容，严禁照抄格式参考中的示例假词。"
    new_ex_line = "- 功能栏中的『格式参考』仅作为排版样式示范，货币单位、装备防具与背包物品必须严格贴合当前剧本的时代与世界观（如民国银元、赛博信用点、修仙灵石、中世纪银币等），严禁跨题材照抄示例假词或混入违和的网游金币/药剂。"
    if old_ex_line in cleaned:
        cleaned = cleaned.replace(old_ex_line, new_ex_line)
    return cleaned


def _default_placeholder_for_empty_field(field_name: str, mod_type: str = "") -> str:
    fn = str(field_name or "").strip()
    if re.search(r"生命|体力|精力|理智|精神|耐力|san|hp|mp|sp|护盾", fn, re.IGNORECASE):
        return "100/100"
    if re.search(r"好感|数值|进度|经验|敏感|恶堕|堕落|淫乱|羞耻|兴奋|快感|污染|侵蚀|暴露|警戒|声望|忠诚|信任|欲|催眠|驯服|屈服", fn, re.IGNORECASE):
        return "0/100"
    if mod_type == "progress_stats" and not re.search(r"处境|状态|地点|位置|时间|穿着|服装|评价|称号|身份|境界|等级|外貌|姿势|神态|关系|态度|动态", fn):
        return "0/100"
    return "{当前状态}"


def segment_ui_mod_fields(raw_fields: str, mod_type: str = "") -> str:
    """将挤在一行的模块字段格式或随手输入的空格/顿号词表自动拆分为清晰的多行标准状态栏格式，同时保留用户已有的换行与空行分段"""
    text = str(raw_fields or "").replace("\r\n", "\n")
    text = re.sub(r"<!--[\s\S]*?-->", "", text).strip()
    if not text:
        return ""
    if mod_type in ("story_narrative", "content_scale"):
        return text

    # 识别从单星号 *部位：* 过渡到双星号 **装备：** 的分组边界，自动插入空行分段
    text = re.sub(r"(\*[^*\n]+?\*[^*\n]*?)\s+(\*\*[^*\n:：]+[:：]\*\*)", r"\1\n\n\2", text)

    # 拆分内联的 **字段：**、*字段：*、,字段：*、[字段]：
    text = re.sub(
        r"(?:(?<=\s)|(?<=[,，;；|｜]))(?:\*\*|\*)+\s*([^*\n:：|｜]{1,14}?)\s*(?:\*\*|\*)?\s*[:：]\s*(?:\*\*|\*)?\s*",
        r"\n\1: ",
        text,
    )
    text = re.sub(
        r"[,，;；]\s*([^\s,，;；|｜:：*\n()/]{1,12}?)\s*(?:(?:\*\*|\*)+\s*[:：]|[:：]\s*(?:\*\*|\*)+)\s*",
        r"\n\1: ",
        text,
    )
    text = re.sub(
        r"^\s*(?:\*\*|\*)+\s*([^*\n:：|｜]{1,14}?)\s*(?:\*\*|\*)?\s*[:：]\s*(?:\*\*|\*)?\s*",
        r"\1: ",
        text,
        flags=re.MULTILINE,
    )

    # 保护括号内部文本，拆分同行多个普通「字段:」（支持空值冒号如「主武器: 副武器: 头部:」）
    paren_pool: List[str] = []

    def _mask_parens(m: re.Match) -> str:
        idx = len(paren_pool)
        paren_pool.append(m.group(0))
        return f"__PAREN_MASK_{idx}__"

    masked_lines = []
    for raw_ln in text.split("\n"):
        if not raw_ln.strip():
            masked_lines.append("")
            continue
        masked = re.sub(r"\([^()\n]*\)|（[^（）\n]*）", _mask_parens, raw_ln)
        masked = re.sub(
            r"(?:[ \t]+|[,，;；]\s*)(?![0-9]+\s*[:：])([^\s,，;；|｜:：*\n()]{1,14}?)\s*[:：]\s*",
            r"\n\1: ",
            masked,
        )
        restored = re.sub(
            r"__PAREN_MASK_(\d+)__",
            lambda m: paren_pool[int(m.group(1))] if int(m.group(1)) < len(paren_pool) else "",
            masked,
        )
        masked_lines.append(restored)
    text = "\n".join(masked_lines)

    # 拆分编号选项 1. 【...】 2. 【...】
    text = re.sub(r"\s+(?=[1-9][\.、．\)]\s*[【\[])", "\n", text)

    # 拆分竖线 | 分隔的多个字段
    if "|" in text or "｜" in text:
        lines_out = []
        for para in re.split(r"\n{2,}", text):
            para_lines = []
            for ln in para.split("\n"):
                parts = [p.strip() for p in re.split(r"\s*[|｜]\s*", ln) if p.strip()]
                para_lines.extend(parts)
            if para_lines:
                lines_out.append("\n".join(para_lines))
        text = "\n\n".join(lines_out)

    # 物品栏：若单行用逗号/空格分隔了多个道具，拆分为多行
    if mod_type in ("inventory_grid", "inventory") and "\n" not in text and re.search(r"[,，、]", text):
        items = [p.strip() for p in re.split(r"[,，、]\s*", text) if p.strip()]
        if len(items) > 1:
            text = "\n".join(item if re.search(r"x\d+$", item, re.I) else f"{item}x1" for item in items)

    # 清理多余空格、支持纯关键词列表（如「头部 胸部 腹部 私处」或「姓名、身份、性格」）自动补全冒号与占位符
    allow_bare_keywords = mod_type not in ("story_narrative", "thinking_fold", "action_choices", "inventory_grid", "inventory", "content_scale")
    cleaned_paras = []
    for para in re.split(r"\n{2,}", text):
        c_lines = []
        for ln in para.split("\n"):
            s = re.sub(r"(\*\*[:：]\*\*|[:：]\*\*)\d+$", ":", ln).replace("**", "").strip().strip("|｜,，;；")
            s = re.sub(r"^[:：]\s*", "", s)
            if not s:
                continue
            # 若整行没有任何冒号，且是用户随手写的空格/顿号/逗号分隔短词（如「头部 胸部 腹部 私处」）
            if allow_bare_keywords and ":" not in s and "：" not in s and not re.match(r"^(?:<|\[|【|[1-9][\.、．\)])", s):
                tokens = [t.strip() for t in re.split(r"[\s,，、;；]+", s) if t.strip()]
                if 1 <= len(tokens) <= 16 and all(len(t) <= 14 for t in tokens):
                    for tok in tokens:
                        c_lines.append(f"{tok}: {_default_placeholder_for_empty_field(tok, mod_type)}")
                    continue
            # 若行尾是空冒号（如「主武器:」或「姓名：」），自动补全占位符
            m_empty = re.match(r"^([^:：]{1,18}?)[:：]\s*$", s)
            if m_empty:
                f_name = m_empty.group(1).strip()
                s = f"{f_name}: {_default_placeholder_for_empty_field(f_name, mod_type)}"
            c_lines.append(s)
        if c_lines:
            cleaned_paras.append("\n".join(c_lines))
    return "\n\n".join(cleaned_paras)


def _fill_default_mod_desc(mod: Dict[str, Any]) -> Dict[str, Any]:
    mc = dict(mod)
    mc["v"] = 2
    m_type = str(mc.get("type") or "").strip()
    m_key = str(mc.get("key") or "").strip()
    m_id = str(mc.get("id") or "").strip()

    # 自动归一化三大核心宏模块（防止用户新增“剧情正文栏/思考栏/选项栏”时误落入普通状态栏导致重复渲染）
    if m_id == "mod_story" or m_type == "story_narrative" or re.match(r"^(?:[📖📝]\s*)?(?:剧情正文|正文)(?:栏|模块)?$", m_key):
        m_type = "story_narrative"
        m_id = "mod_story"
        mc["type"] = "story_narrative"
        mc["id"] = "mod_story"
    elif m_id == "mod_think" or m_type == "thinking_fold" or re.match(r"^(?:[🧠💭]\s*)?(?:思考推演|思考过程|思考)(?:栏|模块)?$", m_key):
        m_type = "thinking_fold"
        m_id = "mod_think"
        mc["type"] = "thinking_fold"
        mc["id"] = "mod_think"
    elif m_id == "mod_choices" or m_type == "action_choices" or re.match(r"^(?:[🎯⚡]\s*)?(?:行动选项|可选行动|选项)(?:栏|模块)?$", m_key):
        m_type = "action_choices"
        m_id = "mod_choices"
        mc["type"] = "action_choices"
        mc["id"] = "mod_choices"

    # 若三大核心宏模块缺失默认 fields，从标准模块库补齐
    if m_type in ("thinking_fold", "story_narrative", "action_choices") and "fields" not in mc:
        for d in STANDARD_UI_MODULES:
            if d["type"] == m_type:
                mc["fields"] = d.get("fields", "")
                break

    if mc.get("fields"):
        mc["fields"] = segment_ui_mod_fields(str(mc.get("fields") or ""), m_type)

    if "desc" in mc:
        return mc

    for d in STANDARD_UI_MODULES:
        if d["id"] == m_id or d["key"] == m_key or (m_type in ("thinking_fold", "story_narrative", "action_choices") and d["type"] == m_type):
            mc["desc"] = d.get("desc", "")
            break
    return mc


def _dedupe_singleton_macro_mods(mods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """确保 thinking_fold / story_narrative / action_choices 三大宏模块全局唯一，不出现重复的剧情正文栏"""
    result: List[Dict[str, Any]] = []
    singleton_idx: Dict[str, int] = {}
    for m in mods:
        filled = _fill_default_mod_desc(m)
        m_type = str(filled.get("type") or "")
        if m_type in ("thinking_fold", "story_narrative", "action_choices"):
            if m_type in singleton_idx:
                prev_i = singleton_idx[m_type]
                result[prev_i] = filled
                continue
            singleton_idx[m_type] = len(result)
        result.append(filled)
    return result


def normalize_ui_modules(raw_mods: Any) -> List[Dict[str, Any]]:
    """规范化项目的 ui_modules 列表：严格保留用户实际添加的栏位，绝不暗中自动塞入未添加的思考栏、正文栏或选项栏"""
    if raw_mods is None or not isinstance(raw_mods, list) or len(raw_mods) == 0:
        return []

    valid_mods = []
    for m in raw_mods:
        if not isinstance(m, dict):
            continue
        mc = dict(m)
        if not str(mc.get("key") or "").strip() and str(mc.get("name") or "").strip():
            mc["key"] = str(mc.get("name")).strip()
        k_str = str(mc.get("key") or "").strip()
        if not k_str:
            continue
        if not CONTENT_SCALE_FEATURE_ENABLED and (
            str(mc.get("id") or "") == "mod_scale"
            or str(mc.get("type") or "") == "content_scale"
            or k_str == "内容尺度"
        ):
            continue
        valid_mods.append(mc)
    if not valid_mods:
        return []

    return _dedupe_singleton_macro_mods(valid_mods)


def build_ui_modules_spec_block(project_data: Dict[str, Any]) -> str:
    """严格生成与游戏设定『功能栏提示词』输入框 (#stUiModulesPromptBox) 100% 一致的提示词文本，零后台暗中加料"""
    if not isinstance(project_data, dict):
        return ""
    if project_data.get("status_panel_enabled", True) is False:
        return ""
    mods_list = normalize_ui_modules(project_data.get("ui_modules"))
    if not mods_list:
        return ""

    icon_map = {
        "thinking_fold": "",
        "story_narrative": "",
        "progress_stats": "",
        "equipment_slots": "",
        "inventory_grid": "",
        "npc_affinity": "",
        "text_card": "",
        "action_choices": "",
        "tags": "",
    }
    blocks: List[str] = []
    enabled_idx = 0
    for mod in mods_list:
        if not isinstance(mod, dict) or mod.get("enabled", True) is False:
            continue
        m_type = str(mod.get("type") or "progress_stats").strip()
        if m_type == "content_scale" or str(mod.get("id") or "") == "mod_scale":
            continue
        ic = icon_map.get(m_type, "")
        k = str(mod.get("key") or "").strip()
        if not k:
            continue
        enabled_idx += 1
        if m_type == "story_narrative":
            fields_label = "正文格式"
            desc_label = "正文栏提示词"
        elif m_type == "thinking_fold":
            fields_label = "思考格式"
            desc_label = "思考栏提示词"
        elif m_type == "action_choices":
            fields_label = "选项格式"
            desc_label = "选项栏提示词"
        else:
            fields_label = "格式参考"
            desc_label = "功能栏提示词"
        fields_val = str(mod.get("fields") or "")
        desc_val = str(mod.get("desc") or "")
        blocks.append(
            f"【#{enabled_idx} {k}】\n"
            f"{fields_label}：\n{fields_val}\n"
            f"{desc_label}：\n{desc_val}"
        )
    return "\n\n".join(blocks)


def is_free_chat_project(project_data: Dict[str, Any]) -> bool:
    """判断项目是否为『自由对话 / 聊天』模式"""
    if not isinstance(project_data, dict):
        return False
    if str(project_data.get("id") or "").strip() == "proj_free_chat":
        return True
    if str(project_data.get("category") or "").strip() in ("自由对话", "聊天"):
        return True
    return False


EROTIC_SCALE_TIERS: Dict[int, Tuple[str, str]] = {
    0: ("纯爱", "全年龄纯爱向，严禁任何性暗示或擦边描写，情感表达止步于纯洁牵手与眼神交流。"),
    1: ("悸动", "青涩暧昧与心动拉扯，可包含耳语、拥抱、脸红心跳等轻度肢体接触，点到为止。"),
    2: ("擦边", "性感暗示与暧昧撩拨（如衣衫半解、深吻、身材曲线与体温感官描写），关键处拉灯留白。"),
    3: ("露骨", "直白成人亲密描写，不避讳身体接触、喘息与情欲张力，展现细腻完整的欢爱过程。"),
    4: ("色情", "高浓度成人肉欲特写（R-18），直白刻画性器官交合、体液交融与强烈生理快感反应。"),
    5: ("极致", "完全解禁的极致情色描写（R-18+），全面放开感官过载、深度支配臣服、失神绝顶等重度色情细节。"),
}

VIOLENCE_SCALE_TIERS: Dict[int, Tuple[str, str]] = {
    0: ("全龄", "全年龄和平向，严禁流血与残酷伤亡，冲突均以切磋、制服或点到为止化解。"),
    1: ("擦伤", "轻度少年漫战斗尺度，仅有淤青、擦伤、气喘与痛感，无重伤致残。"),
    2: ("见血", "写实战斗尺度，包含刀剑入肉、流血负伤、骨折与剧痛描写，但不过度渲染血腥惨状。"),
    3: ("残酷", "黑暗成人尺度，包含致命重创、内脏震裂、严酷折磨与冷酷处决描写。"),
    4: ("血腥", "硬核解剖级血腥尺度（R-18G），直白刻画断肢、贯穿、骨骼碎裂与大量失血痉挛细节。"),
    5: ("极致", "完全解禁的极致血腥暴力（R-18G+），全面放开脏器外露、残忍凌虐、生理崩溃与绝望宿命感官冲击。"),
}


def build_content_scale_prompt_block(project_data: Dict[str, Any]) -> str:
    """根据当前项目的色情 (0-5) 与暴力 (0-5) 档位生成实时导演尺度控制指令（当前已隐藏关闭）"""
    if not CONTENT_SCALE_FEATURE_ENABLED:
        return ""
    if not isinstance(project_data, dict):
        return ""
    e_on = bool(project_data.get("erotic_enabled", False))
    v_on = bool(project_data.get("violence_enabled", False))
    if not e_on and not v_on:
        return ""
    e_lvl = max(0, min(5, safe_int(project_data.get("erotic_level", 3), 3)))
    v_lvl = max(0, min(5, safe_int(project_data.get("violence_level", 3), 3)))
    e_name, e_desc = EROTIC_SCALE_TIERS.get(e_lvl, EROTIC_SCALE_TIERS[3])
    v_name, v_desc = VIOLENCE_SCALE_TIERS.get(v_lvl, VIOLENCE_SCALE_TIERS[3])
    lines = ["【当前内容尺度控制（玩家可随时拖动状态栏滑块切换，请严格按此最新档位控制本轮及后续剧情的描写程度）】："]
    if e_on:
        lines.append(f"- 色情尺度：[{e_lvl}档 · {e_name}] —— {e_desc}")
    if v_on:
        lines.append(f"- 暴力尺度：[{v_lvl}档 · {v_name}] —— {v_desc}")
    return "\n".join(lines)


def build_status_module_prompt(project_data: Dict[str, Any], global_protocol_prompt: Optional[str] = None) -> str:
    """仅拼接当前项目在游戏设定中可见的『系统提示词』、『内容尺度』与『功能栏提示词』"""
    if not isinstance(project_data, dict):
        return ""
    proj_proto = project_data.get("system_protocol_prompt")
    if proj_proto is None and global_protocol_prompt is not None and not is_free_chat_project(project_data):
        raw_proto = str(global_protocol_prompt)
    else:
        raw_proto = "" if proj_proto is None else str(proj_proto)

    protocol_header = upgrade_legacy_global_protocol_prompt(raw_proto, allow_empty=True).strip()
    scale_block = build_content_scale_prompt_block(project_data).strip()
    modules_spec = build_ui_modules_spec_block(project_data).strip()

    checklist_footer = ""
    if project_data.get("status_panel_enabled", True) is not False and modules_spec:
        mods_list = normalize_ui_modules(project_data.get("ui_modules"))
        enabled_mods = [
            m for m in mods_list
            if isinstance(m, dict)
            and m.get("enabled", True) is not False
            and str(m.get("id") or "") != "mod_scale"
            and str(m.get("key") or "").strip()
        ]
        story_mod_on = any(str(m.get("type") or "") == "story_narrative" or str(m.get("id") or "") == "mod_story" for m in enabled_mods)
        choices_mod_on = any(str(m.get("type") or "") == "action_choices" or str(m.get("id") or "") == "mod_choices" for m in enabled_mods)
        status_mods = [
            m for m in enabled_mods
            if str(m.get("type") or "progress_stats") in STATUS_SUBMODULE_TYPES
        ]
        if status_mods and "<status>" not in protocol_header.lower():
            mod_tags = "、".join([f"[{str(m.get('key') or '').strip()}]" for m in status_mods])
            auto_status_proto = (
                f"【状态栏输出协议】：\n"
                f"- 剧情正文请直接输出沉浸式小说段落，严禁写出 `【#1 剧情正文】` 等序号标题；\n"
                f"- 在剧情正文结束后、行动选项之前，必须将状态类功能栏（{mod_tags}）统一包裹在一个 `<status>...</status>` 纯文本块内输出，各栏位以 `[栏位名]` 作为分段标题（切勿带 `#2` 等序号），每个槽位/字段独占一行；\n"
                f"- 行动选项放在 `<status>...</status>` 块之后的最底部输出。"
            )
            protocol_header = f"{protocol_header}\n\n{auto_status_proto}".strip() if protocol_header else auto_status_proto

        step_lines: List[str] = []
        step_idx = 1
        if story_mod_on:
            step_lines.append(
                f"第{step_idx}步【剧情正文（严禁省略）】：回复开头必须先直接写出 1000~2000 字的第二人称沉浸式小说剧情正文（严禁不写正文就直接输出 `<status>`！严禁手写 `【剧情正文】` 标题或 `<story>` 标签）。"
            )
            step_idx += 1
        if status_mods:
            mod_tags = "、".join([f"[{str(m.get('key') or '').strip()}]" for m in status_mods])
            skeleton_sections = []
            for sm in status_mods:
                sm_k = str(sm.get("key") or "").strip()
                sm_f = str(sm.get("fields") or "").strip()
                first_f_line = sm_f.splitlines()[0].strip() if sm_f else "字段名: 当前状态"
                skeleton_sections.append(f"[{sm_k}]\n（按『{first_f_line}』等格式参考逐行填写本轮最新状态，切勿漏掉此栏）")
            skeleton_block = "<status>\n" + "\n\n".join(skeleton_sections) + "\n</status>"
            step_lines.append(
                f"第{step_idx}步【状态栏 `<status>...</status>`（{len(status_mods)}个子栏位缺一不可，且必须保留历史状态栏信息）】：在剧情正文结束后，每回合都必须输出且仅输出一个完整包裹在 `<status>` 与 `</status>` 之间的状态块，内部必须依次完整包含 {mod_tags} 共 {len(status_mods)} 个栏位标题及内容；必须在上一回合状态栏基础上继承并更新，严禁因新对话开始或场景切换而删去历史已结识的 `[角色关系]`、已有 `[装备栏]` 与 `[物品栏]` 信息（标准结构骨架如下）：\n{skeleton_block}"
            )
            step_idx += 1
        if choices_mod_on:
            step_lines.append(
                f"第{step_idx}步【行动选项（严禁省略、严禁重复）】：仅在 `</status>` 闭合标签之后的最底部，写出唯一一次“你打算怎么做？”并另起新行给出 `1.`、`2.`、`3.`、`4.` 四个具体行动选项（严禁在 `<status>` 之前提前输出选项，严禁前后重复输出两遍选项！）。"
            )
        if step_lines:
            checklist_footer = "【⚠️ 本次回复完整性自检清单（以下部分必须在同一条回复中按顺序全部输出，缺一不可）】：\n" + "\n".join(step_lines)

    parts = [p for p in (protocol_header, scale_block, modules_spec, checklist_footer) if p]
    if not parts:
        return ""
    return "\n" + "\n\n".join(parts)

# ==================== 企业级默认项目扩展结构 ====================
def get_default_completion_params(temp: float = 0.68, global_defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    gd = global_defaults or {}
    ctx_fallback = safe_int(gd.get("max_context_turns"), 64)
    return {
        "temperature": safe_float(gd.get("temperature"), temp),
        "repetition_penalty": safe_float(gd.get("repetition_penalty"), 1.08),
        "frequency_penalty": safe_float(gd.get("frequency_penalty"), 0.12),
        "presence_penalty": safe_float(gd.get("presence_penalty"), 0.45),
        "top_p": safe_float(gd.get("top_p"), 0.90),
        "top_k": safe_int(gd.get("top_k"), 40),
        "min_p": safe_float(gd.get("min_p"), 0.06),
        "max_tokens": safe_int(gd.get("max_tokens"), 4096),
        "context_mode": str(gd.get("context_mode") or "turns"),
        "context": safe_int(gd.get("context"), ctx_fallback),
        "max_context_k": safe_int(gd.get("max_context_k"), 96),
        "keep_recent_messages": safe_int(gd.get("keep_recent_messages"), 6),
        "worldbook_scan_depth": safe_int(gd.get("worldbook_scan_depth"), 5),
        "thinking_budget": safe_int(gd.get("thinking_budget"), 1024)
    }

def get_default_appearance() -> Dict[str, Any]:
    return {
        "bg_image": "",
        "bg_mobile": "",
        "enable_custom_opacity": False,
        "chat_bubble_opacity": 0.92,
        "no_image_mode": False,
        "theme": "dark",
        "tts_config": {
            "enabled": False,
            "voice_preset": "",
            "rate": 1.0,
            "pitch": 1.0,
            "emotion_vector": {
                "happy": 0.4,
                "angry": 0.0,
                "sad": 0.0,
                "fear": 0.0,
                "hate": 0.0,
                "love": 0.3,
                "surprise": 0.1,
                "neutral": 0.5
            }
        }
    }

def normalize_worldbook_item(item: Dict[str, Any], idx: int = 0) -> Dict[str, Any]:
    """兼容目标站 _and_/_or_@wb@ 字符串格式、SillyTavern 格式、前端字符串枚举与标准数组格式"""
    if not isinstance(item, dict):
        item = {}
    raw_keys = item.get("keys")
    if raw_keys is None or (isinstance(raw_keys, list) and len(raw_keys) == 0 and item.get("key")):
        raw_keys = item.get("key", [])

    raw_mt = item.get("match_type", 2)
    if isinstance(raw_mt, str):
        mt_up = raw_mt.strip().upper()
        if mt_up in ("1", "AND"):
            match_type = 1
        elif mt_up in ("3", "REGEX"):
            match_type = 3
        else:
            match_type = 2
    else:
        match_type = safe_int(raw_mt, 2)
        if match_type not in (1, 2, 3):
            match_type = 2

    raw_vr = item.get("value_region")
    if raw_vr is None and "position" in item:
        st_pos = item.get("position")
        if st_pos in (0, "0", "before_char"):
            raw_vr = 2
        elif st_pos in (4, "4", "at_depth", "after_an"):
            raw_vr = 4
        else:
            raw_vr = 1
    if raw_vr is None:
        raw_vr = 1
    if isinstance(raw_vr, str):
        vr_up = raw_vr.strip().upper()
        if vr_up.isdigit():
            val_region_int = int(vr_up) or 1
        elif vr_up == "PREFIX":
            val_region_int = 2
        elif vr_up == "SUFFIX":
            val_region_int = 4
        else:
            val_region_int = 1
    else:
        val_region_int = safe_int(raw_vr, 1) or 1

    parsed_keys: List[str] = []

    if isinstance(raw_keys, str):
        s = raw_keys.strip()
        if s.startswith("_and_"):
            match_type = 1
            s = s[5:]
            parsed_keys = [k.strip() for k in s.split("@wb@") if k.strip()]
        elif s.startswith("_or_"):
            match_type = 2
            s = s[4:]
            parsed_keys = [k.strip() for k in s.split("@wb@") if k.strip()]
        elif "@wb@" in s:
            parsed_keys = [k.strip() for k in s.split("@wb@") if k.strip()]
        elif match_type == 3 or (len(s) >= 2 and s.startswith("/") and re.search(r"/[gimsuy]*$", s)):
            parsed_keys = [s] if s else []
        else:
            parsed_keys = [k.strip() for k in re.split(r"[,，;；\n]+", s) if k.strip()]
    elif isinstance(raw_keys, list):
        for k in raw_keys:
            if isinstance(k, str) and k.strip():
                if k.startswith("_and_"):
                    match_type = 1
                    parsed_keys.extend([x.strip() for x in k[5:].split("@wb@") if x.strip()])
                elif k.startswith("_or_"):
                    match_type = 2
                    parsed_keys.extend([x.strip() for x in k[4:].split("@wb@") if x.strip()])
                else:
                    parsed_keys.append(k.strip())

    raw_sec_keys = item.get("secondary_keys") if item.get("secondary_keys") is not None else item.get("keysecondary", [])
    parsed_sec_keys: List[str] = []
    if isinstance(raw_sec_keys, str):
        parsed_sec_keys = [k.strip() for k in re.split(r"[,，;；@wb@\n]+", raw_sec_keys) if k.strip()]
    elif isinstance(raw_sec_keys, list):
        parsed_sec_keys = [str(k).strip() for k in raw_sec_keys if str(k).strip()]

    content_str = str(item.get("content") if item.get("content") is not None else (item.get("value") if item.get("value") is not None else ""))
    raw_val_configs = item.get("value_configs")
    val_configs = []
    if isinstance(raw_val_configs, list) and len(raw_val_configs) > 0:
        for vc in raw_val_configs:
            if isinstance(vc, dict):
                prob_val = safe_float(vc.get("probability") if vc.get("probability") is not None else vc.get("weight"), 50.0)
                vc_val = vc.get("value") if vc.get("value") is not None else content_str
                val_configs.append({
                    "value": vc_val,
                    "probability": prob_val,
                    "weight": prob_val
                })
    if not val_configs or (len(val_configs) == 1 and not val_configs[0].get("value") and content_str):
        val_configs = [{"value": content_str, "probability": 100, "weight": 100}]

    if "enabled" in item:
        is_enabled = bool(item["enabled"])
    elif "enable" in item:
        is_enabled = bool(item["enable"])
    elif "disable" in item:
        is_enabled = not bool(item["disable"])
    else:
        is_enabled = True

    mt_str = "AND" if match_type == 1 else ("Regex" if match_type == 3 else "OR")
    vr_str = "Prefix" if val_region_int == 2 else ("Suffix" if val_region_int == 4 else (str(val_region_int) if val_region_int not in (1, 2, 4) else "System"))

    raw_id = item.get("id") if item.get("id") is not None else item.get("uid")
    norm_id = str(raw_id) if (raw_id is not None and str(raw_id).strip() != "") else f"wb_idx_{idx}"

    raw_sort = item.get("sort") if item.get("sort") is not None else (
        item.get("insertion_order") if item.get("insertion_order") is not None else item.get("order")
    )
    sort_val = safe_int(raw_sort, (idx + 1) * 10) if raw_sort is not None else (idx + 1) * 10

    raw_scan_depth = item.get("scan_depth") if item.get("scan_depth") is not None else item.get("scanDepth")
    raw_depth = item.get("depth") if item.get("depth") is not None else raw_scan_depth
    depth_val = safe_int(raw_depth, 5) if raw_depth is not None else 5

    raw_prob = item.get("probability")
    prob_val_int = safe_int(raw_prob, 100) if raw_prob is not None else 100

    out_item: Dict[str, Any] = {
        "id": norm_id,
        "name": item.get("name") or item.get("comment") or f"世界书词条 #{idx + 1:02d}",
        "group": item.get("group") or "默认分类",
        "enable": is_enabled,
        "enabled": is_enabled,
        "match_type": mt_str if isinstance(raw_mt, str) else match_type,
        "keys": parsed_keys,
        "secondary_keys": parsed_sec_keys,
        "selective": bool(item.get("selective", bool(parsed_sec_keys))),
        "selective_logic": safe_int(item.get("selective_logic", item.get("selectiveLogic", 0)), 0),
        "case_sensitive": bool(item.get("case_sensitive", item.get("caseSensitive", False))),
        "exclude_recursion": bool(item.get("exclude_recursion", item.get("excludeRecursion", False))),
        "key_region": safe_int(item.get("key_region", 6), 6),     # 1=Sys, 2=User, 4=AI, 6=User+AI
        "value_region": vr_str if (isinstance(raw_vr, str) and not raw_vr.strip().isdigit()) else val_region_int,
        "value_type": safe_int(item.get("value_type", 0), 0),     # 0=常规, 1=概率分支
        "value": content_str,
        "content": content_str,
        "value_configs": val_configs,
        "sort": sort_val,
        "depth": depth_val,
        "probability": prob_val_int,
        "constant": bool(item.get("constant", False))
    }
    if raw_scan_depth is not None:
        out_item["scan_depth"] = safe_int(raw_scan_depth, depth_val)
    return out_item

def normalize_project_schema(
    payload: Dict[str, Any],
    existing: Optional[Dict[str, Any]] = None,
    global_defaults: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    existing = existing or {}
    now = time.time()
    project_id = payload.get("id") or existing.get("id") or f"proj_{uuid.uuid4().hex[:8]}"

    # 兼容目标站字段名 pre_prompt / pre_text / post_text；当显式传入 "" 或 null 时保持为空字符串，绝不回退旧值
    if "system_prompt" in payload:
        sys_prompt = "" if payload["system_prompt"] is None else str(payload["system_prompt"])
    elif "pre_prompt" in payload:
        sys_prompt = "" if payload["pre_prompt"] is None else str(payload["pre_prompt"])
    else:
        sys_prompt = str(existing.get("system_prompt") or "")

    if "prefix" in payload:
        prefix = "" if payload["prefix"] is None else str(payload["prefix"])
    elif "pre_text" in payload:
        prefix = "" if payload["pre_text"] is None else str(payload["pre_text"])
    else:
        prefix = str(existing.get("prefix") or "")

    if "suffix" in payload:
        suffix = "" if payload["suffix"] is None else str(payload["suffix"])
    elif "post_text" in payload:
        suffix = "" if payload["post_text"] is None else str(payload["post_text"])
    else:
        suffix = str(existing.get("suffix") or "")

    raw_wb = payload.get("world_book", existing.get("world_book", []))
    norm_wb = [normalize_worldbook_item(x, i) for i, x in enumerate(raw_wb)] if isinstance(raw_wb, list) else []

    raw_wbg = payload.get("world_book_groups")
    if not isinstance(raw_wbg, list):
        raw_wbg = existing.get("world_book_groups")
    wb_groups = list(raw_wbg) if isinstance(raw_wbg, list) else ["默认分类", "核心世界观", "登场人物设定", "地点与势力", "隐藏剧情触发"]
    for w in norm_wb:
        g = w.get("group") or "默认分类"
        if g not in wb_groups:
            wb_groups.append(g)

    base_comp = get_default_completion_params(global_defaults=global_defaults)
    raw_merged_comp = {
        **base_comp,
        **(existing.get("completion_params") if isinstance(existing.get("completion_params"), dict) else {}),
        **(payload.get("completion_params") if isinstance(payload.get("completion_params"), dict) else {})
    }
    comp = get_default_completion_params(global_defaults=raw_merged_comp)
    raw_payload_comp = payload.get("completion_params") if isinstance(payload.get("completion_params"), dict) else {}
    _ctx_default = safe_int(base_comp.get("context"), 16) or 16
    if "context" in raw_payload_comp:
        max_turns = safe_int(raw_payload_comp["context"], _ctx_default)
    elif "max_context_turns" in payload:
        max_turns = safe_int(payload["max_context_turns"], _ctx_default)
    else:
        max_turns = safe_int(comp.get("context", existing.get("max_context_turns", _ctx_default)), _ctx_default)
    comp["context"] = max_turns
    if comp.get("context_mode") not in ("turns", "tokens"):
        comp["context_mode"] = "turns"

    app_cfg = {
        **get_default_appearance(),
        **(existing.get("appearance") if isinstance(existing.get("appearance"), dict) else {}),
        **(payload.get("appearance") if isinstance(payload.get("appearance"), dict) else {})
    }
    if isinstance(payload.get("tts_config"), dict):
        app_cfg["tts_config"] = {**(app_cfg.get("tts_config") or {}), **payload["tts_config"]}
    if "theme_mode" in app_cfg and "theme" not in (payload.get("appearance") or {}):
        app_cfg["theme"] = app_cfg["theme_mode"]
    app_cfg["theme_mode"] = app_cfg.get("theme", "dark")

    avatar_val = payload.get("avatar") or payload.get("icon") or existing.get("avatar") or existing.get("icon")
    if not avatar_val:
        _explicit_empty = any(k in src and src.get(k) is not None for src in (payload, existing) for k in ("avatar", "icon"))
        avatar_val = "" if _explicit_empty else "🎲"
    raw_regex_list = payload.get("regex_replaces") if payload.get("regex_replaces") is not None else payload.get("regex_scripts", existing.get("regex_replaces", existing.get("regex_scripts", [])))
    regex_list = [dict(rx) if isinstance(rx, dict) else rx for rx in raw_regex_list] if isinstance(raw_regex_list, list) else []
    gd = global_defaults or {}

    raw_og = payload.get("opening_greetings")
    if raw_og is None and "opening_greetings" not in payload:
        raw_og = existing.get("opening_greetings")
    norm_og: List[Dict[str, Any]] = []
    if isinstance(raw_og, list):
        for idx, item in enumerate(raw_og):
            if isinstance(item, str):
                txt = item.strip()
                if txt:
                    norm_og.append({"id": f"og_{idx + 1}", "title": "", "content": txt})
            elif isinstance(item, dict):
                title = str(item.get("title") or "").strip()
                content = str(item.get("content") or item.get("text") or "").strip()
                if title or content:
                    og_entry: Dict[str, Any] = {
                        "id": str(item.get("id") or f"og_{idx + 1}"),
                        "title": title,
                        "content": content
                    }
                    if item.get("badge"):
                        og_entry["badge"] = str(item["badge"]).strip()
                    if item.get("desc"):
                        og_entry["desc"] = str(item["desc"]).strip()
                    if "isSandbox" in item:
                        og_entry["isSandbox"] = bool(item["isSandbox"])
                    norm_og.append(og_entry)

    if "system_protocol_prompt" in payload:
        raw_sp = payload.get("system_protocol_prompt")
        sys_proto = "" if raw_sp is None else upgrade_legacy_global_protocol_prompt(str(raw_sp), allow_empty=True)
    elif "system_protocol_prompt" in existing:
        raw_sp = existing.get("system_protocol_prompt")
        sys_proto = "" if raw_sp is None else upgrade_legacy_global_protocol_prompt(str(raw_sp), allow_empty=True)
    else:
        sys_proto = ""

    desc_val = (
        ("" if payload["description"] is None else str(payload["description"]))
        if "description" in payload
        else str(existing.get("description") or "")
    )
    open_stmt_val = (
        ("" if payload["opening_statement"] is None else str(payload["opening_statement"]))
        if "opening_statement" in payload
        else str(existing.get("opening_statement") or "")
    )

    raw_pvars = payload.get("prompt_variables") if isinstance(payload.get("prompt_variables"), list) else (
        existing.get("prompt_variables") if isinstance(existing.get("prompt_variables"), list) else []
    )
    norm_pvars: List[Dict[str, Any]] = []
    for pv in raw_pvars:
        if not isinstance(pv, dict):
            continue
        pv_copy = dict(pv)
        pv_key = str(pv_copy.get("key") or pv_copy.get("name") or "").strip()
        if not pv_key:
            continue
        pv_copy["key"] = pv_key
        pv_copy["name"] = str(pv_copy.get("name") or pv_key).strip()
        if pv_copy.get("default") is None:
            pv_copy["default"] = "" if pv_copy.get("value") is None else str(pv_copy.get("value"))
        norm_pvars.append(pv_copy)

    return {
        "id": project_id,
        "name": payload.get("name") or existing.get("name") or "未命名剧本",
        "avatar": avatar_val,
        "icon": avatar_val,
        "description": desc_val,
        "author": payload.get("author", existing.get("author", "Admin Studio")),
        "category": payload.get("category", existing.get("category", "")),
        "tags": list(payload["tags"]) if isinstance(payload.get("tags"), list) else (list(existing["tags"]) if isinstance(existing.get("tags"), list) else []),
        "system_prompt": sys_prompt,
        "system_protocol_prompt": sys_proto,
        "prefix": prefix,
        "suffix": suffix,
        "opening_greetings": norm_og,
        "opening_statement": open_stmt_val,
        "suggested_questions": list(payload.get("suggested_questions", existing.get("suggested_questions", [])) or []),
        "prompt_variables": norm_pvars,
        "status_panel_enabled": bool(payload.get("status_panel_enabled", existing.get("status_panel_enabled", True))),
        "status_panel_template": payload.get("status_panel_template", existing.get("status_panel_template", "")),
        "ui_modules": normalize_ui_modules(
            payload.get("ui_modules")
            if isinstance(payload.get("ui_modules"), list)
            else existing.get("ui_modules")
        ),
        "world_book": norm_wb,
        "world_book_groups": wb_groups,
        "regex_replaces": list(regex_list),
        "regex_scripts": list(regex_list),
        "cg_book": payload.get("cg_book", existing.get("cg_book", [])),
        "memory_palace": payload.get("memory_palace", existing.get("memory_palace", [])),
        "memory_type": payload.get("memory_type", existing.get("memory_type", "auto_summary")),
        "max_context_turns": max_turns,
        "erotic_enabled": bool(payload.get("erotic_enabled", existing.get("erotic_enabled", gd.get("erotic_enabled", False)))),
        "violence_enabled": bool(payload.get("violence_enabled", existing.get("violence_enabled", gd.get("violence_enabled", False)))),
        "erotic_level": max(0, min(5, safe_int(payload.get("erotic_level", existing.get("erotic_level", gd.get("erotic_level", 3))), 3))),
        "violence_level": max(0, min(5, safe_int(payload.get("violence_level", existing.get("violence_level", gd.get("violence_level", 3))), 3))),
        "auto_summarize": bool(payload.get("auto_summarize", existing.get("auto_summarize", gd.get("auto_summarize", True)))),
        "use_global_params": bool(payload.get("use_global_params", existing.get("use_global_params", False))),
        "completion_params": comp,
        "appearance": app_cfg,
        "tts_config": app_cfg.get("tts_config", {}),
        "created_at": existing.get("created_at", now),
        "updated_at": now
    }

# ==================== 预设模组（纯净版为空，仅保留默认游戏） ====================
EXPLORE_PRESET_APPS: List[Dict[str, Any]] = []

# ==================== 动态变量替换、正则引擎、世界书引擎与CG引擎 ====================
def _eval_dice_expr(expr: str) -> str:
    """解析 SillyTavern {{roll:...}} 掷骰语法（如 20、1d20+3、2d6-1）"""
    s = str(expr or "").strip().lower()
    if not s:
        return "1"
    if s.isdigit():
        sides = max(1, min(10000, int(s)))
        return str(random.randint(1, sides))
    m = re.match(r"^(\d*)d(\d+)\s*([+-]\s*\d+)?$", s)
    if m:
        cnt = max(1, min(100, int(m.group(1) or "1")))
        sides = max(1, min(10000, int(m.group(2))))
        mod = int(m.group(3).replace(" ", "")) if m.group(3) else 0
        return str(sum(random.randint(1, sides) for _ in range(cnt)) + mod)
    return s


def interpolate_variables(
    text: str,
    prompt_variables: Any = None,
    chat_inputs: Optional[Dict[str, Any]] = None,
) -> str:
    if not text:
        return ""
    var_map: Dict[str, str] = {"user": "你"}
    var_map_ci: Dict[str, str] = {"user": "你"}
    if isinstance(prompt_variables, dict):
        for k, val in prompt_variables.items():
            ks = str(k or "").strip()
            if ks and val is not None:
                s_val = str(val)
                var_map[ks] = s_val
                var_map_ci[ks.lower()] = s_val
    else:
        for v in (prompt_variables or []):
            if not isinstance(v, dict):
                continue
            k = str(v.get("key") or v.get("name") or "").strip()
            if k:
                raw_def = v.get("default") if v.get("default") is not None else v.get("value")
                s_def = "" if raw_def is None else str(raw_def)
                var_map[k] = s_def
                var_map_ci[k.lower()] = s_def
    if isinstance(chat_inputs, dict):
        for k, val in chat_inputs.items():
            ks = str(k or "").strip()
            if ks and val is not None and str(val).strip() != "":
                s_val = str(val)
                var_map[ks] = s_val
                var_map_ci[ks.lower()] = s_val

    # 1. 移除酒馆注释宏 {{// ... }}
    out = re.sub(r"\{\{\s*//[\s\S]*?\}\}", "", str(text))

    # 2. 处理 {{setvar::key::val}} 与 {{getvar::key}}
    def _repl_setvar(m: re.Match) -> str:
        k = m.group(1).strip()
        v_str = m.group(2)
        if k:
            var_map[k] = v_str
            var_map_ci[k.lower()] = v_str
            if isinstance(chat_inputs, dict):
                chat_inputs[k] = v_str
            elif isinstance(prompt_variables, dict):
                prompt_variables[k] = v_str
        return ""

    out = re.sub(r"\{\{\s*setvar::([^:}]+)::([\s\S]*?)\}\}", _repl_setvar, out, flags=re.IGNORECASE)
    out = re.sub(
        r"\{\{\s*getvar::([^}]+)\}\}",
        lambda m: var_map.get(m.group(1).strip(), var_map_ci.get(m.group(1).strip().lower(), "")),
        out,
        flags=re.IGNORECASE,
    )

    # 3. 处理 {{random:...}} / {{pick:...}} / {{roll:...}} / {{date}} / {{time}}
    def _repl_func_macro(m: re.Match) -> str:
        fn = m.group(1).strip().lower()
        arg = m.group(2)
        if fn in ("random", "pick"):
            sep = "::" if "::" in arg else ","
            opts = [x.strip() for x in arg.split(sep) if x.strip() != ""]
            return random.choice(opts) if opts else ""
        if fn == "roll":
            return _eval_dice_expr(arg)
        return m.group(0)

    out = re.sub(r"\{\{\s*(random|pick|roll)\s*(?:::|:)\s*([\s\S]*?)\}\}", _repl_func_macro, out, flags=re.IGNORECASE)

    # 4. 通用变量替换（支持中文/Unicode 变量名与大小写无关内置宏）
    weekdays_zh = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")

    def repl(match: re.Match) -> str:
        key = match.group(1).strip()
        if key in var_map:
            return var_map[key]
        k_low = key.lower()
        if k_low in var_map_ci:
            return var_map_ci[k_low]
        if k_low == "date":
            return time.strftime("%Y-%m-%d")
        if k_low == "time":
            return time.strftime("%H:%M")
        if k_low == "weekday":
            return weekdays_zh[time.localtime().tm_wday]
        return match.group(0)

    return re.sub(r"\{\{\s*([^\s{}:]+)\s*\}\}", repl, out)


def _compile_st_or_py_regex(raw_pattern: str, default_flags: int = 0) -> Tuple[Any, bool]:
    """兼容 JS/SillyTavern `/body/flags` 语法、JS 命名捕获组 `(?<name>...)` 与普通 Python 正则"""
    pat = str(raw_pattern or "")
    flags = default_flags
    is_global = True
    m_slash = re.match(r"^/([\s\S]+)/([a-zA-Z]*)$", pat)
    if m_slash:
        pat = m_slash.group(1)
        flag_str = m_slash.group(2).lower()
        is_global = ("g" in flag_str) or (flag_str == "")
        if "i" in flag_str:
            flags |= re.IGNORECASE
        if "m" in flag_str:
            flags |= re.MULTILINE
        if "s" in flag_str:
            flags |= re.DOTALL
    # 将 JS 命名捕获组 (?<name>...) 转换为 Python (?P<name>...)，跳过 (?<=...) 与 (?<!...)
    pat = re.sub(r"(?<!\\)\(\?<(?![=!])([A-Za-z_][A-Za-z0-9_]*)>", r"(?P<\1>", pat)
    return re.compile(pat, flags), is_global


Pattern_or_Any = Any


def _apply_js_replacement(compiled_re: Any, replace_str: str, source_text: str, is_global: bool = True) -> str:
    """使用纯函数回调完整兼容 JS/SillyTavern 替换语法（$$、$&、$`、$'、$<name>、$1~$99），彻底规避 Python re.sub 反斜杠转义崩溃"""
    rep_template = str(replace_str)
    if "$" not in rep_template:
        return compiled_re.sub(lambda _: rep_template, source_text, count=0 if is_global else 1)

    token_re = re.compile(r"\$(\$|&|`|'|<([A-Za-z_][A-Za-z0-9_]*)>|(\d{1,2}))")

    def _repl_cb(m: re.Match) -> str:
        groups = m.groups()
        gdict = m.groupdict()

        def _tok(tm: re.Match) -> str:
            spec = tm.group(1)
            if spec == "$":
                return "$"
            if spec == "&":
                return m.group(0)
            if spec == "`":
                return source_text[:m.start()]
            if spec == "'":
                return source_text[m.end():]
            named = tm.group(2)
            if named is not None:
                val = gdict.get(named)
                return "" if val is None else val
            num_str = tm.group(3)
            if num_str is not None:
                idx = int(num_str)
                if idx == 0:
                    return "$0"
                if 1 <= idx <= len(groups):
                    val = groups[idx - 1]
                    return "" if val is None else val
                if idx >= 10 and (idx // 10) <= len(groups):
                    val = groups[(idx // 10) - 1]
                    return ("" if val is None else val) + str(idx % 10)
            return tm.group(0)

        return token_re.sub(_tok, rep_template)

    return compiled_re.sub(_repl_cb, source_text, count=0 if is_global else 1)


def apply_regex_scripts(text: str, regex_list: List[Dict[str, Any]], target_scope: int, only_persistent: bool = True) -> Tuple[str, List[str]]:
    """
    target_scope: 1 = AI回复("assistant"), 2 = 用户输入("user")
    only_persistent: True 表示仅执行 is_only_render=False 的持久化正则；False 表示全部执行
    完整兼容本项目原生规则与 SillyTavern 正则脚本 (findRegex / replaceString / placement / disabled / markdownOnly)。
    """
    if not text or not isinstance(regex_list, list) or not regex_list:
        return text, []
    applied_titles: List[str] = []
    result = text
    for item in regex_list:
        if not isinstance(item, dict):
            continue
        if "enabled" in item:
            is_en = bool(item["enabled"])
        elif "is_enable" in item:
            is_en = bool(item["is_enable"])
        elif "disabled" in item:
            is_en = not bool(item["disabled"])
        else:
            is_en = True
        if not is_en:
            continue

        is_only_render = bool(
            item.get("is_only_render", False)
            or (item.get("markdownOnly") and not item.get("promptOnly"))
        )
        if only_persistent and is_only_render:
            continue

        # 作用域解析：兼容本项目 scope (1=AI, 2=User, 10=All) 与酒馆 placement 数组 ([1]=User, [2]=AI)
        scope = 10
        if "scope" in item and item.get("scope") is not None:
            raw_scope = item.get("scope")
            if isinstance(raw_scope, str):
                s_lower = raw_scope.strip().lower()
                scope = 1 if s_lower in ("1", "assistant", "ai") else (2 if s_lower in ("2", "user") else 10)
            elif isinstance(raw_scope, list):
                has_ai = any(str(x).lower() in ("1", "assistant", "ai") for x in raw_scope)
                has_user = any(str(x).lower() in ("2", "user") for x in raw_scope)
                scope = 10 if (has_ai and has_user) else (1 if has_ai else (2 if has_user else 0))
            else:
                scope = safe_int(raw_scope, 10)
        elif isinstance(item.get("placement"), list):
            st_pl = {safe_int(x, -1) for x in item["placement"]}
            # SillyTavern placement: 1 = USER_INPUT, 2 = AI_OUTPUT
            has_user = 1 in st_pl
            has_ai = 2 in st_pl
            if has_user and has_ai:
                scope = 10
            elif has_ai:
                scope = 1
            elif has_user:
                scope = 2
            elif not st_pl:
                scope = 10
            else:
                scope = 0

        if scope not in (target_scope, 10):
            continue

        pattern = (
            item.get("pattern")
            if item.get("pattern") is not None
            else (item.get("match_regex") if item.get("match_regex") is not None else item.get("findRegex", ""))
        )
        replace_str = (
            item.get("replacement")
            if item.get("replacement") is not None
            else (item.get("replace_text") if item.get("replace_text") is not None else item.get("replaceString", ""))
        )
        if not pattern:
            continue
        try:
            compiled, is_global = _compile_st_or_py_regex(str(pattern))
            new_res = _apply_js_replacement(compiled, str(replace_str), result, is_global=is_global)
            if new_res != result:
                applied_titles.append(item.get("name") or item.get("scriptName") or item.get("title") or str(pattern))
                result = new_res
        except Exception as e:
            print(f"[RegexEngine] 正则规则执行异常 ({pattern}): {e}")
    return result, applied_titles


_REAL_THINK_BLOCK_RE = re.compile(r"(?<!`)<think(?:ing)?>(?!`)[\s\S]*?(?<!`)</think(?:ing)?>(?!`)", re.IGNORECASE)
_REAL_ORPHAN_CLOSE_THINK_RE = re.compile(r"^[\s\S]*?(?<!`)</think(?:ing)?>(?!`)\s*", re.IGNORECASE)
_REAL_UNCLOSED_OPEN_THINK_RE = re.compile(r"(?<!`)<think(?:ing)?>(?!`)[\s\S]*$", re.IGNORECASE)


def _strip_status_and_wrapper_tags(text: str) -> str:
    if not text:
        return ""
    probe = re.sub(r"<status(?:\s+[^>]*)?>[\s\S]*?</status>", "", text, flags=re.IGNORECASE)
    probe = re.sub(r"<status(?:\s+[^>]*)?>[\s\S]*$", "", probe, flags=re.IGNORECASE)
    probe = re.sub(r"</?(?:story|narrative|text)\s*>", "", probe, flags=re.IGNORECASE)
    return probe


def _has_any_visible_outside_status(text: str) -> bool:
    """检测去除思维链与 <status> 后是否还有任何非空可见文本（哪怕只有 'OK'、简短对白或 1.2.3. 编号规则）"""
    if not text:
        return False
    probe = _REAL_THINK_BLOCK_RE.sub("", text)
    probe = _REAL_UNCLOSED_OPEN_THINK_RE.sub("", probe)
    probe = _strip_status_and_wrapper_tags(probe)
    return bool(probe.strip())


def _has_narrative_outside_status(text: str) -> bool:
    """检测文本在去除 <think>...</think>、<status>...</status> 与底部选项后是否仍包含实质剧情正文"""
    if not text:
        return False
    probe = _REAL_THINK_BLOCK_RE.sub("", text)
    probe = _REAL_UNCLOSED_OPEN_THINK_RE.sub("", probe)
    probe = _strip_status_and_wrapper_tags(probe)
    probe = re.sub(r"(?<!`)</?think(?:ing)?>(?!`)", "", probe, flags=re.IGNORECASE)
    probe = re.sub(r"(?:^|\n)\s*(?:你打算怎么做|接下来你打算怎么做|你的选择)[？?：:\s]*[\s\S]*$", "", probe, flags=re.IGNORECASE)
    probe = re.sub(r"(?:^|\n)\s*[1-9][\.、．\)]\s*[^\n]+", "", probe)
    return len(probe.strip()) >= 25


def strip_thinking_blocks(text: str) -> str:
    """清理模型输出或历史消息中的思维链块：
    1. 彻底清除 <think>...</think> 推理独白（不因简短回复或编号列表而泄漏思维链）；
    2. 跳过反引号包裹的字面量 `` `<think>` `` / `` `</think>` ``，防止润色系统提示词时误截断后半段内容；
    3. 兼容漏写开标签的孤立 </think> 与生成中断的未闭合 <think>。"""
    if not text:
        return ""
    s = re.sub(r"</?(?:story|narrative|text)\s*>", "", text, flags=re.IGNORECASE)
    if _REAL_THINK_BLOCK_RE.search(s):
        cand = _REAL_THINK_BLOCK_RE.sub("", s).strip()
        if _has_any_visible_outside_status(cand) or not cand:
            s = cand
        else:
            # 极端回退：模型仅输出了 <think>正文</think><status>...</status> 而正文区全空时保留内容壳外文本
            s = cand
    if re.search(r"(?<!`)</think(?:ing)?>(?!`)", s, flags=re.IGNORECASE):
        cand = _REAL_ORPHAN_CLOSE_THINK_RE.sub("", s, count=1).strip()
        if _has_any_visible_outside_status(cand):
            s = cand
        else:
            s = re.sub(r"(?<!`)</?think(?:ing)?>(?!`)", "", s, flags=re.IGNORECASE)
    if re.search(r"(?<!`)<think(?:ing)?>(?!`)", s, flags=re.IGNORECASE):
        cand = _REAL_UNCLOSED_OPEN_THINK_RE.sub("", s).strip()
        if _has_any_visible_outside_status(cand) or re.match(r"^\s*<think(?:ing)?>", s, flags=re.IGNORECASE):
            s = cand
        else:
            s = re.sub(r"(?<!`)</?think(?:ing)?>(?!`)", "", s, flags=re.IGNORECASE)
    return s.strip()


def _extract_msg_plain_text(msg: Dict[str, Any]) -> str:
    if not isinstance(msg, dict):
        return ""
    raw_c = msg.get("content")
    if isinstance(raw_c, str):
        return raw_c
    if isinstance(raw_c, list):
        return "\n".join(
            str(p.get("text") or "")
            for p in raw_c
            if isinstance(p, dict) and p.get("type") == "text" and p.get("text")
        )
    return "" if raw_c is None else str(raw_c)


def _match_wb_single_key(key_str: str, haystack: str, haystack_low: str, case_sensitive: bool, force_regex: bool = False) -> bool:
    if not key_str:
        return False
    is_slash_regex = len(key_str) >= 2 and key_str.startswith("/") and bool(re.search(r"/[a-zA-Z]*$", key_str))
    if force_regex or is_slash_regex:
        try:
            default_fl = 0 if case_sensitive else re.IGNORECASE
            compiled, _ = _compile_st_or_py_regex(key_str, default_flags=default_fl)
            return bool(compiled.search(haystack))
        except Exception:
            return False
    if case_sensitive:
        return key_str in haystack
    return key_str.lower() in haystack_low


def evaluate_world_book(
    project_data: Dict[str, Any],
    history_messages: List[Dict[str, Any]],
    current_user_text: str,
    system_prompt: str,
    prefix: str,
    suffix: str,
    chat_inputs: Dict[str, Any],
    visited_wb_ids: Optional[List[str]] = None,
    default_scan_depth: Optional[int] = None,
) -> Tuple[str, str, str, List[Dict[str, Any]]]:
    """
    评估动态世界书规则并注入到对应的影响范围 (1=System, 2=Prefix, 4=Suffix)，
    完整支持世界书全局扫描深度 (default_scan_depth)、酒馆次级条件词 (secondary_keys / selective_logic)、
    大小写敏感开关以及最多 3 层级联递归触发。
    返回: (final_system_prompt, final_prefix, final_suffix, triggered_logs)
    """
    wb_list = project_data.get("world_book") or []
    prompt_vars = project_data.get("prompt_variables") or []
    if not wb_list:
        return system_prompt, prefix, suffix, []

    if default_scan_depth is None:
        proj_cp = project_data.get("completion_params") if isinstance(project_data.get("completion_params"), dict) else {}
        default_scan = safe_int(proj_cp.get("worldbook_scan_depth"), 5)
    else:
        default_scan = safe_int(default_scan_depth, 5)
    default_scan = max(0, min(default_scan, 50))

    # 按 sort 升序排列 (0 ~ 9999)
    sorted_wb = sorted(
        [x for x in wb_list if isinstance(x, dict)],
        key=lambda x: safe_int(x.get("sort", x.get("insertion_order", x.get("order", 100))), 100),
    )
    triggered_logs: List[Dict[str, Any]] = []

    sys_injections: List[str] = []
    pre_injections: List[str] = []
    suf_injections: List[str] = []

    current_matched_ids = set()
    recursion_buffer: List[str] = []
    max_passes = 3

    for pass_idx in range(max_passes):
        newly_triggered_in_pass = False
        for idx, raw_item in enumerate(sorted_wb):
            item = normalize_worldbook_item(raw_item, idx)
            if not item.get("enable", True):
                continue
            item_id = str(item.get("id") or f"wb_idx_{idx}")
            if item_id in current_matched_ids:
                continue
            if pass_idx > 0 and item.get("exclude_recursion"):
                continue

            keys = item.get("keys") or []
            # 常驻词条（SillyTavern constant）无需关键词即可触发
            is_constant = bool(raw_item.get("constant") or item.get("constant"))
            if not keys and not is_constant:
                continue

            # 组装扫描深度内的文本池：优先词条显式 scan_depth，否则使用项目/全局 worldbook_scan_depth（兼容词条自定义非默认 depth）
            if raw_item.get("scan_depth") is not None or raw_item.get("scanDepth") is not None:
                raw_d = raw_item.get("scan_depth") if raw_item.get("scan_depth") is not None else raw_item.get("scanDepth")
                depth_turns = safe_int(raw_d, default_scan)
            elif "depth" in raw_item and safe_int(raw_item.get("depth"), 5) != 5:
                depth_turns = safe_int(raw_item.get("depth"), default_scan)
            else:
                depth_turns = default_scan
            depth_turns = max(0, min(depth_turns, 50))
            msg_slice = history_messages[-(depth_turns * 2):] if depth_turns > 0 else []

            key_region = safe_int(item.get("key_region", 6), 6)
            scan_chunks: List[str] = []
            if pass_idx == 0:
                if key_region & 1:  # System
                    scan_chunks.append(str(system_prompt or ""))
                if (key_region & 2) or (key_region & 16):  # User
                    scan_chunks.append(str(current_user_text or ""))
                    for m in msg_slice:
                        if isinstance(m, dict) and m.get("role") == "user":
                            scan_chunks.append(_extract_msg_plain_text(m))
                if (key_region & 4) or (key_region & 8):  # AI / History
                    for m in msg_slice:
                        if isinstance(m, dict) and m.get("role") == "assistant":
                            scan_chunks.append(strip_thinking_blocks(_extract_msg_plain_text(m)))
            else:
                scan_chunks.extend(recursion_buffer)

            haystack = "\n".join(c for c in scan_chunks if c)
            if not haystack.strip() and not (is_constant and pass_idx == 0):
                continue
            haystack_low = haystack.lower()
            case_sens = bool(item.get("case_sensitive", False))

            raw_mt = item.get("match_type", 2)
            if isinstance(raw_mt, str):
                mt_u = raw_mt.strip().upper()
                match_type = 1 if mt_u in ("1", "AND") else (3 if mt_u in ("3", "REGEX") else 2)
            else:
                match_type = safe_int(raw_mt, 2)
            matched = False
            matched_keyword = ""

            if is_constant and pass_idx == 0:
                matched = True
                matched_keyword = "（常驻）"
            elif match_type == 1:  # AND (所有主关键词同时出现)
                if keys and all(_match_wb_single_key(k, haystack, haystack_low, case_sens, False) for k in keys):
                    matched = True
                    matched_keyword = " & ".join(keys)
            elif match_type == 2:  # OR (任一主关键词出现)
                for k in keys:
                    if _match_wb_single_key(k, haystack, haystack_low, case_sens, False):
                        matched = True
                        matched_keyword = k
                        break
            elif match_type == 3:  # Regex
                for k in keys:
                    if _match_wb_single_key(k, haystack, haystack_low, case_sens, True):
                        matched = True
                        matched_keyword = k if k.startswith("/") else f"/{k}/"
                        break

            # 次级关键词过滤 (SillyTavern selective + keysecondary: 0=AND ANY, 1=NOT ALL, 2=NOT ANY, 3=AND ALL)
            sec_keys = item.get("secondary_keys") or []
            if matched and not is_constant and sec_keys and item.get("selective", True):
                sec_hits = [_match_wb_single_key(sk, haystack, haystack_low, case_sens, False) for sk in sec_keys]
                sel_logic = safe_int(item.get("selective_logic", 0), 0)
                if sel_logic == 0 and not any(sec_hits):
                    matched = False
                elif sel_logic == 1 and all(sec_hits):
                    matched = False
                elif sel_logic == 2 and any(sec_hits):
                    matched = False
                elif sel_logic == 3 and not all(sec_hits):
                    matched = False

            if not matched:
                continue

            # 触发概率判定 (0~100%)
            prob = max(0, min(safe_int(item.get("probability", 100), 100), 100))
            if prob <= 0 or (prob < 100 and random.randint(1, 100) > prob):
                continue

            # 选择注入内容：常规(0) vs 概率权重分支(1)
            chosen_value = ""
            if safe_int(item.get("value_type", 0), 0) == 1:
                configs = item.get("value_configs") or []
                valid_cfgs = [
                    c for c in configs
                    if isinstance(c, dict)
                    and c.get("value")
                    and safe_float(c.get("probability") if c.get("probability") is not None else c.get("weight"), 0.0) > 0
                ]
                if valid_cfgs:
                    weights = [safe_float(c.get("probability") if c.get("probability") is not None else c.get("weight"), 10.0) for c in valid_cfgs]
                    if sum(weights) > 0:
                        picked = random.choices(valid_cfgs, weights=weights, k=1)[0]
                        chosen_value = str(picked.get("value") or "")
            if not chosen_value:
                chosen_value = str(item.get("content") if item.get("content") is not None else (item.get("value") or ""))

            chosen_value = interpolate_variables(chosen_value.strip(), prompt_vars, chat_inputs)
            if not chosen_value:
                continue

            current_matched_ids.add(item_id)
            newly_triggered_in_pass = True
            recursion_buffer.append(chosen_value)
            if visited_wb_ids is not None and item_id not in visited_wb_ids:
                visited_wb_ids.append(item_id)

            raw_vr = item.get("value_region", 1)
            if isinstance(raw_vr, str):
                vr_u = raw_vr.strip().upper()
                if vr_u.isdigit():
                    val_region = int(vr_u) or 1
                else:
                    val_region = 2 if vr_u == "PREFIX" else (4 if vr_u == "SUFFIX" else 1)
            else:
                val_region = safe_int(raw_vr, 1) or 1
            target_names = []
            if (val_region & 1) or (val_region & 8) or (val_region & 16):
                sys_injections.append(chosen_value)
                target_names.append("系统提示词")
            if val_region & 2:
                pre_injections.append(chosen_value)
                target_names.append("前置词")
            if val_region & 4:
                suf_injections.append(chosen_value)
                target_names.append("后置词")

            triggered_logs.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "group": item.get("group"),
                "keys": keys,
                "matched_keyword": matched_keyword if pass_idx == 0 else f"{matched_keyword} (级联#{pass_idx})",
                "value_region": val_region,
                "target_regions": target_names,
                "sort": item.get("sort"),
                "content_preview": chosen_value[:160] + ("..." if len(chosen_value) > 160 else "")
            })

        if not newly_triggered_in_pass:
            break

    final_sys = system_prompt
    if sys_injections:
        wb_block = "\n\n【动态触发的世界书设定 (Worldbook Lore)】\n" + "\n\n".join(sys_injections)
        final_sys = (final_sys + wb_block).strip()

    final_pre = "\n".join(pre_injections + ([prefix] if prefix else [])).strip()
    final_suf = "\n".join(([suffix] if suffix else []) + suf_injections).strip()

    return final_sys, final_pre, final_suf, triggered_logs

def evaluate_cg_book(project_data: Dict[str, Any], text_to_scan: str) -> Tuple[List[Dict[str, Any]], bool]:
    """扫描最新消息中的关键词，触发并解锁对应的 CG 图鉴"""
    cg_list = project_data.get("cg_book") or []
    if not isinstance(cg_list, list) or not cg_list or not text_to_scan:
        return [], False

    triggered_cgs: List[Dict[str, Any]] = []
    updated_flag = False
    lower_text = text_to_scan.lower()

    for cg in cg_list:
        if not isinstance(cg, dict):
            continue
        raw_keys = cg.get("keys") if cg.get("keys") is not None else cg.get("keywords", [])
        if isinstance(raw_keys, str):
            keys = [k.strip() for k in re.split(r"[,，;；@wb@\n]+", raw_keys) if k.strip()]
        elif isinstance(raw_keys, list):
            keys = [str(k).strip() for k in raw_keys if str(k).strip()]
        else:
            keys = []

        if not keys:
            continue

        if any(k.lower() in lower_text for k in keys):
            img_url = cg.get("image_url") or cg.get("url") or ""
            if safe_int(cg.get("value_type", 0), 0) == 1:
                cfgs = [
                    c for c in (cg.get("image_configs") or [])
                    if isinstance(c, dict) and (c.get("image_url") or c.get("url"))
                ]
                if cfgs:
                    weights = [max(0.0, safe_float(c.get("probability"), 50.0)) for c in cfgs]
                    if sum(weights) <= 0:
                        weights = [1.0 for _ in cfgs]
                    picked = random.choices(cfgs, weights=weights, k=1)[0]
                    img_url = picked.get("image_url") or picked.get("url") or img_url
            if img_url:
                if not cg.get("unlocked"):
                    cg["unlocked"] = True
                    updated_flag = True
                cg_name = cg.get("name") or cg.get("title") or "剧情CG插画"
                cg_hint = cg.get("unlock_hint") or cg.get("description") or ""
                triggered_cgs.append({
                    "id": cg.get("id"),
                    "name": cg_name,
                    "title": cg_name,
                    "image_url": img_url,
                    "unlock_hint": cg_hint
                })

    return triggered_cgs, updated_flag

# ==================== 生成高品质 SVG 预览插画（用于内置CG与AI生图演示兜底） ====================
def generate_stylized_svg_card(title: str, subtitle: str, theme_colors: Tuple[str, str] = ("#312e81", "#1e1b4b")) -> str:
    c1, c2 = theme_colors
    safe_title = (title or "CG 插画")[:24].replace("<", "").replace(">", "")
    safe_sub = (subtitle or "")[:48].replace("<", "").replace(">", "")
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="800" height="480" viewBox="0 0 800 480">
      <defs>
        <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="{c1}"/>
          <stop offset="55%" stop-color="{c2}"/>
          <stop offset="100%" stop-color="#090b14"/>
        </linearGradient>
        <radialGradient id="glow" cx="70%" cy="30%" r="50%">
          <stop offset="0%" stop-color="#818cf8" stop-opacity="0.45"/>
          <stop offset="100%" stop-color="#6366f1" stop-opacity="0"/>
        </radialGradient>
      </defs>
      <rect width="800" height="480" fill="url(#bg)"/>
      <circle cx="560" cy="140" r="240" fill="url(#glow)"/>
      <circle cx="580" cy="120" r="68" fill="#fef08a" fill-opacity="0.18"/>
      <circle cx="580" cy="120" r="46" fill="#fef9c3" fill-opacity="0.32"/>
      <path d="M0 360 Q 220 290 420 350 T 800 320 L 800 480 L 0 480 Z" fill="#0f172a" fill-opacity="0.75"/>
      <path d="M0 400 Q 300 340 550 390 T 800 370 L 800 480 L 0 480 Z" fill="#090d16" fill-opacity="0.92"/>
      <rect x="36" y="36" width="728" height="408" rx="18" fill="none" stroke="#818cf8" stroke-opacity="0.35" stroke-width="1.5"/>
      <text x="64" y="392" fill="#ffffff" font-family="sans-serif" font-size="26" font-weight="700">{safe_title}</text>
      <text x="64" y="422" fill="#94a3b8" font-family="sans-serif" font-size="15">{safe_sub}</text>
    </svg>"""
    return svg

# ==================== 构建企业级扩展 APIRouter ====================
def create_enterprise_router(
    get_current_user,
    get_user_dir,
    get_user_projects_dir,
    get_user_chats_dir,
    get_user_gallery_dir,
    load_user_settings,
    save_user_settings,
    auto_save_to_gallery
) -> APIRouter:
    router = APIRouter()

    # 1. 新建游戏(高级)列表：返回用户现有游戏与预设模板
    @router.get("/api/explore")
    def list_explore_apps(request: Request, category: Optional[str] = None, q: Optional[str] = None):
        username = get_current_user(request)
        settings = load_user_settings(username)
        proj_dir = get_user_projects_dir(username)
        user_projects = []
        for p in sorted(proj_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                norm = normalize_project_schema(raw, raw, global_defaults=settings)
                norm["_is_user_project"] = True
                user_projects.append(norm)
            except Exception:
                pass

        results = list(EXPLORE_PRESET_APPS)
        if category and category != "全部":
            results = [a for a in results if a.get("category") == category]
        if q and q.strip():
            kw = q.strip().lower()
            results = [
                a for a in results
                if kw in a.get("name", "").lower()
                or kw in a.get("description", "").lower()
                or any(kw in t.lower() for t in a.get("tags", []))
            ]
        return {
            "status": "ok",
            "categories": ["全部", "我的剧本", "奇幻冒险", "悬疑克苏鲁", "赛博朋克", "古风仙侠", "TRPG跑团", "都市日常"],
            "user_projects": user_projects,
            "apps": results
        }

    @router.get("/api/explore/cg_preview/{cg_key}")
    def get_explore_cg_preview(cg_key: str):
        if cg_key == "cg_saintess":
            svg = generate_stylized_svg_card("雨夜酒馆的戒备圣女 · 希尔薇娅", "生锈齿轮酒馆 · 银发圣女拔匕相向的初遇瞬间", ("#1e1b4b", "#31102f"))
        elif cg_key in ("cg_cathedral", "cg_chapel"):
            svg = generate_stylized_svg_card("星环大圣堂的月下誓约", "浮空晶石月光洒落在圣洁白银祭坛之上", ("#0f172a", "#1e3a8a"))
        else:
            svg = generate_stylized_svg_card("剧情专属 CG 插画", f"CG ID: {cg_key}", ("#1e1b4b", "#0f172a"))
        return Response(content=svg, media_type="image/svg+xml")

    @router.post("/api/explore/install")
    def install_explore_app(payload: Dict[str, Any], request: Request):
        username = get_current_user(request)
        app_id = payload.get("app_id")
        template = next((a for a in EXPLORE_PRESET_APPS if a["id"] == app_id), None)
        if not template:
            raise HTTPException(status_code=404, detail="模板不存在")

        proj_dir = get_user_projects_dir(username)
        target_id = template["id"]
        proj_file = proj_dir / f"{target_id}.json"
        norm_proj = normalize_project_schema(template)
        atomic_write_json(proj_file, norm_proj, ensure_ascii=False, indent=2)

        settings = load_user_settings(username)
        settings["active_project_id"] = target_id
        save_user_settings(username, settings)

        # 若该游戏下尚无对话，自动创建一个带有开场白的首个对话
        chats_dir = get_user_chats_dir(username)
        has_chat = False
        first_chat_id = None
        for p in chats_dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as _cf:
                    cdata = json.load(_cf)
                if cdata.get("project_id") == target_id:
                    has_chat = True
                    first_chat_id = cdata.get("id")
                    break
            except Exception:
                pass

        if not has_chat:
            first_chat_id = str(uuid.uuid4())[:8]
            now = time.time()
            init_msgs = []
            if norm_proj.get("opening_statement"):
                init_msgs.append({
                    "id": "msg_opening",
                    "role": "assistant",
                    "content": norm_proj["opening_statement"],
                    "is_opening": True,
                    "suggested_questions": norm_proj.get("suggested_questions", []),
                    "timestamp": now
                })
            new_chat = {
                "id": first_chat_id,
                "title": f"{norm_proj['name'][:12]} · 初章",
                "project_id": target_id,
                "model": settings.get("model", ""),
                "summary": "",
                "inputs": {
                    (v.get("key") or v.get("name")): v.get("default", "")
                    for v in norm_proj.get("prompt_variables", [])
                    if isinstance(v, dict) and (v.get("key") or v.get("name"))
                },
                "created_at": now,
                "updated_at": now,
                "messages": init_msgs
            }
            atomic_write_json(chats_dir / f"{first_chat_id}.json", new_chat, ensure_ascii=False, indent=2)

        return {"status": "ok", "project": norm_proj, "chat_id": first_chat_id, "chat": {"id": first_chat_id}}

    # 2. 世界书模板下载与批量导入/导出
    @router.get("/api/worldbook/template")
    def download_worldbook_template():
        content = json.dumps(WORLDBOOK_TEMPLATE_JSON, ensure_ascii=False, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=worldbook_template.json"}
        )

    def _safe_id(raw_id: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "", str(raw_id or "").strip())
        if not cleaned:
            raise HTTPException(status_code=400, detail="非法 ID")
        return cleaned

    @router.post("/api/projects/{project_id}/worldbook/import")
    def import_worldbook_json(project_id: str, payload: Dict[str, Any], request: Request):
        username = get_current_user(request)
        safe_proj_id = _safe_id(project_id)
        proj_file = get_user_projects_dir(username) / f"{safe_proj_id}.json"
        if not proj_file.exists():
            raise HTTPException(status_code=404, detail="剧本不存在")

        with open(proj_file, "r", encoding="utf-8") as f:
            _raw_proj = json.load(f)
            proj = normalize_project_schema(_raw_proj, _raw_proj)

        raw_data = payload.get("data", payload)
        entries_to_add = []
        if isinstance(raw_data, list):
            entries_to_add = raw_data
        elif isinstance(raw_data, dict):
            if isinstance(raw_data.get("world_book"), list):
                entries_to_add = raw_data["world_book"]
            elif isinstance(raw_data.get("entries"), dict):
                # 完整兼容 SillyTavern Lorebook JSON 格式（保留 keysecondary / selectiveLogic / caseSensitive / position / uid）
                for k, v in raw_data["entries"].items():
                    if isinstance(v, dict):
                        st_entry = dict(v)
                        st_entry.setdefault("name", v.get("comment") or v.get("name") or f"词条 #{k}")
                        entries_to_add.append(st_entry)
            elif isinstance(raw_data.get("entries"), list):
                entries_to_add = [x for x in raw_data["entries"] if isinstance(x, dict)]
            elif raw_data.get("keys") is not None or raw_data.get("key") is not None or raw_data.get("content") is not None or raw_data.get("value") is not None:
                entries_to_add = [raw_data]

        if not entries_to_add:
            raise HTTPException(status_code=400, detail="未识别到世界书条目（需含 world_book 数组）")

        mode = payload.get("mode", "append")  # append | replace
        normalized_new = [normalize_worldbook_item(item, i) for i, item in enumerate(entries_to_add)]
        if mode == "replace":
            proj["world_book"] = normalized_new
        else:
            proj["world_book"].extend(normalized_new)

        for w in proj["world_book"]:
            g = w.get("group") or "默认分类"
            if g not in proj["world_book_groups"]:
                proj["world_book_groups"].append(g)

        proj["updated_at"] = time.time()
        atomic_write_json(proj_file, proj, ensure_ascii=False, indent=2)

        return {"status": "ok", "imported_count": len(normalized_new), "project": proj}

    # 3. 模型实时连通性与延迟测速 API (`测试模型`) & 收藏模型
    @router.post("/api/models/test")
    async def test_model_connectivity(payload: Dict[str, Any], request: Request):
        username = get_current_user(request)
        settings = load_user_settings(username)
        model_id = (payload.get("model") or settings.get("model") or "").strip()
        if not model_id:
            return {
                "status": "fail",
                "ok": False,
                "model": "",
                "latency_ms": 0,
                "health": "未配置",
                "error": "请先配置模型"
            }
        ep = resolve_model_endpoint(model_id, settings)
        if ep["is_local"]:
            local_err = await ensure_local_engine_ready(model_id)
            ep = resolve_model_endpoint(model_id, settings)
            if local_err:
                return {
                    "status": "fail",
                    "ok": False,
                    "model": model_id,
                    "latency_ms": 0,
                    "health": "引擎异常",
                    "error": local_err,
                }

        proxy = ep["proxy"]
        base_url = ep["base_url"]
        api_key = ep["api_key"]
        upstream_model = ep["upstream_model"]

        t0 = time.time()
        first_token_ms = None
        collected = []
        proxy_candidates = [proxy, None] if proxy else [None]
        last_err = None
        read_timeout = 35.0 if ep["is_local"] else 18.0

        test_body: Dict[str, Any] = {
            "model": upstream_model,
            "messages": [{"role": "user", "content": "请回复OK"}],
            "max_tokens": 24,
            "temperature": 0.1,
            "stream": True
        }
        if ep["is_local"]:
            if ep["engine"] == "ollama":
                test_body["think"] = False
                test_body["options"] = {"num_ctx": get_optimal_ollama_num_ctx()}
            elif ep["engine"] == "strata":
                test_body["reasoning_effort"] = "low"
                test_body["reasoning_budget_tokens"] = 0

        for cur_proxy in proxy_candidates:
            try:
                async with httpx.AsyncClient(proxy=cur_proxy, trust_env=False, timeout=httpx.Timeout(read_timeout, connect=10.0)) as client:
                    async with client.stream(
                        "POST",
                        f"{base_url}/chat/completions",
                        headers=ep.get("headers") or {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json=test_body
                    ) as resp:
                        if resp.status_code != 200:
                            err_body = (await resp.aread()).decode("utf-8", errors="ignore")[:160]
                            last_err = f"HTTP {resp.status_code}: {err_body}"
                            continue
                        async for line in resp.aiter_lines():
                            line = line.strip()
                            if line.startswith("data:"):
                                raw_d = line[5:].lstrip()
                                if not raw_d or raw_d == "[DONE]":
                                    continue
                                try:
                                    d = json.loads(raw_d)
                                    if isinstance(d, dict) and d.get("error"):
                                        err_obj = d["error"]
                                        last_err = err_obj.get("message", str(err_obj)) if isinstance(err_obj, dict) else str(err_obj)
                                        continue
                                    if first_token_ms is None:
                                        first_token_ms = int((time.time() - t0) * 1000)
                                    delta = (d.get("choices") or [{}])[0].get("delta", {})
                                    c = delta.get("content") or delta.get("reasoning_content") or delta.get("reasoning") or ""
                                    if c:
                                        collected.append(c)
                                except Exception:
                                    pass
                        if first_token_ms is not None or collected:
                            break
            except Exception as e:
                last_err = str(e) or type(e).__name__

        total_ms = int((time.time() - t0) * 1000)
        if first_token_ms is not None or collected:
            ft = first_token_ms or total_ms
            health = "本地" if ep["is_local"] else ("正常" if ft < 4500 else "延迟较高")
            reply_sample = strip_thinking_blocks("".join(collected))[:40] or "OK"
            return {
                "status": "ok",
                "ok": True,
                "model": model_id,
                "first_token_ms": ft,
                "latency_ms": ft,
                "total_ms": total_ms,
                "health": health,
                "sample": reply_sample,
                "reply": reply_sample
            }
        return {
            "status": "fail",
            "ok": False,
            "model": model_id,
            "latency_ms": total_ms,
            "health": "异常",
            "error": last_err or "无返回数据"
        }

    @router.post("/api/models/favorite")
    def toggle_favorite_model(payload: Dict[str, Any], request: Request):
        username = get_current_user(request)
        model_id = payload.get("model")
        if not model_id:
            raise HTTPException(status_code=400, detail="缺少模型 ID")
        settings = load_user_settings(username)
        favs = list(settings.get("favorite_models", []))
        if model_id in favs:
            favs.remove(model_id)
            is_fav = False
        else:
            favs.insert(0, model_id)
            is_fav = True
        settings["favorite_models"] = favs
        save_user_settings(username, settings)
        return {"status": "ok", "model": model_id, "is_favorite": is_fav, "favorite_models": favs}

    # 4. 对话分支创建 (`创建分支对话`)、Prompt Log 调试器与对话存档导入导出
    @router.post("/api/chats/{chat_id}/branch")
    def create_chat_branch(chat_id: str, payload: Dict[str, Any], request: Request):
        username = get_current_user(request)
        safe_chat_id = _safe_id(chat_id)
        chats_dir = get_user_chats_dir(username)
        src_file = chats_dir / f"{safe_chat_id}.json"
        if not src_file.exists():
            raise HTTPException(status_code=404, detail="源对话不存在")

        with open(src_file, "r", encoding="utf-8") as f:
            src_data = json.load(f)

        up_to_msg_id = payload.get("up_to_msg_id") or payload.get("message_id") or payload.get("msg_id")
        all_msgs = src_data.get("messages", [])
        msgs = all_msgs
        if up_to_msg_id:
            idx = next((i for i, m in enumerate(all_msgs) if isinstance(m, dict) and m.get("id") == up_to_msg_id), -1)
            if idx == -1:
                raise HTTPException(status_code=404, detail="指定的分支起点消息不存在")
            msgs = all_msgs[:idx + 1]

        orig_sum_cnt = max(0, safe_int(src_data.get("summarized_count", 0), 0))
        if len(msgs) < orig_sum_cnt:
            # 当分支回退到了已归档总结范围之前时，清空未来剧透总结并完整保留早期原文上下文
            branch_summary = ""
            branch_sum_cnt = 0
        else:
            branch_summary = src_data.get("summary", "")
            branch_sum_cnt = orig_sum_cnt

        new_id = str(uuid.uuid4())[:8]
        now = time.time()
        branch_title = payload.get("title") or f"{src_data.get('title', '对话')[:12]} (分支)"
        cloned_inputs = json.loads(json.dumps(src_data.get("inputs", src_data.get("variables", {})) or {}))
        new_chat = {
            "id": new_id,
            "title": branch_title,
            "project_id": src_data.get("project_id", "proj_default"),
            "model": src_data.get("model", ""),
            "summary": branch_summary,
            "summarized_count": branch_sum_cnt,
            "inputs": cloned_inputs,
            "variables": dict(cloned_inputs),
            "parent_chat_id": safe_chat_id,
            "created_at": now,
            "updated_at": now,
            "messages": json.loads(json.dumps(msgs))
        }
        atomic_write_json(chats_dir / f"{new_id}.json", new_chat, ensure_ascii=False, indent=2)

        return {"status": "ok", "chat": new_chat}

    @router.get("/api/chats/{chat_id}/prompt_log")
    def get_chat_prompt_log(chat_id: str, request: Request):
        username = get_current_user(request)
        safe_chat_id = _safe_id(chat_id)
        chat_file = get_user_chats_dir(username) / f"{safe_chat_id}.json"
        if not chat_file.exists():
            raise HTTPException(status_code=404, detail="对话不存在")
        with open(chat_file, "r", encoding="utf-8") as f:
            cdata = json.load(f)
        return {
            "status": "ok",
            "chat_id": safe_chat_id,
            "prompt_log": cdata.get("last_prompt_log") or {
                "timestamp": cdata.get("updated_at", time.time()),
                "model": cdata.get("model"),
                "triggered_worldbooks": [],
                "applied_regex": [],
                "assembled_messages": []
            }
        }

    @router.post("/api/chats/import")
    def import_chat_archive(payload: Any, request: Request):
        username = get_current_user(request)
        chats_dir = get_user_chats_dir(username)
        settings = load_user_settings(username)
        if isinstance(payload, list):
            raw: Any = {"messages": payload}
            outer_proj_id = None
        elif isinstance(payload, dict):
            raw = payload.get("chat", payload)
            outer_proj_id = payload.get("project_id")
        else:
            raise HTTPException(status_code=400, detail="非法的对话存档格式")
        if isinstance(raw, list):
            raw = {"messages": raw}
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="非法的对话存档内容")
        new_id = str(uuid.uuid4())[:8]
        now = time.time()
        raw_proj_id = outer_proj_id or raw.get("project_id") or settings.get("active_project_id", "proj_default")
        raw_msgs = raw.get("messages") if isinstance(raw.get("messages"), list) else []
        chat_data = {
            "id": new_id,
            "title": raw.get("title") or f"导入存档 ({time.strftime('%m-%d %H:%M')})",
            "project_id": _safe_id(raw_proj_id),
            "model": raw.get("model") or settings.get("model", ""),
            "summary": raw.get("summary", ""),
            "summarized_count": max(0, min(safe_int(raw.get("summarized_count"), 0), len(raw_msgs))),
            "inputs": raw.get("inputs", {}) if isinstance(raw.get("inputs"), dict) else {},
            "created_at": now,
            "updated_at": now,
            "messages": raw_msgs
        }
        atomic_write_json(chats_dir / f"{new_id}.json", chat_data, ensure_ascii=False, indent=2)
        return {"status": "ok", "chat": chat_data}

    # 5. 图库文件夹管理
    @router.get("/api/gallery/folders")
    def get_gallery_folders(request: Request):
        username = get_current_user(request)
        fpath = get_user_dir(username) / "gallery_folders.json"
        default_folders = [
            {"id": "默认图库", "name": "默认图库", "system": True},
            {"id": "角色立绘", "name": "角色立绘", "system": False},
            {"id": "场景CG", "name": "场景CG", "system": False},
            {"id": "道具线索", "name": "道具线索", "system": False}
        ]
        if fpath.exists():
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    return {"status": "ok", "folders": json.load(f)}
            except Exception:
                pass
        atomic_write_json(fpath, default_folders, ensure_ascii=False, indent=2)
        return {"status": "ok", "folders": default_folders}

    @router.post("/api/gallery/folders")
    def create_gallery_folder(payload: Dict[str, Any], request: Request):
        username = get_current_user(request)
        name = (payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="名称不能为空")
        fpath = get_user_dir(username) / "gallery_folders.json"
        folders = get_gallery_folders(request)["folders"]
        if any(f.get("name") == name for f in folders):
            raise HTTPException(status_code=400, detail="文件夹已存在")
        new_folder = {"id": name, "name": name, "system": False}
        folders.append(new_folder)
        atomic_write_json(fpath, folders, ensure_ascii=False, indent=2)
        return {"status": "ok", "folder": new_folder, "folders": folders}

    @router.post("/api/gallery/move")
    def move_gallery_images(payload: Dict[str, Any], request: Request):
        username = get_current_user(request)
        img_ids = set(payload.get("image_ids") or [])
        folder_id = payload.get("folder_id") or payload.get("folder") or "默认图库"
        gfile = get_user_dir(username) / "gallery.json"
        if gfile.exists():
            with open(gfile, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                if item.get("id") in img_ids:
                    item["folder"] = folder_id
                    item["folder_id"] = folder_id
            atomic_write_json(gfile, data, ensure_ascii=False, indent=2)
        return {"status": "ok"}

    # 6. 沿用复制游戏 (/api/projects/fork) 与 AI 润色 (/api/ai/polish)
    @router.post("/api/projects/fork")
    def fork_project_to_new(payload: Dict[str, Any], request: Request):
        username = get_current_user(request)
        settings = load_user_settings(username)
        proj_dir = get_user_projects_dir(username)

        src_proj = payload.get("project")
        src_id = payload.get("source_id") or payload.get("source_project_id")
        if not isinstance(src_proj, dict) and src_id:
            safe_sid = _safe_id(src_id)
            pfile = proj_dir / f"{safe_sid}.json"
            if pfile.exists():
                with open(pfile, "r", encoding="utf-8") as f:
                    src_proj = json.load(f)
            else:
                src_proj = next((a for a in EXPLORE_PRESET_APPS if a["id"] == src_id), None)

        if not isinstance(src_proj, dict):
            src_proj = {
                "name": payload.get("new_name") or "新剧本",
                "icon": "🎲",
                "description": "",
                "tags": [],
                "opening_greetings": [],
                "opening_statement": "",
                "prefix": "",
                "system_prompt": "",
                "suffix": "",
                "system_protocol_prompt": "",
                "ui_modules": [],
                "status_panel_enabled": True,
            }

        cloned = json.loads(json.dumps(src_proj))
        if not src_id and "ui_modules" not in cloned:
            cloned["ui_modules"] = []
        if not src_id and "system_protocol_prompt" not in cloned:
            cloned["system_protocol_prompt"] = ""
        new_id = f"proj_{uuid.uuid4().hex[:8]}"
        cloned["id"] = new_id
        if payload.get("new_name"):
            cloned["name"] = str(payload["new_name"]).strip()
        elif not payload.get("keep_exact_name"):
            base_name = (cloned.get("name") or "未命名剧本").strip()
            cloned["name"] = base_name
        norm_proj = normalize_project_schema(cloned, cloned, global_defaults=settings)
        norm_proj["id"] = new_id

        atomic_write_json(proj_dir / f"{new_id}.json", norm_proj, ensure_ascii=False, indent=2)

        settings["active_project_id"] = new_id
        save_user_settings(username, settings)

        chats_dir = get_user_chats_dir(username)
        first_chat_id = str(uuid.uuid4())[:8]
        now = time.time()
        init_msgs: List[Dict[str, Any]] = []
        if norm_proj.get("opening_statement"):
            init_msgs.append({
                "id": "msg_opening",
                "role": "assistant",
                "content": norm_proj["opening_statement"],
                "is_opening": True,
                "suggested_questions": norm_proj.get("suggested_questions", []),
                "timestamp": now
            })
        new_chat = {
            "id": first_chat_id,
            "title": f"{norm_proj['name'][:12]} · 新对话",
            "project_id": new_id,
            "model": settings.get("model", ""),
            "summary": "",
            "inputs": {
                (v.get("key") or v.get("name")): v.get("default", "")
                for v in norm_proj.get("prompt_variables", [])
                if isinstance(v, dict) and (v.get("key") or v.get("name"))
            },
            "created_at": now,
            "updated_at": now,
            "messages": init_msgs
        }
        atomic_write_json(chats_dir / f"{first_chat_id}.json", new_chat, ensure_ascii=False, indent=2)

        return {"status": "ok", "project": norm_proj, "chat_id": first_chat_id}

    @router.post("/api/ai/polish")
    @router.post("/api/ai/polish_prompt")
    async def ai_polish_project_field(payload: Dict[str, Any], request: Request):
        username = get_current_user(request)
        settings = load_user_settings(username)
        raw_text = (payload.get("text") or "").strip()
        field_type = (payload.get("field_type") or "system_prompt").strip()
        instruction = (payload.get("instruction") or "").strip()
        project_name = (payload.get("project_name") or "跑团游戏").strip()
        model_id = (payload.get("model") or settings.get("model") or "").strip()
        if not model_id:
            raise HTTPException(status_code=400, detail="请先选择模型")

        field_labels = {
            "system_prompt": "提示词 (System Prompt，包含世界观规则、角色设定、叙事文风与DM主持准则)",
            "opening_statement": "跑团开场白 (Opening Statement，富有画面感与代入感的首段场景描写)",
            "opening_greeting": "游戏开场白 (Opening Greeting，玩家新建对话后一键发送或修改后发送的初始开局指令/剧情切入点)",
            "description": "游戏简介 (简明扼要、吸引人的游戏核心概览)",
            "prefix": "前置提示词 (Prefix，附加在玩家每次输入前的引导指令)",
            "suffix": "后置提示词 (Suffix，附加在玩家每次输入后的核心约束指令)",
            "worldbook": "世界书词条设定 (Worldbook Entry，触发后注入给AI的设定细节)"
        }
        field_desc = field_labels.get(field_type, "游戏设定文本")

        sys_msg = (
            "你是一位专业的 TRPG 跑团与互动叙事游戏编辑。请直接输出润色或扩写后的最终文本内容，"
            "不要输出任何寒暄、解释、前言、总结或 Markdown 代码块包裹符号。"
        )
        user_msg = f"游戏名称：{project_name}\n当前润色栏目：{field_desc}\n"
        if instruction:
            user_msg += f"用户特别润色/修改要求：{instruction}\n"
        if raw_text:
            user_msg += f"\n原始文本内容：\n{raw_text}\n\n请对以上内容进行润色优化（使其逻辑更清晰、表现力更强、更适合作为高质量AI跑团/角色扮演设定），直接输出润色后的正文："
        else:
            user_msg += f"\n当前内容为空，请根据游戏名称「{project_name}」与栏目定位（{field_desc}），直接创作一段高质量设定正文："

        ep = resolve_model_endpoint(model_id, settings)
        if ep["is_local"]:
            local_err = await ensure_local_engine_ready(model_id)
            ep = resolve_model_endpoint(model_id, settings)
            if local_err:
                raise HTTPException(status_code=502, detail=local_err)

        proxy = ep["proxy"]
        base_url = ep["base_url"]
        api_key = ep["api_key"]
        upstream_model = ep["upstream_model"]
        proxy_candidates = [proxy, None] if proxy else [None]
        collected = []
        read_timeout = 120.0 if ep["is_local"] else 60.0

        req_json: Dict[str, Any] = {
            "model": upstream_model,
            "messages": [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg}
            ],
            "max_tokens": 4096,
            "temperature": 0.68,
            "stream": True
        }
        if ep.get("protocol") not in ("claude", "gemini"):
            req_json["presence_penalty"] = 0.25
        if ep["is_local"]:
            if ep["engine"] == "strata":
                req_json["reasoning_effort"] = "low"
                req_json["reasoning_budget_tokens"] = 256
                req_json["repetition_penalty"] = 1.08
                req_json["penalty_last_n"] = 2048
                req_json["presence_penalty"] = 0.45
                req_json["frequency_penalty"] = 0.12
            elif ep["engine"] == "ollama":
                req_json["think"] = False
                req_json["presence_penalty"] = 0.45
                req_json["frequency_penalty"] = 0.12
                req_json["options"] = {
                    "repeat_penalty": 1.08,
                    "repeat_last_n": 2048,
                    "num_ctx": get_optimal_ollama_num_ctx(),
                }

        last_err = ""
        for cur_proxy in proxy_candidates:
            try:
                async with httpx.AsyncClient(proxy=cur_proxy, trust_env=False, timeout=httpx.Timeout(read_timeout, connect=10.0)) as client:
                    async with client.stream(
                        "POST",
                        f"{base_url}/chat/completions",
                        headers=ep.get("headers") or {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json=req_json
                    ) as resp:
                        if resp.status_code != 200:
                            err_body = (await resp.aread()).decode("utf-8", errors="ignore")[:240]
                            last_err = f"HTTP {resp.status_code}: {err_body}"
                            continue
                        async for line in resp.aiter_lines():
                            line = line.strip()
                            if line.startswith("data:"):
                                raw_d = line[5:].lstrip()
                                if not raw_d or raw_d == "[DONE]":
                                    continue
                                try:
                                    d = json.loads(raw_d)
                                    if isinstance(d, dict) and d.get("error"):
                                        err_obj = d["error"]
                                        last_err = err_obj.get("message", str(err_obj)) if isinstance(err_obj, dict) else str(err_obj)
                                        continue
                                    delta = (d.get("choices") or [{}])[0].get("delta", {})
                                    c = delta.get("content") or ""
                                    if c:
                                        collected.append(c)
                                except Exception:
                                    pass
                        if collected:
                            break
            except Exception as e:
                last_err = str(e) or type(e).__name__
                continue

        polished = strip_thinking_blocks("".join(collected))

        if not polished:
            raise HTTPException(
                status_code=502,
                detail=f"AI 润色请求失败：{last_err or '模型未返回有效文本，请检查 API 地址、密钥或模型状态'}"
            )

        return {"status": "ok", "polished_text": polished}

    # ==================== 7. 整合包本地模型管家：model文件夹直载、指定外部路径挂载、原生文件选择器与 HF 断点续传下载器 ====================
    # 原生文件/文件夹选择器 _native_pick_file_or_folder 已提升为模块级函数（带全局互斥锁，供 server.py 备份文件夹选择复用）

    def _build_hf_catalog_with_status(custom_paths: List[str]) -> List[Dict[str, Any]]:
        out_catalog: List[Dict[str, Any]] = []
        for item in HF_PRESET_CATALOG:
            entry = dict(item)
            raw_files = entry.get("files") or []
            enriched_files: List[Dict[str, Any]] = []
            for f in raw_files:
                f_copy = dict(f)
                fpath = str(f_copy.get("path") or f_copy.get("filename") or "")
                f_copy["path"] = fpath
                f_copy["filename"] = fpath
                loc = _locate_gguf_anywhere(Path(fpath).name, custom_paths) if fpath else None
                f_copy["exists"] = bool(loc and loc.exists())
                f_copy["local_path"] = str(loc) if (loc and loc.exists()) else ""
                enriched_files.append(f_copy)
            entry["files"] = enriched_files
            total_bytes = sum(int(f.get("size") or 0) for f in enriched_files)
            entry["total_bytes"] = total_bytes
            entry["total_gb"] = round(total_bytes / (1024 ** 3), 2)
            main_files = [f for f in enriched_files if "mmproj" not in str(f.get("path") or "").lower()]
            found_main = [f["local_path"] for f in main_files if f.get("exists") and f.get("local_path")]
            entry["installed"] = bool(main_files and len(found_main) == len(main_files))
            entry["all_ready"] = entry["installed"]
            entry["installed_path"] = found_main[0] if found_main else ""
            out_catalog.append(entry)
        return out_catalog

    def _is_secondary_shard_gguf(fname_lower: str) -> bool:
        m = re.search(r"-(\d{5})-of-(\d{5})\.gguf$", fname_lower)
        return bool(m and int(m.group(1)) != 1)

    def _has_valid_gguf_header(fpath: Path, min_bytes: int = 64) -> bool:
        try:
            if not fpath.exists() or fpath.stat().st_size < min_bytes:
                return False
            with open(fpath, "rb") as fh:
                return fh.read(4) == b"GGUF"
        except Exception:
            return False

    def _build_custom_paths_detail(custom_paths: List[str]) -> List[Dict[str, Any]]:
        details: List[Dict[str, Any]] = []
        for cp in custom_paths:
            p = Path(cp)
            exists = p.exists()
            ggufs = [
                g.name for g in _iter_gguf_in_path(p, max_depth=2)
                if "mmproj" not in g.name.lower() and not _is_secondary_shard_gguf(g.name.lower())
            ] if exists else []
            details.append({
                "path": cp,
                "name": p.name or cp,
                "exists": exists,
                "is_dir": p.is_dir() if exists else False,
                "gguf_count": len(ggufs),
                "gguf_names": ggufs[:6],
                "gguf_files": ggufs,
            })
        return details

    @router.get("/api/local_models/manager_status")
    async def get_local_models_manager_status(request: Request):
        username = get_current_user(request)
        settings = load_user_settings(username)
        primary_model_dir = _ensure_bundle_model_dirs()
        custom_paths = load_saved_custom_model_paths(settings.get("custom_model_paths"))
        # GET 接口保持纯只读：仅构建内存视图供探测使用，不在查询状态时写磁盘覆盖 settings.json
        view_settings = dict(settings)
        view_settings["custom_model_paths"] = custom_paths
        detected = await discover_local_models(view_settings)
        hf_catalog = await asyncio.to_thread(_build_hf_catalog_with_status, custom_paths)
        custom_detail = await asyncio.to_thread(_build_custom_paths_detail, custom_paths)
        return {
            "status": "ok",
            "bundle_model_dir": str(primary_model_dir),
            "model_folder": str(primary_model_dir),
            "models_folder": str(_BUNDLE_ROOT / "models"),
            "custom_paths": custom_detail,
            "detected_models": detected,
            "hf_catalog": hf_catalog,
            "downloads": list(HF_DOWNLOAD_TASKS.values()),
        }

    @router.post("/api/local_models/open_folder", dependencies=[Depends(require_loopback)])
    def open_local_model_folder(payload: Dict[str, Any], request: Request):
        _ = get_current_user(request)
        primary_model_dir = _ensure_bundle_model_dirs()
        raw_path = (payload.get("path") or "").strip()
        if raw_path and (raw_path.startswith("\\\\") or raw_path.startswith("//")):
            raise HTTPException(status_code=400, detail="不支持打开网络共享路径")
        if raw_path and not Path(raw_path).is_absolute():
            target = primary_model_dir / raw_path
        else:
            target = Path(raw_path) if raw_path else primary_model_dir
        if target.is_file():
            target = target.parent
        if not target.exists():
            try:
                target.mkdir(parents=True, exist_ok=True)
            except Exception:
                target = primary_model_dir
        opened_ok = open_directory_safely(target)
        return {"status": "ok", "opened": str(target), "gui_opened": opened_ok}

    @router.post("/api/local_models/pick_path", dependencies=[Depends(require_loopback)])
    async def pick_custom_local_model_path(payload: Dict[str, Any], request: Request):
        username = get_current_user(request)
        mode = (payload.get("mode") or "file").strip().lower()
        picked = await asyncio.to_thread(_native_pick_file_or_folder, mode)
        if not picked:
            return {"status": "cancelled", "picked": "", "selected": ""}
        p = Path(picked)
        if not p.exists():
            raise HTTPException(status_code=400, detail=f"路径不存在: {picked}")

        # 在文件对话框返回后重新读取最新 settings，防止阻塞期间用户在页面修改的其他配置被旧快照覆盖
        settings = load_user_settings(username)
        custom_paths = load_saved_custom_model_paths(settings.get("custom_model_paths"))
        norm_str = str(p.absolute())
        if norm_str not in custom_paths:
            custom_paths.insert(0, norm_str)
        custom_paths = save_custom_model_paths(custom_paths)
        settings["custom_model_paths"] = custom_paths
        settings["local_mode"] = "auto"
        save_user_settings(username, settings)

        detected = await discover_local_models(settings)
        # 找出刚挂载路径对应的模型 ID，方便前端一键切换
        matched_model_id = ""
        p_ggufs = {g.name.lower() for g in await asyncio.to_thread(_iter_gguf_in_path, p, 2)}
        for dm in detected:
            gp = str(dm.get("gguf_path") or "")
            if gp and (Path(gp).name.lower() in p_ggufs or str(p.absolute()).lower() in gp.lower()):
                matched_model_id = dm["id"]
                break

        return {
            "status": "ok",
            "picked": norm_str,
            "selected": norm_str,
            "matched_model_id": matched_model_id,
            "custom_paths": await asyncio.to_thread(_build_custom_paths_detail, custom_paths),
            "detected_models": detected,
            "hf_catalog": await asyncio.to_thread(_build_hf_catalog_with_status, custom_paths),
        }

    @router.post("/api/local_models/add_path", dependencies=[Depends(require_loopback)])
    async def add_custom_local_model_path(payload: Dict[str, Any], request: Request):
        username = get_current_user(request)
        raw_path = str(payload.get("path") or "").strip().strip('"').strip("'")
        if not raw_path:
            raise HTTPException(status_code=400, detail="请输入 .gguf 文件或目录路径")
        p = Path(raw_path)
        if not p.exists():
            raise HTTPException(status_code=400, detail=f"路径不存在: {raw_path}")
        if p.is_file() and p.suffix.lower() != ".gguf":
            raise HTTPException(status_code=400, detail="需为 .gguf 文件或其所在目录")

        ggufs_inside = [g for g in await asyncio.to_thread(_iter_gguf_in_path, p, 2) if "mmproj" not in g.name.lower()]
        if not ggufs_inside:
            raise HTTPException(status_code=400, detail="未找到 .gguf 文件")

        settings = load_user_settings(username)
        custom_paths = load_saved_custom_model_paths(settings.get("custom_model_paths"))
        norm_str = str(p.absolute())
        if norm_str not in custom_paths:
            custom_paths.insert(0, norm_str)
        custom_paths = save_custom_model_paths(custom_paths)
        settings["custom_model_paths"] = custom_paths
        settings["local_mode"] = "auto"
        save_user_settings(username, settings)

        detected = await discover_local_models(settings)
        matched_model_id = ""
        target_names = {g.name.lower() for g in ggufs_inside}
        for dm in detected:
            gp = str(dm.get("gguf_path") or "")
            if gp and Path(gp).name.lower() in target_names:
                matched_model_id = dm["id"]
                break

        return {
            "status": "ok",
            "added": norm_str,
            "matched_model_id": matched_model_id,
            "custom_paths": await asyncio.to_thread(_build_custom_paths_detail, custom_paths),
            "detected_models": detected,
            "hf_catalog": await asyncio.to_thread(_build_hf_catalog_with_status, custom_paths),
        }

    @router.post("/api/local_models/remove_path", dependencies=[Depends(require_loopback)])
    async def remove_custom_local_model_path(payload: Dict[str, Any], request: Request):
        username = get_current_user(request)
        settings = load_user_settings(username)
        raw_path = str(payload.get("path") or "").strip()
        custom_paths = [
            cp for cp in load_saved_custom_model_paths(settings.get("custom_model_paths"))
            if cp != raw_path and str(Path(cp)) != str(Path(raw_path))
        ]
        custom_paths = save_custom_model_paths(custom_paths)
        settings["custom_model_paths"] = custom_paths
        save_user_settings(username, settings)
        with _DISCOVERED_MODELS_LOCK:
            DISCOVERED_LOCAL_MODELS.clear()
        detected = await discover_local_models(settings)
        return {
            "status": "ok",
            "custom_paths": await asyncio.to_thread(_build_custom_paths_detail, custom_paths),
            "detected_models": detected,
            "hf_catalog": await asyncio.to_thread(_build_hf_catalog_with_status, custom_paths),
        }

    @router.get("/api/local_models/hf_repo_files")
    async def fetch_hf_author_or_repo_files(
        request: Request,
        author: str = "dongfangshuo",
        repo_id: str = "",
        mirror: str = "hf-mirror",
    ):
        """实时查询用户 HuggingFace (dongfangshuo 或指定 repo_id) 仓库下的所有 .gguf 模型文件，支持国内镜像与代理自动回退"""
        username = get_current_user(request)
        settings = load_user_settings(username)
        cfg_proxy = (settings.get("proxy") or "").strip() or None
        use_proxy = bool(settings.get("use_proxy"))
        hosts = ["https://hf-mirror.com", "https://huggingface.co"] if mirror == "hf-mirror" else ["https://huggingface.co", "https://hf-mirror.com"]

        def _attempts_for_host(h: str) -> List[Optional[str]]:
            if "hf-mirror.com" in h:
                return [None, cfg_proxy] if (use_proxy and cfg_proxy) else [None]
            else:
                if cfg_proxy:
                    return [cfg_proxy, None] if use_proxy else [None, cfg_proxy]
                return [None]

        repos_to_scan: List[str] = []
        if repo_id.strip():
            repos_to_scan = [repo_id.strip().strip("/")]
        else:
            clean_author = (author or "dongfangshuo").strip()
            for host in hosts:
                for p_try in _attempts_for_host(host):
                    try:
                        async with httpx.AsyncClient(proxy=p_try, trust_env=False, timeout=httpx.Timeout(6.0, connect=3.5), follow_redirects=True) as client:
                            r = await client.get(f"{host}/api/models?author={clean_author}", headers={"User-Agent": "Mozilla/5.0"})
                            if r.status_code == 200:
                                models_json = r.json()
                                if isinstance(models_json, list):
                                    repos_to_scan = [m.get("id") for m in models_json if isinstance(m, dict) and m.get("id")]
                                    if repos_to_scan:
                                        break
                    except Exception:
                        continue
                if repos_to_scan:
                    break
            if not repos_to_scan:
                repos_to_scan = [
                    "dongfangshuo/Dongfangshuo-Qwen3.8-27B-NSFW-v4",
                    "dongfangshuo/Dongfangshuo-Qwen3.8-Flash-Next-NSFW",
                    "dongfangshuo/Dongfangshuo-Qwen3.8-27B-NSFW-Novel",
                ]

        repo_results: List[Dict[str, Any]] = []
        custom_paths = load_saved_custom_model_paths(settings.get("custom_model_paths"))
        for rid in repos_to_scan:
            files_found: List[Dict[str, Any]] = []
            for host in hosts:
                for p_try in _attempts_for_host(host):
                    try:
                        async with httpx.AsyncClient(proxy=p_try, trust_env=False, timeout=httpx.Timeout(6.0, connect=3.5), follow_redirects=True) as client:
                            r = await client.get(f"{host}/api/models/{rid}/tree/main?recursive=true", headers={"User-Agent": "Mozilla/5.0"})
                            if r.status_code == 200 and isinstance(r.json(), list):
                                for f in r.json():
                                    if isinstance(f, dict) and f.get("type") == "file" and str(f.get("path") or "").lower().endswith(".gguf"):
                                        fpath = str(f["path"])
                                        fsize = int(f.get("size") or (f.get("lfs") or {}).get("size") or 0)
                                        loc = _locate_gguf_anywhere(Path(fpath).name, custom_paths)
                                        is_inst = bool(loc and loc.exists())
                                        files_found.append({
                                            "path": fpath,
                                            "filename": fpath,
                                            "name": Path(fpath).name,
                                            "size": fsize,
                                            "size_gb": round(fsize / (1024 ** 3), 2) if fsize else 0,
                                            "installed": is_inst,
                                            "exists": is_inst,
                                        })
                                break
                    except Exception:
                        continue
                if files_found:
                    break

            # 若处于纯离线环境且查询的是内置 dongfangshuo 仓库，自动回退使用内置精确文件清单
            if not files_found:
                seen_fpaths = set()
                for preset in HF_PRESET_CATALOG:
                    if preset.get("repo_id", "").lower() == rid.lower():
                        for pf in preset.get("files", []):
                            fpath = str(pf.get("path") or pf.get("filename") or "")
                            if not fpath or fpath in seen_fpaths:
                                continue
                            seen_fpaths.add(fpath)
                            fsize = int(pf.get("size") or 0)
                            loc = _locate_gguf_anywhere(Path(fpath).name, custom_paths)
                            is_inst = bool(loc and loc.exists())
                            files_found.append({
                                "path": fpath,
                                "filename": fpath,
                                "name": Path(fpath).name,
                                "size": fsize,
                                "size_gb": round(fsize / (1024 ** 3), 2) if fsize else 0,
                                "installed": is_inst,
                                "exists": is_inst,
                            })

            if files_found:
                repo_results.append({
                    "repo_id": rid,
                    "url": f"https://huggingface.co/{rid}",
                    "files": files_found,
                })
        top_files = repo_results[0]["files"] if repo_results else []
        return {"status": "ok", "repos": repo_results, "files": top_files}

    async def _run_hf_download_worker(task_id: str, proxy: Optional[str]) -> None:
        task_info = HF_DOWNLOAD_TASKS.get(task_id)
        if not task_info:
            return
        target_root = _ensure_bundle_model_dirs()
        mirror_pref = task_info.get("mirror", "hf-mirror")
        hosts = ["https://hf-mirror.com", "https://huggingface.co"] if mirror_pref == "hf-mirror" else ["https://huggingface.co", "https://hf-mirror.com"]
        repo_id = task_info["repo_id"]
        files_list = task_info["files"]
        subfolder_name = _resolve_model_subfolder(repo_id, files_list[0]["path"] if files_list else "")
        sub_dir = target_root / subfolder_name
        sub_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 先统计已存在或已下载的字节数（含未完成 .part 的初始续传字节，防止暂停后恢复时进度条跳回 0%）
            completed_before = 0
            initial_part_bytes = 0
            for fitem in files_list:
                rel_p = str(fitem["path"]).lstrip("/")
                fname = Path(rel_p).name
                sub_file = sub_dir / fname
                flat_file = target_root / fname
                dest_file = target_root / rel_p
                part_file = sub_dir / f"{fname}.part"
                old_part_file = target_root / f"{fname}.part"
                if old_part_file.exists() and not part_file.exists():
                    try:
                        old_part_file.replace(part_file)
                    except Exception:
                        pass
                expected_sz = int(fitem.get("size") or 0)
                if sub_file.exists() and (expected_sz <= 0 or sub_file.stat().st_size == expected_sz):
                    fitem["_done"] = True
                    fitem["_dest"] = str(sub_file)
                    completed_before += sub_file.stat().st_size
                elif flat_file.exists() and (expected_sz <= 0 or flat_file.stat().st_size == expected_sz):
                    fitem["_done"] = True
                    fitem["_dest"] = str(flat_file)
                    completed_before += flat_file.stat().st_size
                elif dest_file.exists() and (expected_sz <= 0 or dest_file.stat().st_size == expected_sz):
                    fitem["_done"] = True
                    fitem["_dest"] = str(dest_file)
                    completed_before += dest_file.stat().st_size
                else:
                    fitem["_done"] = False
                    if part_file.exists():
                        initial_part_bytes += part_file.stat().st_size

            task_info["downloaded_bytes"] = completed_before + initial_part_bytes
            total_all = int(task_info.get("total_bytes") or 0)
            if total_all > 0:
                task_info["progress_pct"] = min(99.9, round(task_info["downloaded_bytes"] * 100.0 / total_all, 1))
            task_info["updated_at"] = time.time()

            for idx, fitem in enumerate(files_list):
                if task_info.get("status") in ("paused", "cancelled"):
                    return
                if fitem.get("_done"):
                    continue

                rel_p = str(fitem["path"]).lstrip("/")
                fname = Path(rel_p).name
                # 自动归入对应系列子文件夹（model/Dongfangshuo-27B/ 或 model/Flash-Next/）
                dest_file = sub_dir / fname
                part_file = sub_dir / f"{fname}.part"
                expected_sz = int(fitem.get("size") or 0)
                task_info["current_file"] = f"({idx + 1}/{len(files_list)}) {subfolder_name}/{fname}"

                file_success = False
                last_err = ""
                host_proxy_pairs: List[Tuple[str, Optional[str], bool]] = []
                for h in hosts:
                    if "hf-mirror.com" in h:
                        host_proxy_pairs.append((h, None, False))
                        if proxy:
                            host_proxy_pairs.append((h, proxy, False))
                        else:
                            host_proxy_pairs.append((h, None, True))
                    else:
                        if proxy:
                            host_proxy_pairs.append((h, proxy, False))
                        host_proxy_pairs.append((h, None, True))
                        host_proxy_pairs.append((h, None, False))

                for host, cur_proxy, use_trust_env in host_proxy_pairs:
                    if task_info.get("status") in ("paused", "cancelled"):
                        return
                    url = f"{host}/{repo_id}/resolve/main/{rel_p}"
                    existing_bytes = part_file.stat().st_size if part_file.exists() else 0
                    if expected_sz > 0 and existing_bytes >= expected_sz and _has_valid_gguf_header(part_file):
                        if dest_file.exists():
                            dest_file.unlink()
                        part_file.replace(dest_file)
                        completed_before += dest_file.stat().st_size
                        task_info["downloaded_bytes"] = completed_before
                        file_success = True
                        break

                    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                    if existing_bytes > 0:
                        headers["Range"] = f"bytes={existing_bytes}-"

                    try:
                        async with httpx.AsyncClient(
                            proxy=cur_proxy,
                            trust_env=use_trust_env,
                            follow_redirects=True,
                            timeout=httpx.Timeout(60.0, connect=10.0),
                        ) as client:
                            async with client.stream("GET", url, headers=headers) as resp:
                                c_range = str(resp.headers.get("Content-Range") or "")
                                m_cr_total = re.search(r"/(\d+)\s*$", c_range)
                                cr_total_bytes = int(m_cr_total.group(1)) if m_cr_total else 0

                                if resp.status_code == 416:
                                    if cr_total_bytes >= 1024 * 1024:
                                        expected_sz = cr_total_bytes
                                        fitem["size"] = expected_sz
                                        task_info["total_bytes"] = sum(safe_int(x.get("size"), 0) for x in files_list)
                                        total_all = task_info["total_bytes"]
                                    # 严格校验 .part 大小确实已满且具备 GGUF 魔数头，避免镜像源异常返回 416 导致残损文件转正
                                    if (
                                        part_file.exists()
                                        and ((expected_sz > 0 and part_file.stat().st_size >= expected_sz) or (expected_sz <= 0 and part_file.stat().st_size >= 1024 * 1024))
                                        and _has_valid_gguf_header(part_file)
                                    ):
                                        if dest_file.exists():
                                            dest_file.unlink()
                                        part_file.replace(dest_file)
                                        completed_before += dest_file.stat().st_size
                                        task_info["downloaded_bytes"] = completed_before
                                        file_success = True
                                        break
                                    else:
                                        last_err = f"{host} 返回 HTTP 416 (Range 不匹配)，切换备用源重试"
                                        continue
                                if resp.status_code not in (200, 206):
                                    last_err = f"{host} 返回 HTTP {resp.status_code}"
                                    continue

                                resp_ctype = (resp.headers.get("Content-Type") or "").lower()
                                if "text/html" in resp_ctype:
                                    last_err = f"{host} 返回了 HTML 错误/认证页而非模型文件"
                                    continue

                                content_len = safe_int(resp.headers.get("Content-Length"), 0)
                                is_resume = (resp.status_code == 206 and existing_bytes > 0)
                                if not is_resume and existing_bytes > 0:
                                    # 已有分片续传时若服务端返回 200（不支持 Range 或返回了短错误页），严禁直接用 wb 清空已有大体积 .part 文件！
                                    if content_len <= existing_bytes or existing_bytes >= 8 * 1024 * 1024:
                                        last_err = f"{host} 未支持断点续传 (HTTP 200)，已保护本地已下载分片并尝试备用源"
                                        continue
                                    existing_bytes = 0
                                auth_total = cr_total_bytes if (is_resume and cr_total_bytes >= 1024 * 1024) else ((existing_bytes + content_len) if content_len > 0 else 0)
                                if auth_total >= 1024 * 1024:
                                    expected_sz = auth_total
                                    fitem["size"] = expected_sz
                                    task_info["total_bytes"] = sum(safe_int(x.get("size"), 0) for x in files_list)
                                    total_all = task_info["total_bytes"]

                                mode = "ab" if is_resume else "wb"
                                cur_file_bytes = existing_bytes
                                t_last = time.time()
                                bytes_since_last = 0
                                first_chunk_logged = False

                                with open(part_file, mode) as fh:
                                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                                        if task_info.get("status") in ("paused", "cancelled"):
                                            return
                                        if not chunk:
                                            continue
                                        fh.write(chunk)
                                        n = len(chunk)
                                        cur_file_bytes += n
                                        bytes_since_last += n
                                        now = time.time()
                                        elapsed = now - t_last
                                        if not first_chunk_logged or elapsed >= 0.35:
                                            first_chunk_logged = True
                                            speed_bps = bytes_since_last / max(elapsed, 0.05)
                                            task_info["speed_mbps"] = round(speed_bps / (1024 * 1024), 2)
                                            total_done = completed_before + cur_file_bytes
                                            task_info["downloaded_bytes"] = total_done
                                            if total_all > 0:
                                                task_info["progress_pct"] = min(99.9, round(total_done * 100.0 / total_all, 1))
                                                rem = max(0, total_all - total_done)
                                                task_info["eta_sec"] = int(rem / speed_bps) if speed_bps > 1024 else 0
                                            task_info["updated_at"] = now
                                            t_last = now
                                            bytes_since_last = 0

                        part_sz_now = part_file.stat().st_size if part_file.exists() else 0
                        size_ok = (expected_sz > 0 and part_sz_now >= expected_sz) or (expected_sz <= 0 and part_sz_now >= 1024 * 1024)
                        if size_ok and _has_valid_gguf_header(part_file):
                            if dest_file.exists():
                                dest_file.unlink()
                            part_file.replace(dest_file)
                            completed_before += dest_file.stat().st_size
                            task_info["downloaded_bytes"] = completed_before
                            file_success = True
                            break
                        elif size_ok and not _has_valid_gguf_header(part_file):
                            last_err = f"{host} 下载内容非合法 GGUF 模型文件头，已拦截覆盖"
                            if part_sz_now < 8 * 1024 * 1024:
                                try:
                                    part_file.unlink()
                                except Exception:
                                    pass
                        else:
                            last_err = "连接中断，可续传"
                    except asyncio.CancelledError:
                        return
                    except Exception as e:
                        last_err = f"{type(e).__name__}: {str(e)[:120]}"
                        continue

                if not file_success:
                    task_info["status"] = "error"
                    task_info["error"] = last_err or f"下载 {fname} 失败，可换源重试"
                    task_info["updated_at"] = time.time()
                    return

            # 全部文件下载完成！如果是 27B v4 Q4_K_M，立即执行零拷贝硬链接并刷新模型列表
            for fitem in files_list:
                fname = Path(str(fitem["path"])).name
                dest_p = sub_dir / fname
                if dest_p.exists() and dest_p.stat().st_size == 16547400160:
                    mm_p = sub_dir / "mmproj-model-bf16.gguf"
                    _try_zero_copy_link_v4_q4_blobs(dest_p, str(mm_p) if mm_p.exists() else "", _find_ollama_models_dir())

            task_info["status"] = "completed"
            task_info["progress_pct"] = 100.0
            task_info["speed_mbps"] = 0.0
            task_info["eta_sec"] = 0
            task_info["updated_at"] = time.time()
            task_info["current_file"] = f"已完成：model/{subfolder_name}/"
            _scan_local_models_folder()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            task_info["status"] = "error"
            task_info["error"] = str(e)
            task_info["updated_at"] = time.time()

    @router.post("/api/local_models/hf_download", dependencies=[Depends(require_loopback)])
    async def start_hf_model_download(payload: Dict[str, Any], request: Request):
        username = get_current_user(request)
        settings = load_user_settings(username)
        preset_id = (payload.get("preset_id") or "").strip()
        mirror = (payload.get("mirror") or "hf-mirror").strip().lower()
        proxy = settings.get("proxy") if settings.get("use_proxy") else None

        if preset_id:
            preset = next((p for p in HF_PRESET_CATALOG if p["id"] == preset_id), None)
            if not preset:
                raise HTTPException(status_code=404, detail=f"预设不存在: {preset_id}")
            task_id = f"dl_{preset_id}"
            repo_id = preset["repo_id"]
            title = preset["name"]
            files_list = [{"path": f.get("path") or f.get("filename"), "size": safe_int(f.get("size"), 0)} for f in preset["files"]]
        else:
            repo_id = (payload.get("repo_id") or "").strip().strip("/")
            if not re.match(r"^[A-Za-z0-9._\-]+/[A-Za-z0-9._\-]+$", repo_id):
                raise HTTPException(status_code=400, detail="非法的 HuggingFace 仓库 ID 格式（应为 author/repo）")
            raw_files = payload.get("files") or []
            if not raw_files or not isinstance(raw_files, list):
                raise HTTPException(status_code=400, detail="缺少 files 列表")
            files_list = []
            for rf in raw_files:
                raw_fp = rf if isinstance(rf, str) else ((rf.get("path") or rf.get("filename")) if isinstance(rf, dict) else "")
                clean_fp = str(raw_fp or "").strip().replace("\\", "/").lstrip("/")
                if not clean_fp or ".." in clean_fp.split("/") or not clean_fp.lower().endswith(".gguf"):
                    raise HTTPException(status_code=400, detail=f"仅允许下载合法的 .gguf 模型文件: {raw_fp}")
                rf_sz = safe_int(rf.get("size"), 0) if isinstance(rf, dict) else 0
                files_list.append({"path": clean_fp, "size": rf_sz})
            if not files_list:
                raise HTTPException(status_code=400, detail="没有有效的 .gguf 下载文件")
            first_name = Path(files_list[0]["path"]).stem
            slug = re.sub(r"[^a-zA-Z0-9_\-]", "_", first_name)[:36]
            task_id = f"dl_{slug}"
            title = payload.get("title") or f"{repo_id} / {Path(files_list[0]['path']).name}"
            matched_preset = next(
                (
                    p for p in HF_PRESET_CATALOG
                    if p["repo_id"].lower() == repo_id.lower()
                    and any(
                        Path(str(pf.get("path") or pf.get("filename") or "")).name.lower()
                        == Path(files_list[0]["path"]).name.lower()
                        and "mmproj" not in Path(files_list[0]["path"]).name.lower()
                        for pf in (p.get("files") or [])
                    )
                ),
                None,
            )
            if matched_preset and len(files_list) == 1 and len(matched_preset.get("files") or []) > 1:
                preset_id = matched_preset["id"]
                task_id = f"dl_{preset_id}"
                title = matched_preset["name"]
                files_list = [{"path": f.get("path") or f.get("filename"), "size": safe_int(f.get("size"), 0)} for f in matched_preset["files"]]

        existing_task = HF_DOWNLOAD_ASYNC_TASKS.get(task_id)
        if existing_task and not existing_task.done() and HF_DOWNLOAD_TASKS.get(task_id, {}).get("status") == "downloading":
            return {"status": "ok", "task": HF_DOWNLOAD_TASKS[task_id], "downloads": list(HF_DOWNLOAD_TASKS.values())}

        total_bytes = sum(safe_int(f.get("size"), 0) for f in files_list)
        first_fn = Path(files_list[0]["path"]).name if files_list else title
        task_info = {
            "task_id": task_id,
            "preset_id": preset_id,
            "repo_id": repo_id,
            "title": title,
            "filename": files_list[0]["path"] if len(files_list) == 1 else f"{title} ({len(files_list)} 个文件)",
            "mirror": mirror,
            "status": "downloading",
            "downloaded_bytes": 0,
            "total_bytes": total_bytes,
            "progress_pct": 0.0,
            "speed_mbps": 0.0,
            "eta_sec": 0,
            "current_file": f"连接 HuggingFace：{first_fn}...",
            "error": "",
            "files": files_list,
            "started_at": time.time(),
            "updated_at": time.time(),
        }
        HF_DOWNLOAD_TASKS[task_id] = task_info
        bg_task = asyncio.create_task(_run_hf_download_worker(task_id, proxy))
        HF_DOWNLOAD_ASYNC_TASKS[task_id] = bg_task
        return {"status": "ok", "task": task_info, "downloads": list(HF_DOWNLOAD_TASKS.values())}

    @router.post("/api/local_models/hf_control", dependencies=[Depends(require_loopback)])
    async def control_hf_model_download(payload: Dict[str, Any], request: Request):
        username = get_current_user(request)
        task_id = (payload.get("task_id") or "").strip()
        action = (payload.get("action") or "pause").strip().lower()
        task_info = HF_DOWNLOAD_TASKS.get(task_id)
        if not task_info:
            raise HTTPException(status_code=404, detail="下载任务不存在")

        bg_task = HF_DOWNLOAD_ASYNC_TASKS.get(task_id)
        if action == "resume":
            if bg_task and not bg_task.done() and task_info.get("status") == "downloading":
                return {"status": "ok", "downloads": list(HF_DOWNLOAD_TASKS.values())}
            settings = load_user_settings(username)
            proxy = settings.get("proxy") if settings.get("use_proxy") else None
            if payload.get("mirror"):
                task_info["mirror"] = str(payload.get("mirror")).strip().lower()
            task_info["status"] = "downloading"
            task_info["error"] = ""
            task_info["updated_at"] = time.time()
            new_bg_task = asyncio.create_task(_run_hf_download_worker(task_id, proxy))
            HF_DOWNLOAD_ASYNC_TASKS[task_id] = new_bg_task
        elif action in ("pause", "cancel", "remove"):
            task_info["status"] = "paused" if action == "pause" else "cancelled"
            task_info["updated_at"] = time.time()
            if bg_task and not bg_task.done():
                bg_task.cancel()
                try:
                    await asyncio.wait_for(asyncio.gather(bg_task, return_exceptions=True), timeout=2.0)
                except Exception:
                    pass
            if action in ("cancel", "remove"):
                should_del_part = bool(payload.get("delete_part", True if action == "cancel" else False))
                if should_del_part:
                    target_root = _ensure_bundle_model_dirs()
                    t_files = task_info.get("files") or []
                    first_rel_p = str(t_files[0].get("path") or "") if (t_files and isinstance(t_files[0], dict)) else ""
                    sub_name = _resolve_model_subfolder(task_info.get("repo_id", ""), first_rel_p)
                    for fitem in t_files:
                        fname = Path(str(fitem.get("path") or "")).name
                        if not fname:
                            continue
                        for cand_root in (target_root, _BUNDLE_ROOT / "model", _BUNDLE_ROOT / "models"):
                            for part_p in (
                                cand_root / sub_name / f"{fname}.part",
                                cand_root / "Flash-Next" / f"{fname}.part",
                                cand_root / "Dongfangshuo-27B" / f"{fname}.part",
                                cand_root / f"{fname}.part",
                            ):
                                if part_p.exists():
                                    try:
                                        part_p.unlink()
                                    except Exception:
                                        pass
                HF_DOWNLOAD_TASKS.pop(task_id, None)
                HF_DOWNLOAD_ASYNC_TASKS.pop(task_id, None)
        return {"status": "ok", "downloads": list(HF_DOWNLOAD_TASKS.values())}

    return router
