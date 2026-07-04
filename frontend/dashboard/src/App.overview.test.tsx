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
    expect(screen.getAllByRole('button', { name: /Load all rows/i }).length).toBeGreaterThan(0);
    expect(screen.queryByText('32.4%')).not.toBeInTheDocument();
    expect(screen.queryByText('Investigation Presets')).not.toBeInTheDocument();
  });
});
