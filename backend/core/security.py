# -*- coding: utf-8 -*-
"""Security helpers: path traversal prevention, CSRF origin guard, API key masking, native pickers."""
from __future__ import annotations

import copy
import hashlib
import ipaddress
import logging
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from backend.config import USERS_DIR

logger = logging.getLogger("easy_trpg.security")

API_KEY_MASK_TOKEN = "****"
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_ACTIVE_WEB_PORT: int = 8765
_NATIVE_PICKER_LOCK = threading.Lock()


def set_active_web_server_port(port: int) -> None:
    global _ACTIVE_WEB_PORT
    try:
        p = int(port)
        if 1 <= p <= 65535:
            _ACTIVE_WEB_PORT = p
    except (TypeError, ValueError):
        pass


def get_active_web_server_port() -> int:
    return _ACTIVE_WEB_PORT


def sanitize_id(raw_id: Any) -> str:
    """Sanitize path identifiers against path traversal and unsafe characters."""
    s = str(raw_id or "")
    cleaned = re.sub(r"[^a-zA-Z0-9_\-\.]", "", s).strip(".")
    if not cleaned or cleaned in (".", ".."):
        return "default"
    return cleaned


def sanitize_username(username: str) -> str:
    raw = str(username or "player").strip() or "player"
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "", raw)
    h8 = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    if not cleaned or cleaned in (".", "..") or cleaned != raw:
        return f"{cleaned or 'u'}_{h8}"
    return cleaned


def get_user_dir(username: str) -> Path:
    safe_name = sanitize_username(username)
    users_root = USERS_DIR.resolve()
    udir = (USERS_DIR / safe_name).resolve()
    if udir == users_root or not udir.is_relative_to(users_root):
        raise HTTPException(status_code=400, detail="非法用户名路径")
    udir.mkdir(parents=True, exist_ok=True)
    return udir


def get_user_projects_dir(username: str) -> Path:
    d = get_user_dir(username) / "projects"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_user_chats_dir(username: str) -> Path:
    d = get_user_dir(username) / "chats"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_user_gallery_dir(username: str) -> Path:
    d = get_user_dir(username) / "gallery"
    d.mkdir(parents=True, exist_ok=True)
    (d / "thumbs").mkdir(parents=True, exist_ok=True)
    return d


def get_user_presets_dir(username: str) -> Path:
    d = get_user_dir(username) / "presets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def mask_api_key(raw_key: Any) -> str:
    s = str(raw_key or "").strip()
    if not s:
        return ""
    if len(s) <= 8:
        return API_KEY_MASK_TOKEN
    return f"{s[:4]}{API_KEY_MASK_TOKEN}{s[-4:]}"


def is_masked_api_key(val: Any) -> bool:
    s = str(val or "").strip()
    return bool(s and API_KEY_MASK_TOKEN in s)


def mask_settings_for_client(settings: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(settings)
    raw_k = str(out.get("api_key") or "").strip()
    out["has_api_key"] = bool(raw_k)
    out["api_key"] = mask_api_key(raw_k)
    profiles = out.get("api_profiles")
    if isinstance(profiles, list):
        masked_profiles = []
        for pf in profiles:
            if not isinstance(pf, dict):
                continue
            pfc = dict(pf)
            pk = str(pfc.get("api_key") or "").strip()
            pfc["has_api_key"] = bool(pk)
            pfc["api_key"] = mask_api_key(pk)
            masked_profiles.append(pfc)
        out["api_profiles"] = masked_profiles
    return out


def is_loopback_only_url(raw_url: str) -> bool:
    s = (raw_url or "").strip()
    if not s:
        return False
    try:
        parsed = urlparse(s if "://" in s else f"http://{s}")
        host = (parsed.hostname or "").strip().lower()
        if not host:
            return False
        if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return True
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_self_workbench_url(raw_url: str, web_port: int | None = None) -> bool:
    s = (raw_url or "").strip()
    if not s:
        return False
    port_chk = web_port or _ACTIVE_WEB_PORT or 8765
    try:
        parsed = urlparse(s if "://" in s else f"http://{s}")
        host = (parsed.hostname or "").strip().lower()
        port = parsed.port
        if port is None:
            return False
        if port == port_chk and host in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
            return True
        if port == port_chk and host:
            try:
                ip_obj = ipaddress.ip_address(host)
                return ip_obj.is_private or ip_obj.is_loopback
            except ValueError:
                return False
    except ValueError:
        return False
    return False


def get_client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    x_real = request.headers.get("x-real-ip")
    if x_real:
        return x_real.strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"


def parse_device_info(ua_string: str) -> str:
    if not ua_string:
        return "未知设备"
    ua = ua_string.lower()
    os_name = "其他设备"
    if "iphone" in ua:
        os_name = "iPhone"
    elif "ipad" in ua:
        os_name = "iPad"
    elif "android" in ua:
        os_name = "Android"
    elif "windows" in ua:
        os_name = "Windows"
    elif "macintosh" in ua or "mac os" in ua:
        os_name = "Mac"
    elif "linux" in ua:
        os_name = "Linux"

    browser = "浏览器"
    if "micromessenger" in ua:
        browser = "微信"
    elif "edg" in ua:
        browser = "Edge"
    elif "chrome" in ua and "safari" in ua:
        browser = "Chrome"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    elif "firefox" in ua:
        browser = "Firefox"
    return f"{os_name} ({browser})"


def is_same_origin_request(request: Request) -> bool:
    """Validate Origin/Referer on mutating API calls to block cross-site requests."""
    origin = (request.headers.get("origin") or "").strip()
    referer = (request.headers.get("referer") or "").strip()
    if not origin and not referer:
        return True
    src_raw = origin or referer
    if src_raw.lower() == "null":
        return False
    try:
        src_parsed = urlparse(src_raw)
        src_host = (src_parsed.hostname or "").strip().lower()
        src_port = src_parsed.port or (443 if src_parsed.scheme == "https" else 80)
    except ValueError:
        return False
    if not src_host:
        return False

    raw_host_hdr = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
    req_host = ""
    req_port = None
    if raw_host_hdr:
        try:
            rp = urlparse(f"http://{raw_host_hdr}")
            req_host = (rp.hostname or "").strip().lower()
            req_port = rp.port
        except ValueError:
            req_host = raw_host_hdr.split(":")[0].strip().lower()

    if src_host == req_host:
        if req_port is not None and src_port != req_port and src_host not in _LOOPBACK_HOSTS:
            return False
        return True
    if src_host in _LOOPBACK_HOSTS and req_host in _LOOPBACK_HOSTS:
        return True
    return False


def require_loopback(request: Request) -> None:
    """Restrict local filesystem / process endpoints strictly to loopback clients."""
    host = (request.client.host if request.client else "") or ""
    if host.startswith("::ffff:"):
        host = host[7:]
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="仅限本机操作")


def open_directory_safely(target: Path) -> bool:
    raw_str = str(target or "").strip()
    if not raw_str or raw_str.startswith("\\\\") or raw_str.startswith("//"):
        raise HTTPException(status_code=400, detail="不支持网络共享或空路径")
    resolved = target.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"目录不存在: {resolved}")
    if os.name == "nt":
        try:
            os.startfile(str(resolved))  # type: ignore[attr-defined]
            return True
        except OSError:
            subprocess.Popen(["explorer.exe", str(resolved)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    import sys
    if sys.platform == "darwin" and shutil.which("open"):
        subprocess.Popen(["open", str(resolved)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    if shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", str(resolved)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    return False


def _ps_quote(text: str) -> str:
    return str(text or "").replace("'", "''")


def native_pick_path(mode: str = "folder", title: str = "选择文件夹", file_filter: str = "") -> str:
    """Thread-safe native folder/file dialog (tkinter with WinForms PowerShell fallback)."""
    with _NATIVE_PICKER_LOCK:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            if mode in ("folder", "dir"):
                chosen = filedialog.askdirectory(title=title, parent=root)
            else:
                chosen = filedialog.askopenfilename(title=title, parent=root)
            try:
                root.destroy()
            except Exception as exc:
                logger.debug("tk root destroy ignored: %s", exc)
            return os.path.normpath(chosen) if chosen else ""
        except Exception:
            pass

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
                    f"$f.Description = '{_ps_quote(title)}'; "
                    "if ($f.ShowDialog($top) -eq 'OK') { Write-Output $f.SelectedPath }; "
                    "$top.Dispose()"
                )
            else:
                flt = file_filter or "GGUF 模型文件 (*.gguf)|*.gguf|所有文件 (*.*)|*.*"
                ps_cmd = (
                    enc_prefix
                    + "Add-Type -AssemblyName System.Windows.Forms; "
                    "$top = New-Object System.Windows.Forms.Form -Property @{TopMost=$true}; "
                    "$f = New-Object System.Windows.Forms.OpenFileDialog; "
                    f"$f.Title = '{_ps_quote(title)}'; "
                    f"$f.Filter = '{_ps_quote(flt)}'; "
                    "if ($f.ShowDialog($top) -eq 'OK') { Write-Output $f.FileName }; "
                    "$top.Dispose()"
                )
            cf = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-STA", "-Command", ps_cmd],
                stdin=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=cf,
                startupinfo=si,
                timeout=120,
            )
            chosen = out.decode("utf-8", errors="ignore").strip()
            return os.path.normpath(chosen) if chosen else ""
        except Exception as exc:
            logger.warning("Native file picker failed: %s", exc)
            return ""
