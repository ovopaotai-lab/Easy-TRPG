# -*- coding: utf-8 -*-
"""Gallery asset storage (images + HTML5 videos), thumbnails, folders, and deduplication endpoints."""
from __future__ import annotations

import base64
import hashlib
import io
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel

from backend.core.auth import get_current_user
from backend.core.media import auto_save_to_gallery, deduplicate_user_gallery
from backend.core.security import get_user_gallery_dir, sanitize_id
from backend.core.video_processor import ensure_video_processed_async
from backend.storage.db import get_user_db

router = APIRouter()

VIDEO_MIME_BY_EXT: Dict[str, str] = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".m4v": "video/mp4",
    ".ogg": "video/ogg",
}
_EXT_BY_CONTENT_TYPE: Dict[str, str] = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "video/x-m4v": ".m4v",
    "video/ogg": ".ogg",
}
MAX_VIDEO_UPLOAD_BYTES = 200 * 1024 * 1024


def _find_video_file(gdir: Path, safe_id: str) -> Optional[Tuple[Path, str]]:
    vdir = gdir / "videos"
    if not vdir.is_dir():
        return None
    for ext, mime in VIDEO_MIME_BY_EXT.items():
        cand = vdir / f"{safe_id}{ext}"
        if cand.is_file():
            return cand, mime
    return None


def _save_video_poster(gdir: Path, vid_id: str, poster_base64: str) -> bool:
    if not poster_base64:
        return False
    m = re.match(r"^data:image/[^;]+;base64,(.+)$", poster_base64.strip(), flags=re.S)
    raw_part = m.group(1) if m else poster_base64.strip()
    try:
        raw_bytes = base64.b64decode(re.sub(r"\s+", "", raw_part))
        with Image.open(io.BytesIO(raw_bytes)) as im_raw:
            thumb = im_raw.convert("RGB")
            thumb.thumbnail((320, 320))
            thumbs_dir = gdir / "thumbs"
            thumbs_dir.mkdir(parents=True, exist_ok=True)
            thumb.save(thumbs_dir / f"{vid_id}.jpg", format="JPEG", quality=82, optimize=True)
        return True
    except Exception:
        return False


class GalleryUploadReq(BaseModel):
    image_base64: str
    filename: Optional[str] = None
    folder: Optional[str] = None


@router.get("/api/gallery")
def get_gallery(username: str = Depends(get_current_user)):
    return get_user_db(username).list_gallery()


@router.post("/api/gallery/upload")
def upload_to_gallery(req: GalleryUploadReq, username: str = Depends(get_current_user)):
    img_id = auto_save_to_gallery(username, req.image_base64, req.filename, req.folder)
    if not img_id:
        raise HTTPException(status_code=400, detail="保存图片失败")
    return {
        "status": "ok",
        "id": img_id,
        "media_type": "image",
        "folder": req.folder or "默认图库",
        "url": f"/api/gallery/image/{img_id}",
        "thumb_url": f"/api/gallery/thumb/{img_id}",
    }


@router.post("/api/gallery/upload_video")
async def upload_video_to_gallery(
    file: UploadFile = File(...),
    poster_base64: Optional[str] = Form(None),
    folder: Optional[str] = Form("视频素材"),
    username: str = Depends(get_current_user),
):
    orig_name = Path(file.filename or "video.mp4").name
    ext = Path(orig_name).suffix.lower()
    if ext not in VIDEO_MIME_BY_EXT:
        ext = _EXT_BY_CONTENT_TYPE.get((file.content_type or "").lower().split(";")[0].strip(), "")
    if ext not in VIDEO_MIME_BY_EXT:
        raise HTTPException(status_code=400, detail="仅支持 MP4 / WebM / MOV / M4V / OGG 视频格式")

    gdir = get_user_gallery_dir(username)
    vdir = gdir / "videos"
    vdir.mkdir(parents=True, exist_ok=True)
    tmp_path = vdir / f".upload_{uuid.uuid4().hex[:10]}{ext}"
    hasher = hashlib.sha256()
    total_bytes = 0

    try:
        with open(tmp_path, "wb") as wf:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_VIDEO_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="单个视频大小不能超过 200 MB")
                hasher.update(chunk)
                wf.write(chunk)
        if total_bytes <= 0:
            raise HTTPException(status_code=400, detail="视频文件为空")

        sha = hasher.hexdigest()
        db = get_user_db(username)
        existing = db.find_gallery_by_sha256(sha)
        if existing and str(existing.get("id", "")).startswith("vid_"):
            vid_id = str(existing["id"])
            tmp_path.unlink(missing_ok=True)
        else:
            vid_id = f"vid_{sha[:12]}"
            final_path = vdir / f"{vid_id}{ext}"
            os.replace(tmp_path, final_path)
            if poster_base64:
                _save_video_poster(gdir, vid_id, poster_base64)
            db.upsert_gallery_asset(
                {
                    "id": vid_id,
                    "filename": orig_name,
                    "folder": (folder or "视频素材").strip() or "视频素材",
                    "sha256": sha,
                    "vhash": "",
                    "width": 0,
                    "height": 0,
                    "size_bytes": total_bytes,
                    "created_at": time.time(),
                }
            )
    except HTTPException:
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"保存视频失败: {exc}")

    clean_folder = (folder or "视频素材").strip() or "视频素材"
    v_meta = await ensure_video_processed_async(username, vid_id, orig_filename=orig_name)
    if v_meta:
        total_bytes = int(v_meta.get("size_bytes") or total_bytes)
        db.upsert_gallery_asset(
            {
                "id": vid_id,
                "filename": orig_name,
                "folder": clean_folder,
                "sha256": sha,
                "vhash": "",
                "width": int(v_meta.get("width") or 0),
                "height": int(v_meta.get("height") or 0),
                "size_bytes": total_bytes,
                "created_at": existing.get("created_at") if existing else time.time(),
            }
        )

    transcript_preview = str((v_meta or {}).get("transcript") or "").strip()
    if len(transcript_preview) > 160:
        transcript_preview = transcript_preview[:160] + "..."

    return {
        "status": "ok",
        "id": vid_id,
        "media_type": "video",
        "filename": orig_name,
        "folder": clean_folder,
        "url": f"/api/gallery/video/{vid_id}",
        "thumb_url": f"/api/gallery/thumb/{vid_id}",
        "audio_url": f"/api/gallery/audio/{vid_id}" if (v_meta or {}).get("has_audio") else "",
        "size_bytes": total_bytes,
        "duration_sec": (v_meta or {}).get("duration_sec") or 0,
        "frame_count": int((v_meta or {}).get("frame_count") or 0),
        "has_audio": bool((v_meta or {}).get("has_audio")),
        "audio_transcript": transcript_preview,
        "audio_tags": (v_meta or {}).get("audio_tags") or [],
        "asr_engine": (v_meta or {}).get("asr_engine") or "",
        "compressed": bool((v_meta or {}).get("compressed")),
    }


@router.get("/api/gallery/image/{img_id}")
def get_gallery_image(img_id: str, username: str = Depends(get_current_user)):
    safe_id = sanitize_id(img_id)
    p = get_user_gallery_dir(username) / f"{safe_id}.jpg"
    if not p.is_file():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(p, media_type="image/jpeg")


@router.get("/api/gallery/video/{vid_id}")
def get_gallery_video(vid_id: str, username: str = Depends(get_current_user)):
    safe_id = sanitize_id(vid_id)
    found = _find_video_file(get_user_gallery_dir(username), safe_id)
    if not found:
        raise HTTPException(status_code=404, detail="视频不存在")
    path, mime = found
    return FileResponse(path, media_type=mime)


@router.get("/api/gallery/audio/{vid_id}")
def get_gallery_audio(vid_id: str, username: str = Depends(get_current_user)):
    safe_id = sanitize_id(vid_id)
    p = get_user_gallery_dir(username) / "video_audio" / f"{safe_id}.mp3"
    if not p.is_file():
        raise HTTPException(status_code=404, detail="视频音轨不存在")
    return FileResponse(p, media_type="audio/mpeg")


@router.get("/api/gallery/thumb/{img_id}")
def get_gallery_thumb(img_id: str, username: str = Depends(get_current_user)):
    safe_id = sanitize_id(img_id)
    gdir = get_user_gallery_dir(username)
    p = gdir / "thumbs" / f"{safe_id}.jpg"
    if not p.is_file():
        p = gdir / f"{safe_id}.jpg"
    if not p.is_file():
        raise HTTPException(status_code=404, detail="缩略图不存在")
    return FileResponse(p, media_type="image/jpeg")


@router.get("/api/gallery/data_url/{img_id}")
def get_gallery_data_url(img_id: str, username: str = Depends(get_current_user)):
    safe_id = sanitize_id(img_id)
    p = get_user_gallery_dir(username) / f"{safe_id}.jpg"
    if not p.is_file():
        raise HTTPException(status_code=404, detail="图片不存在")
    b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
    return {"id": safe_id, "data_url": f"data:image/jpeg;base64,{b64}"}


@router.delete("/api/gallery/{img_id}")
def delete_gallery_item(img_id: str, username: str = Depends(get_current_user)):
    safe_id = sanitize_id(img_id)
    db = get_user_db(username)
    gdir = get_user_gallery_dir(username)
    db.delete_gallery_asset(safe_id)
    for fp in (
        gdir / f"{safe_id}.jpg",
        gdir / "thumbs" / f"{safe_id}.jpg",
        gdir / "video_audio" / f"{safe_id}.mp3",
        gdir / "video_meta" / f"{safe_id}.json",
    ):
        if fp.is_file():
            fp.unlink(missing_ok=True)
    shutil.rmtree(gdir / "video_frames" / safe_id, ignore_errors=True)
    for ext in VIDEO_MIME_BY_EXT:
        vfp = gdir / "videos" / f"{safe_id}{ext}"
        if vfp.is_file():
            vfp.unlink(missing_ok=True)
    return {"status": "ok"}


@router.post("/api/gallery/deduplicate")
def deduplicate_gallery_endpoint(username: str = Depends(get_current_user)):
    return {"status": "ok", **deduplicate_user_gallery(username)}


@router.get("/api/gallery/folders")
def list_gallery_folders(username: str = Depends(get_current_user)):
    return {"status": "ok", "folders": get_user_db(username).list_gallery_folders()}


@router.post("/api/gallery/folders")
def save_gallery_folders(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    folders = payload.get("folders") or []
    return {"status": "ok", "folders": get_user_db(username).save_gallery_folders([str(f) for f in folders])}


@router.post("/api/gallery/move")
def move_gallery_items(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    ids = [sanitize_id(x) for x in (payload.get("ids") or [])]
    folder = str(payload.get("folder") or "默认图库").strip() or "默认图库"
    moved = get_user_db(username).move_gallery_assets(ids, folder)
    return {"status": "ok", "moved": moved}
