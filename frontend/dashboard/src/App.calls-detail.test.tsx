import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, within } from './test-utils/appTestHarness';

describe('React dashboard calls drilldown and investigator', () => {
  installAppTestHooks();

  it('filters and drills into calls through detail tabs', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /^Calls$/i }));
    expect(screen.getByRole('heading', { name: 'Call Drill-Down' })).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('Search calls, cwd, projects, models...'), {
      target: { value: 'thread-3c8d4e' },
    });

    expect(screen.getByText('thread-3c8d4e')).toBeInTheDocument();
    expect(screen.queryByText('thread-9f3a1c')).not.toBeInTheDocument();

  const row = screen.getByText('thread-3c8d4e').closest('tr');
  expect(row).not.toBeNull();
  fireEvent.mouseEnter(row as HTMLTableRowElement);
expect(screen.getByText('thread-3c8d4e / o3')).toBeInTheDocument();
expect(screen.getAllByText('Uncached input').length).toBeGreaterThan(0);
expect(screen.getByRole('tab', { name: /Summary/i })).toHaveAttribute('aria-selected', 'true');
const callDecision = screen.getByText('Call Decision').closest('.call-decision-card');
expect(callDecision).not.toBeNull();
const callDecisionPanel = within(callDecision as HTMLElement);
expect(callDecisionPanel.getByText('Pricing status')).toBeInTheDocument();
expect(callDecisionPanel.getByText('Next action')).toBeInTheDocument();
    expect(callDecisionPanel.getByText('Why flagged')).toBeInTheDocument();
    expect(callDecisionPanel.getByText('Allowance impact')).toBeInTheDocument();
    expect(callDecisionPanel.getByText('Context use')).toBeInTheDocument();
    const callSource = screen.getByText('Call Source').closest('.call-source-card');
    expect(callSource).not.toBeNull();
    const callSourcePanel = within(callSource as HTMLElement);
    expect(callSourcePanel.getByText('Project tags')).toBeInTheDocument();
    expect(callSourcePanel.getByText('dashboard, rewrite')).toBeInTheDocument();
    expect(callSourcePanel.getByText('Thread attachment')).toBeInTheDocument();
    expect(callSourcePanel.getByText('direct active thread')).toBeInTheDocument();
    expect(callSourcePanel.getByText('Thread source')).toBeInTheDocument();
    expect(callSourcePanel.getAllByText('user').length).toBeGreaterThan(0);
    expect(callSourcePanel.getByText('Turn')).toBeInTheDocument();
    expect(callSourcePanel.getByText('fixture-turn-2')).toBeInTheDocument();
    expect(callSourcePanel.getByText('Credit note')).toBeInTheDocument();
    expect(callSourcePanel.getByText('fixture inherited rate card')).toBeInTheDocument();
    expect(callSourcePanel.getByText('Source line')).toBeInTheDocument();
    expect(callSourcePanel.getAllByText('fixture-thread-2.jsonl:122').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('tab', { name: /Tokens/i }));
    expect(screen.getByText('Last call input')).toBeInTheDocument();
expect(screen.getByText('Last call total')).toBeInTheDocument();
expect(screen.getByText('Session cumulative')).toBeInTheDocument();
expect(screen.getByText('Pricing model')).toBeInTheDocument();
expect(screen.getByText('o3-pricing')).toBeInTheDocument();
expect(screen.getByText('Credit model')).toBeInTheDocument();
expect(screen.getByText('o3-credits')).toBeInTheDocument();
expect(screen.getByText('Credit source')).toBeInTheDocument();
expect(screen.getByText('fixture-rate-card')).toBeInTheDocument();
    expect(screen.getByText('Credit tier')).toBeInTheDocument();
    expect(screen.getByText('standard')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: /Cache/i }));
    expect(screen.getByText('Cache Accounting Delta')).toBeInTheDocument();
    expect(screen.getByText('Partial cache miss')).toBeInTheDocument();
    expect(screen.getByText('Some prefix reused cache, but a meaningful share of input was fresh or reserialized.')).toBeInTheDocument();
    expect(screen.getByText('Next: Use loaded evidence if aggregate totals are not enough to understand this isolated call.')).toBeInTheDocument();
    expect(screen.getByText('No previous aggregate call available for cache delta accounting.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: /Thread/i }));
expect(screen.getByText('Call Narrative')).toBeInTheDocument();
expect(screen.getByText('Initiated by')).toBeInTheDocument();
expect(screen.getAllByText('tool').length).toBeGreaterThan(0);
expect(screen.getByText('Initiator reason')).toBeInTheDocument();
expect(screen.getByText('tool-driven continuation')).toBeInTheDocument();
expect(screen.getByText('Previous gap')).toBeInTheDocument();
expect(screen.getAllByText('14m 0s').length).toBeGreaterThan(0);
expect(screen.getByText('Source line')).toBeInTheDocument();
expect(screen.getByText('fixture-thread-2.jsonl:122')).toBeInTheDocument();

fireEvent.click(screen.getByRole('tab', { name: /Evidence/i }));
expect(screen.getByText('Raw context is gated')).toBeInTheDocument();
expect(screen.getByText(/localhost dashboard server API token/i)).toBeInTheDocument();
});

it('shows legacy calls date range status and invalid range feedback', () => {
render(<App />);
fireEvent.click(screen.getByRole('button', { name: /^Calls$/i }));

expect(screen.queryByText(/Custom:/i)).not.toBeInTheDocument();

fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-07-01' } });
expect(screen.getByLabelText('Time filter')).toHaveValue('custom');
const openEndedStatus = screen.getByText('Custom: from 2026-07-01');
expect(openEndedStatus).toHaveAttribute('data-state', 'active');

fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-07-03' } });
expect(screen.getByText('Custom: 2026-07-01 to 2026-07-03')).toHaveAttribute('data-state', 'active');

fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-07-04' } });
expect(screen.getByText('Invalid date range')).toHaveAttribute('data-state', 'error');
expect(screen.getByText('No rows match current filters.')).toBeInTheDocument();
});

it('toggles the calls detail panel like the legacy dashboard', () => {
render(<App />);
fireEvent.click(screen.getByRole('button', { name: /^Calls$/i }));

expect(screen.getByRole('heading', { name: 'Call Drill-Down' })).toBeInTheDocument();
const hideButton = screen.getByRole('button', { name: /Hide details/i });
expect(hideButton).toHaveAttribute('aria-expanded', 'true');

fireEvent.click(hideButton);

expect(screen.queryByRole('heading', { name: 'Call Drill-Down' })).not.toBeInTheDocument();
expect(window.sessionStorage.getItem('codexUsageDetailPanel')).toBe('collapsed');
expect(screen.getByRole('table', { name: 'Model calls' })).toBeInTheDocument();

const showButton = screen.getByRole('button', { name: /Call Details/i });
expect(showButton).toHaveAttribute('aria-expanded', 'false');
fireEvent.click(showButton);

expect(screen.getByRole('heading', { name: 'Call Drill-Down' })).toBeInTheDocument();
expect(window.sessionStorage.getItem('codexUsageDetailPanel')).toBe('expanded');
});

it('hydrates calls detail panel toggle labels from dashboard i18n payload', () => {
  window.__CODEX_USAGE_BOOT__ = {
    language: 'es',
    language_direction: 'ltr',
    available_languages: [
      { code: 'en', english_name: 'English', native_name: 'English', dir: 'ltr' },
      { code: 'es', english_name: 'Spanish', native_name: 'Español', dir: 'ltr' },
    ],
    translation_catalog: {
        es: {
          'button.hide_details': 'Ocultar detalles',
          'dashboard.call_details': 'Detalles de la llamada',
          'dashboard.model_calls': 'Llamadas modelo',
          'detail.next_action': 'Siguiente acción',
        },
    },
    loaded_row_count: 1,
    rows: [
      {
        record_id: 'detail-i18n-row',
        call_started_at: '2026-07-01T12:00:00Z',
        thread_name: 'detail-i18n-thread',
        model: 'codex-1',
        effort: 'high',
        input_tokens: 1000,
        cached_input_tokens: 500,
        output_tokens: 100,
        total_tokens: 1100,
        estimated_cost_usd: 0.1,
      },
    ],
  };

  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Calls$/i }));

  expect(screen.getByText('Llamadas modelo')).toBeInTheDocument();
  expect(screen.getByRole('table', { name: 'Llamadas modelo' })).toBeInTheDocument();
  expect(screen.getByText('Siguiente acción')).toBeInTheDocument();
  const hideButton = screen.getByRole('button', { name: /Ocultar detalles/i });
  expect(hideButton).toHaveAttribute('aria-expanded', 'true');
  fireEvent.click(hideButton);
  expect(screen.getByRole('button', { name: /Detalles de la llamada/i })).toHaveAttribute('aria-expanded', 'false');
});

it('updates the calls drill-down when hovering model-call rows', () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Calls$/i }));

  expect(screen.getByText('thread-9f3a1c / codex-1')).toBeInTheDocument();
  const row = screen.getByText('thread-7b2e91').closest('tr');
  expect(row).not.toBeNull();

  fireEvent.mouseEnter(row as HTMLTableRowElement);

  expect(screen.getByText('thread-7b2e91 / o4-mini')).toBeInTheDocument();
  expect(screen.queryByText('thread-9f3a1c / codex-1')).not.toBeInTheDocument();
});

it('sorts table columns through accessible header controls', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /^Calls$/i }));

    const sortButton = screen.getByRole('button', { name: 'Sort by Est. Cost' });
    fireEvent.click(sortButton);
    expect(sortButton.closest('th')).toHaveAttribute('aria-sort', 'descending');
  });

  it('toggles call and thread columns while keeping identity columns locked', () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Calls$/i }));
  const callsTable = screen.getByRole('table', { name: 'Model calls' });
  expect(within(callsTable).getByRole('button', { name: /Sort by Total Tokens/i })).toBeInTheDocument();
  expect(within(callsTable).getByRole('button', { name: /Sort by Cached Input/i })).toBeInTheDocument();
  expect(within(callsTable).getByRole('button', { name: /Sort by Uncached Input/i })).toBeInTheDocument();
  expect(within(callsTable).getByRole('button', { name: /Sort by Reasoning Output/i })).toBeInTheDocument();
  expect(within(callsTable).getByRole('button', { name: /Sort by Codex Credits/i })).toBeInTheDocument();
  expect(within(callsTable).getByRole('button', { name: /Sort by Context %/i })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Columns/i }));
  expect(screen.getByRole('checkbox', { name: 'Thread' })).toBeDisabled();
  expect(screen.getByRole('checkbox', { name: 'Investigate' })).toBeDisabled();
  expect(screen.getByRole('checkbox', { name: 'Reasoning Output' })).toBeChecked();
  fireEvent.keyDown(document, { key: 'Escape' });
  expect(screen.queryByText('Calls columns')).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Columns/i }));
  fireEvent.click(screen.getByRole('checkbox', { name: 'Reasoning Output' }));
  expect(screen.queryByRole('columnheader', { name: /Reasoning Output/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^Threads$/i }));
    const threadsTable = screen.getByRole('table', { name: 'Thread leaderboard' });
    expect(within(threadsTable).getByRole('button', { name: /Sort by Latest/i })).toBeInTheDocument();
    expect(within(threadsTable).getByRole('button', { name: /Sort by Avg Gap/i })).toBeInTheDocument();
    expect(within(threadsTable).getByRole('button', { name: /Sort by Initiated/i })).toBeInTheDocument();
    expect(within(threadsTable).getByRole('button', { name: /Sort by Reasoning Output/i })).toBeInTheDocument();
    expect(screen.getByText('Cached / uncached input')).toBeInTheDocument();
    expect(screen.getByText('Peak context')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Columns/i }));
    expect(screen.getByRole('checkbox', { name: 'Thread' })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: 'Investigate' })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: 'Reasoning Output' })).toBeChecked();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Reasoning Output' }));
    expect(screen.queryByRole('columnheader', { name: /Reasoning Output/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Productivity' }));
    expect(screen.queryByRole('columnheader', { name: /Productivity/i })).not.toBeInTheDocument();
  });

  it('keeps selected-call thread context modular in the calls drill-down', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /^Calls$/i }));
    fireEvent.click(screen.getByRole('tab', { name: /^Thread$/i }));

    expect(screen.getByText('Thread timeline')).toBeInTheDocument();
    expect(screen.getByText('fixture-thread-0.jsonl:120')).toBeInTheDocument();
    expect(screen.getByText('fixture-session-0')).toBeInTheDocument();
    expect(screen.getByText('codex-usage-tracker')).toBeInTheDocument();
  });

  it('opens the full-page call investigator from calls and direct record URLs', () => {
  const view = render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Calls$/i }));
  fireEvent.click(screen.getByRole('button', { name: /Open investigator for thread-9f3a1c codex-1/i }));

expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
expect(screen.getByText('thread-9f3a1c / codex-1')).toBeInTheDocument();
expect(screen.getAllByText('fixture-thread-0.jsonl:120').length).toBeGreaterThan(0);
expect(screen.getAllByText('codex-usage-tracker').length).toBeGreaterThan(0);
const metadataCard = screen.getByText('Call Source').closest('.call-source-card');
expect(metadataCard).not.toBeNull();
const metadataPanel = within(metadataCard as HTMLElement);
expect(metadataPanel.getByText('Thread attachment')).toBeInTheDocument();
expect(metadataPanel.getByText('spawned child thread')).toBeInTheDocument();
expect(metadataPanel.getByText('Thread source')).toBeInTheDocument();
expect(metadataPanel.getByText('subagent')).toBeInTheDocument();
expect(metadataPanel.getByText('Subagent type')).toBeInTheDocument();
expect(metadataPanel.getByText('analysis')).toBeInTheDocument();
expect(metadataPanel.getByText('Agent role')).toBeInTheDocument();
expect(metadataPanel.getByText('reviewer')).toBeInTheDocument();
expect(metadataPanel.getByText('Agent nickname')).toBeInTheDocument();
expect(metadataPanel.getByText('usage-reviewer')).toBeInTheDocument();
expect(screen.getByText('Thread Context')).toBeInTheDocument();
expect(screen.getByText('Thread timeline')).toBeInTheDocument();
expect(screen.getByText('Models in thread')).toBeInTheDocument();
expect(window.location.search).toContain('view=call');
    expect(window.location.search).toContain('record=fixture-call-0');
    expect(screen.getByRole('button', { name: /^Calls$/i })).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(screen.getByRole('button', { name: /Next/i }));
    expect(screen.getByText('thread-7b2e91 / o4-mini')).toBeInTheDocument();
    expect(window.location.search).toContain('record=fixture-call-1');

    fireEvent.click(screen.getByRole('button', { name: /Back to Calls/i }));
    expect(screen.getByRole('heading', { name: 'Calls' })).toBeInTheDocument();

    view.unmount();
    window.history.replaceState(null, '', '/?view=call&record=fixture-call-2');
    render(<App />);
expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
  expect(screen.getByText('thread-3c8d4e / o3')).toBeInTheDocument();
  expect(screen.getByText('Call Source')).toBeInTheDocument();
  expect(screen.getByText('dashboard, rewrite')).toBeInTheDocument();
  expect(screen.getByText('Thread Context')).toBeInTheDocument();
expect(screen.getByText('Thread timeline')).toBeInTheDocument();
expect(screen.getByRole('button', { name: /^Open$/i })).toBeInTheDocument();
});

it('opens full-page call investigator through call-row activation', () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Calls$/i }));

  const row = screen.getByText('thread-3c8d4e').closest('tr');
  expect(row).not.toBeNull();
  fireEvent.doubleClick(row as HTMLTableRowElement);

  expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
  expect(screen.getByText('thread-3c8d4e / o3')).toBeInTheDocument();
  expect(window.location.search).toContain('view=call');
  expect(window.location.search).toContain('record=fixture-call-2');
});
});
