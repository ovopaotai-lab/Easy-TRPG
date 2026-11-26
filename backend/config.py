# -*- coding: utf-8 -*-
"""Central configuration, constants, atomic file helpers, and schema normalizers."""
from __future__ import annotations

import copy
import json
import logging
import math
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
MODEL_DIR = BASE_DIR / "model"
STATIC_DIR = BASE_DIR / "static"
USERS_DIR = DATA_DIR / "users"
USERS_FILE = DATA_DIR / "users.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"
BACKUP_ROOT_DIR = BASE_DIR / "backups"
ENGINE_LOGS_DIR = DATA_DIR / "engine_logs"
CUSTOM_PATHS_FILE = DATA_DIR / "custom_model_paths.json"
ACTIVE_PORT_FILE = DATA_DIR / ".active_server_port"

for _d in (DATA_DIR, MODELS_DIR, MODEL_DIR, USERS_DIR, BACKUP_ROOT_DIR, ENGINE_LOGS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

APP_VERSION = "alpha 2.0"
SCHEMA_VERSION = 2
CONTENT_SCALE_FEATURE_ENABLED = False

_LOG_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure structured logging once across backend modules."""
    global _LOG_CONFIGURED
    root_logger = logging.getLogger("easy_trpg")
    if not _LOG_CONFIGURED:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
        root_logger.setLevel(level)
        root_logger.propagate = False
        _LOG_CONFIGURED = True
    return root_logger


logger = configure_logging()


def safe_int(value: Any, default: int = 0) -> int:
    """Tolerant integer conversion avoiding crashes on empty strings or NaN."""
    try:
        if value is None or value == "" or isinstance(value, bool):
            return default
        fval = float(value)
        if math.isnan(fval) or math.isinf(fval):
            return default
        return int(fval)
    except (TypeError, ValueError, OverflowError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """Tolerant float conversion avoiding crashes on empty strings or NaN."""
    try:
        if value is None or value == "" or isinstance(value, bool):
            return default
        fval = float(value)
        if math.isnan(fval) or math.isinf(fval):
            return default
        return fval
    except (TypeError, ValueError, OverflowError):
        return default


def _atomic_replace_with_retry(tmp: Path, target: Path) -> None:
    last_err: Optional[Exception] = None
    for attempt in range(10):
        try:
            os.replace(tmp, target)
            return
        except PermissionError as exc:
            last_err = exc
            time.sleep(0.05 * (attempt + 1))
    if last_err:
        raise last_err


def atomic_write_bytes(path: str | Path, content: bytes) -> None:
    """Atomically write bytes via temporary file in the same directory."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        _atomic_replace_with_retry(tmp, p)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError as exc:
                logger.debug("Cleanup temp file failed %s: %s", tmp, exc)


def atomic_write_text(path: str | Path, content: str, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, content.encode(encoding))


def atomic_write_json(
    path: str | Path,
    data: Any,
    indent: Optional[int] = 2,
    ensure_ascii: bool = False,
) -> None:
    text = json.dumps(data, ensure_ascii=ensure_ascii, indent=indent)
    atomic_write_text(path, text, encoding="utf-8")


def get_default_completion_params() -> Dict[str, Any]:
    return {
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
        "max_context_k": 96,
        "keep_recent_messages": 6,
        "worldbook_scan_depth": 5,
        "thinking_budget": 1024,
        "kv_cache_mode": "stable_chunked",
    }


DEFAULT_SETTINGS: Dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
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
    "low_spec_mode": "auto",  # auto | on | off
    "experience_mode": "simple",  # simple | pro
    "onboarding_completed": False,
    "theme": "lamplight-dark",
    "language": "zh-CN",
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
    "kv_cache_mode": "stable_chunked",
    "active_project_id": "proj_fast_trpg",
    "erotic_level": 0,
    "violence_level": 0,
    "erotic_enabled": False,
    "violence_enabled": False,
    "model_params": {},
    "api_profiles": [],
    "favorite_models": [],
    "global_system_protocol_prompt": "",
}


WORLDBOOK_TEMPLATE_JSON = {
    "_comment": {
        "usage": "用于导入世界书配置。保留 world_book 数组结构即可导入。",
        "tips": [
            "match_type: 1=AND, 2=OR, 3=Regex",
            "keys 支持数组 ['词1','词2'] 或字符串",
            "key_region: 1=系统, 2=用户, 4=AI, 6=用户+AI, 7=全部",
            "value_region: 1=系统(建议仅常驻条目), 2=前置词(Tail), 4=后置词(Tail)",
            "constant=true 放于不可变前缀，关键词触发条默认放动态尾部以保护 KV 缓存",
        ],
    },
    "world_book": [],
}

STANDARD_UI_MODULES: List[Dict[str, Any]] = [
    {
        "id": "mod_think",
        "key": "思考推演",
        "type": "thinking_fold",
        "enabled": True,
        "fields": "<think>\n1. 局势因果\n2. NPC 动机\n3. 检定与状态结算\n</think>",
        "desc": "输出正文前在 <think> 内简短推演局势、NPC动机与数值变更，控制在 200~400 字。",
        "v": 2,
    },
    {
        "id": "mod_story",
        "key": "剧情正文",
        "type": "story_narrative",
        "enabled": True,
        "fields": "第二人称（你）电影感沉浸叙事，按场景与对话自然分段",
        "desc": "注重光影、声响、动作与微表情；严禁代替玩家做决定。",
        "v": 2,
    },
    {
        "id": "mod_stats",
        "key": "主角状态",
        "type": "progress_stats",
        "enabled": True,
        "fields": "生命: 100/100\n理智: 80/100\n财富: 随世界观自适应\n状态: 正常",
        "desc": "同步主角生命、理智、货币与状态变化。",
        "v": 2,
    },
    {
        "id": "mod_equip",
        "key": "装备栏",
        "type": "equipment_slots",
        "enabled": True,
        "fields": "主手: 适配武器或工具\n副手: 无\n防具: 适配衣着护具\n饰品: 随身信物",
        "desc": "记录穿戴的主副手、防具与饰品，穿脱或损毁时更新。",
        "v": 2,
    },
    {
        "id": "mod_inv",
        "key": "物品栏",
        "type": "inventory_grid",
        "enabled": True,
        "fields": "应急补给(恢复状态)x2\n照明工具(贴合时代)x1\n关键线索物(来源简述)x1",
        "desc": "格式为「物品名(简述)x数量」，消耗殆尽时标记 x0 后移除。",
        "v": 2,
    },
    {
        "id": "mod_npc",
        "key": "角色关系",
        "type": "npc_affinity",
        "enabled": True,
        "fields": "角色: 关键角色\n好感: 50/100\n态度: 中立审视\n动态: 当前动作",
        "desc": "追踪在场及已结识 NPC 的好感度、态度与动态。",
        "v": 2,
    },
    {
        "id": "mod_info",
        "key": "情报卡",
        "type": "text_card",
        "enabled": True,
        "fields": "当前目标: 查明线索\n环境线索: 可疑痕迹\n潜在危机: 暗中窥视",
        "desc": "更新当前目标、线索与潜在威胁。",
        "v": 2,
    },
    {
        "id": "mod_choices",
        "key": "行动选项",
        "type": "action_choices",
        "enabled": True,
        "fields": "1. 稳健调查或交涉\n2. 高风险博弈行动 【🎲属性检定】\n3. 利用环境或道具破局\n4. 逆向奇招",
        "desc": "文末输出唯一一次「你打算怎么做？」与 1.~4. 差异化选项。",
        "v": 2,
    },
]

DEFAULT_UI_MODULES: List[Dict[str, Any]] = [
    dict(m)
    for m in STANDARD_UI_MODULES
    if m["id"] in ("mod_story", "mod_stats", "mod_equip", "mod_inv", "mod_npc", "mod_choices")
]

STATUS_SUBMODULE_TYPES = {
    "progress_stats",
    "equipment_slots",
    "inventory_grid",
    "npc_affinity",
    "text_card",
    "tags",
    "gear",
    "inventory",
    "relations",
}

DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT = (
    "【系统提示词 · 跑团协议】：\n"
    "1. 【关键节点检定 & 失败推进】：\n"
    "   - 普通对话与日常移动不挂检定；仅在生死搏杀、高危潜行、撬锁拆弹、识破谎言等关键转折点，在对应选项末尾标注 `【🎲属性检定】`。\n"
    "   - 收到系统投骰结果后严格依据结果推演；检定失败不卡死剧情，以代价或新危机继续推进。\n\n"
    "2. 【思考推演 (`<think>...</think>`)】：\n"
    "   - 若开启思考，仅用 200~400 字提纲敲定时间跨度、NPC 独立动作与数值变化后立刻闭合 `</think>`。\n\n"
    "3. 【剧情正文】：\n"
    "   - 直接输出第二人称（「你」）电影感正文，严禁手写 `剧情正文`、`【剧情正文】`、`[剧情正文]` 等伪标题，严禁代替玩家决定。\n\n"
    "4. 【确定性状态增量 (`<state_patch>`) / 兼容状态栏 (`<status>`)】：\n"
    "   - 优先使用超轻量 `<state_patch>{...}</state_patch>` JSON 增量更新数值、装备、背包、NPC关系、任务与进度时钟；"
    "若当前剧本要求完整 `<status>...</status>` 栏位，则按启用栏位依次输出并跨回合继承历史。\n\n"
    "5. 【行动选项】：\n"
    "   - 仅在文末输出唯一一次「你打算怎么做？」及 `1.` ~ `4.` 差异化行动选项，写完第 4 项立即停止。"
)
DEFAULT_STATUS_PANEL_PROMPT = DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT

DEFAULT_FAST_TRPG_SYSTEM_PROMPT = (
    "【世界观与背景设定】\n"
    "（留空则根据你的首句输入或角色卡自动推演。）\n\n"
    "【极速跑团导演规则】\n"
    "1. 第二人称（「你」）沉浸叙事，细致刻画光影、声响、动作与微表情；不抢说玩家台词。\n"
    "2. 主动推进与真实博弈：每回合实质推进至少一个完整事件节点；敌对势力拥有独立动机与果断执行力，失误或暴露即直接实施压制或升级危机。\n"
    "3. 关键检定：仅在生死搏杀、高危潜行、拆弹撬锁、识破谎言等转折点选项末尾标注 `【🎲XX检定】`；失败以代价继续推进。\n"
    "4. 输出结构：\n"
    "   - 正文：直接输出 700~1300 字剧情正文（无标题）；\n"
    "   - 记忆锚点（200 字以内）：\n"
    "     <memory>\n"
    "     [长期记忆]：不可逆重大事件、关键人物关系与秘密、重要随身物\n"
    "     [短期记忆]：当前时间地点、身体与衣着状态、在场人物与即时危机\n"
    "     </memory>\n"
    "   - 最底部输出唯一一次：\n"
    "     你打算怎么做？\n"
    "     1. ……\n"
    "     2. ……\n"
    "     3. ……\n"
    "     4. ……"
)

_STANDARD_MOD_BY_ID = {m["id"]: m for m in STANDARD_UI_MODULES}
_STANDARD_MOD_BY_KEY = {m["key"]: m for m in STANDARD_UI_MODULES}


def upgrade_legacy_global_protocol_prompt(raw_prompt: Optional[str], allow_empty: bool = True) -> str:
    if raw_prompt is None:
        return ""
    cleaned = str(raw_prompt).strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"\s*\{\{UI_MODULES_SPEC\}\}\s*$", "", cleaned)
    cleaned = re.sub(r"\n*6\.\s*【🧩\s*当前模块出场顺序[\s\S]*$", "", cleaned).strip()
    return cleaned


def _fill_default_mod_desc(mod: Dict[str, Any]) -> Dict[str, Any]:
    mc = dict(mod)
    std = _STANDARD_MOD_BY_ID.get(str(mc.get("id") or "")) or _STANDARD_MOD_BY_KEY.get(str(mc.get("key") or ""))
    if std:
        if not str(mc.get("desc") or "").strip():
            mc["desc"] = std["desc"]
        if not str(mc.get("fields") or "").strip():
            mc["fields"] = std["fields"]
        if not str(mc.get("type") or "").strip():
            mc["type"] = std["type"]
    return mc


def normalize_ui_modules(raw_mods: Any) -> List[Dict[str, Any]]:
    if raw_mods is None or not isinstance(raw_mods, list) or len(raw_mods) == 0:
        return []
    result: List[Dict[str, Any]] = []
    singleton_idx: Dict[str, int] = {}
    for m in raw_mods:
        if not isinstance(m, dict):
            continue
        mc = dict(m)
        if not str(mc.get("key") or "").strip() and str(mc.get("name") or "").strip():
            mc["key"] = str(mc.get("name")).strip()
        k_str = str(mc.get("key") or "").strip()
        if not k_str:
            continue
        if not CONTENT_SCALE_FEATURE_ENABLED and (
            str(mc.get("id") or "") == "mod_scale"
            or str(mc.get("type") or "") == "content_scale"
            or k_str == "内容尺度"
        ):
            continue
        filled = _fill_default_mod_desc(mc)
        m_type = str(filled.get("type") or "")
        if m_type in ("thinking_fold", "story_narrative", "action_choices"):
            if m_type in singleton_idx:
                result[singleton_idx[m_type]] = filled
                continue
            singleton_idx[m_type] = len(result)
        result.append(filled)
    return result


def build_ui_modules_spec_block(project_data: Dict[str, Any]) -> str:
    if not isinstance(project_data, dict):
        return ""
    if project_data.get("status_panel_enabled", True) is False:
        return ""
    mods_list = normalize_ui_modules(project_data.get("ui_modules"))
    if not mods_list:
        return ""
    blocks: List[str] = []
    enabled_idx = 0
    for mod in mods_list:
        if not isinstance(mod, dict) or mod.get("enabled", True) is False:
            continue
        m_type = str(mod.get("type") or "progress_stats").strip()
        if m_type == "content_scale" or str(mod.get("id") or "") == "mod_scale":
            continue
        k = str(mod.get("key") or "").strip()
        if not k:
            continue
        enabled_idx += 1
        if m_type == "story_narrative":
            fl, dl = "正文格式", "正文栏提示词"
        elif m_type == "thinking_fold":
            fl, dl = "思考格式", "思考栏提示词"
        elif m_type == "action_choices":
            fl, dl = "选项格式", "选项栏提示词"
        else:
            fl, dl = "格式参考", "功能栏提示词"
        blocks.append(
            f"【#{enabled_idx} {k}】\n"
            f"{fl}：\n{str(mod.get('fields') or '')}\n"
            f"{dl}：\n{str(mod.get('desc') or '')}"
        )
    return "\n\n".join(blocks)


def build_content_scale_prompt_block(erotic_level: int = 0, violence_level: int = 0) -> str:
    return ""


def build_status_module_prompt(project_data: Dict[str, Any], erotic_level: int = 0, violence_level: int = 0) -> str:
    return build_ui_modules_spec_block(project_data)


def segment_ui_mod_fields(raw_fields: str, mod_type: str = "") -> str:
    text = str(raw_fields or "").replace("\r\n", "\n")
    text = re.sub(r"<!--[\s\S]*?-->", "", text).strip()
    if not text or mod_type in ("story_narrative", "content_scale"):
        return text
    text = re.sub(r"(\*[^*\n]+?\*[^*\n]*?)\s+(\*\*[^*\n:：]+[:：]\*\*)", r"\1\n\n\2", text)
    text = re.sub(
        r"(?:(?<=\s)|(?<=[,，;；|｜]))(?:\*\*|\*)+\s*([^*\n:：|｜]{1,14}?)\s*(?:\*\*|\*)?\s*[:：]\s*(?:\*\*|\*)?\s*",
        r"\n\1: ",
        text,
    )
    text = re.sub(
        r"^\s*(?:\*\*|\*)+\s*([^*\n:：|｜]{1,14}?)\s*(?:\*\*|\*)?\s*[:：]\s*(?:\*\*|\*)?\s*",
        r"\1: ",
        text,
        flags=re.MULTILINE,
    )
    if mod_type in ("inventory_grid", "inventory") and "\n" not in text and re.search(r"[,，、]", text):
        items = [p.strip() for p in re.split(r"[,，、]\s*", text) if p.strip()]
        if len(items) > 1:
            text = "\n".join(it if re.search(r"x\d+$", it, re.I) else f"{it}x1" for it in items)
    return text.strip()


def is_free_chat_project(project_data: Dict[str, Any]) -> bool:
    if not isinstance(project_data, dict):
        return False
    if str(project_data.get("id") or "").strip() == "proj_free_chat":
        return True
    return str(project_data.get("category") or "").strip() in ("自由对话", "聊天")


def is_simple_trpg_project(project_data: Dict[str, Any]) -> bool:
    if not isinstance(project_data, dict) or is_free_chat_project(project_data):
        return False
    if bool(project_data.get("simple_mode", False)):
        return True
    if str(project_data.get("card_tier") or "").strip().lower() == "simple":
        return True
    return str(project_data.get("id") or "").strip() == "proj_fast_trpg" or str(
        project_data.get("category") or ""
    ).strip() in ("极速跑团", "简单跑团")


def normalize_worldbook_item(raw_item: Any, idx: int = 0) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_item, dict):
        return None
    item = dict(raw_item)
    raw_mt = item.get("match_type", 2)
    if isinstance(raw_mt, str):
        u = raw_mt.strip().upper()
        match_type = 1 if u in ("1", "AND") else (3 if u in ("3", "REGEX") else 2)
    else:
        match_type = safe_int(raw_mt, 2)

    raw_vr = item.get("value_region", item.get("position", 1))
    if isinstance(raw_vr, str):
        vru = raw_vr.strip().upper()
        if vru.isdigit():
            val_region_int = int(vru) or 1
        elif vru in ("PREFIX", "BEFORE_CHAR", "2"):
            val_region_int = 2
        elif vru in ("SUFFIX", "AFTER_CHAR", "3"):
            val_region_int = 4
        else:
            val_region_int = 1
    else:
        val_region_int = safe_int(raw_vr, 1) or 1

    raw_keys = item.get("keys") if item.get("keys") is not None else item.get("key", [])
    parsed_keys: List[str] = []
    if isinstance(raw_keys, str):
        s = raw_keys.strip()
        if s.startswith("_and_"):
            match_type = 1
            s = s[5:]
        elif s.startswith("_or_"):
            match_type = 2
            s = s[4:]
        parsed_keys = [k.strip() for k in re.split(r"[,，;；@wb@\n]+", s) if k.strip()]
    elif isinstance(raw_keys, list):
        parsed_keys = [str(k).strip() for k in raw_keys if str(k).strip()]

    raw_sec = item.get("secondary_keys") if item.get("secondary_keys") is not None else item.get("keysecondary", [])
    parsed_sec: List[str] = []
    if isinstance(raw_sec, str):
        parsed_sec = [k.strip() for k in re.split(r"[,，;；@wb@\n]+", raw_sec) if k.strip()]
    elif isinstance(raw_sec, list):
        parsed_sec = [str(k).strip() for k in raw_sec if str(k).strip()]

    content_str = str(
        item.get("content") if item.get("content") is not None else (item.get("value") if item.get("value") is not None else "")
    )
    raw_val_configs = item.get("value_configs")
    val_configs: List[Dict[str, Any]] = []
    if isinstance(raw_val_configs, list):
        for vc in raw_val_configs:
            if isinstance(vc, dict):
                prob_val = safe_float(vc.get("probability") if vc.get("probability") is not None else vc.get("weight"), 50.0)
                vc_val = vc.get("value") if vc.get("value") is not None else content_str
                val_configs.append({"value": vc_val, "probability": prob_val, "weight": prob_val})
    if not val_configs:
        val_configs = [{"value": content_str, "probability": 100, "weight": 100}]

    if "enabled" in item:
        is_enabled = bool(item["enabled"])
    elif "enable" in item:
        is_enabled = bool(item["enable"])
    elif "disable" in item:
        is_enabled = not bool(item["disable"])
    else:
        is_enabled = True

    mt_str = "AND" if match_type == 1 else ("Regex" if match_type == 3 else "OR")
    vr_str = "Prefix" if val_region_int == 2 else ("Suffix" if val_region_int == 4 else ("System" if val_region_int == 1 else str(val_region_int)))

    raw_id = item.get("id") if item.get("id") is not None else item.get("uid")
    norm_id = str(raw_id) if (raw_id is not None and str(raw_id).strip() != "") else f"wb_idx_{idx}"
    raw_sort = item.get("sort") if item.get("sort") is not None else (item.get("insertion_order") if item.get("insertion_order") is not None else item.get("order"))
    sort_val = safe_int(raw_sort, (idx + 1) * 10) if raw_sort is not None else (idx + 1) * 10
    raw_scan_depth = item.get("scan_depth") if item.get("scan_depth") is not None else item.get("scanDepth")
    raw_depth = item.get("depth") if item.get("depth") is not None else raw_scan_depth
    depth_val = safe_int(raw_depth, 5) if raw_depth is not None else 5
    prob_val_int = max(0, min(100, safe_int(item.get("probability"), 100)))

    out_item: Dict[str, Any] = {
        "id": norm_id,
        "name": item.get("name") or item.get("comment") or f"词条 #{idx + 1:02d}",
        "group": item.get("group") or "默认分类",
        "enable": is_enabled,
        "enabled": is_enabled,
        "match_type": mt_str if isinstance(raw_mt, str) else match_type,
        "keys": parsed_keys,
        "secondary_keys": parsed_sec,
        "selective": bool(item.get("selective", bool(parsed_sec))),
        "selective_logic": safe_int(item.get("selective_logic", item.get("selectiveLogic", 0)), 0),
        "case_sensitive": bool(item.get("case_sensitive", item.get("caseSensitive", False))),
        "exclude_recursion": bool(item.get("exclude_recursion", item.get("excludeRecursion", False))),
        "key_region": safe_int(item.get("key_region", 6), 6),
        "value_region": vr_str if (isinstance(raw_vr, str) and not raw_vr.strip().isdigit()) else val_region_int,
        "value_type": safe_int(item.get("value_type", 0), 0),
        "value": content_str,
        "content": content_str,
        "value_configs": val_configs,
        "sort": sort_val,
        "depth": depth_val,
        "probability": prob_val_int,
        "constant": bool(item.get("constant", False)),
        "force_system_top": bool(item.get("force_system_top", False)),
    }
    if raw_scan_depth is not None:
        out_item["scan_depth"] = safe_int(raw_scan_depth, depth_val)
    return out_item


def normalize_project_schema(
    payload: Dict[str, Any],
    existing: Optional[Dict[str, Any]] = None,
    global_defaults: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Normalize v1.x & v2.0 project/game-card schemas into canonical v2 structure."""
    existing = dict(existing or {})
    payload = dict(payload or {})
    gd = dict(global_defaults or {})
    now = time.time()

    project_id = str(payload.get("id") or existing.get("id") or f"proj_{uuid.uuid4().hex[:8]}").strip()

    comp_defaults = get_default_completion_params()
    for k in comp_defaults:
        if k in gd and gd[k] is not None:
            comp_defaults[k] = gd[k]
    raw_comp = payload.get("completion_params") if isinstance(payload.get("completion_params"), dict) else (
        existing.get("completion_params") if isinstance(existing.get("completion_params"), dict) else {}
    )
    comp = {**comp_defaults, **raw_comp}
    max_turns = max(1, safe_int(payload.get("max_context_turns", existing.get("max_context_turns", comp.get("context", 96))), 96))
    comp["context"] = max_turns
    comp["max_context_k"] = max(4, safe_int(comp.get("max_context_k"), 96))
    comp["keep_recent_messages"] = max(2, safe_int(comp.get("keep_recent_messages"), 6))
    comp["worldbook_scan_depth"] = max(1, safe_int(comp.get("worldbook_scan_depth"), 5))

    raw_og = payload.get("opening_greetings") if isinstance(payload.get("opening_greetings"), list) else existing.get("opening_greetings", [])
    norm_og: List[Dict[str, Any]] = []
    for idx, g in enumerate(raw_og or []):
        if isinstance(g, dict) and str(g.get("content") or "").strip():
            norm_og.append({
                "id": str(g.get("id") or f"og_{idx+1}"),
                "title": str(g.get("title") or f"开场 #{idx+1}"),
                "content": str(g.get("content") or ""),
                "isSandbox": bool(g.get("isSandbox", False)),
            })
        elif isinstance(g, str) and g.strip():
            norm_og.append({"id": f"og_{idx+1}", "title": f"开场 #{idx+1}", "content": g.strip(), "isSandbox": False})

    raw_wb = payload.get("world_book") if isinstance(payload.get("world_book"), list) else existing.get("world_book", [])
    norm_wb = [w for i, item in enumerate(raw_wb or []) if (w := normalize_worldbook_item(item, i)) is not None]

    wb_groups = payload.get("world_book_groups") or existing.get("world_book_groups") or [
        "默认分类", "核心世界观", "登场人物设定", "地点与势力", "隐藏剧情触发"
    ]

    raw_rx = payload.get("regex_scripts") if isinstance(payload.get("regex_scripts"), list) else (
        payload.get("regex_replaces") if isinstance(payload.get("regex_replaces"), list) else (
            existing.get("regex_scripts") or existing.get("regex_replaces") or []
        )
    )
    regex_list = [dict(r) for r in raw_rx if isinstance(r, dict)]

    raw_pvars = payload.get("prompt_variables") if isinstance(payload.get("prompt_variables"), list) else existing.get("prompt_variables", [])
    norm_pvars = [dict(v) for v in (raw_pvars or []) if isinstance(v, dict) and (v.get("key") or v.get("name"))]

    raw_app = payload.get("appearance") if isinstance(payload.get("appearance"), dict) else (
        existing.get("appearance") if isinstance(existing.get("appearance"), dict) else {}
    )
    custom_css_val = str(
        payload.get("custom_css") if payload.get("custom_css") is not None else (
            raw_app.get("custom_css") if raw_app.get("custom_css") is not None else existing.get("custom_css", "")
        )
    )
    tts_cfg = payload.get("tts_config") or raw_app.get("tts_config") or existing.get("tts_config") or {
        "enabled": False,
        "voice_preset": "",
        "rate": 1.0,
        "pitch": 1.0,
    }
    app_cfg = {
        "bg_image": raw_app.get("bg_image", ""),
        "bg_mobile": raw_app.get("bg_mobile", ""),
        "enable_custom_opacity": bool(raw_app.get("enable_custom_opacity", False)),
        "chat_bubble_opacity": safe_float(raw_app.get("chat_bubble_opacity"), 0.92),
        "no_image_mode": bool(raw_app.get("no_image_mode", False)),
        "theme": raw_app.get("theme") or raw_app.get("theme_mode") or "dark",
        "custom_css": custom_css_val,
        "tts_config": tts_cfg,
    }

    category = str(payload.get("category", existing.get("category", "跑团")) or "跑团").strip()
    is_free = project_id == "proj_free_chat" or category in ("自由对话", "聊天")
    resolved_simple_mode = bool(
        payload["simple_mode"]
        if ("simple_mode" in payload and payload["simple_mode"] is not None)
        else (
            existing["simple_mode"]
            if ("simple_mode" in existing and existing["simple_mode"] is not None)
            else (project_id == "proj_fast_trpg" or category in ("极速跑团", "简单跑团"))
        )
    ) and not is_free

    ui_mods_raw = payload.get("ui_modules") if isinstance(payload.get("ui_modules"), list) else existing.get("ui_modules")
    norm_mods = [] if (resolved_simple_mode or is_free) else normalize_ui_modules(ui_mods_raw)

    ruleset = str(payload.get("ruleset", existing.get("ruleset", "d20")) or "d20").strip().lower()
    if ruleset not in ("d20", "d100", "2d6", "narrative"):
        ruleset = "d20"

    initial_state = payload.get("initial_state") if isinstance(payload.get("initial_state"), dict) else (
        existing.get("initial_state") if isinstance(existing.get("initial_state"), dict) else {}
    )
    bundled_cards = payload.get("bundled_cards") if isinstance(payload.get("bundled_cards"), list) else (
        existing.get("bundled_cards") if isinstance(existing.get("bundled_cards"), list) else []
    )
    group_defaults = payload.get("group_defaults") if isinstance(payload.get("group_defaults"), dict) else (
        existing.get("group_defaults") if isinstance(existing.get("group_defaults"), dict) else {}
    )

    icon_val = str(payload.get("icon") or payload.get("avatar") or existing.get("icon") or existing.get("avatar") or "")

    return {
        "schema_version": SCHEMA_VERSION,
        "id": project_id,
        "name": str(payload.get("name", existing.get("name", "未命名剧本")) or "未命名剧本"),
        "icon": icon_val,
        "avatar": icon_val,
        "description": str(payload.get("description", existing.get("description", "")) or ""),
        "detailed_description": str(payload.get("detailed_description", existing.get("detailed_description", "")) or ""),
        "custom_css": custom_css_val,
        "quick_replies": list(payload.get("quick_replies") or existing.get("quick_replies") or []),
        "author": str(payload.get("author", existing.get("author", "Easy-TRPG")) or "Easy-TRPG"),
        "category": category,
        "card_tier": "simple" if resolved_simple_mode else str(payload.get("card_tier", existing.get("card_tier", "advanced")) or "advanced"),
        "tags": [str(t).strip() for t in (payload.get("tags") or existing.get("tags") or []) if str(t).strip()],
        "ruleset": ruleset,
        "initial_state": initial_state,
        "bundled_cards": bundled_cards,
        "group_defaults": group_defaults,
        "system_prompt": str(payload.get("system_prompt", existing.get("system_prompt", "")) or ""),
        "system_protocol_prompt": upgrade_legacy_global_protocol_prompt(
            payload.get("system_protocol_prompt", existing.get("system_protocol_prompt", ""))
        ),
        "prefix": str(payload.get("prefix", existing.get("prefix", "")) or ""),
        "suffix": str(payload.get("suffix", existing.get("suffix", "")) or ""),
        "opening_greetings": norm_og,
        "opening_statement": str(payload.get("opening_statement", existing.get("opening_statement", "")) or ""),
        "suggested_questions": list(payload.get("suggested_questions", existing.get("suggested_questions", [])) or []),
        "prompt_variables": norm_pvars,
        "simple_mode": resolved_simple_mode,
        "cot_enabled": bool(
            payload["cot_enabled"]
            if ("cot_enabled" in payload and payload["cot_enabled"] is not None)
            else existing.get("cot_enabled", not resolved_simple_mode)
        ),
        "status_panel_enabled": False if (resolved_simple_mode or is_free) else bool(
            payload.get("status_panel_enabled", existing.get("status_panel_enabled", bool(norm_mods)))
        ),
        "status_panel_template": "" if resolved_simple_mode else str(payload.get("status_panel_template", existing.get("status_panel_template", "")) or ""),
        "ui_modules": norm_mods,
        "world_book": norm_wb,
        "world_book_groups": list(wb_groups),
        "regex_scripts": list(regex_list),
        "regex_replaces": list(regex_list),
        "cg_book": list(payload.get("cg_book", existing.get("cg_book", [])) or []),
        "guided_meta": dict(payload.get("guided_meta") or existing.get("guided_meta") or {}),
        "memory_palace": list(payload.get("memory_palace", existing.get("memory_palace", [])) or []),
        "memory_type": str(payload.get("memory_type", existing.get("memory_type", "auto_summary")) or "auto_summary"),
        "max_context_turns": max_turns,
        "erotic_enabled": bool(payload.get("erotic_enabled", existing.get("erotic_enabled", gd.get("erotic_enabled", False)))),
        "violence_enabled": bool(payload.get("violence_enabled", existing.get("violence_enabled", gd.get("violence_enabled", False)))),
        "erotic_level": max(0, min(5, safe_int(payload.get("erotic_level", existing.get("erotic_level", gd.get("erotic_level", 0))), 0))),
        "violence_level": max(0, min(5, safe_int(payload.get("violence_level", existing.get("violence_level", gd.get("violence_level", 0))), 0))),
        "auto_summarize": bool(payload.get("auto_summarize", existing.get("auto_summarize", gd.get("auto_summarize", True)))),
        "use_global_params": bool(payload.get("use_global_params", existing.get("use_global_params", True))),
        "completion_params": comp,
        "appearance": app_cfg,
        "tts_config": tts_cfg,
        "created_at": existing.get("created_at", now),
        "updated_at": now,
    }


def sanitize_settings_numbers(target: Dict[str, Any]) -> Dict[str, Any]:
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


def normalize_settings(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = copy.deepcopy(DEFAULT_SETTINGS)
    if isinstance(raw, dict):
        merged.update(raw)
    merged["schema_version"] = SCHEMA_VERSION
    return sanitize_settings_numbers(merged)
