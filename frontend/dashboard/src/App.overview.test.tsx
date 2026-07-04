import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, within } from './test-utils/appTestHarness';

describe('React dashboard overview workspace', () => {
  installAppTestHooks();

it('direct finding review clears stale call investigator URL state', () => {
window.history.replaceState(
null,
'',
'/?view=overview&record=fixture-call-0&return=calls&mode=full&max_entries=50&max_chars=0&include_tool_output=1&include_compaction_history=true&report=weekly-credits',
);

render(<App />);
fireEvent.click(screen.getByRole('button', { name: /Review finding 1/i }));

const params = new URLSearchParams(window.location.search);
expect(params.get('view')).toBe('investigator');
expect(params.get('finding')).toBe('1');
for (const name of [
'record',
'return',
'mode',
'max_entries',
'max_chars',
'include_tool_output',
'include_compaction_history',
'report',
]) {
expect(params.get(name)).toBeNull();
}
});

  it('uses live aggregate totals cache composition trend charts without homepage presets', () => {
    window.__CODEX_USAGE_BOOT__ = {
      loaded_row_count: 1,
      total_available_rows: 1,
      limit: 500,
      history_scope: 'active',
      observed_usage: {
        available: true,
        source: 'token_count.rate_limits',
        windows: [
          { key: 'primary', label: '5h', used_percent: 21, resets_at: 1782923400 },
          { key: 'weekly', label: 'Weekly', used_percent: 67, window_minutes: 10_080, resets_at: 1783123200 },
        ],
      },
      rows: [
        {
          record_id: 'live-overview-row',
          call_started_at: '2026-07-02T10:00:00Z',
          thread_name: 'live-overview-thread',
          model: 'codex-1',
          effort: 'high',
          input_tokens: 1_000,
          cached_input_tokens: 400,
          output_tokens: 250,
          total_tokens: 1_250,
          estimated_cost_usd: 0.12,
        },
      ],
    };

    render(<App />);

    expect(screen.getByRole('img', { name: '1.25K composition' })).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: '24.83M composition' })).not.toBeInTheDocument();
    expect(within(screen.getByRole('img', { name: 'Tokens line chart' })).getByText('Input')).toBeInTheDocument();
    expect(within(screen.getByRole('img', { name: 'Tokens line chart' })).getByText('Jul 2')).toBeInTheDocument();
    expect(within(screen.getByRole('img', { name: 'USD line chart' })).getByText('Estimated Cost')).toBeInTheDocument();
    expect(screen.getByText('33%')).toBeInTheDocument();
    expect(screen.getByText('Weekly observed usage')).toBeInTheDocument();
    const recentCallsTable = screen.getByRole('table', { name: 'Recent calls' });
    expect(within(recentCallsTable).getByRole('columnheader', { name: /Thread/i })).toHaveClass('sticky-column');
    expect(within(recentCallsTable).getByText('live-overview-thread').closest('td')).toHaveClass('sticky-column');
    expect(screen.getByText('Showing 1 of 1 loaded calls')).toBeInTheDocument();
    expect(screen.getByText('Dashboard rows: 1 of 1 loaded')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Load more recent calls' })).toBeDisabled();
    expect(screen.getAllByRole('button', { name: /Load all rows/i }).length).toBeGreaterThan(0);
    expect(screen.queryByText('32.4%')).not.toBeInTheDocument();
    expect(screen.queryByText('Investigation Presets')).not.toBeInTheDocument();
  });

  it('separates showing loaded recent calls from loading more dashboard rows', () => {
    window.__CODEX_USAGE_BOOT__ = {
      api_token: 'overview-load-token',
      context_api_enabled: true,
      loaded_row_count: 8,
      total_available_rows: 20,
      has_more: true,
      limit: 8,
      history_scope: 'active',
      rows: Array.from({ length: 8 }, (_, index) => ({
        record_id: `overview-load-row-${index}`,
        call_started_at: new Date(Date.UTC(2026, 6, 2, 10, index)).toISOString(),
        thread_name: `overview-load-thread-${index}`,
        model: 'codex-1',
        effort: 'medium',
        input_tokens: 100 + index,
        cached_input_tokens: 40,
        output_tokens: 10,
        total_tokens: 110 + index,
        estimated_cost_usd: 0.01,
      })),
    };

    render(<App />);

    const recentCallsTable = screen.getByRole('table', { name: 'Recent calls' });
    expect(within(recentCallsTable).getByRole('columnheader', { name: /Thread/i })).toHaveClass('sticky-column');
    expect(within(recentCallsTable).getByText('overview-load-thread-0').closest('td')).toHaveClass('sticky-column');
    expect(screen.getByText('Showing 6 of 8 loaded calls')).toBeInTheDocument();
    expect(screen.getByText('Dashboard rows: 8 of 20 loaded')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Load more recent calls' })).toBeEnabled();

    fireEvent.click(screen.getByRole('button', { name: 'Show 2 more loaded calls' }));

    expect(screen.getByText('overview-load-thread-7')).toBeInTheDocument();
    expect(screen.getByText('Showing 8 of 8 loaded calls')).toBeInTheDocument();
  });
});
