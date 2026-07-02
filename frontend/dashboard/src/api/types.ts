export type UsageRow = {
  id?: string;
  record_id?: string;
  session_id?: string;
  source_file?: string | null;
  line_number?: number | null;
  started_at?: string;
  call_started_at?: string;
  event_timestamp?: string;
  turn_timestamp?: string;
  time?: string;
  thread_name?: string | null;
  thread?: string;
  resolved_parent_thread_name?: string | null;
  parent_thread_name?: string | null;
  thread_attachment_label?: string | null;
  project_name?: string | null;
  project_relative_cwd?: string | null;
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
  duration_seconds?: number;
  call_duration_seconds?: number;
  cache_hit_ratio?: number;
  cache_ratio?: number;
  usage_credit_confidence?: string;
  pricing_estimated?: boolean;
  primary_signal?: string | null;
  recommended_action?: string | null;
};

export type DashboardBootPayload = {
  api_token?: string;
  context_api_enabled?: boolean;
  rows?: UsageRow[];
  summary?: Record<string, unknown>;
  observed_usage?: Record<string, unknown>;
  history_scope?: string;
  loaded_row_count?: number;
  total_available_rows?: number;
  all_history_available_rows?: number;
  active_available_rows?: number;
  pricing_source?: string | Record<string, unknown>;
  allowance_source?: string | Record<string, unknown>;
  privacy_mode?: string;
  shell_boot?: boolean;
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
};

export type CallContextPayload = {
  schema?: string;
  record_id?: string;
  context_mode?: string;
  entries?: CallContextEntry[];
  visible_char_count?: number;
  visible_token_estimate?: number;
  omitted?: Record<string, unknown>;
  serialized_evidence?: {
    total_chars?: number;
    token_estimate?: number;
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
};

export type ChartPoint = {
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
  rawTime: string;
  time: string;
  thread: string;
  model: string;
  effort: string;
  input: number;
  output: number;
  reasoningOutput: number;
  totalTokens: number;
  uncachedInput: number;
  cachedPct: number;
  cost: number;
  credits: number;
  duration: string;
  durationSeconds: number;
  fast: boolean;
  usageCreditConfidence: string;
  pricingEstimated: boolean;
  signal: string;
  recommendation: string;
  tags: string[];
};

export type ThreadRow = {
  name: string;
  turns: number;
  totalTokens: number;
  cost: number;
  cachePct: number;
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

export type DashboardModel = {
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
