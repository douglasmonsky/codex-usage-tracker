import { act, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import type { ShellI18n } from './i18n';
import { DocumentLocalizationBridge } from './DocumentLocalizationBridge';
import { ShellI18nProvider } from './i18nContext';

function testI18n(language: 'en' | 'zh-Hans'): ShellI18n {
  const translateText = (value: string) => language === 'zh-Hans' && value === 'Overview' ? '概览' : value;
  return {
    language,
    direction: 'ltr',
    languages: [],
    t: (_key, fallback) => fallback ?? _key,
    translateText,
    formatText: (template, values) => translateText(template).replace(
      /\{(\w+)\}/gu,
      (token, key) => String(values[key] ?? token),
    ),
    navLabel: (_view, fallback) => fallback,
  };
}

function fixture(language: 'en' | 'zh-Hans') {
  return (
    <ShellI18nProvider value={testI18n(language)}>
      <DocumentLocalizationBridge />
      <main data-dashboard-localization-root>
        <button
          data-testid="marked"
          data-localization-attributes="aria-label title"
          aria-label="Overview"
          title="Overview"
        >
          Overview
        </button>
        <button data-testid="unmarked" aria-label="Overview" title="Overview">Overview</button>
        <span data-testid="opaque" data-localization-skip="true">Overview</span>
      </main>
    </ShellI18nProvider>
  );
}

afterEach(() => {
  document.title = '';
});

describe('DocumentLocalizationBridge', () => {
  it('translates only opted-in attributes and restores them when language changes', () => {
    const rendered = render(fixture('zh-Hans'));
    const marked = rendered.getByTestId('marked');
    const unmarked = rendered.getByTestId('unmarked');
    const opaque = rendered.getByTestId('opaque');

    expect(marked).toHaveAttribute('aria-label', '概览');
    expect(marked).toHaveAttribute('title', '概览');
    expect(unmarked).toHaveAttribute('aria-label', 'Overview');
    expect(unmarked).toHaveAttribute('title', 'Overview');
    expect(opaque).toHaveTextContent('Overview');

    rendered.rerender(fixture('en'));
    expect(marked).toHaveAttribute('aria-label', 'Overview');
    expect(marked).toHaveAttribute('title', 'Overview');
  });

  it('applies the same opt-in rule to dynamically added elements', async () => {
    const rendered = render(fixture('zh-Hans'));
    const root = rendered.container.querySelector('[data-dashboard-localization-root]');
    const marked = document.createElement('button');
    marked.dataset.localizationAttributes = 'aria-label';
    marked.setAttribute('aria-label', 'Overview');
    const unmarked = document.createElement('button');
    unmarked.setAttribute('aria-label', 'Overview');

    act(() => {
      root?.append(marked, unmarked);
    });

    await waitFor(() => expect(marked).toHaveAttribute('aria-label', '概览'));
    expect(unmarked).toHaveAttribute('aria-label', 'Overview');
  });
});
