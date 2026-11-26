import { create } from "zustand";
import { apiFetch, streamSSE } from "../api/client";
import type {
  AppTab,
  BranchNode,
  CharacterCard,
  ChatFull,
  ChatSummary,
  DiceRollResult,
  EngineDiagnosis,
  ExperienceMode,
  HardwareSnapshot,
  LangId,
  LocalModelMeta,
  Persona,
  ProjectData,
  PromptPreset,
  ProviderPreset,
  ThemeId,
  UserSettings,
} from "../types/api";

const bc = typeof BroadcastChannel !== "undefined" ? new BroadcastChannel("easy-trpg-sync") : null;

interface AppState {
  initialized: boolean;
  activeTab: AppTab;
  experienceMode: ExperienceMode;
  theme: ThemeId;
  lang: LangId;
  showOnboarding: boolean;
  toastMsg: string;

  settings: UserSettings | null;
  hardware: HardwareSnapshot | null;
  providerPresets: ProviderPreset[];
  localModels: LocalModelMeta[];
  remoteModels: string[];
  favoriteModels: string[];

  projects: ProjectData[];
  exploreApps: ProjectData[];
  activeProjectId: string;

  chats: ChatSummary[];
  activeChat: ChatFull | null;
  branchTree: BranchNode[];

  cards: CharacterCard[];
  personas: Persona[];
  presets: PromptPreset[];

  isStreaming: boolean;
  streamingChatId: string | null;
  streamingText: string;
  streamingStatus: string;
  lastCacheHitTokens: number;
  streamAbort: AbortController | null;
  engineDiagnosis: EngineDiagnosis | null;

  initApp: () => Promise<void>;
  setTab: (tab: AppTab) => void;
  setExperienceMode: (mode: ExperienceMode) => Promise<void>;
  setTheme: (theme: ThemeId) => Promise<void>;
  setLang: (lang: LangId) => Promise<void>;
  dismissOnboarding: () => Promise<void>;
  openOnboarding: () => void;
  notify: (msg: string) => void;
  clearDiagnosis: () => void;

  refreshModels: () => Promise<void>;
  refreshProjectsAndExplore: () => Promise<void>;
  refreshChats: (projectId?: string) => Promise<void>;
  selectProject: (projectId: string) => Promise<void>;
  selectChat: (chatId: string) => Promise<void>;
  createNewChat: (projectId?: string, openingContent?: string) => Promise<string | null>;
  installExploreCampaign: (appId: string) => Promise<void>;
  saveSettingsPatch: (patch: Partial<UserSettings>) => Promise<UserSettings>;

  sendMessage: (opts: {
    content: string;
    images?: string[];
    videos?: Array<{ id: string; url: string; frames: string[] }>;
    cards?: CharacterCard[];
    regenerate?: boolean;
    targetUserMsgId?: string;
    diceRoll?: DiceRollResult;
  }) => Promise<void>;
  stopGeneration: () => Promise<void>;
  triggerSwipeGenerate: (msgId: string) => Promise<void>;
  switchSwipe: (msgId: string, swipeIdx: number) => Promise<void>;
  checkoutBranchNode: (nodeId: string) => Promise<void>;
  triggerGroupTurn: (cardId?: string) => Promise<void>;
  handleDiagnosisAction: (action: string) => Promise<void>;
}

export const useAppStore = create<AppState>((set, get) => {
  const pollUntilGenerationComplete = async (chatId: string, signal?: AbortSignal): Promise<boolean> => {
    let consecutiveNetErrs = 0;
    for (let i = 0; i < 240; i++) {
      if (signal?.aborted) return false;
      try {
        const latest = await apiFetch<ChatFull>(`/api/chats/${chatId}`);
        consecutiveNetErrs = 0;
        if (signal?.aborted) return false;

        if (latest.is_generating) {
          set((s) => ({
            streamingText: typeof latest.partial_text === "string" ? latest.partial_text : s.streamingText,
            streamingStatus:
              latest.generating_status ||
              (latest.partial_text ? "" : "连接波动，正在同步后台生成..."),
          }));
          await new Promise((r) => setTimeout(r, 1200));
          continue;
        }

        if (latest.last_error) {
          if (latest.last_error.diagnosis) {
            set({ engineDiagnosis: latest.last_error.diagnosis });
          } else {
            get().notify(latest.last_error.error || "生成失败");
          }
        }

        const treeRes = await apiFetch<{ nodes: BranchNode[] }>(`/api/chats/${chatId}/tree`).catch(() => ({ nodes: [] as BranchNode[] }));
        if (get().activeChat?.id === chatId || get().streamingChatId === chatId) {
          set({ activeChat: latest, branchTree: treeRes.nodes || [] });
        }
        await get().refreshChats(get().activeProjectId).catch(() => {});
        return true;
      } catch {
        consecutiveNetErrs += 1;
        if (consecutiveNetErrs > 8) return false;
        await new Promise((r) => setTimeout(r, 1500));
      }
    }
    return false;
  };

  return {
  initialized: false,
  activeTab: "play",
  experienceMode: "simple",
  theme: "lamplight-dark",
  lang: "zh-CN",
  showOnboarding: false,
  toastMsg: "",

  settings: null,
  hardware: null,
  providerPresets: [],
  localModels: [],
  remoteModels: [],
  favoriteModels: [],

  projects: [],
  exploreApps: [],
  activeProjectId: "proj_fast_trpg",

  chats: [],
  activeChat: null,
  branchTree: [],

  cards: [],
  personas: [],
  presets: [],

  isStreaming: false,
  streamingChatId: null,
  streamingText: "",
  streamingStatus: "",
  lastCacheHitTokens: 0,
  streamAbort: null,
  engineDiagnosis: null,

  notify: (msg: string) => {
    set({ toastMsg: msg });
    setTimeout(() => {
      if (get().toastMsg === msg) set({ toastMsg: "" });
    }, 3200);
  },

  clearDiagnosis: () => set({ engineDiagnosis: null }),

  initApp: async () => {
    try {
      const [settings, modelsRes, projectsRes, exploreRes, cardsRes, personasRes, presetsRes, provPresets] =
        await Promise.all([
          apiFetch<UserSettings>("/api/settings"),
          apiFetch<any>("/api/models"),
          apiFetch<ProjectData[]>("/api/projects"),
          apiFetch<any>("/api/explore"),
          apiFetch<CharacterCard[]>("/api/character_cards"),
          apiFetch<any>("/api/personas"),
          apiFetch<any>("/api/presets"),
          apiFetch<any>("/api/providers/presets"),
        ]);

      const theme: ThemeId = (settings.theme as ThemeId) || "lamplight-dark";
      const lang: LangId = (settings.language as LangId) || "zh-CN";
      const experienceMode: ExperienceMode = settings.experience_mode === "pro" ? "pro" : "simple";
      document.documentElement.setAttribute("data-theme", theme);

      const localModels: LocalModelMeta[] = modelsRes.local_models || [];
      const remoteModels: string[] = modelsRes.models || [];
      const activeProjId =
        settings.active_project_id && projectsRes.some((p) => p.id === settings.active_project_id)
          ? settings.active_project_id
          : projectsRes[0]?.id || "proj_fast_trpg";

      // Show onboarding ONLY when user hasn't finished it AND has neither local models nor remote models/key
      const hasAnyBrain = localModels.length > 0 || remoteModels.length > 0 || Boolean(settings.has_api_key);
      const shouldOnboard = !settings.onboarding_completed && !hasAnyBrain;

      set({
        initialized: true,
        settings,
        theme,
        lang,
        experienceMode,
        hardware: modelsRes.hardware || null,
        localModels,
        remoteModels,
        favoriteModels: modelsRes.favorite_models || [],
        providerPresets: provPresets.presets || [],
        projects: projectsRes,
        exploreApps: exploreRes.apps || [],
        activeProjectId: activeProjId,
        cards: cardsRes || [],
        personas: personasRes.personas || [],
        presets: presetsRes.presets || [],
        showOnboarding: shouldOnboard,
      });

      await get().refreshChats(activeProjId);
      const chats = get().chats;
      if (chats.length > 0) {
        await get().selectChat(chats[0].id);
      }

      if (bc) {
        bc.onmessage = (ev) => {
          if (ev.data?.type === "sync_chats") {
            get().refreshChats(get().activeProjectId);
          } else if (ev.data?.type === "sync_projects") {
            get().refreshProjectsAndExplore();
          }
        };
      }
    } catch (err: any) {
      set({ initialized: true });
      get().notify(`初始化失败: ${err?.message || err}`);
    }
  },

  setTab: (tab) => set({ activeTab: tab }),

  setExperienceMode: async (mode) => {
    set({ experienceMode: mode });
    if (mode === "simple" && (get().activeTab === "studio" || get().activeTab === "settings")) {
      set({ activeTab: "play" });
    }
    await get().saveSettingsPatch({ experience_mode: mode });
  },

  setTheme: async (theme) => {
    document.documentElement.setAttribute("data-theme", theme);
    set({ theme });
    await get().saveSettingsPatch({ theme });
  },

  setLang: async (lang) => {
    set({ lang });
    await get().saveSettingsPatch({ language: lang });
  },

  dismissOnboarding: async () => {
    set({ showOnboarding: false });
    await get().saveSettingsPatch({ onboarding_completed: true });
  },

  openOnboarding: () => set({ showOnboarding: true }),

  saveSettingsPatch: async (patch) => {
    const res = await apiFetch<any>("/api/settings", {
      method: "POST",
      body: JSON.stringify(patch),
    });
    const updated = res.settings || res;
    set({ settings: updated });
    return updated;
  },

  refreshModels: async () => {
    const res = await apiFetch<any>("/api/models");
    set({
      localModels: res.local_models || [],
      remoteModels: res.models || [],
      favoriteModels: res.favorite_models || [],
      hardware: res.hardware || get().hardware,
    });
  },

  refreshProjectsAndExplore: async () => {
    const [projects, explore] = await Promise.all([
      apiFetch<ProjectData[]>("/api/projects"),
      apiFetch<any>("/api/explore"),
    ]);
    set({ projects, exploreApps: explore.apps || [] });
  },

  refreshChats: async (projectId) => {
    const pid = projectId ?? get().activeProjectId;
    const chats = await apiFetch<ChatSummary[]>(`/api/chats?project_id=${encodeURIComponent(pid)}`);
    set({ chats });
  },

  selectProject: async (projectId) => {
    set({ activeProjectId: projectId, activeChat: null, branchTree: [] });
    await get().saveSettingsPatch({ active_project_id: projectId });
    await get().refreshChats(projectId);
    const list = get().chats;
    if (list.length > 0) {
      await get().selectChat(list[0].id);
    }
  },

  selectChat: async (chatId) => {
    const [chat, treeRes] = await Promise.all([
      apiFetch<ChatFull>(`/api/chats/${chatId}`),
      apiFetch<{ active_node_id: string; nodes: BranchNode[] }>(`/api/chats/${chatId}/tree`),
    ]);
    set({ activeChat: chat, branchTree: treeRes.nodes || [] });
    if (chat.is_generating && !get().isStreaming) {
      set({
        isStreaming: true,
        streamingChatId: chatId,
        streamingText: chat.partial_text || "",
        streamingStatus: chat.generating_status || "后台生成中...",
      });
      void (async () => {
        try {
          await pollUntilGenerationComplete(chatId);
        } finally {
          if (get().streamingChatId === chatId) {
            set({ isStreaming: false, streamingChatId: null, streamingText: "", streamingStatus: "", streamAbort: null });
          }
        }
      })();
    }
  },

  createNewChat: async (projectId, openingContent) => {
    const pid = projectId || get().activeProjectId;
    const chat = await apiFetch<ChatFull>("/api/chats", {
      method: "POST",
      body: JSON.stringify({
        project_id: pid,
        include_opening: Boolean(openingContent),
        opening_content: openingContent || "",
      }),
    });
    await get().refreshChats(pid);
    await get().selectChat(chat.id);
    bc?.postMessage({ type: "sync_chats" });
    return chat.id;
  },

  installExploreCampaign: async (appId) => {
    const res = await apiFetch<any>("/api/explore/install", {
      method: "POST",
      body: JSON.stringify({ app_id: appId }),
    });
    await get().refreshProjectsAndExplore();
    const cards = await apiFetch<CharacterCard[]>("/api/character_cards");
    set({ cards, activeProjectId: res.project.id, activeTab: "play" });
    await get().refreshChats(res.project.id);
    if (res.chat_id) {
      await get().selectChat(res.chat_id);
    }
    bc?.postMessage({ type: "sync_projects" });
    get().notify(`已进入剧本「${res.project.name}」`);
  },

  sendMessage: async ({ content, images, videos, cards, regenerate, targetUserMsgId, diceRoll }) => {
    let chat = get().activeChat;
    if (!chat) {
      const cid = await get().createNewChat();
      if (!cid) return;
      chat = get().activeChat;
      if (!chat) return;
    }

    const ctrl = new AbortController();
    set({
      isStreaming: true,
      streamingChatId: chat.id,
      streamingText: "",
      streamingStatus: "准备中...",
      engineDiagnosis: null,
      streamAbort: ctrl,
    });

    const videoList = videos || [];
    const videoUrls = videoList.map((v) => v.url);
    const videoIds = videoList.map((v) => v.id);
    const videoFrameImages = videoList.flatMap((v) => v.frames || []).slice(0, 36);

    // Optimistic append user message for instant UI feedback
    if (!regenerate && (content.trim() || (images && images.length > 0) || videoUrls.length > 0)) {
      const optMsg = {
        id: "tmp_" + Date.now(),
        role: "user" as const,
        content: content.trim() || (videoUrls.length > 0 ? "【附带视频】" : "【附带图片】"),
        images: images || [],
        videos: videoUrls,
        dice_rolls: diceRoll ? [diceRoll] : [],
        timestamp: Date.now() / 1000,
      };
      set({
        activeChat: { ...chat, messages: [...chat.messages, optMsg] },
      });
    }

    let receivedDone = false;
    let receivedError = false;
    try {
      await streamSSE(
        "/api/chat/stream",
        {
          chat_id: chat.id,
          content,
          model: get().settings?.model || chat.model || "",
          images_base64: images || [],
          video_ids: videoIds,
          video_frame_images: videoFrameImages,
          character_cards: cards || [],
          regenerate: Boolean(regenerate),
          target_user_msg_id: targetUserMsgId,
          dice_roll: diceRoll,
        },
        (ev) => {
          if (ev.status) {
            set({ streamingStatus: String(ev.status) });
          } else if (ev.chunk) {
            set((s) => ({ streamingText: s.streamingText + String(ev.chunk), streamingStatus: "" }));
          } else if (typeof ev.replace === "string") {
            set({ streamingText: ev.replace });
          } else if (ev.error) {
            receivedError = true;
            if (ev.diagnosis) {
              set({ engineDiagnosis: ev.diagnosis as EngineDiagnosis });
            } else {
              get().notify(String(ev.error));
            }
          } else if (ev.done) {
            receivedDone = true;
            set({ lastCacheHitTokens: Number(ev.cache_read_tokens || 0) });
          }
        },
        ctrl.signal
      );
      if (!receivedDone && !receivedError && !ctrl.signal.aborted) {
        await pollUntilGenerationComplete(chat.id, ctrl.signal);
      } else {
        await get().selectChat(chat.id);
        await get().refreshChats(get().activeProjectId);
      }
      bc?.postMessage({ type: "sync_chats" });
    } catch (err: any) {
      if (err?.name !== "AbortError") {
        const recovered = !receivedDone && !receivedError ? await pollUntilGenerationComplete(chat.id, ctrl.signal) : false;
        if (!recovered) {
          get().notify(err?.message || "连接已断开，请重试");
        }
      }
    } finally {
      set({ isStreaming: false, streamingChatId: null, streamingText: "", streamingStatus: "", streamAbort: null });
    }
  },

  stopGeneration: async () => {
    const cid = get().streamingChatId || get().activeChat?.id;
    get().streamAbort?.abort();
    if (cid) {
      await apiFetch(`/api/chats/${cid}/stop`, { method: "POST" }).catch(() => {});
      await get().selectChat(cid).catch(() => {});
    }
    set({ isStreaming: false, streamingChatId: null, streamingText: "", streamingStatus: "", streamAbort: null });
  },

  triggerSwipeGenerate: async (msgId) => {
    const chat = get().activeChat;
    if (!chat) return;
    const ctrl = new AbortController();
    set({
      isStreaming: true,
      streamingChatId: chat.id,
      streamingText: "",
      streamingStatus: "正在生成新候选回复...",
      engineDiagnosis: null,
      streamAbort: ctrl,
    });
    let receivedDone = false;
    let receivedError = false;
    try {
      await streamSSE(
        `/api/chats/${chat.id}/messages/${msgId}/swipe`,
        { model: get().settings?.model || chat.model || "" },
        (ev) => {
          if (ev.status) set({ streamingStatus: String(ev.status) });
          else if (ev.chunk) set((s) => ({ streamingText: s.streamingText + String(ev.chunk), streamingStatus: "" }));
          else if (ev.error) {
            receivedError = true;
            if (ev.diagnosis) set({ engineDiagnosis: ev.diagnosis as EngineDiagnosis });
            else get().notify(String(ev.error));
          } else if (ev.done) {
            receivedDone = true;
          }
        },
        ctrl.signal
      );
      if (!receivedDone && !receivedError && !ctrl.signal.aborted) {
        await pollUntilGenerationComplete(chat.id, ctrl.signal);
      } else {
        await get().selectChat(chat.id);
      }
    } catch (err: any) {
      if (err?.name !== "AbortError") {
        const recovered = !receivedDone && !receivedError ? await pollUntilGenerationComplete(chat.id, ctrl.signal) : false;
        if (!recovered) get().notify(err?.message || "连接已断开，请重试");
      }
    } finally {
      set({ isStreaming: false, streamingChatId: null, streamingText: "", streamingStatus: "", streamAbort: null });
    }
  },

  switchSwipe: async (msgId, swipeIdx) => {
    const chat = get().activeChat;
    if (!chat) return;
    const res = await apiFetch<any>(`/api/chats/${chat.id}/messages/${msgId}/active_swipe`, {
      method: "PUT",
      body: JSON.stringify({ swipe_idx: swipeIdx }),
    });
    if (res.chat) set({ activeChat: res.chat });
  },

  checkoutBranchNode: async (nodeId) => {
    const chat = get().activeChat;
    if (!chat) return;
    const res = await apiFetch<any>(`/api/chats/${chat.id}/checkout`, {
      method: "POST",
      body: JSON.stringify({ node_id: nodeId }),
    });
    set({ activeChat: res.chat, branchTree: res.tree?.nodes || [] });
  },

  triggerGroupTurn: async (cardId) => {
    const chat = get().activeChat;
    if (!chat) return;
    const ctrl = new AbortController();
    set({
      isStreaming: true,
      streamingChatId: chat.id,
      streamingText: "",
      streamingStatus: "队友思考中...",
      streamAbort: ctrl,
    });
    let receivedDone = false;
    let receivedError = false;
    try {
      await streamSSE(
        `/api/chats/${chat.id}/group_turn`,
        { card_id: cardId || "", model: get().settings?.model || chat.model || "" },
        (ev) => {
          if (ev.status) set({ streamingStatus: String(ev.status) });
          else if (ev.chunk) set((s) => ({ streamingText: s.streamingText + String(ev.chunk), streamingStatus: "" }));
          else if (ev.error) {
            receivedError = true;
            get().notify(String(ev.error));
          } else if (ev.done) {
            receivedDone = true;
          }
        },
        ctrl.signal
      );
      if (!receivedDone && !receivedError && !ctrl.signal.aborted) {
        await pollUntilGenerationComplete(chat.id, ctrl.signal);
      } else {
        await get().selectChat(chat.id);
      }
    } catch (err: any) {
      if (err?.name !== "AbortError") {
        const recovered = !receivedDone && !receivedError ? await pollUntilGenerationComplete(chat.id, ctrl.signal) : false;
        if (!recovered) get().notify(err?.message || "连接已断开，请重试");
      }
    } finally {
      set({ isStreaming: false, streamingChatId: null, streamingText: "", streamingStatus: "", streamAbort: null });
    }
  },

  handleDiagnosisAction: async (action) => {
    if (action === "enable_low_spec") {
      await get().saveSettingsPatch({ low_spec_mode: "on", max_context_k: 8 });
      set({ engineDiagnosis: null });
      get().notify("已开启低配安全模式，请重新发送");
    } else if (action === "open_engine_downloads") {
      set({ activeTab: "engine", engineDiagnosis: null });
    } else if (action === "open_api_setup") {
      set({ showOnboarding: true, engineDiagnosis: null });
    } else if (action === "run_preflight") {
      set({ activeTab: "engine", engineDiagnosis: null });
    }
  },
  };
});
