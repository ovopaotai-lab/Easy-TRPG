# -*- coding: utf-8 -*-
"""Three-tier memory system: Deterministic State + Frozen Chapters + FTS5 Episodic Recall."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from backend.storage.db import UserDatabase

logger = logging.getLogger("easy_trpg.memory")


def build_frozen_chapters_block(chapters: List[Dict[str, Any]]) -> str:
    """Tier 2: Immutable archived chapter summaries (placed in Layer 0 prefix)."""
    if not chapters:
        return ""
    lines = ["【已归档章节纪要（不可变长期记忆）】"]
    for ch in chapters:
        num = ch.get("chapter_num", 1)
        title = ch.get("title") or f"第 {num} 章"
        summ = str(ch.get("summary") or "").strip()
        if summ:
            lines.append(f"- {title}：{summ}")
    return "\n".join(lines) if len(lines) > 1 else ""


def recall_episodic_snippets(
    db: UserDatabase,
    chat_id: str,
    query_text: str,
    *,
    excluded_node_ids: set[str],
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """Tier 3: Search older conversation turns outside the active window via FTS5."""
    clean = re.sub(r"[<>\[\]{}()\"'`,.。！？、：；\n]+", " ", query_text or "").strip()
    keywords = [w for w in clean.split() if len(w) >= 2][:6]
    if not keywords:
        return []
    q_str = " ".join(keywords)
    res = db.search_fts(q_str, scope="messages", chat_id=chat_id, limit=limit * 3)
    hits: List[Dict[str, Any]] = []
    for item in res.get("messages") or []:
        nid = str(item.get("node_id") or "")
        if not nid or nid in excluded_node_ids:
            continue
        snip = str(item.get("snippet") or "").strip()
        if snip:
            hits.append({"node_id": nid, "role": item.get("role", ""), "snippet": snip[:220]})
        if len(hits) >= limit:
            break
    return hits


def format_episodic_recall_block(snippets: List[Dict[str, Any]]) -> str:
    if not snippets:
        return ""
    lines = ["【远期伏笔与历史回忆召回】"]
    for s in snippets:
        role_lbl = "玩家" if s.get("role") == "user" else "剧情"
        lines.append(f"- [{role_lbl}] {s['snippet']}")
    return "\n".join(lines)
