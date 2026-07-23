import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, fireEvent, installAppTestHooks, it, render, screen, vi, waitFor, within } from './test-utils/appTestHarness';
import { fixtureModel } from './test-fixtures/dashboardFixture';
import { ThreadsPage } from './features/threads/ThreadsPage';

describe('React dashboard threads live queries', () => {
  installAppTestHooks();

  it('hydrates a direct thread link from a later focused summary page', async () => {
    const summary = (thread: string) => ({
      thread_key: thread, thread_label: thread,
      first_event_timestamp: '2026-07-01T12:00:00Z', latest_event_timestamp: '2026-07-01T12:02:00Z',
      latest_record_id: `${thread}-latest`, call_count: 1, session_count: 1,
      input_tokens: 100, cached_input_tokens: 20, uncached_input_tokens: 80, output_tokens: 10,
      reasoning_output_tokens: 0, total_tokens: 110, estimated_cost_usd: 0.01, usage_credits: 0,
      avg_cache_ratio: 0.2, max_context_window_percent: 0.2, max_recommendation_score: 0,
      primary_recommendation: '', call_initiator_summary: 'user x1', archived_call_count: 0,
      updated_at: '2026-07-01T12:02:00Z',
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), window.location.origin);
      if (url.pathname === '/api/threads') {
        const offset = Number(url.searchParams.get('offset'));
        const rows = offset === 0 ? [summary('page-one-thread')] : [summary('page-two-thread')];
        return new Response(JSON.stringify({
          schema: 'codex-usage-tracker-threads-v1', rows, row_count: 1, total_matched_rows: 2,
          limit: 250, offset, has_more: offset === 0, next_offset: offset === 0 ? 1 : null,
          include_archived: false,
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return new Response(JSON.stringify({
        schema: 'codex-usage-tracker-thread-calls-v1', thread_key: 'page-two-thread',
        rows: [{
          record_id: 'page-two-call', call_started_at: '2026-07-01T12:02:00Z',
          thread_name: 'page-two-thread', thread_key: 'page-two-thread', model: 'page-two-model', effort: 'high',
          input_tokens: 100, cached_input_tokens: 20, output_tokens: 10, total_tokens: 110,
        }],
        row_count: 1, total_matched_rows: 1, limit: 100, offset: 0, has_more: false, next_offset: null,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);
    window.history.replaceState(null, '', '/?view=threads&thread=page-two-thread');
    const queryClient = new QueryClient();
    render(<QueryClientProvider client={queryClient}><ThreadsPage
      model={{ ...fixtureModel, contextRuntime: { apiToken: 'thread-token', contextApiEnabled: false, fileMode: false } }}
      globalQuery="" onOpenInvestigator={vi.fn()} onCopyCallLink={vi.fn()}
      contextRuntime={{ apiToken: 'thread-token', contextApiEnabled: false, fileMode: false }}
      focusedEndpointsEnabled onNavigateView={vi.fn()}
    /></QueryClientProvider>);

    expect(await screen.findByRole('row', { name: /Collapse calls for page-two-thread/i })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: /Calls for page-two-thread/i })).toBeInTheDocument();
    expect(await screen.findByText('page-two-model')).toBeInTheDocument();
    expect(new URLSearchParams(window.location.search).get('thread_key')).toBe('page-two-thread');
    expect(new URLSearchParams(window.location.search).has('thread')).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) => new URL(String(input), window.location.origin).searchParams.get('offset') === '1')).toBe(true);
  });

  it('preserves a direct thread link when a later focused summary page fails', async () => {
    let pageTwoRequests = 0;
    const summary = {
      thread_key: 'page-one-thread', thread_label: 'page-one-thread',
      first_event_timestamp: '2026-07-01T12:00:00Z', latest_event_timestamp: '2026-07-01T12:02:00Z',
      latest_record_id: 'page-one-latest', call_count: 1, session_count: 1,
      input_tokens: 100, cached_input_tokens: 20, uncached_input_tokens: 80, output_tokens: 10,
      reasoning_output_tokens: 0, total_tokens: 110, estimated_cost_usd: 0.01, usage_credits: 0,
      avg_cache_ratio: 0.2, max_context_window_percent: 0.2, max_recommendation_score: 0,
      primary_recommendation: '', call_initiator_summary: 'user x1', archived_call_count: 0,
      updated_at: '2026-07-01T12:02:00Z',
    };
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const offset = Number(new URL(String(input), window.location.origin).searchParams.get('offset'));
      if (offset === 1) {
        pageTwoRequests += 1;
        return new Response('temporary summary failure', { status: 500 });
      }
      return new Response(JSON.stringify({
        schema: 'codex-usage-tracker-threads-v1', rows: [summary], row_count: 1, total_matched_rows: 2,
        limit: 250, offset: 0, has_more: true, next_offset: 1, include_archived: false,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));
    window.history.replaceState(null, '', '/?view=threads&thread=missing-page-two-thread');
    const queryClient = new QueryClient();
    render(<QueryClientProvider client={queryClient}><ThreadsPage
      model={{ ...fixtureModel, contextRuntime: { apiToken: 'thread-token', contextApiEnabled: false, fileMode: false } }}
      globalQuery="" onOpenInvestigator={vi.fn()} onCopyCallLink={vi.fn()}
      contextRuntime={{ apiToken: 'thread-token', contextApiEnabled: false, fileMode: false }}
      focusedEndpointsEnabled onNavigateView={vi.fn()}
    /></QueryClientProvider>);

    await waitFor(() => expect(pageTwoRequests).toBe(2), { timeout: 3_000 });
    await new Promise(resolve => window.setTimeout(resolve, 100));
    expect(pageTwoRequests).toBe(2);
    expect(new URLSearchParams(window.location.search).get('thread')).toBe('missing-page-two-thread');
  });

  it('clears a missing direct thread only after focused summary pages are exhausted', async () => {
    let finalPageReturned = false;
    const summary = (thread: string) => ({
      thread_key: thread, thread_label: thread,
      first_event_timestamp: '2026-07-01T12:00:00Z', latest_event_timestamp: '2026-07-01T12:02:00Z',
      latest_record_id: `${thread}-latest`, call_count: 1, session_count: 1,
      input_tokens: 100, cached_input_tokens: 20, uncached_input_tokens: 80, output_tokens: 10,
      reasoning_output_tokens: 0, total_tokens: 110, estimated_cost_usd: 0.01, usage_credits: 0,
      avg_cache_ratio: 0.2, max_context_window_percent: 0.2, max_recommendation_score: 0,
      primary_recommendation: '', call_initiator_summary: 'user x1', archived_call_count: 0,
      updated_at: '2026-07-01T12:02:00Z',
    });
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const offset = Number(new URL(String(input), window.location.origin).searchParams.get('offset'));
      if (offset === 1) finalPageReturned = true;
      return new Response(JSON.stringify({
        schema: 'codex-usage-tracker-threads-v1', rows: [summary(offset === 0 ? 'page-one-thread' : 'page-two-thread')],
        row_count: 1, total_matched_rows: 2, limit: 250, offset,
        has_more: offset === 0, next_offset: offset === 0 ? 1 : null, include_archived: false,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));
    window.history.replaceState(null, '', '/?view=threads&thread=never-present-thread');
    const queryClient = new QueryClient();
    render(<QueryClientProvider client={queryClient}><ThreadsPage
      model={{ ...fixtureModel, contextRuntime: { apiToken: 'thread-token', contextApiEnabled: false, fileMode: false } }}
      globalQuery="" onOpenInvestigator={vi.fn()} onCopyCallLink={vi.fn()}
      contextRuntime={{ apiToken: 'thread-token', contextApiEnabled: false, fileMode: false }}
      focusedEndpointsEnabled onNavigateView={vi.fn()}
    /></QueryClientProvider>);

    expect(new URLSearchParams(window.location.search).get('thread')).toBe('never-present-thread');
    await waitFor(() => expect(new URLSearchParams(window.location.search).has('thread')).toBe(false));
    expect(finalPageReturned).toBe(true);
    expect(screen.queryByRole('region', { name: /Calls for never-present-thread/i })).not.toBeInTheDocument();
  });

  it('loads additional thread calls only on request and retries a partial result', async () => {
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
    expect(await screen.findByText('2 of 3 calls loaded')).toBeInTheDocument();
    expect(newThreadPageTwoAttempts).toBe(0);
    resolveOldThread?.(callsPage('old-thread', [callRow('old-1', 'old-thread', 'old-model')], 0, false));
    await waitFor(() => expect(screen.queryByText('old-model')).not.toBeInTheDocument());
    expect(screen.getAllByText('new-model-boundary')).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: 'Load 100 more thread calls' }));
    await screen.findByText(/Partial result:/i, {}, { timeout: 3_000 });
    fireEvent.click(await screen.findByRole('button', { name: 'Retry loading thread calls' }));
    await screen.findByText('3 of 3 calls loaded');
    expect(screen.getAllByText('new-model-boundary')).toHaveLength(1);
    expect(screen.getByText('new-model-3')).toBeInTheDocument();
  });

  it('keeps boot calls as a labelled snapshot and retries an initial call failure', async () => {
    let callAttempts = 0;
    const threadName = fixtureModel.threads[0].name;
    const threadKey = fixtureModel.threads[0].threadKey;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), window.location.origin);
      if (url.pathname === '/api/threads') {
        return new Response(JSON.stringify({
          schema: 'codex-usage-tracker-threads-v1',
          rows: [{
            thread_key: threadKey,
            thread_label: threadName,
            first_event_timestamp: '2026-07-01T12:00:00Z',
            latest_event_timestamp: '2026-07-01T12:02:00Z',
            latest_record_id: fixtureModel.calls[0].id,
            call_count: 1,
            session_count: 1,
            input_tokens: 100,
            cached_input_tokens: 20,
            uncached_input_tokens: 80,
            output_tokens: 10,
            reasoning_output_tokens: 0,
            total_tokens: 110,
            estimated_cost_usd: 0.01,
            usage_credits: 0,
            avg_cache_ratio: 0.2,
            max_context_window_percent: 0.2,
            max_recommendation_score: 0,
            primary_recommendation: '',
            call_initiator_summary: 'user x1',
            archived_call_count: 0,
            updated_at: '2026-07-01T12:02:00Z',
          }],
          row_count: 1,
          total_matched_rows: 1,
          limit: 250,
          offset: 0,
          has_more: false,
          next_offset: null,
          include_archived: false,
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      callAttempts += 1;
      if (callAttempts <= 2) return new Response('temporary call failure', { status: 500 });
      return new Response(JSON.stringify({
        schema: 'codex-usage-tracker-thread-calls-v1',
        thread_key: threadKey,
        rows: [],
        row_count: 0,
        total_matched_rows: 0,
        limit: 100,
        offset: 0,
        has_more: false,
        next_offset: null,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);
    window.history.replaceState(null, '', `/?view=threads&thread_key=${encodeURIComponent(threadKey || '')}`);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><ThreadsPage
      model={{ ...fixtureModel, contextRuntime: { apiToken: 'thread-token', contextApiEnabled: false, fileMode: false } }}
      globalQuery="" onOpenInvestigator={vi.fn()} onCopyCallLink={vi.fn()}
      contextRuntime={{ apiToken: 'thread-token', contextApiEnabled: false, fileMode: false }}
      focusedEndpointsEnabled onNavigateView={vi.fn()}
    /></QueryClientProvider>);

    expect(await screen.findByText('Stored snapshot')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Open investigator for thread call/i })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: 'Retry loading thread calls' }));
    await waitFor(() => expect(callAttempts).toBe(3));
    expect(await screen.findByText('No aggregate calls are available for this thread.')).toBeInTheDocument();
    expect(screen.queryByText('Stored snapshot')).not.toBeInTheDocument();
  });
});
