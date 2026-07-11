import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
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
  it('keeps endpoint-backed summaries without duplicating investigation surfaces', async () => {
    const model = {
      ...fixtureModel,
      scopeSummary: {
        visibleCalls: 1_250,
        inputTokens: 1_000_000,
        cachedInputTokens: 800_000,
        uncachedInputTokens: 200_000,
        outputTokens: 100_000,
        reasoningOutputTokens: 50_000,
        totalTokens: 1_100_000,
        estimatedCostUsd: 890,
        usageCredits: 456.7,
      },
    };
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
          model={model}
          contextRuntime={{ apiToken: 'local-token', contextApiEnabled: false, fileMode: false }}
          sourceRevision="revision-1"
          onRefresh={vi.fn()}
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
          onOpenInvestigator={vi.fn()}
          onCopyCallLink={vi.fn()}
          onNavigateView={vi.fn()}
          focusedEndpointsEnabled
        />
      </QueryClientProvider>,
    );

    expect(screen.getByRole('progressbar', { name: 'Loading overview evidence' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('Focused endpoints')).toBeInTheDocument());
    expect(screen.queryByRole('progressbar', { name: 'Loading overview evidence' })).not.toBeInTheDocument();
    expect(screen.getByText('Total Calls')).toBeInTheDocument();
    expect(screen.getByText('1,250')).toBeInTheDocument();
    expect(screen.getByText('8 detailed rows available')).toBeInTheDocument();
    expect(screen.queryByText('Highest-priority answer')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Needs attention' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Usage constellation' })).not.toBeInTheDocument();
    const callsTable = screen.getByRole('table', { name: 'Overview calls' });
    expect(within(callsTable).getByRole('button', { name: 'Sort by Input Tokens' })).toBeInTheDocument();
    expect(within(callsTable).getByRole('button', { name: 'Sort by Total Tokens' })).toBeInTheDocument();
    expect(within(callsTable).getByRole('button', { name: 'Sort by Codex Credits' })).toBeInTheDocument();
    expect(fetchMock.mock.calls.every(([url]) => String(url).includes('include_archived=false'))).toBe(true);
  });
});
