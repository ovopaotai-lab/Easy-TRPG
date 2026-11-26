# -*- coding: utf-8 -*-
"""Safe self-updater for Easy-TRPG v2 (direct download, whitelist staging, rollback backup)."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import re
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import quote

import httpx

from backend.config import APP_VERSION, BACKUP_ROOT_DIR, BASE_DIR, atomic_write_bytes

UPDATE_HF_REPO = "dongfangshuo/Easy-TRPG"
UPDATE_GH_REPO = "ovopaotai-lab/Easy-TRPG"

_ALLOWED_ROOT_FILES = {
    "server.py",
    "enterprise_engine.py",
    "version.json",
    "requirements.txt",
    "README.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    ".gitignore",
}
_EXCLUDED_DEV_ROOT_FILES = {
    "同步升级到我的工作台.bat",
    "重置纯净母本出厂数据.bat",
    "一键打包纯净发布版.bat",
}
_REQUIRED_CORE_FILES = ("server.py", "backend/app.py", "static/index.html")


def normalize_version_display(ver: str) -> str:
    return re.sub(r"\s+", " ", str(ver or "").strip())


def parse_version_tuple(ver: str) -> Tuple[int, Tuple[int, int, int, int], int]:
    s = normalize_version_display(ver).lower()
    stage_map = {"dev": 0, "pre": 0, "alpha": 1, "a": 1, "beta": 2, "b": 2, "rc": 3}
    stage = 4
    m_stage = re.match(r"^(dev|pre|alpha|beta|rc|a|b)\b", s)
    if not m_stage:
        m_stage = re.match(r"^(dev|pre|alpha|beta|rc|a|b)(?=\d)", s)
    if m_stage:
        stage = stage_map.get(m_stage.group(1), 4)
        s = s[m_stage.end():].strip()
    m_nums = re.search(r"(\d+(?:\.\d+)*)", s)
    if m_nums:
        nums = [int(x) for x in m_nums.group(1).split(".")[:4]]
        tail = s[m_nums.end():]
    else:
        nums = []
        tail = s
    while len(nums) < 4:
        nums.append(0)
    rev = 0
    m_rev = re.search(r"(?:r|rev|patch|hotfix|p)[_\-\s]*(\d+)", tail)
    if m_rev:
        rev = int(m_rev.group(1))
    return (stage, (nums[0], nums[1], nums[2], nums[3]), rev)


def compare_versions(v1: str, v2: str) -> int:
    t1 = parse_version_tuple(v1)
    t2 = parse_version_tuple(v2)
    if t1 > t2:
        return 1
    if t1 < t2:
        return -1
    return 0


def get_local_version() -> str:
    vj = BASE_DIR / "version.json"
    if vj.is_file():
        try:
            ver = normalize_version_display(str(json.loads(vj.read_text(encoding="utf-8")).get("version") or ""))
            if ver:
                return ver
        except Exception:
            pass
    return normalize_version_display(APP_VERSION)


def _is_allowed_update_rel(rel: str) -> bool:
    clean = rel.replace("\\", "/").lstrip("/")
    while clean.startswith("./"):
        clean = clean[2:]
    if not clean or "\x00" in clean or ":" in clean:
        return False
    parts = [p for p in clean.split("/") if p]
    if not parts or any(p in (".", "..") for p in parts):
        return False
    norm = "/".join(parts)
    if len(parts) == 1:
        if norm in _ALLOWED_ROOT_FILES:
            return True
        return norm.lower().endswith((".bat", ".sh")) and norm not in _EXCLUDED_DEV_ROOT_FILES
    top = parts[0]
    if top == "backend":
        if "__pycache__" in parts:
            return False
        return not norm.lower().endswith((".pyc", ".pyo", ".tmp", ".bak"))
    if top == "static":
        return not norm.lower().endswith((".tmp", ".bak"))
    return False


def _normalize_script_bytes(rel: str, raw: bytes) -> bytes:
    low = rel.lower()
    if low.endswith(".bat"):
        txt = raw.decode("utf-8", errors="surrogateescape").replace("\r\n", "\n").replace("\r", "\n")
        return txt.replace("\n", "\r\n").encode("utf-8", errors="surrogateescape")
    if low.endswith(".sh"):
        txt = raw.decode("utf-8", errors="surrogateescape").replace("\r\n", "\n").replace("\r", "\n")
        return txt.encode("utf-8", errors="surrogateescape")
    return raw


async def check_for_update() -> Dict[str, Any]:
    cur_ver = get_local_version()
    probes = [
        ("hf-mirror.com", f"https://hf-mirror.com/{UPDATE_HF_REPO}/raw/main/version.json"),
        ("huggingface.co", f"https://huggingface.co/{UPDATE_HF_REPO}/raw/main/version.json"),
        ("github.com", f"https://raw.githubusercontent.com/{UPDATE_GH_REPO}/main/version.json"),
    ]
    last_err = ""
    async with httpx.AsyncClient(trust_env=False, follow_redirects=True, timeout=6.0) as client:
        for source_name, url in probes:
            try:
                resp = await client.get(url, headers={"User-Agent": "Easy-TRPG-Updater/2.0"})
                if resp.status_code != 200:
                    last_err = f"{source_name} HTTP {resp.status_code}"
                    continue
                m = resp.json()
                if not isinstance(m, dict) or not m.get("version"):
                    last_err = f"{source_name} invalid manifest"
                    continue
                remote_ver = normalize_version_display(str(m.get("version") or ""))
                slug = re.sub(r"\s+", "", remote_ver)
                pkg = str(m.get("package") or f"AI跑团工作台_API纯净版_{slug}.zip").strip()
                enc_pkg = quote(pkg, safe="/._-")
                dl_urls = [
                    f"https://hf-mirror.com/{UPDATE_HF_REPO}/resolve/main/{enc_pkg}",
                    f"https://huggingface.co/{UPDATE_HF_REPO}/resolve/main/{enc_pkg}",
                    f"https://codeload.github.com/{UPDATE_GH_REPO}/zip/refs/heads/main",
                ]
                return {
                    "ok": True,
                    "current_version": cur_ver,
                    "latest_version": remote_ver,
                    "remote_version": remote_ver,
                    "has_update": compare_versions(remote_ver, cur_ver) > 0,
                    "package": pkg,
                    "size": int(m.get("size") or 0),
                    "sha256": str(m.get("sha256") or "").strip().lower(),
                    "notes": str(m.get("notes") or "").strip(),
                    "download_urls": dl_urls,
                    "source": source_name,
                }
            except Exception as exc:
                last_err = f"{source_name}: {exc}"
    return {
        "ok": False,
        "current_version": cur_ver,
        "latest_version": cur_ver,
        "has_update": False,
        "message": f"检查失败: {last_err or '网络不可用'}",
    }


def apply_update_zip_bytes(
    zip_bytes: bytes,
    expected_sha256: str = "",
    target_version: str = "",
) -> Dict[str, Any]:
    """Validate zip archive integrity + Python syntax, backup old files, and apply atomically."""
    if not zip_bytes or len(zip_bytes) < 512:
        raise ValueError("更新包数据为空或已损坏")
    if expected_sha256:
        actual_sha = hashlib.sha256(zip_bytes).hexdigest().lower()
        if actual_sha != expected_sha256.lower():
            raise ValueError(
                f"更新包 SHA256 校验不匹配（期望 {expected_sha256[:12]}...，实际 {actual_sha[:12]}...）"
            )

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

        first_segs = {n.split("/", 1)[0] for n, _ in raw_entries if "/" in n}
        all_under_single_root = len(first_segs) == 1 and all("/" in n for n, _ in raw_entries)
        strip_prefix = (next(iter(first_segs)) + "/") if all_under_single_root else ""

        staged_files: Dict[str, bytes] = {}
        for norm_name, zi in raw_entries:
            rel = norm_name[len(strip_prefix):] if (strip_prefix and norm_name.startswith(strip_prefix)) else norm_name
            if not _is_allowed_update_rel(rel):
                continue
            staged_files[rel] = _normalize_script_bytes(rel, zf.read(zi))

    missing_core = [rk for rk in _REQUIRED_CORE_FILES if rk not in staged_files]
    if missing_core:
        raise ValueError(f"更新包结构不完整，缺少核心文件：{', '.join(missing_core)}")

    for rel, raw_b in staged_files.items():
        if rel.endswith(".py"):
            compile(raw_b.decode("utf-8"), rel, "exec")

    base_resolved = BASE_DIR.resolve()
    changed_rels: List[str] = []
    for rel, new_b in staged_files.items():
        dst = (BASE_DIR / rel).resolve()
        if not dst.is_relative_to(base_resolved) or dst == base_resolved:
            raise ValueError(f"非法更新路径：{rel}")
        if dst.is_file():
            try:
                if dst.read_bytes() == new_b:
                    continue
            except OSError:
                pass
        changed_rels.append(rel)

    tracked_static = {r for r in staged_files if r.startswith("static/")}
    pruned_files: List[str] = []
    static_assets_dir = BASE_DIR / "static" / "assets"
    if static_assets_dir.is_dir():
        for old_f in sorted(static_assets_dir.rglob("*")):
            if old_f.is_file():
                rel_old = old_f.relative_to(BASE_DIR).as_posix()
                if rel_old not in tracked_static:
                    pruned_files.append(rel_old)

    backup_rel = ""
    if changed_rels or pruned_files:
        BACKUP_ROOT_DIR.mkdir(parents=True, exist_ok=True)
        bak_path = BACKUP_ROOT_DIR / f"pre_update_{time.strftime('%Y%m%d_%H%M%S')}.zip"
        with zipfile.ZipFile(bak_path, "w", compression=zipfile.ZIP_DEFLATED) as bf:
            for rel in sorted(set(changed_rels) | set(pruned_files)):
                old_p = BASE_DIR / rel
                if old_p.is_file():
                    bf.write(old_p, arcname=rel)
        backup_rel = bak_path.relative_to(BASE_DIR).as_posix()

        for rel in changed_rels:
            atomic_write_bytes(BASE_DIR / rel, staged_files[rel])
        for rel in pruned_files:
            old_p = BASE_DIR / rel
            if old_p.is_file():
                old_p.unlink()

    resolved_ver = normalize_version_display(target_version)
    if not resolved_ver and "version.json" in staged_files:
        try:
            resolved_ver = normalize_version_display(
                str(json.loads(staged_files["version.json"].decode("utf-8")).get("version") or "")
            )
        except Exception:
            pass
    if not resolved_ver:
        resolved_ver = get_local_version()

    return {
        "updated": bool(changed_rels or pruned_files),
        "version": resolved_ver,
        "changed_count": len(changed_rels),
        "changed_files": changed_rels,
        "pruned_files": pruned_files,
        "backup_path": backup_rel,
    }


async def download_and_apply_update() -> Dict[str, Any]:
    info = await check_for_update()
    if not info.get("ok"):
        return info
    if not info.get("has_update"):
        return {
            "ok": True,
            "updated": False,
            "has_update": False,
            "version": info["current_version"],
            "latest_version": info["latest_version"],
            "message": f"当前已是最新版本 ({info['current_version']})",
        }

    expected_sha = str(info.get("sha256") or "")
    target_ver = str(info.get("latest_version") or "")
    last_err = ""
    async with httpx.AsyncClient(trust_env=False, follow_redirects=True, timeout=60.0) as client:
        for url in info.get("download_urls") or []:
            try:
                resp = await client.get(url, headers={"User-Agent": "Easy-TRPG-Updater/2.0"})
                if resp.status_code != 200:
                    last_err = f"{url} -> HTTP {resp.status_code}"
                    continue
                is_gh_branch_zip = "codeload.github.com" in url
                res = apply_update_zip_bytes(
                    resp.content,
                    expected_sha256="" if is_gh_branch_zip else expected_sha,
                    target_version=target_ver,
                )
                return {
                    "ok": True,
                    "has_update": True,
                    "source": url,
                    **res,
                }
            except Exception as exc:
                last_err = f"{url}: {exc}"
    return {"ok": False, "message": f"更新包下载或校验失败: {last_err or '未知错误'}"}


def run_cli_update(check_only: bool = False) -> int:
    cur_ver = get_local_version()
    print("==================================================")
    print(f"  Easy-TRPG 一键更新 (当前版本: {cur_ver})")
    print("  100% 保留 data/ 存档、角色卡与 models/ 本地模型")
    print("==================================================")
    info = asyncio.run(check_for_update())
    if not info.get("ok"):
        print(f"  [失败] {info.get('message', '检查更新失败')}")
        return 1

    latest = info.get("latest_version", cur_ver)
    if not info.get("has_update"):
        print(f"  [已是最新] 当前版本 {cur_ver} (远端: {latest})")
        return 0

    print(f"  [发现新版本] {latest} (来源: {info.get('source')})")
    if info.get("notes"):
        print(f"  更新内容:\n{info['notes']}")
    if check_only:
        return 0

    print("  正在下载并校验更新包...")
    res = asyncio.run(download_and_apply_update())
    if not res.get("ok"):
        print(f"  [失败] {res.get('message', '更新失败')}")
        return 1

    if res.get("updated"):
        print(
            f"  [更新完成] 已升级至 {res.get('version')} "
            f"(更新 {res.get('changed_count', 0)} 个文件, 清理 {len(res.get('pruned_files') or [])} 个旧资源)"
        )
        if res.get("backup_path"):
            print(f"  旧文件备份: {res['backup_path']}")
    else:
        print(f"  [完成] {res.get('message', '无需替换文件')}")
    return 0
