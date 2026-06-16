(() => {
  function create(deps) {
    const {
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
      getActiveView,
      getInitialDetailApplied,
      getInitialThreadExpansionApplied,
      getPricingConfigured,
      getSelectedRecordId,
      getSelectedThreadKey,
      getThreadCallSortDirection,
      getThreadCallSortKey,
      getThreadCallVisiblePages,
      initialUrlParams,
      loadedRowsDescription,
      moneyText,
      number,
      outputTokenCell,
      pct,
      renderTimeCell,
      renderWithState,
      rowInvestigatorLink,
      rowThreadLabel,
      rowsEl,
      rowsNeedHydration,
      selectThread,
      setInitialDetailApplied,
      setInitialThreadExpansionApplied,
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
      tooltipAttributes,
      totalTokenCell,
      translateEffort,
      truncate,
      uncachedTokenCell,
      updateLoadMoreControl,
      usageCreditValue,
      visibleSlice,
      groupThreads,
    } = deps;

    function threadCallHeader(key, label, numeric = false) {
      const active = getThreadCallSortKey() === key;
      const indicator = active ? (getThreadCallSortDirection() === 'asc' ? '▲' : '▼') : '';
      const ariaSort = active ? (getThreadCallSortDirection() === 'asc' ? 'ascending' : 'descending') : 'none';
      return `
        <th${numeric ? ' class="num"' : ''} data-thread-call-sort-active="${active ? 'true' : 'false'}" aria-sort="${ariaSort}">
          <button class="sort-header child-sort-header" type="button" data-thread-call-sort-key="${escapeHtml(key)}">
            <span>${escapeHtml(label)}</span>
            <span class="sort-indicator">${escapeHtml(indicator)}</span>
          </button>
        </th>
      `;
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
        const threadLabel = rowThreadLabel(row);
        const threadTooltip = `${threadLabel} - ${short(row.session_id)}`;
        tr.className = `call-row${getSelectedRecordId() === row.record_id ? ' selected-row' : ''}`;
        tr.dataset.recordId = row.record_id || '';
        tr.innerHTML = `
          <td>${rowInvestigatorLink(row, renderTimeCell(row.event_timestamp), true)}</td>
          <td>${rowInvestigatorLink(row, `<span class="thread-name" ${tooltipAttributes(threadTooltip)}>${escapeHtml(truncate(threadLabel, 34))}</span>`)}</td>
          <td>${rowInvestigatorLink(row, callInitiatorCell(row))}</td>
          <td>${rowInvestigatorLink(row, `<span class="pill model-pill" data-full-label="${escapeHtml(short(row.model))}">${escapeHtml(short(row.model))}</span>`)}</td>
          <td>${rowInvestigatorLink(row, effortCell(translateEffort(short(row.effort)), translateEffort(short(row.effort))))}</td>
          <td class="num token-cell">${rowInvestigatorLink(row, totalTokenCell(row))}</td>
          <td class="num token-cell">${rowInvestigatorLink(row, cachedTokenCell(row))}</td>
          <td class="num token-cell">${rowInvestigatorLink(row, uncachedTokenCell(row))}</td>
          <td class="num token-cell">${rowInvestigatorLink(row, outputTokenCell(row))}</td>
          <td class="num token-cell">${rowInvestigatorLink(row, tokenNumberCell(row.reasoning_output_tokens || 0, t('metric.reasoning_output')))}</td>
          <td class="num">${rowInvestigatorLink(row, costUsageCell(row.pricing_estimated ? `${moneyText(row.estimated_cost_usd)}*` : moneyText(row.estimated_cost_usd), usageCreditValue(row)))}</td>
          <td class="num">${rowInvestigatorLink(row, pct(row.cache_ratio))}</td>
        `;
        tr.addEventListener('mouseenter', () => showDetail(row));
        rowsEl.appendChild(tr);
      }
      if (!getInitialDetailApplied() && getSelectedRecordId()) {
        const selected = rows.find(row => row.record_id === getSelectedRecordId());
        if (selected) {
          setInitialDetailApplied(true);
          showDetail(selected);
        }
      }
      if (!getInitialDetailApplied() && initialUrlParams.get('detail') === 'first' && page.items[0]) {
        setInitialDetailApplied(true);
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
      if (!getInitialThreadExpansionApplied() && (getActiveView() === 'threads' || getActiveView() === 'insights')) {
        const expansion = initialUrlParams.get('expand');
        if (expansion === 'all') {
          groups.forEach(group => expandedThreads.add(group.key));
        } else if (expansion === 'first' && groups[0]) {
          expandedThreads.add(groups[0].key);
        }
        setInitialThreadExpansionApplied(true);
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
        tr.className = `thread-row${group.parentThreadLabel ? ' spawned-thread' : ''}${getSelectedThreadKey() === group.key ? ' selected-row' : ''}`;
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
                <span class="thread-name" ${tooltipAttributes(group.label)}>${group.renderAsChild ? `<span class="thread-relation">${escapeHtml(t('thread.spawned'))}</span> ` : ''}${escapeHtml(truncate(group.label, 34))}</span>
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
          <td class="num token-cell">${tokenNumberCell(group.reasoningOutputTokens, t('metric.reasoning_output'))}</td>
          <td class="num">${costUsageCell(getPricingConfigured() ? moneyText(group.estimatedCost) : t('state.not_configured'), group.usageCredits)}</td>
          <td class="num">${pct(group.cacheRatio)}</td>
        `;
        tr.addEventListener('click', () => {
          if (expandedThreads.has(group.key)) {
            expandedThreads.delete(group.key);
          } else {
            expandedThreads.add(group.key);
          }
          selectThread(group);
          renderWithState();
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
      if (!getInitialDetailApplied() && getSelectedThreadKey()) {
        const selected = groups.find(group => group.key === getSelectedThreadKey());
        if (selected) {
          setInitialDetailApplied(true);
          showThreadDetail(selected);
        }
      }
      if (!getInitialDetailApplied() && initialUrlParams.get('detail') === 'first' && page.items[0]) {
        setInitialDetailApplied(true);
        showThreadDetail(page.items[0]);
      }
    }

    function renderThreadCalls(group) {
      const tr = document.createElement('tr');
      tr.className = 'thread-child-row';
      const sortedCalls = sortedThreadCalls(group.calls);
      const visiblePages = Math.max(1, getThreadCallVisiblePages().get(group.key) || 1);
      const visibleCount = Math.min(sortedCalls.length, visiblePages * threadCallPageSize);
      const calls = sortedCalls.slice(0, visibleCount).map(row => {
        return `
          <tr class="thread-call-row${getSelectedRecordId() === row.record_id ? ' selected-row' : ''}" data-record-id="${escapeHtml(row.record_id || '')}">
            <td>${rowInvestigatorLink(row, renderTimeCell(row.event_timestamp), true)}</td>
            <td>${rowInvestigatorLink(row, callInitiatorCell(row))}</td>
            <td>${rowInvestigatorLink(row, `<span class="pill model-pill" data-full-label="${escapeHtml(short(row.model))}">${escapeHtml(short(row.model))}</span>`)}</td>
            <td>${rowInvestigatorLink(row, effortCell(translateEffort(short(row.effort)), translateEffort(short(row.effort))))}</td>
            <td class="num token-cell">${rowInvestigatorLink(row, totalTokenCell(row))}</td>
            <td class="num token-cell">${rowInvestigatorLink(row, cachedTokenCell(row))}</td>
            <td class="num token-cell">${rowInvestigatorLink(row, uncachedTokenCell(row))}</td>
            <td class="num token-cell">${rowInvestigatorLink(row, outputTokenCell(row))}</td>
            <td class="num token-cell">${rowInvestigatorLink(row, tokenNumberCell(row.reasoning_output_tokens || 0, t('metric.reasoning_output')))}</td>
            <td class="num">${rowInvestigatorLink(row, costUsageCell(row.pricing_estimated ? `${moneyText(row.estimated_cost_usd)}*` : moneyText(row.estimated_cost_usd), usageCreditValue(row)))}</td>
            <td class="num">${rowInvestigatorLink(row, pct(row.cache_ratio))}</td>
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
            <colgroup>
              <col class="col-time">
              <col class="col-initiated">
              <col class="col-model">
              <col class="col-effort">
              <col class="col-tokens">
              <col class="col-cached">
              <col class="col-uncached">
              <col class="col-output">
              <col class="col-reasoning">
              <col class="col-cost">
              <col class="col-cache">
            </colgroup>
            <thead><tr>
              ${threadCallHeader('time', t('table.time'))}
              ${threadCallHeader('initiator', t('table.initiated'))}
              ${threadCallHeader('model', t('table.model'))}
              ${threadCallHeader('effort', t('table.effort'))}
              ${threadCallHeader('total', t('table.tokens'), true)}
              ${threadCallHeader('cached', t('table.cached'), true)}
              ${threadCallHeader('uncached', t('table.uncached'), true)}
              ${threadCallHeader('output', t('table.output'), true)}
              ${threadCallHeader('reasoning', t('context.token_reasoning'), true)}
              ${threadCallHeader('cost', t('table.cost'), true)}
              ${threadCallHeader('cache', t('table.cache'), true)}
            </tr></thead>
            <tbody>${calls}</tbody>
          </table>
          ${childLoadMore}
        </td>
      `;
      return tr;
    }

    return {
      renderCalls,
      renderThreads,
      renderThreadCalls,
      threadCallHeader,
    };
  }

  window.CodexUsageDashboardTables = { create };
})();
