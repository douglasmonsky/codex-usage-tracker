import { QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { createDashboardQueryClient } from '../../data/queryRuntime';
import {
  overviewRecommendationsQueryOptions,
  overviewSummaryQueryOptions,
} from '../../data/overviewQueries';
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

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage?.clear();
});

describe('Overview focused evidence flow', () => {
  it('reports module progress while recommendations are still loading', async () => {
    let resolveRecommendations: ((response: Response) => void) | undefined;
    const recommendations = new Promise<Response>((resolve) => {
      resolveRecommendations = resolve;
    });
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => (
      String(input).startsWith('/api/summary')
        ? Promise.resolve(summaryResponse())
        : recommendations
    )));

    renderOverview(createDashboardQueryClient());

    await waitFor(() => expect(screen.getByText('1 of 2 modules ready')).toBeInTheDocument());
    expect(screen.getByText('Usage summary ready')).toBeInTheDocument();
    expect(screen.getByText('Recommendations loading')).toBeInTheDocument();

    resolveRecommendations?.(recommendationsResponse());
    await waitFor(() => expect(screen.queryByRole('progressbar', { name: 'Loading overview evidence' })).not.toBeInTheDocument());
  });

  it('keeps completed module data when navigation cancels a slow peer', async () => {
    let recommendationCalls = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).startsWith('/api/summary')) return Promise.resolve(summaryResponse());
      recommendationCalls += 1;
      if (recommendationCalls > 1) return Promise.resolve(recommendationsResponse());
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
      });
    });
    vi.stubGlobal('fetch', fetchMock);
    const queryClient = createDashboardQueryClient();
    const firstView = renderOverview(queryClient);
    await waitFor(() => expect(screen.getByText('1 of 2 modules ready')).toBeInTheDocument());

    firstView.unmount();
    renderOverview(queryClient);

    await waitFor(() => expect(screen.getByText('Focused endpoints')).toBeInTheDocument());
    expect(fetchMock.mock.calls.filter(([url]) => String(url).startsWith('/api/summary'))).toHaveLength(1);
    expect(recommendationCalls).toBe(2);
  });

  it('reports cached modules as updating during a background refetch', async () => {
    let summaryCalls = 0;
    let resolveSummaryRefresh: ((response: Response) => void) | undefined;
    let markSummaryRefreshStarted: (() => void) | undefined;
    const summaryRefresh = new Promise<Response>((resolve) => {
      resolveSummaryRefresh = resolve;
    });
    const summaryRefreshStarted = new Promise<void>((resolve) => {
      markSummaryRefreshStarted = resolve;
    });
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      if (!String(input).startsWith('/api/summary')) {
        return Promise.resolve(recommendationsResponse());
      }
      summaryCalls += 1;
      if (summaryCalls === 1) return Promise.resolve(summaryResponse());
      markSummaryRefreshStarted?.();
      return summaryRefresh;
    }));
    const queryClient = createDashboardQueryClient();
    const endpointCache = {
      read: () => null,
      write: () => undefined,
    };
    const queryRequest = {
      runtime: { apiToken: 'local-token', contextApiEnabled: false, fileMode: false },
      includeArchived: true,
      sourceRevision: 'progress-revision',
      cache: endpointCache,
    };
    const summaryOptions = overviewSummaryQueryOptions(queryRequest);
    await Promise.all([
      queryClient.prefetchQuery(summaryOptions),
      queryClient.prefetchQuery(overviewRecommendationsQueryOptions(queryRequest)),
    ]);
    renderOverview(queryClient);
    expect(screen.getByText('Focused endpoints')).toBeInTheDocument();

    let refresh: Promise<unknown> = Promise.resolve();
    await act(async () => {
      refresh = queryClient.fetchQuery({ ...summaryOptions, staleTime: 0 });
      await summaryRefreshStarted;
    });
    expect(queryClient.isFetching({ queryKey: ['dashboard', 'overview-summary'] })).toBe(1);
    await waitFor(() => expect(screen.getByText('Usage summary updating')).toBeInTheDocument());

    await act(async () => {
      resolveSummaryRefresh?.(summaryResponse());
      await refresh;
    });
  });

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
    expect(screen.getByText('Estimated Cost')).toBeInTheDocument();
    expect(screen.getByText('$890.00')).toBeInTheDocument();
    expect(screen.getByText('Estimated credits')).toBeInTheDocument();
    expect(screen.getByText('456.7')).toBeInTheDocument();
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

function renderOverview(queryClient: ReturnType<typeof createDashboardQueryClient>) {
  return render(
    <QueryClientProvider client={queryClient}>
      <OverviewPage
        model={fixtureModel}
        contextRuntime={{ apiToken: 'local-token', contextApiEnabled: false, fileMode: false }}
        sourceRevision="progress-revision"
        onRefresh={vi.fn()}
        globalQuery=""
        runtime={{
          historyScope: 'all',
          loadLimit: 0,
          loadWindow: 'all',
          loadedRowCount: 500,
          scopeSince: null,
          totalAvailableRows: 404_176,
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
}

function summaryResponse() {
  return new Response(JSON.stringify({
    schema: 'codex-usage-tracker-summary-v1',
    group_by: 'date',
    include_archived: true,
    privacy_mode: 'normal',
    rows: [],
  }), { status: 200 });
}

function recommendationsResponse() {
  return new Response(JSON.stringify({
    schema: 'codex-usage-tracker-recommendations-v1',
    filters: { include_archived: true },
    row_count: 0,
    total_matched_rows: 0,
    truncated: false,
    rows: [],
  }), { status: 200 });
}
