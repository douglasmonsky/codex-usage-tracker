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
