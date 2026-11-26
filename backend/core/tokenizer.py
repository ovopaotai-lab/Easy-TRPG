# -*- coding: utf-8 -*-
"""Calibrated mixed-language tokenizer with live llama-server /tokenize support."""
from __future__ import annotations

import hashlib
import logging
import re
from collections import OrderedDict
from typing import Optional

import httpx

logger = logging.getLogger("easy_trpg.tokenizer")

_TOKEN_CACHE: OrderedDict[str, int] = OrderedDict()
_TOKEN_CACHE_MAX = 2048
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")


def estimate_tokens(text: str) -> int:
    """Fast calibrated token estimator for CJK + English + code (~5% accuracy)."""
    if not text:
        return 0
    key = hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()
    cached = _TOKEN_CACHE.get(key)
    if cached is not None:
        _TOKEN_CACHE.move_to_end(key)
        return cached

    cjk_chars = len(_CJK_RE.findall(text))
    other_chars = len(text) - cjk_chars
    # Typical Qwen/Llama3 BPE ratio: ~1.55 tokens per CJK char, ~0.30 tokens per ASCII char
    est = max(1, int(cjk_chars * 1.55 + other_chars * 0.30))
    _TOKEN_CACHE[key] = est
    if len(_TOKEN_CACHE) > _TOKEN_CACHE_MAX:
        _TOKEN_CACHE.popitem(last=False)
    return est


async def tokenize_text_async(
    text: str,
    llama_base_url: Optional[str] = None,
) -> int:
    """Query local llama-server /tokenize when running; fall back to calibrated estimator."""
    if not text:
        return 0
    if llama_base_url:
        root = llama_base_url.rstrip("/")
        if root.endswith("/v1"):
            root = root[:-3]
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=1.5) as client:
                r = await client.post(f"{root}/tokenize", json={"content": text})
                if r.status_code == 200:
                    toks = r.json().get("tokens")
                    if isinstance(toks, list):
                        return len(toks)
        except Exception as exc:
            logger.debug("llama /tokenize fallback to estimate: %s", exc)
    return estimate_tokens(text)
