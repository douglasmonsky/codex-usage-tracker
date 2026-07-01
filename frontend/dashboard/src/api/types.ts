export type UsageRow = {
  id?: string;
  record_id?: string;
  started_at?: string;
  time?: string;
  thread_name?: string;
  thread?: string;
  model?: string;
  effort?: string;
  input_tokens?: number;
  cached_input_tokens?: number;
  output_tokens?: number;
  reasoning_output_tokens?: number;
  total_tokens?: number;
  estimated_cost_usd?: number;
  usage_credits?: number;
  duration_seconds?: number;
  cache_hit_ratio?: number;
};

export type DashboardBootPayload = {
  api_token?: string;
  rows?: UsageRow[];
  summary?: Record<string, unknown>;
  observed_usage?: Record<string, unknown>;
  history_scope?: string;
  loaded_row_count?: number;
  total_available_rows?: number;
  all_history_available_rows?: number;
  active_available_rows?: number;
  pricing_source?: string;
  allowance_source?: string;
  privacy_mode?: string;
  shell_boot?: boolean;
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
  time: string;
  thread: string;
  model: string;
  effort: string;
  input: number;
  output: number;
  cachedPct: number;
  cost: number;
  duration: string;
  fast: boolean;
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
