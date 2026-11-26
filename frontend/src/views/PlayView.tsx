import React, { useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Copy,
  CornerDownLeft,
  Dices,
  Film,
  GitBranch,
  ImagePlus,
  Maximize2,
  Menu,
  Minimize2,
  PanelRight,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Send,
  Square,
  Trash2,
  UserCheck,
  X,
} from "lucide-react";
import { apiFetch } from "../api/client";
import { useAppStore } from "../stores/useAppStore";
import type { ActionChoice, ChatMessage } from "../types/api";
import { extractVideoFramesAndPoster } from "../utils/videoFrames";
import { IncrementalMarkdown } from "../components/common/IncrementalMarkdown";
import { DiagnosisCard } from "../components/chat/DiagnosisCard";
import { InspectorDrawer } from "../components/chat/InspectorDrawer";

function cleanDisplayTitle(raw?: string): string {
  if (!raw) return "";
  return raw
    .replace(/^[*_#`\s]+/, "")
    .replace(/[*_`\s]+$/, "")
    .trim();
}

function isMetaChoice(text: string): boolean {
  const t = text.replace(/^[【\[\s*]+/, "").trim();
  return (
    /^(?:自定义行动|自由行动|自由输入)/.test(t) ||
    /你可以无视以上建议|自行输入任何指令/.test(t)
  );
}

function parseChoiceCard(ch: ActionChoice): { title: string; detail: string } {
  let clean = (ch.text || "")
    .replace(/\*\*/g, "")
    .replace(/[【\[]\s*🎲\s*[^】\]]+[】\]]/g, "")
    .trim();
  const bracketMatch = clean.match(/^【([^】]{2,16})】\s*(.+)$/);
  if (bracketMatch) {
    return { title: bracketMatch[1].trim(), detail: bracketMatch[2].trim() };
  }
  const colonMatch = clean.match(/^([^：:，。；\s]{2,14})[：:]\s*(.+)$/);
  if (colonMatch) {
    return { title: colonMatch[1].trim(), detail: colonMatch[2].trim() };
  }
  return { title: "", detail: clean };
}

function extractChoicesFromText(txt: string): ActionChoice[] {
  const clean = (txt || "").replace(/<think(?:ing)?>[\s\S]*?<\/think(?:ing)?>/gi, "");
  const lines = clean.split("\n");
  const out: ActionChoice[] = [];
  for (let i = lines.length - 1; i >= 0; i--) {
    const ln = lines[i].trim();
    const m = lines[i].match(/^\s*([1-9])[\.、．\)]\s+(.+)$/);
    if (m) {
      const raw = m[2].trim();
      if (!isMetaChoice(raw)) {
        const dm = raw.match(/[【\[]\s*🎲\s*([^】\]]+)[】\]]/);
        out.push({ index: Number(m[1]), text: raw, dice_skill: dm ? dm[1].trim() : "" });
      }
    } else if (out.length === 0) {
      if (!ln || isMetaChoice(ln) || /^自动行动/.test(ln)) continue;
      break;
    } else if (ln && !/你打算怎么做|接下来|可选行动|行动建议/.test(ln)) {
      break;
    }
  }
  return out.reverse();
}

export function PlayView() {
  const {
    projects,
    activeProjectId,
    chats,
    activeChat,
    personas,
    settings,
    localModels,
    remoteModels,
    isStreaming,
    streamingText,
    streamingStatus,
    lastCacheHitTokens,
    engineDiagnosis,
    experienceMode,
    selectProject,
    selectChat,
    createNewChat,
    sendMessage,
    stopGeneration,
    triggerSwipeGenerate,
    switchSwipe,
    openOnboarding,
    notify,
  } = useAppStore();

  const [input, setInput] = useState("");
  const [searchQ, setSearchQ] = useState("");
  const [searchHits, setSearchHits] = useState<any[]>([]);
  const [showInspector, setShowInspector] = useState(() =>
    typeof window !== "undefined" ? window.innerWidth >= 1024 : true
  );
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [selectedImgs, setSelectedImgs] = useState<string[]>([]);
  const [selectedVideos, setSelectedVideos] = useState<
    Array<{
      id: string;
      url: string;
      poster: string;
      filename: string;
      durationSec: number;
      frameCount: number;
      frames: string[];
      hasAudio?: boolean;
      audioTranscript?: string;
      compressed?: boolean;
    }>
  >([]);
  const [uploadingVideo, setUploadingVideo] = useState(false);
  const [editingMsgId, setEditingMsgId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState("");
  const [choicesCollapsed, setChoicesCollapsed] = useState(false);
  const [showAllChoices, setShowAllChoices] = useState(false);
  const [composerExpanded, setComposerExpanded] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const activeProj = projects.find((p) => p.id === activeProjectId);
  const hasAnyModel = Boolean(settings?.model || localModels.length > 0 || remoteModels.length > 0 || settings?.has_api_key);

  const displayMessages: ChatMessage[] = useMemo(() => {
    const base = activeChat?.messages ? [...activeChat.messages] : [];
    if (isStreaming) {
      base.push({
        id: "streaming_live",
        role: "assistant",
        content: streamingText || "",
      });
    }
    return base;
  }, [activeChat?.messages, isStreaming, streamingText]);

  const virtualizer = useVirtualizer({
    count: displayMessages.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 220,
    overscan: 6,
  });

  useEffect(() => {
    if (displayMessages.length > 0 && scrollRef.current) {
      virtualizer.scrollToIndex(displayMessages.length - 1, { align: "end" });
    }
  }, [displayMessages.length, isStreaming]);

  const lastMsg = !isStreaming && activeChat?.messages?.length
    ? activeChat.messages[activeChat.messages.length - 1]
    : null;

  const latestChoices = useMemo(() => {
    if (!lastMsg || lastMsg.role !== "assistant") return [];
    const raw = lastMsg.suggested_questions?.length
      ? lastMsg.suggested_questions
      : extractChoicesFromText(lastMsg.content);
    return raw.filter((c) => !isMetaChoice(c.text));
  }, [lastMsg]);

  const latestAsstMsgId = latestChoices.length > 0 && lastMsg ? lastMsg.id : null;

  useEffect(() => {
    setShowAllChoices(false);
  }, [latestAsstMsgId]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const vh = typeof window !== "undefined" ? window.innerHeight : 800;
    const isMobile = typeof window !== "undefined" && window.innerWidth < 640;
    const minH = composerExpanded ? (isMobile ? 150 : 260) : isMobile ? 44 : displayMessages.length === 0 ? 88 : 72;
    const maxH = composerExpanded
      ? Math.max(isMobile ? 160 : 260, Math.round(vh * (isMobile ? 0.42 : 0.5)))
      : isMobile
      ? Math.min(130, Math.round(vh * 0.22))
      : displayMessages.length === 0
      ? Math.min(340, Math.round(vh * 0.42))
      : Math.min(260, Math.round(vh * 0.34));
    const targetH = Math.min(Math.max(el.scrollHeight, minH), maxH);
    el.style.height = `${targetH}px`;
    el.style.overflowY = el.scrollHeight > maxH ? "auto" : "hidden";
  }, [input, composerExpanded, displayMessages.length]);

  const handleSend = async (overrideText?: string, diceSkill?: string) => {
    const txt = (overrideText ?? input).trim();
    if (!txt && selectedImgs.length === 0 && selectedVideos.length === 0) return;
    let rollRes = undefined;
    if (diceSkill && activeChat) {
      const r = await apiFetch<any>(`/api/chats/${activeChat.id}/roll`, {
        method: "POST",
        body: JSON.stringify({ skill: diceSkill }),
      });
      rollRes = r.roll;
      notify(`🎲 ${diceSkill}: ${rollRes.total} (${rollRes.tier_label})`);
    }
    if (!overrideText) {
      setInput("");
      setComposerExpanded(false);
    }
    const imgs = [...selectedImgs];
    const vids = [...selectedVideos];
    setSelectedImgs([]);
    setSelectedVideos([]);
    await sendMessage({
      content: txt,
      images: imgs,
      videos: vids.map((v) => ({ id: v.id, url: v.url, frames: v.frames })),
      diceRoll: rollRes,
    });
  };

  const handleManualRoll = async () => {
    if (!activeChat) return;
    const r = await apiFetch<any>(`/api/chats/${activeChat.id}/roll`, {
      method: "POST",
      body: JSON.stringify({ skill: "自由检定" }),
    });
    const roll = r.roll;
    notify(`🎲 ${roll.expression} = ${roll.total} (${roll.tier_label})`);
    setInput((prev) => `${prev ? prev + "\n" : ""}[投骰 ${roll.expression}=${roll.total} ${roll.tier_label}] `);
  };

  const handleRerollChoices = async () => {
    if (!activeChat?.messages?.length) return;
    const lastAsst = [...activeChat.messages].reverse().find((m) => m.role === "assistant");
    if (!lastAsst) return;
    await apiFetch("/api/ai/reroll_choices", {
      method: "POST",
      body: JSON.stringify({ chat_id: activeChat.id, msg_id: lastAsst.id }),
    });
    await selectChat(activeChat.id);
  };

  const handleSearch = async (q: string) => {
    setSearchQ(q);
    if (!q.trim()) {
      setSearchHits([]);
      return;
    }
    const res = await apiFetch<any>(`/api/search?q=${encodeURIComponent(q)}&scope=messages&limit=10`);
    setSearchHits(res.messages || []);
  };

  const appendImageFiles = (files: File[]) => {
    files.forEach((f) => {
      const reader = new FileReader();
      reader.onload = () => {
        if (typeof reader.result === "string") {
          setSelectedImgs((prev) => [...prev, reader.result as string]);
        }
      };
      reader.readAsDataURL(f);
    });
  };

  const handleImagePick = (ev: React.ChangeEvent<HTMLInputElement>) => {
    appendImageFiles(Array.from(ev.target.files || []));
    ev.target.value = "";
  };

  const appendVideoFiles = async (files: File[]) => {
    const vids = files.filter(
      (f) => f.type.startsWith("video/") || /\.(mp4|webm|mov|m4v|ogg)$/i.test(f.name)
    );
    if (vids.length === 0) return;
    setUploadingVideo(true);
    try {
      for (const f of vids) {
        const fd = new FormData();
        fd.append("file", f);
        fd.append("folder", "视频素材");
        const up = await apiFetch<any>("/api/gallery/upload_video", {
          method: "POST",
          body: fd,
        });
        let backendFrames = Number(up.frame_count || 0);
        let fallbackFrames: string[] = [];
        let poster = up.thumb_url || "";
        let durationSec = Number(up.duration_sec || 0);
        if (backendFrames <= 0) {
          const browserRes = await extractVideoFramesAndPoster(f);
          fallbackFrames = browserRes.frames;
          if (!poster && browserRes.poster) poster = browserRes.poster;
          if (!durationSec && browserRes.durationSec) durationSec = browserRes.durationSec;
          backendFrames = fallbackFrames.length;
        }
        setSelectedVideos((prev) => [
          ...prev,
          {
            id: up.id,
            url: up.url,
            poster,
            filename: up.filename || f.name,
            durationSec: Math.round(durationSec),
            frameCount: backendFrames,
            frames: fallbackFrames,
            hasAudio: Boolean(up.has_audio),
            audioTranscript: String(up.audio_transcript || ""),
            compressed: Boolean(up.compressed),
          },
        ]);
      }
      notify("视频已就绪（已抽取多帧画面与音轨供 AI 分析）");
    } catch (err: any) {
      notify(err?.message || "上传视频失败");
    } finally {
      setUploadingVideo(false);
    }
  };

  const handleVideoPick = async (ev: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(ev.target.files || []);
    ev.target.value = "";
    await appendVideoFiles(files);
  };

  const handleComposerDrop = async (ev: React.DragEvent<HTMLDivElement>) => {
    const files = Array.from(ev.dataTransfer?.files || []);
    if (files.length === 0) return;
    const imgs = files.filter((f) => f.type.startsWith("image/"));
    const vids = files.filter((f) => f.type.startsWith("video/") || /\.(mp4|webm|mov|m4v|ogg)$/i.test(f.name));
    if (imgs.length > 0 || vids.length > 0) {
      ev.preventDefault();
      if (imgs.length > 0) appendImageFiles(imgs);
      if (vids.length > 0) await appendVideoFiles(vids);
    }
  };

  const handleTextareaPaste = (ev: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = Array.from(ev.clipboardData?.items || []);
    const imgFiles: File[] = [];
    for (const it of items) {
      if (it.type.startsWith("image/")) {
        const f = it.getAsFile();
        if (f) imgFiles.push(f);
      }
    }
    if (imgFiles.length > 0) {
      appendImageFiles(imgFiles);
    }
  };

  const saveEditedMessage = async (msgId: string) => {
    if (!activeChat) return;
    await apiFetch(`/api/chats/${activeChat.id}/messages/${msgId}`, {
      method: "PUT",
      body: JSON.stringify({ content: editingText }),
    });
    setEditingMsgId(null);
    await selectChat(activeChat.id);
  };

  const deleteMsg = async (msgId: string) => {
    if (!activeChat) return;
    await apiFetch(`/api/chats/${activeChat.id}/messages/${msgId}`, { method: "DELETE" });
    await selectChat(activeChat.id);
  };

  const branchAtMsg = async (msgId: string) => {
    if (!activeChat) return;
    const res = await apiFetch<any>(`/api/chats/${activeChat.id}/branch`, {
      method: "POST",
      body: JSON.stringify({ up_to_msg_id: msgId }),
    });
    await selectChat(res.chat.id);
    notify("已创建分支对话");
  };

  const renderSidebarBody = (isMobile: boolean) => (
    <>
      <div className="p-3 space-y-2 border-b" style={{ borderColor: "var(--border-subtle)" }}>
        <select
          value={activeProjectId}
          onChange={(e) => selectProject(e.target.value)}
          className="w-full rounded-lg border px-2.5 py-1.5 text-xs font-medium outline-none"
          style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        {isMobile && activeChat && personas.length > 0 && (
          <div className="flex items-center gap-1.5 text-[11px]" style={{ color: "var(--text-secondary)" }}>
            <UserCheck className="h-3.5 w-3.5 shrink-0" />
            <span className="shrink-0">人设</span>
            <select
              value={activeChat.persona_id || ""}
              onChange={async (e) => {
                await apiFetch(`/api/chats/${activeChat.id}`, {
                  method: "PUT",
                  body: JSON.stringify({ persona_id: e.target.value }),
                });
                selectChat(activeChat.id);
              }}
              className="flex-1 min-w-0 rounded border px-1.5 py-1 text-xs outline-none"
              style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
            >
              {personas.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
        )}
        <button
          type="button"
          onClick={() => {
            createNewChat(activeProjectId, activeProj?.opening_greetings?.[0]?.content);
            if (isMobile) setMobileSidebarOpen(false);
          }}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg py-1.5 text-xs font-medium"
          style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
        >
          <Plus className="h-3.5 w-3.5" />
          新开对话
        </button>
        <div className="relative">
          <Search className="absolute left-2.5 top-2 h-3.5 w-3.5" style={{ color: "var(--text-muted)" }} />
          <input
            value={searchQ}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="搜剧情..."
            className="w-full rounded-lg border py-1.5 pl-8 pr-2 text-xs outline-none"
            style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {searchHits.length > 0 ? (
          searchHits.map((h) => (
            <button
              key={h.node_id}
              type="button"
              onClick={() => {
                selectChat(h.chat_id);
                setSearchQ("");
                setSearchHits([]);
                if (isMobile) setMobileSidebarOpen(false);
              }}
              className="w-full rounded-lg border p-2 text-left text-xs"
              style={{ borderColor: "var(--border-subtle)", background: "var(--bg-elevated)" }}
            >
              <div className="font-medium truncate">{h.chat_title}</div>
              <div className="mt-0.5 line-clamp-2 text-[11px]" style={{ color: "var(--text-secondary)" }}>
                {h.snippet}
              </div>
            </button>
          ))
        ) : (
          chats.map((c) => (
            <div
              key={c.id}
              className="group flex items-center justify-between rounded-lg px-2.5 py-2 text-xs cursor-pointer transition"
              style={{
                background: activeChat?.id === c.id ? "var(--accent-soft)" : "transparent",
                color: activeChat?.id === c.id ? "var(--accent)" : "var(--text-primary)",
              }}
              onClick={() => {
                selectChat(c.id);
                if (isMobile) setMobileSidebarOpen(false);
              }}
            >
              <div className="truncate flex-1">{cleanDisplayTitle(c.title) || c.title}</div>
              <button
                type="button"
                onClick={async (e) => {
                  e.stopPropagation();
                  await apiFetch(`/api/chats/${c.id}`, { method: "DELETE" });
                  await useAppStore.getState().refreshChats(activeProjectId);
                }}
                className="opacity-70 md:opacity-0 md:group-hover:opacity-100 p-1 md:p-0.5"
                style={{ color: "var(--text-muted)" }}
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))
        )}
      </div>
    </>
  );

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left Sidebar: Projects & Chats (Desktop) */}
      <aside
        className="hidden md:flex w-64 shrink-0 flex-col border-r"
        style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}
      >
        {renderSidebarBody(false)}
      </aside>

      {/* Mobile Slide-Over Sidebar */}
      {mobileSidebarOpen && (
        <div className="fixed inset-0 z-40 flex md:hidden">
          <div className="fixed inset-0 bg-black/60" onClick={() => setMobileSidebarOpen(false)} />
          <aside
            className="relative z-10 flex h-full w-[82vw] max-w-xs flex-col border-r shadow-2xl"
            style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}
          >
            <div
              className="flex items-center justify-between border-b px-3 py-2.5 text-xs font-semibold"
              style={{ borderColor: "var(--border-subtle)" }}
            >
              <span>剧本与对话</span>
              <button
                type="button"
                onClick={() => setMobileSidebarOpen(false)}
                aria-label="关闭列表"
                className="rounded-lg p-1"
                style={{ color: "var(--text-muted)" }}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            {renderSidebarBody(true)}
          </aside>
        </div>
      )}

      {/* Main Reading & Chat Stage */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* Subheader */}
        <div
          className="flex items-center justify-between gap-2 border-b px-2.5 sm:px-4 py-1.5 sm:py-2 text-xs"
          style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}
        >
          <div className="flex items-center gap-2 sm:gap-3 min-w-0">
            <button
              type="button"
              onClick={() => setMobileSidebarOpen(true)}
              aria-label="打开剧本与对话列表"
              className="md:hidden inline-flex shrink-0 items-center justify-center rounded-lg border p-1.5"
              style={{ borderColor: "var(--border-subtle)", color: "var(--text-secondary)" }}
            >
              <Menu className="h-3.5 w-3.5" />
            </button>
            <span className="font-semibold truncate">{cleanDisplayTitle(activeChat?.title) || activeProj?.name || "跑团舞台"}</span>
            {activeChat?.context_tokens_est !== undefined && (
              <span className="hidden sm:inline shrink-0 text-[11px]" style={{ color: "var(--text-muted)" }}>
                上下文 {Math.round(activeChat.context_tokens_est / 100) / 10}K /{" "}
                {Math.round((activeChat.max_context_tokens || 98304) / 1024)}K
              </span>
            )}
            {lastCacheHitTokens > 0 && (
              <span className="hidden sm:inline shrink-0 rounded px-1.5 py-0.5 text-[10px]" style={{ background: "var(--success-soft)", color: "var(--success)" }}>
                KV 命中 {lastCacheHitTokens}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
            {activeChat && personas.length > 0 && (
              <div className="hidden sm:inline-flex items-center gap-1 text-[11px]" style={{ color: "var(--text-secondary)" }}>
                <UserCheck className="h-3.5 w-3.5" />
                <select
                  value={activeChat.persona_id || ""}
                  onChange={async (e) => {
                    await apiFetch(`/api/chats/${activeChat.id}`, {
                      method: "PUT",
                      body: JSON.stringify({ persona_id: e.target.value }),
                    });
                    selectChat(activeChat.id);
                  }}
                  className="rounded border px-1.5 py-0.5 text-[11px]"
                  style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
                >
                  {personas.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <button
              type="button"
              onClick={() => setShowInspector((v) => !v)}
              className="inline-flex shrink-0 items-center gap-1 rounded-lg border px-2 py-1 text-[11px]"
              style={{
                borderColor: showInspector ? "var(--accent)" : "var(--border-subtle)",
                background: showInspector ? "var(--accent-soft)" : "transparent",
                color: showInspector ? "var(--accent)" : "var(--text-secondary)",
              }}
            >
              <PanelRight className="h-3.5 w-3.5" />
              面板
            </button>
          </div>
        </div>

        {!hasAnyModel && (
          <div
            className="mx-2.5 sm:mx-4 mt-2.5 sm:mt-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border px-3 sm:px-4 py-2 sm:py-2.5 text-xs"
            style={{ borderColor: "var(--warn)", background: "var(--warn-soft)" }}
          >
            <span className="min-w-0">尚未配置本地模型或在线 API，点右侧即可 10 秒完成配置。</span>
            <button
              type="button"
              onClick={openOnboarding}
              className="shrink-0 rounded-lg px-3 py-1 font-medium"
              style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
            >
              配置模型
            </button>
          </div>
        )}

        {/* Virtualized Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-2.5 sm:px-4 py-3 sm:py-4">
          {displayMessages.length === 0 ? (
            <div className="mx-auto max-w-2xl py-4 sm:py-8 space-y-3 sm:space-y-4">
              <div className="text-center space-y-1">
                <h3 className="text-lg font-semibold">{activeProj?.name || "欢迎来到 Easy-TRPG"}</h3>
                <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
                  {activeProj?.description ||
                    (activeProj?.opening_greetings?.length
                      ? "点击下方推荐开场，或直接在底部输入你的第一句话。"
                      : "在下方输入开场设定或第一句话开始跑团。")}
                </p>
              </div>
              {activeProj?.opening_greetings?.length ? (
                <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                  {activeProj.opening_greetings.map((og) => (
                    <button
                      key={og.id}
                      type="button"
                      onClick={() => handleSend(og.content)}
                      className="rounded-xl border p-3.5 text-left transition hover:opacity-90"
                      style={{ borderColor: "var(--border-subtle)", background: "var(--bg-elevated)" }}
                    >
                      <div className="text-sm font-medium" style={{ color: "var(--accent)" }}>
                        {og.title}
                      </div>
                      <p className="mt-1 line-clamp-3 text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                        {og.content}
                      </p>
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          ) : (
            <div
              className="mx-auto max-w-3xl relative"
              style={{ height: `${virtualizer.getTotalSize()}px` }}
            >
              {virtualizer.getVirtualItems().map((vRow) => {
                const msg = displayMessages[vRow.index];
                const isLive = msg.id === "streaming_live";
                const isUser = msg.role === "user";
                const swipeCount = msg.swipe_count || 1;
                const swipeIdx = msg.active_swipe_idx || 0;

                return (
                  <div
                    key={msg.id}
                    data-index={vRow.index}
                    ref={virtualizer.measureElement}
                    style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      width: "100%",
                      transform: `translateY(${vRow.start}px)`,
                    }}
                    className="pb-3 sm:pb-4"
                  >
                    <div
                      className={`rounded-2xl border px-3 sm:px-4 py-2.5 sm:py-3 ${isUser ? "ml-auto max-w-[92%] sm:max-w-[85%]" : "w-full"}`}
                      style={{
                        borderColor: "var(--border-subtle)",
                        background: isUser ? "var(--bg-user-bubble)" : "var(--bg-ai-bubble)",
                      }}
                    >
                      <div className="mb-1.5 flex flex-wrap items-center justify-between gap-x-2 gap-y-1 text-[11px]" style={{ color: "var(--text-muted)" }}>
                        <span className="font-medium truncate min-w-0" style={{ color: isUser ? "var(--text-secondary)" : "var(--accent)" }}>
                          {isUser ? "玩家" : msg.speaker_name || activeProj?.name || "DM"}
                        </span>
                        {!isLive && (
                          <div className="flex flex-wrap items-center gap-1.5">
                            {!isUser && swipeCount > 1 && (
                              <span className="inline-flex items-center gap-0.5 rounded border px-1" style={{ borderColor: "var(--border-subtle)" }}>
                                <button
                                  type="button"
                                  disabled={swipeIdx <= 0}
                                  onClick={() => switchSwipe(msg.id, swipeIdx - 1)}
                                  className="disabled:opacity-30"
                                >
                                  <ChevronLeft className="h-3 w-3" />
                                </button>
                                <span>
                                  {swipeIdx + 1}/{swipeCount}
                                </span>
                                <button
                                  type="button"
                                  disabled={swipeIdx + 1 >= swipeCount}
                                  onClick={() => switchSwipe(msg.id, swipeIdx + 1)}
                                  className="disabled:opacity-30"
                                >
                                  <ChevronRight className="h-3 w-3" />
                                </button>
                              </span>
                            )}
                            {!isUser && experienceMode === "pro" && (
                              <button type="button" onClick={() => triggerSwipeGenerate(msg.id)} title="生成新候选">
                                +候选
                              </button>
                            )}
                            {isUser && (
                              <button
                                type="button"
                                onClick={() => sendMessage({ content: "", regenerate: true, targetUserMsgId: msg.id })}
                                title="重写"
                              >
                                <RotateCcw className="h-3 w-3" />
                              </button>
                            )}
                            {experienceMode === "pro" && (
                              <button type="button" onClick={() => branchAtMsg(msg.id)} title="在此创建分支">
                                <GitBranch className="h-3 w-3" />
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => {
                                setEditingMsgId(msg.id);
                                setEditingText(msg.content);
                              }}
                            >
                              编辑
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                navigator.clipboard.writeText(msg.content);
                                notify("已复制");
                              }}
                            >
                              <Copy className="h-3 w-3" />
                            </button>
                            <button type="button" onClick={() => deleteMsg(msg.id)}>
                              <Trash2 className="h-3 w-3" />
                            </button>
                          </div>
                        )}
                      </div>

                      {msg.dice_rolls?.map((dr, idx) => (
                        <div
                          key={idx}
                          className="mb-2 inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium"
                          style={{ background: "var(--accent-soft)", color: "var(--accent)" }}
                        >
                          <Dices className="h-3.5 w-3.5" />
                          <span>
                            {dr.skill ? `${dr.skill} · ` : ""}
                            {dr.expression} = {dr.total} ({dr.tier_label})
                          </span>
                        </div>
                      ))}

                      {msg.images?.length ? (
                        <div className="mb-2 flex flex-wrap gap-2">
                          {msg.images.map((im, i) => (
                            <img key={i} src={im} alt="" className="max-h-48 rounded-lg object-cover" />
                          ))}
                        </div>
                      ) : null}

                      {msg.videos?.length ? (
                        <div className="mb-2 flex flex-wrap gap-2">
                          {msg.videos.map((vidUrl, i) => (
                            <video
                              key={i}
                              src={vidUrl}
                              controls
                              playsInline
                              preload="metadata"
                              className="max-h-56 sm:max-h-72 max-w-full rounded-xl border bg-black"
                              style={{ borderColor: "var(--border-subtle)" }}
                            />
                          ))}
                        </div>
                      ) : null}

                      {editingMsgId === msg.id ? (
                        <div className="space-y-2">
                          <textarea
                            value={editingText}
                            onChange={(e) => setEditingText(e.target.value)}
                            rows={5}
                            className="w-full rounded-lg border p-2 text-xs outline-none"
                            style={{ background: "var(--bg-input)", borderColor: "var(--border-subtle)" }}
                          />
                          <div className="flex justify-end gap-2 text-xs">
                            <button type="button" onClick={() => setEditingMsgId(null)}>
                              取消
                            </button>
                            <button
                              type="button"
                              onClick={() => saveEditedMessage(msg.id)}
                              className="rounded px-3 py-1 font-medium"
                              style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
                            >
                              保存
                            </button>
                          </div>
                        </div>
                      ) : isLive && !msg.content ? (
                        <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                          {streamingStatus || "生成中..."}
                        </span>
                      ) : (
                        <IncrementalMarkdown
                          content={msg.content}
                          isStreaming={isLive}
                          stripTrailingChoices={!isLive && msg.id === latestAsstMsgId && !choicesCollapsed}
                        />
                      )}

                      {!isLive && (msg.triggered_worldbooks?.length || 0) > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {msg.triggered_worldbooks!.map((w: any, idx: number) => (
                            <span
                              key={idx}
                              className="rounded px-1.5 py-0.5 text-[10px]"
                              style={{ background: "var(--bg-hover)", color: "var(--text-secondary)" }}
                            >
                              {typeof w === "string" ? w : w.name}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {engineDiagnosis && <DiagnosisCard diagnosis={engineDiagnosis} />}
        </div>

        {/* Bottom Choices + Input Dock */}
        <div className="border-t px-2.5 sm:px-4 py-2 sm:py-3" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}>
          <div className="mx-auto max-w-3xl space-y-2 sm:space-y-2.5">
            {latestChoices.length > 0 && (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-[11px]" style={{ color: "var(--text-muted)" }}>
                  <span>行动选项 ({latestChoices.length})</span>
                  <div className="flex items-center gap-2">
                    {!choicesCollapsed && latestChoices.length > 4 && (
                      <button
                        type="button"
                        onClick={() => setShowAllChoices((v) => !v)}
                        className="hover:underline"
                        style={{ color: "var(--accent)" }}
                      >
                        {showAllChoices ? "收起多余" : `更多 (+${latestChoices.length - 4})`}
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => setChoicesCollapsed((v) => !v)}
                      className="inline-flex items-center gap-0.5 hover:opacity-80"
                    >
                      {choicesCollapsed ? (
                        <>
                          <span>展开</span>
                          <ChevronUp className="h-3 w-3" />
                        </>
                      ) : (
                        <>
                          <span>收起</span>
                          <ChevronDown className="h-3 w-3" />
                        </>
                      )}
                    </button>
                  </div>
                </div>
                {!choicesCollapsed && (
                  <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2 max-h-36 sm:max-h-48 overflow-y-auto pr-0.5">
                    {(showAllChoices ? latestChoices : latestChoices.slice(0, 4)).map((ch) => {
                      const parsed = parseChoiceCard(ch);
                      return (
                        <div
                          key={ch.index}
                          role="button"
                          tabIndex={0}
                          title={ch.text}
                          onClick={(e) => {
                            if (e.shiftKey) {
                              setInput(ch.text);
                              return;
                            }
                            handleSend(`${ch.index}. ${ch.text}`, ch.dice_skill);
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              handleSend(`${ch.index}. ${ch.text}`, ch.dice_skill);
                            }
                          }}
                          className="group flex flex-col justify-between gap-1 rounded-xl border px-2.5 py-1.5 sm:px-3 sm:py-2 text-left text-xs cursor-pointer transition hover:brightness-110"
                          style={{
                            borderColor: ch.dice_skill ? "var(--accent)" : "var(--border-subtle)",
                            background: "var(--bg-elevated)",
                            color: "var(--text-primary)",
                          }}
                        >
                          <div className="flex items-center justify-between gap-1.5 min-w-0">
                            <div className="flex items-center gap-1.5 min-w-0">
                              <span
                                className="inline-flex h-4 min-w-[16px] shrink-0 items-center justify-center rounded px-1 text-[10px] font-semibold"
                                style={{ background: "var(--accent-soft)", color: "var(--accent)" }}
                              >
                                {ch.index}
                              </span>
                              {parsed.title && (
                                <span className="font-medium truncate" style={{ color: "var(--text-primary)" }}>
                                  {parsed.title}
                                </span>
                              )}
                              {ch.dice_skill && (
                                <span
                                  className="shrink-0 rounded px-1.5 py-0.5 text-[10px]"
                                  style={{ background: "var(--accent-soft)", color: "var(--accent)" }}
                                >
                                  🎲 {ch.dice_skill}
                                </span>
                              )}
                            </div>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setInput(ch.text);
                              }}
                              className="opacity-80 sm:opacity-0 sm:group-hover:opacity-100 inline-flex shrink-0 items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] transition"
                              style={{ color: "var(--text-muted)", background: "var(--bg-hover)" }}
                              title="填入输入框修改后再发送"
                            >
                              <CornerDownLeft className="h-2.5 w-2.5" />
                              填入
                            </button>
                          </div>
                          <div
                            className="line-clamp-2 text-[11px] leading-relaxed"
                            style={{ color: parsed.title ? "var(--text-secondary)" : "var(--text-primary)" }}
                          >
                            {parsed.detail}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            <div
              onDragOver={(e) => {
                if (e.dataTransfer?.types?.includes("Files")) e.preventDefault();
              }}
              onDrop={handleComposerDrop}
              className="rounded-2xl border transition focus-within:border-[var(--accent)]"
              style={{
                background: "var(--bg-input)",
                borderColor: "var(--border-strong)",
              }}
            >
              {(selectedImgs.length > 0 || selectedVideos.length > 0 || uploadingVideo) && (
                <div
                  className="flex flex-wrap items-center gap-2 border-b px-3 py-2.5"
                  style={{ borderColor: "var(--border-subtle)" }}
                >
                  {selectedImgs.map((im, idx) => (
                    <div key={`img-${idx}`} className="relative group">
                      <img
                        src={im}
                        alt=""
                        className="h-14 w-14 rounded-lg border object-cover"
                        style={{ borderColor: "var(--border-subtle)" }}
                      />
                      <button
                        type="button"
                        onClick={() => setSelectedImgs((prev) => prev.filter((_, i) => i !== idx))}
                        className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full shadow"
                        style={{ background: "var(--bg-panel)", color: "var(--text-primary)", border: "1px solid var(--border-strong)" }}
                        title="移除图片"
                      >
                        <X className="h-2.5 w-2.5" />
                      </button>
                    </div>
                  ))}
                  {selectedVideos.map((vid, idx) => (
                    <div
                      key={vid.id}
                      className="relative flex items-center gap-2 rounded-lg border px-2 py-1 text-[11px]"
                      style={{ borderColor: "var(--accent)", background: "var(--bg-panel)" }}
                    >
                      {vid.poster ? (
                        <img src={vid.poster} alt="" className="h-10 w-14 rounded object-cover" />
                      ) : (
                        <div className="flex h-10 w-14 items-center justify-center rounded" style={{ background: "var(--bg-elevated)" }}>
                          <Film className="h-4 w-4" style={{ color: "var(--accent)" }} />
                        </div>
                      )}
                      <div className="max-w-[155px] min-w-0 pr-4">
                        <div className="truncate font-medium">{vid.filename}</div>
                        <div className="text-[10px] truncate" style={{ color: "var(--text-muted)" }}>
                          {vid.durationSec ? `${vid.durationSec}s · ` : ""}
                          {vid.frameCount > 0 ? `已抽 ${vid.frameCount} 帧` : "视频"}
                          {vid.hasAudio ? (vid.audioTranscript ? " · 音频已转写" : " · 含音轨") : ""}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => setSelectedVideos((prev) => prev.filter((_, i) => i !== idx))}
                        className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full shadow"
                        style={{ background: "var(--bg-panel)", color: "var(--text-primary)", border: "1px solid var(--border-strong)" }}
                        title="移除视频"
                      >
                        <X className="h-2.5 w-2.5" />
                      </button>
                    </div>
                  ))}
                  {uploadingVideo && (
                    <span className="text-[11px]" style={{ color: "var(--accent)" }}>
                      正在压缩转码、抽帧并识别音频...
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedImgs([]);
                      setSelectedVideos([]);
                    }}
                    className="ml-auto text-[11px] hover:underline"
                    style={{ color: "var(--text-muted)" }}
                  >
                    清空 ({selectedImgs.length + selectedVideos.length})
                  </button>
                </div>
              )}

              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onPaste={handleTextareaPaste}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !(e.nativeEvent as any).isComposing) {
                    e.preventDefault();
                    if (!isStreaming) handleSend();
                  }
                }}
                rows={2}
                placeholder="输入你的行动、台词或角色设定…（Enter 发送，Shift+Enter 换行，支持粘贴/拖入图片或视频）"
                className="w-full resize-none bg-transparent px-3 sm:px-3.5 pt-2.5 sm:pt-3 pb-1.5 sm:pb-2 text-sm leading-relaxed outline-none"
                style={{ color: "var(--text-primary)" }}
              />

              <div
                className="flex flex-wrap items-center justify-between gap-1.5 sm:gap-2 border-t px-2 sm:px-3 py-1.5 sm:py-2 text-[11px] sm:text-xs"
                style={{ borderColor: "var(--border-subtle)" }}
              >
                <div className="flex flex-wrap items-center gap-1 sm:gap-1.5">
                  <button
                    type="button"
                    disabled={isStreaming || !activeChat?.messages?.length}
                    onClick={handleRerollChoices}
                    className="inline-flex items-center gap-1 rounded-lg border px-2 sm:px-2.5 py-1 disabled:opacity-40"
                    style={{ borderColor: "var(--border-subtle)", color: "var(--text-secondary)" }}
                  >
                    <RefreshCw className="h-3 w-3" />
                    换一批
                  </button>
                  <button
                    type="button"
                    disabled={isStreaming}
                    onClick={() => handleSend("顺其自然，继续推进当前剧情。")}
                    className="rounded-lg border px-2 sm:px-2.5 py-1 disabled:opacity-40"
                    style={{ borderColor: "var(--border-subtle)", color: "var(--text-secondary)" }}
                  >
                    顺其自然
                  </button>
                  <button
                    type="button"
                    disabled={!activeChat}
                    onClick={handleManualRoll}
                    className="inline-flex items-center gap-1 rounded-lg border px-2 sm:px-2.5 py-1 disabled:opacity-40"
                    style={{ borderColor: "var(--border-subtle)", color: "var(--text-secondary)" }}
                  >
                    <Dices className="h-3 w-3" />
                    投骰
                  </button>
                  <label
                    className="inline-flex cursor-pointer items-center gap-1 rounded-lg border px-2 sm:px-2.5 py-1"
                    style={{ borderColor: "var(--border-subtle)", color: "var(--text-secondary)" }}
                  >
                    <ImagePlus className="h-3 w-3" />
                    插图
                    <input type="file" accept="image/*" multiple className="hidden" onChange={handleImagePick} />
                  </label>
                  <label
                    className={`inline-flex items-center gap-1 rounded-lg border px-2 sm:px-2.5 py-1 ${uploadingVideo ? "opacity-50" : "cursor-pointer"}`}
                    style={{ borderColor: "var(--border-subtle)", color: "var(--text-secondary)" }}
                  >
                    <Film className="h-3 w-3" />
                    {uploadingVideo ? "上传中" : "视频"}
                    <input
                      type="file"
                      accept="video/mp4,video/webm,video/quicktime,video/ogg,.mp4,.webm,.mov,.m4v"
                      multiple
                      disabled={uploadingVideo}
                      className="hidden"
                      onChange={handleVideoPick}
                    />
                  </label>
                </div>

                <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
                  {input.length > 0 && (
                    <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                      {input.length} 字
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => setComposerExpanded((v) => !v)}
                    className="inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] hover:opacity-80"
                    style={{
                      borderColor: composerExpanded ? "var(--accent)" : "var(--border-subtle)",
                      color: composerExpanded ? "var(--accent)" : "var(--text-muted)",
                    }}
                    title={composerExpanded ? "收起输入框" : "展开大编辑框"}
                  >
                    {composerExpanded ? <Minimize2 className="h-3 w-3" /> : <Maximize2 className="h-3 w-3" />}
                    <span className="hidden sm:inline">{composerExpanded ? "收起" : "展开"}</span>
                  </button>
                  {isStreaming ? (
                    <button
                      type="button"
                      onClick={stopGeneration}
                      className="inline-flex h-7 sm:h-8 items-center gap-1.5 rounded-lg px-3 sm:px-3.5 text-xs font-medium"
                      style={{ background: "var(--danger)", color: "#fff" }}
                    >
                      <Square className="h-3.5 w-3.5" />
                      停止
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleSend()}
                      className="inline-flex h-7 sm:h-8 items-center gap-1.5 rounded-lg px-3 sm:px-3.5 text-xs font-medium"
                      style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
                    >
                      <Send className="h-3.5 w-3.5" />
                      发送
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {showInspector && <InspectorDrawer onClose={() => setShowInspector(false)} />}
    </div>
  );
}
