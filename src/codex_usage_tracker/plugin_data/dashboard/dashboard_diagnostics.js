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
    let requestGeneration = 0;
    let payloads = emptyPayloads();
    let selectedFactKey = '';
    const factCallPayloads = new Map();

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
      selectedFactKey = '';
      payloads = emptyPayloads();
      factCallPayloads.clear();
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
        diagnosticsPanelEl.innerHTML = renderState('Diagnostics require the live localhost dashboard API.');
        return;
      }
      const filters = getDiagnosticFilters(dateRange);
      const signature = JSON.stringify(filters);
      if (signature !== activeSignature) {
        activeSignature = signature;
        status = 'loading';
        errorMessage = '';
        selectedFactKey = '';
        payloads = emptyPayloads();
        factCallPayloads.clear();
        void fetchDiagnostics(signature, filters);
      }
      diagnosticsPanelEl.innerHTML = renderPanel();
    }

    async function fetchDiagnostics(signature, filters) {
      const generation = requestGeneration + 1;
      requestGeneration = generation;
      try {
        const [facts, tools, compactions] = await Promise.all([
          fetchPayload('/api/diagnostics/facts', { ...filters, limit: '50', sort: 'uncached', direction: 'desc' }),
          fetchPayload('/api/diagnostics/tools', { ...filters, limit: '25', sort: 'uncached', direction: 'desc' }),
          fetchPayload('/api/diagnostics/compactions', { ...filters, limit: '25', sort: 'uncached', direction: 'desc' }),
        ]);
        if (generation !== requestGeneration || signature !== activeSignature) return;
        payloads = { facts, tools, compactions };
        status = 'ready';
      } catch (error) {
        if (generation !== requestGeneration || signature !== activeSignature) return;
        errorMessage = error.message || String(error);
        status = 'error';
      }
      renderIfActive();
    }

    async function fetchFactCalls(factType, factName) {
      const key = factKey(factType, factName);
      const signature = activeSignature;
      if (selectedFactKey === key) {
        selectedFactKey = '';
        renderIfActive();
        return;
      }
      selectedFactKey = key;
      const cached = factCallPayloads.get(key);
      if (cached && cached.status === 'ready') {
        renderIfActive();
        return;
      }
      factCallPayloads.set(key, { status: 'loading', payload: null, error: '' });
      renderIfActive();
      try {
        const filters = getDiagnosticFilters();
        const payload = await fetchPayload('/api/diagnostics/fact-calls', {
          ...filters,
          fact_type: factType,
          fact_name: factName,
          limit: '25',
          sort: 'tokens',
          direction: 'desc',
        });
        if (signature !== activeSignature) return;
        factCallPayloads.set(key, { status: 'ready', payload, error: '' });
      } catch (error) {
        if (signature !== activeSignature) return;
        factCallPayloads.set(key, { status: 'error', payload: null, error: error.message || String(error) });
      }
      renderIfActive();
    }

    async function fetchPayload(path, params) {
      const urlParams = new URLSearchParams();
      Object.entries(params || {}).forEach(([key, value]) => {
        if (value === null || value === undefined || value === '') return;
        urlParams.set(key, String(value));
      });
      urlParams.set('_', String(Date.now()));
      const response = await fetch(`${path}?${urlParams.toString()}`, {
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
          <div class="diagnostics-readout">
            ${readoutMetric('Fact rows', payloads.facts)}
            ${readoutMetric('Tool/function rows', payloads.tools)}
            ${readoutMetric('Compaction rows', payloads.compactions)}
            <span class="diagnostics-note">Structured labels only. Raw context remains on-demand in the call investigator.</span>
          </div>
          ${renderFactSection('Top Diagnostic Facts', 'Ranked by associated uncached input tokens.', payloads.facts, loading)}
          ${renderFactSection('Tool and Function Activity', 'Tool/function facts associated with model calls.', payloads.tools, loading)}
          ${renderFactSection('Compaction Activity', 'Compaction facts and post-compaction associated costs.', payloads.compactions, loading)}
        </div>
      `;
    }

    function renderFactSection(title, caption, payload, loading) {
      const rows = Array.isArray(payload?.rows) ? payload.rows : [];
      return `
        <div class="diagnostics-section">
          <div class="diagnostics-section-header">
            <div>
              <h3>${escapeHtml(title)}</h3>
              <p>${escapeHtml(caption)}</p>
            </div>
            <span>${escapeHtml(payload ? `${number.format(payload.total_matched_rows || rows.length)} matched` : loading ? 'Loading' : 'No payload')}</span>
          </div>
          ${renderFactTable(rows, loading)}
        </div>
      `;
    }

    function renderFactTable(rows, loading) {
      if (loading && !rows.length) return renderState('Loading diagnostics...');
      if (!rows.length) return renderState('No diagnostic facts matched the current filters.');
      const body = rows.map(row => {
        const key = factKey(row.fact_type, row.fact_name);
        const selected = key === selectedFactKey;
        const largest = row.largest_record_id
          ? rowInvestigatorLink({ record_id: row.largest_record_id }, tokenText(row.largest_call_tokens), true)
          : tokenText(row.largest_call_tokens);
        return `
          <tr class="${selected ? 'selected-row' : ''}">
            <td>
              <div class="diagnostic-fact">
                <strong>${escapeHtml(row.fact_type || 'unknown')}/${escapeHtml(row.fact_name || 'unknown')}</strong>
                <span>${escapeHtml(row.fact_category || 'uncategorized')}</span>
              </div>
            </td>
            <td class="num">${number.format(Number(row.occurrences || 0))}</td>
            <td class="num">${number.format(Number(row.associated_calls || 0))}</td>
            <td class="num token-cell">${tokenText(row.associated_total_tokens)}</td>
            <td class="num token-cell">${tokenText(row.associated_cached_input_tokens)}</td>
            <td class="num token-cell">${tokenText(row.associated_uncached_input_tokens)}</td>
            <td class="num token-cell">${tokenText(row.associated_output_tokens)}</td>
            <td class="num">${pct(row.avg_cache_ratio)}</td>
            <td class="num">${largest}</td>
            <td>${escapeHtml(formatTimestamp(row.latest_event_timestamp || ''))}</td>
            <td><button class="toolbar-button diagnostics-expand-button" type="button" aria-expanded="${selected ? 'true' : 'false'}" aria-label="${selected ? 'Hide associated calls' : 'Show associated calls'}" data-diagnostics-fact-type="${escapeHtml(row.fact_type || '')}" data-diagnostics-fact-name="${escapeHtml(row.fact_name || '')}">${selected ? '-' : '+'}</button></td>
          </tr>
          ${selected ? `
            <tr class="diagnostics-drilldown-row">
              <td colspan="11">${renderFactCallsPanel()}</td>
            </tr>
          ` : ''}
        `;
      }).join('');
      return `
        <div class="diagnostics-table-wrap">
          <table class="diagnostics-table">
            <thead><tr>
              ${columnHeader('Fact', 'Diagnostic fact type and name derived from structured local log metadata. Raw prompts, assistant text, and tool output are not persisted.')}
              ${columnHeader('Occ', 'Occurrences: count of matching diagnostic fact events. One model call can contribute more than one occurrence.', 'num')}
              ${columnHeader('Calls', 'Distinct model calls associated with this diagnostic fact.', 'num')}
              ${columnHeader('Assoc total', 'Associated total tokens for those calls. Totals are not additive across facts because one call can have multiple facts.', 'num')}
              ${columnHeader('Cached', 'Associated cached input tokens for those calls.', 'num')}
              ${columnHeader('Uncached', 'Associated uncached input tokens for those calls.', 'num')}
              ${columnHeader('Output', 'Associated output tokens for those calls.', 'num')}
              ${columnHeader('Cache %', 'Average cache ratio across associated calls.', 'num')}
              ${columnHeader('Largest', 'Largest associated call by total tokens.', 'num')}
              ${columnHeader('Latest', 'Latest associated call timestamp.')}
              ${columnHeader('Action', 'Expand or collapse the associated calls.')}
            </tr></thead>
            <tbody>${body}</tbody>
          </table>
        </div>
      `;
    }

    function renderFactCallsPanel() {
      const entry = factCallPayloads.get(selectedFactKey);
      const label = selectedFactKey.replace('\u0000', '/');
      if (!entry || entry.status === 'loading') {
        return `<div class="diagnostics-drilldown">${renderState(`Loading calls for ${label}...`)}</div>`;
      }
      if (entry.status === 'error') {
        return `<div class="diagnostics-drilldown">${renderState(`Could not load calls for ${label}: ${entry.error}`)}</div>`;
      }
      const rows = Array.isArray(entry.payload?.rows) ? entry.payload.rows : [];
      if (!rows.length) {
        return `<div class="diagnostics-drilldown">${renderState(`No calls found for ${label}.`)}</div>`;
      }
      const body = rows.map(row => `
        <tr class="thread-call-row" data-record-id="${escapeHtml(row.record_id || '')}">
          <td>${rowInvestigatorLink(row, renderTimeCell(row.event_timestamp), true)}</td>
          <td>${rowInvestigatorLink(row, escapeHtml(row.thread_name || row.parent_thread_name || row.session_id || 'Unknown'))}</td>
          <td>${rowInvestigatorLink(row, `<span class="pill model-pill" data-full-label="${escapeHtml(row.model || 'Unknown')}">${escapeHtml(row.model || 'Unknown')}</span>`)}</td>
          <td>${rowInvestigatorLink(row, escapeHtml(row.effort || 'unknown'))}</td>
          <td class="num token-cell">${rowInvestigatorLink(row, tokenText(row.total_tokens))}</td>
          <td class="num token-cell">${rowInvestigatorLink(row, tokenText(row.cached_input_tokens))}</td>
          <td class="num token-cell">${rowInvestigatorLink(row, tokenText(row.uncached_input_tokens))}</td>
          <td class="num token-cell">${rowInvestigatorLink(row, tokenText(row.output_tokens))}</td>
          <td class="num token-cell">${rowInvestigatorLink(row, tokenText(row.reasoning_output_tokens))}</td>
          <td class="num">${rowInvestigatorLink(row, pct(row.cache_ratio))}</td>
        </tr>
      `).join('');
      return `
        <div class="diagnostics-drilldown">
          <div class="diagnostics-section-header">
            <div>
              <h3>Associated Calls</h3>
              <p>${escapeHtml(label)} sorted by associated call tokens.</p>
            </div>
            <span>${escapeHtml(`${number.format(entry.payload.total_matched_rows || rows.length)} matched`)}</span>
          </div>
          <div class="diagnostics-table-wrap">
            <table class="diagnostics-table diagnostics-call-table">
              <thead><tr>
                <th>Time</th>
                <th>Thread</th>
                <th>Model</th>
                <th>Effort</th>
                ${columnHeader('Tokens', 'Total tokens for this associated model call.', 'num')}
                ${columnHeader('Cached', 'Cached input tokens for this associated model call.', 'num')}
                ${columnHeader('Uncached', 'Uncached input tokens for this associated model call.', 'num')}
                ${columnHeader('Output', 'Output tokens for this associated model call.', 'num')}
                ${columnHeader('Reasoning', 'Reasoning output tokens for this associated model call.', 'num')}
                ${columnHeader('Cache %', 'Cache ratio for this associated model call.', 'num')}
              </tr></thead>
              <tbody>${body}</tbody>
            </table>
          </div>
        </div>
      `;
    }

    function readoutMetric(label, payload) {
      const count = payload ? Number(payload.total_matched_rows || payload.row_count || 0) : 0;
      return `<span><b>${number.format(count)}</b>${escapeHtml(label)}</span>`;
    }

    function renderState(message) {
      return `<div class="empty-state diagnostics-empty">${escapeHtml(message)}</div>`;
    }

    function tokenText(value) {
      return number.format(Math.round(Number(value || 0)));
    }

    function columnHeader(label, tooltip, className = '') {
      const classAttr = className ? ` class="${escapeHtml(className)}"` : '';
      const tooltipAttr = tooltipAttributes(tooltip);
      return `<th${classAttr}${tooltipAttr ? ` ${tooltipAttr}` : ''}>${escapeHtml(label)}</th>`;
    }

    function factKey(factType, factName) {
      return `${factType || ''}\u0000${factName || ''}`;
    }

    function emptyPayloads() {
      return { facts: null, tools: null, compactions: null };
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
      const button = target.closest('[data-diagnostics-fact-type][data-diagnostics-fact-name]');
      if (!button || !diagnosticsPanelEl.contains(button)) return;
      event.preventDefault();
      event.stopPropagation();
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
