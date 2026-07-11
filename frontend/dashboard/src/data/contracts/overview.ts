type OverviewSummaryRow = {
  groupKey: string;
  modelCalls: number;
  sessions: number;
  turns: number;
  inputTokens: number;
  cachedInputTokens: number;
  uncachedInputTokens: number;
  outputTokens: number;
  reasoningOutputTokens: number;
  totalTokens: number;
  averageCacheRatio: number;
  latestEvent: string;
};

export type OverviewSummaryReport = {
  schema: 'codex-usage-tracker-summary-v1';
  groupBy: string;
  includeArchived: boolean;
  privacyMode: string;
  rows: OverviewSummaryRow[];
};

type OverviewRecommendation = {
  key: string;
  severity: 'high' | 'medium' | 'review';
  title: string;
  why: string;
  action: string;
};

export type OverviewRecommendationRow = {
  recordId: string;
  eventTimestamp: string;
  threadName: string;
  model: string;
  effort: string;
  totalTokens: number;
  uncachedInputTokens: number;
  contextWindowPercent: number | null;
  estimatedCostUsd: number;
  usageCredits: number;
  recommendationScore: number;
  primaryRecommendation: OverviewRecommendation | null;
  recommendedAction: string;
};

export type OverviewRecommendationsReport = {
  schema: 'codex-usage-tracker-recommendations-v1';
  includeArchived: boolean;
  rowCount: number;
  totalMatchedRows: number;
  truncated: boolean;
  rows: OverviewRecommendationRow[];
};

export class OverviewContractError extends Error {}

export function decodeOverviewSummary(value: unknown): OverviewSummaryReport {
  const report = record(value, 'summary report');
  if (report.schema !== 'codex-usage-tracker-summary-v1') {
    throw new OverviewContractError('Unsupported summary response schema.');
  }
  return {
    schema: report.schema,
    groupBy: text(report.group_by),
    includeArchived: boolean(report.include_archived),
    privacyMode: text(report.privacy_mode),
    rows: records(report.rows, 'summary rows').map(decodeSummaryRow),
  };
}

export function decodeOverviewRecommendations(value: unknown): OverviewRecommendationsReport {
  const report = record(value, 'recommendations report');
  if (report.schema !== 'codex-usage-tracker-recommendations-v1') {
    throw new OverviewContractError('Unsupported recommendations response schema.');
  }
  const filters = record(report.filters, 'recommendation filters');
  return {
    schema: report.schema,
    includeArchived: boolean(filters.include_archived),
    rowCount: number(report.row_count),
    totalMatchedRows: number(report.total_matched_rows),
    truncated: boolean(report.truncated),
    rows: records(report.rows, 'recommendation rows').map(decodeRecommendationRow),
  };
}

function decodeSummaryRow(value: Record<string, unknown>): OverviewSummaryRow {
  return {
    groupKey: text(value.group_key),
    modelCalls: number(value.model_calls),
    sessions: number(value.sessions),
    turns: number(value.turns),
    inputTokens: number(value.input_tokens),
    cachedInputTokens: number(value.cached_input_tokens),
    uncachedInputTokens: number(value.uncached_input_tokens),
    outputTokens: number(value.output_tokens),
    reasoningOutputTokens: number(value.reasoning_output_tokens),
    totalTokens: number(value.total_tokens),
    averageCacheRatio: number(value.avg_cache_ratio),
    latestEvent: text(value.latest_event),
  };
}

function decodeRecommendationRow(value: Record<string, unknown>): OverviewRecommendationRow {
  return {
    recordId: text(value.record_id),
    eventTimestamp: text(value.event_timestamp),
    threadName: text(value.thread_name || value.parent_thread_name || value.session_id),
    model: text(value.model),
    effort: text(value.effort),
    totalTokens: number(value.total_tokens),
    uncachedInputTokens: number(value.uncached_input_tokens),
    contextWindowPercent: nullableNumber(value.context_window_percent),
    estimatedCostUsd: number(value.estimated_cost_usd),
    usageCredits: number(value.usage_credits),
    recommendationScore: number(value.recommendation_score),
    primaryRecommendation: decodeRecommendation(value.primary_recommendation),
    recommendedAction: text(value.recommended_action),
  };
}

function decodeRecommendation(value: unknown): OverviewRecommendation | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const recommendation = value as Record<string, unknown>;
  const severity = recommendation.severity;
  if (severity !== 'high' && severity !== 'medium' && severity !== 'review') return null;
  return {
    key: text(recommendation.key),
    severity,
    title: text(recommendation.title),
    why: text(recommendation.why),
    action: text(recommendation.action),
  };
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new OverviewContractError(`Expected ${label} to be an object.`);
  }
  return value as Record<string, unknown>;
}

function records(value: unknown, label: string): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) throw new OverviewContractError(`Expected ${label} to be an array.`);
  return value.map((item, index) => record(item, `${label}[${index}]`));
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : value == null ? '' : String(value);
}

function number(value: unknown): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function nullableNumber(value: unknown): number | null {
  if (value == null || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function boolean(value: unknown): boolean {
  return value === true;
}
