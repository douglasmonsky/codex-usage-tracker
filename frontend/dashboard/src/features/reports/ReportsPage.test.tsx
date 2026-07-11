import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { DashboardModel } from '../../api/types';
import { createDashboardQueryClient } from '../../data/queryRuntime';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import { ReportsPage } from './ReportsPage';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, '', '/');
});

describe('Reports selected-report workspace', () => {
  it('keeps the selected report first and links its single evidence table to the investigator', () => {
    const openCall = vi.fn();
    const copyCall = vi.fn();
    window.history.replaceState(null, '', '/?view=reports&report=cost-curves');

    renderReports({
      model: { ...fixtureModel, contextRuntime: { ...fixtureModel.contextRuntime, apiToken: '', fileMode: true } },
      onOpenInvestigator: openCall,
      onCopyCallLink: copyCall,
    });

    expect(screen.getByRole('heading', { name: 'Cost Curves' })).toBeInTheDocument();
    expect(screen.getByText('Loaded dashboard aggregates')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Live refresh unavailable' })).toBeDisabled();
    expect(screen.getByRole('table', { name: 'Selected report evidence calls' })).toBeInTheDocument();
    expect(screen.getAllByRole('table')).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: 'Fast Mode Proxy' }));
    expect(screen.getByRole('heading', { name: 'Fast Mode Proxy' })).toBeInTheDocument();
    expect(window.location.search).toContain('report=fast-mode-proxy');

    fireEvent.click(screen.getAllByRole('button', { name: /Open investigator for report side evidence call/i })[0]);
    expect(openCall).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getAllByRole('button', { name: /Copy link for report side evidence call/i })[0]);
    expect(copyCall).toHaveBeenCalledTimes(1);
  });

  it('loads live report metadata and reports an honest cached state after a refresh error', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(livePayload()))
      .mockResolvedValueOnce(jsonResponse({ error: 'report service unavailable' }, 503));
    vi.stubGlobal('fetch', fetchMock);

    renderReports({
      model: { ...fixtureModel, contextRuntime: { ...fixtureModel.contextRuntime, apiToken: 'local-token', fileMode: false } },
    });

    expect(screen.getByRole('progressbar', { name: 'Loading full-scope report pack' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Server Cost Review' })).toBeInTheDocument());
    expect(screen.queryByRole('progressbar', { name: 'Loading full-scope report pack' })).not.toBeInTheDocument();
    expect(screen.getByText('Live localhost report pack')).toBeInTheDocument();
    expect(screen.getByText('2026-07-11T10:00:00Z')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/reports\/pack\?.*limit=0/),
      expect.objectContaining({ headers: expect.objectContaining({ 'X-Codex-Usage-Token': 'local-token' }) }),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Refresh report' }));
    await waitFor(() => expect(screen.getByText(/Refresh failed: report service unavailable/)).toBeInTheDocument());
    expect(screen.getByText('Live localhost report pack')).toBeInTheDocument();
  });

  it('keeps an incomplete-evidence warning visible when the initial report query fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ error: 'report service unavailable' }, 503)));

    renderReports({
      model: { ...fixtureModel, contextRuntime: { ...fixtureModel.contextRuntime, apiToken: 'local-token', fileMode: false } },
    });

    expect(await screen.findByRole('alert')).toHaveTextContent('Incomplete page evidence: report service unavailable');
  });
});

function renderReports(overrides: {
  model?: DashboardModel;
  onOpenInvestigator?: (recordId: string) => void;
  onCopyCallLink?: (recordId: string) => void;
} = {}) {
  render(
    <QueryClientProvider client={createDashboardQueryClient()}>
      <ReportsPage
        model={overrides.model ?? fixtureModel}
        refreshState="Loaded snapshot ready"
        includeArchived={false}
        loadWindow="all"
        loadLimit={500}
        onOpenInvestigator={overrides.onOpenInvestigator ?? vi.fn()}
        onCopyCallLink={overrides.onCopyCallLink ?? vi.fn()}
      />
    </QueryClientProvider>,
  );
}

function livePayload() {
  return {
    schema: 'codex-usage-tracker-reports-pack-v1',
    generated_at: '2026-07-11T10:00:00Z',
    row_count: 1,
    total_matched_rows: 12,
    raw_context_included: false,
    reports: [{
      key: 'server-cost-review',
      title: 'Server Cost Review',
      status: 'Ready',
      owner: 'Reports',
      description: 'Server-generated cost evidence.',
    }],
    evidence: {
      'server-cost-review': {
        rows: [{
          record_id: 'server-row',
          call_started_at: '2026-07-11T09:00:00Z',
          thread_name: 'server-thread',
          model: 'o5',
          effort: 'high',
          input_tokens: 200,
          cached_input_tokens: 20,
          output_tokens: 25,
          total_tokens: 225,
          estimated_cost_usd: 0.02,
          usage_credits: 7,
        }],
      },
    },
  };
}

function jsonResponse(payload: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => payload } as Response;
}
