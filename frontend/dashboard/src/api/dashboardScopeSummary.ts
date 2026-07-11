import type { DashboardBootPayload } from './types';
import type { DashboardScopeSummary } from './dashboardDataScope';

export function summaryNumber(payload: DashboardBootPayload, key: string): number {
  const value = Number(payload.summary?.[key] ?? 0);
  return Number.isFinite(value) ? value : 0;
}

export function scopeSummaryFromBootPayload(
  payload: DashboardBootPayload,
): DashboardScopeSummary | undefined {
  if (!payload.summary || payload.load_window === 'rows') return undefined;
  return {
    visibleCalls: summaryNumber(payload, 'visible_calls'),
    inputTokens: summaryNumber(payload, 'input_tokens'),
    cachedInputTokens: summaryNumber(payload, 'cached_input_tokens'),
    uncachedInputTokens: summaryNumber(payload, 'uncached_input_tokens'),
    outputTokens: summaryNumber(payload, 'output_tokens'),
    reasoningOutputTokens: summaryNumber(payload, 'reasoning_output_tokens'),
    totalTokens: summaryNumber(payload, 'total_tokens'),
    estimatedCostUsd: summaryNumber(payload, 'estimated_cost_usd'),
    usageCredits: summaryNumber(payload, 'usage_credits'),
  };
}
