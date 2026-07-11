import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, vi, waitFor, within } from './test-utils/appTestHarness';

describe('React dashboard shell live loading', () => {
  installAppTestHooks();

it('auto-loads live rows for shell boot payloads without showing fixture rows', async () => {
  window.__CODEX_USAGE_BOOT__ = {
    api_token: 'shell-load-token',
    context_api_enabled: true,
    shell_boot: true,
    loaded_row_count: 0,
    total_available_rows: 2,
    active_available_rows: 2,
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
  };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    void init;
    const url = String(input);
    if (!url.includes('/api/usage?')) {
      throw new Error(`Unexpected request: ${url}`);
    }
    return {
      ok: true,
      json: async () => ({
        api_token: 'shell-load-token',
        context_api_enabled: true,
        loaded_row_count: 1,
        total_available_rows: 2,
        default_load_window: 'all',
        load_window: 'all',
        limit: 500,
        rows: [
          {
            record_id: 'real-live-row',
            call_started_at: '2026-07-02T10:00:00Z',
            thread_name: 'real-live-thread',
            model: 'codex-1',
            effort: 'high',
            input_tokens: 1_000,
            cached_input_tokens: 400,
            output_tokens: 250,
            total_tokens: 1_250,
            estimated_cost_usd: 0.12,
          },
        ],
      }),
    } as Response;
  });
  vi.stubGlobal('fetch', fetchMock);

  render(<App />);

  expect(screen.queryByText('thread-9f3a1c')).not.toBeInTheDocument();
  expect(await screen.findByText('real-live-thread')).toBeInTheDocument();
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  expect(String(fetchMock.mock.calls[0][0])).toContain('refresh=0');
  expect(String(fetchMock.mock.calls[0][0])).toContain('limit=10000');
  expect(String(fetchMock.mock.calls[0][0])).toContain('load_window=all');
  expect(screen.getByRole('button', { name: 'All time' })).toHaveAttribute('aria-pressed', 'true');
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

it('loads the next finite row batch from recent calls controls', async () => {
  window.__CODEX_USAGE_BOOT__ = {
    api_token: 'load-more-token',
    context_api_enabled: true,
    loaded_row_count: 500,
      total_available_rows: 900,
    has_more: true,
    limit: 500,
    rows: [
      {
        record_id: 'row-batch-before',
        call_started_at: '2026-07-01T10:00:00Z',
        thread_name: 'row-batch-before-thread',
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
    if (!url.includes('/api/usage?')) {
      throw new Error(`Unexpected request: ${url}`);
    }
    return {
      ok: true,
      json: async () => ({
        api_token: 'load-more-token',
        context_api_enabled: true,
        loaded_row_count: 1_500,
        total_available_rows: 1_500,
        has_more: false,
        limit: 1_500,
        rows: [
          {
            record_id: 'row-batch-after',
            call_started_at: '2026-07-01T11:00:00Z',
            thread_name: 'row-batch-after-thread',
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

expect(screen.getAllByText('Loaded 500 of 900').length).toBeGreaterThan(0);
expect(screen.getByText('Most recent 500')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Load more recent calls' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Load more recent calls' }));

  expect(await screen.findByText('row-batch-after-thread')).toBeInTheDocument();
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  expect(String(fetchMock.mock.calls[0][0])).toContain('limit=1500');
  expect(screen.getByLabelText('Rows to load')).toHaveValue(1500);
expect(screen.getAllByText('Loaded 1,500 rows').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Load more recent calls' })).toBeDisabled();
expect(screen.getByRole('button', { name: /^Load more$/i })).toBeDisabled();
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
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  expect(String(fetchMock.mock.calls[0][0])).toContain('refresh=0');
  expect(String(fetchMock.mock.calls[0][0])).toContain('limit=1500');
  expect(String(fetchMock.mock.calls[0][0])).toContain('include_archived=1');
  expect(screen.getByLabelText('History scope')).toHaveValue('all');
  expect(screen.getByLabelText('Rows to load')).toHaveValue(1500);
  expect(window.sessionStorage.getItem('codexUsageDashboardLoadSettings')).toContain('"loadLimit":1500');
});
});
