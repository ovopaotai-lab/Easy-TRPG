import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Cpu,
  Download,
  FolderOpen,
  Globe,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Star,
  Trash2,
  Zap,
} from "lucide-react";
import { apiFetch, streamNDJSON } from "../api/client";
import { useAppStore } from "../stores/useAppStore";
import type { HFDownloadTask, HFPresetItem, PreflightCheck } from "../types/api";

function extractHostLabel(rawUrl?: string): string {
  if (!rawUrl) return "未配置接口";
  try {
    return new URL(rawUrl).host || rawUrl;
  } catch {
    return rawUrl;
  }
}

export function EngineView() {
  const {
    settings,
    hardware,
    remoteModels,
    favoriteModels,
    providerPresets,
    saveSettingsPatch,
    refreshModels,
    notify,
  } = useAppStore();

  const [subTab, setSubTab] = useState<"all" | "api" | "local">("all");
  const [catalog, setCatalog] = useState<HFPresetItem[]>([]);
  const [downloads, setDownloads] = useState<HFDownloadTask[]>([]);
  const [detected, setDetected] = useState<any[]>([]);
  const [preflight, setPreflight] = useState<PreflightCheck[]>([]);
  const [showPreflightDetails, setShowPreflightDetails] = useState(false);
  const [hideCompletedDownloads, setHideCompletedDownloads] = useState(false);

  // API Panel state
  const [showApiConfig, setShowApiConfig] = useState(() => !settings?.base_url && !settings?.has_api_key);
  const [apiSearch, setApiSearch] = useState("");
  const [apiOnlyFav, setApiOnlyFav] = useState(false);
  const [visibleApiCount, setVisibleApiCount] = useState(18);
  const [customModelInput, setCustomModelInput] = useState("");
  const [refreshingApi, setRefreshingApi] = useState(false);
  const [testingApi, setTestingApi] = useState(false);
  const [apiTestMsg, setApiTestMsg] = useState("");

  // Inline API form synced with settings
  const [baseUrl, setBaseUrl] = useState(settings?.base_url || "");
  const [apiKey, setApiKey] = useState(settings?.api_key || "");
  const [protocol, setProtocol] = useState(settings?.api_protocol || "auto");
  const [proxy, setProxy] = useState(settings?.proxy || "");
  const [useProxy, setUseProxy] = useState(Boolean(settings?.use_proxy));

  // Benchmark state
  const [benchLogs, setBenchLogs] = useState<string[]>([]);
  const [benching, setBenching] = useState(false);

  useEffect(() => {
    if (settings) {
      setBaseUrl(settings.base_url || "");
      setApiKey(settings.api_key || "");
      setProtocol(settings.api_protocol || "auto");
      setProxy(settings.proxy || "");
      setUseProxy(Boolean(settings.use_proxy));
    }
  }, [settings?.base_url, settings?.api_key, settings?.api_protocol, settings?.proxy, settings?.use_proxy]);

  const loadStatus = async () => {
    const [mgr, pre] = await Promise.all([
      apiFetch<any>("/api/local_models/manager_status"),
      apiFetch<any>("/api/system/preflight"),
    ]);
    setCatalog(mgr.hf_catalog || []);
    setDownloads(mgr.downloads || []);
    setDetected(mgr.detected_models || []);
    setPreflight(pre.checks || []);
  };

  useEffect(() => {
    loadStatus();
    const timer = setInterval(() => {
      if (downloads.some((d) => d.status === "downloading")) {
        loadStatus();
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [downloads.length]);

  const favSet = useMemo(() => new Set(favoriteModels), [favoriteModels]);

  const orderedRemoteModels = useMemo(() => {
    const active = settings?.model || "";
    const merged = Array.from(new Set([...(remoteModels || []), ...(settings?.custom_models || [])]));
    const filtered = merged.filter((id) => {
      if (apiOnlyFav && !favSet.has(id)) return false;
      if (apiSearch.trim()) {
        return id.toLowerCase().includes(apiSearch.trim().toLowerCase());
      }
      return true;
    });
    return filtered.sort((a, b) => {
      if (a === active) return -1;
      if (b === active) return 1;
      const fa = favSet.has(a) ? 0 : 1;
      const fb = favSet.has(b) ? 0 : 1;
      if (fa !== fb) return fa - fb;
      return 0;
    });
  }, [remoteModels, settings?.custom_models, settings?.model, favSet, apiOnlyFav, apiSearch]);

  const pageCap = subTab === "api" ? Math.max(60, visibleApiCount) : visibleApiCount;
  const shownRemoteModels = orderedRemoteModels.slice(0, pageCap);

  const visibleDownloads = useMemo(() => {
    if (!hideCompletedDownloads) return downloads;
    return downloads.filter((d) => d.status !== "completed");
  }, [downloads, hideCompletedDownloads]);

  const handleSaveApiConfig = async () => {
    setRefreshingApi(true);
    setApiTestMsg("");
    try {
      await saveSettingsPatch({
        base_url: baseUrl.trim(),
        api_key: apiKey,
        api_protocol: protocol,
        proxy: proxy.trim(),
        use_proxy: useProxy,
      });
      await refreshModels();
      await loadStatus();
      notify("API 配置已保存并刷新模型列表");
    } finally {
      setRefreshingApi(false);
    }
  };

  const handleTestApi = async () => {
    const probeModel =
      (settings?.model && !settings.model.startsWith("local/") ? settings.model : "") ||
      orderedRemoteModels[0] ||
      providerPresets.find((p) => p.protocol === protocol)?.default_model ||
      "";
    if (!probeModel) {
      notify("请先填写一个可测试的模型 ID");
      return;
    }
    setTestingApi(true);
    setApiTestMsg("");
    try {
      const res = await apiFetch<any>("/api/models/test", {
        method: "POST",
        body: JSON.stringify({
          model: probeModel,
          base_url: baseUrl.trim(),
          api_key: apiKey,
          api_protocol: protocol,
          proxy: proxy.trim(),
          use_proxy: useProxy,
        }),
      });
      setApiTestMsg(res.ok ? `测通 ${probeModel} (${res.first_token_ms}ms)` : `失败: ${res.error}`);
    } catch (err: any) {
      setApiTestMsg(`异常: ${err?.message || err}`);
    } finally {
      setTestingApi(false);
    }
  };

  const handleToggleFavorite = async (modelId: string) => {
    const res = await apiFetch<{ status: string; favorite_models: string[] }>("/api/models/favorite", {
      method: "POST",
      body: JSON.stringify({ model: modelId }),
    });
    useAppStore.setState({ favoriteModels: res.favorite_models || [] });
  };

  const handleAddCustomModel = async () => {
    const id = customModelInput.trim();
    if (!id) return;
    const nextCustom = Array.from(new Set([id, ...(settings?.custom_models || [])]));
    await saveSettingsPatch({ custom_models: nextCustom, model: id });
    await refreshModels();
    setCustomModelInput("");
    notify(`已添加并选用模型：${id}`);
  };

  const startDownload = async (presetId: string) => {
    await apiFetch("/api/local_models/hf_download", {
      method: "POST",
      body: JSON.stringify({ preset_id: presetId, mirror: "hf-mirror" }),
    });
    setHideCompletedDownloads(false);
    notify("已加入下载队列 (hf-mirror 国内高速镜像)");
    loadStatus();
  };

  const handleUnloadVram = async () => {
    await apiFetch("/api/local_models/unload", { method: "POST" });
    notify("已释放全部本地显存");
  };

  const runQuickBench = async () => {
    const targetModel = settings?.model || detected[0]?.id;
    if (!targetModel) {
      notify("请先选中或下载一个模型");
      return;
    }
    setBenching(true);
    setBenchLogs(["开始测速..."]);
    try {
      await streamNDJSON("/api/system/benchmark/stream", { model: targetModel, mode: "quick" }, (ev) => {
        if (ev.status) setBenchLogs((p) => [...p, ev.status]);
        if (ev.stage_done) {
          const r = ev.stage_done;
          setBenchLogs((p) => [...p, `[完成] ${r.stage}: 首字 ${r.ttft_ms}ms · ${r.tok_per_s} tok/s (${r.tokens} tok)`]);
        }
        if (ev.error) setBenchLogs((p) => [...p, `[错误] ${ev.error}`]);
      });
    } finally {
      setBenching(false);
    }
  };

  const showApiSection = subTab === "all" || subTab === "api";
  const showLocalSection = subTab === "all" || subTab === "local";
  const hasHardwareWarn = preflight.some((ck) => ck.id !== "ai_brain" && !ck.ok);
  const preflightExpanded = showPreflightDetails || subTab === "local" || hasHardwareWarn;

  return (
    <div className="h-full overflow-y-auto p-3 sm:p-6">
      <div className="mx-auto max-w-5xl space-y-3.5 sm:space-y-4">
        {/* Top Sub-tabs + Active Model Status */}
        <div className="flex flex-wrap items-center justify-between gap-2.5 sm:gap-3">
          <div className="flex flex-wrap gap-1.5">
            {(
              [
                ["all", "全部"],
                ["api", `在线 API (${remoteModels.length})`],
                ["local", `本地模型 (${detected.length})`],
              ] as Array<[typeof subTab, string]>
            ).map(([k, lbl]) => (
              <button
                key={k}
                type="button"
                onClick={() => setSubTab(k)}
                className="rounded-lg border px-2.5 sm:px-3 py-1.5 text-xs font-medium transition"
                style={{
                  borderColor: subTab === k ? "var(--accent)" : "var(--border-subtle)",
                  background: subTab === k ? "var(--accent-soft)" : "var(--bg-panel)",
                  color: subTab === k ? "var(--accent)" : "var(--text-secondary)",
                }}
              >
                {lbl}
              </button>
            ))}
          </div>

          <div className="text-xs truncate max-w-full sm:max-w-xs" style={{ color: "var(--text-secondary)" }}>
            当前选用：
            <span className="font-medium ml-1" style={{ color: "var(--accent)" }}>
              {settings?.model || "未选择"}
            </span>
          </div>
        </div>

        {/* Hardware & Preflight Summary Bar */}
        <div className="rounded-2xl border px-3.5 sm:px-5 py-3 sm:py-3.5 space-y-3" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2.5 min-w-0">
              <Cpu className="h-4.5 w-4.5 shrink-0" style={{ color: "var(--accent)" }} />
              <div className="min-w-0">
                <div className="text-xs font-semibold truncate">{hardware?.gpu_name || "硬件探测中..."}</div>
                <div className="text-[11px] truncate" style={{ color: "var(--text-secondary)" }}>
                  {hardware
                    ? `${hardware.ram_total_gib}G 内存 · 显存 ${Math.round(hardware.vram_total_mib / 1024)}G · 磁盘余 ${hardware.free_disk_gb}G`
                    : ""}
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 text-xs">
              <button
                type="button"
                onClick={async () => {
                  const next = settings?.low_spec_mode === "on" ? "auto" : "on";
                  await saveSettingsPatch({ low_spec_mode: next });
                  notify(next === "on" ? "已强制开启低配安全模式" : "已恢复自动适配");
                }}
                className="rounded-lg border px-2.5 py-1"
                style={{
                  borderColor: settings?.low_spec_mode === "on" ? "var(--accent)" : "var(--border-subtle)",
                  background: settings?.low_spec_mode === "on" ? "var(--accent-soft)" : "transparent",
                }}
              >
                低配模式：{settings?.low_spec_mode === "on" ? "开" : "自动"}
              </button>
              <button
                type="button"
                onClick={() => {
                  loadStatus();
                  setShowPreflightDetails((v) => !v);
                }}
                className="inline-flex items-center gap-1 rounded-lg border px-2.5 py-1"
                style={{ borderColor: "var(--border-strong)" }}
              >
                <ShieldCheck className="h-3.5 w-3.5" />
                环境自检
                {preflightExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              </button>
              <button
                type="button"
                onClick={handleUnloadVram}
                className="inline-flex items-center gap-1 rounded-lg border px-2.5 py-1"
                style={{ borderColor: "var(--danger)", color: "var(--danger)" }}
              >
                <Trash2 className="h-3.5 w-3.5" />
                释放显存
              </button>
            </div>
          </div>

          {preflightExpanded && (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 pt-1">
              {preflight.map((ck) => (
                <div
                  key={ck.id}
                  className="flex items-start gap-2 rounded-xl border px-3 py-2 text-xs"
                  style={{ borderColor: "var(--border-subtle)", background: "var(--bg-input)" }}
                >
                  <CheckCircle2
                    className="mt-0.5 h-3.5 w-3.5 shrink-0"
                    style={{ color: ck.ok ? "var(--success)" : "var(--warn)" }}
                  />
                  <div>
                    <div className="font-medium">{ck.name}</div>
                    <div style={{ color: "var(--text-secondary)" }}>{ck.detail}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Online API Models Section */}
        {showApiSection && (
          <div className="rounded-2xl border p-3.5 sm:p-5 space-y-3.5" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <Globe className="h-4 w-4 shrink-0" style={{ color: "var(--accent)" }} />
                <span className="text-sm font-semibold">在线 API 模型 ({orderedRemoteModels.length})</span>
                <span
                  className="rounded px-2 py-0.5 text-[10px] truncate max-w-[140px] sm:max-w-[200px]"
                  style={{ background: "var(--bg-elevated)", color: "var(--text-muted)" }}
                  title={settings?.base_url || ""}
                >
                  {extractHostLabel(settings?.base_url)}
                </span>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <button
                  type="button"
                  disabled={refreshingApi}
                  onClick={async () => {
                    setRefreshingApi(true);
                    try {
                      await refreshModels();
                      notify("已刷新在线模型列表");
                    } finally {
                      setRefreshingApi(false);
                    }
                  }}
                  className="inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 disabled:opacity-50"
                  style={{ borderColor: "var(--border-subtle)", color: "var(--text-secondary)" }}
                >
                  <RefreshCw className={`h-3 w-3 ${refreshingApi ? "animate-spin" : ""}`} />
                  刷新
                </button>
                <button
                  type="button"
                  onClick={() => setShowApiConfig((v) => !v)}
                  className="inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 font-medium"
                  style={{
                    borderColor: showApiConfig ? "var(--accent)" : "var(--border-strong)",
                    background: showApiConfig ? "var(--accent-soft)" : "transparent",
                    color: showApiConfig ? "var(--accent)" : "var(--text-primary)",
                  }}
                >
                  <Settings2 className="h-3 w-3" />
                  {showApiConfig ? "收起配置" : "配置 API"}
                </button>
              </div>
            </div>

            {showApiConfig && (
              <div className="rounded-xl border p-3.5 space-y-3 text-xs" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-elevated)" }}>
                <div className="flex flex-wrap gap-1.5">
                  {providerPresets.map((vp) => (
                    <button
                      key={vp.id}
                      type="button"
                      onClick={() => {
                        setBaseUrl(vp.base_url);
                        setProtocol(vp.protocol);
                      }}
                      className="rounded-lg border px-2.5 py-1 transition"
                      style={{
                        borderColor: baseUrl === vp.base_url ? "var(--accent)" : "var(--border-subtle)",
                        background: baseUrl === vp.base_url ? "var(--accent-soft)" : "var(--bg-input)",
                        color: baseUrl === vp.base_url ? "var(--accent)" : "var(--text-secondary)",
                      }}
                    >
                      {vp.name}
                    </button>
                  ))}
                </div>
                <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
                  <select
                    value={protocol}
                    onChange={(e) => setProtocol(e.target.value)}
                    className="rounded-lg border px-2.5 py-1.5 outline-none"
                    style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
                  >
                    <option value="auto">自动识别 (auto)</option>
                    <option value="openai">OpenAI / DeepSeek / 中转</option>
                    <option value="claude">Claude 原生 (/v1/messages)</option>
                    <option value="gemini">Gemini 原生 (BLOCK_NONE)</option>
                    <option value="ollama">Ollama (11434)</option>
                  </select>
                  <input
                    value={baseUrl}
                    onChange={(e) => setBaseUrl(e.target.value)}
                    placeholder="API Base URL（如 https://api.deepseek.com/v1）"
                    className="rounded-lg border px-2.5 py-1.5 outline-none sm:col-span-2"
                    style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
                  />
                </div>
                <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3 items-center">
                  <input
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="API Key（保留 **** 表示维持当前密钥）"
                    className="rounded-lg border px-2.5 py-1.5 outline-none sm:col-span-2"
                    style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
                  />
                  <div className="flex items-center gap-2">
                    <input
                      value={proxy}
                      onChange={(e) => setProxy(e.target.value)}
                      placeholder="代理（可选）"
                      className="flex-1 min-w-0 rounded-lg border px-2.5 py-1.5 outline-none"
                      style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
                    />
                    <label className="inline-flex shrink-0 items-center gap-1" style={{ color: "var(--text-secondary)" }}>
                      <input type="checkbox" checked={useProxy} onChange={(e) => setUseProxy(e.target.checked)} />
                      代理
                    </label>
                  </div>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span style={{ color: "var(--text-secondary)" }}>{apiTestMsg}</span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={testingApi}
                      onClick={handleTestApi}
                      className="rounded-lg border px-3 py-1.5 disabled:opacity-50"
                      style={{ borderColor: "var(--border-strong)", color: "var(--text-primary)" }}
                    >
                      {testingApi ? "测试中..." : "测试连接"}
                    </button>
                    <button
                      type="button"
                      disabled={refreshingApi}
                      onClick={handleSaveApiConfig}
                      className="rounded-lg px-3.5 py-1.5 font-medium disabled:opacity-50"
                      style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
                    >
                      保存并刷新
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Search, Filter & Quick Custom Model */}
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <div className="relative flex-1 min-w-[140px]">
                <Search className="absolute left-2.5 top-2 h-3.5 w-3.5" style={{ color: "var(--text-muted)" }} />
                <input
                  value={apiSearch}
                  onChange={(e) => setApiSearch(e.target.value)}
                  placeholder="搜索 API 模型名..."
                  className="w-full rounded-lg border pl-8 pr-3 py-1.5 outline-none"
                  style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
                />
              </div>
              <button
                type="button"
                onClick={() => setApiOnlyFav((v) => !v)}
                className="inline-flex shrink-0 items-center gap-1 rounded-lg border px-2.5 py-1.5"
                style={{
                  borderColor: apiOnlyFav ? "var(--accent)" : "var(--border-subtle)",
                  background: apiOnlyFav ? "var(--accent-soft)" : "var(--bg-input)",
                  color: apiOnlyFav ? "var(--accent)" : "var(--text-secondary)",
                }}
              >
                <Star className="h-3.5 w-3.5" />
                仅收藏 ({favoriteModels.length})
              </button>
              <div className="flex w-full sm:w-auto items-center gap-1">
                <input
                  value={customModelInput}
                  onChange={(e) => setCustomModelInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleAddCustomModel();
                  }}
                  placeholder="手动添加模型 ID"
                  className="flex-1 min-w-0 sm:w-36 rounded-lg border px-2.5 py-1.5 outline-none"
                  style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
                />
                <button
                  type="button"
                  onClick={handleAddCustomModel}
                  className="inline-flex shrink-0 items-center gap-1 rounded-lg border px-2.5 py-1.5"
                  style={{ borderColor: "var(--border-strong)", color: "var(--text-primary)" }}
                >
                  <Plus className="h-3.5 w-3.5" />
                  添加
                </button>
              </div>
            </div>

            {shownRemoteModels.length === 0 ? (
              <div className="py-4 text-center text-xs" style={{ color: "var(--text-muted)" }}>
                {remoteModels.length === 0
                  ? "尚未拉取到在线模型，请点击上方「配置 API」选择厂商并填写 Key，或手动添加模型 ID。"
                  : "没有匹配的模型。"}
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {shownRemoteModels.map((id) => {
                    const isActive = settings?.model === id;
                    const isFav = favSet.has(id);
                    return (
                      <div
                        key={id}
                        className="flex items-center justify-between gap-2 rounded-xl border px-3 py-2 text-xs"
                        style={{
                          borderColor: isActive ? "var(--accent)" : "var(--border-subtle)",
                          background: "var(--bg-input)",
                        }}
                      >
                        <button
                          type="button"
                          onClick={() => handleToggleFavorite(id)}
                          className="shrink-0 p-0.5 hover:opacity-80"
                          title={isFav ? "取消收藏" : "收藏置顶"}
                          style={{ color: isFav ? "var(--accent)" : "var(--text-muted)" }}
                        >
                          <Star className="h-3.5 w-3.5" fill={isFav ? "currentColor" : "none"} />
                        </button>
                        <span className="flex-1 min-w-0 truncate font-medium" title={id}>
                          {id}
                        </span>
                        <button
                          type="button"
                          onClick={async () => {
                            await saveSettingsPatch({ model: id });
                            notify(`已切换模型：${id}`);
                          }}
                          className="shrink-0 rounded-lg px-2.5 py-1 font-medium"
                          style={{
                            background: isActive ? "var(--success-soft)" : "var(--accent)",
                            color: isActive ? "var(--success)" : "var(--accent-fg)",
                          }}
                        >
                          {isActive ? "使用中" : "选用"}
                        </button>
                      </div>
                    );
                  })}
                </div>
                {orderedRemoteModels.length > pageCap && (
                  <div className="flex justify-center pt-1">
                    <button
                      type="button"
                      onClick={() => setVisibleApiCount((c) => c + 48)}
                      className="rounded-lg border px-4 py-1.5 text-xs"
                      style={{ borderColor: "var(--border-strong)", color: "var(--text-secondary)" }}
                    >
                      展开更多 ({orderedRemoteModels.length - pageCap} 个未显示)
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* Installed Local Models */}
        {showLocalSection && (
          <div className="rounded-2xl border p-3.5 sm:p-5 space-y-3" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-semibold">已安装本地模型 ({detected.length})</span>
              <button
                type="button"
                onClick={() => apiFetch("/api/local_models/open_folder", { method: "POST", body: JSON.stringify({ target: "model" }) })}
                className="inline-flex items-center gap-1 rounded-lg border px-3 py-1 text-xs"
                style={{ borderColor: "var(--border-subtle)" }}
              >
                <FolderOpen className="h-3.5 w-3.5" />
                打开 model 文件夹
              </button>
            </div>
            {detected.length === 0 ? (
              <div className="text-xs py-3" style={{ color: "var(--text-muted)" }}>
                尚未检测到本地 .gguf 文件，可直接在下方下载或把模型放入 model/ 目录。
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {detected.map((m) => (
                  <div
                    key={m.id}
                    className="flex items-center justify-between rounded-xl border px-3 py-2.5 text-xs"
                    style={{
                      borderColor: settings?.model === m.id ? "var(--accent)" : "var(--border-subtle)",
                      background: "var(--bg-input)",
                    }}
                  >
                    <div className="min-w-0 pr-2">
                      <div className="font-medium truncate">{m.name}</div>
                      <div style={{ color: "var(--text-muted)" }}>{m.source_label}</div>
                    </div>
                    <button
                      type="button"
                      onClick={async () => {
                        await saveSettingsPatch({ model: m.id });
                        await refreshModels();
                        notify(`已切换模型：${m.name}`);
                      }}
                      className="shrink-0 rounded-lg px-3 py-1 font-medium"
                      style={{
                        background: settings?.model === m.id ? "var(--success-soft)" : "var(--accent)",
                        color: settings?.model === m.id ? "var(--success)" : "var(--accent-fg)",
                      }}
                    >
                      {settings?.model === m.id ? "使用中" : "选用"}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Active Downloads */}
        {showLocalSection && visibleDownloads.length > 0 && (
          <div className="rounded-2xl border p-4 space-y-2 text-xs" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}>
            <div className="flex items-center justify-between">
              <span className="font-semibold">下载进度</span>
              {visibleDownloads.some((d) => d.status === "completed") && (
                <button
                  type="button"
                  onClick={() => setHideCompletedDownloads(true)}
                  className="text-[11px] hover:underline"
                  style={{ color: "var(--text-muted)" }}
                >
                  隐藏已完成
                </button>
              )}
            </div>
            {visibleDownloads.map((d) => (
              <div key={d.id} className="space-y-1 rounded-lg border p-2.5" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-input)" }}>
                <div className="flex justify-between gap-2">
                  <span className="truncate">
                    {d.title}
                    {d.current_file ? ` (${d.current_file})` : ""}
                  </span>
                  <span className="shrink-0">
                    {d.progress}% · {d.speed_mb_s} MB/s · {d.status}
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full" style={{ background: "var(--bg-hover)" }}>
                  <div className="h-full" style={{ width: `${d.progress}%`, background: "var(--accent)" }} />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Tiered HF-Mirror Model Catalog */}
        {showLocalSection && (
          <div className="rounded-2xl border p-3.5 sm:p-5 space-y-3" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-semibold">模型下载中心 (hf-mirror 国内直连)</span>
              <span className="text-xs" style={{ color: "var(--accent)" }}>
                推荐您的硬件：{hardware?.recommended_preset_label}
              </span>
            </div>
            <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2">
              {catalog.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between gap-3 rounded-xl border p-3 text-xs"
                  style={{
                    borderColor: !item.not_recommended && item.id === hardware?.recommended_preset_id ? "var(--accent)" : "var(--border-subtle)",
                    background: "var(--bg-input)",
                  }}
                >
                  <div className="space-y-0.5 min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5 font-medium">
                      <span className="break-words">{item.name}</span>
                      {item.not_recommended ? (
                        <span className="shrink-0 rounded px-1.5 py-0.5 text-[10px]" style={{ background: "rgba(196, 149, 63, 0.16)", color: "var(--warn)" }}>
                          不推荐
                        </span>
                      ) : (
                        item.id === hardware?.recommended_preset_id && (
                          <span className="shrink-0 rounded px-1.5 py-0.5 text-[10px]" style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>
                            本机最佳
                          </span>
                        )
                      )}
                    </div>
                    <div className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                      {item.vram_hint} · {item.total_size_gb} GB
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={item.installed}
                    onClick={() => startDownload(item.id)}
                    className="inline-flex shrink-0 items-center gap-1 rounded-lg px-3 py-1.5 font-medium disabled:opacity-50"
                    style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
                  >
                    <Download className="h-3.5 w-3.5" />
                    {item.installed ? "已下载" : "下载"}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Benchmark Center */}
        {showLocalSection && (
          <div className="rounded-2xl border p-3.5 sm:p-5 space-y-3 text-xs" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="inline-flex items-center gap-1.5 text-sm font-semibold">
                <Activity className="h-4 w-4" style={{ color: "var(--accent)" }} />
                性能测试中心
              </span>
              <button
                type="button"
                disabled={benching}
                onClick={runQuickBench}
                className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 font-medium disabled:opacity-50"
                style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
              >
                <Zap className="h-3.5 w-3.5" />
                {benching ? "测试中..." : "快速测试"}
              </button>
            </div>
            {benchLogs.length > 0 && (
              <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-xl p-3 font-mono text-[11px] leading-relaxed" style={{ background: "var(--bg-input)", color: "var(--text-secondary)" }}>
                {benchLogs.join("\n")}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
