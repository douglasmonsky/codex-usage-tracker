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
      setObservedUsage,
      t,
      tf,
      updateLiveStatus,
    } = deps;

    let refreshInFlight = false;
    let rowHydrationInFlight = false;
    let rowHydrationComplete = getData().length > 0;
    let rowHydrationNextOffset = getData().length;
    let rowHydrationError = '';
    let rowHydrationGeneration = 0;
    let rowHydrationRestartRequested = false;
    let usageImpactRetryTimer = null;
    let usageImpactRetryAttempts = 0;
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
      return liveRefreshSupported && !rowHydrationComplete && target > 0 && Math.max(getData().length, rowHydrationNextOffset) < target;
    }

    function updateRowLoadProgress() {
      if (!rowLoadProgressEl) return;
      const target = rowHydrationTarget();
      const loaded = Math.min(Math.max(getData().length, rowHydrationNextOffset), target || getData().length);
      const shouldShow = activeView() !== 'call' && liveRefreshSupported && (rowHydrationInFlight || rowsNeedHydration() || rowHydrationError);
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

    function scheduleUsageImpactRetry() {
      if (usageImpactRetryTimer || activeView() === 'call') return;
      if (usageImpactRetryAttempts >= 6) return;
      usageImpactRetryTimer = window.setTimeout(() => {
        usageImpactRetryTimer = null;
        usageImpactRetryAttempts += 1;
        refreshLoadedUsageImpactRows();
      }, Math.min(5000, 1200 + (usageImpactRetryAttempts * 600)));
    }

    function refreshResultNumber(result, key) {
      return Number(result?.[key] || 0);
    }

    function refreshResultHasDelta(result) {
      return result && Object.prototype.hasOwnProperty.call(result, 'skipped_downstream_work');
    }

    function refreshResultIsNoOp(result) {
      return refreshResultHasDelta(result) && result.skipped_downstream_work === true;
    }

    function refreshResultHasRowChanges(result) {
      return refreshResultNumber(result, 'inserted_records') > 0
        || refreshResultNumber(result, 'inserted_or_updated_events') > 0;
    }

    function refreshResultNeedsReset(result) {
      return refreshResultNumber(result, 'deleted_records') > 0
        || refreshResultNumber(result, 'full_reparse_source_files') > 0;
    }

    function liveApiHttpMessage(status) {
      const reloadHint = t('live.refresh_suffix').replace(/^\.\s*/, '');
      return `${tf('context.api_http', { status })} ${reloadHint}`;
    }

    function liveApiResponseMessage(response) {
      if (response.status === 401 || response.status === 403) {
        return liveApiHttpMessage(String(response.status));
      }
      return `HTTP ${response.status}`;
    }

    function stopLiveRefreshForAuthFailure(response) {
      if (response.status !== 401 && response.status !== 403) return false;
      if (autoRefreshEl) autoRefreshEl.checked = false;
      scheduleAutoRefresh();
      rowHydrationRestartRequested = false;
      rowHydrationError = liveApiResponseMessage(response);
      updateLiveStatus('status.refresh_error', tf('live.refresh_unavailable', { message: rowHydrationError, suffix: '' }));
      updateRowLoadProgress();
      return true;
    }

    async function fetchCallRows(limit, offset) {
      const params = new URLSearchParams({
        limit: String(limit),
        offset: String(offset),
        include_archived: getIncludeArchived() ? '1' : '0',
        sort: 'time',
        direction: 'desc',
        lang: i18n.currentLanguage,
        _: String(Date.now()),
      });
      const response = await fetch(`/api/calls?${params.toString()}`, {
        headers: {
          'Accept': 'application/json',
          'X-Codex-Usage-Token': apiToken(),
        },
        cache: 'no-store',
      });
      if (!response.ok) {
        stopLiveRefreshForAuthFailure(response);
        throw new Error(liveApiResponseMessage(response));
      }
      const payload = await response.json();
      if (payload.error) throw new Error(payload.error);
      return payload;
    }

    async function refreshLoadedUsageImpactRows() {
      if (!liveRefreshSupported || activeView() === 'call' || !getData().length) return;
      if (rowHydrationInFlight) {
        scheduleUsageImpactRetry();
        return;
      }
      try {
        const limit = Math.max(1, Math.min(getData().length, initialHydrationChunkSize || 500));
        const payload = await fetchCallRows(limit, 0);
        applyDashboardPayload(payload, { appendRows: true });
        if (payload.usage_impact_pending) {
          scheduleUsageImpactRetry();
        } else {
          usageImpactRetryAttempts = 0;
        }
        render();
      } catch (_error) {
        // Usage-impact estimates are supplemental. Row hydration and live
        // refresh must stay usable even if this background update fails.
      }
    }

    async function refreshAppendedRows(refreshResult, scopedRows) {
      if (!liveRefreshSupported || activeView() === 'call') return;
      if (rowHydrationInFlight) {
        rowHydrationRestartRequested = true;
        return;
      }
      const inserted = Math.max(
        refreshResultNumber(refreshResult, 'inserted_records'),
        refreshResultNumber(refreshResult, 'inserted_or_updated_events'),
        1,
      );
      const chunkLimit = Math.min(
        Math.max(inserted, initialHydrationChunkSize),
        Math.max(initialHydrationChunkSize, backgroundHydrationChunkSize),
      );
      rowHydrationError = '';
      updateLiveStatus('status.checking', t('live.loading_rows'));
      updateRowLoadProgress();
      const payload = await fetchCallRows(chunkLimit, 0);
      if (Number.isFinite(scopedRows) && payload.total_matched_rows === undefined) {
        payload.total_matched_rows = scopedRows;
      }
      applyDashboardPayload(payload, { appendRows: true });
      rowHydrationComplete = getData().length >= rowHydrationTarget();
      updateRowLoadProgress();
      updateLiveStatus(autoRefreshEl.checked ? 'badge.live' : 'status.updated', `${loadedRowsDescription()}. ${historyRowsDescription()}`);
    }

    async function hydrateDashboardRows(options = null) {
      if (!liveRefreshSupported || activeView() === 'call') return;
      const hydrateOptions = options || {};
      if (rowHydrationInFlight) {
        if (hydrateOptions.reset) rowHydrationRestartRequested = true;
        return;
      }
      const target = rowHydrationTarget();
      if (!target) {
        rowHydrationComplete = true;
        rowHydrationNextOffset = 0;
        updateRowLoadProgress();
        return;
      }
      if (hydrateOptions.reset) {
        resetRowsForHydration();
        rowHydrationComplete = false;
        rowHydrationNextOffset = 0;
        rowHydrationGeneration += 1;
        rebuildDashboardIndexes();
        rebuildFilterOptions();
        render();
      }
      if (getData().length >= target) {
        rowHydrationComplete = true;
        rowHydrationNextOffset = Math.max(rowHydrationNextOffset, target);
        updateRowLoadProgress();
        return;
      }
      const generation = rowHydrationGeneration;
      rowHydrationInFlight = true;
      rowHydrationError = '';
      let usageImpactPending = false;
      let reachedEnd = false;
      updateLiveStatus('status.checking', t('live.loading_rows'));
      updateRowLoadProgress();
      try {
        while (Math.max(getData().length, rowHydrationNextOffset) < target && generation === rowHydrationGeneration && activeView() !== 'call') {
          const offset = Math.max(0, rowHydrationNextOffset);
          const remaining = target - offset;
          if (remaining <= 0) break;
          const chunkSize = Math.min(
            offset === 0 ? initialHydrationChunkSize : backgroundHydrationChunkSize,
            remaining,
          );
          const payload = await fetchCallRows(chunkSize, offset);
          if (payload.usage_impact_pending) usageImpactPending = true;
          if (generation !== rowHydrationGeneration || activeView() === 'call') break;
          const rows = payloadRows(payload);
          if (!rows.length) {
            reachedEnd = true;
            break;
          }
          const nextOffset = Number(payload.next_offset);
          rowHydrationNextOffset = Number.isFinite(nextOffset) && nextOffset > offset
            ? nextOffset
            : offset + rows.length;
          applyDashboardPayload(payload, { appendRows: true });
          updateRowLoadProgress();
          if (!payload.has_more || rows.length < chunkSize) {
            reachedEnd = true;
            break;
          }
        }
        rowHydrationComplete = reachedEnd || Math.max(getData().length, rowHydrationNextOffset) >= rowHydrationTarget();
        if (!usageImpactPending) usageImpactRetryAttempts = 0;
        updateLiveStatus(autoRefreshEl.checked ? 'badge.live' : 'status.updated', `${loadedRowsDescription()}. ${historyRowsDescription()}`);
      } catch (error) {
        rowHydrationError = error.message || String(error);
        updateLiveStatus('status.refresh_error', tf('live.refresh_unavailable', { message: rowHydrationError, suffix: '' }));
      } finally {
        rowHydrationInFlight = false;
        updateRowLoadProgress();
        const shouldRestart = rowHydrationRestartRequested && activeView() !== 'call';
        rowHydrationRestartRequested = false;
        if (shouldRestart) {
          hydrateDashboardRows();
        } else {
          render();
          if (usageImpactPending) scheduleUsageImpactRetry();
        }
      }
    }

    async function refreshDashboardIfStale() {
      if (!liveRefreshSupported || !apiToken() || activeView() === 'call') return;
      try {
        const params = new URLSearchParams({
          include_archived: getIncludeArchived() ? '1' : '0',
          refresh: '1',
          _: String(Date.now()),
        });
        const response = await fetch(`/api/status?${params.toString()}`, {
          headers: {
            'Accept': 'application/json',
            'X-Codex-Usage-Token': apiToken(),
          },
          cache: 'no-store',
        });
        if (!response.ok) {
          stopLiveRefreshForAuthFailure(response);
          return;
        }
        const payload = await response.json();
        const scopedRows = Number(payload.row_counts?.scoped_rows);
        if (payload.observed_usage) {
          setObservedUsage(payload.observed_usage);
        }
        const refreshResult = payload.refresh_result || {};
        if (refreshResultIsNoOp(refreshResult)) {
          if (rowsNeedHydration()) hydrateDashboardRows();
          return;
        }
        const rowCountChanged = Number.isFinite(scopedRows) && scopedRows !== getTotalAvailableRows();
        if (refreshResultNeedsReset(refreshResult)) {
          refreshDashboardData(false, { refreshLogs: false, resetRows: true });
        } else if (refreshResultHasRowChanges(refreshResult) || rowCountChanged) {
          await refreshAppendedRows(refreshResult, scopedRows);
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
      if (activeView() === 'call' && !manual) return;
      if (refreshInFlight) return;
      const refreshOptions = options || {};
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
          stopLiveRefreshForAuthFailure(response);
          throw new Error(liveApiResponseMessage(response));
        }
        const nextPayload = await response.json();
        if (nextPayload.error) throw new Error(nextPayload.error);
        if (resetRows) {
          resetRowsForHydration();
          rowHydrationGeneration += 1;
          rowHydrationComplete = false;
          rowHydrationNextOffset = 0;
        }
        applyDashboardPayload(nextPayload);
        if (activeView() !== 'call') hydrateDashboardRows({ reset: resetRows });
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
      if (!autoRefreshEl.checked || !liveRefreshSupported || activeView() === 'call') return;
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
