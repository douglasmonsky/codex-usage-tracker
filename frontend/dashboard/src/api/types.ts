import type { DashboardDataScope, DashboardModelScope } from './dashboardDataScope';

export type UsageRow = {
  id?: string;
  record_id?: string;
  session_id?: string;
  turn_id?: string | null;
  source_file?: string | null;
  line_number?: number | null;
  started_at?: string;
  call_started_at?: string;
  event_timestamp?: string;
  turn_timestamp?: string;
  time?: string;
  thread_name?: string | null;
  thread_key?: string | null;
  thread?: string;
  resolved_parent_thread_name?: string | null;
  parent_thread_name?: string | null;
  thread_attachment_label?: string | null;
  thread_source?: string | null;
  subagent_type?: string | null;
  agent_role?: string | null;
  agent_nickname?: string | null;
  project_name?: string | null;
  project_relative_cwd?: string | null;
  cwd?: string | null;
  project_tags?: string[] | null;
  git_branch?: string | null;
  git_remote_label?: string | null;
  git_remote_hash?: string | null;
  parent_session_id?: string | null;
  parent_session_updated_at?: string | null;
  resolved_parent_session_updated_at?: string | null;
  context_window_percent?: number | null;
  model_context_window?: number | null;
  model?: string;
  effort?: string;
  input_tokens?: number;
  cached_input_tokens?: number;
  output_tokens?: number;
  reasoning_output_tokens?: number;
  total_tokens?: number;
  uncached_input_tokens?: number;
  estimated_cost_usd?: number;
  usage_credits?: number;
  rate_limit_plan_type?: string | null;
  rate_limit_limit_id?: string | null;
  rate_limit_primary_used_percent?: number | null;
  rate_limit_primary_window_minutes?: number | null;
  rate_limit_primary_resets_at?: number | null;
  rate_limit_secondary_used_percent?: number | null;
  rate_limit_secondary_window_minutes?: number | null;
  rate_limit_secondary_resets_at?: number | null;
  duration_seconds?: number;
  call_duration_seconds?: number;
  previous_call_event_timestamp?: string | null;
  previous_call_delta_seconds?: number | null;
  call_initiator?: string | null;
  call_initiator_reason?: string | null;
  call_initiator_confidence?: string | null;
 cache_hit_ratio?: number;
 cache_ratio?: number;
 usage_credit_confidence?: string;
 usage_credit_model?: string | null;
 usage_credit_source?: string | null;
 usage_credit_fetched_at?: string | null;
  usage_credit_tier?: string | null;
  usage_credit_note?: string | null;
 pricing_model?: string | null;
 pricing_estimated?: boolean;
 primary_signal?: string | null;
 recommended_action?: string | null;
 cumulative_total_tokens?: number | null;
 estimated_cache_savings_usd?: number | null;
 efficiency_flags?: string[] | null;
};

export type DashboardBootPayload = DashboardDataScope & {
  api_token?: string;
  context_api_enabled?: boolean;
  refresh_jobs_available?: boolean;
  language?: string;
language_direction?: string;
available_languages?: DashboardLanguage[];
translations?: Record<string, string>;
translation_catalog?: Record<string, Record<string, string>>;
rows?: UsageRow[];
  summary?: Record<string, unknown>;
  observed_usage?: ObservedUsage;
  limit?: number | null;
  limit_label?: string;
  has_more?: boolean;
  latest_refresh_at?: string;
  refreshed_at?: string;
  loaded_row_count?: number;
  total_available_rows?: number;
  all_history_available_rows?: number;
  active_available_rows?: number;
  archived_available_rows?: number;
  pricing_configured?: boolean;
  pricing_source?: string | Record<string, unknown>;
  pricing_snapshot_warning?: string;
  allowance_configured?: boolean;
  allowance_source?: string | Record<string, unknown>;
  allowance_windows?: AllowanceWindow[];
  allowance_error?: string;
  rate_card_configured?: boolean;
  rate_card_error?: string;
  parser_diagnostics?: Record<string, number>;
  dedupe?: DedupeSummary;
  project_metadata_privacy?: ProjectMetadataPrivacy;
  privacy_mode?: string;
shell_boot?: boolean;
};

type DedupeSummary = {
  dedupe_enabled?: boolean;
  fingerprint_version?: string;
  physical_rows?: number;
  canonical_rows?: number;
  excluded_copied_rows?: number;
  duplicate_fingerprint_groups?: number;
  physical_total_tokens?: number;
  excluded_total_tokens?: number;
  canonical_total_tokens?: number;
  duplicate_reasons?: Record<string, number>;
};

export type DashboardLanguage = {
  code: string;
  english_name?: string;
  native_name?: string;
  dir?: string;
};

type ProjectMetadataPrivacy = {
  mode?: string;
  cwd_redacted?: boolean;
  project_names_redacted?: boolean;
  git_remote_label_hidden?: boolean;
  relative_cwd_hidden?: boolean;
  git_branch_hidden?: boolean;
  tags_hidden?: boolean;
  aliases_preserved?: boolean;
};

type ObservedUsage = {
  available?: boolean;
  source?: string;
  observed_at?: string;
  plan_type?: string;
  limit_id?: string;
  windows?: ObservedUsageWindow[];
  reconciliation?: Record<string, unknown>;
};

type ObservedUsageWindow = {
  key?: string;
  label?: string;
  used_percent?: number | null;
  window_minutes?: number | null;
  resets_at?: number | string | null;
};

type AllowanceWindow = {
  key?: string;
  label?: string;
  total_credits?: number | null;
  remaining_credits?: number | null;
  remaining_percent?: number | null;
  reset_at?: number | string | null;
};

export type ContextRuntime = {
  apiToken: string;
  contextApiEnabled: boolean;
  fileMode: boolean;
};

export type CallContextEntry = {
  type?: string;
  label?: string;
  role?: string;
  text?: string;
  timestamp?: string;
  line_number?: number;
  chars?: number;
  tokens?: number;
  tool_output_omitted?: boolean;
  token_usage?: {
    last_token_usage?: TokenUsageSummary | null;
    total_token_usage?: TokenUsageSummary | null;
    model_context_window?: number | null;
  };
  compaction?: {
    replacement_history_available?: boolean;
    replacement_entry_count?: number;
    replacement_history?: Array<{ label?: string; text?: string }>;
  };
  action_timing?: {
    since_turn_start_ms?: number;
    since_previous_entry_ms?: number;
    reported_duration_ms?: number;
    duration_source?: string;
  };
};

type TokenUsageSummary = {
  input_tokens?: number;
  cached_input_tokens?: number;
  uncached_input_tokens?: number;
  output_tokens?: number;
  reasoning_output_tokens?: number;
  total_tokens?: number;
};

export type CallContextPayload = {
  schema?: string;
  loaded_on_demand?: boolean;
  raw_context_persisted?: boolean;
  record_id?: string;
  include_tool_output?: boolean;
  include_compaction_history?: boolean;
  context_mode?: string;
  entries?: CallContextEntry[];
  visible_char_count?: number;
  visible_token_estimate?: number;
  visible_token_estimator?: string;
  omitted?: Record<string, unknown>;
  source?: {
    file?: string | null;
    line_number?: number | string | null;
  };
  record?: Record<string, unknown>;
  serialized_evidence?: {
    total_chars?: number;
    token_estimate?: number;
raw_json_char_count?: number;
raw_json_token_estimate?: number;
raw_line_count?: number;
token_estimator?: string;
buckets?: Array<{
      key?: string;
      label?: string;
      note?: string;
      count?: number;
      char_count?: number;
      token_estimate?: number;
    }>;
    deferred?: boolean;
    deferred_buckets?: boolean;
    parse_errors?: number;
  };
};

export type MetricTone = 'blue' | 'green' | 'purple' | 'orange' | 'red' | 'neutral';

export type MetricCard = {
  label: string;
  value: string;
  detail: string;
  trend: string;
  tone: MetricTone;
  breakdown?: Array<{ label: string; value: string }>;
};

type ChartPoint = {
  label: string;
  value: number;
  secondary?: number;
  low?: number;
  high?: number;
};

export type Series = {
  id: string;
  label: string;
  color: string;
  dashed?: boolean;
  points: ChartPoint[];
};

export type Finding = {
  rank: number;
  title: string;
  severity: 'High' | 'Medium' | 'Low';
  credits: number;
  share: number;
  summary: string;
};

export type CallRow = {
  id: string;
  threadKey?: string;
  rawTime: string;
  eventTimestamp: string;
  callStartedAt: string;
  time: string;
  thread: string;
  model: string;
  effort: string;
  input: number;
  output: number;
  reasoningOutput: number;
  totalTokens: number;
  cachedInput: number;
  uncachedInput: number;
  cachedPct: number;
  cost: number;
  credits: number;
  duration: string;
  durationSeconds: number;
  previousCallGap: string;
  previousCallEventTimestamp: string;
  previousCallGapSeconds: number;
  initiator: string;
  initiatorReason: string;
  initiatorConfidence: string;
 fast: boolean;
 usageCreditConfidence: string;
 usageCreditModel: string;
  usageCreditSource: string;
  usageCreditFetchedAt: string;
  usageCreditTier: string;
  usageCreditNote: string;
  pricingModel: string;
 pricingEstimated: boolean;
  signal: string;
  recommendation: string;
  tags: string[];
  sessionId: string;
  turnId: string;
  parentSessionId: string;
  parentSessionUpdatedAt: string;
  parentThread: string;
  threadAttachmentLabel: string;
  threadSource: string;
  subagentType: string;
  agentRole: string;
  agentNickname: string;
  project: string;
  projectRelativeCwd: string;
  projectTags: string[];
  cwd: string;
  sourceFile: string;
  lineNumber: number | null;
  gitBranch: string;
  gitRemoteLabel: string;
  gitRemoteHash: string;
 contextWindowPct: number | null;
 modelContextWindow: number | null;
 cumulativeTotalTokens: number | null;
 estimatedCacheSavings: number;
 efficiencyFlags: string[];
};

export type ThreadRow = {
  name: string;
  latestCallId: string;
  latestActivity: string;
  latestActivityRaw: string;
  turns: number;
  totalDurationSeconds: number;
  totalDuration: string;
  averageGapSeconds: number;
  averageGap: string;
  initiatorSummary: string;
  modelSummary: string;
  effortSummary: string;
  totalTokens: number;
  cachedInput: number;
  uncachedInput: number;
  outputTokens: number;
  reasoningOutput: number;
  cost: number;
  credits: number;
  cachePct: number;
  contextPct: number | null;
  costPerCall: number;
  coldResumeRisk: 'High' | 'Medium' | 'Low';
  productivity: number;
};

export type WeeklyWindow = {
  week: string;
  plan: string;
  observedPct: number;
  credits: number;
  projected: number;
  ciLow: number;
  ciHigh: number;
  confidence: 'High' | 'Medium' | 'Low';
  note: string;
};

export type BarDatum = {
  label: string;
  value: number;
  color?: string;
};

type DonutDatum = {
  label: string;
  value: number;
  color: string;
};

export type HeatmapRow = {
  thread: string;
  values: number[];
  labels?: string[];
};

export type DiagnosticSection = {
  title: string;
  status: 'Ready' | 'Stale' | 'Missing';
  finding: string;
  confidence: 'High' | 'Medium' | 'Low';
  metric: string;
  series: Series[];
};

export type ReportSummary = {
  title: string;
  status: 'Ready' | 'Planned' | 'Blocked';
  description: string;
  owner: string;
};

export type DashboardModel = DashboardModelScope & {
  contextRuntime: ContextRuntime;
  cards: MetricCard[];
  tokenSeries: Series[];
  costSeries: Series[];
  cacheSeries: Series[];
  weeklyCreditSeries: Series[];
  usageRemainingSeries: Series[];
  actualVsPredictedSeries: Series[];
  calls: CallRow[];
  threads: ThreadRow[];
  findings: Finding[];
  weeklyWindows: WeeklyWindow[];
  modelCosts: BarDatum[];
  commandActions: ReportSummary[];
  cacheSegments: DonutDatum[];
  cacheHeatmap: HeatmapRow[];
  diagnostics: DiagnosticSection[];
  reports: ReportSummary[];
};
