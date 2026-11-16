// =========================================================================
// AI 跑团工作台 — 游戏设置与新建游戏(高级)工作台 (v7.2)
// =========================================================================

let exploreAppsCache = [];
let exploreUserProjectsCache = [];
let currentExploreCategory = "ALL";
let advancedDraftProject = null;
window.currentGalleryFolder = "ALL";
let galleryFoldersList = ["默认图库", "角色立绘", "场景CG", "道具线索"];
// 当前会话的提示词变量取值（renderChatVariablesBar / updateSessionPromptVar 使用；此前未声明会抛 ReferenceError）
const sessionVariableValues = {};
window.sessionVariableValues = sessionVariableValues;

function isFreeChatProject(proj) {
  if (!proj || typeof proj !== "object") return false;
  if (proj.id === "proj_free_chat" || proj.category === "自由对话") return true;
  const nm = String(proj.name || "").trim();
  return ["自由对话", "自由聊天", "聊天", "日常闲聊", "Free Chat"].includes(nm);
}
window.isFreeChatProject = isFreeChatProject;

function escapeJsAttr(str) {
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

function getIconHtml(iconVal, sizePx = 22, extraStyle = "") {
  if (typeof window.renderProjectIconHtml === "function") {
    return window.renderProjectIconHtml(iconVal, sizePx, extraStyle);
  }
  const raw = String(iconVal || "").trim();
  if (raw.startsWith("/") || raw.startsWith("http://") || raw.startsWith("https://") || raw.startsWith("data:image/")) {
    return `<img src="${escapeHtml(raw)}" alt="图标" style="width:${sizePx}px;height:${sizePx}px;border-radius:6px;object-fit:cover;vertical-align:middle;flex-shrink:0;display:inline-block;${extraStyle}" />`;
  }
  return "";
}

// 统一规范化游戏对象结构
function normalizeProjectClient(proj) {
  if (!proj || typeof proj !== "object") return null;
  proj.icon = proj.icon || proj.avatar || "";
  proj.avatar = proj.icon;
  proj.name = proj.name || "未命名剧本";
  proj.description = proj.description || "";
  proj.detailed_description = proj.detailed_description || "";
  if (proj.card_tier !== "simple" && proj.card_tier !== "advanced") {
    const catTrim = String(proj.category || "").trim();
    proj.card_tier = (proj.simple_mode === true || catTrim === "极速跑团" || catTrim === "简单跑团")
      ? "simple"
      : "advanced";
  }
  if (proj.card_tier === "advanced" && proj.id !== "proj_fast_trpg") {
    proj.simple_mode = false;
    if (["极速跑团", "简单跑团"].includes(String(proj.category || "").trim())) {
      proj.category = "";
    }
  }
  proj.tags = Array.isArray(proj.tags) ? proj.tags : [];
  proj.prefix = proj.prefix || "";
  proj.system_prompt = proj.system_prompt || "";
  proj.suffix = proj.suffix || "";
  proj.system_protocol_prompt = (proj.system_protocol_prompt === undefined || proj.system_protocol_prompt === null)
    ? ""
    : String(proj.system_protocol_prompt);
  proj.ui_modules = Array.isArray(proj.ui_modules) ? proj.ui_modules : [];
  proj.opening_greetings = Array.isArray(proj.opening_greetings) ? proj.opening_greetings : [];
  proj.status_panel_enabled = proj.status_panel_enabled !== false;
  proj.use_global_params = proj.use_global_params !== false;
  proj.auto_summarize = proj.auto_summarize !== false;

  proj.completion_params = Object.assign({
    temperature: 0.68,
    repetition_penalty: 1.05,
    frequency_penalty: 0.05,
    presence_penalty: 0.20,
    top_p: 0.90,
    top_k: 40,
    min_p: 0.06,
    max_tokens: 8192,
    context_mode: "tokens",
    context: proj.max_context_turns || 96,
    max_context_k: 96,
    keep_recent_messages: 6,
    thinking_budget: 1024
  }, proj.completion_params || {});
  if (proj.completion_params.context_mode !== "tokens") {
    proj.completion_params.context_mode = "turns";
  }

  proj.guided_meta = (proj.guided_meta && typeof proj.guided_meta === "object") ? proj.guided_meta : {};
  proj.world_book = Array.isArray(proj.world_book) ? proj.world_book : [];
  proj.regex_replaces = Array.isArray(proj.regex_replaces)
    ? proj.regex_replaces
    : (Array.isArray(proj.regex_scripts) ? proj.regex_scripts : []);
  proj.regex_scripts = proj.regex_replaces;
  proj.cg_book = Array.isArray(proj.cg_book) ? proj.cg_book : [];
  proj.quick_replies = Array.isArray(proj.quick_replies) ? proj.quick_replies.slice(0, 10) : [];
  proj.worldbook_defaults = Object.assign({
    key_region: 6,
    match_type: "OR",
    value_region: "System"
  }, (proj.worldbook_defaults && typeof proj.worldbook_defaults === "object") ? proj.worldbook_defaults : {});
  proj.cg_defaults = Object.assign({
    trigger_source: "ai",
    match_type: "OR",
    display_mode: "chat"
  }, (proj.cg_defaults && typeof proj.cg_defaults === "object") ? proj.cg_defaults : {});

  const resolvedCss = (proj.custom_css !== undefined && proj.custom_css !== null)
    ? String(proj.custom_css)
    : String(proj.appearance?.custom_css || "");
  proj.custom_css = resolvedCss;
  proj.appearance = Object.assign({
    bg_image: proj.bg_image || "",
    bg_mobile: proj.appearance?.bg_mobile || "",
    custom_css: resolvedCss,
    theme_mode: proj.appearance?.theme || "dark"
  }, proj.appearance || {});
  proj.appearance.custom_css = resolvedCss;
  proj.appearance.theme = proj.appearance.theme_mode;
  proj.bg_image = proj.appearance.bg_image;

  return proj;
}
window.normalizeProjectClient = normalizeProjectClient;

function getActiveProjectObj() {
  const pMap = typeof projectsMap !== "undefined" ? projectsMap : window.projectsMap;
  const curId = typeof currentProjectId !== "undefined" ? currentProjectId : window.currentProjectId;
  if (!pMap || !curId) return null;
  const proj = pMap[curId];
  if (!proj) return null;
  return normalizeProjectClient(proj);
}

// =========================================================================
// 1. 游戏设置面板 (#studioWorkbenchPane) 开关与渲染
// =========================================================================
window.toggleStudioWorkbench = function (forceOpen) {
  const pane = document.getElementById("studioWorkbenchPane");
  const resizerStudio = document.getElementById("resizerStudio");
  if (!pane) return;
  const isCurrentlyOpen = pane.style.display !== "none";
  const nextState = typeof forceOpen === "boolean" ? forceOpen : !isCurrentlyOpen;

  if (typeof window.markPanelAnimating === "function") {
    window.markPanelAnimating(220);
  }

  if (nextState) {
    if (typeof window.closeMinimalistPlusPopover === "function") {
      window.closeMinimalistPlusPopover();
    }
    if (typeof window.closeAnySidebarDrawer === "function") {
      window.closeAnySidebarDrawer();
    }
    if (window.innerWidth < 1600) {
      document.body.classList.add("desktop-sidebar-collapsed");
      if (typeof window.syncDrawerToggleButtonUI === "function") {
        window.syncDrawerToggleButtonUI();
      }
    }
    pane.style.display = "flex";
    if (resizerStudio) resizerStudio.style.display = "flex";
    const alreadyRenderedSameProj =
      pane.dataset.renderedProjId === String(currentProjectId || "") &&
      pane.children.length > 0;
    if (alreadyRenderedSameProj) {
      requestAnimationFrame(() => renderStudioWorkbench());
    } else {
      renderStudioWorkbench();
    }
    if (currentProjectId && window.history && window.history.replaceState) {
      window.history.replaceState({}, "", `/zh/app/${encodeURIComponent(currentProjectId)}/configuration`);
    }
  } else {
    pane.style.display = "none";
    if (resizerStudio) resizerStudio.style.display = "none";
    if (window.history && window.history.replaceState) {
      window.history.replaceState({}, "", "/");
    }
  }
  updateNavActiveState();
  if (typeof window.updateScrollBottomBtnVisibility === "function") {
    window.updateScrollBottomBtnVisibility();
  }
  if (typeof window.triggerTavernAutoAdaptLayout === "function") {
    window.triggerTavernAutoAdaptLayout();
  }
};

window.toggleStudioWideMode = function () {
  const pane = document.getElementById("studioWorkbenchPane");
  if (!pane) return;
  const isWide = pane.classList.toggle("wide-mode");
  const targetWidth = isWide ? Math.min(820, Math.round(window.innerWidth * 0.56)) : 540;
  document.documentElement.style.setProperty("--studio-width", `${targetWidth}px`);
  try {
    localStorage.setItem("tavern_layout_studio_width", String(targetWidth));
  } catch (e) {}
  renderStudioWorkbench();
  if (typeof window.triggerTavernAutoAdaptLayout === "function") {
    window.triggerTavernAutoAdaptLayout();
  }
};

window.openStudioTab = function () {
  window.toggleStudioWorkbench(true);
};

function updateNavActiveState() {
  const pane = document.getElementById("studioWorkbenchPane");
  const isOpen = Boolean(pane && pane.style.display !== "none");
  const btnHeaderStudio = document.getElementById("btnHeaderToggleStudio");
  if (btnHeaderStudio) btnHeaderStudio.classList.toggle("btn-primary", isOpen);
  const projBadge = document.getElementById("activeProjectBadge");
  if (projBadge) {
    projBadge.classList.toggle("studio-open-active", isOpen);
    projBadge.setAttribute("aria-expanded", isOpen ? "true" : "false");
  }
}

function renderStudioWorkbench() {
  const pane = document.getElementById("studioWorkbenchPane");
  if (!pane) return;
  const proj = getActiveProjectObj();
  if (!proj) {
    pane.innerHTML = `<div style="padding:24px;color:var(--text-muted);">加载中...</div>`;
    return;
  }

  const prevBody = document.getElementById("studioTabBody");
  const prevFuncBarDetails = document.getElementById("studioFuncBarSubmenu");
  if (prevFuncBarDetails) {
    window._studioFuncBarSubmenuOpen = prevFuncBarDetails.open;
  }
  const prevAdvDetails = document.getElementById("studioAdvancedSubmenu");
  if (prevAdvDetails) {
    window._studioAdvancedSubmenuOpen = prevAdvDetails.open;
  }
  const isSameProj = pane.dataset.renderedProjId === String(proj.id || "");
  const prevScrollTop = isSameProj && prevBody ? prevBody.scrollTop : 0;
  const prevPaneScroll = isSameProj ? pane.scrollTop : 0;
  pane.dataset.renderedProjId = String(proj.id || "");

  const isWide = pane.classList.contains("wide-mode");
  const isDefaultProj = ["proj_fast_trpg", "proj_default", "proj_free_chat"].includes(proj.id);

  pane.innerHTML = `
    <div class="studio-header">
      <div class="studio-title-row">
        <div class="studio-app-badge">
          <span class="studio-header-icon-box" id="studioHeaderIconWrap">${getIconHtml(proj.icon || "", 18)}</span>
          <div class="studio-header-title-group">
            <span class="studio-header-main-title">剧本设定</span>
            <span class="studio-header-proj-pill" id="studioAppBadgeTitle" title="重命名" onclick="window.startInlineProjectRename && window.startInlineProjectRename('${escapeJsAttr(proj.id)}', this, '${escapeJsAttr(proj.name || "未命名剧本")}', '')">${escapeHtml(proj.name || "未命名剧本")}</span>
            ${!isDefaultProj
              ? (getProjectCardTier(proj) === "simple"
                  ? `<span class="proj-tier-tag tier-simple">简易卡</span>`
                  : `<span class="proj-tier-tag tier-advanced">高级卡</span>`)
              : ""
            }
          </div>
        </div>
        <div class="studio-header-actions">
          ${!isDefaultProj
            ? (getProjectCardTier(proj) === "simple"
                ? `<button class="btn btn-xs btn-outline-secondary studio-top-btn" type="button" onclick="window.openGuidedGameCardModal && window.openGuidedGameCardModal('${escapeJsAttr(proj.id)}')" title="打开三步简易创作向导">简易向导</button>
                   <button class="btn btn-xs btn-primary studio-top-btn" type="button" onclick="window.upgradeProjectToAdvanced('${escapeJsAttr(proj.id)}', false)" title="将此简易卡升级为高级游戏卡（解锁世界书、内置CSS、正则与前后置词）">⬆ 升级高级</button>`
                : `<button class="btn btn-xs btn-outline-secondary studio-top-btn" type="button" onclick="window.openAdvancedCreatorForProject && window.openAdvancedCreatorForProject('${escapeJsAttr(proj.id)}')" title="打开全屏三栏高级创作工坊">高级工坊</button>`)
            : ""
          }
          <button class="btn btn-xs btn-outline-secondary studio-top-btn" type="button" onclick="window.exportProjectGameCard && window.exportProjectGameCard('${escapeJsAttr(proj.id)}', 'png')" title="导出为可分享且兼容酒馆的 PNG 游戏卡">导出卡</button>
          <button id="btnExpandStudioWidth" class="btn btn-xs btn-outline-secondary studio-top-btn" type="button" onclick="window.toggleStudioWideMode()" title="宽度">${isWide ? "标准" : "宽屏"}</button>
          <button class="btn btn-xs btn-primary studio-top-btn studio-top-save-btn" type="button" onclick="window.saveStudioProjectConfig(true)">保存</button>
          <button class="btn btn-xs btn-outline-secondary studio-top-btn studio-top-close-btn" type="button" onclick="window.toggleStudioWorkbench(false)" title="收起">关闭</button>
        </div>
      </div>
    </div>
    <div class="studio-body" id="studioTabBody"></div>
    <div class="studio-footer" style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
      <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
        <button class="btn btn-xs btn-outline-secondary" type="button" onclick="window.exportProjectGameCard && window.exportProjectGameCard('${escapeJsAttr(proj.id)}', 'png')">导出 PNG 游戏卡</button>
        <button class="btn btn-xs btn-outline-secondary" type="button" onclick="window.exportProjectGameCard && window.exportProjectGameCard('${escapeJsAttr(proj.id)}', 'json')">导出 JSON</button>
      </div>
      ${!isDefaultProj
        ? `<button class="btn btn-xs btn-outline-danger studio-delete-btn" type="button" onclick="window.handleDeleteProject && window.handleDeleteProject()">删除此游戏卡</button>`
        : ""
      }
    </div>
  `;

  const bodyEl = document.getElementById("studioTabBody");
  if (bodyEl) {
    renderStudioSettingsBody(bodyEl, proj);
    if (prevScrollTop > 0) {
      bodyEl.scrollTop = prevScrollTop;
      requestAnimationFrame(() => {
        bodyEl.scrollTop = prevScrollTop;
      });
    }
  }
  if (prevPaneScroll > 0) {
    pane.scrollTop = prevPaneScroll;
    requestAnimationFrame(() => {
      pane.scrollTop = prevPaneScroll;
    });
  }
  updateNavActiveState();
}
window.renderStudioWorkbench = renderStudioWorkbench;

// 工作台实际滚动容器：#studioTabBody（由 renderStudioWorkbench 重建），兜底为面板本身
function getStudioScrollContainer() {
  return document.getElementById("studioTabBody") || document.getElementById("studioWorkbenchPane");
}

const DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT = [
  "【系统提示词 · 功能栏与跑团编写协议（可自由修改或清空）】：",
  "1. 【🎲 关键节点检定 & 失败推进原则（Fail Forward）】：",
  "   - 普通对话、日常观察、常规移动【绝对不挂检定标签】，直接顺畅推进剧情；",
  "   - 仅在涉及生死搏杀、高风险潜行、撬锁拆弹、识破关键谎言或逆天改命的【戏剧性分水岭】时，才在对应行动选项末尾标注 `【🎲属性检定】`（如 `【🎲潜行检定】`、`【🎲话术检定】`等，凡需投骰的选项必须包含 `🎲` 图标）；",
  "   - 当玩家投掷骰子后，根据事件难度与点数综合判定成败，并在回复开头简要展示检定结果；检定失败时严禁卡死剧情，须以“付出代价或触发新危机”继续推进。",
  "",
  "2. 【思考推演 (`<think>...</think>`) 精炼与防超时规范】：",
  "   - 若当前请求开启了思考推演，请在 `<think>...</think>` 内用简明提纲快速敲定三件事：① 本回合时间跨度与场景推进节点；② 敌方/NPC 的独立主动动作；③ 检定或数值增减结算；",
  "   - **严禁过度思考**：思考篇幅严格控制在 **200~500 字以内**，严禁在思考中写正文草稿、复述前文或反复纠结措辞，提纲列完立即闭合 `</think>` 输出剧情正文！",
  "",
  "3. 【剧情正文栏（主线叙事模块）编写规范】：",
  "   - 每次回复必须【首先直接输出 1000~2000 字沉浸式剧情正文段落】，严禁跳过剧情正文直接输出 `<status>` 状态栏！",
  "   - 严禁在正文中手写 `剧情正文`、`【剧情正文】`、`[剧情正文]`、`<story>` 等标题行或伪标签，严禁将剧情正文写进 `<status>...</status>` 状态块内。",
  "",
  "4. 【状态类功能栏 (`<status>...</status>`) 编写与跨回合继承规范】：",
  "   - 若下方功能栏中包含状态类栏位（如主角状态、装备栏、物品栏、角色关系等），**每一回合**在剧情正文结束后、行动选项之前，都必须输出一个完整的 `<status>...</status>` 纯文本块，严格按功能栏顺序依次写出所有已启用的 `[栏位名]` 及对应分行内容（例如：`[主角状态]`、`[装备栏]`、`[物品栏]`、`[角色关系]`，所有栏位缺一不可！）；",
  "   - **【历史状态栏继承铁律】**：每回合必须在上一轮状态栏的基础上累积继承并更新！严禁因为开启新对话、切换场景或遇到新人物就删去历史状态栏信息（已结识的历史 NPC 关系、已有穿戴装备、未消耗的背包物品必须完整保留在对应栏位中，遇到新角色时在 `[角色关系]` 中追加或更新，绝不可清空历史记录！）；",
  "   - 若开局尚未结识任何 NPC，`[角色关系]` 栏位也必须保留并写明当前人物状态（如 `周围人物: 暂无其他在场NPC(独自行动中)`），绝不可省略 `[角色关系]` 或任何其他状态栏位；",
  "   - 每个槽位/部位/词条独占一行，写成 `字段名: 简短核心内容(补充细节微简介)`；物品栏写成 `物品名称(简短效果说明)x数量`（当某件物品在本回合消耗殆尽、丢弃或失去时，请在本回合将其标注为 `物品名称(已消耗)x0`，后续回合即可移除；若背包已无任何物品则写 `暂无随身物品`）；",
  "   - 功能栏中的『格式参考』仅作为排版样式示范，货币单位、装备防具与背包物品必须严格贴合当前剧本的时代与世界观（如民国银元、赛博信用点、修仙灵石、中世纪银币等），严禁跨题材照抄示例假词或混入违和的网游金币/药剂。",
  "",
  "5. 【行动选项栏（底部交互模块）编写规范】：",
  "   - 若下方功能栏中包含「行动选项」栏位，仅在 `</status>` 闭合标签之后的最底部输出【唯一一次】“你打算怎么做？”及 `1.` ~ `4.` 编号选项（严禁在 `<status>` 之前提前输出选项，严禁重复输出两遍选项！）；",
  "   - 若功能栏中未添加「行动选项」栏位，则结尾自然收束等待玩家自由输入，不输出编号选项。",
  "",
  "6. 【🎬 DM 主动导演节奏与反派独立执行铁律】：",
  "   - **跨幕推进（拒绝微步长原地踏步）**：每回合必须实质性推进至少一个完整的事件节点或显著的时间跨度（严禁每轮仅挪动一两分钟或停在同一动作反复试探）；当玩家输入「自动行动 / 继续」或简短回应时，DM 必须主动引入外部突发变故、新人物/新威胁介入或阶段升级，直接把局势推向下一个真正的抉择拐点；",
  "   - **世界与反派果断执行（拒绝等玩家授权才动手）**：环境与敌对势力具备独立冷酷的行动意志，绝不盲目迎合或等待玩家发号施令；一旦主角潜行暴露、检定失败或陷入劣势，敌方必须按其人设果断执行实质性的压制、缴械、控制、场景转移与状态扣减（同步在 `<status>` 中结算数值与穿戴变化），严禁只放狠话不动手；",
  "   - **拒绝顺从复读**：严禁照抄复述玩家输入的句子，严禁跨回合套用雷同的段落反应模板；底部的 `1.` ~ `4.` 行动选项必须代表真正改变局势走向的差异化分支。"
].join("\n");
window.DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT = DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT;

const DEFAULT_FAST_TRPG_SYSTEM_PROMPT = [
  "【世界观与背景设定】",
  "（在此填写你的世界观、主角身份与开场处境；若不填，则根据你的首句输入或角色卡自动推演。）",
  "",
  "【跑团导演规则】",
  "你是兼具电影镜头感与游戏策划功底的跑团主持（DM），严格遵循以下规则：",
  "1. 沉浸叙事：全程使用第二人称（「你」），细致刻画光影、声响、动作与微表情；严禁代替玩家做决定或抢说玩家台词。",
  "2. 主动推进与真实博弈：",
  "   - 每回合必须实质推进至少一个完整事件节点，严禁原地踏步或照抄复述玩家原话；",
  "   - 世界与敌对势力拥有独立动机与果断执行力，绝不无脑顺从玩家——一旦你暴露、失误或陷入劣势，敌方会直接实施压制、控制、搜身或局势升级，绝不只放狠话不动手。",
  "3. 关键检定：",
  "   - 普通交谈与日常行动不挂检定；仅在生死搏杀、高危潜行、撬锁拆弹、识破谎言等关键分水岭，才在对应选项末尾标注 `【🎲XX检定】`（如 `【🎲潜行检定】`）；",
  "   - 收到投骰点数后，结合难度在下一轮开头演绎成败；检定失败不卡死剧情，以“付出代价或触发新危机”继续推进。",
  "4. 输出格式（正文 + 折叠记忆区 + 底部选项，严禁输出 `<status>` 状态栏）：",
  "   - 第一部分：直接输出 800~1500 字剧情正文（不写任何标题）；",
  "   - 第二部分：正文结束后，用 `<memory>` 标签输出精炼记忆备忘（总计控制在 200 字以内，只记关键锚点不写流水账）：",
  "     <memory>",
  "     [长期记忆]：跨回合累积保留不可逆的重大事件、关键人物关系与秘密、核心契约及重要随身物（保留旧锚点，简短追加新进展）",
  "     [短期记忆]：当前时间地点、眼下处境与身体/衣着状态、在场人物动向及眼前的即时危机（每轮滚动更新）",
  "     </memory>",
  "   - 第三部分：在 `</memory>` 之后的最底部输出唯一一次：",
  "     你打算怎么做？",
  "     1. ……",
  "     2. ……",
  "     3. ……",
  "     4. ……",
  "     （提供 4 个真正改变局势走向的不同行动分支，写完第 4 项立即停止。）"
].join("\n");
window.DEFAULT_FAST_TRPG_SYSTEM_PROMPT = DEFAULT_FAST_TRPG_SYSTEM_PROMPT;

function isBuiltinSystemProject(proj) {
  const pid = String(proj?.id || "").trim();
  return ["proj_fast_trpg", "proj_default", "proj_free_chat"].includes(pid);
}
window.isBuiltinSystemProject = isBuiltinSystemProject;

function getProjectCardTier(proj) {
  if (!proj || typeof proj !== "object") return "advanced";
  if (isBuiltinSystemProject(proj)) return "builtin";
  if (proj.card_tier === "advanced") return "advanced";
  if (proj.card_tier === "simple" || proj.simple_mode === true) return "simple";
  const cat = String(proj.category || "").trim();
  if (cat === "极速跑团" || cat === "简单跑团") return "simple";
  return "advanced";
}
window.getProjectCardTier = getProjectCardTier;

function isSimpleTrpgProject(proj) {
  if (!proj || typeof proj !== "object") return false;
  if (String(proj.id || "").trim() === "proj_fast_trpg") return true;
  if (proj.card_tier === "advanced") return false;
  if (proj.simple_mode === true) return true;
  const cat = String(proj.category || "").trim();
  return cat === "极速跑团" || cat === "简单跑团";
}
window.isSimpleTrpgProject = isSimpleTrpgProject;

window.upgradeProjectToAdvanced = async function (projId, openWorkshopModal = false) {
  const targetId = projId || currentProjectId;
  if (!targetId || ["proj_fast_trpg", "proj_default", "proj_free_chat"].includes(targetId)) return;

  // 若当前正在右侧剧本设定中编辑该卡，先同步未落盘的输入内容
  if (targetId === currentProjectId && document.getElementById("studioWorkbenchPane")?.style.display !== "none") {
    collectCurrentTabFormState();
  }
  const pMap = typeof projectsMap !== "undefined" ? projectsMap : window.projectsMap;
  const srcProj = (pMap && pMap[targetId]) || exploreUserProjectsCache.find((x) => x.id === targetId);
  if (!srcProj) return;

  if (!window.confirm(`确定将简易游戏卡「${srcProj.name || "未命名"}」升级为高级游戏卡吗？\n\n升级后将 100% 保留现有提示词、封面、背景与开场设定，并解锁：\n• 主提示词 / 前置词 / 后置词独立编排\n• 世界书按需触发词条\n• 内置 CSS 皮肤与自定义 UI\n• 正则脚本、快捷回复指令与独立采样参数\n\n（注：升级为高级卡后为单向升级，不可退回简易卡）`)) {
    return;
  }

  const upgradedPayload = JSON.parse(JSON.stringify(normalizeProjectClient(srcProj)));
  upgradedPayload.id = targetId;
  upgradedPayload.card_tier = "advanced";
  upgradedPayload.simple_mode = false;
  if (["极速跑团", "简单跑团"].includes(String(upgradedPayload.category || "").trim())) {
    upgradedPayload.category = "";
  }

  try {
    const res = await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(upgradedPayload)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);

    await loadProjects();
    if (exploreUserProjectsCache.length > 0) {
      exploreUserProjectsCache = exploreUserProjectsCache.map((p) => (p.id === targetId ? data.project : p));
    }
    if (targetId === currentProjectId) {
      applyProjectAppearance(getActiveProjectObj());
      if (typeof window.syncCotToggleUI === "function") window.syncCotToggleUI();
    }
    const pane = document.getElementById("studioWorkbenchPane");
    if (pane && pane.style.display !== "none" && targetId === currentProjectId) {
      renderStudioWorkbench();
    }
    showToast(`已将「${data.project.name}」升级为高级游戏卡！`);

    if (openWorkshopModal) {
      await window.openAdvancedCreatorForProject(targetId);
    } else if (document.getElementById("exploreModal")?.style.display !== "none" && !advancedDraftProject) {
      renderExploreModalContent();
    }
  } catch (err) {
    showToast("升级高级游戏卡失败: " + err.message);
  }
};

const _DM_PROACTIVE_RULE_6_JS = [
  "6. 【🎬 DM 主动导演节奏与反派独立执行铁律】：",
  "   - **跨幕推进（拒绝微步长原地踏步）**：每回合必须实质性推进至少一个完整的事件节点或显著的时间跨度（严禁每轮仅挪动一两分钟或停在同一动作反复试探）；当玩家输入「自动行动 / 继续」或简短回应时，DM 必须主动引入外部突发变故、新人物/新威胁介入或阶段升级，直接把局势推向下一个真正的抉择拐点；",
  "   - **世界与反派果断执行（拒绝等玩家授权才动手）**：环境与敌对势力具备独立冷酷的行动意志，绝不盲目迎合或等待玩家发号施令；一旦主角潜行暴露、检定失败或陷入劣势，敌方必须按其人设果断执行实质性的压制、缴械、控制、场景转移与状态扣减（同步在 `<status>` 中结算数值与穿戴变化），严禁只放狠话不动手；",
  "   - **拒绝顺从复读**：严禁照抄复述玩家输入的句子，严禁跨回合套用雷同的段落反应模板；底部的 `1.` ~ `4.` 行动选项必须代表真正改变局势走向的差异化分支。"
].join("\n");

function upgradeLegacyGlobalProtocolPrompt(rawPrompt, allowEmpty = true) {
  if (rawPrompt === null || rawPrompt === undefined) return "";
  let clean = String(rawPrompt).trim();
  if (!clean) return "";
  clean = clean.replace(/\s*\{\{UI_MODULES_SPEC\}\}\s*$/g, "").replace(/\n*[67]\.\s*【🧩?\s*当前模块出场顺序[\s\S]*$/g, "").trim();
  const oldSec2 = [
    "2. 【思考推演栏 (`<think>...</think>`) 编写规范】：",
    "   - 仅当下方功能栏中包含「思考推演」栏位时，才在 `<think>...</think>` 标签内推演当前局势因果、NPC 独立动机与检定阈值；",
    "   - 若功能栏中未添加「思考推演」栏位，严禁输出 `<think>` 或 `<thinking>` 标签，直接输出剧情正文。"
  ].join("\n");
  const newSec2 = [
    "2. 【思考推演 (`<think>...</think>`) 精炼与防超时规范】：",
    "   - 若当前请求开启了思考推演，请在 `<think>...</think>` 内用简明提纲快速敲定三件事：① 本回合时间跨度与场景推进节点；② 敌方/NPC 的独立主动动作；③ 检定或数值增减结算；",
    "   - **严禁过度思考**：思考篇幅严格控制在 **200~500 字以内**，严禁在思考中写正文草稿、复述前文或反复纠结措辞，提纲列完立即闭合 `</think>` 输出剧情正文！"
  ].join("\n");
  if (clean.includes(oldSec2)) {
    clean = clean.replace(oldSec2, newSec2);
  }
  const oldSec4Header = "4. 【状态类功能栏 (`<status>...</status>`) 编写规范】：";
  if (clean.includes(oldSec4Header)) {
    clean = clean.replace(oldSec4Header, "4. 【状态类功能栏 (`<status>...</status>`) 编写与跨回合继承规范】：");
  }
  const oldRule5 = "   - 若启用了行动选项栏，在对应位置先输出一句简短引导提问（如“你打算怎么做？”），随后另起新行按 `1.` ~ `4.` 分行给出编号选项；";
  const newRule5 =
    "   - 若启用了行动选项栏，全篇回复只能在最底部（`<status>...</status>` 闭合标签之后）输出唯一一次行动选项，严禁在剧情正文末尾（`<status>` 之前）提前输出选项列表；\n" +
    "   - 在 `<status>...</status>` 之后先输出一句简短引导提问（如“你打算怎么做？”），随后另起新行按 `1.` ~ `4.` 分行给出编号选项；";
  if (clean.includes(oldRule5) && !clean.includes("全篇回复只能在最底部")) {
    clean = clean.replace(oldRule5, newRule5);
  }
  const oldInvLine = "- 每个槽位/部位/词条独占一行，写成 `字段名: 简短核心内容(补充细节微简介)`；物品栏写成 `物品名称(简短效果说明)x数量`；";
  const newInvLine = "- 每个槽位/部位/词条独占一行，写成 `字段名: 简短核心内容(补充细节微简介)`；物品栏写成 `物品名称(简短效果说明)x数量`（当某件物品在本回合消耗殆尽、丢弃或失去时，请在本回合将其标注为 `物品名称(已消耗)x0`，后续回合即可移除；若背包已无任何物品则写 `暂无随身物品`）；";
  if (clean.includes(oldInvLine)) {
    clean = clean.replace(oldInvLine, newInvLine);
  }
  const oldExLine = "- 功能栏中的『格式参考』仅作为排版样式示范，请结合当前剧本设定与实际剧情实时更新内容，严禁照抄格式参考中的示例假词。";
  const newExLine = "- 功能栏中的『格式参考』仅作为排版样式示范，货币单位、装备防具与背包物品必须严格贴合当前剧本的时代与世界观（如民国银元、赛博信用点、修仙灵石、中世纪银币等），严禁跨题材照抄示例假词或混入违和的网游金币/药剂。";
  if (clean.includes(oldExLine)) {
    clean = clean.replace(oldExLine, newExLine);
  }
  clean = clean.replace(/\n*6\.\s*【🎬\s*DM\s*主动导演节奏与反派独立执行铁律（拒绝“木头人”顺从应答）】[\s\S]*$/g, "").trim();
  if (
    (clean.includes("【系统提示词 · 功能栏与跑团编写协议") || (clean.includes("1. 【🎲 关键节点检定") && clean.includes("5. 【行动选项栏"))) &&
    !clean.includes("6. 【🎬 DM 主动导演节奏与反派独立执行铁律】")
  ) {
    clean = clean + "\n\n" + _DM_PROACTIVE_RULE_6_JS;
  }
  return clean;
}
window.upgradeLegacyGlobalProtocolPrompt = upgradeLegacyGlobalProtocolPrompt;

const _GENERIC_ALLOWED_WORDS_SET = new Set(["无", "正常", "空", "未知", "暂无", "健康", "完好", "常规", "默认", "..."]);

function deconstructUiModFieldsForPrompt(rawFields, modType = "", modKey = "") {
  let segmented = segmentUiModuleFields(rawFields, modType);
  const bannedSamples = [];
  const collectBanned = (valStr) => {
    const v = String(valStr || "").trim();
    if (!v || _GENERIC_ALLOWED_WORDS_SET.has(v)) return;
    if (v.startsWith("{{") || v.startsWith("<") || v.startsWith("（") || /^\{[^{}]+\}$/.test(v)) return;
    if (/^[xX*#？?。，、….\-_]+$/.test(v)) return;
    if (/^[+-]?\d+(?:\.\d+)?(?:\s*\/\s*\d+(?:\.\d+)?)?%?$/.test(v)) return;
    if (!bannedSamples.includes(v)) bannedSamples.push(v);
  };

  if (modType === "action_choices") {
    if (!segmented) {
      segmented = "1. 【稳健/交涉】常规推进\n2. 【博弈/险招】高风险高回报 【🎲属性检定】\n3. 【环境/道具破局】利用场景或道具动作\n4. 【逆反/鬼点子】出人意料的脑洞";
    }
    const choiceLines = [];
    segmented.split("\n").forEach((ln) => {
      const s = ln.trim();
      if (!s) return;
      const mCh = s.match(/^([1-9][\.、．\)]\s*(?:【[^】]+】|\[[^\]]+\])?)\s*(.*)$/);
      if (mCh) {
        const prefixPart = mCh[1].trim();
        const restPart = mCh[2].trim();
        const hasDice = restPart.includes("🎲") || prefixPart.includes("🎲");
        const cleanDir = restPart.replace(/【?🎲[^】]*】?/g, "").trim();
        collectBanned(cleanDir);
        const dirHint = cleanDir ? `，方向参考：${cleanDir}（严禁直接照抄该参考词）` : "";
        const diceSuffix = hasDice && !prefixPart.includes("🎲") ? " 【🎲对应具体属性检定】" : "";
        choiceLines.push(`${prefixPart} {{结合当前现场局势写出主角具体的行动台词或举动${dirHint}}}${diceSuffix}`);
      } else {
        choiceLines.push(s);
      }
    });
    const compactRef = segmented.split("\n").map((s) => s.trim()).filter(Boolean).join(" / ");
    return { skeletonStr: choiceLines.join("\n"), compactRef, bannedSamples };
  }

  if (!segmented) {
    return { skeletonStr: "{{结合当前剧情动态填写}}", compactRef: "", bannedSamples: [] };
  }

  const paras = segmented.split(/\n{2,}/);
  const skeletonParas = [];
  const refItems = [];
  const totalNonEmptyLines = paras.reduce((acc, p) => acc + p.split("\n").filter((x) => x.trim()).length, 0);

  paras.forEach((para) => {
    const lines = para.split("\n").map((s) => s.trim()).filter(Boolean);
    if (!lines.length) return;

    if ((modType === "inventory_grid" || modType === "inventory") && lines.every((ln) => !ln.includes(":") && !ln.includes("："))) {
      lines.forEach((ln) => {
        refItems.push(ln);
        collectBanned(ln);
      });
      skeletonParas.push("{{当前实际持有的物品名(效果或特征微简介)x数量，每件物品独占一行；若当前无随身物品请写：暂无随身物品}}");
      return;
    }

    const skelLines = [];
    lines.forEach((ln) => {
      refItems.push(ln);
      if (/^(?:---+|\===+|\[[^\]]+\]|【[^】]+】)$/.test(ln)) {
        skelLines.push(ln);
        return;
      }
      if (ln.includes(":") || ln.includes("：")) {
        const idx = ln.search(/[:：]/);
        const kLabel = ln.slice(0, idx).trim();
        const vSample = ln.slice(idx + 1).trim();
        if (totalNonEmptyLines === 1 && modType === "text_card") {
          collectBanned(vSample);
          skelLines.push(
            `{{${kLabel}或具体分项标题1}}: {{2~10字简短核心内容(补充细节或影响微简介)}}`,
            `{{${kLabel}或具体分项标题2}}: {{2~10字简短核心内容(补充细节或影响微简介)}}`,
            `{{${kLabel}或具体分项标题3}}: {{2~10字简短核心内容(补充细节或影响微简介)}}`
          );
          return;
        }
        if (!vSample || vSample.startsWith("{{") || /^\{[^{}]+\}$/.test(vSample)) {
          skelLines.push(`${kLabel}: {{2~8字简短状态或核心词(附括号细节微简介)}}`);
          return;
        }
        collectBanned(vSample);
        const fracM = vSample.match(/\d+\s*\/\s*(\d+)/);
        const hasParen = /\([^)]+\)|（[^）]+）/.test(vSample);
        const hasQty = /[x×]\d+$/i.test(vSample);
        if (fracM) {
          const maxNum = fracM[1];
          skelLines.push(hasParen ? `${kLabel}: {{当前${kLabel}数值/${maxNum} (当前状态简述)}}` : `${kLabel}: {{当前${kLabel}数值/${maxNum}}}`);
        } else if (hasParen && hasQty) {
          skelLines.push(`${kLabel}: {{当前实际${kLabel}名称(简短效果说明)x数量}}`);
        } else if ((modType === "npc_affinity" || modType === "relations") && /^(?:角色|人物|姓名|对象|同伴|NPC)$/i.test(kLabel)) {
          skelLines.push(`${kLabel}: {{当前在场或已结识的NPC角色名（若暂无在场NPC可写：暂无在场角色）}}`);
        } else if (hasParen || modType === "equipment_slots" || modType === "gear" || modType === "text_card") {
          skelLines.push(`${kLabel}: {{结合当前剧情填写${kLabel}的2~8字简短状态或名称(附括号细节微简介)}}`);
        } else if (/^[+-]?\d+(?:\.\d+)?%?$/.test(vSample)) {
          skelLines.push(`${kLabel}: {{当前${kLabel}实际数值}}`);
        } else {
          skelLines.push(`${kLabel}: {{结合当前剧情填写${kLabel}的简短核心词(附括号细节微简介)}}`);
        }
      } else {
        collectBanned(ln);
        const hasParen = /\([^)]+\)|（[^）]+）/.test(ln);
        const hasQty = /[x×]\d+$/i.test(ln);
        if (modType === "npc_affinity" || modType === "relations") {
          skelLines.push("角色: {{当前在场或已结识的NPC角色名（若暂无在场NPC可写：暂无在场角色）}}");
        } else if (totalNonEmptyLines === 1 && modType === "text_card") {
          skelLines.push(
            `{{${modKey || "分项"}标题1}}: {{2~10字简短核心内容(补充细节微简介)}}`,
            `{{${modKey || "分项"}标题2}}: {{2~10字简短核心内容(补充细节微简介)}}`
          );
        } else if (hasParen && hasQty) {
          skelLines.push("{{当前实际物品名(效果微简介)x数量}}");
        } else if (hasParen) {
          skelLines.push("{{结合当前剧情填写的2~8字简短状态或条目(附括号细节微简介)}}");
        } else {
          skelLines.push("{{分项名称}}: {{2~8字简短核心内容(附括号细节微简介)}}");
        }
      }
    });
    if (skelLines.length) skeletonParas.push(skelLines.join("\n"));
  });

  return {
    skeletonStr: skeletonParas.length ? skeletonParas.join("\n\n") : "{{结合当前剧情动态填写}}",
    compactRef: refItems.slice(0, 8).join(" / "),
    bannedSamples
  };
}
window.deconstructUiModFieldsForPrompt = deconstructUiModFieldsForPrompt;

function buildFrontendUiModulesSpecBlock(proj) {
  const mods = getEffectiveUiModules(proj);
  const statusPanelEnabled = proj?.status_panel_enabled !== false;
  const activeMods = mods.filter((m) => m && m.enabled !== false && String(m.key || "").trim());
  const statusMods = activeMods.filter(
    (m) =>
      !["thinking_fold", "story_narrative", "action_choices"].includes(m.type) &&
      !["mod_think", "mod_story", "mod_choices"].includes(m.id)
  );
  const macroOrder = [];
  activeMods.forEach((m) => {
    const grp = m.type === "thinking_fold" ? "think" : m.type === "story_narrative" ? "story" : m.type === "action_choices" ? "choices" : "status";
    if (grp === "status" && !statusPanelEnabled) return;
    if (!macroOrder.includes(grp)) macroOrder.push(grp);
  });

  const thinkMod = activeMods.find((m) => m.type === "thinking_fold" || m.id === "mod_think");
  const storyMod = activeMods.find((m) => m.type === "story_narrative" || m.id === "mod_story");
  const choicesMod = mods.find((m) => m.type === "action_choices" || m.id === "mod_choices");

  const specLines = [
    "【当前模块出场顺序与各功能栏 AI 演算规则（已按用户拖拽顺序排列，请严格按此顺序与分段格式输出）】：",
  ];
  if (!thinkMod) {
    specLines.push("0. 【思考推演前端展示已隐藏】：若底层开启了思考预算，请在 200~500 字内快速完成幕后提纲推演后立即闭合 </think> 进入首个启用的模块！");
  }

  let stepIdx = 1;
  macroOrder.forEach((grp) => {
    if (grp === "think" && thinkMod) {
      const tKey = String(thinkMod.key || "思考推演").trim();
      let tFields = String(thinkMod.fields || "").trim();
      if (tFields && !/<think/i.test(tFields)) {
        tFields = `<think>\n${tFields}\n</think>`;
      }
      const tDesc = String(thinkMod.desc || "").trim();
      specLines.push(`${stepIdx}. 【${tKey} (<think>...</think>)】：`);
      if (tDesc) specLines.push(`   - 推演规则：${tDesc}`);
      if (tFields) specLines.push(tFields);
      stepIdx++;
    } else if (grp === "story" && storyMod) {
      const sKey = String(storyMod.key || "剧情正文").trim();
      const sFields = String(storyMod.fields || "").trim();
      const sDesc = String(storyMod.desc || "").trim();
      const ruleTxt = [sFields, sDesc].map((s) => s.replace(/[。；;\s]+$/g, "")).filter(Boolean).join("；");
      specLines.push(
        `${stepIdx}. 【${sKey}（直接输出沉浸式小说正文段落，前端会自动渲染剧情正文顶栏；严禁在正文中手写「${sKey}」「[${sKey}]」标题行，严禁使用 <details> 折叠包裹正文，严禁将剧情正文写进 <status> 内！）】：${ruleTxt}`
      );
      stepIdx++;
    } else if (grp === "status" && statusPanelEnabled && statusMods.length) {
      const enabledNames = statusMods.map((m) => `[${String(m.key || "状态").trim()}]`).join("、");
      specLines.push(
        `${stepIdx}. 【功能栏 / 状态面板（输出一个 <status>...</status> 块，必须严格按以下拖拽顺序包含全部 ${statusMods.length} 个栏位 ${enabledNames}；每个 [栏位名] 独占一行，内部字段按行/按段分排；注意下方 {{...}} 为动态填空槽位，输出时必须结合当前剧本设定与本轮最新剧情替换为真实内容，严禁保留 {{ }} 符号，严禁照搬『格式结构参考』里的示例假词，严禁在 <status> 内输出 [剧情正文]）】：\n<status>`
      );
      const modDeconInfo = [];
      statusMods.forEach((m) => {
        const k = String(m.key || "状态").trim();
        const decon = deconstructUiModFieldsForPrompt(m.fields || "", m.type || "", k);
        specLines.push(`[${k}]\n${decon.skeletonStr}`);
        modDeconInfo.push({ key: k, desc: String(m.desc || "").trim(), ...decon });
      });
      specLines.push("</status>");
      specLines.push("   ▼ 【各功能栏写给 AI 的介绍、格式结构参考与防照抄铁律】：");
      modDeconInfo.forEach((info, subI) => {
        const ruleHead = info.desc || `请按上方 [${info.key}] 的分行分段字段结构，结合本轮剧情实时更新。`;
        specLines.push(`   - 【${subI + 1}. ${info.key}】：${ruleHead}`);
        if (info.compactRef) {
          specLines.push(`     · 格式结构参考（仅模仿其冒号、括号、数值比例与分段排版样式，非真实状态）：${info.compactRef}`);
        }
        if (info.bannedSamples && info.bannedSamples.length) {
          const quotedBanned = info.bannedSamples.slice(0, 8).join("」「");
          specLines.push(
            `     · 严禁照搬参考词黑名单：格式框中写的「${quotedBanned}」仅作为排版演示假词，与当前剧本真实角色/剧情无关！请务必根据角色设定与本轮实际剧情全新创作替换，严禁在回复中照抄上述参考词！`
          );
        }
      });
      stepIdx++;
    } else if (grp === "choices" && choicesMod && choicesMod.enabled !== false) {
      const cKey = String(choicesMod.key || "行动选项").trim();
      const decon = deconstructUiModFieldsForPrompt(choicesMod.fields || "", "action_choices", cKey);
      const cDesc = String(choicesMod.desc || "").trim();
      const posHint = macroOrder[macroOrder.length - 1] === "choices" ? "（位于整条回复的最底部！）" : `（位于第 ${stepIdx} 步输出）`;
      specLines.push(
        `${stepIdx}. 【${cKey}${posHint}】：${cDesc || "询问“你打算怎么做？”并结合当前现场局势分行给出具体编号选项（切勿只写分类标签或照抄参考词）"}\n${decon.skeletonStr}`
      );
      stepIdx++;
    }
  });

  if (!statusPanelEnabled || !statusMods.length) {
    specLines.push(`${stepIdx}. 【功能栏 / 状态面板已关闭/清空】：本次回复严禁输出 <status>...</status> 状态面板！`);
    stepIdx++;
  }
  if (!choicesMod || choicesMod.enabled === false) {
    specLines.push(`${stepIdx}. 【行动选项已关闭/移除】：本回合结尾无需列出 1.~4. 编号选项，直接停在悬念处等待玩家自由输入。`);
  }
  return specLines.join("\n");
}
window.buildFrontendUiModulesSpecBlock = buildFrontendUiModulesSpecBlock;

function buildLiveUiModulesPromptText(mods) {
  const iconMap = {
    thinking_fold: "",
    story_narrative: "",
    progress_stats: "",
    equipment_slots: "",
    inventory_grid: "",
    npc_affinity: "",
    text_card: "",
    action_choices: "",
    tags: ""
  };
  const list = Array.isArray(mods) ? mods : [];
  const blocks = [];
  list.forEach((mod, idx) => {
    if (!mod || mod.enabled === false) return;
    const mType = mod.type || "progress_stats";
    if (mType === "content_scale" || mod.id === "mod_scale") return;
    const ic = iconMap[mType] || "";
    const k = mod.key !== undefined ? String(mod.key) : "";
    const fieldsLabel = mType === "story_narrative" ? "正文格式" : mType === "thinking_fold" ? "思考格式" : mType === "action_choices" ? "选项格式" : "格式参考";
    const descLabel = mType === "story_narrative" ? "正文栏提示词" : mType === "thinking_fold" ? "思考栏提示词" : mType === "action_choices" ? "选项栏提示词" : "功能栏提示词";
    const fieldsVal = mod.fields !== undefined ? String(mod.fields) : "";
    const descVal = mod.desc !== undefined ? String(mod.desc) : "";
    blocks.push(
      `【#${idx + 1} ${k}】\n` +
      `${fieldsLabel}：\n${fieldsVal}\n` +
      `${descLabel}：\n${descVal}`
    );
  });
  return blocks.join("\n\n");
}
window.buildLiveUiModulesPromptText = buildLiveUiModulesPromptText;

function readLiveUiModulesFromDom() {
  const uiModListEl = document.getElementById("stUiModulesList");
  if (!uiModListEl) {
    const proj = getActiveProjectObj();
    return proj ? getEffectiveUiModules(proj) : [];
  }
  const cards = Array.from(uiModListEl.querySelectorAll(".st-ui-mod-card"));
  return cards.map((card, idx) => ({
    id: card.dataset.modId || `mod_${idx + 1}`,
    type: card.querySelector(".st-uimod-type")?.value || card.dataset.modType || "progress_stats",
    key: card.querySelector(".st-uimod-key")?.value ?? "",
    enabled: !!card.querySelector(".st-uimod-enabled")?.checked,
    fields: card.querySelector(".st-uimod-fields")?.value ?? "",
    desc: card.querySelector(".st-uimod-desc")?.value ?? "",
    v: 2
  }));
}

window.syncUiModulesToPromptBox = function () {
  const box = document.getElementById("stUiModulesPromptBox");
  const liveMods = readLiveUiModulesFromDom();
  if (box) {
    const nextVal = buildLiveUiModulesPromptText(liveMods);
    if (box.value !== nextVal) {
      box.value = nextVal;
    }
  }
  const proj = getActiveProjectObj();
  if (proj) {
    proj.ui_modules = liveMods;
  }
};

window.syncPromptBoxToUiModules = function (rawText) {
  const uiModListEl = document.getElementById("stUiModulesList");
  if (!uiModListEl) return;
  const cards = Array.from(uiModListEl.querySelectorAll(".st-ui-mod-card"));
  if (!cards.length) return;
  const text = String(rawText ?? "");
  const blockRegex = /【#(\d+)\s+(?:(?:🧠|📖|📊|⚔️|🎒|💕|📋|🎯|🏷️|🧩)\s*)?([^】]*)】\r?\n(?:正文格式|思考格式|选项格式|格式参考)[:：]\r?\n([\s\S]*?)\r?\n(?:正文栏提示词|思考栏提示词|选项栏提示词|功能栏提示词)[:：]\r?\n([\s\S]*?)(?=(?:\r?\n){1,2}【#\d+\s+|$)/g;
  let m;
  while ((m = blockRegex.exec(text)) !== null) {
    const seqIdx = parseInt(m[1], 10) - 1;
    const card = cards[seqIdx];
    if (!card) continue;
    const newKey = m[2];
    const newFields = m[3];
    const newDesc = m[4];
    const keyInp = card.querySelector(".st-uimod-key");
    const fieldsInp = card.querySelector(".st-uimod-fields");
    const descInp = card.querySelector(".st-uimod-desc");
    if (keyInp && keyInp.value !== newKey) {
      keyInp.value = newKey;
      delete keyInp._origRoVal;
      delete keyInp._lastEnRoVal;
    }
    if (fieldsInp && fieldsInp.value !== newFields) {
      fieldsInp.value = newFields;
      delete fieldsInp._origRoVal;
      delete fieldsInp._lastEnRoVal;
    }
    if (descInp && descInp.value !== newDesc) {
      descInp.value = newDesc;
      delete descInp._origRoVal;
      delete descInp._lastEnRoVal;
    }
  }
  const proj = getActiveProjectObj();
  if (proj) {
    proj.ui_modules = readLiveUiModulesFromDom();
  }
};

// 标准功能栏模板库（玩家可在「添加栏位」中一键选用，包含思考推演、剧情正文、行动选项及各类状态栏）
const STANDARD_UI_MODULES = [
  {
    id: "mod_think",
    key: "思考推演",
    type: "thinking_fold",
    enabled: true,
    fields: "<think>\n1. 局势与环境因果分析\n2. 在场 NPC 真实动机与反应\n3. 检定判定与剧情走向推演\n</think>",
    desc: "在正式输出剧情前，于 <think> 标签内分段推演当前场景因果、NPC独立动机、环境线索与检定难度阈值。",
    v: 2
  },
  {
    id: "mod_story",
    key: "剧情正文",
    type: "story_narrative",
    enabled: true,
    fields: "第二人称（你）电影感沉浸叙事，输出 1000~2000 字左右，按场景转换与人物对话自然分段",
    desc: "保持第二人称电影感叙事，注重光影、声响、微表情与动作细节；严禁代替玩家做决定或抢写玩家台词，按游戏逻辑与真实性合理推演。",
    v: 2
  },
  {
    id: "mod_stats",
    key: "主角状态",
    type: "progress_stats",
    enabled: true,
    fields: "生命: 100/100\n理智: 80/100\n财富: 随时代背景自适应(如银元/金币/灵石/信用点)\n状态: 正常",
    desc: "根据剧情受创、消耗、交易或休息实时增减生命、理智与世界观对应货币（如银元/金币/灵石/信用点），并动态更新当前 Buff/异常状态。",
    v: 2
  },
  {
    id: "mod_equip",
    key: "装备栏",
    type: "equipment_slots",
    enabled: true,
    fields: "主手: 随身份适配武器或工具(效果简述)\n副手: 无\n防具: 随时代适配衣着护具(防护简述)\n饰品: 关键随身信物(特征简述)",
    desc: "记录主角当前穿戴的主副手器物、衣着防具与饰品槽位，装备名称必须严格匹配当前时代与世界观，每件装备后用括号标注3~10字微简介，穿脱或损毁时同步更新。",
    v: 2
  },
  {
    id: "mod_inv",
    key: "物品栏",
    type: "inventory_grid",
    enabled: true,
    fields: "应急补给(恢复体力或伤势)x2\n随身照明或工具(贴合时代背景)x1\n关键线索物(来源或用途简述)x1",
    desc: "记录主角随身背包中的消耗品、工具与线索，格式为「物品名(简短效果)x数量」，道具名称必须严格符合当前时代背景（严禁在现代/悬疑/科幻/修仙局混入西幻金币或网游药剂），使用或获得道具时实时增减。",
    v: 2
  },
  {
    id: "mod_npc",
    key: "角色关系",
    type: "npc_affinity",
    enabled: true,
    fields: "角色: 关键角色\n好感: 50/100\n态度: 中立审视\n动态: 正注视着你的一举一动",
    desc: "追踪在场或已结识关键 NPC 对主角的好感度(0~100)、当前态度倾向以及眼下的动作/心理动态。",
    v: 2
  },
  {
    id: "mod_info",
    key: "情报卡",
    type: "text_card",
    enabled: true,
    fields: "当前目标: 查明异常源头(推进主线)\n环境线索: 现场遗留可疑痕迹(可进一步调查)\n潜在危机: 暗处似有视线窥探(需保持警惕)",
    desc: "每回合根据现场局势更新当前主线目标、关键环境线索与潜在危险提示，每个分项独占一行。",
    v: 2
  },
  {
    id: "mod_choices",
    key: "行动选项",
    type: "action_choices",
    enabled: true,
    fields: "1. 稳健推进或现场调查交涉的具体行动\n2. 高风险高回报的险招博弈行动 【🎲属性检定】\n3. 利用现场环境细节或随身道具破局的具体行动\n4. 出人意料的逆反操作或脑洞奇招",
    desc: "询问“你打算怎么做？”，结合当前现场局势分行给出 4 个差异化具体行动选项（稳健调查或交涉 / 险招博弈[需投骰时在句末挂🎲检定] / 环境道具破局 / 逆反奇招；直接写自然行动描述，无需带分类中括号前缀）。",
    v: 2
  }
];
window.STANDARD_UI_MODULES = STANDARD_UI_MODULES;

// 跑团模式默认挂载的功能栏（默认不添加 CoT 思考推演栏，玩家若需要可在「添加栏位」中一键添加）
const DEFAULT_UNIVERSAL_UI_MODULES = STANDARD_UI_MODULES
  .filter((m) => m.id !== "mod_think" && m.id !== "mod_info")
  .map((m) => ({ ...m }));
window.DEFAULT_UNIVERSAL_UI_MODULES = DEFAULT_UNIVERSAL_UI_MODULES;

function defaultPlaceholderForEmptyField(fieldName, modType = "") {
  const fn = String(fieldName || "").trim();
  if (/生命|体力|精力|理智|精神|耐力|san|hp|mp|sp|护盾/i.test(fn)) {
    return "100/100";
  }
  if (/好感|数值|进度|经验|敏感|恶堕|堕落|淫乱|羞耻|兴奋|快感|污染|侵蚀|暴露|警戒|声望|忠诚|信任|欲|催眠|驯服|屈服/i.test(fn)) {
    return "0/100";
  }
  if (modType === "progress_stats" && !/处境|状态|地点|位置|时间|穿着|服装|评价|称号|身份|境界|等级|外貌|姿势|神态|关系|态度|动态/.test(fn)) {
    return "0/100";
  }
  return "{当前状态}";
}

function segmentUiModuleFields(rawFields, modType = "") {
  let text = String(rawFields || "")
    .replace(/\r\n/g, "\n")
    .replace(/<!--[\s\S]*?-->/g, "")
    .trim();
  if (!text) return "";
  if (modType === "story_narrative" || modType === "content_scale") return text;

  // 1. 识别从单星号 *部位：* 过渡到双星号 **武器/装备：** 的分组边界，自动插入空行分段
  text = text.replace(/(\*[^*\n]+?\*[^*\n]*?)\s+(\*\*[^*\n:：]+[:：]\*\*)/g, "$1\n\n$2");

  // 2. 拆分内联的 **字段：**、*字段：*、,字段：*、[字段]：
  text = text
    .replace(/(?:[ \t]+|[,，;；|｜]\s*)(?:\*\*|\*)+\s*([^*\n:：|｜]{1,14}?)\s*(?:\*\*|\*)?\s*[:：]\s*(?:\*\*|\*)?\s*/g, "\n$1: ")
    .replace(/[,，;；]\s*([^\s,，;；|｜:：*\n()/]{1,12}?)\s*(?:\*\*|\*)?\s*[:：]\s*(?:\*\*|\*)+\s*/g, "\n$1: ")
    .replace(/[,，;；]\s*([^\s,，;；|｜:：*\n()/]{1,12}?)\s*(?:\*\*|\*)+\s*[:：]\s*/g, "\n$1: ")
    .replace(/^\s*(?:\*\*|\*)+\s*([^*\n:：|｜]{1,14}?)\s*(?:\*\*|\*)?\s*[:：]\s*(?:\*\*|\*)?\s*/gm, "$1: ");

  // 2.5 保护括号内部文本，拆分同行多个普通「字段:」（支持空值冒号如「主武器: 副武器: 头部:」）
  const parenPool = [];
  text = text
    .split("\n")
    .map((rawLn) => {
      if (!rawLn.trim()) return "";
      let masked = rawLn.replace(/\([^()\n]*\)|（[^（）\n]*）/g, (m) => {
        const idx = parenPool.length;
        parenPool.push(m);
        return `__PAREN_MASK_${idx}__`;
      });
      masked = masked.replace(/(?:[ \t]+|[,，;；]\s*)(?![0-9]+\s*[:：])([^\s,，;；|｜:：*\n()]{1,14}?)\s*[:：]\s*/g, "\n$1: ");
      return masked.replace(/__PAREN_MASK_(\d+)__/g, (_, i) => parenPool[Number(i)] || "");
    })
    .join("\n");

  // 3. 拆分挤在一行的编号选项 1. 【...】 2. 【...】
  text = text.replace(/\s+(?=[1-9][\.、．\)]\s*[【\[])/g, "\n");

  // 4. 拆分竖线 | 分隔的多个字段，保留空行分段
  if (text.includes("|") || text.includes("｜")) {
    const paras = text.split(/\n{2,}/).map((para) => {
      const pLines = [];
      para.split("\n").forEach((ln) => {
        const parts = ln.split(/\s*[|｜]\s*/).map((s) => s.trim()).filter(Boolean);
        pLines.push(...parts);
      });
      return pLines.join("\n");
    }).filter(Boolean);
    text = paras.join("\n\n");
  }

  // 5. 物品格：若单行用逗号或顿号分隔了多个道具，拆分为多行并自动补全 x1
  if ((modType === "inventory_grid" || modType === "inventory") && !text.includes("\n") && /[,，、]/.test(text)) {
    const items = text.split(/[,，、]\s*/).map((s) => s.trim()).filter(Boolean);
    if (items.length > 1) {
      text = items.map((it) => (/x\d+$/i.test(it) ? it : `${it}x1`)).join("\n");
    }
  }

  // 6. 清理残留星号、支持纯关键词列表（如「头部 胸部 腹部 私处」或「姓名、身份、性格」）自动补全冒号与占位符
  const allowBareKeywords = !["story_narrative", "thinking_fold", "action_choices", "inventory_grid", "inventory", "content_scale"].includes(modType);
  const cleanedParas = text.split(/\n{2,}/).map((para) => {
    const lines = [];
    para.split("\n").forEach((ln) => {
      let s = ln
        .replace(/(\*\*[:：]\*\*|[:：]\*\*)\d+$/g, ":")
        .replace(/\*\*/g, "")
        .replace(/^[,，;；|｜:：\s]+|[,，;；|｜\s]+$/g, "")
        .trim();
      if (!s) return;
      if (allowBareKeywords && !s.includes(":") && !s.includes("：") && !/^(?:<|\[|【|[1-9][\.、．\)])/.test(s)) {
        const tokens = s.split(/[\s,，、;；]+/).map((t) => t.trim()).filter(Boolean);
        if (tokens.length >= 1 && tokens.length <= 16 && tokens.every((t) => t.length <= 14)) {
          tokens.forEach((tok) => {
            lines.push(`${tok}: ${defaultPlaceholderForEmptyField(tok, modType)}`);
          });
          return;
        }
      }
      const emptyColonMatch = s.match(/^([^:：]{1,18}?)[:：]\s*$/);
      if (emptyColonMatch) {
        const fName = emptyColonMatch[1].trim();
        s = `${fName}: ${defaultPlaceholderForEmptyField(fName, modType)}`;
      }
      lines.push(s);
    });
    return lines.join("\n");
  }).filter(Boolean);

  return cleanedParas.join("\n\n");
}
window.segmentUiModuleFields = segmentUiModuleFields;

window.autoSegmentUiModuleFields = async function (idx) {
  const textarea = document.getElementById(`stUiModFields_${idx}`);
  if (!textarea) return;
  const card = textarea.closest(".st-ui-mod-card");
  const modType = card?.querySelector(".st-uimod-type")?.value || card?.dataset?.modType || "";
  const modKey = card?.querySelector(".st-uimod-key")?.value?.trim() || "";
  let rawVal = textarea.value.trim();
  if (!rawVal && typeof window.smartGenerateUiModuleTemplate === "function") {
    const tpl = window.smartGenerateUiModuleTemplate(modKey, modType);
    rawVal = tpl.fields;
  }
  const formatted = segmentUiModuleFields(rawVal, modType);
  textarea.value = formatted;
  delete textarea._origRoVal;
  delete textarea._lastEnRoVal;
  textarea.style.height = "auto";
  textarea.style.height = Math.min(260, Math.max(52, textarea.scrollHeight)) + "px";
  if (typeof window.syncUiModulesToPromptBox === "function") {
    window.syncUiModulesToPromptBox();
  }
  await window.saveStudioProjectConfig(false);
  if (typeof window.renderMessages === "function") window.renderMessages(undefined, true);
  showToast("已智能整理为标准格式");
};

function fillDefaultUiModuleDesc(mod) {
  const mc = { ...mod, v: 2 };
  const k = String(mc.key || "").trim();
  if (mc.id === "mod_story" || mc.type === "story_narrative" || /^(?:[📖📝]\s*)?(?:剧情正文|正文)(?:栏|模块)?$/i.test(k)) {
    mc.type = "story_narrative";
    mc.id = "mod_story";
  } else if (mc.id === "mod_think" || mc.type === "thinking_fold" || /^(?:[🧠💭]\s*)?(?:思考推演|思考过程|思考|cot)(?:栏|模块)?$/i.test(k)) {
    mc.type = "thinking_fold";
    mc.id = "mod_think";
  } else if (mc.id === "mod_choices" || mc.type === "action_choices" || /^(?:[🎯⚡]\s*)?(?:行动选项|可选行动|选项)(?:栏|模块)?$/i.test(k)) {
    mc.type = "action_choices";
    mc.id = "mod_choices";
  }
  const mType = String(mc.type || "").trim();
  if (mod.fields === undefined && ["thinking_fold", "story_narrative", "action_choices"].includes(mType)) {
    const defMacro = STANDARD_UI_MODULES.find((d) => d.type === mType);
    if (defMacro) mc.fields = defMacro.fields;
  }
  if (mc.fields) {
    mc.fields = segmentUiModuleFields(mc.fields, mType);
  }
  const hasExplicitDesc = mod && Object.prototype.hasOwnProperty.call(mod, "desc") && mod.desc !== undefined && mod.desc !== null;
  const curDesc = String(mc.desc || "").trim();
  const equipDef = STANDARD_UI_MODULES.find((d) => d.id === "mod_equip");
  if (["身体栏", "身体状态"].includes(k) && (!hasExplicitDesc || (equipDef && curDesc === equipDef.desc))) {
    mc.desc = "按上方槽位分行记录主角身体各部位状态与穿戴装备，每个槽位填写2~8字核心状态并用括号附细节微简介，随剧情受创、反应或穿脱实时更新。";
    return mc;
  }
  if (hasExplicitDesc) return mc;
  if (k.includes("剧情进度")) {
    mc.desc = "根据剧情推进自动增长剧情进度，标准为5-15。剧情进度达到100以上时将会触发新的重要剧情。之后进度归零重新计算。";
    return mc;
  }
  const matched = STANDARD_UI_MODULES.find(
    (d) =>
      d.id === mc.id ||
      d.key === k ||
      (["thinking_fold", "story_narrative", "action_choices"].includes(mType) && d.type === mType)
  );
  mc.desc = matched ? matched.desc : `请严格按照 [${k || "当前栏位"}] 的分行分段字段结构，结合本轮最新剧情动态更新各槽位内容。`;
  return mc;
}

function dedupeSingletonUiModules(mods) {
  const result = [];
  const singletonIdx = {};
  (mods || []).forEach((m) => {
    const filled = fillDefaultUiModuleDesc(m);
    const t = String(filled.type || "");
    if (t === "thinking_fold" || t === "story_narrative" || t === "action_choices") {
      if (singletonIdx[t] !== undefined) {
        result[singletonIdx[t]] = filled;
        return;
      }
      singletonIdx[t] = result.length;
    }
    result.push(filled);
  });
  return result;
}

function getEffectiveUiModules(proj) {
  if (!proj || !Array.isArray(proj.ui_modules) || proj.ui_modules.length === 0) {
    return [];
  }
  const raw = proj.ui_modules.filter(
    (m) =>
      m &&
      typeof m === "object" &&
      String(m.key || "").trim() &&
      (window.CONTENT_SCALE_FEATURE_ENABLED || (m.id !== "mod_scale" && m.type !== "content_scale" && String(m.key || "").trim() !== "内容尺度"))
  );
  if (raw.length === 0) {
    return [];
  }
  const deduped = dedupeSingletonUiModules(raw);
  if (deduped.length !== proj.ui_modules.length) {
    proj.ui_modules = deduped;
  }
  return deduped;
}
window.getEffectiveUiModules = getEffectiveUiModules;

function getActiveModelParamOverrideInfo() {
  const headerSel = document.getElementById("headerModelSelect");
  const settingSel = document.getElementById("settingModel");
  const activeModel = (
    (window.currentChatData && window.currentChatData.model) ||
    (headerSel && headerSel.value) ||
    (settingSel && settingSel.value) ||
    (window.globalUserSettings && window.globalUserSettings.model) ||
    ""
  ).trim();
  const modelParamsMap = (window.globalUserSettings && window.globalUserSettings.model_params) || {};
  const rawOverride = activeModel ? modelParamsMap[activeModel] : null;
  const hasModelOverride = Boolean(rawOverride && typeof rawOverride === "object" && Object.keys(rawOverride).length > 0);
  return {
    activeModel,
    hasModelOverride,
    hasOverride: hasModelOverride,
    modelParams: hasModelOverride ? rawOverride : null,
    params: hasModelOverride ? rawOverride : null
  };
}
window.getActiveModelParamOverrideInfo = getActiveModelParamOverrideInfo;

window.jumpToActiveModelParams = function (modelId) {
  const targetModel = modelId || getActiveModelParamOverrideInfo().activeModel;
  if (typeof window.openModelSettingsModal === "function") {
    window.openModelSettingsModal("list");
  }
  if (targetModel && typeof window.openPerModelParamsEditor === "function") {
    window.openPerModelParamsEditor(targetModel);
  }
};

window.disableActiveModelParamsOverride = async function (modelId) {
  const targetModel = modelId || getActiveModelParamOverrideInfo().activeModel;
  if (!targetModel) return;
  try {
    const res = await fetch("/api/settings/model_params", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: targetModel, clear: true })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "关闭失败");
    if (!window.globalUserSettings) window.globalUserSettings = {};
    window.globalUserSettings.model_params = data.model_params || {};
    if (typeof window.renderMinimalistModelList === "function") window.renderMinimalistModelList();
    if (typeof window.updateContextProgressUI === "function") window.updateContextProgressUI();
    if (typeof window.syncGlobalParamsOverrideUI === "function") window.syncGlobalParamsOverrideUI();
    const studioPaneEl = document.getElementById("studioWorkbenchPane");
    if (studioPaneEl && studioPaneEl.style.display !== "none") {
      window.renderStudioWorkbench();
    }
    if (document.getElementById("exploreModal")?.style.display !== "none" && advancedDraftProject) {
      renderAdvancedProjectEditor();
    }
    showToast(`已关闭独立参数：${targetModel}`);
  } catch (err) {
    showToast("关闭失败: " + err.message);
  }
};

window.resetFastTrpgPromptToDefault = function () {
  const sysEl = document.getElementById("stProjSystem");
  if (sysEl) {
    sysEl.value = DEFAULT_FAST_TRPG_SYSTEM_PROMPT;
    window.saveStudioProjectConfig && window.saveStudioProjectConfig(true);
  }
};

window.resetAdvancedTrpgPromptToDefault = function () {
  if (!window.confirm("恢复高级跑团初始模板提示词？")) return;
  const sysEl = document.getElementById("stProjSystem");
  if (sysEl) {
    const intro = "你是一位兼具电影级镜头感与顶级游戏策划功底的【全题材自适应互动叙事主持（AI 导演 / DM）】。\n请根据玩家当前选用的【开场白】或挂载的【角色卡】自动适配世界观与文风（奇幻冒险/悬疑跑团/赛博修仙/日常情感张力），始终以极具画面感与感官细节（光影、声响、气味、微表情）的第二人称（「你」）叙事。NPC 拥有独立动机、秘密与性格底线，绝不无脑顺从玩家；严禁代替玩家做决定或抢说玩家台词。";
    sysEl.value = `${intro}\n\n${DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT}`;
    window.saveStudioProjectConfig && window.saveStudioProjectConfig(true);
  }
};

function renderStudioSettingsBody(container, proj) {
  if (String(proj?.id || "") === "proj_fast_trpg") {
    container.innerHTML = `
      <div class="studio-section-card" style="display:flex;flex-direction:column;gap:8px;">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;">
          <label style="font-size:0.8rem;font-weight:600;color:var(--text-muted);">跑团提示词</label>
          <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.resetFastTrpgPromptToDefault && window.resetFastTrpgPromptToDefault()">恢复初始模板</button>
        </div>
        <textarea id="stProjSystem" class="form-textarea" rows="25" style="width:100%;font-size:13px;line-height:1.62;" placeholder="在此输入跑团提示词..." onblur="window.saveStudioProjectConfig(false)">${escapeHtml(proj.system_prompt || "")}</textarea>
      </div>
    `;
    if (typeof window.translateSubtree === "function") window.translateSubtree(container);
    return;
  }

  if (getProjectCardTier(proj) === "simple") {
    const sBgUrl = proj.appearance?.bg_image || proj.bg_image || "";
    const sPromptLen = (proj.system_prompt || "").length;
    container.innerHTML = `
      <!-- 简易游戏卡升级横幅 -->
      <div class="simple-card-upgrade-banner">
        <div style="flex:1;min-width:200px;">
          <div style="font-size:12.5px;font-weight:700;color:var(--text-main);margin-bottom:2px;">当前为「简易游戏卡」</div>
          <div style="font-size:11.5px;color:var(--text-muted);line-height:1.45;">轻量省心模式。如需配置<b>内置 CSS 皮肤、世界书、前后置词、正则脚本或快捷指令</b>，可一键升级为高级卡。</div>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          <button type="button" class="btn btn-xs btn-secondary" onclick="window.openGuidedGameCardModal('${escapeJsAttr(proj.id)}')">三步向导编辑</button>
          <button type="button" class="btn btn-xs btn-primary" onclick="window.upgradeProjectToAdvanced('${escapeJsAttr(proj.id)}', false)">⬆ 升级为高级卡</button>
        </div>
      </div>

      <!-- 简易卡基础信息 -->
      <div class="studio-section-card">
        <div class="studio-section-header">
          <div class="studio-section-title">基础外观与简介</div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(175px, 1fr));gap:10px;margin-bottom:10px;">
          <div>
            <label style="font-size:0.74rem;color:var(--text-muted);display:block;margin-bottom:4px;">名称与封面</label>
            <div style="display:flex;align-items:center;gap:6px;">
              <div id="stProjIconPreview" class="studio-preview-box" style="width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center;flex-shrink:0;overflow:hidden;cursor:pointer;" onclick="document.getElementById('stProjIconFileInput').click()" title="上传封面">
                ${getIconHtml(proj.icon || "", 32) || `<span style="font-size:15px;color:var(--text-dim);line-height:1;">+</span>`}
              </div>
              <input type="hidden" id="stProjIcon" value="${escapeHtml(proj.icon || "")}" />
              <input type="file" id="stProjIconFileInput" accept="image/*" style="display:none;" onchange="window.handleUploadProjectIcon(event, 'studio')" />
              <input type="text" id="stProjName" class="form-input" value="${escapeHtml(proj.name || "")}" placeholder="游戏卡名称" onblur="window.saveStudioProjectConfig(false)" onkeydown="if(event.key==='Enter'){this.blur();}" style="flex:1;min-width:0;" />
            </div>
          </div>
          <div>
            <label style="font-size:0.74rem;color:var(--text-muted);display:block;margin-bottom:4px;">聊天背景</label>
            <div class="ai-fused-input-group has-value" style="width:100%;">
              <input type="text" id="stBgImageInput" class="ai-fused-input" value="${escapeHtml(sBgUrl)}" placeholder="背景图 URL" onchange="window.updateAppearanceConfig('bg_image', this.value)" style="flex:1;min-width:0;" />
              ${sBgUrl ? `<button type="button" class="ai-fused-sub-btn" onclick="window.updateAppearanceConfig('bg_image', '')">✕</button>` : ""}
              <button type="button" class="ai-fused-sub-btn" onclick="window.pickStudioGalleryAsset('bg_image')">图库</button>
              <button type="button" class="ai-fused-sub-btn" onclick="document.getElementById('stProjBgFileInput').click()">传图</button>
              <input type="file" id="stProjBgFileInput" accept="image/*" style="display:none;" onchange="window.handleUploadProjectBackground(event, 'studio')" />
            </div>
          </div>
        </div>
        <div>
          <label style="font-size:0.74rem;color:var(--text-muted);display:block;margin-bottom:4px;">作品简介（展示给玩家，不影响 AI）</label>
          <textarea id="stProjDesc" rows="2" class="form-textarea" placeholder="一句话介绍你的游戏卡..." onblur="window.saveStudioProjectConfig(false)">${escapeHtml(proj.description || "")}</textarea>
        </div>
      </div>

      <!-- 简易卡跑团提示词 -->
      <div class="studio-section-card" style="display:flex;flex-direction:column;gap:8px;">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;flex-wrap:wrap;">
          <div style="display:flex;align-items:center;gap:6px;">
            <label style="font-size:0.82rem;font-weight:700;color:var(--text-main);">跑团提示词</label>
            <span id="stPromptTokenStat" style="font-size:0.72rem;color:var(--text-muted);">(${sPromptLen} 字)</span>
          </div>
          <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.openGuidedGameCardModal('${escapeJsAttr(proj.id)}')">按角色/世界观分步填写</button>
        </div>
        <textarea id="stProjSystem" class="form-textarea" rows="20" style="width:100%;font-size:13px;line-height:1.62;" placeholder="在此自由编写跑团设定与规则（留空即为纯净 0 提示词）..." oninput="window.updatePromptCharCount(this)" onblur="window.saveStudioProjectConfig(false)">${escapeHtml(proj.system_prompt || "")}</textarea>
      </div>
    `;
    if (typeof window.translateSubtree === "function") window.translateSubtree(container);
    return;
  }
  const sysLen = (proj.system_prompt || "").length;
  const baseCp = proj.completion_params || {};
  const useGlobal = proj.use_global_params !== false;
  const { activeModel, hasModelOverride, modelParams } = getActiveModelParamOverrideInfo();
  const globalCp = window.globalUserSettings || {};
  const effectiveBase = useGlobal ? { ...baseCp, ...globalCp } : baseCp;
  const cp = hasModelOverride ? { ...effectiveBase, ...modelParams } : effectiveBase;
  const isParamsLocked = hasModelOverride || useGlobal;
  const disabledAttr = isParamsLocked ? "disabled" : "";
  const ctxTurns = Number(cp.context ?? (useGlobal ? globalCp.max_context_turns : proj.max_context_turns) ?? 16);
  const bgUrl = proj.appearance?.bg_image || "";
  const uiMods = getEffectiveUiModules(proj);
  const isStatusPanelOn = proj.status_panel_enabled !== false;
  const enabledUiModCount = uiMods.filter(
    (m) => m && m.enabled !== false && m.type !== "content_scale" && m.id !== "mod_scale"
  ).length;
  const curTemp = Number(cp.temperature ?? 0.68);
  const funcBarOpenAttr = window._studioFuncBarSubmenuOpen ? "open" : "";
  const advOpenAttr = window._studioAdvancedSubmenuOpen ? "open" : "";

  container.innerHTML = `
    <!-- 1. 基本信息 -->
    <div class="studio-section-card">
      <div class="studio-section-header" style="flex-wrap:wrap;gap:6px;">
        <div class="studio-section-title">基本信息</div>
        <div class="ai-fused-input-group">
          <input type="text" id="studioGlobalPolishInstruction" class="ai-fused-input" style="width:165px;" placeholder="想法" oninput="this.parentElement.classList.toggle('has-value', !!this.value.trim())" onkeydown="if(event.key==='Enter'){event.preventDefault();this.nextElementSibling.click();}" />
          <button type="button" id="btnPolishAllStudio" class="ai-fused-btn" onclick="window.polishAllStudioFields(this)" title="润色全部">润色</button>
        </div>
      </div>

      <div class="studio-icon-name-grid" style="display:grid;grid-template-columns:repeat(auto-fit, minmax(175px, 1fr));gap:10px;margin-bottom:10px;">
        <div>
          <label style="font-size:0.74rem;color:var(--text-muted);display:block;margin-bottom:4px;">名称</label>
          <div style="display:flex;align-items:center;gap:6px;">
            <div id="stProjIconPreview" class="studio-preview-box" style="width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center;flex-shrink:0;overflow:hidden;cursor:pointer;" onclick="document.getElementById('stProjIconFileInput').click()" title="上传图标">
              ${getIconHtml(proj.icon || "", 32) || `<span style="font-size:15px;color:var(--text-dim);line-height:1;">+</span>`}
            </div>
            <input type="hidden" id="stProjIcon" value="${escapeHtml(proj.icon || "")}" />
            <input type="file" id="stProjIconFileInput" accept="image/*" style="display:none;" onchange="window.handleUploadProjectIcon(event, 'studio')" />
            <input type="text" id="stProjName" class="form-input" value="${escapeHtml(proj.name || "")}" placeholder="名称" onblur="window.saveStudioProjectConfig(false)" onkeydown="if(event.key==='Enter'){this.blur();}" style="flex:1;min-width:0;" />
          </div>
        </div>
        <div>
          <label style="font-size:0.74rem;color:var(--text-muted);display:block;margin-bottom:4px;">电脑背景图</label>
          <div class="ai-fused-input-group has-value" style="width:100%;">
            <input type="text" id="stBgImageInput" class="ai-fused-input" value="${escapeHtml(bgUrl)}" placeholder="横屏背景 URL" onchange="window.updateAppearanceConfig('bg_image', this.value)" style="flex:1;min-width:0;" />
            ${bgUrl ? `<button type="button" class="ai-fused-sub-btn" onclick="window.updateAppearanceConfig('bg_image', '')" title="清除">✕</button>` : ""}
            <button type="button" class="ai-fused-sub-btn" onclick="window.pickStudioGalleryAsset('bg_image')" title="使用图库图片">图库</button>
            <button type="button" class="ai-fused-sub-btn" onclick="document.getElementById('stProjBgFileInput').click()">传图</button>
            <input type="file" id="stProjBgFileInput" accept="image/*" style="display:none;" onchange="window.handleUploadProjectBackground(event, 'studio')" />
          </div>
        </div>
        <div>
          <label style="font-size:0.74rem;color:var(--text-muted);display:block;margin-bottom:4px;">手机竖屏背景</label>
          <div class="ai-fused-input-group has-value" style="width:100%;">
            <input type="text" id="stBgMobileInput" class="ai-fused-input" value="${escapeHtml(proj.appearance?.bg_mobile || "")}" placeholder="竖屏背景 URL" onchange="window.updateAppearanceConfig('bg_mobile', this.value)" style="flex:1;min-width:0;" />
            ${proj.appearance?.bg_mobile ? `<button type="button" class="ai-fused-sub-btn" onclick="window.updateAppearanceConfig('bg_mobile', '')" title="清除">✕</button>` : ""}
            <button type="button" class="ai-fused-sub-btn" onclick="window.pickStudioGalleryAsset('bg_mobile')" title="使用图库图片">图库</button>
            <button type="button" class="ai-fused-sub-btn" onclick="document.getElementById('stProjBgMobileFileInput').click()">传图</button>
            <input type="file" id="stProjBgMobileFileInput" accept="image/*" style="display:none;" onchange="window.handleUploadProjectMobileBackground(event, 'studio')" />
          </div>
        </div>
      </div>

      <div>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:4px;">
          <label style="font-size:0.74rem;color:var(--text-muted);">简介</label>
          <div class="ai-fused-input-group">
            <input type="text" id="stHint_description" class="ai-fused-input" style="width:150px;" placeholder="想法" oninput="this.parentElement.classList.toggle('has-value', !!this.value.trim())" onkeydown="if(event.key==='Enter'){event.preventDefault();this.nextElementSibling.click();}" />
            <button type="button" class="ai-fused-btn" onclick="window.polishStudioField('stProjDesc', 'description', this, 'stHint_description')">润色</button>
          </div>
        </div>
        <textarea id="stProjDesc" rows="2" class="form-textarea" placeholder="简介" onblur="window.saveStudioProjectConfig(false)">${escapeHtml(proj.description || "")}</textarea>
        <input type="hidden" id="stProjTags" value="${escapeHtml((proj.tags || []).join(", "))}" />
      </div>
    </div>

    <!-- 2. 开场白 -->
    <div class="studio-section-card" id="studioOpeningGreetingsSection">
      <div class="studio-section-header" style="flex-wrap:wrap;gap:6px;">
        <div class="studio-section-title">开场白</div>
        <button type="button" class="btn btn-xs btn-primary" onclick="window.addStudioOpeningGreeting()">新增</button>
      </div>
      <div id="stOpeningGreetingsList" style="display:flex;flex-direction:column;gap:8px;">
        ${Array.isArray(proj.opening_greetings) && proj.opening_greetings.length > 0
          ? proj.opening_greetings.map((og, idx) => {
              const titleVal = typeof og === "object" ? (og.title || "") : "";
              const contentVal = typeof og === "string" ? og : (og.content || og.text || "");
              const ogId = (typeof og === "object" && og.id) ? og.id : `og_${idx + 1}`;
              return `
                <div class="st-opening-greeting-item" data-og-id="${escapeHtml(ogId)}" style="display:flex;flex-direction:column;gap:6px;padding:8px 10px;border-radius:8px;border:1px solid var(--border-subtle);background:rgba(128,128,128,0.05);">
                  <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                    <span style="font-size:11.5px;font-weight:700;color:var(--primary);padding:1px 7px;border-radius:999px;background:var(--tc-rgba-99-102-241-0-12, rgba(99,102,241,0.12));white-space:nowrap;">#${idx + 1}</span>
                    <input type="text" class="form-input st-og-title" value="${escapeHtml(titleVal)}" placeholder="标题" onblur="window.saveStudioProjectConfig(false)" onkeydown="if(event.key==='Enter'){this.blur();}" style="flex:1;min-width:120px;padding:4px 8px;font-size:12px;" />
                    <div class="ai-fused-input-group">
                      <input type="text" id="stHint_og_${idx}" class="ai-fused-input st-og-hint" style="width:135px;" placeholder="想法" oninput="this.parentElement.classList.toggle('has-value', !!this.value.trim())" onkeydown="if(event.key==='Enter'){event.preventDefault();this.nextElementSibling.click();}" />
                      <button type="button" class="ai-fused-btn" onclick="window.polishStudioOpeningGreeting(${idx}, this, 'stHint_og_${idx}')">润色</button>
                    </div>
                    <button type="button" class="btn btn-xs btn-danger" onclick="window.removeStudioOpeningGreeting(${idx})" title="删除">删除</button>
                  </div>
                  <textarea rows="3" class="form-textarea st-og-content" placeholder="开场白" onblur="window.saveStudioProjectConfig(false)">${escapeHtml(contentVal)}</textarea>
                </div>
              `;
            }).join("")
          : `<div style="padding:10px 12px;border-radius:8px;border:1px dashed var(--border-subtle);color:var(--text-dim);font-size:0.76rem;text-align:center;">
              暂无开场白
            </div>`
        }
      </div>
    </div>

    <!-- 3. 核心设定 / 提示词 -->
    <div class="studio-section-card">
      <div class="studio-section-header" style="flex-wrap:wrap;gap:6px;">
        <div class="studio-section-title" style="display:flex;align-items:center;gap:6px;">
          <span>核心设定</span>
          <span id="stPromptTokenStat" style="font-size:0.72rem;font-weight:500;color:var(--text-muted);">(${sysLen} 字)</span>
        </div>
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
          <div class="ai-fused-input-group">
            <input type="text" id="stHint_system_prompt" class="ai-fused-input" style="width:165px;" placeholder="想法" oninput="this.parentElement.classList.toggle('has-value', !!this.value.trim())" onkeydown="if(event.key==='Enter'){event.preventDefault();this.nextElementSibling.click();}" />
            <button type="button" class="ai-fused-btn" onclick="window.polishStudioField('stProjSystem', 'system_prompt', this, 'stHint_system_prompt')">润色</button>
          </div>
          ${proj.id === "proj_default" ? `<button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.resetAdvancedTrpgPromptToDefault && window.resetAdvancedTrpgPromptToDefault()">恢复初始模板</button>` : ""}
        </div>
      </div>
      <textarea id="stProjSystem" rows="12" class="form-textarea" placeholder="留空即为纯净 0 提示词；也可在此编写世界观、规则与人物..." oninput="window.updatePromptCharCount(this)" onblur="window.saveStudioProjectConfig(false)">${escapeHtml(proj.system_prompt || "")}</textarea>
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-top:10px;padding-top:10px;border-top:1px solid var(--border-subtle);${hasModelOverride ? "opacity:0.48;pointer-events:none;filter:grayscale(0.6);" : ""}">
        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
          <span style="font-size:0.74rem;color:var(--text-muted);font-weight:600;">风格</span>
          <button type="button" ${disabledAttr} class="btn btn-xs ${Math.abs(curTemp - 0.68) < 0.03 ? 'btn-primary' : 'btn-outline-secondary'}" onclick="window.applyProjectParamPreset('novel')">小说(0.68)</button>
          <button type="button" ${disabledAttr} class="btn btn-xs ${Math.abs(curTemp - 0.62) < 0.03 ? 'btn-primary' : 'btn-outline-secondary'}" onclick="window.applyProjectParamPreset('strict')">严谨(0.62)</button>
          <button type="button" ${disabledAttr} class="btn btn-xs ${curTemp >= 0.74 ? 'btn-primary' : 'btn-outline-secondary'}" onclick="window.applyProjectParamPreset('creative')">发散(0.75)</button>
        </div>
        <div style="display:flex;align-items:center;gap:8px;min-width:170px;">
          <span style="font-size:0.74rem;color:var(--text-muted);white-space:nowrap;">记忆: <b id="stSimpleTurnsVal">${ctxTurns}</b> 轮</span>
          <input type="range" ${disabledAttr} min="4" max="100" step="2" value="${ctxTurns}" style="width:90px;" oninput="document.getElementById('stSimpleTurnsVal').textContent=this.value; window.updateCompletionParam('context', Number(this.value))" />
        </div>
      </div>
      ${hasModelOverride ? `
        <div style="margin-top:8px;padding:7px 10px;border-radius:7px;background:var(--tc-rgba-245-158-11-0-09, rgba(245,158,11,0.09));border:1px solid var(--tc-rgba-245-158-11-0-35, rgba(245,158,11,0.35));display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px;font-size:11.5px;color:var(--tc-fcd34d, #fcd34d);">
          <span>独立参数：<b>${escapeHtml(activeModel)}</b></span>
          <div style="display:flex;gap:6px;flex-shrink:0;">
            <button type="button" class="btn btn-xs btn-primary" style="padding:2px 8px;font-size:11px;" onclick="window.jumpToActiveModelParams('${escapeJsAttr(activeModel)}')">修改</button>
            <button type="button" class="btn btn-xs btn-outline-secondary" style="padding:2px 8px;font-size:11px;" onclick="window.disableActiveModelParamsOverride('${escapeJsAttr(activeModel)}')">关闭</button>
          </div>
        </div>
      ` : ""}
    </div>



    <!-- 5. 功能栏（子菜单：折叠收纳「功能栏」与「功能栏提示词」，实时双向同步） -->
    <details class="advanced-fold-box" id="studioFuncBarSubmenu" ${funcBarOpenAttr} ontoggle="window._studioFuncBarSubmenuOpen = this.open;" style="margin-top:6px;">
      <summary class="advanced-fold-summary" style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
        <span>功能栏</span>
        <span style="font-size:11.5px;font-weight:600;color:${isStatusPanelOn && enabledUiModCount > 0 ? "var(--tc-34d399, #34d399)" : "var(--text-dim)"};margin-left:auto;padding-right:4px;">${isStatusPanelOn ? `已开启 · ${enabledUiModCount} 栏` : "已关闭"}</span>
      </summary>
      <div class="advanced-fold-body" style="display:flex;flex-direction:column;gap:12px;padding-top:12px;">
        <!-- 5.1 功能栏 -->
        <div class="studio-section-card" id="studioUiModulesSection">
          <div class="studio-section-header" style="flex-wrap:wrap;gap:6px;">
            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
              <div class="studio-section-title" title="拖动排序">功能栏</div>
              <label class="checkbox-label" style="font-size:0.75rem;font-weight:600;color:${isStatusPanelOn ? "var(--tc-34d399, #34d399)" : "var(--text-muted)"};" title="状态栏总开关：控制是否向 AI 注入功能栏提示词并在聊天中渲染状态面板">
                <input type="checkbox" class="st-status-panel-sync-cb" ${isStatusPanelOn ? "checked" : ""} onchange="window.handleToggleStudioStatusPanel(this.checked)" />
                <span>${isStatusPanelOn ? "状态栏已开启" : "状态栏已关闭"}</span>
              </label>
            </div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;">
              <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.resetUiModulesToDefault()" title="默认 6 栏">恢复默认</button>
              <button type="button" class="btn btn-xs btn-primary" onclick="window.openAddCustomUiModuleModal()">添加栏位</button>
            </div>
          </div>
          ${!isStatusPanelOn ? `
            <div style="margin-bottom:8px;padding:7px 10px;border-radius:8px;border:1px dashed var(--border-subtle);background:rgba(128,128,128,0.06);font-size:11.5px;color:var(--text-muted);display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;">
              <span>状态栏已关闭：当前不会向 AI 注入功能栏提示词，下方已配置的栏位将保留但不生效。</span>
              <button type="button" class="btn btn-xs btn-primary" onclick="window.handleToggleStudioStatusPanel(true)">一键开启</button>
            </div>
          ` : ""}
          <div id="stUiModulesList" ondragover="window.onUiModListDragOver && window.onUiModListDragOver(event)" ondrop="window.onUiModListDrop && window.onUiModListDrop(event)" style="display:flex;flex-direction:column;gap:8px;position:relative;${!isStatusPanelOn ? "opacity:0.48;" : ""}">
            ${uiMods.length === 0 ? `<div style="padding:10px 12px;border-radius:8px;border:1px dashed var(--border-subtle);color:var(--text-dim);font-size:0.76rem;text-align:center;">暂无启用栏位，勾选「状态栏」或点击上方「恢复默认 / 添加栏位」即可启用</div>` : uiMods.map((mod, idx) => {
              const iconMap = {
                thinking_fold: "",
                story_narrative: "",
                progress_stats: "",
                equipment_slots: "",
                inventory_grid: "",
                npc_affinity: "",
                text_card: "",
                action_choices: "",
                tags: ""
              };
              const placeholderMap = {
                thinking_fold: "<think>\n1. 局势分析\n2. NPC动机\n3. 检定判定\n</think>",
                story_narrative: "第二人称（你）电影感沉浸叙事，输出 1000~2000 字左右，按场景与对话自然分段",
                progress_stats: "生命: 100/100\n理智: 80/100\n财富: 随时代背景自适应\n状态: 正常",
                equipment_slots: "主手: 随身份适配武器或工具\n副手: 无\n防具: 随时代适配衣着护具\n饰品: 关键随身信物",
                inventory_grid: "应急补给(恢复体力或伤势)x2\n随身照明或工具(贴合时代背景)x1",
                npc_affinity: "角色: 关键角色\n好感: 50/100\n态度: 中立\n动态: 正在审视你",
                text_card: "每行一个子项",
                action_choices: "1. 稳健调查或交涉行动\n2. 险招博弈行动 【🎲属性检定】\n3. 利用环境或道具破局\n4. 逆反脑洞奇招"
              };
              const descPlaceholderMap = {
                thinking_fold: "推演规则",
                story_narrative: "叙事规则",
                progress_stats: "状态栏规则",
                equipment_slots: "装备栏规则",
                inventory_grid: "物品栏规则",
                npc_affinity: "关系栏规则",
                text_card: "情报卡规则",
                action_choices: "选项规则"
              };
              const mType = mod.type || "progress_stats";
              const ic = iconMap[mType] || "";
              const isEnabled = mod.enabled !== false;
              const borderCol = isEnabled
                ? (mType === "action_choices" ? "var(--tc-rgba-245-158-11-0-5, rgba(245,158,11,0.5))" : (mType === "story_narrative" ? "var(--tc-rgba-16-185-129-0-45, rgba(16,185,129,0.45))" : "var(--tc-rgba-99-102-241-0-45, rgba(99,102,241,0.45))"))
                : "var(--border-subtle)";
              const bgCol = isEnabled
                ? (mType === "action_choices" ? "var(--tc-rgba-245-158-11-0-07, rgba(245,158,11,0.07))" : (mType === "story_narrative" ? "var(--tc-rgba-16-185-129-0-06, rgba(16,185,129,0.06))" : "var(--tc-rgba-99-102-241-0-07, rgba(99,102,241,0.07))"))
                : "rgba(128,128,128,0.04)";
              const stopDragAttr = `onmousedown="event.stopPropagation();const c=this.closest('.st-ui-mod-card');if(c)c.setAttribute('draggable','false');" onmouseup="const c=this.closest('.st-ui-mod-card');if(c)c.setAttribute('draggable','true');" onblur="const c=this.closest('.st-ui-mod-card');if(c)c.setAttribute('draggable','true');"`;
              return `
                <div class="st-ui-mod-card" draggable="true" data-mod-idx="${idx}" data-mod-id="${escapeHtml(mod.id || `mod_${idx}`)}" data-mod-type="${escapeHtml(mType)}" ondragstart="window.onUiModDragStart && window.onUiModDragStart(event, ${idx})" ondragover="window.onUiModDragOver && window.onUiModDragOver(event, ${idx})" ondragleave="window.onUiModDragLeave && window.onUiModDragLeave(event)" ondrop="window.onUiModDrop && window.onUiModDrop(event, ${idx})" ondragend="window.onUiModDragEnd && window.onUiModDragEnd(event)" style="padding:9px 10px;border-radius:9px;border:1px solid ${borderCol};background:${bgCol};display:flex;flex-direction:column;gap:6px;transition:transform 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;">
                  <div style="display:flex;align-items:center;justify-content:space-between;gap:6px;flex-wrap:wrap;">
                    <div style="display:flex;align-items:center;gap:6px;flex:1;min-width:190px;">
                      <span class="uimod-drag-handle" onmousedown="const c=this.closest('.st-ui-mod-card');if(c)c.setAttribute('draggable','true');" onpointerdown="window.onUiModHandlePointerDown && window.onUiModHandlePointerDown(event)" title="拖动排序" style="cursor:grab;user-select:none;touch-action:none;padding:2px 6px;border-radius:5px;background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.14);font-size:11px;font-weight:700;color:var(--tc-cbd5e1, #cbd5e1);display:inline-flex;align-items:center;gap:2px;flex-shrink:0;">⠿ #<span class="uimod-seq-num">${idx + 1}</span></span>
                      <input type="checkbox" class="st-uimod-enabled" ${isEnabled ? "checked" : ""} onchange="window.handleToggleSingleUiModule(this)" title="启用" style="cursor:pointer;" />
                      <span style="font-size:14px;line-height:1;">${ic}</span>
                      <input type="text" class="form-input st-uimod-key" ${stopDragAttr} value="${escapeHtml(mod.key || "")}" placeholder="名称" oninput="delete this._origRoVal; delete this._lastEnRoVal; window.syncUiModulesToPromptBox && window.syncUiModulesToPromptBox();" onblur="window.saveStudioProjectConfig(false)" onkeydown="if(event.key==='Enter'){this.blur();}" style="width:105px;min-width:80px;flex:0 1 120px;padding:3px 7px;font-size:12px;font-weight:700;" title="名称" />
                      <select class="form-select st-uimod-type" ${stopDragAttr} onchange="this.closest('.st-ui-mod-card').dataset.modType=this.value; window.saveStudioProjectConfig(false); window.renderStudioWorkbench();" style="width:auto;padding:2px 20px 2px 6px;font-size:11px;height:25px;" title="类型">
                        <option value="thinking_fold" ${mType === "thinking_fold" ? "selected" : ""}>思考折叠</option>
                        <option value="story_narrative" ${mType === "story_narrative" ? "selected" : ""}>剧情正文</option>
                        <option value="progress_stats" ${mType === "progress_stats" ? "selected" : ""}>进度条</option>
                        <option value="equipment_slots" ${mType === "equipment_slots" ? "selected" : ""}>装备槽</option>
                        <option value="inventory_grid" ${mType === "inventory_grid" ? "selected" : ""}>物品格</option>
                        <option value="npc_affinity" ${mType === "npc_affinity" ? "selected" : ""}>好感卡</option>
                        <option value="text_card" ${mType === "text_card" || mType === "tags" ? "selected" : ""}>情报卡</option>
                        <option value="action_choices" ${mType === "action_choices" ? "selected" : ""}>行动选项</option>
                      </select>
                    </div>
                    <div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;">
                      <div class="ai-fused-input-group">
                        <input type="text" id="stHint_uimod_${idx}" ${stopDragAttr} class="ai-fused-input" style="width:110px;" placeholder="想法" oninput="this.parentElement.classList.toggle('has-value', !!this.value.trim())" onkeydown="if(event.key==='Enter'){event.preventDefault();this.nextElementSibling.click();}" />
                        <button type="button" class="ai-fused-btn" onclick="window.polishUiModuleField(${idx}, this)">润色</button>
                      </div>
                      <button type="button" class="btn btn-xs btn-outline-secondary" style="padding:1px 5px;font-size:10.5px;" onclick="window.moveUiModule(${idx}, -1)" ${idx === 0 ? "disabled" : ""} title="上移">↑</button>
                      <button type="button" class="btn btn-xs btn-outline-secondary" style="padding:1px 5px;font-size:10.5px;" onclick="window.moveUiModule(${idx}, 1)" ${idx === uiMods.length - 1 ? "disabled" : ""} title="下移">↓</button>
                      <button type="button" class="btn btn-xs btn-danger" style="padding:1px 5px;font-size:10.5px;" onclick="window.removeCustomUiModule(${idx})" title="删除">✕</button>
                    </div>
                  </div>
                  ${mType === "content_scale" ? `
                    <div ${stopDragAttr}>
                      ${window.renderContentScaleSlidersInnerHtml ? window.renderContentScaleSlidersInnerHtml(proj) : ""}
                    </div>
                    <input type="hidden" id="stUiModFields_${idx}" class="st-uimod-fields" value="${escapeHtml(mod.fields || "")}" />
                    <input type="hidden" id="stUiModDesc_${idx}" class="st-uimod-desc" value="${escapeHtml(mod.desc || "")}" />
                  ` : `
                  <div style="display:flex;align-items:flex-start;gap:6px;">
                    <div style="display:flex;flex-direction:column;align-items:flex-start;gap:4px;min-width:82px;padding-top:3px;">
                      <span style="font-size:11px;font-weight:600;color:var(--text-muted);white-space:nowrap;" title="支持直接写空格/顿号分隔词（如：头部 胸部 腹部），失焦或点整理自动转标准格式">${mType === "story_narrative" ? "正文格式" : mType === "thinking_fold" ? "思考格式" : mType === "action_choices" ? "选项格式" : "格式参考"}</span>
                      <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.autoSegmentUiModuleFields(${idx})" style="padding:1px 6px;font-size:10px;line-height:1.3;" title="随便写几个词（如：头部 胸部 腹部）或空冒号，点击即可一键转为标准格式">✨ 整理</button>
                    </div>
                    <textarea id="stUiModFields_${idx}" ${stopDragAttr} rows="${Math.min(10, Math.max(2, (mod.fields || "").split("\n").length, Math.ceil((mod.fields || "").length / 42)))}" class="form-textarea st-uimod-fields" placeholder="${escapeHtml(placeholderMap[mType] || "直接写字段名即可（如：头部 胸部 腹部），会自动转成标准格式")}" oninput="delete this._origRoVal; delete this._lastEnRoVal; this.style.height='auto';this.style.height=Math.min(260,this.scrollHeight)+'px';window.syncUiModulesToPromptBox && window.syncUiModulesToPromptBox();" onblur="if(window.segmentUiModuleFields){const card=this.closest('.st-ui-mod-card');const mt=card?.querySelector('.st-uimod-type')?.value||card?.dataset?.modType||'';const fmt=window.segmentUiModuleFields(this.value,mt);if(fmt&&fmt!==this.value){this.value=fmt;delete this._origRoVal;delete this._lastEnRoVal;this.style.height='auto';this.style.height=Math.min(260,Math.max(52,this.scrollHeight))+'px';window.syncUiModulesToPromptBox&&window.syncUiModulesToPromptBox();}}window.saveStudioProjectConfig(false)" style="flex:1;padding:6px 8px;font-size:11.5px;line-height:1.55;color:var(--text-main);min-height:46px;white-space:pre-wrap;resize:vertical;">${escapeHtml(mod.fields || "")}</textarea>
                  </div>
                  <div style="display:flex;align-items:flex-start;gap:6px;">
                    <span style="font-size:11px;font-weight:600;color:var(--tc-a5b4fc, #a5b4fc);white-space:nowrap;min-width:82px;padding-top:4px;" title="随系统提示词发送">${mType === "story_narrative" ? "正文栏提示词" : mType === "thinking_fold" ? "思考栏提示词" : mType === "action_choices" ? "选项栏提示词" : "功能栏提示词"}</span>
                    <textarea id="stUiModDesc_${idx}" ${stopDragAttr} rows="${Math.min(6, Math.max(2, (mod.desc || "").split("\n").length, Math.ceil((mod.desc || "").length / 46)))}" class="form-textarea st-uimod-desc" placeholder="${escapeHtml(descPlaceholderMap[mType] || "栏位规则")}" oninput="delete this._origRoVal; delete this._lastEnRoVal; this.style.height='auto';this.style.height=Math.min(220,this.scrollHeight)+'px';window.syncUiModulesToPromptBox && window.syncUiModulesToPromptBox();" onblur="window.saveStudioProjectConfig(false)" style="flex:1;padding:4px 8px;font-size:11.5px;line-height:1.45;color:var(--text-main);min-height:42px;resize:vertical;">${escapeHtml(mod.desc || "")}</textarea>
                  </div>
                  `}
                </div>
              `;
            }).join("")}
          </div>
        </div>

        <!-- 5.2 功能栏提示词 -->
        <div class="studio-section-card" id="studioUiModulesPromptSection" style="border-color:var(--tc-rgba-99-102-241-0-42, rgba(99,102,241,0.42));background:var(--tc-rgba-99-102-241-0-04, rgba(99,102,241,0.04));${!isStatusPanelOn ? "opacity:0.48;" : ""}">
          <div class="studio-section-header" style="flex-wrap:wrap;gap:6px;">
            <div class="studio-section-title" style="color:var(--tc-a5b4fc, #a5b4fc);">功能栏提示词</div>
          </div>
          <textarea id="stUiModulesPromptBox" rows="14" class="form-textarea" style="font-size:11.5px;line-height:1.55;white-space:pre-wrap;" placeholder="与功能栏同步" oninput="window.syncPromptBoxToUiModules && window.syncPromptBoxToUiModules(this.value)" onblur="window.saveStudioProjectConfig(false)">${escapeHtml(buildLiveUiModulesPromptText(uiMods))}</textarea>
        </div>
      </div>
    </details>

    <!-- 6. 高级选项 -->
    <details class="advanced-fold-box" id="studioAdvancedSubmenu" ${advOpenAttr} ontoggle="window._studioAdvancedSubmenuOpen = this.open;" style="margin-top:6px;">
      <summary class="advanced-fold-summary">高级</summary>
      <div class="advanced-fold-body" style="display:flex;flex-direction:column;gap:12px;padding-top:12px;">
        <!-- AI 润色模型选择与状态栏总开关 -->
        <div class="studio-section-card" style="padding:8px 12px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
          <div style="display:flex;align-items:center;gap:6px;">
            <span style="font-size:0.75rem;color:var(--text-muted);font-weight:600;">润色模型</span>
            <select id="studioAiModelSelect" class="form-select ai-assist-model-select" style="width:auto;max-width:210px;padding:2px 24px 2px 8px;font-size:12px;height:26px;" onchange="window.handleAiAssistModelChange && window.handleAiAssistModelChange(this.value)"></select>
          </div>
          <label class="checkbox-label" style="font-size:0.78rem;font-weight:600;color:${isStatusPanelOn ? "var(--tc-fcd34d, #fcd34d)" : "var(--text-muted)"};" title="状态栏总开关：控制是否向 AI 注入功能栏提示词并在对话中渲染可视化状态面板">
            <input type="checkbox" id="stStatusPanelEnabled" ${isStatusPanelOn ? "checked" : ""} onchange="window.handleToggleStudioStatusPanel(this.checked)" />
            <span>状态栏</span>
            <span id="stStatusPanelStateHint" style="font-size:0.72rem;font-weight:500;color:${isStatusPanelOn ? "var(--tc-34d399, #34d399)" : "var(--text-dim)"};">(${isStatusPanelOn ? `已开启 · ${enabledUiModCount} 栏` : "已关闭"})</span>
          </label>
        </div>

        <!-- 前后缀提示词 -->
        <div class="studio-section-card">
          <div class="studio-section-header">
            <div class="studio-section-title">前后缀</div>
          </div>
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;">
            <div>
              <div style="display:flex;justify-content:space-between;align-items:center;gap:4px;flex-wrap:wrap;margin-bottom:4px;">
                <small style="color:var(--text-muted);">前置</small>
                <div class="ai-fused-input-group">
                  <input type="text" id="stHint_prefix" class="ai-fused-input" style="width:120px;" placeholder="想法" oninput="this.parentElement.classList.toggle('has-value', !!this.value.trim())" onkeydown="if(event.key==='Enter'){event.preventDefault();this.nextElementSibling.click();}" />
                  <button type="button" class="ai-fused-btn" onclick="window.polishStudioField('stProjPrefix', 'prefix', this, 'stHint_prefix')">润色</button>
                </div>
              </div>
              <textarea id="stProjPrefix" rows="3" class="form-textarea" placeholder="加在每条发言前" onblur="window.saveStudioProjectConfig(false)">${escapeHtml(proj.prefix || "")}</textarea>
            </div>
            <div>
              <div style="display:flex;justify-content:space-between;align-items:center;gap:4px;flex-wrap:wrap;margin-bottom:4px;">
                <small style="color:var(--text-muted);">后置</small>
                <div class="ai-fused-input-group">
                  <input type="text" id="stHint_suffix" class="ai-fused-input" style="width:120px;" placeholder="想法" oninput="this.parentElement.classList.toggle('has-value', !!this.value.trim())" onkeydown="if(event.key==='Enter'){event.preventDefault();this.nextElementSibling.click();}" />
                  <button type="button" class="ai-fused-btn" onclick="window.polishStudioField('stProjSuffix', 'suffix', this, 'stHint_suffix')">润色</button>
                </div>
              </div>
              <textarea id="stProjSuffix" rows="3" class="form-textarea" placeholder="加在每条发言后" onblur="window.saveStudioProjectConfig(false)">${escapeHtml(String(proj.suffix || "").replace(/\n*【当前内容尺度控制[\s\S]*$/, "").trim())}</textarea>
            </div>
          </div>
        </div>

        <!-- 内置 CSS 皮肤与详细介绍 -->
        <div class="studio-section-card" id="studioCustomCssSection">
          <div class="studio-section-header" style="flex-wrap:wrap;gap:6px;">
            <div class="studio-section-title">内置 CSS 栏 <span id="stCssCharStat" class="adv-char-counter">(${(proj.custom_css || "").length} 字)</span></div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;">
              <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.insertStudioCustomUiSnippet()">插入 .custom-ui 骨架</button>
              ${(proj.custom_css || "").trim() ? `<button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.applyStudioCssPreset('')">清空</button>` : ""}
            </div>
          </div>
          <div class="adv-css-preset-bar">
            <span style="font-size:11.5px;color:var(--text-muted);">官方模板：</span>
            ${Object.entries(window.OFFICIAL_CSS_PRESETS || {}).map(([pKey, pCfg]) => `
              <button type="button" class="adv-css-preset-chip" onclick="window.applyStudioCssPreset('${escapeJsAttr(pKey)}')">${escapeHtml(pCfg.label)}</button>
            `).join("")}
          </div>
          <textarea id="stCustomCssInput" rows="5" class="form-textarea adv-code-editor" placeholder="/* 自动隔离作用于聊天舞台 #chatMainStage，支持美化 .bubble 与 .custom-ui */" oninput="document.getElementById('stCssCharStat')&&(document.getElementById('stCssCharStat').textContent='('+this.value.length+' 字)');window.applyProjectCustomCss&&window.applyProjectCustomCss(this.value);" onblur="window.saveStudioProjectConfig(false)">${escapeHtml(proj.custom_css || "")}</textarea>
          <div style="margin-top:8px;">
            <label style="font-size:0.74rem;color:var(--text-muted);display:flex;justify-content:space-between;margin-bottom:4px;">
              <span>详细介绍（展示在欢迎页，支持安全 HTML/Markdown，不影响 AI）</span>
              <span id="stDetailDescStat" class="adv-char-counter">(${(proj.detailed_description || "").length} 字)</span>
            </label>
            <textarea id="stProjDetailedDesc" rows="3" class="form-textarea" placeholder="选填：向玩家展示的排版介绍（自动过滤 <script>/<iframe>）" oninput="document.getElementById('stDetailDescStat')&&(document.getElementById('stDetailDescStat').textContent='('+this.value.length+' 字)')" onblur="window.saveStudioProjectConfig(false)">${escapeHtml(proj.detailed_description || "")}</textarea>
          </div>
        </div>

        <!-- 快捷回复指令 (0/10) -->
        <div class="studio-section-card" id="studioQuickRepliesSection">
          <div class="studio-section-header" style="flex-wrap:wrap;gap:6px;">
            <div class="studio-section-title">快捷回复指令 <span class="adv-char-counter">(${Array.isArray(proj.quick_replies) ? proj.quick_replies.length : 0}/10)</span></div>
            <button type="button" class="btn btn-xs btn-primary" onclick="window.addStudioQuickReply()">+ 新增指令</button>
          </div>
          <div id="stQuickRepliesList" style="display:flex;flex-direction:column;gap:6px;">
            ${Array.isArray(proj.quick_replies) && proj.quick_replies.length > 0
              ? proj.quick_replies.map((qr, idx) => `
                  <div class="st-qr-item" data-qr-id="${escapeHtml(qr.id || `qr_${idx + 1}`)}" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                    <input type="text" class="form-input st-qr-label" value="${escapeHtml(qr.label || "")}" placeholder="按钮名(如:侦查)" onblur="window.saveStudioProjectConfig(false)" style="width:105px;padding:3px 7px;font-size:12px;" />
                    <input type="text" class="form-input st-qr-cmd" value="${escapeHtml(qr.command || "")}" placeholder="/指令(选填)" onblur="window.saveStudioProjectConfig(false)" style="width:92px;padding:3px 7px;font-size:12px;font-family:monospace;" />
                    <input type="text" class="form-input st-qr-content" value="${escapeHtml(qr.content || "")}" placeholder="点击或输入指令后发送给 AI 的预设内容" onblur="window.saveStudioProjectConfig(false)" style="flex:1;min-width:140px;padding:3px 7px;font-size:12px;" />
                    <button type="button" class="btn btn-xs btn-danger" onclick="window.removeStudioQuickReply(${idx})">✕</button>
                  </div>
                `).join("")
              : `<div style="padding:4px 8px;color:var(--text-dim);font-size:0.74rem;">暂无快捷指令（添加后将显示在聊天输入框上方供一键点击）</div>`
            }
          </div>
        </div>

        <!-- 世界书 -->
        <div class="studio-section-card" id="studioWorldbookSection">
          <div class="studio-section-header" style="flex-wrap:wrap;gap:6px;">
            <div class="studio-section-title">世界书 <span style="font-size:11px;font-weight:500;color:var(--text-muted);">(${Array.isArray(proj.world_book) ? proj.world_book.length : 0})</span></div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;">
              <button type="button" class="btn btn-xs btn-outline-secondary" onclick="document.getElementById('stWbImportFile').click()">导入</button>
              <input type="file" id="stWbImportFile" accept=".json" style="display:none;" onchange="window.importStudioWorldbookFile(event)" />
              <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.exportStudioWorldbook()">导出</button>
              <button type="button" class="btn btn-xs btn-primary" onclick="window.addStudioWorldbookEntry()">新增</button>
            </div>
          </div>
          <div id="stWorldbookList" style="display:flex;flex-direction:column;gap:8px;">
            ${Array.isArray(proj.world_book) && proj.world_book.length > 0
              ? proj.world_book.map((wb, idx) => {
                  const wbId = wb.id || `wb_${idx + 1}`;
                  const wbName = wb.name || wb.comment || `词条 #${idx + 1}`;
                  const wbKeys = Array.isArray(wb.keys) ? wb.keys.join(", ") : (wb.keys || "");
                  const rawMt = wb.match_type;
                  const wbMatch = (rawMt === 1 || rawMt === "1" || rawMt === "AND") ? "AND" : ((rawMt === 3 || rawMt === "3" || rawMt === "Regex" || rawMt === "REGEX") ? "Regex" : "OR");
                  const rawVr = wb.value_region;
                  const wbRegion = (rawVr === 2 || rawVr === "2" || rawVr === "Prefix") ? "Prefix" : ((rawVr === 4 || rawVr === "4" || rawVr === "Suffix") ? "Suffix" : "System");
                  const wbEnabled = (wb.enabled !== undefined ? wb.enabled : wb.enable) !== false;
                  const wbContent = wb.content !== undefined ? wb.content : (wb.value || "");
                  return `
                    <div class="st-wb-item" data-wb-id="${escapeHtml(wbId)}" style="display:flex;flex-direction:column;gap:6px;padding:8px 10px;border-radius:8px;border:1px solid var(--border-subtle);background:rgba(128,128,128,0.05);">
                      <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                        <label class="checkbox-label" style="font-size:11.5px;margin:0;">
                          <input type="checkbox" class="st-wb-enabled" ${wbEnabled ? "checked" : ""} onchange="window.saveStudioProjectConfig(false)" />
                          <span>启用</span>
                        </label>
                        <input type="text" class="form-input st-wb-name" value="${escapeHtml(wbName)}" placeholder="名称" onblur="window.saveStudioProjectConfig(false)" style="width:130px;padding:3px 7px;font-size:12px;" />
                        <input type="text" class="form-input st-wb-keys" value="${escapeHtml(wbKeys)}" placeholder="关键词，逗号分隔" onblur="window.saveStudioProjectConfig(false)" style="flex:1;min-width:150px;padding:3px 7px;font-size:12px;" />
                        <select class="form-select st-wb-match" onchange="window.saveStudioProjectConfig(false)" style="width:auto;padding:2px 6px;font-size:11.5px;height:26px;">
                          <option value="OR" ${wbMatch === "OR" ? "selected" : ""}>OR</option>
                          <option value="AND" ${wbMatch === "AND" ? "selected" : ""}>AND</option>
                          <option value="Regex" ${wbMatch === "Regex" || wbMatch === "REGEX" ? "selected" : ""}>Regex</option>
                        </select>
                        <select class="form-select st-wb-region" onchange="window.saveStudioProjectConfig(false)" style="width:auto;padding:2px 6px;font-size:11.5px;height:26px;">
                          <option value="System" ${wbRegion === "System" ? "selected" : ""}>System</option>
                          <option value="Prefix" ${wbRegion === "Prefix" ? "selected" : ""}>Prefix</option>
                          <option value="Suffix" ${wbRegion === "Suffix" ? "selected" : ""}>Suffix</option>
                        </select>
                        <button type="button" class="btn btn-xs btn-danger" onclick="window.removeStudioWorldbookEntry(${idx})">删除</button>
                      </div>
                      <textarea rows="2" class="form-textarea st-wb-content" placeholder="触发内容" onblur="window.saveStudioProjectConfig(false)">${escapeHtml(wbContent)}</textarea>
                    </div>
                  `;
                }).join("")
              : `<div style="padding:6px 10px;color:var(--text-dim);font-size:0.74rem;">暂无词条</div>`
            }
          </div>
        </div>

        <!-- 正则脚本 -->
        <div class="studio-section-card" id="studioRegexSection">
          <div class="studio-section-header" style="flex-wrap:wrap;gap:6px;">
            <div class="studio-section-title">正则脚本 <span style="font-size:11px;font-weight:500;color:var(--text-muted);">(${Array.isArray(proj.regex_replaces) ? proj.regex_replaces.length : 0})</span></div>
            <button type="button" class="btn btn-xs btn-primary" onclick="window.addStudioRegexRule()">新增</button>
          </div>
          <div id="stRegexList" style="display:flex;flex-direction:column;gap:8px;">
            ${Array.isArray(proj.regex_replaces) && proj.regex_replaces.length > 0
              ? proj.regex_replaces.map((rx, idx) => {
                  const rxId = rx.id || `rx_${idx + 1}`;
                  const rxName = rx.name || rx.title || `规则 #${idx + 1}`;
                  const rxPat = rx.pattern !== undefined ? rx.pattern : (rx.match_regex || "");
                  const rxRep = rx.replacement !== undefined ? rx.replacement : (rx.replace_text ?? "");
                  const rawSc = rx.scope;
                  const rxScope = (rawSc === 2 || rawSc === "2" || rawSc === "user") ? "user" : ((rawSc === 1 || rawSc === "1" || rawSc === "assistant") ? "assistant" : "both");
                  const rxEnabled = (rx.enabled !== undefined ? rx.enabled : rx.is_enable) !== false;
                  return `
                    <div class="st-rx-item" data-rx-id="${escapeHtml(rxId)}" style="display:flex;flex-direction:column;gap:6px;padding:8px 10px;border-radius:8px;border:1px solid var(--border-subtle);background:rgba(128,128,128,0.05);">
                      <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                        <label class="checkbox-label" style="font-size:11.5px;margin:0;">
                          <input type="checkbox" class="st-rx-enabled" ${rxEnabled ? "checked" : ""} onchange="window.saveStudioProjectConfig(false)" />
                          <span>启用</span>
                        </label>
                        <input type="text" class="form-input st-rx-name" value="${escapeHtml(rxName)}" placeholder="规则名" onblur="window.saveStudioProjectConfig(false)" style="width:120px;padding:3px 7px;font-size:12px;" />
                        <select class="form-select st-rx-scope" onchange="window.saveStudioProjectConfig(false)" style="width:auto;padding:2px 6px;font-size:11.5px;height:26px;">
                          <option value="both" ${rxScope === "both" ? "selected" : ""}>双向</option>
                          <option value="user" ${rxScope === "user" ? "selected" : ""}>仅玩家</option>
                          <option value="assistant" ${rxScope === "assistant" ? "selected" : ""}>仅 AI</option>
                        </select>
                        <button type="button" class="btn btn-xs btn-danger" style="margin-left:auto;" onclick="window.removeStudioRegexRule(${idx})">删除</button>
                      </div>
                      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
                        <input type="text" class="form-input st-rx-pattern" value="${escapeHtml(rxPat)}" placeholder="正则" onblur="window.saveStudioProjectConfig(false)" style="padding:4px 8px;font-size:12px;font-family:monospace;" />
                        <input type="text" class="form-input st-rx-replacement" value="${escapeHtml(rxRep)}" placeholder="替换为" onblur="window.saveStudioProjectConfig(false)" style="padding:4px 8px;font-size:12px;font-family:monospace;" />
                      </div>
                    </div>
                  `;
                }).join("")
              : `<div style="padding:6px 10px;color:var(--text-dim);font-size:0.74rem;">暂无规则</div>`
            }
          </div>
        </div>

        <!-- CG / 记忆 / 变量 -->
        <div class="studio-section-card" id="studioAdvancedFeaturesSection">
          <div class="studio-section-header" style="flex-wrap:wrap;gap:6px;">
            <div class="studio-section-title">CG / 记忆 / 变量</div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;">
              <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.addStudioCgEntry()">CG</button>
              <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.addStudioMemoryPalaceItem()">记忆</button>
              <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.addStudioPromptVariable()">变量</button>
            </div>
          </div>
          <div id="stCgBookList" style="display:flex;flex-direction:column;gap:6px;margin-bottom:6px;">
            ${Array.isArray(proj.cg_book) && proj.cg_book.length > 0
              ? proj.cg_book.map((cg, idx) => `
                  <div class="st-cg-item" data-cg-id="${escapeHtml(cg.id || `cg_${idx + 1}`)}" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                    <input type="text" class="form-input st-cg-name" value="${escapeHtml(cg.name || "")}" placeholder="CG 名称" onblur="window.saveStudioProjectConfig(false)" style="width:110px;padding:3px 6px;font-size:12px;" />
                    <input type="text" class="form-input st-cg-keys" value="${escapeHtml(Array.isArray(cg.keys) ? cg.keys.join(", ") : (cg.keys || ""))}" placeholder="触发词" onblur="window.saveStudioProjectConfig(false)" style="width:130px;padding:3px 6px;font-size:12px;" />
                    <input type="text" class="form-input st-cg-url" value="${escapeHtml(cg.url || cg.image_url || "")}" placeholder="图片 URL" onblur="window.saveStudioProjectConfig(false)" style="flex:1;min-width:130px;padding:3px 6px;font-size:12px;" />
                    <button type="button" class="btn btn-xs btn-danger" onclick="window.removeStudioCgEntry(${idx})">删除</button>
                  </div>
                `).join("")
              : ""
            }
          </div>
          <div id="stMemoryPalaceList" style="display:flex;flex-direction:column;gap:6px;margin-bottom:6px;">
            ${Array.isArray(proj.memory_palace) && proj.memory_palace.length > 0
              ? proj.memory_palace.map((mp, idx) => `
                  <div class="st-mp-item" data-mp-id="${escapeHtml(mp.id || `mp_${idx + 1}`)}" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                    <input type="text" class="form-input st-mp-title" value="${escapeHtml(mp.title || mp.key || "")}" placeholder="记忆标签" onblur="window.saveStudioProjectConfig(false)" style="width:120px;padding:3px 6px;font-size:12px;" />
                    <input type="text" class="form-input st-mp-content" value="${escapeHtml(mp.content || mp.value || "")}" placeholder="记忆内容" onblur="window.saveStudioProjectConfig(false)" style="flex:1;min-width:150px;padding:3px 6px;font-size:12px;" />
                    <button type="button" class="btn btn-xs btn-danger" onclick="window.removeStudioMemoryPalaceItem(${idx})">删除</button>
                  </div>
                `).join("")
              : ""
            }
          </div>
          <div id="stPromptVarsList" style="display:flex;flex-direction:column;gap:6px;">
            ${Array.isArray(proj.prompt_variables) && proj.prompt_variables.length > 0
              ? proj.prompt_variables.map((pv, idx) => `
                  <div class="st-pv-item" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                    <input type="text" class="form-input st-pv-name" value="${escapeHtml(pv.name || "")}" placeholder="变量名" onblur="window.saveStudioProjectConfig(false)" style="width:120px;padding:3px 6px;font-size:12px;font-family:monospace;" />
                    <input type="text" class="form-input st-pv-label" value="${escapeHtml(pv.label || "")}" placeholder="显示名称" onblur="window.saveStudioProjectConfig(false)" style="width:120px;padding:3px 6px;font-size:12px;" />
                    <input type="text" class="form-input st-pv-default" value="${escapeHtml(pv.default ?? pv.value ?? "")}" placeholder="默认值" onblur="window.saveStudioProjectConfig(false)" style="flex:1;min-width:110px;padding:3px 6px;font-size:12px;" />
                    <button type="button" class="btn btn-xs btn-danger" onclick="window.removeStudioPromptVariable(${idx})">删除</button>
                  </div>
                `).join("")
              : ""
            }
          </div>
        </div>

        <!-- 采样参数 -->
        <div class="studio-section-card">
          <div class="studio-section-header" style="flex-wrap:wrap;gap:8px;">
            <div class="studio-section-title" style="display:flex;align-items:center;gap:6px;">
              <span>采样参数</span>
              ${hasModelOverride ? `<span class="wb-badge" style="color:var(--tc-fcd34d, #fcd34d);border-color:var(--tc-rgba-245-158-11-0-45, rgba(245,158,11,0.45));background:var(--tc-rgba-245-158-11-0-12, rgba(245,158,11,0.12));font-size:11px;">已被模型参数覆盖</span>` : ""}
            </div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;${hasModelOverride ? "opacity:0.45;pointer-events:none;" : ""}">
              <label class="checkbox-label" style="font-size:0.75rem;">
                <input type="checkbox" ${useGlobal ? "checked" : ""} ${hasModelOverride ? "disabled" : ""} onchange="window.toggleProjectUseGlobalParams(this.checked)" />
                <span>跟随全局</span>
              </label>
              <button type="button" class="btn btn-xs btn-outline-secondary" ${hasModelOverride ? "disabled" : ""} onclick="window.resetCompletionParamsDefault()">恢复默认</button>
            </div>
          </div>

          ${hasModelOverride ? `
            <div class="model-param-override-banner" style="margin-bottom:10px;padding:10px 12px;border-radius:8px;border:1px solid var(--tc-rgba-245-158-11-0-42, rgba(245,158,11,0.42));background:var(--tc-rgba-245-158-11-0-09, rgba(245,158,11,0.09));display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
              <div style="font-size:12px;color:var(--tc-fcd34d, #fcd34d);line-height:1.5;flex:1;min-width:220px;">
                <div><b>独立参数：${escapeHtml(activeModel)}</b></div>
                
              </div>
              <div style="display:flex;gap:6px;flex-wrap:wrap;flex-shrink:0;">
                <button type="button" class="btn btn-xs btn-primary" onclick="window.jumpToActiveModelParams('${escapeJsAttr(activeModel)}')">修改</button>
                <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.disableActiveModelParamsOverride('${escapeJsAttr(activeModel)}')">关闭</button>
              </div>
            </div>
          ` : ""}

          <div class="numeric-params-grid" style="${isParamsLocked ? "opacity:0.45;pointer-events:none;filter:grayscale(0.65);user-select:none;" : ""}">
            <div class="param-slider-row">
              <div class="param-slider-header">
                <span>温度</span>
                <input type="number" ${disabledAttr} class="param-num-input" id="stNum_temperature" min="0" max="2.0" step="0.05" value="${Number(cp.temperature ?? 0.68).toFixed(2)}" oninput="window.updateCompletionParam('temperature', Number(this.value))" />
              </div>
              <input type="range" ${disabledAttr} id="stRange_temperature" min="0" max="2.0" step="0.05" value="${cp.temperature ?? 0.68}" oninput="window.updateCompletionParam('temperature', Number(this.value))" />
            </div>

            <div class="param-slider-row">
              <div class="param-slider-header">
                <span>重复惩罚</span>
                <input type="number" ${disabledAttr} class="param-num-input" id="stNum_repetition_penalty" min="1.0" max="1.5" step="0.01" value="${Number(cp.repetition_penalty ?? 1.05).toFixed(2)}" oninput="window.updateCompletionParam('repetition_penalty', Number(this.value))" />
              </div>
              <input type="range" ${disabledAttr} id="stRange_repetition_penalty" min="1.0" max="1.5" step="0.01" value="${cp.repetition_penalty ?? 1.05}" oninput="window.updateCompletionParam('repetition_penalty', Number(this.value))" />
            </div>

            <div class="param-slider-row">
              <div class="param-slider-header">
                <span>频率惩罚</span>
                <input type="number" ${disabledAttr} class="param-num-input" id="stNum_frequency_penalty" min="-2.0" max="2.0" step="0.05" value="${Number(cp.frequency_penalty ?? 0.05).toFixed(2)}" oninput="window.updateCompletionParam('frequency_penalty', Number(this.value))" />
              </div>
              <input type="range" ${disabledAttr} id="stRange_frequency_penalty" min="-2.0" max="2.0" step="0.05" value="${cp.frequency_penalty ?? 0.05}" oninput="window.updateCompletionParam('frequency_penalty', Number(this.value))" />
            </div>

            <div class="param-slider-row">
              <div class="param-slider-header">
                <span>存在惩罚</span>
                <input type="number" ${disabledAttr} class="param-num-input" id="stNum_presence_penalty" min="-2.0" max="2.0" step="0.05" value="${Number(cp.presence_penalty ?? 0.20).toFixed(2)}" oninput="window.updateCompletionParam('presence_penalty', Number(this.value))" />
              </div>
              <input type="range" ${disabledAttr} id="stRange_presence_penalty" min="-2.0" max="2.0" step="0.05" value="${cp.presence_penalty ?? 0.20}" oninput="window.updateCompletionParam('presence_penalty', Number(this.value))" />
            </div>

            <div class="param-slider-row">
              <div class="param-slider-header">
                <span>Top-P</span>
                <input type="number" ${disabledAttr} class="param-num-input" id="stNum_top_p" min="0.1" max="1.0" step="0.05" value="${Number(cp.top_p ?? 0.90).toFixed(2)}" oninput="window.updateCompletionParam('top_p', Number(this.value))" />
              </div>
              <input type="range" ${disabledAttr} id="stRange_top_p" min="0.1" max="1.0" step="0.05" value="${cp.top_p ?? 0.90}" oninput="window.updateCompletionParam('top_p', Number(this.value))" />
            </div>

            <div class="param-slider-row">
              <div class="param-slider-header">
                <span>Top-K</span>
                <input type="number" ${disabledAttr} class="param-num-input" id="stNum_top_k" min="0" max="100" step="1" value="${cp.top_k ?? 40}" oninput="window.updateCompletionParam('top_k', Number(this.value))" />
              </div>
              <input type="range" ${disabledAttr} id="stRange_top_k" min="0" max="100" step="1" value="${cp.top_k ?? 40}" oninput="window.updateCompletionParam('top_k', Number(this.value))" />
            </div>

            <div class="param-slider-row">
              <div class="param-slider-header">
                <span>Min-P</span>
                <input type="number" ${disabledAttr} class="param-num-input" id="stNum_min_p" min="0.0" max="0.5" step="0.01" value="${Number(cp.min_p ?? 0.06).toFixed(2)}" oninput="window.updateCompletionParam('min_p', Number(this.value))" />
              </div>
              <input type="range" ${disabledAttr} id="stRange_min_p" min="0.0" max="0.5" step="0.01" value="${cp.min_p ?? 0.06}" oninput="window.updateCompletionParam('min_p', Number(this.value))" />
            </div>

            <div class="param-slider-row">
              <div class="param-slider-header">
                <span>最大输出</span>
                <input type="number" ${disabledAttr} class="param-num-input" id="stNum_max_tokens" min="256" max="65536" step="256" value="${cp.max_tokens ?? 8192}" oninput="window.updateCompletionParam('max_tokens', Number(this.value))" />
              </div>
              <input type="range" ${disabledAttr} id="stRange_max_tokens" min="256" max="65536" step="256" value="${cp.max_tokens ?? 8192}" oninput="window.updateCompletionParam('max_tokens', Number(this.value))" />
            </div>

            <div class="param-slider-row context-integrated-card" style="grid-column: 1 / -1;">
              <div class="param-slider-header" style="gap:8px;margin-bottom:6px;">
                <span>上下文</span>
                <select id="stContextMode" ${disabledAttr} class="form-select" style="width:auto;padding:2px 8px;font-size:12px;height:26px;" onchange="window.updateProjectContextMode(this.value)">
                  <option value="turns" ${cp.context_mode !== "tokens" ? "selected" : ""}>按轮数</option>
                  <option value="tokens" ${cp.context_mode === "tokens" ? "selected" : ""}>按 Token</option>
                </select>
              </div>
              <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(195px, 1fr));gap:12px;align-items:start;">
                <div id="stContextTurnsGroup" style="${cp.context_mode === "tokens" ? "display:none;" : ""}">
                  <div class="param-slider-header">
                    <span style="font-size:12px;color:var(--text-muted);">上下文轮数</span>
                    <input type="number" ${disabledAttr} class="param-num-input" id="stNum_context" min="2" max="200" step="1" value="${ctxTurns}" oninput="window.updateCompletionParam('context', Number(this.value))" />
                  </div>
                  <input type="range" ${disabledAttr} id="stRange_context" min="2" max="200" step="1" value="${ctxTurns}" oninput="window.updateCompletionParam('context', Number(this.value))" />
                  <small class="param-item-hint">保留最近 <b id="stContextMsgsCalc">${ctxTurns * 2}</b> 条消息</small>
                </div>
                <div>
                  <div class="param-slider-header">
                    <span style="font-size:12px;color:var(--text-muted);">上下文上限 (k)</span>
                    <input type="number" ${disabledAttr} class="param-num-input" id="stNum_max_context_k" min="4" max="512" step="4" value="${cp.max_context_k ?? 96}" oninput="window.updateCompletionParam('max_context_k', Number(this.value))" />
                  </div>
                  <input type="range" ${disabledAttr} id="stRange_max_context_k" min="4" max="512" step="4" value="${cp.max_context_k ?? 96}" oninput="window.updateCompletionParam('max_context_k', Number(this.value))" />
                  <small class="param-item-hint">单位 k</small>
                </div>
              </div>
            </div>

            <div class="param-slider-row">
              <div class="param-slider-header">
                <span>压缩保留</span>
                <input type="number" ${disabledAttr} class="param-num-input" id="stNum_keep_recent_messages" min="2" max="30" step="2" value="${cp.keep_recent_messages ?? 6}" oninput="window.updateCompletionParam('keep_recent_messages', Number(this.value))" />
              </div>
              <input type="range" ${disabledAttr} id="stRange_keep_recent_messages" min="2" max="30" step="2" value="${cp.keep_recent_messages ?? 6}" oninput="window.updateCompletionParam('keep_recent_messages', Number(this.value))" />
            </div>

            <div class="param-slider-row">
              <div class="param-slider-header">
                <span>思考预算</span>
                <input type="number" ${disabledAttr} class="param-num-input" id="stNum_thinking_budget" min="0" max="65536" step="256" value="${cp.thinking_budget ?? 1024}" oninput="window.updateCompletionParam('thinking_budget', Number(this.value))" />
              </div>
              <input type="range" ${disabledAttr} id="stRange_thinking_budget" min="0" max="65536" step="256" value="${cp.thinking_budget ?? 1024}" oninput="window.updateCompletionParam('thinking_budget', Number(this.value))" />
            </div>
          </div>

          <div style="margin-top:10px;padding-top:8px;border-top:1px solid rgba(255,255,255,0.06);">
            <label class="checkbox-label" style="font-size:0.78rem;">
              <input type="checkbox" id="stAutoSummarize" ${proj.auto_summarize !== false ? "checked" : ""} onchange="window.updateProjectAutoSummarize(this.checked)" />
              <span>超限自动压缩</span>
            </label>
          </div>
        </div>
      </div>
    </details>
  `;
  if (typeof window.syncAllAiAssistModelSelects === "function") {
    window.syncAllAiAssistModelSelects();
  }
  const paneEl = document.getElementById("studioWorkbenchPane") || container;
  if (typeof window.translateSubtree === "function" && paneEl) {
    window.translateSubtree(paneEl);
  }
}

// =========================================================================
// 2. 图标与背景自定义/上传及外观应用
// =========================================================================
window.previewIconInputChange = function (val, previewBoxId) {
  const box = document.getElementById(previewBoxId);
  if (box) {
    box.innerHTML = getIconHtml(val || "", 32) || `<span style="font-size:15px;color:var(--text-dim);line-height:1;">+</span>`;
  }
};

async function uploadImageAndGetUrl(file, maxDim = 1024, quality = 0.78, folderName = "默认图库") {
  return new Promise((resolve, reject) => {
    const doUpload = async (finalDataUrl) => {
      try {
        if (!finalDataUrl) throw new Error("图片压缩失败");
        const res = await fetch("/api/gallery/upload", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            image_base64: finalDataUrl,
            filename: file.name || "upload.jpg",
            folder: folderName
          })
        });
        const data = await res.json();
        if (!res.ok || !data.url) throw new Error(data.detail || "上传失败");
        if (typeof updateGalleryCountBadge === "function") updateGalleryCountBadge();
        resolve(data.url);
      } catch (err) {
        reject(err);
      }
    };
    if (typeof window.compressImageToJpeg === "function") {
      window.compressImageToJpeg(file, maxDim, quality, doUpload);
    } else {
      const reader = new FileReader();
      reader.onload = (ev) => doUpload(ev.target.result);
      reader.onerror = () => reject(new Error("读取图片失败"));
      reader.readAsDataURL(file);
    }
  });
}

window.handleUploadProjectIcon = async function (event, mode = "studio") {
  const file = event.target?.files?.[0];
  if (!file) return;
  showToast("上传中...");
  try {
    const url = await uploadImageAndGetUrl(file, 256, 0.88, "角色立绘");
    if (mode === "advanced" && advancedDraftProject) {
      syncAdvancedDraftFromDom();
      advancedDraftProject.icon = url;
      advancedDraftProject.avatar = url;
      renderAdvancedProjectEditor();
      showToast("图标已上传");
    } else {
      const proj = getActiveProjectObj();
      if (!proj) return;
      collectCurrentTabFormState();
      proj.icon = url;
      proj.avatar = url;
      const inp = document.getElementById("stProjIcon");
      if (inp) inp.value = url;
      await window.saveStudioProjectConfig(false);
      showToast("图标已上传");
    }
  } catch (err) {
    showToast("上传图标失败: " + err.message);
  } finally {
    try { event.target.value = ""; } catch (e) {}
  }
};

window.handleUploadProjectBackground = async function (event, mode = "studio") {
  const file = event.target?.files?.[0];
  if (!file) return;
  showToast("上传中...");
  try {
    const url = await uploadImageAndGetUrl(file, 1600, 0.85, "场景CG");
    if (mode === "advanced" && advancedDraftProject) {
      syncAdvancedDraftFromDom();
      if (!advancedDraftProject.appearance) advancedDraftProject.appearance = {};
      advancedDraftProject.appearance.bg_image = url;
      advancedDraftProject.bg_image = url;
      renderAdvancedProjectEditor();
      showToast("背景已上传");
    } else {
      const proj = getActiveProjectObj();
      if (!proj) return;
      collectCurrentTabFormState();
      if (!proj.appearance) proj.appearance = {};
      proj.appearance.bg_image = url;
      proj.bg_image = url;
      applyProjectAppearance(proj);
      await window.saveStudioProjectConfig(false);
      showToast("背景已上传");
    }
  } catch (err) {
    showToast("上传背景失败: " + err.message);
  } finally {
    try { event.target.value = ""; } catch (e) {}
  }
};

window.previewCgImage = function (url) {
  const lb = document.getElementById("imageLightbox");
  const img = document.getElementById("lightboxImg");
  if (lb && img && url) {
    img.src = url;
    lb.style.display = "flex";
  }
};

const OFFICIAL_CSS_PRESETS = {
  campus: {
    label: "青春校园",
    css: `/* 青春校园 · 清透蔚蓝手账皮肤 */
.message-row.assistant .bubble {
  background: linear-gradient(145deg, rgba(18, 34, 58, 0.88), rgba(15, 25, 42, 0.92));
  border: 1px solid rgba(96, 165, 250, 0.35);
  border-radius: 16px;
  box-shadow: 0 8px 24px rgba(14, 116, 144, 0.14);
}
.custom-ui {
  margin: 12px 0;
  padding: 12px 16px;
  border-radius: 12px;
  background: rgba(30, 58, 95, 0.45);
  border-left: 4px solid #60a5fa;
  border-top: 1px solid rgba(147, 197, 253, 0.25);
  color: #e0f2fe;
  font-size: 0.92em;
}`
  },
  crimson: {
    label: "粉色诱惑",
    css: `/* 粉色诱惑 · 暗夜丝绒霓虹皮肤 */
.message-row.assistant .bubble {
  background: linear-gradient(145deg, rgba(42, 16, 33, 0.90), rgba(24, 11, 22, 0.94));
  border: 1px solid rgba(244, 114, 182, 0.36);
  border-radius: 16px;
  box-shadow: 0 8px 26px rgba(219, 39, 119, 0.16);
}
.custom-ui {
  margin: 12px 0;
  padding: 12px 16px;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(80, 22, 54, 0.55), rgba(38, 12, 30, 0.65));
  border: 1px solid rgba(244, 114, 182, 0.42);
  color: #fce7f3;
  box-shadow: inset 0 0 14px rgba(244, 114, 182, 0.10);
}`
  },
  classical: {
    label: "古色古香",
    css: `/* 古色古香 · 墨金竹简卷轴皮肤 */
.message-row.assistant .bubble {
  background: linear-gradient(160deg, rgba(32, 27, 21, 0.94), rgba(22, 19, 15, 0.96));
  border: 1px solid rgba(212, 166, 90, 0.42);
  border-radius: 10px;
  font-family: "Noto Serif SC", "Songti SC", Georgia, serif;
  box-shadow: 0 6px 22px rgba(0, 0, 0, 0.38);
}
.custom-ui {
  margin: 12px 0;
  padding: 12px 16px;
  border-radius: 6px;
  background: rgba(46, 36, 24, 0.60);
  border-top: 2px solid #d4a65a;
  border-bottom: 2px solid #d4a65a;
  color: #fde68a;
  letter-spacing: 0.03em;
}`
  },
  tactical: {
    label: "战术终端",
    css: `/* 战术终端 · 特勤冷光 HUD 皮肤 */
.message-row.assistant .bubble {
  background: linear-gradient(180deg, rgba(11, 20, 30, 0.94), rgba(8, 14, 22, 0.96));
  border: 1px solid rgba(56, 189, 248, 0.34);
  border-radius: 8px;
  box-shadow: 0 0 18px rgba(14, 165, 233, 0.12);
}
.custom-ui {
  margin: 12px 0;
  padding: 11px 14px;
  border-radius: 6px;
  background: rgba(6, 24, 38, 0.72);
  border: 1px solid rgba(56, 189, 248, 0.45);
  border-left: 3px solid #38bdf8;
  color: #bae6fd;
  font-family: "JetBrains Mono", Consolas, monospace;
  font-size: 0.88em;
}`
  },
  abyss: {
    label: "深渊调查",
    css: `/* 深渊调查 · 旧日密档暗绿皮肤 */
.message-row.assistant .bubble {
  background: linear-gradient(155deg, rgba(16, 28, 24, 0.94), rgba(11, 19, 17, 0.96));
  border: 1px solid rgba(52, 211, 153, 0.28);
  border-radius: 12px;
}
.custom-ui {
  margin: 12px 0;
  padding: 12px 15px;
  border-radius: 8px;
  background: rgba(13, 38, 31, 0.62);
  border: 1px dashed rgba(110, 231, 183, 0.42);
  color: #d1fae5;
}`
  }
};
window.OFFICIAL_CSS_PRESETS = OFFICIAL_CSS_PRESETS;

function _splitTopLevelCssSelectors(selectorGroup) {
  const out = [];
  let cur = "";
  let paren = 0;
  let bracket = 0;
  let quote = "";
  for (let i = 0; i < selectorGroup.length; i++) {
    const ch = selectorGroup[i];
    if (ch === "\\" && i + 1 < selectorGroup.length) {
      cur += ch + selectorGroup[i + 1];
      i++;
      continue;
    }
    if (quote) {
      cur += ch;
      if (ch === quote) quote = "";
      continue;
    }
    if (ch === "'" || ch === '"') {
      quote = ch;
      cur += ch;
      continue;
    }
    if (ch === "(") paren++;
    else if (ch === ")" && paren > 0) paren--;
    else if (ch === "[") bracket++;
    else if (ch === "]" && bracket > 0) bracket--;
    if (ch === "," && paren === 0 && bracket === 0) {
      if (cur.trim()) out.push(cur.trim());
      cur = "";
    } else {
      cur += ch;
    }
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}

function scopeProjectCss(rawCss, scopeRoot = "#chatMainStage") {
  if (!rawCss || typeof rawCss !== "string") return "";
  let css = rawCss
    .replace(/<\/?style[^>]*>/gi, "")
    .replace(/@import\b[^;]*;?/gi, "")
    .replace(/expression\s*\([^)]*\)/gi, "")
    .replace(/url\s*\(\s*['"]?\s*(?:javascript|vbscript|data:text\/html)[^)]*\)/gi, "none")
    .replace(/(?:-moz-binding|behavior)\s*:[^;}]*/gi, "")
    .trim();
  if (!css) return "";

  const transformBlock = (input) => {
    let res = "";
    let i = 0;
    const n = input.length;
    while (i < n) {
      if (input[i] === "/" && input[i + 1] === "*") {
        const endC = input.indexOf("*/", i + 2);
        if (endC === -1) break;
        i = endC + 2;
        continue;
      }
      if (/\s/.test(input[i])) {
        res += input[i++];
        continue;
      }
      let selStart = i;
      let quote = "";
      while (i < n) {
        const ch = input[i];
        if (ch === "\\" && i + 1 < n) {
          i += 2;
          continue;
        }
        if (quote) {
          if (ch === quote) quote = "";
          i++;
          continue;
        }
        if (ch === "'" || ch === '"') {
          quote = ch;
          i++;
          continue;
        }
        if (ch === "/" && input[i + 1] === "*") {
          const endC = input.indexOf("*/", i + 2);
          i = endC === -1 ? n : endC + 2;
          continue;
        }
        if (ch === "{" || ch === "}") break;
        i++;
      }
      if (i >= n || input[i] !== "{") {
        res += input.slice(selStart, Math.min(n, i + 1));
        i++;
        continue;
      }
      const prelude = input.slice(selStart, i).trim();
      i++; // skip '{'
      const bodyStart = i;
      let depth = 1;
      quote = "";
      while (i < n && depth > 0) {
        const ch = input[i];
        if (ch === "\\" && i + 1 < n) {
          i += 2;
          continue;
        }
        if (quote) {
          if (ch === quote) quote = "";
          i++;
          continue;
        }
        if (ch === "'" || ch === '"') {
          quote = ch;
          i++;
          continue;
        }
        if (ch === "/" && input[i + 1] === "*") {
          const endC = input.indexOf("*/", i + 2);
          i = endC === -1 ? n : endC + 2;
          continue;
        }
        if (ch === "{") depth++;
        else if (ch === "}") depth--;
        i++;
      }
      const innerBody = input.slice(bodyStart, Math.max(bodyStart, i - 1));
      if (!prelude) continue;

      if (/^@(?:-\w+-)?keyframes\b/i.test(prelude) || /^@font-face\b/i.test(prelude)) {
        res += `${prelude} {${innerBody}}\n`;
      } else if (/^@(?:media|supports|container)\b/i.test(prelude)) {
        res += `${prelude} {\n${transformBlock(innerBody)}\n}\n`;
      } else if (prelude.startsWith("@")) {
        continue;
      } else {
        const scopedSels = _splitTopLevelCssSelectors(prelude).map((s) => {
          if (s.startsWith(scopeRoot)) return s;
          if (/^(?:html|body|:root|\.chat-main)(?=$|[\s>+~.:#\[])/i.test(s)) {
            return s.replace(/^(?:html|body|:root|\.chat-main)/i, scopeRoot);
          }
          return `${scopeRoot} ${s}`;
        });
        res += `${scopedSels.join(", ")} {${innerBody}}\n`;
      }
    }
    return res;
  };

  return transformBlock(css).trim();
}
window.scopeProjectCss = scopeProjectCss;

function applyProjectCustomCss(rawCss) {
  let styleTag = document.getElementById("projectCustomCssTag");
  const chatMain = document.getElementById("chatMainStage") || document.querySelector(".chat-main");
  const scoped = scopeProjectCss(String(rawCss || ""), "#chatMainStage #messageContainer");
  if (chatMain) {
    chatMain.classList.toggle("has-custom-css", Boolean(scoped));
  }
  if (!scoped) {
    if (styleTag) styleTag.textContent = "";
    return;
  }
  if (!styleTag) {
    styleTag = document.createElement("style");
    styleTag.id = "projectCustomCssTag";
    document.head.appendChild(styleTag);
  }
  styleTag.textContent = scoped;
}
window.applyProjectCustomCss = applyProjectCustomCss;

window.renderQuickRepliesBar = function () {
  const bar = document.getElementById("quickRepliesBar");
  if (!bar) return;
  const proj = getActiveProjectObj();
  if (!proj || isSimpleTrpgProject(proj) || !Array.isArray(proj.quick_replies) || proj.quick_replies.length === 0) {
    bar.style.display = "none";
    bar.innerHTML = "";
    return;
  }
  const validList = proj.quick_replies.filter((q) => q && (q.label || q.command || q.content)).slice(0, 10);
  if (validList.length === 0) {
    bar.style.display = "none";
    bar.innerHTML = "";
    return;
  }
  bar.style.display = "flex";
  bar.innerHTML = validList.map((qr, idx) => {
    const label = qr.label || qr.command || `指令 #${idx + 1}`;
    const tip = qr.command ? `${qr.command} → ${qr.content || label}` : (qr.content || label);
    return `<button type="button" class="quick-reply-pill" onclick="window.triggerQuickReplyItem(${idx})" title="${escapeHtml(tip)}">⚡ ${escapeHtml(label)}</button>`;
  }).join("");
};

window.triggerQuickReplyItem = function (idx) {
  const proj = getActiveProjectObj();
  if (!proj || !Array.isArray(proj.quick_replies)) return;
  const validList = proj.quick_replies.filter((q) => q && (q.label || q.command || q.content)).slice(0, 10);
  const qr = validList[idx];
  if (!qr) return;
  const textToSend = String(qr.content || qr.command || qr.label || "").trim();
  if (!textToSend) return;
  if (qr.auto_send !== false && typeof handleSendMessage === "function") {
    handleSendMessage(textToSend);
  } else {
    const inp = document.getElementById("userInput");
    if (inp) {
      inp.value = textToSend;
      inp.focus();
      inp.dispatchEvent(new Event("input"));
    }
  }
};

window._galleryPickerCallback = null;
window.openGalleryAssetPicker = async function (onPickUrl) {
  const modal = document.getElementById("galleryAssetPickerModal");
  const body = document.getElementById("galleryAssetPickerBody");
  if (!modal || !body) return;
  window._galleryPickerCallback = typeof onPickUrl === "function" ? onPickUrl : null;
  modal.style.display = "flex";
  body.innerHTML = `<div style="padding:20px;text-align:center;color:var(--text-muted);">正在读取素材图库...</div>`;
  try {
    const res = await fetch("/api/gallery");
    const data = await res.json();
    const images = Array.isArray(data) ? data : (data.images || []);
    if (images.length === 0) {
      body.innerHTML = `
        <div style="padding:28px;text-align:center;color:var(--text-muted);display:flex;flex-direction:column;gap:10px;align-items:center;">
          <div>素材图库暂无图片，请先上传图片至图库或直接使用「本地传图」。</div>
          <button type="button" class="btn btn-sm btn-primary" onclick="document.getElementById('galleryAssetPickerModal').style.display='none';window.openGalleryModal&&window.openGalleryModal();">打开素材图库上传</button>
        </div>
      `;
      return;
    }
    body.innerHTML = `
      <div style="margin-bottom:10px;font-size:12px;color:var(--text-muted);">点击任意图库图片即可选用（共 ${images.length} 张）：</div>
      <div class="gallery-picker-grid">
        ${images.map((img) => {
          const url = img.url || "";
          const name = img.filename || img.name || "";
          return `
            <div class="gallery-picker-tile" onclick="window._confirmGalleryAssetPick('${escapeJsAttr(url)}')" title="${escapeHtml(name)}">
              <img src="${escapeHtml(url)}" alt="${escapeHtml(name)}" loading="lazy" />
            </div>
          `;
        }).join("")}
      </div>
    `;
  } catch (err) {
    body.innerHTML = `<div style="padding:20px;color:#f87171;">读取素材图库失败: ${escapeHtml(err.message)}</div>`;
  }
};

window._confirmGalleryAssetPick = function (url) {
  const modal = document.getElementById("galleryAssetPickerModal");
  if (modal) modal.style.display = "none";
  if (typeof window._galleryPickerCallback === "function") {
    const cb = window._galleryPickerCallback;
    window._galleryPickerCallback = null;
    cb(url);
  }
};

window.pickStudioGalleryAsset = function (field) {
  window.openGalleryAssetPicker((url) => {
    window.updateAppearanceConfig(field, url);
    renderStudioWorkbench();
  });
};

window.handleUploadProjectMobileBackground = async function (event, mode = "studio") {
  const file = event.target?.files?.[0];
  if (!file) return;
  showToast("上传移动背景中...");
  try {
    const url = await uploadImageAndGetUrl(file, 1440, 0.85, "场景CG");
    if (mode === "advanced" && advancedDraftProject) {
      syncAdvancedDraftFromDom();
      if (!advancedDraftProject.appearance) advancedDraftProject.appearance = {};
      advancedDraftProject.appearance.bg_mobile = url;
      renderAdvancedProjectEditor();
      showToast("移动设备背景已上传");
    } else {
      const proj = getActiveProjectObj();
      if (!proj) return;
      collectCurrentTabFormState();
      if (!proj.appearance) proj.appearance = {};
      proj.appearance.bg_mobile = url;
      applyProjectAppearance(proj);
      await window.saveStudioProjectConfig(false);
      renderStudioWorkbench();
      showToast("移动设备背景已上传");
    }
  } catch (err) {
    showToast("上传失败: " + err.message);
  } finally {
    try { event.target.value = ""; } catch (e) {}
  }
};

window.applyStudioCssPreset = function (presetKey) {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  const nextCss = presetKey && OFFICIAL_CSS_PRESETS[presetKey] ? OFFICIAL_CSS_PRESETS[presetKey].css : "";
  proj.custom_css = nextCss;
  if (!proj.appearance) proj.appearance = {};
  proj.appearance.custom_css = nextCss;
  const el = document.getElementById("stCustomCssInput");
  if (el) el.value = nextCss;
  applyProjectCustomCss(nextCss);
  window.saveStudioProjectConfig(false);
  renderStudioWorkbench();
  showToast(presetKey ? `已套用皮肤：${OFFICIAL_CSS_PRESETS[presetKey].label}` : "已清空内置 CSS");
};

window.insertStudioCustomUiSnippet = function () {
  const el = document.getElementById("stCustomCssInput");
  if (!el) return;
  const snippet = `\n.custom-ui {\n  padding: 12px 16px;\n  border-radius: 10px;\n  background: rgba(30, 41, 59, 0.72);\n  border: 1px solid rgba(212, 166, 90, 0.42);\n  color: #f8fafc;\n}`;
  el.value = (el.value ? el.value.trimEnd() + "\n" : "") + snippet.trim();
  applyProjectCustomCss(el.value);
  window.saveStudioProjectConfig(false);
};

window.addStudioQuickReply = function () {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  if (!Array.isArray(proj.quick_replies)) proj.quick_replies = [];
  if (proj.quick_replies.length >= 10) {
    showToast("最多可添加 10 个快捷回复指令");
    return;
  }
  proj.quick_replies.push({
    id: `qr_${Date.now().toString(36)}`,
    label: "",
    command: "",
    content: "",
    auto_send: true
  });
  renderStudioWorkbench();
};

window.removeStudioQuickReply = async function (idx) {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj || !Array.isArray(proj.quick_replies)) return;
  proj.quick_replies.splice(idx, 1);
  renderStudioWorkbench();
  await window.saveStudioProjectConfig(false);
};

window.updateAppearanceConfig = function (field, val) {
  const proj = getActiveProjectObj();
  if (!proj) return;
  collectCurrentTabFormState();
  if (!proj.appearance) proj.appearance = {};
  proj.appearance[field] = val;
  if (field === "bg_image") {
    proj.bg_image = val;
  }
  applyProjectAppearance(proj);
  window.saveStudioProjectConfig(false);
};

function applyProjectAppearance(proj) {
  if (!proj) {
    applyProjectCustomCss("");
    return;
  }
  const app = proj.appearance || {};
  document.body.classList.remove("light-theme");

  const chatMain = document.querySelector(".chat-main");
  if (chatMain) {
    const isPortraitView = window.innerWidth <= 768 || document.body.classList.contains("gui-portrait-mode");
    const bgUrl = (isPortraitView && app.bg_mobile)
      ? app.bg_mobile
      : (app.bg_image || proj.bg_image || app.bg_mobile || "");
    chatMain.classList.toggle("has-bg-image", !!bgUrl);
    if (bgUrl) {
      const safeCssUrl = String(bgUrl).replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/[\r\n]/g, "");
      const overlay = "linear-gradient(var(--tc-rgba-10-14-24-0-68, rgba(10, 14, 24, 0.68)), var(--tc-rgba-10-14-24-0-80, rgba(10, 14, 24, 0.80)))";
      chatMain.style.backgroundImage = `${overlay}, url("${safeCssUrl}")`;
      chatMain.style.backgroundSize = "cover";
      chatMain.style.backgroundPosition = "center";
    } else {
      chatMain.style.backgroundImage = "";
    }
  }

  const rawCss = (proj.custom_css !== undefined && proj.custom_css !== null)
    ? proj.custom_css
    : (app.custom_css || "");
  applyProjectCustomCss(rawCss);
  if (typeof window.renderQuickRepliesBar === "function") {
    window.renderQuickRepliesBar();
  }
}
window.applyProjectAppearance = applyProjectAppearance;

window.applyTemporaryCgBackground = function (imgUrl) {
  const chatMain = document.querySelector(".chat-main");
  if (!chatMain || !imgUrl) return;
  const safeCssUrl = String(imgUrl).replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/[\r\n]/g, "");
  const overlay = "linear-gradient(var(--tc-rgba-10-14-24-0-62, rgba(10, 14, 24, 0.62)), var(--tc-rgba-10-14-24-0-78, rgba(10, 14, 24, 0.78)))";
  chatMain.classList.add("has-bg-image");
  chatMain.style.backgroundImage = `${overlay}, url("${safeCssUrl}")`;
  chatMain.style.backgroundSize = "cover";
  chatMain.style.backgroundPosition = "center";
};

// =========================================================================
// 3. 提示词与模型参数控制
// =========================================================================
window.updatePromptCharCount = function (textarea) {
  const stat = document.getElementById("stPromptTokenStat");
  if (!stat || !textarea) return;
  const len = textarea.value.length;
  stat.textContent = `(${len} 字)`;
};

function ensureActiveStatusModulesOnEnable(targetProj) {
  if (!targetProj || typeof targetProj !== "object") return 0;
  let mods = getEffectiveUiModules(targetProj);
  const isStatusSub = (m) =>
    m &&
    !["thinking_fold", "story_narrative", "action_choices", "content_scale"].includes(m.type) &&
    !["mod_think", "mod_story", "mod_choices", "mod_scale"].includes(m.id);
  if (mods.length === 0) {
    mods = DEFAULT_UNIVERSAL_UI_MODULES.map((m) => ({ ...m, enabled: true }));
  } else {
    const statusSubs = mods.filter(isStatusSub);
    if (statusSubs.length === 0) {
      const stdSubs = DEFAULT_UNIVERSAL_UI_MODULES.filter(isStatusSub).map((m) => ({ ...m, enabled: true }));
      const choicesIdx = mods.findIndex((m) => m.type === "action_choices" || m.id === "mod_choices");
      if (choicesIdx !== -1) {
        mods.splice(choicesIdx, 0, ...stdSubs);
      } else {
        mods.push(...stdSubs);
      }
    } else if (statusSubs.every((m) => m.enabled === false)) {
      mods = mods.map((m) => (isStatusSub(m) ? { ...m, enabled: true } : m));
    }
    if (mods.every((m) => m.enabled === false)) {
      mods = mods.map((m) => ({ ...m, enabled: true }));
    }
  }
  targetProj.ui_modules = mods;
  return mods.filter((m) => m && m.enabled !== false && m.type !== "content_scale" && m.id !== "mod_scale").length;
}

window.handleToggleStudioStatusPanel = async function (checked) {
  const nextChecked = !!checked;
  const statusEl = document.getElementById("stStatusPanelEnabled");
  if (statusEl) statusEl.checked = nextChecked;
  document.querySelectorAll(".st-status-panel-sync-cb").forEach((cb) => {
    cb.checked = nextChecked;
  });
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  proj.status_panel_enabled = nextChecked;
  let activeCount = 0;
  if (nextChecked) {
    activeCount = ensureActiveStatusModulesOnEnable(proj);
  }
  const prevScroll = getStudioScrollContainer()?.scrollTop || 0;
  renderStudioWorkbench();
  const wbEl = getStudioScrollContainer();
  if (wbEl) wbEl.scrollTop = prevScroll;
  await window.saveStudioProjectConfig(false);
  if (typeof window.renderMessages === "function") {
    window.renderMessages(undefined, true);
  }
  showToast(nextChecked ? `状态栏已开启（已启用 ${activeCount} 个功能栏）` : "状态栏已关闭");
};

window.handleToggleSingleUiModule = async function (checkboxEl) {
  const isNowChecked = !!checkboxEl?.checked;
  if (isNowChecked) {
    const statusEl = document.getElementById("stStatusPanelEnabled");
    if (statusEl && !statusEl.checked) statusEl.checked = true;
  }
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  if (isNowChecked && proj.status_panel_enabled === false) {
    proj.status_panel_enabled = true;
  }
  const prevScroll = getStudioScrollContainer()?.scrollTop || 0;
  renderStudioWorkbench();
  const wbEl = getStudioScrollContainer();
  if (wbEl) wbEl.scrollTop = prevScroll;
  await window.saveStudioProjectConfig(false);
  if (typeof window.renderMessages === "function") {
    window.renderMessages(undefined, true);
  }
};

window.handleToggleAdvStatusPanel = function (checked) {
  const nextChecked = !!checked;
  const statusEl = document.getElementById("advStatusPanelEnabled");
  if (statusEl) statusEl.checked = nextChecked;
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject) return;
  advancedDraftProject.status_panel_enabled = nextChecked;
  let activeCount = 0;
  if (nextChecked) {
    activeCount = ensureActiveStatusModulesOnEnable(advancedDraftProject);
  }
  renderAdvancedProjectEditor();
  showToast(nextChecked ? `状态栏已开启（将附带 ${activeCount} 个默认功能栏）` : "状态栏已关闭");
};

window.updateCompletionParam = function (key, val) {
  const proj = getActiveProjectObj();
  if (!proj || val === "" || val === null || Number.isNaN(Number(val))) return;
  const focusedEl = document.activeElement;
  if (focusedEl && focusedEl.id === `stNum_${key}` && String(focusedEl.value).trim() === "") return;
  val = Number(val);
  const limitEl = document.getElementById(`stNum_${key}`);
  if (limitEl) {
    const mn = parseFloat(limitEl.min);
    const mx = parseFloat(limitEl.max);
    if (!Number.isNaN(mn)) val = Math.max(mn, val);
    if (!Number.isNaN(mx)) val = Math.min(mx, val);
  }
  if (!proj.completion_params) proj.completion_params = {};
  proj.completion_params[key] = val;
  if (key === "context") {
    proj.max_context_turns = val;
    const calcEl = document.getElementById("stContextMsgsCalc");
    if (calcEl) calcEl.textContent = val * 2;
    if (typeof window.updateContextProgressUI === "function") {
      window.updateContextProgressUI();
    }
  } else if (key === "max_context_k") {
    if (typeof window.updateContextProgressUI === "function") {
      window.updateContextProgressUI();
    }
  }
  const numEl = document.getElementById(`stNum_${key}`);
  const rangeEl = document.getElementById(`stRange_${key}`);
  const isFloat = ["temperature", "repetition_penalty", "frequency_penalty", "presence_penalty", "top_p", "min_p"].includes(key);
  if (numEl && document.activeElement !== numEl) {
    numEl.value = isFloat ? Number(val).toFixed(2) : val;
  }
  if (rangeEl && document.activeElement !== rangeEl) {
    rangeEl.value = val;
  }
  // 参数滑块此前只改内存不落盘：防抖保存，避免后端继续使用旧参数
  clearTimeout(window._stParamSaveTimer);
  const pidAtEdit = currentProjectId;
  window._stParamSaveTimer = setTimeout(() => {
    window._stParamSaveTimer = null;
    if (currentProjectId === pidAtEdit) window.saveStudioProjectConfig(false);
  }, 600);
};

window.updateProjectContextMode = function (mode) {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  if (!proj.completion_params) proj.completion_params = {};
  proj.completion_params.context_mode = mode === "tokens" ? "tokens" : "turns";
  if (typeof window.updateContextProgressUI === "function") {
    window.updateContextProgressUI();
  }
  renderStudioWorkbench();
  window.saveStudioProjectConfig(false);
};

window.toggleProjectUseGlobalParams = function (checked) {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  proj.use_global_params = !!checked;
  if (typeof window.updateContextProgressUI === "function") {
    window.updateContextProgressUI();
  }
  renderStudioWorkbench();
  window.saveStudioProjectConfig(false);
};

window.updateProjectAutoSummarize = function (checked) {
  const proj = getActiveProjectObj();
  if (!proj) return;
  proj.auto_summarize = !!checked;
  window.saveStudioProjectConfig(false);
};

window.applyProjectParamPreset = function (presetKey) {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  proj.use_global_params = false;
  if (presetKey === "novel") {
    proj.completion_params = {
      ...proj.completion_params,
      temperature: 0.68,
      repetition_penalty: 1.04,
      frequency_penalty: 0.02,
      presence_penalty: 0.15,
      top_p: 0.90,
      top_k: 40,
      min_p: 0.06,
      max_tokens: 8192,
      context_mode: proj.completion_params?.context_mode || "tokens",
      context: 96,
      max_context_k: proj.completion_params?.max_context_k ?? 96,
      keep_recent_messages: 6,
      thinking_budget: 1024
    };
    proj.max_context_turns = 96;
    showToast("已应用：小说");
  } else if (presetKey === "strict") {
    proj.completion_params = {
      ...proj.completion_params,
      temperature: 0.62,
      repetition_penalty: 1.03,
      frequency_penalty: 0.02,
      presence_penalty: 0.12,
      top_p: 0.88,
      top_k: 35,
      min_p: 0.06,
      max_tokens: 8192,
      context_mode: proj.completion_params?.context_mode || "tokens",
      context: 96,
      max_context_k: proj.completion_params?.max_context_k ?? 96,
      keep_recent_messages: 8,
      thinking_budget: 1024
    };
    proj.max_context_turns = 96;
    showToast("已应用：严谨");
  } else if (presetKey === "creative") {
    proj.completion_params = {
      ...proj.completion_params,
      temperature: 0.75,
      repetition_penalty: 1.06,
      frequency_penalty: 0.05,
      presence_penalty: 0.25,
      top_p: 0.92,
      top_k: 45,
      min_p: 0.05,
      max_tokens: 8192,
      context_mode: proj.completion_params?.context_mode || "tokens",
      context: 96,
      max_context_k: proj.completion_params?.max_context_k ?? 96,
      keep_recent_messages: 6,
      thinking_budget: 1024
    };
    proj.max_context_turns = 96;
    showToast("已应用：发散");
  }
  if (typeof window.updateContextProgressUI === "function") {
    window.updateContextProgressUI();
  }
  renderStudioWorkbench();
  window.saveStudioProjectConfig(false);
};

window.pullFromGlobalModelParams = async function () {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  try {
    const res = await fetch("/api/settings");
    if (!res.ok) throw new Error("读取失败");
    const s = await res.json();
    window.globalUserSettings = s;
    const ctx = Number(s.context ?? s.max_context_turns ?? 96);
    proj.completion_params = {
      temperature: Number(s.temperature ?? 0.68),
      repetition_penalty: Number(s.repetition_penalty ?? 1.05),
      frequency_penalty: Number(s.frequency_penalty ?? 0.05),
      presence_penalty: Number(s.presence_penalty ?? 0.20),
      top_p: Number(s.top_p ?? 0.90),
      top_k: Number(s.top_k ?? 40),
      min_p: Number(s.min_p ?? 0.06),
      max_tokens: Number(s.max_tokens ?? 8192),
      context_mode: s.context_mode === "tokens" ? "tokens" : "turns",
      context: ctx,
      max_context_k: Number(s.max_context_k ?? 96),
      keep_recent_messages: Number(s.keep_recent_messages ?? 6),
      thinking_budget: Number(s.thinking_budget ?? 1024)
    };
    proj.max_context_turns = ctx;
    proj.auto_summarize = s.auto_summarize !== false;
    if (typeof window.updateContextProgressUI === "function") {
      window.updateContextProgressUI();
    }
    renderStudioWorkbench();
    await window.saveStudioProjectConfig(false);
    showToast("已同步全局参数");
  } catch (err) {
    showToast("同步失败: " + err.message);
  }
};

window.pushProjectParamsToGlobal = async function () {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  const cp = proj.completion_params || {};
  const ctx = Number(cp.context ?? proj.max_context_turns ?? 96);
  const payload = {
    temperature: Number(cp.temperature ?? 0.68),
    repetition_penalty: Number(cp.repetition_penalty ?? 1.05),
    frequency_penalty: Number(cp.frequency_penalty ?? 0.05),
    presence_penalty: Number(cp.presence_penalty ?? 0.20),
    top_p: Number(cp.top_p ?? 0.90),
    top_k: Number(cp.top_k ?? 40),
    min_p: Number(cp.min_p ?? 0.06),
    max_tokens: Number(cp.max_tokens ?? 8192),
    context_mode: cp.context_mode === "tokens" ? "tokens" : "turns",
    context: ctx,
    max_context_turns: ctx,
    max_context_k: Number(cp.max_context_k ?? 96),
    keep_recent_messages: Number(cp.keep_recent_messages ?? 6),
    thinking_budget: Number(cp.thinking_budget ?? 1024),
    auto_summarize: proj.auto_summarize !== false
  };
  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error("保存失败");
    const out = await res.json();
    window.globalUserSettings = out.settings || payload;
    showToast("已设为全局默认");
  } catch (err) {
    showToast("保存失败: " + err.message);
  }
};

window.resetCompletionParamsDefault = function () {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  proj.use_global_params = false;
  proj.completion_params = {
    temperature: 0.68,
    repetition_penalty: 1.05,
    frequency_penalty: 0.05,
    presence_penalty: 0.20,
    top_p: 0.90,
    top_k: 40,
    min_p: 0.06,
    max_tokens: 8192,
    context_mode: "tokens",
    context: 96,
    max_context_k: 96,
    keep_recent_messages: 6,
    thinking_budget: 1024
  };
  proj.max_context_turns = 96;
  if (typeof window.updateContextProgressUI === "function") {
    window.updateContextProgressUI();
  }
  renderStudioWorkbench();
  window.saveStudioProjectConfig(false);
  showToast("已恢复默认");
};

// =========================================================================
// 4. 收集表单状态并保存游戏配置
// =========================================================================
function collectCurrentTabFormState() {
  const proj = getActiveProjectObj();
  if (!proj) return;

  const getRawOrEditedVal = (el) => {
    if (!el) return "";
    if (!el.value || !el.value.trim()) return "";
    if (el._origRoVal !== undefined && (el.value === el._lastEnRoVal || el.value.trim() === el._lastEnRoVal)) {
      return el._origRoVal;
    }
    return el.value;
  };

  const statusEl = document.getElementById("stStatusPanelEnabled");
  const iconEl = document.getElementById("stProjIcon");
  const nameEl = document.getElementById("stProjName");
  const descEl = document.getElementById("stProjDesc");
  const tagsEl = document.getElementById("stProjTags");
  const bgEl = document.getElementById("stBgImageInput");
  const preEl = document.getElementById("stProjPrefix");
  const sysEl = document.getElementById("stProjSystem");
  const sufEl = document.getElementById("stProjSuffix");
  const sysProtoEl = document.getElementById("stGlobalSystemProtocolPrompt");
  const autoSumEl = document.getElementById("stAutoSummarize");
  const ctxModeEl = document.getElementById("stContextMode");

  if (statusEl) proj.status_panel_enabled = statusEl.checked;
  if (iconEl) {
    proj.icon = iconEl.value.trim() || "";
    proj.avatar = proj.icon;
  }
  if (nameEl) proj.name = getRawOrEditedVal(nameEl).trim() || "未命名剧本";
  if (descEl) proj.description = getRawOrEditedVal(descEl).trim();
  if (tagsEl) {
    proj.tags = getRawOrEditedVal(tagsEl).split(/[,，]/).map((s) => s.trim()).filter(Boolean);
  }
  if (bgEl) {
    if (!proj.appearance) proj.appearance = {};
    proj.appearance.bg_image = bgEl.value.trim();
    proj.bg_image = proj.appearance.bg_image;
  }
  const bgMobEl = document.getElementById("stBgMobileInput");
  if (bgMobEl) {
    if (!proj.appearance) proj.appearance = {};
    proj.appearance.bg_mobile = bgMobEl.value.trim();
  }
  const detDescEl = document.getElementById("stProjDetailedDesc");
  if (detDescEl) {
    proj.detailed_description = getRawOrEditedVal(detDescEl).trim();
  }
  const stCssEl = document.getElementById("stCustomCssInput");
  if (stCssEl) {
    proj.custom_css = stCssEl.value;
    if (!proj.appearance) proj.appearance = {};
    proj.appearance.custom_css = stCssEl.value;
  }
  const qrListEl = document.getElementById("stQuickRepliesList");
  if (qrListEl) {
    const qrItems = Array.from(qrListEl.querySelectorAll(".st-qr-item"));
    proj.quick_replies = qrItems.slice(0, 10).map((el, idx) => ({
      id: el.dataset.qrId || `qr_${idx + 1}`,
      label: getRawOrEditedVal(el.querySelector(".st-qr-label")).trim(),
      command: getRawOrEditedVal(el.querySelector(".st-qr-cmd")).trim(),
      content: getRawOrEditedVal(el.querySelector(".st-qr-content")).trim(),
      auto_send: true
    })).filter((q) => q.label || q.command || q.content);
  }
  if (preEl) proj.prefix = getRawOrEditedVal(preEl);
  if (sysEl) proj.system_prompt = getRawOrEditedVal(sysEl);
  if (sufEl) {
    const cleanSuf = String(getRawOrEditedVal(sufEl) || "").replace(/\n*【当前内容尺度控制[\s\S]*$/, "").trim();
    const { eroticLevel, violenceLevel, eroticEnabled, violenceEnabled } = window.getEffectiveContentScaleLevels
      ? window.getEffectiveContentScaleLevels(proj)
      : {
          eroticLevel: Number(proj.erotic_level ?? 3),
          violenceLevel: Number(proj.violence_level ?? 3),
          eroticEnabled: Boolean(proj.erotic_enabled ?? false),
          violenceEnabled: Boolean(proj.violence_enabled ?? false)
        };
    proj.erotic_level = eroticLevel;
    proj.violence_level = violenceLevel;
    proj.erotic_enabled = eroticEnabled;
    proj.violence_enabled = violenceEnabled;
    const scaleDirective = window.buildContentScalePromptDirective
      ? window.buildContentScalePromptDirective(eroticLevel, violenceLevel, eroticEnabled, violenceEnabled)
      : "";
    proj.suffix = cleanSuf ? (scaleDirective ? `${cleanSuf}\n\n${scaleDirective}` : cleanSuf) : scaleDirective;
  }
  if (sysProtoEl) proj.system_protocol_prompt = getRawOrEditedVal(sysProtoEl).trim();
  if (autoSumEl) proj.auto_summarize = autoSumEl.checked;
  const { hasModelOverride } = getActiveModelParamOverrideInfo();
  if (ctxModeEl && !hasModelOverride && !proj.use_global_params) {
    if (!proj.completion_params) proj.completion_params = {};
    proj.completion_params.context_mode = ctxModeEl.value === "tokens" ? "tokens" : "turns";
  }

  const ogListEl = document.getElementById("stOpeningGreetingsList");
  if (ogListEl) {
    const items = Array.from(ogListEl.querySelectorAll(".st-opening-greeting-item"));
    proj.opening_greetings = items.map((item, idx) => ({
      id: item.dataset.ogId || `og_${idx + 1}`,
      title: getRawOrEditedVal(item.querySelector(".st-og-title")).trim(),
      content: getRawOrEditedVal(item.querySelector(".st-og-content")).trim()
    }));
  }

  const uiModListEl = document.getElementById("stUiModulesList");
  if (uiModListEl) {
    const cards = Array.from(uiModListEl.querySelectorAll(".st-ui-mod-card"));
    proj.ui_modules = cards.map((card, idx) => {
      const mType = card.querySelector(".st-uimod-type")?.value || card.dataset.modType || "progress_stats";
      const mKey = getRawOrEditedVal(card.querySelector(".st-uimod-key")).trim() || "自定义模块";
      const rawFields = getRawOrEditedVal(card.querySelector(".st-uimod-fields")).trim();
      const rawDesc = getRawOrEditedVal(card.querySelector(".st-uimod-desc")).trim();
      return fillDefaultUiModuleDesc({
        id: card.dataset.modId || `mod_${idx + 1}`,
        type: mType,
        key: mKey,
        enabled: !!card.querySelector(".st-uimod-enabled")?.checked,
        fields: segmentUiModuleFields(rawFields, mType),
        desc: rawDesc,
        v: 2
      });
    });
  }

  const wbListEl = document.getElementById("stWorldbookList");
  if (wbListEl) {
    const prevWbMap = {};
    (Array.isArray(proj.world_book) ? proj.world_book : []).forEach((w, i) => {
      if (w && typeof w === "object") prevWbMap[w.id || `wb_${i + 1}`] = w;
    });
    const wbItems = Array.from(wbListEl.querySelectorAll(".st-wb-item"));
    proj.world_book = wbItems.map((el, idx) => {
      const wbId = el.dataset.wbId || `wb_${idx + 1}`;
      const prevItem = prevWbMap[wbId] || {};
      const matchType = el.querySelector(".st-wb-match")?.value || prevItem.match_type || "OR";
      const rawKeysStr = getRawOrEditedVal(el.querySelector(".st-wb-keys")).trim();
      let parsedKeys = [];
      if (rawKeysStr) {
        if (String(matchType) === "Regex" || String(matchType) === "3" || /^\/.+\/[gimsuy]*$/.test(rawKeysStr)) {
          parsedKeys = [rawKeysStr];
        } else {
          parsedKeys = rawKeysStr.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
        }
      }
      const nextContent = getRawOrEditedVal(el.querySelector(".st-wb-content")).trim();
      const nextEnabled = !!el.querySelector(".st-wb-enabled")?.checked;
      return {
        ...prevItem,
        id: wbId,
        name: getRawOrEditedVal(el.querySelector(".st-wb-name")).trim() || prevItem.name || `词条 #${idx + 1}`,
        keys: parsedKeys,
        match_type: matchType,
        value_region: el.querySelector(".st-wb-region")?.value || prevItem.value_region || "System",
        enabled: nextEnabled,
        enable: nextEnabled,
        content: nextContent,
        value: nextContent
      };
    });
  }

  const rxListEl = document.getElementById("stRegexList");
  if (rxListEl) {
    const prevRxMap = {};
    (Array.isArray(proj.regex_replaces) ? proj.regex_replaces : []).forEach((r, i) => {
      if (r && typeof r === "object") prevRxMap[r.id || `rx_${i + 1}`] = r;
    });
    const rxItems = Array.from(rxListEl.querySelectorAll(".st-rx-item"));
    proj.regex_replaces = rxItems.map((el, idx) => {
      const rxId = el.dataset.rxId || `rx_${idx + 1}`;
      const prevItem = prevRxMap[rxId] || {};
      const pat = el.querySelector(".st-rx-pattern")?.value ?? prevItem.pattern ?? prevItem.regex ?? "";
      const rep = el.querySelector(".st-rx-replacement")?.value ?? prevItem.replacement ?? prevItem.replace ?? "";
      const nextEnabled = !!el.querySelector(".st-rx-enabled")?.checked;
      return {
        ...prevItem,
        id: rxId,
        name: getRawOrEditedVal(el.querySelector(".st-rx-name")).trim() || prevItem.name || `规则 #${idx + 1}`,
        pattern: pat,
        regex: pat,
        replacement: rep,
        replace: rep,
        scope: el.querySelector(".st-rx-scope")?.value || prevItem.scope || "both",
        enabled: nextEnabled,
        enable: nextEnabled
      };
    });
  }

  const cgListEl = document.getElementById("stCgBookList");
  if (cgListEl) {
    const prevCgMap = {};
    (Array.isArray(proj.cg_book) ? proj.cg_book : []).forEach((c, i) => {
      if (c && typeof c === "object") prevCgMap[c.id || `cg_${i + 1}`] = c;
    });
    const cgItems = Array.from(cgListEl.querySelectorAll(".st-cg-item"));
    proj.cg_book = cgItems.map((el, idx) => {
      const cgId = el.dataset.cgId || `cg_${idx + 1}`;
      const prevItem = prevCgMap[cgId] || {};
      const nextUrl = (el.querySelector(".st-cg-url")?.value || "").trim();
      const enabledChk = el.querySelector(".st-cg-enabled");
      const nextEnabled = enabledChk ? !!enabledChk.checked : (prevItem.enabled !== false);
      return {
        ...prevItem,
        id: cgId,
        name: getRawOrEditedVal(el.querySelector(".st-cg-name")).trim() || prevItem.name || `CG #${idx + 1}`,
        keys: getRawOrEditedVal(el.querySelector(".st-cg-keys")).split(/[,，]/).map((s) => s.trim()).filter(Boolean),
        url: nextUrl,
        image_url: nextUrl,
        enabled: nextEnabled,
        enable: nextEnabled
      };
    });
  }

  const mpListEl = document.getElementById("stMemoryPalaceList");
  if (mpListEl) {
    const mpItems = Array.from(mpListEl.querySelectorAll(".st-mp-item"));
    proj.memory_palace = mpItems.map((el, idx) => ({
      id: el.dataset.mpId || `mp_${idx + 1}`,
      title: getRawOrEditedVal(el.querySelector(".st-mp-title")).trim() || `记忆 #${idx + 1}`,
      content: getRawOrEditedVal(el.querySelector(".st-mp-content")).trim()
    }));
  }

  const pvListEl = document.getElementById("stPromptVarsList");
  if (pvListEl) {
    const prevPvMap = {};
    (Array.isArray(proj.prompt_variables) ? proj.prompt_variables : []).forEach((v) => {
      const k = v && (v.name || v.key);
      if (k) prevPvMap[k] = v;
    });
    const pvItems = Array.from(pvListEl.querySelectorAll(".st-pv-item"));
    proj.prompt_variables = pvItems.map((el) => {
      const varName = (el.querySelector(".st-pv-name")?.value || "").trim();
      const prevVar = prevPvMap[varName] || {};
      const defVal = getRawOrEditedVal(el.querySelector(".st-pv-default")).trim();
      return {
        ...prevVar,
        key: varName,
        name: varName,
        label: getRawOrEditedVal(el.querySelector(".st-pv-label")).trim(),
        default: defVal,
        value: prevVar.value !== undefined ? prevVar.value : defVal
      };
    }).filter((v) => v.name);
  }
}

const QUICK_CUSTOM_UI_PRESETS = [
  {
    id: "custom_body",
    key: "身体状态",
    type: "equipment_slots",
    fields: "头部: {当前状态}\n面部: {当前状态}\n胸部: {当前状态}\n腹部: {当前状态}\n手部: {当前状态}\n私处: {当前状态}\n腿部: {当前状态}\n脚部: {当前状态}",
    desc: "每回合实时更新主角身体各部位的穿戴、损伤、束缚或生理反馈状态，采用「部位: 核心状态(细节说明)」格式输出。"
  },
  {
    id: "custom_npc_profile",
    key: "NPC档案",
    type: "text_card",
    fields: "姓名: {当前状态}\n年龄/性别: {当前状态}\n身份: {当前状态}\n性格: {当前状态}\n外貌/穿搭: {当前状态}\n特长/威胁评估: {当前状态}\n当前态度/意图: {当前状态}",
    desc: "实时记录当前在场关键 NPC 的详细档案、外貌特征、威胁评估与实时意图。"
  },
  {
    id: "custom_quest",
    key: "任务目标",
    type: "text_card",
    fields: "主线目标: {当前状态}\n当前支线: {当前状态}\n关键线索: {当前状态}\n潜在危机: {当前状态}",
    desc: "实时追踪当前主线/支线任务目标、已收集的关键线索与潜在危机倒计时。"
  },
  {
    id: "custom_corruption",
    key: "身心状态",
    type: "progress_stats",
    fields: "理智值: 100/100\n羞耻度: 0/100\n兴奋度: 0/100\n敏感度: 0/100\n屈服度: 0/100\n当前处境: 保持警惕(尚未失守)",
    desc: "实时追踪主角的理智、羞耻、兴奋、敏感与屈服等身心数值变化。"
  }
];

window.smartGenerateUiModuleTemplate = function (rawKey, currentType = "") {
  const k = String(rawKey || "").trim();
  if (/身体|部位|肉体|躯体|穿戴|服饰|衣着|拘束|束缚/.test(k)) {
    return QUICK_CUSTOM_UI_PRESETS[0];
  }
  if (/npc|人物|档案|敌人|对手|头目|目标人物|角色卡/i.test(k) && !/好感|关系/.test(k)) {
    return QUICK_CUSTOM_UI_PRESETS[1];
  }
  if (/任务|目标|委托|主线|支线|线索|调查|悬赏/.test(k)) {
    return QUICK_CUSTOM_UI_PRESETS[2];
  }
  if (/恶堕|淫乱|羞耻|敏感|调教|快感|兴奋|催眠|屈服|堕落|身心|欲/.test(k)) {
    return QUICK_CUSTOM_UI_PRESETS[3];
  }
  if (/好感|关系|羁绊|同伴|后宫/.test(k)) {
    const std = STANDARD_UI_MODULES.find((m) => m.id === "mod_npc");
    if (std) return { type: std.type, fields: std.fields, desc: std.desc };
  }
  if (/装备|武器|防具|护甲|法宝|义体/.test(k)) {
    const std = STANDARD_UI_MODULES.find((m) => m.id === "mod_equip");
    if (std) return { type: std.type, fields: std.fields, desc: std.desc };
  }
  if (/物品|背包|道具|行囊|仓库|储物/.test(k)) {
    const std = STANDARD_UI_MODULES.find((m) => m.id === "mod_inv");
    if (std) return { type: std.type, fields: std.fields, desc: std.desc };
  }
  if (/新闻|情报|传闻|世界|环境|局势|广播/.test(k)) {
    const std = STANDARD_UI_MODULES.find((m) => m.id === "mod_info");
    if (std) return { type: std.type, fields: std.fields, desc: std.desc };
  }
  const t = currentType || "text_card";
  if (t === "progress_stats") {
    return {
      type: "progress_stats",
      fields: `${k || "当前数值"}: 0/100\n当前状态: {当前状态}`,
      desc: `必须将【${k || "自定义状态"}】置于 <status> 块内的 [${k || "自定义状态"}] 标题下，按「字段: 当前值/上限」或「字段: 状态说明」逐行输出。`
    };
  }
  if (t === "equipment_slots") {
    return {
      type: "equipment_slots",
      fields: `槽位1: {当前状态}\n槽位2: {当前状态}\n槽位3: {当前状态}`,
      desc: `必须将【${k || "自定义槽位"}】置于 <status> 块内的 [${k || "自定义槽位"}] 标题下，每行按「字段: 名称(简短说明)」格式输出。`
    };
  }
  if (t === "inventory_grid") {
    return {
      type: "inventory_grid",
      fields: `示例物品(简短说明)x1`,
      desc: `必须将【${k || "物品列表"}】置于 <status> 块内的 [${k || "物品列表"}] 标题下，每行按「物品名(简短说明)x数量」格式输出。`
    };
  }
  if (t === "npc_affinity") {
    return {
      type: "npc_affinity",
      fields: `角色: {角色名}\n好感: 50/100\n态度: {当前态度}\n动态: {当前行为或心理}`,
      desc: `必须将【${k || "人物关系"}】置于 <status> 块内的 [${k || "人物关系"}] 标题下，记录在场角色的姓名、好感、态度与动态。`
    };
  }
  return {
    type: "text_card",
    fields: `${k || "核心状态"}: {当前状态}\n细节补充: {当前状态}`,
    desc: `必须将【${k || "自定义栏位"}】置于 <status> 块内的 [${k || "自定义栏位"}] 标题下，严格按参考字段每行输出「字段名: 当前内容」。`
  };
};

window.applyStandardUiModulePreset = function (modId) {
  const stdMod = STANDARD_UI_MODULES.find((m) => m.id === modId) || QUICK_CUSTOM_UI_PRESETS.find((m) => m.id === modId);
  if (!stdMod) return;
  const modal = document.getElementById("customUiModuleModal");
  if (modal) modal.dataset.presetModId = stdMod.id;
  const keyEl = document.getElementById("newUiModKey");
  const typeEl = document.getElementById("newUiModType");
  const fieldsEl = document.getElementById("newUiModFields");
  const descEl = document.getElementById("newUiModDesc");
  if (keyEl) keyEl.value = stdMod.key;
  if (typeEl) {
    typeEl.value = stdMod.type;
    if (typeof window.syncNewUiModTypePlaceholder === "function") {
      window.syncNewUiModTypePlaceholder(stdMod.type);
    }
  }
  if (fieldsEl) {
    fieldsEl.value = stdMod.fields;
    fieldsEl.dataset.autoGenerated = "1";
  }
  if (descEl) {
    descEl.value = stdMod.desc;
    descEl.dataset.autoGenerated = "1";
  }
};

window.autoFillNewUiModuleFromKey = function (forceOverwrite = false) {
  const keyEl = document.getElementById("newUiModKey");
  const typeEl = document.getElementById("newUiModType");
  const fieldsEl = document.getElementById("newUiModFields");
  const descEl = document.getElementById("newUiModDesc");
  if (!keyEl || !fieldsEl) return;
  const k = keyEl.value.trim();
  const rawFields = fieldsEl.value.trim();
  // 如果用户已经在「格式参考」里随手写了几个词（比如 "头部 胸部 腹部"），点智能生成时直接把用户的词转成标准格式！
  if (forceOverwrite && rawFields && fieldsEl.dataset.autoGenerated !== "1") {
    fieldsEl.value = segmentUiModuleFields(rawFields, typeEl?.value || "text_card");
    if (descEl && !descEl.value.trim()) {
      const tpl = window.smartGenerateUiModuleTemplate(k, typeEl?.value || "text_card");
      descEl.value = tpl.desc;
      descEl.dataset.autoGenerated = "1";
    }
    showToast("已将你输入的词转为标准状态栏格式");
    return;
  }
  if (!k) {
    if (forceOverwrite) showToast("请先输入栏位名称，或在格式参考中随便写几个字段词");
    return;
  }
  const tpl = window.smartGenerateUiModuleTemplate(k, typeEl?.value || "");
  if (typeEl && (forceOverwrite || !fieldsEl.value.trim() || fieldsEl.dataset.autoGenerated === "1")) {
    typeEl.value = tpl.type;
    if (typeof window.syncNewUiModTypePlaceholder === "function") {
      window.syncNewUiModTypePlaceholder(tpl.type);
    }
  }
  if (forceOverwrite || !fieldsEl.value.trim() || fieldsEl.dataset.autoGenerated === "1") {
    fieldsEl.value = tpl.fields;
    fieldsEl.dataset.autoGenerated = "1";
  }
  if (descEl && (forceOverwrite || !descEl.value.trim() || descEl.dataset.autoGenerated === "1")) {
    descEl.value = tpl.desc;
    descEl.dataset.autoGenerated = "1";
  }
  if (forceOverwrite) showToast(`已为「${k}」自动生成标准格式与规则`);
};

window.openAddCustomUiModuleModal = function () {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  let modal = document.getElementById("customUiModuleModal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "customUiModuleModal";
    modal.className = "modal-overlay";
    document.body.appendChild(modal);
  }
  delete modal.dataset.presetModId;
  modal.innerHTML = `
    <div class="modal-card" style="max-width:560px;">
      <div class="modal-header">
        <h3>添加状态栏 / 功能栏位</h3>
        <button type="button" class="modal-close" onclick="document.getElementById('customUiModuleModal').style.display='none'">✕</button>
      </div>
      <div class="modal-body" style="display:flex;flex-direction:column;gap:11px;">
        <div style="padding:8px 11px;border-radius:8px;background:var(--tc-rgba-16-185-129-0-09, rgba(16,185,129,0.09));border:1px solid var(--tc-rgba-16-185-129-0-32, rgba(16,185,129,0.32));font-size:11.5px;color:var(--tc-a7f3d0, #a7f3d0);line-height:1.55;">
          💡 <b>傻瓜式自定义</b>：① 直接点下方<b>一键模板</b>；或 ② <b>只填「名称」</b>（格式留空也会自动生成）；或 ③ 在格式框里<b>用空格/顿号随便写几个词</b>（如 <code>头部 胸部 腹部 私处</code>），系统会自动转成标准状态栏！
        </div>
        <div style="padding:9px 11px;border-radius:8px;background:var(--tc-rgba-99-102-241-0-08, rgba(99,102,241,0.08));border:1px solid var(--tc-rgba-99-102-241-0-3, rgba(99,102,241,0.3));">
          <div style="font-size:11.5px;font-weight:700;color:var(--tc-c7d2fe, #c7d2fe);margin-bottom:6px;">一键预设模板（点击直接填入）</div>
          <div style="display:flex;flex-wrap:wrap;gap:6px;">
            ${STANDARD_UI_MODULES.map((m) => `
              <button type="button" class="btn btn-xs btn-outline-secondary" style="padding:3px 9px;font-size:11.5px;border-color:var(--tc-rgba-165-180-252-0-38, rgba(165,180,252,0.38));" onclick="window.applyStandardUiModulePreset('${escapeJsAttr(m.id)}')">
                ${escapeHtml(m.key)}
              </button>
            `).join("")}
            ${QUICK_CUSTOM_UI_PRESETS.map((m) => `
              <button type="button" class="btn btn-xs btn-outline-secondary" style="padding:3px 9px;font-size:11.5px;border-color:var(--tc-rgba-52-211-153-0-45, rgba(52,211,153,0.45));color:var(--tc-6ee7b7, #6ee7b7);" onclick="window.applyStandardUiModulePreset('${escapeJsAttr(m.id)}')">
                + ${escapeHtml(m.key)}
              </button>
            `).join("")}
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 150px;gap:10px;">
          <div>
            <label style="font-size:12px;font-weight:700;display:block;margin-bottom:4px;">栏位名称 <span style="color:var(--tc-f87171, #f87171);">*</span></label>
            <input type="text" id="newUiModKey" class="form-input" placeholder="如：身体状态 / NPC档案 / 任务目标" oninput="window.autoFillNewUiModuleFromKey && window.autoFillNewUiModuleFromKey(false)" />
          </div>
          <div>
            <label style="font-size:12px;font-weight:700;display:block;margin-bottom:4px;">显示样式</label>
            <select id="newUiModType" class="form-select" onchange="window.syncNewUiModTypePlaceholder && window.syncNewUiModTypePlaceholder(this.value)">
              <option value="text_card" selected>分块卡片 (通用推荐)</option>
              <option value="equipment_slots">部位/装备槽</option>
              <option value="progress_stats">数值进度条 (0/100)</option>
              <option value="npc_affinity">NPC好感卡</option>
              <option value="inventory_grid">物品背包格 (x数量)</option>
              <option value="thinking_fold">思考推演</option>
              <option value="story_narrative">剧情正文</option>
              <option value="action_choices">行动选项</option>
            </select>
          </div>
        </div>
        <div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
            <label style="font-size:12px;font-weight:700;">包含哪些字段 <span style="font-weight:400;font-size:11px;color:var(--text-muted);">（可留空自动生成，或用空格/顿号随便写几个词）</span></label>
            <button type="button" class="btn btn-xs btn-outline-secondary" style="padding:1px 8px;font-size:11px;color:var(--tc-a7f3d0, #a7f3d0);border-color:var(--tc-rgba-16-185-129-0-4, rgba(16,185,129,0.4));" onclick="window.autoFillNewUiModuleFromKey && window.autoFillNewUiModuleFromKey(true)">✨ 一键智能转格式</button>
          </div>
          <textarea id="newUiModFields" rows="4" class="form-textarea" placeholder="直接写词即可，例如：头部 胸部 腹部 私处（系统会自动补全冒号与状态占位符）" oninput="delete this.dataset.autoGenerated"></textarea>
        </div>
        <div>
          <label style="font-size:12px;font-weight:700;color:var(--tc-a5b4fc, #a5b4fc);display:block;margin-bottom:4px;">AI 填写规则 <span style="font-weight:400;font-size:11px;color:var(--text-muted);">（选填，留空会自动生成规则）</span></label>
          <textarea id="newUiModDesc" rows="2" class="form-textarea" placeholder="留空即可，系统会自动告诉 AI 每回合更新此栏位" oninput="delete this.dataset.autoGenerated"></textarea>
        </div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" onclick="document.getElementById('customUiModuleModal').style.display='none'">取消</button>
        <button type="button" class="btn btn-primary" onclick="window.confirmAddCustomUiModule()">添加栏位</button>
      </div>
    </div>
  `;
  document.getElementById("newUiModKey").value = "";
  document.getElementById("newUiModFields").value = "";
  document.getElementById("newUiModDesc").value = "";
  if (typeof window.syncNewUiModTypePlaceholder === "function") {
    window.syncNewUiModTypePlaceholder(document.getElementById("newUiModType")?.value || "text_card");
  }
  modal.style.display = "flex";
};

window.syncNewUiModTypePlaceholder = function (typeVal) {
  const fieldsEl = document.getElementById("newUiModFields");
  const descEl = document.getElementById("newUiModDesc");
  if (!fieldsEl) return;
  const map = {
    progress_stats: "可以直接写：生命 体力 理智 恶堕度（会自动转为 0/100 进度条格式）",
    text_card: "可以直接写：姓名 年龄 身份 性格 威胁评估（会自动转为分块卡片格式）",
    equipment_slots: "可以直接写：头部 面部 上身 下身 手部 脚部（会自动转为部位/装备槽格式）",
    inventory_grid: "可以直接写：手电筒、急救包、备用弹匣（会自动转为 x1 物品格格式）",
    npc_affinity: "角色: 师姐\n好感: 75/100\n态度: 关切\n动态: 正在擦拭长剑",
    story_narrative: "第二人称，注重感官细节",
    thinking_fold: "<think>\n1. 局势与动机推演\n2. 检定与分支判定\n</think>",
    action_choices: "1. 【稳健/交涉】常规推进\n2. 【博弈/险招】高风险高回报 【🎲属性检定】\n3. 【环境/道具破局】利用场景或道具\n4. 【逆反/鬼点子】出人意料的脑洞"
  };
  const descMap = {
    progress_stats: "选填，留空将自动要求 AI 每回合更新数值与状态",
    text_card: "选填，留空将自动要求 AI 每回合更新各字段内容",
    equipment_slots: "选填，留空将自动要求 AI 每回合更新各部位/槽位状态",
    inventory_grid: "选填，留空将自动要求 AI 每回合增减随身物品",
    npc_affinity: "选填，留空将自动要求 AI 每回合更新在场角色好感与动态",
    story_narrative: "叙事规则",
    thinking_fold: "推演规则",
    action_choices: "选项规则"
  };
  fieldsEl.placeholder = map[typeVal] || map.text_card;
  if (descEl) descEl.placeholder = descMap[typeVal] || descMap.text_card;
};

window.confirmAddCustomUiModule = async function () {
  const modal = document.getElementById("customUiModuleModal");
  const presetId = modal?.dataset?.presetModId || "";
  const key = (document.getElementById("newUiModKey")?.value || "").trim();
  const type = document.getElementById("newUiModType")?.value || "text_card";
  if (!key) {
    showToast("请输入栏位名称");
    return;
  }
  const smartTpl = window.smartGenerateUiModuleTemplate
    ? window.smartGenerateUiModuleTemplate(key, type)
    : { fields: `${key}: {当前状态}`, desc: "" };
  const rawFieldsInput = (document.getElementById("newUiModFields")?.value || "").trim() || smartTpl.fields || `${key}: {当前状态}`;
  const fields = segmentUiModuleFields(rawFieldsInput, type);
  const desc = (document.getElementById("newUiModDesc")?.value || "").trim() || smartTpl.desc || "";
  const proj = getActiveProjectObj();
  if (!proj) return;
  proj.ui_modules = getEffectiveUiModules(proj);
  const matchedStd = STANDARD_UI_MODULES.find((m) => m.id === presetId || m.key === key);
  const candidateId = matchedStd && !proj.ui_modules.some((m) => m.id === matchedStd.id)
    ? matchedStd.id
    : `mod_custom_${Date.now().toString(36)}`;
  const newMod = fillDefaultUiModuleDesc({
    id: candidateId,
    key,
    type,
    enabled: true,
    fields,
    ...(desc ? { desc } : {}),
    v: 2
  });
  // 若新增的是三大唯一核心模块（思考推演 / 剧情正文 / 行动选项），若列表中已存在同类型模块，直接原地更新并启用
  if (["thinking_fold", "story_narrative", "action_choices"].includes(newMod.type)) {
    const existIdx = proj.ui_modules.findIndex((m) => m.type === newMod.type || m.id === newMod.id);
    if (existIdx !== -1) {
      proj.ui_modules[existIdx] = {
        ...proj.ui_modules[existIdx],
        ...newMod,
        enabled: true
      };
      proj.status_panel_enabled = true;
      document.getElementById("customUiModuleModal").style.display = "none";
      renderStudioWorkbench();
      await window.saveStudioProjectConfig(false);
      if (typeof window.renderMessages === "function") window.renderMessages();
      showToast(`已启用「${key}」`);
      return;
    }
  }
  if (newMod.type === "thinking_fold") {
    // 思考推演默认置于最顶部（#1）
    proj.ui_modules.unshift(newMod);
  } else if (newMod.type === "story_narrative") {
    // 剧情正文默认置于思考推演之后、其余状态栏之前
    const thinkIdx = proj.ui_modules.findIndex((m) => m.type === "thinking_fold" || m.id === "mod_think");
    proj.ui_modules.splice(thinkIdx + 1, 0, newMod);
  } else {
    // 其余栏位默认插入在底部『行动选项』之前
    const choicesIdx = proj.ui_modules.findIndex((m) => m.type === "action_choices" || m.id === "mod_choices");
    if (newMod.type !== "action_choices" && choicesIdx !== -1) {
      proj.ui_modules.splice(choicesIdx, 0, newMod);
    } else {
      proj.ui_modules.push(newMod);
    }
  }
  proj.status_panel_enabled = true;
  document.getElementById("customUiModuleModal").style.display = "none";
  renderStudioWorkbench();
  await window.saveStudioProjectConfig(false);
  if (typeof window.renderMessages === "function") window.renderMessages();
  showToast(`已添加「${key}」`);
};

window.removeCustomUiModule = async function (idx) {
  if (typeof showCustomDialog === "function" && !(await showCustomDialog({ title: "删除栏位", message: "确定删除这个栏位吗？" }))) return;
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  proj.ui_modules = getEffectiveUiModules(proj);
  proj.ui_modules.splice(idx, 1);
  renderStudioWorkbench();
  await window.saveStudioProjectConfig(false);
  if (typeof window.renderMessages === "function") window.renderMessages();
};

window.moveUiModule = async function (idx, delta) {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  const list = getEffectiveUiModules(proj);
  const targetIdx = idx + delta;
  if (targetIdx < 0 || targetIdx >= list.length) return;
  const temp = list[idx];
  list[idx] = list[targetIdx];
  list[targetIdx] = temp;
  proj.ui_modules = list;
  const prevScroll = getStudioScrollContainer()?.scrollTop || 0;
  renderStudioWorkbench();
  // renderStudioWorkbench 会重建 #studioTabBody，需在渲染后重新获取滚动容器
  const wbEl = getStudioScrollContainer();
  if (wbEl) wbEl.scrollTop = prevScroll;
  await window.saveStudioProjectConfig(false);
  if (typeof window.renderMessages === "function") window.renderMessages(undefined, true);
  showToast(`已移至第 ${targetIdx + 1} 位`);
};

// HTML5 + Pointer/Touch 实时 DOM 拖拽排序实现：拖动任意模块实时交换位置并决定其出场顺序
let _draggedUiModIdx = null;
let _draggedUiModCard = null;
let _draggedUiModInitialIds = [];
let _draggedUiModCommitted = false;

function _refreshUiModLiveSeqNumbers(listEl) {
  if (!listEl) return;
  const cards = listEl.querySelectorAll(".st-ui-mod-card");
  cards.forEach((c, i) => {
    c.dataset.modIdx = String(i);
    const seqEl = c.querySelector(".uimod-seq-num");
    if (seqEl) seqEl.textContent = String(i + 1);
  });
}

function _liveSortUiModCardByClientY(clientY) {
  const listEl = document.getElementById("stUiModulesList");
  if (!listEl || !_draggedUiModCard || !Number.isFinite(clientY)) return;
  const siblings = Array.from(listEl.querySelectorAll(".st-ui-mod-card")).filter((c) => c !== _draggedUiModCard);
  if (siblings.length === 0) return;

  let nextSibling = null;
  for (const sib of siblings) {
    const rect = sib.getBoundingClientRect();
    const midY = rect.top + rect.height / 2;
    if (clientY < midY) {
      nextSibling = sib;
      break;
    }
  }

  siblings.forEach((s) => s.classList.remove("uimod-drag-over"));
  if (nextSibling) {
    if (_draggedUiModCard.nextElementSibling !== nextSibling) {
      listEl.insertBefore(_draggedUiModCard, nextSibling);
      _refreshUiModLiveSeqNumbers(listEl);
    }
  } else {
    if (listEl.lastElementChild !== _draggedUiModCard) {
      listEl.appendChild(_draggedUiModCard);
      _refreshUiModLiveSeqNumbers(listEl);
    }
  }
}

async function _commitUiModLiveOrder(fallbackDropIdx = null) {
  if (_draggedUiModCommitted) return;
  _draggedUiModCommitted = true;

  const listEl = document.getElementById("stUiModulesList");
  const draggedCard = _draggedUiModCard;
  const fromIdx = _draggedUiModIdx;
  const initialIds = Array.isArray(_draggedUiModInitialIds) ? _draggedUiModInitialIds.slice() : [];

  _draggedUiModIdx = null;
  _draggedUiModCard = null;
  _draggedUiModInitialIds = [];

  if (listEl) {
    listEl.classList.remove("is-sorting-uimod");
    listEl.querySelectorAll(".st-ui-mod-card").forEach((c) => {
      c.classList.remove("uimod-dragging", "uimod-drag-over");
      c.setAttribute("draggable", "true");
    });
  }

  if (!listEl) return;
  const currentCards = Array.from(listEl.querySelectorAll(".st-ui-mod-card"));
  const currentIds = currentCards.map((c) => c.dataset.modId || "");
  let orderChanged = initialIds.length === currentIds.length && currentIds.some((id, i) => id !== initialIds[i]);

  // 兜底：若浏览器未触发实时 insertBefore 但传入了明确的目标 dropIdx
  if (!orderChanged && fallbackDropIdx !== null && fromIdx !== null && fromIdx !== fallbackDropIdx && currentCards[fromIdx] && currentCards[fallbackDropIdx]) {
    const movingEl = currentCards[fromIdx];
    const targetEl = currentCards[fallbackDropIdx];
    if (fromIdx < fallbackDropIdx) {
      listEl.insertBefore(movingEl, targetEl.nextElementSibling);
    } else {
      listEl.insertBefore(movingEl, targetEl);
    }
    orderChanged = true;
  }

  if (!orderChanged) return;

  const finalCards = Array.from(listEl.querySelectorAll(".st-ui-mod-card"));
  const newIdx = draggedCard ? finalCards.indexOf(draggedCard) : -1;
  const movedTitle = draggedCard?.querySelector(".st-uimod-key")?.value?.trim() || "模块";

  // collectCurrentTabFormState 直接按当前 #stUiModulesList 的最新 DOM 顺序收集并写入 proj.ui_modules
  collectCurrentTabFormState();
  const prevScroll = getStudioScrollContainer()?.scrollTop || 0;
  renderStudioWorkbench();
  // renderStudioWorkbench 会重建 #studioTabBody，需在渲染后重新获取滚动容器
  const wbEl = getStudioScrollContainer();
  if (wbEl) wbEl.scrollTop = prevScroll;
  await window.saveStudioProjectConfig(false);
  if (typeof window.renderMessages === "function") window.renderMessages(undefined, true);
  if (newIdx !== -1) {
    showToast(`已移至第 ${newIdx + 1} 位`);
  } else {
    showToast("已排序");
  }
}

window.onUiModDragStart = function (ev, idx) {
  const targetTag = (ev.target && ev.target.tagName) ? ev.target.tagName.toLowerCase() : "";
  if (["input", "textarea", "select", "button"].includes(targetTag)) {
    ev.preventDefault();
    return;
  }
  const card = ev.currentTarget?.closest?.(".st-ui-mod-card") || ev.currentTarget;
  const listEl = document.getElementById("stUiModulesList");
  if (!card || !listEl) return;

  _draggedUiModIdx = idx;
  _draggedUiModCard = card;
  _draggedUiModCommitted = false;
  _draggedUiModInitialIds = Array.from(listEl.querySelectorAll(".st-ui-mod-card")).map((c) => c.dataset.modId || "");

  if (ev.dataTransfer) {
    ev.dataTransfer.effectAllowed = "move";
    try {
      ev.dataTransfer.setData("application/x-trpg-uimod", String(idx));
    } catch (_) {
      ev.dataTransfer.setData("text/plain", String(idx));
    }
  }
  card.classList.add("uimod-dragging");
  // 延迟一帧启用 .is-sorting-uimod（屏蔽卡片内部 input/textarea 的 pointer-events，避免浏览器将拖拽误判为往文本框拖字而吞掉 drop）
  setTimeout(() => {
    if (_draggedUiModCard === card && listEl) {
      listEl.classList.add("is-sorting-uimod");
    }
  }, 0);
};

window.onUiModDragOver = function (ev, overIdx) {
  ev.preventDefault();
  ev.stopPropagation();
  if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
  _liveSortUiModCardByClientY(ev.clientY);
};

window.onUiModListDragOver = function (ev) {
  if (!_draggedUiModCard) return;
  ev.preventDefault();
  if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
  _liveSortUiModCardByClientY(ev.clientY);
};

window.onUiModDragLeave = function (ev) {
  const card = ev.currentTarget;
  if (card && !card.contains(ev.relatedTarget)) {
    card.classList.remove("uimod-drag-over");
  }
};

window.onUiModDrop = async function (ev, dropIdx) {
  ev.preventDefault();
  ev.stopPropagation();
  await _commitUiModLiveOrder(dropIdx);
};

window.onUiModListDrop = async function (ev) {
  if (!_draggedUiModCard) return;
  ev.preventDefault();
  ev.stopPropagation();
  await _commitUiModLiveOrder(null);
};

window.onUiModDragEnd = async function (ev) {
  await _commitUiModLiveOrder(null);
};

// 触屏 / 手机端按住「⠿ #序号」手柄上下滑动实时排序支持
window.onUiModHandlePointerDown = function (ev) {
  if (ev.pointerType !== "touch" && ev.pointerType !== "pen") return;
  const handle = ev.currentTarget;
  const card = handle?.closest?.(".st-ui-mod-card");
  const listEl = document.getElementById("stUiModulesList");
  if (!card || !listEl) return;

  ev.preventDefault();
  ev.stopPropagation();
  try {
    handle.setPointerCapture(ev.pointerId);
  } catch (_) {}

  const allCards = Array.from(listEl.querySelectorAll(".st-ui-mod-card"));
  _draggedUiModIdx = allCards.indexOf(card);
  _draggedUiModCard = card;
  _draggedUiModCommitted = false;
  _draggedUiModInitialIds = allCards.map((c) => c.dataset.modId || "");

  card.classList.add("uimod-dragging");
  listEl.classList.add("is-sorting-uimod");

  const onMove = (moveEv) => {
    if (moveEv.pointerId !== ev.pointerId) return;
    moveEv.preventDefault();
    _liveSortUiModCardByClientY(moveEv.clientY);
  };
  const onEnd = async (endEv) => {
    if (endEv.pointerId !== ev.pointerId) return;
    handle.removeEventListener("pointermove", onMove);
    handle.removeEventListener("pointerup", onEnd);
    handle.removeEventListener("pointercancel", onEnd);
    try {
      handle.releasePointerCapture(ev.pointerId);
    } catch (_) {}
    await _commitUiModLiveOrder(null);
  };

  handle.addEventListener("pointermove", onMove);
  handle.addEventListener("pointerup", onEnd);
  handle.addEventListener("pointercancel", onEnd);
};

// 供正文中直接拖拽模块卡片或跨模块调整顺序时调用的同步接口
window.reorderProjectUiModulesByDomOrder = async function (orderedKeysOrIds, movedLabel = "模块") {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj || !Array.isArray(orderedKeysOrIds) || orderedKeysOrIds.length === 0) return;
  const list = getEffectiveUiModules(proj);
  if (list.length <= 1) return;

  const findModIndex = (token) => {
    const t = String(token || "").trim();
    if (!t) return -1;
    return list.findIndex((m) => {
      const k = String(m.key || "").trim();
      return m.id === t || m.type === t || k === t || (k && (t.includes(k) || k.includes(t)));
    });
  };

  const matchedIndices = [];
  orderedKeysOrIds.forEach((tok) => {
    const idx = findModIndex(tok);
    if (idx !== -1 && !matchedIndices.includes(idx)) {
      matchedIndices.push(idx);
    }
  });
  if (matchedIndices.length <= 1) return;

  const sortedSlotPositions = [...matchedIndices].sort((a, b) => a - b);
  const reorderedSubset = matchedIndices.map((idx) => list[idx]);
  sortedSlotPositions.forEach((slotPos, i) => {
    list[slotPos] = reorderedSubset[i];
  });

  proj.ui_modules = list;
  const prevScroll = getStudioScrollContainer()?.scrollTop || 0;
  renderStudioWorkbench();
  // renderStudioWorkbench 会重建 #studioTabBody，需在渲染后重新获取滚动容器
  const wbEl = getStudioScrollContainer();
  if (wbEl) wbEl.scrollTop = prevScroll;
  await window.saveStudioProjectConfig(false);
  if (typeof window.renderMessages === "function") window.renderMessages(undefined, true);
  showToast("已排序");
};

window.resetUiModulesToDefault = async function () {
  const proj = getActiveProjectObj();
  if (!proj) return;
  if (typeof showCustomDialog === "function" && !(await showCustomDialog({ title: "恢复默认栏位", message: "将清除所有自定义栏位，确定吗？" }))) return;
  proj.ui_modules = DEFAULT_UNIVERSAL_UI_MODULES.map((m) => ({ ...m }));
  proj.status_panel_enabled = true;
  renderStudioWorkbench();
  await window.saveStudioProjectConfig(false);
  if (typeof window.renderMessages === "function") window.renderMessages(undefined, true);
  showToast("已恢复默认栏位");
};

// 系统提示词保存、重置与 AI 润色（随当前游戏配置保存，支持留空以彻底关闭系统协议提示词）
window.saveGlobalSystemProtocolPrompt = async function (val) {
  const stEl = document.getElementById("stGlobalSystemProtocolPrompt");
  const modalEl = document.getElementById("settingGlobalSystemProtocolPrompt");
  const settingsModal = document.getElementById("settingsModal");
  const isSettingsModalOpen = Boolean(
    settingsModal &&
    (settingsModal.classList.contains("active") || settingsModal.style.display === "flex" || settingsModal.style.display === "block")
  );
  let rawVal = "";
  if (val !== undefined) {
    rawVal = val === null ? "" : String(val);
  } else if (isSettingsModalOpen && modalEl) {
    rawVal = String(modalEl.value ?? "");
  } else if (stEl) {
    rawVal = String(stEl.value ?? "");
  } else if (modalEl) {
    rawVal = String(modalEl.value ?? "");
  }
  const cleanVal = rawVal.trim();
  const proj = getActiveProjectObj();
  const shouldSyncGlobal = Boolean(isSettingsModalOpen || !proj || proj.id === "proj_default");
  if (stEl && (!proj || !isFreeChatProject(proj)) && (!isSettingsModalOpen || !proj || proj.id === "proj_default")) {
    stEl.value = cleanVal;
    delete stEl._origRoVal;
    delete stEl._lastEnRoVal;
  }
  if (modalEl && shouldSyncGlobal) {
    modalEl.value = cleanVal;
    delete modalEl._origRoVal;
    delete modalEl._lastEnRoVal;
  }
  if (proj && !isFreeChatProject(proj) && (!isSettingsModalOpen || proj.id === "proj_default")) {
    proj.system_protocol_prompt = cleanVal;
    await window.saveStudioProjectConfig(false);
  }
  if (!shouldSyncGlobal) {
    showToast(cleanVal ? "已保存" : "已清空");
    return;
  }
  if (!window.globalUserSettings) window.globalUserSettings = {};
  window.globalUserSettings.global_system_protocol_prompt = cleanVal;
  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ global_system_protocol_prompt: cleanVal })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showToast(cleanVal ? "已保存" : "已清空");
  } catch (err) {
    showToast("保存失败: " + err.message);
  }
};

window.expandUiModulesIntoGlobalPrompt = async function () {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  const specBlock = buildFrontendUiModulesSpecBlock(proj);
  const stEl = document.getElementById("stGlobalSystemProtocolPrompt");
  const modalEl = document.getElementById("settingGlobalSystemProtocolPrompt");
  const currentRaw = String(stEl?.value || modalEl?.value || DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT).trim();
  let expanded = currentRaw;
  if (expanded.includes("{{UI_MODULES_SPEC}}")) {
    expanded = expanded.replace("{{UI_MODULES_SPEC}}", specBlock);
  } else if (expanded.includes("7. 【当前模块出场顺序") || expanded.includes("6. 【当前模块出场顺序")) {
    const idx7 = expanded.indexOf("7. 【当前模块出场顺序");
    const idx6 = expanded.indexOf("6. 【当前模块出场顺序");
    const idx = idx7 !== -1 ? idx7 : idx6;
    expanded = expanded.slice(0, idx).trim() + "\n\n7. 【当前模块出场顺序、字段格式与功能栏专属规则（由工作台自动注入或手动编辑）】：\n" + specBlock;
  } else {
    expanded = expanded + "\n\n7. 【当前模块出场顺序、字段格式与功能栏专属规则（由工作台自动注入或手动编辑）】：\n" + specBlock;
  }
  if (stEl) stEl.value = expanded;
  if (modalEl && (!proj || proj.id === "proj_default")) modalEl.value = expanded;
  await window.saveGlobalSystemProtocolPrompt(expanded);
  showToast("已写入系统提示词");
};

window.resetGlobalSystemProtocolPrompt = async function () {
  if (!window.confirm("恢复默认提示词？")) return;
  const stEl = document.getElementById("stGlobalSystemProtocolPrompt");
  const modalEl = document.getElementById("settingGlobalSystemProtocolPrompt");
  const settingsModal = document.getElementById("settingsModal");
  const isSettingsModalOpen = Boolean(
    settingsModal &&
    (settingsModal.classList.contains("active") || settingsModal.style.display === "flex" || settingsModal.style.display === "block")
  );
  const proj = getActiveProjectObj();
  if (stEl && (!isSettingsModalOpen || !proj || proj.id === "proj_default")) stEl.value = DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT;
  if (modalEl && (isSettingsModalOpen || !proj || proj.id === "proj_default")) modalEl.value = DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT;
  await window.saveGlobalSystemProtocolPrompt(DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT);
  showToast("已恢复默认");
};

window.polishGlobalSystemProtocolPrompt = async function (btnEl) {
  const el = document.getElementById("stGlobalSystemProtocolPrompt") || document.getElementById("settingGlobalSystemProtocolPrompt");
  const hintEl = document.getElementById("stHint_global_proto");
  const localHint = hintEl?.value.trim() || "";
  const selectedModel = document.getElementById("studioAiModelSelect")?.value || "";
  const proj = getActiveProjectObj();
  const origLabel = btnEl ? btnEl.innerHTML : "润色";
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.innerHTML = "润色中...";
  }
  try {
    const instruction = [
      "请润色全局默认系统提示词（必须完整保留 `<status>...</status>` 功能栏五大语法协议、剧情正文栏规则、`{{UI_MODULES_SPEC}}` 占位符以及 `【🎲属性检定】` 图标触发规则，切勿删除 `<status>` 标签要求）",
      localHint ? `修改想法：${localHint}` : ""
    ].filter(Boolean).join("；");
    const polished = await callAiPolishApi(el ? el.value : DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT, "system_prompt", proj?.name || "跑团工作台", instruction, selectedModel);
    if (polished && el) {
      el.value = polished;
      await window.saveGlobalSystemProtocolPrompt(polished);
    }
  } catch (err) {
    showToast("润色失败: " + err.message);
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.innerHTML = origLabel;
    }
  }
};

window.polishUiModuleField = async function (idx, btnEl) {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  const mods = getEffectiveUiModules(proj);
  const mod = mods[idx];
  if (!mod) return;
  const fieldsInput = document.getElementById(`stUiModFields_${idx}`);
  const descInput = document.getElementById(`stUiModDesc_${idx}`);
  const hintInput = document.getElementById(`stHint_uimod_${idx}`);
  const localHint = hintInput?.value.trim() || "";
  const globalHint = document.getElementById("studioGlobalPolishInstruction")?.value.trim() || "";
  const selectedModel = document.getElementById("studioAiModelSelect")?.value || "";
  const typeDescMap = {
    thinking_fold: "AI 幕后思考推演 (<think>) 的推演重点与规则",
    story_narrative: "主线剧情正文的人称、文风、镜头感与描写规范",
    progress_stats: "状态栏数值进度条与状态标签（每行一个字段，如：生命: 100/100）",
    equipment_slots: "装备/身体栏槽位（每行一个槽位/部位，不同分组可空行分段）",
    inventory_grid: "背包物品格（每行一个物品，格式如：物品A(效果)x数量）",
    npc_affinity: "角色关系好感卡（每行一个属性，如：角色 / 好感: 50/100 / 态度 / 动态）",
    text_card: "独立情报/文本模块（每行一个子项或按段落分行）",
    action_choices: "底部行动选项模块（分4行列出 1.~4. 选项维度）"
  };
  const instruction = [
    `当前正在定制状态栏/模块【${mod.key}】（类型：${typeDescMap[mod.type] || "自定义模块"}）。请按以下两个区块输出：\n【字段格式】\n（这里分行/分段写出各字段或槽位格式参考样本，每个字段独占一行，不同类别的字段群之间可空行分段，切勿把所有字段挤在同一行）\n【状态栏介绍】\n（这里写发给跑团AI的该栏位演算规则说明，并务必叮嘱AI：上方字段格式中的具体描述/数值仅作排版样式参考，必须结合当前角色设定与实时剧情动态创作替换，严禁照搬格式参考里的示例词）`,
    localHint ? `玩家想法：${localHint}` : "",
    globalHint
  ].filter(Boolean).join("；");

  const origLabel = btnEl ? btnEl.innerHTML : "润色";
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.innerHTML = "润色中...";
  }
  try {
    const curCombined = `【字段格式】\n${fieldsInput ? fieldsInput.value : (mod.fields || "")}\n\n【状态栏介绍】\n${descInput ? descInput.value : (mod.desc || "")}`;
    const polished = await callAiPolishApi(curCombined, "suffix", proj.name || "跑团游戏", instruction, selectedModel);
    const rawStr = String(polished || "").replace(/\r\n/g, "\n").trim();

    let newFields = "";
    let newDesc = "";
    const secMatch = rawStr.match(/(?:【?(?:1[\.、]?\s*)?(?:格式|字段格式|显示格式)】?[:：]?)\s*([\s\S]*?)\s*(?:【?(?:2[\.、]?\s*)?(?:介绍|状态栏介绍|规则|AI规则)】?[:：]?)\s*([\s\S]*)$/i);
    if (secMatch) {
      newFields = segmentUiModuleFields(secMatch[1].trim(), mod.type || "");
      newDesc = secMatch[2].trim();
    } else {
      const lines = rawStr.split("\n").map((l) => l.trim()).filter(Boolean);
      if (lines.length === 1) {
        newDesc = lines[0];
      } else if (lines.length > 1) {
        newFields = segmentUiModuleFields(lines.slice(0, -1).join("\n"), mod.type || "");
        newDesc = lines[lines.length - 1];
      }
    }

    if (newFields) {
      mod.fields = newFields;
      if (fieldsInput) {
        fieldsInput.value = newFields;
        delete fieldsInput._origRoVal;
        delete fieldsInput._lastEnRoVal;
        fieldsInput.style.height = "auto";
        fieldsInput.style.height = Math.min(260, Math.max(46, fieldsInput.scrollHeight)) + "px";
      }
    }
    if (newDesc) {
      mod.desc = newDesc;
      if (descInput) {
        descInput.value = newDesc;
        delete descInput._origRoVal;
        delete descInput._lastEnRoVal;
        descInput.style.height = "auto";
        descInput.style.height = Math.min(220, Math.max(42, descInput.scrollHeight)) + "px";
      }
    }
    if (typeof window.syncUiModulesToPromptBox === "function") {
      window.syncUiModulesToPromptBox();
    }
    await window.saveStudioProjectConfig(false);
    showToast(`已润色「${mod.key}」`);
  } catch (err) {
    showToast("润色失败: " + err.message);
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.innerHTML = origLabel;
    }
  }
};

window.openModuleQuickEditor = function (modIdentifier) {
  window._studioFuncBarSubmenuOpen = true;
  const pane = document.getElementById("studioWorkbenchPane");
  if ((!pane || pane.style.display === "none") && typeof window.toggleStudioWorkbench === "function") {
    window.toggleStudioWorkbench(true);
  } else {
    renderStudioWorkbench();
  }
  setTimeout(() => {
    const funcBarDetails = document.getElementById("studioFuncBarSubmenu");
    if (funcBarDetails) funcBarDetails.open = true;
    const section = document.getElementById("studioUiModulesSection");
    if (!section) return;
    let targetCard = null;
    if (modIdentifier) {
      const cards = Array.from(section.querySelectorAll(".st-ui-mod-card"));
      targetCard = cards.find((c) => {
        const id = c.dataset.modId || "";
        const type = c.dataset.modType || "";
        const keyVal = c.querySelector(".st-uimod-key")?.value || "";
        return id === modIdentifier || type === modIdentifier || keyVal === modIdentifier || keyVal.includes(modIdentifier);
      });
    }
    const scrollTarget = targetCard || section;
    try {
      scrollTarget.scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (e) {}
    if (targetCard) {
      targetCard.style.boxShadow = "0 0 0 2px var(--tc-f59e0b, #f59e0b), 0 8px 24px var(--tc-rgba-245-158-11-0-28, rgba(245,158,11,0.28))";
      const inp = targetCard.querySelector(".st-uimod-fields");
      if (inp) inp.focus();
      setTimeout(() => {
        targetCard.style.boxShadow = "";
      }, 2200);
    }
  }, 80);
};

window.addStudioWorldbookEntry = function () {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  if (!Array.isArray(proj.world_book)) proj.world_book = [];
  proj.world_book.push({
    id: `wb_${Date.now().toString(36)}`,
    name: `词条 #${proj.world_book.length + 1}`,
    keys: [],
    match_type: "OR",
    value_region: "System",
    enabled: true,
    content: ""
  });
  renderStudioWorkbench();
};

window.removeStudioWorldbookEntry = async function (idx) {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj || !Array.isArray(proj.world_book)) return;
  proj.world_book.splice(idx, 1);
  renderStudioWorkbench();
  await window.saveStudioProjectConfig(false);
};

window.exportStudioWorldbook = function () {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  const blob = new Blob([JSON.stringify({ entries: proj.world_book || [] }, null, 2)], { type: "application/json" });
  const objUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objUrl;
  a.download = `${proj.name || "worldbook"}_worldbook.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(objUrl), 5000);
};

window.importStudioWorldbookFile = function (event) {
  const file = event?.target?.files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = async (ev) => {
    try {
      collectCurrentTabFormState();
      const raw = JSON.parse(ev.target.result);
      const proj = getActiveProjectObj();
      if (!proj) return;
      // 先将当前面板未保存表单状态同步到后端，再调用服务端 SillyTavern 完整规范导入器，确保 constant / depth / secondary_keys / sort 等字段零丢失
      await window.saveStudioProjectConfig(false);
      const res = await fetch(`/api/projects/${encodeURIComponent(proj.id)}/worldbook/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(raw)
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      await loadProjects();
      renderStudioWorkbench();
      showToast(`已导入 ${data.imported ?? 0} 条词条`);
    } catch (err) {
      showToast("导入失败: " + err.message);
    }
  };
  reader.readAsText(file);
  try { event.target.value = ""; } catch (e) {}
};

window.addStudioRegexRule = function () {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  if (!Array.isArray(proj.regex_replaces)) proj.regex_replaces = [];
  proj.regex_replaces.push({
    id: `rx_${Date.now().toString(36)}`,
    name: `规则 #${proj.regex_replaces.length + 1}`,
    pattern: "",
    replacement: "",
    scope: "both",
    enabled: true
  });
  renderStudioWorkbench();
};

window.removeStudioRegexRule = async function (idx) {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj || !Array.isArray(proj.regex_replaces)) return;
  proj.regex_replaces.splice(idx, 1);
  renderStudioWorkbench();
  await window.saveStudioProjectConfig(false);
};

window.addStudioCgEntry = function () {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  if (!Array.isArray(proj.cg_book)) proj.cg_book = [];
  proj.cg_book.push({ id: `cg_${Date.now().toString(36)}`, name: "", keys: [], url: "", enabled: true });
  renderStudioWorkbench();
};

window.removeStudioCgEntry = async function (idx) {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj || !Array.isArray(proj.cg_book)) return;
  proj.cg_book.splice(idx, 1);
  renderStudioWorkbench();
  await window.saveStudioProjectConfig(false);
};

window.addStudioMemoryPalaceItem = function () {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  if (!Array.isArray(proj.memory_palace)) proj.memory_palace = [];
  proj.memory_palace.push({ id: `mp_${Date.now().toString(36)}`, title: "", content: "" });
  renderStudioWorkbench();
};

window.removeStudioMemoryPalaceItem = async function (idx) {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj || !Array.isArray(proj.memory_palace)) return;
  proj.memory_palace.splice(idx, 1);
  renderStudioWorkbench();
  await window.saveStudioProjectConfig(false);
};

window.addStudioPromptVariable = function () {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  if (!Array.isArray(proj.prompt_variables)) proj.prompt_variables = [];
  proj.prompt_variables.push({ name: `var_${proj.prompt_variables.length + 1}`, label: "", default: "" });
  renderStudioWorkbench();
};

window.removeStudioPromptVariable = async function (idx) {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj || !Array.isArray(proj.prompt_variables)) return;
  proj.prompt_variables.splice(idx, 1);
  renderStudioWorkbench();
  await window.saveStudioProjectConfig(false);
};

window.addStudioOpeningGreeting = function () {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;
  if (!Array.isArray(proj.opening_greetings)) proj.opening_greetings = [];
  proj.opening_greetings.push({
    id: `og_${Date.now().toString(36)}`,
    title: `开场白 ${proj.opening_greetings.length + 1}`,
    content: ""
  });
  renderStudioWorkbench();
  requestAnimationFrame(() => {
    const inputs = document.querySelectorAll("#stOpeningGreetingsList .st-og-content");
    const lastInp = inputs[inputs.length - 1];
    if (lastInp) {
      lastInp.focus({ preventScroll: true });
    }
  });
};

window.removeStudioOpeningGreeting = async function (idx) {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj || !Array.isArray(proj.opening_greetings)) return;
  proj.opening_greetings.splice(idx, 1);
  renderStudioWorkbench();
  await window.saveStudioProjectConfig(false);
  showToast("已删除");
};

window.polishStudioOpeningGreeting = async function (idx, btnEl, hintInputId = "") {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj || !Array.isArray(proj.opening_greetings) || !proj.opening_greetings[idx]) return;
  const item = proj.opening_greetings[idx];
  const selectedModel = document.getElementById("studioAiModelSelect")?.value || "";
  const localHint = hintInputId
    ? (document.getElementById(hintInputId)?.value.trim() || "")
    : (document.getElementById(`stHint_og_${idx}`)?.value.trim() || "");
  const globalHint = document.getElementById("studioGlobalPolishInstruction")?.value.trim() || "";
  const origLabel = btnEl ? btnEl.innerHTML : (window.tStr ? window.tStr("润色") : "润色");
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.innerHTML = window.tStr ? window.tStr("润色中...") : "润色中...";
  }
  try {
    const parts = [];
    if (item.title) parts.push(`开场白路线/主题：${item.title}`);
    if (proj.description) parts.push(`游戏简介参考：${proj.description}`);
    if (localHint) parts.push(localHint);
    if (globalHint) parts.push(globalHint);
    const hint = parts.join("；");
    const polished = await callAiPolishApi(item.content || "", "opening_greeting", proj.name || "跑团游戏", hint, selectedModel);
    item.content = polished;
    const contentInputs = document.querySelectorAll("#stOpeningGreetingsList .st-og-content");
    if (contentInputs[idx]) {
      contentInputs[idx].value = polished;
    }
    await window.saveStudioProjectConfig(false);
    showToast("已润色");
  } catch (err) {
    showToast("润色失败: " + err.message);
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.innerHTML = origLabel;
    }
  }
};

window.openStudioToOpeningGreetings = function () {
  if (typeof window.toggleStudioWorkbench === "function") {
    window.toggleStudioWorkbench(true);
  }
  const proj = getActiveProjectObj();
  if (proj && (!Array.isArray(proj.opening_greetings) || proj.opening_greetings.length === 0)) {
    window.addStudioOpeningGreeting();
  } else {
    setTimeout(() => {
      const sec = document.getElementById("studioOpeningGreetingsSection");
      if (sec) sec.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 60);
  }
};

window.saveStudioProjectConfig = async function (showSuccessToast = true) {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;

  const cleanProto = String(proj.system_protocol_prompt ?? "").trim();
  proj.system_protocol_prompt = cleanProto;

  const payload = {
    ...proj,
    system_protocol_prompt: cleanProto,
    opening_greetings: Array.isArray(proj.opening_greetings)
      ? proj.opening_greetings.filter((x) => x && ((x.title || "").trim() || (x.content || "").trim()))
      : []
  };

  try {
    const res = await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const savedData = await res.json();
    await loadProjects();
    if (!showSuccessToast && Array.isArray(proj.opening_greetings) && projectsMap && projectsMap[proj.id]) {
      const hasBlankEditing = proj.opening_greetings.some((x) => !((x.title || "").trim() || (x.content || "").trim()));
      if (hasBlankEditing) {
        projectsMap[proj.id].opening_greetings = proj.opening_greetings;
      }
    }
    applyProjectAppearance(getActiveProjectObj());
    if (typeof window.updateContextProgressUI === "function") {
      window.updateContextProgressUI();
    }
    if (typeof window.renderWelcomeBox === "function") {
      window.renderWelcomeBox();
    }
    renderChatVariablesBar();
    const pane = document.getElementById("studioWorkbenchPane");
    if (pane && pane.style.display !== "none" && showSuccessToast) {
      renderStudioWorkbench();
    }
    if (showSuccessToast) {
      showToast("已保存");
    }
  } catch (err) {
    showToast("保存失败: " + err.message);
  }
};

function renderChatVariablesBar() {
  const bar = document.getElementById("chatVariablesBar");
  if (!bar) return;
  const proj = getActiveProjectObj();
  const vars = Array.isArray(proj?.prompt_variables) ? proj.prompt_variables.filter((v) => v && v.name) : [];
  if (vars.length === 0) {
    bar.style.display = "none";
    bar.innerHTML = "";
    return;
  }
  bar.style.display = "flex";
  bar.innerHTML = vars.map((v) => {
    const curVal = (sessionVariableValues && sessionVariableValues[v.name] !== undefined)
      ? sessionVariableValues[v.name]
      : (v.default ?? v.value ?? "");
    return `
      <div class="chat-var-pill" style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:999px;background:var(--tc-rgba-99-102-241-0-12, rgba(99,102,241,0.12));border:1px solid var(--tc-rgba-99-102-241-0-3, rgba(99,102,241,0.3));font-size:11.5px;">
        <span style="color:var(--text-muted);font-weight:600;">${escapeHtml(v.label || v.name)}:</span>
        <input type="text" value="${escapeHtml(curVal)}" style="background:transparent;border:none;color:var(--text-main);font-size:11.5px;width:76px;outline:none;font-weight:700;" onchange="window.updateSessionPromptVar('${escapeJsAttr(v.name)}', this.value)" />
      </div>
    `;
  }).join("");
}
window.renderChatVariablesBar = renderChatVariablesBar;
window.updateSessionPromptVar = function (name, val) {
  if (typeof sessionVariableValues === "object" && sessionVariableValues) {
    sessionVariableValues[name] = val;
    if (typeof currentChatId === "string" && currentChatId) {
      fetch(`/api/chats/${encodeURIComponent(currentChatId)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ inputs: { ...sessionVariableValues } })
      }).catch(() => {});
    }
  }
};

// =========================================================================
// 5. AI 润色与 模板工坊 弹窗
// =========================================================================
async function callAiPolishApi(text, fieldType, projectName, instruction = "", modelOverride = "") {
  const model =
    modelOverride ||
    document.getElementById("advAiModelSelect")?.value ||
    document.getElementById("studioAiModelSelect")?.value ||
    (typeof window.getPreferredAiAssistModel === "function" ? window.getPreferredAiAssistModel() : "") ||
    (typeof headerModelSelect !== "undefined" && headerModelSelect?.value) ||
    "";
  const res = await fetch("/api/ai/polish", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: text || "",
      field_type: fieldType || "system_prompt",
      project_name: projectName || "跑团游戏",
      instruction: instruction || "",
      model
    })
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "润色失败");
  return data.polished_text || text;
}

window.polishStudioField = async function (inputId, fieldType, btnEl, hintInputId = "") {
  const el = document.getElementById(inputId);
  const proj = getActiveProjectObj();
  if (!el || !proj) return;
  const selectedModel = document.getElementById("studioAiModelSelect")?.value || "";
  const localHintInput = hintInputId
    ? document.getElementById(hintInputId)
    : document.getElementById(`stHint_${fieldType}`);
  const localHint = localHintInput?.value.trim() || "";
  const globalHintInput = document.getElementById("studioGlobalPolishInstruction");
  const globalHint = globalHintInput?.value.trim() || "";
  const instruction = [localHint, globalHint].filter(Boolean).join("；");
  if (inputId === "stProjSystem" && !instruction && !el.value.trim()) {
    if (localHintInput) localHintInput.focus();
    else if (globalHintInput) globalHintInput.focus();
    showToast("请先输入想法");
    return;
  }
  const origLabel = btnEl ? btnEl.innerHTML : (window.tStr ? window.tStr("润色") : "润色");
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.innerHTML = window.tStr ? window.tStr("润色中...") : "润色中...";
  }
  try {
    const polished = await callAiPolishApi(el.value, fieldType, proj.name || "跑团游戏", instruction, selectedModel);
    el.value = polished;
    if (inputId === "stProjSystem" && typeof window.updatePromptCharCount === "function") {
      window.updatePromptCharCount(el);
    }
    await window.saveStudioProjectConfig(false);
    showToast("已润色");
  } catch (err) {
    showToast("润色失败: " + err.message);
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.innerHTML = origLabel;
    }
  }
};

window.polishAllStudioFields = async function (btnEl) {
  collectCurrentTabFormState();
  const proj = getActiveProjectObj();
  if (!proj) return;

  const instruction = document.getElementById("studioGlobalPolishInstruction")?.value.trim() || "";
  const selectedModel = document.getElementById("studioAiModelSelect")?.value || "";
  const isEn = window.currentAppLang === "en";

  if (!Array.isArray(proj.opening_greetings) || proj.opening_greetings.length === 0) {
    proj.opening_greetings = [
      {
        id: `og_${Date.now().toString(36)}`,
        title: "开场白 1",
        content: ""
      }
    ];
    renderStudioWorkbench();
    const instrEl = document.getElementById("studioGlobalPolishInstruction");
    if (instrEl && instruction) instrEl.value = instruction;
    btnEl = document.getElementById("btnPolishAllStudio") || btnEl;
  }

  const origLabel = btnEl ? btnEl.innerHTML : (isEn ? "Polish" : "润色");
  if (btnEl) {
    btnEl.disabled = true;
  }

  const ogCount = Array.isArray(proj.opening_greetings) ? proj.opening_greetings.length : 0;
  const totalSteps = 4 + ogCount;
  let curStep = 0;
  const setProgress = (stepLabel) => {
    curStep += 1;
    if (btnEl) {
      btnEl.innerHTML = isEn
        ? `Polishing (${curStep}/${totalSteps})...`
        : `润色中 (${curStep}/${totalSteps}) ${stepLabel}...`;
    }
  };

  try {
    const pName = proj.name || "跑团游戏";

    setProgress("简介");
    const descEl = document.getElementById("stProjDesc");
    const descHint = [document.getElementById("stHint_description")?.value.trim() || "", instruction].filter(Boolean).join("；");
    const newDesc = await callAiPolishApi(
      descEl ? descEl.value : (proj.description || ""),
      "description",
      pName,
      descHint,
      selectedModel
    );
    proj.description = newDesc;
    if (descEl) descEl.value = newDesc;

    const baseContextHint = [
      proj.description ? `游戏简介参考：${proj.description}` : "",
      instruction
    ].filter(Boolean).join("；");

    if (Array.isArray(proj.opening_greetings)) {
      for (let i = 0; i < proj.opening_greetings.length; i++) {
        setProgress(`开场白 #${i + 1}`);
        const og = proj.opening_greetings[i];
        const titleInputs = document.querySelectorAll("#stOpeningGreetingsList .st-og-title");
        const contentInputs = document.querySelectorAll("#stOpeningGreetingsList .st-og-content");
        const curTitle = titleInputs[i] ? titleInputs[i].value.trim() : (og.title || `开场白 ${i + 1}`);
        const curContent = contentInputs[i] ? contentInputs[i].value : (og.content || "");
        const localOgHint = document.getElementById(`stHint_og_${i}`)?.value.trim() || "";
        const ogHint = [curTitle ? `开场白路线/主题：${curTitle}` : "", localOgHint, baseContextHint].filter(Boolean).join("；");
        const newOgContent = await callAiPolishApi(curContent, "opening_greeting", pName, ogHint, selectedModel);
        og.content = newOgContent;
        if (contentInputs[i]) contentInputs[i].value = newOgContent;
      }
    }

    setProgress("前置");
    const preEl = document.getElementById("stProjPrefix");
    const preHint = [document.getElementById("stHint_prefix")?.value.trim() || "", baseContextHint].filter(Boolean).join("；");
    const newPre = await callAiPolishApi(
      preEl ? preEl.value : (proj.prefix || ""),
      "prefix",
      pName,
      preHint,
      selectedModel
    );
    proj.prefix = newPre;
    if (preEl) preEl.value = newPre;

    setProgress("提示词");
    const sysEl = document.getElementById("stProjSystem");
    const sysHint = [document.getElementById("stHint_system_prompt")?.value.trim() || "", baseContextHint].filter(Boolean).join("；");
    const newSys = await callAiPolishApi(
      sysEl ? sysEl.value : (proj.system_prompt || ""),
      "system_prompt",
      pName,
      sysHint,
      selectedModel
    );
    proj.system_prompt = newSys;
    if (sysEl) {
      sysEl.value = newSys;
      if (typeof window.updatePromptCharCount === "function") {
        window.updatePromptCharCount(sysEl);
      }
    }

    setProgress("后置");
    const sufEl = document.getElementById("stProjSuffix");
    const sufHint = [document.getElementById("stHint_suffix")?.value.trim() || "", baseContextHint].filter(Boolean).join("；");
    const newSuf = await callAiPolishApi(
      sufEl ? sufEl.value : (proj.suffix || ""),
      "suffix",
      pName,
      sufHint,
      selectedModel
    );
    proj.suffix = newSuf;
    if (sufEl) sufEl.value = newSuf;

    await window.saveStudioProjectConfig(false);
    showToast("已润色全部");
  } catch (err) {
    showToast("润色失败: " + err.message);
  } finally {
    const finalBtn = document.getElementById("btnPolishAllStudio") || btnEl;
    if (finalBtn) {
      finalBtn.disabled = false;
      finalBtn.innerHTML = origLabel;
    }
  }
};

window.openExploreModal = async function () {
  const modal = document.getElementById("exploreModal");
  if (!modal) return;
  modal.style.display = "flex";
  const titleEl = document.getElementById("exploreModalTitle");
  if (titleEl) titleEl.textContent = "游戏卡库";
  const body = document.getElementById("exploreModalBody");
  if (body) body.innerHTML = `<div style="padding:24px;text-align:center;color:var(--text-muted);">加载中...</div>`;
  if (typeof window.translateSubtree === "function") window.translateSubtree(modal);

  try {
    const res = await fetch("/api/explore");
    const data = await res.json();
    exploreAppsCache = [];
    const backendUserProjs = Array.isArray(data.user_projects) ? data.user_projects : [];
    const localProjs = typeof projectsMap === "object" && projectsMap ? Object.values(projectsMap) : [];
    const mergedMap = new Map();
    backendUserProjs.forEach((p) => {
      if (p && p.id) {
        mergedMap.set(p.id, { ...p, _is_user_project: true });
      }
    });
    localProjs.forEach((p) => {
      if (p && p.id && !mergedMap.has(p.id)) {
        mergedMap.set(p.id, { ...p, _is_user_project: true });
      }
    });
    exploreUserProjectsCache = Array.from(mergedMap.values());
    currentExploreCategory = "ALL";
    renderExploreModalContent();
  } catch (err) {
    if (body) body.innerHTML = `<div style="padding:24px;color:var(--tc-f87171, #f87171);">加载失败: ${escapeHtml(err.message)}</div>`;
    if (typeof window.translateSubtree === "function" && body) window.translateSubtree(body);
  }
};

function getAllAdvancedCandidateCards() {
  const userCards = exploreUserProjectsCache.map((p) => ({
    ...p,
    _sourceType: "user",
    _badgeText: ""
  }));
  return userCards;
}

function renderExploreModalContent() {
  const body = document.getElementById("exploreModalBody");
  if (!body) return;
  const titleEl = document.getElementById("exploreModalTitle");
  if (titleEl) titleEl.textContent = "游戏卡库";

  const allCards = getAllAdvancedCandidateCards();
  const filtered = allCards;

  body.innerHTML = `
    <div id="gameCardHubDropZone"
         ondragover="event.preventDefault(); this.style.borderColor='var(--primary, #d4a65a)';"
         ondragleave="this.style.borderColor='rgba(212,166,90,0.32)';"
         ondrop="event.preventDefault(); this.style.borderColor='rgba(212,166,90,0.32)'; window.importGameCardFileList && window.importGameCardFileList(event.dataTransfer?.files);"
         style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:12px;padding:12px 15px;border-radius:10px;background:linear-gradient(135deg,rgba(212,166,90,0.12),rgba(255,255,255,0.02));border:1px solid rgba(212,166,90,0.32);transition:border-color 0.16s ease;">
      <div style="display:flex;flex-direction:column;gap:2px;">
        <span style="font-size:13.5px;font-weight:700;color:var(--text-main);">我的游戏卡 (${allCards.length})</span>
        <span style="font-size:11.5px;color:var(--text-muted);">支持导入 / 导出酒馆与本工作台 PNG / JSON 游戏卡（也可直接将文件拖入此处）</span>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
        <button type="button" class="btn btn-sm btn-primary" style="padding:6px 14px;font-size:12.5px;font-weight:700;border-radius:8px;" onclick="document.getElementById('globalGameCardImportInput')?.click()">
          导入游戏卡 (.png / .json)
        </button>
        <button type="button" class="btn btn-sm btn-secondary" onclick="document.getElementById('exploreModal').style.display='none'; window.openGuidedGameCardModal && window.openGuidedGameCardModal(null)">
          简易创作
        </button>
        <button type="button" class="btn btn-sm btn-secondary" onclick="window.startAdvancedForkEditor(null)">
          高级创作
        </button>
      </div>
    </div>

    <div class="explore-grid">
      ${filtered.map((app) => {
        const descPreview = app.description || (app.system_prompt ? app.system_prompt.slice(0, 90) : "暂无简介");
        const isCurrent = app.id === currentProjectId;
        const isBuiltin = ["proj_fast_trpg", "proj_default", "proj_free_chat"].includes(app.id);
        const tier = getProjectCardTier(app);
        const tierTagHtml = isBuiltin
          ? `<span class="wb-badge" style="font-size:10.5px;">系统模式</span>`
          : (tier === "simple"
              ? `<span class="proj-tier-tag tier-simple">简易卡</span>`
              : `<span class="proj-tier-tag tier-advanced">高级卡</span>`);

        let actionBtnsHtml = "";
        if (isBuiltin) {
          actionBtnsHtml = `
            <button type="button" class="btn btn-xs btn-primary" style="flex:1;" onclick="window.startAdvancedForkEditor('${escapeJsAttr(app.id)}')">基于模板建高级卡</button>
          `;
        } else if (tier === "simple") {
          actionBtnsHtml = `
            <button type="button" class="btn btn-xs btn-secondary" style="flex:1;" onclick="document.getElementById('exploreModal').style.display='none'; window.openGuidedGameCardModal && window.openGuidedGameCardModal('${escapeJsAttr(app.id)}')">编辑简易卡</button>
            <button type="button" class="btn btn-xs btn-primary" onclick="window.upgradeProjectToAdvanced('${escapeJsAttr(app.id)}', true)" title="将此简易卡升级为高级卡并进入三栏工坊">⬆ 升级高级</button>
            <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.startAdvancedForkEditor('${escapeJsAttr(app.id)}')" title="以此卡克隆新建一张高级卡">克隆</button>
          `;
        } else {
          actionBtnsHtml = `
            <button type="button" class="btn btn-xs btn-primary" style="flex:1;" onclick="window.startAdvancedEditProject('${escapeJsAttr(app.id)}')">高级编辑</button>
            <button type="button" class="btn btn-xs btn-secondary" onclick="window.startAdvancedForkEditor('${escapeJsAttr(app.id)}')" title="以此卡克隆新建一张高级卡">克隆</button>
          `;
        }

        return `
        <div class="explore-card" style="${isCurrent ? "border-color:rgba(212,166,90,0.55);" : ""}">
          <div class="explore-card-top">
            <div class="explore-icon">${getIconHtml(app.icon || app.avatar || "", 36)}</div>
            <div style="flex:1;min-width:0;">
              <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                <div class="explore-title">${escapeHtml(app.name || "未命名剧本")}</div>
                ${tierTagHtml}
                ${isCurrent ? `<span class="wb-badge" style="color:var(--tc-34d399, #34d399);border-color:var(--tc-rgba-16-185-129-0-4, rgba(16,185,129,0.4));">当前</span>` : ""}
              </div>
            </div>
          </div>
          <div class="explore-desc">${escapeHtml(descPreview)}</div>
          ${(app.tags || []).length > 0 ? `
            <div class="explore-tags">
              ${(app.tags || []).map((t) => `<span class="explore-tag">#${escapeHtml(t)}</span>`).join("")}
            </div>
          ` : ""}
          <div style="display:flex;gap:6px;margin-top:auto;padding-top:6px;flex-wrap:wrap;">
            ${actionBtnsHtml}
            <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.exportProjectGameCard && window.exportProjectGameCard('${escapeJsAttr(app.id)}', 'png')" title="导出可分享 PNG 游戏卡（兼容酒馆）">PNG卡</button>
            <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.exportProjectGameCard && window.exportProjectGameCard('${escapeJsAttr(app.id)}', 'json')" title="导出 JSON 游戏卡">JSON</button>
          </div>
        </div>
      `;
      }).join("")}
    </div>
  `;
  const modal = document.getElementById("exploreModal");
  if (typeof window.translateSubtree === "function") {
    window.translateSubtree(modal || body);
  }
}

window.filterExploreCategory = function (cat) {
  currentExploreCategory = cat;
  renderExploreModalContent();
};

window.quickForkProjectDirect = async function (sourceId) {
  try {
    const allCards = getAllAdvancedCandidateCards();
    const src = allCards.find((x) => x.id === sourceId);
    const res = await fetch("/api/projects/fork", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_id: sourceId,
        project: src || null,
        new_name: src ? `${src.name} (副本)` : "新剧本 (副本)"
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "复制失败");

    const modal = document.getElementById("exploreModal");
    if (modal) modal.style.display = "none";

    currentProjectId = data.project.id;
    await loadProjects();
    currentChatId = data.chat_id || null;
    await loadChats();
    if (currentChatId) await switchChat(currentChatId);
    window.toggleStudioWorkbench(true);
    showToast(`已复制：${data.project.name}`);
  } catch (err) {
    showToast("复制失败: " + err.message);
  }
};

let currentAdvancedCreatorTab = "basic";
let advWbSearchQuery = "";
let advShowDetailedPreview = false;

window.openAdvancedCreatorForProject = async function (projectId) {
  const modal = document.getElementById("exploreModal");
  if (modal) modal.style.display = "flex";
  const pMap = typeof projectsMap !== "undefined" ? projectsMap : window.projectsMap;
  const found = (pMap && pMap[projectId]) || exploreUserProjectsCache.find((x) => x.id === projectId);
  if (found) {
    advancedDraftProject = JSON.parse(JSON.stringify(normalizeProjectClient(found)));
    currentAdvancedCreatorTab = "basic";
    advWbSearchQuery = "";
    renderAdvancedProjectEditor();
  } else if (typeof window.openExploreModal === "function") {
    await window.openExploreModal();
    window.startAdvancedEditProject(projectId);
  }
};

window.startAdvancedEditProject = function (sourceId) {
  const pMap = typeof projectsMap !== "undefined" ? projectsMap : window.projectsMap;
  const allCards = getAllAdvancedCandidateCards();
  const src = (sourceId && pMap && pMap[sourceId]) || (sourceId ? allCards.find((x) => x.id === sourceId) : null);
  if (!src) {
    window.startAdvancedForkEditor(null);
    return;
  }
  const cloned = JSON.parse(JSON.stringify(normalizeProjectClient(src)));
  if (["proj_fast_trpg", "proj_default", "proj_free_chat"].includes(cloned.id)) {
    delete cloned.id;
    cloned.name = `${src.name || "未命名剧本"} (新)`;
  }
  cloned.card_tier = "advanced";
  cloned.simple_mode = false;
  if (["极速跑团", "简单跑团"].includes(String(cloned.category || "").trim())) {
    cloned.category = "";
  }
  advancedDraftProject = cloned;
  currentAdvancedCreatorTab = "basic";
  advWbSearchQuery = "";
  renderAdvancedProjectEditor();
};

window.startAdvancedForkEditor = function (sourceId) {
  const allCards = getAllAdvancedCandidateCards();
  const src = sourceId ? allCards.find((x) => x.id === sourceId) : null;
  if (src) {
    const cloned = JSON.parse(JSON.stringify(normalizeProjectClient(src)));
    delete cloned.id;
    cloned._sourceName = src.name || "原剧本";
    cloned.name = `${src.name || "未命名剧本"} (新)`;
    cloned.card_tier = "advanced";
    cloned.simple_mode = false;
    if (["极速跑团", "简单跑团"].includes(String(cloned.category || "").trim())) {
      cloned.category = "";
    }
    advancedDraftProject = cloned;
  } else {
    const customCount = Object.values(projectsMap || {}).filter(
      (p) => p && !["proj_fast_trpg", "proj_default", "proj_free_chat"].includes(p.id)
    ).length;
    advancedDraftProject = normalizeProjectClient({
      name: `新企划 #${customCount + 1}`,
      card_tier: "advanced",
      simple_mode: false,
      icon: "",
      description: "",
      detailed_description: "",
      custom_css: "",
      quick_replies: [],
      tags: [],
      opening_greetings: [],
      opening_statement: "",
      prefix: "",
      system_prompt: "",
      suffix: "",
      system_protocol_prompt: "",
      ui_modules: [],
      status_panel_enabled: false,
      world_book: [],
      regex_replaces: [],
      cg_book: [],
      appearance: { bg_image: "", bg_mobile: "", custom_css: "" },
      _sourceName: "空白 0 提示词企划"
    });
  }
  currentAdvancedCreatorTab = "basic";
  advWbSearchQuery = "";
  renderAdvancedProjectEditor();
};

window.switchAdvancedCreatorTab = function (tabKey) {
  syncAdvancedDraftFromDom();
  currentAdvancedCreatorTab = ["basic", "worldbook", "other"].includes(tabKey) ? tabKey : "basic";
  renderAdvancedProjectEditor();
};

function syncAdvancedDraftFromDom() {
  if (!advancedDraftProject) return;
  const d = advancedDraftProject;
  const getElVal = (el) => {
    if (!el) return "";
    if (!el.value || !el.value.trim()) return "";
    if (el._origRoVal !== undefined && (el.value === el._lastEnRoVal || el.value.trim() === el._lastEnRoVal)) {
      return el._origRoVal;
    }
    return el.value;
  };
  const gVal = (id) => {
    const el = document.getElementById(id);
    if (!el) return undefined;
    return getElVal(el);
  };

  const statusEl = document.getElementById("advStatusPanelEnabled");
  if (statusEl) d.status_panel_enabled = statusEl.checked;

  if (gVal("advProjIcon") !== undefined) {
    d.icon = gVal("advProjIcon").trim() || "";
    d.avatar = d.icon;
  }
  if (gVal("advProjName") !== undefined) d.name = gVal("advProjName").trim() || "未命名剧本";
  if (gVal("advProjDesc") !== undefined) d.description = gVal("advProjDesc").trim();
  if (gVal("advProjDetailedDesc") !== undefined) {
    d.detailed_description = gVal("advProjDetailedDesc").trim();
  }
  if (gVal("advProjTags") !== undefined) {
    d.tags = gVal("advProjTags").split(/[,，]/).map((s) => s.trim()).filter(Boolean);
  }
  if (gVal("advBgImageInput") !== undefined) {
    if (!d.appearance) d.appearance = {};
    d.appearance.bg_image = gVal("advBgImageInput").trim();
    d.bg_image = d.appearance.bg_image;
  }
  if (gVal("advBgMobileInput") !== undefined) {
    if (!d.appearance) d.appearance = {};
    d.appearance.bg_mobile = gVal("advBgMobileInput").trim();
  }
  const cssEl = document.getElementById("advCustomCssInput");
  if (cssEl) {
    d.custom_css = cssEl.value || "";
    if (!d.appearance) d.appearance = {};
    d.appearance.custom_css = d.custom_css;
  }
  if (gVal("advProjPrefix") !== undefined) d.prefix = gVal("advProjPrefix");
  if (gVal("advProjSystem") !== undefined) d.system_prompt = gVal("advProjSystem");
  if (gVal("advProjSuffix") !== undefined) d.suffix = gVal("advProjSuffix");

  // 变量面板 / 状态栏骨架同步
  const advUiModListEl = document.getElementById("advUiModulesList");
  if (advUiModListEl) {
    d.ui_modules = Array.from(advUiModListEl.querySelectorAll(".adv-uimod-row")).map((row, idx) => {
      const mType = row.querySelector(".adv-uimod-type")?.value || "progress_stats";
      const mKey = getElVal(row.querySelector(".adv-uimod-key")).trim() || `模块 #${idx + 1}`;
      const rawFields = getElVal(row.querySelector(".adv-uimod-fields")).trim();
      const rawDesc = getElVal(row.querySelector(".adv-uimod-desc")).trim();
      return fillDefaultUiModuleDesc({
        id: row.dataset.modId || `mod_${idx + 1}`,
        type: mType,
        key: mKey,
        enabled: !!row.querySelector(".adv-uimod-enabled")?.checked,
        fields: segmentUiModuleFields(rawFields, mType),
        desc: rawDesc,
        v: 2
      });
    });
  }

  // 世界书默认样式 & 词条同步（注意搜索过滤开启时仅更新可见词条，未显示词条原样保留！）
  const wbDefRegionEl = document.getElementById("advWbDefKeyRegion");
  const wbDefMatchEl = document.getElementById("advWbDefMatch");
  const wbDefValRegEl = document.getElementById("advWbDefValRegion");
  if (wbDefRegionEl || wbDefMatchEl || wbDefValRegEl) {
    if (!d.worldbook_defaults) d.worldbook_defaults = {};
    if (wbDefRegionEl) d.worldbook_defaults.key_region = Number(wbDefRegionEl.value) || 6;
    if (wbDefMatchEl) d.worldbook_defaults.match_type = wbDefMatchEl.value || "OR";
    if (wbDefValRegEl) d.worldbook_defaults.value_region = wbDefValRegEl.value || "System";
  }

  const advWbListEl = document.getElementById("advWorldbookList");
  if (advWbListEl) {
    if (!Array.isArray(d.world_book)) d.world_book = [];
    Array.from(advWbListEl.querySelectorAll(".adv-wb-item")).forEach((row) => {
      const origIdx = Number(row.dataset.wbIdx);
      if (Number.isNaN(origIdx) || !d.world_book[origIdx]) return;
      const prev = d.world_book[origIdx];
      const mVal = row.querySelector(".adv-wb-match")?.value || "OR";
      const isConst = mVal === "CONSTANT";
      const matchType = isConst ? "OR" : mVal;
      const rawKeys = getElVal(row.querySelector(".adv-wb-keys")).trim();
      const parsedKeys = (matchType === "Regex" || /^\/.+\/[gimsuy]*$/.test(rawKeys))
        ? (rawKeys ? [rawKeys] : [])
        : rawKeys.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
      const contentStr = getElVal(row.querySelector(".adv-wb-content")).trim();
      const enabled = !!row.querySelector(".adv-wb-enabled")?.checked;
      d.world_book[origIdx] = {
        ...prev,
        name: getElVal(row.querySelector(".adv-wb-name")).trim() || prev.name || `词条 #${origIdx + 1}`,
        keys: parsedKeys,
        constant: isConst,
        match_type: matchType,
        key_region: Number(row.querySelector(".adv-wb-keyregion")?.value) || 6,
        value_region: row.querySelector(".adv-wb-valregion")?.value || "System",
        content: contentStr,
        value: contentStr,
        enabled,
        enable: enabled
      };
    });
  }

  // 正则脚本同步
  const advRxListEl = document.getElementById("advRegexList");
  if (advRxListEl) {
    d.regex_replaces = Array.from(advRxListEl.querySelectorAll(".adv-rx-item")).map((row, idx) => {
      const pat = row.querySelector(".adv-rx-pattern")?.value ?? "";
      const rep = row.querySelector(".adv-rx-replacement")?.value ?? "";
      const enabled = !!row.querySelector(".adv-rx-enabled")?.checked;
      const onlyRender = !!row.querySelector(".adv-rx-renderonly")?.checked;
      const scope = row.querySelector(".adv-rx-scope")?.value || "assistant";
      return {
        id: row.dataset.rxId || `rx_${idx + 1}`,
        name: getElVal(row.querySelector(".adv-rx-name")).trim() || `正则 #${idx + 1}`,
        pattern: pat,
        regex: pat,
        find_regex: pat,
        replacement: rep,
        replace: rep,
        replace_str: rep,
        scope,
        target_scope: scope === "assistant" ? 1 : 3,
        is_only_render: onlyRender,
        enabled,
        enable: enabled
      };
    });
    d.regex_scripts = d.regex_replaces;
  }

  // CG 默认样式 & 列表同步
  const cgDefSrcEl = document.getElementById("advCgDefSource");
  const cgDefMatchEl = document.getElementById("advCgDefMatch");
  const cgDefDispEl = document.getElementById("advCgDefDisplay");
  if (cgDefSrcEl || cgDefMatchEl || cgDefDispEl) {
    if (!d.cg_defaults) d.cg_defaults = {};
    if (cgDefSrcEl) d.cg_defaults.trigger_source = cgDefSrcEl.value || "ai";
    if (cgDefMatchEl) d.cg_defaults.match_type = cgDefMatchEl.value || "OR";
    if (cgDefDispEl) d.cg_defaults.display_mode = cgDefDispEl.value || "chat";
  }

  const advCgListEl = document.getElementById("advCgList");
  if (advCgListEl) {
    d.cg_book = Array.from(advCgListEl.querySelectorAll(".adv-cg-item")).map((row, idx) => {
      const imgUrl = (row.querySelector(".adv-cg-url")?.value || row.dataset.imgUrl || "").trim();
      const keys = getElVal(row.querySelector(".adv-cg-keys")).split(/[,，]/).map((s) => s.trim()).filter(Boolean);
      return {
        id: row.dataset.cgId || `cg_${idx + 1}`,
        name: getElVal(row.querySelector(".adv-cg-name")).trim() || `特殊CG #${idx + 1}`,
        url: imgUrl,
        image_url: imgUrl,
        keys,
        trigger_source: row.querySelector(".adv-cg-source")?.value || "ai",
        match_type: row.querySelector(".adv-cg-match")?.value || "OR",
        display_mode: row.querySelector(".adv-cg-display")?.value || "chat",
        enabled: row.querySelector(".adv-cg-enabled") ? !!row.querySelector(".adv-cg-enabled").checked : true,
        enable: true
      };
    });
  }

  // 预设对话开场白同步
  const advOgListEl = document.getElementById("advOpeningGreetingsList");
  if (advOgListEl) {
    d.opening_greetings = Array.from(advOgListEl.querySelectorAll(".adv-opening-greeting-item")).map((item, idx) => {
      const titleEl = item.querySelector(".adv-og-title");
      const contentEl = item.querySelector(".adv-og-content");
      return {
        id: item.dataset.ogId || `og_${idx + 1}`,
        title: getElVal(titleEl).trim(),
        content: getElVal(contentEl).trim()
      };
    });
  }

  // 快捷回复指令同步
  const advQrListEl = document.getElementById("advQuickRepliesList");
  if (advQrListEl) {
    d.quick_replies = Array.from(advQrListEl.querySelectorAll(".adv-qr-item")).slice(0, 10).map((row, idx) => ({
      id: row.dataset.qrId || `qr_${idx + 1}`,
      label: getElVal(row.querySelector(".adv-qr-label")).trim(),
      command: getElVal(row.querySelector(".adv-qr-cmd")).trim(),
      content: getElVal(row.querySelector(".adv-qr-content")).trim(),
      auto_send: true
    })).filter((q) => q.label || q.command || q.content);
  }

  const { hasModelOverride } = getActiveModelParamOverrideInfo();
  const useGlobEl = document.getElementById("advUseGlobalParams");
  if (useGlobEl && !hasModelOverride) d.use_global_params = useGlobEl.checked;
  const autoSumEl = document.getElementById("advAutoSummarize");
  if (autoSumEl) d.auto_summarize = autoSumEl.checked;
  const ctxModeEl = document.getElementById("advContextMode");
  if (ctxModeEl && !hasModelOverride && !d.use_global_params) {
    if (!d.completion_params) d.completion_params = {};
    d.completion_params.context_mode = ctxModeEl.value === "tokens" ? "tokens" : "turns";
  }
}

window.addAdvOpeningGreeting = function () {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject) return;
  if (!Array.isArray(advancedDraftProject.opening_greetings)) advancedDraftProject.opening_greetings = [];
  advancedDraftProject.opening_greetings.push({
    id: `og_${Date.now().toString(36)}`,
    title: `开场白 ${advancedDraftProject.opening_greetings.length + 1}`,
    content: ""
  });
  renderAdvancedProjectEditor();
  requestAnimationFrame(() => {
    const inputs = document.querySelectorAll("#advOpeningGreetingsList .adv-og-content");
    const lastInp = inputs[inputs.length - 1];
    if (lastInp) lastInp.focus({ preventScroll: true });
  });
};

window.removeAdvOpeningGreeting = function (idx) {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject || !Array.isArray(advancedDraftProject.opening_greetings)) return;
  advancedDraftProject.opening_greetings.splice(idx, 1);
  renderAdvancedProjectEditor();
};

window.polishAdvOpeningGreeting = async function (idx, btnEl, hintInputId = "") {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject || !Array.isArray(advancedDraftProject.opening_greetings) || !advancedDraftProject.opening_greetings[idx]) return;
  const item = advancedDraftProject.opening_greetings[idx];
  const localHint = hintInputId
    ? (document.getElementById(hintInputId)?.value.trim() || "")
    : (document.getElementById(`advHint_og_${idx}`)?.value.trim() || "");
  const globalHint = document.getElementById("advGlobalPolishInstruction")?.value.trim() || "";
  const hint = [item.title ? `开场白主题：${item.title}` : "", localHint, globalHint].filter(Boolean).join("；");
  const selectedModel = document.getElementById("advAiModelSelect")?.value || "";
  const origLabel = btnEl ? btnEl.innerHTML : "润色";
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.innerHTML = "润色中...";
  }
  try {
    const polished = await callAiPolishApi(item.content || "", "opening_greeting", advancedDraftProject.name || "跑团游戏", hint, selectedModel);
    item.content = polished;
    renderAdvancedProjectEditor();
    if (localHint) {
      const restoredInput = document.getElementById(hintInputId || `advHint_og_${idx}`);
      if (restoredInput) {
        restoredInput.value = localHint;
        restoredInput.parentElement?.classList.add("has-value");
      }
    }
    showToast("已润色");
  } catch (err) {
    showToast("润色失败: " + err.message);
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.innerHTML = origLabel;
    }
  }
};

window.updateAdvContextMode = function (mode) {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject) return;
  if (!advancedDraftProject.completion_params) advancedDraftProject.completion_params = {};
  advancedDraftProject.completion_params.context_mode = mode === "tokens" ? "tokens" : "turns";
  renderAdvancedProjectEditor();
};

window.updateAdvCompletionParam = function (key, val) {
  if (!advancedDraftProject || Number.isNaN(val)) return;
  if (!advancedDraftProject.completion_params) advancedDraftProject.completion_params = {};
  advancedDraftProject.completion_params[key] = val;
  if (key === "context") {
    advancedDraftProject.max_context_turns = val;
    const calcEl = document.getElementById("advContextMsgsCalc");
    if (calcEl) calcEl.textContent = val * 2;
  }
  const numEl = document.getElementById(`advNum_${key}`);
  const rangeEl = document.getElementById(`advRange_${key}`);
  const isFloat = ["temperature", "repetition_penalty", "frequency_penalty", "presence_penalty", "top_p", "min_p"].includes(key);
  if (numEl && document.activeElement !== numEl) {
    numEl.value = isFloat ? Number(val).toFixed(2) : val;
  }
  if (rangeEl && document.activeElement !== rangeEl) {
    rangeEl.value = val;
  }
};

window.toggleAdvUseGlobalParams = function (checked) {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject) return;
  advancedDraftProject.use_global_params = !!checked;
  renderAdvancedProjectEditor();
};

window.clearAdvancedBackground = function (isMobile = false) {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject) return;
  if (!advancedDraftProject.appearance) advancedDraftProject.appearance = {};
  if (isMobile) {
    advancedDraftProject.appearance.bg_mobile = "";
  } else {
    advancedDraftProject.appearance.bg_image = "";
    advancedDraftProject.bg_image = "";
  }
  renderAdvancedProjectEditor();
};

window.pickAdvancedGalleryAsset = function (slot, cgIdx = -1) {
  syncAdvancedDraftFromDom();
  window.openGalleryAssetPicker((url) => {
    if (!advancedDraftProject) return;
    if (!advancedDraftProject.appearance) advancedDraftProject.appearance = {};
    if (slot === "icon") {
      advancedDraftProject.icon = url;
      advancedDraftProject.avatar = url;
    } else if (slot === "bg_image") {
      advancedDraftProject.appearance.bg_image = url;
      advancedDraftProject.bg_image = url;
    } else if (slot === "bg_mobile") {
      advancedDraftProject.appearance.bg_mobile = url;
    } else if (slot === "cg" && cgIdx >= 0 && Array.isArray(advancedDraftProject.cg_book) && advancedDraftProject.cg_book[cgIdx]) {
      advancedDraftProject.cg_book[cgIdx].url = url;
      advancedDraftProject.cg_book[cgIdx].image_url = url;
    }
    renderAdvancedProjectEditor();
  });
};

window.handleUploadAdvCgFile = async function (event, cgIdx) {
  const file = event.target?.files?.[0];
  if (!file || !advancedDraftProject) return;
  syncAdvancedDraftFromDom();
  showToast("上传 CG 图片中...");
  try {
    const url = await uploadImageAndGetUrl(file, 1440, 0.85, "场景CG");
    if (Array.isArray(advancedDraftProject.cg_book) && advancedDraftProject.cg_book[cgIdx]) {
      advancedDraftProject.cg_book[cgIdx].url = url;
      advancedDraftProject.cg_book[cgIdx].image_url = url;
      renderAdvancedProjectEditor();
      showToast("CG 图片已上传");
    }
  } catch (err) {
    showToast("CG 上传失败: " + err.message);
  } finally {
    try { event.target.value = ""; } catch (e) {}
  }
};

window.toggleAdvQuickTag = function (tagStr) {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject) return;
  if (!Array.isArray(advancedDraftProject.tags)) advancedDraftProject.tags = [];
  const idx = advancedDraftProject.tags.indexOf(tagStr);
  if (idx === -1) advancedDraftProject.tags.push(tagStr);
  else advancedDraftProject.tags.splice(idx, 1);
  renderAdvancedProjectEditor();
};

window.toggleAdvDetailedPreview = function () {
  syncAdvancedDraftFromDom();
  advShowDetailedPreview = !advShowDetailedPreview;
  renderAdvancedProjectEditor();
};

window.applyAdvStatusSkeletonPreset = function (presetKey) {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject) return;
  const { enabled, modules } = buildPresetUiModules(presetKey, advancedDraftProject.ui_modules);
  advancedDraftProject.status_panel_enabled = enabled;
  advancedDraftProject.ui_modules = modules;
  renderAdvancedProjectEditor();
  showToast(enabled ? "已载入变量/状态面板预设骨架" : "已关闭状态面板");
};

window.addAdvUiModuleRow = function () {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject) return;
  advancedDraftProject.status_panel_enabled = true;
  if (!Array.isArray(advancedDraftProject.ui_modules)) advancedDraftProject.ui_modules = [];
  advancedDraftProject.ui_modules.push({
    id: `mod_${Date.now().toString(36)}`,
    key: `自定义面板 #${advancedDraftProject.ui_modules.length + 1}`,
    type: "progress_stats",
    enabled: true,
    fields: "生命: 100/100\n状态: 正常",
    desc: "根据每回合剧情动态更新数值与状态。",
    v: 2
  });
  renderAdvancedProjectEditor();
};

window.removeAdvUiModuleRow = function (idx) {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject || !Array.isArray(advancedDraftProject.ui_modules)) return;
  advancedDraftProject.ui_modules.splice(idx, 1);
  renderAdvancedProjectEditor();
};

// Tab 2: 世界书管理
window.updateAdvWbSearch = function (val) {
  syncAdvancedDraftFromDom();
  advWbSearchQuery = String(val || "");
  renderAdvancedProjectEditor();
  const inp = document.getElementById("advWbSearchInput");
  if (inp) {
    inp.focus();
    inp.setSelectionRange(inp.value.length, inp.value.length);
  }
};

window.addAdvWorldbookEntry = function () {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject) return;
  if (!Array.isArray(advancedDraftProject.world_book)) advancedDraftProject.world_book = [];
  if (advancedDraftProject.world_book.length >= 2000) {
    showToast("世界书词条已达 2,000 条上限");
    return;
  }
  const defs = advancedDraftProject.worldbook_defaults || {};
  const defMatch = defs.match_type || "OR";
  advancedDraftProject.world_book.unshift({
    id: `wb_${Date.now().toString(36)}`,
    name: `词条 #${advancedDraftProject.world_book.length + 1}`,
    keys: [],
    constant: defMatch === "CONSTANT",
    match_type: defMatch === "CONSTANT" ? "OR" : defMatch,
    key_region: Number(defs.key_region) || 6,
    value_region: defs.value_region || "System",
    content: "",
    value: "",
    enabled: true,
    enable: true
  });
  advWbSearchQuery = "";
  renderAdvancedProjectEditor();
};

window.removeAdvWorldbookEntry = function (origIdx) {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject || !Array.isArray(advancedDraftProject.world_book)) return;
  advancedDraftProject.world_book.splice(origIdx, 1);
  renderAdvancedProjectEditor();
};

window.applyAdvWbDefaultsToAll = function () {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject || !Array.isArray(advancedDraftProject.world_book)) return;
  const defs = advancedDraftProject.worldbook_defaults || {};
  const defMatch = defs.match_type || "OR";
  advancedDraftProject.world_book.forEach((wb) => {
    wb.key_region = Number(defs.key_region) || 6;
    wb.constant = defMatch === "CONSTANT";
    wb.match_type = defMatch === "CONSTANT" ? "OR" : defMatch;
    wb.value_region = defs.value_region || "System";
  });
  renderAdvancedProjectEditor();
  showToast("已将默认样式应用到全部世界书词条");
};

window.exportAdvWorldbookJson = function () {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject) return;
  const blob = new Blob([JSON.stringify(advancedDraftProject.world_book || [], null, 2)], { type: "application/json;charset=utf-8" });
  _triggerBlobDownload(blob, `${(advancedDraftProject.name || "游戏卡").replace(/[\\/:*?"<>|]+/g, "_")}_世界书.json`);
};

window.importAdvWorldbookJson = function (event) {
  const file = event.target?.files?.[0];
  if (!file || !advancedDraftProject) return;
  syncAdvancedDraftFromDom();
  const reader = new FileReader();
  reader.onload = (ev) => {
    try {
      const raw = JSON.parse(String(ev.target.result || "{}"));
      let entries = [];
      if (Array.isArray(raw)) {
        entries = raw;
      } else if (raw && typeof raw === "object") {
        if (Array.isArray(raw.entries)) entries = raw.entries;
        else if (raw.entries && typeof raw.entries === "object") entries = Object.values(raw.entries);
        else if (Array.isArray(raw.world_book)) entries = raw.world_book;
      }
      const converted = entries.map((it, idx) => ({
        id: String(it.id || it.uid || `wb_imp_${Date.now().toString(36)}_${idx}`),
        name: String(it.name || it.comment || `导入词条 #${idx + 1}`),
        keys: Array.isArray(it.keys) ? it.keys : (Array.isArray(it.key) ? it.key : String(it.keys || it.key || "").split(/[,，]/).map((s) => s.trim()).filter(Boolean)),
        constant: Boolean(it.constant),
        match_type: it.selective ? "AND" : (it.match_type || "OR"),
        key_region: Number(it.key_region) || 6,
        value_region: it.value_region || "System",
        content: String(it.content ?? it.value ?? ""),
        value: String(it.content ?? it.value ?? ""),
        enabled: it.enabled !== false && it.disable !== true,
        enable: it.enabled !== false && it.disable !== true
      }));
      if (!Array.isArray(advancedDraftProject.world_book)) advancedDraftProject.world_book = [];
      advancedDraftProject.world_book.push(...converted);
      renderAdvancedProjectEditor();
      showToast(`已导入 ${converted.length} 条世界书词条`);
    } catch (err) {
      showToast("解析世界书 JSON 失败: " + err.message);
    }
  };
  reader.readAsText(file);
  try { event.target.value = ""; } catch (e) {}
};

// Tab 3: 内置 CSS / 正则 / CG / 快捷指令管理
window.applyAdvCssPreset = function (presetKey) {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject) return;
  const nextCss = presetKey && OFFICIAL_CSS_PRESETS[presetKey] ? OFFICIAL_CSS_PRESETS[presetKey].css : "";
  advancedDraftProject.custom_css = nextCss;
  if (!advancedDraftProject.appearance) advancedDraftProject.appearance = {};
  advancedDraftProject.appearance.custom_css = nextCss;
  renderAdvancedProjectEditor();
  showToast(presetKey ? `已套用官方皮肤：${OFFICIAL_CSS_PRESETS[presetKey].label}` : "已清空内置 CSS");
};

window.insertAdvCustomUiExample = function () {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject) return;
  const snippet = `.custom-ui {\n  margin: 10px 0;\n  padding: 12px 16px;\n  border-radius: 10px;\n  background: rgba(30, 41, 59, 0.72);\n  border: 1px solid rgba(212, 166, 90, 0.45);\n  color: #fde68a;\n}`;
  advancedDraftProject.custom_css = (advancedDraftProject.custom_css ? advancedDraftProject.custom_css.trimEnd() + "\n\n" : "") + snippet;
  if (!advancedDraftProject.appearance) advancedDraftProject.appearance = {};
  advancedDraftProject.appearance.custom_css = advancedDraftProject.custom_css;
  renderAdvancedProjectEditor();
};

window.refreshAdvCssLivePreview = function (rawCss) {
  const styleEl = document.getElementById("advCssPreviewScopedStyle");
  const countEl = document.getElementById("advCssCharCounter");
  if (countEl) countEl.textContent = `${String(rawCss || "").length} 字`;
  if (styleEl) {
    styleEl.textContent = scopeProjectCss(String(rawCss || ""), "#advCssLivePreviewStage");
  }
};

window.addAdvRegexRule = function () {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject) return;
  if (!Array.isArray(advancedDraftProject.regex_replaces)) advancedDraftProject.regex_replaces = [];
  advancedDraftProject.regex_replaces.push({
    id: `rx_${Date.now().toString(36)}`,
    name: `正则规则 #${advancedDraftProject.regex_replaces.length + 1}`,
    pattern: "",
    replacement: "",
    scope: "assistant",
    is_only_render: true,
    enabled: true
  });
  advancedDraftProject.regex_scripts = advancedDraftProject.regex_replaces;
  renderAdvancedProjectEditor();
};

window.removeAdvRegexRule = function (idx) {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject || !Array.isArray(advancedDraftProject.regex_replaces)) return;
  advancedDraftProject.regex_replaces.splice(idx, 1);
  advancedDraftProject.regex_scripts = advancedDraftProject.regex_replaces;
  renderAdvancedProjectEditor();
};

window.addAdvCgEntry = function () {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject) return;
  if (!Array.isArray(advancedDraftProject.cg_book)) advancedDraftProject.cg_book = [];
  if (advancedDraftProject.cg_book.length >= 20) {
    showToast("特殊 CG 最多设置 20 个");
    return;
  }
  const defs = advancedDraftProject.cg_defaults || {};
  advancedDraftProject.cg_book.push({
    id: `cg_${Date.now().toString(36)}`,
    name: `特殊CG #${advancedDraftProject.cg_book.length + 1}`,
    url: "",
    image_url: "",
    keys: [],
    trigger_source: defs.trigger_source || "ai",
    match_type: defs.match_type || "OR",
    display_mode: defs.display_mode || "chat",
    enabled: true
  });
  renderAdvancedProjectEditor();
};

window.removeAdvCgEntry = function (idx) {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject || !Array.isArray(advancedDraftProject.cg_book)) return;
  advancedDraftProject.cg_book.splice(idx, 1);
  renderAdvancedProjectEditor();
};

window.addAdvQuickReply = function () {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject) return;
  if (!Array.isArray(advancedDraftProject.quick_replies)) advancedDraftProject.quick_replies = [];
  if (advancedDraftProject.quick_replies.length >= 10) {
    showToast("最多可添加 10 个快捷回复指令");
    return;
  }
  advancedDraftProject.quick_replies.push({
    id: `qr_${Date.now().toString(36)}`,
    label: "",
    command: "",
    content: "",
    auto_send: true
  });
  renderAdvancedProjectEditor();
};

window.removeAdvQuickReply = function (idx) {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject || !Array.isArray(advancedDraftProject.quick_replies)) return;
  advancedDraftProject.quick_replies.splice(idx, 1);
  renderAdvancedProjectEditor();
};

window.updateAdvLiveCounter = function (textareaEl, counterId) {
  const cEl = document.getElementById(counterId);
  if (cEl && textareaEl) {
    cEl.textContent = `${textareaEl.value.length} 字`;
  }
};

function renderAdvancedProjectEditor() {
  const modalEl = document.getElementById("exploreModal");
  if (modalEl && modalEl.style.display === "none") {
    modalEl.style.display = "flex";
  }
  const body = document.getElementById("exploreModalBody");
  if (!body || !advancedDraftProject) return;
  const isAlreadyInEditor = !!document.getElementById("advProjName");
  const prevScrollTop = isAlreadyInEditor ? body.scrollTop : 0;
  const parentEl = body.parentElement;
  const prevParentScroll = isAlreadyInEditor && parentEl ? parentEl.scrollTop : 0;
  const d = advancedDraftProject;
  const baseCp = d.completion_params || {};
  const useGlobal = d.use_global_params !== false;
  const { activeModel, hasModelOverride, modelParams } = getActiveModelParamOverrideInfo();
  const globalCp = window.globalUserSettings || {};
  const effectiveBase = useGlobal ? { ...baseCp, ...globalCp } : baseCp;
  const cp = hasModelOverride ? { ...effectiveBase, ...modelParams } : effectiveBase;
  const isParamsLocked = hasModelOverride || useGlobal;
  const disabledAttr = isParamsLocked ? "disabled" : "";
  const ctxTurns = Number(cp.context ?? (useGlobal ? globalCp.max_context_turns : d.max_context_turns) ?? 16);
  const bgUrl = d.appearance?.bg_image || d.bg_image || "";

  const isEditingExisting = Boolean(d.id && !["proj_fast_trpg", "proj_default", "proj_free_chat"].includes(d.id));
  const bgMobileUrl = d.appearance?.bg_mobile || "";
  const customCssVal = d.custom_css || d.appearance?.custom_css || "";
  const wbList = Array.isArray(d.world_book) ? d.world_book : [];
  const rxList = Array.isArray(d.regex_replaces) ? d.regex_replaces : [];
  const cgList = Array.isArray(d.cg_book) ? d.cg_book : [];
  const qrList = Array.isArray(d.quick_replies) ? d.quick_replies : [];
  const uiMods = getEffectiveUiModules(d);
  const wbDefs = d.worldbook_defaults || { key_region: 6, match_type: "OR", value_region: "System" };
  const cgDefs = d.cg_defaults || { trigger_source: "ai", match_type: "OR", display_mode: "chat" };
  const otherExtCount = (customCssVal.trim() ? 1 : 0) + rxList.length + cgList.length + qrList.length + (d.opening_greetings?.length || 0);

  const titleEl = document.getElementById("exploreModalTitle");
  if (titleEl) {
    titleEl.textContent = isEditingExisting ? `高级创作 · 编辑「${d.name || "游戏卡"}」` : "高级创作 · 游戏卡工坊";
  }

  let tabContentHtml = "";
  if (currentAdvancedCreatorTab === "basic") {
    const detailedRaw = d.detailed_description || "";
    const detailedPreviewRendered = advShowDetailedPreview
      ? `<div style="margin-top:10px;">${
          typeof window.renderDetailedDescriptionBlock === "function"
            ? (window.renderDetailedDescriptionBlock(detailedRaw).html || `<div class="detailed-intro-card">（暂无详细介绍内容）</div>`)
            : `<div class="detailed-intro-card">${escapeHtml(detailedRaw || "（暂无详细介绍内容）")}</div>`
        }</div>`
      : "";

    tabContentHtml = `
      <!-- 1. 作品名称 · 管理标签 · 封面 -->
      <div class="studio-section-card" style="margin:0;">
        <div class="studio-section-header" style="flex-wrap:wrap;gap:8px;">
          <div class="studio-section-title">基础信息与封面</div>
          <span style="font-size:11.5px;color:var(--text-muted);">新建游戏卡默认保持纯净 0 提示词；支持 PNG / JPG / WEBP / GIF 封面</span>
        </div>

        <div style="display:grid;grid-template-columns:220px 1fr;gap:14px;align-items:start;margin-bottom:12px;">
          <!-- 封面卡片 -->
          <div style="display:flex;flex-direction:column;gap:6px;">
            <label class="gc-field-label">封面</label>
            <div style="position:relative;height:142px;border-radius:12px;border:1px dashed rgba(255,255,255,0.22);background:rgba(255,255,255,0.025);display:flex;align-items:center;justify-content:center;overflow:hidden;cursor:pointer;" onclick="document.getElementById('advProjIconFileInput').click()" title="点击上传本地封面图片">
              <div id="advProjIconPreview" style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;">
                ${(d.icon && (d.icon.startsWith("/") || d.icon.startsWith("http") || d.icon.startsWith("data:image/")))
                  ? `<img src="${escapeHtml(d.icon)}" alt="封面" style="width:100%;height:100%;object-fit:cover;" />`
                  : `<div style="text-align:center;color:var(--text-muted);font-size:11.5px;padding:8px;"><div style="font-size:24px;color:var(--lp-accent,#d4a65a);">+</div><div>上传封面图片</div><small style="color:var(--text-dim);">导出 PNG 游戏卡卡面</small></div>`
                }
              </div>
            </div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;">
              <button type="button" class="btn btn-xs btn-secondary" style="flex:1;" onclick="document.getElementById('advProjIconFileInput').click()">本地上传</button>
              <button type="button" class="btn btn-xs btn-outline-secondary" style="flex:1;" onclick="window.pickAdvancedGalleryAsset('icon')">使用图库图片</button>
              ${d.icon ? `<button type="button" class="btn btn-xs btn-outline-secondary" onclick="document.getElementById('advProjIcon').value='';window.previewIconInputChange('','advProjIconPreview');advancedDraftProject.icon='';advancedDraftProject.avatar='';renderAdvancedProjectEditor();">✕</button>` : ""}
            </div>
            <input type="hidden" id="advProjIcon" value="${escapeHtml(d.icon || "")}" />
            <input type="file" id="advProjIconFileInput" accept="image/png,image/jpeg,image/webp,image/gif" style="display:none;" onchange="window.handleUploadProjectIcon(event, 'advanced')" />
          </div>

          <!-- 作品名称 + 管理标签 + 简介 -->
          <div style="display:flex;flex-direction:column;gap:10px;min-width:0;">
            <div style="display:grid;grid-template-columns:1fr 1.2fr;gap:10px;">
              <div>
                <label class="gc-field-label">作品名称</label>
                <input type="text" id="advProjName" class="form-input" value="${escapeHtml(d.name || "")}" placeholder="请输入作品名称" />
              </div>
              <div>
                <label class="gc-field-label">管理标签 <small>（逗号分隔或点选下方快捷标签）</small></label>
                <input type="text" id="advProjTags" class="form-input" value="${escapeHtml((d.tags || []).join(", "))}" placeholder="奇幻, 潜入, 多分支" />
              </div>
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:5px;">
              ${(typeof GUIDED_QUICK_TAGS !== "undefined" ? GUIDED_QUICK_TAGS : ["奇幻", "潜入", "悬疑", "赛博", "古风", "校园", "生存", "多分支"]).map((tg) => {
                const active = (d.tags || []).includes(tg);
                return `<button type="button" class="gc-tag-chip ${active ? "active" : ""}" onclick="window.toggleAdvQuickTag('${escapeJsAttr(tg)}')">#${escapeHtml(tg)}</button>`;
              }).join("")}
            </div>
            <div>
              <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:4px;">
                <label class="gc-field-label" style="margin:0;">简介 <small>（给作品写一句简短介绍，选填，不影响 AI 回复）</small></label>
                <div style="display:flex;align-items:center;gap:8px;">
                  <span id="advDescCounter" class="adv-char-counter">${(d.description || "").length} 字</span>
                  <div class="ai-fused-input-group">
                    <input type="text" id="advHint_description" class="ai-fused-input" style="width:130px;" placeholder="润色想法" oninput="this.parentElement.classList.toggle('has-value', !!this.value.trim())" onkeydown="if(event.key==='Enter'){event.preventDefault();this.nextElementSibling.click();}" />
                    <button type="button" class="ai-fused-btn" onclick="window.polishAdvancedField('advProjDesc', 'description', this, 'advHint_description')">润色</button>
                  </div>
                </div>
              </div>
              <textarea id="advProjDesc" rows="2" class="form-textarea" placeholder="一句话展示在游戏卡列表与 PNG 海报卡面上..." oninput="window.updateAdvLiveCounter(this, 'advDescCounter')">${escapeHtml(d.description || "")}</textarea>
            </div>
          </div>
        </div>

        <!-- 详细介绍（支持 Markdown / 安全 HTML + 调试与预览） -->
        <div style="padding-top:10px;border-top:1px solid var(--border-subtle);">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px;">
            <label class="gc-field-label" style="margin:0;">详细介绍 <small>（支持完整 HTML/CSS/JS 交互开局设定器或 Markdown，独立安全沙箱运行，不影响 AI 回复）</small></label>
            <div style="display:flex;align-items:center;gap:8px;">
              <span id="advDetailDescCounter" class="adv-char-counter">${detailedRaw.length} 字</span>
              <button type="button" class="btn btn-xs ${advShowDetailedPreview ? "btn-primary" : "btn-outline-secondary"}" onclick="window.toggleAdvDetailedPreview()">
                ${advShowDetailedPreview ? "收起预览" : "调试与预览"}
              </button>
            </div>
          </div>
          <textarea id="advProjDetailedDesc" rows="3" class="form-textarea" placeholder="支持 Markdown 与安全 HTML 样式卡片，将在进入该游戏卡时的欢迎页展示..." oninput="window.updateAdvLiveCounter(this, 'advDetailDescCounter')">${escapeHtml(detailedRaw)}</textarea>
          ${detailedPreviewRendered}
        </div>
      </div>

      <!-- 2. 主提示词 -->
      <div class="studio-section-card" style="margin:0;">
        <div class="studio-section-header" style="flex-wrap:wrap;gap:6px;">
          <div style="display:flex;align-items:center;gap:8px;">
            <div class="studio-section-title">提示词（主提示词）</div>
            <span id="advSysCounter" class="adv-char-counter">${(d.system_prompt || "").length} 字</span>
          </div>
          <div class="ai-fused-input-group">
            <input type="text" id="advHint_system_prompt" class="ai-fused-input" style="width:165px;" placeholder="润色想法" oninput="this.parentElement.classList.toggle('has-value', !!this.value.trim())" onkeydown="if(event.key==='Enter'){event.preventDefault();this.nextElementSibling.click();}" />
            <button type="button" class="ai-fused-btn" onclick="window.polishAdvancedField('advProjSystem', 'system_prompt', this, 'advHint_system_prompt')">润色</button>
          </div>
        </div>
        <div class="adv-note-box" style="margin-bottom:8px;">
          1. 主提示词用于实现世界观、角色设定与核心规则（留空则保持 0 提示词纯净模式，建议保持左对齐与层级清晰）。<br/>
          2. 如需让 AI 输出自定义 HTML 界面块，可写在 <code>&lt;Reply Example&gt;&lt;div class='custom-ui'&gt;...&lt;/div&gt;&lt;/Reply Example&gt;</code> 内，并前往 <b>「03 其他设置 · CSS」</b> 编写 <code>.custom-ui</code> 专属样式。
        </div>
        <textarea id="advProjSystem" rows="9" class="form-textarea" placeholder="在此编写世界观、登场人物与游玩规则..." oninput="window.updateAdvLiveCounter(this, 'advSysCounter')">${escapeHtml(d.system_prompt || "")}</textarea>
      </div>

      <!-- 3. 前置词 & 后置词 -->
      <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:12px;">
        <div class="studio-section-card" style="margin:0;">
          <div class="studio-section-header" style="flex-wrap:wrap;gap:6px;">
            <div style="display:flex;align-items:center;gap:8px;">
              <div class="studio-section-title">前置词</div>
              <span id="advPrefixCounter" class="adv-char-counter">${(d.prefix || "").length} 字</span>
            </div>
            <div class="ai-fused-input-group">
              <input type="text" id="advHint_prefix" class="ai-fused-input" style="width:120px;" placeholder="想法" oninput="this.parentElement.classList.toggle('has-value', !!this.value.trim())" onkeydown="if(event.key==='Enter'){event.preventDefault();this.nextElementSibling.click();}" />
              <button type="button" class="ai-fused-btn" onclick="window.polishAdvancedField('advProjPrefix', 'prefix', this, 'advHint_prefix')">润色</button>
            </div>
          </div>
          <div style="font-size:11.5px;color:var(--text-muted);margin-bottom:6px;">系统自动拼接在用户输入之前，可辅助触发世界书或设定本轮前置语境</div>
          <textarea id="advProjPrefix" rows="3" class="form-textarea" placeholder="拼接在玩家每轮输入前（选填）" oninput="window.updateAdvLiveCounter(this, 'advPrefixCounter')">${escapeHtml(d.prefix || "")}</textarea>
        </div>

        <div class="studio-section-card" style="margin:0;">
          <div class="studio-section-header" style="flex-wrap:wrap;gap:6px;">
            <div style="display:flex;align-items:center;gap:8px;">
              <div class="studio-section-title">后置词</div>
              <span id="advSuffixCounter" class="adv-char-counter">${(d.suffix || "").length} 字</span>
            </div>
            <div class="ai-fused-input-group">
              <input type="text" id="advHint_suffix" class="ai-fused-input" style="width:120px;" placeholder="想法" oninput="this.parentElement.classList.toggle('has-value', !!this.value.trim())" onkeydown="if(event.key==='Enter'){event.preventDefault();this.nextElementSibling.click();}" />
              <button type="button" class="ai-fused-btn" onclick="window.polishAdvancedField('advProjSuffix', 'suffix', this, 'advHint_suffix')">润色</button>
            </div>
          </div>
          <div style="font-size:11.5px;color:var(--text-muted);margin-bottom:6px;">系统自动拼接在用户输入之后（最高注意力权重区），适合放置格式收尾守则</div>
          <textarea id="advProjSuffix" rows="3" class="form-textarea" placeholder="拼接在玩家每轮输入后（选填）" oninput="window.updateAdvLiveCounter(this, 'advSuffixCounter')">${escapeHtml(d.suffix || "")}</textarea>
        </div>
      </div>

      <!-- 4. 使用变量面板 / 状态栏 -->
      <div class="studio-section-card" style="margin:0;">
        <div class="studio-section-header" style="flex-wrap:wrap;gap:8px;">
          <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
            <div class="studio-section-title">使用变量面板 / 状态栏</div>
            <label class="checkbox-label" style="font-size:0.8rem;font-weight:600;color:${d.status_panel_enabled !== false ? "var(--tc-34d399, #34d399)" : "var(--text-muted)"};">
              <input type="checkbox" id="advStatusPanelEnabled" ${d.status_panel_enabled !== false ? "checked" : ""} onchange="window.handleToggleAdvStatusPanel(this.checked)" />
              <span>${d.status_panel_enabled !== false ? `已开启 (${uiMods.filter((m) => m.enabled !== false).length} 栏)` : "未开启（点击启用数据骨架与变量提示词）"}</span>
            </label>
          </div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;">
            <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.applyAdvStatusSkeletonPreset('standard')">标准 6 栏</button>
            <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.applyAdvStatusSkeletonPreset('tactical')">战术身体栏</button>
            <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.applyAdvStatusSkeletonPreset('investigative')">调查线索栏</button>
            <button type="button" class="btn btn-xs btn-primary" onclick="window.addAdvUiModuleRow()">+ 添加面板栏位</button>
          </div>
        </div>
        <div style="font-size:11.5px;color:var(--text-muted);margin-bottom:8px;">开启后可为作品配置数据骨架、面板组件类型与变量提示词，聊天中自动渲染实时状态面板。</div>
        ${d.status_panel_enabled !== false ? `
          <div id="advUiModulesList" style="display:flex;flex-direction:column;gap:8px;">
            ${uiMods.map((mod, idx) => `
              <div class="adv-uimod-row" data-mod-id="${escapeHtml(mod.id || `mod_${idx + 1}`)}" style="padding:8px 10px;border-radius:8px;border:1px solid var(--border-subtle);background:rgba(255,255,255,0.025);display:flex;flex-direction:column;gap:6px;">
                <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                  <input type="checkbox" class="adv-uimod-enabled" ${mod.enabled !== false ? "checked" : ""} />
                  <input type="text" class="form-input adv-uimod-key" value="${escapeHtml(mod.key || "")}" placeholder="栏位名称" style="width:130px;padding:3px 8px;font-size:12px;font-weight:700;" />
                  <select class="form-select adv-uimod-type" style="width:auto;padding:2px 22px 2px 8px;height:26px;font-size:11.5px;">
                    <option value="thinking_fold" ${mod.type === "thinking_fold" ? "selected" : ""}>思考折叠</option>
                    <option value="story_narrative" ${mod.type === "story_narrative" ? "selected" : ""}>剧情正文</option>
                    <option value="progress_stats" ${mod.type === "progress_stats" ? "selected" : ""}>数值进度条</option>
                    <option value="equipment_slots" ${mod.type === "equipment_slots" ? "selected" : ""}>身体/装备槽</option>
                    <option value="inventory_grid" ${mod.type === "inventory_grid" ? "selected" : ""}>背包物品格</option>
                    <option value="npc_affinity" ${mod.type === "npc_affinity" ? "selected" : ""}>角色好感卡</option>
                    <option value="text_card" ${mod.type === "text_card" || mod.type === "tags" ? "selected" : ""}>情报线索卡</option>
                    <option value="action_choices" ${mod.type === "action_choices" ? "selected" : ""}>底部行动选项</option>
                  </select>
                  <button type="button" class="btn btn-xs btn-danger" style="margin-left:auto;" onclick="window.removeAdvUiModuleRow(${idx})">删除</button>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                  <textarea rows="2" class="form-textarea adv-uimod-fields" placeholder="数据骨架（如 生命: 100/100）" style="font-size:12px;">${escapeHtml(mod.fields || "")}</textarea>
                  <textarea rows="2" class="form-textarea adv-uimod-desc" placeholder="变量提示词（告诉 AI 如何更新此栏位）" style="font-size:12px;">${escapeHtml(mod.desc || "")}</textarea>
                </div>
              </div>
            `).join("")}
          </div>
        ` : ""}
      </div>
    `;
  } else if (currentAdvancedCreatorTab === "worldbook") {
    const qLower = advWbSearchQuery.trim().toLowerCase();
    const filteredWb = wbList
      .map((wb, origIdx) => ({ wb, origIdx }))
      .filter(({ wb }) => {
        if (!qLower) return true;
        const kStr = Array.isArray(wb.keys) ? wb.keys.join(" ") : String(wb.keys || "");
        return (
          String(wb.name || "").toLowerCase().includes(qLower) ||
          kStr.toLowerCase().includes(qLower) ||
          String(wb.content || wb.value || "").toLowerCase().includes(qLower)
        );
      });

    tabContentHtml = `
      <div class="studio-section-card" style="margin:0;">
        <div class="studio-section-header" style="flex-wrap:wrap;gap:8px;">
          <div class="studio-section-title">世界书设置 <span class="adv-char-counter">(${wbList.length} / 2,000)</span></div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
            <input type="text" id="advWbSearchInput" class="form-input" style="width:210px;padding:4px 10px;font-size:12px;" value="${escapeHtml(advWbSearchQuery)}" placeholder="搜索触发关键词 / 内容..." oninput="window.updateAdvWbSearch(this.value)" />
            <button type="button" class="btn btn-xs btn-outline-secondary" onclick="document.getElementById('advWbImportFileInput').click()">导入 JSON</button>
            <input type="file" id="advWbImportFileInput" accept=".json" style="display:none;" onchange="window.importAdvWorldbookJson(event)" />
            <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.exportAdvWorldbookJson()">导出 JSON</button>
            <button type="button" class="btn btn-xs btn-primary" onclick="window.addAdvWorldbookEntry()">+ 新增词条</button>
          </div>
        </div>

        <div class="adv-note-box" style="margin-bottom:10px;">
          1. 上限 2,000 个词条，适合存放无需每轮常驻的角色档案、支线剧情、门派势力、隐藏彩蛋等按需触发设定。<br/>
          2. 请勿使用“。”、“，”、“你”、“我”、“他”等极高频字词作为触发词以免无意义消耗上下文；需要每轮常驻的设定请直接放入主提示词或将格式设为「常驻」。
        </div>

        <!-- 世界书默认样式 -->
        <div class="adv-default-bar" style="margin-bottom:12px;">
          <b style="color:var(--text-main);">世界书默认样式：</b>
          <span>触发区域</span>
          <select id="advWbDefKeyRegion" class="form-select" style="width:auto;padding:2px 22px 2px 8px;height:26px;font-size:12px;">
            <option value="6" ${Number(wbDefs.key_region || 6) === 6 ? "selected" : ""}>玩家输入 + AI 回复</option>
            <option value="2" ${Number(wbDefs.key_region) === 2 ? "selected" : ""}>仅玩家输入</option>
            <option value="4" ${Number(wbDefs.key_region) === 4 ? "selected" : ""}>仅 AI 回复</option>
          </select>
          <span>格式</span>
          <select id="advWbDefMatch" class="form-select" style="width:auto;padding:2px 22px 2px 8px;height:26px;font-size:12px;">
            <option value="OR" ${wbDefs.match_type === "OR" ? "selected" : ""}>或 OR (任一命中)</option>
            <option value="AND" ${wbDefs.match_type === "AND" ? "selected" : ""}>与 AND (全部命中)</option>
            <option value="Regex" ${wbDefs.match_type === "Regex" ? "selected" : ""}>正则 Regex</option>
            <option value="CONSTANT" ${wbDefs.match_type === "CONSTANT" ? "selected" : ""}>常驻触发</option>
          </select>
          <span>影响范围（注入位置）</span>
          <select id="advWbDefValRegion" class="form-select" style="width:auto;padding:2px 22px 2px 8px;height:26px;font-size:12px;">
            <option value="System" ${wbDefs.value_region !== "Prefix" && wbDefs.value_region !== "Suffix" ? "selected" : ""}>系统设定区 (System)</option>
            <option value="Prefix" ${wbDefs.value_region === "Prefix" ? "selected" : ""}>前置区 (Prefix)</option>
            <option value="Suffix" ${wbDefs.value_region === "Suffix" ? "selected" : ""}>后置区 (Suffix)</option>
          </select>
          ${wbList.length > 0 ? `<button type="button" class="btn btn-xs btn-outline-secondary" style="margin-left:auto;" onclick="window.applyAdvWbDefaultsToAll()">应用到现有词条</button>` : ""}
        </div>

        <div id="advWorldbookList" style="display:flex;flex-direction:column;gap:8px;">
          ${filteredWb.length === 0
            ? `<div style="padding:18px;border:1px dashed var(--border-subtle);border-radius:10px;text-align:center;color:var(--text-dim);font-size:12.5px;">${qLower ? "没有匹配搜索条件的世界书词条" : "暂无世界书词条，点击右上角「+ 新增词条」或「导入 JSON」添加"}</div>`
            : filteredWb.map(({ wb, origIdx }) => {
                const keysStr = Array.isArray(wb.keys) ? wb.keys.join(", ") : String(wb.keys || "");
                const rawMt = wb.constant ? "CONSTANT" : (wb.match_type === 1 || wb.match_type === "AND" ? "AND" : (wb.match_type === 3 || wb.match_type === "Regex" ? "Regex" : "OR"));
                const keyReg = Number(wb.key_region) || 6;
                const valReg = (wb.value_region === 2 || wb.value_region === "Prefix") ? "Prefix" : ((wb.value_region === 4 || wb.value_region === "Suffix") ? "Suffix" : "System");
                const contentVal = wb.content !== undefined ? wb.content : (wb.value || "");
                const isEn = (wb.enabled !== undefined ? wb.enabled : wb.enable) !== false;
                return `
                  <div class="adv-wb-item" data-wb-idx="${origIdx}" style="padding:10px 12px;border-radius:10px;border:1px solid var(--border-subtle);background:rgba(255,255,255,0.025);display:flex;flex-direction:column;gap:8px;">
                    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                      <label class="checkbox-label" style="font-size:12px;margin:0;">
                        <input type="checkbox" class="adv-wb-enabled" ${isEn ? "checked" : ""} />
                        <span>启用</span>
                      </label>
                      <input type="text" class="form-input adv-wb-name" value="${escapeHtml(wb.name || `词条 #${origIdx + 1}`)}" placeholder="词条备注名" style="width:140px;padding:4px 8px;font-size:12px;font-weight:600;" />
                      <input type="text" class="form-input adv-wb-keys" value="${escapeHtml(keysStr)}" placeholder="触发关键词（多个用逗号分隔）" style="flex:1;min-width:160px;padding:4px 8px;font-size:12px;" />
                      <select class="form-select adv-wb-keyregion" style="width:auto;padding:2px 20px 2px 6px;height:26px;font-size:11.5px;" title="触发区域">
                        <option value="6" ${keyReg === 6 ? "selected" : ""}>玩家+AI</option>
                        <option value="2" ${keyReg === 2 ? "selected" : ""}>仅玩家</option>
                        <option value="4" ${keyReg === 4 ? "selected" : ""}>仅AI</option>
                      </select>
                      <select class="form-select adv-wb-match" style="width:auto;padding:2px 20px 2px 6px;height:26px;font-size:11.5px;" title="匹配格式">
                        <option value="OR" ${rawMt === "OR" ? "selected" : ""}>或 OR</option>
                        <option value="AND" ${rawMt === "AND" ? "selected" : ""}>与 AND</option>
                        <option value="Regex" ${rawMt === "Regex" ? "selected" : ""}>Regex</option>
                        <option value="CONSTANT" ${rawMt === "CONSTANT" ? "selected" : ""}>常驻</option>
                      </select>
                      <select class="form-select adv-wb-valregion" style="width:auto;padding:2px 20px 2px 6px;height:26px;font-size:11.5px;" title="注入范围">
                        <option value="System" ${valReg === "System" ? "selected" : ""}>System</option>
                        <option value="Prefix" ${valReg === "Prefix" ? "selected" : ""}>Prefix</option>
                        <option value="Suffix" ${valReg === "Suffix" ? "selected" : ""}>Suffix</option>
                      </select>
                      <button type="button" class="btn btn-xs btn-danger" onclick="window.removeAdvWorldbookEntry(${origIdx})">删除</button>
                    </div>
                    <textarea rows="3" class="form-textarea adv-wb-content" placeholder="命中关键词后动态注入的设定内容（单条上限 40,000 字）">${escapeHtml(contentVal)}</textarea>
                  </div>
                `;
              }).join("")
          }
        </div>
      </div>
    `;
  } else {
    const scopedPreviewCss = scopeProjectCss(customCssVal, "#advCssLivePreviewStage");
    tabContentHtml = `
      <!-- 1. 电脑与移动设备背景图 -->
      <div class="studio-section-card" style="margin:0;">
        <div class="studio-section-header">
          <div class="studio-section-title">聊天背景设置</div>
          <span style="font-size:11.5px;color:var(--text-muted);">电脑横屏与手机竖屏自动切换适配</span>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(290px, 1fr));gap:12px;">
          <div>
            <label class="gc-field-label">背景图（电脑横屏 16:9）</label>
            <div style="display:flex;align-items:center;gap:8px;">
              <div class="studio-preview-box" style="width:64px;height:40px;border-radius:7px;display:flex;align-items:center;justify-content:center;flex-shrink:0;overflow:hidden;font-size:11px;color:var(--text-dim);">
                ${bgUrl ? `<img src="${escapeHtml(bgUrl)}" alt="背景" style="width:100%;height:100%;object-fit:cover;cursor:pointer;" onclick="window.previewCgImage('${escapeJsAttr(bgUrl)}')" />` : "默认"}
              </div>
              <div class="ai-fused-input-group has-value" style="flex:1;min-width:0;">
                <input type="text" id="advBgImageInput" class="ai-fused-input" value="${escapeHtml(bgUrl)}" placeholder="图片 URL 或上传" style="flex:1;min-width:0;" />
                ${bgUrl ? `<button type="button" class="ai-fused-sub-btn" onclick="window.clearAdvancedBackground(false)">清除</button>` : ""}
                <button type="button" class="ai-fused-sub-btn" onclick="window.pickAdvancedGalleryAsset('bg_image')">使用图库图片</button>
                <button type="button" class="ai-fused-sub-btn" onclick="document.getElementById('advProjBgFileInput').click()">传图</button>
              </div>
              <input type="file" id="advProjBgFileInput" accept="image/*" style="display:none;" onchange="window.handleUploadProjectBackground(event, 'advanced')" />
            </div>
          </div>

          <div>
            <label class="gc-field-label">移动设备背景图（竖屏 9:16）</label>
            <div style="display:flex;align-items:center;gap:8px;">
              <div class="studio-preview-box" style="width:38px;height:46px;border-radius:7px;display:flex;align-items:center;justify-content:center;flex-shrink:0;overflow:hidden;font-size:11px;color:var(--text-dim);">
                ${bgMobileUrl ? `<img src="${escapeHtml(bgMobileUrl)}" alt="手机背景" style="width:100%;height:100%;object-fit:cover;cursor:pointer;" onclick="window.previewCgImage('${escapeJsAttr(bgMobileUrl)}')" />` : "竖屏"}
              </div>
              <div class="ai-fused-input-group has-value" style="flex:1;min-width:0;">
                <input type="text" id="advBgMobileInput" class="ai-fused-input" value="${escapeHtml(bgMobileUrl)}" placeholder="竖屏图片 URL 或上传" style="flex:1;min-width:0;" />
                ${bgMobileUrl ? `<button type="button" class="ai-fused-sub-btn" onclick="window.clearAdvancedBackground(true)">清除</button>` : ""}
                <button type="button" class="ai-fused-sub-btn" onclick="window.pickAdvancedGalleryAsset('bg_mobile')">使用图库图片</button>
                <button type="button" class="ai-fused-sub-btn" onclick="document.getElementById('advProjBgMobileFileInput').click()">传图</button>
              </div>
              <input type="file" id="advProjBgMobileFileInput" accept="image/*" style="display:none;" onchange="window.handleUploadProjectMobileBackground(event, 'advanced')" />
            </div>
          </div>
        </div>
      </div>

      <!-- 2. ★ 内置 CSS 栏（官方风格模板 + 代码编辑 + 实时预览台） -->
      <div class="studio-section-card" style="margin:0;border-color:rgba(212,166,90,0.36);">
        <div class="studio-section-header" style="flex-wrap:wrap;gap:8px;">
          <div style="display:flex;align-items:center;gap:8px;">
            <div class="studio-section-title" style="color:var(--lp-accent, #fcd34d);">内置 CSS</div>
            <span id="advCssCharCounter" class="adv-char-counter">${customCssVal.length} 字</span>
          </div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;">
            <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.insertAdvCustomUiExample()">+ 插入 .custom-ui 样式骨架</button>
            ${customCssVal.trim() ? `<button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.applyAdvCssPreset('')">清空 CSS</button>` : ""}
          </div>
        </div>

        <div class="adv-css-preset-bar">
          <span style="font-size:12px;font-weight:600;color:var(--text-muted);">官方模板：</span>
          ${Object.entries(OFFICIAL_CSS_PRESETS).map(([pKey, pCfg]) => {
            const isAct = customCssVal.trim() === pCfg.css.trim();
            return `<button type="button" class="adv-css-preset-chip ${isAct ? "active" : ""}" onclick="window.applyAdvCssPreset('${escapeJsAttr(pKey)}')">${escapeHtml(pCfg.label)}</button>`;
          }).join("")}
        </div>

        <textarea id="advCustomCssInput" rows="8" class="form-textarea adv-code-editor" placeholder="/* 在此编写作品专属内置 CSS，系统会自动将其安全隔离在聊天舞台内，随 PNG/JSON 游戏卡一并分享导出 */\n.custom-ui {\n  padding: 12px 16px;\n  border-radius: 10px;\n  border: 1px solid rgba(212, 166, 90, 0.45);\n}" oninput="window.refreshAdvCssLivePreview(this.value)">${escapeHtml(customCssVal)}</textarea>

        <!-- 内置 CSS 实时渲染预览窗 -->
        <div id="advCssLivePreviewStage" class="adv-css-preview-stage">
          <style id="advCssPreviewScopedStyle">${scopedPreviewCss}</style>
          <div style="font-size:11px;color:var(--text-dim);margin-bottom:8px;display:flex;justify-content:space-between;">
            <span>内置 CSS 实时效果预览（自动对应聊天区 <code>.message-row.assistant .bubble</code> 与自定义块 <code>.custom-ui</code>）</span>
          </div>
          <div class="message-item message-row assistant" style="margin:0;">
            <div class="bubble markdown-body chat-answer-container" style="padding:14px 18px;max-width:100%;">
              <details open>
                <summary>SYSTEM TERMINAL</summary>
                <p style="margin:0 0 8px 0;">推开尘封的橡木门，<em>微光</em>映亮了桌案上的卷宗，<code>HP: 100/100</code>。</p>
                <blockquote>当前阶段：【潜入阶段】 · 任务进展正常</blockquote>
              </details>
              <div class="custom-ui">【自定义状态界面 .custom-ui】生命 100/100 · 理智 85/100</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 3. 正则脚本 -->
      <div class="studio-section-card" style="margin:0;">
        <div class="studio-section-header" style="flex-wrap:wrap;gap:6px;">
          <div class="studio-section-title">正则脚本 <span class="adv-char-counter">(${rxList.length})</span></div>
          <button type="button" class="btn btn-xs btn-primary" onclick="window.addAdvRegexRule()">+ 新增正则脚本</button>
        </div>
        <div style="font-size:11.5px;color:var(--text-muted);margin-bottom:8px;">
          可将 AI 输出内容中匹配正则表达式的文本自动替换为自定义文本或 HTML UI 卡片（勾选「仅渲染」时只美化前端显示，不污染历史上下文）。
        </div>
        <div id="advRegexList" style="display:flex;flex-direction:column;gap:8px;">
          ${rxList.length === 0
            ? `<div style="padding:12px;border:1px dashed var(--border-subtle);border-radius:8px;text-align:center;color:var(--text-dim);font-size:12px;">暂无正则替换规则</div>`
            : rxList.map((rx, idx) => {
                const pat = rx.pattern ?? rx.find_regex ?? rx.regex ?? "";
                const rep = rx.replacement ?? rx.replace_str ?? rx.replace ?? "";
                const sc = (rx.scope === 2 || rx.scope === "user") ? "user" : ((rx.scope === "both" || rx.scope === 3) ? "both" : "assistant");
                const en = rx.enabled !== false;
                const ro = rx.is_only_render !== false;
                return `
                  <div class="adv-rx-item" data-rx-id="${escapeHtml(rx.id || `rx_${idx + 1}`)}" style="padding:9px 11px;border-radius:8px;border:1px solid var(--border-subtle);background:rgba(255,255,255,0.025);display:flex;flex-direction:column;gap:6px;">
                    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                      <label class="checkbox-label" style="font-size:12px;margin:0;">
                        <input type="checkbox" class="adv-rx-enabled" ${en ? "checked" : ""} />
                        <span>启用</span>
                      </label>
                      <input type="text" class="form-input adv-rx-name" value="${escapeHtml(rx.name || `规则 #${idx + 1}`)}" placeholder="规则名称" style="width:135px;padding:3px 8px;font-size:12px;" />
                      <select class="form-select adv-rx-scope" style="width:auto;padding:2px 20px 2px 8px;height:26px;font-size:11.5px;">
                        <option value="assistant" ${sc === "assistant" ? "selected" : ""}>仅 AI 输出</option>
                        <option value="user" ${sc === "user" ? "selected" : ""}>仅玩家输入</option>
                        <option value="both" ${sc === "both" ? "selected" : ""}>双向生效</option>
                      </select>
                      <label class="checkbox-label" style="font-size:11.5px;margin:0;" title="仅在前端渲染时替换（支持替换为 HTML + 内置 CSS 卡片），不改写数据库原文">
                        <input type="checkbox" class="adv-rx-renderonly" ${ro ? "checked" : ""} />
                        <span>仅渲染替换 (支持 HTML)</span>
                      </label>
                      <button type="button" class="btn btn-xs btn-danger" style="margin-left:auto;" onclick="window.removeAdvRegexRule(${idx})">删除</button>
                    </div>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                      <input type="text" class="form-input adv-rx-pattern" value="${escapeHtml(pat)}" placeholder="匹配正则表达式（如 /\\[状态:(.*?)\\]/g）" style="font-family:monospace;font-size:12px;" />
                      <input type="text" class="form-input adv-rx-replacement" value="${escapeHtml(rep)}" placeholder="替换文本或 HTML（如 <div class='custom-ui'>$1</div>）" style="font-family:monospace;font-size:12px;" />
                    </div>
                  </div>
                `;
              }).join("")
          }
        </div>
      </div>

      <!-- 4. CG 图片触发 (0/20) -->
      <div class="studio-section-card" style="margin:0;">
        <div class="studio-section-header" style="flex-wrap:wrap;gap:8px;">
          <div class="studio-section-title">CG 图片触发 <span class="adv-char-counter">（已设置特殊 CG 个数：${cgList.length} / 20）</span></div>
          <button type="button" class="btn btn-xs btn-primary" onclick="window.addAdvCgEntry()">+ 新增特殊 CG</button>
        </div>

        <div class="adv-default-bar" style="margin-bottom:10px;">
          <b style="color:var(--text-main);">CG 图片默认样式：</b>
          <span>触发区域</span>
          <select id="advCgDefSource" class="form-select" style="width:auto;padding:2px 20px 2px 8px;height:25px;font-size:11.5px;">
            <option value="ai" ${cgDefs.trigger_source !== "both" ? "selected" : ""}>仅 AI 回复</option>
            <option value="both" ${cgDefs.trigger_source === "both" ? "selected" : ""}>玩家 + AI</option>
          </select>
          <span>格式</span>
          <select id="advCgDefMatch" class="form-select" style="width:auto;padding:2px 20px 2px 8px;height:25px;font-size:11.5px;">
            <option value="OR" ${cgDefs.match_type !== "AND" ? "selected" : ""}>或 OR (任一命中)</option>
            <option value="AND" ${cgDefs.match_type === "AND" ? "selected" : ""}>与 AND (全部命中)</option>
          </select>
          <span>区域映射</span>
          <select id="advCgDefDisplay" class="form-select" style="width:auto;padding:2px 20px 2px 8px;height:25px;font-size:11.5px;">
            <option value="chat" ${cgDefs.display_mode !== "background" ? "selected" : ""}>聊天消息插图</option>
            <option value="background" ${cgDefs.display_mode === "background" ? "selected" : ""}>切换聊天背景图</option>
          </select>
        </div>

        <div id="advCgList" style="display:flex;flex-direction:column;gap:8px;">
          ${cgList.length === 0
            ? `<div style="padding:12px;border:1px dashed var(--border-subtle);border-radius:8px;text-align:center;color:var(--text-dim);font-size:12px;">暂无特殊 CG（支持本地上传或使用图库图片，命中关键词自动弹出插画或切换背景）</div>`
            : cgList.map((cg, idx) => {
                const imgUrl = cg.image_url || cg.url || "";
                const kStr = Array.isArray(cg.keys) ? cg.keys.join(", ") : String(cg.keys || "");
                return `
                  <div class="adv-cg-item gc-cg-card" data-cg-id="${escapeHtml(cg.id || `cg_${idx + 1}`)}" data-img-url="${escapeHtml(imgUrl)}">
                    <div class="gc-cg-thumb" onclick="document.getElementById('advCgFile_${idx}').click()" title="点击上传本地 CG">
                      <input type="file" id="advCgFile_${idx}" accept="image/*" style="display:none;" onchange="window.handleUploadAdvCgFile(event, ${idx})" />
                      ${imgUrl ? `<img src="${escapeHtml(imgUrl)}" alt="CG" />` : `<span>+ 传图</span>`}
                    </div>
                    <div style="flex:1;min-width:220px;display:flex;flex-direction:column;gap:6px;">
                      <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
                        <input type="text" class="form-input adv-cg-name" style="width:125px;padding:4px 8px;font-size:12px;" value="${escapeHtml(cg.name || "")}" placeholder="CG 名称" />
                        <input type="text" class="form-input adv-cg-keys" style="flex:1;min-width:140px;padding:4px 8px;font-size:12px;" value="${escapeHtml(kStr)}" placeholder="触发关键词（逗号分隔）" />
                        <input type="text" class="form-input adv-cg-url" style="width:150px;padding:4px 8px;font-size:11.5px;" value="${escapeHtml(imgUrl)}" placeholder="图片 URL" />
                        <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.pickAdvancedGalleryAsset('cg', ${idx})">图库</button>
                        <button type="button" class="btn btn-xs btn-danger" onclick="window.removeAdvCgEntry(${idx})">✕</button>
                      </div>
                      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:11.5px;color:var(--text-muted);">
                        <span>触发区域:</span>
                        <select class="form-select adv-cg-source" style="width:auto;padding:2px 20px 2px 6px;height:24px;font-size:11.5px;">
                          <option value="ai" ${cg.trigger_source !== "both" ? "selected" : ""}>仅 AI</option>
                          <option value="both" ${cg.trigger_source === "both" ? "selected" : ""}>玩家+AI</option>
                        </select>
                        <span>格式:</span>
                        <select class="form-select adv-cg-match" style="width:auto;padding:2px 20px 2px 6px;height:24px;font-size:11.5px;">
                          <option value="OR" ${cg.match_type !== "AND" ? "selected" : ""}>或 OR</option>
                          <option value="AND" ${cg.match_type === "AND" ? "selected" : ""}>与 AND</option>
                        </select>
                        <span>区域映射:</span>
                        <select class="form-select adv-cg-display" style="width:auto;padding:2px 20px 2px 6px;height:24px;font-size:11.5px;">
                          <option value="chat" ${cg.display_mode !== "background" ? "selected" : ""}>聊天插图</option>
                          <option value="background" ${cg.display_mode === "background" ? "selected" : ""}>切换背景</option>
                        </select>
                      </div>
                    </div>
                  </div>
                `;
              }).join("")
          }
        </div>
      </div>

      <!-- 5. 预设对话开场白 & 快捷回复指令 -->
      <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(320px, 1fr));gap:12px;">
        <div class="studio-section-card" style="margin:0;">
          <div class="studio-section-header" style="flex-wrap:wrap;gap:6px;">
            <div class="studio-section-title">预设对话开场白 <span class="adv-char-counter">(${(d.opening_greetings || []).length})</span></div>
            <button type="button" class="btn btn-xs btn-primary" onclick="window.addAdvOpeningGreeting()">+ 新增开场白</button>
          </div>
          <div id="advOpeningGreetingsList" style="display:flex;flex-direction:column;gap:8px;">
            ${Array.isArray(d.opening_greetings) && d.opening_greetings.length > 0
              ? d.opening_greetings.map((og, idx) => {
                  const titleVal = typeof og === "object" ? (og.title || "") : "";
                  const contentVal = typeof og === "string" ? og : (og.content || og.text || "");
                  const ogId = (typeof og === "object" && og.id) ? og.id : `og_${idx + 1}`;
                  return `
                    <div class="adv-opening-greeting-item" data-og-id="${escapeHtml(ogId)}" style="display:flex;flex-direction:column;gap:6px;padding:8px 10px;border-radius:8px;border:1px solid var(--border-subtle);background:rgba(128,128,128,0.05);">
                      <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                        <span style="font-size:11.5px;font-weight:700;color:var(--lp-accent,#fcd34d);">#${idx + 1}</span>
                        <input type="text" class="form-input adv-og-title" value="${escapeHtml(titleVal)}" placeholder="分支标题" style="flex:1;min-width:100px;padding:3px 8px;font-size:12px;" />
                        <div class="ai-fused-input-group">
                          <input type="text" id="advHint_og_${idx}" class="ai-fused-input adv-og-hint" style="width:105px;" placeholder="想法" oninput="this.parentElement.classList.toggle('has-value', !!this.value.trim())" />
                          <button type="button" class="ai-fused-btn" onclick="window.polishAdvOpeningGreeting(${idx}, this, 'advHint_og_${idx}')">润色</button>
                        </div>
                        <button type="button" class="btn btn-xs btn-danger" onclick="window.removeAdvOpeningGreeting(${idx})">✕</button>
                      </div>
                      <textarea rows="3" class="form-textarea adv-og-content" placeholder="开场白正文...">${escapeHtml(contentVal)}</textarea>
                    </div>
                  `;
                }).join("")
              : `<div style="padding:12px;border-radius:8px;border:1px dashed var(--border-subtle);color:var(--text-dim);font-size:12px;text-align:center;">暂无预设开场白</div>`
            }
          </div>
        </div>

        <div class="studio-section-card" style="margin:0;">
          <div class="studio-section-header" style="flex-wrap:wrap;gap:6px;">
            <div class="studio-section-title">快捷回复指令 <span class="adv-char-counter">(${qrList.length} / 10)</span></div>
            <button type="button" class="btn btn-xs btn-primary" onclick="window.addAdvQuickReply()">+ 新增快捷指令</button>
          </div>
          <div style="font-size:11.5px;color:var(--text-muted);margin-bottom:8px;">设置快捷按钮或 <code>/指令</code>，玩家点击按钮或输入指令即可快速发送预设内容给 AI。</div>
          <div id="advQuickRepliesList" style="display:flex;flex-direction:column;gap:8px;">
            ${qrList.length === 0
              ? `<div style="padding:12px;border-radius:8px;border:1px dashed var(--border-subtle);color:var(--text-dim);font-size:12px;text-align:center;">最多可添加 0/10 个快捷命令</div>`
              : qrList.map((qr, idx) => `
                  <div class="adv-qr-item" data-qr-id="${escapeHtml(qr.id || `qr_${idx + 1}`)}" style="display:flex;flex-direction:column;gap:5px;padding:8px 10px;border-radius:8px;border:1px solid var(--border-subtle);background:rgba(128,128,128,0.05);">
                    <div style="display:flex;gap:6px;align-items:center;">
                      <input type="text" class="form-input adv-qr-label" value="${escapeHtml(qr.label || "")}" placeholder="按钮显示名 (如: 观察四周)" style="flex:1;padding:3px 8px;font-size:12px;" />
                      <input type="text" class="form-input adv-qr-cmd" value="${escapeHtml(qr.command || "")}" placeholder="/指令词 (选填)" style="width:110px;padding:3px 8px;font-size:12px;font-family:monospace;" />
                      <button type="button" class="btn btn-xs btn-danger" onclick="window.removeAdvQuickReply(${idx})">✕</button>
                    </div>
                    <input type="text" class="form-input adv-qr-content" value="${escapeHtml(qr.content || "")}" placeholder="发送给 AI 的预设内容（如：我仔细观察周围环境的异常细节与可疑人物）" style="padding:4px 8px;font-size:12px;" />
                  </div>
                `).join("")
            }
          </div>
        </div>
      </div>

      <!-- 6. 默认记忆长度与采样参数 -->
      <div class="studio-section-card" style="margin:0;">
        <div class="studio-section-header">
          <div class="studio-section-title" style="display:flex;align-items:center;gap:6px;">
            <span>默认记忆长度与采样参数</span>
            ${hasModelOverride ? `<span class="wb-badge" style="color:var(--tc-fcd34d, #fcd34d);font-size:11px;">已被模型独立参数覆盖</span>` : ""}
          </div>
          <label class="checkbox-label" style="font-size:0.78rem;font-weight:600;color:${useGlobal ? "var(--tc-34d399, #34d399)" : "var(--text-main)"};${hasModelOverride ? "opacity:0.45;pointer-events:none;" : ""}">
            <input type="checkbox" id="advUseGlobalParams" ${useGlobal ? "checked" : ""} ${hasModelOverride ? "disabled" : ""} onchange="window.toggleAdvUseGlobalParams(this.checked)" />
            <span>跟随全局参数</span>
          </label>
        </div>

        <div class="numeric-params-grid" style="${isParamsLocked ? "opacity:0.45;pointer-events:none;filter:grayscale(0.65);user-select:none;" : ""}">
          <div class="param-slider-row context-integrated-card" style="grid-column: 1 / -1;">
            <div class="param-slider-header" style="gap:8px;margin-bottom:6px;">
              <span>默认记忆模式</span>
              <select id="advContextMode" ${disabledAttr} class="form-select" style="width:auto;padding:2px 8px;font-size:12px;height:26px;" onchange="window.updateAdvContextMode(this.value)">
                <option value="turns" ${cp.context_mode !== "tokens" ? "selected" : ""}>按对话轮数</option>
                <option value="tokens" ${cp.context_mode === "tokens" ? "selected" : ""}>按 Token 上限</option>
              </select>
            </div>
            <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(195px, 1fr));gap:12px;align-items:start;">
              <div style="${cp.context_mode === "tokens" ? "display:none;" : ""}">
                <div class="param-slider-header">
                  <span style="font-size:12px;color:var(--text-muted);">默认记忆轮数</span>
                  <input type="number" ${disabledAttr} class="param-num-input" id="advNum_context" min="2" max="200" step="1" value="${ctxTurns}" oninput="window.updateAdvCompletionParam('context', Number(this.value))" />
                </div>
                <input type="range" ${disabledAttr} id="advRange_context" min="2" max="200" step="1" value="${ctxTurns}" oninput="window.updateAdvCompletionParam('context', Number(this.value))" />
                <small class="param-item-hint">保留最近 <b id="advContextMsgsCalc">${ctxTurns * 2}</b> 条消息</small>
              </div>
              <div>
                <div class="param-slider-header">
                  <span style="font-size:12px;color:var(--text-muted);">上下文上限 (k)</span>
                  <input type="number" ${disabledAttr} class="param-num-input" id="advNum_max_context_k" min="4" max="512" step="4" value="${cp.max_context_k ?? 96}" oninput="window.updateAdvCompletionParam('max_context_k', Number(this.value))" />
                </div>
                <input type="range" ${disabledAttr} id="advRange_max_context_k" min="4" max="512" step="4" value="${cp.max_context_k ?? 96}" oninput="window.updateAdvCompletionParam('max_context_k', Number(this.value))" />
                <small class="param-item-hint">单位 k</small>
              </div>
            </div>
          </div>

          <div class="param-slider-row">
            <div class="param-slider-header">
              <span>温度</span>
              <input type="number" ${disabledAttr} class="param-num-input" id="advNum_temperature" min="0" max="2.0" step="0.05" value="${Number(cp.temperature ?? 0.68).toFixed(2)}" oninput="window.updateAdvCompletionParam('temperature', Number(this.value))" />
            </div>
            <input type="range" ${disabledAttr} id="advRange_temperature" min="0" max="2.0" step="0.05" value="${cp.temperature ?? 0.68}" oninput="window.updateAdvCompletionParam('temperature', Number(this.value))" />
          </div>

          <div class="param-slider-row">
            <div class="param-slider-header">
              <span>Top-P</span>
              <input type="number" ${disabledAttr} class="param-num-input" id="advNum_top_p" min="0.1" max="1.0" step="0.05" value="${Number(cp.top_p ?? 0.90).toFixed(2)}" oninput="window.updateAdvCompletionParam('top_p', Number(this.value))" />
            </div>
            <input type="range" ${disabledAttr} id="advRange_top_p" min="0.1" max="1.0" step="0.05" value="${cp.top_p ?? 0.90}" oninput="window.updateAdvCompletionParam('top_p', Number(this.value))" />
          </div>

          <div class="param-slider-row">
            <div class="param-slider-header">
              <span>最大输出</span>
              <input type="number" ${disabledAttr} class="param-num-input" id="advNum_max_tokens" min="256" max="65536" step="256" value="${cp.max_tokens ?? 8192}" oninput="window.updateAdvCompletionParam('max_tokens', Number(this.value))" />
            </div>
            <input type="range" ${disabledAttr} id="advRange_max_tokens" min="256" max="65536" step="256" value="${cp.max_tokens ?? 8192}" oninput="window.updateAdvCompletionParam('max_tokens', Number(this.value))" />
          </div>

          <div class="param-slider-row">
            <div class="param-slider-header">
              <span>思考预算</span>
              <input type="number" ${disabledAttr} class="param-num-input" id="advNum_thinking_budget" min="0" max="65536" step="256" value="${cp.thinking_budget ?? 1024}" oninput="window.updateAdvCompletionParam('thinking_budget', Number(this.value))" />
            </div>
            <input type="range" ${disabledAttr} id="advRange_thinking_budget" min="0" max="65536" step="256" value="${cp.thinking_budget ?? 1024}" oninput="window.updateAdvCompletionParam('thinking_budget', Number(this.value))" />
          </div>
        </div>

        <div style="margin-top:10px;padding-top:8px;border-top:1px solid rgba(255,255,255,0.06);">
          <label class="checkbox-label" style="font-size:0.78rem;">
            <input type="checkbox" id="advAutoSummarize" ${d.auto_summarize !== false ? "checked" : ""} />
            <span>超限自动压缩前情记忆</span>
          </label>
        </div>
      </div>
    `;
  }

  body.innerHTML = `
    <div style="display:flex;flex-direction:column;gap:12px;">
      <!-- 顶部导航 + 三栏切换 (基础设置 / 世界书设置 / 其他设置) + AI 润色与导出栏 -->
      <div class="studio-section-card" style="margin:0;padding:10px 14px;background:linear-gradient(135deg,rgba(212,166,90,0.11),rgba(255,255,255,0.02));border-color:rgba(212,166,90,0.32);">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
          <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
            <button type="button" class="btn btn-xs btn-secondary" onclick="window.backToExploreCardList()">← 游戏卡库</button>
            <span class="proj-tier-tag tier-advanced" style="padding:3px 9px;font-size:11px;">高级游戏卡</span>
            <button type="button" class="btn btn-xs btn-outline-secondary" onclick="document.getElementById('globalGameCardImportInput')?.click()" title="导入酒馆或本工作台 .png/.json 游戏卡">导入游戏卡</button>
          </div>

          <div class="adv-studio-tabs" role="tablist">
            <button type="button" class="adv-studio-tab-btn ${currentAdvancedCreatorTab === "basic" ? "active" : ""}" onclick="window.switchAdvancedCreatorTab('basic')">
              <span>基础设置</span>
            </button>
            <button type="button" class="adv-studio-tab-btn ${currentAdvancedCreatorTab === "worldbook" ? "active" : ""}" onclick="window.switchAdvancedCreatorTab('worldbook')">
              <span>世界书设置</span>
              ${wbList.length > 0 ? `<span class="adv-tab-badge">${wbList.length}</span>` : ""}
            </button>
            <button type="button" class="adv-studio-tab-btn ${currentAdvancedCreatorTab === "other" ? "active" : ""}" onclick="window.switchAdvancedCreatorTab('other')">
              <span>其他设置 · CSS</span>
              ${otherExtCount > 0 ? `<span class="adv-tab-badge">${otherExtCount}</span>` : ""}
            </button>
          </div>

          <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
            <select id="advAiModelSelect" class="form-select ai-assist-model-select" style="width:auto;max-width:170px;padding:3px 22px 3px 8px;font-size:12px;height:28px;" onchange="window.handleAiAssistModelChange && window.handleAiAssistModelChange(this.value)" title="AI 润色模型"></select>
            <div class="ai-fused-input-group">
              <input type="text" id="advGlobalPolishInstruction" class="ai-fused-input" style="width:125px;" placeholder="润色想法" oninput="this.parentElement.classList.toggle('has-value', !!this.value.trim())" onkeydown="if(event.key==='Enter'){event.preventDefault();this.nextElementSibling.click();}" />
              <button type="button" id="btnPolishAllAdv" class="ai-fused-btn" onclick="window.polishAllAdvancedFields(this)">一键润色</button>
            </div>
            <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.exportDraftGameCard('advanced', 'png')" title="导出 PNG 海报游戏卡（兼容酒馆）">导出 PNG</button>
            <button type="button" class="btn btn-xs btn-outline-secondary" onclick="window.exportDraftGameCard('advanced', 'json')" title="导出 JSON 游戏卡">JSON</button>
            <button type="button" class="btn btn-sm btn-primary" style="font-weight:700;" onclick="window.submitAdvancedNewProject()">
              ${isEditingExisting ? "保存游戏卡" : "创建游戏卡"}
            </button>
          </div>
        </div>
      </div>

      ${tabContentHtml}

      <!-- 底部操作栏 -->
      <div style="display:flex;justify-content:space-between;align-items:center;padding-top:4px;flex-wrap:wrap;gap:8px;">
        <div style="display:flex;gap:6px;">
          <button type="button" class="btn btn-sm btn-secondary" onclick="window.backToExploreCardList()">返回卡库</button>
          ${currentAdvancedCreatorTab !== "basic" ? `<button type="button" class="btn btn-sm btn-outline-secondary" onclick="window.switchAdvancedCreatorTab('${currentAdvancedCreatorTab === "other" ? "worldbook" : "basic"}')">← 上一栏</button>` : ""}
          ${currentAdvancedCreatorTab !== "other" ? `<button type="button" class="btn btn-sm btn-outline-secondary" onclick="window.switchAdvancedCreatorTab('${currentAdvancedCreatorTab === "basic" ? "worldbook" : "other"}')">下一栏 →</button>` : ""}
        </div>
        <div style="display:flex;gap:8px;align-items:center;">
          <button type="button" class="btn btn-sm btn-outline-secondary" onclick="window.exportDraftGameCard('advanced', 'png')">导出 PNG 游戏卡</button>
          <button type="button" class="btn btn-sm btn-primary" style="padding:8px 20px;font-weight:700;" onclick="window.submitAdvancedNewProject()">
            ${isEditingExisting ? "保存并游玩" : "创建并游玩"}
          </button>
        </div>
      </div>
    </div>
  `;
  if (typeof window.syncAllAiAssistModelSelects === "function") {
    window.syncAllAiAssistModelSelects();
  }
  const modal = document.getElementById("exploreModal");
  if (typeof window.translateSubtree === "function") {
    window.translateSubtree(modal || body);
  }
  if (prevScrollTop > 0) {
    body.scrollTop = prevScrollTop;
    requestAnimationFrame(() => {
      body.scrollTop = prevScrollTop;
    });
  }
  if (parentEl && prevParentScroll > 0) {
    parentEl.scrollTop = prevParentScroll;
    requestAnimationFrame(() => {
      parentEl.scrollTop = prevParentScroll;
    });
  }
}

window.backToExploreCardList = function () {
  advancedDraftProject = null;
  return window.openExploreModal();
};

window.polishAdvancedField = async function (inputId, fieldType, btnEl, hintInputId = "") {
  syncAdvancedDraftFromDom();
  const el = document.getElementById(inputId);
  if (!el || !advancedDraftProject) return;
  const localHint = hintInputId ? (document.getElementById(hintInputId)?.value.trim() || "") : "";
  const globalHint = document.getElementById("advGlobalPolishInstruction")?.value.trim() || "";
  const instruction = [localHint, globalHint].filter(Boolean).join("；");
  const selectedModel = document.getElementById("advAiModelSelect")?.value || "";

  const origLabel = btnEl ? btnEl.innerHTML : "润色";
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.innerHTML = "润色中...";
  }
  try {
    const polished = await callAiPolishApi(el.value, fieldType, advancedDraftProject.name || "跑团游戏", instruction, selectedModel);
    el.value = polished;
    syncAdvancedDraftFromDom();
    showToast("已润色");
  } catch (err) {
    showToast("润色失败: " + err.message);
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.innerHTML = origLabel;
    }
  }
};

window.polishAllAdvancedFields = async function (btnEl) {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject) return;
  const instruction = document.getElementById("advGlobalPolishInstruction")?.value.trim() || "";
  const selectedModel = document.getElementById("advAiModelSelect")?.value || "";
  const isEn = window.currentAppLang === "en";

  if (!Array.isArray(advancedDraftProject.opening_greetings) || advancedDraftProject.opening_greetings.length === 0) {
    advancedDraftProject.opening_greetings = [
      {
        id: `og_${Date.now().toString(36)}`,
        title: "开场白 1",
        content: ""
      }
    ];
    renderAdvancedProjectEditor();
    const instrEl = document.getElementById("advGlobalPolishInstruction");
    if (instrEl && instruction) instrEl.value = instruction;
    btnEl = document.getElementById("btnPolishAllAdv") || btnEl;
  }

  const origLabel = btnEl ? btnEl.innerHTML : (isEn ? "Polish" : "润色");
  if (btnEl) {
    btnEl.disabled = true;
  }

  const ogCount = Array.isArray(advancedDraftProject.opening_greetings) ? advancedDraftProject.opening_greetings.length : 0;
  const totalSteps = 4 + ogCount;
  let curStep = 0;
  const setProgress = (stepLabel) => {
    curStep += 1;
    if (btnEl) {
      btnEl.innerHTML = isEn
        ? `Polishing (${curStep}/${totalSteps})...`
        : `润色中 (${curStep}/${totalSteps}) ${stepLabel}...`;
    }
  };

  try {
    const pName = advancedDraftProject.name || "新跑团游戏";

    // 1. 游戏简介
    setProgress("简介");
    const descHint = [document.getElementById("advHint_description")?.value.trim() || "", instruction].filter(Boolean).join("；");
    const newDesc = await callAiPolishApi(advancedDraftProject.description || "", "description", pName, descHint, selectedModel);
    advancedDraftProject.description = newDesc;
    const descEl = document.getElementById("advProjDesc");
    if (descEl) descEl.value = newDesc;

    const baseContextHint = [
      advancedDraftProject.description ? `游戏简介参考：${advancedDraftProject.description}` : "",
      instruction
    ].filter(Boolean).join("；");

    // 2. 开场白设置（全部开场白栏）
    if (Array.isArray(advancedDraftProject.opening_greetings)) {
      for (let i = 0; i < advancedDraftProject.opening_greetings.length; i++) {
        setProgress(`开场白 #${i + 1}`);
        const og = advancedDraftProject.opening_greetings[i];
        const titleInputs = document.querySelectorAll("#advOpeningGreetingsList .adv-og-title");
        const contentInputs = document.querySelectorAll("#advOpeningGreetingsList .adv-og-content");
        const curTitle = titleInputs[i] ? titleInputs[i].value.trim() : (og.title || `开场白 ${i + 1}`);
        const curContent = contentInputs[i] ? contentInputs[i].value : (og.content || "");
        const localOgHint = document.getElementById(`advHint_og_${i}`)?.value.trim() || "";
        const ogHint = [curTitle ? `开场白主题：${curTitle}` : "", localOgHint, baseContextHint].filter(Boolean).join("；");
        const newOgContent = await callAiPolishApi(curContent, "opening_greeting", pName, ogHint, selectedModel);
        og.content = newOgContent;
        if (contentInputs[i]) contentInputs[i].value = newOgContent;
      }
    }

    // 3. 前置提示词
    setProgress("前置");
    const preHint = [document.getElementById("advHint_prefix")?.value.trim() || "", baseContextHint].filter(Boolean).join("；");
    const newPre = await callAiPolishApi(advancedDraftProject.prefix || "", "prefix", pName, preHint, selectedModel);
    advancedDraftProject.prefix = newPre;
    const preEl = document.getElementById("advProjPrefix");
    if (preEl) preEl.value = newPre;

    // 4. 提示词 (System Prompt)
    setProgress("提示词");
    const sysHint = [document.getElementById("advHint_system_prompt")?.value.trim() || "", baseContextHint].filter(Boolean).join("；");
    const newSys = await callAiPolishApi(advancedDraftProject.system_prompt || "", "system_prompt", pName, sysHint, selectedModel);
    advancedDraftProject.system_prompt = newSys;
    const sysEl = document.getElementById("advProjSystem");
    if (sysEl) sysEl.value = newSys;

    // 5. 后置提示词
    setProgress("后置");
    const sufHint = [document.getElementById("advHint_suffix")?.value.trim() || "", baseContextHint].filter(Boolean).join("；");
    const newSuf = await callAiPolishApi(advancedDraftProject.suffix || "", "suffix", pName, sufHint, selectedModel);
    advancedDraftProject.suffix = newSuf;
    const sufEl = document.getElementById("advProjSuffix");
    if (sufEl) sufEl.value = newSuf;

    renderAdvancedProjectEditor();
    showToast("已润色全部");
  } catch (err) {
    showToast("润色失败: " + err.message);
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.innerHTML = origLabel;
    }
  }
};

window.submitAdvancedNewProject = async function () {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject) return;
  if (advancedDraftProject.status_panel_enabled !== false) {
    ensureActiveStatusModulesOnEnable(advancedDraftProject);
  }
  const d = JSON.parse(JSON.stringify(advancedDraftProject));
  delete d._sourceName;
  d.card_tier = "advanced";
  d.simple_mode = false;
  if (["极速跑团", "简单跑团"].includes(String(d.category || "").trim())) {
    d.category = "";
  }
  const isUpdatingExisting = Boolean(d.id && !["proj_fast_trpg", "proj_default", "proj_free_chat"].includes(d.id));

  try {
    let savedProj = null;
    let newChatId = null;
    if (isUpdatingExisting) {
      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(d)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "保存失败");
      savedProj = data.project;
    } else {
      const res = await fetch("/api/projects/fork", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project: d,
          keep_exact_name: true
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "创建失败");
      savedProj = data.project;
      newChatId = data.chat_id || null;
    }

    const modal = document.getElementById("exploreModal");
    if (modal) modal.style.display = "none";

    window._welcomeModeStepSelected = true;
    currentProjectId = savedProj.id;
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active_project_id: currentProjectId })
    });
    await loadProjects();
    if (newChatId) {
      currentChatId = newChatId;
      await loadChats();
      await switchChat(newChatId);
    } else {
      await loadChats();
    }
    applyProjectAppearance(getActiveProjectObj());
    if (typeof window.renderWelcomeBox === "function") {
      window.renderWelcomeBox();
    }
    const pane = document.getElementById("studioWorkbenchPane");
    if (pane && pane.style.display !== "none") {
      renderStudioWorkbench();
    }
    showToast(isUpdatingExisting ? `已保存游戏卡：${savedProj.name}` : `已创建游戏卡：${savedProj.name}`);
  } catch (err) {
    showToast((isUpdatingExisting ? "保存失败: " : "创建失败: ") + err.message);
  }
};

window.installExploreApp = window.quickForkProjectDirect;

// =========================================================================
// 6. 提示词日志弹窗
// =========================================================================
window.openPromptLogModal = async function () {
  const modal = document.getElementById("promptLogModal");
  const body = document.getElementById("promptLogModalBody");
  if (!modal || !body) return;
  modal.style.display = "flex";

  if (!currentChatId) {
    body.innerHTML = `<div style="padding:20px;color:var(--text-muted);">未选择对话</div>`;
    if (typeof window.translateSubtree === "function") window.translateSubtree(modal);
    return;
  }

  body.innerHTML = `<div style="padding:20px;color:var(--text-muted);">读取中...</div>`;
  if (typeof window.translateSubtree === "function") window.translateSubtree(modal);
  try {
    const res = await fetch(`/api/chats/${currentChatId}/prompt_log`);
    const data = await res.json();
    const log = data.prompt_log || {};
    if (!log.timestamp) {
      body.innerHTML = `<div style="padding:24px;text-align:center;color:var(--text-muted);">暂无记录</div>`;
      if (typeof window.translateSubtree === "function") window.translateSubtree(modal);
      return;
    }

    const timeStr = new Date(log.timestamp * 1000).toLocaleString("zh-CN", { hour12: false });

    body.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:12px;">
        <div class="studio-section-card" style="margin:0;">
          <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;font-size:0.8rem;">
            <span>时间：<b>${escapeHtml(timeStr)}</b></span>
            <span>模型：<code>${escapeHtml(log.model || "")}</code></span>
          </div>
        </div>

        <div class="studio-section-card" style="margin:0;">
          <div class="studio-section-title" style="margin-bottom:8px;">模型参数</div>
          <pre class="prompt-log-pre">${escapeHtml(JSON.stringify(log.completion_params || {}, null, 2))}</pre>
        </div>

        <div class="studio-section-card" style="margin:0;">
          <div class="studio-section-title" style="margin-bottom:8px;">消息 (${(log.assembled_messages || []).length})</div>
          <div style="display:flex;flex-direction:column;gap:8px;max-height:360px;overflow-y:auto;">
            ${(log.assembled_messages || []).map((m, i) => `
              <div class="prompt-log-msg-card">
                <div class="prompt-log-role role-${escapeHtml(m.role || "user")}">
                  #${i + 1} [${escapeHtml((m.role || "").toUpperCase())}]
                </div>
                <pre style="white-space:pre-wrap;word-break:break-word;font-size:0.76rem;color:var(--text-main);margin:0;">${escapeHtml(typeof m.content === "string" ? m.content : JSON.stringify(m.content))}</pre>
              </div>
            `).join("")}
          </div>
        </div>
      </div>
    `;
    if (typeof window.translateSubtree === "function") window.translateSubtree(modal);
  } catch (err) {
    body.innerHTML = `<div style="padding:20px;color:var(--tc-f87171, #f87171);">读取失败: ${escapeHtml(err.message)}</div>`;
    if (typeof window.translateSubtree === "function") window.translateSubtree(modal);
  }
};

// =========================================================================
// 7. 对话分支与素材图库文件夹分类
// =========================================================================
window.createBranchFromMessage = async function (msgId) {
  if (!currentChatId) return;
  try {
    const res = await fetch(`/api/chats/${currentChatId}/branch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message_id: msgId, up_to_msg_id: msgId })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "创建分支失败");
    await loadChats();
    if (data.chat?.id) {
      await switchChat(data.chat.id);
    }
    showToast("已创建分支");
  } catch (err) {
    showToast("创建分支失败: " + err.message);
  }
};

function renderGalleryFolderPills() {
  const pillsWrap = document.getElementById("galleryFoldersPills");
  if (!pillsWrap) return;
  const cur = window.currentGalleryFolder || "ALL";
  pillsWrap.innerHTML = `
    <button type="button" class="wb-group-pill ${cur === "ALL" ? "active" : ""}" onclick="window.filterGalleryByFolder('ALL')">全部</button>
    ${galleryFoldersList.map((f) => `<button type="button" class="wb-group-pill ${cur === f ? "active" : ""}" onclick="window.filterGalleryByFolder('${escapeJsAttr(f)}')">${escapeHtml(f)}</button>`).join("")}
  `;
  if (typeof window.translateSubtree === "function") window.translateSubtree(pillsWrap);
}

async function syncGalleryFoldersFromBackend() {
  try {
    const res = await fetch("/api/gallery/folders");
    if (!res.ok) return;
    const data = await res.json();
    if (Array.isArray(data.folders) && data.folders.length) {
      const names = data.folders.map((f) => (typeof f === "string" ? f : f.name || f.id)).filter(Boolean);
      if (names.length) {
        galleryFoldersList = Array.from(new Set(names));
        renderGalleryFolderPills();
      }
    }
  } catch (e) {}
}

function injectGalleryEnterpriseToolbar() {
  const modal = document.getElementById("galleryModal");
  if (!modal || document.getElementById("galleryEnterpriseBar")) return;
  const grid = document.getElementById("galleryGrid");
  if (!grid || !grid.parentNode) return;

  const bar = document.createElement("div");
  bar.id = "galleryEnterpriseBar";
  bar.className = "gallery-enterprise-bar";
  bar.innerHTML = `
    <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;" id="galleryFoldersPills"></div>
  `;
  grid.parentNode.insertBefore(bar, grid);
  renderGalleryFolderPills();
  syncGalleryFoldersFromBackend();
}

window.filterGalleryByFolder = function (folderName) {
  window.currentGalleryFolder = folderName;
  renderGalleryFolderPills();
  if (typeof renderGalleryGrid === "function") {
    renderGalleryGrid();
  }
};

// =========================================================================
// 8. Hook 挂载与初始化
// =========================================================================
function setupEnterpriseHooks() {
  // 8.1 为每条消息操作栏增加【分支】按钮
  if (typeof window.appendMessageElement === "function" && !window._origAppendMessageElement) {
    window._origAppendMessageElement = window.appendMessageElement;
    window.appendMessageElement = function (msg) {
      const bubble = window._origAppendMessageElement(msg);
      try {
        const item = bubble?.closest(".message-item");
        const actionBar = item?.querySelector(".msg-action-bar");
        if (actionBar && !actionBar.querySelector(".btn-msg-branch")) {
          const isEn = window.currentAppLang === "en";
          const btnBranch = document.createElement("button");
          btnBranch.type = "button";
          btnBranch.className = "msg-tool-btn btn-msg-branch";
          btnBranch.innerHTML = isEn ? "Branch" : "分支";
          btnBranch.title = isEn ? "Branch from here" : "从此处分支";
          btnBranch.onclick = () => {
            const currentMsgId = item.dataset.msgId || msg.id;
            window.createBranchFromMessage(currentMsgId);
          };
          actionBar.appendChild(btnBranch);
        }
      } catch (e) {}
      return bubble;
    };
  }

  // 8.2 切换游戏时同步刷新游戏设置面板与背景
  if (typeof window.switchProject === "function" && !window._origSwitchProject) {
    window._origSwitchProject = window.switchProject;
    window.switchProject = async function (projId) {
      const ok = await window._origSwitchProject(projId);
      const proj = getActiveProjectObj();
      applyProjectAppearance(proj);
      renderChatVariablesBar();
      const pane = document.getElementById("studioWorkbenchPane");
      // 原 switchProject 已在面板打开时重渲染工作台，这里不再重复渲染，仅同步地址栏
      if (ok !== false && pane && pane.style.display !== "none") {
        if (window.history && window.history.replaceState) {
          window.history.replaceState({}, "", `/zh/app/${encodeURIComponent(currentProjectId || projId)}/configuration`);
        }
      }
      return ok;
    };
  }

  // 8.3 注入图库文件夹栏
  injectGalleryEnterpriseToolbar();
}

async function checkInitialConfigurationRoute() {
  const path = window.location.pathname || "";
  const match = path.match(/\/(?:zh\/)?app\/([^/]+)\/configuration/i);
  let readyTries = 0;
  const MAX_READY_TRIES = 40; // 约 10 秒后放弃，避免 projectsMap 始终为空时无限轮询
  const checkReady = setInterval(async () => {
    readyTries++;
    if (readyTries > MAX_READY_TRIES) {
      clearInterval(checkReady);
      return;
    }
    if (projectsMap && Object.keys(projectsMap).length > 0) {
      clearInterval(checkReady);
      setupEnterpriseHooks();
      const proj = getActiveProjectObj();
      if (proj) applyProjectAppearance(proj);
      renderChatVariablesBar();

      if (match && match[1]) {
        const targetId = decodeURIComponent(match[1]);
        if (projectsMap[targetId]) {
          if (currentProjectId !== targetId) {
            await window.switchProject(targetId);
          }
          window.toggleStudioWorkbench(true);
        } else if (window.history && window.history.replaceState) {
          window.history.replaceState({}, "", "/");
        }
      }
    }
  }, 250);
}

window.addEventListener("DOMContentLoaded", () => {
  setTimeout(setupEnterpriseHooks, 150);
  checkInitialConfigurationRoute();
});

// =========================================================================
// 7. 简易创作向导 & 统一可分享游戏卡（Easy-TRPG <-> SillyTavern 酒馆双向导入/导出）
// =========================================================================
let guidedCardDraft = null;
const GUIDED_QUICK_TAGS = ["跑团", "奇幻冒险", "现代战术", "克苏鲁悬疑", "武侠仙侠", "赛博科幻", "末日求生", "日常群像"];

function createBlankGuidedDraft(defaultName = "新企划 #1") {
  return {
    id: "",
    step: 1,
    name: defaultName,
    icon: "",
    bg_image: "",
    bg_mobile: "",
    tags: [],
    description: "",
    set_initial_as_greeting: true,
    guided_meta: {
      idea_prompt: "",
      protagonist_name: "",
      protagonist_desc: "",
      protagonist_goal: "",
      world_name: "",
      world_era: "",
      world_conflict: "",
      world_tone: "",
      main_plot: "",
      initial_state: "",
      play_rules: "",
      status_preset: "none",
      npcs: []
    },
    cg_book: [],
    extra_raw_prompt: "",
    prefix: "",
    suffix: "",
    world_book: [],
    regex_scripts: [],
    existing_ui_modules: []
  };
}

function buildGuidedDraftFromProject(proj) {
  const p = normalizeProjectClient(JSON.parse(JSON.stringify(proj || {})));
  const gm = (p.guided_meta && typeof p.guided_meta === "object") ? p.guided_meta : {};
  const hasGuidedFields = Boolean(
    gm.protagonist_name || gm.protagonist_desc || gm.world_name || gm.world_era ||
    gm.world_conflict || gm.main_plot || gm.initial_state || gm.play_rules ||
    (Array.isArray(gm.npcs) && gm.npcs.length > 0)
  );
  const og0 = Array.isArray(p.opening_greetings) && p.opening_greetings[0]
    ? (typeof p.opening_greetings[0] === "string" ? p.opening_greetings[0] : (p.opening_greetings[0].content || ""))
    : (p.opening_statement || "");

  let detectedPreset = gm.status_preset || (p.status_panel_enabled ? "keep" : "none");
  return {
    id: p.id && !["proj_fast_trpg", "proj_default", "proj_free_chat"].includes(p.id) ? p.id : "",
    step: 1,
    name: p.name || "未命名游戏卡",
    icon: p.icon || p.avatar || "",
    bg_image: p.appearance?.bg_image || p.bg_image || "",
    bg_mobile: p.appearance?.bg_mobile || "",
    tags: Array.isArray(p.tags) ? [...p.tags] : [],
    description: p.description || "",
    set_initial_as_greeting: Boolean(og0) || gm.set_initial_as_greeting !== false,
    guided_meta: {
      idea_prompt: gm.idea_prompt || "",
      protagonist_name: gm.protagonist_name || "",
      protagonist_desc: gm.protagonist_desc || "",
      protagonist_goal: gm.protagonist_goal || "",
      world_name: gm.world_name || "",
      world_era: gm.world_era || "",
      world_conflict: gm.world_conflict || "",
      world_tone: gm.world_tone || "",
      main_plot: gm.main_plot || "",
      initial_state: gm.initial_state || og0 || "",
      play_rules: gm.play_rules || (!hasGuidedFields ? (p.system_prompt || "") : ""),
      status_preset: detectedPreset,
      npcs: Array.isArray(gm.npcs) ? gm.npcs.map((n) => ({ ...n })) : []
    },
    detailed_description: p.detailed_description || "",
    custom_css: p.custom_css || p.appearance?.custom_css || "",
    quick_replies: Array.isArray(p.quick_replies) ? JSON.parse(JSON.stringify(p.quick_replies)) : [],
    worldbook_defaults: p.worldbook_defaults ? { ...p.worldbook_defaults } : undefined,
    cg_defaults: p.cg_defaults ? { ...p.cg_defaults } : undefined,
    cg_book: Array.isArray(p.cg_book) ? JSON.parse(JSON.stringify(p.cg_book)) : [],
    extra_raw_prompt: gm.extra_raw_prompt || "",
    prefix: p.prefix || "",
    suffix: p.suffix || "",
    world_book: Array.isArray(p.world_book) ? JSON.parse(JSON.stringify(p.world_book)) : [],
    regex_scripts: Array.isArray(p.regex_scripts) ? JSON.parse(JSON.stringify(p.regex_scripts)) : [],
    existing_ui_modules: Array.isArray(p.ui_modules) ? JSON.parse(JSON.stringify(p.ui_modules)) : []
  };
}

function syncGuidedDraftFromDom() {
  if (!guidedCardDraft) return;
  const d = guidedCardDraft;
  const gm = d.guided_meta;
  const valIfPresent = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : undefined;
  };

  if (valIfPresent("gcNameInput") !== undefined) d.name = valIfPresent("gcNameInput").trim() || "未命名游戏卡";
  if (valIfPresent("gcTagsInput") !== undefined) {
    d.tags = valIfPresent("gcTagsInput").split(/[,，]/).map((s) => s.trim()).filter(Boolean);
  }
  if (valIfPresent("gcDescInput") !== undefined) d.description = valIfPresent("gcDescInput").trim();
  if (valIfPresent("gcIdeaInput") !== undefined) gm.idea_prompt = valIfPresent("gcIdeaInput").trim();
  if (valIfPresent("gcProtName") !== undefined) gm.protagonist_name = valIfPresent("gcProtName").trim();
  if (valIfPresent("gcProtDesc") !== undefined) gm.protagonist_desc = valIfPresent("gcProtDesc").trim();
  if (valIfPresent("gcProtGoal") !== undefined) gm.protagonist_goal = valIfPresent("gcProtGoal").trim();
  if (valIfPresent("gcWorldName") !== undefined) gm.world_name = valIfPresent("gcWorldName").trim();
  if (valIfPresent("gcWorldTone") !== undefined) gm.world_tone = valIfPresent("gcWorldTone").trim();
  if (valIfPresent("gcWorldEra") !== undefined) gm.world_era = valIfPresent("gcWorldEra").trim();
  if (valIfPresent("gcWorldConflict") !== undefined) gm.world_conflict = valIfPresent("gcWorldConflict").trim();
  if (valIfPresent("gcMainPlot") !== undefined) gm.main_plot = valIfPresent("gcMainPlot").trim();
  if (valIfPresent("gcInitialState") !== undefined) gm.initial_state = valIfPresent("gcInitialState").trim();
  if (valIfPresent("gcPlayRules") !== undefined) gm.play_rules = valIfPresent("gcPlayRules").trim();

  const greetChk = document.getElementById("gcSetInitialGreeting");
  if (greetChk) d.set_initial_as_greeting = !!greetChk.checked;

  const npcCards = document.querySelectorAll("#gcNpcList .gc-npc-card");
  if (npcCards.length > 0 || document.getElementById("gcNpcList")) {
    gm.npcs = Array.from(npcCards).map((card) => ({
      name: (card.querySelector(".gc-npc-name")?.value || "").trim(),
      role: (card.querySelector(".gc-npc-role")?.value || "").trim(),
      desc: (card.querySelector(".gc-npc-desc")?.value || "").trim(),
      attitude: (card.querySelector(".gc-npc-attitude")?.value || "").trim()
    }));
  }

  const cgCards = document.querySelectorAll("#gcCgList .gc-cg-card");
  if (cgCards.length > 0 || document.getElementById("gcCgList")) {
    d.cg_book = Array.from(cgCards).map((card, idx) => {
      const prevCg = d.cg_book[idx] || {};
      const rawKeys = (card.querySelector(".gc-cg-keys")?.value || "").trim();
      return {
        ...prevCg,
        id: prevCg.id || `cg_${Date.now().toString(36)}_${idx}`,
        name: (card.querySelector(".gc-cg-name")?.value || "").trim() || `特殊CG #${idx + 1}`,
        image_url: card.dataset.imgUrl || prevCg.image_url || "",
        keys: rawKeys.split(/[,，;；]+/).map((s) => s.trim()).filter(Boolean),
        match_type: card.querySelector(".gc-cg-match")?.value || "OR",
        trigger_source: card.querySelector(".gc-cg-source")?.value || "ai",
        display_mode: card.querySelector(".gc-cg-display")?.value || "chat",
        enabled: true
      };
    });
  }
}

function buildPresetUiModules(presetKey, existingMods = []) {
  if (presetKey === "keep" && Array.isArray(existingMods) && existingMods.length > 0) {
    return { enabled: true, modules: JSON.parse(JSON.stringify(existingMods)) };
  }
  if (presetKey === "standard") {
    return {
      enabled: true,
      modules: DEFAULT_UNIVERSAL_UI_MODULES.map((m) => ({ ...m, enabled: true }))
    };
  }
  if (presetKey === "tactical") {
    const base = DEFAULT_UNIVERSAL_UI_MODULES.map((m) => ({ ...m, enabled: true }));
    const bodyMod = {
      id: "mod_body_tac",
      key: "身体与负伤",
      type: "equipment_slots",
      enabled: true,
      fields: "头部: 完好\n胸部: 完好\n腹部: 完好\n四肢: 灵活\n精神/体力: 充沛",
      desc: "每回合根据交战、受创或环境消耗实时更新身体各部位负伤、防护与行动能力变化。",
      v: 2
    };
    base.splice(2, 0, bodyMod);
    return { enabled: true, modules: base };
  }
  if (presetKey === "investigative") {
    const storyM = STANDARD_UI_MODULES.find((m) => m.id === "mod_story");
    const statsM = {
      id: "mod_stats",
      key: "调查员状态",
      type: "progress_stats",
      enabled: true,
      fields: "生命: 100/100\n理智(SAN): 80/100\n精力: 100/100\n当前处境: 保持警惕",
      desc: "实时追踪主角的生命、理智(SAN值)损耗、精力与现场处境。",
      v: 2
    };
    const infoM = STANDARD_UI_MODULES.find((m) => m.id === "mod_info");
    const invM = STANDARD_UI_MODULES.find((m) => m.id === "mod_inv");
    const npcM = STANDARD_UI_MODULES.find((m) => m.id === "mod_npc");
    const choicesM = STANDARD_UI_MODULES.find((m) => m.id === "mod_choices");
    return {
      enabled: true,
      modules: [storyM, statsM, infoM, invM, npcM, choicesM].filter(Boolean).map((m) => ({ ...m, enabled: true }))
    };
  }
  return { enabled: false, modules: [] };
}

function compileGuidedDraftToProject(draft) {
  const d = draft || createBlankGuidedDraft();
  const gm = d.guided_meta || {};
  const sections = [];

  const worldLines = [];
  if (gm.world_name) worldLines.push(`- **世界/舞台名称**：${gm.world_name}`);
  if (gm.world_era) worldLines.push(`- **时代背景与体系**：${gm.world_era}`);
  if (gm.world_conflict) worldLines.push(`- **核心冲突与暗流**：${gm.world_conflict}`);
  if (gm.world_tone) worldLines.push(`- **整体基调与文风**：${gm.world_tone}`);
  if (worldLines.length > 0) {
    sections.push(`## 世界观设定\n${worldLines.join("\n")}`);
  }

  const protLines = [];
  if (gm.protagonist_name) protLines.push(`- **主人公（玩家）称呼/身份**：${gm.protagonist_name}`);
  if (gm.protagonist_desc) protLines.push(`- **背景与能力特征**：${gm.protagonist_desc}`);
  if (gm.protagonist_goal) protLines.push(`- **核心动机与目标**：${gm.protagonist_goal}`);
  if (protLines.length > 0) {
    sections.push(`## 主人公（玩家）设定\n${protLines.join("\n")}`);
  }

  const validNpcs = (Array.isArray(gm.npcs) ? gm.npcs : []).filter(
    (n) => n && (n.name || n.role || n.desc || n.attitude)
  );
  if (validNpcs.length > 0) {
    const npcBlocks = validNpcs.map((n, idx) => {
      const parts = [];
      parts.push(`### ${idx + 1}. ${n.name || "未命名角色"}${n.role ? `（${n.role}）` : ""}`);
      if (n.desc) parts.push(`- **外貌性格与能力**：${n.desc}`);
      if (n.attitude) parts.push(`- **对主角态度与动机**：${n.attitude}`);
      return parts.join("\n");
    });
    sections.push(`## 登场角色设定\n${npcBlocks.join("\n\n")}`);
  }

  const plotLines = [];
  if (gm.main_plot) plotLines.push(`- **主线情节脉络**：${gm.main_plot}`);
  if (gm.initial_state && !d.set_initial_as_greeting) {
    plotLines.push(`- **初始开局处境**：${gm.initial_state}`);
  }
  if (plotLines.length > 0) {
    sections.push(`## 主线剧情设定\n${plotLines.join("\n")}`);
  }

  if (gm.play_rules) {
    sections.push(
      sections.length === 0 && !gm.play_rules.startsWith("#")
        ? gm.play_rules
        : `## 游玩规则\n${gm.play_rules}`
    );
  }

  if (d.extra_raw_prompt && d.extra_raw_prompt.trim()) {
    sections.push(d.extra_raw_prompt.trim());
  }

  const compiledSystemPrompt = sections.join("\n\n").trim();
  const { enabled: stEnabled, modules: uiMods } = buildPresetUiModules(gm.status_preset || "none", d.existing_ui_modules);

  const openingGreetings = [];
  if (d.set_initial_as_greeting && gm.initial_state && gm.initial_state.trim()) {
    openingGreetings.push({
      id: "og_1",
      title: "初始开局",
      content: gm.initial_state.trim()
    });
  }

  return normalizeProjectClient({
    ...(d.id ? { id: d.id } : {}),
    name: (d.name || "").trim() || "未命名游戏卡",
    icon: d.icon || "",
    avatar: d.icon || "",
    description: d.description || "",
    detailed_description: d.detailed_description || "",
    custom_css: d.custom_css || "",
    quick_replies: Array.isArray(d.quick_replies) ? d.quick_replies : [],
    worldbook_defaults: d.worldbook_defaults,
    cg_defaults: d.cg_defaults,
    tags: Array.isArray(d.tags) ? d.tags : [],
    card_tier: "simple",
    simple_mode: false,
    cot_enabled: true,
    status_panel_enabled: stEnabled,
    ui_modules: uiMods,
    prefix: d.prefix || "",
    system_prompt: compiledSystemPrompt,
    suffix: d.suffix || "",
    system_protocol_prompt: "",
    opening_greetings: openingGreetings,
    opening_statement: openingGreetings[0]?.content || "",
    cg_book: (Array.isArray(d.cg_book) ? d.cg_book : []).filter((c) => c && (c.image_url || (c.keys && c.keys.length))),
    world_book: Array.isArray(d.world_book) ? d.world_book : [],
    regex_scripts: Array.isArray(d.regex_scripts) ? d.regex_scripts : [],
    regex_replaces: Array.isArray(d.regex_scripts) ? d.regex_scripts : [],
    guided_meta: {
      ...gm,
      set_initial_as_greeting: d.set_initial_as_greeting
    },
    use_global_params: true,
    appearance: {
      bg_image: d.bg_image || "",
      bg_mobile: d.bg_mobile || "",
      custom_css: d.custom_css || ""
    }
  });
}

window.openGuidedGameCardModal = function (sourceProjIdOrObj = null) {
  const modal = document.getElementById("guidedGameCardModal");
  if (!modal) return;
  if (sourceProjIdOrObj && typeof sourceProjIdOrObj === "object") {
    guidedCardDraft = buildGuidedDraftFromProject(sourceProjIdOrObj);
  } else if (typeof sourceProjIdOrObj === "string" && sourceProjIdOrObj.trim()) {
    const pMap = typeof projectsMap !== "undefined" ? projectsMap : window.projectsMap;
    const found = (pMap && pMap[sourceProjIdOrObj]) || exploreUserProjectsCache.find((x) => x.id === sourceProjIdOrObj);
    guidedCardDraft = found ? buildGuidedDraftFromProject(found) : createBlankGuidedDraft();
  } else {
    const pMap = typeof projectsMap !== "undefined" ? projectsMap : window.projectsMap;
    const customCount = Object.values(pMap || {}).filter(
      (p) => p && !["proj_fast_trpg", "proj_default", "proj_free_chat"].includes(p.id)
    ).length;
    guidedCardDraft = createBlankGuidedDraft(`新企划 #${customCount + 1}`);
  }
  modal.style.display = "flex";
  renderGuidedGameCardModal();
};

window.setGuidedCreatorStep = function (stepNum) {
  syncGuidedDraftFromDom();
  if (!guidedCardDraft) return;
  guidedCardDraft.step = Math.max(1, Math.min(3, Number(stepNum) || 1));
  renderGuidedGameCardModal();
};

window.toggleGuidedQuickTag = function (tagStr) {
  syncGuidedDraftFromDom();
  if (!guidedCardDraft) return;
  const idx = guidedCardDraft.tags.indexOf(tagStr);
  if (idx === -1) {
    guidedCardDraft.tags.push(tagStr);
  } else {
    guidedCardDraft.tags.splice(idx, 1);
  }
  renderGuidedGameCardModal();
};

window.selectGuidedStatusPreset = function (presetKey) {
  syncGuidedDraftFromDom();
  if (!guidedCardDraft) return;
  guidedCardDraft.guided_meta.status_preset = presetKey;
  renderGuidedGameCardModal();
};

window.addGuidedNpcRow = function () {
  syncGuidedDraftFromDom();
  if (!guidedCardDraft) return;
  guidedCardDraft.guided_meta.npcs.push({ name: "", role: "", desc: "", attitude: "" });
  renderGuidedGameCardModal();
};

window.removeGuidedNpcRow = function (idx) {
  syncGuidedDraftFromDom();
  if (!guidedCardDraft) return;
  guidedCardDraft.guided_meta.npcs.splice(idx, 1);
  renderGuidedGameCardModal();
};

window.importCharCardIntoGuidedNpcs = async function () {
  syncGuidedDraftFromDom();
  if (!guidedCardDraft) return;
  try {
    const res = await fetch("/api/character_cards");
    const data = await res.json();
    const cards = Array.isArray(data) ? data : (data.cards || []);
    if (cards.length === 0) {
      showToast("角色卡库暂无卡片，可先在下方直接添加角色");
      return;
    }
    const existingNames = new Set(guidedCardDraft.guided_meta.npcs.map((n) => n.name));
    let added = 0;
    cards.slice(0, 6).forEach((c) => {
      const nm = (c.name || "").trim();
      if (!nm || existingNames.has(nm)) return;
      guidedCardDraft.guided_meta.npcs.push({
        name: nm,
        role: (c.tags || [])[0] || "角色卡导入",
        desc: [c.description, c.personality].filter(Boolean).join("；").slice(0, 260),
        attitude: (c.scenario || "").slice(0, 140)
      });
      existingNames.add(nm);
      added++;
    });
    renderGuidedGameCardModal();
    showToast(added > 0 ? `已从角色卡库载入 ${added} 名角色` : "角色卡库中的角色已在列表中");
  } catch (err) {
    showToast("读取角色卡库失败: " + err.message);
  }
};

window.addGuidedCgRow = function () {
  syncGuidedDraftFromDom();
  if (!guidedCardDraft) return;
  guidedCardDraft.cg_book.push({
    id: `cg_${Date.now().toString(36)}`,
    name: `特殊CG #${guidedCardDraft.cg_book.length + 1}`,
    image_url: "",
    keys: [],
    match_type: "OR",
    trigger_source: "ai",
    display_mode: "chat",
    enabled: true
  });
  renderGuidedGameCardModal();
};

window.removeGuidedCgRow = function (idx) {
  syncGuidedDraftFromDom();
  if (!guidedCardDraft) return;
  guidedCardDraft.cg_book.splice(idx, 1);
  renderGuidedGameCardModal();
};

window.handleUploadGuidedAsset = async function (event, slotType, cgIdx = -1) {
  const file = event.target?.files?.[0];
  if (!file || !guidedCardDraft) return;
  syncGuidedDraftFromDom();
  showToast("正在处理图片...");
  try {
    const maxDim = slotType === "icon" ? 720 : 1600;
    const folder = slotType === "icon" ? "角色立绘" : "场景CG";
    const url = await uploadImageAndGetUrl(file, maxDim, 0.85, folder);
    if (slotType === "icon") {
      guidedCardDraft.icon = url;
    } else if (slotType === "bg_image") {
      guidedCardDraft.bg_image = url;
    } else if (slotType === "bg_mobile") {
      guidedCardDraft.bg_mobile = url;
    } else if (slotType === "cg" && cgIdx >= 0 && guidedCardDraft.cg_book[cgIdx]) {
      guidedCardDraft.cg_book[cgIdx].image_url = url;
    }
    renderGuidedGameCardModal();
    showToast("图片已就绪");
  } catch (err) {
    showToast("图片上传失败: " + err.message);
  } finally {
    try { event.target.value = ""; } catch (e) {}
  }
};

window.clearGuidedAsset = function (slotType, event) {
  if (event) event.stopPropagation();
  syncGuidedDraftFromDom();
  if (!guidedCardDraft) return;
  if (slotType === "icon") guidedCardDraft.icon = "";
  else if (slotType === "bg_image") guidedCardDraft.bg_image = "";
  else if (slotType === "bg_mobile") guidedCardDraft.bg_mobile = "";
  renderGuidedGameCardModal();
};

window.handleAiGenerateGuidedCard = async function (btnEl) {
  syncGuidedDraftFromDom();
  if (!guidedCardDraft) return;
  const gm = guidedCardDraft.guided_meta;
  const idea = gm.idea_prompt || guidedCardDraft.description || "";
  if (!idea.trim()) {
    showToast("请先在输入框中写一句大致想法或题材（如：赛博东京特勤小队潜入黑帮大厦）");
    document.getElementById("gcIdeaInput")?.focus();
    return;
  }
  const selectedModel = document.getElementById("gcAiModelSelect")?.value || "";
  const origHtml = btnEl ? btnEl.innerHTML : "✨ AI 生成设定";
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.innerHTML = "生成中...";
  }
  try {
    const res = await fetch("/api/ai/generate_game_card", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        idea,
        name: guidedCardDraft.name,
        description: guidedCardDraft.description,
        current_meta: gm,
        model: selectedModel
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    const g = data.generated || {};

    // 仅填充用户尚未手写的内容，保护已有设定不被覆盖
    if ((!guidedCardDraft.name || /^新企划\s*#\d+$/.test(guidedCardDraft.name)) && g.name) {
      guidedCardDraft.name = String(g.name).trim();
    }
    if (!guidedCardDraft.description && g.description) {
      guidedCardDraft.description = String(g.description).trim();
    }
    if ((!guidedCardDraft.tags || guidedCardDraft.tags.length === 0) && Array.isArray(g.tags)) {
      guidedCardDraft.tags = g.tags.map((x) => String(x).trim()).filter(Boolean);
    }
    const fillMetaKey = (k) => {
      if (!gm[k] && g[k]) gm[k] = String(g[k]).trim();
    };
    [
      "protagonist_name", "protagonist_desc", "protagonist_goal",
      "world_name", "world_era", "world_conflict", "world_tone",
      "main_plot", "initial_state", "play_rules"
    ].forEach(fillMetaKey);

    if ((!Array.isArray(gm.npcs) || gm.npcs.length === 0) && Array.isArray(g.npcs) && g.npcs.length > 0) {
      gm.npcs = g.npcs.map((n) => ({
        name: String(n.name || "").trim(),
        role: String(n.role || "").trim(),
        desc: String(n.desc || "").trim(),
        attitude: String(n.attitude || "").trim()
      }));
    }
    renderGuidedGameCardModal();
    showToast("AI 已补全空白设定（可在第 1~3 步自由微调）");
  } catch (err) {
    showToast("AI 生成失败: " + err.message);
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.innerHTML = origHtml;
    }
  }
};

window.upgradeGuidedDraftToAdvanced = async function () {
  syncGuidedDraftFromDom();
  if (!guidedCardDraft) return;
  const isExistingCard = Boolean(guidedCardDraft.id);
  if (isExistingCard) {
    if (!window.confirm(`确定将简易游戏卡「${guidedCardDraft.name || "未命名"}」升级为高级游戏卡吗？\n\n升级后将编译保留当前向导中的所有设定，并解锁世界书、内置 CSS、正则脚本与前后置词（单向升级不可退回简易卡）。`)) {
      return;
    }
  }
  const compiled = compileGuidedDraftToProject(guidedCardDraft);
  compiled.card_tier = "advanced";
  compiled.simple_mode = false;
  if (["极速跑团", "简单跑团"].includes(String(compiled.category || "").trim())) {
    compiled.category = "";
  }

  // 若是已落盘的简易卡，先立即持久化升级状态，再进入三栏高级工坊继续精修
  if (isExistingCard) {
    try {
      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(compiled)
      });
      if (res.ok) {
        await loadProjects();
      }
    } catch (e) {}
  }

  advancedDraftProject = compiled;
  currentAdvancedCreatorTab = "basic";
  const gModal = document.getElementById("guidedGameCardModal");
  if (gModal) gModal.style.display = "none";
  const eModal = document.getElementById("exploreModal");
  if (eModal) eModal.style.display = "flex";
  renderAdvancedProjectEditor();
  showToast(isExistingCard ? "已升级为高级游戏卡！现可编辑内置 CSS 与世界书" : "已升级至高级游戏卡工坊");
};
window.switchGuidedToAdvancedCreator = window.upgradeGuidedDraftToAdvanced;

window.switchAdvancedToGuidedCreator = function () {
  syncAdvancedDraftFromDom();
  if (!advancedDraftProject) return;
  guidedCardDraft = buildGuidedDraftFromProject(advancedDraftProject);
  const eModal = document.getElementById("exploreModal");
  if (eModal) eModal.style.display = "none";
  const gModal = document.getElementById("guidedGameCardModal");
  if (gModal) gModal.style.display = "flex";
  renderGuidedGameCardModal();
  showToast("已切换至简易创作向导");
};

window.submitGuidedGameCard = async function () {
  syncGuidedDraftFromDom();
  if (!guidedCardDraft) return;
  const projPayload = compileGuidedDraftToProject(guidedCardDraft);
  const isUpdatingExisting = Boolean(guidedCardDraft.id);

  try {
    let savedProj = null;
    let newChatId = null;
    if (isUpdatingExisting) {
      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(projPayload)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "保存失败");
      savedProj = data.project;
    } else {
      const res = await fetch("/api/projects/fork", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project: projPayload,
          keep_exact_name: true
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "创建失败");
      savedProj = data.project;
      newChatId = data.chat_id || null;
    }

    const modal = document.getElementById("guidedGameCardModal");
    if (modal) modal.style.display = "none";

    window._welcomeModeStepSelected = true;
    currentProjectId = savedProj.id;
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active_project_id: currentProjectId })
    });
    await loadProjects();
    if (newChatId) {
      currentChatId = newChatId;
      await loadChats();
      await switchChat(newChatId);
    } else {
      await loadChats();
    }
    applyProjectAppearance(getActiveProjectObj());
    const pane = document.getElementById("studioWorkbenchPane");
    if (pane && pane.style.display !== "none") {
      renderStudioWorkbench();
    }
    showToast(isUpdatingExisting ? `已更新游戏卡：${savedProj.name}` : `已创建游戏卡：${savedProj.name}`);
  } catch (err) {
    showToast("保存游戏卡失败: " + err.message);
  }
};

function _triggerBlobDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    a.remove();
    URL.revokeObjectURL(url);
  }, 400);
}

window.exportProjectGameCard = async function (projectId, fmt = "png") {
  const pid = projectId || currentProjectId;
  if (!pid) return;
  // 若当前正在右侧面板编辑同一张卡，先自动落盘再导出
  if (pid === currentProjectId && document.getElementById("studioWorkbenchPane")?.style.display !== "none") {
    await window.saveStudioProjectConfig(false);
  }
  const pObj = (typeof projectsMap !== "undefined" && projectsMap && projectsMap[pid]) || null;
  const safeName = ((pObj && pObj.name) || "游戏卡").replace(/[\\/:*?"<>|]+/g, "_");
  showToast(fmt === "json" ? "正在导出 JSON 游戏卡..." : "正在生成 PNG 游戏卡海报...");
  try {
    const res = await fetch(`/api/projects/${encodeURIComponent(pid)}/export_card?format=${encodeURIComponent(fmt)}`);
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP ${res.status}`);
    }
    const blob = await res.blob();
    _triggerBlobDownload(blob, `${safeName}_游戏卡.${fmt === "json" ? "json" : "png"}`);
    showToast(`已导出：${safeName}_游戏卡.${fmt === "json" ? "json" : "png"}`);
  } catch (err) {
    showToast("导出游戏卡失败: " + err.message);
  }
};

window.exportDraftGameCard = async function (sourceMode = "guided", fmt = "png") {
  let draftProj = null;
  if (sourceMode === "guided") {
    syncGuidedDraftFromDom();
    if (!guidedCardDraft) return;
    draftProj = compileGuidedDraftToProject(guidedCardDraft);
  } else {
    syncAdvancedDraftFromDom();
    if (!advancedDraftProject) return;
    draftProj = JSON.parse(JSON.stringify(advancedDraftProject));
  }
  const safeName = (draftProj.name || "游戏卡").replace(/[\\/:*?"<>|]+/g, "_");
  showToast(fmt === "json" ? "正在导出 JSON 游戏卡..." : "正在生成 PNG 游戏卡海报...");
  try {
    const res = await fetch("/api/projects/export_draft_card", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project: draftProj, format: fmt })
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP ${res.status}`);
    }
    const blob = await res.blob();
    _triggerBlobDownload(blob, `${safeName}_游戏卡.${fmt === "json" ? "json" : "png"}`);
    showToast(`已导出：${safeName}_游戏卡.${fmt === "json" ? "json" : "png"}`);
  } catch (err) {
    showToast("导出草稿游戏卡失败: " + err.message);
  }
};

window.importGameCardFileList = async function (rawFileList) {
  const files = Array.from(rawFileList || []).filter((f) => f && /\.(png|json)$/i.test(f.name || ""));
  if (files.length === 0) {
    if (rawFileList && rawFileList.length > 0) {
      showToast("仅支持导入 .png 或 .json 格式的游戏卡");
    }
    return;
  }
  showToast(`正在导入 ${files.length} 张游戏卡...`);
  let lastImported = null;
  let lastChatId = null;
  let okCount = 0;

  try {
    for (const file of files) {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/projects/import_card", {
        method: "POST",
        body: fd
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        showToast(`导入「${file.name}」失败: ${data.detail || res.status}`);
        continue;
      }
      okCount++;
      lastImported = data.project;
      lastChatId = data.chat_id || null;
    }

    if (okCount > 0 && lastImported) {
      document.getElementById("guidedGameCardModal") && (document.getElementById("guidedGameCardModal").style.display = "none");
      document.getElementById("exploreModal") && (document.getElementById("exploreModal").style.display = "none");
      window._welcomeModeStepSelected = true;
      currentProjectId = lastImported.id;
      await loadProjects();
      await loadChats();
      if (lastChatId) {
        currentChatId = lastChatId;
        await switchChat(lastChatId);
      }
      applyProjectAppearance(getActiveProjectObj());
      const pane = document.getElementById("studioWorkbenchPane");
      if (pane && pane.style.display !== "none") {
        renderStudioWorkbench();
      }
      showToast(okCount === 1 ? `已导入游戏卡：${lastImported.name}` : `成功导入 ${okCount} 张游戏卡`);
    }
  } catch (err) {
    showToast("导入游戏卡异常: " + err.message);
  }
};

window.handleImportGameCardFiles = async function (event) {
  try {
    await window.importGameCardFileList(event.target?.files || []);
  } finally {
    try { event.target.value = ""; } catch (e) {}
  }
};

function renderGuidedGameCardModal() {
  const inner = document.getElementById("guidedGameCardModalInner");
  if (!inner || !guidedCardDraft) return;
  const d = guidedCardDraft;
  const gm = d.guided_meta;
  const step = d.step || 1;
  const isEditing = Boolean(d.id);

  let stepBodyHtml = "";
  if (step === 1) {
    stepBodyHtml = `
      <!-- AI 一句话灵感入口（第1步与第2步均可直接触发，不填则保持纯净 0 提示词） -->
      <div class="gc-ai-banner">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px;">
          <span style="font-size:12.5px;font-weight:700;color:var(--tc-fcd34d, #fcd34d);">✨ 一句话 AI 构筑游戏卡 <small style="font-weight:400;color:var(--text-muted);">（选填；不点生成、直接留空创建即为纯净 0 提示词）</small></span>
          <div style="display:flex;align-items:center;gap:6px;">
            <span style="font-size:11.5px;color:var(--text-muted);">模型</span>
            <select id="gcAiModelSelect" class="form-select ai-assist-model-select" style="width:auto;max-width:190px;padding:2px 24px 2px 8px;font-size:11.5px;height:26px;" onchange="window.handleAiAssistModelChange && window.handleAiAssistModelChange(this.value)"></select>
          </div>
        </div>
        <div style="display:flex;gap:8px;align-items:stretch;flex-wrap:wrap;">
          <input type="text" id="gcIdeaInput" class="form-input" style="flex:1;min-width:220px;" value="${escapeHtml(gm.idea_prompt || "")}" placeholder="例：2032年近未来新港市，扮演特勤干员潜入黑帮盘踞的冷链码头解救人质..." onkeydown="if(event.key==='Enter'){event.preventDefault();document.getElementById('btnGcAiGen')?.click();}" />
          <button type="button" id="btnGcAiGen" class="btn btn-sm btn-primary" style="white-space:nowrap;" onclick="window.handleAiGenerateGuidedCard(this)">✨ AI 生成全部设定</button>
        </div>
      </div>

      <!-- 视觉上传三联卡：封面海报 / 电脑背景 / 手机背景（全部选填，不强制） -->
      <div class="gc-upload-grid">
        <div class="gc-upload-slot" onclick="document.getElementById('gcCoverFile').click()">
          <input type="file" id="gcCoverFile" accept="image/*" style="display:none;" onchange="window.handleUploadGuidedAsset(event, 'icon')" />
          ${d.icon
            ? `<img src="${escapeHtml(d.icon)}" alt="封面" class="gc-slot-img" />
               <button type="button" class="gc-slot-clear" onclick="window.clearGuidedAsset('icon', event)" title="移除">✕</button>`
            : `<div class="gc-slot-placeholder">
                 <span class="gc-slot-plus">+</span>
                 <b>封面照片</b>
                 <small>比例 3:4 / 4:3 · 导出 PNG 游戏卡卡面</small>
               </div>`
          }
        </div>

        <div class="gc-upload-slot" onclick="document.getElementById('gcBgDesktopFile').click()">
          <input type="file" id="gcBgDesktopFile" accept="image/*" style="display:none;" onchange="window.handleUploadGuidedAsset(event, 'bg_image')" />
          ${d.bg_image
            ? `<img src="${escapeHtml(d.bg_image)}" alt="电脑背景" class="gc-slot-img" />
               <button type="button" class="gc-slot-clear" onclick="window.clearGuidedAsset('bg_image', event)" title="移除">✕</button>`
            : `<div class="gc-slot-placeholder">
                 <span class="gc-slot-plus">+</span>
                 <b>聊天背景（横屏）</b>
                 <small>推荐 16:9 · 电脑端游玩背景</small>
               </div>`
          }
        </div>

        <div class="gc-upload-slot" onclick="document.getElementById('gcBgMobileFile').click()">
          <input type="file" id="gcBgMobileFile" accept="image/*" style="display:none;" onchange="window.handleUploadGuidedAsset(event, 'bg_mobile')" />
          ${d.bg_mobile
            ? `<img src="${escapeHtml(d.bg_mobile)}" alt="手机背景" class="gc-slot-img" />
               <button type="button" class="gc-slot-clear" onclick="window.clearGuidedAsset('bg_mobile', event)" title="移除">✕</button>`
            : `<div class="gc-slot-placeholder">
                 <span class="gc-slot-plus">+</span>
                 <b>移动设备背景</b>
                 <small>推荐 9:16 · 手机/竖屏自动切换</small>
               </div>`
          }
        </div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1.2fr;gap:12px;">
        <div>
          <label class="gc-field-label">游戏卡名称</label>
          <input type="text" id="gcNameInput" class="form-input" value="${escapeHtml(d.name || "")}" placeholder="为你的游戏企划起个名字" />
        </div>
        <div>
          <label class="gc-field-label">题材标签 <small>（逗号分隔，或点下方标签）</small></label>
          <input type="text" id="gcTagsInput" class="form-input" value="${escapeHtml((d.tags || []).join(", "))}" placeholder="奇幻, 潜入, 多分支" />
        </div>
      </div>

      <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:-4px;">
        ${GUIDED_QUICK_TAGS.map((tg) => {
          const active = (d.tags || []).includes(tg);
          return `<button type="button" class="gc-tag-chip ${active ? "active" : ""}" onclick="window.toggleGuidedQuickTag('${escapeJsAttr(tg)}')">#${escapeHtml(tg)}</button>`;
        }).join("")}
      </div>

      <div>
        <label class="gc-field-label">作品简介 <small>（仅展示给玩家看的游戏卡介绍，不会发送给 AI）</small></label>
        <textarea id="gcDescInput" rows="3" class="form-textarea" placeholder="向玩家介绍你的作品亮点、故事背景、阵营玩法或注意事项...">${escapeHtml(d.description || "")}</textarea>
      </div>
    `;
  } else if (step === 2) {
    stepBodyHtml = `
      <div class="gc-ai-banner">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px;">
          <span style="font-size:12.5px;font-weight:700;color:var(--tc-fcd34d, #fcd34d);">✨ AI 设定补全 <small style="font-weight:400;color:var(--text-muted);">（已有内容的框会自动保留，只补全空白项）</small></span>
          <select id="gcAiModelSelect" class="form-select ai-assist-model-select" style="width:auto;max-width:190px;padding:2px 24px 2px 8px;font-size:11.5px;height:26px;" onchange="window.handleAiAssistModelChange && window.handleAiAssistModelChange(this.value)"></select>
        </div>
        <div style="display:flex;gap:8px;align-items:stretch;flex-wrap:wrap;">
          <input type="text" id="gcIdeaInput" class="form-input" style="flex:1;min-width:220px;" value="${escapeHtml(gm.idea_prompt || "")}" placeholder="输入大致描述，让 AI 自动生成下方角色与世界观设定..." />
          <button type="button" class="btn btn-sm btn-primary" onclick="window.handleAiGenerateGuidedCard(this)">✨ AI 生成</button>
        </div>
      </div>

      <!-- 主人公（玩家）设定 -->
      <div class="studio-section-card" style="margin:0;">
        <div class="studio-section-header">
          <div class="studio-section-title">主人公（玩家）设定</div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1.4fr;gap:10px;margin-bottom:8px;">
          <div>
            <label class="gc-field-label">主人公名称 / 身份</label>
            <input type="text" id="gcProtName" class="form-input" value="${escapeHtml(gm.protagonist_name || "")}" placeholder="例：玩家自定 / 第七分署新晋特工" />
          </div>
          <div>
            <label class="gc-field-label">核心动机 / 初始目标</label>
            <input type="text" id="gcProtGoal" class="form-input" value="${escapeHtml(gm.protagonist_goal || "")}" placeholder="例：追查失踪线人的下落并在灰港活下去" />
          </div>
        </div>
        <div>
          <label class="gc-field-label">主人公背景与特长</label>
          <textarea id="gcProtDesc" rows="2" class="form-textarea" placeholder="例：年轻的流浪剑士，身手敏捷但过去充满谜团（留空则完全交由玩家开局自由扮演）">${escapeHtml(gm.protagonist_desc || "")}</textarea>
        </div>
      </div>

      <!-- 世界观设定 -->
      <div class="studio-section-card" style="margin:0;">
        <div class="studio-section-header">
          <div class="studio-section-title">世界观设定</div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:8px;">
          <div>
            <label class="gc-field-label">世界 / 舞台名称</label>
            <input type="text" id="gcWorldName" class="form-input" value="${escapeHtml(gm.world_name || "")}" placeholder="故事展开的世界、城市或国家名" />
          </div>
          <div>
            <label class="gc-field-label">整体基调与氛围</label>
            <input type="text" id="gcWorldTone" class="form-input" value="${escapeHtml(gm.world_tone || "")}" placeholder="例：冷硬写实、黑暗奇幻、悬疑压迫、轻松搞笑" />
          </div>
        </div>
        <div style="margin-bottom:8px;">
          <label class="gc-field-label">时代背景与科技 / 魔法水平</label>
          <textarea id="gcWorldEra" rows="2" class="form-textarea" placeholder="例：近未来2032年港口都市，写实热武器与帮派武装割据，无超自然异能...">${escapeHtml(gm.world_era || "")}</textarea>
        </div>
        <div>
          <label class="gc-field-label">核心冲突 / 主题</label>
          <textarea id="gcWorldConflict" rows="2" class="form-textarea" placeholder="例：治安局、黑帮辛迪加与财团安保三方暗战，每一次潜入都可能面临背叛...">${escapeHtml(gm.world_conflict || "")}</textarea>
        </div>
      </div>

      <!-- 登场角色设定 -->
      <div class="studio-section-card" style="margin:0;">
        <div class="studio-section-header" style="flex-wrap:wrap;gap:6px;">
          <div class="studio-section-title">关键角色设定 (${(gm.npcs || []).length})</div>
          <div style="display:flex;gap:6px;">
            <button type="button" class="btn btn-xs btn-secondary" onclick="window.importCharCardIntoGuidedNpcs()">从角色卡库导入</button>
            <button type="button" class="btn btn-xs btn-primary" onclick="window.addGuidedNpcRow()">+ 添加角色</button>
          </div>
        </div>
        <div id="gcNpcList" style="display:flex;flex-direction:column;gap:8px;">
          ${(gm.npcs || []).length === 0
            ? `<div style="padding:10px;border:1px dashed var(--border-subtle);border-radius:8px;text-align:center;font-size:12px;color:var(--text-dim);">选填：可添加核心 NPC 档案，或留空由 AI 在剧情中动态生成</div>`
            : (gm.npcs || []).map((npc, idx) => `
              <div class="gc-npc-card">
                <div style="display:grid;grid-template-columns:1fr 1fr auto;gap:8px;align-items:center;">
                  <input type="text" class="form-input gc-npc-name" value="${escapeHtml(npc.name || "")}" placeholder="角色姓名" />
                  <input type="text" class="form-input gc-npc-role" value="${escapeHtml(npc.role || "")}" placeholder="身份 / 阵营" />
                  <button type="button" class="btn btn-xs btn-danger" onclick="window.removeGuidedNpcRow(${idx})">✕</button>
                </div>
                <input type="text" class="form-input gc-npc-desc" value="${escapeHtml(npc.desc || "")}" placeholder="外貌、性格、武器与能力特长..." />
                <input type="text" class="form-input gc-npc-attitude" value="${escapeHtml(npc.attitude || "")}" placeholder="对主角初始态度与隐藏动机..." />
              </div>
            `).join("")
          }
        </div>
      </div>
    `;
  } else {
    const curPreset = gm.status_preset || "none";
    const presets = [
      { key: "none", title: "纯净无状态栏", desc: "0 额外系统注入，仅发送你编写的设定或自定义模板" },
      { key: "standard", title: "标准跑团 6 栏", desc: "自动挂载：主角状态、装备栏、物品栏、角色关系、行动选项" },
      { key: "tactical", title: "硬核战术身体栏", desc: "额外包含身体各部位负伤状态、武器装备与战术选项" },
      { key: "investigative", title: "悬疑调查线索栏", desc: "包含生命/理智(SAN值)、任务线索卡、随身证物与人际动态" }
    ];
    if (curPreset === "keep") {
      presets.unshift({ key: "keep", title: "保留当前自定义栏位", desc: `沿用已配置的 ${(d.existing_ui_modules || []).length} 个功能栏` });
    }
    stepBodyHtml = `
      <!-- 主线与初始开局 -->
      <div class="studio-section-card" style="margin:0;">
        <div class="studio-section-header">
          <div class="studio-section-title">主线情节与初始开局</div>
          <label class="checkbox-label" style="font-size:12px;">
            <input type="checkbox" id="gcSetInitialGreeting" ${d.set_initial_as_greeting ? "checked" : ""} />
            <span>将「初始剧情状态」设为进场开场白</span>
          </label>
        </div>
        <div style="margin-bottom:8px;">
          <label class="gc-field-label">主线情节设定</label>
          <textarea id="gcMainPlot" rows="2" class="form-textarea" placeholder="例：主角在一次常规护送委托中意外截获了财团的实验黑匣子，必须在多方围捕中揭开真相...">${escapeHtml(gm.main_plot || "")}</textarea>
        </div>
        <div>
          <label class="gc-field-label">初始剧情状态（第一幕开场情景）</label>
          <textarea id="gcInitialState" rows="3" class="form-textarea" placeholder="例：雨夜十一点，你坐在第七区地下安全屋的折叠椅上，调度员把三份加急档案拍在铁桌上...">${escapeHtml(gm.initial_state || "")}</textarea>
        </div>
      </div>

      <!-- 游玩规则 -->
      <div class="studio-section-card" style="margin:0;">
        <div class="studio-section-header">
          <div class="studio-section-title">游玩规则（AI 主持守则）</div>
        </div>
        <textarea id="gcPlayRules" rows="4" class="form-textarea" placeholder="AI 扮演主持时需要遵守的法则（例：无主角光环、行动按属性与装备真实判定成败、严禁代替玩家说话或做决定；也可直接粘贴完整规则提示词）">${escapeHtml(gm.play_rules || "")}</textarea>
      </div>

      <!-- 状态栏模板选择 -->
      <div class="studio-section-card" style="margin:0;">
        <div class="studio-section-header">
          <div class="studio-section-title">状态栏预设 <small style="font-weight:400;color:var(--text-muted);">（创建后随时可在右侧剧本设定中增删改字段）</small></div>
        </div>
        <div class="gc-preset-grid">
          ${presets.map((p) => `
            <div class="gc-preset-card ${curPreset === p.key ? "active" : ""}" onclick="window.selectGuidedStatusPreset('${p.key}')">
              <div class="gc-preset-title">${escapeHtml(p.title)}</div>
              <div class="gc-preset-desc">${escapeHtml(p.desc)}</div>
            </div>
          `).join("")}
        </div>
      </div>

      <!-- 特殊事件 CG 触发 -->
      <div class="studio-section-card" style="margin:0;">
        <div class="studio-section-header" style="flex-wrap:wrap;gap:6px;">
          <div class="studio-section-title">特殊事件 CG 触发 (${(d.cg_book || []).length})</div>
          <button type="button" class="btn btn-xs btn-primary" onclick="window.addGuidedCgRow()">+ 新增 CG 触发</button>
        </div>
        <div id="gcCgList" style="display:flex;flex-direction:column;gap:8px;">
          ${(d.cg_book || []).length === 0
            ? `<div style="padding:10px;border:1px dashed var(--border-subtle);border-radius:8px;text-align:center;font-size:12px;color:var(--text-dim);">选填：当 AI 剧情出现指定关键词时，自动在聊天中弹出插画或切换场景背景</div>`
            : (d.cg_book || []).map((cg, idx) => `
              <div class="gc-cg-card" data-img-url="${escapeHtml(cg.image_url || "")}">
                <div class="gc-cg-thumb" onclick="document.getElementById('gcCgFile_${idx}').click()" title="点击上传 CG 图片">
                  <input type="file" id="gcCgFile_${idx}" accept="image/*" style="display:none;" onchange="window.handleUploadGuidedAsset(event, 'cg', ${idx})" />
                  ${cg.image_url ? `<img src="${escapeHtml(cg.image_url)}" alt="CG" />` : `<span>+ 传图</span>`}
                </div>
                <div style="flex:1;min-width:200px;display:flex;flex-direction:column;gap:6px;">
                  <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
                    <input type="text" class="form-input gc-cg-name" style="width:130px;padding:4px 8px;font-size:12px;" value="${escapeHtml(cg.name || "")}" placeholder="CG 名称" />
                    <input type="text" class="form-input gc-cg-keys" style="flex:1;min-width:140px;padding:4px 8px;font-size:12px;" value="${escapeHtml(Array.isArray(cg.keys) ? cg.keys.join(", ") : (cg.keys || ""))}" placeholder="触发词（逗号分隔，如：破门, 潜入成功）" />
                    <button type="button" class="btn btn-xs btn-danger" onclick="window.removeGuidedCgRow(${idx})">✕</button>
                  </div>
                  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:11.5px;color:var(--text-muted);">
                    <span>触发区域:</span>
                    <select class="form-select gc-cg-source" style="width:auto;padding:2px 22px 2px 6px;height:24px;font-size:11.5px;">
                      <option value="ai" ${cg.trigger_source !== "both" ? "selected" : ""}>仅 AI 回复</option>
                      <option value="both" ${cg.trigger_source === "both" ? "selected" : ""}>玩家 + AI</option>
                    </select>
                    <span>条件:</span>
                    <select class="form-select gc-cg-match" style="width:auto;padding:2px 22px 2px 6px;height:24px;font-size:11.5px;">
                      <option value="OR" ${cg.match_type !== "AND" ? "selected" : ""}>或 (任一命中)</option>
                      <option value="AND" ${cg.match_type === "AND" ? "selected" : ""}>与 (全部命中)</option>
                    </select>
                    <span>映射:</span>
                    <select class="form-select gc-cg-display" style="width:auto;padding:2px 22px 2px 6px;height:24px;font-size:11.5px;">
                      <option value="chat" ${cg.display_mode !== "background" ? "selected" : ""}>聊天插图</option>
                      <option value="background" ${cg.display_mode === "background" ? "selected" : ""}>切换背景图</option>
                    </select>
                  </div>
                </div>
              </div>
            `).join("")
          }
        </div>
      </div>
    `;
  }

  inner.innerHTML = `
    <div class="modal-header" style="flex-wrap:wrap;gap:8px;">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
        <h3 style="margin:0;">${isEditing ? "编辑简易游戏卡" : "新建简易游戏卡"}</h3>
        <span class="proj-tier-tag tier-simple" style="padding:2px 8px;font-size:11px;">简易卡</span>
        <span class="wb-badge" style="font-size:11px;">兼容酒馆 PNG / JSON</span>
      </div>
      <div style="display:flex;align-items:center;gap:6px;margin-left:auto;">
        <button type="button" class="btn btn-xs btn-secondary" onclick="document.getElementById('globalGameCardImportInput')?.click()" title="导入本工作台或 SillyTavern 酒馆的 .png/.json 游戏卡">导入游戏卡</button>
        <button type="button" class="btn btn-xs btn-primary" onclick="window.upgradeGuidedDraftToAdvanced()" title="将此简易游戏卡升级为高级游戏卡（解锁世界书、内置CSS、正则与前后置词）">⬆ 升级为高级卡</button>
        <button class="modal-close" type="button" onclick="document.getElementById('guidedGameCardModal').style.display='none'">✕</button>
      </div>
    </div>

    <!-- 顶部可自由点击跳转的三步进度条 -->
    <div class="gc-stepper">
      <button type="button" class="gc-step-item ${step === 1 ? "active" : (step > 1 ? "done" : "")}" onclick="window.setGuidedCreatorStep(1)">
        <span class="gc-step-num">01</span>
        <span class="gc-step-label">基础与外观</span>
      </button>
      <div class="gc-step-line ${step > 1 ? "done" : ""}"></div>
      <button type="button" class="gc-step-item ${step === 2 ? "active" : (step > 2 ? "done" : "")}" onclick="window.setGuidedCreatorStep(2)">
        <span class="gc-step-num">02</span>
        <span class="gc-step-label">角色与世界观</span>
      </button>
      <div class="gc-step-line ${step > 2 ? "done" : ""}"></div>
      <button type="button" class="gc-step-item ${step === 3 ? "active" : ""}" onclick="window.setGuidedCreatorStep(3)">
        <span class="gc-step-num">03</span>
        <span class="gc-step-label">剧情、规则与触发</span>
      </button>
    </div>

    <div class="modal-body gc-modal-body">
      ${stepBodyHtml}
    </div>

    <div class="modal-footer" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
      <div style="display:flex;gap:6px;align-items:center;">
        ${step > 1 ? `<button type="button" class="btn btn-sm btn-secondary" onclick="window.setGuidedCreatorStep(${step - 1})">← 上一步</button>` : ""}
        ${step < 3 ? `<button type="button" class="btn btn-sm btn-secondary" onclick="window.setGuidedCreatorStep(${step + 1})">下一步 →</button>` : ""}
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
        <button type="button" class="btn btn-sm btn-outline-secondary" onclick="window.exportDraftGameCard('guided', 'png')" title="导出为可分享的 PNG 海报游戏卡（可直接导入本工作台或 SillyTavern 酒馆）">导出 PNG 卡</button>
        <button type="button" class="btn btn-sm btn-outline-secondary" onclick="window.exportDraftGameCard('guided', 'json')" title="导出为 JSON 游戏卡">导出 JSON</button>
        <button type="button" class="btn btn-sm btn-primary" style="padding:7px 18px;font-weight:700;" onclick="window.submitGuidedGameCard()">
          ${isEditing ? "保存游戏卡" : "创建并游玩"}
        </button>
      </div>
    </div>
  `;

  if (typeof window.syncAllAiAssistModelSelects === "function") {
    window.syncAllAiAssistModelSelects();
  }
  const modal = document.getElementById("guidedGameCardModal");
  if (typeof window.translateSubtree === "function" && modal) {
    window.translateSubtree(modal);
  }
}
