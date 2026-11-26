# -*- coding: utf-8 -*-
"""Cross-platform process-tree guardian, Win32 Job Object kill-on-close, and port management."""
from __future__ import annotations

import atexit
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

from backend.config import BASE_DIR

logger = logging.getLogger("easy_trpg.process_guard")

_SPAWNED_PROCS: List[subprocess.Popen] = []
_PROCS_LOCK = threading.Lock()
_WIN32_JOB_HANDLE: Optional[int] = getattr(sys, "_trpg_win32_engine_job_handle", None)
_CONSOLE_CTRL_REF: Any = getattr(sys, "_trpg_win32_console_ctrl_ref", None)
_ATEXIT_REGISTERED: bool = bool(getattr(sys, "_trpg_atexit_guard_registered", False))


def _win32_hidden_kwargs() -> dict:
    if os.name != "nt":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        "startupinfo": si,
    }


def _ensure_win32_kill_on_close_job() -> Optional[int]:
    global _WIN32_JOB_HANDLE
    if os.name != "nt":
        return None
    if _WIN32_JOB_HANDLE:
        return _WIN32_JOB_HANDLE
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL

        class _IO_COUNTERS(ctypes.Structure):
            _fields_ = [("ReadOperationCount", ctypes.c_uint64), ("WriteOperationCount", ctypes.c_uint64),
                        ("OtherOperationCount", ctypes.c_uint64), ("ReadTransferCount", ctypes.c_uint64),
                        ("WriteTransferCount", ctypes.c_uint64), ("OtherTransferCount", ctypes.c_uint64)]

        class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
                        ("IoInfo", _IO_COUNTERS), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        h_job = kernel32.CreateJobObjectW(None, None)
        if h_job:
            info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if kernel32.SetInformationJobObject(h_job, 9, ctypes.byref(info), ctypes.sizeof(info)):
                _WIN32_JOB_HANDLE = int(h_job)
                setattr(sys, "_trpg_win32_engine_job_handle", _WIN32_JOB_HANDLE)
                return _WIN32_JOB_HANDLE
            kernel32.CloseHandle(h_job)
    except Exception as exc:
        logger.debug("Win32 JobObject setup skipped: %s", exc)
    return None


def linux_pdeathsig_preexec() -> None:
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        libc.prctl(1, 9)  # PR_SET_PDEATHSIG, SIGKILL
    except Exception:
        pass


def register_spawned_engine_proc(proc: Optional[subprocess.Popen]) -> None:
    if proc is None:
        return
    with _PROCS_LOCK:
        _SPAWNED_PROCS.append(proc)
    if os.name == "nt":
        h_job = _ensure_win32_kill_on_close_job()
        proc_handle = getattr(proc, "_handle", None)
        if h_job and proc_handle:
            try:
                import ctypes
                from ctypes import wintypes
                kernel32 = ctypes.windll.kernel32
                kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
                kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
                kernel32.AssignProcessToJobObject(wintypes.HANDLE(h_job), wintypes.HANDLE(int(proc_handle)))
            except Exception as exc:
                logger.debug("AssignProcessToJobObject failed: %s", exc)


def terminate_process_tree_sync(proc: Optional[subprocess.Popen]) -> None:
    if proc is None:
        return
    try:
        if proc.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=4,
                **_win32_hidden_kwargs(),
            )
        else:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
    except Exception as exc:
        logger.debug("terminate_process_tree_sync ignored: %s", exc)


def kill_processes_by_image_name(names: tuple[str, ...]) -> None:
    """Terminate local engine binaries matching image names (safe scoped cleanup)."""
    if os.name == "nt":
        kw = _win32_hidden_kwargs()
        for nm in names:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/IM", nm],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=4,
                    **kw,
                )
            except Exception:
                pass
    else:
        for nm in names:
            try:
                subprocess.run(["pkill", "-f", nm], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
            except Exception:
                pass


def shutdown_local_engines_sync() -> None:
    with _PROCS_LOCK:
        procs = list(_SPAWNED_PROCS)
        _SPAWNED_PROCS.clear()
    for p in procs:
        terminate_process_tree_sync(p)
    kill_processes_by_image_name(("llama-server.exe", "strata.exe", "strata-vision.exe", "llama-server", "strata"))


def install_process_exit_guards() -> None:
    global _CONSOLE_CTRL_REF, _ATEXIT_REGISTERED
    if not _ATEXIT_REGISTERED:
        atexit.register(shutdown_local_engines_sync)
        _ATEXIT_REGISTERED = True
        setattr(sys, "_trpg_atexit_guard_registered", True)
    if os.name == "nt" and _CONSOLE_CTRL_REF is None:
        _ensure_win32_kill_on_close_job()
        try:
            import ctypes
            from ctypes import wintypes

            HANDLER_TYPE = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

            def _ctrl_handler(ctrl_type: int) -> bool:
                if ctrl_type in (0, 1, 2, 5, 6):
                    shutdown_local_engines_sync()
                return False

            _CONSOLE_CTRL_REF = HANDLER_TYPE(_ctrl_handler)
            setattr(sys, "_trpg_win32_console_ctrl_ref", _CONSOLE_CTRL_REF)
            ctypes.windll.kernel32.SetConsoleCtrlHandler(_CONSOLE_CTRL_REF, True)
        except Exception:
            pass


def is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    for fam, addr in ((socket.AF_INET, host),):
        try:
            with socket.socket(fam, socket.SOCK_STREAM) as s:
                s.settimeout(0.3)
                if s.connect_ex((addr, port)) == 0:
                    return False
        except OSError:
            pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, port))
            return True
    except OSError:
        return False


def pick_available_port(preferred: int, fallback_range: range) -> int:
    if is_port_free(preferred):
        return preferred
    for p in fallback_range:
        if p != preferred and is_port_free(p):
            return p
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def read_log_tail(files: List[Path], max_chars: int = 2400) -> str:
    chunks: List[str] = []
    for fp in files:
        if fp and fp.is_file():
            try:
                txt = fp.read_text(encoding="utf-8", errors="ignore").strip()
                if txt:
                    chunks.append(f"[{fp.name}]\n{txt[-max_chars:]}")
            except OSError:
                pass
    return "\n\n".join(chunks)


install_process_exit_guards()
