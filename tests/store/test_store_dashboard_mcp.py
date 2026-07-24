from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

import codex_usage_tracker.store.usage_event_writer as usage_event_writer
from codex_usage_tracker import store as store_module
from codex_usage_tracker.diagnostics.reports import build_diagnostics_facts_report
from codex_usage_tracker.store.api import (
    connect,
    init_db,
    query_dashboard_event_count,
    query_diagnostic_facts,
    query_latest_observed_usage,
    query_most_expensive_calls,
    query_session_usage,
    query_summary,
    rebuild_usage_index,
    refresh_metadata,
    refresh_usage_index,
    schema_state,
    upsert_usage_events,
)
from tests.store_dashboard_helpers import (
    SECOND_SESSION_ID,
    SESSION_ID,
    _entry,
    _make_codex_home,
    _token_event,
    _usage_event,
    _write_archived_log,
    _write_jsonl,
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
        allowance_cycle_count = conn.execute("SELECT COUNT(*) FROM allowance_cycles").fetchone()[0]
        allowance_source_state_count = conn.execute(
            "SELECT COUNT(*) FROM allowance_source_state"
        ).fetchone()[0]
    assert meta["parsed_events"] == "0"
    assert meta["skipped_events"] == "0"
    assert meta["inserted_or_updated_events"] == "0"
    assert meta["parsed_source_files"] == "0"
    assert meta["skipped_source_files"] == "3"
    assert meta["parser_adapter"] == "codex-jsonl-v2"
    assert meta["schema_version"] == "34"
    assert meta["parser_skipped_events"] == "0"
    assert allowance_cycle_count > 0
    assert allowance_source_state_count == 1
    state = schema_state(db_path)
    assert state["schema_version"] == 34
    assert state["checksum_matches"] is True
    assert [row["version"] for row in state["migrations"]] == list(range(1, 35))
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


def test_summary_can_exclude_archived_usage(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    _write_archived_log(codex_home)
    db_path = tmp_path / "usage.sqlite3"

    refresh_usage_index(codex_home=codex_home, db_path=db_path, include_archived=True)

    active_rows = query_summary(
        db_path=db_path,
        group_by="model",
        include_archived=False,
    )
    all_rows = query_summary(
        db_path=db_path,
        group_by="model",
        limit=0,
        include_archived=True,
    )
    all_expensive = query_most_expensive_calls(
        db_path=db_path,
        limit=0,
        include_archived=True,
    )

    assert sum(int(row["model_calls"]) for row in active_rows) == 4
    assert sum(int(row["model_calls"]) for row in all_rows) == 5
    assert sum(int(row["total_tokens"]) for row in active_rows) == 400
    assert sum(int(row["total_tokens"]) for row in all_rows) == 1_300
    assert len(all_expensive) == 5


def test_refresh_reports_skipped_corrupt_token_events(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    log_path = next(
        path for path in (codex_home / "sessions").glob("**/*.jsonl") if SESSION_ID in path.name
    )
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
        source_before_row = conn.execute(
            """
            SELECT parsed_until_byte, parsed_until_line, parser_state_json
            FROM source_files
            WHERE source_file = ?
            """,
            (str(log_path),),
        ).fetchone()
        assert source_before_row is not None
        source_before = dict(source_before_row)
    target_thread_key = query_session_usage(
        db_path=db_path,
        session_id=SESSION_ID,
    )[0]["thread_key"]
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_token_event(650, 350)) + "\n")
    parse_calls: list[dict[str, Any]] = []
    original_parse = store_module.parse_usage_events_from_file_with_state
    link_scopes: list[set[str]] = []
    original_refresh_links = usage_event_writer._refresh_usage_event_links_for_threads
    summary_scopes: list[set[str]] = []
    original_rebuild_summaries = usage_event_writer.rebuild_thread_summaries

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

    def tracking_refresh_links(*args: Any, **kwargs: Any) -> int:
        link_scopes.append(set(args[1]))
        return original_refresh_links(*args, **kwargs)

    def tracking_rebuild_summaries(*args: Any, **kwargs: Any) -> int:
        summary_scopes.append(set(kwargs.get("thread_keys") or []))
        return original_rebuild_summaries(*args, **kwargs)

    monkeypatch.setattr(
        store_module,
        "parse_usage_events_from_file_with_state",
        tracking_parse,
    )
    monkeypatch.setattr(
        usage_event_writer,
        "_refresh_usage_event_links_for_threads",
        tracking_refresh_links,
    )
    monkeypatch.setattr(
        usage_event_writer,
        "rebuild_thread_summaries",
        tracking_rebuild_summaries,
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
    assert link_scopes == [{target_thread_key}]
    assert summary_scopes == [{target_thread_key}]
    assert [row["cumulative_total_tokens"] for row in rows] == [100, 300, 650]
    assert metadata["parsed_source_files"] == "0"
    assert metadata["skipped_source_files"] == "3"


def test_refresh_reparses_source_when_parser_adapter_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = "019e37d5-f19f-7e4d-84cb-50894143c000"
    codex_home = tmp_path / ".codex"
    db_path = tmp_path / "usage.sqlite3"
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
                "thread_name": "Parser adapter diagnostics",
                "updated_at": "2026-05-17T19:00:00Z",
            }
        ],
    )
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": session_id}),
            _entry("turn_context", {"turn_id": "turn-a", "model": "gpt-5.5"}),
            _entry("event_msg", {"type": "patch_apply_end", "patch": "SECRET PATCH"}),
            _token_event(100, 100),
        ],
    )
    first = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    with connect(db_path) as conn:
        init_db(conn)
        source_before = conn.execute(
            """
            SELECT parsed_until_byte, parser_adapter
            FROM source_files
            WHERE source_file = ?
            """,
            (str(log_path),),
        ).fetchone()
        conn.execute("DELETE FROM call_diagnostic_facts")
        conn.execute(
            "UPDATE source_files SET parser_adapter = ? WHERE source_file = ?",
            ("codex-jsonl-v0", str(log_path)),
        )
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
    facts = query_diagnostic_facts(db_path=db_path, limit=0)

    assert first.parsed_events == 1
    assert source_before is not None
    assert source_before["parsed_until_byte"] > 0
    assert source_before["parser_adapter"] == "codex-jsonl-v2"
    assert len(parse_calls) == 1
    assert parse_calls[0] == {
        "path": log_path,
        "start_byte": 0,
        "start_line": 0,
        "initial_state": None,
    }
    assert second.parsed_events == 1
    assert second.inserted_or_updated_events == 1
    assert [row["fact_name"] for row in facts] == ["patch_applied"]
    assert "SECRET PATCH" not in json.dumps(facts)


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


def test_append_cursor_preserves_pending_diagnostic_facts_between_refreshes(
    tmp_path: Path,
) -> None:
    session_id = "019e37d5-f19f-7e4d-84cb-50894143c002"
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
                "thread_name": "Append cursor diagnostics",
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
                    "type": "function_call_output",
                    "output": "SECRET PENDING TOOL OUTPUT",
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
    facts = query_diagnostic_facts(db_path=db_path, limit=0)
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
    assert len(facts) == 1
    assert facts[0]["fact_name"] == "function_call_output"
    assert facts[0]["associated_total_tokens"] == 50
    assert facts[0]["largest_record_id"] == rows[-1]["record_id"]
    assert facts[0]["raw_content_included"] == 0
    assert "SECRET PENDING TOOL OUTPUT" not in source_rows_text
    assert "SECRET PENDING TOOL OUTPUT" not in json.dumps(facts)


def test_refresh_persists_diagnostic_facts_without_raw_content(tmp_path: Path) -> None:
    session_id = "019e37d5-f19f-7e4d-84cb-50894143c003"
    codex_home = tmp_path / ".codex"
    db_path = tmp_path / "usage.sqlite3"
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
                "thread_name": "Diagnostic facts",
                "updated_at": "2026-05-17T19:00:00Z",
            }
        ],
    )
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": session_id}),
            _entry("turn_context", {"turn_id": "turn-a", "model": "gpt-5.5"}),
            _entry(
                "response_item",
                {"type": "function_call_output", "output": "SECRET TOOL OUTPUT"},
            ),
            _entry(
                "event_msg",
                {"type": "patch_apply_end", "patch": "SECRET PATCH TEXT"},
            ),
            _token_event(120, 120),
            _entry(
                "event_msg",
                {
                    "type": "context_compacted",
                    "replacement_history": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "SECRET COMPACTION TEXT"}],
                        }
                    ],
                },
            ),
            _token_event(200, 80),
        ],
    )

    result = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    facts = query_diagnostic_facts(db_path=db_path, limit=0, sort="fact", direction="asc")
    with connect(db_path) as conn:
        init_db(conn)
        persisted = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM call_diagnostic_facts ORDER BY fact_type, fact_name"
            ).fetchall()
        ]

    by_name = {row["fact_name"]: row for row in facts}
    assert result.parsed_events == 2
    assert set(by_name) == {"function_call_output", "patch_applied", "post_compaction"}
    assert by_name["function_call_output"]["associated_total_tokens"] == 120
    assert by_name["patch_applied"]["associated_total_tokens"] == 120
    assert by_name["post_compaction"]["associated_total_tokens"] == 80
    assert all(row["raw_content_included"] == 0 for row in persisted)
    assert "SECRET" not in json.dumps(persisted, sort_keys=True)
    assert "SECRET" not in json.dumps(facts, sort_keys=True)


def test_refresh_persists_richer_diagnostic_detectors_without_command_text(
    tmp_path: Path,
) -> None:
    session_id = "019e37d5-f19f-7e4d-84cb-50894143c005"
    codex_home = tmp_path / ".codex"
    db_path = tmp_path / "usage.sqlite3"
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
                "thread_name": "Diagnostic detectors",
                "updated_at": "2026-05-17T19:00:00Z",
            }
        ],
    )
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": session_id}),
            _entry("turn_context", {"turn_id": "turn-a", "model": "gpt-5.5"}),
            _entry(
                "response_item",
                {
                    "type": "function_call",
                    "name": "functions.exec_command",
                    "arguments": json.dumps(
                        {"cmd": "python -m pytest tests/test_secret_customer.py"}
                    ),
                },
            ),
            _entry(
                "event_msg",
                {
                    "type": "mcp_tool_call_end",
                    "tool_name": "mcp__calendar__search_events",
                    "server_name": "google-calendar",
                    "arguments": {"calendar": "SECRET CALENDAR"},
                },
            ),
            _entry("event_msg", {"type": "skill_started", "skill_name": "brooks-test"}),
            _token_event(120, 120),
        ],
    )

    result = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    facts = query_diagnostic_facts(db_path=db_path, limit=0, sort="fact", direction="asc")
    tools_payload = build_diagnostics_facts_report(
        db_path=db_path,
        fact_group="tools",
        view="tools",
    ).payload

    by_key = {(row["fact_type"], row["fact_name"]): row for row in facts}
    tool_types = {row["fact_type"] for row in tools_payload["rows"]}
    assert result.parsed_events == 1
    assert {"command_family", "function", "mcp_server", "mcp_tool", "skill", "tool"} <= tool_types
    assert tools_payload["filters"]["fact_group"] == "tools"
    assert by_key[("command_family", "pytest")]["associated_total_tokens"] == 120
    assert by_key[("function", "functions.exec_command")]["associated_total_tokens"] == 120
    assert by_key[("mcp_tool", "mcp__calendar__search_events")]["associated_total_tokens"] == 120
    assert by_key[("mcp_server", "google-calendar")]["associated_total_tokens"] == 120
    assert by_key[("skill", "brooks-test")]["associated_total_tokens"] == 120
    serialized = json.dumps(facts, sort_keys=True)
    assert "SECRET" not in serialized
    assert "test_secret_customer" not in serialized
    assert "python -m pytest" not in serialized


def test_full_reparse_replaces_stale_diagnostic_facts(tmp_path: Path) -> None:
    session_id = "019e37d5-f19f-7e4d-84cb-50894143c004"
    codex_home = tmp_path / ".codex"
    db_path = tmp_path / "usage.sqlite3"
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
                "thread_name": "Diagnostic facts replace",
                "updated_at": "2026-05-17T19:00:00Z",
            }
        ],
    )
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": session_id}),
            _entry("turn_context", {"turn_id": "turn-a", "model": "gpt-5.5"}),
            _entry("event_msg", {"type": "patch_apply_end", "patch": "SECRET PATCH"}),
            _token_event(100, 100),
        ],
    )
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    assert [row["fact_name"] for row in query_diagnostic_facts(db_path=db_path)] == [
        "patch_applied"
    ]

    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": session_id}),
            _entry("turn_context", {"turn_id": "turn-a", "model": "gpt-5.5"}),
            _token_event(100, 100),
        ],
    )
    with connect(db_path) as conn:
        init_db(conn)
        conn.execute(
            """
            UPDATE source_files
            SET size_bytes = ?, mtime_ns = 0
            WHERE source_file = ?
            """,
            (999_999, str(log_path)),
        )

    second = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    with connect(db_path) as conn:
        init_db(conn)
        persisted_count = conn.execute(
            "SELECT COUNT(*) AS count FROM call_diagnostic_facts"
        ).fetchone()

    assert second.parsed_events == 1
    assert query_diagnostic_facts(db_path=db_path) == []
    assert persisted_count is not None
    assert persisted_count["count"] == 0


def test_connect_sets_sqlite_concurrency_pragmas(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    with connect(db_path) as conn:
        init_db(conn)
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]

    assert busy_timeout == 5000
    assert str(journal_mode).lower() == "wal"
    assert user_version == 34


def test_current_schema_reads_succeed_while_writer_is_active(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    with connect(db_path) as conn:
        init_db(conn)

    writer = sqlite3.connect(db_path, timeout=0.1)
    try:
        writer.execute("BEGIN IMMEDIATE")
        with connect(db_path) as reader:
            init_db(reader)
            assert reader.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 0
    finally:
        writer.rollback()
        writer.close()


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
            row["name"] for row in conn.execute("PRAGMA table_info(usage_events)").fetchall()
        }
        indexes = {
            row["name"] for row in conn.execute("PRAGMA index_list(usage_events)").fetchall()
        }
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        migrations = [
            dict(row)
            for row in conn.execute(
                "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
            ).fetchall()
        ]
        allowance_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(allowance_observations)").fetchall()
        }
        allowance_indexes = {
            row["name"]
            for row in conn.execute("PRAGMA index_list(allowance_observations)").fetchall()
        }

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
    assert "rate_limit_plan_type" in columns
    assert "rate_limit_primary_used_percent" in columns
    assert "idx_usage_observed_rate_limit_timestamp" in indexes
    assert "used_percent" in allowance_columns
    assert "window_kind" in allowance_columns
    assert "idx_allowance_observations_window_time" in allowance_indexes
    assert user_version == 34
    assert [row["version"] for row in migrations] == list(range(1, 35))
    assert "idx_usage_source_file_line" in indexes


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
    assert observed["source"] == "token_count.rate_limits"
    assert observed["windows"][0]["label"] == "5h"
    assert observed["windows"][0]["used_percent"] == 3.0
    assert observed["windows"][1]["label"] == "Weekly"
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
        *[
            _usage_event(
                record_id=f"alternate-{index}",
                session_id=SESSION_ID,
                thread_key="thread:Alternate allowance",
                event_timestamp=f"2026-06-16T11:0{index}:00Z",
                cumulative_total_tokens=2000 + index,
                rate_limit_limit_id="codex_bengalfox",
                rate_limit_primary_used_percent=0.0,
                rate_limit_primary_window_minutes=300,
                rate_limit_primary_resets_at=1781566296,
                rate_limit_secondary_used_percent=0.0,
                rate_limit_secondary_window_minutes=10080,
                rate_limit_secondary_resets_at=1781891393,
            )
            for index in range(1, 4)
        ],
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
        "latest_observed_at": "2026-06-16T11:03:00Z",
        "selected_observed_at": "2026-06-16T10:00:00Z",
        "selected_limit_id": "codex",
    }


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
    with connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM allowance_cycles").fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM allowance_source_state").fetchone()[0] == 1
