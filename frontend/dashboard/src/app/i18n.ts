import type { DashboardBootPayload, DashboardLanguage } from '../api/types';
import type { ViewId } from './navigation';

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
  navLabel: (view: ViewId, fallback: string) => string;
};

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
  const languageMeta = languages.find(entry => entry.code === normalized);
  const direction = languageMeta?.dir === 'rtl' || (!languageMeta && payload?.language_direction === 'rtl') ? 'rtl' : 'ltr';
  return {
    language: normalized,
    direction,
    languages,
    t: (key, fallback) => translations[key] ?? fallback ?? key,
    navLabel: (view, fallback) => {
      const key = navTranslationKeys[view];
      return key ? translations[key] ?? fallback : fallback;
    },
  };
}

export function dashboardLanguages(payload: DashboardBootPayload | null): DashboardLanguage[] {
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
