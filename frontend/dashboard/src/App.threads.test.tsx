import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, vi, waitFor, within } from './test-utils/appTestHarness';
import { threadsForCurrentUrl } from './features/threads/ThreadsPage';
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
  expect(screen.getByRole('table', { name: 'Temas principales por puntuación de atención' })).toBeInTheDocument();
  expect(screen.getByText('Siguiente acción')).toBeInTheDocument();
});

  it('hydrates legacy detail-first threads URL state', async () => {
    window.history.replaceState(null, '', '/?view=threads&detail=first');

    render(<App />);

    expect(screen.getByRole('heading', { name: 'Threads' })).toBeInTheDocument();
    const threadsTable = screen.getByRole('table', { name: 'Thread leaderboard' });
    expect(within(threadsTable).getByRole('columnheader', { name: 'Thread' })).toHaveClass('sticky-column');
    expect(within(threadsTable).getByText('thread-9f3a').closest('td')).toHaveClass('sticky-column');
    const firstThreadRow = within(threadsTable).getByText('thread-9f3a').closest('tr');
    expect(firstThreadRow).not.toBeNull();
    expect(firstThreadRow).toHaveAttribute('aria-selected', 'true');

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

    const threadsTable = screen.getByRole('table', { name: 'Thread leaderboard' });
    const selectedThreadRow = within(threadsTable).getByText('thread-7c2b').closest('tr');
    expect(selectedThreadRow).not.toBeNull();
    expect(selectedThreadRow).toHaveAttribute('aria-selected', 'true');

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

    const threadsTable = screen.getByRole('table', { name: 'Thread leaderboard' });
    const firstThreadRow = within(threadsTable).getByText('thread-9f3a').closest('tr');
    expect(firstThreadRow).not.toBeNull();
    expect(firstThreadRow).toHaveAttribute('aria-selected', 'true');

    await waitFor(() => {
      const params = new URLSearchParams(window.location.search);
      expect(params.get('thread')).toBe('thread-9f3a');
      expect(params.get('expand')).toBeNull();
    });
  });

  it('applies legacy shell model filters to threads workspace and export', async () => {
    window.history.replaceState(null, '', '/?view=threads&model=o4-mini');
    render(<App />);

    const threadsTable = screen.getByRole('table', { name: 'Thread leaderboard' });
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

it('opens the full-page call investigator from selected thread calls', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /^Threads$/i }));

    expect(screen.getByRole('heading', { name: 'Threads' })).toBeInTheDocument();
    expect(screen.getByText('Thread Calls')).toBeInTheDocument();
    const threadCallList = screen.getByText('Thread Calls').closest('.thread-call-list');
    expect(threadCallList).not.toBeNull();
    const firstCallRow = within(threadCallList as HTMLElement).getByText('codex-1 / high').closest('li');
    expect(firstCallRow).not.toBeNull();
    fireEvent.click(firstCallRow as HTMLElement);

    expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
    expect(screen.getByText('thread-9f3a1c / codex-1')).toBeInTheDocument();
  expect(window.location.search).toContain('view=call');
  expect(window.location.search).toContain('record=fixture-call-0');
});

it('opens full-page call investigator from thread leaderboard rows', () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Threads$/i }));

  const threadsTable = screen.getByRole('table', { name: 'Thread leaderboard' });
  fireEvent.click(within(threadsTable).getByRole('button', { name: /Open investigator for latest call in thread-9f3a/i }));

  expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
  expect(screen.getByText('thread-9f3a1c / codex-1')).toBeInTheDocument();
  expect(window.location.search).toContain('view=call');
  expect(window.location.search).toContain('record=fixture-call-0');
  expect(window.location.search).toContain('return=threads');
  fireEvent.click(screen.getByRole('button', { name: /Back to Threads/i }));
  expect(screen.getByRole('heading', { name: 'Threads' })).toBeInTheDocument();
  expect(window.location.search).toContain('view=threads');
  expect(window.location.search).not.toContain('record=');
  expect(window.location.search).not.toContain('return=');
});

it('expands thread evidence without leaving the thread leaderboard', () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Threads$/i }));

  const threadsTable = screen.getByRole('table', { name: 'Thread leaderboard' });
  const row = within(threadsTable).getByText('thread-9f3a').closest('tr');
  expect(row).not.toBeNull();
fireEvent.click(row as HTMLTableRowElement);

  expect(screen.getByRole('heading', { name: 'Threads' })).toBeInTheDocument();
  expect(screen.getByText('Thread Calls')).toBeInTheDocument();
  expect(window.location.search).toContain('view=threads');
  expect(window.location.search).not.toContain('record=');
});

it('copies call investigator links from thread row actions', async () => {
 const writeText = vi.fn().mockResolvedValue(undefined);
 Object.defineProperty(navigator, 'clipboard', {
 configurable: true,
 value: { writeText },
 });

 render(<App />);
 fireEvent.click(screen.getByRole('button', { name: /^Threads$/i }));

 fireEvent.click(screen.getByRole('button', { name: /Copy link for latest call in thread-9f3a/i }));
 await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
 const tableUrl = new URL(writeText.mock.calls[0][0]);
 expect(tableUrl.searchParams.get('view')).toBe('call');
 expect(tableUrl.searchParams.get('return')).toBe('threads');
 expect(tableUrl.searchParams.get('record')).toBe('fixture-call-0');

 fireEvent.click(screen.getByRole('button', { name: /Copy link for thread call thread-9f3a1c codex-1/i }));
 await waitFor(() => expect(writeText).toHaveBeenCalledTimes(2));
 const timelineUrl = new URL(writeText.mock.calls[1][0]);
 expect(timelineUrl.searchParams.get('return')).toBe('threads');
 expect(timelineUrl.searchParams.get('record')).toBe('fixture-call-0');
});

it('pages and sorts selected thread calls', () => {
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
  const threadCalls = screen.getByText('Thread Calls').closest('.thread-call-list');
  expect(threadCalls).not.toBeNull();
  const threadCallList = within(threadCalls as HTMLElement);

  expect(threadCallList.getByText('5 of 7 loaded')).toBeInTheDocument();
  expect(threadCallList.queryByText('model-0 / high')).not.toBeInTheDocument();
fireEvent.click(threadCallList.getByRole('button', { name: /Show 2 more calls/i }));
    expect(threadCallList.getByText('7 of 7 loaded')).toBeInTheDocument();
    expect(threadCallList.getByText('model-0 / high')).toBeInTheDocument();
    expect(threadCallList.getAllByText('CACHE')[0]).toHaveAttribute('title', 'Cache Risk');
    expect(threadCallList.getByText('Prev -')).toBeInTheDocument();
    expect(threadCallList.getAllByText('user initiated').length).toBeGreaterThan(0);

fireEvent.change(threadCallList.getByLabelText('Sort thread calls'), { target: { value: 'tokens' } });
expect(threadCallList.getByText('5 of 7 loaded')).toBeInTheDocument();
expect(threadCallList.getByText('model-0 / high')).toBeInTheDocument();
expect(threadCallList.getByText('2 more available')).toBeInTheDocument();
expect(threadCallList.getByLabelText('Sort thread calls direction')).toHaveValue('desc');
fireEvent.change(threadCallList.getByLabelText('Sort thread calls direction'), { target: { value: 'asc' } });
expect(threadCallList.getByText('model-1 / high')).toBeInTheDocument();
expect(threadCallList.queryByText('model-0 / high')).not.toBeInTheDocument();
});

it('hydrates and syncs selected thread call sort and page URL state', async () => {
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

  const threadCalls = screen.getByText('Thread Calls').closest('.thread-call-list');
  expect(threadCalls).not.toBeNull();
  const threadCallList = within(threadCalls as HTMLElement);

  expect(threadCallList.getByLabelText('Sort thread calls')).toHaveValue('tokens');
  expect(threadCallList.getByText('7 of 7 loaded')).toBeInTheDocument();
  expect(threadCallList.getByText('model-0 / high')).toBeInTheDocument();

  await waitFor(() => {
    const params = new URLSearchParams(window.location.search);
    expect(params.get('thread_call_sort')).toBe('tokens');
    expect(params.get('thread_call_page')).toBe('2');
  });

  fireEvent.change(threadCallList.getByLabelText('Sort thread calls'), { target: { value: 'cost' } });

  expect(threadCallList.getByLabelText('Sort thread calls')).toHaveValue('cost');
  expect(threadCallList.getByText('5 of 7 loaded')).toBeInTheDocument();
  expect(threadCallList.getByText('model-6 / high')).toBeInTheDocument();

  await waitFor(() => {
    const params = new URLSearchParams(window.location.search);
    expect(params.get('thread_call_sort')).toBe('cost');
    expect(params.get('thread_call_page')).toBeNull();
  });

  fireEvent.click(threadCallList.getByRole('button', { name: /Show 2 more calls/i }));

  await waitFor(() => {
    expect(new URLSearchParams(window.location.search).get('thread_call_page')).toBe('2');
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

const threadStatus = screen.getByText('Thread Status').closest('.thread-status-card');
expect(threadStatus).not.toBeNull();
const threadStatusPanel = within(threadStatus as HTMLElement);
expect(threadStatusPanel.getByText('Pricing status')).toBeInTheDocument();
expect(threadStatusPanel.getByText('Credit status')).toBeInTheDocument();
expect(threadStatusPanel.getAllByText('Mixed')).toHaveLength(2);
expect(threadStatusPanel.getByText('Cache ratio')).toBeInTheDocument();
expect(threadStatusPanel.getByText('Max context use')).toBeInTheDocument();
expect(threadStatusPanel.getByText('Next action')).toBeInTheDocument();
expect(threadStatusPanel.getAllByText('Review context growth').length).toBeGreaterThan(0);
const threadImpact = screen.getByText('Thread Impact').closest('.thread-impact-card');
expect(threadImpact).not.toBeNull();
const threadImpactPanel = within(threadImpact as HTMLElement);
expect(threadImpactPanel.getByText('Codex credits')).toBeInTheDocument();
expect(threadImpactPanel.getByText('Allowance impact')).toBeInTheDocument();
expect(threadImpactPanel.getByText('Attention score')).toBeInTheDocument();
expect(threadImpactPanel.getByText('Cost per call')).toBeInTheDocument();
expect(threadImpactPanel.getByText('3.1 credits (Mixed)')).toBeInTheDocument();
expect(threadImpactPanel.getAllByText('3.1 credits counted').length).toBeGreaterThan(0);
expect(threadImpactPanel.getByText(/^\d+$/)).toBeInTheDocument();
expect(threadImpactPanel.getByText('$0.42')).toBeInTheDocument();
expect(screen.getByText('Context 75.0%')).toBeInTheDocument();
expect(screen.getByText('Best-guess estimate')).toBeInTheDocument();
expect(screen.getAllByText('Configured price').length).toBeGreaterThan(0);
expect(screen.getByText('30s')).toBeInTheDocument();
expect(screen.getByText('2.4 credits')).toBeInTheDocument();

  expect(screen.getByText('Thread Lifecycle')).toBeInTheDocument();
  expect(screen.getByText('Subagent before spike')).toBeInTheDocument();
  expect(screen.getByText('First expensive turn')).toBeInTheDocument();
  expect(screen.getByText(/Call 3/)).toBeInTheDocument();
  expect(screen.getByText('Largest token jump')).toBeInTheDocument();
expect(screen.getByText(/1\.2K at/)).toBeInTheDocument();
expect(screen.getByText('Cache trend')).toBeInTheDocument();
expect(screen.getByText('-70.0%')).toBeInTheDocument();
expect(screen.getByText('Context trend')).toBeInTheDocument();
expect(screen.getByText('+65.0%')).toBeInTheDocument();
const relationships = screen.getByText('Relationships').closest('.thread-relationships-card');
expect(relationships).not.toBeNull();
const relationshipPanel = within(relationships as HTMLElement);
expect(relationshipPanel.getByText('parent-thread')).toBeInTheDocument();
expect(relationshipPanel.getByText('Spawned from')).toBeInTheDocument();
expect(relationshipPanel.getByText('Subagent calls')).toBeInTheDocument();
expect(relationshipPanel.getByText('Auto-review calls')).toBeInTheDocument();
expect(relationshipPanel.getByText('Attached calls')).toBeInTheDocument();
expect(relationshipPanel.getByText('Spawned threads')).toBeInTheDocument();
expect(relationshipPanel.getByText('Spawned child calls')).toBeInTheDocument();
expect(relationshipPanel.getAllByText('1')).toHaveLength(5);
const threadFields = screen.getByText('Thread Fields').closest('.thread-secondary-card');
expect(threadFields).not.toBeNull();
const threadFieldPanel = within(threadFields as HTMLElement);
expect(threadFieldPanel.getByText('Latest activity')).toBeInTheDocument();
expect(threadFieldPanel.getByText('Total tokens')).toBeInTheDocument();
expect(threadFieldPanel.getByText('Loaded calls')).toBeInTheDocument();
expect(threadFieldPanel.getByText('Efficiency signals')).toBeInTheDocument();
expect(threadFieldPanel.getByText('Model mix')).toBeInTheDocument();
expect(threadFieldPanel.getByText('Effort mix')).toBeInTheDocument();
expect(threadFieldPanel.getByText('1 signals')).toBeInTheDocument();
});

it('hydrates and syncs selected thread URL state', () => {
    window.history.replaceState(null, '', '/?view=threads&thread=thread-3c5d');

    render(<App />);

    expect(screen.getByRole('heading', { name: 'Threads' })).toBeInTheDocument();
    expect(screen.getByText('No loaded aggregate call rows belong to this thread.')).toBeInTheDocument();

const row = within(screen.getByRole('table', { name: 'Thread leaderboard' })).getByText('thread-9f3a').closest('tr');
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

  const table = screen.getByRole('table', { name: 'Thread leaderboard' });
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
