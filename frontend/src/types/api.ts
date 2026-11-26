export type ExperienceMode = "simple" | "pro";
export type AppTab = "play" | "library" | "studio" | "engine" | "settings";
export type ThemeId = "lamplight-dark" | "lamplight-paper" | "midnight-slate";
export type LangId = "zh-CN" | "en-US";

export interface HardwareSnapshot {
  os_name: string;
  cpu_name: string;
  cpu_threads: number;
  ram_total_gib: number;
  ram_free_gib: number;
  free_disk_gb: number;
  has_nvidia: boolean;
  gpu_name: string;
  driver_version: string;
  driver_num: number;
  vram_total_mib: number;
  vram_free_mib: number;
  gpu_temp_c: number;
  gpu_power_w: number;
  tier: "S" | "A" | "B" | "C" | "CPU";
  tier_label: string;
  low_spec_recommended: boolean;
  recommended_preset_id: string;
  recommended_preset_label: string;
  recommended_max_context_k: number;
  supports_flash_next_strata: boolean;
}

export interface PreflightCheck {
  id: string;
  name: string;
  ok: boolean;
  level: "ok" | "warn" | "info";
  detail: string;
}

export interface DiagnosisAction {
  id: string;
  label: string;
  action: "enable_low_spec" | "open_engine_downloads" | "open_api_setup" | "run_preflight";
}

export interface EngineDiagnosis {
  code: string;
  engine: string;
  title: string;
  message: string;
  raw_tail?: string;
  actions: DiagnosisAction[];
}

export interface ProviderPreset {
  id: string;
  name: string;
  protocol: string;
  base_url: string;
  default_model: string;
  suggested_models: string[];
  key_hint: string;
  needs_proxy: boolean;
  badge: string;
}

export interface UserSettings {
  api_protocol: string;
  base_url: string;
  api_key: string;
  has_api_key?: boolean;
  model: string;
  custom_models: string[];
  custom_model_paths: string[];
  proxy: string;
  use_proxy: boolean;
  low_spec_mode: "auto" | "on" | "off";
  experience_mode: ExperienceMode;
  onboarding_completed: boolean;
  theme: ThemeId;
  language: LangId;
  temperature: number;
  repetition_penalty: number;
  frequency_penalty: number;
  presence_penalty: number;
  top_p: number;
  top_k: number;
  min_p: number;
  max_tokens: number;
  context_mode: string;
  max_context_k: number;
  keep_recent_messages: number;
  worldbook_scan_depth: number;
  thinking_budget: number;
  auto_summarize: boolean;
  kv_cache_mode: string;
  active_project_id: string;
  favorite_models: string[];
  model_params: Record<string, Record<string, any>>;
}

export interface GameStateResource {
  key: string;
  label: string;
  current: number;
  max: number;
}

export interface GameStateClock {
  name: string;
  current: number;
  max: number;
  kind?: string;
}

export interface GameStateNpc {
  name: string;
  affinity: number;
  relation: string;
  status: string;
  mood: string;
  notes?: string;
}

export interface GameState {
  resources: GameStateResource[];
  attributes: Record<string, any>;
  equipment: Record<string, { name: string; desc?: string }>;
  inventory: Array<{ name: string; qty: number; desc?: string }>;
  npcs: GameStateNpc[];
  quests: Array<{ title: string; status: string; progress?: string }>;
  clocks: GameStateClock[];
  scene: { time?: string; location?: string; condition?: string };
}

export interface ActionChoice {
  index: number;
  text: string;
  dice_skill?: string;
}

export interface DiceRollResult {
  expression: string;
  ruleset: string;
  skill: string;
  rolls: number[];
  kept: number[];
  modifier: number;
  raw_total: number;
  total: number;
  difficulty?: number | null;
  success?: boolean | null;
  tier: string;
  tier_label: string;
  hidden?: boolean;
}

export interface MessageSwipe {
  id: string;
  swipe_idx: number;
  content: string;
  thinking?: string;
  triggered_worldbooks?: Array<any>;
  triggered_cgs?: Array<any>;
  suggested_questions?: ActionChoice[];
}

export interface ChatMessage {
  id: string;
  parent_id?: string;
  role: "user" | "assistant" | "system";
  speaker_card_id?: string;
  speaker_name?: string;
  content: string;
  prompt_content?: string;
  thinking?: string;
  active_swipe_idx?: number;
  swipe_count?: number;
  swipes?: MessageSwipe[];
  state_snapshot?: GameState;
  dice_rolls?: DiceRollResult[];
  images?: string[];
  videos?: string[];
  character_cards?: CharacterCard[];
  triggered_worldbooks?: Array<any>;
  triggered_cgs?: Array<any>;
  suggested_questions?: ActionChoice[];
  is_opening?: boolean;
  interrupted?: boolean;
  timestamp?: number;
}

export interface BranchNode {
  id: string;
  parent_id: string;
  seq: number;
  role: string;
  speaker_name?: string;
  preview: string;
  on_active_branch: boolean;
  has_dice: boolean;
}

export interface AuthorNote {
  content: string;
  depth: number;
  role: string;
  enabled: boolean;
}

export interface GroupConfig {
  enabled: boolean;
  mode: string;
  members: Array<{ card_id: string; enabled: boolean; talkativeness: number }>;
}

export interface ChatSummary {
  id: string;
  title: string;
  project_id: string;
  model: string;
  active_node_id?: string;
  updated_at: number;
  message_count: number;
  has_summary: boolean;
}

export interface ChatFull {
  id: string;
  title: string;
  project_id: string;
  model: string;
  active_node_id: string;
  summary: string;
  author_note: AuthorNote;
  group_config: GroupConfig;
  persona_id: string;
  preset_id: string;
  variables: Record<string, any>;
  active_state: GameState;
  chapters: Array<{ id: string; chapter_num: number; title: string; summary: string }>;
  messages: ChatMessage[];
  context_tokens_est?: number;
  max_context_tokens?: number;
  is_generating?: boolean;
  partial_text?: string;
  generating_status?: string;
  last_error?: { error?: string; diagnosis?: EngineDiagnosis };
}

export interface WorldbookEntry {
  id: string;
  name: string;
  group: string;
  enabled: boolean;
  constant: boolean;
  keys: string[];
  secondary_keys?: string[];
  selective?: boolean;
  selective_logic?: number;
  match_type: string | number;
  key_region: number;
  value_region: string | number;
  sort: number;
  depth: number;
  probability: number;
  content: string;
}

export interface ProjectData {
  id: string;
  name: string;
  icon?: string;
  avatar?: string;
  description: string;
  detailed_description?: string;
  custom_css?: string;
  author?: string;
  category: string;
  tags: string[];
  ruleset?: "d20" | "d100" | "2d6" | "narrative";
  initial_state?: GameState;
  bundled_cards?: CharacterCard[];
  system_prompt: string;
  system_protocol_prompt?: string;
  prefix: string;
  suffix: string;
  opening_greetings: Array<{ id: string; title: string; content: string; isSandbox?: boolean }>;
  opening_statement?: string;
  simple_mode: boolean;
  cot_enabled: boolean;
  status_panel_enabled: boolean;
  ui_modules: Array<Record<string, any>>;
  world_book: WorldbookEntry[];
  regex_scripts: Array<Record<string, any>>;
  memory_palace: Array<{ title?: string; key?: string; content: string }>;
  use_global_params: boolean;
  completion_params: Record<string, any>;
}

export interface CharacterCard {
  id: string;
  name: string;
  avatar?: string;
  description: string;
  personality?: string;
  scenario?: string;
  first_mes?: string;
  tags?: string[];
}

export interface Persona {
  id: string;
  name: string;
  description: string;
  is_default: boolean;
}

export interface PromptPreset {
  id: string;
  name: string;
  is_default?: boolean;
  temperature?: number;
  top_p?: number;
  max_tokens?: number;
  source?: string;
  custom_blocks?: Array<Record<string, any>>;
}

export interface LocalModelMeta {
  id: string;
  name: string;
  engine: "llama" | "strata";
  supports_vision: boolean;
  gguf_path: string;
  shards_complete: boolean;
  shard_warning: string;
  source_label: string;
  description: string;
}

export interface HFPresetItem {
  id: string;
  series: string;
  series_title: string;
  repo_id: string;
  name: string;
  quant: string;
  engine: string;
  tier: string;
  recommended: boolean;
  not_recommended?: boolean;
  vram_hint: string;
  desc: string;
  installed: boolean;
  total_size_gb: number;
}

export interface HFDownloadTask {
  id: string;
  preset_id: string;
  title: string;
  status: string;
  progress: number;
  downloaded_bytes: number;
  total_bytes: number;
  speed_mb_s: number;
  current_file: string;
  error: string;
}
