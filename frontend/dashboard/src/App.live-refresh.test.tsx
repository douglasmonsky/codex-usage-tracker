import { act, App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, vi, waitFor } from './test-utils/appTestHarness';
import { shouldAutoRefreshUsageView } from './App';

describe('React dashboard live refresh and row loading', () => {
  installAppTestHooks();

it('matches legacy automatic refresh view exclusions', () => {
  expect(shouldAutoRefreshUsageView('overview')).toBe(true);
  expect(shouldAutoRefreshUsageView('calls')).toBe(true);
  expect(shouldAutoRefreshUsageView('call')).toBe(false);
  expect(shouldAutoRefreshUsageView('diagnostics')).toBe(false);
});

it('auto refreshes live dashboards immediately and on interval', async () => {
  vi.useFakeTimers();
  window.__CODEX_USAGE_BOOT__ = {
    api_token: 'auto-refresh-token',
    context_api_enabled: true,
    loaded_row_count: 1,
    limit: 500,
    rows: [
      {
        record_id: 'record-auto-before',
        call_started_at: '2026-07-01T10:00:00Z',
        thread_name: 'auto-before-thread',
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
  const refreshedRows = ['auto-first-thread', 'auto-second-thread'];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    void init;
    const url = String(input);
    if (!url.includes('/api/usage?')) {
      throw new Error(`Unexpected request: ${url}`);
    }
    const threadName = refreshedRows[Math.min(fetchMock.mock.calls.length - 1, refreshedRows.length - 1)];
    return {
      ok: true,
      json: async () => ({
        api_token: 'auto-refresh-token',
        context_api_enabled: true,
        loaded_row_count: 1,
        total_available_rows: 2,
        limit: 500,
        history_scope: 'active',
        include_archived: false,
        rows: [
          {
            record_id: `record-${threadName}`,
            call_started_at: '2026-07-01T11:00:00Z',
            thread_name: threadName,
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
  expect(screen.getByText('auto-before-thread')).toBeInTheDocument();

  await act(async () => {
    fireEvent.click(screen.getByLabelText('Auto refresh'));
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(screen.getByText('auto-first-thread')).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);

  await act(async () => {
    await vi.advanceTimersByTimeAsync(10_000);
  });

  expect(screen.getByText('auto-second-thread')).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(String(fetchMock.mock.calls[1][0])).toContain('refresh=1');
  expect(String(fetchMock.mock.calls[1][0])).toContain('limit=500');
});

it('pauses automatic aggregate refresh on full-page call investigator', async () => {
vi.useFakeTimers();
window.history.replaceState(null, '', '/?view=call&record=record-auto-call');
window.__CODEX_USAGE_BOOT__ = {
api_token: 'auto-refresh-token',
context_api_enabled: true,
loaded_row_count: 1,
limit: 500,
rows: [
{
record_id: 'record-auto-call',
call_started_at: '2026-07-01T10:00:00Z',
thread_name: 'auto-call-thread',
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
api_token: 'auto-refresh-token',
context_api_enabled: true,
loaded_row_count: 1,
total_available_rows: 1,
limit: 500,
history_scope: 'active',
include_archived: false,
rows: [
{
record_id: 'record-auto-call',
call_started_at: '2026-07-01T11:00:00Z',
thread_name: 'auto-call-thread',
model: 'o4-mini',
effort: 'medium',
input_tokens: 200,
cached_input_tokens: 100,
output_tokens: 20,
total_tokens: 220,
estimated_cost_usd: 0.02,
},
],
}),
} as Response;
});
vi.stubGlobal('fetch', fetchMock);

render(<App />);
expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();

await act(async () => {
fireEvent.click(screen.getByLabelText('Auto refresh'));
await Promise.resolve();
await vi.advanceTimersByTimeAsync(20_000);
});

expect(fetchMock).not.toHaveBeenCalled();
expect(screen.getAllByText('Auto refresh pauses on Call Investigator and Diagnostics').length).toBeGreaterThan(0);

await act(async () => {
fireEvent.click(screen.getByRole('button', { name: /^Refresh$/i }));
await Promise.resolve();
});
expect(fetchMock).toHaveBeenCalledTimes(1);
expect(String(fetchMock.mock.calls[0][0])).toContain('/api/usage?');
expect(String(fetchMock.mock.calls[0][0])).toContain('refresh=1');
});

it('refreshes aggregate rows through the live usage API', async () => {
  window.__CODEX_USAGE_BOOT__ = {
    api_token: 'refresh-token',
      context_api_enabled: true,
      loaded_row_count: 1,
      limit: 500,
      rows: [
        {
          record_id: 'record-before-refresh',
          call_started_at: '2026-07-01T10:00:00Z',
          thread_name: 'before-refresh-thread',
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
          api_token: 'refresh-token',
          context_api_enabled: true,
          loaded_row_count: 1,
          total_available_rows: 44,
          limit: 500,
          history_scope: 'active',
          include_archived: false,
          rows: [
            {
              record_id: 'record-after-refresh',
              call_started_at: '2026-07-01T11:00:00Z',
              thread_name: 'after-refresh-thread',
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
    expect(screen.getByText('before-refresh-thread')).toBeInTheDocument();

fireEvent.click(screen.getByRole('button', { name: /^Refresh$/i }));

    expect(await screen.findByText('after-refresh-thread')).toBeInTheDocument();
    expect(screen.queryByText('before-refresh-thread')).not.toBeInTheDocument();
    expect(screen.getAllByText('Live refresh loaded 1 of 44 aggregate rows').length).toBeGreaterThan(0);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/usage?');
    expect(String(fetchMock.mock.calls[0][0])).toContain('refresh=1');
    expect(String(fetchMock.mock.calls[0][0])).toContain('limit=500');
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        cache: 'no-store',
        headers: expect.objectContaining({
          'X-Codex-Usage-Token': 'refresh-token',
        }),
      }),
  );
});

it('applies typed row limits only after Load is clicked', async () => {
  window.__CODEX_USAGE_BOOT__ = {
    api_token: 'row-limit-token',
    context_api_enabled: true,
    loaded_row_count: 1,
    limit: 500,
    rows: [
      {
        record_id: 'row-limit-before',
        call_started_at: '2026-07-01T10:00:00Z',
        thread_name: 'row-limit-before-thread',
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
        api_token: 'row-limit-token',
        context_api_enabled: true,
        loaded_row_count: 1,
        total_available_rows: 50000,
        limit: 250000,
        rows: [
          {
            record_id: 'row-limit-after',
            call_started_at: '2026-07-01T11:00:00Z',
            thread_name: 'row-limit-after-thread',
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
  fireEvent.change(screen.getByLabelText('Rows to load'), { target: { value: '250000' } });

  expect(screen.getByLabelText('Rows to load')).toHaveValue(250000);
  expect(screen.getByLabelText('Rows to load slider')).toHaveAttribute('max', '251100');
  expect(fetchMock).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', { name: /^Load$/i }));

  expect(await screen.findByText('row-limit-after-thread')).toBeInTheDocument();
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  expect(String(fetchMock.mock.calls[0][0])).toContain('limit=250000');
});

it('can request an uncapped row range', async () => {
  window.__CODEX_USAGE_BOOT__ = {
    api_token: 'row-limit-token',
    context_api_enabled: true,
    loaded_row_count: 1,
    limit: 500,
    rows: [
      {
        record_id: 'row-limit-before',
        call_started_at: '2026-07-01T10:00:00Z',
        thread_name: 'row-limit-before-thread',
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
        api_token: 'row-limit-token',
        context_api_enabled: true,
        loaded_row_count: 2,
        total_available_rows: 2,
        limit: null,
        rows: [
          {
            record_id: 'row-limit-after-a',
            call_started_at: '2026-07-01T11:00:00Z',
            thread_name: 'row-limit-after-thread-a',
            model: 'o5',
            effort: 'high',
            input_tokens: 200,
            cached_input_tokens: 20,
            output_tokens: 25,
            total_tokens: 225,
            estimated_cost_usd: 0.02,
          },
          {
            record_id: 'row-limit-after-b',
            call_started_at: '2026-07-01T11:05:00Z',
            thread_name: 'row-limit-after-thread-b',
            model: 'o5',
            effort: 'high',
            input_tokens: 100,
            cached_input_tokens: 10,
            output_tokens: 15,
            total_tokens: 115,
            estimated_cost_usd: 0.01,
          },
        ],
      }),
    } as Response;
  });
  vi.stubGlobal('fetch', fetchMock);

render(<App />);
const rowLimitSlider = screen.getByLabelText('Rows to load slider');
fireEvent.click(screen.getByLabelText('No row cap'));

    expect(screen.getByText('No cap enabled')).toBeInTheDocument();
    expect(screen.getAllByText('No cap').length).toBeGreaterThan(0);
    expect(screen.getByLabelText('No row cap')).toBeChecked();
    expect(rowLimitSlider).not.toBeDisabled();
    expect(rowLimitSlider.getAttribute('aria-valuetext')).toContain('No row cap');

  fireEvent.click(screen.getByRole('button', { name: /^Load all$/i }));

  expect(await screen.findByText('row-limit-after-thread-a')).toBeInTheDocument();
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  expect(String(fetchMock.mock.calls[0][0])).toContain('limit=10000');
  expect(screen.getAllByText(/no row cap/i).length).toBeGreaterThan(0);
});

it('refreshes usage rows when history scope changes', async () => {
  window.__CODEX_USAGE_BOOT__ = {
      api_token: 'history-token',
      context_api_enabled: true,
    loaded_row_count: 1,
    total_available_rows: 3,
    all_history_available_rows: 9,
    active_available_rows: 3,
    archived_available_rows: 6,
    limit: 500,
      history_scope: 'active',
      include_archived: false,
      rows: [
        {
          record_id: 'record-active-history',
          call_started_at: '2026-07-01T10:00:00Z',
          thread_name: 'active-history-thread',
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
          api_token: 'history-token',
      context_api_enabled: true,
      loaded_row_count: 1,
      total_available_rows: 9,
      all_history_available_rows: 9,
      active_available_rows: 3,
      archived_available_rows: 6,
      limit: 500,
          history_scope: 'all-history',
          include_archived: true,
          rows: [
            {
              record_id: 'record-all-history',
              call_started_at: '2026-07-01T11:00:00Z',
              thread_name: 'all-history-thread',
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
  expect(screen.getByText('active-history-thread')).toBeInTheDocument();
  expect(screen.getByText('Active sessions only; 6 archived calls hidden')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('History scope'), { target: { value: 'all' } });
    expect(window.location.search).toContain('history=all');

    expect(await screen.findByText('all-history-thread')).toBeInTheDocument();
  expect(screen.queryByText('active-history-thread')).not.toBeInTheDocument();
  expect(screen.getAllByText('All history - 500 rows').length).toBeGreaterThan(0);
  expect(screen.getByText('All history includes 6 archived calls')).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/usage?');
    expect(String(fetchMock.mock.calls[0][0])).toContain('refresh=1');
    expect(String(fetchMock.mock.calls[0][0])).toContain('limit=500');
    expect(String(fetchMock.mock.calls[0][0])).toContain('include_archived=1');
  expect(fetchMock.mock.calls[0][1]).toEqual(
    expect.objectContaining({
      cache: 'no-store',
      headers: expect.objectContaining({
        'X-Codex-Usage-Token': 'history-token',
        }),
    }),
  );
});

it('refreshes aggregate report evidence through the shell live usage API', async () => {
  window.__CODEX_USAGE_BOOT__ = {
    api_token: 'report-refresh-token',
    context_api_enabled: true,
    loaded_row_count: 1,
    total_available_rows: 1,
    limit: 500,
    rows: [
      {
        record_id: 'report-before',
        call_started_at: '2026-07-01T10:00:00Z',
        thread_name: 'report-before-thread',
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
    if (url.includes('/api/reports/pack?')) {
      return {
        ok: true,
        json: async () => ({
          schema: 'codex-usage-tracker-reports-pack-v1',
          reports: [],
          evidence: {},
          row_count: 0,
          total_matched_rows: 0,
          raw_context_included: false,
        }),
      } as Response;
    }
    if (!url.includes('/api/usage?')) throw new Error(`Unexpected request: ${url}`);
    return {
      ok: true,
      json: async () => ({
        api_token: 'report-refresh-token',
        context_api_enabled: true,
        loaded_row_count: 1,
        total_available_rows: 7,
        limit: 500,
        history_scope: 'active',
        include_archived: false,
        rows: [
          {
            record_id: 'report-after',
            call_started_at: '2026-07-01T11:00:00Z',
            thread_name: 'report-after-thread',
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
  const usageCalls = () => fetchMock.mock.calls.filter(([input]) => String(input).includes('/api/usage?'));
  vi.stubGlobal('fetch', fetchMock);

  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Reports$/i }));
  expect(screen.getAllByText('Stored snapshot loaded just now').length).toBeGreaterThan(0);

  fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));

  expect((await screen.findAllByText('Live refresh loaded 1 of 7 aggregate rows')).length).toBeGreaterThan(0);
  expect(screen.getAllByText('report-after-thread').length).toBeGreaterThan(0);
  expect(screen.queryByText('report-before-thread')).not.toBeInTheDocument();
  await waitFor(() => expect(usageCalls()).toHaveLength(1));
  const [usageInput, usageInit] = usageCalls()[0];
  expect(String(usageInput)).toContain('/api/usage?');
  expect(String(usageInput)).toContain('refresh=1');
  expect(String(usageInput)).toContain('limit=500');
  expect(usageInit).toEqual(
    expect.objectContaining({
      cache: 'no-store',
      headers: expect.objectContaining({
        'X-Codex-Usage-Token': 'report-refresh-token',
      }),
    }),
  );
});
});
