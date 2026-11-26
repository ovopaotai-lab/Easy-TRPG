# -*- coding: utf-8 -*-
"""SillyTavern-compatible regex script engine with scope & persistence modes."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger("easy_trpg.regex")


def _compile_regex_pattern(raw_pat: str) -> re.Pattern[str]:
    pat = raw_pat.strip()
    flags = 0
    if pat.startswith("/") and pat.rfind("/") > 0:
        last_slash = pat.rfind("/")
        flag_str = pat[last_slash + 1:]
        pat = pat[1:last_slash]
        if "i" in flag_str:
            flags |= re.IGNORECASE
        if "m" in flag_str:
            flags |= re.MULTILINE
        if "s" in flag_str:
            flags |= re.DOTALL
    else:
        flags = re.MULTILINE
    return re.compile(pat, flags)


def apply_regex_scripts(
    text: str,
    regex_list: Optional[List[Dict[str, Any]]],
    *,
    target_scope: int = 1,
    only_persistent: bool = False,
    only_prompt: bool = False,
) -> Tuple[str, List[str]]:
    """
    Apply matching regex rules to text.
    target_scope: 1=AI Output, 2=User Input, 4=World Info
    """
    if not text or not regex_list:
        return text, []

    working = text
    applied: List[str] = []
    for idx, rx in enumerate(regex_list):
        if not isinstance(rx, dict):
            continue
        if rx.get("enabled") is False or rx.get("disabled") is True:
            continue
        scope = int(rx.get("target_scope", 1) or 1)
        if not (scope & target_scope):
            continue
        is_render_only = bool(rx.get("is_only_render", rx.get("markdownOnly", False)))
        is_prompt_only = bool(rx.get("promptOnly", False))
        if only_persistent and (is_render_only or is_prompt_only):
            continue
        if only_prompt and is_render_only:
            continue

        pat_raw = str(rx.get("find_regex") or rx.get("findRegex") or rx.get("pattern") or "").strip()
        if not pat_raw:
            continue
        repl = str(rx.get("replace_str") if rx.get("replace_str") is not None else (rx.get("replaceString") or rx.get("replacement") or ""))
        try:
            comp = _compile_regex_pattern(pat_raw)
            new_text, n_subs = comp.subn(repl, working)
            if n_subs > 0:
                working = new_text
                applied.append(str(rx.get("name") or rx.get("scriptName") or f"regex#{idx+1}"))
        except re.error as exc:
            logger.debug("Invalid regex script %s: %s", pat_raw, exc)
    return working, applied
