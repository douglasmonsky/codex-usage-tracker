import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, vi, waitFor, within } from './test-utils/appTestHarness';

describe('React dashboard context evidence cache', () => {
  installAppTestHooks();

  it('reuses loaded evidence when returning to the side-panel Evidence tab', async () => {
    window.history.replaceState(null, '', '/?view=calls&record=record-context-cache');
    installContextCacheBootPayload();
    const fetchMock = vi.fn().mockResolvedValue(contextResponse('cached side-panel sample'));
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole('tab', { name: /Evidence/i }));
    fireEvent.click(screen.getByRole('button', { name: /Show turn (?:log )?evidence/i }));

    expect(await screen.findByText('cached side-panel sample')).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole('tab', { name: /Summary/i }));
    expect(screen.queryByText('cached side-panel sample')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: /Evidence/i }));

    expect(await screen.findByText('cached side-panel sample')).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });

  it('restores opened context entries and scroll positions when returning to Evidence', async () => {
    window.history.replaceState(null, '', '/?view=calls&record=record-context-cache');
    installContextCacheBootPayload();
    const fetchMock = vi.fn().mockResolvedValue(contextEntriesResponse(['context entry one', 'context entry two']));
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole('tab', { name: /Evidence/i }));
    fireEvent.click(screen.getByRole('button', { name: /Show turn (?:log )?evidence/i }));

    expect(await screen.findByText('context entry two')).toBeInTheDocument();
    const entries = contextEntries();
    expect(entries[1]).not.toHaveAttribute('open');
fireEvent.click(entries[1].querySelector('summary') as HTMLElement);
await waitFor(() => expect(entries[1]).toHaveAttribute('open'));
    const scroller = entries[1].querySelector('pre') as HTMLPreElement;
    scroller.scrollTop = 37;
    fireEvent.scroll(scroller);

    fireEvent.click(screen.getByRole('tab', { name: /Summary/i }));
    fireEvent.click(screen.getByRole('tab', { name: /Evidence/i }));

const restoredEntries = contextEntries();
await waitFor(() => expect(restoredEntries[1]).toHaveAttribute('open'));
    expect((restoredEntries[1].querySelector('pre') as HTMLPreElement).scrollTop).toBe(37);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });

  it('restores show-all context entry depth across tabs and full-page investigator', async () => {
    window.history.replaceState(null, '', '/?view=calls&record=record-context-cache');
    installContextCacheBootPayload();
    const fetchMock = vi.fn().mockResolvedValue(
      contextEntriesResponse(Array.from({ length: 12 }, (_, index) => `context depth entry ${index + 1}`)),
    );
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole('tab', { name: /Evidence/i }));
    fireEvent.click(screen.getByRole('button', { name: /Show turn (?:log )?evidence/i }));

    expect(await screen.findByText('context depth entry 8')).toBeInTheDocument();
    expect(screen.queryByText('context depth entry 12')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Show all 12 returned entries/i }));
    expect(await screen.findByText('context depth entry 12')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: /Summary/i }));
    fireEvent.click(screen.getByRole('tab', { name: /Evidence/i }));
    expect(await screen.findByText('context depth entry 12')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^Open investigator$/i }));
    expect(await screen.findByText('context depth entry 12')).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });

  it('reuses side-panel evidence in the full-page Call Investigator', async () => {
    window.history.replaceState(null, '', '/?view=calls&record=record-context-cache');
    installContextCacheBootPayload();
    const fetchMock = vi.fn().mockResolvedValue(serializedContextResponse('cached full-page sample'));
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole('tab', { name: /Evidence/i }));
    fireEvent.click(screen.getByRole('button', { name: /Show turn (?:log )?evidence/i }));

    expect(await screen.findByText('cached full-page sample')).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole('button', { name: /^Open investigator$/i }));

    expect(await screen.findByText('cached full-page sample')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
    expect(screen.getAllByText('Serialized evidence groups').length).toBeGreaterThan(0);
    expect(screen.getByText('Full prompt envelopes')).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });

  it('runs full serialized analysis from full-page Context Attribution', async () => {
    window.history.replaceState(null, '', '/?view=call&record=record-context-cache');
    installContextCacheBootPayload();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(deferredSerializedContextResponse('deferred attribution sample'))
      .mockResolvedValueOnce(serializedContextResponse('full attribution sample', 'full'));
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Show turn (?:log )?evidence/i }));

    expect(await screen.findByText('deferred attribution sample')).toBeInTheDocument();
    const attributionPanel = screen.getByText('Context Attribution').closest('section') as HTMLElement;
    fireEvent.click(within(attributionPanel).getByRole('button', { name: /Run full serialized analysis/i }));

    expect(await screen.findByText('full attribution sample')).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(String(fetchMock.mock.calls[1][0])).toContain('mode=full');
  });

  it('restores non-default side-panel context options in the full-page Call Investigator', async () => {
    window.history.replaceState(null, '', '/?view=calls&record=record-context-cache');
    installContextCacheBootPayload();
    const fetchMock = vi.fn().mockResolvedValue(contextResponse('cached full-analysis option sample'));
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole('tab', { name: /Evidence/i }));
    fireEvent.change(screen.getByLabelText('Side panel context entries'), { target: { value: '50' } });
    fireEvent.click(screen.getByLabelText('Include compaction history'));
    fireEvent.click(screen.getByRole('button', { name: /Run full serialized analysis/i }));

    expect(await screen.findByText('cached full-analysis option sample')).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0][0])).toContain('mode=full');
    expect(String(fetchMock.mock.calls[0][0])).toContain('include_compaction_history=1');
    expect(String(fetchMock.mock.calls[0][0])).toContain('max_entries=50');

    fireEvent.click(screen.getByRole('button', { name: /^Open investigator$/i }));

    expect(await screen.findByText('cached full-analysis option sample')).toBeInTheDocument();
    expect(screen.getByLabelText('Context mode')).toHaveValue('full');
    expect(screen.getByLabelText('Context entries')).toHaveValue('50');
    expect(screen.getByLabelText('Include compaction history')).toBeChecked();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });
});

function installContextCacheBootPayload() {
  window.__CODEX_USAGE_BOOT__ = {
    api_token: 'test-token',
    context_api_enabled: true,
    loaded_row_count: 1,
    rows: [
      {
        record_id: 'record-context-cache',
        call_started_at: '2026-07-01T12:00:00Z',
        thread_name: 'context-cache-thread',
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

function contextResponse(text: string) {
  return contextEntriesResponse([text]);
}

function serializedContextResponse(text: string, contextMode = 'quick') {
  const response = contextEntriesResponse([text]);
  return {
    ...response,
    json: async () => ({
      ...(await response.json()),
      context_mode: contextMode,
      serialized_evidence: {
        raw_json_token_estimate: 720,
        raw_json_char_count: 2880,
        token_estimator: 'chars_per_4_fallback',
        buckets: [
          {
            key: 'prompt_envelopes',
            label: 'Full prompt envelopes',
            count: 3,
            char_count: 1800,
            token_estimate: 450,
          },
        ],
      },
    }),
  };
}

function deferredSerializedContextResponse(text: string) {
  const response = contextEntriesResponse([text]);
  return {
    ...response,
    json: async () => ({
      ...(await response.json()),
      serialized_evidence: {
        raw_json_token_estimate: 720,
        raw_json_char_count: 2880,
        token_estimator: 'chars_per_4_fallback',
        deferred: true,
        deferred_buckets: true,
      },
    }),
  };
}

function contextEntriesResponse(texts: string[]) {
  return {
    ok: true,
    json: async () => ({
      schema: 'codex-usage-tracker-context-v1',
      record_id: 'record-context-cache',
      context_mode: 'quick',
      include_tool_output: false,
      visible_char_count: 42,
      visible_token_estimate: 11,
      omitted: { older_entries: 0 },
      entries: texts.map((text, index) => ({
        type: 'message',
        label: `Entry ${index + 1}`,
        line_number: 14 + index,
        text,
      })),
    }),
  };
}

function contextEntries() {
  return [...document.querySelectorAll('details.context-entry')];
}
