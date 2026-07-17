"""End-to-end aggregate API slice coverage for the dashboard server."""

from __future__ import annotations

import json
import threading
import urllib.parse
from datetime import datetime
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

from codex_usage_tracker.recommendation_engine.api import refresh_usage_index
from tests.store_dashboard_helpers import (
    _assert_contract,
    _http_error_json,
    _make_codex_home,
    _read_json,
    _write_pricing,
)

JsonObject = dict[str, Any]


def _as_json_object(payload: dict[str, object]) -> JsonObject:
    return cast(JsonObject, payload)


def test_dashboard_server_live_sql_api_slices_are_aggregate_only(tmp_path: Path) -> None:
    from codex_usage_tracker.server.api import _UsageDashboardHandler
    from codex_usage_tracker.server.query_cache import AggregateQueryCache

    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    refresh_usage_index(codex_home=codex_home, db_path=db_path, pricing_path=pricing_path)
    handler = partial(
        _UsageDashboardHandler,
        directory=str(tmp_path),
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=tmp_path / "allowance.json",
        thresholds_path=tmp_path / "thresholds.json",
        projects_path=tmp_path / "projects.json",
        limit=5000,
        since=None,
        codex_home=codex_home,
        include_archived=False,
        dashboard_name="dashboard.html",
        context_chars=2000,
        api_token="test-token",
        context_api_enabled=True,
        refresh_lock=threading.Lock(),
        query_cache=AggregateQueryCache(),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"

        health_payload = _as_json_object(_read_json(f"{base_url}/api/health"))
        assert health_payload == {
            "schema": "codex-usage-tracker-health-v1",
            "status": "ok",
        }

        status_payload = _as_json_object(_read_json(f"{base_url}/api/status"))
        calls_payload = _as_json_object(
            _read_json(f"{base_url}/api/calls?limit=2&sort=tokens&direction=desc&q=Codex")
        )
        offset_payload = _as_json_object(
            _read_json(f"{base_url}/api/calls?limit=1&offset=1&sort=tokens&direction=desc&q=Codex")
        )
        record_id = calls_payload["rows"][0]["record_id"]
        call_payload = _as_json_object(_read_json(f"{base_url}/api/call?record_id={record_id}"))
        threads_payload = _as_json_object(_read_json(f"{base_url}/api/threads?limit=2&sort=tokens"))
        thread_key = threads_payload["rows"][0]["thread_key"]
        thread_calls_payload = _as_json_object(
            _read_json(
                f"{base_url}/api/thread-calls?thread_key={urllib.parse.quote(thread_key)}&limit=2"
            )
        )
        summary_payload = _as_json_object(
            _read_json(f"{base_url}/api/summary?group_by=model&limit=5")
        )
        cached_summary_payload = _as_json_object(
            _read_json(f"{base_url}/api/summary?limit=5&group_by=model")
        )
        recommendations_payload = _as_json_object(
            _read_json(f"{base_url}/api/recommendations?limit=5")
        )
        cached_recommendations_payload = _as_json_object(
            _read_json(f"{base_url}/api/recommendations?limit=5")
        )
        reports_pack_payload = _as_json_object(
            _read_json(f"{base_url}/api/reports/pack?limit=5&evidence_limit=2")
        )
        diagnostics_summary_payload = _as_json_object(
            _read_json(f"{base_url}/api/diagnostics/summary?limit=5")
        )
        diagnostics_facts_payload = _as_json_object(
            _read_json(f"{base_url}/api/diagnostics/facts?limit=5")
        )
        diagnostics_sorted_facts_payload = _as_json_object(
            _read_json(f"{base_url}/api/diagnostics/facts?limit=5&sort=cached&direction=desc")
        )
        diagnostics_compactions_payload = _as_json_object(
            _read_json(f"{base_url}/api/diagnostics/compactions?limit=5")
        )
        diagnostics_tools_payload = _as_json_object(
            _read_json(f"{base_url}/api/diagnostics/tools?limit=5")
        )
        diagnostics_fact_calls_payload = _as_json_object(
            _read_json(
                f"{base_url}/api/diagnostics/fact-calls"
                "?fact_type=compaction&fact_name=post_compaction&limit=5"
            )
        )
        invalid_diagnostics = _http_error_json(f"{base_url}/api/diagnostics/facts?sort=bad")
        missing_fact_calls = _http_error_json(f"{base_url}/api/diagnostics/fact-calls")
        invalid_sort = _as_json_object(_http_error_json(f"{base_url}/api/calls?sort=not-a-sort"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status_payload["schema"] == "codex-usage-tracker-status-v1"
    _assert_contract(status_payload)
    assert "rows" not in status_payload
    assert status_payload["row_counts"]["scoped_rows"] == 4
    assert status_payload["max_event_timestamp"]
    assert status_payload["observed_usage"]["available"] is True
    assert status_payload["observed_usage"]["windows"][0]["label"] == "5h"
    assert status_payload["observed_usage"]["windows"][1]["label"] == "Weekly"

    assert calls_payload["schema"] == "codex-usage-tracker-calls-v1"
    _assert_contract(calls_payload)
    assert calls_payload["row_count"] == 2
    assert calls_payload["total_matched_rows"] >= 2
    assert calls_payload["has_more"] is True
    assert calls_payload["next_offset"] == 2
    assert calls_payload["rows"][0]["total_tokens"] >= calls_payload["rows"][1]["total_tokens"]
    assert offset_payload["rows"][0]["record_id"] != calls_payload["rows"][0]["record_id"]

    assert call_payload["schema"] == "codex-usage-tracker-call-v1"
    _assert_contract(call_payload)
    assert call_payload["record"]["record_id"] == record_id
    assert call_payload["raw_context_included"] is False

    assert threads_payload["schema"] == "codex-usage-tracker-threads-v1"
    _assert_contract(threads_payload)
    assert threads_payload["row_count"] >= 1
    assert "total_tokens" in threads_payload["rows"][0]

    assert thread_calls_payload["schema"] == "codex-usage-tracker-thread-calls-v1"
    _assert_contract(thread_calls_payload)
    assert thread_calls_payload["thread_key"] == thread_key
    assert thread_calls_payload["row_count"] >= 1

    assert summary_payload["schema"] == "codex-usage-tracker-summary-v1"
    _assert_contract(summary_payload)
    assert summary_payload["group_by"] == "model"
    assert summary_payload["query_cache"]["status"] == "miss"
    assert cached_summary_payload["query_cache"]["status"] == "hit"
    assert recommendations_payload["schema"] == "codex-usage-tracker-recommendations-v1"
    _assert_contract(recommendations_payload)
    assert recommendations_payload["query_cache"]["status"] == "miss"
    assert cached_recommendations_payload["query_cache"]["status"] == "hit"
    assert reports_pack_payload["schema"] == "codex-usage-tracker-reports-pack-v1"
    assert datetime.fromisoformat(reports_pack_payload["generated_at"]).tzinfo is not None
    _assert_contract(reports_pack_payload)
    report_titles = {report["title"] for report in reports_pack_payload["reports"]}
    assert report_titles >= {"Cost Curves", "Usage Drain Model"}
    assert reports_pack_payload["evidence"]["cost-curves"]["row_count"] <= 2
    if "Fast Mode Proxy" in report_titles:
        assert reports_pack_payload["evidence"]["fast-mode-proxy"]["row_count"] <= 2
    assert reports_pack_payload["raw_context_included"] is False
    assert diagnostics_summary_payload["schema"] == "codex-usage-tracker-diagnostics-v1"
    _assert_contract(diagnostics_summary_payload)
    assert diagnostics_summary_payload["view"] == "summary"
    assert diagnostics_summary_payload["raw_context_included"] is False
    assert diagnostics_facts_payload["schema"] == "codex-usage-tracker-diagnostics-v1"
    _assert_contract(diagnostics_facts_payload)
    assert diagnostics_facts_payload["view"] == "facts"
    assert {row["fact_name"] for row in diagnostics_facts_payload["rows"]} >= {"post_compaction"}
    assert diagnostics_sorted_facts_payload["filters"]["sort"] == "cached"
    assert diagnostics_sorted_facts_payload["filters"]["direction"] == "desc"
    _assert_contract(diagnostics_sorted_facts_payload)
    assert diagnostics_compactions_payload["filters"]["fact_type"] == "compaction"
    _assert_contract(diagnostics_compactions_payload)
    assert {row["fact_type"] for row in diagnostics_compactions_payload["rows"]} == {"compaction"}
    assert diagnostics_tools_payload["filters"]["fact_type"] is None
    assert diagnostics_tools_payload["filters"]["fact_group"] == "tools"
    _assert_contract(diagnostics_tools_payload)
    assert diagnostics_fact_calls_payload["view"] == "fact-calls"
    _assert_contract(diagnostics_fact_calls_payload)
    assert diagnostics_fact_calls_payload["filters"]["fact_name"] == "post_compaction"
    assert diagnostics_fact_calls_payload["rows"][0]["fact_name"] == "post_compaction"
    assert invalid_diagnostics["status"] == 400
    assert missing_fact_calls["status"] == 400
    assert invalid_sort["status"] == 400
    assert "sort must be one of" in invalid_sort["payload"]["error"]

    combined_payload = json.dumps(
        [
            status_payload,
            calls_payload,
            call_payload,
            threads_payload,
            thread_calls_payload,
            summary_payload,
            recommendations_payload,
            reports_pack_payload,
            diagnostics_summary_payload,
            diagnostics_facts_payload,
            diagnostics_compactions_payload,
            diagnostics_tools_payload,
            diagnostics_fact_calls_payload,
        ]
    )
    assert "SECRET RAW PROMPT" not in combined_payload
    assert 'raw_context_included": true' not in combined_payload
