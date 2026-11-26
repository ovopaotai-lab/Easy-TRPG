# -*- coding: utf-8 -*-
"""Cryptographic RPG dice roller supporting d20, CoC d100, PbtA 2d6, advantage/disadvantage."""
from __future__ import annotations

import re
import secrets
from typing import Any, Dict, List, Optional

_EXPR_RE = re.compile(
    r"^\s*(\d{1,2})?d(\d{1,4})(?:(kh|kl)(\d{1,2}))?(\s*[+-]\s*\d{1,4})?\s*$",
    re.IGNORECASE,
)


def roll_dice_expression(
    expr: str = "1d20",
    *,
    ruleset: str = "d20",
    difficulty: Optional[int] = None,
    skill_name: str = "",
    hidden: bool = False,
) -> Dict[str, Any]:
    """Roll cryptographic dice and evaluate outcome under the active TRPG ruleset."""
    raw = str(expr or "1d20").strip()
    low = raw.lower()
    if low in ("adv", "advantage", "优势"):
        raw = "2d20kh1"
    elif low in ("dis", "disadvantage", "劣势"):
        raw = "2d20kl1"
    elif low == "coc":
        raw = "1d100"
    elif low == "pbta":
        raw = "2d6"

    m = _EXPR_RE.match(raw)
    if not m:
        raise ValueError(f"无效骰子表达式: {expr}")

    count = max(1, min(20, int(m.group(1) or 1)))
    sides = max(2, min(1000, int(m.group(2))))
    keep_mode = (m.group(3) or "").lower()
    keep_n = max(1, min(count, int(m.group(4)))) if m.group(4) else count
    mod = int(re.sub(r"\s+", "", m.group(5) or "0"))

    rolls = [secrets.randbelow(sides) + 1 for _ in range(count)]
    if keep_mode == "kh":
        kept = sorted(rolls, reverse=True)[:keep_n]
    elif keep_mode == "kl":
        kept = sorted(rolls)[:keep_n]
    else:
        kept = list(rolls)

    raw_sum = sum(kept)
    total = raw_sum + mod

    tier = "neutral"
    tier_label = "结果已出"
    success: Optional[bool] = None

    rs = (ruleset or "d20").strip().lower()
    if rs == "d100" or (sides == 100 and count == 1):
        target = difficulty if difficulty is not None else 50
        if raw_sum <= 1 or (target >= 50 and raw_sum <= 5):
            tier, tier_label, success = "crit_success", "大成功", True
        elif raw_sum >= 100 or (target < 50 and raw_sum >= 96):
            tier, tier_label, success = "crit_fail", "大失败", False
        elif raw_sum <= max(1, target // 5):
            tier, tier_label, success = "extreme_success", "极难成功", True
        elif raw_sum <= max(1, target // 2):
            tier, tier_label, success = "hard_success", "困难成功", True
        elif raw_sum <= target:
            tier, tier_label, success = "success", "成功", True
        else:
            tier, tier_label, success = "fail", "失败", False
    elif rs == "2d6" or (sides == 6 and count == 2 and not keep_mode):
        if total >= 10:
            tier, tier_label, success = "crit_success", "完全成功 (10+)", True
        elif total >= 7:
            tier, tier_label, success = "mixed", "代价成功 (7~9)", True
        else:
            tier, tier_label, success = "fail", "失手 / 危机 (6-)", False
    elif sides == 20:
        natural = kept[0] if len(kept) == 1 else raw_sum
        dc = difficulty if difficulty is not None else 12
        if natural == 20:
            tier, tier_label, success = "crit_success", "大成功 (Nat 20)", True
        elif natural == 1:
            tier, tier_label, success = "crit_fail", "大失败 (Nat 1)", False
        elif total >= dc:
            tier, tier_label, success = "success", f"检定成功 (DC {dc})", True
        else:
            tier, tier_label, success = "fail", f"检定失败 (DC {dc})", False
    else:
        if difficulty is not None:
            success = total >= difficulty
            tier = "success" if success else "fail"
            tier_label = f"{'成功' if success else '失败'} (目标 {difficulty})"

    return {
        "expression": raw,
        "ruleset": rs,
        "skill": skill_name.strip(),
        "rolls": rolls,
        "kept": kept,
        "modifier": mod,
        "raw_total": raw_sum,
        "total": total,
        "difficulty": difficulty,
        "success": success,
        "tier": tier,
        "tier_label": tier_label,
        "hidden": bool(hidden),
    }


def format_dice_for_prompt(roll: Dict[str, Any]) -> str:
    skill = f"【{roll['skill']}】" if roll.get("skill") else ""
    diff = f" vs 目标 {roll['difficulty']}" if roll.get("difficulty") is not None else ""
    hidden_tag = "[暗骰] " if roll.get("hidden") else ""
    return (
        f"【系统真实检定结果】{hidden_tag}{skill}"
        f"投骰 {roll['expression']} = {roll['total']} (骰面 {roll['kept']}, 修正 {roll['modifier']:+d}{diff}) "
        f"-> 判定：{roll['tier_label']}。请严格依据此真实点数推演成败与后果。"
    )
