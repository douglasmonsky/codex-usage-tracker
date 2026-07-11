import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen, vi, waitFor, within } from './test-utils/appTestHarness';

describe('React dashboard calls links presets and URL state', () => {
  installAppTestHooks();

it('ports legacy calls previous-gap, attention, and initiated sorts', () => {
window.__CODEX_USAGE_BOOT__ = {
api_token: 'legacy-sort-token',
context_api_enabled: true,
loaded_row_count: 4,
limit: 3,
rows: [
{
record_id: 'normal-row',
call_started_at: '2026-07-01T10:00:00Z',
thread_name: 'normal-thread',
model: 'o4-mini',
effort: 'medium',
input_tokens: 1_000,
cached_input_tokens: 900,
output_tokens: 100,
total_tokens: 1_100,
estimated_cost_usd: 0.01,
duration_seconds: 20,
previous_call_delta_seconds: 60,
call_initiator: 'assistant',
call_initiator_reason: 'assistant follow-up',
call_initiator_confidence: 'estimated',
},
{
record_id: 'attention-row',
call_started_at: '2026-07-01T10:05:00Z',
thread_name: 'attention-thread',
model: 'o5',
effort: 'high',
input_tokens: 90_000,
cached_input_tokens: 0,
output_tokens: 10_000,
total_tokens: 100_000,
estimated_cost_usd: 2.5,
duration_seconds: 180,
previous_call_delta_seconds: 30,
call_initiator: 'tool',
call_initiator_reason: 'tool-driven continuation',
call_initiator_confidence: 'exact',
primary_signal: 'cache-risk',
recommended_action: 'Review uncached aggregate input before continuing this thread.',
context_window_percent: 0.86,
},
{
record_id: 'gap-row',
call_started_at: '2026-07-01T10:10:00Z',
thread_name: 'gap-thread',
model: 'o4-mini',
effort: 'low',
input_tokens: 2_000,
cached_input_tokens: 1_800,
output_tokens: 200,
total_tokens: 2_200,
estimated_cost_usd: 0.02,
duration_seconds: 10,
previous_call_delta_seconds: 9_000,
call_initiator: 'user',
call_initiator_reason: 'direct user request',
call_initiator_confidence: 'exact',
},
],
};
window.history.replaceState(null, '', '/?view=calls&sort=gap');

render(<App />);

const table = screen.getByRole('table', { name: 'Model calls' });
const firstBodyRowText = () => within(screen.getByRole('table', { name: 'Model calls' })).getAllByRole('row')[1]?.textContent ?? '';

expect(screen.getByLabelText('Sort calls')).toHaveValue('gap');
expect(screen.getByLabelText('Sort direction')).toHaveValue('desc');
expect(screen.getByText('Prev Gap')).toBeInTheDocument();
expect(within(table).getByRole('button', { name: /Sort by Initiated/i })).toBeInTheDocument();
expect(firstBodyRowText()).toContain('gap-thread');
expect(firstBodyRowText()).toContain('150m 0s');

fireEvent.change(screen.getByLabelText('Sort calls'), { target: { value: 'attention' } });
expect(screen.getByLabelText('Sort direction')).toHaveValue('desc');
expect(firstBodyRowText()).toContain('attention-thread');

fireEvent.change(screen.getByLabelText('Sort calls'), { target: { value: 'initiator' } });
expect(screen.getByLabelText('Sort direction')).toHaveValue('asc');
expect(firstBodyRowText()).toContain('normal-thread');
expect(firstBodyRowText()).toContain('assistant');
});

it('hydrates full-page call investigator action labels from dashboard i18n payload', () => {
    window.__CODEX_USAGE_BOOT__ = {
      language: 'es',
      language_direction: 'ltr',
      available_languages: [
        { code: 'en', english_name: 'English', native_name: 'English', dir: 'ltr' },
        { code: 'es', english_name: 'Spanish', native_name: 'Español', dir: 'ltr' },
      ],
      translation_catalog: {
        es: {
        'button.copy_link': 'Copiar enlace',
        'button.back_to_dashboard': 'Volver al tablero',
        'button.enable_context_loading': 'Habilitar la carga de contexto',
          'button.full_serialized_analysis': 'Ejecute un análisis serializado completo',
          'button.include_tool_output': 'Incluir salida de herramienta',
          'button.next_call': 'Próxima llamada',
          'button.no_char_limit': 'Sin límite de caracteres',
        'button.previous_call': 'Convocatoria anterior',
        'button.show_turn_evidence': 'Mostrar evidencia del registro de turnos',
        'call.readout.badge': 'Evidencia exacta + derivada + a demanda',
        'call.readout.evidence_label': 'Estado de la evidencia',
        'call.readout.exact_body': '{input} tokens de entrada = {cached} en caché + {uncached} sin caché; {output} tokens de salida; {cache} reutilización de caché.',
        'call.readout.exact_label': 'Contabilidad exacta del callback',
        'call.readout.next_label': 'Siguiente movimiento diagnóstico',
        'call.readout.previous_label': 'Comparado con la llamada anterior',
        'call.readout.previous_unavailable': 'No hay una llamada anterior cargada para este hilo resuelto, así que los deltas entre llamadas no están disponibles.',
        'call.readout.title': 'Resumen de investigación',
      },
      },
      api_token: 'call-i18n-token',
      context_api_enabled: false,
      loaded_row_count: 2,
      total_available_rows: 2,
      limit: 500,
      rows: [
        {
          record_id: 'i18n-call-current',
          call_started_at: '2026-07-02T10:00:00Z',
          thread_name: 'i18n-thread',
          model: 'codex-1',
          effort: 'high',
          input_tokens: 1_000,
          cached_input_tokens: 400,
          output_tokens: 250,
          total_tokens: 1_250,
          estimated_cost_usd: 0.12,
        },
        {
          record_id: 'i18n-call-next',
          call_started_at: '2026-07-02T09:55:00Z',
          thread_name: 'i18n-thread',
          model: 'o4-mini',
          effort: 'medium',
          input_tokens: 900,
          cached_input_tokens: 500,
          output_tokens: 100,
          total_tokens: 1_000,
          estimated_cost_usd: 0.06,
        },
      ],
    };
    window.history.replaceState(null, '', '/?view=call&record=i18n-call-current');

    render(<App />);

expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
expect(screen.getByRole('button', { name: /Volver al tablero/i })).toBeInTheDocument();
expect(screen.getByText('Resumen de investigación')).toBeInTheDocument();
expect(screen.getByText('Evidencia exacta + derivada + a demanda')).toBeInTheDocument();
expect(screen.getByText('Contabilidad exacta del callback')).toBeInTheDocument();
expect(
  screen.getByText('1,000 tokens de entrada = 400 en caché + 600 sin caché; 250 tokens de salida; 40.0% reutilización de caché.'),
).toBeInTheDocument();
expect(screen.getByText('Comparado con la llamada anterior')).toBeInTheDocument();
expect(
  screen.getByText('No hay una llamada anterior cargada para este hilo resuelto, así que los deltas entre llamadas no están disponibles.'),
).toBeInTheDocument();
expect(screen.getByText('Estado de la evidencia')).toBeInTheDocument();
expect(screen.getByText('Siguiente movimiento diagnóstico')).toBeInTheDocument();
expect(screen.getByRole('button', { name: /Convocatoria anterior/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Próxima llamada/i })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Copiar enlace/i }).length).toBeGreaterThan(1);
    expect(screen.getByRole('button', { name: /Habilitar la carga de contexto/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Mostrar evidencia del registro de turnos/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Ejecute un análisis serializado completo/i })).toBeInTheDocument();
    expect(screen.getByText('Incluir salida de herramienta')).toBeInTheDocument();
    expect(screen.getByText('Sin límite de caracteres')).toBeInTheDocument();
  });

it('opens Investigate and detailed overview calls without homepage presets', () => {
  render(<App />);
  expect(screen.queryByText('Investigation Presets')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Investigate' }));
  expect(screen.getByRole('heading', { name: 'Investigate' })).toBeInTheDocument();
  expect(window.location.search).toContain('view=investigator');
  fireEvent.click(screen.getByRole('button', { name: /^Overview$/i }));
  fireEvent.click(screen.getByRole('button', { name: 'Open investigator for thread-1a2b3c codex-1' }));
  expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
  expect(screen.getByText('thread-1a2b3c / codex-1')).toBeInTheDocument();
  expect(window.location.search).toContain('record=fixture-call-3');
});

it('clears active investigation presets without leaving the current view', () => {
  window.history.replaceState(null, '', '/?view=calls&preset=context-bloat');
  render(<App />);
  expect(screen.getByRole('heading', { name: 'Calls' })).toBeInTheDocument();
  expect(window.location.search).toContain('view=calls');
  expect(window.location.search).toContain('preset=context-bloat');
  expect(screen.getByRole('button', { name: /Clear Context Bloat/i })).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Clear Context Bloat/i }));

  expect(screen.getByRole('heading', { name: 'Calls' })).toBeInTheDocument();
  expect(window.location.search).toContain('view=calls');
  expect(window.location.search).not.toContain('preset=');
  expect(screen.queryByRole('button', { name: /Clear Context Bloat/i })).not.toBeInTheDocument();
  expect(screen.getAllByText('Investigation preset cleared').length).toBeGreaterThan(0);
});

it('hydrates active preset clear label dashboard i18n payload', () => {
  window.localStorage?.removeItem('codex-usage-dashboard-language');
  window.history.replaceState(null, '', '/?view=calls&preset=context-bloat');
  window.__CODEX_USAGE_BOOT__ = {
    language: 'es',
    language_direction: 'ltr',
    available_languages: [
      { code: 'en', english_name: 'English', native_name: 'English', dir: 'ltr' },
      { code: 'es', english_name: 'Spanish', native_name: 'Español', dir: 'ltr' },
    ],
    translation_catalog: {
      es: {
        'button.clear': 'Borrar',
      },
    },
    loaded_row_count: 1,
    rows: [
      {
        record_id: 'preset-clear-i18n-row',
        call_started_at: '2026-07-01T12:00:00Z',
        thread_name: 'preset-clear-i18n-thread',
        model: 'codex-1',
        effort: 'high',
        input_tokens: 1000,
        cached_input_tokens: 100,
        output_tokens: 100,
        total_tokens: 1100,
        estimated_cost_usd: 0.1,
      },
    ],
  };

  render(<App />);

  expect(screen.getByRole('heading', { name: 'Calls' })).toBeInTheDocument();
  const clearButton = screen.getByRole('button', { name: /Borrar Context Bloat/i });
  fireEvent.click(clearButton);

  expect(window.location.search).toContain('view=calls');
  expect(window.location.search).not.toContain('preset=');
  expect(screen.queryByRole('button', { name: /Borrar Context Bloat/i })).not.toBeInTheDocument();
});

it('filters calls by pricing and credit confidence', () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Calls$/i }));

  fireEvent.change(screen.getByLabelText('Confidence filter'), { target: { value: 'cost-estimated' } });

  expect(screen.getByText('thread-7b2e91')).toBeInTheDocument();
  expect(screen.getByText('thread-2f9e7d')).toBeInTheDocument();
  expect(screen.queryByText('thread-9f3a1c')).not.toBeInTheDocument();
});

it('hydrates legacy pricing confidence URL alias', async () => { window.history.replaceState(null, '', '/?view=calls&pricing=estimated'); render(<App />); expect(screen.getByRole('heading', { name: 'Calls' })).toBeInTheDocument(); expect(screen.getByLabelText('Confidence filter')).toHaveValue('cost-estimated'); expect(screen.getByText('thread-7b2e91')).toBeInTheDocument(); expect(screen.getByText('thread-2f9e7d')).toBeInTheDocument(); expect(screen.queryByText('thread-9f3a1c')).not.toBeInTheDocument(); await waitFor(() => { const params = new URLSearchParams(window.location.search); expect(params.get('confidence')).toBe('cost-estimated'); expect(params.get('pricing')).toBeNull(); }); }); it('filters calls by legacy unpriced cost and credit override confidence', () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Calls$/i }));

  fireEvent.change(screen.getByLabelText('Confidence filter'), { target: { value: 'cost-unpriced' } });
  expect(screen.getByText('thread-8d7c6b')).toBeInTheDocument();
  expect(screen.queryByText('thread-9f3a1c')).not.toBeInTheDocument();

  fireEvent.change(screen.getByLabelText('Confidence filter'), { target: { value: 'credit-override' } });
  expect(screen.getByText('thread-0f1e2d')).toBeInTheDocument();
  expect(screen.queryByText('thread-8d7c6b')).not.toBeInTheDocument();
});

it('filters calls by legacy time presets', () => {
vi.useFakeTimers();
vi.setSystemTime(new Date('2026-07-02T12:00:00Z'));
window.__CODEX_USAGE_BOOT__ = { rows: [
{ record_id: 'recent-time-row', call_started_at: '2026-07-02T10:00:00Z', thread_name: 'recent-time-thread', model: 'o4-mini', effort: 'medium', input_tokens: 100, cached_input_tokens: 40, output_tokens: 10, total_tokens: 110, estimated_cost_usd: 0.01 },
{ record_id: 'old-time-row', call_started_at: '2026-06-15T10:00:00Z', thread_name: 'old-time-thread', model: 'o4-mini', effort: 'medium', input_tokens: 100, cached_input_tokens: 40, output_tokens: 10, total_tokens: 110, estimated_cost_usd: 0.01 },
] };
render(<App />);
fireEvent.click(screen.getByRole('button', { name: /^Calls$/i }));
fireEvent.change(screen.getByLabelText('Time filter'), { target: { value: 'last-7-days' } });
expect(screen.getByText('recent-time-thread')).toBeInTheDocument();
expect(screen.queryByText('old-time-thread')).not.toBeInTheDocument();
});

it('hydrates and copies shareable calls filter links', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText },
  });
  window.history.replaceState(
    null,
    '',
    '/?view=calls&record=stale-record&call_q=thread-2f9e7d&model=o4-mini&effort=medium&confidence=cost-estimated&density=roomy',
  );

  render(<App />);

  expect(screen.getByRole('heading', { name: 'Calls' })).toBeInTheDocument();
  expect(screen.getByText('thread-2f9e7d')).toBeInTheDocument();
  expect(screen.queryByText('thread-7b2e91')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Roomy' })).toHaveAttribute('aria-pressed', 'true');

  fireEvent.click(screen.getByRole('button', { name: /Copy view/i }));

  await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
  const copiedUrl = new URL(writeText.mock.calls[0][0]);
  expect(copiedUrl.searchParams.get('view')).toBe('calls');
  expect(copiedUrl.searchParams.get('record')).toBeNull();
  expect(copiedUrl.searchParams.get('call_q')).toBe('thread-2f9e7d');
  expect(copiedUrl.searchParams.get('model')).toBe('o4-mini');
  expect(copiedUrl.searchParams.get('effort')).toBe('medium');
  expect(copiedUrl.searchParams.get('confidence')).toBe('cost-estimated');
  expect(copiedUrl.searchParams.get('density')).toBe('roomy');
  expect(screen.getByText('Copied Calls view link')).toBeInTheDocument();
});

it('hydrates and copies legacy custom calls date ranges', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText },
  });
  window.__CODEX_USAGE_BOOT__ = {
    rows: [
      {
        record_id: 'custom-range-match',
        call_started_at: '2026-07-01T14:00:00Z',
        thread_name: 'custom-range-thread',
        model: 'o4-mini',
        effort: 'medium',
        input_tokens: 100,
        cached_input_tokens: 40,
        output_tokens: 10,
        total_tokens: 110,
        estimated_cost_usd: 0.01,
      },
      {
        record_id: 'custom-range-miss',
        call_started_at: '2026-07-02T14:00:00Z',
        thread_name: 'outside-range-thread',
        model: 'o4-mini',
        effort: 'medium',
        input_tokens: 100,
        cached_input_tokens: 40,
        output_tokens: 10,
        total_tokens: 110,
        estimated_cost_usd: 0.01,
      },
    ],
  };
  window.history.replaceState(null, '', '/?view=calls&date=custom&from=2026-07-01&to=2026-07-01');

  render(<App />);

  expect(screen.getByRole('heading', { name: 'Calls' })).toBeInTheDocument();
  expect(screen.getByText('custom-range-thread')).toBeInTheDocument();
  expect(screen.queryByText('outside-range-thread')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Start date')).toHaveValue('2026-07-01');
  expect(screen.getByLabelText('End date')).toHaveValue('2026-07-01');

  fireEvent.click(screen.getByRole('button', { name: /Copy view/i }));

  await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
  const copiedUrl = new URL(writeText.mock.calls[0][0]);
  expect(copiedUrl.searchParams.get('view')).toBe('calls');
  expect(copiedUrl.searchParams.get('date')).toBe('custom');
  expect(copiedUrl.searchParams.get('from')).toBe('2026-07-01');
  expect(copiedUrl.searchParams.get('to')).toBe('2026-07-01');
});

it('hydrates and copies legacy calls sort state', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText },
  });
  window.history.replaceState(null, '', '/?view=calls&sort=cache&direction=desc');

  render(<App />);

  expect(screen.getByLabelText('Sort calls')).toHaveValue('cache');
  expect(screen.getByLabelText('Sort direction')).toHaveValue('desc');
  const tableRows = within(screen.getByRole('table', { name: 'Model calls' })).getAllByRole('row');
  expect(within(tableRows[1]).getByText('thread-1a2b3c')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Copy view/i }));

  await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
  const copiedUrl = new URL(writeText.mock.calls[0][0]);
  expect(copiedUrl.searchParams.get('view')).toBe('calls');
  expect(copiedUrl.searchParams.get('sort')).toBe('cache');
  expect(copiedUrl.searchParams.get('direction')).toBe('desc');
});

});
