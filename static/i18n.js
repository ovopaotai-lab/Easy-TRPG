// =========================================================================
// AI TRPG Workbench — Bilingual (ZH / EN) Auto-Detect & Live i18n Engine
// =========================================================================

(function () {
  const STORAGE_KEY = "trpg_lang";

  // 1. Exact String Dictionary (Normalized trimmed text -> English)
  const EXACT_DICT = {
    // App Title & Header / Sidebar
    "AI 跑团工作台": "AI TRPG Workbench",
    "酒馆工作台": "Tavern Workbench",
    "● 免登录直连模式": "● Direct Play Mode",
    "● 纯净免登录版": "● Pure Edition",
    "● 在线": "● Online",
    "Language": "Language",
    "Language / 选择语言": "Language / 选择语言",
    "Switch Language / 切换语言": "Switch Language / 切换语言",
    "中文": "中文",
    "🇨🇳 简体中文": "🇨🇳 简体中文",
    "🇺🇸 English": "🇺🇸 English",
    "收起侧栏": "Collapse Sidebar",
    "收起/展开侧栏": "Toggle Sidebar",
    "切换深色/浅色主题": "Toggle Dark/Light Theme",
    "全局设置": "Global Settings",
    "⚙️ 设置": "⚙️ Settings",
    "设置": "Settings",
    "💰 模型列表": "💰 Models",
    "💰 模型列表与价格": "💰 Models & Pricing",
    "模型列表与价格": "Models & Pricing",
    "🪪 角色卡": "🪪 Cards",
    "🪪 角色卡设置": "🪪 Character Cards",
    "角色卡设置": "Character Cards",
    "角色卡设置（新建 / 导入 / 编辑 / 导出 / 删除）": "Character Card Manager (Create / Import / Edit / Export / Delete)",
    "🪪 角色卡设置（支持简易角色卡 & OpenTavern 高级角色卡）": "🪪 Character Card Manager (Simple & OpenTavern Advanced Cards)",
    "🪪 选择角色卡发送": "🪪 Select Character Cards to Send",
    "选择角色卡随消息发送": "Select Character Cards to Send with Message",
    "🖼️ 图库": "🖼️ Gallery",
    "🖼️ 素材图库": "🖼️ Asset Gallery",
    "素材图库": "Asset Gallery",
    "🌐 访问地址": "🌐 Access URLs",
    "访问地址": "Access URLs",
    "🔍 日志": "🔍 Logs",
    "🔍 提示词日志": "🔍 Prompt Logs",
    "提示词日志": "Prompt Logs",
    "提示词与运行日志": "Prompt & Runtime Logs",
    "新建游戏(快速)": "Quick New",
    "新建游戏(高级)": "Adv. New",
    "✨ 新建游戏 (高级)": "✨ New Game (Advanced)",
    "直接新建空白游戏": "Create a Blank Game Directly",
    "沿用已有游戏或模板创建并修改/AI润色": "Create from Existing Game or Template with AI Polish",
    "对话列表": "Chat Sessions",
    "新建对话": "New Chat",
    "未命名对话": "Untitled Chat",
    "默认游戏": "Default Game",
    "未命名游戏": "Untitled Game",
    "未命名角色": "Unnamed Character",
    "未命名栏位": "Unnamed Field",
    "点击或双击直接修改游戏名称": "Click or double-click to rename game",
    "修改对话名称": "Rename Chat",
    "双击直接重命名": "Double-click to rename",
    "重命名": "Rename",
    "重命名游戏": "Rename Game",
    "删除对话": "Delete Chat",
    "展开列表": "Expand List",
    "更多操作": "More Actions",
    "🛠️ 游戏设置": "🛠️ Setup",
    "📁 游戏设置": "📁 Game Settings",
    "游戏设置": "Game Settings",
    "游戏设定": "Game Settings",
    "选择当前对话模型": "Select Model for Current Chat",
    "当前上下文 / 最大上下文": "Current Context / Max Context",
    "上下文": "Context",
    "⚡ 压缩上下文": "⚡ Compress",
    "压缩上下文": "Compress Context",
    "📖 前情备忘": "📖 Summary",
    "前情备忘": "Story Summary",
    "查看或手动编写前情备忘": "View or Edit Story Summary",
    "已生成前情备忘（点击展开）": "Story Summary Available (Click to Expand)",
    "🗑️ 清空": "🗑️ Clear",
    "🗑️ 清空当前对话": "🗑️ Clear Current Chat",
    "清空当前对话": "Clear Current Chat",
    "👤 账号信息": "👤 Account Info",
    "账号信息": "Account Info",
    "🚪 退出登录": "🚪 Log Out",
    "退出登录": "Log Out",
    "🔑 修改密码": "🔑 Change Password",

    // Summary Card & Welcome Box
    "🤖 总结模型:": "🤖 Summary Model:",
    "选择前情备忘总结使用的 AI 模型": "Select AI model for story summarization",
    "选择压缩上下文使用的 AI 模型": "Select AI model for context compression",
    "⚡ AI 总结": "⚡ AI Summarize",
    "使用所选 AI 模型重新提炼前情备忘": "Re-summarize story context using selected AI model",
    "✏️ 编辑": "✏️ Edit",
    "✕ 收起": "✕ Collapse",
    "记录当前剧情与角色状态...": "Record current plot progress and character status...",
    "取消": "Cancel",
    "💾 保存": "💾 Save",
    "暂无前情提要（当对话超过设定的上下文轮数后，系统将自动提炼关键剧情、线索与角色状态备忘）。": "No story summary yet (When the conversation exceeds the context limit, key plot points and character states will be summarized automatically).",
    "开始对话": "Start Adventure",
    "选择左侧游戏或直接发送消息开始。": "Select a game on the left or send a message below to begin.",
    "在下方输入你的角色卡或行动指令，或直接点击预设开场白开启冒险。": "Enter your character sheet or action below, or click a preset opening greeting to start your adventure.",
    "选择开场白开启冒险": "Choose an Opening Greeting to Start",
    "（点击卡片直接发送，或点击「修改后发送」微调内容）": "(Click a card to send directly, or click 'Edit & Send' to customize)",
    "🚀 直接发送": "🚀 Send Now",
    "一键直接发送此开场白": "Send this opening greeting directly",
    "🎲 掷骰发送": "🎲 Roll & Send",
    "投掷 1d100 并发送此开场白": "Roll 1D100 and send this opening greeting",
    "✏️ 修改后发送": "✏️ Edit & Send",
    "在卡片内或下方输入框修改一部分内容后再发送": "Edit the greeting before sending",
    "在此微调开场白内容后发送...": "Customize the opening greeting here before sending...",
    "💡 也已同步填入底部输入框，可直接改完点发送": "💡 Also copied to the bottom input box for quick editing",
    "🚀 发送修改后的开场白": "🚀 Send Edited Greeting",
    "点击卡片直接发送此开场白，或点击右侧按钮修改后发送": "Click card to send directly, or use buttons on the right to edit first",
    "⬇ 回到最新": "⬇ Jump to Latest",
    "滚动到最新消息": "Scroll to latest message",

    // Bottom Input & Toolbar
    "已选 0 张角色卡": "0 character cards selected",
    "已就绪 0 张图片": "0 images ready",
    "已选 0 张图片": "0 images selected",
    "清空已选": "Clear Selected",
    "清空图片": "Clear Images",
    "移除此图": "Remove Image",
    "从待发送移除": "Remove from pending",
    "🎲 D100掷骰并发送": "🎲 D100 & Send",
    "投掷 1D100 并发送": "Roll 1D100 and send",
    "📷 上传图片": "📷 Upload",
    "上传图片": "Upload Image",
    "🔄 重新生成": "🔄 Regenerate",
    "重新生成": "Regenerate",
    "⏹ 停止": "⏹ Stop",
    "停止生成": "Stop Generation",
    "输入内容...（Enter 发送，Shift+Enter 换行）": "Type your action or message... (Enter to send, Shift+Enter for new line)",
    "发送": "Send",
    "发送 (Enter)": "Send (Enter)",
    "🚀 发送": "🚀 Send",

    // Message Bubble Actions & Rich Content
    "🌿 分支": "🌿 Branch",
    "从此处分叉创建新对话": "Create a new branched chat from here",
    "📋 复制": "📋 Copy",
    "复制": "Copy",
    "🗑️ 删除": "🗑️ Delete",
    "✨ 保存并重新生成": "✨ Save & Regenerate",
    "💾 仅保存文本": "💾 Save Text Only",
    "💾 保存修改": "💾 Save Changes",
    "🔄 重新生成本处": "🔄 Regenerate Here",
    "左右拖拽调整消息气泡宽度比例（双击恢复默认）": "Drag left/right to resize message bubble width (double-click to reset)",
    "🧠 正在推演世界线与构思剧情...": "🧠 Simulating worldline & crafting story...",
    "🧠 AI 剧情推演与构思过程": "🧠 AI Story Reasoning & Thought Process",
    "✨ HTML/CSS 渲染": "✨ HTML/CSS Render",
    "👁️ 渲染效果": "👁️ Preview",
    "💻 源码": "💻 Source",
    "普通发送该行动": "Send this action normally",
    "投掷 1d100 检定并附带该行动发送": "Roll 1D100 check and send with this action",
    "点击直接发送该选项（或右侧点击掷骰发送）": "Click to send this choice directly (or click dice on the right to roll & send)",
    "点击在下方输入框填写自定义行动": "Click to type a custom action in the input box below",
    "✏️ 点击输入": "✏️ Custom Input",
    "KP / 主持人": "KP / Game Master",
    "玩家": "Player",

    // Global Settings Modal (#settingsModal)
    "API 地址 (Base URL)：": "API Base URL:",
    "API 密钥 (API Key)：": "API Key:",
    "默认模型：": "Default Model:",
    "🔄 刷新列表": "🔄 Refresh List",
    "⏳ 刷新中...": "⏳ Refreshing...",
    "手动填写模型 ID": "Manually Enter Model ID",
    "输入模型 ID": "Enter Model ID",
    "尚未配置模型，请填写 API 地址与密钥后点击「🔄 刷新列表」，或勾选「手动填写模型 ID」": "No model configured. Enter API Base URL & Key then click '🔄 Refresh List', or check 'Manually Enter Model ID'",
    "🖥️ 本地模型接口": "🖥️ Local AI Endpoint",
    "⚡ 自动探测本机端口 (11434 / 8080 / 1234)": "⚡ Auto-Detect Local Ports (11434 / 8080 / 1234)",
    "✍️ 手动填写本地接口与模型": "✍️ Manually Enter Local URL & Model",
    "已启用自动扫描：点击上方「🔄 刷新列表」将自动发现本机运行中的 Ollama (11434)、llama.cpp / Strata (8080) 或 LM Studio (1234) 模型。": "Auto-Scan enabled: Click '🔄 Refresh List' above to automatically discover local models running on Ollama (11434), llama.cpp / Strata (8080), or LM Studio (1234).",
    "本地接口地址 (Local URL)：": "Local Endpoint URL:",
    "指定本地模型 ID (可选)：": "Local Model ID (Optional):",
    "请输入 API 接口地址": "Enter API Base URL",
    "请输入 API 密钥": "Enter API Key",
    "请输入本地接口地址": "Enter Local Endpoint URL",
    "留空则自动拉取模型列表": "Leave blank to auto-fetch model list",
    "可选，请输入代理地址": "Optional, enter proxy address",
    "如 qwen2.5:14b（留空则自动拉取）": "Leave blank to auto-fetch",
    "网络代理 (Proxy)：": "Network Proxy:",
    "可选，如 http://127.0.0.1:8080": "Optional, enter proxy address",
    "启用代理": "Enable Proxy",
    "🎛️ 全局默认参数": "🎛️ Global Default Parameters",
    "🔄 同步到所有游戏": "🔄 Sync to All Games",
    "将当前全局参数同步至所有游戏": "Sync current global parameters to all games",
    "↺ 恢复默认": "↺ Reset Defaults",
    "温度 (Temperature)": "Temperature",
    "控制输出随机性（默认 0.68）": "Controls output randomness (default 0.68)",
    "控制输出随机性（默认 0.85）": "Controls output randomness (default 0.68)",
    "重复惩罚 (Repetition Penalty)": "Repetition Penalty",
    "抑制重复词句（默认 1.05）": "Penalizes repetitive phrases (default 1.05)",
    "抑制重复词句（默认 1.10）": "Penalizes repetitive phrases (default 1.05)",
    "频率惩罚 (Frequency Penalty)": "Frequency Penalty",
    "按词频降低重复（默认 0.00，防碎句）": "Reduces repetition by word frequency (default 0.00, prevents choppy prose)",
    "按词频降低重复（默认 0.15）": "Reduces repetition by word frequency (default 0.00)",
    "存在惩罚 (Presence Penalty)": "Presence Penalty",
    "控制话题推进与防复读（默认 0.25）": "Encourages new topics and prevents repetition (default 0.25)",
    "控制话题发散度（默认 0.00）": "Encourages new topics (default 0.25)",
    "核采样 (Top-P)": "Top-P (Nucleus Sampling)",
    "累积概率采样阈值（默认 0.90）": "Cumulative probability threshold (default 0.90)",
    "累积概率采样阈值（默认 0.95）": "Cumulative probability threshold (default 0.90)",
    "候选词数 (Top-K)": "Top-K",
    "每步保留候选词数量（默认 40）": "Number of top tokens kept per step (default 40)",
    "最小概率 (Min-P)": "Min-P",
    "过滤低概率词阈值（默认 0.06）": "Minimum probability threshold (default 0.06)",
    "过滤低概率词阈值（默认 0.05）": "Minimum probability threshold (default 0.06)",
    "单次最大生成长度 (Max Tokens)": "Max Output Tokens",
    "单次最大生成长度（最大 64k / 65536，默认 12288）": "Max tokens per response (up to 64k / 65536, default 12288)",
    "单次最大生成长度（最大 64k / 65536，默认 4096）": "Max tokens per response (up to 64k / 65536, default 12288)",
    "最大 64k (65536)": "Max 64k (65536)",
    "上下文计算方式": "Context Calculation Mode",
    "按轮数算 (Turns)": "By Turns",
    "按 Token 数算 (Tokens)": "By Tokens",
    "上下文轮数 (Context Turns)": "Context Turns",
    "上下文轮数：": "Context Turns:",
    "保留最近": "Keep latest",
    "条消息": "messages",
    "最大上下文 Token 长度 (Max Context k)": "Max Context Length (k Tokens)",
    "单位 k（默认 110k，安全不爆显存）": "Unit in k (default 110k, safe VRAM headroom)",
    "单位 k（如 32k、128k、256k；按 Token 算时以此为截断上限）": "Unit in k (e.g. 32k, 110k, 256k; used as truncation limit in Token mode)",
    "单位 k（按 Token 算时以此为截断上限）": "Unit in k (used as truncation limit in Token mode)",
    "压缩保留消息数 (Keep Recent)": "Keep Recent Messages on Compress",
    "压缩时保留最近消息条数（默认 6）": "Recent messages kept un-summarized when compressing (default 6)",
    "思考预算 (Thinking Budget)": "Thinking Budget (Tokens)",
    "推理模型思考 Token 预算（默认 1024，快速起笔）": "Reasoning token budget for thinking models (default 1024, fast start)",
    "推理模型思考 Token 预算（默认 2048，最大 64k）": "Reasoning token budget for thinking models (default 1024, max 64k)",
    "超出上下文上限（轮数或 Token 数）时自动压缩早期对话至前情备忘": "Automatically compress older messages into Story Summary when exceeding context limit",
    "超出轮数后自动压缩早期对话至前情备忘": "Automatically compress older messages into Story Summary when exceeding turn limit",
    "公网地址：": "Public URL:",
    "局域网地址：": "LAN URL:",
    "本机地址：": "Local URL:",
    "检测中...": "Detecting...",
    "未检测到公网隧道": "No public tunnel detected",
    "📦 数据备份：一键导出与文件夹导入": "📦 Data Backup: 1-Click Export & Folder Import",
    "全选 / 取消全选": "Select All / Deselect All",
    "可自由勾选需要导出或导入的项目（支持单选具体游戏与对话记录，也支持一键全选）：": "Select items to export or import (supports selecting individual games/chats or selecting all):",
    "展开勾选 ▾": "Expand ▾",
    "(全部)": "(All)",
    "游戏对话记录": "Game Chat History",
    "全局设置与预设": "Global Settings & Presets",
    "(含API与参数)": "(Includes API & Params)",
    "图片与图库素材": "Images & Gallery Assets",
    "(0 张)": "(0 images)",
    "(全部日志)": "(All logs)",
    "📤 一键导出到文件夹": "📤 1-Click Export to Folder",
    "输入或选择导出目标文件夹路径（留空则自动生成备份文件夹）": "Enter or browse export folder path (leave blank to auto-generate backup folder)",
    "📂 浏览选择文件夹": "📂 Browse Folder",
    "🗂️ 打开文件夹": "🗂️ Open Folder",
    "在资源管理器中打开该文件夹": "Open this folder in File Explorer",
    "🚀 一键导出所选数据": "🚀 Export Selected Data",
    "📥 从文件夹导入数据（按上方勾选项导入）": "📥 Import Data from Folder (Imports checked categories above)",
    "输入或选择要导入的备份文件夹路径": "Enter or browse backup folder path to import",
    "📥 从该路径导入": "📥 Import from Path",
    "🌐 浏览器选择文件夹导入": "🌐 Upload Folder via Browser",
    "直接通过浏览器选择整个本地文件夹上传导入（支持手机/远程电脑）": "Select an entire local folder via browser to upload and import (supports mobile/remote PC)",
    "💾 保存设置": "💾 Save Settings",

    // Models & Pricing Modal (#pricingModal)
    "🔍 搜索模型...": "🔍 Search models...",
    "共 0 个模型": "0 models total",
    "全部": "All",
    "本地": "Local",
    "本地模型": "Local Models",
    "常用 API 模型": "Recommended API Models",
    "其他": "Other",
    "其它": "Other",
    "API · DeepSeek": "API · DeepSeek",
    "API · 其他": "API · Other",
    "API · 其它": "API · Other",
    "API 按次": "API Per-Call",
    "API 按量": "API Token-Based",
    "模型": "Model",
    "类型": "Type",
    "价格": "Pricing",
    "操作": "Action",
    "✓ 当前": "✓ Active",
    "选用": "Select",
    "关闭": "Close",
    "加载中...": "Loading...",
    "读取中...": "Loading...",
    "暂无可用模型，请先在设置中配置 API 地址与密钥并点击「刷新列表」": "No models available. Please configure your API URL & Key or Local AI Endpoint in Settings and click 'Refresh List'.",
    "⚙️ 请先在设置中配置 API / 模型": "⚙️ Configure API / Local Model in Settings first",
    "⚙️ 请先配置 API 并刷新，或手动填写模型 ID": "⚙️ Configure API & Refresh, or manually enter Model ID",

    // Studio Workbench & Advanced Game Creator (enterprise.js)
    "正在加载游戏设置...": "Loading game settings...",
    "📐 标准宽度": "📐 Standard Width",
    "↔️ 宽屏": "↔️ Wide View",
    "✕ 关闭": "✕ Close",
    "🗑️ 删除游戏": "🗑️ Delete Game",
    "修改后自动或点击右侧保存生效": "Changes auto-save on blur or click Save on the right",
    "✨ AI 润色助手": "✨ AI Polish Assistant",
    "（用于下方简介与提示词润色）": "(Used for polishing description & prompts below)",
    "🤖 润色模型:": "🤖 Polish Model:",
    "选择游戏设置中 AI 润色使用的模型": "Select AI model for polishing in Game Settings",
    "选择新建游戏 AI 润色使用的模型": "Select AI model for polishing in New Game editor",
    "🏷️ 游戏信息与外观": "🏷️ Game Info & Appearance",
    "1. 🏷️ 游戏信息与外观": "1. 🏷️ Game Info & Appearance",
    "启用 HTML/CSS": "Enable HTML/CSS",
    "游戏图标（可自定义或上传图片）": "Game Icon (Emoji or upload custom image)",
    "游戏图标（可自定义可上传）": "Game Icon (Emoji or upload image)",
    "输入图标或URL": "Emoji or Image URL",
    "📤 上传": "📤 Upload",
    "上传自定义图片作为游戏图标": "Upload custom image as game icon",
    "游戏名称": "Game Name",
    "游戏名称：": "Game Name:",
    "输入游戏名称": "Enter game name",
    "输入游戏名称...": "Enter game name...",
    "游戏简介": "Game Description",
    "✨ AI 润色": "✨ AI Polish",
    "✨ AI 润色简介": "✨ AI Polish Description",
    "✨ AI 润色提示词": "✨ AI Polish Prompt",
    "⏳ 润色中...": "⏳ Polishing...",
    "输入游戏简介...": "Enter game description...",
    "标签（多个标签用逗号分隔）": "Tags (comma-separated)",
    "标签（逗号分隔）": "Tags (comma-separated)",
    "标签（逗号分隔，选填）": "Tags (comma-separated, optional)",
    "如：奇幻, 跑团, 冒险": "e.g. Fantasy, TRPG, Adventure",
    "奇幻, 跑团": "Fantasy, TRPG",
    "游戏背景（游玩时的聊天背景，支持自定义上传）": "Game Background (Chat wallpaper during play, supports upload)",
    "游戏背景（游玩时的背景，支持自定义上传）": "Game Background (Wallpaper during play, supports upload)",
    "默认": "Default",
    "点击放大预览背景": "Click to enlarge background preview",
    "输入背景图 URL 或点击右侧上传图片...": "Enter background image URL or click Upload on the right...",
    "输入背景图片地址或点击右侧上传...": "Enter background image URL or click Upload on the right...",
    "📤 上传背景": "📤 Upload BG",
    "🗑️ 清除": "🗑️ Clear",
    "🎬 开场白设置": "🎬 Opening Greetings",
    "（可设置多个，新建对话后显示在游戏页，支持一键发送或修改后发送）": "(Add multiple routes/greetings shown on new chats; send directly or edit before sending)",
    "➕ 新增开场白": "➕ Add Greeting",
    "开场白名称/路线标题（可选，如：标准开局 / 潜入路线）": "Greeting title / route name (optional, e.g. Standard Start / Stealth Route)",
    "开场白名称/路线标题（可选）": "Greeting title / route name (optional)",
    "删除此开场白": "Delete this greeting",
    "输入开场白内容（新建对话后将作为卡片展示在游戏页中，点击可快速发送或修改后发送）...": "Enter opening greeting content (displayed as a selectable card in new chats)...",
    "输入开场白内容...": "Enter opening greeting content...",
    "暂无开场白，点击右上角": "No opening greetings yet. Click",
    "添加（可添加多个不同剧情路线或初始行动指令）": "in the top-right to add multiple story routes or starting actions.",
    "添加": "to add one.",
    "🔗 前置提示词": "🔗 Prefix Prompt",
    "2. 🔗 前置提示词": "2. 🔗 Prefix Prompt",
    "前置提示词": "Prefix Prompt",
    "自动附加在每次玩家发言开头...": "Automatically prepended to every player message...",
    "自动附加在每次发言开头": "Automatically prepended to every player message",
    "附加在每次发言开头...": "Prepended to every player message...",
    "🧠 提示词": "🧠 System Prompt",
    "3. 🧠 提示词": "3. 🧠 System Prompt",
    "提示词": "System Prompt",
    "编写角色设定、背景规则、文风要求等...": "Write world rules, GM instructions, character settings, writing style...",
    "编写角色设定、世界观规则、文风要求等...": "Write world rules, GM instructions, character settings, writing style...",
    "输入提示词...": "Enter system prompt...",
    "本栏润色要求（可选）...": "Polish instructions for this field (optional)...",
    "🔚 后置提示词": "🔚 Postfix Prompt",
    "4. 🔚 后置提示词": "4. 🔚 Postfix Prompt",
    "后置提示词": "Postfix Prompt",
    "自动附加在每次发言末尾...": "Automatically appended to the end of every player message...",
    "自动附加在每次发言末尾": "Automatically appended to the end of every player message",
    "附加在每次发言末尾...": "Appended to the end of every player message...",
    "🎛️ 模型参数": "🎛️ Model Parameters",
    "5. 🎛️ 模型参数": "5. 🎛️ Model Parameters",
    "📥 从全局默认同步": "📥 Pull from Global Defaults",
    "📤 设为全局默认": "📤 Save as Global Defaults",
    "🔗 跟随全局默认参数": "🔗 Follow Global Default Parameters",
    "预设：": "Presets:",
    "小说 (0.68)": "Novel (0.68)",
    "严谨 (0.62)": "Strict (0.62)",
    "发散 (0.75)": "Creative (0.75)",
    "小说 (0.88)": "Novel (0.68)",
    "严谨 (0.65)": "Strict (0.62)",
    "发散 (1.12)": "Creative (0.75)",
    "✨ 新建游戏 (高级) — 选择要沿用的游戏卡片": "✨ New Game (Advanced) — Choose a Base Game or Template",
    "➕ 新建游戏": "➕ New Game",
    "新建游戏": "New Game",
    "直接从空白创建新游戏，或在下方选择现有游戏沿用模板": "Create a new game from scratch, or use an existing game below as a template",
    "➕ 从空白开始高级创建 (支持 AI 润色)": "➕ Start from Blank Template (with AI Polish)",
    "我的游戏": "My Games",
    "预设模组": "Preset Modules",
    "当前使用中": "Currently Active",
    "暂无简介": "No description",
    "暂无描述": "No description",
    "📋 沿用该游戏 (修改 / AI润色)": "📋 Use as Template (Edit / AI Polish)",
    "⚡ 直接复制": "⚡ Quick Duplicate",
    "⬅️ 返回重选游戏卡片": "⬅️ Back to Game Cards",
    "⬅️ 返回游戏卡片列表": "⬅️ Back to Game Cards",
    "已复制": "Copied all settings from",
    "的全部设置，可逐栏修改或点击": "— edit fields below or click",
    "润色/改写方向（可选）...": "Polish / rewrite direction (optional)...",
    "✨ 一键润色全部栏": "✨ Polish All Fields",
    "✨ AI 一键润色全游戏": "✨ AI Polish Entire Game",
    "⏳ 正在润色全游戏...": "⏳ Polishing entire game...",
    "✅ 完成并创建新游戏": "✅ Create New Game",
    "✅ 完成修改并创建新游戏": "✅ Save & Create New Game",
    "原游戏": "Original Game",
    "空白模板": "Blank Template",

    // Character Cards Modal & Editor
    "点击下方角色即可选中或取消，选中的角色卡将随本条回复一同发送。": "Click a character card below to select or deselect it. Selected cards will be attached to your next message.",
    "🔍 搜索角色卡名称或标签...": "🔍 Search character name or tags...",
    "🔍 搜索角色名称或标签...": "🔍 Search character name or tags...",
    "当前已选 0 张角色卡": "0 character cards currently selected",
    "✅ 确认选择": "✅ Confirm Selection",
    "完成": "Done",
    "只需设置角色图片与基本信息（名称、身份、性别/年龄、基本简介）；": "Quickly set up character image and basic info (Name, Identity, Gender/Age, Summary); ",
    "提供完整 OpenTavern 标准字段。发送回复时可在输入框上方点击「🪪 角色卡」选择角色发送。": "provides full OpenTavern standard fields. Click '🪪 Character Cards' above the input box to attach cards when chatting.",
    "简易角色卡": "Simple Character Card",
    "高级角色卡": "Advanced Character Card",
    "OpenTavern 高级角色卡": "OpenTavern Advanced Card",
    "⚡ 新建简易角色卡": "⚡ New Simple Card",
    "🛠️ 新建高级角色卡 (OpenTavern)": "🛠️ New Advanced Card (OpenTavern)",
    "🛠️ 新建高级角色卡 (OpenTavern 格式)": "🛠️ New Advanced Card (OpenTavern)",
    "📥 导入 (.json / .png)": "📥 Import (.json / .png)",
    "📥 导入 .json / .png": "📥 Import .json / .png",
    "共 0 张角色卡": "0 character cards total",
    "当前暂无可选角色卡": "No character cards available",
    "角色卡库为空": "Character Card Library is Empty",
    "没有找到匹配的角色卡": "No matching character cards found",
    "请在左侧功能栏点击「🪪 角色卡设置」新建或导入角色卡后再来选择发送。": "Click '🪪 Character Cards' in the left sidebar to create or import a character card first.",
    "你可以快速创建只包含角色图片与基本信息的": "You can quickly create a ",
    "，也可以创建或导入完整的": ", or create/import a full ",
    "⚡ 简易": "⚡ Simple",
    "⚡ 简易卡": "⚡ Simple",
    "🛠️ 高级": "🛠️ Advanced",
    "🛠️ 高级卡": "🛠️ Advanced",
    "✓ 已选择（点击取消）": "✓ Selected (Click to Deselect)",
    "➕ 选择此角色发送": "➕ Select to Send",
    "✏️ 编辑角色卡": "✏️ Edit Character Card",
    "⚡ 简易角色卡（仅角色图片 + 基本信息）": "⚡ Simple Card (Avatar + Basic Info)",
    "🛠️ 高级角色卡（OpenTavern 完整设定）": "🛠️ Advanced Card (Full OpenTavern Spec)",
    "✨ AI 辅助自动填卡": "✨ AI Auto-Fill Character Card",
    "（支持文字描述、多张参考图识别 + 实时联网搜索百科/人设）": "(Supports text description, multi-image vision & web search)",
    "🤖 模型:": "🤖 Model:",
    "选择 AI 自动填卡使用的模型": "Select AI model for auto-filling character card",
    "🌐 启用联网搜索": "🌐 Enable Web Search",
    "📷 附带图片": "📷 Attach Images",
    "上传 1 张或多张角色立绘、设定图或截图供 AI 识别（也支持在输入框 Ctrl+V 粘贴图片）": "Upload 1 or more character illustrations or reference sheets for AI vision (Ctrl+V paste also supported)",
    "输入角色名、所属作品或人设需求，或上传/粘贴多张参考图让 AI 识图填卡...": "Enter character name, series, or persona prompt, or upload/paste reference images for AI auto-fill...",
    "✨ AI 一键生成填充": "✨ AI Generate & Fill",
    "⏳ 正在识别与生成...": "⏳ Generating...",
    "点击上传角色图片/立绘头像": "Click to upload character portrait/avatar",
    "📷 上传角色图片": "📷 Upload Portrait",
    "角色名称 (Name)": "Character Name",
    "输入角色名称": "Enter character name",
    "标签（逗号分隔，选填）": "Tags (comma-separated, optional)",
    "如：队友, 魔法师, 傲娇": "e.g. Companion, Mage, Tsundere",
    "🧩 角色属性与设定信息栏": "🧩 Character Attributes & Info Fields",
    "（点击栏位名称可直接改名，可自由增删）": "(Click any field title to rename, add or remove freely)",
    "➕ 新建单行输入栏": "➕ Add Single-Line Field",
    "➕ 新建多行输入栏": "➕ Add Multi-Line Field",
    "📋 填入 OpenTavern 标准六大系统空白模板": "📋 Fill Blank OpenTavern 6-System Template",
    "填写角色的背景故事、身世经历、核心动机或其他补充设定...": "Write character backstory, experiences, core motivations, or extra notes...",
    "角色外貌、穿搭、三层性格、说话方式、背景与动机、人际关系与对{{user}}的态度...": "Appearance, outfits, 3-layer personality, speech style, backstory & relationship with {{user}}...",
    "性格 (Personality)": "Personality",
    "角色核心性格概括（外在表现、内在性格、核心渴望）...": "Core personality summary (outer traits, inner nature, core desires)...",
    "场景 (Scenario)": "Scenario",
    "当前所处时间线、背景环境与互动关系设定...": "Current timeline, environment, and interaction context...",
    "开场白 (First Message)": "First Message",
    "角色默认开场白（支持环境描写、动作神态与台词）...": "Default opening greeting (environment description, actions, and dialogue)...",
    "备用开场白 (Alternate Greetings)": "Alternate Greetings",
    "+ 添加": "+ Add",
    "默认开场白在上方。这里是可切换的额外开场，会写入": "Default first message is above. Extra greetings here are saved into",
    "输入备用开场白 (alternate_greetings)...": "Enter alternate greeting...",
    "删除该条备用开场白": "Delete this alternate greeting",
    "示例对话 (Example Messages)": "Example Messages (mes_example)",
    "系统提示词 (System Prompt)": "Character System Prompt",
    "角色专属系统提示词（选填）...": "Character-specific system prompt (optional)...",
    "历史后指令 (Post-History Instructions)": "Post-History Instructions",
    "注入在历史记录之后的指令（选填）...": "Instructions injected after chat history (optional)...",
    "Depth Prompt（角色笔记 @ Depth）": "Depth Prompt (Character Note @ Depth)",
    "注入到聊天记录指定深度，对应角色卡": "Injected at a specific chat history depth, mapped to",
    "深度 (Depth)": "Depth",
    "角色 (Role)": "Role",
    "需要按深度注入的角色笔记或防 OOC 提醒...": "Character note or anti-OOC reminder injected at depth...",
    "作者备注 (Creator Notes)": "Creator Notes",
    "角色卡编写说明、搭配世界书建议、版本备注等...": "Creator notes, recommended worldbooks, version notes...",
    "🗑️ 删除角色卡": "🗑️ Delete Card",
    "删除角色卡": "Delete Character Card",
    "💾 保存角色卡": "💾 Save Character Card",
    "导出 OpenTavern/SillyTavern JSON": "Export OpenTavern/SillyTavern JSON",
    "📤 导出": "📤 Export",
    "属性": "Attribute",
    "身份": "Identity",
    "身份 / 职业": "Identity / Class",
    "性别": "Gender",
    "性别 / 种族": "Gender / Race",
    "年龄": "Age",
    "年龄 / 身高": "Age / Height",
    "种族": "Race",
    "职业": "Class",
    "外貌特征与穿搭": "Appearance & Outfit",
    "性格特点": "Personality Traits",
    "说话口吻与口癖": "Speech Style & Catchphrases",
    "能力技能与装备": "Skills, Abilities & Gear",
    "人际关系与态度": "Relationships & Attitude",
    "基本信息与角色简介": "Basic Info & Summary",
    "背景故事与补充设定": "Backstory & Additional Notes",
    "描述 (Description)": "Description",
    "单行": "1-Line",
    "多行": "Multi",
    "切换单行/多行输入框": "Toggle Single-Line / Multi-Line Input",
    "删除该输入栏": "Delete this field",
    "点击自定义此输入栏名称": "Click to rename this field",
    "点击可自定义该输入栏名称": "Click to customize field name",
    "输入栏名称（如：身份、属性、装备）": "Field Name (e.g. Identity, Stats, Gear)",
    "输入该项内容...": "Enter content...",
    "输入该项详细内容...": "Enter detailed content...",

    // Gallery Modal
    "对话中发送的图片或手动上传的图片将保存在此。": "Images sent in chats or uploaded manually are archived here.",
    "➕ 上传图片": "➕ Upload Image",
    "🧹 去重": "🧹 Deduplicate",
    "🧹 一键去重": "🧹 Deduplicate",
    "⏳ 去重中...": "⏳ Deduplicating...",
    "清理重复图片": "Clean up duplicate images",
    "全选": "Select All",
    "取消选择": "Deselect All",
    "📥 导入所选": "📥 Insert Selected",
    "📥 导入所选图片": "📥 Insert Selected Images",
    "📥 导入": "📥 Insert",
    "一键导入此图进对话框": "Insert this image into chat",
    "从素材库删除": "Delete from gallery",
    "点击勾选多张，或点右下角【📥 导入】一键插入对话": "Click to select multiple images, or click '📥 Insert' at bottom-right",
    "暂无图片": "No images in gallery",
    "⏳ 正在加载历史素材...": "⏳ Loading gallery assets...",
    "📂 全部素材": "📂 All Assets",
    "📁 默认图库": "📁 Default Gallery",
    "📁 角色立绘": "📁 Portraits",
    "📁 场景CG": "📁 Scene CGs",
    "📁 道具线索": "📁 Items & Clues",
    "默认图库": "Default Gallery",
    "角色立绘": "Portraits",
    "场景CG": "Scene CGs",
    "道具线索": "Items & Clues",

    // Prompt Log Modal & Dialogs
    "请先选择一个对话。": "Please select a chat session first.",
    "当前对话暂无请求记录。": "No prompt logs recorded for the current chat yet.",
    "🕒 时间：": "🕒 Time:",
    "🤖 模型：": "🤖 Model:",
    "提示": "Notice",
    "确定": "OK",
    "确认": "Confirm",
    "🗑️ 删除游戏确认": "🗑️ Confirm Delete Game",
    "确定要删除当前游戏吗？该游戏下的所有历史对话将自动安全移入【默认游戏】。": "Are you sure you want to delete the current game? All chat history under this game will be safely moved to [Default Game].",
    "默认游戏不可删除": "The Default Game cannot be deleted",
    "🗑️ 删除素材图片": "🗑️ Delete Gallery Image",
    "确定要从历史素材库中永久删除这张图片吗？": "Are you sure you want to permanently delete this image from the gallery?",
    "🗑️ 清空当前对话": "🗑️ Clear Current Chat",
    "确定要清空当前对话中的所有聊天记录与前情备忘吗？": "Are you sure you want to clear all messages and story summary in the current chat?",
    "🗑️ 删除单条消息": "🗑️ Delete Message",
    "确定要从记录中删除这条消息吗？": "Are you sure you want to delete this message?",
    "🗑️ 删除对话分支": "🗑️ Delete Chat Session",
    "确定要删除这个对话分支吗？此操作不可撤销。": "Are you sure you want to delete this chat session? This action cannot be undone.",

    // Toasts & Status Messages
    "✅ 全局系统与默认模型数值参数已保存": "✅ Global settings and default model parameters saved",
    "↺ 已恢复全局默认参数": "↺ Restored global default parameters",
    "已从全局默认参数同步": "Synced from global default parameters",
    "已设为全局默认参数": "Saved as global default parameters",
    "已恢复默认参数": "Restored default parameters",
    "已保存游戏设置": "Game settings saved",
    "已应用【小说】预设": "Applied [Novel] parameter preset",
    "已应用【严谨】预设": "Applied [Strict] parameter preset",
    "已应用【发散】预设": "Applied [Creative] parameter preset",
    "🗑️ 已删除该开场白": "🗑️ Opening greeting deleted",
    "✨ AI 润色完成": "✨ AI polish completed",
    "✨ AI 润色完成并已保存": "✨ AI polish completed & saved",
    "✨ 开场白 AI 润色完成": "✨ Opening greeting polished by AI",
    "✨ 开场白 AI 润色完成并已保存": "✨ Opening greeting polished & saved",
    "✨ 全部栏目 AI 润色完成并已保存！": "✨ All fields polished by AI & saved!",
    "✨ 全游戏已由 AI 润色完成！": "✨ Entire game polished by AI!",
    "🌿 已从此处创建新对话分支": "🌿 Created new chat branch from here",
    "消息已更新": "Message updated",
    "玩家发言已更新": "Player message updated",
    "已删除该条消息": "Message deleted",
    "已复制消息文本": "Message text copied",
    "已复制到剪贴板": "Copied to clipboard",
    "外网访问网址已复制": "Public URL copied",
    "局域网网址已复制": "LAN URL copied",
    "本机网址已复制": "Local URL copied",
    "游戏已删除": "Game deleted",
    "对话已删除": "Chat session deleted",
    "当前对话记录已清空": "Current chat history cleared",
    "✅ 前情提要备忘已保存": "✅ Story summary saved",
    "✅ 已浓缩早期对话并释放活跃上下文槽位！": "✅ Compressed older messages into Story Summary!",
    "当前消息较少，暂无需压缩": "Too few messages to compress yet",
    "🎲 正在思考与撰写剧情……": "🎲 Thinking and writing story...",
    "🎲 正在推演剧情与撰写回复……": "🎲 Simulating plot and writing response...",
    "🎲 正在重新推演世界线与撰写剧情……": "🎲 Re-simulating worldline and writing response...",
    "✨ 剧情回复已生成完毕！": "✨ Story response generated!",
    "✨ 已保存修改并开始重新生成回复...": "✨ Saved changes and regenerating response...",
    "🔄 正在重新生成本轮回复...": "🔄 Regenerating response...",
    "🔄 正在重新生成最新回复...": "🔄 Regenerating latest response...",
    "🔄 已中断当前生成并立即刷新重Roll！": "🔄 Aborted current generation and re-rolling immediately!",
    "请先选择或新建一个对话": "Please select or create a chat first",
    "当前对话尚无玩家行动，无法重新生成": "No player action in current chat to regenerate",
    "*(已手动停止生成)*": "*(Generation stopped manually)*",
    "✅ 一键导出成功！": "✅ 1-Click backup export succeeded!",
    "✅ 数据导入成功！正在刷新界面...": "✅ Backup imported! Refreshing UI...",
    "✅ 文件夹导入成功！正在刷新界面...": "✅ Folder imported! Refreshing UI...",
    "🗂️ 已在资源管理器中打开文件夹": "🗂️ Opened folder in File Explorer",
    "📂 正在打开文件夹选择窗口...": "📂 Opening folder picker dialog...",
    "⚠️ 请至少勾选一项要导出的数据！": "⚠️ Please check at least one data category to export!",
    "⚠️ 请至少勾选一项要导入的数据类型！": "⚠️ Please check at least one data category to import!",
    "⚠️ 请先输入或浏览选择要导入的备份文件夹路径！": "⚠️ Please enter or browse a backup folder path to import!",
    "📥 正在导入素材图片...": "📥 Inserting image from gallery...",
    "✅ 已导入素材图片进对话框": "✅ Inserted gallery image into chat",
    "✅ 上传完成，已永久归档至素材库": "✅ Upload complete & archived in gallery",
    "图片已从素材库删除": "Image deleted from gallery",
    "✅ 已删除角色卡": "✅ Character card deleted",
    "已删除角色卡": "Character card deleted",
    "📋 已填入 OpenTavern 标准六大系统空白角色卡格式模板": "📋 Filled OpenTavern 6-System blank character template",
    "未配置模型": "No Model Set",
    "上下文设置": "Context Settings",
    "共": "Total",
    "已选": "Selected",
    "张": "images",
    "张图片": "images",
    "条消息）": "messages)",
    "轮（": "turns (",
    "🤖 AI模型：": "🤖 Model:",
    "对话名称：": "Chat:",
    "原密码：": "Current Password:",
    "新密码（至少 6 位）：": "New Password (min 6 chars):",
    "输入原密码": "Enter current password",
    "输入新密码": "Enter new password",
    "当前连接：": "Current Connection:",
    "设备：": "Device:",
    "设备": "Device",
    "时间": "Time",
    "登录记录：": "Login History:",
    "未知设备": "Unknown Device",
    "暂无历史记录": "No history records",
    "AI 正在后台生成回复中...": "AI is generating a response in the background...",
    "有未读的新回复": "Unread new response",
    "拖拽缩放弹窗边框（双击恢复默认尺寸）": "Drag border to resize modal (double-click to reset size)",
    "拖拽调整宽度（双击重置）": "Drag to resize width (double-click to reset)",
    "拖拽调整高度（双击重置）": "Drag to resize height (double-click to reset)",
    "点击放大查看": "Click to enlarge",
    "点击查看角色卡设定": "Click to view character card details",
    "点击重新选择发送的角色卡": "Click to re-select character cards to send",
    "点击取消选择该角色卡": "Click to deselect this character card",
    "点击选择该角色卡随消息发送": "Click to select this character card to send with message",
    "编辑角色卡设定": "Edit character card details",
    "自定义此输入栏名称...": "Customize field name...",
    "身份 / 职业": "Identity / Class",
    "性别 / 种族": "Gender / Race",
    "年龄 / 身高": "Age / Height",
    "外貌特征与穿搭": "Appearance & Outfit",
    "性格特点": "Personality Traits",
    "说话口吻与口癖": "Speech Style & Catchphrases",
    "能力技能与装备": "Abilities, Skills & Gear",
    "人际关系与态度": "Relationships & Attitude",
    "背景故事与补充设定": "Backstory & Extra Notes",
    "描述 (Description)": "Description",
    "基本信息与角色简介": "Basic Info & Bio",
    "未检测到公网隧道": "No public tunnel detected",
    "读取中...": "Loading...",
    "外网访问网址已复制": "Public URL copied",
    "局域网网址已复制": "LAN URL copied",
    "本机网址已复制": "Local URL copied",
    "高清预览": "HD Preview",
    "⏳ 压缩中...": "⏳ Compressing...",
    "⚡ 压缩上下文": "⚡ Compress",
    "⏳ 总结中...": "⏳ Summarizing...",
    "当前使用中": "In Use",
    "🗑️ 清除": "🗑️ Clear",
    "✨ 已新建对话": "✨ New chat created",
    "🎯 已填入行动输入框": "🎯 Inserted into action input",
    "✏️ 请在下方输入框输入你的自定义行动": "✏️ Enter your custom action in the input box below",
    "✏️ 已展开开场白编辑框（同时已填入底部输入框），可修改后发送": "✏️ Opening message editor expanded (and copied to input box)",
    "📷 已粘贴参考图片到 AI 辅助填卡栏": "📷 Reference image pasted into AI Card Assistant",
    "💡 请先输入角色名称/人设需求，或上传至少 1 张角色参考图片！": "💡 Please enter a character name/concept or upload at least 1 reference image!",
    "💡 请先点击上方图片勾选，或直接点图片右下角【📥 导入】": "💡 Select images above or click [📥 Insert] on an image",
    "💬 后台分支对话已完成生成（点击左侧红点查看）": "💬 Background branch chat finished generating (click the red dot on the left)",
    "🧠 服务端后台正在深度识图与持续生成剧情中，请稍候……": "🧠 Server is analyzing images and generating story in background, please wait...",
    "上游模型响应超时或未返回内容，请点击【🔄 重新生成】重试": "Model timed out or returned empty response. Click [🔄 Regenerate] to retry.",
    "📐 已恢复前情备忘默认高度 (150px)": "📐 Restored summary height to default (150px)",
    "📐 已恢复左侧栏默认宽度 (288px)": "📐 Restored sidebar width to default (288px)",
    "📐 已恢复弹窗默认尺寸与居中位置": "📐 Restored modal size and position to default",
    "📐 已恢复消息气泡默认宽度比例 (88%)": "📐 Restored message bubble width to default (88%)",
    "📐 已恢复游戏列表默认高度 (126px)": "📐 Restored game list height to default (126px)",
    "📐 已恢复游戏设置默认分屏宽度 (540px)": "📐 Restored game studio width to default (540px)",
    "📐 已恢复行动输入框默认高度 (66px)": "📐 Restored action input height to default (66px)",
    "⚠️ 该 API 不支持自动拉取列表，请直接手动输入模型 ID": "⚠️ API did not return a model list. Please enter the Model ID manually.",
    "⚠️ 未能从该 API 自动拉取到模型列表，已自动展开下方输入框，请直接手动输入要调用的模型 ID（如": "⚠️ Could not auto-fetch model list from this API. Please enter the Model ID manually below (e.g.",
    "）。": ").",
    "✍️ 手动添加 API / 模型": "✍️ Add API / Model",
    "✍️ 手动添加 API 与模型": "✍️ Manually Add API & Model",
    "显示/隐藏密钥": "Show/Hide Key",
    "模型名称 (Model ID)：": "Model Name (Model ID):",
    "🔄 尝试从该接口拉取模型": "🔄 Try Fetching Models from Endpoint",
    "⏳ 正在拉取...": "⏳ Fetching...",
    "手动输入模型名称（如 deepseek-chat / gpt-4o / claude-3-7-sonnet）": "Enter Model ID manually (e.g. deepseek-chat / gpt-4o / claude-3-7-sonnet)",
    "👇 点击下方拉取到的模型可直接填入：": "👇 Click a fetched model below to fill:",
    "📌 已手动添加的模型（点击直接选用，点 ✕ 移除）：": "📌 Manually Added Models (click to select, ✕ to remove):",
    "✅ 保存并设为当前模型": "✅ Save & Set as Current Model",
    "手动添加的 API 模型": "Manually Added API Models",
    "移除此模型": "Remove this model",
    "💡 请先填写 API 地址 (Base URL)": "💡 Please enter the API Base URL first",
    "⚠️ 该接口未返回模型列表，请直接在下方输入框手动填写模型名称": "⚠️ Endpoint did not return a model list. Please enter the Model ID manually below.",
    "⚠️ 拉取失败，请直接手动输入模型名称": "⚠️ Fetch failed. Please enter the Model ID manually.",
    "💡 请输入要调用的模型名称（如 deepseek-chat / gpt-4o）": "💡 Please enter the Model ID to call (e.g. deepseek-chat / gpt-4o)",
    "🔌 接口协议 (API Protocol)：": "🔌 API Protocol:",
    "⚡ 自动识别 (默认推荐 · 智能适配中转站/官方/本地)": "⚡ Auto-Detect (Recommended · Relays / Official / Local)",
    "🔌 OpenAI 兼容协议 (通用中转 / DeepSeek / 硅基流动 / OpenRouter)": "🔌 OpenAI Compatible (Relays / DeepSeek / SiliconFlow / OpenRouter)",
    "✨ Google Gemini 官方协议 (AI Studio 直连 · 网址可留空)": "✨ Google Gemini Official (AI Studio · URL Optional)",
    "🎭 Anthropic Claude 官方协议 (Anthropic 直连 · 网址可留空)": "🎭 Anthropic Claude Official (Direct · URL Optional)",
    "🦙 Ollama 本地/局域网协议 (默认 11434 端口)": "🦙 Ollama Local / LAN Protocol (Default Port 11434)",
    "默认自动根据您填写的网址或密钥特征（如 AIza... / sk-...）智能匹配协议并补全 /v1。": "Auto-detects protocol from your URL or Key prefix (e.g. AIza... / sk-...) and auto-completes /v1.",
    "适用于所有 OpenAI 兼容接口（各类中转站、DeepSeek、硅基流动、OpenRouter、通义千问等），支持自动补全 /v1。": "For all OpenAI-compatible endpoints (relays, DeepSeek, SiliconFlow, OpenRouter, Qwen, etc.) with auto /v1 completion.",
    "Google Gemini 官方协议：API 地址可留空（默认直连 Google AI Studio），也可填写自定义反代地址。": "Google Gemini Official: Base URL can be left blank (defaults to Google AI Studio) or set to a custom proxy URL.",
    "Anthropic Claude 官方协议：API 地址可留空（默认直连 Anthropic 官方接口），也可填写自定义反代地址。": "Anthropic Claude Official: Base URL can be left blank (defaults to Anthropic Official) or set to a custom proxy URL.",
    "Ollama 本地/局域网协议：API 地址可留空（默认连接本机 11434 端口），也可填写局域网 IP。": "Ollama Local/LAN: Base URL can be left blank (defaults to localhost:11434) or set to a LAN IP.",
    "请输入 API 接口地址（如使用 Gemini/Claude 官方 Key 可留空）": "Enter API Base URL (optional for official Gemini/Claude keys)",
    "可留空（默认使用 Google 官方接口）": "Optional (defaults to Google Official endpoint)",
    "可留空（默认使用 Anthropic 官方接口）": "Optional (defaults to Anthropic Official endpoint)",
    "可留空（默认连接本机 11434 端口）": "Optional (defaults to localhost:11434)",
    "{{user}}: 你好\n{{char}}: *动作描写* 台词内容...": "{{user}}: Hello\n{{char}}: *action description* dialogue...",
    "{{user}}: 你好&#10;{{char}}: *动作描写* 台词内容...": "{{user}}: Hello\n{{char}}: *action description* dialogue...",
    "。": ".",
    "图标": "Icon",
    "背景": "Background",
    "模板": "Template",
    "角色卡": "Character Card",
    "角色": "Character",
    "跑团游戏": "TRPG Game",
    "新跑团游戏": "New TRPG Game",
    "开场白内容不能为空": "Opening greeting cannot be empty",
    "🖼️ 触发隐藏剧情关键词，已解锁全新角色 CG 插画！": "🖼️ Hidden plot keyword triggered! Unlocked new character CG!",
    "✅ 图片已就绪，已同步归档至素材库": "✅ Image ready & archived to gallery",
    "AI 生成角色卡失败": "AI character card generation failed",
    "保存角色卡失败": "Failed to save character card",
    "删除失败": "Delete failed",
    "导入失败": "Import failed",
    "导出失败": "Export failed",
    "打开失败": "Failed to open",
    "同步失败": "Sync failed",
    "保存失败": "Save failed",
    "创建失败": "Creation failed",
    "复制失败": "Copy failed",
    "上传失败": "Upload failed",
    "读取图片失败": "Failed to read image",
    "读取全局设置失败": "Failed to load global settings",
    "AI 润色失败": "AI polish failed",
    "创建分支失败": "Failed to create branch",
    "暂无游戏": "No games",
    "暂无对话记录": "No chat history",
    "选择文件夹": "Select Folder",
    "打开文件夹选择器失败，请直接手动输入路径": "Could not open folder picker, please enter the path manually",
    "请先指定或导出一个文件夹路径": "Please specify or export a folder path first",
    "⏳ 正在导出...": "⏳ Exporting...",
    "⏳ 正在导入...": "⏳ Importing...",
    "导出完成！": "Export Completed!",
    "从文件夹导入成功！": "Imported from Folder Successfully!",
    "浏览器文件夹上传导入成功！": "Uploaded & Imported Folder Successfully!",
    "📁 导出目录：": "📁 Export Folder: ",
    "📁 来源目录：": "📁 Source Folder: ",
    "请复制以下内容": "Please copy the following content",
    "加载素材失败": "Failed to load gallery assets",
    "网络请求异常": "Network request failed",
    "去重请求失败": "Deduplication request failed",
    "导入图片失败，请重试": "Failed to insert image, please try again",
    "请填写原密码与新密码": "Please enter current and new passwords",
    "新密码长度不能少于 6 位": "New password must be at least 6 characters",
    "修改密码失败": "Failed to change password",
    "✅ 密码已成功更新！": "✅ Password updated successfully!",
    "请输入游戏名称": "Please enter a game name",
    "正在上传图片...": "Uploading image...",
    "⏳ 正在上传游戏图标...": "⏳ Uploading game icon...",
    "✅ 游戏图标已上传": "✅ Game icon uploaded",
    "✅ 游戏图标已上传并保存": "✅ Game icon uploaded & saved",
    "✅ 游戏图标已上传并更新": "✅ Game icon uploaded & updated",
    "⏳ 正在上传游戏背景图...": "⏳ Uploading game background...",
    "✅ 游戏背景图已上传": "✅ Game background uploaded",
    "✅ 游戏背景已上传并生效": "✅ Game background uploaded & applied",
    "✅ 游戏背景已上传并更新": "✅ Game background uploaded & updated",
    "已清除游戏背景": "Game background cleared",
    "新游戏 (副本)": "New Game (Copy)",

    // Backend API notices & error details
    "非法的资源 ID": "Invalid resource ID",
    "当前尚未配置可用模型，请先在【⚙️ 设置】中选择或填写模型 ID，或开启本地 Ollama 服务。": "No model configured. Please select or enter a Model ID in [⚙️ Settings], or start a local Ollama service.",
    "尚未配置 API 地址 (Base URL) 或密钥，请先点击左下角【⚙️ 设置】填写 API 地址与密钥，或使用本地模型。": "API Base URL or Key is not configured. Please click [⚙️ Settings] in the bottom-left to configure your API or local model.",
    "请先在左下角【⚙️ 设置】中填写 API 地址与密钥，或开启本地模型后再使用 AI 润色。": "Please configure your API URL & Key or enable a local model in [⚙️ Settings] before using AI Polish.",
    "请先在左下角【⚙️ 设置】中填写 API 地址与密钥，或启动本地模型服务后再使用 AI 自动填卡。": "Please configure your API URL & Key or start a local model service in [⚙️ Settings] before using AI Auto-Fill.",
    "当前消息较少，暂无需压缩（至少需要 4 条以上对话记录）": "Too few messages to compress yet (at least 4 messages required)",
    "生成前情提要失败": "Failed to generate story summary",
    "正在启动本地 Strata 引擎 (Flash Next)...": "Starting local Strata engine (Flash Next)...",
    "正在释放 Strata 显存并切换至 Ollama 引擎...": "Releasing Strata VRAM and switching to Ollama engine...",
    "正在唤醒本机 Ollama 服务...": "Waking up local Ollama service...",

    // Default Project & Built-in Preset Modules (Names, Categories, Tags, Descriptions, Prompts)
    "高自由度多分支 AI 角色扮演与跑团游戏": "High-freedom multi-branch AI roleplay & TRPG adventure",
    "TRPG跑团": "TRPG Adventure",
    "动态世界书": "Dynamic Worldbook",
    "HTML状态栏": "HTML Status Bar",
    "多分支剧情": "Multi-Branch Plot",
    "动态世界书, HTML状态栏, 多分支剧情": "Dynamic Worldbook, HTML Status Bar, Multi-Branch Plot",
    "默认分类": "Default",
    "核心世界观": "Core Worldview",
    "登场人物设定": "Characters",
    "地点与势力": "Locations & Factions",
    "隐藏剧情触发": "Hidden Plot Triggers",
    "【玩家行动】": "[Player Action]",
    "【系统约束：保持第二人称代入感，给出环境细节与NPC神态，不替玩家做行动决定，等待玩家下一步输入。】": "[System Constraint: Maintain immersive second-person narration ('You...'), describe environment details and NPC reactions, never make decisions for the player, and wait for the player's next input.]",
    "你是一位富有想象力且严谨公正的 TRPG 跑团主持人（KP/DM）。\n世界观与规则设定：\n1. 始终以沉浸、生动的第二人称（你……）进行环境与感官细节描写。\n2. 严禁代玩家做决定，每次描写完场景和NPC反应后，停下来询问玩家：“你打算怎么做？”\n3. 需要判定时，提示玩家进行骰点（如：请进行【侦查】或【敏捷】检定）。\n4. 严格遵守世界书逻辑，NPC有各自的动机与性格，不盲目迎合玩家。": "You are an imaginative, fair, and rigorous TRPG Game Master (KP/DM).\nWorld & Rules:\n1. Always narrate environment and sensory details in an immersive, vivid second-person perspective ('You...').\n2. Never make decisions for the player. After describing the scene and NPC reactions, pause and ask: 'What do you do?'\n3. When a check is needed, prompt the player to roll dice (e.g., Please make a [Spot Hidden] or [DEX] check).\n4. Strictly follow the world setting; NPCs have their own motivations and personalities and do not blindly cater to the player.",

    // Generic TRPG Tags & Labels
    "奇幻冒险": "Fantasy Adventure",
    "奇幻": "Fantasy",
    "世界书": "Worldbook",
    "状态栏": "Status Bar",
    "CG": "CG",
    "奇幻, 世界书, 状态栏, CG": "Fantasy, Worldbook, Status Bar, CG",
    "跑团": "TRPG",
    "冒险": "Adventure",
    "悬疑克苏鲁": "Lovecraftian Mystery",
    "CoC7版规则": "CoC 7th Rules",
    "SAN值检定": "SAN Check",
    "悬疑解谜": "Mystery",
    "多结局": "Multiple Endings",
    "赛博朋克": "Cyberpunk",
    "黑客搭档": "Netrunner Partner",
    "全息状态栏": "Holo HUD",
    "多势力博弈": "Faction Intrigue",
    "赛博朋克, 黑客搭档, 全息状态栏, 多势力博弈": "Cyberpunk, Netrunner Partner, Holo HUD, Faction Intrigue",
    "【边缘行者行动】": "[Edgerunner Action]",
    "【系统约束：维持赛博朋克冷峻华丽文风，末尾输出 ```html 全息HUD状态面板。】": "[System Constraint: Maintain gritty neon cyberpunk style and append the ```html Holographic HUD status panel at the end.]",
    "你是赛博朋克2099【新巴比伦城】的主持AI，同时扮演玩家的顶尖黑客搭档少女【零（Zero）】。\n1. 展现霓虹雨夜、全息广告、企业安保部队、黑市义体诊所与深网数据流的硬核科幻质感。\n2. 追踪玩家的【信用点】【义体排异率/赛博精神病阈值】【荒坂/军用科技通缉等级】。\n3. 每次回复末尾输出赛博霓虹风格的 ```html 全息HUD状态栏。": "You are the GM AI of Cyberpunk 2099 [New Babylon City], also portraying the player's elite netrunner partner [Zero].\n1. Deliver hardcore sci-fi immersion: neon rain, holographic ads, corp tac-teams, ripperdoc clinics, and deep-net data streams.\n2. Track the player's [Creds], [Cyberware Overload / Cyberpsychosis Threshold], and [Megacorp Wanted Level].\n3. Output a neon cyberpunk ```html Holographic HUD status panel at the end of every reply.",

    // Preset Module 4: Wuxia
    "【古风武侠】天骄少侠夜探魔教总坛 · 战况模拟器": "[Wuxia] Young Martial Prodigy Infiltrates the Demon Sect · Combat Simulator",
    "古风仙侠": "Wuxia & Xianxia",
    "硬核古风武侠潜入与博弈模拟器。内置内力真气槽、招式破绽推演、护体罡气、暗器机关与回合制状态面板。": "Hardcore Wuxia stealth & martial arts tactical simulator with Qi meter, stance analysis, protective aura, hidden traps, and turn-based status panel.",
    "武侠潜入": "Wuxia Stealth",
    "内力招式": "Martial Arts & Qi",
    "状态模拟器": "Combat Sim",
    "动态机关": "Dynamic Traps",
    "武侠潜入, 内力招式, 状态模拟器, 动态机关": "Wuxia Stealth, Martial Arts & Qi, Combat Sim, Dynamic Traps",
    "【少侠行动】": "[Martial Hero Action]",
    "【系统约束：保持金古武侠质感，注重招式交互细节，末尾输出 ```html 武侠状态栏。】": "[System Constraint: Maintain classic Wuxia martial arts atmosphere, focus on tactical stance exchanges, and output the ```html Wuxia status panel at the end.]",
    "你是古风武侠跑团与战斗推演主持人。\n1. 描写细腻考究的轻功身法、剑气交锋、穴道经脉、机关暗器与心理交锋。\n2. 实时计算少侠的【内力值】【体力值】【轻功隐蔽度】【防具完整度】与周围守卫警戒等级。\n3. 每次回复末尾输出古风卷轴式 ```html 战况与角色状态面板。": "You are a classic Wuxia TRPG and tactical combat Game Master.\n1. Depict refined轻功 footwork, sword Qi clashes, acupoint strikes, hidden mechanisms, and tactical mind games.\n2. Track the hero's [Inner Qi], [Stamina], [Stealth Rating], [Armor Integrity], and [Guard Alert Level].\n3. Output a scroll-style ```html Wuxia Combat & Character Status panel at the end of each reply.",

    // Shortened Buttons & Concise Labels
    "📋 沿用该游戏": "📋 Use as Template",
    "✨ 新建游戏 (高级)": "✨ New Game (Advanced)",
    "✨ 一键润色": "✨ Polish All",
    "⬅️ 返回": "⬅️ Back",
    "✅ 创建游戏": "✅ Create Game",
    "游戏图标": "Game Icon",
    "标签": "Tags",
    "游戏背景": "Game Background",
    "开场白标题（可选）": "Opening Title (Optional)",
    "✏️ 修改": "✏️ Edit",
    "🎲 掷骰": "🎲 Roll",
    "🚀 发送": "🚀 Send",
    "💡 也已同步填入底部输入框": "💡 Synced to bottom input box",
    "选择开场白": "Choose Opening",
    "➕ 设置开场白": "➕ Set Opening",
    "在下方输入角色卡或行动指令，或点击开场白开启冒险。": "Enter your character card or action below, or click an opening to begin.",
    "点击卡片直接发送": "Click card to send",
    "✓ 已选择": "✓ Selected",
    "➕ 选择": "➕ Select",
    "✏️ 编辑": "✏️ Edit",
    "⚡ 新建简易卡": "⚡ New Simple Card",
    "🛠️ 新建高级卡": "🛠️ New Advanced Card",
    "📥 导入角色卡": "📥 Import Card",
    "⚡ 简易角色卡": "⚡ Simple Card",
    "🛠️ 高级角色卡": "🛠️ Advanced Card",
    "✨ AI 自动填卡": "✨ AI Auto-Fill",
    "🌐 联网搜索": "🌐 Web Search",
    "✨ AI 生成": "✨ AI Generate",
    "📷 上传图片": "📷 Upload Image",
    "角色名称": "Character Name",
    "🧩 角色属性栏": "🧩 Character Fields",
    "➕ 单行栏": "➕ 1-Line Field",
    "➕ 多行栏": "➕ Multi-Line Field",
    "📋 填入默认模板": "📋 Fill Default Template",
    "性格": "Personality",
    "场景": "Scenario",
    "开场白": "First Message",
    "备用开场白": "Alternate Greetings",
    "示例对话": "Example Messages",
    "角色提示词": "Character Prompt",
    "历史后指令": "Post-History Instructions",
    "作者备注": "Creator Notes",
    "深度提示词 (Depth Prompt)": "Depth Prompt",
    "🔌 接口协议：": "🔌 Protocol:",
    "⚡ 自动识别": "⚡ Auto-Detect",
    "🔌 OpenAI 兼容协议": "🔌 OpenAI Compatible",
    "✨ Google Gemini 协议": "✨ Google Gemini",
    "🎭 Anthropic Claude 协议": "🎭 Anthropic Claude",
    "🦙 Ollama 本地协议": "🦙 Ollama Local",
    "🔄 拉取模型": "🔄 Fetch Models",
    "👇 点击直接填入：": "👇 Click to fill:",
    "📌 已添加的模型：": "📌 Added Models:",
    "✅ 保存并选用": "✅ Save & Select",
    "📦 数据备份": "📦 Data Backup",
    "📤 导出数据": "📤 Export Data",
    "📥 导入数据": "📥 Import Data",
    "📂 浏览": "📂 Browse",
    "🚀 导出": "🚀 Export",
    "📥 导入": "📥 Import",
    "🌐 选择文件夹": "🌐 Select Folder",
    "✍️ 手动添加": "✍️ Add Model",
    "✍️ 手动填写": "✍️ Enter Manually",
    "⚡ 自动探测本机端口": "⚡ Auto-Probe Local Ports",
    "当前选择的模型：": "Active Model:",
    "预设分类": "Preset",
    "本地算力": "Local GPU",
    "其他": "Other",
    "全局温度 (Temperature)": "Temperature",
    "回复长度上限 (Max Tokens)": "Max Output Tokens",
    "✍️ 手动配置": "✍️ Manual Config",
    "✍️ 手动添加模型": "✍️ Add Model Manually",
    "📦 导入 / 导出备份": "📦 Import / Export Backup",
    "⚙️ 高级选项": "⚙️ Advanced Options",
    "筛选 ▾": "Filter ▾",
    "收起 ▴": "Collapse ▴",
    "☰ 面板": "☰ Panel",
    "◀ 收起": "◀ Hide",
    "开始游戏": "Start Game",
    "📱 界面显示方向 (GUI 横竖屏切换)：": "📱 GUI Display Orientation (Landscape / Portrait):",
    "横屏模式 (宽屏桌面)": "Landscape Mode (Desktop Wide)",
    "竖屏模式 (掌上竖版)": "Portrait Mode (Handheld Vertical)",
    "自动适配": "Auto",
    "此设置仅对当前设备生效（电脑和手机可分别设置）。": "This setting only applies to the current device (PC and phone can differ).",
    "手机自动使用竖屏界面、电脑自动使用横屏界面，并跟随屏幕旋转": "Phones use the portrait UI, PCs the wide UI, following screen rotation",
    "模型设置 / 下载模型": "Model Settings / Download",
    "更多功能": "More",
    "切换为宽屏横版桌面布局": "Switch to desktop landscape layout",
    "切换为掌上竖版单栏布局": "Switch to handheld vertical portrait layout",
    "📱 已切换为竖屏界面模式": "📱 Switched to Portrait GUI Mode",
    "🖥️ 已切换为横屏界面模式": "🖥️ Switched to Landscape GUI Mode",
    // === merged simplified copy ===
    "AI 填充": "AI Fill",
    "OpenAI 兼容接口": "OpenAI Compatible",
    "*(已停止)*": "*(Stopped)*",
    "✓ 已选择": "✓ Selected",
    "下载": "Download",
    "丢弃": "Discard",
    "主持人": "GM",
    "人设描述…": "Persona...",
    "仅保存": "Save Only",
    "从此处分支": "Branch from here",
    "使用": "Use",
    "保存": "Save",
    "保存失败": "Save failed",
    "保存并生成": "Save & Generate",
    "停用": "Disable",
    "内容…": "Content...",
    "出示": "Show",
    "删除": "Delete",
    "删除剧本": "Delete Script",
    "删除图片": "Delete Image",
    "删除对话": "Delete Chat",
    "删除当前剧本？对话将移入默认剧本": "Delete current scenario? Chats will move to Default Scenario.",
    "删除此图片？不可恢复": "Delete this image? Cannot be undone.",
    "删除此对话？不可恢复": "Delete this chat? Cannot be undone.",
    "删除此消息？": "Delete this message?",
    "删除消息": "Delete Message",
    "前情": "Summary",
    "剧本设定": "Script Settings",
    "加载中…": "Loading...",
    "加载失败": "Load failed",
    "单行/多行": "Single/Multi-line",
    "压缩中…": "Compressing...",
    "去修改": "Edit",
    "去重": "Dedupe",
    "去重失败": "Dedupe failed",
    "双击重命名": "Double-click to rename",
    "取消": "Cancel",
    "取消选择": "Deselect",
    "可留空": "Optional",
    "后台对话已生成": "Background reply ready",
    "后台生成中…": "Generating in background...",
    "地址可留空": "URL optional",
    "备用开场白…": "Alternate greeting...",
    "复制": "Copy",
    "密码已更新": "Password updated",
    "导入": "Import",
    "导入中…": "Importing...",
    "导入失败": "Import failed",
    "导入所选": "Insert Selected",
    "导出": "Export",
    "导出 JSON": "Export JSON",
    "导出 PNG": "Export PNG",
    "已上传": "Uploaded",
    "已中断，重新生成中": "Aborted, regenerating",
    "已保存": "Saved",
    "已保存，重新生成中": "Saved, regenerating",
    "已删除": "Deleted",
    "已刷新": "Refreshed",
    "已压缩": "Compressed",
    "已取消": "Cancelled",
    "已填入": "Filled",
    "已填入模板": "Template filled",
    "已填入，保存后生效": "Filled, save to apply",
    "已复位": "Reset",
    "已复制": "Copied",
    "已存在": "Already exists",
    "已导入": "Imported",
    "已导出": "Exported",
    "已就绪": "Ready",
    "已恢复全局": "Restored global",
    "已恢复默认": "Reset to default",
    "已打开": "Opened",
    "已换一批": "Rerolled",
    "已暂停": "Paused",
    "已更新": "Updated",
    "已清空": "Cleared",
    "已生成": "Generated",
    "已移除": "Removed",
    "已粘贴参考图": "Reference image pasted",
    "已继续": "Resumed",
    "已解锁新 CG": "New CG unlocked",
    "已锁定": "Locked",
    "已隐藏": "Hidden",
    "常用 API": "Presets",
    "开场白为空": "Greeting is empty",
    "手动添加": "Add Manually",
    "执行": "Run",
    "扫描": "Scan",
    "拖拽调整，双击复位": "Drag to resize, double-click to reset",
    "挂载": "Mount",
    "按地址或 Key 自动识别": "Auto-detect from URL or Key",
    "收起": "Collapse",
    "放大": "Zoom",
    "新回复": "New reply",
    "新密码至少 6 位": "Password must be at least 6 chars",
    "无 .gguf 文件": "No .gguf files",
    "无匹配": "No match",
    "无可换选项": "No choices to reroll",
    "无可选物品": "No items",
    "无可重新生成的消息": "Nothing to regenerate",
    "无法打开，请手动输入路径": "Cannot open dialog, enter path manually",
    "无重复": "No duplicates",
    "暂无前情": "No summary yet",
    "暂无剧本": "No scenarios",
    "暂无对话": "No chats",
    "暂无挂载路径": "No mounted paths",
    "暂无本地模型": "No local models",
    "暂无模型": "No models",
    "暂无角色卡": "No character cards",
    "暂无记录": "No records",
    "未命名角色": "Unnamed Character",
    "未获取到模型，请手动填写": "No models fetched, enter ID manually",
    "未获取到模型，请手动添加": "No models fetched, add manually",
    "未配置模型": "No model configured",
    "本地": "Local",
    "查看角色卡": "View Card",
    "查询中…": "Querying...",
    "查询失败": "Query failed",
    "栏位名": "Field name",
    "检定": "Check",
    "检查": "Inspect",
    "检索并生成中…": "Searching & generating...",
    "模块设置": "Module Settings",
    "模型无响应，请重新生成": "No response from model, please regenerate",
    "横屏": "Landscape",
    "消息太少，无需压缩": "Too few messages to compress",
    "清空全部消息与前情？": "Clear all messages and summary?",
    "清空对话": "Clear Chat",
    "点击勾选": "Click to select",
    "状态面板": "Status Panel",
    "生成中": "Generating",
    "生成中…": "Generating...",
    "生成中，请稍候": "Generating, please wait",
    "生成失败": "Generation failed",
    "移除": "Remove",
    "空": "Empty",
    "竖屏": "Portrait",
    "等待超时，请刷新或重新生成": "Timed out, refresh or regenerate",
    "简易": "Simple",
    "继续": "Resume",
    "▶继续": "▶ Resume",
    "编辑": "Edit",
    "网络错误": "Network error",
    "自动（竖屏）": "Auto (Portrait)",
    "自动（横屏）": "Auto (Landscape)",
    "自由输入": "Custom input",
    "补充用法…": "Usage note...",
    "补充行动…": "Action note...",
    "装备": "Equip",
    "角色": "Character",
    "设定": "Setup",
    "设置": "Settings",
    "请先指定路径": "Specify a path first",
    "请先选择图片": "Select an image first",
    "请先选择对话": "Select a chat first",
    "请手动填写模型 ID": "Enter model ID manually",
    "请至少选一项": "Select at least one item",
    "请输入 .gguf 文件或目录路径": "Enter .gguf file or folder path",
    "请输入人设或上传参考图": "Enter persona or upload reference image",
    "请输入模型名": "Enter model name",
    "请选择物品或输入行动": "Select an item or enter action",
    "输入行动…": "Enter action...",
    "选择": "Select",
    "选择中…": "Selecting...",
    "选择文件夹…": "Pick folder...",
    "选用": "Use",
    "选项生成中": "Rerolling choices...",
    "重命名": "Rename",
    "重新生成": "Regenerate",
    "重新生成中": "Regenerating",
    "重新生成中…": "Regenerating...",
    "重新选择": "Reselect",
    "隐藏": "Hide",
    "面板": "Panel",
    "高级": "Advanced",
    "默认剧本不可删除": "Default scenario cannot be deleted",
    "默认本机 11434": "Default localhost:11434",
    "改名": "Rename",
    "背景图": "Background",
    "新增": "Add",
    "换一批": "Reroll",
    "用道具 ▾": "Item ▾",
    "物品栏": "Inventory",
    "功能栏": "Modules",
    "独立参数": "Custom Params",
    "跟随全局": "Use Global",
    "暂停": "Pause",
    "开始": "Start",
    "源码": "Source",
    "正则脚本": "Regex",
    "思考折叠": "Thought",
    "思考推演": "Reasoning",
    "剧情正文": "Story",
    "行动选项": "Choices",
    "沿用": "Use Template",
    "仅 AI": "AI Only",
    "仅玩家": "User Only",
    "双向": "Both",
    "变量": "Variables",
    "记忆": "Memory",
    "记忆:": "Memory:",
    "模型参数": "Model Params",
    "模型：": "Model:",
    "当前": "Current",
    "轮": "turns",
    "小说(0.68)": "Novel (0.68)",
    "严谨(0.62)": "Strict (0.62)",
    "发散(0.75)": "Creative (0.75)",
    "API 设置": "API Settings",
    "配置 API": "Configure API",
    "CG / 记忆 / 变量": "CG / Memory / Vars",
    "暂无 API 模型": "No API models",
    "暂无本地模型 ·": "No local models ·",
    "未发现 .gguf": "No .gguf found",
    "暂无物品": "No items",
    "暂无词条": "No entries",
    "状态栏 (": "Status (",
    "路径不存在": "Path not found",
    "角色设定": "Character",
    "顺其自然": "Go with the flow",
    "搜查": "Search",
    "质问": "Question",
    "调情": "Flirt",
    "偷袭": "Ambush",
    "压缩中...": "Compressing...",
    "0 / 32 条": "0 / 32 msgs",
    "时间：": "Time:",
    "或": "or",
    "未命名剧本": "Untitled Scenario",
    "加载中...": "Loading...",
    "宽度": "Width",
    "标准": "Normal",
    "宽屏": "Wide",
    "关闭": "Close",
    "已分段": "Segmented",
    "关闭失败": "Failed to disable",
    "想法": "Idea",
    "润色": "Polish",
    "润色全部": "Polish all",
    "润色中...": "Polishing...",
    "上传图标": "Upload icon",
    "名称": "Name",
    "图片 URL": "Image URL",
    "清除": "Clear",
    "简介": "Description",
    "标题": "Title",
    "开场白": "Greeting",
    "暂无开场白": "No greetings",
    "世界观、规则、人物": "World, rules, characters",
    "风格": "Style",
    "修改": "Edit",
    "恢复默认": "Reset",
    "留空则不发送": "Empty = not sent",
    "拖动排序": "Drag to reorder",
    "默认 6 栏": "Default 6 bars",
    "每行一个子项": "One item per line",
    "推演规则": "Reasoning rules",
    "叙事规则": "Narrative rules",
    "状态栏规则": "Status bar rules",
    "装备栏规则": "Equipment rules",
    "物品栏规则": "Inventory rules",
    "关系栏规则": "Relationship rules",
    "情报卡规则": "Info card rules",
    "选项规则": "Choice rules",
    "启用": "Enable",
    "类型": "Type",
    "上移": "Move up",
    "下移": "Move down",
    "仅作排版参考": "Layout reference only",
    "正文格式": "Story format",
    "思考格式": "Thinking format",
    "选项格式": "Choice format",
    "格式参考": "Format reference",
    "自动分段": "Auto-segment",
    "分段": "Segment",
    "每行一个字段": "One field per line",
    "随系统提示词发送": "Sent with system prompt",
    "正文栏提示词": "Story prompt",
    "思考栏提示词": "Thinking prompt",
    "选项栏提示词": "Choice prompt",
    "功能栏提示词": "Bar prompt",
    "栏位规则": "Bar rules",
    "与功能栏同步": "Synced with bars",
    "润色模型": "Polish model",
    "状态栏": "Status Bar",
    "前后缀": "Prefix / Suffix",
    "加在每条发言前": "Prepended to each message",
    "加在每条发言后": "Appended to each message",
    "关键词，逗号分隔": "Keywords, comma-separated",
    "触发内容": "Triggered content",
    "正则": "Regex",
    "替换为": "Replace with",
    "暂无规则": "No rules",
    "记忆内容": "Memory content",
    "变量名": "Variable name",
    "已被模型参数覆盖": "Overridden by model params",
    "温度": "Temperature",
    "重复惩罚": "Repetition Penalty",
    "频率惩罚": "Frequency Penalty",
    "存在惩罚": "Presence Penalty",
    "最大输出": "Max Output",
    "上下文模式": "Context Mode",
    "按轮数": "By Turns",
    "按 Token": "By Tokens",
    "上下文轮数": "Context Turns",
    "上下文上限 (k)": "Context Limit (k)",
    "压缩保留": "Keep Recent",
    "思考预算": "Thinking Budget",
    "超限自动压缩": "Auto-compress when over limit",
    "单位 k": "Unit: k",
    "上传中...": "Uploading...",
    "图标已上传": "Icon uploaded",
    "背景已上传": "Background uploaded",
    "已应用：小说": "Applied: Novel",
    "已应用：严谨": "Applied: Strict",
    "已应用：发散": "Applied: Creative",
    "读取失败": "Load failed",
    "已同步全局参数": "Synced global params",
    "已设为全局默认": "Set as global default",
    "添加栏位": "Add Bar",
    "预设": "Preset",
    "提示词": "Prompt",
    "进度条": "Progress",
    "装备槽": "Equipment",
    "物品格": "Inventory",
    "好感卡": "Affinity",
    "情报卡": "Info Card",
    "第二人称，注重感官细节": "Second person, sensory detail",
    "请输入名称": "Enter a name",
    "已排序": "Reordered",
    "已恢复默认栏位": "Default bars restored",
    "已写入系统提示词": "Written to system prompt",
    "恢复默认提示词？": "Reset prompt to default?",
    "润色失败": "Polish failed",
    "已润色": "Polished",
    "请先输入想法": "Enter an idea first",
    "已润色全部": "All polished",
    "前置": "Prefix",
    "后置": "Suffix",
    "高级新建": "Advanced New",
    "新建": "New",
    "新剧本 (副本)": "New Script (Copy)",
    "原剧本": "Original",
    "返回": "Back",
    "创建": "Create",
    "基本信息": "Basic Info",
    "前置提示词": "Prefix Prompt",
    "核心设定": "Core Setup",
    "后置提示词": "Suffix Prompt",
    "采样参数": "Sampling",
    "未选择对话": "No chat selected",
    "已创建分支": "Branch created",
    "全部": "All",
    "AI 跑团": "AI TRPG",
    "存档": "Saves",
    "默认剧本": "Default Script",
    "更多": "More",
    "日志": "Logs",
    "模型价格": "Model Pricing",
    "聊天": "Chat",
    "最新": "Latest",
    "剧情与角色状态": "Plot & character state",
    "剧本名称": "Script name",
    "附加在发言开头": "Prepended to each message",
    "附加在发言末尾": "Appended to each message",
    "列表": "List",
    "指定路径": "Custom Path",
    "小说": "Novel",
    "严谨": "Strict",
    "发散": "Creative",
    "目录": "folder",
    "放入": "Drop",
    "自动识别": "to auto-detect",
    "打开目录": "Open Folder",
    "选文件": "Pick File",
    "选目录": "Pick Folder",
    ".gguf 文件或目录路径": ".gguf file or folder path",
    "本地端口": "Local Port",
    "接口地址": "Endpoint URL",
    "模型名": "Model name",
    "HF 主页": "HF Page",
    "API 地址": "API URL",
    "添加模型": "Add Model",
    "模型 ID": "Model ID",
    "界面方向": "Orientation",
    "自动": "Auto",
    "仅本设备生效": "This device only",
    "代理": "Proxy",
    "全局参数": "Global Parameters",
    "同步到全部剧本": "Sync to all scripts",
    "默认 0.68": "Default 0.68",
    "默认 1.05": "Default 1.05",
    "默认 0.00": "Default 0.00",
    "默认 0.25": "Default 0.25",
    "默认 0.90": "Default 0.90",
    "默认 40": "Default 40",
    "默认 0.06": "Default 0.06",
    "默认 12288": "Default 12288",
    "默认 64k": "Default 64k",
    "默认 6": "Default 6",
    "默认 1024": "Default 1024",
    "上下文计算": "Context Mode",
    "公网": "Public",
    "局域网": "LAN",
    "本机": "This PC",
    "备份": "Backup",
    "选择数据": "Data",
    "剧本": "Scripts",
    "对话": "Chats",
    "留空自动生成": "Leave empty to auto-generate",
    "选择导出目录": "Select export folder",
    "备份目录": "Backup folder",
    "选择备份目录": "Select backup folder",
    "原密码": "Old Password",
    "新密码": "New Password",
    "当前连接": "Current Connection",
    "登录记录": "Login History",
    "退出": "Log Out",
    "点击改名": "Click to rename",
    "角色名": "Character name",
    "AI 填卡": "AI Fill",
    "角色名 / 作品 / 人设": "Name / work / persona",
    "参考图": "Reference images",
    "外貌、性格、背景": "Looks, personality, background",
    "队友, 魔法师, 傲娇": "teammate, mage, tsundere",
    "性格概括": "Personality summary",
    "时间线、环境、关系": "Timeline, setting, relations",
    "选填": "Optional",
    "说明、版本备注": "Notes, version",
    "按深度注入的笔记": "Notes injected at depth",
    "深度": "Depth",
    "自定义栏位": "Custom Fields",
    "添加 API": "Add API",
    "协议": "Protocol",
    "OpenAI 兼容": "OpenAI Compatible",
    "拉取": "Fetch",
    "点击填入": "Click to fill",
    "已添加": "Added",
    "预览": "Preview",
    "总结": "Summarize",
    "角色卡库": "Characters",
    "重生成": "Regenerate",
    "压缩": "Compress",
    "清空": "Clear",
    "停止": "Stop",
    "刷新": "Refresh",
    "独立参数：": "Model Params:",
    "最高优先": "Top Priority",
    "下载模型": "Download Models",
    "显示": "Show",
    "同步全部": "Sync All",
    "系统提示词": "System Prompt",
    "浏览": "Browse",
    "打开": "Open",
    "修改密码": "Change Password",
    "选择角色卡": "Select Cards",
    "编辑角色卡": "Edit Card",
    "传图": "Image",
    "模型:": "Model:",
    "联网": "Web",
    "生成": "Generate",
    "高级选项": "Advanced",
    "输入行动或对白...": "Action or dialogue...",
    "搜索模型...": "Search models...",
    "留空自动获取": "Leave empty to auto-detect",
    "输入系统提示词...": "System prompt...",
    "搜索角色...": "Search...",
    "搜索角色卡...": "Search cards...",
    "(API/参数)": "(API/Params)",
    "已选 0 张": "0 selected",
    "共 0 张": "0 total",
    "非法 ID": "Invalid ID",
    "尝试过多，1 分钟后再试": "Too many attempts, retry in 1 min",
    "密码至少 6 位": "Password must be at least 6 chars",
    "原密码错误": "Wrong current password",
    "注册已关闭": "Registration disabled",
    "用户名必填，密码至少 6 位": "Username required, password ≥ 6 chars",
    "缺少模型名": "Model name required",
    "缺少模型 ID": "Model ID required",
    "剧本不存在": "Scenario not found",
    "消息不足 6 条，无需压缩": "Fewer than 6 messages, no need to compress",
    "暂无可重新生成的消息": "Nothing to regenerate",
    "未找到对应发言": "Target message not found",
    "请先配置 API Key 和模型": "Configure API Key and model first",
    "请先配置模型": "Configure model first",
    "请先选择模型": "Select a model first",
    "生成中...": "Generating...",
    "模型未返回内容，请重试或换模型": "Empty response from model, retry or switch model",
    "正在生成中": "Already generating",
    "暂无 AI 回复": "No AI reply yet",
    "生成失败，请重试": "Generation failed, please retry",
    "请选择文件夹": "Select a folder",
    "文件夹为空": "Folder is empty",
    "角色卡格式无效": "Invalid character card format",
    "PNG 中无角色卡数据": "No character card data in PNG",
    "请输入需求或上传图片": "Enter request or upload image",
    "AI 返回格式无效，请重试或换模型": "Invalid AI output format, retry or switch model",
    "仅限本机操作": "Local machine only",
    "选择模型文件夹": "Select Model Folder",
    "选择 .gguf 文件": "Select .gguf File",
    "切换至 Ollama...": "Switching to Ollama...",
    "启动 Ollama...": "Starting Ollama...",
    "我的剧本": "My Scenarios",
    "模板不存在": "Template not found",
    "未识别到世界书条目（需含 world_book 数组）": "No lorebook entries found (requires world_book array)",
    "无返回数据": "No data returned",
    "名称不能为空": "Name required",
    "文件夹已存在": "Folder already exists",
    "新剧本": "New Scenario",
    "需为 .gguf 文件或其所在目录": "Must be a .gguf file or folder containing .gguf",
    "未找到 .gguf 文件": "No .gguf files found",
    "连接中断，可续传": "Disconnected, resumable",
    "尚未检测到可用 AI 模型 · 任选一种方式配置后即可畅玩": "No AI model configured yet · Choose an option below to start",
    "⬇️ 一键下载本地模型": "⬇️ Download Local Model",
    "📂 扫描 / 挂载 GGUF": "📂 Scan / Mount GGUF",
    "🔑 配置在线 API": "🔑 Connect Cloud API",
    "请先下载本地模型或配置在线 API 后即可开始游玩": "Download a local model or configure a Cloud API first to start playing",
    "当前活跃记忆 / 上下文上限（点击查看详情或手动压缩）": "Active Context / Max Limit (Click for details or manual compress)",
    "默认 1.05": "Default 1.05",
    "默认 0.05": "Default 0.05",
    "默认 0.20": "Default 0.20",
    "默认 1.08": "Default 1.08",
    "默认 0.12": "Default 0.12",
    "默认 0.45": "Default 0.45",
    "默认 4096": "Default 4096",
    "默认 96k": "Default 96k"
  };

  // Build whitespace-collapsed dictionary and reverse lookup dictionary (English -> Chinese)
  const COLLAPSED_DICT = {};
  const REVERSE_FIELD_LABELS = {
    "Identity / Class": "身份 / 职业",
    "Gender / Race": "性别 / 种族",
    "Age / Height": "年龄 / 身高",
    "Appearance & Outfit": "外貌特征与穿搭",
    "Personality Traits": "性格特点",
    "Speech Style & Catchphrases": "说话口吻与口癖",
    "Abilities, Skills & Gear": "能力技能与装备",
    "Relationships & Attitude": "人际关系与态度",
    "Backstory & Extra Notes": "背景故事与补充设定",
    "Description": "描述 (Description)",
    "Basic Info & Bio": "基本信息与角色简介",
    "No public tunnel detected": "未检测到公网隧道",
    "Loading...": "读取中..."
  };
  for (const [zhKey, enVal] of Object.entries(EXACT_DICT)) {
    const collapsedKey = zhKey.replace(/\s+/g, " ").trim();
    if (collapsedKey && !COLLAPSED_DICT[collapsedKey]) {
      COLLAPSED_DICT[collapsedKey] = enVal;
    }
    if (enVal && !REVERSE_FIELD_LABELS[enVal]) {
      REVERSE_FIELD_LABELS[enVal] = zhKey;
    }
  }

  // 2. Dynamic Regex Pattern Rules (Chinese pattern -> English replacement function)
  const PATTERN_RULES = [
    // === merged simplified patterns ===
    [new RegExp("^(\\d+)\\s*个\\s*GGUF$"), (...m) => "$1 GGUF(s)".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^生成中…\\s*(\\d+)s$"), (...m) => "Generating... $1s".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^连接中断:\\s*(.+?)（可刷新查看）$"), (...m) => "Disconnected: $1 (refresh to check)".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^「(.+?)」使用独立参数$"), (...m) => "\"$1\" uses custom params".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^上传\\s*(\\d+)\\s*张图片…$"), (...m) => "Uploading $1 image(s)...".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^下载\\s*\\((\\d+)\\)$"), (...m) => "Downloads ($1)".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^删除「(.+?)」？$"), (...m) => "Delete \"$1\"?".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^剧本列表:\\s*(.+)$"), (...m) => "Scenario List: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^剧本设定:\\s*(.+)$"), (...m) => "Scenario Settings: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^参考图\\s*\\((\\d+)\\)$"), (...m) => "Ref Images ($1)".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^发现\\s*(\\d+)\\s*个本地模型$"), (...m) => "Found $1 local model(s)".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^图片已就绪\\s*\\((.+?)\\)$"), (...m) => "Image ready ($1)".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^处理\\s*(\\d+)\\s*张图片…$"), (...m) => "Processing $1 image(s)...".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^对话\\s*#(\\d+)\\s*\\((.+)\\)$"), (...m) => "Chat #$1 ($2)".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^导入中\\s*\\((\\d+)\\)…$"), (...m) => "Importing ($1)...".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^导入中（(\\d+)\\s*个文件）$"), (...m) => "Importing ($1 files)".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^导入所选\\s*\\((\\d+)\\)$"), (...m) => "Insert Selected ($1)".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已保存：(.+)$"), (...m) => "Saved: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已切换模型：(.+)$"), (...m) => "Switched model: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已切换：(.+)$"), (...m) => "Switched: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已刷新（(\\d+)）$"), (...m) => "Refreshed ($1)".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已取消：(.+)$"), (...m) => "Deselected: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已同步\\s*(\\d+)\\s*个剧本$"), (...m) => "Synced $1 scenario(s)".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已填充：(.+?)，请核对后保存$"), (...m) => "Filled: $1 (review and save)".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已填充：(.+)$"), (...m) => "Filled: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已导入\\s*(\\d+)\\s*张角色卡$"), (...m) => "Imported $1 card(s)".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已导入\\s*(\\d+)\\s*张图片$"), (...m) => "Imported $1 image(s)".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已导出：(.+)$"), (...m) => "Exported: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已就绪\\s*(\\d+)$"), (...m) => "Ready: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已开始下载：(.+)$"), (...m) => "Downloading: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已打开：(.+)$"), (...m) => "Opened: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已挂载：(.+)$"), (...m) => "Mounted: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已新建：(.+)$"), (...m) => "Created: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已添加：(.+)$"), (...m) => "Added: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已清理\\s*(\\d+)\\s*张，剩余\\s*(\\d+)\\s*张$"), (...m) => "Cleaned $1, $2 remaining".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已获取\\s*(\\d+)\\s*个模型$"), (...m) => "Fetched $1 model(s)".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已解锁 CG：(.+)$"), (...m) => "Unlocked CG: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已选\\s*(\\d+)\\s*张角色卡$"), (...m) => "$1 card(s) selected".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已选择[:：]\\s*(.+)$"), (...m) => "Selected: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已锁定\\s*\\((.+)\\)$"), (...m) => "Locked ($1)".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^掷出\\s*(.+?)\\s*=\\s*(.+)$"), (...m) => "Rolled $1 = $2".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^检定：(.+?)\\s*=\\s*(.+)$"), (...m) => "Check: $1 = $2".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^新剧本\\s*#(\\d+)$"), (...m) => "New Scenario #$1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^消息\\s*(\\d+)/(\\d+)\\s*·\\s*Token\\s*(.+)/(.+)$"), (...m) => "Msgs $1/$2 · Tokens $3/$4".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^目录：(.+)$"), (...m) => "Dir: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^辅助模型：(.+)$"), (...m) => "Assist model: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^换一批失败:\\s*(.+)$"), (...m) => "Reroll failed: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^压缩失败:\\s*(.+)$"), (...m) => "Compress failed: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^添加失败:\\s*(.+)$"), (...m) => "Add failed: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^选择失败:\\s*(.+)$"), (...m) => "Select failed: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^新建失败:\\s*(.+)$"), (...m) => "Create failed: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已关闭独立参数：(.+)$"), (...m) => "Per-model params off: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^关闭失败: (.+)$"), (...m) => "Failed to disable: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^独立参数：(.+)$"), (...m) => "Per-model params: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已启用「(.+)」$"), (...m) => "Enabled \"$1\"".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已添加「(.+)」$"), (...m) => "Added \"$1\"".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已移至第 (\\d+) 位$"), (...m) => "Moved to #$1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已润色「(.+)」$"), (...m) => "Polished \"$1\"".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已导入 (\\d+) 条$"), (...m) => "Imported $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^导入失败: (.+)$"), (...m) => "Import failed: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^润色失败: (.+)$"), (...m) => "Polish failed: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^保存失败: (.+)$"), (...m) => "Save failed: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^复制失败: (.+)$"), (...m) => "Copy failed: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^创建失败: (.+)$"), (...m) => "Create failed: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^读取失败: (.+)$"), (...m) => "Load failed: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已复制：(.+)$"), (...m) => "Copied: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已创建：(.+)$"), (...m) => "Created: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^新剧本\\s*#(\\d+)$"), (...m) => "New Script #$1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^消息 \\((\\d+)\\)$"), (...m) => "Messages ($1)".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^润色中 \\((\\d+)/(\\d+)\\) (.+)\\.\\.\\.$"), (...m) => "Polishing ($1/$2)...".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^状态栏 \\((\\d+) 字\\)$"), (...m) => "Status Bar ($1 chars)".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^无法创建文件夹\\s*\\((.+?)\\):\\s*(.+)$"), (...m) => "Cannot create folder ($1): $2".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^文件夹不存在:\\s*(.+)$"), (...m) => "Folder not found: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^路径不存在:\\s*(.+)$"), (...m) => "Path not found: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^预设不存在:\\s*(.+)$"), (...m) => "Preset not found: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已完成：(.+)$"), (...m) => "Completed: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^连接 HuggingFace：(.+)$"), (...m) => "Connecting to HuggingFace: $1".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^下载\\s*(.+?)\\s*失败，可换源重试$"), (...m) => "Download $1 failed, switch mirror or retry".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^首次加载\\s*(.+?)，构建 Strata 包\\.\\.\\.$"), (...m) => "First load $1, building Strata package...".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^首次加载\\s*(.+?)，注册模型\\.\\.\\.$"), (...m) => "First load $1, registering model...".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^切换至\\s*(.+?)\\.\\.\\.$"), (...m) => "Switching to $1...".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^启动 Strata 引擎\\s*\\((.+?)\\)，约 30~90 秒\\.\\.\\.$"), (...m) => "Starting Strata engine ($1), ~30-90s...".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^缺少 Strata 引擎文件（(.+?)）$"), (...m) => "Missing Strata engine files ($1)".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    [new RegExp("^已提交(.*)，等待响应\\.\\.\\.$"), (...m) => "Submitted$1, waiting for response...".replace(/\$(\d)/g, (_, n) => m[n] ?? "")],
    // === end merged patterns ===
    // Context & Token badges
    [/^✅ 已自动从 API 拉取到\s*(\d+)\s*个可用模型$/, (_, n) => `✅ Auto-fetched ${n} available model(s) from API`],
    [/^✅ 成功拉取到\s*(\d+)\s*个模型，点击即可选用$/, (_, n) => `✅ Fetched ${n} model(s), click to select`],
    [/^✅ 已添加并切换当前模型为：(.+)$/, (_, m) => `✅ Added and switched current model to: ${m}`],
    [/^(.+?)\s*【手动添加】$/, (_, m) => `${m} [Manual]`],
    [/^(\d+)\s*\/\s*(\d+)\s*条\s*\(([^)]+)\)$/, (_, a, b, c) => `${a} / ${b} msgs (${c})`],
    [/^\(([^)]+)\)\s*·\s*(\d+)\s*条$/, (_, a, b) => `(${a}) · ${b} msgs`],
    [/^(\d+)\s*字符\s*·\s*约\s*(\d+)\s*Tokens$/, (_, a, b) => `${a} chars · ~${b} Tokens`],
    [/^点击放大查看参考图\s*#(\d+)$/, (_, n) => `Click to enlarge reference image #${n}`],
    [/^共\s*(\d+)\s*个模型$/, (_, n) => `${n} models total`],
    [/^共\s*(\d+)\s*张角色卡$/, (_, n) => `${n} character cards total`],
    [/^当前已选\s*(\d+)\s*张角色卡（将随下一条回复一同发送）$/, (_, n) => `${n} character card(s) selected (will be sent with next message)`],
    [/^当前已选\s*(\d+)\s*张角色卡$/, (_, n) => `${n} character card(s) selected`],
    [/^已选\s*(\d+)\s*张角色卡（将随消息一同发送）$/, (_, n) => `${n} character card(s) selected (attached to message)`],
    [/^已选\s*(\d+)\s*张角色卡$/, (_, n) => `${n} character card(s) selected`],
    [/^已就绪\s*(\d+)\s*张图片（将随消息一同发送）$/, (_, n) => `${n} image(s) ready (attached to message)`],
    [/^已就绪\s*(\d+)\s*张图片$/, (_, n) => `${n} image(s) ready`],
    [/^已选\s*(\d+)\s*张图片$/, (_, n) => `${n} image(s) selected`],
    [/^\((\d+)\s*张\)$/, (_, n) => `(${n} images)`],
    [/^\(设置\s*\+\s*(\d+)\s*预设\)$/, (_, n) => `(Settings + ${n} presets)`],
    [/^\((\d+)\s*份对话日志\)$/, (_, n) => `(${n} chat logs)`],
    [/^\((\d+)条\)$/, (_, n) => `(${n} msgs)`],
    [/^📥 导入所选图片\s*\((\d+)\)$/, (_, n) => `📥 Insert Selected (${n})`],
    [/^⏳ 正在导入\s*\((\d+)\)\.\.\.$/, (_, n) => `⏳ Inserting (${n})...`],
    [/^📷 附带图片\s*\((\d+)\)$/, (_, n) => `📷 Attach Images (${n})`],
    [/^⚙️\s*管理开场白\s*\((\d+)\)$/, (_, n) => `⚙️ Manage Greetings (${n})`],
    [/^🎬\s*(.+)$/, (_, t) => `🎬 ${translateSingleString(t.trim()) || t.trim()}`],
    [/^#(.+)$/, (_, t) => `#${translateSingleString(t.trim()) || t.trim()}`],
    [/^开场白\s*#?(\d+)$/, (_, n) => `Greeting #${n}`],
    [/^新游戏\s*#(\d+)$/, (_, n) => `New Game #${n}`],
    [/^(.+?)\s*\(副本\)$/, (_, n) => `${translateSingleString(n.trim()) || n.trim()} (Copy)`],
    [/^(.+?)\s*\(新\)$/, (_, n) => `${translateSingleString(n.trim()) || n.trim()} (New)`],
    [/^新对话\s*#(\d+)\s*\((.+)\)$/, (_, n, t) => `New Chat #${n} (${t})`],
    [/^分支\s*#(\d+)(.*)$/, (_, n, rest) => `Branch #${n}${rest}`],
    [/^全部游戏\s*\((\d+)\)$/, (_, n) => `All Games (${n})`],
    [/^📁 我的现有游戏\s*\((\d+)\)$/, (_, n) => `📁 My Games (${n})`],
    [/^🧭 预设模组\s*\((\d+)\)$/, (_, n) => `🧭 Preset Modules (${n})`],
    [/^📜 组装后的完整消息\s*\((\d+)\s*条\)$/, (_, n) => `📜 Assembled Prompt Messages (${n})`],
    [/^(.+?)\s*【本地\s*·\s*手动指定】$/, (_, m) => `${m} [Local · Manual]`],
    [/^(.+?)\s*【本地\s*·\s*(.+?)】$/, (_, m, lbl) => `${m} [Local · ${lbl}]`],
    [/^本地运行\s*\((.+?)\)$/, (_, lbl) => `Local Runtime (${lbl})`],
    [/^手动配置的本地模型\s*\((.+?)\)$/, (_, u) => `Manually configured local model (${u})`],
    [/^本地模型\s*\((.+?)\)$/, (_, u) => `Local model (${u})`],
    [/^(.+?)\s*【本地】$/, (_, m) => `${m} [Local]`],
    [/^(.+?)\s*【API\s*·\s*(.+?)】$/, (_, m, p) => `${m} [API · ${p.replace("/次", "/call")}]`],
    [/^当前模型\s*\((.+?)\)：$/, (_, m) => `Current Model (${m}):`],
    [/^当前模型：$/, () => `Current Model:`],
    [/^当前对话模型:\s*(.+)$/, (_, m) => `Current Chat Model: ${m === "默认" ? "Default" : m}`],
    [/^欢迎来到\s*(.+)$/, (_, n) => `Welcome to ${translateSingleString(n.trim()) || n.trim()}`],
    [/^([+➕]\s*)?为「(.+?)」设置多个可选开场白$/, (_, pfx, n) => `${pfx || "➕ "}Set Multiple Opening Greetings for "${translateSingleString(n.trim()) || n.trim()}"`],
    [/^点击切换至游戏:\s*(.+?)（双击名称可直接重命名）$/, (_, n) => `Click to switch to game: ${translateSingleString(n.trim()) || n.trim()} (Double-click name to rename)`],
    [/^打开「(.+?)」的游戏设置$/, (_, n) => `Open Game Settings for "${translateSingleString(n.trim()) || n.trim()}"`],
    [/^角色卡：(.+)$/, (_, n) => `Character Card: ${translateSingleString(n.trim()) || n.trim()}`],
    [/^✏️ 编辑角色卡：(.+)$/, (_, n) => `✏️ Edit Character Card: ${translateSingleString(n.trim()) || n.trim()}`],
    [/^✨ 新建游戏 \(高级\) — 沿用「(.+?)」逐栏修改与 AI 润色$/, (_, n) => `✨ New Game (Advanced) — Customize & AI Polish from "${translateSingleString(n.trim()) || n.trim()}"`],
    [/^📁 已切换至游戏：(.+)$/, (_, n) => `📁 Switched to game: ${translateSingleString(n.trim()) || n.trim()}`],
    [/^✨ 已新建空白游戏：(.+)$/, (_, n) => `✨ Created blank game: ${translateSingleString(n.trim()) || n.trim()}`],
    [/^✨ 已沿用并创建新游戏：(.+)$/, (_, n) => `✨ Created new game from template: ${translateSingleString(n.trim()) || n.trim()}`],
    [/^✨ 新游戏「(.+?)」已创建完成！$/, (_, n) => `✨ New game "${translateSingleString(n.trim()) || n.trim()}" created!`],
    [/^已切换模型：(.+)$/, (_, m) => `Switched model to: ${m}`],
    [/^已刷新模型列表（共\s*(\d+)\s*个）$/, (_, n) => `Refreshed model list (${n} models found)`],
    [/^🤖 本对话模型已切换为:\s*(.+)$/, (_, m) => `🤖 Chat model switched to: ${m}`],
    [/^🤖 AI 辅助\/润色\/总结模型已切换为：(.+)$/, (_, m) => `🤖 AI Assist/Polish/Summary model switched to: ${m}`],
    [/^🔄 已将全局数值参数同步应用到全部\s*(\d+)\s*个游戏！$/, (_, n) => `🔄 Synced global parameters to all ${n} games!`],
    [/^🪪 已选择角色卡「(.+?)」，将随下一条消息一同发送！$/, (_, n) => `🪪 Selected character card "${n}" to send with next message!`],
    [/^已取消选择角色卡：「(.+?)」$/, (_, n) => `Deselected character card: "${n}"`],
    [/^💾 (简易|高级)角色卡「(.+?)」已保存$/, (_, t, n) => `💾 ${t === "简易" ? "Simple" : "Advanced"} character card "${n}" saved`],
    [/^📤 已导出角色卡：(.+)$/, (_, n) => `📤 Exported character card: ${n}`],
    [/^确定要从角色卡库中删除「(.+?)」吗？$/, (_, n) => `Are you sure you want to delete "${n}" from Character Cards?`],
    [/^✅ 成功导入\s*(\d+)\s*张角色卡！$/, (_, n) => `✅ Imported ${n} character card(s)!`],
    [/^✅ 已成功导入\s*(\d+)\s*张素材图片$/, (_, n) => `✅ Imported ${n} image(s) from gallery`],
    [/^⏳ 正在上传\s*(\d+)\s*张新图片至素材库\.\.\.$/, (_, n) => `⏳ Uploading ${n} image(s) to gallery...`],
    [/^📷 已选择\s*(\d+)\s*张图片，正在处理\.\.\.$/, (_, n) => `📷 Processing ${n} selected image(s)...`],
    [/^🧹 已自动清理\s*(\d+)\s*张重复\/测试图片，剩余\s*(\d+)\s*张精选素材$/, (_, r, a) => `🧹 Cleaned ${r} duplicate image(s), ${a} unique assets remaining`],
    [/^✨ 素材库非常整洁，全部\s*(\d+)\s*张图片均无重复$/, (_, a) => `✨ Gallery is clean! All ${a} images are unique.`],
    [/^⚡ 正在使用\s*(.+?)\s*提炼浓缩早期剧情\.\.\.$/, (_, m) => `⚡ Summarizing earlier plot using ${m}...`],
    [/^🧠 服务端正在深度识图与推演长篇剧情……\s*\(已等待\s*(\d+)\s*秒\)$/, (_, s) => `🧠 Server is analyzing images and generating story... (waited ${s}s)`],
    [/^🖼️\s*解锁CG:\s*(.+)$/, (_, t) => `🖼️ Unlocked CG: ${translateSingleString(t.trim()) || t.trim()}`],
    [/^🌍\s*(.+)$/, (_, t) => `🌍 ${translateSingleString(t.trim()) || t.trim()}`],
    [/^🖼️\s*触发剧情关键词，已解锁 CG：【(.+)】$/, (_, n) => `🖼️ Plot keyword triggered! Unlocked CG: [${n}]`],
    [/^【附带角色卡：(.+)】$/, (_, names) => `[Attached Character Card(s): ${names.replace(/、/g, ", ")}]`],
    [/^⚠️\s*接口提示:\s*(.+)$/, (_, m) => `⚠️ API Notice: ${translateSingleString(m.trim()) || m.trim()}`],
    [/^⚠️\s*生成连接中断:\s*(.+?)（服务端后台可能仍在生成，可刷新或点击重新生成查看）$/, (_, m) => `⚠️ Connection interrupted: ${m} (Server may still be generating in background; refresh or click Regenerate)`],
    [/^🖼️\s*已附带\s*(\d+)\s*张参考图供 AI 识别：$/, (_, n) => `🖼️ ${n} reference image(s) attached for AI vision:`],
    [/^(🖼️\s*已附带\s*\d+\s*张参考图，)?🌐 正在联网检索角色资料并调用 AI 自动整理填充卡片\.\.\.$/, (_, p) => `${p ? p.replace(/🖼️\s*已附带\s*(\d+)\s*张参考图，/, "🖼️ $1 image(s) attached, ") : ""}🌐 Searching the web and auto-filling character card with AI...`],
    [/^(🖼️\s*已附带\s*\d+\s*张参考图，)?🤖 正在调用 AI 视觉与知识库自动编写并填充角色卡片资料\.\.\.$/, (_, p) => `${p ? p.replace(/🖼️\s*已附带\s*(\d+)\s*张参考图，/, "🖼️ $1 image(s) attached, ") : ""}🤖 Generating and filling character card with AI vision & knowledge...`],
    [/^✅ 已自动填充「(.+?)」的角色卡资料（(.+?)），核对后点击右下角保存即可！$/, (_, n, src) => `✅ Auto-filled character card for "${n}" (${src.replace("已由 AI 知识库生成", "generated by AI").replace("已融合 ", "").replace(/(\d+)\s*张参考图视觉解析/, "$1 image(s) vision").replace(/(\d+)\s*条联网检索资料/, "$1 web result(s)")}). Review and click Save at bottom-right!`],
    [/^✨ 已自动填充角色卡：「(.+?)」$/, (_, n) => `✨ Auto-filled character card: "${n}"`],
    [/^📦 已选择文件夹（共\s*(\d+)\s*个文件），正在上传导入\.\.\.$/, (_, n) => `📦 Selected folder (${n} files), uploading and importing...`],
    [/^📊 统计：游戏\s*(\d+)\s*个\s*·\s*对话记录\s*(\d+)\s*条\s*·\s*设置\s*(\d+)\s*项\s*·\s*预设\s*(\d+)\s*个\s*·\s*图片\s*(\d+)\s*张\s*·\s*日志\s*(\d+)\s*条$/, (_, a, b, c, d, e, f) => `📊 Stats: ${a} Games · ${b} Chats · ${c} Settings · ${d} Presets · ${e} Images · ${f} Logs`],
    [/^📊 已恢复：游戏\s*(\d+)\s*个\s*·\s*对话记录\s*(\d+)\s*条\s*·\s*设置\s*(\d+)\s*项\s*·\s*预设\s*(\d+)\s*个\s*·\s*图片\s*(\d+)\s*张\s*·\s*日志\s*(\d+)\s*条$/, (_, a, b, c, d, e, f) => `📊 Restored: ${a} Games · ${b} Chats · ${c} Settings · ${d} Presets · ${e} Images · ${f} Logs`],
    [/^✅ 已选择文件夹:\s*(.+)$/, (_, p) => `✅ Selected folder: ${p}`],
    [/^📋\s*(.+)$/, (_, t) => `📋 ${translateSingleString(t.trim()) || t.trim()}`],
    [/^左侧栏宽度:\s*(.+)$/, (_, v) => `Sidebar Width: ${v}`],
    [/^游戏列表高度:\s*(.+)$/, (_, v) => `Game List Height: ${v}`],
    [/^游戏设置工作台:\s*(.+)$/, (_, v) => `Game Settings Width: ${v}`],
    [/^前情备忘高度:\s*(.+)$/, (_, v) => `Summary Height: ${v}`],
    [/^行动输入框高度:\s*(.+)$/, (_, v) => `Input Box Height: ${v}`],
    [/^消息气泡宽度:\s*(.+)$/, (_, v) => `Bubble Width: ${v}`],
    [/^弹窗尺寸:\s*(.+)$/, (_, v) => `Modal Size: ${v}`],
    [/^重命名游戏失败:\s*(.+)$/, (_, e) => `Failed to rename game: ${translateSingleString(e.trim()) || e}`],
    [/^创建游戏失败:\s*(.+)$/, (_, e) => `Failed to create game: ${translateSingleString(e.trim()) || e}`],
    [/^复制游戏失败:\s*(.+)$/, (_, e) => `Failed to duplicate game: ${translateSingleString(e.trim()) || e}`],
    [/^删除游戏失败:\s*(.+)$/, (_, e) => `Failed to delete game: ${translateSingleString(e.trim()) || e}`],
    [/^新建对话失败:\s*(.+)$/, (_, e) => `Failed to create chat: ${translateSingleString(e.trim()) || e}`],
    [/^重命名失败:\s*(.+)$/, (_, e) => `Rename failed: ${translateSingleString(e.trim()) || e}`],
    [/^删除失败:\s*(.+)$/, (_, e) => `Delete failed: ${translateSingleString(e.trim()) || e}`],
    [/^清空失败:\s*(.+)$/, (_, e) => `Clear failed: ${translateSingleString(e.trim()) || e}`],
    [/^切换模型失败:\s*(.+)$/, (_, e) => `Failed to switch model: ${translateSingleString(e.trim()) || e}`],
    [/^保存备忘失败:\s*(.+)$/, (_, e) => `Failed to save summary: ${translateSingleString(e.trim()) || e}`],
    [/^压缩总结失败:\s*(.+)$/, (_, e) => `Context compression failed: ${translateSingleString(e.trim()) || e}`],
    [/^修改失败:\s*(.+)$/, (_, e) => `Update failed: ${translateSingleString(e.trim()) || e}`],
    [/^保存失败:\s*(.+)$/, (_, e) => `Save failed: ${translateSingleString(e.trim()) || e}`],
    [/^保存角色卡失败:\s*(.+)$/, (_, e) => `Failed to save character card: ${translateSingleString(e.trim()) || e}`],
    [/^删除角色卡失败:\s*(.+)$/, (_, e) => `Failed to delete character card: ${translateSingleString(e.trim()) || e}`],
    [/^AI 生成角色卡失败:\s*(.+)$/, (_, e) => `AI character card generation failed: ${translateSingleString(e.trim()) || e}`],
    [/^⚠️ 生成失败:\s*(.+)$/, (_, e) => `⚠️ Generation failed: ${translateSingleString(e.trim()) || e}`],
    [/^导入\s*(.+?)\s*失败:\s*(.+)$/, (_, f, e) => `Failed to import ${f}: ${translateSingleString(e.trim()) || e}`],
    [/^同步到所有游戏失败:\s*(.+)$/, (_, e) => `Failed to sync to all games: ${translateSingleString(e.trim()) || e}`],
    [/^同步失败:\s*(.+)$/, (_, e) => `Sync failed: ${translateSingleString(e.trim()) || e}`],
    [/^保存设置失败:\s*(.+)$/, (_, e) => `Failed to save settings: ${translateSingleString(e.trim()) || e}`],
    [/^打开文件夹失败:\s*(.+)$/, (_, e) => `Failed to open folder: ${translateSingleString(e.trim()) || e}`],
    [/^❌ 导出失败：(.+)$/, (_, e) => `❌ Export failed: ${translateSingleString(e.trim()) || e}`],
    [/^导出失败:\s*(.+)$/, (_, e) => `Export failed: ${translateSingleString(e.trim()) || e}`],
    [/^❌ 导入失败：(.+)$/, (_, e) => `❌ Import failed: ${translateSingleString(e.trim()) || e}`],
    [/^❌ 文件夹导入失败：(.+)$/, (_, e) => `❌ Folder import failed: ${translateSingleString(e.trim()) || e}`],
    [/^导入失败:\s*(.+)$/, (_, e) => `Import failed: ${translateSingleString(e.trim()) || e}`],
    [/^网络异常:\s*(.+)$/, (_, e) => `Network error: ${e}`],
    [/^网络请求异常:\s*(.+)$/, (_, e) => `Network request error: ${e}`],
    [/^请求失败:\s*(.+)$/, (_, e) => `Request failed: ${e}`],
    [/^AI 润色失败:\s*(.+)$/, (_, e) => `AI polish failed: ${translateSingleString(e.trim()) || e}`],
    [/^AI 整套润色失败:\s*(.+)$/, (_, e) => `Full-game AI polish failed: ${translateSingleString(e.trim()) || e}`],
    [/^读取日志失败:\s*(.+)$/, (_, e) => `Failed to load logs: ${e}`],
    [/^创建分支失败:\s*(.+)$/, (_, e) => `Failed to create branch: ${translateSingleString(e.trim()) || e}`],
    [/^上传图标失败:\s*(.+)$/, (_, e) => `Failed to upload icon: ${translateSingleString(e.trim()) || e}`],
    [/^上传背景失败:\s*(.+)$/, (_, e) => `Failed to upload background: ${translateSingleString(e.trim()) || e}`],
    [/^上传图片失败:\s*(.+)$/, (_, e) => `Failed to upload image: ${translateSingleString(e.trim()) || e}`],
    [/^加载失败:\s*(.+)$/, (_, e) => `Failed to load: ${translateSingleString(e.trim()) || e}`],
    [/^活跃上下文约\s*(.+?)\s*\/\s*(.+?)\s*tokens（(\d+)\s*条未压缩消息\s*·\s*点击打开上下文控制与一键压缩）$/, (_, cur, max, cnt) => `Active context ~${cur} / ${max} tokens (${cnt} unsummarized msgs · Click for context controls & compression)`],
    [/^【🎲 掷骰\s*(.+?)】(.*)$/, (_, d, r) => `[🎲 Roll ${d}]${r}`]
  ];

  // English version of OpenTavern blank template
  const EN_OPENTAVERN_TEMPLATE = `Character Name:
Gender:
Age / Birthday:
Identity / Class:
Race:

1. Appearance System (Visual & Sensory)
Face & Head:
Physique & Body:
Sensory Details:
- Voice:
- Scent:
- Touch:
- Mannerisms / Body Language:

2. Outfit System
Daily Outfit:
Home / Casual Outfit:
Combat / Formal Outfit:
Outfit Notes:

3. Personality System (3 Layers + Emotional Triggers)
Outer Persona:
Inner Nature:
Core Drive:
Emotional Triggers:

4. Speech Style (Crucial for Roleplay)
Speech Summary:
Catchphrases / Verbal Tics:
Tone Shifts by Emotion:
- Calm / Daily:
- Flustered / Exposed:
- Serious / Angry:
- Intimate / Affectionate:
- Despair / Breakdown:

5. Backstory & Motivation
Past Events:
Current Goals (Short-term & Long-term):
Greatest Fear / Weakness:
Hidden Secret:

6. Relationships & Attitude Toward {{user}}
Relationship Network:
How They Address {{user}}:
True Feelings Toward {{user}} (Outer vs. Inner):
Dynamic Progression:`;

  function detectInitialLanguage() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === "zh" || saved === "en") return saved;
    } catch (e) {}
    const navLang = String(navigator.language || navigator.userLanguage || "zh").toLowerCase();
    const detected = navLang.startsWith("zh") ? "zh" : "en";
    try {
      localStorage.setItem(STORAGE_KEY, detected);
    } catch (e) {}
    return detected;
  }

  let currentLang = detectInitialLanguage();
  window.currentAppLang = currentLang;

  function translateSingleString(str) {
    if (!str || typeof str !== "string") return str;
    const isMultiline = str.includes("\n") || str.includes("\r");
    const rawTrim = str.replace(/\r\n/g, "\n").trim();
    if (!rawTrim) return str;

    if (EXACT_DICT[rawTrim]) {
      return EXACT_DICT[rawTrim];
    }

    const trimmed = rawTrim.replace(/\s+/g, " ").trim();
    if (!isMultiline) {
      if (EXACT_DICT[trimmed]) {
        return EXACT_DICT[trimmed];
      }
      if (COLLAPSED_DICT[trimmed]) {
        return COLLAPSED_DICT[trimmed];
      }

      for (let i = 0; i < PATTERN_RULES.length; i++) {
        const [regex, replacer] = PATTERN_RULES[i];
        const match = trimmed.match(regex);
        if (match) {
          return replacer(...match);
        }
      }

      // Comma-separated tag lists (e.g. "动态世界书, HTML状态栏, 多分支剧情")
      if ((trimmed.includes(",") || trimmed.includes("，")) && trimmed.length < 120) {
        const parts = trimmed.split(/\s*[,，]\s*/).filter(Boolean);
        if (parts.length > 1 && parts.every((p) => EXACT_DICT[p])) {
          return parts.map((p) => EXACT_DICT[p]).join(", ");
        }
      }
    }

    // Multi-part compound strings (e.g. Context tooltip or pricing detail)
    if (trimmed.includes("计算模式：") && trimmed.includes("当前携带活跃消息：")) {
      return str
        .replace("计算模式：", "Calculation Mode: ")
        .replace(/按轮数计算（上限\s*(\d+)\s*轮\s*\/\s*(\d+)\s*条）/, "By Turns (Max $1 turns / $2 msgs)")
        .replace(/按 Token 数计算（上限\s*([^）]+)）/, "By Tokens (Max $1)")
        .replace(/当前携带活跃消息：(\d+)\s*条（未压缩共\s*(\d+)\s*条）/, "Active Messages in Context: $1 ($2 uncompressed)")
        .replace(/已压缩进前情备忘：(\d+)\s*条（总计\s*(\d+)\s*条）/, "Compressed into Summary: $1 ($2 total)")
        .replace("上下文长度：", "Context Tokens: ");
    }

    if (trimmed.startsWith("API 按次：") || trimmed.startsWith("API 按量：")) {
      return trimmed
        .replace("API 按次：", "API Per-Call: ")
        .replace("API 按量：", "API Token-Based: ")
        .replace(/\/次/g, "/call")
        .replace("输入", "In")
        .replace("输出", "Out");
    }

    return null;
  }
  window.tStr = function (str) {
    if (currentLang !== "en") return str;
    return translateSingleString(str) || str;
  };

  // Wrap native browser dialogs so any confirm/alert/prompt calls are translated in English mode
  if (typeof window.confirm === "function" && !window._i18nOrigConfirm) {
    window._i18nOrigConfirm = window.confirm.bind(window);
    window.confirm = function (msg) {
      return window._i18nOrigConfirm(window.tStr(String(msg || "")));
    };
  }
  if (typeof window.alert === "function" && !window._i18nOrigAlert) {
    window._i18nOrigAlert = window.alert.bind(window);
    window.alert = function (msg) {
      return window._i18nOrigAlert(window.tStr(String(msg || "")));
    };
  }
  if (typeof window.prompt === "function" && !window._i18nOrigPrompt) {
    window._i18nOrigPrompt = window.prompt.bind(window);
    window.prompt = function (msg, defVal) {
      return window._i18nOrigPrompt(window.tStr(String(msg || "")), defVal !== undefined ? window.tStr(String(defVal)) : undefined);
    };
  }

  function shouldSkipElement(el) {
    if (!el || el.nodeType !== 1) return true;
    const tag = el.tagName;
    if (tag === "SCRIPT" || tag === "STYLE" || tag === "CODE" || tag === "PRE" || tag === "TEXTAREA") return true;
    // Inside user chat message bubbles (.message-item.user .bubble), keep user-entered Chinese prose untouched,
    // except UI badges/buttons attached to the bubble.
    if (el.closest && el.closest(".message-item.user .bubble")) {
      if (
        el.closest(".msg-charcard-badge") ||
        el.closest(".msg-inline-actions") ||
        el.closest(".dice-roll-badge")
      ) {
        return false;
      }
      return true;
    }
    return false;
  }

  function processTextNode(node) {
    const parent = node.parentElement;
    if (!parent || shouldSkipElement(parent)) return;

    const curVal = node.nodeValue || "";
    if (!curVal.trim()) return;

    if (currentLang === "en") {
      // If node was never translated, or JS dynamically updated its text to a new Chinese string
      if (node._origZh === undefined || (node._lastEn !== undefined && curVal !== node._lastEn)) {
        if (/[\u4e00-\u9fff]/.test(curVal)) {
          node._origZh = curVal;
        } else {
          return;
        }
      }
      const srcZh = node._origZh;
      if (!srcZh) return;
      const translated = translateSingleString(srcZh);
      if (translated) {
        // Preserve leading/trailing whitespace
        const lead = (srcZh.match(/^\s*/) || [""])[0];
        const trail = (srcZh.match(/\s*$/) || [""])[0];
        const nextEn = lead + translated + trail;
        if (node.nodeValue !== nextEn) {
          node._lastEn = nextEn;
          node.nodeValue = nextEn;
        }
      }
    } else {
      // Restore original Chinese if we previously translated this node
      if (node._origZh !== undefined && node.nodeValue === node._lastEn) {
        node.nodeValue = node._origZh;
      }
    }
  }

  const TRANSLATABLE_ATTRS = ["placeholder", "title", "label", "alt"];

  function processElementAttributes(el) {
    if (!el || el.nodeType !== 1) return;
    if (el.tagName === "SCRIPT" || el.tagName === "STYLE") return;

    for (let i = 0; i < TRANSLATABLE_ATTRS.length; i++) {
      const attr = TRANSLATABLE_ATTRS[i];
      if (!el.hasAttribute(attr)) continue;
      const curAttr = el.getAttribute(attr) || "";
      const dataKeyOrig = `_origAttr_${attr}`;
      const dataKeyLastEn = `_lastEnAttr_${attr}`;

      if (currentLang === "en") {
        if (el[dataKeyOrig] === undefined || (el[dataKeyLastEn] !== undefined && curAttr !== el[dataKeyLastEn])) {
          if (/[\u4e00-\u9fff]/.test(curAttr)) {
            el[dataKeyOrig] = curAttr;
          } else {
            continue;
          }
        }
        const srcZh = el[dataKeyOrig];
        if (!srcZh) continue;
        const translated = translateSingleString(srcZh);
        if (translated && curAttr !== translated) {
          el[dataKeyLastEn] = translated;
          el.setAttribute(attr, translated);
        }
      } else {
        if (el[dataKeyOrig] !== undefined && curAttr === el[dataKeyLastEn]) {
          el.setAttribute(attr, el[dataKeyOrig]);
        }
      }
    }

    // Handle OpenTavern template in #charEditDescription when switching languages
    if (el.id === "charEditDescription" && el.tagName === "TEXTAREA") {
      if (currentLang === "en" && el.value && el.value.includes("一、外貌系统（视觉 + 感官）")) {
        el._origZhTemplate = el.value;
        el.value = EN_OPENTAVERN_TEMPLATE;
        return;
      } else if (currentLang === "zh" && el.value === EN_OPENTAVERN_TEMPLATE && el._origZhTemplate) {
        el.value = el._origZhTemplate;
        return;
      }
    }

    // Handle <input> values that hold built-in default/preset/UI strings (never mutate <textarea> user prompts/JSON/lorebooks)
    if (
      el.tagName === "INPUT" &&
      el.id !== "userInput" &&
      el.type !== "password" &&
      el.type !== "number" &&
      el.type !== "range" &&
      el.type !== "checkbox" &&
      el.type !== "radio" &&
      el.type !== "file" &&
      el.value
    ) {
      const rawVal = el.value;
      const curVal = rawVal.trim();
      if (currentLang === "en") {
        if (el._origRoVal === undefined || (el._lastEnRoVal !== undefined && rawVal !== el._lastEnRoVal && curVal !== el._lastEnRoVal)) {
          if (/[\u4e00-\u9fff]/.test(curVal)) {
            const trCheck = translateSingleString(rawVal);
            if (trCheck) {
              el._origRoVal = rawVal;
            }
          }
        }
        if (el._origRoVal) {
          const tr = translateSingleString(el._origRoVal);
          if (tr && el.value !== tr) {
            el._lastEnRoVal = tr;
            el.value = tr;
            if (el.id === "stProjSystem" && typeof window.updatePromptCharCount === "function") {
              window.updatePromptCharCount(el);
            }
          }
        }
      } else {
        if (el._origRoVal !== undefined && (rawVal === el._lastEnRoVal || curVal === el._lastEnRoVal)) {
          el.value = el._origRoVal;
          if (el.id === "stProjSystem" && typeof window.updatePromptCharCount === "function") {
            window.updatePromptCharCount(el);
          }
        } else if (REVERSE_FIELD_LABELS[curVal]) {
          el.value = REVERSE_FIELD_LABELS[curVal];
          if (el.id === "stProjSystem" && typeof window.updatePromptCharCount === "function") {
            window.updatePromptCharCount(el);
          }
        }
      }
    }
  }

  function translateSubtree(root) {
    if (!root) return;
    if (root.nodeType === 3) {
      processTextNode(root);
      return;
    }
    if (root.nodeType !== 1) return;

    processElementAttributes(root);

    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, null, false);
    let curr = walker.nextNode();
    while (curr) {
      if (curr.nodeType === 3) {
        processTextNode(curr);
      } else if (curr.nodeType === 1) {
        processElementAttributes(curr);
      }
      curr = walker.nextNode();
    }
  }
  window.translateSubtree = translateSubtree;
  window.EN_OPENTAVERN_TEMPLATE = EN_OPENTAVERN_TEMPLATE;

  let isMutating = false;

  function updateLanguageSelectorUI() {
    const labelEl = document.getElementById("currentLangLabel");
    if (labelEl) {
      labelEl.textContent = currentLang === "en" ? "EN" : "中文";
    }
    const chkZh = document.getElementById("langCheckZh");
    const chkEn = document.getElementById("langCheckEn");
    if (chkZh) chkZh.textContent = currentLang === "zh" ? "✓" : "";
    if (chkEn) {
      chkEn.style.display = "inline";
      chkEn.textContent = currentLang === "en" ? "✓" : "";
    }
  }

  window.toggleLanguageMenu = function (event) {
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }
    const menu = document.getElementById("langDropdownMenu");
    if (!menu) return;
    const triggerBtn =
      (event && event.currentTarget) ||
      (event && event.target && event.target.closest("button")) ||
      document.getElementById("btnSidebarLangSwitch");
    const isVis = menu.style.display === "block" && menu._anchorBtn === triggerBtn;
    if (isVis) {
      menu.style.display = "none";
      menu._anchorBtn = null;
      return;
    }
    menu._anchorBtn = triggerBtn;
    if (triggerBtn && triggerBtn.getBoundingClientRect) {
      const rect = triggerBtn.getBoundingClientRect();
      menu.style.position = "fixed";
      menu.style.top = `${Math.round(rect.bottom + 6)}px`;
      const leftPos = Math.min(window.innerWidth - 165, Math.max(8, Math.round(rect.left)));
      menu.style.left = `${leftPos}px`;
      menu.style.right = "auto";
    }
    menu.style.display = "block";
  };

  window.setAppLanguage = function (lang, event) {
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }
    const nextLang = lang === "en" ? "en" : "zh";
    currentLang = nextLang;
    window.currentAppLang = nextLang;
    try {
      localStorage.setItem(STORAGE_KEY, nextLang);
    } catch (e) {}

    const menu = document.getElementById("langDropdownMenu");
    if (menu) {
      menu.style.display = "none";
      menu._anchorBtn = null;
    }

    isMutating = true;
    try {
      updateLanguageSelectorUI();
      translateSubtree(document.body);
    } finally {
      isMutating = false;
    }
  };

  // Close language dropdown when clicking outside
  document.addEventListener("click", (e) => {
    const menu = document.getElementById("langDropdownMenu");
    const btn1 = document.getElementById("btnHeaderLangSwitch");
    const btn2 = document.getElementById("btnSidebarLangSwitch");
    if (menu && menu.style.display === "block") {
      if (!menu.contains(e.target) && e.target !== btn1 && !btn1?.contains(e.target) && e.target !== btn2 && !btn2?.contains(e.target)) {
        menu.style.display = "none";
        menu._anchorBtn = null;
      }
    }
  });

  // Start MutationObserver so dynamically rendered modals/tabs/toasts are translated automatically
  const observer = new MutationObserver((mutations) => {
    if (isMutating || currentLang !== "en") return;
    isMutating = true;
    try {
      for (let i = 0; i < mutations.length; i++) {
        const m = mutations[i];
        if (m.type === "characterData") {
          processTextNode(m.target);
        } else if (m.type === "attributes") {
          processElementAttributes(m.target);
        } else if (m.type === "childList") {
          m.addedNodes.forEach((n) => {
            if (n.nodeType === 3) {
              processTextNode(n);
            } else if (n.nodeType === 1) {
              translateSubtree(n);
            }
          });
        }
      }
    } finally {
      isMutating = false;
    }
  });

  function initI18n() {
    updateLanguageSelectorUI();
    if (currentLang === "en") {
      translateSubtree(document.body);
    }
    if (document.body) {
      observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true,
        attributes: true,
        attributeFilter: TRANSLATABLE_ATTRS
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initI18n);
  } else {
    initI18n();
  }
})();

