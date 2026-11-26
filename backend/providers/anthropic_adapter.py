# -*- coding: utf-8 -*-
"""Native Anthropic /v1/messages adapter with prompt caching (cache_control) & thinking."""
from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator, Dict, List, Tuple

import httpx

from backend.providers.base import StreamDelta

_DATA_URI_RE = re.compile(r"^data:(image/[^;]+);base64,(.+)$", re.S)


def _convert_content_to_anthropic(content: Any) -> Any:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content or "")
    blocks: List[Dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text":
            blocks.append({"type": "text", "text": str(part.get("text") or "")})
        elif part.get("type") == "image_url":
            url = str((part.get("image_url") or {}).get("url") or "")
            m = _DATA_URI_RE.match(url)
            if m:
                blocks.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": m.group(1),
                            "data": re.sub(r"\s+", "", m.group(2)),
                        },
                    }
                )
    return blocks or ""


def build_anthropic_payload(
    *,
    model: str,
    messages: List[Dict[str, Any]],
    params: Dict[str, Any],
    think_enabled: bool = False,
    thinking_budget: int = 1024,
) -> Tuple[Dict[str, Any], str]:
    """Convert OpenAI-shape messages to Native Anthropic /v1/messages with cache_control."""
    system_blocks: List[Dict[str, Any]] = []
    chat_msgs: List[Dict[str, Any]] = []

    for idx, m in enumerate(messages):
        role = str(m.get("role") or "user")
        content = m.get("content")
        if role == "system":
            txt = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            if txt.strip():
                blk: Dict[str, Any] = {"type": "text", "text": txt}
                # Pin cache_control on the first immutable Layer-0 system prefix block!
                if len(system_blocks) == 0:
                    blk["cache_control"] = {"type": "ephemeral"}
                system_blocks.append(blk)
            continue

        anth_role = "assistant" if role == "assistant" else "user"
        conv_c = _convert_content_to_anthropic(content)
        if chat_msgs and chat_msgs[-1]["role"] == anth_role:
            prev = chat_msgs[-1]["content"]
            if isinstance(prev, str) and isinstance(conv_c, str):
                chat_msgs[-1]["content"] = f"{prev}\n\n{conv_c}"
            else:
                prev_list = [{"type": "text", "text": prev}] if isinstance(prev, str) else list(prev)
                cur_list = [{"type": "text", "text": conv_c}] if isinstance(conv_c, str) else list(conv_c)
                chat_msgs[-1]["content"] = prev_list + cur_list
        else:
            chat_msgs.append({"role": anth_role, "content": conv_c})

    if not chat_msgs or chat_msgs[0]["role"] != "user":
        chat_msgs.insert(0, {"role": "user", "content": "开始"})

    max_tok = int(params.get("max_tokens") or 8192)
    body: Dict[str, Any] = {
        "model": model,
        "messages": chat_msgs,
        "max_tokens": max_tok,
        "temperature": float(params.get("temperature") if params.get("temperature") is not None else 0.7),
        "stream": True,
    }
    if system_blocks:
        body["system"] = system_blocks
    if think_enabled and max_tok >= 2048:
        budget = max(1024, min(max_tok - 512, int(thinking_budget or 1024)))
        body["thinking"] = {"type": "enabled", "budget_tokens": budget}
        # Anthropic extended thinking requires temperature == 1.0
        body["temperature"] = 1.0
    else:
        body["top_p"] = float(params.get("top_p") if params.get("top_p") is not None else 0.9)

    return body, "/messages"


async def stream_anthropic_chat(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    headers: Dict[str, str],
    body: Dict[str, Any],
) -> AsyncIterator[StreamDelta]:
    root = base_url.rstrip("/")
    if not root.endswith("/v1") and "/v1/" not in root:
        root = f"{root}/v1"
    url = f"{root}/messages"
    req_hdrs = dict(headers)
    req_hdrs.setdefault("anthropic-version", "2023-06-01")
    req_hdrs.setdefault("Content-Type", "application/json")

    async with client.stream("POST", url, headers=req_hdrs, json=body) as resp:
        if resp.status_code != 200:
            err_b = await resp.aread()
            raise httpx.HTTPStatusError(
                f"Claude API Error {resp.status_code}: {err_b.decode('utf-8', errors='ignore')[:500]}",
                request=resp.request,
                response=resp,
            )

        async for line in resp.aiter_lines():
            ln = line.strip()
            if not ln or not ln.startswith("data:"):
                continue
            payload = ln[5:].lstrip()
            try:
                ev = json.loads(payload)
            except json.JSONDecodeError:
                continue
            etype = ev.get("type")
            if etype == "error":
                raise RuntimeError(f"Claude Stream Error: {ev.get('error')}")
            if etype == "message_start":
                u = (ev.get("message") or {}).get("usage") or {}
                cr = int(u.get("cache_read_input_tokens") or 0)
                cc = int(u.get("cache_creation_input_tokens") or 0)
                pt = int(u.get("input_tokens") or 0)
                if cr or cc or pt:
                    yield StreamDelta(cache_read_tokens=cr, cache_creation_tokens=cc, prompt_tokens=pt)
            elif etype == "content_block_delta":
                delta = ev.get("delta") or {}
                dtype = delta.get("type")
                if dtype == "text_delta":
                    yield StreamDelta(text=str(delta.get("text") or ""))
                elif dtype == "thinking_delta":
                    yield StreamDelta(thinking=str(delta.get("thinking") or ""))
            elif etype == "message_delta":
                u = ev.get("usage") or {}
                yield StreamDelta(
                    completion_tokens=int(u.get("output_tokens") or 0),
                    finish_reason=str((ev.get("delta") or {}).get("stop_reason") or "stop"),
                )
