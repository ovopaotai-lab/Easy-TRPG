import React, { useState } from "react";
import { AlertTriangle, ChevronDown, ChevronUp, Wrench } from "lucide-react";
import type { EngineDiagnosis } from "../../types/api";
import { useAppStore } from "../../stores/useAppStore";

export function DiagnosisCard({ diagnosis }: { diagnosis: EngineDiagnosis }) {
  const [showRaw, setShowRaw] = useState(false);
  const { handleDiagnosisAction, clearDiagnosis } = useAppStore();

  return (
    <div
      className="mx-auto my-3 max-w-2xl rounded-xl border p-3 sm:p-4 shadow-sm"
      style={{
        borderColor: "var(--danger)",
        background: "var(--danger-soft)",
      }}
    >
      <div className="flex items-start gap-2.5 sm:gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" style={{ color: "var(--danger)" }} />
        <div className="flex-1 min-w-0 space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              {diagnosis.title}
            </h4>
            <button
              type="button"
              onClick={clearDiagnosis}
              className="text-xs px-2 py-0.5 rounded hover:opacity-80"
              style={{ color: "var(--text-secondary)" }}
            >
              关闭
            </button>
          </div>
          <p className="whitespace-pre-line text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            {diagnosis.message}
          </p>

          <div className="flex flex-wrap gap-2 pt-1">
            {diagnosis.actions.map((act) => (
              <button
                key={act.id}
                type="button"
                onClick={() => handleDiagnosisAction(act.action)}
                className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition"
                style={{
                  background: "var(--accent)",
                  color: "var(--accent-fg)",
                }}
              >
                <Wrench className="h-3.5 w-3.5" />
                {act.label}
              </button>
            ))}
          </div>

          {diagnosis.raw_tail && (
            <div className="pt-1">
              <button
                type="button"
                onClick={() => setShowRaw((v) => !v)}
                className="inline-flex items-center gap-1 text-[11px]"
                style={{ color: "var(--text-muted)" }}
              >
                {showRaw ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                技术日志详情
              </button>
              {showRaw && (
                <pre
                  className="mt-1.5 max-h-36 overflow-auto rounded-lg p-2 text-[11px]"
                  style={{ background: "var(--bg-app)", color: "var(--text-secondary)" }}
                >
                  {diagnosis.raw_tail}
                </pre>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
