# -*- coding: utf-8 -*-
"""AI output sanitizer, thinking extractor, loop detector, and choice parser."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from backend.trpg.state_engine import strip_state_patch_tags

_ARTIFACT_TAG_RE = re.compile(
    r"</?(?:im_end|im_start|endoftext|eot_id|start_header_id|end_header_id|pad|bos|eos)[^>]*>",
    re.IGNORECASE,
)
_THINK_RE = re.compile(r"<think(?:ing)?>([\s\S]*?)</think(?:ing)?>", re.IGNORECASE)
_MEMORY_RE = re.compile(r"<memory>[\s\S]*?</memory>", re.IGNORECASE)
_STATUS_RE = re.compile(r"<status(?:\s+[^>]*)?>[\s\S]*?</status>|＜status＞[\s\S]*?＜/status＞", re.IGNORECASE)
_CHOICE_LINE_RE = re.compile(r"^\s*([1-9])[\.、．\)]\s+(.+)$")
_DICE_HINT_RE = re.compile(r"[【\[]\s*🎲\s*([^】\]]+)[】\]]")


def strip_distilled_artifact_tags(text: str) -> str:
    return _ARTIFACT_TAG_RE.sub("", text or "")


def strip_thinking_blocks(text: str) -> str:
    if not text:
        return ""
    cleaned = _THINK_RE.sub("", text)
    if re.search(r"</think(?:ing)?>", cleaned, re.I) and not re.search(r"<think(?:ing)?>", cleaned, re.I):
        cleaned = re.split(r"</think(?:ing)?>", cleaned, maxsplit=1, flags=re.I)[-1]
    return cleaned.strip()


def extract_thinking_block(text: str) -> Tuple[str, str]:
    """Return (thinking_text, rest_without_thinking)."""
    if not text:
        return "", ""
    matches = _THINK_RE.findall(text)
    think = "\n".join(m.strip() for m in matches if m.strip())
    rest = strip_thinking_blocks(text)
    return think, rest


def detect_and_trim_stream_loop(text: str) -> Tuple[str, bool]:
    """Detect degenerate n-gram or line repetition loops during local model streaming."""
    if not text or len(text) < 400:
        return text, False
    lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) >= 12]
    if len(lines) >= 6:
        tail = lines[-1]
        if lines[-6:].count(tail) >= 4:
            first_pos = text.find(tail)
            if first_pos > 0:
                return text[: first_pos + len(tail)].rstrip(), True
    # Check repeating 60-char block at the very end
    tail_blk = text[-80:]
    if len(tail_blk) == 80 and text[:-80].count(tail_blk) >= 2:
        idx = text.find(tail_blk)
        return text[: idx + len(tail_blk)].rstrip(), True
    return text, False


def build_prompt_frozen_content(raw_ai_output: str) -> str:
    """
    Create the immutable prompt_content saved on write for KV-cache stability:
    strips thinking, <state_patch>, and verbose <status> walls so future turns
    NEVER need to rewrite history turn N-3!
    """
    txt = strip_distilled_artifact_tags(strip_thinking_blocks(raw_ai_output))
    txt = strip_state_patch_tags(txt)
    txt = _STATUS_RE.sub("", txt)
    txt = _MEMORY_RE.sub("", txt)
    return re.sub(r"\n{3,}", "\n\n", txt).strip()


def extract_action_choices(text: str) -> List[Dict[str, Any]]:
    """Extract numbered action choices + embedded [🎲...] dice hints."""
    clean = strip_thinking_blocks(text or "")
    lines = clean.splitlines()
    choices: List[Dict[str, Any]] = []
    for ln in reversed(lines):
        m = _CHOICE_LINE_RE.match(ln)
        if m:
            raw_opt = m.group(2).strip()
            dm = _DICE_HINT_RE.search(raw_opt)
            choices.append(
                {
                    "index": int(m.group(1)),
                    "text": raw_opt,
                    "dice_skill": dm.group(1).strip() if dm else "",
                }
            )
        elif choices:
            # Stop once we pass above the contiguous trailing option block
            if ln.strip() and not re.search(r"你打算怎么做|接下来|你的选择", ln):
                break
    choices.reverse()
    return choices
