import { describe, expect, it } from 'vitest';

import type { AllowanceEvidenceRow, AllowanceStatusPayload } from '../../api/types';
import { buildAllowanceReadout, sortAllowanceEvidenceRows } from './allowanceIntelligenceModel';

describe('allowance intelligence presentation model', () => {
  it('labels reconstructed usage and personal calibration without implying an official conversion', () => {
    const readout = buildAllowanceReadout(statusPayload({
      weekly_estimate: {
        used_percent: 44,
        clipped: false,
        reason: null,
        observed_at: '2026-07-15T10:00:00Z',
        post_observation_credits: 16,
      },
      capacity: {
        status: 'descriptive',
        credits_per_percent: 4,
        total_ratio_credits_per_percent: 4.1,
        robust_median_credits_per_percent: 4,
        iqr_credits_per_percent: 0.8,
        completed_cycle_count: 4,
        eligible_interval_count: 18,
        price_coverage: 0.98,
        unexplained_movement_share: 0.03,
        prior_only_errors: {},
        cycle_weight_cap: 1,
      },
    }));

    expect(readout.primary.kind).toBe('estimated');
    expect(readout.primary.value).toBe('44%');
    expect(readout.primary.detail).toContain('40% observed');
    expect(readout.capacity.value).toBe('4 credits / 1%');
    expect(readout.capacity.detail).toContain('Personal historical calibration');
    expect(readout.capacity.detail).not.toContain('official');
    expect(readout.capacity.grade).toBe('Descriptive');
  });

  it('withholds forecasts that did not pass time-ordered validation', () => {
    const readout = buildAllowanceReadout(statusPayload({
      forecast: { used_percent: null, reason: 'insufficient_prior_cycle_evidence', quantiles: null },
    }));

    expect(readout.forecast.value).toBe('Unavailable');
    expect(readout.forecast.grade).toBe('Observed only');
    expect(readout.forecast.detail).toContain('time-ordered validation');
  });

  it('shows validated forecast intervals without replacing the observed anchor', () => {
    const readout = buildAllowanceReadout(statusPayload({
      weekly_estimate: { used_percent: 43, clipped: false, reason: null, observed_at: '2026-07-15T10:00:00Z', post_observation_credits: 12 },
      forecast: { used_percent: 43, reason: null, sample_size: 8, quantiles: { p10: 39, p50: 43, p90: 48 } },
    }));

    expect(readout.primary.kind).toBe('estimated');
    expect(readout.forecast.value).toBe('43%');
    expect(readout.forecast.detail).toContain('39–48%');
    expect(readout.weekly.value).toBe('40%');
  });

  it('defensively sorts supporting evidence newest first', () => {
    const rows = [evidenceRow('2026-07-01T00:00:00Z'), evidenceRow('2026-07-15T00:00:00Z')];
    expect(sortAllowanceEvidenceRows(rows).map(row => row.end_observed_at)).toEqual([
      '2026-07-15T00:00:00Z',
      '2026-07-01T00:00:00Z',
    ]);
    expect(rows[0].end_observed_at).toBe('2026-07-01T00:00:00Z');
  });
});

function statusPayload(estimationOverrides: Record<string, unknown>): AllowanceStatusPayload {
  return {
    schema: 'codex-usage-tracker-allowance-status-v2',
    revision: 'revision-1',
    changed: true,
    data_state: 'fresh',
    generated_at: '2026-07-15T12:00:00Z',
    weekly: {
      cohort_id: 'codex',
      used_percent: 40,
      remaining_percent: 60,
      reset_at: 1_752_595_200,
      reset_countdown_seconds: 86_400,
      observed_at: '2026-07-15T10:00:00Z',
      age_seconds: 7_200,
      freshness: 'fresh',
      status: 'observed',
      pricing_coverage: 0.98,
      quality: 'good',
      canonical_source_revision: 'revision-1',
    },
    five_hour: null,
    estimation: {
      model_version: 'reset-aware-v2',
      window_kind: 'weekly',
      capacity: {
        status: 'descriptive',
        credits_per_percent: null,
        total_ratio_credits_per_percent: null,
        robust_median_credits_per_percent: null,
        iqr_credits_per_percent: null,
        completed_cycle_count: 0,
        eligible_interval_count: 0,
        price_coverage: 0,
        unexplained_movement_share: null,
        prior_only_errors: {},
        cycle_weight_cap: 1,
      },
      coverage_gaps: { missing_pricing_interval_count: 0, eligible_interval_count: 0 },
      reconstructions: [],
      weekly_estimate: { used_percent: null, clipped: false, reason: 'insufficient_prior_capacity' },
      forecast: { used_percent: null, reason: 'insufficient_prior_cycle_evidence', quantiles: null },
      validation: {
        status: 'descriptive',
        sample_size: 0,
        mean_absolute_error: null,
        median_absolute_error: null,
        rmse: null,
        holdout: { sample_size: 0 },
      },
      pace_scenarios: {
        status: 'observed_only',
        reason: 'insufficient_recent_pace_samples',
        if_current_pace_continues: null,
        sample_count: 0,
        unit: 'percent_per_hour',
      },
      ...estimationOverrides,
    },
    quality: { canonical: true, copied_rows_excluded: 0 },
    next: { action: 'poll_status', poll_after_seconds: 30 },
  };
}

function evidenceRow(endObservedAt: string): AllowanceEvidenceRow {
  return {
    interval_id: endObservedAt,
    cycle_id: 'cycle-1',
    window_kind: 'weekly',
    end_observed_at: endObservedAt,
    end_used_percent: 20,
    point_kind: 'positive',
    censor_reason: null,
  };
}
