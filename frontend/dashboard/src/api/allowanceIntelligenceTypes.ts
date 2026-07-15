// Versioned allowance-intelligence contracts shared by the live dashboard client.

export type AllowanceWindowKindV2 = 'weekly' | 'five_hour';
type AllowanceFreshness = 'fresh' | 'aging' | 'stale';
export type AllowanceDataState = AllowanceFreshness | 'empty' | 'partial';
type AllowancePointKind =
  | 'observed'
  | 'estimated'
  | 'forecast'
  | 'reset'
  | 'positive'
  | 'conflict'
  | 'censored'
  | 'unexplained_correction';
type AllowanceAnalysisStatus =
  | 'missing'
  | 'insufficient_evidence'
  | 'no_supported_change'
  | 'supported_change'
  | 'supported_changes';

type AllowanceDedupeQuality = {
  canonical: true;
  copied_rows_excluded: number;
};

export type AllowanceStatusWindow = {
  cohort_id: string;
  plan_type?: string | null;
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

type AllowanceCapacityEstimate = {
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

type AllowanceUsageEstimate = {
  used_percent: number | null;
  clipped: boolean;
  reason: string | null;
  observed_at?: string;
  post_observation_credits?: number;
};

type AllowanceForecastEstimate = {
  used_percent: number | null;
  reason: string | null;
  sample_size?: number;
  quantiles: { p10: number; p50: number; p90: number } | null;
};

type AllowanceValidation = {
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

type AllowancePaceScenarios = {
  status: 'conditional' | 'observed_only';
  reason: string | null;
  if_current_pace_continues: number | null;
  sample_count: number;
  unit: 'percent_per_hour';
  low?: number | null;
  high?: number | null;
  contributing_windows?: Record<string, unknown>;
};

type AllowanceEstimation = {
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

type AllowanceSeriesPoint = {
  kind: Extract<AllowancePointKind, 'observed' | 'reset'>;
  cycle_id: string;
  observed_at: string;
  reset_at: number | null;
  used_percent?: number | null;
};

type AllowanceCycleSummary = {
  cycle_id: string;
  reset_at: number | null;
  first_observed_at: string;
  last_observed_at: string;
  latest_used_percent: number | null;
  status: string;
  quality_grade: string | null;
  plan_type?: string | null;
};

type AllowanceCapacityPoint = {
  cycle_id: string;
  completed_at: string;
  credits_per_percent: number;
  rolling_median: number | null;
  rolling_q1: number | null;
  rolling_q3: number | null;
  quality_grade: string;
  price_coverage: number;
  regime_id: string | null;
  plan_type?: string | null;
};

type AllowanceCapacityEffect = {
  median_before_credits_per_percent: number;
  median_after_credits_per_percent: number;
  median_shift_credits_per_percent: number;
  cliffs_delta: number;
};

export type AllowanceCapacityBoundary = {
  boundary_id: string;
  split_index: number;
  before_cycle_id: string;
  after_cycle_id: string;
  effective_at: string;
  alpha: number;
  adjusted_p_value: number;
  effect_size: AllowanceCapacityEffect;
  confidence_interval?: Record<string, unknown> | null;
  permutation_method?: string;
  permutation_count?: number;
  seed?: number | null;
};

type AllowanceCapacityRegime = {
  regime_id: string;
  start_at: string;
  end_at: string;
  start_index: number;
  end_index: number;
  eligible_cycle_count: number;
  median_credits_per_percent: number;
  iqr_credits_per_percent: number;
  price_coverage: number;
};

type AllowanceCapacityHistory = {
  status: 'ready' | 'insufficient_completed_cycles' | 'unsupported_window_model';
  unit: 'credits_per_percent';
  points: AllowanceCapacityPoint[];
  buckets?: AllowanceCapacityPoint[];
  robust_domain?: { mode: 'tukey_1_5_iqr'; min: number | null; max: number | null };
  clipped_point_count?: number;
  eligible_cycle_count?: number;
  trailing_window_cycles?: number;
  plan_types?: string[];
  analysis_status?: AllowanceAnalysisStatus;
  boundaries?: AllowanceCapacityBoundary[];
  regimes?: AllowanceCapacityRegime[];
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
  capacity_history: AllowanceCapacityHistory;
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
  parameters: {
    min_cycles_per_regime: number;
    permutation_count: number;
    familywise_alpha: number;
    min_cycles_per_side?: number;
  };
  quality?: AllowanceDedupeQuality;
  detector_version?: string;
  selection_correction?: string;
  eligible_cycle_count?: number;
  excluded_cycle_count?: number;
  candidate_count?: number;
  reason?: string | null;
  adjusted_p_value?: number | null;
  effect_size?: AllowanceCapacityEffect | null;
  confidence_interval?: { low: number; high: number; confidence_level?: number } | null;
  familywise_alpha?: number;
  minimum_cycles_per_regime?: number;
  boundaries?: AllowanceCapacityBoundary[];
  regimes?: AllowanceCapacityRegime[];
  compatibility_status?: 'deprecated_single_boundary' | 'not_applicable';
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
