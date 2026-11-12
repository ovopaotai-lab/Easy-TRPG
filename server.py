import os
import sys
import copy
import json
import uuid
import time
import io
import re
import socket
import asyncio
import threading
import subprocess
import secrets
import hashlib
import shutil
import base64
from contextlib import asynccontextmanager
from urllib.parse import urlparse
import httpx
import uvicorn
import webbrowser
from PIL import Image
from pathlib import Path
from typing import List, Optional, Dict, Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, HTTPException, Request, Response, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from enterprise_engine import (
    EXPLORE_PRESET_APPS,
    WORLDBOOK_TEMPLATE_JSON,
    LOCAL_MODELS_CATALOG,
    DEFAULT_UI_MODULES,
    DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT,
    upgrade_legacy_global_protocol_prompt,
    normalize_ui_modules,
    build_ui_modules_spec_block,
    build_content_scale_prompt_block,
    build_status_module_prompt,
    is_free_chat_project,
    discover_local_models,
    get_installed_local_model_ids,
    normalize_api_endpoint_and_protocol,
    resolve_model_endpoint,
    ensure_local_engine_ready,
    sanitize_messages_for_model,
    normalize_project_schema,
    interpolate_variables,
    apply_regex_scripts,
    strip_thinking_blocks,
    _has_narrative_outside_status,
    STATUS_SUBMODULE_TYPES,
    evaluate_world_book,
    evaluate_cg_book,
    create_enterprise_router,
    atomic_write_json,
    safe_int,
    safe_float,
    open_directory_safely,
    get_optimal_ollama_num_ctx,
    shutdown_local_engines,
    get_default_completion_params,
    require_loopback,
    _get_process_image_name,
    _NATIVE_PICKER_LOCK,
    _native_pick_path_powershell,
    detect_gpu_vram_mib,
)

# 跟踪后台正在生成的对话任务与实时增量文本，防止手机刷新或网络抖动中断生成
ACTIVE_BG_TASKS: Dict[str, asyncio.Task] = {}
ACTIVE_PARTIAL_TEXT: Dict[str, str] = {}

# 文件与状态并发读写互斥锁
_USER_SETTINGS_LOCK = threading.RLock()
_GALLERY_LOCK = threading.RLock()
_CHAR_CARDS_LOCK = threading.RLock()
_USERS_AUTH_LOCK = threading.RLock()
_CHAT_LOCKS_GUARD = threading.Lock()
_CHAT_LOCKS: Dict[str, asyncio.Lock] = {}


def _get_chat_lock(chat_id: str) -> asyncio.Lock:
    with _CHAT_LOCKS_GUARD:
        lk = _CHAT_LOCKS.get(chat_id)
        if lk is None:
            lk = asyncio.Lock()
            _CHAT_LOCKS[chat_id] = lk
        return lk

def strip_legacy_start_game_hint(text: str) -> str:
    """剥离旧版『开始游戏』后面误拼接到玩家可见气泡里的系统提示词尾巴"""
    if not text:
        return ""
    cleaned = re.sub(
        r"\s*[（(]请根据当前剧本世界观与角色设定，直接以第二人称代入感展开第一幕沉浸式场景描写[^）)]*[）)]\s*",
        "",
        str(text)
    ).strip()
    return cleaned or str(text).strip()

def optimize_image_base64(img_b64: str, max_dim: int = 1024, quality: int = 78, min_bytes: int = 110_000, max_target_bytes: int = 240_000) -> str:
    """自动将高分辨率或超大 base64 图片自适应多级压缩缩放（控制在 ~80KB-220KB 以内），彻底杜绝几十 MB 大图入库或导致超时"""
    try:
        if not img_b64 or not isinstance(img_b64, str) or not img_b64.startswith("data:image"):
            return img_b64
        if len(img_b64) < min_bytes and img_b64.startswith("data:image/jpeg;base64,"):
            return img_b64

        header, b64_str = img_b64.split(",", 1)
        raw_bytes = base64.b64decode(b64_str)
        im = Image.open(io.BytesIO(raw_bytes))

        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            rgba = im.convert("RGBA")
            bg.paste(rgba, mask=rgba.split()[3])
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")

        im.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        cur_im = im
        cur_q = quality
        new_bytes = b""
        for step in range(4):
            buf = io.BytesIO()
            cur_im.save(buf, format="JPEG", quality=cur_q, optimize=True)
            new_bytes = buf.getvalue()
            if len(new_bytes) <= max_target_bytes:
                break
            cur_q = max(55, cur_q - 10)
            if step >= 1 and max(cur_im.width, cur_im.height) > 768:
                next_dim = max(768, int(max(cur_im.width, cur_im.height) * 0.82))
                cur_im = cur_im.copy()
                cur_im.thumbnail((next_dim, next_dim), Image.Resampling.LANCZOS)

        return "data:image/jpeg;base64," + base64.b64encode(new_bytes).decode("utf-8")
    except Exception as e:
        print(f"优化图片尺寸异常: {e}")
        return img_b64

BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
MODEL_DIR = BASE_DIR / "model"
STATIC_DIR = BASE_DIR / "static"
USERS_DIR = DATA_DIR / "users"
USERS_FILE = DATA_DIR / "users.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)
USERS_DIR.mkdir(parents=True, exist_ok=True)

# 默认全局配置（含全局默认模型数值参数与 <status> 状态栏底层系统协议，新建/全局游戏自动继承）
DEFAULT_SETTINGS = {
    "api_protocol": "auto",
    "base_url": "",
    "api_key": "",
    "model": "",
    "custom_models": [],
    "custom_model_paths": [],
    "local_mode": "auto",
    "local_base_url": "",
    "local_model": "",
    "proxy": "",
    "use_proxy": False,
    "temperature": 0.68,
    "repetition_penalty": 1.05,
    "frequency_penalty": 0.05,
    "presence_penalty": 0.20,
    "top_p": 0.90,
    "top_k": 40,
    "min_p": 0.06,
    "max_tokens": 4096,
    "context_mode": "tokens",
    "context": 96,
    "max_context_turns": 96,
    "max_context_k": 96,
    "keep_recent_messages": 6,
    "worldbook_scan_depth": 5,
    "thinking_budget": 1024,
    "auto_summarize": True,
    "active_project_id": "proj_default",
    "erotic_level": 0,
    "violence_level": 0,
    "model_params": {},
    "global_system_protocol_prompt": DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT,
}

# 默认初始游戏 1：跑团
DEFAULT_PROJECT = {
    "id": "proj_default",
    "name": "跑团",
    "icon": "",
    "avatar": "",
    "category": "跑团",
    "description": "",
    "tags": [],
    "status_panel_enabled": True,
    "opening_greetings": [
        {
            "id": "og_trpg_fantasy",
            "title": "圣女与暗巷",
            "content": "我想玩《圣女与暗巷》：雨夜的蒸汽下城区，我是一名身怀旧伤的落魄骑士，在暗巷尽头的破败钟楼下，偶然撞见了一名浑身湿透、正被教会黑衣审判官追捕的银发见习圣女。请直接用电影级第二人称视角拉入危机开场。"
        },
        {
            "id": "og_trpg_mystery",
            "title": "雾港古宅",
            "content": "我想玩《雾港古宅》：1920年代被海雾笼罩的孤岛渔村，我作为受雇的私家侦探提着煤油灯推开钟表匠老宅生锈的铁门，壁炉里的余烬尚温，桌上的怀表却全部停在了午夜十二点零七分。请直接开启悬疑探索。"
        },
        {
            "id": "og_trpg_xianxia",
            "title": "仙门卧底",
            "content": "我想玩《仙门卧底》：我是魔教安插在正道第一剑宗「太虚剑阁」的亲传弟子，今夜奉命潜入禁地藏经阁盗取剑印，却在推开顶层木门的瞬间，迎面撞见了本该闭关百年的清冷师尊独自坐在月光下擦剑。请直接拉入高张力开场。"
        },
        {
            "id": "og_trpg_cyber",
            "title": "霓虹义体猎人",
            "content": "我想玩《霓虹义体猎人》：2089年的夜之城底层黑市，我是一名靠接高危暗网悬赏维生的边缘佣兵。今晚在酸雨笼罩的废弃义体诊所交接加密芯片时，雇主早已死在手术台上，而诊所外突然响起了荒坂重工浮空装甲车的警报声。请直接开启危机跑团。"
        },
        {
            "id": "og_trpg_sandbox",
            "title": "自由沙盒",
            "isSandbox": True,
            "content": "请开启《自由沙盒跑团》模式，根据我的设定或角色卡自动推演世界观，直接把我拉入充满张力的第一幕场景。"
        }
    ],
    "ui_modules": [dict(m) for m in DEFAULT_UI_MODULES],
    "system_prompt": (
        "你是一位兼具电影级镜头感与顶级游戏策划功底的【全题材自适应互动叙事主持（AI 导演 / DM）】。\n"
        "请根据玩家当前选用的【开场白】或挂载的【角色卡】自动适配世界观与文风（奇幻冒险/悬疑跑团/赛博修仙/日常情感张力），始终以极具画面感与感官细节（光影、声响、气味、微表情）的第二人称（「你」）叙事。NPC 拥有独立动机、秘密与性格底线，绝不无脑顺从玩家；严禁代替玩家做决定或抢说玩家台词。"
    ),
    "system_protocol_prompt": DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT,
    "prefix": "【玩家行动】",
    "suffix": (
        "【导演执行约束：保持第二人称电影感叙事；用户的回复和自定义剧情发展要合理地通过游戏世界逻辑与真实性进行推演，不要盲目听从用户的命令。每次回复必须严格按照当前已启用的模块顺序完整输出：先写沉浸式剧情正文，随后按系统协议同步已启用的 <status>...</status> 状态栏（每回合在上一轮状态栏基础上继承并更新，保留历史已结识角色关系、已有装备与未消耗物品，严禁因新对话开始或场景切换而删去历史状态栏信息），若启用了行动选项模块则仅在最底部输出唯一一次提问与编号选项（严禁提前或重复输出选项）。】"
    ),
    "max_context_turns": 64,
    "erotic_level": 0,
    "violence_level": 0,
    "auto_summarize": True,
    "created_at": time.time(),
    "updated_at": time.time()
}

# 默认初始游戏 2：聊天（100% 纯净网页版 AI，无任何功能栏、无任何提示词、无任何预设开场白）
DEFAULT_FREE_CHAT_UI_MODULES: List[Dict[str, Any]] = []

DEFAULT_FREE_CHAT_PROJECT = {
    "id": "proj_free_chat",
    "name": "聊天",
    "icon": "",
    "avatar": "",
    "category": "聊天",
    "description": "",
    "tags": [],
    "status_panel_enabled": True,
    "opening_greetings": [],
    "ui_modules": [],
    "system_prompt": "",
    "system_protocol_prompt": "",
    "prefix": "",
    "suffix": "",
    "max_context_turns": 64,
    "erotic_level": 0,
    "violence_level": 0,
    "auto_summarize": True,
    "created_at": time.time(),
    "updated_at": time.time()
}

# ==================== 用户密码与多租户目录工具 ====================
def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return pwd_hash, salt

def verify_password(password: str, pwd_hash: str, salt: str) -> bool:
    calc_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(calc_hash, pwd_hash)

def load_users() -> Dict[str, Any]:
    with _USERS_AUTH_LOCK:
        if not USERS_FILE.exists():
            return {}
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

def save_users(users: Dict[str, Any]):
    with _USERS_AUTH_LOCK:
        atomic_write_json(USERS_FILE, users, ensure_ascii=False, indent=2)

def load_sessions() -> Dict[str, Any]:
    with _USERS_AUTH_LOCK:
        if not SESSIONS_FILE.exists():
            return {}
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

def save_sessions():
    with _USERS_AUTH_LOCK:
        atomic_write_json(SESSIONS_FILE, SESSIONS, ensure_ascii=False, indent=2)

SESSIONS: Dict[str, Any] = load_sessions()

def sanitize_id(raw_id: str) -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9_\-]', '', str(raw_id or '').strip())
    if not cleaned:
        raise HTTPException(status_code=400, detail="非法 ID")
    return cleaned

def get_user_dir(username: str) -> Path:
    raw = str(username or "").strip()
    if not raw or raw == "player":
        safe_name = "player"
    else:
        cleaned = re.sub(r"[^\w\-]", "_", raw).strip("._ ")
        if not cleaned or cleaned in (".", ".."):
            cleaned = "user"
        if cleaned != raw or not cleaned.strip("_"):
            h8 = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
            safe_name = f"{cleaned[:32]}_{h8}"
        else:
            safe_name = cleaned[:48]
    users_root = USERS_DIR.resolve()
    udir = (USERS_DIR / safe_name).resolve()
    if udir == users_root or not udir.is_relative_to(users_root):
        raise HTTPException(status_code=400, detail="非法用户名")
    (udir / "chats").mkdir(parents=True, exist_ok=True)
    (udir / "projects").mkdir(parents=True, exist_ok=True)
    (udir / "presets").mkdir(parents=True, exist_ok=True)
    (udir / "gallery").mkdir(parents=True, exist_ok=True)
    (udir / "gallery" / "thumbs").mkdir(parents=True, exist_ok=True)
    return udir

def get_user_chats_dir(username: str) -> Path:
    return get_user_dir(username) / "chats"

def get_user_projects_dir(username: str) -> Path:
    return get_user_dir(username) / "projects"

def get_user_presets_dir(username: str) -> Path:
    return get_user_dir(username) / "presets"

def get_user_gallery_dir(username: str) -> Path:
    return get_user_dir(username) / "gallery"

def get_user_settings_file(username: str) -> Path:
    return get_user_dir(username) / "settings.json"

def load_user_settings(username: str) -> Dict[str, Any]:
    with _USER_SETTINGS_LOCK:
        sfile = get_user_settings_file(username)
        if sfile.exists():
            saved = None
            try:
                with open(sfile, "r", encoding="utf-8-sig") as f:
                    saved = json.load(f)
                if not isinstance(saved, dict):
                    raise ValueError("settings.json 顶层不是对象")
            except OSError as e:
                # 文件被短暂占用等 I/O 异常：本次返回默认值，但绝不覆盖原文件
                print(f"[Warn] 读取用户配置 settings.json 失败 ({e})，本次临时使用默认配置")
                return copy.deepcopy(DEFAULT_SETTINGS)
            except Exception as e:
                # 解析失败时绝不直接用默认值覆盖用户配置：先把损坏文件改名保留，便于人工恢复
                saved = None
                try:
                    corrupt_path = sfile.with_name(f"settings.json.corrupt-{time.strftime('%Y%m%d_%H%M%S')}")
                    os.replace(sfile, corrupt_path)
                    print(f"[Warn] 用户配置 settings.json 解析失败 ({e})，已备份为 {corrupt_path.name} 并重建默认配置")
                except Exception as mv_err:
                    print(f"[Warn] 用户配置 settings.json 解析失败 ({e})，且无法备份 ({mv_err})，本次使用默认配置但不覆盖原文件")
                    return copy.deepcopy(DEFAULT_SETTINGS)
            if isinstance(saved, dict):
                merged = {**copy.deepcopy(DEFAULT_SETTINGS), **copy.deepcopy(saved)}
                upgraded_proto = upgrade_legacy_global_protocol_prompt(merged.get("global_system_protocol_prompt"), allow_empty=True)
                if upgraded_proto != merged.get("global_system_protocol_prompt"):
                    merged["global_system_protocol_prompt"] = upgraded_proto
                    try:
                        save_user_settings(username, merged)
                    except Exception as e:
                        print(f"[Warn] 升级全局协议提示词后保存配置失败: {e}")
                return merged
        default_copy = copy.deepcopy(DEFAULT_SETTINGS)
        save_user_settings(username, default_copy)
        return copy.deepcopy(default_copy)

def save_user_settings(username: str, settings: Dict[str, Any]):
    with _USER_SETTINGS_LOCK:
        sfile = get_user_settings_file(username)
        atomic_write_json(sfile, settings, ensure_ascii=False, indent=2)

def compute_image_vhash(im: Image.Image) -> str:
    """计算图像的 64位 灰度感知差分哈希 (dHash)，防止因 Canvas/JPEG 重编码产生重复图库副本"""
    try:
        g = im.convert("L").resize((9, 8), Image.Resampling.BILINEAR)
        pixels = list(g.getdata())
        bits = []
        for row in range(8):
            offset = row * 9
            for col in range(8):
                bits.append("1" if pixels[offset + col] > pixels[offset + col + 1] else "0")
        return hex(int("".join(bits), 2))[2:].zfill(16)
    except Exception:
        return ""

def vhash_hamming(h1: str, h2: str) -> int:
    if not h1 or not h2 or len(h1) != 16 or len(h2) != 16:
        return 999
    try:
        return bin(int(h1, 16) ^ int(h2, 16)).count("1")
    except Exception:
        return 999

def auto_save_to_gallery(username: str, img_b64: str, filename: Optional[str] = None, folder: Optional[str] = None) -> Optional[str]:
    """将图片保存进用户素材图库并生成缩略图，返回图片ID（支持分类文件夹、MD5与感知哈希双重秒级去重）"""
    try:
        if not img_b64 or not isinstance(img_b64, str) or not img_b64.startswith("data:image"):
            return None
        with _GALLERY_LOCK:
            udir = get_user_dir(username)
            gallery_dir = get_user_gallery_dir(username)
            thumbs_dir = gallery_dir / "thumbs"

            header, b64_str = img_b64.split(",", 1)
            raw = base64.b64decode(b64_str)
            img_id = "img_" + hashlib.md5(raw).hexdigest()[:12]
            img_filename = f"{img_id}.jpg"
            out_path = gallery_dir / img_filename
            thumb_path = thumbs_dir / img_filename

            gallery_file = udir / "gallery.json"
            gallery = []
            if gallery_file.exists():
                try:
                    with open(gallery_file, "r", encoding="utf-8") as f:
                        gallery = json.load(f)
                except Exception:
                    gallery = []

            existing_idx = next((i for i, x in enumerate(gallery) if x.get("id") == img_id), -1)

            # 若图片与缩略图均已存在且在图库记录中，跳过重复的 PIL 缩放编码，大幅提速启动与重发
            if out_path.exists() and thumb_path.exists() and existing_idx != -1:
                if folder or filename:
                    if folder:
                        gallery[existing_idx]["folder"] = folder
                        gallery[existing_idx]["folder_id"] = folder
                    if filename and not str(filename).startswith("img_"):
                        gallery[existing_idx]["filename"] = filename
                    atomic_write_json(gallery_file, gallery, ensure_ascii=False, indent=2)
                return img_id

            im = Image.open(io.BytesIO(raw))
            vhash = compute_image_vhash(im)

            # 检查是否已有感知哈希高度一致的图片（避免从图库选图发送或 Canvas 二次压缩后重复入库）
            if existing_idx == -1 and vhash:
                for idx, item in enumerate(gallery):
                    item_id = item.get("id", "")
                    item_path = gallery_dir / f"{item_id}.jpg"
                    if not item_path.exists():
                        continue
                    item_vhash = item.get("vhash")
                    if not item_vhash:
                        try:
                            with Image.open(item_path) as existing_im:
                                item_vhash = compute_image_vhash(existing_im)
                            item["vhash"] = item_vhash
                        except Exception:
                            item_vhash = ""
                    if item_vhash and vhash_hamming(vhash, item_vhash) <= 3:
                        # 命中同一张图片！若新传入了真实文件名或文件夹则补充更新
                        changed = False
                        if filename and not str(filename).startswith("img_") and str(item.get("filename", "")).startswith("img_"):
                            item["filename"] = filename
                            changed = True
                        if folder and folder != "默认图库":
                            item["folder"] = folder
                            item["folder_id"] = folder
                            changed = True
                        if changed:
                            atomic_write_json(gallery_file, gallery, ensure_ascii=False, indent=2)
                        return item_id

            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                rgba = im.convert("RGBA")
                bg.paste(rgba, mask=rgba.split()[3])
                im = bg
            elif im.mode != "RGB":
                im = im.convert("RGB")
            im.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            im.save(out_path, format="JPEG", quality=80, optimize=True)
            if out_path.stat().st_size > 260_000:
                im.save(out_path, format="JPEG", quality=68, optimize=True)

            thumb = im.copy()
            thumb.thumbnail((200, 200), Image.Resampling.LANCZOS)
            thumb.save(thumb_path, format="JPEG", quality=78, optimize=True)

            prev_entry = gallery[existing_idx] if existing_idx != -1 else {}
            resolved_folder = folder or prev_entry.get("folder") or prev_entry.get("folder_id") or "默认图库"
            entry = {
                "id": img_id,
                "filename": filename or prev_entry.get("filename") or img_filename,
                "folder": resolved_folder,
                "folder_id": resolved_folder,
                "vhash": vhash,
                "size_bytes": out_path.stat().st_size,
                "created_at": time.time(),
                "width": im.width,
                "height": im.height
            }
            if existing_idx != -1:
                gallery[existing_idx] = entry
            else:
                gallery.insert(0, entry)

            atomic_write_json(gallery_file, gallery, ensure_ascii=False, indent=2)
            return img_id
    except Exception as e:
        print(f"自动存入图库异常: {e}")
        return None

def deduplicate_user_gallery(username: str) -> Dict[str, int]:
    """清理图库中的重复副本，优先保留带真实文件名的条目"""
    with _GALLERY_LOCK:
        udir = get_user_dir(username)
        gallery_dir = get_user_gallery_dir(username)
        thumbs_dir = gallery_dir / "thumbs"
        gallery_file = udir / "gallery.json"
        if not gallery_file.exists():
            return {"before": 0, "after": 0, "removed": 0}
        try:
            with open(gallery_file, "r", encoding="utf-8") as f:
                gallery = json.load(f)
        except Exception:
            return {"before": 0, "after": 0, "removed": 0}

        before_count = len(gallery)
        valid_items = []
        removed_ids = []

        for item in gallery:
            img_id = item.get("id", "")
            p = gallery_dir / f"{img_id}.jpg"
            if not p.exists():
                removed_ids.append(img_id)
                continue
            if not item.get("vhash"):
                try:
                    with Image.open(p) as im:
                        item["vhash"] = compute_image_vhash(im)
                except Exception:
                    item["vhash"] = ""
            valid_items.append(item)

        # 优先排序：拥有真实文件名（非 img_ 开头）的排在前面，其次按体积更大/清晰度更高排序
        def _item_priority(x: Dict[str, Any]):
            fname = str(x.get("filename", ""))
            has_real_name = 0 if (fname and not fname.startswith("img_")) else 1
            has_custom_folder = 0 if (x.get("folder") and x.get("folder") != "默认图库") else 1
            return (has_real_name, has_custom_folder, -int(x.get("size_bytes", 0)))

        sorted_items = sorted(valid_items, key=_item_priority)
        kept_items: List[Dict[str, Any]] = []

        for item in sorted_items:
            vh = item.get("vhash", "")
            is_dup = False
            if vh:
                for k in kept_items:
                    if k.get("vhash") and vhash_hamming(vh, k["vhash"]) <= 3:
                        is_dup = True
                        break
            if is_dup:
                removed_ids.append(item.get("id", ""))
            else:
                kept_items.append(item)

        # 删除被去重淘汰的物理文件
        kept_id_set = {x.get("id") for x in kept_items}
        for rid in set(removed_ids):
            if not rid or rid in kept_id_set:
                continue
            for fp in (gallery_dir / f"{rid}.jpg", thumbs_dir / f"{rid}.jpg"):
                try:
                    if fp.exists():
                        fp.unlink()
                except Exception:
                    pass

        # 恢复按创建时间倒序排列
        kept_items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        atomic_write_json(gallery_file, kept_items, ensure_ascii=False, indent=2)

        return {"before": before_count, "after": len(kept_items), "removed": before_count - len(kept_items)}

def init_user_gallery_from_chats(username: str):
    """扫描对话历史提取既有图片至素材库（对已归档图片自动秒级跳过）"""
    udir = get_user_dir(username)
    chats_dir = udir / "chats"
    for cfile in chats_dir.glob("*.json"):
        try:
            with open(cfile, "r", encoding="utf-8") as f:
                cdata = json.load(f)
            for m in cdata.get("messages", []):
                for img_data in m.get("images", []):
                    auto_save_to_gallery(username, img_data)
        except Exception:
            pass
    deduplicate_user_gallery(username)

_WORKSPACE_READY: set = set()

def ensure_user_workspace(username: str):
    """确保用户拥有基础目录与两个默认初始游戏：『🎲 跑团游戏 (proj_default)』与『自由对话 (proj_free_chat)』"""
    user_dir = get_user_dir(username)
    settings_path = user_dir / "settings.json"
    projects_dir = user_dir / "projects"
    # 每个请求都会经过这里：旧数据迁移只需每个进程执行一次，避免反复改写项目文件
    if username in _WORKSPACE_READY and settings_path.exists() \
            and (projects_dir / "proj_default.json").exists() and (projects_dir / "proj_free_chat.json").exists():
        return
    if not settings_path.exists():
        save_user_settings(username, DEFAULT_SETTINGS)

    default_proj_path = projects_dir / "proj_default.json"
    if not default_proj_path.exists():
        atomic_write_json(default_proj_path, normalize_project_schema(DEFAULT_PROJECT), ensure_ascii=False, indent=2)
    else:
        try:
            with open(default_proj_path, "r", encoding="utf-8") as f:
                raw_def = json.load(f)
            if isinstance(raw_def, dict):
                changed_def = False
                if raw_def.get("name") in ("默认游戏", "跑团游戏"):
                    raw_def["name"] = "跑团"
                    raw_def["description"] = ""
                    changed_def = True
                if raw_def.get("icon") == "🎲" or raw_def.get("avatar") == "🎲":
                    raw_def["icon"] = ""
                    raw_def["avatar"] = ""
                    changed_def = True
                if "沉浸式 TRPG 互动叙事跑团" in str(raw_def.get("description") or ""):
                    raw_def["description"] = ""
                    changed_def = True
                def_ogs = raw_def.get("opening_greetings") or []
                def_titles = [str(x.get("title") or "") for x in def_ogs if isinstance(x, dict)]
                if any("（" in t for t in def_titles):
                    raw_def["opening_greetings"] = DEFAULT_PROJECT["opening_greetings"]
                    changed_def = True
                # 移除旧版默认自动塞入的 CoT 思考推演栏（除非用户修改过其默认描述）
                old_mods = raw_def.get("ui_modules")
                if isinstance(old_mods, list):
                    filtered_mods = [
                        m for m in old_mods
                        if not (
                            isinstance(m, dict)
                            and (m.get("id") == "mod_think" or m.get("type") == "thinking_fold")
                            and "分段推演当前场景因果" in str(m.get("desc") or "")
                        )
                    ]
                    if len(filtered_mods) != len(old_mods):
                        raw_def["ui_modules"] = filtered_mods
                        changed_def = True
                if "system_protocol_prompt" not in raw_def:
                    raw_def["system_protocol_prompt"] = DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT
                    changed_def = True
                elif raw_def.get("system_protocol_prompt") is None:
                    raw_def["system_protocol_prompt"] = ""
                    changed_def = True
                elif "【系统提示词 · 功能栏与跑团编写协议（可自由修改或清空）】：\n1. 【🎲 关键节点检定" in str(raw_def.get("system_protocol_prompt") or "") and (
                    "所有栏位缺一不可" not in str(raw_def.get("system_protocol_prompt") or "")
                    or "唯一一次" not in str(raw_def.get("system_protocol_prompt") or "")
                    or "(已消耗)x0" not in str(raw_def.get("system_protocol_prompt") or "")
                ):
                    raw_def["system_protocol_prompt"] = upgrade_legacy_global_protocol_prompt(
                        str(raw_def.get("system_protocol_prompt") or ""), allow_empty=True
                    ) or DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT
                    changed_def = True
                cur_def_suffix = str(raw_def.get("suffix") or "").strip()
                if cur_def_suffix.startswith("【导演执行约束：保持第二人称电影感叙事") and cur_def_suffix != DEFAULT_PROJECT["suffix"]:
                    raw_def["suffix"] = DEFAULT_PROJECT["suffix"]
                    changed_def = True
                if changed_def:
                    atomic_write_json(default_proj_path, normalize_project_schema(raw_def, raw_def), ensure_ascii=False, indent=2)
        except Exception:
            pass

    free_chat_proj_path = projects_dir / "proj_free_chat.json"
    if not free_chat_proj_path.exists():
        atomic_write_json(free_chat_proj_path, normalize_project_schema(DEFAULT_FREE_CHAT_PROJECT), ensure_ascii=False, indent=2)
    else:
        try:
            with open(free_chat_proj_path, "r", encoding="utf-8") as f:
                raw_fc = json.load(f)
            if isinstance(raw_fc, dict):
                changed_fc = False
                if raw_fc.get("name") in ("自由对话", "对话"):
                    raw_fc["name"] = "聊天"
                    changed_fc = True
                if raw_fc.get("icon") in ("🎲", "💬") or raw_fc.get("avatar") in ("🎲", "💬"):
                    raw_fc["icon"] = ""
                    raw_fc["avatar"] = ""
                    changed_fc = True
                if raw_fc.get("category") == "自由对话":
                    raw_fc["category"] = "聊天"
                    changed_fc = True
                if raw_fc.get("tags") == ["自由对话", "小说创作", "角色扮演"]:
                    raw_fc["tags"] = []
                    changed_fc = True
                fc_mods = raw_fc.get("ui_modules")
                fc_ids = {str(m.get("id") or "") for m in (fc_mods or []) if isinstance(m, dict)}
                if fc_ids and fc_ids.issubset({"mod_think", "mod_story", "mod_hero", "mod_stats", "mod_equip", "mod_bag", "mod_inv", "mod_rel", "mod_npc", "mod_choices"}):
                    raw_fc["ui_modules"] = []
                    raw_fc["system_protocol_prompt"] = ""
                    changed_fc = True
                fc_proto = str(raw_fc.get("system_protocol_prompt") or "").strip()
                if not raw_fc.get("ui_modules") and fc_proto.startswith("【系统提示词 ·"):
                    raw_fc["system_protocol_prompt"] = ""
                    changed_fc = True
                if "全能型 AI 创作搭档" in str(raw_fc.get("system_prompt") or "") or "自由对话模式" in str(raw_fc.get("system_prompt") or ""):
                    raw_fc["system_prompt"] = ""
                    raw_fc["system_protocol_prompt"] = ""
                    raw_fc["prefix"] = ""
                    raw_fc["suffix"] = ""
                    changed_fc = True
                if "无拘束自由畅聊" in str(raw_fc.get("description") or ""):
                    raw_fc["description"] = ""
                    changed_fc = True
                fc_ogs = raw_fc.get("opening_greetings") or []
                fc_og_ids = {str(x.get("id") or "") for x in fc_ogs if isinstance(x, dict)}
                if fc_og_ids and fc_og_ids.issubset({"og_free_chat", "og_free_novel", "og_free_rp", "og_free_worldbuild"}):
                    raw_fc["opening_greetings"] = []
                    changed_fc = True
                if changed_fc:
                    atomic_write_json(free_chat_proj_path, normalize_project_schema(raw_fc, raw_fc), ensure_ascii=False, indent=2)
        except Exception:
            pass

    # 清理旧版空白「新游戏 #N」中被自动塞入的默认功能栏（含剧情正文栏）、系统提示词与默认开场白
    try:
        for pfile in projects_dir.glob("*.json"):
            if pfile.name in ("proj_default.json", "proj_free_chat.json"):
                continue
            with open(pfile, "r", encoding="utf-8") as f:
                raw_p = json.load(f)
            if not isinstance(raw_p, dict):
                continue
            p_name = str(raw_p.get("name") or "").strip()
            p_sys = str(raw_p.get("system_prompt") or "").strip()
            p_mods = raw_p.get("ui_modules")
            p_mod_ids = {str(m.get("id") or "") for m in (p_mods or []) if isinstance(m, dict)}
            if p_name.startswith("新游戏") and not p_sys:
                changed_p = False
                if p_mod_ids and p_mod_ids.issubset({"mod_think", "mod_story", "mod_stats", "mod_equip", "mod_inv", "mod_npc", "mod_info", "mod_choices"}):
                    raw_p["ui_modules"] = []
                    changed_p = True
                _sp = str(raw_p.get("system_protocol_prompt") or "").strip()
                if _sp and (_sp == DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT.strip() or _sp.startswith("【全局底层系统提示词")):
                    raw_p["system_protocol_prompt"] = ""
                    changed_p = True
                raw_og_list = raw_p.get("opening_greetings")
                if isinstance(raw_og_list, list) and len(raw_og_list) == 1 and isinstance(raw_og_list[0], dict) and raw_og_list[0].get("content") == "开始游戏":
                    raw_p["opening_greetings"] = []
                    changed_p = True
                if changed_p:
                    atomic_write_json(pfile, normalize_project_schema(raw_p, raw_p), ensure_ascii=False, indent=2)
    except Exception:
        pass
    _WORKSPACE_READY.add(username)

def init_system_and_migrate():
    """系统启动初始化：为已有用户初始化默认工作区结构"""
    users = load_users()
    for uname in list(users.keys()) + ["player"]:
        ensure_user_workspace(uname)

init_system_and_migrate()

# ==================== 设备与 IP 分析 ====================
def get_client_ip(request: Request) -> str:
    # 优先识别反向代理传递的真实客户端 IP
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    x_real = request.headers.get("x-real-ip")
    if x_real:
        return x_real.strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"

def parse_device_info(ua_string: str) -> str:
    if not ua_string:
        return "未知设备"
    ua = ua_string.lower()
    os_name = "其他设备"
    if "iphone" in ua:
        os_name = "iPhone"
    elif "ipad" in ua:
        os_name = "iPad"
    elif "android" in ua:
        os_name = "Android 手机"
    elif "windows" in ua:
        os_name = "Windows PC"
    elif "macintosh" in ua or "mac os" in ua:
        os_name = "Mac"
    elif "linux" in ua:
        os_name = "Linux"

    browser = "浏览器"
    if "micromessenger" in ua:
        browser = "微信内置"
    elif "edg" in ua:
        browser = "Edge"
    elif "chrome" in ua and "safari" in ua:
        browser = "Chrome"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    elif "firefox" in ua:
        browser = "Firefox"

    return f"{os_name} ({browser})"

# ==================== 用户认证依赖 (免登录默认直进 player，同时支持已登录账号 Session 隔离) ====================
def get_current_user(request: Request) -> str:
    token = request.cookies.get("session_token")
    if not token:
        auth_hdr = request.headers.get("authorization") or ""
        if auth_hdr.startswith("Bearer "):
            token = auth_hdr[7:].strip()
    if token:
        with _USERS_AUTH_LOCK:
            sess = SESSIONS.get(token)
            if isinstance(sess, dict):
                now = time.time()
                if safe_float(sess.get("expires_at"), 0.0) > now:
                    uname = str(sess.get("username") or "").strip()
                    if uname:
                        sess["last_seen_at"] = now
                        ensure_user_workspace(uname)
                        return uname
                else:
                    SESSIONS.pop(token, None)
    ensure_user_workspace("player")
    return "player"


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_PENDING_BROWSER_OPEN_URL: Optional[str] = None
_WAS_PORT_REPLACED: bool = False


def _is_same_origin_request(request: Request) -> bool:
    """校验状态变更请求的 Origin / Referer，拦截外部恶意网页或沙盒 iframe 的跨站请求伪造 (CSRF)"""
    origin = (request.headers.get("origin") or "").strip()
    referer = (request.headers.get("referer") or "").strip()
    if not origin and not referer:
        # 非浏览器客户端（本地脚本 / CLI / 单元测试）不携带 Origin/Referer，予以放行
        return True
    src_raw = origin or referer
    if src_raw.lower() == "null":
        # 沙盒 iframe 或 data:/file: 页面发出的跨源请求，必须拒绝
        return False
    try:
        src_host = (urlparse(src_raw).hostname or "").strip().lower()
    except Exception:
        return False
    if not src_host:
        return False

    raw_host_hdr = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
    req_host = ""
    if raw_host_hdr:
        try:
            req_host = (urlparse(f"http://{raw_host_hdr}").hostname or "").strip().lower()
        except Exception:
            req_host = raw_host_hdr.split(":")[0].strip().lower()

    if src_host == req_host:
        return True
    if src_host in _LOOPBACK_HOSTS and req_host in _LOOPBACK_HOSTS:
        return True

    pub_url = os.environ.get("PUBLIC_URL", "").strip()
    if pub_url:
        try:
            pub_host = (urlparse(pub_url).hostname or "").strip().lower()
            if pub_host and src_host == pub_host:
                return True
        except Exception:
            pass
    return False


@asynccontextmanager
async def _app_lifespan(app_instance: FastAPI):
    if _PENDING_BROWSER_OPEN_URL:
        target_url = _PENDING_BROWSER_OPEN_URL

        def _open_after_ready():
            if _WAS_PORT_REPLACED:
                time.sleep(0.6)
            else:
                time.sleep(0.15)
            if _HAS_ACTIVE_CLIENT:
                return
            try:
                webbrowser.open(target_url, new=0, autoraise=True)
            except Exception:
                pass

        threading.Thread(target=_open_after_ready, daemon=True).start()
    try:
        yield
    finally:
        pending_tasks = [t for t in list(ACTIVE_BG_TASKS.values()) if t and not t.done()]
        for t in pending_tasks:
            t.cancel()
        if pending_tasks:
            try:
                await asyncio.wait(pending_tasks, timeout=2.0)
            except Exception:
                pass
        ACTIVE_BG_TASKS.clear()
        ACTIVE_PARTIAL_TEXT.clear()
        await shutdown_local_engines()


# ==================== FastAPI 应用与路由 ====================
APP_VERSION = "alpha 1.4"
app = FastAPI(title="AI TRPG", version=APP_VERSION, lifespan=_app_lifespan)

app.include_router(
    create_enterprise_router(
        get_current_user=get_current_user,
        get_user_dir=get_user_dir,
        get_user_projects_dir=get_user_projects_dir,
        get_user_chats_dir=get_user_chats_dir,
        get_user_gallery_dir=get_user_gallery_dir,
        load_user_settings=load_user_settings,
        save_user_settings=save_user_settings,
        auto_save_to_gallery=auto_save_to_gallery
    )
)

_HAS_ACTIVE_CLIENT = False

@app.middleware("http")
async def disable_static_cache_middleware(request: Request, call_next):
    global _HAS_ACTIVE_CLIENT
    path = request.url.path
    if request.method.upper() in ("POST", "PUT", "DELETE", "PATCH") and path.startswith("/api/"):
        if not _is_same_origin_request(request):
            return JSONResponse(status_code=403, content={"detail": "跨站请求已被安全策略拦截 (CSRF Origin Mismatch)"})
    _HAS_ACTIVE_CLIENT = True
    response = await call_next(request)
    if path == "/" or path.endswith(".js") or path.endswith(".css") or path.endswith(".html") or "/configuration" in path:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", response_class=HTMLResponse)
@app.get("/zh/app/{app_id}/configuration", response_class=HTMLResponse)
@app.get("/app/{app_id}/configuration", response_class=HTMLResponse)
def read_root(app_id: Optional[str] = None):
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(
            content=index_path.read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
        )
    return HTMLResponse("<h1>Loading...</h1>")

# ==================== 账号系统 API ====================
FAILED_LOGIN_TRACKER: Dict[str, List[float]] = {}

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

@app.post("/api/auth/login")
def api_login(req: LoginRequest, request: Request, response: Response):
    now = time.time()
    client_ip = get_client_ip(request)
    recent_fails = [t for t in FAILED_LOGIN_TRACKER.get(client_ip, []) if now - t < 60]
    if len(recent_fails) >= 8:
        raise HTTPException(status_code=429, detail="尝试过多，1 分钟后再试")

    users = load_users()
    uname = req.username.strip()
    if not uname or not req.password:
        raise HTTPException(status_code=400, detail="请输入账号和密码")

    # 首次启动（尚无任何账号）时，首次登录自动创建初始管理员账号
    if not users:
        if len(req.password) < 6:
            raise HTTPException(status_code=400, detail="密码至少 6 位")
        pwd_hash, salt = hash_password(req.password)
        users[uname] = {
            "username": uname,
            "password_hash": pwd_hash,
            "salt": salt,
            "role": "admin",
            "created_at": now,
            "login_history": []
        }
        save_users(users)
        ensure_user_workspace(uname)
    elif uname not in users:
        recent_fails.append(now)
        FAILED_LOGIN_TRACKER[client_ip] = recent_fails
        raise HTTPException(status_code=400, detail="账号或密码错误")

    user_data = users[uname]
    if not verify_password(req.password, user_data.get("password_hash", ""), user_data.get("salt", "")):
        recent_fails.append(now)
        FAILED_LOGIN_TRACKER[client_ip] = recent_fails
        raise HTTPException(status_code=400, detail="账号或密码错误")

    ensure_user_workspace(uname)
    FAILED_LOGIN_TRACKER.pop(client_ip, None)
    token = secrets.token_urlsafe(32)
    user_agent = request.headers.get("user-agent", "")
    device_name = parse_device_info(user_agent)

    # 记录接入历史
    login_entry = {
        "id": secrets.token_hex(4),
        "time": now,
        "ip": client_ip,
        "device": device_name,
        "user_agent": user_agent[:180]
    }
    history = user_data.get("login_history", [])
    history.insert(0, login_entry)
    user_data["login_history"] = history[:50]
    user_data["last_login_at"] = now
    user_data["last_login_ip"] = client_ip
    user_data["last_login_device"] = device_name
    save_users(users)

    # 记录活跃 Session
    SESSIONS[token] = {
        "username": uname,
        "created_at": now,
        "last_seen_at": now,
        "ip": client_ip,
        "device": device_name,
        "user_agent": user_agent[:180],
        "expires_at": now + 30 * 24 * 3600
    }
    save_sessions()

    # 设置登录 Cookie
    response.set_cookie(
        key="session_token",
        value=token,
        max_age=30 * 24 * 3600,
        httponly=False,
        samesite="lax",
        path="/"
    )

    return {
        "status": "ok",
        "token": token,
        "user": {
            "username": uname,
            "role": user_data.get("role", "user"),
            "device": device_name,
            "current_device": device_name,
            "ip": client_ip,
            "current_ip": client_ip,
            "login_history": user_data.get("login_history", [])[:30]
        }
    }

@app.post("/api/auth/logout")
def api_logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if not token:
        auth_hdr = request.headers.get("authorization")
        if auth_hdr and auth_hdr.startswith("Bearer "):
            token = auth_hdr[7:].strip()
    if token and token in SESSIONS:
        del SESSIONS[token]
        save_sessions()
    response.delete_cookie("session_token", path="/")
    return {"status": "ok"}

@app.post("/api/auth/password")
def api_change_password(req: ChangePasswordRequest, username: str = Depends(get_current_user)):
    users = load_users()
    if username not in users:
        raise HTTPException(status_code=404, detail="账号不存在")
    user_data = users[username]
    if not verify_password(req.old_password, user_data.get("password_hash", ""), user_data.get("salt", "")):
        raise HTTPException(status_code=400, detail="原密码错误")
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    pwd_hash, salt = hash_password(req.new_password)
    user_data["password_hash"] = pwd_hash
    user_data["salt"] = salt
    save_users(users)
    return {"status": "ok"}

@app.get("/api/auth/me")
def api_me(request: Request, username: str = Depends(get_current_user)):
    client_ip = get_client_ip(request)
    device_name = parse_device_info(request.headers.get("user-agent", ""))
    return {
        "status": "ok",
        "user": {
            "username": username,
            "role": "admin",
            "ip": client_ip,
            "current_ip": client_ip,
            "device": device_name,
            "current_device": device_name,
            "last_login_at": time.time(),
            "login_history": []
        }
    }

@app.post("/api/auth/register")
def api_register(req: LoginRequest):
    users = load_users()
    if users:
        raise HTTPException(status_code=403, detail="注册已关闭")
    uname = req.username.strip()
    if not uname or len(req.password) < 6:
        raise HTTPException(status_code=400, detail="用户名必填，密码至少 6 位")
    pwd_hash, salt = hash_password(req.password)
    users[uname] = {
        "username": uname,
        "password_hash": pwd_hash,
        "salt": salt,
        "role": "admin",
        "created_at": time.time(),
        "login_history": []
    }
    save_users(users)
    ensure_user_workspace(uname)
    return {"status": "ok", "username": uname}

# ==================== 账号专属图片素材库 API ====================
@app.get("/api/gallery")
def get_gallery(username: str = Depends(get_current_user)):
    with _GALLERY_LOCK:
        udir = get_user_dir(username)
        gallery_file = udir / "gallery.json"
        if gallery_file.exists():
            try:
                with open(gallery_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return sorted(data, key=lambda x: x.get("created_at", 0), reverse=True)
            except Exception:
                pass
        return []

class GalleryUploadReq(BaseModel):
    image_base64: str
    filename: Optional[str] = None
    folder: Optional[str] = None

@app.post("/api/gallery/upload")
def upload_to_gallery(req: GalleryUploadReq, username: str = Depends(get_current_user)):
    img_id = auto_save_to_gallery(username, req.image_base64, req.filename, req.folder)
    if not img_id:
        raise HTTPException(status_code=400, detail="保存失败")
    return {
        "status": "ok",
        "id": img_id,
        "folder": req.folder or "默认图库",
        "url": f"/api/gallery/image/{img_id}",
        "thumb_url": f"/api/gallery/thumb/{img_id}"
    }

@app.get("/api/gallery/image/{img_id}")
def get_gallery_image(img_id: str, username: str = Depends(get_current_user)):
    safe_img_id = sanitize_id(img_id)
    udir = get_user_dir(username)
    p = udir / "gallery" / f"{safe_img_id}.jpg"
    if not p.exists():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(p, media_type="image/jpeg")

@app.get("/api/gallery/thumb/{img_id}")
def get_gallery_thumb(img_id: str, username: str = Depends(get_current_user)):
    safe_img_id = sanitize_id(img_id)
    udir = get_user_dir(username)
    p = udir / "gallery" / "thumbs" / f"{safe_img_id}.jpg"
    if not p.exists():
        p = udir / "gallery" / f"{safe_img_id}.jpg"
    if not p.exists():
        raise HTTPException(status_code=404, detail="缩略图不存在")
    return FileResponse(p, media_type="image/jpeg")

@app.get("/api/gallery/data_url/{img_id}")
def get_gallery_data_url(img_id: str, username: str = Depends(get_current_user)):
    safe_img_id = sanitize_id(img_id)
    udir = get_user_dir(username)
    p = udir / "gallery" / f"{safe_img_id}.jpg"
    if not p.exists():
        raise HTTPException(status_code=404, detail="图片不存在")
    with open(p, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return {"status": "ok", "data_url": f"data:image/jpeg;base64,{b64}"}

@app.delete("/api/gallery/{img_id}")
def delete_gallery_image(img_id: str, username: str = Depends(get_current_user)):
    safe_img_id = sanitize_id(img_id)
    with _GALLERY_LOCK:
        udir = get_user_dir(username)
        p = udir / "gallery" / f"{safe_img_id}.jpg"
        if p.exists():
            p.unlink()
        tp = udir / "gallery" / "thumbs" / f"{safe_img_id}.jpg"
        if tp.exists():
            tp.unlink()
        gallery_file = udir / "gallery.json"
        if gallery_file.exists():
            try:
                with open(gallery_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data = [x for x in data if x.get("id") != safe_img_id]
                atomic_write_json(gallery_file, data, ensure_ascii=False, indent=2)
            except Exception:
                pass
    return {"status": "ok"}

@app.post("/api/gallery/deduplicate")
def api_deduplicate_gallery(username: str = Depends(get_current_user)):
    stats = deduplicate_user_gallery(username)
    return {"status": "ok", **stats}

# ==================== 设置 API (每个用户独立，API Key 脱敏防泄露) ====================
API_KEY_MASK_TOKEN = "****"


def mask_api_key(raw_key: Any) -> str:
    s = str(raw_key or "").strip()
    if not s:
        return ""
    if len(s) <= 8:
        return API_KEY_MASK_TOKEN
    return f"{s[:4]}{API_KEY_MASK_TOKEN}{s[-4:]}"


def is_masked_api_key(val: Any) -> bool:
    s = str(val or "").strip()
    return bool(s and API_KEY_MASK_TOKEN in s)


def mask_settings_for_client(settings: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(settings)
    raw_k = str(out.get("api_key") or "").strip()
    out["has_api_key"] = bool(raw_k)
    out["api_key"] = mask_api_key(raw_k)
    return out


def _sanitize_settings_numbers(target: Dict[str, Any]) -> Dict[str, Any]:
    target["temperature"] = safe_float(target.get("temperature"), 0.68)
    target["repetition_penalty"] = safe_float(target.get("repetition_penalty"), 1.05)
    target["frequency_penalty"] = safe_float(target.get("frequency_penalty"), 0.0)
    target["presence_penalty"] = safe_float(target.get("presence_penalty"), 0.25)
    target["top_p"] = safe_float(target.get("top_p"), 0.90)
    target["top_k"] = max(0, safe_int(target.get("top_k"), 40))
    target["min_p"] = safe_float(target.get("min_p"), 0.06)
    target["max_tokens"] = max(64, safe_int(target.get("max_tokens"), 12288))
    target["context"] = max(1, safe_int(target.get("context", target.get("max_context_turns", 16)), 16))
    target["max_context_turns"] = target["context"]
    target["max_context_k"] = max(4, safe_int(target.get("max_context_k"), 64))
    target["keep_recent_messages"] = max(2, safe_int(target.get("keep_recent_messages"), 6))
    target["worldbook_scan_depth"] = max(1, safe_int(target.get("worldbook_scan_depth"), 5))
    target["thinking_budget"] = max(0, safe_int(target.get("thinking_budget"), 1024))
    return target


@app.get("/api/settings")
def get_settings(username: str = Depends(get_current_user)):
    return mask_settings_for_client(load_user_settings(username))

@app.post("/api/settings")
async def update_settings(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    payload = dict(payload or {})
    payload.pop("has_api_key", None)
    with _USER_SETTINGS_LOCK:
        current = load_user_settings(username)
        old_model = str(current.get("model") or "").strip()
        existing_model_params = copy.deepcopy(current.get("model_params") or {})
        preserved_api_key = str(current.get("api_key") or "")
        if "api_key" in payload:
            if is_masked_api_key(payload.get("api_key")):
                payload["api_key"] = preserved_api_key
            else:
                payload["api_key"] = str(payload.get("api_key") or "").strip()
        current.update(payload)
        if any(k in payload for k in ("global_system_protocol_prompt", "erotic_level", "violence_level", "erotic_enabled", "violence_enabled")):
            if "global_system_protocol_prompt" in payload:
                raw_gp = payload.get("global_system_protocol_prompt")
                clean_gp = "" if raw_gp is None else upgrade_legacy_global_protocol_prompt(str(raw_gp), allow_empty=True)
                current["global_system_protocol_prompt"] = clean_gp
            if "erotic_level" in payload:
                current["erotic_level"] = max(0, min(5, safe_int(payload.get("erotic_level"), 3)))
            if "violence_level" in payload:
                current["violence_level"] = max(0, min(5, safe_int(payload.get("violence_level"), 3)))
            if "erotic_enabled" in payload:
                current["erotic_enabled"] = bool(payload.get("erotic_enabled"))
            if "violence_enabled" in payload:
                current["violence_enabled"] = bool(payload.get("violence_enabled"))
            active_pid = sanitize_id(current.get("active_project_id") or "proj_default")
            active_pfile = get_user_projects_dir(username) / f"{active_pid}.json"
            if active_pfile.exists():
                try:
                    with open(active_pfile, "r", encoding="utf-8") as f:
                        raw_proj = json.load(f)
                    if isinstance(raw_proj, dict):
                        if "global_system_protocol_prompt" in payload and not is_free_chat_project(raw_proj):
                            raw_proj["system_protocol_prompt"] = current["global_system_protocol_prompt"]
                        if "erotic_level" in payload:
                            raw_proj["erotic_level"] = current["erotic_level"]
                        if "violence_level" in payload:
                            raw_proj["violence_level"] = current["violence_level"]
                        if "erotic_enabled" in payload:
                            raw_proj["erotic_enabled"] = current["erotic_enabled"]
                        if "violence_enabled" in payload:
                            raw_proj["violence_enabled"] = current["violence_enabled"]
                        atomic_write_json(active_pfile, raw_proj, ensure_ascii=False, indent=2)
                except Exception:
                    pass
        if "model_params" in payload and isinstance(payload["model_params"], dict):
            current["model_params"] = {**existing_model_params, **payload["model_params"]}
        else:
            current["model_params"] = existing_model_params
        if "context" in payload:
            current["context"] = max(1, safe_int(payload["context"], 16))
            current["max_context_turns"] = current["context"]
        elif "max_context_turns" in payload:
            current["max_context_turns"] = max(1, safe_int(payload["max_context_turns"], 16))
            current["context"] = current["max_context_turns"]
        _sanitize_settings_numbers(current)
        save_user_settings(username, current)

    # 同步全局数值参数至启用「跟随全局参数 (use_global_params=True)」的项目（保留独立参数项目的自定义配置）
    param_keys = (
        "temperature", "repetition_penalty", "frequency_penalty", "presence_penalty",
        "top_p", "top_k", "min_p", "max_tokens", "context_mode", "context",
        "max_context_k", "keep_recent_messages", "worldbook_scan_depth", "thinking_budget"
    )
    if any(k in payload for k in param_keys) or "auto_summarize" in payload:
        projects_dir = get_user_projects_dir(username)
        for p in projects_dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if not isinstance(raw, dict) or raw.get("use_global_params", True) is False:
                    continue
                cp = dict(raw.get("completion_params") or {})
                for k in param_keys:
                    if k in current:
                        cp[k] = current[k]
                raw["completion_params"] = cp
                raw["max_context_turns"] = safe_int(current.get("context", 16), 16)
                raw["auto_summarize"] = bool(current.get("auto_summarize", True))
                atomic_write_json(p, raw, ensure_ascii=False, indent=2)
            except Exception:
                pass

    new_model = str(current.get("model") or "").strip()
    if "model" in payload and new_model and new_model != old_model:
        ep = resolve_model_endpoint(new_model, current)
        if ep.get("is_local"):
            asyncio.create_task(ensure_local_engine_ready(new_model))

    return {"status": "ok", "settings": mask_settings_for_client(current)}

@app.post("/api/settings/model_params")
def update_single_model_params(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    """保存或清除单个 AI 模型的独立参数（最高优先级，永不被全局参数覆盖）"""
    model_id = str(payload.get("model") or "").strip()
    if not model_id:
        raise HTTPException(status_code=400, detail="缺少模型名")
    with _USER_SETTINGS_LOCK:
        settings = load_user_settings(username)
        model_params = dict(settings.get("model_params") or {})
        if payload.get("clear"):
            model_params.pop(model_id, None)
        else:
            params = payload.get("params") or {}
            if isinstance(params, dict) and params:
                model_params[model_id] = params
            else:
                model_params.pop(model_id, None)
        settings["model_params"] = model_params
        save_user_settings(username, settings)
    return {"status": "ok", "model": model_id, "model_params": model_params}

@app.post("/api/settings/sync_params_to_projects")
def sync_global_params_to_all_projects(payload: Optional[Dict[str, Any]] = None, username: str = Depends(get_current_user)):
    """一键将全局默认模型数值参数同步到当前用户的所有游戏"""
    with _USER_SETTINGS_LOCK:
        settings = load_user_settings(username)
        if payload:
            clean_p = dict(payload)
            clean_p.pop("has_api_key", None)
            if "api_key" in clean_p and is_masked_api_key(clean_p.get("api_key")):
                clean_p.pop("api_key", None)
            settings.update(clean_p)
            if "context" in clean_p:
                settings["context"] = max(1, safe_int(clean_p["context"], 16))
                settings["max_context_turns"] = settings["context"]
            _sanitize_settings_numbers(settings)
            save_user_settings(username, settings)

    global_comp = get_default_completion_params(global_defaults=settings)
    auto_sum = bool(settings.get("auto_summarize", True))

    force_override = bool((payload or {}).get("force_override_independent", False))
    projects_dir = get_user_projects_dir(username)
    updated_count = 0
    skipped_independent = 0
    for p in projects_dir.glob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                continue
            if raw.get("use_global_params", True) is False and not force_override:
                skipped_independent += 1
                continue
            raw["completion_params"] = {**(raw.get("completion_params") or {}), **global_comp}
            raw["max_context_turns"] = global_comp["context"]
            raw["auto_summarize"] = auto_sum
            norm = normalize_project_schema(raw, raw, global_defaults=settings)
            atomic_write_json(p, norm, ensure_ascii=False, indent=2)
            updated_count += 1
        except Exception as e:
            print(f"同步全局参数到游戏失败 ({p.name}): {e}")

    return {
        "status": "ok",
        "updated_count": updated_count,
        "skipped_independent": skipped_independent,
        "completion_params": global_comp,
        "settings": mask_settings_for_client(settings),
    }

# ==================== 模型列表与价格 API ====================
def _format_model_pricing_entry(m: Dict[str, Any]) -> Dict[str, Any]:
    name = m.get("model_name", "")
    qtype = m.get("quota_type", 0)
    desc = (m.get("description") or "").strip()
    if qtype == 1:
        price_val = m.get("model_price", 0)
        short_price = f"${price_val:.4g}/次"
        detail_price = f"API 按次：${price_val:.4g}/次"
        billing_type = "per_call"
    else:
        mr = m.get("model_ratio", 0)
        cr = m.get("completion_ratio", 1) or 1
        inp = mr * 2.0
        out = inp * cr
        cache_r = m.get("cache_ratio", 0)
        cache_part = f" · 缓${inp * cache_r:.4g}/M" if cache_r else ""
        short_price = f"入${inp:.4g}/M · 出${out:.4g}/M"
        detail_price = f"API 按量：输入 ${inp:.4g}/M · 输出 ${out:.4g}/M{cache_part}"
        billing_type = "token"
    return {
        "id": name,
        "billing_type": billing_type,
        "short_price": short_price,
        "detail_price": detail_price,
        "description": desc,
        "groups": m.get("enable_groups", [])
    }

@app.get("/api/models")
async def get_available_models(username: str = Depends(get_current_user)):
    settings = load_user_settings(username)
    proxy = settings.get("proxy") if settings.get("use_proxy") else None
    raw_base_url = (settings.get("base_url") or "").strip().rstrip("/")
    api_key = (settings.get("api_key") or "").strip()
    api_protocol = (settings.get("api_protocol") or "auto").strip().lower()

    norm = normalize_api_endpoint_and_protocol(raw_base_url, api_key, api_protocol)
    base_url = norm["base_url"]
    detected_proto = norm["protocol"]
    site_root = base_url[:-3] if base_url.endswith("/v1") else base_url

    discovered_locals = await discover_local_models(settings)
    combined_local_catalog = list(LOCAL_MODELS_CATALOG)
    existing_local_ids = {m["id"] for m in combined_local_catalog}
    for dm in discovered_locals:
        if dm["id"] not in existing_local_ids:
            combined_local_catalog.append(dm)
            existing_local_ids.add(dm["id"])

    local_models_list = [
        {
            "id": m["id"],
            "name": m["name"],
            "group": "Local",
            "engine": m["engine"],
            "supports_vision": m["supports_vision"],
            "gguf_path": m.get("gguf_path", ""),
            "shards_complete": m.get("shards_complete", True),
            "shard_warning": m.get("shard_warning", ""),
            "source_label": m.get("source_label", ""),
            "strata_config": m.get("strata_config", ""),
            "aliases": m.get("aliases", []),
        }
        for m in combined_local_catalog
    ]

    recommendations: List[Dict[str, Any]] = []

    pricing_map: Dict[str, Any] = {}
    for lm in combined_local_catalog:
        pricing_map[lm["id"]] = {
            "id": lm["id"],
            "billing_type": "local",
            "short_price": lm["short_price"],
            "detail_price": lm["detail_price"],
            "description": lm["description"],
            "groups": ["local"]
        }

    raw_models: List[str] = []
    # 只要有归一化后的 base_url，且 (用户填了 raw_base_url，或填了 api_key 且识别出了官方协议，或手动选择了非 openai/auto 的自带默认地址协议)
    should_fetch_remote = bool(base_url) and bool(raw_base_url or api_key or api_protocol in ("gemini", "claude", "ollama"))
    if should_fetch_remote:
        try:
            headers = dict(norm["headers"])
            headers.pop("Content-Type", None)
            async with httpx.AsyncClient(proxy=proxy, trust_env=False, timeout=8.0) as client:
                models_task = client.get(f"{base_url}/models", headers=headers)
                pricing_task = client.get(f"{site_root}/api/pricing") if raw_base_url else asyncio.sleep(0, result=None)
                results = await asyncio.gather(models_task, pricing_task, return_exceptions=True)

                resp_models, resp_pricing = results[0], results[1]
                if resp_pricing is not None and not isinstance(resp_pricing, Exception) and getattr(resp_pricing, "status_code", 0) == 200:
                    try:
                        pdata = resp_pricing.json()
                        if isinstance(pdata, dict):
                            for item in pdata.get("data", []):
                                mname = item.get("model_name") if isinstance(item, dict) else None
                                if mname:
                                    pricing_map[mname] = _format_model_pricing_entry(item)
                    except Exception:
                        pass

                def _extract_model_ids(resp_obj) -> List[str]:
                    if isinstance(resp_obj, Exception) or getattr(resp_obj, "status_code", 0) != 200:
                        return []
                    try:
                        data = resp_obj.json()
                        items = (
                            data.get("data")
                            if isinstance(data, dict) and "data" in data
                            else (data.get("models") if isinstance(data, dict) and "models" in data else (data if isinstance(data, list) else []))
                        )
                        out: List[str] = []
                        for m in (items or []):
                            if isinstance(m, dict):
                                mid = m.get("id") or m.get("name") or ""
                                if mid.startswith("models/"):
                                    mid = mid[len("models/"):]
                                if mid:
                                    out.append(mid)
                        return out
                    except Exception:
                        return []

                raw_models = _extract_model_ids(resp_models)
                # 若 Gemini 官方 /v1beta/openai/models 未返回，回退尝试原生 /v1beta/models?key=
                if not raw_models and detected_proto == "gemini" and api_key:
                    gemini_root = norm["raw_clean_url"] or "https://generativelanguage.googleapis.com"
                    if gemini_root.endswith("/v1beta/openai"):
                        gemini_root = gemini_root[:-len("/v1beta/openai")]
                    resp_gem = await client.get(f"{gemini_root}/v1beta/models", params={"key": api_key})
                    raw_models = _extract_model_ids(resp_gem)
                # 若 Ollama /v1/models 未返回，回退尝试 /api/tags
                if not raw_models and detected_proto == "ollama":
                    ollama_root = base_url[:-3] if base_url.endswith("/v1") else base_url
                    resp_ol = await client.get(f"{ollama_root}/api/tags")
                    raw_models = _extract_model_ids(resp_ol)
                # 若用户填写了不含 /v1 的地址且归一化补全后的地址成功拿到模型，同步保存归一化地址（重读最新配置避免覆盖并发保存）
                if raw_models and raw_base_url and base_url != raw_base_url:
                    with _USER_SETTINGS_LOCK:
                        latest_s = load_user_settings(username)
                        if (latest_s.get("base_url") or "").strip().rstrip("/") == raw_base_url:
                            latest_s["base_url"] = base_url
                            save_user_settings(username, latest_s)
                            settings = latest_s
        except Exception as e:
            print(f"获取模型列表或价格失败: {e}")

    local_ids = [m["id"] for m in combined_local_catalog]
    if not raw_models and pricing_map:
        raw_models = [k for k in pricing_map.keys() if k not in local_ids]

    fresh_settings = load_user_settings(username)
    custom_models = [str(m).strip() for m in (fresh_settings.get("custom_models") or []) if str(m).strip()]
    all_known_ids = list(dict.fromkeys(custom_models + local_ids + raw_models + list(pricing_map.keys())))
    current_model = fresh_settings.get("model", "")
    if all_known_ids and (
        not current_model
        or (current_model not in all_known_ids and not raw_base_url and not api_key and not fresh_settings.get("local_base_url"))
    ):
        current_model = local_ids[0] if local_ids else all_known_ids[0]
        with _USER_SETTINGS_LOCK:
            latest_s = load_user_settings(username)
            if not latest_s.get("model") or latest_s.get("model") == fresh_settings.get("model", ""):
                latest_s["model"] = current_model
                save_user_settings(username, latest_s)
            else:
                current_model = latest_s["model"]

    return {
        "status": "ok",
        "models": all_known_ids,
        "remote_models": raw_models,
        "custom_models": custom_models,
        "local_models": local_models_list,
        "recommendations": recommendations,
        "pricing": pricing_map,
        "favorite_models": settings.get("favorite_models", []),
        "current": current_model,
        "normalized_base_url": base_url if raw_base_url else "",
        "api_protocol": norm["configured_protocol"],
        "detected_protocol": detected_proto
    }

# ==================== 项目 / 应用编排 API (用户隔离，1:1 完整企业级 Schema) ====================
@app.get("/api/projects")
def list_projects(username: str = Depends(get_current_user)):
    ensure_user_workspace(username)
    settings = load_user_settings(username)
    projects_dir = get_user_projects_dir(username)
    projects = []
    for p in projects_dir.glob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                raw = json.load(f)
                projects.append(normalize_project_schema(raw, raw, global_defaults=settings))
        except Exception:
            pass

    def _proj_sort_key(item: Dict[str, Any]):
        pid = item.get("id", "")
        if pid == "proj_default":
            return (0, 0)
        if pid == "proj_free_chat":
            return (1, 0)
        return (2, -float(item.get("updated_at", 0) or 0))

    projects.sort(key=_proj_sort_key)
    return projects

@app.get("/api/projects/{project_id}")
def get_project(project_id: str, username: str = Depends(get_current_user)):
    ensure_user_workspace(username)
    project_id = sanitize_id(project_id)
    settings = load_user_settings(username)
    file_path = get_user_projects_dir(username) / f"{project_id}.json"
    if not file_path.exists():
        tpl = next((a for a in EXPLORE_PRESET_APPS if a["id"] == project_id), None)
        if tpl:
            norm = normalize_project_schema(tpl, global_defaults=settings)
            atomic_write_json(file_path, norm, ensure_ascii=False, indent=2)
            return norm
        raise HTTPException(status_code=404, detail="剧本不存在")
    with open(file_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
        return normalize_project_schema(raw, raw, global_defaults=settings)

@app.post("/api/projects")
def save_project(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    project_id = sanitize_id(payload.get("id") or f"proj_{uuid.uuid4().hex[:8]}")
    payload["id"] = project_id
    settings = load_user_settings(username)
    existing = {}
    file_path = get_user_projects_dir(username) / f"{project_id}.json"
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass

    data = normalize_project_schema(payload, existing, global_defaults=settings)
    atomic_write_json(file_path, data, ensure_ascii=False, indent=2)

    with _USER_SETTINGS_LOCK:
        latest_settings = load_user_settings(username)
        settings_changed = False
        if not latest_settings.get("active_project_id"):
            latest_settings["active_project_id"] = project_id
            settings_changed = True
        if (
            "system_protocol_prompt" in payload
            and latest_settings.get("active_project_id") == project_id
            and not is_free_chat_project(data)
        ):
            latest_settings["global_system_protocol_prompt"] = data.get("system_protocol_prompt", "")
            settings_changed = True
        if settings_changed:
            save_user_settings(username, latest_settings)

    return {"status": "ok", "project": data}

@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str, username: str = Depends(get_current_user)):
    project_id = sanitize_id(project_id)
    if project_id in ("proj_default", "proj_free_chat"):
        raise HTTPException(status_code=400, detail="默认剧本不可删除")
    file_path = get_user_projects_dir(username) / f"{project_id}.json"
    if file_path.exists():
        file_path.unlink()

    # 将该项目下的对话迁移至默认项目
    chats_dir = get_user_chats_dir(username)
    for p in chats_dir.glob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                cdata = json.load(f)
            if cdata.get("project_id") == project_id:
                cdata["project_id"] = "proj_default"
                atomic_write_json(p, cdata, ensure_ascii=False, indent=2)
        except Exception:
            pass

    return {"status": "ok"}

# ==================== 网络与远程访问支持 ====================
SERVER_PORT = 8765

def get_local_ip() -> str:
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if ip.startswith("192.168.") or ip.startswith("10.") or (ip.startswith("172.") and int(ip.split('.')[1]) in range(16, 32)):
                return ip
    except Exception:
        pass
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        s.close()

def get_network_info() -> Dict[str, Any]:
    ip = get_local_ip()
    pub_url = os.environ.get("PUBLIC_URL", "").strip()
    if not pub_url:
        pub_file = BASE_DIR / "public_url.txt"
        if pub_file.exists():
            try:
                candidate = pub_file.read_text(encoding="utf-8").strip()
                if candidate.startswith("http"):
                    pub_url = candidate
            except Exception:
                pass
    return {
        "local_url": f"http://127.0.0.1:{SERVER_PORT}",
        "lan_url": f"http://{ip}:{SERVER_PORT}",
        "public_url": pub_url
    }

@app.get("/api/network_info")
def api_network_info():
    return get_network_info()

# ==================== 对话管理 API (用户隔离) ====================
@app.get("/api/chats")
def list_chats(project_id: Optional[str] = None, username: str = Depends(get_current_user)):
    settings = load_user_settings(username)
    default_model = settings.get("model", "")
    chats_dir = get_user_chats_dir(username)
    chats = []
    for p in chats_dir.glob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                c_proj = data.get("project_id", "proj_default")
                if project_id and c_proj != project_id:
                    continue
                chats.append({
                    "id": data.get("id"),
                    "title": data.get("title", "未命名对话"),
                    "project_id": c_proj,
                    "model": data.get("model", default_model),
                    "created_at": data.get("created_at", 0),
                    "updated_at": data.get("updated_at", 0),
                    "message_count": len(data.get("messages", [])),
                    "has_summary": bool(data.get("summary"))
                })
        except Exception:
            pass
    chats.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
    return chats

@app.post("/api/chats")
def create_chat(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    settings = load_user_settings(username)
    chat_id = str(uuid.uuid4())[:8]
    now = time.time()
    proj_id = sanitize_id(payload.get("project_id") or settings.get("active_project_id", "proj_default"))
    chat_model = payload.get("model") or settings.get("model", "")

    # 读取游戏配置，若配置了开场白（opening_statement）与变量，自动注入首条欢迎消息
    proj_file = get_user_projects_dir(username) / f"{proj_id}.json"
    proj_data = {}
    if proj_file.exists():
        try:
            with open(proj_file, "r", encoding="utf-8") as pf:
                proj_data = normalize_project_schema(json.load(pf))
        except Exception:
            pass

    default_inputs = {
        (v.get("key") or v.get("name")): v.get("default", "")
        for v in (proj_data.get("prompt_variables") or [])
        if isinstance(v, dict) and (v.get("key") or v.get("name"))
    }
    raw_in = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else (
        payload.get("variables") if isinstance(payload.get("variables"), dict) else {}
    )
    user_inputs = {**default_inputs, **raw_in}

    init_messages = []
    opening = (proj_data.get("opening_statement") or "").strip()
    if opening and payload.get("include_opening") is True:
        rendered_opening = interpolate_variables(opening, proj_data.get("prompt_variables", []), user_inputs)
        init_messages.append({
            "id": "msg_opening_" + uuid.uuid4().hex[:6],
            "role": "assistant",
            "content": rendered_opening,
            "is_opening": True,
            "suggested_questions": proj_data.get("suggested_questions", []),
            "timestamp": now
        })

    chat_data = {
        "id": chat_id,
        "title": payload.get("title") or f"对话 {time.strftime('%m-%d %H:%M')}",
        "project_id": proj_id,
        "model": chat_model,
        "summary": "",
        "summarized_count": 0,
        "inputs": user_inputs,
        "variables": dict(user_inputs),
        "created_at": now,
        "updated_at": now,
        "messages": init_messages
    }
    file_path = get_user_chats_dir(username) / f"{chat_id}.json"
    atomic_write_json(file_path, chat_data, ensure_ascii=False, indent=2)
    return chat_data

def _estimate_chat_active_context_tokens(data: Dict[str, Any], username: str) -> int:
    try:
        msgs = data.get("messages") or []
        raw_sum = safe_int(data.get("summarized_count", 0), 0)
        sum_cnt = min(raw_sum, max(0, len(msgs) - 2))
        unsummarized = msgs[sum_cnt:]
        proj_id = sanitize_id(data.get("project_id") or "proj_default")
        proj_file = get_user_projects_dir(username) / f"{proj_id}.json"
        base_chars = len(str(data.get("summary") or ""))
        if proj_file.exists():
            try:
                pdoc = json.loads(proj_file.read_text(encoding="utf-8"))
                base_chars += len(str(pdoc.get("system_prompt") or "")) + len(str(pdoc.get("system_protocol_prompt") or ""))
            except Exception:
                pass
        else:
            base_chars += 1600
        hist_chars = 0
        for m in unsummarized:
            if not isinstance(m, dict):
                continue
            txt = strip_thinking_blocks(m.get("content", "")) if m.get("role") == "assistant" else str(m.get("content") or "")
            hist_chars += len(txt)
        return int((base_chars + hist_chars) * 0.65)
    except Exception:
        return 0


@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, username: str = Depends(get_current_user)):
    chat_id = sanitize_id(chat_id)
    file_path = get_user_chats_dir(username) / f"{chat_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="对话不存在")
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "project_id" not in data:
        data["project_id"] = "proj_default"
    if "model" not in data:
        data["model"] = load_user_settings(username).get("model", "")
    if "summary" not in data:
        data["summary"] = ""
    if "inputs" not in data:
        data["inputs"] = data.get("variables", {})
    data["variables"] = data["inputs"]
    bg_task = ACTIVE_BG_TASKS.get(chat_id)
    data["is_generating"] = bool(bg_task and not bg_task.done())
    data["partial_reply"] = ACTIVE_PARTIAL_TEXT.get(chat_id, "") if data["is_generating"] else ""
    if data["is_generating"] and chat_id in ACTIVE_PENDING_REGEN:
        # 重新生成进行中：磁盘仍保留旧回复（失败/停止时可恢复），对外返回截断后的视图以保持前端轮询显示一致
        try:
            _apply_pending_regen(data, ACTIVE_PENDING_REGEN.get(chat_id))
        except Exception:
            pass
    data["context_token_len"] = _estimate_chat_active_context_tokens(data, username)
    return data

@app.post("/api/chats/{chat_id}/stop")
async def stop_chat_generation(chat_id: str, username: str = Depends(get_current_user)):
    chat_id = sanitize_id(chat_id)
    bg_task = ACTIVE_BG_TASKS.pop(chat_id, None)
    if bg_task and not bg_task.done():
        bg_task.cancel()
        try:
            await asyncio.wait({bg_task}, timeout=2.0)
        except Exception:
            pass
    ACTIVE_PARTIAL_TEXT.pop(chat_id, None)
    ACTIVE_PENDING_REGEN.pop(chat_id, None)
    return {"status": "ok"}

@app.put("/api/chats/{chat_id}")
def update_chat(chat_id: str, payload: Dict[str, Any], username: str = Depends(get_current_user)):
    chat_id = sanitize_id(chat_id)
    file_path = get_user_chats_dir(username) / f"{chat_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="对话不存在")
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "title" in payload:
        data["title"] = payload["title"]
    if "project_id" in payload:
        data["project_id"] = sanitize_id(payload["project_id"])
    if "model" in payload:
        data["model"] = payload["model"]
    if "summary" in payload:
        data["summary"] = payload["summary"]
        if not payload["summary"]:
            data["summarized_count"] = 0
    if "inputs" in payload:
        data["inputs"] = payload["inputs"]
        data["variables"] = payload["inputs"]
    if "variables" in payload:
        data["inputs"] = payload["variables"]
        data["variables"] = payload["variables"]
    if "messages" in payload:
        data["messages"] = payload["messages"]
        data["summarized_count"] = min(safe_int(data.get("summarized_count", 0), 0), len(data["messages"]))
    data["updated_at"] = time.time()

    atomic_write_json(file_path, data, ensure_ascii=False, indent=2)
    data["context_token_len"] = _estimate_chat_active_context_tokens(data, username)
    return data

@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str, username: str = Depends(get_current_user)):
    chat_id = sanitize_id(chat_id)
    bg_task = ACTIVE_BG_TASKS.pop(chat_id, None)
    if bg_task and not bg_task.done():
        bg_task.cancel()
        try:
            await asyncio.wait({bg_task}, timeout=2.5)
        except Exception:
            pass
    ACTIVE_PARTIAL_TEXT.pop(chat_id, None)
    ACTIVE_PENDING_REGEN.pop(chat_id, None)
    file_path = get_user_chats_dir(username) / f"{chat_id}.json"
    if file_path.exists():
        file_path.unlink()
    return {"status": "ok"}

# ==================== 单条消息编辑与删除 API ====================
@app.put("/api/chats/{chat_id}/messages/{message_id}")
def edit_message(chat_id: str, message_id: str, payload: Dict[str, Any], username: str = Depends(get_current_user)):
    chat_id = sanitize_id(chat_id)
    file_path = get_user_chats_dir(username) / f"{chat_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="对话不存在")
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    target_msg = None
    for msg in data.get("messages", []):
        if msg.get("id") == message_id:
            target_msg = msg
            break

    if not target_msg:
        raise HTTPException(status_code=404, detail="未找到该消息")

    if "content" in payload:
        target_msg["content"] = payload["content"]
    data["updated_at"] = time.time()

    atomic_write_json(file_path, data, ensure_ascii=False, indent=2)
    return {"status": "ok", "message": target_msg}

@app.delete("/api/chats/{chat_id}/messages/{message_id}")
def delete_message(chat_id: str, message_id: str, username: str = Depends(get_current_user)):
    chat_id = sanitize_id(chat_id)
    file_path = get_user_chats_dir(username) / f"{chat_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="对话不存在")
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    old_messages = data.get("messages", [])
    del_idx = next((i for i, m in enumerate(old_messages) if m.get("id") == message_id), -1)
    if del_idx == -1:
        raise HTTPException(status_code=404, detail="未找到该消息")

    data["messages"] = [m for i, m in enumerate(old_messages) if i != del_idx]
    old_sum = int(data.get("summarized_count", 0))
    if del_idx < old_sum:
        old_sum = max(0, old_sum - 1)
    data["summarized_count"] = min(old_sum, max(0, len(data["messages"]) - 2))
    data["updated_at"] = time.time()
    atomic_write_json(file_path, data, ensure_ascii=False, indent=2)
    return {
        "status": "ok",
        "remaining_count": len(data["messages"]),
        "summarized_count": data["summarized_count"]
    }

# ==================== 智能上下文压缩总结函数 ====================
def _patch_chat_file(
    file_path: Path,
    patch: Dict[str, Any],
    expected_cutoff_idx: Optional[int] = None,
    expected_cutoff_msg_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """重新读取磁盘上最新的对话文件，仅覆盖 patch 中的字段后原子写回（中间无 await，避免并发协程丢失更新）。
    若提供 expected_cutoff_msg_id，则校验磁盘对应位置消息 ID 未发生篡改/回退后再写入总结，防止删除或重生成期间旧总结错位覆盖。"""
    try:
        if not file_path.exists():
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            fresh = json.load(f)
        if not isinstance(fresh, dict):
            return None
        fresh_msgs = fresh.get("messages") or []
        if expected_cutoff_idx is not None and expected_cutoff_msg_id:
            if (
                expected_cutoff_idx < 0
                or expected_cutoff_idx >= len(fresh_msgs)
                or not isinstance(fresh_msgs[expected_cutoff_idx], dict)
                or str(fresh_msgs[expected_cutoff_idx].get("id") or "") != expected_cutoff_msg_id
            ):
                return fresh
        for k, v in patch.items():
            fresh[k] = v
        if "summarized_count" in patch:
            msg_len = len(fresh_msgs)
            fresh["summarized_count"] = max(0, min(safe_int(patch.get("summarized_count"), 0), msg_len))
        atomic_write_json(file_path, fresh, ensure_ascii=False, indent=2)
        return fresh
    except Exception as e:
        print(f"修补对话文件失败 ({file_path.name}): {e}")
        return None

async def generate_summary(existing_summary: str, messages_to_compress: List[Dict[str, Any]], settings: Dict[str, Any], model_override: str = "") -> Optional[str]:
    """调用当前对话的大模型将历史长对话归档为详实的数千字剧情前情与状态档案（不作激进删减）
    返回新生成的总结；失败/无可压缩内容时返回 None（调用方据此决定是否推进 summarized_count，避免静默丢弃历史）"""
    if not messages_to_compress:
        return None

    dialogue_snippets = []
    per_msg_limit = min(2200, max(700, 32000 // max(1, len(messages_to_compress))))
    half_limit = max(300, per_msg_limit // 2)
    for idx_m, m in enumerate(messages_to_compress):
        role_label = "【玩家】" if m.get("role") == "user" else "【主持人】"
        raw_content = m.get("content", "")
        text = strip_thinking_blocks(raw_content) if m.get("role") == "assistant" else raw_content.strip()
        if not text:
            text = raw_content.strip()
        # 完整保留每回合历史 <status> 状态栏信息，严禁因总结或新对话开始而剥离历史状态栏
        if len(text) > per_msg_limit:
            text = text[:half_limit] + "\n……（中段细节省略）……\n" + text[-half_limit:]
        dialogue_snippets.append(f"{role_label}: {text}")

    dialogue_block = "\n\n".join(dialogue_snippets)

    system_instruction = (
        "你是一位专业的互动叙事与跑团长篇档案记录员。\n"
        "任务：请结合【当前已有备忘】与【待合并归档的历史对话】，整理并更新一份详实、连贯、高还原度的【前情提要与世界状态完整档案】。\n"
        "核心铁律（切勿压缩得太狠！必须保留数千字的详实信息！）：\n"
        "1. 篇幅与信息量要求：严禁过度删减或只写几百字简略大纲！请输出 **1500 ~ 3500 字左右（数千字信息量）** 的详实长篇备忘档案，完整保留关键剧情过程、重要动作细节、人物对话神态与伏笔。\n"
        "2. 完整剧情时间线：按时间顺序详述每一幕发生的具体事件、玩家的每一次行动选择与检定结果、冲突细节与剧情转折。\n"
        "3. 角色与关系档案：详细记录所有登场 NPC 的姓名、身份、外貌穿搭、性格动机、好感度/态度变化、关键台词以及与主角的恩怨/约定。\n"
        "4. 主角状态与装备道具全记录：完整保留主角当前的各项数值（生命/理智/剧情进度等）、身体各部位状态与穿戴/伤势/束缚细节、装备栏各槽位与背包全部物品清单。\n"
        "5. 当前局势与待解悬念：清晰记录归档截止时刻所处的具体场景、眼下面临的紧迫局势与下一步悬念，确保后续剧情无缝衔接。\n"
        "直接输出整理后的完整档案正文，无需思考过程或多余客套。"
    )

    user_prompt = f"【当前已有备忘】：\n{existing_summary if existing_summary else '（暂无，首次整理）'}\n\n" \
                  f"【待合并归档的历史对话】：\n{dialogue_block}\n\n" \
                  f"请生成整合更新后的详实长篇【前情提要与世界状态完整档案】（保留数千字完整细节，切勿过度压缩）："

    raw_model = (model_override or "").strip() or settings.get("model", "")
    if not raw_model:
        return None

    ep = resolve_model_endpoint(raw_model, settings)
    if ep["is_local"]:
        local_err = await ensure_local_engine_ready(raw_model)
        ep = resolve_model_endpoint(raw_model, settings)
        if local_err:
            return None

    sum_req_json: Dict[str, Any] = {
        "model": ep["upstream_model"],
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.6,
        "max_tokens": 4096,
        "stream": False
    }
    if ep.get("protocol") not in ("claude", "gemini"):
        sum_req_json["presence_penalty"] = 0.15
    if ep["is_local"]:
        if ep["engine"] == "strata":
            sum_req_json["reasoning_effort"] = "none"
            sum_req_json["reasoning_budget_tokens"] = 0
            sum_req_json["chat_template_kwargs"] = {"enable_thinking": False}
            sum_req_json["repetition_penalty"] = 1.08
            sum_req_json["penalty_last_n"] = 2048
        elif ep["engine"] == "ollama":
            safe_sum_ctx = get_optimal_ollama_num_ctx(
                safe_int(settings.get("max_context_k"), 96),
                ep.get("gguf_path", ""),
            )
            sum_req_json["stop"] = list(_LOCAL_STOP_SEQUENCES)
            sum_req_json["think"] = False
            sum_req_json["reasoning_effort"] = "none"
            sum_req_json["thinking_budget_tokens"] = 0
            sum_req_json["reasoning_budget"] = 0
            sum_req_json["reasoning_budget_tokens"] = 0
            sum_req_json["chat_template_kwargs"] = {"enable_thinking": False}
            sum_req_json["frequency_penalty"] = 0.12
            sum_req_json["options"] = {
                "repeat_penalty": 1.08,
                "repeat_last_n": 2048,
                "num_ctx": safe_sum_ctx,
                "num_predict": 4096
            }
        else:
            sum_req_json["think"] = False
            sum_req_json["reasoning_effort"] = "none"
            sum_req_json["chat_template_kwargs"] = {"enable_thinking": False}

    sum_timeout = 300.0 if ep["is_local"] else 120.0
    proxy_candidates = [ep["proxy"], None] if ep["proxy"] else [None]
    for cur_proxy in proxy_candidates:
        try:
            async with httpx.AsyncClient(proxy=cur_proxy, trust_env=False, timeout=sum_timeout) as client:
                resp = await client.post(
                    f"{ep['base_url']}/chat/completions",
                    headers=ep.get("headers") or {
                        "Authorization": f"Bearer {ep['api_key']}",
                        "Content-Type": "application/json"
                    },
                    json=sum_req_json
                )
                if resp.status_code == 200:
                    res_json = resp.json()
                    summary_content = res_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    summary_content = strip_thinking_blocks(summary_content)
                    if summary_content:
                        return summary_content
        except Exception as e:
            print(f"自动总结生成异常: {e}")
    return None

@app.post("/api/chats/{chat_id}/summarize")
async def trigger_summarize(chat_id: str, payload: Optional[Dict[str, Any]] = None, username: str = Depends(get_current_user)):
    chat_id = sanitize_id(chat_id)
    file_path = get_user_chats_dir(username) / f"{chat_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="对话不存在")
    with open(file_path, "r", encoding="utf-8") as f:
        chat_data = json.load(f)

    messages = chat_data.get("messages", [])
    if len(messages) < 6:
        return {
            "status": "ignored",
            "detail": "消息不足 6 条，无需压缩",
            "summary": chat_data.get("summary", ""),
            "summarized_count": safe_int(chat_data.get("summarized_count", 0), 0)
        }

    settings = load_user_settings(username)
    proj_id = sanitize_id(chat_data.get("project_id") or settings.get("active_project_id", "proj_default"))
    proj_file = get_user_projects_dir(username) / f"{proj_id}.json"
    keep_recent_msgs = max(2, safe_int(settings.get("keep_recent_messages", 10), 10))
    if proj_file.exists():
        try:
            with open(proj_file, "r", encoding="utf-8") as pf:
                raw_proj = json.load(pf)
                if not raw_proj.get("use_global_params", True):
                    cp = raw_proj.get("completion_params") or {}
                    if "keep_recent_messages" in cp:
                        keep_recent_msgs = max(2, safe_int(cp.get("keep_recent_messages"), keep_recent_msgs))
        except Exception:
            pass

    # 温和压缩策略：压缩不要压得太狠，至少保留近期约 6000~8000 字（约 4k~6k Token）且不少于 10 条（5 轮）的完整近期对话，每次最多归档未压缩历史的早期一半；但若单条消息极长导致总字数超过 28000 字（约 18k Token），则优先按字数上限截断
    raw_already = min(safe_int(chat_data.get("summarized_count", 0), 0), max(0, len(messages) - 4))
    unsummarized_len = len(messages) - raw_already
    min_keep_msgs = max(keep_recent_msgs, 10, unsummarized_len // 2)
    token_safe_min_keep = max(2, min(keep_recent_msgs, 6, max(2, unsummarized_len - 2)))

    kept_chars = 0
    keep_from_idx = len(messages)
    for i in range(len(messages) - 1, raw_already - 1, -1):
        m = messages[i]
        m_txt = strip_thinking_blocks(m.get("content", "")) if m.get("role") == "assistant" else m.get("content", "")
        kept_chars += len(m_txt or "")
        keep_from_idx = i
        kept_count = len(messages) - i
        if (kept_count >= min_keep_msgs and kept_chars >= 6500) or (kept_count >= token_safe_min_keep and kept_chars >= 28000):
            break

    cutoff = max(raw_already + 2, min(keep_from_idx, len(messages) - token_safe_min_keep))
    if cutoff >= len(messages) - 2:
        cutoff = max(2, len(messages) - 4)

    if raw_already < cutoff:
        to_compress = messages[raw_already:cutoff]
        base_summary = chat_data.get("summary", "")
    else:
        to_compress = messages[:cutoff]
        base_summary = ""

    cutoff_anchor_idx = cutoff - 1 if 0 < cutoff <= len(messages) else None
    cutoff_anchor_id = (
        str(messages[cutoff_anchor_idx].get("id") or "")
        if cutoff_anchor_idx is not None and isinstance(messages[cutoff_anchor_idx], dict)
        else ""
    )

    # 强制使用当前对话的 AI 模型进行压缩
    req_model = str((payload or {}).get("model") or chat_data.get("model") or settings.get("model") or "").strip()
    new_summary = await generate_summary(base_summary, to_compress, settings, model_override=req_model)
    if not new_summary and to_compress:
        fallback_lines = [base_summary.strip()] if base_summary.strip() else ["**【前情提要与世界状态完整档案】**"]
        for m in to_compress:
            r_tag = "玩家" if m.get("role") == "user" else "剧情"
            c_txt = strip_thinking_blocks(m.get("content", "")) if m.get("role") == "assistant" else m.get("content", "")
            c_txt = re.sub(r"\s+", " ", c_txt).strip()[:500]
            if c_txt:
                fallback_lines.append(f"- 【{r_tag}】{c_txt}")
        new_summary = "\n".join(fallback_lines)

    # 总结期间（可能长达数十秒）用户可能已发送新消息/重生成/删消息：校验锚点消息 ID 未变后仅修补总结字段
    patch: Dict[str, Any] = {"updated_at": time.time()}
    if new_summary:
        patch["summary"] = new_summary
        patch["summarized_count"] = cutoff
    fresh = _patch_chat_file(
        file_path,
        patch,
        expected_cutoff_idx=cutoff_anchor_idx,
        expected_cutoff_msg_id=cutoff_anchor_id or None,
    )
    if fresh is None:
        fresh = chat_data

    return {
        "status": "ok",
        "summary": fresh.get("summary", ""),
        "summarized_count": safe_int(fresh.get("summarized_count", 0), 0)
    }

# ==================== 发送消息与流式响应 ====================
def format_character_cards_block(
    cards: Optional[List[Dict[str, Any]]],
    for_system: bool = True,
    prompt_vars: Optional[List[Dict[str, Any]]] = None,
    chat_inputs: Optional[Dict[str, Any]] = None,
) -> str:
    """格式化角色卡设定块：核心人设/性格/场景/示例对话统一注入 System，并自动将每张卡的 {{char}}/{{user}} 替换为对应角色名与玩家名"""
    if not cards or not isinstance(cards, list):
        return ""
    if not for_system:
        names = [str(c.get("name") or "未命名角色").strip() for c in cards if isinstance(c, dict)]
        return f"【登场角色卡：{'、'.join(names)}】" if names else ""
    pvars = prompt_vars or []
    base_inputs = dict(chat_inputs or {})
    blocks = []
    for idx, c in enumerate(cards, 1):
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "未命名角色").strip()
        card_inputs = {**base_inputs, "char": name}

        def _interp_card_txt(raw_val: Any) -> str:
            s = str(raw_val or "").strip()
            if not s:
                return ""
            return interpolate_variables(s, pvars, card_inputs).strip()

        card_mode = str(c.get("card_mode") or "advanced").strip().lower()
        gender = _interp_card_txt(c.get("gender"))
        age = _interp_card_txt(c.get("age"))
        identity = _interp_card_txt(c.get("identity"))
        custom_fields = c.get("custom_fields") or (c.get("extensions") or {}).get("custom_fields") or []
        fl = c.get("field_labels") or (c.get("extensions") or {}).get("field_labels") or {}
        if not isinstance(fl, dict):
            fl = {}
        description_label = str(fl.get("description") or c.get("description_label") or (c.get("extensions") or {}).get("description_label") or "角色设定与描述 (Description)").strip()
        lbl_tags = str(fl.get("tags") or "标签 (Tags)").strip()
        lbl_pers = str(fl.get("personality") or "性格 (Personality)").strip()
        lbl_scen = str(fl.get("scenario") or "场景 (Scenario)").strip()
        lbl_first_mes = str(fl.get("first_mes") or "角色专属开场白 (First Message)").strip()
        lbl_sys_p = str(fl.get("system_prompt") or "角色系统提示词 (System Prompt)").strip()
        lbl_mes_ex = str(fl.get("mes_example") or "角色台词与行文示例 (Example Dialogue)").strip()
        lbl_post_h = str(fl.get("post_history_instructions") or "历史后指令 (Post-History Instructions)").strip()

        tags = c.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        desc = _interp_card_txt(c.get("description"))
        pers = _interp_card_txt(c.get("personality"))
        scen = _interp_card_txt(c.get("scenario"))
        first_m = _interp_card_txt(c.get("first_mes"))
        mes_ex = _interp_card_txt(c.get("mes_example"))
        sys_p = _interp_card_txt(c.get("system_prompt"))
        post_h = _interp_card_txt(c.get("post_history_instructions"))

        mode_label = "简易角色卡" if card_mode == "simple" else "角色卡"
        lines = [f"=== 绑定{mode_label} #{idx}：{name} ==="]
        if isinstance(custom_fields, list) and len(custom_fields) > 0:
            for cf in custom_fields:
                if not isinstance(cf, dict):
                    continue
                cf_label = str(cf.get("label") or "属性").strip()
                cf_val = _interp_card_txt(cf.get("value"))
                if not cf_val:
                    continue
                if "\n" in cf_val or cf.get("multiline"):
                    lines.append(f"【{cf_label}】：\n{cf_val}")
                else:
                    lines.append(f"【{cf_label}】：{cf_val}")
        else:
            basic_parts = []
            if identity:
                basic_parts.append(f"身份/职业：{identity}")
            if gender:
                basic_parts.append(f"性别/种族：{gender}")
            if age:
                basic_parts.append(f"年龄：{age}")
            if basic_parts:
                lines.append(f"【基本信息】：{' | '.join(basic_parts)}")
        if tags:
            lines.append(f"【{lbl_tags}】：{', '.join(tags)}")
        if desc:
            lines.append(f"【{description_label}】：\n{desc}")
        if pers:
            lines.append(f"【{lbl_pers}】：\n{pers}")
        if scen:
            lines.append(f"【{lbl_scen}】：\n{scen}")
        if first_m:
            lines.append(f"【{lbl_first_mes}】：\n{first_m}")
        if sys_p:
            lines.append(f"【{lbl_sys_p}】：\n{sys_p}")
        if mes_ex:
            lines.append(f"【{lbl_mes_ex}】：\n{mes_ex}")
        if post_h:
            lines.append(f"【{lbl_post_h}】：\n{post_h}")
        lines.append("==============================")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _collect_card_depth_prompts(
    cards: Optional[List[Dict[str, Any]]],
    prompt_vars: Optional[List[Dict[str, Any]]] = None,
    chat_inputs: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """提取所有挂载角色卡的 SillyTavern depth_prompt (按指定 depth 倒数插入对话上下文)"""
    if not cards or not isinstance(cards, list):
        return []
    pvars = prompt_vars or []
    base_inputs = dict(chat_inputs or {})
    out: List[Dict[str, Any]] = []
    for c in cards:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "未命名角色").strip()
        dp = c.get("depth_prompt") or (c.get("extensions") or {}).get("depth_prompt") or {}
        if not isinstance(dp, dict):
            continue
        raw_p = str(dp.get("prompt") or "").strip()
        if not raw_p:
            continue
        card_inputs = {**base_inputs, "char": name}
        rendered_p = interpolate_variables(raw_p, pvars, card_inputs).strip()
        if not rendered_p:
            continue
        fl = c.get("field_labels") or (c.get("extensions") or {}).get("field_labels") or {}
        lbl_dp = str((fl.get("depth_prompt") if isinstance(fl, dict) else None) or "角色深层笔记").strip()
        dp_depth = max(0, safe_int(dp.get("depth"), 4))
        dp_role = str(dp.get("role") or "system").strip().lower()
        if dp_role not in ("system", "user", "assistant"):
            dp_role = "system"
        out.append({
            "role": dp_role,
            "depth": dp_depth,
            "content": f"【{name}·{lbl_dp}】：{rendered_p}",
        })
    return out


def _resolve_avatar_to_data_url(username: str, raw_avatar: str) -> str:
    s = str(raw_avatar or "").strip()
    if not s:
        return ""
    if s.startswith("data:image/"):
        return s
    if s.startswith("/api/gallery/"):
        raw_id = s.rstrip("/").split("/")[-1].split("?")[0]
        clean_id = re.sub(r"[^a-zA-Z0-9_\-]", "", raw_id)
        if clean_id:
            p = get_user_gallery_dir(username) / f"{clean_id}.jpg"
            if p.exists():
                try:
                    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode("ascii")
                except Exception:
                    return ""
    return ""


def _collect_active_character_cards(history_messages: List[Dict[str, Any]], current_cards: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """汇总当前对话中已挂载的所有角色卡（按名称/ID去重，保留最新状态）"""
    by_key: Dict[str, Dict[str, Any]] = {}
    for m in (history_messages or []):
        for c in (m.get("character_cards") or []):
            if isinstance(c, dict):
                k = str(c.get("id") or c.get("name") or "").strip()
                if k:
                    by_key[k] = c
    for c in (current_cards or []):
        if isinstance(c, dict):
            k = str(c.get("id") or c.get("name") or "").strip()
            if k:
                by_key[k] = c
    return list(by_key.values())


def _extract_cards_worldbook_entries(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """提取 V2/V3 角色卡内嵌的 character_book 词条，转换为标准动态世界书规则参与扫描触发"""
    entries_out: List[Dict[str, Any]] = []
    for c_idx, c in enumerate(cards or []):
        if not isinstance(c, dict):
            continue
        cname = str(c.get("name") or "角色卡").strip()
        card_key = re.sub(r"[^a-zA-Z0-9_\-]", "", str(c.get("id") or "")) or f"card{c_idx}"
        cb_entries = c.get("character_book_entries")
        if not isinstance(cb_entries, list):
            raw_cb = c.get("character_book") or (c.get("extensions") or {}).get("character_book")
            cb_entries = _normalize_character_book_entries(raw_cb, cname)
        for e_idx, item in enumerate(cb_entries or []):
            # 标准化后的词条正文存放在 content 字段（兼容旧数据的 value 字段）
            if isinstance(item, dict) and item.get("enabled", True) and (item.get("content") or item.get("value")):
                entry = dict(item)
                raw_eid = str(entry.get("id") if entry.get("id") not in (None, "") else f"cb_{e_idx}")
                # 不同角色卡的 cb_0 / uid 会互相冲突，统一加角色卡 ID 前缀（保证每轮一致，便于已探索记录）
                entry["id"] = raw_eid if raw_eid.startswith(f"{card_key}:") else f"{card_key}:{raw_eid}"
                entries_out.append(entry)
    return entries_out


async def _optimize_images_async(imgs: List[str], **kwargs) -> List[str]:
    """在线程池中批量压缩图片，避免 PIL 解码/重编码阻塞事件循环（手机端轮询/其他请求卡顿）"""
    valid = [img for img in (imgs or []) if img]
    if not valid:
        return []
    return await asyncio.to_thread(lambda: [optimize_image_base64(img, **kwargs) for img in valid])


async def _auto_save_images_to_gallery_async(username: str, imgs: List[str]) -> None:
    """在线程池中将图片批量存入素材图库（含缩略图生成与感知哈希去重）"""
    valid = [img for img in (imgs or []) if img]
    if not valid:
        return
    def _work():
        for img in valid:
            auto_save_to_gallery(username, img)
    try:
        await asyncio.to_thread(_work)
    except Exception as e:
        print(f"图片存入图库异常: {e}")


# 正在进行中的「重新生成」请求：chat_id -> {target_user_msg_id, target_idx, user_msg}
# 截断仅在新回复成功落盘时才写入磁盘；生成期间 GET /api/chats/{id} 按此记录返回截断后的视图，保持前端轮询表现一致
ACTIVE_PENDING_REGEN: Dict[str, Dict[str, Any]] = {}


def _apply_pending_regen(chat_data: Dict[str, Any], pending: Optional[Dict[str, Any]]) -> bool:
    """按消息 ID（回退到原索引）定位目标玩家消息，截断其后的所有消息并替换为编辑后的玩家消息。成功返回 True"""
    if not pending or not isinstance(chat_data, dict):
        return False
    msgs = chat_data.get("messages") or []
    tid = pending.get("target_user_msg_id")
    idx = -1
    if tid:
        for i, m in enumerate(msgs):
            if isinstance(m, dict) and m.get("id") == tid:
                idx = i
                break
    if idx == -1 and not tid:
        t_idx = safe_int(pending.get("target_idx"), -1)
        if 0 <= t_idx < len(msgs) and isinstance(msgs[t_idx], dict) and msgs[t_idx].get("role") == "user":
            idx = t_idx
    if idx == -1:
        return False
    user_msg = pending.get("user_msg") if isinstance(pending.get("user_msg"), dict) else msgs[idx]
    chat_data["messages"] = list(msgs[:idx]) + [user_msg]
    chat_data["summarized_count"] = max(0, min(safe_int(chat_data.get("summarized_count"), 0), len(chat_data["messages"]) - 1))
    return True


class SendMessageRequest(BaseModel):
    chat_id: str
    content: Optional[str] = ""
    image_base64: Optional[str] = None
    images_base64: Optional[List[str]] = None
    character_cards: Optional[List[Dict[str, Any]]] = None
    model: Optional[str] = None
    mode: Optional[str] = "send"
    target_user_msg_id: Optional[str] = None
    user_msg_id: Optional[str] = None
    erotic_level: Optional[int] = None
    violence_level: Optional[int] = None
    erotic_enabled: Optional[bool] = None
    violence_enabled: Optional[bool] = None

@app.post("/api/chat/stream")
async def chat_stream(req: SendMessageRequest, username: str = Depends(get_current_user)):
    req.chat_id = sanitize_id(req.chat_id)
    # 若该对话仍有上一轮未结束的后台生成任务，必须在读取与写入对话文件之前先行取消并等待收尾，杜绝旧流并发覆写新消息
    prev_bg = ACTIVE_BG_TASKS.pop(req.chat_id, None)
    if prev_bg and not prev_bg.done():
        prev_bg.cancel()
        try:
            await asyncio.wait({prev_bg}, timeout=2.0)
        except Exception:
            pass
    ACTIVE_PARTIAL_TEXT.pop(req.chat_id, None)
    ACTIVE_PENDING_REGEN.pop(req.chat_id, None)

    settings = load_user_settings(username)
    chat_file = get_user_chats_dir(username) / f"{req.chat_id}.json"
    if not chat_file.exists():
        default_chat = {
            "id": req.chat_id,
            "project_id": settings.get("active_project_id", "proj_default"),
            "title": f"新对话 ({time.strftime('%m-%d %H:%M')})",
            "created_at": time.time(),
            "updated_at": time.time(),
            "model": req.model or settings.get("model", ""),
            "summary": "",
            "summarized_count": 0,
            "messages": []
        }
        atomic_write_json(chat_file, default_chat, ensure_ascii=False, indent=2)

    with open(chat_file, "r", encoding="utf-8") as f:
        chat_data = json.load(f)

    # 读取所属项目并归一化企业级配置
    project_id = sanitize_id(chat_data.get("project_id") or settings.get("active_project_id", "proj_default"))
    proj_file = get_user_projects_dir(username) / f"{project_id}.json"
    if proj_file.exists():
        with open(proj_file, "r", encoding="utf-8") as f:
            raw_proj = json.load(f)
            project_data = normalize_project_schema(raw_proj, raw_proj, global_defaults=settings)
    elif project_id == "proj_free_chat":
        project_data = normalize_project_schema(DEFAULT_FREE_CHAT_PROJECT, global_defaults=settings)
    else:
        project_data = normalize_project_schema(DEFAULT_PROJECT, global_defaults=settings)

    prompt_vars = project_data.get("prompt_variables") or []
    chat_inputs = {
        "user": username,
        "char": project_data.get("name", "AI"),
        **(chat_data.get("variables") or {}),
        **(chat_data.get("inputs") or {})
    }
    regex_list = project_data.get("regex_replaces") or []
    model = (req.model or chat_data.get("model") or settings.get("model") or "").strip()
    if not model or (not settings.get("base_url") and not settings.get("api_key") and not settings.get("local_base_url")):
        installed_local = get_installed_local_model_ids(settings.get("custom_model_paths") or [])
        custom_model_list = [str(m).strip() for m in (settings.get("custom_models") or []) if str(m).strip()]
        if installed_local and (not model or (model not in installed_local and model not in custom_model_list)):
            model = installed_local[0]
            with _USER_SETTINGS_LOCK:
                latest_s = load_user_settings(username)
                latest_s["model"] = model
                save_user_settings(username, latest_s)
            settings["model"] = model
    if model and chat_data.get("model") != model:
        chat_data["model"] = model
    use_global = bool(project_data.get("use_global_params", True))
    proj_cp = project_data.get("completion_params") if isinstance(project_data.get("completion_params"), dict) else {}
    global_cp = get_default_completion_params(global_defaults=settings)
    base_comp_params = {**proj_cp, **global_cp} if use_global else {**global_cp, **proj_cp}
    per_model_params = (settings.get("model_params") or {}).get(model) or {}
    has_per_model_override = bool(isinstance(per_model_params, dict) and per_model_params)
    if has_per_model_override:
        comp_params = {**base_comp_params, **{k: v for k, v in per_model_params.items() if v is not None and v != ""}}
    else:
        comp_params = base_comp_params

    temp = safe_float(comp_params.get("temperature"), safe_float(settings.get("temperature"), 0.68))
    rep_pen = safe_float(comp_params.get("repetition_penalty"), safe_float(settings.get("repetition_penalty"), 1.08))
    freq_pen = safe_float(comp_params.get("frequency_penalty"), safe_float(settings.get("frequency_penalty"), 0.12))
    pres_pen = safe_float(comp_params.get("presence_penalty"), safe_float(settings.get("presence_penalty"), 0.45))
    top_p = safe_float(comp_params.get("top_p"), safe_float(settings.get("top_p"), 0.90))
    top_k = max(0, safe_int(comp_params.get("top_k"), safe_int(settings.get("top_k"), 40)))
    min_p = safe_float(comp_params.get("min_p"), safe_float(settings.get("min_p"), 0.06))
    max_tok = max(64, safe_int(comp_params.get("max_tokens"), safe_int(settings.get("max_tokens"), 4096)))
    thinking_budget = max(0, safe_int(comp_params.get("thinking_budget"), safe_int(settings.get("thinking_budget"), 1024)))
    wb_scan_depth = max(1, safe_int(comp_params.get("worldbook_scan_depth"), safe_int(settings.get("worldbook_scan_depth"), 5)))

    raw_proj_sys = project_data.get("system_prompt", "").strip()
    if "【万物模块化输出协议" in raw_proj_sys:
        raw_proj_sys = raw_proj_sys.split("【万物模块化输出协议")[0].strip()
    raw_proj_sys = re.sub(r"\{\{\s*(?:UI_MODULES_SPEC|功能栏规范|模块规范)\s*\}\}", "", raw_proj_sys, flags=re.I).strip()
    base_system_prompt = interpolate_variables(raw_proj_sys, prompt_vars, chat_inputs)
    raw_proj_proto = "" if project_data.get("system_protocol_prompt") is None else str(project_data.get("system_protocol_prompt"))
    global_proto = interpolate_variables(
        upgrade_legacy_global_protocol_prompt(raw_proj_proto, allow_empty=True),
        prompt_vars,
        chat_inputs
    )
    proj_for_spec = dict(project_data)
    if req.erotic_level is not None:
        proj_for_spec["erotic_level"] = max(0, min(5, safe_int(req.erotic_level, 3)))
        project_data["erotic_level"] = proj_for_spec["erotic_level"]
    if req.violence_level is not None:
        proj_for_spec["violence_level"] = max(0, min(5, safe_int(req.violence_level, 3)))
        project_data["violence_level"] = proj_for_spec["violence_level"]
    if req.erotic_enabled is not None:
        proj_for_spec["erotic_enabled"] = bool(req.erotic_enabled)
        project_data["erotic_enabled"] = proj_for_spec["erotic_enabled"]
    if req.violence_enabled is not None:
        proj_for_spec["violence_enabled"] = bool(req.violence_enabled)
        project_data["violence_enabled"] = proj_for_spec["violence_enabled"]
    proj_for_spec["system_protocol_prompt"] = global_proto
    status_mod_prompt = interpolate_variables(
        build_status_module_prompt(proj_for_spec, global_proto),
        prompt_vars,
        chat_inputs
    )
    if status_mod_prompt:
        base_system_prompt = f"{base_system_prompt}\n\n{status_mod_prompt.strip()}".strip() if base_system_prompt else status_mod_prompt.strip()
    base_prefix = interpolate_variables(project_data.get("prefix", "").strip(), prompt_vars, chat_inputs)
    raw_base_suffix = re.sub(r"\n*【当前内容尺度控制[\s\S]*$", "", project_data.get("suffix", "")).strip()
    base_suffix = interpolate_variables(raw_base_suffix, prompt_vars, chat_inputs)
    scale_suffix_block = build_content_scale_prompt_block(proj_for_spec).strip()
    if scale_suffix_block:
        base_suffix = f"{base_suffix}\n{scale_suffix_block}".strip() if base_suffix else scale_suffix_block
    context_mode = str(comp_params.get("context_mode") or (settings.get("context_mode", "turns") if use_global else proj_cp.get("context_mode", "turns")))
    if context_mode not in ("turns", "tokens"):
        context_mode = "turns"
    max_turns = max(1, safe_int(comp_params.get("context"), safe_int(settings.get("context", 64) if use_global else project_data.get("max_context_turns", 64), 64)))
    max_context_k = max(4, safe_int(comp_params.get("max_context_k"), safe_int(settings.get("max_context_k", 96) if use_global else proj_cp.get("max_context_k", 96), 96)))
    max_token_budget = max(2048, max_context_k * 1024)
    keep_recent_msgs = max(2, min(safe_int(comp_params.get("keep_recent_messages"), safe_int(settings.get("keep_recent_messages", 6), 6)), 40))
    auto_summarize = bool(comp_params.get("auto_summarize") if "auto_summarize" in comp_params else (settings.get("auto_summarize", True) if use_global else project_data.get("auto_summarize", True)))

    applied_regex_logs: List[str] = []
    pending_regen: Optional[Dict[str, Any]] = None
    turn_raw_images: List[str] = []

    if req.mode == "regenerate":
        messages = chat_data.get("messages", [])
        if not messages:
            raise HTTPException(status_code=400, detail="暂无可重新生成的消息")

        target_idx = -1
        if req.target_user_msg_id:
            for idx, m in enumerate(messages):
                if m.get("id") == req.target_user_msg_id:
                    target_idx = idx
                    break
            if target_idx != -1 and messages[target_idx].get("role") == "assistant":
                found_user_idx = -1
                for i in range(target_idx - 1, -1, -1):
                    if messages[i].get("role") == "user":
                        found_user_idx = i
                        break
                if found_user_idx != -1:
                    target_idx = found_user_idx

        if target_idx == -1:
            for idx in range(len(messages) - 1, -1, -1):
                if messages[idx].get("role") == "user":
                    target_idx = idx
                    break

        if target_idx == -1:
            raise HTTPException(status_code=400, detail="未找到对应发言")

        chat_data["messages"] = messages[:target_idx + 1]
        chat_data["summarized_count"] = min(int(chat_data.get("summarized_count", 0)), len(chat_data["messages"]) - 1)
        target_user_msg = chat_data["messages"][target_idx]

        if req.content is not None and req.content.strip():
            raw_clean_req = strip_legacy_start_game_hint(req.content.strip())
            cleaned_u, rx_u = apply_regex_scripts(raw_clean_req, regex_list, target_scope=2, only_persistent=True)
            applied_regex_logs.extend(rx_u)
            target_user_msg["content"] = cleaned_u
        elif target_user_msg.get("content"):
            target_user_msg["content"] = strip_legacy_start_game_hint(target_user_msg.get("content", ""))

        # 仅当明确传入非空图片数组时才更新图片，防止重新生成/编辑重生成时默认空数组 [] 清空原有图片
        if req.images_base64 and len(req.images_base64) > 0:
            optimized_req_imgs = await _optimize_images_async([img for img in req.images_base64 if img])
            target_user_msg["images"] = optimized_req_imgs
            target_user_msg["image"] = optimized_req_imgs[0] if optimized_req_imgs else None
            await _auto_save_images_to_gallery_async(username, optimized_req_imgs)

        if req.character_cards and len(req.character_cards) > 0:
            target_user_msg["character_cards"] = req.character_cards

        chat_data["updated_at"] = time.time()
        # 重新生成：不再提前把截断结果写盘（否则生成失败/被停止时旧回复会被永久删除）。
        # 截断 + 编辑后的玩家消息改为在新回复成功落盘时，按消息 ID 定位后一次性原子写入。
        pending_regen = {
            "target_user_msg_id": target_user_msg.get("id"),
            "target_idx": target_idx,
            "user_msg": target_user_msg,
        }

        user_display_text = strip_legacy_start_game_hint(target_user_msg.get("content", "").strip())
        raw_imgs = target_user_msg.get("images") or ([target_user_msg.get("image")] if target_user_msg.get("image") else [])
        turn_raw_images = [img for img in raw_imgs if img]
        input_images = await _optimize_images_async(turn_raw_images)
        input_char_cards = target_user_msg.get("character_cards") or []
        history_messages = chat_data["messages"][:-1]
    else:
        raw_input_images = []
        if req.images_base64:
            raw_input_images.extend([img for img in req.images_base64 if img])
        elif req.image_base64:
            raw_input_images.append(req.image_base64)

        turn_raw_images = [img for img in raw_input_images if img]
        input_images = await _optimize_images_async(turn_raw_images)
        await _auto_save_images_to_gallery_async(username, input_images)

        input_char_cards = req.character_cards or []

        raw_user_text = strip_legacy_start_game_hint(req.content.strip() if req.content else "")
        if not raw_user_text and input_char_cards:
            card_names = "、".join([str(c.get("name") or "未命名角色") for c in input_char_cards if isinstance(c, dict)])
            raw_user_text = f"【附带角色卡：{card_names}】"
        user_display_text, rx_u = apply_regex_scripts(raw_user_text, regex_list, target_scope=2, only_persistent=True)
        applied_regex_logs.extend(rx_u)

        user_msg_record = {
            "id": req.user_msg_id or str(uuid.uuid4())[:8],
            "role": "user",
            "content": user_display_text,
            "images": input_images,
            "image": input_images[0] if input_images else None,
            "character_cards": input_char_cards,
            "timestamp": time.time()
        }
        # 图片压缩/入图库在线程中执行期间可能有其它请求写入了该对话：重新读取最新文件再追加，避免覆盖
        try:
            with open(chat_file, "r", encoding="utf-8") as f:
                fresh_chat = json.load(f)
            if isinstance(fresh_chat, dict):
                if model and fresh_chat.get("model") != model:
                    fresh_chat["model"] = model
                chat_data = fresh_chat
        except Exception:
            pass
        chat_data.setdefault("messages", []).append(user_msg_record)
        chat_data["updated_at"] = time.time()
        atomic_write_json(chat_file, chat_data, ensure_ascii=False, indent=2)

        history_messages = chat_data["messages"][:-1]

    # 汇总当前对话中挂载的所有角色卡，将核心人设注入 System，并将角色卡内嵌世界书 (character_book) 合并入世界书引擎
    all_active_cards = _collect_active_character_cards(history_messages, input_char_cards)
    active_cards_system_block = format_character_cards_block(
        all_active_cards,
        for_system=True,
        prompt_vars=prompt_vars,
        chat_inputs=chat_inputs,
    )
    active_card_depth_prompts = _collect_card_depth_prompts(
        all_active_cards,
        prompt_vars=prompt_vars,
        chat_inputs=chat_inputs,
    )
    card_wb_entries = _extract_cards_worldbook_entries(all_active_cards)
    if card_wb_entries:
        merged_proj_data = dict(project_data)
        merged_proj_data["world_book"] = list(project_data.get("world_book") or []) + card_wb_entries
    else:
        merged_proj_data = project_data

    current_cards_tag = format_character_cards_block(input_char_cards, for_system=False)
    combined_scan_text = f"{user_display_text}\n{current_cards_tag}".strip() if current_cards_tag else user_display_text

    visited_wb_ids: List[str] = [str(x) for x in (chat_data.get("visited_wb_ids") or []) if x]

    # 动态世界书匹配与注入引擎 (扫描 depth 轮历史与触发区域，按 sort 排序注入提示词/前置词/后置词)
    final_system_prompt, final_prefix, final_suffix, triggered_wb_logs = evaluate_world_book(
        project_data=merged_proj_data,
        history_messages=history_messages,
        current_user_text=combined_scan_text,
        system_prompt=base_system_prompt,
        prefix=base_prefix,
        suffix=base_suffix,
        chat_inputs=chat_inputs,
        visited_wb_ids=visited_wb_ids,
        default_scan_depth=wb_scan_depth,
    )
    if visited_wb_ids != chat_data.get("visited_wb_ids"):
        chat_data["visited_wb_ids"] = visited_wb_ids
        try:
            _patch_chat_file(chat_file, {"visited_wb_ids": list(visited_wb_ids)})
        except Exception:
            pass

    # 提示词组装：拼接玩家输入与游戏设定中的前置词(prefix)、后置词(suffix)；若启用了状态栏模块但后置词未包含全部栏位锚点，自动同步尾部状态栏清单以防多轮长对话遗忘
    user_final_text = user_display_text
    if current_cards_tag and current_cards_tag not in user_final_text:
        user_final_text = f"{current_cards_tag}\n{user_final_text}".strip()
    if final_prefix:
        user_final_text = f"{final_prefix}\n{user_final_text}".strip()
    if final_suffix:
        user_final_text = f"{user_final_text}\n{final_suffix}".strip()
    if (project_data.get("status_panel_enabled", True) is not False) and not is_free_chat_project(project_data):
        _turn_mods = normalize_ui_modules(project_data.get("ui_modules"))
        _turn_st_keys = [
            str(m.get("key") or "").strip()
            for m in _turn_mods
            if isinstance(m, dict)
            and m.get("enabled", True) is not False
            and str(m.get("id") or "") != "mod_scale"
            and str(m.get("type") or "progress_stats") in STATUS_SUBMODULE_TYPES
            and str(m.get("key") or "").strip()
        ]
        if _turn_st_keys and ("<status>" not in user_final_text.lower() or any(f"[{k}]" not in user_final_text for k in _turn_st_keys)):
            _tags_str = "、".join([f"[{k}]" for k in _turn_st_keys])
            _has_choices_mod = any(
                isinstance(m, dict) and m.get("enabled", True) is not False and (m.get("type") == "action_choices" or m.get("id") == "mod_choices")
                for m in _turn_mods
            )
            _choice_tail = "，并在 `</status>` 闭合标签之后输出唯一一次“你打算怎么做？”及 `1.`~`4.` 行动选项（输出完第 4 项即刻停止，严禁自问自答或重复输出）" if _has_choices_mod else "（输出完 `</status>` 即刻停止，严禁重复输出）"
            _long_ctx_ref = ""
            if not history_messages:
                _sample_hdrs = "\n".join([f"[{k}]" for k in _turn_st_keys])
                _long_ctx_ref = f"（严格使用 `<status>\\n{_sample_hdrs}\\n...</status>` 包裹）"
            elif len(history_messages) >= 8:
                _last_asst_has_st = bool(
                    history_messages
                    and history_messages[-1].get("role") == "assistant"
                    and "<status>" in str(history_messages[-1].get("content") or "").lower()
                )
                if not _last_asst_has_st:
                    for _hm_prev in reversed(history_messages):
                        if isinstance(_hm_prev, dict) and _hm_prev.get("role") == "assistant":
                            _prev_sp = split_ai_message_modules(str(_hm_prev.get("content") or ""), _turn_st_keys)
                            if _prev_sp.get("status"):
                                _compact_st = _prev_sp["status"][:900]
                                _long_ctx_ref = f"\n【近期状态栏快照（请在此基础上结合本轮最新剧情继承并更新，切勿遗漏 `<status>...</status>` 标签）】：\n{_compact_st}"
                                break
            user_final_text = (
                f"{user_final_text}\n"
                f"【本轮状态栏同步硬性要求：剧情正文结束后必须紧跟输出唯一一个包含 {_tags_str} 的 `<status>...</status>` 状态块{_choice_tail}，所有栏位缺一不可；必须在上一轮状态栏基础上继承并更新，严禁遗漏状态栏或删去历史已结识角色与物品。】"
                f"{_long_ctx_ref}"
            ).strip()

    def _est_msg_tokens(txt: str) -> int:
        return max(1, int(len(txt or "") * 0.65))

    # 统一双触发自动压缩机制：无论是“按轮数”还是“按Token”模式，
    # 只要【未压缩历史超过轮数上限】或【当前上下文总Token超过预算水位线(88%)】，均自动触发前情提要压缩
    already_summarized = min(int(chat_data.get("summarized_count", 0)), max(0, len(history_messages) - 2))
    fixed_tok = (
        _est_msg_tokens(final_system_prompt)
        + _est_msg_tokens(active_cards_system_block)
        + _est_msg_tokens(chat_data.get("summary", ""))
        + _est_msg_tokens(user_final_text)
    )
    avail_hist_tok = max(1000, max_token_budget - fixed_tok)
    token_high_water = max(2048, int(max_token_budget * 0.88))
    compress_target_hist_tok = max(6000, int(max_token_budget * 0.68) - fixed_tok)
    max_history_count = max(4, max_turns * 2)
    min_auto_keep_msgs = max(keep_recent_msgs, 10, int(max_history_count * 0.65))
    min_token_keep_msgs = max(2, min(keep_recent_msgs, max(2, len(history_messages) - already_summarized - 2)))

    unsummarized_history_pre = history_messages[already_summarized:]
    unsummarized_hist_tok = 0
    for hm in unsummarized_history_pre:
        hm_txt = strip_thinking_blocks(hm.get("content", "")) if hm.get("role") == "assistant" else hm.get("content", "")
        unsummarized_hist_tok += _est_msg_tokens(hm_txt)

    exceeds_turns = (context_mode != "tokens") and (len(unsummarized_history_pre) > max_history_count)
    exceeds_tokens = (fixed_tok + unsummarized_hist_tok) > token_high_water

    if auto_summarize and (exceeds_turns or exceeds_tokens):
        turn_overflow = 0
        if exceeds_turns:
            turn_overflow = max(already_summarized, len(history_messages) - min_auto_keep_msgs)

        token_overflow = 0
        if exceeds_tokens:
            acc_tok = 0
            cutoff_idx = len(history_messages)
            for i in range(len(history_messages) - 1, already_summarized - 1, -1):
                hm = history_messages[i]
                hm_txt = strip_thinking_blocks(hm.get("content", "")) if hm.get("role") == "assistant" else hm.get("content", "")
                m_tok = _est_msg_tokens(hm_txt)
                if acc_tok + m_tok > compress_target_hist_tok and (len(history_messages) - i) >= min_token_keep_msgs:
                    break
                acc_tok += m_tok
                cutoff_idx = i
            token_overflow = max(already_summarized, min(cutoff_idx, len(history_messages) - min_token_keep_msgs))

        overflow_count = max(already_summarized, max(turn_overflow, token_overflow))
        if overflow_count - already_summarized >= 2:
            to_compress = history_messages[already_summarized:overflow_count]
            auto_anchor_idx = overflow_count - 1 if 0 < overflow_count <= len(history_messages) else None
            auto_anchor_id = (
                str(history_messages[auto_anchor_idx].get("id") or "")
                if auto_anchor_idx is not None and isinstance(history_messages[auto_anchor_idx], dict)
                else ""
            )
            try:
                updated_summary = await generate_summary(
                    chat_data.get("summary", ""),
                    to_compress,
                    settings,
                    model_override=str(model or req.model or chat_data.get("model") or "")
                )
                if updated_summary:
                    chat_data["summary"] = updated_summary
                    chat_data["summarized_count"] = overflow_count
                    # 总结 await 期间文件可能已被其它请求修改：校验锚点消息 ID 未变后仅修补总结字段
                    _patch_chat_file(
                        chat_file,
                        {
                            "summary": updated_summary,
                            "summarized_count": overflow_count,
                            "updated_at": time.time(),
                        },
                        expected_cutoff_idx=auto_anchor_idx,
                        expected_cutoff_msg_id=auto_anchor_id or None,
                    )
            except Exception as e:
                print(f"自动总结执行跳过: {e}")

    already_summarized_idx = min(safe_int(chat_data.get("summarized_count", 0), 0), max(0, len(history_messages) - 2))
    unsummarized_history = history_messages[already_summarized_idx:]
    if context_mode != "tokens" and len(unsummarized_history) > max_history_count:
        unsummarized_history = unsummarized_history[-max_history_count:]

    selected_rev = []
    acc_tok = 0
    for m in reversed(unsummarized_history):
        m_txt = strip_thinking_blocks(m.get("content", "")) if m.get("role") == "assistant" else m.get("content", "")
        m_tok = _est_msg_tokens(m_txt)
        if acc_tok + m_tok > avail_hist_tok and len(selected_rev) >= keep_recent_msgs:
            break
        acc_tok += m_tok
        selected_rev.append(m)
    active_history = list(reversed(selected_rev))

    api_messages = []
    system_sections: List[str] = []
    if final_system_prompt:
        system_sections.append(final_system_prompt)
    if active_cards_system_block:
        system_sections.append(active_cards_system_block)

    # 注入记忆宫殿 (Memory Palace) 长期固定记忆槽
    mem_palace = [m for m in (project_data.get("memory_palace") or []) if isinstance(m, dict) and m.get("content") and m.get("pinned", True)]
    if mem_palace:
        mp_lines = [
            f"• 【{m.get('title') or m.get('key') or '核心记忆'}】：{interpolate_variables(str(m.get('content') or ''), prompt_vars, chat_inputs)}"
            for m in mem_palace
        ]
        system_sections.append("【记忆宫殿（长期核心设定与契约）】\n" + "\n".join(mp_lines))

    current_summary = chat_data.get("summary", "").strip()
    if current_summary:
        summary_system_block = (
            f"【历史前情回顾与世界状态备忘】\n"
            f"以下是更早之前已经发生的重要事件、人物关系与当前状态，请在此连贯背景下继续推进冒险：\n"
            f"{current_summary}"
        )
        system_sections.append(summary_system_block)

    if system_sections:
        api_messages.append({"role": "system", "content": "\n\n".join(system_sections)})

    # 视觉 Token 节省策略：AI 仅接收【本轮】与【上一轮（active_history 中最后一条 user 消息）】的图片，
    # 更早之前的历史轮次一律只发纯文本、不再重复发送 base64 图片或旧角色卡立绘
    effective_turn_user_images: List[str] = list(input_images) if input_images else []
    turn_image_set = set(effective_turn_user_images) | set(turn_raw_images or [])

    last_prev_user_idx = -1
    for idx_h in range(len(active_history) - 1, -1, -1):
        if active_history[idx_h].get("role", "user") == "user":
            last_prev_user_idx = idx_h
            break

    sent_card_avatar_names = set()
    for idx_h, h in enumerate(active_history):
        role = h.get("role", "user")
        if role == "user":
            h_text = strip_legacy_start_game_hint(h.get("content", ""))
            h_cards = h.get("character_cards") or []
            h_cards_tag = format_character_cards_block(h_cards, for_system=False)
            if h_cards_tag and h_cards_tag not in h_text:
                h_text = f"{h_cards_tag}\n{h_text}".strip()

            is_immediately_prev_turn = (idx_h == last_prev_user_idx)
            h_imgs: List[str] = []
            if is_immediately_prev_turn:
                raw_h_imgs = [x for x in (h.get("images") or ([h.get("image")] if h.get("image") else [])) if x]
                h_imgs = [img for img in raw_h_imgs if img not in turn_image_set]
                for hc in h_cards:
                    if not isinstance(hc, dict):
                        continue
                    hc_name = str(hc.get("name") or "未命名角色").strip()
                    hc_avatar = _resolve_avatar_to_data_url(username, str(hc.get("avatar") or ""))
                    if hc_avatar and hc_name not in sent_card_avatar_names:
                        sent_card_avatar_names.add(hc_name)
                        h_imgs.extend(await _optimize_images_async([hc_avatar], max_dim=768, quality=75, min_bytes=35_000))

            if h_imgs:
                content_parts = []
                for opt_img in await _optimize_images_async(h_imgs, max_dim=896, quality=76, min_bytes=70_000):
                    content_parts.append({"type": "image_url", "image_url": {"url": opt_img}})
                content_parts.append({"type": "text", "text": h_text})
                api_messages.append({"role": "user", "content": content_parts})
            else:
                api_messages.append({"role": "user", "content": h_text})
        elif role == "assistant":
            raw_asst = h.get("content", "")
            clean_asst = strip_thinking_blocks(raw_asst)
            api_messages.append({"role": "assistant", "content": clean_asst or raw_asst})

    turn_images = list(effective_turn_user_images)
    for c in (input_char_cards or []):
        if not isinstance(c, dict):
            continue
        c_name = str(c.get("name") or "未命名角色").strip()
        c_avatar = _resolve_avatar_to_data_url(username, str(c.get("avatar") or ""))
        if c_avatar and c_name not in sent_card_avatar_names:
            sent_card_avatar_names.add(c_name)
            turn_images.extend(await _optimize_images_async([c_avatar], max_dim=768, quality=75, min_bytes=35_000))

    if turn_images:
        content_parts = []
        for opt_img in await _optimize_images_async(turn_images, max_dim=896, quality=76, min_bytes=70_000):
            content_parts.append({"type": "image_url", "image_url": {"url": opt_img}})
        content_parts.append({"type": "text", "text": user_final_text})
        api_messages.append({"role": "user", "content": content_parts})
    else:
        api_messages.append({"role": "user", "content": user_final_text})

    # 按 SillyTavern depth_prompt 规范，将各活跃角色卡的深层笔记按倒数第 depth 条消息位置注入对话上下文
    if active_card_depth_prompts:
        min_dp_idx = 1 if (api_messages and api_messages[0].get("role") == "system") else 0
        # 相同 depth 保持角色卡顺序；不同 depth 从大到小插入以避免改变末尾消息相对偏移
        for dp_item in sorted(active_card_depth_prompts, key=lambda x: int(x.get("depth", 4)), reverse=True):
            dp_d = max(0, int(dp_item.get("depth", 4)))
            ins_idx = max(min_dp_idx, len(api_messages) - dp_d)
            api_messages.insert(ins_idx, {"role": dp_item["role"], "content": dp_item["content"]})

    model = (req.model or chat_data.get("model") or settings.get("model") or "").strip()
    ui_mods_norm = normalize_ui_modules(project_data.get("ui_modules"))
    think_mod_obj = next(
        (m for m in ui_mods_norm if m.get("type") == "thinking_fold" or m.get("id") == "mod_think"),
        None
    )
    think_mod_enabled = bool(think_mod_obj and think_mod_obj.get("enabled", True) is not False)

    # 记录完整组装的 Prompt 日志以便用户在【提示词日志】中审计
    prompt_log_snapshot = {
        "timestamp": time.time(),
        "model": model,
        "estimated_context_tokens": fixed_tok + acc_tok,
        "variables": chat_inputs,
        "completion_params": {
            "model_independent_params": has_per_model_override,
            "use_global_params": use_global,
            "temperature": temp,
            "repetition_penalty": rep_pen,
            "frequency_penalty": freq_pen,
            "presence_penalty": pres_pen,
            "top_p": top_p,
            "top_k": top_k,
            "min_p": min_p,
            "max_tokens": max_tok,
            "context_mode": context_mode,
            "context_turns": max_turns,
            "max_context_k": max_context_k,
            "keep_recent_messages": keep_recent_msgs,
            "worldbook_scan_depth": wb_scan_depth,
            "thinking_budget": thinking_budget if think_mod_enabled else 0
        },
        "triggered_worldbooks": triggered_wb_logs,
        "triggered_worldbook": triggered_wb_logs,
        "applied_regex": applied_regex_logs,
        "assembled_messages": [
            {
                "role": m["role"],
                "content": m["content"] if isinstance(m["content"], str) else f"[多模态消息: 含文本与 {len(m['content'])-1} 张图片]"
            }
            for m in api_messages
        ]
    }

    old_task = ACTIVE_BG_TASKS.pop(req.chat_id, None)
    if old_task and not old_task.done():
        old_task.cancel()
    ACTIVE_PARTIAL_TEXT[req.chat_id] = ""
    if pending_regen:
        ACTIVE_PENDING_REGEN[req.chat_id] = pending_regen
    else:
        ACTIVE_PENDING_REGEN.pop(req.chat_id, None)

    event_queue: asyncio.Queue = asyncio.Queue()

    async def _run_upstream_generation():
        if not model:
            await event_queue.put({"error": "尚未选择可用模型：请点击左下角「下载」一键获取本地模型，或在「模型」中配置在线 API"})
            await event_queue.put(None)
            ACTIVE_BG_TASKS.pop(req.chat_id, None)
            ACTIVE_PARTIAL_TEXT.pop(req.chat_id, None)
            ACTIVE_PENDING_REGEN.pop(req.chat_id, None)
            return

        collected_chunks: List[str] = []
        model_candidates = [model]
        last_err_str: Optional[str] = None
        is_trpg_stream = (project_data.get("status_panel_enabled", True) is not False) and not is_free_chat_project(project_data)
        stream_choices_enabled = any(
            isinstance(m, dict) and m.get("enabled", True) is not False and (str(m.get("type") or "") == "action_choices" or str(m.get("id") or "") == "mod_choices")
            for m in ui_mods_norm
        )

        try:
            for cur_model in model_candidates:
                if collected_chunks:
                    break
                ep = resolve_model_endpoint(cur_model, settings)
                if ep["is_local"]:
                    local_err = await ensure_local_engine_ready(
                        cur_model,
                        status_callback=lambda msg: event_queue.put({"status": msg})
                    )
                    ep = resolve_model_endpoint(cur_model, settings)
                    if local_err:
                        last_err_str = local_err
                        continue

                cur_base_url = ep["base_url"]
                cur_api_key = ep["api_key"]
                cur_upstream_model = ep["upstream_model"]
                has_multimodal_msgs = any(isinstance(m.get("content"), list) for m in api_messages)
                cur_vision_enabled = bool(ep["supports_vision"])
                cur_messages = sanitize_messages_for_model(api_messages, cur_vision_enabled)
                proxy_candidates = [ep["proxy"], None] if ep["proxy"] else [None]
                net_retry_used = False
                vision_fallback_used = False

                attempt_idx = 0
                while attempt_idx < len(proxy_candidates):
                    cur_proxy = proxy_candidates[attempt_idx]
                    attempt_idx += 1
                    try:
                        client_Timeout = httpx.Timeout(600.0 if ep["is_local"] else 300.0, connect=30.0)
                        eff_max_tok = max_tok
                        eff_rep_pen = rep_pen
                        eff_freq_pen = freq_pen
                        eff_pres_pen = pres_pen
                        if ep["is_local"] and not has_per_model_override:
                            # 自动升级旧版遗留配置，并为 Flash-Next (Strata) 与 27B (Ollama/llama-server) 匹配各自双盲验证的最优采样甜点
                            if eff_max_tok == 12288:
                                eff_max_tok = 4096
                            is_default_or_legacy = (
                                (eff_rep_pen >= 1.08 and eff_pres_pen >= 0.40)
                                or (eff_rep_pen <= 1.02 and eff_freq_pen == 0.0 and eff_pres_pen == 0.0)
                                or (abs(eff_rep_pen - 1.05) < 1e-6 and abs(eff_pres_pen - 0.20) < 1e-6 and abs(eff_freq_pen - 0.05) < 1e-6)
                            )
                            if is_default_or_legacy:
                                if ep.get("engine") == "ollama":
                                    eff_rep_pen = 1.03
                                    eff_freq_pen = 0.0
                                    eff_pres_pen = 0.10
                                else:
                                    eff_rep_pen = 1.05
                                    eff_freq_pen = 0.05
                                    eff_pres_pen = 0.20

                        req_body: Dict[str, Any] = {
                            "model": cur_upstream_model,
                            "messages": cur_messages,
                            "temperature": temp,
                            "top_p": top_p,
                            "stream": True
                        }
                        if eff_max_tok > 0:
                            req_body["max_tokens"] = eff_max_tok
                        if ep.get("protocol") not in ("claude", "gemini"):
                            if ep["is_local"] or eff_pres_pen != 0:
                                req_body["presence_penalty"] = eff_pres_pen
                            if ep["is_local"] or eff_freq_pen != 0:
                                req_body["frequency_penalty"] = eff_freq_pen
                        if ep["is_local"]:
                            req_body["stop"] = list(_LOCAL_STOP_SEQUENCES)
                            safe_think_budget = (
                                max(1024, min(thinking_budget, 4096))
                                if (think_mod_enabled and thinking_budget > 0)
                                else 0
                            )
                            if ep["engine"] == "strata":
                                if think_mod_enabled and safe_think_budget > 0:
                                    req_body["reasoning_effort"] = "medium"
                                    req_body["reasoning_budget_tokens"] = safe_think_budget
                                else:
                                    req_body["reasoning_effort"] = "none"
                                    req_body["reasoning_budget_tokens"] = 0
                                    req_body["chat_template_kwargs"] = {"enable_thinking": False}
                                req_body["repetition_penalty"] = eff_rep_pen
                                req_body["penalty_last_n"] = 1024
                                req_body["top_k"] = top_k
                                req_body["min_p"] = min_p
                            elif ep["engine"] == "ollama":
                                if think_mod_enabled and safe_think_budget > 0:
                                    capped_local_think = min(safe_think_budget, 1024)
                                    req_body["thinking_budget_tokens"] = capped_local_think
                                    req_body["reasoning_budget"] = capped_local_think
                                    req_body["reasoning_budget_tokens"] = capped_local_think
                                    ollama_total_predict = (eff_max_tok if eff_max_tok > 0 else 4096) + capped_local_think
                                    req_body["max_tokens"] = ollama_total_predict
                                else:
                                    req_body["think"] = False
                                    req_body["reasoning_effort"] = "none"
                                    req_body["thinking_budget_tokens"] = 0
                                    req_body["reasoning_budget"] = 0
                                    req_body["reasoning_budget_tokens"] = 0
                                    req_body["chat_template_kwargs"] = {"enable_thinking": False}
                                    ollama_total_predict = eff_max_tok if eff_max_tok > 0 else 4096
                                safe_num_ctx = get_optimal_ollama_num_ctx(
                                    max_context_k if max_context_k else 96,
                                    ep.get("gguf_path", ""),
                                )
                                req_body["repeat_penalty"] = eff_rep_pen
                                req_body["repeat_last_n"] = 1024
                                req_body["top_k"] = top_k
                                req_body["min_p"] = min_p
                                req_body["options"] = {
                                    "repeat_penalty": eff_rep_pen,
                                    "repeat_last_n": 1024,
                                    "top_k": top_k,
                                    "min_p": min_p,
                                    "presence_penalty": eff_pres_pen,
                                    "frequency_penalty": eff_freq_pen,
                                    "num_ctx": safe_num_ctx,
                                    "num_predict": ollama_total_predict
                                }
                            else:
                                if not think_mod_enabled or safe_think_budget <= 0:
                                    req_body["think"] = False
                                    req_body["reasoning_effort"] = "none"
                                    req_body["chat_template_kwargs"] = {"enable_thinking": False}

                        async with httpx.AsyncClient(proxy=cur_proxy, trust_env=False, timeout=client_Timeout) as client:
                            async with client.stream(
                                "POST",
                                f"{cur_base_url}/chat/completions",
                                headers=ep.get("headers") or {
                                    "Authorization": f"Bearer {cur_api_key}",
                                    "Content-Type": "application/json"
                                },
                                json=req_body
                            ) as response:
                                if response.status_code != 200:
                                    err_bytes = await response.aread()
                                    err_msg = err_bytes.decode("utf-8", errors="ignore")
                                    # 若中转站/纯文本模型拒绝 image_url 块 (HTTP 400/422)，自动退化为纯文本消息重试一次
                                    if (
                                        response.status_code in (400, 422)
                                        and not collected_chunks
                                        and cur_vision_enabled
                                        and has_multimodal_msgs
                                        and not vision_fallback_used
                                    ):
                                        vision_fallback_used = True
                                        cur_vision_enabled = False
                                        cur_messages = sanitize_messages_for_model(api_messages, False)
                                        proxy_candidates.insert(attempt_idx, cur_proxy)
                                        await event_queue.put({"status": "当前模型不支持图片输入，已自动转为纯文本模式..."})
                                        continue
                                    last_err_str = f"API Error {response.status_code}: {err_msg}"
                                    if response.status_code in (500, 502, 503, 504) and len(model_candidates) > 1:
                                        break
                                    await event_queue.put({"error": last_err_str})
                                    return

                                resp_ctype = (response.headers.get("content-type") or "").lower()
                                if "text/event-stream" not in resp_ctype and "application/json" in resp_ctype:
                                    raw_json_bytes = await response.aread()
                                    try:
                                        non_sse_json = json.loads(raw_json_bytes.decode("utf-8", errors="ignore"))
                                    except Exception:
                                        non_sse_json = {}
                                    if isinstance(non_sse_json, dict) and non_sse_json.get("error") and not non_sse_json.get("choices"):
                                        err_obj = non_sse_json.get("error")
                                        err_detail = err_obj.get("message") if isinstance(err_obj, dict) else str(err_obj)
                                        last_err_str = f"API Error: {err_detail}"
                                        await event_queue.put({"error": last_err_str})
                                        return
                                    msg_obj = ((non_sse_json.get("choices") or [{}])[0].get("message") or {}) if isinstance(non_sse_json, dict) else {}
                                    non_sse_r = str(msg_obj.get("reasoning_content") or msg_obj.get("reasoning") or "")
                                    non_sse_c = str(msg_obj.get("content") or "")
                                    merged_non_sse = (f"<think>\n{non_sse_r}\n</think>\n\n{non_sse_c}" if (non_sse_r and think_mod_enabled) else non_sse_c)
                                    if not think_mod_enabled:
                                        merged_non_sse = strip_thinking_blocks(merged_non_sse)
                                    if merged_non_sse:
                                        collected_chunks.append(merged_non_sse)
                                        ACTIVE_PARTIAL_TEXT[req.chat_id] = merged_non_sse
                                        await event_queue.put({"chunk": merged_non_sse})
                                    break

                                in_reasoning_block = False
                                suppressed_think_buf = ""
                                suppressed_reasoning_pieces: List[str] = []
                                suppressing_inline_think = False
                                sent_wait_status = False
                                last_loop_chk_len = 0

                                async for line in response.aiter_lines():
                                    line = line.strip()
                                    if not line:
                                        continue
                                    if line.startswith("data:"):
                                        raw_data = line[5:].lstrip()
                                        if raw_data == "[DONE]":
                                            break
                                        try:
                                            chunk_json = json.loads(raw_data)
                                            if isinstance(chunk_json, dict) and chunk_json.get("error") and not chunk_json.get("choices"):
                                                err_obj = chunk_json.get("error")
                                                err_detail = err_obj.get("message") if isinstance(err_obj, dict) else str(err_obj)
                                                last_err_str = f"API Stream Error: {err_detail}"
                                                break
                                            choices_arr = chunk_json.get("choices") or []
                                            choice0 = choices_arr[0] if choices_arr and isinstance(choices_arr[0], dict) else {}
                                            delta = choice0.get("delta") or choice0.get("message") or {}
                                            reasoning_piece = delta.get("reasoning_content") or delta.get("reasoning") or ""
                                            content_piece = delta.get("content") or ""

                                            out_piece = ""
                                            if reasoning_piece:
                                                if think_mod_enabled:
                                                    if not in_reasoning_block:
                                                        out_piece += "<think>\n"
                                                        in_reasoning_block = True
                                                    out_piece += reasoning_piece
                                                else:
                                                    suppressed_reasoning_pieces.append(reasoning_piece)
                                                    if not collected_chunks and not sent_wait_status:
                                                        sent_wait_status = True
                                                        await event_queue.put({"status": "生成中..."})

                                            if content_piece:
                                                if in_reasoning_block:
                                                    out_piece += "\n</think>\n\n"
                                                    in_reasoning_block = False

                                                if not think_mod_enabled and not collected_chunks:
                                                    cand_buf = suppressed_think_buf + content_piece
                                                    cand_l = cand_buf.lstrip().lower()
                                                    if not cand_l:
                                                        suppressed_think_buf = cand_buf
                                                        content_piece = ""
                                                    elif suppressing_inline_think or re.match(r"^<think(?:ing)?(?:\s|>)", cand_l):
                                                        suppressing_inline_think = True
                                                        suppressed_think_buf = cand_buf
                                                        if re.search(r"</think(?:ing)?>", suppressed_think_buf, flags=re.I):
                                                            after_think = re.sub(r"^[\s\S]*?</think(?:ing)?>\s*", "", suppressed_think_buf, flags=re.I)
                                                            suppressed_think_buf = ""
                                                            suppressing_inline_think = False
                                                            content_piece = after_think
                                                        else:
                                                            if not sent_wait_status:
                                                                sent_wait_status = True
                                                                await event_queue.put({"status": "生成中..."})
                                                            content_piece = ""
                                                    elif (
                                                        len(cand_l) < len("<thinking>")
                                                        and ("<think>".startswith(cand_l) or "<thinking>".startswith(cand_l))
                                                    ):
                                                        # 仅在仍可能是 <think>/<thinking> 前缀（如刚收到 "<" 或 "<th"）时暂存，绝不锁死 <div> / <status>
                                                        suppressed_think_buf = cand_buf
                                                        content_piece = ""
                                                    else:
                                                        suppressed_think_buf = ""
                                                        content_piece = cand_buf

                                                if content_piece:
                                                    out_piece += content_piece

                                            if out_piece:
                                                combined_so_far = "".join(collected_chunks) + out_piece
                                                if not think_mod_enabled and re.search(r"(?<!`)</think(?:ing)?>(?!`)", combined_so_far, flags=re.I):
                                                    cleaned_so_far = strip_thinking_blocks(combined_so_far)
                                                    collected_chunks.clear()
                                                    if cleaned_so_far:
                                                        collected_chunks.append(cleaned_so_far)
                                                    combined_so_far = cleaned_so_far
                                                    ACTIVE_PARTIAL_TEXT[req.chat_id] = cleaned_so_far
                                                    await event_queue.put({"replace": cleaned_so_far})
                                                else:
                                                    collected_chunks.append(out_piece)
                                                    ACTIVE_PARTIAL_TEXT[req.chat_id] = combined_so_far
                                                    await event_queue.put({"chunk": out_piece})

                                                if len(combined_so_far) >= 48 and (
                                                    "\n" in out_piece or (len(combined_so_far) - last_loop_chk_len) >= 40
                                                ):
                                                    last_loop_chk_len = len(combined_so_far)
                                                    trimmed_loop = _detect_and_trim_stream_loop(
                                                        combined_so_far,
                                                        is_trpg=is_trpg_stream,
                                                        expect_choices=stream_choices_enabled,
                                                    )
                                                    if trimmed_loop is not None:
                                                        print(f"[LoopGuard] 实时拦截复读/越界死循环，自动裁剪 {len(combined_so_far)} -> {len(trimmed_loop)} 字并终止流")
                                                        collected_chunks.clear()
                                                        if trimmed_loop:
                                                            collected_chunks.append(trimmed_loop)
                                                        ACTIVE_PARTIAL_TEXT[req.chat_id] = trimmed_loop
                                                        await event_queue.put({"replace": trimmed_loop})
                                                        break
                                        except Exception:
                                            continue

                                if not collected_chunks and suppressed_think_buf and not suppressing_inline_think:
                                    collected_chunks.append(suppressed_think_buf)
                                    ACTIVE_PARTIAL_TEXT[req.chat_id] = suppressed_think_buf
                                    await event_queue.put({"chunk": suppressed_think_buf})
                                    suppressed_think_buf = ""

                                if in_reasoning_block and think_mod_enabled:
                                    close_tag = "\n</think>\n\n"
                                    collected_chunks.append(close_tag)
                                    ACTIVE_PARTIAL_TEXT[req.chat_id] = "".join(collected_chunks)
                                    await event_queue.put({"chunk": close_tag})

                                cur_combined_check = "".join(collected_chunks)
                                if (not collected_chunks or not _has_narrative_outside_status(cur_combined_check)) and (suppressed_think_buf or suppressed_reasoning_pieces):
                                    salvaged = re.sub(r"^<think(?:ing)?>\s*", "", suppressed_think_buf, flags=re.I).strip()
                                    if not salvaged and suppressed_reasoning_pieces:
                                        salvaged = "".join(suppressed_reasoning_pieces).strip()
                                    if salvaged and (not collected_chunks or _has_narrative_outside_status(salvaged)):
                                        if not collected_chunks:
                                            collected_chunks.append(salvaged)
                                        else:
                                            collected_chunks.insert(0, salvaged + "\n\n")
                                        merged_salvaged = "".join(collected_chunks)
                                        ACTIVE_PARTIAL_TEXT[req.chat_id] = merged_salvaged
                                        await event_queue.put({"replace": merged_salvaged})

                        if collected_chunks:
                            last_err_str = None
                            break
                    except (httpx.ConnectError, httpx.ProxyError) as conn_e:
                        raw_ce = str(conn_e).strip()
                        if ep["is_local"]:
                            last_err_str = (
                                f"无法连接本地模型引擎 ({cur_base_url})：引擎可能刚退出、正在重载或被安全软件拦截。"
                                "可点击「重新生成」自动拉起，或查看 data/engine_logs 日志。"
                            )
                        else:
                            last_err_str = raw_ce or f"{type(conn_e).__name__}: 无法连接上游接口或代理异常"
                        if attempt_idx == 1 and len(proxy_candidates) > 1 and not collected_chunks:
                            continue
                        break
                    except httpx.TimeoutException as to_e:
                        last_err_str = f"{type(to_e).__name__}: 通道 {cur_model} 响应超时"
                        break
                    except httpx.HTTPError as net_e:
                        # 流式传输中途断开（RemoteProtocolError / ReadError 等）：已收到内容则保留半截回复直接落盘，
                        # 一个字都没收到时才重试一次，避免丢弃已生成的长文
                        last_err_str = str(net_e).strip() or f"{type(net_e).__name__}: 上游连接中途断开"
                        if collected_chunks:
                            print(f"[Warn] 上游流式连接中途断开，保留已生成的 {len(''.join(collected_chunks))} 字半截回复: {type(net_e).__name__}")
                            break
                        if not net_retry_used:
                            net_retry_used = True
                            proxy_candidates.append(cur_proxy)
                            await asyncio.sleep(1.0)
                            continue
                        break

            if last_err_str is not None and not collected_chunks:
                await event_queue.put({"error": last_err_str})
                return

            full_reply = "".join(collected_chunks)
            if full_reply:
                m_close = re.search(r"(?<!`)</think(?:ing)?>(?!`)", full_reply, flags=re.I)
                m_open = re.search(r"(?<!`)<think(?:ing)?>(?!`)", full_reply, flags=re.I)
                if m_close and (not m_open or m_close.start() < m_open.start()):
                    after_unmatched_think = full_reply[m_close.end():].lstrip()
                    if _has_narrative_outside_status(after_unmatched_think):
                        full_reply = "<think>\n" + full_reply
                    else:
                        full_reply = re.sub(r"(?<!`)</?think(?:ing)?>(?!`)", "", full_reply, flags=re.I)

                if not think_mod_enabled:
                    full_reply = strip_thinking_blocks(full_reply)

                # 执行 AI 回复的持久化正则替换 (is_only_render=False)
                full_reply, rx_ai = apply_regex_scripts(full_reply, regex_list, target_scope=1, only_persistent=True)
                prompt_log_snapshot["applied_regex"].extend(rx_ai)

                # 万物模块顺序归一化与跑团缺漏模块自动自愈补全
                try:
                    is_trpg_active = (project_data.get("status_panel_enabled", True) is not False) and not is_free_chat_project(project_data)
                    enabled_ui_mods = [
                        m for m in ui_mods_norm
                        if isinstance(m, dict) and m.get("enabled", True) is not False and str(m.get("id") or "") != "mod_scale"
                    ]
                    story_mod_enabled = any(str(m.get("type") or "") == "story_narrative" or str(m.get("id") or "") == "mod_story" for m in enabled_ui_mods)
                    choices_mod_enabled = any(str(m.get("type") or "") == "action_choices" or str(m.get("id") or "") == "mod_choices" for m in enabled_ui_mods)
                    active_status_mods = [
                        m for m in enabled_ui_mods
                        if str(m.get("type") or "progress_stats") in STATUS_SUBMODULE_TYPES and str(m.get("key") or "").strip()
                    ]
                    active_status_keys = [str(m.get("key") or "").strip() for m in active_status_mods if str(m.get("key") or "").strip()]
                    post_trim = _detect_and_trim_stream_loop(full_reply, is_trpg=is_trpg_active, expect_choices=choices_mod_enabled)
                    if post_trim is not None and post_trim.strip():
                        full_reply = post_trim
                    norm_parts = split_ai_message_modules(full_reply, active_status_keys)

                    async def _run_self_heal_stream(heal_messages: List[Dict[str, Any]], heal_max_tokens: int = 2048, on_partial=None) -> str:
                        heal_ep = resolve_model_endpoint(model_candidates[0], settings)
                        heal_rep = max(rep_pen, 1.08) if heal_ep["is_local"] else rep_pen
                        heal_pres = max(pres_pen, 0.45) if heal_ep["is_local"] else pres_pen
                        heal_freq = max(freq_pen, 0.12) if heal_ep["is_local"] else freq_pen
                        heal_body: Dict[str, Any] = {
                            "model": heal_ep["upstream_model"],
                            "messages": sanitize_messages_for_model(heal_messages, heal_ep["supports_vision"] and not vision_fallback_used),
                            "temperature": max(0.35, min(temp, 0.72)),
                            "top_p": top_p,
                            "max_tokens": heal_max_tokens,
                            "stream": True,
                        }
                        if heal_ep.get("protocol") not in ("claude", "gemini"):
                            if heal_pres != 0:
                                heal_body["presence_penalty"] = heal_pres
                            if heal_freq != 0:
                                heal_body["frequency_penalty"] = heal_freq
                        if heal_ep["is_local"]:
                            heal_body["stop"] = list(_LOCAL_STOP_SEQUENCES)
                            if heal_ep["engine"] == "strata":
                                heal_body["reasoning_effort"] = "none"
                                heal_body["reasoning_budget_tokens"] = 0
                                heal_body["chat_template_kwargs"] = {"enable_thinking": False}
                                heal_body["repetition_penalty"] = heal_rep
                                heal_body["penalty_last_n"] = 2048
                            elif heal_ep["engine"] == "ollama":
                                heal_body["think"] = False
                                heal_body["reasoning_effort"] = "none"
                                heal_body["thinking_budget_tokens"] = 0
                                heal_body["reasoning_budget"] = 0
                                heal_body["reasoning_budget_tokens"] = 0
                                heal_body["chat_template_kwargs"] = {"enable_thinking": False}
                                heal_body["options"] = {
                                    "repeat_penalty": heal_rep,
                                    "repeat_last_n": 2048,
                                    "presence_penalty": heal_pres,
                                    "frequency_penalty": heal_freq,
                                    "num_ctx": get_optimal_ollama_num_ctx(
                                        max_context_k if max_context_k else 96,
                                        heal_ep.get("gguf_path", ""),
                                    ),
                                    "num_predict": heal_max_tokens,
                                }
                            else:
                                heal_body["think"] = False
                                heal_body["reasoning_effort"] = "none"
                                heal_body["chat_template_kwargs"] = {"enable_thinking": False}
                        heal_chunks: List[str] = []
                        heal_timeout = 180.0 if heal_ep["is_local"] else 90.0
                        async with httpx.AsyncClient(proxy=heal_ep.get("proxy"), trust_env=False, timeout=httpx.Timeout(heal_timeout, connect=15.0)) as h_client:
                            async with h_client.stream(
                                "POST",
                                f"{heal_ep['base_url']}/chat/completions",
                                headers=heal_ep.get("headers") or {
                                    "Authorization": f"Bearer {heal_ep['api_key']}",
                                    "Content-Type": "application/json",
                                },
                                json=heal_body,
                            ) as h_resp:
                                if h_resp.status_code != 200:
                                    return ""
                                async for h_line in h_resp.aiter_lines():
                                    h_line = h_line.strip()
                                    if not h_line or not h_line.startswith("data:"):
                                        continue
                                    h_raw = h_line[5:].lstrip()
                                    if h_raw == "[DONE]":
                                        break
                                    try:
                                        h_json = json.loads(h_raw)
                                        h_piece = ((h_json.get("choices") or [{}])[0].get("delta") or {}).get("content") or ""
                                        if h_piece:
                                            heal_chunks.append(h_piece)
                                            h_joined = "".join(heal_chunks)
                                            h_trim = _detect_and_trim_stream_loop(h_joined, is_trpg=is_trpg_active, expect_choices=choices_mod_enabled)
                                            if h_trim is not None:
                                                heal_chunks = [h_trim] if h_trim else []
                                                if on_partial is not None:
                                                    await on_partial(h_trim)
                                                break
                                            if on_partial is not None:
                                                await on_partial(h_joined)
                                    except Exception:
                                        continue
                        return strip_thinking_blocks("".join(heal_chunks))

                    # 自愈 1：若模型跳过【剧情正文】直接输出了 <status> 或选项，自动流式补写本回合剧情正文
                    if is_trpg_active and story_mod_enabled and len(norm_parts.get("story", "").strip()) < 40 and (norm_parts.get("status") or norm_parts.get("choices")):
                        await event_queue.put({"status": "正在补全剧情正文..."})
                        existing_tail = assemble_ai_message_modules("", "", norm_parts.get("status", ""), norm_parts.get("choices", ""))

                        async def _on_story_heal_partial(partial_story_raw: str):
                            clean_p = re.sub(r"<status[\s\S]*$", "", partial_story_raw, flags=re.I).strip()
                            if clean_p:
                                preview_full = assemble_ai_message_modules(
                                    norm_parts.get("think", "") if think_mod_enabled else "",
                                    clean_p,
                                    norm_parts.get("status", ""),
                                    norm_parts.get("choices", ""),
                                )
                                ACTIVE_PARTIAL_TEXT[req.chat_id] = preview_full
                                await event_queue.put({"replace": preview_full})

                        heal_story_msgs = list(api_messages) + [
                            {"role": "assistant", "content": existing_tail},
                            {
                                "role": "user",
                                "content": (
                                    "【系统补全指令】：你刚才漏写了【剧情正文】就直接输出了状态栏！\n"
                                    "请立刻根据刚才的玩家行动与当前状态栏，补写本回合 800~1500 字的第二人称（「你」）沉浸式小说【剧情正文】。\n"
                                    "严禁再次输出 `<status>` 状态栏、严禁输出行动选项、严禁输出 `【剧情正文】` 标题或任何解释，直接输出小说正文段落："
                                ),
                            },
                        ]
                        try:
                            healed_story_raw = await _run_self_heal_stream(heal_story_msgs, heal_max_tokens=2048, on_partial=_on_story_heal_partial)
                            healed_parts = split_ai_message_modules(healed_story_raw, active_status_keys)
                            if len(healed_parts.get("story", "").strip()) >= 40:
                                norm_parts["story"] = healed_parts["story"].strip()
                            if not norm_parts.get("choices") and healed_parts.get("choices"):
                                norm_parts["choices"] = healed_parts["choices"]
                        except Exception as heal_e:
                            print(f"[Warn] 自动补全剧情正文异常: {heal_e}")

                    # 自愈 2：若模型漏掉了 <status>（或漏掉了 [角色关系] 等已启用子栏位）或漏掉了底部行动选项
                    if is_trpg_active and (norm_parts.get("story", "").strip() or norm_parts.get("status", "").strip() or norm_parts.get("choices", "").strip()):
                        missing_st_mods = _find_missing_status_mods(norm_parts.get("status", ""), active_status_mods) if active_status_mods else []
                        missing_choices = bool(choices_mod_enabled and not norm_parts.get("choices", "").strip())
                        if (missing_st_mods or missing_choices) and len(norm_parts.get("story", "").strip()) >= 15:
                            await event_queue.put({"status": "正在同步状态栏与行动选项..."})
                            req_sections_desc: List[str] = []
                            if missing_st_mods:
                                spec_lines = ["1. 请输出 `<status>...</status>` 状态块，内部必须包含以下状态栏位（结合本轮最新剧情实时更新数值与物品，严禁照抄示例假词）："]
                                for sm in missing_st_mods:
                                    sm_key = str(sm.get("key") or "").strip()
                                    sm_fields = str(sm.get("fields") or "").strip()
                                    spec_lines.append(f"[{sm_key}]\n{sm_fields}")
                                req_sections_desc.append("\n".join(spec_lines))
                            if missing_choices:
                                req_sections_desc.append(
                                    "2. 在 `</status>` 之后的最底部输出唯一一次“你打算怎么做？”，并另起新行按 `1.`、`2.`、`3.`、`4.` 给出 4 个结合当前剧情的具体行动选项。"
                                )

                            prev_status_ref = ""
                            if history_messages:
                                for _hm in reversed(history_messages):
                                    if isinstance(_hm, dict) and _hm.get("role") == "assistant":
                                        _hp = split_ai_message_modules(str(_hm.get("content") or ""), active_status_keys)
                                        if _hp.get("status"):
                                            prev_status_ref = f"\n\n【上一轮状态栏参考（请在此基础上结合本轮最新剧情增减数值与物品）】：\n{_hp['status']}"
                                            break

                            async def _on_tail_heal_partial(partial_tail_raw: str):
                                t_parts = split_ai_message_modules(partial_tail_raw, active_status_keys)
                                merged_st = norm_parts.get("status", "")
                                if t_parts.get("status") and active_status_mods:
                                    merged_st = _merge_and_complete_status_block(
                                        norm_parts.get("status", ""),
                                        t_parts["status"],
                                        active_status_mods,
                                        history_messages,
                                    )
                                merged_ch = norm_parts.get("choices", "") or t_parts.get("choices", "")
                                preview_full = assemble_ai_message_modules(
                                    norm_parts.get("think", "") if think_mod_enabled else "",
                                    norm_parts.get("story", ""),
                                    merged_st,
                                    merged_ch,
                                )
                                if preview_full:
                                    ACTIVE_PARTIAL_TEXT[req.chat_id] = preview_full
                                    await event_queue.put({"replace": preview_full})

                            compact_ctx_msgs = ([api_messages[0]] if api_messages and api_messages[0].get("role") == "system" else []) + list(api_messages[-2:])
                            asst_so_far = norm_parts["story"][-2000:]
                            if norm_parts.get("status"):
                                asst_so_far = f"{asst_so_far}\n\n{norm_parts['status']}"
                            heal_tail_msgs = compact_ctx_msgs + [
                                {"role": "assistant", "content": asst_so_far},
                                {
                                    "role": "user",
                                    "content": (
                                        "【系统补全指令】：请紧接上面的剧情正文，立即补全本次回复缺失的状态栏与行动选项（严禁重复输出剧情正文，只输出以下缺失内容）："
                                        + prev_status_ref
                                        + "\n\n"
                                        + "\n\n".join(req_sections_desc)
                                    ),
                                },
                            ]
                            try:
                                healed_tail_raw = await _run_self_heal_stream(heal_tail_msgs, heal_max_tokens=1024, on_partial=_on_tail_heal_partial)
                                if healed_tail_raw:
                                    tail_parts = split_ai_message_modules(healed_tail_raw, active_status_keys)
                                    if tail_parts.get("status"):
                                        norm_parts["status"] = _merge_and_complete_status_block(
                                            norm_parts.get("status", ""),
                                            tail_parts["status"],
                                            active_status_mods,
                                            history_messages,
                                        )
                                    if missing_choices and tail_parts.get("choices"):
                                        norm_parts["choices"] = tail_parts["choices"]
                            except Exception as heal_tail_e:
                                print(f"[Warn] 自动补全状态栏/选项异常: {heal_tail_e}")

                        if active_status_mods:
                            norm_parts["status"] = _merge_and_complete_status_block(
                                norm_parts.get("status", ""),
                                "",
                                active_status_mods,
                                history_messages,
                            )
                        if choices_mod_enabled and not norm_parts.get("choices", "").strip():
                            norm_parts["choices"] = (
                                "你打算怎么做？\n"
                                "1. 仔细观察周围环境的异常细节与可疑线索\n"
                                "2. 主动开口试探或与眼前人物交涉\n"
                                "3. 检查随身装备与物品，做好随时应对变故的准备\n"
                                "4. 保持警惕，顺着当前局势继续向前探索推进"
                            )

                    if norm_parts.get("status") or norm_parts.get("choices") or norm_parts.get("story"):
                        new_full_reply = assemble_ai_message_modules(
                            norm_parts.get("think", "") if think_mod_enabled else "",
                            norm_parts.get("story", ""),
                            norm_parts.get("status", ""),
                            norm_parts.get("choices", ""),
                        )
                        if new_full_reply and new_full_reply != full_reply:
                            full_reply = new_full_reply
                            ACTIVE_PARTIAL_TEXT[req.chat_id] = full_reply
                            await event_queue.put({"replace": full_reply})
                except Exception as norm_e:
                    print(f"[Warn] 模块归一化或自愈异常: {norm_e}")

                # 检测 CG 图鉴触发与自动解锁（仅扫描去除思维链后的正文，避免思考过程误触发 CG）
                visible_reply_for_cg = strip_thinking_blocks(full_reply)
                triggered_cgs, cg_updated = evaluate_cg_book(project_data, f"{user_display_text}\n{visible_reply_for_cg}")
                all_unlocked_ids = [c.get("id") for c in (project_data.get("cg_book") or []) if c.get("unlocked") and c.get("id")]
                if cg_updated and proj_file.exists():
                    # 生成期间用户可能编辑过项目：重新读取最新项目文件，仅把本次触发的 CG 标记为已解锁后原子写回
                    try:
                        trig_ids = {str(t.get("id")) for t in (triggered_cgs or []) if isinstance(t, dict) and t.get("id")}
                        with open(proj_file, "r", encoding="utf-8") as pf:
                            fresh_proj = json.load(pf)
                        if isinstance(fresh_proj, dict) and trig_ids:
                            changed = False
                            for cg in (fresh_proj.get("cg_book") or []):
                                if isinstance(cg, dict) and str(cg.get("id")) in trig_ids and not cg.get("unlocked"):
                                    cg["unlocked"] = True
                                    changed = True
                            if changed:
                                atomic_write_json(proj_file, fresh_proj, ensure_ascii=False, indent=2)
                            all_unlocked_ids = [
                                c.get("id") for c in (fresh_proj.get("cg_book") or [])
                                if isinstance(c, dict) and c.get("unlocked") and c.get("id")
                            ]
                    except Exception:
                        pass

                assistant_msg_id = str(uuid.uuid4())[:8]
                assistant_msg = {
                    "id": assistant_msg_id,
                    "role": "assistant",
                    "content": full_reply,
                    "triggered_cgs": triggered_cgs,
                    "triggered_worldbooks": [w["name"] for w in triggered_wb_logs],
                    "timestamp": time.time()
                }
                with open(chat_file, "r", encoding="utf-8") as f:
                    cur_data = json.load(f)
                if model:
                    cur_data["model"] = model
                if pending_regen:
                    # 重新生成：新回复成功后才按消息 ID 截断旧回复并写入编辑后的玩家消息（失败/停止时旧回复完整保留）
                    if not _apply_pending_regen(cur_data, pending_regen):
                        print(f"[Warn] 重新生成目标玩家消息已不存在 (chat={req.chat_id})，新回复将追加到对话末尾")
                cur_data.setdefault("messages", []).append(assistant_msg)
                cur_data["unlocked_cgs"] = all_unlocked_ids
                cur_data["last_prompt_log"] = prompt_log_snapshot
                cur_data["updated_at"] = time.time()

                chat_title = cur_data.get("title", "")
                if len(cur_data["messages"]) <= 3 and (chat_title.startswith("对话 ") or chat_title.startswith("分支 #") or chat_title == "未命名对话"):
                    short_title = user_display_text[:14] + ("..." if len(user_display_text) > 14 else "")
                    if short_title.strip():
                        cur_data["title"] = short_title

                atomic_write_json(chat_file, cur_data, ensure_ascii=False, indent=2)
                if ACTIVE_PENDING_REGEN.get(req.chat_id) is pending_regen:
                    ACTIVE_PENDING_REGEN.pop(req.chat_id, None)

                await event_queue.put({
                    "done": True,
                    "msg_id": assistant_msg_id,
                    "full_reply": full_reply,
                    "title": cur_data.get("title"),
                    "summary": cur_data.get("summary"),
                    "summarized_count": int(cur_data.get("summarized_count", 0)),
                    "triggered_cgs": triggered_cgs,
                    "unlocked_cgs": all_unlocked_ids,
                    "triggered_worldbooks": triggered_wb_logs
                })
            else:
                await event_queue.put({"error": "模型未返回内容，请重试或换模型"})
        except asyncio.CancelledError:
            raise
        except Exception as e:
            err_desc = str(e).strip() or f"{type(e).__name__}: 超时或网络中断，请重试"
            await event_queue.put({"error": err_desc})
        finally:
            if ACTIVE_BG_TASKS.get(req.chat_id) is asyncio.current_task():
                ACTIVE_BG_TASKS.pop(req.chat_id, None)
                ACTIVE_PARTIAL_TEXT.pop(req.chat_id, None)
                if pending_regen is None or ACTIVE_PENDING_REGEN.get(req.chat_id) is pending_regen:
                    ACTIVE_PENDING_REGEN.pop(req.chat_id, None)
            await event_queue.put(None)

    bg_task = asyncio.create_task(_run_upstream_generation())
    ACTIVE_BG_TASKS[req.chat_id] = bg_task

    async def stream_generator():
        start_ts = time.time()
        has_received_chunk = False
        img_count = len(turn_images)
        img_hint = f"（{img_count}张图）" if img_count > 0 else ""
        wb_hint = f" · 触发 {len(triggered_wb_logs)} 条世界书" if triggered_wb_logs else ""

        yield f"data: {json.dumps({'status': f'已提交{img_hint}{wb_hint}，等待响应...'})}\n\n"

        while True:
            try:
                item = await asyncio.wait_for(event_queue.get(), timeout=2.0)
                if item is None:
                    break
                if "chunk" in item:
                    has_received_chunk = True
                yield f"data: {json.dumps(item)}\n\n"
            except asyncio.TimeoutError:
                if not has_received_chunk:
                    elapsed = int(time.time() - start_ts)
                    yield f"data: {json.dumps({'status': f'生成中{img_hint}{wb_hint}... ({elapsed}s)'})}\n\n"
                else:
                    yield ": keep-alive\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


_STATUS_KEY_ALIASES: Dict[str, str] = {
    "角色状态": "主角状态",
    "状态栏": "主角状态",
    "状态面板": "主角状态",
    "个人状态": "主角状态",
    "自身状态": "主角状态",
    "当前状态": "主角状态",
    "生命状态": "主角状态",
    "主角属性": "主角状态",
    "角色属性": "主角状态",
    "属性栏": "主角状态",
    "属性": "主角状态",
    "装备": "装备栏",
    "身体装备": "装备栏",
    "穿戴装备": "装备栏",
    "当前装备": "装备栏",
    "武器装备": "装备栏",
    "防具武器": "装备栏",
    "物品": "物品栏",
    "背包": "物品栏",
    "背包栏": "物品栏",
    "随身物品": "物品栏",
    "背包物品": "物品栏",
    "行囊": "物品栏",
    "道具栏": "物品栏",
    "道具": "物品栏",
    "人物关系": "角色关系",
    "好感": "角色关系",
    "好感度": "角色关系",
    "好感栏": "角色关系",
    "关系栏": "角色关系",
    "人际关系": "角色关系",
    "同伴关系": "角色关系",
    "在场人物": "角色关系",
    "在场NPC": "角色关系",
    "周围人物": "角色关系",
    "NPC关系": "角色关系",
    "NPC": "角色关系",
    "NPC信息": "角色关系",
    "羁绊": "角色关系",
    "情报": "情报卡",
    "情报栏": "情报卡",
    "世界情报": "情报卡",
    "当前情报": "情报卡",
}


def _normalize_status_section_key(raw_key: str, active_keys: Optional[List[str]] = None) -> str:
    k = re.sub(
        r"^[📊⚔️🎒💕📋🏷️🧩📖🧠🎯📝💭⚡#\d①-⑩一二三四五六七八九十\.、:：\-—\s*]+|[\*:\s：]+$",
        "",
        str(raw_key or ""),
    ).strip()
    if active_keys and k in active_keys:
        return k
    mapped = _STATUS_KEY_ALIASES.get(k, k)
    if active_keys and mapped in active_keys:
        return mapped
    # 兼容复合标题，如 [角色关系 - 银发圣女]、[装备栏（当前穿戴）]
    m_comp = re.match(r"^([^\s\-—:：/（(]{2,10})[\s\-—:：/（(]+(.+)$", k)
    if m_comp:
        head_k = m_comp.group(1).strip()
        head_mapped = _STATUS_KEY_ALIASES.get(head_k, head_k)
        if (active_keys and head_mapped in active_keys) or head_mapped in ("主角状态", "装备栏", "物品栏", "角色关系", "情报卡"):
            return head_mapped
    if active_keys:
        for ak in active_keys:
            if ak and (ak in k or k in ak) and len(k) >= 2:
                return ak
    return mapped


def _compact_runaway_status_line(line: str) -> str:
    """清理 <status> 单行中偶发的无标点近义词/成语堆砌失控（如括号内连续数十个无标点汉字），保留前半段有效状态描述并自动补齐未闭合括号"""
    s = str(line or "").strip()
    if len(s) < 36:
        return s
    s = re.sub(r"([\u4e00-\u9fff]{18})[\u4e00-\u9fff]{18,}", r"\1", s)
    if "|" not in s and "｜" not in s and len(s) > 150:
        s = s[:140].rstrip("，、,;； ")
    if s.count("(") > s.count(")"):
        s += ")" * (s.count("(") - s.count(")"))
    if s.count("（") > s.count("）"):
        s += "）" * (s.count("（") - s.count("）"))
    if s.count("[") > s.count("]"):
        s += "]" * (s.count("[") - s.count("]"))
    return s


def _parse_status_sections(status_text: str, active_keys: Optional[List[Any]] = None) -> Dict[str, List[str]]:
    if not status_text:
        return {}
    norm_keys: List[str] = []
    if active_keys:
        for item in active_keys:
            if isinstance(item, dict):
                s_k = str(item.get("key") or item.get("name") or "").strip()
            else:
                s_k = str(item or "").strip()
            if s_k:
                norm_keys.append(s_k)
    active_keys = norm_keys
    inner = re.sub(r"```(?:xml|html|text|markdown|status)?\s*|\s*```", "", str(status_text).strip(), flags=re.I)
    inner = re.sub(r"</?(?:status|status_panel|status_bar)(?:\s+[^>]*)?>|＜/?status＞|\[/?status\]", "", inner, flags=re.I).strip()
    hdr_re = re.compile(
        r"^\s*(?:[-*•]\s*)?(?:#{1,6}\s*|\*\*|\*)?\s*(?:(?:#?\d+|[①-⑩])[\.、\s]*)?[\[【]\s*(?:(?:#?\d+|[①-⑩])[\.、\s]*)?([^\]】\n]+?)\s*[\]】]\s*[:：]?\s*(?:\*\*|\*)?\s*[:：]?\s*(.*)$"
    )
    md_hdr_re = re.compile(
        r"^\s*(?:[-*•]\s*)?(?:#{1,6}\s+|\*\*\s*)(?:(?:#?\d+|[①-⑩])[\.、\s]*)?([📊⚔️🎒💕📋🏷️🧩📖🧠🎯📝💭⚡\s]*[^*\n:：\[\]【】]{2,14}?)\s*(?:\*\*)?\s*[:：]?\s*(?:\*\*)?\s*$"
    )
    sections: Dict[str, List[str]] = {}
    cur_key = ""
    for raw_ln in inner.splitlines():
        ln = raw_ln.strip()
        if not ln or re.match(r"^(?:---|\*\*\*|___)$", ln):
            continue
        m_h = hdr_re.match(ln)
        if m_h:
            raw_hdr_name = m_h.group(1).strip()
            cur_key = _normalize_status_section_key(raw_hdr_name, active_keys)
            sections.setdefault(cur_key, [])
            # 若复合标题形如 [角色关系 - 银发圣女]，自动保留 NPC 名称行
            m_comp_npc = re.match(r"^([^\s\-—:：/（(]{2,10})[\s\-—:：/]+([^）)\n]+)$", raw_hdr_name)
            if m_comp_npc and cur_key == "角色关系":
                npc_sub = m_comp_npc.group(2).strip()
                if npc_sub and not re.match(r"^(?:状态|列表|面板|详情)$", npc_sub):
                    sections[cur_key].append(f"角色: {npc_sub}")
            rest = m_h.group(2).strip()
            if rest:
                sections[cur_key].append(rest)
            continue
        m_md = md_hdr_re.match(ln)
        if m_md:
            cand_k = _normalize_status_section_key(m_md.group(1), active_keys)
            if (active_keys and cand_k in active_keys) or cand_k in ("主角状态", "装备栏", "物品栏", "角色关系", "情报卡", "身体栏", "世界新闻"):
                cur_key = cand_k
                sections.setdefault(cur_key, [])
                continue
        if not cur_key:
            # 若模型在 <status> 开头直接写了「生命: 100/100」而漏写了首行 [主角状态]，自动归入首个状态栏位
            cur_key = active_keys[0] if active_keys else "主角状态"
            sections.setdefault(cur_key, [])
        sections[cur_key].append(_compact_runaway_status_line(ln))
    return sections


def _find_missing_status_mods(status_text: str, active_status_mods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not active_status_mods:
        return []
    active_keys = [str(m.get("key") or "").strip() for m in active_status_mods if str(m.get("key") or "").strip()]
    parsed = _parse_status_sections(status_text, active_keys)
    missing: List[Dict[str, Any]] = []
    for m in active_status_mods:
        k = str(m.get("key") or "").strip()
        if not k:
            continue
        lines = [x.strip() for x in parsed.get(k, []) if x.strip()]
        if not lines:
            missing.append(m)
    return missing


def _default_fallback_status_lines(mod: Dict[str, Any]) -> List[str]:
    k = str(mod.get("key") or "").strip()
    m_type = str(mod.get("type") or "")
    raw_fields = str(mod.get("fields") or "").strip()
    if raw_fields and k != "角色关系" and m_type not in ("npc_affinity", "relations"):
        parsed_schema_lines: List[str] = []
        for raw_ln in raw_fields.splitlines():
            ln = raw_ln.strip()
            if not ln or ln.startswith(("#", "//", "<!--")):
                continue
            if any(ph in ln for ph in ("实际在场人物", "严禁留空", "示例假词", "待定", "请填写")):
                continue
            if any(meta in ln for meta in ("随时代背景自适应", "随身份适配", "随时代适配", "贴合时代背景", "关键随身信物", "关键线索物")):
                slot_m = re.match(r"^([^:：]{1,12})[:：]", ln)
                if slot_m:
                    sk = slot_m.group(1).strip()
                    if sk == "财富":
                        parsed_schema_lines.append("财富: 随身路费(日常开销)")
                    elif sk == "主手":
                        parsed_schema_lines.append("主手: 空手(未持握武器)")
                    elif sk == "防具":
                        parsed_schema_lines.append("防具: 常服(日常行动装束)")
                    elif sk == "饰品":
                        parsed_schema_lines.append("饰品: 无")
                continue
            if m_type in ("inventory_grid", "inventory") and ln.startswith("应急补给("):
                parsed_schema_lines.append("随身行囊(基础随身物品)x1")
                continue
            parsed_schema_lines.append(ln)
        if parsed_schema_lines:
            return parsed_schema_lines

    if k == "角色关系" or m_type in ("npc_affinity", "relations"):
        return [
            "在场人物: 暂无明确交集对象(随剧情接触解锁)",
            "当前关系: 未知(尚未建立深入互动)",
            "人物态度: 观察中(等待进一步行动触发)",
        ]
    if k == "物品栏" or m_type in ("inventory_grid", "inventory"):
        return ["随身行囊(基础随身物品)x1"]
    if k == "装备栏" or m_type in ("equipment_slots", "gear"):
        return [
            "头部: 常服(无特殊防护)",
            "身体: 便装(日常行动装束)",
            "手部: 空手(未持握武器)",
            "脚部: 便鞋(轻便行走)",
        ]
    if k == "主角状态" or m_type == "progress_stats":
        return [
            "生命: 100/100(状态完好)",
            "理智: 80/100(精神稳定)",
            "财富: 随身路费(日常开销)",
            "状态: 正常(无异常负面效果)",
        ]
    return ["状态: 正常(随剧情推进实时更新)"]


_NPC_PLACEHOLDER_RE = re.compile(
    r"暂无(?:其他)?(?:在场)?(?:NPC|人物|角色|明确交集对象|交集|对象)|"
    r"无(?:其他)?(?:在场)?(?:NPC|人物|角色)|"
    r"独自(?:一人|行动)|尚未(?:遇到|结识|建立)",
    re.I,
)
_NPC_ATTR_LINE_RE = re.compile(
    r"^(?:好感度?|好感|信赖度?|信任度?|亲密度?|恶堕度?|服从度?|警戒度?|戒心|敌意|"
    r"态度|倾向|立场|关系|身份|定位|动态|动作|表现|心理|神态|状态|"
    r"当前动态|当前态度|当前关系|人物态度|备注|印象|评价)\s*[:：]",
    re.I,
)
_NPC_NAME_PREFIX_RE = re.compile(
    r"^(?:角色|人物|姓名|对象|目标|同伴|队友|敌人|NPC|在场人物|周围人物)\s*\d*\s*[:：]\s*",
    re.I,
)
_KV_SLOT_ALIASES = {
    "生命值": "生命", "HP": "生命", "hp": "生命", "气血": "生命",
    "体力值": "体力", "精力": "体力", "耐力": "体力", "SP": "体力", "sp": "体力",
    "理智值": "理智", "精神": "理智", "SAN": "理智", "MP": "理智", "法力": "理智", "灵力": "理智",
    "金钱": "财富", "金币": "财富", "银币": "财富", "银元": "财富", "铜币": "财富", "灵石": "财富", "信用点": "财富", "货币": "财富", "资金": "财富", "盘缠": "财富",
    "当前处境": "处境", "当前状态": "处境", "当前位置": "处境", "位置": "处境", "地点": "处境",
    "主手": "手部", "右手": "手部", "双手": "手部", "武器": "手部",
    "上衣": "身体", "躯干": "身体", "服饰": "身体", "防具": "身体", "外衣": "身体",
    "鞋子": "脚部", "足部": "脚部", "靴子": "脚部",
}


def _extract_npc_blocks(lines: List[str]) -> List[tuple[str, List[str], bool]]:
    blocks: List[List[str]] = []
    cur_blk: List[str] = []
    for raw_ln in lines:
        ln = re.sub(r"^\s*[-*•]\s*", "", str(raw_ln or "")).strip()
        if not ln:
            continue
        if "|" in ln or "｜" in ln:
            if cur_blk:
                blocks.append(cur_blk)
                cur_blk = []
            blocks.append([ln])
            continue
        if _NPC_NAME_PREFIX_RE.match(ln):
            if cur_blk:
                blocks.append(cur_blk)
            cur_blk = [ln]
            continue
        if _NPC_ATTR_LINE_RE.match(ln):
            if not cur_blk:
                cur_blk = ["当前角色"]
            cur_blk.append(ln)
            continue
        if cur_blk:
            blocks.append(cur_blk)
        cur_blk = [ln]
    if cur_blk:
        blocks.append(cur_blk)

    out: List[tuple[str, List[str], bool]] = []
    for blk in blocks:
        joined = "\n".join(blk)
        is_ph = bool(_NPC_PLACEHOLDER_RE.search(joined))
        first_seg = re.split(r"[|｜]", blk[0])[0].strip()
        has_prefix = bool(_NPC_NAME_PREFIX_RE.match(first_seg))
        raw_name = _NPC_NAME_PREFIX_RE.sub("", first_seg).strip()
        if not has_prefix and not _NPC_ATTR_LINE_RE.match(first_seg) and (":" in raw_name or "：" in raw_name):
            raw_name = re.split(r"[:：]", raw_name, maxsplit=1)[0].strip()
        clean_name = re.sub(r"[(（\[【].*?[)）\]】]", "", raw_name).strip()
        if clean_name in ("当前角色", "未知", "未知人物", "无", "暂无"):
            clean_name = ""
        out.append((clean_name, blk, is_ph))
    return out


def _npc_keys_match(k1: str, k2: str) -> bool:
    if not k1 or not k2:
        return False
    if k1 == k2:
        return True
    parts1 = {p.strip() for p in re.split(r"[·•・/\-—\s]+", k1) if len(p.strip()) >= 2}
    parts2 = {p.strip() for p in re.split(r"[·•・/\-—\s]+", k2) if len(p.strip()) >= 2}
    if parts1 and parts2 and (parts1 & parts2):
        return True
    short_k, long_k = (k1, k2) if len(k1) <= len(k2) else (k2, k1)
    if len(short_k) >= 3 and short_k in long_k:
        return True
    return False


def _merge_npc_section_lines(cur_lines: List[str], hist_npc_sections: List[List[str]]) -> List[str]:
    hist_blocks: List[tuple[str, List[str]]] = []
    for h_lines in hist_npc_sections:
        for nk, b_lines, is_ph in _extract_npc_blocks(h_lines):
            if is_ph or not nk:
                continue
            updated = False
            for idx_b, (ex_nk, _) in enumerate(hist_blocks):
                if _npc_keys_match(nk, ex_nk):
                    hist_blocks[idx_b] = (nk, b_lines)
                    updated = True
                    break
            if not updated:
                hist_blocks.append((nk, b_lines))

    cur_parsed = _extract_npc_blocks(cur_lines)
    real_cur = [(nk, b_lines) for nk, b_lines, is_ph in cur_parsed if not is_ph]
    if real_cur:
        dedup_cur: List[tuple[str, List[str]]] = []
        for c_nk, c_lines in real_cur:
            replaced = False
            if c_nk:
                for idx_c, (ex_ck, _) in enumerate(dedup_cur):
                    if ex_ck and _npc_keys_match(c_nk, ex_ck):
                        dedup_cur[idx_c] = (c_nk, c_lines)
                        replaced = True
                        break
            if not replaced:
                dedup_cur.append((c_nk, c_lines))
        merged = list(dedup_cur)
        for h_nk, h_lines in hist_blocks:
            if not any(_npc_keys_match(h_nk, c_nk) for c_nk, _ in merged if c_nk):
                merged.append((h_nk, h_lines))
        return [ln for _, b_lines in merged for ln in b_lines]
    if hist_blocks:
        return [ln for _, b_lines in hist_blocks for ln in b_lines]
    return cur_lines


def _canon_kv_slot(line: str) -> str:
    m = re.match(r"^\s*[-*•]?\s*([^:：|｜(（]{1,14})\s*[:：]", str(line or ""))
    if not m:
        return ""
    raw_k = m.group(1).strip()
    return _KV_SLOT_ALIASES.get(raw_k, raw_k)


def _merge_kv_section_lines(cur_lines: List[str], prev_lines: List[str]) -> List[str]:
    if not cur_lines or not prev_lines:
        return cur_lines or prev_lines
    cur_slots = {_canon_kv_slot(ln) for ln in cur_lines if _canon_kv_slot(ln)}
    if not cur_slots:
        return cur_lines
    out = list(cur_lines)
    for p_ln in prev_lines:
        p_slot = _canon_kv_slot(p_ln)
        if p_slot and p_slot not in cur_slots:
            cur_slots.add(p_slot)
            out.append(p_ln)
    return out


def _extract_item_base_name(raw_item: str) -> str:
    s = re.sub(r"^\s*[-*•]\s*", "", str(raw_item or "")).strip()
    s = re.sub(r"[(（].*?[)）]", "", s)
    s = re.sub(r"\s*[xX×*]\s*\d+.*$", "", s)
    return s.strip()


def _merge_inventory_lines(cur_lines: List[str], prev_lines: List[str]) -> List[str]:
    explicit_wipe_re = re.compile(
        r"^\s*[-*•]?\s*(?:暂无(?:随身)?物品|暂无|无|空|背包为空|行囊为空|none|-)\s*$",
        re.I,
    )
    empty_re = re.compile(
        r"^\s*[-*•]?\s*(?:暂无(?:随身)?物品|暂无|无|空|背包为空|行囊为空|none|-|随身行囊\(基础随身物品\)x1)\s*$",
        re.I,
    )
    consumed_re = re.compile(
        r"(?:[xX×*]\s*0(?:\b|$)|(?:数量|剩余)\s*[:：]?\s*0\b|已消耗|已用尽|已用完|已丢弃|已损毁|已失去|已交出|已售出)"
    )
    non_blank_cur = [ln.strip() for ln in (cur_lines or []) if ln and ln.strip()]
    if non_blank_cur and all(bool(explicit_wipe_re.match(ln)) for ln in non_blank_cur):
        return ["暂无随身物品"]

    real_prev = [
        ln for ln in (prev_lines or [])
        if ln and ln.strip() and not empty_re.match(ln.strip()) and not consumed_re.search(ln)
    ]
    real_cur = [ln for ln in (cur_lines or []) if ln and ln.strip() and not empty_re.match(ln.strip())]
    if not real_prev:
        active_only = [ln for ln in real_cur if not consumed_re.search(ln)]
        return active_only if active_only else (["暂无随身物品"] if real_cur else cur_lines)
    if not real_cur:
        return real_prev

    cur_names = {_extract_item_base_name(ln) for ln in real_cur if _extract_item_base_name(ln)}
    active_cur = [ln for ln in real_cur if not consumed_re.search(ln)]
    out = list(active_cur)
    for p_ln in real_prev:
        p_name = _extract_item_base_name(p_ln)
        if p_name and p_name not in cur_names:
            cur_names.add(p_name)
            out.append(p_ln)
    return out if out else ["暂无随身物品"]


def _merge_and_complete_status_block(
    primary_status: str,
    patch_status: str,
    active_status_mods: List[Dict[str, Any]],
    history_messages: Optional[List[Dict[str, Any]]] = None,
) -> str:
    if not active_status_mods:
        return primary_status
    active_keys = [str(m.get("key") or "").strip() for m in active_status_mods if str(m.get("key") or "").strip()]
    pri_sec = _parse_status_sections(primary_status, active_keys)
    pat_sec = _parse_status_sections(patch_status, active_keys)
    prev_sec: Dict[str, List[str]] = {}
    hist_sec_by_key: Dict[str, List[List[str]]] = {}
    if history_messages:
        for h_msg in history_messages:
            if isinstance(h_msg, dict) and h_msg.get("role") == "assistant":
                h_parts = split_ai_message_modules(str(h_msg.get("content") or ""))
                if h_parts.get("status"):
                    parsed_h = _parse_status_sections(h_parts["status"], active_keys)
                    for hk, hlines in parsed_h.items():
                        clean_hlines = [x for x in hlines if x.strip()]
                        if clean_hlines:
                            prev_sec[hk] = clean_hlines
                            hist_sec_by_key.setdefault(hk, []).append(clean_hlines)

    out_blocks: List[str] = []
    used_keys = set()
    for m in active_status_mods:
        k = str(m.get("key") or "").strip()
        if not k:
            continue
        used_keys.add(k)
        m_type = str(m.get("type") or "")
        lines = [x for x in pri_sec.get(k, []) if x.strip()]
        if not lines:
            lines = [x for x in pat_sec.get(k, []) if x.strip()]
        if not lines:
            lines = [x for x in prev_sec.get(k, []) if x.strip()]
        elif prev_sec.get(k):
            if k == "角色关系" or m_type in ("npc_affinity", "relations"):
                lines = _merge_npc_section_lines(lines, hist_sec_by_key.get(k, [prev_sec[k]]))
            elif k in ("装备栏", "主角状态") or m_type in ("equipment_slots", "gear", "progress_stats"):
                lines = _merge_kv_section_lines(lines, prev_sec[k])
            elif k == "物品栏" or m_type in ("inventory_grid", "inventory"):
                lines = _merge_inventory_lines(lines, prev_sec[k])
        if not lines:
            lines = _default_fallback_status_lines(m)
        out_blocks.append(f"[{k}]\n" + "\n".join(lines))

    for extra_k, extra_lines in pri_sec.items():
        if extra_k not in used_keys and extra_k not in ("剧情正文", "正文", "行动选项") and extra_lines:
            out_blocks.append(f"[{extra_k}]\n" + "\n".join(extra_lines))

    return "<status>\n" + "\n\n".join(out_blocks) + "\n</status>"


def _deduplicate_choices_block(choices_text: str) -> str:
    """对提取出的行动选项块进行去重：当模型在 <status> 前后各输出了一遍 1.~4. 选项时，只保留唯一一组干净的提问与编号选项"""
    raw = str(choices_text or "").strip()
    if not raw:
        return ""
    if "<details" in raw.lower():
        m_det = re.search(r"<details[\s\S]*?</details>", raw, flags=re.I)
        if m_det:
            return m_det.group(0).strip()

    ask_hdr_re = re.compile(
        r"^\s*(?:#{1,6}\s*|\*\*|\*)?\s*(?:[\[【]\s*(?:#\d+\s*)?)?(?:[🎯🎬💡⚡🧭]\s*)?"
        r"(?:你打算怎么做|接下来你[^\n]{0,18}|你的选择|你的抉择|行动选项|行动推荐|可选行动|可采取的?行动|你决定怎么做|你要怎么做|现在你[^\n]{0,12}怎么做)"
        r"[^\n]*$",
        re.I,
    )
    opt_line_re = re.compile(
        r"^\s*(?:\*\*|\*)?\s*(?:([1-9])|([①②③④⑤⑥⑦⑧⑨])|([A-G]))[\.、．\)\s]\s*(.+)$",
        re.I,
    )
    bullet_opt_re = re.compile(r"^\s*[-*•]\s*(?:\*\*)?(?:[【\[].+)$")

    kept_lines: List[str] = []
    has_header = False
    seen_opt_nums: set = set()
    seen_opt_bodies: set = set()

    for raw_ln in raw.splitlines():
        ln = raw_ln.strip()
        if not ln or re.match(r"^(?:---|\*\*\*|___)$", ln):
            continue
        if ask_hdr_re.match(ln):
            if not has_header and not seen_opt_nums and not seen_opt_bodies:
                kept_lines.append("你打算怎么做？")
                has_header = True
            continue
        m_opt = opt_line_re.match(ln)
        if m_opt:
            num_key = (m_opt.group(1) or m_opt.group(2) or m_opt.group(3) or "").upper()
            body_norm = re.sub(r"\s+", "", m_opt.group(4)).strip("*_ ")
            if num_key in seen_opt_nums or (body_norm and body_norm in seen_opt_bodies):
                continue
            if num_key:
                seen_opt_nums.add(num_key)
            if body_norm:
                seen_opt_bodies.add(body_norm)
            kept_lines.append(ln)
            continue
        if bullet_opt_re.match(ln):
            body_norm = re.sub(r"^[-*•\s*_]+|\s+", "", ln)
            if body_norm in seen_opt_bodies:
                continue
            seen_opt_bodies.add(body_norm)
            kept_lines.append(ln)
            continue
        if ln not in kept_lines:
            kept_lines.append(ln)

    return "\n".join(kept_lines).strip()


_LOCAL_STOP_SEQUENCES: List[str] = [
    "<|im_end|>",
    "<|im_start|>",
    "<|endoftext|>",
    "\n【玩家行动】",
]


def _detect_and_trim_stream_loop(
    raw_text: str,
    is_trpg: bool = False,
    expect_choices: bool = False,
) -> Optional[str]:
    """实时检测流式生成中的复读死循环与回合越界自演：
    一旦命中（如单字刷屏、词组/句子/整段连续复读、跨段循环克隆、或跑团在完成 </status> + 1.~4. 选项后继续输出第二个 <status>/第二轮提问），
    立即返回裁剪后的干净文本，调用方收到非 None 返回值即可主动断开上游流以终止 GPU 无效推理。
    """
    if not raw_text or len(raw_text) < 48:
        return None

    # 0. 若当前仍处于未闭合的 <think> 块内部，检测思考块内部的死循环刷屏
    last_open_think = -1
    for m_op in re.finditer(r"(?<!`)<think(?:ing)?>(?!`)", raw_text, re.I):
        last_open_think = m_op.end()
    last_close_think = -1
    for m_cl in re.finditer(r"(?<!`)</think(?:ing)?>(?!`)", raw_text, re.I):
        last_close_think = m_cl.end()

    if last_open_think > last_close_think:
        think_tail = raw_text[last_open_think:]
        if len(think_tail) >= 160:
            last_ch = think_tail[-1]
            if not last_ch.isspace() and last_ch not in "-=_*" and think_tail.endswith(last_ch * 45):
                trimmed_t = think_tail.rstrip(last_ch) + (last_ch * 3)
                return raw_text[:last_open_think] + trimmed_t + "\n</think>\n\n"
            m_think_runon = re.search(r"[\u4e00-\u9fff]{110,}", think_tail[-450:])
            if m_think_runon:
                rel_s = len(think_tail) - len(think_tail[-450:]) + m_think_runon.start()
                return raw_text[:last_open_think + rel_s + 24].rstrip() + "\n</think>\n\n"
            t_win = think_tail[-1200:]
            max_tu = min(240, len(t_win) // 3)
            for u in range(6, max_tu + 1):
                unit = t_win[-u:]
                if len(unit.strip()) < 4:
                    continue
                need_k = 4 if u < 36 else 3
                if len(t_win) >= u * need_k and t_win.endswith(unit * need_k):
                    cut_pos = len(raw_text) - u * (need_k - 1)
                    while (
                        cut_pos >= last_open_think + 2 * u
                        and raw_text[cut_pos - u:cut_pos] == unit
                        and raw_text[cut_pos - 2 * u:cut_pos - u] == unit
                    ):
                        cut_pos -= u
                    return raw_text[:cut_pos].rstrip() + "\n</think>\n\n"
        return None

    body_offset = last_close_think if last_close_think > 0 else 0
    visible = raw_text[body_offset:]
    if len(visible) < 48:
        return None

    # 1. 跑团回合越界拦截：正文 + </status>（+ 1.~4. 选项）完整输出后，禁止开启第二个 <status> 或第二轮提问/自演
    if is_trpg:
        vis_norm = re.sub(r"＜/status＞|\[/status\]|</status_(?:panel|bar)>", "</status>", visible, flags=re.I)
        vis_norm = re.sub(r"＜status＞|\[status\]|<status_(?:panel|bar)>", "<status>", vis_norm, flags=re.I)
        m_first_open_st = re.search(r"<status(?:\s+[^>]*)?>", vis_norm, re.I)
        m_first_close_st = re.search(r"</status>", vis_norm, re.I)
        if m_first_open_st and m_first_close_st and m_first_close_st.start() > m_first_open_st.start():
            story_before_st = vis_norm[:m_first_open_st.start()].strip()
            after_close_idx = m_first_close_st.end()
            after_st = vis_norm[after_close_idx:]
            # 1a. 出现了第二个 <status> 标签（无论是否启用选项，只要首个状态栏前已有正文，第二个 <status> 必属越界重跑）
            m_second_st = re.search(r"<status(?:\s+[^>]*)?>", after_st, re.I)
            if m_second_st and len(story_before_st) >= 30:
                rel_cut = after_close_idx + m_second_st.start()
                clean_vis = re.sub(r"(?:\n\s*---+\s*|\n\s*#{1,4}\s*[^\n]*|\n\s*【[^】]{1,16}】\s*)$", "", vis_norm[:rel_cut]).rstrip()
                return raw_text[:body_offset] + clean_vis
            # 1b. 未启用选项模块时，</status> 闭合后若又继续生成超过 80 字的新剧情段落，直接截断在 </status>
            if not expect_choices and len(story_before_st) >= 60 and len(after_st.strip()) >= 80:
                clean_vis = vis_norm[:after_close_idx].rstrip()
                return raw_text[:body_offset] + clean_vis
            # 1c. 启用了选项模块且 1.~4. 四个选项均已换行落定，之后又开始输出第二轮“你打算怎么做”/玩家自演/新一轮 1. 选项
            if expect_choices and len(story_before_st) >= 40:
                has_1234 = all(
                    re.search(rf"(?:^|\n)\s*(?:\*\*|\*)?{n}[\.、．\)]\s*\S", after_st)
                    for n in (1, 2, 3, 4)
                )
                if has_1234:
                    m_opt4_line = re.search(r"(?:^|\n)\s*(?:\*\*|\*)?4[\.、．\)][^\n]+\n", after_st)
                    if m_opt4_line:
                        tail_after_opt4 = after_st[m_opt4_line.end():]
                        # 跳过可能存在的合法第 5~6 项，检测越界标志
                        m_runaway = re.search(
                            r"(?:^|\n)\s*(?:(?:#{1,4}\s*|\*\*|\*)?(?:你打算怎么做|接下来你打算|你的选择是|请做出你的选择)|"
                            r"【(?:玩家|剧情正文|新一轮|下一回合)|(?:玩家|你选择|Player)\s*[:：]|"
                            r"(?:\*\*|\*)?1[\.、．\)]\s*\S)",
                            tail_after_opt4,
                            re.I,
                        )
                        if m_runaway:
                            rel_cut = after_close_idx + m_opt4_line.end() + m_runaway.start()
                            clean_vis = vis_norm[:rel_cut].rstrip()
                            return raw_text[:body_offset] + clean_vis

    # 2. 尾部单字符刷屏死循环（排除 Markdown 分割线与空格缩进，连续 >= 42 个相同字符立即截断）
    last_ch = visible[-1]
    if not last_ch.isspace() and last_ch not in "-=_*#" and len(visible) >= 45 and visible.endswith(last_ch * 42):
        trimmed_vis = visible.rstrip(last_ch) + (last_ch * 3)
        return (raw_text[:body_offset] + trimmed_vis).rstrip()

    # 3. 尾部连续精确复读检测（支持 2~450 字的词组、句子、整段连续循环）
    tail = visible[-1800:]
    max_u = min(450, len(tail) // 2)
    for u in range(2, max_u + 1):
        unit = tail[-u:]
        u_stripped = unit.strip()
        if not u_stripped:
            continue
        if all(c in "-=_*| \t\r\n" for c in unit):
            continue
        if u <= 4:
            need_k = 8
            if len(u_stripped) < 2 or u * need_k < 24:
                continue
        elif u <= 8:
            need_k = 5
            if len(u_stripped) < 3 or u * need_k < 22:
                continue
        elif u <= 22:
            need_k = 4
            if len(u_stripped) < 6:
                continue
        elif u <= 79:
            need_k = 3
            if len(u_stripped) < 18:
                continue
        else:
            need_k = 2
            if len(u_stripped) < 55 or "<status" in unit.lower() or "</status>" in unit.lower():
                continue

        if len(tail) >= u * need_k and tail.endswith(unit * need_k):
            cut_pos = len(raw_text) - u * (need_k - 1)
            while (
                cut_pos >= body_offset + 2 * u
                and raw_text[cut_pos - u:cut_pos] == unit
                and raw_text[cut_pos - 2 * u:cut_pos - u] == unit
            ):
                cut_pos -= u
            return raw_text[:cut_pos].rstrip()

    # 4. 跨段克隆死循环检测（例如 A -> B -> A -> B 或同一 >=45 字长段落在正文中重复出现 >= 3 次）
    vis_no_st = re.sub(r"<status(?:\s+[^>]*)?>[\s\S]*$", "", visible, flags=re.I)
    if len(vis_no_st) >= 180:
        paras = [m for m in re.finditer(r"[^\n]{45,}", vis_no_st)]
        if len(paras) >= 3:
            seen_norm: Dict[str, List[re.Match]] = {}
            for pm in paras:
                norm_p = re.sub(r"[\s，。！？、：“”‘’\"'—…·,.!?:;\-()（）]+", "", pm.group(0))
                if len(norm_p) < 38:
                    continue
                seen_norm.setdefault(norm_p, []).append(pm)
                if len(seen_norm[norm_p]) >= 3:
                    # 保留第 1 次出现，从第 2 次重复起点前干净截断
                    second_match = seen_norm[norm_p][1]
                    return (raw_text[:body_offset] + visible[:second_match.start()]).rstrip()
            # 检测相邻双段 (P_a, P_b) 整体克隆重复：(P_{n-3}, P_{n-2}) == (P_{n-1}, P_n)
            if len(paras) >= 4:
                norms = [re.sub(r"\s+", "", pm.group(0)) for pm in paras[-4:]]
                if len(norms[0]) >= 40 and len(norms[1]) >= 40 and norms[0] == norms[2] and norms[1] == norms[3]:
                    dup_start = paras[-2].start()
                    return (raw_text[:body_offset] + visible[:dup_start]).rstrip()

    # 5. 标点丢失 + 近义词/成语词链无限堆砌死循环检测（根治超长上下文下模型连续输出上百个无标点汉字导致耗尽 max_tokens 并吞掉 </status>）
    vis_st_norm = re.sub(r"＜/status＞|\[/status\]|</status_(?:panel|bar)>", "</status>", visible, flags=re.I)
    vis_st_norm = re.sub(r"＜status＞|\[status\]|<status_(?:panel|bar)>", "<status>", vis_st_norm, flags=re.I)
    m_st_open_live = re.search(r"<status(?:\s+[^>]*)?>", vis_st_norm, re.I)
    m_st_close_live = re.search(r"</status>", vis_st_norm, re.I)
    if m_st_open_live and (not m_st_close_live or m_st_close_live.start() < m_st_open_live.start()):
        st_live_body = visible[m_st_open_live.end():]
        m_st_cjk_runon = re.search(r"[\u4e00-\u9fff]{52,}", st_live_body)
        if m_st_cjk_runon:
            cut_vis = visible[:m_st_open_live.end() + m_st_cjk_runon.start() + 16]
            last_ln = cut_vis.rsplit("\n", 1)[-1]
            if last_ln.count("(") > last_ln.count(")"):
                cut_vis += ")" * (last_ln.count("(") - last_ln.count(")"))
            if last_ln.count("（") > last_ln.count("）"):
                cut_vis += "）" * (last_ln.count("（") - last_ln.count("）"))
            return raw_text[:body_offset] + cut_vis.rstrip() + "\n</status>"
        last_st_line = st_live_body.rsplit("\n", 1)[-1]
        if "|" not in last_st_line and "｜" not in last_st_line and len(last_st_line) >= 280:
            cut_vis = visible[:len(visible) - len(last_st_line) + 96].rstrip("，、,;； ")
            last_ln = cut_vis.rsplit("\n", 1)[-1]
            if last_ln.count("(") > last_ln.count(")"):
                cut_vis += ")" * (last_ln.count("(") - last_ln.count(")"))
            if last_ln.count("（") > last_ln.count("）"):
                cut_vis += "）" * (last_ln.count("（") - last_ln.count("）"))
            return raw_text[:body_offset] + cut_vis.rstrip() + "\n</status>"
    else:
        tail_body_chk = vis_no_st[-450:] if vis_no_st else ""
        m_body_cjk_runon = re.search(r"[\u4e00-\u9fff]{96,}", tail_body_chk)
        if m_body_cjk_runon:
            rel_body_cut = len(vis_no_st) - len(tail_body_chk) + m_body_cjk_runon.start() + 28
            return (raw_text[:body_offset] + vis_no_st[:rel_body_cut]).rstrip() + "。"

    return None


def split_ai_message_modules(raw_text: str, active_status_keys: Optional[List[str]] = None) -> Dict[str, str]:
    """将 AI 回复按模块化架构拆解为 4 个独立模块：think (思考模块)、story (正文模块)、status (状态栏模块)、choices (选项模块)"""
    working = str(raw_text or "").strip()
    if not working:
        return {"think": "", "story": "", "status": "", "choices": ""}

    working = re.sub(r"</?(?:story|narrative|text|system|user|assistant|output|response)\s*>", "", working, flags=re.I).strip()

    # 1. 提取 <think>...</think> 思考模块（仅当非反引号包裹的 </think> 后仍存在正文时才把无开标签的前缀当思考过程，防止误删正文）
    think_blocks: List[str] = []
    m_unmatched_close = re.search(r"(?<!`)</think(?:ing)?>(?!`)", working, re.I)
    m_first_open = re.search(r"(?<!`)<think(?:ing)?>(?!`)", working, re.I)
    if m_unmatched_close and (not m_first_open or m_unmatched_close.start() < m_first_open.start()):
        after_unmatched = working[m_unmatched_close.end():].lstrip()
        if _has_narrative_outside_status(after_unmatched):
            working = "<think>\n" + working
        else:
            working = re.sub(r"(?<!`)</?think(?:ing)?>(?!`)", "", working, flags=re.I)

    def _extract_think(m: re.Match) -> str:
        think_blocks.append(m.group(0).strip())
        return "\n"

    _real_think_pair_re = r"(?<!`)<think(?:ing)?>(?!`)[\s\S]*?(?<!`)</think(?:ing)?>(?!`)"
    if re.search(_real_think_pair_re, working, re.I):
        cand_after_think = re.sub(_real_think_pair_re + r"\s*", "", working, flags=re.I).strip()
        if cand_after_think and (_has_narrative_outside_status(cand_after_think) or not _has_narrative_outside_status(working)):
            working = re.sub(_real_think_pair_re, _extract_think, working, flags=re.I).strip()
        else:
            working = re.sub(r"(?<!`)</?think(?:ing)?>(?!`)", "", working, flags=re.I).strip()

    # 2. 提取 <status>...</status> 状态栏模块（优先于选项拆分，确保即使 <status> 位于选项下方或被包裹在代码块/未闭合围栏中也绝不被误删）
    working = re.sub(r"＜status＞|\[status\]|<status_(?:panel|bar)>", "<status>", working, flags=re.I)
    working = re.sub(r"＜/status＞|\[/status\]|</status_(?:panel|bar)>", "</status>", working, flags=re.I)
    working = re.sub(
        r"```(?:xml|html|text|markdown|status)?\s*(<status(?:\s+[^>]*)?>[\s\S]*?</status>)\s*```",
        r"\1",
        working,
        flags=re.I,
    )
    working = re.sub(
        r"```(?:xml|html|text|markdown|status)?\s*(<status(?:\s+[^>]*)?>[\s\S]*?)(?:\s*```|$)",
        r"\1",
        working,
        flags=re.I,
    )

    status_inners: List[str] = []
    hoisted_story_from_status: List[str] = []

    def _extract_status(m: re.Match) -> str:
        raw_st = m.group(0).strip()
        inner_st = re.sub(r"^\s*<status(?:\s+[^>]*)?>\s*|\s*</status>\s*$", "", raw_st, flags=re.I)
        inner_st = re.sub(r"\s*```\s*$", "", inner_st).strip()
        hdr_re = re.compile(
            r"^\s*(?:[-*•]\s*)?(?:#{1,6}\s*|\*\*|\*)?\s*(?:(?:#?\d+|[①-⑩])[\.、\s]*)?[\[【]\s*(?:(?:#?\d+|[①-⑩])[\.、\s]*)?([^\]】\n]+?)\s*[\]】]\s*[:：]?\s*(?:\*\*|\*)?\s*[:：]?\s*(.*)$"
        )
        kept_lines: List[str] = []
        in_story_sec = False
        for s_ln in inner_st.splitlines():
            m_sh = hdr_re.match(s_ln.strip())
            if m_sh:
                sec_t = re.sub(r"^[📊⚔️🎒💕📋🏷️🧩📖🧠🎯📝💭⚡#\d①-⑩\.、\s*]+|\*+$", "", m_sh.group(1)).strip()
                if sec_t in ("剧情正文", "正文", "正文栏", "剧情正文栏", "主线叙事"):
                    in_story_sec = True
                    rest_story = m_sh.group(2).strip()
                    if rest_story:
                        hoisted_story_from_status.append(rest_story)
                    continue
                else:
                    in_story_sec = False
            if in_story_sec:
                if s_ln.strip():
                    hoisted_story_from_status.append(s_ln.strip())
            else:
                kept_lines.append(s_ln)
        clean_inner = "\n".join(kept_lines).strip()
        if clean_inner:
            status_inners.append(clean_inner)
        return "\n"

    working = re.sub(r"<status(?:\s+[^>]*)?>[\s\S]*?</status>", _extract_status, working, flags=re.I).strip()
    if re.search(r"<status(?:\s+[^>]*)?>", working, re.I) and not re.search(r"</status>", working, re.I):
        working = re.sub(r"<status(?:\s+[^>]*)?>[\s\S]*$", _extract_status, working, flags=re.I).strip()
    if hoisted_story_from_status and not working.strip():
        working = "\n\n".join(hoisted_story_from_status).strip()

    if not status_inners:
        w_lines = working.splitlines()
        bare_hdr_re = re.compile(
            r"^\s*(?:[-*•]\s*)?(?:#{1,6}\s*|\*\*|\*)?\s*(?:(?:#?\d+|[①-⑩])[\.、\s]*)?[\[【]\s*(?:(?:#?\d+|[①-⑩])[\.、\s]*)?([^\]】\n]+?)\s*[\]】]\s*[:：]?\s*(?:\*\*|\*)?\s*[:：]?\s*(.*)$"
        )
        custom_key_set = {str(k).strip().lower() for k in (active_status_keys or []) if str(k).strip()}
        stat_title_re = re.compile(
            r"^(?:主角状态|角色状态|个人状态|自身状态|当前状态|状态栏|状态面板|属性栏|装备栏|装备|穿戴装备|身体装备|义体|身体栏|身体状态|物品栏|物品|随身物品|背包|背包栏|行囊|道具栏|角色关系|好感|好感度|好感栏|人物关系|人际关系|在场人物|周围人物|情报卡|情报栏|世界新闻|任务目标|当前任务|剧情进度|NPC|NPC关系|NPC信息|系统面板)$",
            re.I,
        )
        choice_hdr_re = re.compile(r"^(?:行动选项|可选行动|行动推荐|行动选择|你的选择|你的抉择|选项)(?:栏|模块)?$", re.I)
        opt_num_re = re.compile(r"^\s*(?:\*\*|\*)?(?:[1-9]|[①-⑨]|[A-G])[\.、．\)]\s*\S", re.I)
        st_start = -1
        for idx_l, ln in enumerate(w_lines):
            m_b = bare_hdr_re.match(ln)
            if m_b:
                t_clean = re.sub(r"^[📊⚔️🎒💕📋🏷️🧩📖🧠🎯📝💭⚡#\d①-⑩\.、\s*]+|\*+$", "", m_b.group(1)).strip()
                if stat_title_re.match(t_clean) or (t_clean.lower() in custom_key_set):
                    st_start = idx_l
                    break
        if st_start != -1:
            st_end = len(w_lines)
            for idx_l in range(st_start + 1, len(w_lines)):
                ln_s = w_lines[idx_l].strip()
                m_b = bare_hdr_re.match(ln_s)
                if m_b:
                    t_clean = re.sub(r"^[📊⚔️🎒💕📋🏷️🧩📖🧠🎯📝💭⚡#\d①-⑩\.、\s*]+|\*+$", "", m_b.group(1)).strip()
                    if choice_hdr_re.match(t_clean):
                        st_end = idx_l
                        break
                if re.match(
                    r"^(?:#{1,6}\s*|\*\*|\*)?\s*(?:[🎯🎬💡⚡🧭]\s*)?(?:你打算怎么做|接下来你[^\n]{0,18}|你的选择|你的抉择|你决定怎么做|你要怎么做|现在你[^\n]{0,12}怎么做)[？?：:\s]*(?:\*\*|\*)?$",
                    ln_s,
                    re.I,
                ):
                    st_end = idx_l
                    break
                # 若未写提问语直接进入 1. xxx / 2. xxx 行动选项列表，也在选项起点处截断状态栏
                if re.match(r"^\s*(?:\*\*|\*)?(?:1|①|A)[\.、．\)]\s*\S", ln_s, re.I):
                    has_second_opt = any(
                        opt_num_re.match(w_lines[k].strip())
                        for k in range(idx_l + 1, min(len(w_lines), idx_l + 4))
                    )
                    if has_second_opt:
                        st_end = idx_l
                        break
            extracted_st_lines = []
            for ln in w_lines[st_start:st_end]:
                m_b = bare_hdr_re.match(ln)
                if m_b:
                    t_clean = re.sub(r"^[📊⚔️🎒💕📋🏷️🧩📖🧠🎯📝💭⚡#\d①-⑩\.、\s*]+|\*+$", "", m_b.group(1)).strip()
                    rest_s = m_b.group(2).strip()
                    extracted_st_lines.append(f"[{t_clean}]" + (f" {rest_s}" if rest_s else ""))
                else:
                    extracted_st_lines.append(ln)
            extracted_st = "\n".join(extracted_st_lines).strip()
            if extracted_st:
                status_inners.append(extracted_st)
                before_l = w_lines[:st_start]
                after_l = w_lines[st_end:]
                after_txt = "\n".join(after_l)
                if re.search(r"(?:^|\n)\s*1[\.、．\)]\s*\S", after_txt) and re.search(r"(?:^|\n)\s*2[\.、．\)]\s*\S", after_txt):
                    while before_l and not before_l[-1].strip():
                        before_l.pop()
                    while before_l and re.match(r"^\s*[1-9][\.、．\)]\s*\S", before_l[-1]):
                        before_l.pop()
                working = ("\n".join(before_l) + "\n\n" + after_txt).strip()

    working = re.sub(
        r"^[ \t]*(?:#{1,6}[ \t]*|\*\*)*[ \t]*(?:[①②③④1-9][\.、．\s]*)?(?:[\[【][ \t]*(?:#\d+[ \t]*)?)?(?:[📖📝📊][ \t]*)?(?:剧情正文|正文栏|剧情正文栏|剧情正文模块)(?:[ \t]*[\]】])?[ \t]*(?:\*\*)*[ \t]*[:：]?[ \t]*\n*",
        "",
        working,
        flags=re.I | re.M
    ).strip()

    # 清理残余的尾部重复空提问行（如模型在 <status> 后多写了一句单独的“你打算怎么做？”）
    working = re.sub(
        r"(?:\n\s*(?:---|\*\*\*|___)\s*)*\n\s*(?:#{1,6}\s*|\*\*|\*)?\s*(?:[🎯🎬💡⚡🧭]\s*)?(?:你打算怎么做|接下来你打算怎么做|你的选择|你的抉择)[？?：:\s]*(?:\*\*|\*)?\s*$",
        "",
        working,
        flags=re.I
    ).strip()

    # 3. 从剩余内容（正文 + 选项）中精准剥离末尾的【选项模块】，并彻底去重
    choice_pattern = re.compile(
        r"(?:(?:\n|^)\s*(?:---|\*\*\*|___)\s*)?"
        r"(?:"
        r"(?:\n|^)\s*<details[^>]*>\s*<summary[^>]*>[^<]*(?:行动|选项|推荐|抉择|分支|选择|choice|action|option)[\s\S]*?</details>\s*$"
        r"|"
        r"(?:\n|^)\s*(?:#{1,6}\s*|\*\*|\*)?\s*(?:[\[【]\s*(?:#\d+\s*)?)?(?:[🎯🎬💡⚡🧭]\s*)?(?:你打算怎么做|接下来你[^\n]{0,18}|你的选择|你的抉择|行动选项|行动推荐|可选行动|可采取的?行动|你决定怎么做|你要怎么做|现在你[^\n]{0,12}怎么做)[^\n]*\n[\s\S]*$"
        r"|"
        r"(?:\n|^)(?:\s*(?:(?:\*\*|\*)?(?:[1-4]|①|②|③|④|[A-D])[\.、．\)\s]|[-*•]\s*(?:\*\*)?[【\[])[^\n]+(?:\n|$)){2,}[\s\S]*$"
        r")",
        re.I
    )
    collected_choice_chunks: List[str] = []
    story_body = working
    while True:
        m_choice = choice_pattern.search(story_body)
        if not m_choice:
            break
        chunk = re.sub(r"^(?:---|\*\*\*|___)\s*\n*", "", m_choice.group(0).strip()).strip()
        if chunk:
            collected_choice_chunks.insert(0, chunk)
        story_body = story_body[:m_choice.start()].strip()

    choices_body = _deduplicate_choices_block("\n".join(collected_choice_chunks))

    story_body = re.sub(r"(?:\n\s*(?:---|\*\*\*|___)\s*)+$", "", story_body).strip()
    story_body = re.sub(
        r"\n\s*(?:#{1,6}\s*|\*\*|\*)?\s*(?:[🎯🎬💡⚡🧭]\s*)?(?:你打算怎么做|接下来你打算怎么做|你的选择|你的抉择)[？?：:\s]*(?:\*\*|\*)?\s*$",
        "",
        story_body,
        flags=re.I
    ).strip()

    merged_status_str = f"<status>\n{chr(10) + chr(10) if len(status_inners) > 1 else ''}".join([])
    if status_inners:
        merged_status_str = "<status>\n" + "\n\n".join(status_inners) + "\n</status>"
    else:
        merged_status_str = ""

    return {
        "think": "\n\n".join(think_blocks).strip(),
        "story": story_body,
        "status": merged_status_str,
        "choices": choices_body
    }


def assemble_ai_message_modules(think: str, story: str, status: str, choices: str) -> str:
    """按标准模块顺序重组 AI 消息：思考模块 -> 正文模块 -> 状态栏模块 -> 选项模块"""
    parts = [p.strip() for p in (think, story, status, choices) if p and p.strip()]
    return "\n\n".join(parts)


@app.post("/api/ai/reroll_choices")
async def reroll_choices(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    """模块化重生成选项：严格保持思考过程、正文与 <status> 状态栏不变，删除旧选项模块并重新生成 4 个全新行动选项"""
    chat_id = sanitize_id(str(payload.get("chat_id") or ""))
    if chat_id in ACTIVE_BG_TASKS:
        raise HTTPException(status_code=409, detail="正在生成中")

    target_msg_id = str(payload.get("msg_id") or "").strip()
    chat_file = get_user_chats_dir(username) / f"{chat_id}.json"
    if not chat_file.exists():
        raise HTTPException(status_code=404, detail="对话不存在")

    with open(chat_file, "r", encoding="utf-8") as f:
        chat_data = json.load(f)

    messages = chat_data.get("messages") or []
    target_msg = None
    if target_msg_id:
        for m in reversed(messages):
            if m.get("role") == "assistant" and str(m.get("id") or "") == target_msg_id:
                target_msg = m
                break
    if not target_msg:
        for m in reversed(messages):
            if m.get("role") == "assistant":
                target_msg = m
                break

    if not target_msg:
        raise HTTPException(status_code=400, detail="暂无 AI 回复")

    raw_full_content = str(target_msg.get("content") or payload.get("current_content") or "").strip()
    mods = split_ai_message_modules(raw_full_content)
    think_part = mods["think"]
    story_part = mods["story"]
    status_part = mods["status"]
    old_choices_part = mods["choices"] or "（原回复未包含标准编号选项）"

    settings = load_user_settings(username)
    model_id = str(payload.get("model") or chat_data.get("model") or settings.get("model") or "").strip()
    if not model_id:
        raise HTTPException(status_code=400, detail="请先选择模型")

    ep = resolve_model_endpoint(model_id, settings)
    if ep["is_local"]:
        local_err = await ensure_local_engine_ready(model_id)
        ep = resolve_model_endpoint(model_id, settings)
        if local_err:
            raise HTTPException(status_code=502, detail=local_err)

    proj_id = sanitize_id(str(payload.get("project_id") or chat_data.get("project_id") or "proj_default"))
    proj_file = get_user_projects_dir(username) / f"{proj_id}.json"
    proj_data: Dict[str, Any] = {}
    if proj_file.exists():
        try:
            with open(proj_file, "r", encoding="utf-8") as pf:
                proj_data = json.load(pf)
        except Exception:
            proj_data = {}
    ui_mods = normalize_ui_modules(proj_data.get("ui_modules"))
    choices_mod = next((m for m in ui_mods if m.get("type") == "action_choices" or m.get("id") == "mod_choices"), None)
    custom_choices_rule = str(choices_mod.get("fields") or "").strip() if choices_mod else ""
    choices_title = str(choices_mod.get("key") or "行动选项").strip() if choices_mod else "行动选项"

    rule_block = (
        f"3. 必须严格遵循玩家在【{choices_title}模块】中自定义的生成规范：\n   {custom_choices_rule}\n"
        if custom_choices_rule
        else (
            "3. 必须严格按以下 4 个维度输出编号 `1.` ~ `4.`：\n"
            "   - 1. 【稳健/交涉】：全新的沟通话术、心理试探或细节观察角度（不挂检定）；\n"
            "   - 2. 【博弈/险招】：果断出手、威慑施压或高风险高回报行动（句尾附带 `【🎲对应技能检定】`）；\n"
            "   - 3. 【环境/道具破局】：巧妙利用当前场景中的地形细节、机关光影或【状态栏】物品栏里的现有道具破局；\n"
            "   - 4. 【逆反/鬼点子】：出人意料的非常规骚操作、反向设局或打破常规的戏剧性举动。"
        )
    )

    sys_prompt = (
        "你是一位极具想象力的互动叙事导演。当前我们采用【万物模块化输出架构】，正文模块与状态栏模块已经固定锁定。\n"
        f"请阅读刚刚发生的【正文模块】与【状态栏模块】，为玩家重新生成【{choices_title}模块】（与旧选项截然不同、脑洞大开且极具戏剧张力的全新行动选项）。\n"
        "【严格输出铁律】：\n"
        "1. 只允许输出【选项模块】（第一行输出 `你打算怎么做？`，紧接着输出编号选项）；\n"
        "2. 严禁重复任何正文剧情、严禁输出 `<status>` 状态栏、严禁输出任何寒暄或解释！\n"
        f"{rule_block}"
    )
    status_ctx = f"\n\n【当前状态栏模块（保持不变，供构思道具/状态相关选项参考）】：\n{status_part}" if status_part else ""
    user_prompt = (
        f"【当前正文模块片段（保持不变）】：\n{story_part[-2400:]}{status_ctx}\n\n"
        f"【已删除的旧选项模块（严禁雷同或换汤不换药）】：\n{old_choices_part}\n\n"
        f"请直接输出全新的【{choices_title}模块】（以“你打算怎么做？”开头，紧跟编号选项）："
    )

    read_timeout = 180.0 if ep["is_local"] else 45.0
    req_json: Dict[str, Any] = {
        "model": ep["upstream_model"],
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.85,
        "top_p": 0.92,
        "max_tokens": 1024,
        "stream": True
    }
    if ep.get("protocol") not in ("claude", "gemini"):
        req_json["presence_penalty"] = 0.35
    if ep["is_local"]:
        req_json["stop"] = list(_LOCAL_STOP_SEQUENCES)
        if ep["engine"] == "strata":
            req_json["reasoning_effort"] = "none"
            req_json["reasoning_budget_tokens"] = 0
            req_json["chat_template_kwargs"] = {"enable_thinking": False}
            req_json["repetition_penalty"] = 1.08
            req_json["penalty_last_n"] = 512
        elif ep["engine"] == "ollama":
            req_json["think"] = False
            req_json["reasoning_effort"] = "none"
            req_json["thinking_budget_tokens"] = 0
            req_json["reasoning_budget"] = 0
            req_json["reasoning_budget_tokens"] = 0
            req_json["chat_template_kwargs"] = {"enable_thinking": False}
            req_json["options"] = {
                "repeat_penalty": 1.08,
                "num_predict": 1024,
                "num_ctx": get_optimal_ollama_num_ctx(model_id, settings, min_ctx=8192),
            }

    new_choices_text = ""
    proxy_candidates = [ep["proxy"], None] if ep["proxy"] else [None]
    req_headers = ep.get("headers") or {"Authorization": f"Bearer {ep['api_key']}", "Content-Type": "application/json"}

    for cur_proxy in proxy_candidates:
        try:
            collected_pieces: List[str] = []
            async with httpx.AsyncClient(proxy=cur_proxy, trust_env=False, timeout=httpx.Timeout(read_timeout, connect=10.0)) as client:
                async with client.stream(
                    "POST",
                    f"{ep['base_url']}/chat/completions",
                    headers=req_headers,
                    json=req_json
                ) as resp:
                    if resp.status_code != 200:
                        continue
                    ctype = (resp.headers.get("content-type") or "").lower()
                    if "text/event-stream" not in ctype:
                        raw_bytes = await resp.aread()
                        rj = json.loads(raw_bytes.decode("utf-8", errors="ignore"))
                        raw_c = rj.get("choices", [{}])[0].get("message", {}).get("content", "")
                        if raw_c:
                            collected_pieces.append(raw_c)
                    else:
                        in_reasoning = False
                        async for line in resp.aiter_lines():
                            line = line.strip()
                            if not line:
                                continue
                            if line.startswith("data:"):
                                raw_data = line[5:].lstrip()
                                if raw_data == "[DONE]":
                                    continue
                                try:
                                    d = json.loads(raw_data)
                                    delta = d.get("choices", [{}])[0].get("delta", {})
                                    r_piece = delta.get("reasoning_content") or delta.get("reasoning") or ""
                                    c_piece = delta.get("content") or ""
                                    if r_piece and not in_reasoning:
                                        in_reasoning = True
                                    if c_piece:
                                        if in_reasoning:
                                            in_reasoning = False
                                        collected_pieces.append(c_piece)
                                except Exception:
                                    continue
            if collected_pieces:
                raw_joined = "".join(collected_pieces)
                if re.search(r"(?<!`)</think(?:ing)?>(?!`)", raw_joined, re.I) and not re.search(r"(?<!`)<think(?:ing)?>(?!`)", raw_joined, re.I):
                    raw_joined = "<think>\n" + raw_joined
                cleaned_choices = strip_thinking_blocks(raw_joined).strip()
                # 防御性剥离：万一模型违背指令在选项里夹带了 <status>，将其剔除，绝不污染原状态栏
                cleaned_choices = re.sub(r"<status>[\s\S]*?</status>", "", cleaned_choices, flags=re.I).strip()
                cleaned_choices = re.sub(r"^(?:---|\*\*\*|___)\s*\n*", "", cleaned_choices).strip()
                if cleaned_choices:
                    new_choices_text = cleaned_choices
                    break
        except Exception:
            continue

    if not new_choices_text:
        raise HTTPException(status_code=500, detail="生成失败，请重试")

    first_line = new_choices_text.splitlines()[0] if new_choices_text.splitlines() else ""
    if not re.search(r"你打算怎么做|接下来你|你的选择|你的抉择|行动选项|可选行动", first_line):
        new_choices_text = "你打算怎么做？\n\n" + new_choices_text

    updated_content = assemble_ai_message_modules(think_part, story_part, status_part, new_choices_text)
    target_msg["content"] = updated_content
    chat_data["updated_at"] = time.time()
    # 生成选项期间对话文件可能已变化：加锁重新读取最新文件，仅替换目标消息内容，避免覆盖期间新增的消息
    async with _get_chat_lock(chat_id):
        try:
            with open(chat_file, "r", encoding="utf-8") as f:
                fresh_chat = json.load(f)
            target_id = str(target_msg.get("id") or "")
            patched = False
            if isinstance(fresh_chat, dict) and target_id:
                for m in (fresh_chat.get("messages") or []):
                    if isinstance(m, dict) and str(m.get("id") or "") == target_id:
                        m["content"] = updated_content
                        patched = True
                        break
            if patched:
                fresh_chat["updated_at"] = time.time()
                chat_data = fresh_chat
        except Exception:
            pass
        atomic_write_json(chat_file, chat_data, ensure_ascii=False, indent=2)

    return {
        "status": "ok",
        "msg_id": target_msg.get("id"),
        "updated_content": updated_content,
        "new_choices": new_choices_text
    }


# ==================== 全量/勾选数据一键导出与从文件夹导入 ====================
BACKUP_ROOT_DIR = BASE_DIR / "backups"
BACKUP_ROOT_DIR.mkdir(parents=True, exist_ok=True)

@app.get("/api/backup/overview")
def get_backup_overview(username: str = Depends(get_current_user)):
    udir = get_user_dir(username)
    projects_dir = get_user_projects_dir(username)
    chats_dir = get_user_chats_dir(username)
    gallery_dir = get_user_gallery_dir(username)
    presets_dir = get_user_presets_dir(username)

    projects_list = []
    for pf in sorted(projects_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            with open(pf, "r", encoding="utf-8") as f:
                pd = json.load(f)
            projects_list.append({
                "id": pd.get("id") or pf.stem,
                "name": pd.get("name") or pf.stem,
                "icon": pd.get("icon") or pd.get("avatar") or ""
            })
        except Exception:
            pass

    chats_list = []
    logs_count = 0
    for cf in sorted(chats_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            with open(cf, "r", encoding="utf-8") as f:
                cd = json.load(f)
            if cd.get("last_prompt_log"):
                logs_count += 1
            chats_list.append({
                "id": cd.get("id") or cf.stem,
                "title": cd.get("title") or cf.stem,
                "project_id": cd.get("project_id") or "proj_default",
                "msg_count": len(cd.get("messages") or []),
                "updated_at": cd.get("updated_at") or cf.stat().st_mtime
            })
        except Exception:
            pass

    img_files = [p for p in gallery_dir.glob("*.*") if p.is_file()] if gallery_dir.exists() else []
    preset_files = list(presets_dir.glob("*.json")) if presets_dir.exists() else []
    default_dir = str(BACKUP_ROOT_DIR / time.strftime("backup_%Y%m%d_%H%M%S"))

    return {
        "default_export_dir": default_dir,
        "backup_root_dir": str(BACKUP_ROOT_DIR),
        "projects": projects_list,
        "chats": chats_list,
        "gallery_count": len(img_files),
        "presets_count": len(preset_files),
        "logs_count": logs_count
    }

@app.post("/api/backup/pick-folder", dependencies=[Depends(require_loopback)])
async def pick_backup_folder(payload: Dict[str, Any] = {}, username: str = Depends(get_current_user)):
    initial_dir = str(payload.get("initial_dir") or BACKUP_ROOT_DIR)
    if not os.path.exists(initial_dir):
        initial_dir = str(BACKUP_ROOT_DIR)
    title_str = str(payload.get("title") or "选择文件夹")

    def _open_dialog():
        # 全局互斥锁：防止多次点击同时弹出多个系统对话框
        with _NATIVE_PICKER_LOCK:
            tk_ok = False
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                chosen = filedialog.askdirectory(initialdir=initial_dir, title=title_str, parent=root)
                tk_ok = True
                try:
                    root.destroy()
                except Exception:
                    pass
                return chosen or ""
            except Exception as e:
                if not tk_ok:
                    print(f"tkinter 文件夹选择器不可用，回退 PowerShell 原生对话框: {e}")
            if tk_ok:
                return ""
            # 整合包内置的嵌入式 Python 不含 tkinter：回退到 PowerShell WinForms 原生文件夹选择器
            try:
                return _native_pick_path_powershell("folder", title_str) or ""
            except Exception as e:
                print(f"打开文件夹选择器异常: {e}")
                return ""

    selected = await asyncio.to_thread(_open_dialog)
    return {"folder_path": os.path.normpath(selected) if selected else ""}

@app.post("/api/backup/open-folder", dependencies=[Depends(require_loopback)])
def open_backup_folder(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    folder_path = str(payload.get("folder_path") or "").strip()
    if not folder_path:
        folder_path = str(BACKUP_ROOT_DIR)
    target = Path(folder_path)
    target.mkdir(parents=True, exist_ok=True)
    if not open_directory_safely(target):
        raise HTTPException(status_code=500, detail=f"打开文件夹失败（无桌面环境或系统管理器不可用）: {target}")
    return {"status": "ok", "folder_path": str(target)}

@app.post("/api/backup/export-folder", dependencies=[Depends(require_loopback)])
def export_to_folder(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    raw_target = str(payload.get("target_dir") or "").strip()
    if not raw_target:
        out_dir = BACKUP_ROOT_DIR / time.strftime("backup_%Y%m%d_%H%M%S")
    else:
        out_dir = Path(raw_target).expanduser().resolve()

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法创建文件夹 ({out_dir}): {e}")

    inc_projects = bool(payload.get("include_projects", True))
    inc_chats = bool(payload.get("include_chats", True))
    inc_settings = bool(payload.get("include_settings", True))
    inc_gallery = bool(payload.get("include_gallery", True))
    inc_logs = bool(payload.get("include_logs", True))

    sel_project_ids = set(payload.get("project_ids") or [])
    sel_chat_ids = set(payload.get("chat_ids") or [])

    udir = get_user_dir(username)
    projects_dir = get_user_projects_dir(username)
    chats_dir = get_user_chats_dir(username)
    gallery_dir = get_user_gallery_dir(username)
    presets_dir = get_user_presets_dir(username)

    stats = {
        "projects": 0,
        "chats": 0,
        "settings": 0,
        "presets": 0,
        "images": 0,
        "logs": 0
    }

    # 1. 导出游戏设定 (projects)
    if inc_projects and projects_dir.exists():
        dst_proj = out_dir / "projects"
        dst_proj.mkdir(parents=True, exist_ok=True)
        for pf in projects_dir.glob("*.json"):
            try:
                with open(pf, "r", encoding="utf-8") as f:
                    pd = json.load(f)
                pid = pd.get("id") or pf.stem
                if sel_project_ids and pid not in sel_project_ids and pf.stem not in sel_project_ids:
                    continue
                shutil.copy2(pf, dst_proj / pf.name)
                stats["projects"] += 1
            except Exception:
                pass

    # 2. 导出游戏对话记录 (chats)
    collected_prompt_logs = []
    if (inc_chats or inc_logs) and chats_dir.exists():
        if inc_chats:
            dst_chats = out_dir / "chats"
            dst_chats.mkdir(parents=True, exist_ok=True)
        for cf in chats_dir.glob("*.json"):
            try:
                with open(cf, "r", encoding="utf-8") as f:
                    cd = json.load(f)
                cid = cd.get("id") or cf.stem
                if inc_chats:
                    if not sel_chat_ids or cid in sel_chat_ids or cf.stem in sel_chat_ids:
                        shutil.copy2(cf, out_dir / "chats" / cf.name)
                        stats["chats"] += 1
                if inc_logs and cd.get("last_prompt_log"):
                    collected_prompt_logs.append({
                        "chat_id": cid,
                        "chat_title": cd.get("title") or cid,
                        "project_id": cd.get("project_id") or "proj_default",
                        "updated_at": cd.get("updated_at"),
                        "prompt_log": cd.get("last_prompt_log")
                    })
            except Exception:
                pass

    # 3. 导出全局设置、参数预设与角色卡库 (settings, presets & character_cards)
    if inc_settings or inc_projects:
        cc_file = udir / "character_cards.json"
        if cc_file.exists():
            shutil.copy2(cc_file, out_dir / "character_cards.json")

    if inc_settings:
        dst_settings = out_dir / "settings"
        dst_settings.mkdir(parents=True, exist_ok=True)
        sfile = get_user_settings_file(username)
        if sfile.exists():
            shutil.copy2(sfile, dst_settings / "settings.json")
            stats["settings"] += 1
        if presets_dir.exists():
            dst_presets = out_dir / "presets"
            dst_presets.mkdir(parents=True, exist_ok=True)
            for prf in presets_dir.glob("*.json"):
                shutil.copy2(prf, dst_presets / prf.name)
                stats["presets"] += 1

    # 4. 导出图片与图库数据 (gallery)
    if inc_gallery:
        dst_gal = out_dir / "gallery"
        dst_thumbs = dst_gal / "thumbs"
        dst_gal.mkdir(parents=True, exist_ok=True)
        dst_thumbs.mkdir(parents=True, exist_ok=True)

        for meta_name in ["gallery.json", "gallery_folders.json"]:
            mfile = udir / meta_name
            if mfile.exists():
                shutil.copy2(mfile, out_dir / meta_name)

        if gallery_dir.exists():
            for img_p in gallery_dir.glob("*.*"):
                if img_p.is_file():
                    shutil.copy2(img_p, dst_gal / img_p.name)
                    stats["images"] += 1
            thumbs_src = gallery_dir / "thumbs"
            if thumbs_src.exists():
                for th_p in thumbs_src.glob("*.*"):
                    if th_p.is_file():
                        shutil.copy2(th_p, dst_thumbs / th_p.name)
        stats["gallery_images"] = stats["images"]

    # 5. 导出日志 (logs)
    if inc_logs:
        dst_logs = out_dir / "logs"
        dst_logs.mkdir(parents=True, exist_ok=True)
        atomic_write_json(dst_logs / "prompt_logs.json", collected_prompt_logs, ensure_ascii=False, indent=2)
        stats["logs"] = len(collected_prompt_logs)

        user_sess_logs = [
            {
                "device": v.get("device"),
                "ip": v.get("ip") or v.get("last_ip") or v.get("created_ip"),
                "created_at": v.get("created_at"),
                "last_seen_at": v.get("last_seen_at")
            }
            for v in SESSIONS.values() if v.get("username") == username
        ]
        atomic_write_json(dst_logs / "session_logs.json", user_sess_logs, ensure_ascii=False, indent=2)

    manifest = {
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": time.time(),
        "username": username,
        "target_dir": str(out_dir),
        "included": {
            "projects": inc_projects,
            "chats": inc_chats,
            "settings": inc_settings,
            "gallery": inc_gallery,
            "logs": inc_logs
        },
        "stats": stats
    }
    atomic_write_json(out_dir / "backup_manifest.json", manifest, ensure_ascii=False, indent=2)

    return {
        "status": "ok",
        "target_dir": str(out_dir),
        "stats": stats
    }

def _import_from_local_directory(
    src_dir: Path,
    username: str,
    inc_projects: bool = True,
    inc_chats: bool = True,
    inc_settings: bool = True,
    inc_gallery: bool = True,
    inc_logs: bool = True
) -> Dict[str, int]:
    udir = get_user_dir(username)
    projects_dir = get_user_projects_dir(username)
    chats_dir = get_user_chats_dir(username)
    gallery_dir = get_user_gallery_dir(username)
    presets_dir = get_user_presets_dir(username)

    stats = {
        "projects": 0,
        "chats": 0,
        "settings": 0,
        "presets": 0,
        "images": 0,
        "gallery_images": 0,
        "logs": 0
    }

    # 若用户选中的文件夹下只有一个子文件夹且自身无 projects/chats，自动下探一层
    if not any((src_dir / sub).exists() for sub in ["projects", "chats", "settings", "gallery", "settings.json", "backup_manifest.json", "character_cards.json"]):
        subdirs = [d for d in src_dir.iterdir() if d.is_dir()]
        if len(subdirs) == 1:
            src_dir = subdirs[0]

    # 1. 导入游戏设定 (projects)
    src_proj = src_dir / "projects"
    if inc_projects and src_proj.exists() and src_proj.is_dir():
        for pf in src_proj.glob("*.json"):
            try:
                safe_stem = re.sub(r'[^a-zA-Z0-9_\-]', '', pf.stem)
                if not safe_stem:
                    continue
                with open(pf, "r", encoding="utf-8") as f:
                    pd = json.load(f)
                if isinstance(pd, dict):
                    shutil.copy2(pf, projects_dir / f"{safe_stem}.json")
                    stats["projects"] += 1
            except Exception:
                pass

    # 导入角色卡库 (character_cards.json)
    src_cc = src_dir / "character_cards.json"
    if (inc_settings or inc_projects) and src_cc.exists():
        try:
            with open(src_cc, "r", encoding="utf-8") as f:
                imp_cards = json.load(f)
            if isinstance(imp_cards, list):
                cur_cards = load_user_character_cards(username)
                existing_ids = {c.get("id") for c in cur_cards if isinstance(c, dict)}
                for c in imp_cards:
                    if isinstance(c, dict) and c.get("id") not in existing_ids:
                        cur_cards.append(c)
                        existing_ids.add(c.get("id"))
                save_user_character_cards(username, cur_cards)
        except Exception:
            pass

    # 2. 导入游戏对话记录 (chats)
    src_chats = src_dir / "chats"
    if inc_chats and src_chats.exists() and src_chats.is_dir():
        for cf in src_chats.glob("*.json"):
            try:
                safe_stem = re.sub(r'[^a-zA-Z0-9_\-]', '', cf.stem)
                if not safe_stem:
                    continue
                with open(cf, "r", encoding="utf-8") as f:
                    cd = json.load(f)
                if isinstance(cd, dict) and "messages" in cd:
                    shutil.copy2(cf, chats_dir / f"{safe_stem}.json")
                    stats["chats"] += 1
            except Exception:
                pass

    # 3. 导入全局设置与预设 (settings & presets)
    if inc_settings:
        cand_settings = [src_dir / "settings" / "settings.json", src_dir / "settings.json"]
        for cs in cand_settings:
            if cs.exists() and cs.is_file():
                try:
                    with open(cs, "r", encoding="utf-8") as f:
                        sd = json.load(f)
                    if isinstance(sd, dict):
                        sd_clean = _sanitize_settings_numbers(dict(sd))
                        if is_masked_api_key(sd_clean.get("api_key")):
                            sd_clean.pop("api_key", None)
                        cur_s = load_user_settings(username)
                        cur_s.update(sd_clean)
                        save_user_settings(username, cur_s)
                        stats["settings"] += 1
                        break
                except Exception:
                    pass
        src_presets = src_dir / "presets"
        if src_presets.exists() and src_presets.is_dir():
            for prf in src_presets.glob("*.json"):
                try:
                    safe_preset_stem = re.sub(r'[^a-zA-Z0-9_\-\u4e00-\u9fff]', '', prf.stem)
                    if not safe_preset_stem:
                        continue
                    with open(prf, "r", encoding="utf-8") as pf_check:
                        json.load(pf_check)
                    shutil.copy2(prf, presets_dir / f"{safe_preset_stem}.json")
                    stats["presets"] += 1
                except Exception:
                    pass

    # 4. 导入图片与图库数据 (gallery)
    if inc_gallery:
        allowed_gal_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

        def _is_valid_gallery_image(p: Path) -> bool:
            if not p.is_file() or p.suffix.lower() not in allowed_gal_exts:
                return False
            try:
                with Image.open(p) as im:
                    im.verify()
                return True
            except Exception:
                return False

        src_gal = src_dir / "gallery"
        if src_gal.exists() and src_gal.is_dir():
            thumbs_dst = gallery_dir / "thumbs"
            thumbs_dst.mkdir(parents=True, exist_ok=True)
            for img_p in src_gal.glob("*.*"):
                if _is_valid_gallery_image(img_p):
                    safe_name = os.path.basename(img_p.name)
                    shutil.copy2(img_p, gallery_dir / safe_name)
                    stats["images"] += 1
            src_thumbs = src_gal / "thumbs"
            if src_thumbs.exists() and src_thumbs.is_dir():
                for th_p in src_thumbs.glob("*.*"):
                    if _is_valid_gallery_image(th_p):
                        safe_name = os.path.basename(th_p.name)
                        shutil.copy2(th_p, thumbs_dst / safe_name)
        stats["gallery_images"] = stats["images"]

        # 合并 gallery.json 与 gallery_folders.json
        with _GALLERY_LOCK:
            src_gal_json = src_dir / "gallery.json"
            if src_gal_json.exists():
                try:
                    with open(src_gal_json, "r", encoding="utf-8") as f:
                        imp_gal = json.load(f)
                    dst_gal_json = udir / "gallery.json"
                    cur_gal = []
                    if dst_gal_json.exists():
                        with open(dst_gal_json, "r", encoding="utf-8") as f:
                            cur_gal = json.load(f)
                    existing_ids = {item.get("id") for item in cur_gal if isinstance(item, dict)}
                    for item in (imp_gal if isinstance(imp_gal, list) else []):
                        if isinstance(item, dict) and item.get("id") not in existing_ids:
                            cur_gal.append(item)
                            existing_ids.add(item.get("id"))
                    atomic_write_json(dst_gal_json, cur_gal, ensure_ascii=False, indent=2)
                except Exception:
                    pass

            src_folders_json = src_dir / "gallery_folders.json"
            if src_folders_json.exists():
                try:
                    with open(src_folders_json, "r", encoding="utf-8") as f:
                        imp_folders = json.load(f)
                    dst_folders_json = udir / "gallery_folders.json"
                    cur_folders = []
                    if dst_folders_json.exists():
                        with open(dst_folders_json, "r", encoding="utf-8") as f:
                            cur_folders = json.load(f)
                    for fd in (imp_folders if isinstance(imp_folders, list) else []):
                        if fd not in cur_folders:
                            cur_folders.append(fd)
                    atomic_write_json(dst_folders_json, cur_folders, ensure_ascii=False, indent=2)
                except Exception:
                    pass

    # 5. 导入日志 (logs/prompt_logs.json)
    if inc_logs:
        src_plogs = src_dir / "logs" / "prompt_logs.json"
        if src_plogs.exists():
            try:
                with open(src_plogs, "r", encoding="utf-8") as f:
                    plogs = json.load(f)
                if isinstance(plogs, list):
                    for entry in plogs:
                        if not isinstance(entry, dict):
                            continue
                        cid = re.sub(r'[^a-zA-Z0-9_\-]', '', str(entry.get("chat_id") or ""))
                        plog = entry.get("prompt_log")
                        if cid and plog:
                            cfile = chats_dir / f"{cid}.json"
                            if cfile.exists():
                                with open(cfile, "r", encoding="utf-8") as cf:
                                    cdata = json.load(cf)
                                if not cdata.get("last_prompt_log"):
                                    cdata["last_prompt_log"] = plog
                                    atomic_write_json(cfile, cdata, ensure_ascii=False, indent=2)
                        stats["logs"] += 1
            except Exception:
                pass

    return stats

@app.post("/api/backup/import-folder", dependencies=[Depends(require_loopback)])
def import_from_folder(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    raw_src = str(payload.get("source_dir") or "").strip()
    if not raw_src:
        raise HTTPException(status_code=400, detail="请选择文件夹")
    src_dir = Path(raw_src).expanduser().resolve()
    if not src_dir.exists() or not src_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"文件夹不存在: {src_dir}")

    stats = _import_from_local_directory(
        src_dir=src_dir,
        username=username,
        inc_projects=bool(payload.get("include_projects", True)),
        inc_chats=bool(payload.get("include_chats", True)),
        inc_settings=bool(payload.get("include_settings", True)),
        inc_gallery=bool(payload.get("include_gallery", True)),
        inc_logs=bool(payload.get("include_logs", True))
    )
    return {
        "status": "ok",
        "source_dir": str(src_dir),
        "stats": stats
    }

def _safe_import_dest(temp_import_dir: Path, raw_rel_path: Any) -> Optional[Path]:
    """将上传文件的相对路径安全映射到临时导入目录内；拒绝绝对路径、盘符/ADS(':')、'..' 及解析后逃逸出临时目录的路径"""
    raw = str(raw_rel_path or "")
    if not raw or ":" in raw or raw.startswith("/") or raw.startswith("\\") or "\x00" in raw:
        return None
    rel_path = raw.replace("\\", "/")
    if not rel_path or ".." in rel_path.split("/"):
        return None
    parts = [p for p in rel_path.split("/") if p not in ("", ".")]
    if not parts:
        return None
    if len(parts) > 1 and parts[0] not in ("projects", "chats", "settings", "presets", "gallery", "logs"):
        parts = parts[1:]
    try:
        base_resolved = temp_import_dir.resolve()
        dest_file = (temp_import_dir / "/".join(parts)).resolve()
        if dest_file == base_resolved:
            return None
        try:
            if not dest_file.is_relative_to(base_resolved):
                return None
        except AttributeError:
            dest_file.relative_to(base_resolved)
        return dest_file
    except Exception:
        return None

@app.post("/api/backup/import-uploaded-folder", dependencies=[Depends(require_loopback)])
async def import_uploaded_folder_files(request: Request, username: str = Depends(get_current_user)):
    """接收前端通过 <input type='file' webkitdirectory> 选择的整个文件夹文件列表（支持 FormData 或 JSON）并还原"""
    max_total_bytes = 512 * 1024 * 1024
    total_written_bytes = 0
    temp_import_dir = BACKUP_ROOT_DIR / f"_tmp_import_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"
    temp_import_dir.mkdir(parents=True, exist_ok=True)
    try:
        content_type = (request.headers.get("content-type") or "").lower()
        opts = {
            "include_projects": True,
            "include_chats": True,
            "include_settings": True,
            "include_gallery": True,
            "include_logs": True
        }

        if "multipart/form-data" in content_type:
            # 备份文件夹常包含上千个图库文件，Starlette 默认 max_files/max_fields=1000 会直接拒绝
            form = await request.form(max_files=100_000, max_fields=100_000)
            raw_opts = form.get("options")
            if raw_opts:
                try:
                    opts.update(json.loads(str(raw_opts)))
                except Exception:
                    pass
            raw_rels = form.get("relative_paths")
            rel_paths = []
            if raw_rels:
                try:
                    rel_paths = json.loads(str(raw_rels))
                except Exception:
                    pass
            uploaded_files = form.getlist("files")
            if not uploaded_files:
                raise HTTPException(status_code=400, detail="文件夹为空")
            for idx, uf in enumerate(uploaded_files):
                rel_path = (rel_paths[idx] if idx < len(rel_paths) else getattr(uf, "filename", "")) or ""
                dest_file = _safe_import_dest(temp_import_dir, rel_path)
                if dest_file is None:
                    continue
                file_bytes = await uf.read()
                total_written_bytes += len(file_bytes)
                if total_written_bytes > max_total_bytes:
                    raise HTTPException(status_code=413, detail="上传文件夹总大小超过 512MB 上限；请改用本机路径直接导入")
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                dest_file.write_bytes(file_bytes)
        else:
            payload = await request.json()
            opts.update(payload)
            files_list = payload.get("files") or []
            if not isinstance(files_list, list) or len(files_list) == 0:
                raise HTTPException(status_code=400, detail="文件夹为空")
            for fitem in files_list:
                if not isinstance(fitem, dict):
                    continue
                dest_file = _safe_import_dest(temp_import_dir, fitem.get("rel_path") or fitem.get("name") or "")
                if dest_file is None:
                    continue
                b64_data = fitem.get("base64")
                text_data = fitem.get("content")
                if b64_data:
                    if "," in b64_data:
                        b64_data = b64_data.split(",", 1)[1]
                    decoded_b = base64.b64decode(b64_data)
                    total_written_bytes += len(decoded_b)
                    if total_written_bytes > max_total_bytes:
                        raise HTTPException(status_code=413, detail="上传文件夹总大小超过 512MB 上限；请改用本机路径直接导入")
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    dest_file.write_bytes(decoded_b)
                elif text_data is not None:
                    encoded_t = str(text_data).encode("utf-8")
                    total_written_bytes += len(encoded_t)
                    if total_written_bytes > max_total_bytes:
                        raise HTTPException(status_code=413, detail="上传文件夹总大小超过 512MB 上限；请改用本机路径直接导入")
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    dest_file.write_bytes(encoded_t)

        stats = await asyncio.to_thread(
            _import_from_local_directory,
            src_dir=temp_import_dir,
            username=username,
            inc_projects=bool(opts.get("include_projects", True)),
            inc_chats=bool(opts.get("include_chats", True)),
            inc_settings=bool(opts.get("include_settings", True)),
            inc_gallery=bool(opts.get("include_gallery", True)),
            inc_logs=bool(opts.get("include_logs", True))
        )
        return {"status": "ok", "stats": stats}
    finally:
        try:
            shutil.rmtree(temp_import_dir, ignore_errors=True)
        except Exception:
            pass

# ==================== OpenTavern 格式角色卡管理 (chara_card_v1 / v2 / v3) ====================
def get_user_character_cards_file(username: str) -> Path:
    return get_user_dir(username) / "character_cards.json"

def load_user_character_cards(username: str) -> List[Dict[str, Any]]:
    with _CHAR_CARDS_LOCK:
        cc_file = get_user_character_cards_file(username)
        if not cc_file.exists():
            return []
        try:
            with open(cc_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

def save_user_character_cards(username: str, cards: List[Dict[str, Any]]) -> None:
    with _CHAR_CARDS_LOCK:
        cc_file = get_user_character_cards_file(username)
        atomic_write_json(cc_file, cards, ensure_ascii=False, indent=2)

def _replace_char_macro(text: str, card_name: str) -> str:
    if not text or not card_name:
        return text
    return re.sub(r"\{\{\s*char\s*\}\}|<BOT>", lambda _m: card_name, text, flags=re.IGNORECASE)

def _normalize_character_book_entries(raw_cb: Any, card_name: str = "") -> List[Dict[str, Any]]:
    """将 SillyTavern / V2 / V3 角色卡内嵌的 character_book 词条标准化为工作台 evaluate_world_book 可执行的条目列表"""
    if not raw_cb:
        return []
    entries_raw = []
    if isinstance(raw_cb, dict):
        entries_obj = raw_cb.get("entries")
        if isinstance(entries_obj, list):
            entries_raw = entries_obj
        elif isinstance(entries_obj, dict):
            entries_raw = list(entries_obj.values())
    elif isinstance(raw_cb, list):
        entries_raw = raw_cb

    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(entries_raw):
        if not isinstance(item, dict):
            continue
        if item.get("enabled") is False or item.get("disable") is True:
            continue
        content = _replace_char_macro(str(item.get("content") or item.get("entry") or "").strip(), card_name)
        if not content:
            continue
        raw_keys = item.get("keys") if "keys" in item else item.get("key", [])
        if isinstance(raw_keys, str):
            keys = [_replace_char_macro(k.strip(), card_name) for k in raw_keys.replace("，", ",").split(",") if k.strip()]
        elif isinstance(raw_keys, list):
            keys = [_replace_char_macro(str(k).strip(), card_name) for k in raw_keys if str(k).strip()]
        else:
            keys = []
        raw_sec = item.get("secondary_keys") if "secondary_keys" in item else item.get("keysecondary", [])
        if isinstance(raw_sec, str):
            sec_keys = [_replace_char_macro(k.strip(), card_name) for k in raw_sec.replace("，", ",").split(",") if k.strip()]
        elif isinstance(raw_sec, list):
            sec_keys = [_replace_char_macro(str(k).strip(), card_name) for k in raw_sec if str(k).strip()]
        else:
            sec_keys = []

        constant = bool(item.get("constant", False))
        if not keys and not constant:
            continue

        pos_raw = item.get("position") if item.get("position") is not None else item.get("value_region", "System")
        pos = str(pos_raw).strip()
        pos_map = {
            "before_char": "System",
            "after_char": "System",
            "0": "System",
            "1": "System",
            "2": "Prefix",
            "3": "Suffix",
            "4": "System",
            "system": "System",
            "prefix": "Prefix",
            "suffix": "Suffix",
        }
        value_region = pos_map.get(pos.lower(), "System")
        comment = _replace_char_macro(
            str(item.get("comment") or item.get("name") or f"{card_name or '角色'}词条#{idx+1}").strip(),
            card_name,
        )
        raw_id = item.get("id") if item.get("id") is not None else item.get("uid")
        entry_id = str(raw_id) if (raw_id is not None and str(raw_id).strip() != "") else f"cb_{idx}"

        raw_order = item.get("insertion_order") if item.get("insertion_order") is not None else item.get("order")
        order_val = safe_int(raw_order, 100) if raw_order is not None else 100

        raw_scan_depth = item.get("scan_depth") if item.get("scan_depth") is not None else (
            item.get("scanDepth") if item.get("scanDepth") is not None else item.get("depth")
        )
        raw_prob = item.get("probability")
        prob_val = safe_int(raw_prob, 100) if raw_prob is not None else 100

        entry_obj: Dict[str, Any] = {
            "id": entry_id,
            "name": comment,
            "keys": [] if constant else keys,
            "secondary_keys": sec_keys,
            "selective": bool(item.get("selective", bool(sec_keys))),
            "selective_logic": safe_int(item.get("selective_logic", item.get("selectiveLogic", 0)), 0),
            "case_sensitive": bool(item.get("case_sensitive", item.get("caseSensitive", False))),
            "exclude_recursion": bool(item.get("exclude_recursion", item.get("excludeRecursion", False))),
            "constant": constant,
            "match_type": str(item.get("match_type") or "OR"),
            "value_region": value_region,
            "content": f"【{card_name}·专属设定：{comment}】\n{content}" if card_name else content,
            "enabled": True,
            "order": order_val,
            "sort": order_val,
            "probability": prob_val,
        }
        if raw_scan_depth is not None:
            sd_val = safe_int(raw_scan_depth, 5)
            entry_obj["scan_depth"] = sd_val
            entry_obj["depth"] = sd_val
        normalized.append(entry_obj)
    return normalized


def normalize_character_card_payload(raw: Dict[str, Any], existing_id: Optional[str] = None) -> Dict[str, Any]:
    """兼容 OpenTavern / SillyTavern chara_card_v1 / v2 / v3 及编辑器表单数据（完整保留内嵌 character_book 世界书）"""
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="角色卡格式无效")

    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    name = str(data.get("name") or raw.get("name") or "").strip()
    if not name:
        name = "未命名角色"

    raw_tags = data.get("tags") if "tags" in data else raw.get("tags", [])
    if isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.replace("，", ",").split(",") if t.strip()]
    elif isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    else:
        tags = []

    raw_greets = data.get("alternate_greetings") if "alternate_greetings" in data else raw.get("alternate_greetings", [])
    if isinstance(raw_greets, list):
        alternate_greetings = [str(g) for g in raw_greets if str(g).strip()]
    else:
        alternate_greetings = []

    extensions = copy.deepcopy(data.get("extensions")) if isinstance(data.get("extensions"), dict) else {}
    wb_ext = extensions.get("trpg_workbench") if isinstance(extensions.get("trpg_workbench"), dict) else {}
    raw_dp = data.get("depth_prompt") or extensions.get("depth_prompt") or raw.get("depth_prompt") or {}
    if not isinstance(raw_dp, dict):
        raw_dp = {}
    dp_prompt = str(raw_dp.get("prompt") or "")
    try:
        dp_depth = max(0, int(raw_dp.get("depth", 4)))
    except Exception:
        dp_depth = 4
    dp_role = str(raw_dp.get("role") or "system")
    if dp_role not in ("system", "user", "assistant"):
        dp_role = "system"
    depth_prompt = {"prompt": dp_prompt, "depth": dp_depth, "role": dp_role}
    if dp_prompt.strip():
        extensions["depth_prompt"] = depth_prompt

    # 提取并保留 V2/V3 规范中的 data.character_book（内嵌专属世界书）
    raw_cb = data.get("character_book") or raw.get("character_book") or extensions.get("character_book")
    character_book = raw_cb if isinstance(raw_cb, (dict, list)) else None
    character_book_entries = _normalize_character_book_entries(character_book, name) if character_book else (
        raw.get("character_book_entries") if isinstance(raw.get("character_book_entries"), list) else []
    )

    avatar = str(raw.get("avatar") or data.get("avatar") or "").strip()
    if avatar and avatar.startswith("data:image/"):
        avatar = optimize_image_base64(avatar, max_dim=480, quality=82, min_bytes=30_000)

    card_id = existing_id or str(raw.get("id") or data.get("id") or f"card_{uuid.uuid4().hex[:10]}")
    raw_mode = str(
        raw.get("card_mode") or data.get("card_mode") or extensions.get("card_mode") or wb_ext.get("card_mode") or ""
    ).strip().lower()
    card_mode = "simple" if raw_mode == "simple" else "advanced"
    gender = str(raw.get("gender") or data.get("gender") or extensions.get("gender") or wb_ext.get("gender") or "").strip()
    age = str(raw.get("age") or data.get("age") or extensions.get("age") or wb_ext.get("age") or "").strip()
    identity = str(raw.get("identity") or data.get("identity") or extensions.get("identity") or wb_ext.get("identity") or "").strip()
    description_label = str(
        raw.get("description_label") or data.get("description_label") or extensions.get("description_label") or wb_ext.get("description_label") or ""
    ).strip()

    raw_fl = raw.get("field_labels") if isinstance(raw.get("field_labels"), dict) else (
        data.get("field_labels") if isinstance(data.get("field_labels"), dict) else (
            extensions.get("field_labels") if isinstance(extensions.get("field_labels"), dict) else (
                wb_ext.get("field_labels") if isinstance(wb_ext.get("field_labels"), dict) else {}
            )
        )
    )
    field_labels: Dict[str, str] = {}
    if isinstance(raw_fl, dict):
        for k, v in raw_fl.items():
            ks = str(k).strip()
            vs = str(v or "").strip()
            if ks and vs:
                field_labels[ks] = vs
    if description_label and "description" not in field_labels:
        field_labels["description"] = description_label
    elif "description" in field_labels and not description_label:
        description_label = field_labels["description"]

    if "custom_fields" in raw:
        raw_cf = raw.get("custom_fields")
    elif "custom_fields" in data:
        raw_cf = data.get("custom_fields")
    elif "custom_fields" in extensions:
        raw_cf = extensions.get("custom_fields")
    else:
        raw_cf = wb_ext.get("custom_fields", [])
    custom_fields = []
    if isinstance(raw_cf, list):
        for item in raw_cf:
            if isinstance(item, dict):
                lbl = str(item.get("label") or "").strip()
                val = str(item.get("value") or "").strip()
                multi = bool(item.get("multiline", False))
                if lbl or val:
                    custom_fields.append({"label": lbl or "未命名栏位", "value": val, "multiline": multi})

    extensions["card_mode"] = card_mode
    extensions["custom_fields"] = custom_fields
    if field_labels:
        extensions["field_labels"] = field_labels
    if description_label:
        extensions["description_label"] = description_label
    if gender:
        extensions["gender"] = gender
    if age:
        extensions["age"] = age
    if identity:
        extensions["identity"] = identity
    extensions["trpg_workbench"] = {
        "card_mode": card_mode,
        "gender": gender,
        "age": age,
        "identity": identity,
        "custom_fields": custom_fields,
        "description_label": description_label,
        "field_labels": field_labels,
    }

    return {
        "id": card_id,
        "spec": "chara_card_v3",
        "spec_version": "3.0",
        "card_mode": card_mode,
        "name": name,
        "gender": gender,
        "age": age,
        "identity": identity,
        "custom_fields": custom_fields,
        "description_label": description_label,
        "field_labels": field_labels,
        "tags": tags,
        "avatar": avatar,
        "description": str(data.get("description") or ""),
        "personality": str(data.get("personality") or ""),
        "scenario": str(data.get("scenario") or ""),
        "first_mes": str(data.get("first_mes") or ""),
        "alternate_greetings": alternate_greetings,
        "mes_example": str(data.get("mes_example") or ""),
        "system_prompt": str(data.get("system_prompt") or data.get("system_prompts") or ""),
        "post_history_instructions": str(data.get("post_history_instructions") or ""),
        "creator_notes": str(data.get("creator_notes") or ""),
        "depth_prompt": depth_prompt,
        "character_book": character_book,
        "character_book_entries": character_book_entries,
        "extensions": extensions,
        "updated_at": time.time()
    }

@app.get("/api/character_cards")
def list_character_cards(username: str = Depends(get_current_user)):
    return {"cards": load_user_character_cards(username)}

@app.post("/api/character_cards")
def create_or_save_character_card(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    card = normalize_character_card_payload(payload)
    with _CHAR_CARDS_LOCK:
        cards = load_user_character_cards(username)
        replaced = False
        for idx, c in enumerate(cards):
            if c.get("id") == card["id"]:
                if not card.get("character_book") and c.get("character_book"):
                    card["character_book"] = c["character_book"]
                    card["character_book_entries"] = c.get("character_book_entries", [])
                cards[idx] = card
                replaced = True
                break
        if not replaced:
            cards.insert(0, card)
        save_user_character_cards(username, cards)
    return {"status": "ok", "card": card, "cards": cards}

@app.put("/api/character_cards/{card_id}")
def update_character_card(card_id: str, payload: Dict[str, Any], username: str = Depends(get_current_user)):
    card = normalize_character_card_payload(payload, existing_id=card_id)
    with _CHAR_CARDS_LOCK:
        cards = load_user_character_cards(username)
        found = False
        for idx, c in enumerate(cards):
            if c.get("id") == card_id:
                if not card.get("avatar") and c.get("avatar"):
                    card["avatar"] = c["avatar"]
                if not card.get("character_book") and c.get("character_book"):
                    card["character_book"] = c["character_book"]
                    card["character_book_entries"] = c.get("character_book_entries", [])
                cards[idx] = card
                found = True
                break
        if not found:
            cards.insert(0, card)
        save_user_character_cards(username, cards)
    return {"status": "ok", "card": card, "cards": cards}

@app.delete("/api/character_cards/{card_id}")
def delete_character_card(card_id: str, username: str = Depends(get_current_user)):
    with _CHAR_CARDS_LOCK:
        cards = load_user_character_cards(username)
        cards = [c for c in cards if c.get("id") != card_id]
        save_user_character_cards(username, cards)
    return {"status": "ok", "cards": cards}

def _extract_chara_json_from_png_bytes(png_bytes: bytes) -> Dict[str, Any]:
    """解析 SillyTavern / OpenTavern PNG 角色卡中内嵌的 tEXt / zTXt / iTXt (chara / ccv3) 数据块"""
    import struct
    import zlib

    if len(png_bytes) < 8 or png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("不是有效的 PNG 文件")

    max_decomp_bytes = 16 * 1024 * 1024

    def _safe_decompress(comp_data: bytes) -> bytes:
        dobj = zlib.decompressobj()
        out = dobj.decompress(comp_data, max_decomp_bytes + 1)
        if len(out) > max_decomp_bytes or dobj.unconsumed_tail:
            raise ValueError("PNG 文本块解压后体积超过 16MB 安全上限")
        out += dobj.flush()
        return out

    pos = 8
    found_json = None
    while pos + 12 <= len(png_bytes):
        length = struct.unpack(">I", png_bytes[pos:pos + 4])[0]
        if pos + 12 + length > len(png_bytes):
            break
        chunk_type = png_bytes[pos + 4:pos + 8].decode("ascii", errors="ignore")
        chunk_data = png_bytes[pos + 8:pos + 8 + length]
        pos += 12 + length

        if chunk_type in ("tEXt", "zTXt", "iTXt"):
            nul_idx = chunk_data.find(b"\x00")
            if nul_idx == -1:
                continue
            keyword = chunk_data[:nul_idx].decode("utf-8", errors="ignore").strip().lower()
            if keyword in ("chara", "ccv3"):
                try:
                    if chunk_type == "tEXt":
                        payload_bytes = chunk_data[nul_idx + 1:]
                    elif chunk_type == "zTXt":
                        if nul_idx + 2 > len(chunk_data):
                            continue
                        payload_bytes = _safe_decompress(chunk_data[nul_idx + 2:])
                    else:
                        cursor = nul_idx + 1
                        if cursor + 2 > len(chunk_data):
                            continue
                        comp_flag = chunk_data[cursor]
                        cursor += 2
                        for _ in range(2):
                            n_pos = chunk_data.find(b"\x00", cursor)
                            if n_pos == -1:
                                break
                            cursor = n_pos + 1
                        raw_part = chunk_data[cursor:]
                        payload_bytes = _safe_decompress(raw_part) if comp_flag == 1 else raw_part

                    text_str = payload_bytes.decode("utf-8", errors="ignore").strip()
                    if text_str.startswith("{"):
                        parsed = json.loads(text_str)
                    else:
                        b64_compact = re.sub(r"\s+", "", text_str)
                        b64_compact += "=" * ((-len(b64_compact)) % 4)
                        decoded_bytes = base64.b64decode(b64_compact)
                        parsed = json.loads(decoded_bytes.decode("utf-8-sig"))
                    if keyword == "ccv3":
                        return parsed
                    found_json = parsed
                except Exception:
                    continue
        elif chunk_type == "IEND":
            break
    if found_json:
        return found_json
    raise ValueError("PNG 中无角色卡数据")

@app.post("/api/character_cards/import")
async def import_character_card_file(file: UploadFile = File(...), username: str = Depends(get_current_user)):
    raw_bytes = await file.read()
    if len(raw_bytes) > 30 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="角色卡文件体积不能超过 30MB")
    fname = (file.filename or "").lower()
    avatar_b64 = ""

    try:
        if fname.endswith(".png") or raw_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            raw_json = _extract_chara_json_from_png_bytes(raw_bytes)
            raw_data_url = "data:image/png;base64," + base64.b64encode(raw_bytes).decode("ascii")
            avatar_b64 = await asyncio.to_thread(optimize_image_base64, raw_data_url, 320, 80, 30_000)
        else:
            raw_json = json.loads(raw_bytes.decode("utf-8-sig"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析角色卡失败: {e}")

    if avatar_b64 and isinstance(raw_json, dict):
        raw_json["avatar"] = avatar_b64

    card = normalize_character_card_payload(raw_json)
    with _CHAR_CARDS_LOCK:
        cards = load_user_character_cards(username)
        existing_ids = {str(c.get("id") or "") for c in cards if isinstance(c, dict)}
        if not card.get("id") or card["id"] in existing_ids:
            card["id"] = f"card_{uuid.uuid4().hex[:10]}"
        cards.insert(0, card)
        save_user_character_cards(username, cards)
    return {"status": "ok", "card": card, "cards": cards}



async def _search_character_web_info(query: str, proxy: Optional[str] = None) -> List[str]:
    """并发从 Bangumi 角色库、中文维基百科与 Bing 搜索抓取角色设定文本资料（不抓取图片）"""
    q = (query or "").strip()
    if not q:
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    snippets: List[str] = []

    async def _search_bgm():
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=6.0, headers=headers) as client:
                r = await client.post(
                    "https://api.bgm.tv/v0/search/characters?limit=3",
                    json={"keyword": q}
                )
                if r.status_code == 200:
                    items = (r.json() or {}).get("data") or []
                    for item in items[:2]:
                        cname = item.get("name") or ""
                        summary = (item.get("summary") or "").strip()
                        infobox = item.get("infobox") or []
                        info_parts = []
                        for ib in infobox:
                            if isinstance(ib, dict) and ib.get("key") and ib.get("value"):
                                val = ib["value"]
                                if isinstance(val, list):
                                    val = " / ".join(str(v.get("v", v)) if isinstance(v, dict) else str(v) for v in val)
                                info_parts.append(f"{ib['key']}: {val}")
                        if cname or summary or info_parts:
                            snippets.append(
                                f"【Bangumi 角色百科：{cname}】\n"
                                + (f"属性：{'; '.join(info_parts[:10])}\n" if info_parts else "")
                                + (f"简介：{summary[:600]}" if summary else "")
                            )
        except Exception:
            pass

    async def _search_wiki():
        for cur_proxy in ([proxy, None] if proxy else [None]):
            try:
                async with httpx.AsyncClient(proxy=cur_proxy, trust_env=False, timeout=5.5, headers=headers) as client:
                    r = await client.get(
                        "https://zh.wikipedia.org/w/api.php",
                        params={
                            "action": "query",
                            "list": "search",
                            "srsearch": q,
                            "format": "json",
                            "utf8": 1,
                            "srlimit": 2
                        }
                    )
                    if r.status_code == 200:
                        slist = ((r.json() or {}).get("query") or {}).get("search") or []
                        for s in slist[:2]:
                            title = s.get("title") or ""
                            clean_snip = re.sub(r"<[^>]+>", "", s.get("snippet") or "").strip()
                            if title and clean_snip:
                                snippets.append(f"【维基百科：{title}】{clean_snip}")
                        break
            except Exception:
                continue

    async def _search_bing():
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=5.5, headers=headers, follow_redirects=True) as client:
                r = await client.get("https://cn.bing.com/search", params={"q": f"{q} 角色 设定 简介"})
                if r.status_code == 200:
                    html_txt = r.text
                    blocks = re.findall(r'<li class="b_algo"[\s\S]*?</li>', html_txt)
                    for b in blocks[:4]:
                        t_m = re.search(r"<h2[^>]*>([\s\S]*?)</h2>", b)
                        p_m = re.search(r"<p[^>]*>([\s\S]*?)</p>", b)
                        t_str = re.sub(r"<[^>]+>", "", t_m.group(1) if t_m else "").strip()
                        p_str = re.sub(r"<[^>]+>", "", p_m.group(1) if p_m else "").strip()
                        if t_str and p_str:
                            snippets.append(f"【网页检索：{t_str}】{p_str[:300]}")
        except Exception:
            pass

    await asyncio.gather(_search_bgm(), _search_wiki(), _search_bing(), return_exceptions=True)
    return snippets


@app.post("/api/character_cards/ai_generate")
async def ai_generate_character_card(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    prompt_req = str(payload.get("prompt") or payload.get("name") or "").strip()
    raw_images = payload.get("images") if isinstance(payload.get("images"), list) else []
    input_images = [img for img in raw_images if isinstance(img, str) and img.startswith("data:image")]

    if not prompt_req and not input_images:
        raise HTTPException(status_code=400, detail="请输入需求或上传图片")

    card_mode = "simple" if str(payload.get("card_mode") or "simple").lower() == "simple" else "advanced"
    use_web_search = bool(payload.get("use_web_search", True))
    req_custom_fields = payload.get("custom_fields") if isinstance(payload.get("custom_fields"), list) else []
    desc_label = str(payload.get("description_label") or "基本信息与角色简介").strip()

    settings = load_user_settings(username)
    model_id = str(payload.get("model") or settings.get("model", "")).strip()
    if not model_id:
        raise HTTPException(status_code=400, detail="请先选择模型")
    ep = resolve_model_endpoint(model_id, settings)
    if ep["is_local"]:
        local_err = await ensure_local_engine_ready(model_id)
        ep = resolve_model_endpoint(model_id, settings)
        if local_err:
            raise HTTPException(status_code=502, detail=local_err)

    web_snippets: List[str] = []
    if use_web_search and prompt_req:
        web_snippets = await _search_character_web_info(prompt_req, ep["proxy"])

    field_labels = [str(f.get("label") or "").strip() for f in req_custom_fields if isinstance(f, dict) and str(f.get("label") or "").strip()]
    default_core_labels = [
        "身份 / 职业",
        "性别 / 种族",
        "年龄 / 身高",
        "外貌特征与穿搭",
        "性格特点",
        "说话口吻与口癖",
        "能力技能与装备",
        "人际关系与态度"
    ]
    if not field_labels or set(field_labels) <= {"身份 / 职业", "性别 / 种族", "年龄", "年龄 / 身高"}:
        field_labels = default_core_labels

    web_context = "\n\n".join(web_snippets) if web_snippets else "（未检索到外部网页条目，请直接结合附带图片与你自身的知识库/创作能力）"
    vision_guide = (
        "\n若用户附带了 1 张或多张角色参考图片（如立绘、三视图、设定图、卡片截图），请仔细观察所有图片中的视觉细节（发型发色、瞳色、五官气质、身高体型、服装款式、配饰、所持武器/道具）以及图片内包含的文字设定，将其精准提炼并融入角色卡各栏位中。"
        if input_images
        else ""
    )

    if card_mode == "simple":
        sys_instruction = (
            "你是一位精通 ACG、文学影视、TRPG 跑团与角色设定的资深角色卡设计师。\n"
            f"请结合用户附带的参考图片、联网检索资料与你自身的知识库，将用户的需求转化为极简直观的【角色卡】JSON 数据。{vision_guide}\n"
            "必须严格只输出合法的 JSON 对象（不要用解释文字包裹），JSON 格式如下：\n"
            "{\n"
            '  "name": "角色正式名称",\n'
            '  "tags": ["标签1", "标签2", "标签3"],\n'
            '  "custom_fields": [],\n'
            '  "description": "【身份与定位】：...\\n【外貌特征与穿搭】：...\\n【核心性格与行事准则】：...\\n【说话口吻与口癖】：...\\n【能力技能与随身装备】：...\\n【背景故事与人际关系】：..."\n'
            "}\n"
            "注意：由于极简编辑器只展示一个统一的「角色设定与简介 (description)」大文本框，请务必把角色的身份职业、性别年龄、外貌特征与穿搭、性格特点、说话口吻与口癖、能力装备、背景经历与人际关系全部清晰分段写进 `description` 字段中，并将 `custom_fields` 保持为空数组 `[]`！"
        )
    else:
        sys_instruction = (
            "你是一位精通 SillyTavern / OpenTavern (chara_card_v3) 标准格式的角色卡大师。\n"
            f"请结合用户附带的参考图片、联网检索资料与你自身的知识库，将用户的需求转化为完整的【高级角色卡】JSON 数据。{vision_guide}\n"
            "必须严格只输出合法的 JSON 对象，JSON 格式如下：\n"
            "{\n"
            '  "name": "角色正式名称",\n'
            '  "tags": ["标签1", "标签2", "标签3", "标签4"],\n'
            '  "custom_fields": [\n'
            '    {"label": "栏位名称", "value": "对应具体内容", "multiline": true}\n'
            "  ],\n"
            '  "description": "按 OpenTavern 标准六大系统（一、外貌系统；二、穿搭系统；三、三层性格系统；四、说话方式与口癖；五、背景与动机；六、人际关系与对{{user}}的态度）编写的详尽设定",\n'
            '  "personality": "外在表现、内在性格与性格内核精炼概括",\n'
            '  "scenario": "当前所处场景、时间线与{{char}}和{{user}}的互动背景",\n'
            '  "first_mes": "富有画面感、动作神态描写与符合角色口吻台词的默认开场白（200~400字）",\n'
            '  "alternate_greetings": ["备用开场白1"],\n'
            '  "mes_example": "<START>\\n{{user}}: 你好\\n{{char}}: *动作神态描写* 角色台词",\n'
            '  "system_prompt": "扮演该角色的核心文风与防OOC准则",\n'
            '  "post_history_instructions": "保持角色性格与说话口癖，严禁代替{{user}}说话或行动",\n'
            '  "creator_notes": "角色出处与食用说明",\n'
            '  "depth_prompt": {"prompt": "时刻体现角色的标志性神态、口癖与内在情感变化。", "depth": 4, "role": "system"}\n'
            "}\n"
            f"注意：custom_fields 中必须包含并填充以下用户指定的栏位：{json.dumps(field_labels, ensure_ascii=False)}。"
        )

    effective_prompt_str = (
        prompt_req
        if prompt_req
        else "请仔细识别并分析附带的所有角色参考图片（包括立绘外观、服饰配件、神态气质以及图片中的文字信息），提炼并完善该角色的名称、属性栏与背景设定。"
    )
    user_msg = (
        f"【用户角色需求】：{effective_prompt_str}\n"
        f"【附带参考图片数量】：{len(input_images)} 张\n"
        f"【用户主简介栏标题】：{desc_label}\n"
        f"【用户当前自定义属性栏】：{', '.join(field_labels)}\n\n"
        f"【联网搜索参考资料】：\n{web_context}\n\n"
        "请直接输出填充好的 JSON 对象："
    )

    if input_images:
        user_content: Any = [{"type": "text", "text": user_msg}]
        for opt_img in await _optimize_images_async(list(input_images), max_dim=1024, quality=80, min_bytes=120_000):
            user_content.append({"type": "image_url", "image_url": {"url": opt_img}})
    else:
        user_content = user_msg

    api_messages = sanitize_messages_for_model(
        [
            {"role": "system", "content": sys_instruction},
            {"role": "user", "content": user_content}
        ],
        ep["supports_vision"]
    )

    proxy = ep["proxy"]
    base_url = ep["base_url"]
    api_key = ep["api_key"]
    upstream_model = ep["upstream_model"]
    proxy_candidates = [proxy, None] if proxy else [None]
    collected: List[str] = []

    card_req_json: Dict[str, Any] = {
        "model": upstream_model,
        "messages": api_messages,
        "max_tokens": 6144,
        "temperature": 0.68,
        "stream": True
    }
    if ep.get("protocol") not in ("claude", "gemini"):
        card_req_json["presence_penalty"] = 0.25
    if ep["is_local"]:
        if ep["engine"] == "strata":
            card_req_json["reasoning_effort"] = "low"
            card_req_json["reasoning_budget_tokens"] = 512
            card_req_json["repeat_penalty"] = 1.05
            card_req_json["repeat_last_n"] = 1024
        elif ep["engine"] == "ollama":
            card_req_json["think"] = False
            card_req_json["options"] = {
                "repeat_penalty": 1.05,
                "repeat_last_n": 1024,
                "num_ctx": get_optimal_ollama_num_ctx(model_id, settings, min_ctx=8192),
            }

    for cur_proxy in proxy_candidates:
        try:
            async with httpx.AsyncClient(proxy=cur_proxy, trust_env=False, timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                async with client.stream(
                    "POST",
                    f"{base_url}/chat/completions",
                    headers=ep.get("headers") or {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=card_req_json
                ) as resp:
                    if resp.status_code != 200:
                        continue
                    ctype = (resp.headers.get("content-type") or "").lower()
                    if "text/event-stream" not in ctype:
                        raw_bytes = await resp.aread()
                        rj = json.loads(raw_bytes.decode("utf-8", errors="ignore"))
                        raw_c = rj.get("choices", [{}])[0].get("message", {}).get("content", "")
                        if raw_c:
                            collected.append(raw_c)
                    else:
                        async for line in resp.aiter_lines():
                            line = line.strip()
                            if line.startswith("data:"):
                                raw_data = line[5:].lstrip()
                                if raw_data == "[DONE]":
                                    continue
                                try:
                                    d = json.loads(raw_data)
                                    delta = d.get("choices", [{}])[0].get("delta", {})
                                    c = delta.get("content") or ""
                                    if c:
                                        collected.append(c)
                                except Exception:
                                    pass
                    if collected:
                        break
        except Exception:
            continue

    raw_reply = strip_thinking_blocks("".join(collected))

    parsed_card: Dict[str, Any] = {}
    if raw_reply:
        clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_reply, flags=re.IGNORECASE).strip()
        try:
            parsed_card = json.loads(clean_json)
        except Exception:
            m = re.search(r"\{[\s\S]*\}", clean_json)
            if m:
                try:
                    parsed_card = json.loads(m.group(0))
                except Exception:
                    pass

    if not isinstance(parsed_card, dict) or not parsed_card:
        raise HTTPException(status_code=500, detail="AI 返回格式无效，请重试或换模型")

    parsed_card.pop("avatar", None)
    if card_mode == "simple":
        raw_cfs = parsed_card.get("custom_fields")
        desc_str = str(parsed_card.get("description") or "").strip()
        if isinstance(raw_cfs, list) and raw_cfs:
            cf_lines = []
            for cf in raw_cfs:
                if isinstance(cf, dict):
                    lbl = str(cf.get("label") or "").strip()
                    val = str(cf.get("value") or "").strip()
                    if lbl and val and val not in desc_str:
                        cf_lines.append(f"【{lbl}】：{val}")
            if cf_lines:
                merged_cf_text = "\n".join(cf_lines)
                desc_str = f"{merged_cf_text}\n\n{desc_str}".strip() if desc_str else merged_cf_text
        parsed_card["description"] = desc_str
        parsed_card["custom_fields"] = []

    return {
        "status": "ok",
        "card_data": parsed_card,
        "web_sources_count": len(web_snippets),
        "images_count": len(input_images)
    }


def _is_own_trpg_server_process(pid: int, creation_flags: int, si: Any) -> bool:
    """严格校验占用端口的进程是否为当前工作台目录的旧 server.py 实例，绝不误杀其他 Python 服务"""
    try:
        ps_cmd = (
            f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {int(pid)}' "
            "| Select-Object -ExpandProperty CommandLine)"
        )
        cmd_line = subprocess.check_output(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            encoding="utf-8",
            errors="ignore",
            stderr=subprocess.DEVNULL,
            timeout=3.0,
            creationflags=creation_flags,
            startupinfo=si,
        ).strip()
        if not cmd_line:
            return False
        norm_cmd = cmd_line.replace("/", "\\").lower()
        norm_base = str(BASE_DIR.resolve()).replace("/", "\\").lower()
        return ("server.py" in norm_cmd) and (norm_base in norm_cmd)
    except Exception:
        return False


def _free_port_on_windows(port: int) -> bool:
    """若目标端口被当前目录旧的跑团服务进程占用，自动静默清理释放端口，避免 Errno 10048 与误杀无关服务"""
    current_pid = os.getpid()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.35)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return False
    except Exception:
        return False

    print(f"  [Info] Port {port} is occupied. Checking owning process...")
    if os.name == "nt":
        try:
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            si = subprocess.STARTUPINFO()
            si.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
            si.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
            out = subprocess.check_output(
                ["netstat", "-ano", "-p", "TCP"],
                encoding="gbk",
                errors="ignore",
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
                startupinfo=si
            )
            pids_to_kill = set()
            target_suffix = f":{port}"
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[0].upper() == "TCP":
                    local_addr = parts[1]
                    state = parts[3].upper()
                    pid_str = parts[4]
                    if local_addr.endswith(target_suffix) and state == "LISTENING":
                        if pid_str.isdigit():
                            pid = int(pid_str)
                            if pid > 0 and pid != current_pid:
                                pids_to_kill.add(pid)
            killed_any = False
            for pid in pids_to_kill:
                img_name = _get_process_image_name(pid)
                if "python" not in img_name or not _is_own_trpg_server_process(pid, creation_flags, si):
                    print(f"  [Warn] Port {port} is held by another service (PID {pid}, {img_name or 'unknown'}); not killing it.")
                    continue
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creation_flags,
                    startupinfo=si
                )
                killed_any = True
            if killed_any:
                time.sleep(0.5)
                return True
        except Exception:
            pass
    return False


def main():
    port = 8765
    try:
        if "--port" in sys.argv:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        elif os.environ.get("TRPG_PORT"):
            port = int(os.environ["TRPG_PORT"])
    except (ValueError, IndexError):
        port = 8765

    host = "0.0.0.0"
    try:
        if "--host" in sys.argv:
            host = str(sys.argv[sys.argv.index("--host") + 1]).strip() or "0.0.0.0"
        elif os.environ.get("TRPG_HOST"):
            host = str(os.environ["TRPG_HOST"]).strip() or "0.0.0.0"
    except IndexError:
        host = "0.0.0.0"

    no_browser = "--no-browser" in sys.argv
    global SERVER_PORT, _PENDING_BROWSER_OPEN_URL, _WAS_PORT_REPLACED
    SERVER_PORT = port
    was_replaced = _free_port_on_windows(port)
    _WAS_PORT_REPLACED = was_replaced
    _PENDING_BROWSER_OPEN_URL = None if no_browser else f"http://127.0.0.1:{port}"
    net_info = get_network_info()

    print("==================================================")
    print(f"  AI TRPG ({APP_VERSION})")
    print(f"  Local  http://127.0.0.1:{port}")
    if host == "0.0.0.0":
        print(f"  LAN    {net_info['lan_url']}")
    else:
        print(f"  Host   http://{host}:{port}")
    print("==================================================")

    uvicorn.run(app, host=host, port=port, reload=False)

if __name__ == "__main__":
    main()

