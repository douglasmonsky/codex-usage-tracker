    const dashboardFormat = window.CodexUsageDashboardFormat;
    const dashboardData = window.CodexUsageDashboardData;
    const {
      number,
      money,
      credits,
      pct,
      short,
      escapeHtml,
      truncate,
      formatTimestamp,
      formatTimestampTitle,
      renderTimeCell,
      defaultSortDirection,
      textValue,
      compareValues,
      sortLabel,
    } = dashboardFormat;
    const {
      payloadRows,
      payloadLimit,
      limitValue,
      optionValueExists,
      clamp,
      usageCreditValue,
      usageCreditStatusText,
      sumUsageCredits,
      creditCoverageRatio,
      isAutoReview,
      isSubagent,
      sourceLabel,
      resolvedParentThreadName,
      resolvedParentSessionUpdatedAt,
      resolveThreadAttachment,
      chronological,
      adjacentThreadCalls,
      classifyCacheDiagnostic,
      callAccountingDelta,
      rowInputTokens: dataRowInputTokens,
      cachedInputTokens: dataCachedInputTokens,
      uncachedInputTokens: dataUncachedInputTokens,
      outputTokens: dataOutputTokens,
      rowReasoningTokens: dataRowReasoningTokens,
    } = dashboardData;
    const initialPayload = JSON.parse(document.getElementById('usage-data').textContent);
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
      'button.show_tool_output': 'Show tool output',
      'button.load_older_context': 'Load older entries',
      'button.no_char_limit': 'No char limit',
      'button.open_investigator': 'Open investigator',
      'button.previous_call': 'Previous call',
      'button.next_call': 'Next call',
      'button.back_to_dashboard': 'Back to dashboard',
      'button.show_compaction_history': 'Show compacted replacement',
      'button.copy_link': 'Copy link',
      'button.clear': 'Clear',
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
      'state.no_data': 'No data',
      'state.no_rows': 'No rows',
      'state.no_calls': 'No calls match the current filters.',
      'state.no_threads': 'No threads match the current filters.',
      'state.requires_evidence': 'Load evidence',
      'table.time': 'Time',
      'table.thread': 'Thread',
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
      'call.evidence_label': 'Evidence loaded from local JSONL on demand',
      'call.cache_warm': 'Warm cache reuse',
      'call.cache_cold': 'Cold resume / stale cache',
      'call.cache_partial': 'Partial cache miss',
      'call.cache_spike': 'Uncached spike',
      'call.cache_steady': 'Steady cache profile',
      'call.post_compaction': 'Post-compaction possible',
      'call.no_previous': 'No previous call in this resolved thread.',
      'call.visible_estimate': 'Visible new context estimate',
      'call.hidden_estimate': 'Unexplained hidden/serialized input estimate',
      'call.open_hint': 'Double-click a row or use Open investigator for deep diagnostics.',
      'call.not_found': 'Selected call was not found in the loaded dashboard rows.',
      'call.position': 'Call {position} in this resolved thread.',
      'call.context_estimate_hint': 'Load raw evidence to compare exact uncached input with visible log entries. The gap should be treated as hidden scaffolding, serialization, or tokenizer estimate error.',
      'call.compaction_hint': 'Load raw evidence to detect explicit compaction events and view redacted replacement history when available.',
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
    };
    let availableLanguages = Array.isArray(initialPayload.available_languages) && initialPayload.available_languages.length
      ? initialPayload.available_languages
      : [{ code: 'en', english_name: 'English', native_name: 'English', dir: 'ltr' }];
    let supportedLanguages = new Set(availableLanguages.map(language => language.code));
    let translationCatalog = initialPayload.translation_catalog || { [initialPayload.language || 'en']: initialPayload.translations || {} };
    let fallbackTranslations = { ...builtInFallbackTranslations, ...(translationCatalog.en || initialPayload.translations || {}) };
    function storedLanguage() {
      try {
        return window.localStorage ? window.localStorage.getItem('codex-usage-dashboard-language') : '';
      } catch (error) {
        return '';
      }
    }
    function normalizeLanguage(value) {
      const aliases = {
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
      const raw = String(value || '').trim();
      const normalized = raw.toLowerCase().replace(/_/g, '-');
      const candidate = aliases[normalized] || raw;
      return supportedLanguages.has(candidate) ? candidate : 'en';
    }
    let currentLanguage = normalizeLanguage(storedLanguage() || initialPayload.language || 'en');
    let translations = translationCatalog[currentLanguage] || fallbackTranslations;
    let liveStatusKey = window.location.protocol !== 'file:' ? 'badge.live' : 'status.static';
    let liveStatusDetail = '';
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
    function languageDirection(language) {
      const entry = availableLanguages.find(candidate => candidate.code === language);
      return entry && entry.dir === 'rtl' ? 'rtl' : 'ltr';
    }
    function populateLanguageOptions() {
      if (!languageSelectEl) return;
      languageSelectEl.innerHTML = availableLanguages.map(language => {
        const label = language.native_name || language.english_name || language.code;
        return `<option value="${escapeHtml(language.code)}" dir="${escapeHtml(language.dir || 'ltr')}">${escapeHtml(label)}</option>`;
      }).join('');
      languageSelectEl.value = currentLanguage;
    }
    function translateEffort(value) {
      if (!value) return value;
      const key = `effort.${String(value).toLowerCase()}`;
      const translated = t(key);
      return translated === key ? value : translated;
    }
    const stateManager = window.CodexUsageDashboardState;
    const urlParams = new URLSearchParams(window.location.search);
    const initialState = stateManager ? stateManager.read(urlParams) : {};
    let data = payloadRows(initialPayload);
    let pricingConfigured = Boolean(initialPayload.pricing_configured);
    let pricingSource = initialPayload.pricing_source || {};
    let pricingSnapshotWarning = initialPayload.pricing_snapshot_warning || '';
    let allowanceConfigured = Boolean(initialPayload.allowance_configured);
    let allowanceSource = initialPayload.allowance_source || {};
    let allowanceWindows = Array.isArray(initialPayload.allowance_windows) ? initialPayload.allowance_windows : [];
    let allowanceError = initialPayload.allowance_error || '';
    let rateCardError = initialPayload.rate_card_error || '';
    let projectMetadataPrivacy = initialPayload.project_metadata_privacy || { mode: initialPayload.privacy_mode || 'normal' };
    let parserDiagnostics = initialPayload.parser_diagnostics || {};
    let apiToken = initialPayload.api_token || '';
    let contextApiEnabled = Boolean(initialPayload.context_api_enabled);
    let actionThresholds = initialPayload.action_thresholds || {};
    let totalAvailableRows = Number(initialPayload.total_available_rows || data.length);
    let activeAvailableRows = Number(initialPayload.active_available_rows || data.length);
    let allHistoryAvailableRows = Number(initialPayload.all_history_available_rows || totalAvailableRows);
    let archivedAvailableRows = Number(initialPayload.archived_available_rows || Math.max(allHistoryAvailableRows - activeAvailableRows, 0));
    let loadedLimit = payloadLimit(initialPayload);
    const rowsEl = document.getElementById('rows');
    const detailEl = document.getElementById('detail');
    const searchEl = document.getElementById('search');
    const modelEl = document.getElementById('model');
    const effortEl = document.getElementById('effort');
    const pricingStatusEl = document.getElementById('pricingStatus');
    const datePresetEl = document.getElementById('datePreset');
    const dateStartEl = document.getElementById('dateStart');
    const dateEndEl = document.getElementById('dateEnd');
    const dateRangeStatusEl = document.getElementById('dateRangeStatus');
    const sortEl = document.getElementById('sort');
    const tableTitleEl = document.getElementById('tableTitle');
    const tableCaptionEl = document.getElementById('tableCaption');
    const insightsViewEl = document.getElementById('insightsView');
    const callsViewEl = document.getElementById('callsView');
    const threadsViewEl = document.getElementById('threadsView');
    const insightsPanelEl = document.getElementById('insightsPanel');
    const insightCardsEl = document.getElementById('insightCards');
    const presetListEl = document.getElementById('presetList');
    const presetStatusEl = document.getElementById('presetStatus');
    const clearPresetEl = document.getElementById('clearPreset');
    const refreshDashboardEl = document.getElementById('refreshDashboard');
    const autoRefreshEl = document.getElementById('autoRefresh');
    const loadLimitEl = document.getElementById('loadLimit');
    const historyScopeEl = document.getElementById('historyScope');
    const languageSelectEl = document.getElementById('languageSelect');
    const liveStatusEl = document.getElementById('liveStatus');
    const copyViewLinkEl = document.getElementById('copyViewLink');
    const exportVisibleEl = document.getElementById('exportVisible');
    const actionStatusEl = document.getElementById('actionStatus');
    const loadMoreRowsEl = document.getElementById('loadMoreRows');
    const pageStatusEl = document.getElementById('pageStatus');
    const pagerEl = document.getElementById('pager');
    const toTopEl = document.getElementById('toTop');
    let rowByRecordId = new Map();
    let threadAttachmentByRecordId = new Map();
    const expandedThreads = new Set();
    const liveRefreshSupported = window.location.protocol !== 'file:';
    const initialPayloadIncludeArchived = Boolean(initialPayload.include_archived);
    let includeArchived = initialPayloadIncludeArchived;
    if (liveRefreshSupported && initialState.historyScope === 'all') includeArchived = true;
    const needsInitialHistoryRefresh = liveRefreshSupported && includeArchived !== initialPayloadIncludeArchived;
    const liveRefreshIntervalMs = 10000;
    const pageSize = 500;
    const threadCallPageSize = 100;
    const defaultContextEntries = 80;
    const datePresetLabels = {
      all: 'option.all_time',
      today: 'option.today',
      'this-week': 'option.this_week',
      'last-7-days': 'option.last_7_days',
      'this-month': 'option.this_month',
      custom: 'option.custom_range',
    };
    const allowedDatePresets = new Set(Object.keys(datePresetLabels));
    let activeView = ['calls', 'threads', 'insights', 'call'].includes(initialState.view) ? initialState.view : 'insights';
    let sortKey = optionValueExists(sortEl, initialState.sort) ? initialState.sort : sortEl.value || 'attention';
    let sortDirection = ['asc', 'desc'].includes(initialState.direction) ? initialState.direction : defaultSortDirection(sortKey);
    let threadCallSortKey = 'time';
    let threadCallSortDirection = 'desc';
    let activePreset = '';
    let selectedRecordId = initialState.record || '';
    let selectedThreadKey = initialState.thread || '';
    let refreshInFlight = false;
    let autoRefreshTimer = null;
    let currentPage = 1;
    const threadCallVisiblePages = new Map();
    const contextRequestState = new Map();
    let pendingFocusTarget = null;
    let fastTooltipEl = null;
    let fastTooltipTarget = null;
    let fastTooltipTimer = null;
    let initialThreadExpansionApplied = false;
    let initialDetailApplied = false;
    const presetDefinitions = [
      {
        key: 'highest-cost',
        labelKey: 'preset.highest_cost_threads',
        descriptionKey: 'preset.highest_cost_threads_desc',
        view: 'threads',
        sort: 'cost',
        direction: 'desc',
        captionKey: 'preset.highest_cost_threads_caption',
        matches: () => true,
      },
      {
        key: 'context-bloat',
        labelKey: 'preset.context_bloat',
        descriptionKey: 'preset.context_bloat_desc',
        view: 'calls',
        sort: 'context',
        direction: 'desc',
        captionKey: 'preset.context_bloat_caption',
        matches: row => Number(row.context_window_percent || 0) >= threshold('high_context_percent', 0.6) || Number(row.cumulative_total_tokens || 0) >= threshold('large_cumulative_tokens', 200000),
      },
      {
        key: 'cache-misses',
        labelKey: 'preset.cache_misses',
        descriptionKey: 'preset.cache_misses_desc',
        view: 'calls',
        sort: 'cache',
        direction: 'asc',
        captionKey: 'preset.cache_misses_caption',
        matches: row => Number(row.input_tokens || 0) > 0 && Number(row.cache_ratio || 0) < threshold('low_cache_ratio', 0.3),
      },
      {
        key: 'pricing-gaps',
        labelKey: 'preset.pricing_gaps',
        descriptionKey: 'preset.pricing_gaps_desc',
        view: 'calls',
        sort: 'total',
        direction: 'desc',
        pricingStatus: 'unpriced',
        captionKey: 'preset.pricing_gaps_caption',
        matches: row => !row.pricing_model,
      },
      {
        key: 'estimated-review',
        labelKey: 'preset.estimated_price_review',
        descriptionKey: 'preset.estimated_price_review_desc',
        view: 'calls',
        sort: 'cost',
        direction: 'desc',
        pricingStatus: 'estimated',
        captionKey: 'preset.estimated_price_review_caption',
        matches: row => Boolean(row.pricing_estimated),
      },
      {
        key: 'usage-credits',
        labelKey: 'preset.highest_codex_credits',
        descriptionKey: 'preset.highest_codex_credits_desc',
        view: 'calls',
        sort: 'usage',
        direction: 'desc',
        captionKey: 'preset.highest_codex_credits_caption',
        matches: row => Number(row.usage_credits || 0) > 0,
      },
    ];
    function applyTranslations() {
      translations = translationCatalog[currentLanguage] || fallbackTranslations;
      document.documentElement.lang = currentLanguage;
      document.documentElement.dir = languageDirection(currentLanguage);
      document.title = t('dashboard.title');
      if (languageSelectEl) languageSelectEl.value = currentLanguage;
      document.querySelectorAll('[data-i18n]').forEach(element => {
        if (element === detailEl) return;
        element.textContent = t(element.dataset.i18n);
      });
      document.querySelectorAll('[data-i18n-placeholder]').forEach(element => {
        element.setAttribute('placeholder', t(element.dataset.i18nPlaceholder));
      });
      document.querySelectorAll('[data-i18n-title]').forEach(element => {
        setFastTooltip(element, t(element.dataset.i18nTitle));
      });
      document.querySelectorAll('[data-i18n-aria-label]').forEach(element => {
        element.setAttribute('aria-label', t(element.dataset.i18nAriaLabel));
      });
      if (detailEl && detailEl.dataset.i18n && !detailEl.querySelector('.detail-stack')) {
        detailEl.textContent = t(detailEl.dataset.i18n);
      }
      renderLiveStatus();
    }
    function setLanguage(language) {
      currentLanguage = normalizeLanguage(language);
      try {
        if (window.localStorage) window.localStorage.setItem('codex-usage-dashboard-language', currentLanguage);
      } catch (error) {
        // Local storage can be unavailable for file URLs or privacy settings.
      }
      applyTranslations();
      render();
      rerenderSelectedDetail();
    }
    function rerenderSelectedDetail() {
      if (selectedRecordId) {
        const row = rowByRecordId.get(selectedRecordId);
        if (row) showDetail(row);
        return;
      }
      if (selectedThreadKey) {
        const group = groups.find(candidate => candidate.key === selectedThreadKey);
        if (group) showThreadDetail(group);
      }
    }
    function resetVisibleRows() {
      currentPage = 1;
      threadCallVisiblePages.clear();
    }
    function queueFocusTarget(target) {
      if (!target) return;
      pendingFocusTarget = target;
      if (target.threadKey) {
        selectedThreadKey = target.threadKey;
        selectedRecordId = '';
        if (target.expandThread) expandedThreads.add(target.threadKey);
      }
      if (target.recordId) {
        selectedRecordId = target.recordId;
        selectedThreadKey = '';
      }
    }
    function ensurePendingFocusVisibleInRows(rows) {
      if (!pendingFocusTarget || !pendingFocusTarget.recordId) return;
      const index = rows.findIndex(row => row.record_id === pendingFocusTarget.recordId);
      if (index >= 0) currentPage = Math.max(currentPage, Math.ceil((index + 1) / pageSize));
    }
    function ensurePendingFocusVisibleInGroups(groups) {
      if (!pendingFocusTarget || !pendingFocusTarget.threadKey) return;
      const index = groups.findIndex(group => group.key === pendingFocusTarget.threadKey);
      if (index >= 0) currentPage = Math.max(currentPage, Math.ceil((index + 1) / pageSize));
    }
    function focusPendingTarget() {
      if (!pendingFocusTarget) return;
      const target = pendingFocusTarget;
      const selector = target.threadKey ? '.thread-row' : '.call-row, .thread-call-row';
      const element = [...rowsEl.querySelectorAll(selector)].find(row => (
        target.threadKey
          ? row.dataset.threadKey === target.threadKey
          : row.dataset.recordId === target.recordId
      ));
      if (!element) return;
      pendingFocusTarget = null;
      element.scrollIntoView({ block: 'center', behavior: 'auto' });
      element.focus({ preventScroll: true });
      element.classList.add('focus-target');
      window.setTimeout(() => element.classList.remove('focus-target'), 2600);
    }
    function scheduleFocusPendingTarget() {
      if (!pendingFocusTarget) return;
      window.requestAnimationFrame(focusPendingTarget);
    }
    function directional(compareResult) {
      return sortDirection === 'asc' ? compareResult : -compareResult;
    }
    function setSort(key, direction = null) {
      sortKey = key;
      sortDirection = direction || defaultSortDirection(key);
      sortEl.value = key;
      resetVisibleRows();
      render();
    }
    function handleHeaderSort(key) {
      if (sortKey === key) {
        sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
      } else {
        sortKey = key;
        sortDirection = defaultSortDirection(key);
      }
      sortEl.value = key;
      resetVisibleRows();
      render();
    }
    function updateSortControls() {
      sortEl.value = sortKey;
      document.querySelectorAll('[data-sort-header]').forEach(header => {
        const active = header.dataset.sortHeader === sortKey;
        header.dataset.sortActive = active ? 'true' : 'false';
        header.setAttribute('aria-sort', active ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none');
      });
      document.querySelectorAll('[data-sort-indicator]').forEach(indicator => {
        indicator.textContent = indicator.dataset.sortIndicator === sortKey ? (sortDirection === 'asc' ? '▲' : '▼') : '';
      });
      tableCaptionEl.dataset.sortDescription = tf('caption.sort_direction', {
        label: sortLabelText(sortKey),
        direction: sortDirection === 'asc' ? t('caption.ascending') : t('caption.descending'),
      });
    }
    function sortLabelText(key) {
      return {
        attention: t('option.needs_attention'),
        cache: t('table.cache'),
        context: t('metric.context_use'),
        cost: t('table.cost'),
        effort: t('table.effort'),
        model: t('table.model'),
        cached: t('table.cached'),
        uncached: t('table.uncached'),
        output: t('table.output'),
        signals: t('table.signals'),
        thread: t('table.thread'),
        time: t('table.time'),
        total: t('table.tokens'),
        usage: t('metric.codex_credits'),
      }[key] || t('filter.sort');
    }
    function moneyText(value) {
      return money(value, t('state.no_price'));
    }
    function creditsText(value) {
      return credits(value, t('state.no_rate'));
    }
    function loadedRowsDescription() {
      const loaded = number.format(data.length);
      const available = number.format(totalAvailableRows || data.length);
      const capped = loadedLimit !== null && totalAvailableRows > data.length;
      return capped
        ? tf('caption.loaded_capped', { loaded, available })
        : tf('caption.loaded', { loaded });
    }
    function historyRowsDescription() {
      const archived = Number(archivedAvailableRows || 0);
      if (includeArchived) {
        return archived
          ? tf('history.all_includes', { count: number.format(archived) })
          : t('history.all_empty');
      }
      return archived
        ? tf('history.active_hidden', { count: number.format(archived) })
        : t('history.active_only');
    }
    function updateHistoryScopeControl() {
      historyScopeEl.value = includeArchived ? 'all' : 'active';
      const detail = historyRowsDescription();
      setFastTooltip(historyScopeEl, detail);
      setFastTooltip(historyScopeEl.parentElement, tf('history.archived_scan_hint', { detail }));
    }
    function updateLoadLimitControl() {
      const value = limitValue(loadedLimit);
      const existing = new Set(Array.from(loadLimitEl.options).map(option => option.value));
      if (!existing.has(value)) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = tf('caption.loaded', { loaded: number.format(loadedLimit) });
        loadLimitEl.insertBefore(option, loadLimitEl.lastElementChild);
      }
      loadLimitEl.value = value;
    }
    function rebuildDashboardIndexes() {
      rowByRecordId = new Map(data.map(row => [row.record_id, row]));
      threadAttachmentByRecordId = new Map(data.map(row => [row.record_id, resolveThreadAttachment(row)]));
    }
    function usageCreditStatusLabel(row) {
      if (usageCreditValue(row) === null) return t('allowance.row_no_rate');
      if (row.usage_credit_confidence === 'exact') return t('credit.official_match');
      if (row.usage_credit_confidence === 'estimated') return t('credit.inferred_mapping');
      if (row.usage_credit_confidence === 'user_override') return t('credit.user_rate');
      return short(row.usage_credit_confidence, t('credit.configured_rate'));
    }
    function sourceLabelText(row) {
      if (isAutoReview(row)) return t('source.auto_review');
      if (row.subagent_type === 'thread_spawn') {
        return row.agent_role ? tf('source.subagent_role', { role: row.agent_role }) : t('source.subagent');
      }
      if (isSubagent(row)) return t('source.subagent');
      return t('source.user');
    }
    function attachmentRelationText(relation) {
      return {
        direct: t('thread.direct'),
        session: t('thread.session'),
        'explicit parent thread': t('thread.explicit_parent_thread'),
        'explicit parent': t('thread.explicit_parent'),
        'unmatched subagent': t('thread.unmatched_subagent'),
      }[relation] || relation || t('state.unknown');
    }
    function usageCreditsWithStatus(row) {
      const value = usageCreditValue(row);
      return value === null
        ? t('credit.no_mapped_rate')
        : tf('credit.with_status', { value: credits(value), status: usageCreditStatusLabel(row) });
    }
    function tooltipAttributes(text) {
      const safe = escapeHtml(text || '');
      return `title="${safe}" data-fast-tooltip data-tooltip="${safe}"`;
    }
    function setFastTooltip(element, text) {
      if (!element) return;
      const value = text || '';
      if (!value) {
        element.removeAttribute('title');
        element.removeAttribute('data-tooltip');
        element.removeAttribute('data-fast-tooltip');
        return;
      }
      element.setAttribute('title', value);
      element.dataset.tooltip = value;
      element.dataset.fastTooltip = '';
    }
    function ensureFastTooltipElement() {
      if (fastTooltipEl) return fastTooltipEl;
      fastTooltipEl = document.createElement('div');
      fastTooltipEl.className = 'fast-tooltip';
      fastTooltipEl.hidden = true;
      document.body.appendChild(fastTooltipEl);
      return fastTooltipEl;
    }
    function restoreNativeTooltip(target = fastTooltipTarget) {
      if (!target || !target.dataset) return;
      if (target.dataset.nativeTitle !== undefined) {
        target.setAttribute('title', target.dataset.nativeTitle);
        delete target.dataset.nativeTitle;
      }
    }
    function hideFastTooltip() {
      if (fastTooltipTimer) window.clearTimeout(fastTooltipTimer);
      fastTooltipTimer = null;
      restoreNativeTooltip();
      if (fastTooltipEl) fastTooltipEl.hidden = true;
      fastTooltipTarget = null;
    }
    function positionFastTooltip(target) {
      if (!fastTooltipEl || fastTooltipEl.hidden) return;
      const rect = target.getBoundingClientRect();
      const gap = 8;
      const width = fastTooltipEl.offsetWidth;
      const height = fastTooltipEl.offsetHeight;
      const left = clamp(rect.left + rect.width / 2 - width / 2, 8, window.innerWidth - width - 8);
      const above = rect.top - height - gap;
      const top = above >= 8 ? above : Math.min(rect.bottom + gap, window.innerHeight - height - 8);
      fastTooltipEl.style.left = `${left}px`;
      fastTooltipEl.style.top = `${Math.max(8, top)}px`;
    }
    function showFastTooltip(target) {
      const text = target.dataset.tooltip || target.getAttribute('title') || '';
      if (!text.trim()) {
        hideFastTooltip();
        return;
      }
      if (target.hasAttribute('title') && target.dataset.nativeTitle === undefined) {
        target.dataset.nativeTitle = target.getAttribute('title') || '';
        target.removeAttribute('title');
      }
      fastTooltipTarget = target;
      const tooltip = ensureFastTooltipElement();
      tooltip.textContent = text;
      tooltip.hidden = false;
      positionFastTooltip(target);
    }
    function scheduleFastTooltip(target) {
      if (!target) return;
      if (fastTooltipTimer) window.clearTimeout(fastTooltipTimer);
      restoreNativeTooltip();
      if (fastTooltipEl) fastTooltipEl.hidden = true;
      fastTooltipTarget = target;
      fastTooltipTimer = window.setTimeout(() => {
        fastTooltipTimer = null;
        showFastTooltip(target);
      }, 70);
    }
    function closestFastTooltipTarget(eventTarget) {
      return eventTarget && eventTarget.closest ? eventTarget.closest('[data-fast-tooltip]') : null;
    }
    function costUsageCell(costText, creditValue) {
      const usage = creditValue === null || creditValue === undefined ? t('credit.no_rate') : credits(creditValue);
      return `<span class="cost-cell" ${tooltipAttributes(`${t('metric.codex_credits')}: ${usage}`)}>${escapeHtml(costText)}</span>`;
    }
    function cachedInputTokens(row) {
      return dataCachedInputTokens(row);
    }
    function uncachedInputTokens(row) {
      return dataUncachedInputTokens(row);
    }
    function outputTokens(row) {
      return dataOutputTokens(row);
    }
    function tokenNumberCell(value, label) {
      return `<span class="token-number" ${tooltipAttributes(`${label}: ${number.format(value)}`)}>${escapeHtml(number.format(value))}</span>`;
    }
    function totalTokenCell(row) {
      const total = Number(row.total_tokens || 0);
      const title = [
        `${t('metric.total_tokens')}: ${number.format(total)}`,
        `${t('metric.cached_input')}: ${number.format(cachedInputTokens(row))}`,
        `${t('metric.uncached_input')}: ${number.format(uncachedInputTokens(row))}`,
        `${t('metric.output_tokens')}: ${number.format(outputTokens(row))}`,
        Number(row.reasoning_output_tokens || 0) ? `${t('metric.reasoning_output')}: ${number.format(row.reasoning_output_tokens || 0)}` : '',
      ].filter(Boolean).join(' - ');
      return `<span class="token-number token-total" ${tooltipAttributes(title)}>${escapeHtml(number.format(total))}</span>`;
    }
    function cachedTokenCell(row) {
      return tokenNumberCell(cachedInputTokens(row), t('metric.cached_input'));
    }
    function uncachedTokenCell(row) {
      return tokenNumberCell(uncachedInputTokens(row), t('metric.uncached_input'));
    }
    function outputTokenCell(row) {
      return tokenNumberCell(outputTokens(row), t('metric.output_tokens'));
    }
    function signedNumber(value) {
      const numeric = Number(value || 0);
      return `${numeric >= 0 ? '+' : ''}${number.format(numeric)}`;
    }
    function signedPct(value) {
      const numeric = Number(value || 0);
      return `${numeric >= 0 ? '+' : ''}${pct(numeric)}`;
    }
    function rowInputTokens(row) {
      return dataRowInputTokens(row);
    }
    function rowReasoningTokens(row) {
      return dataRowReasoningTokens(row);
    }
    function adjacentCalls(row) {
      return adjacentThreadCalls(data, row);
    }
    function cacheDiagnostic(row, previous = null) {
      const diagnostic = classifyCacheDiagnostic(row, previous);
      if (diagnostic === 'post_compaction') {
        return {
          key: 'post-compaction',
          label: t('call.post_compaction'),
          body: 'A compaction marker or reset-like profile is associated with this call. Load evidence to confirm replacement context.',
        };
      }
      if (diagnostic === 'cold') {
        return {
          key: 'cold',
          label: t('call.cache_cold'),
          body: 'Conversation-specific cache likely expired or missed; remaining cache is probably stable Codex scaffolding or tool schema prefix.',
        };
      }
      if (diagnostic === 'spike') {
        return {
          key: 'spike',
          label: t('call.cache_spike'),
          body: 'Fresh input rose sharply compared with the previous call in this resolved thread.',
        };
      }
      if (diagnostic === 'warm') {
        return {
          key: 'warm',
          label: t('call.cache_warm'),
          body: 'Most input tokens reused prompt cache. The uncached portion is the most likely investigation target.',
        };
      }
      if (diagnostic === 'partial') {
        return {
          key: 'partial',
          label: t('call.cache_partial'),
          body: 'Some prefix reused cache, but a meaningful share of the input was fresh or reserialized.',
        };
      }
      return {
        key: 'cold',
        label: t('call.cache_cold'),
        body: 'This call has little or no cache reuse, so most input was charged as fresh.',
      };
    }
    function callDeltaRows(row, previous) {
      if (!previous) return [];
      const delta = callAccountingDelta(row, previous);
      return [
        [t('metric.last_call_input'), signedNumber(delta.input)],
        [t('metric.cached_input'), signedNumber(delta.cached)],
        [t('metric.uncached_input'), signedNumber(delta.uncached)],
        [t('metric.output'), signedNumber(delta.output)],
        [t('metric.reasoning_output'), signedNumber(delta.reasoning)],
        [t('metric.cache_ratio'), signedPct(delta.cacheRatio)],
      ];
    }
    function investigatorUrl(row, overrides = {}) {
      if (!stateManager) return '#';
      return stateManager.urlFor({
        ...currentDashboardState(),
        ...overrides,
        view: 'call',
        record: row.record_id || '',
        thread: rowAttachment(row).key,
        expandedThreads: Array.from(expandedThreads),
      });
    }
    function tableUrlForRow(row) {
      if (!stateManager) return '#';
      return stateManager.urlFor({
        ...currentDashboardState(),
        view: 'calls',
        record: row.record_id || '',
        thread: rowAttachment(row).key,
        expandedThreads: Array.from(expandedThreads),
      });
    }
    function openInvestigator(row) {
      const url = investigatorUrl(row);
      const opened = window.open(url, '_blank', 'noopener');
      if (!opened) window.location.href = url;
    }
    async function copyCallLink(row) {
      if (!stateManager) return;
      try {
        await stateManager.copyText(investigatorUrl(row));
        showActionStatus(t('action.copied'));
      } catch (error) {
        showActionStatus(t('action.copy_failed'));
      }
    }
    function effortTooltipText(values) {
      const unique = [...new Set(values.filter(Boolean).map(value => translateEffort(short(value))))].sort();
      return unique.length ? unique.join(' - ') : t('state.unknown');
    }
    function effortCell(label, tooltip) {
      return `<span class="effort-cell" ${tooltipAttributes(tooltip || label)}>${escapeHtml(label)}</span>`;
    }
    function signalPuckLabel(row, flag, index) {
      return translateEfficiencyFlag(row, flag, index);
    }
    function signalPuckAbbreviation(flag, label) {
      const byFlag = {
        'context-bloat': 'CTX',
        'elevated-context-use': 'CTX',
        'elevated-context': 'CTX',
        'expensive-low-output-call': 'LO',
        'estimated-pricing': 'EST',
        'high-context-use': 'CTX',
        'high-estimated-cost': '$',
        'high-cost': '$',
        'high-reasoning-share': 'RSN',
        'large-thread': 'BIG',
        'low-cache-reuse': 'CACHE',
        'low-cache': 'CACHE',
        'low-output': 'LO',
        'pricing-gap': 'PRICE',
        'reasoning-spike': 'RSN',
        'subagent-attribution': 'SUB',
      };
      const normalized = String(flag || '').toLowerCase().replace(/[_\s]+/g, '-');
      if (byFlag[normalized]) return byFlag[normalized];
      const words = String(label || flag || '')
        .replace(/[^a-zA-Z0-9 ]/g, ' ')
        .split(/\s+/)
        .filter(Boolean);
      if (!words.length) return '?';
      if (words.length === 1) return words[0].slice(0, 4).toUpperCase();
      return words.slice(0, 3).map(word => word[0]).join('').toUpperCase();
    }
    function renderSignalPucks(row, flags, max = 3, emptyLabel = '') {
      if (!flags.length) return emptyLabel ? `<span class="muted">${escapeHtml(emptyLabel)}</span>` : '';
      const visible = flags.slice(0, max);
      const pucks = visible.map((flag, index) => {
        const label = signalPuckLabel(row, flag, index);
        return `<span class="flag signal-puck" ${tooltipAttributes(label)}>${escapeHtml(signalPuckAbbreviation(flag, label))}</span>`;
      });
      if (flags.length > max) {
        const remaining = flags.slice(max).map((flag, offset) => signalPuckLabel(row, flag, max + offset)).join(' - ');
        pucks.push(`<span class="flag signal-puck more" ${tooltipAttributes(remaining)}>+${escapeHtml(flags.length - max)}</span>`);
      }
      return pucks.join('');
    }
    function allowanceWindowText(totalCredits, mode = 'impact') {
      if (!allowanceWindows.length) return '';
      const labels = allowanceWindows.map(window => {
        const label = short(window.label || window.key, 'Window');
        const total = Number(window.total_credits || 0);
        const remainingCredits = window.remaining_credits === null || window.remaining_credits === undefined ? null : Number(window.remaining_credits);
        const remainingPercent = window.remaining_percent === null || window.remaining_percent === undefined ? null : Number(window.remaining_percent);
        if (mode === 'remaining-card' && remainingPercent !== null && Number.isFinite(remainingPercent)) {
          return `${label} ${pct(remainingPercent)}`;
        }
        if (mode === 'remaining-card' && remainingCredits !== null && Number.isFinite(remainingCredits)) {
          return `${label} ${tf('allowance.cr_left', { value: credits(remainingCredits) })}`;
        }
        if (mode === 'impact' && total > 0) {
          return `${label} ${tf('allowance.of_allowance', { ratio: pct(totalCredits / total) })}`;
        }
        if (mode === 'impact' && remainingCredits !== null && Number.isFinite(remainingCredits)) {
          return `${label} ${tf('allowance.used_vs_remaining', { used: credits(totalCredits), remaining: credits(remainingCredits) })}`;
        }
        if (remainingPercent !== null && Number.isFinite(remainingPercent)) {
          return `${label} ${tf('allowance.remaining', { value: pct(remainingPercent) })}`;
        }
        if (remainingCredits !== null && Number.isFinite(remainingCredits)) {
          return `${label} ${tf('allowance.credits_remaining', { value: credits(remainingCredits) })}`;
        }
        if (total > 0) {
          return `${label} ${tf('allowance.of_total', { used: credits(totalCredits), total: credits(total) })}`;
        }
        return tf('allowance.window_configured', { label });
      });
      return labels.join(mode === 'remaining-card' ? '\n' : ' · ');
    }
    function allowanceImpactText(totalCredits) {
      const windowImpact = allowanceWindowText(totalCredits, 'remaining-card') || allowanceWindowText(totalCredits, 'impact');
      if (windowImpact) return windowImpact;
      if (allowanceError) return t('state.allowance_config_error');
      return allowanceConfigured ? t('state.allowance_configured') : t('action.set_limits');
    }
    function rowAllowanceImpact(row) {
      const value = usageCreditValue(row);
      if (value === null) return t('allowance.row_no_rate');
      const impact = allowanceWindowText(value, 'impact');
      return impact || tf('allowance.counted', { value: credits(value) });
    }
    function updateAllowanceSourceLine() {
      const sourceEl = document.getElementById('allowanceSource');
      const sourceName = allowanceSource.name || 'Codex credit rates';
      const coverage = creditCoverageRatio(data);
      sourceEl.textContent = t('badge.credits');
      sourceEl.dataset.state = coverage > 0 ? 'ready' : 'missing';
      setFastTooltip(sourceEl, [
        allowanceSource.url ? `Source: ${allowanceSource.url}` : '',
        allowanceSource.fetched_at ? `rate card snapshot ${allowanceSource.fetched_at}` : '',
        tf('allowance.credit_rates', { source: sourceName }),
        tf('allowance.credit_coverage', { ratio: pct(coverage) }),
        allowanceWindows.length ? tf('allowance.windows', { windows: allowanceWindows.map(window => short(window.label || window.key)).join(', ') }) : t('allowance.init_hint'),
        allowanceWindows.some(window => window.reset_at) ? tf('allowance.resets', { resets: allowanceWindows.map(window => window.reset_at ? `${short(window.label || window.key)} ${formatTimestamp(window.reset_at, window.reset_at)}` : '').filter(Boolean).join('; ') }) : '',
        allowanceError ? `${t('state.allowance_config_error')}: ${allowanceError}` : '',
        rateCardError ? tf('allowance.rate_card_error', { error: rateCardError }) : '',
      ].filter(Boolean).join(' '));
    }
    function rebuildSelectOptions(select, values, label) {
      const previous = select.value;
      select.textContent = '';
      const allOption = document.createElement('option');
      allOption.value = '';
      allOption.textContent = label;
      select.appendChild(allOption);
      [...new Set(values.filter(Boolean))].sort().forEach(value => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = select.id === 'effort' ? translateEffort(value) : value;
        select.appendChild(option);
      });
      const valuesSet = new Set(Array.from(select.options).map(option => option.value));
      select.value = valuesSet.has(previous) ? previous : '';
    }
    function rebuildFilterOptions() {
      rebuildSelectOptions(modelEl, data.map(row => row.model), t('option.all_models'));
      rebuildSelectOptions(effortEl, data.map(row => row.effort), t('option.all_efforts'));
    }
    function applyInitialState() {
      if (!initialState) return;
      searchEl.value = initialState.search || '';
      if (optionValueExists(modelEl, initialState.model)) modelEl.value = initialState.model;
      if (optionValueExists(effortEl, initialState.effort)) effortEl.value = initialState.effort;
      if (optionValueExists(pricingStatusEl, initialState.confidence)) pricingStatusEl.value = initialState.confidence;
      const initialDatePreset = allowedDatePresets.has(initialState.datePreset) ? initialState.datePreset : '';
      const initialDateStart = cleanDateInput(initialState.dateStart);
      const initialDateEnd = cleanDateInput(initialState.dateEnd);
      if (initialDatePreset && initialDatePreset !== 'custom' && initialDatePreset !== 'all') {
        datePresetEl.value = initialDatePreset;
        syncDatePresetInputs();
      } else if (initialDateStart || initialDateEnd) {
        datePresetEl.value = 'custom';
        dateStartEl.value = initialDateStart;
        dateEndEl.value = initialDateEnd;
      } else if (initialDatePreset) {
        datePresetEl.value = initialDatePreset;
      }
      if (optionValueExists(sortEl, initialState.sort)) {
        sortKey = initialState.sort;
        sortEl.value = sortKey;
      }
      if (['asc', 'desc'].includes(initialState.direction)) sortDirection = initialState.direction;
      if (presetDefinitions.some(preset => preset.key === initialState.preset)) activePreset = initialState.preset;
      if (initialState.page && Number(initialState.page) > 1) currentPage = Number(initialState.page);
      if (Array.isArray(initialState.expandedThreads)) {
        initialState.expandedThreads.forEach(key => expandedThreads.add(key));
      }
      if (initialState.expandedThreads && initialState.expandedThreads.length) {
        initialThreadExpansionApplied = true;
      }
    }
    function updatePricingSourceLine() {
      const sourceEl = document.getElementById('pricingSource');
      if (pricingConfigured && pricingSource.url) {
        const sourceParts = [
          pricingSource.name || t('pricing.source'),
          pricingSource.tier ? tf('pricing.tier', { tier: pricingSource.tier }) : '',
          pricingSource.fetched_at ? tf('pricing.fetched', { time: formatTimestamp(pricingSource.fetched_at) }) : '',
          pricingSource.pinned ? t('pricing.pinned') : '',
        ].filter(Boolean);
        sourceEl.textContent = t('badge.costs');
        sourceEl.dataset.state = 'ready';
        setFastTooltip(sourceEl, pricingSource.fetched_at
          ? tf('pricing.title_fetched', { parts: sourceParts.join(' · '), url: pricingSource.url, time: formatTimestampTitle(pricingSource.fetched_at), warning: pricingSnapshotWarning ? ` ${pricingSnapshotWarning}` : '' })
          : tf('pricing.title', { parts: sourceParts.join(' · '), warning: pricingSnapshotWarning ? ` ${pricingSnapshotWarning}` : '' }));
      } else {
        sourceEl.textContent = pricingConfigured ? t('badge.costs') : t('badge.no_costs');
        sourceEl.dataset.state = pricingConfigured ? 'ready' : 'missing';
        setFastTooltip(sourceEl, pricingConfigured ? (pricingSnapshotWarning || '') : t('pricing.configure_hint'));
      }
    }
    function updateParserDiagnosticsLine() {
      const sourceEl = document.getElementById('parserDiagnostics');
      const entries = Object.entries(parserDiagnostics || {}).filter(([, value]) => Number(value || 0) > 0);
      if (!entries.length) {
        sourceEl.hidden = true;
        sourceEl.textContent = '';
        setFastTooltip(sourceEl, '');
        return;
      }
      const total = entries.reduce((sum, [, value]) => sum + Number(value || 0), 0);
      sourceEl.hidden = false;
      sourceEl.textContent = t('badge.parser_warnings');
      sourceEl.dataset.state = 'missing';
      setFastTooltip(sourceEl, tf('parser.warnings_title', { count: number.format(total), entries: entries.map(([key, value]) => `${key}=${value}`).join(', ') }));
    }
    function updatePrivacyModeLine() {
      const sourceEl = document.getElementById('privacyMode');
      const mode = projectMetadataPrivacy.mode || 'normal';
      sourceEl.textContent = mode === 'normal' ? t('badge.metadata_normal') : tf('badge.metadata_mode', { mode });
      sourceEl.dataset.state = mode === 'normal' ? 'ready' : 'missing';
      setFastTooltip(sourceEl, mode === 'normal'
        ? t('privacy.normal_title')
        : [
            tf('privacy.mode', { mode }),
            projectMetadataPrivacy.cwd_redacted ? t('privacy.cwd_redacted') : '',
            projectMetadataPrivacy.project_names_redacted ? t('privacy.project_names_redacted') : '',
            projectMetadataPrivacy.git_remote_label_hidden ? t('privacy.git_remote_label_hidden') : '',
            projectMetadataPrivacy.relative_cwd_hidden ? t('privacy.relative_cwd_hidden') : '',
            projectMetadataPrivacy.git_branch_hidden ? t('privacy.git_branch_hidden') : '',
            projectMetadataPrivacy.tags_hidden ? t('privacy.tags_hidden') : '',
            projectMetadataPrivacy.aliases_preserved ? t('privacy.aliases_preserved') : '',
          ].filter(Boolean).join(' '));
    }
    function padDatePart(value) {
      return String(value).padStart(2, '0');
    }
    function localDateKey(date) {
      return `${date.getFullYear()}-${padDatePart(date.getMonth() + 1)}-${padDatePart(date.getDate())}`;
    }
    function localDay(value = new Date()) {
      return new Date(value.getFullYear(), value.getMonth(), value.getDate());
    }
    function addDays(date, days) {
      return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
    }
    function parseDateInput(value) {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null;
      const [year, month, day] = value.split('-').map(Number);
      const date = new Date(year, month - 1, day);
      return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : null;
    }
    function cleanDateInput(value) {
      const date = parseDateInput(value);
      return date ? localDateKey(date) : '';
    }
    function weekStart(date) {
      const day = date.getDay();
      const offset = day === 0 ? -6 : 1 - day;
      return addDays(date, offset);
    }
    function presetDateRange(preset) {
      const today = localDay();
      if (preset === 'today') {
        return { start: today, endExclusive: addDays(today, 1) };
      }
      if (preset === 'this-week') {
        const start = weekStart(today);
        return { start, endExclusive: addDays(start, 7) };
      }
      if (preset === 'last-7-days') {
        return { start: addDays(today, -6), endExclusive: addDays(today, 1) };
      }
      if (preset === 'this-month') {
        return {
          start: new Date(today.getFullYear(), today.getMonth(), 1),
          endExclusive: new Date(today.getFullYear(), today.getMonth() + 1, 1),
        };
      }
      return { start: null, endExclusive: null };
    }
    function syncDatePresetInputs() {
      const preset = datePresetEl.value;
      if (preset === 'custom') return;
      if (preset === 'all') {
        dateStartEl.value = '';
        dateEndEl.value = '';
        return;
      }
      const range = presetDateRange(preset);
      dateStartEl.value = range.start ? localDateKey(range.start) : '';
      dateEndEl.value = range.endExclusive ? localDateKey(addDays(range.endExclusive, -1)) : '';
    }
    function formatDateRangeLabel(prefix, start, end) {
      const startLabel = start ? localDateKey(start) : '';
      const endLabel = end ? localDateKey(end) : '';
      if (startLabel && endLabel && startLabel === endLabel) return tf('date.range_exact', { prefix, date: startLabel });
      if (startLabel && endLabel) return tf('date.range_between', { prefix, start: startLabel, end: endLabel });
      if (startLabel) return tf('date.range_from', { prefix, start: startLabel });
      if (endLabel) return tf('date.range_through', { prefix, end: endLabel });
      return prefix;
    }
    function currentDateRange() {
      const preset = allowedDatePresets.has(datePresetEl.value) ? datePresetEl.value : 'all';
      if (preset !== 'custom' && preset !== 'all') {
        const range = presetDateRange(preset);
        return {
          active: true,
          invalid: false,
          start: range.start,
          endExclusive: range.endExclusive,
          label: formatDateRangeLabel(t(datePresetLabels[preset]), range.start, addDays(range.endExclusive, -1)),
        };
      }
      const start = parseDateInput(dateStartEl.value);
      const end = parseDateInput(dateEndEl.value);
      if (start && end && start > end) {
        return {
          active: true,
          invalid: true,
          start,
          endExclusive: addDays(end, 1),
          label: t('date.invalid_range'),
        };
      }
      if (start || end) {
        return {
          active: true,
          invalid: false,
          start,
          endExclusive: end ? addDays(end, 1) : null,
          label: formatDateRangeLabel(t('date.custom'), start, end),
        };
      }
      return { active: false, invalid: false, start: null, endExclusive: null, label: t('option.all_time') };
    }
    function rowMatchesDateRange(row, range) {
      if (range.invalid) return false;
      if (!range.active) return true;
      const timestamp = row.event_timestamp ? new Date(row.event_timestamp) : null;
      if (!timestamp || Number.isNaN(timestamp.getTime())) return false;
      if (range.start && timestamp < range.start) return false;
      if (range.endExclusive && timestamp >= range.endExclusive) return false;
      return true;
    }
    function updateDateFilterControls() {
      const range = currentDateRange();
      const showStatus = range.active || range.invalid;
      dateRangeStatusEl.hidden = !showStatus;
      dateRangeStatusEl.textContent = showStatus ? range.label : '';
      dateRangeStatusEl.dataset.state = range.invalid ? 'error' : range.active ? 'active' : 'idle';
      return range;
    }
    function dateCaptionPrefix(range = currentDateRange()) {
      return range.active || range.invalid ? `${range.label}. ` : '';
    }
    function filtered(dateRange = currentDateRange()) {
      const term = searchEl.value.trim().toLowerCase();
      const model = modelEl.value;
      const effort = effortEl.value;
      const pricingStatus = pricingStatusEl.value;
      const rows = data.filter(row => {
        const haystack = [
          rowThreadLabel(row),
          row.cwd,
          row.project_name,
          row.project_relative_cwd,
          Array.isArray(row.project_tags) ? row.project_tags.join(' ') : '',
          row.git_branch,
          row.git_remote_label,
          row.model,
          row.effort,
          row.session_id,
          row.turn_id,
          row.thread_source,
          row.subagent_type,
          row.agent_role,
          row.agent_nickname,
          row.parent_session_id,
          row.parent_thread_name,
          row.resolved_parent_thread_name,
        ].join(' ').toLowerCase();
        const statusMatches = !pricingStatus
          || (pricingStatus === 'official' && row.pricing_model && !row.pricing_estimated)
          || (pricingStatus === 'estimated' && row.pricing_estimated)
          || (pricingStatus === 'unpriced' && !row.pricing_model)
          || (pricingStatus === 'credit-exact' && row.usage_credit_confidence === 'exact')
          || (pricingStatus === 'credit-estimated' && row.usage_credit_confidence === 'estimated')
          || (pricingStatus === 'credit-override' && row.usage_credit_confidence === 'user_override')
          || (pricingStatus === 'credit-missing' && row.usage_credit_confidence === 'unpriced');
        return (!term || haystack.includes(term)) && (!model || row.model === model) && (!effort || row.effort === effort) && statusMatches && rowMatchesDateRange(row, dateRange) && presetMatchesRow(row);
      });
      rows.sort(compareCalls);
      return rows;
    }
    function currentDashboardState() {
      return {
        view: activeView,
        search: searchEl.value.trim(),
        model: modelEl.value,
        effort: effortEl.value,
        confidence: pricingStatusEl.value,
        datePreset: datePresetEl.value,
        dateStart: datePresetEl.value === 'custom' ? dateStartEl.value : '',
        dateEnd: datePresetEl.value === 'custom' ? dateEndEl.value : '',
        historyScope: includeArchived ? 'all' : 'active',
        sort: sortKey,
        direction: sortDirection,
        preset: activePreset,
        page: currentPage,
        record: selectedRecordId,
        thread: selectedThreadKey,
        expandedThreads: Array.from(expandedThreads),
      };
    }
    function syncUrlState() {
      if (!stateManager) return;
      stateManager.replace(currentDashboardState());
    }
    function showActionStatus(message) {
      actionStatusEl.textContent = message;
      if (!message) return;
      window.setTimeout(() => {
        if (actionStatusEl.textContent === message) actionStatusEl.textContent = '';
      }, 2200);
    }
    async function copyCurrentViewLink() {
      if (!stateManager) return;
      const url = stateManager.urlFor(currentDashboardState());
      try {
        await stateManager.copyText(url);
        showActionStatus(t('action.copied'));
      } catch (error) {
        showActionStatus(t('action.copy_failed'));
      }
    }
    function exportCurrentRows() {
      if (!stateManager) return;
      const rows = filtered();
      const columns = [
        { label: 'timestamp', field: 'event_timestamp' },
        { label: 'thread', field: row => rowThreadLabel(row) },
        { label: 'project', field: 'project_name' },
        { label: 'model', field: 'model' },
        { label: 'effort', field: 'effort' },
        { label: 'total_tokens', field: 'total_tokens' },
        { label: 'input_tokens', field: 'input_tokens' },
        { label: 'cached_input_tokens', field: 'cached_input_tokens' },
        { label: 'uncached_input_tokens', field: 'uncached_input_tokens' },
        { label: 'output_tokens', field: 'output_tokens' },
        { label: 'reasoning_output_tokens', field: 'reasoning_output_tokens' },
        { label: 'estimated_cost_usd', field: 'estimated_cost_usd' },
        { label: 'usage_credits', field: 'usage_credits' },
        { label: 'cache_ratio', field: 'cache_ratio' },
        { label: 'context_window_percent', field: 'context_window_percent' },
        { label: 'pricing_model', field: 'pricing_model' },
        { label: 'usage_credit_confidence', field: 'usage_credit_confidence' },
        { label: 'recommendation', field: row => row.recommended_action || recommendationSummary(row) },
        { label: 'record_id', field: 'record_id' },
      ];
      const csv = stateManager.toCsv(rows, columns);
      const suffix = activeView === 'threads' ? 'thread-filtered-calls' : `${activeView}-calls`;
      stateManager.downloadText(`codex-usage-${suffix}.csv`, csv, 'text/csv;charset=utf-8');
      showActionStatus(tf('action.exported', { count: number.format(rows.length) }));
    }
    function activePresetDefinition() {
      return presetDefinitions.find(preset => preset.key === activePreset) || null;
    }
    function presetMatchesRow(row) {
      const preset = activePresetDefinition();
      return preset ? preset.matches(row) : true;
    }
    function applyPreset(key, focusTarget = null) {
      const preset = presetDefinitions.find(candidate => candidate.key === key);
      if (!preset) return;
      activePreset = preset.key;
      activeView = preset.view;
      pricingStatusEl.value = preset.pricingStatus || '';
      sortKey = preset.sort;
      sortDirection = preset.direction || defaultSortDirection(preset.sort);
      sortEl.value = preset.sort;
      resetVisibleRows();
      queueFocusTarget(focusTarget);
      render();
    }
    function clearPreset() {
      activePreset = '';
      pricingStatusEl.value = '';
      sortKey = 'attention';
      sortDirection = defaultSortDirection(sortKey);
      sortEl.value = sortKey;
      resetVisibleRows();
      render();
    }
    function threshold(key, fallback) {
      const value = Number(actionThresholds[key]);
      return Number.isFinite(value) ? value : fallback;
    }
    function topRecommendation(row) {
      return Array.isArray(row.action_recommendations) && row.action_recommendations.length
        ? row.action_recommendations[0]
        : null;
    }
    function recommendationSummary(row) {
      const recommendation = topRecommendation(row);
      if (!recommendation) return t('detail.no_aggregate_action');
      const title = translatedField(recommendation.title_key, recommendation.title);
      const why = translatedField(recommendation.why_key, recommendation.why);
      return `${title}: ${why}`;
    }
    function translateEfficiencyFlag(row, flag, index) {
      const keys = Array.isArray(row.efficiency_flag_keys) ? row.efficiency_flag_keys : [];
      return translatedField(keys[index], flag);
    }
    function signalCount(row) {
      return Array.isArray(row.efficiency_flags) ? row.efficiency_flags.length : 0;
    }
    function rowAttentionScore(row) {
      const costScore = clamp(Number(row.estimated_cost_usd || 0) * 24, 0, 60);
      const tokenScore = clamp(Number(row.total_tokens || 0) / 2500, 0, 36);
      const lowCacheScore = Number(row.input_tokens || 0) > 0 ? clamp((0.5 - Number(row.cache_ratio || 0)) * 70, 0, 35) : 0;
      const contextScore = clamp(Number(row.context_window_percent || 0) * 42, 0, 42);
      const pricingScore = row.pricing_model ? (row.pricing_estimated ? 12 : 0) : 30;
      const usageScore = clamp(Number(row.usage_credits || 0) * 2.5, 0, 48);
      return costScore + usageScore + tokenScore + lowCacheScore + contextScore + pricingScore + signalCount(row) * 12;
    }
    function threadAttentionScore(group) {
      const costScore = clamp(Number(group.estimatedCost || 0) * 24, 0, 72);
      const tokenScore = clamp(Number(group.totalTokens || 0) / 3500, 0, 42);
      const lowCacheScore = clamp((0.55 - Number(group.cacheRatio || 0)) * 70, 0, 38);
      const contextScore = clamp(Number(group.maxContextUse || 0) * 45, 0, 45);
      const pricingScore = group.pricingStatusCode === 'no_price' ? 36 : group.pricingStatusCode === 'estimated' || group.pricingStatusCode === 'mixed' ? 18 : 0;
      const usageScore = clamp(Number(group.usageCredits || 0) * 2.4, 0, 72);
      const relationScore = (group.subagentCount || 0) * 4 + (group.autoReviewCount || 0) * 6 + (group.attachedCount || 0) * 3;
      return costScore + usageScore + tokenScore + lowCacheScore + contextScore + pricingScore + relationScore + Number(group.signalCount || 0) * 10;
    }
    function severityForScore(score, hasPricingGap = false) {
      if (score >= 95) return 'high';
      if (score >= 48) return 'medium';
      return hasPricingGap ? 'review' : 'review';
    }
    function callSortValue(row, key) {
      if (key === 'attention') return rowAttentionScore(row);
      if (key === 'cache') return Number(row.cache_ratio || 0);
      if (key === 'context') return Number(row.context_window_percent || 0);
      if (key === 'cost') return Number(row.estimated_cost_usd || 0);
      if (key === 'effort') return textValue(row.effort);
      if (key === 'model') return textValue(row.model);
      if (key === 'cached') return cachedInputTokens(row);
      if (key === 'uncached') return uncachedInputTokens(row);
      if (key === 'output') return outputTokens(row);
      if (key === 'signals') return Array.isArray(row.efficiency_flags) ? row.efficiency_flags.length : 0;
      if (key === 'thread') return textValue(rowThreadLabel(row));
      if (key === 'time') return String(row.event_timestamp || '');
      if (key === 'usage') return Number(row.usage_credits || 0);
      return Number(row.total_tokens || 0);
    }
    function compareCalls(a, b) {
      const primary = directional(compareValues(callSortValue(a, sortKey), callSortValue(b, sortKey)));
      if (primary !== 0) return primary;
      const timeFallback = String(b.event_timestamp || '').localeCompare(String(a.event_timestamp || ''));
      if (timeFallback !== 0) return timeFallback;
      return String(a.record_id || '').localeCompare(String(b.record_id || ''));
    }
    function threadCallSortValue(row, key) {
      if (key === 'cache') return Number(row.cache_ratio || 0);
      if (key === 'cost') return Number(row.estimated_cost_usd || 0);
      if (key === 'effort') return textValue(row.effort);
      if (key === 'model') return textValue(row.model);
      if (key === 'cached') return cachedInputTokens(row);
      if (key === 'uncached') return uncachedInputTokens(row);
      if (key === 'output') return outputTokens(row);
      if (key === 'signals') return signalCount(row);
      if (key === 'source') return textValue(sourceLabelText(row));
      if (key === 'time') return String(row.event_timestamp || '');
      return Number(row.total_tokens || 0);
    }
    function compareThreadCalls(a, b) {
      const comparison = compareValues(
        threadCallSortValue(a, threadCallSortKey),
        threadCallSortValue(b, threadCallSortKey),
      );
      const primary = threadCallSortDirection === 'asc' ? comparison : -comparison;
      if (primary !== 0) return primary;
      const timeFallback = String(b.event_timestamp || '').localeCompare(String(a.event_timestamp || ''));
      if (timeFallback !== 0) return timeFallback;
      return String(a.record_id || '').localeCompare(String(b.record_id || ''));
    }
    function sortedThreadCalls(calls) {
      return calls.slice().sort(compareThreadCalls);
    }
    function handleThreadCallHeaderSort(key) {
      if (threadCallSortKey === key) {
        threadCallSortDirection = threadCallSortDirection === 'asc' ? 'desc' : 'asc';
      } else {
        threadCallSortKey = key;
        threadCallSortDirection = key === 'time' || key === 'total' || key === 'cached' || key === 'uncached' || key === 'output' || key === 'cost' || key === 'cache' || key === 'signals' ? 'desc' : 'asc';
      }
      render();
    }
    function threadCallHeader(key, label, numeric = false) {
      const active = threadCallSortKey === key;
      const indicator = active ? (threadCallSortDirection === 'asc' ? '▲' : '▼') : '';
      const ariaSort = active ? (threadCallSortDirection === 'asc' ? 'ascending' : 'descending') : 'none';
      return `
        <th${numeric ? ' class="num"' : ''} data-thread-call-sort-active="${active ? 'true' : 'false'}" aria-sort="${ariaSort}">
          <button class="sort-header child-sort-header" type="button" data-thread-call-sort-key="${escapeHtml(key)}">
            <span>${escapeHtml(label)}</span>
            <span class="sort-indicator">${escapeHtml(indicator)}</span>
          </button>
        </th>
      `;
    }
    function rowAttachment(row) {
      return threadAttachmentByRecordId.get(row.record_id) || resolveThreadAttachment(row);
    }
    function rowThreadLabel(row) {
      return rowAttachment(row).label;
    }
    function sortThreads(groups) {
      groups.sort(compareThreads);
      return groups;
    }
    function threadSortValue(group, key) {
      if (key === 'attention') return group.attentionScore;
      if (key === 'cache') return group.cacheRatio;
      if (key === 'context') return group.maxContextUse;
      if (key === 'cost') return group.estimatedCost;
      if (key === 'effort') return textValue(group.effortSummary);
      if (key === 'model') return textValue(group.modelSummary);
      if (key === 'cached') return group.cachedTokens;
      if (key === 'uncached') return group.uncachedTokens;
      if (key === 'output') return group.outputTokens;
      if (key === 'signals') return group.signalCount;
      if (key === 'thread') return textValue(group.label);
      if (key === 'time') return String(group.latestActivity || '');
      if (key === 'usage') return group.usageCredits;
      return group.totalTokens;
    }
    function compareThreads(a, b) {
      const primary = directional(compareValues(threadSortValue(a, sortKey), threadSortValue(b, sortKey)));
      if (primary !== 0) return primary;
      const timeFallback = String(b.latestActivity || '').localeCompare(String(a.latestActivity || ''));
      if (timeFallback !== 0) return timeFallback;
      return String(a.label || '').localeCompare(String(b.label || ''));
    }
    function relationshipTime(group) {
      return String(group.relationshipLatestActivity || group.latestActivity || '');
    }
    function compareTopLevelThreads(a, b) {
      if (sortKey === 'time' && sortDirection === 'desc') {
        const relationshipCompare = relationshipTime(b).localeCompare(relationshipTime(a));
        if (relationshipCompare !== 0) return relationshipCompare;
      }
      return compareThreads(a, b);
    }
    function fitModelPills() {
      document.querySelectorAll('.model-pill').forEach(pill => {
        pill.style.fontSize = '';
        const maxSize = 12;
        const minSize = 9;
        let size = maxSize;
        while (size > minSize && pill.scrollWidth > pill.clientWidth) {
          size -= 0.5;
          pill.style.fontSize = `${size}px`;
        }
        setFastTooltip(pill, pill.dataset.fullLabel || pill.textContent || '');
      });
    }
    function compactSummaryText(values, fallbackKey) {
      const unique = [...new Set(values.filter(Boolean))].sort();
      if (!unique.length) return t('state.unknown');
      if (unique.length === 1) return fallbackKey === 'table.more_efforts' ? translateEffort(unique[0]) : unique[0];
      return tf(fallbackKey, {
        model: unique[0],
        effort: fallbackKey === 'table.more_efforts' ? translateEffort(unique[0]) : unique[0],
        count: unique.length - 1
      });
    }
    function threadModelSummaryText(calls) {
      const models = [...new Set(calls.map(row => row.model).filter(Boolean))].sort();
      if (!models.length) return t('state.unknown');
      if (models.length === 1) return models[0];
      const nonReviewModels = models.filter(model => model !== 'codex-auto-review');
      const primary = nonReviewModels.length ? nonReviewModels[0] : models[0];
      return tf('table.more_models', { model: primary, count: models.length - 1 });
    }
    function dominantParentThread(calls, ownLabel) {
      const counts = new Map();
      for (const row of calls) {
        const parent = resolvedParentThreadName(row);
        if (!parent || parent === ownLabel) continue;
        counts.set(parent, (counts.get(parent) || 0) + 1);
      }
      const ranked = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
      return ranked.length ? ranked[0][0] : '';
    }
    function arrangeThreadGroups(groups) {
      const byLabel = new Map(groups.map(group => [group.label, group]));
      for (const group of groups) {
        group.childThreadCount = 0;
        group.childCallCount = 0;
        group.relationshipLatestActivity = group.latestActivity;
        group.parentVisible = Boolean(group.parentThreadLabel && byLabel.has(group.parentThreadLabel));
        group.renderAsChild = false;
      }
      for (const group of groups) {
        if (!group.parentVisible) continue;
        const parent = byLabel.get(group.parentThreadLabel);
        parent.childThreadCount += 1;
        parent.childCallCount += group.callCount;
        if (String(group.latestActivity || '') > String(parent.relationshipLatestActivity || '')) {
          parent.relationshipLatestActivity = group.latestActivity;
        }
      }
      if (sortKey !== 'time' || sortDirection !== 'desc') {
        return sortThreads(groups);
      }
      const childrenByParent = new Map();
      for (const group of groups) {
        if (!group.parentVisible) continue;
        if (!childrenByParent.has(group.parentThreadLabel)) childrenByParent.set(group.parentThreadLabel, []);
        childrenByParent.get(group.parentThreadLabel).push(group);
      }
      const display = [];
      const topLevel = groups.filter(group => !group.parentVisible).sort(compareTopLevelThreads);
      const displayed = new Set();
      function appendGroup(group, renderAsChild = false) {
        if (displayed.has(group.key)) return;
        displayed.add(group.key);
        group.renderAsChild = renderAsChild;
        display.push(group);
        const children = (childrenByParent.get(group.label) || []).sort(compareThreads);
        for (const child of children) appendGroup(child, true);
      }
      for (const group of topLevel) {
        appendGroup(group, false);
      }
      return display;
    }
    function pricingStatusCodeFor(rows) {
      const priced = rows.filter(row => row.pricing_model);
      const estimated = rows.filter(row => row.pricing_estimated);
      if (priced.length === 0) return 'no_price';
      if (estimated.length === rows.length) return 'estimated';
      if (estimated.length > 0 || priced.length < rows.length) return 'mixed';
      return 'configured';
    }
    function pricingStatusFor(rows) {
      return {
        no_price: t('state.no_price'),
        estimated: t('state.estimated'),
        mixed: t('state.mixed'),
        configured: t('state.configured'),
      }[pricingStatusCodeFor(rows)];
    }
    function creditStatusFor(rows) {
      const rated = rows.filter(row => usageCreditValue(row) !== null);
      const estimated = rows.filter(row => row.usage_credit_confidence === 'estimated');
      if (rated.length === 0) return t('credit.no_mapped_rate');
      if (estimated.length === rows.length) return t('credit.estimated_mapping');
      if (estimated.length > 0 || rated.length < rows.length) return t('state.mixed');
      return t('credit.official_match');
    }
    function threadLifecycle(calls) {
      const highCost = threshold('high_cost_usd', 1);
      const highContext = threshold('high_context_percent', 0.6);
      let largestJump = 0;
      let largestJumpRow = null;
      for (let index = 1; index < calls.length; index += 1) {
        const previous = Number(calls[index - 1].cumulative_total_tokens || 0);
        const current = Number(calls[index].cumulative_total_tokens || 0);
        const jump = Math.max(current - previous, Number(calls[index].total_tokens || 0), 0);
        if (jump > largestJump) {
          largestJump = jump;
          largestJumpRow = calls[index];
        }
      }
      const firstExpensiveIndex = calls.findIndex(row => Number(row.estimated_cost_usd || 0) >= highCost || Number(row.context_window_percent || 0) >= highContext);
      const firstExpensiveRow = firstExpensiveIndex >= 0 ? calls[firstExpensiveIndex] : null;
      const first = calls[0] || {};
      const last = calls[calls.length - 1] || {};
      const cacheTrend = Number(last.cache_ratio || 0) - Number(first.cache_ratio || 0);
      const contextTrend = Number(last.context_window_percent || 0) - Number(first.context_window_percent || 0);
      const spikeIndex = largestJumpRow ? calls.indexOf(largestJumpRow) : -1;
      const subagentBeforeSpike = spikeIndex > 0 && calls.slice(0, spikeIndex).some(row => isSubagent(row) || isAutoReview(row));
      const topAction = calls.map(topRecommendation).filter(Boolean)[0];
      let action = topAction
        ? topAction.action
        : t('action.expand_or_select_recommendations');
      if (contextTrend >= 0.15 || Number(last.context_window_percent || 0) >= highContext) {
        action = t('action.review_context_growth');
      } else if (cacheTrend <= -0.25) {
        action = t('action.check_cache_drop');
      } else if (subagentBeforeSpike) {
        action = t('action.compare_subagent_calls');
      }
      return {
        firstExpensiveRow,
        firstExpensiveIndex,
        largestJump,
        largestJumpRow,
        cacheTrend,
        contextTrend,
        subagentBeforeSpike,
        action,
      };
    }
    function groupThreads(rows) {
      const map = new Map();
      for (const row of rows) {
        const attachment = rowAttachment(row);
        const key = attachment.key;
        if (!map.has(key)) {
          map.set(key, { key, label: attachment.label, rows: [] });
        }
        map.get(key).rows.push(row);
      }
      const groups = [...map.values()].map(group => {
        const calls = group.rows.slice().sort(chronological);
        const totalTokens = calls.reduce((sum, row) => sum + Number(row.total_tokens || 0), 0);
        const inputTokens = calls.reduce((sum, row) => sum + Number(row.input_tokens || 0), 0);
        const cachedTokens = calls.reduce((sum, row) => sum + Number(row.cached_input_tokens || 0), 0);
        const uncachedTokens = calls.reduce((sum, row) => sum + uncachedInputTokens(row), 0);
        const outputTokensTotal = calls.reduce((sum, row) => sum + outputTokens(row), 0);
        const estimatedCost = calls.reduce((sum, row) => sum + Number(row.estimated_cost_usd || 0), 0);
        const usageCredits = sumUsageCredits(calls);
        const signalCount = calls.reduce((sum, row) => sum + (Array.isArray(row.efficiency_flags) ? row.efficiency_flags.length : 0), 0);
        const latestActivity = calls.reduce((latest, row) => String(row.event_timestamp || '') > latest ? String(row.event_timestamp || '') : latest, '');
        const maxContextUse = calls.reduce((max, row) => Math.max(max, Number(row.context_window_percent || 0)), 0);
        const subagentCount = calls.filter(isSubagent).length;
        const autoReviewCount = calls.filter(isAutoReview).length;
        const attachedCount = calls.filter(row => rowAttachment(row).relation !== 'direct' && rowAttachment(row).relation !== 'session').length;
        const modelSummary = threadModelSummaryText(calls);
        const effortSummary = compactSummaryText(calls.map(row => row.effort), 'table.more_efforts');
        const effortTooltip = effortTooltipText(calls.map(row => row.effort));
        const parentThreadLabel = dominantParentThread(calls, group.label);
        const lifecycle = threadLifecycle(calls);
        return {
          key: group.key,
          label: group.label,
          calls,
          callCount: calls.length,
          latestActivity,
          parentThreadLabel,
          modelSummary,
          effortSummary,
          effortTooltip,
          totalTokens,
          cachedTokens,
          uncachedTokens,
          outputTokens: outputTokensTotal,
          estimatedCost,
          usageCredits,
          cacheRatio: inputTokens ? cachedTokens / inputTokens : 0,
          maxContextUse,
          pricingStatusCode: pricingStatusCodeFor(calls),
          pricingStatus: pricingStatusFor(calls),
          creditStatus: creditStatusFor(calls),
          signalCount,
          subagentCount,
          autoReviewCount,
          attachedCount,
          lifecycle,
          attentionScore: 0,
        };
      });
      for (const group of groups) {
        group.attentionScore = threadAttentionScore(group);
      }
      return arrangeThreadGroups(groups);
    }
    function visibleSlice(items) {
      const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
      currentPage = Math.min(Math.max(currentPage, 1), pageCount);
      const end = Math.min(currentPage * pageSize, items.length);
      return {
        items: items.slice(0, end),
        start: 0,
        end,
        total: items.length,
        pageCount,
      };
    }
    function updateLoadMoreControl(page, itemLabel = 'table.rows') {
      pagerEl.hidden = !page.total;
      loadMoreRowsEl.hidden = page.end >= page.total;
      if (!page.total) {
        pageStatusEl.textContent = t('state.no_rows');
        return;
      }
      pageStatusEl.textContent = tf('table.visible_status', {
        end: number.format(page.end),
        total: number.format(page.total),
        items: t(itemLabel),
      });
    }
    function buildInsights(rows) {
      const groups = groupThreads(rows);
      const insights = [];
      const topCostGroup = groups.filter(group => group.estimatedCost > 0).sort((a, b) => b.estimatedCost - a.estimatedCost || b.attentionScore - a.attentionScore)[0];
      if (topCostGroup) {
        insights.push({
          title: t('insight.costliest_thread'),
          value: pricingConfigured ? moneyText(topCostGroup.estimatedCost) : t('state.not_configured'),
          body: tf('insight.costliest_thread_body', { thread: topCostGroup.label, calls: number.format(topCostGroup.callCount), tokens: number.format(topCostGroup.totalTokens) }),
          severity: severityForScore(topCostGroup.attentionScore),
          action: t('insight.open_thread_timeline'),
          preset: 'highest-cost',
          target: { threadKey: topCostGroup.key, expandThread: true },
        });
      }
      const lowCacheLimit = threshold('low_cache_ratio', 0.3);
      const lowCacheRows = rows.filter(row => Number(row.input_tokens || 0) > 0 && Number(row.cache_ratio || 0) < lowCacheLimit);
      if (lowCacheRows.length) {
        const lowest = lowCacheRows.slice().sort((a, b) => Number(a.cache_ratio || 0) - Number(b.cache_ratio || 0))[0];
        insights.push({
          title: t('insight.low_cache_reuse'),
          value: pct(lowest.cache_ratio),
          body: tf('insight.low_cache_reuse_body', { calls: number.format(lowCacheRows.length), ratio: pct(lowCacheLimit), thread: rowThreadLabel(lowest) }),
          severity: 'medium',
          action: t('insight.apply_cache_misses'),
          preset: 'cache-misses',
          target: { recordId: lowest.record_id },
        });
      }
      const highContextLimit = threshold('high_context_percent', 0.6);
      const highContextRows = rows.filter(row => Number(row.context_window_percent || 0) >= highContextLimit);
      if (highContextRows.length) {
        const highest = highContextRows.slice().sort((a, b) => Number(b.context_window_percent || 0) - Number(a.context_window_percent || 0))[0];
        insights.push({
          title: t('insight.context_bloat'),
          value: pct(highest.context_window_percent),
          body: tf('insight.context_bloat_body', { calls: number.format(highContextRows.length), ratio: pct(highContextLimit) }),
          severity: severityForScore(rowAttentionScore(highest)),
          action: t('insight.apply_context_bloat'),
          preset: 'context-bloat',
          target: { recordId: highest.record_id },
        });
      }
      const usageCredits = sumUsageCredits(rows);
      if (usageCredits > 0) {
        const creditCoverage = creditCoverageRatio(rows);
        const highestUsageRow = rows.filter(row => usageCreditValue(row) !== null).sort((a, b) => Number(usageCreditValue(b) || 0) - Number(usageCreditValue(a) || 0))[0];
        insights.push({
          title: t('insight.codex_allowance_usage'),
          value: `${credits(usageCredits)} ${t('badge.credits')}`,
          body: allowanceWindowText(usageCredits, 'impact') || allowanceWindowText(usageCredits, 'remaining') || tf('insight.credit_coverage_body', { ratio: pct(creditCoverage) }),
          severity: severityForScore(clamp(usageCredits * 2.4, 0, 140)),
          action: t('insight.review_highest_credit'),
          preset: 'usage-credits',
          target: highestUsageRow ? { recordId: highestUsageRow.record_id } : null,
        });
      }
      const unpricedTokens = rows.reduce((sum, row) => sum + (!row.pricing_model ? Number(row.total_tokens || 0) : 0), 0);
      if (unpricedTokens) {
        const topUnpricedRow = rows.filter(row => !row.pricing_model).sort((a, b) => Number(b.total_tokens || 0) - Number(a.total_tokens || 0))[0];
        insights.push({
          title: t('insight.unpriced_usage'),
          value: number.format(unpricedTokens),
          body: t('insight.unpriced_usage_body'),
          severity: 'review',
          action: t('insight.review_pricing_gaps'),
          preset: 'pricing-gaps',
          target: topUnpricedRow ? { recordId: topUnpricedRow.record_id } : null,
        });
      }
      const estimatedTokens = rows.reduce((sum, row) => sum + (row.pricing_estimated ? Number(row.total_tokens || 0) : 0), 0);
      if (estimatedTokens) {
        const topEstimatedRow = rows.filter(row => row.pricing_estimated).sort((a, b) => Number(b.total_tokens || 0) - Number(a.total_tokens || 0))[0];
        insights.push({
          title: t('insight.estimated_pricing'),
          value: number.format(estimatedTokens),
          body: t('insight.estimated_pricing_body'),
          severity: 'review',
          action: t('insight.review_estimates'),
          preset: 'estimated-review',
          target: topEstimatedRow ? { recordId: topEstimatedRow.record_id } : null,
        });
      }
      const reasoningRows = rows.filter(row => Number(row.reasoning_output_tokens || 0) > 0).sort((a, b) => Number(b.reasoning_output_tokens || 0) - Number(a.reasoning_output_tokens || 0));
      if (reasoningRows[0]) {
        insights.push({
          title: t('insight.reasoning_output_spike'),
          value: number.format(reasoningRows[0].reasoning_output_tokens || 0),
          body: tf('insight.reasoning_spike_body', { thread: rowThreadLabel(reasoningRows[0]) }),
          severity: severityForScore(rowAttentionScore(reasoningRows[0])),
          action: t('insight.inspect_selected_call'),
          view: 'calls',
          sort: 'signals',
          target: { recordId: reasoningRows[0].record_id },
        });
      }
      return insights.slice(0, 6);
    }
    function renderInsightPanel(rows) {
      if (activeView === 'call') {
        insightsPanelEl.hidden = true;
        return;
      }
      if (activeView !== 'insights' && !activePreset) {
        insightsPanelEl.hidden = true;
        return;
      }
      insightsPanelEl.hidden = false;
      renderPresetControls();
      const insights = buildInsights(rows);
      if (!insights.length) {
        insightCardsEl.innerHTML = `<div class="empty-state">${escapeHtml(t('state.no_data'))}</div>`;
        return;
      }
      insightCardsEl.innerHTML = insights.map((insight, index) => {
        const severity = insight.severity || 'review';
        return `
          <article class="insight-card" data-severity="${escapeHtml(severity)}">
            <div class="insight-card-header">
              <h3>${escapeHtml(insight.title)}</h3>
              <span class="severity-chip ${escapeHtml(severity)}">${escapeHtml(severity === 'high' ? t('severity.high') : severity === 'medium' ? t('severity.medium') : t('severity.review'))}</span>
            </div>
            <strong>${escapeHtml(insight.value)}</strong>
            <p>${escapeHtml(insight.body)}</p>
            <button class="insight-action" type="button" data-insight-index="${index}">${escapeHtml(insight.action)}</button>
          </article>
        `;
      }).join('');
      insightCardsEl.querySelectorAll('[data-insight-index]').forEach(button => {
        const insight = insights[Number(button.dataset.insightIndex)];
        button.addEventListener('click', () => {
          if (insight.preset) {
            applyPreset(insight.preset, insight.target);
            return;
          }
          activeView = insight.view || 'calls';
          if (insight.sort) {
            sortKey = insight.sort;
            sortDirection = defaultSortDirection(insight.sort);
            sortEl.value = sortKey;
          }
          resetVisibleRows();
          queueFocusTarget(insight.target);
          render();
        });
      });
    }
    function renderPresetControls() {
      const preset = activePresetDefinition();
      clearPresetEl.hidden = !preset;
      presetStatusEl.textContent = preset
        ? tf('preset.caption', { caption: t(preset.captionKey), description: t(preset.descriptionKey) })
        : t('preset.no_preset');
      presetListEl.innerHTML = presetDefinitions.map(candidate => `
        <button class="preset-card" type="button" data-preset="${escapeHtml(candidate.key)}" aria-pressed="${candidate.key === activePreset ? 'true' : 'false'}">
          <span class="preset-copy"><b>${escapeHtml(t(candidate.labelKey))}</b><span>${escapeHtml(t(candidate.descriptionKey))}</span></span>
          <span class="preset-chip">${escapeHtml(t('action.run'))}</span>
        </button>
      `).join('');
      presetListEl.querySelectorAll('[data-preset]').forEach(button => {
        button.addEventListener('click', () => applyPreset(button.dataset.preset));
      });
    }
    function render() {
      const dateRange = updateDateFilterControls();
      const rows = filtered(dateRange);
      rowsEl.textContent = '';
      document.body.dataset.activeView = activeView;
      updateSortControls();
      const totalTokens = rows.reduce((sum, row) => sum + Number(row.total_tokens || 0), 0);
      const cachedInputTokens = rows.reduce((sum, row) => sum + Number(row.cached_input_tokens || 0), 0);
      const uncachedInputTokens = rows.reduce((sum, row) => sum + Number(row.uncached_input_tokens || 0), 0);
      const reasoningOutputTokens = rows.reduce((sum, row) => sum + Number(row.reasoning_output_tokens || 0), 0);
      document.getElementById('visibleCalls').textContent = number.format(rows.length);
      document.getElementById('totalTokens').textContent = number.format(totalTokens);
      document.getElementById('cachedTokens').textContent = number.format(cachedInputTokens);
      document.getElementById('uncachedTokens').textContent = number.format(uncachedInputTokens);
      document.getElementById('reasoningTokens').textContent = number.format(reasoningOutputTokens);
      const estimatedCost = rows.reduce((sum, row) => sum + Number(row.estimated_cost_usd || 0), 0);
      const usageCredits = sumUsageCredits(rows);
      document.getElementById('estimatedCost').textContent = pricingConfigured ? moneyText(estimatedCost) : t('state.not_configured');
      document.getElementById('usageCredits').textContent = credits(usageCredits);
      document.getElementById('allowanceImpact').textContent = allowanceImpactText(usageCredits);
      setFastTooltip(document.getElementById('allowanceImpact'), allowanceWindowText(usageCredits, 'remaining') || t('allowance.title_hint'));
      insightsViewEl.setAttribute('aria-pressed', activeView === 'insights' ? 'true' : 'false');
      callsViewEl.setAttribute('aria-pressed', activeView === 'calls' ? 'true' : 'false');
      threadsViewEl.setAttribute('aria-pressed', activeView === 'threads' ? 'true' : 'false');
      renderInsightPanel(rows);
      if (activeView === 'call') {
        renderCallInvestigator(rows);
      } else if (activeView === 'threads') {
        renderThreads(rows);
      } else if (activeView === 'insights') {
        renderThreads(rows, 'insights');
      } else {
        renderCalls(rows);
      }
      fitModelPills();
      syncUrlState();
      scheduleFocusPendingTarget();
    }
    function callMetricCard(label, value, badge = '') {
      return `
        <div class="call-metric-card">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
          ${badge ? `<small>${escapeHtml(badge)}</small>` : ''}
        </div>
      `;
    }
    function callDiagnosticPucks(row, previous) {
      const primary = cacheDiagnostic(row, previous);
      const pucks = [`<span class="flag signal-puck diagnostic-${escapeHtml(primary.key)}">${escapeHtml(primary.label)}</span>`];
      if (previous && uncachedInputTokens(row) > Math.max(uncachedInputTokens(previous) * 2, 1000) && primary.key !== 'spike') {
        pucks.push(`<span class="flag signal-puck diagnostic-spike">${escapeHtml(t('call.cache_spike'))}</span>`);
      }
      if (Number(row.context_window_percent || 0) >= threshold('high_context_percent', 0.6)) {
        pucks.push(`<span class="flag signal-puck">${escapeHtml(t('flag.high_context_use'))}</span>`);
      }
      return pucks.join('');
    }
    function renderDeltaCards(row, previous) {
      if (!previous) {
        return `<p class="muted">${escapeHtml(t('call.no_previous'))}</p>`;
      }
      return `
        <div class="call-delta-grid">
          ${callDeltaRows(row, previous).map(([label, value]) => callMetricCard(label, value, t('call.derived_label'))).join('')}
        </div>
      `;
    }
    function renderCallNavigation(row, previous, next) {
      const backUrl = tableUrlForRow(row);
      return `
        <div class="call-nav">
          <a class="toolbar-button" href="${escapeHtml(backUrl)}">${escapeHtml(t('button.back_to_dashboard'))}</a>
          <button class="toolbar-button" type="button" data-call-nav-record="${escapeHtml(previous?.record_id || '')}" ${previous ? '' : 'disabled'}>${escapeHtml(t('button.previous_call'))}</button>
          <button class="toolbar-button" type="button" data-call-nav-record="${escapeHtml(next?.record_id || '')}" ${next ? '' : 'disabled'}>${escapeHtml(t('button.next_call'))}</button>
          <button class="toolbar-button" type="button" data-copy-call-link="${escapeHtml(row.record_id || '')}">${escapeHtml(t('button.copy_link'))}</button>
        </div>
      `;
    }
    function renderCallInvestigator(rows) {
      const row = rowByRecordId.get(selectedRecordId) || rows.find(candidate => candidate.record_id === selectedRecordId);
      updateLoadMoreControl({ total: 0, end: 0 }, 'table.calls');
      pagerEl.hidden = true;
      tableTitleEl.textContent = t('dashboard.view.call');
      tableCaptionEl.textContent = selectedRecordId
        ? tf('caption.call_investigator', { record: short(selectedRecordId, '').slice(0, 12) })
        : t('call.open_hint');
      if (!row) {
        rowsEl.innerHTML = `<tr><td class="empty-state" colspan="11">${escapeHtml(t('call.not_found'))}</td></tr>`;
        detailEl.textContent = t('dashboard.detail.empty');
        return;
      }
      selectedRecordId = row.record_id || selectedRecordId;
      const { calls, index, previous, next } = adjacentCalls(row);
      const diagnostic = cacheDiagnostic(row, previous);
      const threadLabel = rowThreadLabel(row);
      const callPosition = index >= 0 ? `${number.format(index + 1)} / ${number.format(calls.length)}` : t('state.unknown');
      rowsEl.innerHTML = `
        <tr class="call-investigator-row">
          <td colspan="11">
            <article class="call-investigator" data-record-id="${escapeHtml(row.record_id || '')}">
              <header class="call-investigator-header">
                <div>
                  <p class="eyebrow">${escapeHtml(t('dashboard.view.call'))}</p>
                  <h3>${escapeHtml(threadLabel)}</h3>
                  <p class="muted">${escapeHtml(formatTimestamp(row.event_timestamp))} · ${escapeHtml(short(row.model))} · ${escapeHtml(translateEffort(short(row.effort)))}</p>
                </div>
                ${renderCallNavigation(row, previous, next)}
              </header>
              <section class="call-diagnostic-section">
                <div class="section-heading compact">
                  <h3>${escapeHtml(t('call.exact_accounting'))}</h3>
                  <span class="evidence-chip exact">${escapeHtml(t('call.exact_label'))}</span>
                </div>
                <div class="call-metric-grid">
                  ${callMetricCard(t('metric.last_call_input'), number.format(rowInputTokens(row)), t('metric.last_call_total'))}
                  ${callMetricCard(t('metric.cached_input'), number.format(cachedInputTokens(row)), pct(row.cache_ratio))}
                  ${callMetricCard(t('metric.uncached_input'), number.format(uncachedInputTokens(row)), t('call.exact_label'))}
                  ${callMetricCard(t('metric.output'), number.format(outputTokens(row)), t('metric.reasoning_output'))}
                  ${callMetricCard(t('metric.estimated_cost'), moneyText(row.estimated_cost_usd), pricingStatusText(row))}
                  ${callMetricCard(t('metric.codex_credits'), usageCreditsWithStatus(row), rowAllowanceImpact(row))}
                </div>
              </section>
              <section class="call-diagnostic-section">
                <div class="section-heading compact">
                  <h3>${escapeHtml(t('call.cache_diagnostics'))}</h3>
                  <span class="evidence-chip derived">${escapeHtml(t('call.derived_label'))}</span>
                </div>
                <div class="diagnostic-summary">
                  <div class="flags">${callDiagnosticPucks(row, previous)}</div>
                  <p>${escapeHtml(diagnostic.body)}</p>
                  <p class="muted">${escapeHtml(tf('call.position', { position: callPosition }))}</p>
                </div>
              </section>
              <section class="call-diagnostic-section">
                <div class="section-heading compact">
                  <h3>${escapeHtml(t('call.cache_accounting_delta'))}</h3>
                  <span class="evidence-chip derived">${escapeHtml(t('call.derived_label'))}</span>
                </div>
                ${renderDeltaCards(row, previous)}
              </section>
              <section class="call-diagnostic-section">
                <div class="section-heading compact">
                  <h3>${escapeHtml(t('call.context_estimate'))}</h3>
                  <span class="evidence-chip estimated">${escapeHtml(t('call.estimated_label'))}</span>
                </div>
                <div class="call-metric-grid two">
                  ${callMetricCard(t('metric.uncached_input'), number.format(uncachedInputTokens(row)), t('call.exact_label'))}
                  ${callMetricCard(t('call.hidden_estimate'), t('state.requires_evidence'), t('call.evidence_label'))}
                </div>
                <p class="muted">${escapeHtml(t('call.context_estimate_hint'))}</p>
              </section>
              <section class="call-diagnostic-section">
                <div class="section-heading compact">
                  <h3>${escapeHtml(t('call.compaction_diagnostics'))}</h3>
                  <span class="evidence-chip evidence">${escapeHtml(t('call.evidence_label'))}</span>
                </div>
                <p class="muted">${escapeHtml(t('call.compaction_hint'))}</p>
              </section>
              <section class="call-diagnostic-section raw-evidence">
                <div class="section-heading compact">
                  <h3>${escapeHtml(t('call.raw_evidence'))}</h3>
                  <span class="evidence-chip evidence">${escapeHtml(t('call.evidence_label'))}</span>
                </div>
                ${contextControls(row)}
              </section>
            </article>
          </td>
        </tr>
      `;
      const article = rowsEl.querySelector('.call-investigator');
      if (article) bindContextButtons(row, article);
      showDetail(row);
    }
    function renderCalls(rows) {
      ensurePendingFocusVisibleInRows(rows);
      const page = visibleSlice(rows);
      updateLoadMoreControl(page, 'table.calls');
      tableTitleEl.textContent = t('dashboard.model_calls');
      const preset = activePresetDefinition();
      const prefix = preset ? `${t(preset.captionKey)}. ` : '';
      tableCaptionEl.textContent = `${prefix}${dateCaptionPrefix()}${tf('caption.calls', { sort: tableCaptionEl.dataset.sortDescription, loaded: loadedRowsDescription() })}`;
      for (const row of page.items) {
        const tr = document.createElement('tr');
        const flags = Array.isArray(row.efficiency_flags) ? row.efficiency_flags : [];
        tr.className = `call-row${selectedRecordId === row.record_id ? ' selected-row' : ''}`;
        tr.dataset.recordId = row.record_id || '';
        tr.tabIndex = 0;
        tr.setAttribute('role', 'button');
        tr.setAttribute('aria-label', tf('aria.inspect_thread', { thread: rowThreadLabel(row) }));
        tr.innerHTML = `
          <td>${renderTimeCell(row.event_timestamp)}</td>
          <td title="${escapeHtml(short(row.session_id))}">
            <div class="call-thread-cell">
              <span>${escapeHtml(truncate(rowThreadLabel(row)))}</span>
              <button class="mini-open-button" type="button" data-open-investigator-record="${escapeHtml(row.record_id || '')}">${escapeHtml(t('button.open_investigator'))}</button>
            </div>
          </td>
          <td><span class="pill model-pill" data-full-label="${escapeHtml(short(row.model))}">${escapeHtml(short(row.model))}</span></td>
          <td>${effortCell(translateEffort(short(row.effort)), translateEffort(short(row.effort)))}</td>
          <td class="num token-cell">${totalTokenCell(row)}</td>
          <td class="num token-cell">${cachedTokenCell(row)}</td>
          <td class="num token-cell">${uncachedTokenCell(row)}</td>
          <td class="num token-cell">${outputTokenCell(row)}</td>
          <td class="num">${costUsageCell(row.pricing_estimated ? `${moneyText(row.estimated_cost_usd)}*` : moneyText(row.estimated_cost_usd), usageCreditValue(row))}</td>
          <td class="num">${pct(row.cache_ratio)}</td>
          <td><div class="flags">${renderSignalPucks(row, flags, 3)}</div></td>
        `;
        tr.addEventListener('mouseenter', () => showDetail(row));
        tr.addEventListener('click', event => {
          if (event.target.closest('[data-open-investigator-record]')) return;
          selectRow(row);
        });
        tr.addEventListener('dblclick', () => openInvestigator(row));
        tr.addEventListener('keydown', event => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            selectRow(row);
          }
        });
        rowsEl.appendChild(tr);
      }
      if (!initialDetailApplied && selectedRecordId) {
        const selected = rows.find(row => row.record_id === selectedRecordId);
        if (selected) {
          initialDetailApplied = true;
          showDetail(selected);
        }
      }
      if (!initialDetailApplied && urlParams.get('detail') === 'first' && page.items[0]) {
        initialDetailApplied = true;
        showDetail(page.items[0]);
      }
      if (!rows.length) {
        rowsEl.innerHTML = `<tr><td class="empty-state" colspan="11">${escapeHtml(t('state.no_calls'))}</td></tr>`;
      }
    }
    function renderThreads(rows, mode = 'threads') {
      const groups = groupThreads(rows);
      ensurePendingFocusVisibleInGroups(groups);
      if (!initialThreadExpansionApplied && (activeView === 'threads' || activeView === 'insights')) {
        const expansion = urlParams.get('expand');
        if (expansion === 'all') {
          groups.forEach(group => expandedThreads.add(group.key));
        } else if (expansion === 'first' && groups[0]) {
          expandedThreads.add(groups[0].key);
        }
        initialThreadExpansionApplied = true;
      }
      const page = visibleSlice(groups);
      updateLoadMoreControl(page, 'table.threads');
      tableTitleEl.textContent = mode === 'insights' ? t('dashboard.top_threads_by_attention') : t('dashboard.view.threads');
      const preset = activePresetDefinition();
      const prefix = preset ? `${t(preset.captionKey)}. ` : '';
      tableCaptionEl.textContent = `${prefix}${dateCaptionPrefix()}${tf('caption.threads', { threads: number.format(groups.length), calls: number.format(rows.length), sort: tableCaptionEl.dataset.sortDescription, loaded: loadedRowsDescription() })}`;
      for (const group of page.items) {
        const tr = document.createElement('tr');
        const expanded = expandedThreads.has(group.key);
        const threadNotes = [
          `${number.format(group.callCount)} ${t('table.calls')}`,
          group.pricingStatus,
          group.parentThreadLabel ? tf('thread.spawned_from', { thread: group.parentThreadLabel }) : '',
          group.childThreadCount ? tf('thread.spawned_threads', { count: number.format(group.childThreadCount) }) : '',
          group.subagentCount ? tf('thread.subagent', { count: number.format(group.subagentCount) }) : '',
          group.autoReviewCount ? tf('thread.auto_review', { count: number.format(group.autoReviewCount) }) : '',
          group.attachedCount ? t('thread.attached') : '',
        ].filter(Boolean).join(' - ');
        tr.className = `thread-row${group.parentThreadLabel ? ' spawned-thread' : ''}${selectedThreadKey === group.key ? ' selected-row' : ''}`;
        tr.dataset.threadKey = group.key;
        tr.tabIndex = 0;
        tr.setAttribute('role', 'button');
        tr.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        tr.setAttribute('aria-label', tf('thread.expand_label', { action: expanded ? t('thread.collapse') : t('thread.expand'), thread: group.label, score: Math.round(group.attentionScore) }));
        tr.innerHTML = `
          <td>${renderTimeCell(group.latestActivity)}</td>
          <td>
            <div class="thread-title">
                <span class="thread-toggle" aria-hidden="true">${expanded ? '-' : '+'}</span>
              <span class="thread-meta">
                <span class="thread-name">${group.renderAsChild ? `<span class="thread-relation">${escapeHtml(t('thread.spawned'))}</span> ` : ''}${escapeHtml(truncate(group.label, 72))}</span>
                <span class="thread-subtle">${escapeHtml(threadNotes)} · ${escapeHtml(tf('thread.attention', { score: number.format(Math.round(group.attentionScore)) }))}</span>
              </span>
            </div>
          </td>
          <td><span class="pill model-pill" data-full-label="${escapeHtml(short(group.modelSummary))}">${escapeHtml(short(group.modelSummary))}</span></td>
          <td>${effortCell(truncate(group.effortSummary, 28), group.effortTooltip)}</td>
          <td class="num token-cell">${tokenNumberCell(group.totalTokens, t('metric.total_tokens'))}</td>
          <td class="num token-cell">${tokenNumberCell(group.cachedTokens, t('metric.cached_input'))}</td>
          <td class="num token-cell">${tokenNumberCell(group.uncachedTokens, t('metric.uncached_input'))}</td>
          <td class="num token-cell">${tokenNumberCell(group.outputTokens, t('metric.output_tokens'))}</td>
          <td class="num">${costUsageCell(pricingConfigured ? moneyText(group.estimatedCost) : t('state.not_configured'), group.usageCredits)}</td>
          <td class="num">${pct(group.cacheRatio)}</td>
          <td class="num">${number.format(group.signalCount)}</td>
        `;
        tr.addEventListener('click', () => {
          if (expandedThreads.has(group.key)) {
            expandedThreads.delete(group.key);
          } else {
            expandedThreads.add(group.key);
          }
          selectThread(group);
          render();
        });
        tr.addEventListener('keydown', event => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            tr.click();
          }
        });
        tr.addEventListener('mouseenter', () => showThreadDetail(group));
        rowsEl.appendChild(tr);
        if (expanded) {
          rowsEl.appendChild(renderThreadCalls(group));
        }
      }
      if (!groups.length) {
        rowsEl.innerHTML = `<tr><td class="empty-state" colspan="11">${escapeHtml(t('state.no_threads'))}</td></tr>`;
      }
      if (!initialDetailApplied && selectedThreadKey) {
        const selected = groups.find(group => group.key === selectedThreadKey);
        if (selected) {
          initialDetailApplied = true;
          showThreadDetail(selected);
        }
      }
      if (!initialDetailApplied && urlParams.get('detail') === 'first' && page.items[0]) {
        initialDetailApplied = true;
        showThreadDetail(page.items[0]);
      }
    }
    function renderThreadCalls(group) {
      const tr = document.createElement('tr');
      tr.className = 'thread-child-row';
      const sortedCalls = sortedThreadCalls(group.calls);
      const visiblePages = Math.max(1, threadCallVisiblePages.get(group.key) || 1);
      const visibleCount = Math.min(sortedCalls.length, visiblePages * threadCallPageSize);
      const calls = sortedCalls.slice(0, visibleCount).map(row => {
        const flags = Array.isArray(row.efficiency_flags) ? row.efficiency_flags : [];
        return `
          <tr class="thread-call-row${selectedRecordId === row.record_id ? ' selected-row' : ''}" tabindex="0" role="button" data-record-id="${escapeHtml(row.record_id || '')}">
            <td>${renderTimeCell(row.event_timestamp)}</td>
            <td><span class="pill model-pill" data-full-label="${escapeHtml(short(row.model))}">${escapeHtml(short(row.model))}</span></td>
            <td>${effortCell(translateEffort(short(row.effort)), translateEffort(short(row.effort)))}</td>
            <td>
              <div class="call-thread-cell">
                <span>${escapeHtml(sourceLabelText(row))}</span>
                <button class="mini-open-button" type="button" data-open-investigator-record="${escapeHtml(row.record_id || '')}">${escapeHtml(t('button.open_investigator'))}</button>
              </div>
            </td>
            <td class="num token-cell">${totalTokenCell(row)}</td>
            <td class="num token-cell">${cachedTokenCell(row)}</td>
            <td class="num token-cell">${uncachedTokenCell(row)}</td>
            <td class="num token-cell">${outputTokenCell(row)}</td>
            <td class="num">${costUsageCell(row.pricing_estimated ? `${moneyText(row.estimated_cost_usd)}*` : moneyText(row.estimated_cost_usd), usageCreditValue(row))}</td>
            <td class="num">${pct(row.cache_ratio)}</td>
            <td><div class="flags compact-flags">${renderSignalPucks(row, flags, 3, t('state.none'))}</div></td>
          </tr>
        `;
      }).join('');
      const canLoadMore = visibleCount < sortedCalls.length;
      const childLoadMore = canLoadMore
        ? `
          <div class="child-load-more">
            <span>${escapeHtml(tf('table.visible_status', { end: number.format(visibleCount), total: number.format(sortedCalls.length), items: t('table.calls') }))}</span>
            <button class="pager-button" type="button" data-thread-load-more="${escapeHtml(group.key)}">${escapeHtml(t('button.load_more'))}</button>
          </div>
        `
        : sortedCalls.length
          ? `<div class="child-load-more"><span>${escapeHtml(tf('table.visible_status', { end: number.format(visibleCount), total: number.format(sortedCalls.length), items: t('table.calls') }))}</span></div>`
          : '';
      tr.innerHTML = `
        <td class="child-cell" colspan="11">
          <table class="thread-call-table" aria-label="${escapeHtml(`${group.label} ${t('table.calls')}`)}">
            <thead><tr>
              ${threadCallHeader('time', t('table.time'))}
              ${threadCallHeader('model', t('table.model'))}
              ${threadCallHeader('effort', t('table.effort'))}
              ${threadCallHeader('source', t('table.source'))}
              ${threadCallHeader('total', t('table.tokens'), true)}
              ${threadCallHeader('cached', t('table.cached'), true)}
              ${threadCallHeader('uncached', t('table.uncached'), true)}
              ${threadCallHeader('output', t('table.output'), true)}
              ${threadCallHeader('cost', t('table.cost'), true)}
              ${threadCallHeader('cache', t('table.cache'), true)}
              ${threadCallHeader('signals', t('table.signals'))}
            </tr></thead>
            <tbody>${calls}</tbody>
          </table>
          ${childLoadMore}
        </td>
      `;
      return tr;
    }
    function contextControls(row) {
      const fileMode = window.location.protocol === 'file:';
      const apiMissing = !apiToken;
      const apiDisabled = !contextApiEnabled;
      const disabled = fileMode || apiMissing || apiDisabled ? ' disabled' : '';
      const hint = fileMode
        ? t('context.file_hint')
        : apiMissing
          ? t('context.token_required')
          : apiDisabled
            ? t('context.disabled_hint')
          : t('context.ready_hint');
      const enableButton = !fileMode && !apiMissing && apiDisabled
        ? `<button class="context-button" type="button" data-context-enable>${escapeHtml(t('button.enable_context_loading'))}</button>`
        : '';
      return `
        <div class="context-actions">
          <button class="context-button" type="button" data-context-load${disabled}>${escapeHtml(t('button.show_turn_evidence'))}</button>
          <button class="context-button secondary" type="button" data-context-load-output${disabled}>${escapeHtml(t('button.include_tool_output'))}</button>
          ${enableButton}
        </div>
        <div id="contextResult" class="context-result"><p class="context-note">${escapeHtml(hint)}</p></div>
      `;
    }
    function bindContextButtons(row, root = detailEl) {
      const loadButton = root.querySelector('[data-context-load]');
      const outputButton = root.querySelector('[data-context-load-output]');
      const enableButton = root.querySelector('[data-context-enable]');
      const contextResult = root.querySelector('#contextResult');
      if (loadButton) loadButton.addEventListener('click', () => loadContext(row, { includeToolOutput: false, maxChars: null, maxEntries: defaultContextEntries }, contextResult));
      if (outputButton) outputButton.addEventListener('click', () => loadContext(row, { includeToolOutput: true, maxChars: null, maxEntries: defaultContextEntries }, contextResult));
      if (enableButton) enableButton.addEventListener('click', () => enableContextApi(row));
      if (contextResult) {
        contextResult.addEventListener('click', event => {
          if (!(event.target instanceof Element)) return;
          const button = event.target.closest('[data-context-entry-load-output], [data-context-load-older], [data-context-no-budget], [data-context-compaction-history]');
          if (!button) return;
          if (button.matches('[data-context-entry-load-output]')) {
            loadContext(row, { includeToolOutput: true }, contextResult);
            return;
          }
          if (button.matches('[data-context-load-older]')) {
            loadContext(row, { maxEntries: Number(button.dataset.contextMaxEntries || 0) }, contextResult);
            return;
          }
          if (button.matches('[data-context-no-budget]')) {
            loadContext(row, { maxChars: 0 }, contextResult);
            return;
          }
          if (button.matches('[data-context-compaction-history]')) {
            loadContext(row, { includeCompactionHistory: true }, contextResult);
          }
        });
      }
    }
    async function enableContextApi(row) {
      const target = document.getElementById('contextResult');
      if (!target) return;
      target.innerHTML = `<p class="context-note">${escapeHtml(t('context.loading'))}</p>`;
      try {
        const params = new URLSearchParams({ enabled: '1', _: String(Date.now()) });
        const response = await fetch(`/api/context-settings?${params.toString()}`, {
          headers: {
            'Accept': 'application/json',
            'X-Codex-Usage-Token': apiToken,
          },
          cache: 'no-store',
        });
        if (!response.ok) {
          throw new Error(tf('context.settings_http', { status: response.status }));
        }
        const payload = await response.json();
        if (payload.error) throw new Error(payload.error);
        contextApiEnabled = Boolean(payload.context_api_enabled);
        showDetail(row);
        const nextTarget = document.getElementById('contextResult');
        if (nextTarget && contextApiEnabled) {
          nextTarget.innerHTML = `<p class="context-note">${escapeHtml(t('context.enabled_note'))}</p>`;
        }
      } catch (error) {
        target.innerHTML = `<p class="context-note">${escapeHtml(error.message || String(error))}</p>`;
      }
    }
    function contextStateForRow(row) {
      const key = row.record_id || '';
      return key && contextRequestState.has(key)
        ? contextRequestState.get(key)
        : { includeToolOutput: false, includeCompactionHistory: false, maxChars: null, maxEntries: defaultContextEntries };
    }
    function nextContextState(row, options) {
      const base = contextStateForRow(row);
      const updates = typeof options === 'boolean' ? { includeToolOutput: options } : (options || {});
      const next = { ...base, ...updates };
      next.includeToolOutput = Boolean(next.includeToolOutput);
      next.includeCompactionHistory = Boolean(next.includeCompactionHistory);
      if (next.maxEntries === undefined) next.maxEntries = defaultContextEntries;
      if (next.maxChars === undefined) next.maxChars = null;
      if (row.record_id) contextRequestState.set(row.record_id, next);
      return next;
    }
    async function loadContext(row, options = {}, targetElement = null) {
      const target = targetElement || document.getElementById('contextResult');
      if (!target) return;
      if (!row.record_id) {
        target.innerHTML = `<p class="context-note">${escapeHtml(t('context.no_record_id'))}</p>`;
        return;
      }
      target.innerHTML = `<p class="context-note">${escapeHtml(t('context.loading'))}</p>`;
      const requestState = nextContextState(row, options);
      const params = new URLSearchParams({ record_id: row.record_id });
      if (requestState.includeToolOutput) params.set('include_tool_output', '1');
      if (requestState.includeCompactionHistory) params.set('include_compaction_history', '1');
      if (requestState.maxChars !== null && requestState.maxChars !== undefined) {
        params.set('max_chars', String(requestState.maxChars));
      }
      if (requestState.maxEntries !== null && requestState.maxEntries !== undefined) {
        params.set('max_entries', String(requestState.maxEntries));
      }
      try {
        const response = await fetch(`/api/context?${params.toString()}`, {
          headers: {
            'Accept': 'application/json',
            'X-Codex-Usage-Token': apiToken,
          },
          cache: 'no-store',
        });
        if (!response.ok) {
          const errorText = response.status === 404
            ? t('context.api_unavailable')
            : tf('context.api_http', { status: response.status });
          throw new Error(errorText);
        }
        const payload = await response.json();
        target.innerHTML = renderContext(payload);
      } catch (error) {
        target.innerHTML = `<p class="context-note">${escapeHtml(error.message || String(error))}</p>`;
      }
    }
    function contextLimitActions(payload) {
      const omitted = payload.omitted || {};
      const buttons = [];
      const maxEntries = Number(omitted.max_entries || defaultContextEntries);
      if (Number(omitted.older_entries || 0) > 0) {
        const nextEntries = maxEntries > 0 ? Math.max(maxEntries + defaultContextEntries, maxEntries * 2) : 0;
        buttons.push(`<button class="context-entry-action" type="button" data-context-load-older data-context-max-entries="${escapeHtml(String(nextEntries))}">${escapeHtml(t('button.load_older_context'))}</button>`);
      }
      if (Number(omitted.over_budget_chars || 0) > 0 && Number(omitted.max_chars || 0) !== 0) {
        buttons.push(`<button class="context-entry-action" type="button" data-context-no-budget>${escapeHtml(t('button.no_char_limit'))}</button>`);
      }
      return buttons.length ? `<div class="context-followup-actions">${buttons.join('')}</div>` : '';
    }
    function tokenUsageNumber(value) {
      const numeric = Number(value || 0);
      return Number.isFinite(numeric) ? number.format(numeric) : '0';
    }
    function tokenUsageRows(usage) {
      if (!usage || typeof usage !== 'object') return '';
      const input = Number(usage.input_tokens || 0);
      const cached = Number(usage.cached_input_tokens || 0);
      const uncached = Number(usage.uncached_input_tokens ?? Math.max(input - cached, 0));
      return `
        <td>${escapeHtml(tokenUsageNumber(input))}</td>
        <td>${escapeHtml(tokenUsageNumber(cached))}</td>
        <td>${escapeHtml(tokenUsageNumber(uncached))}</td>
        <td>${escapeHtml(tokenUsageNumber(usage.output_tokens))}</td>
        <td>${escapeHtml(tokenUsageNumber(usage.reasoning_output_tokens))}</td>
        <td>${escapeHtml(tokenUsageNumber(usage.total_tokens))}</td>
      `;
    }
    function tokenUsageScopeLabel(entry, payload, index) {
      const sourceLine = Number(payload?.source?.line_number || 0);
      if (sourceLine && Number(entry.line_number || 0) === sourceLine) return t('context.token_scope_selected');
      if (index === 0) return t('context.token_scope_previous');
      return t('context.token_scope_earlier');
    }
    function renderContextTokenUsage(entry, payload, index) {
      const usage = entry.token_usage || {};
      const rows = [
        [tokenUsageScopeLabel(entry, payload, index), usage.last_token_usage],
        [t('context.token_scope_session'), usage.total_token_usage],
      ].filter(([, value]) => value && typeof value === 'object');
      if (!rows.length) return '';
      return `
        <div class="context-token-breakdown" aria-label="${escapeHtml(t('context.token_breakdown'))}">
          <table>
            <thead>
              <tr>
                <th>${escapeHtml(t('context.token_type'))}</th>
                <th>${escapeHtml(t('context.token_input'))}</th>
                <th>${escapeHtml(t('context.token_cached'))}</th>
                <th>${escapeHtml(t('context.token_uncached'))}</th>
                <th>${escapeHtml(t('context.token_output'))}</th>
                <th>${escapeHtml(t('context.token_reasoning'))}</th>
                <th>${escapeHtml(t('context.token_total'))}</th>
              </tr>
            </thead>
            <tbody>
              ${rows.map(([label, usageValue]) => `<tr><th>${escapeHtml(label)}</th>${tokenUsageRows(usageValue)}</tr>`).join('')}
            </tbody>
          </table>
        </div>
      `;
    }
    function renderContextCompaction(entry, payload) {
      const compaction = entry.compaction || {};
      if (!compaction.replacement_history_available) return '';
      const replacementEntries = Array.isArray(compaction.replacement_history) ? compaction.replacement_history : [];
      const history = replacementEntries.length
        ? `
          <div class="context-replacement-history">
            <h4>${escapeHtml(t('context.compaction_replacement'))}</h4>
            ${replacementEntries.map(item => `
              <div class="context-replacement-entry">
                <strong>${escapeHtml(item.label || 'replacement item')}</strong>
                <pre>${escapeHtml(item.text || '')}</pre>
              </div>
            `).join('')}
          </div>
        `
        : `<button class="context-entry-action" type="button" data-context-compaction-history>${escapeHtml(t('button.show_compaction_history'))}</button>`;
      return `
        <div class="context-compaction">
          <strong>${escapeHtml(t('context.compaction_detected'))}</strong>
          <span>${escapeHtml(tf('context.compaction_replacement_count', { count: number.format(compaction.replacement_entry_count || 0) }))}</span>
          ${history}
        </div>
      `;
    }
    function renderContext(payload) {
      const entries = Array.isArray(payload.entries) ? payload.entries : [];
      const source = payload.source || {};
      const omitted = payload.omitted || {};
      const note = [
        t('context.local_redacted'),
        payload.include_tool_output ? t('context.tool_included') : t('context.tool_omitted'),
        source.file ? tf('context.source', { file: source.file, line: source.line_number || '' }) : '',
        omitted.older_entries ? tf('context.older_omitted', { count: number.format(omitted.older_entries) }) : '',
        omitted.over_budget_chars ? tf('context.chars_omitted', { count: number.format(omitted.over_budget_chars) }) : '',
        Number(omitted.max_chars || 0) === 0 ? t('context.no_char_limit_active') : '',
      ].filter(Boolean).join(' ');
      const tokenEntryIndexes = new Map();
      entries.filter(entry => entry && entry.token_usage).forEach((entry, index) => {
        tokenEntryIndexes.set(entry, index);
      });
      const body = entries.map(entry => {
        const meta = [formatTimestamp(entry.timestamp, ''), entry.line_number ? tf('context.line', { line: entry.line_number }) : ''].filter(Boolean).join(' - ');
        const outputAction = entry.tool_output_omitted && !payload.include_tool_output
          ? `<button class="context-entry-action" type="button" data-context-entry-load-output>${escapeHtml(t('button.show_tool_output'))}</button>`
          : '';
        const tokenUsage = renderContextTokenUsage(entry, payload, tokenEntryIndexes.get(entry) || 0);
        const compaction = renderContextCompaction(entry, payload);
        return `
          <div class="context-entry">
            <div class="context-entry-header">
              <span class="context-entry-title">${escapeHtml(entry.label || entry.type || 'entry')}</span>
              <span class="context-entry-meta">
                ${meta ? `<span>${escapeHtml(meta)}</span>` : ''}
                ${outputAction}
              </span>
            </div>
            ${tokenUsage}
            ${compaction}
            <pre>${escapeHtml(entry.text || '')}</pre>
          </div>
        `;
      }).join('');
      return `<p class="context-note">${escapeHtml(note)}</p>${contextLimitActions(payload)}${body || `<p class="context-note">${escapeHtml(t('state.no_context_entries'))}</p>`}`;
    }
    function pricingStatusText(row) {
      if (!row.pricing_model) return t('state.no_configured_price');
      return row.pricing_estimated ? t('state.best_guess_estimate') : t('state.configured_price');
    }
    function nextActionForRow(row) {
      if (row.recommended_action || row.recommended_action_key) {
        return translatedField(row.recommended_action_key, row.recommended_action);
      }
      if (!row.pricing_model) return t('action.configure_pricing');
      if (Number(row.cache_ratio || 0) < 0.3 && Number(row.input_tokens || 0) > 0) return t('action.compare_fresh_input');
      if (Number(row.context_window_percent || 0) >= 0.6) return t('action.inspect_thread_timeline');
      if (Number(row.reasoning_output_tokens || 0) > Number(row.output_tokens || 0)) return t('action.review_reasoning_effort');
      return t('action.use_aggregate_first');
    }
    function fieldsList(fields, className = 'detail-kv') {
      return `<dl class="${className}">${fields.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(short(value))}</dd>`).join('')}</dl>`;
    }
    function detailCollapse(title, fields) {
      return `
        <details class="detail-collapse">
          <summary>${escapeHtml(title)}</summary>
          <div class="detail-collapse-body">${fieldsList(fields)}</div>
        </details>
      `;
    }
    function timelineSeverity(value) {
      if (value >= 0.65) return 'high';
      if (value >= 0.35) return 'medium';
      return 'low';
    }
    function timelineWidth(value) {
      return `${Math.round(clamp(Number(value || 0), 0, 1) * 100)}%`;
    }
    function renderThreadTimeline(group) {
      const calls = group.calls.slice(-5);
      if (!calls.length) return `<p>${escapeHtml(t('detail.timeline_empty'))}</p>`;
      return `<div class="timeline-list">${calls.map(row => {
        const contextUse = Number(row.context_window_percent || 0);
        return `
          <div class="timeline-item">
            <div class="timeline-time">${escapeHtml(formatTimestamp(row.event_timestamp, t('state.unknown')))}</div>
            <div>
              <div class="timeline-title">${escapeHtml(sourceLabelText(row))} · ${escapeHtml(short(row.model))}</div>
              <div class="timeline-meta">${escapeHtml(tf('detail.timeline_meta', { tokens: number.format(row.total_tokens || 0), cost: moneyText(row.estimated_cost_usd), credits: usageCreditValue(row) === null ? t('credit.no_rate') : `${credits(usageCreditValue(row))} ${t('badge.credits')}`, cache: pct(row.cache_ratio) }))}</div>
              <div class="timeline-meta">${escapeHtml(recommendationSummary(row))}</div>
              <div class="signal-strip">
                <span class="flag">${escapeHtml(tf('detail.timeline_context', { value: pct(contextUse) }))}</span>
                <span class="flag">${escapeHtml(pricingStatusText(row))}</span>
              </div>
              <div class="mini-bar" title="${escapeHtml(t('metric.context_use'))} ${escapeHtml(pct(contextUse))}"><span class="${timelineSeverity(contextUse)}" style="width: ${timelineWidth(contextUse)}"></span></div>
            </div>
          </div>
        `;
      }).join('')}</div>`;
    }
    function selectRow(row) {
      selectedRecordId = row.record_id || '';
      selectedThreadKey = '';
      showDetail(row);
      syncUrlState();
    }
    function bindDetailButtons(row, includeEvidence = true) {
      const openButton = detailEl.querySelector('[data-open-investigator-record]');
      const copyButton = detailEl.querySelector('[data-copy-call-link]');
      if (openButton) openButton.addEventListener('click', () => openInvestigator(row));
      if (copyButton) copyButton.addEventListener('click', () => copyCallLink(row));
      if (includeEvidence) bindContextButtons(row);
    }
    function selectThread(group) {
      selectedThreadKey = group.key || '';
      selectedRecordId = '';
      showThreadDetail(group);
      syncUrlState();
    }
    function showDetail(row) {
      const attachment = rowAttachment(row);
      const includeEvidence = activeView !== 'call';
      const flagValues = Array.isArray(row.efficiency_flags) ? row.efficiency_flags : [];
      const explanationKeys = Array.isArray(row.flag_explanation_keys) ? row.flag_explanation_keys : [];
      const flags = flagValues.length ? flagValues.map((flag, index) => translateEfficiencyFlag(row, flag, index)).join(', ') : t('state.none');
      const whyFlagged = Array.isArray(row.flag_explanations) && row.flag_explanations.length
        ? row.flag_explanations.map((explanation, index) => translatedField(explanationKeys[index], explanation)).join(' ')
        : recommendationSummary(row);
      detailEl.innerHTML = `
        <div class="detail-stack">
          <div class="detail-card primary">
            <h3>${escapeHtml(t('detail.cost_usage_context'))}</h3>
            <div class="detail-action-row">
              <button class="context-button" type="button" data-open-investigator-record="${escapeHtml(row.record_id || '')}">${escapeHtml(t('button.open_investigator'))}</button>
              <button class="context-button secondary" type="button" data-copy-call-link="${escapeHtml(row.record_id || '')}">${escapeHtml(t('button.copy_link'))}</button>
            </div>
            ${fieldsList([
              [t('metric.estimated_cost'), moneyText(row.estimated_cost_usd)],
              [t('metric.codex_credits'), usageCreditsWithStatus(row)],
              [t('detail.allowance_impact'), rowAllowanceImpact(row)],
              [t('metric.cache_ratio'), pct(row.cache_ratio)],
              [t('metric.uncached_input'), number.format(row.uncached_input_tokens || 0)],
              [t('metric.context_use'), pct(row.context_window_percent)],
              [t('detail.pricing_status'), pricingStatusText(row)],
              [t('detail.next_action'), nextActionForRow(row)],
              [t('detail.why_flagged'), whyFlagged],
            ])}
          </div>
          <div class="detail-card">
            <h3>${escapeHtml(t('detail.thread_narrative'))}</h3>
            ${fieldsList([
              [t('table.thread'), attachment.label],
              [t('filter.project'), row.project_name || t('state.unknown')],
              [t('detail.project_tags'), Array.isArray(row.project_tags) && row.project_tags.length ? row.project_tags.join(', ') : t('state.none')],
              [t('detail.thread_attachment'), attachmentRelationText(attachment.relation)],
              [t('table.source'), sourceLabelText(row)],
              [t('detail.parent_thread'), resolvedParentThreadName(row) || t('state.none')],
              [t('detail.timestamp'), formatTimestamp(row.event_timestamp)],
            ])}
          </div>
          <div class="detail-card">
            <h3>${escapeHtml(t('detail.token_pricing_breakdown'))}</h3>
            ${fieldsList([
              [t('metric.last_call_total'), number.format(row.total_tokens || 0)],
              [t('metric.last_call_input'), number.format(row.input_tokens || 0)],
              [t('metric.cached_input'), number.format(row.cached_input_tokens || 0)],
              [t('metric.output'), number.format(row.output_tokens || 0)],
              [t('metric.reasoning_output'), number.format(row.reasoning_output_tokens || 0)],
              [t('metric.session_cumulative'), number.format(row.cumulative_total_tokens || 0)],
              [t('detail.pricing_model'), row.pricing_model || t('state.no_configured_price')],
              [t('detail.credit_model'), row.usage_credit_model || t('credit.no_mapped_rate')],
              [t('detail.credit_confidence'), usageCreditStatusLabel(row)],
              [t('detail.credit_source'), t(row.usage_credit_source) || t('state.none')],
              [t('detail.credit_source_fetched'), row.usage_credit_fetched_at || t('state.unknown')],
              [t('detail.credit_tier'), t(row.usage_credit_tier) || t('state.unknown')],
              [t('detail.cache_savings'), moneyText(row.estimated_cache_savings_usd)],
              [t('detail.efficiency_signals'), flags],
            ])}
          </div>
          ${detailCollapse(t('detail.raw_identifiers'), [
            [t('filter.session'), row.session_id],
            [t('detail.turn'), row.turn_id],
              [t('detail.thread_source'), row.thread_source || t('source.user')],
              [t('detail.subagent_type'), row.subagent_type || t('state.none')],
              [t('detail.agent_role'), row.agent_role || t('state.none')],
              [t('detail.agent_nickname'), row.agent_nickname || t('state.none')],
              [t('detail.credit_note'), row.usage_credit_note || t('state.none')],
              [t('detail.parent_session'), row.parent_session_id || t('state.none')],
            [t('detail.parent_updated'), resolvedParentSessionUpdatedAt(row) ? formatTimestamp(resolvedParentSessionUpdatedAt(row)) : t('state.none')],
            [t('detail.cwd'), row.cwd],
            [t('detail.project_cwd'), row.project_relative_cwd || '.'],
            [t('detail.git_branch'), row.git_branch || t('state.unknown')],
            [t('detail.remote_label'), row.git_remote_label || t('state.none')],
            [t('detail.remote_hash'), row.git_remote_hash || t('state.none')],
          ])}
          ${detailCollapse(t('detail.source_file_line'), [
            [t('detail.source_line'), `${row.source_file}:${row.line_number}`],
            [t('detail.context_window'), number.format(row.model_context_window || 0)],
          ])}
          ${includeEvidence ? contextControls(row) : ''}
        </div>
      `;
      bindDetailButtons(row, includeEvidence);
    }
    function showThreadDetail(group) {
      const lifecycle = group.lifecycle || {};
      detailEl.innerHTML = `
        <div class="detail-stack">
          <div class="detail-card primary">
            <h3>${escapeHtml(t('detail.thread_attention_summary'))}</h3>
            ${fieldsList([
              [t('metric.estimated_cost'), pricingConfigured ? moneyText(group.estimatedCost) : t('state.not_configured')],
              [t('metric.codex_credits'), tf('credit.with_status', { value: credits(group.usageCredits), status: group.creditStatus })],
              [t('detail.allowance_impact'), allowanceWindowText(group.usageCredits, 'impact') || allowanceWindowText(group.usageCredits, 'remaining') || tf('allowance.counted', { value: credits(group.usageCredits) })],
              [t('metric.attention_score'), number.format(Math.round(group.attentionScore))],
              [t('metric.cache_ratio'), pct(group.cacheRatio)],
              [t('metric.max_context_use'), pct(group.maxContextUse)],
              [t('detail.pricing_status'), group.pricingStatus],
              [t('detail.next_action'), lifecycle.action || (group.maxContextUse >= threshold('high_context_percent', 0.6) || group.cacheRatio < threshold('low_cache_ratio', 0.3) ? t('action.inspect_thread_timeline') : t('action.expand_or_select_recommendations'))],
            ])}
          </div>
          <div class="detail-card">
            <h3>${escapeHtml(t('detail.thread_lifecycle'))}</h3>
            ${fieldsList([
              [t('detail.first_expensive_turn'), lifecycle.firstExpensiveRow ? `${formatTimestamp(lifecycle.firstExpensiveRow.event_timestamp)} · ${tf('detail.call_number', { number: number.format((lifecycle.firstExpensiveIndex || 0) + 1) })}` : t('detail.no_above_thresholds')],
              [t('detail.largest_cumulative_jump'), lifecycle.largestJumpRow ? tf('detail.tokens_at', { tokens: number.format(lifecycle.largestJump), time: formatTimestamp(lifecycle.largestJumpRow.event_timestamp) }) : t('state.none')],
              [t('metric.cache_trend'), `${lifecycle.cacheTrend >= 0 ? '+' : ''}${pct(lifecycle.cacheTrend || 0)}`],
              [t('metric.context_trend'), `${lifecycle.contextTrend >= 0 ? '+' : ''}${pct(lifecycle.contextTrend || 0)}`],
              [t('detail.subagent_before_spike'), lifecycle.subagentBeforeSpike ? t('state.yes') : t('state.no')],
            ])}
          </div>
          <div class="detail-card">
            <h3>${escapeHtml(t('detail.thread_timeline'))}</h3>
            ${renderThreadTimeline(group)}
          </div>
          <div class="detail-card">
            <h3>${escapeHtml(t('detail.relationships'))}</h3>
            ${fieldsList([
              [t('table.thread'), group.label],
              [t('detail.calls'), number.format(group.callCount)],
              [t('detail.subagent_calls'), number.format(group.subagentCount)],
              [t('detail.auto_review_calls'), number.format(group.autoReviewCount)],
              [t('detail.attached_calls'), number.format(group.attachedCount)],
              [t('detail.spawned_from'), group.parentThreadLabel || t('state.none')],
              [t('detail.spawned_threads'), number.format(group.childThreadCount || 0)],
              [t('detail.spawned_child_calls'), number.format(group.childCallCount || 0)],
            ])}
          </div>
          ${detailCollapse(t('detail.secondary_thread_fields'), [
            [t('detail.latest_activity'), formatTimestamp(group.latestActivity)],
            [t('metric.total_tokens'), number.format(group.totalTokens)],
            [t('detail.efficiency_signals'), number.format(group.signalCount)],
            [t('detail.model_mix'), group.modelSummary],
            [t('detail.reasoning_mix'), group.effortSummary],
          ])}
        </div>
      `;
    }
    function setView(view) {
      activeView = view;
      resetVisibleRows();
      render();
    }
    function renderLiveStatus() {
      const label = t(liveStatusKey);
      const detail = liveStatusDetail || label;
      liveStatusEl.textContent = label;
      setFastTooltip(liveStatusEl, detail);
      liveStatusEl.dataset.state = liveStatusKey === 'status.refresh_error' ? 'error' : 'ready';
    }
    function updateLiveStatus(statusKey, detail = '') {
      liveStatusKey = statusKey;
      liveStatusDetail = detail;
      renderLiveStatus();
    }
    function updateToTopVisibility() {
      toTopEl.dataset.visible = window.scrollY > 320 ? 'true' : 'false';
    }
    function applyDashboardPayload(nextPayload) {
      if (nextPayload.translation_catalog) {
        translationCatalog = nextPayload.translation_catalog;
        fallbackTranslations = { ...builtInFallbackTranslations, ...(translationCatalog.en || fallbackTranslations) };
      }
      if (Array.isArray(nextPayload.available_languages) && nextPayload.available_languages.length) {
        availableLanguages = nextPayload.available_languages;
        supportedLanguages = new Set(availableLanguages.map(language => language.code));
        populateLanguageOptions();
      }
      currentLanguage = normalizeLanguage(nextPayload.language || currentLanguage);
      applyTranslations();
      data = payloadRows(nextPayload);
      pricingConfigured = Boolean(nextPayload.pricing_configured);
      pricingSource = nextPayload.pricing_source || {};
      pricingSnapshotWarning = nextPayload.pricing_snapshot_warning || '';
      allowanceConfigured = Boolean(nextPayload.allowance_configured);
      allowanceSource = nextPayload.allowance_source || {};
      allowanceWindows = Array.isArray(nextPayload.allowance_windows) ? nextPayload.allowance_windows : [];
      allowanceError = nextPayload.allowance_error || '';
      rateCardError = nextPayload.rate_card_error || '';
      parserDiagnostics = nextPayload.parser_diagnostics || {};
      projectMetadataPrivacy = nextPayload.project_metadata_privacy || { mode: nextPayload.privacy_mode || 'normal' };
      apiToken = nextPayload.api_token || apiToken;
      contextApiEnabled = Boolean(nextPayload.context_api_enabled);
      actionThresholds = nextPayload.action_thresholds || actionThresholds;
      totalAvailableRows = Number(nextPayload.total_available_rows || data.length);
      activeAvailableRows = Number(nextPayload.active_available_rows || data.length);
      allHistoryAvailableRows = Number(nextPayload.all_history_available_rows || totalAvailableRows);
      archivedAvailableRows = Number(nextPayload.archived_available_rows || Math.max(allHistoryAvailableRows - activeAvailableRows, 0));
      includeArchived = Boolean(nextPayload.include_archived);
      loadedLimit = payloadLimit(nextPayload);
      rebuildDashboardIndexes();
      rebuildFilterOptions();
      updatePricingSourceLine();
      updateAllowanceSourceLine();
      updatePrivacyModeLine();
      updateParserDiagnosticsLine();
      updateLoadLimitControl();
      updateHistoryScopeControl();
      render();
    }
    async function refreshDashboardData(manual = false) {
      if (!liveRefreshSupported) {
        updateLiveStatus('status.reloading', t('live.reloading_static'));
        window.location.reload();
        return;
      }
      if (refreshInFlight) return;
      refreshInFlight = true;
      refreshDashboardEl.disabled = true;
      updateLiveStatus(manual ? 'status.refreshing' : 'status.checking', manual ? t('live.refreshing_index') : t('live.checking_usage'));
      try {
        const params = new URLSearchParams({
          refresh: '1',
          limit: loadLimitEl.value,
          include_archived: includeArchived ? '1' : '0',
          lang: currentLanguage,
          _: String(Date.now()),
        });
        const response = await fetch(`/api/usage?${params.toString()}`, {
          headers: {
            'Accept': 'application/json',
            'X-Codex-Usage-Token': apiToken,
          },
          cache: 'no-store',
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const nextPayload = await response.json();
        if (nextPayload.error) throw new Error(nextPayload.error);
        applyDashboardPayload(nextPayload);
        const result = nextPayload.refresh_result || {};
        const indexed = result.inserted_or_updated_events === undefined
          ? ''
          : tf('live.indexed', { rows: number.format(result.inserted_or_updated_events), files: number.format(result.scanned_files || 0) });
        const skipped = result.skipped_events
          ? tf('live.skipped', { count: number.format(result.skipped_events) })
          : '';
        updateLiveStatus(autoRefreshEl.checked ? 'badge.live' : 'status.updated', tf('live.updated_detail', { time: formatTimestamp(nextPayload.refreshed_at), loaded: loadedRowsDescription(), history: historyRowsDescription(), indexed, skipped }));
      } catch (error) {
        const message = error.message || String(error);
        updateLiveStatus('status.refresh_error', tf('live.refresh_unavailable', { message, suffix: manual ? t('live.refresh_suffix') : '' }));
        if (manual && message === 'HTTP 404') window.location.reload();
      } finally {
        refreshInFlight = false;
        refreshDashboardEl.disabled = false;
      }
    }
    function scheduleAutoRefresh() {
      if (autoRefreshTimer) window.clearInterval(autoRefreshTimer);
      autoRefreshTimer = null;
      if (!autoRefreshEl.checked || !liveRefreshSupported) return;
      autoRefreshTimer = window.setInterval(() => {
        if (document.visibilityState === 'visible') refreshDashboardData(false);
      }, liveRefreshIntervalMs);
    }
    insightsViewEl.addEventListener('click', () => setView('insights'));
    callsViewEl.addEventListener('click', () => setView('calls'));
    threadsViewEl.addEventListener('click', () => setView('threads'));
    clearPresetEl.addEventListener('click', clearPreset);
    copyViewLinkEl.addEventListener('click', copyCurrentViewLink);
    exportVisibleEl.addEventListener('click', exportCurrentRows);
    refreshDashboardEl.addEventListener('click', () => refreshDashboardData(true));
    if (languageSelectEl) {
      languageSelectEl.addEventListener('change', () => setLanguage(languageSelectEl.value));
    }
    loadLimitEl.addEventListener('change', () => {
      resetVisibleRows();
      if (liveRefreshSupported) {
        refreshDashboardData(true);
      } else {
        updateLiveStatus('status.static', t('live.load_static_hint'));
      }
    });
    historyScopeEl.addEventListener('change', () => {
      includeArchived = historyScopeEl.value === 'all';
      resetVisibleRows();
      updateHistoryScopeControl();
      syncUrlState();
      if (liveRefreshSupported) {
        refreshDashboardData(true);
      } else {
        updateLiveStatus('status.static', t('live.history_static_hint'));
      }
    });
    autoRefreshEl.addEventListener('change', () => {
      scheduleAutoRefresh();
      updateLiveStatus(autoRefreshEl.checked ? 'badge.live' : 'status.paused', `${autoRefreshEl.checked ? tf('live.every', { seconds: liveRefreshIntervalMs / 1000 }) : t('live.paused')}. ${loadedRowsDescription()}. ${historyRowsDescription()}`);
      if (autoRefreshEl.checked) refreshDashboardData(false);
    });
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && autoRefreshEl.checked) refreshDashboardData(false);
    });
    document.addEventListener('keydown', event => {
      const target = event.target;
      const inEditable = target && target.closest && target.closest('input, select, textarea, button, [contenteditable="true"]');
      if (inEditable) return;
      if (event.key === '/') {
        event.preventDefault();
        searchEl.focus();
        return;
      }
      if (event.key === '1') setView('insights');
      if (event.key === '2') setView('calls');
      if (event.key === '3') setView('threads');
    });
    window.addEventListener('scroll', updateToTopVisibility, { passive: true });
    toTopEl.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
    loadMoreRowsEl.addEventListener('click', () => {
      currentPage += 1;
      render();
    });
    document.querySelectorAll('[data-sort-key]').forEach(button => {
      button.addEventListener('click', () => handleHeaderSort(button.dataset.sortKey));
    });
    rowsEl.addEventListener('mouseover', event => {
      const callRow = event.target.closest('.thread-call-row');
      if (!callRow || !rowsEl.contains(callRow)) return;
      const row = rowByRecordId.get(callRow.dataset.recordId);
      if (row) selectRow(row);
    });
    rowsEl.addEventListener('click', event => {
      const openButton = event.target.closest('[data-open-investigator-record]');
      if (openButton && rowsEl.contains(openButton)) {
        event.preventDefault();
        event.stopPropagation();
        const row = rowByRecordId.get(openButton.dataset.openInvestigatorRecord);
        if (row) openInvestigator(row);
        return;
      }
      const copyButton = event.target.closest('[data-copy-call-link]');
      if (copyButton && rowsEl.contains(copyButton)) {
        event.preventDefault();
        event.stopPropagation();
        const row = rowByRecordId.get(copyButton.dataset.copyCallLink);
        if (row) copyCallLink(row);
        return;
      }
      const navButton = event.target.closest('[data-call-nav-record]');
      if (navButton && rowsEl.contains(navButton)) {
        event.preventDefault();
        event.stopPropagation();
        const recordId = navButton.dataset.callNavRecord;
        const row = rowByRecordId.get(recordId);
        if (row) {
          selectedRecordId = row.record_id || '';
          selectedThreadKey = rowAttachment(row).key;
          activeView = 'call';
          render();
        }
        return;
      }
      const sortButton = event.target.closest('[data-thread-call-sort-key]');
      if (sortButton && rowsEl.contains(sortButton)) {
        event.preventDefault();
        event.stopPropagation();
        handleThreadCallHeaderSort(sortButton.dataset.threadCallSortKey);
        return;
      }
      const loadMoreButton = event.target.closest('[data-thread-load-more]');
      if (loadMoreButton && rowsEl.contains(loadMoreButton)) {
        event.preventDefault();
        event.stopPropagation();
        const key = loadMoreButton.dataset.threadLoadMore;
        threadCallVisiblePages.set(key, Math.max(1, threadCallVisiblePages.get(key) || 1) + 1);
        render();
        return;
      }
      const callRow = event.target.closest('.thread-call-row');
      if (!callRow || !rowsEl.contains(callRow)) return;
      const row = rowByRecordId.get(callRow.dataset.recordId);
      if (row) showDetail(row);
    });
    rowsEl.addEventListener('dblclick', event => {
      const callRow = event.target.closest('.thread-call-row');
      if (!callRow || !rowsEl.contains(callRow)) return;
      const row = rowByRecordId.get(callRow.dataset.recordId);
      if (row) openInvestigator(row);
    });
    rowsEl.addEventListener('keydown', event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const callRow = event.target.closest('.thread-call-row');
      if (!callRow || !rowsEl.contains(callRow)) return;
      event.preventDefault();
      const row = rowByRecordId.get(callRow.dataset.recordId);
      if (row) selectRow(row);
    });
    document.addEventListener('mouseover', event => {
      const target = closestFastTooltipTarget(event.target);
      if (!target || !document.body.contains(target)) return;
      if (target.contains(event.relatedTarget)) return;
      scheduleFastTooltip(target);
    });
    document.addEventListener('mouseout', event => {
      const target = closestFastTooltipTarget(event.target);
      if (!target) return;
      if (target.contains(event.relatedTarget)) return;
      hideFastTooltip();
    });
    document.addEventListener('focusin', event => {
      const target = closestFastTooltipTarget(event.target);
      if (target) scheduleFastTooltip(target);
    });
    document.addEventListener('focusout', event => {
      const target = closestFastTooltipTarget(event.target);
      if (target) hideFastTooltip();
    });
    window.addEventListener('scroll', hideFastTooltip, { passive: true });
    window.addEventListener('resize', hideFastTooltip);
    datePresetEl.addEventListener('input', () => {
      syncDatePresetInputs();
      resetVisibleRows();
      render();
    });
    [dateStartEl, dateEndEl].forEach(el => el.addEventListener('input', () => {
      if (datePresetEl.value !== 'custom') datePresetEl.value = 'custom';
      el.value = cleanDateInput(el.value) || el.value;
      resetVisibleRows();
      render();
    }));
    [searchEl, modelEl, effortEl, pricingStatusEl].forEach(el => el.addEventListener('input', () => {
      resetVisibleRows();
      render();
    }));
    sortEl.addEventListener('input', () => setSort(sortEl.value, defaultSortDirection(sortEl.value)));
    rebuildDashboardIndexes();
    populateLanguageOptions();
    applyTranslations();
    rebuildFilterOptions();
    applyInitialState();
    updatePricingSourceLine();
    updateAllowanceSourceLine();
    updatePrivacyModeLine();
    updateParserDiagnosticsLine();
    updateLoadLimitControl();
    updateHistoryScopeControl();
    if (!liveRefreshSupported) {
      autoRefreshEl.checked = false;
      autoRefreshEl.disabled = true;
      loadLimitEl.disabled = true;
      historyScopeEl.disabled = true;
      updateLiveStatus('status.static', `${t('status.static')}. ${loadedRowsDescription()}. ${historyRowsDescription()}`);
    } else {
      updateLiveStatus('badge.live', `${tf('live.every', { seconds: liveRefreshIntervalMs / 1000 })}. ${loadedRowsDescription()}. ${historyRowsDescription()}`);
      scheduleAutoRefresh();
      if (needsInitialHistoryRefresh) refreshDashboardData(false);
    }
    updateToTopVisibility();
    render();
