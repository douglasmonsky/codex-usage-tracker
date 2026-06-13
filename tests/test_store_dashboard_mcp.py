from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from store_dashboard_helpers import (
    SECOND_SESSION_ID,
    SESSION_ID,
    _entry,
    _extract_js_function,
    _make_codex_home,
    _token_event,
    _usage_event,
    _write_archived_log,
    _write_jsonl,
    _write_pricing,
)

from codex_usage_tracker import store as store_module
from codex_usage_tracker.dashboard import dashboard_payload, generate_dashboard
from codex_usage_tracker.models import UsageEvent
from codex_usage_tracker.store import (
    EVENT_COLUMNS,
    connect,
    export_usage_csv,
    init_db,
    query_dashboard_event_count,
    query_dashboard_events,
    query_most_expensive_calls,
    query_session_usage,
    query_summary,
    query_thread_summaries,
    rebuild_usage_index,
    refresh_metadata,
    refresh_usage_index,
    schema_state,
    upsert_usage_events,
)


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
    assert second.parsed_events == 0
    assert second.inserted_or_updated_events == 0
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
    assert meta["parsed_events"] == "0"
    assert meta["skipped_events"] == "0"
    assert meta["inserted_or_updated_events"] == "0"
    assert meta["parsed_source_files"] == "0"
    assert meta["skipped_source_files"] == "3"
    assert meta["parser_adapter"] == "codex-jsonl-v1"
    assert meta["schema_version"] == "7"
    assert meta["parser_skipped_events"] == "0"
    state = schema_state(db_path)
    assert state["schema_version"] == 7
    assert state["checksum_matches"] is True
    assert [row["version"] for row in state["migrations"]] == [1, 2, 3, 4, 5, 6, 7]
    with connect(db_path) as conn:
        init_db(conn)
        source_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT source_file, size_bytes, parsed_until_line, latest_record_id,
                    parser_diagnostics_json, parser_state_json
                FROM source_files
                ORDER BY source_file
                """
            ).fetchall()
        ]
    assert len(source_rows) == 3
    assert all(row["size_bytes"] > 0 for row in source_rows)
    assert all(row["parsed_until_line"] > 0 for row in source_rows)
    assert any(row["latest_record_id"] for row in source_rows)
    assert all(row["parser_state_json"] for row in source_rows)
    assert "SECRET RAW PROMPT" not in json.dumps(source_rows)


def test_refresh_reports_skipped_corrupt_token_events(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    log_path = next(path for path in (codex_home / "sessions").glob("**/*.jsonl") if SESSION_ID in path.name)
    corrupt = _token_event(600, 300)
    corrupt["payload"]["info"]["last_token_usage"]["total_tokens"] = "bad-total"  # type: ignore[index]
    valid = _token_event(650, 50)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(corrupt) + "\n")
        handle.write(json.dumps(valid) + "\n")

    result = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    rows = query_session_usage(db_path=db_path, session_id=SESSION_ID)

    assert result.skipped_events == 1
    assert result.parser_diagnostics["invalid_integer"] == 1
    assert refresh_metadata(db_path)["parser_invalid_integer"] == "1"
    assert result.parsed_events == 5
    assert [row["cumulative_total_tokens"] for row in rows] == [100, 300, 650]


def test_refresh_indexes_only_appended_token_events_when_source_grows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    log_path = next(
        path for path in (codex_home / "sessions").glob("**/*.jsonl") if SESSION_ID in path.name
    )

    first = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    with connect(db_path) as conn:
        init_db(conn)
        source_before = conn.execute(
            """
            SELECT parsed_until_byte, parsed_until_line, parser_state_json
            FROM source_files
            WHERE source_file = ?
            """,
            (str(log_path),),
        ).fetchone()
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_token_event(650, 350)) + "\n")
    parse_calls: list[dict[str, Any]] = []
    original_parse = store_module.parse_usage_events_from_file_with_state

    def tracking_parse(*args: Any, **kwargs: Any):
        parse_calls.append(
            {
                "path": args[0],
                "start_byte": kwargs.get("start_byte"),
                "start_line": kwargs.get("start_line"),
                "initial_state": kwargs.get("initial_state"),
            }
        )
        return original_parse(*args, **kwargs)

    monkeypatch.setattr(
        store_module,
        "parse_usage_events_from_file_with_state",
        tracking_parse,
    )
    second = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    third = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    rows = query_session_usage(db_path=db_path, session_id=SESSION_ID)
    metadata = refresh_metadata(db_path)

    assert first.parsed_events == 4
    assert source_before is not None
    assert source_before["parser_state_json"]
    assert len(parse_calls) == 1
    assert parse_calls[0]["path"] == log_path
    assert parse_calls[0]["start_byte"] == source_before["parsed_until_byte"]
    assert parse_calls[0]["start_line"] == source_before["parsed_until_line"]
    assert parse_calls[0]["start_byte"] > 0
    assert parse_calls[0]["initial_state"] is not None
    assert second.parsed_events == 1
    assert second.inserted_or_updated_events == 1
    assert third.parsed_events == 0
    assert [row["cumulative_total_tokens"] for row in rows] == [100, 300, 650]
    assert metadata["parsed_source_files"] == "0"
    assert metadata["skipped_source_files"] == "3"


def test_append_cursor_preserves_pending_call_origin_between_refreshes(
    tmp_path: Path,
) -> None:
    session_id = "019e37d5-f19f-7e4d-84cb-50894143c001"
    codex_home = tmp_path / ".codex"
    log_path = (
        codex_home
        / "sessions"
        / "2026"
        / "05"
        / "17"
        / f"rollout-2026-05-17T18-58-27-{session_id}.jsonl"
    )
    _write_jsonl(
        codex_home / "session_index.jsonl",
        [
            {
                "id": session_id,
                "thread_name": "Append cursor origin",
                "updated_at": "2026-05-17T19:00:00Z",
            }
        ],
    )
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": session_id}),
            _entry("turn_context", {"turn_id": "turn-a", "model": "gpt-5.5"}),
            _token_event(100, 100),
            _entry(
                "response_item",
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "SECRET PENDING USER TEXT"}],
                },
            ),
        ],
    )
    db_path = tmp_path / "usage.sqlite3"

    first = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_token_event(150, 50)) + "\n")
    second = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    rows = query_session_usage(db_path=db_path, session_id=session_id)
    source_rows_text = ""
    with connect(db_path) as conn:
        init_db(conn)
        source_rows_text = json.dumps(
            [
                dict(row)
                for row in conn.execute(
                    "SELECT parser_state_json FROM source_files WHERE source_file = ?",
                    (str(log_path),),
                ).fetchall()
            ]
        )

    assert first.parsed_events == 1
    assert second.parsed_events == 1
    assert [row["cumulative_total_tokens"] for row in rows] == [100, 150]
    assert rows[-1]["call_initiator"] == "user"
    assert rows[-1]["call_initiator_reason"] == "user_message"
    assert "SECRET PENDING USER TEXT" not in source_rows_text


def test_connect_sets_sqlite_concurrency_pragmas(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    with connect(db_path) as conn:
        init_db(conn)
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]

    assert busy_timeout == 5000
    assert str(journal_mode).lower() == "wal"
    assert user_version == 7


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
        migrations = [
            dict(row)
            for row in conn.execute(
                "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
            ).fetchall()
        ]

    assert {
        "thread_source",
        "parent_thread_name",
        "parent_session_updated_at",
        "call_initiator",
        "call_initiator_reason",
        "call_initiator_confidence",
        "is_archived",
        "thread_key",
        "thread_call_index",
        "previous_record_id",
        "next_record_id",
    } <= columns
    assert "idx_usage_timestamp" in indexes
    assert "idx_usage_parent_thread" in indexes
    assert "idx_usage_total_tokens" in indexes
    assert user_version == 7
    assert [row["version"] for row in migrations] == [1, 2, 3, 4, 5, 6, 7]


def test_rebuild_index_clears_aggregate_rows_before_rescan(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    with connect(db_path) as conn:
        init_db(conn)
        conn.execute("INSERT INTO refresh_meta (key, value) VALUES ('stale', 'yes')")
        conn.execute("DELETE FROM usage_events")

    result = rebuild_usage_index(codex_home=codex_home, db_path=db_path)

    assert result.parsed_events == 4
    assert query_dashboard_event_count(db_path=db_path) == 4
    assert "stale" not in refresh_metadata(db_path)


def test_dashboard_event_query_uses_sql_prefilters(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    model_rows = query_dashboard_events(db_path=db_path, limit=0, model="codex-auto-review")
    effort_rows = query_dashboard_events(db_path=db_path, limit=0, effort="xhigh")
    token_rows = query_dashboard_events(db_path=db_path, limit=0, min_tokens=100)
    thread_rows = query_dashboard_events(
        db_path=db_path,
        limit=0,
        thread="Add Codex token tracking",
    )
    offset_rows = query_dashboard_events(db_path=db_path, limit=2, offset=2)
    session_rows = query_dashboard_events(db_path=db_path, limit=0, thread=SESSION_ID)
    since_rows = query_dashboard_events(db_path=db_path, limit=0, since="2026-05-17")
    future_rows = query_dashboard_events(db_path=db_path, limit=0, until="2000-01-01")

    assert len(model_rows) == 1
    assert model_rows[0]["model"] == "codex-auto-review"
    assert {row["effort"] for row in effort_rows} == {"xhigh"}
    assert {row["total_tokens"] for row in token_rows} == {100, 200}
    assert {row["session_id"] for row in thread_rows} >= {SESSION_ID, SECOND_SESSION_ID}
    assert len(offset_rows) == 2
    assert {row["record_id"] for row in offset_rows}.isdisjoint(
        {row["record_id"] for row in query_dashboard_events(db_path=db_path, limit=2)}
    )
    assert {row["session_id"] for row in session_rows} == {SESSION_ID}
    assert len(since_rows) == 4
    assert future_rows == []


def test_large_history_query_prefilter_uses_sql_indexes(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    events = [
        UsageEvent(
            record_id=f"record-{index}",
            session_id=f"session-{index % 100}",
            thread_name=f"Thread {index % 25}",
            session_updated_at="2026-05-17T18:58:27Z",
            event_timestamp=f"2026-05-{(index % 28) + 1:02d}T12:00:00Z",
            source_file=f"/tmp/synthetic/{index}.jsonl",
            line_number=index + 1,
            turn_id=f"turn-{index}",
            turn_timestamp=f"2026-05-{(index % 28) + 1:02d}T12:00:00Z",
            cwd=f"/tmp/project-{index % 10}",
            model="gpt-5.5" if index % 2 == 0 else "codex-auto-review",
            effort="high" if index % 3 == 0 else "low",
            current_date="2026-05-17",
            timezone="UTC",
            call_initiator="user",
            call_initiator_reason="user_message",
            call_initiator_confidence="high",
            is_archived=0,
            thread_key=f"thread:Thread {index % 25}",
            thread_call_index=None,
            previous_record_id=None,
            next_record_id=None,
            thread_source="user",
            subagent_type=None,
            agent_role=None,
            agent_nickname=None,
            parent_session_id=None,
            parent_thread_name=None,
            parent_session_updated_at=None,
            model_context_window=200000,
            input_tokens=1000 + index,
            cached_input_tokens=200,
            output_tokens=100,
            reasoning_output_tokens=10,
            total_tokens=1100 + index,
            cumulative_input_tokens=1000 + index,
            cumulative_cached_input_tokens=200,
            cumulative_output_tokens=100,
            cumulative_reasoning_output_tokens=10,
            cumulative_total_tokens=1100 + index,
        )
        for index in range(10_000)
    ]
    upsert_usage_events(events, db_path=db_path)

    rows = query_dashboard_events(
        db_path=db_path,
        limit=25,
        model="gpt-5.5",
        effort="high",
        min_tokens=9000,
    )
    with connect(db_path) as conn:
        init_db(conn)
        plan = " ".join(
            str(row["detail"])
            for row in conn.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT *
                FROM usage_events
                WHERE model = ? AND effort = ? AND total_tokens >= ?
                """,
                ("gpt-5.5", "high", 9000),
            )
        )

    assert len(rows) == 25
    assert all(row["model"] == "gpt-5.5" for row in rows)
    assert all(row["effort"] == "high" for row in rows)
    assert all(row["total_tokens"] >= 9000 for row in rows)
    assert "idx_usage_model_effort" in plan


def test_upsert_refreshes_thread_adjacency_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    events = [
        _usage_event(
            record_id="a1",
            session_id="session-a",
            thread_key="thread:Alpha",
            event_timestamp="2026-05-17T12:00:00Z",
            cumulative_total_tokens=100,
        ),
        _usage_event(
            record_id="b1",
            session_id="session-b",
            thread_key="thread:Beta",
            event_timestamp="2026-05-17T12:00:01Z",
            cumulative_total_tokens=50,
        ),
        _usage_event(
            record_id="a2",
            session_id="session-a",
            thread_key="thread:Alpha",
            event_timestamp="2026-05-17T12:00:02Z",
            cumulative_total_tokens=200,
        ),
        _usage_event(
            record_id="a3",
            session_id="session-a",
            thread_key="thread:Alpha",
            event_timestamp="2026-05-17T12:00:03Z",
            cumulative_total_tokens=300,
        ),
    ]

    upsert_usage_events(events, db_path=db_path)
    rows = query_dashboard_events(db_path=db_path, limit=0, include_archived=True)
    by_id = {row["record_id"]: row for row in rows}

    assert by_id["a1"]["thread_call_index"] == 1
    assert by_id["a1"]["previous_record_id"] is None
    assert by_id["a1"]["next_record_id"] == "a2"
    assert by_id["a2"]["thread_call_index"] == 2
    assert by_id["a2"]["previous_record_id"] == "a1"
    assert by_id["a2"]["next_record_id"] == "a3"
    assert by_id["a3"]["thread_call_index"] == 3
    assert by_id["a3"]["previous_record_id"] == "a2"
    assert by_id["a3"]["next_record_id"] is None
    assert by_id["b1"]["thread_call_index"] == 1
    assert by_id["b1"]["previous_record_id"] is None
    assert by_id["b1"]["next_record_id"] is None


def test_upsert_materializes_thread_summaries(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    events = [
        _usage_event(
            record_id="a1",
            session_id="session-a",
            thread_key="thread:Alpha",
            event_timestamp="2026-05-17T12:00:00Z",
            cumulative_total_tokens=100,
        ),
        _usage_event(
            record_id="a2",
            session_id="session-a",
            thread_key="thread:Alpha",
            event_timestamp="2026-05-17T12:00:02Z",
            cumulative_total_tokens=220,
        ),
        _usage_event(
            record_id="b1",
            session_id="session-b",
            thread_key="thread:Beta",
            event_timestamp="2026-05-17T12:00:01Z",
            cumulative_total_tokens=90,
        ),
    ]

    upsert_usage_events(events, db_path=db_path)
    summaries = query_thread_summaries(db_path=db_path, limit=0, include_archived=False)
    by_key = {row["thread_key"]: row for row in summaries}

    assert set(by_key) == {"thread:Alpha", "thread:Beta"}
    assert by_key["thread:Alpha"]["call_count"] == 2
    assert by_key["thread:Alpha"]["session_count"] == 1
    assert by_key["thread:Alpha"]["total_tokens"] == 220
    assert by_key["thread:Alpha"]["cached_input_tokens"] == 40
    assert by_key["thread:Alpha"]["call_initiator_summary"] == "mostly_user"
    assert by_key["thread:Alpha"]["is_archived_scope"] == "active"
    assert by_key["thread:Alpha"]["estimated_cost_usd"] is None
    assert by_key["thread:Alpha"]["usage_credits"] is None

    with connect(db_path) as conn:
        init_db(conn)
        persisted = conn.execute("SELECT COUNT(*) AS count FROM thread_summaries").fetchone()
    assert persisted is not None
    assert persisted["count"] == 4


def test_thread_summaries_keep_active_and_all_history_scopes_separate(
    tmp_path: Path,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    _write_archived_log(codex_home)
    db_path = tmp_path / "usage.sqlite3"

    refresh_usage_index(codex_home=codex_home, db_path=db_path, include_archived=True)
    active_summaries = query_thread_summaries(db_path=db_path, limit=0)
    all_summaries = query_thread_summaries(
        db_path=db_path,
        limit=0,
        include_archived=True,
    )

    assert {row["is_archived_scope"] for row in active_summaries} == {"active"}
    assert {row["is_archived_scope"] for row in all_summaries} == {"all-history"}
    assert sum(row["call_count"] for row in active_summaries) == 4
    assert sum(row["call_count"] for row in all_summaries) == 5
    assert sum(row["archived_call_count"] for row in active_summaries) == 0
    assert sum(row["archived_call_count"] for row in all_summaries) == 1


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
    dashboard_format_js = (asset_dir / "dashboard_format.js").read_text(encoding="utf-8")
    dashboard_data_js = (asset_dir / "dashboard_data.js").read_text(encoding="utf-8")
    dashboard_analysis_js = (asset_dir / "dashboard_analysis.js").read_text(encoding="utf-8")
    dashboard_cells_js = (asset_dir / "dashboard_cells.js").read_text(encoding="utf-8")
    dashboard_details_js = (asset_dir / "dashboard_details.js").read_text(encoding="utf-8")
    dashboard_tables_js = (asset_dir / "dashboard_tables.js").read_text(encoding="utf-8")
    dashboard_filters_js = (asset_dir / "dashboard_filters.js").read_text(encoding="utf-8")
    dashboard_payload_cache_js = (asset_dir / "dashboard_payload_cache.js").read_text(
        encoding="utf-8"
    )
    dashboard_i18n_js = (asset_dir / "dashboard_i18n.js").read_text(encoding="utf-8")
    dashboard_tooltips_js = (asset_dir / "dashboard_tooltips.js").read_text(encoding="utf-8")
    dashboard_call_js = (asset_dir / "dashboard_call_investigator.js").read_text(
        encoding="utf-8"
    )
    dashboard_state_js = (asset_dir / "dashboard_state.js").read_text(encoding="utf-8")
    dashboard_stylesheets = [
        "dashboard.css",
        "dashboard_call.css",
        "dashboard_insights.css",
        "dashboard_layout.css",
        "dashboard_tables.css",
        "dashboard_detail.css",
        "dashboard_responsive.css",
    ]
    dashboard_css = "\n".join(
        (asset_dir / stylesheet).read_text(encoding="utf-8")
        for stylesheet in dashboard_stylesheets
    )
    render_calls_js = _extract_js_function(dashboard_tables_js, "renderCalls")
    dashboard_surface = "\n".join([
        dashboard,
        dashboard_format_js,
        dashboard_data_js,
        dashboard_analysis_js,
        dashboard_cells_js,
        dashboard_details_js,
        dashboard_tables_js,
        dashboard_filters_js,
        dashboard_payload_cache_js,
        dashboard_i18n_js,
        dashboard_tooltips_js,
        dashboard_call_js,
        dashboard_js,
        dashboard_state_js,
        dashboard_css,
    ])
    csv_text = csv_path.read_text(encoding="utf-8")
    assert exported == 4
    assert exported_with_zero_limit == 4
    assert "SECRET RAW PROMPT" not in dashboard
    assert "SECRET RAW PROMPT" not in dashboard_js
    assert "SECRET RAW PROMPT" not in dashboard_analysis_js
    assert "SECRET RAW PROMPT" not in dashboard_cells_js
    assert "SECRET RAW PROMPT" not in dashboard_details_js
    assert "SECRET RAW PROMPT" not in dashboard_tables_js
    assert "SECRET RAW PROMPT" not in dashboard_filters_js
    assert "SECRET RAW PROMPT" not in dashboard_payload_cache_js
    assert "SECRET RAW PROMPT" not in dashboard_i18n_js
    assert "SECRET RAW PROMPT" not in dashboard_tooltips_js
    assert "SECRET RAW PROMPT" not in dashboard_call_js
    assert "SECRET RAW PROMPT" not in dashboard_css
    assert "SECRET RAW PROMPT" not in csv_text
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_analysis_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_cells_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_details_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_tables_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_filters_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_payload_cache_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_i18n_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_tooltips_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_call_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_analysis_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_cells_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_details_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_tables_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_filters_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_payload_cache_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_i18n_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_tooltips_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_call_js
    for stylesheet in dashboard_stylesheets:
        assert f'href="codex-usage-tracker-assets/{stylesheet}?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_format.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_data.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_analysis.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_cells.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_details.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_tables.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_filters.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_state.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_payload_cache.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_i18n.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_tooltips.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_call_investigator.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard.js?v=' in dashboard
    assert "CodexUsageDashboardFormat" in dashboard_format_js
    assert "CodexUsageDashboardData" in dashboard_data_js
    assert "CodexUsageDashboardAnalysis" in dashboard_analysis_js
    assert "CodexUsageDashboardCells" in dashboard_cells_js
    assert "CodexUsageDashboardDetails" in dashboard_details_js
    assert "CodexUsageDashboardTables" in dashboard_tables_js
    assert "CodexUsageDashboardFilters" in dashboard_filters_js
    assert "CodexUsageDashboardState" in dashboard_state_js
    assert "CodexUsageDashboardPayloadCache" in dashboard_payload_cache_js
    assert "CodexUsageDashboardI18n" in dashboard_i18n_js
    assert "CodexUsageDashboardTooltips" in dashboard_tooltips_js
    assert "CodexUsageCallInvestigator" in dashboard_call_js
    assert "copyViewLink" in dashboard
    assert "exportVisible" in dashboard
    assert "Copy link" in dashboard
    assert "Export CSV" in dashboard
    assert "currentDashboardState" in dashboard_js
    assert "copyCurrentViewLink" in dashboard_js
    assert "exportCurrentRows" in dashboard_js
    assert "last call" in dashboard_surface.lower()
    assert "metric.session_cumulative" in dashboard_surface.lower()

    from codex_usage_tracker.i18n import translations_for
    en_trans = translations_for("en")
    assert "session cumulative" in en_trans["metric.session_cumulative"].lower()
    assert "Estimated Cost" in dashboard
    assert "estimated_cost_usd" in dashboard
    assert "pricing_snapshot" in dashboard
    assert "rates_fingerprint" in dashboard
    assert "Uncached Input" in dashboard
    assert "uncachedTokens" in dashboard
    assert "Codex Credits" in dashboard
    assert "Usage Remaining" in dashboard
    assert "Price Coverage" not in dashboard
    assert "priceCoverage" not in dashboard_surface
    assert "usageCredits" in dashboard
    assert "allowanceImpact" in dashboard
    assert "usage_credits" in dashboard
    assert "parser_diagnostics" in dashboard
    assert "parserDiagnostics" in dashboard_js
    assert "privacyMode" in dashboard
    assert "projectMetadataPrivacy" in dashboard_js
    assert "datePreset" in dashboard
    assert "dateStart" in dashboard
    assert "dateEnd" in dashboard
    assert "dateRangeStatus" in dashboard
    assert "Today" in dashboard
    assert "This week" in dashboard
    assert "Last 7 days" in dashboard
    assert "This month" in dashboard
    assert "Custom range" in dashboard
    assert "currentDateRange" in dashboard_js
    assert "rowMatchesDateRange" in dashboard_js
    assert "syncDatePresetInputs" in dashboard_js
    assert "datePreset: clean(params.get('date'))" in dashboard_state_js
    assert "dateStart: clean(params.get('from'))" in dashboard_state_js
    assert "dateEnd: clean(params.get('to'))" in dashboard_state_js
    assert "api_token" in dashboard
    assert "context_api_enabled" in dashboard
    assert "X-Codex-Usage-Token" in dashboard_js
    assert "contextApiEnabled" in dashboard_js
    assert "recommended_action" in dashboard
    assert "flag_explanations" in dashboard
    assert "action_recommendations" in dashboard
    assert "action_thresholds" in dashboard
    assert "detail.why_flagged" in dashboard_details_js
    assert "detail.thread_lifecycle" in dashboard_details_js
    assert "detail.largest_cumulative_jump" in dashboard_details_js
    assert "project_name" in dashboard
    assert "detail.project_tags" in dashboard_details_js
    assert "detail.git_branch" in dashboard_details_js
    assert "usage_credit_confidence" in dashboard
    assert "allowance.credit_rates" in dashboard_js
    assert "insight.codex_allowance_usage" in dashboard_js
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
    assert "attentionScore" in dashboard_analysis_js
    assert "thread-row" in dashboard_surface
    assert "thread-call-table" in dashboard_surface
    assert "cachedTokenCell" in dashboard_cells_js
    assert "uncachedTokenCell" in dashboard_cells_js
    assert "outputTokenCell" in dashboard_cells_js
    assert "signalPuckAbbreviation" in dashboard_cells_js
    assert "signal-puck" in dashboard_css
    assert "data-thread-call-sort-key" in dashboard_tables_js
    assert "threadCallSortKey = 'time'" in dashboard_js
    assert "threadCallSortDirection = 'desc'" in dashboard_js
    assert "detail.thread_attachment" in dashboard_details_js
    assert "detail.subagent_type" in dashboard_details_js
    assert "source.auto_review" in dashboard_cells_js
    assert "button.load_context" in dashboard_surface
    assert "button.open_investigator" in dashboard_details_js
    assert "Click a call row for deep diagnostics." in dashboard_surface
    assert "data-open-investigator-record" not in render_calls_js
    assert "rowInvestigatorLink(row" in render_calls_js
    assert "target=\"_blank\"" in dashboard_js
    assert "rel=\"noopener\"" in dashboard_js
    assert "a.row-investigator-link" in dashboard_js
    assert "/api/open-investigator" in dashboard_js
    assert "openInvestigatorUrl(rowLink.href)" in dashboard_js
    assert "window.location.href = url" not in dashboard_js
    assert "window.open(url, '_blank')" in dashboard_js
    assert "opened.opener = null" in dashboard_js
    assert "selectRow(row);" not in render_calls_js
    assert "dashboard.view.call" in dashboard_js
    assert "renderCallInvestigator" in dashboard_js
    assert "fetchCallRecord" in dashboard_js
    assert "fetchCallRecord" in dashboard_call_js
    assert "/api/call?" in dashboard_js
    assert "supplementalRowsByRecordId" in dashboard_js
    assert 'body[data-active-view="call"] .detail-section' in dashboard_css
    assert 'body[data-active-view="call"] .table-tools' in dashboard_css
    assert ".call-diagnostic-section.exact" in dashboard_css
    assert "creditsText(usageCreditValue(row))" in dashboard_call_js
    assert "const contextPayloadState = new Map()" in dashboard_call_js
    assert "renderInvestigationReadout" in dashboard_call_js
    assert "contextStateRecord(row)" in dashboard_call_js
    assert "defaultContextRequest" in dashboard_call_js
    assert "mode: 'quick'" in dashboard_call_js
    assert "mode: 'full'" in dashboard_call_js
    assert "includeToolOutput: false" in dashboard_call_js
    assert "maxChars: null" in dashboard_call_js
    assert "maxEntries: defaultContextEntries" in dashboard_call_js
    assert "data-context-toggle-tool-output" in dashboard_call_js
    assert "data-context-full-analysis" in dashboard_call_js
    assert "button.hide_tool_output" in dashboard_call_js
    assert "data-context-autoload-toggle" not in dashboard_call_js
    assert "renderCacheVerdict" in dashboard_call_js
    assert "data-context-scroll" not in dashboard_call_js
    assert ".readout-grid" in dashboard_css
    assert ".cache-verdict" in dashboard_css
    assert ".context-inline-action" in dashboard_css
    assert ".initiator-puck" in dashboard_css
    assert ".initiator-unknown" in dashboard_css
    assert ".initiator-cell" in dashboard_css
    assert "table.initiated" in dashboard_tables_js
    assert "callInitiatorCell" in dashboard_cells_js
    assert "sortLabelText(sortKey)" in dashboard_js
    assert "callInitiatorPuck" in dashboard_cells_js
    assert "row.call_initiator" in dashboard_js
    assert "data-open-investigator-record" in dashboard_details_js
    assert "data-call-nav-record" in dashboard_js
    assert "call.cache_accounting_delta" in dashboard_call_js
    assert "call.hidden_estimate" in dashboard_call_js
    assert "call.serialized_upper_bound" in dashboard_call_js
    assert "call.remaining_after_serialized" in dashboard_call_js
    assert "renderSerializedEvidenceBreakdown" in dashboard_call_js
    assert "serialized_evidence" in dashboard_call_js
    assert ".serialized-breakdown" in dashboard_css
    assert "captureContextUiState" in dashboard_call_js
    assert "restoreContextUiState" in dashboard_call_js
    assert "bindContextUiState" in dashboard_call_js
    assert "data-context-entry-key" in dashboard_call_js
    assert "button.show_tool_output" in dashboard_call_js
    assert "data-context-entry-load-output" in dashboard_call_js
    assert "button.full_serialized_analysis" in dashboard_call_js
    assert ".grid > section:not(.detail-section)" in dashboard_css
    assert "overflow-x: auto" in dashboard_css
    assert "overscroll-behavior-x: contain" in dashboard_css
    assert "position: sticky" in dashboard_css
    assert ".grid > section:first-child > table > thead" in dashboard_css
    assert "${callInitiatorPuck(row)}" in dashboard_details_js
    assert "<span>${escapeHtml(initiator.source)}</span>" not in dashboard_details_js
    assert "tooltipAttributes(label)" in dashboard_call_js
    assert "tooltipAttributes(badge)" in dashboard_call_js
    assert "data-context-load-older" in dashboard_call_js
    assert "data-context-no-budget" not in dashboard_call_js
    assert "renderContextTokenUsage" in dashboard_call_js
    assert "renderContextCompaction" in dashboard_call_js
    assert "renderThreadAnchors" not in dashboard_call_js
    assert "payload.call_anchors" not in dashboard_call_js
    assert "payload.thread_anchors" not in dashboard_call_js
    assert "context-entry-collapsed" in dashboard_call_js
    assert "Evidence analyzed:" in dashboard_call_js
    assert "total_entries" in dashboard_call_js
    assert ".context-anchor-panel" not in dashboard_css
    assert ".context-entry-summary" in dashboard_css
    assert "data-context-compaction-history" in dashboard_call_js
    assert "context-token-breakdown" in dashboard_css
    assert "context-compaction" in dashboard_css
    assert "tool_output_omitted" in dashboard_call_js
    assert "parent_thread_name" in dashboard
    assert "thread_attachment_label" in dashboard
    assert "thread_attachment_relation" in dashboard
    assert "explicit parent thread" in dashboard_surface
    assert "thread.spawned_from" in dashboard_tables_js
    assert "thread.spawned_threads" in dashboard_tables_js

    from codex_usage_tracker.i18n import translations_for
    en_trans = translations_for("en")
    assert en_trans["detail.why_flagged"] == "Why flagged"
    assert en_trans["detail.thread_lifecycle"] == "Thread lifecycle"
    assert en_trans["detail.largest_cumulative_jump"] == "Largest cumulative jump"
    assert en_trans["detail.project_tags"] == "Project tags"
    assert en_trans["detail.git_branch"] == "Git branch"
    assert "Credit rates:" in en_trans["allowance.credit_rates"]
    assert en_trans["insight.codex_allowance_usage"] == "Codex allowance usage"
    assert en_trans["detail.thread_attachment"] == "Thread attachment"
    assert en_trans["detail.subagent_type"] == "Subagent type"
    assert en_trans["source.auto_review"] == "Auto-review"
    assert en_trans["button.show_turn_evidence"] == "Show turn log evidence"
    assert en_trans["button.open_investigator"] == "Open investigator"
    assert en_trans["call.open_hint"] == "Click a call row for deep diagnostics."
    assert en_trans["call.serialized_upper_bound"] == "Serialized local upper bound"
    assert en_trans["call.serialized_bucket_detail"] == "{count} fields · {chars} chars"
    assert en_trans["dashboard.view.call"] == "Call Investigator"
    assert en_trans["button.show_tool_output"] == "Show tool output"
    assert en_trans["button.hide_tool_output"] == "Hide tool output"
    assert en_trans["button.full_serialized_analysis"] == "Run full serialized analysis"
    assert en_trans["button.hide_details"] == "Hide details"
    assert en_trans["table.initiated"] == "Initiated"
    assert en_trans["source.user_initiated"] == "User initiated"
    assert en_trans["source.codex_initiated"] == "Codex initiated"
    assert "spawned from" in en_trans["thread.spawned_from"]
    assert "spawned threads" in en_trans["thread.spawned_threads"]
    assert en_trans["detail.thread_timeline"] == "Thread timeline"
    assert en_trans["detail.raw_identifiers"] == "Raw aggregate identifiers"
    assert en_trans["metric.codex_credits"] == "Codex credits"
    assert en_trans["detail.allowance_impact"] == "Allowance impact"
    assert en_trans["detail.credit_model"] == "Credit model"
    assert "Live refresh every" in en_trans["live.every"]
    assert "Refreshing local usage index" in en_trans["live.refreshing_index"]
    assert "Aggregate only" not in dashboard
    assert "Call Details" in dashboard
    assert "Dashboard guide" in dashboard
    assert "github.com/douglasmonsky/codex-usage-tracker/blob/main/docs/dashboard-guide.md" not in dashboard
    assert "codex-usage-tracker-guide/dashboard-guide.html" in dashboard
    assert (tmp_path / "codex-usage-tracker-guide" / "dashboard-guide.html").exists()
    dashboard_guide = (tmp_path / "codex-usage-tracker-guide" / "dashboard-guide.html").read_text(
        encoding="utf-8"
    )
    assert "call anchors" not in dashboard_guide.lower()
    assert "nearest visible message" not in dashboard_guide
    assert (tmp_path / "codex-usage-tracker-guide" / "assets" / "dashboard-calls.png").exists()
    assert (asset_dir / "dashboard.js").exists()
    assert (asset_dir / "dashboard_call_investigator.js").exists()
    assert (asset_dir / "dashboard_format.js").exists()
    assert (asset_dir / "dashboard_data.js").exists()
    assert (asset_dir / "dashboard_analysis.js").exists()
    assert (asset_dir / "dashboard_cells.js").exists()
    assert (asset_dir / "dashboard_details.js").exists()
    assert (asset_dir / "dashboard_tables.js").exists()
    assert (asset_dir / "dashboard_filters.js").exists()
    assert (asset_dir / "dashboard_state.js").exists()
    assert (asset_dir / "dashboard_payload_cache.js").exists()
    assert (asset_dir / "dashboard_i18n.js").exists()
    assert (asset_dir / "dashboard_tooltips.js").exists()
    for stylesheet in dashboard_stylesheets:
        assert (asset_dir / stylesheet).exists()
    assert "detail-section" in dashboard
    assert "detailToggle" in dashboard
    assert "body[data-detail-panel=\"expanded\"] .grid" in dashboard_css
    assert "applyDetailPanelState()" in dashboard_js
    assert "time-cell" in dashboard_surface
    assert "formatTimestamp" in dashboard_js
    assert "scrollbar-gutter: stable" in dashboard_css
    assert "overflow-y: scroll" in dashboard_css
    assert "formatTimestamp(pricingSource.fetched_at)" in dashboard_js
    assert "pricingSnapshotWarning" in dashboard_js
    assert "formatTimestamp(nextPayload.refreshed_at)" in dashboard_js
    assert "threadModelSummary" in dashboard_analysis_js
    assert "model-pill" in dashboard_surface
    assert "Back to top" in dashboard
    assert "updateToTopVisibility" in dashboard_js
    assert "live.every" in dashboard_js
    assert "live.refreshing_index" in dashboard_js
    assert "loadLimit" in dashboard
    assert "pager" in dashboard
    assert "loadMoreRows" in dashboard
    assert "visibleSlice(rows)" in dashboard_tables_js
    assert "updateLoadMoreControl(page, 'table.threads')" in dashboard_tables_js
    assert "data-thread-load-more" in dashboard_tables_js
    assert "data-fast-tooltip" in dashboard_surface
    assert "scheduleFastTooltip(target)" in dashboard_js
    assert "focusPendingTarget" in dashboard_js
    assert "queueFocusTarget(insight.target)" in dashboard_js
    assert "selected-row" in dashboard_tables_js
    assert "selected-row" in dashboard_css
    assert "costUsageCell" in dashboard_cells_js
    assert "Codex credits" in dashboard
    assert "All calls" in dashboard
    assert "/api/usage" in dashboard_js
    assert "detail-card primary" in dashboard_details_js
    assert "detail.thread_timeline" in dashboard_details_js
    assert "detail.raw_identifiers" in dashboard_details_js
    assert "metric.codex_credits" in dashboard_details_js
    assert "detail.allowance_impact" in dashboard_details_js
    assert "detail.credit_model" in dashboard_details_js
    assert 'data-sort-key="time"' in dashboard
    assert 'data-sort-key="thread"' in dashboard
    assert '<option value="attention" selected data-i18n="option.needs_attention">Needs attention</option>' in dashboard
    assert '<option value="initiator" data-i18n="table.initiated">Initiated</option>' in dashboard
    assert '<option value="usage" data-i18n="option.highest_codex_credits">Highest Codex credits</option>' in dashboard

    pricing_path.write_text(
        json.dumps(
            {
                "_source": {
                    "name": "Synthetic pricing",
                    "fetched_at": "2026-06-05T12:00:00Z",
                },
                "models": {
                    "gpt-5.5": {
                        "input_per_million": 3.0,
                        "cached_input_per_million": 0.75,
                        "output_per_million": 12.0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    generate_dashboard(db_path=db_path, output_path=dashboard_path, pricing_path=pricing_path)
    updated_dashboard = dashboard_path.read_text(encoding="utf-8")
    assert "Pricing snapshot changed since the previous dashboard render" in updated_dashboard


def test_dashboard_payload_contract_includes_analysis_metadata(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    payload = dashboard_payload(db_path=db_path, pricing_path=pricing_path)
    row = payload["rows"][0]

    assert {
        "rows",
        "pricing_configured",
        "allowance_configured",
        "loaded_row_count",
        "total_available_rows",
        "parser_diagnostics",
        "parser_adapter",
        "action_thresholds",
        "project_metadata_privacy",
    } <= set(payload)
    assert {
        "record_id",
        "session_id",
        "event_timestamp",
        "cwd",
        "total_tokens",
        "cache_ratio",
        "pricing_model",
        "usage_credits",
        "recommended_action",
        "call_initiator",
        "call_initiator_reason",
        "call_initiator_confidence",
        "project_name",
        "project_key",
        "thread_attachment_label",
    } <= set(row)


def test_dashboard_payload_uses_persisted_call_origin_without_source_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    poison_source = tmp_path / "poison-source.jsonl"
    poison_source.write_text("{this is not valid json}\n" * 1000, encoding="utf-8")
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE usage_events
            SET source_file = ?
            WHERE call_initiator = 'user'
            """,
            (str(poison_source),),
        )

    original_open = Path.open

    def fail_source_open(self: Path, *args: object, **kwargs: object) -> object:
        if self == poison_source:
            raise AssertionError("dashboard_payload must not read source JSONL")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_source_open)

    payload = dashboard_payload(db_path=db_path)
    rows = payload["rows"]
    by_initiator = {row["call_initiator"]: row for row in rows}

    assert by_initiator["user"]["call_initiator_reason"] == "user_message"
    assert by_initiator["user"]["call_initiator_confidence"] == "high"


def test_dashboard_payload_and_csv_privacy_mode_redact_project_metadata(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    csv_path = tmp_path / "usage-redacted.csv"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    payload = dashboard_payload(db_path=db_path, privacy_mode="strict")
    exported = export_usage_csv(
        output_path=csv_path,
        db_path=db_path,
        privacy_mode="redacted",
    )
    csv_text = csv_path.read_text(encoding="utf-8")
    csv_header = csv_text.splitlines()[0].split(",")
    first_row = payload["rows"][0]

    assert exported == 4
    assert payload["privacy_mode"] == "strict"
    assert payload["project_metadata_privacy"]["cwd_redacted"] is True
    assert first_row["cwd"].startswith("[redacted cwd:")
    assert first_row["project_name"].startswith("Project ")
    assert first_row["project_relative_cwd"] is None
    assert first_row["git_branch"] is None
    assert first_row["git_remote_label"] is None
    assert "/tmp/codex-usage-tracker" not in json.dumps(payload)
    assert "/tmp/codex-usage-tracker" not in csv_text
    assert "[redacted cwd:" in csv_text
    assert csv_header == EVENT_COLUMNS


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

def test_dashboard_query_limit_zero_loads_all_rows(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    assert len(query_dashboard_events(db_path=db_path, limit=2)) == 2
    assert len(query_dashboard_events(db_path=db_path, limit=0)) == 4
    assert query_dashboard_event_count(db_path=db_path) == 4
