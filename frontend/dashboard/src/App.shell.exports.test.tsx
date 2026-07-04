import { App, describe, expect, fireEvent, installAppTestHooks, it, render, rowsToCsv, screen, vi, within } from './test-utils/appTestHarness';
import { callCsvColumns } from './features/shared/tables';
import { fixtureModel } from './test-fixtures/dashboardFixture';

describe('React dashboard shell exports', () => {
  installAppTestHooks();

it('exports the current view from the shell topbar', () => {
const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);

render(<App />);

fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));
expect(clickSpy).toHaveBeenCalledTimes(1);
expect(screen.getAllByText('Exported 8 call rows').length).toBeGreaterThan(0);

fireEvent.click(screen.getByRole('button', { name: /^Threads$/i }));
  fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));
  expect(clickSpy).toHaveBeenCalledTimes(2);
  expect(screen.getAllByText(/Exported \d+ call rows/).length).toBeGreaterThan(0);
});

it('exports filtered Calls rows from shell topbar', () => {
  const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  window.history.replaceState(null, '', '/?view=calls&call_q=thread-9f3a');

  render(<App />);

  fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));
  expect(clickSpy).toHaveBeenCalledTimes(1);
  expect(screen.getAllByText('Exported 1 call rows').length).toBeGreaterThan(0);
});

it('exports only the selected full-page Call Investigator row from shell topbar', () => {
  const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  window.history.replaceState(null, '', '/?view=call&record=fixture-call-2');

  render(<App />);

  fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));
  expect(clickSpy).toHaveBeenCalledTimes(1);
  expect(screen.getAllByText('Exported 1 call rows').length).toBeGreaterThan(0);
});

it('does not export the wrong Call Investigator row for unloaded records', () => {
  const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  window.history.replaceState(null, '', '/?view=call&record=not-loaded');

  render(<App />);

  fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));
  expect(clickSpy).not.toHaveBeenCalled();
  expect(screen.getAllByText('No call rows to export').length).toBeGreaterThan(0);
});

it('exports overview rows filtered by global search from shell topbar', () => {
  const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  window.history.replaceState(null, '', '/?view=overview&q=thread-9f3a');

  render(<App />);

  fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));
  expect(clickSpy).toHaveBeenCalledTimes(1);
  expect(screen.getAllByText('Exported 1 call rows').length).toBeGreaterThan(0);
});

it('exports investigator rows scoped by selected finding URL state', () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    window.history.replaceState(null, '', '/?view=investigator&finding=2');

  render(<App />);

  fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(screen.getAllByText('Exported 6 call rows').length).toBeGreaterThan(0);
  });

it('exports Cache And Context evidence rows scoped by selected thread URL state', () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    window.history.replaceState(null, '', '/?view=cache-context&cache_thread=thread-9f3a');

    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));

    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(screen.getAllByText('Exported 1 call rows').length).toBeGreaterThan(0);
  });

it('syncs Cache And Context selected thread to URL state', () => {
    window.history.replaceState(null, '', '/?view=cache-context');

    render(<App />);
    const table = screen.getByRole('table', { name: 'Cache context threads overview' });
    const row = within(table).getByText('thread-3c5d').closest('tr');
    expect(row).not.toBeNull();
    fireEvent.mouseEnter(row as HTMLTableRowElement);

    expect(new URLSearchParams(window.location.search).get('cache_thread')).toBe('thread-3c5d');
  });

it('exports Diagnostics fact calls scoped by selected fact URL state', () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    window.history.replaceState(null, '', '/?view=diagnostics&diagnostic_fact=model:high_effort');

    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));

    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(screen.getAllByText('Exported 4 call rows').length).toBeGreaterThan(0);
  });

it('syncs Diagnostics selected structured fact to URL state', () => {
    window.history.replaceState(null, '', '/?view=diagnostics');

    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /model\s*\/\s*high_effort/i }));

    const params = new URLSearchParams(window.location.search);
    expect(params.get('view')).toBe('diagnostics');
    expect(params.get('diagnostic_fact')).toBe('model:high_effort');
  });

it('exports reports evidence rows scoped by selected report URL state', () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    window.history.replaceState(null, '', '/?view=reports&report=fast-mode-proxy');

    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));

    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(screen.getAllByText('Exported 4 call rows').length).toBeGreaterThan(0);
  });

it('exports Usage Drain evidence rows scoped by URL-backed controls', () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    window.history.replaceState(
      null,
      '',
      '/?view=usage-drain&usage_plan=Prolite&usage_effort=low&usage_subagents=0&usage_sample=1&usage_confidence=0.55',
    );

    render(<App />);

    expect(screen.getByLabelText('Plan')).toHaveValue('Prolite');
    expect(screen.getByLabelText('Effort Filter')).toHaveValue('low');
    expect(screen.getByLabelText('Include subagents')).not.toBeChecked();
    expect(screen.getByLabelText('Min sample size')).toHaveValue(1);
    expect(screen.getByLabelText('Confidence threshold')).toHaveValue('0.55');

    fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));

    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(screen.getAllByText('Exported 1 call rows').length).toBeGreaterThan(0);
  });

it('syncs Usage Drain controls to URL state', () => {
    window.history.replaceState(null, '', '/?view=usage-drain');

    render(<App />);

    fireEvent.change(screen.getByLabelText('Effort Filter'), { target: { value: 'low' } });
    fireEvent.click(screen.getByLabelText('Include subagents'));
    fireEvent.change(screen.getByLabelText('Min sample size'), { target: { value: '3' } });

    const params = new URLSearchParams(window.location.search);
    expect(params.get('view')).toBe('usage-drain');
    expect(params.get('usage_effort')).toBe('low');
    expect(params.get('usage_subagents')).toBe('0');
    expect(params.get('usage_sample')).toBe('3');
  });

it('exports call rows behind filtered Threads rows from shell topbar', () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  window.history.replaceState(null, '', '/?view=threads&thread_q=thread-0e16&risk=Low');

  render(<App />);

  fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));
  expect(clickSpy).toHaveBeenCalledTimes(1);
  expect(screen.getAllByText('Exported 1 call rows').length).toBeGreaterThan(0);
});

it('syncs investigator selected finding to the URL', () => {
  window.history.replaceState(null, '', '/?view=investigator');

  render(<App />);

  const findingCard = screen.getByText('Cache Misses (Large Inputs)').closest('article');
  expect(findingCard).not.toBeNull();
  fireEvent.click(within(findingCard as HTMLElement).getByRole('button', { name: /Inspect/i }));

  expect(new URLSearchParams(window.location.search).get('finding')).toBe('2');
  expect(screen.getByText('Selected Cache Misses (Large Inputs)')).toBeInTheDocument();
});

it('reports empty Calls shell exports without duplicated row wording', () => {
  const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  window.history.replaceState(null, '', '/?view=calls&call_q=definitely-no-matching-call');

  render(<App />);

  fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));
  expect(clickSpy).not.toHaveBeenCalled();
  expect(screen.getAllByText('No call rows to export').length).toBeGreaterThan(0);
});

it('escapes CSV output for aggregate exports', () => {
    expect(
      rowsToCsv(
        [{ name: 'thread,with,commas', value: 42 }],
        [
          { header: 'Name', value: row => row.name },
          { header: 'Value', value: row => row.value },
        ],
      ),
    ).toBe('Name,Value\n"thread,with,commas",42');
  });

it('keeps call CSV headers compatible with legacy aggregate exports', () => {
  const csv = rowsToCsv([fixtureModel.calls[0]], callCsvColumns);
  const headers = csv.split('\n')[0].split(',');

  expect(headers.slice(0, 6)).toEqual([
    'timestamp',
    'thread',
    'call_started_at',
    'call_duration_seconds',
    'previous_call_event_timestamp',
    'previous_call_delta_seconds',
  ]);
  expect(headers).toEqual(
    expect.arrayContaining([
      'call_duration_seconds',
      'estimated_cost_usd',
      'usage_credits',
      'cache_ratio',
      'context_window_percent',
      'pricing_model',
      'usage_credit_confidence',
      'recommendation',
    ]),
  );
});
});
