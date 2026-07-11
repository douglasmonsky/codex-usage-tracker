import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, vi, within } from './test-utils/appTestHarness';

describe('React dashboard Explore workspaces', () => {
  installAppTestHooks();

  it('moves between tool and file evidence while preserving investigator return state', async () => {
    window.__CODEX_USAGE_BOOT__ = {
      api_token: 'explore-token',
      context_api_enabled: true,
      loaded_row_count: 1,
      total_available_rows: 1,
      rows: [{
        record_id: 'explore-call',
        call_started_at: '2026-07-10T12:00:00Z',
        thread_name: 'explore-thread',
        model: 'codex-1',
        effort: 'high',
        input_tokens: 4_000,
        cached_input_tokens: 1_000,
        output_tokens: 300,
        total_tokens: 4_300,
      }],
    };
    const jsonResponse = (payload: Record<string, unknown>) => ({ ok: true, json: async () => payload }) as Response;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/diagnostics/tools?')) {
        return jsonResponse({
          schema: 'codex-usage-tracker-diagnostic-facts-v1',
          rows: [{
            fact_type: 'tool',
            fact_name: 'rg',
            fact_category: 'search',
            occurrences: 12,
            associated_calls: 1,
            associated_uncached_input_tokens: 3_000,
            associated_total_tokens: 4_300,
            avg_cache_ratio: 0.25,
            largest_call_tokens: 4_300,
            largest_record_id: 'explore-call',
            action_hint: 'Batch repeated searches when the target set is known.',
          }],
          row_count: 1,
          total_matched_rows: 1,
          raw_context_included: false,
        });
      }
      if (url.includes('/api/diagnostics/fact-calls?')) {
        return jsonResponse({
          rows: window.__CODEX_USAGE_BOOT__?.rows,
          row_count: 1,
          total_matched_rows: 1,
          raw_context_included: false,
        });
      }
      if (url.includes('/api/diagnostics/file-reads?')) {
        return jsonResponse({
          status: 'ready',
          top_paths: [{
            path_hash: 'path-hash-a',
            path_label: 'src/search.ts',
            read_events: 7,
            allocated_output_token_sum: 2_400,
            representative_record_id: 'explore-call',
          }],
          raw_context_included: false,
        });
      }
      if (url.includes('/api/diagnostics/file-modifications?')) {
        return jsonResponse({
          status: 'ready',
          top_paths: [{
            path_hash: 'path-hash-a',
            path_label: 'src/search.ts',
            modification_events: 2,
            representative_record_id: 'explore-call',
          }],
          raw_context_included: false,
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.click(within(screen.getByRole('navigation', { name: 'Primary' })).getByRole('button', { name: /^Calls$/i }));
    fireEvent.click(within(screen.getByRole('group', { name: 'Explore workspace' })).getByRole('button', { name: 'Tools' }));

    expect(await screen.findByRole('heading', { name: 'Tools' })).toBeInTheDocument();
    expect(await screen.findByText('Batch repeated searches when the target set is known.')).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Tool evidence' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open largest call for rg' }));

    expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
    expect(window.location.search).toContain('record=explore-call');
    expect(window.location.search).toContain('explore=tools');
    fireEvent.click(screen.getByRole('button', { name: /Back to Calls/i }));
    expect(await screen.findByRole('heading', { name: 'Tools' })).toBeInTheDocument();

    fireEvent.click(within(screen.getByRole('group', { name: 'Explore workspace' })).getByRole('button', { name: 'Files' }));
    expect(await screen.findByRole('heading', { name: 'Files' })).toBeInTheDocument();
    const fileTable = await screen.findByRole('table', { name: 'File evidence' });
    expect(within(fileTable).getByText('src/search.ts')).toBeInTheDocument();
    expect(within(fileTable).getByText('path-hash-a')).toBeInTheDocument();
    expect(window.location.search).toContain('explore=files');
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/api/diagnostics/overview'))).toBe(false);
  });
});
