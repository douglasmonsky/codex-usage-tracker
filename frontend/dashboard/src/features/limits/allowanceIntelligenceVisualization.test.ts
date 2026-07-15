import { describe, expect, it } from 'vitest';

import { buildAllowanceIntelligenceVisualization } from './allowanceIntelligenceVisualization';
import type { AllowanceSeriesPayload, AllowanceStatusPayload } from '../../api/allowanceIntelligenceTypes';
import { buildEChartsVisualizationModel } from '../../visualization/renderer/optionBuilder';

describe('allowance intelligence visualization', () => {
  it('renders weekly capacity instead of usage percentage history', () => {
    const spec = buildAllowanceIntelligenceVisualization(
      seriesPayload(),
      statusPayload(),
      'weekly',
      { showFullRange: false },
    );

    expect(spec.title).toBe('Weekly limit capacity over time');
    expect(spec.data.rows.map(row => row.creditsPerPercent)).toEqual([100, 120, 900, 110]);
    expect(spec.series.map(series => series.id)).toEqual([
      'plan-pro-capacity',
      'plan-pro-median',
      'plan-prolite-capacity',
      'plan-prolite-median',
    ]);
    expect(spec.series.map(series => series.label)).toEqual([
      'Pro reset-window capacity',
      'Pro trailing median',
      'Pro Lite reset-window capacity',
      'Pro Lite trailing median',
    ]);
    expect(spec.showLegend).toBe(false);
    expect(spec.series[0]).toMatchObject({
      mark: 'line',
      color: '#3b82f6',
      lineWidth: 1.5,
      pointStyle: 'hollow',
      showPoints: true,
    });
    expect(spec.series[1]).toMatchObject({
      mark: 'line',
      color: '#1d4ed8',
      lineWidth: 3,
      pointStyle: 'none',
      showPoints: false,
    });
    expect(spec.series[0].color).not.toBe(spec.series[1].color);
    expect(spec.series[2].color).not.toBe(spec.series[3].color);
    const renderedSeries = buildEChartsVisualizationModel(spec).option.series as Array<Record<string, unknown>>;
    expect(renderedSeries[0]).toMatchObject({ symbol: 'emptyCircle', showSymbol: true, lineStyle: { color: '#3b82f6', width: 1.5 } });
    expect(renderedSeries[1]).toMatchObject({ symbol: 'none', showSymbol: false, lineStyle: { color: '#1d4ed8', width: 3 } });
    expect(buildEChartsVisualizationModel(spec).option.legend).toBeUndefined();
    expect(spec.axes.y.unit).toBe('credits_per_percent');
    expect(spec.axes.y.max).toBe(200);
    expect(spec.annotations).toHaveLength(2);
    expect(spec.annotations?.[0].label).toBe('Observed plan changed · Pro → Pro Lite');
    expect(spec.table.defaultSort).toEqual({ field: 'completedAt', direction: 'desc' });
    expect(spec.interactions?.zoom).toEqual({ axis: 'x', startPercent: 0, endPercent: 100 });
  });

  it('discloses robust-domain clipping and supports full range', () => {
    const robust = buildAllowanceIntelligenceVisualization(
      seriesPayload(), statusPayload(), 'weekly', { showFullRange: false },
    );
    const full = buildAllowanceIntelligenceVisualization(
      seriesPayload(), statusPayload(), 'weekly', { showFullRange: true },
    );

    expect(robust.caveats?.join(' ')).toContain('1 capacity point outside the robust range');
    expect(full.axes.y.max).toBeUndefined();
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
    capacity_history: {
      status: 'ready',
      unit: 'credits_per_percent',
      eligible_cycle_count: 4,
      trailing_window_cycles: 8,
      clipped_point_count: 1,
      robust_domain: { mode: 'tukey_1_5_iqr', min: 80, max: 200 },
      analysis_status: 'supported_changes',
      points: [
        capacityPoint('c1', '2026-06-01T00:00:00Z', 100, null, 'pro'),
        capacityPoint('c2', '2026-06-08T00:00:00Z', 120, null, 'pro'),
        capacityPoint('c3', '2026-06-15T00:00:00Z', 900, null, 'prolite'),
        capacityPoint('c4', '2026-06-22T00:00:00Z', 110, 115, 'prolite'),
      ],
      buckets: [],
      boundaries: [{
        boundary_id: 'boundary-2', split_index: 2, before_cycle_id: 'c2', after_cycle_id: 'c3',
        effective_at: '2026-06-15T00:00:00Z', alpha: 0.05, adjusted_p_value: 0.01,
        effect_size: {
          median_before_credits_per_percent: 110,
          median_after_credits_per_percent: 505,
          median_shift_credits_per_percent: 395,
          cliffs_delta: 1,
        },
      }],
      regimes: [],
    },
  };
}

function capacityPoint(
  cycleId: string,
  completedAt: string,
  creditsPerPercent: number,
  rollingMedian: number | null,
  planType: string,
) {
  return {
    cycle_id: cycleId,
    completed_at: completedAt,
    credits_per_percent: creditsPerPercent,
    rolling_median: rollingMedian,
    rolling_q1: rollingMedian === null ? null : 107.5,
    rolling_q3: rollingMedian === null ? null : 315,
    quality_grade: 'high',
    price_coverage: 1,
    regime_id: null,
    plan_type: planType,
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
