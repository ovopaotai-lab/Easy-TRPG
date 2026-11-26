import React from "react";
import { Dices, GitBranch } from "lucide-react";
import { useAppStore } from "../../stores/useAppStore";

export function BranchTreePanel() {
  const { branchTree, activeChat, checkoutBranchNode } = useAppStore();

  if (!activeChat) return null;

  return (
    <div className="space-y-2 text-xs">
      <div className="flex items-center justify-between">
        <span className="font-semibold">平行世界分支树</span>
        <span style={{ color: "var(--text-muted)" }}>{branchTree.length} 节点</span>
      </div>
      <p className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
        点击任意节点可瞬间切换回该时间线继续游玩。
      </p>
      <div className="space-y-1.5 max-h-[65vh] overflow-y-auto pr-1">
        {branchTree.map((n) => (
          <button
            key={n.id}
            type="button"
            onClick={() => checkoutBranchNode(n.id)}
            className="w-full rounded-lg border p-2 text-left transition"
            style={{
              borderColor: n.on_active_branch ? "var(--accent)" : "var(--border-subtle)",
              background: n.id === activeChat.active_node_id ? "var(--accent-soft)" : "var(--bg-input)",
            }}
          >
            <div className="flex items-center justify-between gap-1">
              <span className="inline-flex items-center gap-1 font-medium">
                <GitBranch className="h-3 w-3" style={{ color: n.on_active_branch ? "var(--accent)" : "var(--text-muted)" }} />
                #{n.seq} {n.role === "user" ? "玩家" : n.speaker_name || "DM"}
              </span>
              {n.has_dice && <Dices className="h-3 w-3" style={{ color: "var(--accent)" }} />}
            </div>
            <div className="mt-1 truncate text-[11px]" style={{ color: "var(--text-secondary)" }}>
              {n.preview || "(空)"}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
