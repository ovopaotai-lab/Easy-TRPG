# -*- coding: utf-8 -*-
"""FastAPI application factory, middleware, static hosting, and lifecycle management."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api import ai_tools, auth, cards, chats, gallery, models, projects, settings, system, trpg
from backend.config import APP_VERSION, STATIC_DIR, configure_logging
from backend.core.auth import ensure_user_workspace
from backend.core.security import is_same_origin_request
from backend.engines.supervisor import shutdown_local_engines
from backend.providers.base import close_http_clients

logger = configure_logging()


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    ensure_user_workspace("player")
    yield
    for t in list(chats.ACTIVE_BG_TASKS.values()):
        if not t.done():
            t.cancel()
    chats.ACTIVE_BG_TASKS.clear()
    chats.ACTIVE_PARTIAL_TEXT.clear()
    await close_http_clients()
    await shutdown_local_engines()


def create_app() -> FastAPI:
    app = FastAPI(title="Easy-TRPG", version=APP_VERSION, lifespan=_app_lifespan)

    for mod in (auth, settings, models, projects, chats, trpg, cards, gallery, ai_tools, system):
        app.include_router(mod.router)

    @app.middleware("http")
    async def security_and_cache_middleware(request: Request, call_next):
        path = request.url.path
        if request.method.upper() in ("POST", "PUT", "DELETE", "PATCH") and path.startswith("/api/"):
            if not is_same_origin_request(request):
                return JSONResponse(status_code=403, content={"detail": "跨站请求已被拦截 (CSRF)"})
        response = await call_next(request)
        if path == "/" or path.endswith((".html", ".js", ".css")) or "/configuration" in path:
            if path == "/" or path.endswith(".html") or "/configuration" in path:
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
        return response

    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    @app.get("/zh/app/{app_id}/configuration", response_class=HTMLResponse)
    @app.get("/app/{app_id}/configuration", response_class=HTMLResponse)
    def read_root(app_id: Optional[str] = None):
        idx = STATIC_DIR / "index.html"
        if idx.is_file():
            return HTMLResponse(
                content=idx.read_text(encoding="utf-8"),
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )
        return HTMLResponse("<h1>Easy-TRPG 正在初始化前端资源...</h1>")

    return app
