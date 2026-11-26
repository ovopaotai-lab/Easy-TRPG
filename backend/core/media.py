# -*- coding: utf-8 -*-
"""Async image optimization, deduplication, and gallery asset helpers."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

from backend.core.security import get_user_gallery_dir, sanitize_id
from backend.storage.db import get_user_db

logger = logging.getLogger("easy_trpg.media")


def compute_image_vhash(img: Image.Image) -> str:
    """16x16 grayscale average perceptual hash (256-bit hex)."""
    gray = img.convert("L").resize((16, 16), Image.Resampling.BILINEAR)
    pixels = list(gray.getdata())
    avg = sum(pixels) / max(1, len(pixels))
    bits = "".join("1" if p >= avg else "0" for p in pixels)
    return f"{int(bits, 2):064x}"


def vhash_hamming(h1: str, h2: str) -> int:
    try:
        return bin(int(h1, 16) ^ int(h2, 16)).count("1")
    except ValueError:
        return 999


def optimize_image_base64_sync(
    img_b64: str,
    max_dim: int = 896,
    quality: int = 76,
    min_bytes: int = 70_000,
) -> str:
    if not img_b64 or not isinstance(img_b64, str):
        return img_b64
    s = img_b64.strip()
    if s.startswith("/api/gallery/") or s.startswith("http"):
        return s
    m = re.match(r"^data:image/[^;]+;base64,(.+)$", s, flags=re.S)
    if not m:
        return s
    try:
        raw_bytes = base64.b64decode(re.sub(r"\s+", "", m.group(1)))
        if len(raw_bytes) <= min_bytes:
            return s
        with Image.open(io.BytesIO(raw_bytes)) as im_raw:
            im = im_raw.convert("RGB")
            if max(im.size) > max_dim:
                im.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=quality, optimize=True)
            out_bytes = buf.getvalue()
            if len(out_bytes) >= len(raw_bytes):
                return s
            return "data:image/jpeg;base64," + base64.b64encode(out_bytes).decode("utf-8")
    except Exception as exc:
        logger.debug("Image optimization skipped: %s", exc)
        return s


async def optimize_images_async(
    images: List[str],
    max_dim: int = 896,
    quality: int = 76,
    min_bytes: int = 70_000,
) -> List[str]:
    if not images:
        return []
    return await asyncio.gather(
        *[asyncio.to_thread(optimize_image_base64_sync, img, max_dim, quality, min_bytes) for img in images]
    )


def auto_save_to_gallery(
    username: str,
    img_b64: str,
    filename: Optional[str] = None,
    folder: Optional[str] = None,
) -> Optional[str]:
    if not img_b64 or not isinstance(img_b64, str):
        return None
    s = img_b64.strip()
    if s.startswith("/api/gallery/"):
        m = re.search(r"/api/gallery/(?:image|thumb)/([a-zA-Z0-9._-]+)", s)
        return sanitize_id(m.group(1)) if m else None
    raw_part = s
    if s.startswith("data:image"):
        m = re.match(r"^data:image/[^;]+;base64,(.+)$", s, flags=re.S)
        if not m:
            return None
        raw_part = m.group(1)
    try:
        raw_bytes = base64.b64decode(re.sub(r"\s+", "", raw_part))
    except Exception:
        return None

    sha = hashlib.sha256(raw_bytes).hexdigest()
    db = get_user_db(username)
    existing = db.find_gallery_by_sha256(sha)
    if existing:
        return str(existing["id"])

    gdir = get_user_gallery_dir(username)
    try:
        with Image.open(io.BytesIO(raw_bytes)) as im_raw:
            im = im_raw.convert("RGB")
            img_id = f"img_{sha[:12]}"
            out_path = gdir / f"{img_id}.jpg"
            thumb_path = gdir / "thumbs" / f"{img_id}.jpg"
            im.save(out_path, format="JPEG", quality=92, optimize=True)
            thumb = im.copy()
            thumb.thumbnail((320, 320))
            thumb.save(thumb_path, format="JPEG", quality=82, optimize=True)
            vhash = compute_image_vhash(im)
            db.upsert_gallery_asset(
                {
                    "id": img_id,
                    "filename": filename or f"{img_id}.jpg",
                    "folder": folder or "默认图库",
                    "sha256": sha,
                    "vhash": vhash,
                    "width": im.width,
                    "height": im.height,
                    "size_bytes": out_path.stat().st_size,
                    "created_at": time.time(),
                }
            )
            return img_id
    except Exception as exc:
        logger.warning("auto_save_to_gallery failed: %s", exc)
        return None


async def auto_save_images_to_gallery_async(username: str, images: List[str]) -> List[str]:
    if not images:
        return []
    res = await asyncio.gather(*[asyncio.to_thread(auto_save_to_gallery, username, im) for im in images])
    return [r for r in res if r]


def resolve_gallery_ref_to_data_url(username: str, raw_ref: str) -> str:
    s = str(raw_ref or "").strip()
    if not s:
        return ""
    if s.startswith("data:image/"):
        return s
    m = re.search(r"/api/gallery/(?:image|thumb)/([a-zA-Z0-9._-]+)", s)
    if m:
        aid = sanitize_id(m.group(1))
        gdir = get_user_gallery_dir(username)
        fp = gdir / f"{aid}.jpg"
        if fp.is_file():
            b64 = base64.b64encode(fp.read_bytes()).decode("utf-8")
            return f"data:image/jpeg;base64,{b64}"
    return ""


def deduplicate_user_gallery(username: str) -> Dict[str, int]:
    db = get_user_db(username)
    gdir = get_user_gallery_dir(username)
    items = db.list_gallery()
    before = len(items)
    valid = []
    removed_ids = []
    for it in items:
        iid = it["id"]
        fp = gdir / f"{iid}.jpg"
        if not fp.is_file():
            removed_ids.append(iid)
            continue
        if not it.get("vhash"):
            try:
                with Image.open(fp) as im:
                    it["vhash"] = compute_image_vhash(im)
                    db.upsert_gallery_asset(it)
            except Exception:
                pass
        valid.append(it)

    kept: List[Dict[str, Any]] = []
    for it in valid:
        vh = it.get("vhash") or ""
        dup = False
        if vh:
            for k in kept:
                if k.get("vhash") and vhash_hamming(vh, k["vhash"]) <= 3:
                    dup = True
                    break
        if dup:
            removed_ids.append(it["id"])
        else:
            kept.append(it)

    kept_set = {k["id"] for k in kept}
    for rid in set(removed_ids):
        if rid in kept_set:
            continue
        db.delete_gallery_asset(rid)
        for p in (gdir / f"{rid}.jpg", gdir / "thumbs" / f"{rid}.jpg"):
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass
    return {"before": before, "after": len(kept), "removed": before - len(kept)}
