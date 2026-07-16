import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, vi, waitFor, within } from './test-utils/appTestHarness';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { threadsForCurrentUrl } from './features/threads/ThreadsPage';
import { ThreadsPage } from './features/threads/ThreadsPage';
import { fixtureModel } from './test-fixtures/dashboardFixture';

describe('React dashboard threads workspace', () => {
  installAppTestHooks();

  it('hydrates legacy top threads leaderboard label dashboard i18n payload', () => {
    window.localStorage?.removeItem('codex-usage-dashboard-language');
    window.history.replaceState(null, '', '/?view=threads');
    window.__CODEX_USAGE_BOOT__ = {
      language: 'es',
      language_direction: 'ltr',
      available_languages: [
        { code: 'en', english_name: 'English', native_name: 'English', dir: 'ltr' },
        { code: 'es', english_name: 'Spanish', native_name: 'Español', dir: 'ltr' },
      ],
      translation_catalog: {
      es: {
        'dashboard.top_threads_by_attention': 'Temas principales por puntuación de atención',
        'detail.next_action': 'Siguiente acción',
      },
      },
      loaded_row_count: 1,
      rows: [
        {
          record_id: 'threads-i18n-row',
          call_started_at: '2026-07-01T12:00:00Z',
          thread_name: 'threads-i18n-thread',
          model: 'codex-1',
          effort: 'high',
          input_tokens: 1000,
          cached_input_tokens: 400,
          output_tokens: 100,
          total_tokens: 1100,
          estimated_cost_usd: 0.1,
        },
      ],
    };

    render(<App />);

  expect(screen.getByText('Temas principales por puntuación de atención')).toBeInTheDocument();
  expect(screen.getByRole('treegrid', { name: 'Temas principales por puntuación de atención' })).toBeInTheDocument();
});

  it('hydrates legacy detail-first threads URL state', async () => {
    window.history.replaceState(null, '', '/?view=threads&detail=first');

    render(<App />);

    expect(screen.getByRole('heading', { name: 'Threads' })).toBeInTheDocument();
    const threadsTable = screen.getByRole('treegrid', { name: 'Thread leaderboard' });
    const firstThreadRow = within(threadsTable).getByRole('row', { name: /Collapse calls for thread-9f3a/i });
    expect(firstThreadRow).not.toBeNull();
    expect(firstThreadRow).toHaveAttribute('aria-expanded', 'true');

    await waitFor(() => {
      const params = new URLSearchParams(window.location.search);
      expect(params.get('view')).toBe('threads');
      expect(params.get('thread')).toBe('thread-9f3a');
      expect(params.get('detail')).toBeNull();
    });
  });

  it('hydrates legacy expanded thread URL state', async () => {
    window.history.replaceState(null, '', '/?view=threads&threads=thread-7c2b,thread-9f3a');

    render(<App />);

    const threadsTable = screen.getByRole('treegrid', { name: 'Thread leaderboard' });
    const selectedThreadRow = within(threadsTable).getByRole('row', { name: /Collapse calls for thread-7c2b/i });
    expect(selectedThreadRow).not.toBeNull();
    expect(selectedThreadRow).toHaveAttribute('aria-expanded', 'true');

    await waitFor(() => {
      const params = new URLSearchParams(window.location.search);
      expect(params.get('view')).toBe('threads');
      expect(params.get('thread')).toBe('thread-7c2b');
      expect(params.get('threads')).toBeNull();
    });
  });

  it('hydrates legacy expand-first threads URL state', async () => {
    window.history.replaceState(null, '', '/?view=threads&expand=first');

    render(<App />);

    const threadsTable = screen.getByRole('treegrid', { name: 'Thread leaderboard' });
    const firstThreadRow = within(threadsTable).getByRole('row', { name: /Collapse calls for thread-9f3a/i });
    expect(firstThreadRow).not.toBeNull();
    expect(firstThreadRow).toHaveAttribute('aria-expanded', 'true');

    await waitFor(() => {
      const params = new URLSearchParams(window.location.search);
      expect(params.get('thread')).toBe('thread-9f3a');
      expect(params.get('expand')).toBeNull();
    });
  });

  it('applies legacy shell model filters to threads workspace and export', async () => {
    window.history.replaceState(null, '', '/?view=threads&model=o4-mini');
    render(<App />);

    const threadsTable = screen.getByRole('treegrid', { name: 'Thread leaderboard' });
    expect(within(threadsTable).getByText('thread-7b2e91')).toBeInTheDocument();
    expect(within(threadsTable).getByText('thread-2f9e7d')).toBeInTheDocument();
    expect(within(threadsTable).queryByText('thread-9f3a')).not.toBeInTheDocument();

    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));

    await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(1));
    expect(await screen.findAllByText('Exported 2 call rows')).not.toHaveLength(0);
  });

  it('exports thread workspace call rows from the local toolbar', () => {
  const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  window.history.replaceState(null, '', '/?view=threads&risk=Low');

  render(<App />);

  fireEvent.click(screen.getByRole('button', { name: /Export thread calls/i }));
  expect(clickSpy).toHaveBeenCalledTimes(1);
  expect(screen.getAllByText(/Exported \d+ calls/).length).toBeGreaterThan(0);
});

it('expands, switches, and collapses one thread inline', () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Threads$/i }));
  const table = screen.getByRole('treegrid', { name: 'Thread leaderboard' });
  const first = within(table).getByRole('row', { name: /thread-9f3a/i });
  const second = within(table).getByRole('row', { name: /thread-7c2b/i });

  fireEvent.click(first);
  expect(first).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getByRole('region', { name: /Calls for thread-9f3a/i })).toBeInTheDocument();
  expect(window.location.search).toContain('thread=thread-9f3a');

  fireEvent.click(second);
  expect(second).toHaveAttribute('aria-expanded', 'true');
  expect(screen.queryByRole('region', { name: /Calls for thread-9f3a/i })).not.toBeInTheDocument();

  fireEvent.click(second);
  expect(screen.queryByRole('region', { name: /Calls for thread-7c2b/i })).not.toBeInTheDocument();
  expect(new URLSearchParams(window.location.search).has('thread')).toBe(false);
});

it('never opens a representative call from parent activation', () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Threads$/i }));
  const row = screen.getByRole('row', { name: /thread-9f3a/i });
  fireEvent.doubleClick(row);
  fireEvent.keyDown(row, { key: 'Enter' });
  fireEvent.keyDown(row, { key: ' ' });
  expect(screen.getByRole('heading', { name: 'Threads' })).toBeInTheDocument();
  expect(window.location.search).not.toContain('view=call');
});

it('isolates progressive thread call pages and retries a partial result', async () => {
  let resolveOldThread: ((response: Response) => void) | undefined;
  let newThreadPageTwoAttempts = 0;
  const callRow = (id: string, thread: string, model: string) => ({
    record_id: id,
    call_started_at: '2026-07-01T12:00:00Z',
    thread_name: thread,
    thread_key: thread,
    model,
    effort: 'high',
    input_tokens: 100,
    cached_input_tokens: 20,
    output_tokens: 10,
    total_tokens: 110,
  });
  const callsPage = (thread: string, rows: object[], offset: number, hasMore: boolean) => new Response(JSON.stringify({
    schema: 'codex-usage-tracker-thread-calls-v1',
    thread_key: thread,
    rows,
    row_count: rows.length,
    total_matched_rows: 3,
    limit: 100,
    offset,
    has_more: hasMore,
    next_offset: hasMore ? 2 : null,
  }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  const summary = (thread: string) => ({
    thread_key: thread,
    thread_label: thread,
    first_event_timestamp: '2026-07-01T12:00:00Z',
    latest_event_timestamp: '2026-07-01T12:02:00Z',
    latest_record_id: `${thread}-latest`,
    call_count: 3,
    session_count: 1,
    input_tokens: 300,
    cached_input_tokens: 60,
    uncached_input_tokens: 240,
    output_tokens: 30,
    reasoning_output_tokens: 0,
    total_tokens: 330,
    estimated_cost_usd: 0.03,
    usage_credits: 0,
    avg_cache_ratio: 0.2,
    max_context_window_percent: 0.2,
    max_recommendation_score: 0,
    primary_recommendation: '',
    call_initiator_summary: 'user x3',
    archived_call_count: 0,
    updated_at: '2026-07-01T12:02:00Z',
  });
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), window.location.origin);
    if (url.pathname === '/api/threads') {
      return new Response(JSON.stringify({
        schema: 'codex-usage-tracker-threads-v1', rows: [summary('old-thread'), summary('new-thread')],
        row_count: 2, total_matched_rows: 2, limit: 250, offset: 0, has_more: false, next_offset: null,
        include_archived: false,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    const thread = url.searchParams.get('thread_key');
    const offset = Number(url.searchParams.get('offset'));
    if (thread === 'old-thread') {
      return new Promise<Response>(resolve => { resolveOldThread = resolve; });
    }
    if (offset === 0) {
      return callsPage('new-thread', [callRow('new-1', 'new-thread', 'new-model-1'), callRow('boundary', 'new-thread', 'new-model-boundary')], 0, true);
    }
    newThreadPageTwoAttempts += 1;
    if (newThreadPageTwoAttempts <= 2) return new Response('temporary failure', { status: 500 });
    return callsPage('new-thread', [callRow('boundary', 'new-thread', 'new-model-boundary'), callRow('new-3', 'new-thread', 'new-model-3')], 2, false);
  }));
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  window.history.replaceState(null, '', '/?view=threads&thread=old-thread');
  render(<QueryClientProvider client={queryClient}><ThreadsPage
    model={{ ...fixtureModel, contextRuntime: { apiToken: 'thread-token', contextApiEnabled: false, fileMode: false } }}
    globalQuery="" onOpenInvestigator={vi.fn()} onCopyCallLink={vi.fn()}
    contextRuntime={{ apiToken: 'thread-token', contextApiEnabled: false, fileMode: false }}
    focusedEndpointsEnabled onNavigateView={vi.fn()}
  /></QueryClientProvider>);

  const grid = await screen.findByRole('treegrid', { name: 'Thread leaderboard' });
  await within(grid).findByRole('row', { name: /Collapse calls for old-thread/i });
  fireEvent.click(await within(grid).findByRole('row', { name: /new-thread/i }));
  await screen.findByText(/Partial result:/i, {}, { timeout: 3_000 });
  expect(screen.getByText('2 of 3 calls loaded')).toBeInTheDocument();
  resolveOldThread?.(callsPage('old-thread', [callRow('old-1', 'old-thread', 'old-model')], 0, false));
  await waitFor(() => expect(screen.queryByText('old-model / high')).not.toBeInTheDocument());
  expect(screen.getAllByText('new-model-boundary / high')).toHaveLength(1);

  fireEvent.click(screen.getByRole('button', { name: 'Retry loading thread calls' }));
  await screen.findByText('3 of 3 calls loaded');
  expect(screen.getAllByText('new-model-boundary / high')).toHaveLength(1);
  expect(screen.getByText('new-model-3 / high')).toBeInTheDocument();
});

it('shows and sorts all selected thread calls inline', () => {
  const tokenPattern = [700, 10, 600, 20, 500, 30, 400];
  window.__CODEX_USAGE_BOOT__ = {
    loaded_row_count: 7,
      rows: tokenPattern.map((inputTokens, index) => ({
        record_id: `thread-page-${index}`,
        call_started_at: `2026-07-01T12:0${index}:00Z`,
        thread_name: 'thread-page-demo',
        model: `model-${index}`,
        effort: 'high',
        input_tokens: inputTokens,
        cached_input_tokens: Math.round(inputTokens * 0.2),
        output_tokens: 10,
        total_tokens: inputTokens + 10,
        estimated_cost_usd: index / 100,
        previous_call_delta_seconds: index * 60,
        call_duration_seconds: 10 + index,
        call_initiator: index % 2 === 0 ? 'user' : 'codex',
      })),
    };

  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Threads$/i }));
  fireEvent.click(screen.getByRole('row', { name: /thread-page-demo/i }));
  const threadCallList = within(screen.getByRole('region', { name: /Calls for thread-page-demo/i }));

  expect(threadCallList.getByText('7 of 7 calls loaded')).toBeInTheDocument();
  expect(screen.getByText('model-0 / high')).toBeInTheDocument();

fireEvent.change(threadCallList.getByLabelText('Sort thread calls'), { target: { value: 'tokens' } });
expect(threadCallList.getByLabelText('Sort thread calls direction')).toHaveValue('desc');
fireEvent.change(threadCallList.getByLabelText('Sort thread calls direction'), { target: { value: 'asc' } });
expect(screen.getByText('model-1 / high')).toBeInTheDocument();
});

it('hydrates and syncs selected thread call sort URL state', async () => {
  const tokenPattern = [700, 10, 600, 20, 500, 30, 400];
  window.__CODEX_USAGE_BOOT__ = {
    loaded_row_count: 7,
    rows: tokenPattern.map((inputTokens, index) => ({
      record_id: `thread-url-page-${index}`,
      call_started_at: `2026-07-01T12:0${index}:00Z`,
      thread_name: 'thread-page-demo',
      model: `model-${index}`,
      effort: 'high',
      input_tokens: inputTokens,
      cached_input_tokens: Math.round(inputTokens * 0.2),
      output_tokens: 10,
      total_tokens: inputTokens + 10,
      estimated_cost_usd: index / 100,
    })),
  };
  window.history.replaceState(null, '', '/?view=threads&thread=thread-page-demo&thread_call_sort=tokens&thread_call_page=2');

  render(<App />);

  const threadCallList = within(screen.getByRole('region', { name: /Calls for thread-page-demo/i }));

  expect(threadCallList.getByLabelText('Sort thread calls')).toHaveValue('tokens');
  expect(threadCallList.getByText('7 of 7 calls loaded')).toBeInTheDocument();
  expect(screen.getByText('model-0 / high')).toBeInTheDocument();

  await waitFor(() => {
    const params = new URLSearchParams(window.location.search);
    expect(params.get('thread_call_sort')).toBe('tokens');
    expect(params.get('thread_call_page')).toBeNull();
  });

  fireEvent.change(threadCallList.getByLabelText('Sort thread calls'), { target: { value: 'cost' } });

  expect(threadCallList.getByLabelText('Sort thread calls')).toHaveValue('cost');
  expect(screen.getByText('model-6 / high')).toBeInTheDocument();

  await waitFor(() => {
    const params = new URLSearchParams(window.location.search);
    expect(params.get('thread_call_sort')).toBe('cost');
    expect(params.get('thread_call_page')).toBeNull();
  });

});

it('shows selected thread lifecycle and relationship signals from aggregate calls', () => {
  window.__CODEX_USAGE_BOOT__ = {
    loaded_row_count: 3,
    rows: [
      {
        record_id: 'thread-lifecycle-0',
        call_started_at: '2026-07-01T12:00:00Z',
        thread_name: 'thread-lifecycle-demo',
        parent_thread_name: 'parent-thread',
        model: 'model-0',
        effort: 'medium',
        input_tokens: 100,
        cached_input_tokens: 80,
        output_tokens: 20,
 total_tokens: 120,
 estimated_cost_usd: 0.02,
 usage_credits: 0.2,
 usage_credit_confidence: 'exact',
 duration_seconds: 10,
 context_window_percent: 0.1,
 call_initiator: 'subagent',
 },
      {
        record_id: 'thread-lifecycle-1',
        call_started_at: '2026-07-01T12:01:00Z',
        thread_name: 'thread-lifecycle-demo',
model: 'codex-auto-review',
        effort: 'high',
        input_tokens: 300,
        cached_input_tokens: 90,
        output_tokens: 50,
 total_tokens: 350,
 estimated_cost_usd: 0.04,
 pricing_estimated: true,
 usage_credits: 0.5,
 usage_credit_confidence: 'estimated',
 duration_seconds: 20,
 context_window_percent: 0.25,
 },
      {
        record_id: 'thread-lifecycle-2',
        call_started_at: '2026-07-01T12:02:00Z',
        thread_name: 'thread-lifecycle-demo',
        model: 'model-2',
        effort: 'high',
        input_tokens: 1000,
cached_input_tokens: 100,
output_tokens: 200,
total_tokens: 1200,
estimated_cost_usd: 1.2,
usage_credits: 2.4,
usage_credit_confidence: 'exact',
duration_seconds: 30,
context_window_percent: 0.75,
primary_signal: 'context-pressure',
recommended_action: 'Start a new thread after reviewing context growth.',
},
{
record_id: 'thread-lifecycle-child-0',
call_started_at: '2026-07-01T12:03:00Z',
thread_name: 'child-lifecycle-demo',
parent_thread_name: 'thread-lifecycle-demo',
model: 'child-model',
effort: 'medium',
input_tokens: 50,
cached_input_tokens: 10,
output_tokens: 10,
total_tokens: 60,
estimated_cost_usd: 0.01,
context_window_percent: 0.05,
},
],
};
window.history.replaceState(null, '', '/?view=threads&thread=thread-lifecycle-demo');

render(<App />);

expect(screen.getByRole('region', { name: /Calls for thread-lifecycle-demo/i })).toBeInTheDocument();
expect(screen.getByText('3 of 3 calls loaded')).toBeInTheDocument();
fireEvent.click(screen.getByRole('button', { name: 'Lifecycle' }));
expect(screen.getByRole('button', { name: 'Lifecycle' })).toHaveAttribute('aria-pressed', 'true');
expect(screen.queryByRole('treegrid', { name: 'Thread leaderboard' })).not.toBeInTheDocument();
});

it('hydrates and syncs selected thread URL state', () => {
    window.history.replaceState(null, '', '/?view=threads&thread=thread-3c5d');

    render(<App />);

    expect(screen.getByRole('heading', { name: 'Threads' })).toBeInTheDocument();
    expect(screen.getByText('No loaded aggregate call rows belong to this thread.')).toBeInTheDocument();

const row = within(screen.getByRole('treegrid', { name: 'Thread leaderboard' })).getByText('thread-9f3a').closest('[role="row"]');
expect(row).not.toBeNull();
    fireEvent.click(row as HTMLTableRowElement);

expect(window.location.search).toContain('view=threads');
    expect(window.location.search).toContain('thread=thread-9f3a');
    expect(screen.getByRole('button', { name: /Open investigator for thread call thread-9f3a1c codex-1/i })).toBeInTheDocument();
  });

it('hydrates and syncs thread filter URL state', async () => {
  window.history.replaceState(null, '', '/?view=threads&thread_q=thread-0e16&risk=Low&thread=thread-0e16&record=stale-record');

  render(<App />);

  expect(screen.getByRole('heading', { name: 'Threads' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Search threads, risks, token totals...')).toHaveValue('thread-0e16');
    expect(screen.getByLabelText('Cold risk')).toHaveValue('Low');
    expect(screen.getAllByText('thread-0e16').length).toBeGreaterThan(0);
    expect(
      screen.getByText(/Filters: Search "thread-0e16"; Cold risk Low; Selected thread-0e16/i),
    ).toBeInTheDocument();
    expect(screen.queryByText('thread-9f3a')).not.toBeInTheDocument();

  await waitFor(() => {
    const params = new URLSearchParams(window.location.search);
    expect(params.get('view')).toBe('threads');
    expect(params.get('thread_q')).toBe('thread-0e16');
    expect(params.get('risk')).toBe('Low');
    expect(params.get('thread')).toBe('thread-0e16');
    expect(params.get('record')).toBeNull();
  });
});

it('hydrates and syncs thread table sort URL state', async () => {
  window.history.replaceState(null, '', '/?view=threads&sort=totalTokens&direction=asc&page=2&record=stale-record');

  render(<App />);

  const table = screen.getByRole('treegrid', { name: 'Thread leaderboard' });
  const rows = within(table).getAllByRole('row');
  expect(rows[1]).toHaveTextContent('thread-0e16');

  await waitFor(() => {
    const params = new URLSearchParams(window.location.search);
    expect(params.get('view')).toBe('threads');
    expect(params.get('sort')).toBe('totalTokens');
    expect(params.get('direction')).toBe('asc');
    expect(params.get('page')).toBe('2');
    expect(params.get('record')).toBeNull();
  });

  fireEvent.click(within(table).getByRole('button', { name: /Total Tokens/i }));

  await waitFor(() => {
    const params = new URLSearchParams(window.location.search);
    expect(params.get('sort')).toBe('totalTokens');
    expect(params.get('direction')).toBe('desc');
    expect(params.get('page')).toBeNull();
  });
});

it('derives filtered and sorted thread export rows from URL state', () => {
  window.history.replaceState(null, '', '/?view=threads&risk=Low&sort=totalTokens&direction=asc');

  const rows = threadsForCurrentUrl(fixtureModel.threads);

  expect(rows.map(row => row.name)).toEqual(['thread-0e16', 'thread-b7f0', 'thread-d3e1']);
});

it('clears thread filters and selected thread URL state', () => {
  window.history.replaceState(null, '', '/?view=threads&thread=thread-3c5d&page=2&record=stale-record');

    render(<App />);

    expect(screen.getByRole('heading', { name: 'Threads' })).toBeInTheDocument();
  expect(window.location.search).toContain('thread=thread-3c5d');
  fireEvent.change(screen.getByPlaceholderText('Search threads, risks, token totals...'), { target: { value: 'thread-0e16' } });
  fireEvent.change(screen.getByDisplayValue('All risks'), { target: { value: 'Low' } });
  expect(screen.getAllByText('thread-0e16').length).toBeGreaterThan(0);
  expect(screen.queryByText('thread-9f3a')).not.toBeInTheDocument();
  let params = new URLSearchParams(window.location.search);
  expect(params.get('thread_q')).toBe('thread-0e16');
  expect(params.get('risk')).toBe('Low');

  fireEvent.click(screen.getByRole('button', { name: /Reset thread view/i }));

  expect(screen.getByPlaceholderText('Search threads, risks, token totals...')).toHaveValue('');
  expect(screen.getByDisplayValue('All risks')).toBeInTheDocument();
  expect(screen.getAllByText('thread-9f3a').length).toBeGreaterThan(0);
  expect(screen.getByText('Thread filters cleared')).toBeInTheDocument();
  params = new URLSearchParams(window.location.search);
  expect(params.get('view')).toBe('threads');
expect(params.get('thread')).toBeNull();
expect(params.get('thread_q')).toBeNull();
expect(params.get('risk')).toBeNull();
expect(params.get('page')).toBeNull();
expect(params.get('record')).toBeNull();
});
});
