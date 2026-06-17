(() => {
  function bindDashboardEvents(deps) {
    const {
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
      getRowByRecordId,
      handleHeaderSort,
      handleFiltersChanged,
      handleThreadCallHeaderSort,
      hideFastTooltip,
      historyRowsDescription,
      historyScopeEl,
      incrementCurrentPage,
      incrementThreadCallVisiblePage,
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
      setIncludeArchived,
      setLanguage,
      setSessionFilter,
      setSort,
      setView,
      sortEl,
      t,
      tableHeadEl,
      tf,
      threadsViewEl,
      sessionsViewEl,
      toggleDetailPanel,
      toggleSessionEpochs,
      toTopEl,
      updateHistoryScopeControl,
      updateLiveStatus,
      updateToTopVisibility,
      syncDatePresetInputs,
      syncUrlState,
    } = deps;

    insightsViewEl.addEventListener('click', () => setView('insights'));
    callsViewEl.addEventListener('click', () => setView('calls'));
    threadsViewEl.addEventListener('click', () => setView('threads'));
    sessionsViewEl.addEventListener('click', () => setView('sessions'));
    clearPresetEl.addEventListener('click', clearPreset);
    copyViewLinkEl.addEventListener('click', copyCurrentViewLink);
    exportVisibleEl.addEventListener('click', exportCurrentRows);
    refreshDashboardEl.addEventListener('click', () => refreshDashboardData(true));
    if (languageSelectEl) {
      languageSelectEl.addEventListener('change', () => setLanguage(languageSelectEl.value));
    }
    loadLimitEl.addEventListener('change', () => {
      resetVisibleRows();
      if (liveRefreshSupported) {
        refreshDashboardData(false, { refreshLogs: false, resetRows: true });
      } else {
        updateLiveStatus('status.static', t('live.load_static_hint'));
      }
    });
    historyScopeEl.addEventListener('change', () => {
      setIncludeArchived(historyScopeEl.value === 'all');
      resetVisibleRows();
      updateHistoryScopeControl();
      syncUrlState();
      if (liveRefreshSupported) {
        refreshDashboardData(false, { refreshLogs: false, resetRows: true });
      } else {
        updateLiveStatus('status.static', t('live.history_static_hint'));
      }
    });
    autoRefreshEl.addEventListener('change', () => {
      scheduleAutoRefresh();
      updateLiveStatus(autoRefreshEl.checked ? 'badge.live' : 'status.paused', `${autoRefreshEl.checked ? tf('live.every', { seconds: liveRefreshIntervalMs / 1000 }) : t('live.paused')}. ${loadedRowsDescription()}. ${historyRowsDescription()}`);
      if (autoRefreshEl.checked) refreshDashboardIfStale();
    });
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && autoRefreshEl.checked) refreshDashboardIfStale();
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
      if (event.key === '4') setView('sessions');
    });
    window.addEventListener('scroll', updateToTopVisibility, { passive: true });
    toTopEl.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
    loadMoreRowsEl.addEventListener('click', incrementCurrentPage);
    document.addEventListener('click', event => {
      const sessionFilterButton = event.target.closest('[data-session-filter]');
      if (!sessionFilterButton || !document.body.contains(sessionFilterButton)) return;
      event.preventDefault();
      setSessionFilter(sessionFilterButton.dataset.sessionFilter || '');
    });
    tableHeadEl.addEventListener('click', event => {
      const button = event.target.closest('[data-sort-key]');
      if (!button || !tableHeadEl.contains(button)) return;
      handleHeaderSort(button.dataset.sortKey);
    });
    rowsEl.addEventListener('mouseover', event => {
      const callRow = event.target.closest('.thread-call-row');
      if (!callRow || !rowsEl.contains(callRow)) return;
      const row = getRowByRecordId(callRow.dataset.recordId);
      if (row) selectRow(row);
    });
    rowsEl.addEventListener('click', event => {
      const dashboardRoute = event.target.closest('[data-dashboard-route]');
      if (dashboardRoute && rowsEl.contains(dashboardRoute)) {
        event.preventDefault();
        event.stopPropagation();
        routeBackToDashboard(dashboardRoute.dataset.dashboardRoute || 'calls');
        return;
      }
      const rowLink = event.target.closest('a.row-investigator-link');
      if (rowLink && rowsEl.contains(rowLink)) {
        if (!liveRefreshSupported) return;
        event.preventDefault();
        event.stopPropagation();
        openInvestigatorUrl(rowLink.href);
        return;
      }
      const openButton = event.target.closest('[data-open-investigator-record]');
      if (openButton && rowsEl.contains(openButton)) {
        event.preventDefault();
        event.stopPropagation();
        const row = getRowByRecordId(openButton.dataset.openInvestigatorRecord);
        if (row) openInvestigator(row);
        return;
      }
      const copyButton = event.target.closest('[data-copy-call-link]');
      if (copyButton && rowsEl.contains(copyButton)) {
        event.preventDefault();
        event.stopPropagation();
        const row = getRowByRecordId(copyButton.dataset.copyCallLink);
        if (row) copyCallLink(row);
        return;
      }
      const navButton = event.target.closest('[data-call-nav-record]');
      if (navButton && rowsEl.contains(navButton)) {
        event.preventDefault();
        event.stopPropagation();
        const recordId = navButton.dataset.callNavRecord;
        navigateToCallRecord(recordId);
        return;
      }
      const sortButton = event.target.closest('[data-thread-call-sort-key]');
      if (sortButton && rowsEl.contains(sortButton)) {
        event.preventDefault();
        event.stopPropagation();
        handleThreadCallHeaderSort(sortButton.dataset.threadCallSortKey);
        return;
      }
      const loadMoreButton = event.target.closest('[data-thread-load-more]');
      if (loadMoreButton && rowsEl.contains(loadMoreButton)) {
        event.preventDefault();
        event.stopPropagation();
        incrementThreadCallVisiblePage(loadMoreButton.dataset.threadLoadMore);
        return;
      }
      const sessionRow = event.target.closest('.work-session-row');
      if (sessionRow && rowsEl.contains(sessionRow)) {
        event.preventDefault();
        event.stopPropagation();
        if (toggleSessionEpochs) toggleSessionEpochs(sessionRow.dataset.workSessionId || '');
        return;
      }
      const callRow = event.target.closest('.call-row, .thread-call-row');
      if (!callRow || !rowsEl.contains(callRow)) return;
      event.preventDefault();
      event.stopPropagation();
      const row = getRowByRecordId(callRow.dataset.recordId);
      if (row) openInvestigator(row);
    });
    rowsEl.addEventListener('dblclick', event => {
      const callRow = event.target.closest('.call-row, .thread-call-row');
      if (!callRow || !rowsEl.contains(callRow)) return;
      event.preventDefault();
      event.stopPropagation();
    });
    rowsEl.addEventListener('keydown', event => {
      if (event.target.closest('a.row-investigator-link')) return;
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const sessionRow = event.target.closest('.work-session-row');
      if (sessionRow && rowsEl.contains(sessionRow)) {
        event.preventDefault();
        if (toggleSessionEpochs) toggleSessionEpochs(sessionRow.dataset.workSessionId || '');
        return;
      }
      const callRow = event.target.closest('.call-row, .thread-call-row');
      if (!callRow || !rowsEl.contains(callRow)) return;
      event.preventDefault();
      const row = getRowByRecordId(callRow.dataset.recordId);
      if (row) openInvestigator(row);
    });
    if (detailToggleEl) detailToggleEl.addEventListener('click', toggleDetailPanel);
    document.addEventListener('mouseover', event => {
      const target = closestFastTooltipTarget(event.target);
      if (!target || !document.body.contains(target)) return;
      if (target.contains(event.relatedTarget)) return;
      scheduleFastTooltip(target);
    });
    document.addEventListener('mouseout', event => {
      const target = closestFastTooltipTarget(event.target);
      if (!target) return;
      if (target.contains(event.relatedTarget)) return;
      hideFastTooltip();
    });
    document.addEventListener('focusin', event => {
      const target = closestFastTooltipTarget(event.target);
      if (target) scheduleFastTooltip(target);
    });
    document.addEventListener('focusout', event => {
      const target = closestFastTooltipTarget(event.target);
      if (target) hideFastTooltip();
    });
    window.addEventListener('scroll', hideFastTooltip, { passive: true });
    window.addEventListener('resize', hideFastTooltip);
    datePresetEl.addEventListener('input', () => {
      syncDatePresetInputs();
      handleFiltersChanged();
    });
    [dateStartEl, dateEndEl].forEach(el => el.addEventListener('input', () => {
      if (datePresetEl.value !== 'custom') datePresetEl.value = 'custom';
      el.value = cleanDateInput(el.value) || el.value;
      handleFiltersChanged();
    }));
    [searchEl, modelEl, effortEl, pricingStatusEl].forEach(el => el.addEventListener('input', () => {
      handleFiltersChanged();
    }));
    sortEl.addEventListener('input', () => setSort(sortEl.value, defaultSortDirection(sortEl.value)));
  }

  window.CodexUsageDashboardEvents = { bind: bindDashboardEvents };
})();
