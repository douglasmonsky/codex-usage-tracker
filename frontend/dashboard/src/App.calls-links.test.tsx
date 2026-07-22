import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, vi, waitFor, within } from './test-utils/appTestHarness';

describe('React dashboard call investigator link URL state', () => {
  installAppTestHooks();

  it('copies direct call investigator links from row actions', async () => {
      const writeText = vi.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: { writeText },
      });
      window.history.replaceState(null, '', '/?view=explore&mode=calls&qa=row-copy');

 render(<App />);
 const copyButton = screen.getByRole('button', { name: /Copy link for thread-9f3a1c codex-1/i });
 fireEvent.keyDown(copyButton, { key: 'Enter' });
 expect(screen.queryByRole('heading', { name: 'Call Investigator' })).not.toBeInTheDocument();
 expect(window.location.search).toContain('view=explore');
 fireEvent.click(copyButton);

      await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
      const copiedUrl = new URL(writeText.mock.calls[0][0]);
      expect(copiedUrl.searchParams.get('view')).toBe('evidence');
      expect(copiedUrl.searchParams.get('kind')).toBe('call');
      expect(copiedUrl.searchParams.get('record')).toBe('fixture-call-0');
      expect(copiedUrl.searchParams.get('return')).toBe('explore');
      expect(copiedUrl.searchParams.get('return_mode')).toBe('calls');
      expect(copiedUrl.searchParams.get('qa')).toBe('row-copy');
  expect(window.location.search).toContain('view=explore');
  expect(await screen.findByText('Copied call investigator link')).toBeInTheDocument();
  });

  it('copies selected-call drill-down links with calls return state', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', {
  configurable: true,
  value: { writeText },
  });
  window.history.replaceState(null, '', '/?view=calls&record=fixture-call-0&call_q=thread-9f3a&sort=cache');

  render(<App />);

  const drilldown = screen.getByText('Call Drill-Down').closest('aside');
  expect(drilldown).not.toBeNull();
  fireEvent.click(within(drilldown as HTMLElement).getByRole('button', { name: /^Copy link$/i }));

  await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
  const copiedUrl = new URL(writeText.mock.calls[0][0]);
  expect(copiedUrl.searchParams.get('view')).toBe('evidence');
  expect(copiedUrl.searchParams.get('kind')).toBe('call');
  expect(copiedUrl.searchParams.get('record')).toBe('fixture-call-0');
  expect(copiedUrl.searchParams.get('return')).toBe('explore');
  expect(copiedUrl.searchParams.get('return_mode')).toBe('calls');
  expect(copiedUrl.searchParams.get('call_q')).toBe('thread-9f3a');
  expect(copiedUrl.searchParams.get('sort')).toBe('cache');
  expect(await screen.findByText('Copied investigator link')).toBeInTheDocument();
  });

  it('copies full-page thread timeline call links', async () => {
   const writeText = vi.fn().mockResolvedValue(undefined);
   Object.defineProperty(navigator, 'clipboard', {
   configurable: true,
   value: { writeText },
   });
   window.history.replaceState(null, '', '/?view=call&record=timeline-row-2&return=calls&qa=timeline-copy');
   window.__CODEX_USAGE_BOOT__ = {
   api_token: 'timeline-copy-token',
   context_api_enabled: true,
   loaded_row_count: 2,
   rows: [
   {
   record_id: 'timeline-row-1',
   call_started_at: '2026-07-01T10:00:00Z',
   thread_name: 'timeline-thread',
   model: 'codex-1',
   effort: 'high',
  input_tokens: 2000,
  cached_input_tokens: 1000,
  output_tokens: 300,
  total_tokens: 2300,
  estimated_cost_usd: 0.12,
  pricing_estimated: true,
  context_window_percent: 0.82,
  duration_seconds: 42,
  previous_call_delta_seconds: 360,
  call_initiator: 'assistant',
  recommended_action: 'Timeline recommendation sample.',
  },
   {
   record_id: 'timeline-row-2',
   call_started_at: '2026-07-01T10:10:00Z',
   thread_name: 'timeline-thread',
   model: 'o4-mini',
   effort: 'medium',
  input_tokens: 3000,
  cached_input_tokens: 1500,
  output_tokens: 400,
  total_tokens: 3400,
  estimated_cost_usd: 0.18,
  pricing_estimated: false,
  context_window_percent: 0.41,
  duration_seconds: 24,
  previous_call_delta_seconds: 600,
  call_initiator: 'user',
  },
   ],
   };

   render(<App />);
   expect(screen.getByText('Context 82.0%')).toBeInTheDocument();
   expect(screen.getByText('Best-guess estimate')).toBeInTheDocument();
   expect(screen.getByText('Timeline recommendation sample.')).toBeInTheDocument();
   expect(screen.getByText('prev 6m 0s')).toBeInTheDocument();
   expect(screen.getAllByText('Configured price').length).toBeGreaterThan(0);
   fireEvent.click(screen.getByRole('button', { name: /Copy link for thread context call timeline-thread codex-1/i }));

   await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
   const copiedUrl = new URL(writeText.mock.calls[0][0]);
   expect(copiedUrl.searchParams.get('view')).toBe('evidence');
   expect(copiedUrl.searchParams.get('kind')).toBe('call');
   expect(copiedUrl.searchParams.get('record')).toBe('timeline-row-1');
   expect(copiedUrl.searchParams.get('return')).toBe('explore');
   expect(copiedUrl.searchParams.get('return_mode')).toBe('calls');
   expect(copiedUrl.searchParams.get('qa')).toBe('timeline-copy');
   expect(window.location.search).toContain('record=timeline-row-2');
   expect(await screen.findByText('Copied call investigator link')).toBeInTheDocument();
  });

  it('copies side-panel thread timeline call links and shows timeline signals', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
    window.history.replaceState(null, '', '/?view=calls&record=timeline-row-2&qa=side-timeline-copy');
    window.__CODEX_USAGE_BOOT__ = {
      api_token: 'side-timeline-copy-token',
      context_api_enabled: true,
      loaded_row_count: 2,
      rows: [
        {
          record_id: 'timeline-row-1',
          call_started_at: '2026-07-01T10:00:00Z',
          thread_name: 'timeline-thread',
          model: 'codex-1',
          effort: 'high',
          input_tokens: 2000,
          cached_input_tokens: 1000,
          output_tokens: 300,
          total_tokens: 2300,
          estimated_cost_usd: 0.12,
          pricing_estimated: true,
          context_window_percent: 0.82,
          duration_seconds: 42,
          previous_call_delta_seconds: 360,
          call_initiator: 'assistant',
          recommended_action: 'Timeline recommendation sample.',
        },
        {
          record_id: 'timeline-row-2',
          call_started_at: '2026-07-01T10:10:00Z',
          thread_name: 'timeline-thread',
          model: 'o4-mini',
          effort: 'medium',
          input_tokens: 3000,
          cached_input_tokens: 1500,
          output_tokens: 400,
          total_tokens: 3400,
          estimated_cost_usd: 0.18,
          pricing_estimated: false,
          context_window_percent: 0.41,
          duration_seconds: 24,
          previous_call_delta_seconds: 600,
          call_initiator: 'user',
        },
      ],
    };

    render(<App />);
    fireEvent.click(screen.getByRole('tab', { name: /^Thread$/i }));

    expect(screen.getByText('Context 82.0%')).toBeInTheDocument();
    expect(screen.getByText('Best-guess estimate')).toBeInTheDocument();
    expect(screen.getByText('Timeline recommendation sample.')).toBeInTheDocument();
    expect(screen.getByText('prev 6m 0s')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Copy link for side-panel thread call timeline-thread codex-1/i }));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const copiedUrl = new URL(writeText.mock.calls[0][0]);
    expect(copiedUrl.searchParams.get('view')).toBe('evidence');
    expect(copiedUrl.searchParams.get('kind')).toBe('call');
    expect(copiedUrl.searchParams.get('record')).toBe('timeline-row-1');
    expect(copiedUrl.searchParams.get('return')).toBe('explore');
    expect(copiedUrl.searchParams.get('return_mode')).toBe('calls');
    expect(copiedUrl.searchParams.get('qa')).toBe('side-timeline-copy');
    expect(window.location.search).toContain('view=explore');
    expect(window.location.search).toContain('mode=calls');
    expect(await screen.findByText('Copied call investigator link')).toBeInTheDocument();
  });

  it('opens the full-page call investigator from a single Explore call row click', () => {
      window.history.replaceState(null, '', '/?view=explore&mode=calls');
      render(<App />);

    fireEvent.click(screen.getByText('thread-9f3a1c'));

    expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
    expect(screen.getByText('thread-9f3a1c / codex-1')).toBeInTheDocument();
    expect(screen.getByText('Exact callback accounting')).toBeInTheDocument();
    expect(screen.getByText('128,542 input tokens = 79,696 cached + 48,846 uncached; 45,231 output tokens; 62.0% cache reuse.')).toBeInTheDocument();
    expect(screen.getByText('Compared previous call')).toBeInTheDocument();
    expect(screen.getByText('Evidence state')).toBeInTheDocument();
    expect(screen.getByText('Next diagnostic move')).toBeInTheDocument();
    expect(screen.getByText('Evidence is not loaded yet. Aggregate token counts are exact, but visible-context attribution needs runtime evidence.')).toBeInTheDocument();
    expect(window.location.search).toContain('view=evidence');
    expect(window.location.search).toContain('kind=call');
    expect(window.location.search).toContain('record=fixture-call-0');
  });
});
