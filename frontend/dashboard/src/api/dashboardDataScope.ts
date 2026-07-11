export type DashboardDataScope = {
  history_scope?: string;
  include_archived?: boolean;
  load_window?: 'day' | 'week' | 'rows' | 'all';
  default_load_window?: 'day' | 'week' | 'rows' | 'all';
  since?: string | null;
};

export type DashboardScopeSummary = {
  visibleCalls: number;
  inputTokens: number;
  cachedInputTokens: number;
  uncachedInputTokens: number;
  outputTokens: number;
  reasoningOutputTokens: number;
  totalTokens: number;
  estimatedCostUsd: number;
  usageCredits: number;
};

export type DashboardModelScope = {
  scopeSummary?: DashboardScopeSummary;
};
