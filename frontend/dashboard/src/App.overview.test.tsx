import { vi } from 'vitest';
import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, waitFor, within } from './test-utils/appTestHarness';

vi.mock('./visualization/renderer/echartsRenderer', () => ({
  createEChartsVisualizationRenderer: vi.fn(async () => ({
    dispose: vi.fn(),
    exportSvgDataUrl: vi.fn(() => ''),
    resize: vi.fn(),
    select: vi.fn(),
    setSpec: vi.fn(),
  })),
}));

describe('React dashboard overview workspace', () => {
  installAppTestHooks();

  it('uses loaded totals, focused visualization contracts, and no homepage presets', async () => {
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

    const metrics = screen.getByLabelText('Loaded usage metrics');
    expect(within(metrics).getByText('1.25K')).toBeInTheDocument();
    expect(within(metrics).getByText('Cached')).toBeInTheDocument();
    expect(within(metrics).getByText('400')).toBeInTheDocument();
    expect(within(metrics).getByText('Uncached')).toBeInTheDocument();
    expect(within(metrics).getByText('600')).toBeInTheDocument();
    expect(within(metrics).getByText('Output')).toBeInTheDocument();
    expect(within(metrics).getByText('250')).toBeInTheDocument();
    expect(within(metrics).getByText('Reasoning')).toBeInTheDocument();
    expect(within(metrics).getByText('40.0%')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Recent token movement' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Loaded token accounting' })).toBeInTheDocument();
    const recentCallsTable = screen.getByRole('table', { name: 'Overview calls' });
    const recentCallsSection = screen.getByRole('region', { name: 'Calls' });
    expect(within(recentCallsTable).getByRole('columnheader', { name: /Thread/i })).toBeInTheDocument();
    expect(within(recentCallsTable).getByRole('button', { name: 'Sort by Input Tokens' })).toBeInTheDocument();
    expect(within(recentCallsTable).getByRole('button', { name: 'Sort by Total Tokens' })).toBeInTheDocument();
    expect(within(recentCallsTable).getByRole('button', { name: 'Sort by Codex Credits' })).toBeInTheDocument();
    await waitFor(() => expect(within(recentCallsTable).getByText('live-overview-thread')).toBeInTheDocument());
    expect(screen.getByText('Loaded 1 of 1 available calls')).toBeInTheDocument();
    expect(within(recentCallsSection).getByRole('button', { name: 'Load more recent calls' })).toBeDisabled();
    expect(screen.getAllByRole('button', { name: /Browse all calls/i }).length).toBeGreaterThan(0);
    expect(screen.queryByText('32.4%')).not.toBeInTheDocument();
    expect(screen.queryByText('Investigation Presets')).not.toBeInTheDocument();
  });

  it('virtualizes loaded recent calls and opens a row in Call Investigator', async () => {
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

    const recentCallsTable = screen.getByRole('table', { name: 'Overview calls' });
    const recentCallsSection = screen.getByRole('region', { name: 'Calls' });
    expect(recentCallsTable).toHaveAttribute('aria-rowcount', '9');
    await waitFor(() => expect(within(recentCallsTable).getByText('overview-load-thread-0')).toBeInTheDocument());
    expect(screen.getByText('Loaded 8 of 20 available calls')).toBeInTheDocument();
    expect(within(recentCallsSection).getByRole('button', { name: 'Load more recent calls' })).toBeEnabled();

    fireEvent.click(within(recentCallsTable).getByText('overview-load-thread-0'));

    const params = new URLSearchParams(window.location.search);
    expect(params.get('view')).toBe('call');
    expect(params.get('record')).toBe('overview-load-row-0');
  });
});
