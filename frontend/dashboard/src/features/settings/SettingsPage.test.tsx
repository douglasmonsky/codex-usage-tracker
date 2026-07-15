import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DashboardBootPayload } from '../../api/types';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import { SettingsPage } from './SettingsPage';
import { settingsSectionStorageKey } from './useSettingsSection';

beforeEach(() => vi.stubGlobal('localStorage', memoryStorage()));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('SettingsPage', () => {
  it('shows all categories and their focused content', () => {
    renderPage();
    const navigation = screen.getByRole('navigation', { name: 'Settings sections' });
    for (const label of ['Data', 'Estimates', 'Content Access', 'Application', 'Source Health']) {
      expect(navigation).toHaveTextContent(label);
    }
    expect(screen.getByText('Data window')).toBeInTheDocument();
    expect(screen.getByText('Evidence rows')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Estimates' }));
    expect(screen.getByText('custom-pricing.json')).toBeInTheDocument();
    expect(screen.getByText('Observed Weekly')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Content Access' }));
    expect(screen.getByText('strict: cwd redacted, project names redacted')).toBeInTheDocument();
    expect(screen.getByText(/Aggregate payloads avoid prompts/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Application' }));
    expect(screen.getByText('en, es')).toBeInTheDocument();
  });

  it('persists and restores the selected category', async () => {
    const first = renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Source Health' }));
    await waitFor(() => expect(window.localStorage.getItem(settingsSectionStorageKey)).toBe('"sources"'));
    first.unmount();
    renderPage();
    expect(screen.getByRole('button', { name: 'Source Health' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('falls back safely when stored state is malformed', () => {
    window.localStorage.setItem(settingsSectionStorageKey, '{broken');
    renderPage();
    expect(screen.getByRole('button', { name: 'Data' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('reports actionable source health while ignoring cumulative duplicates', () => {
    window.localStorage.setItem(settingsSectionStorageKey, '"sources"');
    renderPage();
    expect(screen.getByText('Config error: invalid allowance file')).toBeInTheDocument();
    expect(screen.getByText('2 parser diagnostics: malformed_event=2')).toBeInTheDocument();
    expect(screen.getByText('2 copied rows excluded; 10 physical rows preserved')).toBeInTheDocument();
    expect(screen.queryByText(/duplicate_cumulative_total=/)).not.toBeInTheDocument();
  });

  it('keeps a readable language fallback when the shell catalog is empty', () => {
    window.localStorage.setItem(settingsSectionStorageKey, '"application"');
    renderPage({ language: 'en', direction: 'ltr', languages: [] });
    expect(screen.getByText('English (en)')).toBeInTheDocument();
  });
});

function renderPage(applicationI18n = { language: 'en', direction: 'ltr' as const, languages: [{ code: 'en' }, { code: 'es' }] }) {
  return render(
    <SettingsPage
      model={fixtureModel}
      payload={payload}
      historyScope="all"
      loadWindow="week"
      loadLimit={500}
      scopeSince="2026-07-04T00:00:00Z"
      loadedRowCount={400}
      totalAvailableRows={900}
      canUseLiveApi
      autoRefreshEnabled={false}
      refreshState="Refresh idle"
      applicationI18n={applicationI18n}
    />,
  );
}

const payload: DashboardBootPayload = {
  shell_boot: true,
  language: 'en',
  language_direction: 'ltr',
  available_languages: [{ code: 'en' }, { code: 'es' }],
  pricing_configured: true,
  pricing_source: 'custom-pricing.json',
  allowance_configured: false,
  allowance_source: 'allowance.toml',
  allowance_error: 'invalid allowance file',
  rate_card_configured: true,
  observed_usage: {
    available: true,
    source: 'token_count.rate_limits',
    windows: [{ key: 'weekly', label: 'Weekly', used_percent: 25, window_minutes: 10_080 }],
  },
  parser_diagnostics: { malformed_event: 2, duplicate_cumulative_total: 7 },
  dedupe: { canonical_rows: 8, physical_rows: 10, excluded_copied_rows: 2 },
  privacy_mode: 'strict',
  project_metadata_privacy: { mode: 'strict', cwd_redacted: true, project_names_redacted: true },
};

function memoryStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() { return values.size; },
    clear: () => values.clear(),
    getItem: key => values.get(key) ?? null,
    key: index => [...values.keys()][index] ?? null,
    removeItem: key => values.delete(key),
    setItem: (key, value) => values.set(key, value),
  };
}
