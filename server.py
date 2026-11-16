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
import zipfile
import base64
import importlib
import importlib.util
from contextlib import asynccontextmanager
from urllib.parse import urlparse, quote
import httpx
import uvicorn
import webbrowser
from PIL import Image
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Callable, Awaitable

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
    DEFAULT_FAST_TRPG_SYSTEM_PROMPT,
    upgrade_legacy_global_protocol_prompt,
    normalize_ui_modules,
    build_ui_modules_spec_block,
    build_content_scale_prompt_block,
    build_status_module_prompt,
    is_free_chat_project,
    is_simple_trpg_project,
    _detect_system_ram_gib,
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
    HF_DOWNLOAD_TASKS,
    set_active_web_server_port,
    is_self_workbench_url,
    _is_loopback_only_url,
)

# 跟踪后台正在生成的对话任务与实时增量文本，防止手机刷新或网络抖动中断生成
ACTIVE_BG_TASKS: Dict[str, asyncio.Task] = {}
ACTIVE_PARTIAL_TEXT: Dict[str, str] = {}
GEN_SEQ: Dict[str, int] = {}


def _bump_gen_seq(chat_id: str) -> int:
    """递增对话级生成序号，用于拦截停止/删除/连发新消息期间尚处于前置准备阶段的旧请求晚到覆写"""
    nxt = GEN_SEQ.get(chat_id, 0) + 1
    GEN_SEQ[chat_id] = nxt
    return nxt

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
    "max_tokens": 8192,
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
    "global_system_protocol_prompt": "",
}

# 默认初始游戏 1：高级跑团（完整状态栏 + 默认开启思考）
DEFAULT_PROJECT = {
    "id": "proj_default",
    "name": "高级跑团",
    "simple_mode": False,
    "cot_enabled": True,
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
        "请根据玩家当前选用的【开场白】或挂载的【角色卡】自动适配世界观与文风（奇幻冒险/悬疑跑团/赛博修仙/日常情感张力），始终以极具画面感与感官细节（光影、声响、气味、微表情）的第二人称（「你」）叙事。NPC 拥有独立动机、秘密与性格底线，绝不无脑顺从玩家；严禁代替玩家做决定或抢说玩家台词。\n\n"
        + DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT
    ),
    "system_protocol_prompt": "",
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

# 默认初始游戏 0：极速跑团（无状态栏 + 自带折叠记忆区 + 默认关闭思考，低配秒回）
DEFAULT_FAST_TRPG_PROJECT = {
    "id": "proj_fast_trpg",
    "name": "极速跑团",
    "author": "Easy-TRPG",
    "icon": "",
    "avatar": "",
    "category": "极速跑团",
    "description": "",
    "tags": [],
    "simple_mode": True,
    "cot_enabled": False,
    "status_panel_enabled": False,
    "opening_greetings": copy.deepcopy(DEFAULT_PROJECT["opening_greetings"]),
    "ui_modules": [],
    "system_prompt": DEFAULT_FAST_TRPG_SYSTEM_PROMPT,
    "system_protocol_prompt": "",
    "prefix": "",
    "suffix": "",
    "max_context_turns": 10,
    "erotic_level": 0,
    "violence_level": 0,
    "auto_summarize": True,
    "use_global_params": True,
    "created_at": time.time(),
    "updated_at": time.time(),
}

# 默认初始游戏 2：聊天（100% 纯净网页版 AI，无任何功能栏、无任何提示词、无任何预设开场白）
DEFAULT_FREE_CHAT_UI_MODULES: List[Dict[str, Any]] = []

DEFAULT_FREE_CHAT_PROJECT = {
    "id": "proj_free_chat",
    "name": "聊天",
    "simple_mode": False,
    "cot_enabled": True,
    "icon": "",
    "avatar": "",
    "category": "聊天",
    "description": "",
    "tags": [],
    "status_panel_enabled": False,
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

def build_hardware_adapted_default_settings(base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """首次启动（或点击硬件推荐）时，根据本机显卡显存、内存与本地引擎环境自动分配最佳上下文长度、轮次记忆与默认入口"""
    cfg = {**copy.deepcopy(DEFAULT_SETTINGS), **(copy.deepcopy(base) if isinstance(base, dict) else {})}
    vram_mib = detect_gpu_vram_mib()
    sys_ram_gib = _detect_system_ram_gib()
    has_local_env = (BASE_DIR / "engine").exists() or bool(get_installed_local_model_ids(cfg.get("custom_model_paths") or []))

    if vram_mib >= 28000 or (sys.platform == "darwin" and sys_ram_gib >= 48):
        cfg.update({
            "context_mode": "tokens",
            "context": 96,
            "max_context_turns": 96,
            "max_context_k": 96,
            "keep_recent_messages": 10,
            "worldbook_scan_depth": 5,
            "max_tokens": 8192,
            "thinking_budget": 1024,
            "auto_summarize": True,
            "hw_tier_label": f"旗舰配置 ({round(vram_mib/1024) if vram_mib else sys_ram_gib}G · 96K)",
        })
        if base is None:
            cfg["active_project_id"] = "proj_default"
    elif vram_mib >= 20000 or (sys.platform == "darwin" and sys_ram_gib >= 32):
        cfg.update({
            "context_mode": "tokens",
            "context": 40,
            "max_context_turns": 40,
            "max_context_k": 64,
            "keep_recent_messages": 8,
            "worldbook_scan_depth": 5,
            "max_tokens": 8192,
            "thinking_budget": 1024,
            "auto_summarize": True,
            "hw_tier_label": f"高配显存 ({round(vram_mib/1024) if vram_mib else sys_ram_gib}G · 64K)",
        })
        if base is None:
            cfg["active_project_id"] = "proj_default"
    elif vram_mib > 10240:
        cfg.update({
            "context_mode": "turns",
            "context": 16,
            "max_context_turns": 16,
            "max_context_k": 32,
            "keep_recent_messages": 6,
            "worldbook_scan_depth": 4,
            "max_tokens": 8192,
            "thinking_budget": 1024,
            "auto_summarize": True,
            "hw_tier_label": f"主流独显 ({round(vram_mib/1024)}G · 16轮+32K)",
        })
        if base is None:
            cfg["active_project_id"] = "proj_fast_trpg"
    elif vram_mib > 0 or has_local_env:
        v_str = f"{round(vram_mib/1024)}G · " if vram_mib > 0 else ""
        cfg.update({
            "context_mode": "turns",
            "context": 10,
            "max_context_turns": 10,
            "max_context_k": 32,
            "keep_recent_messages": 6,
            "worldbook_scan_depth": 3,
            "max_tokens": 8192,
            "thinking_budget": 1024,
            "auto_summarize": True,
            "hw_tier_label": f"轻量极速档 ({v_str}10轮+32K)",
        })
        if base is None:
            cfg["active_project_id"] = "proj_fast_trpg"
    else:
        cfg.update({
            "context_mode": "tokens",
            "context": 64,
            "max_context_turns": 64,
            "max_context_k": 96,
            "keep_recent_messages": 8,
            "worldbook_scan_depth": 5,
            "max_tokens": 8192,
            "thinking_budget": 1024,
            "auto_summarize": True,
            "hw_tier_label": "在线API档 (96K)",
        })
        if base is None:
            cfg["active_project_id"] = "proj_default"

    cfg["hw_profile_initialized"] = True
    return cfg


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
                print(f"[Warn] 读取用户配置 settings.json 失败 ({e})，本次临时使用默认配置")
                return copy.deepcopy(DEFAULT_SETTINGS)
            except Exception as e:
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
                needs_save = False
                if (
                    not saved.get("hw_profile_initialized")
                    and not str(saved.get("api_key") or "").strip()
                    and not str(saved.get("base_url") or "").strip()
                    and not str(saved.get("model") or "").strip()
                ):
                    chats_dir = get_user_chats_dir(username)
                    has_any_chats = any(chats_dir.glob("*.json")) if chats_dir.exists() else False
                    if not has_any_chats:
                        merged = build_hardware_adapted_default_settings()
                        needs_save = True
                if merged.get("global_system_protocol_prompt"):
                    merged["global_system_protocol_prompt"] = ""
                    needs_save = True
                if needs_save:
                    try:
                        save_user_settings(username, merged)
                    except Exception as e:
                        print(f"[Warn] 保存自动初始化/升级后的配置失败: {e}")
                return merged
        default_copy = build_hardware_adapted_default_settings()
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
    if (
        username in _WORKSPACE_READY
        and settings_path.exists()
        and (projects_dir / "proj_fast_trpg.json").exists()
        and (projects_dir / "proj_default.json").exists()
        and (projects_dir / "proj_free_chat.json").exists()
    ):
        return
    if not settings_path.exists():
        save_user_settings(username, build_hardware_adapted_default_settings())

    fast_trpg_path = projects_dir / "proj_fast_trpg.json"
    if not fast_trpg_path.exists():
        atomic_write_json(fast_trpg_path, normalize_project_schema(DEFAULT_FAST_TRPG_PROJECT), ensure_ascii=False, indent=2)

    default_proj_path = projects_dir / "proj_default.json"
    if not default_proj_path.exists():
        atomic_write_json(default_proj_path, normalize_project_schema(DEFAULT_PROJECT), ensure_ascii=False, indent=2)
    else:
        try:
            with open(default_proj_path, "r", encoding="utf-8") as f:
                raw_def = json.load(f)
            if isinstance(raw_def, dict):
                changed_def = False
                if raw_def.get("name") in ("默认游戏", "跑团游戏", "跑团"):
                    raw_def["name"] = "高级跑团"
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
                legacy_def_proto = str(raw_def.get("system_protocol_prompt") or "").strip()
                if legacy_def_proto:
                    upgraded_def_proto = upgrade_legacy_global_protocol_prompt(legacy_def_proto, allow_empty=True).strip()
                    cur_def_sys = str(raw_def.get("system_prompt") or "").strip()
                    if upgraded_def_proto and upgraded_def_proto not in cur_def_sys and "1. 【🎲 关键节点检定" not in cur_def_sys:
                        raw_def["system_prompt"] = f"{cur_def_sys}\n\n{upgraded_def_proto}".strip() if cur_def_sys else upgraded_def_proto
                    raw_def["system_protocol_prompt"] = ""
                    changed_def = True
                elif raw_def.get("system_protocol_prompt") is None:
                    raw_def["system_protocol_prompt"] = ""
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
            if pfile.name in ("proj_fast_trpg.json", "proj_default.json", "proj_free_chat.json"):
                continue
            with open(pfile, "r", encoding="utf-8") as f:
                raw_p = json.load(f)
            if not isinstance(raw_p, dict):
                continue
            p_name = str(raw_p.get("name") or "").strip()
            p_sys = str(raw_p.get("system_prompt") or "").strip()
            p_mods = raw_p.get("ui_modules")
            p_mod_ids = {str(m.get("id") or "") for m in (p_mods or []) if isinstance(m, dict)}
            changed_p = False
            _sp = str(raw_p.get("system_protocol_prompt") or "").strip()
            if p_name.startswith(("新游戏", "新剧本", "新企划")) and not p_sys:
                if p_mod_ids and p_mod_ids.issubset({"mod_think", "mod_story", "mod_stats", "mod_equip", "mod_inv", "mod_npc", "mod_info", "mod_choices"}):
                    raw_p["ui_modules"] = []
                    raw_p["status_panel_enabled"] = False
                    changed_p = True
                if _sp:
                    raw_p["system_protocol_prompt"] = ""
                    changed_p = True
                raw_og_list = raw_p.get("opening_greetings")
                if isinstance(raw_og_list, list) and len(raw_og_list) == 1 and isinstance(raw_og_list[0], dict) and raw_og_list[0].get("content") == "开始游戏":
                    raw_p["opening_greetings"] = []
                    changed_p = True
            elif _sp:
                if _sp not in p_sys:
                    raw_p["system_prompt"] = f"{p_sys}\n\n{_sp}".strip() if p_sys else _sp
                raw_p["system_protocol_prompt"] = ""
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
        main_mod = sys.modules.get("__main__")
        is_update_restart = bool(
            globals().get("_PENDING_RESTART_AFTER_UPDATE", False)
            or getattr(main_mod, "_PENDING_RESTART_AFTER_UPDATE", False)
        )
        if not is_update_restart:
            ee_live = sys.modules.get("enterprise_engine")
            if ee_live is not None and hasattr(ee_live, "shutdown_local_engines"):
                await ee_live.shutdown_local_engines()
            else:
                await shutdown_local_engines()


# ==================== FastAPI 应用与路由 ====================
APP_VERSION = "alpha 1.6"
_SERVER_BOOT_ID = uuid.uuid4().hex[:10]
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
        raw_html = index_path.read_text(encoding="utf-8")
        try:
            _st_mtime = max(int(p.stat().st_mtime) for p in STATIC_DIR.glob("*") if p.is_file())
        except Exception:
            _st_mtime = 0
        ver_tag = f"{re.sub(r'[^a-zA-Z0-9._-]+', '_', APP_VERSION)}_{_SERVER_BOOT_ID}_{_st_mtime}" 
        raw_html = re.sub(
            r'(/static/[a-zA-Z0-9._/-]+\.(?:js|css))(?:\?v=[^"\'>\s]*)?',
            rf"\1?v={ver_tag}",
            raw_html,
        )
        raw_html = re.sub(
            r"<title>AI 跑团[^<]*</title>",
            f"<title>AI 跑团 ({APP_VERSION})</title>",
            raw_html,
            count=1,
        )
        return HTMLResponse(
            content=raw_html,
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
    target["frequency_penalty"] = safe_float(target.get("frequency_penalty"), 0.05)
    target["presence_penalty"] = safe_float(target.get("presence_penalty"), 0.20)
    target["top_p"] = safe_float(target.get("top_p"), 0.90)
    target["top_k"] = max(0, safe_int(target.get("top_k"), 40))
    target["min_p"] = safe_float(target.get("min_p"), 0.06)
    target["max_tokens"] = max(64, safe_int(target.get("max_tokens"), 8192))
    target["context"] = max(1, safe_int(target.get("context", target.get("max_context_turns", 96)), 96))
    target["max_context_turns"] = target["context"]
    target["max_context_k"] = max(4, safe_int(target.get("max_context_k"), 96))
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
        self_url_warnings: List[str] = []
        if is_self_workbench_url(str(current.get("base_url") or "")):
            current["base_url"] = ""
            if "base_url" in payload and str(payload.get("base_url") or "").strip():
                self_url_warnings.append(
                    "检测到填入的是本工作台自己的网页地址，已自动清空修正（用本地模型无需填地址，直接在模型列表点「选用」即可；用在线 API 请填服务商地址）"
                )
        if is_self_workbench_url(str(current.get("local_base_url") or "")):
            current["local_base_url"] = ""
            if str(current.get("local_mode") or "").lower() == "manual":
                current["local_mode"] = "auto"
            if "local_base_url" in payload and str(payload.get("local_base_url") or "").strip():
                self_url_warnings.append(
                    "检测到填入的是本工作台自己的网页地址，已自动恢复为「自动识别」模式（把 .gguf 放入 model 文件夹即可直接识别，无需填网页地址）"
                )
        if any(k in payload for k in ("erotic_level", "violence_level", "erotic_enabled", "violence_enabled")):
            if "erotic_level" in payload:
                current["erotic_level"] = max(0, min(5, safe_int(payload.get("erotic_level"), 3)))
            if "violence_level" in payload:
                current["violence_level"] = max(0, min(5, safe_int(payload.get("violence_level"), 3)))
            if "erotic_enabled" in payload:
                current["erotic_enabled"] = bool(payload.get("erotic_enabled"))
            if "violence_enabled" in payload:
                current["violence_enabled"] = bool(payload.get("violence_enabled"))
            active_pid = sanitize_id(current.get("active_project_id") or "proj_default")
            projects_dir_sync = get_user_projects_dir(username)
            for cand_pfile in projects_dir_sync.glob("*.json"):
                try:
                    with open(cand_pfile, "r", encoding="utf-8") as f:
                        raw_proj = json.load(f)
                    if not isinstance(raw_proj, dict):
                        continue
                    is_active_proj = (cand_pfile.stem == active_pid)
                    proj_changed = False
                    if is_active_proj:
                        if "erotic_level" in payload:
                            raw_proj["erotic_level"] = current["erotic_level"]
                            proj_changed = True
                        if "violence_level" in payload:
                            raw_proj["violence_level"] = current["violence_level"]
                            proj_changed = True
                        if "erotic_enabled" in payload:
                            raw_proj["erotic_enabled"] = current["erotic_enabled"]
                            proj_changed = True
                        if "violence_enabled" in payload:
                            raw_proj["violence_enabled"] = current["violence_enabled"]
                            proj_changed = True
                    if proj_changed:
                        atomic_write_json(cand_pfile, raw_proj, ensure_ascii=False, indent=2)
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

    # 严禁在切换模型或保存设置时后台自动预加载本地大模型（避免无故占用数十 GB 显存/内存）；仅在实际发送消息或运行性能测试时按需启动

    resp_out: Dict[str, Any] = {"status": "ok", "settings": mask_settings_for_client(current)}
    if self_url_warnings:
        resp_out["self_url_warning"] = "；".join(self_url_warnings)
    return resp_out


@app.post("/api/local_models/unload")
async def unload_local_models_endpoint(_: None = Depends(require_loopback)):
    """一键停止后台所有本地推理引擎（Strata / Ollama 驻留权重 / llama-server）并释放显存与内存"""
    unloaded_items: List[str] = []
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=4.0) as client:
            ps_resp = await client.get("http://127.0.0.1:11434/api/ps")
            if ps_resp.status_code == 200:
                for active_m in ps_resp.json().get("models", []):
                    m_name = active_m.get("name")
                    if m_name:
                        await client.post("http://127.0.0.1:11434/api/generate", json={"model": m_name, "keep_alive": 0})
                        unloaded_items.append(f"Ollama:{m_name}")
    except Exception:
        pass

    ee_live = sys.modules.get("enterprise_engine")
    if ee_live is not None and hasattr(ee_live, "shutdown_local_engines"):
        await ee_live.shutdown_local_engines()
    else:
        await shutdown_local_engines()

    def _sweep_residual_engines() -> None:
        if os.name == "nt":
            cf = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            for imgs in (["strata.exe", "strata-vision.exe"], ["llama-server.exe"]):
                cmd = ["taskkill", "/F"]
                for im in imgs:
                    cmd.extend(["/IM", im])
                cmd.append("/T")
                try:
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=cf, timeout=4)
                except Exception:
                    pass

    await asyncio.to_thread(_sweep_residual_engines)
    detail_suffix = f"（含 {', '.join(unloaded_items)}）" if unloaded_items else ""
    return {"ok": True, "message": f"已关闭本地推理引擎并释放显存与内存{detail_suffix}"}

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
    if raw_base_url and is_self_workbench_url(raw_base_url):
        raw_base_url = ""
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
    remote_fetch_error: str = ""
    used_direct_fallback: bool = False
    # 只要有归一化后的 base_url，且 (用户填了 raw_base_url，或填了 api_key 且识别出了官方协议，或手动选择了非 openai/auto 的自带默认地址协议)
    should_fetch_remote = bool(base_url) and bool(raw_base_url or api_key or api_protocol in ("gemini", "claude", "ollama"))
    if should_fetch_remote:
        headers = dict(norm["headers"])
        headers.pop("Content-Type", None)
        headers.setdefault("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Easy-TRPG/1.5")
        headers.setdefault("Accept", "application/json")

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
                    elif isinstance(m, str) and m.strip():
                        out.append(m.strip())
                return out
            except Exception:
                return []

        # 构建代理与直连回退链：若用户在设置中开启了代理但本地代理软件未启动（如 127.0.0.1:7890 拒绝连接），自动无缝回退直连！
        proxy_candidates: List[Optional[str]] = []
        if proxy:
            proxy_candidates.append(proxy)
            if os.name == "nt":
                try:
                    import winreg
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as rk:
                        p_en, _ = winreg.QueryValueEx(rk, "ProxyEnable")
                        p_srv, _ = winreg.QueryValueEx(rk, "ProxyServer")
                        if p_en and p_srv and isinstance(p_srv, str):
                            sys_px = p_srv.strip()
                            if "://" not in sys_px and "=" not in sys_px:
                                sys_px = f"http://{sys_px}"
                            if sys_px.startswith("http") and sys_px not in proxy_candidates:
                                proxy_candidates.append(sys_px)
                except Exception:
                    pass
            proxy_candidates.append(None)
        else:
            proxy_candidates.append(None)

        for cand_idx, cur_proxy in enumerate(proxy_candidates):
            try:
                async with httpx.AsyncClient(proxy=cur_proxy, trust_env=False, timeout=8.0, follow_redirects=True) as client:
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

                    if isinstance(resp_models, Exception):
                        remote_fetch_error = f"连接失败 ({type(resp_models).__name__})"
                        continue
                    st_code = getattr(resp_models, "status_code", 0)
                    if st_code in (401, 403):
                        remote_fetch_error = f"API Key 鉴权失败或被拦截 (HTTP {st_code})"
                    elif st_code >= 400:
                        remote_fetch_error = f"接口返回 HTTP {st_code}"

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

                    if raw_models:
                        remote_fetch_error = ""
                        if proxy and cur_proxy is None and cand_idx > 0:
                            used_direct_fallback = True
                        # 若用户填写了不含 /v1 的地址且归一化补全后的地址成功拿到模型，同步保存归一化地址
                        if raw_base_url and base_url != raw_base_url:
                            with _USER_SETTINGS_LOCK:
                                latest_s = load_user_settings(username)
                                if (latest_s.get("base_url") or "").strip().rstrip("/") == raw_base_url:
                                    latest_s["base_url"] = base_url
                                    save_user_settings(username, latest_s)
                                    settings = latest_s
                        break
                    if st_code in (401, 403):
                        break
            except Exception as e:
                remote_fetch_error = f"网络异常: {e}"
                print(f"获取模型列表或价格失败 (proxy={cur_proxy}): {e}")

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
        "remote_fetch_error": remote_fetch_error,
        "used_direct_fallback": used_direct_fallback,
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
@app.post("/api/settings/hardware_recommend")
def apply_hardware_recommended_settings(username: str = Depends(get_current_user)):
    with _USER_SETTINGS_LOCK:
        cur = load_user_settings(username)
        tuned = build_hardware_adapted_default_settings(base=cur)
        save_user_settings(username, tuned)
    return {"status": "ok", "settings": tuned, "hw_tier_label": tuned.get("hw_tier_label", "")}

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
        if pid == "proj_fast_trpg":
            return (0, 0)
        if pid == "proj_default":
            return (1, 0)
        if pid == "proj_free_chat":
            return (2, 0)
        return (3, -float(item.get("updated_at", 0) or 0))

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

        if settings_changed:
            save_user_settings(username, latest_settings)

    return {"status": "ok", "project": data}

@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str, username: str = Depends(get_current_user)):
    project_id = sanitize_id(project_id)
    if project_id in ("proj_fast_trpg", "proj_default", "proj_free_chat"):
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

    try:
        with _USER_SETTINGS_LOCK:
            cur_settings = load_user_settings(username)
            if cur_settings.get("active_project_id") == project_id:
                cur_settings["active_project_id"] = "proj_default"
                save_user_settings(username, cur_settings)
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
        asst_idxs = [idx for idx, m in enumerate(unsummarized) if isinstance(m, dict) and m.get("role") == "assistant"]
        keep_st_set = set(asst_idxs[-2:])
        hist_chars = 0
        for idx, m in enumerate(unsummarized):
            if not isinstance(m, dict):
                continue
            if m.get("role") == "assistant":
                txt = strip_thinking_blocks(m.get("content", ""))
                if idx not in keep_st_set:
                    txt = _strip_historical_status_block(txt)
            else:
                txt = str(m.get("content") or "")
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
    _bump_gen_seq(chat_id)
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
    _bump_gen_seq(chat_id)
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
    old_sum = safe_int(data.get("summarized_count"), 0)
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

def _strip_historical_status_block(text: str) -> str:
    """剥离远期历史轮次中高度重复的 <status>...</status> 状态面板（仅用于发给大模型的上下文减负，磁盘聊天记录与最近 2 轮状态栏 100% 原样保留）"""
    if not text or ("<status" not in text.lower() and "＜status＞" not in text.lower()):
        return text
    cleaned = re.sub(
        r"```(?:xml|html|text|markdown|status)?\s*<status(?:\s+[^>]*)?>[\s\S]*?</status>\s*```",
        "",
        text,
        flags=re.I,
    )
    cleaned = re.sub(r"<status(?:\s+[^>]*)?>[\s\S]*?</status>", "", cleaned, flags=re.I)
    cleaned = re.sub(r"＜status＞[\s\S]*?＜/status＞", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned if cleaned else text


def _strip_distilled_artifact_tags(text: str) -> str:
    """清除部分微调量化模型蒸馏语料中残留的 <localjavatoolN> 伪工具占位标签，防止污染后续轮次上下文诱发提前截断"""
    if not text or "localjavatool" not in text.lower():
        return text
    cleaned = re.sub(r"</?localjavatool\d*\s*>", "", text, flags=re.I)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip() if cleaned.strip() else cleaned


def _strip_historical_memory_block(text: str) -> str:
    """剥离远期历史轮次中已过期的 <memory>...</memory> 记忆区（最近 2 轮完整保留长期+短期记忆，磁盘聊天记录 100% 原样保留）"""
    text = _strip_distilled_artifact_tags(text)
    if not text or ("<memory" not in text.lower() and "＜memory＞" not in text.lower()):
        return text
    cleaned = re.sub(
        r"```(?:xml|html|text|markdown|memory)?\s*<memory(?:\s+[^>]*)?>[\s\S]*?</memory>\s*```",
        "",
        text,
        flags=re.I,
    )
    cleaned = re.sub(r"<memory(?:\s+[^>]*)?>[\s\S]*?</memory>", "", cleaned, flags=re.I)
    cleaned = re.sub(r"＜memory＞[\s\S]*?＜/memory＞", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned if cleaned else text


async def generate_summary(existing_summary: str, messages_to_compress: List[Dict[str, Any]], settings: Dict[str, Any], model_override: str = "") -> Optional[str]:
    """调用当前对话的大模型将历史长对话归档为详实的数千字剧情前情与状态档案（不作激进删减）
    返回新生成的总结；失败/无可压缩内容时返回 None（调用方据此决定是否推进 summarized_count，避免静默丢弃历史）"""
    if not messages_to_compress:
        return None

    last_asst_in_batch = -1
    for _i in range(len(messages_to_compress) - 1, -1, -1):
        if messages_to_compress[_i].get("role") == "assistant":
            last_asst_in_batch = _i
            break

    dialogue_snippets = []
    per_msg_limit = min(2200, max(700, 32000 // max(1, len(messages_to_compress))))
    for idx_m, m in enumerate(messages_to_compress):
        role_label = "【玩家】" if m.get("role") == "user" else "【主持人】"
        raw_content = m.get("content", "")
        text = strip_thinking_blocks(raw_content) if m.get("role") == "assistant" else raw_content.strip()
        if not text:
            text = raw_content.strip()
        # 仅保留待归档片段最后一条 assistant 的完整 <status> 快照，更早轮次剥离重复装备栏以防挤占剧情摘要空间
        if m.get("role") == "assistant" and idx_m != last_asst_in_batch:
            text = _strip_historical_status_block(text)
        cur_limit = per_msg_limit + 900 if idx_m == last_asst_in_batch else per_msg_limit
        cur_half = max(300, cur_limit // 2)
        if len(text) > cur_limit:
            text = text[:cur_half] + "\n……（中段细节省略）……\n" + text[-cur_half:]
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
        elif ep["engine"] == "llama":
            sum_req_json["stop"] = list(_LOCAL_STOP_SEQUENCES)
            sum_req_json["reasoning_budget"] = 0
            sum_req_json["chat_template_kwargs"] = {"enable_thinking": False}
            sum_req_json["repeat_penalty"] = 1.08
            sum_req_json["repeat_last_n"] = 2048
            sum_req_json["frequency_penalty"] = 0.12
            sum_req_json["cache_prompt"] = True
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

    if raw_already > 0 and raw_already >= cutoff:
        return {
            "status": "ignored",
            "detail": "暂无新的可压缩历史",
            "summary": chat_data.get("summary", ""),
            "summarized_count": raw_already,
        }
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
    cot_enabled: Optional[bool] = None

@app.post("/api/chat/stream")
async def chat_stream(req: SendMessageRequest, username: str = Depends(get_current_user)):
    req.chat_id = sanitize_id(req.chat_id)
    my_seq = _bump_gen_seq(req.chat_id)
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
    if GEN_SEQ.get(req.chat_id) != my_seq:
        raise HTTPException(status_code=409, detail="请求已被停止或被新消息取代")

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
    elif project_id == "proj_fast_trpg":
        project_data = normalize_project_schema(DEFAULT_FAST_TRPG_PROJECT, global_defaults=settings)
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
    _eff_cfg_burl = "" if is_self_workbench_url(str(settings.get("base_url") or "")) else str(settings.get("base_url") or "").strip()
    _eff_cfg_lurl = "" if is_self_workbench_url(str(settings.get("local_base_url") or "")) else str(settings.get("local_base_url") or "").strip()
    if not model or (not _eff_cfg_burl and not settings.get("api_key") and not _eff_cfg_lurl):
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
    rep_pen = safe_float(comp_params.get("repetition_penalty"), safe_float(settings.get("repetition_penalty"), 1.05))
    freq_pen = safe_float(comp_params.get("frequency_penalty"), safe_float(settings.get("frequency_penalty"), 0.05))
    pres_pen = safe_float(comp_params.get("presence_penalty"), safe_float(settings.get("presence_penalty"), 0.20))
    top_p = safe_float(comp_params.get("top_p"), safe_float(settings.get("top_p"), 0.90))
    top_k = max(0, safe_int(comp_params.get("top_k"), safe_int(settings.get("top_k"), 40)))
    min_p = safe_float(comp_params.get("min_p"), safe_float(settings.get("min_p"), 0.06))
    max_tok = max(64, safe_int(comp_params.get("max_tokens"), safe_int(settings.get("max_tokens"), 8192)))
    thinking_budget = max(0, safe_int(comp_params.get("thinking_budget"), safe_int(settings.get("thinking_budget"), 1024)))
    wb_scan_depth = max(1, safe_int(comp_params.get("worldbook_scan_depth"), safe_int(settings.get("worldbook_scan_depth"), 5)))

    raw_proj_sys = project_data.get("system_prompt", "").strip()
    if "【万物模块化输出协议" in raw_proj_sys:
        raw_proj_sys = raw_proj_sys.split("【万物模块化输出协议")[0].strip()
    raw_proj_sys = re.sub(r"\{\{\s*(?:UI_MODULES_SPEC|功能栏规范|模块规范)\s*\}\}", "", raw_proj_sys, flags=re.I).strip()
    base_system_prompt = interpolate_variables(raw_proj_sys, prompt_vars, chat_inputs)
    raw_proj_proto = "" if project_data.get("system_protocol_prompt") is None else str(project_data.get("system_protocol_prompt"))
    proj_proto_interp = interpolate_variables(
        upgrade_legacy_global_protocol_prompt(raw_proj_proto, allow_empty=True),
        prompt_vars,
        chat_inputs
    )
    global_proto = ""
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
    proj_for_spec["system_protocol_prompt"] = proj_proto_interp
    status_mod_prompt = interpolate_variables(
        build_status_module_prompt(proj_for_spec, global_proto),
        prompt_vars,
        chat_inputs
    )
    if status_mod_prompt:
        base_system_prompt = f"{base_system_prompt}\n\n{status_mod_prompt.strip()}".strip() if base_system_prompt else status_mod_prompt.strip()
    if is_simple_trpg_project(project_data):
        base_prefix = ""
        base_suffix = ""
    else:
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
        chat_data["summarized_count"] = min(safe_int(chat_data.get("summarized_count"), 0), len(chat_data["messages"]) - 1)
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
        if GEN_SEQ.get(req.chat_id) != my_seq:
            raise HTTPException(status_code=409, detail="请求已被停止或被新消息取代")
        input_char_cards = target_user_msg.get("character_cards") or []
        turn_user_msg_id = str(target_user_msg.get("id") or "")
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
        if GEN_SEQ.get(req.chat_id) != my_seq:
            raise HTTPException(status_code=409, detail="请求已被停止或被新消息取代")

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
        turn_user_msg_id = str(user_msg_record["id"])
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
    if (project_data.get("status_panel_enabled", True) is not False) and not is_free_chat_project(project_data) and not is_simple_trpg_project(project_data):
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
    already_summarized = min(safe_int(chat_data.get("summarized_count"), 0), max(0, len(history_messages) - 2))
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
    unsummarized_asst_indices = [
        idx_u for idx_u, hm_u in enumerate(unsummarized_history_pre) if hm_u.get("role") == "assistant"
    ]
    keep_status_pre_set = set(unsummarized_asst_indices[-2:])
    unsummarized_hist_tok = 0
    for idx_u, hm in enumerate(unsummarized_history_pre):
        if hm.get("role") == "assistant":
            hm_txt = strip_thinking_blocks(hm.get("content", ""))
            if idx_u not in keep_status_pre_set:
                hm_txt = _strip_historical_memory_block(_strip_historical_status_block(hm_txt))
        else:
            hm_txt = hm.get("content", "")
        unsummarized_hist_tok += _est_msg_tokens(hm_txt)

    exceeds_turns = (context_mode != "tokens") and (len(unsummarized_history_pre) > max_history_count)
    exceeds_tokens = (fixed_tok + unsummarized_hist_tok) > token_high_water

    pending_auto_summary: Optional[Dict[str, Any]] = None
    if auto_summarize and (exceeds_turns or exceeds_tokens):
        turn_overflow = 0
        if exceeds_turns:
            turn_overflow = max(already_summarized, len(history_messages) - min_auto_keep_msgs)

        token_overflow = 0
        if exceeds_tokens:
            acc_tok_pre = 0
            cutoff_idx = len(history_messages)
            for i in range(len(history_messages) - 1, already_summarized - 1, -1):
                hm = history_messages[i]
                hm_txt = strip_thinking_blocks(hm.get("content", "")) if hm.get("role") == "assistant" else hm.get("content", "")
                m_tok = _est_msg_tokens(hm_txt)
                if acc_tok_pre + m_tok > compress_target_hist_tok and (len(history_messages) - i) >= min_token_keep_msgs:
                    break
                acc_tok_pre += m_tok
                cutoff_idx = i
            token_overflow = max(already_summarized, min(cutoff_idx, len(history_messages) - min_token_keep_msgs))

        overflow_count = max(already_summarized, max(turn_overflow, token_overflow))
        if overflow_count - already_summarized >= 2:
            auto_anchor_idx = overflow_count - 1 if 0 < overflow_count <= len(history_messages) else None
            auto_anchor_id = (
                str(history_messages[auto_anchor_idx].get("id") or "")
                if auto_anchor_idx is not None and isinstance(history_messages[auto_anchor_idx], dict)
                else ""
            )
            pending_auto_summary = {
                "overflow_count": overflow_count,
                "to_compress": history_messages[already_summarized:overflow_count],
                "auto_anchor_idx": auto_anchor_idx,
                "auto_anchor_id": auto_anchor_id,
            }

    model = (model or req.model or chat_data.get("model") or settings.get("model") or "").strip()
    ui_mods_norm = normalize_ui_modules(project_data.get("ui_modules"))
    think_mod_obj = next(
        (m for m in ui_mods_norm if m.get("type") == "thinking_fold" or m.get("id") == "mod_think"),
        None
    )
    # UI 是否展示折叠思考卡片（think_mod_enabled）与底层模型是否开启后台思考推演（model_think_enabled）彻底解耦：
    # 只要 thinking_budget > 0，本地模型即可在受控硬上限内先做简短导演规划，前端未挂载思考栏时自动静默隐藏
    think_mod_enabled = bool(think_mod_obj and think_mod_obj.get("enabled", True) is not False)
    is_simple_trpg = is_simple_trpg_project(project_data)
    effective_cot_on = (
        bool(req.cot_enabled)
        if req.cot_enabled is not None
        else bool(project_data.get("cot_enabled", False if is_simple_trpg else True))
    )
    if effective_cot_on and thinking_budget <= 0:
        thinking_budget = 1024
    model_think_enabled = bool(effective_cot_on and thinking_budget > 0)

    async def _assemble_turn_context() -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[str]]:
        cur_fixed_tok = (
            _est_msg_tokens(final_system_prompt)
            + _est_msg_tokens(active_cards_system_block)
            + _est_msg_tokens(chat_data.get("summary", ""))
            + _est_msg_tokens(user_final_text)
        )
        cur_avail_hist_tok = max(1000, max_token_budget - cur_fixed_tok)
        already_summarized_idx = min(safe_int(chat_data.get("summarized_count", 0), 0), max(0, len(history_messages) - 2))
        unsummarized_history = history_messages[already_summarized_idx:]
        if context_mode != "tokens" and len(unsummarized_history) > max_history_count:
            unsummarized_history = unsummarized_history[-max_history_count:]

        selected_rev = []
        acc_tok = 0
        seen_asst_rev = 0
        for m in reversed(unsummarized_history):
            if m.get("role") == "assistant":
                m_txt = strip_thinking_blocks(m.get("content", ""))
                seen_asst_rev += 1
                if seen_asst_rev > 2:
                    m_txt = _strip_historical_memory_block(_strip_historical_status_block(m_txt))
            else:
                m_txt = m.get("content", "")
            m_tok = _est_msg_tokens(m_txt)
            if acc_tok + m_tok > cur_avail_hist_tok and len(selected_rev) >= keep_recent_msgs:
                break
            acc_tok += m_tok
            selected_rev.append(m)
        active_history = list(reversed(selected_rev))

        assembled_msgs: List[Dict[str, Any]] = []
        system_sections: List[str] = []
        if final_system_prompt:
            system_sections.append(final_system_prompt)
        if active_cards_system_block:
            system_sections.append(active_cards_system_block)

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
            assembled_msgs.append({"role": "system", "content": "\n\n".join(system_sections)})

        effective_turn_user_images: List[str] = list(input_images) if input_images else []
        turn_image_set = set(effective_turn_user_images) | set(turn_raw_images or [])

        last_prev_user_idx = -1
        for idx_h in range(len(active_history) - 1, -1, -1):
            if active_history[idx_h].get("role", "user") == "user":
                last_prev_user_idx = idx_h
                break

        # 上下文去重减负策略：仅在最近 2 轮 assistant 回复中保留完整的 <status>...</status> 状态栏（确保 100% 跨轮状态与历史人物/物品继承），
        # 倒数第 3 轮及更早的历史 assistant 消息自动剥离重复的装备/状态块，彻底消除长上下文高重复锚定导致的呆滞与复读（磁盘聊天记录绝不删改）
        recent_full_status_asst_idxs = set(
            [idx_a for idx_a, ha in enumerate(active_history) if ha.get("role") == "assistant"][-2:]
        )

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
                    assembled_msgs.append({"role": "user", "content": content_parts})
                else:
                    assembled_msgs.append({"role": "user", "content": h_text})
            elif role == "assistant":
                raw_asst = h.get("content", "")
                clean_asst = _strip_distilled_artifact_tags(strip_thinking_blocks(raw_asst) or raw_asst)
                if idx_h not in recent_full_status_asst_idxs:
                    clean_asst = _strip_historical_memory_block(_strip_historical_status_block(clean_asst))
                assembled_msgs.append({"role": "assistant", "content": clean_asst})

        cur_turn_images = list(effective_turn_user_images)
        for c in (input_char_cards or []):
            if not isinstance(c, dict):
                continue
            c_name = str(c.get("name") or "未命名角色").strip()
            c_avatar = _resolve_avatar_to_data_url(username, str(c.get("avatar") or ""))
            if c_avatar and c_name not in sent_card_avatar_names:
                sent_card_avatar_names.add(c_name)
                cur_turn_images.extend(await _optimize_images_async([c_avatar], max_dim=768, quality=75, min_bytes=35_000))

        if cur_turn_images:
            content_parts = []
            for opt_img in await _optimize_images_async(cur_turn_images, max_dim=896, quality=76, min_bytes=70_000):
                content_parts.append({"type": "image_url", "image_url": {"url": opt_img}})
            content_parts.append({"type": "text", "text": user_final_text})
            assembled_msgs.append({"role": "user", "content": content_parts})
        else:
            assembled_msgs.append({"role": "user", "content": user_final_text})

        if active_card_depth_prompts:
            min_dp_idx = 1 if (assembled_msgs and assembled_msgs[0].get("role") == "system") else 0
            for dp_item in sorted(active_card_depth_prompts, key=lambda x: int(x.get("depth", 4)), reverse=True):
                dp_d = max(0, int(dp_item.get("depth", 4)))
                ins_idx = max(min_dp_idx, len(assembled_msgs) - dp_d)
                assembled_msgs.insert(ins_idx, {"role": dp_item["role"], "content": dp_item["content"]})

        log_snap = {
            "timestamp": time.time(),
            "model": model,
            "estimated_context_tokens": cur_fixed_tok + acc_tok,
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
                "thinking_budget": min(max(256, thinking_budget), 1536) if model_think_enabled else 0
            },
            "triggered_worldbooks": triggered_wb_logs,
            "triggered_worldbook": triggered_wb_logs,
            "applied_regex": list(applied_regex_logs),
            "assembled_messages": [
                {
                    "role": m["role"],
                    "content": m["content"] if isinstance(m["content"], str) else f"[多模态消息: 含文本与 {len(m['content'])-1} 张图片]"
                }
                for m in assembled_msgs
            ]
        }
        return assembled_msgs, log_snap, cur_turn_images

    api_messages: List[Dict[str, Any]] = []
    prompt_log_snapshot: Dict[str, Any] = {}
    turn_images: List[str] = list(input_images) if input_images else []
    if pending_auto_summary is None:
        api_messages, prompt_log_snapshot, turn_images = await _assemble_turn_context()

    if GEN_SEQ.get(req.chat_id) != my_seq:
        raise HTTPException(status_code=409, detail="请求已被停止或被新消息取代")

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
        nonlocal api_messages, prompt_log_snapshot, turn_images
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
        is_trpg_stream = (
            ((project_data.get("status_panel_enabled", True) is not False) or is_simple_trpg)
            and not is_free_chat_project(project_data)
        )
        stream_choices_enabled = is_simple_trpg or any(
            isinstance(m, dict) and m.get("enabled", True) is not False and (str(m.get("type") or "") == "action_choices" or str(m.get("id") or "") == "mod_choices")
            for m in ui_mods_norm
        )

        try:
            if pending_auto_summary is not None:
                await event_queue.put({"status": "正在压缩历史前情提要..."})
                try:
                    updated_summary = await generate_summary(
                        chat_data.get("summary", ""),
                        pending_auto_summary["to_compress"],
                        settings,
                        model_override=str(model or req.model or chat_data.get("model") or ""),
                    )
                    if updated_summary and GEN_SEQ.get(req.chat_id) == my_seq:
                        ov_cnt = pending_auto_summary["overflow_count"]
                        chat_data["summary"] = updated_summary
                        chat_data["summarized_count"] = ov_cnt
                        _patch_chat_file(
                            chat_file,
                            {
                                "summary": updated_summary,
                                "summarized_count": ov_cnt,
                                "updated_at": time.time(),
                            },
                            expected_cutoff_idx=pending_auto_summary["auto_anchor_idx"],
                            expected_cutoff_msg_id=pending_auto_summary["auto_anchor_id"] or None,
                        )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    print(f"自动总结执行跳过: {e}")
                api_messages, prompt_log_snapshot, turn_images = await _assemble_turn_context()

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
                if not cur_model or not cur_base_url or is_self_workbench_url(cur_base_url):
                    if not cur_model:
                        last_err_str = (
                            "尚未选择或下载 AI 模型：请先点击页面左下角「模型」按钮 —— "
                            "想用本机显卡跑团请切到「下载」一键下载本地模型（或将已有 .gguf 放入 model 文件夹），"
                            "想用在线服务请切到「API」填写接口地址与密钥后再开始游戏！"
                        )
                    else:
                        last_err_str = (
                            f"当前选中的模型「{cur_model}」尚未配置有效的接口地址（或本地模型文件已被移动）："
                            "请点击左下角「模型」重新选择已就绪的本地模型，或在「API」页填写服务商接口地址与密钥。"
                        )
                    await event_queue.put({"error": last_err_str})
                    return
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
                            if eff_max_tok >= 12288:
                                eff_max_tok = 8192
                            is_default_or_legacy = (
                                (eff_rep_pen >= 1.08 and eff_pres_pen >= 0.40)
                                or (eff_rep_pen <= 1.02 and eff_freq_pen == 0.0 and eff_pres_pen == 0.0)
                                or (abs(eff_rep_pen - 1.05) < 1e-6 and abs(eff_pres_pen - 0.20) < 1e-6 and abs(eff_freq_pen - 0.05) < 1e-6)
                                or (abs(eff_rep_pen - 1.05) < 1e-6 and abs(eff_pres_pen - 0.25) < 1e-6 and abs(eff_freq_pen - 0.0) < 1e-6)
                            )
                            if is_default_or_legacy:
                                if ep.get("engine") in ("llama", "ollama"):
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
                        total_output_budget = eff_max_tok if eff_max_tok > 0 else 8192
                        req_body["max_tokens"] = total_output_budget
                        if ep.get("protocol") not in ("claude", "gemini"):
                            if ep["is_local"] or eff_pres_pen != 0:
                                req_body["presence_penalty"] = eff_pres_pen
                            if ep["is_local"] or eff_freq_pen != 0:
                                req_body["frequency_penalty"] = eff_freq_pen

                        safe_think_budget = 0
                        max_think_chars_guard = 0
                        if ep["is_local"]:
                            req_body["stop"] = list(_LOCAL_STOP_SEQUENCES)
                            max_allowed_think = max(0, total_output_budget - 512)
                            safe_think_budget = (
                                min(max(256, thinking_budget), 1536, max_allowed_think)
                                if (model_think_enabled and max_allowed_think >= 256)
                                else 0
                            )
                            if ep["engine"] == "strata":
                                if safe_think_budget > 0:
                                    req_body["reasoning_effort"] = "low" if safe_think_budget <= 1024 else "medium"
                                    req_body["reasoning_budget_tokens"] = safe_think_budget
                                    # Strata 原生 C++/Python 引擎在 safe_think_budget 处自动闭合 </think>，外层熔断器留足余量做双保险
                                    max_think_chars_guard = max(900, int(safe_think_budget * 2.2))
                                else:
                                    req_body["reasoning_effort"] = "none"
                                    req_body["reasoning_budget_tokens"] = 0
                                    req_body["chat_template_kwargs"] = {"enable_thinking": False}
                                req_body["repetition_penalty"] = eff_rep_pen
                                req_body["penalty_last_n"] = 1024
                                req_body["top_k"] = top_k
                                req_body["min_p"] = min_p
                            elif ep["engine"] == "llama":
                                req_body["max_tokens"] = total_output_budget
                                if safe_think_budget > 0:
                                    capped_local_think = min(safe_think_budget, 1536)
                                    req_body["reasoning_budget"] = capped_local_think
                                    req_body["chat_template_kwargs"] = {"enable_thinking": True}
                                    max_think_chars_guard = max(900, int(capped_local_think * 2.2))
                                else:
                                    req_body["reasoning_budget"] = 0
                                    req_body["chat_template_kwargs"] = {"enable_thinking": False}
                                req_body["repeat_penalty"] = eff_rep_pen
                                req_body["repeat_last_n"] = 1024
                                req_body["top_k"] = top_k
                                req_body["min_p"] = min_p
                                req_body["dry_multiplier"] = 0.8
                                req_body["cache_prompt"] = True
                            elif ep["engine"] == "ollama":
                                # 所有模型统一口径：单次最大输出 (默认 8192) 总量包含 CoT 思考与正文
                                ollama_total_predict = total_output_budget
                                req_body["max_tokens"] = ollama_total_predict
                                if safe_think_budget > 0:
                                    capped_local_think = min(safe_think_budget, 1024)
                                    req_body["think"] = True
                                    req_body["thinking_budget_tokens"] = capped_local_think
                                    req_body["reasoning_budget"] = capped_local_think
                                    req_body["reasoning_budget_tokens"] = capped_local_think
                                    # Ollama /v1/chat/completions 不支持原生思考预算硬截断，启用流式熔断器严防雷霆思考十分钟
                                    max_think_chars_guard = max(900, int(capped_local_think * 2.0))
                                else:
                                    req_body["think"] = False
                                    req_body["reasoning_effort"] = "none"
                                    req_body["thinking_budget_tokens"] = 0
                                    req_body["reasoning_budget"] = 0
                                    req_body["reasoning_budget_tokens"] = 0
                                    req_body["chat_template_kwargs"] = {"enable_thinking": False}
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
                                if safe_think_budget > 0:
                                    capped_other_think = min(safe_think_budget, 1024)
                                    req_body["reasoning_budget"] = capped_other_think
                                    req_body["thinking_budget_tokens"] = capped_other_think
                                    max_think_chars_guard = max(450, int(capped_other_think * 1.6))
                                else:
                                    req_body["think"] = False
                                    req_body["reasoning_effort"] = "none"
                                    req_body["chat_template_kwargs"] = {"enable_thinking": False}

                        req_headers = ep.get("headers") or {
                            "Authorization": f"Bearer {cur_api_key}",
                            "Content-Type": "application/json"
                        }

                        async with httpx.AsyncClient(proxy=cur_proxy, trust_env=False, timeout=client_Timeout) as client:
                            think_budget_cut = False
                            captured_think_pieces: List[str] = []

                            async with client.stream(
                                "POST",
                                f"{cur_base_url}/chat/completions",
                                headers=req_headers,
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
                                last_think_status_len = 0
                                streamed_think_chars = 0
                                has_exited_think = False
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
                                                captured_think_pieces.append(reasoning_piece)
                                                streamed_think_chars += len(reasoning_piece)
                                                if think_mod_enabled:
                                                    if not in_reasoning_block:
                                                        out_piece += "<think>\n"
                                                        in_reasoning_block = True
                                                    out_piece += reasoning_piece
                                                else:
                                                    suppressed_reasoning_pieces.append(reasoning_piece)
                                                    if not collected_chunks and (
                                                        not sent_wait_status or (streamed_think_chars - last_think_status_len) >= 240
                                                    ):
                                                        sent_wait_status = True
                                                        last_think_status_len = streamed_think_chars
                                                        await event_queue.put({"status": f"AI 正在构思剧情走向... ({streamed_think_chars}字)"})
                                                if max_think_chars_guard > 0 and streamed_think_chars >= max_think_chars_guard and not has_exited_think:
                                                    think_budget_cut = True
                                                    break

                                            if content_piece:
                                                if in_reasoning_block:
                                                    out_piece += "\n</think>\n\n"
                                                    in_reasoning_block = False
                                                    has_exited_think = True

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
                                                            has_exited_think = True
                                                            content_piece = after_think
                                                        else:
                                                            cur_in_len = len(suppressed_think_buf)
                                                            if not sent_wait_status or (cur_in_len - last_think_status_len) >= 240:
                                                                sent_wait_status = True
                                                                last_think_status_len = cur_in_len
                                                                await event_queue.put({"status": f"AI 正在构思剧情走向... ({cur_in_len}字)"})
                                                            if max_think_chars_guard > 0 and cur_in_len >= max_think_chars_guard:
                                                                captured_think_pieces = [
                                                                    re.sub(r"^\s*<think(?:ing)?>\s*", "", suppressed_think_buf, flags=re.I)
                                                                ]
                                                                think_budget_cut = True
                                                                break
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
                                                        has_exited_think = True
                                                        content_piece = cand_buf

                                                if content_piece:
                                                    out_piece += content_piece

                                            if out_piece:
                                                combined_so_far = "".join(collected_chunks) + out_piece
                                                if (
                                                    think_mod_enabled
                                                    and max_think_chars_guard > 0
                                                    and not has_exited_think
                                                    and re.match(r"^\s*<think(?:ing)?(?:\s|>)", combined_so_far, flags=re.I)
                                                    and not re.search(r"</think(?:ing)?>", combined_so_far, flags=re.I)
                                                    and len(combined_so_far) >= max_think_chars_guard
                                                ):
                                                    captured_think_pieces = [
                                                        re.sub(r"^\s*<think(?:ing)?>\s*", "", combined_so_far, flags=re.I)
                                                    ]
                                                    think_budget_cut = True
                                                    break
                                                if re.search(r"</think(?:ing)?>", combined_so_far, flags=re.I):
                                                    has_exited_think = True

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

                                if not think_budget_cut:
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

                            # 流式思考熔断续写：当 Ollama 等引擎突破思考字符上限仍未结束 <think> 时，立即切断思考流并带提纲免思考直出正文
                            if think_budget_cut:
                                trunc_think = "".join(captured_think_pieces).strip()[:max_think_chars_guard]
                                print(f"[ThinkBudgetGuard] 思考达到预算上限 ({len(trunc_think)} 字)，自动熔断思考并无缝切入剧情正文")
                                await event_queue.put({"status": "构思已完成，正在输出剧情正文..."})
                                collected_chunks.clear()
                                if think_mod_enabled and trunc_think:
                                    closed_think_hdr = f"<think>\n{trunc_think}\n</think>\n\n"
                                    collected_chunks.append(closed_think_hdr)
                                    ACTIVE_PARTIAL_TEXT[req.chat_id] = closed_think_hdr
                                    await event_queue.put({"replace": closed_think_hdr})
                                else:
                                    ACTIVE_PARTIAL_TEXT[req.chat_id] = ""

                                cont_msgs = copy.deepcopy(cur_messages)
                                outline_note = (
                                    f"\n\n【系统强制收束指令：你刚才已完成本回合剧情构思提纲：\n{trunc_think[:1000]}\n"
                                    "严禁继续思考或输出 `<think>` 标签！请立刻从第一句小说场景与动作开始，直接输出本回合完整的剧情正文、`<status>...</status>` 状态栏与底部行动选项！】"
                                )
                                if cont_msgs and cont_msgs[-1].get("role") == "user":
                                    last_u_c = cont_msgs[-1].get("content")
                                    if isinstance(last_u_c, list):
                                        for _part in reversed(last_u_c):
                                            if isinstance(_part, dict) and _part.get("type") == "text":
                                                _part["text"] = str(_part.get("text") or "") + outline_note
                                                break
                                    else:
                                        cont_msgs[-1]["content"] = str(last_u_c or "") + outline_note
                                else:
                                    cont_msgs.append({"role": "user", "content": outline_note.strip()})

                                used_think_tok = min(safe_think_budget or 1024, max(1, int(len(trunc_think) * 0.65)))
                                cont_max_tok = max(256, total_output_budget - used_think_tok)
                                cont_body = copy.deepcopy(req_body)
                                cont_body["messages"] = cont_msgs
                                cont_body["max_tokens"] = cont_max_tok
                                cont_body["think"] = False
                                cont_body["reasoning_effort"] = "none"
                                cont_body["thinking_budget_tokens"] = 0
                                cont_body["reasoning_budget"] = 0
                                cont_body["reasoning_budget_tokens"] = 0
                                cont_body["chat_template_kwargs"] = {"enable_thinking": False}
                                if isinstance(cont_body.get("options"), dict):
                                    cont_body["options"]["num_predict"] = cont_max_tok

                                cont_loop_chk_len = 0
                                async with client.stream(
                                    "POST",
                                    f"{cur_base_url}/chat/completions",
                                    headers=req_headers,
                                    json=cont_body
                                ) as cont_resp:
                                    if cont_resp.status_code == 200:
                                        async for c_line in cont_resp.aiter_lines():
                                            c_line = c_line.strip()
                                            if not c_line or not c_line.startswith("data:"):
                                                continue
                                            c_raw = c_line[5:].lstrip()
                                            if c_raw == "[DONE]":
                                                break
                                            try:
                                                c_json = json.loads(c_raw)
                                                c_choices = c_json.get("choices") or []
                                                c_delta = (c_choices[0].get("delta") or c_choices[0].get("message") or {}) if c_choices and isinstance(c_choices[0], dict) else {}
                                                c_piece = c_delta.get("content") or ""
                                                if c_piece:
                                                    c_combined = "".join(collected_chunks) + c_piece
                                                    if not think_mod_enabled and re.search(r"(?<!`)</?think(?:ing)?>(?!`)", c_combined, flags=re.I):
                                                        c_cleaned = strip_thinking_blocks(c_combined)
                                                        collected_chunks.clear()
                                                        if c_cleaned:
                                                            collected_chunks.append(c_cleaned)
                                                        c_combined = c_cleaned
                                                        ACTIVE_PARTIAL_TEXT[req.chat_id] = c_cleaned
                                                        await event_queue.put({"replace": c_cleaned})
                                                    else:
                                                        collected_chunks.append(c_piece)
                                                        ACTIVE_PARTIAL_TEXT[req.chat_id] = c_combined
                                                        await event_queue.put({"chunk": c_piece})
                                                    if len(c_combined) >= 48 and ("\n" in c_piece or (len(c_combined) - cont_loop_chk_len) >= 40):
                                                        cont_loop_chk_len = len(c_combined)
                                                        c_trimmed = _detect_and_trim_stream_loop(
                                                            c_combined,
                                                            is_trpg=is_trpg_stream,
                                                            expect_choices=stream_choices_enabled,
                                                        )
                                                        if c_trimmed is not None:
                                                            collected_chunks.clear()
                                                            if c_trimmed:
                                                                collected_chunks.append(c_trimmed)
                                                            ACTIVE_PARTIAL_TEXT[req.chat_id] = c_trimmed
                                                            await event_queue.put({"replace": c_trimmed})
                                                            break
                                            except Exception:
                                                continue

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

                cleaned_artifacts = _strip_distilled_artifact_tags(full_reply)
                if cleaned_artifacts != full_reply:
                    full_reply = cleaned_artifacts
                    ACTIVE_PARTIAL_TEXT[req.chat_id] = full_reply
                    await event_queue.put({"replace": full_reply})

                # 执行 AI 回复的持久化正则替换 (is_only_render=False)
                full_reply, rx_ai = apply_regex_scripts(full_reply, regex_list, target_scope=1, only_persistent=True)
                prompt_log_snapshot["applied_regex"].extend(rx_ai)

                # 万物模块顺序归一化与跑团缺漏模块自动自愈补全
                try:
                    is_trpg_active = (
                        (project_data.get("status_panel_enabled", True) is not False)
                        and not is_free_chat_project(project_data)
                        and not is_simple_trpg
                    )
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
                    post_trim = _detect_and_trim_stream_loop(
                        full_reply,
                        is_trpg=is_trpg_active,
                        expect_choices=(choices_mod_enabled if is_trpg_active else False),
                    )
                    if post_trim is not None and post_trim.strip():
                        full_reply = post_trim
                    norm_parts = (
                        split_ai_message_modules(full_reply, active_status_keys)
                        if is_trpg_active
                        else {"think": "", "story": "", "status": "", "choices": ""}
                    )

                    async def _run_self_heal_stream(heal_messages: List[Dict[str, Any]], heal_max_tokens: int = 2048, on_partial=None) -> str:
                        heal_ep = resolve_model_endpoint(model_candidates[0], settings)
                        heal_rep, heal_pres, heal_freq = rep_pen, pres_pen, freq_pen
                        if heal_ep["is_local"] and not has_per_model_override:
                            heal_is_default = (
                                (heal_rep >= 1.08 and heal_pres >= 0.40)
                                or (heal_rep <= 1.02 and heal_freq == 0.0 and heal_pres == 0.0)
                                or (abs(heal_rep - 1.05) < 1e-6 and abs(heal_pres - 0.20) < 1e-6 and abs(heal_freq - 0.05) < 1e-6)
                            )
                            if heal_is_default:
                                if heal_ep.get("engine") in ("llama", "ollama"):
                                    heal_rep, heal_pres, heal_freq = 1.03, 0.10, 0.0
                                else:
                                    heal_rep, heal_pres, heal_freq = 1.05, 0.20, 0.05
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
                            elif heal_ep["engine"] == "llama":
                                heal_body["reasoning_budget"] = 0
                                heal_body["chat_template_kwargs"] = {"enable_thinking": False}
                                heal_body["repeat_penalty"] = heal_rep
                                heal_body["repeat_last_n"] = 2048
                                heal_body["cache_prompt"] = True
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
                        _last_story_emit_len = 0

                        async def _on_story_heal_partial(partial_story_raw: str):
                            nonlocal _last_story_emit_len
                            if (len(partial_story_raw) - _last_story_emit_len) < 100:
                                return
                            _last_story_emit_len = len(partial_story_raw)
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
                        _tail_hist_cache = _collect_hist_status(history_messages, active_status_keys) if active_status_mods else ({}, {})
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

                            _last_tail_emit_len = 0

                            async def _on_tail_heal_partial(partial_tail_raw: str):
                                nonlocal _last_tail_emit_len
                                if (len(partial_tail_raw) - _last_tail_emit_len) < 100:
                                    return
                                _last_tail_emit_len = len(partial_tail_raw)
                                t_parts = split_ai_message_modules(partial_tail_raw, active_status_keys)
                                merged_st = norm_parts.get("status", "")
                                if t_parts.get("status") and active_status_mods:
                                    merged_st = _merge_and_complete_status_block(
                                        norm_parts.get("status", ""),
                                        t_parts["status"],
                                        active_status_mods,
                                        history_messages,
                                        hist_cache=_tail_hist_cache,
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

                            heal_ep_chk = resolve_model_endpoint(model_candidates[0], settings)
                            compact_ctx_msgs = (
                                list(api_messages)
                                if heal_ep_chk.get("is_local")
                                else (([api_messages[0]] if api_messages and api_messages[0].get("role") == "system" else []) + list(api_messages[-2:]))
                            )
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
                                            hist_cache=_tail_hist_cache,
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
                                hist_cache=_tail_hist_cache,
                            )
                        if choices_mod_enabled and not norm_parts.get("choices", "").strip():
                            norm_parts["choices"] = (
                                "你打算怎么做？\n"
                                "1. 仔细观察周围环境的异常细节与可疑线索\n"
                                "2. 主动开口试探或与眼前人物交涉\n"
                                "3. 检查随身装备与物品，做好随时应对变故的准备\n"
                                "4. 保持警惕，顺着当前局势继续向前探索推进"
                            )

                    if is_trpg_active and (norm_parts.get("status") or norm_parts.get("choices") or norm_parts.get("story")):
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
                    elif not is_free_chat_project(project_data):
                        # 极速跑团 / 简易卡 (simple_mode=True 或未启用 <status> 状态面板) 的底部行动选项（及 <memory>）断流自动自愈补全：
                        # 当量化模型写到“你打算怎么做？”或刚写完正文便提前触发 EOS 停止时，毫秒级无思考续写补齐选项，绝不漏选项栏！
                        sys_p_raw = str(project_data.get("system_prompt") or "") + "\n" + str(project_data.get("system_protocol_prompt") or "")
                        dangling_ask = bool(
                            re.search(
                                r"(?:你打算怎么做|你要怎么做|接下来你[^\n]{0,16}|你的选择|你的抉择|行动选项)[？?：:\s]*$",
                                full_reply.strip(),
                            )
                        )
                        simple_expects_choices = dangling_ask or bool(
                            re.search(r"你打算怎么做|行动选项|可选行动|1\.\s*[…\.]{2}|行动分支", sys_p_raw)
                        )
                        if simple_expects_choices:
                            simp_parts = split_ai_message_modules(full_reply, [])
                            base_story_with_mem = simp_parts.get("story", "").strip()
                            if not simp_parts.get("choices", "").strip() and len(base_story_with_mem) >= 20:
                                await event_queue.put({"status": "正在补全底部行动选项..."})
                                need_mem = ("<memory>" in sys_p_raw.lower()) and ("</memory>" not in base_story_with_mem.lower())
                                req_simp_lines: List[str] = []
                                if need_mem:
                                    req_simp_lines.append(
                                        "1. 先用 `<memory>...</memory>` 标签输出精炼的 `[长期记忆]：...` 与 `[短期记忆]：...`（总计 180 字以内）；"
                                    )
                                req_simp_lines.append(
                                    ("2. 紧接着在最底部" if need_mem else "请直接在最底部")
                                    + "输出唯一一次“你打算怎么做？”，并另起新行按 `1.`、`2.`、`3.`、`4.` 给出 4 个紧贴刚才剧情处境的具体行动分支（高风险搏杀或潜行可在句末标 `【🎲XX检定】`，第 4 项可为异想天开破局或 `【自定义行动】___`）。"
                                )
                                heal_ep_s = resolve_model_endpoint(model_candidates[0], settings)
                                simp_ctx_msgs = (
                                    list(api_messages)
                                    if heal_ep_s.get("is_local")
                                    else (([api_messages[0]] if api_messages and api_messages[0].get("role") == "system" else []) + list(api_messages[-2:]))
                                )
                                heal_simp_msgs = simp_ctx_msgs + [
                                    {"role": "assistant", "content": base_story_with_mem[-2400:]},
                                    {
                                        "role": "user",
                                        "content": (
                                            "【系统补全指令】：你刚才的正文已写完但提前中断，漏掉了底部的行动选项！"
                                            "严禁重复输出剧情正文或任何解释，请紧接上面的剧情立即只输出以下缺失部分：\n"
                                            + "\n".join(req_simp_lines)
                                        ),
                                    },
                                ]
                                healed_simp_choices = ""
                                healed_mem_block = ""
                                try:
                                    healed_simp_raw = _strip_distilled_artifact_tags(
                                        await _run_self_heal_stream(heal_simp_msgs, heal_max_tokens=640)
                                    )
                                    if healed_simp_raw:
                                        m_mem_h = re.search(r"(<memory>[\s\S]*?</memory>)", healed_simp_raw, flags=re.I)
                                        if need_mem and m_mem_h:
                                            healed_mem_block = m_mem_h.group(1).strip()
                                        s_tail_parts = split_ai_message_modules(healed_simp_raw, [])
                                        if s_tail_parts.get("choices"):
                                            healed_simp_choices = s_tail_parts["choices"].strip()
                                except Exception as hs_e:
                                    print(f"[Warn] 极速/简易卡自动补全选项异常: {hs_e}")

                                if not healed_simp_choices:
                                    healed_simp_choices = (
                                        "你打算怎么做？\n"
                                        "1. 保持冷静观察对手破绽与周围地形，伺机而动\n"
                                        "2. 果断出手抢占先机，正面化解眼前的危机 【🎲行动检定】\n"
                                        "3. 借助现场环境掩体或随身器物制造混乱脱身\n"
                                        "4. 【自定义行动】___"
                                    )
                                combined_story = (
                                    f"{base_story_with_mem}\n\n{healed_mem_block}"
                                    if healed_mem_block
                                    else base_story_with_mem
                                )
                                full_reply = assemble_ai_message_modules(
                                    simp_parts.get("think", "") if think_mod_enabled else "",
                                    combined_story,
                                    "",
                                    healed_simp_choices,
                                )
                                ACTIVE_PARTIAL_TEXT[req.chat_id] = full_reply
                                await event_queue.put({"replace": full_reply})
                except Exception as norm_e:
                    print(f"[Warn] 模块归一化或自愈异常: {norm_e}")

                # 检测 CG 图鉴触发与自动解锁（仅扫描去除思维链后的正文，避免思考过程误触发 CG）
                visible_reply_for_cg = strip_thinking_blocks(full_reply)
                triggered_cgs, cg_updated = evaluate_cg_book(
                    project_data,
                    f"{user_display_text}\n{visible_reply_for_cg}",
                    ai_only_text=visible_reply_for_cg,
                )
                all_unlocked_ids = [c.get("id") for c in (project_data.get("cg_book") or []) if isinstance(c, dict) and c.get("unlocked") and c.get("id")]
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

                if GEN_SEQ.get(req.chat_id) != my_seq or not chat_file.exists():
                    return
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

                chat_title = str(cur_data.get("title") or "")
                if len(cur_data["messages"]) <= 3 and (chat_title.startswith("对话 ") or chat_title.startswith("新对话") or chat_title.startswith("分支 #") or chat_title in ("", "未命名对话")):
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
                    "summarized_count": safe_int(cur_data.get("summarized_count"), 0),
                    "triggered_cgs": triggered_cgs,
                    "unlocked_cgs": all_unlocked_ids,
                    "triggered_worldbooks": triggered_wb_logs
                })
            else:
                await event_queue.put({"error": "模型未返回内容，请重试或换模型"})
        except asyncio.CancelledError:
            # 停止生成 / 连发下一条消息时：已经生成的正文同步落盘（标记 interrupted），避免整段回复丢失、历史出现连续两条玩家消息。
            # 重新生成被中断时保留旧回复不动；对话已被删除（文件不存在）时不写回，防止“诈尸”。
            try:
                partial_reply = locals().get("full_reply") or "".join(collected_chunks)
                if partial_reply and partial_reply.strip() and not pending_regen and chat_file.exists():
                    if not think_mod_enabled:
                        partial_reply = strip_thinking_blocks(partial_reply)
                    if partial_reply.strip():
                        with open(chat_file, "r", encoding="utf-8") as f:
                            cancel_data = json.load(f)
                        cancel_msgs = cancel_data.setdefault("messages", [])
                        last_m = cancel_msgs[-1] if cancel_msgs and isinstance(cancel_msgs[-1], dict) else None
                        if last_m is not None and last_m.get("role") == "user" and (not turn_user_msg_id or str(last_m.get("id") or "") == turn_user_msg_id):
                            cancel_msgs.append({
                                "id": str(uuid.uuid4())[:8],
                                "role": "assistant",
                                "content": partial_reply,
                                "interrupted": True,
                                "timestamp": time.time(),
                            })
                            cancel_data["updated_at"] = time.time()
                            atomic_write_json(chat_file, cancel_data, ensure_ascii=False, indent=2)
            except Exception as save_err:
                print(f"[Warn] 中断时保存部分回复失败: {save_err}")
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
            event_queue.put_nowait(None)

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
    sep_re = r"[·•・/\-—\s]+"
    n1, n2 = re.sub(sep_re, "", k1), re.sub(sep_re, "", k2)
    if n1 and n1 == n2:
        return True
    t1 = [p for p in re.split(sep_re, k1) if p]
    t2 = [p for p in re.split(sep_re, k2) if p]
    short_t, long_t = (t1, t2) if len(t1) <= len(t2) else (t2, t1)
    # 别名形式：短名的每个词都出现在长名中（如「艾琳」⊂「艾琳·怀特」），且多出来的词不是甲乙/编号这类序号
    if short_t and len(short_t) < len(long_t) and all(t in long_t for t in short_t):
        extra = [t for t in long_t if t not in short_t]
        if not any(re.fullmatch(r"[甲乙丙丁戊己庚辛A-Za-z0-9一二三四五六七八九十]", t) for t in extra):
            return True
    # 头衔前缀形式：「钟表匠老林恩」以「老林恩」结尾
    short_k, long_k = (n1, n2) if len(n1) <= len(n2) else (n2, n1)
    if len(short_k) >= 3 and long_k.endswith(short_k):
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


_FAST_STATUS_EXTRACT_RE = re.compile(r"<status(?:\s+[^>]*)?>[\s\S]*?</status>|＜status＞[\s\S]*?＜/status＞", re.I)


def _collect_hist_status(
    history_messages: Optional[List[Dict[str, Any]]],
    active_keys: List[str],
    limit: int = 200,
) -> Tuple[Dict[str, List[str]], Dict[str, List[List[str]]]]:
    """从最近 limit 条含状态栏的 assistant 历史消息中一次性提取 prev_sec 与 hist_sec_by_key，避免自愈流式预览逐 Token 全量重扫整份长对话"""
    prev_sec: Dict[str, List[str]] = {}
    hist_sec_by_key: Dict[str, List[List[str]]] = {}
    if not history_messages:
        return prev_sec, hist_sec_by_key

    collected_status_texts: List[str] = []
    for h_msg in reversed(history_messages):
        if not isinstance(h_msg, dict) or h_msg.get("role") != "assistant":
            continue
        raw_c = str(h_msg.get("content") or "")
        if not raw_c:
            continue
        m_fast = _FAST_STATUS_EXTRACT_RE.search(raw_c)
        if m_fast:
            st_txt = m_fast.group(0)
        else:
            st_txt = split_ai_message_modules(raw_c, active_keys).get("status") or ""
        if st_txt:
            collected_status_texts.append(st_txt)
            if len(collected_status_texts) >= limit:
                break

    for st_txt in reversed(collected_status_texts):
        parsed_h = _parse_status_sections(st_txt, active_keys)
        for hk, hlines in parsed_h.items():
            clean_hlines = [x for x in hlines if x.strip()]
            if clean_hlines:
                prev_sec[hk] = clean_hlines
                hist_sec_by_key.setdefault(hk, []).append(clean_hlines)
    return prev_sec, hist_sec_by_key


def _merge_and_complete_status_block(
    primary_status: str,
    patch_status: str,
    active_status_mods: List[Dict[str, Any]],
    history_messages: Optional[List[Dict[str, Any]]] = None,
    hist_cache: Optional[Tuple[Dict[str, List[str]], Dict[str, List[List[str]]]]] = None,
) -> str:
    if not active_status_mods:
        return primary_status
    active_keys = [str(m.get("key") or "").strip() for m in active_status_mods if str(m.get("key") or "").strip()]
    pri_sec = _parse_status_sections(primary_status, active_keys)
    pat_sec = _parse_status_sections(patch_status, active_keys)
    if hist_cache is not None:
        prev_sec, hist_sec_by_key = hist_cache
    else:
        prev_sec, hist_sec_by_key = _collect_hist_status(history_messages, active_keys)

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
        m_det = re.search(
            r"<details[^>]*>\s*<summary[^>]*>[^<]*(?:行动|选项|推荐|抉择|分支|下场|选择|choice|action|option)[\s\S]*?</details>",
            raw,
            flags=re.I,
        )
        if m_det:
            return m_det.group(0).strip()
        return raw

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
            r"^\s*(?:#{1,6}\s*|\*\*)?\s*(?:(?:#?\d+|[①-⑩])[\.、\s]*)?[\[【]\s*(?:(?:#?\d+|[①-⑩])[\.、\s]*)?([^\]】\n]+?)\s*[\]】]\s*[:：]?\s*(?:\*\*)?\s*[:：]?\s*(.*)$"
        )
        custom_key_set = {str(k).strip().lower() for k in (active_status_keys or []) if str(k).strip()}
        stat_title_re = re.compile(
            r"^(?:主角状态|角色状态|个人状态|自身状态|当前状态|状态栏|状态面板|属性栏|装备栏|穿戴装备|身体装备|义体|身体栏|身体状态|物品栏|随身物品|背包|背包栏|行囊|道具栏|角色关系|好感度|好感栏|人物关系|人际关系|在场人物|周围人物|情报卡|情报栏|世界新闻|任务目标|当前任务|剧情进度|NPC关系)$",
            re.I,
        )
        choice_hdr_re = re.compile(r"^(?:行动选项|可选行动|行动推荐|行动选择|你的选择|你的抉择|选项)(?:栏|模块)?$", re.I)
        opt_num_re = re.compile(r"^\s*(?:\*\*|\*)?(?:[1-9]|[①-⑨]|[A-G])[\.、．\)]\s*\S", re.I)
        st_start = -1
        det_depth = 0
        for idx_l, ln in enumerate(w_lines):
            det_opens = len(re.findall(r"<details\b", ln, flags=re.I))
            det_closes = len(re.findall(r"</details\s*>", ln, flags=re.I))
            if det_opens:
                det_depth += det_opens
            if det_depth == 0 and not re.match(r"^\s*(?:[-*•>])", ln):
                m_b = bare_hdr_re.match(ln)
                if m_b:
                    t_clean = re.sub(r"^[📊⚔️🎒💕📋🏷️🧩📖🧠🎯📝💭⚡#\d①-⑩\.、\s*]+|\*+$", "", m_b.group(1)).strip()
                    if stat_title_re.match(t_clean) or (t_clean.lower() in custom_key_set):
                        st_start = idx_l
                        break
            if det_closes:
                det_depth = max(0, det_depth - det_closes)
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

    # 3. 从剩余内容（正文 + 选项）中精准剥离末尾的【选项模块】，并彻底去重（兼容外层包裹 <details> 的闭合标签）
    choice_pattern = re.compile(
        r"(?:(?:\n|^)\s*(?:---|\*\*\*|___)\s*)?"
        r"(?:"
        r"(?:\n|^)\s*(<details[^>]*>\s*<summary[^>]*>[^<]*(?:行动|选项|推荐|抉择|分支|下场|选择|choice|action|option)(?![^<]*(?:SYSTEM\s*TERMINAL|系统面板|主角信息|NPC信息|记忆))[\s\S]*?</details>)((?:\s*</details>)*)\s*$"
        r"|"
        r"(?:\n|^)\s*((?:#{1,6}\s*|\*\*|\*)?\s*(?:[\[【]\s*(?:#\d+\s*)?)?(?:[🎯🎬💡⚡🧭]\s*)?(?:你打算怎么做|接下来你[^\n]{0,18}|你的选择|你的抉择|行动选项|行动推荐|可选行动|可采取的?行动|你决定怎么做|你要怎么做|现在你[^\n]{0,12}怎么做)[^\n]*\n(?:\s*(?:\*\*|\*)?(?:[1-9]|[①-⑨]|[A-G])[\.、．\)\s][^\n]+(?:\n|$))+?)((?:\s*</details>)*)\s*$"
        r"|"
        r"(?:\n|^)((?:\s*(?:\*\*|\*)?(?:[1-7]|①|②|③|④|⑤|⑥|⑦|[A-D])[\.、．\)]\s*[^\n]+(?:\n|$)){2,})((?:\s*</details>)*)\s*$"
        r")",
        re.I
    )
    collected_choice_chunks: List[str] = []
    story_body = working
    while True:
        m_choice = choice_pattern.search(story_body)
        if not m_choice:
            break
        inner_chunk = (m_choice.group(1) or m_choice.group(3) or m_choice.group(5) or "").strip()
        outer_closes = (m_choice.group(2) or m_choice.group(4) or m_choice.group(6) or "")
        chunk = re.sub(r"^(?:---|\*\*\*|___)\s*\n*", "", inner_chunk).strip()
        if chunk:
            collected_choice_chunks.insert(0, chunk)
        story_body = (story_body[:m_choice.start()].rstrip() + outer_closes).strip()

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
        elif ep["engine"] == "llama":
            req_json["reasoning_budget"] = 0
            req_json["chat_template_kwargs"] = {"enable_thinking": False}
            req_json["repeat_penalty"] = 1.08
            req_json["repeat_last_n"] = 512
            req_json["cache_prompt"] = True
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
        except Exception:
            patched = False
        if not patched:
            raise HTTPException(status_code=409, detail="这条回复已被修改或删除，请重新操作")
        atomic_write_json(chat_file, fresh_chat, ensure_ascii=False, indent=2)
        chat_data = fresh_chat

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



# ==================== 游戏卡（Game Card）双向互通：本工作台 <-> SillyTavern 酒馆 (PNG / JSON, V2 / V3) ====================
def _load_cjk_font(size: int, bold: bool = False):
    from PIL import ImageFont
    candidates = (
        [
            r"C:\Windows\Fonts\msyhbd.ttc",
            r"C:\Windows\Fonts\simhei.ttf",
            r"C:\Windows\Fonts\msyh.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        ]
        if bold
        else [
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\simhei.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        ]
    )
    for fp in candidates:
        try:
            if Path(fp).exists():
                return ImageFont.truetype(fp, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _resolve_project_image_bytes(img_ref: str, username: str) -> Optional[bytes]:
    s = str(img_ref or "").strip()
    if not s:
        return None
    if s.startswith("data:image/"):
        m = re.match(r"^data:image/[^;]+;base64,(.+)$", s, flags=re.S)
        if m:
            try:
                return base64.b64decode(re.sub(r"\s+", "", m.group(1)))
            except Exception:
                return None
    m_gal = re.search(r"/api/gallery/(?:image|thumb)/([a-zA-Z0-9._-]+)", s)
    if m_gal:
        gid = sanitize_id(m_gal.group(1))
        gdir = get_user_gallery_dir(username)
        for cand in gdir.glob(f"{gid}*"):
            if cand.is_file() and cand.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                try:
                    return cand.read_bytes()
                except Exception:
                    pass
    return None


def _inject_png_text_chunks(png_bytes: bytes, chunks_kv: List[Tuple[str, str]]) -> bytes:
    """在 PNG IEND 块前写入标准 tEXt 数据块（同时写入 chara 与 ccv3，100% 兼容 SillyTavern V2/V3 与本工作台）"""
    import struct
    import zlib

    if len(png_bytes) < 12 or png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("无效的 PNG 字节流")

    out = bytearray(png_bytes[:8])
    pos = 8
    injected = False
    extra_chunks = bytearray()
    for keyword, text_val in chunks_kv:
        kw_bytes = keyword.encode("latin-1", errors="ignore")[:79]
        b64_payload = base64.b64encode(text_val.encode("utf-8"))
        c_data = kw_bytes + b"\x00" + b64_payload
        c_type = b"tEXt"
        crc = zlib.crc32(c_type + c_data) & 0xFFFFFFFF
        extra_chunks.extend(struct.pack(">I", len(c_data)))
        extra_chunks.extend(c_type)
        extra_chunks.extend(c_data)
        extra_chunks.extend(struct.pack(">I", crc))

    while pos + 12 <= len(png_bytes):
        length = struct.unpack(">I", png_bytes[pos:pos + 4])[0]
        if pos + 12 + length > len(png_bytes):
            break
        chunk_type = png_bytes[pos + 4:pos + 8]
        chunk_full = png_bytes[pos:pos + 12 + length]
        pos += 12 + length
        if chunk_type in (b"tEXt", b"zTXt", b"iTXt"):
            nul_pos = chunk_full[8:-4].find(b"\x00")
            if nul_pos != -1:
                kw = chunk_full[8:8 + nul_pos].decode("latin-1", errors="ignore").strip().lower()
                if kw in ("chara", "ccv3"):
                    continue
        if chunk_type == b"IEND" and not injected:
            out.extend(extra_chunks)
            injected = True
        out.extend(chunk_full)
        if chunk_type == b"IEND":
            break

    if not injected:
        out.extend(extra_chunks)
    return bytes(out)


def _render_game_card_poster_png(proj: Dict[str, Any], username: str) -> bytes:
    from PIL import Image, ImageDraw

    W, H = 600, 840
    cover_bytes = (
        _resolve_project_image_bytes(proj.get("icon") or proj.get("avatar") or "", username)
        or _resolve_project_image_bytes((proj.get("appearance") or {}).get("bg_mobile") or "", username)
        or _resolve_project_image_bytes((proj.get("appearance") or {}).get("bg_image") or "", username)
    )

    canvas = Image.new("RGBA", (W, H), (20, 18, 16, 255))
    has_art = False
    if cover_bytes:
        try:
            src_im = Image.open(io.BytesIO(cover_bytes)).convert("RGBA")
            sw, sh = src_im.size
            if sw > 0 and sh > 0:
                scale = max(W / sw, H / sh)
                nw, nh = max(1, int(sw * scale)), max(1, int(sh * scale))
                resized = src_im.resize((nw, nh), Image.Resampling.LANCZOS)
                left = max(0, (nw - W) // 2)
                top = max(0, (nh - H) // 2)
                canvas = resized.crop((left, top, left + W, top + H))
                has_art = True
        except Exception:
            has_art = False

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    if has_art:
        for y in range(H // 2, H):
            ratio = (y - H // 2) / max(1, (H - H // 2))
            alpha = int(235 * (ratio ** 1.35))
            odraw.line([(0, y), (W, y)], fill=(14, 12, 11, min(242, alpha)))
    else:
        for y in range(H):
            r = int(28 - 10 * (y / H))
            g = int(24 - 8 * (y / H))
            b = int(21 - 7 * (y / H))
            odraw.line([(0, y), (W, y)], fill=(r, g, b, 255))
        odraw.rounded_rectangle([22, 22, W - 22, H - 22], radius=20, outline=(212, 166, 90, 130), width=2)
        odraw.rounded_rectangle([32, 32, W - 32, H - 32], radius=14, outline=(212, 166, 90, 48), width=1)

    canvas = Image.alpha_composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas)

    f_badge = _load_cjk_font(17, bold=True)
    f_title = _load_cjk_font(36, bold=True)
    f_desc = _load_cjk_font(19, bold=False)
    f_tag = _load_cjk_font(16, bold=False)

    mode_txt = "EASY-TRPG · 简易游戏卡" if (proj.get("card_tier") == "simple" or proj.get("simple_mode")) else "EASY-TRPG · 高级游戏卡"
    title_txt = str(proj.get("name") or "未命名游戏卡").strip()[:28]
    desc_txt = str(proj.get("description") or "").strip()
    if not desc_txt:
        gm = proj.get("guided_meta") if isinstance(proj.get("guided_meta"), dict) else {}
        desc_txt = str(gm.get("main_plot") or gm.get("world_conflict") or proj.get("system_prompt") or "支持一键导入 Easy-TRPG 工作台与 SillyTavern 酒馆").strip()
    desc_txt = re.sub(r"\s+", " ", desc_txt)[:96]
    tags_list = [str(t).strip() for t in (proj.get("tags") or []) if str(t).strip()][:5]

    def _wrap_lines(txt: str, font_obj, max_px: int, max_lines: int) -> List[str]:
        lines_out: List[str] = []
        cur = ""
        for ch in txt:
            cand = cur + ch
            try:
                w = draw.textlength(cand, font=font_obj)
            except Exception:
                w = len(cand) * 20
            if w > max_px and cur:
                lines_out.append(cur)
                cur = ch
                if len(lines_out) >= max_lines:
                    lines_out[-1] = lines_out[-1][:-1] + "…"
                    return lines_out
            else:
                cur = cand
        if cur and len(lines_out) < max_lines:
            lines_out.append(cur)
        return lines_out

    base_y = H - 245 if has_art else 220
    draw.rounded_rectangle([44, base_y, 260, base_y + 30], radius=8, fill=(212, 166, 90, 42), outline=(212, 166, 90, 150), width=1)
    draw.text((56, base_y + 5), mode_txt, font=f_badge, fill=(242, 205, 138, 255))

    ty = base_y + 46
    for t_ln in _wrap_lines(title_txt, f_title, W - 92, 2):
        draw.text((46, ty), t_ln, font=f_title, fill=(248, 244, 236, 255))
        ty += 46

    ty += 8
    for d_ln in _wrap_lines(desc_txt, f_desc, W - 96, 3 if has_art else 6):
        draw.text((46, ty), d_ln, font=f_desc, fill=(208, 198, 184, 230))
        ty += 28

    if tags_list:
        tx = 46
        tag_y = H - 58
        for tg in tags_list:
            lbl = f"#{tg[:10]}"
            try:
                tw = int(draw.textlength(lbl, font=f_tag)) + 20
            except Exception:
                tw = len(lbl) * 16 + 20
            if tx + tw > W - 44:
                break
            draw.rounded_rectangle([tx, tag_y, tx + tw, tag_y + 28], radius=14, fill=(255, 255, 255, 22), outline=(212, 166, 90, 85), width=1)
            draw.text((tx + 10, tag_y + 5), lbl, font=f_tag, fill=(235, 214, 175, 240))
            tx += tw + 8

    out_buf = io.BytesIO()
    canvas.convert("RGB").save(out_buf, format="PNG", optimize=True)
    return out_buf.getvalue()


def _inline_gallery_ref_to_data_url(ref_val: Any, username: str, max_dim: int = 1024, max_bytes: int = 160_000) -> str:
    s = str(ref_val or "").strip()
    if not s or s.startswith("data:image/"):
        return s
    raw_b = _resolve_project_image_bytes(s, username)
    if not raw_b:
        return s
    try:
        raw_durl = "data:image/png;base64," + base64.b64encode(raw_b).decode("ascii")
        return optimize_image_base64(raw_durl, max_dim, 82, max_bytes)
    except Exception:
        return s


def _build_tavern_v3_game_card_dict(proj: Dict[str, Any], username: str = "player") -> Dict[str, Any]:
    """将本工作台游戏企划打包为标准 SillyTavern V2/V3 兼容结构 + 无损 easy_trpg_game_card 扩展"""
    name = str(proj.get("name") or "未命名游戏卡").strip()
    player_intro = str(proj.get("description") or "").strip()
    sys_prompt = str(proj.get("system_prompt") or "").strip()
    status_spec = ""
    if proj.get("status_panel_enabled", False) and not proj.get("simple_mode", False):
        status_spec = build_status_module_prompt(proj).strip()
    combined_desc = f"{sys_prompt}\n\n{status_spec}".strip() if (sys_prompt and status_spec) else (sys_prompt or status_spec)

    gm = proj.get("guided_meta") if isinstance(proj.get("guided_meta"), dict) else {}
    scenario_txt = str(gm.get("world_conflict") or gm.get("main_plot") or "").strip()

    og_list = proj.get("opening_greetings") if isinstance(proj.get("opening_greetings"), list) else []
    greetings: List[str] = []
    for og in og_list:
        if isinstance(og, str) and og.strip():
            greetings.append(og.strip())
        elif isinstance(og, dict):
            c = str(og.get("content") or og.get("text") or "").strip()
            if c:
                greetings.append(c)
    if not greetings and str(proj.get("opening_statement") or "").strip():
        greetings.append(str(proj.get("opening_statement")).strip())

    first_mes = greetings[0] if greetings else ""
    alt_greetings = greetings[1:] if len(greetings) > 1 else []

    wb_entries = []
    for idx, wb in enumerate(proj.get("world_book") or []):
        if not isinstance(wb, dict):
            continue
        raw_k = wb.get("keys") or []
        keys_arr = [str(k).strip() for k in raw_k if str(k).strip()] if isinstance(raw_k, list) else [k.strip() for k in str(raw_k).split(",") if k.strip()]
        m_type = str(wb.get("match_type") or "OR").upper()
        is_const = (m_type == "CONSTANT") or bool(wb.get("constant", False)) or (len(keys_arr) == 0 and bool(wb.get("content", "").strip()))
        wb_entries.append({
            "id": idx,
            "keys": keys_arr,
            "secondary_keys": [],
            "comment": str(wb.get("name") or f"词条 #{idx + 1}"),
            "content": str(wb.get("content") or ""),
            "constant": is_const,
            "selective": m_type == "AND",
            "insertion_order": 100 + idx,
            "enabled": wb.get("enabled", True) is not False,
            "position": "after_char" if str(wb.get("value_region") or "System").lower() == "after" else "before_char",
        })

    st_regex_scripts = []
    for r_idx, rx in enumerate(proj.get("regex_scripts") or proj.get("regex_replaces") or []):
        if not isinstance(rx, dict):
            continue
        pat = str(rx.get("find_regex") or rx.get("pattern") or rx.get("findRegex") or "").strip()
        if not pat:
            continue
        st_regex_scripts.append({
            "id": str(rx.get("id") or f"rx_{r_idx + 1}"),
            "scriptName": str(rx.get("name") or rx.get("scriptName") or f"规则 #{r_idx + 1}"),
            "findRegex": pat,
            "replaceString": str(rx.get("replace_str") or rx.get("replacement") or rx.get("replaceString") or ""),
            "placement": [2] if int(rx.get("target_scope", 1) or 1) == 1 else [1, 2],
            "disabled": rx.get("enabled", True) is False,
            "markdownOnly": bool(rx.get("is_only_render", False)),
            "promptOnly": False,
            "runOnEdit": True,
        })

    portable_proj = copy.deepcopy(proj)
    portable_proj.pop("id", None)
    if portable_proj.get("icon"):
        portable_proj["icon"] = _inline_gallery_ref_to_data_url(portable_proj["icon"], username, 384, 75_000)
        portable_proj["avatar"] = portable_proj["icon"]
    if isinstance(portable_proj.get("appearance"), dict):
        if portable_proj["appearance"].get("bg_image"):
            portable_proj["appearance"]["bg_image"] = _inline_gallery_ref_to_data_url(portable_proj["appearance"]["bg_image"], username, 1280, 180_000)
            portable_proj["bg_image"] = portable_proj["appearance"]["bg_image"]
        if portable_proj["appearance"].get("bg_mobile"):
            portable_proj["appearance"]["bg_mobile"] = _inline_gallery_ref_to_data_url(portable_proj["appearance"]["bg_mobile"], username, 1080, 160_000)
    if isinstance(portable_proj.get("cg_book"), list):
        for cg_it in portable_proj["cg_book"]:
            if isinstance(cg_it, dict) and cg_it.get("image_url"):
                cg_it["image_url"] = _inline_gallery_ref_to_data_url(cg_it["image_url"], username, 1024, 150_000)

    data_block: Dict[str, Any] = {
        "name": name,
        "description": combined_desc,
        "personality": "",
        "scenario": scenario_txt,
        "first_mes": first_mes,
        "mes_example": "",
        "creator_notes": player_intro,
        "system_prompt": str(proj.get("prefix") or ""),
        "post_history_instructions": str(proj.get("suffix") or ""),
        "alternate_greetings": alt_greetings,
        "tags": list(proj.get("tags") or []),
        "creator": str(proj.get("author") or "Easy-TRPG Creator"),
        "character_version": APP_VERSION,
        "extensions": {
            "easy_trpg_game_card": portable_proj,
            **({"custom_css": str(proj.get("custom_css") or "")} if str(proj.get("custom_css") or "").strip() else {}),
            **({"detailed_description": str(proj.get("detailed_description") or "")} if str(proj.get("detailed_description") or "").strip() else {}),
            **({"quick_replies": list(proj.get("quick_replies") or [])} if proj.get("quick_replies") else {}),
            **({"regex_scripts": st_regex_scripts} if st_regex_scripts else {}),
        },
    }
    if wb_entries:
        data_block["character_book"] = {
            "name": f"{name} 世界书",
            "entries": wb_entries,
        }

    return {
        "spec": "chara_card_v3",
        "spec_version": "3.0",
        "name": name,
        "description": combined_desc,
        "personality": "",
        "scenario": scenario_txt,
        "first_mes": first_mes,
        "mes_example": "",
        "creatorcomment": player_intro,
        "tags": list(proj.get("tags") or []),
        "data": data_block,
    }


def _convert_imported_card_to_project(
    raw_json: Dict[str, Any],
    cover_b64: str,
    settings: Dict[str, Any],
) -> Dict[str, Any]:
    """将导入的 Easy-TRPG 游戏卡或 SillyTavern V1/V2/V3 角色卡/世界卡无损转换为本工作台游戏企划"""
    if not isinstance(raw_json, dict):
        raise ValueError("JSON 结构不是有效对象")

    data_part = raw_json.get("data") if isinstance(raw_json.get("data"), dict) else {}
    ext_part = data_part.get("extensions") if isinstance(data_part.get("extensions"), dict) else (
        raw_json.get("extensions") if isinstance(raw_json.get("extensions"), dict) else {}
    )

    native_snap = ext_part.get("easy_trpg_game_card") or raw_json.get("easy_trpg_game_card")
    if not native_snap and ("ui_modules" in raw_json or "completion_params" in raw_json or "guided_meta" in raw_json):
        native_snap = raw_json

    if isinstance(native_snap, dict):
        restored = copy.deepcopy(native_snap)
        restored.pop("id", None)
        cur_ic = str(restored.get("icon") or "").strip()
        if cover_b64 and (not cur_ic or not (cur_ic.startswith("data:image/") or cur_ic.startswith("/") or cur_ic.startswith("http"))):
            restored["icon"] = cover_b64
            restored["avatar"] = cover_b64
        return normalize_project_schema(restored, {}, global_defaults=settings)

    # 标准 SillyTavern / OpenTavern V1 / V2 / V3 卡片转换
    def _pick(*keys: str) -> str:
        for k in keys:
            v = data_part.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
            v2 = raw_json.get(k)
            if isinstance(v2, str) and v2.strip():
                return v2.strip()
        return ""

    name = _pick("name") or "导入酒馆游戏卡"
    creator_notes = _pick("creator_notes", "creatorcomment")
    st_desc = _pick("description")
    st_pers = _pick("personality")
    st_scen = _pick("scenario")
    st_mes_ex = _pick("mes_example")
    st_sys = _pick("system_prompt")
    st_post = _pick("post_history_instructions", "depth_prompt_prompt")

    sys_sections: List[str] = []
    if st_desc:
        sys_sections.append(st_desc)
    if st_pers:
        sys_sections.append(f"## 角色性格与特征\n{st_pers}")
    if st_scen:
        sys_sections.append(f"## 背景与初始处境\n{st_scen}")
    if st_mes_ex and st_mes_ex != "<START>":
        sys_sections.append(f"## 叙事与对话示例\n{st_mes_ex}")
    assembled_sys = "\n\n".join(sys_sections).strip()

    first_mes = _pick("first_mes")
    alt_raw = data_part.get("alternate_greetings") if isinstance(data_part.get("alternate_greetings"), list) else (
        raw_json.get("alternate_greetings") if isinstance(raw_json.get("alternate_greetings"), list) else []
    )
    opening_greetings = []
    if first_mes:
        opening_greetings.append({"id": "og_1", "title": "默认开场", "content": first_mes})
    for idx_a, ag in enumerate(alt_raw):
        ag_s = str(ag or "").strip()
        if ag_s:
            opening_greetings.append({"id": f"og_{len(opening_greetings) + 1}", "title": f"分支开场 #{idx_a + 2}", "content": ag_s})

    raw_cb = data_part.get("character_book") or raw_json.get("character_book") or ext_part.get("character_book")
    wb_list = _normalize_character_book_entries(raw_cb, name) if raw_cb else []

    raw_rx = ext_part.get("regex_scripts") if isinstance(ext_part.get("regex_scripts"), list) else []
    regex_list = []
    for r_i, rx in enumerate(raw_rx):
        if not isinstance(rx, dict):
            continue
        f_pat = str(rx.get("findRegex") or rx.get("pattern") or "").strip()
        if not f_pat:
            continue
        regex_list.append({
            "id": str(rx.get("id") or f"rx_{r_i + 1}"),
            "name": str(rx.get("scriptName") or rx.get("name") or f"酒馆正则 #{r_i + 1}"),
            "find_regex": f_pat,
            "pattern": f_pat,
            "replace_str": str(rx.get("replaceString") or rx.get("replacement") or ""),
            "replacement": str(rx.get("replaceString") or rx.get("replacement") or ""),
            "enabled": not bool(rx.get("disabled", False)),
            "is_only_render": bool(rx.get("markdownOnly", True)),
            "target_scope": 1,
        })

    raw_tags = data_part.get("tags") if isinstance(data_part.get("tags"), list) else (
        raw_json.get("tags") if isinstance(raw_json.get("tags"), list) else []
    )
    tags = [str(t).strip() for t in raw_tags if str(t).strip()]

    imported_css = str(ext_part.get("custom_css") or raw_json.get("custom_css") or "").strip()
    if not imported_css and creator_notes and "<style" in creator_notes.lower():
        m_styles = re.findall(r"<style[^>]*>([\s\S]*?)</style>", creator_notes, flags=re.IGNORECASE)
        if m_styles:
            imported_css = "\n\n".join(s.strip() for s in m_styles if s.strip())
            creator_notes = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", creator_notes, flags=re.IGNORECASE).strip()
    imported_detailed_desc = str(ext_part.get("detailed_description") or raw_json.get("detailed_description") or "").strip()
    imported_qr = ext_part.get("quick_replies") if isinstance(ext_part.get("quick_replies"), list) else []

    proj_payload = {
        "name": name,
        "icon": cover_b64 or "",
        "avatar": cover_b64 or "",
        "description": creator_notes,
        "detailed_description": imported_detailed_desc,
        "custom_css": imported_css,
        "quick_replies": imported_qr,
        "tags": tags,
        "card_tier": "advanced",
        "simple_mode": False,
        "cot_enabled": True,
        "status_panel_enabled": False,
        "ui_modules": [],
        "prefix": st_sys,
        "system_prompt": assembled_sys,
        "suffix": st_post,
        "opening_greetings": opening_greetings,
        "opening_statement": first_mes,
        "world_book": wb_list,
        "regex_scripts": regex_list,
        "regex_replaces": regex_list,
        "appearance": {"bg_image": "", "custom_css": imported_css},
    }
    return normalize_project_schema(proj_payload, {}, global_defaults=settings)


@app.get("/api/projects/{project_id}/export_card")
async def export_project_game_card(
    project_id: str,
    format: str = "png",
    username: str = Depends(get_current_user),
):
    ensure_user_workspace(username)
    project_id = sanitize_id(project_id)
    settings = load_user_settings(username)
    file_path = get_user_projects_dir(username) / f"{project_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="游戏卡不存在")
    with open(file_path, "r", encoding="utf-8") as f:
        proj = normalize_project_schema(json.load(f), global_defaults=settings)

    card_dict = _build_tavern_v3_game_card_dict(proj, username)
    safe_name = re.sub(r'[\\/:*?"<>|]+', "_", str(proj.get("name") or "游戏卡")).strip() or "game_card"
    fmt = (format or "png").strip().lower()
    if fmt == "json":
        json_bytes = json.dumps(card_dict, ensure_ascii=False, indent=2).encode("utf-8")
        disp = f"attachment; filename*=UTF-8''{quote(safe_name + '_游戏卡.json')}"
        return Response(content=json_bytes, media_type="application/json; charset=utf-8", headers={"Content-Disposition": disp})

    poster_png = await asyncio.to_thread(_render_game_card_poster_png, proj, username)
    compact_json = json.dumps(card_dict, ensure_ascii=False, separators=(",", ":"))
    card_png = _inject_png_text_chunks(poster_png, [("chara", compact_json), ("ccv3", compact_json)])
    disp = f"attachment; filename*=UTF-8''{quote(safe_name + '_游戏卡.png')}"
    return Response(content=card_png, media_type="image/png", headers={"Content-Disposition": disp})


@app.post("/api/projects/export_draft_card")
async def export_draft_game_card(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    settings = load_user_settings(username)
    raw_proj = payload.get("project") if isinstance(payload.get("project"), dict) else payload
    proj = normalize_project_schema(raw_proj, {}, global_defaults=settings)
    card_dict = _build_tavern_v3_game_card_dict(proj, username)
    safe_name = re.sub(r'[\\/:*?"<>|]+', "_", str(proj.get("name") or "游戏卡")).strip() or "game_card"
    fmt = str(payload.get("format") or "png").strip().lower()
    if fmt == "json":
        json_bytes = json.dumps(card_dict, ensure_ascii=False, indent=2).encode("utf-8")
        disp = f"attachment; filename*=UTF-8''{quote(safe_name + '_游戏卡.json')}"
        return Response(content=json_bytes, media_type="application/json; charset=utf-8", headers={"Content-Disposition": disp})

    poster_png = await asyncio.to_thread(_render_game_card_poster_png, proj, username)
    compact_json = json.dumps(card_dict, ensure_ascii=False, separators=(",", ":"))
    card_png = _inject_png_text_chunks(poster_png, [("chara", compact_json), ("ccv3", compact_json)])
    disp = f"attachment; filename*=UTF-8''{quote(safe_name + '_游戏卡.png')}"
    return Response(content=card_png, media_type="image/png", headers={"Content-Disposition": disp})


@app.post("/api/projects/import_card")
async def import_project_game_card(file: UploadFile = File(...), username: str = Depends(get_current_user)):
    ensure_user_workspace(username)
    raw_bytes = await file.read()
    if len(raw_bytes) > 40 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="游戏卡文件体积不能超过 40MB")
    fname = (file.filename or "").lower()
    cover_b64 = ""
    settings = load_user_settings(username)

    try:
        if fname.endswith(".png") or raw_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            raw_json = _extract_chara_json_from_png_bytes(raw_bytes)
            raw_data_url = "data:image/png;base64," + base64.b64encode(raw_bytes).decode("ascii")
            cover_b64 = await asyncio.to_thread(optimize_image_base64, raw_data_url, 480, 84, 95_000)
        else:
            raw_json = json.loads(raw_bytes.decode("utf-8-sig"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析游戏卡失败：{e}")

    try:
        proj = _convert_imported_card_to_project(raw_json, cover_b64, settings)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"转换游戏卡格式失败：{e}")

    new_pid = f"proj_{uuid.uuid4().hex[:8]}"
    proj["id"] = new_pid
    now = time.time()
    proj["created_at"] = now
    proj["updated_at"] = now

    proj_file = get_user_projects_dir(username) / f"{new_pid}.json"
    atomic_write_json(proj_file, proj, ensure_ascii=False, indent=2)

    chat_id = str(uuid.uuid4().hex[:8])
    init_msgs = []
    first_og = ""
    if isinstance(proj.get("opening_greetings"), list) and proj["opening_greetings"]:
        og0 = proj["opening_greetings"][0]
        first_og = str(og0.get("content") if isinstance(og0, dict) else og0 or "").strip()
    elif str(proj.get("opening_statement") or "").strip():
        first_og = str(proj.get("opening_statement")).strip()

    if first_og:
        init_msgs.append({
            "id": "msg_opening_" + uuid.uuid4().hex[:6],
            "role": "assistant",
            "content": first_og,
            "is_opening": True,
            "timestamp": now,
        })

    chat_data = {
        "id": chat_id,
        "title": f"{proj.get('name', '新游戏')} · 存档 #1",
        "project_id": new_pid,
        "model": settings.get("model", ""),
        "summary": "",
        "summarized_count": 0,
        "inputs": {},
        "variables": {},
        "created_at": now,
        "updated_at": now,
        "messages": init_msgs,
    }
    atomic_write_json(get_user_chats_dir(username) / f"{chat_id}.json", chat_data, ensure_ascii=False, indent=2)

    with _USER_SETTINGS_LOCK:
        cur_s = load_user_settings(username)
        cur_s["active_project_id"] = new_pid
        save_user_settings(username, cur_s)

    return {"status": "ok", "project": proj, "chat_id": chat_id}


@app.post("/api/ai/generate_game_card")
async def ai_generate_guided_game_card(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    """简易创作：根据一句话脑洞/大纲自动生成全套结构化游戏卡设定（保留用户已填内容不覆盖）"""
    settings = load_user_settings(username)
    idea = str(payload.get("idea") or "").strip()
    cur_name = str(payload.get("name") or "").strip()
    cur_desc = str(payload.get("description") or "").strip()
    cur_meta = payload.get("current_meta") if isinstance(payload.get("current_meta"), dict) else {}
    req_model = str(payload.get("model") or settings.get("model") or "").strip()

    if not idea and not cur_name and not cur_desc:
        raise HTTPException(status_code=400, detail="请先输入一句话创作想法或题材描述")

    ep = resolve_model_endpoint(req_model, settings)
    if ep["is_local"]:
        local_err = await ensure_local_engine_ready(req_model)
        ep = resolve_model_endpoint(req_model, settings)
        if local_err:
            raise HTTPException(status_code=503, detail=local_err)
    if not ep.get("base_url") or is_self_workbench_url(ep["base_url"]):
        raise HTTPException(status_code=400, detail="尚未配置可用的 AI 模型，请先在左下角「模型」中选择本地模型或配置 API")

    existing_summary_lines = []
    if cur_name and not cur_name.startswith(("新企划", "新剧本", "新游戏")):
        existing_summary_lines.append(f"- 已有名称：{cur_name}")
    if cur_desc:
        existing_summary_lines.append(f"- 已有简介：{cur_desc}")
    for k, lbl in [
        ("protagonist_name", "主人公名称"),
        ("protagonist_desc", "主人公设定"),
        ("protagonist_goal", "核心动机/目标"),
        ("world_name", "世界名称"),
        ("world_era", "时代与体系"),
        ("world_conflict", "核心冲突"),
        ("world_tone", "整体基调与文风"),
        ("main_plot", "主线情节"),
        ("initial_state", "初始剧情状态"),
        ("play_rules", "游玩规则"),
    ]:
        val = str(cur_meta.get(k) or "").strip()
        if val:
            existing_summary_lines.append(f"- 已有{lbl}：{val}")

    sys_msg = (
        "你是一位顶级互动跑团企划设计师与世界观架构师。请根据用户的创作脑洞，构思一套结构严密、极具代入感与可玩性的跑团游戏卡设定。\n"
        "请严格只输出一个合法的 JSON 对象（不要包裹 markdown 代码块解释文字），包含以下字段：\n"
        "{\n"
        '  "name": "富有吸引力的作品名称（4~12字）",\n'
        '  "description": "面向玩家展示的作品简介（60~140字，吸引玩家游玩，不发给AI）",\n'
        '  "tags": ["题材标签1", "标签2", "标签3"],\n'
        '  "protagonist_name": "主人公称呼或身份定位",\n'
        '  "protagonist_desc": "主人公背景、能力特长与随身特征（60~150字）",\n'
        '  "protagonist_goal": "主人公的核心动机与初始目标（40~100字）",\n'
        '  "world_name": "故事展开的世界/城市/舞台名称",\n'
        '  "world_era": "时代背景与科技/魔法/力量体系（80~180字）",\n'
        '  "world_conflict": "核心冲突、派系暗流与生存压力（80~180字）",\n'
        '  "world_tone": "整体基调、叙事视角与文风要求（如：第二人称冷硬写实、悬疑紧张等）",\n'
        '  "main_plot": "主线情节推进脉络与关键转折悬念（100~220字）",\n'
        '  "initial_state": "第一幕初始剧情状态（第二人称『你』开场，描写玩家刚进入游戏时的具体场景、感官细节与眼前局势，120~260字）",\n'
        '  "play_rules": "AI 主持必须遵守的游玩法则（如：真实因果判定、NPC独立动机、严禁代写玩家台词等，60~160字）",\n'
        '  "npcs": [\n'
        '    {"name": "角色名", "role": "身份/阵营", "desc": "外貌、性格与实力特征", "attitude": "对主角初始态度与隐藏动机"}\n'
        "  ]\n"
        "}"
    )
    user_msg = f"【创作脑洞 / 大致描述】：\n{idea or cur_desc or cur_name}"
    if existing_summary_lines:
        user_msg += "\n\n【用户已填写的设定（请围绕这些已有设定保持一致并补全其余项）】：\n" + "\n".join(existing_summary_lines)

    req_json: Dict[str, Any] = {
        "model": ep["upstream_model"],
        "messages": [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ],
        "max_tokens": 4096,
        "temperature": 0.72,
        "stream": True,
    }
    if ep["is_local"]:
        if ep["engine"] == "strata":
            req_json["reasoning_effort"] = "none"
            req_json["reasoning_budget_tokens"] = 0
            req_json["chat_template_kwargs"] = {"enable_thinking": False}
        elif ep["engine"] == "llama":
            req_json["reasoning_budget"] = 0
            req_json["chat_template_kwargs"] = {"enable_thinking": False}
        elif ep["engine"] == "ollama":
            req_json["think"] = False
            req_json["chat_template_kwargs"] = {"enable_thinking": False}

    collected: List[str] = []
    proxy_candidates = [ep["proxy"], None] if ep["proxy"] else [None]
    req_headers = ep.get("headers") or {"Authorization": f"Bearer {ep['api_key']}", "Content-Type": "application/json"}

    for cur_proxy in proxy_candidates:
        try:
            async with httpx.AsyncClient(proxy=cur_proxy, trust_env=False, timeout=httpx.Timeout(120.0, connect=12.0)) as client:
                async with client.stream("POST", f"{ep['base_url']}/chat/completions", headers=req_headers, json=req_json) as resp:
                    if resp.status_code != 200:
                        continue
                    ctype = (resp.headers.get("content-type") or "").lower()
                    if "text/event-stream" not in ctype:
                        rj = json.loads((await resp.aread()).decode("utf-8", errors="ignore"))
                        c = ((rj.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                        if c:
                            collected.append(c)
                    else:
                        async for line in resp.aiter_lines():
                            line = line.strip()
                            if line.startswith("data:"):
                                raw_d = line[5:].lstrip()
                                if raw_d == "[DONE]":
                                    break
                                try:
                                    dj = json.loads(raw_d)
                                    c = (((dj.get("choices") or [{}])[0].get("delta") or {}).get("content")) or ""
                                    if c:
                                        collected.append(c)
                                except Exception:
                                    pass
                    if collected:
                        break
        except Exception:
            continue

    raw_reply = strip_thinking_blocks("".join(collected)).strip()
    clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_reply, flags=re.I).strip()
    parsed: Dict[str, Any] = {}
    try:
        parsed = json.loads(clean_json)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", clean_json)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except Exception:
                pass
    if not isinstance(parsed, dict) or not parsed:
        raise HTTPException(status_code=500, detail="AI 返回格式解析失败，请重试或切换模型")

    return {"status": "ok", "generated": parsed}


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
        elif ep["engine"] == "llama":
            card_req_json["reasoning_budget"] = 0
            card_req_json["chat_template_kwargs"] = {"enable_thinking": False}
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


# ==================== 一键更新系统（直连 hf-mirror 优先 · 零损存档与模型 · 内存热更新 + 自动备份兜底） ====================
UPDATE_HF_REPO = "dongfangshuo/Easy-TRPG"
UPDATE_GH_REPO = "ovopaotai-lab/Easy-TRPG"
_UVICORN_SERVER: Optional[uvicorn.Server] = None
_PENDING_RESTART_AFTER_UPDATE: bool = False
_RESTART_BYPASS_SUPERVISOR: bool = False
_UPDATE_LOCK = asyncio.Lock()


class _HotSwappableASGI:
    """零停机热更新 ASGI 动态分发器：不断开监听端口、不卸载本地显存模型，毫秒级切换新版 FastAPI 实例"""
    def __init__(self, target_app: Any):
        self.target_app = target_app
        self.reload_count = 0

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        await self.target_app(scope, receive, send)


_ASGI_DISPATCHER: Optional[_HotSwappableASGI] = None


def _normalize_version_display(ver: str) -> str:
    s = str(ver or "").strip()
    if not s:
        return "0.0.0"
    s = re.sub(r"^v(?=\d)", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^(alpha|beta|rc|dev|pre)[_\-\s]*(\d)", lambda m: f"{m.group(1).lower()} {m.group(2)}", s, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", s).strip()


def _parse_version_tuple(ver: str) -> Tuple[int, Tuple[int, int, int, int], int]:
    s = _normalize_version_display(ver).lower()
    stage_map = {"dev": 0, "pre": 0, "alpha": 1, "a": 1, "beta": 2, "b": 2, "rc": 3}
    stage = 4
    m_stage = re.match(r"^(dev|pre|alpha|beta|rc|a|b)\b", s)
    if m_stage:
        stage = stage_map.get(m_stage.group(1), 4)
        s = s[m_stage.end():].strip()
    nums: List[int] = []
    m_nums = re.search(r"(\d+(?:\.\d+)*)", s)
    if m_nums:
        nums = [int(x) for x in m_nums.group(1).split(".")[:4]]
        tail = s[m_nums.end():]
    else:
        tail = s
    while len(nums) < 4:
        nums.append(0)
    rev = 0
    m_rev = re.search(r"(?:r|rev|patch|hotfix|p)[_\-\s]*(\d+)", tail)
    if m_rev:
        rev = int(m_rev.group(1))
    return (stage, (nums[0], nums[1], nums[2], nums[3]), rev)


def _compare_versions(v1: str, v2: str) -> int:
    t1 = _parse_version_tuple(v1)
    t2 = _parse_version_tuple(v2)
    if t1 > t2:
        return 1
    if t1 < t2:
        return -1
    return 0


try:
    _vj_file = BASE_DIR / "version.json"
    if _vj_file.exists():
        _vj_obj = json.loads(_vj_file.read_text(encoding="utf-8"))
        _vj_ver = _normalize_version_display(str(_vj_obj.get("version") or ""))
        if _vj_ver and _compare_versions(_vj_ver, APP_VERSION) > 0:
            APP_VERSION = _vj_ver
            app.version = APP_VERSION
except Exception:
    pass


def _resolve_configured_proxy_url(username: str = "player") -> str:
    try:
        st = load_user_settings(username)
        p = str(st.get("proxy") or "").strip()
        if p:
            return p
    except Exception:
        pass
    for env_k in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
        val = os.environ.get(env_k, "").strip()
        if val:
            return val
    return ""


async def _probe_update_channels_once(client: httpx.AsyncClient, source_prefix: str = "") -> Optional[Dict[str, Any]]:
    # 支持测试/私有镜像环境变量覆盖 manifest 地址
    override_manifest_url = os.environ.get("TRPG_UPDATE_MANIFEST_URL", "").strip()
    if override_manifest_url:
        r = await client.get(override_manifest_url, timeout=8.0)
        r.raise_for_status()
        m = r.json()
        ver = _normalize_version_display(str(m.get("version") or APP_VERSION))
        dl_urls = list(m.get("download_urls") or ([] if not m.get("download_url") else [m["download_url"]]))
        return {
            "version": ver,
            "size_bytes": int(m.get("size") or m.get("size_bytes") or 490_000),
            "sha256": str(m.get("sha256") or "").strip().lower(),
            "notes": str(m.get("notes") or "").strip(),
            "published_at": str(m.get("published_at") or "").strip(),
            "download_urls": dl_urls,
            "source": m.get("source") or "custom-manifest",
        }

    best_candidate: Optional[Dict[str, Any]] = None

    # 渠道 1 & 2：优先走国内高速镜像 hf-mirror.com，其次 huggingface.co
    hf_hosts = [
        ("hf-mirror.com", "https://hf-mirror.com", "https://huggingface.co"),
        ("huggingface.co", "https://huggingface.co", "https://hf-mirror.com"),
    ]
    for host_label, primary_host, backup_host in hf_hosts:
        try:
            api_url = f"{primary_host}/api/models/{UPDATE_HF_REPO}"
            resp = await client.get(api_url, timeout=8.0)
            if resp.status_code != 200:
                continue
            repo_info = resp.json()
            siblings = repo_info.get("siblings") or []
            sib_names = [str(s.get("rfilename") or "") for s in siblings if isinstance(s, dict)]

            # 1a. 扫描仓库内所有 AI跑团工作台_API纯净版_<ver>.zip（即使未放 version.json 也能全自动识别最新版！）
            best_zip_ver = ""
            best_zip_name = ""
            best_zip_size = 0
            for s in siblings:
                if not isinstance(s, dict):
                    continue
                rfn = str(s.get("rfilename") or "")
                m_zip = re.match(r"^AI跑团工作台_API纯净版_(.+)\.zip$", rfn)
                if m_zip:
                    cand_v = _normalize_version_display(m_zip.group(1))
                    if not best_zip_ver or _compare_versions(cand_v, best_zip_ver) > 0:
                        best_zip_ver = cand_v
                        best_zip_name = rfn
                        lfs_info = s.get("lfs") if isinstance(s.get("lfs"), dict) else {}
                        best_zip_size = int(lfs_info.get("size") or s.get("size") or 0)

            # 1b. 若存在 version.json，读取详细更新日志、精确体积与 sha256
            manifest_data: Dict[str, Any] = {}
            if "version.json" in sib_names:
                try:
                    r_ver = await client.get(f"{primary_host}/{UPDATE_HF_REPO}/resolve/main/version.json", timeout=6.0)
                    if r_ver.status_code == 200:
                        parsed = r_ver.json()
                        if isinstance(parsed, dict):
                            manifest_data = parsed
                except Exception:
                    pass

            mf_ver = _normalize_version_display(str(manifest_data.get("version") or "")) if manifest_data.get("version") else ""
            mf_pkg = str(manifest_data.get("package") or "").strip()
            if mf_ver and mf_pkg and (not best_zip_ver or _compare_versions(mf_ver, best_zip_ver) >= 0):
                chosen_ver = mf_ver
                chosen_pkg = mf_pkg
                chosen_size = int(manifest_data.get("size") or best_zip_size or 490_000)
                chosen_sha = str(manifest_data.get("sha256") or "").strip().lower()
                chosen_notes = str(manifest_data.get("notes") or "").strip()
                chosen_pub = str(manifest_data.get("published_at") or "").strip()
            elif best_zip_ver and best_zip_name:
                chosen_ver = best_zip_ver
                chosen_pkg = best_zip_name
                chosen_size = int(best_zip_size or 490_000)
                chosen_sha = ""
                chosen_notes = ""
                chosen_pub = ""
            else:
                continue

            enc_pkg = quote(chosen_pkg, safe="/._-")
            dl_urls = [
                f"{primary_host}/{UPDATE_HF_REPO}/resolve/main/{enc_pkg}",
                f"{backup_host}/{UPDATE_HF_REPO}/resolve/main/{enc_pkg}",
            ]
            best_candidate = {
                "version": chosen_ver,
                "package": chosen_pkg,
                "size_bytes": chosen_size,
                "sha256": chosen_sha,
                "notes": chosen_notes,
                "published_at": chosen_pub,
                "download_urls": dl_urls,
                "source": f"{source_prefix}{host_label}",
            }
            break
        except Exception:
            continue

    # 渠道 3：快速探测 GitHub 主分支是否有更新的源码热修提交（短超时，国内不通时静默跳过绝不卡顿）
    try:
        r_gh_v = await client.get(
            f"https://raw.githubusercontent.com/{UPDATE_GH_REPO}/main/version.json",
            timeout=4.0,
        )
        if r_gh_v.status_code == 200:
            gh_mf = r_gh_v.json()
            if isinstance(gh_mf, dict) and gh_mf.get("version"):
                gh_ver = _normalize_version_display(str(gh_mf["version"]))
                if not best_candidate or _compare_versions(gh_ver, best_candidate["version"]) > 0:
                    best_candidate = {
                        "version": gh_ver,
                        "package": f"{UPDATE_GH_REPO.split('/')[-1]}-main.zip",
                        "size_bytes": int(gh_mf.get("size") or 520_000),
                        "sha256": "",
                        "notes": str(gh_mf.get("notes") or "").strip(),
                        "published_at": str(gh_mf.get("published_at") or "").strip(),
                        "download_urls": [f"https://codeload.github.com/{UPDATE_GH_REPO}/zip/refs/heads/main"],
                        "source": f"{source_prefix}github.com",
                    }
        elif best_candidate is None:
            r_gh_srv = await client.get(
                f"https://raw.githubusercontent.com/{UPDATE_GH_REPO}/main/server.py",
                headers={"Range": "bytes=0-48000"},
                timeout=4.0,
            )
            if r_gh_srv.status_code in (200, 206):
                m_av = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', r_gh_srv.text)
                if m_av:
                    gh_ver = _normalize_version_display(m_av.group(1))
                    best_candidate = {
                        "version": gh_ver,
                        "package": f"{UPDATE_GH_REPO.split('/')[-1]}-main.zip",
                        "size_bytes": 520_000,
                        "sha256": "",
                        "notes": "",
                        "published_at": "",
                        "download_urls": [f"https://codeload.github.com/{UPDATE_GH_REPO}/zip/refs/heads/main"],
                        "source": f"{source_prefix}github.com",
                    }
    except Exception:
        pass

    return best_candidate


async def _fetch_remote_update_manifest(allow_proxy: bool = False, username: str = "player") -> Dict[str, Any]:
    """严格遵循直连优先原则：先禁用一切代理直连 hf-mirror / HF / GitHub；全部不通时询问用户获批后才走代理"""
    headers = {"User-Agent": f"Easy-TRPG-Updater/{APP_VERSION}"}
    async with httpx.AsyncClient(trust_env=False, follow_redirects=True, headers=headers) as direct_client:
        direct_res = await _probe_update_channels_once(direct_client, source_prefix="")
        if direct_res is not None:
            return {"ok": True, **direct_res}

    proxy_url = _resolve_configured_proxy_url(username)
    est_mb = 0.5
    if not allow_proxy:
        if proxy_url:
            return {
                "ok": False,
                "need_proxy_confirm": True,
                "estimated_size_mb": est_mb,
                "message": f"直连下载无法连通，目标文件大小约为 {est_mb} MB，是否允许走代理流量下载？",
            }
        return {
            "ok": False,
            "need_proxy_confirm": False,
            "message": "无法连接更新源（hf-mirror.com / HuggingFace / GitHub 均未响应），请检查网络连接或在「设置 → 代理」中配置代理后重试。",
        }

    if not proxy_url:
        return {
            "ok": False,
            "need_proxy_confirm": False,
            "message": "未检测到可用的代理地址，请先在「设置 → 代理」中填写代理地址（如 http://127.0.0.1:7890）后再试。",
        }

    try:
        async with httpx.AsyncClient(proxy=proxy_url, trust_env=False, follow_redirects=True, headers=headers) as proxy_client:
            proxy_res = await _probe_update_channels_once(proxy_client, source_prefix="proxy:")
            if proxy_res is not None:
                return {"ok": True, **proxy_res}
    except Exception as e:
        return {"ok": False, "need_proxy_confirm": False, "message": f"通过代理连接更新源失败：{e}"}

    return {"ok": False, "need_proxy_confirm": False, "message": "通过代理仍无法获取版本信息，请检查代理节点状态。"}


async def _download_update_archive_bytes(
    download_urls: List[str],
    allow_proxy: bool = False,
    username: str = "player",
    expected_size_mb: float = 0.5,
    expected_size_bytes: int = 0,
    progress_cb: Optional[Callable[[int, int], Awaitable[None]]] = None,
) -> Tuple[Optional[bytes], Optional[Dict[str, Any]]]:
    """优先直连下载更新包（上限保护 60MB）；直连失败时必须先报体积经用户同意后才允许走代理"""
    headers = {"User-Agent": f"Easy-TRPG-Updater/{APP_VERSION}"}
    max_update_bytes = 60 * 1024 * 1024

    async def _try_urls_with_client(client: httpx.AsyncClient) -> Optional[bytes]:
        for u in download_urls:
            if not u:
                continue
            try:
                async with client.stream("GET", u, timeout=45.0) as resp:
                    if resp.status_code != 200:
                        continue
                    content_len = 0
                    try:
                        content_len = int(resp.headers.get("content-length") or 0)
                    except Exception:
                        content_len = 0
                    target_total = content_len or int(expected_size_bytes or 0)
                    chunks: List[bytes] = []
                    total = 0
                    async for chunk in resp.aiter_bytes(chunk_size=16384):
                        total += len(chunk)
                        if total > max_update_bytes:
                            raise ValueError("更新包体积异常超出安全上限 (60MB)，已中止下载")
                        chunks.append(chunk)
                        if progress_cb is not None:
                            try:
                                await progress_cb(total, target_total)
                            except Exception:
                                pass
                    raw = b"".join(chunks)
                    if len(raw) > 1024:
                        return raw
            except Exception:
                continue
        return None

    # 1. 强制优先本地直连（显式禁用代理环境变量）
    async with httpx.AsyncClient(trust_env=False, follow_redirects=True, headers=headers) as direct_client:
        data = await _try_urls_with_client(direct_client)
        if data is not None:
            return data, None

    proxy_url = _resolve_configured_proxy_url(username)
    size_disp = round(max(0.1, float(expected_size_mb or 0.5)), 2)
    if not allow_proxy:
        if proxy_url:
            return None, {
                "ok": False,
                "need_proxy_confirm": True,
                "estimated_size_mb": size_disp,
                "message": f"直连下载无法连通，目标文件大小约为 {size_disp} MB，是否允许走代理流量下载？",
            }
        return None, {
            "ok": False,
            "need_proxy_confirm": False,
            "message": "直连下载更新包失败，请检查网络连接或在「设置 → 代理」中配置代理后重试。",
        }

    if not proxy_url:
        return None, {
            "ok": False,
            "need_proxy_confirm": False,
            "message": "未配置有效代理地址，无法走代理下载。",
        }

    async with httpx.AsyncClient(proxy=proxy_url, trust_env=False, follow_redirects=True, headers=headers) as proxy_client:
        data = await _try_urls_with_client(proxy_client)
        if data is not None:
            return data, None

    return None, {"ok": False, "need_proxy_confirm": False, "message": "通过代理下载更新包失败，请稍后重试。"}


def _is_allowed_update_rel_path(rel_posix: str) -> Tuple[bool, bool]:
    """返回 (是否允许处理, 是否仅在目标文件不存在时才初始化写入)"""
    if not rel_posix or rel_posix.startswith("/") or ".." in rel_posix.split("/") or ":" in rel_posix:
        return (False, False)
    low = rel_posix.lower()
    if low.endswith((".pyc", ".pyo", ".pyd", ".dll", ".exe", ".so", ".gguf", ".keep")):
        return (False, False)
    if low in (".hf_token", ".gh_token", ".env"):
        return (False, False)
    # 绝对保护区：本地模型、备份、Python 运行时、推理引擎、Git 仓库
    if low.startswith(("model/", "models/", "backups/", "runtime/", "engine/", ".git/", "__pycache__/")):
        return (False, False)
    # 玩家存档与个人设置保护区：已存在任何文件时 100% 跳过绝不覆盖；仅当全新缺失默认种子时才补充
    if low.startswith("data/"):
        return (True, True)
    if "/" not in rel_posix:
        if low.endswith((".py", ".bat", ".sh", ".md", ".txt", ".json")) or low == ".gitignore":
            return (True, False)
        return (False, False)
    if low.startswith(("static/", "tutorial/")):
        return (True, False)
    return (False, False)


def _apply_update_zip_bytes(zip_bytes: bytes, expected_sha256: str = "", target_version: str = "") -> Dict[str, Any]:
    """校验更新包完整性与 Python 语法，备份当前代码至 backups/，并原子替换代码与静态资源（100% 保留 data/ 与 model/）"""
    global _RESTART_BYPASS_SUPERVISOR
    if not zip_bytes or len(zip_bytes) < 512:
        raise ValueError("更新包数据为空或已损坏")
    if expected_sha256:
        actual_sha = hashlib.sha256(zip_bytes).hexdigest().lower()
        if actual_sha != expected_sha256.lower():
            raise ValueError(f"更新包 SHA256 校验不匹配（期望 {expected_sha256[:12]}...，实际 {actual_sha[:12]}...）")

    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        corrupt_member = zf.testzip()
        if corrupt_member is not None:
            raise ValueError(f"更新压缩包内文件损坏：{corrupt_member}")

        raw_entries: List[Tuple[str, zipfile.ZipInfo]] = []
        for zi in zf.infolist():
            if zi.is_dir():
                continue
            norm_name = zi.filename.replace("\\", "/").lstrip("/")
            if norm_name:
                raw_entries.append((norm_name, zi))

        if not raw_entries:
            raise ValueError("更新压缩包为空")

        # 自动剥离顶层单目录前缀（如 AI跑团工作台_API纯净版_alpha1.6/ 或 Easy-TRPG-main/）
        first_segs = {n.split("/", 1)[0] for n, _ in raw_entries if "/" in n}
        all_under_single_root = len(first_segs) == 1 and all("/" in n for n, _ in raw_entries)
        strip_prefix = (next(iter(first_segs)) + "/") if all_under_single_root else ""

        staged_files: Dict[str, bytes] = {}
        seed_only_files: Dict[str, bytes] = {}
        for norm_name, zi in raw_entries:
            rel = norm_name[len(strip_prefix):] if (strip_prefix and norm_name.startswith(strip_prefix)) else norm_name
            allowed, only_if_missing = _is_allowed_update_rel_path(rel)
            if not allowed:
                continue
            content = zf.read(zi)
            if only_if_missing:
                seed_only_files[rel] = content
            else:
                staged_files[rel] = content

    required_core = ("server.py", "enterprise_engine.py", "static/app.js", "static/index.html")
    missing_core = [rk for rk in required_core if rk not in staged_files]
    if missing_core:
        raise ValueError(f"更新包结构不完整，缺少核心文件：{', '.join(missing_core)}")

    # 在写入磁盘前先在内存中对全部根目录 .py 执行 AST/字节码编译校验，杜绝半截或语法损坏代码落地
    detected_new_ver = _normalize_version_display(target_version) if target_version else ""
    for rel, raw_b in staged_files.items():
        if rel.endswith(".py") and "/" not in rel:
            src_txt = raw_b.decode("utf-8")
            compile(src_txt, rel, "exec")
            if rel == "server.py" and not detected_new_ver:
                m_v = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', src_txt)
                if m_v:
                    detected_new_ver = _normalize_version_display(m_v.group(1))

    # 规范化脚本换行符（.bat 保持 CRLF，.sh 保持纯 LF）
    normalized_writes: Dict[str, bytes] = {}
    for rel, raw_b in staged_files.items():
        low = rel.lower()
        if low.endswith(".bat"):
            txt = raw_b.decode("utf-8", errors="surrogateescape").replace("\r\n", "\n").replace("\r", "\n")
            normalized_writes[rel] = txt.replace("\n", "\r\n").encode("utf-8", errors="surrogateescape")
        elif low.endswith(".sh"):
            txt = raw_b.decode("utf-8", errors="surrogateescape").replace("\r\n", "\n").replace("\r", "\n")
            normalized_writes[rel] = txt.encode("utf-8", errors="surrogateescape")
        else:
            normalized_writes[rel] = raw_b

    # 筛选真正有字节变化的文件，并在覆盖前自动打包备份旧版代码至 backups/
    changed_rels: List[str] = []
    for rel, new_b in normalized_writes.items():
        dst = (BASE_DIR / rel).resolve()
        if BASE_DIR.resolve() not in dst.parents and dst != BASE_DIR.resolve():
            raise ValueError(f"非法更新路径：{rel}")
        if dst.exists() and dst.is_file():
            try:
                if dst.read_bytes() == new_b:
                    continue
            except Exception:
                pass
        changed_rels.append(rel)

    backup_rel_path = ""
    if changed_rels:
        backups_dir = BASE_DIR / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)
        safe_old_ver = re.sub(r"[^a-zA-Z0-9._-]+", "_", APP_VERSION)
        ts_str = time.strftime("%Y%m%d_%H%M%S")
        backup_zip_path = backups_dir / f"code_backup_{safe_old_ver}_{ts_str}.zip"
        with zipfile.ZipFile(backup_zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bzf:
            for rel in sorted(changed_rels):
                cur_p = BASE_DIR / rel
                if cur_p.exists() and cur_p.is_file():
                    bzf.write(cur_p, arcname=rel)
        backup_rel_path = f"backups/{backup_zip_path.name}"
        # 仅保留最近 5 份更新代码备份，避免占用多余磁盘空间
        old_baks = sorted(backups_dir.glob("code_backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        for stale_b in old_baks[5:]:
            try:
                stale_b.unlink()
            except Exception:
                pass

    # 原子替换所有变更的代码与前端资源文件
    uid_tag = uuid.uuid4().hex[:8]
    for rel in changed_rels:
        if os.name == "nt" and rel in ("run.bat", "一键启动_AI跑团工作台.bat"):
            _RESTART_BYPASS_SUPERVISOR = True
        dst = BASE_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp_dst = dst.parent / f".{dst.name}.upd_{uid_tag}"
        tmp_dst.write_bytes(normalized_writes[rel])
        if os.name != "nt" and rel.lower().endswith(".sh"):
            try:
                os.chmod(tmp_dst, 0o755)
            except Exception:
                pass
        os.replace(str(tmp_dst), str(dst))

    # 仅补充本地尚不存在的默认 data/ 种子文件（100% 不触碰任何已有存档、设置、剧本与角色卡）
    seeded_count = 0
    for rel, seed_b in seed_only_files.items():
        dst = BASE_DIR / rel
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(seed_b)
            seeded_count += 1

    # 清理项目根目录与 static 下的 __pycache__ 缓存，确保重启后加载最新字节码
    for pc in [BASE_DIR / "__pycache__"]:
        if pc.exists():
            shutil.rmtree(pc, ignore_errors=True)

    return {
        "old_version": APP_VERSION,
        "new_version": detected_new_ver or target_version or APP_VERSION,
        "updated_count": len(changed_rels),
        "updated_files": changed_rels,
        "seeded_count": seeded_count,
        "backup_file": backup_rel_path,
    }


def _perform_backend_hot_reload(changed_rels: List[str], target_version: str = "") -> Dict[str, Any]:
    """在当前进程内执行零停机热更新：
    1. 若仅静态资源 / 配置变更：刷新版本号与缓存指纹，0ms 无感生效；
    2. 若 Python 后端变更：热重载 enterprise_engine 并构建新 FastAPI 实例原子切换至 _ASGI_DISPATCHER，不断端口、不卸载本地显存模型。
    """
    global APP_VERSION, _SERVER_BOOT_ID
    norm_ver = _normalize_version_display(target_version) if target_version else APP_VERSION
    py_changed = any(str(r).lower().endswith(".py") for r in (changed_rels or []))
    main_mod = sys.modules.get("__main__")

    if not py_changed:
        if norm_ver:
            APP_VERSION = norm_ver
            app.version = APP_VERSION
        _SERVER_BOOT_ID = uuid.uuid4().hex[:10]
        if main_mod is not None:
            setattr(main_mod, "APP_VERSION", APP_VERSION)
            setattr(main_mod, "_SERVER_BOOT_ID", _SERVER_BOOT_ID)
        _set_windows_console_title(f"AI 跑团 ({APP_VERSION})")
        return {
            "hot_updated": True,
            "mode": "static_hot",
            "boot_id": _SERVER_BOOT_ID,
            "version": APP_VERSION,
        }

    dispatcher = _ASGI_DISPATCHER or getattr(main_mod, "_ASGI_DISPATCHER", None)
    uv_srv = _UVICORN_SERVER or getattr(main_mod, "_UVICORN_SERVER", None)
    if dispatcher is None:
        return {"hot_updated": False, "reason": "no_asgi_dispatcher"}

    try:
        ee_mod = sys.modules.get("enterprise_engine")
        if ee_mod is not None:
            alive_procs = [p for p in getattr(ee_mod, "_SPAWNED_ENGINE_PROCS", []) if p and p.poll() is None]
            strata_port = getattr(ee_mod, "_ACTIVE_STRATA_PORT", 8080)
            llama_port = getattr(ee_mod, "_ACTIVE_LLAMA_PORT", 8081)
            hf_tasks = dict(getattr(ee_mod, "HF_DOWNLOAD_TASKS", {}))
            hf_async = dict(getattr(ee_mod, "HF_DOWNLOAD_ASYNC_TASKS", {}))
            win32_job = getattr(ee_mod, "_WIN32_ENGINE_JOB_HANDLE", None)
            win32_ctrl = getattr(ee_mod, "_WIN32_CONSOLE_CTRL_REF", None)
            if win32_job:
                setattr(sys, "_trpg_win32_engine_job_handle", win32_job)
            if win32_ctrl is not None:
                setattr(sys, "_trpg_win32_console_ctrl_ref", win32_ctrl)
            ee_mod = importlib.reload(ee_mod)
            ee_mod._SPAWNED_ENGINE_PROCS[:] = alive_procs
            ee_mod._ACTIVE_STRATA_PORT = strata_port
            ee_mod._ACTIVE_LLAMA_PORT = llama_port
            if win32_job:
                ee_mod._WIN32_ENGINE_JOB_HANDLE = win32_job
            if win32_ctrl is not None:
                ee_mod._WIN32_CONSOLE_CTRL_REF = win32_ctrl
            ee_mod.HF_DOWNLOAD_TASKS.update(hf_tasks)
            ee_mod.HF_DOWNLOAD_ASYNC_TASKS.update(hf_async)
            ee_mod.set_active_web_server_port(SERVER_PORT)

        mod_name = f"_trpg_hot_srv_{int(time.time() * 1000)}_{uuid.uuid4().hex[:4]}"
        spec = importlib.util.spec_from_file_location(mod_name, str(BASE_DIR / "server.py"))
        if spec is None or spec.loader is None:
            return {"hot_updated": False, "reason": "spec_load_failed"}
        new_srv = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = new_srv
        spec.loader.exec_module(new_srv)

        new_srv.SERVER_PORT = SERVER_PORT
        new_srv._UVICORN_SERVER = uv_srv
        new_srv._ASGI_DISPATCHER = dispatcher
        new_srv._HAS_ACTIVE_CLIENT = True
        new_srv._PENDING_BROWSER_OPEN_URL = None
        if norm_ver and _compare_versions(norm_ver, getattr(new_srv, "APP_VERSION", "")) > 0:
            new_srv.APP_VERSION = norm_ver
            new_srv.app.version = norm_ver

        dispatcher.target_app = new_srv.app
        dispatcher.reload_count = getattr(dispatcher, "reload_count", 0) + 1
        if main_mod is not None:
            setattr(main_mod, "APP_VERSION", new_srv.APP_VERSION)
            setattr(main_mod, "_SERVER_BOOT_ID", new_srv._SERVER_BOOT_ID)

        stale_mods = [k for k in list(sys.modules.keys()) if k.startswith("_trpg_hot_srv_") and k != mod_name]
        for sk in stale_mods:
            sys.modules.pop(sk, None)

        _set_windows_console_title(f"AI 跑团 ({new_srv.APP_VERSION})")
        print(f"\n[热更新] 已完成内存零停机热替换 -> {new_srv.APP_VERSION} (reload #{dispatcher.reload_count})")
        return {
            "hot_updated": True,
            "mode": "asgi_hot_swap",
            "boot_id": new_srv._SERVER_BOOT_ID,
            "version": new_srv.APP_VERSION,
        }
    except Exception as exc:
        print(f"\n[热更新] 内存热替换异常，自动回退至平滑重启: {exc}")
        return {"hot_updated": False, "reason": str(exc)}


async def _trigger_graceful_self_restart(delay_sec: float = 0.6) -> None:
    global _PENDING_RESTART_AFTER_UPDATE
    await asyncio.sleep(max(0.1, delay_sec))
    _PENDING_RESTART_AFTER_UPDATE = True
    main_mod = sys.modules.get("__main__")
    if main_mod is not None:
        setattr(main_mod, "_PENDING_RESTART_AFTER_UPDATE", True)
        if _RESTART_BYPASS_SUPERVISOR:
            setattr(main_mod, "_RESTART_BYPASS_SUPERVISOR", True)
    uv_srv = _UVICORN_SERVER or getattr(main_mod, "_UVICORN_SERVER", None)
    if uv_srv is not None:
        uv_srv.should_exit = True


@app.get("/api/system/version")
def api_system_version():
    return {
        "ok": True,
        "version": APP_VERSION,
        "boot_id": _SERVER_BOOT_ID,
    }


class DevHotReloadRequest(BaseModel):
    changed_files: List[str] = ["server.py", "enterprise_engine.py"]
    target_version: str = ""


@app.post("/api/system/dev/hot_reload", dependencies=[Depends(require_loopback)])
async def api_system_dev_hot_reload(req: DevHotReloadRequest):
    """供本地纯净开发母本 sync_to_personal.py 单向推送代码后，零停机热重载个人工作台内存实例"""
    info = _perform_backend_hot_reload(req.changed_files or ["server.py", "enterprise_engine.py"], req.target_version)
    return {"ok": True, **info}


@app.get("/api/system/update/check")
async def api_system_update_check(request: Request, allow_proxy: bool = False):
    username = get_current_user(request)
    mf = await _fetch_remote_update_manifest(allow_proxy=allow_proxy, username=username)
    if not mf.get("ok"):
        return {
            "ok": False,
            "current_version": APP_VERSION,
            "boot_id": _SERVER_BOOT_ID,
            "need_proxy_confirm": bool(mf.get("need_proxy_confirm")),
            "estimated_size_mb": mf.get("estimated_size_mb", 0.5),
            "message": mf.get("message") or "检查更新失败",
        }
    remote_ver = _normalize_version_display(str(mf.get("version") or APP_VERSION))
    cmp_res = _compare_versions(remote_ver, APP_VERSION)
    has_update = cmp_res > 0
    can_repair = cmp_res >= 0
    size_bytes = int(mf.get("size_bytes") or 490_000)
    size_mb = round(max(0.1, size_bytes / (1024 * 1024)), 2)
    return {
        "ok": True,
        "current_version": APP_VERSION,
        "latest_version": remote_ver if cmp_res >= 0 else APP_VERSION,
        "remote_version": remote_ver,
        "has_update": has_update,
        "can_repair": can_repair,
        "size_bytes": size_bytes,
        "size_mb": size_mb,
        "source": mf.get("source") or "hf-mirror.com",
        "notes": mf.get("notes") or "",
        "published_at": mf.get("published_at") or "",
        "boot_id": _SERVER_BOOT_ID,
    }


class SystemUpdateApplyRequest(BaseModel):
    allow_proxy: bool = False
    force: bool = False
    force_reinstall: bool = False


@app.post("/api/system/update/apply", dependencies=[Depends(require_loopback)])
async def api_system_update_apply(req: SystemUpdateApplyRequest, request: Request):
    if _UPDATE_LOCK.locked():
        raise HTTPException(status_code=409, detail="正在执行更新任务，请勿重复点击")
    async with _UPDATE_LOCK:
        if not req.force:
            running_chats = [cid for cid, t in ACTIVE_BG_TASKS.items() if t and not t.done()]
            if running_chats:
                raise HTTPException(status_code=409, detail="当前有正在生成的对话回复，请先停止生成或等待完成后再更新。")
            active_dls = [
                t for t in HF_DOWNLOAD_TASKS.values()
                if isinstance(t, dict) and t.get("status") in ("downloading", "starting")
            ]
            if active_dls:
                raise HTTPException(status_code=409, detail="当前后台正在下载本地模型，请等待下载完成或先暂停下载后再执行软件更新。")

        username = get_current_user(request)
        mf = await _fetch_remote_update_manifest(allow_proxy=req.allow_proxy, username=username)
        if not mf.get("ok"):
            return JSONResponse(
                status_code=200,
                content={
                    "ok": False,
                    "need_proxy_confirm": bool(mf.get("need_proxy_confirm")),
                    "estimated_size_mb": mf.get("estimated_size_mb", 0.5),
                    "message": mf.get("message") or "无法获取更新信息",
                },
            )

        remote_ver = _normalize_version_display(str(mf.get("version") or APP_VERSION))
        cmp_res = _compare_versions(remote_ver, APP_VERSION)
        if cmp_res < 0 or (cmp_res == 0 and not req.force_reinstall):
            return {
                "ok": True,
                "already_latest": True,
                "can_repair": bool(cmp_res == 0),
                "old_version": APP_VERSION,
                "new_version": APP_VERSION,
                "hot_updated": False,
                "restarting": False,
                "message": f"当前已是最新版本 ({APP_VERSION})",
            }

        expected_bytes = int(mf.get("size_bytes") or 490_000)
        est_mb = round(max(0.1, expected_bytes / (1024 * 1024)), 2)
        dl_urls = list(mf.get("download_urls") or [])
        if not dl_urls:
            raise HTTPException(status_code=502, detail="未找到有效的更新包下载地址")

        zip_bytes, dl_err = await _download_update_archive_bytes(
            dl_urls,
            allow_proxy=req.allow_proxy,
            username=username,
            expected_size_mb=est_mb,
            expected_size_bytes=expected_bytes,
        )
        if zip_bytes is None:
            return JSONResponse(status_code=200, content=dl_err or {"ok": False, "message": "下载更新包失败"})

        try:
            apply_res = await asyncio.to_thread(
                _apply_update_zip_bytes,
                zip_bytes,
                str(mf.get("sha256") or ""),
                remote_ver,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"更新包校验或写入失败（原文件未受损）：{e}")

        changed_rels = list(apply_res.get("updated_files") or [])
        frontend_js_or_html_changed = any(
            r == "static/index.html" or (r.startswith("static/") and r.lower().endswith(".js"))
            for r in changed_rels
        )
        frontend_css_changed = any(
            r.startswith("static/") and r.lower().endswith(".css")
            for r in changed_rels
        )
        hot_info = _perform_backend_hot_reload(changed_rels, str(apply_res.get("new_version") or remote_ver))
        hot_ok = bool(hot_info.get("hot_updated"))
        if not hot_ok:
            asyncio.create_task(_trigger_graceful_self_restart(0.5))

        return {
            "ok": True,
            "hot_updated": hot_ok,
            "hot_mode": hot_info.get("mode", ""),
            "restarting": not hot_ok,
            "frontend_reload_needed": frontend_js_or_html_changed,
            "css_hot_swap": frontend_css_changed,
            "boot_id": hot_info.get("boot_id") or _SERVER_BOOT_ID,
            **apply_res,
        }


@app.post("/api/system/update/stream", dependencies=[Depends(require_loopback)])
async def api_system_update_stream(req: SystemUpdateApplyRequest, request: Request):
    """流式一键热更新接口：单次请求串行推送「检查 -> 分块下载进度 -> 校验备份 -> 内存零停机热更新」实时百分比"""
    if _UPDATE_LOCK.locked():
        raise HTTPException(status_code=409, detail="正在执行更新任务，请勿重复点击")

    username = get_current_user(request)

    async def _ndjson_gen():
        def _pack(payload: Dict[str, Any]) -> bytes:
            return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")

        async with _UPDATE_LOCK:
            if not req.force:
                running_chats = [cid for cid, t in ACTIVE_BG_TASKS.items() if t and not t.done()]
                if running_chats:
                    yield _pack({
                        "ok": False,
                        "stage": "error",
                        "percent": 0,
                        "message": "当前有正在生成的对话回复，请先停止生成或等待完成后再更新。",
                    })
                    return
                active_dls = [
                    t for t in HF_DOWNLOAD_TASKS.values()
                    if isinstance(t, dict) and t.get("status") in ("downloading", "starting")
                ]
                if active_dls:
                    yield _pack({
                        "ok": False,
                        "stage": "error",
                        "percent": 0,
                        "message": "当前后台正在下载本地模型，请等待下载完成或先暂停下载后再更新。",
                    })
                    return

            yield _pack({
                "ok": True,
                "stage": "checking",
                "percent": 10,
                "current_version": APP_VERSION,
                "message": "正在直连镜像源检查最新版本...",
            })
            mf = await _fetch_remote_update_manifest(allow_proxy=req.allow_proxy, username=username)
            if not mf.get("ok"):
                yield _pack({
                    "ok": False,
                    "stage": "need_proxy" if mf.get("need_proxy_confirm") else "error",
                    "percent": 12,
                    "current_version": APP_VERSION,
                    "need_proxy_confirm": bool(mf.get("need_proxy_confirm")),
                    "estimated_size_mb": mf.get("estimated_size_mb", 0.5),
                    "message": mf.get("message") or "无法获取更新信息",
                })
                return

            remote_ver = _normalize_version_display(str(mf.get("version") or APP_VERSION))
            cmp_res = _compare_versions(remote_ver, APP_VERSION)
            expected_bytes = int(mf.get("size_bytes") or 490_000)
            est_mb = round(max(0.1, expected_bytes / (1024 * 1024)), 2)

            if cmp_res < 0 or (cmp_res == 0 and not req.force_reinstall):
                yield _pack({
                    "ok": True,
                    "stage": "done",
                    "already_latest": True,
                    "hot_updated": False,
                    "restarting": False,
                    "percent": 100,
                    "old_version": APP_VERSION,
                    "new_version": APP_VERSION,
                    "remote_version": remote_ver,
                    "can_repair": bool(cmp_res == 0),
                    "size_mb": est_mb,
                    "boot_id": _SERVER_BOOT_ID,
                    "message": f"当前已是最新版本 ({APP_VERSION})",
                })
                return

            dl_urls = list(mf.get("download_urls") or [])
            if not dl_urls:
                yield _pack({"ok": False, "stage": "error", "percent": 15, "message": "未找到有效的更新包下载地址"})
                return

            action_label = "重新校验热修复" if (cmp_res == 0 and req.force_reinstall) else f"更新至 {remote_ver}"
            yield _pack({
                "ok": True,
                "stage": "manifest",
                "percent": 18,
                "old_version": APP_VERSION,
                "latest_version": remote_ver,
                "size_bytes": expected_bytes,
                "size_mb": est_mb,
                "source": mf.get("source") or "hf-mirror.com",
                "notes": mf.get("notes") or "",
                "message": f"准备{action_label}（约 {est_mb} MB，来源：{mf.get('source') or 'hf-mirror.com'}）...",
            })

            prog_q: asyncio.Queue = asyncio.Queue()
            last_emit_ts = 0.0
            last_emit_pct = 18

            async def _on_dl_progress(dl_bytes: int, tot_bytes: int) -> None:
                nonlocal last_emit_ts, last_emit_pct
                now = time.monotonic()
                denom = max(tot_bytes, expected_bytes, dl_bytes, 1)
                ratio = min(1.0, max(0.0, dl_bytes / denom))
                pct = min(78, max(19, int(round(18 + ratio * 60))))
                if pct > last_emit_pct or (now - last_emit_ts) >= 0.05:
                    last_emit_ts = now
                    last_emit_pct = pct
                    dl_mb_s = f"{dl_bytes / (1024 * 1024):.2f}"
                    tot_mb_s = f"{denom / (1024 * 1024):.2f}"
                    await prog_q.put({
                        "ok": True,
                        "stage": "downloading",
                        "percent": pct,
                        "downloaded_bytes": dl_bytes,
                        "total_bytes": denom,
                        "latest_version": remote_ver,
                        "message": f"正在下载更新包 ({dl_mb_s} / {tot_mb_s} MB)...",
                    })

            dl_task = asyncio.create_task(
                _download_update_archive_bytes(
                    dl_urls,
                    allow_proxy=req.allow_proxy,
                    username=username,
                    expected_size_mb=est_mb,
                    expected_size_bytes=expected_bytes,
                    progress_cb=_on_dl_progress,
                )
            )
            while not dl_task.done():
                try:
                    ev = await asyncio.wait_for(prog_q.get(), timeout=0.06)
                    yield _pack(ev)
                except asyncio.TimeoutError:
                    pass
            while not prog_q.empty():
                yield _pack(prog_q.get_nowait())

            zip_bytes, dl_err = await dl_task
            if zip_bytes is None:
                err_obj = dl_err or {"ok": False, "message": "下载更新包失败"}
                yield _pack({
                    "ok": False,
                    "stage": "need_proxy" if err_obj.get("need_proxy_confirm") else "error",
                    "percent": last_emit_pct,
                    "need_proxy_confirm": bool(err_obj.get("need_proxy_confirm")),
                    "estimated_size_mb": err_obj.get("estimated_size_mb", est_mb),
                    "message": err_obj.get("message") or "下载更新包失败",
                })
                return

            yield _pack({
                "ok": True,
                "stage": "verifying",
                "percent": 85,
                "latest_version": remote_ver,
                "message": "下载完成，正在校验代码语法与备份旧版文件...",
            })

            try:
                apply_res = await asyncio.to_thread(
                    _apply_update_zip_bytes,
                    zip_bytes,
                    str(mf.get("sha256") or ""),
                    remote_ver,
                )
            except Exception as e:
                yield _pack({
                    "ok": False,
                    "stage": "error",
                    "percent": 85,
                    "message": f"更新包校验或写入失败（原文件未受损）：{e}",
                })
                return

            changed_rels = list(apply_res.get("updated_files") or [])
            yield _pack({
                "ok": True,
                "stage": "applying",
                "percent": 94,
                "updated_count": apply_res.get("updated_count", 0),
                "latest_version": apply_res.get("new_version") or remote_ver,
                "message": f"已原子替换 {apply_res.get('updated_count', 0)} 个变更文件，正在执行内存热更新...",
            })

            frontend_js_or_html_changed = any(
                r == "static/index.html" or (r.startswith("static/") and r.lower().endswith(".js"))
                for r in changed_rels
            )
            frontend_css_changed = any(
                r.startswith("static/") and r.lower().endswith(".css")
                for r in changed_rels
            )

            hot_info = _perform_backend_hot_reload(changed_rels, str(apply_res.get("new_version") or remote_ver))
            hot_ok = bool(hot_info.get("hot_updated"))
            if not hot_ok:
                asyncio.create_task(_trigger_graceful_self_restart(0.5))

            final_ver_disp = apply_res.get("new_version") or remote_ver
            yield _pack({
                "ok": True,
                "stage": "done",
                "already_latest": False,
                "percent": 100,
                "hot_updated": hot_ok,
                "hot_mode": hot_info.get("mode", ""),
                "restarting": not hot_ok,
                "frontend_reload_needed": frontend_js_or_html_changed,
                "css_hot_swap": frontend_css_changed,
                "boot_id": hot_info.get("boot_id") or _SERVER_BOOT_ID,
                **apply_res,
                "message": (
                    f"热更新完成！已升级至 {final_ver_disp}"
                    if hot_ok
                    else f"更新文件已就绪，正在平滑切换至 {final_ver_disp}..."
                ),
            })

    return StreamingResponse(
        _ndjson_gen(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
        },
    )


# ==================== 机器硬件实时遥测与全维度模型性能测试引擎 ====================
_BENCH_STATIC_CPU_CACHE: Dict[str, Any] = {}
_BENCH_PREV_CPU_TIMES: Tuple[int, int, float] = (0, 0, 0.0)
_BENCH_CPU_LOCK = threading.Lock()


def _get_static_cpu_info() -> Tuple[str, int]:
    if _BENCH_STATIC_CPU_CACHE.get("name"):
        return _BENCH_STATIC_CPU_CACHE["name"], _BENCH_STATIC_CPU_CACHE["threads"]
    import platform
    cpu_name = ""
    cpu_mhz = 0
    threads = os.cpu_count() or 1
    os_name = f"{platform.system()} {platform.release()}"
    board_name = ""
    disk_models: List[str] = []
    try:
        if os.name == "nt":
            import winreg

            def _rv(subk: str, vname: str) -> str:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subk) as k:
                        return str(winreg.QueryValueEx(k, vname)[0] or "").strip()
                except Exception:
                    return ""

            cpu_name = _rv(r"HARDWARE\Description\System\CentralProcessor\0", "ProcessorNameString")
            mhz_raw = _rv(r"HARDWARE\Description\System\CentralProcessor\0", "~MHz")
            if mhz_raw.isdigit():
                cpu_mhz = int(mhz_raw)

            win_prod = _rv(r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "ProductName")
            win_disp = _rv(r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "DisplayVersion")
            win_build = _rv(r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "CurrentBuild")
            if win_build.isdigit() and int(win_build) >= 22000 and "Windows 10" in win_prod:
                win_prod = win_prod.replace("Windows 10", "Windows 11")
            if win_prod:
                os_name = " ".join(x for x in [win_prod, win_disp, f"(Build {win_build})" if win_build else ""] if x)

            mb_mfg = _rv(r"HARDWARE\Description\System\BIOS", "BaseBoardManufacturer") or _rv(
                r"HARDWARE\Description\System\BIOS", "SystemManufacturer"
            )
            mb_prod = _rv(r"HARDWARE\Description\System\BIOS", "BaseBoardProduct") or _rv(
                r"HARDWARE\Description\System\BIOS", "SystemProductName"
            )
            for junk in ("System manufacturer", "System Product Name", "To be filled by O.E.M.", "Default string"):
                mb_mfg = mb_mfg.replace(junk, "").strip()
                mb_prod = mb_prod.replace(junk, "").strip()
            board_name = f"{mb_mfg} {mb_prod}".strip()

            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\disk\Enum") as dk:
                    cnt = int(winreg.QueryValueEx(dk, "Count")[0])
                    for i in range(cnt):
                        raw_d = str(winreg.QueryValueEx(dk, str(i))[0])
                        if "Prod_" in raw_d:
                            part = (
                                raw_d.split("Prod_", 1)[1]
                                .split("\\", 1)[0]
                                .split("&Rev_", 1)[0]
                                .replace("_", " ")
                                .strip(" -")
                            )
                            if part and part not in disk_models:
                                disk_models.append(part)
            except Exception:
                pass
        elif Path("/proc/cpuinfo").exists():
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore").splitlines():
                if "model name" in line.lower() and ":" in line:
                    cpu_name = line.split(":", 1)[1].strip()
                    break
            if Path("/etc/os-release").exists():
                for ln in Path("/etc/os-release").read_text(encoding="utf-8", errors="ignore").splitlines():
                    if ln.startswith("PRETTY_NAME="):
                        os_name = ln.split("=", 1)[1].strip().strip('"')
                        break
        elif sys.platform == "darwin":
            cpu_name = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"], text=True, timeout=1.5
            ).strip()
            os_name = f"macOS {platform.mac_ver()[0]}"
    except Exception:
        pass
    if not cpu_name:
        cpu_name = platform.processor() or platform.machine() or "Generic CPU"
    _BENCH_STATIC_CPU_CACHE.update({
        "name": cpu_name,
        "threads": threads,
        "mhz": cpu_mhz,
        "os_name": os_name,
        "board_name": board_name,
        "disk_models": disk_models,
        "drive_root": BASE_DIR.anchor or str(BASE_DIR)[:3],
    })
    return cpu_name, threads


def _read_raw_cpu_times() -> Optional[Tuple[int, int]]:
    try:
        if os.name == "nt":
            import ctypes

            class _FT(ctypes.Structure):
                _fields_ = [("low", ctypes.c_ulong), ("high", ctypes.c_ulong)]

            idle_ft, kern_ft, user_ft = _FT(), _FT(), _FT()
            if ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(idle_ft), ctypes.byref(kern_ft), ctypes.byref(user_ft)
            ):
                idle = (idle_ft.high << 32) | idle_ft.low
                total = ((kern_ft.high << 32) | kern_ft.low) + ((user_ft.high << 32) | user_ft.low)
                return (idle, total)
        elif Path("/proc/stat").exists():
            first = Path("/proc/stat").read_text(encoding="utf-8", errors="ignore").splitlines()[0]
            parts = [int(x) for x in first.split()[1:] if x.isdigit()]
            if len(parts) >= 4:
                idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
                return (idle, sum(parts))
    except Exception:
        pass
    return None


def _sample_cpu_percent_fast() -> float:
    global _BENCH_PREV_CPU_TIMES
    with _BENCH_CPU_LOCK:
        now = time.monotonic()
        t1 = _read_raw_cpu_times()
        if t1 is None:
            return 0.0
        prev_idle, prev_tot, prev_ts = _BENCH_PREV_CPU_TIMES
        if prev_tot <= 0 or (now - prev_ts) > 12.0 or t1[1] <= prev_tot:
            time.sleep(0.045)
            t2 = _read_raw_cpu_times()
            if t2 is None or t2[1] <= t1[1]:
                _BENCH_PREV_CPU_TIMES = (t1[0], t1[1], time.monotonic())
                return 0.0
            d_idle = t2[0] - t1[0]
            d_tot = t2[1] - t1[1]
            _BENCH_PREV_CPU_TIMES = (t2[0], t2[1], time.monotonic())
        else:
            d_idle = t1[0] - prev_idle
            d_tot = t1[1] - prev_tot
            _BENCH_PREV_CPU_TIMES = (t1[0], t1[1], now)
        return round(max(0.0, min(100.0, (1.0 - (d_idle / max(1, d_tot))) * 100.0)), 1)


def _sample_ram_status() -> Dict[str, Any]:
    try:
        if os.name == "nt":
            import ctypes

            class _MEMSTAT(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            ms = _MEMSTAT()
            ms.dwLength = ctypes.sizeof(_MEMSTAT)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
                tot_g = ms.ullTotalPhys / (1024**3)
                avail_g = ms.ullAvailPhys / (1024**3)
                used_g = max(0.0, tot_g - avail_g)
                return {
                    "total_gib": round(tot_g, 1),
                    "used_gib": round(used_g, 1),
                    "avail_gib": round(avail_g, 1),
                    "percent": round((used_g / max(0.1, tot_g)) * 100.0, 1),
                }
        elif Path("/proc/meminfo").exists():
            kv: Dict[str, int] = {}
            for ln in Path("/proc/meminfo").read_text(encoding="utf-8", errors="ignore").splitlines():
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    nums = [int(x) for x in v.split() if x.isdigit()]
                    if nums:
                        kv[k.strip()] = nums[0]
            tot_kb = kv.get("MemTotal", 0)
            avail_kb = kv.get("MemAvailable", kv.get("MemFree", 0))
            if tot_kb > 0:
                tot_g = tot_kb / (1024**2)
                avail_g = avail_kb / (1024**2)
                used_g = max(0.0, tot_g - avail_g)
                return {
                    "total_gib": round(tot_g, 1),
                    "used_gib": round(used_g, 1),
                    "avail_gib": round(avail_g, 1),
                    "percent": round((used_g / max(0.1, tot_g)) * 100.0, 1),
                }
    except Exception:
        pass
    fallback_tot = float(_detect_system_ram_gib() or 16)
    return {"total_gib": fallback_tot, "used_gib": 0.0, "avail_gib": fallback_tot, "percent": 0.0}


def _sample_gpu_telemetry() -> Dict[str, Any]:
    cf = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu,temperature.gpu,power.draw,power.limit",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            creationflags=cf,
            timeout=1.6,
        ).strip()
        if out:
            best_row = None
            best_vram = -1.0
            for raw_ln in out.splitlines():
                cols = [c.strip() for c in raw_ln.split(",")]
                if len(cols) >= 6:
                    def _pf(s: str) -> float:
                        try:
                            return float(s)
                        except Exception:
                            return 0.0
                    vt = _pf(cols[2])
                    if vt > best_vram:
                        best_vram = vt
                        best_row = cols
            if best_row:
                def _pf2(s: str) -> float:
                    try:
                        return float(s)
                    except Exception:
                        return 0.0
                v_tot = _pf2(best_row[2])
                v_used = _pf2(best_row[3])
                return {
                    "available": True,
                    "vendor": "NVIDIA",
                    "name": best_row[0],
                    "driver": best_row[1],
                    "vram_total_mib": int(round(v_tot)),
                    "vram_used_mib": int(round(v_used)),
                    "vram_total_gib": round(v_tot / 1024.0, 1),
                    "vram_used_gib": round(v_used / 1024.0, 2),
                    "vram_percent": round((v_used / max(1.0, v_tot)) * 100.0, 1),
                    "gpu_util_pct": round(_pf2(best_row[4]), 1),
                    "temp_c": int(round(_pf2(best_row[5]))),
                    "power_w": round(_pf2(best_row[6]), 1) if len(best_row) > 6 else 0.0,
                    "power_limit_w": round(_pf2(best_row[7]), 1) if len(best_row) > 7 else 0.0,
                }
    except Exception:
        pass
    vram_fb = detect_gpu_vram_mib()
    return {
        "available": bool(vram_fb > 0),
        "vendor": "Generic",
        "name": "本机图形处理器" if vram_fb > 0 else "未检测到独立显卡 (CPU / 云端推理)",
        "driver": "",
        "vram_total_mib": int(vram_fb),
        "vram_used_mib": 0,
        "vram_total_gib": round(vram_fb / 1024.0, 1) if vram_fb > 0 else 0.0,
        "vram_used_gib": 0.0,
        "vram_percent": 0.0,
        "gpu_util_pct": 0.0,
        "temp_c": 0,
        "power_w": 0.0,
        "power_limit_w": 0.0,
    }


def _collect_hardware_telemetry_sync() -> Dict[str, Any]:
    cpu_name, cpu_threads = _get_static_cpu_info()
    cpu_pct = _sample_cpu_percent_fast()
    ram = _sample_ram_status()
    gpu = _sample_gpu_telemetry()
    disk_free_gib = 0.0
    disk_total_gib = 0.0
    try:
        du = shutil.disk_usage(str(BASE_DIR))
        disk_total_gib = round(du.total / (1024**3), 1)
        disk_free_gib = round(du.free / (1024**3), 1)
    except Exception:
        pass
    std_dimms = [4, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256, 512]
    ram_nominal_gb = next((d for d in std_dimms if ram["total_gib"] <= d + 0.6 and ram["total_gib"] >= d * 0.86), int(round(ram["total_gib"])))
    return {
        "ok": True,
        "ts": time.time(),
        "system_specs": {
            "os_name": _BENCH_STATIC_CPU_CACHE.get("os_name", ""),
            "board_name": _BENCH_STATIC_CPU_CACHE.get("board_name", ""),
            "cpu_full": cpu_name,
            "cpu_threads": cpu_threads,
            "cpu_mhz": _BENCH_STATIC_CPU_CACHE.get("cpu_mhz", 0),
            "ram_nominal_gb": ram_nominal_gb,
            "ram_total_gib": ram["total_gib"],
            "gpu_full": gpu["name"],
            "gpu_vram_gib": gpu["vram_total_gib"],
            "gpu_vram_mib": gpu["vram_total_mib"],
            "gpu_driver": gpu["driver"],
            "drive_root": _BENCH_STATIC_CPU_CACHE.get("drive_root", ""),
            "disk_models": _BENCH_STATIC_CPU_CACHE.get("disk_models", []),
            "disk_total_gib": disk_total_gib,
            "disk_free_gib": disk_free_gib,
        },
        "cpu": {
            "name": cpu_name,
            "threads": cpu_threads,
            "mhz": _BENCH_STATIC_CPU_CACHE.get("cpu_mhz", 0),
            "load_pct": cpu_pct,
        },
        "ram": ram,
        "gpu": gpu,
        "disk": {
            "total_gib": disk_total_gib,
            "free_gib": disk_free_gib,
            "models": _BENCH_STATIC_CPU_CACHE.get("disk_models", []),
        },
    }


def _run_machine_micro_benchmark_sync() -> Dict[str, Any]:
    """在约 0.30s 内实测本机 DDR 内存复制带宽、CPU 算力与模型盘顺序读取速率"""
    # 1. 真实物理内存块复制带宽 (C-level memcpy over 64 MB * 16 = 1 GiB) + CPU 哈希与浮点综合算力
    copy_blk = 64 * 1024 * 1024
    src_buf = bytearray(b"\x5a\xa5\x3c\xc3" * (copy_blk // 4))
    dst_buf = bytearray(copy_blk)
    copy_iters = 16
    t_mc0 = time.perf_counter()
    for _ in range(copy_iters):
        dst_buf[:] = src_buf
    dt_mc = max(1e-4, time.perf_counter() - t_mc0)
    mem_bw_gbps = round(((copy_blk * copy_iters) / (1024**3)) / dt_mc, 1)

    t_cpu0 = time.perf_counter()
    mv16 = memoryview(src_buf)[: 16 * 1024 * 1024]
    for r in range(6):
        hashlib.blake2b(mv16, digest_size=32, person=bytes([r])).digest()
    acc = 0.0
    for i in range(1, 180_000):
        acc += (i * 0.00013) * (1.0007 / (i + 3.0))
    dt_cpu = max(1e-4, time.perf_counter() - t_cpu0)
    cpu_score = int(round((120.0 / dt_cpu) * 4.2 + (os.cpu_count() or 4) * 55 + min(600.0, mem_bw_gbps * 8.5) + (0 if acc < -1e9 else 0)))

    # 2. 存储盘顺序读取测速（优先直接读取已有大模型/引擎二进制前 48MB，零写入磨损；若无则使用临时探针并立即清理）
    probe_candidates: List[Path] = []
    for search_dir in (BASE_DIR / "models", BASE_DIR / "model", BASE_DIR / "engine", BASE_DIR / "runtime"):
        if search_dir.exists():
            try:
                for p in search_dir.rglob("*"):
                    if p.is_file():
                        sz = p.stat().st_size
                        if sz >= 16 * 1024 * 1024:
                            probe_candidates.append(p)
                            if sz >= 64 * 1024 * 1024:
                                break
                if probe_candidates:
                    break
            except Exception:
                pass

    temp_probe: Optional[Path] = None
    disk_read_mbps = 0.0
    try:
        if probe_candidates:
            target_f = max(probe_candidates, key=lambda x: x.stat().st_size)
            max_read = 64 * 1024 * 1024
        else:
            temp_probe = DATA_DIR / f".bench_io_{uuid.uuid4().hex[:6]}.tmp"
            payload_1m = os.urandom(1024 * 1024)
            with open(temp_probe, "wb") as wf:
                for _ in range(16):
                    wf.write(payload_1m)
                wf.flush()
            target_f = temp_probe
            max_read = 16 * 1024 * 1024

        read_bytes = 0
        t_io0 = time.perf_counter()
        with open(target_f, "rb", buffering=0) as rf:
            while read_bytes < max_read:
                chk = rf.read(1024 * 1024)
                if not chk:
                    break
                read_bytes += len(chk)
        dt_io = max(1e-4, time.perf_counter() - t_io0)
        disk_read_mbps = round((read_bytes / (1024 * 1024)) / dt_io, 1)
    except Exception:
        disk_read_mbps = 0.0
    finally:
        if temp_probe and temp_probe.exists():
            try:
                temp_probe.unlink()
            except Exception:
                pass

    return {
        "cpu_score": cpu_score,
        "mem_bw_gbps": mem_bw_gbps,
        "disk_read_mbps": disk_read_mbps,
    }


def _estimate_mixed_tokens(text: str, sse_chunks: int = 0) -> int:
    if not text:
        return 0
    cjk = len(re.findall(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", text))
    non_cjk_text = re.sub(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", " ", text)
    ascii_words = len(re.findall(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]", non_cjk_text))
    est = max(1, int(round(cjk * 0.68 + ascii_words * 0.85)))
    if sse_chunks >= 8 and 0.55 * est <= sse_chunks <= 1.85 * est:
        return sse_chunks
    return est


@app.get("/api/system/benchmark/telemetry")
async def api_system_benchmark_telemetry():
    return await asyncio.to_thread(_collect_hardware_telemetry_sync)


def _build_trpg_32k_context_text(target_tokens: int = 31500, nonce: str = "") -> str:
    """动态生成指定 Token 规模（默认约 32K）的结构化跑团世界书与多轮战役档案，并在中段埋入大海捞针锚点（卷宗 #17）"""
    target_tokens = max(2048, min(98304, int(target_tokens)))
    # 校准 Qwen/Llama 分词器在含编号符号中文长文上的 ~1.24x 细分倍率，确保 32K 请求精确落在 ~32,000 真实 Token
    calibrated_est_target = max(1600, int(target_tokens * 0.81))
    header = f"【战役全局世界书与历史推演长卷 · 会话标识 {nonce or 'BENCH-32K'}】\n"
    blocks: List[str] = [header]
    cur_est = _estimate_mixed_tokens(header)
    sec_i = 1
    factions = ("灰潮商会", "守夜人卫队", "黑曜石教团", "深海钟表匠行会", "白银审判庭", "铁锈船坞同盟")
    weathers = ("暴雨如注、海雾弥漫", "铅灰浓雾笼罩码头", "冷冽咸腥的朔风呼啸", "霓虹倒映在油污积水间")
    while cur_est < calibrated_est_target:
        fac = factions[sec_i % len(factions)]
        wth = weathers[sec_i % len(weathers)]
        freq = f"{140 + sec_i}.5" if sec_i != 17 else "157.5"
        code_word = f"白鸦-{sec_i}" if sec_i != 17 else "白鸦-17"
        blk = (
            f"【世界书卷宗 #{sec_i:03d} · 雾港第 {sec_i} 扇区勘探与战史记录】"
            f"本扇区现由「{fac}」与地方巡防哨共同接管，常年处于{wth}的异常气候之下。"
            f"核心战术地标包含：旧钟楼第 {sec_i * 3} 号地下排水涵洞、高压蒸汽阀门站 B-{sec_i:02d}、"
            f"黑市物资转运暗仓 C-{sec_i * 2}，以及加密无线电报中继台（工作频段 {freq} MHz）。"
            f"跑团检定规则：当调查员持有特制银壳怀表或报出接头暗号『{code_word}』进入第 {sec_i} 扇区时，"
            f"守卫初始警戒值降低 15 点，潜行与话术检定获得 +10 补正；反之若强行破门，将在 3 回合内触发蒸汽警报并引来重装巡逻小队。"
            f"历史行动纪要（第 {sec_i} 幕）：先遣小队曾在此处与潜伏暗哨交火，遗留了编号 LOG-{1000 + sec_i} 的密封羊皮卷与三枚刻有潮汐纹章的黄铜弹壳。\n"
        )
        blocks.append(blk)
        cur_est += _estimate_mixed_tokens(blk)
        sec_i += 1
    return "".join(blocks)


class BenchmarkStreamRequest(BaseModel):
    model: str = ""
    mode: str = "full"  # "full" (默认32K上下文 + 单次8192吐字 + 60s长时间压测) | "quick"
    duration_s: float = 60.0
    context_k: int = 32
    max_tokens: int = 8192


class ParallelBenchmarkRequest(BaseModel):
    model: str = ""
    parallel: int = 4   # 1..16 可选并发任务数
    context_k: int = 32
    max_tokens: int = 8192
    duration_s: float = 60.0


def _prepare_bench_req_body(
    ep: Dict[str, Any],
    messages: List[Dict[str, str]],
    max_toks: int,
    temp: float,
    ollama_num_ctx: int = 40960,
    force_sustained_decode: bool = False,
) -> Dict[str, Any]:
    req_body: Dict[str, Any] = {
        "model": ep["upstream_model"],
        "messages": messages,
        "temperature": temp,
        "max_tokens": max_toks,
        "stream": True,
    }
    if ep.get("protocol") not in ("claude", "gemini"):
        req_body["stream_options"] = {"include_usage": True}
    if ep["is_local"]:
        if ep["engine"] == "strata":
            req_body["reasoning_effort"] = "none"
            req_body["reasoning_budget_tokens"] = 0
            req_body["chat_template_kwargs"] = {"enable_thinking": False}
            if force_sustained_decode:
                req_body["min_tokens"] = max_toks
        elif ep["engine"] == "llama":
            req_body["reasoning_budget"] = 0
            req_body["chat_template_kwargs"] = {"enable_thinking": False}
            req_body["cache_prompt"] = False
            if force_sustained_decode:
                req_body["ignore_eos"] = True
        elif ep["engine"] == "ollama":
            req_body["think"] = False
            req_body["reasoning_effort"] = "none"
            req_body["thinking_budget_tokens"] = 0
            req_body["reasoning_budget"] = 0
            req_body["reasoning_budget_tokens"] = 0
            req_body["chat_template_kwargs"] = {"enable_thinking": False}
            req_body["options"] = {"num_ctx": max(8192, int(ollama_num_ctx)), "num_predict": max_toks}
        else:
            req_body["think"] = False
            req_body["reasoning_effort"] = "none"
            req_body["chat_template_kwargs"] = {"enable_thinking": False}
    return req_body


@app.post("/api/system/benchmark/stream")
async def api_system_benchmark_stream(req: BenchmarkStreamRequest, request: Request):
    """全维度机器 + 模型实时流式性能基准测试（全面模式默认 32K 上下文 + 单次吐字 8192 + 持续 1 分钟满载压力测试）"""
    username = get_current_user(request)
    settings = load_user_settings(username)
    target_model = (req.model or "").strip() or str(settings.get("model") or "").strip()
    is_full = (req.mode or "full").strip().lower() != "quick"
    burn_duration_s = max(5.0, min(300.0, float(req.duration_s or 60.0)))
    target_ctx_k = max(8, min(96, safe_int(req.context_k, 32)))
    single_max_tokens = max(512, min(16384, safe_int(req.max_tokens, 8192)))

    async def _bench_gen():
        def _pack(obj: Dict[str, Any]) -> bytes:
            return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")

        if not target_model:
            yield _pack({"ok": False, "type": "error", "message": "请先选择一个要测试的模型！"})
            return

        live_hw: Dict[str, Any] = await asyncio.to_thread(_collect_hardware_telemetry_sync)
        stop_hw_flag = False

        async def _bg_hw_poller():
            nonlocal live_hw
            while not stop_hw_flag:
                await asyncio.sleep(0.42)
                if stop_hw_flag:
                    break
                try:
                    live_hw = await asyncio.to_thread(_collect_hardware_telemetry_sync)
                except Exception:
                    pass

        hw_poller_task = asyncio.create_task(_bg_hw_poller())
        try:
            ep = resolve_model_endpoint(target_model, settings)
            allow_api_stress = os.environ.get("TRPG_ALLOW_API_STRESS_TEST") == "1"
            if not ep["is_local"] and is_full and not allow_api_stress:
                yield _pack({
                    "ok": False,
                    "type": "error",
                    "message": "API 模型仅支持快速测试",
                })
                return

            total_st = 5
            # -------- 阶段 1：硬件基准 --------
            yield _pack({
                "ok": True,
                "type": "stage_start",
                "stage": "hardware",
                "stage_index": 1,
                "total_stages": total_st,
                "percent": 3,
                "title": "硬件基准",
                "telemetry": live_hw,
            })
            hw_bench = await asyncio.to_thread(_run_machine_micro_benchmark_sync)
            live_hw = await asyncio.to_thread(_collect_hardware_telemetry_sync)
            yield _pack({
                "ok": True,
                "type": "stage_done",
                "stage": "hardware",
                "percent": 8 if is_full else 12,
                "metrics": hw_bench,
                "telemetry": live_hw,
                "summary": f"CPU {hw_bench['cpu_score']} · 内存 {hw_bench['mem_bw_gbps']} GB/s · 磁盘 {hw_bench['disk_read_mbps']} MB/s",
            })

            # -------- 解析并准备模型引擎 --------
            bench_ollama_ctx = (
                get_optimal_ollama_num_ctx(max(42, target_ctx_k + (single_max_tokens // 1024) + 2), min_ctx=16384)
                if is_full
                else 8192
            )
            engine_ready_ms = 0.0
            if ep["is_local"]:
                eng_q: asyncio.Queue = asyncio.Queue()

                async def _eng_status_cb(msg: str) -> None:
                    await eng_q.put(msg)

                t_eng0 = time.perf_counter()
                eng_task = asyncio.create_task(
                    ensure_local_engine_ready(
                        target_model,
                        status_callback=_eng_status_cb,
                        slot_ctx_tokens=bench_ollama_ctx,
                    )
                )
                last_eng_msg = f"启动引擎 ({ep.get('engine', 'local')})..."
                yield _pack({
                    "ok": True,
                    "type": "status",
                    "percent": 9,
                    "message": last_eng_msg,
                    "telemetry": live_hw,
                })
                while not eng_task.done():
                    try:
                        m_txt = await asyncio.wait_for(eng_q.get(), timeout=0.6)
                        if m_txt:
                            last_eng_msg = m_txt
                    except asyncio.TimeoutError:
                        pass
                    elapsed_s = time.perf_counter() - t_eng0
                    yield _pack({
                        "ok": True,
                        "type": "status",
                        "percent": 10,
                        "message": f"{last_eng_msg} ({elapsed_s:.1f}s)",
                        "telemetry": live_hw,
                    })
                local_err = await eng_task
                ep = resolve_model_endpoint(target_model, settings)
                if local_err:
                    yield _pack({"ok": False, "type": "error", "message": f"引擎启动失败：{local_err}"})
                    return
                if ep.get("engine") == "ollama" and ":11434" in str(ep.get("base_url") or ""):
                    ollama_root = str(ep["base_url"]).rstrip("/")
                    if ollama_root.endswith("/v1"):
                        ollama_root = ollama_root[:-3]
                    up_mid = str(ep.get("upstream_model") or target_model)

                    async def _preload_ollama_vram() -> None:
                        try:
                            async with httpx.AsyncClient(trust_env=False, timeout=180.0) as pc:
                                await pc.post(
                                    f"{ollama_root}/api/generate",
                                    json={
                                        "model": up_mid,
                                        "keep_alive": "15m",
                                        "options": {"num_ctx": bench_ollama_ctx},
                                    },
                                )
                        except Exception:
                            pass

                    pre_task = asyncio.create_task(_preload_ollama_vram())
                    while not pre_task.done():
                        await asyncio.sleep(0.55)
                        elapsed_s = time.perf_counter() - t_eng0
                        yield _pack({
                            "ok": True,
                            "type": "status",
                            "percent": 10,
                            "message": f"加载模型 {up_mid} ({elapsed_s:.1f}s)",
                            "telemetry": live_hw,
                        })
                    await pre_task
                engine_ready_ms = round((time.perf_counter() - t_eng0) * 1000.0, 1)
            elif not ep.get("base_url") or (not ep.get("api_key") and not ep.get("is_local")):
                yield _pack({
                    "ok": False,
                    "type": "error",
                    "message": f"模型「{target_model}」尚未配置有效的 API 地址或密钥，请先在「模型」设置中配置。",
                })
                return

            req_headers = ep.get("headers") or {
                "Authorization": f"Bearer {ep['api_key']}",
                "Content-Type": "application/json",
            }
            proxy_cands = [ep["proxy"], None] if ep.get("proxy") else [None]

            async def _stream_stage_live(
                stage_key: str,
                pct_start: int,
                pct_end: int,
                messages: List[Dict[str, str]],
                max_toks: int,
                result_out: Dict[str, Any],
                temp: float = 0.4,
                ollama_ctx: int = 40960,
                sustained_duration_s: float = 0.0,
                context_builder_fn: Optional[Callable[[int, str], List[Dict[str, str]]]] = None,
                target_ctx_tokens: int = 0,
            ):
                """通用流式测试执行器：支持单次短请求与 60 秒长时间 32K+8192 续航烤机模式"""
                q: asyncio.Queue = asyncio.Queue()

                async def _worker():
                    timeout_cfg = httpx.Timeout(max(180.0, sustained_duration_s + 120.0), connect=20.0)
                    last_error = ""

                    for cur_proxy in proxy_cands:
                        all_pieces: List[str] = []
                        tok_times: List[float] = []
                        early_tps_samples: List[float] = []
                        late_tps_samples: List[float] = []
                        total_est_tokens = 0
                        total_prompt_tokens = 0
                        first_ttft_ms: Optional[float] = None
                        burn_start_ts: Optional[float] = None
                        t_stage0 = time.perf_counter()
                        round_idx = 0
                        eff_ctx_tokens = target_ctx_tokens
                        eff_max_toks = max_toks

                        try:
                            async with httpx.AsyncClient(proxy=cur_proxy, trust_env=False, timeout=timeout_cfg) as client:
                                while True:
                                    round_idx += 1
                                    if context_builder_fn and eff_ctx_tokens > 0:
                                        cur_msgs = context_builder_fn(eff_ctx_tokens, f"R{round_idx}-{uuid.uuid4().hex[:6]}")
                                    else:
                                        cur_msgs = messages

                                    req_body = _prepare_bench_req_body(
                                        ep,
                                        cur_msgs,
                                        eff_max_toks,
                                        temp,
                                        ollama_num_ctx=ollama_ctx,
                                        force_sustained_decode=(sustained_duration_s > 0),
                                    )
                                    t_req0 = time.perf_counter()
                                    round_ttft_ms: Optional[float] = None
                                    round_pieces: List[str] = []
                                    round_sse_cnt = 0
                                    round_usage_comp = 0
                                    round_usage_prompt = 0
                                    last_tick_emit = 0.0
                                    pending_preview = ""
                                    reached_duration = False

                                    async def _consume_resp(resp_obj: httpx.Response):
                                        nonlocal round_ttft_ms, first_ttft_ms, burn_start_ts, round_sse_cnt
                                        nonlocal round_usage_comp, round_usage_prompt, last_tick_emit, pending_preview, reached_duration
                                        ct_hdr = (resp_obj.headers.get("content-type") or "").lower()
                                        if "text/event-stream" not in ct_hdr and "stream" not in ct_hdr:
                                            raw_b = await resp_obj.aread()
                                            cj = json.loads(raw_b.decode("utf-8", errors="ignore"))
                                            if isinstance(cj.get("usage"), dict):
                                                round_usage_comp = int(cj["usage"].get("completion_tokens") or 0)
                                                round_usage_prompt = int(cj["usage"].get("prompt_tokens") or 0)
                                            msg_o = ((cj.get("choices") or [{}])[0].get("message") or {})
                                            piece = str(msg_o.get("content") or "") + str(msg_o.get("reasoning_content") or "")
                                            if piece:
                                                now_t = time.perf_counter()
                                                round_ttft_ms = round((now_t - t_req0) * 1000.0, 1)
                                                if first_ttft_ms is None:
                                                    first_ttft_ms = round_ttft_ms
                                                if burn_start_ts is None:
                                                    burn_start_ts = now_t
                                                round_pieces.append(piece)
                                                all_pieces.append(piece)
                                                tok_times.append(now_t)
                                                round_sse_cnt += 1
                                                est_1 = round_usage_comp or _estimate_mixed_tokens(piece, 1)
                                                tps_1 = round((total_est_tokens + est_1) / max(0.05, now_t - t_stage0), 1)
                                                await q.put({
                                                    "ok": True,
                                                    "type": "token_tick",
                                                    "stage": stage_key,
                                                    "percent": pct_end - 2,
                                                    "ttft_ms": first_ttft_ms,
                                                    "tokens": total_est_tokens + est_1,
                                                    "live_tps": tps_1,
                                                    "avg_tps": tps_1,
                                                    "preview_delta": piece[:600],
                                                    "telemetry": live_hw,
                                                })
                                            return

                                        async for raw_ln in resp_obj.aiter_lines():
                                            now_chk = time.perf_counter()
                                            if sustained_duration_s > 0 and burn_start_ts is not None and (now_chk - burn_start_ts) >= sustained_duration_s:
                                                reached_duration = True
                                                break
                                            ln = raw_ln.strip()
                                            if not ln or not ln.startswith("data:"):
                                                continue
                                            dat = ln[5:].lstrip()
                                            if dat == "[DONE]":
                                                break
                                            try:
                                                cj = json.loads(dat)
                                            except Exception:
                                                continue
                                            if isinstance(cj.get("usage"), dict):
                                                round_usage_comp = int(cj["usage"].get("completion_tokens") or round_usage_comp or 0)
                                                round_usage_prompt = int(cj["usage"].get("prompt_tokens") or round_usage_prompt or 0)
                                            ch_arr = cj.get("choices") or []
                                            dlt = (ch_arr[0].get("delta") or ch_arr[0].get("message") or {}) if ch_arr and isinstance(ch_arr[0], dict) else {}
                                            piece = (dlt.get("content") or "") + (dlt.get("reasoning_content") or dlt.get("reasoning") or "")
                                            if piece:
                                                now_t = time.perf_counter()
                                                if round_ttft_ms is None:
                                                    round_ttft_ms = round((now_t - t_req0) * 1000.0, 1)
                                                if first_ttft_ms is None:
                                                    first_ttft_ms = round_ttft_ms
                                                if burn_start_ts is None:
                                                    burn_start_ts = now_t
                                                round_pieces.append(piece)
                                                all_pieces.append(piece)
                                                tok_times.append(now_t)
                                                round_sse_cnt += 1
                                                pending_preview += piece

                                                if (now_t - last_tick_emit) >= 0.11:
                                                    last_tick_emit = now_t
                                                    r_txt = "".join(round_pieces)
                                                    r_toks = round_usage_comp or _estimate_mixed_tokens(r_txt, round_sse_cnt)
                                                    cum_toks = total_est_tokens + r_toks
                                                    decode_elapsed = max(0.03, now_t - burn_start_ts) if burn_start_ts else max(0.05, now_t - t_req0)
                                                    avg_tps = round(cum_toks / decode_elapsed, 1)
                                                    win_cut = now_t - 0.65
                                                    recent_cnt = sum(1 for ts in tok_times if ts >= win_cut)
                                                    tok_per_ev = r_toks / max(1, round_sse_cnt)
                                                    live_tps = (
                                                        round((recent_cnt * tok_per_ev) / min(0.65, max(0.10, decode_elapsed)), 1)
                                                        if len(tok_times) > 2
                                                        else avg_tps
                                                    )
                                                    if sustained_duration_s > 0:
                                                        prog_ratio = min(0.99, decode_elapsed / sustained_duration_s)
                                                        if prog_ratio <= 0.35:
                                                            early_tps_samples.append(live_tps)
                                                        elif prog_ratio >= 0.65:
                                                            late_tps_samples.append(live_tps)
                                                    else:
                                                        prog_ratio = min(0.95, cum_toks / max(1, eff_max_toks))
                                                    cur_pct = int(round(pct_start + (pct_end - pct_start) * prog_ratio))
                                                    prev_out = pending_preview[-400:] if len(pending_preview) > 400 else pending_preview
                                                    pending_preview = ""
                                                    await q.put({
                                                        "ok": True,
                                                        "type": "token_tick",
                                                        "stage": stage_key,
                                                        "percent": cur_pct,
                                                        "ttft_ms": first_ttft_ms,
                                                        "tokens": cum_toks,
                                                        "round": round_idx,
                                                        "burn_elapsed_s": round(decode_elapsed, 1) if sustained_duration_s > 0 else None,
                                                        "burn_target_s": round(sustained_duration_s, 0) if sustained_duration_s > 0 else None,
                                                        "live_tps": live_tps,
                                                        "avg_tps": avg_tps,
                                                        "preview_delta": prev_out,
                                                        "telemetry": live_hw,
                                                    })
                                                if sustained_duration_s > 0 and burn_start_ts is not None and (now_t - burn_start_ts) >= sustained_duration_s:
                                                    reached_duration = True
                                                    break

                                    # 发送请求（若遇到严格 32768 总窗口上限或 4096 单次输出上限的在线 API，自动自适应重试）
                                    retried_compat = False
                                    while True:
                                        async with client.stream(
                                            "POST",
                                            f"{ep['base_url']}/chat/completions",
                                            headers=req_headers,
                                            json=req_body,
                                        ) as resp:
                                            if resp.status_code != 200:
                                                err_b = await resp.aread()
                                                err_str = err_b.decode("utf-8", errors="ignore")
                                                err_low = err_str.lower()
                                                if resp.status_code in (400, 422) and not retried_compat:
                                                    retried_compat = True
                                                    req_body.pop("stream_options", None)
                                                    if any(k in err_low for k in ("context", "length", "tokens", "max_tokens", "range")):
                                                        if eff_ctx_tokens > 23500 and context_builder_fn:
                                                            eff_ctx_tokens = 23500
                                                            cur_msgs = context_builder_fn(eff_ctx_tokens, f"R{round_idx}-fit32k")
                                                            req_body["messages"] = cur_msgs
                                                        elif eff_max_toks > 4096:
                                                            eff_max_toks = 4096
                                                            req_body["max_tokens"] = eff_max_toks
                                                    continue
                                                last_error = f"HTTP {resp.status_code}: {err_str[:220]}"
                                                break
                                            await _consume_resp(resp)
                                            last_error = ""
                                            break

                                    if last_error:
                                        break

                                    r_full = "".join(round_pieces)
                                    r_final_toks = round_usage_comp or _estimate_mixed_tokens(r_full, round_sse_cnt)
                                    r_prompt_toks = round_usage_prompt or sum(_estimate_mixed_tokens(m.get("content", "")) for m in cur_msgs)
                                    total_est_tokens += r_final_toks
                                    if round_idx == 1:
                                        total_prompt_tokens = r_prompt_toks

                                    if pending_preview:
                                        await q.put({
                                            "ok": True,
                                            "type": "token_tick",
                                            "stage": stage_key,
                                            "percent": pct_end - 1,
                                            "ttft_ms": first_ttft_ms,
                                            "tokens": total_est_tokens,
                                            "preview_delta": pending_preview[-300:],
                                            "telemetry": live_hw,
                                        })
                                        pending_preview = ""

                                    if sustained_duration_s <= 0:
                                        break
                                    now_after = time.perf_counter()
                                    if reached_duration or (burn_start_ts is not None and (now_after - burn_start_ts) >= sustained_duration_s):
                                        break
                                    if (now_after - t_stage0) >= (sustained_duration_s + 25.0):
                                        break
                                    if r_final_toks <= 0:
                                        break

                            if all_pieces and total_est_tokens > 0:
                                t_end = time.perf_counter()
                                full_txt = "".join(all_pieces)
                                total_ms = round((t_end - t_stage0) * 1000.0, 1)
                                eff_ttft_ms = first_ttft_ms if first_ttft_ms is not None else total_ms
                                decode_span_s = (
                                    max(0.02, tok_times[-1] - tok_times[0])
                                    if len(tok_times) >= 3
                                    else max(0.05, (t_end - burn_start_ts) if burn_start_ts else (t_end - t_stage0))
                                )
                                sustained_tps = round((max(1, total_est_tokens - 1) if len(tok_times) >= 3 else total_est_tokens) / decode_span_s, 1)
                                tok_scale = total_est_tokens / max(1, len(tok_times))
                                peak_tps = sustained_tps
                                if len(tok_times) >= 5:
                                    j = 0
                                    for i in range(len(tok_times)):
                                        while tok_times[i] - tok_times[j] > 0.65 and j < i:
                                            j += 1
                                        span_w = tok_times[i] - tok_times[j]
                                        if span_w >= 0.20 and (i - j) >= 2:
                                            cand_tps = round(((i - j) * tok_scale) / span_w, 1)
                                            if cand_tps > peak_tps:
                                                peak_tps = cand_tps
                                intervals_ms = [
                                    (tok_times[k] - tok_times[k - 1]) * 1000.0
                                    for k in range(1, len(tok_times))
                                    if 0.2 < (tok_times[k] - tok_times[k - 1]) * 1000.0 < 3000.0
                                ]
                                if intervals_ms:
                                    intervals_ms.sort()
                                    p95_tpot_ms = round(intervals_ms[min(len(intervals_ms) - 1, int(len(intervals_ms) * 0.95))], 1)
                                else:
                                    p95_tpot_ms = round(1000.0 / max(1.0, sustained_tps), 1)
                                prefill_tps = round(total_prompt_tokens / max(0.01, eff_ttft_ms / 1000.0), 1)
                                stability_pct = 100.0
                                if early_tps_samples and late_tps_samples:
                                    e_avg = sum(early_tps_samples) / len(early_tps_samples)
                                    l_avg = sum(late_tps_samples) / len(late_tps_samples)
                                    if e_avg > 0.5:
                                        stability_pct = round(min(100.0, (l_avg / e_avg) * 100.0), 1)
                                await q.put({
                                    "_final": True,
                                    "ok": True,
                                    "text": full_txt,
                                    "ttft_ms": eff_ttft_ms,
                                    "total_ms": total_ms,
                                    "decode_span_s": round(decode_span_s, 1),
                                    "rounds": round_idx,
                                    "output_tokens": total_est_tokens,
                                    "prompt_tokens": total_prompt_tokens,
                                    "sustained_tps": sustained_tps,
                                    "peak_tps": max(peak_tps, sustained_tps),
                                    "p95_tpot_ms": p95_tpot_ms,
                                    "prefill_tps": prefill_tps,
                                    "stability_pct": stability_pct,
                                })
                                return
                        except asyncio.CancelledError:
                            raise
                        except Exception as ex:
                            last_error = f"{type(ex).__name__}: {ex}"
                            continue

                    await q.put({"_final": True, "ok": False, "error": last_error or "模型未返回任何内容"})

                w_task = asyncio.create_task(_worker())
                try:
                    while True:
                        if await request.is_disconnected():
                            w_task.cancel()
                            result_out.update({"ok": False, "cancelled": True})
                            return
                        try:
                            item = await asyncio.wait_for(q.get(), timeout=0.25)
                        except asyncio.TimeoutError:
                            if w_task.done() and q.empty():
                                break
                            continue
                        if item.get("_final"):
                            result_out.update(item)
                            return
                        yield item
                finally:
                    if not w_task.done():
                        w_task.cancel()
                if "ok" not in result_out:
                    result_out.update({"ok": False, "error": "流式测试意外中断"})

            # -------- 阶段 2：首字延迟 --------
            yield _pack({
                "ok": True,
                "type": "stage_start",
                "stage": "ttft",
                "stage_index": 2,
                "total_stages": total_st,
                "percent": 11,
                "title": "首字延迟",
                "engine_ready_ms": engine_ready_ms,
                "is_local": ep["is_local"],
                "engine": ep.get("engine", "api"),
                "telemetry": live_hw,
            })
            s2_res: Dict[str, Any] = {}
            async for ev in _stream_stage_live(
                "ttft",
                11,
                16,
                [
                    {"role": "system", "content": "你是敏捷的跑团主持，请直接用两句简短生动的中文回应。"},
                    {"role": "user", "content": "推开酒馆沉重的橡木门，迎面吹来一阵裹挟着麦芽酒香的暖风。请用两句话描写酒馆老板抬头看来的瞬间。"},
                ],
                max_toks=64,
                result_out=s2_res,
                temp=0.4,
                ollama_ctx=bench_ollama_ctx,
            ):
                yield _pack(ev)
            if not s2_res.get("ok"):
                if not s2_res.get("cancelled"):
                    yield _pack({"ok": False, "type": "error", "message": f"首字响应测试失败：{s2_res.get('error', '未知错误')}"})
                return
            yield _pack({
                "ok": True,
                "type": "stage_done",
                "stage": "ttft",
                "percent": 16,
                "metrics": {
                    "short_ttft_ms": s2_res["ttft_ms"],
                    "engine_ready_ms": engine_ready_ms,
                    "burst_tps": s2_res["sustained_tps"],
                },
                "telemetry": live_hw,
                "summary": f"{s2_res['ttft_ms']} ms · {s2_res['sustained_tps']} tok/s",
            })

            long_ttft_ms = s2_res["ttft_ms"]
            prefill_tps = s2_res["prefill_tps"]
            needle_hit = True
            protocol_score = 100
            protocol_detail = ""
            s3_res: Dict[str, Any] = {}

            # -------- 阶段 3：持续吐字 --------
            if is_full:
                target_32k_toks = target_ctx_k * 1000
                dur_disp = f"{int(burn_duration_s)}s"
                yield _pack({
                    "ok": True,
                    "type": "stage_start",
                    "stage": "throughput",
                    "stage_index": 3,
                    "total_stages": total_st,
                    "percent": 17,
                    "title": f"持续吐字 ({target_ctx_k}K · {single_max_tokens} · {dur_disp})",
                    "telemetry": live_hw,
                })

                def _build_burn_msgs(ctx_toks: int, nonce_tag: str) -> List[Dict[str, str]]:
                    lore_32k = _build_trpg_32k_context_text(ctx_toks, nonce=f"BURN60S-{nonce_tag}")
                    sys_p = (
                        "你是硬核沉浸式桌面角色扮演游戏主持（DM）。以下为当前战役完整的 32K 世界书与前情历史档案。\n"
                        "请严格基于档案细节，连续撰写一部超长篇、高密度细节的跑团战役实况推演纪实（目标长度 6000~8192 Tokens，按『第一幕』至『第十二幕』逐幕深入展开，包含环境光影、战术动作、NPC 对白、心理博弈与检定细节，严禁提前总结收尾或省略跳段）：\n\n"
                        + lore_32k
                    )
                    usr_p = (
                        "现在暴雨夜警报已经拉响！先遣调查员小队正携带银壳怀表从第 17 扇区高压蒸汽阀门站突围前往旧钟楼地下涵洞。"
                        "请立即开始超长篇逐幕连载推演，尽可能详尽地持续输出完整剧情！"
                    )
                    return [{"role": "system", "content": sys_p}, {"role": "user", "content": usr_p}]

                async for ev in _stream_stage_live(
                    "throughput",
                    17,
                    78,
                    [],
                    max_toks=single_max_tokens,
                    result_out=s3_res,
                    temp=0.68,
                    ollama_ctx=bench_ollama_ctx,
                    sustained_duration_s=burn_duration_s,
                    context_builder_fn=_build_burn_msgs,
                    target_ctx_tokens=target_32k_toks,
                ):
                    yield _pack(ev)
                if not s3_res.get("ok"):
                    if not s3_res.get("cancelled"):
                        yield _pack({"ok": False, "type": "error", "message": f"长时间满载吐字压测失败：{s3_res.get('error', '未知错误')}"})
                    return
                yield _pack({
                    "ok": True,
                    "type": "stage_done",
                    "stage": "throughput",
                    "percent": 78,
                    "metrics": {
                        "sustained_tps": s3_res["sustained_tps"],
                        "peak_tps": s3_res["peak_tps"],
                        "p95_tpot_ms": s3_res["p95_tpot_ms"],
                        "output_tokens": s3_res["output_tokens"],
                        "decode_span_s": s3_res.get("decode_span_s", burn_duration_s),
                        "stability_pct": s3_res.get("stability_pct", 100.0),
                    },
                    "telemetry": live_hw,
                    "summary": (
                        f"{s3_res['sustained_tps']} tok/s · 峰值 {s3_res['peak_tps']} · "
                        f"P95 {s3_res['p95_tpot_ms']}ms · 稳定度 {s3_res.get('stability_pct', 100)}%"
                    ),
                })

                # -------- 阶段 4：长文预填 --------
                yield _pack({
                    "ok": True,
                    "type": "stage_start",
                    "stage": "prefill",
                    "stage_index": 4,
                    "total_stages": total_st,
                    "percent": 79,
                    "title": f"长文预填 ({target_ctx_k}K)",
                    "telemetry": live_hw,
                })

                def _build_prefill_msgs(ctx_toks: int, nonce_tag: str) -> List[Dict[str, str]]:
                    lore_32k = _build_trpg_32k_context_text(ctx_toks, nonce=f"PREFILL-{nonce_tag}")
                    return [
                        {"role": "system", "content": "请根据给定的超长世界书设定准确回答调查员的问题，简明扼要（不超过60字）。\n\n" + lore_32k},
                        {"role": "user", "content": "请查阅上述世界书卷宗 #017 的记载：雾港第 17 扇区的加密无线电报中继台工作频段是多少 MHz？接头暗号是什么？"},
                    ]

                s4_res: Dict[str, Any] = {}
                async for ev in _stream_stage_live(
                    "prefill",
                    79,
                    90,
                    [],
                    max_toks=96,
                    result_out=s4_res,
                    temp=0.2,
                    ollama_ctx=bench_ollama_ctx,
                    context_builder_fn=_build_prefill_msgs,
                    target_ctx_tokens=target_32k_toks,
                ):
                    yield _pack(ev)
                if not s4_res.get("ok"):
                    if not s4_res.get("cancelled"):
                        yield _pack({"ok": False, "type": "error", "message": f"{target_ctx_k}K 长上下文压测失败：{s4_res.get('error', '未知错误')}"})
                    return
                long_ttft_ms = s4_res["ttft_ms"]
                prefill_tps = s4_res["prefill_tps"]
                needle_hit = ("157.5" in s4_res["text"]) and ("白鸦-17" in s4_res["text"] or "白鸦" in s4_res["text"] or "17" in s4_res["text"])
                yield _pack({
                    "ok": True,
                    "type": "stage_done",
                    "stage": "prefill",
                    "percent": 90,
                    "metrics": {
                        "long_ttft_ms": long_ttft_ms,
                        "prefill_tps": prefill_tps,
                        "prompt_tokens": s4_res["prompt_tokens"],
                        "needle_hit": needle_hit,
                    },
                    "telemetry": live_hw,
                    "summary": f"{prefill_tps} tok/s · 首字 {long_ttft_ms}ms · {'命中' if needle_hit else '未中'}",
                })
            else:
                yield _pack({
                    "ok": True,
                    "type": "stage_start",
                    "stage": "throughput",
                    "stage_index": 3,
                    "total_stages": total_st,
                    "percent": 28,
                    "title": "持续吐字",
                    "telemetry": live_hw,
                })
                async for ev in _stream_stage_live(
                    "throughput",
                    28,
                    58,
                    [
                        {"role": "system", "content": "你是硬核沉浸式桌面角色扮演游戏主持（DM）。请直接输出细腻的雨夜潜行与近身危机场景描写，包含光影、雨声、呼吸与动作细节，约 280~360 字。"},
                        {"role": "user", "content": "暴雨冲刷着锈蚀的港口集装箱迷宫，探照灯的光柱每隔四秒扫过头顶铁桥。我贴着冰冷的钢板屏住呼吸，听见拐角处传来两双战术靴踩碎积水的脚步声。请继续推演这一幕。"},
                    ],
                    max_toks=280,
                    result_out=s3_res,
                    temp=0.65,
                    ollama_ctx=bench_ollama_ctx,
                ):
                    yield _pack(ev)
                if not s3_res.get("ok"):
                    if not s3_res.get("cancelled"):
                        yield _pack({"ok": False, "type": "error", "message": f"沉浸叙事持续吐字压测失败：{s3_res.get('error', '未知错误')}"})
                    return
                yield _pack({
                    "ok": True,
                    "type": "stage_done",
                    "stage": "throughput",
                    "percent": 58,
                    "metrics": {
                        "sustained_tps": s3_res["sustained_tps"],
                        "peak_tps": s3_res["peak_tps"],
                        "p95_tpot_ms": s3_res["p95_tpot_ms"],
                        "output_tokens": s3_res["output_tokens"],
                    },
                    "telemetry": live_hw,
                    "summary": f"{s3_res['sustained_tps']} tok/s · 峰值 {s3_res['peak_tps']} · P95 {s3_res['p95_tpot_ms']}ms",
                })

                # -------- 快速测试 阶段 4：~3.2K 长文预填 --------
                yield _pack({
                    "ok": True,
                    "type": "stage_start",
                    "stage": "prefill",
                    "stage_index": 4,
                    "total_stages": total_st,
                    "percent": 60,
                    "title": "长文预填 (~3.2K)",
                    "telemetry": live_hw,
                })
                lore_blocks_q = []
                for sec_i in range(1, 29):
                    lore_blocks_q.append(
                        f"【世界书卷宗 #{sec_i:02d} · 雾港区域档案】第 {sec_i} 扇区由灰潮商会与守夜人卫队共同巡逻，"
                        f"主要地标包含旧钟楼第 {sec_i * 3} 号地下水道、蒸汽阀门站 B-{sec_i} 与加密电报中继台（频段 {140 + sec_i}.5 MHz）。"
                        f"当调查员携带银制怀表或暗号『白鸦-{sec_i}』进入时，守卫警戒度下降 15 点，但黑曜石教团暗哨会在雨夜记录行踪。"
                    )
                long_ctx_q = "\n".join(lore_blocks_q)
                s4_res_q: Dict[str, Any] = {}
                async for ev in _stream_stage_live(
                    "prefill",
                    60,
                    82,
                    [
                        {"role": "system", "content": "请根据给定的长篇世界书设定准确回答调查员的问题，简明扼要（不超过50字）。\n\n" + long_ctx_q},
                        {"role": "user", "content": "根据上述世界书卷宗 #17 的记载，第 17 扇区的加密电报中继台频段是多少 MHz？暗号是什么？"},
                    ],
                    max_toks=64,
                    result_out=s4_res_q,
                    temp=0.2,
                    ollama_ctx=bench_ollama_ctx,
                ):
                    yield _pack(ev)
                if not s4_res_q.get("ok"):
                    if not s4_res_q.get("cancelled"):
                        yield _pack({"ok": False, "type": "error", "message": f"长上下文世界书消化压测失败：{s4_res_q.get('error', '未知错误')}"})
                    return
                long_ttft_ms = s4_res_q["ttft_ms"]
                prefill_tps = s4_res_q["prefill_tps"]
                needle_hit = ("157.5" in s4_res_q["text"]) and ("白鸦-17" in s4_res_q["text"] or "17" in s4_res_q["text"])
                yield _pack({
                    "ok": True,
                    "type": "stage_done",
                    "stage": "prefill",
                    "percent": 82,
                    "metrics": {
                        "long_ttft_ms": long_ttft_ms,
                        "prefill_tps": prefill_tps,
                        "prompt_tokens": s4_res_q["prompt_tokens"],
                        "needle_hit": needle_hit,
                    },
                    "telemetry": live_hw,
                    "summary": f"{prefill_tps} tok/s · 首字 {long_ttft_ms}ms · {'命中' if needle_hit else '未中'}",
                })

            # -------- 阶段 5：协议检定 --------
            yield _pack({
                "ok": True,
                "type": "stage_start",
                "stage": "protocol",
                "stage_index": 5,
                "total_stages": total_st,
                "percent": 91 if is_full else 84,
                "title": "协议检定",
                "telemetry": live_hw,
            })
            s5_res: Dict[str, Any] = {}
            proto_sys = (
                "你是严格的跑团主持人(DM)。请严格按以下顺序输出：\n"
                "1. 剧情正文（约80~120字）：根据 D100 规则（掷骰结果 <= 技能值为成功，> 技能值为失败）推演结果；\n"
                "2. 状态栏：用 <status>生命: xx/100 | 警戒: xx%</status> 包裹；\n"
                "3. 行动选项：必须在全文最后紧跟 3 个编号选项（1. ... 2. ... 3. ...），选项后不得再有任何文字。"
            )
            proto_user = "【系统检定结果：玩家尝试撬开典狱长保险柜，开锁技能 35，本次 D100 掷出 89（89 > 35，检定失败！）】请立即推演这一幕。"
            async for ev in _stream_stage_live(
                "protocol",
                91 if is_full else 84,
                98,
                [
                    {"role": "system", "content": proto_sys},
                    {"role": "user", "content": proto_user},
                ],
                max_toks=240,
                result_out=s5_res,
                temp=0.3,
                ollama_ctx=bench_ollama_ctx,
            ):
                yield _pack(ev)
            if not s5_res.get("ok"):
                if not s5_res.get("cancelled"):
                    yield _pack({"ok": False, "type": "error", "message": f"跑团协议检定失败：{s5_res.get('error', '未知错误')}"})
                return

            p_txt = strip_thinking_blocks(s5_res["text"]).strip()
            score_pts = 0
            checks_passed = []
            fail_keywords = ("失败", "断裂", "卡死", "警报", "刺耳", "声响", "未能", "没能", "滑脱", "崩断", "暴露", "脚步")
            blind_success = ("成功打开", "顺利打开", "咔哒一声开了", "柜门缓缓打开")
            dice_ok = any(k in p_txt for k in fail_keywords) and not any(bs in p_txt for bs in blind_success)
            if dice_ok:
                score_pts += 35
                checks_passed.append("D100失败判定准确")
            if needle_hit:
                score_pts += 15
                checks_passed.append("长文记忆精准")
            m_st = re.search(r"<status>([\s\S]+?)</status>", p_txt, flags=re.I)
            if m_st and len(m_st.group(1).strip()) >= 4:
                score_pts += 25
                checks_passed.append("<status>闭合规范")
            tail_part = p_txt[m_st.end():] if m_st else p_txt
            has_123 = all(re.search(rf"(?:^|\n)\s*{n}[.、）)]\s*\S+", tail_part) for n in (1, 2, 3))
            if has_123:
                score_pts += 25
                checks_passed.append("末尾行动选项完整")

            protocol_score = score_pts
            protocol_detail = " · ".join(checks_passed) if checks_passed else "部分漏项"
            yield _pack({
                "ok": True,
                "type": "stage_done",
                "stage": "protocol",
                "percent": 98,
                "metrics": {
                    "protocol_score": protocol_score,
                    "checks": checks_passed,
                },
                "telemetry": live_hw,
                "summary": f"{protocol_score}/100 ({protocol_detail})",
            })

            # -------- 汇总计算综合评分与建议参数 --------
            live_hw = await asyncio.to_thread(_collect_hardware_telemetry_sync)
            tps_val = s3_res["sustained_tps"]
            short_ttft = s2_res["ttft_ms"]
            stability_pct = s3_res.get("stability_pct", 100.0)

            tps_score = min(100.0, (tps_val / 75.0) * 100.0) if tps_val <= 75 else 100.0
            if tps_val >= 40:
                tps_score = max(tps_score, 85.0 + min(15.0, (tps_val - 40.0) / 4.0))
            elif tps_val >= 20:
                tps_score = 68.0 + ((tps_val - 20.0) / 20.0) * 17.0
            else:
                tps_score = max(15.0, (tps_val / 20.0) * 68.0)

            ttft_score = 100.0 if short_ttft <= 450 else max(25.0, 100.0 - ((short_ttft - 450.0) / 45.0))
            prefill_score = min(100.0, 55.0 + (prefill_tps / 2500.0) * 45.0) if prefill_tps > 0 else 70.0
            hw_score = min(100.0, (hw_bench["cpu_score"] / 2400.0) * 50.0 + (min(32.0, live_hw["gpu"]["vram_total_gib"]) / 24.0) * 50.0)

            overall_score = int(round(
                tps_score * 0.40
                + ttft_score * 0.18
                + prefill_score * 0.17
                + protocol_score * 0.15
                + hw_score * 0.10
            ))
            overall_score = max(10, min(100, overall_score))

            if overall_score >= 92:
                grade, grade_label = "S+", ""
            elif overall_score >= 83:
                grade, grade_label = "S", ""
            elif overall_score >= 72:
                grade, grade_label = "A", ""
            elif overall_score >= 58:
                grade, grade_label = "B", ""
            else:
                grade, grade_label = "C", ""

            tips: List[str] = []
            vram_gib = live_hw["gpu"].get("vram_total_gib") or 0.0
            if ep["is_local"] and hw_bench["disk_read_mbps"] > 0 and hw_bench["disk_read_mbps"] < 350:
                tips.append(f"磁盘读取 {hw_bench['disk_read_mbps']} MB/s 偏慢，建议移至固态硬盘")
            if is_full and stability_pct < 80.0:
                tips.append(f"长压后半程速率降至 {stability_pct}%")

            cur_global = {
                "context_mode": str(settings.get("context_mode") or "tokens"),
                "max_context_k": safe_int(settings.get("max_context_k"), 96),
                "context": safe_int(settings.get("context", settings.get("max_context_turns", 64)), 64),
                "max_tokens": safe_int(settings.get("max_tokens"), 8192),
                "thinking_budget": safe_int(settings.get("thinking_budget"), 1024),
                "keep_recent_messages": safe_int(settings.get("keep_recent_messages"), 6),
                "worldbook_scan_depth": safe_int(settings.get("worldbook_scan_depth"), 5),
                "auto_summarize": bool(settings.get("auto_summarize", True)),
            }

            ram_gib = live_hw["ram"].get("total_gib") or 16.0
            is_fast_model = tps_val >= 38 and (not is_full or prefill_tps >= 900 or not ep["is_local"])
            is_mid_model = tps_val >= 18

            rec_profile_title = ""
            recommended_global: Optional[Dict[str, Any]] = None
            if ep["is_local"]:
                if (vram_gib >= 26 or ram_gib >= 48) and is_fast_model:
                    rec_ctx_mode, rec_ctx_k, rec_turns, rec_keep, rec_wb_depth = "tokens", 96, 96, 10, 6
                    rec_profile_title = "96K"
                elif vram_gib >= 18 or (vram_gib >= 14 and is_mid_model):
                    rec_ctx_mode, rec_ctx_k, rec_turns, rec_keep, rec_wb_depth = "tokens", 64, 48, 8, 5
                    rec_profile_title = "64K"
                elif vram_gib >= 10 or is_mid_model:
                    rec_ctx_mode, rec_ctx_k, rec_turns, rec_keep, rec_wb_depth = "turns", 32, 20, 6, 4
                    rec_profile_title = "32K"
                else:
                    rec_ctx_mode, rec_ctx_k, rec_turns, rec_keep, rec_wb_depth = "turns", 24, 12, 4, 3
                    rec_profile_title = "24K"

                if tps_val >= 50:
                    rec_max_tokens, rec_think = 8192, 1280
                elif tps_val >= 25:
                    rec_max_tokens, rec_think = 8192, 1024
                elif tps_val >= 15:
                    rec_max_tokens, rec_think = 6144, 512
                else:
                    rec_max_tokens, rec_think = 4096, 0

                recommended_global = {
                    "context_mode": rec_ctx_mode,
                    "max_context_k": rec_ctx_k,
                    "context": rec_turns,
                    "max_context_turns": rec_turns,
                    "max_tokens": rec_max_tokens,
                    "thinking_budget": rec_think,
                    "keep_recent_messages": rec_keep,
                    "worldbook_scan_depth": rec_wb_depth,
                    "auto_summarize": True,
                }

            final_report = {
                "model": target_model,
                "is_local": ep["is_local"],
                "engine": ep.get("engine", "api"),
                "mode": "full" if is_full else "quick",
                "context_k": target_ctx_k if is_full else 4,
                "single_max_tokens": single_max_tokens if is_full else 280,
                "burn_duration_s": s3_res.get("decode_span_s", burn_duration_s) if is_full else s3_res.get("decode_span_s", 0),
                "total_output_tokens": s3_res.get("output_tokens", 0),
                "stability_pct": stability_pct,
                "overall_score": overall_score,
                "grade": grade,
                "grade_label": grade_label,
                "short_ttft_ms": short_ttft,
                "long_ttft_ms": long_ttft_ms,
                "engine_ready_ms": engine_ready_ms,
                "sustained_tps": tps_val,
                "peak_tps": s3_res["peak_tps"],
                "p95_tpot_ms": s3_res["p95_tpot_ms"],
                "prefill_tps": prefill_tps,
                "protocol_score": protocol_score,
                "protocol_detail": protocol_detail,
                "cpu_score": hw_bench["cpu_score"],
                "mem_bw_gbps": hw_bench["mem_bw_gbps"],
                "disk_read_mbps": hw_bench["disk_read_mbps"],
                "tips": tips,
                "rec_profile_title": rec_profile_title,
                "current_global_params": cur_global,
                "recommended_global_params": recommended_global,
            }

            yield _pack({
                "ok": True,
                "type": "benchmark_done",
                "percent": 100,
                "report": final_report,
                "telemetry": live_hw,
            })
        except asyncio.CancelledError:
            raise
        except Exception as bench_ex:
            yield _pack({
                "ok": False,
                "type": "error",
                "message": f"性能测试执行异常：{type(bench_ex).__name__}: {bench_ex}",
            })
        finally:
            stop_hw_flag = True
            hw_poller_task.cancel()

    return StreamingResponse(
        _bench_gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "X-Accel-Buffering": "no"},
    )


@app.post("/api/system/benchmark/parallel_stream")
async def api_system_benchmark_parallel_stream(req: ParallelBenchmarkRequest, request: Request):
    """非默认底部高级压测：1~16 路并行长时间满载压力测试（默认 32K 上下文 + 单次吐字 8192 + 持续 60 秒）"""
    username = get_current_user(request)
    settings = load_user_settings(username)
    target_model = (req.model or "").strip() or str(settings.get("model") or "").strip()
    parallel_n = max(1, min(16, safe_int(req.parallel, 4)))
    ctx_k = max(8, min(96, safe_int(req.context_k, 32)))
    max_toks = max(512, min(16384, safe_int(req.max_tokens, 8192)))
    duration_s = max(5.0, min(300.0, float(req.duration_s or 60.0)))

    async def _par_gen():
        def _pack(obj: Dict[str, Any]) -> bytes:
            return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")

        if not target_model:
            yield _pack({"ok": False, "type": "error", "message": "请先在上方选择要压测的模型！"})
            return

        live_hw: Dict[str, Any] = await asyncio.to_thread(_collect_hardware_telemetry_sync)
        stop_hw = False
        peak_vram_gib = float(live_hw.get("gpu", {}).get("vram_used_gib") or 0.0)
        peak_gpu_power_w = float(live_hw.get("gpu", {}).get("power_w") or 0.0)
        peak_gpu_temp_c = int(live_hw.get("gpu", {}).get("temp_c") or 0)

        async def _hw_loop():
            nonlocal live_hw, peak_vram_gib, peak_gpu_power_w, peak_gpu_temp_c
            while not stop_hw:
                await asyncio.sleep(0.45)
                if stop_hw:
                    break
                try:
                    live_hw = await asyncio.to_thread(_collect_hardware_telemetry_sync)
                    g = live_hw.get("gpu") or {}
                    peak_vram_gib = max(peak_vram_gib, float(g.get("vram_used_gib") or 0.0))
                    peak_gpu_power_w = max(peak_gpu_power_w, float(g.get("power_w") or 0.0))
                    peak_gpu_temp_c = max(peak_gpu_temp_c, int(g.get("temp_c") or 0))
                except Exception:
                    pass

        hw_task = asyncio.create_task(_hw_loop())
        lane_tasks: List[asyncio.Task] = []
        try:
            ep = resolve_model_endpoint(target_model, settings)
            if not ep["is_local"] and os.environ.get("TRPG_ALLOW_API_STRESS_TEST") != "1":
                yield _pack({
                    "ok": False,
                    "type": "error",
                    "message": "已暂时禁用在线 API 模型运行并行长时间高压测试（防止消耗大量 Token 额度），API 模型仅支持运行上方「快速测试」！",
                })
                return
            engine_slots_info = f"{parallel_n} 路异步并发流"
            if ep["is_local"]:
                eng_q: asyncio.Queue = asyncio.Queue()

                async def _ecb(msg: str) -> None:
                    await eng_q.put(msg)

                t_e0 = time.perf_counter()
                par_slot_ctx = ctx_k * 1024 + max_toks + 1024
                etask = asyncio.create_task(
                    ensure_local_engine_ready(
                        target_model,
                        status_callback=_ecb,
                        parallel_slots=parallel_n,
                        slot_ctx_tokens=par_slot_ctx,
                    )
                )
                last_m = f"准备引擎 ({parallel_n} 路)..."
                yield _pack({"ok": True, "type": "status", "percent": 4, "message": last_m, "telemetry": live_hw})
                while not etask.done():
                    try:
                        m_s = await asyncio.wait_for(eng_q.get(), timeout=0.6)
                        if m_s:
                            last_m = m_s
                    except asyncio.TimeoutError:
                        pass
                    yield _pack({
                        "ok": True,
                        "type": "status",
                        "percent": 6,
                        "message": f"{last_m} ({time.perf_counter() - t_e0:.1f}s)",
                        "telemetry": live_hw,
                    })
                l_err = await etask
                ep = resolve_model_endpoint(target_model, settings)
                if l_err:
                    yield _pack({"ok": False, "type": "error", "message": f"本地引擎启动失败：{l_err}"})
                    return
                if ep.get("engine") == "strata":
                    try:
                        root_u = ep["base_url"][:-3] if ep["base_url"].endswith("/v1") else ep["base_url"]
                        async with httpx.AsyncClient(trust_env=False, timeout=2.0) as cs:
                            rs = await cs.get(f"{root_u}/v1/status")
                            if rs.status_code == 200:
                                conc = rs.json().get("concurrency") or {}
                                srv_sl = safe_int(conc.get("serving"), 1)
                                engine_slots_info = (
                                    f"Strata 硬件并行槽位 {srv_sl} 个"
                                    + (f"（其余 {parallel_n - srv_sl} 路引擎内排队轮转）" if parallel_n > srv_sl else "（全量同时解码）")
                                )
                    except Exception:
                        engine_slots_info = f"Strata 本地并发 ({parallel_n} 路)"
                else:
                    engine_slots_info = f"{ep.get('engine', 'local')} 连续批处理 ({parallel_n} 路)"
            elif not ep.get("base_url") or (not ep.get("api_key") and not ep.get("is_local")):
                yield _pack({"ok": False, "type": "error", "message": f"模型「{target_model}」尚未配置有效的 API 地址或密钥！"})
                return

            yield _pack({
                "ok": True,
                "type": "parallel_init",
                "parallel": parallel_n,
                "context_k": ctx_k,
                "max_tokens": max_toks,
                "duration_s": duration_s,
                "engine_slots_info": engine_slots_info,
                "telemetry": live_hw,
            })

            req_headers = ep.get("headers") or {
                "Authorization": f"Bearer {ep['api_key']}",
                "Content-Type": "application/json",
            }
            proxy_cands = [ep["proxy"], None] if ep.get("proxy") else [None]
            chosen_proxy = proxy_cands[0]
            # 若配置了本机代理但端口未启动，毫秒级探测自动切回直连，避免 16 路同时撞死端口
            if chosen_proxy and _is_loopback_only_url(chosen_proxy):
                try:
                    up = urlparse(chosen_proxy if "://" in chosen_proxy else f"http://{chosen_proxy}")
                    if up.port:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as psock:
                            psock.settimeout(0.15)
                            if psock.connect_ex((up.hostname or "127.0.0.1", int(up.port))) != 0:
                                chosen_proxy = None
                except Exception:
                    chosen_proxy = None

            base_32k_core = await asyncio.to_thread(_build_trpg_32k_context_text, ctx_k * 1000, "PAR-CORE")
            lanes_state: List[Dict[str, Any]] = [
                {
                    "id": idx + 1,
                    "state": "预填",
                    "rounds": 0,
                    "tokens": 0,
                    "ttft_ms": None,
                    "tok_events": [],
                    "decode_s": 0.0,
                    "tail": "",
                    "errors": 0,
                    "last_err": "",
                }
                for idx in range(parallel_n)
            ]

            t_par0 = time.perf_counter()
            burn_t0: Optional[float] = None
            burn_base_toks: List[int] = [0] * parallel_n
            stop_burn_ev = asyncio.Event()
            limits = httpx.Limits(max_connections=max(36, parallel_n * 2 + 4), max_keepalive_connections=max(20, parallel_n + 2))
            timeout_cfg = httpx.Timeout(max(360.0, duration_s + 240.0), connect=25.0)

            async with httpx.AsyncClient(proxy=chosen_proxy, trust_env=False, limits=limits, timeout=timeout_cfg) as shared_client:

                async def _lane_runner(lane_idx: int):
                    st = lanes_state[lane_idx]
                    lane_no = lane_idx + 1
                    cur_ctx_str = base_32k_core
                    cur_max_toks = max_toks
                    round_no = 0
                    while not stop_burn_ev.is_set() and (burn_t0 is None or (time.perf_counter() - burn_t0) < duration_s):
                        round_no += 1
                        st["rounds"] = round_no
                        st["state"] = "预填"
                        lane_prefix = f"[并行压测通道 #{lane_no:02d} · 轮次 {round_no} · 标识 {uuid.uuid4().hex[:6]}]\n"
                        msgs = [
                            {
                                "role": "system",
                                "content": (
                                    lane_prefix
                                    + "你是沉浸式跑团主持(DM)。请基于以下 32K 世界书档案，持续详尽推演第 "
                                    + str(lane_no)
                                    + " 小队的突围长篇剧情（目标 8192 Tokens，切勿提前结束）：\n\n"
                                    + cur_ctx_str
                                ),
                            },
                            {
                                "role": "user",
                                "content": f"第 {lane_no} 特勤调查小队已抵达雾港第 {(lane_no % 24) + 1} 扇区地下蒸汽管网，请立即开始超长篇连续实况推演！",
                            },
                        ]
                        body = _prepare_bench_req_body(
                            ep,
                            msgs,
                            cur_max_toks,
                            0.68,
                            ollama_num_ctx=max(40960, ctx_k * 1024 + cur_max_toks + 1024),
                            force_sustained_decode=True,
                        )
                        t_r0 = time.perf_counter()
                        r_first_t: Optional[float] = None
                        r_last_t: Optional[float] = None
                        r_pieces: List[str] = []
                        r_sse = 0
                        r_usage_toks = 0
                        base_toks_before = st["tokens"]
                        base_decode_s = st["decode_s"]

                        try:
                            async with shared_client.stream(
                                "POST",
                                f"{ep['base_url']}/chat/completions",
                                headers=req_headers,
                                json=body,
                            ) as resp:
                                if resp.status_code != 200:
                                    eb = (await resp.aread()).decode("utf-8", errors="ignore")
                                    if resp.status_code in (400, 422):
                                        body.pop("stream_options", None)
                                        if any(w in eb.lower() for w in ("context", "length", "tokens", "max_tokens")):
                                            cur_ctx_str = _build_trpg_32k_context_text(23500, f"FIT-{lane_no}")
                                            cur_max_toks = min(cur_max_toks, 4096) if "max_tokens" in eb.lower() else cur_max_toks
                                            continue
                                    st["errors"] += 1
                                    st["last_err"] = f"HTTP {resp.status_code}: {eb[:120]}"
                                    st["state"] = f"异常({resp.status_code})"
                                    await asyncio.sleep(1.0)
                                    continue

                                async for raw_ln in resp.aiter_lines():
                                    if stop_burn_ev.is_set() or (burn_t0 is not None and (time.perf_counter() - burn_t0) >= duration_s):
                                        break
                                    ln = raw_ln.strip()
                                    if not ln or not ln.startswith("data:"):
                                        continue
                                    dat = ln[5:].lstrip()
                                    if dat == "[DONE]":
                                        break
                                    try:
                                        cj = json.loads(dat)
                                    except Exception:
                                        continue
                                    if isinstance(cj.get("usage"), dict):
                                        r_usage_toks = int(cj["usage"].get("completion_tokens") or r_usage_toks or 0)
                                    ch_arr = cj.get("choices") or []
                                    dlt = (ch_arr[0].get("delta") or ch_arr[0].get("message") or {}) if ch_arr and isinstance(ch_arr[0], dict) else {}
                                    piece = (dlt.get("content") or "") + (dlt.get("reasoning_content") or dlt.get("reasoning") or "")
                                    if piece:
                                        now_t = time.perf_counter()
                                        if r_first_t is None:
                                            r_first_t = now_t
                                            if st["ttft_ms"] is None:
                                                st["ttft_ms"] = round((now_t - t_r0) * 1000.0, 1)
                                            st["state"] = "吐字"
                                        r_last_t = now_t
                                        r_pieces.append(piece)
                                        r_sse += 1
                                        cur_r_txt = "".join(r_pieces)
                                        r_est = r_usage_toks or _estimate_mixed_tokens(cur_r_txt, r_sse)
                                        prev_toks = st["tokens"]
                                        new_toks = max(prev_toks, base_toks_before + r_est)
                                        delta_toks = max(1, new_toks - prev_toks)
                                        st["tokens"] = new_toks
                                        st["decode_s"] = base_decode_s + max(0.02, r_last_t - r_first_t)
                                        st["tok_events"].append((now_t, delta_toks))
                                        if len(st["tok_events"]) > 180:
                                            st["tok_events"] = st["tok_events"][-110:]
                        except asyncio.CancelledError:
                            break
                        except Exception as ex:
                            if not stop_burn_ev.is_set():
                                st["errors"] += 1
                                st["last_err"] = f"{type(ex).__name__}: {ex}"
                                st["state"] = "重试"
                                await asyncio.sleep(0.8)

                    if st["tokens"] > 0 and st["errors"] == 0:
                        st["state"] = "完成"

                for i in range(parallel_n):
                    lane_tasks.append(asyncio.create_task(_lane_runner(i)))

                peak_agg_tps = 0.0
                while True:
                    if await request.is_disconnected():
                        stop_burn_ev.set()
                        break
                    await asyncio.sleep(0.22)
                    now_t = time.perf_counter()
                    wall_elapsed = now_t - t_par0
                    ready_lanes = sum(1 for st in lanes_state if st["ttft_ms"] is not None or st["errors"] > 0)
                    if burn_t0 is None and (ready_lanes >= parallel_n or (ready_lanes >= 1 and wall_elapsed >= 120.0)):
                        burn_t0 = now_t
                        burn_base_toks = [st["tokens"] for st in lanes_state]

                    burn_elapsed = (now_t - burn_t0) if burn_t0 is not None else 0.0
                    win_s = 1.0
                    win_cut = now_t - win_s

                    total_toks = 0
                    agg_live_tps = 0.0
                    active_decoding = 0
                    total_errs = 0
                    ttfts: List[float] = []
                    lanes_view: List[Dict[str, Any]] = []

                    for idx_l, st in enumerate(lanes_state):
                        total_toks += st["tokens"]
                        total_errs += st["errors"]
                        if st["ttft_ms"] is not None:
                            ttfts.append(st["ttft_ms"])
                        win_toks = sum(dt for ts, dt in st["tok_events"] if ts >= win_cut)
                        live_lane_tps = round(win_toks / win_s, 1) if win_toks > 0 else 0.0
                        if burn_t0 is not None and burn_elapsed >= 0.4:
                            avg_lane_tps = round(max(0, st["tokens"] - burn_base_toks[idx_l]) / burn_elapsed, 1)
                        else:
                            avg_lane_tps = round(st["tokens"] / max(0.1, wall_elapsed), 1) if st["tokens"] > 0 else 0.0
                        dec_lane_tps = round(st["tokens"] / max(0.05, st["decode_s"]), 1) if st["tokens"] > 0 and st["decode_s"] > 0 else avg_lane_tps
                        if live_lane_tps > 0 or st["state"] == "吐字":
                            active_decoding += 1
                        agg_live_tps += live_lane_tps
                        lanes_view.append({
                            "id": st["id"],
                            "state": st["state"],
                            "rounds": st["rounds"],
                            "tokens": st["tokens"],
                            "tps": live_lane_tps if live_lane_tps > 0 else avg_lane_tps,
                            "avg_tps": avg_lane_tps,
                            "decode_tps": dec_lane_tps,
                            "ttft_ms": st["ttft_ms"],
                        })

                    agg_live_tps = round(agg_live_tps, 1)
                    if burn_t0 is not None:
                        burn_toks_cur = max(0, total_toks - sum(burn_base_toks))
                        agg_avg_tps = round(burn_toks_cur / max(0.15, burn_elapsed), 1) if burn_elapsed >= 0.4 else agg_live_tps
                        if burn_elapsed >= 1.0:
                            peak_agg_tps = max(peak_agg_tps, agg_live_tps, agg_avg_tps)
                        pct = min(99, 20 + int(round((burn_elapsed / duration_s) * 80)))
                    else:
                        agg_avg_tps = agg_live_tps
                        pct = min(20, 8 + int(12 * ready_lanes / max(1, parallel_n)))

                    yield _pack({
                        "ok": True,
                        "type": "parallel_tick",
                        "phase": "burn" if burn_t0 is not None else "prefill",
                        "ready_lanes": ready_lanes,
                        "prefill_elapsed_s": round(wall_elapsed, 1),
                        "percent": pct,
                        "elapsed_s": round(min(duration_s, burn_elapsed), 1),
                        "duration_s": duration_s,
                        "parallel": parallel_n,
                        "active_lanes": active_decoding,
                        "total_tokens": total_toks,
                        "agg_live_tps": agg_live_tps,
                        "agg_avg_tps": agg_avg_tps,
                        "per_lane_tps": round(agg_avg_tps / max(1, parallel_n), 1),
                        "peak_agg_tps": round(peak_agg_tps, 1),
                        "avg_ttft_ms": round(sum(ttfts) / len(ttfts), 1) if ttfts else None,
                        "max_ttft_ms": round(max(ttfts), 1) if ttfts else None,
                        "error_count": total_errs,
                        "peak_vram_gib": round(peak_vram_gib, 2),
                        "lanes": lanes_view,
                        "telemetry": live_hw,
                    })

                    if (burn_t0 is not None and burn_elapsed >= duration_s) or all(t.done() for t in lane_tasks):
                        stop_burn_ev.set()
                        break

                for t in lane_tasks:
                    if not t.done():
                        t.cancel()
                if lane_tasks:
                    await asyncio.gather(*lane_tasks, return_exceptions=True)

            eff_burn_s = (
                max(0.1, min(duration_s + 2.0, time.perf_counter() - burn_t0))
                if burn_t0 is not None
                else max(0.1, min(duration_s + 2.0, time.perf_counter() - t_par0))
            )
            total_toks = sum(st["tokens"] for st in lanes_state)
            burn_toks_final = max(0, total_toks - sum(burn_base_toks)) if burn_t0 is not None else total_toks
            use_burn_window = burn_t0 is not None and burn_toks_final > 0
            total_errs = sum(st["errors"] for st in lanes_state)
            ok_lanes = sum(1 for st in lanes_state if st["tokens"] > 0)
            ttfts_all = sorted(st["ttft_ms"] for st in lanes_state if st["ttft_ms"] is not None)
            if total_toks == 0:
                first_err = next((st["last_err"] for st in lanes_state if st["last_err"]), "所有并发通道均未收到有效输出")
                yield _pack({"ok": False, "type": "error", "message": f"并行测试失败：{first_err}"})
                return

            for st in lanes_state:
                if st["tokens"] > 0:
                    st["state"] = "完成"
            agg_sustained_tps = round((burn_toks_final if use_burn_window else total_toks) / eff_burn_s, 1)
            per_lane_sustained = round(agg_sustained_tps / max(1, parallel_n), 1)
            avg_ttft = round(sum(ttfts_all) / len(ttfts_all), 1) if ttfts_all else 0.0
            p95_ttft = round(ttfts_all[min(len(ttfts_all) - 1, int(len(ttfts_all) * 0.95))], 1) if ttfts_all else 0.0
            max_ttft = round(ttfts_all[-1], 1) if ttfts_all else 0.0

            par_report = {
                "model": target_model,
                "is_local": ep["is_local"],
                "engine": ep.get("engine", "api"),
                "engine_slots_info": engine_slots_info,
                "parallel": parallel_n,
                "success_lanes": ok_lanes,
                "context_k": ctx_k,
                "max_tokens": max_toks,
                "duration_s": round(eff_burn_s, 1),
                "total_tokens": total_toks,
                "aggregate_tps": agg_sustained_tps,
                "per_lane_tps": per_lane_sustained,
                "peak_agg_tps": round(max(peak_agg_tps, agg_sustained_tps), 1),
                "avg_ttft_ms": avg_ttft,
                "p95_ttft_ms": p95_ttft,
                "max_ttft_ms": max_ttft,
                "error_count": total_errs,
                "peak_vram_gib": round(peak_vram_gib, 2),
                "peak_gpu_power_w": round(peak_gpu_power_w, 1),
                "peak_gpu_temp_c": peak_gpu_temp_c,
                "lanes": [
                    {
                        "id": st["id"],
                        "state": st["state"],
                        "rounds": st["rounds"],
                        "tokens": st["tokens"],
                        "tps": round((max(0, st["tokens"] - burn_base_toks[idx_l]) if use_burn_window else st["tokens"]) / eff_burn_s, 1),
                        "decode_tps": round(st["tokens"] / max(0.05, st["decode_s"]), 1) if st["decode_s"] > 0 else round(st["tokens"] / eff_burn_s, 1),
                        "ttft_ms": st["ttft_ms"],
                    }
                    for idx_l, st in enumerate(lanes_state)
                ],
            }
            yield _pack({
                "ok": True,
                "type": "parallel_done",
                "percent": 100,
                "report": par_report,
                "telemetry": live_hw,
            })
        except asyncio.CancelledError:
            raise
        except Exception as par_ex:
            yield _pack({
                "ok": False,
                "type": "error",
                "message": f"并行压测执行异常：{type(par_ex).__name__}: {par_ex}",
            })
        finally:
            stop_hw = True
            hw_task.cancel()
            for t in lane_tasks:
                if not t.done():
                    t.cancel()

    return StreamingResponse(
        _par_gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "X-Accel-Buffering": "no"},
    )


def _set_windows_console_title(title_text: str) -> None:
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW(str(title_text))
        except Exception:
            pass


def _enable_windows_vt100_console() -> Optional[bool]:
    """在传统 Windows cmd.exe (conhost) 中开启 VT100 终端颜色解析，彻底消除  [32mINFO [0m 乱码方框"""
    if os.name != "nt":
        return None
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        ok_any = False
        for std_handle in (-11, -12):  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
            h = kernel32.GetStdHandle(std_handle)
            if h and h != -1:
                mode = ctypes.c_ulong()
                if kernel32.GetConsoleMode(h, ctypes.byref(mode)):
                    if kernel32.SetConsoleMode(h, mode.value | 0x0004):
                        ok_any = True
        return True if ok_any else False
    except Exception:
        return False


def _run_cli_one_click_update(check_only: bool = False, port: int = 8765) -> int:
    """供 一键更新.bat / 一键更新.sh 或 server.py --update 调用的独立命令行更新入口"""
    print("==================================================")
    print(f"  AI 跑团 · 一键更新工具 (当前版本: {APP_VERSION})")
    print("  安全承诺：100% 保留 data/ 存档角色卡与 model/ 本地模型")
    print("==================================================")

    # 若本地服务正在运行（含自动避让至 8766+ 端口的实例）且非仅检查模式，优先通知运行中的本机服务完成热更新与自动重启
    if not check_only:
        probe_ports: List[int] = []
        active_port_file = DATA_DIR / ".active_server_port"
        if "--port" not in sys.argv and active_port_file.exists():
            try:
                sp = int(active_port_file.read_text(encoding="utf-8").strip())
                if 1024 <= sp <= 65535:
                    probe_ports.append(sp)
            except Exception:
                pass
        if port not in probe_ports:
            probe_ports.append(port)
        try:
            with httpx.Client(trust_env=False, timeout=2.0) as local_c:
                r_ver = None
                for cand_p in probe_ports:
                    try:
                        rv = local_c.get(f"http://127.0.0.1:{cand_p}/api/system/version")
                        if rv.status_code == 200 and rv.json().get("ok"):
                            port = cand_p
                            r_ver = rv
                            break
                    except Exception:
                        continue
                if r_ver is None:
                    raise RuntimeError("no running local instance")
                if r_ver.status_code == 200 and r_ver.json().get("ok"):
                    print(f"[检测到 AI 跑团正在端口 {port} 运行，正在通过运行中实例执行热更新与重启...]")
                    r_app = local_c.post(
                        f"http://127.0.0.1:{port}/api/system/update/apply",
                        headers={"Origin": f"http://127.0.0.1:{port}"},
                        json={"allow_proxy": False, "force_reinstall": False},
                        timeout=60.0,
                    )
                    res_j = r_app.json()
                    if res_j.get("need_proxy_confirm"):
                        ans = input(f"\n{res_j.get('message')} [y/N]: ").strip().lower()
                        if ans in ("y", "yes"):
                            r_app = local_c.post(
                                f"http://127.0.0.1:{port}/api/system/update/apply",
                                headers={"Origin": f"http://127.0.0.1:{port}"},
                                json={"allow_proxy": True, "force_reinstall": False},
                                timeout=60.0,
                            )
                            res_j = r_app.json()
                        else:
                            print("[已取消走代理下载]")
                            return 0
                    if res_j.get("already_latest"):
                        print(f"[✓] {res_j.get('message')}")
                        ans_fix = input("是否强制重新下载覆盖修复当前版本代码文件？[y/N]: ").strip().lower()
                        if ans_fix not in ("y", "yes"):
                            return 0
                        r_app = local_c.post(
                            f"http://127.0.0.1:{port}/api/system/update/apply",
                            headers={"Origin": f"http://127.0.0.1:{port}"},
                            json={"allow_proxy": False, "force_reinstall": True},
                            timeout=60.0,
                        )
                        res_j = r_app.json()
                    if r_app.status_code == 200 and res_j.get("ok"):
                        print(f"[✓] 更新完成：{res_j.get('old_version')} -> {res_j.get('new_version')}（更新 {res_j.get('updated_count', 0)} 个文件）")
                        if res_j.get("backup_file"):
                            print(f"    旧版备份：{res_j['backup_file']}")
                        print("    后台服务正在自动重启，刷新浏览器页面即可生效！")
                        return 0
                    print(f"[!] 热更新返回提示：{res_j.get('detail') or res_j.get('message') or res_j}")
                    return 1
        except Exception:
            pass

    async def _cli_async_flow() -> int:
        print("[1/3] 正在直连检查最新版本（优先国内镜像 hf-mirror.com）...")
        allow_proxy = False
        mf = await _fetch_remote_update_manifest(allow_proxy=False)
        if not mf.get("ok") and mf.get("need_proxy_confirm"):
            if check_only:
                print(f"[!] {mf.get('message')}")
                return 1
            ans = input(f"\n{mf.get('message')} [y/N]: ").strip().lower()
            if ans not in ("y", "yes"):
                print("[已取消走代理下载]")
                return 0
            allow_proxy = True
            mf = await _fetch_remote_update_manifest(allow_proxy=True)

        if not mf.get("ok"):
            print(f"[✗] {mf.get('message') or '检查更新失败'}")
            return 1

        remote_ver = _normalize_version_display(str(mf.get("version") or APP_VERSION))
        cmp_res = _compare_versions(remote_ver, APP_VERSION)
        est_mb = round(max(0.1, int(mf.get("size_bytes") or 490_000) / (1024 * 1024)), 2)
        print(f"      当前版本: {APP_VERSION}  |  远端版本: {remote_ver} (来源: {mf.get('source')}, 约 {est_mb} MB)")
        if mf.get("notes"):
            print(f"      更新说明: {mf['notes']}")

        if check_only:
            return 0
        if cmp_res < 0:
            print(f"[✓] 当前本地版本 ({APP_VERSION}) 高于远端公开包 ({remote_ver})，无需更新。")
            return 0
        if cmp_res == 0:
            print(f"[✓] 当前已是最新版本 ({APP_VERSION})。")
            ans_fix = input("是否重新下载代码包覆盖修复当前版本文件？[y/N]: ").strip().lower()
            if ans_fix not in ("y", "yes"):
                return 0

        print(f"[2/3] 正在下载轻量更新包 (~{est_mb} MB)...")
        zip_bytes, dl_err = await _download_update_archive_bytes(
            list(mf.get("download_urls") or []),
            allow_proxy=allow_proxy,
            expected_size_mb=est_mb,
        )
        if zip_bytes is None and dl_err and dl_err.get("need_proxy_confirm"):
            ans = input(f"\n{dl_err.get('message')} [y/N]: ").strip().lower()
            if ans not in ("y", "yes"):
                print("[已取消走代理下载]")
                return 0
            zip_bytes, dl_err = await _download_update_archive_bytes(
                list(mf.get("download_urls") or []),
                allow_proxy=True,
                expected_size_mb=est_mb,
            )
        if zip_bytes is None:
            print(f"[✗] {(dl_err or {}).get('message') or '下载更新包失败'}")
            return 1

        print("[3/3] 正在校验语法、备份旧版并写入更新文件...")
        res = _apply_update_zip_bytes(zip_bytes, str(mf.get("sha256") or ""), remote_ver)
        print(f"[✓] 更新成功！版本：{res['old_version']} -> {res['new_version']}（共更新 {res['updated_count']} 个文件）")
        if res.get("backup_file"):
            print(f"    旧版代码已自动备份至：{res['backup_file']}")
        return 0

    return asyncio.run(_cli_async_flow())


def _is_web_port_bindable(host: str, port: int) -> bool:
    """检测 Web 服务端口是否真正可绑定（同时拦截外部软件监听 10048 与 Windows Hyper-V 系统保留端口段 10013）"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.15)
            if probe.connect_ex(("127.0.0.1", int(port))) == 0:
                return False
    except Exception:
        pass
    bind_hosts = ["127.0.0.1"] if host == "127.0.0.1" else ["127.0.0.1", host]
    for bh in dict.fromkeys(bind_hosts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                else:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((bh, int(port)))
        except OSError:
            return False
    return True


def _pick_available_web_port(host: str, preferred_port: int = 8765) -> int:
    """优先使用 preferred_port (8765)；若撞上 Windows 保留端口段或被其他程序占用，自动顺延至相邻空闲端口"""
    candidates: List[int] = []
    near_ports = list(range(preferred_port + 1, min(65535, preferred_port + 35)))
    for p in [preferred_port] + near_ports + list(range(8766, 8800)) + list(range(18765, 18785)):
        if 1024 <= int(p) <= 65535 and int(p) not in candidates:
            candidates.append(int(p))
    for cand in candidates:
        if _is_web_port_bindable(host, cand):
            return cand
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as ephem:
            ephem.bind(("127.0.0.1", 0))
            return int(ephem.getsockname()[1])
    except Exception:
        return preferred_port


def main():
    port = 8765
    explicit_cli_port = "--port" in sys.argv
    try:
        if explicit_cli_port:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        elif os.environ.get("TRPG_PORT"):
            port = int(os.environ["TRPG_PORT"])
    except (ValueError, IndexError):
        port = 8765

    if "--update" in sys.argv or "--check-update" in sys.argv:
        sys.exit(_run_cli_one_click_update(check_only=("--check-update" in sys.argv), port=port))

    host = "0.0.0.0"
    try:
        if "--host" in sys.argv:
            host = str(sys.argv[sys.argv.index("--host") + 1]).strip() or "0.0.0.0"
        elif os.environ.get("TRPG_HOST"):
            host = str(os.environ["TRPG_HOST"]).strip() or "0.0.0.0"
    except IndexError:
        host = "0.0.0.0"

    no_browser = "--no-browser" in sys.argv
    global SERVER_PORT, _PENDING_BROWSER_OPEN_URL, _WAS_PORT_REPLACED, _UVICORN_SERVER, _PENDING_RESTART_AFTER_UPDATE, _ASGI_DISPATCHER
    was_replaced = _free_port_on_windows(port)
    if not explicit_cli_port and not _is_web_port_bindable(host, port):
        old_p = port
        port = _pick_available_web_port(host, preferred_port=port)
        if port != old_p:
            print(f"  [提示] 默认端口 {old_p} 被 Windows 系统保留（如 Hyper-V/WSL）或其他软件占用，已自动切换至空闲端口 {port}！")
    SERVER_PORT = port
    set_active_web_server_port(port)
    os.environ["TRPG_PORT"] = str(port)
    try:
        (DATA_DIR / ".active_server_port").write_text(str(port), encoding="utf-8")
    except Exception:
        pass
    _WAS_PORT_REPLACED = was_replaced
    _PENDING_BROWSER_OPEN_URL = None if no_browser else f"http://127.0.0.1:{port}"
    vt_colors = _enable_windows_vt100_console()
    _set_windows_console_title(f"AI 跑团 ({APP_VERSION})")
    net_info = get_network_info()

    print("==================================================")
    print(f"  AI TRPG ({APP_VERSION})")
    print(f"  Local  http://127.0.0.1:{port}")
    if host == "0.0.0.0":
        print(f"  LAN    {net_info['lan_url']}")
    else:
        print(f"  Host   http://{host}:{port}")
    print("==================================================")

    dispatcher = _HotSwappableASGI(app)
    _ASGI_DISPATCHER = dispatcher
    cfg = uvicorn.Config(dispatcher, host=host, port=port, reload=False, use_colors=vt_colors)
    srv = uvicorn.Server(cfg)
    _UVICORN_SERVER = srv
    srv.run()

    if _PENDING_RESTART_AFTER_UPDATE:
        print("\n[一键更新] 更新已就绪，正在自动重启服务...")
        if os.environ.get("TRPG_SUPERVISOR") == "1" and not _RESTART_BYPASS_SUPERVISOR:
            sys.exit(42)
        restart_cmd = [sys.executable, "-B", str(BASE_DIR / "server.py"), "--host", host, "--port", str(port), "--no-browser"]
        if os.name != "nt":
            os.execv(sys.executable, restart_cmd)
        else:
            subprocess.Popen(restart_cmd, cwd=str(BASE_DIR))
            sys.exit(0)

if __name__ == "__main__":
    main()

