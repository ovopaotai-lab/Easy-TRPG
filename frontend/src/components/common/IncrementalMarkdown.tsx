import React, { memo, useMemo, useState } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { Brain, Database } from "lucide-react";

marked.setOptions({ breaks: true, gfm: true });

const CompletedBlock = memo(function CompletedBlock({ markdown }: { markdown: string }) {
  const html = useMemo(() => {
    const raw = marked.parse(markdown) as string;
    return DOMPurify.sanitize(raw, {
      FORBID_TAGS: ["script", "style", "iframe", "object", "embed", "form", "input"],
    });
  }, [markdown]);

  return <div className="prose-trpg" dangerouslySetInnerHTML={{ __html: html }} />;
});

function splitStructuredSegments(rawText: string, stripTrailingChoices = false) {
  let working = rawText || "";

  // Extract <think>...</think> (handles unclosed <think> while streaming)
  let think = "";
  const closedThink = working.match(/<think(?:ing)?>([\s\S]*?)<\/think(?:ing)?>/i);
  if (closedThink) {
    think = closedThink[1].trim();
    working = working.replace(/<think(?:ing)?>[\s\S]*?<\/think(?:ing)?>/gi, "").trim();
  } else {
    const openThink = working.match(/<think(?:ing)?>([\s\S]*)$/i);
    if (openThink) {
      think = openThink[1].trim();
      working = working.slice(0, openThink.index).trim();
    }
  }

  // Extract <memory>...</memory>
  let memory = "";
  const closedMem = working.match(/<memory>([\s\S]*?)<\/memory>/i);
  if (closedMem) {
    memory = closedMem[1].trim();
    working = working.replace(/<memory>[\s\S]*?<\/memory>/gi, "").trim();
  }

  // Strip <state_patch> and <status> from visible narrative (State HUD renders them cleanly)
  working = working
    .replace(/<state_patch>[\s\S]*?<\/state_patch>/gi, "")
    .replace(/<status(?:\s+[^>]*)?>[\s\S]*?<\/status>/gi, "")
    .replace(/＜status＞[\s\S]*?＜\/status＞/gi, "");

  // Strip trailing contiguous option block ONLY when rendered as cards in bottom dock
  if (stripTrailingChoices) {
    const lines = working.split("\n");
    let endIdx = lines.length - 1;
    while (
      endIdx >= 0 &&
      (!lines[endIdx].trim() ||
        /^(?:[【\[]\s*)?(?:自定义行动|自由行动|自由输入|自动行动)|你可以无视以上建议/.test(lines[endIdx].trim()))
    ) {
      endIdx--;
    }
    let optCount = 0;
    let firstOptIdx = -1;
    for (let i = endIdx; i >= 0; i--) {
      if (/^\s*[1-9][\.、．\)]\s+/.test(lines[i])) {
        optCount++;
        firstOptIdx = i;
      } else if (!lines[i].trim() && optCount > 0) {
        continue;
      } else {
        break;
      }
    }
    if (optCount >= 2 && firstOptIdx >= 0) {
      let cut = firstOptIdx;
      while (cut > 0 && !lines[cut - 1].trim()) {
        cut--;
      }
      if (
        cut > 0 &&
        /^(?:[*#>\s]*)(?:你打算怎么做|接下来|可选行动|行动建议|你可以|---|\*\*\*)/.test(lines[cut - 1].trim())
      ) {
        cut--;
        while (cut > 0 && !lines[cut - 1].trim()) {
          cut--;
        }
      }
      working = lines.slice(0, cut).join("\n").trim();
    }
  }

  // Extract fenced ```html blocks for sandboxed iframe rendering
  const htmlBlocks: string[] = [];
  working = working.replace(/```html\s*\n([\s\S]*?)```/gi, (_, inner) => {
    const idx = htmlBlocks.length;
    htmlBlocks.push(inner);
    return `\n\n__HTML_SANDBOX_${idx}__\n\n`;
  });

  return { think, memory, body: working, htmlBlocks };
}

interface Props {
  content: string;
  isStreaming?: boolean;
  stripTrailingChoices?: boolean;
}

export function IncrementalMarkdown({ content, isStreaming, stripTrailingChoices = false }: Props) {
  const [thinkOpen, setThinkOpen] = useState(false);
  const [memOpen, setMemOpen] = useState(false);

  const { think, memory, body, htmlBlocks } = useMemo(
    () => splitStructuredSegments(content, stripTrailingChoices),
    [content, stripTrailingChoices]
  );

  // Split body on double newlines so finished paragraphs are memoized and never flicker on stream
  const paragraphs = useMemo(() => {
    if (!body) return [];
    return body.split(/\n{2,}/).filter((p) => p.trim().length > 0);
  }, [body]);

  const completedCount = isStreaming && paragraphs.length > 0 ? paragraphs.length - 1 : paragraphs.length;

  return (
    <div className="space-y-2.5">
      {think && (
        <div
          className="rounded-lg border px-3 py-2 text-xs"
          style={{ borderColor: "var(--border-subtle)", background: "var(--bg-input)" }}
        >
          <button
            type="button"
            onClick={() => setThinkOpen((v) => !v)}
            className="flex w-full items-center gap-1.5 font-medium"
            style={{ color: "var(--text-secondary)" }}
          >
            <Brain className="h-3.5 w-3.5" style={{ color: "var(--accent)" }} />
            <span>思考推演</span>
            <span className="ml-auto text-[11px]">{thinkOpen ? "收起" : "展开"}</span>
          </button>
          {thinkOpen && (
            <pre className="mt-2 whitespace-pre-wrap text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              {think}
            </pre>
          )}
        </div>
      )}

      <div className="space-y-2">
        {paragraphs.slice(0, completedCount).map((p, idx) => {
          const m = p.trim().match(/^__HTML_SANDBOX_(\d+)__$/);
          if (m) {
            const rawHtml = htmlBlocks[Number(m[1])] || "";
            return (
              <iframe
                key={`hb-${idx}`}
                sandbox="allow-scripts"
                srcDoc={`<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{margin:0;padding:8px;color:#e8e6e1;background:transparent;font-family:system-ui;}</style></head><body>${rawHtml}</body></html>`}
                className="w-full min-h-[140px] rounded-lg border"
                style={{ borderColor: "var(--border-subtle)" }}
              />
            );
          }
          return <CompletedBlock key={`p-${idx}`} markdown={p} />;
        })}

        {isStreaming && paragraphs.length > completedCount && (
          <div
            className="prose-trpg"
            dangerouslySetInnerHTML={{
              __html: DOMPurify.sanitize(marked.parse(paragraphs[paragraphs.length - 1]) as string),
            }}
          />
        )}
      </div>

      {memory && (
        <div
          className="rounded-lg border px-3 py-2 text-xs"
          style={{ borderColor: "var(--border-subtle)", background: "var(--bg-input)" }}
        >
          <button
            type="button"
            onClick={() => setMemOpen((v) => !v)}
            className="flex w-full items-center gap-1.5 font-medium"
            style={{ color: "var(--text-secondary)" }}
          >
            <Database className="h-3.5 w-3.5" style={{ color: "var(--accent)" }} />
            <span>记忆锚点</span>
            <span className="ml-auto text-[11px]">{memOpen ? "收起" : "查看"}</span>
          </button>
          {memOpen && (
            <pre className="mt-2 whitespace-pre-wrap text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              {memory}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
