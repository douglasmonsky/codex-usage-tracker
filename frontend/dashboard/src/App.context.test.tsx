import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, vi, waitFor } from './test-utils/appTestHarness';

describe('React dashboard context and live call APIs', () => {
  installAppTestHooks();

it('hydrates direct call investigator URLs through the live call API when the row is not loaded', async () => {
    window.history.replaceState(null, '', '/?view=call&record=record-hydrated');
    window.__CODEX_USAGE_BOOT__ = {
      api_token: 'test-token',
      context_api_enabled: false,
      loaded_row_count: 1,
      rows: [
        {
          record_id: 'record-loaded',
          call_started_at: '2026-07-01T11:00:00Z',
          thread_name: 'loaded-thread',
          model: 'o4-mini',
          effort: 'medium',
          input_tokens: 900,
          cached_input_tokens: 300,
          output_tokens: 90,
          total_tokens: 990,
          estimated_cost_usd: 0.02,
        },
      ],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void init;
      const url = String(input);
      if (!url.includes('/api/call?')) {
        throw new Error(`Unexpected request: ${url}`);
      }
      return {
        ok: true,
        json: async () => ({
          schema: 'codex-usage-tracker-call-v1',
          record: {
            record_id: 'record-hydrated',
            call_started_at: '2026-07-01T12:00:00Z',
            thread_name: 'hydrated-thread',
            model: 'o5',
            effort: 'high',
            input_tokens: 2000,
            cached_input_tokens: 400,
            output_tokens: 250,
            total_tokens: 2250,
            usage_credits: 0.25,
            estimated_cost_usd: 0.2,
            recommended_action: 'Review hydrated aggregate call.',
          },
          previous_record: {
            record_id: 'record-prev',
            call_started_at: '2026-07-01T11:55:00Z',
            thread_name: 'hydrated-thread',
            model: 'o5',
            effort: 'high',
            input_tokens: 1000,
            cached_input_tokens: 500,
            output_tokens: 100,
            total_tokens: 1100,
            estimated_cost_usd: 0.1,
          },
          next_record: {
            record_id: 'record-next',
            call_started_at: '2026-07-01T12:05:00Z',
            thread_name: 'hydrated-thread',
            model: 'o5',
            effort: 'high',
            input_tokens: 1100,
            cached_input_tokens: 550,
            output_tokens: 120,
            total_tokens: 1220,
            estimated_cost_usd: 0.12,
          },
        }),
      } as Response;
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);

    expect(await screen.findByText('hydrated-thread / o5')).toBeInTheDocument();
    expect(screen.getByText('Hydrated from /api/call')).toBeInTheDocument();
    expect(screen.getAllByText('Review hydrated aggregate call.').length).toBeGreaterThan(0);
    expect(screen.getByText('Cache Accounting')).toBeInTheDocument();
    expect(screen.getByText('Cache Accounting Delta')).toBeInTheDocument();
    expect(screen.getByText('Uncached spike')).toBeInTheDocument();
    expect(screen.getByText('Fresh input rose sharply compared with the previous call in this resolved thread.')).toBeInTheDocument();
    expect(screen.getByText('Next: Inspect the most recent evidence entries first; the spike is in fresh uncached input, not cached history.')).toBeInTheDocument();
    expect(screen.getByText('Uncached input rose by 1,100 while cached input fell by 100.')).toBeInTheDocument();
    expect(screen.getByText('+1,000')).toBeInTheDocument();
    expect(screen.getByText('-100')).toBeInTheDocument();
    expect(screen.getByText('+1,100')).toBeInTheDocument();
    expect(screen.getByText('-30.0pp')).toBeInTheDocument();
    expect(screen.getByText('Thread Context')).toBeInTheDocument();
expect(screen.getByText('Thread timeline')).toBeInTheDocument();
expect(screen.getByText('Models in thread')).toBeInTheDocument();
expect(screen.getAllByRole('button', { name: /^Open$/i }).some(button => !button.hasAttribute('disabled'))).toBe(true);
expect(screen.getByRole('button', { name: /Previous/i })).not.toBeDisabled();
expect(screen.getByRole('button', { name: /Next/i })).not.toBeDisabled();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/call?');
    expect(String(fetchMock.mock.calls[0][0])).toContain('record_id=record-hydrated');
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        cache: 'no-store',
        headers: expect.objectContaining({
          'X-Codex-Usage-Token': 'test-token',
        }),
      }),
    );
  });

  it('loads selected-call context evidence through the localhost API', async () => {
    window.history.replaceState(null, '', '/?view=calls');
    window.__CODEX_USAGE_BOOT__ = {
      api_token: 'test-token',
      context_api_enabled: true,
      loaded_row_count: 1,
      rows: [
        {
          record_id: 'record-context-1',
          call_started_at: '2026-07-01T12:00:00Z',
          thread_name: 'context-thread',
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
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'codex-usage-tracker-context-v1',
        record_id: 'record-context-1',
        context_mode: 'full',
        visible_char_count: 42,
        visible_token_estimate: 11,
        omitted: { older_entries: 0 },
        entries: [{ type: 'message', label: 'User prompt', line_number: 14, text: 'redacted context sample' }],
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

render(<App />);
fireEvent.click(screen.getByRole('tab', { name: /Evidence/i }));
fireEvent.change(screen.getByLabelText('Side panel context entries'), { target: { value: '50' } });
fireEvent.click(screen.getByLabelText('Include compaction history'));
fireEvent.click(screen.getByRole('button', { name: /(?:Show full analysis|Run full serialized analysis)/i }));

    expect(await screen.findByText('redacted context sample')).toBeInTheDocument();
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
expect(String(fetchMock.mock.calls[0][0])).toContain('/api/context?');
expect(String(fetchMock.mock.calls[0][0])).toContain('record_id=record-context-1');
expect(String(fetchMock.mock.calls[0][0])).toContain('mode=full');
expect(String(fetchMock.mock.calls[0][0])).toContain('include_compaction_history=1');
expect(String(fetchMock.mock.calls[0][0])).toContain('max_entries=50');
expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        cache: 'no-store',
        headers: expect.objectContaining({
          'X-Codex-Usage-Token': 'test-token',
        }),
      }),
    );
  });

  it('loads full-page investigator context through the localhost API', async () => {
    window.history.replaceState(null, '', '/?view=call&record=record-context-1');
    window.__CODEX_USAGE_BOOT__ = {
      api_token: 'test-token',
      context_api_enabled: true,
      loaded_row_count: 1,
      rows: [
        {
          record_id: 'record-context-1',
          call_started_at: '2026-07-01T12:00:00Z',
          thread_name: 'context-thread',
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
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'codex-usage-tracker-context-v1',
        record_id: 'record-context-1',
        context_mode: 'full',
      visible_char_count: 42,
      visible_token_estimate: 11,
      serialized_evidence: {
        raw_json_char_count: 200,
        raw_json_token_estimate: 80,
        buckets: [
          {
            key: 'encrypted_reasoning_state',
            label: 'Encrypted reasoning/state payload',
            note: 'Opaque local payload; counted as serialized evidence, not readable text.',
            count: 2,
            char_count: 180,
            token_estimate: 45,
          },
        ],
      },
      omitted: { older_entries: 0 },
      entries: [{
        type: 'message',
        label: 'User prompt',
        line_number: 14,
        text: 'redacted investigator sample',
        tool_output_omitted: true,
        action_timing: {
          since_turn_start_ms: 1250,
          since_previous_entry_ms: 250,
          reported_duration_ms: 500,
          duration_source: 'event.duration_ms',
        },
        token_usage: {
          last_token_usage: {
            input_tokens: 100,
            cached_input_tokens: 40,
            uncached_input_tokens: 60,
            output_tokens: 25,
            total_tokens: 125,
          },
          total_token_usage: {
            input_tokens: 400,
            cached_input_tokens: 100,
            uncached_input_tokens: 300,
            output_tokens: 80,
            total_tokens: 480,
          },
        },
        compaction: {
          replacement_history_available: true,
          replacement_history: [{ label: 'summary', text: 'redacted summary' }],
        },
      }],
      }),
    });
  vi.stubGlobal('fetch', fetchMock);

  render(<App />);
  fireEvent.change(screen.getByLabelText('Context entries'), { target: { value: '50' } });
  fireEvent.click(screen.getByLabelText('Include compaction history'));
  fireEvent.click(screen.getByRole('button', { name: /(?:Show full analysis|Run full serialized analysis)/i }));

    expect(await screen.findByText('redacted investigator sample')).toBeInTheDocument();
  await waitFor(() => {
    expect(screen.getByText('Evidence analyzed: 1 selected-turn entries, 42 visible redacted chars, 11 visible tokens. Serialized local upper bound: 80 tokens.')).toBeInTheDocument();
  });
  expect(screen.getByText('Context Attribution')).toBeInTheDocument();
  expect(screen.getByText('Visible new context estimate')).toBeInTheDocument();
  expect(screen.getByText('Serialized local upper bound')).toBeInTheDocument();
  expect(screen.getByText('Unexplained hidden/serialized input estimate')).toBeInTheDocument();
  expect(screen.getByText('Remaining after serialized bound')).toBeInTheDocument();
  expect(screen.getByText('~11')).toBeInTheDocument();
  expect(screen.getByText('~80')).toBeInTheDocument();
  expect(screen.getByText('~489')).toBeInTheDocument();
  expect(screen.getByText('~420')).toBeInTheDocument();
  expect(screen.getByText('Serialized evidence groups')).toBeInTheDocument();
  expect(screen.getByText('Upper-bound local JSONL structure; not exact prompt text.')).toBeInTheDocument();
  expect(screen.getByText('Encrypted reasoning/state payload')).toBeInTheDocument();
  expect(screen.getByText('2 fields · 180 chars')).toBeInTheDocument();
  expect(screen.getByText('Opaque local payload; counted as serialized evidence, not readable text.')).toBeInTheDocument();
  expect(screen.getByText('T+: 1.3s')).toBeInTheDocument();
  expect(screen.getByText('Gap: 250ms')).toBeInTheDocument();
  expect(screen.getByText('Duration: 500ms')).toBeInTheDocument();
  expect(screen.getByText('Entry tokens: 125 total · 60 uncached')).toBeInTheDocument();
  expect(screen.getByText('Session tokens: 480 total · 300 uncached')).toBeInTheDocument();
  expect(screen.getByText('Compaction: 1 replacement entries')).toBeInTheDocument();
  expect(screen.getByText('Tool output: omitted')).toBeInTheDocument();
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  expect(String(fetchMock.mock.calls[0][0])).toContain('/api/context?');
  expect(String(fetchMock.mock.calls[0][0])).toContain('record_id=record-context-1');
  expect(String(fetchMock.mock.calls[0][0])).toContain('mode=full');
  expect(String(fetchMock.mock.calls[0][0])).toContain('include_compaction_history=1');
  expect(String(fetchMock.mock.calls[0][0])).toContain('max_entries=50');
  expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        cache: 'no-store',
        headers: expect.objectContaining({
          'X-Codex-Usage-Token': 'test-token',
        }),
      }),
    );
  });

  it('loads older selected-call context when entries were omitted', async () => {
    window.history.replaceState(null, '', '/?view=calls');
    window.__CODEX_USAGE_BOOT__ = {
      api_token: 'test-token',
      context_api_enabled: true,
      loaded_row_count: 1,
      rows: [
        {
          record_id: 'record-context-older',
          call_started_at: '2026-07-01T12:00:00Z',
          thread_name: 'context-older-thread',
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
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          schema: 'codex-usage-tracker-context-v1',
          record_id: 'record-context-older',
          context_mode: 'quick',
          visible_char_count: 20,
          visible_token_estimate: 5,
          omitted: { older_entries: 4, max_entries: 20 },
          entries: [{ type: 'message', label: 'Recent prompt', line_number: 20, text: 'recent context sample' }],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          schema: 'codex-usage-tracker-context-v1',
          record_id: 'record-context-older',
          context_mode: 'quick',
          visible_char_count: 60,
          visible_token_estimate: 15,
          omitted: { older_entries: 0, max_entries: 40 },
          entries: [{ type: 'message', label: 'Older prompt', line_number: 5, text: 'older context sample' }],
        }),
      });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole('tab', { name: /Evidence/i }));
    fireEvent.click(screen.getByRole('button', { name: /Show turn (?:log )?evidence/i }));

    expect(await screen.findByText('recent context sample')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Load older (?:context|entries)/i }));

    expect(await screen.findByText('older context sample')).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(String(fetchMock.mock.calls[1][0])).toContain('max_entries=40');
  });

  it('loads older full-page investigator context when entries were omitted', async () => {
    window.history.replaceState(null, '', '/?view=call&record=record-context-older');
    window.__CODEX_USAGE_BOOT__ = {
      api_token: 'test-token',
      context_api_enabled: true,
      loaded_row_count: 1,
      rows: [
        {
          record_id: 'record-context-older',
          call_started_at: '2026-07-01T12:00:00Z',
          thread_name: 'context-older-thread',
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
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          schema: 'codex-usage-tracker-context-v1',
          record_id: 'record-context-older',
          context_mode: 'quick',
          visible_char_count: 20,
          visible_token_estimate: 5,
          omitted: { older_entries: 2, max_entries: 20 },
          entries: [{ type: 'message', label: 'Recent prompt', line_number: 20, text: 'recent full-page sample' }],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          schema: 'codex-usage-tracker-context-v1',
          record_id: 'record-context-older',
          context_mode: 'quick',
          visible_char_count: 60,
          visible_token_estimate: 15,
          omitted: { older_entries: 0, max_entries: 40 },
          entries: [{ type: 'message', label: 'Older prompt', line_number: 5, text: 'older full-page sample' }],
        }),
      });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Show turn (?:log )?evidence/i }));

    expect(await screen.findByText('recent full-page sample')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Load older (?:context|entries)/i }));

  expect(await screen.findByText('older full-page sample')).toBeInTheDocument();
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  expect(String(fetchMock.mock.calls[1][0])).toContain('max_entries=40');
});

it('hydrates loaded evidence readout body dashboard i18n payload', async () => {
  window.history.replaceState(null, '', '/?view=call&record=record-evidence-i18n');
  window.__CODEX_USAGE_BOOT__ = {
    language: 'es',
    language_direction: 'ltr',
    available_languages: [
      { code: 'en', english_name: 'English', native_name: 'English', dir: 'ltr' },
      { code: 'es', english_name: 'Spanish', native_name: 'Español', dir: 'ltr' },
    ],
    translation_catalog: {
      es: {
        'call.readout.evidence_analyzed':
          'Evidencia analizada: {totalEntries} entradas del turno seleccionado, {visibleChars} caracteres visibles redactados, {visibleTokens} tokens visibles mediante {estimator}. {serializedDetail} {renderedEntries} entradas mostradas inicialmente.',
        'call.readout.evidence_serialized_bound':
          'Límite superior local serializado: {tokens} tokens de {chars} caracteres JSON sin procesar.',
      },
    },
    api_token: 'test-token',
    context_api_enabled: true,
    loaded_row_count: 1,
    rows: [
      {
        record_id: 'record-evidence-i18n',
        call_started_at: '2026-07-01T12:00:00Z',
        thread_name: 'evidence-i18n-thread',
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
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      schema: 'codex-usage-tracker-context-v1',
      record_id: 'record-evidence-i18n',
      context_mode: 'full',
      visible_char_count: 42,
      visible_token_estimate: 11,
      visible_token_estimator: 'chars_per_4_fallback',
      serialized_evidence: {
        raw_json_char_count: 200,
        raw_json_token_estimate: 80,
      },
      omitted: { older_entries: 0 },
      entries: [{ type: 'message', label: 'User prompt', line_number: 14, text: 'redacted evidence i18n sample' }],
    }),
  });
  vi.stubGlobal('fetch', fetchMock);

  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /Show turn (?:log )?evidence/i }));

  expect(await screen.findByText('redacted evidence i18n sample')).toBeInTheDocument();
  await waitFor(() =>
    expect(document.body.textContent).toContain(
      'Evidencia analizada: 1 entradas del turno seleccionado, 42 caracteres visibles redactados, 11 tokens visibles mediante chars_per_4_fallback. Límite superior local serializado: 80 tokens de 200 caracteres JSON sin procesar. 1 entradas mostradas inicialmente.',
    ),
  );
});
});
