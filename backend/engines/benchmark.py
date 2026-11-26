# -*- coding: utf-8 -*-
"""System telemetry, single-stream 5-dim / 32K benchmark, and 1-16 parallel stress runner."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, Dict, List

from backend.engines.hardware import get_hardware_snapshot_async
from backend.engines.supervisor import ensure_local_engine_ready
from backend.providers.router import resolve_model_endpoint, stream_via_endpoint


async def get_benchmark_telemetry() -> Dict[str, Any]:
    hw = await get_hardware_snapshot_async(use_cache=False)
    try:
        import psutil
        cpu_pct = psutil.cpu_percent(interval=None)
    except Exception:
        cpu_pct = 0.0
    return {
        "ok": True,
        "cpu_percent": cpu_pct,
        **hw,
    }


def _build_32k_prompt(target_tokens: int = 31000) -> str:
    seed = "【档案记录】在雾港镇第七号灯塔的地下密室里，发条机械钟每七分钟发出一声轻响，潮汐日志记录了第14次异常涨潮与古老徽章的共振现象。"
    repeat_cnt = max(20, target_tokens // 65)
    return "\n".join(f"[{i:04d}] {seed}" for i in range(repeat_cnt)) + "\n请用一句话总结档案核心异常。"


async def run_benchmark_stream(
    model_id: str,
    mode: str,
    settings: Dict[str, Any],
) -> AsyncIterator[str]:
    ep = resolve_model_endpoint(model_id, settings)
    if ep["is_local"]:
        yield json.dumps({"stage": "boot", "status": "正在唤醒本地模型..."}) + "\n"
        err = await ensure_local_engine_ready(model_id, ep["local_meta"], settings=settings)
        if err:
            yield json.dumps({"error": err.get("message") or "引擎启动失败", "diagnosis": err}) + "\n"
            return

    stages = (
        [("32K 上下文", _build_32k_prompt(30000), 128), ("长文生成", "请描写一场雨夜蒸汽火车站对峙戏，约 800 字。", 1024)]
        if mode == "full"
        else [("快速响应", "请用 120 字描写一座雨夜灯塔的氛围。", 192)]
    )

    results: List[Dict[str, Any]] = []
    for label, prompt, max_tok in stages:
        t0 = time.perf_counter()
        ttft = 0.0
        toks = 0
        yield json.dumps({"stage": label, "status": f"测试中: {label}"}) + "\n"
        try:
            async for delta in stream_via_endpoint(
                endpoint=ep,
                messages=[{"role": "user", "content": prompt}],
                params={"temperature": 0.65, "max_tokens": max_tok},
                proxy_url=(settings.get("proxy") if settings.get("use_proxy") else None),
                think_enabled=False,
            ):
                if delta.text or delta.thinking:
                    if ttft == 0.0:
                        ttft = time.perf_counter() - t0
                    toks += max(1, len(delta.text + delta.thinking) // 2)
            elapsed = max(0.05, time.perf_counter() - t0)
            gen_t = max(0.05, elapsed - ttft)
            tps = round(toks / gen_t, 1)
            rec = {"stage": label, "ttft_ms": int(ttft * 1000), "tokens": toks, "tok_per_s": tps, "elapsed_s": round(elapsed, 2)}
            results.append(rec)
            yield json.dumps({"stage_done": rec}) + "\n"
        except Exception as exc:
            yield json.dumps({"error": f"{label} 失败: {exc}"}) + "\n"
            return

    yield json.dumps({"done": True, "results": results}) + "\n"


async def run_parallel_benchmark_stream(
    model_id: str,
    concurrency: int,
    settings: Dict[str, Any],
) -> AsyncIterator[str]:
    conc = max(1, min(16, int(concurrency or 1)))
    ep = resolve_model_endpoint(model_id, settings)
    if ep["is_local"]:
        err = await ensure_local_engine_ready(model_id, ep["local_meta"], settings=settings, req_parallel=conc, slot_ctx_tokens=8192)
        if err:
            yield json.dumps({"error": err.get("message") or "引擎启动失败"}) + "\n"
            return

    t0 = time.perf_counter()
    lane_stats: Dict[int, Dict[str, Any]] = {i: {"lane": i + 1, "tokens": 0, "tok_per_s": 0.0, "done": False} for i in range(conc)}

    async def _worker(idx: int):
        lt0 = time.perf_counter()
        toks = 0
        async for delta in stream_via_endpoint(
            endpoint=ep,
            messages=[{"role": "user", "content": f"第{idx+1}路压测：请用 300 字描写一段地下城探索。"}],
            params={"temperature": 0.7, "max_tokens": 512},
            think_enabled=False,
        ):
            if delta.text:
                toks += max(1, len(delta.text) // 2)
                dt = max(0.05, time.perf_counter() - lt0)
                lane_stats[idx]["tokens"] = toks
                lane_stats[idx]["tok_per_s"] = round(toks / dt, 1)
        lane_stats[idx]["done"] = True

    tasks = [asyncio.create_task(_worker(i)) for i in range(conc)]
    while any(not t.done() for t in tasks):
        await asyncio.sleep(0.5)
        total_tok = sum(v["tokens"] for v in lane_stats.values())
        yield json.dumps({"lanes": list(lane_stats.values()), "total_tokens": total_tok, "elapsed_s": round(time.perf_counter() - t0, 1)}) + "\n"
    await asyncio.gather(*tasks, return_exceptions=True)
    total_tok = sum(v["tokens"] for v in lane_stats.values())
    elapsed = max(0.1, time.perf_counter() - t0)
    yield json.dumps({"done": True, "lanes": list(lane_stats.values()), "total_tokens": total_tok, "total_tok_per_s": round(total_tok / elapsed, 1)}) + "\n"
