# -*- coding: utf-8 -*-
"""Backwards-compatibility shim re-exporting symbols moved into backend/*."""
from backend.config import (
    DEFAULT_FAST_TRPG_SYSTEM_PROMPT,
    DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT,
    DEFAULT_UI_MODULES,
    STATUS_SUBMODULE_TYPES,
    WORLDBOOK_TEMPLATE_JSON,
    atomic_write_json,
    build_content_scale_prompt_block,
    build_status_module_prompt,
    build_ui_modules_spec_block,
    get_default_completion_params,
    is_free_chat_project,
    is_simple_trpg_project,
    normalize_project_schema,
    normalize_ui_modules,
    normalize_worldbook_item,
    safe_float,
    safe_int,
    upgrade_legacy_global_protocol_prompt,
)
from backend.content.catalog import EXPLORE_PRESET_APPS
from backend.core.security import is_loopback_only_url as _is_loopback_only_url
from backend.core.security import is_self_workbench_url, open_directory_safely, require_loopback, set_active_web_server_port
from backend.core.variables import interpolate_variables
from backend.core.regex_engine import apply_regex_scripts
from backend.core.worldbook import evaluate_cg_book, evaluate_world_book
from backend.engines.hardware import detect_system_ram_gib as _detect_system_ram_gib
from backend.engines.llama_manager import get_optimal_ctx_tokens as get_optimal_ollama_num_ctx
from backend.engines.supervisor import (
    HF_DOWNLOAD_TASKS,
    HF_PRESET_CATALOG,
    LOCAL_MODELS_CATALOG,
    discover_local_models,
    ensure_local_engine_ready,
    get_installed_local_model_ids,
    shutdown_local_engines,
)
from backend.providers.router import (
    normalize_api_endpoint_and_protocol,
    resolve_model_endpoint,
    sanitize_messages_for_model,
)
from backend.trpg.stream_parser import strip_thinking_blocks
