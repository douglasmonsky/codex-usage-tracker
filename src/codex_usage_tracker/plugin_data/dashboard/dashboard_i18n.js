(function () {
  const builtInFallbackTranslations = {
    'dashboard.title': 'Usage Dashboard',
    'dashboard.eyebrow': 'Local Codex analytics',
    'docs.dashboard_guide': 'Dashboard guide',
    'dashboard.view.insights': 'Insights',
    'dashboard.view.calls': 'Calls',
    'dashboard.view.threads': 'Threads',
    'dashboard.view.call': 'Call Investigator',
    'dashboard.model_calls': 'Model Calls',
    'dashboard.call_details': 'Call Details',
    'dashboard.detail.empty': 'Hover or click a row to inspect aggregate usage fields.',
    'button.refresh': 'Refresh',
    'button.export_csv': 'Export CSV',
    'button.load_more': 'Load more',
    'button.load_context': 'Load context',
    'button.show_turn_evidence': 'Show turn log evidence',
    'button.include_tool_output': 'Include tool output',
    'button.hide_tool_output': 'Hide tool output',
    'button.show_tool_output': 'Show tool output',
    'button.full_serialized_analysis': 'Run full serialized analysis',
    'button.load_older_context': 'Load older entries',
    'button.no_char_limit': 'No char limit',
    'button.open_investigator': 'Open investigator',
    'button.previous_call': 'Previous call',
    'button.next_call': 'Next call',
    'button.back_to_dashboard': 'Back to dashboard',
    'button.show_compaction_history': 'Show compacted replacement',
    'button.copy_link': 'Copy link',
    'button.clear': 'Clear',
    'button.hide_details': 'Hide details',
    'action.run': 'Run',
    'nav.live': 'Live',
    'nav.load': 'Load',
    'nav.history': 'History',
    'filter.search': 'Search',
    'filter.search_placeholder': 'Thread, cwd, model',
    'filter.model': 'Model',
    'filter.effort': 'Reasoning',
    'filter.confidence': 'Confidence',
    'filter.sort': 'Sort',
    'filter.start': 'Start',
    'filter.end': 'End',
    'option.all_models': 'All models',
    'option.all_efforts': 'All efforts',
    'option.all_confidence': 'All confidence',
    'section.needs_attention': 'Needs Attention',
    'section.investigation_presets': 'Investigation Presets',
    'state.error': 'Error',
    'state.no_data': 'No data',
    'state.loading_rows': 'Loading rows',
    'state.no_rows': 'No rows',
    'state.no_calls': 'No calls match the current filters.',
    'state.no_threads': 'No threads match the current filters.',
    'state.requires_evidence': 'Evidence needed',
    'caption.rows_loading_background': 'Dashboard totals are ready. Rows are loading in the background.',
    'caption.rows_loading_progress': 'Loading rows: {loaded} of {total}',
    'caption.rows_loaded_progress': 'Rows loaded: {loaded} of {total}',
    'live.loading_rows': 'Loading rows in the background...',
    'table.time': 'Time',
    'table.thread': 'Thread',
    'table.initiated': 'Initiated',
    'table.model': 'Model',
    'table.effort': 'Effort',
    'table.tokens': 'Tokens',
    'table.cached': 'Cached',
    'table.uncached': 'Uncached',
    'table.output': 'Output',
    'table.cost': 'Cost',
    'table.cache': 'Cache',
    'table.signals': 'Signals',
    'table.source': 'Source',
    'table.last_call': 'Last Call',
    'table.visible_status': 'Showing {end} of {total} {items}',
    'language.label': 'Language',
    'caption.call_investigator': 'Investigating call {record}.',
    'call.exact_accounting': 'Exact token accounting',
    'call.cache_diagnostics': 'Cache diagnostics',
    'call.cache_accounting_delta': 'Cache/accounting delta',
    'call.context_estimate': 'Context change estimate',
    'call.compaction_diagnostics': 'Compaction diagnostics',
    'call.raw_evidence': 'Raw evidence',
    'call.exact_label': 'Exact from token callback',
    'call.derived_label': 'Derived from adjacent aggregate calls',
    'call.estimated_label': 'Estimated from visible log volume',
    'call.evidence_label': 'Runtime evidence',
    'call.cache_warm': 'Warm cache reuse',
    'call.cache_cold': 'Cold resume / stale cache',
    'call.cache_partial': 'Partial cache miss',
    'call.cache_spike': 'Uncached spike',
    'call.cache_steady': 'Steady cache profile',
    'call.post_compaction': 'Post-compaction possible',
    'call.no_previous': 'No previous call in this resolved thread.',
    'call.visible_estimate': 'Visible new context estimate',
    'call.hidden_estimate': 'Unexplained hidden/serialized input estimate',
    'call.serialized_upper_bound': 'Serialized local upper bound',
    'call.serialized_candidate': 'Possible serialized overhead',
    'call.remaining_after_serialized': 'Remaining after serialized bound',
    'call.visible_gap': 'Uncached input minus visible estimate',
    'call.serialized_candidate_hint': 'Serialized upper bound minus visible estimate, capped by exact uncached input',
    'call.remaining_after_serialized_hint': 'Uncached input not covered even by serialized upper bound',
    'call.serialized_breakdown': 'Serialized evidence groups',
    'call.serialized_bound_hint': 'Upper-bound local JSONL structure; not exact prompt text.',
    'call.serialized_bucket_detail': '{count} fields · {chars} chars',
    'call.serialized_deferred': 'Fast estimate loaded; full serialized grouping is deferred.',
    'call.serialized_quick_hint': 'fast estimate',
    'call.open_hint': 'Click a call row for deep diagnostics.',
    'call.not_found': 'Selected call was not found in the loaded dashboard rows.',
    'call.position': 'Call {position} in this resolved thread.',
    'call.context_estimate_hint': 'Compare exact uncached input with tokenizer-counted visible log evidence. The gap should be treated as hidden scaffolding, serialization, or tokenizer estimate error.',
    'call.compaction_hint': 'Loaded evidence can show explicit compaction events. Redacted replacement history is shown only after the compacted replacement action.',
    'context.token_breakdown': 'Token breakdown',
    'context.compaction_detected': 'Compaction detected',
    'context.compaction_replacement': 'Compacted replacement context',
    'context.compaction_replacement_count': '{count} replacement history entries available.',
    'context.token_scope_call': 'This call',
    'context.token_scope_selected': 'Selected call token count',
    'context.token_scope_previous': 'Previous token count in same turn',
    'context.token_scope_earlier': 'Earlier token count in same turn',
    'context.token_scope_session': 'Session cumulative',
    'context.token_type': 'Type',
    'context.token_input': 'Input',
    'context.token_cached': 'Cached',
    'context.token_uncached': 'Uncached',
    'context.token_output': 'Output',
    'context.token_reasoning': 'Reasoning',
    'context.token_total': 'Total',
    'context.no_char_limit_active': 'No character limit applied.',
    'context.auto_loading': 'Loading selected-turn evidence with tool output included.',
    'source.user_initiated': 'User initiated',
    'source.codex_initiated': 'Codex initiated',
  };

  const languageAliases = {
    eng: 'en',
    english: 'en',
    'en-us': 'en',
    vn: 'vi',
    vie: 'vi',
    vietnamese: 'vi',
    'tieng viet': 'vi',
    'tiếng việt': 'vi',
    'vi-vn': 'vi',
    spa: 'es',
    spanish: 'es',
    'es-es': 'es',
    'es-mx': 'es',
    fre: 'fr',
    fra: 'fr',
    french: 'fr',
    ger: 'de',
    deu: 'de',
    german: 'de',
    por: 'pt',
    portuguese: 'pt',
    'pt-br': 'pt',
    jpn: 'ja',
    japanese: 'ja',
    zh: 'zh-Hans',
    'zh-cn': 'zh-Hans',
    'zh-hans': 'zh-Hans',
    chinese: 'zh-Hans',
    'simplified chinese': 'zh-Hans',
    kor: 'ko',
    korean: 'ko',
    rus: 'ru',
    russian: 'ru',
    ita: 'it',
    italian: 'it',
    ara: 'ar',
    arabic: 'ar',
  };

  function storedLanguage() {
    try {
      return window.localStorage ? window.localStorage.getItem('codex-usage-dashboard-language') : '';
    } catch (_error) {
      return '';
    }
  }

  function create(payload, helpers = {}) {
    const escapeHtml = helpers.escapeHtml || (value => String(value ?? ''));
    let availableLanguages = Array.isArray(payload.available_languages) && payload.available_languages.length
      ? payload.available_languages
      : [{ code: 'en', english_name: 'English', native_name: 'English', dir: 'ltr' }];
    let supportedLanguages = new Set(availableLanguages.map(language => language.code));
    let translationCatalog = payload.translation_catalog || { [payload.language || 'en']: payload.translations || {} };
    let fallbackTranslations = { ...builtInFallbackTranslations, ...(translationCatalog.en || payload.translations || {}) };
    let currentLanguage = normalizeLanguage(storedLanguage() || payload.language || 'en');
    let translations = translationCatalog[currentLanguage] || fallbackTranslations;

    function normalizeLanguage(value) {
      const raw = String(value || '').trim();
      const normalized = raw.toLowerCase().replace(/_/g, '-');
      const candidate = languageAliases[normalized] || raw;
      return supportedLanguages.has(candidate) ? candidate : 'en';
    }

    function t(key) {
      return translations[key] || fallbackTranslations[key] || key;
    }

    function tf(key, values = {}) {
      return t(key).replace(/\{(\w+)\}/g, (match, name) => (
        Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : match
      ));
    }

    function translatedField(keyValue, fallbackText = '') {
      if (keyValue) {
        const translated = t(keyValue);
        if (translated !== keyValue) return translated;
      }
      return fallbackText || '';
    }

    function languageDirection(language = currentLanguage) {
      const entry = availableLanguages.find(candidate => candidate.code === language);
      return entry && entry.dir === 'rtl' ? 'rtl' : 'ltr';
    }

    function populateLanguageOptions(languageSelectEl) {
      if (!languageSelectEl) return;
      languageSelectEl.innerHTML = availableLanguages.map(language => {
        const label = language.native_name || language.english_name || language.code;
        return `<option value="${escapeHtml(language.code)}" dir="${escapeHtml(language.dir || 'ltr')}">${escapeHtml(label)}</option>`;
      }).join('');
      languageSelectEl.value = currentLanguage;
    }

    function refreshTranslations() {
      translations = translationCatalog[currentLanguage] || fallbackTranslations;
      return translations;
    }

    function setLanguage(language, options = {}) {
      currentLanguage = normalizeLanguage(language);
      refreshTranslations();
      if (options.persist !== false) {
        try {
          if (window.localStorage) window.localStorage.setItem('codex-usage-dashboard-language', currentLanguage);
        } catch (_error) {
          // Local storage can be unavailable for file URLs or privacy settings.
        }
      }
      return currentLanguage;
    }

    function updatePayload(nextPayload) {
      let languagesChanged = false;
      if (nextPayload.translation_catalog) {
        translationCatalog = nextPayload.translation_catalog;
        fallbackTranslations = { ...builtInFallbackTranslations, ...(translationCatalog.en || fallbackTranslations) };
      }
      if (Array.isArray(nextPayload.available_languages) && nextPayload.available_languages.length) {
        availableLanguages = nextPayload.available_languages;
        supportedLanguages = new Set(availableLanguages.map(language => language.code));
        languagesChanged = true;
      }
      setLanguage(nextPayload.language || currentLanguage, { persist: false });
      return languagesChanged;
    }

    function translateEffort(value) {
      if (!value) return value;
      const key = `effort.${String(value).toLowerCase()}`;
      const translated = t(key);
      return translated === key ? value : translated;
    }

    return {
      t,
      tf,
      translatedField,
      languageDirection,
      populateLanguageOptions,
      refreshTranslations,
      setLanguage,
      updatePayload,
      translateEffort,
      get currentLanguage() {
        return currentLanguage;
      },
    };
  }

  window.CodexUsageDashboardI18n = {
    create,
    builtInFallbackTranslations,
  };
})();
