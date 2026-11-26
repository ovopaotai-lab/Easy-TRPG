# -*- coding: utf-8 -*-
"""Unified endpoint router, 1-click vendor presets, model discovery, and connectivity tests."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from backend.core.security import is_loopback_only_url, is_self_workbench_url
from backend.providers.anthropic_adapter import build_anthropic_payload, stream_anthropic_chat
from backend.providers.base import StreamDelta, get_http_client
from backend.providers.gemini_adapter import build_gemini_payload, stream_gemini_chat
from backend.providers.openai_adapter import build_openai_payload, stream_openai_chat

logger = logging.getLogger("easy_trpg.providers.router")

CLOUD_VENDOR_PRESETS: List[Dict[str, Any]] = [
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "protocol": "openai",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "suggested_models": ["deepseek-chat", "deepseek-reasoner"],
        "key_hint": "sk-...",
        "needs_proxy": False,
        "badge": "国内直连 · 性价比首选",
    },
    {
        "id": "siliconflow",
        "name": "硅基流动 SiliconFlow",
        "protocol": "openai",
        "base_url": "https://api.siliconflow.cn/v1",
        "default_model": "Qwen/Qwen3-32B",
        "suggested_models": ["Qwen/Qwen3-32B", "deepseek-ai/DeepSeek-V3"],
        "key_hint": "sk-...",
        "needs_proxy": False,
        "badge": "国内直连 · 送免费额度",
    },
    {
        "id": "gemini",
        "name": "Google Gemini",
        "protocol": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "default_model": "gemini-2.5-flash",
        "suggested_models": ["gemini-2.5-flash", "gemini-2.5-pro"],
        "key_hint": "AIza...",
        "needs_proxy": True,
        "badge": "原生无审查配置",
    },
    {
        "id": "claude",
        "name": "Anthropic Claude",
        "protocol": "claude",
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-sonnet-4-5",
        "suggested_models": ["claude-sonnet-4-5", "claude-opus-4-1"],
        "key_hint": "sk-ant-...",
        "needs_proxy": True,
        "badge": "原生 /v1/messages + 缓存",
    },
    {
        "id": "openai",
        "name": "OpenAI / 通用中转",
        "protocol": "openai",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "suggested_models": ["gpt-4o", "gpt-4.1"],
        "key_hint": "sk-...",
        "needs_proxy": True,
        "badge": "OpenAI 标准兼容",
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "protocol": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "anthropic/claude-sonnet-4",
        "suggested_models": ["anthropic/claude-sonnet-4", "deepseek/deepseek-chat-v3"],
        "key_hint": "sk-or-...",
        "needs_proxy": False,
        "badge": "全模型聚合",
    },
    {
        "id": "ollama",
        "name": "本机 Ollama",
        "protocol": "ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "default_model": "",
        "suggested_models": [],
        "key_hint": "无需填写",
        "needs_proxy": False,
        "badge": "本机服务",
    },
]


def is_model_vision_capable(model_id: str) -> bool:
    low = (model_id or "").lower()
    if any(t in low for t in ("vl", "vision", "omni", "gemini", "claude-3", "claude-4", "claude-sonnet", "claude-opus", "gpt-4o", "gpt-4.1", "qwen3.8", "dongfangshuo")):
        return True
    return False


def is_model_audio_capable(model_id: str, native_protocol: str = "openai", is_local: bool = False) -> bool:
    """Return True for endpoints that accept audio parts natively (e.g. Gemini, gpt-4o-audio, omni)."""
    if is_local:
        return False
    if native_protocol == "gemini_native":
        return True
    low = (model_id or "").lower()
    return any(t in low for t in ("gemini", "gpt-4o-audio", "gpt-audio", "omni", "step-audio", "minicpm-o"))


def sanitize_messages_for_model(
    messages: List[Dict[str, Any]],
    supports_vision: bool,
    supports_audio: bool = False,
) -> List[Dict[str, Any]]:
    if supports_vision and supports_audio:
        return messages
    out: List[Dict[str, Any]] = []
    for m in messages:
        c = m.get("content")
        if isinstance(c, list):
            kept: List[Dict[str, Any]] = []
            for p in c:
                if not isinstance(p, dict):
                    continue
                ptype = p.get("type")
                if ptype == "image_url" and not supports_vision:
                    continue
                if ptype == "input_audio" and not supports_audio:
                    continue
                kept.append(p)
            has_media = any(p.get("type") != "text" for p in kept)
            if has_media:
                out.append({**m, "content": kept})
            else:
                txts = [str(p.get("text") or "") for p in kept if p.get("type") == "text"]
                out.append({**m, "content": "\n".join(t for t in txts if t).strip() or "[媒体]"})
        else:
            out.append(m)
    return out


def normalize_api_endpoint_and_protocol(
    raw_base_url: str,
    raw_api_key: str,
    raw_protocol: str = "auto",
) -> Dict[str, Any]:
    url = (raw_base_url or "").strip().rstrip("/")
    key = (raw_api_key or "").strip()
    proto = (raw_protocol or "auto").strip().lower()
    if proto not in ("auto", "openai", "gemini", "claude", "ollama"):
        proto = "auto"

    for suffix in ("/chat/completions", "/completions", "/messages", "/models", "/api/tags", "/api/chat"):
        if url.lower().endswith(suffix):
            url = url[: -len(suffix)].rstrip("/")

    effective_proto = proto
    ul = url.lower()
    if effective_proto == "auto":
        if "generativelanguage.googleapis.com" in ul or (not url and key.startswith("AIza")):
            effective_proto = "gemini"
        elif "anthropic.com" in ul or (not url and key.startswith("sk-ant-")):
            effective_proto = "claude"
        elif ":11434" in ul:
            effective_proto = "ollama"
        else:
            effective_proto = "openai"

    # Decide if Gemini uses native REST vs third-party OpenAI-compatible relay
    native_gemini = effective_proto == "gemini" and ("generativelanguage.googleapis.com" in ul or not url)
    native_claude = effective_proto == "claude" and ("anthropic.com" in ul or not url or proto == "claude")

    if effective_proto == "gemini":
        if not url:
            norm_url = "https://generativelanguage.googleapis.com/v1beta"
        elif ul.endswith("/v1beta/openai"):
            norm_url = url[:-len("/openai")] if native_gemini else url
        elif ul.endswith("/v1beta") or ul.endswith("/v1"):
            norm_url = url
        else:
            norm_url = f"{url}/v1" if not re.search(r"/v\d+", ul) else url
    elif effective_proto == "claude":
        if not url:
            norm_url = "https://api.anthropic.com/v1"
        elif not re.search(r"/v\d+$", ul):
            norm_url = f"{url}/v1"
        else:
            norm_url = url
    elif effective_proto == "ollama":
        if not url:
            norm_url = "http://127.0.0.1:11434/v1"
        elif not ul.endswith("/v1"):
            norm_url = f"{url}/v1"
        else:
            norm_url = url
    else:
        if not url and key:
            norm_url = "https://api.openai.com/v1"
        elif url and not re.search(r"/v\d+(?:beta(?:/openai)?)?$", ul):
            norm_url = f"{url}/v1"
        else:
            norm_url = url

    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if key:
        if not native_claude and not native_gemini:
            headers["Authorization"] = f"Bearer {key}"
        if effective_proto == "gemini":
            headers["x-goog-api-key"] = key
            if not native_gemini:
                headers["Authorization"] = f"Bearer {key}"
        elif effective_proto == "claude":
            headers["x-api-key"] = key
            headers["anthropic-version"] = "2023-06-01"
            if not native_claude:
                headers["Authorization"] = f"Bearer {key}"

    return {
        "configured_protocol": proto,
        "protocol": effective_proto,
        "native_protocol": "gemini_native" if native_gemini else ("claude_native" if native_claude else "openai"),
        "base_url": norm_url,
        "raw_clean_url": url,
        "api_key": key,
        "headers": headers,
    }


def resolve_model_endpoint(
    model_id: str,
    settings: Dict[str, Any],
    discovered_locals: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    from backend.engines.supervisor import get_discovered_models_snapshot

    locals_map = discovered_locals if discovered_locals is not None else get_discovered_models_snapshot()
    if model_id in locals_map:
        lm = locals_map[model_id]
        engine = lm.get("engine", "llama")
        base_url = lm.get("base_url") or (
            "http://127.0.0.1:8080/v1" if engine == "strata" else "http://127.0.0.1:11435/v1"
        )
        return {
            "is_local": True,
            "engine": engine,
            "protocol": "openai",
            "native_protocol": "openai",
            "base_url": base_url,
            "api_key": "local-key",
            "upstream_model": lm.get("upstream_model") or model_id,
            "supports_vision": bool(lm.get("supports_vision", True)),
            "supports_audio": False,
            "gguf_path": lm.get("gguf_path", ""),
            "local_meta": lm,
            "headers": {"Authorization": "Bearer local-key", "Content-Type": "application/json"},
        }

    raw_base = str(settings.get("base_url") or "").strip()
    if is_self_workbench_url(raw_base):
        raw_base = ""
    raw_key = str(settings.get("api_key") or "").strip()
    raw_proto = str(settings.get("api_protocol") or "auto").strip()
    norm = normalize_api_endpoint_and_protocol(raw_base, raw_key, raw_proto)
    return {
        "is_local": False,
        "engine": norm["protocol"],
        "protocol": norm["protocol"],
        "native_protocol": norm["native_protocol"],
        "base_url": norm["base_url"],
        "api_key": norm["api_key"],
        "upstream_model": model_id,
        "supports_vision": is_model_vision_capable(model_id),
        "supports_audio": is_model_audio_capable(model_id, norm["native_protocol"], is_local=False),
        "headers": norm["headers"],
    }


async def stream_via_endpoint(
    *,
    endpoint: Dict[str, Any],
    messages: List[Dict[str, Any]],
    params: Dict[str, Any],
    proxy_url: Optional[str] = None,
    think_enabled: bool = True,
    thinking_budget: int = 1024,
    chat_id: str = "",
) -> AsyncIterator[StreamDelta]:
    """Stream tokens using pooled HTTP client with automatic proxy->direct fallback."""
    is_local = bool(endpoint.get("is_local"))
    local_meta = endpoint.get("local_meta")
    live_local_url = str(local_meta.get("base_url") or "").strip() if (is_local and isinstance(local_meta, dict)) else ""
    base_url = live_local_url or str(endpoint.get("base_url") or "")
    if live_local_url:
        endpoint["base_url"] = live_local_url
    eff_proxy = None if (is_local or is_loopback_only_url(base_url)) else (proxy_url or None)
    proxy_attempts = [eff_proxy, None] if eff_proxy else [None]

    native_proto = endpoint.get("native_protocol") or "openai"
    model = str(endpoint.get("upstream_model") or "")
    headers = dict(endpoint.get("headers") or {})

    if native_proto == "claude_native":
        body, _ = build_anthropic_payload(
            model=model,
            messages=messages,
            params=params,
            think_enabled=think_enabled,
            thinking_budget=thinking_budget,
        )
    elif native_proto == "gemini_native":
        body = build_gemini_payload(
            model=model,
            messages=messages,
            params=params,
            think_enabled=think_enabled,
            thinking_budget=thinking_budget,
        )
    else:
        body = build_openai_payload(
            model=model,
            messages=messages,
            endpoint=endpoint,
            params=params,
            think_enabled=think_enabled,
            thinking_budget=thinking_budget,
            chat_id=chat_id,
        )

    last_exc: Optional[Exception] = None
    for idx, p_try in enumerate(proxy_attempts):
        client = get_http_client(p_try)
        emitted = False
        try:
            if native_proto == "claude_native":
                async for delta in stream_anthropic_chat(client, base_url=base_url, headers=headers, body=body):
                    emitted = True
                    yield delta
                return
            elif native_proto == "gemini_native":
                async for delta in stream_gemini_chat(
                    client,
                    base_url=base_url,
                    api_key=str(endpoint.get("api_key") or ""),
                    model=model,
                    headers=headers,
                    body=body,
                ):
                    emitted = True
                    yield delta
                return
            else:
                async for delta in stream_openai_chat(client, base_url=base_url, headers=headers, body=body):
                    emitted = True
                    yield delta
                return
        except (httpx.ConnectError, httpx.ProxyError, httpx.ConnectTimeout) as exc:
            last_exc = exc
            if not emitted and idx + 1 < len(proxy_attempts):
                logger.info("Proxy unreachable (%s), falling back to direct connection", exc)
                continue
            raise
    if last_exc:
        raise last_exc


async def fetch_remote_models(settings: Dict[str, Any]) -> Dict[str, Any]:
    raw_base = str(settings.get("base_url") or "").strip()
    if is_self_workbench_url(raw_base):
        raw_base = ""
    api_key = str(settings.get("api_key") or "").strip()
    proto = str(settings.get("api_protocol") or "auto").strip().lower()
    norm = normalize_api_endpoint_and_protocol(raw_base, api_key, proto)
    base_url = norm["base_url"]
    if not base_url or not (raw_base or api_key or proto in ("gemini", "claude", "ollama")):
        return {"models": [], "error": "", "used_direct_fallback": False}

    proxy = (settings.get("proxy") or "").strip() if settings.get("use_proxy") else None
    attempts = [proxy, None] if (proxy and not is_loopback_only_url(base_url)) else [None]
    headers = dict(norm["headers"])
    headers.pop("Content-Type", None)

    models: List[str] = []
    last_err = ""
    used_direct_fb = False

    for idx, p_try in enumerate(attempts):
        client = get_http_client(p_try)
        try:
            url = f"{base_url.rstrip('/')}/models"
            r = await client.get(url, headers=headers, timeout=8.0)
            if r.status_code == 200:
                data = r.json()
                items = data.get("data") if isinstance(data, dict) and "data" in data else (
                    data.get("models") if isinstance(data, dict) and "models" in data else (data if isinstance(data, list) else [])
                )
                for m in items or []:
                    if isinstance(m, dict):
                        mid = str(m.get("id") or m.get("name") or "")
                        if mid.startswith("models/"):
                            mid = mid[7:]
                        if mid:
                            models.append(mid)
                    elif isinstance(m, str) and m.strip():
                        models.append(m.strip())
                if idx > 0:
                    used_direct_fb = True
                break
            else:
                last_err = f"HTTP {r.status_code}"
        except Exception as exc:
            last_err = str(exc)

    # Static sensible defaults for Claude when /models fails or isn't supported
    if not models and norm["protocol"] == "claude" and api_key:
        models = ["claude-sonnet-4-5", "claude-opus-4-1", "claude-3-7-sonnet-latest"]
        last_err = ""

    return {
        "models": list(dict.fromkeys(models)),
        "error": last_err if not models else "",
        "used_direct_fallback": used_direct_fb,
        "protocol": norm["protocol"],
    }


async def test_model_connectivity(
    model_id: str,
    settings: Dict[str, Any],
    proxy_url: Optional[str] = None,
) -> Dict[str, Any]:
    ep = resolve_model_endpoint(model_id, settings)
    if not ep["is_local"] and not ep.get("base_url"):
        return {"status": "fail", "ok": False, "model": model_id, "error": "未配置 API 地址或 Key"}

    t0 = time.perf_counter()
    first_token_ms: Optional[int] = None
    pieces: List[str] = []
    try:
        if ep["is_local"]:
            from backend.engines.supervisor import ensure_local_engine_ready
            err = await ensure_local_engine_ready(model_id, ep["local_meta"], settings=settings)
            if err:
                msg = err.get("message") if isinstance(err, dict) else str(err)
                return {"status": "fail", "ok": False, "model": model_id, "error": msg, "diagnosis": err if isinstance(err, dict) else None}
            if ep.get("local_meta", {}).get("base_url"):
                ep["base_url"] = ep["local_meta"]["base_url"]
        async for delta in stream_via_endpoint(
            endpoint=ep,
            messages=[{"role": "user", "content": "Reply with OK only."}],
            params={"temperature": 0.1, "max_tokens": 32},
            proxy_url=proxy_url,
            think_enabled=False,
        ):
            if first_token_ms is None and (delta.text or delta.thinking):
                first_token_ms = int((time.perf_counter() - t0) * 1000)
            if delta.text:
                pieces.append(delta.text)
                if len("".join(pieces)) >= 12:
                    break
        total_ms = int((time.perf_counter() - t0) * 1000)
        ft = first_token_ms or total_ms
        return {
            "status": "ok",
            "ok": True,
            "model": model_id,
            "first_token_ms": ft,
            "latency_ms": ft,
            "total_ms": total_ms,
            "health": "本地" if ep["is_local"] else ("正常" if ft < 4500 else "延迟较高"),
            "sample": "".join(pieces).strip()[:40] or "OK",
        }
    except Exception as exc:
        return {
            "status": "fail",
            "ok": False,
            "model": model_id,
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "health": "异常",
            "error": str(exc),
        }
