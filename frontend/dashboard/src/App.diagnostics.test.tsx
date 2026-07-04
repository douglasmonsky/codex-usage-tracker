import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, vi, waitFor, within } from './test-utils/appTestHarness';

describe('React dashboard diagnostics workspace', () => {
  installAppTestHooks();

  it('opens the full-page call investigator from diagnostic evidence calls', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Diagnostics Notebook/i }));

    expect(screen.getByRole('heading', { name: 'Diagnostics Notebook' })).toBeInTheDocument();
    expect(screen.getAllByText('Evidence Calls').length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByRole('button', { name: /Open investigator for diagnostic call/i })[0]);

    expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
    expect(window.location.search).toContain('view=call');
 expect(window.location.search).toContain('record=');
 });

 it('copies call investigator links from diagnostics row actions', async () => {
 const writeText = vi.fn().mockResolvedValue(undefined);
 Object.defineProperty(navigator, 'clipboard', {
 configurable: true,
 value: { writeText },
 });

 render(<App />);

 fireEvent.click(screen.getByRole('button', { name: /Diagnostics Notebook/i }));
 fireEvent.click(screen.getAllByRole('button', { name: /Copy link for diagnostic call/i })[0]);

 await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
 const evidenceUrl = new URL(writeText.mock.calls[0][0]);
 expect(evidenceUrl.searchParams.get('view')).toBe('call');
 expect(evidenceUrl.searchParams.get('return')).toBe('diagnostics');
 expect(evidenceUrl.searchParams.get('record')).toBeTruthy();

 fireEvent.click(screen.getByRole('button', { name: /Copy link for diagnostic snapshot Tool Output file-heavy/i }));
 await waitFor(() => expect(writeText).toHaveBeenCalledTimes(2));
 const snapshotUrl = new URL(writeText.mock.calls[1][0]);
 expect(snapshotUrl.searchParams.get('record')).toBe('fixture-call-6');

 fireEvent.click(screen.getAllByRole('button', { name: /Copy link for largest diagnostic fact call/i })[0]);
 await waitFor(() => expect(writeText).toHaveBeenCalledTimes(3));
 const factUrl = new URL(writeText.mock.calls[2][0]);
 expect(factUrl.searchParams.get('return')).toBe('diagnostics');
 expect(factUrl.searchParams.get('record')).toBeTruthy();
 });


  it('opens the full-page call investigator from structured diagnostic fact calls', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Diagnostics Notebook/i }));

    expect(screen.getByRole('heading', { name: 'Diagnostics Notebook' })).toBeInTheDocument();
    expect(screen.getByText('Structured Diagnostic Facts')).toBeInTheDocument();
expect(screen.getByText(/large_uncached_input/i)).toBeInTheDocument();
expect(screen.getByText('Diagnostic Fact Calls')).toBeInTheDocument();
expect(screen.getByLabelText('Sort diagnostic fact calls')).toBeInTheDocument();
expect(screen.getByRole('button', { name: /Sort diagnostic fact calls ascending/i })).toBeInTheDocument();
expect(screen.getAllByRole('columnheader', { name: 'Input' }).length).toBeGreaterThan(0);
expect(screen.getAllByRole('columnheader', { name: 'Cached' }).length).toBeGreaterThan(0);
expect(screen.getAllByRole('columnheader', { name: 'Uncached' }).length).toBeGreaterThan(0);
expect(screen.getAllByRole('columnheader', { name: 'Output' }).length).toBeGreaterThan(0);
expect(screen.getAllByRole('columnheader', { name: 'Reasoning' }).length).toBeGreaterThan(0);
expect(screen.getAllByRole('columnheader', { name: 'Cache %' }).length).toBeGreaterThan(0);
fireEvent.change(screen.getByLabelText('Sort diagnostic fact calls'), { target: { value: 'cache' } });
fireEvent.click(screen.getByRole('button', { name: /Sort diagnostic fact calls ascending/i }));

fireEvent.click(screen.getAllByLabelText(/Open investigator diagnostic fact call thread-6a5b4c codex-1/i)[0]);

    expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
    expect(screen.getByText('thread-6a5b4c / codex-1')).toBeInTheDocument();
    expect(window.location.search).toContain('view=call');
    expect(window.location.search).toContain('record=fixture-call-6');
  });


  it('reuses live diagnostics cache when returning to the notebook', async () => {
    const usageRow = {
      record_id: 'diag-cache-call',
      call_started_at: '2026-07-02T10:00:00Z',
      thread_name: 'diag-cache-thread',
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
      api_token: 'diagnostic-cache-token',
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
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void init;
      const url = String(input);
      if (url.includes('/api/diagnostics/facts?')) {
        return jsonResponse({
          rows: [
            {
              fact_type: 'cache',
              fact_name: 'large_uncached_input',
              associated_calls: 1,
              associated_uncached_input_tokens: 10_000,
              associated_total_tokens: 12_800,
              avg_cache_ratio: 0.16,
              largest_call_tokens: 12_800,
              largest_record_id: 'diag-cache-call',
            },
          ],
          total_matched_rows: 1,
        });
      }
      if (url.includes('/api/diagnostics/fact-calls?')) {
        return jsonResponse({ rows: [usageRow], row_count: 1, total_matched_rows: 1 });
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
    await screen.findByText('Live facts: 1');
    expect((await screen.findAllByText('diag-cache-thread')).length).toBeGreaterThan(0);
    const firstLoadCount = fetchMock.mock.calls.filter(([input]) => String(input).includes('/api/diagnostics/')).length;
    expect(firstLoadCount).toBe(14);

  fireEvent.click(screen.getByRole('button', { name: /^Overview$/i }));
  fireEvent.click(screen.getByRole('button', { name: /Diagnostics Notebook/i }));

  expect(screen.getByText('Live snapshots: 10')).toBeInTheDocument();
  expect(screen.getByText('Live facts: 1')).toBeInTheDocument();
  expect(screen.queryByText('Loading diagnostic snapshots...')).not.toBeInTheDocument();
  expect(screen.queryByText('Loading top diagnostic facts...')).not.toBeInTheDocument();
  await screen.findByText('Live snapshots: 10');
  await screen.findByText('Live facts: 1');
  expect(fetchMock.mock.calls.filter(([input]) => String(input).includes('/api/diagnostics/'))).toHaveLength(firstLoadCount);
  });


  it('switches live structured diagnostic modules', async () => {
    const usageRow = {
      record_id: 'diag-source-call',
      call_started_at: '2026-07-02T10:00:00Z',
      thread_name: 'diag-source-thread',
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
      api_token: 'diagnostic-source-token',
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
    const factPayload = (fact_type: string, fact_name: string, uncached: number, count = 1, totalMatched = count) =>
      jsonResponse({
        rows: Array.from({ length: count }, (_, index) => ({
          fact_type,
          fact_name: index ? `${fact_name}_${index + 1}` : fact_name,
          fact_category: 'diagnostic',
        occurrences: 3 + index,
        associated_calls: 1,
        associated_input_tokens: uncached + 2_000 + index,
        associated_cached_input_tokens: 2_000 + index,
        associated_uncached_input_tokens: uncached - index,
        associated_output_tokens: 800 + index,
        associated_reasoning_output_tokens: 160 + index,
        associated_total_tokens: uncached + 2_800 - index,
        avg_cache_ratio: 0.16,
        largest_call_tokens: uncached + 3_300 + index * 1_000,
          largest_record_id: 'diag-source-call',
          latest_event_timestamp: '2026-07-02T10:00:00Z',
        })),
        total_matched_rows: totalMatched,
      });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/diagnostics/facts?')) return factPayload('cache', 'large_uncached_input', 10_000, 8, 12);
      if (url.includes('/api/diagnostics/tools?')) return factPayload('tool', 'function_call', 44_000);
      if (url.includes('/api/diagnostics/compactions?')) {
        return factPayload('compaction', 'compacted_history', 18_000);
      }
      if (url.includes('/api/diagnostics/fact-calls?')) {
        return jsonResponse({ rows: [usageRow], row_count: 1, total_matched_rows: 1 });
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

    await screen.findByText('Live facts: 12');
    expect(screen.getByRole('tab', { name: /Top Facts 12/i })).toBeInTheDocument();
    expect(screen.getByText(/8 loaded \/ 12 matched/i)).toBeInTheDocument();
    expect(screen.getByText(/sorted by uncached input descending/i)).toBeInTheDocument();
    expect(screen.getByText('Showing 6 of 8 loaded facts / 12 matched')).toBeInTheDocument();
    expect(screen.getAllByText('Category').length).toBeGreaterThan(0);
    expect(screen.getAllByText('diagnostic').length).toBeGreaterThan(0);
  expect(screen.getAllByText('Occurrences').length).toBeGreaterThan(0);
  expect(screen.getAllByText('Input').length).toBeGreaterThan(0);
  expect(screen.getAllByText('Reasoning').length).toBeGreaterThan(0);
  expect(screen.getAllByText('Largest').length).toBeGreaterThan(0);
  expect(screen.getAllByText('13.3K').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Latest').length).toBeGreaterThan(0);
    expect(screen.queryByText(/large_uncached_input_8/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Show 2 more/i }));
    expect(screen.getByText(/large_uncached_input_8/i)).toBeInTheDocument();
    const factRequestCount = fetchMock.mock.calls.filter(([input]) =>
      String(input).includes('/api/diagnostics/facts?'),
    ).length;

    fireEvent.click(screen.getByRole('button', { name: /^Overview$/i }));
    fireEvent.click(screen.getByRole('button', { name: /Diagnostics Notebook/i }));

    expect(screen.getByText(/large_uncached_input_8/i)).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter(([input]) => String(input).includes('/api/diagnostics/facts?')),
    ).toHaveLength(factRequestCount);
    expect(screen.getAllByRole('option', { name: 'Cached input' }).length).toBeGreaterThan(0);
    expect(screen.getByRole('option', { name: 'Largest call' })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Sort diagnostic facts'), { target: { value: 'largest' } });
  await waitFor(() => expect(screen.getByText(/sorted by largest call descending/i)).toBeInTheDocument());
  await waitFor(() => {
    expect(
      fetchMock.mock.calls.some(([input]) => {
        const url = String(input);
        return url.includes('/api/diagnostics/facts?') && url.includes('sort=largest') && url.includes('direction=desc');
      }),
    ).toBe(true);
  });
  fireEvent.change(screen.getByLabelText('Sort diagnostic facts'), { target: { value: 'occurrences' } });
  await waitFor(() => expect(screen.getAllByText(/large_uncached_input_8/i).length).toBeGreaterThan(0));
  fireEvent.click(screen.getByRole('button', { name: /Sort diagnostic facts ascending/i }));
  await waitFor(() => expect(screen.queryByText(/large_uncached_input_8/i)).not.toBeInTheDocument());
  fireEvent.click(screen.getByRole('button', { name: /Show 2 more/i }));
  expect(screen.getByText(/large_uncached_input_8/i)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Sort diagnostic fact calls'), { target: { value: 'cache' } });
  fireEvent.click(screen.getByRole('button', { name: /Sort diagnostic fact calls ascending/i }));
  expect(screen.getByText(/sorted by cache % ascending/i)).toBeInTheDocument();
  await waitFor(() => {
    expect(
      fetchMock.mock.calls.some(([input]) => {
        const url = String(input);
        return url.includes('/api/diagnostics/fact-calls?') && url.includes('sort=cache') && url.includes('direction=asc');
      }),
    ).toBe(true);
  });
  fireEvent.click(screen.getByRole('tab', { name: /Tools 1/i }));
    expect((await screen.findAllByText(/function_call/i)).length).toBeGreaterThan(0);
    expect(screen.getByText('Live tools: 1')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /Compactions 1/i }));
    expect((await screen.findAllByText(/compacted_history/i)).length).toBeGreaterThan(0);
    expect(screen.getByText('Live compactions: 1')).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/api/diagnostics/tools?'))).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/api/diagnostics/compactions?'))).toBe(true);
  });


  it('opens full-page call investigator from investigator evidence table rows', () => {
    render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Investigator$/i }));
  expect(screen.getByRole('heading', { name: 'Investigator Workbench' })).toBeInTheDocument();
  expect(screen.getByText('Evidence Profile')).toBeInTheDocument();
  expect(screen.getByText('Evidence Basis')).toBeInTheDocument();
  expect(screen.getByText('Selection: highest-impact calls across loaded threads')).toBeInTheDocument();
  expect(screen.getByText('Order: total tokens descending, then estimated cost')).toBeInTheDocument();
  expect(screen.getByText('Limit: top 8 loaded aggregate rows')).toBeInTheDocument();
  expect(screen.getAllByRole('button', { name: /Open investigator for workbench call/i }).length).toBeGreaterThan(0);

    const table = screen.getByRole('table', { name: 'Investigator evidence calls' });
    const firstRow = table.querySelector('tbody tr');
    expect(firstRow).not.toBeNull();
    fireEvent.doubleClick(firstRow as HTMLTableRowElement);

    expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
    expect(screen.getByText('thread-6a5b4c / codex-1')).toBeInTheDocument();
    expect(window.location.search).toContain('view=call');
    expect(window.location.search).toContain('record=fixture-call-6');
  });


  it('loads more diagnostic fact calls from the live drilldown', async () => {
    const usageRows = Array.from({ length: 10 }, (_, index) => ({
      record_id: `diag-page-call-${index}`,
      call_started_at: `2026-07-02T10:${String(index).padStart(2, '0')}:00Z`,
      thread_name: `diag-page-thread-${index}`,
      model: 'codex-1',
      effort: 'high',
      input_tokens: 12_000 + index,
      cached_input_tokens: 2_000,
      uncached_input_tokens: 10_000 + index,
      output_tokens: 800,
      total_tokens: 12_800 + index,
      estimated_cost_usd: 0.25,
    }));
    window.__CODEX_USAGE_BOOT__ = {
      api_token: 'diagnostic-fact-paging-token',
      context_api_enabled: true,
      loaded_row_count: 1,
      total_available_rows: 1,
      rows: [usageRows[0]],
    };
    const jsonResponse = (payload: Record<string, unknown>) =>
      ({
        ok: true,
        json: async () => payload,
      }) as Response;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/diagnostics/facts?')) {
        return jsonResponse({
          rows: [
            {
              fact_type: 'cache',
              fact_name: 'large_uncached_input',
              associated_calls: 10,
              associated_uncached_input_tokens: 100_000,
              associated_total_tokens: 128_000,
              avg_cache_ratio: 0.16,
              largest_call_tokens: 12_809,
              largest_record_id: 'diag-page-call-9',
            },
          ],
          total_matched_rows: 1,
        });
      }
      if (url.includes('/api/diagnostics/fact-calls?')) {
        const params = new URL(`http://local.test${url}`).searchParams;
        const offset = Number(params.get('offset') ?? 0);
        const limit = Number(params.get('limit') ?? 8);
        return jsonResponse({
          rows: usageRows.slice(offset, offset + limit),
          row_count: Math.min(limit, usageRows.length - offset),
          total_matched_rows: usageRows.length,
          truncated: offset + limit < usageRows.length,
        });
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

    expect((await screen.findAllByText('Showing 8 of 10 calls')).length).toBeGreaterThan(0);
    expect(screen.getByText('diag-page-thread-7')).toBeInTheDocument();
    expect(screen.queryByText('diag-page-thread-8')).not.toBeInTheDocument();
    const factCallsPanel = screen.getByText('Diagnostic Fact Calls').closest('section') as HTMLElement;

    fireEvent.click(within(factCallsPanel).getByRole('button', { name: /^Load more$/i }));

    expect(await screen.findByText('diag-page-thread-9')).toBeInTheDocument();
    expect(screen.getAllByText('Showing 10 of 10 calls').length).toBeGreaterThan(0);
    expect(within(factCallsPanel).queryByRole('button', { name: /^Load more$/i })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/api/diagnostics/fact-calls?') && String(input).includes('offset=8'))).toBe(
      true,
    );
    const factCallRequestCount = fetchMock.mock.calls.filter(([input]) =>
      String(input).includes('/api/diagnostics/fact-calls?'),
    ).length;

    fireEvent.click(screen.getByRole('button', { name: /^Overview$/i }));
    fireEvent.click(screen.getByRole('button', { name: /Diagnostics Notebook/i }));

    expect(screen.getAllByText('Showing 10 of 10 calls').length).toBeGreaterThan(0);
    expect(screen.getByText('diag-page-thread-9')).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter(([input]) => String(input).includes('/api/diagnostics/fact-calls?')),
    ).toHaveLength(factCallRequestCount);
  });
});
