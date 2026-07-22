import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, vi, waitFor, within } from './test-utils/appTestHarness';

describe('React dashboard shell controls', () => {
  installAppTestHooks();

  it('labels the dashboard as an unofficial project in the shell', () => {
    render(<App />);

    expect(screen.getByRole('note', { name: 'Unofficial project notice' })).toHaveTextContent(
      'Unofficial project. Not made by, affiliated with, endorsed by, sponsored by, or supported by OpenAI.',
    );
  });

it('normalizes legacy insights view URLs to the Home route', async () => {
  window.history.replaceState(null, '', '/?view=insights');

  render(<App />);

  expect(screen.getByRole('heading', { name: 'Home' })).toBeInTheDocument();
  await waitFor(() => {
    const params = new URLSearchParams(window.location.search);
    expect(params.get('view')).toBe('home');
  });
});

  it('normalizes legacy insights return URLs from the call investigator', async () => {
    window.history.replaceState(null, '', '/?view=call&record=fixture-call-0&return=insights');

    render(<App />);

  expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
  await waitFor(() => {
    expect(new URLSearchParams(window.location.search).get('return')).toBe('home');
  });

  fireEvent.click(screen.getByRole('button', { name: /Back to Home/i }));
  expect(screen.getByRole('heading', { name: 'Home' })).toBeInTheDocument();
  expect(new URLSearchParams(window.location.search).get('view')).toBe('home');
});

it('hydrates legacy call investigator context options from URL params', () => {
  window.history.replaceState(
    null,
    '',
    '/?view=call&record=fixture-call-0&return=calls&mode=full&max_entries=50&max_chars=0&include_tool_output=1&include_compaction_history=true',
  );

  render(<App />);

  expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
  expect(screen.getByLabelText('Context mode')).toHaveValue('full');
  expect(screen.getByLabelText('Context entries')).toHaveValue('50');
  expect(screen.getByLabelText('Include tool output')).toBeChecked();
  expect(screen.getByLabelText('Include compaction history')).toBeChecked();
  expect(screen.getByLabelText('No char limit')).toBeChecked();

  fireEvent.click(screen.getByRole('button', { name: /Back to Explore/i }));
  const params = new URLSearchParams(window.location.search);
  expect(params.get('view')).toBe('explore');
  expect(params.get('mode')).toBe('calls');
  for (const name of ['max_entries', 'max_chars', 'include_tool_output', 'include_compaction_history']) {
    expect(params.get(name)).toBeNull();
  }
});

it('supports target-route keyboard shortcuts outside form fields', () => {
render(<App />);

fireEvent.keyDown(window, { key: '/' });
const searchInput = screen.getByLabelText('Search dashboard');
expect(searchInput).toHaveFocus();
searchInput.blur();

fireEvent.keyDown(window, { key: '1' });
expect(screen.getByRole('heading', { name: 'Home' })).toBeInTheDocument();
expect(window.location.search).toContain('view=home');

fireEvent.keyDown(window, { key: '2' });
expect(screen.getByRole('heading', { name: 'Calls' })).toBeInTheDocument();
expect(window.location.search).toContain('view=explore');

fireEvent.keyDown(window, { key: '3' });
expect(screen.getByRole('heading', { name: 'Limits' })).toBeInTheDocument();
expect(window.location.search).toContain('view=limits');

fireEvent.keyDown(searchInput, { key: '4' });
expect(screen.getByRole('heading', { name: 'Limits' })).toBeInTheDocument();
expect(window.location.search).toContain('view=limits');

fireEvent.keyDown(window, { key: '4' });
expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument();
expect(window.location.search).toContain('view=settings');
});

it('creates navigation history entries and rehydrates shell state on popstate', () => {
  const pushState = vi.spyOn(window.history, 'pushState');
  render(<App />);

  fireEvent.click(screen.getByRole('button', { name: /^Explore$/i }));
  expect(pushState).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('heading', { name: 'Calls' })).toBeInTheDocument();

  window.history.replaceState(null, '', '/?view=overview&q=cache&preset=cache-heavy&history=all');
  fireEvent.popState(window);

  expect(screen.getByRole('heading', { name: 'Home' })).toBeInTheDocument();
  expect(screen.getByLabelText('Search dashboard')).toHaveValue('cache');
  const params = new URLSearchParams(window.location.search);
  expect(params.get('view')).toBe('home');
  expect(params.get('history')).toBe('all');
});

it('shows legacy back-to-top control after scrolling', () => {
    const scrollTo = vi.fn();
    Object.defineProperty(window, 'scrollTo', {
      configurable: true,
      value: scrollTo,
    });
    Object.defineProperty(window, 'scrollY', {
      configurable: true,
      value: 0,
    });

    render(<App />);
    expect(screen.queryByRole('button', { name: /Back to top/i })).not.toBeInTheDocument();

    Object.defineProperty(window, 'scrollY', {
      configurable: true,
      value: 420,
    });
    fireEvent.scroll(window);

    fireEvent.click(screen.getByRole('button', { name: /Back to top/i }));
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: 'smooth' });
  });

it('copies the current dashboard view link from the topbar', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
  window.history.replaceState(
    null,
    '',
    '/?view=threads&thread=thread-3c5d&history=all&report=weekly-credits&mode=full&max_entries=50',
  );

render(<App />);
fireEvent.click(within(screen.getByRole('banner', { name: 'Dashboard toolbar' })).getByRole('button', { name: /^Copy link$/i }));

await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
const copiedUrl = new URL(writeText.mock.calls[0][0]);
  expect(copiedUrl.searchParams.get('view')).toBe('explore');
  expect(copiedUrl.searchParams.get('mode')).toBe('threads');
  expect(copiedUrl.searchParams.get('thread')).toBe('thread-3c5d');
  expect(copiedUrl.searchParams.get('history')).toBe('all');
  expect(copiedUrl.searchParams.has('report')).toBe(false);
  expect(copiedUrl.searchParams.has('max_entries')).toBe(false);
  expect(screen.getByText('Copied current view link')).toBeInTheDocument();
});

it('copies call investigator view links with return workspace context', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText },
  });
  window.history.replaceState(
    null,
    '',
    '/?view=call&record=fixture-call-6&return=reports&report=weekly-credits&mode=full&max_entries=50&diagnostic_fact=tool:read',
  );

  render(<App />);
fireEvent.click(within(screen.getByRole('banner', { name: 'Dashboard toolbar' })).getByRole('button', { name: /^Copy link$/i }));

  await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
  const copiedUrl = new URL(writeText.mock.calls[0][0]);
  expect(copiedUrl.searchParams.get('view')).toBe('evidence');
  expect(copiedUrl.searchParams.get('kind')).toBe('call');
  expect(copiedUrl.searchParams.get('record')).toBe('fixture-call-6');
  expect(copiedUrl.searchParams.get('return')).toBe('reports');
  expect(copiedUrl.searchParams.get('report')).toBe('weekly-credits');
  expect(copiedUrl.searchParams.get('mode')).toBe('full');
expect(copiedUrl.searchParams.get('max_entries')).toBe('50');
expect(copiedUrl.searchParams.has('diagnostic_fact')).toBe(false);

window.history.replaceState(
  null,
  '',
  '/?view=call&record=fixture-call-6&return=reports&report=weekly-credits&mode=full&max_entries=50&diagnostic_fact=tool:read',
);
fireEvent.click(screen.getByRole('button', { name: /^Copy investigator link$/i }));

await waitFor(() => expect(writeText).toHaveBeenCalledTimes(2));
const pageUrl = new URL(writeText.mock.calls[1][0]);
expect(pageUrl.searchParams.get('view')).toBe('evidence');
expect(pageUrl.searchParams.get('kind')).toBe('call');
expect(pageUrl.searchParams.get('record')).toBe('fixture-call-6');
expect(pageUrl.searchParams.get('return')).toBe('reports');
expect(pageUrl.searchParams.get('report')).toBe('weekly-credits');
expect(pageUrl.searchParams.get('mode')).toBe('full');
expect(pageUrl.searchParams.get('max_entries')).toBe('50');
expect(pageUrl.searchParams.has('diagnostic_fact')).toBe(false);
});

it('clears stale investigator finding state when leaving Investigator workspace', () => {
  window.history.replaceState(null, '', '/?view=investigator&finding=2');

  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Explore$/i }));

  const params = new URLSearchParams(window.location.search);
  expect(params.get('view')).toBe('explore');
  expect(params.get('finding')).toBeNull();
});

it('clears stale thread state when leaving Threads workspace', () => {
  window.history.replaceState(
    null,
    '',
    '/?view=threads&thread=thread-3c5d&expand=all&threads=thread-a,thread-b&thread_q=cache&risk=Low&thread_call_sort=total&thread_call_page=2',
  );

  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Home$/i }));

  const params = new URLSearchParams(window.location.search);
  expect(params.get('view')).toBe('home');
  for (const name of ['thread', 'expand', 'threads', 'thread_q', 'risk', 'thread_call_sort', 'thread_call_page']) {
    expect(params.get(name)).toBeNull();
  }
});

it('clears stale cache thread state leaving Cache And Context workspace', () => {
  window.history.replaceState(null, '', '/?view=cache-context&cache_thread=Thread%20Alpha');

  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Home$/i }));

  const params = new URLSearchParams(window.location.search);
  expect(params.get('view')).toBe('home');
  expect(params.get('cache_thread')).toBeNull();
});

it('clears stale report state leaving Reports workspace', () => {
  window.history.replaceState(null, '', '/?view=reports&report=weekly-credits');

  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Home$/i }));

  const params = new URLSearchParams(window.location.search);
  expect(params.get('view')).toBe('home');
  expect(params.get('report')).toBeNull();
});

it('clears stale usage drain state leaving Usage Drain workspace', () => {
  window.history.replaceState(
    null,
    '',
    '/?view=usage-drain&usage_plan=Weekly&usage_effort=high&usage_subagents=0&usage_sample=80&usage_confidence=0.55&limit_window=five_hour&limit_hypothesis=stable',
  );

  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Home$/i }));

  const params = new URLSearchParams(window.location.search);
  expect(params.get('view')).toBe('home');
  for (const name of ['usage_plan', 'usage_effort', 'usage_subagents', 'usage_sample', 'usage_confidence', 'limit_window', 'limit_hypothesis']) {
    expect(params.get(name)).toBeNull();
  }
});

it('clears stale diagnostics state leaving Diagnostics workspace', () => {
  window.history.replaceState(
    null,
    '',
    '/?view=diagnostics&diagnostic_source=tools&diagnostic_fact=tool:read',
  );

  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Home$/i }));

  const params = new URLSearchParams(window.location.search);
  expect(params.get('view')).toBe('home');
  expect(params.get('diagnostic_source')).toBeNull();
  expect(params.get('diagnostic_fact')).toBeNull();
});

it('clears stale Calls table state leaving Calls workspace but preserves global filters', () => {
  window.history.replaceState(
    null,
    '',
    '/?view=calls&record=fixture-call-0&detail=first&call_q=cache&source=missing&sort=total&direction=asc&density=roomy&page=3&model=gpt-5&effort=high&confidence=cost-estimated&date=last-7-days',
  );

  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Home$/i }));

  const params = new URLSearchParams(window.location.search);
  expect(params.get('view')).toBe('home');
  for (const name of ['record', 'detail', 'call_q', 'source', 'sort', 'direction', 'density', 'page']) {
    expect(params.get(name)).toBeNull();
  }
  expect(params.get('model')).toBe('gpt-5');
  expect(params.get('effort')).toBe('high');
  expect(params.get('confidence')).toBe('cost-estimated');
  expect(params.get('date')).toBe('last-7-days');
});

it('switches between feature workspaces and preserves active navigation state', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /^Limits$/i }));
    expect(screen.getByRole('heading', { name: 'Limits' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Limits$/i })).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(screen.getByRole('button', { name: /^Settings$/i }));
    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument();
  });

it('exposes only target navigation plus the Settings utility', () => {
  render(<App />);

    const primary = screen.getByRole('navigation', { name: 'Primary' });
    expect(within(primary).getAllByRole('button').map(button => button.textContent)).toEqual([
      'Home', 'Explore', 'Limits',
    ]);
    expect(screen.queryByRole('group', { name: 'Quick Links' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Models' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Commands' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Explore' }));
    expect(screen.getByRole('heading', { name: 'Calls' })).toBeInTheDocument();

fireEvent.click(screen.getByText('More filters'));
expect(screen.getByRole('combobox', { name: 'Source filter' })).toBeVisible();
    const sortButton = screen.getByRole('button', { name: 'Sort by Est. Cost' });
    fireEvent.click(sortButton);
    expect(sortButton.closest('th')).toHaveAttribute('aria-sort', 'descending');

    fireEvent.click(within(screen.getByRole('group', { name: 'Utility' })).getByRole('button', { name: 'Settings' }));
    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument();
    expect(screen.getByText('Loaded Data')).toBeInTheDocument();
 expect(screen.getAllByText('Evidence rows').length).toBeGreaterThan(0);
    expect(screen.getByText('8 of 8')).toBeInTheDocument();
    expect(screen.getByText('Static snapshot')).toBeInTheDocument();
    expect(screen.getByText('Content access gated')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^Limits$/i }));
    fireEvent.click(screen.getByRole('button', { name: '5-hour' }));
    expect(screen.getByRole('heading', { level: 2, name: '5-hour rolling context' })).toBeInTheDocument();
    expect(new URLSearchParams(window.location.search).get('limit_window')).toBe('five_hour');

    window.history.replaceState(null, '', '/?view=explore&mode=threads');
    fireEvent.popState(window);
    expect(screen.getByPlaceholderText('Search threads, risks, token totals...')).toBeVisible();
  });

it('surfaces legacy environment status chips in the shell', () => {
    window.__CODEX_USAGE_BOOT__ = {
      api_token: 'status-token',
      context_api_enabled: true,
      loaded_row_count: 0,
      total_available_rows: 0,
      rows: [],
      pricing_configured: false,
      pricing_source: { name: 'OpenAI pricing cache' },
      allowance_configured: false,
      allowance_source: { name: 'Codex credit rates' },
      allowance_error: 'missing allowance.json',
      parser_diagnostics: {
        missing_usage: 3,
        duplicate_cumulative_total: 99,
      },
      dedupe: {
        canonical_rows: 8,
        physical_rows: 10,
        excluded_copied_rows: 2,
      },
      project_metadata_privacy: {
        mode: 'strict',
        cwd_redacted: true,
        project_names_redacted: true,
      },
      privacy_mode: 'strict',
    };

    render(<App />);

    const status = screen.getByLabelText('Dashboard status');
    expect(within(status).getByText('Unofficial project')).toHaveAttribute(
      'title',
      expect.stringContaining('independent'),
    );
    expect(within(status).getByText('Live API')).toHaveAttribute(
      'title',
      expect.stringContaining('Local API token present'),
    );
    expect(within(status).getByText('No costs')).toHaveAttribute(
      'title',
      expect.stringContaining('update-pricing'),
    );
    expect(within(status).getByText('Allowance config error')).toHaveAttribute(
      'title',
      'Config error: missing allowance.json',
    );
    expect(within(status).getByText('Metadata strict')).toHaveAttribute('title', expect.stringContaining('cwd redacted'));
    expect(within(status).getByText('Deduped · 2 copied excluded')).toHaveAttribute(
      'title',
      expect.stringContaining('10 physical source rows'),
    );
    expect(within(status).getByText('Parser warnings')).toHaveAttribute(
      'title',
      expect.stringContaining('missing_usage=3'),
    );
    expect(within(status).getByText('Parser warnings').getAttribute('title')).not.toContain(
      'duplicate_cumulative_total',
    );
  });
});
