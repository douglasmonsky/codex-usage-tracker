from __future__ import annotations

import json
import sqlite3
import threading
import urllib.error
import urllib.parse
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from store_dashboard_helpers import (
    SESSION_ID,
    _assert_contract,
    _http_error_json,
    _make_codex_home,
    _read_json,
    _token_event,
    _usage_event,
    _write_archived_log,
    _write_pricing,
)

from codex_usage_tracker.dashboard import dashboard_payload, generate_dashboard
from codex_usage_tracker.store import (
    connect,
    query_dashboard_events,
    query_session_usage,
    refresh_usage_index,
    upsert_usage_events,
)
from codex_usage_tracker.usage_impact_cache import UsageImpactCache


def test_dashboard_server_usage_api_refreshes_aggregate_rows(tmp_path: Path) -> None:
    from codex_usage_tracker.server import _UsageDashboardHandler

    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    (tmp_path / "dashboard.html").write_text("<!doctype html><title>Dashboard</title>", encoding="utf-8")
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
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            f"http://127.0.0.1:{server.server_port}/dashboard.html",
            timeout=5,
        ) as response:
            dashboard_cache_control = response.headers.get("Cache-Control")
            dashboard_html = response.read().decode("utf-8")
        refresh_without_token = _http_error_json(
            f"http://127.0.0.1:{server.server_port}/api/usage?refresh=1&limit=2"
        )
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/usage?refresh=1&limit=2",
                headers={"X-Codex-Usage-Token": "test-token"},
            ),
            timeout=5,
        ) as response:
            content_security_policy = response.headers.get("Content-Security-Policy")
            referrer_policy = response.headers.get("Referrer-Policy")
            limited_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            f"http://127.0.0.1:{server.server_port}/api/usage?limit=all",
            timeout=5,
        ) as response:
            all_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            f"http://127.0.0.1:{server.server_port}/api/usage?limit=2&offset=2",
            timeout=5,
        ) as response:
            offset_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            f"http://127.0.0.1:{server.server_port}/api/usage?shell=1&limit=all",
            timeout=5,
        ) as response:
            shell_payload = json.loads(response.read().decode("utf-8"))
        forbidden_origin = _http_error_json(
            f"http://127.0.0.1:{server.server_port}/api/usage",
            headers={"Origin": "http://example.test"},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert refresh_without_token["status"] == 403
    assert dashboard_cache_control == "no-store"
    shell_raw_payload = dashboard_html.split(
        '<script id="usage-data" type="application/json">',
        1,
    )[1].split("</script>", 1)[0]
    dashboard_shell_payload = json.loads(shell_raw_payload)
    assert 'data-dashboard-shell="true"' in dashboard_html
    assert dashboard_shell_payload["shell_boot"] is True
    assert dashboard_shell_payload["rows"] == []
    assert dashboard_shell_payload["summary"]["visible_calls"] == 0
    assert limited_payload["refresh_result"]["parsed_events"] == 4
    assert limited_payload["refresh_result"]["skipped_events"] == 0
    assert limited_payload["refresh_result"]["changed_source_files"] >= 1
    assert limited_payload["refresh_result"]["inserted_records"] == 4
    assert limited_payload["refresh_result"]["skipped_downstream_work"] is False
    assert limited_payload["refresh_result"]["parser_diagnostics"] == {}
    assert len(limited_payload["rows"]) == 2
    assert limited_payload["loaded_row_count"] == 2
    assert limited_payload["total_available_rows"] == 4
    assert limited_payload["limit"] == 2
    assert limited_payload["offset"] == 0
    assert limited_payload["has_more"] is True
    assert limited_payload["next_offset"] == 2
    assert content_security_policy is not None
    assert "connect-src 'self'" in content_security_policy
    assert "unsafe-inline" not in content_security_policy
    assert referrer_policy == "no-referrer"
    assert len(all_payload["rows"]) == 4
    assert all_payload["loaded_row_count"] == 4
    assert all_payload["total_available_rows"] == 4
    assert all_payload["limit"] is None
    assert all_payload["offset"] == 0
    assert all_payload["has_more"] is False
    assert all_payload["limit_label"] == "All"
    assert len(offset_payload["rows"]) == 2
    assert shell_payload["shell_boot"] is True
    assert shell_payload["rows"] == []
    assert shell_payload["summary"]["visible_calls"] == 4
    assert shell_payload["summary"]["total_tokens"] == sum(
        row["total_tokens"] for row in all_payload["rows"]
    )
    assert shell_payload["limit"] is None
    assert shell_payload["loaded_row_count"] == 0
    assert offset_payload["loaded_row_count"] == 2
    assert offset_payload["total_available_rows"] == 4
    assert offset_payload["limit"] == 2
    assert offset_payload["offset"] == 2
    assert offset_payload["has_more"] is False
    assert offset_payload["next_offset"] is None
    assert {row["record_id"] for row in offset_payload["rows"]}.isdisjoint(
        {row["record_id"] for row in limited_payload["rows"]}
    )
    assert limited_payload["pricing_configured"] is True
    assert limited_payload["allowance_configured"] is False
    assert limited_payload["allowance_source"]["name"] == "OpenAI Codex rate card"
    assert limited_payload["rows"][0]["usage_credits"] is not None
    assert "refreshed_at" in limited_payload
    assert limited_payload["parser_diagnostics"] == {}
    assert limited_payload["api_token"] == "test-token"
    assert limited_payload["context_api_enabled"] is True
    assert forbidden_origin["status"] == 403
    assert "SECRET RAW PROMPT" not in json.dumps(limited_payload)


def test_dashboard_status_live_refresh_parses_appended_events_incrementally(tmp_path: Path) -> None:
    from codex_usage_tracker.server import _UsageDashboardHandler

    class FakeUsageImpactCache:
        def __init__(self) -> None:
            self.invalidations = 0
            self.warms = 0

        def invalidate(self) -> None:
            self.invalidations += 1

        def warm_async(self, *, include_archived: bool) -> None:
            _ = include_archived
            self.warms += 1

    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    usage_impact_cache = FakeUsageImpactCache()
    log_path = next(
        path for path in (codex_home / "sessions").glob("**/*.jsonl") if SESSION_ID in path.name
    )
    first_refresh = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_token_event(650, 350)) + "\n")
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
        usage_impact_cache=usage_impact_cache,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        forbidden = _http_error_json(
            f"http://127.0.0.1:{server.server_port}/api/status?refresh=1"
        )
        live_payload = _read_json(
            f"http://127.0.0.1:{server.server_port}/api/status?refresh=1",
            headers={"X-Codex-Usage-Token": "test-token"},
        )
        second_payload = _read_json(
            f"http://127.0.0.1:{server.server_port}/api/status?refresh=1",
            headers={"X-Codex-Usage-Token": "test-token"},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert first_refresh.parsed_events == 4
    assert forbidden["status"] == 403
    assert live_payload["refresh_result"]["parsed_events"] == 1
    assert live_payload["refresh_result"]["inserted_or_updated_events"] == 1
    assert live_payload["refresh_result"]["changed_source_files"] == 1
    assert live_payload["refresh_result"]["append_source_files"] == 1
    assert live_payload["refresh_result"]["full_reparse_source_files"] == 0
    assert live_payload["refresh_result"]["inserted_records"] == 1
    assert live_payload["refresh_result"]["deleted_records"] == 0
    assert live_payload["refresh_result"]["affected_threads"] == 1
    assert live_payload["refresh_result"]["skipped_downstream_work"] is False
    assert live_payload["row_counts"]["scoped_rows"] == 5
    assert second_payload["refresh_result"]["parsed_events"] == 0
    assert second_payload["refresh_result"]["inserted_or_updated_events"] == 0
    assert second_payload["refresh_result"]["changed_source_files"] == 0
    assert second_payload["refresh_result"]["inserted_records"] == 0
    assert second_payload["refresh_result"]["affected_threads"] == 0
    assert second_payload["refresh_result"]["skipped_downstream_work"] is True
    assert usage_impact_cache.invalidations == 1
    assert usage_impact_cache.warms == 1


def test_dashboard_server_exposes_usage_impact_read_model(tmp_path: Path) -> None:
    from codex_usage_tracker.server import _UsageDashboardHandler

    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    events = []
    for index in range(5):
        events.append(
            _usage_event(
                record_id=f"baseline-{index}",
                session_id=SESSION_ID,
                thread_key="thread:Usage impact API",
                event_timestamp=f"2026-06-15T12:{index * 2:02d}:00Z",
                cumulative_total_tokens=100 + index * 100,
                rate_limit_primary_used_percent=10 + index,
                rate_limit_primary_window_minutes=300,
                rate_limit_primary_resets_at=1781562696,
            )
        )
        events.append(
            _usage_event(
                record_id=f"observed-{index}",
                session_id=SESSION_ID,
                thread_key="thread:Usage impact API",
                event_timestamp=f"2026-06-15T12:{index * 2 + 1:02d}:00Z",
                cumulative_total_tokens=150 + index * 100,
                rate_limit_primary_used_percent=11 + index,
                rate_limit_primary_window_minutes=300,
                rate_limit_primary_resets_at=1781562696,
            )
        )
    events.append(
        _usage_event(
            record_id="target-impact",
            session_id=SESSION_ID,
            thread_key="thread:Usage impact API",
            event_timestamp="2026-06-15T12:15:00Z",
            cumulative_total_tokens=1000,
        )
    )
    upsert_usage_events(events, db_path=db_path)
    UsageImpactCache(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
    ).rebuild(include_archived=False)
    (tmp_path / "dashboard.html").write_text("<!doctype html><title>Dashboard</title>", encoding="utf-8")
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
        codex_home=tmp_path / ".codex",
        include_archived=False,
        dashboard_name="dashboard.html",
        context_chars=2000,
        api_token="test-token",
        context_api_enabled=True,
        refresh_lock=threading.Lock(),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        impact_payload = _read_json(
            f"http://127.0.0.1:{server.server_port}/api/usage-impact?record_id=target-impact"
        )
        call_payload = _read_json(
            f"http://127.0.0.1:{server.server_port}/api/call?record_id=target-impact"
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert impact_payload["schema"] == "codex-usage-tracker-usage-impact-v1"
    assert impact_payload["record_id"] == "target-impact"
    assert impact_payload["row_count"] == 2
    assert impact_payload["raw_context_included"] is False
    assert any(row["status"] == "fresh" for row in impact_payload["rows"])
    assert "usage_impact" in call_payload
    assert call_payload["usage_impact"]["schema"] == "codex-usage-tracker-usage-impact-v1"
    assert "SECRET RAW PROMPT" not in json.dumps(impact_payload)


def test_dashboard_history_scope_excludes_archived_rows_by_default(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    _write_archived_log(codex_home)
    db_path = tmp_path / "usage.sqlite3"
    refresh_result = refresh_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        include_archived=True,
    )

    active_payload = dashboard_payload(db_path=db_path, limit=0)
    all_history_payload = dashboard_payload(db_path=db_path, limit=0, include_archived=True)
    active_rows = query_dashboard_events(db_path=db_path, limit=0, include_archived=False)
    all_rows = query_dashboard_events(db_path=db_path, limit=0, include_archived=True)
    archived_rows = [row for row in all_rows if "/archived_sessions/" in row["source_file"]]

    assert refresh_result.parsed_events == 5
    assert active_payload["include_archived"] is False
    assert active_payload["history_scope"] == "active"
    assert active_payload["loaded_row_count"] == 4
    assert active_payload["total_available_rows"] == 4
    assert active_payload["active_available_rows"] == 4
    assert active_payload["all_history_available_rows"] == 5
    assert active_payload["archived_available_rows"] == 1
    assert all_history_payload["include_archived"] is True
    assert all_history_payload["history_scope"] == "all-history"
    assert all_history_payload["loaded_row_count"] == 5
    assert all_history_payload["total_available_rows"] == 5
    assert len(active_rows) == 4
    assert len(all_rows) == 5
    assert not any("/archived_sessions/" in row["source_file"] for row in active_rows)
    assert len(archived_rows) == 1
    assert archived_rows[0]["is_archived"] == 1
    assert all(row["is_archived"] == 0 for row in active_rows)

    with connect(db_path) as conn:
        conn.execute("UPDATE usage_events SET is_archived = 0")
    active_rows_after_migrated_flag_reset = query_dashboard_events(
        db_path=db_path,
        limit=0,
        include_archived=False,
    )
    assert len(active_rows_after_migrated_flag_reset) == 4
    assert not any(
        "/archived_sessions/" in row["source_file"]
        for row in active_rows_after_migrated_flag_reset
    )


def test_dashboard_server_usage_api_switches_history_scope(tmp_path: Path) -> None:
    from codex_usage_tracker.server import _UsageDashboardHandler

    codex_home = _make_codex_home(tmp_path)
    _write_archived_log(codex_home)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
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
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/usage?refresh=1&limit=all",
                headers={"X-Codex-Usage-Token": "test-token"},
            ),
            timeout=5,
        ) as response:
            active_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/usage?refresh=1&limit=all&include_archived=1",
                headers={"X-Codex-Usage-Token": "test-token"},
            ),
            timeout=5,
        ) as response:
            all_history_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            f"http://127.0.0.1:{server.server_port}/api/usage?limit=all&include_archived=0",
            timeout=5,
        ) as response:
            active_after_all_payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert active_payload["include_archived"] is False
    assert active_payload["loaded_row_count"] == 4
    assert active_payload["archived_available_rows"] == 0
    assert active_payload["refresh_result"]["include_archived"] is False
    assert all_history_payload["include_archived"] is True
    assert all_history_payload["loaded_row_count"] == 5
    assert all_history_payload["archived_available_rows"] == 1
    assert all_history_payload["refresh_result"]["include_archived"] is True
    assert active_after_all_payload["include_archived"] is False
    assert active_after_all_payload["loaded_row_count"] == 4
    assert active_after_all_payload["archived_available_rows"] == 1
    assert not any(
        "/archived_sessions/" in row["source_file"]
        for row in active_after_all_payload["rows"]
    )


def test_dashboard_server_api_timing_diagnostics_are_opt_in_and_technical(
    tmp_path: Path,
) -> None:
    from codex_usage_tracker.server import _UsageDashboardHandler

    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
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
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            urllib.request.Request(
                f"{base_url}/api/usage?refresh=1&limit=2&diagnostics=true",
                headers={"X-Codex-Usage-Token": "test-token"},
            ),
            timeout=5,
        ) as response:
            usage_diagnostics_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            f"{base_url}/api/usage?limit=2",
            timeout=5,
        ) as response:
            usage_default_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            f"{base_url}/api/usage?limit=2&diagnostics=false",
            timeout=5,
        ) as response:
            usage_false_payload = json.loads(response.read().decode("utf-8"))

        record_id = usage_diagnostics_payload["rows"][0]["record_id"]
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            urllib.request.Request(
                f"{base_url}/api/context?record_id={record_id}&diagnostics=true",
                headers={"X-Codex-Usage-Token": "test-token"},
            ),
            timeout=5,
        ) as response:
            context_diagnostics_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            urllib.request.Request(
                f"{base_url}/api/context?record_id={record_id}",
                headers={"X-Codex-Usage-Token": "test-token"},
            ),
            timeout=5,
        ) as response:
            context_default_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            urllib.request.Request(
                f"{base_url}/api/context?record_id={record_id}&diagnostics=false",
                headers={"X-Codex-Usage-Token": "test-token"},
            ),
            timeout=5,
        ) as response:
            context_false_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            urllib.request.Request(
                f"{base_url}/api/context?record_id={record_id}&mode=full",
                headers={"X-Codex-Usage-Token": "test-token"},
            ),
            timeout=5,
        ) as response:
            context_full_payload = json.loads(response.read().decode("utf-8"))
        invalid_context_mode = _http_error_json(
            f"{base_url}/api/context?record_id={record_id}&mode=slow",
            headers={"X-Codex-Usage-Token": "test-token"},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert "diagnostics" not in usage_default_payload
    assert "diagnostics" not in usage_false_payload
    usage_diagnostics = usage_diagnostics_payload["diagnostics"]
    assert usage_diagnostics["refresh_ms"] >= 0
    assert usage_diagnostics["dashboard_payload_ms"] >= 0
    assert usage_diagnostics["json_bytes"] > 0
    assert usage_diagnostics["rows_returned"] == 2
    assert usage_diagnostics["include_archived"] is False
    assert usage_diagnostics["limit"] == 2
    assert usage_diagnostics["offset"] == 0
    usage_diagnostics_text = json.dumps(usage_diagnostics)
    assert "SECRET RAW PROMPT" not in usage_diagnostics_text
    assert "source_file" not in usage_diagnostics_text

    assert "diagnostics" not in context_default_payload
    assert "diagnostics" not in context_false_payload
    assert context_default_payload["context_mode"] == "quick"
    assert context_default_payload["serialized_evidence"]["deferred_buckets"] is True
    assert context_full_payload["context_mode"] == "full"
    assert context_full_payload["serialized_evidence"]["deferred_buckets"] is False
    assert invalid_context_mode["status"] == 400
    context_diagnostics = context_diagnostics_payload["diagnostics"]
    assert context_diagnostics["db_lookup_ms"] >= 0
    assert context_diagnostics["source_scan_ms"] >= 0
    assert context_diagnostics["serialized_estimate_ms"] >= 0
    assert context_diagnostics["source_file_bytes"] > 0
    assert context_diagnostics["source_line_number"] > 0
    assert context_diagnostics["entries_before_limit"] >= context_diagnostics["entries_returned"]
    assert context_diagnostics["json_bytes"] > 0
    context_diagnostics_text = json.dumps(context_diagnostics)
    assert "SECRET RAW PROMPT" not in context_diagnostics_text
    assert str(codex_home) not in context_diagnostics_text
    assert ".jsonl" not in context_diagnostics_text


def test_dashboard_server_live_sql_api_slices_are_aggregate_only(tmp_path: Path) -> None:
    from codex_usage_tracker.server import _UsageDashboardHandler

    class FakeUsageImpactCache:
        def __init__(self) -> None:
            self.copy_calls: list[dict[str, object]] = []

        def copy_usage_impact(
            self,
            rows: list[dict[str, object]],
            *,
            include_archived: bool,
            block: bool = True,
            schedule_warm: bool = True,
        ) -> list[dict[str, object]]:
            self.copy_calls.append(
                {
                    "row_count": len(rows),
                    "include_archived": include_archived,
                    "block": block,
                    "schedule_warm": schedule_warm,
                }
            )
            return [dict(row) for row in rows]

    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    usage_impact_cache = FakeUsageImpactCache()
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
        usage_impact_cache=usage_impact_cache,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"

        status_payload = _read_json(f"{base_url}/api/status")
        calls_payload = _read_json(
            f"{base_url}/api/calls?limit=2&sort=tokens&direction=desc&q=Codex"
        )
        offset_payload = _read_json(
            f"{base_url}/api/calls?limit=1&offset=1&sort=tokens&direction=desc&q=Codex"
        )
        record_id = calls_payload["rows"][0]["record_id"]
        call_payload = _read_json(f"{base_url}/api/call?record_id={record_id}")
        threads_payload = _read_json(f"{base_url}/api/threads?limit=2&sort=tokens")
        thread_key = threads_payload["rows"][0]["thread_key"]
        thread_calls_payload = _read_json(
            f"{base_url}/api/thread-calls?thread_key={urllib.parse.quote(thread_key)}&limit=2"
        )
        summary_payload = _read_json(f"{base_url}/api/summary?group_by=model&limit=5")
        recommendations_payload = _read_json(f"{base_url}/api/recommendations?limit=5")
        invalid_sort = _http_error_json(f"{base_url}/api/calls?sort=not-a-sort")
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
    assert usage_impact_cache.copy_calls
    assert all(call["block"] is False for call in usage_impact_cache.copy_calls)
    assert all(call["schedule_warm"] is False for call in usage_impact_cache.copy_calls)

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
    assert recommendations_payload["schema"] == "codex-usage-tracker-recommendations-v1"
    _assert_contract(recommendations_payload)
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
        ]
    )
    assert "SECRET RAW PROMPT" not in combined_payload
    assert "raw_context_included\": true" not in combined_payload


def test_dashboard_server_serves_lightweight_call_investigator_boot_html(
    tmp_path: Path,
) -> None:
    from codex_usage_tracker.server import _UsageDashboardHandler

    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    dashboard_path = tmp_path / "dashboard.html"
    generate_dashboard(
        db_path=db_path,
        output_path=dashboard_path,
        pricing_path=pricing_path,
        api_token="test-token",
        context_api_enabled=True,
        include_archived=True,
    )
    record_id = query_dashboard_events(db_path=db_path, include_archived=True)[0]["record_id"]
    static_html = dashboard_path.read_text(encoding="utf-8")
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
        dashboard_path=dashboard_path,
        context_chars=2000,
        api_token="test-token",
        context_api_enabled=True,
        refresh_lock=threading.Lock(),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = (
            f"http://127.0.0.1:{server.server_port}/dashboard.html"
            f"?view=call&record={urllib.parse.quote(record_id)}&history=all"
        )
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - local test server only
            html = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    raw_payload = html.split('<script id="usage-data" type="application/json">', 1)[1].split(
        "</script>",
        1,
    )[0]
    payload = json.loads(raw_payload)
    assert 'data-active-view="call"' in html
    assert 'data-investigator-boot="true"' in html
    assert 'data-dashboard-shell="true"' in html
    assert payload["investigator_boot"] is True
    assert payload["rows"] == []
    assert payload["include_archived"] is True
    assert payload["api_token"] == "test-token"
    assert len(html) < len(static_html)


def test_dashboard_call_api_returns_adjacent_records_for_investigator(
    tmp_path: Path,
) -> None:
    from codex_usage_tracker.server import _UsageDashboardHandler

    db_path = tmp_path / "usage.sqlite3"
    events = [
        _usage_event(
            record_id="a1",
            session_id="session-a",
            thread_key="thread:Alpha",
            event_timestamp="2026-05-17T18:58:20Z",
            cumulative_total_tokens=100,
        ),
        _usage_event(
            record_id="a2",
            session_id="session-a",
            thread_key="thread:Alpha",
            event_timestamp="2026-05-17T18:58:30Z",
            cumulative_total_tokens=250,
        ),
        _usage_event(
            record_id="a3",
            session_id="session-a",
            thread_key="thread:Alpha",
            event_timestamp="2026-05-17T18:58:40Z",
            cumulative_total_tokens=400,
        ),
    ]
    upsert_usage_events(events, db_path=db_path)
    handler = partial(
        _UsageDashboardHandler,
        directory=str(tmp_path),
        db_path=db_path,
        pricing_path=_write_pricing(tmp_path / "pricing.json"),
        allowance_path=tmp_path / "allowance.json",
        thresholds_path=tmp_path / "thresholds.json",
        projects_path=tmp_path / "projects.json",
        limit=5000,
        since=None,
        codex_home=tmp_path / ".codex",
        include_archived=False,
        dashboard_name="dashboard.html",
        context_chars=2000,
        api_token="test-token",
        context_api_enabled=True,
        refresh_lock=threading.Lock(),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = _read_json(
            f"http://127.0.0.1:{server.server_port}/api/call?record_id=a2",
            headers={"X-Codex-Usage-Token": "test-token"},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert payload["schema"] == "codex-usage-tracker-call-v1"
    assert payload["record"]["record_id"] == "a2"
    assert payload["previous_record"]["record_id"] == "a1"
    assert payload["next_record"]["record_id"] == "a3"
    assert [row["record_id"] for row in payload["adjacent_records"]] == ["a1", "a2", "a3"]
    assert payload["raw_context_included"] is False


def test_dashboard_server_opens_only_token_protected_investigator_urls(
    tmp_path: Path, monkeypatch
) -> None:
    from codex_usage_tracker import server as server_module
    from codex_usage_tracker.server import _UsageDashboardHandler

    opened_urls: list[str] = []
    monkeypatch.setattr(server_module.webbrowser, "open_new_tab", lambda url: opened_urls.append(url) or True)
    (tmp_path / "dashboard.html").write_text("<!doctype html><title>Dashboard</title>", encoding="utf-8")
    handler = partial(
        _UsageDashboardHandler,
        directory=str(tmp_path),
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        thresholds_path=tmp_path / "thresholds.json",
        projects_path=tmp_path / "projects.json",
        limit=5000,
        since=None,
        codex_home=_make_codex_home(tmp_path),
        include_archived=False,
        dashboard_name="dashboard.html",
        context_chars=2000,
        api_token="test-token",
        context_api_enabled=True,
        refresh_lock=threading.Lock(),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        target = f"{base_url}/dashboard.html?view=call&record=abc123&history=all"
        encoded_target = urllib.parse.quote(target, safe="")
        without_token = _http_error_json(
            f"{base_url}/api/open-investigator?url={encoded_target}"
        )
        external_url = urllib.parse.quote("https://example.test/dashboard.html?view=call&record=abc123", safe="")
        external_error = _http_error_json(
            f"{base_url}/api/open-investigator?url={external_url}",
            headers={"X-Codex-Usage-Token": "test-token"},
        )
        missing_record = urllib.parse.quote(f"{base_url}/dashboard.html?view=call", safe="")
        missing_record_error = _http_error_json(
            f"{base_url}/api/open-investigator?url={missing_record}",
            headers={"X-Codex-Usage-Token": "test-token"},
        )
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            urllib.request.Request(
                f"{base_url}/api/open-investigator?url={encoded_target}",
                headers={"X-Codex-Usage-Token": "test-token"},
            ),
            timeout=5,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert without_token["status"] == 403
    assert external_error["status"] == 400
    assert missing_record_error["status"] == 400
    assert payload["schema"] == "codex-usage-tracker-open-investigator-v1"
    assert payload["opened"] is True
    assert opened_urls == [target]


def test_dashboard_server_returns_json_for_sqlite_errors(tmp_path: Path, monkeypatch) -> None:
    from codex_usage_tracker import server as server_module
    from codex_usage_tracker.server import _UsageDashboardHandler

    def broken_dashboard_payload(**kwargs):
        raise sqlite3.OperationalError("database is locked")

    def broken_context(**kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(server_module, "dashboard_payload", broken_dashboard_payload)
    monkeypatch.setattr(server_module, "load_call_context", broken_context)
    handler = partial(
        _UsageDashboardHandler,
        directory=str(tmp_path),
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        thresholds_path=tmp_path / "thresholds.json",
        projects_path=tmp_path / "projects.json",
        limit=5000,
        since=None,
        codex_home=tmp_path / ".codex",
        include_archived=False,
        dashboard_name="dashboard.html",
        context_chars=2000,
        api_token="test-token",
        context_api_enabled=True,
        refresh_lock=threading.Lock(),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        usage_error = _http_error_json(
            f"http://127.0.0.1:{server.server_port}/api/usage"
        )
        context_error = _http_error_json(
            f"http://127.0.0.1:{server.server_port}/api/context?record_id=abc",
            headers={"X-Codex-Usage-Token": "test-token"},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert usage_error["status"] == 500
    assert "Database error" in usage_error["payload"]["error"]
    assert context_error["status"] == 500
    assert "Database error" in context_error["payload"]["error"]


def test_dashboard_server_can_enable_context_api_at_runtime(tmp_path: Path) -> None:
    from codex_usage_tracker.server import _ContextApiState, _UsageDashboardHandler

    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    record_id = query_session_usage(db_path=db_path, session_id=SESSION_ID)[0]["record_id"]
    context_api_state = _ContextApiState(False)

    handler = partial(
        _UsageDashboardHandler,
        directory=str(tmp_path),
        db_path=db_path,
        pricing_path=tmp_path / "pricing.json",
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
        context_api_state=context_api_state,
        refresh_lock=threading.Lock(),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        disabled_error = _http_error_json(
            f"http://127.0.0.1:{server.server_port}/api/context?record_id={record_id}",
            headers={"X-Codex-Usage-Token": "test-token"},
        )
        enable_without_token = _http_error_json(
            f"http://127.0.0.1:{server.server_port}/api/context-settings?enabled=1"
        )
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/context-settings?enabled=1",
                headers={"X-Codex-Usage-Token": "test-token"},
            ),
            timeout=5,
        ) as response:
            settings_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/usage?limit=1",
                headers={"X-Codex-Usage-Token": "test-token"},
            ),
            timeout=5,
        ) as response:
            usage_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/context?record_id={record_id}",
                headers={"X-Codex-Usage-Token": "test-token"},
            ),
            timeout=5,
        ) as response:
            context_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/context?record_id={record_id}&max_chars=0&max_entries=0",
                headers={"X-Codex-Usage-Token": "test-token"},
            ),
            timeout=5,
        ) as response:
            unlimited_context_payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert disabled_error["status"] == 403
    assert disabled_error["payload"]["context_api_enabled"] is False
    assert disabled_error["payload"]["can_enable_context_api"] is True
    assert enable_without_token["status"] == 403
    assert settings_payload["schema"] == "codex-usage-tracker-context-settings-v1"
    assert settings_payload["context_api_enabled"] is True
    assert settings_payload["raw_context_persisted"] is False
    assert usage_payload["context_api_enabled"] is True
    assert context_payload["loaded_on_demand"] is True
    assert context_payload["raw_context_persisted"] is False
    assert context_payload["context_mode"] == "quick"
    assert unlimited_context_payload["omitted"]["max_chars"] == 0
    assert unlimited_context_payload["omitted"]["max_entries"] == 0
    assert unlimited_context_payload["omitted"]["older_entries"] == 0
