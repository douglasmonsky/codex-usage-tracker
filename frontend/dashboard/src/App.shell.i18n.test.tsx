import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen } from './test-utils/appTestHarness';

describe('React dashboard shell i18n', () => {
  installAppTestHooks();

it('keeps the React home route labeled Overview when legacy Insights translations are present', () => {
  window.__CODEX_USAGE_BOOT__ = {
    translation_catalog: {
      en: {
        'dashboard.view.insights': 'Insights',
      },
    },
    rows: [],
  };

  render(<App />);

  expect(screen.getByRole('button', { name: /^Overview$/i })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.queryByRole('button', { name: /^Insights$/i })).not.toBeInTheDocument();
});

it('hydrates legacy language selector from dashboard i18n payload', () => {
  window.localStorage?.removeItem('codex-usage-dashboard-language');
  window.__CODEX_USAGE_BOOT__ = {
    default_load_window: 'rows',
    load_window: 'rows',
    limit: 500,
    language: 'es',
    language_direction: 'ltr',
    available_languages: [
      { code: 'en', english_name: 'English', native_name: 'English', dir: 'ltr' },
      { code: 'es', english_name: 'Spanish', native_name: 'Español', dir: 'ltr' },
    ],
    translation_catalog: {
        en: {
          'badge.live': 'Live',
          'button.copy_link': 'Copy link',
          'button.export_csv': 'Export CSV',
          'button.load_more': 'Load more',
          'button.open_investigator': 'Open investigator',
          'button.refresh': 'Refresh',
          'button.top': 'Top',
          'dashboard.eyebrow': 'Local Codex analytics',
          'dashboard.view.calls': 'Calls',
          'filter.search': 'Search dashboard',
          'language.label': 'Language',
          'nav.history': 'History',
          'nav.load': 'Load',
          'status.static': 'Static',
        },
        es: {
          'badge.live': 'en vivo',
          'button.copy_link': 'Copiar enlace',
          'button.export_csv': 'Exportar CSV',
          'button.load_more': 'Cargar más',
          'button.open_investigator': 'Investigador abierto',
          'button.refresh': 'Actualizar',
          'button.top': 'Arriba',
          'dashboard.eyebrow': 'Análisis locales de Codex',
          'dashboard.view.calls': 'Llamadas',
          'filter.search': 'Buscar tablero',
          'filter.search_placeholder': 'Hilo, cwd, modelo',
          'language.label': 'Idioma',
          'nav.history': 'Historial',
          'nav.load': 'Cargar',
          'nav.live': 'En vivo',
          'option.active_sessions_only': 'Activo',
          'option.all_history': 'Todo el historial',
          'status.static': 'estática',
        },
      },
      rows: [
        {
          record_id: 'i18n-action-row',
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
      ],
    };

  render(<App />);

  expect(document.documentElement.lang).toBe('es');
  expect(screen.getByLabelText('Idioma')).toHaveValue('es');
    expect(screen.getByRole('button', { name: /Llamadas/i })).toBeInTheDocument();
    expect(screen.getByLabelText('Buscar tablero')).toHaveAttribute('placeholder', 'Hilo, cwd, modelo');
    expect(screen.getByText('Análisis locales de Codex')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Cargar$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Cargar más$/i })).toBeInTheDocument();
    expect(screen.getAllByText('Static').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /Investigador abierto.*i18n-thread codex-1/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Exportar CSV/i })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Idioma'), { target: { value: 'en' } });

    expect(document.documentElement.lang).toBe('en');
    expect(screen.getByLabelText('Language')).toHaveValue('en');
    expect(screen.getByRole('button', { name: /^Calls$/i })).toBeInTheDocument();
    expect(screen.getByText('Local Codex analytics')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Load$/i })).toBeInTheDocument();
expect(screen.getAllByText('Static').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /Open investigator for i18n-thread codex-1/i })).toBeInTheDocument();
  window.localStorage?.removeItem('codex-usage-dashboard-language');
});
});
