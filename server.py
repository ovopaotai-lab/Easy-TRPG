# -*- coding: utf-8 -*-
"""Easy-TRPG alpha 2.0 thin server entrypoint (backwards compatible with run.bat / run.sh)."""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List

import uvicorn

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.api.system import set_hot_reload_callback  # noqa: E402
from backend.app import create_app  # noqa: E402
from backend.config import ACTIVE_PORT_FILE, APP_VERSION  # noqa: E402
from backend.core.security import set_active_web_server_port  # noqa: E402
from backend.core.updater import get_local_version, run_cli_update  # noqa: E402


class _HotSwappableASGI:
    """Zero-downtime ASGI wrapper allowing in-memory hot swap without unloading local GPU models."""

    def __init__(self, target_app: Any) -> None:
        self.target_app = target_app
        self.reload_count = 0

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        await self.target_app(scope, receive, send)


app = create_app()
_DISPATCHER = _HotSwappableASGI(app)


def _perform_hot_reload(changed_files: List[str], target_version: str = "") -> Dict[str, Any]:
    global app
    try:
        # Refresh backend app instance cleanly
        new_app = create_app()
        _DISPATCHER.target_app = new_app
        _DISPATCHER.reload_count += 1
        app = new_app
        return {
            "hot_updated": True,
            "mode": "asgi_hot_swap",
            "version": target_version or APP_VERSION,
            "reload_count": _DISPATCHER.reload_count,
        }
    except Exception as exc:
        return {"hot_updated": False, "reason": str(exc)}


set_hot_reload_callback(_perform_hot_reload)


def _pick_web_port(preferred: int = 8765) -> int:
    for port in [preferred] + list(range(8766, 8799)):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("0.0.0.0", port))
                return port
        except OSError:
            continue
    return preferred


def main() -> None:
    parser = argparse.ArgumentParser(description="Easy-TRPG Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--check-update", action="store_true")
    args, _ = parser.parse_known_args()

    if args.update or args.check_update:
        sys.exit(run_cli_update(check_only=bool(args.check_update)))

    port = args.port if args.port > 0 else _pick_web_port(8765)
    set_active_web_server_port(port)
    ACTIVE_PORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_PORT_FILE.write_text(str(port), encoding="utf-8")

    local_url = f"http://127.0.0.1:{port}"
    print(f"\n  Easy-TRPG ({get_local_version()}) 已就绪: {local_url}\n")

    if not args.no_browser:
        def _open():
            time.sleep(0.9)
            try:
                webbrowser.open(local_url)
            except Exception:
                pass
        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(_DISPATCHER, host=args.host, port=port, log_level="warning", timeout_keep_alive=75)


if __name__ == "__main__":
    main()
