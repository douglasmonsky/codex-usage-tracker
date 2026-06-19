(() => {
  function createDashboardLiveRuntime(deps) {
    const {
      activeView,
      apiToken,
      applyDashboardPayload,
      autoRefreshEl,
      formatTimestamp,
      getData,
      getIncludeArchived,
      getLoadedLimit,
      getTotalAvailableRows,
      getArchivedAvailableRows,
      historyScopeEl,
      initialHydrationChunkSize,
      backgroundHydrationChunkSize,
      i18n,
      liveRefreshIntervalMs,
      liveRefreshSupported,
      loadLimitEl,
      limitValue,
      number,
      payloadRows,
      rebuildDashboardIndexes,
      rebuildFilterOptions,
      refreshDashboardEl,
      render,
      resetRowsForHydration,
      rowLoadProgressBarEl,
      rowLoadProgressCountEl,
      rowLoadProgressEl,
      rowLoadProgressLabelEl,
      setFastTooltip,
      t,
      tf,
      updateLiveStatus,
    } = deps;

    let refreshInFlight = false;
    let rowHydrationInFlight = false;
    let rowHydrationComplete = getData().length > 0;
    let rowHydrationError = '';
    let rowHydrationGeneration = 0;
    let rowHydrationRestartRequested = false;
    let autoRefreshTimer = null;

    function loadedRowsDescription() {
      const data = getData();
      const loaded = number.format(data.length);
      const available = number.format(getTotalAvailableRows() || data.length);
      const loadedLimit = getLoadedLimit();
      const capped = loadedLimit !== null && getTotalAvailableRows() > data.length;
      return capped
        ? tf('caption.loaded_capped', { loaded, available })
        : tf('caption.loaded', { loaded });
    }

    function rowHydrationTarget() {
      const available = Math.max(0, Number(getTotalAvailableRows() || 0));
      if (!available) return 0;
      const loadedLimit = getLoadedLimit();
      return loadedLimit === null ? available : Math.min(available, Number(loadedLimit || available));
    }

    function rowsNeedHydration() {
      const target = rowHydrationTarget();
      return liveRefreshSupported && target > 0 && getData().length < target;
    }

    function updateRowLoadProgress() {
      if (!rowLoadProgressEl) return;
      const target = rowHydrationTarget();
      const loaded = Math.min(getData().length, target || getData().length);
      const shouldShow = !['call', 'diagnostics'].includes(activeView()) && liveRefreshSupported && (rowHydrationInFlight || rowsNeedHydration() || rowHydrationError);
      rowLoadProgressEl.hidden = !shouldShow;
      if (!shouldShow) return;
      const totalText = number.format(target || getTotalAvailableRows() || loaded);
      const loadedText = number.format(loaded);
      rowLoadProgressLabelEl.textContent = rowHydrationError ? t('state.error') : t('state.loading_rows');
      rowLoadProgressCountEl.textContent = rowHydrationError
        ? rowHydrationError
        : (rowHydrationComplete
            ? tf('caption.rows_loaded_progress', { loaded: loadedText, total: totalText })
            : tf('caption.rows_loading_progress', { loaded: loadedText, total: totalText }));
      const ratio = target ? Math.max(0, Math.min(100, (loaded / target) * 100)) : 0;
      rowLoadProgressBarEl.style.width = `${ratio}%`;
    }

    function historyRowsDescription() {
      const archived = Number(getArchivedAvailableRows() || 0);
      if (getIncludeArchived()) {
        return archived
          ? tf('history.all_includes', { count: number.format(archived) })
          : t('history.all_empty');
      }
      return archived
        ? tf('history.active_hidden', { count: number.format(archived) })
        : t('history.active_only');
    }

    function updateHistoryScopeControl() {
      historyScopeEl.value = getIncludeArchived() ? 'all' : 'active';
      const detail = historyRowsDescription();
      setFastTooltip(historyScopeEl, detail);
      setFastTooltip(historyScopeEl.parentElement, tf('history.archived_scan_hint', { detail }));
    }

    function updateLoadLimitControl() {
      const loadedLimit = getLoadedLimit();
      const value = limitValue(loadedLimit);
      const existing = new Set(Array.from(loadLimitEl.options).map(option => option.value));
      if (!existing.has(value)) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = tf('caption.loaded', { loaded: number.format(loadedLimit) });
        loadLimitEl.insertBefore(option, loadLimitEl.lastElementChild);
      }
      loadLimitEl.value = value;
    }

    async function hydrateDashboardRows(options = null) {
      if (!liveRefreshSupported || ['call', 'diagnostics'].includes(activeView())) return;
      const hydrateOptions = options || {};
      if (rowHydrationInFlight) {
        if (hydrateOptions.reset) rowHydrationRestartRequested = true;
        return;
      }
      const target = rowHydrationTarget();
      if (!target) {
        rowHydrationComplete = true;
        updateRowLoadProgress();
        return;
      }
      if (hydrateOptions.reset) {
        resetRowsForHydration();
        rowHydrationComplete = false;
        rowHydrationGeneration += 1;
        rebuildDashboardIndexes();
        rebuildFilterOptions();
        render();
      }
      if (getData().length >= target) {
        rowHydrationComplete = true;
        updateRowLoadProgress();
        return;
      }
      const generation = rowHydrationGeneration;
      rowHydrationInFlight = true;
      rowHydrationError = '';
      updateLiveStatus('status.checking', t('live.loading_rows'));
      updateRowLoadProgress();
      try {
        while (getData().length < target && generation === rowHydrationGeneration && !['call', 'diagnostics'].includes(activeView())) {
          const offset = getData().length;
          const remaining = target - offset;
          const chunkSize = Math.min(
            offset === 0 ? initialHydrationChunkSize : backgroundHydrationChunkSize,
            remaining,
          );
          const params = new URLSearchParams({
            limit: String(chunkSize),
            offset: String(offset),
            include_archived: getIncludeArchived() ? '1' : '0',
            lang: i18n.currentLanguage,
            _: String(Date.now()),
          });
          const response = await fetch(`/api/usage?${params.toString()}`, {
            headers: {
              'Accept': 'application/json',
              'X-Codex-Usage-Token': apiToken(),
            },
            cache: 'no-store',
          });
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          const payload = await response.json();
          if (payload.error) throw new Error(payload.error);
          if (generation !== rowHydrationGeneration || ['call', 'diagnostics'].includes(activeView())) break;
          const rows = payloadRows(payload);
          if (!rows.length) break;
          applyDashboardPayload(payload, { appendRows: true });
          updateRowLoadProgress();
          if (!payload.has_more || rows.length < chunkSize) break;
        }
        rowHydrationComplete = getData().length >= rowHydrationTarget();
        updateLiveStatus(autoRefreshEl.checked ? 'badge.live' : 'status.updated', `${loadedRowsDescription()}. ${historyRowsDescription()}`);
      } catch (error) {
        rowHydrationError = error.message || String(error);
        updateLiveStatus('status.refresh_error', tf('live.refresh_unavailable', { message: rowHydrationError, suffix: '' }));
      } finally {
        rowHydrationInFlight = false;
        updateRowLoadProgress();
        const shouldRestart = rowHydrationRestartRequested && !['call', 'diagnostics'].includes(activeView());
        rowHydrationRestartRequested = false;
        if (shouldRestart) {
          hydrateDashboardRows();
        } else {
          render();
        }
      }
    }

    async function refreshDashboardIfStale() {
      if (!liveRefreshSupported || !apiToken() || ['call', 'diagnostics'].includes(activeView())) return;
      try {
        const params = new URLSearchParams({
          include_archived: getIncludeArchived() ? '1' : '0',
          _: String(Date.now()),
        });
        const response = await fetch(`/api/status?${params.toString()}`, {
          headers: {
            'Accept': 'application/json',
          },
          cache: 'no-store',
        });
        if (!response.ok) return;
        const payload = await response.json();
        const statusRefreshAt = payload.latest_refresh_at || '';
        const scopedRows = Number(payload.row_counts?.scoped_rows);
        const rowCountChanged = Number.isFinite(scopedRows) && scopedRows !== getTotalAvailableRows();
        const refreshChanged = statusRefreshAt && statusRefreshAt !== deps.latestRefreshAt();
        if (rowCountChanged || refreshChanged) {
          refreshDashboardData(false, { refreshLogs: false, resetRows: true });
        } else if (rowsNeedHydration()) {
          hydrateDashboardRows();
        }
      } catch (_error) {
        // Background freshness checks must never interrupt the local dashboard.
      }
    }

    async function refreshDashboardData(manual = false, options = null) {
      if (!liveRefreshSupported) {
        updateLiveStatus('status.reloading', t('live.reloading_static'));
        window.location.reload();
        return;
      }
      const refreshOptions = options || {};
      const allowDiagnosticsBootstrap = Boolean(refreshOptions.allowDiagnosticsBootstrap);
      if (activeView() === 'call' && !manual) return;
      if (activeView() === 'diagnostics' && !manual && !allowDiagnosticsBootstrap) return;
      if (refreshInFlight) return;
      const refreshLogs = refreshOptions.refreshLogs === undefined ? manual : Boolean(refreshOptions.refreshLogs);
      const resetRows = refreshOptions.resetRows !== undefined
        ? Boolean(refreshOptions.resetRows)
        : Boolean(manual || refreshLogs);
      refreshInFlight = true;
      refreshDashboardEl.disabled = true;
      updateLiveStatus(refreshLogs ? 'status.refreshing' : 'status.checking', refreshLogs ? t('live.refreshing_index') : t('live.checking_usage'));
      try {
        const params = new URLSearchParams({
          limit: loadLimitEl.value,
          include_archived: getIncludeArchived() ? '1' : '0',
          lang: i18n.currentLanguage,
          shell: '1',
          _: String(Date.now()),
        });
        if (refreshLogs) params.set('refresh', '1');
        const response = await fetch(`/api/usage?${params.toString()}`, {
          headers: {
            'Accept': 'application/json',
            'X-Codex-Usage-Token': apiToken(),
          },
          cache: 'no-store',
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const nextPayload = await response.json();
        if (nextPayload.error) throw new Error(nextPayload.error);
        if (resetRows) {
          resetRowsForHydration();
          rowHydrationGeneration += 1;
          rowHydrationComplete = false;
        }
        applyDashboardPayload(nextPayload);
        if (!['call', 'diagnostics'].includes(activeView())) hydrateDashboardRows({ reset: resetRows });
        const result = nextPayload.refresh_result || {};
        const indexed = result.inserted_or_updated_events === undefined
          ? ''
          : tf('live.indexed', { rows: number.format(result.inserted_or_updated_events), files: number.format(result.scanned_files || 0) });
        const skipped = result.skipped_events
          ? tf('live.skipped', { count: number.format(result.skipped_events) })
          : '';
        updateLiveStatus(autoRefreshEl.checked ? 'badge.live' : 'status.updated', tf('live.updated_detail', { time: formatTimestamp(nextPayload.refreshed_at), loaded: loadedRowsDescription(), history: historyRowsDescription(), indexed, skipped }));
      } catch (error) {
        const message = error.message || String(error);
        updateLiveStatus('status.refresh_error', tf('live.refresh_unavailable', { message, suffix: manual ? t('live.refresh_suffix') : '' }));
        if (manual && message === 'HTTP 404') window.location.reload();
      } finally {
        refreshInFlight = false;
        refreshDashboardEl.disabled = false;
      }
    }

    function scheduleAutoRefresh() {
      if (autoRefreshTimer) window.clearInterval(autoRefreshTimer);
      autoRefreshTimer = null;
      if (!autoRefreshEl.checked || !liveRefreshSupported || ['call', 'diagnostics'].includes(activeView())) return;
      autoRefreshTimer = window.setInterval(() => {
        if (document.visibilityState === 'visible') refreshDashboardIfStale();
      }, liveRefreshIntervalMs);
    }

    return {
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
    };
  }

  window.CodexUsageDashboardLive = { create: createDashboardLiveRuntime };
})();
