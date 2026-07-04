import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, vi, waitFor } from './test-utils/appTestHarness';

describe('React dashboard context entry metadata', () => {
  installAppTestHooks();

  it('hydrates selected-call evidence action labels from dashboard i18n payload', () => {
    window.history.replaceState(null, '', '/?view=calls');
    window.__CODEX_USAGE_BOOT__ = {
      language: 'es',
      language_direction: 'ltr',
      available_languages: [
        { code: 'en', english_name: 'English', native_name: 'English', dir: 'ltr' },
        { code: 'es', english_name: 'Spanish', native_name: 'Español', dir: 'ltr' },
      ],
      translation_catalog: {
        es: {
          'button.enable_context_loading': 'Habilitar la carga de contexto',
          'button.full_serialized_analysis': 'Ejecute un análisis serializado completo',
          'button.include_tool_output': 'Incluir salida de herramienta',
          'button.no_char_limit': 'Sin límite de caracteres',
          'button.show_turn_evidence': 'Mostrar evidencia del registro de turnos',
        },
      },
      api_token: 'side-panel-i18n-token',
      context_api_enabled: false,
      loaded_row_count: 1,
      rows: [
        {
          record_id: 'record-side-panel-i18n',
          call_started_at: '2026-07-01T12:00:00Z',
          thread_name: 'side-panel-i18n-thread',
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

    render(<App />);
    fireEvent.click(screen.getByRole('tab', { name: /Evidence/i }));

    expect(screen.getByRole('button', { name: /Habilitar la carga de contexto/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Mostrar evidencia del registro de turnos/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Ejecute un análisis serializado completo/i })).toBeInTheDocument();
    expect(screen.getByText('Incluir salida de herramienta')).toBeInTheDocument();
    expect(screen.getByText('Sin límite de caracteres')).toBeInTheDocument();
  });

  it('shows timing, token, compaction, and tool-output metadata in selected-call evidence', async () => {
    window.history.replaceState(null, '', '/?view=calls');
    window.__CODEX_USAGE_BOOT__ = {
      api_token: 'test-token',
      context_api_enabled: true,
      loaded_row_count: 1,
      rows: [
        {
          record_id: 'record-metadata',
          call_started_at: '2026-07-01T12:00:00Z',
          thread_name: 'metadata-thread',
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
        record_id: 'record-metadata',
        context_mode: 'quick',
        visible_char_count: 42,
        visible_token_estimate: 11,
        serialized_evidence: {
          raw_json_char_count: 200,
          raw_json_token_estimate: 80,
          raw_line_count: 6,
          token_estimator: 'chars_per_3_75',
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
        entries: [
          {
            type: 'message',
            label: 'Metadata entry',
            line_number: 14,
            text: 'metadata sample',
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
              replacement_history: [],
            },
          },
        ],
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole('tab', { name: /Evidence/i }));
    fireEvent.click(screen.getByRole('button', { name: /Show turn (?:log )?evidence/i }));

    expect(await screen.findByText('metadata sample')).toBeInTheDocument();
    expect(screen.getByText('T+: 1.3s')).toBeInTheDocument();
    expect(screen.getByText('Gap: 250ms')).toBeInTheDocument();
    expect(screen.getByText('Duration: 500ms')).toBeInTheDocument();
    expect(screen.getByText('Entry tokens: 125 total · 60 uncached')).toBeInTheDocument();
    expect(screen.getByText('Session tokens: 480 total · 300 uncached')).toBeInTheDocument();
    expect(screen.getByText('Compaction: 0 replacement entries')).toBeInTheDocument();
    expect(screen.getByText('Tool output: omitted')).toBeInTheDocument();
    expect(screen.getByText('Context Attribution')).toBeInTheDocument();
    expect(screen.getByText('Visible new context estimate')).toBeInTheDocument();
    expect(screen.getByText('Serialized local upper bound')).toBeInTheDocument();
    expect(screen.getByText('Unexplained hidden/serialized input estimate')).toBeInTheDocument();
    expect(screen.getByText('Remaining after serialized bound')).toBeInTheDocument();
    expect(screen.getByText('~11')).toBeInTheDocument();
    expect(screen.getByText('~80')).toBeInTheDocument();
    expect(screen.getByText('200 raw JSON chars · chars_per_3_75 · 6 raw lines')).toBeInTheDocument();
    expect(screen.getByText('~489')).toBeInTheDocument();
    expect(screen.getByText('~420')).toBeInTheDocument();
    expect(screen.getByText('Serialized evidence groups')).toBeInTheDocument();
    expect(screen.getByText('Encrypted reasoning/state payload')).toBeInTheDocument();
    expect(screen.getByText('2 fields · 180 chars')).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });

  it('runs full serialized analysis from deferred selected-call evidence', async () => {
    window.history.replaceState(null, '', '/?view=calls');
    installMetadataBootPayload();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(contextAttributionResponse({ deferred: true }))
      .mockResolvedValueOnce(contextAttributionResponse({ deferred: false }));
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole('tab', { name: /Evidence/i }));
    fireEvent.click(screen.getByRole('button', { name: /Show turn (?:log )?evidence/i }));

    expect(await screen.findByText('Fast estimate loaded; full serialized grouping is deferred.')).toBeInTheDocument();
    expect(screen.getByText('200 raw JSON chars · chars_per_3_75 · fast estimate · 6 raw lines')).toBeInTheDocument();
    fireEvent.click(document.querySelector<HTMLButtonElement>('.serialized-action')!);

    expect(await screen.findByText('Encrypted reasoning/state payload')).toBeInTheDocument();
    expect(screen.getByText('2 fields · 180 chars')).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(String(fetchMock.mock.calls[0][0])).toContain('mode=quick');
    expect(String(fetchMock.mock.calls[1][0])).toContain('mode=full');
  });
});

function installMetadataBootPayload() {
  window.__CODEX_USAGE_BOOT__ = {
    api_token: 'test-token',
    context_api_enabled: true,
    loaded_row_count: 1,
    rows: [
      {
        record_id: 'record-metadata',
        call_started_at: '2026-07-01T12:00:00Z',
        thread_name: 'metadata-thread',
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

function contextAttributionResponse({ deferred }: { deferred: boolean }) {
  return {
    ok: true,
    json: async () => ({
      schema: 'codex-usage-tracker-context-v1',
      record_id: 'record-metadata',
      context_mode: deferred ? 'quick' : 'full',
      visible_char_count: 42,
      visible_token_estimate: 11,
      serialized_evidence: {
        raw_json_char_count: 200,
        raw_json_token_estimate: 80,
        raw_line_count: 6,
        token_estimator: 'chars_per_3_75',
        deferred_buckets: deferred,
        buckets: deferred
          ? []
          : [
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
      entries: [{ type: 'message', label: 'Metadata entry', line_number: 14, text: 'metadata sample' }],
    }),
  };
}
