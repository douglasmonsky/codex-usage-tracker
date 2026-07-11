import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, vi, waitFor, within } from './test-utils/appTestHarness';

function mockClipboardWrite(): ReturnType<typeof vi.fn> {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText },
  });
  return writeText;
}

describe('React dashboard secondary workspaces', () => {
  installAppTestHooks();

  it('opens full-page call investigator from cache context thread calls', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Cache And Context/i }));
    expect(screen.getByRole('heading', { name: 'Cache And Context Lab' })).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Cache context threads overview' })).toBeInTheDocument();
    expect(screen.getByText('Efficiency Profile')).toBeInTheDocument();
    expect(screen.getByText('Cache Windows')).toBeInTheDocument();
    expect(screen.getByText('Diagnosis Basis')).toBeInTheDocument();
    expect(screen.getByText('Risk: High cold-resume score')).toBeInTheDocument();
    expect(screen.getByText('Cache: 12.0% hit rate; action threshold below 35%')).toBeInTheDocument();
expect(screen.getByText('Cost: $1.38 per call; inspect threshold above $1.00')).toBeInTheDocument();
expect(screen.getByText('Evidence: 1 loaded calls, no heatmap row')).toBeInTheDocument();
expect(screen.getAllByText('May 26').length).toBeGreaterThan(0);
const heatmap = screen.getByRole('table', { name: 'Cache reuse heatmap' });
expect(within(heatmap).getByRole('columnheader', { name: 'Thread' })).toHaveClass('sticky-column');
expect(within(heatmap).getByRole('rowheader', { name: 'thread-f9c3' })).toHaveClass('sticky-column');
expect(screen.getByText('Thread Calls')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Open investigator for cache thread call thread-9f3a1c codex-1/i }));

    expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
  expect(screen.getByText('thread-9f3a1c / codex-1')).toBeInTheDocument();
  expect(window.location.search).toContain('view=call');
expect(window.location.search).toContain('record=fixture-call-0');
});

it('copies call investigator links from cache context row actions', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText },
  });

  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /Cache And Context/i }));

  fireEvent.click(screen.getByRole('button', { name: /Copy link for latest call in thread-9f3a/i }));
  await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
  const tableUrl = new URL(writeText.mock.calls[0][0]);
  expect(tableUrl.searchParams.get('view')).toBe('call');
  expect(tableUrl.searchParams.get('return')).toBe('cache-context');
  expect(tableUrl.searchParams.get('record')).toBe('fixture-call-0');

  fireEvent.click(screen.getByRole('button', { name: /Copy link for cache thread call thread-9f3a1c codex-1/i }));
  await waitFor(() => expect(writeText).toHaveBeenCalledTimes(2));
  const timelineUrl = new URL(writeText.mock.calls[1][0]);
  expect(timelineUrl.searchParams.get('return')).toBe('cache-context');
  expect(timelineUrl.searchParams.get('record')).toBe('fixture-call-0');
});

it('copies call investigator links from report and investigation evidence lists', async () => {
  const writeText = mockClipboardWrite();

  render(<App />);

fireEvent.click(screen.getByRole('button', { name: /^Reports$/i }));
window.history.replaceState(null, '', '/?view=reports&report=weekly-credits&mode=full&max_entries=50&include_tool_output=1');
fireEvent.click(screen.getByRole('button', { name: /Copy link for report side evidence call thread-6a5b4c codex-1/i }));
  await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
  const reportUrl = new URL(writeText.mock.calls[0][0]);
expect(reportUrl.searchParams.get('view')).toBe('call');
expect(reportUrl.searchParams.get('record')).toBe('fixture-call-6');
expect(reportUrl.searchParams.get('return')).toBe('reports');
expect(reportUrl.searchParams.get('report')).toBe('weekly-credits');
expect(reportUrl.searchParams.has('mode')).toBe(false);
expect(reportUrl.searchParams.has('max_entries')).toBe(false);
expect(reportUrl.searchParams.has('include_tool_output')).toBe(false);

fireEvent.click(screen.getByRole('button', { name: 'Commands' }));
  const investigatorEvidenceRow = screen.getByRole('row', {
    name: /thread-6a5b4c cache-risk 1 425\.65K medium/i,
  });
  fireEvent.click(within(investigatorEvidenceRow).getByRole('button', { name: /Copy call link for cache-risk/i }));
  await waitFor(() => expect(writeText).toHaveBeenCalledTimes(2));
  const investigatorUrl = new URL(writeText.mock.calls[1][0]);
  expect(investigatorUrl.searchParams.get('view')).toBe('call');
  expect(investigatorUrl.searchParams.get('record')).toBe('fixture-call-6');
  expect(investigatorUrl.searchParams.get('return')).toBe('investigator');
});


it('shows an empty cache heatmap state for live snapshots without heatmap rows', () => {
window.__CODEX_USAGE_BOOT__ = {
loaded_row_count: 1,
total_available_rows: 1,
limit: 500,
history_scope: 'active',
rows: [
{
record_id: 'live-cache-row',
call_started_at: '2026-07-02T10:00:00Z',
thread_name: 'live-cache-thread',
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
fireEvent.click(screen.getByRole('button', { name: /Cache And Context/i }));

expect(screen.getByText('No cache heatmap rows in the current aggregate snapshot.')).toBeInTheDocument();
expect(screen.queryByText('May 26')).not.toBeInTheDocument();
});

it('opens full-page call investigator from cache context thread table rows', () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /Cache And Context/i }));

  const table = screen.getByRole('table', { name: 'Cache context threads overview' });
  expect(within(table).getByRole('columnheader', { name: 'Thread' })).toHaveClass('sticky-column');
  expect(within(table).getByText('thread-9f3a').closest('td')).toHaveClass('sticky-column');
  const row = within(table).getByText('thread-9f3a').closest('tr');
  expect(row).not.toBeNull();
  fireEvent.click(row as HTMLTableRowElement);

  expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
  expect(screen.getByText('thread-9f3a1c / codex-1')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Back to Cache And Context/i })).toBeInTheDocument();
  expect(window.location.search).toContain('view=call');
  expect(window.location.search).toContain('record=fixture-call-0');
  expect(window.location.search).toContain('return=cache-context');
});


it('opens the weekly-first Limits workspace and evaluates URL-backed hypotheses', () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Limits$/i }));
    expect(screen.getByRole('heading', { name: 'Limits' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Weekly local capacity evidence' })).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Allowance evidence windows and linked calls' })).toBeInTheDocument();
    expect(screen.getByText('Supporting windows')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Behavior stayed stable' }));
    fireEvent.click(screen.getByRole('button', { name: 'Test weekly claim' }));
    expect(screen.getByText('The loaded weekly history cannot test this claim yet')).toBeInTheDocument();
    expect(new URLSearchParams(window.location.search).get('limit_hypothesis')).toBe('stable');
  });


  it('opens full-page call investigator from report evidence calls', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /^Reports$/i }));
    expect(screen.getByRole('heading', { name: 'Reports' })).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Selected report evidence calls' })).toBeInTheDocument();
    expect(screen.getByText('Research Notes')).toBeInTheDocument();
    expect(screen.getByText('Method')).toBeInTheDocument();
    expect(screen.getByText('Caveat')).toBeInTheDocument();
    expect(screen.getByText(/Rank aggregate calls by estimated Codex credit impact/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Cost Curves/i }));
    expect(screen.getByRole('heading', { name: 'Cost Curves' })).toBeInTheDocument();
    expect(screen.getByText(/Rank aggregate calls by estimated cost/)).toBeInTheDocument();
    window.history.replaceState(
      null,
      '',
      '/?view=reports&report=cost-curves&mode=full&max_entries=50&diagnostic_fact=tool:read',
    );

    fireEvent.click(screen.getByRole('button', { name: /Open investigator for report side evidence call thread-6a5b4c codex-1/i }));

expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
expect(screen.getByText('thread-6a5b4c / codex-1')).toBeInTheDocument();
const params = new URLSearchParams(window.location.search);
expect(params.get('view')).toBe('call');
expect(params.get('record')).toBe('fixture-call-6');
expect(params.get('return')).toBe('reports');
expect(params.get('report')).toBe('cost-curves');
expect(params.has('mode')).toBe(false);
expect(params.has('max_entries')).toBe(false);
expect(params.has('diagnostic_fact')).toBe(false);
});

it('ports Fast Mode Proxy report duration distribution', () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Reports$/i }));

  fireEvent.click(screen.getByRole('button', { name: /Fast Mode Proxy/i }));

  expect(within(screen.getByRole('region', { name: 'Fast Mode Proxy' }))
    .getByText(/4 loaded calls are fast-tagged or low effort/)).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Speed proxy evidence' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Table view' }));
  expect(screen.getByText('Under 5s')).toBeInTheDocument();
  expect(screen.getByText('5-15s')).toBeInTheDocument();
  expect(document.body).toHaveTextContent('Filter fast-tagged and low-effort calls');
  expect(document.body).toHaveTextContent('Aggregate timing cannot distinguish model latency');
});

it('loads live report-pack evidence rows in Reports', async () => {
  window.__CODEX_USAGE_BOOT__ = {
    api_token: 'report-pack-token',
    context_api_enabled: true,
    loaded_row_count: 1,
    total_available_rows: 1,
    limit: 500,
    rows: [
      {
        record_id: 'local-report-row',
        call_started_at: '2026-07-01T10:00:00Z',
        thread_name: 'local-report-thread',
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
    const url = String(input);
    if (!url.includes('/api/reports/pack?')) throw new Error(`Unexpected request: ${url}`);
    expect(init).toEqual(
      expect.objectContaining({
        cache: 'no-store',
        headers: expect.objectContaining({ 'X-Codex-Usage-Token': 'report-pack-token' }),
      }),
    );
    return {
      ok: true,
      json: async () => ({
        schema: 'codex-usage-tracker-reports-pack-v1',
        reports: [
          {
            key: 'usage-drain-model',
            title: 'Usage Drain Model',
            status: 'Ready',
            owner: 'Reports',
            description: 'Server-side report pack evidence.',
          },
        ],
        evidence: {
          'usage-drain-model': {
            rows: [
              {
                record_id: 'server-report-row',
                call_started_at: '2026-07-01T11:00:00Z',
                thread_name: 'server-report-thread',
                model: 'o5',
                effort: 'high',
                input_tokens: 200,
                cached_input_tokens: 20,
                output_tokens: 25,
                total_tokens: 225,
                estimated_cost_usd: 0.02,
                usage_credits: 7,
              },
            ],
            row_count: 1,
            limit: 8,
          },
        },
        row_count: 1,
        total_matched_rows: 1,
        raw_context_included: false,
      }),
    } as Response;
  });
  vi.stubGlobal('fetch', fetchMock);

  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Reports$/i }));

  expect(await screen.findByText('Live report pack ready.')).toBeInTheDocument();
  expect(screen.getByText('Live localhost report pack')).toBeInTheDocument();
  expect(screen.getAllByText('server-report-thread').length).toBeGreaterThan(0);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  expect(String(fetchMock.mock.calls[0][0])).toContain('/api/reports/pack?');
  expect(String(fetchMock.mock.calls[0][0])).toContain('limit=500');
  expect(String(fetchMock.mock.calls[0][0])).toContain('evidence_limit=8');
});


it('surfaces legacy source health metadata in Settings', () => {
  window.__CODEX_USAGE_BOOT__ = {
    api_token: 'settings-source-token',
    context_api_enabled: true,
    loaded_row_count: 1,
    total_available_rows: 1,
    limit: 500,
    pricing_configured: true,
    pricing_source: { name: 'OpenAI Pricing', url: 'https://example.test/pricing', fetched_at: '2026-07-01T10:00:00Z' },
    pricing_snapshot_warning: 'Pricing snapshot changed since last refresh.',
    allowance_configured: false,
    allowance_source: { name: 'Codex credit rates' },
    allowance_windows: [
      { key: 'five_hour', label: '5h', remaining_percent: 79, remaining_credits: 2.75, total_credits: 5, reset_at: '2026-07-01T16:30:00Z' },
      { key: 'weekly', label: 'Weekly', remaining_percent: 33, remaining_credits: 9.25, total_credits: 28, reset_at: '2026-07-04T00:00:00Z' },
    ],
    allowance_error: 'missing allowance.json',
    observed_usage: {
      available: true,
      source: 'token_count.rate_limits',
      observed_at: '2026-07-01T10:15:00Z',
      plan_type: 'pro',
      limit_id: 'codex',
      windows: [
        { key: 'primary', label: '5h', used_percent: 21, window_minutes: 300, resets_at: 1782923400 },
        { key: 'secondary', label: 'Weekly', used_percent: 67, window_minutes: 10080, resets_at: 1783123200 },
      ],
    },
    rate_card_configured: false,
    rate_card_error: 'rate card stale',
    parser_diagnostics: {
      unknown_model: 4,
      malformed_jsonl: 2,
      duplicate_cumulative_total: 99,
    },
    project_metadata_privacy: {
      mode: 'strict',
      cwd_redacted: true,
      git_branch_hidden: true,
      aliases_preserved: true,
    },
    privacy_mode: 'strict',
    rows: [
      {
        record_id: 'settings-source-row',
        call_started_at: '2026-07-01T10:00:00Z',
        thread_name: 'settings-source-thread',
        model: 'o5',
        effort: 'high',
        input_tokens: 120,
        cached_input_tokens: 20,
        output_tokens: 15,
        total_tokens: 135,
        estimated_cost_usd: 0.02,
      },
    ],
  };
  window.history.replaceState(null, '', '/?view=settings');

  render(<App />);

  expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Estimates' }));
  expect(screen.getByText('Allowance Windows')).toBeInTheDocument();
  expect(screen.getByText('token_count.rate_limits · plan pro · limit codex · observed 2026-07-01 10:15 UTC')).toBeInTheDocument();
  const allowancePanel = screen.getByText('Allowance Windows').closest('section') as HTMLElement;
  expect(allowancePanel).toBeTruthy();
  const observedWeekly = within(allowancePanel).getByText('Observed Weekly');
  const observedFiveHour = within(allowancePanel).getByText('Observed 5h');
  const configuredWeekly = within(allowancePanel).getByText('Configured Weekly');
  const configuredFiveHour = within(allowancePanel).getByText('Configured 5h');
  expect(observedWeekly.compareDocumentPosition(observedFiveHour) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(configuredWeekly.compareDocumentPosition(configuredFiveHour) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.getByText('Observed 5h')).toBeInTheDocument();
  expect(screen.getByText('79% remaining · 21% used · resets 2026-07-01 16:30 UTC')).toBeInTheDocument();
  expect(screen.getByText('Observed Weekly')).toBeInTheDocument();
  expect(screen.getByText('33% remaining · 67% used · resets 2026-07-04 00:00 UTC')).toBeInTheDocument();
  expect(screen.getByText('Configured 5h')).toBeInTheDocument();
  expect(screen.getByText('79% remaining · 2.75 cr left · 5 cr total · resets 2026-07-01 16:30 UTC')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Source Health' }));
  expect(screen.getByRole('heading', { name: 'Source Health' })).toBeInTheDocument();
  expect(screen.getByText('Pricing snapshot changed since last refresh.')).toBeInTheDocument();
  expect(screen.getByText('Config error: missing allowance.json')).toBeInTheDocument();
  expect(screen.getByText('Rate-card error: rate card stale')).toBeInTheDocument();
  expect(screen.getByText('6 parser diagnostics: unknown_model=4, malformed_jsonl=2')).toBeInTheDocument();
  expect(screen.queryByText(/duplicate_cumulative_total/)).not.toBeInTheDocument();
  expect(screen.getByText('strict: cwd redacted, git branch hidden, aliases preserved')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Content Access' }));
  expect(screen.getByText('Privacy Boundary')).toBeInTheDocument();
  expect(screen.getByText('Payload mode')).toBeInTheDocument();
  expect(screen.getByText('Project metadata')).toBeInTheDocument();
  expect(screen.getByText('strict: cwd redacted, git branch hidden, aliases preserved')).toBeInTheDocument();
  expect(screen.getByText('Explicit localhost request, selected call only')).toBeInTheDocument();
  expect(screen.getByText('Local API token present')).toBeInTheDocument();
});
});
