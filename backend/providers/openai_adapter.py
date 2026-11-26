# -*- coding: utf-8 -*-
"""OpenAI-compatible, LlamaCpp native, Strata, and Ollama streaming adapter."""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, AsyncIterator, Dict, List

import httpx

from backend.providers.base import StreamDelta

logger = logging.getLogger("easy_trpg.providers.openai")

_LOCAL_STOP_SEQUENCES = ["<|im_end|>", "<|endoftext|>", "<|eot_id|>"]


def build_openai_payload(
    *,
    model: str,
    messages: List[Dict[str, Any]],
    endpoint: Dict[str, Any],
    params: Dict[str, Any],
    think_enabled: bool = True,
    thinking_budget: int = 1024,
    chat_id: str = "",
) -> Dict[str, Any]:
    engine = str(endpoint.get("engine") or "openai").lower()
    is_local = bool(endpoint.get("is_local", False))
    max_tok = int(params.get("max_tokens") or 8192)
    temp = float(params.get("temperature") if params.get("temperature") is not None else 0.68)
    top_p = float(params.get("top_p") if params.get("top_p") is not None else 0.90)
    top_k = int(params.get("top_k") if params.get("top_k") is not None else 40)
    min_p = float(params.get("min_p") if params.get("min_p") is not None else 0.06)
    rep_pen = float(params.get("repetition_penalty") if params.get("repetition_penalty") is not None else 1.05)
    freq_pen = float(params.get("frequency_penalty") if params.get("frequency_penalty") is not None else 0.05)
    pres_pen = float(params.get("presence_penalty") if params.get("presence_penalty") is not None else 0.20)

    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temp,
        "top_p": top_p,
        "max_tokens": max_tok,
        "stream": True,
    }
    if is_local or pres_pen != 0:
        body["presence_penalty"] = pres_pen
    if is_local or freq_pen != 0:
        body["frequency_penalty"] = freq_pen

    if is_local:
        body["stop"] = list(_LOCAL_STOP_SEQUENCES)
        safe_think = min(max(256, thinking_budget), 1536, max(0, max_tok - 512)) if (think_enabled and max_tok >= 768) else 0
        if engine == "llama":
            body["cache_prompt"] = True
            if chat_id:
                body["id_slot"] = int(hashlib.md5(chat_id.encode("utf-8")).hexdigest()[:6], 16) % 4
            body["repeat_penalty"] = rep_pen
            body["repeat_last_n"] = 1024
            body["top_k"] = top_k
            body["min_p"] = min_p
            body["dry_multiplier"] = 0.8
            body["dry_base"] = 1.75
            body["dry_allowed_length"] = 2
            body["reasoning_budget"] = safe_think
            body["chat_template_kwargs"] = {"enable_thinking": bool(safe_think > 0)}
        elif engine == "strata":
            body["repetition_penalty"] = rep_pen
            body["penalty_last_n"] = 1024
            body["top_k"] = top_k
            body["min_p"] = min_p
            if safe_think > 0:
                body["reasoning_effort"] = "low" if safe_think <= 1024 else "medium"
                body["reasoning_budget_tokens"] = safe_think
            else:
                body["reasoning_effort"] = "none"
                body["reasoning_budget_tokens"] = 0
                body["chat_template_kwargs"] = {"enable_thinking": False}
        elif engine == "ollama":
            body["think"] = bool(safe_think > 0)
            body["repeat_penalty"] = rep_pen
            body["top_k"] = top_k
            body["min_p"] = min_p
            body["options"] = {
                "repeat_penalty": rep_pen,
                "repeat_last_n": 1024,
                "top_k": top_k,
                "min_p": min_p,
                "presence_penalty": pres_pen,
                "frequency_penalty": freq_pen,
                "num_predict": max_tok,
            }

    return body


async def stream_openai_chat(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    headers: Dict[str, str],
    body: Dict[str, Any],
) -> AsyncIterator[StreamDelta]:
    url = f"{base_url.rstrip('/')}/chat/completions"
    async with client.stream("POST", url, headers=headers, json=body) as resp:
        if resp.status_code != 200:
            err_b = await resp.aread()
            raise httpx.HTTPStatusError(
                f"API Error {resp.status_code}: {err_b.decode('utf-8', errors='ignore')[:500]}",
                request=resp.request,
                response=resp,
            )

        ctype = (resp.headers.get("content-type") or "").lower()
        if "text/event-stream" not in ctype and "application/json" in ctype:
            raw = await resp.aread()
            data = json.loads(raw.decode("utf-8", errors="ignore"))
            if data.get("error") and not data.get("choices"):
                raise RuntimeError(f"API Error: {data['error']}")
            msg = ((data.get("choices") or [{}])[0].get("message") or {})
            usage = data.get("usage") or {}
            pd = usage.get("prompt_tokens_details") or {}
            yield StreamDelta(
                text=str(msg.get("content") or ""),
                thinking=str(msg.get("reasoning_content") or msg.get("reasoning") or ""),
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                cache_read_tokens=int(pd.get("cached_tokens") or usage.get("prompt_cache_hit_tokens") or 0),
                finish_reason="stop",
            )
            return

        async for line in resp.aiter_lines():
            ln = line.strip()
            if not ln or not ln.startswith("data:"):
                continue
            payload = ln[5:].lstrip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if chunk.get("error") and not chunk.get("choices"):
                raise RuntimeError(f"API Stream Error: {chunk['error']}")

            usage = chunk.get("usage") or {}
            timings = chunk.get("timings") or {}
            pd = usage.get("prompt_tokens_details") or {}
            cached_tok = int(
                pd.get("cached_tokens")
                or usage.get("prompt_cache_hit_tokens")
                or timings.get("cache_n")
                or 0
            )
            choices = chunk.get("choices") or []
            c0 = choices[0] if choices and isinstance(choices[0], dict) else {}
            delta = c0.get("delta") or c0.get("message") or {}
            yield StreamDelta(
                text=str(delta.get("content") or ""),
                thinking=str(delta.get("reasoning_content") or delta.get("reasoning") or ""),
                cache_read_tokens=cached_tok,
                prompt_tokens=int(usage.get("prompt_tokens") or timings.get("prompt_n") or 0),
                completion_tokens=int(usage.get("completion_tokens") or timings.get("predicted_n") or 0),
                finish_reason=str(c0.get("finish_reason") or ""),
                raw=chunk,
            )
