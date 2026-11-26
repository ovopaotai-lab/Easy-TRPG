import React, { useEffect, useState } from "react";
import { Plus, Save, Sparkles, Trash2, Upload } from "lucide-react";
import { apiFetch } from "../api/client";
import { useAppStore } from "../stores/useAppStore";
import type { ProjectData, WorldbookEntry } from "../types/api";

export function StudioView() {
  const { projects, activeProjectId, refreshProjectsAndExplore, selectProject, notify } = useAppStore();
  const [subTab, setSubTab] = useState<"guided" | "editor" | "worldbook" | "rules" | "presets">("guided");
  const [idea, setIdea] = useState("");
  const [generating, setGenerating] = useState(false);

  const currentProj = projects.find((p) => p.id === activeProjectId) || projects[0];
  const [draft, setDraft] = useState<ProjectData | null>(currentProj || null);

  useEffect(() => {
    if (currentProj) setDraft(JSON.parse(JSON.stringify(currentProj)));
  }, [activeProjectId, projects.length]);

  const handleAiGenerate = async () => {
    if (!idea.trim()) return;
    setGenerating(true);
    try {
      const res = await apiFetch<any>("/api/ai/generate_game_card", {
        method: "POST",
        body: JSON.stringify({ idea }),
      });
      await apiFetch("/api/projects", { method: "POST", body: JSON.stringify(res.project) });
      await refreshProjectsAndExplore();
      await selectProject(res.project.id);
      setDraft(res.project);
      setSubTab("editor");
      notify(`已生成剧本「${res.project.name}」`);
    } catch (err: any) {
      notify(err?.message || "生成失败");
    } finally {
      setGenerating(false);
    }
  };

  const handleSaveDraft = async () => {
    if (!draft) return;
    const res = await apiFetch<any>("/api/projects", { method: "POST", body: JSON.stringify(draft) });
    await refreshProjectsAndExplore();
    setDraft(res.project);
    notify("剧本设置已保存");
  };

  const handleImportSTPreset = async (ev: React.ChangeEvent<HTMLInputElement>) => {
    const file = ev.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    const parsed = JSON.parse(text);
    const res = await apiFetch<any>("/api/presets/import_st", {
      method: "POST",
      body: JSON.stringify({ preset: parsed, name: file.name.replace(/\.json$/i, "") }),
    });
    const list = await apiFetch<any>("/api/presets");
    useAppStore.setState({ presets: list.presets || [] });
    notify(`已导入预设「${res.preset.name}」`);
  };

  const addWorldbookRow = () => {
    if (!draft) return;
    const next: WorldbookEntry = {
      id: `wb_${Date.now()}`,
      name: "新词条",
      group: "核心世界观",
      enabled: true,
      constant: false,
      keys: ["关键词"],
      match_type: "OR",
      key_region: 6,
      value_region: "System",
      sort: (draft.world_book?.length || 0) * 10 + 10,
      depth: 5,
      probability: 100,
      content: "",
    };
    setDraft({ ...draft, world_book: [...(draft.world_book || []), next] });
  };

  return (
    <div className="h-full overflow-y-auto p-3 sm:p-6">
      <div className="mx-auto max-w-4xl space-y-4 sm:space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-1.5">
            {(
              [
                ["guided", "简易创作"],
                ["editor", "高级设定"],
                ["worldbook", "世界书"],
                ["rules", "跑团规则"],
                ["presets", "预设导入"],
              ] as Array<[typeof subTab, string]>
            ).map(([k, lbl]) => (
              <button
                key={k}
                type="button"
                onClick={() => setSubTab(k)}
                className="rounded-lg border px-2.5 sm:px-3 py-1.5 text-xs font-medium"
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

          {draft && subTab !== "guided" && (
            <button
              type="button"
              onClick={handleSaveDraft}
              className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-xs font-medium"
              style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
            >
              <Save className="h-3.5 w-3.5" />
              保存剧本
            </button>
          )}
        </div>

        {subTab === "guided" && (
          <div className="rounded-2xl border p-3.5 sm:p-5 space-y-3" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}>
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Sparkles className="h-4 w-4" style={{ color: "var(--accent)" }} />
              一句话生成完整跑团剧本（含世界书与开场白）
            </div>
            <textarea
              value={idea}
              onChange={(e) => setIdea(e.target.value)}
              rows={4}
              placeholder="例如：1935年上海滩雨夜侦探社，主角是退伍法医，搭档是能看见死者残影的戏班花旦..."
              className="w-full rounded-xl border p-3 text-xs outline-none"
              style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
            />
            <button
              type="button"
              disabled={generating}
              onClick={handleAiGenerate}
              className="rounded-lg px-4 py-2 text-xs font-medium disabled:opacity-50"
              style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
            >
              {generating ? "生成中..." : "AI 一键创作剧本"}
            </button>
          </div>
        )}

        {subTab === "editor" && draft && (
          <div className="rounded-2xl border p-3.5 sm:p-5 space-y-3 text-xs" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="space-y-1">
                <span style={{ color: "var(--text-secondary)" }}>剧本名称</span>
                <input
                  value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 outline-none"
                  style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
                />
              </label>
              <label className="space-y-1">
                <span style={{ color: "var(--text-secondary)" }}>分类</span>
                <input
                  value={draft.category}
                  onChange={(e) => setDraft({ ...draft, category: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 outline-none"
                  style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
                />
              </label>
            </div>
            <label className="block space-y-1">
              <span style={{ color: "var(--text-secondary)" }}>系统提示词（静态前缀，自动享 KV 缓存）</span>
              <textarea
                value={draft.system_prompt}
                onChange={(e) => setDraft({ ...draft, system_prompt: e.target.value })}
                rows={10}
                className="w-full rounded-xl border p-3 font-mono text-xs outline-none"
                style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
              />
            </label>
            <label className="block space-y-1">
              <span style={{ color: "var(--text-secondary)" }}>后置指令 (Suffix)</span>
              <textarea
                value={draft.suffix}
                onChange={(e) => setDraft({ ...draft, suffix: e.target.value })}
                rows={3}
                className="w-full rounded-xl border p-3 text-xs outline-none"
                style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
              />
            </label>
          </div>
        )}

        {subTab === "worldbook" && draft && (
          <div className="space-y-3">
            <button
              type="button"
              onClick={addWorldbookRow}
              className="inline-flex items-center gap-1 rounded-lg border px-3 py-1.5 text-xs"
              style={{ borderColor: "var(--border-strong)" }}
            >
              <Plus className="h-3.5 w-3.5" />
              新增世界书词条
            </button>
            {(draft.world_book || []).map((wb, idx) => (
              <div key={wb.id || idx} className="rounded-xl border p-3 sm:p-4 space-y-2 text-xs" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <input
                    value={wb.name}
                    onChange={(e) => {
                      const arr = [...draft.world_book];
                      arr[idx] = { ...wb, name: e.target.value };
                      setDraft({ ...draft, world_book: arr });
                    }}
                    className="min-w-[140px] flex-1 sm:flex-initial rounded border px-2.5 py-1 font-semibold outline-none"
                    style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
                  />
                  <div className="flex items-center gap-3">
                    <label className="inline-flex items-center gap-1">
                      <input
                        type="checkbox"
                        checked={Boolean(wb.constant)}
                        onChange={(e) => {
                          const arr = [...draft.world_book];
                          arr[idx] = { ...wb, constant: e.target.checked };
                          setDraft({ ...draft, world_book: arr });
                        }}
                      />
                      常驻(KV前缀)
                    </label>
                    <button
                      type="button"
                      onClick={() => {
                        const arr = draft.world_book.filter((_, i) => i !== idx);
                        setDraft({ ...draft, world_book: arr });
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5" style={{ color: "var(--text-muted)" }} />
                    </button>
                  </div>
                </div>
                {!wb.constant && (
                  <input
                    value={(wb.keys || []).join(", ")}
                    onChange={(e) => {
                      const arr = [...draft.world_book];
                      arr[idx] = { ...wb, keys: e.target.value.split(/[,，]/).map((s) => s.trim()).filter(Boolean) };
                      setDraft({ ...draft, world_book: arr });
                    }}
                    placeholder="触发关键词（逗号分隔）"
                    className="w-full rounded border px-2.5 py-1 outline-none"
                    style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
                  />
                )}
                <textarea
                  value={wb.content}
                  onChange={(e) => {
                    const arr = [...draft.world_book];
                    arr[idx] = { ...wb, content: e.target.value };
                    setDraft({ ...draft, world_book: arr });
                  }}
                  rows={3}
                  className="w-full rounded-lg border p-2 outline-none"
                  style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
                />
              </div>
            ))}
          </div>
        )}

        {subTab === "rules" && draft && (
          <div className="rounded-2xl border p-3.5 sm:p-5 space-y-3 text-xs" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}>
            <label className="block space-y-1">
              <span style={{ color: "var(--text-secondary)" }}>检定骰子规则体系</span>
              <select
                value={draft.ruleset || "d20"}
                onChange={(e) => setDraft({ ...draft, ruleset: e.target.value as any })}
                className="w-full sm:w-auto rounded-lg border px-3 py-2"
                style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
              >
                <option value="d20">D20 (标准奇幻 / 仙侠)</option>
                <option value="d100">CoC D100 (克苏鲁 / 悬疑)</option>
                <option value="2d6">PbtA 2D6 (赛博 / 强叙事代价)</option>
                <option value="narrative">纯叙事（无骰子判定）</option>
              </select>
            </label>
            <label className="inline-flex items-center gap-2">
              <input
                type="checkbox"
                checked={Boolean(draft.cot_enabled)}
                onChange={(e) => setDraft({ ...draft, cot_enabled: e.target.checked })}
              />
              启用导演思考推演 (&lt;think&gt;)
            </label>
          </div>
        )}

        {subTab === "presets" && (
          <div className="rounded-2xl border p-3.5 sm:p-5 space-y-3 text-xs" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold">导入 SillyTavern Chat Completion 预设 (JSON)</span>
              <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border px-3 py-1.5" style={{ borderColor: "var(--border-strong)" }}>
                <Upload className="h-3.5 w-3.5" />
                选择 JSON 文件
                <input type="file" accept=".json" className="hidden" onChange={handleImportSTPreset} />
              </label>
            </div>
            <div className="space-y-2">
              {useAppStore.getState().presets.map((pr) => (
                <div key={pr.id} className="flex items-center justify-between rounded-lg border px-3 py-2" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-input)" }}>
                  <span>{pr.name}</span>
                  <span style={{ color: "var(--text-muted)" }}>{pr.source || "builtin"}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
