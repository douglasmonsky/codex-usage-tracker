import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { createDashboardQueryClient } from '../../data/queryRuntime';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import { OverviewPage } from './OverviewPage';

vi.mock('../../visualization/renderer/echartsRenderer', () => ({
  createEChartsVisualizationRenderer: vi.fn(async () => ({
    dispose: vi.fn(),
    exportSvgDataUrl: vi.fn(() => ''),
    resize: vi.fn(),
    select: vi.fn(),
    setSpec: vi.fn(),
  })),
}));

afterEach(() => vi.unstubAllGlobals());

describe('Overview focused evidence flow', () => {
  it('renders endpoint-ranked evidence and opens its supporting call', async () => {
    const openCall = vi.fn();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const payload = String(input).startsWith('/api/summary')
        ? {
            schema: 'codex-usage-tracker-summary-v1',
            group_by: 'date',
            include_archived: false,
            privacy_mode: 'normal',
            rows: [{
              group_key: '2026-07-10',
              model_calls: 2,
              input_tokens: 1_200,
              cached_input_tokens: 500,
              output_tokens: 200,
              total_tokens: 1_400,
              latest_event: '2026-07-10T12:00:00Z',
            }],
          }
        : {
            schema: 'codex-usage-tracker-recommendations-v1',
            filters: { include_archived: false },
            row_count: 1,
            total_matched_rows: 1,
            truncated: false,
            rows: [{
              record_id: 'endpoint-call-1',
              event_timestamp: '2026-07-10T12:00:00Z',
              thread_name: 'Endpoint evidence thread',
              recommendation_score: 96,
              primary_recommendation: {
                key: 'context-bloat',
                severity: 'high',
                title: 'High context pressure',
                why: 'This call used a large share of its context window.',
                action: 'Start a fresh thread for unrelated work.',
              },
            }],
          };
      return new Response(JSON.stringify(payload), { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <QueryClientProvider client={createDashboardQueryClient()}>
        <OverviewPage
          model={fixtureModel}
          contextRuntime={{ apiToken: 'local-token', contextApiEnabled: false, fileMode: false }}
          sourceRevision="revision-1"
          onRefresh={vi.fn()}
          refreshState="Stored snapshot loaded"
          globalQuery=""
          runtime={{
            historyScope: 'active',
            loadLimit: 500,
            loadWindow: 'rows',
            loadedRowCount: 8,
            scopeSince: null,
            totalAvailableRows: 8,
          }}
          refreshing={false}
          canLoadMoreRows={false}
          onLoadMoreRows={vi.fn()}
          onOpenInvestigator={openCall}
          onCopyCallLink={vi.fn()}
          onOpenFinding={vi.fn()}
          onNavigateView={vi.fn()}
          focusedEndpointsEnabled
        />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByRole('heading', { name: 'High context pressure is the clearest current signal' })).toBeInTheDocument());
    expect(screen.getByText('Focused endpoints')).toBeInTheDocument();
    expect(screen.getByText('1 call')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Usage constellation' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Usage constellation evidence' })).toBeInTheDocument();
    expect(fetchMock.mock.calls.every(([url]) => String(url).includes('include_archived=false'))).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: 'Inspect evidence' }));
    expect(openCall).toHaveBeenCalledWith('endpoint-call-1');
  });
});
