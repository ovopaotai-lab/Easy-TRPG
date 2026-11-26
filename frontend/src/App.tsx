import React, { useEffect } from "react";
import { BookMarked, Cpu, Dices, MessageSquare, Settings, Sliders, Sparkles } from "lucide-react";
import { OnboardingWizard } from "./components/onboarding/OnboardingWizard";
import { t } from "./i18n";
import { useAppStore } from "./stores/useAppStore";
import type { AppTab } from "./types/api";
import { EngineView } from "./views/EngineView";
import { LibraryView } from "./views/LibraryView";
import { PlayView } from "./views/PlayView";
import { SettingsView } from "./views/SettingsView";
import { StudioView } from "./views/StudioView";

export function App() {
  const {
    initialized,
    activeTab,
    experienceMode,
    lang,
    settings,
    localModels,
    remoteModels,
    favoriteModels,
    showOnboarding,
    toastMsg,
    initApp,
    setTab,
    setExperienceMode,
    saveSettingsPatch,
    openOnboarding,
  } = useAppStore();

  useEffect(() => {
    initApp();
  }, []);

  if (!initialized) {
    return (
      <div className="flex h-full items-center justify-center text-sm" style={{ color: "var(--text-secondary)" }}>
        正在加载 Easy-TRPG alpha 2.0...
      </div>
    );
  }

  const tabs: Array<{ id: AppTab; label: string; icon: React.ReactNode }> =
    experienceMode === "simple"
      ? [
          { id: "play", label: t(lang, "nav.play"), icon: <MessageSquare className="h-4 w-4" /> },
          { id: "library", label: t(lang, "nav.library"), icon: <BookMarked className="h-4 w-4" /> },
          { id: "engine", label: t(lang, "nav.engine"), icon: <Cpu className="h-4 w-4" /> },
        ]
      : [
          { id: "play", label: t(lang, "nav.play"), icon: <MessageSquare className="h-4 w-4" /> },
          { id: "library", label: t(lang, "nav.library.pro"), icon: <BookMarked className="h-4 w-4" /> },
          { id: "studio", label: t(lang, "nav.studio"), icon: <Sliders className="h-4 w-4" /> },
          { id: "engine", label: t(lang, "nav.engine.pro"), icon: <Cpu className="h-4 w-4" /> },
          { id: "settings", label: t(lang, "nav.settings"), icon: <Settings className="h-4 w-4" /> },
        ];

  const favSet = new Set(favoriteModels);
  const sortedRemote = [
    ...remoteModels.filter((id) => favSet.has(id)),
    ...remoteModels.filter((id) => !favSet.has(id)),
  ];
  const allModels = [
    ...localModels.map((m) => ({ id: m.id, label: `[本地] ${m.name}` })),
    ...sortedRemote.map((id) => ({ id, label: favSet.has(id) ? `★ ${id}` : id })),
  ];

  return (
    <div className="flex h-full flex-col">
      {/* Slim Top Navigation Bar */}
      <header
        className="flex h-11 md:h-12 shrink-0 items-center justify-between gap-2 border-b px-2.5 md:px-4 safe-pt"
        style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}
      >
        <div className="flex items-center gap-2 md:gap-4 shrink-0">
          <div className="flex items-center gap-2 font-semibold text-sm">
            <Dices className="h-5 w-5" style={{ color: "var(--accent)" }} />
            <span className="hidden sm:inline">Easy-TRPG</span>
          </div>

          <nav className="hidden md:flex items-center gap-1">
            {tabs.map((tb) => {
              const active = activeTab === tb.id;
              return (
                <button
                  key={tb.id}
                  type="button"
                  onClick={() => setTab(tb.id)}
                  className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition"
                  style={{
                    background: active ? "var(--accent-soft)" : "transparent",
                    color: active ? "var(--accent)" : "var(--text-secondary)",
                  }}
                >
                  {tb.icon}
                  <span>{tb.label}</span>
                </button>
              );
            })}
          </nav>
        </div>

        <div className="flex flex-1 md:flex-initial items-center justify-end gap-1.5 sm:gap-2 min-w-0 text-xs">
          <select
            value={settings?.model || ""}
            onChange={(e) => saveSettingsPatch({ model: e.target.value })}
            className="block min-w-0 flex-1 max-w-[190px] sm:flex-initial sm:w-auto sm:max-w-[200px] rounded-lg border px-2 sm:px-2.5 py-1 text-xs outline-none"
            style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
          >
            <option value="">-- 选择模型 --</option>
            {allModels.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>

          <button
            type="button"
            onClick={openOnboarding}
            title="向导配置"
            className="inline-flex shrink-0 items-center gap-1 rounded-lg border px-2 sm:px-2.5 py-1"
            style={{ borderColor: "var(--border-subtle)", color: "var(--text-secondary)" }}
          >
            <Sparkles className="h-3.5 w-3.5" style={{ color: "var(--accent)" }} />
            <span className="hidden sm:inline">向导</span>
          </button>

          <button
            type="button"
            onClick={() => setExperienceMode(experienceMode === "simple" ? "pro" : "simple")}
            className="shrink-0 whitespace-nowrap rounded-lg border px-2 sm:px-2.5 py-1 font-medium"
            style={{
              borderColor: experienceMode === "pro" ? "var(--accent)" : "var(--border-subtle)",
              background: experienceMode === "pro" ? "var(--accent-soft)" : "var(--bg-input)",
              color: experienceMode === "pro" ? "var(--accent)" : "var(--text-secondary)",
            }}
          >
            <span className="sm:hidden">{experienceMode === "simple" ? "简单" : "专业"}</span>
            <span className="hidden sm:inline">
              {experienceMode === "simple" ? t(lang, "mode.simple") : t(lang, "mode.pro")}
            </span>
          </button>
        </div>
      </header>

      {/* Active Workspace */}
      <main className="flex-1 min-h-0 overflow-hidden">
        {activeTab === "play" && <PlayView />}
        {activeTab === "library" && <LibraryView />}
        {activeTab === "studio" && <StudioView />}
        {activeTab === "engine" && <EngineView />}
        {activeTab === "settings" && <SettingsView />}
      </main>

      {/* Mobile Bottom Navigation */}
      <nav
        className="md:hidden flex shrink-0 items-center justify-around border-t px-1 safe-pb"
        style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}
      >
        {tabs.map((tb) => {
          const active = activeTab === tb.id;
          return (
            <button
              key={tb.id}
              type="button"
              onClick={() => setTab(tb.id)}
              className="flex flex-1 flex-col items-center justify-center gap-0.5 py-1.5 text-[10px] font-medium transition"
              style={{
                color: active ? "var(--accent)" : "var(--text-secondary)",
              }}
            >
              <span
                className="flex items-center justify-center rounded-full px-3 py-0.5"
                style={{ background: active ? "var(--accent-soft)" : "transparent" }}
              >
                {tb.icon}
              </span>
              <span className="truncate leading-tight">{tb.label}</span>
            </button>
          );
        })}
      </nav>

      {showOnboarding && <OnboardingWizard />}

      {toastMsg && (
        <div
          className="fixed bottom-16 md:bottom-5 left-3 right-3 sm:left-auto sm:right-5 z-50 text-center sm:text-left rounded-xl border px-4 py-2 text-xs font-medium shadow-lg"
          style={{
            background: "var(--bg-elevated)",
            borderColor: "var(--accent)",
            color: "var(--text-primary)",
          }}
        >
          {toastMsg}
        </div>
      )}
    </div>
  );
}
export default App;
