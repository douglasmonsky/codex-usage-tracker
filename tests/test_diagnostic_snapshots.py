from __future__ import annotations

import json
from pathlib import Path

from store_dashboard_helpers import (
    SESSION_ID,
    _assert_contract,
    _entry,
    _make_codex_home,
    _token_event,
    _write_jsonl,
)

from codex_usage_tracker.diagnostic_snapshots import (
    DIAGNOSTIC_OVERVIEW_SECTION,
    build_diagnostic_commands_report,
    build_diagnostic_overview_report,
    build_diagnostic_tool_output_report,
)
from codex_usage_tracker.store import (
    query_diagnostic_snapshot,
    refresh_usage_index,
    upsert_diagnostic_snapshot,
)


def test_diagnostic_overview_snapshot_is_explicit_and_aggregate_only(
    tmp_path: Path,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"

    missing_before_refresh = build_diagnostic_overview_report(db_path=db_path).payload
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    missing_after_usage_refresh = build_diagnostic_overview_report(db_path=db_path).payload
    refreshed = build_diagnostic_overview_report(db_path=db_path, refresh=True).payload
    stored = build_diagnostic_overview_report(db_path=db_path).payload

    _assert_contract(missing_before_refresh)
    _assert_contract(missing_after_usage_refresh)
    _assert_contract(refreshed)
    _assert_contract(stored)
    assert missing_before_refresh["status"] == "missing"
    assert missing_after_usage_refresh["status"] == "missing"
    assert refreshed["status"] == "ready"
    assert refreshed["refreshed"] is True
    assert stored["status"] == "ready"
    assert stored["refreshed"] is False
    assert refreshed["overview"]["usage_rows"] == 4
    assert refreshed["overview"]["total_tokens"] == 400
    assert refreshed["snapshot"]["history_scope"] == "active"
    assert refreshed["snapshot"]["raw_content_included"] is False

    serialized = json.dumps(refreshed, sort_keys=True)
    assert "SECRET RAW PROMPT" not in serialized
    assert "sk-proj" not in serialized
    assert "/tmp/codex-usage-tracker" not in serialized
    assert "AGENTS.md instructions" not in serialized


def test_usage_refresh_does_not_recompute_diagnostic_overview_snapshot(
    tmp_path: Path,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    build_diagnostic_overview_report(db_path=db_path, refresh=True)

    stale_payload = {
        "schema": "codex-usage-tracker-diagnostic-overview-v1",
        "section": DIAGNOSTIC_OVERVIEW_SECTION,
        "status": "ready",
        "refreshed": True,
        "raw_context_included": False,
        "snapshot": {
            "computed_at": "2000-01-01T00:00:00+00:00",
            "history_scope": "active",
            "source_logs_scanned": 1,
            "usage_rows_scanned": 1,
            "raw_content_included": False,
        },
        "overview": {"usage_rows": 1, "total_tokens": 7},
        "notes": [],
    }
    upsert_diagnostic_snapshot(
        db_path=db_path,
        section=DIAGNOSTIC_OVERVIEW_SECTION,
        history_scope="active",
        payload=stale_payload,
        computed_at="2000-01-01T00:00:00+00:00",
        source_logs_scanned=1,
        usage_rows_scanned=1,
    )

    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    stored = query_diagnostic_snapshot(
        db_path=db_path,
        section=DIAGNOSTIC_OVERVIEW_SECTION,
        history_scope="active",
    )

    assert stored is not None
    assert stored["computed_at"] == "2000-01-01T00:00:00+00:00"
    assert stored["payload"]["overview"]["total_tokens"] == 7


def test_tool_output_and_command_snapshots_use_safe_aggregate_labels(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / ".codex"
    log_path = (
        codex_home
        / "sessions"
        / "2026"
        / "05"
        / "17"
        / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
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
                    "cwd": "/tmp/private-diagnostics",
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "function_call",
                    "call_id": "call-git",
                    "name": "exec_command",
                    "arguments": json.dumps({"cmd": "git diff --stat SECRET_RAW_ARGUMENT"}),
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "function_call_output",
                    "call_id": "call-git",
                    "output": _terminal_output(42),
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "function_call",
                    "call_id": "call-python",
                    "name": "exec_command",
                    "arguments": json.dumps(
                        {"cmd": "PYTHONPATH=src python -m pytest tests/test_private.py"}
                    ),
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "function_call_output",
                    "call_id": "call-python",
                    "output": "plain output without wrapper header SECRET_OUTPUT",
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "function_call",
                    "call_id": "call-stdin",
                    "name": "write_stdin",
                    "arguments": json.dumps({"chars": "SECRET_STDIN"}),
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "function_call_output",
                    "call_id": "call-stdin",
                    "output": _terminal_output(5),
                },
            ),
            _token_event(100, 100),
        ],
    )
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    missing = build_diagnostic_tool_output_report(db_path=db_path).payload
    tool_output = build_diagnostic_tool_output_report(db_path=db_path, refresh=True).payload
    commands = build_diagnostic_commands_report(db_path=db_path, refresh=True).payload

    _assert_contract(missing)
    _assert_contract(tool_output)
    _assert_contract(commands)
    assert missing["status"] == "missing"
    assert tool_output["status"] == "ready"
    assert tool_output["summary"]["function_calls"] == 3
    assert tool_output["summary"]["function_outputs"] == 3
    assert tool_output["summary"]["outputs_with_original_token_count"] == 2
    assert tool_output["summary"]["outputs_missing_original_token_count"] == 1
    assert tool_output["summary"]["original_token_sum"] == 47
    functions = {row["function"]: row for row in tool_output["functions"]}
    assert functions["exec_command"]["calls"] == 2
    assert functions["exec_command"]["with_original_token_count"] == 1
    assert functions["exec_command"]["missing_original_token_count"] == 1
    assert functions["write_stdin"]["original_token_sum"] == 5
    assert tool_output["missing_reasons"] == [{"name": "string_no_header", "count": 1}]

    command_rows = {row["root"]: row for row in commands["commands"]}
    assert command_rows["git"]["total"] == 1
    assert command_rows["git"]["children"][0] == {"child": "diff", "count": 1}
    assert command_rows["python"]["children"][0] == {"child": "-m:pytest", "count": 1}
    assert commands["summary"]["missing_command"] == 1

    serialized = json.dumps([tool_output, commands], sort_keys=True)
    assert "SECRET" not in serialized
    assert "test_private.py" not in serialized
    assert "/tmp/private-diagnostics" not in serialized


def _terminal_output(count: int) -> str:
    return (
        "Chunk ID: abc123\n"
        "Wall time: 0.0000 seconds\n"
        "Process exited with code 0\n"
        f"Original token count: {count}\n"
        "Output:\n"
        "redacted by test fixture"
    )
