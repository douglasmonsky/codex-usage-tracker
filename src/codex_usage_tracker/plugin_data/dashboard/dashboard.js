const initialPayload = JSON.parse(document.getElementById('usage-data').textContent);
    const urlParams = new URLSearchParams(window.location.search);
    let data = payloadRows(initialPayload);
    let pricingConfigured = Boolean(initialPayload.pricing_configured);
    let pricingSource = initialPayload.pricing_source || {};
    let totalAvailableRows = Number(initialPayload.total_available_rows || data.length);
    let loadedLimit = payloadLimit(initialPayload);
    const rowsEl = document.getElementById('rows');
    const detailEl = document.getElementById('detail');
    const searchEl = document.getElementById('search');
    const modelEl = document.getElementById('model');
    const effortEl = document.getElementById('effort');
    const pricingStatusEl = document.getElementById('pricingStatus');
    const sortEl = document.getElementById('sort');
    const tableTitleEl = document.getElementById('tableTitle');
    const tableCaptionEl = document.getElementById('tableCaption');
    const callsViewEl = document.getElementById('callsView');
    const threadsViewEl = document.getElementById('threadsView');
    const refreshDashboardEl = document.getElementById('refreshDashboard');
    const autoRefreshEl = document.getElementById('autoRefresh');
    const loadLimitEl = document.getElementById('loadLimit');
    const liveStatusEl = document.getElementById('liveStatus');
    const prevPageEl = document.getElementById('prevPage');
    const nextPageEl = document.getElementById('nextPage');
    const pageStatusEl = document.getElementById('pageStatus');
    const pagerEl = document.getElementById('pager');
    const toTopEl = document.getElementById('toTop');
    const number = new Intl.NumberFormat();
    const tableDateFormat = new Intl.DateTimeFormat([], { month: 'short', day: 'numeric', year: 'numeric' });
    const tableTimeFormat = new Intl.DateTimeFormat([], { hour: 'numeric', minute: '2-digit', second: '2-digit' });
    const detailDateTimeFormat = new Intl.DateTimeFormat([], {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      timeZoneName: 'short',
    });
    let rowByRecordId = new Map();
    let threadAttachmentByRecordId = new Map();
    const expandedThreads = new Set();
    const liveRefreshSupported = window.location.protocol !== 'file:';
    const liveRefreshIntervalMs = 10000;
    const pageSize = 500;
    let activeView = urlParams.get('view') === 'threads' ? 'threads' : 'calls';
    let sortKey = sortEl.value || 'time';
    let sortDirection = defaultSortDirection(sortKey);
    let refreshInFlight = false;
    let autoRefreshTimer = null;
    let currentPage = 1;
    let initialThreadExpansionApplied = false;
    let initialDetailApplied = false;
    const money = (value, missingLabel = 'No price') => {
      if (value === null || value === undefined) return missingLabel;
      const amount = Number(value) || 0;
      if (amount > 0 && amount < 0.01) return `$${amount.toFixed(4)}`;
      return `$${amount.toFixed(2)}`;
    };
    const pct = value => `${((Number(value) || 0) * 100).toFixed(1)}%`;
    const short = (value, fallback = 'Unknown') => value || fallback;
    const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[char]));
    const truncate = (value, size = 54) => {
      const text = short(value, '');
      return text.length > size ? `${text.slice(0, size - 1)}…` : text;
    };
    function parsedTimestamp(value) {
      if (!value) return null;
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? null : date;
    }
    function formatTimestamp(value, fallback = 'Unknown') {
      const date = parsedTimestamp(value);
      return date ? detailDateTimeFormat.format(date) : short(value, fallback);
    }
    function formatTimestampTitle(value) {
      const formatted = formatTimestamp(value, '');
      return [formatted, value].filter(Boolean).join(' - ');
    }
    function renderTimeCell(value) {
      const date = parsedTimestamp(value);
      if (!date) return escapeHtml(truncate(value, 20));
      return `
        <span class="time-cell" title="${escapeHtml(formatTimestampTitle(value))}">
          <span class="time-date">${escapeHtml(tableDateFormat.format(date))}</span>
          <span class="time-clock">${escapeHtml(tableTimeFormat.format(date))}</span>
        </span>
      `;
    }
    function defaultSortDirection(key) {
      return {
        cache: 'asc',
        effort: 'asc',
        model: 'asc',
        thread: 'asc',
      }[key] || 'desc';
    }
    function textValue(value) {
      return short(value, '').toLowerCase();
    }
    function compareValues(left, right) {
      if (typeof left === 'number' || typeof right === 'number') {
        return (Number(left) || 0) - (Number(right) || 0);
      }
      return String(left || '').localeCompare(String(right || ''));
    }
    function directional(compareResult) {
      return sortDirection === 'asc' ? compareResult : -compareResult;
    }
    function sortLabel(key) {
      return {
        cache: 'Cache',
        context: 'Context use',
        cost: 'Cost',
        effort: 'Effort',
        model: 'Model',
        signals: 'Signals',
        thread: 'Thread',
        time: 'Time',
        total: 'Tokens',
      }[key] || 'Sort';
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
    function payloadRows(nextPayload) {
      return Array.isArray(nextPayload) ? nextPayload : Array.isArray(nextPayload.rows) ? nextPayload.rows : [];
    }
    function payloadLimit(nextPayload) {
      if (!nextPayload || nextPayload.limit === null || nextPayload.limit === undefined) return null;
      const parsed = Number(nextPayload.limit);
      return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
    }
    function limitValue(limit) {
      return limit === null || limit === undefined ? 'all' : String(limit);
    }
    function loadedRowsDescription() {
      const loaded = number.format(data.length);
      const available = number.format(totalAvailableRows || data.length);
      const capped = loadedLimit !== null && totalAvailableRows > data.length;
      return capped ? `${loaded} of ${available} calls loaded` : `${loaded} calls loaded`;
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
    function updatePricingSourceLine() {
      const sourceEl = document.getElementById('pricingSource');
      if (pricingConfigured && pricingSource.url) {
        const sourceParts = [
          pricingSource.name || 'Pricing source',
          pricingSource.tier ? `${pricingSource.tier} tier` : '',
          pricingSource.fetched_at ? `fetched ${formatTimestamp(pricingSource.fetched_at)}` : '',
        ].filter(Boolean);
        sourceEl.textContent = `Costs: ${sourceParts.join(' · ')}`;
        sourceEl.title = pricingSource.fetched_at
          ? `Fetched from ${pricingSource.url} at ${formatTimestampTitle(pricingSource.fetched_at)}. Internal Codex labels may use marked best-guess estimates.`
          : 'Internal Codex labels may use marked best-guess estimates.';
      } else {
        sourceEl.textContent = pricingConfigured ? '' : 'Costs unavailable';
        sourceEl.title = pricingConfigured ? '' : 'Run codex-usage-tracker update-pricing to configure estimated costs.';
      }
    }
    function filtered() {
      const term = searchEl.value.trim().toLowerCase();
      const model = modelEl.value;
      const effort = effortEl.value;
      const pricingStatus = pricingStatusEl.value;
      const rows = data.filter(row => {
        const haystack = [
          rowThreadLabel(row),
          row.cwd,
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
          || (pricingStatus === 'unpriced' && !row.pricing_model);
        return (!term || haystack.includes(term)) && (!model || row.model === model) && (!effort || row.effort === effort) && statusMatches;
      });
      rows.sort(compareCalls);
      return rows;
    }
    function callSortValue(row, key) {
      if (key === 'cache') return Number(row.cache_ratio || 0);
      if (key === 'context') return Number(row.context_window_percent || 0);
      if (key === 'cost') return Number(row.estimated_cost_usd || 0);
      if (key === 'effort') return textValue(row.effort);
      if (key === 'model') return textValue(row.model);
      if (key === 'signals') return Array.isArray(row.efficiency_flags) ? row.efficiency_flags.length : 0;
      if (key === 'thread') return textValue(rowThreadLabel(row));
      if (key === 'time') return String(row.event_timestamp || '');
      return Number(row.total_tokens || 0);
    }
    function compareCalls(a, b) {
      const primary = directional(compareValues(callSortValue(a, sortKey), callSortValue(b, sortKey)));
      if (primary !== 0) return primary;
      const timeFallback = String(b.event_timestamp || '').localeCompare(String(a.event_timestamp || ''));
      if (timeFallback !== 0) return timeFallback;
      return String(a.record_id || '').localeCompare(String(b.record_id || ''));
    }
    function isAutoReview(row) {
      return row.model === 'codex-auto-review' || row.subagent_type === 'guardian';
    }
    function isSubagent(row) {
      return row.thread_source === 'subagent' || Boolean(row.subagent_type || row.parent_session_id);
    }
    function sourceLabel(row) {
      if (isAutoReview(row)) return 'Auto-review';
      if (row.subagent_type === 'thread_spawn') {
        return row.agent_role ? `Subagent: ${row.agent_role}` : 'Subagent';
      }
      if (isSubagent(row)) return 'Subagent';
      return 'User';
    }
    function resolvedParentThreadName(row) {
      return row.resolved_parent_thread_name || row.parent_thread_name || '';
    }
    function resolvedParentSessionUpdatedAt(row) {
      return row.resolved_parent_session_updated_at || row.parent_session_updated_at || '';
    }
    function resolveThreadAttachment(row) {
      if (row.thread_attachment_key && row.thread_attachment_label) {
        return {
          key: row.thread_attachment_key,
          label: row.thread_attachment_label,
          relation: row.thread_attachment_relation || 'session',
          parentSessionId: row.thread_attachment_parent_session_id || row.parent_session_id || null,
        };
      }
      if (row.thread_name) {
        return { key: `thread:${row.thread_name}`, label: row.thread_name, relation: 'direct' };
      }
      const parentThreadName = resolvedParentThreadName(row);
      if (row.parent_session_id && parentThreadName) {
        return {
          key: `thread:${parentThreadName}`,
          label: parentThreadName,
          relation: 'explicit parent thread',
          parentSessionId: row.parent_session_id,
        };
      }
      if (row.parent_session_id) {
        return {
          key: `session:${row.parent_session_id}`,
          label: `Parent ${row.parent_session_id}`,
          relation: 'explicit parent',
          parentSessionId: row.parent_session_id,
        };
      }
      return {
        key: `session:${row.session_id || 'unknown'}`,
        label: row.session_id || 'Unknown thread',
        relation: isSubagent(row) ? 'unmatched subagent' : 'session',
      };
    }
    function rowAttachment(row) {
      return threadAttachmentByRecordId.get(row.record_id) || resolveThreadAttachment(row);
    }
    function rowThreadLabel(row) {
      return rowAttachment(row).label;
    }
    function chronological(a, b) {
      const timeCompare = String(a.event_timestamp || '').localeCompare(String(b.event_timestamp || ''));
      if (timeCompare !== 0) return timeCompare;
      return Number(a.cumulative_total_tokens || 0) - Number(b.cumulative_total_tokens || 0);
    }
    function sortThreads(groups) {
      groups.sort(compareThreads);
      return groups;
    }
    function threadSortValue(group, key) {
      if (key === 'cache') return group.cacheRatio;
      if (key === 'context') return group.maxContextUse;
      if (key === 'cost') return group.estimatedCost;
      if (key === 'effort') return textValue(group.effortSummary);
      if (key === 'model') return textValue(group.modelSummary);
      if (key === 'signals') return group.signalCount;
      if (key === 'thread') return textValue(group.label);
      if (key === 'time') return String(group.latestActivity || '');
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
    function compactListSummary(values, fallback = 'Mixed') {
      const unique = [...new Set(values.filter(Boolean))].sort();
      if (!unique.length) return 'Unknown';
      if (unique.length === 1) return unique[0];
      return `${unique[0]} +${unique.length - 1} ${fallback.toLowerCase()}`;
    }
    function threadModelSummary(calls) {
      const models = [...new Set(calls.map(row => row.model).filter(Boolean))].sort();
      if (!models.length) return 'Unknown';
      if (models.length === 1) return models[0];
      const nonReviewModels = models.filter(model => model !== 'codex-auto-review');
      const primary = nonReviewModels.length ? nonReviewModels[0] : models[0];
      return `${primary} +${models.length - 1} models`;
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
        const signalCount = calls.reduce((sum, row) => sum + (Array.isArray(row.efficiency_flags) ? row.efficiency_flags.length : 0), 0);
        const latestActivity = calls.reduce((latest, row) => String(row.event_timestamp || '') > latest ? String(row.event_timestamp || '') : latest, '');
        const maxContextUse = calls.reduce((max, row) => Math.max(max, Number(row.context_window_percent || 0)), 0);
        const subagentCount = calls.filter(isSubagent).length;
        const autoReviewCount = calls.filter(isAutoReview).length;
        const attachedCount = calls.filter(row => rowAttachment(row).relation !== 'direct' && rowAttachment(row).relation !== 'session').length;
        const modelSummary = threadModelSummary(calls);
        const effortSummary = compactListSummary(calls.map(row => row.effort), 'efforts');
        const parentThreadLabel = dominantParentThread(calls, group.label);
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
          cacheRatio: inputTokens ? cachedTokens / inputTokens : 0,
          maxContextUse,
          pricingStatus: pricingStatusFor(calls),
          signalCount,
          subagentCount,
          autoReviewCount,
          attachedCount,
        };
      });
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
    function render() {
      const rows = filtered();
      rowsEl.textContent = '';
      updateSortControls();
      document.getElementById('visibleCalls').textContent = number.format(rows.length);
      document.getElementById('totalTokens').textContent = number.format(rows.reduce((sum, row) => sum + Number(row.total_tokens || 0), 0));
      document.getElementById('cachedTokens').textContent = number.format(rows.reduce((sum, row) => sum + Number(row.cached_input_tokens || 0), 0));
      document.getElementById('reasoningTokens').textContent = number.format(rows.reduce((sum, row) => sum + Number(row.reasoning_output_tokens || 0), 0));
      const estimatedCost = rows.reduce((sum, row) => sum + Number(row.estimated_cost_usd || 0), 0);
      const pricedTokens = rows.reduce((sum, row) => sum + (row.pricing_model ? Number(row.total_tokens || 0) : 0), 0);
      const estimatedTokens = rows.reduce((sum, row) => sum + (row.pricing_estimated ? Number(row.total_tokens || 0) : 0), 0);
      const unpricedTokens = rows.reduce((sum, row) => sum + (!row.pricing_model ? Number(row.total_tokens || 0) : 0), 0);
      const totalTokens = rows.reduce((sum, row) => sum + Number(row.total_tokens || 0), 0);
      document.getElementById('estimatedCost').textContent = pricingConfigured ? money(estimatedCost) : 'Not configured';
      document.getElementById('priceCoverage').textContent = pct(totalTokens ? pricedTokens / totalTokens : 0);
      document.getElementById('estimatedTokens').textContent = number.format(estimatedTokens);
      document.getElementById('unpricedTokens').textContent = number.format(unpricedTokens);
      callsViewEl.setAttribute('aria-pressed', activeView === 'calls' ? 'true' : 'false');
      threadsViewEl.setAttribute('aria-pressed', activeView === 'threads' ? 'true' : 'false');
      if (activeView === 'threads') {
        renderThreads(rows);
      } else {
        renderCalls(rows);
      }
      fitModelPills();
    }
    function renderCalls(rows) {
      const page = paginate(rows);
      updatePager(page, 'calls');
      tableTitleEl.textContent = 'Model Calls';
      tableCaptionEl.textContent = `Showing individual model calls sorted by ${tableCaptionEl.dataset.sortDescription}. ${loadedRowsDescription()}.`;
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
          <td class="num">${escapeHtml(row.pricing_estimated ? `${money(row.estimated_cost_usd)}*` : money(row.estimated_cost_usd))}</td>
          <td class="num">${pct(row.cache_ratio)}</td>
          <td><div class="flags">${flags.slice(0, 2).map(flag => `<span class="flag">${escapeHtml(flag)}</span>`).join('')}</div></td>
        `;
        tr.addEventListener('mouseenter', () => showDetail(row));
        tr.addEventListener('click', () => showDetail(row));
        tr.addEventListener('keydown', event => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            showDetail(row);
          }
        });
        rowsEl.appendChild(tr);
      }
      if (!initialDetailApplied && urlParams.get('detail') === 'first' && page.items[0]) {
        initialDetailApplied = true;
        showDetail(page.items[0]);
      }
      if (!rows.length) {
        rowsEl.innerHTML = '<tr><td class="empty-state" colspan="8">No calls match the current filters.</td></tr>';
      }
    }
    function renderThreads(rows) {
      const groups = groupThreads(rows);
      if (!initialThreadExpansionApplied && activeView === 'threads') {
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
      tableTitleEl.textContent = 'Threads';
      tableCaptionEl.textContent = `Showing ${number.format(groups.length)} threads from ${number.format(rows.length)} filtered calls, sorted by ${tableCaptionEl.dataset.sortDescription}. ${loadedRowsDescription()}. Click a thread to expand its calls.`;
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
        tr.setAttribute('aria-label', `${expanded ? 'Collapse' : 'Expand'} ${group.label} calls`);
        tr.innerHTML = `
          <td>${renderTimeCell(group.latestActivity)}</td>
          <td>
            <div class="thread-title">
                <span class="thread-toggle" aria-hidden="true">${expanded ? '-' : '+'}</span>
              <span class="thread-meta">
                <span class="thread-name">${group.renderAsChild ? '<span class="thread-relation">spawned</span> ' : ''}${escapeHtml(truncate(group.label, 72))}</span>
                <span class="thread-subtle">${escapeHtml(threadNotes)}</span>
              </span>
            </div>
          </td>
          <td><span class="pill model-pill" data-full-label="${escapeHtml(short(group.modelSummary))}">${escapeHtml(short(group.modelSummary))}</span></td>
          <td>${escapeHtml(truncate(group.effortSummary, 28))}</td>
          <td class="num">${number.format(group.totalTokens)}</td>
          <td class="num">${pricingConfigured ? money(group.estimatedCost) : 'Not configured'}</td>
          <td class="num">${pct(group.cacheRatio)}</td>
          <td class="num">${number.format(group.signalCount)}</td>
        `;
        tr.addEventListener('click', () => {
          if (expandedThreads.has(group.key)) {
            expandedThreads.delete(group.key);
          } else {
            expandedThreads.add(group.key);
          }
          showThreadDetail(group);
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
            <td class="num">${escapeHtml(row.pricing_estimated ? `${money(row.estimated_cost_usd)}*` : money(row.estimated_cost_usd))}</td>
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
      const disabled = fileMode ? ' disabled' : '';
      const hint = fileMode
        ? 'Open this dashboard with codex-usage-tracker serve-dashboard to load raw context on demand.'
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
          headers: { 'Accept': 'application/json' },
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
    function showDetail(row) {
      const attachment = rowAttachment(row);
      const fields = [
        ['Thread', attachment.label],
        ['Thread attachment', attachment.relation],
        ['Session', row.session_id],
        ['Thread source', row.thread_source || 'user'],
        ['Subagent type', row.subagent_type || 'None'],
        ['Agent role', row.agent_role || 'None'],
        ['Agent nickname', row.agent_nickname || 'None'],
        ['Parent session', row.parent_session_id || 'None'],
        ['Parent thread', resolvedParentThreadName(row) || 'None'],
        ['Parent updated', resolvedParentSessionUpdatedAt(row) ? formatTimestamp(resolvedParentSessionUpdatedAt(row)) : 'None'],
        ['Turn', row.turn_id],
        ['Timestamp', formatTimestamp(row.event_timestamp)],
        ['Model', row.model],
        ['Reasoning', row.effort],
        ['Cwd', row.cwd],
        ['Last call total', number.format(row.total_tokens || 0)],
        ['Last call input', number.format(row.input_tokens || 0)],
        ['Cached input', number.format(row.cached_input_tokens || 0)],
        ['Uncached input', number.format(row.uncached_input_tokens || 0)],
        ['Output', number.format(row.output_tokens || 0)],
        ['Reasoning output', number.format(row.reasoning_output_tokens || 0)],
        ['Estimated cost', money(row.estimated_cost_usd)],
        ['Pricing model', row.pricing_model || 'No configured price'],
        ['Pricing status', row.pricing_estimated ? 'Best-guess estimate' : row.pricing_model ? 'Configured price' : 'No configured price'],
        ['Estimated cache savings', money(row.estimated_cache_savings_usd)],
        ['Efficiency signals', Array.isArray(row.efficiency_flags) && row.efficiency_flags.length ? row.efficiency_flags.join(', ') : 'None'],
        ['Session cumulative', number.format(row.cumulative_total_tokens || 0)],
        ['Context window', number.format(row.model_context_window || 0)],
        ['Context use', pct(row.context_window_percent)],
        ['Source line', `${row.source_file}:${row.line_number}`],
      ];
      detailEl.innerHTML = '<dl>' + fields.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(short(value))}</dd>`).join('') + '</dl>' + contextControls(row);
      bindContextButtons(row);
    }
    function showThreadDetail(group) {
      const fields = [
        ['Thread', group.label],
        ['Latest activity', formatTimestamp(group.latestActivity)],
        ['Calls', number.format(group.callCount)],
        ['Total tokens', number.format(group.totalTokens)],
        ['Estimated cost', pricingConfigured ? money(group.estimatedCost) : 'Not configured'],
        ['Cache ratio', pct(group.cacheRatio)],
        ['Pricing status', group.pricingStatus],
        ['Efficiency signals', number.format(group.signalCount)],
        ['Subagent calls', number.format(group.subagentCount)],
        ['Auto-review calls', number.format(group.autoReviewCount)],
        ['Attached calls', number.format(group.attachedCount)],
        ['Spawned from', group.parentThreadLabel || 'None'],
        ['Spawned threads', number.format(group.childThreadCount || 0)],
        ['Spawned child calls', number.format(group.childCallCount || 0)],
        ['Max context use', pct(group.maxContextUse)],
      ];
      detailEl.innerHTML = '<dl>' + fields.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(short(value))}</dd>`).join('') + '</dl>';
    }
    function setView(view) {
      activeView = view;
      currentPage = 1;
      render();
    }
    function updateLiveStatus(message) {
      liveStatusEl.textContent = message;
    }
    function updateToTopVisibility() {
      toTopEl.dataset.visible = window.scrollY > 320 ? 'true' : 'false';
    }
    function applyDashboardPayload(nextPayload) {
      data = payloadRows(nextPayload);
      pricingConfigured = Boolean(nextPayload.pricing_configured);
      pricingSource = nextPayload.pricing_source || {};
      totalAvailableRows = Number(nextPayload.total_available_rows || data.length);
      loadedLimit = payloadLimit(nextPayload);
      rebuildDashboardIndexes();
      rebuildFilterOptions();
      updatePricingSourceLine();
      updateLoadLimitControl();
      render();
    }
    async function refreshDashboardData(manual = false) {
      if (!liveRefreshSupported) {
        updateLiveStatus('Reloading static dashboard snapshot...');
        window.location.reload();
        return;
      }
      if (refreshInFlight) return;
      refreshInFlight = true;
      refreshDashboardEl.disabled = true;
      updateLiveStatus(manual ? 'Refreshing local usage index...' : 'Checking for new usage...');
      try {
        const params = new URLSearchParams({ refresh: '1', limit: loadLimitEl.value, _: String(Date.now()) });
        const response = await fetch(`/api/usage?${params.toString()}`, {
          headers: { 'Accept': 'application/json' },
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
        updateLiveStatus(`Updated ${formatTimestamp(nextPayload.refreshed_at)}. ${loadedRowsDescription()}.${indexed}${skipped}`);
      } catch (error) {
        const message = error.message || String(error);
        updateLiveStatus(`Live refresh unavailable: ${message}${manual ? '. Reload this page after regenerating a static dashboard, or run codex-usage-tracker serve-dashboard.' : ''}`);
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
    callsViewEl.addEventListener('click', () => setView('calls'));
    threadsViewEl.addEventListener('click', () => setView('threads'));
    refreshDashboardEl.addEventListener('click', () => refreshDashboardData(true));
    loadLimitEl.addEventListener('change', () => {
      currentPage = 1;
      if (liveRefreshSupported) {
        refreshDashboardData(true);
      } else {
        updateLiveStatus('Run codex-usage-tracker serve-dashboard to load a different history size from the dashboard.');
      }
    });
    autoRefreshEl.addEventListener('change', () => {
      scheduleAutoRefresh();
      updateLiveStatus(autoRefreshEl.checked ? `Live · polls every ${liveRefreshIntervalMs / 1000}s · ${loadedRowsDescription()}` : `Live paused · ${loadedRowsDescription()}`);
      if (autoRefreshEl.checked) refreshDashboardData(false);
    });
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && autoRefreshEl.checked) refreshDashboardData(false);
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
      if (row) showDetail(row);
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
      if (row) showDetail(row);
    });
    [searchEl, modelEl, effortEl, pricingStatusEl].forEach(el => el.addEventListener('input', () => {
      currentPage = 1;
      render();
    }));
    sortEl.addEventListener('input', () => setSort(sortEl.value, defaultSortDirection(sortEl.value)));
    rebuildDashboardIndexes();
    rebuildFilterOptions();
    updatePricingSourceLine();
    updateLoadLimitControl();
    if (!liveRefreshSupported) {
      autoRefreshEl.checked = false;
      autoRefreshEl.disabled = true;
      loadLimitEl.disabled = true;
      updateLiveStatus(`Static snapshot · ${loadedRowsDescription()}`);
    } else {
      updateLiveStatus(`Live · polls every ${liveRefreshIntervalMs / 1000}s · ${loadedRowsDescription()}`);
      scheduleAutoRefresh();
    }
    updateToTopVisibility();
    render();
