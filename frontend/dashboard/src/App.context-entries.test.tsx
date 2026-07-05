import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, vi, waitFor } from './test-utils/appTestHarness';

describe('React dashboard context entry visibility', () => {
installAppTestHooks();

it('reveals all returned selected-call evidence entries instead of silently truncating them', async () => {
    window.history.replaceState(null, '', '/?view=calls&record=record-many-entries');
installEntryBootPayload();
const fetchMock = vi.fn().mockResolvedValue(contextEntriesResponse(10));
vi.stubGlobal('fetch', fetchMock);

render(<App />);
fireEvent.click(screen.getByRole('tab', { name: /Evidence/i }));
fireEvent.click(screen.getByRole('button', { name: /Show turn (?:log )?evidence/i }));

expect(await screen.findByText('context entry 8')).toBeInTheDocument();
expectContextEntriesCollapsed();
expect(screen.queryByText('context entry 10')).not.toBeInTheDocument();
expect(screen.getByText('2 entries hidden in compact view')).toBeInTheDocument();
fireEvent.click(screen.getByRole('button', { name: /Show all 10 returned entries/i }));

expect(screen.getByText('context entry 10')).toBeInTheDocument();
expectSecondContextEntryOpen();
fireEvent.click(screen.getByRole('button', { name: /Show first 8 entries/i }));
expect(screen.queryByText('context entry 10')).not.toBeInTheDocument();
await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
});

it('reveals all returned full-page investigator evidence entries instead of silently truncating them', async () => {
window.history.replaceState(null, '', '/?view=call&record=record-many-entries');
installEntryBootPayload();
const fetchMock = vi.fn().mockResolvedValue(contextEntriesResponse(12));
vi.stubGlobal('fetch', fetchMock);

render(<App />);
fireEvent.click(screen.getByRole('button', { name: /Show turn (?:log )?evidence/i }));

expect(await screen.findByText('context entry 10')).toBeInTheDocument();
expectContextEntriesCollapsed();
expect(screen.queryByText('context entry 12')).not.toBeInTheDocument();
expect(screen.getByText('2 entries hidden in compact view')).toBeInTheDocument();
fireEvent.click(screen.getByRole('button', { name: /Show all 12 returned entries/i }));

expect(await screen.findByText('context entry 12')).toBeInTheDocument();
expectSecondContextEntryOpen();
fireEvent.click(screen.getByRole('button', { name: /Show first 10 entries/i }));
await waitFor(() => expect(screen.queryByText('context entry 12')).not.toBeInTheDocument());
await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
});
});

function installEntryBootPayload() {
window.__CODEX_USAGE_BOOT__ = {
api_token: 'test-token',
context_api_enabled: true,
loaded_row_count: 1,
rows: [
{
record_id: 'record-many-entries',
call_started_at: '2026-07-01T12:00:00Z',
thread_name: 'many-entry-thread',
model: 'gpt-5.5',
effort: 'high',
input_tokens: 1000,
cached_input_tokens: 500,
output_tokens: 100,
total_tokens: 1100,
estimated_cost_usd: 0.1,
},
],
};
}

function expectContextEntriesCollapsed() {
const entries = [...document.querySelectorAll('details.context-entry')];
expect(entries.length).toBeGreaterThan(1);
expect(entries[0]).toHaveAttribute('open');
expect(entries[1]).not.toHaveAttribute('open');
fireEvent.click(entries[1].querySelector('summary') as HTMLElement);
expect(entries[1]).toHaveAttribute('open');
}

function expectSecondContextEntryOpen() {
const entries = [...document.querySelectorAll('details.context-entry')];
expect(entries.length).toBeGreaterThan(1);
expect(entries[1]).toHaveAttribute('open');
}

function contextEntriesResponse(count: number) {
return {
ok: true,
json: async () => ({
schema: 'codex-usage-tracker-context-v1',
record_id: 'record-many-entries',
context_mode: 'quick',
visible_char_count: 120,
visible_token_estimate: 30,
omitted: { older_entries: 0 },
entries: Array.from({ length: count }, (_, index) => ({
type: 'message',
label: `Entry ${index + 1}`,
line_number: 20 + index,
text: `context entry ${index + 1}`,
})),
}),
};
}
