import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { createDashboardQueryClient } from '../../data/queryRuntime';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import { LimitsPage } from './LimitsPage';

vi.mock('../../visualization/renderer/echartsRenderer', () => ({
  createEChartsVisualizationRenderer: vi.fn(async () => ({
    dispose: vi.fn(),
    exportSvgDataUrl: vi.fn(() => ''),
    resize: vi.fn(),
    select: vi.fn(),
    setSpec: vi.fn(),
  })),
}));

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('Limits live evidence flow', () => {
  it('uses revision-aware v2 allowance endpoints and keeps export as an explicit offline action', async () => {
    const openCall = vi.fn();
    const copyCall = vi.fn();
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.startsWith('/api/allowance/status')) return jsonResponse(statusPayload());
      if (path.startsWith('/api/allowance/series')) return jsonResponse(seriesPayload());
      if (path.startsWith('/api/allowance/evidence')) return jsonResponse(evidencePayload());
      if (path.startsWith('/api/allowance/analysis')) return jsonResponse(analysisPayload());
      if (path.startsWith('/api/allowance/export')) return jsonResponse(exportPayload());
      return jsonResponse({ error: 'unknown path' }, 404);
    });
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('URL', Object.assign(URL, {
      createObjectURL: vi.fn(() => 'blob:allowance-export'),
      revokeObjectURL: vi.fn(),
    }));

    render(
      <QueryClientProvider client={createDashboardQueryClient()}>
        <LimitsPage
          model={fixtureModel}
          contextRuntime={{ apiToken: 'local-token', contextApiEnabled: false, fileMode: false }}
          sourceRevision="revision-1"
          onOpenInvestigator={openCall}
          onCopyCallLink={copyCall}
        />
      </QueryClientProvider>,
    );

    expect(screen.getByRole('progressbar', { name: 'Loading allowance intelligence' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('Canonical usage')).toBeInTheDocument());
    await waitFor(() => expect(
      screen.queryByRole('progressbar', { name: 'Loading allowance intelligence' }),
    ).not.toBeInTheDocument());
    expect(screen.getByRole('heading', { name: '40%' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'No supported capacity shift' })).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Latest-first allowance intelligence evidence' })).toBeInTheDocument();

    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/api/allowance/history'))).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/api/allowance/diagnostics'))).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/api/allowance/series?range_preset=8w'))).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/api/allowance/evidence?limit=100'))).toBe(true);

    fireEvent.click(screen.getAllByTitle('Open source call')[0]);
    expect(openCall).toHaveBeenCalledWith('rec-new');
    fireEvent.click(screen.getAllByTitle('Copy source call link')[0]);
    expect(copyCall).toHaveBeenCalledWith('rec-new');

    fireEvent.click(screen.getByRole('button', { name: '6m' }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => (
      String(input).includes('/api/allowance/series?range_preset=6m')
    ))).toBe(true));
    fireEvent.change(screen.getByRole('combobox', { name: 'Granularity' }), { target: { value: 'day' } });
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => (
      String(input).includes('granularity=day')
    ))).toBe(true));

    const seriesCallsBeforeStatusCheck = fetchMock.mock.calls.filter(([input]) => String(input).startsWith('/api/allowance/series')).length;
    const evidenceCallsBeforeStatusCheck = fetchMock.mock.calls.filter(([input]) => String(input).startsWith('/api/allowance/evidence')).length;
    fireEvent.click(screen.getByRole('button', { name: 'Check for new data' }));
    await waitFor(() => expect(screen.getByText('Allowance status checked')).toBeInTheDocument());
    expect(fetchMock.mock.calls.filter(([input]) => String(input).startsWith('/api/allowance/series')).length).toBe(seriesCallsBeforeStatusCheck);
    expect(fetchMock.mock.calls.filter(([input]) => String(input).startsWith('/api/allowance/evidence')).length).toBe(evidenceCallsBeforeStatusCheck);

    fireEvent.click(screen.getByRole('button', { name: 'Export evidence' }));
    await waitFor(() => expect(anchorClick).toHaveBeenCalledTimes(1));
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/allowance/export?'),
      expect.objectContaining({ cache: 'no-store' }),
    );
  });

  it('reloads series and evidence only when the semantic revision changes', async () => {
    let statusCalls = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.startsWith('/api/allowance/status')) {
        statusCalls += 1;
        return jsonResponse(statusPayload(statusCalls === 1 ? 'allowance-revision-1' : 'allowance-revision-2'));
      }
      if (path.startsWith('/api/allowance/series')) return jsonResponse(seriesPayload());
      if (path.startsWith('/api/allowance/evidence')) return jsonResponse(evidencePayload());
      if (path.startsWith('/api/allowance/analysis')) return jsonResponse(analysisPayload());
      return jsonResponse({ error: 'unknown path' }, 404);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <QueryClientProvider client={createDashboardQueryClient()}>
        <LimitsPage
          model={fixtureModel}
          contextRuntime={{ apiToken: 'local-token', contextApiEnabled: false, fileMode: false }}
          onOpenInvestigator={vi.fn()}
          onCopyCallLink={vi.fn()}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(
      fetchMock.mock.calls.filter(([input]) => String(input).startsWith('/api/allowance/evidence')),
    ).toHaveLength(1));
    await waitFor(() => expect(
      screen.queryByRole('progressbar', { name: 'Loading allowance intelligence' }),
    ).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Check for new data' }));
    await waitFor(() => expect(
      fetchMock.mock.calls.filter(([input]) => String(input).startsWith('/api/allowance/evidence')),
    ).toHaveLength(2));
    expect(fetchMock.mock.calls.filter(([input]) => String(input).startsWith('/api/allowance/series'))).toHaveLength(2);
  });
});

function statusPayload(revision = 'allowance-revision-1') {
  return {
    schema: 'codex-usage-tracker-allowance-status-v2',
    revision,
    changed: true,
    data_state: 'fresh',
    data_as_of: '2026-07-15T10:00:00Z',
    weekly: {
      cohort_id: 'codex',
      used_percent: 40,
      remaining_percent: 60,
      reset_at: null,
      reset_countdown_seconds: null,
      observed_at: '2026-07-15T10:00:00Z',
      age_seconds: 7200,
      freshness: 'fresh',
      status: 'observed',
      pricing_coverage: 1,
      quality: 'good',
      canonical_source_revision: revision,
    },
    five_hour: null,
    quality: { canonical: true, copied_rows_excluded: 2 },
    next: { action: 'poll_status', poll_after_seconds: 30 },
  };
}

function seriesPayload() {
  return {
    schema: 'codex-usage-tracker-allowance-series-v2',
    model_version: 'allowance-v2',
    generated_at: '2026-07-10T12:00:00Z',
    revision: 'allowance-revision-1',
    requested_range: { preset: '8w', start_at: '2026-05-01T00:00:00Z', end_at: '2026-07-10T12:00:00Z' },
    available_range: { start_at: '2026-06-01T00:00:00Z', end_at: '2026-06-15T00:00:00Z' },
    granularity: 'week',
    truncated: false,
    downsampled: false,
    quality: { canonical: true, copied_rows_excluded: 2, observed_only: true },
    points: [],
    cycles: [],
  };
}

function evidencePayload() {
  return {
    schema: 'codex-usage-tracker-allowance-evidence-v2',
    model_version: 'allowance-v2',
    generated_at: '2026-07-10T12:00:00Z',
    revision: 'allowance-revision-1',
    privacy_mode: 'local',
    rows: [
      {
        interval_id: 'older', cycle_id: 'cycle-1', window_kind: 'weekly', cohort_key: 'codex',
        end_observed_at: '2026-07-01T00:00:00Z', end_used_percent: 20, point_kind: 'positive', censor_reason: null,
        end_record_id: 'rec-old',
      },
      {
        interval_id: 'newer', cycle_id: 'cycle-2', window_kind: 'weekly', cohort_key: 'codex',
        end_observed_at: '2026-07-15T00:00:00Z', end_used_percent: 40, point_kind: 'positive', censor_reason: null,
        end_record_id: 'rec-new',
      },
    ],
    next_cursor: null,
    copied_rows_excluded: 2,
    provenance: 'local',
    offline_export_action: 'build_allowance_export_report',
  };
}

function analysisPayload() {
  return {
    schema: 'codex-usage-tracker-allowance-analysis-v2',
    status: 'no_supported_change',
    snapshot_id: 'snapshot-1',
    source_revision: 'allowance-revision-1',
    model_version: 'allowance-v2',
    rate_card_revision: 'rates-1',
    parameters: { min_cycles_per_side: 3, permutation_count: 2000 },
  };
}

function diagnosticsPayload() {
  const spans = [span('2026-06-08T00:00:00Z', 100, 'rec-2'), span('2026-06-15T00:00:00Z', 102, 'rec-3')];
  return {
    schema: 'codex-usage-tracker-allowance-diagnostics-v1',
    generated_at: '2026-07-10T12:00:00Z',
    privacy_mode: 'normal',
    include_archived: false,
    window_kind: null,
    summary: {
      observation_count: 3,
      window_report_count: 1,
      positive_span_count: 2,
      candidate_change_count: 0,
      primary_window_kind: 'weekly',
      primary_evidence_grade: 'no_change_detected',
      weekly_observation_count: 3,
      five_hour_observation_count: 0,
      research_readiness: {
        detector_version: 'nonparametric-v1',
        ready_for_public_claim: false,
        weekly_positive_span_count: 2,
        minimum_split_spans_for_public_claim: 6,
        p_value_threshold_for_public_claim: 0.05,
        best_candidate_capacity_ratio: null,
        reasons: ['No candidate split cleared the detector threshold.'],
      },
    },
    windows: [{
      window_kind: 'weekly',
      plan_type: 'pro',
      limit_id: 'codex',
      observation_count: 3,
      positive_span_count: 2,
      evidence_grade: 'no_change_detected',
      span_stats: { baseline_rows: 1, unchanged_rows: 0, reset_or_negative_delta_rows: 0, missing_used_percent_rows: 0 },
      change_candidates: [],
      spans,
    }],
    spans,
    change_candidates: [],
    notes: ['Weekly windows are the primary signal.'],
  };
}

function exportPayload() {
  return {
    schema: 'codex-usage-tracker-allowance-evidence-export-v1',
    generated_at: '2026-07-10T12:00:00Z',
    privacy_mode: 'strict',
    include_archived: false,
    summary: diagnosticsPayload().summary,
    windows: [],
    change_candidates: [],
    notes: ['Identifiers omitted.'],
  };
}

function span(endObservedAt: string, creditsPerPercent: number, recordId: string) {
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

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } });
}
