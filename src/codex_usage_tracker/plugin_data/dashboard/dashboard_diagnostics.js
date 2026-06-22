(() => {
  function createDiagnosticsRuntime(deps) {
    const {
      apiToken,
      diagnosticsPanelEl,
      escapeHtml,
      formatTimestamp,
      getDiagnosticFilters,
      isActive,
      liveRefreshSupported,
      number,
      openInvestigatorUrl,
      pagerEl,
      pct,
      renderDashboard,
      renderTimeCell,
      rowInvestigatorLink,
      rowLoadProgressEl,
      rowsEl,
      tableCaptionEl,
      tableTitleEl,
      t,
      tooltipAttributes = () => '',
      usageTableEl,
    } = deps;

    let activeSignature = '';
    let status = 'idle';
    let errorMessage = '';
    let snapshotRefreshStatus = 'idle';
    let snapshotRefreshError = '';
    let requestGeneration = 0;
    let payloads = emptyPayloads();
    let selectedFactKey = '';
    let pendingScrollAnchor = null;
    const factCallPageSize = 25;
    const factCallPayloads = new Map();
    const factCallSorts = new Map();
    const factSorts = new Map();
    const snapshotRenderer = window.CodexUsageDashboardDiagnosticSnapshots.create({
      escapeHtml,
      formatTimestamp,
      number,
      pct,
      renderState,
      rowInvestigatorLink,
      tokenText,
    });
    const factRenderer = window.CodexUsageDashboardDiagnosticFacts.create({
      escapeHtml,
      factCallRows,
      factCallsHasMore,
      factCallSortState,
      factKey,
      factSortState,
      formatTimestamp,
      getFactCallEntry: key => factCallPayloads.get(key),
      getSelectedFactKey: () => selectedFactKey,
      number,
      pct,
      renderState,
      renderTimeCell,
      rowInvestigatorLink,
      t,
      tokenText,
      tooltipAttributes,
    });
    function setActive(active) {
      diagnosticsPanelEl.hidden = !active;
      if (usageTableEl) usageTableEl.hidden = active;
      if (active) {
        pagerEl.hidden = true;
        rowLoadProgressEl.hidden = true;
      }
    }

    function invalidate() {
      activeSignature = '';
      status = 'idle';
      errorMessage = '';
      snapshotRefreshStatus = 'idle';
      snapshotRefreshError = '';
      selectedFactKey = '';
      payloads = emptyPayloads();
      factCallPayloads.clear();
      factCallSorts.clear();
      factSorts.clear();
    }

    function renderDiagnostics(dateRange) {
      setActive(true);
      rowsEl.textContent = '';
      tableTitleEl.textContent = t('dashboard.view.diagnostics');
      tableCaptionEl.textContent = 'Associated token totals by structured diagnostic facts. Totals are not additive when one call has multiple facts.';
      if (dateRange && dateRange.invalid) {
        diagnosticsPanelEl.innerHTML = renderState(t('date.invalid_range'));
        return;
      }
      if (!liveRefreshSupported) {
        diagnosticsPanelEl.innerHTML = renderState('Live API required for diagnostics refresh.');
        return;
      }
      const filters = getDiagnosticFilters(dateRange);
      const signature = JSON.stringify(filters);
      if (signature !== activeSignature) {
        activeSignature = signature;
        status = 'loading';
        errorMessage = '';
        snapshotRefreshStatus = 'idle';
        snapshotRefreshError = '';
        selectedFactKey = '';
        payloads = emptyPayloads();
        factCallPayloads.clear();
        void fetchDiagnostics(signature, filters);
      }
      diagnosticsPanelEl.innerHTML = renderPanel();
      restoreScrollAnchor();
    }

    async function fetchDiagnostics(signature, filters) {
      const generation = requestGeneration + 1;
      requestGeneration = generation;
      try {
        const factsSort = factSortState('facts');
        const toolsSort = factSortState('tools');
        const compactionsSort = factSortState('compactions');
        const [facts, tools, compactions, snapshots] = await Promise.all([
          fetchPayload('/api/diagnostics/facts', { ...filters, limit: '50', sort: factsSort.sort, direction: factsSort.direction }),
          fetchPayload('/api/diagnostics/tools', { ...filters, limit: '25', sort: toolsSort.sort, direction: toolsSort.direction }),
          fetchPayload('/api/diagnostics/compactions', { ...filters, limit: '25', sort: compactionsSort.sort, direction: compactionsSort.direction }),
          fetchSnapshotPayloads(filters, false),
        ]);
        if (generation !== requestGeneration || signature !== activeSignature) return;
        payloads = { facts, tools, compactions, ...snapshots };
        status = 'ready';
      } catch (error) {
        if (generation !== requestGeneration || signature !== activeSignature) return;
        errorMessage = error.message || String(error);
        status = 'error';
      }
      renderIfActive();
    }

    async function fetchSnapshotPayloads(filters, refresh) {
      const snapshotFilters = { include_archived: filters?.include_archived || '0' };
      const entries = await Promise.all(snapshotRenderer.sections.map(async section => {
        const payload = await fetchPayload(
          refresh ? section.refreshPath : section.path,
          snapshotFilters,
          refresh ? { method: 'POST' } : {},
        );
        return [section.key, payload];
      }));
      return Object.fromEntries(entries);
    }

    async function refreshDiagnosticSnapshots() {
      if (snapshotRefreshStatus === 'refreshing') return;
      const signature = activeSignature;
      snapshotRefreshStatus = 'refreshing';
      snapshotRefreshError = '';
      renderIfActive();
      try {
        const filters = getDiagnosticFilters();
        const snapshotFilters = { include_archived: filters?.include_archived || '0' };
        const refreshPayload = await fetchPayload(
          '/api/diagnostics/refresh',
          snapshotFilters,
          { method: 'POST' },
        );
        const snapshots = refreshPayload.sections || {};
        if (signature !== activeSignature) return;
        payloads = { ...payloads, ...snapshots };
        snapshotRefreshStatus = 'ready';
      } catch (error) {
        if (signature !== activeSignature) return;
        snapshotRefreshStatus = 'error';
        snapshotRefreshError = error.message || String(error);
      }
      renderIfActive();
    }

    async function fetchFactCalls(factType, factName, options = {}) {
      const key = factKey(factType, factName);
      const append = Boolean(options.append);
      const force = Boolean(options.force);
      const signature = activeSignature;
      if (!append && !force && selectedFactKey === key) {
        selectedFactKey = '';
        renderIfActive();
        return;
      }
      selectedFactKey = key;
      const cached = factCallPayloads.get(key);
      const sortState = factCallSortState(key);
      if (!append && !force && cached && cached.status === 'ready' && cached.sort === sortState.sort && cached.direction === sortState.direction) {
        renderIfActive();
        return;
      }
      if (append && (!cached || cached.status === 'appending' || !factCallsHasMore(cached.payload))) {
        return;
      }
      const previousPayload = cached && cached.payload ? cached.payload : null;
      const offset = append ? factCallRows(previousPayload).length : 0;
      factCallPayloads.set(key, {
        status: append ? 'appending' : 'loading',
        payload: previousPayload,
        error: '',
        sort: sortState.sort,
        direction: sortState.direction,
      });
      renderIfActive();
      try {
        const filters = getDiagnosticFilters();
        const payload = await fetchPayload('/api/diagnostics/fact-calls', {
          ...filters,
          fact_type: factType,
          fact_name: factName,
          limit: String(factCallPageSize),
          offset: String(offset),
          sort: sortState.sort,
          direction: sortState.direction,
        });
        if (signature !== activeSignature) return;
        factCallPayloads.set(key, {
          status: 'ready',
          payload: append ? mergeFactCallPayload(previousPayload, payload) : payload,
          error: '',
          sort: sortState.sort,
          direction: sortState.direction,
        });
      } catch (error) {
        if (signature !== activeSignature) return;
        factCallPayloads.set(key, {
          status: append && previousPayload ? 'ready' : 'error',
          payload: append ? previousPayload : null,
          error: error.message || String(error),
          sort: sortState.sort,
          direction: sortState.direction,
        });
      }
      renderIfActive();
    }

    function sortFactRows(sectionKey, sortKey) {
      if (!factRenderer.factSortLabels()[sortKey]) return;
      const current = factSortState(sectionKey);
      const next = current.sort === sortKey
        ? { sort: sortKey, direction: current.direction === 'asc' ? 'desc' : 'asc' }
        : { sort: sortKey, direction: defaultFactSortDirection(sortKey) };
      factSorts.set(sectionKey, next);
      status = 'loading';
      errorMessage = '';
      const filters = getDiagnosticFilters();
      void fetchDiagnostics(activeSignature, filters);
      renderIfActive();
    }

    function sortFactCalls(sortKey) {
      if (!selectedFactKey || !factRenderer.callSortLabels()[sortKey]) return;
      const current = factCallSortState(selectedFactKey);
      const next = current.sort === sortKey
        ? { sort: sortKey, direction: current.direction === 'asc' ? 'desc' : 'asc' }
        : { sort: sortKey, direction: defaultFactCallSortDirection(sortKey) };
      factCallSorts.set(selectedFactKey, next);
      const [factType, factName] = splitFactKey(selectedFactKey);
      void fetchFactCalls(factType, factName, { force: true });
    }

    async function fetchPayload(path, params, options = {}) {
      const urlParams = new URLSearchParams();
      Object.entries(params || {}).forEach(([key, value]) => {
        if (value === null || value === undefined || value === '') return;
        urlParams.set(key, String(value));
      });
      urlParams.set('_', String(Date.now()));
      const response = await fetch(`${path}?${urlParams.toString()}`, {
        method: options.method || 'GET',
        headers: {
          'Accept': 'application/json',
          'X-Codex-Usage-Token': apiToken(),
        },
        cache: 'no-store',
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      if (payload.error) throw new Error(payload.error);
      return payload;
    }

    function renderPanel() {
      if (status === 'error') return renderState(`Diagnostics unavailable: ${errorMessage}`);
      const loading = status === 'loading';
      return `
        <div class="diagnostics-stack">
          ${snapshotRenderer.renderToolbar({
            loading,
            payloads,
            refreshStatus: snapshotRefreshStatus,
            refreshError: snapshotRefreshError,
          })}
          <div class="diagnostics-readout">
            ${factRenderer.readoutMetric('Fact rows', payloads.facts)}
            ${factRenderer.readoutMetric('Tool/function rows', payloads.tools)}
            ${factRenderer.readoutMetric('Compaction rows', payloads.compactions)}
            ${snapshotRenderer.readoutMetric('Snapshot sections', snapshotRenderer.readyCount(payloads))}
            <span class="diagnostics-note">Structured labels only. Raw context remains on-demand in the call investigator.</span>
          </div>
          ${snapshotRenderer.renderPanels({ loading, payloads })}
          ${factRenderer.renderFactSection('facts', 'Top Diagnostic Facts', 'Structured facts associated with model calls.', payloads.facts, loading)}
          ${factRenderer.renderFactSection('tools', 'Tool and Function Activity', 'Tool/function facts associated with model calls.', payloads.tools, loading)}
          ${factRenderer.renderFactSection('compactions', 'Compaction Activity', 'Compaction facts and post-compaction associated costs.', payloads.compactions, loading)}
        </div>
      `;
    }

    function renderState(message) {
      return `<div class="empty-state diagnostics-empty">${escapeHtml(message)}</div>`;
    }

    function tokenText(value) {
      return number.format(Math.round(Number(value || 0)));
    }

    function factSortState(sectionKey) {
      return factSorts.get(sectionKey) || { sort: 'uncached', direction: 'desc' };
    }

    function defaultFactSortDirection(sortKey) {
      return sortKey === 'fact' ? 'asc' : 'desc';
    }

    function factCallSortState(key) {
      return factCallSorts.get(key) || { sort: 'tokens', direction: 'desc' };
    }

    function defaultFactCallSortDirection(sortKey) {
      return ['effort', 'model', 'thread'].includes(sortKey) ? 'asc' : 'desc';
    }

    function factCallRows(payload) {
      return Array.isArray(payload?.rows) ? payload.rows : [];
    }

    function factCallsHasMore(payload) {
      if (!payload) return false;
      const loaded = factCallRows(payload).length;
      const total = Number(payload.total_matched_rows || loaded);
      return Boolean(payload.truncated) && loaded < total;
    }

    function mergeFactCallPayload(previousPayload, nextPayload) {
      const previousRows = factCallRows(previousPayload);
      const mergedRows = previousRows.slice();
      const seenRecordIds = new Set(previousRows.map(row => row.record_id).filter(Boolean));
      factCallRows(nextPayload).forEach(row => {
        const recordId = row.record_id || '';
        if (recordId && seenRecordIds.has(recordId)) return;
        if (recordId) seenRecordIds.add(recordId);
        mergedRows.push(row);
      });
      const total = Number(nextPayload.total_matched_rows || previousPayload?.total_matched_rows || mergedRows.length);
      const madeProgress = mergedRows.length > previousRows.length;
      return {
        ...nextPayload,
        rows: mergedRows,
        row_count: mergedRows.length,
        total_matched_rows: total,
        truncated: madeProgress && mergedRows.length < total,
        filters: {
          ...(nextPayload.filters || {}),
          offset: 0,
        },
      };
    }

    function factKey(factType, factName) {
      return `${factType || ''}\u0000${factName || ''}`;
    }

    function splitFactKey(key) {
      const delimiter = key.indexOf('\u0000');
      if (delimiter < 0) return [key, ''];
      return [key.slice(0, delimiter), key.slice(delimiter + 1)];
    }

    function captureScrollAnchor(element, key, type = 'fact') {
      if (!element || !element.getBoundingClientRect) return;
      pendingScrollAnchor = {
        key,
        type,
        top: element.getBoundingClientRect().top,
        scrollY: window.scrollY,
      };
    }

    function captureScrollPosition() {
      pendingScrollAnchor = {
        key: '',
        type: 'scroll',
        top: 0,
        scrollY: window.scrollY,
      };
    }

    function restoreScrollAnchor() {
      if (!pendingScrollAnchor) return;
      const anchor = pendingScrollAnchor;
      pendingScrollAnchor = null;
      if (anchor.type === 'scroll') {
        window.requestAnimationFrame(() => {
          window.scrollTo({ top: anchor.scrollY, behavior: 'auto' });
        });
        return;
      }
      window.requestAnimationFrame(() => {
        const target = anchor.type === 'load-more'
          ? diagnosticsPanelEl.querySelector('[data-diagnostics-call-load-more]')
          : findFactButton(anchor.key);
        const fallback = findFactButton(anchor.key);
        const element = target || fallback;
        if (!element || !element.getBoundingClientRect) {
          window.scrollTo({ top: anchor.scrollY, behavior: 'auto' });
          return;
        }
        const delta = element.getBoundingClientRect().top - anchor.top;
        if (Math.abs(delta) > 1) {
          window.scrollBy({ top: delta, behavior: 'auto' });
        }
      });
    }

    function findFactButton(key) {
      const [factType, factName] = splitFactKey(key);
      return Array.from(diagnosticsPanelEl.querySelectorAll('[data-diagnostics-fact-type][data-diagnostics-fact-name]')).find(button => {
        return button.dataset.diagnosticsFactType === factType && button.dataset.diagnosticsFactName === factName;
      }) || null;
    }

    function emptyPayloads() {
      return {
        facts: null,
        tools: null,
        compactions: null,
        overview: null,
        toolOutput: null,
        commands: null,
        gitInteractions: null,
        fileReads: null,
        fileModifications: null,
        readProductivity: null,
        concentration: null,
        usageDrain: null,
      };
    }

    function renderIfActive() {
      if (isActive()) renderDashboard();
    }

    diagnosticsPanelEl.addEventListener('click', event => {
      const target = event.target;
      if (!target || !target.closest) return;
      const link = target.closest('a.row-investigator-link');
      if (link && diagnosticsPanelEl.contains(link) && liveRefreshSupported) {
        event.preventDefault();
        event.stopPropagation();
        void openInvestigatorUrl(link.href);
        return;
      }
      const refreshButton = target.closest('[data-diagnostics-refresh]');
      if (refreshButton && diagnosticsPanelEl.contains(refreshButton)) {
        event.preventDefault();
        event.stopPropagation();
        void refreshDiagnosticSnapshots();
        return;
      }
      const loadMoreButton = target.closest('[data-diagnostics-call-load-more]');
      if (loadMoreButton && diagnosticsPanelEl.contains(loadMoreButton)) {
        event.preventDefault();
        event.stopPropagation();
        if (!selectedFactKey) return;
        captureScrollAnchor(loadMoreButton, selectedFactKey, 'load-more');
        const [factType, factName] = splitFactKey(selectedFactKey);
        void fetchFactCalls(factType, factName, { append: true });
        return;
      }
      const factSortButton = target.closest('[data-diagnostics-fact-sort-key]');
      if (factSortButton && diagnosticsPanelEl.contains(factSortButton)) {
        event.preventDefault();
        event.stopPropagation();
        captureScrollPosition();
        sortFactRows(
          factSortButton.dataset.diagnosticsFactSection || 'facts',
          factSortButton.dataset.diagnosticsFactSortKey || '',
        );
        return;
      }
      const sortButton = target.closest('[data-diagnostics-call-sort-key]');
      if (sortButton && diagnosticsPanelEl.contains(sortButton)) {
        event.preventDefault();
        event.stopPropagation();
        if (!selectedFactKey) return;
        captureScrollAnchor(sortButton, selectedFactKey, 'fact');
        sortFactCalls(sortButton.dataset.diagnosticsCallSortKey || '');
        return;
      }
      const button = target.closest('[data-diagnostics-fact-type][data-diagnostics-fact-name]');
      if (!button || !diagnosticsPanelEl.contains(button)) return;
      event.preventDefault();
      event.stopPropagation();
      const key = factKey(button.dataset.diagnosticsFactType || '', button.dataset.diagnosticsFactName || '');
      captureScrollAnchor(button, key);
      void fetchFactCalls(button.dataset.diagnosticsFactType || '', button.dataset.diagnosticsFactName || '');
    });

    return {
      invalidate,
      renderDiagnostics,
      setActive,
    };
  }

  window.CodexUsageDashboardDiagnostics = { create: createDiagnosticsRuntime };
})();
