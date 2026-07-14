import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, vi, within } from './test-utils/appTestHarness';

describe('React dashboard diagnostics snapshot matrix', () => {
  installAppTestHooks();

 it('opens full-page call investigator from diagnostic snapshot rows', () => {
 render(<App />);
 fireEvent.click(screen.getByRole('button', { name: /Diagnostics Notebook/i }));

 fireEvent.click(
 screen.getByRole('button', { name: /Open investigator for diagnostic snapshot Tool Output file-heavy/i }),
 );

 expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
 expect(window.location.search).toContain('view=call');
 expect(window.location.search).toContain('record=fixture-call-6');
 });

  it('reloads one diagnostic snapshot without refetching the full notebook', async () => {
    const usageRow = {
      record_id: 'diag-refresh-call',
      call_started_at: '2026-07-02T10:00:00Z',
      thread_name: 'diag-refresh-thread',
      model: 'codex-1',
      effort: 'high',
      input_tokens: 12_000,
      cached_input_tokens: 2_000,
      uncached_input_tokens: 10_000,
      output_tokens: 800,
      total_tokens: 12_800,
      estimated_cost_usd: 0.25,
    };
    window.__CODEX_USAGE_BOOT__ = {
      api_token: 'diagnostic-refresh-token',
      context_api_enabled: true,
      loaded_row_count: 1,
      total_available_rows: 1,
      rows: [usageRow],
    };
    const jsonResponse = (payload: Record<string, unknown>) =>
      ({
        ok: true,
        json: async () => payload,
      }) as Response;
    const overviewPayload = (usageRows: number, totalTokens: number, refreshed = false) => ({
      status: 'ready',
      refreshed,
      snapshot: { computed_at: refreshed ? '2026-07-03T12:00:00Z' : '2026-07-02T10:00:00Z' },
      overview: {
        usage_rows: usageRows,
        total_tokens: totalTokens,
        cache_ratio: 0.25,
        thread_count: 2,
        model_count: 1,
      },
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/api/diagnostics/facts?')) {
        return jsonResponse({ rows: [], total_matched_rows: 0 });
      }
      if (url.includes('/api/diagnostics/overview/refresh')) {
        expect(init).toEqual(expect.objectContaining({ method: 'POST' }));
        return jsonResponse(overviewPayload(33, 44_000, true));
      }
      if (url.includes('/api/diagnostics/overview?')) {
        return jsonResponse(overviewPayload(11, 22_000));
      }
      if (url.includes('/api/diagnostics/')) {
        return jsonResponse({
          status: 'ready',
          refreshed: false,
          snapshot: { computed_at: '2026-07-02T10:00:00Z' },
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Diagnostics Notebook/i }));

    await screen.findByText('Live snapshots: 10');
    const overviewCard = screen.getByText('Distinct aggregate thread labels').closest('article') as HTMLElement;
    expect(within(overviewCard).getByText('22K')).toBeInTheDocument();
    const initialFullNotebookCalls = fetchMock.mock.calls.filter(
      ([input]) => String(input).includes('/api/diagnostics/') && !String(input).includes('/refresh'),
    ).length;

    fireEvent.click(screen.getByRole('button', { name: /Reload Overview diagnostic snapshot/i }));

    expect(await within(overviewCard).findByText('44K')).toBeInTheDocument();
    expect(within(overviewCard).getByText('33')).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([input]) => String(input).includes('/api/diagnostics/overview/refresh'))).toHaveLength(1);
    expect(
      fetchMock.mock.calls.filter(([input]) => String(input).includes('/api/diagnostics/') && !String(input).includes('/refresh')),
    ).toHaveLength(initialFullNotebookCalls);
  });

  it('keeps live diagnostic snapshots visible while full refresh is pending', async () => {
    const usageRow = {
      record_id: 'diag-refresh-pending-call',
      call_started_at: '2026-07-02T10:00:00Z',
      thread_name: 'diag-refresh-pending-thread',
      model: 'codex-1',
      effort: 'high',
      input_tokens: 12_000,
      cached_input_tokens: 2_000,
      uncached_input_tokens: 10_000,
      output_tokens: 800,
      total_tokens: 12_800,
      estimated_cost_usd: 0.25,
    };
    window.__CODEX_USAGE_BOOT__ = {
      api_token: 'diagnostic-refresh-pending-token',
      context_api_enabled: true,
      loaded_row_count: 1,
      total_available_rows: 1,
      rows: [usageRow],
    };
    const jsonResponse = (payload: Record<string, unknown>) =>
      ({
        ok: true,
        json: async () => payload,
      }) as Response;
    const overviewPayload = (usageRows: number, totalTokens: number, refreshed = false) => ({
      status: 'ready',
      refreshed,
      snapshot: { computed_at: refreshed ? '2026-07-03T12:00:00Z' : '2026-07-02T10:00:00Z' },
      overview: {
        usage_rows: usageRows,
        total_tokens: totalTokens,
        cache_ratio: 0.25,
        thread_count: 2,
        model_count: 1,
      },
    });
    let resolveRefreshStatus!: (response: Response) => void;
    const refreshStatusPromise = new Promise<Response>(resolve => {
      resolveRefreshStatus = resolve;
    });
    let refreshCompleted = false;
    const refreshJob = (status: 'running' | 'completed', completed: number) => ({
      schema: 'codex-usage-tracker-analysis-job-v1',
      job_id: 'diagnostic-refresh-test',
      job_kind: 'diagnostic-refresh',
      status,
      stage: status === 'completed' ? 'complete' : 'persisting_snapshots',
      progress: {
        completed_units: completed,
        total_units: 10,
        percent: completed * 10,
        current_unit: status === 'completed' ? null : 'commands',
      },
      error: null,
      next: status === 'completed'
        ? { action: 'reload_persisted_results' }
        : { action: 'poll', job_id: 'diagnostic-refresh-test', poll_after_ms: 0 },
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/diagnostics/refresh?')) {
        return jsonResponse(refreshJob('running', 2));
      }
      if (url.includes('/api/diagnostics/refresh/status?')) {
        return refreshStatusPromise;
      }
      if (
        url.includes('/api/diagnostics/facts?') ||
        url.includes('/api/diagnostics/tools?') ||
        url.includes('/api/diagnostics/compactions?')
      ) {
        return jsonResponse({ rows: [], total_matched_rows: 0 });
      }
      if (url.includes('/api/diagnostics/fact-calls?')) {
        return jsonResponse({ rows: [], row_count: 0, total_matched_rows: 0 });
      }
      if (url.includes('/api/diagnostics/overview?')) {
        return jsonResponse(refreshCompleted ? overviewPayload(44, 88_000, true) : overviewPayload(11, 22_000));
      }
      if (url.includes('/api/diagnostics/')) {
        return jsonResponse({ status: 'ready', refreshed: false, snapshot: { computed_at: '2026-07-02T10:00:00Z' } });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Diagnostics Notebook/i }));
    await screen.findByText('Live snapshots: 10');

    const overviewCard = screen.getByText('Distinct aggregate thread labels').closest('article') as HTMLElement;
    expect(within(overviewCard).getByText('22K')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^Refresh snapshots$/i }));

    expect(screen.getByText('Refreshing diagnostic snapshots...')).toBeInTheDocument();
    expect(within(overviewCard).getByText('22K')).toBeInTheDocument();
    const progress = await screen.findByRole('progressbar', { name: /Refreshing diagnostic snapshots/i });
    expect(progress).toHaveAttribute('aria-valuenow', '2');
    expect(progress).toHaveAttribute('aria-valuemax', '10');

    refreshCompleted = true;
    resolveRefreshStatus(jsonResponse(refreshJob('completed', 10)));
    expect(await within(overviewCard).findByText('88K')).toBeInTheDocument();
  });

  it('opens the full-page call investigator from diagnostics snapshot matrix rows', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Diagnostics Notebook/i }));

    expect(screen.getByRole('heading', { name: 'Diagnostics Notebook' })).toBeInTheDocument();
    expect(screen.getByText('Diagnostics Snapshot Matrix')).toBeInTheDocument();
    expect(screen.getByText('Tool Output')).toBeInTheDocument();
    expect(screen.getByText('What Is Driving Usage?')).toBeInTheDocument();
    expect(screen.getByText('Concentration')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Open investigator for diagnostic snapshot Concentration thread-6a5b4c/i }));

    expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
    expect(screen.getByText('thread-6a5b4c / codex-1')).toBeInTheDocument();
    expect(window.location.search).toContain('view=call');
    expect(window.location.search).toContain('record=fixture-call-6');
  });

  it('expands compact diagnostic snapshot cards and keeps hidden row actions available', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Diagnostics Notebook/i }));

    const toolOutputCard = screen.getByRole('heading', { name: 'Tool Output' }).closest('article');
    if (!toolOutputCard) throw new Error('Tool Output diagnostic card not found');
    expect(within(toolOutputCard).getByText('Showing 4 of 8 rows')).toBeInTheDocument();
    expect(within(toolOutputCard).queryByText('fast')).not.toBeInTheDocument();

    fireEvent.click(within(toolOutputCard).getByRole('button', { name: 'Show 4 more' }));

    expect(within(toolOutputCard).getByText('Showing all 8 rows')).toBeInTheDocument();
    expect(within(toolOutputCard).getByText('fast')).toBeInTheDocument();
    fireEvent.click(within(toolOutputCard).getByRole('button', { name: /Open investigator for diagnostic snapshot Tool Output fast/i }));
    expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
    expect(window.location.search).toContain('record=fixture-call-7');
  });

  it('renders command child breakdowns from live diagnostic snapshots', async () => {
    window.__CODEX_USAGE_BOOT__ = {
      api_token: 'diagnostic-command-children-token',
      context_api_enabled: true,
      loaded_row_count: 0,
      total_available_rows: 0,
      rows: [],
    };
    const jsonResponse = (payload: Record<string, unknown>) =>
      ({
        ok: true,
        json: async () => payload,
      }) as Response;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (
        url.includes('/api/diagnostics/facts?') ||
        url.includes('/api/diagnostics/tools?') ||
        url.includes('/api/diagnostics/compactions?')
      ) {
        return jsonResponse({ rows: [], total_matched_rows: 0 });
      }
      if (url.includes('/api/diagnostics/fact-calls?')) {
        return jsonResponse({ rows: [], row_count: 0, total_matched_rows: 0 });
      }
      if (url.includes('/api/diagnostics/commands?')) {
        return jsonResponse({
          status: 'ready',
          snapshot: { computed_at: '2026-07-03T12:00:00Z' },
          summary: { shell_function_calls: 5, command_root_count: 1, missing_command: 0 },
          commands: [
            {
              root: 'git',
              total: 5,
              children: [
                { child: 'status', count: 3 },
                { child: 'diff', count: 2 },
              ],
            },
          ],
        });
      }
      if (url.includes('/api/diagnostics/')) {
        return jsonResponse({ status: 'ready', snapshot: { computed_at: '2026-07-03T12:00:00Z' } });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Diagnostics Notebook/i }));
    await screen.findByText('Live snapshots: 10');

    const commandsCard = screen.getByRole('heading', { name: 'Commands' }).closest('article');
    if (!commandsCard) throw new Error('Commands diagnostic card not found');
    expect(within(commandsCard).getByText('2 child commands')).toBeInTheDocument();
    fireEvent.click(within(commandsCard).getByText('Show 2 child commands'));

    expect(within(commandsCard).getByText('status')).toBeInTheDocument();
    expect(within(commandsCard).getByText('diff')).toBeInTheDocument();
  });
});
