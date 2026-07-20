import type { DashboardBootPayload, DashboardLanguage } from '../api/types';
import type { ViewId } from './navigation';
import {
  translateZhHansUiText,
  type CatalogTemplateTranslation,
} from './zh-Hans/translate';

const languageStorageKey = 'codex-usage-dashboard-language';

const fallbackTranslations: Record<string, string> = {
  'button.back_to_dashboard': 'Back to dashboard',
  'button.clear': 'Clear',
  'button.copy_link': 'Copy link',
  'button.enable_context_loading': 'Enable context loading',
  'button.export_csv': 'Export CSV',
  'button.full_serialized_analysis': 'Run full serialized analysis',
  'button.hide_details': 'Hide details',
  'button.include_tool_output': 'Include tool output',
  'button.load_more': 'Load more',
  'button.load_older_context': 'Load older entries',
  'button.next_call': 'Next call',
  'button.no_char_limit': 'No char limit',
  'button.open_investigator': 'Open investigator',
  'button.previous_call': 'Previous call',
  'button.refresh': 'Refresh',
  'button.show_compaction_history': 'Show compacted replacement',
  'button.show_tool_output': 'Show tool output',
  'button.top': 'Top',
  'button.show_turn_evidence': 'Show turn log evidence',
  'badge.live': 'Live',
  'dashboard.eyebrow': 'Local Codex analytics',
  'dashboard.call_details': 'Call Details',
  'dashboard.title': 'Usage Dashboard',
  'dashboard.view.call': 'Call Investigator',
  'dashboard.view.calls': 'Calls',
  'dashboard.view.insights': 'Overview',
  'dashboard.view.overview': 'Overview',
  'dashboard.view.threads': 'Threads',
  'detail.next_action': 'Next action',
  'filter.search': 'Search dashboard',
  'filter.search_placeholder': 'Search calls, threads, models, diagnostics...',
  'language.label': 'Language',
  'nav.history': 'History',
  'nav.load': 'Load',
  'nav.live': 'Live',
  'option.active_sessions_only': 'Active',
  'option.all_history': 'All history',
  'status.paused': 'Paused',
  'status.static': 'Static',
  'settings.experimental.title': 'Experimental Features',
  'settings.experimental.subtitle': 'Browser-local preference',
  'settings.experimental.toggle': 'Show experimental dashboard features',
  'settings.experimental.origin_scope': 'This preference is stored for this browser origin. Experimental workspaces remain available from direct links, and Diagnostics stays visible.',
  'maturity.aria': 'Feature maturity: {title}',
  'maturity.highly_experimental': 'Highly experimental',
  'maturity.highly_experimental_description': 'Useful for technical exploration; methods and presentation may change.',
  'maturity.available_transition': 'Available during transition',
  'maturity.transition_description': 'This workspace remains available in Release N while its future placement is prepared.',
  'readiness.eyebrow': 'Conversational analysis',
  'readiness.title': 'Analysis readiness',
  'readiness.state.ready': 'Ready',
  'readiness.state.restart_required': 'Restart required',
  'readiness.state.unavailable': 'Unavailable',
  'readiness.state.unknown': 'Unknown',
  'readiness.unknown_summary': 'Conversational analysis readiness could not be determined from this static payload.',
  'readiness.summary.unavailable_not_configured': 'Conversational analysis is not locally configured.',
  'readiness.summary.unavailable_failed': 'Conversational analysis failed a local configuration or launcher check.',
  'readiness.summary.unknown_local_files': 'Conversational analysis readiness could not be determined from local files.',
  'readiness.summary.ready_local_checks': 'Local installation and launcher checks passed; current task tool exposure is not verified.',
  'readiness.summary.restart_fresh_task': 'The local launcher is installed; a fresh Codex task is required for discovery.',
  'readiness.guidance.ready': 'Local checks passed. This does not verify that the current task loaded MCP tools.',
  'readiness.guidance.restart_required': 'Restart Codex and open a fresh task to load the local plugin tools.',
  'readiness.guidance.unavailable': 'Run `codex-usage-tracker setup`, then `codex-usage-tracker doctor`.',
  'readiness.guidance.unknown': 'Readiness could not be determined from this payload.',
  'readiness.manual_fallback': 'Manual fallback',
  'readiness.fallback.calls': 'Calls',
  'readiness.fallback.threads': 'Threads',
  'readiness.fallback.limits': 'Limits',
  'readiness.fallback.diagnostics': 'Diagnostics',
  'readiness.fallback.advanced': 'Advanced experimental controls',
  'evidence.actions.aria': 'Dashboard evidence actions',
  'evidence.open': 'Open evidence',
  'evidence.copy_prompt': 'Copy investigation prompt',
  'evidence.prompt_copied': 'Investigation prompt copied',
  'evidence.prompt_copy_failed': 'Unable to copy investigation prompt',
  'evidence.launch_guidance': 'Start the local dashboard first: {instruction}',
  'evidence.question.default': 'Investigate the selected aggregate usage evidence.',
  'evidence.aggregate_selection': 'aggregate selection',
  'evidence.prompt.template': '{question} Evidence: {identifiers}. Scope: history={history}, privacy_mode={privacy}. Target: {target}.{launch}',
  'evidence.prompt.launch': ' Launch locally with: {instruction}.',
};

const navTranslationKeys: Partial<Record<ViewId, string>> = {
  overview: 'dashboard.view.overview',
  calls: 'dashboard.view.calls',
  call: 'dashboard.view.call',
  threads: 'dashboard.view.threads',
};

export type ShellI18n = {
  language: string;
  direction: 'ltr' | 'rtl';
  languages: DashboardLanguage[];
  t: (key: string, fallback?: string) => string;
  translateText: (value: string) => string;
  formatText: (template: string, values: Readonly<Record<string, string | number>>) => string;
  navLabel: (view: ViewId, fallback: string) => string;
};

export type LocalizedText = {
  template: string;
  values: Readonly<Record<string, string | number>>;
};

export function formatLocalizedText(i18n: ShellI18n, value: string | LocalizedText): string {
  return typeof value === 'string' ? i18n.translateText(value) : i18n.formatText(value.template, value.values);
}

export function createShellI18n(payload: DashboardBootPayload | null, language: string): ShellI18n {
  const languages = dashboardLanguages(payload);
  const normalized = normalizeLanguage(language, languages);
  const catalog = payload?.translation_catalog ?? {};
  const selectedTranslations =
    catalog[normalized] ?? (payload?.language === normalized ? payload?.translations : undefined) ?? {};
  const englishTranslations = catalog.en ?? (payload?.language === 'en' ? payload.translations : undefined) ?? {};
  const translations = {
    ...fallbackTranslations,
    ...englishTranslations,
    ...selectedTranslations,
  };
  const catalogLiteralTranslations = buildCatalogLiteralTranslations(
    englishTranslations,
    selectedTranslations,
  );
  const catalogTemplateTranslations = buildCatalogTemplateTranslations(
    englishTranslations,
    selectedTranslations,
  );
  const languageMeta = languages.find(entry => entry.code === normalized);
  const direction = languageMeta?.dir === 'rtl' || (!languageMeta && payload?.language_direction === 'rtl') ? 'rtl' : 'ltr';
  const translateText = (value: string) => {
    if (normalized === 'zh-Hans') {
      return translateZhHansUiText(
        value,
        catalogLiteralTranslations,
        catalogTemplateTranslations,
      );
    }
    return catalogLiteralTranslations.get(value) ?? value;
  };
  return {
    language: normalized,
    direction,
    languages,
    t: (key, fallback) => translations[key] ?? fallback ?? key,
    translateText,
    formatText: (template, values) => translateText(template).replace(
      /\{([A-Za-z][A-Za-z0-9_]*)\}/gu,
      (token, key) => String(values[String(key)] ?? token),
    ),
    navLabel: (view, fallback) => {
      const key = navTranslationKeys[view];
      return key ? translations[key] ?? fallback : fallback;
    },
  };
}

function buildCatalogTemplateTranslations(
  englishTranslations: Record<string, string>,
  selectedTranslations: Record<string, string>,
): ReadonlyArray<CatalogTemplateTranslation> {
  const templates: CatalogTemplateTranslation[] = [];
  for (const [key, englishValue] of Object.entries(englishTranslations)) {
    const selectedValue = selectedTranslations[key];
    if (!selectedValue || selectedValue === englishValue || !englishValue.includes('{')) continue;
    const placeholders: string[] = [];
    const patternParts: string[] = [];
    let cursor = 0;
    for (const match of englishValue.matchAll(/\{([A-Za-z][A-Za-z0-9_]*)\}/gu)) {
      const index = match.index ?? cursor;
      patternParts.push(escapeRegularExpression(englishValue.slice(cursor, index)));
      patternParts.push('(.+?)');
      placeholders.push(match[1]);
      cursor = index + match[0].length;
    }
    patternParts.push(escapeRegularExpression(englishValue.slice(cursor)));
    templates.push({
      pattern: new RegExp(`^${patternParts.join('')}$`, 'u'),
      placeholders,
      translatedTemplate: selectedValue,
    });
  }
  return templates.sort((left, right) => right.translatedTemplate.length - left.translatedTemplate.length);
}

function escapeRegularExpression(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/gu, '\\$&');
}

function buildCatalogLiteralTranslations(
  englishTranslations: Record<string, string>,
  selectedTranslations: Record<string, string>,
): ReadonlyMap<string, string> {
  const literals = new Map<string, string>();
  for (const [key, englishValue] of Object.entries(englishTranslations)) {
    const selectedValue = selectedTranslations[key];
    if (selectedValue && selectedValue !== englishValue) {
      literals.set(englishValue, selectedValue);
    }
  }
  return literals;
}

function dashboardLanguages(payload: DashboardBootPayload | null): DashboardLanguage[] {
  const languages = payload?.available_languages?.filter(language => language.code) ?? [];
  return languages.length ? languages : [{ code: 'en', english_name: 'English', native_name: 'English', dir: 'ltr' }];
}

export function initialDashboardLanguage(payload: DashboardBootPayload | null): string {
  return normalizeLanguage(storedDashboardLanguage() || payload?.language || 'en', dashboardLanguages(payload));
}

export function storeDashboardLanguage(language: string): void {
  try {
    window.localStorage?.setItem(languageStorageKey, language);
  } catch {
    // Storage can be unavailable in restricted browsers; language still applies for this session.
  }
}

function storedDashboardLanguage(): string {
  try {
    return window.localStorage?.getItem(languageStorageKey) ?? '';
  } catch {
    return '';
  }
}

function normalizeLanguage(language: string, languages: DashboardLanguage[]): string {
  const supported = new Set(languages.map(entry => entry.code));
  if (supported.has(language)) return language;
  const lower = language.toLowerCase();
  const match = languages.find(entry => entry.code.toLowerCase() === lower);
  return match?.code ?? 'en';
}
