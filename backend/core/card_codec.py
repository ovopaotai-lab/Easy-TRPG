# -*- coding: utf-8 -*-
"""Bidirectional SillyTavern V2/V3 & Easy-TRPG Game Card PNG/JSON codec."""
from __future__ import annotations

import base64
import io
import json
import re
import struct
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from backend.config import normalize_project_schema, safe_int
from backend.core.media import resolve_gallery_ref_to_data_url
from backend.core.security import get_user_gallery_dir, sanitize_id


def _safe_decompress(raw: bytes, max_bytes: int = 8 * 1024 * 1024) -> bytes:
    d = zlib.decompressobj()
    out = d.decompress(raw, max_bytes)
    if d.unconsumed_tail:
        raise ValueError("PNG chunk payload exceeds safety limit")
    return out


def extract_png_card_json(png_bytes: bytes) -> Dict[str, Any]:
    """Read SillyTavern V2 ('chara') or V3 ('ccv3') JSON metadata from PNG bytes."""
    if len(png_bytes) < 12 or png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("不是有效的 PNG 文件")
    pos = 8
    found_json: Optional[Dict[str, Any]] = None
    while pos + 12 <= len(png_bytes):
        length = struct.unpack(">I", png_bytes[pos:pos + 4])[0]
        if pos + 12 + length > len(png_bytes):
            break
        ctype = png_bytes[pos + 4:pos + 8].decode("latin-1", errors="ignore")
        cdata = png_bytes[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctype in ("tEXt", "zTXt", "iTXt"):
            nul = cdata.find(b"\x00")
            if nul == -1:
                continue
            kw = cdata[:nul].decode("utf-8", errors="ignore").strip().lower()
            if kw in ("chara", "ccv3"):
                try:
                    if ctype == "tEXt":
                        payload = cdata[nul + 1:]
                    elif ctype == "zTXt":
                        payload = _safe_decompress(cdata[nul + 2:])
                    else:
                        cursor = nul + 1
                        comp_flag = cdata[cursor]
                        cursor += 2
                        for _ in range(2):
                            np = cdata.find(b"\x00", cursor)
                            if np == -1:
                                break
                            cursor = np + 1
                        raw_part = cdata[cursor:]
                        payload = _safe_decompress(raw_part) if comp_flag == 1 else raw_part
                    text_str = payload.decode("utf-8", errors="ignore").strip()
                    if text_str.startswith("{"):
                        parsed = json.loads(text_str)
                    else:
                        b64 = re.sub(r"\s+", "", text_str)
                        b64 += "=" * ((-len(b64)) % 4)
                        parsed = json.loads(base64.b64decode(b64).decode("utf-8-sig"))
                    if kw == "ccv3":
                        return parsed
                    found_json = parsed
                except Exception:
                    continue
        elif ctype == "IEND":
            break
    if found_json:
        return found_json
    raise ValueError("PNG 中未包含角色卡/游戏卡数据")


def inject_png_text_chunks(png_bytes: bytes, chunks_kv: List[Tuple[str, str]]) -> bytes:
    if len(png_bytes) < 12 or png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("无效的 PNG 字节流")
    out = bytearray(png_bytes[:8])
    pos = 8
    injected = False
    extra = bytearray()
    for kw, val in chunks_kv:
        kw_b = kw.encode("latin-1", errors="ignore")[:79]
        b64_b = base64.b64encode(val.encode("utf-8"))
        cdata = kw_b + b"\x00" + b64_b
        crc = zlib.crc32(b"tEXt" + cdata) & 0xFFFFFFFF
        extra.extend(struct.pack(">I", len(cdata)))
        extra.extend(b"tEXt")
        extra.extend(cdata)
        extra.extend(struct.pack(">I", crc))

    while pos + 12 <= len(png_bytes):
        length = struct.unpack(">I", png_bytes[pos:pos + 4])[0]
        if pos + 12 + length > len(png_bytes):
            break
        ctype = png_bytes[pos + 4:pos + 8]
        cfull = png_bytes[pos:pos + 12 + length]
        pos += 12 + length
        if ctype in (b"tEXt", b"zTXt", b"iTXt"):
            np = cfull[8:-4].find(b"\x00")
            if np != -1 and cfull[8:8 + np].decode("latin-1", errors="ignore").strip().lower() in ("chara", "ccv3"):
                continue
        if ctype == b"IEND" and not injected:
            out.extend(extra)
            injected = True
        out.extend(cfull)
        if ctype == b"IEND":
            break
    if not injected:
        out.extend(extra)
    return bytes(out)


def _replace_char_macro(text: str, card_name: str) -> str:
    if not text or not card_name:
        return text
    return re.sub(r"\{\{\s*char\s*\}\}|<BOT>", lambda _m: card_name, text, flags=re.IGNORECASE)


def normalize_character_book_entries(raw_cb: Any, card_name: str = "") -> List[Dict[str, Any]]:
    if not raw_cb:
        return []
    entries_raw: List[Any] = []
    if isinstance(raw_cb, dict):
        eo = raw_cb.get("entries")
        entries_raw = eo if isinstance(eo, list) else (list(eo.values()) if isinstance(eo, dict) else [])
    elif isinstance(raw_cb, list):
        entries_raw = raw_cb

    out: List[Dict[str, Any]] = []
    for idx, item in enumerate(entries_raw):
        if not isinstance(item, dict) or item.get("enabled") is False or item.get("disable") is True:
            continue
        content = _replace_char_macro(str(item.get("content") or item.get("entry") or "").strip(), card_name)
        if not content:
            continue
        raw_keys = item.get("keys") if "keys" in item else item.get("key", [])
        keys = (
            [_replace_char_macro(k.strip(), card_name) for k in raw_keys.replace("，", ",").split(",") if k.strip()]
            if isinstance(raw_keys, str)
            else [_replace_char_macro(str(k).strip(), card_name) for k in (raw_keys or []) if str(k).strip()]
        )
        raw_sec = item.get("secondary_keys") if "secondary_keys" in item else item.get("keysecondary", [])
        sec_keys = (
            [_replace_char_macro(k.strip(), card_name) for k in raw_sec.replace("，", ",").split(",") if k.strip()]
            if isinstance(raw_sec, str)
            else [_replace_char_macro(str(k).strip(), card_name) for k in (raw_sec or []) if str(k).strip()]
        )
        constant = bool(item.get("constant", False))
        if not keys and not constant:
            continue
        pos = str(item.get("position") if item.get("position") is not None else item.get("value_region", "System")).strip().lower()
        pos_map = {"2": "Prefix", "prefix": "Prefix", "3": "Suffix", "suffix": "Suffix"}
        out.append(
            {
                "id": str(item.get("id") or item.get("uid") or f"cb_{idx}"),
                "name": _replace_char_macro(str(item.get("comment") or item.get("name") or f"{card_name or '角色'}词条#{idx+1}"), card_name),
                "group": str(item.get("group") or (f"角色：{card_name}" if card_name else "角色世界书")),
                "enabled": True,
                "enable": True,
                "constant": constant,
                "keys": keys,
                "secondary_keys": sec_keys,
                "selective": bool(item.get("selective", bool(sec_keys))),
                "selective_logic": safe_int(item.get("selective_logic", item.get("selectiveLogic", 0)), 0),
                "case_sensitive": bool(item.get("case_sensitive", item.get("caseSensitive", False))),
                "exclude_recursion": bool(item.get("exclude_recursion", item.get("excludeRecursion", False))),
                "sort": safe_int(item.get("insertion_order", item.get("order", 100)), 100),
                "depth": safe_int(item.get("scan_depth", item.get("scanDepth", item.get("depth", 5))), 5),
                "probability": safe_int(item.get("probability", 100), 100),
                "key_region": 6,
                "value_region": pos_map.get(pos, "System"),
                "content": content,
                "value": content,
            }
        )
    return out


def parse_character_card_payload(raw_json: Dict[str, Any], avatar_b64: str = "") -> Dict[str, Any]:
    """Parse SillyTavern V1/V2/V3 JSON into normalized Character Card."""
    data_part = raw_json.get("data") if isinstance(raw_json.get("data"), dict) else raw_json
    ext_part = data_part.get("extensions") if isinstance(data_part.get("extensions"), dict) else {}

    def _pick(field: str, default: str = "") -> str:
        val = data_part.get(field)
        if val in (None, "") and raw_json is not data_part:
            val = raw_json.get(field)
        return str(val or default).strip()

    name = _pick("name", "未命名角色")
    cb_raw = data_part.get("character_book") or raw_json.get("character_book") or ext_part.get("character_book")
    alt_raw = data_part.get("alternate_greetings") or raw_json.get("alternate_greetings") or []
    return {
        "name": name,
        "avatar": avatar_b64 or _pick("avatar"),
        "description": _replace_char_macro(_pick("description"), name),
        "personality": _replace_char_macro(_pick("personality"), name),
        "scenario": _replace_char_macro(_pick("scenario"), name),
        "first_mes": _replace_char_macro(_pick("first_mes"), name),
        "mes_example": _replace_char_macro(_pick("mes_example"), name),
        "system_prompt": _replace_char_macro(_pick("system_prompt"), name),
        "post_history_instructions": _replace_char_macro(_pick("post_history_instructions"), name),
        "alternate_greetings": [_replace_char_macro(str(g), name) for g in alt_raw if str(g).strip()],
        "creator": _pick("creator"),
        "creator_notes": _pick("creator_notes"),
        "tags": [str(t).strip() for t in (data_part.get("tags") or raw_json.get("tags") or []) if str(t).strip()],
        "character_book": normalize_character_book_entries(cb_raw, name),
        "extensions": ext_part,
    }


def _load_cjk_font(size: int, bold: bool = False):
    cands = (
        [r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\msyh.ttc"]
        if bold
        else [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"]
    )
    for fp in cands:
        if Path(fp).exists():
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                pass
    return ImageFont.load_default()


def project_to_st_card_v3(proj: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize an Easy-TRPG project into SillyTavern V2/V3 + Easy-TRPG extension payload."""
    ogs = proj.get("opening_greetings") or []
    first_mes = str(proj.get("opening_statement") or (ogs[0].get("content") if ogs else "") or "")
    alt_greets = [str(g.get("content") or "") for g in ogs[1:] if isinstance(g, dict) and g.get("content")]
    wb_entries = []
    for idx, w in enumerate(proj.get("world_book") or []):
        if not isinstance(w, dict):
            continue
        wb_entries.append(
            {
                "id": idx,
                "keys": w.get("keys") or [],
                "secondary_keys": w.get("secondary_keys") or [],
                "comment": w.get("name") or f"词条#{idx+1}",
                "content": w.get("content") or w.get("value") or "",
                "constant": bool(w.get("constant", False)),
                "selective": bool(w.get("selective", True)),
                "insertion_order": safe_int(w.get("sort"), 100),
                "enabled": w.get("enabled", True) is not False,
                "position": "before_char",
            }
        )
    return {
        "spec": "chara_card_v3",
        "spec_version": "3.0",
        "name": proj.get("name", "未命名剧本"),
        "description": proj.get("description", ""),
        "system_prompt": proj.get("system_prompt", ""),
        "first_mes": first_mes,
        "alternate_greetings": alt_greets,
        "data": {
            "name": proj.get("name", "未命名剧本"),
            "description": proj.get("description", ""),
            "system_prompt": proj.get("system_prompt", ""),
            "post_history_instructions": proj.get("suffix", ""),
            "first_mes": first_mes,
            "alternate_greetings": alt_greets,
            "creator": proj.get("author", "Easy-TRPG"),
            "creator_notes": proj.get("description", ""),
            "tags": proj.get("tags") or [],
            "character_book": {"name": proj.get("name", ""), "entries": wb_entries},
            "extensions": {
                "easy_trpg_project": proj,
                "custom_css": proj.get("custom_css", ""),
                "detailed_description": proj.get("detailed_description", ""),
            },
        },
    }


def st_card_to_project(raw_json: Dict[str, Any], cover_b64: str = "", global_defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Import SillyTavern V2/V3 card or Easy-TRPG exported card into normalized project dict."""
    data_part = raw_json.get("data") if isinstance(raw_json.get("data"), dict) else raw_json
    ext_part = data_part.get("extensions") if isinstance(data_part.get("extensions"), dict) else {}
    embedded_proj = ext_part.get("easy_trpg_project")
    if isinstance(embedded_proj, dict) and embedded_proj.get("name"):
        p = dict(embedded_proj)
        p.pop("id", None)
        if cover_b64:
            p["icon"] = cover_b64
            p["avatar"] = cover_b64
        return normalize_project_schema(p, {}, global_defaults=global_defaults)

    parsed = parse_character_card_payload(raw_json, cover_b64)
    name = parsed["name"]
    sys_parts = []
    if parsed["system_prompt"]:
        sys_parts.append(parsed["system_prompt"])
    if parsed["description"]:
        sys_parts.append(f"【角色与设定】\n{parsed['description']}")
    if parsed["personality"]:
        sys_parts.append(f"【性格特征】\n{parsed['personality']}")
    if parsed["scenario"]:
        sys_parts.append(f"【场景背景】\n{parsed['scenario']}")
    if parsed["mes_example"]:
        sys_parts.append(f"【对话范例】\n{parsed['mes_example']}")

    ogs = []
    if parsed["first_mes"]:
        ogs.append({"id": "og_1", "title": "默认开场", "content": parsed["first_mes"]})
    for idx, ag in enumerate(parsed["alternate_greetings"]):
        ogs.append({"id": f"og_{idx+2}", "title": f"分支开场 #{idx+2}", "content": ag})

    proj_payload = {
        "name": name,
        "icon": cover_b64 or parsed.get("avatar", ""),
        "avatar": cover_b64 or parsed.get("avatar", ""),
        "description": parsed.get("creator_notes") or parsed.get("description", "")[:160],
        "detailed_description": str(ext_part.get("detailed_description") or ""),
        "custom_css": str(ext_part.get("custom_css") or ""),
        "tags": parsed.get("tags") or [],
        "simple_mode": False,
        "cot_enabled": True,
        "status_panel_enabled": False,
        "system_prompt": "\n\n".join(sys_parts).strip(),
        "suffix": parsed.get("post_history_instructions", ""),
        "opening_greetings": ogs,
        "opening_statement": parsed.get("first_mes", ""),
        "world_book": parsed.get("character_book") or [],
    }
    return normalize_project_schema(proj_payload, {}, global_defaults=global_defaults)


def render_game_card_poster_png(proj: Dict[str, Any], username: str) -> bytes:
    """Render clean stylized 600x840 poster PNG embedding V3 card JSON chunks."""
    W, H = 600, 840
    cover_ref = proj.get("icon") or proj.get("avatar") or (proj.get("appearance") or {}).get("bg_image") or ""
    cover_url = resolve_gallery_ref_to_data_url(username, str(cover_ref))
    canvas = Image.new("RGBA", (W, H), (20, 18, 16, 255))
    if cover_url.startswith("data:image/"):
        try:
            b64 = cover_url.split(",", 1)[1]
            src = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")
            scale = max(W / max(1, src.width), H / max(1, src.height))
            nw, nh = max(1, int(src.width * scale)), max(1, int(src.height * scale))
            resized = src.resize((nw, nh), Image.Resampling.LANCZOS)
            canvas = resized.crop(((nw - W) // 2, (nh - H) // 2, (nw - W) // 2 + W, (nh - H) // 2 + H))
        except Exception:
            pass

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for y in range(H // 2, H):
        ratio = (y - H // 2) / max(1, H - H // 2)
        od.line([(0, y), (W, y)], fill=(14, 12, 11, min(235, int(235 * (ratio ** 1.3)))))
    od.rounded_rectangle([20, 20, W - 20, H - 20], radius=18, outline=(212, 163, 89, 140), width=2)
    canvas = Image.alpha_composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas)

    f_title = _load_cjk_font(34, bold=True)
    f_sub = _load_cjk_font(18, bold=False)
    title = str(proj.get("name") or "Easy-TRPG")[:20]
    desc = str(proj.get("description") or "Easy-TRPG V2 Card")[:60]
    draw.text((40, H - 180), title, font=f_title, fill=(240, 232, 218, 255))
    draw.text((40, H - 120), desc, font=f_sub, fill=(190, 180, 165, 255))
    draw.text((40, H - 64), f"EASY-TRPG · {proj.get('category', '跑团')}", font=f_sub, fill=(212, 163, 89, 255))

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    card_json = json.dumps(project_to_st_card_v3(proj), ensure_ascii=False)
    return inject_png_text_chunks(buf.getvalue(), [("chara", card_json), ("ccv3", card_json)])
