import { App, describe, expect, fireEvent, installAppTestHooks, it, navigateApp, render, rowsToCsv, screen, vi, waitFor } from './test-utils/appTestHarness';
import { callCsvColumns } from './features/shared/tables';
import { fixtureModel } from './test-fixtures/dashboardFixture';

describe('React dashboard shell exports', () => {
  installAppTestHooks();

it('exports the current view from the shell topbar', async () => {
const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);

render(<App />);
navigateApp('/?view=explore&mode=calls');

fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));
await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(1));
expect(await screen.findAllByText('Exported 8 call rows')).not.toHaveLength(0);

navigateApp('/?view=explore&mode=threads');
  fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));
  await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(2));
  expect(await screen.findAllByText(/Exported \d+ call rows/)).not.toHaveLength(0);
});

it('exports filtered Calls rows from shell topbar', async () => {
  const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  window.history.replaceState(null, '', '/?view=calls&call_q=thread-9f3a');

  render(<App />);

  fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));
  await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(1));
  expect(await screen.findAllByText('Exported 1 call rows')).not.toHaveLength(0);
});

it('exports only the selected full-page Call Investigator row from shell topbar', async () => {
  const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  window.history.replaceState(null, '', '/?view=call&record=fixture-call-2');

  render(<App />);

  fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));
  await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(1));
  expect(await screen.findAllByText('Exported 1 call rows')).not.toHaveLength(0);
});

it('does not export the wrong Call Investigator row for unloaded records', async () => {
  const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  window.history.replaceState(null, '', '/?view=call&record=not-loaded');

  render(<App />);

  fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));
  expect(clickSpy).not.toHaveBeenCalled();
  expect(await screen.findAllByText('No call rows to export')).not.toHaveLength(0);
});

it('exports overview rows filtered by global search from shell topbar', async () => {
  const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  window.history.replaceState(null, '', '/?view=overview&q=thread-9f3a');

  render(<App />);

  fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));
  await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(1));
  expect(await screen.findAllByText('Exported 1 call rows')).not.toHaveLength(0);
});

it('exports Limits compatibility call rows while preserving URL-backed analysis state', async () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    window.history.replaceState(
      null,
      '',
      '/?view=usage-drain&limit_window=five_hour&limit_hypothesis=stable',
    );

    render(<App />);

    expect(screen.getByRole('button', { name: '5-hour' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Behavior stayed stable' })).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));

    await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(1));
    expect(await screen.findAllByText('Exported 8 call rows')).not.toHaveLength(0);
  });

it('syncs Limits window and hypothesis controls to URL state', () => {
    window.history.replaceState(null, '', '/?view=usage-drain');

    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: '5-hour' }));
    fireEvent.click(screen.getByRole('button', { name: 'Behavior stayed stable' }));

    const params = new URLSearchParams(window.location.search);
    expect(params.get('view')).toBe('usage-drain');
    expect(params.get('limit_window')).toBe('five_hour');
    expect(params.get('limit_hypothesis')).toBe('stable');
  });

it('exports call rows behind filtered Threads rows from shell topbar', async () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  window.history.replaceState(null, '', '/?view=threads&thread_q=thread-0e16&risk=Low');

  render(<App />);

  fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));
  await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(1));
  expect(await screen.findAllByText('Exported 1 call rows')).not.toHaveLength(0);
});

it('reports empty Calls shell exports without duplicated row wording', async () => {
  const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  window.history.replaceState(null, '', '/?view=calls&call_q=definitely-no-matching-call');

  render(<App />);

  fireEvent.click(screen.getByRole('button', { name: /Export CSV/i }));
  expect(clickSpy).not.toHaveBeenCalled();
  expect(await screen.findAllByText('No call rows to export')).not.toHaveLength(0);
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
