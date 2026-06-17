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
    const dashboardActionsFactory = window.CodexUsageDashboardActions;
    const dashboardEventsFactory = window.CodexUsageDashboardEvents;
    const dashboardLiveFactory = window.CodexUsageDashboardLive;
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
      compactListSummary,
      rowInputTokens: dataRowInputTokens,
      cachedInputTokens: dataCachedInputTokens,
      uncachedInputTokens: dataUncachedInputTokens,
      outputTokens: dataOutputTokens,
      rowReasoningTokens: dataRowReasoningTokens,
      threadModelSummary,
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
    function translationOrFallback(key, fallback) {
      const translated = t(key);
      return translated === key ? fallback : translated;
    }
    const stateManager = window.CodexUsageDashboardState;
    const urlParams = new URLSearchParams(window.location.search);
    const initialState = stateManager ? stateManager.read(urlParams) : {};
    let data = payloadRows(activeInitialPayload);
    let summaryData = activeInitialPayload.summary || null;
    let pricingConfigured = Boolean(activeInitialPayload.pricing_configured);
    let pricingSource = activeInitialPayload.pricing_source || {};
    let pricingSnapshotWarning = activeInitialPayload.pricing_snapshot_warning || '';
    let latestRefreshAt = activeInitialPayload.latest_refresh_at || '';
    let allowanceConfigured = Boolean(activeInitialPayload.allowance_configured);
    let allowanceSource = activeInitialPayload.allowance_source || {};
    let allowanceWindows = Array.isArray(activeInitialPayload.allowance_windows) ? activeInitialPayload.allowance_windows : [];
    let allowanceError = activeInitialPayload.allowance_error || '';
    let observedUsage = activeInitialPayload.observed_usage || {};
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
    const tableColgroupEl = document.getElementById('tableColgroup');
    const tableHeadEl = document.getElementById('tableHead');
    const insightsViewEl = document.getElementById('insightsView');
    const callsViewEl = document.getElementById('callsView');
    const threadsViewEl = document.getElementById('threadsView');
    const sessionsViewEl = document.getElementById('sessionsView');
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
    let activeView = ['calls', 'threads', 'insights', 'sessions', 'call'].includes(initialState.view) ? initialState.view : 'calls';
    document.body.dataset.activeView = activeView;
    let sortKey = optionValueExists(sortEl, initialState.sort) ? initialState.sort : sortEl.value || 'time';
    let sortDirection = ['asc', 'desc'].includes(initialState.direction) ? initialState.direction : defaultSortDirection(sortKey);
    const callSortKeys = new Set(['attention', 'cache', 'cached', 'context', 'cost', 'effort', 'initiator', 'model', 'output', 'reasoning', 'thread', 'time', 'total', 'uncached', 'usage', 'usage_impact']);
    const sessionSortKeys = new Set(['action', 'cache', 'calls', 'context', 'duration', 'ended', 'idle', 'largest_miss', 'started', 'thread', 'tokens', 'uncached']);
    let threadCallSortKey = 'time';
    let threadCallSortDirection = 'desc';
    let activePreset = '';
    let selectedRecordId = initialState.record || '';
    let selectedThreadKey = initialState.thread || '';
    const sessionPageSize = 500;
    let sessionFilter = initialState.sessionFilter || '';
    let sessionRows = [];
    let sessionRowsTotal = 0;
    let sessionsNextOffset = 0;
    let sessionsHasMore = false;
    let sessionsLoading = false;
    let sessionsError = '';
    let sessionsLoadedOnce = false;
    let sessionLoadScheduled = false;
    const expandedSessionIds = new Set();
    const sessionEpochs = new Map();
    const sessionEpochErrors = new Map();
    const sessionEpochLoading = new Set();
    const threadPageSize = 500;
    let threadRows = [];
    let threadRowsTotal = 0;
    let threadsNextOffset = 0;
    let threadsHasMore = false;
    let threadsLoading = false;
    let threadsError = '';
    let threadsLoadedOnce = false;
    let threadLoadScheduled = false;
    const threadCallsByKey = new Map();
    const threadCallLoading = new Set();
    const threadCallErrors = new Map();
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
        const key = element.dataset.i18n;
        const translated = t(key);
        element.textContent = translated === key
          ? (element.dataset.i18nFallback || element.textContent || key)
          : translated;
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
        const dateRange = currentDateRange();
        const groups = activeView === 'threads' && threadReadModelEligible(dateRange)
          ? threadRows.map(threadSummaryGroup)
          : groupThreads(filtered(dateRange));
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
    function ensureSortOption(key) {
      if (!sortEl || optionValueExists(sortEl, key)) return;
      const option = document.createElement('option');
      option.value = key;
      option.dataset.dynamicSortOption = 'true';
      option.textContent = sortLabelText(key);
      sortEl.appendChild(option);
    }
    function normalizeSortForView(view = activeView) {
      if (view === 'sessions') {
        if (!sessionSortKeys.has(sortKey)) {
          sortKey = 'uncached';
          sortDirection = defaultSortDirection(sortKey);
        }
        ensureSortOption(sortKey);
        sortEl.value = sortKey;
        return;
      }
      if (view !== 'call' && !callSortKeys.has(sortKey)) {
        sortKey = 'time';
        sortDirection = defaultSortDirection(sortKey);
      }
      ensureSortOption(sortKey);
      sortEl.value = sortKey;
    }
    function resetSessionRows() {
      sessionRows = [];
      sessionRowsTotal = 0;
      sessionsNextOffset = 0;
      sessionsHasMore = false;
      sessionsError = '';
      sessionsLoadedOnce = false;
      expandedSessionIds.clear();
      sessionEpochs.clear();
      sessionEpochErrors.clear();
      sessionEpochLoading.clear();
    }
    function resetThreadRows() {
      threadRows = [];
      threadRowsTotal = 0;
      threadsNextOffset = 0;
      threadsHasMore = false;
      threadsError = '';
      threadsLoadedOnce = false;
      threadLoadScheduled = false;
      threadCallsByKey.clear();
      threadCallLoading.clear();
      threadCallErrors.clear();
    }
    function threadApiSortKey() {
      const map = {
        attention: 'attention',
        cache: 'cache',
        cached: 'cached',
        context: 'context',
        cost: 'cost',
        effort: 'effort',
        initiator: 'initiator',
        model: 'model',
        output: 'output',
        reasoning: 'reasoning',
        thread: 'thread',
        time: 'time',
        total: 'tokens',
        tokens: 'tokens',
        uncached: 'uncached',
        usage: 'usage',
        usage_impact: 'usage_impact',
      };
      return map[sortKey] || 'tokens';
    }
    function threadReadModelEligible(dateRange = currentDateRange()) {
      return liveRefreshSupported
        && !modelEl.value
        && !effortEl.value
        && !pricingStatusEl.value
        && !activePreset
        && !dateRange.active
        && !dateRange.invalid;
    }
    function sessionFilterParams(params) {
      if (sessionFilter === 'cold') params.set('cold_resumes_only', '1');
      if (sessionFilter === 'high_uncached') params.set('high_uncached_only', '1');
      if (sessionFilter === 'needs_handoff') params.set('needs_handoff_only', '1');
      if (sessionFilter === 'recent') params.set('recent_only', '1');
    }
    async function loadSessions(options = null) {
      if (!liveRefreshSupported || !apiToken || activeView !== 'sessions') return;
      const loadOptions = options || {};
      if (sessionsLoading) return;
      sessionLoadScheduled = false;
      if (loadOptions.reset) resetSessionRows();
      sessionsLoading = true;
      sessionsError = '';
      render();
      try {
        const params = new URLSearchParams({
          limit: String(sessionPageSize),
          offset: String(sessionsNextOffset),
          include_archived: includeArchived ? '1' : '0',
          sort: sessionSortKeys.has(sortKey) ? sortKey : 'uncached',
          direction: sortDirection,
          lang: i18n.currentLanguage,
          _: String(Date.now()),
        });
        const query = searchEl.value.trim();
        if (query) params.set('q', query);
        sessionFilterParams(params);
        const response = await fetch(`/api/sessions?${params.toString()}`, {
          headers: {
            'Accept': 'application/json',
            'X-Codex-Usage-Token': apiToken,
          },
          cache: 'no-store',
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        if (payload.error) throw new Error(payload.error);
        const rows = Array.isArray(payload.rows) ? payload.rows : [];
        sessionRows = loadOptions.reset ? rows : sessionRows.concat(rows);
        sessionsNextOffset = Number(payload.offset || 0) + rows.length;
        sessionsHasMore = rows.length >= Number(payload.limit || sessionPageSize);
        sessionRowsTotal = sessionRows.length + (sessionsHasMore ? sessionPageSize : 0);
        sessionsLoadedOnce = true;
      } catch (error) {
        sessionsError = error.message || String(error);
      } finally {
        sessionsLoading = false;
        render();
      }
    }
    async function loadThreads(options = null) {
      if (!liveRefreshSupported || !apiToken || activeView !== 'threads' || !threadReadModelEligible()) return;
      const loadOptions = options || {};
      if (threadsLoading) return;
      threadLoadScheduled = false;
      if (loadOptions.reset) resetThreadRows();
      threadsLoading = true;
      threadsError = '';
      render();
      try {
        const params = new URLSearchParams({
          limit: String(threadPageSize),
          offset: String(threadsNextOffset),
          include_archived: includeArchived ? '1' : '0',
          sort: threadApiSortKey(),
          direction: sortDirection,
          lang: i18n.currentLanguage,
          _: String(Date.now()),
        });
        const query = searchEl.value.trim();
        if (query) params.set('q', query);
        const response = await fetch(`/api/threads?${params.toString()}`, {
          headers: {
            'Accept': 'application/json',
            'X-Codex-Usage-Token': apiToken,
          },
          cache: 'no-store',
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        if (payload.error) throw new Error(payload.error);
        const rows = Array.isArray(payload.rows) ? payload.rows : [];
        threadRows = loadOptions.reset ? rows : threadRows.concat(rows);
        threadsNextOffset = Number.isFinite(Number(payload.next_offset))
          ? Number(payload.next_offset)
          : Number(payload.offset || 0) + rows.length;
        threadsHasMore = Boolean(payload.has_more);
        threadRowsTotal = Number(payload.total_matched_rows ?? threadRows.length);
        threadsLoadedOnce = true;
      } catch (error) {
        threadsError = error.message || String(error);
      } finally {
        threadsLoading = false;
        render();
      }
    }
    async function loadThreadCalls(threadKey, options = null) {
      if (!liveRefreshSupported || !apiToken || activeView !== 'threads' || !threadKey) return;
      const existing = threadCallsByKey.get(threadKey) || { rows: [], nextOffset: 0, hasMore: true, total: 0 };
      const loadOptions = options || {};
      if (threadCallLoading.has(threadKey)) return;
      if (!loadOptions.reset && existing.rows.length && !existing.hasMore) return;
      const nextOffset = loadOptions.reset ? 0 : Number(existing.nextOffset || existing.rows.length || 0);
      threadCallLoading.add(threadKey);
      threadCallErrors.delete(threadKey);
      render();
      try {
        const params = new URLSearchParams({
          thread_key: threadKey,
          limit: String(threadCallPageSize),
          offset: String(nextOffset),
          include_archived: includeArchived ? '1' : '0',
          sort: threadCallSortKey,
          direction: threadCallSortDirection,
          lang: i18n.currentLanguage,
          _: String(Date.now()),
        });
        const response = await fetch(`/api/thread-calls?${params.toString()}`, {
          headers: {
            'Accept': 'application/json',
            'X-Codex-Usage-Token': apiToken,
          },
          cache: 'no-store',
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        if (payload.error) throw new Error(payload.error);
        const rows = Array.isArray(payload.rows) ? payload.rows : [];
        const previousRows = loadOptions.reset ? [] : existing.rows || [];
        threadCallsByKey.set(threadKey, {
          rows: mergedRows(previousRows, rows),
          nextOffset: Number.isFinite(Number(payload.next_offset))
            ? Number(payload.next_offset)
            : nextOffset + rows.length,
          hasMore: Boolean(payload.has_more),
          total: Number(payload.total_matched_rows ?? previousRows.length + rows.length),
        });
        rows.forEach(row => {
          if (row?.record_id) supplementalRowsByRecordId.set(row.record_id, row);
        });
        rebuildDashboardIndexes();
      } catch (error) {
        threadCallErrors.set(threadKey, error.message || String(error));
      } finally {
        threadCallLoading.delete(threadKey);
        render();
      }
    }
    async function loadSessionEpochs(workSessionId) {
      if (!liveRefreshSupported || !apiToken || !workSessionId) return;
      if (sessionEpochLoading.has(workSessionId) || sessionEpochs.has(workSessionId)) return;
      sessionEpochLoading.add(workSessionId);
      sessionEpochErrors.delete(workSessionId);
      render();
      try {
        const params = new URLSearchParams({
          work_session_id: workSessionId,
          limit: '0',
          sort: 'started',
          direction: 'asc',
          _: String(Date.now()),
        });
        const response = await fetch(`/api/context-epochs?${params.toString()}`, {
          headers: {
            'Accept': 'application/json',
            'X-Codex-Usage-Token': apiToken,
          },
          cache: 'no-store',
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        if (payload.error) throw new Error(payload.error);
        sessionEpochs.set(workSessionId, Array.isArray(payload.rows) ? payload.rows : []);
      } catch (error) {
        sessionEpochErrors.set(workSessionId, error.message || String(error));
      } finally {
        sessionEpochLoading.delete(workSessionId);
        render();
      }
    }
    function toggleSessionEpochs(workSessionId) {
      if (!workSessionId) return;
      if (expandedSessionIds.has(workSessionId)) {
        expandedSessionIds.delete(workSessionId);
        render();
        return;
      }
      expandedSessionIds.add(workSessionId);
      render();
      loadSessionEpochs(workSessionId);
    }
    function setSort(key, direction = null) {
      sortKey = key;
      sortDirection = direction || defaultSortDirection(key);
      resetVisibleRows();
      if (activeView === 'sessions') {
        resetSessionRows();
        normalizeSortForView();
        render();
        loadSessions({ reset: true });
        return;
      }
      if (activeView === 'threads') {
        resetThreadRows();
        normalizeSortForView();
        render();
        if (threadReadModelEligible()) loadThreads({ reset: true });
        return;
      }
      normalizeSortForView();
      render();
    }
    function handleHeaderSort(key) {
      if (sortKey === key) {
        sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
      } else {
        sortKey = key;
        sortDirection = defaultSortDirection(key);
      }
      resetVisibleRows();
      if (activeView === 'sessions') {
        resetSessionRows();
        normalizeSortForView();
        render();
        loadSessions({ reset: true });
        return;
      }
      if (activeView === 'threads') {
        resetThreadRows();
        normalizeSortForView();
        render();
        if (threadReadModelEligible()) loadThreads({ reset: true });
        return;
      }
      normalizeSortForView();
      render();
    }
    function updateSortControls() {
      normalizeSortForView();
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
        reasoning: t('metric.reasoning_output'),
        action: t('table.action'),
        calls: t('detail.calls'),
        duration: t('table.duration'),
        ended: t('table.ended'),
        idle: t('table.idle_before'),
        largest_miss: t('table.largest_miss'),
        started: t('table.started'),
        thread: t('table.thread'),
        time: t('table.time'),
        total: t('table.tokens'),
        tokens: t('table.tokens'),
        usage_impact: translationOrFallback('table.usage_impact', 'Usage'),
        usage: t('metric.codex_credits'),
      }[key] || t('filter.sort');
    }
    function moneyText(value) {
      return money(value, t('state.no_price'));
    }
    function creditsText(value) {
      return credits(value, t('state.no_rate'));
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
      const merged = [...existingRows];
      const indexesByRecordId = new Map();
      existingRows.forEach((row, index) => {
        if (row?.record_id) indexesByRecordId.set(row.record_id, index);
      });
      for (const row of nextRows) {
        if (!row?.record_id) continue;
        if (indexesByRecordId.has(row.record_id)) {
          const index = indexesByRecordId.get(row.record_id);
          merged[index] = { ...merged[index], ...row };
          continue;
        }
        indexesByRecordId.set(row.record_id, merged.length);
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
      allowanceReconcileElement: document.getElementById('allowanceReconcile'),
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
      getObservedUsage: () => observedUsage,
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
    const dashboardLive = dashboardLiveFactory.create({
      activeView: () => activeView,
      apiToken: () => apiToken,
      applyDashboardPayload,
      autoRefreshEl,
      backgroundHydrationChunkSize,
      formatTimestamp,
      getArchivedAvailableRows: () => archivedAvailableRows,
      getData: () => data,
      getIncludeArchived: () => includeArchived,
      getLoadedLimit: () => loadedLimit,
      getTotalAvailableRows: () => totalAvailableRows,
      historyScopeEl,
      i18n,
      initialHydrationChunkSize,
      limitValue,
      liveRefreshIntervalMs,
      liveRefreshSupported,
      loadLimitEl,
      number,
      payloadRows,
      rebuildDashboardIndexes,
      rebuildFilterOptions,
      refreshDashboardEl,
      refreshSessions,
      refreshThreads,
      render,
      resetRowsForHydration: () => {
        data = [];
        supplementalRowsByRecordId = new Map();
      },
      rowLoadProgressBarEl,
      rowLoadProgressCountEl,
      rowLoadProgressEl,
      rowLoadProgressLabelEl,
      setFastTooltip,
      setObservedUsage: value => {
        observedUsage = value || {};
        const dateRange = updateDateFilterControls();
        const rows = filtered(dateRange);
        const shellSummary = summaryForCards(dateRange, rows);
        const usageCredits = shellSummary ? shellSummary.usageCredits : sumUsageCredits(rows);
        updateAllowanceImpact(usageCredits);
      },
      t,
      tf,
      threadsUseReadModel: () => activeView === 'threads' && threadReadModelEligible(),
      updateLiveStatus,
    });
    const {
      historyRowsDescription,
      hydrateDashboardRows,
      loadedRowsDescription,
      refreshDashboardData,
      refreshDashboardIfStale,
      rowHydrationTarget,
      rowsNeedHydration,
      scheduleAutoRefresh,
      updateHistoryScopeControl,
      updateLoadLimitControl,
      updateRowLoadProgress,
    } = dashboardLive;
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
      if (initialState.sort) {
        sortKey = initialState.sort;
        ensureSortOption(sortKey);
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
      if (activeView === 'threads') resetThreadRows();
      queueFocusTarget(focusTarget);
      render();
      if (activeView === 'threads' && threadReadModelEligible()) loadThreads({ reset: true });
    }
    function clearPreset() {
      activePreset = '';
      pricingStatusEl.value = '';
      sortKey = 'time';
      sortDirection = defaultSortDirection(sortKey);
      sortEl.value = sortKey;
      resetVisibleRows();
      if (activeView === 'threads') resetThreadRows();
      render();
      if (activeView === 'threads' && threadReadModelEligible()) loadThreads({ reset: true });
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
      sourceLabelText,
      threadInitiatorSummary,
      tokenNumberCell,
      totalTokenCell,
      uncachedInputTokens,
      uncachedTokenCell,
      usageImpactCell,
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
    const dashboardActions = dashboardActionsFactory.create({
      actionStatusEl,
      apiToken: () => apiToken,
      callInitiator,
      currentPage: () => currentPage,
      dateEndEl,
      datePresetEl,
      dateStartEl,
      effortEl,
      escapeHtml,
      expandedThreads,
      filtered,
      getActivePreset: () => activePreset,
      getActiveView: () => activeView,
      getIncludeArchived: () => includeArchived,
      getSelectedRecordId: () => selectedRecordId,
      getSelectedThreadKey: () => selectedThreadKey,
      getSessionFilter: () => sessionFilter,
      getSessionRows: () => sessionRows,
      getSortDirection: () => sortDirection,
      getSortKey: () => sortKey,
      liveRefreshSupported,
      modelEl,
      number,
      pricingStatusEl,
      recommendationSummary,
      rowAttachment,
      rowThreadLabel,
      searchEl,
      stateManager,
      t,
      tf,
      usageCreditValue,
    });
    const {
      copyCallLink,
      copyCurrentViewLink,
      exportCurrentRows,
      openInvestigator,
      openInvestigatorUrl,
      rowInvestigatorLink,
      syncUrlState,
      tableUrlForRow,
    } = dashboardActions;
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
    function threadSummaryGroup(row) {
      const key = String(row.thread_key || '');
      const childState = threadCallsByKey.get(key) || {};
      const calls = Array.isArray(childState.rows) ? childState.rows : [];
      const modelSummary = calls.length ? threadModelSummary(calls) : t('state.unknown');
      const effortValues = calls.map(call => call.effort);
      const effortSummary = calls.length
        ? compactListSummary(effortValues, t('table.more_efforts'))
        : t('state.unknown');
      const effortTooltip = calls.length ? effortTooltipText(effortValues) : t('state.unknown');
      return {
        key,
        label: row.thread_label || key || t('state.unknown'),
        calls,
        callCount: Number(row.call_count || calls.length || 0),
        latestActivity: row.latest_event_timestamp || row.first_event_timestamp || '',
        parentThreadLabel: '',
        modelSummary,
        effortSummary,
        effortTooltip,
        totalTokens: Number(row.total_tokens || 0),
        cachedTokens: Number(row.cached_input_tokens || 0),
        uncachedTokens: Number(row.uncached_input_tokens || 0),
        outputTokens: Number(row.output_tokens || 0),
        reasoningOutputTokens: Number(row.reasoning_output_tokens || 0),
        estimatedCost: Number(row.estimated_cost_usd || 0),
        usageCredits: Number(row.usage_credits || 0),
        usage_impact: null,
        cacheRatio: Number(row.avg_cache_ratio || 0),
        maxContextUse: Number(row.max_context_window_percent || 0),
        pricingStatus: t('state.unknown'),
        creditStatus: t('state.unknown'),
        signalCount: 0,
        subagentCount: 0,
        autoReviewCount: 0,
        attachedCount: 0,
        lifecycle: null,
        attentionScore: Number(row.max_recommendation_score || 0),
        callInitiatorSummary: row.call_initiator_summary || '',
        callsLoading: threadCallLoading.has(key),
        callsError: threadCallErrors.get(key) || '',
        callsHasMore: Boolean(childState.hasMore),
        callsServerPaged: true,
        callsTotal: Number(childState.total || row.call_count || calls.length || 0),
      };
    }
    function threadReadModelLoadedDescription() {
      const total = threadRowsTotal || threadRows.length;
      return threadRows.length
        ? tf('table.visible_status', {
            end: number.format(threadRows.length),
            total: number.format(total),
            items: t('dashboard.view.threads'),
          })
        : loadedRowsDescription();
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
          body: t('call.cache_body_post_compaction'),
        };
      }
      if (diagnostic === 'cold') {
        return {
          key: 'cold',
          label: t('call.cache_cold'),
          body: t('call.cache_body_cold'),
        };
      }
      if (diagnostic === 'spike') {
        return {
          key: 'spike',
          label: t('call.cache_spike'),
          body: t('call.cache_body_spike'),
        };
      }
      if (diagnostic === 'warm') {
        return {
          key: 'warm',
          label: t('call.cache_warm'),
          body: t('call.cache_body_warm'),
        };
      }
      if (diagnostic === 'partial') {
        return {
          key: 'partial',
          label: t('call.cache_partial'),
          body: t('call.cache_body_partial'),
        };
      }
      return {
        key: 'cold',
        label: t('call.cache_cold'),
        body: t('call.cache_body_uncached'),
      };
    }
    function handleThreadCallHeaderSort(key) {
      if (threadCallSortKey === key) {
        threadCallSortDirection = threadCallSortDirection === 'asc' ? 'desc' : 'asc';
      } else {
        threadCallSortKey = key;
        threadCallSortDirection = key === 'time' || key === 'total' || key === 'cached' || key === 'uncached' || key === 'output' || key === 'reasoning' || key === 'usage_impact' || key === 'cost' || key === 'cache' ? 'desc' : 'asc';
      }
      if (activeView === 'threads' && threadReadModelEligible()) {
        threadCallsByKey.clear();
        threadCallErrors.clear();
        render();
        expandedThreads.forEach(threadKey => loadThreadCalls(threadKey, { reset: true }));
        return;
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
      getSessionFilter: () => sessionFilter,
      getSortDirection: () => sortDirection,
      getSortKey: () => sortKey,
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
      tableColgroupEl,
      tableHeadEl,
      tableTitleEl,
      t,
      tf,
      threadCallPageSize,
      threadInitiatorSummary,
      toggleThread,
      tokenNumberCell,
      tooltipAttributes,
      totalTokenCell,
      translateEffort,
      truncate,
      uncachedTokenCell,
      updateLoadMoreControl,
      usageImpactCell,
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
      if (activeView === 'threads') resetThreadRows();
      queueFocusTarget(insight.target);
      render();
      if (activeView === 'threads' && threadReadModelEligible()) loadThreads({ reset: true });
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
        insightsViewEl.setAttribute('aria-pressed', 'false');
        callsViewEl.setAttribute('aria-pressed', 'false');
        threadsViewEl.setAttribute('aria-pressed', 'false');
        sessionsViewEl.setAttribute('aria-pressed', 'false');
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
      sessionsViewEl.setAttribute('aria-pressed', activeView === 'sessions' ? 'true' : 'false');
      renderInsightPanel(rows);
      if (activeView === 'call') {
        callInvestigator.renderCallInvestigator(rows);
      } else if (activeView === 'sessions') {
        const sessionTotal = sessionRowsTotal || sessionRows.length;
        dashboardTables.renderSessions({
          rows: sessionRows,
          loading: sessionsLoading,
          error: sessionsError,
          total: sessionTotal,
          expandedSessionIds,
          sessionEpochErrors,
          sessionEpochLoading,
          sessionEpochs,
          loadedDescription: sessionRows.length
            ? tf('table.visible_status', {
                end: number.format(sessionRows.length),
                total: number.format(sessionTotal),
                items: t('table.sessions'),
              })
            : loadedRowsDescription(),
        });
        if (!sessionsLoading && !sessionsError && !sessionsLoadedOnce && !sessionRows.length) {
          if (!sessionLoadScheduled) {
            sessionLoadScheduled = true;
            window.setTimeout(() => loadSessions({ reset: true }), 0);
          }
        }
      } else if (activeView === 'threads') {
        if (threadReadModelEligible(dateRange)) {
          renderReadModelThreads();
        } else {
          renderThreads(rows);
        }
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
    function renderReadModelThreads() {
      const groups = threadRows.map(threadSummaryGroup);
      dashboardTables.renderThreadGroups(groups, 'threads', {
        totalThreads: threadRowsTotal || groups.length,
        totalCalls: totalAvailableRows,
        loaded: threadReadModelLoadedDescription(),
        loading: threadsLoading,
        error: threadsError,
        serverPaged: true,
      });
      if (!threadsLoading && !threadsError && !threadsLoadedOnce && !threadRows.length && !threadLoadScheduled) {
        threadLoadScheduled = true;
        window.setTimeout(() => loadThreads({ reset: true }), 0);
      }
      for (const group of groups) {
        const childState = threadCallsByKey.get(group.key);
        if (
          expandedThreads.has(group.key)
          && !childState
          && !threadCallLoading.has(group.key)
          && !threadCallErrors.has(group.key)
        ) {
          window.setTimeout(() => loadThreadCalls(group.key, { reset: true }), 0);
        }
      }
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
    function handleFiltersChanged() {
      resetVisibleRows();
      if (activeView === 'sessions') {
        resetSessionRows();
        render();
        loadSessions({ reset: true });
        return;
      }
      if (activeView === 'threads') {
        resetThreadRows();
        render();
        if (threadReadModelEligible()) {
          loadThreads({ reset: true });
        } else if (rowsNeedHydration()) {
          hydrateDashboardRows();
        }
        return;
      }
      render();
    }
    function setSessionFilter(value) {
      const normalized = ['', 'cold', 'high_uncached', 'needs_handoff', 'recent'].includes(value) ? value : '';
      if (sessionFilter === normalized) return;
      sessionFilter = normalized;
      resetVisibleRows();
      resetSessionRows();
      render();
      if (activeView === 'sessions') loadSessions({ reset: true });
    }
    function refreshSessions() {
      resetSessionRows();
      render();
      loadSessions({ reset: true });
    }
    function refreshThreads() {
      resetThreadRows();
      render();
      if (activeView !== 'threads') return;
      if (threadReadModelEligible()) {
        loadThreads({ reset: true });
      } else if (rowsNeedHydration()) {
        hydrateDashboardRows({ reset: true });
      }
    }
    function toggleThread(group) {
      if (!group?.key) return;
      if (expandedThreads.has(group.key)) {
        expandedThreads.delete(group.key);
        selectThread(group);
        render();
        return;
      }
      expandedThreads.add(group.key);
      selectThread(group);
      render();
      if (activeView === 'threads' && threadReadModelEligible()) {
        loadThreadCalls(group.key, { reset: true });
      }
    }
    function setView(view) {
      activeView = ['calls', 'threads', 'insights', 'sessions', 'call'].includes(view) ? view : 'calls';
      normalizeSortForView();
      resetVisibleRows();
      render();
      if (activeView === 'threads' && threadReadModelEligible()) {
        loadThreads({ reset: !threadsLoadedOnce });
      } else if (!['call', 'sessions'].includes(activeView) && rowsNeedHydration()) {
        hydrateDashboardRows();
      }
    }
    async function routeBackToDashboard(view = 'calls') {
      activeView = ['calls', 'threads', 'insights', 'sessions'].includes(view) ? view : 'calls';
      normalizeSortForView();
      resetVisibleRows();
      if (liveRefreshSupported && !data.length) {
        autoRefreshEl.checked = true;
        await refreshDashboardData(false, { refreshLogs: false, resetRows: true });
      } else if (activeView === 'sessions' && !sessionRows.length) {
        render();
        await loadSessions({ reset: true });
      } else if (activeView === 'threads' && threadReadModelEligible() && !threadRows.length) {
        render();
        await loadThreads({ reset: true });
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
      const appendRows = Boolean(applyOptions.appendRows);
      if (i18n.updatePayload(nextPayload)) {
        populateLanguageOptions();
      }
      applyTranslations();
      const nextRows = payloadRows(nextPayload);
      if (appendRows) {
        data = mergedRows(data, nextRows);
      } else if (applyOptions.preserveRows) {
        data = data.length ? data : nextRows;
      } else {
        data = nextRows;
      }
      summaryData = nextPayload.summary || summaryData;
      if (!appendRows || Object.prototype.hasOwnProperty.call(nextPayload, 'pricing_configured')) {
        pricingConfigured = Boolean(nextPayload.pricing_configured);
      }
      pricingSource = nextPayload.pricing_source || pricingSource || {};
      pricingSnapshotWarning = nextPayload.pricing_snapshot_warning ?? pricingSnapshotWarning;
      if (!appendRows || Object.prototype.hasOwnProperty.call(nextPayload, 'allowance_configured')) {
        allowanceConfigured = Boolean(nextPayload.allowance_configured);
      }
      allowanceSource = nextPayload.allowance_source || allowanceSource || {};
      allowanceWindows = Array.isArray(nextPayload.allowance_windows) ? nextPayload.allowance_windows : allowanceWindows;
      allowanceError = nextPayload.allowance_error ?? allowanceError;
      observedUsage = nextPayload.observed_usage || observedUsage || {};
      rateCardError = nextPayload.rate_card_error ?? rateCardError;
      parserDiagnostics = nextPayload.parser_diagnostics || parserDiagnostics || {};
      projectMetadataPrivacy = nextPayload.project_metadata_privacy || projectMetadataPrivacy || { mode: nextPayload.privacy_mode || 'normal' };
      apiToken = nextPayload.api_token || apiToken;
      if (!appendRows || Object.prototype.hasOwnProperty.call(nextPayload, 'context_api_enabled')) {
        contextApiEnabled = Boolean(nextPayload.context_api_enabled);
      }
      actionThresholds = nextPayload.action_thresholds || actionThresholds;
      latestRefreshAt = nextPayload.latest_refresh_at || latestRefreshAt;
      if (nextPayload.total_available_rows !== undefined) {
        totalAvailableRows = Number(nextPayload.total_available_rows || data.length);
      }
      if (nextPayload.total_matched_rows !== undefined && !nextPayload.total_available_rows && totalAvailableRows < Number(nextPayload.total_matched_rows || 0)) {
        totalAvailableRows = Number(nextPayload.total_matched_rows || totalAvailableRows);
      }
      if (nextPayload.active_available_rows !== undefined) {
        activeAvailableRows = Number(nextPayload.active_available_rows || data.length);
      }
      if (nextPayload.all_history_available_rows !== undefined) {
        allHistoryAvailableRows = Number(nextPayload.all_history_available_rows || totalAvailableRows);
      }
      if (nextPayload.archived_available_rows !== undefined) {
        archivedAvailableRows = Number(nextPayload.archived_available_rows || Math.max(allHistoryAvailableRows - activeAvailableRows, 0));
      }
      if (Object.prototype.hasOwnProperty.call(nextPayload, 'include_archived')) {
        includeArchived = Boolean(nextPayload.include_archived);
      }
      if (!appendRows) loadedLimit = payloadLimit(nextPayload);
      if (!appendRows) supplementalRowsByRecordId = new Map();
      restoredAggregatePayloadFromCache = false;
      if (!nextPayload.shell_boot && !appendRows) {
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
      if (
        existing
        && Object.prototype.hasOwnProperty.call(existing, 'task_receipts')
        && Object.prototype.hasOwnProperty.call(existing, 'lifecycle_recommendations')
      ) return existing;
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
        payload.record.task_receipts = payload.task_receipts || { rows: [] };
        payload.record.lifecycle_recommendations = payload.lifecycle_recommendations || { rows: [] };
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
      handleFiltersChanged,
      handleThreadCallHeaderSort,
      hideFastTooltip,
      historyRowsDescription,
      historyScopeEl,
      incrementCurrentPage: () => {
        if (activeView === 'sessions') {
          if (sessionsHasMore) {
            loadSessions();
          } else {
            render();
          }
          return;
        }
        if (activeView === 'threads' && threadReadModelEligible()) {
          if (threadsHasMore) {
            loadThreads();
          } else {
            render();
          }
          return;
        }
        currentPage += 1;
        render();
      },
      incrementThreadCallVisiblePage: key => {
        if (activeView === 'threads' && threadReadModelEligible()) {
          const childState = threadCallsByKey.get(key);
          if (!childState || childState.hasMore) {
            loadThreadCalls(key);
            return;
          }
        }
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
      setIncludeArchived: value => {
        includeArchived = Boolean(value);
        if (activeView === 'sessions') resetSessionRows();
        if (activeView === 'threads') resetThreadRows();
      },
      setLanguage,
      setSessionFilter,
      setSort,
      setView,
      sortEl,
      syncDatePresetInputs,
      syncUrlState,
      tableHeadEl,
      t,
      tf,
      threadsViewEl,
      sessionsViewEl,
      toggleDetailPanel: () => setDetailPanelExpanded(!detailPanelExpanded),
      toggleSessionEpochs,
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
      } else if (activeView === 'threads' && threadReadModelEligible()) {
        loadThreads({ reset: true });
      } else if (rowsNeedHydration()) {
        hydrateDashboardRows();
      } else if (restoredAggregatePayloadFromCache) {
        refreshDashboardIfStale();
      }
    }
    updateToTopVisibility();
    render();
