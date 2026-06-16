from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def _run_dashboard_data_script(script: str) -> dict[str, object]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for dashboard data helper tests")
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "src" / "codex_usage_tracker" / "plugin_data" / "dashboard" / "dashboard_data.js"
    wrapped = f"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync({json.dumps(str(script_path))}, 'utf8');
const context = {{ window: {{}} }};
vm.createContext(context);
vm.runInContext(code, context);
const helpers = context.window.CodexUsageDashboardData;
{script}
"""
    result = subprocess.run(
        [node, "-e", wrapped],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _run_dashboard_format_script(script: str) -> dict[str, object]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for dashboard format helper tests")
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "src" / "codex_usage_tracker" / "plugin_data" / "dashboard" / "dashboard_format.js"
    wrapped = f"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync({json.dumps(str(script_path))}, 'utf8');
const context = {{ window: {{}}, Intl }};
vm.createContext(context);
vm.runInContext(code, context);
const helpers = context.window.CodexUsageDashboardFormat;
{script}
"""
    result = subprocess.run(
        [node, "-e", wrapped],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _run_dashboard_live_script(script: str) -> dict[str, object]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for dashboard live helper tests")
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "src" / "codex_usage_tracker" / "plugin_data" / "dashboard" / "dashboard_live.js"
    wrapped = f"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync({json.dumps(str(script_path))}, 'utf8');
const context = {{
  window: {{
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
  }},
  document: {{ visibilityState: 'visible' }},
  URLSearchParams,
  setTimeout,
  clearTimeout,
  setInterval,
  clearInterval,
}};
vm.createContext(context);
vm.runInContext(code, context);
const helpers = context.window.CodexUsageDashboardLive;
(async () => {{
{script}
}})().catch(error => {{
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
}});
"""
    result = subprocess.run(
        [node, "-e", wrapped],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_compact_number_collapses_billion_scale_values() -> None:
    payload = _run_dashboard_format_script(
        """
console.log(JSON.stringify({
  below: helpers.compactNumber(999999999),
  one: helpers.compactNumber(1000000000),
  decimal: helpers.compactNumber(1234567890),
  large: helpers.compactNumber(2280875918),
}));
"""
    )

    assert payload == {
        "below": "999,999,999",
        "one": "1B",
        "decimal": "1.2B",
        "large": "2.3B",
    }


def test_live_refresh_append_delta_hydrates_rows_through_calls_api() -> None:
    payload = _run_dashboard_live_script(
        """
let data = [{ record_id: 'b' }, { record_id: 'c' }];
let totalAvailableRows = 2;
let requestUrls = [];
let appliedPayloads = [];
let liveStatuses = [];
let renderCount = 0;
let fetchIndex = 0;
const responses = [
  {
    ok: true,
    status: 200,
    json: async () => ({
      row_counts: { scoped_rows: 3 },
      refresh_result: {
        skipped_downstream_work: false,
        inserted_records: 1,
        deleted_records: 0,
        full_reparse_source_files: 0,
      },
      observed_usage: { available: true },
    }),
  },
  {
    ok: true,
    status: 200,
    json: async () => ({
      rows: [{ record_id: 'a' }, { record_id: 'b' }],
      row_count: 2,
      total_matched_rows: 3,
      has_more: true,
      usage_impact_pending: false,
    }),
  },
];
context.fetch = async url => {
  requestUrls.push(String(url));
  return responses[fetchIndex++];
};
const runtime = helpers.create({
  activeView: () => 'calls',
  apiToken: () => 'token',
  applyDashboardPayload: (payload, options = {}) => {
    appliedPayloads.push({ appendRows: Boolean(options.appendRows), keys: Object.keys(payload).sort() });
    if (options.appendRows) {
      const seen = new Set(data.map(row => row.record_id));
      data = data.concat((payload.rows || []).filter(row => {
        if (!row.record_id || seen.has(row.record_id)) return false;
        seen.add(row.record_id);
        return true;
      }));
    } else {
      data = payload.rows || [];
      if (payload.total_available_rows !== undefined) totalAvailableRows = payload.total_available_rows;
    }
  },
  autoRefreshEl: { checked: true },
  formatTimestamp: value => String(value || ''),
  getData: () => data,
  getIncludeArchived: () => true,
  getLoadedLimit: () => null,
  getTotalAvailableRows: () => totalAvailableRows,
  getArchivedAvailableRows: () => 0,
  historyScopeEl: { value: 'all', parentElement: {} },
  initialHydrationChunkSize: 2,
  backgroundHydrationChunkSize: 2,
  i18n: { currentLanguage: 'en' },
  liveRefreshIntervalMs: 10000,
  liveRefreshSupported: true,
  loadLimitEl: { value: 'all', options: [], insertBefore: () => {}, lastElementChild: null },
  limitValue: value => value === null ? 'all' : String(value),
  number: { format: value => String(value) },
  payloadRows: payload => payload.rows || [],
  rebuildDashboardIndexes: () => {},
  rebuildFilterOptions: () => {},
  refreshDashboardEl: { disabled: false },
  render: () => { renderCount += 1; },
  resetRowsForHydration: () => { data = []; },
  rowLoadProgressBarEl: { style: {} },
  rowLoadProgressCountEl: { textContent: '' },
  rowLoadProgressEl: { hidden: true },
  rowLoadProgressLabelEl: { textContent: '' },
  setFastTooltip: () => {},
  setObservedUsage: () => {},
  t: key => key,
  tf: (key, values) => `${key}:${JSON.stringify(values || {})}`,
  updateLiveStatus: (key, detail) => liveStatuses.push({ key, detail }),
});
await runtime.refreshDashboardIfStale();
await new Promise(resolve => setTimeout(resolve, 25));
console.log(JSON.stringify({
  requestUrls,
  appliedPayloads,
  dataLength: data.length,
  liveStatuses,
  renderCount,
}));
"""
    )

    assert payload["dataLength"] == 3
    assert payload["requestUrls"][0].startswith("/api/status?")
    assert payload["requestUrls"][1].startswith("/api/calls?")
    assert len(payload["requestUrls"]) == 2
    assert all(not url.startswith("/api/usage?") for url in payload["requestUrls"])
    assert payload["appliedPayloads"][0]["appendRows"] is True


def test_live_usage_impact_retry_updates_loaded_rows_without_rehydrating_table() -> None:
    payload = _run_dashboard_live_script(
        """
let data = [];
let requestUrls = [];
let resetCalls = 0;
let renderCount = 0;
let fetchIndex = 0;
const responses = [
  {
    ok: true,
    status: 200,
    json: async () => ({
      rows: [
        { record_id: 'a', usage_impact_pending: true, usage_impact: { primary: null, secondary: null } },
        { record_id: 'b', usage_impact_pending: true, usage_impact: { primary: null, secondary: null } },
      ],
      row_count: 2,
      total_matched_rows: 2,
      has_more: false,
      usage_impact_pending: true,
    }),
  },
  {
    ok: true,
    status: 200,
    json: async () => ({
      rows: [
        { record_id: 'a', usage_impact: { primary: null, secondary: { estimate_percent: 0.123 } } },
        { record_id: 'b', usage_impact: { primary: null, secondary: { estimate_percent: 0.456 } } },
      ],
      row_count: 2,
      total_matched_rows: 2,
      has_more: false,
      usage_impact_pending: false,
    }),
  },
];
context.fetch = async url => {
  requestUrls.push(String(url));
  return responses[fetchIndex++];
};
const runtime = helpers.create({
  activeView: () => 'calls',
  apiToken: () => 'token',
  applyDashboardPayload: (payload, options = {}) => {
    if (!options.appendRows) {
      data = payload.rows || [];
      return;
    }
    const indexById = new Map(data.map((row, index) => [row.record_id, index]));
    for (const row of payload.rows || []) {
      if (indexById.has(row.record_id)) {
        data[indexById.get(row.record_id)] = { ...data[indexById.get(row.record_id)], ...row };
      } else {
        indexById.set(row.record_id, data.length);
        data.push(row);
      }
    }
  },
  autoRefreshEl: { checked: true },
  formatTimestamp: value => String(value || ''),
  getData: () => data,
  getIncludeArchived: () => true,
  getLoadedLimit: () => null,
  getTotalAvailableRows: () => 2,
  getArchivedAvailableRows: () => 0,
  historyScopeEl: { value: 'all', parentElement: {} },
  initialHydrationChunkSize: 2,
  backgroundHydrationChunkSize: 2,
  i18n: { currentLanguage: 'en' },
  liveRefreshIntervalMs: 10000,
  liveRefreshSupported: true,
  loadLimitEl: { value: 'all', options: [], insertBefore: () => {}, lastElementChild: null },
  limitValue: value => value === null ? 'all' : String(value),
  number: { format: value => String(value) },
  payloadRows: payload => payload.rows || [],
  rebuildDashboardIndexes: () => {},
  rebuildFilterOptions: () => {},
  refreshDashboardEl: { disabled: false },
  render: () => { renderCount += 1; },
  resetRowsForHydration: () => { resetCalls += 1; data = []; },
  rowLoadProgressBarEl: { style: {} },
  rowLoadProgressCountEl: { textContent: '' },
  rowLoadProgressEl: { hidden: true },
  rowLoadProgressLabelEl: { textContent: '' },
  setFastTooltip: () => {},
  setObservedUsage: () => {},
  t: key => key,
  tf: (key, values) => `${key}:${JSON.stringify(values || {})}`,
  updateLiveStatus: () => {},
});
await runtime.hydrateDashboardRows();
await new Promise(resolve => setTimeout(resolve, 2100));
console.log(JSON.stringify({
  requestUrls,
  resetCalls,
  renderCount,
  data,
}));
"""
    )

    assert payload["resetCalls"] == 0
    assert payload["renderCount"] >= 1
    assert len(payload["requestUrls"]) == 2
    assert all(url.startswith("/api/calls?") for url in payload["requestUrls"])
    assert payload["data"][0]["record_id"] == "a"
    assert payload["data"][0]["usage_impact"]["secondary"]["estimate_percent"] == 0.123


def test_live_refresh_auth_failure_stops_polling_and_surfaces_error() -> None:
    payload = _run_dashboard_live_script(
        """
let liveStatuses = [];
let progressHidden = true;
const autoRefreshEl = { checked: true };
context.fetch = async url => ({
  ok: false,
  status: 403,
  json: async () => ({ error: 'bad token' }),
});
const runtime = helpers.create({
  activeView: () => 'calls',
  apiToken: () => 'stale-token',
  applyDashboardPayload: () => {},
  autoRefreshEl,
  formatTimestamp: value => String(value || ''),
  getData: () => [],
  getIncludeArchived: () => true,
  getLoadedLimit: () => null,
  getTotalAvailableRows: () => 10,
  getArchivedAvailableRows: () => 0,
  historyScopeEl: { value: 'all', parentElement: {} },
  initialHydrationChunkSize: 2,
  backgroundHydrationChunkSize: 2,
  i18n: { currentLanguage: 'en' },
  liveRefreshIntervalMs: 10000,
  liveRefreshSupported: true,
  loadLimitEl: { value: 'all', options: [], insertBefore: () => {}, lastElementChild: null },
  limitValue: value => value === null ? 'all' : String(value),
  number: { format: value => String(value) },
  payloadRows: payload => payload.rows || [],
  rebuildDashboardIndexes: () => {},
  rebuildFilterOptions: () => {},
  refreshDashboardEl: { disabled: false },
  render: () => {},
  resetRowsForHydration: () => {},
  rowLoadProgressBarEl: { style: {} },
  rowLoadProgressCountEl: { textContent: '' },
  rowLoadProgressEl: {
    get hidden() { return progressHidden; },
    set hidden(value) { progressHidden = value; },
  },
  rowLoadProgressLabelEl: { textContent: '' },
  setFastTooltip: () => {},
  setObservedUsage: () => {},
  t: key => key === 'live.refresh_suffix'
    ? '. Reload this page after regenerating a static dashboard, or run codex-usage-tracker serve-dashboard.'
    : key,
  tf: (key, values) => `${key}:${JSON.stringify(values || {})}`,
  updateLiveStatus: (key, detail) => liveStatuses.push({ key, detail }),
});
await runtime.refreshDashboardIfStale();
console.log(JSON.stringify({
  autoRefreshChecked: autoRefreshEl.checked,
  liveStatuses,
  progressHidden,
}));
"""
    )

    assert payload["autoRefreshChecked"] is False
    assert payload["progressHidden"] is False
    assert payload["liveStatuses"][-1]["key"] == "status.refresh_error"
    assert "403" in payload["liveStatuses"][-1]["detail"]
    assert "Reload this page" in payload["liveStatuses"][-1]["detail"]


def test_cache_diagnostic_classification_handles_expected_patterns() -> None:
    payload = _run_dashboard_data_script(
        """
const previousWarm = { input_tokens: 1000, cached_input_tokens: 900, uncached_input_tokens: 100, cache_ratio: 0.9 };
const cases = {
  warm: helpers.classifyCacheDiagnostic({ input_tokens: 1000, cached_input_tokens: 920, uncached_input_tokens: 80, cache_ratio: 0.92 }),
  cold: helpers.classifyCacheDiagnostic({ input_tokens: 1600, cached_input_tokens: 10, uncached_input_tokens: 1590, cache_ratio: 0.01 }, previousWarm),
  partial: helpers.classifyCacheDiagnostic({ input_tokens: 1000, cached_input_tokens: 400, uncached_input_tokens: 600, cache_ratio: 0.4 }, previousWarm),
  spike: helpers.classifyCacheDiagnostic({ input_tokens: 3000, cached_input_tokens: 1200, uncached_input_tokens: 1800, cache_ratio: 0.4 }, { input_tokens: 1200, cached_input_tokens: 1100, uncached_input_tokens: 100, cache_ratio: 0.92 }),
  postCompaction: helpers.classifyCacheDiagnostic({ input_tokens: 1000, cached_input_tokens: 100, uncached_input_tokens: 900, cache_ratio: 0.1, post_compaction: true }, previousWarm),
};
console.log(JSON.stringify(cases));
"""
    )

    assert payload == {
        "warm": "warm",
        "cold": "cold",
        "partial": "partial",
        "spike": "spike",
        "postCompaction": "post_compaction",
    }


def test_adjacent_thread_calls_are_chronological_and_scoped_to_resolved_thread() -> None:
    payload = _run_dashboard_data_script(
        """
const rows = [
  { record_id: 'other', thread_name: 'Other', event_timestamp: '2026-06-01T00:00:00Z', cumulative_total_tokens: 1 },
  { record_id: 'middle', thread_name: 'Thread A', event_timestamp: '2026-06-01T00:02:00Z', cumulative_total_tokens: 30 },
  { record_id: 'first', thread_name: 'Thread A', event_timestamp: '2026-06-01T00:01:00Z', cumulative_total_tokens: 10 },
  { record_id: 'last', thread_name: 'Thread A', event_timestamp: '2026-06-01T00:02:00Z', cumulative_total_tokens: 50 },
];
const selected = rows.find(row => row.record_id === 'middle');
const index = helpers.buildCallAdjacencyIndex(rows);
const adjacent = helpers.adjacentThreadCalls(rows, selected, index);
console.log(JSON.stringify({
  order: adjacent.calls.map(row => row.record_id),
  index: adjacent.index,
  previous: adjacent.previous.record_id,
  next: adjacent.next.record_id,
}));
"""
    )

    assert payload == {
        "order": ["first", "middle", "last"],
        "index": 1,
        "previous": "first",
        "next": "last",
    }


def test_call_adjacency_index_prefers_persisted_neighbors_when_loaded() -> None:
    payload = _run_dashboard_data_script(
        """
const rows = [
  { record_id: 'old-loaded', thread_name: 'Thread A', event_timestamp: '2026-06-01T00:00:00Z', cumulative_total_tokens: 1 },
  { record_id: 'middle', thread_name: 'Thread A', event_timestamp: '2026-06-01T00:02:00Z', cumulative_total_tokens: 30, previous_record_id: 'persisted-prev', next_record_id: 'persisted-next' },
  { record_id: 'persisted-next', thread_name: 'Thread A', event_timestamp: '2026-06-01T00:03:00Z', cumulative_total_tokens: 40 },
  { record_id: 'persisted-prev', thread_name: 'Thread A', event_timestamp: '2026-06-01T00:04:00Z', cumulative_total_tokens: 50 },
];
const index = helpers.buildCallAdjacencyIndex(rows);
const adjacent = index.get('middle');
console.log(JSON.stringify({
  order: adjacent.calls.map(row => row.record_id),
  previous: adjacent.previous.record_id,
  next: adjacent.next.record_id,
}));
"""
    )

    assert payload == {
        "order": ["old-loaded", "middle", "persisted-next", "persisted-prev"],
        "previous": "persisted-prev",
        "next": "persisted-next",
    }


def test_call_adjacency_index_does_not_guess_when_persisted_neighbor_is_unloaded() -> None:
    payload = _run_dashboard_data_script(
        """
const rows = [
  { record_id: 'old-loaded', thread_name: 'Thread A', event_timestamp: '2026-06-01T00:00:00Z', cumulative_total_tokens: 1 },
  { record_id: 'middle', thread_name: 'Thread A', event_timestamp: '2026-06-01T00:02:00Z', cumulative_total_tokens: 30, previous_record_id: 'not-loaded' },
  { record_id: 'next-loaded', thread_name: 'Thread A', event_timestamp: '2026-06-01T00:03:00Z', cumulative_total_tokens: 40 },
];
const adjacent = helpers.buildCallAdjacencyIndex(rows).get('middle');
console.log(JSON.stringify({
  previous: adjacent.previous,
  next: adjacent.next.record_id,
}));
"""
    )

    assert payload == {
        "previous": None,
        "next": "next-loaded",
    }


def test_call_accounting_delta_uses_token_counter_fields() -> None:
    payload = _run_dashboard_data_script(
        """
const previous = {
  input_tokens: 1000,
  cached_input_tokens: 800,
  uncached_input_tokens: 200,
  output_tokens: 50,
  reasoning_output_tokens: 10,
  cache_ratio: 0.8,
};
const row = {
  input_tokens: 1300,
  cached_input_tokens: 600,
  uncached_input_tokens: 700,
  output_tokens: 90,
  reasoning_output_tokens: 25,
  cache_ratio: 0.4615,
};
console.log(JSON.stringify(helpers.callAccountingDelta(row, previous)));
"""
    )

    assert payload == {
        "input": 300,
        "cached": -200,
        "uncached": 500,
        "output": 40,
        "reasoning": 15,
        "cacheRatio": pytest.approx(-0.3385),
    }
