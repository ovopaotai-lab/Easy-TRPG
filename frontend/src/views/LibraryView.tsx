import React, { useState } from "react";
import { Check, Download, Image as ImageIcon, Pencil, Play, Plus, Trash2, Upload, User } from "lucide-react";
import { apiFetch } from "../api/client";
import { CharacterCardEditorModal, ProjectEditorModal } from "../components/library/LibraryEditors";
import { useAppStore } from "../stores/useAppStore";
import type { CharacterCard, ProjectData } from "../types/api";

const CORE_DEFAULT_PROJECT_IDS = new Set(["proj_fast_trpg", "proj_default", "proj_free_chat"]);

export function LibraryView() {
  const {
    exploreApps,
    projects,
    cards,
    personas,
    experienceMode,
    installExploreCampaign,
    selectProject,
    refreshProjectsAndExplore,
    setTab,
    notify,
  } = useAppStore();

  const [subTab, setSubTab] = useState<"featured" | "mine" | "cards" | "personas" | "gallery">("featured");
  const [editMode, setEditMode] = useState(false);
  const [editingProject, setEditingProject] = useState<{ data: Partial<ProjectData>; isNew?: boolean } | null>(null);
  const [editingCard, setEditingCard] = useState<{ data: Partial<CharacterCard>; isNew?: boolean } | null>(null);
  const [gallery, setGallery] = useState<any[]>([]);
  const [newPersonaName, setNewPersonaName] = useState("");
  const [newPersonaDesc, setNewPersonaDesc] = useState("");

  const reloadCards = async () => {
    const list = await apiFetch<CharacterCard[]>("/api/character_cards");
    useAppStore.setState({ cards: list });
  };

  const handleDeleteProject = async (projectId: string, projectName: string) => {
    if (!window.confirm(`确定删除剧本「${projectName}」？该操作不可恢复。`)) return;
    await apiFetch(`/api/projects/${projectId}`, { method: "DELETE" });
    await refreshProjectsAndExplore();
    notify(`已删除剧本「${projectName}」`);
  };

  const handleDeleteCard = async (cardId: string, cardName: string) => {
    if (!window.confirm(`确定删除角色卡「${cardName}」？`)) return;
    await apiFetch(`/api/character_cards/${cardId}`, { method: "DELETE" });
    await reloadCards();
    notify(`已删除角色卡「${cardName}」`);
  };

  const loadGallery = async () => {
    const items = await apiFetch<any[]>("/api/gallery");
    setGallery(items || []);
  };

  const handleImportGameCard = async (ev: React.ChangeEvent<HTMLInputElement>) => {
    const file = ev.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    const res = await apiFetch<any>("/api/projects/import_card", { method: "POST", body: fd });
    await refreshProjectsAndExplore();
    notify(`已导入剧本「${res.project.name}」`);
  };

  const handleImportCharCard = async (ev: React.ChangeEvent<HTMLInputElement>) => {
    const file = ev.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    const res = await apiFetch<any>("/api/character_cards/import", { method: "POST", body: fd });
    const list = await apiFetch<any[]>("/api/character_cards");
    useAppStore.setState({ cards: list });
    notify(`已导入角色卡「${res.card.name}」`);
  };

  const handleCreatePersona = async () => {
    if (!newPersonaName.trim()) return;
    await apiFetch("/api/personas", {
      method: "POST",
      body: JSON.stringify({ name: newPersonaName.trim(), description: newPersonaDesc.trim(), is_default: false }),
    });
    const list = await apiFetch<any>("/api/personas");
    useAppStore.setState({ personas: list.personas || [] });
    setNewPersonaName("");
    setNewPersonaDesc("");
    notify("人设已保存");
  };

  return (
    <div className="h-full overflow-y-auto p-3 sm:p-6">
      <div className="mx-auto max-w-5xl space-y-4 sm:space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-2.5 sm:gap-3">
          <div className="flex flex-wrap gap-1.5">
            {(
              [
                ["featured", "精选剧本"],
                ["mine", "我的剧本"],
                ["cards", "角色卡"],
                ...(experienceMode === "pro"
                  ? [
                      ["personas", "玩家人设"],
                      ["gallery", "素材图库"],
                    ]
                  : []),
              ] as Array<[typeof subTab, string]>
            ).map(([k, lbl]) => (
              <button
                key={k}
                type="button"
                onClick={() => {
                  setSubTab(k);
                  if (k === "gallery") loadGallery();
                }}
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

          <div className="flex flex-wrap items-center gap-2 text-xs">
            {editMode && (subTab === "mine" || subTab === "featured") && (
              <button
                type="button"
                onClick={() => setEditingProject({ data: { name: "", category: "跑团", ruleset: "d20" }, isNew: true })}
                className="inline-flex items-center gap-1 rounded-lg px-2.5 sm:px-3 py-1.5 font-medium"
                style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
              >
                <Plus className="h-3.5 w-3.5" />
                新建剧本
              </button>
            )}
            {editMode && subTab === "cards" && (
              <button
                type="button"
                onClick={() => setEditingCard({ data: { name: "", description: "", tags: [] }, isNew: true })}
                className="inline-flex items-center gap-1 rounded-lg px-2.5 sm:px-3 py-1.5 font-medium"
                style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
              >
                <Plus className="h-3.5 w-3.5" />
                新建角色卡
              </button>
            )}
            <button
              type="button"
              onClick={() => setEditMode((v) => !v)}
              className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 sm:px-3 py-1.5 font-medium transition"
              style={{
                borderColor: editMode ? "var(--accent)" : "var(--border-strong)",
                background: editMode ? "var(--accent-soft)" : "var(--bg-panel)",
                color: editMode ? "var(--accent)" : "var(--text-primary)",
              }}
            >
              {editMode ? <Check className="h-3.5 w-3.5" /> : <Pencil className="h-3.5 w-3.5" />}
              {editMode ? "退出编辑" : "编辑模式"}
            </button>
            <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 sm:px-3 py-1.5" style={{ borderColor: "var(--border-strong)" }}>
              <Upload className="h-3.5 w-3.5" />
              <span>导入酒馆卡<span className="hidden sm:inline"> (PNG/JSON)</span></span>
              <input type="file" accept=".png,.json" className="hidden" onChange={subTab === "cards" ? handleImportCharCard : handleImportGameCard} />
            </label>
          </div>
        </div>

        {subTab === "featured" && (
          <div className="grid grid-cols-1 gap-3 sm:gap-4 md:grid-cols-2">
            {exploreApps.map((app) => {
              const savedCopy = projects.find((p) => p.id === app.id);
              const displayApp = savedCopy || app;
              return (
                <div
                  key={app.id}
                  className="flex flex-col justify-between rounded-2xl border p-3 sm:p-4 transition"
                  style={{
                    borderColor: editMode ? "var(--accent)" : "var(--border-subtle)",
                    background: "var(--bg-panel)",
                  }}
                >
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <h3 className="text-base font-semibold truncate">{displayApp.name}</h3>
                        <span
                          className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium"
                          style={{ background: "var(--success-soft)", color: "var(--success)" }}
                        >
                          已安装
                        </span>
                      </div>
                      <span className="shrink-0 rounded-full px-2.5 py-0.5 text-[11px]" style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>
                        {displayApp.category} · {displayApp.ruleset?.toUpperCase() || "D20"}
                      </span>
                    </div>
                    <p className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                      {displayApp.description}
                    </p>
                    <div className="flex flex-wrap gap-1 pt-1">
                      {displayApp.tags?.map((tg) => (
                        <span key={tg} className="rounded px-2 py-0.5 text-[10px]" style={{ background: "var(--bg-elevated)", color: "var(--text-muted)" }}>
                          {tg}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t pt-3 text-xs" style={{ borderColor: "var(--border-subtle)" }}>
                    <span style={{ color: "var(--text-muted)" }}>
                      世界书 {displayApp.world_book?.length || 0} 条 · 角色卡 {app.bundled_cards?.length || 0} 张
                    </span>
                    <div className="flex items-center gap-1.5">
                      {editMode && (
                        <>
                          <button
                            type="button"
                            onClick={() => setEditingProject({ data: displayApp })}
                            className="inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 font-medium"
                            style={{ borderColor: "var(--border-strong)", color: "var(--text-primary)" }}
                          >
                            <Pencil className="h-3 w-3" />
                            编辑
                          </button>
                          {savedCopy && (
                            <button
                              type="button"
                              onClick={() => handleDeleteProject(savedCopy.id, savedCopy.name)}
                              className="inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 font-medium"
                              style={{ borderColor: "var(--danger)", color: "var(--danger)" }}
                            >
                              <Trash2 className="h-3 w-3" />
                              删除
                            </button>
                          )}
                        </>
                      )}
                      <button
                        type="button"
                        onClick={() => installExploreCampaign(app.id)}
                        className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 font-medium"
                        style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
                      >
                        <Play className="h-3.5 w-3.5" />
                        开始游玩
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {subTab === "mine" && (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {projects.map((p) => {
              const isCore = CORE_DEFAULT_PROJECT_IDS.has(p.id);
              return (
                <div
                  key={p.id}
                  className="flex flex-col justify-between rounded-xl border p-3 sm:p-4 transition"
                  style={{
                    borderColor: editMode ? "var(--accent)" : "var(--border-subtle)",
                    background: "var(--bg-panel)",
                  }}
                >
                  <div>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold truncate">{p.name}</span>
                      <div className="flex items-center gap-1.5 shrink-0">
                        {editMode && isCore && (
                          <span className="rounded px-1.5 py-0.5 text-[10px]" style={{ background: "var(--bg-elevated)", color: "var(--text-muted)" }}>
                            内置
                          </span>
                        )}
                        <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                          {p.category}
                        </span>
                      </div>
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs" style={{ color: "var(--text-secondary)" }}>
                      {p.description || "自定义跑团剧本"}
                    </p>
                  </div>
                  <div className="mt-4 flex flex-wrap items-center gap-1.5 text-[11px]">
                    <button
                      type="button"
                      onClick={async () => {
                        await selectProject(p.id);
                        setTab("play");
                      }}
                      className="rounded-lg px-2.5 py-1 font-medium"
                      style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
                    >
                      游玩
                    </button>
                    {editMode ? (
                      <>
                        <button
                          type="button"
                          onClick={() => setEditingProject({ data: p })}
                          className="inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 font-medium"
                          style={{ borderColor: "var(--border-strong)", color: "var(--text-primary)" }}
                        >
                          <Pencil className="h-3 w-3" />
                          编辑
                        </button>
                        {!isCore && (
                          <button
                            type="button"
                            onClick={() => handleDeleteProject(p.id, p.name)}
                            className="inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 font-medium"
                            style={{ borderColor: "var(--danger)", color: "var(--danger)" }}
                          >
                            <Trash2 className="h-3 w-3" />
                            删除
                          </button>
                        )}
                      </>
                    ) : (
                      <>
                        <a
                          href={`/api/projects/${p.id}/export_card?format=png`}
                          className="inline-flex items-center gap-1 rounded-lg border px-2 py-1"
                          style={{ borderColor: "var(--border-subtle)", color: "var(--text-secondary)" }}
                        >
                          <Download className="h-3 w-3" />
                          PNG
                        </a>
                        <a
                          href={`/api/projects/${p.id}/export_card?format=json`}
                          className="inline-flex items-center gap-1 rounded-lg border px-2 py-1"
                          style={{ borderColor: "var(--border-subtle)", color: "var(--text-secondary)" }}
                        >
                          JSON
                        </a>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {subTab === "cards" && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
            {cards.map((c) => (
              <div
                key={c.id}
                className="flex flex-col justify-between rounded-xl border p-3 sm:p-4 space-y-2 transition"
                style={{
                  borderColor: editMode ? "var(--accent)" : "var(--border-subtle)",
                  background: "var(--bg-panel)",
                }}
              >
                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="inline-flex items-center gap-1.5 text-sm font-semibold truncate">
                      <User className="h-4 w-4 shrink-0" style={{ color: "var(--accent)" }} />
                      <span className="truncate">{c.name}</span>
                    </span>
                  </div>
                  <p className="line-clamp-3 text-xs" style={{ color: "var(--text-secondary)" }}>
                    {c.description || c.personality || "暂无简介"}
                  </p>
                </div>
                {editMode && (
                  <div className="flex items-center gap-1.5 border-t pt-2.5 text-[11px]" style={{ borderColor: "var(--border-subtle)" }}>
                    <button
                      type="button"
                      onClick={() => setEditingCard({ data: c })}
                      className="inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 font-medium"
                      style={{ borderColor: "var(--border-strong)", color: "var(--text-primary)" }}
                    >
                      <Pencil className="h-3 w-3" />
                      编辑
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDeleteCard(c.id, c.name)}
                      className="inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 font-medium"
                      style={{ borderColor: "var(--danger)", color: "var(--danger)" }}
                    >
                      <Trash2 className="h-3 w-3" />
                      删除
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {subTab === "personas" && (
          <div className="space-y-4">
            <div className="rounded-xl border p-4 space-y-2" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}>
              <div className="text-xs font-semibold">新增玩家人设</div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                <input
                  value={newPersonaName}
                  onChange={(e) => setNewPersonaName(e.target.value)}
                  placeholder="人设名称（如 失忆游侠）"
                  className="rounded-lg border px-3 py-1.5 text-xs outline-none"
                  style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
                />
                <input
                  value={newPersonaDesc}
                  onChange={(e) => setNewPersonaDesc(e.target.value)}
                  placeholder="外貌、背景与性格简述..."
                  className="sm:col-span-2 rounded-lg border px-3 py-1.5 text-xs outline-none"
                  style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
                />
              </div>
              <button
                type="button"
                onClick={handleCreatePersona}
                className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium"
                style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
              >
                <Plus className="h-3.5 w-3.5" />
                保存人设
              </button>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {personas.map((p) => (
                <div key={p.id} className="rounded-xl border p-3.5 flex items-start justify-between" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}>
                  <div>
                    <div className="text-sm font-medium">{p.name}</div>
                    <p className="mt-1 text-xs" style={{ color: "var(--text-secondary)" }}>{p.description}</p>
                  </div>
                  <button
                    type="button"
                    onClick={async () => {
                      await apiFetch(`/api/personas/${p.id}`, { method: "DELETE" });
                      const list = await apiFetch<any>("/api/personas");
                      useAppStore.setState({ personas: list.personas || [] });
                    }}
                    style={{ color: "var(--text-muted)" }}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {subTab === "gallery" && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 md:grid-cols-5">
            {gallery.length === 0 ? (
              <div className="col-span-full py-12 text-center text-xs" style={{ color: "var(--text-muted)" }}>
                <ImageIcon className="mx-auto mb-2 h-6 w-6 opacity-50" />
                图库暂无素材
              </div>
            ) : (
              gallery.map((g) => (
                <div key={g.id} className="overflow-hidden rounded-xl border" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}>
                  {g.media_type === "video" || String(g.id).startsWith("vid_") ? (
                    <video
                      src={g.url}
                      poster={g.thumb_url}
                      controls
                      muted
                      preload="metadata"
                      className="h-32 w-full bg-black object-cover"
                    />
                  ) : (
                    <img src={g.thumb_url || g.url} alt={g.filename} className="h-32 w-full object-cover" />
                  )}
                  <div className="flex items-center justify-between px-2 py-1 text-[10px]" style={{ color: "var(--text-secondary)" }}>
                    <span className="truncate">{g.filename}</span>
                    <button
                      type="button"
                      onClick={async () => {
                        await apiFetch(`/api/gallery/${g.id}`, { method: "DELETE" });
                        loadGallery();
                      }}
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {editingProject && (
        <ProjectEditorModal
          project={editingProject.data}
          isNew={editingProject.isNew}
          onClose={() => setEditingProject(null)}
          onSaved={async (saved) => {
            await refreshProjectsAndExplore();
            notify(`已保存剧本「${saved.name}」`);
          }}
        />
      )}

      {editingCard && (
        <CharacterCardEditorModal
          card={editingCard.data}
          isNew={editingCard.isNew}
          onClose={() => setEditingCard(null)}
          onSaved={async () => {
            await reloadCards();
            notify("角色卡已保存");
          }}
        />
      )}
    </div>
  );
}
