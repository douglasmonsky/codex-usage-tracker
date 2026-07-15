import { advancedPagesZhHansPatterns, advancedPagesZhHansTranslations } from './advancedPages';
import { commonZhHansPatterns, commonZhHansTranslations } from './common';
import { corePagesZhHansPatterns, corePagesZhHansTranslations } from './corePages';
import {
  diagnosticsReportsZhHansPatterns,
  diagnosticsReportsZhHansTranslations,
} from './diagnosticsReports';
import { limitsZhHansPatterns, limitsZhHansTranslations } from './limits';
import type { ZhHansPattern } from './types';

const supplementalTranslations: Readonly<Record<string, string>> = {
  ...commonZhHansTranslations,
  ...corePagesZhHansTranslations,
  ...diagnosticsReportsZhHansTranslations,
  ...advancedPagesZhHansTranslations,
  ...limitsZhHansTranslations,
};

const supplementalPatterns: ReadonlyArray<ZhHansPattern> = [
  ...corePagesZhHansPatterns,
  ...diagnosticsReportsZhHansPatterns,
  ...advancedPagesZhHansPatterns,
  ...limitsZhHansPatterns,
  ...commonZhHansPatterns,
];

export type CatalogTemplateTranslation = {
  pattern: RegExp;
  placeholders: string[];
  translatedTemplate: string;
};

export function translateZhHansUiText(
  value: string,
  catalogTranslations: ReadonlyMap<string, string> = new Map(),
  catalogTemplates: ReadonlyArray<CatalogTemplateTranslation> = [],
): string {
  if (!value || !/[A-Za-z]/u.test(value)) return value;

  const exact = supplementalTranslations[value] ?? catalogTranslations.get(value);
  if (exact) return localizeEmbeddedZhHansFragments(exact);

  for (const { pattern, replace } of supplementalPatterns) {
    if (!pattern.test(value)) continue;
    pattern.lastIndex = 0;
    const translated = typeof replace === 'string'
      ? value.replace(pattern, replace)
      : value.replace(pattern, (...matches) => replace(...matches.map(String)));
    return localizeEmbeddedZhHansFragments(translated);
  }

  for (const template of catalogTemplates) {
    const match = value.match(template.pattern);
    if (!match) continue;
    const values = new Map<string, string>();
    template.placeholders.forEach((placeholder, index) => values.set(placeholder, match[index + 1]));
    return localizeEmbeddedZhHansFragments(template.translatedTemplate.replace(/\{([A-Za-z][A-Za-z0-9_]*)\}/gu, (_token, placeholder) => (
      values.get(String(placeholder)) ?? String(_token)
    )));
  }
  return localizeEmbeddedZhHansFragments(value);
}

const monthNumberByEnglishShortName: Readonly<Record<string, number>> = {
  Jan: 1,
  Feb: 2,
  Mar: 3,
  Apr: 4,
  May: 5,
  Jun: 6,
  Jul: 7,
  Aug: 8,
  Sep: 9,
  Oct: 10,
  Nov: 11,
  Dec: 12,
};

function localizeEmbeddedZhHansFragments(value: string): string {
  return value.replace(
    /\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{1,2})(?:, (\d{4}))?(?:,? (\d{1,2}):(\d{2}) (AM|PM))?\b/gu,
    (_match, monthName, day, year, hour, minute, period) => {
      const date = `${year ? `${year}年` : ''}${monthNumberByEnglishShortName[String(monthName)]}月${day}日`;
      if (!hour || !minute || !period) return date;
      const hourValue = Number(hour) % 12 + (period === 'PM' ? 12 : 0);
      return `${date} ${String(hourValue).padStart(2, '0')}:${minute}`;
    },
  );
}
