import { describe, expect, it } from 'vitest';

import {
  decodeOverviewRecommendations,
  decodeOverviewSummary,
  OverviewContractError,
} from './overview';

describe('overview endpoint contracts', () => {
  it('normalizes summary token rows and history scope', () => {
    const report = decodeOverviewSummary({
      schema: 'codex-usage-tracker-summary-v1',
      group_by: 'date',
      include_archived: false,
      privacy_mode: 'normal',
      rows: [{ group_key: '2026-07-10', model_calls: 3, total_tokens: 1200, avg_cache_ratio: 0.75 }],
    });

    expect(report.includeArchived).toBe(false);
    expect(report.rows[0]).toMatchObject({ groupKey: '2026-07-10', modelCalls: 3, totalTokens: 1200 });
  });

  it('normalizes ranked recommendation evidence', () => {
    const report = decodeOverviewRecommendations({
      schema: 'codex-usage-tracker-recommendations-v1',
      filters: { include_archived: true },
      row_count: 1,
      total_matched_rows: 2,
      truncated: true,
      rows: [
        {
          record_id: 'call-1',
          event_timestamp: '2026-07-10T12:00:00Z',
          thread_name: 'Dashboard redesign',
          recommendation_score: 91,
          primary_recommendation: {
            key: 'low-cache',
            severity: 'medium',
            title: 'Low cache reuse',
            why: 'Fresh uncached input is high.',
            action: 'Inspect repeated context.',
          },
        },
      ],
    });

    expect(report).toMatchObject({ includeArchived: true, totalMatchedRows: 2, truncated: true });
    expect(report.rows[0].primaryRecommendation?.key).toBe('low-cache');
  });

  it('rejects responses from an unknown schema', () => {
    expect(() => decodeOverviewSummary({ schema: 'future-v2', rows: [] })).toThrow(OverviewContractError);
  });
});
