(() => {
  function createFactRenderer(deps) {
    const {
      escapeHtml,
      factCallRows,
      factCallsHasMore,
      factCallSortState,
      factKey,
      factSortState,
      formatTimestamp,
      getFactCallEntry,
      getSelectedFactKey,
      number,
      pct,
      renderState,
      renderTimeCell,
      rowInvestigatorLink,
      t,
      tokenText,
      tooltipAttributes = () => '',
    } = deps;

    function renderFactSection(sectionKey, title, caption, payload, loading) {
      const rows = Array.isArray(payload?.rows) ? payload.rows : [];
      return `
        <div class="diagnostics-section">
          <div class="diagnostics-section-header">
            <div>
              <h3>${escapeHtml(title)}</h3>
              <p>${escapeHtml(`${caption} Sorted by ${diagnosticFactSortDescription(sectionKey)}.`)}</p>
            </div>
            <span>${escapeHtml(payload ? `${number.format(payload.total_matched_rows || rows.length)} matched` : loading ? 'Loading' : 'No payload')}</span>
          </div>
          ${renderFactTable(sectionKey, rows, loading)}
        </div>
      `;
    }

    function renderFactTable(sectionKey, rows, loading) {
      if (loading && !rows.length) return renderState('Loading diagnostics...');
      if (!rows.length) return renderState('No diagnostic facts matched the current filters.');
      const selectedFactKey = getSelectedFactKey();
      const body = rows.map(row => {
        const key = factKey(row.fact_type, row.fact_name);
        const selected = key === selectedFactKey;
        const largest = row.largest_record_id
          ? rowInvestigatorLink({ record_id: row.largest_record_id }, tokenText(row.largest_call_tokens), true)
          : tokenText(row.largest_call_tokens);
        return `
          <tr class="${selected ? 'selected-row' : ''}">
            <td class="diagnostics-fact-cell">
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
          <table class="diagnostics-table diagnostics-facts-table">
            <colgroup>
              <col class="diagnostics-fact-col">
              <col class="diagnostics-count-col">
              <col class="diagnostics-count-col">
              <col class="diagnostics-token-col">
              <col class="diagnostics-token-col">
              <col class="diagnostics-token-col">
              <col class="diagnostics-token-col">
              <col class="diagnostics-ratio-col">
              <col class="diagnostics-token-col">
              <col class="diagnostics-latest-col">
              <col class="diagnostics-action-col">
            </colgroup>
            <thead><tr>
              ${diagnosticFactHeader(sectionKey, 'fact', 'Fact', false, 'Diagnostic fact type and name derived from structured local log metadata. Raw prompts, assistant text, and tool output are not persisted.')}
              ${diagnosticFactHeader(sectionKey, 'occurrences', 'Occ', true, 'Occurrences: count of matching diagnostic fact events. One model call can contribute more than one occurrence.')}
              ${diagnosticFactHeader(sectionKey, 'calls', 'Calls', true, 'Distinct model calls associated with this diagnostic fact.')}
              ${diagnosticFactHeader(sectionKey, 'tokens', 'Assoc total', true, 'Associated total tokens for those calls. Totals are not additive across facts because one call can have multiple facts.')}
              ${diagnosticFactHeader(sectionKey, 'cached', 'Cached', true, 'Associated cached input tokens for those calls.')}
              ${diagnosticFactHeader(sectionKey, 'uncached', 'Uncached', true, 'Associated uncached input tokens for those calls.')}
              ${diagnosticFactHeader(sectionKey, 'output', 'Output', true, 'Associated output tokens for those calls.')}
              ${diagnosticFactHeader(sectionKey, 'cache', 'Cache %', true, 'Average cache ratio across associated calls.')}
              ${diagnosticFactHeader(sectionKey, 'largest', 'Largest', true, 'Largest associated call by total tokens.')}
              ${diagnosticFactHeader(sectionKey, 'time', 'Latest', false, 'Latest associated call timestamp.')}
              ${columnHeader('Action', 'Expand or collapse the associated calls.')}
            </tr></thead>
            <tbody>${body}</tbody>
          </table>
        </div>
      `;
    }

    function renderFactCallsPanel() {
      const selectedFactKey = getSelectedFactKey();
      const entry = getFactCallEntry(selectedFactKey);
      const label = selectedFactKey.replace('\u0000', '/');
      if (!entry || (entry.status === 'loading' && !entry.payload)) {
        return `<div class="diagnostics-drilldown">${renderState(`Loading calls for ${label}...`)}</div>`;
      }
      if (entry.status === 'error' && !entry.payload) {
        return `<div class="diagnostics-drilldown">${renderState(`Could not load calls for ${label}: ${entry.error}`)}</div>`;
      }
      const rows = factCallRows(entry.payload);
      if (!rows.length) {
        return `<div class="diagnostics-drilldown">${renderState(`No calls found for ${label}.`)}</div>`;
      }
      const total = Number(entry.payload?.total_matched_rows || rows.length);
      const loadingMore = entry.status === 'appending';
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
              <p>${escapeHtml(`${label} sorted by ${diagnosticCallSortDescription()}.`)}</p>
            </div>
            <span>${escapeHtml(`${number.format(total)} matched`)}</span>
          </div>
          <div class="diagnostics-table-wrap">
            <table class="diagnostics-table diagnostics-call-table">
              <thead><tr>
                ${diagnosticCallHeader('time', 'Time', false, 'Call timestamp.')}
                ${diagnosticCallHeader('thread', 'Thread', false, 'Resolved thread, parent thread, or session label.')}
                ${diagnosticCallHeader('model', 'Model', false, 'Model label for this associated call.')}
                ${diagnosticCallHeader('effort', 'Effort', false, 'Reasoning effort label for this associated call.')}
                ${diagnosticCallHeader('tokens', 'Tokens', true, 'Total tokens for this associated model call.')}
                ${diagnosticCallHeader('cached', 'Cached', true, 'Cached input tokens for this associated model call.')}
                ${diagnosticCallHeader('uncached', 'Uncached', true, 'Uncached input tokens for this associated model call.')}
                ${diagnosticCallHeader('output', 'Output', true, 'Output tokens for this associated model call.')}
                ${diagnosticCallHeader('reasoning', 'Reasoning', true, 'Reasoning output tokens for this associated model call.')}
                ${diagnosticCallHeader('cache', 'Cache %', true, 'Cache ratio for this associated model call.')}
              </tr></thead>
              <tbody>${body}</tbody>
            </table>
            ${renderFactCallPager(entry, rows.length, total, loadingMore)}
          </div>
          ${entry.error ? `<div class="diagnostics-inline-error">${escapeHtml(`Could not load more calls: ${entry.error}`)}</div>` : ''}
        </div>
      `;
    }

    function renderFactCallPager(entry, loaded, total, loadingMore) {
      const canLoadMore = loadingMore || factCallsHasMore(entry.payload);
      const statusText = `Showing ${number.format(loaded)} of ${number.format(total)} calls`;
      if (!canLoadMore) {
        return `<div class="child-load-more diagnostics-call-load-more"><span>${escapeHtml(statusText)}</span></div>`;
      }
      return `
        <div class="child-load-more diagnostics-call-load-more">
          <span>${escapeHtml(statusText)}</span>
          <button class="pager-button" type="button" data-diagnostics-call-load-more ${loadingMore ? 'disabled' : ''}>${escapeHtml(loadingMore ? 'Loading...' : t('button.load_more'))}</button>
        </div>
      `;
    }

    function readoutMetric(label, payload) {
      const count = payload ? Number(payload.total_matched_rows || payload.row_count || 0) : 0;
      return `<span><b>${number.format(count)}</b>${escapeHtml(label)}</span>`;
    }

    function columnHeader(label, tooltip, className = '') {
      const classAttr = className ? ` class="${escapeHtml(className)}"` : '';
      const tooltipAttr = tooltipAttributes(tooltip);
      return `<th${classAttr}${tooltipAttr ? ` ${tooltipAttr}` : ''}>${escapeHtml(label)}</th>`;
    }

    function diagnosticFactHeader(sectionKey, sortKey, label, numeric = false, tooltip = '') {
      const state = factSortState(sectionKey);
      const active = state.sort === sortKey;
      const indicator = active ? (state.direction === 'asc' ? '▲' : '▼') : '';
      const ariaSort = active ? (state.direction === 'asc' ? 'ascending' : 'descending') : 'none';
      const tooltipAttr = tooltipAttributes(tooltip);
      return `
        <th${numeric ? ' class="num"' : ''} data-diagnostics-fact-sort-active="${active ? 'true' : 'false'}" aria-sort="${ariaSort}"${tooltipAttr ? ` ${tooltipAttr}` : ''}>
          <button class="sort-header child-sort-header" type="button" data-diagnostics-fact-section="${escapeHtml(sectionKey)}" data-diagnostics-fact-sort-key="${escapeHtml(sortKey)}">
            <span>${escapeHtml(label)}</span>
            <span class="sort-indicator">${escapeHtml(indicator)}</span>
          </button>
        </th>
      `;
    }

    function diagnosticCallHeader(sortKey, label, numeric = false, tooltip = '') {
      const state = factCallSortState(getSelectedFactKey());
      const active = state.sort === sortKey;
      const indicator = active ? (state.direction === 'asc' ? '▲' : '▼') : '';
      const ariaSort = active ? (state.direction === 'asc' ? 'ascending' : 'descending') : 'none';
      const tooltipAttr = tooltipAttributes(tooltip);
      return `
        <th${numeric ? ' class="num"' : ''} data-diagnostics-call-sort-active="${active ? 'true' : 'false'}" aria-sort="${ariaSort}"${tooltipAttr ? ` ${tooltipAttr}` : ''}>
          <button class="sort-header child-sort-header" type="button" data-diagnostics-call-sort-key="${escapeHtml(sortKey)}">
            <span>${escapeHtml(label)}</span>
            <span class="sort-indicator">${escapeHtml(indicator)}</span>
          </button>
        </th>
      `;
    }

    function diagnosticFactSortDescription(sectionKey) {
      const state = factSortState(sectionKey);
      const labels = factSortLabels();
      const label = labels[state.sort] || state.sort;
      return `${label} ${state.direction === 'asc' ? 'ascending' : 'descending'}`;
    }

    function diagnosticCallSortDescription() {
      const state = factCallSortState(getSelectedFactKey());
      const labels = callSortLabels();
      const label = labels[state.sort] || state.sort;
      return `${label} ${state.direction === 'asc' ? 'ascending' : 'descending'}`;
    }

    function factSortLabels() {
      return {
        cache: 'cache ratio',
        cached: 'cached input tokens',
        calls: 'associated calls',
        fact: 'fact name',
        largest: 'largest call',
        occurrences: 'occurrences',
        output: 'output tokens',
        time: 'latest call time',
        tokens: 'total tokens',
        uncached: 'uncached input tokens',
      };
    }

    function callSortLabels() {
      return {
        cache: 'cache ratio',
        cached: 'cached input tokens',
        effort: 'effort',
        input: 'input tokens',
        model: 'model',
        output: 'output tokens',
        reasoning: 'reasoning output tokens',
        thread: 'thread',
        time: 'time',
        tokens: 'total tokens',
        uncached: 'uncached input tokens',
      };
    }

    return {
      callSortLabels,
      factSortLabels,
      readoutMetric,
      renderFactSection,
    };
  }

  window.CodexUsageDashboardDiagnosticFacts = { create: createFactRenderer };
})();
