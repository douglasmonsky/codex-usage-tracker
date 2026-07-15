import { describe, expect, it } from 'vitest';

import type { AllowanceSeriesPayload, AllowanceStatusPayload } from '../../api/types';
import { buildAllowanceIntelligenceVisualization } from './allowanceIntelligenceVisualization';

describe('allowance intelligence visualization', () => {
  it('keeps observations distinct from reconstructed and validated values', () => {
    const spec = buildAllowanceIntelligenceVisualization(seriesPayload(), statusPayload(), 'weekly');

    expect(spec.data.rows.map(row => row.observed)).toEqual([10, 20, null, 30, null]);
    expect(spec.data.rows.at(-1)?.reconstructed).toBe(34);
    expect(spec.data.rows.at(-1)?.forecast).toBe(34);
    expect(spec.series.map(series => series.id)).toEqual(['observed', 'reconstructed', 'validated-forecast']);
    expect(spec.table.defaultSort).toEqual({ field: 'observedAt', direction: 'desc' });
    expect(spec.interactions?.zoom).toEqual({ axis: 'x', startPercent: 0, endPercent: 100 });
  });

  it('does not draw forecast or reconstruction series when evidence is unavailable', () => {
    const status = statusPayload();
    status.estimation = undefined;
    const spec = buildAllowanceIntelligenceVisualization(seriesPayload(), status, 'five_hour');
    expect(spec.series.map(series => series.id)).toEqual(['observed']);
    expect(spec.title).toBe('5-hour observed usage');
  });
});

function seriesPayload(): AllowanceSeriesPayload {
  return {
    schema: 'codex-usage-tracker-allowance-series-v2',
    model_version: 'allowance-v2',
    generated_at: '2026-07-15T12:00:00Z',
    revision: 'revision-1',
    requested_range: { preset: '8w', start_at: '2026-06-01T00:00:00Z', end_at: '2026-07-15T12:00:00Z' },
    available_range: { start_at: '2026-06-01T00:00:00Z', end_at: '2026-07-15T10:00:00Z' },
    granularity: 'week',
    truncated: false,
    downsampled: false,
    quality: { canonical: true, copied_rows_excluded: 3, observed_only: true },
    points: [
      { kind: 'observed', cycle_id: 'c1', observed_at: '2026-06-01T00:00:00Z', reset_at: null, used_percent: 10 },
      { kind: 'observed', cycle_id: 'c1', observed_at: '2026-06-08T00:00:00Z', reset_at: null, used_percent: 20 },
      { kind: 'reset', cycle_id: 'c2', observed_at: '2026-06-09T00:00:00Z', reset_at: 1_750_000_000 },
      { kind: 'observed', cycle_id: 'c2', observed_at: '2026-07-15T10:00:00Z', reset_at: null, used_percent: 30 },
    ],
    cycles: [],
  };
}

function statusPayload(): AllowanceStatusPayload {
  return {
    schema: 'codex-usage-tracker-allowance-status-v2',
    revision: 'revision-1',
    changed: true,
    data_state: 'fresh',
    generated_at: '2026-07-15T12:00:00Z',
    quality: { canonical: true, copied_rows_excluded: 3 },
    estimation: {
      model_version: 'reset-aware-v2',
      window_kind: 'weekly',
      capacity: {
        status: 'validated', credits_per_percent: 4, total_ratio_credits_per_percent: 4,
        robust_median_credits_per_percent: 4, iqr_credits_per_percent: 1, completed_cycle_count: 5,
        eligible_interval_count: 20, price_coverage: 1, unexplained_movement_share: 0,
        prior_only_errors: {}, cycle_weight_cap: 1,
      },
      coverage_gaps: { missing_pricing_interval_count: 0, eligible_interval_count: 20 },
      reconstructions: [],
      weekly_estimate: { used_percent: 34, clipped: false, reason: null, observed_at: '2026-07-15T10:00:00Z', post_observation_credits: 16 },
      forecast: { used_percent: 34, reason: null, sample_size: 6, quantiles: { p10: 31, p50: 34, p90: 39 } },
      validation: { status: 'validated', sample_size: 9, median_absolute_error: 2, mean_absolute_error: 2.2, rmse: 3, holdout: { sample_size: 6 } },
      pace_scenarios: { status: 'conditional', reason: null, if_current_pace_continues: 1.2, sample_count: 8, unit: 'percent_per_hour' },
    },
    next: { action: 'poll_status', poll_after_seconds: 30 },
  };
}
