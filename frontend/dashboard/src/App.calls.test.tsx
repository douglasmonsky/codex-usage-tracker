import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, waitFor, within } from './test-utils/appTestHarness';

describe('React dashboard calls filters and source metadata', () => {
  installAppTestHooks();

it('clears calls filters and URL state', () => {
window.history.replaceState(
null,
'',
'/?view=calls&record=stale-record&call_q=thread-2f9e7d&model=o4-mini&effort=medium&confidence=cost-estimated&source=git&date=custom&from=2026-06-01&to=2026-06-01&sort=cache&direction=desc&density=roomy',
);

render(<App />);

expect(screen.getByLabelText('Search calls')).toHaveValue('thread-2f9e7d');
expect(screen.getByLabelText('Confidence filter')).toHaveValue('cost-estimated');
expect(screen.getByLabelText('Source filter')).toHaveValue('git');
expect(screen.getByLabelText('Time filter')).toHaveValue('custom');
expect(screen.getByLabelText('Sort calls')).toHaveValue('cache');
expect(screen.getByRole('button', { name: 'Roomy' })).toHaveAttribute('aria-pressed', 'true');

fireEvent.click(screen.getByRole('button', { name: /Clear filters/i }));

expect(screen.getByText('thread-9f3a1c')).toBeInTheDocument();
expect(screen.getByLabelText('Search calls')).toHaveValue('');
expect(screen.getByLabelText('Confidence filter')).toHaveValue('all');
expect(screen.getByLabelText('Source filter')).toHaveValue('all');
expect(screen.getByLabelText('Time filter')).toHaveValue('all');
expect(screen.getByLabelText('Sort calls')).toHaveValue('time');
expect(screen.getByRole('button', { name: 'Dense' })).toHaveAttribute('aria-pressed', 'true');
expect(screen.getByText('Calls filters cleared')).toBeInTheDocument();
const params = new URLSearchParams(window.location.search);
expect(params.get('view')).toBe('calls');
for (const key of ['record', 'call_q', 'model', 'effort', 'confidence', 'source', 'date', 'from', 'to', 'sort', 'direction', 'density']) {
expect(params.get(key)).toBeNull();
}
});

it('hydrates selected calls record URL state', async () => {
  window.history.replaceState(null, '', '/?view=calls&record=fixture-call-2');

  render(<App />);

  const callsTable = screen.getByRole('table', { name: 'Model calls' });
  const selectedRow = within(callsTable).getByText('thread-3c8d4e').closest('tr');
  expect(selectedRow).not.toBeNull();
  expect(selectedRow).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByText('Accounting Snapshot')).toBeInTheDocument();
  expect(screen.getByText('Session cumulative')).toBeInTheDocument();
  expect(screen.getByText('Pricing model')).toBeInTheDocument();
  expect(screen.getByText('Cache savings')).toBeInTheDocument();

  await waitFor(() => {
    const params = new URLSearchParams(window.location.search);
    expect(params.get('view')).toBe('calls');
    expect(params.get('record')).toBe('fixture-call-2');
  });
});

it('hydrates legacy detail-first calls URL state', async () => {
  window.history.replaceState(null, '', '/?view=calls&detail=first');

  render(<App />);

  const callsTable = screen.getByRole('table', { name: 'Model calls' });
  const firstRow = within(callsTable).getByText('thread-9f3a1c').closest('tr');
  expect(firstRow).not.toBeNull();
  expect(firstRow).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByText('thread-9f3a1c / codex-1')).toBeInTheDocument();

  await waitFor(() => {
    const params = new URLSearchParams(window.location.search);
    expect(params.get('view')).toBe('calls');
    expect(params.get('record')).toBe('fixture-call-0');
    expect(params.get('detail')).toBeNull();
  });
});

it('syncs selected calls record when a table row is hovered', async () => {
  window.history.replaceState(null, '', '/?view=calls');

  render(<App />);

  const callsTable = screen.getByRole('table', { name: 'Model calls' });
  const selectedRow = within(callsTable).getByText('thread-3c8d4e').closest('tr');
  expect(selectedRow).not.toBeNull();
  fireEvent.mouseEnter(selectedRow as HTMLTableRowElement);

  await waitFor(() => {
    const params = new URLSearchParams(window.location.search);
    expect(params.get('view')).toBe('calls');
    expect(params.get('record')).toBe('fixture-call-2');
  });
});

it('opens full call investigator when a calls table row is clicked', async () => {
  window.history.replaceState(null, '', '/?view=calls');

  render(<App />);

  const callsTable = screen.getByRole('table', { name: 'Model calls' });
  const selectedRow = within(callsTable).getByText('thread-3c8d4e').closest('tr');
  expect(selectedRow).not.toBeNull();
  fireEvent.click(selectedRow as HTMLTableRowElement);

  await waitFor(() => {
    const params = new URLSearchParams(window.location.search);
    expect(params.get('view')).toBe('call');
    expect(params.get('record')).toBe('fixture-call-2');
    expect(params.get('return')).toBe('calls');
  });
  expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
});

it('syncs calls filters and sorting into URL state', async () => {
  window.history.replaceState(null, '', '/?view=calls&record=stale-record&page=2');

render(<App />);

fireEvent.change(screen.getByLabelText('Search calls'), { target: { value: 'thread-3c8d4e' } });
fireEvent.change(screen.getByDisplayValue('All models'), { target: { value: 'o3' } });
fireEvent.change(screen.getByLabelText('Confidence filter'), { target: { value: 'cost-estimated' } });
fireEvent.change(screen.getByLabelText('Source filter'), { target: { value: 'session' } });
fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-07-01' } });
fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-07-03' } });
    fireEvent.change(screen.getByLabelText('Sort calls'), { target: { value: 'cache' } });
    fireEvent.click(screen.getByRole('button', { name: 'Roomy' }));

    expect(
      screen.getByText(
        /Filters: Search "thread-3c8d4e"; Model o3; Confidence estimated cost; Source session-linked; Custom: 2026-07-01 to 2026-07-03/i,
      ),
    ).toBeInTheDocument();

    let params = new URLSearchParams(window.location.search);
  expect(params.get('view')).toBe('calls');
  expect(params.get('record')).toBeNull();
  expect(params.get('page')).toBeNull();
  expect(params.get('call_q')).toBe('thread-3c8d4e');
expect(params.get('model')).toBe('o3');
expect(params.get('confidence')).toBe('cost-estimated');
expect(params.get('source')).toBe('session');
expect(params.get('date')).toBe('custom');
expect(params.get('time')).toBe('custom');
expect(params.get('from')).toBe('2026-07-01');
expect(params.get('to')).toBe('2026-07-03');
expect(params.get('sort')).toBe('cache');
expect(params.get('direction')).toBeNull();
expect(params.get('density')).toBe('roomy');

let callsTable = screen.getByRole('table', { name: 'Model calls' });
fireEvent.click(within(callsTable).getByRole('button', { name: /Thread/i }));
await waitFor(() => {
  params = new URLSearchParams(window.location.search);
  expect(params.get('sort')).toBe('thread');
  expect(params.get('direction')).toBeNull();
});

callsTable = screen.getByRole('table', { name: 'Model calls' });
fireEvent.click(within(callsTable).getByRole('button', { name: /Thread/i }));
await waitFor(() => {
params = new URLSearchParams(window.location.search);
expect(params.get('sort')).toBe('thread');
expect(params.get('direction')).toBe('desc');
});
});

it('searches calls by legacy cwd and project metadata', () => {
window.__CODEX_USAGE_BOOT__ = {
api_token: 'metadata-search-token',
context_api_enabled: true,
loaded_row_count: 2,
limit: 2,
rows: [
{
record_id: 'metadata-project-row',
session_id: 'session-project-search',
call_started_at: '2026-07-01T10:00:00Z',
thread_name: 'metadata-project-thread',
project_name: 'codex-usage-tracker',
project_relative_cwd: 'frontend/dashboard',
cwd: '/workspace/codex-usage-tracker/frontend/dashboard',
project_tags: ['dashboard', 'react'],
git_branch: 'feature/search-parity',
git_remote_label: 'origin/codex-usage-tracker',
model: 'o5',
effort: 'high',
input_tokens: 100,
cached_input_tokens: 50,
output_tokens: 10,
total_tokens: 110,
estimated_cost_usd: 0.01,
},
{
record_id: 'metadata-other-row',
session_id: 'session-other-search',
call_started_at: '2026-07-01T11:00:00Z',
thread_name: 'metadata-other-thread',
project_name: 'unrelated-tool',
project_relative_cwd: 'backend/api',
cwd: '/workspace/unrelated-tool/backend/api',
git_branch: 'main',
git_remote_label: 'origin/unrelated-tool',
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
window.history.replaceState(null, '', '/?view=calls');

render(<App />);

expect(screen.getByPlaceholderText('Search calls, cwd, projects, models...')).toBeInTheDocument();
fireEvent.change(screen.getByLabelText('Search calls'), { target: { value: 'frontend/dashboard' } });

expect(screen.getByText('metadata-project-thread')).toBeInTheDocument();
expect(screen.queryByText('metadata-other-thread')).not.toBeInTheDocument();
});

it('filters calls by source metadata scope', () => {
window.__CODEX_USAGE_BOOT__ = {
api_token: 'source-filter-token',
context_api_enabled: true,
loaded_row_count: 4,
limit: 4,
rows: [
{
record_id: 'source-project-row',
call_started_at: '2026-07-01T10:00:00Z',
thread_name: 'source-project-thread',
project_name: 'codex-usage-tracker',
project_relative_cwd: 'frontend/dashboard',
cwd: '/workspace/codex-usage-tracker/frontend/dashboard',
model: 'o5',
effort: 'high',
input_tokens: 100,
cached_input_tokens: 50,
output_tokens: 10,
total_tokens: 110,
estimated_cost_usd: 0.01,
},
{
record_id: 'source-session-row',
session_id: 'source-session-id',
call_started_at: '2026-07-01T10:05:00Z',
thread_name: 'source-session-thread',
model: 'o4-mini',
effort: 'medium',
input_tokens: 100,
cached_input_tokens: 50,
output_tokens: 10,
total_tokens: 110,
estimated_cost_usd: 0.01,
},
{
record_id: 'source-file-row',
source_file: '/tmp/source-file.jsonl',
line_number: 42,
call_started_at: '2026-07-01T10:10:00Z',
thread_name: 'source-file-thread',
model: 'o4-mini',
effort: 'medium',
input_tokens: 100,
cached_input_tokens: 50,
output_tokens: 10,
total_tokens: 110,
estimated_cost_usd: 0.01,
},
{
record_id: 'source-missing-row',
call_started_at: '2026-07-01T10:15:00Z',
thread_name: 'source-missing-thread',
model: 'o4-mini',
effort: 'low',
input_tokens: 100,
cached_input_tokens: 50,
output_tokens: 10,
total_tokens: 110,
estimated_cost_usd: 0.01,
},
],
};
window.history.replaceState(null, '', '/?view=calls&source=missing');

render(<App />);

expect(screen.getByLabelText('Source filter')).toHaveValue('missing');
expect(screen.getByText('source-missing-thread')).toBeInTheDocument();
expect(screen.queryByText('source-project-thread')).not.toBeInTheDocument();
expect(screen.queryByText('source-session-thread')).not.toBeInTheDocument();
expect(screen.queryByText('source-file-thread')).not.toBeInTheDocument();

fireEvent.change(screen.getByLabelText('Source filter'), { target: { value: 'source-file' } });

expect(screen.getByText('source-file-thread')).toBeInTheDocument();
expect(screen.queryByText('source-missing-thread')).not.toBeInTheDocument();
expect(new URLSearchParams(window.location.search).get('source')).toBe('source-file');
});
});
