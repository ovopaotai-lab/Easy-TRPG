// ================= 全局状态 =================
const LEGACY_PRESET_PROJECT_IDS = new Set();
let currentProjectId = "proj_default";
let currentChatId = null;
let projectsMap = {};
let availableModelsData = null;
let currentChatData = null;
let currentUser = null;

// 待发送多图队列 (Base64 Data URLs)
let selectedImages = [];

// 角色卡库与待发送角色卡队列 (OpenTavern 格式)
let allCharacterCards = [];
let selectedCharacterCards = [];
let currentCharEditAvatar = "";

// 多会话并发后台生成追踪与未读集合
const activeStreams = {}; // { [chatId]: { controller, text, bubbleEl, itemEl, msgId, isAbortedForRegen } }
const unreadChats = new Set();
let cachedChatList = [];

// 素材库状态
let selectedGalleryImageIds = new Set();
let cachedGalleryList = [];

// ================= DOM 元素引用 =================
const appLayout = document.getElementById("appLayout");
const sidebarEl = document.getElementById("sidebar");
const sidebarBackdrop = document.getElementById("sidebarBackdrop");
const btnToggleMobileMenu = document.getElementById("btnToggleMobileMenu");
const btnCloseMobileSidebar = document.getElementById("btnCloseMobileSidebar");

// 登录与认证
const loginOverlay = document.getElementById("loginOverlay");
const loginForm = document.getElementById("loginForm");
const loginUsername = document.getElementById("loginUsername");
const loginPassword = document.getElementById("loginPassword");
const btnTogglePwdVis = document.getElementById("btnTogglePwdVis");
const loginError = document.getElementById("loginError");
const displayUsername = document.getElementById("displayUsername");
const displayUserStatus = document.getElementById("displayUserStatus");
const btnLogout = document.getElementById("btnLogout");
const btnLogoutModalBtn = document.getElementById("btnLogoutModalBtn");

// 用户与安全审计弹窗
const btnOpenUserModal = document.getElementById("btnOpenUserModal");
const userModal = document.getElementById("userModal");
const btnCloseUserModal = document.getElementById("btnCloseUserModal");
const btnCloseUserModalBtn = document.getElementById("btnCloseUserModalBtn");
const userModalName = document.getElementById("userModalName");
const currDeviceName = document.getElementById("currDeviceName");
const currClientIp = document.getElementById("currClientIp");
const loginHistoryTableBody = document.getElementById("loginHistoryTableBody");
const btnToggleChangePwd = document.getElementById("btnToggleChangePwd");
const changePwdBox = document.getElementById("changePwdBox");
const oldPasswordInput = document.getElementById("oldPasswordInput");
const newPasswordInput = document.getElementById("newPasswordInput");
const btnCancelChangePwd = document.getElementById("btnCancelChangePwd");
const btnSubmitChangePwd = document.getElementById("btnSubmitChangePwd");

// 侧边栏游戏与对话列表
const projectPillsList = document.getElementById("projectPillsList");
const btnNewProject = document.getElementById("btnNewProject");
const btnEditProject = document.getElementById("btnEditProject");
const chatListEl = document.getElementById("chatList");
const chatCountBadge = document.getElementById("chatCountBadge");
const btnNewChat = document.getElementById("btnNewChat");

// 顶栏与模型选择
const titleClickArea = document.getElementById("titleClickArea");
const currentChatTitleEl = document.getElementById("currentChatTitle");
const btnRenameChat = document.getElementById("btnRenameChat");
const activeProjectBadge = document.getElementById("activeProjectBadge");
const activeProjectNameEl = document.getElementById("activeProjectName");
const headerModelSelect = document.getElementById("headerModelSelect");
const btnToggleSummary = document.getElementById("btnToggleSummary");
const summaryDot = document.getElementById("summaryDot");
const btnTriggerSummary = document.getElementById("btnTriggerSummary");
const btnClearHistory = document.getElementById("btnClearHistory");

// 移动端更多操作菜单
const btnMobileMoreActions = document.getElementById("btnMobileMoreActions");
const mobileMoreMenu = document.getElementById("mobileMoreMenu");
const btnMobileEditProject = document.getElementById("btnMobileEditProject");
const btnMobileTriggerSummary = document.getElementById("btnMobileTriggerSummary");
const btnMobileOpenSettings = document.getElementById("btnMobileOpenSettings");
const btnMobileOpenRemote = document.getElementById("btnMobileOpenRemote");
const btnMobileOpenUser = document.getElementById("btnMobileOpenUser");
const btnMobileClearHistory = document.getElementById("btnMobileClearHistory");
const btnMobileLogout = document.getElementById("btnMobileLogout");

// 前情提要备忘卡片
const summaryCard = document.getElementById("summaryCard");
const summaryTextEl = document.getElementById("summaryText");
const summaryEditBox = document.getElementById("summaryEditBox");
const summaryEditTextarea = document.getElementById("summaryEditTextarea");
const btnEditSummary = document.getElementById("btnEditSummary");
const btnSaveSummaryEdit = document.getElementById("btnSaveSummaryEdit");
const btnCancelSummaryEdit = document.getElementById("btnCancelSummaryEdit");
const btnCloseSummaryCard = document.getElementById("btnCloseSummaryCard");

// 消息流与输入栏
const messageContainer = document.getElementById("messageContainer");
const welcomeBox = document.getElementById("welcomeBox");
const btnScrollBottom = document.getElementById("btnScrollBottom");
const userInput = document.getElementById("userInput");
const btnSend = document.getElementById("btnSend");
const btnStop = document.getElementById("btnStop");
const btnRegenerateLatest = document.getElementById("btnRegenerateLatest");

// 图片上传、多图预览与灯箱
const fileInput = document.getElementById("fileInput");
const imagePreviewBar = document.getElementById("imagePreviewBar");
const imagePreviewList = document.getElementById("imagePreviewList");
const previewCountHint = document.getElementById("previewCountHint");
const btnClearAllImages = document.getElementById("btnClearAllImages");
const imageLightbox = document.getElementById("imageLightbox");
const lightboxImg = document.getElementById("lightboxImg");

// 快捷骰子
const btnRollD100 = document.getElementById("btnRollD100");
const btnRollD20 = document.getElementById("btnRollD20");
const btnRoll3D6 = document.getElementById("btnRoll3D6");

// 账号素材图库弹窗
const btnOpenGalleryModal = document.getElementById("btnOpenGalleryModal");
const galleryModal = document.getElementById("galleryModal");
const btnCloseGalleryModal = document.getElementById("btnCloseGalleryModal");
const galleryTotalCount = document.getElementById("galleryTotalCount");
const galleryFileInput = document.getElementById("galleryFileInput");
const galleryGrid = document.getElementById("galleryGrid");
const galleryEmptyHint = document.getElementById("galleryEmptyHint");
const gallerySelectedCount = document.getElementById("gallerySelectedCount");
const btnSelectAllGallery = document.getElementById("btnSelectAllGallery");
const btnClearSelectionGallery = document.getElementById("btnClearSelectionGallery");
const btnInsertSelectedImages = document.getElementById("btnInsertSelectedImages");
const galleryCountBadge = document.getElementById("galleryCountBadge");

// 游戏设置弹窗
const projectModal = document.getElementById("projectModal");
const btnCloseProjectModal = document.getElementById("btnCloseProjectModal");
const projNameInput = document.getElementById("projNameInput");
const projSystemInput = document.getElementById("projSystemInput");
const projPrefixInput = document.getElementById("projPrefixInput");
const projSuffixInput = document.getElementById("projSuffixInput");
const projContextTurnsInput = document.getElementById("projContextTurnsInput");
const turnsCalcHint = document.getElementById("turnsCalcHint");
const projAutoSummarizeInput = document.getElementById("projAutoSummarizeInput");
const btnSaveProject = document.getElementById("btnSaveProject");
const btnDeleteCurrentProject = document.getElementById("btnDeleteCurrentProject");

// API 与模型设置弹窗
const settingsModal = document.getElementById("settingsModal");
const btnOpenSettings = document.getElementById("btnOpenSettings");
const btnCloseSettingsModal = document.getElementById("btnCloseSettingsModal");
const settingBaseUrl = document.getElementById("settingBaseUrl");
const settingApiKey = document.getElementById("settingApiKey");
const settingModel = document.getElementById("settingModel");
const settingModelSelect = document.getElementById("settingModelSelect");
const btnRefreshModels = document.getElementById("btnRefreshModels");
const chkCustomModel = document.getElementById("chkCustomModel");
const settingProxy = document.getElementById("settingProxy");
const settingUseProxy = document.getElementById("settingUseProxy");
const settingTemperature = document.getElementById("settingTemperature");
const btnSaveSettings = document.getElementById("btnSaveSettings");

// 远程访问弹窗
const btnSidebarRemote = document.getElementById("btnSidebarRemote");
const btnOpenRemoteModal = document.getElementById("btnOpenRemoteModal");
const remoteModal = document.getElementById("remoteModal");
const btnCloseRemoteModal = document.getElementById("btnCloseRemoteModal");
const btnCloseRemoteModalBtn = document.getElementById("btnCloseRemoteModalBtn");
const remotePublicUrl = document.getElementById("remotePublicUrl");
const remoteLanUrl = document.getElementById("remoteLanUrl");
const remoteLocalUrl = document.getElementById("remoteLocalUrl");
const btnCopyPublicUrl = document.getElementById("btnCopyPublicUrl");
const btnCopyLanUrl = document.getElementById("btnCopyLanUrl");
const btnCopyLocalUrl = document.getElementById("btnCopyLocalUrl");

// 通用无感自定义对话框
const customDialogModal = document.getElementById("customDialogModal");
const customDialogTitle = document.getElementById("customDialogTitle");
const customDialogMessage = document.getElementById("customDialogMessage");
const customDialogInput = document.getElementById("customDialogInput");
const btnCloseCustomDialog = document.getElementById("btnCloseCustomDialog");
const btnCustomDialogCancel = document.getElementById("btnCustomDialogCancel");
const btnCustomDialogConfirm = document.getElementById("btnCustomDialogConfirm");

// ================= 通用工具函数 =================
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// 用于内联事件属性中单引号 JS 字符串的转义：先做 JS 字符串转义，再做 HTML 属性转义
function escapeJsStrAttr(str) {
  return String(str ?? "")
    .replace(/\\/g, "\\\\")
    .replace(/'/g, "\\'")
    .replace(/\r/g, "\\r")
    .replace(/\n/g, "\\n")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function showToast(message) {
  let container = document.getElementById("toastContainer");
  if (!container) {
    container = document.createElement("div");
    container.id = "toastContainer";
    container.className = "toast-container";
    document.body.appendChild(container);
  }
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = typeof window.tStr === "function" ? window.tStr(message) : message;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("show"));
  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => toast.remove(), 250);
  }, 1800);
}

// 替代丑陋原生 prompt / confirm 的现代化异步对话框
function showCustomDialog({ title = "提示", message = "", isPrompt = false, defaultValue = "", placeholder = "" }) {
  return new Promise((resolve) => {
    const tr = (s) => (typeof window.tStr === "function" ? window.tStr(s) : s);
    if (!customDialogModal) {
      if (isPrompt) resolve(window.prompt(tr(message || title), tr(defaultValue)));
      else resolve(window.confirm(tr(message || title)));
      return;
    }
    customDialogTitle.textContent = tr(title);
    customDialogMessage.textContent = tr(message);
    customDialogMessage.style.display = message ? "block" : "none";

    if (isPrompt) {
      customDialogInput.style.display = "block";
      customDialogInput.value = tr(defaultValue || "");
      customDialogInput.placeholder = tr(placeholder || "");
    } else {
      customDialogInput.style.display = "none";
    }

    customDialogModal.style.display = "flex";
    if (typeof window.translateSubtree === "function") {
      window.translateSubtree(customDialogModal);
    }
    if (isPrompt) {
      setTimeout(() => {
        customDialogInput.focus();
        customDialogInput.select();
      }, 30);
    }

    const cleanup = (result) => {
      customDialogModal.style.display = "none";
      btnCustomDialogConfirm.onclick = null;
      btnCustomDialogCancel.onclick = null;
      btnCloseCustomDialog.onclick = null;
      customDialogInput.onkeydown = null;
      resolve(result);
    };

    btnCustomDialogConfirm.onclick = () => {
      cleanup(isPrompt ? customDialogInput.value : true);
    };
    btnCustomDialogCancel.onclick = () => {
      cleanup(isPrompt ? null : false);
    };
    btnCloseCustomDialog.onclick = () => {
      cleanup(isPrompt ? null : false);
    };
    customDialogInput.onkeydown = (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        cleanup(customDialogInput.value);
      } else if (e.key === "Escape") {
        cleanup(null);
      }
    };
  });
}

function getShortModelName(modelId) {
  if (!modelId) return "未配置模型";
  const clean = modelId.replace(/^\[.*?\]/, "");
  if (clean.includes("gemini-2.5-pro")) return "Gemini 2.5P";
  if (clean.includes("gemini-2.5-flash")) return "Gemini 2.5F";
  if (clean.includes("claude-sonnet") || clean.includes("sonnet")) return "Sonnet";
  if (clean.includes("claude-opus") || clean.includes("opus")) return "Opus";
  if (clean.includes("deepseek")) return "DeepSeek";
  return clean.length > 13 ? clean.slice(0, 12) + "…" : clean;
}

// ================= 网络拦截：自动携带 Bearer Token 与 Cookie =================
const originalFetch = window.fetch;
window.fetch = function (url, options = {}) {
  const isApi = typeof url === "string" && (url.startsWith("/api") || url.startsWith("./api"));
  if (isApi) {
    options = options || {};
    options.credentials = "include";
    const token = localStorage.getItem("session_token");
    if (token) {
      if (!options.headers) {
        options.headers = { Authorization: `Bearer ${token}` };
      } else if (options.headers instanceof Headers) {
        if (!options.headers.has("Authorization")) {
          options.headers.set("Authorization", `Bearer ${token}`);
        }
      } else if (typeof options.headers === "object") {
        if (!options.headers["Authorization"] && !options.headers["authorization"]) {
          options.headers["Authorization"] = `Bearer ${token}`;
        }
      }
    }
  }
  return originalFetch.call(this, url, options);
};

// ================= 认证与初始化（纯净免登录版） =================
async function checkAuth() {
  if (loginOverlay) loginOverlay.style.display = "none";
  if (appLayout) appLayout.style.display = "flex";
  try {
    const res = await fetch("/api/auth/me");
    if (res.ok) {
      const data = await res.json();
      currentUser = data.user || { username: "player", role: "admin" };
      return true;
    }
  } catch (err) {
    console.warn("本地服务初始化检测:", err);
  }
  currentUser = { username: "player", role: "admin" };
  return true;
}

function updateUserUI() {
  // 纯净版已关闭账号系统，保留工作台标题展示
}

async function handleLoginSubmit(e) {
  e.preventDefault();
}

async function handleLogout() {
  if (userModal) userModal.style.display = "none";
  if (mobileMoreMenu) mobileMoreMenu.style.display = "none";
}

let _panelAnimatingTimer = null;
window.markPanelAnimating = function (durationMs = 240) {
  document.body.classList.add("panel-animating");
  if (_panelAnimatingTimer) clearTimeout(_panelAnimatingTimer);
  _panelAnimatingTimer = setTimeout(() => {
    document.body.classList.remove("panel-animating");
    _panelAnimatingTimer = null;
    if (typeof window.triggerTavernAutoAdaptLayout === "function") {
      requestAnimationFrame(window.triggerTavernAutoAdaptLayout);
    }
  }, durationMs);
};

// 与 style.css 中 @media (max-width: 900px) 抽屉规则保持同一断点，避免 641~900px 区间点击 [面板] 无反应
const DRAWER_BREAKPOINT_MQ = "(max-width: 900px)";
const PHONE_BREAKPOINT_MQ = "(max-width: 768px)";

function isEffectivePortraitDrawerMode() {
  if (document.body.classList.contains("gui-portrait-mode")) return true;
  return window.matchMedia ? window.matchMedia(DRAWER_BREAKPOINT_MQ).matches : window.innerWidth <= 900;
}

function syncDrawerToggleButtonUI() {
  const btn = document.getElementById("btnToggleMobileMenu");
  if (!btn) return;
  const isOverlayMode = isEffectivePortraitDrawerMode();
  const isOpen = isOverlayMode
    ? Boolean(sidebarEl?.classList.contains("mobile-open"))
    : !document.body.classList.contains("desktop-sidebar-collapsed");
  const isEn = window.currentAppLang === "en";
  btn.classList.toggle("drawer-open-active", isOpen);
  btn.setAttribute("aria-expanded", isOpen ? "true" : "false");
  const span = btn.querySelector("span") || btn;
  const zhText = isOpen ? "收起" : "面板";
  const enText = isOpen ? "Hide" : "Panel";
  span._origZhText = zhText;
  span.textContent = isEn ? enText : zhText;
  span._lastEnText = span.textContent;
}
window.syncDrawerToggleButtonUI = syncDrawerToggleButtonUI;

function openMobileSidebar() {
  window.markPanelAnimating(250);
  document.body.classList.remove("desktop-sidebar-collapsed");
  document.body.classList.add("mobile-drawer-open");
  sidebarEl?.classList.add("mobile-open");
  if (sidebarBackdrop) sidebarBackdrop.style.display = "block";
  syncDrawerToggleButtonUI();
}

function closeMobileSidebar() {
  window.markPanelAnimating(250);
  document.body.classList.remove("mobile-drawer-open");
  sidebarEl?.classList.remove("mobile-open");
  if (sidebarBackdrop) sidebarBackdrop.style.display = "none";
  syncDrawerToggleButtonUI();
}

// 界面方向偏好：auto（默认，按设备宽度自动适配）/ landscape / portrait
// 仅保存在本机 localStorage，不再同步到服务器，避免手机选了竖屏导致电脑端也被压成 480px 窄列
const GUI_ORIENT_PREF_KEY = "trpg_gui_orientation_pref";

function getGuiOrientationPref() {
  try {
    const pref = localStorage.getItem(GUI_ORIENT_PREF_KEY);
    if (pref === "auto" || pref === "portrait" || pref === "landscape") return pref;
    // 兼容旧版本（一次性迁移）：旧版每次启动都会写入 landscape，只有 portrait 代表用户曾主动选择
    const legacy = localStorage.getItem("trpg_gui_orientation");
    localStorage.removeItem("trpg_gui_orientation");
    const migrated = legacy === "portrait" ? "portrait" : "auto";
    localStorage.setItem(GUI_ORIENT_PREF_KEY, migrated);
    return migrated;
  } catch (e) {}
  return "auto";
}

window.resolveGuiOrientation = function (pref) {
  const p = pref || getGuiOrientationPref();
  if (p === "portrait" || p === "landscape") return p;
  const isPhoneWidth = window.matchMedia ? window.matchMedia(PHONE_BREAKPOINT_MQ).matches : window.innerWidth <= 768;
  return isPhoneWidth ? "portrait" : "landscape";
};

window.getGuiOrientation = function () {
  return document.body.classList.contains("gui-portrait-mode") ? "portrait" : "landscape";
};

window.setGuiOrientation = function (mode, silent = false) {
  const pref = mode === "portrait" || mode === "landscape" || mode === "auto" ? mode : "auto";
  // silent 调用（启动 / 加载设置 / 自动跟随）始终按本机保存的偏好执行，不改变偏好本身
  const effectivePref = silent ? getGuiOrientationPref() : pref;
  const normalized = window.resolveGuiOrientation(effectivePref);
  const isPortrait = normalized === "portrait";
  const changed = !document.body.classList.contains(isPortrait ? "gui-portrait-mode" : "gui-landscape-mode");

  document.body.classList.toggle("gui-portrait-mode", isPortrait);
  document.body.classList.toggle("gui-landscape-mode", !isPortrait);

  const hiddenInp = document.getElementById("settingGuiOrientation");
  if (hiddenInp) hiddenInp.value = normalized;

  const btnLandscape = document.getElementById("btnGuiOrientLandscape");
  const btnPortrait = document.getElementById("btnGuiOrientPortrait");
  const btnAuto = document.getElementById("btnGuiOrientAuto");
  if (btnAuto) btnAuto.classList.toggle("active", effectivePref === "auto");
  if (btnLandscape) btnLandscape.classList.toggle("active", effectivePref === "landscape");
  if (btnPortrait) btnPortrait.classList.toggle("active", effectivePref === "portrait");

  if (!silent) {
    try {
      localStorage.setItem(GUI_ORIENT_PREF_KEY, pref);
    } catch (e) {}
  }

  if (window.globalUserSettings) {
    window.globalUserSettings.gui_orientation = normalized;
  }

  // 仅在方向真正变化或用户主动切换时收起抽屉，避免每次打开模型设置都把侧栏关掉
  if (changed || !silent) {
    if (isPortrait) {
      document.body.classList.add("desktop-sidebar-collapsed");
    }
    closeMobileSidebar();
  }
  syncDrawerToggleButtonUI();

  if (typeof window.triggerTavernAutoAdaptLayout === "function") {
    window.triggerTavernAutoAdaptLayout();
  }

  if (!silent) {
    const isEn = window.currentAppLang === "en";
    const msg = pref === "auto"
      ? (isEn ? `Auto (${isPortrait ? "portrait" : "landscape"})` : `自动（${isPortrait ? "竖屏" : "横屏"}）`)
      : (isPortrait ? (isEn ? "Portrait" : "竖屏") : (isEn ? "Landscape" : "横屏"));
    showToast(msg);
  }
};

let _lastSidebarToggleAt = 0;
window.toggleDesktopSidebar = function (event) {
  if (event) event.stopPropagation();
  const now = Date.now();
  if (now - _lastSidebarToggleAt < 180) return;
  _lastSidebarToggleAt = now;

  window.markPanelAnimating(240);
  if (isEffectivePortraitDrawerMode()) {
    if (sidebarEl?.classList.contains("mobile-open")) {
      window.closeAnySidebarDrawer();
    } else {
      openMobileSidebar();
    }
    return;
  }
  document.body.classList.toggle("desktop-sidebar-collapsed");
  if (sidebarBackdrop) {
    sidebarBackdrop.style.display = "none";
  }
  syncDrawerToggleButtonUI();
};

window.closeAnySidebarDrawer = function () {
  closeMobileSidebar();
  if (isEffectivePortraitDrawerMode()) {
    document.body.classList.add("desktop-sidebar-collapsed");
  }
  syncDrawerToggleButtonUI();
};

let _lastPlusPopoverToggleAt = 0;
window.closeMinimalistPlusPopover = function () {
  const pop = document.getElementById("minimalistPlusPopover");
  const btn = document.getElementById("btnTogglePlusPopover") || document.getElementById("btnMinimalistPlus");
  if (pop) pop.style.display = "none";
  if (btn) btn.classList.remove("popover-open-active");
  if (typeof window.updateScrollBottomBtnVisibility === "function") {
    window.updateScrollBottomBtnVisibility();
  }
};

window.toggleMinimalistPlusPopover = function (event) {
  if (event) event.stopPropagation();
  const now = Date.now();
  if (now - _lastPlusPopoverToggleAt < 150) return;
  _lastPlusPopoverToggleAt = now;

  const pop = document.getElementById("minimalistPlusPopover");
  const btn = document.getElementById("btnTogglePlusPopover") || document.getElementById("btnMinimalistPlus");
  if (!pop) return;
  const isVis = pop.style.display !== "none" && pop.style.display !== "";
  const nextOpen = !isVis;
  pop.style.display = nextOpen ? "flex" : "none";
  if (btn) btn.classList.toggle("popover-open-active", nextOpen);
  if (typeof window.updateScrollBottomBtnVisibility === "function") {
    window.updateScrollBottomBtnVisibility();
  }
};

document.addEventListener("click", (e) => {
  const pop = document.getElementById("minimalistPlusPopover");
  const btn = document.getElementById("btnTogglePlusPopover") || document.getElementById("btnMinimalistPlus");
  if (!pop) return;
  if (pop.style.display !== "none" && pop.style.display !== "") {
    if (!pop.contains(e.target) && e.target !== btn && !btn?.contains(e.target)) {
      window.closeMinimalistPlusPopover();
    } else if (pop.contains(e.target) && e.target.closest("button, label")) {
      window.closeMinimalistPlusPopover();
    }
  } else if (btn && btn.classList.contains("popover-open-active") && e.target !== btn && !btn.contains(e.target)) {
    btn.classList.remove("popover-open-active");
  }
});

async function initAppContent() {
  await loadSettings();
  await loadProjects();
  await loadChats();
  loadModels();
  updateGalleryCountBadge();
  loadCharacterCards();
}

async function initApp() {
  if (window.marked) {
    marked.setOptions({ breaks: true, gfm: true });
  }
  window.setGuiOrientation("auto", true);
  setupEventListeners();
  initUniversalResizersAndAutoAdapt();
  initResponsiveViewportWatchers();
  const isAuthed = await checkAuth();
  if (isAuthed) {
    await initAppContent();
  }
}

// ================= 响应式：断点 / 旋转 / 软键盘 视口监听 =================
function initResponsiveViewportWatchers() {
  if (!window.matchMedia) return;
  const mqPhone = window.matchMedia(PHONE_BREAKPOINT_MQ);
  const mqDrawer = window.matchMedia(DRAWER_BREAKPOINT_MQ);

  // 跨越断点（窗口缩放 / 平板旋转）时复位抽屉状态，避免遮罩与侧栏残留
  const normalizeDrawerState = () => {
    window.closeAnySidebarDrawer();
    if (!isEffectivePortraitDrawerMode()) {
      document.body.classList.add("desktop-sidebar-collapsed");
    }
    syncDrawerToggleButtonUI();
  };

  const onPhoneChange = () => {
    // 自动模式下跟随设备宽度切换横 / 竖屏界面
    if (getGuiOrientationPref() === "auto") window.setGuiOrientation("auto", true);
    normalizeDrawerState();
  };
  const addMqListener = (mq, fn) => {
    if (typeof mq.addEventListener === "function") mq.addEventListener("change", fn);
    else if (typeof mq.addListener === "function") mq.addListener(fn);
  };
  addMqListener(mqPhone, onPhoneChange);
  addMqListener(mqDrawer, normalizeDrawerState);
  window.addEventListener("orientationchange", () => setTimeout(onPhoneChange, 180));

  // 软键盘弹出时以可视视口高度为准，防止底部输入框被键盘遮挡
  const vv = window.visualViewport;
  const isTouch = window.matchMedia("(pointer: coarse)").matches;
  if (vv && isTouch) {
    let rafId = 0;
    const applyAppHeight = () => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        document.documentElement.style.setProperty("--app-height", `${Math.round(vv.height)}px`);
        // iOS 键盘弹起时会平移整个页面，将其复位使顶栏与输入框同时可见
        if (vv.offsetTop > 0 && document.activeElement && /^(TEXTAREA|INPUT)$/.test(document.activeElement.tagName)) {
          window.scrollTo(0, 0);
        }
      });
    };
    vv.addEventListener("resize", applyAppHeight);
    vv.addEventListener("scroll", applyAppHeight);
    applyAppHeight();
    document.body.classList.add("has-visual-viewport");
  }
}

// ================= 事件统一安全绑定 =================
function setupEventListeners() {
  // 纯净版无需绑定账号登录与密码修改弹窗
  btnCloseUserModal?.addEventListener("click", () => {
    if (userModal) userModal.style.display = "none";
  });
  btnCloseUserModalBtn?.addEventListener("click", () => {
    if (userModal) userModal.style.display = "none";
  });

  // 移动端抽屉与右上角菜单（[面板] 已在 index.html 内联 onclick 绑定，这里不再重复绑定，避免一次点击触发两次）
  btnCloseMobileSidebar?.addEventListener("click", () => window.closeAnySidebarDrawer());
  sidebarBackdrop?.addEventListener("click", () => window.closeAnySidebarDrawer());

  if (btnMobileMoreActions && mobileMoreMenu) {
    btnMobileMoreActions.addEventListener("click", (e) => {
      e.stopPropagation();
      const isVis = mobileMoreMenu.style.display === "flex";
      mobileMoreMenu.style.display = isVis ? "none" : "flex";
    });
    document.addEventListener("click", (e) => {
      if (!mobileMoreMenu.contains(e.target) && e.target !== btnMobileMoreActions) {
        mobileMoreMenu.style.display = "none";
      } else if (mobileMoreMenu.contains(e.target) && e.target.closest(".mobile-menu-item")) {
        // 点选菜单项后自动收起菜单，避免菜单残留在新打开的面板上方
        setTimeout(() => { mobileMoreMenu.style.display = "none"; }, 0);
      }
    });
  }

  btnMobileEditProject?.addEventListener("click", () => {
    if (mobileMoreMenu) mobileMoreMenu.style.display = "none";
    if (typeof window.toggleStudioWorkbench === "function") {
      window.toggleStudioWorkbench(true);
    } else {
      openProjectModal();
    }
  });
  btnMobileTriggerSummary?.addEventListener("click", () => {
    if (mobileMoreMenu) mobileMoreMenu.style.display = "none";
    handleManualSummarize();
  });
  btnMobileOpenSettings?.addEventListener("click", () => {
    if (mobileMoreMenu) mobileMoreMenu.style.display = "none";
    openSettingsModal();
  });
  btnMobileOpenRemote?.addEventListener("click", () => {
    if (mobileMoreMenu) mobileMoreMenu.style.display = "none";
    openRemoteModal();
  });
  btnMobileOpenUser?.addEventListener("click", () => {
    if (mobileMoreMenu) mobileMoreMenu.style.display = "none";
    openUserModal();
  });
  btnMobileClearHistory?.addEventListener("click", () => {
    if (mobileMoreMenu) mobileMoreMenu.style.display = "none";
    handleClearHistory();
  });
  btnMobileLogout?.addEventListener("click", () => {
    if (mobileMoreMenu) mobileMoreMenu.style.display = "none";
    handleLogout();
  });
  document.getElementById("btnMobileOpenPricing")?.addEventListener("click", () => {
    if (mobileMoreMenu) mobileMoreMenu.style.display = "none";
    openPricingModal();
  });

  // 全模型价格总览弹窗
  document.getElementById("btnOpenPricingModal")?.addEventListener("click", openPricingModal);
  document.getElementById("btnSidebarPricing")?.addEventListener("click", () => {
    closeMobileSidebar();
    openPricingModal();
  });
  document.getElementById("btnSettingsOpenPricing")?.addEventListener("click", openPricingModal);
  document.getElementById("btnClosePricingModal")?.addEventListener("click", () => {
    const pm = document.getElementById("pricingModal");
    if (pm) pm.style.display = "none";
  });
  document.getElementById("btnClosePricingModalBtn")?.addEventListener("click", () => {
    const pm = document.getElementById("pricingModal");
    if (pm) pm.style.display = "none";
  });
  document.getElementById("pricingSearchInput")?.addEventListener("input", () => {
    renderPricingTable();
  });
  document.querySelectorAll(".pricing-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".pricing-tab-btn").forEach((b) => {
        b.classList.remove("btn-primary");
        b.classList.add("btn-secondary");
      });
      btn.classList.remove("btn-secondary");
      btn.classList.add("btn-primary");
      currentPricingFilter = btn.dataset.filter || "all";
      renderPricingTable();
    });
  });

  // 远程访问弹窗
  btnSidebarRemote?.addEventListener("click", () => {
    closeMobileSidebar();
    openRemoteModal();
  });
  btnOpenRemoteModal?.addEventListener("click", openRemoteModal);
  btnCloseRemoteModal?.addEventListener("click", () => (remoteModal.style.display = "none"));
  btnCloseRemoteModalBtn?.addEventListener("click", () => (remoteModal.style.display = "none"));
  btnCopyPublicUrl?.addEventListener("click", () => copyText(remotePublicUrl?.value, "已复制"));
  btnCopyLanUrl?.addEventListener("click", () => copyText(remoteLanUrl?.value, "已复制"));
  btnCopyLocalUrl?.addEventListener("click", () => copyText(remoteLocalUrl?.value, "已复制"));

  // 素材图库弹窗与文件上传
  // btnOpenGalleryModal 已在 index.html 中通过内联 onclick 绑定 openGalleryModal，此处不再重复绑定以免双重打开
  btnCloseGalleryModal?.addEventListener("click", () => (galleryModal.style.display = "none"));
  btnSelectAllGallery?.addEventListener("click", selectAllGalleryImages);
  btnClearSelectionGallery?.addEventListener("click", clearSelectionGalleryImages);
  btnInsertSelectedImages?.addEventListener("click", insertSelectedGalleryImages);
  galleryFileInput?.addEventListener("change", handleGalleryFileUpload);

  // 聊天图片选择、粘贴与预览
  fileInput?.addEventListener("change", handleFileSelectMultiple);
  btnClearAllImages?.addEventListener("click", clearAllSelectedImages);
  document.addEventListener("paste", handlePasteMultiple);
  imageLightbox?.addEventListener("click", () => (imageLightbox.style.display = "none"));

  // 发送、中断、重新生成与输入框自适应
  btnSend?.addEventListener("click", handleSendMessage);
  btnStop?.addEventListener("click", handleStopCurrentGeneration);
  btnRegenerateLatest?.addEventListener("click", handleRegenerateLatest);

  userInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      // 中文 / 日文输入法选词期间的回车不发送
      if (e.isComposing || e.keyCode === 229) return;
      // 触屏设备（手机 / 平板软键盘）回车换行，通过 [发送] 按钮发送
      if (window.matchMedia && window.matchMedia("(pointer: coarse)").matches && !window.matchMedia("(pointer: fine)").matches) return;
      e.preventDefault();
      handleSendMessage();
    }
  });
  userInput?.addEventListener("focus", () => {
    // 手机端聚焦输入框时，等待软键盘弹出后确保输入框在可视区域内
    if (window.matchMedia && window.matchMedia("(pointer: coarse)").matches) {
      setTimeout(() => userInput.scrollIntoView({ block: "nearest" }), 320);
    }
  });
  userInput?.addEventListener("input", autoResizeTextarea);

  // 消息流滚动监听（向上翻阅时浮现“回到最新剧情”按钮，当弹出层/备忘抽屉/移动端工作台展开时自动隐藏）
  window.updateScrollBottomBtnVisibility = function () {
    if (!messageContainer || !btnScrollBottom) return;
    const pop = document.getElementById("minimalistPlusPopover");
    const popOpen = Boolean(pop && pop.style.display !== "none" && pop.style.display !== "");
    const sumOpen = Boolean(summaryCard && summaryCard.style.display !== "none" && summaryCard.style.display !== "");
    const studioPane = document.getElementById("studioWorkbenchPane");
    const studioCoversMobile = Boolean(
      studioPane &&
      studioPane.style.display !== "none" &&
      studioPane.style.display !== "" &&
      (window.innerWidth <= 900 || document.body.classList.contains("gui-portrait-mode"))
    );
    const welcomeVis = Boolean(welcomeBox && welcomeBox.style.display !== "none" && welcomeBox.offsetParent !== null);
    if (popOpen || sumOpen || studioCoversMobile || welcomeVis) {
      btnScrollBottom.style.display = "none";
      return;
    }
    const distFromBottom = messageContainer.scrollHeight - messageContainer.scrollTop - messageContainer.clientHeight;
    btnScrollBottom.style.display = distFromBottom > 180 ? "inline-flex" : "none";
  };

  messageContainer?.addEventListener("scroll", () => {
    window.updateScrollBottomBtnVisibility();
  });
  messageContainer?.addEventListener("click", (e) => {
    const choiceEl = e.target?.closest?.(".trpg-action-choice-item");
    if (choiceEl && typeof window.handleChoiceItemClick === "function") {
      window.handleChoiceItemClick(choiceEl, e);
    }
  });
  btnScrollBottom?.addEventListener("click", scrollToBottom);

  // 游戏管理与设置
  btnNewProject?.addEventListener("click", handleNewProject);
  btnEditProject?.addEventListener("click", () => {
    closeMobileSidebar();
    if (typeof window.toggleStudioWorkbench === "function") {
      window.toggleStudioWorkbench();
    } else {
      openProjectModal();
    }
  });
  activeProjectBadge?.addEventListener("click", () => {
    if (typeof window.toggleStudioWorkbench === "function") {
      window.toggleStudioWorkbench();
    } else {
      openProjectModal();
    }
  });
  btnCloseProjectModal?.addEventListener("click", () => (projectModal.style.display = "none"));
  btnSaveProject?.addEventListener("click", handleSaveProject);
  btnDeleteCurrentProject?.addEventListener("click", handleDeleteProject);
  projContextTurnsInput?.addEventListener("input", () => {
    const turns = parseInt(projContextTurnsInput.value) || 12;
    if (turnsCalcHint) turnsCalcHint.textContent = turns * 2;
  });

  // 对话新建（一键直建）、重命名、清空與独立模型切换
  btnNewChat?.addEventListener("click", () => createNewChat());
  titleClickArea?.addEventListener("click", handleRenameCurrentChat);
  btnClearHistory?.addEventListener("click", handleClearHistory);
  headerModelSelect?.addEventListener("change", handleHeaderModelChange);

  // 前情提要备忘卡片
  btnToggleSummary?.addEventListener("click", () => {
    if (!summaryCard) return;
    summaryCard.style.display = summaryCard.style.display === "none" ? "flex" : "none";
    window.updateScrollBottomBtnVisibility();
  });
  btnCloseSummaryCard?.addEventListener("click", () => {
    if (summaryCard) summaryCard.style.display = "none";
    window.updateScrollBottomBtnVisibility();
  });
  btnTriggerSummary?.addEventListener("click", handleManualSummarize);
  btnEditSummary?.addEventListener("click", openSummaryEditor);
  btnCancelSummaryEdit?.addEventListener("click", closeSummaryEditor);
  btnSaveSummaryEdit?.addEventListener("click", handleSaveSummaryEdit);

  // 快捷掷骰（填入输入框，再按一次重新掷骰）
  btnRollD100?.addEventListener("click", () => rollDice(1, 100, false));

  // API 与模型设置弹窗
  btnOpenSettings?.addEventListener("click", () => {
    if (typeof window.closeAnySidebarDrawer === "function") {
      window.closeAnySidebarDrawer();
    } else {
      closeMobileSidebar();
    }
    openSettingsModal();
  });
  btnCloseSettingsModal?.addEventListener("click", () => (settingsModal.style.display = "none"));
  btnSaveSettings?.addEventListener("click", handleSaveSettings);
  btnRefreshModels?.addEventListener("click", async () => {
    try {
      const payload = collectSettingsPayload();
      if (!window.globalUserSettings) window.globalUserSettings = {};
      Object.assign(window.globalUserSettings, payload);
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
    } catch (e) {}
    await loadModels(true, {
      autoFromApiInput: Boolean(settingBaseUrl?.value?.trim() || settingApiKey?.value?.trim()),
      triggerSource: "refresh_btn"
    });
  });

  // 填完 API 地址 / API 密钥 / 本地接口地址 移开焦点或按回车时，自动拉取模型列表
  let _lastAutoFetchSig = "";
  const triggerAutoFetchApiModels = async (source) => {
    const bUrl = (settingBaseUrl?.value || "").trim();
    const aKey = (settingApiKey?.value || "").trim();
    const lMode = document.getElementById("settingLocalMode")?.value || "manual";
    const lUrl = (document.getElementById("settingLocalBaseUrl")?.value || "").trim();
    const aProto = window.globalUserSettings?.api_protocol || "auto";
    const canAutoByProtoOrKey =
      aKey.startsWith("AIza") ||
      aKey.startsWith("sk-ant-") ||
      ["gemini", "claude", "ollama"].includes(aProto);
    if (!bUrl && !canAutoByProtoOrKey && !(lMode === "manual" && lUrl)) return;

    const sig = `${aProto}||${bUrl}||${aKey}||${lMode}||${lUrl}`;
    if (sig === _lastAutoFetchSig) return;
    _lastAutoFetchSig = sig;

    try {
      const payload = collectSettingsPayload();
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
    } catch (e) {}

    await loadModels(false, {
      autoFromApiInput: Boolean(bUrl || canAutoByProtoOrKey),
      triggerSource: source
    });
  };

  [
    [settingBaseUrl, "base_url"],
    [settingApiKey, "api_key"],
    [document.getElementById("settingLocalBaseUrl"), "local_url"]
  ].forEach(([inpEl, srcName]) => {
    if (!inpEl) return;
    inpEl.addEventListener("blur", () => triggerAutoFetchApiModels(srcName));
    inpEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        triggerAutoFetchApiModels(srcName);
      }
    });
  });

  settingModelSelect?.addEventListener("change", () => {
    if (settingModel) settingModel.value = settingModelSelect.value;
    updateSelectedModelPriceHint(settingModelSelect.value);
  });
  chkCustomModel?.addEventListener("change", () => {
    if (!settingModel || !settingModelSelect) return;
    if (chkCustomModel.checked) {
      settingModel.style.display = "block";
      settingModelSelect.style.display = "none";
      settingModel.focus();
    } else {
      settingModel.style.display = "none";
      settingModelSelect.style.display = "block";
      settingModel.value = settingModelSelect.value;
      updateSelectedModelPriceHint(settingModelSelect.value);
    }
  });
}

// ================= 游戏管理（单击胶囊直接切换） =================
async function loadProjects() {
  try {
    const res = await fetch("/api/projects");
    if (!res.ok) return;
    const rawProjects = await res.json();
    const projects = (rawProjects || []).filter((p) => p && p.id);

    projectsMap = {};
    projects.forEach((p) => (projectsMap[p.id] = p));

    if (!projectsMap[currentProjectId]) {
      currentProjectId = projectsMap["proj_default"]
        ? "proj_default"
        : projects.length > 0
        ? projects[0].id
        : "proj_default";
    }
    renderProjectPills(projects);
    updateProjectHeaderBadge();
    if (welcomeBox && welcomeBox.style.display !== "none" && typeof renderWelcomeBox === "function") {
      renderWelcomeBox();
    }
  } catch (err) {
    console.error("加载游戏列表失败:", err);
  }
}

// 通用就地重命名组件：回车或失焦自动保存，Esc 取消，无需弹窗与保存按钮
function startInlineRename(targetEl, currentText, onCommit, extraClass = "") {
  if (!targetEl || targetEl.dataset.inlineEditing === "1") return;
  targetEl.dataset.inlineEditing = "1";

  const rawInitial = (currentText || "").trim();
  const displayInitial =
    window.currentAppLang === "en" && typeof window.tStr === "function"
      ? window.tStr(rawInitial)
      : rawInitial;
  const input = document.createElement("input");
  input.type = "text";
  input.className = `inline-rename-input ${extraClass}`.trim();
  input.value = displayInitial;

  const prevDisplay = targetEl.style.display;
  targetEl.style.display = "none";
  targetEl.parentNode.insertBefore(input, targetEl.nextSibling);

  ["click", "dblclick", "mousedown", "mouseup"].forEach((evtName) => {
    input.addEventListener(evtName, (e) => e.stopPropagation());
  });

  let finished = false;
  const finish = (shouldSave) => {
    if (finished) return;
    finished = true;
    const nextVal = input.value.trim();
    if (input.parentNode) input.parentNode.removeChild(input);
    targetEl.style.display = prevDisplay;
    delete targetEl.dataset.inlineEditing;
    if (shouldSave && nextVal && nextVal !== displayInitial && nextVal !== rawInitial) {
      onCommit(nextVal);
    }
  };

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      e.stopPropagation();
      input.blur();
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      finish(false);
    }
  });

  input.addEventListener("blur", () => {
    finish(true);
  });

  setTimeout(() => {
    input.focus();
    input.select();
  }, 10);
}
window.startInlineRename = startInlineRename;

async function saveProjectNameInline(projId, newName) {
  const proj = projectsMap[projId];
  if (!proj || !newName) return;
  proj.name = newName;
  renderProjectPills();
  updateProjectHeaderBadge();
  const stNameInp = document.getElementById("stProjName");
  if (stNameInp && currentProjectId === projId) stNameInp.value = newName;
  const stBadgeTitle = document.getElementById("studioAppBadgeTitle");
  if (stBadgeTitle && currentProjectId === projId) stBadgeTitle.textContent = newName;

  try {
    await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...proj, id: projId, name: newName })
    });
  } catch (err) {
    showToast("重命名失败: " + err);
  }
}
window.saveProjectNameInline = saveProjectNameInline;

function isImageIconUrl(val) {
  if (!val || typeof val !== "string") return false;
  const s = val.trim();
  return s.startsWith("/") || s.startsWith("http://") || s.startsWith("https://") || s.startsWith("data:image/");
}
window.isImageIconUrl = isImageIconUrl;

function renderProjectIconHtml(iconVal, sizePx = 20, extraStyle = "") {
  const raw = String(iconVal || "").trim();
  if (isImageIconUrl(raw)) {
    return `<img src="${escapeHtml(raw)}" alt="图标" style="width:${sizePx}px;height:${sizePx}px;border-radius:6px;object-fit:cover;vertical-align:middle;flex-shrink:0;display:inline-block;${extraStyle}" />`;
  }
  return "";
}
window.renderProjectIconHtml = renderProjectIconHtml;

function startInlineProjectRename(projId, targetEl, oldName, prefixText = "") {
  startInlineRename(targetEl, oldName, (newName) => {
    targetEl.textContent = `${prefixText}${newName}`;
    saveProjectNameInline(projId, newName);
  });
}
window.startInlineProjectRename = startInlineProjectRename;

function renderProjectPills(projects = Object.values(projectsMap)) {
  if (!projectPillsList) return;
  projectPillsList.innerHTML = "";
  projects.forEach((proj) => {
    const pill = document.createElement("div");
    const isActive = proj.id === currentProjectId;
    pill.className = `project-pill ${isActive ? "active" : ""}`;
    pill.dataset.projId = proj.id;
    pill.title = proj.name || "";
    pill.onclick = () => switchProject(proj.id);

    const leftWrap = document.createElement("div");
    leftWrap.style.cssText = "display:flex;align-items:center;gap:6px;min-width:0;flex:1;overflow:hidden;";

    const iconHtml = renderProjectIconHtml(proj.icon || proj.avatar || "", 20);
    if (iconHtml) {
      const iconWrap = document.createElement("span");
      iconWrap.style.cssText = "display:inline-flex;align-items:center;flex-shrink:0;";
      iconWrap.innerHTML = iconHtml;
      leftWrap.appendChild(iconWrap);
    }

    const titleSpan = document.createElement("span");
    titleSpan.className = "project-pill-title";
    titleSpan.textContent = proj.name;
    titleSpan.ondblclick = (e) => {
      e.stopPropagation();
      startInlineProjectRename(proj.id, titleSpan, proj.name, "");
    };
    leftWrap.appendChild(titleSpan);
    pill.appendChild(leftWrap);

    const rightBox = document.createElement("div");
    rightBox.style.cssText = "display:flex;align-items:center;gap:4px;flex-shrink:0;";

    const renameBtn = document.createElement("button");
    renameBtn.type = "button";
    renameBtn.className = "chat-item-btn";
    renameBtn.innerHTML = "改名";
    renameBtn.title = "重命名";
    renameBtn.onclick = (e) => {
      e.stopPropagation();
      startInlineProjectRename(proj.id, titleSpan, proj.name, "");
    };
    rightBox.appendChild(renameBtn);

    const settingsBtn = document.createElement("button");
    settingsBtn.type = "button";
    settingsBtn.className = "icon-tool-btn project-pill-settings-btn";
    settingsBtn.innerHTML = "设定";
    settingsBtn.title = "剧本设定";
    settingsBtn.onclick = async (e) => {
      e.stopPropagation();
      if (currentProjectId !== proj.id) {
        await switchProject(proj.id);
      }
      if (typeof window.closeAnySidebarDrawer === "function") {
        window.closeAnySidebarDrawer();
      }
      if (typeof window.toggleStudioWorkbench === "function") {
        window.toggleStudioWorkbench(true);
      }
    };
    rightBox.appendChild(settingsBtn);

    pill.appendChild(rightBox);
    projectPillsList.appendChild(pill);
  });
}

async function switchProject(projId) {
  window._welcomeModeStepSelected = true;
  if (currentProjectId === projId) {
    if (welcomeBox && welcomeBox.style.display !== "none" && typeof renderWelcomeBox === "function") {
      renderWelcomeBox();
    }
    return true;
  }
  const prevProjectId = currentProjectId;
  currentProjectId = projId;
  renderProjectPills();
  updateProjectHeaderBadge();

  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active_project_id: currentProjectId })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
  } catch (err) {
    // 保存失败：回滚到之前的游戏，避免前端状态与服务端不一致（半切换）
    if (currentProjectId === projId) {
      currentProjectId = prevProjectId;
      renderProjectPills();
      updateProjectHeaderBadge();
    }
    showToast("切换失败: " + (err?.message || err));
    return false;
  }
  // 等待期间用户又切换了其他游戏：放弃本次后续处理
  if (currentProjectId !== projId) return false;

  currentChatId = null;
  await loadChats();
  if (typeof window.applyProjectAppearance === "function") {
    window.applyProjectAppearance(projectsMap[currentProjectId]);
  }
  const pane = document.getElementById("studioWorkbenchPane");
  if (pane && pane.style.display !== "none" && typeof window.renderStudioWorkbench === "function") {
    window.renderStudioWorkbench();
  }
  if (welcomeBox && welcomeBox.style.display !== "none" && typeof renderWelcomeBox === "function") {
    renderWelcomeBox();
  }
  showToast(`已切换：${projectsMap[currentProjectId]?.name || ""}`);
  return true;
}
window.switchProject = switchProject;

function updateProjectHeaderBadge() {
  const proj = projectsMap[currentProjectId];
  if (proj) {
    if (activeProjectNameEl) {
      activeProjectNameEl.textContent = proj.name;
    }
    const badgeIconEl = activeProjectBadge?.querySelector(".badge-icon");
    if (badgeIconEl) {
      badgeIconEl.innerHTML = renderProjectIconHtml(proj.icon || proj.avatar || "", 18);
    }
  }
}

async function handleNewProject() {
  const nextIdx = Object.keys(projectsMap || {}).length + 1;
  const defaultName = `新剧本 #${nextIdx}`;
  const defaultMods = Array.isArray(window.DEFAULT_UNIVERSAL_UI_MODULES)
    ? window.DEFAULT_UNIVERSAL_UI_MODULES.map((m) => ({ ...m }))
    : [];
  const defaultProto = typeof window.DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT === "string"
    ? window.DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT
    : "";

  try {
    const res = await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: defaultName,
        icon: "",
        description: "",
        tags: [],
        opening_greetings: [],
        opening_statement: "",
        system_prompt: "",
        prefix: "",
        suffix: "",
        system_protocol_prompt: defaultProto,
        ui_modules: defaultMods,
        status_panel_enabled: true,
        appearance: { bg_image: "" }
      })
    });
    const data = await res.json();
    if (!res.ok || !data?.project?.id) throw new Error(data?.detail || `HTTP ${res.status}`);
    currentProjectId = data.project.id;
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active_project_id: currentProjectId })
    });
    await loadProjects();
    currentChatId = null;
    await loadChats();
    if (typeof window.renderStudioWorkbench === "function") {
      const pane = document.getElementById("studioWorkbenchPane");
      if (pane && pane.style.display !== "none") {
        window.renderStudioWorkbench();
      }
    }
    showToast(`已新建：${defaultName}`);
  } catch (err) {
    showToast("新建失败: " + err);
  }
}

function openProjectModal() {
  if (typeof window.toggleStudioWorkbench === "function") {
    window.toggleStudioWorkbench(true);
  }
}

async function handleSaveProject() {
  if (typeof window.saveStudioProjectConfig === "function") {
    await window.saveStudioProjectConfig(true);
  }
}

async function handleDeleteProject() {
  if (currentProjectId === "proj_default") {
    showToast("默认剧本不可删除");
    return;
  }
  const confirmed = await showCustomDialog({
    title: "删除剧本",
    message: "删除当前剧本？对话将移入默认剧本"
  });
  if (!confirmed) return;

  try {
    const delRes = await fetch(`/api/projects/${currentProjectId}`, { method: "DELETE" });
    if (!delRes.ok) {
      const errData = await delRes.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP ${delRes.status}`);
    }
    currentProjectId = "proj_default";
    if (projectModal) projectModal.style.display = "none";
    await loadProjects();
    currentChatId = null;
    await loadChats();
    if (typeof window.renderStudioWorkbench === "function") {
      const pane = document.getElementById("studioWorkbenchPane");
      if (pane && pane.style.display !== "none") {
        window.renderStudioWorkbench();
      }
    }
    showToast("已删除");
  } catch (err) {
    showToast("删除失败: " + err);
  }
}
window.handleDeleteProject = handleDeleteProject;

// ================= 对话列表与独立模型绑定 =================
async function loadChats() {
  try {
    if (!currentProjectId) {
      currentProjectId = "proj_default";
    }
    const res = await fetch(`/api/chats?project_id=${encodeURIComponent(currentProjectId)}`);
    if (!res.ok) return;
    const rawChats = await res.json();
    const cleanedChats = [];
    for (const c of rawChats || []) {
      if (!c || !c.id) continue;
      cleanedChats.push(c);
    }
    cachedChatList = cleanedChats;
    if (chatCountBadge) chatCountBadge.textContent = cachedChatList.length;
    renderChatList(cachedChatList);

    if (cachedChatList.length > 0) {
      if (!currentChatId || !cachedChatList.find((c) => c.id === currentChatId)) {
        await switchChat(cachedChatList[0].id);
      }
    } else {
      await createNewChat();
    }
  } catch (err) {
    console.error("加载对话列表失败:", err);
  }
}

function renderChatList(chats = cachedChatList) {
  if (!chatListEl) return;
  chatListEl.innerHTML = "";
  chats.forEach((chat) => {
    const item = document.createElement("div");
    item.className = `chat-item ${chat.id === currentChatId ? "active" : ""}`;
    item.dataset.id = chat.id;

    const titleWrap = document.createElement("div");
    titleWrap.className = "chat-item-meta";

    const titleSpan = document.createElement("span");
    titleSpan.className = "chat-item-title";
    titleSpan.textContent = chat.title || "未命名对话";
    titleSpan.title = "双击重命名";
    titleSpan.ondblclick = (e) => {
      e.stopPropagation();
      startInlineChatRename(chat.id, titleSpan, chat.title || "未命名对话");
    };

    const modelTag = document.createElement("span");
    modelTag.className = "chat-model-tag";
    modelTag.textContent = getShortModelName(chat.model);
    modelTag.title = `当前对话模型: ${chat.model || "默认"}`;

    titleWrap.appendChild(titleSpan);
    titleWrap.appendChild(modelTag);

    // 后台流式生成状态灯（绿点脉冲）与未读新回复提醒（红点）
    if (activeStreams[chat.id]) {
      const genDot = document.createElement("span");
      genDot.className = "generating-badge";
      genDot.title = "生成中";
      titleWrap.appendChild(genDot);
    } else if (unreadChats.has(chat.id)) {
      const unreadDot = document.createElement("span");
      unreadDot.className = "unread-badge";
      unreadDot.title = "新回复";
      titleWrap.appendChild(unreadDot);
    }

    const actions = document.createElement("div");
    actions.className = "chat-item-actions";

    const btnRename = document.createElement("button");
    btnRename.type = "button";
    btnRename.className = "chat-item-btn";
    btnRename.innerHTML = "改名";
    btnRename.title = "重命名";
    btnRename.onclick = (e) => {
      e.stopPropagation();
      startInlineChatRename(chat.id, titleSpan, chat.title || "未命名对话");
    };

    const btnDel = document.createElement("button");
    btnDel.type = "button";
    btnDel.className = "chat-item-btn btn-del";
    btnDel.innerHTML = "删除";
    btnDel.title = "删除对话";
    btnDel.onclick = (e) => {
      e.stopPropagation();
      deleteChat(chat.id);
    };

    actions.appendChild(btnRename);
    actions.appendChild(btnDel);

    item.appendChild(titleWrap);
    item.appendChild(actions);

    item.onclick = () => {
      switchChat(chat.id);
      closeMobileSidebar();
    };
    chatListEl.appendChild(item);
  });
}

// 一键秒建新对话（无任何弹窗打断）
async function createNewChat() {
  closeMobileSidebar();
  const nextNum = (cachedChatList ? cachedChatList.length : 0) + 1;
  const now = new Date();
  const timeStr = `${(now.getMonth() + 1).toString().padStart(2, "0")}-${now.getDate().toString().padStart(2, "0")} ${now.getHours().toString().padStart(2, "0")}:${now.getMinutes().toString().padStart(2, "0")}`;
  const autoTitle = `对话 #${nextNum} (${timeStr})`;
  const activeModel = headerModelSelect?.value || settingModel?.value || "";

  try {
    const res = await fetch("/api/chats", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: autoTitle,
        project_id: currentProjectId || "proj_default",
        model: activeModel
      })
    });
    const newChat = await res.json();
    if (!res.ok || !newChat || !newChat.id) throw new Error(newChat?.detail || `HTTP ${res.status}`);
    await loadChats();
    await switchChat(newChat.id);
    showToast("已新建对话");
  } catch (err) {
    showToast("新建对话失败: " + err);
  }
}

// 自由切换对话（后台生成中的对话绝不中断，且支持页面刷新后自动衔接服务端后台生成）
let bgPollTimer = null;
let _switchChatSeq = 0;
async function switchChat(chatId) {
  closeMobileSidebar();
  const mySwitchSeq = ++_switchChatSeq;
  currentChatId = chatId;
  unreadChats.delete(chatId);
  if (bgPollTimer) {
    clearInterval(bgPollTimer);
    bgPollTimer = null;
  }
  renderChatList();

  try {
    const res = await fetch(`/api/chats/${encodeURIComponent(chatId)}`);
    if (mySwitchSeq !== _switchChatSeq || currentChatId !== chatId) return;
    if (!res.ok) return;
    const fetchedChatData = await res.json();
    // 用户在等待期间已切换到其他对话或触发了更新的切换请求：丢弃本次结果，避免覆盖新对话的数据与界面
    if (mySwitchSeq !== _switchChatSeq || currentChatId !== chatId) return;
    currentChatData = fetchedChatData;

    if (currentChatData.project_id) {
      currentProjectId = currentChatData.project_id;
      updateProjectHeaderBadge();
    }

    // 同步当前会话的提示词变量取值，清空上一会话遗留键值并刷新变量条
    if (typeof window.sessionVariableValues === "object" && window.sessionVariableValues) {
      Object.keys(window.sessionVariableValues).forEach((k) => {
        delete window.sessionVariableValues[k];
      });
      if (currentChatData.variables && typeof currentChatData.variables === "object") {
        Object.assign(window.sessionVariableValues, currentChatData.variables);
      }
    }
    if (typeof window.renderChatVariablesBar === "function") {
      window.renderChatVariablesBar();
    }

    if (currentChatTitleEl) {
      currentChatTitleEl.textContent = currentChatData.title || "未命名对话";
    }

    if (currentChatData.model) {
      syncHeaderModelSelect(currentChatData.model);
    }

    updateSummaryUI(currentChatData.summary || "");
    renderMessages(currentChatData.messages || []);

    // 若该对话正在前端或服务端后台流式生成中，无缝挂载实时气泡
    if (activeStreams[chatId]) {
      if (btnSend) btnSend.style.display = "none";
      if (btnStop) btnStop.style.display = "inline-flex";
      const streamInfo = activeStreams[chatId];
      streamInfo.bubbleEl = appendMessageElement({
        id: streamInfo.msgId,
        role: "assistant",
        content: streamInfo.text || "生成中…"
      });
      streamInfo.itemEl = streamInfo.bubbleEl.closest(".message-item");
    } else if (currentChatData.is_generating) {
      if (btnSend) btnSend.style.display = "none";
      if (btnStop) btnStop.style.display = "inline-flex";
      const tempBubble = appendMessageElement({
        id: "msg_bg_polling",
        role: "assistant",
        content: currentChatData.partial_reply || "后台生成中…"
      });
      let elapsedPoll = 0;
      const BG_POLL_MAX_SECONDS = 600; // 最长轮询 10 分钟，防止服务端未清除 is_generating 时无限轮询
      let thisPollTimer = null;
      const stopThisPoll = () => {
        clearInterval(thisPollTimer);
        if (bgPollTimer === thisPollTimer) bgPollTimer = null;
      };
      thisPollTimer = bgPollTimer = setInterval(async () => {
        if (currentChatId !== chatId || bgPollTimer !== thisPollTimer) {
          stopThisPoll();
          return;
        }
        elapsedPoll += 2;
        if (elapsedPoll > BG_POLL_MAX_SECONDS) {
          stopThisPoll();
          if (btnSend) btnSend.style.display = "inline-flex";
          if (btnStop) btnStop.style.display = "none";
          showToast("等待超时，请刷新或重新生成");
          return;
        }
        try {
          const pollRes = await fetch(`/api/chats/${chatId}`);
          if (!pollRes.ok) return;
          const pollData = await pollRes.json();
          // 等待期间已切换对话或轮询已被停止：丢弃结果
          if (currentChatId !== chatId || bgPollTimer !== thisPollTimer) return;
          if (pollData.is_generating) {
            const prevSt = messageContainer ? messageContainer.scrollTop : 0;
            if (pollData.partial_reply) {
              tempBubble.innerHTML = renderRichContent(pollData.partial_reply);
            } else {
              tempBubble.innerHTML = `<span style="color:#fbbf24;">生成中… ${elapsedPoll}s</span>`;
            }
            if (messageContainer && Math.abs(messageContainer.scrollTop - prevSt) > 1) {
              messageContainer.scrollTop = prevSt;
            }
          } else {
            stopThisPoll();
            currentChatData = pollData;
            if (btnSend) btnSend.style.display = "inline-flex";
            if (btnStop) btnStop.style.display = "none";
            renderMessages(pollData.messages || []);
            showToast("已生成");
          }
        } catch (e) {}
      }, 2000);
    } else {
      if (btnSend) btnSend.style.display = "inline-flex";
      if (btnStop) btnStop.style.display = "none";
    }
  } catch (err) {
    console.error("加载对话内容失败:", err);
  }
}

async function saveChatTitleInline(chatId, newTitle) {
  const cleanTitle = (newTitle || "").trim();
  if (!chatId || !cleanTitle) return;

  const targetChat = Array.isArray(cachedChatList) ? cachedChatList.find((c) => c.id === chatId) : null;
  if (targetChat) targetChat.title = cleanTitle;
  if (currentChatId === chatId) {
    if (currentChatData) currentChatData.title = cleanTitle;
    if (currentChatTitleEl) currentChatTitleEl.textContent = cleanTitle;
  }
  const sidebarTitleEl = chatListEl?.querySelector(`.chat-item[data-id="${chatId}"] .chat-item-title`);
  if (sidebarTitleEl) sidebarTitleEl.textContent = cleanTitle;

  try {
    await fetch(`/api/chats/${chatId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: cleanTitle })
    });
  } catch (err) {
    showToast("重命名失败: " + err);
  }
}
window.saveChatTitleInline = saveChatTitleInline;

function startInlineChatRename(chatId, targetEl, oldTitle, extraClass = "") {
  if (!chatId || !targetEl) return;
  startInlineRename(
    targetEl,
    oldTitle,
    (newTitle) => {
      targetEl.textContent = newTitle;
      saveChatTitleInline(chatId, newTitle);
    },
    extraClass
  );
}
window.startInlineChatRename = startInlineChatRename;

function handleRenameCurrentChat(e) {
  if (e) e.stopPropagation();
  if (!currentChatId || !currentChatTitleEl) return;
  startInlineChatRename(
    currentChatId,
    currentChatTitleEl,
    currentChatTitleEl.textContent || "未命名对话",
    "header-inline-rename-input"
  );
}

function renameChatPrompt(chatId, oldTitle) {
  const sidebarTitleEl = chatListEl?.querySelector(`.chat-item[data-id="${chatId}"] .chat-item-title`);
  const targetEl = sidebarTitleEl || (currentChatId === chatId ? currentChatTitleEl : null);
  if (targetEl) {
    startInlineChatRename(chatId, targetEl, oldTitle || targetEl.textContent || "未命名对话");
  }
}

async function deleteChat(chatId) {
  const confirmed = await showCustomDialog({
    title: "删除对话",
    message: "删除此对话？不可恢复"
  });
  if (!confirmed) return;

  try {
    abortCurrentChatStream(chatId, true);
    const delRes = await fetch(`/api/chats/${chatId}`, { method: "DELETE" });
    if (!delRes.ok) {
      const errData = await delRes.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP ${delRes.status}`);
    }
    if (currentChatId === chatId) {
      currentChatId = null;
    }
    await loadChats();
    showToast("已删除");
  } catch (err) {
    showToast("删除失败: " + err);
  }
}

async function handleClearHistory() {
  if (!currentChatId) return;
  const confirmed = await showCustomDialog({
    title: "清空对话",
    message: "清空全部消息与前情？"
  });
  if (!confirmed) return;

  try {
    abortCurrentChatStream(currentChatId, true, true);
    await fetch(`/api/chats/${currentChatId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: [], summary: "" })
    });
    if (currentChatData) {
      currentChatData.messages = [];
      currentChatData.summary = "";
      currentChatData.summarized_count = 0;
    }
    updateSummaryUI("");
    renderMessages([]);
    updateContextProgressUI();
    showToast("已清空");
  } catch (err) {
    showToast("清空失败: " + err);
  }
}

async function handleHeaderModelChange() {
  const selectedModel = headerModelSelect?.value;
  if (!currentChatId || !selectedModel) return;

  try {
    await fetch(`/api/chats/${currentChatId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: selectedModel })
    });
    if (currentChatData) currentChatData.model = selectedModel;
    const found = cachedChatList.find((c) => c.id === currentChatId);
    if (found) found.model = selectedModel;
    renderChatList();
    updateContextProgressUI();
    showToast(`已切换模型：${getShortModelName(selectedModel)}`);
  } catch (err) {
    showToast("切换模型失败: " + err);
  }
}

// ================= 上下文 & 最大上下文实时进度槽 =================
function formatContextTokenLen(n) {
  const val = Math.max(0, Math.round(Number(n) || 0));
  if (val < 1000) return `${val}`;
  const kVal = val / 1000;
  return kVal >= 100 || Math.abs(kVal - Math.round(kVal)) < 0.05
    ? `${Math.round(kVal)}k`
    : `${kVal.toFixed(1)}k`;
}

window.toggleHeaderContextPopover = function (event) {
  if (event) event.stopPropagation();
  const pop = document.getElementById("minimalistPlusPopover");
  if (!pop) return;
  const isOpen = pop.style.display !== "none";
  pop.style.display = isOpen ? "none" : "flex";
};

function stripThinkingForTokenEst(rawText) {
  if (!rawText) return "";
  return String(rawText)
    .replace(/<think>[\s\S]*?(?:<\/think>|$)/gi, "")
    .replace(/<thinking>[\s\S]*?(?:<\/thinking>|$)/gi, "")
    .trim();
}

function updateContextProgressUI() {
  const meterTextEl = document.getElementById("contextMeterText");
  const meterFillEl = document.getElementById("contextMeterFill");
  const meterGroupEl = document.getElementById("contextMeterGroup");
  const headerPillEl = document.getElementById("headerContextPill");
  const headerPillTextEl = document.getElementById("headerContextPillText");
  if (!meterTextEl && !headerPillTextEl) return;

  const proj = (typeof projectsMap === "object" && projectsMap && currentProjectId) ? projectsMap[currentProjectId] : null;
  const activeModel =
    headerModelSelect?.value ||
    (currentChatData && currentChatData.model) ||
    settingModel?.value ||
    window.globalUserSettings?.model ||
    "";
  const perModelParams = ((window.globalUserSettings && window.globalUserSettings.model_params) || {})[activeModel] || {};
  const globalCtxMode = window.globalUserSettings?.context_mode || proj?.completion_params?.context_mode || "tokens";
  const ctxMode = perModelParams.context_mode || globalCtxMode || "tokens";

  const globalCtx = parseInt(window.globalUserSettings?.context || window.globalUserSettings?.max_context_turns) || parseInt(proj?.completion_params?.context || proj?.max_context_turns) || 64;
  const maxTurns = parseInt(perModelParams.context) || globalCtx || 64;
  const maxMsgs = Math.max(4, maxTurns * 2);

  const globalMaxContextK = parseInt(window.globalUserSettings?.max_context_k) || parseInt(proj?.completion_params?.max_context_k) || 96;
  const maxContextK = parseInt(perModelParams.max_context_k) || globalMaxContextK || 96;
  const maxModelTokens = Math.max(2048, maxContextK * 1024);
  const maxModelTokensStr = `${maxContextK}k`;

  const msgs = Array.isArray(currentChatData?.messages) ? currentChatData.messages : [];
  const totalMsgs = msgs.length;
  const rawSummarized = parseInt(currentChatData?.summarized_count) || 0;
  const summarizedCount = Math.min(rawSummarized, Math.max(0, totalMsgs - 2));
  const unsummarizedList = msgs.slice(summarizedCount);
  const unsummarizedMsgs = unsummarizedList.length;

  const baseChars =
    (currentChatData?.summary || "").length +
    (proj?.system_prompt || "").length +
    (proj?.system_protocol_prompt || "").length;
  let activeSlice = [];
  let totalChars = baseChars;

  const keepRecent = parseInt(window.globalUserSettings?.keep_recent_messages || proj?.completion_params?.keep_recent_messages) || 6;
  const candidateList = ctxMode === "tokens" ? unsummarizedList : unsummarizedList.slice(-maxMsgs);
  for (let i = candidateList.length - 1; i >= 0; i--) {
    const m = candidateList[i];
    const cleanTxt = m?.role === "assistant" ? stripThinkingForTokenEst(m?.content || "") : String(m?.content || "");
    const mLen = cleanTxt.length;
    const nextEstTok = Math.round((totalChars + mLen) * 0.65);
    if (nextEstTok > maxModelTokens && activeSlice.length >= keepRecent) {
      break;
    }
    totalChars += mLen;
    activeSlice.unshift(m);
  }

  const activeMsgs = activeSlice.length;
  const estTokens = totalMsgs > 0 ? Math.max(0, Math.round(totalChars * 0.65)) : 0;
  const estTokensStr = formatContextTokenLen(estTokens);

  const tokenRatio = maxModelTokens > 0 ? (estTokens / maxModelTokens) : 0;
  const pct = estTokens > 0
    ? Math.min(100, Math.max(1, Math.round(tokenRatio * 100)))
    : 0;

  if (meterTextEl) {
    if (ctxMode === "tokens") {
      meterTextEl.textContent = `(${estTokensStr}/${maxModelTokensStr}) · ${activeMsgs}条`;
    } else {
      meterTextEl.textContent = `${activeMsgs} / ${maxMsgs} 条 (${estTokensStr}/${maxModelTokensStr})`;
    }
  }
  if (meterFillEl) {
    meterFillEl.style.width = `${pct}%`;
    meterFillEl.classList.remove("warn", "danger");
    if (tokenRatio >= 0.85 || pct >= 100) {
      meterFillEl.classList.add("danger");
    } else if (pct >= 75) {
      meterFillEl.classList.add("warn");
    }
  }
  if (headerPillTextEl) {
    headerPillTextEl.textContent = `${estTokensStr} / ${maxModelTokensStr}`;
  }
  if (headerPillEl) {
    headerPillEl.classList.remove("is-warn", "is-danger");
    if (tokenRatio >= 0.85) {
      headerPillEl.classList.add("is-danger");
    } else if (tokenRatio >= 0.70) {
      headerPillEl.classList.add("is-warn");
    }
    headerPillEl.title = `活跃上下文约 ${estTokens.toLocaleString()} / ${maxModelTokens.toLocaleString()} tokens（${activeMsgs} 条未压缩消息 · 点击打开上下文控制与一键压缩）`;
  }

  if (meterGroupEl) {
    meterGroupEl.title = `消息 ${activeMsgs}/${maxMsgs} · Token ${estTokensStr}/${maxModelTokensStr}`;
  }
}
window.updateContextProgressUI = updateContextProgressUI;

// ================= 前情提要备忘卡片 =================
function updateSummaryUI(summary) {
  if (!summaryTextEl) return;
  const clean = (summary || "").trim();
  if (clean) {
    const safeClean = clean.replace(/~/g, "&#126;");
    summaryTextEl.innerHTML = window.marked ? sanitizeRichHtml(marked.parse(safeClean)) : escapeHtml(clean);
    summaryTextEl.dataset.raw = clean;
    if (summaryDot) summaryDot.style.display = "inline-block";
    if (btnToggleSummary) btnToggleSummary.title = "前情";
  } else {
    summaryTextEl.textContent = "暂无前情";
    summaryTextEl.dataset.raw = "";
    if (summaryDot) summaryDot.style.display = "none";
    if (btnToggleSummary) btnToggleSummary.title = "前情";
  }
  updateContextProgressUI();
}

function openSummaryEditor() {
  if (!summaryEditTextarea || !summaryTextEl || !summaryEditBox) return;
  summaryEditTextarea.value = summaryTextEl.dataset.raw || "";
  summaryTextEl.style.display = "none";
  summaryEditBox.style.display = "flex";
  if (btnEditSummary) btnEditSummary.style.display = "none";
}

function closeSummaryEditor() {
  if (summaryEditBox) summaryEditBox.style.display = "none";
  if (summaryTextEl) summaryTextEl.style.display = "block";
  if (btnEditSummary) btnEditSummary.style.display = "inline-flex";
}

async function handleSaveSummaryEdit() {
  if (!currentChatId || !summaryEditTextarea) return;
  const newSummary = summaryEditTextarea.value.trim();
  try {
    await fetch(`/api/chats/${currentChatId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ summary: newSummary })
    });
    if (currentChatData) currentChatData.summary = newSummary;
    updateSummaryUI(newSummary);
    closeSummaryEditor();
    showToast("已保存");
  } catch (err) {
    showToast("保存备忘失败: " + err);
  }
}

async function handleManualSummarize() {
  if (!currentChatId) return;
  const targetChatId = currentChatId;
  const btnCard = document.getElementById("btnRetriggerSummaryCard");
  if (btnTriggerSummary) {
    btnTriggerSummary.innerHTML = "<span>压缩中...</span>";
    btnTriggerSummary.disabled = true;
  }
  if (btnCard) {
    btnCard.innerHTML = "总结中...";
    btnCard.disabled = true;
  }
  const summaryDedicatedSelect = document.getElementById("summaryAiModelSelect");
  const summaryModel =
    (summaryDedicatedSelect && summaryDedicatedSelect.value) ||
    headerModelSelect?.value ||
    (currentChatData && currentChatData.model) ||
    settingModel?.value ||
    window.globalUserSettings?.model ||
    "";
  showToast("压缩中…");

  try {
    const res = await fetch(`/api/chats/${encodeURIComponent(targetChatId)}/summarize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: summaryModel })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    if (data.status === "ignored") {
      showToast(data.detail || "消息太少，无需压缩");
    } else {
      if (currentChatId === targetChatId) {
        if (currentChatData) {
          currentChatData.summary = data.summary || "";
          if (typeof data.summarized_count === "number") {
            currentChatData.summarized_count = data.summarized_count;
          }
        }
        updateSummaryUI(data.summary || "");
        updateContextProgressUI();
      }
      showToast("已压缩");
    }
  } catch (err) {
    showToast("压缩失败: " + err);
  } finally {
    if (btnTriggerSummary) {
      btnTriggerSummary.innerHTML = "<span>压缩</span>";
      btnTriggerSummary.disabled = false;
    }
    if (btnCard) {
      btnCard.innerHTML = "AI 总结";
      btnCard.disabled = false;
    }
  }
}
window.handleManualSummarize = handleManualSummarize;

// ================= HTML 自动排版与富文本渲染 =================
function stripLegacyStartGameHint(text) {
  if (!text) return "";
  const cleaned = String(text)
    .replace(/\s*[（(]请根据当前剧本世界观与角色设定，直接以第二人称代入感展开第一幕沉浸式场景描写[^）)]*[）)]\s*/g, "")
    .trim();
  return cleaned || String(text).trim();
}
window.stripLegacyStartGameHint = stripLegacyStartGameHint;

function formatUserBubbleHtml(text) {
  const escaped = escapeHtml(stripLegacyStartGameHint(text || ""));
  return escaped
    .replace(/【[^】]*🎲[^】]+】/g, (m) => `<span class="dice-roll-badge">${m}</span>`)
    .replace(/\n/g, "<br>");
}

// ================= 通用 TRPG 骰子表达式解析器 (支持 1d100, 1d20, 2d6+3, 2d20kh1, 2d20kl1) =================
function evaluateDiceExpression(exprStr) {
  const raw = String(exprStr || "1d100").trim().toLowerCase();
  const m = raw.match(/^(\d*)d(\d+)(?:(kh|kl)(\d+))?([+-]\d+)?$/i);
  if (!m) {
    const val = Math.floor(Math.random() * 100) + 1;
    return { expr: "1d100", total: val, detail: `${val}` };
  }
  const count = Math.min(20, Math.max(1, parseInt(m[1] || "1", 10)));
  const sides = Math.min(1000, Math.max(2, parseInt(m[2] || "100", 10)));
  const keepMode = m[3] || "";
  const keepCount = m[4] ? Math.min(count, Math.max(1, parseInt(m[4], 10))) : count;
  const mod = m[5] ? parseInt(m[5], 10) : 0;

  const rolls = [];
  for (let i = 0; i < count; i++) {
    rolls.push(Math.floor(Math.random() * sides) + 1);
  }
  let kept = [...rolls];
  if (keepMode === "kh") {
    kept.sort((a, b) => b - a);
    kept = kept.slice(0, keepCount);
  } else if (keepMode === "kl") {
    kept.sort((a, b) => a - b);
    kept = kept.slice(0, keepCount);
  }
  const sum = kept.reduce((a, b) => a + b, 0) + mod;
  const detail = count === 1 && mod === 0 ? `${sum}` : `[${rolls.join(",")}]${mod ? (mod > 0 ? `+${mod}` : mod) : ""}=${sum}`;
  return { expr: raw, total: sum, detail };
}
window.evaluateDiceExpression = evaluateDiceExpression;

// ================= 模块五：零代码 <status> 纯文本可视化状态/装备/物品/好感解析器 =================
function parseItemWithMicroDesc(rawStr) {
  let working = String(rawStr || "").trim();
  let qty = 1;
  let hasExplicitQty = false;

  const tailQtyMatch = working.match(/^(.+?)\s*[xX×\*]\s*(\d+)$/);
  if (tailQtyMatch) {
    working = tailQtyMatch[1].trim();
    qty = parseInt(tailQtyMatch[2], 10) || 1;
    hasExplicitQty = true;
  }

  let itemName = working;
  let itemDesc = "";
  const descMatch = working.match(/^(.+?)\s*[(（]([^)）]+)[)）]\s*(?:[xX×\*]\s*(\d+))?$/);
  if (descMatch) {
    itemName = descMatch[1].trim();
    itemDesc = descMatch[2].trim();
    if (descMatch[3]) {
      qty = parseInt(descMatch[3], 10) || qty;
      hasExplicitQty = true;
    }
  } else {
    const midQtyMatch = working.match(/^(.+?)\s*[xX×\*]\s*(\d+)\s*[(（]([^)）]+)[)）]$/);
    if (midQtyMatch) {
      itemName = midQtyMatch[1].trim();
      qty = parseInt(midQtyMatch[2], 10) || 1;
      itemDesc = midQtyMatch[3].trim();
      hasExplicitQty = true;
    }
  }

  return { itemName, itemDesc, qty, hasExplicitQty };
}

function splitOutsideParens(text, sepRegex) {
  const tokens = [];
  let buf = "";
  let depth = 0;
  const s = String(text || "");
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (ch === "(" || ch === "（") {
      depth++;
      buf += ch;
    } else if (ch === ")" || ch === "）") {
      depth = Math.max(0, depth - 1);
      buf += ch;
    } else if (depth === 0 && sepRegex.test(ch)) {
      if (buf.trim()) tokens.push(buf.trim());
      buf = "";
    } else {
      buf += ch;
    }
  }
  if (buf.trim()) tokens.push(buf.trim());
  return tokens;
}

function renderNativeStatusModulesCard(statusRawText) {
  const allRawLines = String(statusRawText || "")
    .split(/\r?\n/)
    .map((l) => l.replace(/^(?:[-•>]\s*|\*\s+)/, "").replace(/\{\{([\s\S]*?)\}\}/g, "$1").trim())
    .filter((l) => !/^---+$/.test(l) && !/^<\/?status>$/i.test(l));
  const rawLines = [];
  allRawLines.forEach((l) => {
    if (!l) {
      if (rawLines.length > 0 && rawLines[rawLines.length - 1] !== "") {
        rawLines.push("");
      }
    } else {
      rawLines.push(l);
    }
  });
  while (rawLines.length > 0 && rawLines[rawLines.length - 1] === "") rawLines.pop();
  if (rawLines.length === 0) return "";

  const activeProj = (typeof projectsMap === "object" && projectsMap && currentProjectId) ? projectsMap[currentProjectId] : null;
  if (activeProj && (activeProj.id === "proj_free_chat" || activeProj.status_panel_enabled === false)) {
    return "";
  }
  const rawConfiguredMods =
    typeof window.getEffectiveUiModules === "function" && activeProj
      ? window.getEffectiveUiModules(activeProj)
      : (activeProj?.ui_modules || activeProj?.status_modules || []);
  const allConfiguredMods =
    Array.isArray(rawConfiguredMods) && rawConfiguredMods.length > 0
      ? rawConfiguredMods
      : (Array.isArray(window.DEFAULT_UNIVERSAL_UI_MODULES) ? window.DEFAULT_UNIVERSAL_UI_MODULES : []);
  const nonStatusMacroTitleRegex = /^(?:[📖🧠🎯📊📝💭⚡]\s*)?(?:剧情正文|正文|游戏正文|剧情叙事|思考推演|思考过程|思考|行动选项|可选行动|选项)(?:栏|模块)?$/i;
  const configuredMods = Array.isArray(allConfiguredMods)
    ? allConfiguredMods.filter(
        (m) =>
          m &&
          m.enabled !== false &&
          !["thinking_fold", "story_narrative", "action_choices"].includes(m.type) &&
          !["mod_think", "mod_story", "mod_choices"].includes(m.id) &&
          !nonStatusMacroTitleRegex.test(String(m.key || m.name || "").trim())
      )
    : [];

  const cleanStatusHeaderTitle = (rawStr) => {
    const cleaned = String(rawStr || "")
      .replace(/^[📊⚔️🎒💕📋🏷️🧩📖🧠🎯📝💭⚡#\d①-⑩一二三四五六七八九十\.、:：\-—\s*]+|[\*:\s：]+$/g, "")
      .trim();
    const aliasMap = {
      角色状态: "主角状态",
      个人状态: "主角状态",
      自身状态: "主角状态",
      当前状态: "主角状态",
      生命状态: "主角状态",
      主角属性: "主角状态",
      角色属性: "主角状态",
      属性栏: "主角状态",
      状态栏: "主角状态",
      状态面板: "主角状态",
      装备: "装备栏",
      身体装备: "装备栏",
      穿戴装备: "装备栏",
      当前装备: "装备栏",
      武器装备: "装备栏",
      物品: "物品栏",
      背包: "物品栏",
      背包栏: "物品栏",
      随身物品: "物品栏",
      背包物品: "物品栏",
      行囊: "物品栏",
      道具栏: "物品栏",
      人物关系: "角色关系",
      人际关系: "角色关系",
      同伴关系: "角色关系",
      好感: "角色关系",
      好感度: "角色关系",
      好感栏: "角色关系",
      关系栏: "角色关系",
      在场人物: "角色关系",
      在场NPC: "角色关系",
      周围人物: "角色关系",
      NPC关系: "角色关系",
      NPC: "角色关系",
      NPC信息: "角色关系",
      情报: "情报卡",
      情报栏: "情报卡"
    };
    return aliasMap[cleaned] || cleaned;
  };

  const isKnownTopModuleTitle = (cand, strictExact = false) => {
    const t = cleanStatusHeaderTitle(cand);
    if (!t || nonStatusMacroTitleRegex.test(t)) return false;
    if (strictExact) {
      if (/^(?:主角状态|角色状态|个人状态|自身状态|状态栏|状态面板|装备栏|物品栏|背包|角色关系|人物关系|身体栏|身体状态|情报卡|世界新闻|当前任务|任务进度|剧情进度)$/i.test(t)) {
        return true;
      }
      if (Array.isArray(configuredMods)) {
        return configuredMods.some((mod) => {
          const k = String(mod?.key || mod?.name || "").trim();
          return k && k === t;
        });
      }
      return false;
    }
    if (/^(?:主角状态|角色状态|个人状态|自身状态|状态栏|状态面板|属性栏|装备栏|装备|物品栏|物品|背包|角色关系|好感|人物关系|身体栏|身体状态|情报卡|世界新闻|当前任务|任务进度|剧情进度)$/i.test(t)) {
      return true;
    }
    if (Array.isArray(configuredMods)) {
      return configuredMods.some((mod) => {
        const k = String(mod?.key || mod?.name || "").trim();
        return k && (k === t || t.includes(k) || k.includes(t));
      });
    }
    return false;
  };

  // 支持模块跨多行（换行）与空行分段：将连续的非顶层标题行自动归入当前模块 bodyLines
  const logicalEntries = [];
  rawLines.forEach((line) => {
    if (line === "") {
      if (logicalEntries.length > 0) {
        const curBody = logicalEntries[logicalEntries.length - 1].bodyLines;
        if (curBody.length > 0 && curBody[curBody.length - 1] !== "") {
          curBody.push("");
        }
      }
      return;
    }
    // 1. 方括号 [模块名] 开启模块（支持 ### [模块名]、1. [模块名]、**[模块名]：** 等变体）
    const sqMatch = line.match(/^(?:#{1,6}\s*|\*\*|\*)?\s*(?:(?:#?\d+|[①-⑩])[\.、\s]*)?\[([^\]]+)\]\s*([:：]?)\s*(?:\*\*|\*)?\s*([:：]?)\s*(.*)$/);
    if (sqMatch) {
      const rawTitleInside = sqMatch[1].trim();
      let mTitle = cleanStatusHeaderTitle(rawTitleInside);
      const hasInlineColon = Boolean(sqMatch[2] || sqMatch[3]);
      let rest = sqMatch[4].trim();
      // 兼容 [角色关系 - 银发圣女] 复合标题
      const compM = mTitle.match(/^([^\s\-—:：/（(]{2,10})[\s\-—:：/]+([^）)\n]+)$/);
      if (compM) {
        const headClean = cleanStatusHeaderTitle(compM[1]);
        if (isKnownTopModuleTitle(headClean)) {
          mTitle = headClean;
          if (headClean === "角色关系" && compM[2].trim()) {
            rest = rest ? `角色: ${compM[2].trim()}\n${rest}` : `角色: ${compM[2].trim()}`;
          }
        }
      }
      const curEntry = logicalEntries.length > 0 ? logicalEntries[logicalEntries.length - 1] : null;
      const isInlineSubItem = curEntry && !isKnownTopModuleTitle(mTitle) && (/[|｜]/.test(rest) || /(?:好感|态度|动态|数量|效果)\s*[:：]/.test(rest));
      if (!isInlineSubItem) {
        logicalEntries.push({
          modTitle: mTitle,
          bodyLines: rest ? [rest] : [],
          isBracketModule: true,
          hasInlineColon
        });
        return;
      }
    }
    // 2. 中文方头括号 【模块名】（兼容 ### 【#2 主角状态】、**【主角状态】：** 等带序号/标题变体）
    const cnBracketMatch = line.match(/^(?:#{1,6}\s*|\*\*|\*)?\s*(?:(?:#?\d+|[①-⑩])[\.、\s]*)?【([^】]+)】\s*([:：]?)\s*(?:\*\*|\*)?\s*([:：]?)\s*(.*)$/);
    if (cnBracketMatch) {
      const candTitle = cleanStatusHeaderTitle(cnBracketMatch[1]);
      const hasInlineColon = Boolean(cnBracketMatch[2] || cnBracketMatch[3]);
      const rest = cnBracketMatch[4].trim();
      if (isKnownTopModuleTitle(candTitle) || logicalEntries.length === 0) {
        logicalEntries.push({
          modTitle: candTitle,
          bodyLines: rest ? [rest] : [],
          isBracketModule: true,
          hasInlineColon
        });
        return;
      }
    }
    // 2.5 无括号的 Markdown 标题或纯粗体独立标题行（如 ### 主角状态、**装备栏**）
    const mdBareHdrMatch = line.match(/^(?:#{1,6}\s+|\*\*\s*)(?:(?:#?\d+|[①-⑩])[\.、\s]*)?([^*\n:：\[\]【】]{2,14}?)\s*(?:\*\*)?\s*[:：]?\s*(?:\*\*)?\s*$/);
    if (mdBareHdrMatch) {
      const candMdTitle = cleanStatusHeaderTitle(mdBareHdrMatch[1]);
      if (isKnownTopModuleTitle(candMdTitle, true)) {
        logicalEntries.push({
          modTitle: candMdTitle,
          bodyLines: [],
          isBracketModule: true,
          hasInlineColon: false
        });
        return;
      }
    }
    // 3. 冒号前缀 模块名: 内容（若当前已在 [模块名] 块内，仅当严格匹配其他顶层模块名时才切换模块，防止「身体: xxx」等子字段误拆模块）
    const colonMatch = line.match(/^(?:#{1,6}\s*)?(?:\*\*([^*:：]+)\*\*|([^:：|｜*]{2,12}))\s*[:：]\s*(.*)$/);
    if (colonMatch) {
      const candTitle = cleanStatusHeaderTitle(colonMatch[1] || colonMatch[2] || "");
      const rest = (colonMatch[3] || "").trim();
      const curEntry = logicalEntries.length > 0 ? logicalEntries[logicalEntries.length - 1] : null;
      const canStartNew = !curEntry
        ? isKnownTopModuleTitle(candTitle, false) || true
        : (isKnownTopModuleTitle(candTitle, true) && candTitle !== curEntry.modTitle && (!curEntry.isBracketModule || curEntry.bodyLines.length > 0));
      if (canStartNew) {
        logicalEntries.push({
          modTitle: candTitle,
          bodyLines: rest ? [rest] : [],
          isBracketModule: false,
          hasInlineColon: true
        });
        return;
      }
    }
    // 4. 其余行作为当前模块的换行延续内容
    if (logicalEntries.length > 0) {
      logicalEntries[logicalEntries.length - 1].bodyLines.push(line);
    } else {
      logicalEntries.push({ modTitle: "", bodyLines: [line], isBracketModule: false, hasInlineColon: false });
    }
  });

  // 合并同名顶层模块（例如 AI 为每个 NPC 重复写了多次 [角色关系] 标题时，自动归并进同一个模块）
  const mergedLogicalEntries = [];
  logicalEntries.forEach((ent) => {
    const normTitle = String(ent.modTitle || "").trim();
    if (normTitle) {
      const existing = mergedLogicalEntries.find((x) => String(x.modTitle || "").trim() === normTitle);
      if (existing) {
        if (existing.bodyLines.length > 0 && existing.bodyLines[existing.bodyLines.length - 1] !== "") {
          existing.bodyLines.push("");
        }
        existing.bodyLines.push(...ent.bodyLines);
        return;
      }
    }
    mergedLogicalEntries.push(ent);
  });
  logicalEntries.splice(0, logicalEntries.length, ...mergedLogicalEntries);

  const sectionsHtml = [];
  const compactStatBars = [];
  const compactStatPills = [];
  const compactStatRawLines = [];

  const findConfiguredStatMod = (titleStr) => {
    if (!Array.isArray(configuredMods) || configuredMods.length === 0) return null;
    const cleanT = String(titleStr || "").trim();
    if (!cleanT || nonStatusMacroTitleRegex.test(cleanT)) return null;
    // 1. 精确键名匹配（支持识别被用户显式关闭的同名栏位）
    let exactFound = configuredMods.find((mod) => {
      const k = String(mod?.key || mod?.name || "").trim();
      return k && k === cleanT;
    });
    if (exactFound) return exactFound;
    // 2. 包含关系匹配（优先匹配已启用的栏位，避免已禁用的宽泛词误伤其他栏位）
    let subFound = configuredMods.find((mod) => {
      if (mod?.enabled === false) return false;
      const k = String(mod?.key || mod?.name || "").trim();
      return k && (cleanT.includes(k) || k.includes(cleanT));
    });
    if (subFound) return subFound;
    // 3. 类型与语义回退（仅匹配当前已启用的模块！绝不因禁用「装备栏」而误隐藏「身体栏/穿着装备/身体状况」）
    const enabledOnly = configuredMods.filter((m) => m && m.enabled !== false);
    let found = null;
    if (/进度|章节/i.test(cleanT)) {
      found = enabledOnly.find((m) => m.type === "progress_stats" && /进度|章节/i.test(m.key || ""));
    } else if (/^(?:主角状态|角色状态|状态栏|状态面板)$/i.test(cleanT)) {
      found = configuredMods.find((m) => m.id === "mod_stats" || (m.type === "progress_stats" && !/进度|章节/i.test(m.key || "")));
    } else if (/主角|环境状态|生命|体力|理智/i.test(cleanT)) {
      found = enabledOnly.find((m) => m.type === "progress_stats" && !/进度|章节/i.test(m.key || ""));
    } else if (/^(?:装备栏|装备)$/i.test(cleanT)) {
      found = configuredMods.find((m) => m.id === "mod_equip" || m.key === "装备栏");
    } else if (/装备|义体|武器|防具|装配|身体|穿戴|服饰|equipment/i.test(cleanT)) {
      found = enabledOnly.find((m) => m.type === "equipment_slots" || m.type === "gear");
    } else if (/^(?:物品栏|背包)$/i.test(cleanT)) {
      found = configuredMods.find((m) => m.id === "mod_inv" || m.key === "物品栏");
    } else if (/物品|道具|行囊|线索|储物|法宝|inventory|bag|item/i.test(cleanT)) {
      found = enabledOnly.find((m) => m.type === "inventory_grid" || m.type === "inventory");
    } else if (/^(?:角色关系|人物关系|好感栏)$/i.test(cleanT)) {
      found = configuredMods.find((m) => m.id === "mod_npc" || m.key === "角色关系");
    } else if (/关系|好感|同伴|羁绊|态度|npc|affinity/i.test(cleanT)) {
      found = enabledOnly.find((m) => m.type === "npc_affinity" || m.type === "relations");
    }
    return found || null;
  };

  // 通用模块化分块网格渲染器：将装备栏、身体栏、情报卡、世界新闻及自定义文字栏统一分割为「图标+槽位名 | 粗体核心词+(微简介)」的并排方块
  const slotIcons = {
    主手: "", 主武器: "", 武器: "",
    副手: "", 副武器: "", 便携武器: "",
    防具: "", 护甲: "", 上身: "", 身体: "", 躯干: "", 整体穿着: "", 穿着装备: "",
    下身: "", 内衣: "", 内裤: "", 袜子: "", 鞋子: "",
    饰品: "", 其他: "", 其他部位: "", 配件: "",
    头部: "", 面部: "", 眼部: "", 耳部: "", 颈部: "",
    胸部: "", 腹部: "", 腰带: "", 背部: "",
    手部: "", 左臂: "", 右臂: "", 腿部: "",
    靴子: "", 足部: "", 脚部: "",
    私处: "", 臀部: "",
    随身物品: "", 背包: "", 义眼: ""
  };
  const inferSlotBlockIcon = (slotName, modTitleCtx = "", fallbackIcon = "") => {
    const cleanKey = String(slotName || "").replace(/\s*\d+$/, "").trim();
    if (slotIcons[cleanKey]) return slotIcons[cleanKey];
    const combined = `${cleanKey} ${modTitleCtx}`;
    if (/新闻|传闻|消息|情报|广播|悬赏|公告|轶事|风声|rumor|news/i.test(combined)) return "📰";
    if (/任务|目标|主线|支线|委托|指引|quest|mission/i.test(combined)) return "🎯";
    if (/时间|日期|天气|季节|昼夜|时刻|时辰|世界状态/i.test(cleanKey)) return "🕒";
    if (/地点|位置|区域|场景|环境|坐标|方位/i.test(cleanKey)) return "📍";
    if (/金钱|金币|银币|银元|铜币|信用点|灵石|货币|财富|资金|盘缠/i.test(cleanKey)) return "🪙";
    if (/危机|威胁|警告|警戒|通缉|危险|代价/i.test(cleanKey)) return "⚠️";
    if (/线索|秘密|疑点|发现|调查/i.test(cleanKey)) return "🔍";
    if (/头|发|面|脸|眼|眸|耳|唇|口|鼻|神态|表情|视线/.test(cleanKey)) return "🪖";
    if (/颈|脖|胸|乳|腹|肚|腰|背|躯干|身体|皮肤|体温|呼吸|心跳|生理/.test(cleanKey)) return "🫀";
    if (/手|臂|腕|指|掌/.test(cleanKey)) return "🧤";
    if (/腿|膝|踝|足|脚|靴|鞋|袜/.test(cleanKey)) return "🦵";
    if (/臀|尻|私|穴|阴|下体|隐秘|内衣|内裤/.test(cleanKey)) return "🌸";
    if (/武器|剑|刀|枪|杖|弓|弩|刃|匕|主手|副手/.test(cleanKey)) return "⚔️";
    if (/防具|护甲|甲|衣|服|裙|裤|袍|帽|饰|戒|链|镯|穿戴|穿着/.test(cleanKey)) return "🧥";
    if (/状态|异常|buff|效果|境界|等级|称号|身份/i.test(cleanKey)) return "✨";
    return fallbackIcon;
  };
  const isBodyPartSlotName = (name) => /^(?:头部|面部|眼部|耳部|颈部|胸部|腹部|背部|躯干|左臂|右臂|手部|臀部|私处|腿部|足部|脚部|其他部位)$/.test(name);
  const isGearSlotName = (name) => /^(?:主手|副手|主武器|副武器|便携武器|武器|防具|护甲|整体穿着|上身|下身|内衣|内裤|袜子|鞋子|靴子|饰品|配件|腰带|随身物品|背包)$/.test(name);

  // 保护括号内部文本，将挤在同一行的多组「字段: 值」安全拆分为多行（保留原有空行分段，不误造多余空行）
  const splitInlineKvPreservingParens = (text) => {
    const parenPool = [];
    const maskParens = (s) =>
      String(s || "").replace(/\([^()\n]*\)|（[^（）\n]*）/g, (m) => {
        const id = parenPool.length;
        parenPool.push(m);
        return `__PAREN_MASK_${id}__`;
      });
    const unmaskParens = (s) =>
      String(s || "").replace(/__PAREN_MASK_(\d+)__/g, (_, idx) => parenPool[Number(idx)] || "");

    const processedLines = String(text || "")
      .split(/\r?\n/)
      .map((rawLn) => {
        if (!rawLn.trim()) return "";
        let masked = maskParens(rawLn);
        masked = masked
          .replace(/(?:^|[ \t]+|[,，;；。！？]\s*)(?:\*\*|\*)?\s*[\[【]([^\]】\n]{1,14})[\]】]\s*(?:\*\*|\*)?\s*[:：]\s*(?:\*\*|\*)?\s*/g, "\n$1: ")
          .replace(/(?:\*\*|\*)([^*\n:：|｜]{1,14}?)\s*[:：]\s*(?:\*\*|\*)+\s*/g, "\n$1: ")
          .replace(/(?:\*\*|\*)([^*\n:：|｜]{1,14}?)(?:\*\*|\*)+\s*[:：]\s*/g, "\n$1: ")
          .replace(/(?:^|[ \t]+|[,，;；。！？]\s*)(?![0-9]+\s*(?:\*\*|\*)?\s*[:：])([^\s,，;；。！？|｜:：*\n()/]{1,12}?)\s*(?:\*\*|\*)?\s*[:：]\s*\*+\s*/g, "\n$1: ")
          .replace(/[,，;；。！？]\s*(?![0-9]+\s*[:：])([^\s,，;；。！？|｜:：*\n()/]{1,10}?)\s*[:：]\s*/g, "\n$1: ")
          .replace(/(__PAREN_MASK_\d+__)[ \t]*(?![0-9]+\s*[:：])([^\s,，;；。！？|｜:：*\n()/]{1,10})\s*[:：]\s*/g, "$1\n$2: ")
          .replace(/[ \t]+(?![0-9]+\s*[:：])([^\s,，;；。！？|｜:：*\n()/]{1,8})\s*[:：]\s*/g, "\n$1: ")
          .replace(/^\n+|\n+$/g, "")
          .replace(/\n{2,}/g, "\n");
        return unmaskParens(masked);
      });
    return processedLines.join("\n").replace(/\n{3,}/g, "\n\n");
  };

  const renderModularBlockGridHtml = (rawBodyText, modTitleCtx = "状态", defaultIcon = "") => {
    const preSplitText = splitInlineKvPreservingParens(rawBodyText);
    const rawParagraphs = preSplitText.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
    const slotGroups = [];

    const splitProseIntoSentences = (str) => {
      const clean = String(str || "").trim();
      if (!clean) return [];
      // 1. 若含内联编号（如 1. xxx 2. xxx 或 ① xxx ② xxx），优先按编号切分
      if (/(?:^|[\s。；;，,]+)(?:[1-9]\d*[\.、．\)]|[①-⑩])\s*\S/.test(clean)) {
        const numParts = clean
          .split(/(?:^|[\s。；;，,]+)(?=(?:[1-9]\d*[\.、．\)]|[①-⑩])\s*\S)/)
          .map((s) => s.replace(/^(?:[1-9]\d*[\.、．\)]|[①-⑩])\s*/, "").replace(/[。；;]+$/g, "").trim())
          .filter(Boolean);
        if (numParts.length > 1) return numParts;
      }
      // 2. 若为多句长文（含句号/感叹号且在括号外至少有 2 个分句），按句号拆分为独立块
      const sentParts = splitOutsideParens(clean, /[。！？]+/)
        .map((s) => s.replace(/^(?:[1-9]\d*[\.、．\)]|[①-⑩])\s*/, "").trim())
        .filter(Boolean);
      if (sentParts.length >= 2 && clean.length >= 20) {
        return sentParts;
      }
      return [clean];
    };

    rawParagraphs.forEach((para) => {
      const rawLines = para.split(/\n/).map((l) => l.trim()).filter(Boolean);
      const expandedSlots = [];

      rawLines.forEach((line) => {
        // 按分号/竖线切分同行多条目（保护括号内部）
        let segs = splitOutsideParens(line, /[|｜;；]/)
          .map((s) => s.replace(/^\*+|\*+$/g, "").trim())
          .filter(Boolean);
        if (segs.length === 0) return;

        // 若单行未被分号/竖线切开，但内部包含多条编号或长段落多句号（如「重要新闻: 1. 事件A。2. 事件B。」或「事件A。事件B。」），自动拆分为多块
        if (segs.length === 1) {
          const single = segs[0];
          const cPos = single.search(/[:：]/);
          if (cPos > 0 && cPos <= 15) {
            const bKey = single.slice(0, cPos).replace(/^\*+|\*+$/g, "").trim();
            const bVal = single.slice(cPos + 1).trim();
            const subSents = splitProseIntoSentences(bVal);
            if (subSents.length > 1) {
              subSents.forEach((sv, sIdx) => {
                if (/^([^\d:：][^:：]{0,11})[:：]\s*\S/.test(sv)) {
                  expandedSlots.push(sv);
                } else {
                  expandedSlots.push(`${bKey} ${sIdx + 1}: ${sv}`);
                }
              });
              return;
            }
          } else {
            const subSents = splitProseIntoSentences(single);
            if (subSents.length > 1) {
              subSents.forEach((sv, sIdx) => {
                if (/^([^\d:：][^:：]{0,11})[:：]\s*\S/.test(sv)) {
                  expandedSlots.push(sv);
                } else {
                  expandedSlots.push(`${modTitleCtx} ${sIdx + 1}: ${sv}`);
                }
              });
              return;
            }
          }
        }

        if (segs.length > 1) {
          const firstColon = segs[0].search(/[:：]/);
          const firstHasKey = firstColon > 0 && firstColon <= 15;
          const restHaveKey = segs.slice(1).some((sg) => {
            const c = sg.search(/[:：]/);
            return c > 0 && c <= 15;
          });
          // 若形如「重要新闻：事件A；事件B；事件C」，自动拆分为「重要新闻 1: 事件A」「重要新闻 2: 事件B」等独立方块
          if (firstHasKey && !restHaveKey) {
            const baseKey = segs[0].slice(0, firstColon).replace(/^\*+|\*+$/g, "").trim();
            const firstVal = segs[0].slice(firstColon + 1).trim();
            const allVals = [firstVal, ...segs.slice(1)]
              .map((v) => v.replace(/^(?:[1-9]\d*[\.、．\)]|[①-⑩])\s*/, "").trim())
              .filter(Boolean);
            allVals.forEach((v, idx) => {
              if (/^([^\d:：][^:：]{0,11})[:：]\s*\S/.test(v)) {
                expandedSlots.push(v);
              } else {
                expandedSlots.push(`${baseKey} ${idx + 1}: ${v}`);
              }
            });
            return;
          }
        }

        segs.forEach((sg) => {
          const numMatch = sg.match(/^(?:([1-9]\d*)[\.、．\)]|([①-⑩]))\s*(.+)$/);
          if (numMatch && sg.search(/[:：]/) < 0) {
            const numLabel = numMatch[1] || numMatch[2];
            expandedSlots.push(`${modTitleCtx} ${numLabel}: ${numMatch[3].trim()}`);
          } else {
            expandedSlots.push(sg);
          }
        });
      });

      // 若多行均无冒号，自动赋予序号槽位名以便分块展示
      const normalizedSlots = expandedSlots.map((s, idx) => {
        const cIdx = s.search(/[:：]/);
        if (cIdx > 0 && cIdx <= 16) return s;
        return expandedSlots.length > 1 ? `${modTitleCtx} ${idx + 1}: ${s}` : `${modTitleCtx}: ${s}`;
      });

      let curGroup = [];
      let curCategory = null; // 'body' | 'gear' | null
      normalizedSlots.forEach((s) => {
        const cIdx = s.search(/[:：]/);
        const sName = (cIdx > 0 ? s.slice(0, cIdx) : "").replace(/^\*+|\*+$/g, "").trim();
        const nextCat = isBodyPartSlotName(sName) ? "body" : (isGearSlotName(sName) ? "gear" : curCategory);
        if (curGroup.length > 0 && curCategory === "body" && nextCat === "gear") {
          slotGroups.push(curGroup);
          curGroup = [s];
          curCategory = nextCat;
        } else {
          curGroup.push(s);
          if (nextCat) curCategory = nextCat;
        }
      });
      if (curGroup.length > 0) slotGroups.push(curGroup);
    });

    const renderSlotHtml = (s) => {
      const colonIdx = s.search(/[:：]/);
      const slotName = (colonIdx > 0 ? s.slice(0, colonIdx) : modTitleCtx).replace(/^\*+|\*+$/g, "").trim() || modTitleCtx;
      let rawVal = (colonIdx > 0 ? s.slice(colonIdx + 1) : s).replace(/^\*+|\*+$/g, "").trim();
      rawVal = rawVal.replace(/^(?:[1-9]\d*[\.、．\)]|[①-⑩])\s*/, "").replace(/^[。，、；;]+|[。；;]+$/g, "").trim();
      const ic = inferSlotBlockIcon(slotName, modTitleCtx, defaultIcon);
      const isEmpty = !rawVal || /^(?:无|空|未装备|暂无|none|-)$/i.test(rawVal);

      let parsed = parseItemWithMicroDesc(rawVal);
      // 若 AI 未写括号，而是用逗号/破折号写了「核心状态，补充细节说明」，自动将首分句提炼为粗体主词、后半句转为括号微简介
      if (!parsed.itemDesc && rawVal && /[,，——]/.test(rawVal)) {
        const commaIdx = rawVal.search(/[,，——]/);
        if (commaIdx >= 2 && commaIdx <= 26) {
          const headPart = rawVal.slice(0, commaIdx).trim();
          const tailPart = rawVal.slice(commaIdx + 1).replace(/^[\s—\-，,]+|[。！？!?.]+$/g, "").trim();
          if (headPart && tailPart) {
            parsed = { itemName: headPart, itemDesc: tailPart, qty: 1, hasExplicitQty: false };
          }
        }
      }

      const dispName = parsed.itemName || rawVal || "无";
      const isLongSlot = (dispName.length + (parsed.itemDesc || "").length) > 56;
      const descHtml = !isEmpty && parsed.itemDesc
        ? `<span class="equip-item-desc">(${escapeHtml(parsed.itemDesc)})</span>`
        : "";
      return `
        <div class="bg3-equip-slot ${isEmpty ? "is-empty" : ""} ${isLongSlot ? "is-long-slot" : ""}" onclick="${isEmpty ? "" : `window.handleInventoryItemClick('${escapeJsAttr(dispName)}', event, '${escapeJsAttr(parsed.itemDesc || "")}')`}" title="${isEmpty ? "空" : `${escapeHtml(dispName)}${parsed.itemDesc ? ` (${escapeHtml(parsed.itemDesc)})` : ""}`}">
          <span class="equip-slot-label">${ic} ${escapeHtml(slotName)}</span>
          <div class="equip-slot-val">
            <span class="equip-item-name">${escapeHtml(dispName)}</span>
            ${descHtml}
          </div>
        </div>
      `;
    };

    return slotGroups
      .map((grp) => `<div class="bg3-equip-grid">${grp.map(renderSlotHtml).join("")}</div>`)
      .join('<div class="bg3-module-segment-divider"></div>');
  };

  const flushCompactStats = (titleOverride = "状态面板") => {
    if (compactStatBars.length === 0 && compactStatPills.length === 0 && compactStatRawLines.length === 0) return;
    const fallbackMod = findConfiguredStatMod(titleOverride);
    if (fallbackMod && fallbackMod.enabled === false && compactStatRawLines.length === 0) {
      compactStatBars.splice(0);
      compactStatPills.splice(0);
      return;
    }
    const displayTitle = (fallbackMod && fallbackMod.enabled !== false) ? (fallbackMod.key || titleOverride) : "状态面板";
    const modKeyAttr = escapeHtml(displayTitle);
    const modIdAttr = escapeHtml((fallbackMod && fallbackMod.enabled !== false) ? (fallbackMod.id || "") : "");
    const cfgBtn = `<button type="button" class="module-quick-cfg-btn" onclick="event.stopPropagation(); window.openModuleQuickEditor && window.openModuleQuickEditor('${escapeJsAttr(modIdAttr || displayTitle)}')" title="模块设置">设置</button>`;
    const rawLinesCopy = compactStatRawLines.splice(0);
    const pillsCopy = compactStatPills.splice(0);
    const barsCopy = compactStatBars.splice(0);
    const nonBarsHtml = (barsCopy.length === 0 && rawLinesCopy.length > 0)
      ? renderModularBlockGridHtml(rawLinesCopy.join("\n"), displayTitle, "")
      : (pillsCopy.length > 0
        ? (pillsCopy.every((p) => p.startsWith('<div class="bg3-stats-pills-row">'))
          ? pillsCopy.join("")
          : `<div class="bg3-stats-pills-row">${pillsCopy.join("")}</div>`)
        : "");
    sectionsHtml.push(`
      <div class="bg3-module-block" data-mod-id="${modIdAttr}" data-mod-key="${modKeyAttr}">
        <div class="bg3-module-title"><span>${escapeHtml(displayTitle)}</span>${cfgBtn}</div>
        ${barsCopy.length > 0 ? `<div class="bg3-stats-bars-grid">${barsCopy.join("")}</div>` : ""}
        ${nonBarsHtml}
      </div>
    `);
  };

  logicalEntries.forEach((entry) => {
    let modTitle = String(entry.modTitle || "").trim();
    if (nonStatusMacroTitleRegex.test(modTitle)) {
      return;
    }
    let bodyText = (entry.bodyLines || []).join("\n").replace(/\n{3,}/g, "\n\n").trim();

    // 若模型在 <status> 开头漏写了第一个 [主角状态] 标题但直接输出了「生命值: 100/100」等键值行，自动归入首个启用的状态模块
    if (!modTitle && bodyText && (/[:：]/.test(bodyText) || /\d+\s*\/\s*\d+/.test(bodyText))) {
      const firstActiveStatMod = (configuredMods || []).find(
        (m) => m && m.enabled !== false && !["thinking_fold", "story_narrative", "action_choices", "content_scale"].includes(m.type)
      );
      modTitle = String(firstActiveStatMod?.key || firstActiveStatMod?.name || "主角状态").trim();
    }

    if (!modTitle || !bodyText) {
      const cleanRaw = (bodyText || modTitle).replace(/\*\*/g, "").replace(/^\*+|\*+$/g, "").trim();
      if (cleanRaw && !nonStatusMacroTitleRegex.test(cleanRaw)) {
        const isLong = cleanRaw.length > 26 || cleanRaw.includes("\n");
        compactStatPills.push(`<span class="status-kv-pill ${isLong ? "is-long-pill" : ""}">${escapeHtml(cleanRaw)}</span>`);
        compactStatRawLines.push(cleanRaw);
      }
      return;
    }

    // 智能规范化模块内部的内联多字段（保护括号内部，支持单空格/逗号/星号切分）与多段换行文本
    bodyText = splitInlineKvPreservingParens(bodyText)
      .replace(/\*\*/g, "")
      .replace(/[█▓▒░▪▫■□]{2,}\s*/g, "")
      .replace(/^\n+|\n+$/g, "")
      .replace(/\n{3,}/g, "\n\n")
      .trim();

    // 若栏位被用户显式关闭（enabled === false），则跳过；否则无论标准栏位还是自定义 [栏位名] 均自动智能渲染
    const matchedMod = findConfiguredStatMod(modTitle);
    if (matchedMod && (matchedMod.enabled === false || ["thinking_fold", "story_narrative", "action_choices"].includes(matchedMod.type))) {
      return;
    }
    const explicitType = matchedMod?.type || "";
    const modIdAttr = escapeHtml(matchedMod?.id || "");
    const modKeyAttr = escapeHtml(matchedMod?.key || modTitle);
    const cfgBtnHtml = `<button type="button" class="module-quick-cfg-btn" onclick="event.stopPropagation(); window.openModuleQuickEditor && window.openModuleQuickEditor('${escapeJsAttr(matchedMod?.id || modTitle)}')" title="模块设置">设置</button>`;

    const isEquip =
      explicitType === "equipment_slots" ||
      explicitType === "gear" ||
      (!explicitType && /装备|义体|武器|防具|装配|身体|穿戴|服饰|部位|equipment/i.test(modTitle) && (!entry.hasInlineColon || bodyText.includes("\n")));

    const isInventory =
      explicitType === "inventory_grid" ||
      explicitType === "inventory" ||
      (!explicitType && /物品|背包|道具|行囊|储物|法宝|inventory|bag|item/i.test(modTitle) && (!entry.hasInlineColon || bodyText.includes("\n")));

    const isNpc =
      explicitType === "npc_affinity" ||
      explicitType === "relations" ||
      (!explicitType && /关系|好感|同伴|羁绊|affinity/i.test(modTitle));

    const isTextCard =
      explicitType === "text_card" ||
      (!explicitType && !isEquip && !isInventory && !isNpc && !/\d+\s*\/\s*\d+/.test(bodyText));

    // 0. 独立文本 / 情报卡 / 世界新闻模块（统一采用装备栏式分块网格卡片展示）
    if (isTextCard) {
      flushCompactStats();
      const groupsHtml = renderModularBlockGridHtml(bodyText, modTitle, "");
      sectionsHtml.push(`
        <div class="bg3-module-block" data-mod-id="${modIdAttr}" data-mod-key="${modKeyAttr}">
          <div class="bg3-module-title"><span>${escapeHtml(modTitle)}</span>${cfgBtnHtml}</div>
          ${groupsHtml || `<div class="bg3-text-card-content">${escapeHtml(bodyText)}</div>`}
        </div>
      `);
      return;
    }

    // 1. 装备栏 / 身体栏识别（支持多段落分组、身体部位与武器服饰自动分段、并排分块展示）
    if (isEquip) {
      flushCompactStats();
      const groupsHtml = renderModularBlockGridHtml(bodyText, modTitle, "");
      sectionsHtml.push(`
        <div class="bg3-module-block" data-mod-id="${modIdAttr}" data-mod-key="${modKeyAttr}">
          <div class="bg3-module-title"><span>${escapeHtml(modTitle)}</span>${cfgBtnHtml}</div>
          ${groupsHtml}
        </div>
      `);
      return;
    }

    // 2. 物品栏 / 背包 / 自定义储物格识别（支持括号微简介、换行分段与点击物品交互）
    if (isInventory) {
      flushCompactStats();
      const rawItems = splitOutsideParens(bodyText, /[,，、|｜；;\n]/)
        .map((s) => s.replace(/^\*+|\*+$/g, "").trim())
        .filter(Boolean);
      const itemsHtml = rawItems.map((rawItem) => {
        if (/^(?:无|空|暂无|none|-)$/i.test(rawItem)) {
          return `<span style="font-size:12px;color:var(--text-dim);">暂无物品</span>`;
        }
        const { itemName, itemDesc, qty, hasExplicitQty } = parseItemWithMicroDesc(rawItem);
        const showQty = qty > 1 || hasExplicitQty;
        const itemIcon = typeof window.inferTrpgItemIcon === "function" ? window.inferTrpgItemIcon(itemName, itemDesc) : "";
        const tooltip = itemDesc ? `${itemName} (${itemDesc})` : itemName;
        return `
          <button type="button" class="bg3-inv-cell" onclick="window.handleInventoryItemClick('${escapeJsAttr(itemName)}', event, '${escapeJsAttr(itemDesc)}')" title="${escapeHtml(tooltip)}">
            <span class="inv-item-icon">${itemIcon}</span>
            <span class="inv-item-name">${escapeHtml(itemName)}</span>
            ${itemDesc ? `<span class="inv-item-desc">(${escapeHtml(itemDesc)})</span>` : ""}
            ${showQty ? `<span class="inv-item-qty">×${qty}</span>` : ""}
          </button>
        `;
      }).join("");
      sectionsHtml.push(`
        <div class="bg3-module-block" data-mod-id="${modIdAttr}" data-mod-key="${modKeyAttr}">
          <div class="bg3-module-title"><span>${escapeHtml(modTitle)}</span>${cfgBtnHtml}</div>
          <div class="bg3-inv-grid">${itemsHtml}</div>
        </div>
      `);
      return;
    }

    // 3. 角色关系 / 好感栏识别（支持单行竖线分隔或多行「角色 + 好感/态度/动态」自动归组为独立 NPC 卡片）
    if (isNpc) {
      flushCompactStats();
      const normalizedNpcBody = splitInlineKvPreservingParens(bodyText);
      const rawLines = normalizedNpcBody
        .split(/\r?\n/)
        .map((s) => s.replace(/^\s*[-*•]\s*/, "").trim())
        .filter(Boolean);
      const npcAttrLineRe = /^(?:好感度?|好感|信赖度?|信任度?|亲密度?|恶堕度?|服从度?|警戒度?|戒心|敌意|态度|倾向|立场|关系|身份|定位|动态|动作|表现|心理|神态|状态|当前动态|当前态度|备注|印象|评价)\s*[:：]/i;
      const npcNameLineRe = /^(?:角色|人物|姓名|对象|目标|同伴|队友|敌人|NPC)\s*\d*\s*[:：]/i;

      const groupedNpcBlocks = [];
      let currentNpcLines = [];

      rawLines.forEach((line) => {
        const hasPipe = /[|｜]/.test(line);
        if (hasPipe) {
          if (currentNpcLines.length > 0) {
            groupedNpcBlocks.push(currentNpcLines.join("\n"));
            currentNpcLines = [];
          }
          groupedNpcBlocks.push(line);
          return;
        }
        if (npcNameLineRe.test(line)) {
          if (currentNpcLines.length > 0) {
            groupedNpcBlocks.push(currentNpcLines.join("\n"));
          }
          currentNpcLines = [line];
          return;
        }
        if (npcAttrLineRe.test(line)) {
          if (currentNpcLines.length === 0) {
            currentNpcLines = ["当前角色"];
          }
          currentNpcLines.push(line);
          return;
        }
        // 非属性行（如直接写角色名「鹰眼(队友)」或分号隔开的条目）开启新角色卡
        if (currentNpcLines.length > 0) {
          groupedNpcBlocks.push(currentNpcLines.join("\n"));
        }
        currentNpcLines = [line];
      });
      if (currentNpcLines.length > 0) {
        groupedNpcBlocks.push(currentNpcLines.join("\n"));
      }

      const npcEntries = groupedNpcBlocks.length > 0 ? groupedNpcBlocks : [bodyText];
      const npcCardsHtml = npcEntries.map((entryText) => {
        const segs = entryText.split(/\s*[|｜\n]\s*/).map((s) => s.trim()).filter(Boolean);
        const npcName = (segs[0] || "当前角色").replace(/^(?:角色|人物|姓名|对象|目标|同伴|队友|敌人|NPC)\s*\d*\s*[:：]\s*/i, "").trim() || "当前角色";
        let affinityPct = null;
        let affinityLabel = "";
        const metaTags = [];
        segs.slice(1).forEach((seg) => {
          const ratioM = seg.match(/([^:：]+)[:：]\s*(-?\d+)\s*\/\s*(\d+)/);
          if (ratioM) {
            const cur = parseInt(ratioM[2], 10);
            const max = Math.max(1, parseInt(ratioM[3], 10));
            affinityPct = Math.max(0, Math.min(100, Math.round((cur / max) * 100)));
            affinityLabel = `${ratioM[1].trim()}: ${cur}/${max}`;
          } else {
            metaTags.push(seg);
          }
        });
        return `
          <div class="bg3-npc-card">
            <div class="bg3-npc-header">
              <span class="bg3-npc-name">${escapeHtml(npcName)}</span>
              ${affinityPct !== null ? `
                <div class="bg3-stat-bar-wrap" style="min-width:140px;max-width:220px;">
                  <div class="bg3-stat-bar-top"><span>${escapeHtml(affinityLabel)}</span></div>
                  <div class="bg3-stat-bar-track"><div class="bg3-stat-bar-fill fill-pink" style="width:${affinityPct}%;background:linear-gradient(90deg,#db2777,#ec4899,#f472b6);box-shadow:0 0 8px rgba(236,72,153,0.45);"></div></div>
                </div>
              ` : ""}
            </div>
            ${metaTags.length > 0 ? `<div class="bg3-npc-meta">${metaTags.map((t) => `<span class="bg3-npc-tag">${escapeHtml(t)}</span>`).join("")}</div>` : ""}
          </div>
        `;
      }).join("");
      sectionsHtml.push(`
        <div class="bg3-module-block" data-mod-id="${modIdAttr}" data-mod-key="${escapeHtml(matchedMod?.key || modTitle || "角色关系")}">
          <div class="bg3-module-title"><span>${escapeHtml(modTitle || "角色关系")}</span>${cfgBtnHtml}</div>
          <div class="bg3-npc-list">${npcCardsHtml}</div>
        </div>
      `);
      return;
    }

    // 4. 默认：主角状态栏 / 数值进度条 + 分块属性卡片（若自定义栏位无数值进度条，则自动以装备式分块网格渲染）
    const lines = bodyText.split(/\n/);
    const barsHtml = [];
    const nonBarLines = [];
    const pillRowGroupsHtml = [];
    let flatIdx = 0;

    lines.forEach((rawLine) => {
      const trimmedLine = rawLine.trim();
      if (!trimmedLine) {
        if (pillRowGroupsHtml.length > 0 && pillRowGroupsHtml[pillRowGroupsHtml.length - 1] !== "__DIVIDER__") {
          pillRowGroupsHtml.push("__DIVIDER__");
        }
        nonBarLines.push("");
        return;
      }
      const lineParts = splitOutsideParens(trimmedLine, /[|｜]/).map((s) => s.replace(/^\*+|\*+$/g, "").trim()).filter(Boolean);
      const rowPills = [];
      const rowNonBarParts = [];

      lineParts.forEach((p) => {
        const idx = flatIdx++;
        const ratioMatch = p.match(/^(?:([^:：]+)[:：]\s*)?(-?\d+)\s*\/\s*(\d+)(?:\s*[(（]([^)）]+)[)）])?$/);
        const pctMatch = !ratioMatch ? p.match(/^(?:([^:：]+)[:：]\s*)?(\d{1,3})%(?:\s*[(（]([^)）]+)[)）])?$/) : null;
        const getBarVisuals = (lbl, pctVal) => {
          if (/好感|亲密|信赖|信任|恶堕|堕落|淫乱|羞耻|兴奋|快感|爱意|倾慕/i.test(lbl)) {
            return {
              cls: "fill-pink",
              bg: "linear-gradient(90deg,#db2777,#ec4899,#f472b6)",
              glow: "0 0 8px rgba(236,72,153,0.45)",
              numColor: "#f9a8d4"
            };
          }
          if (/理智|san|精神|魔力|mp|法力|灵力|心力|神识/i.test(lbl)) {
            return {
              cls: "fill-indigo",
              bg: "linear-gradient(90deg,#4f46e5,#6366f1,#818cf8)",
              glow: "0 0 8px rgba(99,102,241,0.45)",
              numColor: "#a5b4fc"
            };
          }
          if (/体力|精力|耐力|sp|护盾|能量|怒气|饱腹|饥饿/i.test(lbl)) {
            return {
              cls: "fill-amber",
              bg: "linear-gradient(90deg,#d97706,#f59e0b,#fbbf24)",
              glow: "0 0 8px rgba(245,158,11,0.45)",
              numColor: "#fcd34d"
            };
          }
          if (pctVal <= 30) {
            return {
              cls: "fill-danger",
              bg: "linear-gradient(90deg,#dc2626,#ef4444,#f87171)",
              glow: "0 0 8px rgba(239,68,68,0.5)",
              numColor: "#fca5a5"
            };
          }
          return {
            cls: "fill-emerald",
            bg: "linear-gradient(90deg,#059669,#10b981,#34d399)",
            glow: "0 0 8px rgba(16,185,129,0.45)",
            numColor: "#6ee7b7"
          };
        };
        if (ratioMatch) {
          const label = (ratioMatch[1] || (idx === 0 ? modTitle : "数值")).trim();
          const cur = parseInt(ratioMatch[2], 10);
          const max = Math.max(1, parseInt(ratioMatch[3], 10));
          const note = (ratioMatch[4] || "").trim();
          const pct = Math.max(0, Math.min(100, Math.round((cur / max) * 100)));
          const vis = getBarVisuals(label, pct);
          barsHtml.push(`
            <div class="bg3-stat-bar-wrap">
              <div class="bg3-stat-bar-top">
                <span class="stat-label">${escapeHtml(label)}${note ? ` <small style="opacity:0.75;">(${escapeHtml(note)})</small>` : ""}</span>
                <span class="stat-num" style="color:${vis.numColor};font-weight:700;">${cur} / ${max}</span>
              </div>
              <div class="bg3-stat-bar-track">
                <div class="bg3-stat-bar-fill ${vis.cls}" style="width:${pct}%;background:${vis.bg};box-shadow:${vis.glow};"></div>
              </div>
            </div>
          `);
        } else if (pctMatch) {
          const label = (pctMatch[1] || (idx === 0 ? modTitle : "状态")).trim();
          const pct = Math.max(0, Math.min(100, parseInt(pctMatch[2], 10)));
          const note = (pctMatch[3] || "").trim();
          const vis = getBarVisuals(label, pct);
          barsHtml.push(`
            <div class="bg3-stat-bar-wrap">
              <div class="bg3-stat-bar-top">
                <span class="stat-label">${escapeHtml(label)}${note ? ` <small style="opacity:0.75;">(${escapeHtml(note)})</small>` : ""}</span>
                <span class="stat-num" style="color:${vis.numColor};font-weight:700;">${pct}%</span>
              </div>
              <div class="bg3-stat-bar-track">
                <div class="bg3-stat-bar-fill ${vis.cls}" style="width:${pct}%;background:${vis.bg};box-shadow:${vis.glow};"></div>
              </div>
            </div>
          `);
        } else if (/^(?:状态|buff|异常|效果)[:：]/i.test(p)) {
          rowNonBarParts.push(p);
          const buffs = splitOutsideParens(p.replace(/^[^:：]+[:：]\s*/, ""), /[,，、;；]/).map((s) => s.trim()).filter(Boolean);
          buffs.forEach((b) => {
            const isLong = b.length > 42;
            rowPills.push(`<span class="status-buff-pill ${isLong ? "is-long-pill" : ""}">${escapeHtml(b)}</span>`);
          });
        } else {
          const hasOwnColon = /[:：]/.test(p);
          const kvText = (!hasOwnColon && idx === 0 && !/主角状态|状态栏/.test(modTitle)) ? `${modTitle}: ${p}` : p;
          rowNonBarParts.push(kvText);
          const isLong = kvText.length > 48 || kvText.includes("\n");
          const cIdx = kvText.search(/[:：]/);
          if (cIdx > 0 && cIdx <= 14) {
            const k = kvText.slice(0, cIdx).trim();
            const v = kvText.slice(cIdx + 1).trim();
            rowPills.push(`<span class="status-kv-pill ${isLong ? "is-long-pill" : ""}"><strong class="status-kv-key">${escapeHtml(k)}:</strong> <span class="status-kv-val">${escapeHtml(v)}</span></span>`);
          } else {
            rowPills.push(`<span class="status-kv-pill ${isLong ? "is-long-pill" : ""}">${escapeHtml(kvText)}</span>`);
          }
        }
      });

      if (rowNonBarParts.length > 0) {
        nonBarLines.push(rowNonBarParts.join(" | "));
      }
      if (rowPills.length > 0) {
        pillRowGroupsHtml.push(`<div class="bg3-stats-pills-row">${rowPills.join("")}</div>`);
      }
    });

    while (pillRowGroupsHtml.length > 0 && pillRowGroupsHtml[pillRowGroupsHtml.length - 1] === "__DIVIDER__") {
      pillRowGroupsHtml.pop();
    }
    const renderedPillRows = pillRowGroupsHtml
      .map((item) => (item === "__DIVIDER__" ? '<div class="bg3-module-segment-divider"></div>' : item))
      .join("");

    const isStandaloneBracketSection = entry.isBracketModule && (!entry.hasInlineColon || bodyText.includes("\n"));
    if (matchedMod || isStandaloneBracketSection || /主角状态|状态栏/i.test(modTitle)) {
      flushCompactStats();
      // 若该功能栏没有任何数值进度条（例如用户新建了自定义栏位但保持了默认的 progress_stats 类型，或写成了纯文字段落），直接采用装备式分块网格渲染！
      const nonBarBody = nonBarLines.join("\n").replace(/\n{3,}/g, "\n\n").trim();
      const useBlockGridForNonBars = barsHtml.length === 0 && Boolean(nonBarBody);
      const nonBarsHtml = useBlockGridForNonBars
        ? renderModularBlockGridHtml(nonBarBody, modTitle, "")
        : renderedPillRows;
      sectionsHtml.push(`
        <div class="bg3-module-block" data-mod-id="${modIdAttr}" data-mod-key="${modKeyAttr}">
          <div class="bg3-module-title"><span>${escapeHtml(modTitle)}</span>${cfgBtnHtml}</div>
          ${barsHtml.length > 0 ? `<div class="bg3-stats-bars-grid">${barsHtml.join("")}</div>` : ""}
          ${nonBarsHtml}
        </div>
      `);
    } else {
      compactStatBars.push(...barsHtml);
      if (renderedPillRows) compactStatPills.push(renderedPillRows);
      if (nonBarLines.length > 0) compactStatRawLines.push(...nonBarLines);
    }
  });

  flushCompactStats("主角状态");

  if (window.CONTENT_SCALE_FEATURE_ENABLED) {
    const isScaleModExplicitlyDisabled = Array.isArray(allConfiguredMods) && allConfiguredMods.some(
      (m) => m && (m.id === "mod_scale" || m.type === "content_scale" || String(m.key || "").trim() === "内容尺度") && m.enabled === false
    );
    if (!isScaleModExplicitlyDisabled && typeof window.renderContentScaleStatusBlockHtml === "function") {
      sectionsHtml.push(window.renderContentScaleStatusBlockHtml(activeProj));
    }
  }

  if (sectionsHtml.length === 0) return "";
  if (Array.isArray(configuredMods) && configuredMods.length > 0 && sectionsHtml.length > 1) {
    const getOrderIdx = (htmlStr) => {
      const idM = htmlStr.match(/data-mod-id="([^"]*)"/);
      const modId = idM ? idM[1] : "";
      if (modId) {
        const byId = configuredMods.findIndex((mod) => mod?.id === modId);
        if (byId !== -1) return byId;
      }
      const m = htmlStr.match(/data-mod-key="([^"]+)"/);
      const key = m ? m[1] : "";
      if (!key) return 999;
      const idx = configuredMods.findIndex((mod) => {
        const k = String(mod?.key || mod?.name || "").trim();
        return k && (k === key || key.includes(k) || k.includes(key));
      });
      return idx !== -1 ? idx : 999;
    };
    const sorted = sectionsHtml
      .map((html, origIdx) => ({ html, order: getOrderIdx(html), origIdx }))
      .sort((a, b) => (a.order !== b.order ? a.order - b.order : a.origIdx - b.origIdx))
      .map((x) => x.html);
    return `<div class="bg3-status-hud-card trpg-universal-module" data-module="status">${sorted.join("")}</div>`;
  }
  return `<div class="bg3-status-hud-card trpg-universal-module" data-module="status">${sectionsHtml.join("")}</div>`;
}

// ================= 内容尺度状态栏（暂时隐藏，置为 true 即可重新开启） =================
window.CONTENT_SCALE_FEATURE_ENABLED = false;
window.EROTIC_SCALE_TIERS = ["纯爱", "悸动", "擦边", "露骨", "色情", "极致"];
window.VIOLENCE_SCALE_TIERS = ["全龄", "擦伤", "见血", "残酷", "血腥", "极致"];

window.EROTIC_SCALE_DESCS = {
  0: "全年龄纯爱向，严禁任何性暗示或擦边描写，情感表达止步于纯洁牵手与眼神交流。",
  1: "青涩暧昧与心动拉扯，可包含耳语、拥抱、脸红心跳等轻度肢体接触，点到为止。",
  2: "性感暗示与暧昧撩拨（如衣衫半解、深吻、身材曲线与体温感官描写），关键处拉灯留白。",
  3: "直白成人亲密描写，不避讳身体接触、喘息与情欲张力，展现细腻完整的欢爱过程。",
  4: "高浓度成人肉欲特写（R-18），直白刻画性器官交合、体液交融与强烈生理快感反应。",
  5: "完全解禁的极致情色描写（R-18+），全面放开感官过载、深度支配臣服、失神绝顶等重度色情细节。"
};

window.VIOLENCE_SCALE_DESCS = {
  0: "全年龄和平向，严禁流血与残酷伤亡，冲突均以切磋、制服或点到为止化解。",
  1: "轻度少年漫战斗尺度，仅有淤青、擦伤、气喘与痛感，无重伤致残。",
  2: "写实战斗尺度，包含刀剑入肉、流血负伤、骨折与剧痛描写，但不过度渲染血腥惨状。",
  3: "黑暗成人尺度，包含致命重创、内脏震裂、严酷折磨与冷酷处决描写。",
  4: "硬核解剖级血腥尺度（R-18G），直白刻画断肢、贯穿、骨骼碎裂与大量失血痉挛细节。",
  5: "完全解禁的极致血腥暴力（R-18G+），全面放开脏器外露、残忍凌虐、生理崩溃与绝望宿命感官冲击。"
};

window.getEffectiveContentScaleLevels = function (proj) {
  const activeProj = proj || ((typeof projectsMap === "object" && projectsMap && currentProjectId) ? projectsMap[currentProjectId] : null);
  const gs = window.globalUserSettings || {};
  const live = window._liveScaleLevels || {};
  let storedE = null;
  let storedV = null;
  let storedEOn = null;
  let storedVOn = null;
  try {
    const se = localStorage.getItem("trpg_scale_erotic");
    const sv = localStorage.getItem("trpg_scale_violence");
    const seo = localStorage.getItem("trpg_scale_erotic_on");
    const svo = localStorage.getItem("trpg_scale_violence_on");
    if (se !== null && se !== "") storedE = Number(se);
    if (sv !== null && sv !== "") storedV = Number(sv);
    if (seo !== null && seo !== "") storedEOn = seo === "true";
    if (svo !== null && svo !== "") storedVOn = svo === "true";
  } catch (_) {}
  let eLvl = Number(live.erotic ?? activeProj?.erotic_level ?? storedE ?? gs.erotic_level ?? 3);
  let vLvl = Number(live.violence ?? activeProj?.violence_level ?? storedV ?? gs.violence_level ?? 3);
  if (isNaN(eLvl)) eLvl = 3;
  if (isNaN(vLvl)) vLvl = 3;
  eLvl = Math.max(0, Math.min(5, Math.round(eLvl)));
  vLvl = Math.max(0, Math.min(5, Math.round(vLvl)));
  const eOn = Boolean(live.eroticEnabled ?? activeProj?.erotic_enabled ?? storedEOn ?? gs.erotic_enabled ?? false);
  const vOn = Boolean(live.violenceEnabled ?? activeProj?.violence_enabled ?? storedVOn ?? gs.violence_enabled ?? false);
  return { erotic: eLvl, violence: vLvl, eroticLevel: eLvl, violenceLevel: vLvl, eroticEnabled: eOn, violenceEnabled: vOn };
};

window.buildContentScalePromptDirective = function (eLvl, vLvl, eOn = false, vOn = false) {
  if (!window.CONTENT_SCALE_FEATURE_ENABLED) return "";
  if (!eOn && !vOn) return "";
  const e = Math.max(0, Math.min(5, isNaN(Number(eLvl)) ? 3 : Number(eLvl)));
  const v = Math.max(0, Math.min(5, isNaN(Number(vLvl)) ? 3 : Number(vLvl)));
  const eName = window.EROTIC_SCALE_TIERS[e] || "露骨";
  const vName = window.VIOLENCE_SCALE_TIERS[v] || "残酷";
  const eDesc = window.EROTIC_SCALE_DESCS[e] || window.EROTIC_SCALE_DESCS[3];
  const vDesc = window.VIOLENCE_SCALE_DESCS[v] || window.VIOLENCE_SCALE_DESCS[3];
  const lines = ["【当前内容尺度控制（玩家可随时拖动状态栏滑块切换，请严格按此最新档位控制本轮及后续剧情的描写程度）】："];
  if (eOn) lines.push(`- 色情尺度：[${e}档 · ${eName}] —— ${eDesc}`);
  if (vOn) lines.push(`- 暴力尺度：[${v}档 · ${vName}] —— ${vDesc}`);
  return lines.join("\n");
};

window.renderContentScaleSlidersInnerHtml = function (proj) {
  const { erotic: eLvl, violence: vLvl, eroticEnabled: eOn, violenceEnabled: vOn } = window.getEffectiveContentScaleLevels(proj);
  const eName = window.EROTIC_SCALE_TIERS[eLvl] || "露骨";
  const vName = window.VIOLENCE_SCALE_TIERS[vLvl] || "残酷";

  const eTicks = window.EROTIC_SCALE_TIERS.map((lbl, idx) => `
    <button type="button" class="scale-tick-btn is-erotic ${eOn && idx === eLvl ? "is-active" : ""}" data-scale-tick="erotic_${idx}" onclick="window.handleContentScaleInput('erotic', ${idx}, true, event)">${idx} ${lbl}</button>
  `).join("");

  const vTicks = window.VIOLENCE_SCALE_TIERS.map((lbl, idx) => `
    <button type="button" class="scale-tick-btn is-violence ${vOn && idx === vLvl ? "is-active" : ""}" data-scale-tick="violence_${idx}" onclick="window.handleContentScaleInput('violence', ${idx}, true, event)">${idx} ${lbl}</button>
  `).join("");

  return `
    <div class="content-scale-grid" onclick="event.stopPropagation()">
      <div class="content-scale-card is-erotic ${eOn ? "" : "is-disabled"}" data-scale-card="erotic">
        <div class="content-scale-top">
          <div style="display:flex;align-items:center;gap:6px;">
            <span class="content-scale-label">💗 色情</span>
            <button type="button" class="scale-toggle-btn is-erotic ${eOn ? "is-on" : ""}" data-scale-toggle="erotic" onclick="window.toggleContentScaleEnabled('erotic', event)">${eOn ? "开启 (点此关闭)" : "已关闭 (点此开启)"}</button>
          </div>
          <span class="scale-tier-badge is-erotic ${eOn ? "" : "is-off"}" data-scale-badge="erotic">${eOn ? `${eLvl} · ${eName}` : "已关闭"}</span>
        </div>
        <input type="range" class="content-scale-slider is-erotic" data-scale-slider="erotic" min="0" max="5" step="1" value="${eLvl}" oninput="window.handleContentScaleInput('erotic', this.value, false, event)" onchange="window.handleContentScaleInput('erotic', this.value, true, event)" />
        <div class="scale-ticks-row">${eTicks}</div>
      </div>
      <div class="content-scale-card is-violence ${vOn ? "" : "is-disabled"}" data-scale-card="violence">
        <div class="content-scale-top">
          <div style="display:flex;align-items:center;gap:6px;">
            <span class="content-scale-label">🩸 暴力</span>
            <button type="button" class="scale-toggle-btn is-violence ${vOn ? "is-on" : ""}" data-scale-toggle="violence" onclick="window.toggleContentScaleEnabled('violence', event)">${vOn ? "开启 (点此关闭)" : "已关闭 (点此开启)"}</button>
          </div>
          <span class="scale-tier-badge is-violence ${vOn ? "" : "is-off"}" data-scale-badge="violence">${vOn ? `${vLvl} · ${vName}` : "已关闭"}</span>
        </div>
        <input type="range" class="content-scale-slider is-violence" data-scale-slider="violence" min="0" max="5" step="1" value="${vLvl}" oninput="window.handleContentScaleInput('violence', this.value, false, event)" onchange="window.handleContentScaleInput('violence', this.value, true, event)" />
        <div class="scale-ticks-row">${vTicks}</div>
      </div>
    </div>
  `;
};

window.renderContentScaleStatusBlockHtml = function (proj) {
  return `
    <div class="bg3-module-block bg3-scale-module-block" data-mod-id="mod_scale" data-mod-key="内容尺度">
      <div class="bg3-module-title"><span>内容尺度</span></div>
      ${window.renderContentScaleSlidersInnerHtml(proj)}
    </div>
  `;
};

window.syncContentScaleDomAndSave = async function (commitSave = true, toastMsg = "") {
  const activeProj = (typeof projectsMap === "object" && projectsMap && currentProjectId) ? projectsMap[currentProjectId] : null;
  const { erotic: eLvl, violence: vLvl, eroticEnabled: eOn, violenceEnabled: vOn } = window.getEffectiveContentScaleLevels(activeProj);

  const updateKindDom = (kind, lvl, isOn) => {
    const tierArr = kind === "erotic" ? window.EROTIC_SCALE_TIERS : window.VIOLENCE_SCALE_TIERS;
    const tierName = tierArr[lvl] || "";
    document.querySelectorAll(`[data-scale-card="${kind}"]`).forEach((el) => {
      el.classList.toggle("is-disabled", !isOn);
    });
    document.querySelectorAll(`[data-scale-toggle="${kind}"]`).forEach((el) => {
      el.classList.toggle("is-on", isOn);
      el.textContent = isOn ? "开启 (点此关闭)" : "已关闭 (点此开启)";
    });
    document.querySelectorAll(`[data-scale-slider="${kind}"]`).forEach((el) => {
      if (String(el.value) !== String(lvl)) el.value = lvl;
    });
    document.querySelectorAll(`[data-scale-badge="${kind}"]`).forEach((el) => {
      el.classList.toggle("is-off", !isOn);
      el.textContent = isOn ? `${lvl} · ${tierName}` : "已关闭";
    });
    for (let i = 0; i <= 5; i++) {
      document.querySelectorAll(`[data-scale-tick="${kind}_${i}"]`).forEach((el) => {
        el.classList.toggle("is-active", isOn && i === lvl);
      });
    }
  };

  updateKindDom("erotic", eLvl, eOn);
  updateKindDom("violence", vLvl, vOn);

  const scaleDirective = window.buildContentScalePromptDirective(eLvl, vLvl, eOn, vOn);
  if (activeProj) {
    const cleanBaseSuffix = String(activeProj.suffix || "")
      .replace(/\n*【当前内容尺度控制[\s\S]*$/, "")
      .trim();
    activeProj.suffix = cleanBaseSuffix ? (scaleDirective ? `${cleanBaseSuffix}\n${scaleDirective}` : cleanBaseSuffix) : scaleDirective;
  }

  if (!commitSave) return;

  const saveTask = (async () => {
    try {
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ erotic_level: eLvl, violence_level: vLvl, erotic_enabled: eOn, violence_enabled: vOn })
      });
      if (activeProj && activeProj.id) {
        await fetch("/api/projects", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(activeProj)
        });
      }
    } catch (e) {}
  })();
  window._pendingContentScaleSavePromise = saveTask;
  await saveTask;

  if (toastMsg) showToast(toastMsg);
};

window.toggleContentScaleEnabled = async function (kind, event = null) {
  if (event) event.stopPropagation();
  const activeProj = (typeof projectsMap === "object" && projectsMap && currentProjectId) ? projectsMap[currentProjectId] : null;
  if (!window.globalUserSettings) window.globalUserSettings = {};
  const initLvls = window.getEffectiveContentScaleLevels(activeProj);
  if (!window._liveScaleLevels) {
    window._liveScaleLevels = {
      erotic: initLvls.erotic,
      violence: initLvls.violence,
      eroticEnabled: initLvls.eroticEnabled,
      violenceEnabled: initLvls.violenceEnabled
    };
  }

  if (kind === "erotic") {
    const nextOn = !initLvls.eroticEnabled;
    window._liveScaleLevels.eroticEnabled = nextOn;
    if (activeProj) activeProj.erotic_enabled = nextOn;
    window.globalUserSettings.erotic_enabled = nextOn;
    try { localStorage.setItem("trpg_scale_erotic_on", String(nextOn)); } catch (_) {}
    const tName = window.EROTIC_SCALE_TIERS[initLvls.erotic] || "露骨";
    await window.syncContentScaleDomAndSave(true, nextOn ? `💗 色情尺度已开启：${initLvls.erotic}档 · ${tName}` : "💗 色情尺度已关闭");
  } else {
    const nextOn = !initLvls.violenceEnabled;
    window._liveScaleLevels.violenceEnabled = nextOn;
    if (activeProj) activeProj.violence_enabled = nextOn;
    window.globalUserSettings.violence_enabled = nextOn;
    try { localStorage.setItem("trpg_scale_violence_on", String(nextOn)); } catch (_) {}
    const tName = window.VIOLENCE_SCALE_TIERS[initLvls.violence] || "残酷";
    await window.syncContentScaleDomAndSave(true, nextOn ? `🩸 暴力尺度已开启：${initLvls.violence}档 · ${tName}` : "🩸 暴力尺度已关闭");
  }
};

window.handleContentScaleInput = async function (kind, rawVal, commitSave = false, event = null) {
  if (event) event.stopPropagation();
  const numVal = Number(rawVal);
  const lvl = Math.max(0, Math.min(5, Math.round(isNaN(numVal) ? 3 : numVal)));
  const activeProj = (typeof projectsMap === "object" && projectsMap && currentProjectId) ? projectsMap[currentProjectId] : null;
  if (!window.globalUserSettings) window.globalUserSettings = {};
  const initLvls = window.getEffectiveContentScaleLevels(activeProj);
  if (!window._liveScaleLevels) {
    window._liveScaleLevels = {
      erotic: initLvls.erotic,
      violence: initLvls.violence,
      eroticEnabled: initLvls.eroticEnabled,
      violenceEnabled: initLvls.violenceEnabled
    };
  }

  // 玩家主动拖动滑块或点击档位时，自动将该项设为开启
  if (kind === "erotic") {
    window._liveScaleLevels.erotic = lvl;
    window._liveScaleLevels.eroticEnabled = true;
    if (activeProj) {
      activeProj.erotic_level = lvl;
      activeProj.erotic_enabled = true;
    }
    window.globalUserSettings.erotic_level = lvl;
    window.globalUserSettings.erotic_enabled = true;
    try {
      localStorage.setItem("trpg_scale_erotic", String(lvl));
      localStorage.setItem("trpg_scale_erotic_on", "true");
    } catch (_) {}
  } else {
    window._liveScaleLevels.violence = lvl;
    window._liveScaleLevels.violenceEnabled = true;
    if (activeProj) {
      activeProj.violence_level = lvl;
      activeProj.violence_enabled = true;
    }
    window.globalUserSettings.violence_level = lvl;
    window.globalUserSettings.violence_enabled = true;
    try {
      localStorage.setItem("trpg_scale_violence", String(lvl));
      localStorage.setItem("trpg_scale_violence_on", "true");
    } catch (_) {}
  }

  const tierArr = kind === "erotic" ? window.EROTIC_SCALE_TIERS : window.VIOLENCE_SCALE_TIERS;
  const tierName = tierArr[lvl] || "";
  await window.syncContentScaleDomAndSave(
    commitSave,
    commitSave ? `${kind === "erotic" ? "💗 色情" : "🩸 暴力"}尺度：${lvl}档 · ${tierName}` : ""
  );
};

window.handleInventoryItemClick = function (itemName, event, itemDesc = "") {
  if (event) event.stopPropagation();
  if (!itemName) return;
  window._lastItemPopoverAnchorEl = event?.currentTarget || null;
  let pop = document.getElementById("bg3ItemActionPopover");
  if (!pop) {
    pop = document.createElement("div");
    pop.id = "bg3ItemActionPopover";
    pop.className = "bg3-item-popover";
    document.body.appendChild(pop);
    document.addEventListener("click", () => {
      if (pop) pop.style.display = "none";
    });
  }
  const fullItemLabel = itemDesc ? `${itemName}(${itemDesc})` : itemName;
  const itemIcon = typeof window.inferTrpgItemIcon === "function" ? window.inferTrpgItemIcon(itemName, itemDesc) : "";
  pop.innerHTML = `
    <div style="font-size:12px;font-weight:700;color:var(--text-main);padding:4px 8px;border-bottom:1px solid var(--border-subtle);">
      <div>${itemIcon} ${escapeHtml(itemName)}</div>
      ${itemDesc ? `<div style="font-size:10.5px;font-weight:500;color:var(--primary);margin-top:2px;">${escapeHtml(itemDesc)}</div>` : ""}
    </div>
    <button type="button" class="bg3-item-pop-btn" onclick="window.fillItemActionToInlineInput('仔细检查【${escapeJsAttr(fullItemLabel)}】的细节与线索：', '${escapeJsAttr(itemName)}', '${escapeJsAttr(itemDesc)}')">检查</button>
    <button type="button" class="bg3-item-pop-btn" onclick="window.fillItemActionToInlineInput('拿出并使用【${escapeJsAttr(fullItemLabel)}】：', '${escapeJsAttr(itemName)}', '${escapeJsAttr(itemDesc)}')">使用</button>
    <button type="button" class="bg3-item-pop-btn" onclick="window.fillItemActionToInlineInput('出示【${escapeJsAttr(fullItemLabel)}】并询问或试探对方反应：', '${escapeJsAttr(itemName)}', '${escapeJsAttr(itemDesc)}')">出示</button>
    <button type="button" class="bg3-item-pop-btn is-danger" onclick="window.fillItemActionToInlineInput('丢弃或销毁【${escapeJsAttr(itemName)}】：', '${escapeJsAttr(itemName)}', '${escapeJsAttr(itemDesc)}')">丢弃</button>
  `;
  pop.style.display = "flex";
  const rect = event?.currentTarget?.getBoundingClientRect?.();
  if (rect) {
    pop.style.left = `${Math.min(window.innerWidth - 190, Math.max(12, rect.left))}px`;
    pop.style.top = `${Math.max(12, rect.top - (itemDesc ? 162 : 142))}px`;
  }
};

window.fillItemActionToInlineInput = function (actionText, itemName = "", itemDesc = "") {
  const pop = document.getElementById("bg3ItemActionPopover");
  if (pop) pop.style.display = "none";
  if (!actionText) return;

  const anchorEl = window._lastItemPopoverAnchorEl;
  const msgEl = anchorEl?.closest?.(".message-item, .bubble");
  let box = msgEl?.querySelector?.(".inline-custom-action-box");
  if (!box) {
    const allBoxes = document.querySelectorAll("#messageContainer .inline-custom-action-box");
    if (allBoxes.length > 0) box = allBoxes[allBoxes.length - 1];
  }

  if (box) {
    box.style.display = "flex";
    const inp = box.querySelector(".inline-action-input");
    if (inp) {
      inp.value = actionText;
      inp.dataset.selectedItemName = itemName || "";
      inp.dataset.selectedItemDesc = itemDesc || "";
      if (itemName) {
        inp.placeholder = "补充行动…";
      }
      inp.parentElement?.classList?.add("has-value");
      try {
        box.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } catch (e) {}
      setTimeout(() => {
        inp.focus();
        try {
          inp.setSelectionRange(inp.value.length, inp.value.length);
        } catch (e) {}
      }, 30);
      return;
    }
  }

  // 若当前气泡没有内联自由输入栏，则自动填入底部主输入框（不自动发送）
  window.pickRecommendedAction(actionText, false);
};

const _SAFE_RICH_TAGS = new Set([
  "p", "br", "hr", "div", "span", "strong", "b", "em", "i", "u", "s", "del", "ins", "mark",
  "code", "pre", "blockquote", "ul", "ol", "li", "dl", "dt", "dd",
  "h1", "h2", "h3", "h4", "h5", "h6",
  "table", "thead", "tbody", "tfoot", "tr", "th", "td",
  "details", "summary", "sup", "sub", "ruby", "rt", "rp",
  "abbr", "kbd", "samp", "var", "small", "q", "cite", "dfn", "time", "figure", "figcaption",
  "img", "a"
]);
const _DROP_SUBTREE_TAGS = new Set([
  "script", "style", "iframe", "object", "embed", "applet", "svg", "math",
  "form", "input", "textarea", "select", "option", "button",
  "base", "link", "meta", "head", "title", "template", "noscript"
]);
const _SAFE_RICH_ATTRS = new Set([
  "class", "id", "title", "open", "start", "reversed", "colspan", "rowspan",
  "align", "dir", "lang", "role", "href", "target", "rel",
  "src", "alt", "width", "height", "loading", "decoding", "style"
]);

function _isSafeRichUrl(rawUrl, isImage) {
  const u = String(rawUrl || "").replace(/[\u0000-\u0020]+/g, "").trim();
  if (!u) return false;
  const low = u.toLowerCase();
  if (low.startsWith("javascript:") || low.startsWith("vbscript:")) return false;
  if (low.startsWith("data:")) {
    return Boolean(isImage && /^data:image\/(?:png|jpe?g|gif|webp|bmp);base64,[a-z0-9+/=\s]+$/i.test(u));
  }
  if (low.startsWith("http://") || low.startsWith("https://") || low.startsWith("/") || low.startsWith("./") || low.startsWith("#")) {
    return true;
  }
  return !isImage && low.startsWith("mailto:");
}

function sanitizeRichHtml(rawHtml) {
  if (!rawHtml || typeof rawHtml !== "string") return "";
  if (typeof DOMParser === "undefined") {
    return rawHtml
      .replace(/<(script|style|iframe|object|embed|svg|math|form|base|link|meta)\b[\s\S]*?<\/\1>/gi, "")
      .replace(/<(script|style|iframe|object|embed|svg|math|form|input|button|base|link|meta)\b[^>]*\/?>/gi, "")
      .replace(/\s+on[a-z0-9_-]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, "")
      .replace(/\s+(href|src|xlink:href)\s*=\s*(?:"\s*(?:javascript|vbscript|data:text):[^"]*"|'\s*(?:javascript|vbscript|data:text):[^']*')/gi, "");
  }
  const parser = new DOMParser();
  const doc = parser.parseFromString(`<body>${rawHtml}</body>`, "text/html");
  const cleanNode = (root) => {
    const children = Array.from(root.childNodes);
    for (const node of children) {
      if (node.nodeType === 8) {
        node.remove();
        continue;
      }
      if (node.nodeType !== 1) continue;
      const tag = node.tagName.toLowerCase();
      if (_DROP_SUBTREE_TAGS.has(tag)) {
        node.remove();
        continue;
      }
      if (!_SAFE_RICH_TAGS.has(tag)) {
        cleanNode(node);
        while (node.firstChild) {
          root.insertBefore(node.firstChild, node);
        }
        node.remove();
        continue;
      }
      for (const attr of Array.from(node.attributes)) {
        const aName = attr.name.toLowerCase();
        const aVal = attr.value || "";
        if (aName.startsWith("on") || aName === "srcdoc") {
          node.removeAttribute(attr.name);
          continue;
        }
        const isDataOrAria = aName.startsWith("data-") || aName.startsWith("aria-");
        if (!isDataOrAria && !_SAFE_RICH_ATTRS.has(aName)) {
          node.removeAttribute(attr.name);
          continue;
        }
        if (aName === "href" && !_isSafeRichUrl(aVal, false)) {
          node.removeAttribute(attr.name);
        } else if (aName === "src" && !_isSafeRichUrl(aVal, tag === "img")) {
          node.removeAttribute(attr.name);
        } else if (aName === "id" && /^(?:sidebar|chatMainStage|studioWorkbenchPane|settingsModal|userInput|btnSend|btnStop)$/i.test(aVal.trim())) {
          node.removeAttribute(attr.name);
        } else if (aName === "style") {
          if (/expression\s*\(|url\s*\(\s*['"]?\s*(?:javascript|vbscript|data:text)|@import|-moz-binding|behavior\s*:/i.test(aVal)) {
            node.removeAttribute(attr.name);
          }
        }
      }
      if (tag === "a" && node.getAttribute("href")) {
        node.setAttribute("rel", "noopener noreferrer");
        if (!node.getAttribute("target")) node.setAttribute("target", "_blank");
      }
      cleanNode(node);
    }
  };
  cleanNode(doc.body);
  return doc.body.innerHTML;
}
window.sanitizeRichHtml = sanitizeRichHtml;

function applyRenderOnlyRegexScripts(rawText, proj) {
  if (!rawText || !proj || !Array.isArray(proj.regex_replaces) || proj.regex_replaces.length === 0) {
    return rawText;
  }
  let out = rawText;
  for (const r of proj.regex_replaces) {
    if (!r || typeof r !== "object") continue;
    if (r.enabled === false || r.enable === false || r.disabled === true) continue;
    if (!r.is_only_render && !r.markdownOnly) continue;
    const scope = r.scope;
    if (typeof scope === "string") {
      if (!["ai", "assistant", "output", "both", "all"].includes(scope.toLowerCase())) continue;
    } else if (typeof scope === "number") {
      if ((scope & 4) === 0) continue;
    }
    const rawPat = String(r.pattern ?? r.regex ?? r.findRegex ?? "");
    if (!rawPat) continue;
    const repStr = String(r.replacement ?? r.replace ?? r.replaceString ?? "");
    let patBody = rawPat;
    let flags = String(r.flags || "gm");
    const slashMatch = rawPat.match(/^\/(.+)\/([gimsuy]*)$/s);
    if (slashMatch) {
      patBody = slashMatch[1];
      flags = slashMatch[2] || "g";
      if (!flags.includes("g")) flags += "g";
    } else if (!flags.includes("g")) {
      flags += "g";
    }
    try {
      const rx = new RegExp(patBody, flags);
      out = out.replace(rx, repStr);
    } catch (e) {}
  }
  return out;
}

function renderRichContent(content) {
  if (!content) return "";
  let working = String(content);

  const _earlyProj = (typeof projectsMap === "object" && projectsMap && currentProjectId) ? projectsMap[currentProjectId] : null;
  working = applyRenderOnlyRegexScripts(working, _earlyProj);
  const _earlyMods = window.getEffectiveUiModules ? window.getEffectiveUiModules(_earlyProj) : [];
  const _earlyThinkMod = _earlyMods.find((m) => m && m.type === "thinking_fold");
  const _earlyThinkEnabled = Boolean(_earlyThinkMod && _earlyThinkMod.enabled !== false);
  const _hasNarrativeOutsideStatusJs = (txt) => {
    if (!txt) return false;
    const probe = String(txt)
      .replace(/<status(?:\s+[^>]*)?>[\s\S]*?<\/status>/gi, "")
      .replace(/<status(?:\s+[^>]*)?>[\s\S]*$/gi, "")
      .replace(/<\/?(?:story|narrative|text|think|thinking)>/gi, "")
      .replace(/(?:^|\n)\s*(?:你打算怎么做|接下来你打算怎么做|你的选择)[？?：:\s]*[\s\S]*$/i, "")
      .replace(/(?:^|\n)\s*[1-9][\.、．\)]\s*[^\n]+/g, "")
      .trim();
    return probe.length > 0;
  };
  working = working.replace(/<\/?(?:story|narrative|text)\s*>/gi, "");
  if (!_earlyThinkEnabled) {
    if (/<think(?:ing)?>[\s\S]*?<\/think(?:ing)?>/i.test(working)) {
      const cand = working.replace(/<think(?:ing)?>[\s\S]*?<\/think(?:ing)?>/gi, "").trim();
      if (cand && (_hasNarrativeOutsideStatusJs(cand) || !_hasNarrativeOutsideStatusJs(working))) {
        working = cand;
      } else {
        working = working.replace(/<\/?think(?:ing)?>/gi, "").trim();
      }
    }
    if (/<\/think(?:ing)?>/i.test(working)) {
      const cand = working.replace(/^[\s\S]*?<\/think(?:ing)?>/i, "").trim();
      if (cand && _hasNarrativeOutsideStatusJs(cand)) {
        working = cand;
      } else {
        working = working.replace(/<\/?think(?:ing)?>/gi, "").trim();
      }
    }
    if (/<think(?:ing)?>/i.test(working)) {
      const cand = working.replace(/<think(?:ing)?>[\s\S]*$/i, "").trim();
      if (cand && _hasNarrativeOutsideStatusJs(cand)) {
        working = cand;
      } else {
        working = working.replace(/<\/?think(?:ing)?>/gi, "").trim();
      }
    }
    if (!working) return "";
  }

  // 1. 提取 <think>...</think> 或 <thinking>...</thinking> 思考过程（忽略反引号内联代码中的 `<think>`/`</think>`，并合并多个思考块）
  const thinkBlocks = [];
  const realCloseRe = /(?<!`)<\/think(?:ing)?>(?!`)/i;
  const realOpenRe = /(?<!`)<think(?:ing)?>(?!`)/i;
  const closeMatch = realCloseRe.exec(working);
  const openMatch = realOpenRe.exec(working);
  if (closeMatch && (!openMatch || closeMatch.index < openMatch.index)) {
    const afterUnmatched = working.slice(closeMatch.index + closeMatch[0].length).trim();
    if (_hasNarrativeOutsideStatusJs(afterUnmatched)) {
      working = "<think>\n" + working;
    } else {
      working = working.replace(/(?<!`)<\/?think(?:ing)?>(?!`)/gi, "");
    }
  }
  working = working.replace(/(?<!`)<think(?:ing)?>(?!`)([\s\S]*?)(?<!`)<\/think(?:ing)?>(?!`)/gi, (_, inner) => {
    const cleanInner = inner.trim();
    if (thinkBlocks.length > 0) {
      if (cleanInner) {
        thinkBlocks[0].text = thinkBlocks[0].text ? `${thinkBlocks[0].text}\n\n---\n\n${cleanInner}` : cleanInner;
      }
      return "\n\n";
    }
    thinkBlocks.push({ text: cleanInner, streaming: false });
    return `\n\n@@THINK_BLOCK_0@@\n\n`;
  });
  if (realOpenRe.test(working) && !realCloseRe.test(working)) {
    working = working.replace(/(?<!`)<think(?:ing)?>(?!`)([\s\S]*)$/i, (_, inner) => {
      const cleanInner = inner.trim();
      if (thinkBlocks.length > 0) {
        if (cleanInner) {
          thinkBlocks[0].text = thinkBlocks[0].text ? `${thinkBlocks[0].text}\n\n---\n\n${cleanInner}` : cleanInner;
        }
        thinkBlocks[0].streaming = true;
        return "\n\n";
      }
      thinkBlocks.push({ text: cleanInner, streaming: true });
      return `\n\n@@THINK_BLOCK_0@@\n\n`;
    });
  }

  const activeProjForHtml = (typeof projectsMap === "object" && projectsMap && currentProjectId) ? projectsMap[currentProjectId] : null;
  const isHtmlCssEnabled = activeProjForHtml ? (activeProjForHtml.status_panel_enabled !== false) : true;

  // 1.2 剥离模型自造的伪系统标签（如 <system_event>【剧情正文】</system_event>、<system_writing>### 剧情正文</system_writing>）
  // 以及解包模型误用 <details summary="剧情正文"> 或 <details><summary>剧情正文</summary> 包裹的正文，避免与原生「剧情正文」模块顶栏重复出现
  working = working
    .replace(/<system_(?:event|writing|status)>[\s\S]*?<\/system_(?:event|writing|status)>/gi, "\n\n")
    .replace(/<details[^>]*\bsummary=["'][^"']*?(?:剧情正文|正文|叙事)[^"']*?["'][^>]*>([\s\S]*?)<\/details>/gi, "\n\n$1\n\n")
    .replace(/<details[^>]*\bsummary=["'][^"']*?(?:剧情正文|正文|叙事)[^"']*?["'][^>]*>([\s\S]*)$/gi, "\n\n$1\n\n")
    .replace(/<details[^>]*>[ \t\r\n]*<summary[^>]*>[^<\n]*?(?:剧情正文|正文栏|正文模块|游戏正文)[^<\n]*?<\/summary>([\s\S]*?)<\/details>/gi, "\n\n$1\n\n")
    .replace(/<details[^>]*>[ \t\r\n]*<summary[^>]*>[^<\n]*?(?:剧情正文|正文栏|正文模块|游戏正文)[^<\n]*?<\/summary>([\s\S]*)$/gi, "\n\n$1\n\n");

  // 1.5 提取 <status>...</status> 零代码轻量状态块（同时自动剥离模型误写进 <status> 内部的 [剧情正文] 块，彻底杜绝状态栏与剧情正文同时出现两个剧情正文栏）
  const statusBlocks = [];
  const hoistedStoryChunks = [];
  const cleanMisplacedStoryInStatus = (stRaw) => {
    const cleaned = String(stRaw || "").replace(
      /(?:^|\n)[ \t]*(?:\*\*|\*)?[ \t]*[\[【][ \t]*(?:#\d+[ \t]*)?(?:[📖📝][ \t]*)?(?:剧情正文|正文)(?:栏|模块)?[ \t]*[\]】][ \t]*(?:\*\*|\*)?[ \t]*[:：]?[ \t]*([\s\S]*?)(?=\n[ \t]*(?:\*\*|\*)?[ \t]*[\[【][^\]】\n]+[\]】]|$)/gi,
      (_, body) => {
        const b = String(body || "").trim();
        if (b && b.length > 25 && !/第二人称.*电影感沉浸叙事|严禁代玩家做决定/.test(b)) {
          hoistedStoryChunks.push(b);
        }
        return "\n";
      }
    );
    return cleaned.trim();
  };

  // 兼容模型用 ```xml ... ``` 代码块包裹 <status>、或使用全角/变体标签的情况
  working = working
    .replace(/＜(\/?status)＞/gi, "<$1>")
    .replace(/<(?:status_panel|status_bar|状态栏|状态面板)(?:\s+[^>]*)?>/gi, "<status>")
    .replace(/<\/(?:status_panel|status_bar|状态栏|状态面板)>/gi, "</status>")
    .replace(/\[status\]([\s\S]*?)\[\/status\]/gi, "<status>$1</status>")
    .replace(/```(?:xml|html|text|markdown|status)?[ \t]*\r?\n?([ \t]*<status>[\s\S]*?<\/status>[ \t]*)\r?\n?```/gi, "$1");

  working = working.replace(/<status>([\s\S]*?)<\/status>/gi, (_, inner) => {
    const cleanedInner = cleanMisplacedStoryInStatus(inner);
    if (!cleanedInner) return "\n";
    if (statusBlocks.length === 0) {
      statusBlocks.push(cleanedInner);
      return `\n\n@@STATUS_BLOCK_0@@\n\n`;
    }
    statusBlocks[0] = `${statusBlocks[0]}\n${cleanedInner}`;
    return "\n";
  });
  if (/<status>/i.test(working) && !/<\/status>/i.test(working)) {
    working = working.replace(/<status>([\s\S]*)$/i, (_, inner) => {
      const cleanedInner = cleanMisplacedStoryInStatus(inner);
      if (!cleanedInner) return "\n";
      if (statusBlocks.length === 0) {
        statusBlocks.push(cleanedInner);
        return `\n\n@@STATUS_BLOCK_0@@\n\n`;
      }
      statusBlocks[0] = `${statusBlocks[0]}\n${cleanedInner}`;
      return "\n";
    });
  }
  // 若模型在 <status> 之前与之后各写了一遍 1.~4. 选项列表，自动剥离 <status> 上方重复的选项列表
  if (statusBlocks.length > 0 && working.includes("@@STATUS_BLOCK_0@@")) {
    const stSplit = working.split("@@STATUS_BLOCK_0@@");
    const beforeSt = stSplit[0] || "";
    const afterSt = stSplit.slice(1).join("@@STATUS_BLOCK_0@@");
    if (/(?:^|\n)\s*1[\.、．\)]\s*\S/.test(afterSt) && /(?:^|\n)\s*2[\.、．\)]\s*\S/.test(afterSt)) {
      const bLines = beforeSt.split(/\r?\n/);
      while (bLines.length > 0 && !bLines[bLines.length - 1].trim()) {
        bLines.pop();
      }
      let tailOptIdx = bLines.length;
      while (tailOptIdx > 0 && /^\s*(?:\*\*|\*)?(?:[1-9]|[①-⑨]|[A-G])[\.、．\)]\s*\S/i.test(bLines[tailOptIdx - 1].trim())) {
        tailOptIdx--;
      }
      if (bLines.length - tailOptIdx >= 2) {
        bLines.splice(tailOptIdx);
        while (bLines.length > 0 && !bLines[bLines.length - 1].trim()) {
          bLines.pop();
        }
        if (
          bLines.length > 0 &&
          /^(?:#{1,6}\s*|\*\*|\*)?\s*(?:[\[【]\s*(?:#\d+\s*)?)?(?:[🎯🎬💡⚡🧭]\s*)?(?:你打算怎么做|接下来你[^\n]{0,18}|你的选择|你的抉择|行动选项|行动推荐|可选行动|你决定怎么做|你要怎么做)[？?：:\s]*(?:\*\*|\*)?$/i.test(
            bLines[bLines.length - 1].trim()
          )
        ) {
          bLines.pop();
        }
        working = `${bLines.join("\n")}\n\n@@STATUS_BLOCK_0@@\n\n${afterSt.trim()}`;
      }
    }
  }
  if (statusBlocks.length === 0 && isHtmlCssEnabled) {
    // 兼容模型漏写 <status> 标签、直接按提示词输出多行【#2 主角状态】…【#6 NPC】或 [主角状态]…[角色关系] 的情况
    const customStatKeys = (_earlyMods || [])
      .filter((m) => m && m.enabled !== false && !["thinking_fold", "story_narrative", "action_choices", "content_scale"].includes(m.type))
      .map((m) => String(m.key || m.name || "").trim())
      .filter(Boolean);
    const isBareStatusHeaderTitle = (rawTitle) => {
      const t = String(rawTitle || "")
        .replace(/^\*+|\*+$/g, "")
        .replace(/^#\d+\s*/, "")
        .replace(/^[📊⚔️🎒💕📋🏷️🧩📖🧠🎯📝💭⚡]+\s*/, "")
        .trim();
      if (!t || /^(?:剧情正文|正文|游戏正文|剧情叙事|思考推演|思考过程|思考|行动选项|可选行动|行动推荐|行动选择|你的选择|你的抉择|选项)(?:栏|模块)?$/i.test(t)) {
        return false;
      }
      if (/^(?:主角状态|角色状态|状态栏|状态面板|装备栏|装备|义体|身体栏|身体状态|物品栏|物品|背包|角色关系|好感|人物关系|情报卡|剧情进度|NPC|NPC信息|系统面板)$/i.test(t)) {
        return true;
      }
      return customStatKeys.some((k) => k === t || t.includes(k) || k.includes(t));
    };
    const isBareChoicesHeaderTitle = (rawTitle) => {
      const t = String(rawTitle || "")
        .replace(/^\*+|\*+$/g, "")
        .replace(/^#\d+\s*/, "")
        .replace(/^[📊⚔️🎒💕📋🏷️🧩📖🧠🎯📝💭⚡]+\s*/, "")
        .trim();
      return /^(?:行动选项|可选行动|行动推荐|行动选择|你的选择|你的抉择|选项)(?:栏|模块)?$/i.test(t);
    };

    const wLines = working.split(/\r?\n/);
    const bracketHdrRe = /^[ \t]*(?:#{1,6}[ \t]*|\*\*|\*)?[ \t]*[\[【]([^\]】\n]+)[\]】][ \t]*(?:\*\*|\*)?[ \t]*[:：]?[ \t]*(.*)$/;
    let statusStartLine = -1;
    let statusHeaderCount = 0;
    for (let i = 0; i < wLines.length; i++) {
      const m = wLines[i].match(bracketHdrRe);
      if (m && isBareStatusHeaderTitle(m[1])) {
        if (statusStartLine === -1) statusStartLine = i;
        statusHeaderCount++;
      }
    }

    if (statusStartLine !== -1 && statusHeaderCount >= 1) {
      let statusEndLine = wLines.length;
      for (let i = statusStartLine + 1; i < wLines.length; i++) {
        const lnTrim = wLines[i].trim();
        const m = lnTrim.match(bracketHdrRe);
        if (m && isBareChoicesHeaderTitle(m[1])) {
          statusEndLine = i;
          break;
        }
        if (/^(?:#{1,6}\s*|\*\*|\*)?\s*(?:[🎯🎬💡⚡🧭]\s*)?(?:你打算怎么做|接下来你打算怎么做|你的选择|你的抉择)[？?：:\s]*(?:\*\*|\*)?$/i.test(lnTrim)) {
          statusEndLine = i;
          break;
        }
        if (/^(?:\*\*|\*)?(?:1|①|A)[\.、．\)]\s*\S/i.test(lnTrim)) {
          const restSlice = wLines.slice(i + 1, i + 6).map((x) => x.trim());
          if (restSlice.some((x) => /^(?:\*\*|\*)?(?:2|②|B)[\.、．\)]\s*\S/i.test(x))) {
            statusEndLine = i;
            break;
          }
        }
      }
      const extractedStatusText = wLines.slice(statusStartLine, statusEndLine).join("\n").trim();
      if (extractedStatusText) {
        const beforeLines = wLines.slice(0, statusStartLine);
        const afterLines = wLines.slice(statusEndLine);
        const afterJoined = afterLines.join("\n");
        // 若底部已有【#7 行动选项】列表，自动清理模型在正文末尾（状态栏上方）重复写的一遍 1.~4. 选项列表
        if (/(?:^|\n)\s*1[\.、．\)]\s*\S/.test(afterJoined) && /(?:^|\n)\s*2[\.、．\)]\s*\S/.test(afterJoined)) {
          while (beforeLines.length > 0 && !beforeLines[beforeLines.length - 1].trim()) {
            beforeLines.pop();
          }
          let tailOptIdx = beforeLines.length;
          while (tailOptIdx > 0 && /^\s*[1-9][\.、．\)]\s*\S/.test(beforeLines[tailOptIdx - 1])) {
            tailOptIdx--;
          }
          if (beforeLines.length - tailOptIdx >= 2) {
            beforeLines.splice(tailOptIdx);
          }
        }
        const idx = statusBlocks.length;
        statusBlocks.push(cleanMisplacedStoryInStatus(extractedStatusText));
        working = `${beforeLines.join("\n")}\n\n@@STATUS_BLOCK_${idx}@@\n\n${afterJoined}`;
      }
    }
  }

  // 清理正文中模型自行手写的孤立「剧情正文」「【#1 剧情正文】」「[剧情正文]」「状态面板」冗余标题行
  working = working.replace(
    /^[ \t]*(?:#{1,6}[ \t]*|\*\*)*[ \t]*(?:[①②③④1-9][\.、．\s]*)?(?:[\[【][ \t]*(?:#\d+[ \t]*)?)?(?:[📖📝📊][ \t]*)?(?:剧情正文|正文栏|剧情正文栏|剧情正文模块|状态面板|状态栏模块)(?:[ \t]*[\]】])?[ \t]*(?:\*\*)*[ \t]*[:：]?[ \t]*$/gim,
    ""
  );

  // 若模型误将整段真实剧情正文写进了 <status> 的 [剧情正文] 项且外部无正文，将其自动提回正文区
  if (hoistedStoryChunks.length > 0) {
    const outsidePlain = working
      .replace(/@@THINK_BLOCK_\d+@@/g, "")
      .replace(/@@STATUS_BLOCK_\d+@@/g, "")
      .trim();
    if (outsidePlain.length < 30) {
      working = working.replace("@@STATUS_BLOCK_0@@", `${hoistedStoryChunks.join("\n\n")}\n\n@@STATUS_BLOCK_0@@`);
    }
  }

  if (!isHtmlCssEnabled) {
    working = working.replace(/<style[\s\S]*?<\/style>/gi, (m) => escapeHtml(m));
  }

  working = working
    .replace(/(<\/summary>)[ \t]*\r?\n(?!\r?\n)/gi, "$1\n\n")
    .replace(/([^\r\n])\r?\n([ \t]*<\/details>)/gi, "$1\n\n$2")
    .replace(/~/g, "&#126;");

  let rawHtml = window.marked ? sanitizeRichHtml(marked.parse(working)) : escapeHtml(working);

  const configuredMods = window.getEffectiveUiModules ? window.getEffectiveUiModules(activeProjForHtml) : [];
  const findUimodByType = (t) => configuredMods.find((m) => m.type === t);
  const thinkMod = findUimodByType("thinking_fold");
  const storyMod = findUimodByType("story_narrative");
  const choicesMod = findUimodByType("action_choices");
  const isThinkModEnabled = Boolean(thinkMod && thinkMod.enabled !== false);
  const isChoicesModEnabled = Boolean(choicesMod && choicesMod.enabled !== false);

  // 2. 还原 <think> 折叠卡片（当「思考推演」模块被删除或关闭时，彻底剥离隐藏，绝不弹出思考框）
  thinkBlocks.forEach((tb, idx) => {
    if (!isThinkModEnabled) {
      rawHtml = rawHtml.replace(new RegExp(`<p>\\s*@@THINK_BLOCK_${idx}@@\\s*<\\/p>|@@THINK_BLOCK_${idx}@@`, "g"), "");
      return;
    }
    const modTitle = escapeHtml((thinkMod && thinkMod.key) ? thinkMod.key : "AI 剧情推演与构思过程");
    const titleLabel = tb.streaming ? `${modTitle}…` : `${modTitle}`;
    const openAttr = tb.streaming ? "open" : "";
    const cardHtml = `
      <details class="think-collapse-card trpg-universal-module" data-module="think" ${openAttr}>
        <summary>
          <span>${titleLabel}</span>
          <span class="module-quick-cfg-btn" onclick="event.preventDefault();event.stopPropagation();window.openModuleQuickEditor&&window.openModuleQuickEditor('thinking_fold')" title="模块设置">设置</span>
        </summary>
        <div class="think-collapse-body">${escapeHtml(tb.text || "...")}</div>
      </details>
    `;
    rawHtml = rawHtml.replace(new RegExp(`<p>\\s*@@THINK_BLOCK_${idx}@@\\s*<\\/p>|@@THINK_BLOCK_${idx}@@`, "g"), cardHtml);
  });

  // 2.5 还原 <status> 原生博德之门3风格 HUD 面板
  statusBlocks.forEach((stText, idx) => {
    const hudHtml = isHtmlCssEnabled ? renderNativeStatusModulesCard(stText) : "";
    rawHtml = rawHtml.replace(new RegExp(`<p>\\s*@@STATUS_BLOCK_${idx}@@\\s*<\\/p>|@@STATUS_BLOCK_${idx}@@`, "g"), hudHtml);
  });

  // 3. 高亮跑团检定骰子结果徽章
  rawHtml = rawHtml.replace(/【[^】]*🎲[^】]+】/g, (m) => `<span class="dice-roll-badge">${m}</span>`);

  // 4. 兼容旧版 ```html 代码块：使用 <iframe sandbox="allow-scripts"> 沙箱隔离渲染，彻底杜绝全局 CSS 污染与 XSS
  if (isHtmlCssEnabled) {
    const htmlBlockRegex = /<pre><code class="language-(?:html|css)">([\s\S]*?)<\/code><\/pre>/gi;
    rawHtml = rawHtml.replace(htmlBlockRegex, (match, codeSnippet) => {
      const tempDiv = document.createElement("div");
      tempDiv.innerHTML = codeSnippet;
      const unescapedCode = tempDiv.textContent || tempDiv.innerText || "";
      const cardId = "card_" + Math.random().toString(36).substring(2, 9);
      const iframeSrcDoc = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{margin:0;padding:8px;font-family:system-ui,-apple-system,sans-serif;color:#e2e8f0;background:transparent;overflow-x:hidden;}</style></head><body>${unescapedCode}<script>function _syncH(){parent.postMessage({type:'trpg_iframe_resize',id:'${cardId}',height:document.documentElement.scrollHeight},'*');}window.addEventListener('load',_syncH);new ResizeObserver(_syncH).observe(document.body);<\/script></body></html>`;

      return `
        <div class="html-preview-card" id="${cardId}">
          <div class="html-preview-header">
            <span>状态面板</span>
            <div class="html-toggle-tabs">
              <button class="html-tab-btn active" type="button" onclick="window.toggleHtmlPreviewTab('${cardId}', 'preview')">面板</button>
              <button class="html-tab-btn" type="button" onclick="window.toggleHtmlPreviewTab('${cardId}', 'code')">源码</button>
            </div>
          </div>
          <div class="html-preview-body" id="${cardId}_preview" style="padding:0;">
            <iframe id="${cardId}_iframe" sandbox="allow-scripts" srcdoc="${escapeHtml(iframeSrcDoc)}" style="width:100%;min-height:140px;border:none;display:block;background:transparent;" loading="lazy"></iframe>
          </div>
          <pre class="html-raw-code" id="${cardId}_code" style="display: none;"><code class="language-html">${codeSnippet}</code></pre>
        </div>
      `;
    });
  }

  // 5. 万物皆模块组装：美化 <details> 折叠面板，识别行动选项，脱离嵌套状态卡，并按模块配置顺序组装（确保选项栏恒在最底部）
  try {
    const tempWrap = document.createElement("div");
    tempWrap.innerHTML = rawHtml;

    // 5.0 关键修复：若模型把 <status> 紧跟在列表项后输出，marked 会将 .bg3-status-hud-card 包进 <li>/<ol>/<p> 内部；
    // 先将所有状态面板提升为 tempWrap 顶层直接子节点，防止被选项列表连带吞入
    tempWrap.querySelectorAll(".bg3-status-hud-card, .html-preview-card").forEach((card) => {
      if (card.parentElement && card.parentElement !== tempWrap) {
        tempWrap.appendChild(card);
      }
    });

    tempWrap.querySelectorAll("details:not(.think-collapse-card)").forEach((det) => {
      if (det.closest(".html-preview-card")) return;
      const sumEl = det.querySelector(":scope > summary") || det.querySelector("summary");
      if (sumEl && sumEl.childNodes.length > 0) {
        const firstNode = sumEl.childNodes[0];
        if (firstNode.nodeType === Node.TEXT_NODE) {
          firstNode.nodeValue = firstNode.nodeValue.replace(/^\s*[▲▼◀▶▴▾▸◂▹▿►]+\s*/, "");
        }
      }
      const sumText = (sumEl?.textContent || det.getAttribute("summary") || "").trim();
      // 若模型仍然用 <details> 包裹了「剧情正文」，直接解包展开为正文节点，杜绝双重正文框
      if (/^(?:[📖📝]\s*)?(?:剧情正文|正文栏|剧情正文栏|正文模块|游戏正文)$/i.test(sumText)) {
        if (sumEl) sumEl.remove();
        while (det.firstChild) {
          det.parentNode.insertBefore(det.firstChild, det);
        }
        det.remove();
        return;
      }
      const isActionSection = /行动|选项|推荐|抉择|分支|下场|选择|choice|action|option/i.test(sumText);

      if (isActionSection && isChoicesModEnabled) {
        const liNodes = det.querySelectorAll("li");
        if (liNodes.length > 0) {
          liNodes.forEach((li) => attachChoiceItemBehavior(li, li.textContent));
        } else {
          const sumHtml = sumEl ? sumEl.outerHTML : "";
          const closeSumIdx = det.innerHTML.toLowerCase().indexOf("</summary>");
          const restHtml = closeSumIdx !== -1 ? det.innerHTML.slice(closeSumIdx + 10) : det.innerHTML;
          const lines = restHtml.split(/(?:<br\s*\/?>|<\/p>|<p>|\r?\n)+/);
          const optionLineRegex = /^\s*(?:\d+[\.、．\)]|[A-Za-z][\.、．：:\)]|[①-⑩]|[▶►🎯🔹🔸]|[-*•]|【)/;
          if (lines.some((l) => optionLineRegex.test(l.replace(/<[^>]+>/g, "")))) {
            const box = document.createElement("div");
            box.style.cssText = "padding:8px 12px;display:flex;flex-direction:column;gap:4px;";
            lines.forEach((lineHtml) => {
              const plain = lineHtml.replace(/<[^>]+>/g, "").trim();
              if (!plain) return;
              const row = document.createElement("div");
              row.innerHTML = lineHtml.trim();
              if (optionLineRegex.test(plain)) {
                attachChoiceItemBehavior(row, plain);
              } else {
                row.style.padding = "4px 0";
              }
              box.appendChild(row);
            });
            det.innerHTML = sumHtml;
            det.appendChild(box);
          }
        }
      } else if (det.children.length === 1 && sumEl) {
        const closeSumIdx = det.innerHTML.toLowerCase().indexOf("</summary>");
        if (closeSumIdx !== -1) {
          const restHtml = det.innerHTML.slice(closeSumIdx + 10).trim();
          if (restHtml) {
            det.innerHTML = `${sumEl.outerHTML}<div style="padding:10px 14px;white-space:pre-wrap;font-size:13px;color:var(--text-muted);line-height:1.65;">${restHtml}</div>`;
          }
        }
      }
    });

    if (isChoicesModEnabled) {
      const isInsideInfoDetails = (node) => {
        if (node.closest(".html-preview-card") || node.closest(".bg3-status-hud-card")) return true;
        const parentDet = node.closest("details");
        if (!parentDet) return false;
        if (parentDet.classList.contains("think-collapse-card")) return true;
        const sText = (parentDet.querySelector(":scope > summary")?.textContent || "").trim();
        if (/SYSTEM\s*TERMINAL|游戏推演|正文/i.test(sText)) return false;
        if (/行动|选项|推荐|抉择|分支|下场|选择|choice|action|option/i.test(sText)) return false;
        return true;
      };

      const explicitOptionRegex = /^(?:[▶►🎯🔹🔸📜]\s*)*(?:(?:任务选项|任务|大纲|路线|分支选项|结局分支|行动选项|可选行动|选项|方案|Option|Choice)\s*(?:[A-G]|[1-9]|[一二三四五六七八九十])(?:\s*[：:．.、—\-「【《（(]|$)|[A-G]\s*路线\s*[：:．.、—\-]|【\s*(?:选项|任务|大纲|路线|行动|分支|抉择)\s*(?:[A-G]|[1-9]|[一二三四五六七八九十])[^】]*】|[▶►]\s*\S+)/i;

      tempWrap.querySelectorAll("p, li, h3, h4").forEach((el) => {
        if (el.classList.contains("trpg-action-choice-item") || isInsideInfoDetails(el)) return;
        const txt = (el.textContent || "").trim();
        if (!txt) return;
        if (explicitOptionRegex.test(txt)) {
          attachChoiceItemBehavior(el, txt);
        }
      });

      const choicesCustomKey = (choicesMod && choicesMod.key) ? choicesMod.key.trim() : "";
      const sectionHeaderRegex = /(?:行动推荐|行动选择|可选行动|行动选项|你的选择|你的抉择|请选择|任务选择|结局分支|可采取的?行动|你打算怎么做|你要怎么做|你决定怎么做)/i;
      const isChoiceHeaderText = (txt) => {
        if (!txt || txt.length > 80) return false;
        if (choicesCustomKey && txt.includes(choicesCustomKey)) return true;
        return sectionHeaderRegex.test(txt);
      };
      const itemPrefixRegex = /^(?:\d+[\.、．\)]|[A-G][\.、．：:\)]|[①-⑩]|[▶►🎯🔹🔸]|[-*•]|【)/i;

      tempWrap.querySelectorAll("p, h1, h2, h3, h4, h5, h6").forEach((hdr) => {
        if (isInsideInfoDetails(hdr)) return;
        const hTxt = (hdr.textContent || "").trim();
        if (!isChoiceHeaderText(hTxt)) return;

        let sib = hdr.nextElementSibling;
        while (sib) {
          const tag = sib.tagName.toLowerCase();
          if (tag === "hr") {
            sib = sib.nextElementSibling;
            continue;
          }
          if (tag === "ol" || tag === "ul") {
            sib.querySelectorAll(":scope > li").forEach((li) => attachChoiceItemBehavior(li, li.textContent));
            sib = sib.nextElementSibling;
            continue;
          }
          if (tag === "p") {
            const pTxt = (sib.textContent || "").trim();
            if (itemPrefixRegex.test(pTxt) || explicitOptionRegex.test(pTxt)) {
              attachChoiceItemBehavior(sib, pTxt);
              sib = sib.nextElementSibling;
              continue;
            }
          }
          break;
        }
      });

      // 兜底识别：若模型未写标题但直接输出了带【稳健/博弈/环境/逆反/检定】或 🎲 的有序/无序列表
      tempWrap.querySelectorAll("ol, ul").forEach((listEl) => {
        if (isInsideInfoDetails(listEl)) return;
        const liItems = Array.from(listEl.querySelectorAll(":scope > li"));
        if (liItems.length >= 2 && liItems.some((li) => /^[【\[]|🎲/.test((li.textContent || "").trim()))) {
          liItems.forEach((li) => attachChoiceItemBehavior(li, li.textContent));
        }
      });

      // 模块化封装：将选项标题、行动选项与底部懒人破局条统一封装进独立的「选项模块 (.trpg-choices-module)」
      const allChoiceNodes = tempWrap.querySelectorAll(".trpg-action-choice-item");
      if (allChoiceNodes.length > 0 && !tempWrap.querySelector(".trpg-choices-module")) {
        const choicesModule = document.createElement("div");
        choicesModule.className = "trpg-choices-module trpg-universal-module";
        choicesModule.setAttribute("data-module", "choices");

        const topBlocks = [];
        allChoiceNodes.forEach((node) => {
          const block = node.closest("details:not(.think-collapse-card), ol, ul") || node;
          if (block && !topBlocks.includes(block)) {
            topBlocks.push(block);
          }
        });

        const firstBlock = topBlocks[0];
        let headerEl = null;
        let leadingHr = null;
        if (firstBlock && firstBlock.parentElement === tempWrap) {
          let prev = firstBlock.previousElementSibling;
          if (prev && prev.tagName.toLowerCase() === "hr") {
            leadingHr = prev;
            prev = prev.previousElementSibling;
          }
          if (prev && !isInsideInfoDetails(prev)) {
            const prevTxt = (prev.textContent || "").trim();
            if (isChoiceHeaderText(prevTxt)) {
              headerEl = prev;
              if (!leadingHr && headerEl.previousElementSibling && headerEl.previousElementSibling.tagName.toLowerCase() === "hr") {
                leadingHr = headerEl.previousElementSibling;
              }
            }
          }
        }

        // 清理模型在 <status> 前后可能重复输出的多余孤立“你打算怎么做？”空行
        const standaloneAskRegex = /^(?:[🎯🎬💡⚡🧭]\s*)?(?:你打算怎么做|接下来你打算怎么做|你的选择|你的抉择|行动选项)[？?：:\s]*$/i;
        tempWrap.querySelectorAll(":scope > p, :scope > h3, :scope > h4").forEach((el) => {
          if (el === headerEl || el.classList.contains("trpg-action-choice-item")) return;
          const t = (el.textContent || "").trim();
          if (standaloneAskRegex.test(t) || (choicesCustomKey && t === choicesCustomKey)) {
            if (!headerEl) {
              headerEl = el;
            } else {
              el.remove();
            }
          }
        });

        if (leadingHr) {
          leadingHr.remove();
        }

        const choicesTitle = escapeHtml(choicesCustomKey || "行动选项");
        const modHeadBar = document.createElement("div");
        modHeadBar.className = "trpg-choices-module-header";
        modHeadBar.innerHTML = `
          <span class="trpg-choices-module-title">${choicesTitle}</span>
          <button type="button" class="module-quick-cfg-btn" onclick="window.openModuleQuickEditor&&window.openModuleQuickEditor('action_choices')" title="模块设置">设置</button>
        `;
        choicesModule.appendChild(modHeadBar);

        if (headerEl) {
          headerEl.remove();
        }
        // 对行动选项条目做去重保护：若模型在 <status> 前后输出了两遍 1.~4.，自动剔除重复的选项与空列表容器
        const seenChoiceBodies = new Set();
        topBlocks.forEach((blk) => {
          const items = blk.classList?.contains("trpg-action-choice-item")
            ? [blk]
            : Array.from(blk.querySelectorAll?.(".trpg-action-choice-item") || []);
          items.forEach((itemEl) => {
            const rawTxt = (itemEl.getAttribute("data-raw-choice") || itemEl.textContent || "").trim();
            const normKey = rawTxt
              .replace(/^\s*(?:\d+[\.、．\)]|[A-G][\.、．：:\)]|[①-⑩]|[▶►🎯🔹🔸]|[-*•])\s*/i, "")
              .replace(/\s+/g, "");
            if (normKey && seenChoiceBodies.has(normKey)) {
              itemEl.remove();
            } else if (normKey) {
              seenChoiceBodies.add(normKey);
            }
          });
          if (blk.classList?.contains("trpg-action-choice-item")) {
            if (blk.isConnected || seenChoiceBodies.size > 0) {
              choicesModule.appendChild(blk);
            }
          } else if (blk.querySelectorAll && blk.querySelectorAll(".trpg-action-choice-item").length > 0) {
            choicesModule.appendChild(blk);
          } else if (blk.parentElement) {
            blk.remove();
          }
        });

        const breakerWrap = document.createElement("div");
        breakerWrap.className = "choice-lazy-breaker-wrap";
        breakerWrap.innerHTML = `
          <div class="choice-lazy-breaker-bar">
            <button type="button" class="lazy-breaker-btn" onclick="window.rerollChoicesOnly && window.rerollChoicesOnly(this)">
              <span>换一批</span>
            </button>
            <button type="button" class="lazy-breaker-btn" onclick="window.autoAdvanceStory && window.autoAdvanceStory()">
              <span>顺其自然</span>
            </button>
            <button type="button" class="lazy-breaker-btn highlight" onclick="window.toggleInlineActionInput && window.toggleInlineActionInput(this)">
              <span>自由输入</span>
            </button>
          </div>
          <div class="inline-custom-action-box" style="display: none;">
            <div class="inline-inspiration-pills">
              <button type="button" class="insp-pill" onclick="window.fillInlineInspiration(this, '质问：')">质问</button>
              <button type="button" class="insp-pill" onclick="window.fillInlineInspiration(this, '偷袭：')">偷袭</button>
              <button type="button" class="insp-pill" onclick="window.fillInlineInspiration(this, '搜查：')">搜查</button>
              <button type="button" class="insp-pill" onclick="window.fillInlineInspiration(this, '调情：')">调情</button>
              <button type="button" class="insp-pill insp-pill-item-btn" onclick="window.toggleInlineItemPicker(this, event)">用道具 ▾</button>
            </div>
            <div class="inline-item-picker-tray" style="display: none;"></div>
            <div class="ai-fused-input-group inline-action-input-row" style="width:100%;">
              <input type="text" class="ai-fused-input inline-action-input" placeholder="输入行动…" oninput="this.parentElement.classList.toggle('has-value', !!this.value.trim())" onkeydown="if(event.key==='Enter'){event.preventDefault();window.submitInlineCustomAction(this);}" />
              <button type="button" class="ai-fused-btn inline-action-submit" onclick="window.submitInlineCustomAction(this)">发送</button>
            </div>
          </div>
        `;
        choicesModule.appendChild(breakerWrap);
        tempWrap.appendChild(choicesModule);
      }
    }

    // 5.5 终极万物模块重组：提取思考推演 / 剧情正文 / 每个独立状态栏子模块 / 行动选项，严格按模块工作台顺序逐一精准排序
    const thinkNodes = Array.from(tempWrap.querySelectorAll(":scope > .think-collapse-card"));
    thinkNodes.forEach((n) => {
      n.setAttribute("data-mod-id", thinkMod?.id || "mod_think");
      n.setAttribute("data-mod-key", thinkMod?.key || "思考推演");
      n.remove();
    });

    const hudCards = Array.from(tempWrap.querySelectorAll(":scope > .bg3-status-hud-card"));
    const statusSubBlocks = [];
    const redundantStoryTitleRegex = /^(?:[📖🧠🎯📊📝💭⚡]\s*)?(?:剧情正文|正文|游戏正文|剧情叙事|思考推演|思考过程|思考|行动选项|可选行动|选项)(?:栏|模块)?$/i;
    hudCards.forEach((card) => {
      Array.from(card.querySelectorAll(":scope > .bg3-module-block")).forEach((blk) => {
        const blkKey = (blk.getAttribute("data-mod-key") || "").trim();
        const blkId = (blk.getAttribute("data-mod-id") || "").trim();
        if (blkId === "mod_story" || blkId === "mod_think" || blkId === "mod_choices" || redundantStoryTitleRegex.test(blkKey)) {
          blk.remove();
          return;
        }
        statusSubBlocks.push(blk);
      });
      card.remove();
    });

    const htmlPreviewNodes = Array.from(tempWrap.querySelectorAll(":scope > .html-preview-card"));
    htmlPreviewNodes.forEach((n) => n.remove());

    const choiceNodes = Array.from(tempWrap.querySelectorAll(":scope > .trpg-choices-module"));
    choiceNodes.forEach((n) => {
      n.setAttribute("data-mod-id", choicesMod?.id || "mod_choices");
      n.setAttribute("data-mod-key", choicesMod?.key || "行动选项");
      n.remove();
    });

    // 清理正文中可能残余的孤立「剧情正文」「剧情正文栏」「状态面板」标题节点
    const customStoryKey = (storyMod && storyMod.key) ? String(storyMod.key).trim() : "";
    Array.from(tempWrap.querySelectorAll(":scope > p, :scope > h1, :scope > h2, :scope > h3, :scope > h4, :scope > h5, :scope > h6")).forEach((el) => {
      const txt = (el.textContent || "").replace(/^\*+|\*+$/g, "").trim();
      if (
        /^(?:[①②③④1-9][\.、．\s]*)?(?:[\[【]\s*(?:#\d+\s*)?)?(?:[📖📝📊]\s*)?(?:剧情正文|正文|剧情正文栏|正文栏|剧情正文模块|状态面板|状态栏|状态栏模块)(?:\s*[\]】])?\s*[:：]?$/i.test(txt) ||
        (customStoryKey && (txt === customStoryKey || txt === `${customStoryKey}` || txt === `【${customStoryKey}】` || txt === `[${customStoryKey}]`))
      ) {
        el.remove();
      }
    });

    // 清理残留的孤立分割线
    Array.from(tempWrap.querySelectorAll(":scope > hr")).forEach((hr) => {
      if (!hr.previousElementSibling || !hr.nextElementSibling) hr.remove();
    });

    const remainingStoryChildren = Array.from(tempWrap.childNodes).filter((node) => {
      if (node.nodeType === Node.TEXT_NODE) return !!node.textContent.trim();
      return true;
    });

    const storyNodes = [];
    if (remainingStoryChildren.length > 0) {
      if (storyMod && storyMod.enabled !== false) {
        const storyWrap = document.createElement("div");
        storyWrap.className = "trpg-story-module trpg-universal-module";
        storyWrap.setAttribute("data-module", "story");
        storyWrap.setAttribute("data-mod-id", storyMod?.id || "mod_story");
        storyWrap.setAttribute("data-mod-key", storyMod?.key || "剧情正文");
        const storyTitle = escapeHtml((storyMod && storyMod.key) ? storyMod.key : "剧情正文");
        const storyBar = document.createElement("div");
        storyBar.className = "trpg-story-module-bar";
        storyBar.innerHTML = `
          <span class="trpg-story-module-tag">${storyTitle}</span>
          <button type="button" class="module-quick-cfg-btn" onclick="window.openModuleQuickEditor&&window.openModuleQuickEditor('story_narrative')" title="模块设置">设置</button>
        `;
        storyWrap.appendChild(storyBar);
        remainingStoryChildren.forEach((ch) => storyWrap.appendChild(ch));
        storyNodes.push(storyWrap);
      } else {
        // 用户未添加或关闭了「剧情正文」功能栏，保留普通聊天气泡正文内容（不带「剧情正文」模块顶栏）
        const plainWrap = document.createElement("div");
        remainingStoryChildren.forEach((ch) => plainWrap.appendChild(ch));
        storyNodes.push(plainWrap);
      }
    }
    tempWrap.innerHTML = "";

    const getModConfigOrder = (modId, modKey, modType, fallbackOrder) => {
      if (!Array.isArray(configuredMods) || configuredMods.length === 0) return fallbackOrder;
      if (modId) {
        const idxById = configuredMods.findIndex((m) => m && m.id === modId);
        if (idxById !== -1) return idxById;
      }
      if (modType) {
        const idxByType = configuredMods.findIndex((m) => m && m.type === modType);
        if (idxByType !== -1) return idxByType;
      }
      if (modKey) {
        const cleanK = String(modKey).trim();
        const idxByKey = configuredMods.findIndex((m) => {
          const k = String(m?.key || m?.name || "").trim();
          return k && (k === cleanK || cleanK.includes(k) || k.includes(cleanK));
        });
        if (idxByKey !== -1) return idxByKey;
      }
      return fallbackOrder;
    };

    const sortableItems = [];
    let seqCounter = 0;

    thinkNodes.forEach((node) => {
      sortableItems.push({
        node,
        isStatusBlock: false,
        order: getModConfigOrder(thinkMod?.id, thinkMod?.key, "thinking_fold", 0),
        seq: seqCounter++
      });
    });

    storyNodes.forEach((node) => {
      sortableItems.push({
        node,
        isStatusBlock: false,
        order: getModConfigOrder(storyMod?.id, storyMod?.key, "story_narrative", 1),
        seq: seqCounter++
      });
    });

    statusSubBlocks.forEach((blk, sIdx) => {
      const bId = blk.getAttribute("data-mod-id") || "";
      const bKey = blk.getAttribute("data-mod-key") || "";
      sortableItems.push({
        node: blk,
        isStatusBlock: true,
        order: getModConfigOrder(bId, bKey, "", 100 + sIdx),
        seq: seqCounter++
      });
    });

    htmlPreviewNodes.forEach((node, hIdx) => {
      sortableItems.push({
        node,
        isStatusBlock: false,
        order: 200 + hIdx,
        seq: seqCounter++
      });
    });

    choiceNodes.forEach((node) => {
      sortableItems.push({
        node,
        isStatusBlock: false,
        order: getModConfigOrder(choicesMod?.id, choicesMod?.key, "action_choices", 999),
        seq: seqCounter++
      });
    });

    sortableItems.sort((a, b) => (a.order !== b.order ? a.order - b.order : a.seq - b.seq));

    let currentHudCard = null;
    sortableItems.forEach((item) => {
      if (item.isStatusBlock) {
        if (!currentHudCard) {
          currentHudCard = document.createElement("details");
          currentHudCard.className = "bg3-status-hud-card trpg-universal-module";
          currentHudCard.setAttribute("data-module", "status");
          currentHudCard.setAttribute("open", "");
          const sumEl = document.createElement("summary");
          sumEl.className = "bg3-status-hud-summary";
          const barPreviews = [];
          statusSubBlocks.forEach((sb) => {
            sb.querySelectorAll(".bg3-stat-bar-top").forEach((bt) => {
              const lblNode = bt.querySelector(".stat-label");
              const lbl = (lblNode?.childNodes?.[0]?.textContent || lblNode?.textContent || "").trim();
              const num = (bt.querySelector(".stat-num")?.textContent || "").replace(/\s+/g, "").trim();
              if (lbl && num && barPreviews.length < 3) {
                barPreviews.push(`${lbl} ${num}`);
              }
            });
          });
          const previewText = barPreviews.length > 0
            ? barPreviews.join(" · ")
            : statusSubBlocks.map((sb) => sb.getAttribute("data-mod-key") || "").filter(Boolean).slice(0, 4).join(" · ");
          sumEl.innerHTML = `<span class="hud-summary-title">状态栏</span>${previewText ? `<span class="hud-summary-preview">${escapeHtml(previewText)}</span>` : ""}`;
          currentHudCard.appendChild(sumEl);
          const bodyWrap = document.createElement("div");
          bodyWrap.className = "bg3-status-hud-body";
          currentHudCard.appendChild(bodyWrap);
          tempWrap.appendChild(currentHudCard);
        }
        const bodyContainer = currentHudCard.querySelector(":scope > .bg3-status-hud-body") || currentHudCard;
        bodyContainer.appendChild(item.node);
      } else {
        currentHudCard = null;
        tempWrap.appendChild(item.node);
      }
    });

    rawHtml = tempWrap.innerHTML;
  } catch (e) {}

  return rawHtml;
}

// 监听沙箱 iframe 自适应高度消息
window.addEventListener("message", (ev) => {
  if (ev.data && ev.data.type === "trpg_iframe_resize" && ev.data.id) {
    const ifr = document.getElementById(`${ev.data.id}_iframe`);
    if (ifr && ev.data.height) {
      ifr.style.height = `${Math.min(680, Math.max(90, Number(ev.data.height) + 12))}px`;
    }
  }
});

// ================= 模块四：博德之门3式「关键节点单按钮智能检定」 =================
function attachChoiceItemBehavior(el, rawActionText) {
  if (!el || el.classList.contains("trpg-action-choice-item")) return;
  let cleanText = String(rawActionText || "")
    .replace(/🚀\s*点击发送|🚀\s*发送|🎲\s*点击检定|🎲\s*掷骰发送|🎲\s*掷骰|🎯\s*点击选用|✏️\s*点击输入/g, "")
    .trim();
  if (!cleanText) return;

  const strippedNum = cleanText.replace(/^(?:\d+[\.、．\)]\s*|[▶►🎯🔹🔸📜]\s*)/, "").trim();
  if (strippedNum) cleanText = strippedNum;

  const isCustomPrompt =
    (/^(?:[【\[]\s*)?(?:自定义(?:行动|选项)?|自由(?:行动|发挥|输入))\s*(?:[】\]]\s*)?[：:（(]/.test(cleanText) &&
      /自行输入|直接输入|输入你想要|输入任何|无视以上|回复你的选择|其他指令/.test(cleanText)) ||
    /^[（(【\[]\s*(?:自定义(?:行动|选项)?|自由(?:行动|发挥|输入))\s*[）)】\]]$/.test(cleanText);

  // 智能检测是否为含有 🎲 或【XXX检定/判定/掷骰】或骰子表达式 (如 1d100 / 1d20) 的关键风险选项
  const isCheckOption = /🎲|[【\[（(][^】\]）)]*(?:检定|判定|掷骰|Check|Roll)[^】\]）)]*[】\]）)]|\b\d+d\d+\b/i.test(cleanText);

  let sendText = cleanText;
  if (sendText.length > 140) {
    const headerMatch = sendText.match(/^([^：:。！？\n]{2,60}?)(?:[：:]|——)/);
    if (headerMatch) {
      sendText = `选择：${headerMatch[1].trim()}`;
    } else {
      const firstSent = sendText.split(/[。！？\n]/)[0].trim();
      sendText = firstSent.length >= 4 && firstSent.length <= 120 ? firstSent : sendText.slice(0, 100);
    }
  }

  el.classList.add("trpg-action-choice-item");
  if (isCheckOption) {
    el.classList.add("trpg-choice-check-item");
  }
  el.setAttribute("data-action-text", sendText);
  el.setAttribute("data-is-check", isCheckOption ? "1" : "0");
  el.setAttribute("data-custom-input", isCustomPrompt ? "1" : "0");
  el.setAttribute("role", "button");
  el.setAttribute("tabindex", "0");
  el.setAttribute(
    "title",
    isCustomPrompt
      ? "自由输入"
      : isCheckOption
      ? "检定"
      : "执行"
  );
  el.setAttribute("onclick", "window.handleChoiceItemClick && window.handleChoiceItemClick(this, event)");

  if (!el.querySelector(".trpg-action-choice-hint")) {
    if (isCustomPrompt) {
      const hint = document.createElement("span");
      hint.className = "trpg-action-choice-hint";
      hint.textContent = "自由输入";
      el.appendChild(hint);
    } else if (isCheckOption && !el.querySelector(".dice-roll-badge")) {
      const hint = document.createElement("span");
      hint.className = "trpg-action-choice-hint choice-check-badge";
      hint.textContent = "检定";
      el.appendChild(hint);
    }
  }
}

window.handleChoiceItemClick = function (el, event) {
  if (event) {
    event.stopPropagation();
  }
  if (!el) return;
  const now = Date.now();
  if (window._lastChoiceClickAt && now - window._lastChoiceClickAt < 450) return;
  window._lastChoiceClickAt = now;

  const actionText =
    el.getAttribute("data-action-text") ||
    (el.textContent || "").replace(/🚀\s*点击发送|🚀\s*发送|🚀|🎲\s*检定并发送|🎲\s*检定|🎲\s*点击检定|🎲\s*掷骰发送|🎲\s*掷骰|🎯\s*点击选用|✏️\s*自由输入/g, "").trim();
  const isCustom = el.getAttribute("data-custom-input") === "1";
  const isCheck = el.getAttribute("data-is-check") === "1";

  if (isCustom) {
    const wrap = el.closest(".trpg-choices-module, .bubble, .message-item")?.querySelector(".choice-lazy-breaker-wrap .lazy-breaker-btn.highlight");
    if (wrap) {
      window.toggleInlineActionInput(wrap);
      return;
    }
    if (userInput) {
      userInput.focus();
    }
    return;
  }

  const existingInputDiceMatch = (userInput?.value || "").match(/【[^】]*🎲[^】]*】/);

  if (isCheck) {
    if (existingInputDiceMatch) {
      window.pickRecommendedAction(`${actionText} ${existingInputDiceMatch[0]}`, true);
      return;
    }
    const exprMatch = actionText.match(/\b(\d*d\d+(?:(?:kh|kl)\d+)?(?:[+-]\d+)?)\b/i);
    const diceRes = evaluateDiceExpression(exprMatch ? exprMatch[1] : "1d100");
    showToast(`检定：${diceRes.expr} = ${diceRes.detail}`);
    setTimeout(() => {
      window.pickRecommendedAction(`${actionText} 【🎲 ${diceRes.expr} = ${diceRes.detail}】`, true);
    }, 320);
    return;
  }

  window.pickRecommendedAction(actionText, true);
};

window.handleChoiceRollSendClick = function (btnEl, event) {
  const choiceEl = btnEl?.closest?.(".trpg-action-choice-item");
  if (choiceEl) window.handleChoiceItemClick(choiceEl, event);
};

// ================= 模块六：懒人破局条三大神器（模块化重Roll选项 / 顺其自然 / 原地写动作） =================
window.inferTrpgItemIcon = function (itemName, itemDesc = "") {
  const s = `${itemName || ""} ${itemDesc || ""}`;
  if (/药|膏|绷带|止血|治疗|血瓶|剂|丹|散|针剂|医疗|急救/i.test(s)) return "🧪";
  if (/面包|干粮|肉|水|酒|果|饼|汤|粮|饱腹|饮|茶|奶|糖|巧克/i.test(s)) return "🍞";
  if (/火折|火柴|火把|提灯|蜡烛|打火|照明|点火|电筒|荧光/i.test(s)) return "🔥";
  if (/钥匙|撬锁|铁丝|令牌|徽记|徽章|印章|信物|通行证|门卡|芯片/i.test(s)) return "🔑";
  if (/卷轴|书|信|地图|笔记|羊皮|文献|情报|字条|照片|日记|名册|画/i.test(s)) return "📜";
  if (/剑|刀|匕首|刃|枪|刺|斧|锤/i.test(s)) return "🗡️";
  if (/弓|弩|箭|弹|铳|雷|炸药|燃烧瓶|暗器|飞镖|钉/i.test(s)) return "🎯";
  if (/盾|甲|铠|袍|斗篷|披风|衣|服/i.test(s)) return "🛡️";
  if (/戒|坠|链|环|玉|佩|护符|怀表|饰/i.test(s)) return "💍";
  if (/绳|钩|镐|铲|工具|钳|扳手|罗盘|指南针|望远镜/i.test(s)) return "🧰";
  if (/钱|金币|银币|铜币|灵石|筹码|信用点|宝石|钻/i.test(s)) return "🪙";
  return "";
};

function collectPlayerEquipAndInventory(anchorEl) {
  const equipItems = [];
  const invItems = [];
  const seenKeys = new Set();

  const msgEl = anchorEl?.closest?.(".message-item, .bubble");
  let hudCard = msgEl?.querySelector?.(".bg3-status-hud-card");
  if (!hudCard) {
    const allHuds = document.querySelectorAll("#messageContainer .bg3-status-hud-card");
    if (allHuds.length > 0) hudCard = allHuds[allHuds.length - 1];
  }

  if (hudCard) {
    hudCard.querySelectorAll(".bg3-equip-slot:not(.is-empty)").forEach((slotEl) => {
      const rawLabel = (slotEl.querySelector(".equip-slot-label")?.textContent || "").trim();
      const iconMatch = rawLabel.match(/^(\S+)\s+(.*)$/);
      const icon = iconMatch ? iconMatch[1] : "";
      const slotName = iconMatch ? iconMatch[2].trim() : rawLabel;
      let itemName = (slotEl.querySelector(".equip-item-name")?.textContent || "").trim();
      let itemDesc = (slotEl.querySelector(".equip-item-desc")?.textContent || "").trim().replace(/^\(|\)$/g, "");
      if (!itemName) {
        const valText = (slotEl.querySelector(".equip-slot-val")?.textContent || "").trim();
        const parsed = parseItemWithMicroDesc(valText);
        itemName = parsed.itemName || valText;
        itemDesc = parsed.itemDesc || "";
      }
      if (itemName && !/^(?:无|空|未装备|none|-)$/i.test(itemName)) {
        const key = `equip_${slotName}_${itemName}`;
        if (!seenKeys.has(key)) {
          seenKeys.add(key);
          equipItems.push({ type: "equip", icon, slotName, name: itemName, desc: itemDesc, qty: "" });
        }
      }
    });

    hudCard.querySelectorAll(".bg3-inv-cell").forEach((cellEl) => {
      const itemName = (cellEl.querySelector(".inv-item-name")?.textContent || "").trim();
      const itemDesc = (cellEl.querySelector(".inv-item-desc")?.textContent || "").trim().replace(/^\(|\)$/g, "");
      const itemQty = (cellEl.querySelector(".inv-item-qty")?.textContent || "").trim();
      if (itemName && !/^(?:无|空|暂无|none|-)$/i.test(itemName)) {
        const key = `inv_${itemName}`;
        if (!seenKeys.has(key)) {
          seenKeys.add(key);
          const icon = window.inferTrpgItemIcon(itemName, itemDesc);
          invItems.push({ type: "inv", icon, slotName: "", name: itemName, desc: itemDesc, qty: itemQty });
        }
      }
    });
  }

  return { equipItems, invItems };
}

window.toggleInlineItemPicker = function (pillEl, event) {
  if (event) event.stopPropagation();
  const box = pillEl?.closest?.(".inline-custom-action-box");
  if (!box) return;
  const tray = box.querySelector(".inline-item-picker-tray");
  const inp = box.querySelector(".inline-action-input");
  if (!tray) return;

  const isOpening = tray.style.display === "none";
  box.querySelectorAll(".insp-pill").forEach((b) => b.classList.remove("active"));

  if (!isOpening) {
    tray.style.display = "none";
    pillEl.innerHTML = "用道具 ▾";
    return;
  }

  pillEl.classList.add("active");
  pillEl.innerHTML = "用道具 ▴";

  const { equipItems, invItems } = collectPlayerEquipAndInventory(pillEl);

  if (equipItems.length === 0 && invItems.length === 0) {
    tray.innerHTML = `
      <div class="inline-picker-empty">
        <span>无可选物品</span>
      </div>
    `;
  } else {
    const sections = [];
    if (equipItems.length > 0) {
      const chipsHtml = equipItems.map((it) => {
        const tip = `${it.slotName ? `【${it.slotName}】` : ""}${it.name}${it.desc ? ` (${it.desc})` : ""}`;
        return `
          <button type="button" class="inline-picker-chip is-equip-chip" onclick="window.selectInlinePickerItem(this, '${escapeJsAttr(it.name)}', '${escapeJsAttr(it.desc || "")}', 'equip', '${escapeJsAttr(it.slotName || "")}')" title="${escapeHtml(tip)}">
            <span class="picker-chip-icon">${escapeHtml(it.icon)}</span>
            ${it.slotName ? `<span class="picker-chip-slot">${escapeHtml(it.slotName)}</span>` : ""}
            <span class="picker-chip-name">${escapeHtml(it.name)}</span>
            ${it.desc ? `<span class="picker-chip-desc">(${escapeHtml(it.desc)})</span>` : ""}
          </button>
        `;
      }).join("");
      sections.push(`
        <div class="inline-picker-group">
          <span class="inline-picker-group-label equip-label">装备</span>
          <div class="inline-picker-chips-wrap">${chipsHtml}</div>
        </div>
      `);
    }
    if (invItems.length > 0) {
      const chipsHtml = invItems.map((it) => {
        const tip = `${it.name}${it.desc ? ` (${it.desc})` : ""}${it.qty ? ` ${it.qty}` : ""}`;
        return `
          <button type="button" class="inline-picker-chip is-inv-chip" onclick="window.selectInlinePickerItem(this, '${escapeJsAttr(it.name)}', '${escapeJsAttr(it.desc || "")}', 'inv', '')" title="${escapeHtml(tip)}">
            <span class="picker-chip-icon">${escapeHtml(it.icon)}</span>
            <span class="picker-chip-name">${escapeHtml(it.name)}</span>
            ${it.desc ? `<span class="picker-chip-desc">(${escapeHtml(it.desc)})</span>` : ""}
            ${it.qty ? `<span class="picker-chip-qty">${escapeHtml(it.qty)}</span>` : ""}
          </button>
        `;
      }).join("");
      sections.push(`
        <div class="inline-picker-group">
          <span class="inline-picker-group-label inv-label">物品栏</span>
          <div class="inline-picker-chips-wrap">${chipsHtml}</div>
        </div>
      `);
    }
    tray.innerHTML = sections.join("");
  }

  tray.style.display = "flex";

  if (inp) {
    const cur = inp.value.trim();
    if (!cur || /^(?:质问|偷袭|搜查|调情)[：:]?$/.test(cur)) {
      inp.value = "用道具：";
      inp.parentElement?.classList?.toggle("has-value", true);
    }
    inp.focus();
  }
};

window.selectInlinePickerItem = function (chipEl, itemName, itemDesc = "", itemType = "inv", slotName = "") {
  const box = chipEl?.closest?.(".inline-custom-action-box");
  if (!box || !itemName) return;
  box.querySelectorAll(".inline-picker-chip").forEach((c) => c.classList.remove("is-selected"));
  chipEl.classList.add("is-selected");

  const inp = box.querySelector(".inline-action-input");
  if (!inp) return;

  inp.dataset.selectedItemName = itemName;
  inp.dataset.selectedItemDesc = itemDesc || "";
  inp.dataset.selectedItemType = itemType || "inv";

  const cur = inp.value.trim();
  let userSuffix = "";
  const prefixRe = /^(?:用道具|质问|偷袭|搜查|调情|(?:动用装备|使用道具|使用|拿出)【[^】]+】)\s*[：:]\s*(.*)$/;
  const m = cur.match(prefixRe);
  if (m) {
    userSuffix = m[1].trim();
  } else if (cur && !/^(?:用道具|质问|偷袭|搜查|调情)[：:]?$/.test(cur)) {
    userSuffix = cur;
  }

  const newPrefix = itemType === "equip" ? `动用装备【${itemName}】：` : `使用道具【${itemName}】：`;
  inp.value = userSuffix ? `${newPrefix}${userSuffix}` : newPrefix;
  inp.placeholder = "补充用法…";
  inp.parentElement?.classList?.toggle("has-value", true);
  inp.focus();
  try {
    inp.setSelectionRange(inp.value.length, inp.value.length);
  } catch (e) {}
};

window.autoAdvanceStory = function () {
  window.pickRecommendedAction("（顺其自然：不主动干预，紧接上一轮结尾直接推进下一幕新事件）", true);
};

window.toggleInlineActionInput = function (btnEl) {
  const wrap = btnEl?.closest?.(".choice-lazy-breaker-wrap");
  if (!wrap) return;
  const box = wrap.querySelector(".inline-custom-action-box");
  if (!box) return;
  const isHidden = box.style.display === "none";
  box.style.display = isHidden ? "flex" : "none";
  if (isHidden) {
    const inp = box.querySelector(".inline-action-input");
    if (inp) inp.focus();
  }
};

window.fillInlineInspiration = function (pillEl, prefixText) {
  const box = pillEl?.closest?.(".inline-custom-action-box");
  if (box) {
    box.querySelectorAll(".insp-pill").forEach((b) => b.classList.remove("active"));
    pillEl.classList.add("active");
    const itemBtn = box.querySelector(".insp-pill-item-btn");
    if (itemBtn && itemBtn !== pillEl) itemBtn.innerHTML = "用道具 ▾";
    const tray = box.querySelector(".inline-item-picker-tray");
    if (tray) tray.style.display = "none";
  }
  const inp = box?.querySelector?.(".inline-action-input");
  if (!inp) return;
  const cur = inp.value.trim();
  inp.value = cur ? `${prefixText}${cur.replace(/^(?:(?:动用装备|使用道具|使用|拿出)【[^】]+】|[^：:]+)[：:]\s*/, "")}` : prefixText;
  inp.parentElement?.classList?.toggle("has-value", !!inp.value.trim());
  inp.focus();
};

window.submitInlineCustomAction = function (el) {
  const box = el?.closest?.(".inline-custom-action-box");
  const inp = box?.querySelector?.(".inline-action-input");
  let val = (inp?.value || "").trim();
  if (!val || /^[^：:]+[：:]$/.test(val)) {
    const onlyItemMatch = val.match(/^(动用装备|使用道具|使用|拿出)【([^】]+)】[：:]$/);
    if (onlyItemMatch) {
      const actType = onlyItemMatch[1];
      const itName = onlyItemMatch[2];
      const itDesc = inp?.dataset?.selectedItemName === itName && !itName.includes("(") ? (inp?.dataset?.selectedItemDesc || "") : "";
      const fullLabel = itDesc ? `${itName}(${itDesc})` : itName;
      val = actType === "动用装备" ? `拔出并动用随身装备【${fullLabel}】` : `拿出并使用道具【${fullLabel}】`;
    } else if (/【[^】]+】.*[：:]$/.test(val)) {
      val = val.replace(/[：:]\s*$/, "").trim();
    } else {
      showToast("请选择物品或输入行动");
      if (inp) inp.focus();
      return;
    }
  }
  inp.value = "";
  const tray = box.querySelector(".inline-item-picker-tray");
  if (tray) tray.style.display = "none";
  box.style.display = "none";
  window.pickRecommendedAction(val, true);
};

window.rerollChoicesOnly = async function (btnEl) {
  const isStreamBusy = Boolean(
    typeof activeStreams === "object" && activeStreams && currentChatId && activeStreams[currentChatId]
  );
  if (isStreamBusy) {
    showToast("生成中，请稍候");
    return;
  }
  if (window._isRerollingChoices) {
    showToast("选项生成中");
    return;
  }

  const msgItemEl =
    btnEl?.closest?.(".message-item.assistant") ||
    Array.from(document.querySelectorAll(".message-item.assistant")).pop();
  const bubbleEl = msgItemEl?.querySelector?.(".bubble");
  const targetMsgId = msgItemEl?.dataset?.msgId || "";

  const msgs = Array.isArray(currentChatData?.messages) ? currentChatData.messages : [];
  let targetIdx = -1;
  if (targetMsgId) {
    targetIdx = msgs.findIndex((m) => m.role === "assistant" && String(m.id || "") === String(targetMsgId));
  }
  if (targetIdx === -1) {
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === "assistant") {
        targetIdx = i;
        break;
      }
    }
  }
  if (targetIdx === -1) {
    showToast("无可换选项");
    return;
  }

  const choicesModEl =
    btnEl?.closest?.(".trpg-choices-module") ||
    bubbleEl?.querySelector?.(".trpg-choices-module");
  const backupChoicesHtml = choicesModEl ? choicesModEl.innerHTML : "";
  const backupBtnHtml = !choicesModEl && btnEl ? btnEl.innerHTML : "";

  window._isRerollingChoices = true;

  // 模块化局部更新：保持思考块、正文模块与 <status> 状态栏模块 DOM 完全不动，仅清空并重绘【选项模块】
  if (choicesModEl) {
    choicesModEl.innerHTML = `
      <div class="trpg-choices-rerolling-state" style="margin-top:10px;padding:14px 16px;border-radius:10px;border:1px dashed var(--primary);background:rgba(99,102,241,0.06);display:flex;align-items:center;gap:10px;color:var(--text-main);font-size:13px;">
        <span style="display:inline-block;animation:spin 1s linear infinite;font-size:16px;"></span>
        <span>生成中…</span>
      </div>
    `;
  } else if (btnEl) {
    btnEl.disabled = true;
    btnEl.innerHTML = "<span>生成中…</span>";
  }

  const lockedChatId = currentChatId;
  const lockedProjectId = currentProjectId;
  const lockedMsgRef = msgs[targetIdx];

  try {
    const model = (typeof headerModelSelect !== "undefined" && headerModelSelect?.value) || "";
    const res = await fetch("/api/ai/reroll_choices", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: lockedChatId,
        msg_id: lockedMsgRef.id || targetMsgId,
        project_id: lockedProjectId,
        model,
        current_content: lockedMsgRef.content || ""
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "生成失败");

    if (currentChatId === lockedChatId) {
      if (data.updated_content && lockedMsgRef) {
        lockedMsgRef.content = data.updated_content;
      }

      if (choicesModEl && choicesModEl.isConnected && data.new_choices) {
        const tempDiv = document.createElement("div");
        tempDiv.innerHTML = renderRichContent(data.new_choices);
        const renderedMod = tempDiv.querySelector(".trpg-choices-module");
        choicesModEl.innerHTML = renderedMod ? renderedMod.innerHTML : tempDiv.innerHTML;
      } else if (bubbleEl && bubbleEl.isConnected && data.updated_content) {
        bubbleEl.innerHTML = renderRichContent(data.updated_content);
      }
    }

    showToast("已换一批");
  } catch (err) {
    if (choicesModEl && backupChoicesHtml) {
      choicesModEl.innerHTML = backupChoicesHtml;
    } else if (btnEl && backupBtnHtml) {
      btnEl.disabled = false;
      btnEl.innerHTML = backupBtnHtml;
    }
    showToast("换一批失败: " + err.message);
  } finally {
    if (btnEl && btnEl.isConnected) {
      btnEl.disabled = false;
    }
    window._isRerollingChoices = false;
  }
};

window.pickRecommendedAction = function (actionText, sendImmediately = true) {
  if (!actionText) return;
  const existingInputDiceMatch = (userInput?.value || "").match(/【[^】]*🎲[^】]*】/);
  let mergedText = String(actionText).trim();
  if (existingInputDiceMatch && !/【[^】]*🎲[^】]*】/.test(mergedText)) {
    mergedText = `${mergedText} ${existingInputDiceMatch[0]}`;
  }
  if (sendImmediately) {
    if (userInput && document.activeElement === userInput) {
      userInput.blur();
    }
    handleSendMessage(mergedText);
  } else if (userInput) {
    userInput.value = mergedText;
    autoResizeTextarea();
    userInput.focus();
    showToast("已填入");
  }
};

window.toggleHtmlPreviewTab = function (cardId, tab) {
  const card = document.getElementById(cardId);
  if (!card) return;
  const previewBody = document.getElementById(`${cardId}_preview`);
  const rawCode = document.getElementById(`${cardId}_code`);
  const btns = card.querySelectorAll(".html-tab-btn");
  if (!previewBody || !rawCode || btns.length < 2) return;

  if (tab === "preview") {
    previewBody.style.display = "block";
    rawCode.style.display = "none";
    btns[0].classList.add("active");
    btns[1].classList.remove("active");
  } else {
    previewBody.style.display = "none";
    rawCode.style.display = "block";
    btns[0].classList.remove("active");
    btns[1].classList.add("active");
  }
};

// ================= 模块三 3.2：空状态直出 3 张高颜值大号剧本卡片 =================
function interpolateClientGreetingVars(rawText, proj) {
  let text = String(rawText || "");
  if (!text || !proj) return text;
  const vars = Array.isArray(proj.prompt_variables) ? proj.prompt_variables : [];
  const chatInputs = (currentChatData && currentChatData.inputs) || {};
  vars.forEach((v) => {
    const key = (v && (v.key || v.name) ? String(v.key || v.name) : "").trim();
    if (!key) return;
    const val = chatInputs[key] !== undefined && chatInputs[key] !== "" ? String(chatInputs[key]) : String(v.default ?? "");
    if (val) {
      text = text.split(`{{${key}}}`).join(val);
    }
  });
  return text;
}

const DEFAULT_BUILTIN_SCENARIO_CARDS = [
  {
    id: "og_builtin_1",
    title: "圣女与暗巷",
    isSandbox: false,
    content: "我想玩《圣女与暗巷》：雨夜的蒸汽下城区，我是一名身怀旧伤的落魄骑士，在暗巷尽头的破败钟楼下，偶然撞见了一名浑身湿透、正被教会黑衣审判官追捕的银发见习圣女。请直接用电影级第二人称视角拉入危机开场。"
  },
  {
    id: "og_builtin_2",
    title: "雾港古宅",
    isSandbox: false,
    content: "我想玩《雾港古宅》：1920年代被海雾笼罩的孤岛渔村，我作为受雇的私家侦探提着煤油灯推开钟表匠老宅生锈的铁门，壁炉里的余烬尚温，桌上的怀表却全部停在了午夜十二点零七分。请直接开启悬疑探索。"
  },
  {
    id: "og_builtin_3",
    title: "自由沙盒",
    isSandbox: true,
    content: "请开启《自由沙盒跑团》模式，根据我的设定或角色卡自动推演世界观，直接把我拉入充满张力的第一幕场景。"
  }
];

const BUILTIN_SHORT_TITLE_MAP = {
  og_free_chat: "聊天",
  og_free_novel: "写小说",
  og_free_rp: "角色扮演",
  og_trpg_fantasy: "圣女与暗巷",
  og_trpg_mystery: "雾港古宅",
  og_trpg_xianxia: "仙门卧底",
  og_trpg_cyber: "霓虹义体猎人",
  og_trpg_sandbox: "自由沙盒"
};

function getActiveProjectOpeningGreetings() {
  const proj = (typeof projectsMap === "object" && projectsMap && currentProjectId) ? projectsMap[currentProjectId] : null;
  const rawList = (proj && Array.isArray(proj.opening_greetings)) ? proj.opening_greetings : [];
  const mapped = rawList
    .map((item, idx) => {
      if (typeof item === "string") {
        const content = interpolateClientGreetingVars(item.trim(), proj);
        return content ? { id: `og_${idx + 1}`, title: `开场 ${idx + 1}`, isSandbox: false, content } : null;
      }
      if (item && typeof item === "object") {
        const rawId = String(item.id || "").trim();
        if (rawId === "og_free_worldbuild") return null;
        let title = BUILTIN_SHORT_TITLE_MAP[rawId] || String(item.title || "").trim() || `开场 ${idx + 1}`;
        const content = interpolateClientGreetingVars(String(item.content || item.text || "").trim(), proj);
        const isSandbox = !!item.isSandbox || /自由沙盒|一句话定制|一句话创世/.test(title);
        return (content || title)
          ? { id: rawId || `og_${idx + 1}`, title, isSandbox, content: content || title }
          : null;
      }
      return null;
    })
    .filter(Boolean);
  if (currentProjectId === "proj_free_chat") {
    return mapped.filter((g) => !["og_free_chat", "og_free_novel", "og_free_rp", "og_free_worldbuild"].includes(g.id));
  }
  return mapped;
}

window._welcomeModeStepSelected = false;

window.enterInitialGameMode = async function (projId, event) {
  if (event) event.stopPropagation();
  window._welcomeModeStepSelected = true;
  if (projId && currentProjectId !== projId) {
    await switchProject(projId);
  } else {
    renderWelcomeBox();
  }
};

window.backToWelcomeModeGate = function (event) {
  if (event) event.stopPropagation();
  window._welcomeModeStepSelected = false;
  renderWelcomeBox();
};

function hasAnyConfiguredModel() {
  if (headerModelSelect && (headerModelSelect.value || "").trim()) return true;
  if ((window.globalUserSettings?.model || "").trim()) return true;
  if ((window.globalUserSettings?.api_key || "").trim() && (window.globalUserSettings?.base_url || "").trim()) return true;
  if (Array.isArray(availableModelsData?.models) && availableModelsData.models.length > 0) return true;
  if (Array.isArray(availableModelsData?.local_models) && availableModelsData.local_models.length > 0) return true;
  return false;
}
window.hasAnyConfiguredModel = hasAnyConfiguredModel;

function buildZeroModelOnboardingHtml() {
  if (!availableModelsData || hasAnyConfiguredModel()) return "";
  return `
    <div id="welcomeZeroModelBar" class="welcome-onboarding-bar" onclick="event.stopPropagation()">
      <div class="welcome-onboarding-info">
        <span class="welcome-onboarding-dot"></span>
        <span>尚未检测到可用 AI 模型 · 任选一种方式配置后即可畅玩</span>
      </div>
      <div class="welcome-onboarding-actions">
        <button type="button" class="btn btn-xs btn-primary" onclick="window.openModelSettingsModal && window.openModelSettingsModal('hf')">⬇️ 一键下载本地模型</button>
        <button type="button" class="btn btn-xs btn-secondary" onclick="window.openModelSettingsModal && window.openModelSettingsModal('local')">📂 扫描 / 挂载 GGUF</button>
        <button type="button" class="btn btn-xs btn-secondary" onclick="window.openModelSettingsModal && window.openModelSettingsModal('api')">🔑 配置在线 API</button>
      </div>
    </div>
  `;
}

function renderWelcomeBox() {
  if (!welcomeBox) return;
  const isBuiltinModeProj = !currentProjectId || currentProjectId === "proj_default" || currentProjectId === "proj_free_chat";
  const onboardingHtml = buildZeroModelOnboardingHtml();

  welcomeBox.style.background = "transparent";
  welcomeBox.style.border = "none";
  welcomeBox.style.boxShadow = "none";

  // 第一步：首次打开显示【跑团】与【聊天】（若完全无模型则附带极简新手引导条）
  if (isBuiltinModeProj && !window._welcomeModeStepSelected) {
    welcomeBox.innerHTML = `
      ${onboardingHtml}
      <div style="display:flex;justify-content:center;align-items:center;gap:24px;flex-wrap:wrap;padding:24px 0;">
        <button type="button" onclick="window.enterInitialGameMode('proj_default', event)" style="min-width:180px;padding:32px 48px;border-radius:16px;border:1px solid rgba(99,102,241,0.45);background:linear-gradient(145deg, rgba(99,102,241,0.14), rgba(15,23,42,0.65));color:#e0e7ff;font-size:1.5rem;font-weight:800;letter-spacing:0.12em;cursor:pointer;transition:transform 0.15s ease,border-color 0.15s ease,box-shadow 0.15s ease;" onmouseover="this.style.transform='translateY(-2px)';this.style.borderColor='rgba(99,102,241,0.85)';this.style.boxShadow='0 8px 24px rgba(99,102,241,0.22)';" onmouseout="this.style.transform='';this.style.borderColor='rgba(99,102,241,0.45)';this.style.boxShadow='';">跑团</button>
        <button type="button" onclick="window.enterInitialGameMode('proj_free_chat', event)" style="min-width:180px;padding:32px 48px;border-radius:16px;border:1px solid rgba(16,185,129,0.45);background:linear-gradient(145deg, rgba(16,185,129,0.14), rgba(15,23,42,0.65));color:#d1fae5;font-size:1.5rem;font-weight:800;letter-spacing:0.12em;cursor:pointer;transition:transform 0.15s ease,border-color 0.15s ease,box-shadow 0.15s ease;" onmouseover="this.style.transform='translateY(-2px)';this.style.borderColor='rgba(16,185,129,0.85)';this.style.boxShadow='0 8px 24px rgba(16,185,129,0.22)';" onmouseout="this.style.transform='';this.style.borderColor='rgba(16,185,129,0.45)';this.style.boxShadow='';">聊天</button>
      </div>
    `;
    return;
  }

  // 第二步：极简展示当前项目的开场按钮
  const greetings = getActiveProjectOpeningGreetings();
  if (!greetings || greetings.length === 0) {
    welcomeBox.innerHTML = onboardingHtml;
    return;
  }

  const buttonsHtml = greetings
    .map((g, idx) => {
      if (g.isSandbox) {
        return `
          <div style="display:flex;flex-direction:column;align-items:center;gap:10px;">
            <button type="button" id="welcomeGreetingCard_${idx}" onclick="window.expandSandboxCreator(${idx}, event)" style="min-width:160px;padding:24px 36px;border-radius:14px;border:1px solid rgba(255,255,255,0.14);background:rgba(15,23,42,0.65);color:#f8fafc;font-size:1.2rem;font-weight:700;letter-spacing:0.08em;cursor:pointer;transition:transform 0.15s ease,border-color 0.15s ease,box-shadow 0.15s ease;" onmouseover="this.style.transform='translateY(-2px)';this.style.borderColor='rgba(99,102,241,0.75)';" onmouseout="this.style.transform='';this.style.borderColor='rgba(255,255,255,0.14)';">${escapeHtml(g.title)}</button>
            <div id="welcomeGreetingEditor_${idx}" style="display:none;gap:8px;align-items:center;" onclick="event.stopPropagation()">
              <input type="text" class="form-input" id="sandboxQuickInput_${idx}" placeholder="输入世界设定..." style="min-width:220px;" onkeydown="if(event.key==='Enter'){event.preventDefault();window.launchSandboxWorld(${idx}, event);}" />
              <button type="button" class="btn btn-xs btn-primary" style="padding:8px 14px;" onclick="window.launchSandboxWorld(${idx}, event)">开始</button>
            </div>
          </div>
        `;
      }
      return `<button type="button" id="welcomeGreetingCard_${idx}" onclick="window.sendOpeningGreetingNow(${idx}, event)" style="min-width:160px;padding:24px 36px;border-radius:14px;border:1px solid rgba(255,255,255,0.14);background:rgba(15,23,42,0.65);color:#f8fafc;font-size:1.2rem;font-weight:700;letter-spacing:0.08em;cursor:pointer;transition:transform 0.15s ease,border-color 0.15s ease,box-shadow 0.15s ease;" onmouseover="this.style.transform='translateY(-2px)';this.style.borderColor='rgba(99,102,241,0.75)';" onmouseout="this.style.transform='';this.style.borderColor='rgba(255,255,255,0.14)';">${escapeHtml(g.title)}</button>`;
    })
    .join("");

  welcomeBox.innerHTML = `
    ${onboardingHtml}
    <div style="display:flex;justify-content:center;align-items:center;gap:20px;flex-wrap:wrap;padding:24px 0;">
      ${buttonsHtml}
    </div>
  `;
}
window.renderWelcomeBox = renderWelcomeBox;

window.expandSandboxCreator = function (idx, event) {
  if (event) event.stopPropagation();
  const editorEl = document.getElementById(`welcomeGreetingEditor_${idx}`);
  if (editorEl) {
    editorEl.style.display = editorEl.style.display === "none" ? "flex" : "none";
    const inp = document.getElementById(`sandboxQuickInput_${idx}`);
    if (inp && editorEl.style.display !== "none") inp.focus();
  }
};

window.launchSandboxWorld = function (idx, event) {
  if (event) event.stopPropagation();
  const inp = document.getElementById(`sandboxQuickInput_${idx}`);
  const idea = (inp?.value || "").trim();
  if (!idea) return;
  handleSendMessage(idea);
};

window.sendOpeningGreetingNow = function (idx, event) {
  if (event) event.stopPropagation();
  const greetings = getActiveProjectOpeningGreetings();
  const item = greetings[idx];
  if (!item) return;
  if (item.isSandbox) {
    window.expandSandboxCreator(idx, event);
    return;
  }
  handleSendMessage(item.content);
};

window.sendOpeningGreetingWithRoll = function (idx, event) {
  window.sendOpeningGreetingNow(idx, event);
};

window.editOpeningGreetingBeforeSend = function (idx, event) {
  window.sendOpeningGreetingNow(idx, event);
};

window.cancelInlineOpeningGreetingEdit = function (idx, event) {
  if (event) event.stopPropagation();
  const previewEl = document.getElementById(`welcomeGreetingPreview_${idx}`);
  const editorEl = document.getElementById(`welcomeGreetingEditor_${idx}`);
  if (previewEl) previewEl.style.display = "block";
  if (editorEl) editorEl.style.display = "none";
};

window.confirmInlineOpeningGreetingSend = function (idx, withRoll = false, event) {
  if (event) event.stopPropagation();
  const textareaEl = document.getElementById(`welcomeGreetingTextarea_${idx}`);
  const text = (textareaEl?.value || "").trim();
  if (!text) {
    showToast("开场白为空");
    return;
  }
  if (withRoll) {
    const rollVal = Math.floor(Math.random() * 100) + 1;
    window.pickRecommendedAction(`${text}\n【🎲 1d100 = ${rollVal}】`, true);
  } else {
    window.pickRecommendedAction(text, true);
  }
};

// ================= 消息流渲染与单条消息编辑/重生成/删除 =================
function renderMessages(messages = currentChatData?.messages, preserveScroll = false) {
  if (!messageContainer) return;
  const prevScrollTop = preserveScroll ? messageContainer.scrollTop : null;
  messageContainer.innerHTML = "";
  if (!messages || messages.length === 0) {
    if (welcomeBox) {
      renderWelcomeBox();
      messageContainer.appendChild(welcomeBox);
      welcomeBox.style.display = "block";
    }
    if (btnScrollBottom) btnScrollBottom.style.display = "none";
    updateContextProgressUI();
    return;
  }
  if (welcomeBox) welcomeBox.style.display = "none";
  messages.forEach((msg) => appendMessageElement(msg));
  updateContextProgressUI();
  if (preserveScroll && prevScrollTop !== null) {
    messageContainer.scrollTop = prevScrollTop;
  } else {
    scrollToBottom();
  }
}
window.renderMessages = renderMessages;

function appendMessageElement(msg) {
  if (welcomeBox) welcomeBox.style.display = "none";
  const item = document.createElement("div");
  item.className = `message-item ${msg.role}`;
  item.dataset.msgId = msg.id;

  const activeProj = (typeof projectsMap === "object" && projectsMap && currentProjectId) ? projectsMap[currentProjectId] : null;
  const assistantIcon = activeProj?.icon || activeProj?.avatar || "";
  const assistantName = activeProj?.name || "主持人";
  const avatarHtml = msg.role === "user" ? "" : renderProjectIconHtml(assistantIcon, 20);

  const bubbleWrap = document.createElement("div");
  bubbleWrap.className = "bubble-wrap";

  // 对话框内置标头：内嵌头像 + 发送者名称 + 时间
  const metaHeader = document.createElement("div");
  metaHeader.className = "msg-meta-header";
  const timeVal = msg.timestamp ? new Date(msg.timestamp * 1000) : new Date();
  const timeStr = !isNaN(timeVal.getTime())
    ? timeVal.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })
    : "";
  metaHeader.innerHTML = `
    ${avatarHtml ? `<span class="msg-inline-avatar">${avatarHtml}</span>` : ""}
    <span class="msg-sender-name">${escapeHtml(msg.role === "user" ? "玩家" : assistantName)}</span>
    ${timeStr ? `<span class="msg-time-label">${escapeHtml(timeStr)}</span>` : ""}
  `;
  bubbleWrap.appendChild(metaHeader);

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  if (msg.role === "assistant") {
    bubble.innerHTML = renderRichContent(msg.content || "");
    if (Array.isArray(msg.suggested_questions) && msg.suggested_questions.length > 0) {
      const sqBox = document.createElement("div");
      sqBox.className = "trpg-suggested-questions-box";
      sqBox.style.cssText = "margin-top:10px;display:flex;flex-direction:column;gap:4px;";
      msg.suggested_questions.forEach((q) => {
        const qText = String(q || "").trim();
        if (!qText) return;
        const qItem = document.createElement("div");
        qItem.textContent = qText;
        attachChoiceItemBehavior(qItem, qText);
        sqBox.appendChild(qItem);
      });
      if (sqBox.children.length > 0) {
        bubble.appendChild(sqBox);
      }
    }
  } else {
    bubble.innerHTML = formatUserBubbleHtml(msg.content || "");
  }

  // 渲染消息附加的角色卡
  const charCards = Array.isArray(msg.character_cards) ? msg.character_cards : [];
  if (charCards.length > 0) {
    renderMessageCharCardsList(charCards, bubble);
  }

  // 渲染消息附图
  const images = msg.images || (msg.image ? [msg.image] : []);
  if (images.length > 0) {
    const grid = document.createElement("div");
    grid.className = "message-images-grid";
    images.forEach((imgSrc) => {
      const img = document.createElement("img");
      img.src = imgSrc;
      img.title = "放大";
      img.onclick = () => {
        if (lightboxImg && imageLightbox) {
          lightboxImg.src = imgSrc;
          imageLightbox.style.display = "flex";
        }
      };
      grid.appendChild(img);
    });
    bubble.appendChild(grid);
  }

  // 消息操作栏（手机端与桌面端均可直接点按）
  const actionBar = document.createElement("div");
  actionBar.className = "msg-action-bar";

  const btnEdit = document.createElement("button");
  btnEdit.type = "button";
  btnEdit.className = "msg-tool-btn";
  btnEdit.innerHTML = "编辑";
  btnEdit.onclick = () => {
    const currentMsgId = item.dataset.msgId || msg.id;
    const currentText = getMessageContent(currentMsgId, bubble);
    startInlineEditMessage(currentMsgId, bubble, currentText);
  };

  if (msg.role === "assistant") {
    const btnRegen = document.createElement("button");
    btnRegen.type = "button";
    btnRegen.className = "msg-tool-btn btn-msg-regen";
    btnRegen.innerHTML = "重新生成";
    btnRegen.onclick = () => {
      const currentMsgId = item.dataset.msgId || msg.id;
      handleRegenerateFromAssistantMessage(currentMsgId);
    };
    actionBar.appendChild(btnRegen);
  }

  const btnBranch = document.createElement("button");
  btnBranch.type = "button";
  btnBranch.className = "msg-tool-btn btn-msg-branch";
  btnBranch.innerHTML = "分支";
  btnBranch.title = "从此处分支";
  btnBranch.onclick = () => {
    const currentMsgId = item.dataset.msgId || msg.id;
    if (typeof window.createBranchFromMessage === "function") {
      window.createBranchFromMessage(currentMsgId);
    }
  };

  const btnCopy = document.createElement("button");
  btnCopy.type = "button";
  btnCopy.className = "msg-tool-btn";
  btnCopy.innerHTML = "复制";
  btnCopy.onclick = () => {
    const currentMsgId = item.dataset.msgId || msg.id;
    const currentText = getMessageContent(currentMsgId, bubble);
    copyText(currentText, "已复制");
  };

  const btnDel = document.createElement("button");
  btnDel.type = "button";
  btnDel.className = "msg-tool-btn btn-msg-del";
  btnDel.innerHTML = "删除";
  btnDel.onclick = () => {
    const currentMsgId = item.dataset.msgId || msg.id;
    deleteSingleMessage(currentMsgId, item);
  };

  actionBar.appendChild(btnEdit);
  actionBar.appendChild(btnBranch);
  actionBar.appendChild(btnCopy);
  actionBar.appendChild(btnDel);

  bubbleWrap.appendChild(bubble);

  // 若该条 AI 回复命中了动态世界书或解锁了 CG，展示轻量化触发徽章
  const wbNames = Array.isArray(msg.triggered_worldbooks) ? msg.triggered_worldbooks : [];
  const cgItems = Array.isArray(msg.triggered_cgs) ? msg.triggered_cgs : [];
  if (wbNames.length > 0 || cgItems.length > 0) {
    const trigBox = document.createElement("div");
    trigBox.className = "msg-triggered-badges";
    wbNames.forEach((w) => {
      const wName = typeof w === "string" ? w : w?.name;
      if (wName) {
        const sp = document.createElement("span");
        sp.className = "msg-trigger-pill";
        sp.textContent = `${wName}`;
        trigBox.appendChild(sp);
      }
    });
    cgItems.forEach((c) => {
      const cTitle = typeof c === "string" ? c : (c?.title || c?.name);
      if (cTitle) {
        const sp = document.createElement("span");
        sp.className = "msg-trigger-pill cg-pill";
        sp.textContent = `解锁CG: ${cTitle}`;
        trigBox.appendChild(sp);
      }
    });
    bubbleWrap.appendChild(trigBox);
  }

  bubbleWrap.appendChild(actionBar);

  // 消息气泡侧边框自由拖拽把手（可拖拽调节对话气泡最大宽度比例，双击恢复默认 88%）
  const bubbleResizer = document.createElement("div");
  bubbleResizer.className = "msg-bubble-resizer";
  bubbleResizer.title = "拖拽调整，双击复位";
  bubbleWrap.appendChild(bubbleResizer);

  item.appendChild(bubbleWrap);
  messageContainer?.appendChild(item);
  return bubble;
}

function getMessageContent(msgId, bubbleEl) {
  const m = currentChatData?.messages?.find((x) => x.id === msgId);
  if (m) return stripLegacyStartGameHint(m.content);
  return bubbleEl ? stripLegacyStartGameHint(bubbleEl.innerText) : "";
}

function extractMessageImages(msgId, itemEl) {
  let imgs = [];
  if (currentChatData && Array.isArray(currentChatData.messages)) {
    const m = currentChatData.messages.find((x) => x.id === msgId);
    if (m) {
      if (Array.isArray(m.images) && m.images.length > 0) {
        imgs = m.images.filter(Boolean);
      } else if (m.image) {
        imgs = [m.image];
      }
    }
  }
  if (imgs.length === 0 && itemEl) {
    const domImgs = Array.from(itemEl.querySelectorAll(".message-images-grid img"))
      .map((el) => el.getAttribute("src") || "")
      .filter((src) => src.startsWith("data:image") || src.startsWith("/api/gallery"));
    if (domImgs.length > 0) {
      imgs = domImgs;
    }
  }
  if (consumeComposerImages && Array.isArray(selectedImages) && selectedImages.length > 0) {
    selectedImages.forEach((si) => {
      if (si && !imgs.includes(si)) imgs.push(si);
    });
    clearAllSelectedImages();
  }
  return imgs;
}

function startInlineEditMessage(msgId, bubbleEl, originalContent) {
  const itemEl = bubbleEl.closest(".message-item");
  const isUser = itemEl ? itemEl.classList.contains("user") : false;
  const preservedImages = isUser ? extractMessageImages(msgId, itemEl, false) : [];
  const originalHtml = bubbleEl.innerHTML;
  bubbleEl.innerHTML = "";

  const editorWrap = document.createElement("div");
  editorWrap.className = "msg-inline-editor";

  const textarea = document.createElement("textarea");
  textarea.rows = 4;
  textarea.className = "form-textarea";
  textarea.value = stripLegacyStartGameHint(originalContent);

  const actions = document.createElement("div");
  actions.className = "msg-inline-actions";

  if (isUser) {
    const btnSaveAndRegen = document.createElement("button");
    btnSaveAndRegen.type = "button";
    btnSaveAndRegen.className = "btn btn-xs btn-primary btn-save-regen";
    btnSaveAndRegen.innerHTML = "保存并生成";
    btnSaveAndRegen.onclick = async () => {
      const updatedText = stripLegacyStartGameHint(textarea.value.trim());
      if (!updatedText && preservedImages.length === 0) return;
      await handleSaveAndRegenerateUserMessage(msgId, updatedText, preservedImages);
    };

    const btnSaveOnly = document.createElement("button");
    btnSaveOnly.type = "button";
    btnSaveOnly.className = "btn btn-xs btn-secondary";
    btnSaveOnly.innerHTML = "仅保存";
    btnSaveOnly.onclick = async () => {
      const updatedText = stripLegacyStartGameHint(textarea.value.trim());
      if (!updatedText && preservedImages.length === 0) return;
      await handleSaveUserMessageOnly(msgId, updatedText, bubbleEl, preservedImages);
    };

    const btnCancel = document.createElement("button");
    btnCancel.type = "button";
    btnCancel.className = "btn btn-xs btn-outline-secondary";
    btnCancel.textContent = "取消";
    btnCancel.onclick = () => {
      bubbleEl.innerHTML = originalHtml;
    };

    actions.appendChild(btnSaveAndRegen);
    actions.appendChild(btnSaveOnly);
    actions.appendChild(btnCancel);

    textarea.onkeydown = (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        btnSaveAndRegen.click();
      }
    };
  } else {
    const btnSave = document.createElement("button");
    btnSave.type = "button";
    btnSave.className = "btn btn-xs btn-primary";
    btnSave.textContent = "保存";
    btnSave.onclick = async () => {
      const updatedText = textarea.value.trim();
      if (!updatedText) return;
      try {
        await fetch(`/api/chats/${currentChatId}/messages/${msgId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: updatedText })
        });
        bubbleEl.innerHTML = renderRichContent(updatedText);
        if (currentChatData && currentChatData.messages) {
          const m = currentChatData.messages.find((x) => x.id === msgId);
          if (m) m.content = updatedText;
        }
        showToast("已更新");
      } catch (err) {
        showToast("修改失败: " + err);
      }
    };

    const btnSaveAndRegen = document.createElement("button");
    btnSaveAndRegen.type = "button";
    btnSaveAndRegen.className = "btn btn-xs btn-secondary";
    btnSaveAndRegen.innerHTML = "重新生成";
    btnSaveAndRegen.onclick = async () => {
      await handleRegenerateFromAssistantMessage(msgId);
    };

    const btnCancel = document.createElement("button");
    btnCancel.type = "button";
    btnCancel.className = "btn btn-xs btn-outline-secondary";
    btnCancel.textContent = "取消";
    btnCancel.onclick = () => {
      bubbleEl.innerHTML = originalHtml;
    };

    actions.appendChild(btnSave);
    actions.appendChild(btnSaveAndRegen);
    actions.appendChild(btnCancel);
  }

  editorWrap.appendChild(textarea);
  editorWrap.appendChild(actions);
  bubbleEl.appendChild(editorWrap);
  if (isUser && preservedImages.length > 0) {
    const grid = document.createElement("div");
    grid.className = "message-images-grid";
    preservedImages.forEach((imgSrc) => {
      const img = document.createElement("img");
      img.src = imgSrc;
      grid.appendChild(img);
    });
    bubbleEl.appendChild(grid);
  }
  textarea.focus();
}

async function handleSaveUserMessageOnly(msgId, updatedText, bubbleEl, fallbackImages = []) {
  try {
    await fetch(`/api/chats/${currentChatId}/messages/${msgId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: updatedText })
    });
    const m = currentChatData?.messages?.find((x) => x.id === msgId);
    if (m) {
      m.content = updatedText;
      if ((!Array.isArray(m.images) || m.images.length === 0) && fallbackImages.length > 0) {
        m.images = [...fallbackImages];
      }
    }

    bubbleEl.innerHTML = formatUserBubbleHtml(updatedText);
    if (Array.isArray(m?.character_cards) && m.character_cards.length > 0) {
      renderMessageCharCardsList(m.character_cards, bubbleEl);
    }
    const images = (m?.images && m.images.length > 0) ? m.images : (m?.image ? [m.image] : fallbackImages);
    if (images.length > 0) {
      const grid = document.createElement("div");
      grid.className = "message-images-grid";
      images.forEach((imgSrc) => {
        const img = document.createElement("img");
        img.src = imgSrc;
        img.onclick = () => {
          if (lightboxImg && imageLightbox) {
            lightboxImg.src = imgSrc;
            imageLightbox.style.display = "flex";
          }
        };
        grid.appendChild(img);
      });
      bubbleEl.appendChild(grid);
    }
    showToast("已更新");
  } catch (err) {
    showToast("保存失败: " + err);
  }
}

function abortCurrentChatStream(chatId = currentChatId, silent = true, stopServer = false) {
  if (chatId === currentChatId && bgPollTimer) {
    clearInterval(bgPollTimer);
    bgPollTimer = null;
    if (silent) {
      const bgEl = messageContainer?.querySelector('.message-item[data-msg-id="msg_bg_polling"]');
      if (bgEl) bgEl.remove();
    }
    if (btnSend) btnSend.style.display = "inline-flex";
    if (btnStop) btnStop.style.display = "none";
  }
  if (chatId && activeStreams[chatId]) {
    const streamInfo = activeStreams[chatId];
    if (streamInfo.renderTimer) {
      clearTimeout(streamInfo.renderTimer);
      streamInfo.renderTimer = null;
    }
    streamInfo.isAbortedForRegen = silent;
    try {
      streamInfo.controller.abort();
    } catch (e) {}
    if (silent && streamInfo.itemEl) {
      streamInfo.itemEl.remove();
    }
    delete activeStreams[chatId];
    // 旧流的 finally 在 isAbortedForRegen=true 时会提前 return，这里负责复位按钮，避免 UI 卡在“生成中”
    if (chatId === currentChatId) {
      if (btnSend) btnSend.style.display = "inline-flex";
      if (btnStop) btnStop.style.display = "none";
    }
    // 仅在不会紧接着发起新生成时通知服务端停止（新生成请求服务端会自行取消旧任务，避免异步 stop 误杀新任务）
    if (stopServer) {
      fetch(`/api/chats/${encodeURIComponent(chatId)}/stop`, { method: "POST" }).catch(() => {});
    }
    renderChatList();
  } else if (stopServer && chatId) {
    fetch(`/api/chats/${encodeURIComponent(chatId)}/stop`, { method: "POST" }).catch(() => {});
  }
}

// 重新编辑玩家自己的发言 -> 自动截断后续并立即触发重新生成
async function handleSaveAndRegenerateUserMessage(userMsgId, newContent, fallbackImages = []) {
  if (!currentChatId) return;
  abortCurrentChatStream(currentChatId, true);

  const cleanContent = stripLegacyStartGameHint(newContent);
  const allMsgItems = Array.from(messageContainer.querySelectorAll(".message-item"));
  const userItemIdx = allMsgItems.findIndex((el) => el.dataset.msgId === userMsgId);
  const userItemEl = userItemIdx !== -1 ? allMsgItems[userItemIdx] : null;
  let existingImages = extractMessageImages(userMsgId, userItemEl);
  if (existingImages.length === 0 && Array.isArray(fallbackImages) && fallbackImages.length > 0) {
    existingImages = [...fallbackImages];
  }
  let existingCharCards = [];

  if (currentChatData && currentChatData.messages) {
    const idx = currentChatData.messages.findIndex((m) => m.id === userMsgId);
    if (idx !== -1) {
      currentChatData.messages[idx].content = cleanContent;
      if (existingImages.length > 0) {
        currentChatData.messages[idx].images = existingImages;
      }
      existingCharCards = Array.isArray(currentChatData.messages[idx].character_cards) ? currentChatData.messages[idx].character_cards : [];
      currentChatData.messages = currentChatData.messages.slice(0, idx + 1);
      currentChatData.summarized_count = Math.min(
        parseInt(currentChatData.summarized_count) || 0,
        Math.max(0, currentChatData.messages.length - 1)
      );
    }
  }
  updateContextProgressUI();

  if (userItemIdx !== -1) {
    for (let i = userItemIdx + 1; i < allMsgItems.length; i++) {
      allMsgItems[i].remove();
    }
    const userBubble = allMsgItems[userItemIdx].querySelector(".bubble");
    if (userBubble) {
      userBubble.innerHTML = formatUserBubbleHtml(cleanContent);
      if (existingCharCards.length > 0) {
        renderMessageCharCardsList(existingCharCards, userBubble);
      }
      if (existingImages.length > 0) {
        const grid = document.createElement("div");
        grid.className = "message-images-grid";
        existingImages.forEach((imgSrc) => {
          const img = document.createElement("img");
          img.src = imgSrc;
          img.onclick = () => {
            if (lightboxImg && imageLightbox) {
              lightboxImg.src = imgSrc;
              imageLightbox.style.display = "flex";
            }
          };
          grid.appendChild(img);
        });
        userBubble.appendChild(grid);
      }
    }
  }

  showToast("已保存，重新生成中");
  startStreamingProcess({
    chatId: currentChatId,
    mode: "regenerate",
    target_user_msg_id: userMsgId,
    content: cleanContent,
    images: existingImages.length > 0 ? existingImages : null,
    character_cards: existingCharCards.length > 0 ? existingCharCards : null
  });
}

async function handleRegenerateFromAssistantMessage(assistantMsgId) {
  if (!currentChatId) return;
  abortCurrentChatStream(currentChatId, true);

  let targetUserMsgId = null;
  if (currentChatData && currentChatData.messages) {
    const aIdx = currentChatData.messages.findIndex((m) => m.id === assistantMsgId);
    if (aIdx !== -1) {
      for (let i = aIdx - 1; i >= 0; i--) {
        if (currentChatData.messages[i].role === "user") {
          targetUserMsgId = currentChatData.messages[i].id;
          break;
        }
      }
      currentChatData.messages = currentChatData.messages.slice(0, aIdx);
      currentChatData.summarized_count = Math.min(
        parseInt(currentChatData.summarized_count) || 0,
        Math.max(0, currentChatData.messages.length - 1)
      );
    }
  }
  updateContextProgressUI();

  const allMsgItems = Array.from(messageContainer.querySelectorAll(".message-item"));
  const aItemIdx = allMsgItems.findIndex((el) => el.dataset.msgId === assistantMsgId);
  if (aItemIdx !== -1) {
    for (let i = aItemIdx; i < allMsgItems.length; i++) {
      allMsgItems[i].remove();
    }
  }

  const userItemEl = targetUserMsgId ? allMsgItems.find((el) => el.dataset.msgId === targetUserMsgId) : null;
  const regenImages = targetUserMsgId ? extractMessageImages(targetUserMsgId, userItemEl) : [];

  showToast("重新生成中");
  startStreamingProcess({
    chatId: currentChatId,
    mode: "regenerate",
    target_user_msg_id: targetUserMsgId,
    images: regenImages.length > 0 ? regenImages : null
  });
}

async function handleRegenerateLatest() {
  if (!currentChatId) {
    showToast("请先选择对话");
    return;
  }

  const wasGenerating = !!activeStreams[currentChatId];
  abortCurrentChatStream(currentChatId, true);

  const messages = currentChatData?.messages || [];
  let lastUserIdx = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "user") {
      lastUserIdx = i;
      break;
    }
  }

  if (lastUserIdx === -1) {
    showToast("无可重新生成的消息");
    return;
  }

  const targetUserMsg = messages[lastUserIdx];
  const allMsgItems = Array.from(messageContainer.querySelectorAll(".message-item"));
  const userItemIdx = allMsgItems.findIndex((el) => el.dataset.msgId === targetUserMsg.id);
  const userItemEl = userItemIdx !== -1 ? allMsgItems[userItemIdx] : null;
  const regenImages = extractMessageImages(targetUserMsg.id, userItemEl);
  if (regenImages.length > 0) {
    targetUserMsg.images = regenImages;
  }

  if (userItemIdx !== -1) {
    for (let i = userItemIdx + 1; i < allMsgItems.length; i++) {
      allMsgItems[i].remove();
    }
  }

  currentChatData.messages = messages.slice(0, lastUserIdx + 1);
  currentChatData.summarized_count = Math.min(
    parseInt(currentChatData.summarized_count) || 0,
    Math.max(0, currentChatData.messages.length - 1)
  );
  updateContextProgressUI();
  showToast(wasGenerating ? "已中断，重新生成中" : "重新生成中");

  startStreamingProcess({
    chatId: currentChatId,
    mode: "regenerate",
    target_user_msg_id: targetUserMsg.id,
    images: regenImages.length > 0 ? regenImages : null
  });
}

async function deleteSingleMessage(msgId, itemEl) {
  const confirmed = await showCustomDialog({
    title: "删除消息",
    message: "删除此消息？"
  });
  if (!confirmed) return;

  try {
    const res = await fetch(`/api/chats/${currentChatId}/messages/${msgId}`, { method: "DELETE" });
    let resData = {};
    try {
      resData = await res.json();
    } catch (_) {}
    itemEl.remove();
    if (currentChatData && currentChatData.messages) {
      const delIdx = currentChatData.messages.findIndex((m) => m.id === msgId);
      currentChatData.messages = currentChatData.messages.filter((m) => m.id !== msgId);
      if (typeof resData.summarized_count === "number") {
        currentChatData.summarized_count = resData.summarized_count;
      } else if (delIdx !== -1) {
        let oldSum = parseInt(currentChatData.summarized_count) || 0;
        if (delIdx < oldSum) oldSum = Math.max(0, oldSum - 1);
        currentChatData.summarized_count = Math.min(oldSum, Math.max(0, currentChatData.messages.length - 2));
      }
    }
    updateContextProgressUI();
    showToast("已删除");
  } catch (err) {
    showToast("删除失败: " + err);
  }
}

function scrollToBottom() {
  if (!messageContainer) return;
  messageContainer.scrollTop = messageContainer.scrollHeight;
  if (btnScrollBottom) btnScrollBottom.style.display = "none";
}

// ================= 流式生成核心引擎（文字流式输出时绝不强制滚动拉扯） =================
function startStreamingProcess(options) {
  const {
    chatId,
    mode = "send",
    content = "",
    images = null,
    character_cards = null,
    target_user_msg_id = null,
    user_msg_id = null
  } = options;
  const currentModel = headerModelSelect?.value || (currentChatData && currentChatData.model);
  if (currentChatData && currentModel && currentChatData.model !== currentModel) {
    currentChatData.model = currentModel;
  }

  const assistantMsgId = "msg_reply_" + Date.now().toString(36);
  const assistantBubble = appendMessageElement({
    id: assistantMsgId,
    role: "assistant",
    content: mode === "regenerate" ? "重新生成中…" : "生成中…",
    images: []
  });
  const assistantItem = assistantBubble.closest(".message-item");

  if (btnSend) btnSend.style.display = "none";
  if (btnStop) btnStop.style.display = "inline-flex";

  const controller = new AbortController();
  activeStreams[chatId] = {
    controller,
    bubbleEl: assistantBubble,
    itemEl: assistantItem,
    msgId: assistantMsgId,
    text: "",
    done: false,
    isAbortedForRegen: false
  };

  renderChatList();

  fetchStreamForChat(chatId, {
    chat_id: chatId,
    content: content,
    images_base64: Array.isArray(images) && images.length > 0 ? images : (mode === "send" ? [] : null),
    character_cards: Array.isArray(character_cards) && character_cards.length > 0 ? character_cards : (mode === "send" ? [] : null),
    model: currentModel,
    mode: mode,
    target_user_msg_id: target_user_msg_id,
    user_msg_id: user_msg_id
  });
}

async function handleSendMessage(overrideText) {
  const hasOverride = typeof overrideText === "string" && overrideText.trim().length > 0;
  let rawText = stripLegacyStartGameHint(hasOverride ? overrideText.trim() : (userInput?.value.trim() || ""));
  if (hasOverride && userInput && userInput.value) {
    const pendingDiceMatch = userInput.value.match(/【[^】]*🎲[^】]*】/);
    if (pendingDiceMatch && !/【[^】]*🎲[^】]*】/.test(rawText)) {
      rawText = `${rawText} ${pendingDiceMatch[0]}`.trim();
    }
  }
  if (!rawText && selectedImages.length === 0 && selectedCharacterCards.length === 0) return;

  if (!hasAnyConfiguredModel()) {
    showToast("请先下载本地模型或配置在线 API 后即可开始游玩");
    if (typeof window.openModelSettingsModal === "function") {
      window.openModelSettingsModal("hf");
    }
    return;
  }

  if (!currentChatId) {
    await loadChats();
    if (!currentChatId) {
      await createNewChat();
    }
  }
  if (!currentChatId) return;

  // 支持通用 TRPG 掷骰指令：/roll 2d6+3 或 /r 1d20+4
  const rollCmdMatch = rawText.match(/^\/(?:roll|r)\s+([0-9dD+\-\s]+)(.*)$/i);
  if (rollCmdMatch) {
    const diceRes = evaluateDiceExpression(rollCmdMatch[1]);
    if (diceRes) {
      const note = (rollCmdMatch[2] || "").trim();
      rawText = `🎲 【玩家投掷检定】${note ? note + "：" : ""}掷出 ${diceRes.expr} = ${diceRes.total} (${diceRes.detail})`;
      showToast(`掷出 ${diceRes.expr} = ${diceRes.total}`);
    }
  }

  const targetChatId = currentChatId;
  if (activeStreams[targetChatId] || bgPollTimer) {
    abortCurrentChatStream(targetChatId, false, false);
  }
  const sendingImages = [...selectedImages];
  const sendingCharCards = selectedCharacterCards.map((c) => JSON.parse(JSON.stringify(c)));
  const sendingText =
    rawText ||
    (sendingCharCards.length > 0
      ? `【附带角色卡：${sendingCharCards.map((c) => c.name || "未命名角色").join("、")}】`
      : "");

  if (!hasOverride && userInput) {
    userInput.value = "";
    autoResizeTextarea();
  } else if (hasOverride && userInput) {
    if (userInput.value.trim() === overrideText.trim() || /【[^】]*🎲[^】]*】/.test(userInput.value)) {
      userInput.value = "";
      autoResizeTextarea();
    }
  }
  clearAllSelectedImages();
  clearAllSelectedCharCards();

  // 生成统一的前后端消息 ID，确保刚发出的消息即可直接行内编辑或删除
  const userMsgId = "u_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
  appendMessageElement({
    id: userMsgId,
    role: "user",
    content: sendingText,
    images: sendingImages,
    character_cards: sendingCharCards
  });

  if (currentChatData && currentChatData.messages) {
    currentChatData.messages.push({
      id: userMsgId,
      role: "user",
      content: sendingText,
      images: sendingImages,
      character_cards: sendingCharCards,
      timestamp: Date.now() / 1000
    });
  }
  updateContextProgressUI();

  // 仅在玩家点击发送那一刻平滑对齐一次底部，之后 AI 生成全程绝不强制滚动
  scrollToBottom();
  abortCurrentChatStream(targetChatId, true);

  startStreamingProcess({
    chatId: targetChatId,
    mode: "send",
    content: sendingText,
    images: sendingImages,
    character_cards: sendingCharCards,
    user_msg_id: userMsgId
  });
}

async function fetchStreamForChat(chatId, reqPayload) {
  const streamInfo = activeStreams[chatId];
  if (!streamInfo) return;

  try {
    if (window._pendingContentScaleSavePromise) {
      try {
        await window._pendingContentScaleSavePromise;
      } catch (_) {}
    }
    if (typeof window.getEffectiveContentScaleLevels === "function") {
      const liveLvls = window.getEffectiveContentScaleLevels();
      reqPayload.erotic_level = liveLvls.erotic;
      reqPayload.violence_level = liveLvls.violence;
      reqPayload.erotic_enabled = liveLvls.eroticEnabled;
      reqPayload.violence_enabled = liveLvls.violenceEnabled;
    }
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(reqPayload),
      signal: streamInfo.controller.signal
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    // 手机竖屏防弹跳与触控保护：记录用户在思考/状态折叠框上的手动展开/收起状态，以及安全替换 innerHTML（锁死 scrollTop 防止回弹）
    if (streamInfo.bubbleEl && !streamInfo.bubbleEl._streamTouchBound) {
      streamInfo.bubbleEl._streamTouchBound = true;
      streamInfo.bubbleEl.addEventListener(
        "pointerdown",
        (ev) => {
          const sumEl = ev.target.closest ? ev.target.closest("details.think-collapse-card > summary") : null;
          if (sumEl) {
            const det = sumEl.parentElement;
            if (det) {
              // pointerdown 发生在 click 切换 det.open 之前，因此目标状态是 !det.open
              streamInfo._userThinkOpenState = !det.open;
            }
          }
          const stSumEl = ev.target.closest ? ev.target.closest("details.bg3-status-hud-card > summary") : null;
          if (stSumEl) {
            const det = stSumEl.parentElement;
            if (det) {
              streamInfo._userStatusOpenState = !det.open;
            }
          }
        },
        { passive: true }
      );
    }

    const applyStreamBubbleHtmlSafely = (htmlStr) => {
      if (currentChatId !== chatId || !streamInfo.bubbleEl) return;
      const prevScrollTop = messageContainer ? messageContainer.scrollTop : 0;
      const existingThink = streamInfo.bubbleEl.querySelector("details.think-collapse-card");
      if (existingThink && streamInfo._userThinkOpenState === undefined && existingThink.hasAttribute("open")) {
        streamInfo._userThinkOpenState = true;
      }
      streamInfo.bubbleEl.innerHTML = htmlStr;
      if (streamInfo._userThinkOpenState !== undefined) {
        const newThink = streamInfo.bubbleEl.querySelector("details.think-collapse-card");
        if (newThink) {
          if (streamInfo._userThinkOpenState) {
            newThink.setAttribute("open", "");
          } else {
            newThink.removeAttribute("open");
          }
        }
      }
      if (streamInfo._userStatusOpenState !== undefined) {
        const newStatus = streamInfo.bubbleEl.querySelector("details.bg3-status-hud-card");
        if (newStatus) {
          if (streamInfo._userStatusOpenState) {
            newStatus.setAttribute("open", "");
          } else {
            newStatus.removeAttribute("open");
          }
        }
      }
      // 关键修复：手机浏览器在替换长气泡 innerHTML 时会丢失滚动锚点导致画面猛烈往上弹，此处同步锁死原 scrollTop
      if (messageContainer && Math.abs(messageContainer.scrollTop - prevScrollTop) > 1) {
        messageContainer.scrollTop = prevScrollTop;
      }
      if (typeof window.updateScrollBottomBtnVisibility === "function") {
        window.updateScrollBottomBtnVisibility();
      }
    };

    const scheduleStreamChunkRender = () => {
      if (streamInfo.renderTimer) return;
      const now = Date.now();
      const elapsed = now - (streamInfo.lastRenderAt || 0);
      const minInterval = 140; // 140ms 节流，彻底释放手机端主线程，保证按钮点击 100% 灵敏响应
      const waitMs = Math.max(16, minInterval - elapsed);
      streamInfo.renderTimer = setTimeout(() => {
        streamInfo.renderTimer = null;
        if (currentChatId !== chatId || !streamInfo.bubbleEl) return;
        // 若用户手指正在点击按钮或刚触摸屏幕不到 180ms，延后 DOM 重绘以防吞掉移动端 click 事件或引发触控回弹
        const sinceTouch = Date.now() - (window._lastTouchInteractionAt || 0);
        if (window._isUserTouchingScreen || sinceTouch < 180) {
          scheduleStreamChunkRender();
          return;
        }
        streamInfo.lastRenderAt = Date.now();
        const renderedStreamHtml = renderRichContent(streamInfo.text);
        applyStreamBubbleHtmlSafely(renderedStreamHtml || `<span class="stream-status-text">生成中…</span>`);
      }, waitMs);
    };

    // 单个 SSE 事件块处理（抽取为局部函数，以便读取结束后冲刷剩余缓冲）
    const processSseBlock = (block) => {
        const line = block.trim();
        if (!line.startsWith("data: ")) return;
        try {
          const data = JSON.parse(line.slice(6));
          if (data.status && !streamInfo.text) {
            if (currentChatId === chatId && streamInfo.bubbleEl) {
              applyStreamBubbleHtmlSafely(`<span class="stream-status-text">${escapeHtml(data.status)}</span>`);
            }
          } else if (data.error !== undefined && data.error !== null) {
            const errMsg = String(data.error).trim() || "模型无响应，请重新生成";
            streamInfo.text += `\n接口提示: ${errMsg}`;
            if (currentChatId === chatId && streamInfo.bubbleEl) {
              applyStreamBubbleHtmlSafely(`<span style="color:#f87171;">${escapeHtml(streamInfo.text)}</span>`);
            }
          } else if (data.chunk) {
            streamInfo.text += data.chunk;
            if (currentChatId === chatId && streamInfo.bubbleEl) {
              scheduleStreamChunkRender();
            }
          } else if (typeof data.replace === "string") {
            streamInfo.text = data.replace;
            if (currentChatId === chatId && streamInfo.bubbleEl) {
              scheduleStreamChunkRender();
            }
          } else if (data.done) {
            if (streamInfo.renderTimer) {
              clearTimeout(streamInfo.renderTimer);
              streamInfo.renderTimer = null;
            }
            if (typeof data.full_reply === "string" && data.full_reply) {
              streamInfo.text = data.full_reply;
            }
            if (currentChatId === chatId && streamInfo.bubbleEl) {
              applyStreamBubbleHtmlSafely(renderRichContent(streamInfo.text));
            }
            if (data.msg_id) {
              if (streamInfo.itemEl) {
                streamInfo.itemEl.dataset.msgId = data.msg_id;
              }
              if (currentChatId === chatId && currentChatData && currentChatData.messages) {
                currentChatData.messages.push({
                  id: data.msg_id,
                  role: "assistant",
                  content: streamInfo.text,
                  triggered_worldbooks: (data.triggered_worldbooks || []).map((w) => (typeof w === "string" ? w : w?.name)).filter(Boolean),
                  triggered_cgs: data.triggered_cgs || [],
                  timestamp: Date.now() / 1000
                });
              }
            }
            if (currentChatId === chatId && streamInfo.itemEl) {
              const wbList = Array.isArray(data.triggered_worldbooks) ? data.triggered_worldbooks : [];
              const cgList = Array.isArray(data.triggered_cgs) ? data.triggered_cgs : [];
              const bWrap = streamInfo.itemEl.querySelector(".bubble-wrap");
              const actBar = streamInfo.itemEl.querySelector(".msg-action-bar");
              if (bWrap && (wbList.length > 0 || cgList.length > 0) && !bWrap.querySelector(".msg-triggered-badges")) {
                const trigBox = document.createElement("div");
                trigBox.className = "msg-triggered-badges";
                wbList.forEach((w) => {
                  const wName = typeof w === "string" ? w : w?.name;
                  if (wName) {
                    const sp = document.createElement("span");
                    sp.className = "msg-trigger-pill";
                    sp.textContent = `${wName}`;
                    trigBox.appendChild(sp);
                  }
                });
                cgList.forEach((c) => {
                  const cTitle = typeof c === "string" ? c : (c?.title || c?.name);
                  if (cTitle) {
                    const sp = document.createElement("span");
                    sp.className = "msg-trigger-pill cg-pill";
                    sp.textContent = `解锁CG: ${cTitle}`;
                    trigBox.appendChild(sp);
                  }
                });
                if (actBar) bWrap.insertBefore(trigBox, actBar);
                else bWrap.appendChild(trigBox);
              }
            }
            if (typeof data.summarized_count === "number" && currentChatId === chatId && currentChatData) {
              currentChatData.summarized_count = data.summarized_count;
            }
            if (data.summary && currentChatId === chatId) {
              if (currentChatData) currentChatData.summary = data.summary;
              updateSummaryUI(data.summary);
            }
            if (currentChatId === chatId) {
              updateContextProgressUI();
            }
            if (data.title) {
              const found = cachedChatList.find((c) => c.id === chatId);
              if (found && found.title !== data.title) {
                found.title = data.title;
                if (currentChatId === chatId && currentChatTitleEl) {
                  currentChatTitleEl.textContent = data.title;
                }
                renderChatList();
              }
            }
            if ((Array.isArray(data.unlocked_cgs) || Array.isArray(data.triggered_cgs)) && currentChatId === chatId) {
              const prevUnlocked = (currentChatData && currentChatData.unlocked_cgs) || [];
              if (Array.isArray(data.unlocked_cgs) && currentChatData) {
                currentChatData.unlocked_cgs = data.unlocked_cgs;
              }
              if (Array.isArray(data.triggered_cgs) && data.triggered_cgs.length > 0) {
                const proj = projectsMap && projectsMap[currentProjectId];
                if (proj && Array.isArray(proj.cg_book)) {
                  data.triggered_cgs.forEach((tcg) => {
                    const foundCg = proj.cg_book.find((c) => c.id === tcg.id || c.name === tcg.name);
                    if (foundCg) foundCg.unlocked = true;
                  });
                }
                showToast(`已解锁 CG：${data.triggered_cgs.map((c) => c.name || c.title).join("、")}`);
              } else if (Array.isArray(data.unlocked_cgs) && data.unlocked_cgs.length > prevUnlocked.length) {
                showToast("已解锁新 CG");
              }
              if (typeof renderUnlockedCgsBanner === "function") renderUnlockedCgsBanner();
            }
          }
        } catch (e) {
          console.error("流数据块解析异常:", e);
        }
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split(/\r?\n\r?\n/);
      buffer = lines.pop();

      for (const block of lines) {
        processSseBlock(block);
      }
    }
    // 流结束：冲刷解码器并处理末尾未以空行结尾的残余事件块（防止丢失最后的 done 事件）
    buffer += decoder.decode();
    if (buffer.trim()) {
      for (const block of buffer.split(/\r?\n\r?\n/)) {
        processSseBlock(block);
      }
    }
    buffer = "";
  } catch (err) {
    if (streamInfo.renderTimer) {
      clearTimeout(streamInfo.renderTimer);
      streamInfo.renderTimer = null;
    }
    if (err.name === "AbortError") {
      if (streamInfo.isAbortedForRegen) return;
      streamInfo.text += `\n\n*(已停止)*`;
      if (currentChatId === chatId && streamInfo.bubbleEl) {
        const prevSt = messageContainer ? messageContainer.scrollTop : 0;
        streamInfo.bubbleEl.innerHTML = renderRichContent(streamInfo.text);
        if (messageContainer && Math.abs(messageContainer.scrollTop - prevSt) > 1) {
          messageContainer.scrollTop = prevSt;
        }
      }
    } else {
      streamInfo.text += `\n连接中断: ${err.message}（可刷新查看）`;
      if (currentChatId === chatId && streamInfo.bubbleEl) {
        const prevSt = messageContainer ? messageContainer.scrollTop : 0;
        streamInfo.bubbleEl.innerHTML = renderRichContent(streamInfo.text);
        if (messageContainer && Math.abs(messageContainer.scrollTop - prevSt) > 1) {
          messageContainer.scrollTop = prevSt;
        }
      }
    }
  } finally {
    if (streamInfo.renderTimer) {
      clearTimeout(streamInfo.renderTimer);
      streamInfo.renderTimer = null;
    }
    if (streamInfo.isAbortedForRegen) return;
    if (currentChatId !== chatId) {
      unreadChats.add(chatId);
      showToast("后台对话已生成");
    } else {
      if (btnSend) btnSend.style.display = "inline-flex";
      if (btnStop) btnStop.style.display = "none";
    }
    delete activeStreams[chatId];
    renderChatList();
  }
}

function handleStopCurrentGeneration() {
  if (!currentChatId) return;
  fetch(`/api/chats/${currentChatId}/stop`, { method: "POST" }).catch(() => {});
  if (bgPollTimer) {
    clearInterval(bgPollTimer);
    bgPollTimer = null;
    if (btnSend) btnSend.style.display = "inline-flex";
    if (btnStop) btnStop.style.display = "none";
  }
  if (activeStreams[currentChatId]) {
    activeStreams[currentChatId].isAbortedForRegen = false;
    activeStreams[currentChatId].controller.abort();
  }
}

// ================= 多图上传、自动压缩与粘贴处理 =================
function handleFileSelectMultiple(e) {
  const files = Array.from(e.target.files || []);
  if (!files.length) return;
  try {
    e.target.value = "";
  } catch (err) {}
  showToast(`处理 ${files.length} 张图片…`);

  for (const file of files) {
    readAndAppendImage(file);
  }
}

function handlePasteMultiple(e) {
  const charEditorModal = document.getElementById("charCardEditorModal");
  if (charEditorModal && charEditorModal.style.display !== "none") {
    handleCharAiPromptPaste(e);
    return;
  }
  const items = (e.clipboardData || e.originalEvent?.clipboardData)?.items;
  if (!items) return;
  let hasImage = false;
  for (let i = 0; i < items.length; i++) {
    if (items[i].type.indexOf("image") !== -1) {
      const blob = items[i].getAsFile();
      readAndAppendImage(blob);
      hasImage = true;
    }
  }
  if (hasImage) e.preventDefault();
}

function readAndAppendImage(file) {
  if (!file) return;
  compressImageToJpeg(file, 1024, 0.78, (compressedData) => {
    if (!compressedData) return;
    if (!selectedImages.includes(compressedData)) {
      selectedImages.push(compressedData);
    }
    renderImagePreviews();
    const approxKb = Math.max(1, Math.round((compressedData.length * 0.75) / 1024));
    showToast(`图片已就绪 (${approxKb} KB)`);
    if (imagePreviewBar) {
      imagePreviewBar.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    uploadImageToGalleryBackend(compressedData, file.name || "uploaded.jpg");
  });
}

function compressImageToJpeg(source, maxDimension = 1024, quality = 0.78, callback) {
  if (!source) {
    if (typeof callback === "function") callback("");
    return;
  }
  const isBlob = typeof Blob !== "undefined" && source instanceof Blob;
  const objectUrl = isBlob ? URL.createObjectURL(source) : null;
  const img = new Image();
  img.onload = () => {
    if (objectUrl) {
      try {
        URL.revokeObjectURL(objectUrl);
      } catch (e) {}
    }
    let width = img.width || 1024;
    let height = img.height || 1024;
    const capDim = Math.min(maxDimension || 1024, 1280);
    if (width > capDim || height > capDim) {
      if (width > height) {
        height = Math.max(1, Math.round((height * capDim) / width));
        width = capDim;
      } else {
        width = Math.max(1, Math.round((width * capDim) / height));
        height = capDim;
      }
    }
    const renderAt = (w, h, q) => {
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, w, h);
      ctx.drawImage(img, 0, 0, w, h);
      return canvas.toDataURL("image/jpeg", q);
    };
    try {
      let curW = width;
      let curH = height;
      let curQ = Math.min(0.85, Math.max(0.5, quality || 0.78));
      let result = renderAt(curW, curH, curQ);
      // 约 240KB 对应的 base64 长度约为 328,000 字符；若超出则自动递减质量与分辨率，杜绝大图
      const maxBase64Len = 330000;
      let step = 0;
      while (result.length > maxBase64Len && step < 3) {
        step++;
        curQ = Math.max(0.55, curQ - 0.1);
        if (step >= 2 && Math.max(curW, curH) > 768) {
          curW = Math.max(1, Math.round(curW * 0.82));
          curH = Math.max(1, Math.round(curH * 0.82));
        }
        result = renderAt(curW, curH, curQ);
      }
      callback(result);
    } catch (e) {
      if (!isBlob && typeof source === "string") {
        callback(source);
      } else {
        callback("");
      }
    }
  };
  img.onerror = () => {
    if (objectUrl) {
      try {
        URL.revokeObjectURL(objectUrl);
      } catch (e) {}
    }
    if (!isBlob && typeof source === "string") {
      callback(source);
    } else {
      callback("");
    }
  };
  img.src = objectUrl || source;
}
window.compressImageToJpeg = compressImageToJpeg;

function renderImagePreviews() {
  if (!imagePreviewBar || !imagePreviewList || !previewCountHint) return;
  if (selectedImages.length === 0) {
    imagePreviewBar.style.display = "none";
    imagePreviewList.innerHTML = "";
    previewCountHint.textContent = "已就绪 0 张图片";
    return;
  }

  imagePreviewBar.style.display = "flex";
  previewCountHint.textContent = `已选 ${selectedImages.length} 张图片`;
  imagePreviewList.innerHTML = "";

  selectedImages.forEach((imgBase64, idx) => {
    const wrap = document.createElement("div");
    wrap.className = "preview-thumbnail-wrap";

    const img = document.createElement("img");
    img.src = imgBase64;
    img.onclick = () => {
      if (lightboxImg && imageLightbox) {
        lightboxImg.src = imgBase64;
        imageLightbox.style.display = "flex";
      }
    };

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "remove-img-btn";
    delBtn.innerHTML = "✕";
    delBtn.title = "移除";
    delBtn.onclick = (e) => {
      e.stopPropagation();
      removeSelectedImage(idx);
    };

    wrap.appendChild(img);
    wrap.appendChild(delBtn);
    imagePreviewList.appendChild(wrap);
  });
}

function removeSelectedImage(index) {
  selectedImages.splice(index, 1);
  renderImagePreviews();
}

function clearAllSelectedImages() {
  selectedImages = [];
  renderImagePreviews();
}

// ================= OpenTavern 格式角色卡管理与随消息发送 =================
const OPENTAVERN_BLANK_DESCRIPTION_TEMPLATE = `角色名称：
性别：
年龄 / 生日：
职业身份：
种族：

一、外貌系统（视觉 + 感官）
颜值（脖子以上）：
身材（脖子以下整体）：
感官细节：
- 声音：
- 气味：
- 触感：
- 小动作 / 身体语言：

二、穿搭系统
日常穿搭：
居家穿搭：
工作/正式场合穿搭：
穿搭备注：

三、性格系统（核心三层 + 情绪触发）
外在性格：
内在性格：
性格内核：
情绪触发器：

四、说话方式（SillyTavern最重要字段）
说话风格总结：
口癖 / 常用表达：
不同情绪下的说话变化：
- 平静/日常：
- 害羞/被戳穿：
- 认真/生气：
- 亲密/撒娇：
- 崩溃/绝望：
- 成长后：

五、背景与动机系统
过往事件：
当前目标（短期 + 长期）：
最大恐惧 / 弱点：
隐藏的秘密：

六、人际关系与对{{user}}的态度
人际关系网：
对{{user}}的称呼（多场景标注）：
对{{user}}的真实情感（外在表现 vs 内心真实）：
关系动态变化：

其他补充
喜欢的事物：
讨厌的事物：
特殊技能 / 能力：
角色弧光潜力：`;

let characterCardsLoaded = false;

async function loadCharacterCards(forceNetwork = false) {
  if (characterCardsLoaded && !forceNetwork) {
    updateCharCardCountBadges();
    return;
  }
  try {
    const res = await fetch("/api/character_cards");
    if (!res.ok) return;
    const data = await res.json();
    allCharacterCards = Array.isArray(data.cards) ? data.cards : [];
    characterCardsLoaded = true;
    updateCharCardCountBadges();
    const pickerModal = document.getElementById("charCardSelectModal");
    if (pickerModal && pickerModal.style.display !== "none") renderCharCardPicker();
    const libModal = document.getElementById("charCardModal");
    if (libModal && libModal.style.display !== "none") renderCharCardLibrary();
  } catch (e) {
    console.error("加载角色卡失败:", e);
  }
}

function updateCharCardCountBadges() {
  const badge = document.getElementById("charCardCountBadge");
  if (badge) {
    badge.textContent =
      selectedCharacterCards.length > 0
        ? `${selectedCharacterCards.length}/${allCharacterCards.length}`
        : String(allCharacterCards.length);
  }
  const pickerSummaryEl = document.getElementById("charCardPickerSelectedSummary");
  if (pickerSummaryEl) {
    pickerSummaryEl.textContent = `已选 ${selectedCharacterCards.length} 张角色卡`;
  }
  const summaryEl = document.getElementById("charCardModalSelectedSummary");
  if (summaryEl) {
    summaryEl.textContent = `共 ${allCharacterCards.length} 张角色卡`;
  }
}

// 底部回复栏入口：仅用于选择角色卡随消息发送
function openCharCardPickerModal() {
  const modal = document.getElementById("charCardSelectModal");
  if (modal) modal.style.display = "flex";
  renderCharCardPicker();
  if (!characterCardsLoaded) loadCharacterCards(true);
}

// 左侧功能栏入口：角色卡设置（新建 / 导入 / 编辑 / 导出 / 删除）
function openCharCardSettingsModal() {
  if (typeof closeMobileSidebar === "function") closeMobileSidebar();
  const mobileMenu = document.getElementById("mobileMoreMenu");
  if (mobileMenu) mobileMenu.style.display = "none";
  const modal = document.getElementById("charCardModal");
  if (modal) modal.style.display = "flex";
  renderCharCardLibrary();
  if (!characterCardsLoaded) loadCharacterCards(true);
}

function openCharCardModal() {
  openCharCardPickerModal();
}

function isCharCardSelected(cardId) {
  return selectedCharacterCards.some((c) => c.id === cardId);
}

function syncPickerCardDomState(cardId) {
  const grid = document.getElementById("charCardPickerGrid");
  if (!grid) return;
  const attached = isCharCardSelected(cardId);
  grid.querySelectorAll(".charcard-lib-item").forEach((el) => {
    if (el.dataset.cardId !== cardId) return;
    el.classList.toggle("attached", attached);
    el.title = attached ? "取消选择" : "选择";
    const btn = el.querySelector(".btn-select-card");
    if (btn) {
      btn.className = `btn btn-xs ${attached ? "btn-secondary" : "btn-primary"} btn-select-card`;
      btn.textContent = attached ? "✓ 已选择" : "选择";
    }
  });
}

function toggleAttachCharCard(cardId) {
  const idx = selectedCharacterCards.findIndex((c) => c.id === cardId);
  if (idx !== -1) {
    const removed = selectedCharacterCards[idx];
    selectedCharacterCards.splice(idx, 1);
    showToast(`已取消：${removed.name || "未命名角色"}`);
  } else {
    const card = allCharacterCards.find((c) => c.id === cardId);
    if (!card) return;
    selectedCharacterCards.push({ ...card });
    showToast(`已选择：${card.name}`);
  }
  renderCharCardPreviews();
  syncPickerCardDomState(cardId);
  updateCharCardCountBadges();
}

function renderCharCardPreviews() {
  const bar = document.getElementById("charCardPreviewBar");
  const listEl = document.getElementById("charCardPreviewList");
  const hintEl = document.getElementById("charCardPreviewCountHint");
  updateCharCardCountBadges();
  if (!bar || !listEl || !hintEl) return;

  if (selectedCharacterCards.length === 0) {
    bar.style.display = "none";
    listEl.innerHTML = "";
    hintEl.textContent = "已选 0 张角色卡";
    return;
  }

  bar.style.display = "flex";
  hintEl.textContent = `已选 ${selectedCharacterCards.length} 张角色卡`;
  listEl.innerHTML = "";

  selectedCharacterCards.forEach((card, idx) => {
    const pill = document.createElement("div");
    pill.className = "charcard-preview-pill";
    pill.title = "重新选择";

    if (card.avatar) {
      const av = document.createElement("img");
      av.src = card.avatar;
      av.decoding = "async";
      av.style.cssText = "width:20px;height:20px;border-radius:50%;object-fit:cover;";
      pill.appendChild(av);
    } else {
      const ic = document.createElement("span");
      ic.textContent = "";
      pill.appendChild(ic);
    }

    const nameSpan = document.createElement("span");
    nameSpan.style.fontWeight = "600";
    nameSpan.textContent = card.name || "未命名角色";
    pill.appendChild(nameSpan);

    pill.onclick = () => {
      openCharCardPickerModal();
    };

    const rmBtn = document.createElement("button");
    rmBtn.type = "button";
    rmBtn.className = "charcard-preview-rm";
    rmBtn.textContent = "✕";
    rmBtn.title = "移除";
    rmBtn.onclick = (e) => {
      e.stopPropagation();
      const removedId = card.id;
      selectedCharacterCards.splice(idx, 1);
      renderCharCardPreviews();
      syncPickerCardDomState(removedId);
    };
    pill.appendChild(rmBtn);
    listEl.appendChild(pill);
  });
}

function clearAllSelectedCharCards() {
  selectedCharacterCards = [];
  renderCharCardPreviews();
  const pickerModal = document.getElementById("charCardSelectModal");
  if (pickerModal && pickerModal.style.display !== "none") renderCharCardPicker();
}

function renderMessageCharCardsList(cards, containerEl) {
  if (!Array.isArray(cards) || cards.length === 0 || !containerEl) return;
  const wrap = document.createElement("div");
  wrap.className = "message-charcards-list";
  wrap.style.cssText = "display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;";

  cards.forEach((c) => {
    if (!c || typeof c !== "object") return;
    const badge = document.createElement("div");
    badge.className = "msg-charcard-badge";
    badge.title = "查看角色卡";

    if (c.avatar) {
      const img = document.createElement("img");
      img.src = c.avatar;
      img.decoding = "async";
      img.style.cssText = "width:28px;height:28px;border-radius:8px;object-fit:cover;flex-shrink:0;";
      badge.appendChild(img);
    } else {
      const icon = document.createElement("span");
      icon.style.fontSize = "18px";
      icon.textContent = "";
      badge.appendChild(icon);
    }

    const info = document.createElement("div");
    info.style.cssText = "display:flex;flex-direction:column;min-width:0;";
    const titleRow = document.createElement("div");
    titleRow.className = "msg-charcard-title";
    titleRow.textContent = `角色卡：${c.name || "未命名角色"}`;
    info.appendChild(titleRow);

    const tags = Array.isArray(c.tags) ? c.tags : [];
    const subRow = document.createElement("div");
    subRow.className = "msg-charcard-sub";
    subRow.textContent = tags.length > 0 ? tags.slice(0, 4).join(" · ") : (c.personality || c.description || "角色卡").slice(0, 36);
    info.appendChild(subRow);

    badge.appendChild(info);
    badge.onclick = (e) => {
      e.stopPropagation();
      openCharCardEditorModal(c);
    };
    wrap.appendChild(badge);
  });

  containerEl.appendChild(wrap);
}

// 渲染底部回复栏的「选择角色卡发送」列表（仅允许选择角色发送，不含新建/编辑/删除等设置项）
function renderCharCardPicker() {
  const grid = document.getElementById("charCardPickerGrid");
  if (!grid) return;

  const q = (document.getElementById("charCardPickerSearchInput")?.value || "").trim().toLowerCase();
  const filtered = allCharacterCards.filter((c) => {
    if (!q) return true;
    const n = (c.name || "").toLowerCase();
    const iden = (c.identity || "").toLowerCase();
    const t = Array.isArray(c.tags) ? c.tags.join(" ").toLowerCase() : "";
    const d = (c.description || "").toLowerCase();
    return n.includes(q) || iden.includes(q) || t.includes(q) || d.includes(q);
  });

  if (filtered.length === 0) {
    grid.innerHTML = `
      <div style="grid-column:1/-1;text-align:center;padding:32px 16px;color:var(--text-dim);border:1px dashed var(--border-color);border-radius:12px;">
        <div style="font-size:32px;margin-bottom:8px;"></div>
        <div style="font-size:14px;font-weight:600;color:var(--text-main);margin-bottom:4px;">${allCharacterCards.length === 0 ? "暂无角色卡" : "无匹配"}</div>
      </div>
    `;
    return;
  }

  const frag = document.createDocumentFragment();
  filtered.forEach((card) => {
    const attached = isCharCardSelected(card.id);
    const isSimple = (card.card_mode || "advanced") === "simple";
    const cardEl = document.createElement("div");
    cardEl.className = `charcard-lib-item ${attached ? "attached" : ""}`;
    cardEl.dataset.cardId = card.id;
    cardEl.style.cursor = "pointer";
    cardEl.title = attached ? "取消选择" : "选择";

    const customMeta = Array.isArray(card.custom_fields)
      ? card.custom_fields
          .filter((f) => f && f.value && String(f.value).trim())
          .slice(0, 3)
          .map((f) => `${f.label || "属性"}: ${String(f.value).trim()}`)
          .join(" · ")
      : "";
    const basicMeta = customMeta || [card.identity, card.gender, card.age].filter(Boolean).join(" · ");
    const tags = Array.isArray(card.tags) ? card.tags : [];
    const tagsHtml =
      tags.length > 0
        ? `<div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:4px;">${tags
            .slice(0, 5)
            .map((t) => `<span class="charcard-lib-tag">${escapeHtml(t)}</span>`)
            .join("")}</div>`
        : "";

    const descPreview = (card.personality || card.description || card.scenario || basicMeta || "暂无描述")
      .replace(/\s+/g, " ")
      .slice(0, 75);

    cardEl.innerHTML = `
      <div>
        <div style="display:flex;gap:10px;align-items:center;">
          <div class="charcard-lib-avatar">
            ${card.avatar ? `<img src="${escapeHtml(card.avatar)}" decoding="async" loading="lazy" style="width:100%;height:100%;object-fit:cover;" />` : ""}
          </div>
          <div style="min-width:0;flex:1;">
            <div style="display:flex;align-items:center;gap:6px;">
              <div style="font-weight:700;font-size:14px;color:var(--text-main);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(
                card.name || "未命名角色"
              )}</div>
              <span class="charcard-lib-tag" style="flex-shrink:0;">${isSimple ? "简易" : "高级"}</span>
            </div>
            ${basicMeta ? `<div style="font-size:11.5px;color:var(--text-dim);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(basicMeta)}</div>` : ""}
            ${tagsHtml}
          </div>
        </div>
        <div style="font-size:12px;color:var(--text-dim);margin-top:8px;line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;">
          ${escapeHtml(descPreview)}
        </div>
      </div>
      <div style="display:flex;gap:6px;align-items:center;padding-top:6px;border-top:1px solid var(--border-color);">
        <button type="button" class="btn btn-xs ${attached ? "btn-secondary" : "btn-primary"} btn-select-card" style="width:100%;">
          ${attached ? "✓ 已选择" : "选择"}
        </button>
      </div>
    `;

    cardEl.onclick = () => toggleAttachCharCard(card.id);
    frag.appendChild(cardEl);
  });
  grid.replaceChildren(frag);
}

// 渲染左侧功能栏「角色卡设置」弹窗中的角色卡管理列表（新建简易卡 / 新建高级卡 / 导入 / 编辑 / 导出 / 删除）
function renderCharCardLibrary() {
  const grid = document.getElementById("charCardLibraryGrid");
  if (!grid) return;

  const q = (document.getElementById("charCardSearchInput")?.value || "").trim().toLowerCase();
  const filtered = allCharacterCards.filter((c) => {
    if (!q) return true;
    const n = (c.name || "").toLowerCase();
    const iden = (c.identity || "").toLowerCase();
    const cfStr = Array.isArray(c.custom_fields)
      ? c.custom_fields.map((f) => `${f.label || ""} ${f.value || ""}`).join(" ").toLowerCase()
      : "";
    const t = Array.isArray(c.tags) ? c.tags.join(" ").toLowerCase() : "";
    const d = (c.description || "").toLowerCase();
    return n.includes(q) || iden.includes(q) || cfStr.includes(q) || t.includes(q) || d.includes(q);
  });

  if (filtered.length === 0) {
    grid.innerHTML = `
      <div style="grid-column:1/-1;text-align:center;padding:36px 16px;color:var(--text-dim);border:1px dashed var(--border-color);border-radius:12px;">
        <div style="font-size:32px;margin-bottom:8px;opacity:0.7;"></div>
        <div style="font-size:14px;font-weight:600;color:var(--text-main);">${allCharacterCards.length === 0 ? "暂无角色卡" : "无匹配"}</div>
      </div>
    `;
    return;
  }

  const frag = document.createDocumentFragment();
  filtered.forEach((card) => {
    const isSimple = (card.card_mode || "advanced") === "simple";
    const cardEl = document.createElement("div");
    cardEl.className = "charcard-lib-item";

    const customMeta = Array.isArray(card.custom_fields)
      ? card.custom_fields
          .filter((f) => f && f.value && String(f.value).trim())
          .slice(0, 3)
          .map((f) => `${f.label || "属性"}: ${String(f.value).trim()}`)
          .join(" · ")
      : "";
    const basicMeta = customMeta || [card.identity, card.gender, card.age].filter(Boolean).join(" · ");
    const tags = Array.isArray(card.tags) ? card.tags : [];
    const tagsHtml =
      tags.length > 0
        ? `<div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:4px;">${tags
            .slice(0, 5)
            .map(
              (t) =>
                `<span class="charcard-lib-tag">${escapeHtml(
                  t
                )}</span>`
            )
            .join("")}</div>`
        : "";

    const descPreview = (card.personality || card.description || card.scenario || basicMeta || "暂无描述")
      .replace(/\s+/g, " ")
      .slice(0, 75);

    cardEl.innerHTML = `
      <div>
        <div style="display:flex;gap:10px;align-items:center;">
          <div class="charcard-lib-avatar">
            ${card.avatar ? `<img src="${escapeHtml(card.avatar)}" decoding="async" loading="lazy" style="width:100%;height:100%;object-fit:cover;" />` : ""}
          </div>
          <div style="min-width:0;flex:1;">
            <div style="display:flex;align-items:center;gap:6px;">
              <div style="font-weight:700;font-size:14px;color:var(--text-main);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(
                card.name || "未命名角色"
              )}</div>
              <span class="charcard-lib-tag" style="flex-shrink:0;">${isSimple ? "简易" : "高级"}</span>
            </div>
            ${basicMeta ? `<div style="font-size:11.5px;color:var(--text-dim);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(basicMeta)}</div>` : ""}
            ${tagsHtml}
          </div>
        </div>
        <div style="font-size:12px;color:var(--text-dim);margin-top:8px;line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;">
          ${escapeHtml(descPreview)}
        </div>
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;padding-top:6px;border-top:1px solid var(--border-color);">
        <button type="button" class="btn btn-xs btn-primary btn-edit-card" style="flex:1;">编辑</button>
        <button type="button" class="btn btn-xs btn-secondary btn-export-card-png" title="导出 PNG">PNG</button>
        <button type="button" class="btn btn-xs btn-secondary btn-export-card" title="导出 JSON">JSON</button>
        <button type="button" class="btn btn-xs btn-secondary btn-del-card" style="color:var(--danger);" title="删除角色卡">删除</button>
      </div>
    `;

    cardEl.querySelector(".btn-edit-card").onclick = () => openCharCardEditorModal(card, card.card_mode || "advanced");
    cardEl.querySelector(".btn-export-card-png").onclick = () => handleExportCharCardPng(card);
    cardEl.querySelector(".btn-export-card").onclick = () => handleExportCharCardJson(card);
    cardEl.querySelector(".btn-del-card").onclick = () => handleDeleteCharCard(card.id, card.name);

    frag.appendChild(cardEl);
  });
  grid.replaceChildren(frag);
}

function addCharEditorCustomField(label = "", value = "", multiline = false, focusLabel = false) {
  const listEl = document.getElementById("charEditCustomFieldsList");
  if (!listEl) return;

  const item = document.createElement("div");
  item.className = "char-custom-field-item";
  item.dataset.multiline = multiline ? "1" : "0";
  item.style.cssText = `display:flex;flex-direction:column;gap:5px;padding:8px 10px;border:1px solid var(--border-color);border-radius:8px;background:var(--bg-input, rgba(255,255,255,0.02));${multiline ? "grid-column:1/-1;" : ""}`;

  const topRow = document.createElement("div");
  topRow.style.cssText = "display:flex;align-items:center;gap:6px;";

  const labelInput = document.createElement("input");
  labelInput.type = "text";
  labelInput.className = "form-input char-custom-field-label";
  labelInput.style.cssText = "flex:1;font-weight:700;font-size:12.5px;padding:3px 7px;height:26px;";
  labelInput.placeholder = "栏位名";
  const rawLabel = label || "";
  labelInput._origRoVal = rawLabel;
  labelInput.value = window.tStr ? window.tStr(rawLabel) : rawLabel;
  labelInput._lastEnRoVal = labelInput.value;
  labelInput.title = "栏位名";

  const toggleBtn = document.createElement("button");
  toggleBtn.type = "button";
  toggleBtn.className = "btn btn-xs btn-secondary";
  toggleBtn.style.cssText = "padding:2px 6px;font-size:11px;flex-shrink:0;";
  toggleBtn.textContent = multiline ? "单行" : "多行";
  toggleBtn.title = "单行/多行";

  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.className = "btn btn-xs btn-secondary";
  delBtn.style.cssText = "padding:2px 6px;font-size:11px;color:var(--danger);flex-shrink:0;";
  delBtn.textContent = "✕";
  delBtn.title = "删除";
  delBtn.onclick = () => item.remove();

  topRow.appendChild(labelInput);
  topRow.appendChild(toggleBtn);
  topRow.appendChild(delBtn);
  item.appendChild(topRow);

  const createValueEl = (isMulti, currentVal) => {
    let valEl;
    if (isMulti) {
      valEl = document.createElement("textarea");
      valEl.className = "form-textarea char-custom-field-value";
      valEl.rows = 2;
      valEl.placeholder = "内容…";
    } else {
      valEl = document.createElement("input");
      valEl.type = "text";
      valEl.className = "form-input char-custom-field-value";
      valEl.placeholder = "内容…";
    }
    valEl.value = currentVal || "";
    return valEl;
  };

  let valueEl = createValueEl(multiline, value);
  item.appendChild(valueEl);

  toggleBtn.onclick = () => {
    const nextMulti = item.dataset.multiline !== "1";
    const curVal = valueEl.value;
    item.dataset.multiline = nextMulti ? "1" : "0";
    item.style.gridColumn = nextMulti ? "1 / -1" : "";
    toggleBtn.textContent = nextMulti ? "单行" : "多行";
    const nextEl = createValueEl(nextMulti, curVal);
    item.replaceChild(nextEl, valueEl);
    valueEl = nextEl;
    if (typeof window.translateSubtree === "function") {
      window.translateSubtree(item);
    }
    valueEl.focus({ preventScroll: true });
  };

  listEl.appendChild(item);
  if (typeof window.translateSubtree === "function") {
    window.translateSubtree(item);
  }
  if (focusLabel) {
    labelInput.focus({ preventScroll: true });
  }
}
window.addCharEditorCustomField = addCharEditorCustomField;

function addCharEditorAlternateGreeting(val = "") {
  const listEl = document.getElementById("charEditGreetingsList");
  if (!listEl) return;
  const row = document.createElement("div");
  row.className = "char-edit-greeting-row";
  row.style.cssText = "display:flex;gap:6px;align-items:flex-start;";

  const ta = document.createElement("textarea");
  ta.className = "form-textarea char-edit-greeting-input";
  ta.rows = 2;
  ta.style.flex = "1";
  ta.placeholder = "备用开场白…";
  ta.value = val || "";

  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.className = "btn btn-xs btn-secondary";
  delBtn.style.color = "#f87171";
  delBtn.textContent = "✕";
  delBtn.title = "删除";
  delBtn.onclick = () => row.remove();

  row.appendChild(ta);
  row.appendChild(delBtn);
  listEl.appendChild(row);
  if (typeof window.translateSubtree === "function") {
    window.translateSubtree(row);
  }
}

function fillOpenTavernBlankDescriptionTemplate(silent = false) {
  const descEl = document.getElementById("charEditDescription");
  if (!descEl) return;
  const activeTpl =
    window.currentAppLang === "en" && window.EN_OPENTAVERN_TEMPLATE
      ? window.EN_OPENTAVERN_TEMPLATE
      : OPENTAVERN_BLANK_DESCRIPTION_TEMPLATE;
  descEl._origZhTemplate = OPENTAVERN_BLANK_DESCRIPTION_TEMPLATE;
  const curTrim = descEl.value.trim();
  const isBlankTpl =
    curTrim === OPENTAVERN_BLANK_DESCRIPTION_TEMPLATE.trim() ||
    (window.EN_OPENTAVERN_TEMPLATE && curTrim === window.EN_OPENTAVERN_TEMPLATE.trim());
  if (!silent && curTrim && !isBlankTpl) {
    descEl.value = curTrim + "\n\n" + activeTpl;
  } else {
    descEl.value = activeTpl;
  }
  if (!silent) {
    showToast("已填入模板");
  }
}

function switchCharEditorMode(mode) {
  const targetMode = mode === "advanced" ? "advanced" : "simple";
  const modeInput = document.getElementById("charEditMode");
  if (modeInput) modeInput.value = targetMode;

  const isCreate = !(document.getElementById("charEditId")?.value || "").trim();
  const titleEl = document.getElementById("charEditorModalTitle");
  if (titleEl && isCreate) {
    titleEl.textContent = "新建角色卡";
  }

  const advSection = document.getElementById("charEditorAdvancedSection");
  if (advSection) {
    advSection.style.display = "flex";
    if (advSection.parentElement && advSection.parentElement.tagName === "DETAILS") {
      advSection.parentElement.open = false;
    }
  }

  const descEl = document.getElementById("charEditDescription");
  if (descEl) {
    descEl.rows = 6;
    descEl.placeholder = "人设描述…";
  }
}

function openCharCardEditorModal(cardOrNull, defaultMode = "simple") {
  const modal = document.getElementById("charCardEditorModal");
  if (!modal) return;

  const isCreate = !cardOrNull;
  const c = cardOrNull || {};
  const mode = isCreate ? (defaultMode === "advanced" ? "advanced" : "simple") : (c.card_mode || "simple");

  const titleEl = document.getElementById("charEditorModalTitle");
  if (titleEl) {
    if (isCreate) {
      titleEl.textContent = "新建角色卡";
    } else {
      titleEl.textContent = `编辑角色卡：${c.name || "未命名角色"}`;
    }
  }

  document.getElementById("charEditId").value = c.id || "";
  document.getElementById("charEditName").value = c.name || "";
  document.getElementById("charEditTags").value = Array.isArray(c.tags) ? c.tags.join(", ") : c.tags || "";

  const cfListEl = document.getElementById("charEditCustomFieldsList");
  if (cfListEl) {
    cfListEl.innerHTML = "";
  }
  const savedFields =
    Array.isArray(c.custom_fields) && c.custom_fields.length > 0
      ? c.custom_fields
      : c.extensions && Array.isArray(c.extensions.custom_fields) && c.extensions.custom_fields.length > 0
      ? c.extensions.custom_fields
      : c.extensions && c.extensions.trpg_workbench && Array.isArray(c.extensions.trpg_workbench.custom_fields)
      ? c.extensions.trpg_workbench.custom_fields
      : [];
  if (Array.isArray(savedFields) && savedFields.length > 0 && typeof addCharEditorCustomField === "function") {
    savedFields.forEach((f) => {
      if (f && typeof f === "object" && (f.label || f.value)) {
        addCharEditorCustomField(f.label || "", f.value || "", Boolean(f.multiline), false);
      }
    });
  }
  let mergedDescription = String(c.description || "").trim();

  const savedLabels =
    (c.field_labels && typeof c.field_labels === "object" ? c.field_labels : null) ||
    (c.extensions && c.extensions.field_labels && typeof c.extensions.field_labels === "object" ? c.extensions.field_labels : null) ||
    {};

  const setEditableLabel = (elId, key, defaultZh) => {
    const el = document.getElementById(elId);
    if (!el) return;
    const rawVal = savedLabels[key] || (key === "description" ? (c.description_label || (c.extensions && c.extensions.description_label)) : "") || defaultZh;
    el._origRoVal = rawVal;
    el.value = window.tStr ? window.tStr(rawVal) : rawVal;
    el._lastEnRoVal = el.value;
  };

  setEditableLabel("charEditLabel_name", "name", "角色名称");
  setEditableLabel("charEditDescLabelInput", "description", "角色设定");
  setEditableLabel("charEditLabel_tags", "tags", "标签");
  setEditableLabel("charEditLabel_personality", "personality", "性格 (Personality)");
  setEditableLabel("charEditLabel_scenario", "scenario", "场景 (Scenario)");
  setEditableLabel("charEditLabel_first_mes", "first_mes", "角色专属开场白 (First Message)");
  setEditableLabel("charEditLabel_alternate_greetings", "alternate_greetings", "备用开场白 (Alternate Greetings)");
  setEditableLabel("charEditLabel_mes_example", "mes_example", "示例对话 (Mes Example)");
  setEditableLabel("charEditLabel_system_prompt", "system_prompt", "角色提示词 (System Prompt)");
  setEditableLabel("charEditLabel_post_history_instructions", "post_history_instructions", "历史后指令 (Post-History Instructions)");
  setEditableLabel("charEditLabel_creator_notes", "creator_notes", "作者备注 (Creator Notes)");
  setEditableLabel("charEditLabel_depth_prompt", "depth_prompt", "深度提示词 (Depth Prompt)");

  const activeTpl =
    window.currentAppLang === "en" && window.EN_OPENTAVERN_TEMPLATE
      ? window.EN_OPENTAVERN_TEMPLATE
      : OPENTAVERN_BLANK_DESCRIPTION_TEMPLATE;
  const descEl = document.getElementById("charEditDescription");
  if (descEl) {
    descEl._origZhTemplate = OPENTAVERN_BLANK_DESCRIPTION_TEMPLATE;
    descEl.value = isCreate
      ? (mode === "advanced" ? activeTpl : "")
      : mergedDescription;
  }
  document.getElementById("charEditPersonality").value = c.personality || "";
  document.getElementById("charEditScenario").value = c.scenario || "";
  document.getElementById("charEditFirstMes").value = c.first_mes || "";
  document.getElementById("charEditMesExample").value = c.mes_example || "";
  document.getElementById("charEditSystemPrompt").value = c.system_prompt || "";
  document.getElementById("charEditPostHistory").value = c.post_history_instructions || "";
  document.getElementById("charEditCreatorNotes").value = c.creator_notes || "";

  const dp = c.depth_prompt || (c.extensions && c.extensions.depth_prompt) || {};
  document.getElementById("charEditDepthPrompt").value = dp.prompt || "";
  document.getElementById("charEditDepthPromptDepth").value = dp.depth !== undefined ? dp.depth : 4;
  document.getElementById("charEditDepthPromptRole").value = dp.role || "system";

  currentCharEditAvatar = c.avatar || "";
  const avPreview = document.getElementById("charEditAvatarPreview");
  if (avPreview) {
    avPreview.innerHTML = currentCharEditAvatar
      ? `<img src="${escapeHtml(currentCharEditAvatar)}" style="width:100%;height:100%;object-fit:cover;" />`
      : "";
  }

  const greetList = document.getElementById("charEditGreetingsList");
  if (greetList) {
    greetList.innerHTML = "";
    const greets = Array.isArray(c.alternate_greetings) ? c.alternate_greetings : [];
    greets.forEach((g) => addCharEditorAlternateGreeting(g));
  }

  const aiPromptEl = document.getElementById("charAiPromptInput");
  if (aiPromptEl) aiPromptEl.value = "";
  charAiAssistImages = [];
  renderCharAiImagePreviews();
  const aiStatusEl = document.getElementById("charAiAssistStatus");
  if (aiStatusEl) {
    aiStatusEl.style.display = "none";
    aiStatusEl.textContent = "";
  }

  switchCharEditorMode(mode);
  if (typeof window.syncAllAiAssistModelSelects === "function") {
    window.syncAllAiAssistModelSelects();
  }
  if (typeof window.translateSubtree === "function") {
    window.translateSubtree(modal);
  }
  modal.style.display = "flex";
}

let charAiAssistImages = [];

function renderCharAiImagePreviews() {
  const bar = document.getElementById("charAiImagePreviewBar");
  const upBtn = document.getElementById("btnCharAiUploadImages");
  if (upBtn) {
    upBtn.innerHTML = charAiAssistImages.length > 0 ? `附带图片 (${charAiAssistImages.length})` : `附带图片`;
  }
  if (!bar) return;
  if (!charAiAssistImages.length) {
    bar.style.display = "none";
    bar.innerHTML = "";
    return;
  }
  bar.style.display = "flex";
  const itemsHtml = charAiAssistImages
    .map(
      (src, idx) => `
      <div class="char-ai-img-thumb-item" style="position:relative;width:54px;height:54px;border-radius:8px;overflow:hidden;border:1px solid rgba(99,102,241,0.45);background:var(--bg-panel);flex-shrink:0;">
        <img src="${escapeHtml(src)}" decoding="async" style="width:100%;height:100%;object-fit:cover;cursor:zoom-in;" onclick="window.openLightbox && window.openLightbox('${escapeJsStrAttr(src)}')" title="点击放大查看参考图 #${idx + 1}" />
        <button type="button" onclick="window.removeCharAiAssistImage(${idx})" title="移除" style="position:absolute;top:2px;right:2px;width:18px;height:18px;border-radius:50%;border:none;background:rgba(15,23,42,0.78);color:#fff;font-size:11px;line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center;padding:0;">✕</button>
      </div>`
    )
    .join("");
  bar.innerHTML = `
    <span style="font-size:12px;color:var(--primary);font-weight:600;">参考图 (${charAiAssistImages.length})</span>
    ${itemsHtml}
    <button type="button" class="btn btn-xs btn-secondary" onclick="window.clearCharAiAssistImages()" style="color:var(--danger);border-color:rgba(239,68,68,0.3);">清空图片</button>
  `;
}

function handleCharAiImageSelect(event) {
  const files = Array.from((event && event.target && event.target.files) || []);
  if (!files.length) return;
  files.forEach((file) => {
    if (!file.type || !file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      compressImageToJpeg(ev.target.result, 1024, 0.82, (compressed) => {
        charAiAssistImages.push(compressed);
        renderCharAiImagePreviews();
      });
    };
    reader.readAsDataURL(file);
  });
  event.target.value = "";
}
window.handleCharAiImageSelect = handleCharAiImageSelect;

function handleCharAiPromptPaste(event) {
  const items = (event.clipboardData || window.clipboardData)?.items;
  if (!items) return;
  let hasImage = false;
  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    if (item.type && item.type.indexOf("image") !== -1) {
      const file = item.getAsFile();
      if (file) {
        hasImage = true;
        const reader = new FileReader();
        reader.onload = (ev) => {
          compressImageToJpeg(ev.target.result, 1024, 0.82, (compressed) => {
            charAiAssistImages.push(compressed);
            renderCharAiImagePreviews();
          });
        };
        reader.readAsDataURL(file);
      }
    }
  }
  if (hasImage) {
    event.preventDefault();
    event.stopPropagation();
    showToast("已粘贴参考图");
  }
}
window.handleCharAiPromptPaste = handleCharAiPromptPaste;

function removeCharAiAssistImage(idx) {
  if (idx >= 0 && idx < charAiAssistImages.length) {
    charAiAssistImages.splice(idx, 1);
    renderCharAiImagePreviews();
  }
}
window.removeCharAiAssistImage = removeCharAiAssistImage;

function clearCharAiAssistImages() {
  charAiAssistImages = [];
  renderCharAiImagePreviews();
}
window.clearCharAiAssistImages = clearCharAiAssistImages;

async function handleCharAiAssistGenerate() {
  const promptEl = document.getElementById("charAiPromptInput");
  const nameEl = document.getElementById("charEditName");
  const statusEl = document.getElementById("charAiAssistStatus");
  const btn = document.getElementById("btnCharAiAssistGenerate");

  const promptText = (promptEl?.value || "").trim();
  const curName = (nameEl?.value || "").trim();
  const hasImages = charAiAssistImages.length > 0;
  if (!promptText && !curName && !hasImages) {
    showToast("请输入人设或上传参考图");
    if (promptEl) promptEl.focus();
    return;
  }

  const card_mode = (document.getElementById("charEditMode")?.value || "simple").trim();
  const use_web_search = Boolean(document.getElementById("charAiWebSearchToggle")?.checked);
  const description_label = (document.getElementById("charEditDescLabelInput")?.value || "").trim() || "背景故事与补充设定";
  const current_custom_fields = [];
  const activeModel =
    document.getElementById("charAiModelSelect")?.value ||
    (typeof window.getPreferredAiAssistModel === "function" ? window.getPreferredAiAssistModel() : "") ||
    (currentChatData && currentChatData.model) ||
    headerModelSelect?.value ||
    settingModel?.value ||
    "";

  const origBtnHtml = btn ? btn.innerHTML : "AI 填充";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = "生成中…";
  }
  if (statusEl) {
    statusEl.style.display = "block";
    statusEl.style.color = "var(--primary)";
    statusEl.textContent = use_web_search && (promptText || curName) ? "检索并生成中…" : "生成中…";
  }

  try {
    const res = await fetch("/api/character_cards/ai_generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: promptText || curName,
        name: curName,
        images: charAiAssistImages,
        card_mode,
        use_web_search,
        custom_fields: current_custom_fields,
        description_label,
        model: activeModel
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "生成失败");

    const cd = data.card_data || {};
    if (cd.name && nameEl) {
      nameEl.value = cd.name;
    }
    if (Array.isArray(cd.tags) && cd.tags.length > 0) {
      const tagsEl = document.getElementById("charEditTags");
      if (tagsEl) tagsEl.value = cd.tags.join(", ");
    } else if (typeof cd.tags === "string" && cd.tags.trim()) {
      const tagsEl = document.getElementById("charEditTags");
      if (tagsEl) tagsEl.value = cd.tags.trim();
    }

    const cfListEl = document.getElementById("charEditCustomFieldsList");
    if (cfListEl) {
      cfListEl.innerHTML = "";
    }

    let finalDescText = cd.description !== undefined ? String(cd.description || "").trim() : "";
    if (Array.isArray(cd.custom_fields) && cd.custom_fields.length > 0) {
      const cfLines = [];
      cd.custom_fields.forEach((f) => {
        if (f && typeof f === "object") {
          const lbl = String(f.label || "").trim();
          const val = String(f.value || "").trim();
          if (lbl && val && !finalDescText.includes(val)) {
            cfLines.push(`【${lbl}】：${val}`);
          }
        }
      });
      if (cfLines.length > 0) {
        finalDescText = finalDescText
          ? `${cfLines.join("\n")}\n\n${finalDescText}`
          : cfLines.join("\n");
      }
    }

    if (finalDescText || cd.description !== undefined) {
      const descEl = document.getElementById("charEditDescription");
      if (descEl) descEl.value = finalDescText;
    }

    if (cd.personality !== undefined) {
      const el = document.getElementById("charEditPersonality");
      if (el) el.value = cd.personality;
    }
    if (cd.scenario !== undefined) {
      const el = document.getElementById("charEditScenario");
      if (el) el.value = cd.scenario;
    }
    if (cd.first_mes !== undefined) {
      const el = document.getElementById("charEditFirstMes");
      if (el) el.value = cd.first_mes;
    }
    if (Array.isArray(cd.alternate_greetings)) {
      const greetList = document.getElementById("charEditGreetingsList");
      if (greetList) {
        greetList.innerHTML = "";
        cd.alternate_greetings.forEach((g) => {
          if (String(g || "").trim()) addCharEditorAlternateGreeting(String(g).trim());
        });
      }
    }
    if (cd.mes_example !== undefined) {
      const el = document.getElementById("charEditMesExample");
      if (el) el.value = cd.mes_example;
    }
    if (cd.system_prompt !== undefined) {
      const el = document.getElementById("charEditSystemPrompt");
      if (el) el.value = cd.system_prompt;
    }
    if (cd.post_history_instructions !== undefined) {
      const el = document.getElementById("charEditPostHistory");
      if (el) el.value = cd.post_history_instructions;
    }
    if (cd.creator_notes !== undefined) {
      const el = document.getElementById("charEditCreatorNotes");
      if (el) el.value = cd.creator_notes;
    }
    if (cd.depth_prompt && typeof cd.depth_prompt === "object") {
      const dpEl = document.getElementById("charEditDepthPrompt");
      if (dpEl && cd.depth_prompt.prompt !== undefined) dpEl.value = cd.depth_prompt.prompt;
    }

    if (statusEl) {
      statusEl.style.color = "#10b981";
      statusEl.textContent = `已填充：${cd.name || promptText || "角色"}，请核对后保存`;
    }
    showToast(`已填充：${cd.name || promptText || "角色"}`);
  } catch (e) {
    if (statusEl) {
      statusEl.style.color = "var(--danger)";
      statusEl.textContent = `生成失败: ${e.message}`;
    }
    showToast("生成失败: " + e.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origBtnHtml;
    }
  }
}
window.handleCharAiAssistGenerate = handleCharAiAssistGenerate;

function handleCharEditAvatarSelect(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (ev) => {
    compressImageToJpeg(ev.target.result, 256, 0.8, (compressed) => {
      currentCharEditAvatar = compressed;
      const avPreview = document.getElementById("charEditAvatarPreview");
      if (avPreview) {
        avPreview.innerHTML = `<img src="${compressed}" decoding="async" style="width:100%;height:100%;object-fit:cover;" />`;
      }
    });
  };
  reader.readAsDataURL(file);
  event.target.value = "";
}

async function handleSaveCharCardFromEditor(attachToInput = false) {
  const id = (document.getElementById("charEditId")?.value || "").trim();
  const card_mode = (document.getElementById("charEditMode")?.value || "simple").trim();
  const name = (document.getElementById("charEditName")?.value || "").trim() || "未命名角色";
  const rawTags = (document.getElementById("charEditTags")?.value || "").trim();
  const tags = rawTags
    ? rawTags
        .replace(/，/g, ",")
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean)
    : [];

  const readPreservedInputZh = (el) => {
    if (!el) return "";
    const cur = String(el.value ?? "");
    if (el._origRoVal !== undefined && (cur === el._lastEnRoVal || cur.trim() === el._lastEnRoVal)) {
      return String(el._origRoVal);
    }
    return cur;
  };

  const custom_fields = Array.from(document.querySelectorAll("#charEditCustomFieldsList .char-custom-field-item"))
    .map((item) => {
      const label = readPreservedInputZh(item.querySelector(".char-custom-field-label")).trim();
      const value = (item.querySelector(".char-custom-field-value")?.value || "").trim();
      const multiline = item.dataset.multiline === "1";
      return { label: label || "未命名栏位", value, multiline };
    })
    .filter((f) => f.label || f.value);

  const getLbl = (elId, defVal) => readPreservedInputZh(document.getElementById(elId)).trim() || defVal;
  const description_label = getLbl("charEditDescLabelInput", "角色设定");
  const field_labels = {
    name: getLbl("charEditLabel_name", "角色名称"),
    description: description_label,
    tags: getLbl("charEditLabel_tags", "标签"),
    personality: getLbl("charEditLabel_personality", "性格 (Personality)"),
    scenario: getLbl("charEditLabel_scenario", "场景 (Scenario)"),
    first_mes: getLbl("charEditLabel_first_mes", "角色专属开场白 (First Message)"),
    alternate_greetings: getLbl("charEditLabel_alternate_greetings", "备用开场白 (Alternate Greetings)"),
    mes_example: getLbl("charEditLabel_mes_example", "示例对话 (Mes Example)"),
    system_prompt: getLbl("charEditLabel_system_prompt", "角色提示词 (System Prompt)"),
    post_history_instructions: getLbl("charEditLabel_post_history_instructions", "历史后指令 (Post-History Instructions)"),
    creator_notes: getLbl("charEditLabel_creator_notes", "作者备注 (Creator Notes)"),
    depth_prompt: getLbl("charEditLabel_depth_prompt", "深度提示词 (Depth Prompt)")
  };

  // 兼容旧字段映射
  const findFieldVal = (kw) => {
    const hit = custom_fields.find((f) => f.label.toLowerCase().includes(kw.toLowerCase()));
    return hit ? hit.value : "";
  };
  const identity = findFieldVal("身份") || findFieldVal("职业") || findFieldVal("identity") || findFieldVal("class");
  const gender = findFieldVal("性别") || findFieldVal("种族") || findFieldVal("gender") || findFieldVal("race");
  const age = findFieldVal("年龄") || findFieldVal("age");

  const alternate_greetings = Array.from(document.querySelectorAll(".char-edit-greeting-input"))
    .map((el) => el.value.trim())
    .filter(Boolean);

  const dpPrompt = (document.getElementById("charEditDepthPrompt")?.value || "").trim();
  const dpDepth = parseInt(document.getElementById("charEditDepthPromptDepth")?.value || "4", 10);
  const dpRole = document.getElementById("charEditDepthPromptRole")?.value || "system";

  const payload = {
    id: id || undefined,
    card_mode,
    name,
    identity,
    gender,
    age,
    custom_fields,
    description_label,
    field_labels,
    tags,
    avatar: currentCharEditAvatar || "",
    description: document.getElementById("charEditDescription")?.value || "",
    personality: document.getElementById("charEditPersonality")?.value || "",
    scenario: document.getElementById("charEditScenario")?.value || "",
    first_mes: document.getElementById("charEditFirstMes")?.value || "",
    alternate_greetings,
    mes_example: document.getElementById("charEditMesExample")?.value || "",
    system_prompt: document.getElementById("charEditSystemPrompt")?.value || "",
    post_history_instructions: document.getElementById("charEditPostHistory")?.value || "",
    creator_notes: document.getElementById("charEditCreatorNotes")?.value || "",
    depth_prompt: {
      prompt: dpPrompt,
      depth: Number.isNaN(dpDepth) ? 4 : Math.max(0, dpDepth),
      role: dpRole
    }
  };

  try {
    const res = await fetch(id ? `/api/character_cards/${encodeURIComponent(id)}` : "/api/character_cards", {
      method: id ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "保存失败");

    allCharacterCards = Array.isArray(data.cards) ? data.cards : allCharacterCards;
    const savedCard = data.card;

    // 同步更新已选列表中同 ID 的角色卡
    const selIdx = selectedCharacterCards.findIndex((c) => c.id === savedCard.id);
    if (selIdx !== -1) {
      selectedCharacterCards[selIdx] = JSON.parse(JSON.stringify(savedCard));
    } else if (attachToInput && savedCard) {
      selectedCharacterCards.push(JSON.parse(JSON.stringify(savedCard)));
    }

    renderCharCardPreviews();
    renderCharCardPicker();
    renderCharCardLibrary();
    updateCharCardCountBadges();

    const editorModal = document.getElementById("charCardEditorModal");
    if (editorModal) editorModal.style.display = "none";

    showToast(`已保存：${savedCard.name}`);
  } catch (e) {
    showToast("保存失败: " + e.message);
  }
}

async function handleDeleteCharCard(cardId, cardName) {
  const confirmed = await showCustomDialog({
    title: "删除角色卡",
    message: `删除「${cardName || "未命名角色"}」？`
  });
  if (!confirmed) return;

  try {
    const res = await fetch(`/api/character_cards/${encodeURIComponent(cardId)}`, { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "删除失败");
    allCharacterCards = Array.isArray(data.cards) ? data.cards : [];
    selectedCharacterCards = selectedCharacterCards.filter((c) => c.id !== cardId);
    renderCharCardPreviews();
    renderCharCardPicker();
    renderCharCardLibrary();
    updateCharCardCountBadges();
    showToast("已删除");
  } catch (e) {
    showToast("删除失败: " + e.message);
  }
}

function handleExportCharCardJson(card) {
  if (!card) return;
  const exportObj = {
    spec: "chara_card_v3",
    spec_version: "3.0",
    data: {
      name: card.name || "Unnamed",
      description: card.description || "",
      personality: card.personality || "",
      scenario: card.scenario || "",
      first_mes: card.first_mes || "",
      mes_example: card.mes_example || "",
      creator_notes: card.creator_notes || "",
      system_prompt: card.system_prompt || "",
      post_history_instructions: card.post_history_instructions || "",
      alternate_greetings: Array.isArray(card.alternate_greetings) ? card.alternate_greetings : [],
      tags: Array.isArray(card.tags) ? card.tags : [],
      creator: "",
      character_version: "1.0",
      extensions: {
        ...(card.extensions || {}),
        card_mode: card.card_mode || "advanced",
        identity: card.identity || "",
        gender: card.gender || "",
        age: card.age || "",
        custom_fields: Array.isArray(card.custom_fields) ? card.custom_fields : [],
        description_label: card.description_label || "",
        field_labels: card.field_labels && typeof card.field_labels === "object" ? card.field_labels : {},
        depth_prompt: card.depth_prompt || { prompt: "", depth: 4, role: "system" },
        trpg_workbench: {
          card_mode: card.card_mode || "advanced",
          identity: card.identity || "",
          gender: card.gender || "",
          age: card.age || "",
          custom_fields: Array.isArray(card.custom_fields) ? card.custom_fields : [],
          description_label: card.description_label || "",
          field_labels: card.field_labels && typeof card.field_labels === "object" ? card.field_labels : {},
          depth_prompt: card.depth_prompt || { prompt: "", depth: 4, role: "system" }
        }
      },
      character_book: card.character_book || undefined
    }
  };
  const blob = new Blob([JSON.stringify(exportObj, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${(card.name || "character_card").replace(/[\\/:*?"<>|]/g, "_")}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  showToast(`已导出：${card.name}.json`);
}

function _crc32Bytes(bytes) {
  let c = -1;
  for (let i = 0; i < bytes.length; i++) {
    c ^= bytes[i];
    for (let k = 0; k < 8; k++) {
      c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
    }
  }
  return (c ^ -1) >>> 0;
}

function _buildPngTextChunk(keyword, text) {
  const enc = new TextEncoder();
  const keyBytes = enc.encode(keyword);
  const valBytes = enc.encode(text);
  const dataLen = keyBytes.length + 1 + valBytes.length;
  const chunk = new Uint8Array(12 + dataLen);
  const view = new DataView(chunk.buffer);
  view.setUint32(0, dataLen, false);
  // "tEXt"
  chunk[4] = 0x74;
  chunk[5] = 0x45;
  chunk[6] = 0x58;
  chunk[7] = 0x74;
  chunk.set(keyBytes, 8);
  chunk[8 + keyBytes.length] = 0;
  chunk.set(valBytes, 8 + keyBytes.length + 1);
  const crc = _crc32Bytes(chunk.subarray(4, 8 + dataLen));
  view.setUint32(8 + dataLen, crc, false);
  return chunk;
}

async function handleExportCharCardPng(card) {
  try {
    const exportObj = {
      spec: "chara_card_v3",
      spec_version: "3.0",
      name: card.name || "未命名角色",
      description: card.description || "",
      personality: card.personality || "",
      scenario: card.scenario || "",
      first_mes: card.first_mes || "",
      mes_example: card.mes_example || "",
      creator_notes: card.creator_notes || "",
      system_prompt: card.system_prompt || "",
      post_history_instructions: card.post_history_instructions || "",
      alternate_greetings: Array.isArray(card.alternate_greetings) ? card.alternate_greetings : [],
      tags: Array.isArray(card.tags) ? card.tags : [],
      data: {
        name: card.name || "未命名角色",
        description: card.description || "",
        personality: card.personality || "",
        scenario: card.scenario || "",
        first_mes: card.first_mes || "",
        mes_example: card.mes_example || "",
        creator_notes: card.creator_notes || "",
        system_prompt: card.system_prompt || "",
        post_history_instructions: card.post_history_instructions || "",
        alternate_greetings: Array.isArray(card.alternate_greetings) ? card.alternate_greetings : [],
        tags: Array.isArray(card.tags) ? card.tags : [],
        character_book: card.character_book || undefined,
        extensions: {
          ...(card.extensions || {}),
          card_mode: card.card_mode || "advanced",
          identity: card.identity || "",
          gender: card.gender || "",
          age: card.age || "",
          custom_fields: Array.isArray(card.custom_fields) ? card.custom_fields : [],
          description_label: card.description_label || "",
          field_labels: card.field_labels && typeof card.field_labels === "object" ? card.field_labels : {},
          depth_prompt: card.depth_prompt || { prompt: "", depth: 4, role: "system" },
          trpg_workbench: {
            card_mode: card.card_mode || "advanced",
            identity: card.identity || "",
            gender: card.gender || "",
            age: card.age || "",
            custom_fields: Array.isArray(card.custom_fields) ? card.custom_fields : [],
            description_label: card.description_label || "",
            field_labels: card.field_labels && typeof card.field_labels === "object" ? card.field_labels : {},
            depth_prompt: card.depth_prompt || { prompt: "", depth: 4, role: "system" }
          }
        }
      }
    };
    const jsonBytes = new TextEncoder().encode(JSON.stringify(exportObj));
    let binStr = "";
    for (let i = 0; i < jsonBytes.length; i++) {
      binStr += String.fromCharCode(jsonBytes[i]);
    }
    const b64Payload = btoa(binStr);

    const canvas = document.createElement("canvas");
    canvas.width = 400;
    canvas.height = 600;
    const ctx = canvas.getContext("2d");

    let drewAvatar = false;
    const avSrc = String(card.avatar || "").trim();
    if (avSrc && (avSrc.startsWith("data:image/") || avSrc.startsWith("/") || avSrc.startsWith("http://") || avSrc.startsWith("https://"))) {
      try {
        const img = new Image();
        if (!avSrc.startsWith("data:")) img.crossOrigin = "anonymous";
        await new Promise((resolve, reject) => {
          img.onload = resolve;
          img.onerror = reject;
          img.src = avSrc;
        });
        ctx.drawImage(img, 0, 0, 400, 600);
        drewAvatar = true;
      } catch (e) {}
    }
    if (!drewAvatar) {
      const grad = ctx.createLinearGradient(0, 0, 400, 600);
      grad.addColorStop(0, "#1e1b4b");
      grad.addColorStop(1, "#0f172a");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, 400, 600);
      ctx.strokeStyle = "#6366f1";
      ctx.lineWidth = 4;
      ctx.strokeRect(18, 18, 364, 564);
      ctx.fillStyle = "#e0e7ff";
      ctx.font = "bold 28px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText((card.name || "Character").slice(0, 14), 200, 290);
      ctx.fillStyle = "#818cf8";
      ctx.font = "16px sans-serif";
      ctx.fillText("TRPG Character Card (V2/V3)", 200, 330);
    }

    const baseBlob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    const baseBuf = new Uint8Array(await baseBlob.arrayBuffer());
    const iendPos = baseBuf.length - 12;
    const chunkChara = _buildPngTextChunk("chara", b64Payload);
    const chunkCcv3 = _buildPngTextChunk("ccv3", b64Payload);

    const finalPng = new Uint8Array(baseBuf.length + chunkChara.length + chunkCcv3.length);
    finalPng.set(baseBuf.subarray(0, iendPos), 0);
    finalPng.set(chunkChara, iendPos);
    finalPng.set(chunkCcv3, iendPos + chunkChara.length);
    finalPng.set(baseBuf.subarray(iendPos), iendPos + chunkChara.length + chunkCcv3.length);

    const outBlob = new Blob([finalPng], { type: "image/png" });
    const url = URL.createObjectURL(outBlob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(card.name || "character_card").replace(/[\\/:*?"<>|]/g, "_")}.png`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    showToast(`已导出：${card.name}.png`);
  } catch (e) {
    showToast(`导出 PNG 失败：${e.message}`, "error");
  }
}

async function handleImportCharCardFiles(event) {
  const files = Array.from(event.target.files || []);
  if (!files.length) return;

  let importedCount = 0;
  for (const f of files) {
    try {
      const fd = new FormData();
      fd.append("file", f);
      const res = await fetch("/api/character_cards/import", {
        method: "POST",
        body: fd
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "导入失败");
      allCharacterCards = Array.isArray(data.cards) ? data.cards : allCharacterCards;
      importedCount++;
    } catch (e) {
      showToast(`导入 ${f.name} 失败: ${e.message}`);
    }
  }

  if (importedCount > 0) {
    renderCharCardPicker();
    renderCharCardLibrary();
    updateCharCardCountBadges();
    showToast(`已导入 ${importedCount} 张角色卡`);
  }
  event.target.value = "";
}

window.openCharCardModal = openCharCardModal;
window.openCharCardPickerModal = openCharCardPickerModal;
window.openCharCardSettingsModal = openCharCardSettingsModal;
window.renderCharCardPicker = renderCharCardPicker;
window.renderCharCardLibrary = renderCharCardLibrary;
window.toggleAttachCharCard = toggleAttachCharCard;
window.clearAllSelectedCharCards = clearAllSelectedCharCards;
window.openCharCardEditorModal = openCharCardEditorModal;
window.switchCharEditorMode = switchCharEditorMode;
window.fillOpenTavernBlankDescriptionTemplate = fillOpenTavernBlankDescriptionTemplate;
window.addCharEditorAlternateGreeting = addCharEditorAlternateGreeting;
window.handleCharEditAvatarSelect = handleCharEditAvatarSelect;
window.handleSaveCharCardFromEditor = handleSaveCharCardFromEditor;
window.handleImportCharCardFiles = handleImportCharCardFiles;

// ================= 快捷检定骰子 =================
function rollDice(count, sides, sendImmediately = false) {
  let total = 0;
  const rolls = [];
  for (let i = 0; i < count; i++) {
    const val = Math.floor(Math.random() * sides) + 1;
    rolls.push(val);
    total += val;
  }
  let rollStr = `【🎲 掷骰 ${count}D${sides}`;
  if (count > 1) rollStr += ` (${rolls.join("+")})`;
  rollStr += ` = ${total}】`;

  if (btnRollD100) {
    btnRollD100.classList.remove("dice-rolling");
    void btnRollD100.offsetWidth;
    btnRollD100.classList.add("dice-rolling");
  }

  if (userInput) {
    const diceRegex = /【🎲\s*掷骰\s*\d+D\d+[^】]*】/;
    if (diceRegex.test(userInput.value)) {
      userInput.value = userInput.value.replace(diceRegex, rollStr);
    } else {
      const trimmed = userInput.value.trimEnd();
      userInput.value = (trimmed ? trimmed + " " : "") + rollStr + " ";
    }
    userInput.dispatchEvent(new Event("input", { bubbles: true }));
    if (sendImmediately) {
      handleSendMessage();
    } else {
      userInput.focus();
      autoResizeTextarea();
    }
  }
}

function autoResizeTextarea() {
  if (!userInput) return;
  const customBase = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--input-box-height")) || 66;
  userInput.style.height = "auto";
  // 手机软键盘弹出时可视高度很小，输入框最多占可视区域 30%，避免把对话区挤没
  const viewH = (window.visualViewport && window.visualViewport.height) || window.innerHeight || 800;
  const maxAllowed = Math.max(Math.min(customBase, 120), Math.min(240, Math.round(viewH * 0.3)));
  const nextH = Math.max(Math.min(customBase, maxAllowed), Math.min(userInput.scrollHeight, maxAllowed));
  userInput.style.height = nextH + "px";
}

// ================= 模型列表拉取、价格展示与同步 =================
let currentPricingFilter = "all";

function cleanModelBaseName(rawStr) {
  return String(rawStr || "")
    .replace(/^\[本地\s*(?:GGUF|Ollama|AI)?\]\s*/i, "")
    .replace(/\s*【本地[^】]*】\s*$/g, "")
    .replace(/^local-(?:gguf|ollama)::/i, "")
    .replace(/\s*\([a-zA-Z0-9_.-]+:[a-zA-Z0-9_.-]+\)\s*$/, "")
    .replace(/\.gguf$/i, "")
    .trim();
}

function extractModelDiffMeta(targetRaw, siblingRawList = []) {
  const cleanName = cleanModelBaseName(targetRaw);
  const lowerClean = cleanName.toLowerCase();
  let maxLcp = 0;

  if (Array.isArray(siblingRawList) && siblingRawList.length > 1) {
    for (const item of siblingRawList) {
      const otherClean = cleanModelBaseName(item);
      const lowerOther = otherClean.toLowerCase();
      if (!otherClean || lowerOther === lowerClean) continue;
      const minLen = Math.min(lowerClean.length, lowerOther.length);
      let i = 0;
      while (i < minLen && lowerClean[i] === lowerOther[i]) {
        i++;
      }
      if (i > maxLcp) maxLcp = i;
    }
  }

  let sharedPrefix = "";
  let uniquePart = cleanName;
  let diffTag = "";

  if (maxLcp >= 8 && maxLcp < cleanName.length) {
    // 回退到最近的分隔符（- _ . / : 空格），保证完整的词块或量化后缀不被截断
    let snapIdx = maxLcp;
    while (snapIdx > 0 && !/[-_./:\s\]】]/.test(cleanName[snapIdx - 1])) {
      snapIdx--;
    }
    if (snapIdx < 4) snapIdx = maxLcp;
    sharedPrefix = cleanName.slice(0, snapIdx);
    uniquePart = cleanName.slice(snapIdx).replace(/^[-_./:\s]+/, "");
    diffTag = uniquePart;
  } else if (cleanName.length > 20) {
    // 单一超长模型名称：提取末尾量化精度或版本标识作为尾标提示
    const quantMatch = cleanName.match(/[-_.:]((?:IQ\d+_[A-Z0-9_]+|Q\d+_[A-Z0-9_]+|fp16|bf16|int8|int4|awq|gptq|exl2|thinking|latest|[0-9]{4,8}|v\d+(?:\.\d+)*))$/i);
    if (quantMatch && quantMatch[1]) {
      diffTag = quantMatch[1];
      const cutPos = cleanName.length - quantMatch[1].length;
      sharedPrefix = cleanName.slice(0, cutPos);
      uniquePart = quantMatch[1];
    } else {
      const parts = cleanName.split(/[-_/:]+/).filter(Boolean);
      if (parts.length >= 3) {
        diffTag = parts.slice(-2).join("-");
        if (diffTag.length > 16) diffTag = parts[parts.length - 1];
      }
    }
  }

  if (diffTag && diffTag.length > 22) {
    const tokens = diffTag.split(/[-_/:]+/).filter(Boolean);
    if (tokens.length >= 2) {
      diffTag = tokens.slice(-2).join("-");
    } else {
      diffTag = "…" + diffTag.slice(-18);
    }
  }

  return {
    cleanName,
    sharedPrefix,
    uniquePart,
    diffTag
  };
}
window.cleanModelBaseName = cleanModelBaseName;
window.extractModelDiffMeta = extractModelDiffMeta;

function formatModelOptionLabel(mId, pricingMap = {}, siblingIds = []) {
  const meta = extractModelDiffMeta(mId, siblingIds);
  const prefixBadge = meta.diffTag && meta.cleanName.length > 16 ? `【${meta.diffTag}】` : "";
  const p = pricingMap[mId];
  if (p && p.short_price) {
    if (p.billing_type === "local") {
      return `${p.name || meta.cleanName || mId}`;
    }
    return `${prefixBadge}${mId} 【API · ${p.short_price}】`;
  }
  const match = mId.match(/^\[([0-9.]+)\/次\]/);
  if (match) {
    return `${prefixBadge}${mId} 【API · $${match[1]}/次】`;
  }
  return `${prefixBadge}${mId}`;
}

function updateSelectedModelPriceHint(modelId) {
  const hintEl = document.getElementById("selectedModelPriceHint");
  if (!hintEl) return;
  if (!modelId) {
    hintEl.innerHTML = `<span style="color:var(--text-dim);">未配置模型</span>`;
    return;
  }
  const pricingMap = availableModelsData?.pricing || {};
  const p = pricingMap[modelId];
  if (p) {
    const descPart = p.description ? `<br><span style="color:var(--text-dim);font-size:12px;">${escapeHtml(p.description)}</span>` : "";
    hintEl.innerHTML = `<b>当前模型 (${escapeHtml(modelId)})：</b> <b class="price-hint-val">${escapeHtml(p.detail_price)}</b>${descPart}`;
  } else {
    hintEl.innerHTML = `<b>当前模型：</b> <code>${escapeHtml(modelId)}</code>`;
  }
}

async function openPricingModal() {
  if (typeof window.openModelSettingsModal === "function") {
    await window.openModelSettingsModal("list");
    return;
  }
  const pm = document.getElementById("pricingModal");
  if (pm) pm.style.display = "flex";
  if (!availableModelsData || !availableModelsData.pricing || Object.keys(availableModelsData.pricing).length === 0) {
    await loadModels(false);
  }
  renderPricingTable();
}

function renderPricingTable() {
  const tbody = document.getElementById("pricingTableBody");
  const countEl = document.getElementById("pricingCountSummary");
  if (!tbody) return;

  const pricingMap = availableModelsData?.pricing || {};
  const models = availableModelsData?.models || Object.keys(pricingMap);
  const searchVal = (document.getElementById("pricingSearchInput")?.value || "").trim().toLowerCase();
  const activeModel = (currentChatData && currentChatData.model) || headerModelSelect?.value || settingModel?.value || "";

  const allIds = Array.from(new Set([...models, ...Object.keys(pricingMap)]));

  const filtered = allIds.filter((mId) => {
    const p = pricingMap[mId] || {};
    const lower = mId.toLowerCase();
    const desc = (p.description || "").toLowerCase();
    const detail = (p.detail_price || "").toLowerCase();
    const isLocal = p.billing_type === "local";

    const isGemini = lower.includes("gemini");
    const isClaude = lower.includes("claude") || lower.includes("sonnet") || lower.includes("opus") || lower.includes("haiku");
    const isDeepSeek = lower.includes("deepseek");

    if (currentPricingFilter === "local" && !isLocal) return false;
    if (currentPricingFilter === "gemini" && !isGemini) return false;
    if (currentPricingFilter === "claude" && !isClaude) return false;
    if (currentPricingFilter === "deepseek" && !isDeepSeek) return false;
    if (currentPricingFilter === "other" && (isGemini || isClaude || isDeepSeek)) return false;
    if (currentPricingFilter === "per_call" && p.billing_type !== "per_call" && !mId.includes("/次]") && !mId.includes("[按次]")) return false;
    if (currentPricingFilter === "token" && p.billing_type !== "token") return false;

    if (searchVal && !lower.includes(searchVal) && !desc.includes(searchVal) && !detail.includes(searchVal)) {
      return false;
    }
    return true;
  });

  if (countEl) {
    countEl.textContent = `共 ${filtered.length} 个模型`;
  }

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:24px;color:var(--text-dim);">暂无模型</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  filtered.forEach((mId) => {
    const p = pricingMap[mId] || {};
    const isLocal = p.billing_type === "local";
    const isPerCall = p.billing_type === "per_call" || mId.includes("/次]") || mId.includes("[按次]");
    const isCurrent = mId === activeModel;

    const tr = document.createElement("tr");
    if (isCurrent) {
      tr.style.background = "rgba(99, 102, 241, 0.14)";
    }

    const tdName = document.createElement("td");
    tdName.innerHTML = `
      <div style="font-weight:600;color:var(--text-main);word-break:break-all;white-space:normal;">
        ${escapeHtml(mId)}
      </div>
      ${p.description ? `<div style="font-size:11.5px;color:var(--text-dim);margin-top:2px;">${escapeHtml(p.description)}</div>` : ""}
    `;

    const tdType = document.createElement("td");
    if (isLocal) {
      tdType.innerHTML = `<span class="pricing-badge pricing-badge-local">本地</span>`;
    } else if (isPerCall) {
      tdType.innerHTML = `<span class="pricing-badge pricing-badge-percall">API 按次</span>`;
    } else {
      tdType.innerHTML = `<span class="pricing-badge pricing-badge-token">API 按量</span>`;
    }

    const tdPrice = document.createElement("td");
    tdPrice.className = isLocal ? "pricing-price-cell pricing-price-local" : (isPerCall ? "pricing-price-cell pricing-price-percall" : "pricing-price-cell pricing-price-token");
    tdPrice.textContent = isLocal ? "本地" : (p.detail_price ? p.detail_price.replace(/^API 按次：|^API 按量：|^按次计费：|^按量Token：/, "") : (p.short_price || "-"));

    const tdAction = document.createElement("td");
    tdAction.style.textAlign = "right";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = isCurrent ? "btn btn-xs btn-secondary" : "btn btn-xs btn-primary";
    btn.textContent = isCurrent ? "✓ 当前" : "选用";
    btn.disabled = isCurrent;
    btn.onclick = async () => {
      await selectModelFromPricingTable(mId);
    };
    tdAction.appendChild(btn);

    tr.appendChild(tdName);
    tr.appendChild(tdType);
    tr.appendChild(tdPrice);
    tr.appendChild(tdAction);
    tbody.appendChild(tr);
  });
}

async function selectModelFromPricingTable(modelId) {
  syncHeaderModelSelect(modelId);
  if (currentChatId) {
    await handleHeaderModelChange();
  }
  await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: modelId })
  });
  renderPricingTable();
  const pm = document.getElementById("pricingModal");
  if (pm) pm.style.display = "none";
  showToast(`已切换模型：${modelId}`);
}

async function loadModels(showToastNotice = false, opts = {}) {
  try {
    if (btnRefreshModels) {
      btnRefreshModels.textContent = "刷新中...";
      btnRefreshModels.disabled = true;
    }

    const res = await fetch("/api/models");
    if (!res.ok) return;
    availableModelsData = await res.json();
    const {
      models = [],
      remote_models = [],
      custom_models = [],
      local_models = [],
      recommendations = [],
      pricing = {},
      current = "",
      normalized_base_url = ""
    } = availableModelsData;

    const mergedCustomModels = Array.from(
      new Set([
        ...(Array.isArray(custom_models) ? custom_models : []),
        ...(Array.isArray(window.globalUserSettings?.custom_models) ? window.globalUserSettings.custom_models : [])
      ])
    ).filter(Boolean);

    if (normalized_base_url && settingBaseUrl && settingBaseUrl.value.trim() && settingBaseUrl.value.trim() !== normalized_base_url) {
      settingBaseUrl.value = normalized_base_url;
    }

    if (headerModelSelect) headerModelSelect.innerHTML = "";
    if (settingModelSelect) settingModelSelect.innerHTML = "";

    const allKnownNamesForDiff = [
      ...mergedCustomModels,
      ...local_models.map((lm) => lm.name || lm.id),
      ...recommendations.map((r) => r.id),
      ...models
    ];

    const customIds = new Set();
    if (mergedCustomModels.length > 0) {
      const grpCustomHeader = document.createElement("optgroup");
      grpCustomHeader.label = "手动添加";
      const grpCustomSetting = document.createElement("optgroup");
      grpCustomSetting.label = "手动添加";

      mergedCustomModels.forEach((cmId) => {
        customIds.add(cmId);
        const meta = extractModelDiffMeta(cmId, mergedCustomModels);
        const prefixBadge = meta.diffTag && meta.cleanName.length > 16 ? `【${meta.diffTag}】` : "";
        const o1 = document.createElement("option");
        o1.value = cmId;
        o1.textContent = `${prefixBadge}${cmId} 【手动添加】`;
        grpCustomHeader.appendChild(o1);

        const o2 = document.createElement("option");
        o2.value = cmId;
        o2.textContent = `${prefixBadge}${cmId} 【手动添加】`;
        grpCustomSetting.appendChild(o2);
      });

      headerModelSelect?.appendChild(grpCustomHeader);
      settingModelSelect?.appendChild(grpCustomSetting);
    }

    const userCfg = window.globalUserSettings || {};
    const effectiveLocalMode = document.getElementById("settingLocalMode")?.value || userCfg.local_mode || "manual";
    const hasConfiguredApi = Boolean(
      (userCfg.base_url || "").trim() ||
      (userCfg.api_key || "").trim() ||
      mergedCustomModels.length > 0 ||
      (effectiveLocalMode === "manual" && (userCfg.local_base_url || "").trim()) ||
      effectiveLocalMode === "auto" ||
      opts?.triggerSource === "refresh_btn"
    );

    const localIds = new Set();
    const localNamePool = local_models.map((x) => x.name || x.id);
    if (local_models.length > 0 && (hasConfiguredApi || effectiveLocalMode === "auto")) {
      const grpLocalHeader = document.createElement("optgroup");
      grpLocalHeader.label = "本地模型";
      const grpLocalSetting = document.createElement("optgroup");
      grpLocalSetting.label = "本地模型";

      local_models.forEach((lm) => {
        localIds.add(lm.id);
        if (customIds.has(lm.id)) return;
        const optLabel = `${lm.name || lm.id}`;
        const o1 = document.createElement("option");
        o1.value = lm.id;
        o1.textContent = optLabel;
        grpLocalHeader.appendChild(o1);

        const o2 = document.createElement("option");
        o2.value = lm.id;
        o2.textContent = optLabel;
        grpLocalSetting.appendChild(o2);
      });

      if (grpLocalHeader.children.length > 0) {
        headerModelSelect?.appendChild(grpLocalHeader);
        settingModelSelect?.appendChild(grpLocalSetting);
      }
    } else {
      local_models.forEach((lm) => localIds.add(lm.id));
    }

    const grpRecHeader = document.createElement("optgroup");
    grpRecHeader.label = "常用 API";
    const grpRecSetting = document.createElement("optgroup");
    grpRecSetting.label = "常用 API";

    const recIds = new Set(customIds);
    recommendations.forEach((r) => {
      if (localIds.has(r.id)) return;
      recIds.add(r.id);
      const opt1 = document.createElement("option");
      opt1.value = r.id;
      opt1.textContent = r.name;
      grpRecHeader.appendChild(opt1);

      const opt2 = document.createElement("option");
      opt2.value = r.id;
      opt2.textContent = r.name;
      grpRecSetting.appendChild(opt2);
    });

    if (grpRecHeader.children.length > 0) {
      headerModelSelect?.appendChild(grpRecHeader);
      settingModelSelect?.appendChild(grpRecSetting);
    }

    const grpGeminiHeader = document.createElement("optgroup");
    grpGeminiHeader.label = "API · Gemini";
    const grpGeminiSetting = document.createElement("optgroup");
    grpGeminiSetting.label = "API · Gemini";

    const grpClaudeHeader = document.createElement("optgroup");
    grpClaudeHeader.label = "API · Claude";
    const grpClaudeSetting = document.createElement("optgroup");
    grpClaudeSetting.label = "API · Claude";

    const grpDeepSeekHeader = document.createElement("optgroup");
    grpDeepSeekHeader.label = "API · DeepSeek";
    const grpDeepSeekSetting = document.createElement("optgroup");
    grpDeepSeekSetting.label = "API · DeepSeek";

    const grpOtherHeader = document.createElement("optgroup");
    grpOtherHeader.label = "API · 其他";
    const grpOtherSetting = document.createElement("optgroup");
    grpOtherSetting.label = "API · 其他";

    models.forEach((mId) => {
      if (recIds.has(mId) || localIds.has(mId)) return;
      const lower = mId.toLowerCase();
      let th = grpOtherHeader;
      let ts = grpOtherSetting;
      if (lower.includes("gemini")) {
        th = grpGeminiHeader;
        ts = grpGeminiSetting;
      } else if (lower.includes("claude") || lower.includes("sonnet") || lower.includes("opus") || lower.includes("haiku")) {
        th = grpClaudeHeader;
        ts = grpClaudeSetting;
      } else if (lower.includes("deepseek")) {
        th = grpDeepSeekHeader;
        ts = grpDeepSeekSetting;
      }

      const labelWithPrice = formatModelOptionLabel(mId, pricing, allKnownNamesForDiff);

      const o1 = document.createElement("option");
      o1.value = mId;
      o1.textContent = labelWithPrice;
      th.appendChild(o1);

      const o2 = document.createElement("option");
      o2.value = mId;
      o2.textContent = labelWithPrice;
      ts.appendChild(o2);
    });

    if (grpGeminiHeader.children.length > 0) {
      headerModelSelect?.appendChild(grpGeminiHeader);
      settingModelSelect?.appendChild(grpGeminiSetting);
    }
    if (grpClaudeHeader.children.length > 0) {
      headerModelSelect?.appendChild(grpClaudeHeader);
      settingModelSelect?.appendChild(grpClaudeSetting);
    }
    if (grpDeepSeekHeader.children.length > 0) {
      headerModelSelect?.appendChild(grpDeepSeekHeader);
      settingModelSelect?.appendChild(grpDeepSeekSetting);
    }
    if (grpOtherHeader.children.length > 0) {
      headerModelSelect?.appendChild(grpOtherHeader);
      settingModelSelect?.appendChild(grpOtherSetting);
    }

    const validModelSet = new Set([...models, ...customIds, ...localIds]);
    const nonLocalModels = models.filter((mId) => !localIds.has(mId));
    let initialModel =
      (currentChatData && currentChatData.model) ||
      settingModel?.value ||
      current ||
      (nonLocalModels.length > 0 ? nonLocalModels[0] : (models[0] || ""));
    if (initialModel && validModelSet.size > 0 && !validModelSet.has(initialModel)) {
      initialModel = models[0] || Array.from(localIds)[0] || Array.from(customIds)[0] || "";
      if (currentChatData && initialModel) {
        currentChatData.model = initialModel;
      }
      if (settingModel && initialModel) {
        settingModel.value = initialModel;
      }
    }
    if (!hasConfiguredApi && localIds.has(initialModel) && !customIds.has(initialModel)) {
      initialModel = "";
    }

    // 当用户在设置中填写了 API 地址并触发自动拉取（或点击刷新）时：
    if (opts && opts.autoFromApiInput) {
      const hasBaseUrl = Boolean((settingBaseUrl?.value || "").trim());
      const hasApiKey = Boolean((settingApiKey?.value || "").trim());
      const effectiveRemoteModels =
        Array.isArray(remote_models) && remote_models.length > 0
          ? remote_models
          : models.filter((mId) => !localIds.has(mId));
      if (effectiveRemoteModels.length > 0) {
        // 成功拉取到该 API 的模型列表：自动切回下拉框并优先选中该 API 的模型
        if (chkCustomModel && chkCustomModel.checked) {
          chkCustomModel.checked = false;
          if (settingModel) settingModel.style.display = "none";
          if (settingModelSelect) settingModelSelect.style.display = "block";
        }
        if (!initialModel || localIds.has(initialModel) || !effectiveRemoteModels.includes(initialModel)) {
          initialModel = effectiveRemoteModels[0];
          if (settingModel) settingModel.value = initialModel;
        }
        showToast(`已获取 ${effectiveRemoteModels.length} 个模型`);
      } else if (hasBaseUrl && (hasApiKey || opts.triggerSource === "refresh_btn")) {
        // 填了 API 地址+密钥（或点了刷新）但接口未返回模型列表：自动展开手动输入框
        if (chkCustomModel && settingModel && settingModelSelect) {
          chkCustomModel.checked = true;
          settingModel.style.display = "block";
          settingModelSelect.style.display = "none";
          if (localIds.has(settingModel.value)) {
            settingModel.value = "";
          }
          if (opts.triggerSource !== "base_url") {
            settingModel.focus();
          }
        }
        const hintEl = document.getElementById("selectedModelPriceHint");
        if (hintEl) {
          hintEl.innerHTML = `<span style="color:#fbbf24;">请手动填写模型 ID</span>`;
        }
        showToast("未获取到模型，请手动填写");
        return;
      }
    }

    if (!initialModel && headerModelSelect && headerModelSelect.options.length === 0) {
      const ph1 = document.createElement("option");
      ph1.value = "";
      ph1.textContent = "未配置模型";
      headerModelSelect.appendChild(ph1);
      if (settingModelSelect) {
        const ph2 = document.createElement("option");
        ph2.value = "";
        ph2.textContent = "未配置模型";
        settingModelSelect.appendChild(ph2);
      }
    }

    syncHeaderModelSelect(initialModel);
    if (typeof window.renderMinimalistModelList === "function") {
      window.renderMinimalistModelList();
    }
    if (typeof window.renderLocalScanResultBox === "function") {
      window.renderLocalScanResultBox();
    }
    if (welcomeBox && welcomeBox.style.display !== "none") {
      renderWelcomeBox();
    }

    if (showToastNotice) {
      showToast(`已刷新（${models.length}）`);
    }
  } catch (err) {
    console.error("加载模型列表失败:", err);
  } finally {
    if (btnRefreshModels) {
      btnRefreshModels.textContent = "刷新列表";
      btnRefreshModels.disabled = false;
    }
  }
}

function syncHeaderModelSelect(modelId) {
  if (!headerModelSelect) return;
  if (!modelId) {
    updateSelectedModelPriceHint("");
    syncAllAiAssistModelSelects();
    return;
  }
  let exists = false;
  for (const opt of headerModelSelect.options) {
    if (opt.value === modelId) {
      exists = true;
      break;
    }
  }
  if (!exists) {
    const opt = document.createElement("option");
    opt.value = modelId;
    opt.textContent = formatModelOptionLabel(modelId, availableModelsData?.pricing || {});
    headerModelSelect.appendChild(opt);
    if (settingModelSelect) {
      const opt2 = document.createElement("option");
      opt2.value = modelId;
      opt2.textContent = opt.textContent;
      settingModelSelect.appendChild(opt2);
    }
  }
  headerModelSelect.value = modelId;
  if (settingModelSelect) settingModelSelect.value = modelId;
  if (settingModel) settingModel.value = modelId;
  updateSelectedModelPriceHint(modelId);
  syncAllAiAssistModelSelects();
}

function getPreferredAiAssistModel() {
  const saved = localStorage.getItem("trpg_ai_assist_model");
  if (saved && headerModelSelect) {
    for (const opt of headerModelSelect.options) {
      if (opt.value === saved) return saved;
    }
  }
  return (
    (currentChatData && currentChatData.model) ||
    headerModelSelect?.value ||
    settingModel?.value ||
    ""
  );
}
window.getPreferredAiAssistModel = getPreferredAiAssistModel;

function syncAllAiAssistModelSelects(overrideModel = "") {
  if (!headerModelSelect) return;
  const targetModel = overrideModel || getPreferredAiAssistModel();
  const optionsHtml = headerModelSelect.innerHTML;
  document.querySelectorAll(".ai-assist-model-select").forEach((sel) => {
    if (optionsHtml && sel.innerHTML !== optionsHtml) {
      sel.innerHTML = optionsHtml;
    }
    if (targetModel) {
      let found = false;
      for (const opt of sel.options) {
        if (opt.value === targetModel) {
          found = true;
          break;
        }
      }
      if (!found) {
        const opt = document.createElement("option");
        opt.value = targetModel;
        opt.textContent = formatModelOptionLabel(targetModel, availableModelsData?.pricing || {});
        sel.appendChild(opt);
      }
      sel.value = targetModel;
    }
  });
}
window.syncAllAiAssistModelSelects = syncAllAiAssistModelSelects;

function handleAiAssistModelChange(modelId) {
  if (!modelId) return;
  localStorage.setItem("trpg_ai_assist_model", modelId);
  syncAllAiAssistModelSelects(modelId);
  showToast(`辅助模型：${modelId}`);
}
window.handleAiAssistModelChange = handleAiAssistModelChange;

// ================= API、代理与全局默认模型数值参数设置 =================
const GLOBAL_PARAM_PAIRS = [
  { key: "temperature", numId: "settingTemperature", rangeId: "settingTemperatureRange", def: 0.68, isFloat: true, digits: 2 },
  { key: "repetition_penalty", numId: "settingRepetitionPenalty", rangeId: "settingRepetitionPenaltyRange", def: 1.05, isFloat: true, digits: 2 },
  { key: "frequency_penalty", numId: "settingFrequencyPenalty", rangeId: "settingFrequencyPenaltyRange", def: 0.05, isFloat: true, digits: 2 },
  { key: "presence_penalty", numId: "settingPresencePenalty", rangeId: "settingPresencePenaltyRange", def: 0.20, isFloat: true, digits: 2 },
  { key: "top_p", numId: "settingTopP", rangeId: "settingTopPRange", def: 0.90, isFloat: true, digits: 2 },
  { key: "top_k", numId: "settingTopK", rangeId: "settingTopKRange", def: 40, isFloat: false },
  { key: "min_p", numId: "settingMinP", rangeId: "settingMinPRange", def: 0.06, isFloat: true, digits: 2 },
  { key: "max_tokens", numId: "settingMaxTokens", rangeId: "settingMaxTokensRange", def: 4096, isFloat: false },
  { key: "context", numId: "settingContextTurns", rangeId: "settingContextTurnsRange", def: 96, isFloat: false },
  { key: "max_context_k", numId: "settingMaxContextK", rangeId: "settingMaxContextKRange", def: 96, isFloat: false },
  { key: "keep_recent_messages", numId: "settingKeepRecent", rangeId: "settingKeepRecentRange", def: 6, isFloat: false },
  { key: "thinking_budget", numId: "settingThinkingBudget", rangeId: "settingThinkingBudgetRange", def: 1024, isFloat: false }
];

let globalParamBindingsInitialized = false;
function initGlobalParamBindings() {
  if (globalParamBindingsInitialized) return;
  globalParamBindingsInitialized = true;

  GLOBAL_PARAM_PAIRS.forEach((p) => {
    const numEl = document.getElementById(p.numId);
    const rangeEl = document.getElementById(p.rangeId);
    if (rangeEl && numEl) {
      rangeEl.addEventListener("input", () => {
        const v = p.isFloat ? parseFloat(rangeEl.value) : parseInt(rangeEl.value, 10);
        numEl.value = p.isFloat ? v.toFixed(p.digits || 2) : v;
        if (p.key === "context") {
          const hint = document.getElementById("settingContextMsgsHint");
          if (hint) hint.textContent = (v || 16) * 2;
        }
      });
      numEl.addEventListener("input", () => {
        const v = p.isFloat ? parseFloat(numEl.value) : parseInt(numEl.value, 10);
        if (!Number.isNaN(v)) {
          rangeEl.value = v;
          if (p.key === "context") {
            const hint = document.getElementById("settingContextMsgsHint");
            if (hint) hint.textContent = v * 2;
          }
        }
      });
    }
  });

  const ctxModeSelect = document.getElementById("settingContextMode");
  const syncGlobalCtxModeUi = () => {
    const grp = document.getElementById("settingContextTurnsGroup");
    if (grp && ctxModeSelect) {
      const isTok = ctxModeSelect.value === "tokens";
      grp.style.opacity = isTok ? "0.45" : "1";
      grp.style.pointerEvents = isTok ? "none" : "auto";
    }
  };
  ctxModeSelect?.addEventListener("change", syncGlobalCtxModeUi);

  const btnResetGlobal = document.getElementById("btnResetGlobalParams");
  btnResetGlobal?.addEventListener("click", () => {
    GLOBAL_PARAM_PAIRS.forEach((p) => {
      const numEl = document.getElementById(p.numId);
      const rangeEl = document.getElementById(p.rangeId);
      if (numEl) numEl.value = p.isFloat ? p.def.toFixed(p.digits || 2) : p.def;
      if (rangeEl) rangeEl.value = p.def;
    });
    if (ctxModeSelect) {
      ctxModeSelect.value = "turns";
      syncGlobalCtxModeUi();
    }
    const hint = document.getElementById("settingContextMsgsHint");
    if (hint) hint.textContent = 128;
    const autoSumEl = document.getElementById("settingAutoSummarize");
    if (autoSumEl) autoSumEl.checked = true;
    showToast("已恢复默认");
  });

  const btnSyncAll = document.getElementById("btnSyncGlobalParamsToProjects");
  btnSyncAll?.addEventListener("click", async () => {
    const payload = collectSettingsPayload();
    try {
      const res = await fetch("/api/settings/sync_params_to_projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "同步失败");
      window.globalUserSettings = data.settings || { ...(window.globalUserSettings || {}), ...payload };
      await loadProjects();
      updateContextProgressUI();
      if (typeof window.renderStudioWorkbench === "function") {
        window.renderStudioWorkbench();
      }
      showToast(`已同步 ${data.updated_count || 0} 个剧本`);
    } catch (err) {
      showToast("同步失败: " + err.message);
    }
  });
}

function populateGlobalParamInputs(s) {
  initGlobalParamBindings();
  const overrideInfo = typeof window.getActiveModelParamOverrideInfo === "function"
    ? window.getActiveModelParamOverrideInfo()
    : { activeModel: "", hasOverride: false, params: {} };
  const hasOverride = overrideInfo.hasOverride;
  const mParams = overrideInfo.params || {};

  GLOBAL_PARAM_PAIRS.forEach((p) => {
    const rawVal = hasOverride && mParams[p.key] !== undefined
      ? mParams[p.key]
      : (p.key === "context" ? (s.context ?? s.max_context_turns ?? p.def) : (s[p.key] ?? p.def));
    const val = p.isFloat ? parseFloat(rawVal) : parseInt(rawVal, 10);
    const safeVal = Number.isNaN(val) ? p.def : val;
    const numEl = document.getElementById(p.numId);
    const rangeEl = document.getElementById(p.rangeId);
    if (numEl) numEl.value = p.isFloat ? safeVal.toFixed(p.digits || 2) : safeVal;
    if (rangeEl) rangeEl.value = safeVal;
    if (p.key === "context") {
      const hint = document.getElementById("settingContextMsgsHint");
      if (hint) hint.textContent = safeVal * 2;
    }
  });
  const ctxModeSelect = document.getElementById("settingContextMode");
  if (ctxModeSelect) {
    ctxModeSelect.value = s.context_mode === "tokens" ? "tokens" : "turns";
    const grp = document.getElementById("settingContextTurnsGroup");
    if (grp) {
      const isTok = ctxModeSelect.value === "tokens";
      grp.style.opacity = isTok ? "0.45" : "1";
      grp.style.pointerEvents = isTok ? "none" : "auto";
    }
  }
  const autoSumEl = document.getElementById("settingAutoSummarize");
  if (autoSumEl) autoSumEl.checked = s.auto_summarize !== false;
  const globalProtoEl = document.getElementById("settingGlobalSystemProtocolPrompt");
  if (globalProtoEl) {
    const rawProto = (s.global_system_protocol_prompt !== undefined && s.global_system_protocol_prompt !== null)
      ? String(s.global_system_protocol_prompt)
      : "";
    globalProtoEl.value = typeof window.upgradeLegacyGlobalProtocolPrompt === "function"
      ? window.upgradeLegacyGlobalProtocolPrompt(rawProto, true)
      : rawProto;
  }
  syncGlobalParamsOverrideUI(s);
}

function syncGlobalParamsOverrideUI(baseSettings) {
  const s = baseSettings || window.globalUserSettings || {};
  const overrideInfo = typeof window.getActiveModelParamOverrideInfo === "function"
    ? window.getActiveModelParamOverrideInfo()
    : { activeModel: "", hasOverride: false, params: {} };
  const hasOverride = overrideInfo.hasOverride;
  const activeModel = overrideInfo.activeModel || "";
  const mParams = overrideInfo.params || {};

  const badgeEl = document.getElementById("globalParamsModelOverrideBadge");
  const headerActionsEl = document.getElementById("globalParamsHeaderActions");
  const bannerEl = document.getElementById("globalParamsModelOverrideBanner");
  const bodyEl = document.getElementById("globalParamsBody");
  const ctxBodyEl = document.getElementById("globalParamsContextBody");

  if (badgeEl) {
    badgeEl.style.display = hasOverride ? "inline-flex" : "none";
    badgeEl.textContent = hasOverride ? `已锁定 (${activeModel})` : "已锁定";
  }
  if (headerActionsEl) {
    headerActionsEl.style.opacity = hasOverride ? "0.4" : "1";
    headerActionsEl.style.pointerEvents = hasOverride ? "none" : "auto";
  }
  if (bannerEl) {
    if (hasOverride) {
      const safeModelAttr = activeModel.replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/"/g, "&quot;");
      const safeModelHtml = activeModel.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      bannerEl.style.display = "flex";
      bannerEl.innerHTML = `
        <div style="flex:1; min-width:220px;">
          <div style="font-size:12.5px; font-weight:700; color:#fbbf24; margin-bottom:3px;">「${safeModelHtml}」使用独立参数</div>
        </div>
        <div style="display:flex; gap:6px; flex-shrink:0; flex-wrap:wrap;">
          <button type="button" class="btn secondary small" onclick="window.jumpToActiveModelParams('${safeModelAttr}')" style="font-size:11.5px; padding:5px 10px; border-color:rgba(245,158,11,0.5); color:#fde68a; background:rgba(245,158,11,0.15);">去修改</button>
          <button type="button" class="btn secondary small" onclick="window.disableActiveModelParamsOverride('${safeModelAttr}')" style="font-size:11.5px; padding:5px 10px;">停用</button>
        </div>
      `;
    } else {
      bannerEl.style.display = "none";
      bannerEl.innerHTML = "";
    }
  }

  [bodyEl, ctxBodyEl].forEach((container) => {
    if (!container) return;
    container.style.opacity = hasOverride ? "0.45" : "1";
    container.style.pointerEvents = hasOverride ? "none" : "auto";
    container.style.filter = hasOverride ? "grayscale(0.65)" : "none";
    container.querySelectorAll("input, select, button").forEach((ctrl) => {
      ctrl.disabled = hasOverride;
    });
  });

  GLOBAL_PARAM_PAIRS.forEach((p) => {
    const rawVal = hasOverride && mParams[p.key] !== undefined
      ? mParams[p.key]
      : (p.key === "context" ? (s.context ?? s.max_context_turns ?? p.def) : (s[p.key] ?? p.def));
    const val = p.isFloat ? parseFloat(rawVal) : parseInt(rawVal, 10);
    const safeVal = Number.isNaN(val) ? p.def : val;
    const numEl = document.getElementById(p.numId);
    const rangeEl = document.getElementById(p.rangeId);
    if (numEl) numEl.value = p.isFloat ? safeVal.toFixed(p.digits || 2) : safeVal;
    if (rangeEl) rangeEl.value = safeVal;
    if (p.key === "context") {
      const hint = document.getElementById("settingContextMsgsHint");
      if (hint) hint.textContent = safeVal * 2;
    }
  });
}
window.syncGlobalParamsOverrideUI = syncGlobalParamsOverrideUI;

function handleLocalModeChange(mode) {
  const sel = document.getElementById("settingLocalMode");
  const effectiveMode = mode || sel?.value || "auto";
  const autoRow = document.getElementById("localAutoHintRow");
  const manualRow = document.getElementById("localManualConfigRow");
  const isManual = effectiveMode === "manual";
  if (autoRow) autoRow.style.display = isManual ? "none" : "block";
  if (manualRow) manualRow.style.display = isManual ? "block" : "none";
}
window.handleLocalModeChange = handleLocalModeChange;

function collectSettingsPayload() {
  const chosenModel =
    (chkCustomModel?.checked ? settingModel?.value.trim() : settingModelSelect?.value) ||
    headerModelSelect?.value ||
    window.globalUserSettings?.model ||
    "";
  const ctxModeSelect = document.getElementById("settingContextMode");
  const localModeSelect = document.getElementById("settingLocalMode");
  const localBaseUrlInput = document.getElementById("settingLocalBaseUrl");
  const localModelInput = document.getElementById("settingLocalModel");
  const manualProtoSelect = document.getElementById("manualApiProtocolSelect");
  const existingCustomModels = Array.isArray(window.globalUserSettings?.custom_models)
    ? window.globalUserSettings.custom_models.filter(Boolean)
    : [];
  if (chkCustomModel?.checked && chosenModel && !existingCustomModels.includes(chosenModel)) {
    existingCustomModels.unshift(chosenModel);
  }
  const guiOrientInput = document.getElementById("settingGuiOrientation");
  const globalProtoModalEl = document.getElementById("settingGlobalSystemProtocolPrompt");
  const globalProtoStEl = document.getElementById("stGlobalSystemProtocolPrompt");
  const isSettingsOpen = Boolean(
    settingsModal &&
    (settingsModal.classList.contains("active") || settingsModal.style.display === "flex" || settingsModal.style.display === "block")
  );
  const activeProjObj = (typeof projectsMap === "object" && projectsMap && currentProjectId) ? projectsMap[currentProjectId] : null;
  const activeIsFreeChat = Boolean(activeProjObj && typeof window.isFreeChatProject === "function" && window.isFreeChatProject(activeProjObj));
  let globalProtoVal = "";
  if (isSettingsOpen && globalProtoModalEl) {
    globalProtoVal = String(globalProtoModalEl.value ?? "").trim();
  } else if (globalProtoStEl && !activeIsFreeChat) {
    globalProtoVal = String(globalProtoStEl.value ?? "").trim();
  } else if (globalProtoModalEl) {
    globalProtoVal = String(globalProtoModalEl.value ?? "").trim();
  } else if (window.globalUserSettings && window.globalUserSettings.global_system_protocol_prompt !== undefined && window.globalUserSettings.global_system_protocol_prompt !== null) {
    globalProtoVal = String(window.globalUserSettings.global_system_protocol_prompt).trim();
  }
  const payload = {
    api_protocol: manualProtoSelect?.value || window.globalUserSettings?.api_protocol || "auto",
    base_url: settingBaseUrl?.value.trim() || "",
    api_key: settingApiKey?.value.trim() || "",
    model: chosenModel || "",
    custom_models: existingCustomModels,
    local_mode: localModeSelect?.value === "manual" ? "manual" : "auto",
    local_base_url: localBaseUrlInput?.value.trim() || "",
    local_model: localModelInput?.value.trim() || "",
    proxy: settingProxy?.value.trim() || "",
    use_proxy: !!settingUseProxy?.checked,
    gui_orientation: guiOrientInput?.value === "portrait" ? "portrait" : (typeof window.getGuiOrientation === "function" ? window.getGuiOrientation() : "landscape"),
    context_mode: ctxModeSelect?.value === "tokens" ? "tokens" : "turns",
    auto_summarize: document.getElementById("settingAutoSummarize") ? !!document.getElementById("settingAutoSummarize").checked : true,
    global_system_protocol_prompt: globalProtoVal,
    model_params: (window.globalUserSettings && window.globalUserSettings.model_params) || {}
  };
  const overrideInfo = typeof window.getActiveModelParamOverrideInfo === "function"
    ? window.getActiveModelParamOverrideInfo()
    : { hasOverride: false };
  GLOBAL_PARAM_PAIRS.forEach((p) => {
    if (overrideInfo.hasOverride && window.globalUserSettings && window.globalUserSettings[p.key] !== undefined) {
      payload[p.key] = window.globalUserSettings[p.key];
      return;
    }
    const numEl = document.getElementById(p.numId);
    const raw = numEl ? (p.isFloat ? parseFloat(numEl.value) : parseInt(numEl.value, 10)) : p.def;
    payload[p.key] = Number.isNaN(raw) ? p.def : raw;
  });
  payload.max_context_turns = payload.context;
  return payload;
}

// ================= 手动添加 API 与模型独立窗口 (#manualApiModal) =================
function handleManualProtocolChange(protoVal) {
  const proto = (protoVal || document.getElementById("manualApiProtocolSelect")?.value || "auto").trim().toLowerCase();
  const hintEl = document.getElementById("manualApiProtocolHint");
  const bInp = document.getElementById("manualApiBaseUrl");
  const modal = document.getElementById("manualApiModal");

  const hintMap = {
    auto: "按地址或 Key 自动识别",
    openai: "OpenAI 兼容接口",
    gemini: "地址可留空",
    claude: "地址可留空",
    ollama: "默认本机 11434"
  };
  const placeholderMap = {
    auto: "https://api.xxx.com/v1",
    openai: "https://api.xxx.com/v1",
    gemini: "可留空",
    claude: "可留空",
    ollama: "可留空"
  };

  if (hintEl) {
    const zhHint = hintMap[proto] || hintMap.auto;
    hintEl.textContent = window.tStr ? window.tStr(zhHint) : zhHint;
  }
  if (bInp) {
    const zhPh = placeholderMap[proto] || placeholderMap.auto;
    bInp.setAttribute("data-orig-placeholder", zhPh);
    bInp.placeholder = window.tStr ? window.tStr(zhPh) : zhPh;
  }
  if (modal && typeof window.translateSubtree === "function") {
    window.translateSubtree(modal);
  }
}
window.handleManualProtocolChange = handleManualProtocolChange;

function renderManualSavedModelsList() {
  const sec = document.getElementById("manualSavedModelsSection");
  const listEl = document.getElementById("manualSavedModelsList");
  const minWrap = document.getElementById("minimalistSavedCustomModelsWrap");
  const savedList = Array.isArray(window.globalUserSettings?.custom_models)
    ? window.globalUserSettings.custom_models.filter(Boolean)
    : [];

  if (minWrap) {
    minWrap.innerHTML = "";
    savedList.forEach((mId) => {
      const pill = document.createElement("div");
      pill.style.cssText =
        "display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;background:rgba(16,185,129,0.14);border:1px solid rgba(16,185,129,0.4);color:#34d399;font-size:12px;font-weight:600;cursor:pointer;";
      const span = document.createElement("span");
      span.textContent = mId;
      span.onclick = () => window.selectModelFromMinimalistList(mId);
      const delBtn = document.createElement("span");
      delBtn.textContent = "✕";
      delBtn.title = "移除";
      delBtn.style.cssText = "color:#f87171;font-weight:700;padding:0 2px;cursor:pointer;";
      delBtn.onclick = async (e) => {
        e.stopPropagation();
        await removeSavedCustomModel(mId);
      };
      pill.appendChild(span);
      pill.appendChild(delBtn);
      minWrap.appendChild(pill);
    });
  }

  if (!sec || !listEl) return;
  if (savedList.length === 0) {
    sec.style.display = "none";
    listEl.innerHTML = "";
    return;
  }
  sec.style.display = "block";
  listEl.innerHTML = "";
  savedList.forEach((mId) => {
    const pill = document.createElement("div");
    pill.style.cssText =
      "display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;background:rgba(16,185,129,0.14);border:1px solid rgba(16,185,129,0.4);color:#34d399;font-size:12px;font-weight:600;cursor:pointer;";
    const span = document.createElement("span");
    span.textContent = mId;
    span.onclick = () => {
      const mInp = document.getElementById("manualApiModelId");
      if (mInp) mInp.value = mId;
    };
    const delBtn = document.createElement("span");
    delBtn.textContent = "✕";
    delBtn.title = "移除";
    delBtn.style.cssText = "color:#f87171;font-weight:700;padding:0 2px;cursor:pointer;";
    delBtn.onclick = async (e) => {
      e.stopPropagation();
      await removeSavedCustomModel(mId);
    };
    pill.appendChild(span);
    pill.appendChild(delBtn);
    listEl.appendChild(pill);
  });
}

async function removeSavedCustomModel(mId) {
  if (!window.globalUserSettings) window.globalUserSettings = {};
  const cur = Array.isArray(window.globalUserSettings.custom_models) ? window.globalUserSettings.custom_models : [];
  window.globalUserSettings.custom_models = cur.filter((x) => x !== mId);
  renderManualSavedModelsList();
  try {
    const payload = collectSettingsPayload();
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    await loadModels(false);
  } catch (e) {}
}
window.removeSavedCustomModel = removeSavedCustomModel;

function openManualApiModal() {
  if (typeof window.openModelSettingsModal === "function") {
    window.openModelSettingsModal("api");
    return;
  }
}
window.openManualApiModal = openManualApiModal;

function toggleManualApiKeyVis() {
  const kInp = document.getElementById("manualApiKeyInput");
  if (!kInp) return;
  kInp.type = kInp.type === "password" ? "text" : "password";
}
window.toggleManualApiKeyVis = toggleManualApiKeyVis;

function toggleSettingApiKeyVis() {
  if (!settingApiKey) return;
  settingApiKey.type = settingApiKey.type === "password" ? "text" : "password";
}
window.toggleSettingApiKeyVis = toggleSettingApiKeyVis;

async function handleManualModalFetchModels() {
  await window.saveMinimalistApiConfig();
}
window.handleManualModalFetchModels = handleManualModalFetchModels;

async function handleSaveManualApiAndModel() {
  await window.saveMinimalistApiConfig();
}
window.handleSaveManualApiAndModel = handleSaveManualApiAndModel;

async function loadSettings() {
  try {
    initGlobalParamBindings();
    const res = await fetch("/api/settings");
    if (!res.ok) return;
    const s = await res.json();
    const hasCustomOrApi = Boolean(
      (s.base_url || "").trim() ||
      (s.api_key || "").trim() ||
      (Array.isArray(s.custom_models) && s.custom_models.length > 0) ||
      (s.local_base_url || "").trim()
    );
    let dirtySettings = false;
    if (s.active_project_id && LEGACY_PRESET_PROJECT_IDS.has(s.active_project_id)) {
      s.active_project_id = "proj_default";
      dirtySettings = true;
    }
    if (!hasCustomOrApi && s.model === "dongfangshuo-v3:direct") {
      s.model = "";
      dirtySettings = true;
    }
    if (dirtySettings) {
      fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active_project_id: s.active_project_id, model: s.model })
      }).catch(() => {});
    }
    window.globalUserSettings = s;
    // 界面方向为本机独立偏好（localStorage），不再使用服务器端 gui_orientation 覆盖，避免多设备互相干扰
    if (typeof window.setGuiOrientation === "function") {
      window.setGuiOrientation("auto", true);
    }
    if (settingBaseUrl) settingBaseUrl.value = s.base_url || "";
    if (settingApiKey) settingApiKey.value = s.api_key || "";
    if (settingModel) settingModel.value = s.model || "";
    if (settingProxy) settingProxy.value = s.proxy || "";
    if (settingUseProxy) settingUseProxy.checked = !!s.use_proxy;
    const localModeSelect = document.getElementById("settingLocalMode");
    const localBaseUrlInput = document.getElementById("settingLocalBaseUrl");
    const localModelInput = document.getElementById("settingLocalModel");
    const lMode = s.local_mode === "auto" ? "auto" : "manual";
    if (localModeSelect) localModeSelect.value = lMode;
    if (localBaseUrlInput) localBaseUrlInput.value = s.local_base_url || "";
    if (localModelInput) localModelInput.value = s.local_model || "";
    handleLocalModeChange(lMode);
    populateGlobalParamInputs(s);
    renderManualSavedModelsList();
    if (s.active_project_id) {
      currentProjectId = s.active_project_id;
    }
    syncHeaderModelSelect(s.model);
    updateContextProgressUI();
  } catch (err) {
    console.error("加载设置失败:", err);
  }
}

function openSettingsModal() {
  if (settingsModal) settingsModal.style.display = "flex";
  loadSettings();
  loadNetworkInfoIntoSettings();
  loadBackupOverview();
}

async function loadNetworkInfoIntoSettings() {
  try {
    const res = await fetch("/api/network_info");
    const data = await res.json();
    if (remotePublicUrl) {
      const rawPub = data.public_url || "未检测到公网隧道";
      remotePublicUrl._origRoVal = rawPub;
      remotePublicUrl.value = window.tStr ? window.tStr(rawPub) : rawPub;
      remotePublicUrl._lastEnRoVal = remotePublicUrl.value;
    }
    if (remoteLanUrl) remoteLanUrl.value = data.lan_url || "http://127.0.0.1:8765";
    if (remoteLocalUrl) remoteLocalUrl.value = data.local_url || "http://127.0.0.1:8765";
  } catch (e) {
    console.error("获取网络信息失败:", e);
  }
}

async function handleSaveSettings() {
  const payload = collectSettingsPayload();

  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const out = await res.json();
    window.globalUserSettings = out.settings || payload;
    if (settingModel) settingModel.value = payload.model;
    await loadModels(false);
    syncHeaderModelSelect(payload.model);
    updateContextProgressUI();
    if (settingsModal) settingsModal.style.display = "none";
    showToast("已保存");
  } catch (err) {
    showToast("保存设置失败: " + err);
  }
}

// ================= 极简模型设置弹窗 (#modelSettingsModal：模型列表 / 本地 / API + 最高优先级单模型独立参数) =================
let currentEditingPerModelId = "";
const PER_MODEL_PARAM_FIELDS = [
  { key: "temperature", id: "pm_temperature", rangeId: "pm_temperature_range", def: 0.68, isFloat: true, digits: 2 },
  { key: "top_p", id: "pm_top_p", rangeId: "pm_top_p_range", def: 0.90, isFloat: true, digits: 2 },
  { key: "top_k", id: "pm_top_k", rangeId: "pm_top_k_range", def: 40, isFloat: false },
  { key: "min_p", id: "pm_min_p", rangeId: "pm_min_p_range", def: 0.06, isFloat: true, digits: 2 },
  { key: "repetition_penalty", id: "pm_repetition_penalty", rangeId: "pm_repetition_penalty_range", def: 1.05, isFloat: true, digits: 2 },
  { key: "frequency_penalty", id: "pm_frequency_penalty", rangeId: "pm_frequency_penalty_range", def: 0.05, isFloat: true, digits: 2 },
  { key: "presence_penalty", id: "pm_presence_penalty", rangeId: "pm_presence_penalty_range", def: 0.20, isFloat: true, digits: 2 },
  { key: "max_tokens", id: "pm_max_tokens", rangeId: "pm_max_tokens_range", def: 4096, isFloat: false },
  { key: "context", id: "pm_context", rangeId: "pm_context_range", def: 96, isFloat: false },
  { key: "max_context_k", id: "pm_max_context_k", rangeId: "pm_max_context_k_range", def: 96, isFloat: false },
  { key: "thinking_budget", id: "pm_thinking_budget", rangeId: "pm_thinking_budget_range", def: 1024, isFloat: false }
];

let _hfStatusPollTimer = null;
window.localModelsManagerData = null;

async function openModelSettingsModal(defaultTab = "list") {
  const modal = document.getElementById("modelSettingsModal");
  if (!modal) return;
  modal.style.display = "flex";
  await loadSettings();
  switchModelSettingsTab(defaultTab || "list");
  if (!availableModelsData || !Array.isArray(availableModelsData.models)) {
    await loadModels(false);
  } else {
    renderMinimalistModelList();
    renderLocalScanResultBox();
  }
  loadLocalModelsManagerStatus(false);
  renderManualSavedModelsList();
  if (typeof window.translateSubtree === "function") {
    window.translateSubtree(modal);
  }
}
window.openModelSettingsModal = openModelSettingsModal;

function switchModelSettingsTab(tab) {
  const target = ["list", "local", "hf", "api"].includes(tab) ? tab : "list";
  ["list", "local", "hf", "api"].forEach((t) => {
    const btn = document.getElementById(`modelTabBtn_${t}`);
    const pane = document.getElementById(`modelTabPane_${t}`);
    if (btn) btn.classList.toggle("active", t === target);
    if (pane) pane.style.display = t === target ? "flex" : "none";
  });
  if (target === "list") {
    closePerModelParamsEditor();
    renderMinimalistModelList();
  } else if (target === "local") {
    renderLocalScanResultBox();
    loadLocalModelsManagerStatus(false);
  } else if (target === "hf") {
    loadLocalModelsManagerStatus(false);
  } else if (target === "api") {
    renderManualSavedModelsList();
  }
}
window.switchModelSettingsTab = switchModelSettingsTab;

async function refreshMinimalistModelList() {
  const btn = document.getElementById("btnMinimalistRefreshModels");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "检测中...";
  }
  try {
    await loadModels(true, { triggerSource: "refresh_btn" });
    await loadLocalModelsManagerStatus(false);
    renderMinimalistModelList();
    renderLocalScanResultBox();
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "刷新";
    }
  }
}
window.refreshMinimalistModelList = refreshMinimalistModelList;

function renderMinimalistModelList() {
  const container = document.getElementById("minimalistModelListContainer");
  if (!container) return;

  const q = (document.getElementById("minimalistModelSearchInput")?.value || "").trim().toLowerCase();
  const activeModel =
    (currentChatData && currentChatData.model) ||
    headerModelSelect?.value ||
    settingModel?.value ||
    window.globalUserSettings?.model ||
    "";
  const modelParamsMap = (window.globalUserSettings && window.globalUserSettings.model_params) || {};
  const localModels = Array.isArray(availableModelsData?.local_models) ? availableModelsData.local_models : [];
  const localIdSet = new Set(localModels.map((lm) => lm.id));

  const rawRemote = Array.isArray(availableModelsData?.remote_models) ? availableModelsData.remote_models : [];
  const customModels = Array.from(
    new Set([
      ...(Array.isArray(availableModelsData?.custom_models) ? availableModelsData.custom_models : []),
      ...(Array.isArray(window.globalUserSettings?.custom_models) ? window.globalUserSettings.custom_models : [])
    ])
  ).filter(Boolean);
  const allApiIds = Array.from(
    new Set([
      ...customModels,
      ...rawRemote,
      ...((availableModelsData?.models || []).filter((id) => !localIdSet.has(id)))
    ])
  ).filter((id) => id && !localIdSet.has(id));

  const filteredLocals = localModels.filter((lm) => {
    if (!q) return true;
    return (lm.id || "").toLowerCase().includes(q) || (lm.name || "").toLowerCase().includes(q);
  });

  const filteredApis = allApiIds.filter((mId) => {
    if (!q) return true;
    return mId.toLowerCase().includes(q);
  });

  const localNamesPool = localModels.map((lm) => lm.name || lm.id);
  const apiNamesPool = allApiIds;

  const buildModelRowHtml = (mId, displayName, isLocal, extraSub = "", siblingPool = [], engineType = "", shardWarning = "") => {
    const isCurrent = mId === activeModel;
    const hasCustomParams = Boolean(modelParamsMap[mId] && Object.keys(modelParamsMap[mId]).length > 0);
    const paramSummary = hasCustomParams
      ? `T:${modelParamsMap[mId].temperature ?? 0.68} · Ctx:${modelParamsMap[mId].context ?? 16}轮`
      : "";
    const meta = extractModelDiffMeta(displayName || mId, siblingPool);
    const fullCleanTitle = meta.cleanName || displayName || mId;
    const highlightedTitleHtml =
      meta.sharedPrefix && meta.uniquePart && meta.sharedPrefix !== fullCleanTitle
        ? `<span style="opacity:0.86;">${escapeHtml(meta.sharedPrefix)}</span><span class="model-name-unique-part">${escapeHtml(meta.uniquePart)}</span>`
        : escapeHtml(fullCleanTitle);

    const engineBadgeHtml = isLocal && engineType
      ? `<span class="wb-badge" style="flex-shrink:0;white-space:nowrap;${engineType === "strata" ? "color:#c084fc;border-color:rgba(192,132,252,0.45);background:rgba(192,132,252,0.12);" : "color:#38bdf8;border-color:rgba(56,189,248,0.45);background:rgba(56,189,248,0.12);"}">${engineType === "strata" ? "Strata" : "Ollama"}</span>`
      : "";
    const warnBadgeHtml = shardWarning
      ? `<span class="wb-badge" style="flex-shrink:0;white-space:nowrap;color:#fca5a5;border-color:rgba(248,113,113,0.65);background:rgba(239,68,68,0.18);font-weight:700;">⚠️ ${escapeHtml(shardWarning)}</span>`
      : "";

    return `
      <div class="minimalist-model-row ${isCurrent ? "is-active" : ""}">
        <div class="minimalist-model-info">
          <div class="minimalist-model-title-line">
            ${meta.diffTag ? `<span class="wb-badge model-diff-tag-badge">${escapeHtml(meta.diffTag)}</span>` : ""}
            <span class="minimalist-model-full-name" title="${escapeHtml(displayName || mId)}">${highlightedTitleHtml}</span>
          </div>
          <div class="minimalist-model-badges-line">
            <span class="wb-badge" style="flex-shrink:0;white-space:nowrap;${isLocal ? "color:#fbbf24;border-color:rgba(245,158,11,0.45);background:rgba(245,158,11,0.12);" : "color:#93c5fd;border-color:rgba(59,130,246,0.45);background:rgba(59,130,246,0.12);"}">${isLocal ? "本地" : "API"}</span>
            ${engineBadgeHtml}
            ${warnBadgeHtml}
            ${hasCustomParams ? `<span class="wb-badge" style="flex-shrink:0;white-space:nowrap;color:#34d399;border-color:rgba(16,185,129,0.5);background:rgba(16,185,129,0.15);">独立 (${escapeHtml(paramSummary)})</span>` : ""}
            ${extraSub ? `<span class="minimalist-model-sub-text">${escapeHtml(extraSub)}</span>` : ""}
          </div>
        </div>
        <div class="model-row-actions">
          <button type="button" class="btn btn-xs model-row-param-btn ${hasCustomParams ? "btn-studio-toggle" : "btn-secondary"}" onclick="window.openPerModelParamsEditor('${escapeJsAttr(mId)}')">
            参数
          </button>
          <button type="button" class="btn btn-xs model-row-select-btn ${isCurrent ? "btn-secondary is-current" : "btn-primary"}" ${isCurrent ? "disabled" : ""} onclick="window.selectModelFromMinimalistList('${escapeJsAttr(mId)}')">
            ${isCurrent ? "✓ 当前" : "选用"}
          </button>
        </div>
      </div>
    `;
  };

  const localSectionHtml = `
    <div class="minimalist-model-group">
      <div class="minimalist-model-group-header">
        <span>本地模型 (${filteredLocals.length})</span>
      </div>
      ${
        filteredLocals.length > 0
          ? filteredLocals.map((lm) => buildModelRowHtml(lm.id, lm.name || lm.id, true, "", localNamesPool, lm.engine || "", lm.shard_warning || "")).join("")
          : `<div style="padding:14px;text-align:center;color:var(--text-dim);font-size:12.5px;">
               暂无本地模型
               <div style="display:flex;justify-content:center;gap:8px;margin-top:8px;">
                 <button type="button" class="btn btn-xs btn-primary" onclick="window.switchModelSettingsTab('local')">扫描</button>
                 <button type="button" class="btn btn-xs btn-secondary" style="color:#38bdf8;border-color:rgba(56,189,248,0.45);" onclick="window.switchModelSettingsTab('hf')">下载</button>
               </div>
             </div>`
      }
    </div>
  `;

  const apiSectionHtml = `
    <div class="minimalist-model-group">
      <div class="minimalist-model-group-header">
        <span>API 模型 (${filteredApis.length})</span>
      </div>
      ${
        filteredApis.length > 0
          ? filteredApis.map((mId) => {
              const p = (availableModelsData?.pricing || {})[mId];
              const sub = p && p.detail_price ? p.detail_price : (customModels.includes(mId) ? "手动添加" : "");
              return buildModelRowHtml(mId, mId, false, sub, apiNamesPool);
            }).join("")
          : `<div style="padding:14px;text-align:center;color:var(--text-dim);font-size:12.5px;">
               暂无 API 模型
               <button type="button" class="btn btn-xs btn-primary" style="margin-left:8px;" onclick="window.switchModelSettingsTab('api')">配置 API</button>
             </div>`
      }
    </div>
  `;

  container.innerHTML = localSectionHtml + apiSectionHtml;
}
window.renderMinimalistModelList = renderMinimalistModelList;

function refreshAllParamOverridePanels() {
  if (typeof window.syncGlobalParamsOverrideUI === "function") {
    window.syncGlobalParamsOverrideUI();
  }
  const studioPane = document.getElementById("studioWorkbenchPane");
  if (studioPane && studioPane.style.display !== "none" && typeof window.renderStudioWorkbench === "function") {
    window.renderStudioWorkbench();
  }
  const advView = document.getElementById("advancedProjectEditorView") || document.getElementById("advancedProjectModal");
  if (advView && advView.style.display !== "none" && typeof window.switchAdvancedProjectTab === "function") {
    const activeTabBtn = advView.querySelector(".adv-tab-btn.active");
    if (activeTabBtn && activeTabBtn.textContent.includes("采样参数")) {
      window.switchAdvancedProjectTab("params");
    }
  }
}
window.refreshAllParamOverridePanels = refreshAllParamOverridePanels;

async function selectModelFromMinimalistList(modelId) {
  if (!modelId) return;
  syncHeaderModelSelect(modelId);
  if (!window.globalUserSettings) window.globalUserSettings = {};
  window.globalUserSettings.model = modelId;
  if (currentChatId) {
    await handleHeaderModelChange();
  }
  await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: modelId })
  });
  renderMinimalistModelList();
  renderLocalScanResultBox();
  updateContextProgressUI();
  refreshAllParamOverridePanels();
  showToast(`已切换模型：${modelId}`);
}
window.selectModelFromMinimalistList = selectModelFromMinimalistList;

function openPerModelParamsEditor(modelId) {
  if (!modelId) return;
  currentEditingPerModelId = modelId;
  const listView = document.getElementById("modelListMainView");
  const paramView = document.getElementById("perModelParamsView");
  const titleEl = document.getElementById("perModelParamsTargetTitle");
  const badgeEl = document.getElementById("perModelParamsActiveBadge");
  if (listView) listView.style.display = "none";
  if (paramView) paramView.style.display = "flex";
  if (titleEl) titleEl.textContent = modelId;

  const savedMap = (window.globalUserSettings && window.globalUserSettings.model_params) || {};
  const saved = savedMap[modelId] || {};
  const hasSaved = Object.keys(saved).length > 0;
  if (badgeEl) {
    badgeEl.textContent = hasSaved ? "已启用" : "未启用";
    badgeEl.style.color = hasSaved ? "#34d399" : "#94a3b8";
  }

  const fallbackGlobal = window.globalUserSettings || {};
  const is27bLocal = /(?:27b|dongfangshuo-v4)/i.test(String(modelId));
  const modelSpecificDef = is27bLocal
    ? { repetition_penalty: 1.03, frequency_penalty: 0.0, presence_penalty: 0.10 }
    : {};
  PER_MODEL_PARAM_FIELDS.forEach((f) => {
    const baseFallback = modelSpecificDef[f.key] !== undefined
      ? modelSpecificDef[f.key]
      : (fallbackGlobal[f.key] !== undefined ? fallbackGlobal[f.key] : f.def);
    const raw = saved[f.key] !== undefined ? saved[f.key] : baseFallback;
    const val = f.isFloat ? parseFloat(raw) : parseInt(raw, 10);
    const safeVal = Number.isNaN(val) ? f.def : val;
    const inp = document.getElementById(f.id);
    const rng = document.getElementById(f.rangeId);
    if (inp) inp.value = f.isFloat ? safeVal.toFixed(f.digits || 2) : safeVal;
    if (rng) rng.value = safeVal;
  });
}
window.openPerModelParamsEditor = openPerModelParamsEditor;

function closePerModelParamsEditor() {
  const listView = document.getElementById("modelListMainView");
  const paramView = document.getElementById("perModelParamsView");
  if (paramView) paramView.style.display = "none";
  if (listView) listView.style.display = "flex";
}
window.closePerModelParamsEditor = closePerModelParamsEditor;

function applyPerModelPreset(presetType) {
  const is27bLocal = /(?:27b|dongfangshuo-v4)/i.test(String(currentEditingPerModelId || ""));
  const presets = {
    novel: {
      temperature: 0.68, top_p: 0.90, top_k: 40, min_p: 0.06,
      repetition_penalty: is27bLocal ? 1.03 : 1.05,
      frequency_penalty: is27bLocal ? 0.00 : 0.05,
      presence_penalty: is27bLocal ? 0.10 : 0.20
    },
    strict: {
      temperature: 0.62, top_p: 0.85, top_k: 35, min_p: 0.08,
      repetition_penalty: 1.03, frequency_penalty: 0.02, presence_penalty: 0.12
    },
    creative: {
      temperature: 0.75, top_p: 0.92, top_k: 45, min_p: 0.05,
      repetition_penalty: 1.06, frequency_penalty: 0.05, presence_penalty: 0.25
    }
  };
  const target = presets[presetType] || presets.novel;
  PER_MODEL_PARAM_FIELDS.forEach((f) => {
    if (target[f.key] !== undefined) {
      const v = target[f.key];
      const inp = document.getElementById(f.id);
      const rng = document.getElementById(f.rangeId);
      if (inp) inp.value = f.isFloat ? Number(v).toFixed(f.digits || 2) : v;
      if (rng) rng.value = v;
    }
  });
  showToast("已填入，保存后生效");
}
window.applyPerModelPreset = applyPerModelPreset;

async function savePerModelParams() {
  if (!currentEditingPerModelId) return;
  const params = {};
  PER_MODEL_PARAM_FIELDS.forEach((f) => {
    const inp = document.getElementById(f.id);
    const raw = inp ? (f.isFloat ? parseFloat(inp.value) : parseInt(inp.value, 10)) : f.def;
    params[f.key] = Number.isNaN(raw) ? f.def : raw;
  });

  try {
    const res = await fetch("/api/settings/model_params", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: currentEditingPerModelId, params })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "保存失败");
    if (!window.globalUserSettings) window.globalUserSettings = {};
    window.globalUserSettings.model_params = data.model_params || {};
    closePerModelParamsEditor();
    renderMinimalistModelList();
    updateContextProgressUI();
    refreshAllParamOverridePanels();
    showToast(`已保存：${currentEditingPerModelId}`);
  } catch (err) {
    showToast("保存失败: " + err.message);
  }
}
window.savePerModelParams = savePerModelParams;

async function clearPerModelParams() {
  if (!currentEditingPerModelId) return;
  try {
    const res = await fetch("/api/settings/model_params", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: currentEditingPerModelId, clear: true })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "清除失败");
    if (!window.globalUserSettings) window.globalUserSettings = {};
    window.globalUserSettings.model_params = data.model_params || {};
    closePerModelParamsEditor();
    renderMinimalistModelList();
    updateContextProgressUI();
    refreshAllParamOverridePanels();
    showToast("已恢复全局");
  } catch (err) {
    showToast("清除失败: " + err.message);
  }
}
window.clearPerModelParams = clearPerModelParams;

function renderLocalScanResultBox() {
  const box = document.getElementById("localScanResultBox");
  if (!box) return;
  const mgrModels = Array.isArray(window.localModelsManagerData?.detected_models)
    ? window.localModelsManagerData.detected_models
    : null;
  const localModels = mgrModels || (Array.isArray(availableModelsData?.local_models) ? availableModelsData.local_models : []);
  const activeModel =
    (currentChatData && currentChatData.model) ||
    headerModelSelect?.value ||
    settingModel?.value ||
    window.globalUserSettings?.model ||
    "";
  if (localModels.length === 0) {
    box.innerHTML = `
      <div style="padding:12px 14px;border-radius:10px;background:rgba(255,255,255,0.03);border:1px dashed var(--border-color);color:var(--text-dim);font-size:12.5px;text-align:center;">
        暂无本地模型 · <a href="javascript:void(0)" style="color:#38bdf8;font-weight:700;" onclick="window.switchModelSettingsTab('hf')">下载</a>
      </div>
    `;
    return;
  }
  const localNamesPool = localModels.map((lm) => lm.name || lm.id);
  const readyCount = localModels.filter((lm) => lm.shards_complete !== false && !lm.shard_warning).length;
  const incompleteCount = localModels.length - readyCount;
  const summaryColor = incompleteCount > 0 && readyCount === 0 ? "#f87171" : "#34d399";
  const summaryHtml =
    incompleteCount > 0
      ? `已就绪 ${readyCount} <span style="color:#fca5a5;margin-left:6px;">· ⚠️ 分片缺失/未完成 ${incompleteCount}</span>`
      : `已就绪 ${readyCount}`;
  box.innerHTML = `
    <div style="display:flex;flex-direction:column;gap:6px;">
      <div style="font-size:12px;font-weight:700;color:${summaryColor};margin-bottom:2px;">${summaryHtml}</div>
      ${localModels
        .map((lm) => {
          const isCurrent = lm.id === activeModel;
          const meta = extractModelDiffMeta(lm.name || lm.id, localNamesPool);
          const fullCleanTitle = meta.cleanName || lm.name || lm.id;
          const highlightedTitleHtml =
            meta.sharedPrefix && meta.uniquePart && meta.sharedPrefix !== fullCleanTitle
              ? `<span style="opacity:0.86;">${escapeHtml(meta.sharedPrefix)}</span><span class="model-name-unique-part">${escapeHtml(meta.uniquePart)}</span>`
              : escapeHtml(fullCleanTitle);
          const isStrata = lm.engine === "strata" || (lm.id || "").includes("iq3_xxs") || (lm.id || "").includes("flash");
          const engineBadge = isStrata
            ? `<span class="wb-badge" style="color:#c084fc;border-color:rgba(192,132,252,0.45);background:rgba(192,132,252,0.12);font-size:11px;">Strata (Flash-Next)</span>`
            : `<span class="wb-badge" style="color:#38bdf8;border-color:rgba(56,189,248,0.45);background:rgba(56,189,248,0.12);font-size:11px;">Ollama 80K (27B)</span>`;
          const shardWarnBadge = lm.shard_warning
            ? `<span class="wb-badge" style="color:#fca5a5;border-color:rgba(248,113,113,0.65);background:rgba(239,68,68,0.18);font-size:11px;font-weight:700;">⚠️ ${escapeHtml(lm.shard_warning)}</span>`
            : "";
          const pathHint = lm.gguf_path || lm.config_path || "";
          return `
            <div class="minimalist-model-row ${isCurrent ? "is-active" : ""}">
              <div class="minimalist-model-info">
                <div class="minimalist-model-title-line">
                  ${meta.diffTag ? `<span class="wb-badge model-diff-tag-badge">${escapeHtml(meta.diffTag)}</span>` : ""}
                  <span class="minimalist-model-full-name" title="${escapeHtml(lm.name || lm.id)}">${highlightedTitleHtml}</span>
                </div>
                <div class="minimalist-model-badges-line" style="margin-top:3px;">
                  ${engineBadge}
                  ${shardWarnBadge}
                  <span class="minimalist-model-sub-text">ID: ${escapeHtml(lm.id)}</span>
                  ${pathHint ? `<span class="minimalist-model-sub-text" style="opacity:0.75;" title="${escapeHtml(pathHint)}">${escapeHtml(pathHint.split(/[\\/]/).slice(-2).join("/"))}</span>` : ""}
                </div>
              </div>
              <div class="model-row-actions">
                <button type="button" class="btn btn-xs model-row-param-btn btn-secondary" onclick="window.switchModelSettingsTab('list');window.openPerModelParamsEditor('${escapeJsAttr(lm.id)}')">独立参数</button>
                <button type="button" class="btn btn-xs model-row-select-btn ${isCurrent ? "btn-secondary is-current" : "btn-primary"}" ${isCurrent ? "disabled" : ""} onclick="window.selectModelFromMinimalistList('${escapeJsAttr(lm.id)}')">
                  ${isCurrent ? "✓ 当前" : "选用"}
                </button>
              </div>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}
window.renderLocalScanResultBox = renderLocalScanResultBox;

async function loadLocalModelsManagerStatus(showToastMsg = false) {
  try {
    const res = await fetch("/api/local_models/manager_status");
    if (!res.ok) return;
    const data = await res.json();
    window.localModelsManagerData = data;

    if (Array.isArray(data.detected_models)) {
      if (!availableModelsData) availableModelsData = { models: [], local_models: [] };
      availableModelsData.local_models = data.detected_models;
      const existingIds = new Set(availableModelsData.models || []);
      data.detected_models.forEach((dm) => {
        if (dm.id && !existingIds.has(dm.id)) {
          availableModelsData.models.unshift(dm.id);
        }
      });
    }

    const dirEl = document.getElementById("localBundleModelDirDisplay");
    if (dirEl && data.bundle_model_dir) {
      dirEl.textContent = `目录：${data.bundle_model_dir}`;
    }

    renderLocalScanResultBox();
    renderCustomModelPathsList();
    renderHfDownloaderPanel();

    // 若有正在下载的任务，自动开启 1.5s 轮询更新进度条
    const downloads = data.downloads || {};
    const hasActiveDl = Object.values(downloads).some((t) => t && t.status === "downloading");
    if (hasActiveDl) {
      if (!_hfStatusPollTimer) {
        _hfStatusPollTimer = setInterval(() => {
          const modal = document.getElementById("modelSettingsModal");
          if (!modal || modal.style.display === "none") {
            clearInterval(_hfStatusPollTimer);
            _hfStatusPollTimer = null;
            return;
          }
          loadLocalModelsManagerStatus(false);
        }, 1500);
      }
    } else if (_hfStatusPollTimer) {
      clearInterval(_hfStatusPollTimer);
      _hfStatusPollTimer = null;
      await loadModels(false);
      renderMinimalistModelList();
      renderLocalScanResultBox();
    }

    if (showToastMsg) {
      showToast("已刷新");
    }
  } catch (err) {
    console.error("获取本地模型管理状态失败:", err);
  }
}
window.loadLocalModelsManagerStatus = loadLocalModelsManagerStatus;

function renderCustomModelPathsList() {
  const box = document.getElementById("customModelPathsListBox");
  if (!box) return;
  const customPaths = Array.isArray(window.localModelsManagerData?.custom_paths)
    ? window.localModelsManagerData.custom_paths
    : [];
  if (customPaths.length === 0) {
    box.innerHTML = `<div style="font-size:11.5px;color:var(--text-dim);padding:4px 2px;">暂无挂载路径</div>`;
    return;
  }
  const detectedModels = Array.isArray(window.localModelsManagerData?.detected_models)
    ? window.localModelsManagerData.detected_models
    : [];

  box.innerHTML = customPaths
    .map((cp) => {
      const pStr = cp.path || "";
      const ggufs = Array.isArray(cp.gguf_files) ? cp.gguf_files : [];
      const ggufSet = new Set(ggufs.map((x) => String(x).toLowerCase()));
      const matchedModel = detectedModels.find((dm) => {
        const gp = String(dm.gguf_path || "").split(/[\\/]/).pop().toLowerCase();
        return gp && ggufSet.has(gp);
      });
      const statusBadge = !cp.exists
        ? `<span class="wb-badge" style="color:#f87171;border-color:rgba(248,113,113,0.4);">路径不存在</span>`
        : ggufs.length > 0
        ? `<span class="wb-badge" style="color:#34d399;border-color:rgba(16,185,129,0.4);background:rgba(16,185,129,0.12);">${ggufs.length} 个 GGUF</span>`
        : `<span class="wb-badge" style="color:#fbbf24;border-color:rgba(251,191,36,0.4);">未发现 .gguf</span>`;
      const shardWarnBadge = matchedModel?.shard_warning
        ? `<span class="wb-badge" style="color:#fca5a5;border-color:rgba(248,113,113,0.65);background:rgba(239,68,68,0.18);font-weight:700;">⚠️ ${escapeHtml(matchedModel.shard_warning)}</span>`
        : "";

      return `
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;padding:8px 10px;border-radius:9px;background:rgba(255,255,255,0.03);border:1px solid var(--border-color);flex-wrap:wrap;">
          <div style="display:flex;flex-direction:column;gap:3px;min-width:0;flex:1;">
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
              <span style="font-size:12px;font-weight:700;color:var(--text-main);font-family:monospace;word-break:break-all;">${escapeHtml(pStr)}</span>
              ${statusBadge}
              ${shardWarnBadge}
            </div>
            ${ggufs.length > 0 ? `<div style="font-size:11px;color:var(--text-dim);">识别文件：${escapeHtml(ggufs.slice(0, 3).join(" , "))}${ggufs.length > 3 ? ` 等 ${ggufs.length} 个` : ""}</div>` : ""}
          </div>
          <div style="display:flex;gap:6px;flex-shrink:0;">
            ${matchedModel ? `<button type="button" class="btn btn-xs btn-primary" onclick="window.selectModelFromMinimalistList('${escapeJsAttr(matchedModel.id)}')">选用</button>` : ""}
            <button type="button" class="btn btn-xs btn-secondary" style="color:#f87171;" onclick="window.removeCustomModelPath('${escapeJsAttr(pStr)}')">移除</button>
          </div>
        </div>
      `;
    })
    .join("");
}
window.renderCustomModelPathsList = renderCustomModelPathsList;

async function openLocalBundleModelFolder(targetPath = "") {
  try {
    const res = await fetch("/api/local_models/open_folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: targetPath || "" })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "打开文件夹失败");
    showToast(`已打开：${data.opened}`);
  } catch (err) {
    showToast("打开文件夹失败: " + err.message);
  }
}
window.openLocalBundleModelFolder = openLocalBundleModelFolder;

async function pickCustomModelPathDialog(mode = "file") {
  const btnId = mode === "dir" ? "btnPickCustomGgufDir" : "btnPickCustomGgufFile";
  const btn = document.getElementById(btnId);
  const origText = btn ? btn.textContent : "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "选择中…";
  }
  try {
    const res = await fetch("/api/local_models/pick_path", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "选择路径失败");
    if (data.status === "cancelled" || !data.selected) {
      return;
    }
    const inp = document.getElementById("customModelPathInput");
    if (inp) inp.value = data.selected;
    if (window.localModelsManagerData) {
      window.localModelsManagerData.custom_paths = data.custom_paths || [];
      window.localModelsManagerData.detected_models = data.detected_models || [];
      window.localModelsManagerData.hf_catalog = data.hf_catalog || [];
    }
    await loadModels(false, { triggerSource: "refresh_btn" });
    await loadLocalModelsManagerStatus(false);
    if (data.matched_model_id) {
      await selectModelFromMinimalistList(data.matched_model_id);
      showToast(`已切换：${data.matched_model_id}`);
    } else {
      showToast(`已挂载：${data.selected}`);
    }
  } catch (err) {
    showToast("选择失败: " + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = origText;
    }
  }
}
window.pickCustomModelPathDialog = pickCustomModelPathDialog;

async function addCustomModelPathFromInput() {
  const inp = document.getElementById("customModelPathInput");
  const rawPath = (inp?.value || "").trim();
  if (!rawPath) {
    showToast("请输入 .gguf 文件或目录路径");
    inp?.focus();
    return;
  }
  const btn = document.getElementById("btnAddCustomModelPath");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "识别中...";
  }
  try {
    const res = await fetch("/api/local_models/add_path", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: rawPath })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "挂载路径失败");
    if (inp) {
      inp.value = "";
      inp.parentElement?.classList.remove("has-value");
    }
    if (window.localModelsManagerData) {
      window.localModelsManagerData.custom_paths = data.custom_paths || [];
      window.localModelsManagerData.detected_models = data.detected_models || [];
      window.localModelsManagerData.hf_catalog = data.hf_catalog || [];
    }
    await loadModels(false, { triggerSource: "refresh_btn" });
    await loadLocalModelsManagerStatus(false);
    if (data.matched_model_id) {
      await selectModelFromMinimalistList(data.matched_model_id);
      showToast(`已切换：${data.matched_model_id}`);
    } else {
      showToast(`已挂载：${data.added}`);
    }
  } catch (err) {
    showToast("挂载失败: " + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "挂载";
    }
  }
}
window.addCustomModelPathFromInput = addCustomModelPathFromInput;

async function removeCustomModelPath(pathStr) {
  if (!pathStr) return;
  try {
    const res = await fetch("/api/local_models/remove_path", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: pathStr })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "移除失败");
    if (window.localModelsManagerData) {
      window.localModelsManagerData.custom_paths = data.custom_paths || [];
      window.localModelsManagerData.detected_models = data.detected_models || [];
      window.localModelsManagerData.hf_catalog = data.hf_catalog || [];
    }
    await loadModels(false, { triggerSource: "refresh_btn" });
    await loadLocalModelsManagerStatus(false);
    showToast("已移除");
  } catch (err) {
    showToast("移除失败: " + err.message);
  }
}
window.removeCustomModelPath = removeCustomModelPath;

function _formatBytesGb(bytes) {
  const b = Number(bytes) || 0;
  if (b <= 0) return "0 B";
  if (b >= 1e9) return `${(b / 1e9).toFixed(2)} GB`;
  if (b >= 1e6) return `${(b / 1e6).toFixed(1)} MB`;
  return `${Math.round(b / 1024)} KB`;
}

function _getGroupedHfCatalog() {
  const raw = Array.isArray(window.localModelsManagerData?.hf_catalog)
    ? window.localModelsManagerData.hf_catalog
    : [];
  if (raw.length === 0) return [];
  if (Array.isArray(raw[0]?.tiers)) return raw;

  const folderMap = new Map();
  raw.forEach((item) => {
    const repoId = item.repo_id || "dongfangshuo/model";
    const isFlash =
      item.subfolder === "Flash-Next" ||
      item.series === "Flash-Next" ||
      String(repoId).toLowerCase().includes("flash-next") ||
      item.engine === "strata";
    const folderKey = isFlash ? "Flash-Next" : "Dongfangshuo-27B";

    if (!folderMap.has(folderKey)) {
      folderMap.set(folderKey, {
        folder_key: folderKey,
        repo_id: isFlash
          ? "dongfangshuo/Dongfangshuo-Qwen3.8-Flash-Next-NSFW"
          : "dongfangshuo/Dongfangshuo-Qwen3.8-27B-NSFW-v4",
        title: folderKey,
        subfolder: folderKey,
        engine: isFlash ? "strata" : "ollama",
        tiers: []
      });
    }
    const grp = folderMap.get(folderKey);
    // Clean any legacy suffix after " · " in item.name if backend wasn't restarted yet
    const rawName = String(item.name || item.quant || item.id || "").trim();
    const cleanName = rawName.replace(/\s*·\s*[^()]+(\))?$/, "$1");
    const rawHint = String(item.vram_hint || "").trim();
    const cleanHint = rawHint.startsWith("推荐配置")
      ? rawHint
      : rawHint
      ? `推荐配置：${rawHint.replace(/\s*·\s*\d+(\.\d+)?\s*GB.*$/i, "")}`
      : "";

    grp.tiers.push({
      preset_id: item.id || "",
      repo_id: repoId,
      name: cleanName,
      vram_hint: cleanHint,
      tier_name: cleanName,
      all_ready: Boolean(item.all_ready || item.installed),
      installed_path: item.installed_path || "",
      files: (item.files || []).map((f) => ({
        path: f.path || f.filename || "",
        filename: f.filename || f.path || "",
        size: Number(f.size) || 0,
        exists: Boolean(f.exists),
        local_path: f.local_path || ""
      }))
    });
  });
  return Array.from(folderMap.values());
}

function renderHfDownloaderPanel() {
  const dlBox = document.getElementById("hfActiveDownloadsBox");
  const catBox = document.getElementById("hfCatalogContainer");
  const mgr = window.localModelsManagerData || {};
  const downloads = mgr.downloads || [];
  const catalog = _getGroupedHfCatalog();

  if (dlBox) {
    const dlList = (Array.isArray(downloads) ? downloads : Object.values(downloads)).sort(
      (a, b) => (b.updated_at || b.started_at || 0) - (a.updated_at || a.started_at || 0)
    );
    if (dlList.length === 0) {
      dlBox.style.display = "none";
      dlBox.innerHTML = "";
    } else {
      dlBox.style.display = "flex";
      dlBox.innerHTML = `
        <div class="context-setting-card" style="padding:12px 14px;display:flex;flex-direction:column;gap:8px;border-color:rgba(56,189,248,0.4);">
          <div style="font-size:12.5px;font-weight:700;color:#38bdf8;">下载 (${dlList.length})</div>
          ${dlList
            .map((t) => {
              const st = t.status || "downloading";
              const pct = Number(t.progress_pct || 0).toFixed(1);
              const spd = Number(t.speed_mbps || 0).toFixed(2);
              const dlBytes = _formatBytesGb(t.downloaded_bytes || 0);
              const totBytes = _formatBytesGb(t.total_bytes || 0);
              const curFileHint = t.current_file ? ` · ${escapeHtml(t.current_file)}` : "";
              const statusLabel =
                st === "downloading"
                  ? `下载中 ${pct}% (${spd} MB/s · ${dlBytes} / ${totBytes})${curFileHint}`
                  : st === "completed"
                  ? `下载完成 (${totBytes})`
                  : st === "paused"
                  ? `已暂停 (${pct}% · ${dlBytes} / ${totBytes})`
                  : st === "error"
                  ? `下载中断: ${escapeHtml(t.error || "网络异常")}`
                  : `已取消`;
              const barColor =
                st === "completed"
                  ? "#10b981"
                  : st === "error"
                  ? "#ef4444"
                  : st === "paused"
                  ? "#f59e0b"
                  : "#38bdf8";

              return `
                <div style="display:flex;flex-direction:column;gap:5px;padding:8px 10px;border-radius:8px;background:rgba(255,255,255,0.03);border:1px solid var(--border-color);">
                  <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
                    <span style="font-size:12px;font-weight:700;color:var(--text-main);word-break:break-all;">${escapeHtml(t.title || t.filename || t.task_id)}</span>
                    <div style="display:flex;gap:6px;align-items:center;">
                      ${
                        st === "downloading"
                          ? `<button type="button" class="btn btn-xs btn-secondary" onclick="window.controlHfDownload('${escapeJsAttr(t.task_id)}', 'pause')">暂停</button>`
                          : st === "paused" || st === "error"
                          ? `<button type="button" class="btn btn-xs btn-primary" onclick="window.controlHfDownload('${escapeJsAttr(t.task_id)}', 'resume')">继续</button>`
                          : ""
                      }
                      ${
                        st !== "completed"
                          ? `<button type="button" class="btn btn-xs btn-secondary" style="color:#f87171;" onclick="window.controlHfDownload('${escapeJsAttr(t.task_id)}', 'cancel')">取消</button>`
                          : `<button type="button" class="btn btn-xs btn-secondary" onclick="window.controlHfDownload('${escapeJsAttr(t.task_id)}', 'remove')">隐藏</button>`
                      }
                    </div>
                  </div>
                  <div style="width:100%;height:7px;border-radius:999px;background:rgba(255,255,255,0.08);overflow:hidden;">
                    <div style="width:${Math.max(0, Math.min(100, Number(pct)))}%;height:100%;background:${barColor};transition:width 0.3s ease;"></div>
                  </div>
                  <div style="font-size:11.5px;color:var(--text-dim);display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;">
                    <span>${statusLabel}</span>
                    <span style="opacity:0.7;">源: ${escapeHtml(t.mirror || "hf-mirror")}</span>
                  </div>
                </div>
              `;
            })
            .join("")}
        </div>
      `;
    }
  }

  if (!catBox) return;
  if (catalog.length === 0) {
    catBox.dataset.renderedSig = "";
    catBox.innerHTML = `<div style="padding:18px;text-align:center;color:var(--text-dim);">加载中…</div>`;
    return;
  }

  const catSig = JSON.stringify(
    catalog.map((g) => ({
      k: g.folder_key,
      t: (g.tiers || []).map((t) => [t.preset_id || t.name, Boolean(t.all_ready)])
    }))
  );
  if (catBox.dataset.renderedSig === catSig && catBox.children.length > 0) {
    return;
  }
  catBox.dataset.renderedSig = catSig;

  catBox.innerHTML = catalog
    .map((group) => {
      const folderKey = group.folder_key || group.subfolder || group.repo_id || "";
      const tiersHtml = (group.tiers || [])
        .map((tier, tIdx) => {
          const files = Array.isArray(tier.files) ? tier.files : [];
          const totalBytes = files.reduce((acc, f) => acc + (Number(f.size) || 0), 0);
          const allReady = Boolean(tier.all_ready);

          return `
            <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;padding:9px 12px;border-radius:9px;background:rgba(255,255,255,0.025);border:1px solid ${allReady ? "rgba(16,185,129,0.4)" : "var(--border-color)"};flex-wrap:wrap;">
              <div style="display:flex;flex-direction:column;gap:3px;min-width:200px;flex:1;">
                <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                  <span style="font-size:13px;font-weight:700;color:var(--text-main);">${escapeHtml(tier.name || tier.tier_name || "")}</span>
                  <span class="wb-badge" style="font-size:11px;color:#94a3b8;">${_formatBytesGb(totalBytes)}</span>
                  ${allReady ? `<span class="wb-badge" style="color:#34d399;border-color:rgba(16,185,129,0.45);background:rgba(16,185,129,0.14);font-size:11px;">已就绪</span>` : ""}
                </div>
                ${tier.vram_hint ? `<div style="font-size:12px;color:var(--text-dim);">${escapeHtml(tier.vram_hint)}</div>` : ""}
              </div>
              <div style="display:flex;gap:6px;flex-shrink:0;">
                ${
                  allReady
                    ? `<button type="button" class="btn btn-sm btn-primary" onclick="window.selectReadyHfTierModel('${escapeJsAttr(folderKey)}', ${tIdx})">选用</button>`
                    : `<button type="button" class="btn btn-sm btn-primary" style="background:linear-gradient(135deg,#0284c7,#2563eb);border:none;" onclick="window.startHfTierDownload('${escapeJsAttr(folderKey)}', ${tIdx})">下载</button>`
                }
              </div>
            </div>
          `;
        })
        .join("");

      return `
        <details open class="context-setting-card" style="padding:12px 14px;">
          <summary style="cursor:pointer;list-style:none;display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;user-select:none;">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
              <span style="font-size:14px;font-weight:800;color:var(--text-main);">${escapeHtml(group.title || folderKey)}</span>
              <code style="font-size:11.5px;color:#94a3b8;background:rgba(255,255,255,0.05);padding:2px 6px;border-radius:5px;">model/${escapeHtml(folderKey)}/</code>
            </div>
            <div style="display:flex;gap:6px;align-items:center;" onclick="event.stopPropagation();">
              <button type="button" class="btn btn-xs btn-secondary" onclick="window.openLocalBundleModelFolder('${escapeJsAttr(folderKey)}')">
                打开目录
              </button>
            </div>
          </summary>
          <div style="display:flex;flex-direction:column;gap:7px;margin-top:10px;">
            ${tiersHtml}
          </div>
        </details>
      `;
    })
    .join("");
}
window.renderHfDownloaderPanel = renderHfDownloaderPanel;

async function startHfPresetDownloadById(presetId) {
  const mirror = document.getElementById("hfMirrorSelect")?.value || "hf-mirror";
  try {
    const res = await fetch("/api/local_models/hf_download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preset_id: presetId, mirror })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "启动下载失败");
    showToast("已继续");
    await loadLocalModelsManagerStatus(false);
  } catch (err) {
    showToast("启动下载失败: " + err.message);
  }
}
window.startHfPresetDownloadById = startHfPresetDownloadById;

async function startHfTierDownload(folderOrRepoKey, tierIdx) {
  const catalog = _getGroupedHfCatalog();
  const group = catalog.find((r) => r.folder_key === folderOrRepoKey || r.repo_id === folderOrRepoKey);
  if (!group || !Array.isArray(group.tiers) || !group.tiers[tierIdx]) return;
  const tier = group.tiers[tierIdx];
  const filesToDl = (tier.files || []).filter((f) => !f.exists);
  if (filesToDl.length === 0) {
    showToast("已就绪");
    selectReadyHfTierModel(folderOrRepoKey, tierIdx);
    return;
  }
  const mirror = document.getElementById("hfMirrorSelect")?.value || "hf-mirror";
  try {
    const payload = tier.preset_id
      ? { preset_id: tier.preset_id, mirror }
      : { repo_id: tier.repo_id || group.repo_id, files: filesToDl, mirror };
    const res = await fetch("/api/local_models/hf_download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "启动下载失败");
    showToast(`已开始下载：${tier.name || tier.tier_name}`);
    await loadLocalModelsManagerStatus(false);
  } catch (err) {
    showToast("启动下载失败: " + err.message);
  }
}
window.startHfTierDownload = startHfTierDownload;

async function resumeHfDownloadTask(repoId, filename, expectedSize = 0) {
  const mirror = document.getElementById("hfMirrorSelect")?.value || "hf-mirror";
  try {
    const res = await fetch("/api/local_models/hf_download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repo_id: repoId,
        files: [{ path: filename, filename, size: Number(expectedSize) || 0 }],
        mirror
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "启动下载失败");
    showToast(`已开始下载：${filename.split("/").pop()}`);
    await loadLocalModelsManagerStatus(false);
  } catch (err) {
    showToast("启动下载失败: " + err.message);
  }
}
window.resumeHfDownloadTask = resumeHfDownloadTask;

async function controlHfDownload(taskId, action) {
  const mirror = document.getElementById("hfMirrorSelect")?.value || "hf-mirror";
  try {
    const res = await fetch("/api/local_models/hf_control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: taskId, action, mirror })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "操作失败");
    await loadLocalModelsManagerStatus(false);
    if (action === "pause") {
      showToast("已暂停");
    } else if (action === "resume") {
      showToast("已继续");
    } else if (action === "remove") {
      showToast("已隐藏");
    } else {
      showToast("已取消");
    }
  } catch (err) {
    showToast("操作失败: " + err.message);
  }
}
window.controlHfDownload = controlHfDownload;

async function selectReadyHfTierModel(folderOrRepoKey, tierIdx) {
  await loadModels(false, { triggerSource: "refresh_btn" });
  await loadLocalModelsManagerStatus(false);
  const catalog = _getGroupedHfCatalog();
  const group = catalog.find((r) => r.folder_key === folderOrRepoKey || r.repo_id === folderOrRepoKey);
  const tier = group && Array.isArray(group.tiers) ? group.tiers[tierIdx] : null;
  const detected = Array.isArray(window.localModelsManagerData?.detected_models)
    ? window.localModelsManagerData.detected_models
    : [];
  if (!tier || detected.length === 0) {
    switchModelSettingsTab("local");
    return;
  }
  const mainFiles = (tier.files || [])
    .map((f) => String(f.filename || f.path || "").split("/").pop().toLowerCase())
    .filter((fn) => fn && !fn.includes("mmproj"));

  let matched = detected.find((dm) => {
    const gp = String(dm.gguf_path || "").split(/[\\/]/).pop().toLowerCase();
    return gp && mainFiles.includes(gp);
  });
  if (!matched && group.engine === "strata") {
    matched = detected.find((dm) => dm.engine === "strata");
  }
  if (!matched && group.engine === "ollama") {
    matched = detected.find((dm) => dm.engine === "ollama");
  }
  if (matched) {
    await selectModelFromMinimalistList(matched.id);
    switchModelSettingsTab("list");
  } else {
    switchModelSettingsTab("local");
  }
}
window.selectReadyHfTierModel = selectReadyHfTierModel;

async function fetchLiveHfRepoFiles(repoId, containerId) {
  const box = document.getElementById(containerId);
  if (!box) return;
  if (box.style.display === "flex" && box.dataset.loaded === "1") {
    box.style.display = "none";
    return;
  }
  box.style.display = "flex";
  box.innerHTML = `<div style="font-size:12px;color:var(--text-dim);">查询中…</div>`;
  const mirror = document.getElementById("hfMirrorSelect")?.value || "hf-mirror";
  try {
    const res = await fetch(`/api/local_models/hf_repo_files?repo_id=${encodeURIComponent(repoId)}&mirror=${encodeURIComponent(mirror)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "查询失败");
    const files = Array.isArray(data.files) ? data.files : [];
    box.dataset.loaded = "1";
    if (files.length === 0) {
      box.innerHTML = `<div style="font-size:12px;color:var(--text-dim);">无 .gguf 文件</div>`;
      return;
    }
    box.innerHTML = `
      <div style="font-size:12px;font-weight:700;color:#93c5fd;">GGUF (${files.length})</div>
      <div style="display:flex;flex-direction:column;gap:5px;">
        ${files
          .map(
            (f) => `
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;padding:6px 10px;border-radius:8px;background:rgba(255,255,255,0.02);border:1px solid var(--border-color);flex-wrap:wrap;">
            <div style="display:flex;align-items:center;gap:6px;min-width:0;flex:1;">
              <span style="font-size:12px;font-family:monospace;color:var(--text-main);word-break:break-all;">${escapeHtml(f.filename)}</span>
              <span class="wb-badge" style="font-size:11px;color:#94a3b8;">${_formatBytesGb(f.size || 0)}</span>
            </div>
            ${
              f.exists
                ? `<span class="wb-badge" style="color:#34d399;border-color:rgba(16,185,129,0.4);">已存在</span>`
                : `<button type="button" class="btn btn-xs btn-primary" onclick="window.resumeHfDownloadTask('${escapeJsAttr(repoId)}', '${escapeJsAttr(f.filename)}', ${Number(f.size || 0)})">下载</button>`
            }
          </div>
        `
          )
          .join("")}
      </div>
    `;
  } catch (err) {
    box.innerHTML = `<div style="font-size:12px;color:#f87171;">查询失败: ${escapeHtml(err.message)}</div>`;
  }
}
window.fetchLiveHfRepoFiles = fetchLiveHfRepoFiles;

async function autoScanLocalAiModels() {
  const btn = document.getElementById("btnAutoScanLocalAi");
  const modeSel = document.getElementById("settingLocalMode");
  if (modeSel) modeSel.value = "auto";
  if (!window.globalUserSettings) window.globalUserSettings = {};
  window.globalUserSettings.local_mode = "auto";

  if (btn) {
    btn.disabled = true;
    btn.textContent = "扫描中...";
  }
  try {
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ local_mode: "auto" })
    });
    await loadModels(false, { triggerSource: "refresh_btn" });
    await loadLocalModelsManagerStatus(false);
    renderLocalScanResultBox();
    renderMinimalistModelList();
    const count = (availableModelsData?.local_models || []).length;
    showToast(count > 0 ? `发现 ${count} 个本地模型` : "暂无本地模型");
  } catch (err) {
    showToast("扫描失败: " + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "扫描";
    }
  }
}
window.autoScanLocalAiModels = autoScanLocalAiModels;

async function saveManualLocalAiConfig() {
  const urlInp = document.getElementById("settingLocalBaseUrl");
  const modInp = document.getElementById("settingLocalModel");
  const modeSel = document.getElementById("settingLocalMode");
  const lUrl = (urlInp?.value || "").trim();
  const lMod = (modInp?.value || "").trim();
  const nextMode = lUrl ? "manual" : "auto";
  if (modeSel) modeSel.value = nextMode;

  if (!window.globalUserSettings) window.globalUserSettings = {};
  window.globalUserSettings.local_mode = nextMode;
  window.globalUserSettings.local_base_url = lUrl;
  window.globalUserSettings.local_model = lMod;

  try {
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        local_mode: nextMode,
        local_base_url: lUrl,
        local_model: lMod
      })
    });
    await loadModels(false, { triggerSource: "refresh_btn" });
    await loadLocalModelsManagerStatus(false);
    renderLocalScanResultBox();
    renderMinimalistModelList();
    showToast("已保存");
  } catch (err) {
    showToast("保存失败: " + err.message);
  }
}
window.saveManualLocalAiConfig = saveManualLocalAiConfig;

async function saveMinimalistApiConfig() {
  const bUrl = (settingBaseUrl?.value || "").trim();
  const aKey = (settingApiKey?.value || "").trim();
  const btn = document.getElementById("btnSaveMinimalistApi");
  const statusBox = document.getElementById("apiConnectStatusBox");

  if (!window.globalUserSettings) window.globalUserSettings = {};
  window.globalUserSettings.base_url = bUrl;
  window.globalUserSettings.api_key = aKey;

  if (btn) {
    btn.disabled = true;
    btn.textContent = "连接中...";
  }
  try {
    const payload = collectSettingsPayload();
    payload.base_url = bUrl;
    payload.api_key = aKey;
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    await loadModels(false, { autoFromApiInput: true, triggerSource: "refresh_btn" });
    renderMinimalistModelList();

    const localSet = new Set((availableModelsData?.local_models || []).map((x) => x.id));
    const apiList = (availableModelsData?.models || []).filter((id) => !localSet.has(id));
    if (apiList.length > 0) {
      if (statusBox) {
        statusBox.innerHTML = `<span style="color:#34d399;font-weight:600;">已连接 (${apiList.length} 个模型)</span>`;
      }
      showToast(`已获取 ${apiList.length} 个模型`);
    } else {
      if (statusBox) {
        statusBox.innerHTML = `<span style="color:#fbbf24;">未获取到模型，请手动添加</span>`;
      }
      const sub = document.getElementById("apiManualModelSubmenu");
      if (sub) sub.open = true;
    }
  } catch (err) {
    showToast("保存失败: " + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "保存";
    }
  }
}
window.saveMinimalistApiConfig = saveMinimalistApiConfig;

async function addMinimalistCustomModel() {
  const inp = document.getElementById("minimalistCustomModelInput");
  const mId = (inp?.value || "").trim();
  if (!mId) {
    showToast("请输入模型名");
    inp?.focus();
    return;
  }
  if (!window.globalUserSettings) window.globalUserSettings = {};
  const cur = Array.isArray(window.globalUserSettings.custom_models)
    ? window.globalUserSettings.custom_models.filter(Boolean)
    : [];
  const next = [mId, ...cur.filter((x) => x !== mId)];
  window.globalUserSettings.custom_models = next;
  window.globalUserSettings.model = mId;
  if (inp) inp.value = "";

  try {
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        base_url: (settingBaseUrl?.value || "").trim(),
        api_key: (settingApiKey?.value || "").trim(),
        custom_models: next,
        model: mId
      })
    });
    await loadModels(false);
    syncHeaderModelSelect(mId);
    renderManualSavedModelsList();
    renderMinimalistModelList();
    showToast(`已添加：${mId}`);
  } catch (err) {
    showToast("添加失败: " + err.message);
  }
}
window.addMinimalistCustomModel = addMinimalistCustomModel;

// ================= 数据备份：一键导出到文件夹 & 从文件夹导入 =================
let cachedBackupOverview = null;

async function loadBackupOverview() {
  try {
    const res = await fetch("/api/backup/overview");
    if (!res.ok) return;
    const data = await res.json();
    cachedBackupOverview = data;

    const expInput = document.getElementById("backupExportFolderPath");
    if (expInput && !expInput.value.trim() && data.default_export_dir) {
      expInput.value = data.default_export_dir;
    }

    // 渲染游戏子项列表
    const projBox = document.getElementById("backupProjectsSubList");
    const chkProjMain = document.getElementById("chkBackupProjects");
    const isProjChecked = chkProjMain ? chkProjMain.checked : true;
    if (projBox) {
      const projs = data.projects || [];
      if (projs.length === 0) {
        projBox.innerHTML = `<small style="color:var(--text-dim);">暂无剧本</small>`;
      } else {
        projBox.innerHTML = projs
          .map(
            (p) => `
          <label class="checkbox-row" style="margin:0;font-size:12px;cursor:pointer;">
            <input type="checkbox" class="backup-proj-item-chk" value="${escapeHtml(p.id)}" ${isProjChecked ? "checked" : ""} onchange="window.onBackupSubItemChange('proj')" />
            <span>${escapeHtml(p.icon || "")} ${escapeHtml(p.name || p.id)}</span>
          </label>`
          )
          .join("");
      }
    }

    // 渲染对话记录子项列表
    const chatBox = document.getElementById("backupChatsSubList");
    const chkChatMain = document.getElementById("chkBackupChats");
    const isChatChecked = chkChatMain ? chkChatMain.checked : true;
    if (chatBox) {
      const chats = data.chats || [];
      if (chats.length === 0) {
        chatBox.innerHTML = `<small style="color:var(--text-dim);">暂无对话</small>`;
      } else {
        chatBox.innerHTML = chats
          .map(
            (c) => `
          <label class="checkbox-row" style="margin:0;font-size:12px;cursor:pointer;">
            <input type="checkbox" class="backup-chat-item-chk" value="${escapeHtml(c.id)}" ${isChatChecked ? "checked" : ""} onchange="window.onBackupSubItemChange('chat')" />
            <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(c.title || c.id)} <small style="color:var(--text-dim);">(${c.msg_count || 0}条)</small></span>
          </label>`
          )
          .join("");
      }
    }

    const galLabel = document.getElementById("backupGalleryCountLabel");
    if (galLabel) galLabel.textContent = `(${data.gallery_count || 0} 张)`;

    const setLabel = document.getElementById("backupSettingsCountLabel");
    if (setLabel) setLabel.textContent = `(设置 + ${data.presets_count || 0} 预设)`;

    const logLabel = document.getElementById("backupLogsCountLabel");
    if (logLabel) logLabel.textContent = `(${data.logs_count || 0} 份对话日志)`;

    updateBackupCountLabels();
  } catch (e) {
    console.error("加载备份概览失败:", e);
  }
}

function toggleBackupSubList(elId, btnEl) {
  const el = document.getElementById(elId);
  if (!el) return;
  const willOpen = el.style.display === "none";
  el.style.display = willOpen ? "flex" : "none";
  const targetBtn = btnEl || document.querySelector(`button[onclick*="${elId}"]`);
  if (targetBtn) {
    const isEn = window.currentAppLang === "en";
    targetBtn.textContent = willOpen ? (isEn ? "Collapse ▴" : "收起 ▴") : (isEn ? "Filter ▾" : "筛选 ▾");
    targetBtn.classList.toggle("btn-primary", willOpen);
    targetBtn.classList.toggle("btn-secondary", !willOpen);
  }
}

function updateBackupCountLabels() {
  const projChks = Array.from(document.querySelectorAll(".backup-proj-item-chk"));
  const checkedProjs = projChks.filter((c) => c.checked);
  const projLabel = document.getElementById("backupProjectsCountLabel");
  if (projLabel) {
    projLabel.textContent = projChks.length > 0 ? `(${checkedProjs.length}/${projChks.length})` : "(0)";
  }

  const chatChks = Array.from(document.querySelectorAll(".backup-chat-item-chk"));
  const checkedChats = chatChks.filter((c) => c.checked);
  const chatLabel = document.getElementById("backupChatsCountLabel");
  if (chatLabel) {
    chatLabel.textContent = chatChks.length > 0 ? `(${checkedChats.length}/${chatChks.length})` : "(0)";
  }

  const catChks = Array.from(document.querySelectorAll(".backup-cat-chk"));
  const allChk = document.getElementById("chkBackupSelectAll");
  if (allChk && catChks.length > 0) {
    allChk.checked = catChks.every((c) => c.checked);
  }
}

function toggleBackupSelectAll(checked) {
  document.querySelectorAll(".backup-cat-chk").forEach((c) => {
    c.checked = !!checked;
  });
  document.querySelectorAll(".backup-proj-item-chk").forEach((c) => {
    c.checked = !!checked;
  });
  document.querySelectorAll(".backup-chat-item-chk").forEach((c) => {
    c.checked = !!checked;
  });
  updateBackupCountLabels();
}

function onBackupCatChange() {
  const chkProj = document.getElementById("chkBackupProjects");
  if (chkProj) {
    const projChks = Array.from(document.querySelectorAll(".backup-proj-item-chk"));
    const anyChecked = projChks.some((c) => c.checked);
    if (!chkProj.checked) {
      projChks.forEach((c) => (c.checked = false));
    } else if (!anyChecked) {
      projChks.forEach((c) => (c.checked = true));
    }
  }

  const chkChat = document.getElementById("chkBackupChats");
  if (chkChat) {
    const chatChks = Array.from(document.querySelectorAll(".backup-chat-item-chk"));
    const anyChecked = chatChks.some((c) => c.checked);
    if (!chkChat.checked) {
      chatChks.forEach((c) => (c.checked = false));
    } else if (!anyChecked) {
      chatChks.forEach((c) => (c.checked = true));
    }
  }

  updateBackupCountLabels();
}

function onBackupSubItemChange(type) {
  if (type === "proj") {
    const projChks = Array.from(document.querySelectorAll(".backup-proj-item-chk"));
    const chkProj = document.getElementById("chkBackupProjects");
    if (chkProj) chkProj.checked = projChks.some((c) => c.checked);
  } else if (type === "chat") {
    const chatChks = Array.from(document.querySelectorAll(".backup-chat-item-chk"));
    const chkChat = document.getElementById("chkBackupChats");
    if (chkChat) chkChat.checked = chatChks.some((c) => c.checked);
  }
  updateBackupCountLabels();
}

function collectBackupSelections() {
  const include_projects = !!document.getElementById("chkBackupProjects")?.checked;
  const include_chats = !!document.getElementById("chkBackupChats")?.checked;
  const include_settings = !!document.getElementById("chkBackupSettings")?.checked;
  const include_gallery = !!document.getElementById("chkBackupGallery")?.checked;
  const include_logs = !!document.getElementById("chkBackupLogs")?.checked;

  const projChks = Array.from(document.querySelectorAll(".backup-proj-item-chk"));
  const checkedProjs = projChks.filter((c) => c.checked).map((c) => c.value);
  const project_ids = projChks.length > 0 && checkedProjs.length < projChks.length ? checkedProjs : null;

  const chatChks = Array.from(document.querySelectorAll(".backup-chat-item-chk"));
  const checkedChats = chatChks.filter((c) => c.checked).map((c) => c.value);
  const chat_ids = chatChks.length > 0 && checkedChats.length < chatChks.length ? checkedChats : null;

  return {
    include_projects,
    project_ids,
    include_chats,
    chat_ids,
    include_settings,
    include_gallery,
    include_logs
  };
}

function showBackupNotice(msg, isError = false) {
  const el = document.getElementById("backupStatusNotice");
  if (!el) return;
  el.style.display = "block";
  el.classList.toggle("is-error", !!isError);
  el.innerHTML = msg;
}

async function pickBackupFolder(inputId, title) {
  const inputEl = document.getElementById(inputId);
  try {
    showToast("选择文件夹…");
    const res = await fetch("/api/backup/pick-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: title || "选择文件夹",
        initial_dir: inputEl?.value.trim() || ""
      })
    });
    const data = await res.json();
    if (data.folder_path && inputEl) {
      inputEl.value = data.folder_path;
      showToast("已选择: " + data.folder_path);
    }
  } catch (e) {
    showToast("无法打开，请手动输入路径");
  }
}

async function handleOpenBackupFolder(inputId) {
  const inputEl = document.getElementById(inputId);
  const folder_path = inputEl?.value.trim() || "";
  if (!folder_path) {
    showToast("请先指定路径");
    return;
  }
  try {
    const res = await fetch("/api/backup/open-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder_path })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "打开失败");
    showToast("已打开");
  } catch (e) {
    showToast("打开文件夹失败: " + e.message);
  }
}

async function handleExportBackupToFolder() {
  const sel = collectBackupSelections();
  if (!sel.include_projects && !sel.include_chats && !sel.include_settings && !sel.include_gallery && !sel.include_logs) {
    showToast("请至少选一项");
    return;
  }
  const expInput = document.getElementById("backupExportFolderPath");
  const target_dir = expInput?.value.trim() || "";
  const btn = document.getElementById("btnDoBackupExport");
  try {
    if (btn) {
      btn.disabled = true;
      btn.textContent = "正在导出...";
    }
    const res = await fetch("/api/backup/export-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_dir,
        ...sel
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "导出失败");

    if (expInput && data.target_dir) {
      expInput.value = data.target_dir;
    }
    const impInput = document.getElementById("backupImportFolderPath");
    if (impInput && !impInput.value.trim() && data.target_dir) {
      impInput.value = data.target_dir;
    }

    const s = data.stats || {};
    const summaryText = `<b>已导出</b><br><code>${escapeHtml(data.target_dir)}</code><br>剧本 ${s.projects || 0} · 对话 ${s.chats || 0} · 设置 ${s.settings || 0} · 预设 ${s.presets || 0} · 图片 ${s.gallery_images || 0} · 日志 ${s.logs || 0}`;
    showBackupNotice(summaryText, false);
    showToast("已导出");
  } catch (e) {
    showBackupNotice(`导出失败：${escapeHtml(e.message)}`, true);
    showToast("导出失败: " + e.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "导出";
    }
  }
}

async function refreshAllAppDataAfterImport() {
  await loadSettings();
  await loadProjects();
  await loadChats();
  await updateGalleryCountBadge();
  await loadCharacterCards(true);
  await loadBackupOverview();
  if (typeof window.renderStudioWorkbench === "function") {
    window.renderStudioWorkbench();
  }
}

async function handleImportBackupFromPath() {
  const impInput = document.getElementById("backupImportFolderPath");
  const source_dir = impInput?.value.trim() || "";
  if (!source_dir) {
    showToast("请先指定路径");
    return;
  }
  const sel = collectBackupSelections();
  if (!sel.include_projects && !sel.include_chats && !sel.include_settings && !sel.include_gallery && !sel.include_logs) {
    showToast("请至少选一项");
    return;
  }

  const btn = document.getElementById("btnDoBackupImport");
  try {
    if (btn) {
      btn.disabled = true;
      btn.textContent = "正在导入...";
    }
    const res = await fetch("/api/backup/import-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_dir,
        include_projects: sel.include_projects,
        include_chats: sel.include_chats,
        include_settings: sel.include_settings,
        include_gallery: sel.include_gallery,
        include_logs: sel.include_logs
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "导入失败");

    const s = data.stats || {};
    const summaryText = `<b>已导入</b><br><code>${escapeHtml(data.source_dir)}</code><br>剧本 ${s.projects || 0} · 对话 ${s.chats || 0} · 设置 ${s.settings || 0} · 预设 ${s.presets || 0} · 图片 ${s.gallery_images || 0} · 日志 ${s.logs || 0}`;
    showBackupNotice(summaryText, false);
    showToast("已导入");
    await refreshAllAppDataAfterImport();
  } catch (e) {
    showBackupNotice(`导入失败：${escapeHtml(e.message)}`, true);
    showToast("导入失败: " + e.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "导入";
    }
  }
}

async function handleImportBackupFromBrowserFiles(event) {
  const files = Array.from(event.target.files || []);
  if (!files.length) return;

  const sel = collectBackupSelections();
  if (!sel.include_projects && !sel.include_chats && !sel.include_settings && !sel.include_gallery && !sel.include_logs) {
    showToast("请至少选一项");
    event.target.value = "";
    return;
  }

  try {
    showToast(`导入中（${files.length} 个文件）`);
    const formData = new FormData();
    const relPaths = [];
    files.forEach((f) => {
      formData.append("files", f);
      relPaths.push(f.webkitRelativePath || f.name);
    });
    formData.append("relative_paths", JSON.stringify(relPaths));
    formData.append(
      "options",
      JSON.stringify({
        include_projects: sel.include_projects,
        include_chats: sel.include_chats,
        include_settings: sel.include_settings,
        include_gallery: sel.include_gallery,
        include_logs: sel.include_logs
      })
    );

    const res = await fetch("/api/backup/import-uploaded-folder", {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "导入失败");

    const s = data.stats || {};
    const summaryText = `<b>已导入</b><br>剧本 ${s.projects || 0} · 对话 ${s.chats || 0} · 设置 ${s.settings || 0} · 预设 ${s.presets || 0} · 图片 ${s.gallery_images || 0} · 日志 ${s.logs || 0}`;
    showBackupNotice(summaryText, false);
    showToast("已导入");
    await refreshAllAppDataAfterImport();
  } catch (e) {
    showBackupNotice(`导入失败：${escapeHtml(e.message)}`, true);
    showToast("导入失败: " + e.message);
  } finally {
    try {
      event.target.value = "";
    } catch (err) {}
  }
}

window.toggleBackupSubList = toggleBackupSubList;
window.toggleBackupSelectAll = toggleBackupSelectAll;
window.onBackupCatChange = onBackupCatChange;
window.onBackupSubItemChange = onBackupSubItemChange;
window.pickBackupFolder = pickBackupFolder;
window.handleOpenBackupFolder = handleOpenBackupFolder;
window.handleExportBackupToFolder = handleExportBackupToFolder;
window.handleImportBackupFromPath = handleImportBackupFromPath;
window.handleImportBackupFromBrowserFiles = handleImportBackupFromBrowserFiles;

// ================= 手机与外网远程访问（已整合进系统设置弹窗） =================
async function openRemoteModal() {
  openSettingsModal();
}

function copyText(val, tip = "已复制") {
  if (!val) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard
      .writeText(val)
      .then(() => showToast(`${tip}`))
      .catch(() => fallbackCopyText(val, tip));
  } else {
    fallbackCopyText(val, tip);
  }
}

function fallbackCopyText(val, tip) {
  const ta = document.createElement("textarea");
  ta.value = val;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  try {
    document.execCommand("copy");
    showToast(`${tip}`);
  } catch (e) {
    showCustomDialog({ title: "复制", message: "", isPrompt: true, defaultValue: val });
  }
  ta.remove();
}

// ================= 账号专属历史素材图库 =================
async function updateGalleryCountBadge() {
  try {
    const res = await fetch("/api/gallery");
    if (res.ok) {
      const data = await res.json();
      cachedGalleryList = data;
      const count = data.length;
      if (galleryCountBadge) galleryCountBadge.textContent = count;
      if (galleryTotalCount) galleryTotalCount.textContent = count;
    }
  } catch (e) {}
}

async function openGalleryModal() {
  if (galleryModal) galleryModal.style.display = "flex";
  selectedGalleryImageIds.clear();
  updateGallerySelectionUI();
  await renderGalleryGrid();
}

async function renderGalleryGrid() {
  if (!galleryGrid) return;
  galleryGrid.innerHTML = "<div style='color:var(--text-dim);padding:24px;text-align:center;grid-column:1/-1;'>加载中…</div>";

  try {
    const res = await fetch("/api/gallery");
    if (!res.ok) {
      galleryGrid.innerHTML = "<div style='color:var(--text-dim);padding:20px;text-align:center;grid-column:1/-1;'>加载失败</div>";
      return;
    }
    const rawList = await res.json();
    cachedGalleryList = rawList;
    if (galleryCountBadge) galleryCountBadge.textContent = rawList.length;
    if (galleryTotalCount) galleryTotalCount.textContent = rawList.length;

    const activeFolder = window.currentGalleryFolder || "ALL";
    const list = activeFolder === "ALL"
      ? rawList
      : rawList.filter((x) => {
          const f = x.folder || x.folder_id || "默认图库";
          return f === activeFolder || (activeFolder === "场景CG" && String(x.filename || "").startsWith("AI_"));
        });

    if (list.length === 0) {
      galleryGrid.innerHTML = "";
      if (galleryEmptyHint) galleryEmptyHint.style.display = "block";
      return;
    }

    if (galleryEmptyHint) galleryEmptyHint.style.display = "none";
    galleryGrid.innerHTML = "";

    list.forEach((item) => {
      const card = document.createElement("button");
      card.type = "button";
      const isSelected = selectedGalleryImageIds.has(item.id);
      card.className = "gallery-card" + (isSelected ? " selected" : "");
      card.dataset.id = item.id;
      card.title = "点击勾选";

      const img = document.createElement("img");
      img.className = "gallery-thumb";
      img.loading = "lazy";
      img.src = `/api/gallery/thumb/${item.id}`;
      img.alt = item.filename || item.id;

      const checkIcon = document.createElement("span");
      checkIcon.className = "gallery-check-icon";
      checkIcon.innerHTML = isSelected ? "✓" : "";

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "gallery-del-btn";
      delBtn.title = "删除";
      delBtn.innerHTML = "删除";
      delBtn.onclick = async (e) => {
        e.stopPropagation();
        e.preventDefault();
        const confirmed = await showCustomDialog({
          title: "删除图片",
          message: "删除此图片？不可恢复"
        });
        if (confirmed) {
          await deleteGalleryImage(item.id);
        }
      };

      const quickInsertBtn = document.createElement("button");
      quickInsertBtn.type = "button";
      quickInsertBtn.className = "gallery-quick-insert";
      quickInsertBtn.title = "导入";
      quickInsertBtn.textContent = "导入";
      quickInsertBtn.onclick = async (e) => {
        e.stopPropagation();
        e.preventDefault();
        await insertSingleGalleryImage(item.id);
      };

      card.appendChild(img);
      card.appendChild(checkIcon);
      card.appendChild(delBtn);

      const fname = item.filename || "";
      if (fname && !fname.startsWith("img_")) {
        const fnameTag = document.createElement("span");
        fnameTag.className = "gallery-filename-tag";
        fnameTag.textContent = fname.replace(/\.(jpeg|jpg|png|webp)$/i, "");
        card.appendChild(fnameTag);
      }

      card.appendChild(quickInsertBtn);

      card.onclick = () => {
        if (selectedGalleryImageIds.has(item.id)) {
          selectedGalleryImageIds.delete(item.id);
          card.classList.remove("selected");
          checkIcon.innerHTML = "";
        } else {
          selectedGalleryImageIds.add(item.id);
          card.classList.add("selected");
          checkIcon.innerHTML = "✓";
        }
        updateGallerySelectionUI();
      };

      card.ondblclick = async (e) => {
        e.preventDefault();
        await insertSingleGalleryImage(item.id);
      };

      galleryGrid.appendChild(card);
    });
  } catch (err) {
    galleryGrid.innerHTML = "<div style='color:var(--text-dim);padding:20px;text-align:center;grid-column:1/-1;'>网络错误</div>";
  }
}

async function handleDeduplicateGallery() {
  const btn = document.getElementById("btnDeduplicateGallery");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "去重中...";
  }
  try {
    const res = await fetch("/api/gallery/deduplicate", { method: "POST" });
    if (res.ok) {
      const data = await res.json();
      selectedGalleryImageIds.clear();
      updateGallerySelectionUI();
      await renderGalleryGrid();
      if (data.removed > 0) {
        showToast(`已清理 ${data.removed} 张，剩余 ${data.after} 张`);
      } else {
        showToast("无重复");
      }
    } else {
      showToast("去重失败");
    }
  } catch (err) {
    showToast("网络异常: " + err);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "去重";
    }
  }
}
window.handleDeduplicateGallery = handleDeduplicateGallery;

function selectAllGalleryImages() {
  const curFolder = window.currentGalleryFolder || "ALL";
  cachedGalleryList.forEach((item) => {
    const itemFolder = item.folder || "默认图库";
    if (curFolder === "ALL" || itemFolder === curFolder) {
      selectedGalleryImageIds.add(item.id);
    }
  });
  updateGallerySelectionUI();
  galleryGrid?.querySelectorAll(".gallery-card").forEach((c) => {
    c.classList.add("selected");
    const icon = c.querySelector(".gallery-check-icon");
    if (icon) icon.innerHTML = "✓";
  });
}

function clearSelectionGalleryImages() {
  selectedGalleryImageIds.clear();
  updateGallerySelectionUI();
  galleryGrid?.querySelectorAll(".gallery-card").forEach((c) => {
    c.classList.remove("selected");
    const icon = c.querySelector(".gallery-check-icon");
    if (icon) icon.innerHTML = "";
  });
}

function updateGallerySelectionUI() {
  const count = selectedGalleryImageIds.size;
  if (gallerySelectedCount) gallerySelectedCount.textContent = count;
  if (btnInsertSelectedImages) {
    btnInsertSelectedImages.disabled = false;
    btnInsertSelectedImages.textContent = count > 0 ? `导入所选 (${count})` : "导入所选";
  }
}

async function insertSingleGalleryImage(imgId) {
  showToast("导入中…");
  try {
    const res = await fetch(`/api/gallery/data_url/${imgId}`);
    if (res.ok) {
      const data = await res.json();
      if (data.data_url) {
        compressImageToJpeg(data.data_url, 1024, 0.78, (compressed) => {
          const finalUrl = compressed || data.data_url;
          if (!selectedImages.includes(finalUrl)) {
            selectedImages.push(finalUrl);
          }
          renderImagePreviews();
          if (galleryModal) galleryModal.style.display = "none";
          showToast("已导入");
          if (imagePreviewBar) {
            imagePreviewBar.scrollIntoView({ behavior: "smooth", block: "nearest" });
          }
        });
        return;
      }
    }
    showToast("导入失败");
  } catch (err) {
    showToast("网络请求异常: " + err);
  }
}

async function insertSelectedGalleryImages() {
  if (selectedGalleryImageIds.size === 0) {
    showToast("请先选择图片");
    return;
  }
  const ids = Array.from(selectedGalleryImageIds);
  const origText = btnInsertSelectedImages ? btnInsertSelectedImages.textContent : "导入所选";
  if (btnInsertSelectedImages) {
    btnInsertSelectedImages.disabled = true;
    btnInsertSelectedImages.textContent = `导入中 (${ids.length})…`;
  }

  let successCount = 0;
  for (const id of ids) {
    try {
      const res = await fetch(`/api/gallery/data_url/${id}`);
      if (res.ok) {
        const data = await res.json();
        if (data.data_url) {
          await new Promise((resolve) => {
            compressImageToJpeg(data.data_url, 1024, 0.78, (compressed) => {
              const finalUrl = compressed || data.data_url;
              if (!selectedImages.includes(finalUrl)) {
                selectedImages.push(finalUrl);
              }
              successCount++;
              resolve();
            });
          });
        }
      }
    } catch (e) {
      console.error("加载图库图片失败:", e);
    }
  }

  renderImagePreviews();
  if (galleryModal) galleryModal.style.display = "none";
  if (btnInsertSelectedImages) {
    btnInsertSelectedImages.textContent = origText;
    btnInsertSelectedImages.disabled = false;
  }
  showToast(`已导入 ${successCount} 张图片`);
  if (imagePreviewBar) {
    imagePreviewBar.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

async function deleteGalleryImage(id) {
  try {
    await fetch(`/api/gallery/${id}`, { method: "DELETE" });
    selectedGalleryImageIds.delete(id);
    updateGallerySelectionUI();
    await renderGalleryGrid();
    showToast("已删除");
  } catch (err) {
    showToast("删除失败: " + err);
  }
}

async function handleGalleryFileUpload(e) {
  const files = Array.from(e.target.files || []);
  if (!files.length) return;
  showToast(`上传 ${files.length} 张图片…`);

  for (const file of files) {
    await new Promise((resolve) => {
      compressImageToJpeg(file, 1024, 0.78, async (compressed) => {
        if (compressed) {
          await uploadImageToGalleryBackend(compressed, file.name);
        }
        resolve();
      });
    });
  }

  try {
    e.target.value = "";
  } catch (err) {}
  await renderGalleryGrid();
  showToast("已上传");
}

async function uploadImageToGalleryBackend(b64, filename) {
  try {
    const activeFolder =
      window.currentGalleryFolder && window.currentGalleryFolder !== "ALL"
        ? window.currentGalleryFolder
        : "默认图库";
    await fetch("/api/gallery/upload", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_base64: b64, filename: filename, folder: activeFolder })
    });
    updateGalleryCountBadge();
  } catch (err) {
    console.error("自动归档素材库失败:", err);
  }
}

// ================= 账号安全中心与修改密码 =================
async function openUserModal() {
  if (userModal) userModal.style.display = "flex";
  if (changePwdBox) changePwdBox.style.display = "none";

  try {
    const res = await fetch("/api/auth/me");
    if (!res.ok) return;
    const data = await res.json();
    const user = data.user;

    if (userModalName) userModalName.textContent = user.username;
    if (currDeviceName) currDeviceName.textContent = user.current_device || "未知设备";
    if (currClientIp) currClientIp.textContent = user.current_ip || "127.0.0.1";

    if (loginHistoryTableBody) {
      loginHistoryTableBody.innerHTML = "";
      const history = user.login_history || [];
      if (history.length === 0) {
        loginHistoryTableBody.innerHTML = "<tr><td colspan='3' style='text-align:center;padding:14px;'>暂无记录</td></tr>";
      } else {
        history.forEach((h) => {
          const tr = document.createElement("tr");
          const dateStr = new Date(h.time * 1000).toLocaleString("zh-CN", { hour12: false });
          tr.innerHTML = `
            <td>${escapeHtml(dateStr)}</td>
            <td><b>${escapeHtml(h.device || "未知设备")}</b></td>
            <td><code>${escapeHtml(h.ip || "127.0.0.1")}</code></td>
          `;
          loginHistoryTableBody.appendChild(tr);
        });
      }
    }
  } catch (err) {
    console.error("加载用户信息失败:", err);
  }
}

async function handleChangePassword() {
  const oldPassword = oldPasswordInput?.value || "";
  const newPassword = newPasswordInput?.value || "";
  if (!oldPassword || !newPassword) {
    showToast("请填写原密码与新密码");
    return;
  }
  if (newPassword.length < 6) {
    showToast("新密码至少 6 位");
    return;
  }

  try {
    const res = await fetch("/api/auth/password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old_password: oldPassword, new_password: newPassword })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || "修改密码失败");
      return;
    }
    if (oldPasswordInput) oldPasswordInput.value = "";
    if (newPasswordInput) newPasswordInput.value = "";
    if (changePwdBox) changePwdBox.style.display = "none";
    showToast("密码已更新");
  } catch (err) {
    showToast("请求失败: " + err);
  }
}

// ================= 全酒馆自由拖拽边框与智能自适应 UI 引擎 =================
let _autoAdaptRafId = 0;
let _lastSidebarW = -1;
let _lastStudioW = -1;
let _lastStageW = -1;

// 全局触控状态追踪：保护手机竖屏 AI 流式生成期间的触摸滑动与按钮点击不被 DOM 重排打断
if (!window._touchGuardInitialized) {
  window._touchGuardInitialized = true;
  window._isUserTouchingScreen = false;
  window._lastTouchInteractionAt = 0;

  const markTouchStart = () => {
    window._isUserTouchingScreen = true;
    window._lastTouchInteractionAt = Date.now();
  };
  const markTouchEnd = () => {
    window._isUserTouchingScreen = false;
    window._lastTouchInteractionAt = Date.now();
  };

  window.addEventListener("touchstart", markTouchStart, { passive: true, capture: true });
  window.addEventListener("touchend", markTouchEnd, { passive: true, capture: true });
  window.addEventListener("touchcancel", markTouchEnd, { passive: true, capture: true });
  window.addEventListener(
    "pointerdown",
    (e) => {
      if (e.pointerType === "touch" || e.pointerType === "pen") {
        markTouchStart();
      }
    },
    { passive: true, capture: true }
  );
  window.addEventListener(
    "pointerup",
    (e) => {
      if (e.pointerType === "touch" || e.pointerType === "pen") {
        markTouchEnd();
      }
    },
    { passive: true, capture: true }
  );
  window.addEventListener(
    "pointercancel",
    (e) => {
      if (e.pointerType === "touch" || e.pointerType === "pen") {
        markTouchEnd();
      }
    },
    { passive: true, capture: true }
  );
}

function isMobileOrPortraitViewport() {
  return window.innerWidth <= 768 || document.body.classList.contains("gui-portrait-mode");
}

function triggerTavernAutoAdaptLayout() {
  if (document.body.classList.contains("panel-animating")) return;

  const sidebar = document.getElementById("sidebar");
  const studio = document.getElementById("studioWorkbenchPane");
  const stage = document.getElementById("chatMainStage");

  if (sidebar && sidebar.offsetParent !== null && !document.body.classList.contains("desktop-sidebar-collapsed")) {
    const sw = Math.round(sidebar.getBoundingClientRect().width);
    if (sw !== _lastSidebarW) {
      _lastSidebarW = sw;
      sidebar.classList.toggle("pane-narrow", sw > 0 && sw < 236);
      sidebar.classList.toggle("pane-wide", sw > 340);
    }
  }

  if (studio && studio.style.display !== "none" && studio.offsetParent !== null) {
    const stw = Math.round(studio.getBoundingClientRect().width);
    if (stw !== _lastStudioW) {
      _lastStudioW = stw;
      studio.classList.toggle("pane-narrow", stw > 0 && stw < 460);
      studio.classList.toggle("pane-wide", stw > 720);
    }
  }

  if (stage && stage.offsetParent !== null) {
    const cw = Math.round(stage.getBoundingClientRect().width);
    if (cw !== _lastStageW) {
      _lastStageW = cw;
      stage.classList.toggle("stage-compact", cw > 0 && cw < 640);
      stage.classList.toggle("stage-medium", cw >= 640 && cw < 880);
      stage.classList.toggle("stage-wide", cw >= 1060);
    }
  }
}

function scheduleTavernAutoAdaptLayout() {
  if (document.body.classList.contains("panel-animating")) return;
  if (_autoAdaptRafId) return;
  _autoAdaptRafId = requestAnimationFrame(() => {
    _autoAdaptRafId = 0;
    triggerTavernAutoAdaptLayout();
  });
}
window.triggerTavernAutoAdaptLayout = scheduleTavernAutoAdaptLayout;

function initUniversalResizersAndAutoAdapt() {
  const root = document.documentElement;

  // 1. 从 localStorage 恢复用户上次拖拽保存的各面板尺寸
  const savedLayout = {
    sidebarWidth: parseInt(localStorage.getItem("tavern_layout_sidebar_width")),
    projectListHeight: parseInt(localStorage.getItem("tavern_layout_project_list_height")),
    studioWidth: parseInt(localStorage.getItem("tavern_layout_studio_width")),
    summaryHeight: parseInt(localStorage.getItem("tavern_layout_summary_height")),
    inputHeight: parseInt(localStorage.getItem("tavern_layout_input_height")),
    msgMaxWidth: parseFloat(localStorage.getItem("tavern_layout_msg_max_width"))
  };

  if (savedLayout.sidebarWidth >= 185 && savedLayout.sidebarWidth <= 560) {
    root.style.setProperty("--sidebar-width", `${savedLayout.sidebarWidth}px`);
  }
  if (savedLayout.projectListHeight >= 48 && savedLayout.projectListHeight <= 520) {
    root.style.setProperty("--project-list-height", `${savedLayout.projectListHeight}px`);
  }
  if (savedLayout.studioWidth >= 300 && savedLayout.studioWidth <= 1200) {
    root.style.setProperty("--studio-width", `${savedLayout.studioWidth}px`);
  }
  if (savedLayout.summaryHeight >= 56 && savedLayout.summaryHeight <= 540) {
    root.style.setProperty("--summary-text-height", `${savedLayout.summaryHeight}px`);
  }
  if (savedLayout.inputHeight >= 48 && savedLayout.inputHeight <= 440) {
    root.style.setProperty("--input-box-height", `${savedLayout.inputHeight}px`);
    if (userInput) userInput.style.height = `${savedLayout.inputHeight}px`;
  }
  if (savedLayout.msgMaxWidth >= 45 && savedLayout.msgMaxWidth <= 100) {
    root.style.setProperty("--msg-max-width", `${savedLayout.msgMaxWidth}%`);
  }

  // 2. 创建实时尺寸悬浮 HUD 指示器
  let hudEl = document.getElementById("resizeDimensionHud");
  if (!hudEl) {
    hudEl = document.createElement("div");
    hudEl.id = "resizeDimensionHud";
    hudEl.className = "resize-dimension-hud";
    hudEl.style.display = "none";
    document.body.appendChild(hudEl);
  }

  function showResizeHud(x, y, text) {
    if (!hudEl) return;
    hudEl.textContent = text;
    hudEl.style.left = `${Math.max(60, Math.min(window.innerWidth - 60, x))}px`;
    hudEl.style.top = `${Math.max(36, Math.min(window.innerHeight - 20, y))}px`;
    hudEl.style.display = "block";
  }

  function hideResizeHud() {
    if (hudEl) hudEl.style.display = "none";
  }

  // 3. 通用拖拽绑定工具函数
  function bindResizerDrag(resizerEl, config) {
    if (!resizerEl) return;
    const { axis, getInitialSize, onDragMove, onReset, storageKey } = config;

    resizerEl.addEventListener("pointerdown", (e) => {
      if (e.pointerType === "touch" || isMobileOrPortraitViewport()) return;
      if (e.button !== 0 && e.pointerType === "mouse") return;
      e.preventDefault();
      resizerEl.setPointerCapture(e.pointerId);
      resizerEl.classList.add("is-dragging");
      document.body.classList.add("is-resizing-pane", axis === "x" ? "is-resizing-col" : "is-resizing-row");

      const startPos = axis === "x" ? e.clientX : e.clientY;
      const startSize = getInitialSize();
      let latestVal = startSize;

      const handleMove = (moveEv) => {
        const currPos = axis === "x" ? moveEv.clientX : moveEv.clientY;
        const delta = currPos - startPos;
        const res = onDragMove(startSize, delta, moveEv);
        if (res && typeof res.value !== "undefined") {
          latestVal = res.value;
          if (res.label) {
            showResizeHud(moveEv.clientX, moveEv.clientY, res.label);
          }
          triggerTavernAutoAdaptLayout();
        }
      };

      const handleUp = (upEv) => {
        try {
          resizerEl.releasePointerCapture(upEv.pointerId);
        } catch (err) {}
        resizerEl.classList.remove("is-dragging");
        document.body.classList.remove("is-resizing-pane", "is-resizing-col", "is-resizing-row");
        hideResizeHud();
        if (storageKey && typeof latestVal !== "undefined") {
          try {
            localStorage.setItem(storageKey, String(latestVal));
          } catch (err) {}
        }
        triggerTavernAutoAdaptLayout();
        resizerEl.removeEventListener("pointermove", handleMove);
        resizerEl.removeEventListener("pointerup", handleUp);
        resizerEl.removeEventListener("pointercancel", handleUp);
      };

      resizerEl.addEventListener("pointermove", handleMove);
      resizerEl.addEventListener("pointerup", handleUp);
      resizerEl.addEventListener("pointercancel", handleUp);
    });

    if (onReset) {
      resizerEl.addEventListener("dblclick", (e) => {
        e.preventDefault();
        e.stopPropagation();
        onReset();
        if (storageKey) {
          try {
            localStorage.removeItem(storageKey);
          } catch (err) {}
        }
        triggerTavernAutoAdaptLayout();
      });
    }
  }

  // (A) 左侧导航栏右边框拖拽 (#resizerSidebar)
  bindResizerDrag(document.getElementById("resizerSidebar"), {
    axis: "x",
    storageKey: "tavern_layout_sidebar_width",
    getInitialSize: () => {
      const sb = document.getElementById("sidebar");
      return sb ? sb.getBoundingClientRect().width : 288;
    },
    onDragMove: (startSize, delta) => {
      const maxW = Math.min(540, Math.round(window.innerWidth * 0.46));
      const nextW = Math.round(Math.max(185, Math.min(maxW, startSize + delta)));
      root.style.setProperty("--sidebar-width", `${nextW}px`);
      return { value: nextW, label: `左侧栏宽度: ${nextW}px` };
    },
    onReset: () => {
      root.style.setProperty("--sidebar-width", "288px");
      showToast("已复位");
    }
  });

  // (B) 左侧栏内「游戏列表」与「对话列表」上下分割边框拖拽 (#resizerSidebarProjects)
  bindResizerDrag(document.getElementById("resizerSidebarProjects"), {
    axis: "y",
    storageKey: "tavern_layout_project_list_height",
    getInitialSize: () => {
      const pl = document.getElementById("projectPillsList");
      return pl ? pl.getBoundingClientRect().height : 126;
    },
    onDragMove: (startSize, delta) => {
      const maxH = Math.min(480, Math.round(window.innerHeight * 0.55));
      const nextH = Math.round(Math.max(48, Math.min(maxH, startSize + delta)));
      root.style.setProperty("--project-list-height", `${nextH}px`);
      return { value: nextH, label: `剧本列表: ${nextH}px` };
    },
    onReset: () => {
      root.style.setProperty("--project-list-height", "126px");
      showToast("已复位");
    }
  });

  // (C) 游戏设置工作台右边框拖拽 (#resizerStudio)
  bindResizerDrag(document.getElementById("resizerStudio"), {
    axis: "x",
    storageKey: "tavern_layout_studio_width",
    getInitialSize: () => {
      const st = document.getElementById("studioWorkbenchPane");
      return st ? st.getBoundingClientRect().width : 540;
    },
    onDragMove: (startSize, delta) => {
      const sb = document.getElementById("sidebar");
      const sbW = sb && sb.offsetParent !== null && !document.body.classList.contains("desktop-sidebar-collapsed")
        ? sb.getBoundingClientRect().width
        : 0;
      const maxW = Math.max(360, window.innerWidth - sbW - 320);
      const nextW = Math.round(Math.max(300, Math.min(maxW, startSize + delta)));
      root.style.setProperty("--studio-width", `${nextW}px`);
      return { value: nextW, label: `剧本设定: ${nextW}px` };
    },
    onReset: () => {
      root.style.setProperty("--studio-width", "540px");
      const st = document.getElementById("studioWorkbenchPane");
      if (st) st.classList.remove("wide-mode");
      showToast("已复位");
    }
  });

  // (D) 前情提要备忘面板顶边框拖拽 (#resizerSummary)
  bindResizerDrag(document.getElementById("resizerSummary"), {
    axis: "y",
    storageKey: "tavern_layout_summary_height",
    getInitialSize: () => {
      const st = document.getElementById("summaryText");
      const se = document.getElementById("summaryEditTextarea");
      if (se && se.offsetParent !== null) return se.getBoundingClientRect().height;
      return st ? st.getBoundingClientRect().height : 150;
    },
    onDragMove: (startSize, delta) => {
      // 向上拉 (delta < 0) 增大前情备忘高度，向下拉减小高度
      const maxH = Math.min(520, Math.round(window.innerHeight * 0.62));
      const nextH = Math.round(Math.max(56, Math.min(maxH, startSize - delta)));
      root.style.setProperty("--summary-text-height", `${nextH}px`);
      return { value: nextH, label: `前情备忘高度: ${nextH}px` };
    },
    onReset: () => {
      root.style.setProperty("--summary-text-height", "150px");
      showToast("已复位");
    }
  });

  // (E) 底部行动输入框顶边框拖拽 (#resizerInputArea)
  bindResizerDrag(document.getElementById("resizerInputArea"), {
    axis: "y",
    storageKey: "tavern_layout_input_height",
    getInitialSize: () => {
      return userInput ? userInput.getBoundingClientRect().height : 66;
    },
    onDragMove: (startSize, delta) => {
      // 向上拉 (delta < 0) 增大输入框高度，向下拉减小高度
      const maxH = Math.min(420, Math.round(window.innerHeight * 0.52));
      const nextH = Math.round(Math.max(48, Math.min(maxH, startSize - delta)));
      root.style.setProperty("--input-box-height", `${nextH}px`);
      if (userInput) userInput.style.height = `${nextH}px`;
      return { value: nextH, label: `行动输入框高度: ${nextH}px` };
    },
    onReset: () => {
      root.style.setProperty("--input-box-height", "66px");
      if (userInput) userInput.style.height = "66px";
      showToast("已复位");
    }
  });

  // (F) 对话消息气泡侧边框拖拽调节气泡最大宽度比例 (.msg-bubble-resizer)
  if (messageContainer) {
    messageContainer.addEventListener("pointerdown", (e) => {
      if (e.pointerType === "touch" || isMobileOrPortraitViewport()) return;
      const handle = e.target.closest(".msg-bubble-resizer");
      if (!handle) return;
      if (e.button !== 0 && e.pointerType === "mouse") return;
      e.preventDefault();
      e.stopPropagation();

      const msgItem = handle.closest(".message-item");
      const isUserMsg = msgItem ? msgItem.classList.contains("user") : false;
      const containerRect = messageContainer.getBoundingClientRect();
      const startX = e.clientX;
      const startPct = parseFloat(getComputedStyle(root).getPropertyValue("--msg-max-width")) || 88;
      let latestPct = startPct;

      handle.setPointerCapture(e.pointerId);
      handle.classList.add("is-dragging");
      document.body.classList.add("is-resizing-pane", "is-resizing-col");

      const onMove = (moveEv) => {
        const dx = moveEv.clientX - startX;
        const signedDx = isUserMsg ? -dx : dx;
        const deltaPct = (signedDx / Math.max(300, containerRect.width)) * 100;
        latestPct = Math.round(Math.max(45, Math.min(100, startPct + deltaPct)) * 10) / 10;
        root.style.setProperty("--msg-max-width", `${latestPct}%`);
        showResizeHud(moveEv.clientX, moveEv.clientY, `消息气泡宽度: ${latestPct}%`);
      };

      const onUp = (upEv) => {
        try {
          handle.releasePointerCapture(upEv.pointerId);
        } catch (err) {}
        handle.classList.remove("is-dragging");
        document.body.classList.remove("is-resizing-pane", "is-resizing-col");
        hideResizeHud();
        try {
          localStorage.setItem("tavern_layout_msg_max_width", String(latestPct));
        } catch (err) {}
        handle.removeEventListener("pointermove", onMove);
        handle.removeEventListener("pointerup", onUp);
        handle.removeEventListener("pointercancel", onUp);
      };

      handle.addEventListener("pointermove", onMove);
      handle.addEventListener("pointerup", onUp);
      handle.addEventListener("pointercancel", onUp);
    });

    messageContainer.addEventListener("dblclick", (e) => {
      const handle = e.target.closest(".msg-bubble-resizer");
      if (!handle) return;
      e.preventDefault();
      e.stopPropagation();
      root.style.setProperty("--msg-max-width", "88%");
      try {
        localStorage.removeItem("tavern_layout_msg_max_width");
      } catch (err) {}
      showToast("已复位");
    });
  }

  // (G) 所有模态弹窗 (.modal-card) 八向自由拖拽边框缩放 + 顶栏拖拽移动
  const directions = ["n", "s", "e", "w", "nw", "ne", "sw", "se"];
  document.querySelectorAll(".modal-card").forEach((card) => {
    if (card.dataset.resizerBound === "1") return;
    card.dataset.resizerBound = "1";

    directions.forEach((dir) => {
      const h = document.createElement("div");
      h.className = `modal-resizer-handle modal-resizer-${dir}`;
      h.dataset.dir = dir;
      h.title = "拖拽调整，双击复位";
      card.appendChild(h);

      h.addEventListener("pointerdown", (e) => {
        if (e.pointerType === "touch" || isMobileOrPortraitViewport()) return;
        if (e.button !== 0 && e.pointerType === "mouse") return;
        e.preventDefault();
        e.stopPropagation();
        h.setPointerCapture(e.pointerId);
        document.body.classList.add("is-resizing-pane");

        const rect = card.getBoundingClientRect();
        const startX = e.clientX;
        const startY = e.clientY;
        const startW = rect.width;
        const startH = rect.height;

        const onMove = (moveEv) => {
          const dx = moveEv.clientX - startX;
          const dy = moveEv.clientY - startY;
          let nextW = startW;
          let nextH = startH;

          if (dir.includes("e")) nextW = startW + dx * 2;
          if (dir.includes("w")) nextW = startW - dx * 2;
          if (dir.includes("s")) nextH = startH + dy * 2;
          if (dir.includes("n")) nextH = startH - dy * 2;

          nextW = Math.round(Math.max(320, Math.min(window.innerWidth * 0.96, nextW)));
          nextH = Math.round(Math.max(240, Math.min(window.innerHeight * 0.94, nextH)));

          card.style.width = `${nextW}px`;
          card.style.maxWidth = `${nextW}px`;
          card.style.height = `${nextH}px`;
          card.style.maxHeight = `${nextH}px`;
          showResizeHud(moveEv.clientX, moveEv.clientY, `弹窗尺寸: ${nextW} × ${nextH}`);
        };

        const onUp = (upEv) => {
          try {
            h.releasePointerCapture(upEv.pointerId);
          } catch (err) {}
          document.body.classList.remove("is-resizing-pane");
          hideResizeHud();
          h.removeEventListener("pointermove", onMove);
          h.removeEventListener("pointerup", onUp);
          h.removeEventListener("pointercancel", onUp);
        };

        h.addEventListener("pointermove", onMove);
        h.addEventListener("pointerup", onUp);
        h.addEventListener("pointercancel", onUp);
      });

      h.addEventListener("dblclick", (e) => {
        e.preventDefault();
        e.stopPropagation();
        card.style.width = "";
        card.style.maxWidth = "";
        card.style.height = "";
        card.style.maxHeight = "";
        card.style.transform = "";
        card.dataset.tx = "0";
        card.dataset.ty = "0";
        showToast("已复位");
      });
    });

    // 模态窗顶部标题栏拖拽移动位置
    const header = card.querySelector(".modal-header");
    if (header) {
      header.addEventListener("pointerdown", (e) => {
        if (e.pointerType === "touch" || isMobileOrPortraitViewport()) return;
        if (e.target.closest("button, input, select, a")) return;
        if (e.button !== 0 && e.pointerType === "mouse") return;
        e.preventDefault();
        header.setPointerCapture(e.pointerId);

        const startX = e.clientX;
        const startY = e.clientY;
        const origTx = parseFloat(card.dataset.tx || "0") || 0;
        const origTy = parseFloat(card.dataset.ty || "0") || 0;

        const onMove = (moveEv) => {
          const nx = origTx + (moveEv.clientX - startX);
          const ny = origTy + (moveEv.clientY - startY);
          card.dataset.tx = String(nx);
          card.dataset.ty = String(ny);
          card.style.transform = `translate(${nx}px, ${ny}px)`;
        };

        const onUp = (upEv) => {
          try {
            header.releasePointerCapture(upEv.pointerId);
          } catch (err) {}
          header.removeEventListener("pointermove", onMove);
          header.removeEventListener("pointerup", onUp);
          header.removeEventListener("pointercancel", onUp);
        };

        header.addEventListener("pointermove", onMove);
        header.addEventListener("pointerup", onUp);
        header.addEventListener("pointercancel", onUp);
      });
    }
  });

  // 4. 启动 ResizeObserver 实时监听所有主容器尺寸变化并自动适配内部布局（rAF 节流 + 动画期间零重排）
  if (typeof ResizeObserver !== "undefined") {
    const ro = new ResizeObserver(() => {
      scheduleTavernAutoAdaptLayout();
    });
    const sb = document.getElementById("sidebar");
    const st = document.getElementById("studioWorkbenchPane");
    const cm = document.getElementById("chatMainStage");
    if (sb) ro.observe(sb);
    if (st) ro.observe(st);
    if (cm) ro.observe(cm);
  }
  window.addEventListener("resize", scheduleTavernAutoAdaptLayout, { passive: true });
  setTimeout(scheduleTavernAutoAdaptLayout, 60);
}

// 暴露全局处理函数，双重兜底确保手机与电脑任何浏览器点击必然响应
window.openGalleryModal = openGalleryModal;
window.handleFileSelectMultiple = handleFileSelectMultiple;
window.handleGalleryFileUpload = handleGalleryFileUpload;
window.openLightbox = function (src) {
  if (!src) return;
  const lb = document.getElementById("imageLightbox") || imageLightbox;
  const lbImg = document.getElementById("lightboxImg") || lightboxImg;
  if (lb && lbImg) {
    lbImg.src = src;
    lb.style.display = "flex";
  }
};

// 启动应用
window.addEventListener("DOMContentLoaded", initApp);

