# -*- coding: utf-8 -*-
"""Template variable & dice macro interpolation."""
from __future__ import annotations

import datetime
import re
import secrets
from typing import Any, Dict, List, Optional


def _eval_inline_roll(expr: str) -> str:
    m = re.match(r"^\s*(\d{1,2})d(\d{1,4})\s*([+-]\s*\d+)?\s*$", expr, re.I)
    if not m:
        return expr
    n = max(1, min(20, int(m.group(1))))
    sides = max(2, min(1000, int(m.group(2))))
    mod = int(re.sub(r"\s+", "", m.group(3) or "0"))
    rolls = [secrets.randbelow(sides) + 1 for _ in range(n)]
    return str(sum(rolls) + mod)


def interpolate_variables(
    text: str,
    prompt_vars: Optional[List[Dict[str, Any]]] = None,
    chat_inputs: Optional[Dict[str, Any]] = None,
    *,
    user_name: str = "玩家",
    char_name: str = "",
    persona_desc: str = "",
) -> str:
    if not text:
        return ""
    values: Dict[str, str] = {}
    for pv in prompt_vars or []:
        if isinstance(pv, dict):
            k = str(pv.get("key") or pv.get("name") or "").strip()
            if k:
                values[k] = str(pv.get("default") or "")
    for k, v in (chat_inputs or {}).items():
        if k:
            values[str(k)] = "" if v is None else str(v)

    now = datetime.datetime.now()
    builtin = {
        "user": user_name or values.get("user") or "玩家",
        "char": char_name or values.get("char") or "主持人",
        "persona": persona_desc or values.get("persona") or "",
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "weekday": now.strftime("%A"),
    }

    def _repl(match: re.Match) -> str:
        raw_key = match.group(1).strip()
        low = raw_key.lower()
        if low.startswith("roll:"):
            return _eval_inline_roll(raw_key[5:])
        if low in builtin:
            return builtin[low]
        if raw_key in values:
            return values[raw_key]
        return match.group(0)

    out = re.sub(r"\{\{([^{}]+)\}\}", _repl, text)
    if values:
        def _single_repl(match: re.Match) -> str:
            k = match.group(1).strip()
            return values.get(k, match.group(0))
        out = re.sub(r"\{([a-zA-Z0-9_\u4e00-\u9fa5-]+)\}", _single_repl, out)
    return out
