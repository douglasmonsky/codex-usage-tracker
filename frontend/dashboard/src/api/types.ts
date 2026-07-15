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

export type DedupeSummary = {
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

export type DonutDatum = {
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

export type AllowanceWindowKindV2 = 'weekly' | 'five_hour';
export type AllowanceFreshness = 'fresh' | 'aging' | 'stale';
export type AllowanceDataState = AllowanceFreshness | 'empty' | 'partial';
export type AllowancePointKind =
  | 'observed'
  | 'estimated'
  | 'forecast'
  | 'reset'
  | 'positive'
  | 'conflict'
  | 'censored'
  | 'unexplained_correction';
export type AllowanceAnalysisStatus =
  | 'missing'
  | 'insufficient_evidence'
  | 'no_supported_change'
  | 'supported_change';

export type AllowanceDedupeQuality = {
  canonical: true;
  copied_rows_excluded: number;
};

export type AllowanceStatusWindow = {
  cohort_id: string;
  used_percent: number | null;
  remaining_percent: number | null;
  reset_at: number | null;
  reset_countdown_seconds: number | null;
  observed_at: string;
  age_seconds: number;
  freshness: AllowanceFreshness;
  status: string;
  pricing_coverage: number | null;
  quality: string | null;
  canonical_source_revision: string | null;
};

export type AllowanceCapacityEstimate = {
  status: 'validated' | 'descriptive';
  credits_per_percent: number | null;
  total_ratio_credits_per_percent: number | null;
  robust_median_credits_per_percent: number | null;
  iqr_credits_per_percent: number | null;
  completed_cycle_count: number;
  eligible_interval_count: number;
  price_coverage: number;
  unexplained_movement_share: number | null;
  prior_only_errors: Record<string, unknown>;
  cycle_weight_cap: number;
};

export type AllowanceUsageEstimate = {
  used_percent: number | null;
  clipped: boolean;
  reason: string | null;
  observed_at?: string;
  post_observation_credits?: number;
};

export type AllowanceForecastEstimate = {
  used_percent: number | null;
  reason: string | null;
  sample_size?: number;
  quantiles: { p10: number; p50: number; p90: number } | null;
};

export type AllowanceValidation = {
  status: 'validated' | 'descriptive';
  sample_size: number;
  evaluation_horizon?: 'time_ordered_holdout';
  calibration_window?: 'strictly_earlier_completed_cycles';
  median_absolute_error: number | null;
  mean_absolute_error: number | null;
  rmse: number | null;
  holdout: { sample_size: number; [key: string]: unknown };
  [key: string]: unknown;
};

export type AllowancePaceScenarios = {
  status: 'conditional' | 'observed_only';
  reason: string | null;
  if_current_pace_continues: number | null;
  sample_count: number;
  unit: 'percent_per_hour';
  low?: number | null;
  high?: number | null;
  contributing_windows?: Record<string, unknown>;
};

export type AllowanceEstimation = {
  model_version: 'reset-aware-v2';
  window_kind: 'weekly';
  capacity: AllowanceCapacityEstimate;
  coverage_gaps: { missing_pricing_interval_count: number; eligible_interval_count: number };
  reconstructions: Record<string, unknown>[];
  weekly_estimate: AllowanceUsageEstimate;
  forecast: AllowanceForecastEstimate;
  validation: AllowanceValidation;
  pace_scenarios: AllowancePaceScenarios;
};

export type AllowanceStatusPayload = {
  schema: 'codex-usage-tracker-allowance-status-v2';
  revision: string;
  changed: boolean;
  model_version?: string;
  generated_at?: string;
  data_as_of?: string | null;
  privacy_mode?: string;
  include_archived?: boolean;
  data_state?: AllowanceDataState;
  weekly?: AllowanceStatusWindow | null;
  five_hour?: AllowanceStatusWindow | null;
  estimation?: AllowanceEstimation;
  quality: AllowanceDedupeQuality;
  cohorts?: {
    selected: Record<string, unknown>;
    alternates: Record<string, unknown>[];
    reconciliation: Record<string, unknown>[];
  };
  next: { action: 'poll_status'; poll_after_seconds: number };
};

export type AllowanceSeriesPoint = {
  kind: Extract<AllowancePointKind, 'observed' | 'reset'>;
  cycle_id: string;
  observed_at: string;
  reset_at: number | null;
  used_percent?: number | null;
};

export type AllowanceCycleSummary = {
  cycle_id: string;
  reset_at: number | null;
  first_observed_at: string;
  last_observed_at: string;
  latest_used_percent: number | null;
  status: string;
  quality_grade: string | null;
};

export type AllowanceSeriesPayload = {
  schema: 'codex-usage-tracker-allowance-series-v2';
  model_version: string;
  generated_at: string;
  revision: string | null;
  requested_range: { preset: string; start_at: string; end_at: string };
  available_range: { start_at: string | null; end_at: string | null };
  granularity: 'auto' | 'raw' | 'hour' | 'day' | 'week' | 'month' | 'cycle';
  truncated: boolean;
  downsampled: boolean;
  quality: AllowanceDedupeQuality & { observed_only: boolean };
  points: AllowanceSeriesPoint[];
  cycles: AllowanceCycleSummary[];
};

export type AllowanceEvidenceRow = {
  interval_id?: string | null;
  cycle_id?: string | null;
  window_kind: AllowanceWindowKindV2;
  cohort_key?: string | null;
  end_observed_at: string;
  end_used_percent: number | null;
  point_kind: Extract<AllowancePointKind, 'positive' | 'conflict' | 'censored'>;
  censor_reason: string | null;
  source_revision?: string | null;
  start_record_id?: string | null;
  end_record_id?: string | null;
};

export type AllowanceEvidencePayload = {
  schema: 'codex-usage-tracker-allowance-evidence-v2';
  model_version: string;
  generated_at: string;
  revision: string | null;
  privacy_mode: 'strict' | 'normal' | 'local';
  rows: AllowanceEvidenceRow[];
  next_cursor: string | null;
  copied_rows_excluded: number;
  provenance: 'local' | 'local_aggregate';
  offline_export_action: 'build_allowance_export_report';
};

export type AllowanceAnalysisPayload = {
  schema: 'codex-usage-tracker-allowance-analysis-v2';
  status: AllowanceAnalysisStatus;
  snapshot_id: string;
  source_revision: string;
  model_version: string;
  rate_card_revision: string;
  generated_at?: string;
  data_as_of?: string | null;
  archive_scope?: 'active' | 'all';
  window_kind?: 'weekly';
  cohort_key?: string;
  forecast_horizon?: number;
  parameters: { min_cycles_per_side: number; permutation_count: number };
  quality?: AllowanceDedupeQuality;
  detector_version?: string;
  selection_correction?: string;
  eligible_cycle_count?: number;
  excluded_cycle_count?: number;
  candidate_count?: number;
  reason?: string | null;
  adjusted_p_value?: number | null;
  effect_size?: {
    median_before_credits_per_percent: number;
    median_after_credits_per_percent: number;
    median_shift_credits_per_percent: number;
    cliffs_delta: number;
  } | null;
  confidence_interval?: { low: number; high: number; confidence_level?: number } | null;
  caveats?: string[];
  next?: { action: 'start_analysis_job' };
  [key: string]: unknown;
};

export type AllowanceAnalysisJobPayload = {
  schema: 'codex-usage-tracker-analysis-job-v1';
  job_id: string;
  job_kind?: 'allowance-analysis';
  status: 'pending' | 'queued' | 'running' | 'completed' | 'failed' | 'missing';
  stage?: string;
  source_revision?: string;
  progress?: {
    completed_units: number;
    total_units: number | null;
    percent: number | null;
    current_unit: string | null;
  };
  result?: Record<string, unknown> | null;
  error?: Record<string, unknown> | null;
  next?: { action: string; job_id?: string; poll_after_ms?: number; endpoint?: string };
};
