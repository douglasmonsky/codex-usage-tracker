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
    _make_codex_home,
    _token_event,
    _usage_event,
    _write_archived_log,
    _write_jsonl,
)

from codex_usage_tracker import store as store_module
from codex_usage_tracker.models import UsageEvent
from codex_usage_tracker.parser import PARSER_ADAPTER_VERSION
from codex_usage_tracker.store import (
    connect,
    init_db,
    query_dashboard_event_count,
    query_dashboard_events,
    query_latest_observed_usage,
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
from codex_usage_tracker.store_query_sql import _thread_key_expression


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
    assert meta["parser_adapter"] == PARSER_ADAPTER_VERSION
    assert meta["schema_version"] == "8"
    assert meta["parser_skipped_events"] == "0"
    state = schema_state(db_path)
    assert state["schema_version"] == 8
    assert state["checksum_matches"] is True
    assert [row["version"] for row in state["migrations"]] == [1, 2, 3, 4, 5, 6, 7, 8]
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


def test_noop_refresh_skips_parser_upsert_and_downstream_rebuilds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"

    first = refresh_usage_index(codex_home=codex_home, db_path=db_path)

    def fail_if_called(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("no-op refresh should not parse or rebuild downstream models")

    monkeypatch.setattr(
        store_module,
        "parse_usage_events_from_file_with_state",
        fail_if_called,
    )
    monkeypatch.setattr(store_module, "_upsert_usage_events_with_delta", fail_if_called)
    monkeypatch.setattr(store_module, "refresh_usage_event_links_for_threads", fail_if_called)
    monkeypatch.setattr(store_module, "rebuild_thread_summaries", fail_if_called)

    second = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    metadata = refresh_metadata(db_path)

    assert first.parsed_events == 4
    assert second.parsed_events == 0
    assert second.inserted_or_updated_events == 0
    assert second.changed_source_files == 0
    assert second.append_source_files == 0
    assert second.full_reparse_source_files == 0
    assert second.inserted_records == 0
    assert second.deleted_records == 0
    assert second.affected_threads == 0
    assert second.skipped_downstream_work is True
    assert metadata["parsed_source_files"] == "0"
    assert metadata["skipped_source_files"] == "3"


def test_latest_observed_usage_prefers_normal_codex_limit_pool(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    events = [
        _usage_event(
            record_id="normal-codex",
            session_id=SESSION_ID,
            thread_key="thread:Main allowance",
            event_timestamp="2026-06-16T10:00:00Z",
            cumulative_total_tokens=1000,
            rate_limit_plan_type="pro",
            rate_limit_limit_id="codex",
            rate_limit_primary_used_percent=3.0,
            rate_limit_primary_window_minutes=300,
            rate_limit_primary_resets_at=1781562696,
            rate_limit_secondary_used_percent=29.0,
            rate_limit_secondary_window_minutes=10080,
            rate_limit_secondary_resets_at=1781887793,
        ),
        _usage_event(
            record_id="separate-pool",
            session_id=SESSION_ID,
            thread_key="thread:Separate pool",
            event_timestamp="2026-06-16T11:00:00Z",
            cumulative_total_tokens=2000,
            rate_limit_plan_type="pro",
            rate_limit_limit_id="codex_bengalfox",
            rate_limit_primary_used_percent=0.0,
            rate_limit_primary_window_minutes=300,
            rate_limit_primary_resets_at=1781566296,
            rate_limit_secondary_used_percent=0.0,
            rate_limit_secondary_window_minutes=10080,
            rate_limit_secondary_resets_at=1781891393,
        ),
    ]
    upsert_usage_events(events, db_path=db_path)

    observed = query_latest_observed_usage(db_path=db_path)

    assert observed["record_id"] == "normal-codex"
    assert observed["limit_id"] == "codex"
    assert observed["windows"][0]["used_percent"] == 3.0
    assert observed["windows"][1]["used_percent"] == 29.0
    assert observed["reconciliation"]["recommended"] is False
    assert observed["reconciliation"]["consecutive_alternate_rows"] == 1


def test_latest_observed_usage_recommends_live_check_after_consecutive_alternate_rows(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    events = [
        _usage_event(
            record_id="normal-codex",
            session_id=SESSION_ID,
            thread_key="thread:Main allowance",
            event_timestamp="2026-06-16T10:00:00Z",
            cumulative_total_tokens=1000,
            rate_limit_plan_type="pro",
            rate_limit_limit_id="codex",
            rate_limit_primary_used_percent=3.0,
            rate_limit_primary_window_minutes=300,
            rate_limit_primary_resets_at=1781562696,
            rate_limit_secondary_used_percent=29.0,
            rate_limit_secondary_window_minutes=10080,
            rate_limit_secondary_resets_at=1781887793,
        ),
        _usage_event(
            record_id="alternate-1",
            session_id=SESSION_ID,
            thread_key="thread:Alternate allowance",
            event_timestamp="2026-06-16T11:00:00Z",
            cumulative_total_tokens=2000,
            rate_limit_plan_type=None,
            rate_limit_limit_id="codex_bengalfox",
            rate_limit_primary_used_percent=0.0,
            rate_limit_primary_window_minutes=300,
            rate_limit_primary_resets_at=1781566296,
            rate_limit_secondary_used_percent=0.0,
            rate_limit_secondary_window_minutes=10080,
            rate_limit_secondary_resets_at=1781891393,
        ),
        _usage_event(
            record_id="alternate-2",
            session_id=SESSION_ID,
            thread_key="thread:Alternate allowance",
            event_timestamp="2026-06-16T11:01:00Z",
            cumulative_total_tokens=3000,
            rate_limit_plan_type=None,
            rate_limit_limit_id="codex_bengalfox",
            rate_limit_primary_used_percent=0.0,
            rate_limit_primary_window_minutes=300,
            rate_limit_primary_resets_at=1781566296,
            rate_limit_secondary_used_percent=0.0,
            rate_limit_secondary_window_minutes=10080,
            rate_limit_secondary_resets_at=1781891393,
        ),
        _usage_event(
            record_id="alternate-3",
            session_id=SESSION_ID,
            thread_key="thread:Alternate allowance",
            event_timestamp="2026-06-16T11:02:00Z",
            cumulative_total_tokens=4000,
            rate_limit_plan_type=None,
            rate_limit_limit_id="codex_bengalfox",
            rate_limit_primary_used_percent=0.0,
            rate_limit_primary_window_minutes=300,
            rate_limit_primary_resets_at=1781566296,
            rate_limit_secondary_used_percent=0.0,
            rate_limit_secondary_window_minutes=10080,
            rate_limit_secondary_resets_at=1781891393,
        ),
    ]
    upsert_usage_events(events, db_path=db_path)

    observed = query_latest_observed_usage(db_path=db_path)

    assert observed["record_id"] == "normal-codex"
    assert observed["limit_id"] == "codex"
    assert observed["reconciliation"] == {
        "recommended": True,
        "reason": "latest_alternate_codex_limit_rows",
        "suggested_action": "live_usage_check",
        "consecutive_alternate_rows": 3,
        "threshold": 3,
        "latest_limit_id": "codex_bengalfox",
        "latest_plan_type": None,
        "latest_observed_at": "2026-06-16T11:02:00Z",
        "selected_observed_at": "2026-06-16T10:00:00Z",
        "selected_limit_id": "codex",
    }


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
    link_calls: list[set[str]] = []
    summary_calls: list[set[str] | None] = []
    original_link_refresh = store_module.refresh_usage_event_links_for_threads
    original_summary_rebuild = store_module.rebuild_thread_summaries

    def tracking_link_refresh(conn: sqlite3.Connection, thread_keys: object) -> int:
        normalized = set(thread_keys) if thread_keys is not None else set()
        link_calls.append(normalized)
        return original_link_refresh(conn, thread_keys)  # type: ignore[arg-type]

    def tracking_summary_rebuild(
        conn: sqlite3.Connection,
        *,
        thread_keys: object = None,
    ) -> int:
        normalized = set(thread_keys) if thread_keys is not None else None
        summary_calls.append(normalized)
        return original_summary_rebuild(conn, thread_keys=thread_keys)  # type: ignore[arg-type]

    monkeypatch.setattr(store_module, "refresh_usage_event_links_for_threads", tracking_link_refresh)
    monkeypatch.setattr(store_module, "rebuild_thread_summaries", tracking_summary_rebuild)

    second = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    partial_link_calls = list(link_calls)
    partial_summary_calls = list(summary_calls)
    affected_keys = link_calls[0] if link_calls else set()
    before_full_repair_links = _thread_link_snapshot(db_path, affected_keys)
    before_full_repair_summaries = _thread_summary_snapshot(db_path, affected_keys)
    store_module.refresh_usage_event_links(db_path)
    after_full_repair_links = _thread_link_snapshot(db_path, affected_keys)
    after_full_repair_summaries = _thread_summary_snapshot(db_path, affected_keys)
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
    assert second.changed_source_files == 1
    assert second.append_source_files == 1
    assert second.full_reparse_source_files == 0
    assert second.inserted_records == 1
    assert second.deleted_records == 0
    assert second.affected_threads == 1
    assert second.skipped_downstream_work is False
    assert partial_link_calls == [{"thread:Add Codex token tracking"}]
    assert partial_summary_calls == [{"thread:Add Codex token tracking"}]
    assert before_full_repair_links == after_full_repair_links
    assert before_full_repair_summaries == after_full_repair_summaries
    assert third.parsed_events == 0
    assert third.skipped_downstream_work is True
    assert [row["cumulative_total_tokens"] for row in rows] == [100, 300, 650]
    assert metadata["parsed_source_files"] == "0"
    assert metadata["skipped_source_files"] == "3"


def test_refresh_replaces_source_when_parser_adapter_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    log_path = next(
        path for path in (codex_home / "sessions").glob("**/*.jsonl") if SESSION_ID in path.name
    )

    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    with connect(db_path) as conn:
        init_db(conn)
        conn.execute(
            "UPDATE source_files SET parser_adapter = ? WHERE source_file = ?",
            ("codex-jsonl-v1", str(log_path)),
        )

    parse_calls: list[dict[str, Any]] = []
    original_parse = store_module.parse_usage_events_from_file_with_state

    def tracking_parse(*args: Any, **kwargs: Any):
        parse_calls.append(
            {
                "path": args[0],
                "start_byte": kwargs.get("start_byte"),
                "start_line": kwargs.get("start_line"),
            }
        )
        return original_parse(*args, **kwargs)

    monkeypatch.setattr(
        store_module,
        "parse_usage_events_from_file_with_state",
        tracking_parse,
    )
    result = refresh_usage_index(codex_home=codex_home, db_path=db_path)

    assert result.parsed_events == 2
    assert len(parse_calls) == 1
    assert parse_calls[0]["path"] == log_path
    assert parse_calls[0]["start_byte"] == 0
    assert parse_calls[0]["start_line"] == 0
    with connect(db_path) as conn:
        init_db(conn)
        source_after = conn.execute(
            "SELECT parser_adapter FROM source_files WHERE source_file = ?",
            (str(log_path),),
        ).fetchone()
    assert source_after["parser_adapter"] == PARSER_ADAPTER_VERSION


def test_full_reparse_invalidates_old_and_new_thread_summaries(tmp_path: Path) -> None:
    session_id = "019e37d5-f19f-7e4d-84cb-50894143c002"
    codex_home = tmp_path / ".codex"
    log_path = (
        codex_home
        / "sessions"
        / "2026"
        / "05"
        / "17"
        / f"rollout-2026-05-17T19-00-00-{session_id}.jsonl"
    )
    _write_jsonl(
        codex_home / "session_index.jsonl",
        [
            {
                "id": session_id,
                "thread_name": "Original thread",
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
        ],
    )
    db_path = tmp_path / "usage.sqlite3"

    first = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    _write_jsonl(
        codex_home / "session_index.jsonl",
        [
            {
                "id": session_id,
                "thread_name": "Replacement thread",
                "updated_at": "2026-05-17T19:05:00Z",
            }
        ],
    )
    with connect(db_path) as conn:
        init_db(conn)
        conn.execute(
            "UPDATE source_files SET parser_adapter = ? WHERE source_file = ?",
            ("codex-jsonl-v1", str(log_path)),
        )

    second = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    summaries = query_thread_summaries(db_path=db_path, limit=0)
    summary_keys = {row["thread_key"] for row in summaries}

    assert first.parsed_events == 1
    assert second.parsed_events == 1
    assert second.changed_source_files == 1
    assert second.append_source_files == 0
    assert second.full_reparse_source_files == 1
    assert second.inserted_records == 1
    assert second.deleted_records == 1
    assert second.affected_threads == 2
    assert second.skipped_downstream_work is False
    assert "thread:Original thread" not in summary_keys
    assert "thread:Replacement thread" in summary_keys


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
    assert user_version == 8


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
    assert "idx_usage_observed_rate_limit_timestamp" in indexes
    assert user_version == 8
    assert [row["version"] for row in migrations] == [1, 2, 3, 4, 5, 6, 7, 8]


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


def _thread_link_snapshot(db_path: Path, thread_keys: set[str]) -> list[dict[str, object]]:
    if not thread_keys:
        return []
    placeholders = ", ".join("?" for _key in thread_keys)
    thread_key_expr = _thread_key_expression()
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            f"""
            SELECT record_id, thread_call_index, previous_record_id, next_record_id
            FROM usage_events
            WHERE {thread_key_expr} IN ({placeholders})
            ORDER BY record_id
            """,
            sorted(thread_keys),
        ).fetchall()
    return [dict(row) for row in rows]


def _thread_summary_snapshot(db_path: Path, thread_keys: set[str]) -> list[dict[str, object]]:
    if not thread_keys:
        return []
    placeholders = ", ".join("?" for _key in thread_keys)
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            f"""
            SELECT
                thread_key,
                is_archived_scope,
                thread_label,
                first_event_timestamp,
                latest_event_timestamp,
                call_count,
                session_count,
                input_tokens,
                cached_input_tokens,
                uncached_input_tokens,
                output_tokens,
                reasoning_output_tokens,
                total_tokens,
                avg_cache_ratio,
                max_context_window_percent,
                max_recommendation_score,
                primary_recommendation,
                call_initiator_summary,
                archived_call_count
            FROM thread_summaries
            WHERE thread_key IN ({placeholders})
            ORDER BY thread_key, is_archived_scope
            """,
            sorted(thread_keys),
        ).fetchall()
    return [dict(row) for row in rows]


def test_dashboard_query_limit_zero_loads_all_rows(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    assert len(query_dashboard_events(db_path=db_path, limit=2)) == 2
    assert len(query_dashboard_events(db_path=db_path, limit=0)) == 4
    assert query_dashboard_event_count(db_path=db_path) == 4
