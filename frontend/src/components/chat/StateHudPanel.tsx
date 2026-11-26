import React, { useState } from "react";
import { Package, Shield, Sparkles, Swords, Users } from "lucide-react";
import { apiFetch } from "../../api/client";
import { useAppStore } from "../../stores/useAppStore";
import type { GameState } from "../../types/api";

export function StateHudPanel({ state }: { state?: GameState }) {
  const { activeChat, selectChat, notify } = useAppStore();
  const [editing, setEditing] = useState(false);
  const [jsonText, setJsonText] = useState("");

  if (!state) return null;

  const handleSaveJson = async () => {
    if (!activeChat) return;
    try {
      const parsed = JSON.parse(jsonText);
      await apiFetch(`/api/chats/${activeChat.id}/state`, {
        method: "PUT",
        body: JSON.stringify({ state: parsed }),
      });
      await selectChat(activeChat.id);
      setEditing(false);
      notify("状态已更新");
    } catch {
      notify("JSON 格式无效");
    }
  };

  return (
    <div className="space-y-3 text-xs">
      <div className="flex items-center justify-between">
        <span className="font-semibold" style={{ color: "var(--text-primary)" }}>
          实时角色与世界状态
        </span>
        <button
          type="button"
          onClick={() => {
            if (!editing) setJsonText(JSON.stringify(state, null, 2));
            setEditing((v) => !v);
          }}
          className="rounded px-2 py-0.5 text-[11px] border"
          style={{ borderColor: "var(--border-subtle)", color: "var(--text-secondary)" }}
        >
          {editing ? "取消" : "微调"}
        </button>
      </div>

      {editing ? (
        <div className="space-y-2">
          <textarea
            value={jsonText}
            onChange={(e) => setJsonText(e.target.value)}
            rows={14}
            className="w-full rounded-lg border p-2 font-mono text-[11px] outline-none"
            style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
          />
          <button
            type="button"
            onClick={handleSaveJson}
            className="w-full rounded-lg py-1.5 font-medium"
            style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
          >
            保存状态
          </button>
        </div>
      ) : (
        <>
          {(state.scene?.location || state.scene?.time) && (
            <div className="rounded-lg border p-2.5" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-input)" }}>
              <div className="font-medium" style={{ color: "var(--accent)" }}>
                {state.scene.location || "未知地点"}
              </div>
              <div className="mt-0.5 text-[11px]" style={{ color: "var(--text-secondary)" }}>
                {[state.scene.time, state.scene.condition].filter(Boolean).join(" · ")}
              </div>
            </div>
          )}

          {state.resources?.length > 0 && (
            <div className="space-y-2">
              {state.resources.map((r) => {
                const pct = r.max > 0 ? Math.max(0, Math.min(100, (r.current / r.max) * 100)) : 100;
                return (
                  <div key={r.key || r.label} className="space-y-1">
                    <div className="flex justify-between">
                      <span style={{ color: "var(--text-secondary)" }}>{r.label || r.key}</span>
                      <span className="font-mono font-medium">
                        {r.current} / {r.max}
                      </span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full" style={{ background: "var(--bg-hover)" }}>
                      <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: "var(--accent)" }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {state.clocks?.length > 0 && (
            <div className="space-y-1.5 pt-1">
              <div className="flex items-center gap-1 font-medium" style={{ color: "var(--warn)" }}>
                <Sparkles className="h-3.5 w-3.5" />
                进度时钟
              </div>
              {state.clocks.map((c) => (
                <div key={c.name} className="flex items-center justify-between rounded-lg border px-2.5 py-1.5" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-input)" }}>
                  <span>{c.name}</span>
                  <div className="flex items-center gap-1">
                    {Array.from({ length: c.max || 6 }).map((_, i) => (
                      <span
                        key={i}
                        className="h-2 w-2 rounded-full"
                        style={{ background: i < c.current ? "var(--danger)" : "var(--bg-hover)" }}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {Object.keys(state.attributes || {}).length > 0 && (
            <div className="grid grid-cols-2 gap-1.5">
              {Object.entries(state.attributes).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between rounded-lg border px-2 py-1" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-input)" }}>
                  <span style={{ color: "var(--text-secondary)" }}>{k}</span>
                  <span className="font-mono font-semibold">{String(v)}</span>
                </div>
              ))}
            </div>
          )}

          {Object.keys(state.equipment || {}).length > 0 && (
            <div className="space-y-1">
              <div className="flex items-center gap-1 font-medium" style={{ color: "var(--text-secondary)" }}>
                <Shield className="h-3.5 w-3.5" />
                装备
              </div>
              {Object.entries(state.equipment).map(([slot, info]) => (
                <div key={slot} className="rounded-lg border px-2.5 py-1.5" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-input)" }}>
                  <span style={{ color: "var(--text-muted)" }}>{slot}: </span>
                  <span className="font-medium">{typeof info === "string" ? info : info?.name}</span>
                </div>
              ))}
            </div>
          )}

          {state.inventory?.length > 0 && (
            <div className="space-y-1">
              <div className="flex items-center gap-1 font-medium" style={{ color: "var(--text-secondary)" }}>
                <Package className="h-3.5 w-3.5" />
                物品 ({state.inventory.length})
              </div>
              {state.inventory.map((it, idx) => (
                <div key={`${it.name}-${idx}`} className="flex items-center justify-between rounded-lg border px-2.5 py-1" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-input)" }}>
                  <span>{it.name}</span>
                  <span className="font-mono" style={{ color: "var(--accent)" }}>
                    x{it.qty}
                  </span>
                </div>
              ))}
            </div>
          )}

          {state.npcs?.length > 0 && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-1 font-medium" style={{ color: "var(--text-secondary)" }}>
                <Users className="h-3.5 w-3.5" />
                人物关系
              </div>
              {state.npcs.map((n) => (
                <div key={n.name} className="rounded-lg border p-2" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-input)" }}>
                  <div className="flex items-center justify-between">
                    <span className="font-semibold">{n.name}</span>
                    <span style={{ color: "var(--accent)" }}>好感 {n.affinity}</span>
                  </div>
                  <div className="mt-0.5 text-[11px]" style={{ color: "var(--text-secondary)" }}>
                    {[n.relation, n.mood, n.status].filter(Boolean).join(" · ")}
                  </div>
                </div>
              ))}
            </div>
          )}

          {state.quests?.length > 0 && (
            <div className="space-y-1">
              <div className="flex items-center gap-1 font-medium" style={{ color: "var(--text-secondary)" }}>
                <Swords className="h-3.5 w-3.5" />
                任务线索
              </div>
              {state.quests.map((q, i) => (
                <div key={i} className="rounded-lg border px-2.5 py-1.5" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-input)" }}>
                  <div className="font-medium">{q.title}</div>
                  {q.progress && <div className="text-[11px]" style={{ color: "var(--text-secondary)" }}>{q.progress}</div>}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
