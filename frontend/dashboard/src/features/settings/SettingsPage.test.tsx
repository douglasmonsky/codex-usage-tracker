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
    expect(screen.getByText('Rows loaded')).toBeInTheDocument();

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
    expect(screen.queryByText(/duplicate_cumulative_total=/)).not.toBeInTheDocument();
  });
});

function renderPage() {
  return render(
    <SettingsPage
      model={fixtureModel}
      payload={payload}
      historyScope="all"
      loadLimit={500}
      loadedRowCount={400}
      totalAvailableRows={900}
      canUseLiveApi
      autoRefreshEnabled={false}
      refreshState="Refresh idle"
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
