    const dashboardFormat = window.CodexUsageDashboardFormat;
    const dashboardData = window.CodexUsageDashboardData;
    const dashboardFilters = window.CodexUsageDashboardFilters;
    const dashboardAnalysisFactory = window.CodexUsageDashboardAnalysis;
    const dashboardCellsFactory = window.CodexUsageDashboardCells;
    const dashboardDetailsFactory = window.CodexUsageDashboardDetails;
    const dashboardInsightsFactory = window.CodexUsageDashboardInsights;
    const dashboardTablesFactory = window.CodexUsageDashboardTables;
    const dashboardPayloadCache = window.CodexUsageDashboardPayloadCache;
    const dashboardTooltipFactory = window.CodexUsageDashboardTooltips;
    const dashboardStatusFactory = window.CodexUsageDashboardStatus;
    const dashboardEventsFactory = window.CodexUsageDashboardEvents;
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
    let dashboardStatus = null;
    const dashboardInsights = dashboardInsightsFactory.create({
      allowanceWindowText,
      applyPreset,
      clearPresetEl,
      clamp,
      creditCoverageRatio,
      credits,
      escapeHtml,
      groupThreads,
      insightCardsEl,
      insightsPanelEl,
      moneyText,
      number,
      onInsightActivated,
      pct,
      presetListEl,
      presetStatusEl,
      pricingConfigured: () => pricingConfigured,
      rowAttentionScore,
      rowThreadLabel,
      severityForScore,
      sumUsageCredits,
      t,
      tf,
      threshold,
      usageCreditValue,
    });
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
    dashboardStatus = dashboardStatusFactory.create({
      allowanceImpactElement: document.getElementById('allowanceImpact'),
      allowanceSourceElement: document.getElementById('allowanceSource'),
      creditCoverageRatio,
      credits,
      formatTimestamp,
      formatTimestampTitle,
      getAllowanceConfigured: () => allowanceConfigured,
      getAllowanceError: () => allowanceError,
      getAllowanceSource: () => allowanceSource,
      getAllowanceWindows: () => allowanceWindows,
      getData: () => data,
      getParserDiagnostics: () => parserDiagnostics,
      getPricingConfigured: () => pricingConfigured,
      getPricingSnapshotWarning: () => pricingSnapshotWarning,
      getPricingSource: () => pricingSource,
      getProjectMetadataPrivacy: () => projectMetadataPrivacy,
      getRateCardError: () => rateCardError,
      liveStatusElement: liveStatusEl,
      number,
      parserDiagnosticsElement: document.getElementById('parserDiagnostics'),
      pct,
      pricingSourceElement: document.getElementById('pricingSource'),
      privacyModeElement: document.getElementById('privacyMode'),
      setFastTooltip,
      short,
      t,
      tf,
      usageCreditValue,
    });
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
      return dashboardStatus.allowanceWindowText(totalCredits, mode);
    }
    function allowanceImpactText(totalCredits) {
      return dashboardStatus.allowanceImpactText(totalCredits);
    }
    function rowAllowanceImpact(row) {
      return dashboardStatus.rowAllowanceImpact(row);
    }
    function updateAllowanceImpact(totalCredits) {
      dashboardStatus.updateAllowanceImpact(totalCredits);
    }
    function updateAllowanceSourceLine() {
      dashboardStatus.updateAllowanceSourceLine();
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
      if (dashboardInsights.hasPreset(initialState.preset)) activePreset = initialState.preset;
      if (initialState.page && Number(initialState.page) > 1) currentPage = Number(initialState.page);
      if (Array.isArray(initialState.expandedThreads)) {
        initialState.expandedThreads.forEach(key => expandedThreads.add(key));
      }
      if (initialState.expandedThreads && initialState.expandedThreads.length) {
        initialThreadExpansionApplied = true;
      }
    }
    function updatePricingSourceLine() {
      dashboardStatus.updatePricingSourceLine();
    }
    function updateParserDiagnosticsLine() {
      dashboardStatus.updateParserDiagnosticsLine();
    }
    function updatePrivacyModeLine() {
      dashboardStatus.updatePrivacyModeLine();
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
      return dashboardInsights.activePresetDefinition(activePreset);
    }
    function presetMatchesRow(row) {
      return dashboardInsights.presetMatchesRow(row, activePreset);
    }
    function applyPreset(key, focusTarget = null) {
      const preset = dashboardInsights.activePresetDefinition(key);
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
    const dashboardTables = dashboardTablesFactory.create({
      activePresetDefinition,
      callInitiatorCell,
      cachedTokenCell,
      costUsageCell,
      dateCaptionPrefix,
      effortCell,
      ensurePendingFocusVisibleInGroups,
      ensurePendingFocusVisibleInRows,
      escapeHtml,
      expandedThreads,
      getActiveView: () => activeView,
      getInitialDetailApplied: () => initialDetailApplied,
      getInitialThreadExpansionApplied: () => initialThreadExpansionApplied,
      getPricingConfigured: () => pricingConfigured,
      getSelectedRecordId: () => selectedRecordId,
      getSelectedThreadKey: () => selectedThreadKey,
      getThreadCallSortDirection: () => threadCallSortDirection,
      getThreadCallSortKey: () => threadCallSortKey,
      getThreadCallVisiblePages: () => threadCallVisiblePages,
      groupThreads,
      initialUrlParams: urlParams,
      loadedRowsDescription,
      moneyText,
      number,
      outputTokenCell,
      pct,
      renderSignalPucks,
      renderTimeCell,
      renderWithState: () => render(),
      rowInvestigatorLink,
      rowThreadLabel,
      rowsEl,
      rowsNeedHydration,
      selectThread,
      setInitialDetailApplied: value => { initialDetailApplied = Boolean(value); },
      setInitialThreadExpansionApplied: value => { initialThreadExpansionApplied = Boolean(value); },
      short,
      showDetail,
      showThreadDetail,
      sortedThreadCalls,
      tableCaptionEl,
      tableTitleEl,
      t,
      tf,
      threadCallPageSize,
      threadInitiatorSummary,
      tokenNumberCell,
      totalTokenCell,
      translateEffort,
      truncate,
      uncachedTokenCell,
      updateLoadMoreControl,
      usageCreditValue,
      visibleSlice,
    });
    function onInsightActivated(insight) {
      activeView = insight.view || 'calls';
      if (insight.sort) {
        sortKey = insight.sort;
        sortDirection = defaultSortDirection(insight.sort);
        sortEl.value = sortKey;
      }
      resetVisibleRows();
      queueFocusTarget(insight.target);
      render();
    }
    function renderInsightPanel(rows) {
      dashboardInsights.renderInsightPanel(rows, activeView, activePreset);
    }
    function renderPresetControls() {
      dashboardInsights.renderPresetControls(activePreset);
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
      updateAllowanceImpact(usageCredits);
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
      dashboardTables.renderCalls(rows);
    }
    function renderThreads(rows, mode = 'threads') {
      dashboardTables.renderThreads(rows, mode);
    }
    function renderThreadCalls(group) {
      return dashboardTables.renderThreadCalls(group);
    }
    let callInvestigator = null;
    const dashboardDetails = dashboardDetailsFactory.create({
      allowanceWindowText,
      attachmentRelationText,
      callInitiatorPuck,
      callInitiatorText,
      copyCallLink,
      credits,
      detailEl,
      escapeHtml,
      formatTimestamp,
      getActiveView: () => activeView,
      getCallInvestigator: () => callInvestigator,
      isPricingConfigured: () => pricingConfigured,
      moneyText,
      number,
      openInvestigator,
      pct,
      recommendationSummary,
      resolvedParentSessionUpdatedAt,
      resolvedParentThreadName,
      rowAllowanceImpact,
      rowAttachment,
      short,
      sourceLabelText,
      t,
      tf,
      threshold,
      translateEfficiencyFlag,
      translatedField,
      usageCreditStatusLabel,
      usageCreditValue,
      usageCreditsWithStatus,
    });
    function pricingStatusText(row) {
      return dashboardDetails.pricingStatusText(row);
    }
    function showDetail(row) {
      dashboardDetails.showDetail(row);
    }
    function showThreadDetail(group) {
      dashboardDetails.showThreadDetail(group);
    }
    function selectRow(row) {
      selectedRecordId = row.record_id || '';
      selectedThreadKey = '';
      showDetail(row);
      syncUrlState();
    }
    function selectThread(group) {
      selectedThreadKey = group.key || '';
      selectedRecordId = '';
      showThreadDetail(group);
      syncUrlState();
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
      dashboardStatus.renderLiveStatus();
    }
    function updateLiveStatus(statusKey, detail = '') {
      dashboardStatus.updateLiveStatus(statusKey, detail);
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
    callInvestigator = window.CodexUsageCallInvestigator.create({
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
    dashboardEventsFactory.bind({
      autoRefreshEl,
      callsViewEl,
      clearPreset,
      clearPresetEl,
      cleanDateInput,
      closestFastTooltipTarget,
      copyCallLink,
      copyCurrentViewLink,
      copyViewLinkEl,
      dateEndEl,
      datePresetEl,
      dateStartEl,
      defaultSortDirection,
      detailToggleEl,
      effortEl,
      exportCurrentRows,
      exportVisibleEl,
      getRowByRecordId: recordId => rowByRecordId.get(recordId),
      handleHeaderSort,
      handleThreadCallHeaderSort,
      hideFastTooltip,
      historyRowsDescription,
      historyScopeEl,
      incrementCurrentPage: () => {
        currentPage += 1;
        render();
      },
      incrementThreadCallVisiblePage: key => {
        threadCallVisiblePages.set(key, Math.max(1, threadCallVisiblePages.get(key) || 1) + 1);
      },
      insightsViewEl,
      languageSelectEl,
      liveRefreshIntervalMs,
      liveRefreshSupported,
      loadLimitEl,
      loadedRowsDescription,
      loadMoreRowsEl,
      modelEl,
      navigateToCallRecord,
      openInvestigator,
      openInvestigatorUrl,
      pricingStatusEl,
      refreshDashboardData,
      refreshDashboardEl,
      refreshDashboardIfStale,
      render,
      resetVisibleRows,
      routeBackToDashboard,
      rowsEl,
      scheduleAutoRefresh,
      scheduleFastTooltip,
      searchEl,
      selectRow,
      setIncludeArchived: value => { includeArchived = Boolean(value); },
      setLanguage,
      setSort,
      setView,
      sortEl,
      syncDatePresetInputs,
      syncUrlState,
      t,
      tf,
      threadsViewEl,
      toggleDetailPanel: () => setDetailPanelExpanded(!detailPanelExpanded),
      toTopEl,
      updateHistoryScopeControl,
      updateLiveStatus,
      updateToTopVisibility,
    });
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
