# -*- coding: utf-8 -*-
"""Native Google Gemini API adapter (BLOCK_NONE safety + systemInstruction + thought parts)."""
from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator, Dict, List

import httpx

from backend.providers.base import StreamDelta

_DATA_URI_RE = re.compile(r"^data:(image/[^;]+);base64,(.+)$", re.S)

GEMINI_SAFETY_NONE = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
]


def _to_gemini_parts(content: Any) -> List[Dict[str, Any]]:
    if isinstance(content, str):
        return [{"text": content}] if content else []
    if not isinstance(content, list):
        return [{"text": str(content)}]
    parts: List[Dict[str, Any]] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            txt = str(item.get("text") or "")
            if txt:
                parts.append({"text": txt})
        elif item.get("type") == "image_url":
            url = str((item.get("image_url") or {}).get("url") or "")
            m = _DATA_URI_RE.match(url)
            if m:
                parts.append(
                    {
                        "inlineData": {
                            "mimeType": m.group(1),
                            "data": re.sub(r"\s+", "", m.group(2)),
                        }
                    }
                )
        elif item.get("type") == "input_audio":
            ia = item.get("input_audio") or {}
            fmt = str(ia.get("format") or "mp3").lower()
            data = re.sub(r"\s+", "", str(ia.get("data") or ""))
            if data:
                mime_map = {
                    "mp3": "audio/mp3",
                    "wav": "audio/wav",
                    "aac": "audio/aac",
                    "ogg": "audio/ogg",
                    "m4a": "audio/mp4",
                    "flac": "audio/flac",
                }
                parts.append(
                    {
                        "inlineData": {
                            "mimeType": mime_map.get(fmt, "audio/mp3"),
                            "data": data,
                        }
                    }
                )
    return parts


def build_gemini_payload(
    *,
    model: str,
    messages: List[Dict[str, Any]],
    params: Dict[str, Any],
    think_enabled: bool = True,
    thinking_budget: int = 1024,
) -> Dict[str, Any]:
    sys_texts: List[str] = []
    contents: List[Dict[str, Any]] = []
    for m in messages:
        role = str(m.get("role") or "user")
        if role == "system":
            c = m.get("content")
            txt = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
            if txt.strip():
                sys_texts.append(txt.strip())
            continue
        g_role = "model" if role == "assistant" else "user"
        parts = _to_gemini_parts(m.get("content"))
        if not parts:
            continue
        if contents and contents[-1]["role"] == g_role:
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": g_role, "parts": parts})

    if not contents:
        contents.append({"role": "user", "parts": [{"text": "开始"}]})

    gen_cfg: Dict[str, Any] = {
        "temperature": float(params.get("temperature") if params.get("temperature") is not None else 0.7),
        "topP": float(params.get("top_p") if params.get("top_p") is not None else 0.9),
        "topK": max(1, int(params.get("top_k") or 40)),
        "maxOutputTokens": int(params.get("max_tokens") or 8192),
    }
    if "2.5" in model.lower() or "3" in model.lower() or "thinking" in model.lower():
        gen_cfg["thinkingConfig"] = {
            "thinkingBudget": max(256, int(thinking_budget or 1024)) if think_enabled else 0,
            "includeThoughts": bool(think_enabled),
        }

    body: Dict[str, Any] = {
        "contents": contents,
        "generationConfig": gen_cfg,
        "safetySettings": GEMINI_SAFETY_NONE,
    }
    if sys_texts:
        body["systemInstruction"] = {"parts": [{"text": "\n\n".join(sys_texts)}]}
    return body


async def stream_gemini_chat(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    api_key: str,
    model: str,
    headers: Dict[str, str],
    body: Dict[str, Any],
) -> AsyncIterator[StreamDelta]:
    root = base_url.rstrip("/")
    if root.endswith("/v1beta/openai"):
        root = root[:-len("/openai")]
    elif not root.endswith("/v1beta") and not root.endswith("/v1"):
        root = f"{root}/v1beta"
    clean_model = model[7:] if model.startswith("models/") else model
    url = f"{root}/models/{clean_model}:streamGenerateContent?alt=sse"
    req_hdrs = {"Content-Type": "application/json"}
    if api_key:
        req_hdrs["x-goog-api-key"] = api_key
    for k, v in headers.items():
        if k.lower() != "authorization":
            req_hdrs[k] = v

    async with client.stream("POST", url, headers=req_hdrs, json=body) as resp:
        if resp.status_code != 200:
            err_b = await resp.aread()
            raise httpx.HTTPStatusError(
                f"Gemini API Error {resp.status_code}: {err_b.decode('utf-8', errors='ignore')[:500]}",
                request=resp.request,
                response=resp,
            )

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
            if chunk.get("error"):
                raise RuntimeError(f"Gemini Error: {chunk['error']}")
            cands = chunk.get("candidates") or []
            c0 = cands[0] if cands else {}
            parts = ((c0.get("content") or {}).get("parts")) or []
            usage = chunk.get("usageMetadata") or {}
            txt_parts = []
            thk_parts = []
            for p in parts:
                if not isinstance(p, dict):
                    continue
                if p.get("thought"):
                    thk_parts.append(str(p.get("text") or ""))
                elif "text" in p:
                    txt_parts.append(str(p.get("text") or ""))
            yield StreamDelta(
                text="".join(txt_parts),
                thinking="".join(thk_parts),
                cache_read_tokens=int(usage.get("cachedContentTokenCount") or 0),
                prompt_tokens=int(usage.get("promptTokenCount") or 0),
                completion_tokens=int(usage.get("candidatesTokenCount") or 0),
                finish_reason=str(c0.get("finishReason") or ""),
                raw=chunk,
            )
