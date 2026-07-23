import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, vi, waitFor, within } from './test-utils/appTestHarness';

function usageRequestCalls(fetchMock: ReturnType<typeof vi.fn>) {
  return fetchMock.mock.calls.filter(([input]) => String(input).includes('/api/usage?'));
}

describe('React dashboard shell live loading', () => {
  installAppTestHooks();

it('keeps stable Home shell boot bounded instead of hydrating compatibility rows', async () => {
  window.history.replaceState(null, '', '/?view=home');
  const embedded = document.createElement('script');
  embedded.id = 'usage-data';
  embedded.type = 'application/json';
  embedded.textContent = JSON.stringify({
    api_token: 'shell-load-token',
    context_api_enabled: true,
    shell_boot: true,
    readiness_deferred: true,
    loaded_row_count: 0,
    default_load_window: 'all',
    load_window: 'rows',
    limit: 500,
    history_scope: 'active',
    rows: [],
    summary: {
      visible_calls: 2,
      input_tokens: 1_000,
      cached_input_tokens: 400,
      total_tokens: 1_250,
      estimated_cost_usd: 0.12,
    },
  });
  document.body.append(embedded);
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === '/api/v2/query') {
      const request = JSON.parse(String(init?.body)) as {
        filters?: { since?: string };
        history?: string;
      };
      expect(request.filters?.since).toMatch(/^2026-|^2027-/);
      expect(['active', 'all']).toContain(request.history);
      return {
        ok: true,
        json: async () => ({
          schema: 'codex-usage-tracker.query.v2',
          rows: [{
            model: 'gpt-5.6',
            tokens: 900,
            cached_tokens: 600,
            uncached_tokens: 200,
            output_tokens: 100,
            reasoning_tokens: 50,
            estimated_cost: 0.25,
            estimated_cost_coverage: 1,
            estimated_credits: 9,
            call_count: 3,
          }],
          next_cursor: null,
          total_matched: 1,
        }),
      } as Response;
    }
    if (url.includes('/api/status?')) {
      return {
        ok: true,
        json: async () => ({
          schema: 'codex-usage-tracker-status-v1',
          conversational_analysis: {
            schema: 'codex-usage-tracker-conversational-readiness-v1',
            state: 'ready',
            summary: 'Deferred MCP readiness passed.',
            next_action: null,
            evidence: ['MCP runtime: pass'],
          },
          home_summary: {
            schema: 'codex-usage-tracker-home-summary-v1',
            source_revision: 'shell-live-test',
            latest_refresh_at: null,
            latest_event_at: null,
            accounting: { physical_rows: 1, canonical_rows: 1, excluded_copied_rows: 0 },
            pricing: { configured: false, model_count: 0, estimated_model_count: 0 },
            allowance: {
              configured: false,
              error: null,
              observed_usage: { available: false, windows: [] },
              windows: [],
            },
            findings: [],
            recent_evidence: [],
          },
        }),
      } as Response;
    }
    throw new Error(`Unexpected request: ${url}`);
  });
  vi.stubGlobal('fetch', fetchMock);

  render(<App />);

  expect(screen.queryByText('thread-9f3a1c')).not.toBeInTheDocument();
  expect(await screen.findByRole('heading', { name: 'Overview' })).toBeInTheDocument();
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  expect(usageRequestCalls(fetchMock)).toHaveLength(0);
  expect(screen.getByText('Total Calls')).toBeInTheDocument();
  expect(screen.getAllByText('2').length).toBeGreaterThan(0);
  expect(screen.getByRole('button', { name: 'All time' })).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(screen.getByRole('button', { name: 'Last 24h' }));
  expect(await screen.findByText('900')).toBeInTheDocument();
  expect(screen.getByText('3')).toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([input]) => String(input) === '/api/v2/query')).toBe(true);
  expect(usageRequestCalls(fetchMock)).toHaveLength(0);
  fireEvent.change(screen.getByLabelText('History scope'), { target: { value: 'all' } });
  await waitFor(() => {
    const v2Calls = fetchMock.mock.calls.filter(([input]) => String(input) === '/api/v2/query');
    expect(v2Calls).toHaveLength(2);
    expect(JSON.parse(String(v2Calls[1]?.[1]?.body)).history).toBe('all');
  });
  expect(usageRequestCalls(fetchMock)).toHaveLength(0);
  fireEvent.click(screen.getByRole('button', { name: 'Settings' }));
  expect(await screen.findByText('Deferred MCP readiness passed.')).toBeInTheDocument();
  embedded.remove();
});

  it('restores saved Home scope controls without compatibility hydration', async () => {
    window.history.replaceState(null, '', '/?view=home');
    window.sessionStorage.setItem(
      'codexUsageDashboardLoadSettings',
      JSON.stringify({ loadLimit: 1_500, historyScope: 'all', loadWindow: 'rows' }),
    );
    window.__CODEX_USAGE_BOOT__ = {
      api_token: 'home-session-token',
      shell_boot: true,
      loaded_row_count: 0,
      total_available_rows: 0,
      load_window: 'all',
      default_load_window: 'all',
      limit: 500,
      history_scope: 'active',
      rows: [],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/v2/query') {
        return {
          ok: true,
          json: async () => ({
            schema: 'codex-usage-tracker.query.v2',
            rows: [],
            next_cursor: null,
          }),
        } as Response;
      }
      if (url.includes('/api/status?')) {
        return {
          ok: true,
          json: async () => ({
            schema: 'codex-usage-tracker-status-v1',
            conversational_analysis: {
              schema: 'codex-usage-tracker-conversational-readiness-v1',
              state: 'ready',
              summary: 'Ready.',
              next_action: null,
              configured_profile: 'core',
              runtime_version_matches: true,
              evidence: [],
            },
            home_summary: {
              schema: 'codex-usage-tracker-home-summary-v1',
              source_revision: 'session-restore',
              accounting: {
                physical_rows: 0,
                canonical_rows: 0,
                excluded_copied_rows: 0,
              },
              usage_metrics: null,
              pricing: { configured: false, model_count: 0, estimated_model_count: 0 },
              allowance: {
                configured: false,
                error: null,
                observed_usage: { available: false, windows: [] },
                windows: [],
              },
              findings: [],
              recent_evidence: [],
            },
          }),
        } as Response;
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);

    expect(await screen.findByRole('button', { name: 'Recent rows' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByLabelText('History scope')).toHaveValue('all');
    expect(screen.getByLabelText('Rows to load')).toHaveValue(1_500);
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input]) => String(input) === '/api/v2/query'),
      ).toBe(true);
    });
    expect(usageRequestCalls(fetchMock)).toHaveLength(0);
  });

  it('renders Reports live boot payloads without embedded report summaries', () => {
    window.history.replaceState(null, '', '/?view=reports&report=fast-mode-proxy');
    window.__CODEX_USAGE_BOOT__ = {
      loaded_row_count: 1,
      total_available_rows: 1,
      limit: 500,
      history_scope: 'active',
      rows: [
        {
          record_id: 'live-report-row',
          call_started_at: '2026-07-02T10:00:00Z',
          thread_name: 'live-report-thread',
          model: 'codex-1',
          effort: 'low',
          input_tokens: 1_000,
          cached_input_tokens: 400,
          output_tokens: 250,
          total_tokens: 1_250,
          estimated_cost_usd: 0.12,
        },
      ],
    };

    render(<App />);

    expect(screen.getByRole('heading', { name: 'Reports' })).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Selected report evidence calls' })).toBeInTheDocument();
    expect(screen.getAllByText('live-report-thread').length).toBeGreaterThan(0);
  });

it('hydrates legacy history scope from the URL and exposes granular row controls', () => {
    window.__CODEX_USAGE_BOOT__ = {
    api_token: 'history-url-token',
    context_api_enabled: true,
    loaded_row_count: 1,
    total_available_rows: 61_378,
    all_history_available_rows: 61_378,
    active_available_rows: 12_000,
    archived_available_rows: 49_378,
    limit: 500,
    history_scope: 'active',
    include_archived: false,
 rows: [
 {
 record_id: 'history-url-row',
 call_started_at: '2026-07-02T10:00:00Z',
 thread_name: 'history-url-thread',
 model: 'codex-1',
 effort: 'high',
 input_tokens: 100,
 cached_input_tokens: 40,
 output_tokens: 20,
 total_tokens: 120,
 estimated_cost_usd: 0.01,
 },
 ],
 };
    window.history.replaceState(null, '', '/?history=all');

    render(<App />);

  expect(screen.getByLabelText('History scope')).toHaveValue('all');
  expect(screen.getByRole('button', { name: 'Recent rows' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByText('All history includes 49,378 archived calls')).toBeInTheDocument();
  expect(screen.getByLabelText('Rows to load')).toHaveValue(500);
  const rowLimitSlider = screen.getByLabelText('Rows to load slider');
  expect(rowLimitSlider).toHaveAttribute('max', '1600');
  expect(rowLimitSlider).toHaveAttribute(
    'aria-valuetext',
    '500 recent rows',
  );
  expect(screen.getByLabelText('Rows to load')).not.toHaveAttribute('max');
  expect(screen.getByRole('button', { name: 'Last 24h' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Last 7 days' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Recent rows' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('button', { name: 'All time' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Rows to load'), { target: { value: '250000' } });
  expect(rowLimitSlider).toHaveAttribute('max', '251100');
    expect((rowLimitSlider as HTMLInputElement).value).toBe('250000');
    expect(rowLimitSlider).toHaveAttribute(
      'aria-valuetext',
      '250,000 recent rows',
    );
  });

it('virtualizes large tables while preserving page URL state', () => {
  window.__CODEX_USAGE_BOOT__ = {
    api_token: 'large-table-token',
    context_api_enabled: true,
    loaded_row_count: 520,
    total_available_rows: 520,
    limit: 520,
    rows: Array.from({ length: 520 }, (_, index) => ({
      record_id: `large-table-row-${index}`,
      call_started_at: new Date(Date.UTC(2026, 6, 1, 0, index)).toISOString(),
      thread_name: `large-table-thread-${String(index).padStart(3, '0')}`,
      model: index % 2 ? 'o5' : 'o4-mini',
      effort: index % 3 === 0 ? 'high' : 'medium',
      input_tokens: 1_000 + index,
      cached_input_tokens: 500,
      output_tokens: 100,
      total_tokens: 1_100 + index,
      estimated_cost_usd: 0.01,
    })),
  };
  window.history.replaceState(null, '', '/?view=calls&page=2');

  render(<App />);

  const table = screen.getByRole('table', { name: 'Model calls' });
  expect(table).toHaveAttribute('aria-rowcount', '521');
  expect(within(table).getAllByRole('row').length).toBeLessThan(40);
  expect(table.parentElement).toHaveAttribute('data-virtualized', 'true');
  expect(screen.getByText('520 loaded / 520 matched')).toBeInTheDocument();
  expect(new URLSearchParams(window.location.search).get('page')).toBe('2');
});

it('restores session row loading preferences on browser refresh', async () => {
  window.history.replaceState(null, '', '/?view=explore&mode=calls');
  window.sessionStorage.setItem(
    'codexUsageDashboardLoadSettings',
    JSON.stringify({ loadLimit: 1500, historyScope: 'all' }),
  );
  window.__CODEX_USAGE_BOOT__ = {
    api_token: 'session-restore-token',
    context_api_enabled: true,
    loaded_row_count: 500,
    total_available_rows: 2_000,
    all_history_available_rows: 2_000,
    active_available_rows: 500,
    limit: 500,
    history_scope: 'active',
    include_archived: false,
    rows: [
      {
        record_id: 'session-before',
        call_started_at: '2026-07-01T10:00:00Z',
        thread_name: 'session-before-thread',
        model: 'o4-mini',
        effort: 'medium',
        input_tokens: 100,
        cached_input_tokens: 50,
        output_tokens: 10,
        total_tokens: 110,
        estimated_cost_usd: 0.01,
      },
    ],
  };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    void init;
    const url = String(input);
    if (!url.includes('/api/usage?')) throw new Error(`Unexpected request: ${url}`);
    return {
      ok: true,
      json: async () => ({
        api_token: 'session-restore-token',
        context_api_enabled: true,
        loaded_row_count: 1_500,
        total_available_rows: 2_000,
        all_history_available_rows: 2_000,
        active_available_rows: 500,
        limit: 1_500,
        history_scope: 'all',
        include_archived: true,
        rows: [
          {
            record_id: 'session-after',
            call_started_at: '2026-07-01T11:00:00Z',
            thread_name: 'session-after-thread',
            model: 'o5',
            effort: 'high',
            input_tokens: 200,
            cached_input_tokens: 20,
            output_tokens: 25,
            total_tokens: 225,
            estimated_cost_usd: 0.02,
          },
        ],
      }),
    } as Response;
  });
  vi.stubGlobal('fetch', fetchMock);

  render(<App />);

  expect(await screen.findByText('session-after-thread')).toBeInTheDocument();
  await waitFor(() => expect(usageRequestCalls(fetchMock)).toHaveLength(1));
  expect(String(usageRequestCalls(fetchMock)[0][0])).toContain('refresh=0');
  expect(String(usageRequestCalls(fetchMock)[0][0])).toContain('limit=1500');
  expect(String(usageRequestCalls(fetchMock)[0][0])).toContain('include_archived=1');
  expect(screen.getByLabelText('History scope')).toHaveValue('all');
  expect(screen.getByLabelText('Rows to load')).toHaveValue(1500);
  expect(window.sessionStorage.getItem('codexUsageDashboardLoadSettings')).toContain('"loadLimit":1500');
});
});
