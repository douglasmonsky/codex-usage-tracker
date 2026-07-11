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
  it('uses allowance endpoints, opens linked calls, and exports the strict bundle', async () => {
    const openCall = vi.fn();
    const copyCall = vi.fn();
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.startsWith('/api/allowance/history')) return jsonResponse(historyPayload());
      if (path.startsWith('/api/allowance/diagnostics')) return jsonResponse(diagnosticsPayload());
      if (path.startsWith('/api/allowance/export')) return jsonResponse(exportPayload());
      return jsonResponse({ error: 'unknown path' }, 404);
    }));
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

    await waitFor(() => expect(screen.getByText('Live detector payload')).toBeInTheDocument());
    expect(screen.getByRole('heading', { name: 'No weekly regime change detected' })).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Allowance evidence windows and linked calls' })).toBeInTheDocument();

    fireEvent.click(screen.getAllByTitle('Open call')[0]);
    expect(openCall).toHaveBeenCalledWith('rec-3');
    fireEvent.click(screen.getAllByTitle('Copy call link')[0]);
    expect(copyCall).toHaveBeenCalledWith('rec-3');

    fireEvent.click(screen.getByRole('button', { name: 'Refresh evidence' }));
    await waitFor(() => expect(screen.getByText('Allowance evidence refreshed')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Export evidence' }));
    await waitFor(() => expect(anchorClick).toHaveBeenCalledTimes(1));
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/allowance/export?'),
      expect.objectContaining({ cache: 'no-store' }),
    );
  });
});

function historyPayload() {
  return {
    schema: 'codex-usage-tracker-allowance-history-v1',
    generated_at: '2026-07-10T12:00:00Z',
    privacy_mode: 'normal',
    include_archived: false,
    window_kind: null,
    row_count: 3,
    rows: [
      historyRow('2026-06-01T00:00:00Z', 10, 'rec-1'),
      historyRow('2026-06-08T00:00:00Z', 11, 'rec-2'),
      historyRow('2026-06-15T00:00:00Z', 12, 'rec-3'),
    ],
    notes: ['Local observations only.'],
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

function historyRow(observedAt: string, usedPercent: number, recordId: string) {
  return {
    observed_at: observedAt,
    observed_date: observedAt.slice(0, 10),
    source: 'token_count.rate_limits',
    window_key: 'secondary',
    window_kind: 'weekly',
    window_minutes: 10080,
    used_percent: usedPercent,
    remaining_percent: 100 - usedPercent,
    resets_at: null,
    plan_type: 'pro',
    limit_id: 'codex',
    model: 'gpt-5.4',
    effort: 'high',
    total_tokens: 100,
    usage_credits: 100,
    usage_credit_confidence: 'exact',
    record_id: recordId,
    session_id: 'local-session',
    line_number: 1,
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
