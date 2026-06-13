    const dashboardFormat = window.CodexUsageDashboardFormat;
    const dashboardData = window.CodexUsageDashboardData;
    const dashboardFilters = window.CodexUsageDashboardFilters;
    const dashboardAnalysisFactory = window.CodexUsageDashboardAnalysis;
    const dashboardCellsFactory = window.CodexUsageDashboardCells;
    const dashboardPayloadCache = window.CodexUsageDashboardPayloadCache;
    const dashboardTooltipFactory = window.CodexUsageDashboardTooltips;
    const {
      number,
      money,
      credits,
      compactNumber,
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
      buildCallAdjacencyIndex,
      classifyCacheDiagnostic,
      callAccountingDelta,
      rowInputTokens: dataRowInputTokens,
      cachedInputTokens: dataCachedInputTokens,
      uncachedInputTokens: dataUncachedInputTokens,
      outputTokens: dataOutputTokens,
      rowReasoningTokens: dataRowReasoningTokens,
    } = dashboardData;
    const {
      addDays,
      cleanDateInput,
      formatDateRangeLabel: formatDateRangeLabelWithTranslator,
      localDateKey,
      parseDateInput,
      presetDateRange,
      rowMatchesDateRange,
    } = dashboardFilters;
    const initialPayload = JSON.parse(document.getElementById('usage-data').textContent);
    const {
      activeInitialPayload,
      restoredAggregatePayloadFromCache: initialRestoredAggregatePayloadFromCache,
    } = dashboardPayloadCache.resolveInitialPayload(initialPayload);
    let restoredAggregatePayloadFromCache = initialRestoredAggregatePayloadFromCache;
    const i18n = window.CodexUsageDashboardI18n.create(activeInitialPayload, { escapeHtml });
    const tooltips = dashboardTooltipFactory.create({ escapeHtml, clamp });
    let liveStatusKey = window.location.protocol !== 'file:' ? 'badge.live' : 'status.static';
    let liveStatusDetail = '';
    function t(key) {
      return i18n.t(key);
    }
    function tf(key, values = {}) {
      return i18n.tf(key, values);
    }
    function translatedField(keyValue, fallbackText = '') {
      return i18n.translatedField(keyValue, fallbackText);
    }
    function languageDirection(language) {
      return i18n.languageDirection(language);
    }
    function populateLanguageOptions() {
      i18n.populateLanguageOptions(languageSelectEl);
    }
    function translateEffort(value) {
      return i18n.translateEffort(value);
    }
    const stateManager = window.CodexUsageDashboardState;
    const urlParams = new URLSearchParams(window.location.search);
    const initialState = stateManager ? stateManager.read(urlParams) : {};
    let data = payloadRows(activeInitialPayload);
    let summaryData = activeInitialPayload.summary || null;
    let shellBoot = Boolean(activeInitialPayload.shell_boot);
    let pricingConfigured = Boolean(activeInitialPayload.pricing_configured);
    let pricingSource = activeInitialPayload.pricing_source || {};
    let pricingSnapshotWarning = activeInitialPayload.pricing_snapshot_warning || '';
    let latestRefreshAt = activeInitialPayload.latest_refresh_at || '';
    let allowanceConfigured = Boolean(activeInitialPayload.allowance_configured);
    let allowanceSource = activeInitialPayload.allowance_source || {};
    let allowanceWindows = Array.isArray(activeInitialPayload.allowance_windows) ? activeInitialPayload.allowance_windows : [];
    let allowanceError = activeInitialPayload.allowance_error || '';
    let rateCardError = activeInitialPayload.rate_card_error || '';
    let projectMetadataPrivacy = activeInitialPayload.project_metadata_privacy || { mode: activeInitialPayload.privacy_mode || 'normal' };
    let parserDiagnostics = activeInitialPayload.parser_diagnostics || {};
    let apiToken = initialPayload.api_token || activeInitialPayload.api_token || '';
    let contextApiEnabled = Boolean(initialPayload.context_api_enabled || activeInitialPayload.context_api_enabled);
    let actionThresholds = activeInitialPayload.action_thresholds || {};
    let totalAvailableRows = Number(activeInitialPayload.total_available_rows || data.length);
    let activeAvailableRows = Number(activeInitialPayload.active_available_rows || data.length);
    let allHistoryAvailableRows = Number(activeInitialPayload.all_history_available_rows || totalAvailableRows);
    let archivedAvailableRows = Number(activeInitialPayload.archived_available_rows || Math.max(allHistoryAvailableRows - activeAvailableRows, 0));
    let loadedLimit = payloadLimit(activeInitialPayload);
    const rowsEl = document.getElementById('rows');
    const detailEl = document.getElementById('detail');
    const detailToggleEl = document.getElementById('detailToggle');
    const detailSectionEl = document.querySelector('.detail-section');
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
    const rowLoadProgressEl = document.getElementById('rowLoadProgress');
    const rowLoadProgressLabelEl = document.getElementById('rowLoadProgressLabel');
    const rowLoadProgressCountEl = document.getElementById('rowLoadProgressCount');
    const rowLoadProgressBarEl = document.getElementById('rowLoadProgressBar');
    const toTopEl = document.getElementById('toTop');
    let rowByRecordId = new Map();
    let threadAttachmentByRecordId = new Map();
    let callAdjacencyByRecordId = new Map();
    let supplementalRowsByRecordId = new Map();
    const callFetchInFlightByRecordId = new Set();
    const expandedThreads = new Set();
    const liveRefreshSupported = window.location.protocol !== 'file:';
    const initialPayloadIncludeArchived = Boolean(activeInitialPayload.include_archived);
    let includeArchived = initialPayloadIncludeArchived;
    if (liveRefreshSupported && initialState.historyScope === 'all') includeArchived = true;
    const needsInitialHistoryRefresh = liveRefreshSupported && includeArchived !== initialPayloadIncludeArchived;
    const liveRefreshIntervalMs = 10000;
    const pageSize = 500;
    const initialHydrationChunkSize = 500;
    const backgroundHydrationChunkSize = 2000;
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
    document.body.dataset.activeView = activeView;
    let sortKey = optionValueExists(sortEl, initialState.sort) ? initialState.sort : sortEl.value || 'attention';
    let sortDirection = ['asc', 'desc'].includes(initialState.direction) ? initialState.direction : defaultSortDirection(sortKey);
    let threadCallSortKey = 'time';
    let threadCallSortDirection = 'desc';
    let activePreset = '';
    let selectedRecordId = initialState.record || '';
    let selectedThreadKey = initialState.thread || '';
    let refreshInFlight = false;
    let rowHydrationInFlight = false;
    let rowHydrationComplete = !shellBoot && data.length > 0;
    let rowHydrationError = '';
    let rowHydrationGeneration = 0;
    let rowHydrationRestartRequested = false;
    let autoRefreshTimer = null;
    let currentPage = 1;
    const threadCallVisiblePages = new Map();
    let pendingFocusTarget = null;
    let detailPanelExpanded = readDetailPanelPreference();
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
      i18n.refreshTranslations();
      document.documentElement.lang = i18n.currentLanguage;
      document.documentElement.dir = languageDirection(i18n.currentLanguage);
      document.title = t('dashboard.title');
      if (languageSelectEl) languageSelectEl.value = i18n.currentLanguage;
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
      applyDetailPanelState();
    }
    function setLanguage(language) {
      i18n.setLanguage(language);
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
    function readDetailPanelPreference() {
      try {
        return window.sessionStorage?.getItem('codexUsageDetailPanel') === 'expanded';
      } catch (error) {
        return false;
      }
    }
    function rememberDetailPanelPreference(expanded) {
      try {
        window.sessionStorage?.setItem('codexUsageDetailPanel', expanded ? 'expanded' : 'collapsed');
      } catch (error) {
        // Session storage is optional; the drawer can still work without persistence.
      }
    }
    function applyDetailPanelState() {
      document.body.dataset.detailPanel = detailPanelExpanded ? 'expanded' : 'collapsed';
      if (detailSectionEl) detailSectionEl.dataset.collapsed = detailPanelExpanded ? 'false' : 'true';
      if (detailToggleEl) {
        detailToggleEl.setAttribute('aria-expanded', detailPanelExpanded ? 'true' : 'false');
        detailToggleEl.textContent = detailPanelExpanded ? t('button.hide_details') : t('dashboard.call_details');
      }
    }
    function setDetailPanelExpanded(expanded) {
      detailPanelExpanded = Boolean(expanded);
      rememberDetailPanelPreference(detailPanelExpanded);
      applyDetailPanelState();
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
        initiator: t('table.initiated'),
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
    function rowHydrationTarget() {
      const available = Math.max(0, Number(totalAvailableRows || 0));
      if (!available) return 0;
      return loadedLimit === null ? available : Math.min(available, Number(loadedLimit || available));
    }
    function rowsNeedHydration() {
      const target = rowHydrationTarget();
      return liveRefreshSupported && target > 0 && data.length < target;
    }
    function clientFiltersActive(dateRange = currentDateRange()) {
      return Boolean(
        searchEl.value.trim()
        || modelEl.value
        || effortEl.value
        || pricingStatusEl.value
        || activePreset
        || dateRange.active
        || dateRange.invalid
      );
    }
    function summaryForCards(dateRange, rows) {
      if (!summaryData || loadedLimit !== null || clientFiltersActive(dateRange) || data.length >= rowHydrationTarget()) return null;
      return {
        visibleCalls: Number(summaryData.visible_calls ?? summaryData.row_count ?? totalAvailableRows ?? rows.length),
        totalTokens: Number(summaryData.total_tokens || 0),
        cachedInputTokens: Number(summaryData.cached_input_tokens || 0),
        uncachedInputTokens: Number(summaryData.uncached_input_tokens || 0),
        reasoningOutputTokens: Number(summaryData.reasoning_output_tokens || 0),
        estimatedCost: Number(summaryData.estimated_cost_usd || 0),
        usageCredits: Number(summaryData.usage_credits || 0),
      };
    }
    function updateRowLoadProgress() {
      if (!rowLoadProgressEl) return;
      const target = rowHydrationTarget();
      const loaded = Math.min(data.length, target || data.length);
      const shouldShow = activeView !== 'call' && liveRefreshSupported && (rowHydrationInFlight || rowsNeedHydration() || rowHydrationError);
      rowLoadProgressEl.hidden = !shouldShow;
      if (!shouldShow) return;
      const totalText = number.format(target || totalAvailableRows || loaded);
      const loadedText = number.format(loaded);
      rowLoadProgressLabelEl.textContent = rowHydrationError ? t('state.error') : t('state.loading_rows');
      rowLoadProgressCountEl.textContent = rowHydrationError
        ? rowHydrationError
        : (rowHydrationComplete
            ? tf('caption.rows_loaded_progress', { loaded: loadedText, total: totalText })
            : tf('caption.rows_loading_progress', { loaded: loadedText, total: totalText }));
      const ratio = target ? Math.max(0, Math.min(100, (loaded / target) * 100)) : 0;
      rowLoadProgressBarEl.style.width = `${ratio}%`;
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
      const indexedRows = [...data];
      for (const row of supplementalRowsByRecordId.values()) {
        if (!row?.record_id || indexedRows.some(candidate => candidate.record_id === row.record_id)) continue;
        indexedRows.push(row);
      }
      rowByRecordId = new Map(indexedRows.map(row => [row.record_id, row]));
      threadAttachmentByRecordId = new Map(indexedRows.map(row => [row.record_id, resolveThreadAttachment(row)]));
      callAdjacencyByRecordId = buildCallAdjacencyIndex(indexedRows);
    }
    function mergedRows(existingRows, nextRows) {
      const seen = new Set(existingRows.map(row => row.record_id).filter(Boolean));
      const merged = [...existingRows];
      for (const row of nextRows) {
        if (!row?.record_id || seen.has(row.record_id)) continue;
        seen.add(row.record_id);
        merged.push(row);
      }
      return merged;
    }
    function tooltipAttributes(text) {
      return tooltips.tooltipAttributes(text);
    }
    function setFastTooltip(element, text) {
      tooltips.setFastTooltip(element, text);
    }
    function hideFastTooltip() {
      tooltips.hideFastTooltip();
    }
    function scheduleFastTooltip(target) {
      tooltips.scheduleFastTooltip(target);
    }
    function closestFastTooltipTarget(eventTarget) {
      return tooltips.closestFastTooltipTarget(eventTarget);
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
    async function openInvestigatorUrl(url) {
      if (liveRefreshSupported) {
        if (apiToken) {
          try {
            const params = new URLSearchParams({ url });
            const response = await fetch(`/api/open-investigator?${params.toString()}`, {
              headers: {
                'Accept': 'application/json',
                'X-Codex-Usage-Token': apiToken,
              },
              cache: 'no-store',
            });
            if (response.ok) return true;
          } catch (_error) {
            // Fall through to copying the link; never mutate this window on failure.
          }
        }
      } else {
        const opened = window.open(url, '_blank');
        if (opened) {
          opened.opener = null;
          return true;
        }
      }
      try {
        await stateManager.copyText(url);
        showActionStatus(t('action.copied'));
      } catch (_error) {
        showActionStatus(t('action.copy_failed'));
      }
      return false;
    }
    async function openInvestigator(row) {
      await openInvestigatorUrl(investigatorUrl(row));
    }
    function rowInvestigatorLink(row, html, focusable = false) {
      const tabIndex = focusable ? '' : ' tabindex="-1"';
      return `<a class="row-investigator-link" href="${escapeHtml(investigatorUrl(row))}" target="_blank" rel="noopener"${tabIndex}>${html}</a>`;
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
    function formatDateRangeLabel(prefix, start, end) {
      return formatDateRangeLabelWithTranslator(prefix, start, end, tf);
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
          row.call_initiator,
          row.call_initiator_reason,
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
        { label: 'initiated', field: row => callInitiator(row).label },
        { label: 'initiated_reason', field: row => callInitiator(row).source },
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
    const {
      attachmentRelationText,
      cachedInputTokens,
      cachedTokenCell,
      callInitiator,
      callInitiatorCell,
      callInitiatorPuck,
      callInitiatorText,
      costUsageCell,
      effortCell,
      effortTooltipText,
      outputTokenCell,
      outputTokens,
      renderSignalPucks,
      sourceLabelText,
      threadInitiatorSummary,
      tokenNumberCell,
      totalTokenCell,
      uncachedInputTokens,
      uncachedTokenCell,
      usageCreditsWithStatus,
      usageCreditStatusLabel,
    } = dashboardCellsFactory.create({
      credits,
      dataCachedInputTokens,
      dataOutputTokens,
      dataUncachedInputTokens,
      escapeHtml,
      isAutoReview,
      isSubagent,
      number,
      short,
      t,
      tf,
      tooltipAttributes,
      translateEffort,
      translateEfficiencyFlag,
      usageCreditValue,
    });
    const dashboardAnalysis = dashboardAnalysisFactory.create({
      cachedInputTokens,
      callInitiatorText,
      chronological,
      clamp,
      compareValues,
      effortTooltipText,
      isAutoReview,
      isSubagent,
      outputTokens,
      resolvedParentThreadName,
      rowAttachment,
      rowThreadLabel,
      sumUsageCredits,
      t,
      textValue,
      tf,
      topRecommendation,
      translateEffort,
      uncachedInputTokens,
      usageCreditValue,
    });
    function signalCount(row) {
      return dashboardAnalysis.signalCount(row);
    }
    function rowAttentionScore(row) {
      return dashboardAnalysis.rowAttentionScore(row);
    }
    function severityForScore(score, hasPricingGap = false) {
      return dashboardAnalysis.severityForScore(score, hasPricingGap);
    }
    function compareCalls(a, b) {
      return dashboardAnalysis.compareCalls(a, b, sortKey, sortDirection);
    }
    function sortedThreadCalls(calls) {
      return dashboardAnalysis.sortedThreadCalls(calls, threadCallSortKey, threadCallSortDirection);
    }
    function groupThreads(rows) {
      return dashboardAnalysis.groupThreads(rows, sortKey, sortDirection, {
        highCost: threshold('high_cost_usd', 1),
        highContext: threshold('high_context_percent', 0.6),
      });
    }
    function setSummaryNumber(id, value, labelKey) {
      const element = document.getElementById(id);
      if (!element) return;
      const exact = number.format(Math.round(Number(value) || 0));
      const compacted = compactNumber(value);
      element.textContent = compacted;
      setFastTooltip(element, compacted === exact ? '' : `${t(labelKey)}: ${exact}`);
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
      return adjacentThreadCalls(data, row, callAdjacencyByRecordId);
    }
    function cacheDiagnostic(row, previous = null) {
      const diagnostic = classifyCacheDiagnostic(row, previous);
      if (diagnostic === 'post_compaction') {
        return {
          key: 'post-compaction',
          label: t('call.post_compaction'),
          body: 'A compaction marker or reset-like profile is associated with this call. Check loaded evidence to confirm replacement context.',
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
      rowsEl.textContent = '';
      document.body.dataset.activeView = activeView;
      updateSortControls();
      if (activeView === 'call') {
        callInvestigator.renderCallInvestigator(Array.from(rowByRecordId.values()));
        fitModelPills();
        syncUrlState();
        return;
      }
      const dateRange = updateDateFilterControls();
      const rows = filtered(dateRange);
      const shellSummary = summaryForCards(dateRange, rows);
      const totalTokens = shellSummary ? shellSummary.totalTokens : rows.reduce((sum, row) => sum + Number(row.total_tokens || 0), 0);
      const cachedInputTokens = shellSummary ? shellSummary.cachedInputTokens : rows.reduce((sum, row) => sum + Number(row.cached_input_tokens || 0), 0);
      const uncachedInputTokens = shellSummary ? shellSummary.uncachedInputTokens : rows.reduce((sum, row) => sum + Number(row.uncached_input_tokens || 0), 0);
      const reasoningOutputTokens = shellSummary ? shellSummary.reasoningOutputTokens : rows.reduce((sum, row) => sum + Number(row.reasoning_output_tokens || 0), 0);
      setSummaryNumber('visibleCalls', shellSummary ? shellSummary.visibleCalls : rows.length, 'metric.visible_calls');
      setSummaryNumber('totalTokens', totalTokens, 'metric.total_tokens');
      setSummaryNumber('cachedTokens', cachedInputTokens, 'metric.cached_input');
      setSummaryNumber('uncachedTokens', uncachedInputTokens, 'metric.uncached_input');
      setSummaryNumber('reasoningTokens', reasoningOutputTokens, 'metric.reasoning_output');
      const estimatedCost = shellSummary ? shellSummary.estimatedCost : rows.reduce((sum, row) => sum + Number(row.estimated_cost_usd || 0), 0);
      const usageCredits = shellSummary ? shellSummary.usageCredits : sumUsageCredits(rows);
      document.getElementById('estimatedCost').textContent = pricingConfigured ? moneyText(estimatedCost) : t('state.not_configured');
      document.getElementById('usageCredits').textContent = credits(usageCredits);
      document.getElementById('allowanceImpact').textContent = allowanceImpactText(usageCredits);
      setFastTooltip(document.getElementById('allowanceImpact'), allowanceWindowText(usageCredits, 'remaining') || t('allowance.title_hint'));
      insightsViewEl.setAttribute('aria-pressed', activeView === 'insights' ? 'true' : 'false');
      callsViewEl.setAttribute('aria-pressed', activeView === 'calls' ? 'true' : 'false');
      threadsViewEl.setAttribute('aria-pressed', activeView === 'threads' ? 'true' : 'false');
      renderInsightPanel(rows);
      if (activeView === 'call') {
        callInvestigator.renderCallInvestigator(rows);
      } else if (activeView === 'threads') {
        renderThreads(rows);
      } else if (activeView === 'insights') {
        renderThreads(rows, 'insights');
      } else {
        renderCalls(rows);
      }
      fitModelPills();
      updateRowLoadProgress();
      syncUrlState();
      scheduleFocusPendingTarget();
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
        tr.innerHTML = `
          <td>${rowInvestigatorLink(row, renderTimeCell(row.event_timestamp), true)}</td>
          <td title="${escapeHtml(short(row.session_id))}">${rowInvestigatorLink(row, `<span class="thread-name">${escapeHtml(truncate(rowThreadLabel(row)))}</span>`)}</td>
          <td>${rowInvestigatorLink(row, callInitiatorCell(row))}</td>
          <td>${rowInvestigatorLink(row, `<span class="pill model-pill" data-full-label="${escapeHtml(short(row.model))}">${escapeHtml(short(row.model))}</span>`)}</td>
          <td>${rowInvestigatorLink(row, effortCell(translateEffort(short(row.effort)), translateEffort(short(row.effort))))}</td>
          <td class="num token-cell">${rowInvestigatorLink(row, totalTokenCell(row))}</td>
          <td class="num token-cell">${rowInvestigatorLink(row, cachedTokenCell(row))}</td>
          <td class="num token-cell">${rowInvestigatorLink(row, uncachedTokenCell(row))}</td>
          <td class="num token-cell">${rowInvestigatorLink(row, outputTokenCell(row))}</td>
          <td class="num">${rowInvestigatorLink(row, costUsageCell(row.pricing_estimated ? `${moneyText(row.estimated_cost_usd)}*` : moneyText(row.estimated_cost_usd), usageCreditValue(row)))}</td>
          <td class="num">${rowInvestigatorLink(row, pct(row.cache_ratio))}</td>
          <td>${rowInvestigatorLink(row, `<div class="flags">${renderSignalPucks(row, flags, 3)}</div>`)}</td>
        `;
        tr.addEventListener('mouseenter', () => showDetail(row));
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
        const message = rowsNeedHydration()
          ? t('caption.rows_loading_background')
          : t('state.no_calls');
        rowsEl.innerHTML = `<tr><td class="empty-state" colspan="12">${escapeHtml(message)}</td></tr>`;
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
          <td>${threadInitiatorSummary(group)}</td>
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
        rowsEl.innerHTML = `<tr><td class="empty-state" colspan="12">${escapeHtml(t('state.no_threads'))}</td></tr>`;
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
          <tr class="thread-call-row${selectedRecordId === row.record_id ? ' selected-row' : ''}" data-record-id="${escapeHtml(row.record_id || '')}">
            <td>${rowInvestigatorLink(row, renderTimeCell(row.event_timestamp), true)}</td>
            <td>${rowInvestigatorLink(row, callInitiatorCell(row))}</td>
            <td>${rowInvestigatorLink(row, `<span class="pill model-pill" data-full-label="${escapeHtml(short(row.model))}">${escapeHtml(short(row.model))}</span>`)}</td>
            <td>${rowInvestigatorLink(row, effortCell(translateEffort(short(row.effort)), translateEffort(short(row.effort))))}</td>
            <td class="num token-cell">${rowInvestigatorLink(row, totalTokenCell(row))}</td>
            <td class="num token-cell">${rowInvestigatorLink(row, cachedTokenCell(row))}</td>
            <td class="num token-cell">${rowInvestigatorLink(row, uncachedTokenCell(row))}</td>
            <td class="num token-cell">${rowInvestigatorLink(row, outputTokenCell(row))}</td>
            <td class="num">${rowInvestigatorLink(row, costUsageCell(row.pricing_estimated ? `${moneyText(row.estimated_cost_usd)}*` : moneyText(row.estimated_cost_usd), usageCreditValue(row)))}</td>
            <td class="num">${rowInvestigatorLink(row, pct(row.cache_ratio))}</td>
            <td>${rowInvestigatorLink(row, `<div class="flags compact-flags">${renderSignalPucks(row, flags, 3, t('state.none'))}</div>`)}</td>
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
        <td class="child-cell" colspan="12">
          <table class="thread-call-table" aria-label="${escapeHtml(`${group.label} ${t('table.calls')}`)}">
            <thead><tr>
              ${threadCallHeader('time', t('table.time'))}
              ${threadCallHeader('initiator', t('table.initiated'))}
              ${threadCallHeader('model', t('table.model'))}
              ${threadCallHeader('effort', t('table.effort'))}
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
              <div class="timeline-title">${callInitiatorPuck(row)} ${escapeHtml(short(row.model))}</div>
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
      if (includeEvidence) callInvestigator.bindContextButtons(row);
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
            <div class="detail-source-line">${callInitiatorPuck(row)}<span>${escapeHtml(sourceLabelText(row))}</span></div>
            ${fieldsList([
              [t('table.thread'), attachment.label],
              [t('filter.project'), row.project_name || t('state.unknown')],
              [t('detail.project_tags'), Array.isArray(row.project_tags) && row.project_tags.length ? row.project_tags.join(', ') : t('state.none')],
              [t('detail.thread_attachment'), attachmentRelationText(attachment.relation)],
              [t('table.source'), callInitiatorText(row)],
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
          ${includeEvidence ? callInvestigator.contextControls(row) : ''}
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
    async function routeBackToDashboard(view = 'calls') {
      activeView = ['calls', 'threads', 'insights'].includes(view) ? view : 'calls';
      resetVisibleRows();
      if (liveRefreshSupported && !data.length) {
        autoRefreshEl.checked = true;
        await refreshDashboardData(false, { refreshLogs: false, resetRows: true });
      } else {
        render();
      }
      if (liveRefreshSupported && autoRefreshEl.checked) {
        scheduleAutoRefresh();
        refreshDashboardIfStale();
      }
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
    function applyDashboardPayload(nextPayload, options = null) {
      const applyOptions = options || {};
      if (i18n.updatePayload(nextPayload)) {
        populateLanguageOptions();
      }
      applyTranslations();
      const nextRows = payloadRows(nextPayload);
      if (applyOptions.appendRows) {
        data = mergedRows(data, nextRows);
      } else if (applyOptions.preserveRows) {
        data = data.length ? data : nextRows;
      } else {
        data = nextRows;
      }
      summaryData = nextPayload.summary || summaryData;
      if (!applyOptions.appendRows) shellBoot = Boolean(nextPayload.shell_boot);
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
      latestRefreshAt = nextPayload.latest_refresh_at || latestRefreshAt;
      totalAvailableRows = Number(nextPayload.total_available_rows || data.length);
      activeAvailableRows = Number(nextPayload.active_available_rows || data.length);
      allHistoryAvailableRows = Number(nextPayload.all_history_available_rows || totalAvailableRows);
      archivedAvailableRows = Number(nextPayload.archived_available_rows || Math.max(allHistoryAvailableRows - activeAvailableRows, 0));
      includeArchived = Boolean(nextPayload.include_archived);
      if (!applyOptions.appendRows) loadedLimit = payloadLimit(nextPayload);
      if (!applyOptions.appendRows) supplementalRowsByRecordId = new Map();
      restoredAggregatePayloadFromCache = false;
      if (!nextPayload.shell_boot && !applyOptions.appendRows) {
        dashboardPayloadCache.writeAggregatePayloadCache({ ...nextPayload, api_token: apiToken });
      }
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
    const callInvestigator = window.CodexUsageCallInvestigator.create({
      number,
      pct,
      escapeHtml,
      short,
      formatTimestamp,
      t,
      tf,
      moneyText,
      creditsText,
      tooltipAttributes,
      usageCreditValue,
      rowInputTokens,
      cachedInputTokens,
      uncachedInputTokens,
      outputTokens,
      rowReasoningTokens,
      callAccountingDelta,
      cacheDiagnostic,
      adjacentCalls,
      rowThreadLabel,
      rowAttachment,
      translateEffort,
      pricingStatusText,
      usageCreditStatusLabel,
      usageCreditsWithStatus,
      callInitiatorPuck,
      callInitiatorText,
      tableUrlForRow,
      signedNumber,
      signedPct,
      threshold,
      getSelectedRecordId: () => selectedRecordId,
      setSelectedRecordId: value => { selectedRecordId = value || ''; },
      getRowByRecordId: () => rowByRecordId,
      fetchCallRecord,
      getContextRuntime: () => ({ apiToken, contextApiEnabled, activeView }),
      setContextApiEnabled: value => { contextApiEnabled = Boolean(value); },
      renderDashboard: render,
      showDetail,
      updateLoadMoreControl,
      rowsEl,
      detailEl,
      pagerEl,
      tableTitleEl,
      tableCaptionEl,
      defaultContextEntries,
    });
    async function fetchCallRecord(recordId) {
      const normalizedRecordId = recordId || '';
      if (!liveRefreshSupported || !normalizedRecordId || !apiToken) return null;
      const existing = rowByRecordId.get(normalizedRecordId);
      if (existing) return existing;
      if (callFetchInFlightByRecordId.has(normalizedRecordId)) return null;
      callFetchInFlightByRecordId.add(normalizedRecordId);
      try {
        const params = new URLSearchParams({ record_id: normalizedRecordId, _: String(Date.now()) });
        const response = await fetch(`/api/call?${params.toString()}`, {
          headers: {
            'Accept': 'application/json',
            'X-Codex-Usage-Token': apiToken,
          },
          cache: 'no-store',
        });
        if (!response.ok) return null;
        const payload = await response.json();
        if (!payload?.record?.record_id) return null;
        const adjacentRecords = Array.isArray(payload.adjacent_records) && payload.adjacent_records.length
          ? payload.adjacent_records
          : [payload.previous_record, payload.record, payload.next_record].filter(Boolean);
        adjacentRecords.forEach(record => {
          if (record?.record_id) supplementalRowsByRecordId.set(record.record_id, record);
        });
        rebuildDashboardIndexes();
        if (activeView === 'call' && selectedRecordId === normalizedRecordId) {
          selectedThreadKey = rowAttachment(payload.record).key;
          render();
        }
        return payload.record;
      } catch (_error) {
        return null;
      } finally {
        callFetchInFlightByRecordId.delete(normalizedRecordId);
      }
    }
    async function navigateToCallRecord(recordId) {
      const normalizedRecordId = recordId || '';
      if (!normalizedRecordId) return;
      selectedRecordId = normalizedRecordId;
      const existing = rowByRecordId.get(normalizedRecordId);
      if (existing) selectedThreadKey = rowAttachment(existing).key;
      activeView = 'call';
      render();
      if (!existing) {
        const fetched = await fetchCallRecord(normalizedRecordId);
        if (fetched && selectedRecordId === normalizedRecordId) {
          selectedThreadKey = rowAttachment(fetched).key;
          render();
        }
      }
    }
    async function hydrateDashboardRows(options = null) {
      if (!liveRefreshSupported || activeView === 'call') return;
      const hydrateOptions = options || {};
      if (rowHydrationInFlight) {
        if (hydrateOptions.reset) rowHydrationRestartRequested = true;
        return;
      }
      const target = rowHydrationTarget();
      if (!target) {
        rowHydrationComplete = true;
        updateRowLoadProgress();
        return;
      }
      if (hydrateOptions.reset) {
        data = [];
        supplementalRowsByRecordId = new Map();
        rowHydrationComplete = false;
        rowHydrationGeneration += 1;
        rebuildDashboardIndexes();
        rebuildFilterOptions();
        render();
      }
      if (data.length >= target) {
        rowHydrationComplete = true;
        updateRowLoadProgress();
        return;
      }
      const generation = rowHydrationGeneration;
      rowHydrationInFlight = true;
      rowHydrationError = '';
      updateLiveStatus('status.checking', t('live.loading_rows'));
      updateRowLoadProgress();
      try {
        while (data.length < target && generation === rowHydrationGeneration && activeView !== 'call') {
          const offset = data.length;
          const remaining = target - offset;
          const chunkSize = Math.min(
            offset === 0 ? initialHydrationChunkSize : backgroundHydrationChunkSize,
            remaining,
          );
          const params = new URLSearchParams({
            limit: String(chunkSize),
            offset: String(offset),
            include_archived: includeArchived ? '1' : '0',
            lang: i18n.currentLanguage,
            _: String(Date.now()),
          });
          const response = await fetch(`/api/usage?${params.toString()}`, {
            headers: {
              'Accept': 'application/json',
              'X-Codex-Usage-Token': apiToken,
            },
            cache: 'no-store',
          });
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          const payload = await response.json();
          if (payload.error) throw new Error(payload.error);
          if (generation !== rowHydrationGeneration || activeView === 'call') break;
          const rows = payloadRows(payload);
          if (!rows.length) break;
          applyDashboardPayload(payload, { appendRows: true });
          updateRowLoadProgress();
          if (!payload.has_more || rows.length < chunkSize) break;
        }
        rowHydrationComplete = data.length >= rowHydrationTarget();
        updateLiveStatus(autoRefreshEl.checked ? 'badge.live' : 'status.updated', `${loadedRowsDescription()}. ${historyRowsDescription()}`);
      } catch (error) {
        rowHydrationError = error.message || String(error);
        updateLiveStatus('status.refresh_error', tf('live.refresh_unavailable', { message: rowHydrationError, suffix: '' }));
      } finally {
        rowHydrationInFlight = false;
        updateRowLoadProgress();
        const shouldRestart = rowHydrationRestartRequested && activeView !== 'call';
        rowHydrationRestartRequested = false;
        if (shouldRestart) {
          hydrateDashboardRows();
        } else {
          render();
        }
      }
    }
    async function refreshDashboardIfStale() {
      if (!liveRefreshSupported || !apiToken || activeView === 'call') return;
      try {
        const params = new URLSearchParams({
          include_archived: includeArchived ? '1' : '0',
          _: String(Date.now()),
        });
        const response = await fetch(`/api/status?${params.toString()}`, {
          headers: {
            'Accept': 'application/json',
          },
          cache: 'no-store',
        });
        if (!response.ok) return;
        const payload = await response.json();
        const statusRefreshAt = payload.latest_refresh_at || '';
        const scopedRows = Number(payload.row_counts?.scoped_rows);
        const rowCountChanged = Number.isFinite(scopedRows) && scopedRows !== totalAvailableRows;
        const refreshChanged = statusRefreshAt && statusRefreshAt !== latestRefreshAt;
        if (rowCountChanged || refreshChanged) {
          refreshDashboardData(false, { refreshLogs: false, resetRows: true });
        } else if (rowsNeedHydration()) {
          hydrateDashboardRows();
        }
      } catch (_error) {
        // Background freshness checks must never interrupt the local dashboard.
      }
    }
    async function refreshDashboardData(manual = false, options = null) {
      if (!liveRefreshSupported) {
        updateLiveStatus('status.reloading', t('live.reloading_static'));
        window.location.reload();
        return;
      }
      if (activeView === 'call' && !manual) return;
      if (refreshInFlight) return;
      const refreshOptions = options || {};
      const refreshLogs = refreshOptions.refreshLogs === undefined ? manual : Boolean(refreshOptions.refreshLogs);
      const resetRows = refreshOptions.resetRows !== undefined
        ? Boolean(refreshOptions.resetRows)
        : Boolean(manual || refreshLogs);
      refreshInFlight = true;
      refreshDashboardEl.disabled = true;
      updateLiveStatus(refreshLogs ? 'status.refreshing' : 'status.checking', refreshLogs ? t('live.refreshing_index') : t('live.checking_usage'));
      try {
        const params = new URLSearchParams({
          limit: loadLimitEl.value,
          include_archived: includeArchived ? '1' : '0',
          lang: i18n.currentLanguage,
          shell: '1',
          _: String(Date.now()),
        });
        if (refreshLogs) params.set('refresh', '1');
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
        if (resetRows) {
          data = [];
          supplementalRowsByRecordId = new Map();
          rowHydrationGeneration += 1;
          rowHydrationComplete = false;
        }
        applyDashboardPayload(nextPayload);
        if (activeView !== 'call') hydrateDashboardRows({ reset: resetRows });
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
      if (!autoRefreshEl.checked || !liveRefreshSupported || activeView === 'call') return;
      autoRefreshTimer = window.setInterval(() => {
        if (document.visibilityState === 'visible') refreshDashboardIfStale();
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
        refreshDashboardData(false, { refreshLogs: false, resetRows: true });
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
        refreshDashboardData(false, { refreshLogs: false, resetRows: true });
      } else {
        updateLiveStatus('status.static', t('live.history_static_hint'));
      }
    });
    autoRefreshEl.addEventListener('change', () => {
      scheduleAutoRefresh();
      updateLiveStatus(autoRefreshEl.checked ? 'badge.live' : 'status.paused', `${autoRefreshEl.checked ? tf('live.every', { seconds: liveRefreshIntervalMs / 1000 }) : t('live.paused')}. ${loadedRowsDescription()}. ${historyRowsDescription()}`);
      if (autoRefreshEl.checked) refreshDashboardIfStale();
    });
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && autoRefreshEl.checked) refreshDashboardIfStale();
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
      const dashboardRoute = event.target.closest('[data-dashboard-route]');
      if (dashboardRoute && rowsEl.contains(dashboardRoute)) {
        event.preventDefault();
        event.stopPropagation();
        routeBackToDashboard(dashboardRoute.dataset.dashboardRoute || 'calls');
        return;
      }
      const rowLink = event.target.closest('a.row-investigator-link');
      if (rowLink && rowsEl.contains(rowLink)) {
        if (!liveRefreshSupported) return;
        event.preventDefault();
        event.stopPropagation();
        openInvestigatorUrl(rowLink.href);
        return;
      }
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
        navigateToCallRecord(recordId);
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
      const callRow = event.target.closest('.call-row, .thread-call-row');
      if (!callRow || !rowsEl.contains(callRow)) return;
      event.preventDefault();
      event.stopPropagation();
      const row = rowByRecordId.get(callRow.dataset.recordId);
      if (row) openInvestigator(row);
    });
    rowsEl.addEventListener('dblclick', event => {
      const callRow = event.target.closest('.call-row, .thread-call-row');
      if (!callRow || !rowsEl.contains(callRow)) return;
      event.preventDefault();
      event.stopPropagation();
    });
    rowsEl.addEventListener('keydown', event => {
      if (event.target.closest('a.row-investigator-link')) return;
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const callRow = event.target.closest('.call-row, .thread-call-row');
      if (!callRow || !rowsEl.contains(callRow)) return;
      event.preventDefault();
      const row = rowByRecordId.get(callRow.dataset.recordId);
      if (row) openInvestigator(row);
    });
    if (detailToggleEl) detailToggleEl.addEventListener('click', () => setDetailPanelExpanded(!detailPanelExpanded));
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
    if (!initialPayload.investigator_boot) dashboardPayloadCache.writeAggregatePayloadCache(activeInitialPayload);
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
    } else if (activeView === 'call') {
      autoRefreshEl.checked = false;
      updateLiveStatus('badge.live', `${t('dashboard.view.call')}. ${loadedRowsDescription()}. ${historyRowsDescription()}`);
    } else {
      updateLiveStatus('badge.live', `${tf('live.every', { seconds: liveRefreshIntervalMs / 1000 })}. ${loadedRowsDescription()}. ${historyRowsDescription()}`);
      scheduleAutoRefresh();
      if (needsInitialHistoryRefresh) {
        refreshDashboardData(false, { refreshLogs: false, resetRows: true });
      } else if (rowsNeedHydration()) {
        hydrateDashboardRows();
      } else if (restoredAggregatePayloadFromCache) {
        refreshDashboardIfStale();
      }
    }
    updateToTopVisibility();
    render();
