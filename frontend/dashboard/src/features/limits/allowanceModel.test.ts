import { describe, expect, it } from 'vitest';

import type {
  AllowanceChangeCandidate,
  AllowanceDiagnosticsPayload,
  AllowanceEvidenceGrade,
  AllowanceHistoryPayload,
  AllowanceSpan,
  AllowanceWindowKind,
} from '../../api/allowance';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import { validateVisualizationSpec } from '../../visualization';
import {
  buildAllowanceWorkspace,
  buildFallbackAllowanceExport,
  evaluateAllowanceHypothesis,
} from './allowanceModel';
import { buildAllowanceVisualizationSpec } from './allowanceVisualization';

describe('allowance workspace model', () => {
  it('keeps stable weekly evidence conservative and contract-valid', () => {
    const diagnostics = diagnosticsPayload('no_change_detected', null, 'weekly');
    const workspace = buildAllowanceWorkspace(fixtureModel, diagnostics, historyPayload('weekly'));
    const spec = buildAllowanceVisualizationSpec(workspace, 'weekly');

    expect(workspace.live).toBe(true);
    expect(workspace.answer.title).toBe('No weekly regime change detected');
    expect(evaluateAllowanceHypothesis(workspace, 'decreased').badge).toBe('Not supported');
    expect(validateVisualizationSpec(spec)).toEqual([]);
    expect(spec.scope.label).toContain('weekly primary signal');
  });

  it('labels the five-hour view as noisy secondary context', () => {
    const diagnostics = diagnosticsPayload('counter_noise_likely', null, 'five_hour');
    const workspace = buildAllowanceWorkspace(fixtureModel, diagnostics, historyPayload('five_hour'));
    const spec = buildAllowanceVisualizationSpec(workspace, 'five_hour');

    expect(workspace.fiveHour.evidenceGrade).toBe('counter_noise_likely');
    expect(spec.title).toBe('5-hour rolling context');
    expect(spec.accessibility.summary).toContain('not primary allowance evidence');
    expect(validateVisualizationSpec(spec)).toEqual([]);
  });

  it('renders a candidate regime with exact median intervals and claim readiness', () => {
    const candidate = changeCandidate({ ready: true, outsideUsage: false, grade: 'strong_local_evidence' });
    const diagnostics = diagnosticsPayload('strong_local_evidence', candidate, 'weekly', true);
    const workspace = buildAllowanceWorkspace(fixtureModel, diagnostics, historyPayload('weekly'));
    const spec = buildAllowanceVisualizationSpec(workspace, 'weekly');

    expect(workspace.answer.badge).toBe('Claim-ready locally');
    expect(evaluateAllowanceHypothesis(workspace, 'decreased').badge).toBe('Supported locally');
    expect(spec.annotations?.some(annotation => annotation.id === 'candidate-regime-shift')).toBe(true);
    expect(spec.series[0]).toMatchObject({ lowerField: 'low', upperField: 'high' });
    expect(validateVisualizationSpec(spec)).toEqual([]);
  });

  it('marks observation gaps and resets without promoting them to a change claim', () => {
    const history = historyPayload('weekly');
    history.rows = [
      historyRow('2026-06-01T00:00:00Z', 10, 'rec-1'),
      historyRow('2026-06-01T01:00:00Z', 12, 'rec-2'),
      historyRow('2026-06-05T00:00:00Z', 4, 'rec-3'),
    ];
    history.row_count = history.rows.length;
    const workspace = buildAllowanceWorkspace(
      fixtureModel,
      diagnosticsPayload('no_change_detected', null, 'weekly'),
      history,
    );
    const annotations = buildAllowanceVisualizationSpec(workspace, 'weekly').annotations ?? [];

    expect(annotations.map(annotation => annotation.label)).toEqual(
      expect.arrayContaining(['Observation gap', 'Observed counter reset or rollback']),
    );
    expect(workspace.primaryGrade).toBe('no_change_detected');
  });

  it('treats outside usage as inconclusive and keeps fallback exports identifier-free', () => {
    const candidate = changeCandidate({ ready: false, outsideUsage: true, grade: 'inconclusive_other_usage_possible' });
    const workspace = buildAllowanceWorkspace(
      fixtureModel,
      diagnosticsPayload('inconclusive_other_usage_possible', candidate, 'weekly'),
      historyPayload('weekly'),
    );
    const fallback = buildAllowanceWorkspace(fixtureModel);
    const fallbackSpec = buildAllowanceVisualizationSpec(fallback, 'weekly');
    const encoded = JSON.stringify(buildFallbackAllowanceExport(fallback));

    expect(evaluateAllowanceHypothesis(workspace, 'decreased').badge).toBe('Inconclusive');
    expect(workspace.answer.title).toContain('not fully attributable');
    expect(fallback.fiveHour.points).toHaveLength(0);
    expect(fallbackSpec.description).toContain('Exact detector intervals require');
    expect(fallbackSpec.series[0]).not.toHaveProperty('lowerField');
    expect(encoded).not.toContain('fixture-call-');
    expect(encoded).not.toContain('record_id');
  });
});

function diagnosticsPayload(
  grade: AllowanceEvidenceGrade,
  candidate: AllowanceChangeCandidate | null,
  kind: AllowanceWindowKind,
  ready = false,
): AllowanceDiagnosticsPayload {
  const spans = kind === 'weekly' ? [span('2026-06-01T01:00:00Z', 100, 'rec-2'), span('2026-06-08T01:00:00Z', 50, 'rec-3')] : [];
  return {
    schema: 'codex-usage-tracker-allowance-diagnostics-v1',
    generated_at: '2026-07-10T12:00:00Z',
    privacy_mode: 'normal',
    include_archived: false,
    window_kind: null,
    summary: {
      observation_count: 3,
      window_report_count: 1,
      positive_span_count: spans.length,
      candidate_change_count: candidate ? 1 : 0,
      primary_window_kind: kind,
      primary_evidence_grade: grade,
      weekly_observation_count: kind === 'weekly' ? 3 : 0,
      five_hour_observation_count: kind === 'five_hour' ? 3 : 0,
      research_readiness: {
        detector_version: 'nonparametric-v1',
        ready_for_public_claim: ready,
        weekly_positive_span_count: spans.length,
        minimum_split_spans_for_public_claim: 6,
        p_value_threshold_for_public_claim: 0.05,
        best_candidate_capacity_ratio: candidate?.capacity_ratio ?? null,
        reasons: ready ? ['Local detector thresholds are met.'] : ['More weekly spans are required.'],
      },
    },
    windows: [{
      window_kind: kind,
      plan_type: 'pro',
      limit_id: 'codex',
      observation_count: 3,
      positive_span_count: spans.length,
      evidence_grade: grade,
      span_stats: { baseline_rows: 1, unchanged_rows: 0, reset_or_negative_delta_rows: 0, missing_used_percent_rows: 0 },
      change_candidates: candidate ? [candidate] : [],
      spans,
    }],
    spans,
    change_candidates: candidate ? [candidate] : [],
    notes: ['Local evidence only.'],
  };
}

function historyPayload(kind: AllowanceWindowKind): AllowanceHistoryPayload {
  const rows = [
    historyRow('2026-06-01T00:00:00Z', 10, 'rec-1', kind),
    historyRow('2026-06-01T01:00:00Z', 11, 'rec-2', kind),
    historyRow('2026-06-01T02:00:00Z', 12, 'rec-3', kind),
  ];
  return {
    schema: 'codex-usage-tracker-allowance-history-v1',
    generated_at: '2026-07-10T12:00:00Z',
    privacy_mode: 'normal',
    include_archived: false,
    window_kind: null,
    row_count: rows.length,
    rows,
    notes: [],
  };
}

function historyRow(
  observedAt: string,
  usedPercent: number,
  recordId: string,
  kind: AllowanceWindowKind = 'weekly',
) {
  return {
    observed_at: observedAt,
    observed_date: observedAt.slice(0, 10),
    source: 'token_count.rate_limits',
    window_key: kind === 'weekly' ? 'secondary' : 'primary',
    window_kind: kind,
    window_minutes: kind === 'weekly' ? 10080 : 300,
    used_percent: usedPercent,
    remaining_percent: 100 - usedPercent,
    resets_at: null,
    plan_type: 'pro',
    limit_id: 'codex',
    model: 'gpt-5.4',
    effort: 'high',
    total_tokens: 100,
    usage_credits: 50,
    usage_credit_confidence: 'exact',
    record_id: recordId,
    session_id: 'session-local',
    line_number: 1,
  };
}

function span(endObservedAt: string, creditsPerPercent: number, recordId: string): AllowanceSpan {
  return {
    window_kind: 'weekly',
    plan_type: 'pro',
    limit_id: 'codex',
    start_observed_at: '2026-06-01T00:00:00Z',
    end_observed_at: endObservedAt,
    start_used_percent: 10,
    end_used_percent: 11,
    delta_usage_percent: 1,
    estimated_usage_credits: creditsPerPercent,
    credits_per_percent: creditsPerPercent,
    row_count: 1,
    credit_confidence_mix: { exact: 1 },
    record_id: recordId,
  };
}

function changeCandidate(options: {
  ready: boolean;
  outsideUsage: boolean;
  grade: AllowanceEvidenceGrade;
}): AllowanceChangeCandidate {
  return {
    evidence_grade: options.grade,
    window_kind: 'weekly',
    candidate_start_observed_at: '2026-06-08T00:00:00Z',
    candidate_end_observed_at: '2026-06-30T00:00:00Z',
    split_index: 6,
    previous_span_count: 6,
    recent_span_count: options.ready ? 6 : 3,
    previous_median_credits_per_percent: 100,
    recent_median_credits_per_percent: 50,
    capacity_ratio: 0.5,
    observed_recent_delta_percent: 6,
    expected_recent_delta_percent_from_prior_baseline: 3,
    unexplained_usage_percent: options.outsideUsage ? 4 : 0.5,
    outside_usage_possible: options.outsideUsage,
    statistical_evidence: {
      detector_version: 'nonparametric-v1',
      method: 'exact_permutation_mean_shift',
      sample_size_before: 6,
      sample_size_after: options.ready ? 6 : 3,
      median_shift_credits_per_percent: -50,
      median_confidence_interval_before_95: interval(100, 6, true),
      median_confidence_interval_after_95: interval(50, options.ready ? 6 : 3, options.ready),
      effect_size_cliffs_delta: -1,
      p_value_one_sided: options.ready ? 0.01 : 0.15,
      combinations_evaluated: 924,
      effect_direction: 'recent_lower_credits_per_percent',
      signal: options.ready ? 'strong_nonparametric_shift' : 'directionally_consistent_small_sample',
      public_claim_ready: options.ready,
    },
  };
}

function interval(value: number, sampleSize: number, available: boolean) {
  return {
    method: 'exact_binomial_order_statistic' as const,
    confidence_level: 0.95,
    sample_size: sampleSize,
    available,
    low: available ? value : null,
    high: available ? value : null,
    achieved_coverage: available ? 0.96875 : 0.75,
  };
}
