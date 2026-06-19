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
