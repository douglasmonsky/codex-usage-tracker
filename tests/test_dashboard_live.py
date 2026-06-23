from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def _run_dashboard_live_script(script: str) -> dict[str, object]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for dashboard live helper tests")
    repo_root = Path(__file__).resolve().parents[1]
    script_path = (
        repo_root
        / "src"
        / "codex_usage_tracker"
        / "plugin_data"
        / "dashboard"
        / "dashboard_live.js"
    )
    wrapped = f"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync({json.dumps(str(script_path))}, 'utf8');
const context = {{
  window: {{ clearInterval, setInterval }},
  URLSearchParams,
  fetch: async (url, options) => globalThis.__fetch(url, options),
  console,
}};
vm.createContext(context);
vm.runInContext(code, context);
const factory = context.window.CodexUsageDashboardLive;
{script}
"""
    result = subprocess.run(
        [node, "-e", wrapped],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_dashboard_live_allows_diagnostics_bootstrap_refresh() -> None:
    payload = _run_dashboard_live_script(
        """
(async () => {
  const calls = [];
  globalThis.__fetch = async (url, options) => {
    calls.push({ url, headers: options.headers });
    return {
      ok: true,
      json: async () => ({
        rows: [],
        refreshed_at: '2026-06-19T00:00:00Z',
        refresh_result: null,
        total_available_rows: 0,
      }),
    };
  };
  const statusUpdates = [];
  const appliedPayloads = [];
  const runtime = factory.create({
    activeView: () => 'diagnostics',
    apiToken: () => 'test-token',
    applyDashboardPayload: payload => appliedPayloads.push(payload),
    autoRefreshEl: { checked: false },
    backgroundHydrationChunkSize: 2000,
    formatTimestamp: value => value,
    getArchivedAvailableRows: () => 0,
    getData: () => [],
    getIncludeArchived: () => false,
    getLoadedLimit: () => null,
    getTotalAvailableRows: () => 0,
    historyScopeEl: { value: 'active', parentElement: {} },
    i18n: { currentLanguage: 'en' },
    initialHydrationChunkSize: 500,
    latestRefreshAt: () => '',
    limitValue: value => value === null ? 'all' : String(value),
    liveRefreshIntervalMs: 10000,
    liveRefreshSupported: true,
    loadLimitEl: { value: '5000', options: [], lastElementChild: null, insertBefore: () => {} },
    number: new Intl.NumberFormat('en-US'),
    payloadRows: payload => payload.rows || [],
    rebuildDashboardIndexes: () => {},
    rebuildFilterOptions: () => {},
    refreshDashboardEl: { disabled: false },
    render: () => {},
    resetRowsForHydration: () => {},
    rowLoadProgressBarEl: { style: {} },
    rowLoadProgressCountEl: { textContent: '' },
    rowLoadProgressEl: { hidden: true },
    rowLoadProgressLabelEl: { textContent: '' },
    setFastTooltip: () => {},
    t: key => key,
    tf: (key, values = {}) => `${key}:${JSON.stringify(values)}`,
    updateLiveStatus: (key, detail) => statusUpdates.push({ key, detail }),
  });
  await runtime.refreshDashboardData(false, {
    refreshLogs: false,
    resetRows: true,
    allowDiagnosticsBootstrap: true,
  });
  console.log(JSON.stringify({
    fetchCount: calls.length,
    firstUrl: calls[0] ? calls[0].url : '',
    token: calls[0] ? calls[0].headers['X-Codex-Usage-Token'] : '',
    appliedCount: appliedPayloads.length,
    statusKeys: statusUpdates.map(entry => entry.key),
  }));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
"""
    )

    assert payload["fetchCount"] == 1
    assert payload["firstUrl"].startswith("/api/usage?")
    assert "shell=1" in payload["firstUrl"]
    assert "refresh=1" not in payload["firstUrl"]
    assert payload["token"] == "test-token"
    assert payload["appliedCount"] == 1
    assert payload["statusKeys"] == ["status.checking", "status.updated"]


def test_dashboard_live_skips_diagnostics_auto_refresh_cycle() -> None:
    payload = _run_dashboard_live_script(
        """
(async () => {
  const calls = [];
  const statusUpdates = [];
  const appliedPayloads = [];
  let scheduledIntervals = 0;
  context.window.setInterval = () => {
    scheduledIntervals += 1;
    return 1;
  };
  context.window.clearInterval = () => {};
  globalThis.__fetch = async (url, options) => {
    calls.push({ url, headers: options.headers });
    return {
      ok: true,
      json: async () => ({
        rows: [],
        refreshed_at: '2026-06-19T00:00:00Z',
        refresh_result: {
          inserted_or_updated_events: 1,
          scanned_files: 1,
          skipped_events: 0,
        },
        total_available_rows: 1,
      }),
    };
  };
  const refreshDashboardEl = { disabled: false };
  const runtime = factory.create({
    activeView: () => 'diagnostics',
    apiToken: () => 'test-token',
    applyDashboardPayload: payload => appliedPayloads.push(payload),
    autoRefreshEl: { checked: true },
    backgroundHydrationChunkSize: 2000,
    formatTimestamp: value => value,
    getArchivedAvailableRows: () => 0,
    getData: () => [],
    getIncludeArchived: () => false,
    getLoadedLimit: () => null,
    getTotalAvailableRows: () => 1,
    historyScopeEl: { value: 'active', parentElement: {} },
    i18n: { currentLanguage: 'en' },
    initialHydrationChunkSize: 500,
    latestRefreshAt: () => '',
    limitValue: value => value === null ? 'all' : String(value),
    liveRefreshIntervalMs: 10000,
    liveRefreshSupported: true,
    loadLimitEl: { value: '5000', options: [], lastElementChild: null, insertBefore: () => {} },
    number: new Intl.NumberFormat('en-US'),
    payloadRows: payload => payload.rows || [],
    rebuildDashboardIndexes: () => {},
    rebuildFilterOptions: () => {},
    refreshDashboardEl,
    render: () => {},
    resetRowsForHydration: () => {},
    rowLoadProgressBarEl: { style: {} },
    rowLoadProgressCountEl: { textContent: '' },
    rowLoadProgressEl: { hidden: true },
    rowLoadProgressLabelEl: { textContent: '' },
    setFastTooltip: () => {},
    t: key => key,
    tf: (key, values = {}) => `${key}:${JSON.stringify(values)}`,
    updateLiveStatus: (key, detail) => statusUpdates.push({ key, detail }),
  });
  runtime.scheduleAutoRefresh();
  await runtime.refreshDashboardLive();
  console.log(JSON.stringify({
    fetchCount: calls.length,
    appliedCount: appliedPayloads.length,
    statusKeys: statusUpdates.map(entry => entry.key),
    scheduledIntervals,
    refreshDisabled: refreshDashboardEl.disabled,
  }));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
"""
    )

    assert payload["fetchCount"] == 0
    assert payload["appliedCount"] == 0
    assert payload["statusKeys"] == []
    assert payload["scheduledIntervals"] == 0
    assert payload["refreshDisabled"] is False


def test_dashboard_live_prepends_new_rows_after_cached_index_refresh() -> None:
    payload = _run_dashboard_live_script(
        """
(async () => {
  const calls = [];
  const appliedPayloads = [];
  let totalRows = 4;
  let data = [
    { record_id: 'old-1' },
    { record_id: 'old-2' },
    { record_id: 'old-3' },
    { record_id: 'old-4' },
  ];
  globalThis.__fetch = async (url, options) => {
    calls.push({ url, headers: options.headers });
    const isRefresh = url.includes('refresh=1');
    return {
      ok: true,
      json: async () => ({
        rows: isRefresh ? [] : [{ record_id: 'new-1' }],
        refreshed_at: '2026-06-19T00:00:00Z',
        refresh_result: {
          inserted_or_updated_events: 1,
          scanned_files: 1,
          skipped_events: 0,
        },
        total_available_rows: 5,
      }),
    };
  };
  const runtime = factory.create({
    activeView: () => 'calls',
    apiToken: () => 'test-token',
    applyDashboardPayload: (payload, options = {}) => {
      appliedPayloads.push({
        rows: (payload.rows || []).map(row => row.record_id),
        options,
      });
      totalRows = payload.total_available_rows || totalRows;
      if (options.prependRows) {
        const incoming = payload.rows || [];
        const incomingIds = new Set(incoming.map(row => row.record_id));
        data = [...incoming, ...data.filter(row => !incomingIds.has(row.record_id))];
      }
    },
    autoRefreshEl: { checked: true },
    backgroundHydrationChunkSize: 2000,
    formatTimestamp: value => value,
    getArchivedAvailableRows: () => 0,
    getData: () => data,
    getIncludeArchived: () => false,
    getLoadedLimit: () => 5000,
    getTotalAvailableRows: () => totalRows,
    historyScopeEl: { value: 'active', parentElement: {} },
    i18n: { currentLanguage: 'en' },
    initialHydrationChunkSize: 500,
    latestRefreshAt: () => '',
    limitValue: value => value === null ? 'all' : String(value),
    liveRefreshIntervalMs: 10000,
    liveRefreshSupported: true,
    loadLimitEl: { value: '5000', options: [], lastElementChild: null, insertBefore: () => {} },
    number: new Intl.NumberFormat('en-US'),
    payloadRows: payload => payload.rows || [],
    rebuildDashboardIndexes: () => {},
    rebuildFilterOptions: () => {},
    refreshDashboardEl: { disabled: false },
    render: () => {},
    resetRowsForHydration: () => {},
    rowLoadProgressBarEl: { style: {} },
    rowLoadProgressCountEl: { textContent: '' },
    rowLoadProgressEl: { hidden: true },
    rowLoadProgressLabelEl: { textContent: '' },
    setFastTooltip: () => {},
    t: key => key,
    tf: (key, values = {}) => `${key}:${JSON.stringify(values)}`,
    updateLiveStatus: () => {},
  });
  await runtime.refreshDashboardLive();
  console.log(JSON.stringify({
    urls: calls.map(call => call.url.replace(/_=[0-9]+/, '_=<ts>')),
    tokens: calls.map(call => call.headers['X-Codex-Usage-Token']),
    appliedPayloads,
    data: data.map(row => row.record_id),
  }));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
"""
    )

    assert payload["urls"] == [
        "/api/usage?limit=5000&include_archived=0&lang=en&shell=1&_=<ts>&refresh=1",
        "/api/usage?limit=1&offset=0&include_archived=0&lang=en&_=<ts>",
    ]
    assert payload["tokens"] == ["test-token", "test-token"]
    assert payload["appliedPayloads"] == [
        {"rows": [], "options": {"preserveRows": True}},
        {"rows": ["new-1"], "options": {"prependRows": True, "trimRowsToTarget": True}},
    ]
    assert payload["data"] == ["new-1", "old-1", "old-2", "old-3", "old-4"]


def test_dashboard_live_hydrates_empty_shell_after_refresh() -> None:
    payload = _run_dashboard_live_script(
        """
(async () => {
  const calls = [];
  const appliedPayloads = [];
  let totalRows = 9862;
  let data = [];
  globalThis.__fetch = async (url, options) => {
    calls.push({ url, headers: options.headers });
    const shellRequest = url.includes('shell=1');
    return {
      ok: true,
      json: async () => ({
        rows: shellRequest
          ? []
          : [{ record_id: 'row-1' }, { record_id: 'row-2' }, { record_id: 'row-3' }],
        refreshed_at: '2026-06-19T00:00:00Z',
        refresh_result: {
          inserted_or_updated_events: 0,
          scanned_files: 411,
          skipped_events: 0,
        },
        total_available_rows: 9862,
        has_more: true,
      }),
    };
  };
  const runtime = factory.create({
    activeView: () => 'calls',
    apiToken: () => 'test-token',
    applyDashboardPayload: (payload, options = {}) => {
      appliedPayloads.push({
        rows: (payload.rows || []).map(row => row.record_id),
        options,
      });
      totalRows = payload.total_available_rows || totalRows;
      if (options.appendRows) data = [...data, ...(payload.rows || [])];
    },
    autoRefreshEl: { checked: false },
    backgroundHydrationChunkSize: 2000,
    formatTimestamp: value => value,
    getArchivedAvailableRows: () => 0,
    getData: () => data,
    getIncludeArchived: () => false,
    getLoadedLimit: () => 5000,
    getTotalAvailableRows: () => totalRows,
    historyScopeEl: { value: 'active', parentElement: {} },
    i18n: { currentLanguage: 'en' },
    initialHydrationChunkSize: 500,
    latestRefreshAt: () => '',
    limitValue: value => value === null ? 'all' : String(value),
    liveRefreshIntervalMs: 10000,
    liveRefreshSupported: true,
    loadLimitEl: { value: '5000', options: [], lastElementChild: null, insertBefore: () => {} },
    number: new Intl.NumberFormat('en-US'),
    payloadRows: payload => payload.rows || [],
    rebuildDashboardIndexes: () => {},
    rebuildFilterOptions: () => {},
    refreshDashboardEl: { disabled: false },
    render: () => {},
    resetRowsForHydration: () => {},
    rowLoadProgressBarEl: { style: {} },
    rowLoadProgressCountEl: { textContent: '' },
    rowLoadProgressEl: { hidden: true },
    rowLoadProgressLabelEl: { textContent: '' },
    setFastTooltip: () => {},
    t: key => key,
    tf: (key, values = {}) => `${key}:${JSON.stringify(values)}`,
    updateLiveStatus: () => {},
  });
  await runtime.refreshDashboardLive();
  console.log(JSON.stringify({
    urls: calls.map(call => call.url.replace(/_=[0-9]+/, '_=<ts>')),
    tokens: calls.map(call => call.headers['X-Codex-Usage-Token']),
    appliedPayloads,
    data: data.map(row => row.record_id),
  }));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
"""
    )

    assert payload["urls"] == [
        "/api/usage?limit=5000&include_archived=0&lang=en&shell=1&_=<ts>&refresh=1",
        "/api/usage?limit=500&offset=0&include_archived=0&lang=en&_=<ts>",
    ]
    assert payload["tokens"] == ["test-token", "test-token"]
    assert payload["appliedPayloads"] == [
        {"rows": [], "options": {"preserveRows": True}},
        {"rows": ["row-1", "row-2", "row-3"], "options": {"appendRows": True}},
    ]
    assert payload["data"] == ["row-1", "row-2", "row-3"]


def test_dashboard_bootstraps_direct_diagnostics_view() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    dashboard_js = (
        repo_root
        / "src"
        / "codex_usage_tracker"
        / "plugin_data"
        / "dashboard"
        / "dashboard.js"
    ).read_text(encoding="utf-8")

    assert "allowDiagnosticsBootstrap: true" in dashboard_js
