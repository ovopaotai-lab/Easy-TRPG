# -*- coding: utf-8 -*-
"""Video transcoding, adaptive duration-scaled keyframe extraction, MP3 compression, and offline CPU ASR."""
from __future__ import annotations

import asyncio
import base64
import glob
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from backend.config import BASE_DIR
from backend.core.security import get_user_gallery_dir, sanitize_id

logger = logging.getLogger("easy_trpg.video")

VIDEO_META_SCHEMA_VERSION = 2
_FFMPEG_CACHE: Optional[str] = None
_FFMPEG_CHECKED = False
_ASR_ENV_CACHE: Optional[Dict[str, str]] = None
_ASR_ENV_CHECKED = False
_VIDEO_PROCESS_LOCKS: Dict[str, asyncio.Lock] = {}

_EVENT_TAG_LABELS: Dict[str, str] = {
    "HAPPY": "开心",
    "SAD": "悲伤",
    "ANGRY": "愤怒",
    "FEARFUL": "恐惧",
    "DISGUSTED": "厌恶",
    "SURPRISED": "惊讶",
    "Laughter": "笑声",
    "BGM": "背景音乐",
    "Applause": "掌声",
    "Crying": "哭泣",
    "Cough": "咳嗽",
    "Sneeze": "喷嚏",
    "Sing": "歌声",
    "Speech": "人声",
}

_LANG_TAG_LABELS: Dict[str, str] = {
    "zh": "中文",
    "en": "英文",
    "ja": "日语",
    "ko": "韩语",
    "yue": "粤语",
}


def _hidden_subprocess_kw() -> Dict[str, Any]:
    if os.name != "nt":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
    si.wShowWindow = 0
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        "startupinfo": si,
    }


def find_ffmpeg_exe() -> Optional[str]:
    """Locate an already-installed local ffmpeg binary without downloading anything."""
    global _FFMPEG_CACHE, _FFMPEG_CHECKED
    if _FFMPEG_CHECKED:
        return _FFMPEG_CACHE
    _FFMPEG_CHECKED = True

    candidates: List[str] = []
    for env_key in ("FFMPEG_PATH", "IMAGEIO_FFMPEG_EXE"):
        val = (os.environ.get(env_key) or "").strip()
        if val:
            candidates.append(val)

    exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    candidates.append(str(BASE_DIR / "runtime" / "ffmpeg" / exe_name))

    which_ff = shutil.which("ffmpeg")
    if which_ff:
        candidates.append(which_ff)

    try:
        import imageio_ffmpeg  # type: ignore

        eff = imageio_ffmpeg.get_ffmpeg_exe()
        if eff:
            candidates.append(eff)
    except Exception:
        pass

    if os.name == "nt":
        candidates.extend(
            [
                r"C:\ffmpeg\bin\ffmpeg.exe",
                r"D:\ffmpeg\bin\ffmpeg.exe",
            ]
        )
        patterns = [
            str(Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Python*" / "Lib" / "site-packages" / "imageio_ffmpeg" / "binaries" / "ffmpeg*.exe"),
            str(Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"),
        ]
        for pat in patterns:
            candidates.extend(sorted(glob.glob(pat, recursive=True)))

    for cand in candidates:
        try:
            p = Path(cand)
            if p.is_file():
                _FFMPEG_CACHE = str(p)
                return _FFMPEG_CACHE
        except OSError:
            continue
    return None


def find_local_asr_env() -> Optional[Dict[str, str]]:
    """Locate locally cached SenseVoiceSmall + FunASR Python environment (strictly offline)."""
    global _ASR_ENV_CACHE, _ASR_ENV_CHECKED
    if _ASR_ENV_CHECKED:
        return dict(_ASR_ENV_CACHE) if _ASR_ENV_CACHE else None
    _ASR_ENV_CHECKED = True

    home = Path.home()
    ms_root = home / ".cache" / "modelscope" / "models"
    sv_candidates = [
        ms_root / "iic--SenseVoiceSmall" / "snapshots" / "master",
        ms_root / "iic" / "SenseVoiceSmall",
    ]
    sv_dir = next((p for p in sv_candidates if (p / "model.pt").is_file()), None)
    if not sv_dir:
        return None

    vad_candidates = [
        ms_root / "iic--speech_fsmn_vad_zh-cn-16k-common-pytorch" / "snapshots" / "master",
        ms_root / "iic" / "speech_fsmn_vad_zh-cn-16k-common-pytorch",
    ]
    vad_dir = next((p for p in vad_candidates if (p / "model.pt").is_file()), None)

    import sys

    py_cands: List[str] = [sys.executable]
    if os.name == "nt":
        py_cands.extend(sorted(glob.glob(str(home / "AppData" / "Local" / "Programs" / "Python" / "Python*" / "python.exe"))))
    w_py = shutil.which("python") or shutil.which("python3")
    if w_py:
        py_cands.append(w_py)

    seen_py: set[str] = set()
    chosen_py = ""
    for pc in py_cands:
        try:
            rp = str(Path(pc).resolve())
        except OSError:
            continue
        if rp in seen_py or not Path(rp).is_file():
            continue
        seen_py.add(rp)
        # Fast directory check first to avoid importing torch in unrelated pythons
        py_root = Path(rp).parent
        if (py_root / "Lib" / "site-packages" / "funasr").is_dir() or (py_root.parent / "lib" / "python3.10" / "site-packages" / "funasr").is_dir():
            chosen_py = rp
            break
        try:
            r = subprocess.run(
                [rp, "-c", "import funasr"],
                capture_output=True,
                timeout=6.0,
                **_hidden_subprocess_kw(),
            )
            if r.returncode == 0:
                chosen_py = rp
                break
        except Exception:
            continue

    if not chosen_py:
        return None

    _ASR_ENV_CACHE = {
        "python": chosen_py,
        "sensevoice_dir": str(sv_dir),
        "vad_dir": str(vad_dir) if vad_dir else "",
    }
    return dict(_ASR_ENV_CACHE)


def compute_target_frame_count(duration_sec: float) -> int:
    """Choose adaptive keyframe count (4..36) scaled smoothly by video duration."""
    d = float(duration_sec or 0.0)
    if d <= 0.0:
        return 6
    if d <= 4.0:
        return max(4, min(6, round(d * 1.5)))
    if d <= 12.0:
        return max(6, min(11, round(d * 0.9)))
    if d <= 30.0:
        return max(11, min(18, round(10 + (d - 12.0) * 0.45)))
    if d <= 60.0:
        return max(18, min(26, round(18 + (d - 30.0) * 0.25)))
    if d <= 180.0:
        return max(26, min(36, round(26 + (d - 60.0) * 0.08)))
    return 36


def choose_frame_encoding_profile(frame_count: int) -> Tuple[int, int]:
    """Return (max_dim_px, jpeg_qscale) balancing visual clarity vs context/token budget."""
    if frame_count <= 12:
        return 640, 4
    if frame_count <= 24:
        return 512, 5
    return 448, 5


def format_timestamp_mmss(sec: float) -> str:
    s = max(0, int(round(sec)))
    return f"{s // 60:02d}:{s % 60:02d}"


def probe_video_sync(ffmpeg_exe: str, video_path: Path) -> Dict[str, Any]:
    """Parse duration, resolution, video codec/pix_fmt, and audio presence via ffmpeg -i."""
    res: Dict[str, Any] = {
        "duration_sec": 0.0,
        "width": 0,
        "height": 0,
        "video_codec": "",
        "pix_fmt": "",
        "has_audio": False,
        "audio_codec": "",
    }
    try:
        proc = subprocess.run(
            [ffmpeg_exe, "-hide_banner", "-i", str(video_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=15.0,
            **_hidden_subprocess_kw(),
        )
        txt = (proc.stderr or "") + "\n" + (proc.stdout or "")
    except Exception as exc:
        logger.warning("ffmpeg probe failed for %s: %s", video_path.name, exc)
        return res

    m_dur = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", txt)
    if m_dur:
        res["duration_sec"] = round(
            int(m_dur.group(1)) * 3600 + int(m_dur.group(2)) * 60 + float(m_dur.group(3)),
            2,
        )

    m_v = re.search(r"Stream\s+#\d+:\d+[^\n]*?Video:\s*([^,\s]+)(?:[^\n]*?,\s*(yuv[a-z0-9_]+|rgb[a-z0-9_]+|gbrp[a-z0-9_]*))?[^\n]*?,\s*(\d{2,5})x(\d{2,5})", txt)
    if m_v:
        res["video_codec"] = (m_v.group(1) or "").lower()
        res["pix_fmt"] = (m_v.group(2) or "").lower()
        res["width"] = int(m_v.group(3))
        res["height"] = int(m_v.group(4))
    else:
        m_wh = re.search(r"Video:[^\n]*?,\s*(\d{2,5})x(\d{2,5})", txt)
        if m_wh:
            res["width"] = int(m_wh.group(1))
            res["height"] = int(m_wh.group(2))
        m_vc = re.search(r"Video:\s*([a-zA-Z0-9_.-]+)", txt)
        if m_vc:
            res["video_codec"] = m_vc.group(1).lower()

    m_a = re.search(r"Stream\s+#\d+:\d+[^\n]*?Audio:\s*([^,\s(]+)", txt)
    if m_a and m_a.group(1).lower() != "none":
        res["has_audio"] = True
        res["audio_codec"] = m_a.group(1).lower()
    elif re.search(r"Stream\s+#\d+:\d+[^\n]*?Audio:\s*(?:aac|mp3|opus|vorbis|flac|pcm_)", txt, re.I):
        res["has_audio"] = True

    return res


def ensure_web_compatible_mp4_sync(ffmpeg_exe: str, video_path: Path, probe: Dict[str, Any]) -> Tuple[Path, bool]:
    """Transcode MOV/10-bit/HEVC/high-res/oversized videos into compact faststart H.264/AAC MP4."""
    vcodec = str(probe.get("video_codec") or "").lower()
    pix_fmt = str(probe.get("pix_fmt") or "").lower()
    max_wh = max(int(probe.get("width") or 0), int(probe.get("height") or 0))
    size_bytes = video_path.stat().st_size if video_path.is_file() else 0

    needs_transcode = (
        video_path.suffix.lower() != ".mp4"
        or (vcodec and vcodec != "h264")
        or ("10le" in pix_fmt or "10be" in pix_fmt or "12le" in pix_fmt)
        or max_wh > 1280
        or size_bytes > 15 * 1024 * 1024
    )
    if not needs_transcode:
        return video_path, False

    target_mp4 = video_path.with_suffix(".mp4")
    tmp_mp4 = video_path.parent / f".{video_path.stem}_{uuid.uuid4().hex[:6]}.tmp.mp4"
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", str(video_path),
        "-map", "0:v:0",
        "-map", "0:a:0?",
        "-vf", "scale='min(1280,iw)':'min(1280,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,format=yuv420p",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "26",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "96k",
        "-ac", "2",
        "-ar", "44100",
        "-movflags", "+faststart",
        str(tmp_mp4),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=180.0,
            **_hidden_subprocess_kw(),
        )
        if proc.returncode == 0 and tmp_mp4.is_file() and tmp_mp4.stat().st_size > 1024:
            old_path = video_path
            os.replace(tmp_mp4, target_mp4)
            if old_path != target_mp4 and old_path.is_file():
                old_path.unlink(missing_ok=True)
            return target_mp4, True
        logger.warning("ffmpeg transcode returned %s: %s", proc.returncode, (proc.stderr or "")[-400:])
    except Exception as exc:
        logger.warning("ffmpeg transcode failed for %s: %s", video_path.name, exc)
    finally:
        if tmp_mp4.is_file():
            tmp_mp4.unlink(missing_ok=True)
    return video_path, False


def extract_video_frames_sync(
    ffmpeg_exe: str,
    video_path: Path,
    frames_dir: Path,
    thumb_path: Path,
    duration_sec: float,
) -> Tuple[List[Path], List[float]]:
    """Extract duration-scaled timestamped JPEG keyframes plus gallery poster thumbnail."""
    if frames_dir.exists():
        shutil.rmtree(frames_dir, ignore_errors=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    target_n = compute_target_frame_count(duration_sec)
    max_dim, qscale = choose_frame_encoding_profile(target_n)
    scale_vf = f"scale='min({max_dim},iw)':'min({max_dim},ih)':force_original_aspect_ratio=decrease"

    if duration_sec <= 0.35:
        cmd = [
            ffmpeg_exe, "-y", "-i", str(video_path),
            "-vf", scale_vf,
            "-frames:v", "1", "-q:v", str(qscale),
            str(frames_dir / "frame_%03d.jpg"),
        ]
        subprocess.run(cmd, capture_output=True, timeout=30.0, **_hidden_subprocess_kw())
    elif duration_sec <= 90.0:
        fps_val = max(0.05, target_n / max(0.5, duration_sec))
        cmd = [
            ffmpeg_exe, "-y", "-i", str(video_path),
            "-vf", f"fps={fps_val:.4f},{scale_vf}",
            "-frames:v", str(target_n),
            "-q:v", str(qscale),
            str(frames_dir / "frame_%03d.jpg"),
        ]
        subprocess.run(cmd, capture_output=True, timeout=90.0, **_hidden_subprocess_kw())
    else:
        for idx in range(target_n):
            frac = (idx + 0.5) / target_n
            ts = min(max(0.1, duration_sec * frac), max(0.1, duration_sec - 0.1))
            out_f = frames_dir / f"frame_{idx + 1:03d}.jpg"
            cmd = [
                ffmpeg_exe, "-y",
                "-ss", f"{ts:.2f}",
                "-i", str(video_path),
                "-frames:v", "1",
                "-vf", scale_vf,
                "-q:v", str(qscale),
                str(out_f),
            ]
            subprocess.run(cmd, capture_output=True, timeout=20.0, **_hidden_subprocess_kw())

    frame_files = sorted(frames_dir.glob("frame_*.jpg"))
    # Fallback single-frame grab if fps filter yielded 0 frames on unusual VFR files
    if not frame_files:
        cmd = [
            ffmpeg_exe, "-y", "-i", str(video_path),
            "-vf", scale_vf,
            "-frames:v", "1", "-q:v", str(qscale),
            str(frames_dir / "frame_001.jpg"),
        ]
        subprocess.run(cmd, capture_output=True, timeout=30.0, **_hidden_subprocess_kw())
        frame_files = sorted(frames_dir.glob("frame_*.jpg"))

    if frame_files:
        try:
            thumb_path.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(frame_files[0]) as im_raw:
                thumb = im_raw.convert("RGB")
                thumb.thumbnail((320, 320))
                thumb.save(thumb_path, format="JPEG", quality=82, optimize=True)
        except Exception:
            pass

    n = len(frame_files)
    if n <= 0:
        return [], []
    if duration_sec > 0.35:
        timestamps = [
            round(min(max(0.0, duration_sec * ((i + 0.5) / n)), duration_sec), 1)
            for i in range(n)
        ]
    else:
        timestamps = [0.0 for _ in range(n)]
    return frame_files, timestamps


def _parse_sensevoice_output(raw_text: str) -> Tuple[str, List[str]]:
    """Convert raw SenseVoice special tags into readable tags + clean transcript text."""
    raw = str(raw_text or "").strip()
    tags: List[str] = []
    for tok in re.findall(r"<\|([^|>]+)\|>", raw):
        if tok in _EVENT_TAG_LABELS:
            lbl = _EVENT_TAG_LABELS[tok]
            if lbl not in tags:
                tags.append(lbl)
        elif tok in _LANG_TAG_LABELS:
            lbl = f"语种:{_LANG_TAG_LABELS[tok]}"
            if lbl not in tags:
                tags.append(lbl)
    clean = re.sub(r"<\|[^|>]*\|>", "", raw).strip()
    return clean, tags


def extract_audio_and_transcribe_sync(
    ffmpeg_exe: str,
    video_path: Path,
    audio_mp3_path: Path,
    duration_sec: float,
) -> Dict[str, Any]:
    """Extract compressed mono MP3 audio and run offline CPU SenseVoice transcription when available."""
    out: Dict[str, Any] = {
        "has_audio": False,
        "audio_path": "",
        "audio_size_bytes": 0,
        "transcript": "",
        "audio_tags": [],
        "asr_engine": "",
    }
    audio_mp3_path.parent.mkdir(parents=True, exist_ok=True)
    bitrate = "48k" if duration_sec <= 600 else "32k"
    tmp_mp3 = audio_mp3_path.parent / f".{audio_mp3_path.stem}_{uuid.uuid4().hex[:6]}.mp3"
    cmd_mp3 = [
        ffmpeg_exe, "-y", "-i", str(video_path),
        "-vn", "-map", "0:a:0",
        "-ac", "1", "-ar", "24000",
        "-c:a", "libmp3lame", "-b:a", bitrate,
        str(tmp_mp3),
    ]
    try:
        r_mp3 = subprocess.run(cmd_mp3, capture_output=True, timeout=90.0, **_hidden_subprocess_kw())
        if r_mp3.returncode != 0 or not tmp_mp3.is_file() or tmp_mp3.stat().st_size <= 256:
            tmp_mp3.unlink(missing_ok=True)
            return out
        os.replace(tmp_mp3, audio_mp3_path)
        out["has_audio"] = True
        out["audio_path"] = str(audio_mp3_path)
        out["audio_size_bytes"] = int(audio_mp3_path.stat().st_size)
    except Exception as exc:
        tmp_mp3.unlink(missing_ok=True)
        logger.warning("Audio extraction failed for %s: %s", video_path.name, exc)
        return out

    asr_env = find_local_asr_env()
    if not asr_env:
        return out

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        wav_path = Path(tf.name)
    try:
        cmd_wav = [
            ffmpeg_exe, "-y", "-i", str(audio_mp3_path),
            "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
            str(wav_path),
        ]
        r_wav = subprocess.run(cmd_wav, capture_output=True, timeout=45.0, **_hidden_subprocess_kw())
        if r_wav.returncode != 0 or not wav_path.is_file() or wav_path.stat().st_size <= 1024:
            return out

        asr_script = (
            "import json, sys\n"
            "from funasr import AutoModel\n"
            "from funasr.utils.postprocess_utils import rich_transcription_postprocess\n"
            "sv_dir, vad_dir, wav = sys.argv[1], sys.argv[2], sys.argv[3]\n"
            "kw = dict(model=sv_dir, device='cpu', disable_update=True, disable_pbar=True)\n"
            "if vad_dir:\n"
            "    kw['vad_model'] = vad_dir\n"
            "    kw['vad_kwargs'] = {'max_single_segment_time': 30000}\n"
            "m = AutoModel(**kw)\n"
            "res = m.generate(input=wav, cache={}, language='auto', use_itn=True, batch_size_s=60, merge_vad=True, merge_length_s=15)\n"
            "raw = res[0].get('text', '') if res and isinstance(res[0], dict) else ''\n"
            "clean = rich_transcription_postprocess(raw) if raw else ''\n"
            "print('__ASR_JSON__' + json.dumps({'raw': raw, 'clean': clean}, ensure_ascii=False))\n"
        )
        env = os.environ.copy()
        env["HF_HUB_OFFLINE"] = "1"
        env["MODELSCOPE_OFFLINE"] = "1"
        env["TQDM_DISABLE"] = "1"
        ff_dir = str(Path(ffmpeg_exe).parent)
        env["PATH"] = f"{ff_dir}{os.pathsep}{env.get('PATH', '')}"

        r_asr = subprocess.run(
            [asr_env["python"], "-c", asr_script, asr_env["sensevoice_dir"], asr_env.get("vad_dir") or "", str(wav_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            env=env,
            timeout=120.0,
            **_hidden_subprocess_kw(),
        )
        for ln in (r_asr.stdout or "").splitlines():
            if ln.startswith("__ASR_JSON__"):
                obj = json.loads(ln[len("__ASR_JSON__"):])
                raw = str(obj.get("raw") or "")
                clean = str(obj.get("clean") or "").strip()
                parsed_clean, tags = _parse_sensevoice_output(raw)
                out["transcript"] = clean or parsed_clean
                out["audio_tags"] = tags
                out["asr_engine"] = "sensevoice"
                break
    except Exception as exc:
        logger.warning("Offline SenseVoice ASR skipped for %s: %s", video_path.name, exc)
    finally:
        wav_path.unlink(missing_ok=True)
    return out


def process_video_asset_sync(
    gdir: Path,
    vid_id: str,
    video_path: Path,
    orig_filename: str = "",
) -> Dict[str, Any]:
    """Run transcode + adaptive keyframes + compressed MP3 + offline ASR and persist v2 metadata."""
    meta_dir = gdir / "video_meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    meta_file = meta_dir / f"{vid_id}.json"

    ffmpeg_exe = find_ffmpeg_exe()
    if not ffmpeg_exe or not video_path.is_file():
        meta: Dict[str, Any] = {
            "schema_version": VIDEO_META_SCHEMA_VERSION,
            "id": vid_id,
            "orig_filename": orig_filename or video_path.name,
            "stored_relpath": video_path.name,
            "duration_sec": 0.0,
            "width": 0,
            "height": 0,
            "size_bytes": video_path.stat().st_size if video_path.is_file() else 0,
            "compressed": False,
            "frame_count": 0,
            "frame_timestamps": [],
            "has_audio": False,
            "audio_size_bytes": 0,
            "transcript": "",
            "audio_tags": [],
            "asr_engine": "",
            "ffmpeg_available": bool(ffmpeg_exe),
        }
        meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return meta

    probe1 = probe_video_sync(ffmpeg_exe, video_path)
    final_path, transcoded = ensure_web_compatible_mp4_sync(ffmpeg_exe, video_path, probe1)
    probe2 = probe_video_sync(ffmpeg_exe, final_path) if transcoded else probe1
    dur = float(probe2.get("duration_sec") or probe1.get("duration_sec") or 0.0)

    frames_dir = gdir / "video_frames" / vid_id
    thumb_path = gdir / "thumbs" / f"{vid_id}.jpg"
    frame_files, timestamps = extract_video_frames_sync(ffmpeg_exe, final_path, frames_dir, thumb_path, dur)

    audio_info: Dict[str, Any] = {
        "has_audio": False,
        "audio_path": "",
        "audio_size_bytes": 0,
        "transcript": "",
        "audio_tags": [],
        "asr_engine": "",
    }
    if probe2.get("has_audio") or probe1.get("has_audio"):
        audio_mp3_path = gdir / "video_audio" / f"{vid_id}.mp3"
        audio_info = extract_audio_and_transcribe_sync(ffmpeg_exe, final_path, audio_mp3_path, dur)

    meta = {
        "schema_version": VIDEO_META_SCHEMA_VERSION,
        "id": vid_id,
        "orig_filename": orig_filename or video_path.name,
        "stored_relpath": final_path.name,
        "duration_sec": round(dur, 2),
        "width": int(probe2.get("width") or probe1.get("width") or 0),
        "height": int(probe2.get("height") or probe1.get("height") or 0),
        "size_bytes": int(final_path.stat().st_size) if final_path.is_file() else 0,
        "compressed": bool(transcoded),
        "frame_count": len(frame_files),
        "frame_timestamps": timestamps,
        "has_audio": bool(audio_info.get("has_audio")),
        "audio_size_bytes": int(audio_info.get("audio_size_bytes") or 0),
        "transcript": str(audio_info.get("transcript") or ""),
        "audio_tags": list(audio_info.get("audio_tags") or []),
        "asr_engine": str(audio_info.get("asr_engine") or ""),
        "ffmpeg_available": True,
    }
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def _find_video_asset_file(gdir: Path, safe_id: str) -> Optional[Path]:
    vdir = gdir / "videos"
    if not vdir.is_dir():
        return None
    for ext in (".mp4", ".mov", ".webm", ".m4v", ".ogg"):
        cand = vdir / f"{safe_id}{ext}"
        if cand.is_file():
            return cand
    for cand in sorted(vdir.glob(f"{safe_id}.*")):
        if cand.is_file() and not cand.name.startswith("."):
            return cand
    return None


async def ensure_video_processed_async(
    username: str,
    vid_id: str,
    orig_filename: str = "",
    force: bool = False,
) -> Optional[Dict[str, Any]]:
    """Ensure uploaded video has v2 keyframes, compatible MP4, MP3 audio, and offline transcript cached."""
    safe_id = sanitize_id(vid_id)
    if not safe_id:
        return None
    lock = _VIDEO_PROCESS_LOCKS.setdefault(f"{username}:{safe_id}", asyncio.Lock())
    async with lock:
        gdir = get_user_gallery_dir(username)
        meta_file = gdir / "video_meta" / f"{safe_id}.json"
        frames_dir = gdir / "video_frames" / safe_id
        if not force and meta_file.is_file():
            try:
                cached = json.loads(meta_file.read_text(encoding="utf-8"))
                if (
                    int(cached.get("schema_version") or 0) >= VIDEO_META_SCHEMA_VERSION
                    and int(cached.get("frame_count") or 0) > 0
                    and frames_dir.is_dir()
                    and len(list(frames_dir.glob("frame_*.jpg"))) > 0
                ):
                    return cached
            except Exception:
                pass

        vpath = _find_video_asset_file(gdir, safe_id)
        if not vpath:
            return None
        return await asyncio.to_thread(process_video_asset_sync, gdir, safe_id, vpath, orig_filename)


def load_video_prompt_bundle(
    username: str,
    vid_id: str,
    max_audio_bytes: int = 6 * 1024 * 1024,
) -> Optional[Dict[str, Any]]:
    """Load extracted JPEG keyframes with timestamps, compressed MP3 base64, and ASR transcript for LLM prompts."""
    safe_id = sanitize_id(vid_id)
    if not safe_id:
        return None
    gdir = get_user_gallery_dir(username)
    meta_file = gdir / "video_meta" / f"{safe_id}.json"
    meta: Dict[str, Any] = {}
    if meta_file.is_file():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            meta = {}

    frames_dir = gdir / "video_frames" / safe_id
    frame_files = sorted(frames_dir.glob("frame_*.jpg")) if frames_dir.is_dir() else []
    timestamps = list(meta.get("frame_timestamps") or [])
    dur = float(meta.get("duration_sec") or 0.0)

    frames_payload: List[Dict[str, Any]] = []
    n = len(frame_files)
    for idx, fp in enumerate(frame_files):
        try:
            b64 = base64.b64encode(fp.read_bytes()).decode("utf-8")
            ts_sec = float(timestamps[idx]) if idx < len(timestamps) else (dur * ((idx + 0.5) / max(1, n)) if dur > 0 else 0.0)
            frames_payload.append(
                {
                    "index": idx + 1,
                    "timestamp_sec": round(ts_sec, 1),
                    "timestamp_label": format_timestamp_mmss(ts_sec),
                    "data_url": f"data:image/jpeg;base64,{b64}",
                }
            )
        except OSError:
            continue

    audio_b64 = ""
    audio_file = gdir / "video_audio" / f"{safe_id}.mp3"
    if audio_file.is_file():
        try:
            raw_audio = audio_file.read_bytes()
            if 0 < len(raw_audio) <= max_audio_bytes:
                audio_b64 = base64.b64encode(raw_audio).decode("utf-8")
        except OSError:
            pass

    if not frames_payload and not audio_b64 and not meta.get("transcript"):
        return None

    return {
        "id": safe_id,
        "filename": str(meta.get("orig_filename") or f"{safe_id}.mp4"),
        "duration_sec": dur,
        "duration_label": format_timestamp_mmss(dur) if dur > 0 else "未知时长",
        "frame_count": len(frames_payload),
        "frames": frames_payload,
        "has_audio": bool(meta.get("has_audio") or audio_b64),
        "audio_base64": audio_b64,
        "audio_format": "mp3",
        "transcript": str(meta.get("transcript") or "").strip(),
        "audio_tags": list(meta.get("audio_tags") or []),
        "asr_engine": str(meta.get("asr_engine") or ""),
    }


def format_video_text_summary(bundle: Dict[str, Any]) -> str:
    """Format concise structured video+audio context block injected alongside visual frames."""
    fname = str(bundle.get("filename") or bundle.get("id") or "视频")
    dur = float(bundle.get("duration_sec") or 0.0)
    dur_str = f"{round(dur)}秒 ({bundle.get('duration_label') or ''})" if dur > 0 else "时长未知"
    fc = int(bundle.get("frame_count") or len(bundle.get("frames") or []))
    lines = [f"【视频素材：{fname} | 时长 {dur_str} | 按时间顺序抽取 {fc} 张关键画面】"]

    transcript = str(bundle.get("transcript") or "").strip()
    tags = [str(t) for t in (bundle.get("audio_tags") or []) if str(t).strip()]
    if bundle.get("has_audio"):
        tag_str = f"（音频特征: {'、'.join(tags)}）" if tags else ""
        if transcript:
            lines.append(f"【视频音频识别{tag_str}】：{transcript}")
        elif tags:
            lines.append(f"【视频音频特征】：{'、'.join(tags)}（未检测到清晰语音对白）")
        else:
            lines.append("【视频音轨】：含音轨但无明显对白或暂未识别出人声")
    else:
        lines.append("【视频音轨】：该视频无音轨")
    return "\n".join(lines)
