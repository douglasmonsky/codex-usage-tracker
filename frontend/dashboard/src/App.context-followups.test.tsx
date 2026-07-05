import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, vi, waitFor } from './test-utils/appTestHarness';

describe('React dashboard context follow-up actions', () => {
installAppTestHooks();

it('loads omitted tool output from selected-call evidence entries', async () => {
    window.history.replaceState(null, '', '/?view=calls&record=record-tool-output');
installToolOutputBootPayload();
const fetchMock = vi.fn()
.mockResolvedValueOnce(contextResponse('tool output omitted sample', true))
.mockResolvedValueOnce(contextResponse('tool output included sample', false));
vi.stubGlobal('fetch', fetchMock);

render(<App />);
fireEvent.click(screen.getByRole('tab', { name: /Evidence/i }));
fireEvent.click(screen.getByRole('button', { name: /Show turn (?:log )?evidence/i }));

expect(await screen.findByText('tool output omitted sample')).toBeInTheDocument();
expect(screen.getByText(/Tool output hidden for this view/)).toBeInTheDocument();
expect(screen.getByText(/Source: fixture-thread\.jsonl:14\./)).toBeInTheDocument();
expect(screen.getByText(/7 older entries omitted/)).toBeInTheDocument();
expect(screen.getByText(/1,234 chars over budget omitted/)).toBeInTheDocument();
fireEvent.click(screen.getByRole('button', { name: /Show tool output/i }));

expect(await screen.findByText('tool output included sample')).toBeInTheDocument();
expect(screen.getByText(/Tool output included with redaction and size limits/)).toBeInTheDocument();
expect(screen.getByText(/No character limit applied/)).toBeInTheDocument();
await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
expect(String(fetchMock.mock.calls[0][0])).toContain('include_tool_output=0');
expect(String(fetchMock.mock.calls[1][0])).toContain('include_tool_output=1');
expect(String(fetchMock.mock.calls[1][0])).toContain('record_id=record-tool-output');
});

it('loads omitted tool output from full-page investigator evidence entries', async () => {
window.history.replaceState(null, '', '/?view=call&record=record-tool-output');
installToolOutputBootPayload();
const fetchMock = vi.fn()
.mockResolvedValueOnce(contextResponse('full-page tool output omitted sample', true))
.mockResolvedValueOnce(contextResponse('full-page tool output included sample', false));
vi.stubGlobal('fetch', fetchMock);

render(<App />);
fireEvent.click(screen.getByRole('button', { name: /Show turn (?:log )?evidence/i }));

expect(await screen.findByText('full-page tool output omitted sample')).toBeInTheDocument();
expect(screen.getByText(/Tool output hidden for this view/)).toBeInTheDocument();
expect(screen.getByText(/Source: fixture-thread\.jsonl:14\./)).toBeInTheDocument();
expect(screen.getByText(/7 older entries omitted/)).toBeInTheDocument();
expect(screen.getByText(/1,234 chars over budget omitted/)).toBeInTheDocument();
expect(screen.getByText('Tool output: omitted')).toBeInTheDocument();
fireEvent.click(screen.getByRole('button', { name: /Show tool output/i }));

expect(await screen.findByText('full-page tool output included sample')).toBeInTheDocument();
expect(screen.getByText(/Tool output included with redaction and size limits/)).toBeInTheDocument();
expect(screen.getByText(/No character limit applied/)).toBeInTheDocument();
await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
expect(String(fetchMock.mock.calls[0][0])).toContain('include_tool_output=0');
expect(String(fetchMock.mock.calls[1][0])).toContain('include_tool_output=1');
expect(String(fetchMock.mock.calls[1][0])).toContain('record_id=record-tool-output');
});

it('loads compacted replacement from selected-call evidence entries', async () => {
    window.history.replaceState(null, '', '/?view=calls&record=record-tool-output');
installToolOutputBootPayload();
const fetchMock = vi.fn()
.mockResolvedValueOnce(compactionResponse('compaction omitted sample', false))
.mockResolvedValueOnce(compactionResponse('compaction included sample', true));
vi.stubGlobal('fetch', fetchMock);

render(<App />);
fireEvent.click(screen.getByRole('tab', { name: /Evidence/i }));
fireEvent.click(screen.getByRole('button', { name: /Show turn (?:log )?evidence/i }));

expect(await screen.findByText('compaction omitted sample')).toBeInTheDocument();
expect(screen.getByText('2 replacement history entries available.')).toBeInTheDocument();
fireEvent.click(screen.getByRole('button', { name: /Show compacted replacement/i }));

expect(await screen.findByText('compaction included sample')).toBeInTheDocument();
expect(screen.getByText('redacted replacement summary')).toBeInTheDocument();
await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
expect(String(fetchMock.mock.calls[0][0])).toContain('include_compaction_history=0');
expect(String(fetchMock.mock.calls[1][0])).toContain('include_compaction_history=1');
expect(String(fetchMock.mock.calls[1][0])).toContain('record_id=record-tool-output');
});

it('loads compacted replacement from full-page investigator evidence entries', async () => {
window.history.replaceState(null, '', '/?view=call&record=record-tool-output');
installToolOutputBootPayload();
const fetchMock = vi.fn()
.mockResolvedValueOnce(compactionResponse('full-page compaction omitted sample', false))
.mockResolvedValueOnce(compactionResponse('full-page compaction included sample', true));
vi.stubGlobal('fetch', fetchMock);

render(<App />);
fireEvent.click(screen.getByRole('button', { name: /Show turn (?:log )?evidence/i }));

expect(await screen.findByText('full-page compaction omitted sample')).toBeInTheDocument();
expect(screen.getByText('Compaction: 0 replacement entries')).toBeInTheDocument();
fireEvent.click(screen.getByRole('button', { name: /Show compacted replacement/i }));

expect(await screen.findByText('full-page compaction included sample')).toBeInTheDocument();
expect(screen.getByText('redacted replacement summary')).toBeInTheDocument();
await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
expect(String(fetchMock.mock.calls[0][0])).toContain('include_compaction_history=0');
expect(String(fetchMock.mock.calls[1][0])).toContain('include_compaction_history=1');
expect(String(fetchMock.mock.calls[1][0])).toContain('record_id=record-tool-output');
});
});

function installToolOutputBootPayload() {
window.__CODEX_USAGE_BOOT__ = {
api_token: 'test-token',
context_api_enabled: true,
loaded_row_count: 1,
rows: [
{
record_id: 'record-tool-output',
call_started_at: '2026-07-01T12:00:00Z',
thread_name: 'tool-output-thread',
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

function contextResponse(text: string, toolOutputOmitted: boolean) {
return {
ok: true,
json: async () => ({
schema: 'codex-usage-tracker-context-v1',
record_id: 'record-tool-output',
context_mode: 'quick',
include_tool_output: !toolOutputOmitted,
visible_char_count: 42,
visible_token_estimate: 11,
source: { file: 'fixture-thread.jsonl', line_number: 14 },
omitted: toolOutputOmitted
? { older_entries: 7, over_budget_chars: 1234, max_chars: 4000 }
: { older_entries: 0, max_chars: 0 },
entries: [
{
type: 'tool_output',
label: 'Tool output',
line_number: 14,
text,
tool_output_omitted: toolOutputOmitted,
},
],
}),
};
}

function compactionResponse(text: string, includeHistory: boolean) {
return {
ok: true,
json: async () => ({
schema: 'codex-usage-tracker-context-v1',
record_id: 'record-tool-output',
context_mode: 'quick',
visible_char_count: 42,
visible_token_estimate: 11,
omitted: { older_entries: 0 },
entries: [
{
type: 'compaction',
label: 'Compaction',
line_number: 20,
text,
compaction: {
replacement_history_available: true,
replacement_entry_count: 2,
replacement_history: includeHistory ? [{ label: 'summary', text: 'redacted replacement summary' }] : [],
},
},
],
}),
};
}
