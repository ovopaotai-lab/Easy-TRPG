import React, { useEffect, useState } from "react";
import { Check, FolderInput, Globe, HardDrive, Palette, Save } from "lucide-react";
import { apiFetch } from "../api/client";
import { useAppStore } from "../stores/useAppStore";
import type { LangId, ThemeId } from "../types/api";

export function SettingsView() {
  const {
    settings,
    providerPresets,
    theme,
    lang,
    saveSettingsPatch,
    refreshModels,
    setTheme,
    setLang,
    notify,
  } = useAppStore();

  const [baseUrl, setBaseUrl] = useState(settings?.base_url || "");
  const [apiKey, setApiKey] = useState(settings?.api_key || "");
  const [protocol, setProtocol] = useState(settings?.api_protocol || "auto");
  const [model, setModel] = useState(settings?.model || "");
  const [proxy, setProxy] = useState(settings?.proxy || "");
  const [useProxy, setUseProxy] = useState(Boolean(settings?.use_proxy));
  const [temp, setTemp] = useState(settings?.temperature ?? 0.68);
  const [maxTokens, setMaxTokens] = useState(settings?.max_tokens ?? 8192);
  const [ctxK, setCtxK] = useState(settings?.max_context_k ?? 96);
  const [backupInfo, setBackupInfo] = useState<any>(null);
  const [exportPath, setExportPath] = useState("");
  const [importPath, setImportPath] = useState("");

  useEffect(() => {
    apiFetch("/api/backup/overview").then((d) => {
      setBackupInfo(d);
      setExportPath(d.default_export_dir || "");
    });
  }, []);

  const handleSave = async () => {
    await saveSettingsPatch({
      base_url: baseUrl,
      api_key: apiKey,
      api_protocol: protocol,
      model,
      proxy,
      use_proxy: useProxy,
      temperature: Number(temp),
      max_tokens: Number(maxTokens),
      max_context_k: Number(ctxK),
    });
    await refreshModels();
    notify("设置已保存");
  };

  return (
    <div className="h-full overflow-y-auto p-3 sm:p-6">
      <div className="mx-auto max-w-4xl space-y-4 sm:space-y-5 text-xs">
        {/* API & Vendor Presets */}
        <div className="rounded-2xl border p-3.5 sm:p-5 space-y-4" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 text-sm font-semibold">
              <Globe className="h-4 w-4" style={{ color: "var(--accent)" }} />
              在线 API 与模型参数
            </span>
            <button
              type="button"
              onClick={handleSave}
              className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 font-medium"
              style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
            >
              <Save className="h-3.5 w-3.5" />
              保存设置
            </button>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {providerPresets.map((vp) => (
              <button
                key={vp.id}
                type="button"
                onClick={() => {
                  setBaseUrl(vp.base_url);
                  setProtocol(vp.protocol);
                  if (vp.default_model) setModel(vp.default_model);
                }}
                className="rounded-lg border px-2.5 py-1"
                style={{ borderColor: "var(--border-subtle)", background: "var(--bg-input)" }}
              >
                {vp.name}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="space-y-1">
              <span style={{ color: "var(--text-secondary)" }}>协议模式</span>
              <select
                value={protocol}
                onChange={(e) => setProtocol(e.target.value)}
                className="w-full rounded-lg border px-3 py-2"
                style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
              >
                <option value="auto">自动识别 (auto)</option>
                <option value="openai">OpenAI / DeepSeek / 中转</option>
                <option value="claude">Claude 原生 (/v1/messages)</option>
                <option value="gemini">Gemini 原生 (BLOCK_NONE)</option>
                <option value="ollama">Ollama (11434)</option>
              </select>
            </label>
            <label className="space-y-1">
              <span style={{ color: "var(--text-secondary)" }}>当前模型</span>
              <input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 outline-none"
                style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
              />
            </label>
            <label className="space-y-1">
              <span style={{ color: "var(--text-secondary)" }}>API Base URL</span>
              <input
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 outline-none"
                style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
              />
            </label>
            <label className="space-y-1">
              <span style={{ color: "var(--text-secondary)" }}>API Key</span>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 outline-none"
                style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
              />
            </label>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 pt-2 border-t" style={{ borderColor: "var(--border-subtle)" }}>
            <label className="space-y-1">
              <span style={{ color: "var(--text-secondary)" }}>温度 Temperature ({temp})</span>
              <input type="range" min={0} max={1.5} step={0.02} value={temp} onChange={(e) => setTemp(Number(e.target.value))} className="w-full" />
            </label>
            <label className="space-y-1">
              <span style={{ color: "var(--text-secondary)" }}>单次最大输出 Tokens</span>
              <input type="number" value={maxTokens} onChange={(e) => setMaxTokens(Number(e.target.value))} className="w-full rounded border px-2 py-1" style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }} />
            </label>
            <label className="space-y-1">
              <span style={{ color: "var(--text-secondary)" }}>上下文窗口 ({ctxK}K)</span>
              <input type="number" value={ctxK} onChange={(e) => setCtxK(Number(e.target.value))} className="w-full rounded border px-2 py-1" style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }} />
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-3 pt-1">
            <label className="inline-flex items-center gap-1.5">
              <input type="checkbox" checked={useProxy} onChange={(e) => setUseProxy(e.target.checked)} />
              启用在线 API 代理
            </label>
            <input
              value={proxy}
              onChange={(e) => setProxy(e.target.value)}
              placeholder="http://127.0.0.1:7890"
              className="flex-1 min-w-[200px] rounded-lg border px-3 py-1.5 outline-none"
              style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
            />
          </div>
        </div>

        {/* Theme & Language */}
        <div className="rounded-2xl border p-3.5 sm:p-5 space-y-3" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}>
          <div className="inline-flex items-center gap-1.5 text-sm font-semibold">
            <Palette className="h-4 w-4" style={{ color: "var(--accent)" }} />
            外观与语言
          </div>
          <div className="flex flex-wrap gap-2">
            {(
              [
                ["lamplight-dark", "暗金灯火"],
                ["lamplight-paper", "暖纸书卷"],
                ["midnight-slate", "午夜石板"],
              ] as Array<[ThemeId, string]>
            ).map(([tid, label]) => (
              <button
                key={tid}
                type="button"
                onClick={() => setTheme(tid)}
                className="inline-flex items-center gap-1 rounded-lg border px-3 py-1.5"
                style={{
                  borderColor: theme === tid ? "var(--accent)" : "var(--border-subtle)",
                  background: theme === tid ? "var(--accent-soft)" : "var(--bg-input)",
                }}
              >
                {theme === tid && <Check className="h-3.5 w-3.5" />}
                {label}
              </button>
            ))}

            <select
              value={lang}
              onChange={(e) => setLang(e.target.value as LangId)}
              className="sm:ml-auto rounded-lg border px-3 py-1.5"
              style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
            >
              <option value="zh-CN">简体中文</option>
              <option value="en-US">English</option>
            </select>
          </div>
        </div>

        {/* Backup & Migration */}
        <div className="rounded-2xl border p-3.5 sm:p-5 space-y-3" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 text-sm font-semibold">
              <HardDrive className="h-4 w-4" style={{ color: "var(--accent)" }} />
              数据备份与旧版存档迁移
            </span>
            {backupInfo && (
              <span style={{ color: "var(--text-muted)" }}>
                剧本 {backupInfo.projects?.length || 0} · 对话 {backupInfo.chats?.length || 0} · 图片 {backupInfo.gallery_count || 0}
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <input
              value={exportPath}
              onChange={(e) => setExportPath(e.target.value)}
              className="min-w-0 w-full sm:w-auto sm:flex-1 rounded-lg border px-3 py-1.5 outline-none"
              style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
            />
            <button
              type="button"
              onClick={async () => {
                const res = await apiFetch<any>("/api/backup/export-folder", {
                  method: "POST",
                  body: JSON.stringify({ folder_path: exportPath }),
                });
                notify(`已导出至 ${res.export_dir}`);
              }}
              className="rounded-lg px-3.5 py-1.5 font-medium"
              style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
            >
              一键全量备份
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            <input
              value={importPath}
              onChange={(e) => setImportPath(e.target.value)}
              placeholder="填入旧版 alpha 1.x 或备份目录路径..."
              className="min-w-0 w-full sm:w-auto sm:flex-1 rounded-lg border px-3 py-1.5 outline-none"
              style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
            />
            <button
              type="button"
              onClick={async () => {
                const res = await apiFetch<any>("/api/backup/import-folder", {
                  method: "POST",
                  body: JSON.stringify({ folder_path: importPath }),
                });
                notify(`导入完成：${JSON.stringify(res.imported)}`);
                window.location.reload();
              }}
              className="inline-flex items-center gap-1 rounded-lg border px-3.5 py-1.5"
              style={{ borderColor: "var(--border-strong)" }}
            >
              <FolderInput className="h-3.5 w-3.5" />
              从目录无损导入
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
