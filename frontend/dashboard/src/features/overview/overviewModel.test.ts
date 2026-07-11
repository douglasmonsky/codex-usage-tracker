import { describe, expect, it } from 'vitest';

import type { OverviewEndpointBundle } from '../../data/overviewQueries';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import { buildOverviewViewModel } from './overviewModel';

describe('Overview view model', () => {
  it('uses loaded calls for totals and the focused recommendation endpoint for findings', () => {
    const endpoints: OverviewEndpointBundle = {
      summary: { data: null, error: 'summary unavailable' },
      recommendations: {
        error: null,
        data: {
          schema: 'codex-usage-tracker-recommendations-v1',
          includeArchived: false,
          rowCount: 1,
          totalMatchedRows: 1,
          truncated: false,
          rows: [{
            recordId: 'fixture-call-0',
            eventTimestamp: '2026-07-10T12:00:00Z',
            threadName: 'Dashboard redesign',
            model: 'codex-1',
            effort: 'high',
            totalTokens: 1000,
            uncachedInputTokens: 700,
            contextWindowPercent: 68,
            estimatedCostUsd: 0.2,
            usageCredits: 1.1,
            recommendationScore: 92,
            recommendedAction: 'Start fresh.',
            primaryRecommendation: {
              key: 'context-bloat',
              severity: 'high',
              title: 'High context pressure',
              why: 'The call used a large share of the context window.',
              action: 'Start a fresh thread for unrelated work.',
            },
          }],
        },
      },
    };

    const result = buildOverviewViewModel(fixtureModel, endpoints, 'active');

    expect(result.metrics.calls).toBe(fixtureModel.calls.length);
    expect(result.findings[0]).toMatchObject({ title: 'High context pressure', evidenceGrade: 'Moderate' });
    expect(result.answer.title).toContain('clearest current signal');
    expect(result.pulseSpec.state.kind).toBe('partial');
  });

  it('labels token accounting as loaded and non-causal', () => {
    const result = buildOverviewViewModel(fixtureModel, undefined, 'all');

    expect(result.pulseSpec.data.rows).toEqual([
      expect.objectContaining({ day: '2026-06-01' }),
    ]);
    expect(result.tokenFlowSpec.scope.label).toContain('loaded calls');
    expect(result.tokenFlowSpec.caveats?.[0]).toContain('not causality');
    expect(result.tokenFlowSpec.data.links.length).toBeGreaterThan(0);
  });
});
