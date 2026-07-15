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
    let statusCalls = 0;
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.startsWith('/api/allowance/status')) {
        statusCalls += 1;
        return jsonResponse(statusCalls === 1 ? statusPayload() : unchangedStatusPayload());
      }
      if (path.startsWith('/api/allowance/series')) {
        const preset = new URL(path, 'http://localhost').searchParams.get('range_preset') ?? '8w';
        return jsonResponse(seriesPayload(preset));
      }
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
    expect(screen.getByRole('group', { name: 'Current limit status' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Weekly limit capacity over time' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'How to read and trust this chart' })).toBeInTheDocument();
    expect(screen.getByText(/Locally priced credits ÷ visible percentage-point movement/)).toBeInTheDocument();
    expect(screen.getByText(/Copied clone rows are excluded/)).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Capacity chart legend' })).toBeVisible();
    expect(screen.getByRole('list', { name: 'Subscription plan key' })).toHaveTextContent('Pro');
    expect(screen.getByRole('list', { name: 'Chart mark key' })).toHaveTextContent('Observed reset window');
    expect(screen.getByRole('list', { name: 'Chart mark key' })).toHaveTextContent('Trailing 8-window median');
    expect(screen.getByText(/Pro · Fresh · observed/)).toBeInTheDocument();
    expect(screen.getByText('63 eligible')).toBeInTheDocument();
    expect(screen.getByText('12 excluded')).toBeInTheDocument();
    expect(screen.getByText('6 candidates tested')).toBeInTheDocument();
    expect(screen.getByText('0 supported changes')).toBeInTheDocument();
    expect(screen.getByText(/4 reset windows on each side/)).toBeInTheDocument();
    expect(screen.getByText(/1,999 cycle-block permutations/)).toBeInTheDocument();
    expect(screen.getByText(/5% family-wise false-positive limit/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'No reliable capacity change detected' })).toBeInTheDocument();
    expect(screen.getByText('No supported change')).toBeInTheDocument();
    expect(screen.queryByText('Usage percentage over time')).not.toBeInTheDocument();
    expect(screen.queryByText('Personal model')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /analysis|revision/i })).not.toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Latest-first allowance intelligence evidence' })).toBeInTheDocument();
    expect(screen.getByText('Overview')).toHaveAttribute('data-localization-skip', 'true');

    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/api/allowance/history'))).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/api/allowance/diagnostics'))).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/api/allowance/series?range_preset=8w'))).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('granularity=cycle'))).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/api/allowance/evidence?limit=50'))).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('privacy_mode=normal'))).toBe(true);

    expect(screen.queryByTitle('Open source call')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Show physical source links' }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => String(input).includes('privacy_mode=local'))).toBe(true));
    fireEvent.click((await screen.findAllByTitle('Open source call'))[0]);
    expect(openCall).toHaveBeenCalledWith('rec-new');
    fireEvent.click(screen.getAllByTitle('Copy source call link')[0]);
    expect(copyCall).toHaveBeenCalledWith('rec-new');

    fireEvent.click(screen.getByRole('button', { name: '6m' }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => (
      String(input).includes('/api/allowance/series?range_preset=6m')
    ))).toBe(true));
    const rangeResult = await screen.findByRole('status', { name: 'History range result' });
    expect(rangeResult).toHaveTextContent('6m selected');
    expect(rangeResult).toHaveTextContent('No older capacity history is available');
    fireEvent.change(screen.getByRole('combobox', { name: 'Granularity' }), { target: { value: 'week' } });
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => (
      String(input).includes('granularity=week')
    ))).toBe(true));

    const seriesCallsBeforeStatusCheck = fetchMock.mock.calls.filter(([input]) => String(input).startsWith('/api/allowance/series')).length;
    const evidenceCallsBeforeStatusCheck = fetchMock.mock.calls.filter(([input]) => String(input).startsWith('/api/allowance/evidence')).length;
    const refreshButton = await screen.findByRole('button', { name: 'Check for new data' });
    fireEvent.click(refreshButton);
    await waitFor(() => expect(screen.getByText('Allowance status checked')).toBeInTheDocument());
    expect(fetchMock.mock.calls.filter(([input]) => String(input).startsWith('/api/allowance/status'))[1][0]).toEqual(
      expect.stringContaining('since_revision=allowance-revision-1'),
    );
    expect(screen.getAllByText('40%').length).toBeGreaterThan(0);
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

  it('automatically starts missing analysis for the current revision without exposing a run button', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.startsWith('/api/allowance/status')) return jsonResponse(statusPayload());
      if (path.startsWith('/api/allowance/series')) return jsonResponse(seriesPayload());
      if (path.startsWith('/api/allowance/evidence')) return jsonResponse(evidencePayload());
      if (path.startsWith('/api/allowance/analysis/jobs?') && init?.method === 'POST') {
        return jsonResponse({ schema: 'codex-usage-tracker-analysis-job-v1', job_id: 'job-1', status: 'pending' });
      }
      if (path.startsWith('/api/allowance/analysis/jobs/job-1')) {
        return jsonResponse({ schema: 'codex-usage-tracker-analysis-job-v1', job_id: 'job-1', status: 'running' });
      }
      if (path.startsWith('/api/allowance/analysis')) return jsonResponse({ ...analysisPayload(), status: 'missing' });
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

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/allowance/analysis/jobs?window_kind=weekly'),
      expect.objectContaining({ method: 'POST' }),
    ));
    expect(screen.queryByRole('button', { name: /analysis|revision/i })).not.toBeInTheDocument();
  });

  it('lists every supported capacity change newest first', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.startsWith('/api/allowance/status')) return jsonResponse(statusPayload());
      if (path.startsWith('/api/allowance/series')) return jsonResponse(seriesPayload());
      if (path.startsWith('/api/allowance/evidence')) return jsonResponse(evidencePayload());
      if (path.startsWith('/api/allowance/analysis')) return jsonResponse(multipleChangesPayload());
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

    const changes = await screen.findAllByRole('listitem', { name: /Credits per 1%/ });
    expect(changes).toHaveLength(2);
    expect(changes[0]).toHaveTextContent('Jul 1');
    expect(changes[1]).toHaveTextContent('Jun 1');
    expect(screen.queryByText('Adjusted p-value')).not.toBeInTheDocument();
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
      plan_type: 'pro',
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
    estimation: {
      capacity: {
        status: 'descriptive', credits_per_percent: 105.11, completed_cycle_count: 63, price_coverage: 1,
      },
    },
    next: { action: 'poll_status', poll_after_seconds: 30 },
  };
}

function unchangedStatusPayload() {
  return {
    schema: 'codex-usage-tracker-allowance-status-v2',
    revision: 'allowance-revision-1',
    changed: false,
    quality: { canonical: true, copied_rows_excluded: 2 },
    next: { action: 'poll_status', poll_after_seconds: 60 },
  };
}

function seriesPayload(preset = '8w') {
  return {
    schema: 'codex-usage-tracker-allowance-series-v2',
    model_version: 'allowance-v2',
    generated_at: '2026-07-10T12:00:00Z',
    revision: 'allowance-revision-1',
    requested_range: { preset, start_at: '2026-05-01T00:00:00Z', end_at: '2026-07-10T12:00:00Z' },
    available_range: { start_at: '2026-06-01T00:00:00Z', end_at: '2026-06-15T00:00:00Z' },
    granularity: 'cycle',
    truncated: false,
    downsampled: false,
    quality: { canonical: true, copied_rows_excluded: 2, observed_only: true },
    points: [],
    cycles: [],
    capacity_history: {
      status: 'ready', unit: 'credits_per_percent', eligible_cycle_count: 63,
      robust_domain: { mode: 'tukey_1_5_iqr', min: 50, max: 180 }, clipped_point_count: 0,
      points: [{
        cycle_id: 'cycle-2', completed_at: '2026-07-01T00:00:00Z', credits_per_percent: 105.11,
        rolling_median: 105.11, rolling_q1: 95, rolling_q3: 115, quality_grade: 'high',
        price_coverage: 1, regime_id: 'regime-1',
        plan_type: 'pro',
      }],
      boundaries: [], regimes: [],
    },
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
        interval_id: 'newer', cycle_id: 'cycle-2', window_kind: 'weekly', cohort_key: 'Overview',
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
    generated_at: '2026-07-15T12:00:00Z',
    eligible_cycle_count: 63,
    excluded_cycle_count: 12,
    candidate_count: 6,
    parameters: { min_cycles_per_regime: 4, permutation_count: 1999, familywise_alpha: 0.05 },
  };
}

function multipleChangesPayload() {
  const boundary = (id: string, effectiveAt: string, before: number, after: number) => ({
    boundary_id: id,
    split_index: 10,
    before_cycle_id: `${id}-before`,
    after_cycle_id: `${id}-after`,
    effective_at: effectiveAt,
    alpha: 0.025,
    adjusted_p_value: 0.01,
    effect_size: {
      median_before_credits_per_percent: before,
      median_after_credits_per_percent: after,
      median_shift_credits_per_percent: after - before,
      cliffs_delta: -0.8,
    },
  });
  return {
    ...analysisPayload(),
    status: 'supported_changes',
    boundaries: [
      boundary('older', '2026-06-01T00:00:00Z', 140, 100),
      boundary('newer', '2026-07-01T00:00:00Z', 100, 70),
    ],
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
