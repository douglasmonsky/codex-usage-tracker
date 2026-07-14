import type { ContextRuntime } from './types';

export type AllowanceWindowKind = 'weekly' | 'five_hour';

export type AllowanceEvidenceGrade =
  | 'insufficient_data'
  | 'counter_noise_likely'
  | 'no_change_detected'
  | 'possible_regime_change'
  | 'strong_local_evidence'
  | 'inconclusive_other_usage_possible';

export type AllowanceHistoryRow = {
  observed_at: string | null;
  observed_date: string | null;
  source: string | null;
  window_key: string | null;
  window_kind: AllowanceWindowKind;
  window_minutes: number | null;
  used_percent: number | null;
  remaining_percent: number | null;
  resets_at: number | null;
  plan_type: string | null;
  limit_id: string | null;
  model: string | null;
  effort: string | null;
  total_tokens: number | null;
  usage_credits: number | null;
  usage_credit_confidence: string | null;
  record_id?: string | null;
  session_id?: string | null;
  line_number?: number | null;
};

type AllowanceMedianInterval = {
  method: 'exact_binomial_order_statistic';
  confidence_level: number;
  sample_size: number;
  available: boolean;
  low: number | null;
  high: number | null;
  achieved_coverage: number;
};

type AllowanceStatisticalEvidence = {
  detector_version: string;
  method: string;
  sample_size_before: number;
  sample_size_after: number;
  median_shift_credits_per_percent: number | null;
  median_confidence_interval_before_95?: AllowanceMedianInterval;
  median_confidence_interval_after_95?: AllowanceMedianInterval;
  effect_size_cliffs_delta: number | null;
  p_value_one_sided: number | null;
  combinations_evaluated: number | null;
  effect_direction: string;
  signal: string;
  public_claim_ready: boolean;
};

export type AllowanceChangeCandidate = {
  evidence_grade: AllowanceEvidenceGrade;
  window_kind: 'weekly';
  candidate_start_observed_at: string | null;
  candidate_end_observed_at: string | null;
  split_index: number;
  previous_span_count: number;
  recent_span_count: number;
  previous_median_credits_per_percent: number | null;
  recent_median_credits_per_percent: number | null;
  capacity_ratio: number | null;
  observed_recent_delta_percent: number | null;
  expected_recent_delta_percent_from_prior_baseline: number | null;
  unexplained_usage_percent: number | null;
  outside_usage_possible: boolean;
  statistical_evidence: AllowanceStatisticalEvidence;
};

export type AllowanceSpan = {
  window_kind: AllowanceWindowKind;
  plan_type: string | null;
  limit_id: string | null;
  start_observed_at?: string | null;
  end_observed_at?: string | null;
  start_observed_date?: string | null;
  end_observed_date?: string | null;
  start_used_percent: number | null;
  end_used_percent: number | null;
  delta_usage_percent: number | null;
  estimated_usage_credits: number | null;
  credits_per_percent: number | null;
  row_count: number;
  credit_confidence_mix: Record<string, number>;
  record_id?: string | null;
};

export type AllowanceWindowReport = {
  window_kind: AllowanceWindowKind;
  plan_type: string | null;
  limit_id: string | null;
  observation_count: number;
  positive_span_count: number;
  evidence_grade: AllowanceEvidenceGrade;
  span_stats: {
    baseline_rows: number;
    unchanged_rows: number;
    reset_or_negative_delta_rows: number;
    missing_used_percent_rows: number;
  };
  change_candidates: AllowanceChangeCandidate[];
  spans: AllowanceSpan[];
};

export type AllowanceResearchReadiness = {
  detector_version: string;
  ready_for_public_claim: boolean;
  weekly_positive_span_count: number;
  minimum_split_spans_for_public_claim: number;
  p_value_threshold_for_public_claim: number;
  best_candidate_capacity_ratio: number | null;
  reasons: string[];
};

type AllowanceDiagnosticsSummary = {
  observation_count: number;
  window_report_count: number;
  positive_span_count: number;
  candidate_change_count: number;
  primary_window_kind: AllowanceWindowKind | null;
  primary_evidence_grade: AllowanceEvidenceGrade;
  weekly_observation_count: number;
  five_hour_observation_count: number;
  research_readiness: AllowanceResearchReadiness;
};

export type AllowanceHistoryPayload = {
  schema: 'codex-usage-tracker-allowance-history-v1';
  generated_at: string;
  privacy_mode: string;
  include_archived: boolean;
  window_kind: AllowanceWindowKind | null;
  row_count: number;
  rows: AllowanceHistoryRow[];
  notes: string[];
};

export type AllowanceDiagnosticsPayload = {
  schema: 'codex-usage-tracker-allowance-diagnostics-v1';
  generated_at: string;
  privacy_mode: string;
  include_archived: boolean;
  window_kind: AllowanceWindowKind | null;
  summary: AllowanceDiagnosticsSummary;
  windows: AllowanceWindowReport[];
  spans: AllowanceSpan[];
  change_candidates: AllowanceChangeCandidate[];
  notes: string[];
};

export type AllowanceEvidenceExportPayload = {
  schema: 'codex-usage-tracker-allowance-evidence-export-v1';
  generated_at: string;
  privacy_mode: 'strict';
  include_archived: boolean;
  summary: AllowanceDiagnosticsSummary;
  windows: AllowanceWindowReport[];
  change_candidates: AllowanceChangeCandidate[];
  notes: string[];
};

type AllowanceRequest = {
  includeArchived?: boolean;
  limit?: number | null;
  windowKind?: AllowanceWindowKind;
};

export async function loadAllowanceHistory(
  runtime: ContextRuntime,
  options: AllowanceRequest = {},
): Promise<AllowanceHistoryPayload> {
  return loadAllowancePayload(runtime, '/api/allowance/history', requestParams(options, true),
    'codex-usage-tracker-allowance-history-v1', 'Allowance history');
}

export async function loadAllowanceDiagnostics(
  runtime: ContextRuntime,
  options: AllowanceRequest = {},
): Promise<AllowanceDiagnosticsPayload> {
  return loadAllowancePayload(runtime, '/api/allowance/diagnostics', requestParams(options, true),
    'codex-usage-tracker-allowance-diagnostics-v1', 'Allowance diagnostics');
}

export async function loadAllowanceEvidenceExport(
  runtime: ContextRuntime,
  options: AllowanceRequest = {},
): Promise<AllowanceEvidenceExportPayload> {
  return loadAllowancePayload(runtime, '/api/allowance/export', requestParams(options, false),
    'codex-usage-tracker-allowance-evidence-export-v1', 'Allowance evidence export');
}

function requestParams(options: AllowanceRequest, includePrivacyMode: boolean): URLSearchParams {
  const params = new URLSearchParams({
    limit: options.limit === null ? 'None' : String(Math.max(0, Math.round(options.limit ?? 0))),
  });
  if (options.includeArchived) params.set('include_archived', '1');
  if (options.windowKind) params.set('window_kind', options.windowKind);
  if (includePrivacyMode) params.set('privacy_mode', 'normal');
  return params;
}

async function loadAllowancePayload<T>(
  runtime: ContextRuntime,
  path: string,
  params: URLSearchParams,
  expectedSchema: string,
  label: string,
): Promise<T> {
  ensureAllowanceRuntime(runtime);
  const response = await fetch(`${path}?${params.toString()}`, {
    headers: {
      Accept: 'application/json',
      'X-Codex-Usage-Token': runtime.apiToken,
    },
    cache: 'no-store',
  });
  const payload = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (!response.ok) {
    throw new Error(typeof payload.error === 'string' ? payload.error : `${label} failed with HTTP ${response.status}`);
  }
  if (payload.schema !== expectedSchema) {
    throw new Error(`${label} returned an unsupported schema.`);
  }
  return payload as T;
}

function ensureAllowanceRuntime(runtime: ContextRuntime): void {
  if (runtime.fileMode || window.location.protocol === 'file:') {
    throw new Error('Live allowance intelligence requires the localhost dashboard server.');
  }
  if (!runtime.apiToken) {
    throw new Error('Live allowance intelligence requires the localhost dashboard API token.');
  }
}
