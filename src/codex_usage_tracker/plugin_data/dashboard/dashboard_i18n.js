(function () {
  const builtInFallbackTranslations = {
    'dashboard.title': 'Usage Dashboard',
    'dashboard.eyebrow': 'Local Codex analytics',
    'docs.dashboard_guide': 'Dashboard guide',
    'dashboard.view.insights': 'Insights',
    'dashboard.view.calls': 'Calls',
    'dashboard.view.threads': 'Threads',
    'dashboard.view.diagnostics': 'Diagnostics',
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
    'action.set_limits': 'Set limits',
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
    'metric.visible_calls': 'Visible Calls',
    'metric.total_tokens': 'Total Tokens',
    'metric.cached_input': 'Cached Input',
    'metric.uncached_input': 'Uncached Input',
    'metric.output_tokens': 'Output tokens',
    'metric.reasoning_output': 'Reasoning output',
    'metric.estimated_cost': 'Estimated Cost',
    'metric.codex_credits': 'Codex credits',
    'metric.usage_observed': 'Usage observed',
    'allowance.live_check_short': 'Verify live',
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
    'call.cache_body_post_compaction': 'A compaction marker or reset-like profile is associated with this call. Check loaded evidence to confirm replacement context.',
    'call.cache_body_cold': 'Conversation-specific cache likely expired or missed; remaining cache is probably stable Codex scaffolding or tool schema prefix.',
    'call.cache_body_spike': 'Fresh input rose sharply compared with the previous call in this resolved thread.',
    'call.cache_body_warm': 'Most input tokens reused prompt cache. The uncached portion is the most likely investigation target.',
    'call.cache_body_partial': 'Some prefix reused cache, but a meaningful share of the input was fresh or reserialized.',
    'call.cache_body_uncached': 'This call has little or no cache reuse, so most input was charged as fresh.',
    'call.delta.cache_drop': 'Fresh input rose by {uncached} while cached input fell by {cached}; this is the classic cache-drop profile.',
    'call.delta.uncached_increase': 'Fresh input increased by {uncached} from the previous call; inspect evidence for new files, tool results, or rewritten context.',
    'call.delta.uncached_decrease_cached_increase': 'Fresh input fell by {uncached} while cached input increased, so this call is reusing context more efficiently than the previous one.',
    'call.delta.stable': 'Token accounting is broadly stable compared with the previous call in this resolved thread.',
    'call.next_step.post_compaction': 'Check the loaded evidence for an explicit compaction marker or replacement history before interpreting the cache delta.',
    'call.next_step.cold': 'Compare the previous call, then inspect the loaded evidence to see what fresh context was sent after the cache miss.',
    'call.next_step.spike': 'Inspect the most recent evidence entries first; the spike is in fresh uncached input, not cached history.',
    'call.next_step.warm': 'Cache reuse is healthy; focus on the {uncached} uncached tokens that were still billed as fresh input.',
    'call.next_step.delta': 'Use the delta cards to locate whether the change is cached input, uncached input, or output/reasoning.',
    'call.next_step.isolated': 'Use the loaded evidence if the aggregate totals are not enough to understand this isolated call.',
    'call.readout.title': 'Investigation readout',
    'call.readout.badge': 'Exact + derived + on-demand evidence',
    'call.readout.exact_label': 'Exact callback accounting',
    'call.readout.previous_label': 'Compared with previous call',
    'call.readout.evidence_label': 'Evidence state',
    'call.readout.next_label': 'Next diagnostic move',
    'call.readout.exact_body': '{input} input tokens = {cached} cached + {uncached} uncached; {output} output tokens; {cache} cache reuse.',
    'call.readout.previous_unavailable': 'No previous call is loaded for this resolved thread, so call-to-call deltas are unavailable.',
    'call.readout.evidence_loading': 'Evidence is loading from the local JSONL source. Aggregate token counts are exact, but visible-context attribution needs that runtime evidence.',
    'call.readout.evidence_serialized_deferred': 'Fast serialized estimate only; full serialized grouping is deferred.',
    'call.readout.evidence_serialized_bound': 'Serialized local upper bound: {tokens} tokens from {chars} raw JSON chars.',
    'call.readout.evidence_analyzed': 'Evidence analyzed: {totalEntries} selected-turn entries, {visibleChars} visible redacted chars, {visibleTokens} visible tokens via {estimator}. {serializedDetail} {renderedEntries} entries rendered initially.',
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
