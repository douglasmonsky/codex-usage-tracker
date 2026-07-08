from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.core.json_contracts import validate_json_payload_contract
from codex_usage_tracker.reports.api import (
    build_content_search_report,
    build_investigation_walk_report,
    build_large_low_output_report,
    build_local_evidence_export_report,
    build_pattern_scan_report,
    build_repeated_file_rediscovery_report,
    build_shell_churn_report,
    build_thread_trace_report,
)
from codex_usage_tracker.store.api import connect, init_db, refresh_usage_index
from tests.store_dashboard_helpers import _entry, _make_codex_home, _token_event, _write_jsonl


def test_refresh_populates_normalized_content_index_by_default(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"

    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    with connect(db_path) as conn:
        init_db(conn)
        turn_count = conn.execute("SELECT COUNT(*) FROM conversation_turns").fetchone()
        fragment_rows = conn.execute(
            """
            SELECT fragment_kind, role, safe_label, fragment_text, includes_raw_fragment
            FROM content_fragments
            ORDER BY line_start, safe_label
            """
        ).fetchall()

    assert turn_count is not None
    assert turn_count[0] >= 1
    assert any("SECRET RAW PROMPT" in row["fragment_text"] for row in fragment_rows)
    assert any("AFTER SELECTED CALL" in row["fragment_text"] for row in fragment_rows)
    assert any(row["fragment_kind"] == "reasoning_summary" for row in fragment_rows)
    assert all(row["includes_raw_fragment"] == 1 for row in fragment_rows)
    assert all("SECRET RAW PROMPT" not in row["safe_label"] for row in fragment_rows)


def test_refresh_populates_normalized_local_event_tables(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    session_id = "019e37f1-15d4-76a5-bf68-9d7616f9b8db"
    log_path = (
        codex_home / "sessions" / "2026" / "05" / "18" / f"rollout-2026-05-18T09-00-00-{session_id}.jsonl"
    )
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": session_id}),
            _entry("turn_context", {"turn_id": "turn-tools", "model": "gpt-5.5"}),
            _entry(
                "response_item",
                {
                    "type": "function_call",
                    "call_id": "call-read",
                    "name": "exec_command",
                    "arguments": json.dumps({"cmd": "cat docs/private_notes.md"}),
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "function_call_output",
                    "call_id": "call-read",
                    "output": (
                        "Chunk ID: abc123\n"
                        "Wall time: 0.0000 seconds\n"
                        "Process exited with code 0\n"
                        "Original token count: 12\n"
                        "Output:\n"
                        "SECRET FILE CONTENT"
                    ),
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "function_call",
                    "call_id": "call-patch",
                    "name": "apply_patch",
                    "input": (
                        "*** Begin Patch\n"
                        "*** Update File: src/app.py\n"
                        "@@\n"
                        "-old\n"
                        "+new\n"
                        "*** End Patch\n"
                    ),
                },
            ),
            _token_event(420, 120),
        ],
    )

    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    with connect(db_path) as conn:
        init_db(conn)
        tool_rows = conn.execute(
            """
            SELECT tool_name, call_id, status, argument_shape, output_size_bytes, line_start, line_end
            FROM tool_calls
            ORDER BY call_id
            """
        ).fetchall()
        command_rows = conn.execute(
            """
            SELECT command_root, command_label, status, exit_code, output_size_bytes, line_start, line_end
            FROM command_runs
            """
        ).fetchall()
        file_rows = conn.execute(
            """
            SELECT operation, path_basename, path_extension, path_identity
            FROM file_events
            ORDER BY operation, path_basename
            """
        ).fetchall()

    read_tool = next(row for row in tool_rows if row["call_id"] == "call-read")
    assert read_tool["tool_name"] == "exec_command"
    assert read_tool["status"] == "completed"
    assert read_tool["argument_shape"] == '{"cmd":"str"}'
    assert read_tool["output_size_bytes"] > 0
    assert read_tool["line_start"] < read_tool["line_end"]
    assert all("docs/private_notes.md" not in row["argument_shape"] for row in tool_rows)

    assert len(command_rows) == 1
    assert command_rows[0]["command_root"] == "cat"
    assert command_rows[0]["command_label"] == "cat"
    assert command_rows[0]["status"] == "completed"
    assert command_rows[0]["exit_code"] == 0
    assert command_rows[0]["output_size_bytes"] > 0

    assert {row["operation"] for row in file_rows} == {"modify", "read"}
    assert {row["path_basename"] for row in file_rows} == {"app.py", "private_notes.md"}
    assert all("/" not in row["path_basename"] for row in file_rows)
    assert all(row["path_identity"] == row["path_identity"][:12] for row in file_rows)

    command_scan = build_pattern_scan_report(
        db_path=db_path,
        scan_type="command_loop",
        min_occurrences=1,
    ).payload
    file_scan = build_pattern_scan_report(
        db_path=db_path,
        scan_type="file_churn",
        min_occurrences=1,
    ).payload
    context_scan = build_pattern_scan_report(
        db_path=db_path,
        scan_type="context_bloat",
        min_occurrences=1,
    ).payload

    for payload in (command_scan, file_scan, context_scan):
        assert validate_json_payload_contract(payload) == []
        assert payload["schema"] == "codex-usage-tracker-pattern-scan-v1"
        assert payload["content_mode"] == "local_content_index"
        assert payload["includes_indexed_content"] is True
        assert payload["includes_raw_fragments"] is False
        assert payload["pattern_count"] >= 1

    assert command_scan["patterns"][0]["details"]["command_root"] == "cat"
    assert {row["details"]["path_basename"] for row in file_scan["patterns"]} >= {
        "app.py",
        "private_notes.md",
    }
    assert context_scan["patterns"][0]["details"]["fragment_count"] >= 1

    walk = build_investigation_walk_report(
        db_path=db_path,
        question="Look for local token waste patterns",
        min_occurrences=1,
    ).payload
    assert validate_json_payload_contract(walk) == []
    assert walk["schema"] == "codex-usage-tracker-investigation-walk-v1"
    assert walk["content_mode"] == "local_content_index"
    assert walk["includes_indexed_content"] is True
    assert walk["includes_raw_fragments"] is False
    assert walk["summary"]["supported_branch_count"] >= 1
    assert walk["branches"][0]["evidence_count"] >= 1
    assert walk["recommended_next_tools"]

    export = build_local_evidence_export_report(
        db_path=db_path,
        question="Share local token waste evidence",
        min_occurrences=1,
    ).payload
    assert validate_json_payload_contract(export) == []
    assert export["schema"] == "codex-usage-tracker-local-evidence-export-v1"
    assert export["content_mode"] == "shareable_local_evidence"
    assert export["includes_indexed_content"] is False
    assert export["includes_raw_fragments"] is False
    assert export["privacy_mode"] == "strict"
    serialized_export = json.dumps(export)
    for forbidden in _private_export_sentinels():
        assert forbidden not in serialized_export
    with connect(db_path) as conn:
        init_db(conn)
        run_rows = conn.execute(
            """
            SELECT run_kind, payload_schema, content_mode, includes_raw_fragments, summary_json
            FROM investigation_runs
            ORDER BY created_at, run_kind
            """
        ).fetchall()
    assert {row["run_kind"] for row in run_rows} >= {
        "investigation_walk",
        "local_evidence_export",
    }
    assert all(row["includes_raw_fragments"] == 0 for row in run_rows)
    serialized_runs = json.dumps([dict(row) for row in run_rows])
    for forbidden in _private_export_sentinels():
        assert forbidden not in serialized_runs


def test_refresh_aggregate_only_skips_content_index(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"

    refresh_usage_index(codex_home=codex_home, db_path=db_path, aggregate_only=True)

    with connect(db_path) as conn:
        init_db(conn)
        usage_count = conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()
        fragment_count = conn.execute("SELECT COUNT(*) FROM content_fragments").fetchone()
        tool_count = conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()
        command_count = conn.execute("SELECT COUNT(*) FROM command_runs").fetchone()
        file_count = conn.execute("SELECT COUNT(*) FROM file_events").fetchone()

    assert usage_count is not None
    assert fragment_count is not None
    assert tool_count is not None
    assert command_count is not None
    assert file_count is not None
    assert usage_count[0] > 0
    assert fragment_count[0] == 0
    assert tool_count[0] == 0
    assert command_count[0] == 0
    assert file_count[0] == 0


def test_content_search_returns_explicit_local_snippets(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    payload = build_content_search_report(
        db_path=db_path,
        query="SECRET RAW PROMPT",
        limit=1,
        max_snippet_chars=32,
    ).payload

    assert validate_json_payload_contract(payload) == []
    assert payload["schema"] == "codex-usage-tracker-content-search-v1"
    assert payload["content_mode"] == "local_content_index"
    assert payload["includes_indexed_content"] is True
    assert payload["includes_raw_fragments"] is True
    assert payload["row_count"] == 1
    assert payload["total_matched_rows"] >= 1
    assert payload["rows"][0]["includes_raw_fragment"] is True
    assert "SECRET" in payload["rows"][0]["snippet"]
    assert payload["rows"][0]["snippet_truncated"] is True


def test_repeated_file_rediscovery_ranks_safe_path_hashes(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    session_id = "019e3911-c0de-7777-8afe-111111111111"
    log_path = (
        codex_home
        / "sessions"
        / "2026"
        / "05"
        / "19"
        / f"rollout-2026-05-19T10-00-00-{session_id}.jsonl"
    )
    rows: list[dict[str, object]] = [_entry("session_meta", {"id": session_id})]
    for index, path in enumerate(
        [
            "docs/repeated_notes.md",
            "docs/repeated_notes.md",
            "docs/repeated_notes.md",
            "docs/unrelated_notes.md",
        ],
        start=1,
    ):
        rows.extend(
            [
                _entry("turn_context", {"turn_id": f"turn-{index}", "model": "gpt-5.5"}),
                _entry(
                    "response_item",
                    {
                        "type": "function_call",
                        "call_id": f"call-read-{index}",
                        "name": "exec_command",
                        "arguments": json.dumps({"cmd": f"cat {path}"}),
                    },
                ),
                _entry(
                    "response_item",
                    {
                        "type": "function_call_output",
                        "call_id": f"call-read-{index}",
                        "output": (
                            "Chunk ID: abc123\n"
                            "Wall time: 0.0000 seconds\n"
                            "Process exited with code 0\n"
                            "Original token count: 4\n"
                            "Output:\n"
                            "safe synthetic output"
                        ),
                    },
                ),
                _token_event(500 + index * 100, 100 + index * 10),
            ]
        )
    _write_jsonl(log_path, rows)

    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    payload = build_repeated_file_rediscovery_report(
        db_path=db_path,
        min_occurrences=2,
        limit=5,
    ).payload

    assert validate_json_payload_contract(payload) == []
    assert payload["schema"] == "codex-usage-tracker-repeated-file-rediscovery-v1"
    assert payload["content_mode"] == "local_content_index"
    assert payload["includes_indexed_content"] is True
    assert payload["includes_raw_fragments"] is False
    assert payload["row_count"] == 1
    top = payload["rows"][0]
    assert top["path_basename"] == "repeated_notes.md"
    assert top["path_extension"] == ".md"
    assert top["candidate_kind"] == "repeated_read_rediscovery"
    assert top["operation_mix"]["read"] == 3
    assert top["call_count"] == 3
    assert "repeated_notes.md" in top["recommendation"]
    assert "3 reads" in top["recommendation"]
    assert top["trace_handles"][0]["next_tool"] == "usage_thread_trace"
    serialized = json.dumps(payload)
    assert "docs/repeated_notes.md" not in serialized
    assert "docs/unrelated_notes.md" not in serialized


def test_shell_churn_detects_repeated_command_families(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    session_id = "019e3911-c0de-7777-8afe-222222222222"
    log_path = (
        codex_home
        / "sessions"
        / "2026"
        / "05"
        / "19"
        / f"rollout-2026-05-19T11-00-00-{session_id}.jsonl"
    )
    commands = [
        ("sed -n '1,20p' src/app.py", 0),
        ("sed -n '21,40p' src/app.py", 0),
        ("sed -n '41,60p' src/app.py", 0),
        ("rg TODO src", 1),
        ("rg TODO tests", 1),
        ("git status --short", 0),
        ("git diff --stat", 0),
        ("nl -ba src/app.py", 0),
        ("nl -ba tests/test_app.py", 0),
        ("echo one-off", 0),
    ]
    rows: list[dict[str, object]] = [_entry("session_meta", {"id": session_id})]
    for index, (command, exit_code) in enumerate(commands, start=1):
        rows.extend(
            [
                _entry("turn_context", {"turn_id": f"turn-{index}", "model": "gpt-5.5"}),
                _entry(
                    "response_item",
                    {
                        "type": "function_call",
                        "call_id": f"call-shell-{index}",
                        "name": "exec_command",
                        "arguments": json.dumps({"cmd": command}),
                    },
                ),
                _entry(
                    "response_item",
                    {
                        "type": "function_call_output",
                        "call_id": f"call-shell-{index}",
                        "output": (
                            "Chunk ID: abc123\n"
                            "Wall time: 0.0000 seconds\n"
                            f"Process exited with code {exit_code}\n"
                            "Original token count: 4\n"
                            "Output:\n"
                            "safe synthetic output"
                        ),
                    },
                ),
                _token_event(800 + index * 100, 100 + index * 10),
            ]
        )
    _write_jsonl(log_path, rows)

    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    payload = build_shell_churn_report(
        db_path=db_path,
        min_occurrences=2,
        limit=10,
    ).payload

    assert validate_json_payload_contract(payload) == []
    assert payload["schema"] == "codex-usage-tracker-shell-churn-v1"
    assert payload["content_mode"] == "local_content_index"
    assert payload["includes_raw_fragments"] is False
    roots = {row["command_root"]: row for row in payload["rows"]}
    assert {"sed", "rg", "git", "nl"} <= set(roots)
    assert "echo" not in roots
    assert roots["sed"]["churn_kind"] == "successful_loop_churn"
    assert roots["sed"]["success_count"] == 3
    assert roots["sed"]["adjacent_root_repeat_count"] >= 2
    assert roots["rg"]["churn_kind"] == "failure_retry_churn"
    assert roots["rg"]["failure_count"] == 2
    assert roots["rg"]["top_labels"][0]["exit_code"] == 1
    assert roots["sed"]["trace_handles"][0]["next_tool"] == "usage_thread_trace"
    serialized = json.dumps(payload)
    assert "src/app.py" not in serialized
    assert "safe synthetic output" not in serialized


def test_thread_trace_returns_calls_with_indexed_fragments(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    payload = build_thread_trace_report(
        db_path=db_path,
        thread="Add Codex token tracking",
        limit=5,
        max_snippet_chars=64,
    ).payload

    assert validate_json_payload_contract(payload) == []
    assert payload["schema"] == "codex-usage-tracker-thread-trace-v1"
    assert payload["content_mode"] == "local_content_index"
    assert payload["includes_indexed_content"] is True
    assert payload["includes_raw_fragments"] is True
    assert payload["call_count"] >= 1
    assert payload["total_matched_calls"] >= payload["call_count"]
    assert any(call["fragment_count"] > 0 for call in payload["calls"])
    assert any(
        "SECRET" in fragment["snippet"]
        for call in payload["calls"]
        for fragment in call["fragments"]
    )


def test_large_low_output_calls_flags_cold_resume_candidates(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    session_id = "019e3911-c0de-7777-8afe-333333333333"
    log_path = (
        codex_home
        / "sessions"
        / "2026"
        / "05"
        / "20"
        / f"rollout-2026-05-20T10-00-00-{session_id}.jsonl"
    )
    rows = [
        _entry("session_meta", {"id": session_id}),
        _entry("turn_context", {"turn_id": "turn-cold", "model": "gpt-5.5"}),
        _entry(
            "response_item",
            {
                "type": "function_call",
                "call_id": "call-cold-rg",
                "name": "exec_command",
                "arguments": json.dumps({"cmd": "rg TODO src/private_low_output.py"}),
            },
        ),
        _entry(
            "response_item",
            {
                "type": "function_call_output",
                "call_id": "call-cold-rg",
                "output": (
                    "Chunk ID: abc123\n"
                    "Wall time: 0.0000 seconds\n"
                    "Process exited with code 0\n"
                    "Original token count: 4\n"
                    "Output:\n"
                    "PRIVATE LOW OUTPUT MATCH"
                ),
            },
        ),
        _custom_token_event(
            50_100,
            last_input_tokens=50_000,
            last_cached_input_tokens=500,
            last_output_tokens=100,
            last_reasoning_output_tokens=20,
        ),
        _entry("turn_context", {"turn_id": "turn-high-output", "model": "gpt-5.5"}),
        _custom_token_event(
            108_100,
            last_input_tokens=50_000,
            last_cached_input_tokens=45_000,
            last_output_tokens=8_000,
            last_reasoning_output_tokens=200,
        ),
        _entry("turn_context", {"turn_id": "turn-small", "model": "gpt-5.5"}),
        _custom_token_event(
            109_000,
            last_input_tokens=850,
            last_cached_input_tokens=0,
            last_output_tokens=50,
        ),
    ]
    _write_jsonl(log_path, rows)

    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    payload = build_large_low_output_report(
        db_path=db_path,
        min_total_tokens=20_000,
        max_output_tokens=500,
        limit=None,
    ).payload

    assert validate_json_payload_contract(payload) == []
    assert payload["schema"] == "codex-usage-tracker-large-low-output-v1"
    assert payload["content_mode"] == "aggregate_with_local_activity"
    assert payload["includes_indexed_content"] is False
    assert payload["includes_raw_fragments"] is False
    assert payload["row_count"] == 1
    candidate = payload["rows"][0]
    assert candidate["total_tokens"] == 50_100
    assert candidate["output_tokens"] == 100
    assert candidate["cache_ratio"] < 0.02
    assert candidate["command_run_count"] == 1
    assert candidate["candidate_explanation"] == "cold_resume_or_cache_miss"
    assert "large_uncached_input" in candidate["explanation_reasons"]
    serialized = json.dumps(payload)
    assert "src/private_low_output.py" not in serialized
    assert "PRIVATE LOW OUTPUT MATCH" not in serialized

    walk = build_investigation_walk_report(
        db_path=db_path,
        question="look for token waste",
        min_occurrences=1,
    ).payload
    assert validate_json_payload_contract(walk) == []
    assert any(branch["scan_type"] == "large_low_output" for branch in walk["branches"])
    assert any(tool["tool"] == "usage_large_low_output_calls" for tool in walk["recommended_next_tools"])


def _custom_token_event(
    cumulative_total: int,
    *,
    last_input_tokens: int,
    last_cached_input_tokens: int,
    last_output_tokens: int,
    last_reasoning_output_tokens: int = 0,
) -> dict[str, object]:
    return _entry(
        "event_msg",
        {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": max(cumulative_total - last_output_tokens, 0),
                    "cached_input_tokens": last_cached_input_tokens,
                    "output_tokens": last_output_tokens,
                    "reasoning_output_tokens": last_reasoning_output_tokens,
                    "total_tokens": cumulative_total,
                },
                "last_token_usage": {
                    "input_tokens": last_input_tokens,
                    "cached_input_tokens": last_cached_input_tokens,
                    "output_tokens": last_output_tokens,
                    "reasoning_output_tokens": last_reasoning_output_tokens,
                    "total_tokens": last_input_tokens + last_output_tokens,
                },
                "model_context_window": 100_000,
            },
        },
    )


def _private_export_sentinels() -> tuple[str, ...]:
    return (
        "SECRET",
        "docs/private_notes.md",
        "private_notes.md",
        "src/app.py",
        "app.py",
        "call-read",
        "call-patch",
    )
