from __future__ import annotations

import json
import sqlite3
import threading
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from codex_usage_tracker.context import load_call_context
from codex_usage_tracker.dashboard import generate_dashboard
from codex_usage_tracker.diagnostics import run_doctor
from codex_usage_tracker.pricing import (
    PricingUpdateResult,
    annotate_rows_with_efficiency,
    load_pricing_config,
)
from codex_usage_tracker.store import (
    connect,
    export_usage_csv,
    init_db,
    query_dashboard_event_count,
    query_dashboard_events,
    query_most_expensive_calls,
    query_session_usage,
    query_summary,
    refresh_usage_index,
)

SESSION_ID = "019e374d-c19f-7da3-a44f-8de043a7a64e"
SECOND_SESSION_ID = "019e37d4-c1f1-71aa-b154-2d5d837af92c"
AUTO_REVIEW_SESSION_ID = "019e37d5-01fd-71df-87f4-ae3e8d60df7a"


def test_refresh_is_idempotent_and_summary_works(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"

    first = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    second = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    session_rows = query_session_usage(db_path=db_path, session_id=SESSION_ID)
    summary = query_summary(db_path=db_path, group_by="model")
    recent_summary = query_summary(db_path=db_path, group_by="model", since="2026-05-17")
    future_summary = query_summary(db_path=db_path, group_by="model", since="2099-01-01")
    subagent_summary = query_summary(db_path=db_path, group_by="agent_role")
    thread_summary = query_summary(db_path=db_path, group_by="thread")
    expensive = query_most_expensive_calls(db_path=db_path, limit=1)
    subagent_rows = query_session_usage(db_path=db_path, session_id=SECOND_SESSION_ID)

    assert first.parsed_events == 4
    assert second.parsed_events == 4
    assert first.skipped_events == 0
    assert len(session_rows) == 2
    assert summary[0]["group_key"] == "gpt-5.5"
    assert summary[0]["total_tokens"] == 350
    assert recent_summary[0]["total_tokens"] == 350
    assert future_summary == []
    assert {row["group_key"] for row in subagent_summary} >= {"test_runner", "not agent role"}
    assert thread_summary[0]["group_key"] == "Add Codex token tracking"
    assert thread_summary[0]["total_tokens"] == 350
    assert subagent_rows[0]["parent_thread_name"] == "Add Codex token tracking"
    assert subagent_rows[0]["parent_session_updated_at"] == "2026-05-17T18:58:27Z"
    assert expensive[0]["total_tokens"] == 200
    with connect(db_path) as conn:
        init_db(conn)
        meta = {
            row["key"]: row["value"]
            for row in conn.execute("SELECT key, value FROM refresh_meta").fetchall()
        }
    assert meta["parsed_events"] == "4"
    assert meta["skipped_events"] == "0"
    assert meta["inserted_or_updated_events"] == "4"


def test_refresh_reports_skipped_corrupt_token_events(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    log_path = next((codex_home / "sessions").glob("**/*.jsonl"))
    corrupt = _token_event(600, 300)
    corrupt["payload"]["info"]["last_token_usage"]["total_tokens"] = "bad-total"  # type: ignore[index]
    valid = _token_event(650, 50)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(corrupt) + "\n")
        handle.write(json.dumps(valid) + "\n")

    result = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    rows = query_session_usage(db_path=db_path, session_id=SESSION_ID)

    assert result.skipped_events == 1
    assert result.parsed_events == 5
    assert [row["cumulative_total_tokens"] for row in rows] == [100, 300, 650]


def test_connect_sets_sqlite_concurrency_pragmas(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    with connect(db_path) as conn:
        init_db(conn)
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]

    assert busy_timeout == 5000
    assert str(journal_mode).lower() == "wal"
    assert user_version == 1


def test_init_db_repairs_version_zero_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    raw = sqlite3.connect(db_path)
    try:
        raw.execute(
            """
            CREATE TABLE usage_events (
                record_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                event_timestamp TEXT NOT NULL,
                source_file TEXT NOT NULL,
                line_number INTEGER NOT NULL,
                input_tokens INTEGER NOT NULL,
                cached_input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                reasoning_output_tokens INTEGER NOT NULL,
                total_tokens INTEGER NOT NULL,
                cumulative_input_tokens INTEGER NOT NULL,
                cumulative_cached_input_tokens INTEGER NOT NULL,
                cumulative_output_tokens INTEGER NOT NULL,
                cumulative_reasoning_output_tokens INTEGER NOT NULL,
                cumulative_total_tokens INTEGER NOT NULL,
                uncached_input_tokens INTEGER NOT NULL,
                cache_ratio REAL NOT NULL,
                reasoning_output_ratio REAL NOT NULL,
                context_window_percent REAL NOT NULL
            )
            """
        )
        raw.commit()
    finally:
        raw.close()

    with connect(db_path) as conn:
        init_db(conn)
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(usage_events)").fetchall()
        }
        indexes = {
            row["name"]
            for row in conn.execute("PRAGMA index_list(usage_events)").fetchall()
        }
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]

    assert {"thread_source", "parent_thread_name", "parent_session_updated_at"} <= columns
    assert "idx_usage_timestamp" in indexes
    assert user_version == 1


def test_dashboard_and_csv_are_aggregate_only(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    dashboard_path = tmp_path / "dashboard.html"
    csv_path = tmp_path / "usage.csv"
    all_csv_path = tmp_path / "usage-all.csv"

    generate_dashboard(db_path=db_path, output_path=dashboard_path, pricing_path=pricing_path)
    exported = export_usage_csv(output_path=csv_path, db_path=db_path)
    exported_with_zero_limit = export_usage_csv(output_path=all_csv_path, db_path=db_path, limit=0)

    dashboard = dashboard_path.read_text(encoding="utf-8")
    asset_dir = tmp_path / "codex-usage-tracker-assets"
    dashboard_js = (asset_dir / "dashboard.js").read_text(encoding="utf-8")
    dashboard_css = (asset_dir / "dashboard.css").read_text(encoding="utf-8")
    dashboard_surface = "\n".join([dashboard, dashboard_js, dashboard_css])
    csv_text = csv_path.read_text(encoding="utf-8")
    assert exported == 4
    assert exported_with_zero_limit == 4
    assert "SECRET RAW PROMPT" not in dashboard
    assert "SECRET RAW PROMPT" not in dashboard_js
    assert "SECRET RAW PROMPT" not in dashboard_css
    assert "SECRET RAW PROMPT" not in csv_text
    assert 'href="codex-usage-tracker-assets/dashboard.css?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard.js?v=' in dashboard
    assert "last call" in dashboard_js.lower()
    assert "session cumulative" in dashboard_js.lower()
    assert "Estimated Cost" in dashboard
    assert "estimated_cost_usd" in dashboard
    assert "Uncached Input" in dashboard
    assert "uncachedTokens" in dashboard
    assert "Codex Credits" in dashboard
    assert "Usage Remaining" in dashboard
    assert "Price Coverage" not in dashboard
    assert "priceCoverage" not in dashboard_surface
    assert "usageCredits" in dashboard
    assert "allowanceImpact" in dashboard
    assert "usage_credits" in dashboard
    assert "usage_credit_confidence" in dashboard
    assert "Credit rates:" in dashboard_js
    assert "Codex allowance usage" in dashboard_js
    assert "Highest Codex credits" in dashboard
    assert "Estimated Tokens" not in dashboard
    assert "Unpriced Tokens" not in dashboard
    assert "insightsView" in dashboard
    assert "callsView" in dashboard
    assert "threadsView" in dashboard
    assert "Needs Attention" in dashboard
    assert "Investigation Presets" in dashboard
    assert "presetDefinitions" in dashboard_js
    assert "renderInsightPanel" in dashboard_js
    assert "attentionScore" in dashboard_js
    assert "thread-row" in dashboard_surface
    assert "thread-call-table" in dashboard_surface
    assert "Thread attachment" in dashboard_js
    assert "Subagent type" in dashboard_js
    assert "Auto-review" in dashboard_js
    assert "Load context" in dashboard_js
    assert "parent_thread_name" in dashboard
    assert "thread_attachment_label" in dashboard
    assert "thread_attachment_relation" in dashboard
    assert "explicit parent thread" in dashboard_js
    assert "spawned from" in dashboard_js
    assert "spawned threads" in dashboard_js
    assert "Aggregate only" not in dashboard
    assert "Call Details" in dashboard
    assert "Dashboard guide" in dashboard
    assert "github.com/douglasmonsky/codex-usage-tracker/blob/main/docs/dashboard-guide.md" not in dashboard
    assert "codex-usage-tracker-guide/dashboard-guide.html" in dashboard
    assert (tmp_path / "codex-usage-tracker-guide" / "dashboard-guide.html").exists()
    assert (tmp_path / "codex-usage-tracker-guide" / "assets" / "dashboard-calls.png").exists()
    assert (asset_dir / "dashboard.js").exists()
    assert (asset_dir / "dashboard.css").exists()
    assert "detail-section" in dashboard
    assert "time-cell" in dashboard_surface
    assert "formatTimestamp" in dashboard_js
    assert "scrollbar-gutter: stable" in dashboard_css
    assert "overflow-y: scroll" in dashboard_css
    assert "formatTimestamp(pricingSource.fetched_at)" in dashboard_js
    assert "formatTimestamp(nextPayload.refreshed_at)" in dashboard_js
    assert "threadModelSummary" in dashboard_js
    assert "model-pill" in dashboard_surface
    assert "Back to top" in dashboard
    assert "updateToTopVisibility" in dashboard_js
    assert "Live refresh every" in dashboard_js
    assert "Refreshing local usage index" in dashboard_js
    assert "loadLimit" in dashboard
    assert "pager" in dashboard
    assert "pagerEl.hidden = !shouldShowPager" in dashboard_js
    assert "updatePager(page, 'threads')" in dashboard_js
    assert "All calls" in dashboard
    assert "/api/usage" in dashboard_js
    assert "detail-card primary" in dashboard_js
    assert "Thread timeline" in dashboard_js
    assert "Raw aggregate identifiers" in dashboard_js
    assert "Codex credits" in dashboard_js
    assert "Allowance impact" in dashboard_js
    assert "Credit model" in dashboard_js
    assert 'data-sort-key="time"' in dashboard
    assert 'data-sort-key="thread"' in dashboard
    assert '<option value="attention" selected>Needs attention</option>' in dashboard
    assert '<option value="usage">Highest Codex credits</option>' in dashboard


def test_dashboard_guide_link_can_use_docs_url_override(tmp_path: Path, monkeypatch) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    monkeypatch.setenv("CODEX_USAGE_TRACKER_DOCS_URL", "https://example.test/guide")

    dashboard_path = tmp_path / "dashboard.html"
    generate_dashboard(db_path=db_path, output_path=dashboard_path)

    dashboard = dashboard_path.read_text(encoding="utf-8")
    assert 'href="https://example.test/guide"' in dashboard
    assert not (tmp_path / "codex-usage-tracker-guide").exists()
    assert (tmp_path / "codex-usage-tracker-assets" / "dashboard.js").exists()


def test_dashboard_server_usage_api_refreshes_aggregate_rows(tmp_path: Path) -> None:
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
        limit=5000,
        since=None,
        codex_home=codex_home,
        include_archived=False,
        dashboard_name="dashboard.html",
        context_chars=2000,
        refresh_lock=threading.Lock(),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            f"http://127.0.0.1:{server.server_port}/api/usage?refresh=1&limit=2",
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
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert limited_payload["refresh_result"]["parsed_events"] == 4
    assert limited_payload["refresh_result"]["skipped_events"] == 0
    assert len(limited_payload["rows"]) == 2
    assert limited_payload["loaded_row_count"] == 2
    assert limited_payload["total_available_rows"] == 4
    assert limited_payload["limit"] == 2
    assert content_security_policy is not None
    assert "connect-src 'self'" in content_security_policy
    assert referrer_policy == "no-referrer"
    assert len(all_payload["rows"]) == 4
    assert all_payload["loaded_row_count"] == 4
    assert all_payload["total_available_rows"] == 4
    assert all_payload["limit"] is None
    assert all_payload["limit_label"] == "All"
    assert limited_payload["pricing_configured"] is True
    assert limited_payload["allowance_configured"] is False
    assert limited_payload["allowance_source"]["name"] == "OpenAI Codex rate card"
    assert limited_payload["rows"][0]["usage_credits"] is not None
    assert "refreshed_at" in limited_payload
    assert "SECRET RAW PROMPT" not in json.dumps(limited_payload)


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
        limit=5000,
        since=None,
        codex_home=tmp_path / ".codex",
        include_archived=False,
        dashboard_name="dashboard.html",
        context_chars=2000,
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
            f"http://127.0.0.1:{server.server_port}/api/context?record_id=abc"
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert usage_error["status"] == 500
    assert "Database error" in usage_error["payload"]["error"]
    assert context_error["status"] == 500
    assert "Database error" in context_error["payload"]["error"]


def test_dashboard_query_limit_zero_loads_all_rows(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    assert len(query_dashboard_events(db_path=db_path, limit=2)) == 2
    assert len(query_dashboard_events(db_path=db_path, limit=0)) == 4
    assert query_dashboard_event_count(db_path=db_path) == 4


def test_context_loads_raw_log_only_on_demand(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    rows = query_session_usage(db_path=db_path, session_id=SESSION_ID)

    context = load_call_context(rows[0]["record_id"], db_path=db_path)
    context_text = json.dumps(context)

    assert context["loaded_on_demand"] is True
    assert context["raw_context_persisted"] is False
    assert "SECRET RAW PROMPT" in context_text
    assert "sk" + "-proj-" not in context_text
    assert "AKIAIOSFODNN7EXAMPLE" not in context_text
    assert "Authorization: Bearer abc.def" not in context_text
    assert "xoxb-123456789012" not in context_text
    assert "eyJhbGciOiJIUzI1Ni" not in context_text
    assert "client_secret=super-secret-value" not in context_text
    assert "BEGIN OPENSSH PRIVATE KEY" not in context_text
    assert "[REDACTED_OPENAI_KEY]" in context_text
    assert "[REDACTED_AWS_ACCESS_KEY]" in context_text
    assert "[REDACTED_BEARER_TOKEN]" in context_text
    assert "[REDACTED_SLACK_TOKEN]" in context_text
    assert "[REDACTED_JWT]" in context_text
    assert "[REDACTED_PRIVATE_KEY]" in context_text
    assert any(entry["label"] == "message / user" for entry in context["entries"])


def test_mcp_wrappers_smoke(tmp_path: Path, monkeypatch) -> None:
    from codex_usage_tracker import mcp_server

    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    dashboard_path = tmp_path / "dashboard.html"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    allowance_path = tmp_path / "allowance.json"
    monkeypatch.setattr(mcp_server, "DEFAULT_CODEX_HOME", codex_home)
    monkeypatch.setattr(mcp_server, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_DASHBOARD_PATH", dashboard_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_PRICING_PATH", pricing_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_ALLOWANCE_PATH", allowance_path)
    monkeypatch.setattr(mcp_server, "update_pricing_from_openai_docs", _fake_pricing_update)

    refresh = mcp_server.refresh_usage_index()
    summary = mcp_server.usage_summary(group_by="thread")
    model_summary = mcp_server.usage_summary(preset="by-model")
    expensive = mcp_server.most_expensive_usage_calls(limit=1)
    pricing_coverage = mcp_server.usage_pricing_coverage()
    session = mcp_server.session_usage(session_id=SESSION_ID)
    record_id = query_session_usage(db_path=db_path, session_id=SESSION_ID)[0]["record_id"]
    context_disabled = mcp_server.usage_call_context(record_id=record_id)
    monkeypatch.setenv("CODEX_USAGE_TRACKER_ALLOW_RAW_CONTEXT", "1")
    context = mcp_server.usage_call_context(record_id=record_id)
    dashboard = mcp_server.generate_usage_dashboard()
    pricing_update = mcp_server.update_usage_pricing_config()
    allowance = mcp_server.init_usage_allowance_config()
    doctor = mcp_server.usage_doctor()

    assert refresh["parsed_events"] == 4
    assert refresh["skipped_events"] == 0
    assert "Add Codex token tracking" in summary
    assert "estimated cost" in model_summary
    assert "Most expensive Codex calls" in expensive
    assert "Codex pricing coverage" in pricing_coverage
    assert SESSION_ID in session
    assert "Raw context loading through MCP is disabled" in context_disabled
    assert "SECRET RAW PROMPT" not in context_disabled
    assert "SECRET RAW PROMPT" in context
    assert "sk" + "-proj-" not in context
    assert "[REDACTED_OPENAI_KEY]" in context
    assert dashboard["dashboard_path"] == str(dashboard_path)
    assert pricing_update["model_count"] == 1
    assert pricing_update["source_url"] == "https://example.test/pricing.md"
    assert allowance["allowance_path"] == str(allowance_path)
    assert allowance_path.exists()
    assert "Codex Usage Tracker doctor" in doctor


def test_pricing_annotation_and_doctor_pass(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    dashboard_path = tmp_path / "dashboard.html"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    generate_dashboard(db_path=db_path, output_path=dashboard_path, pricing_path=pricing_path)

    rows = query_most_expensive_calls(db_path=db_path, limit=1)
    annotated = annotate_rows_with_efficiency(
        rows, pricing=load_pricing_config(tmp_path / "missing-pricing.json")
    )
    assert annotated[0]["estimated_cost_usd"] is None
    annotated = annotate_rows_with_efficiency(rows, pricing=load_pricing_config(pricing_path))
    assert annotated[0]["estimated_cost_usd"] > 0

    repo_root = tmp_path / "repo"
    (repo_root / ".codex-plugin").mkdir(parents=True)
    (repo_root / ".codex-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    (repo_root / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "codex-usage-tracker": {
                        "command": "/usr/bin/python3",
                        "args": ["-m", "codex_usage_tracker.mcp_server"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    plugin_link = tmp_path / "plugins" / "codex-usage-tracker"
    plugin_link.parent.mkdir()
    plugin_link.symlink_to(repo_root, target_is_directory=True)
    marketplace_path = tmp_path / "marketplace.json"
    marketplace_path.write_text(
        json.dumps({"plugins": [{"name": "codex-usage-tracker"}]}),
        encoding="utf-8",
    )

    report = run_doctor(
        codex_home=codex_home,
        db_path=db_path,
        dashboard_path=dashboard_path,
        pricing_path=pricing_path,
        plugin_link=plugin_link,
        marketplace_path=marketplace_path,
        repo_root=repo_root,
    )

    assert report["status"] == "pass"


def _make_codex_home(tmp_path: Path) -> Path:
    codex_home = tmp_path / ".codex"
    log_dir = codex_home / "sessions" / "2026" / "05" / "17"
    log_path = log_dir / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    second_log_path = log_dir / f"rollout-2026-05-17T16-24-11-{SECOND_SESSION_ID}.jsonl"
    auto_review_log_path = log_dir / f"rollout-2026-05-17T16-31-02-{AUTO_REVIEW_SESSION_ID}.jsonl"
    _write_jsonl(
        codex_home / "session_index.jsonl",
        [
            {
                "id": SESSION_ID,
                "thread_name": "Add Codex token tracking",
                "updated_at": "2026-05-17T18:58:27Z",
            },
            {
                "id": SECOND_SESSION_ID,
                "updated_at": "2026-05-17T20:24:11Z",
            },
            {
                "id": AUTO_REVIEW_SESSION_ID,
                "updated_at": "2026-05-17T20:31:02Z",
            },
        ],
    )
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": SESSION_ID}),
            _entry(
                "turn_context",
                {
                    "turn_id": "turn-a",
                    "model": "gpt-5.5",
                    "effort": "xhigh",
                    "cwd": "/tmp/codex-usage-tracker",
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "SECRET RAW PROMPT "
                            + "sk"
                            + "-proj-abcdefghijklmnopqrstuvwxyz123456 "
                            + "AKIAIOSFODNN7EXAMPLE "
                            + "Authorization: Bearer abc.def.ghi123456789 "
                            + "xoxb-123456789012-123456789012-abcdefghijklmnopqrstuvwx "
                            + "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                            + "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkNvZGV4In0."
                            + "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c "
                            + "client_secret=super-secret-value "
                            + "-----BEGIN OPENSSH PRIVATE KEY-----abc123-----END OPENSSH PRIVATE KEY-----",
                        }
                    ],
                },
            ),
            _token_event(100, 100),
            _token_event(300, 200),
        ],
    )
    _write_jsonl(
        second_log_path,
        [
            _entry(
                "session_meta",
                {
                    "id": SECOND_SESSION_ID,
                    "thread_source": "subagent",
                    "source": {
                        "subagent": {
                            "thread_spawn": {
                                "parent_thread_id": SESSION_ID,
                                "agent_nickname": "Verifier",
                                "agent_role": "test_runner",
                            }
                        }
                    },
                },
            ),
            _entry(
                "turn_context",
                {
                    "turn_id": "turn-c",
                    "model": "gpt-5.5",
                    "effort": "medium",
                    "cwd": "/tmp/codex-usage-tracker",
                },
            ),
            _token_event(50, 50),
        ],
    )
    _write_jsonl(
        auto_review_log_path,
        [
            _entry(
                "session_meta",
                {
                    "id": AUTO_REVIEW_SESSION_ID,
                    "thread_source": "subagent",
                    "source": {"subagent": {"other": "guardian"}},
                },
            ),
            _entry(
                "turn_context",
                {
                    "turn_id": "turn-d",
                    "model": "codex-auto-review",
                    "effort": "low",
                    "cwd": "/tmp/codex-usage-tracker",
                },
            ),
            _token_event(50, 50),
        ],
    )
    return codex_home


def _write_pricing(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "models": {
                    "gpt-5.5": {
                        "input_per_million": 2.0,
                        "cached_input_per_million": 0.5,
                        "output_per_million": 10.0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def _http_error_json(url: str) -> dict[str, object]:
    try:
        urllib.request.urlopen(url, timeout=5)  # noqa: S310 - local test server only
    except urllib.error.HTTPError as exc:
        return {
            "status": exc.code,
            "payload": json.loads(exc.read().decode("utf-8")),
        }
    raise AssertionError("expected HTTPError")


def _fake_pricing_update(
    path: Path,
    tier: str = "standard",
    include_estimates: bool = True,
) -> PricingUpdateResult:
    return PricingUpdateResult(
        path=path,
        source_url="https://example.test/pricing.md",
        tier=tier,
        fetched_at="2026-05-17T00:00:00+00:00",
        model_count=1,
        estimated_model_count=1 if include_estimates else 0,
        backup_path=None,
    )


def _token_event(cumulative_total: int, last_total: int) -> dict[str, object]:
    return _entry(
        "event_msg",
        {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": cumulative_total - 25,
                    "cached_input_tokens": 25,
                    "output_tokens": 25,
                    "reasoning_output_tokens": 5,
                    "total_tokens": cumulative_total,
                },
                "last_token_usage": {
                    "input_tokens": last_total - 25,
                    "cached_input_tokens": 10,
                    "output_tokens": 25,
                    "reasoning_output_tokens": 5,
                    "total_tokens": last_total,
                },
                "model_context_window": 258400,
            },
        },
    )


def _entry(entry_type: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "timestamp": "2026-05-17T18:58:27.000Z",
        "type": entry_type,
        "payload": payload,
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
