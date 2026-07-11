import { describe, expect, it } from 'vitest';

import { threadSummaryToRow } from './threadSummaryAdapter';

describe('threadSummaryToRow', () => {
  it('normalizes focused API rows into explorer thread rows', () => {
    const row = threadSummaryToRow({
      threadKey: 'thread-a',
      threadLabel: 'Thread A',
      firstEventTimestamp: '2026-07-01T00:00:00Z',
      latestEventTimestamp: '2026-07-10T00:00:00Z',
      latestRecordId: 'call-4',
      callCount: 4,
      sessionCount: 2,
      inputTokens: 1_000,
      cachedInputTokens: 700,
      uncachedInputTokens: 300,
      outputTokens: 100,
      reasoningOutputTokens: 50,
      totalTokens: 1_150,
      estimatedCostUsd: null,
      usageCredits: null,
      averageCacheRatio: 0.7,
      maxContextWindowPercent: 0.82,
      maxRecommendationScore: 80,
      primaryRecommendation: 'low_cache_reuse',
      initiatorSummary: 'mostly_user',
      archivedCallCount: 1,
      updatedAt: '2026-07-10T00:00:00Z',
    });

    expect(row).toMatchObject({
      threadKey: 'thread-a', name: 'Thread A', latestCallId: 'call-4', turns: 4, sessionCount: 2, cachePct: 70,
      contextPct: 82, coldResumeRisk: 'Low', recommendation: 'low_cache_reuse', archivedCallCount: 1,
    });
  });
});
