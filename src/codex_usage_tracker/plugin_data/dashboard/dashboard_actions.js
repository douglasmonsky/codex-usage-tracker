(() => {
  function createDashboardActions(deps) {
    const {
      actionStatusEl,
      apiToken,
      callInitiator,
      currentPage,
      dateEndEl,
      datePresetEl,
      dateStartEl,
      effortEl,
      escapeHtml,
      expandedThreads,
      filtered,
      getActivePreset,
      getActiveView,
      getIncludeArchived,
      getSelectedRecordId,
      getSelectedThreadKey,
      getSessionFilter,
      getSessionRows,
      getSortDirection,
      getSortKey,
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
    } = deps;

    function currentDashboardState() {
      return {
        view: getActiveView(),
        search: searchEl.value.trim(),
        model: modelEl.value,
        effort: effortEl.value,
        confidence: pricingStatusEl.value,
        datePreset: datePresetEl.value,
        dateStart: datePresetEl.value === 'custom' ? dateStartEl.value : '',
        dateEnd: datePresetEl.value === 'custom' ? dateEndEl.value : '',
        historyScope: getIncludeArchived() ? 'all' : 'active',
        sort: getSortKey(),
        direction: getSortDirection(),
        preset: getActivePreset(),
        page: currentPage(),
        record: getSelectedRecordId(),
        thread: getSelectedThreadKey(),
        sessionFilter: getSessionFilter(),
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
      const opened = window.open(url, '_blank');
      if (opened) {
        opened.opener = null;
        return true;
      }
      if (liveRefreshSupported) {
        if (apiToken()) {
          try {
            const params = new URLSearchParams({ url });
            const response = await fetch(`/api/open-investigator?${params.toString()}`, {
              headers: {
                'Accept': 'application/json',
                'X-Codex-Usage-Token': apiToken(),
              },
              cache: 'no-store',
            });
            if (response.ok) return true;
          } catch (_error) {
            // Fall through to the normal browser path.
          }
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
      } catch (_error) {
        showActionStatus(t('action.copy_failed'));
      }
    }

    async function copyCurrentViewLink() {
      if (!stateManager) return;
      const url = stateManager.urlFor(currentDashboardState());
      try {
        await stateManager.copyText(url);
        showActionStatus(t('action.copied'));
      } catch (_error) {
        showActionStatus(t('action.copy_failed'));
      }
    }

    function usageImpactExportValue(row, key) {
      const impact = row && row.usage_impact && typeof row.usage_impact === 'object'
        ? row.usage_impact[key]
        : null;
      return impact && typeof impact === 'object' && impact.estimate_percent !== undefined
        ? impact.estimate_percent
        : '';
    }

    function exportCurrentRows() {
      if (!stateManager) return;
      if (getActiveView() === 'sessions') {
        const rows = getSessionRows();
        const columns = [
          { label: 'started_at', field: 'started_at' },
          { label: 'ended_at', field: 'ended_at' },
          { label: 'thread', field: 'thread_label' },
          { label: 'session_index', field: 'session_index' },
          { label: 'start_reason', field: 'start_reason' },
          { label: 'idle_minutes_before', field: 'idle_minutes_before' },
          { label: 'duration_minutes', field: 'duration_minutes' },
          { label: 'call_count', field: 'call_count' },
          { label: 'total_tokens', field: 'total_tokens' },
          { label: 'uncached_input_tokens', field: 'uncached_input_tokens' },
          { label: 'avg_cache_ratio', field: 'avg_cache_ratio' },
          { label: 'largest_uncached_input_tokens', field: 'largest_uncached_input_tokens' },
          { label: 'max_context_window_percent', field: 'max_context_window_percent' },
          { label: 'suggested_next_action', field: 'suggested_next_action' },
          { label: 'recommendation_score', field: 'recommendation_score' },
          { label: 'work_session_id', field: 'work_session_id' },
        ];
        const csv = stateManager.toCsv(rows, columns);
        stateManager.downloadText('codex-usage-work-sessions.csv', csv, 'text/csv;charset=utf-8');
        showActionStatus(tf('action.exported', { count: number.format(rows.length) }));
        return;
      }
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
        { label: 'estimated_weekly_usage_impact_percent', field: row => usageImpactExportValue(row, 'secondary') },
        { label: 'estimated_5h_usage_impact_percent', field: row => usageImpactExportValue(row, 'primary') },
        { label: 'cache_ratio', field: 'cache_ratio' },
        { label: 'context_window_percent', field: 'context_window_percent' },
        { label: 'pricing_model', field: 'pricing_model' },
        { label: 'usage_credit_confidence', field: 'usage_credit_confidence' },
        { label: 'recommendation', field: row => row.recommended_action || recommendationSummary(row) },
        { label: 'record_id', field: 'record_id' },
      ];
      const csv = stateManager.toCsv(rows, columns);
      const suffix = getActiveView() === 'threads' ? 'thread-filtered-calls' : `${getActiveView()}-calls`;
      stateManager.downloadText(`codex-usage-${suffix}.csv`, csv, 'text/csv;charset=utf-8');
      showActionStatus(tf('action.exported', { count: number.format(rows.length) }));
    }

    return {
      copyCallLink,
      copyCurrentViewLink,
      currentDashboardState,
      exportCurrentRows,
      investigatorUrl,
      openInvestigator,
      openInvestigatorUrl,
      rowInvestigatorLink,
      showActionStatus,
      syncUrlState,
      tableUrlForRow,
    };
  }

  window.CodexUsageDashboardActions = { create: createDashboardActions };
})();
