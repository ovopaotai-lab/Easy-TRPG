import React, { useEffect, useState } from "react";
import { BookOpen, GitBranch, Layers, Users, X } from "lucide-react";
import { apiFetch } from "../../api/client";
import { useAppStore } from "../../stores/useAppStore";
import { BranchTreePanel } from "./BranchTreePanel";
import { StateHudPanel } from "./StateHudPanel";

export function InspectorDrawer({ onClose }: { onClose?: () => void }) {
  const { activeChat, cards, experienceMode, selectChat, triggerGroupTurn, notify } = useAppStore();
  const [subTab, setSubTab] = useState<"state" | "tree" | "memory">("state");
  const [noteText, setNoteText] = useState("");
  const [noteDepth, setNoteDepth] = useState(1);
  const [promptLog, setPromptLog] = useState<any>(null);

  useEffect(() => {
    if (activeChat?.author_note) {
      setNoteText(activeChat.author_note.content || "");
      setNoteDepth(activeChat.author_note.depth ?? 1);
    }
  }, [activeChat?.id]);

  if (!activeChat) return null;

  const saveAuthorNote = async () => {
    await apiFetch(`/api/chats/${activeChat.id}/author_note`, {
      method: "PUT",
      body: JSON.stringify({ content: noteText, depth: noteDepth, role: "system", enabled: true }),
    });
    notify("导演备注已生效");
  };

  const toggleGroupMember = async (cardId: string) => {
    const gc = activeChat.group_config || { enabled: true, mode: "round_robin", members: [] };
    const exists = gc.members.find((m) => m.card_id === cardId);
    let nextMembers;
    if (exists) {
      nextMembers = gc.members.filter((m) => m.card_id !== cardId);
    } else {
      nextMembers = [...gc.members, { card_id: cardId, enabled: true, talkativeness: 0.7 }];
    }
    await apiFetch(`/api/chats/${activeChat.id}/group_config`, {
      method: "PUT",
      body: JSON.stringify({ enabled: nextMembers.length > 0, mode: "round_robin", members: nextMembers }),
    });
    await selectChat(activeChat.id);
  };

  const loadPromptLog = async () => {
    const res = await apiFetch<any>(`/api/chats/${activeChat.id}/prompt_log`);
    setPromptLog(res.prompt_log || {});
  };

  return (
    <div className="fixed inset-0 z-40 flex justify-end lg:static lg:inset-auto lg:z-auto lg:h-full">
      <div className="fixed inset-0 bg-black/60 lg:hidden" onClick={onClose} />
      <aside
        className="relative z-10 flex h-full w-[88vw] max-w-sm lg:w-80 shrink-0 flex-col border-l shadow-2xl lg:shadow-none"
        style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}
      >
        <div className="flex items-center border-b px-2 pt-2" style={{ borderColor: "var(--border-subtle)" }}>
          <button
            type="button"
            onClick={() => setSubTab("state")}
            className="flex-1 inline-flex items-center justify-center gap-1 border-b-2 pb-2 text-xs font-medium"
            style={{
              borderColor: subTab === "state" ? "var(--accent)" : "transparent",
              color: subTab === "state" ? "var(--accent)" : "var(--text-secondary)",
            }}
          >
            <Layers className="h-3.5 w-3.5" />
            状态
          </button>
          {experienceMode === "pro" && (
            <>
              <button
                type="button"
                onClick={() => setSubTab("tree")}
                className="flex-1 inline-flex items-center justify-center gap-1 border-b-2 pb-2 text-xs font-medium"
                style={{
                  borderColor: subTab === "tree" ? "var(--accent)" : "transparent",
                  color: subTab === "tree" ? "var(--accent)" : "var(--text-secondary)",
                }}
              >
                <GitBranch className="h-3.5 w-3.5" />
                分支树
              </button>
              <button
                type="button"
                onClick={() => setSubTab("memory")}
                className="flex-1 inline-flex items-center justify-center gap-1 border-b-2 pb-2 text-xs font-medium"
                style={{
                  borderColor: subTab === "memory" ? "var(--accent)" : "transparent",
                  color: subTab === "memory" ? "var(--accent)" : "var(--text-secondary)",
                }}
              >
                <BookOpen className="h-3.5 w-3.5" />
                记忆/群聊
              </button>
            </>
          )}
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="关闭面板"
              className="lg:hidden ml-1 mb-1.5 rounded-lg p-1.5 hover:opacity-80"
              style={{ color: "var(--text-muted)" }}
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

      <div className="flex-1 overflow-y-auto p-3">
        {subTab === "state" && <StateHudPanel state={activeChat.active_state} />}
        {subTab === "tree" && <BranchTreePanel />}
        {subTab === "memory" && (
          <div className="space-y-4 text-xs">
            <div className="space-y-1.5">
              <div className="font-semibold">作者注释 / 导演指令 (Author's Note)</div>
              <textarea
                value={noteText}
                onChange={(e) => setNoteText(e.target.value)}
                rows={3}
                placeholder="例如：接下来转为暴雨悬疑氛围，线索指向码头..."
                className="w-full rounded-lg border p-2 text-xs outline-none"
                style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
              />
              <div className="flex items-center justify-between gap-2">
                <label className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                  插入深度: {noteDepth}
                  <input
                    type="range"
                    min={0}
                    max={6}
                    value={noteDepth}
                    onChange={(e) => setNoteDepth(Number(e.target.value))}
                    className="ml-2 align-middle"
                  />
                </label>
                <button
                  type="button"
                  onClick={saveAuthorNote}
                  className="rounded px-2.5 py-1 font-medium"
                  style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
                >
                  应用
                </button>
              </div>
            </div>

            <div className="space-y-2 border-t pt-3" style={{ borderColor: "var(--border-subtle)" }}>
              <div className="flex items-center justify-between">
                <span className="inline-flex items-center gap-1 font-semibold">
                  <Users className="h-3.5 w-3.5" />
                  多角色群聊小队
                </span>
                <button
                  type="button"
                  onClick={() => triggerGroupTurn()}
                  className="rounded px-2 py-0.5 text-[11px] font-medium"
                  style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
                >
                  轮流发言
                </button>
              </div>
              <div className="space-y-1">
                {cards.map((c) => {
                  const active = activeChat.group_config?.members?.some((m) => m.card_id === c.id);
                  return (
                    <div
                      key={c.id}
                      className="flex items-center justify-between rounded-lg border px-2 py-1.5"
                      style={{ borderColor: active ? "var(--accent)" : "var(--border-subtle)", background: "var(--bg-input)" }}
                    >
                      <button type="button" onClick={() => toggleGroupMember(c.id)} className="flex-1 text-left">
                        <span>{active ? "✓ " : "+ "}</span>
                        {c.name}
                      </button>
                      {active && (
                        <button
                          type="button"
                          onClick={() => triggerGroupTurn(c.id)}
                          className="rounded px-1.5 py-0.5 text-[10px]"
                          style={{ background: "var(--accent-soft)", color: "var(--accent)" }}
                        >
                          点名
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="space-y-1.5 border-t pt-3" style={{ borderColor: "var(--border-subtle)" }}>
              <div className="flex items-center justify-between">
                <span className="font-semibold">Prompt 日志 & 缓存</span>
                <button type="button" onClick={loadPromptLog} className="underline text-[11px]">
                  读取最新
                </button>
              </div>
              {promptLog && (
                <pre
                  className="max-h-48 overflow-auto rounded-lg p-2 text-[10px]"
                  style={{ background: "var(--bg-input)", color: "var(--text-secondary)" }}
                >
                  {JSON.stringify(
                    {
                      est_tokens: promptLog.estimated_context_tokens,
                      prefix_tokens: promptLog.immutable_prefix_tokens,
                      worldbooks: (promptLog.triggered_worldbooks || []).map((w: any) => w.name),
                    },
                    null,
                    2
                  )}
                </pre>
              )}
            </div>
          </div>
        )}
      </div>
      </aside>
    </div>
  );
}
