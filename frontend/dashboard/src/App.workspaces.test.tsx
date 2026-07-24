import {
  App,
  describe,
  expect,
  fireEvent,
  installAppTestHooks,
  it,
  render,
  screen,
  within,
} from './test-utils/appTestHarness';

describe('React dashboard secondary workspaces', () => {
  installAppTestHooks();

  it('opens the weekly-first Limits workspace and evaluates URL-backed hypotheses', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /^Limits$/i }));

    expect(screen.getByRole('heading', { name: 'Limits' })).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Weekly local capacity evidence' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('table', {
        name: 'Allowance evidence windows and linked calls',
      }),
    ).toBeInTheDocument();
    expect(screen.getByText('Supporting windows')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Behavior stayed stable' }));
    fireEvent.click(screen.getByRole('button', { name: 'Test weekly claim' }));
    expect(
      screen.getByText('The loaded weekly history cannot test this claim yet'),
    ).toBeInTheDocument();
    expect(new URLSearchParams(window.location.search).get('limit_hypothesis')).toBe(
      'stable',
    );
  });

  it('surfaces legacy source health metadata in Settings', () => {
    window.__CODEX_USAGE_BOOT__ = {
      api_token: 'settings-source-token',
      context_api_enabled: true,
      loaded_row_count: 1,
      total_available_rows: 1,
      limit: 500,
      pricing_configured: true,
      pricing_source: {
        name: 'OpenAI Pricing',
        url: 'https://example.test/pricing',
        fetched_at: '2026-07-01T10:00:00Z',
      },
      pricing_snapshot_warning: 'Pricing snapshot changed since last refresh.',
      allowance_configured: false,
      allowance_source: { name: 'Codex credit rates' },
      allowance_windows: [
        {
          key: 'five_hour',
          label: '5h',
          remaining_percent: 79,
          remaining_credits: 2.75,
          total_credits: 5,
          reset_at: '2026-07-01T16:30:00Z',
        },
        {
          key: 'weekly',
          label: 'Weekly',
          remaining_percent: 33,
          remaining_credits: 9.25,
          total_credits: 28,
          reset_at: '2026-07-04T00:00:00Z',
        },
      ],
      allowance_error: 'missing allowance.json',
      observed_usage: {
        available: true,
        source: 'token_count.rate_limits',
        observed_at: '2026-07-01T10:15:00Z',
        plan_type: 'pro',
        limit_id: 'codex',
        windows: [
          {
            key: 'primary',
            label: '5h',
            used_percent: 21,
            window_minutes: 300,
            resets_at: 1782923400,
          },
          {
            key: 'secondary',
            label: 'Weekly',
            used_percent: 67,
            window_minutes: 10080,
            resets_at: 1783123200,
          },
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
    expect(
      screen.getByText(
        'token_count.rate_limits · plan pro · limit codex · observed 2026-07-01 10:15 UTC',
      ),
    ).toBeInTheDocument();
    const allowancePanel = screen.getByText('Allowance Windows').closest('section');
    expect(allowancePanel).toBeTruthy();
    const observedWeekly = within(allowancePanel as HTMLElement).getByText(
      'Observed Weekly',
    );
    const observedFiveHour = within(allowancePanel as HTMLElement).getByText(
      'Observed 5h',
    );
    const configuredWeekly = within(allowancePanel as HTMLElement).getByText(
      'Configured Weekly',
    );
    const configuredFiveHour = within(allowancePanel as HTMLElement).getByText(
      'Configured 5h',
    );
    expect(
      observedWeekly.compareDocumentPosition(observedFiveHour)
        & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      configuredWeekly.compareDocumentPosition(configuredFiveHour)
        & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.getByText('Observed 5h')).toBeInTheDocument();
    expect(
      screen.getByText('79% remaining · 21% used · resets 2026-07-01 16:30 UTC'),
    ).toBeInTheDocument();
    expect(screen.getByText('Observed Weekly')).toBeInTheDocument();
    expect(
      screen.getByText('33% remaining · 67% used · resets 2026-07-04 00:00 UTC'),
    ).toBeInTheDocument();
    expect(screen.getByText('Configured 5h')).toBeInTheDocument();
    expect(
      screen.getByText(
        '79% remaining · 2.75 cr left · 5 cr total · resets 2026-07-01 16:30 UTC',
      ),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Source Health' }));
    expect(screen.getByRole('heading', { name: 'Source Health' })).toBeInTheDocument();
    expect(
      screen.getByText('Pricing snapshot changed since last refresh.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Config error: missing allowance.json'),
    ).toBeInTheDocument();
    expect(screen.getByText('Rate-card error: rate card stale')).toBeInTheDocument();
    expect(
      screen.getByText(
        '6 parser diagnostics: unknown_model=4, malformed_jsonl=2',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/duplicate_cumulative_total/)).not.toBeInTheDocument();
    expect(
      screen.getByText('strict: cwd redacted, git branch hidden, aliases preserved'),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Content Access' }));
    expect(screen.getByText('Privacy Boundary')).toBeInTheDocument();
    expect(screen.getByText('Payload mode')).toBeInTheDocument();
    expect(screen.getByText('Project metadata')).toBeInTheDocument();
    expect(
      screen.getByText('strict: cwd redacted, git branch hidden, aliases preserved'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Explicit localhost request, selected call only'),
    ).toBeInTheDocument();
    expect(screen.getByText('Local API token present')).toBeInTheDocument();
  });
});
