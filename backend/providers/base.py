# -*- coding: utf-8 -*-
"""Shared reusable httpx.AsyncClient pool and streaming event dataclass."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("easy_trpg.providers.base")

_CLIENT_POOL_LOCK = threading.Lock()
_CLIENT_POOL: Dict[str, httpx.AsyncClient] = {}


def get_http_client(proxy_url: Optional[str] = None) -> httpx.AsyncClient:
    """Return a pooled AsyncClient reusing TCP/TLS connections."""
    key = str(proxy_url or "").strip()
    with _CLIENT_POOL_LOCK:
        client = _CLIENT_POOL.get(key)
        if client is not None and not client.is_closed:
            return client
        timeout = httpx.Timeout(connect=12.0, read=180.0, write=30.0, pool=15.0)
        limits = httpx.Limits(max_connections=64, max_keepalive_connections=24, keepalive_expiry=60.0)
        client = httpx.AsyncClient(
            proxy=key or None,
            trust_env=False,
            timeout=timeout,
            limits=limits,
            follow_redirects=True,
        )
        _CLIENT_POOL[key] = client
        return client


async def close_http_clients() -> None:
    with _CLIENT_POOL_LOCK:
        clients = list(_CLIENT_POOL.values())
        _CLIENT_POOL.clear()
    for c in clients:
        try:
            await c.aclose()
        except Exception:
            pass


@dataclass
class StreamDelta:
    text: str = ""
    thinking: str = ""
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
