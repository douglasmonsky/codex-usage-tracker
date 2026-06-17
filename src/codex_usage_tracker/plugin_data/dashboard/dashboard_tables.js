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
      getSortDirection,
      getSortKey,
      getSessionFilter,
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
      groupThreads,
    } = deps;

    let tableColumnCount = 13;

    function topLevelHeader(key, label, numeric = false) {
      const active = getSortKey() === key;
      const indicator = active ? (getSortDirection() === 'asc' ? '▲' : '▼') : '';
      const ariaSort = active ? (getSortDirection() === 'asc' ? 'ascending' : 'descending') : 'none';
      return `
        <th${numeric ? ' class="num"' : ''} data-sort-header="${escapeHtml(key)}" data-sort-active="${active ? 'true' : 'false'}" aria-sort="${ariaSort}">
          <button class="sort-header" type="button" data-sort-key="${escapeHtml(key)}">
            <span>${escapeHtml(label)}</span>
            <span class="sort-indicator" data-sort-indicator="${escapeHtml(key)}">${escapeHtml(indicator)}</span>
          </button>
        </th>
      `;
    }

    function configureMainTable(columns, headers) {
      tableColumnCount = columns.length;
      tableColgroupEl.innerHTML = columns.map(column => `<col class="${escapeHtml(column)}">`).join('');
      tableHeadEl.innerHTML = `<tr>${headers.join('')}</tr>`;
    }

    function configureCallTable() {
      configureMainTable(
        [
          'col-time',
          'col-thread',
          'col-initiated',
          'col-model',
          'col-effort',
          'col-tokens',
          'col-cached',
          'col-uncached',
          'col-output',
          'col-reasoning',
          'col-usage-impact',
          'col-cost',
          'col-cache',
        ],
        [
          topLevelHeader('time', t('table.time')),
          topLevelHeader('thread', t('table.thread')),
          topLevelHeader('initiator', t('table.initiated')),
          topLevelHeader('model', t('table.model')),
          topLevelHeader('effort', t('table.effort')),
          topLevelHeader('total', t('table.tokens'), true),
          topLevelHeader('cached', t('table.cached'), true),
          topLevelHeader('uncached', t('table.uncached'), true),
          topLevelHeader('output', t('table.output'), true),
          topLevelHeader('reasoning', t('context.token_reasoning'), true),
          topLevelHeader('usage_impact', translationOrFallback('table.usage_impact', 'Usage'), true),
          topLevelHeader('cost', t('table.cost'), true),
          topLevelHeader('cache', t('table.cache'), true),
        ],
      );
    }

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

    function translationOrFallback(key, fallback) {
      const translated = t(key);
      return translated === key ? fallback : translated;
    }

    function renderCalls(rows) {
      configureCallTable();
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
          <td>${rowInvestigatorLink(row, `<span class="thread-name" ${tooltipAttributes(threadTooltip)}>${escapeHtml(threadLabel)}</span>`)}</td>
          <td>${rowInvestigatorLink(row, callInitiatorCell(row))}</td>
          <td>${rowInvestigatorLink(row, `<span class="pill model-pill" data-full-label="${escapeHtml(short(row.model))}">${escapeHtml(short(row.model))}</span>`)}</td>
          <td>${rowInvestigatorLink(row, effortCell(translateEffort(short(row.effort)), translateEffort(short(row.effort))))}</td>
          <td class="num token-cell">${rowInvestigatorLink(row, totalTokenCell(row))}</td>
          <td class="num token-cell">${rowInvestigatorLink(row, cachedTokenCell(row))}</td>
          <td class="num token-cell">${rowInvestigatorLink(row, uncachedTokenCell(row))}</td>
          <td class="num token-cell">${rowInvestigatorLink(row, outputTokenCell(row))}</td>
          <td class="num token-cell">${rowInvestigatorLink(row, tokenNumberCell(row.reasoning_output_tokens || 0, t('metric.reasoning_output')))}</td>
          <td class="num usage-impact-column">${rowInvestigatorLink(row, usageImpactCell(row))}</td>
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
        rowsEl.innerHTML = `<tr><td class="empty-state" colspan="${tableColumnCount}">${escapeHtml(message)}</td></tr>`;
      }
    }

    function renderThreads(rows, mode = 'threads') {
      const groups = groupThreads(rows);
      renderThreadGroups(groups, mode, {
        calls: rows.length,
        loaded: loadedRowsDescription(),
      });
    }

    function renderThreadGroups(groups, mode = 'threads', meta = {}) {
      configureCallTable();
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
      tableTitleEl.textContent = mode === 'insights' ? t('dashboard.top_threads_by_attention') : t('dashboard.view.threads');
      const preset = activePresetDefinition();
      const prefix = preset ? `${t(preset.captionKey)}. ` : '';
      const threadTotal = Number.isFinite(Number(meta.totalThreads)) ? Number(meta.totalThreads) : groups.length;
      const callTotal = Number.isFinite(Number(meta.totalCalls)) ? Number(meta.totalCalls) : Number(meta.calls || 0);
      const loaded = meta.loaded || loadedRowsDescription();
      const serverPaged = Boolean(meta.serverPaged);
      const page = serverPaged
        ? { items: groups, start: 0, end: groups.length, total: threadTotal, pageCount: 1 }
        : visibleSlice(groups);
      updateLoadMoreControl(page, 'table.threads');
      tableCaptionEl.textContent = `${prefix}${dateCaptionPrefix()}${tf('caption.threads', { threads: number.format(threadTotal), calls: number.format(callTotal), sort: tableCaptionEl.dataset.sortDescription, loaded })}`;
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
                <span class="thread-name" ${tooltipAttributes(group.label)}>${group.renderAsChild ? `<span class="thread-relation">${escapeHtml(t('thread.spawned'))}</span> ` : ''}${escapeHtml(group.label)}</span>
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
          <td class="num usage-impact-column">${usageImpactCell(group)}</td>
          <td class="num">${costUsageCell(getPricingConfigured() ? moneyText(group.estimatedCost) : t('state.not_configured'), group.usageCredits)}</td>
          <td class="num">${pct(group.cacheRatio)}</td>
        `;
        tr.addEventListener('click', () => {
          if (typeof toggleThread === 'function') {
            toggleThread(group);
            return;
          }
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
        const message = meta.error
          ? meta.error
          : meta.loading
            ? t('state.loading_rows')
            : t('state.no_threads');
        rowsEl.innerHTML = `<tr><td class="empty-state" colspan="${tableColumnCount}">${escapeHtml(message)}</td></tr>`;
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
      const sortedCalls = sortedThreadCalls(group.calls || []);
      const visiblePages = Math.max(1, getThreadCallVisiblePages().get(group.key) || 1);
      const visibleCount = group.callsServerPaged
        ? sortedCalls.length
        : Math.min(sortedCalls.length, visiblePages * threadCallPageSize);
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
            <td class="num usage-impact-column">${rowInvestigatorLink(row, usageImpactCell(row))}</td>
            <td class="num">${rowInvestigatorLink(row, costUsageCell(row.pricing_estimated ? `${moneyText(row.estimated_cost_usd)}*` : moneyText(row.estimated_cost_usd), usageCreditValue(row)))}</td>
            <td class="num">${rowInvestigatorLink(row, pct(row.cache_ratio))}</td>
          </tr>
        `;
      }).join('');
      const totalCalls = Number.isFinite(Number(group.callsTotal)) ? Number(group.callsTotal) : sortedCalls.length;
      const canLoadMore = visibleCount < sortedCalls.length || Boolean(group.callsHasMore);
      const childLoadMore = canLoadMore
        ? `
          <div class="child-load-more">
            <span>${escapeHtml(tf('table.visible_status', { end: number.format(visibleCount), total: number.format(totalCalls), items: t('table.calls') }))}</span>
            <button class="pager-button" type="button" data-thread-load-more="${escapeHtml(group.key)}">${escapeHtml(t('button.load_more'))}</button>
          </div>
        `
        : sortedCalls.length
          ? `<div class="child-load-more"><span>${escapeHtml(tf('table.visible_status', { end: number.format(visibleCount), total: number.format(totalCalls), items: t('table.calls') }))}</span></div>`
          : '';
      const childRows = group.callsError
        ? `<tr><td colspan="12" class="empty-state">${escapeHtml(group.callsError)}</td></tr>`
        : group.callsLoading && !sortedCalls.length
          ? `<tr><td colspan="12" class="empty-state">${escapeHtml(t('state.loading_rows'))}</td></tr>`
          : !sortedCalls.length
            ? `<tr><td colspan="12" class="empty-state">${escapeHtml(t('state.no_calls'))}</td></tr>`
            : calls;
      tr.innerHTML = `
        <td class="child-cell" colspan="${tableColumnCount}">
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
              <col class="col-usage-impact">
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
              ${threadCallHeader('usage_impact', translationOrFallback('table.usage_impact', 'Usage'), true)}
              ${threadCallHeader('cost', t('table.cost'), true)}
              ${threadCallHeader('cache', t('table.cache'), true)}
            </tr></thead>
            <tbody>${childRows}</tbody>
          </table>
          ${childLoadMore}
        </td>
      `;
      return tr;
    }

    function formatSessionMinutes(value) {
      const numeric = Number(value);
      if (!Number.isFinite(numeric)) return '-';
      const rounded = Math.max(0, Math.round(numeric));
      if (rounded < 60) return tf('session.minutes', { minutes: number.format(rounded) });
      const hours = Math.floor(rounded / 60);
      const minutes = rounded % 60;
      return tf('session.hours_minutes', { hours: number.format(hours), minutes: number.format(minutes) });
    }

    function sessionActionLabel(value) {
      return {
        monitor: t('session.action.monitor'),
        inspect_cold_resume: t('session.action.inspect_cold_resume'),
        handoff_or_start_fresh: t('session.action.handoff_or_start_fresh'),
      }[value] || short(value, t('state.unknown'));
    }

    function sessionReasonLabel(value) {
      return {
        session_start: t('session.reason.session_start'),
        thread_start: t('session.reason.thread_start'),
        cold_resume: t('session.reason.cold_resume'),
        post_compaction: t('session.reason.post_compaction'),
      }[value] || short(value, t('state.unknown'));
    }

    function epochEffectivenessLabel(value) {
      return {
        effective: t('session.effectiveness.effective'),
        mixed: t('session.effectiveness.mixed'),
        ineffective: t('session.effectiveness.ineffective'),
        unknown: t('session.effectiveness.unknown'),
      }[value] || short(value, t('state.unknown'));
    }

    function sessionFilterButton(key, label) {
      const active = getSessionFilter() === key;
      return `<button class="session-filter-button" type="button" data-session-filter="${escapeHtml(key)}" aria-pressed="${active ? 'true' : 'false'}">${escapeHtml(label)}</button>`;
    }

    function renderSessionCaption(state) {
      const filterButtons = [
        sessionFilterButton('', t('session.filter.all')),
        sessionFilterButton('cold', t('session.filter.cold')),
        sessionFilterButton('high_uncached', t('session.filter.high_uncached')),
        sessionFilterButton('needs_handoff', t('session.filter.needs_handoff')),
        sessionFilterButton('recent', t('session.filter.recent')),
      ].join('');
      const caption = state.loading && !state.rows.length
        ? t('session.loading')
        : tf('session.caption', {
          sort: tableCaptionEl.dataset.sortDescription,
          loaded: state.loadedDescription,
        });
      tableCaptionEl.innerHTML = `
        <div class="session-caption">
          <span>${escapeHtml(caption)}</span>
          <span class="session-filter-buttons">${filterButtons}</span>
        </div>
      `;
    }

    function configureSessionTable() {
      configureMainTable(
        [
          'col-time',
          'col-thread',
          'col-ended',
          'col-reason',
          'col-idle',
          'col-duration',
          'col-calls',
          'col-tokens',
          'col-uncached',
          'col-cache',
          'col-largest-miss',
          'col-context',
          'col-action',
        ],
        [
          topLevelHeader('started', t('table.started')),
          topLevelHeader('thread', t('table.thread')),
          topLevelHeader('ended', t('table.ended')),
          topLevelHeader('reason', t('table.source')),
          topLevelHeader('idle', t('table.idle_before'), true),
          topLevelHeader('duration', t('table.duration'), true),
          topLevelHeader('calls', t('detail.calls'), true),
          topLevelHeader('tokens', t('table.tokens'), true),
          topLevelHeader('uncached', t('table.uncached'), true),
          topLevelHeader('cache', t('table.cache'), true),
          topLevelHeader('largest_miss', t('table.largest_miss'), true),
          topLevelHeader('context', t('table.context_peak'), true),
          topLevelHeader('action', t('table.action')),
        ],
      );
    }

    function renderSessions(state) {
      configureSessionTable();
      const rows = Array.isArray(state.rows) ? state.rows : [];
      const expandedSessionIds = state.expandedSessionIds || new Set();
      tableTitleEl.textContent = t('dashboard.view.sessions');
      renderSessionCaption(state);
      updateLoadMoreControl({
        end: rows.length,
        total: state.total || rows.length,
      }, 'table.sessions');
      if (state.error) {
        rowsEl.innerHTML = `<tr><td class="empty-state" colspan="${tableColumnCount}">${escapeHtml(tf('session.error', { message: state.error }))}</td></tr>`;
        return;
      }
      if (!rows.length) {
        rowsEl.innerHTML = `<tr><td class="empty-state" colspan="${tableColumnCount}">${escapeHtml(state.loading ? t('session.loading') : t('state.no_sessions'))}</td></tr>`;
        return;
      }
      rowsEl.textContent = '';
      for (const row of rows) {
        const tr = document.createElement('tr');
        const threadLabel = short(row.thread_label, t('state.unknown'));
        const actionLabel = sessionActionLabel(row.suggested_next_action);
        const reasonLabel = sessionReasonLabel(row.start_reason);
        const workSessionId = row.work_session_id || '';
        const expanded = expandedSessionIds.has(workSessionId);
        tr.className = `work-session-row${row.start_reason === 'cold_resume' ? ' cold-resume-session' : ''}`;
        tr.dataset.workSessionId = workSessionId;
        tr.tabIndex = 0;
        tr.setAttribute('role', 'button');
        tr.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        tr.setAttribute('aria-label', `${expanded ? t('thread.collapse') : t('thread.expand')} ${threadLabel} ${t('session.context_segments')}`);
        tr.innerHTML = `
          <td>${renderTimeCell(row.started_at)}</td>
          <td>
            <span class="thread-toggle" aria-hidden="true">${expanded ? '-' : '+'}</span>
            <span class="thread-name" ${tooltipAttributes(threadLabel)}>${escapeHtml(threadLabel)}</span>
          </td>
          <td>${renderTimeCell(row.ended_at)}</td>
          <td><span class="session-reason ${row.start_reason === 'cold_resume' ? 'cold' : ''}" ${tooltipAttributes(reasonLabel)}>${escapeHtml(reasonLabel)}</span></td>
          <td class="num">${escapeHtml(formatSessionMinutes(row.idle_minutes_before))}</td>
          <td class="num">${escapeHtml(formatSessionMinutes(row.duration_minutes))}</td>
          <td class="num">${tokenNumberCell(row.call_count || 0, t('detail.calls'))}</td>
          <td class="num token-cell">${tokenNumberCell(row.total_tokens || 0, t('metric.total_tokens'))}</td>
          <td class="num token-cell">${tokenNumberCell(row.uncached_input_tokens || 0, t('metric.uncached_input'))}</td>
          <td class="num">${pct(row.avg_cache_ratio || 0)}</td>
          <td class="num token-cell">${tokenNumberCell(row.largest_uncached_input_tokens || 0, t('table.largest_miss'))}</td>
          <td class="num">${pct(row.max_context_window_percent || 0)}</td>
          <td><span class="session-action" ${tooltipAttributes(actionLabel)}>${escapeHtml(actionLabel)}</span></td>
        `;
        rowsEl.appendChild(tr);
        if (expanded) rowsEl.appendChild(renderSessionEpochs(row, state));
      }
    }

    function renderSessionEpochs(row, state) {
      const workSessionId = row.work_session_id || '';
      const tr = document.createElement('tr');
      tr.className = 'session-epoch-child-row';
      const loading = state.sessionEpochLoading && state.sessionEpochLoading.has(workSessionId);
      const error = state.sessionEpochErrors && state.sessionEpochErrors.get(workSessionId);
      const epochs = state.sessionEpochs && state.sessionEpochs.get(workSessionId);
      let body = '';
      if (loading && !epochs) {
        body = `<div class="session-epoch-state">${escapeHtml(t('session.epoch.loading'))}</div>`;
      } else if (error) {
        body = `<div class="session-epoch-state error">${escapeHtml(tf('session.epoch.error', { message: error }))}</div>`;
      } else if (!epochs || !epochs.length) {
        body = `<div class="session-epoch-state">${escapeHtml(t('session.epoch.none'))}</div>`;
      } else {
        const rows = epochs.map(epoch => {
          const reasonLabel = sessionReasonLabel(epoch.start_reason);
          const effectivenessLabel = epochEffectivenessLabel(epoch.compaction_effectiveness);
          const firstMiss = epoch.post_compaction_uncached_spike || epoch.first_call_uncached_input_tokens || 0;
          return `
            <tr>
              <td>
                <span class="session-epoch-index">${escapeHtml(`#${number.format(epoch.epoch_index || 0)}`)}</span>
                <span class="session-reason ${epoch.start_reason === 'post_compaction' ? 'compaction' : ''}" ${tooltipAttributes(reasonLabel)}>${escapeHtml(reasonLabel)}</span>
              </td>
              <td>${renderTimeCell(epoch.started_at)}</td>
              <td class="num">${tokenNumberCell(epoch.call_count || 0, t('detail.calls'))}</td>
              <td class="num token-cell">${tokenNumberCell(epoch.total_tokens || 0, t('metric.total_tokens'))}</td>
              <td class="num token-cell">${tokenNumberCell(epoch.uncached_input_tokens || 0, t('metric.uncached_input'))}</td>
              <td class="num">${pct(epoch.avg_cache_ratio || 0)}</td>
              <td class="num">${pct(epoch.max_context_window_percent || 0)}</td>
              <td class="num token-cell">${tokenNumberCell(firstMiss, t('session.epoch.first_miss'))}</td>
              <td><span class="session-effectiveness" ${tooltipAttributes(effectivenessLabel)}>${escapeHtml(effectivenessLabel)}</span></td>
            </tr>
          `;
        }).join('');
        body = `
          <table class="session-epoch-table" aria-label="${escapeHtml(`${row.thread_label || t('state.unknown')} ${t('session.context_segments')}`)}">
            <thead><tr>
              <th>${escapeHtml(t('session.epoch.segment'))}</th>
              <th>${escapeHtml(t('table.started'))}</th>
              <th class="num">${escapeHtml(t('detail.calls'))}</th>
              <th class="num">${escapeHtml(t('table.tokens'))}</th>
              <th class="num">${escapeHtml(t('table.uncached'))}</th>
              <th class="num">${escapeHtml(t('table.cache'))}</th>
              <th class="num">${escapeHtml(t('table.context_peak'))}</th>
              <th class="num">${escapeHtml(t('session.epoch.first_miss'))}</th>
              <th>${escapeHtml(t('session.epoch.effectiveness'))}</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        `;
      }
      tr.innerHTML = `
        <td class="child-cell session-epoch-cell" colspan="${tableColumnCount}">
          <div class="session-epoch-panel">
            <div class="session-epoch-heading">
              <strong>${escapeHtml(t('session.context_segments'))}</strong>
              <span>${escapeHtml(t('session.context_segments_hint'))}</span>
            </div>
            ${body}
          </div>
        </td>
      `;
      return tr;
    }

    return {
      renderCalls,
      renderSessions,
      renderThreadGroups,
      renderThreads,
      renderThreadCalls,
      threadCallHeader,
    };
  }

  window.CodexUsageDashboardTables = { create };
})();
