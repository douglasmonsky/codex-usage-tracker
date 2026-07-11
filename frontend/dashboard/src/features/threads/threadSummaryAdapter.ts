import type { ThreadRow } from '../../api/types';
import type { ThreadSummaryRecord } from '../../data/contracts/explore';

export type ExploreThreadRow = ThreadRow & {
  threadKey: string;
  firstActivityRaw: string;
  sessionCount: number;
  recommendation: string;
  recommendationScore: number | null;
  archivedCallCount: number;
};

export function threadSummaryToRow(
  summary: ThreadSummaryRecord,
  loadedFallback?: ThreadRow,
): ExploreThreadRow {
  const cachePct = normalizedPercent(summary.averageCacheRatio);
  const contextPct = nullablePercent(summary.maxContextWindowPercent);
  const turns = summary.callCount;
  const cost = summary.estimatedCostUsd ?? loadedFallback?.cost ?? 0;
  const credits = summary.usageCredits ?? loadedFallback?.credits ?? 0;
  return {
    threadKey: summary.threadKey,
    name: summary.threadLabel || summary.threadKey,
    latestCallId: summary.latestRecordId || loadedFallback?.latestCallId || '',
    latestActivity: formatShortDate(summary.latestEventTimestamp),
    latestActivityRaw: summary.latestEventTimestamp,
    firstActivityRaw: summary.firstEventTimestamp,
    turns,
    sessionCount: summary.sessionCount,
    totalDurationSeconds: loadedFallback?.totalDurationSeconds ?? 0,
    totalDuration: loadedFallback?.totalDuration ?? '-',
    averageGapSeconds: loadedFallback?.averageGapSeconds ?? 0,
    averageGap: loadedFallback?.averageGap ?? '-',
    initiatorSummary: summary.initiatorSummary || loadedFallback?.initiatorSummary || 'unknown',
    modelSummary: loadedFallback?.modelSummary ?? 'Load thread calls',
    effortSummary: loadedFallback?.effortSummary ?? 'Load thread calls',
    totalTokens: summary.totalTokens,
    cachedInput: summary.cachedInputTokens,
    uncachedInput: summary.uncachedInputTokens,
    outputTokens: summary.outputTokens,
    reasoningOutput: summary.reasoningOutputTokens,
    cost,
    credits,
    cachePct,
    contextPct,
    costPerCall: cost / Math.max(turns, 1),
    coldResumeRisk: cachePct < 25 ? 'High' : cachePct < 45 ? 'Medium' : 'Low',
    productivity: loadedFallback?.productivity ?? Math.max(20, Math.round(cachePct - cost / Math.max(turns, 1) * 4)),
    recommendation: summary.primaryRecommendation,
    recommendationScore: summary.maxRecommendationScore,
    archivedCallCount: summary.archivedCallCount,
  };
}

function normalizedPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return value <= 1 ? value * 100 : value;
}

function nullablePercent(value: number | null): number | null {
  if (value === null || !Number.isFinite(value)) return null;
  return normalizedPercent(value);
}

function formatShortDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || '-';
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
}
