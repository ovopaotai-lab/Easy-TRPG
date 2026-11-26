import React, { useState } from "react";
import { Plus, Save, Trash2, X } from "lucide-react";
import { apiFetch } from "../../api/client";
import type { CharacterCard, ProjectData, WorldbookEntry } from "../../types/api";

interface ProjectEditorModalProps {
  project: Partial<ProjectData>;
  isNew?: boolean;
  onClose: () => void;
  onSaved: (saved: ProjectData) => Promise<void> | void;
}

export function ProjectEditorModal({ project, isNew, onClose, onSaved }: ProjectEditorModalProps) {
  const [name, setName] = useState(project.name || "");
  const [category, setCategory] = useState(project.category || "跑团");
  const [ruleset, setRuleset] = useState<ProjectData["ruleset"]>(project.ruleset || "d20");
  const [description, setDescription] = useState(project.description || "");
  const [systemPrompt, setSystemPrompt] = useState(project.system_prompt || "");
  const [openingStatement, setOpeningStatement] = useState(project.opening_statement || "");
  const [prefix, setPrefix] = useState(project.prefix || "");
  const [suffix, setSuffix] = useState(project.suffix || "");
  const [worldBook, setWorldBook] = useState<WorldbookEntry[]>(
    Array.isArray(project.world_book) ? project.world_book.map((w) => ({ ...w })) : []
  );
  const [saving, setSaving] = useState(false);

  const handleAddWb = () => {
    setWorldBook((prev) => [
      ...prev,
      {
        id: `wb_${Date.now()}_${prev.length}`,
        name: "新词条",
        group: "核心世界观",
        enabled: true,
        constant: false,
        keys: [],
        match_type: "OR",
        key_region: 6,
        value_region: "System",
        sort: (prev.length + 1) * 10,
        depth: 5,
        probability: 100,
        content: "",
      },
    ]);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try {
      const payload: Partial<ProjectData> = {
        ...project,
        name: name.trim(),
        category: category.trim() || "跑团",
        ruleset,
        description: description.trim(),
        system_prompt: systemPrompt,
        opening_statement: openingStatement,
        prefix,
        suffix,
        world_book: worldBook,
      };
      if (isNew) {
        delete payload.id;
      }
      const res = await apiFetch<{ status: string; project: ProjectData }>("/api/projects", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await onSaved(res.project);
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-2.5 sm:p-4 backdrop-blur-sm">
      <form
        onSubmit={handleSubmit}
        className="flex max-h-[92dvh] w-full max-w-2xl flex-col rounded-2xl border shadow-2xl"
        style={{ background: "var(--bg-panel)", borderColor: "var(--border-strong)" }}
      >
        <div
          className="flex items-center justify-between border-b px-3.5 sm:px-5 py-3 sm:py-3.5"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <h3 className="text-sm font-semibold">{isNew ? "新建剧本" : `编辑剧本 · ${project.name || ""}`}</h3>
          <button type="button" onClick={onClose} className="rounded p-1 hover:opacity-80" style={{ color: "var(--text-muted)" }}>
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-3.5 sm:p-5 text-xs">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <label className="space-y-1 sm:col-span-1">
              <span style={{ color: "var(--text-secondary)" }}>剧本名称</span>
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="输入剧本名"
                className="w-full rounded-lg border px-2.5 py-1.5 outline-none"
                style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
              />
            </label>
            <label className="space-y-1">
              <span style={{ color: "var(--text-secondary)" }}>分类</span>
              <input
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="跑团 / 奇幻冒险 / 悬疑"
                className="w-full rounded-lg border px-2.5 py-1.5 outline-none"
                style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
              />
            </label>
            <label className="space-y-1">
              <span style={{ color: "var(--text-secondary)" }}>规则体系</span>
              <select
                value={ruleset || "d20"}
                onChange={(e) => setRuleset(e.target.value as ProjectData["ruleset"])}
                className="w-full rounded-lg border px-2.5 py-1.5 outline-none"
                style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
              >
                <option value="d20">D20</option>
                <option value="d100">CoC D100</option>
                <option value="2d6">PbtA 2d6</option>
                <option value="narrative">纯叙事</option>
              </select>
            </label>
          </div>

          <label className="block space-y-1">
            <span style={{ color: "var(--text-secondary)" }}>剧本简介</span>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="一句话介绍背景与玩法..."
              className="w-full rounded-lg border px-2.5 py-1.5 outline-none"
              style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
            />
          </label>

          <label className="block space-y-1">
            <span style={{ color: "var(--text-secondary)" }}>主持人系统提示词</span>
            <textarea
              rows={5}
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="世界观、文风约束与 DM 裁决规则..."
              className="w-full rounded-lg border p-2.5 outline-none"
              style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
            />
          </label>

          <label className="block space-y-1">
            <span style={{ color: "var(--text-secondary)" }}>默认开场白</span>
            <textarea
              rows={3}
              value={openingStatement}
              onChange={(e) => setOpeningStatement(e.target.value)}
              placeholder="新建对话时的自动首句开场白（可选）..."
              className="w-full rounded-lg border p-2.5 outline-none"
              style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
            />
          </label>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="block space-y-1">
              <span style={{ color: "var(--text-secondary)" }}>玩家行动前置词</span>
              <input
                value={prefix}
                onChange={(e) => setPrefix(e.target.value)}
                className="w-full rounded-lg border px-2.5 py-1.5 outline-none"
                style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
              />
            </label>
            <label className="block space-y-1">
              <span style={{ color: "var(--text-secondary)" }}>玩家行动后置词</span>
              <input
                value={suffix}
                onChange={(e) => setSuffix(e.target.value)}
                className="w-full rounded-lg border px-2.5 py-1.5 outline-none"
                style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
              />
            </label>
          </div>

          <div className="space-y-2 rounded-xl border p-3" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-elevated)" }}>
            <div className="flex items-center justify-between">
              <span className="font-semibold">世界书词条 ({worldBook.length})</span>
              <button
                type="button"
                onClick={handleAddWb}
                className="inline-flex items-center gap-1 rounded-lg border px-2 py-1"
                style={{ borderColor: "var(--border-strong)", color: "var(--accent)" }}
              >
                <Plus className="h-3 w-3" />
                新增词条
              </button>
            </div>
            {worldBook.length === 0 ? (
              <div style={{ color: "var(--text-muted)" }}>暂无世界书词条，可点击右上角新增。</div>
            ) : (
              <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                {worldBook.map((wb, idx) => (
                  <div
                    key={wb.id || idx}
                    className="space-y-1.5 rounded-lg border p-2.5"
                    style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}
                  >
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={wb.enabled !== false}
                        onChange={(e) =>
                          setWorldBook((prev) => prev.map((it, i) => (i === idx ? { ...it, enabled: e.target.checked } : it)))
                        }
                      />
                      <input
                        value={wb.name}
                        onChange={(e) =>
                          setWorldBook((prev) => prev.map((it, i) => (i === idx ? { ...it, name: e.target.value } : it)))
                        }
                        placeholder="词条名"
                        className="w-28 rounded border px-2 py-0.5 outline-none"
                        style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
                      />
                      <input
                        value={(wb.keys || []).join(", ")}
                        onChange={(e) =>
                          setWorldBook((prev) =>
                            prev.map((it, i) =>
                              i === idx
                                ? {
                                    ...it,
                                    keys: e.target.value
                                      .split(/[,，]/)
                                      .map((s) => s.trim())
                                      .filter(Boolean),
                                  }
                                : it
                            )
                          )
                        }
                        placeholder="触发关键词（逗号分隔，空则仅常驻）"
                        className="flex-1 rounded border px-2 py-0.5 outline-none"
                        style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
                      />
                      <label className="inline-flex items-center gap-1 text-[11px]" style={{ color: "var(--text-secondary)" }}>
                        <input
                          type="checkbox"
                          checked={Boolean(wb.constant)}
                          onChange={(e) =>
                            setWorldBook((prev) => prev.map((it, i) => (i === idx ? { ...it, constant: e.target.checked } : it)))
                          }
                        />
                        常驻
                      </label>
                      <button
                        type="button"
                        onClick={() => setWorldBook((prev) => prev.filter((_, i) => i !== idx))}
                        style={{ color: "var(--danger)" }}
                        title="删除词条"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    <textarea
                      rows={2}
                      value={wb.content || ""}
                      onChange={(e) =>
                        setWorldBook((prev) => prev.map((it, i) => (i === idx ? { ...it, content: e.target.value } : it)))
                      }
                      placeholder="触发后注入的内容..."
                      className="w-full rounded border px-2 py-1 outline-none"
                      style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
                    />
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t px-3.5 sm:px-5 py-3 text-xs" style={{ borderColor: "var(--border-subtle)" }}>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border px-3.5 py-1.5"
            style={{ borderColor: "var(--border-subtle)", color: "var(--text-secondary)" }}
          >
            取消
          </button>
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-lg px-4 py-1.5 font-medium disabled:opacity-50"
            style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
          >
            <Save className="h-3.5 w-3.5" />
            {saving ? "保存中..." : "保存剧本"}
          </button>
        </div>
      </form>
    </div>
  );
}

interface CharacterCardEditorModalProps {
  card: Partial<CharacterCard>;
  isNew?: boolean;
  onClose: () => void;
  onSaved: () => Promise<void> | void;
}

export function CharacterCardEditorModal({ card, isNew, onClose, onSaved }: CharacterCardEditorModalProps) {
  const [name, setName] = useState(card.name || "");
  const [tagsText, setTagsText] = useState((card.tags || []).join(", "));
  const [description, setDescription] = useState(card.description || "");
  const [personality, setPersonality] = useState(card.personality || "");
  const [scenario, setScenario] = useState(card.scenario || "");
  const [firstMes, setFirstMes] = useState(card.first_mes || "");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try {
      const tags = tagsText
        .split(/[,，]/)
        .map((s) => s.trim())
        .filter(Boolean);
      const body = {
        ...card,
        name: name.trim(),
        tags,
        description,
        personality,
        scenario,
        first_mes: firstMes,
      };
      if (isNew || !card.id) {
        delete body.id;
        await apiFetch("/api/character_cards", { method: "POST", body: JSON.stringify(body) });
      } else {
        await apiFetch(`/api/character_cards/${card.id}`, { method: "PUT", body: JSON.stringify(body) });
      }
      await onSaved();
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-2.5 sm:p-4 backdrop-blur-sm">
      <form
        onSubmit={handleSubmit}
        className="flex max-h-[92dvh] w-full max-w-lg flex-col rounded-2xl border shadow-2xl"
        style={{ background: "var(--bg-panel)", borderColor: "var(--border-strong)" }}
      >
        <div
          className="flex items-center justify-between border-b px-3.5 sm:px-5 py-3 sm:py-3.5"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <h3 className="text-sm font-semibold">{isNew ? "新建角色卡" : `编辑角色卡 · ${card.name || ""}`}</h3>
          <button type="button" onClick={onClose} className="rounded p-1 hover:opacity-80" style={{ color: "var(--text-muted)" }}>
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-3.5 sm:p-5 text-xs">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="space-y-1">
              <span style={{ color: "var(--text-secondary)" }}>角色名称</span>
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="输入角色名"
                className="w-full rounded-lg border px-2.5 py-1.5 outline-none"
                style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
              />
            </label>
            <label className="space-y-1">
              <span style={{ color: "var(--text-secondary)" }}>标签（逗号分隔）</span>
              <input
                value={tagsText}
                onChange={(e) => setTagsText(e.target.value)}
                placeholder="骑士, 队友, 银发"
                className="w-full rounded-lg border px-2.5 py-1.5 outline-none"
                style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
              />
            </label>
          </div>

          <label className="block space-y-1">
            <span style={{ color: "var(--text-secondary)" }}>角色设定</span>
            <textarea
              rows={4}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="外貌、身份、能力、秘密与行动动机..."
              className="w-full rounded-lg border p-2.5 outline-none"
              style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
            />
          </label>

          <label className="block space-y-1">
            <span style={{ color: "var(--text-secondary)" }}>性格特征</span>
            <textarea
              rows={2}
              value={personality}
              onChange={(e) => setPersonality(e.target.value)}
              className="w-full rounded-lg border p-2.5 outline-none"
              style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
            />
          </label>

          <label className="block space-y-1">
            <span style={{ color: "var(--text-secondary)" }}>所在背景 / 情景</span>
            <textarea
              rows={2}
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              className="w-full rounded-lg border p-2.5 outline-none"
              style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
            />
          </label>

          <label className="block space-y-1">
            <span style={{ color: "var(--text-secondary)" }}>开场白 / 典型台词</span>
            <textarea
              rows={2}
              value={firstMes}
              onChange={(e) => setFirstMes(e.target.value)}
              className="w-full rounded-lg border p-2.5 outline-none"
              style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
            />
          </label>
        </div>

        <div className="flex justify-end gap-2 border-t px-3.5 sm:px-5 py-3 text-xs" style={{ borderColor: "var(--border-subtle)" }}>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border px-3.5 py-1.5"
            style={{ borderColor: "var(--border-subtle)", color: "var(--text-secondary)" }}
          >
            取消
          </button>
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-lg px-4 py-1.5 font-medium disabled:opacity-50"
            style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
          >
            <Save className="h-3.5 w-3.5" />
            {saving ? "保存中..." : "保存角色卡"}
          </button>
        </div>
      </form>
    </div>
  );
}
