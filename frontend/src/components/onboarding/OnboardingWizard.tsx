import React, { useState } from "react";
import { CheckCircle2, Cpu, Download, Globe, Sparkles, X } from "lucide-react";
import { apiFetch } from "../../api/client";
import { useAppStore } from "../../stores/useAppStore";

export function OnboardingWizard() {
  const {
    hardware,
    providerPresets,
    exploreApps,
    dismissOnboarding,
    saveSettingsPatch,
    refreshModels,
    installExploreCampaign,
    setTab,
    notify,
  } = useAppStore();

  const [step, setStep] = useState<1 | 2>(1);
  const [brainMode, setBrainMode] = useState<"local" | "api">(
    hardware && (hardware.tier === "CPU" || hardware.tier === "C") ? "api" : "local"
  );
  const [selectedVendor, setSelectedVendor] = useState("deepseek");
  const [baseUrl, setBaseUrl] = useState("https://api.deepseek.com/v1");
  const [apiKey, setApiKey] = useState("");
  const [apiModel, setApiModel] = useState("deepseek-chat");
  const [protocol, setProtocol] = useState("openai");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string>("");

  const handleVendorPick = (id: string) => {
    setSelectedVendor(id);
    const vp = providerPresets.find((p) => p.id === id);
    if (vp) {
      setBaseUrl(vp.base_url);
      setApiModel(vp.default_model);
      setProtocol(vp.protocol);
    }
  };

  const handleTestAndSaveApi = async () => {
    if (!apiKey.trim() && protocol !== "ollama") {
      notify("请填写 API Key");
      return;
    }
    setTesting(true);
    setTestResult("");
    try {
      const res = await apiFetch<any>("/api/models/test", {
        method: "POST",
        body: JSON.stringify({
          model: apiModel,
          base_url: baseUrl,
          api_key: apiKey,
          api_protocol: protocol,
        }),
      });
      if (res.ok) {
        await saveSettingsPatch({
          base_url: baseUrl,
          api_key: apiKey,
          api_protocol: protocol,
          model: apiModel,
          onboarding_completed: true,
        });
        await refreshModels();
        setTestResult(`连接成功 (${res.first_token_ms}ms)`);
        setStep(2);
      } else {
        setTestResult(`连接失败: ${res.error}`);
      }
    } catch (err: any) {
      setTestResult(`异常: ${err?.message || err}`);
    } finally {
      setTesting(false);
    }
  };

  const handleDownloadRecommendedLocal = async () => {
    if (!hardware?.recommended_preset_id) return;
    try {
      await apiFetch("/api/local_models/hf_download", {
        method: "POST",
        body: JSON.stringify({ preset_id: hardware.recommended_preset_id, mirror: "hf-mirror" }),
      });
      await saveSettingsPatch({
        low_spec_mode: hardware.low_spec_recommended ? "on" : "auto",
        onboarding_completed: true,
      });
      notify("已开始后台下载推荐模型，可在「模型」页查看进度");
      setStep(2);
    } catch (err: any) {
      notify(err?.message || "启动下载失败");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-2.5 sm:p-4 backdrop-blur-sm">
      <div
        className="max-h-[92dvh] w-full max-w-2xl overflow-y-auto rounded-2xl border p-4 sm:p-6 shadow-2xl"
        style={{ background: "var(--bg-panel)", borderColor: "var(--border-strong)" }}
      >
        <div className="flex items-center justify-between pb-4 border-b" style={{ borderColor: "var(--border-subtle)" }}>
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5" style={{ color: "var(--accent)" }} />
            <h2 className="text-base font-semibold">
              {step === 1 ? "第 1 步 · 选择 AI 大脑" : "第 2 步 · 挑个剧本开玩"}
            </h2>
          </div>
          <button
            type="button"
            onClick={dismissOnboarding}
            className="rounded-lg p-1 text-xs hover:opacity-80"
            style={{ color: "var(--text-muted)" }}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {step === 1 ? (
          <div className="mt-4 space-y-4">
            {hardware && (
              <div
                className="flex flex-wrap items-center justify-between gap-2 rounded-xl border px-3.5 py-2.5 text-xs"
                style={{ borderColor: "var(--border-subtle)", background: "var(--bg-elevated)" }}
              >
                <div className="flex items-center gap-2">
                  <Cpu className="h-4 w-4" style={{ color: "var(--accent)" }} />
                  <span>
                    {hardware.gpu_name} · 显存 {Math.round(hardware.vram_total_mib / 1024)}G · 内存 {hardware.ram_total_gib}G
                  </span>
                </div>
                <span
                  className="rounded-full px-2.5 py-0.5 font-medium"
                  style={{ background: "var(--accent-soft)", color: "var(--accent)" }}
                >
                  {hardware.tier_label} {hardware.low_spec_recommended ? "· 低配适配" : ""}
                </span>
              </div>
            )}

            <div className="grid grid-cols-2 gap-2.5">
              <button
                type="button"
                onClick={() => setBrainMode("local")}
                className="rounded-xl border p-2.5 sm:p-3 text-left transition"
                style={{
                  borderColor: brainMode === "local" ? "var(--accent)" : "var(--border-subtle)",
                  background: brainMode === "local" ? "var(--accent-soft)" : "var(--bg-elevated)",
                }}
              >
                <div className="flex items-center gap-2 text-sm font-medium">
                  <Download className="h-4 w-4" style={{ color: "var(--accent)" }} />
                  本地免费跑
                </div>
                <p className="mt-1 text-xs" style={{ color: "var(--text-secondary)" }}>
                  断网可用 · 零费用 · 隐私本地
                </p>
              </button>
              <button
                type="button"
                onClick={() => setBrainMode("api")}
                className="rounded-xl border p-2.5 sm:p-3 text-left transition"
                style={{
                  borderColor: brainMode === "api" ? "var(--accent)" : "var(--border-subtle)",
                  background: brainMode === "api" ? "var(--accent-soft)" : "var(--bg-elevated)",
                }}
              >
                <div className="flex items-center gap-2 text-sm font-medium">
                  <Globe className="h-4 w-4" style={{ color: "var(--accent)" }} />
                  在线 API 秒玩
                </div>
                <p className="mt-1 text-xs" style={{ color: "var(--text-secondary)" }}>
                  不吃显卡 · 轻薄本首选
                </p>
              </button>
            </div>

            {brainMode === "local" ? (
              <div
                className="rounded-xl border p-4 space-y-3"
                style={{ borderColor: "var(--border-subtle)", background: "var(--bg-elevated)" }}
              >
                <div className="text-xs" style={{ color: "var(--text-secondary)" }}>
                  为当前配置智能匹配的唯一最佳模型：
                </div>
                <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                  {hardware?.recommended_preset_label || "Qwen3-8B (Q4_K_M · 不推荐，建议在线 API)"}
                </div>
                <div className="flex flex-wrap gap-2 pt-1">
                  <button
                    type="button"
                    onClick={handleDownloadRecommendedLocal}
                    className="rounded-lg px-4 py-2 text-xs font-medium"
                    style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
                  >
                    一键下载并继续
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      dismissOnboarding();
                      setTab("engine");
                    }}
                    className="rounded-lg border px-3 py-2 text-xs"
                    style={{ borderColor: "var(--border-strong)", color: "var(--text-secondary)" }}
                  >
                    去选其他模型 / 已有 GGUF
                  </button>
                </div>
              </div>
            ) : (
              <div
                className="rounded-xl border p-4 space-y-3"
                style={{ borderColor: "var(--border-subtle)", background: "var(--bg-elevated)" }}
              >
                <div className="flex flex-wrap gap-1.5">
                  {providerPresets.slice(0, 6).map((vp) => (
                    <button
                      key={vp.id}
                      type="button"
                      onClick={() => handleVendorPick(vp.id)}
                      className="rounded-lg border px-2.5 py-1 text-xs"
                      style={{
                        borderColor: selectedVendor === vp.id ? "var(--accent)" : "var(--border-subtle)",
                        background: selectedVendor === vp.id ? "var(--accent-soft)" : "transparent",
                        color: selectedVendor === vp.id ? "var(--accent)" : "var(--text-secondary)",
                      }}
                    >
                      {vp.name}
                    </button>
                  ))}
                </div>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <input
                    value={apiModel}
                    onChange={(e) => setApiModel(e.target.value)}
                    placeholder="模型名 (如 deepseek-chat)"
                    className="rounded-lg border px-3 py-2 text-xs outline-none"
                    style={{ borderColor: "var(--border-subtle)", background: "var(--bg-input)", color: "var(--text-primary)" }}
                  />
                  <input
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="粘贴 API Key (sk-...)"
                    className="rounded-lg border px-3 py-2 text-xs outline-none"
                    style={{ borderColor: "var(--border-subtle)", background: "var(--bg-input)", color: "var(--text-primary)" }}
                  />
                </div>
                <input
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="接口地址"
                  className="w-full rounded-lg border px-3 py-2 text-xs outline-none"
                  style={{ borderColor: "var(--border-subtle)", background: "var(--bg-input)", color: "var(--text-primary)" }}
                />
                <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                  <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                    {testResult}
                  </span>
                  <button
                    type="button"
                    disabled={testing}
                    onClick={handleTestAndSaveApi}
                    className="rounded-lg px-4 py-2 text-xs font-medium disabled:opacity-50"
                    style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
                  >
                    {testing ? "测试中..." : "测通并进入下一步"}
                  </button>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="mt-4 space-y-3">
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 max-h-80 overflow-y-auto pr-1">
              {exploreApps.map((app) => (
                <div
                  key={app.id}
                  className="flex flex-col justify-between rounded-xl border p-3"
                  style={{ borderColor: "var(--border-subtle)", background: "var(--bg-elevated)" }}
                >
                  <div>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium">{app.name}</span>
                      <span className="rounded px-1.5 py-0.5 text-[10px]" style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>
                        {app.category}
                      </span>
                    </div>
                    <p className="mt-1 text-xs line-clamp-2" style={{ color: "var(--text-secondary)" }}>
                      {app.description}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={async () => {
                      await installExploreCampaign(app.id);
                      await dismissOnboarding();
                    }}
                    className="mt-3 inline-flex items-center justify-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium"
                    style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    立刻开团
                  </button>
                </div>
              ))}
            </div>
            <div className="flex justify-end">
              <button
                type="button"
                onClick={dismissOnboarding}
                className="text-xs px-3 py-1.5 rounded-lg border"
                style={{ borderColor: "var(--border-subtle)", color: "var(--text-secondary)" }}
              >
                跳过，直接用默认极速跑团
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
