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
      compactListSummary,
      threadModelSummary,
    } = dashboardData;
    const initialPayload = JSON.parse(document.getElementById('usage-data').textContent);
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
    const liveStatusEl = document.getElementById('liveStatus');
    const copyViewLinkEl = document.getElementById('copyViewLink');
    const exportVisibleEl = document.getElementById('exportVisible');
    const actionStatusEl = document.getElementById('actionStatus');
    const prevPageEl = document.getElementById('prevPage');
    const nextPageEl = document.getElementById('nextPage');
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
    const datePresetLabels = {
      all: 'All time',
      today: 'Today',
      'this-week': 'This week',
      'last-7-days': 'Last 7 days',
      'this-month': 'This month',
      custom: 'Custom range',
    };
    const allowedDatePresets = new Set(Object.keys(datePresetLabels));
    let activeView = ['calls', 'threads', 'insights'].includes(initialState.view) ? initialState.view : 'insights';
    let sortKey = optionValueExists(sortEl, initialState.sort) ? initialState.sort : sortEl.value || 'attention';
    let sortDirection = ['asc', 'desc'].includes(initialState.direction) ? initialState.direction : defaultSortDirection(sortKey);
    let activePreset = '';
    let selectedRecordId = initialState.record || '';
    let selectedThreadKey = initialState.thread || '';
    let refreshInFlight = false;
    let autoRefreshTimer = null;
    let currentPage = 1;
    let initialThreadExpansionApplied = false;
    let initialDetailApplied = false;
    const presetDefinitions = [
      {
        key: 'highest-cost',
        label: 'Highest-cost threads',
        description: 'Threads sorted by estimated spend, with subagents attached.',
        view: 'threads',
        sort: 'cost',
        direction: 'desc',
        caption: 'Highest-cost threads preset',
        matches: () => true,
      },
      {
        key: 'context-bloat',
        label: 'Context bloat',
        description: 'Calls over 60% context use or with very high cumulative tokens.',
        view: 'calls',
        sort: 'context',
        direction: 'desc',
        caption: 'Context bloat preset',
        matches: row => Number(row.context_window_percent || 0) >= threshold('high_context_percent', 0.6) || Number(row.cumulative_total_tokens || 0) >= threshold('large_cumulative_tokens', 200000),
      },
      {
        key: 'cache-misses',
        label: 'Cache misses',
        description: 'Low cache-ratio calls grouped by cwd, model, and thread.',
        view: 'calls',
        sort: 'cache',
        direction: 'asc',
        caption: 'Cache misses preset',
        matches: row => Number(row.input_tokens || 0) > 0 && Number(row.cache_ratio || 0) < threshold('low_cache_ratio', 0.3),
      },
      {
        key: 'pricing-gaps',
        label: 'Pricing gaps',
        description: 'Unpriced usage that makes estimated cost totals incomplete.',
        view: 'calls',
        sort: 'total',
        direction: 'desc',
        pricingStatus: 'unpriced',
        caption: 'Pricing gaps preset',
        matches: row => !row.pricing_model,
      },
      {
        key: 'estimated-review',
        label: 'Estimated-price review',
        description: 'Usage priced with marked best-guess estimates.',
        view: 'calls',
        sort: 'cost',
        direction: 'desc',
        pricingStatus: 'estimated',
        caption: 'Estimated-price review preset',
        matches: row => Boolean(row.pricing_estimated),
      },
      {
        key: 'usage-credits',
        label: 'Highest Codex credits',
        description: 'Calls sorted by estimated impact on Codex usage allowance.',
        view: 'calls',
        sort: 'usage',
        direction: 'desc',
        caption: 'Highest Codex credits preset',
        matches: row => Number(row.usage_credits || 0) > 0,
      },
    ];
    function directional(compareResult) {
      return sortDirection === 'asc' ? compareResult : -compareResult;
    }
    function setSort(key, direction = null) {
      sortKey = key;
      sortDirection = direction || defaultSortDirection(key);
      sortEl.value = key;
      currentPage = 1;
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
      currentPage = 1;
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
      tableCaptionEl.dataset.sortDescription = `${sortLabel(sortKey)} ${sortDirection === 'asc' ? 'ascending' : 'descending'}`;
    }
    function loadedRowsDescription() {
      const loaded = number.format(data.length);
      const available = number.format(totalAvailableRows || data.length);
      const capped = loadedLimit !== null && totalAvailableRows > data.length;
      return capped ? `${loaded} of ${available} calls loaded` : `${loaded} calls loaded`;
    }
    function historyRowsDescription() {
      const archived = Number(archivedAvailableRows || 0);
      if (includeArchived) {
        return archived
          ? `All history includes ${number.format(archived)} archived calls`
          : 'All history selected; no archived calls are indexed yet';
      }
      return archived
        ? `Active sessions only; ${number.format(archived)} archived calls hidden`
        : 'Active sessions only';
    }
    function updateHistoryScopeControl() {
      historyScopeEl.value = includeArchived ? 'all' : 'active';
      const detail = historyRowsDescription();
      historyScopeEl.title = detail;
      historyScopeEl.parentElement.title = `${detail}. Archived sessions are scanned only when All history is selected during live refresh.`;
    }
    function updateLoadLimitControl() {
      const value = limitValue(loadedLimit);
      const existing = new Set(Array.from(loadLimitEl.options).map(option => option.value));
      if (!existing.has(value)) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = `${number.format(loadedLimit)} calls`;
        loadLimitEl.insertBefore(option, loadLimitEl.lastElementChild);
      }
      loadLimitEl.value = value;
    }
    function rebuildDashboardIndexes() {
      rowByRecordId = new Map(data.map(row => [row.record_id, row]));
      threadAttachmentByRecordId = new Map(data.map(row => [row.record_id, resolveThreadAttachment(row)]));
    }
    function usageCreditsWithStatus(row) {
      const value = usageCreditValue(row);
      return value === null ? 'No mapped rate' : `${credits(value)} credits · ${usageCreditStatusText(row)}`;
    }
    function costUsageCell(costText, creditValue) {
      const usage = creditValue === null || creditValue === undefined ? 'No credit rate' : `${credits(creditValue)} cr`;
      return `<span class="metric-stack"><span>${escapeHtml(costText)}</span><span class="metric-sub">${escapeHtml(usage)}</span></span>`;
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
          return `${label} ${credits(remainingCredits)} cr left`;
        }
        if (mode === 'impact' && total > 0) {
          return `${label} ${pct(totalCredits / total)} of allowance`;
        }
        if (mode === 'impact' && remainingCredits !== null && Number.isFinite(remainingCredits)) {
          return `${label} ${credits(totalCredits)} used vs ${credits(remainingCredits)} remaining`;
        }
        if (remainingPercent !== null && Number.isFinite(remainingPercent)) {
          return `${label} ${pct(remainingPercent)} remaining`;
        }
        if (remainingCredits !== null && Number.isFinite(remainingCredits)) {
          return `${label} ${credits(remainingCredits)} credits remaining`;
        }
        if (total > 0) {
          return `${label} ${credits(totalCredits)} of ${credits(total)} credits`;
        }
        return `${label} configured`;
      });
      return labels.join(mode === 'remaining-card' ? '\n' : ' · ');
    }
    function allowanceImpactText(totalCredits) {
      const windowImpact = allowanceWindowText(totalCredits, 'remaining-card') || allowanceWindowText(totalCredits, 'impact');
      if (windowImpact) return windowImpact;
      if (allowanceError) return 'Allowance config error';
      return allowanceConfigured ? 'Allowance configured' : 'Set limits';
    }
    function rowAllowanceImpact(row) {
      const value = usageCreditValue(row);
      if (value === null) return 'No mapped Codex credit rate';
      const impact = allowanceWindowText(value, 'impact');
      return impact || `${credits(value)} credits counted toward Codex usage limits`;
    }
    function updateAllowanceSourceLine() {
      const sourceEl = document.getElementById('allowanceSource');
      const sourceName = allowanceSource.name || 'Codex credit rates';
      const coverage = creditCoverageRatio(data);
      sourceEl.textContent = 'Credits';
      sourceEl.dataset.state = coverage > 0 ? 'ready' : 'missing';
      sourceEl.title = [
        allowanceSource.url ? `Source: ${allowanceSource.url}` : '',
        allowanceSource.fetched_at ? `rate card snapshot ${allowanceSource.fetched_at}` : '',
        `Credit rates: ${sourceName}.`,
        `Credit coverage ${pct(coverage)} of loaded tokens.`,
        allowanceWindows.length ? `Allowance windows: ${allowanceWindows.map(window => short(window.label || window.key)).join(', ')}` : 'Run codex-usage-tracker init-allowance to add remaining usage windows.',
        allowanceWindows.some(window => window.reset_at) ? `Resets: ${allowanceWindows.map(window => window.reset_at ? `${short(window.label || window.key)} ${formatTimestamp(window.reset_at, window.reset_at)}` : '').filter(Boolean).join('; ')}` : '',
        allowanceError ? `Allowance config error: ${allowanceError}` : '',
        rateCardError ? `Rate-card error: ${rateCardError}` : '',
      ].filter(Boolean).join(' ');
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
        option.textContent = value;
        select.appendChild(option);
      });
      const valuesSet = new Set(Array.from(select.options).map(option => option.value));
      select.value = valuesSet.has(previous) ? previous : '';
    }
    function rebuildFilterOptions() {
      rebuildSelectOptions(modelEl, data.map(row => row.model), 'All models');
      rebuildSelectOptions(effortEl, data.map(row => row.effort), 'All efforts');
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
          pricingSource.name || 'Pricing source',
          pricingSource.tier ? `${pricingSource.tier} tier` : '',
          pricingSource.fetched_at ? `fetched ${formatTimestamp(pricingSource.fetched_at)}` : '',
          pricingSource.pinned ? 'pinned snapshot' : '',
        ].filter(Boolean);
        sourceEl.textContent = 'Costs';
        sourceEl.dataset.state = 'ready';
        sourceEl.title = pricingSource.fetched_at
          ? `${sourceParts.join(' · ')}. Fetched from ${pricingSource.url} at ${formatTimestampTitle(pricingSource.fetched_at)}. Internal Codex labels may use marked best-guess estimates.${pricingSnapshotWarning ? ` ${pricingSnapshotWarning}` : ''}`
          : `${sourceParts.join(' · ')}. Internal Codex labels may use marked best-guess estimates.${pricingSnapshotWarning ? ` ${pricingSnapshotWarning}` : ''}`;
      } else {
        sourceEl.textContent = pricingConfigured ? 'Costs' : 'No costs';
        sourceEl.dataset.state = pricingConfigured ? 'ready' : 'missing';
        sourceEl.title = pricingConfigured ? (pricingSnapshotWarning || '') : 'Run codex-usage-tracker update-pricing to configure estimated costs.';
      }
    }
    function updateParserDiagnosticsLine() {
      const sourceEl = document.getElementById('parserDiagnostics');
      const entries = Object.entries(parserDiagnostics || {}).filter(([, value]) => Number(value || 0) > 0);
      if (!entries.length) {
        sourceEl.hidden = true;
        sourceEl.textContent = '';
        sourceEl.title = '';
        return;
      }
      const total = entries.reduce((sum, [, value]) => sum + Number(value || 0), 0);
      sourceEl.hidden = false;
      sourceEl.textContent = 'Parser warnings';
      sourceEl.dataset.state = 'missing';
      sourceEl.title = `Latest refresh reported ${number.format(total)} parser diagnostics: ${entries.map(([key, value]) => `${key}=${value}`).join(', ')}. Run codex-usage-tracker inspect-log <path> to investigate schema drift.`;
    }
    function updatePrivacyModeLine() {
      const sourceEl = document.getElementById('privacyMode');
      const mode = projectMetadataPrivacy.mode || 'normal';
      sourceEl.textContent = mode === 'normal' ? 'Metadata normal' : `Metadata ${mode}`;
      sourceEl.dataset.state = mode === 'normal' ? 'ready' : 'missing';
      sourceEl.title = mode === 'normal'
        ? 'Project metadata is shown with local cwd, project, branch, and configured labels.'
        : [
            `Project metadata privacy mode: ${mode}.`,
            projectMetadataPrivacy.cwd_redacted ? 'Raw cwd paths are redacted.' : '',
            projectMetadataPrivacy.project_names_redacted ? 'Unnamed projects use stable hashed labels.' : '',
            projectMetadataPrivacy.git_remote_label_hidden ? 'Git remote labels are hidden.' : '',
            projectMetadataPrivacy.relative_cwd_hidden ? 'Relative cwd is hidden.' : '',
            projectMetadataPrivacy.git_branch_hidden ? 'Git branch is hidden.' : '',
            projectMetadataPrivacy.tags_hidden ? 'Project tags are hidden.' : '',
            projectMetadataPrivacy.aliases_preserved ? 'Configured project aliases are treated as explicit display opt-ins.' : '',
          ].filter(Boolean).join(' ');
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
      if (startLabel && endLabel && startLabel === endLabel) return `${prefix} ${startLabel}`;
      if (startLabel && endLabel) return `${prefix} ${startLabel} to ${endLabel}`;
      if (startLabel) return `${prefix} from ${startLabel}`;
      if (endLabel) return `${prefix} through ${endLabel}`;
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
          label: formatDateRangeLabel(datePresetLabels[preset], range.start, addDays(range.endExclusive, -1)),
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
          label: 'Invalid date range',
        };
      }
      if (start || end) {
        return {
          active: true,
          invalid: false,
          start,
          endExclusive: end ? addDays(end, 1) : null,
          label: formatDateRangeLabel('Custom', start, end),
        };
      }
      return { active: false, invalid: false, start: null, endExclusive: null, label: 'All time' };
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
        showActionStatus('Copied');
      } catch (error) {
        showActionStatus('Copy failed');
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
      showActionStatus(`Exported ${number.format(rows.length)}`);
    }
    function activePresetDefinition() {
      return presetDefinitions.find(preset => preset.key === activePreset) || null;
    }
    function presetMatchesRow(row) {
      const preset = activePresetDefinition();
      return preset ? preset.matches(row) : true;
    }
    function applyPreset(key) {
      const preset = presetDefinitions.find(candidate => candidate.key === key);
      if (!preset) return;
      activePreset = preset.key;
      activeView = preset.view;
      pricingStatusEl.value = preset.pricingStatus || '';
      sortKey = preset.sort;
      sortDirection = preset.direction || defaultSortDirection(preset.sort);
      sortEl.value = preset.sort;
      currentPage = 1;
      render();
    }
    function clearPreset() {
      activePreset = '';
      pricingStatusEl.value = '';
      sortKey = 'attention';
      sortDirection = defaultSortDirection(sortKey);
      sortEl.value = sortKey;
      currentPage = 1;
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
      return recommendation ? `${recommendation.title}: ${recommendation.why}` : 'No aggregate action is flagged.';
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
      const pricingScore = group.pricingStatus === 'No price' ? 36 : group.pricingStatus === 'Estimated' || group.pricingStatus === 'Mixed' ? 18 : 0;
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
        pill.title = pill.dataset.fullLabel || pill.textContent || '';
      });
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
    function pricingStatusFor(rows) {
      const priced = rows.filter(row => row.pricing_model);
      const estimated = rows.filter(row => row.pricing_estimated);
      if (priced.length === 0) return 'No price';
      if (estimated.length === rows.length) return 'Estimated';
      if (estimated.length > 0 || priced.length < rows.length) return 'Mixed';
      return 'Configured';
    }
    function creditStatusFor(rows) {
      const rated = rows.filter(row => usageCreditValue(row) !== null);
      const estimated = rows.filter(row => row.usage_credit_confidence === 'estimated');
      if (rated.length === 0) return 'No mapped rate';
      if (estimated.length === rows.length) return 'Estimated mapping';
      if (estimated.length > 0 || rated.length < rows.length) return 'Mixed';
      return 'Official rate-card match';
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
        : 'Expand calls or select a row for call-level recommendations.';
      if (contextTrend >= 0.15 || Number(last.context_window_percent || 0) >= highContext) {
        action = 'Review where context growth begins and consider starting a fresh thread.';
      } else if (cacheTrend <= -0.25) {
        action = 'Check for reintroduced files or tool output after cache reuse dropped.';
      } else if (subagentBeforeSpike) {
        action = 'Compare attached subagent or review calls before changing the parent workflow.';
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
        const estimatedCost = calls.reduce((sum, row) => sum + Number(row.estimated_cost_usd || 0), 0);
        const usageCredits = sumUsageCredits(calls);
        const signalCount = calls.reduce((sum, row) => sum + (Array.isArray(row.efficiency_flags) ? row.efficiency_flags.length : 0), 0);
        const latestActivity = calls.reduce((latest, row) => String(row.event_timestamp || '') > latest ? String(row.event_timestamp || '') : latest, '');
        const maxContextUse = calls.reduce((max, row) => Math.max(max, Number(row.context_window_percent || 0)), 0);
        const subagentCount = calls.filter(isSubagent).length;
        const autoReviewCount = calls.filter(isAutoReview).length;
        const attachedCount = calls.filter(row => rowAttachment(row).relation !== 'direct' && rowAttachment(row).relation !== 'session').length;
        const modelSummary = threadModelSummary(calls);
        const effortSummary = compactListSummary(calls.map(row => row.effort), 'efforts');
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
          totalTokens,
          estimatedCost,
          usageCredits,
          cacheRatio: inputTokens ? cachedTokens / inputTokens : 0,
          maxContextUse,
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
    function paginate(items) {
      const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
      currentPage = Math.min(Math.max(currentPage, 1), pageCount);
      const start = (currentPage - 1) * pageSize;
      const end = Math.min(start + pageSize, items.length);
      return {
        items: items.slice(start, end),
        start,
        end,
        total: items.length,
        pageCount,
      };
    }
    function updatePager(page, itemLabel = 'rows') {
      const shouldShowPager = page.pageCount > 1;
      pagerEl.hidden = !shouldShowPager;
      prevPageEl.disabled = currentPage <= 1;
      nextPageEl.disabled = currentPage >= page.pageCount;
      if (!page.total) {
        pageStatusEl.textContent = 'No rows';
        return;
      }
      pageStatusEl.textContent = `${number.format(page.start + 1)}-${number.format(page.end)} of ${number.format(page.total)} ${itemLabel} · page ${number.format(currentPage)}/${number.format(page.pageCount)}`;
    }
    function buildInsights(rows) {
      const groups = groupThreads(rows);
      const insights = [];
      const topCostGroup = groups.filter(group => group.estimatedCost > 0).sort((a, b) => b.estimatedCost - a.estimatedCost || b.attentionScore - a.attentionScore)[0];
      if (topCostGroup) {
        insights.push({
          title: 'Costliest thread',
          value: pricingConfigured ? money(topCostGroup.estimatedCost) : 'Not configured',
          body: `${topCostGroup.label} has ${number.format(topCostGroup.callCount)} calls and ${number.format(topCostGroup.totalTokens)} tokens.`,
          severity: severityForScore(topCostGroup.attentionScore),
          action: 'Open thread timeline',
          preset: 'highest-cost',
        });
      }
      const lowCacheLimit = threshold('low_cache_ratio', 0.3);
      const lowCacheRows = rows.filter(row => Number(row.input_tokens || 0) > 0 && Number(row.cache_ratio || 0) < lowCacheLimit);
      if (lowCacheRows.length) {
        const lowest = lowCacheRows.slice().sort((a, b) => Number(a.cache_ratio || 0) - Number(b.cache_ratio || 0))[0];
        insights.push({
          title: 'Low cache reuse',
          value: pct(lowest.cache_ratio),
          body: `${number.format(lowCacheRows.length)} calls are under ${pct(lowCacheLimit)} cache reuse. Start with ${rowThreadLabel(lowest)}.`,
          severity: 'medium',
          action: 'Apply cache-misses preset',
          preset: 'cache-misses',
        });
      }
      const highContextLimit = threshold('high_context_percent', 0.6);
      const highContextRows = rows.filter(row => Number(row.context_window_percent || 0) >= highContextLimit);
      if (highContextRows.length) {
        const highest = highContextRows.slice().sort((a, b) => Number(b.context_window_percent || 0) - Number(a.context_window_percent || 0))[0];
        insights.push({
          title: 'Context bloat',
          value: pct(highest.context_window_percent),
          body: `${number.format(highContextRows.length)} calls are at or above ${pct(highContextLimit)} context use.`,
          severity: severityForScore(rowAttentionScore(highest)),
          action: 'Apply context-bloat preset',
          preset: 'context-bloat',
        });
      }
      const usageCredits = sumUsageCredits(rows);
      if (usageCredits > 0) {
        const creditCoverage = creditCoverageRatio(rows);
        insights.push({
          title: 'Codex allowance usage',
          value: `${credits(usageCredits)} credits`,
          body: allowanceWindowText(usageCredits, 'impact') || allowanceWindowText(usageCredits, 'remaining') || `${pct(creditCoverage)} of visible tokens map to Codex credit rates.`,
          severity: severityForScore(clamp(usageCredits * 2.4, 0, 140)),
          action: 'Review highest-credit calls',
          preset: 'usage-credits',
        });
      }
      const unpricedTokens = rows.reduce((sum, row) => sum + (!row.pricing_model ? Number(row.total_tokens || 0) : 0), 0);
      if (unpricedTokens) {
        insights.push({
          title: 'Unpriced usage',
          value: number.format(unpricedTokens),
          body: 'These tokens are omitted from estimated cost totals until pricing is configured.',
          severity: 'review',
          action: 'Review pricing gaps',
          preset: 'pricing-gaps',
        });
      }
      const estimatedTokens = rows.reduce((sum, row) => sum + (row.pricing_estimated ? Number(row.total_tokens || 0) : 0), 0);
      if (estimatedTokens) {
        insights.push({
          title: 'Estimated pricing',
          value: number.format(estimatedTokens),
          body: 'Marked best-guess prices are included, but should be reviewed separately.',
          severity: 'review',
          action: 'Review estimates',
          preset: 'estimated-review',
        });
      }
      const reasoningRows = rows.filter(row => Number(row.reasoning_output_tokens || 0) > 0).sort((a, b) => Number(b.reasoning_output_tokens || 0) - Number(a.reasoning_output_tokens || 0));
      if (reasoningRows[0]) {
        insights.push({
          title: 'Reasoning output spike',
          value: number.format(reasoningRows[0].reasoning_output_tokens || 0),
          body: `${rowThreadLabel(reasoningRows[0])} has the largest reasoning-output call in the current filter.`,
          severity: severityForScore(rowAttentionScore(reasoningRows[0])),
          action: 'Inspect selected call',
          view: 'calls',
          sort: 'signals',
        });
      }
      return insights.slice(0, 6);
    }
    function renderInsightPanel(rows) {
      if (activeView !== 'insights' && !activePreset) {
        insightsPanelEl.hidden = true;
        return;
      }
      insightsPanelEl.hidden = false;
      renderPresetControls();
      const insights = buildInsights(rows);
      if (!insights.length) {
        insightCardsEl.innerHTML = '<div class="empty-state">No attention signals match the current filters.</div>';
        return;
      }
      insightCardsEl.innerHTML = insights.map((insight, index) => {
        const severity = insight.severity || 'review';
        return `
          <article class="insight-card" data-severity="${escapeHtml(severity)}">
            <div class="insight-card-header">
              <h3>${escapeHtml(insight.title)}</h3>
              <span class="severity-chip ${escapeHtml(severity)}">${escapeHtml(severity === 'high' ? 'High' : severity === 'medium' ? 'Medium' : 'Review')}</span>
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
            applyPreset(insight.preset);
            return;
          }
          activeView = insight.view || 'calls';
          if (insight.sort) {
            sortKey = insight.sort;
            sortDirection = defaultSortDirection(insight.sort);
            sortEl.value = sortKey;
          }
          currentPage = 1;
          render();
        });
      });
    }
    function renderPresetControls() {
      const preset = activePresetDefinition();
      clearPresetEl.hidden = !preset;
      presetStatusEl.textContent = preset ? `${preset.caption}: ${preset.description}` : 'No preset applied.';
      presetListEl.innerHTML = presetDefinitions.map(candidate => `
        <button class="preset-card" type="button" data-preset="${escapeHtml(candidate.key)}" aria-pressed="${candidate.key === activePreset ? 'true' : 'false'}">
          <span class="preset-copy"><b>${escapeHtml(candidate.label)}</b><span>${escapeHtml(candidate.description)}</span></span>
          <span class="preset-chip">Run</span>
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
      document.getElementById('estimatedCost').textContent = pricingConfigured ? money(estimatedCost) : 'Not configured';
      document.getElementById('usageCredits').textContent = credits(usageCredits);
      document.getElementById('allowanceImpact').textContent = allowanceImpactText(usageCredits);
      document.getElementById('allowanceImpact').title = allowanceWindowText(usageCredits, 'remaining') || 'Add ~/.codex-usage-tracker/allowance.json to show 5h and weekly remaining usage.';
      insightsViewEl.setAttribute('aria-pressed', activeView === 'insights' ? 'true' : 'false');
      callsViewEl.setAttribute('aria-pressed', activeView === 'calls' ? 'true' : 'false');
      threadsViewEl.setAttribute('aria-pressed', activeView === 'threads' ? 'true' : 'false');
      renderInsightPanel(rows);
      if (activeView === 'threads') {
        renderThreads(rows);
      } else if (activeView === 'insights') {
        renderThreads(rows, 'insights');
      } else {
        renderCalls(rows);
      }
      fitModelPills();
      syncUrlState();
    }
    function renderCalls(rows) {
      const page = paginate(rows);
      updatePager(page, 'calls');
      tableTitleEl.textContent = 'Model Calls';
      const preset = activePresetDefinition();
      const prefix = preset ? `${preset.caption}. ` : '';
      tableCaptionEl.textContent = `${prefix}${dateCaptionPrefix()}Showing individual model calls sorted by ${tableCaptionEl.dataset.sortDescription}. ${loadedRowsDescription()}.`;
      for (const row of page.items) {
        const tr = document.createElement('tr');
        const flags = Array.isArray(row.efficiency_flags) ? row.efficiency_flags : [];
        tr.className = 'call-row';
        tr.tabIndex = 0;
        tr.setAttribute('role', 'button');
        tr.setAttribute('aria-label', `Inspect ${rowThreadLabel(row)} usage`);
        tr.innerHTML = `
          <td>${renderTimeCell(row.event_timestamp)}</td>
          <td title="${escapeHtml(short(row.session_id))}">${escapeHtml(truncate(rowThreadLabel(row)))}</td>
          <td><span class="pill model-pill" data-full-label="${escapeHtml(short(row.model))}">${escapeHtml(short(row.model))}</span></td>
          <td>${escapeHtml(short(row.effort))}</td>
          <td class="num">${number.format(row.total_tokens || 0)}</td>
          <td class="num">${costUsageCell(row.pricing_estimated ? `${money(row.estimated_cost_usd)}*` : money(row.estimated_cost_usd), usageCreditValue(row))}</td>
          <td class="num">${pct(row.cache_ratio)}</td>
          <td><div class="flags">${flags.slice(0, 2).map(flag => `<span class="flag">${escapeHtml(flag)}</span>`).join('')}</div></td>
        `;
        tr.addEventListener('mouseenter', () => showDetail(row));
        tr.addEventListener('click', () => selectRow(row));
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
        rowsEl.innerHTML = '<tr><td class="empty-state" colspan="8">No calls match the current filters.</td></tr>';
      }
    }
    function renderThreads(rows, mode = 'threads') {
      const groups = groupThreads(rows);
      if (!initialThreadExpansionApplied && (activeView === 'threads' || activeView === 'insights')) {
        const expansion = urlParams.get('expand');
        if (expansion === 'all') {
          groups.forEach(group => expandedThreads.add(group.key));
        } else if (expansion === 'first' && groups[0]) {
          expandedThreads.add(groups[0].key);
        }
        initialThreadExpansionApplied = true;
      }
      const page = paginate(groups);
      updatePager(page, 'threads');
      tableTitleEl.textContent = mode === 'insights' ? 'Top Threads by Attention Score' : 'Threads';
      const preset = activePresetDefinition();
      const prefix = preset ? `${preset.caption}. ` : '';
      tableCaptionEl.textContent = `${prefix}${dateCaptionPrefix()}Showing ${number.format(groups.length)} threads from ${number.format(rows.length)} filtered calls, sorted by ${tableCaptionEl.dataset.sortDescription}. ${loadedRowsDescription()}. Click a thread to expand its calls.`;
      for (const group of page.items) {
        const tr = document.createElement('tr');
        const expanded = expandedThreads.has(group.key);
        const threadNotes = [
          `${number.format(group.callCount)} calls`,
          group.pricingStatus,
          group.parentThreadLabel ? `spawned from ${group.parentThreadLabel}` : '',
          group.childThreadCount ? `${number.format(group.childThreadCount)} spawned threads` : '',
          group.subagentCount ? `${number.format(group.subagentCount)} subagent` : '',
          group.autoReviewCount ? `${number.format(group.autoReviewCount)} auto-review` : '',
          group.attachedCount ? 'attached' : '',
        ].filter(Boolean).join(' - ');
        tr.className = `thread-row${group.parentThreadLabel ? ' spawned-thread' : ''}`;
        tr.tabIndex = 0;
        tr.setAttribute('role', 'button');
        tr.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        tr.setAttribute('aria-label', `${expanded ? 'Collapse' : 'Expand'} ${group.label} calls. Attention score ${Math.round(group.attentionScore)}.`);
        tr.innerHTML = `
          <td>${renderTimeCell(group.latestActivity)}</td>
          <td>
            <div class="thread-title">
                <span class="thread-toggle" aria-hidden="true">${expanded ? '-' : '+'}</span>
              <span class="thread-meta">
                <span class="thread-name">${group.renderAsChild ? '<span class="thread-relation">spawned</span> ' : ''}${escapeHtml(truncate(group.label, 72))}</span>
                <span class="thread-subtle">${escapeHtml(threadNotes)} · attention ${number.format(Math.round(group.attentionScore))}</span>
              </span>
            </div>
          </td>
          <td><span class="pill model-pill" data-full-label="${escapeHtml(short(group.modelSummary))}">${escapeHtml(short(group.modelSummary))}</span></td>
          <td>${escapeHtml(truncate(group.effortSummary, 28))}</td>
          <td class="num">${number.format(group.totalTokens)}</td>
          <td class="num">${costUsageCell(pricingConfigured ? money(group.estimatedCost) : 'Not configured', group.usageCredits)}</td>
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
        rowsEl.innerHTML = '<tr><td class="empty-state" colspan="8">No threads match the current filters.</td></tr>';
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
      const calls = group.calls.map(row => {
        const flags = Array.isArray(row.efficiency_flags) ? row.efficiency_flags : [];
        return `
          <tr class="thread-call-row" tabindex="0" role="button" data-record-id="${escapeHtml(row.record_id || '')}">
            <td>${renderTimeCell(row.event_timestamp)}</td>
            <td><span class="pill model-pill" data-full-label="${escapeHtml(short(row.model))}">${escapeHtml(short(row.model))}</span></td>
            <td>${escapeHtml(short(row.effort))}</td>
            <td>${escapeHtml(sourceLabel(row))}</td>
            <td class="num">${number.format(row.total_tokens || 0)}</td>
            <td class="num">${costUsageCell(row.pricing_estimated ? `${money(row.estimated_cost_usd)}*` : money(row.estimated_cost_usd), usageCreditValue(row))}</td>
            <td class="num">${pct(row.cache_ratio)}</td>
            <td><div class="flags">${flags.slice(0, 2).map(flag => `<span class="flag">${escapeHtml(flag)}</span>`).join('')}</div></td>
          </tr>
        `;
      }).join('');
      tr.innerHTML = `
        <td class="child-cell" colspan="8">
          <table class="thread-call-table" aria-label="${escapeHtml(group.label)} calls">
            <thead><tr><th>Time</th><th>Model</th><th>Effort</th><th>Source</th><th class="num">Last Call</th><th class="num">Cost</th><th class="num">Cache</th><th>Signals</th></tr></thead>
            <tbody>${calls}</tbody>
          </table>
        </td>
      `;
      return tr;
    }
    function contextControls(row) {
      const fileMode = window.location.protocol === 'file:';
      const apiUnavailable = !contextApiEnabled || !apiToken;
      const disabled = fileMode || apiUnavailable ? ' disabled' : '';
      const hint = fileMode
        ? 'Open this dashboard with codex-usage-tracker serve-dashboard to load raw context on demand.'
        : apiUnavailable
          ? 'Context loading is disabled for this dashboard server. Restart with --context-api explicit to enable explicit row actions.'
          : 'Context is not embedded in this dashboard. Press a button to read this call from the local JSONL source.';
      return `
        <div class="context-actions">
          <button class="context-button" type="button" data-context-load${disabled}>Load context</button>
          <button class="context-button secondary" type="button" data-context-load-output${disabled}>Include tool output</button>
        </div>
        <div id="contextResult" class="context-result"><p class="context-note">${escapeHtml(hint)}</p></div>
      `;
    }
    function bindContextButtons(row) {
      const loadButton = detailEl.querySelector('[data-context-load]');
      const outputButton = detailEl.querySelector('[data-context-load-output]');
      if (loadButton) loadButton.addEventListener('click', () => loadContext(row, false));
      if (outputButton) outputButton.addEventListener('click', () => loadContext(row, true));
    }
    async function loadContext(row, includeToolOutput) {
      const target = document.getElementById('contextResult');
      if (!target) return;
      if (!row.record_id) {
        target.innerHTML = '<p class="context-note">This row has no record id for context lookup.</p>';
        return;
      }
      target.innerHTML = '<p class="context-note">Loading local context...</p>';
      const params = new URLSearchParams({ record_id: row.record_id });
      if (includeToolOutput) params.set('include_tool_output', '1');
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
            ? 'Context API is unavailable here. Run codex-usage-tracker serve-dashboard --open for on-demand context loading.'
            : `Context API returned HTTP ${response.status}.`;
          throw new Error(errorText);
        }
        const payload = await response.json();
        target.innerHTML = renderContext(payload);
      } catch (error) {
        target.innerHTML = `<p class="context-note">${escapeHtml(error.message || String(error))}</p>`;
      }
    }
    function renderContext(payload) {
      const entries = Array.isArray(payload.entries) ? payload.entries : [];
      const source = payload.source || {};
      const omitted = payload.omitted || {};
      const note = [
        'Loaded on demand from local JSONL.',
        payload.raw_context_persisted === false ? 'Not persisted to SQLite or dashboard HTML.' : '',
        payload.include_tool_output ? 'Tool output included with redaction and size limits.' : 'Tool output omitted by default.',
        source.file ? `Source: ${source.file}:${source.line_number || ''}` : '',
        omitted.older_entries ? `${number.format(omitted.older_entries)} older entries omitted.` : '',
        omitted.over_budget_chars ? `${number.format(omitted.over_budget_chars)} chars over budget omitted.` : '',
      ].filter(Boolean).join(' ');
      const body = entries.map(entry => `
        <div class="context-entry">
          <div class="context-entry-header">
            <span>${escapeHtml(entry.label || entry.type || 'entry')}</span>
            <span>${escapeHtml([formatTimestamp(entry.timestamp, ''), entry.line_number ? `line ${entry.line_number}` : ''].filter(Boolean).join(' - '))}</span>
          </div>
          <pre>${escapeHtml(entry.text || '')}</pre>
        </div>
      `).join('');
      return `<p class="context-note">${escapeHtml(note)}</p>${body || '<p class="context-note">No context entries found for this call.</p>'}`;
    }
    function pricingStatusText(row) {
      if (!row.pricing_model) return 'No configured price';
      return row.pricing_estimated ? 'Best-guess estimate' : 'Configured price';
    }
    function nextActionForRow(row) {
      if (row.recommended_action) return row.recommended_action;
      if (!row.pricing_model) return 'Configure pricing before trusting cost totals.';
      if (Number(row.cache_ratio || 0) < 0.3 && Number(row.input_tokens || 0) > 0) return 'Compare fresh input with the previous turn before continuing.';
      if (Number(row.context_window_percent || 0) >= 0.6) return 'Inspect the thread timeline and consider starting a fresh thread.';
      if (Number(row.reasoning_output_tokens || 0) > Number(row.output_tokens || 0)) return 'Review whether reasoning effort is appropriate for this task.';
      return 'Use the aggregate fields first; load context only if the signal is still unclear.';
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
      if (!calls.length) return '<p>No calls in this thread.</p>';
      return `<div class="timeline-list">${calls.map(row => {
        const contextUse = Number(row.context_window_percent || 0);
        return `
          <div class="timeline-item">
            <div class="timeline-time">${escapeHtml(formatTimestamp(row.event_timestamp, 'Unknown'))}</div>
            <div>
              <div class="timeline-title">${escapeHtml(sourceLabel(row))} · ${escapeHtml(short(row.model))}</div>
              <div class="timeline-meta">${escapeHtml(number.format(row.total_tokens || 0))} tokens · ${escapeHtml(money(row.estimated_cost_usd))} · ${escapeHtml(usageCreditValue(row) === null ? 'no credit rate' : `${credits(usageCreditValue(row))} credits`)} · cache ${escapeHtml(pct(row.cache_ratio))}</div>
              <div class="timeline-meta">${escapeHtml(recommendationSummary(row))}</div>
              <div class="signal-strip">
                <span class="flag">context ${escapeHtml(pct(contextUse))}</span>
                <span class="flag">${escapeHtml(pricingStatusText(row))}</span>
              </div>
              <div class="mini-bar" title="Context use ${escapeHtml(pct(contextUse))}"><span class="${timelineSeverity(contextUse)}" style="width: ${timelineWidth(contextUse)}"></span></div>
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
    function selectThread(group) {
      selectedThreadKey = group.key || '';
      selectedRecordId = '';
      showThreadDetail(group);
      syncUrlState();
    }
    function showDetail(row) {
      const attachment = rowAttachment(row);
      const flags = Array.isArray(row.efficiency_flags) && row.efficiency_flags.length ? row.efficiency_flags.join(', ') : 'None';
      const whyFlagged = Array.isArray(row.flag_explanations) && row.flag_explanations.length ? row.flag_explanations.join(' ') : recommendationSummary(row);
      detailEl.innerHTML = `
        <div class="detail-stack">
          <div class="detail-card primary">
            <h3>Cost, usage, and context</h3>
            ${fieldsList([
              ['Estimated cost', money(row.estimated_cost_usd)],
              ['Codex credits', usageCreditsWithStatus(row)],
              ['Allowance impact', rowAllowanceImpact(row)],
              ['Cache ratio', pct(row.cache_ratio)],
              ['Uncached input', number.format(row.uncached_input_tokens || 0)],
              ['Context use', pct(row.context_window_percent)],
              ['Pricing status', pricingStatusText(row)],
              ['Next action', nextActionForRow(row)],
              ['Why flagged', whyFlagged],
            ])}
          </div>
          <div class="detail-card">
            <h3>Thread narrative</h3>
            ${fieldsList([
              ['Thread', attachment.label],
              ['Project', row.project_name || 'Unknown project'],
              ['Project tags', Array.isArray(row.project_tags) && row.project_tags.length ? row.project_tags.join(', ') : 'None'],
              ['Thread attachment', attachment.relation],
              ['Source', sourceLabel(row)],
              ['Parent thread', resolvedParentThreadName(row) || 'None'],
              ['Timestamp', formatTimestamp(row.event_timestamp)],
            ])}
          </div>
          <div class="detail-card">
            <h3>Token and pricing breakdown</h3>
            ${fieldsList([
              ['Last call total', number.format(row.total_tokens || 0)],
              ['Last call input', number.format(row.input_tokens || 0)],
              ['Cached input', number.format(row.cached_input_tokens || 0)],
              ['Output', number.format(row.output_tokens || 0)],
              ['Reasoning output', number.format(row.reasoning_output_tokens || 0)],
              ['Session cumulative', number.format(row.cumulative_total_tokens || 0)],
              ['Pricing model', row.pricing_model || 'No configured price'],
              ['Credit model', row.usage_credit_model || 'No mapped rate'],
              ['Credit confidence', usageCreditStatusText(row)],
              ['Credit source', row.usage_credit_source || 'None'],
              ['Credit source fetched', row.usage_credit_fetched_at || 'Unknown'],
              ['Credit tier', row.usage_credit_tier || 'Unknown'],
              ['Cache savings', money(row.estimated_cache_savings_usd)],
              ['Efficiency signals', flags],
            ])}
          </div>
          ${detailCollapse('Raw aggregate identifiers', [
            ['Session', row.session_id],
            ['Turn', row.turn_id],
              ['Thread source', row.thread_source || 'user'],
              ['Subagent type', row.subagent_type || 'None'],
              ['Agent role', row.agent_role || 'None'],
              ['Agent nickname', row.agent_nickname || 'None'],
              ['Credit note', row.usage_credit_note || 'None'],
              ['Parent session', row.parent_session_id || 'None'],
            ['Parent updated', resolvedParentSessionUpdatedAt(row) ? formatTimestamp(resolvedParentSessionUpdatedAt(row)) : 'None'],
            ['Cwd', row.cwd],
            ['Project cwd', row.project_relative_cwd || '.'],
            ['Git branch', row.git_branch || 'Unknown'],
            ['Remote label', row.git_remote_label || 'None'],
            ['Remote hash', row.git_remote_hash || 'None'],
          ])}
          ${detailCollapse('Source file and line', [
            ['Source line', `${row.source_file}:${row.line_number}`],
            ['Context window', number.format(row.model_context_window || 0)],
          ])}
          ${contextControls(row)}
        </div>
      `;
      bindContextButtons(row);
    }
    function showThreadDetail(group) {
      const lifecycle = group.lifecycle || {};
      detailEl.innerHTML = `
        <div class="detail-stack">
          <div class="detail-card primary">
            <h3>Thread attention summary</h3>
            ${fieldsList([
              ['Estimated cost', pricingConfigured ? money(group.estimatedCost) : 'Not configured'],
              ['Codex credits', `${credits(group.usageCredits)} credits · ${group.creditStatus}`],
              ['Allowance impact', allowanceWindowText(group.usageCredits, 'impact') || allowanceWindowText(group.usageCredits, 'remaining') || `${credits(group.usageCredits)} credits counted toward Codex usage limits`],
              ['Attention score', number.format(Math.round(group.attentionScore))],
              ['Cache ratio', pct(group.cacheRatio)],
              ['Max context use', pct(group.maxContextUse)],
              ['Pricing status', group.pricingStatus],
              ['Next action', lifecycle.action || (group.maxContextUse >= threshold('high_context_percent', 0.6) || group.cacheRatio < threshold('low_cache_ratio', 0.3) ? 'Inspect the timeline before continuing this thread.' : 'Expand calls or select a row for call-level details.')],
            ])}
          </div>
          <div class="detail-card">
            <h3>Thread lifecycle</h3>
            ${fieldsList([
              ['First expensive turn', lifecycle.firstExpensiveRow ? `${formatTimestamp(lifecycle.firstExpensiveRow.event_timestamp)} · call ${number.format((lifecycle.firstExpensiveIndex || 0) + 1)}` : 'None above thresholds'],
              ['Largest cumulative jump', lifecycle.largestJumpRow ? `${number.format(lifecycle.largestJump)} tokens at ${formatTimestamp(lifecycle.largestJumpRow.event_timestamp)}` : 'None'],
              ['Cache trend', `${lifecycle.cacheTrend >= 0 ? '+' : ''}${pct(lifecycle.cacheTrend || 0)}`],
              ['Context trend', `${lifecycle.contextTrend >= 0 ? '+' : ''}${pct(lifecycle.contextTrend || 0)}`],
              ['Subagent before spike', lifecycle.subagentBeforeSpike ? 'Yes' : 'No'],
            ])}
          </div>
          <div class="detail-card">
            <h3>Thread timeline</h3>
            ${renderThreadTimeline(group)}
          </div>
          <div class="detail-card">
            <h3>Relationships</h3>
            ${fieldsList([
              ['Thread', group.label],
              ['Calls', number.format(group.callCount)],
              ['Subagent calls', number.format(group.subagentCount)],
              ['Auto-review calls', number.format(group.autoReviewCount)],
              ['Attached calls', number.format(group.attachedCount)],
              ['Spawned from', group.parentThreadLabel || 'None'],
              ['Spawned threads', number.format(group.childThreadCount || 0)],
              ['Spawned child calls', number.format(group.childCallCount || 0)],
            ])}
          </div>
          ${detailCollapse('Secondary thread fields', [
            ['Latest activity', formatTimestamp(group.latestActivity)],
            ['Total tokens', number.format(group.totalTokens)],
            ['Efficiency signals', number.format(group.signalCount)],
            ['Model mix', group.modelSummary],
            ['Reasoning mix', group.effortSummary],
          ])}
        </div>
      `;
    }
    function setView(view) {
      activeView = view;
      currentPage = 1;
      render();
    }
    function updateLiveStatus(label, detail = '') {
      liveStatusEl.textContent = label;
      liveStatusEl.title = detail || label;
      liveStatusEl.dataset.state = label.toLowerCase().includes('error') ? 'error' : 'ready';
    }
    function updateToTopVisibility() {
      toTopEl.dataset.visible = window.scrollY > 320 ? 'true' : 'false';
    }
    function applyDashboardPayload(nextPayload) {
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
        updateLiveStatus('Reloading', 'Reloading static dashboard snapshot...');
        window.location.reload();
        return;
      }
      if (refreshInFlight) return;
      refreshInFlight = true;
      refreshDashboardEl.disabled = true;
      updateLiveStatus(manual ? 'Refreshing' : 'Checking', manual ? 'Refreshing local usage index...' : 'Checking for new usage...');
      try {
        const params = new URLSearchParams({
          refresh: '1',
          limit: loadLimitEl.value,
          include_archived: includeArchived ? '1' : '0',
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
          : ` Indexed ${number.format(result.inserted_or_updated_events)} aggregate rows from ${number.format(result.scanned_files || 0)} logs.`;
        const skipped = result.skipped_events
          ? ` Skipped ${number.format(result.skipped_events)} malformed token-count events.`
          : '';
        updateLiveStatus(autoRefreshEl.checked ? 'Live' : 'Updated', `Updated ${formatTimestamp(nextPayload.refreshed_at)}. ${loadedRowsDescription()}. ${historyRowsDescription()}.${indexed}${skipped}`);
      } catch (error) {
        const message = error.message || String(error);
        updateLiveStatus('Refresh error', `Live refresh unavailable: ${message}${manual ? '. Reload this page after regenerating a static dashboard, or run codex-usage-tracker serve-dashboard.' : ''}`);
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
    loadLimitEl.addEventListener('change', () => {
      currentPage = 1;
      if (liveRefreshSupported) {
        refreshDashboardData(true);
      } else {
        updateLiveStatus('Static', 'Run codex-usage-tracker serve-dashboard to load a different history size from the dashboard.');
      }
    });
    historyScopeEl.addEventListener('change', () => {
      includeArchived = historyScopeEl.value === 'all';
      currentPage = 1;
      updateHistoryScopeControl();
      syncUrlState();
      if (liveRefreshSupported) {
        refreshDashboardData(true);
      } else {
        updateLiveStatus('Static', 'Run codex-usage-tracker serve-dashboard to switch between active sessions and all history from the dashboard.');
      }
    });
    autoRefreshEl.addEventListener('change', () => {
      scheduleAutoRefresh();
      updateLiveStatus(autoRefreshEl.checked ? 'Live' : 'Paused', `${autoRefreshEl.checked ? `Live refresh every ${liveRefreshIntervalMs / 1000}s` : 'Live refresh paused'}. ${loadedRowsDescription()}. ${historyRowsDescription()}`);
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
    prevPageEl.addEventListener('click', () => {
      currentPage = Math.max(1, currentPage - 1);
      render();
    });
    nextPageEl.addEventListener('click', () => {
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
      const callRow = event.target.closest('.thread-call-row');
      if (!callRow || !rowsEl.contains(callRow)) return;
      const row = rowByRecordId.get(callRow.dataset.recordId);
      if (row) showDetail(row);
    });
    rowsEl.addEventListener('keydown', event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const callRow = event.target.closest('.thread-call-row');
      if (!callRow || !rowsEl.contains(callRow)) return;
      event.preventDefault();
      const row = rowByRecordId.get(callRow.dataset.recordId);
      if (row) selectRow(row);
    });
    datePresetEl.addEventListener('input', () => {
      syncDatePresetInputs();
      currentPage = 1;
      render();
    });
    [dateStartEl, dateEndEl].forEach(el => el.addEventListener('input', () => {
      if (datePresetEl.value !== 'custom') datePresetEl.value = 'custom';
      el.value = cleanDateInput(el.value) || el.value;
      currentPage = 1;
      render();
    }));
    [searchEl, modelEl, effortEl, pricingStatusEl].forEach(el => el.addEventListener('input', () => {
      currentPage = 1;
      render();
    }));
    sortEl.addEventListener('input', () => setSort(sortEl.value, defaultSortDirection(sortEl.value)));
    rebuildDashboardIndexes();
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
      updateLiveStatus('Static', `Static snapshot. ${loadedRowsDescription()}. ${historyRowsDescription()}`);
    } else {
      updateLiveStatus('Live', `Live refresh every ${liveRefreshIntervalMs / 1000}s. ${loadedRowsDescription()}. ${historyRowsDescription()}`);
      scheduleAutoRefresh();
      if (needsInitialHistoryRefresh) refreshDashboardData(false);
    }
    updateToTopVisibility();
    render();
