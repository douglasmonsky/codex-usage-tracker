export type ConversationalReadiness = {
  schema: 'codex-usage-tracker-conversational-readiness-v1';
  state: 'ready' | 'restart-required' | 'unavailable' | 'unknown';
  summary: string;
  next_action: string | null;
  configured_profile?: string;
  runtime_version_matches?: boolean;
  evidence: string[];
};

export type HomeFindingPayload = {
  finding_id: string;
  confidence: 'high' | 'review';
  title: string;
  summary: string;
  action: string;
  follow_up_prompt: string;
  evidence: { kind: 'call'; record_id: string };
};

export type HomeRecentEvidencePayload = {
  kind: 'call';
  evidence_id: string;
  label: string;
  detail: string;
  observed_at: string | null;
  record_id: string;
};

export type PricingSnapshot = {
  configured?: boolean;
  model_count?: number;
  official_model_count?: number;
  estimated_model_count?: number;
  fingerprint?: string | null;
  error?: string | null;
};

type HomeObservedUsageWindow = {
  key?: string;
  label?: string;
  used_percent?: number | null;
  window_minutes?: number | null;
  resets_at?: number | string | null;
};

type HomeObservedUsage = {
  available?: boolean;
  source?: string;
  observed_at?: string;
  plan_type?: string;
  limit_id?: string;
  windows?: HomeObservedUsageWindow[];
};

type HomeAllowanceWindow = {
  key?: string;
  label?: string;
  total_credits?: number | null;
  remaining_credits?: number | null;
  remaining_percent?: number | null;
  reset_at?: number | string | null;
  captured_at?: string | null;
};

type HomeUsageMetricsPayload = {
  calls: number;
  input_tokens: number;
  cached_input_tokens: number;
  uncached_input_tokens: number;
  output_tokens: number;
  reasoning_output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  usage_credits: number;
  pricing_coverage: number;
  credit_coverage: number;
  source_generation: number;
  materialized_calls: number;
};

export type HomeSummaryPayload = {
  schema: 'codex-usage-tracker-home-summary-v1';
  source_revision: string;
  latest_refresh_at: string | null;
  latest_event_at: string | null;
  accounting: {
    physical_rows: number;
    canonical_rows: number;
    excluded_copied_rows: number;
  };
  usage_metrics?: HomeUsageMetricsPayload | null;
  pricing: PricingSnapshot;
  allowance: {
    configured: boolean;
    error?: string | null;
    observed_usage: HomeObservedUsage;
    windows: HomeAllowanceWindow[];
  };
  findings: HomeFindingPayload[];
  recent_evidence: HomeRecentEvidencePayload[];
};

export type HomeStatusPayload = {
  schema: 'codex-usage-tracker-status-v1';
  conversational_analysis: ConversationalReadiness;
  home_summary: HomeSummaryPayload;
};
