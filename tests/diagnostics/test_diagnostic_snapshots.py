from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from codex_usage_tracker.diagnostics import snapshots as diagnostic_snapshot_module
from codex_usage_tracker.diagnostics.snapshots import (
    DIAGNOSTIC_OVERVIEW_SECTION,
    build_diagnostic_commands_report,
    build_diagnostic_concentration_report,
    build_diagnostic_file_modifications_report,
    build_diagnostic_file_reads_report,
    build_diagnostic_git_interactions_report,
    build_diagnostic_guided_summary_report,
    build_diagnostic_overview_report,
    build_diagnostic_read_productivity_report,
    build_diagnostic_tool_output_report,
    refresh_diagnostic_snapshots,
)
from codex_usage_tracker.store.api import (
    query_diagnostic_snapshot,
    query_session_usage,
    refresh_usage_index,
    upsert_diagnostic_snapshot,
    upsert_usage_events,
)
from tests.store_dashboard_helpers import (
    SESSION_ID,
    _assert_contract,
    _entry,
    _make_codex_home,
    _token_event,
    _usage_event,
    _write_jsonl,
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


def test_batch_diagnostic_refresh_shares_source_log_analysis_pass(
    tmp_path: Path,
    monkeypatch,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    calls = 0
    original = diagnostic_snapshot_module.analyze_indexed_source_logs

    def counting_analyzer(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(
        diagnostic_snapshot_module,
        "analyze_indexed_source_logs",
        counting_analyzer,
    )

    refreshed = refresh_diagnostic_snapshots(db_path=db_path)
    stored_file_reads = build_diagnostic_file_reads_report(db_path=db_path).payload
    stored_file_modifications = build_diagnostic_file_modifications_report(db_path=db_path).payload
    stored_read_productivity = build_diagnostic_read_productivity_report(db_path=db_path).payload

    assert calls == 1
    assert refreshed["schema"] == "codex-usage-tracker-diagnostic-snapshot-refresh-v1"
    assert refreshed["meta"]["source_log_analysis_passes"] == 1
    assert refreshed["sections"]["overview"]["status"] == "ready"
    assert refreshed["sections"]["toolOutput"]["status"] == "ready"
    assert refreshed["sections"]["commands"]["status"] == "ready"
    assert refreshed["sections"]["gitInteractions"]["status"] == "ready"
    assert refreshed["sections"]["fileReads"]["status"] == "ready"
    assert refreshed["sections"]["fileModifications"]["status"] == "ready"
    assert refreshed["sections"]["readProductivity"]["status"] == "ready"
    assert refreshed["sections"]["concentration"]["status"] == "ready"
    assert refreshed["sections"]["guidedSummary"]["status"] == "ready"
    assert stored_file_reads["status"] == "ready"
    assert stored_file_reads["refreshed"] is False
    assert stored_file_modifications["status"] == "ready"
    assert stored_file_modifications["refreshed"] is False
    assert stored_read_productivity["status"] == "ready"
    assert stored_read_productivity["refreshed"] is False


def test_guided_summary_snapshot_ranks_aggregate_usage_drivers(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    first = replace(
        _usage_event(
            record_id="heavy-thread-a",
            session_id=SESSION_ID,
            thread_key="thread:Long Research Thread",
            event_timestamp="2026-05-17T14:00:00Z",
            cumulative_total_tokens=1_000,
        ),
        model="gpt-5.5",
        effort="high",
        input_tokens=900,
        cached_input_tokens=100,
        output_tokens=100,
        reasoning_output_tokens=50,
        total_tokens=1_000,
        cumulative_input_tokens=900,
        cumulative_cached_input_tokens=100,
        cumulative_output_tokens=100,
        cumulative_reasoning_output_tokens=50,
        cumulative_total_tokens=1_000,
    )
    second = replace(
        _usage_event(
            record_id="small-thread-b",
            session_id="019e37d4-c1f1-71aa-b154-2d5d837af92c",
            thread_key="thread:Small Fix Thread",
            event_timestamp="2026-05-17T15:00:00Z",
            cumulative_total_tokens=1_120,
        ),
        model="gpt-5.4",
        effort="low",
        input_tokens=90,
        cached_input_tokens=70,
        output_tokens=30,
        reasoning_output_tokens=5,
        total_tokens=120,
        cumulative_input_tokens=90,
        cumulative_cached_input_tokens=70,
        cumulative_output_tokens=30,
        cumulative_reasoning_output_tokens=5,
        cumulative_total_tokens=120,
    )
    upsert_usage_events(db_path=db_path, events=[first, second])

    missing = build_diagnostic_guided_summary_report(db_path=db_path).payload
    guided = build_diagnostic_guided_summary_report(
        db_path=db_path,
        refresh=True,
    ).payload
    stored = build_diagnostic_guided_summary_report(db_path=db_path).payload

    _assert_contract(missing)
    _assert_contract(guided)
    assert missing["status"] == "missing"
    assert guided["status"] == "ready"
    assert guided["schema"] == "codex-usage-tracker-diagnostic-guided-summary-v1"
    assert guided["summary"]["usage_rows"] == 2
    assert guided["summary"]["total_tokens"] == 1_120
    assert guided["top_threads"][0]["label"] == "Long Research Thread"
    assert guided["top_models"][0]["label"] == "gpt-5.5"
    assert guided["drivers"][0]["key"] == "top-thread"
    assert any(signal["key"] == "low-cache-reuse" for signal in guided["signals"])
    assert stored["status"] == "ready"

    serialized = json.dumps(guided, sort_keys=True)
    assert "SECRET" not in serialized
    assert "tool output" not in serialized.lower()


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
    record_id = query_session_usage(db_path=db_path, session_id=SESSION_ID)[0]["record_id"]

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
    assert functions["exec_command"]["representative_record_id"] == record_id
    assert functions["write_stdin"]["original_token_sum"] == 5
    assert functions["write_stdin"]["representative_record_id"] == record_id
    assert tool_output["missing_reasons"] == [{"name": "string_no_header", "count": 1}]

    command_rows = {row["root"]: row for row in commands["commands"]}
    assert command_rows["git"]["total"] == 1
    assert command_rows["git"]["representative_record_id"] == record_id
    assert command_rows["git"]["children"][0] == {"child": "diff", "count": 1}
    assert command_rows["pytest"]["children"][0] == {"child": "<target>", "count": 1}
    assert command_rows["pytest"]["representative_record_id"] == record_id
    assert commands["summary"]["missing_command"] == 1

    serialized = json.dumps([tool_output, commands], sort_keys=True)
    assert "SECRET" not in serialized
    assert "test_private.py" not in serialized
    assert "/tmp/private-diagnostics" not in serialized


def test_git_interaction_snapshot_uses_safe_aggregate_operations(tmp_path: Path) -> None:
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
            _function_call("call-status", "git -C /tmp/private/repo status --short --branch"),
            _function_output("call-status", _terminal_output(11)),
            _function_call("call-diff", "git diff --stat SECRET_RAW_ARGUMENT"),
            _function_output("call-diff", _terminal_output(42)),
            _function_call("call-add", "git add src/private.py"),
            _function_output("call-add", _terminal_output(7)),
            _function_call("call-commit", "git commit -m SECRET_COMMIT_MESSAGE"),
            _function_output("call-commit", "plain output without wrapper SECRET_OUTPUT"),
            _function_call("call-push", "git push origin feature/secret-branch"),
            _function_output("call-push", _terminal_output(9)),
            _function_call("call-gh-pr", "gh pr create --title SECRET_TITLE"),
            _function_output("call-gh-pr", _terminal_output(13)),
            _function_call("call-gh-release", "gh release create v0.9.0 --notes SECRET_NOTES"),
            _function_output("call-gh-release", _terminal_output(17)),
            _function_call("call-gh-run", "gh run watch 123456"),
            _function_output("call-gh-run", _terminal_output(19)),
            _token_event(100, 100),
        ],
    )
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    record_id = query_session_usage(db_path=db_path, session_id=SESSION_ID)[0]["record_id"]

    missing = build_diagnostic_git_interactions_report(db_path=db_path).payload
    git_interactions = build_diagnostic_git_interactions_report(
        db_path=db_path,
        refresh=True,
    ).payload

    _assert_contract(missing)
    _assert_contract(git_interactions)
    assert missing["status"] == "missing"
    assert git_interactions["status"] == "ready"
    assert git_interactions["summary"]["git_shell_calls"] == 8
    assert git_interactions["summary"]["git_command_calls"] == 5
    assert git_interactions["summary"]["github_cli_calls"] == 3
    assert git_interactions["summary"]["interactions_with_original_token_count"] == 7
    assert git_interactions["summary"]["interactions_missing_original_token_count"] == 1
    assert git_interactions["summary"]["original_token_sum"] == 118

    rows = {
        (row["root"], row["operation"]): row
        for row in git_interactions["interactions"]
    }
    assert rows[("git", "status")]["category"] == "read_only"
    assert rows[("git", "status")]["mutability"] == "read_only"
    assert rows[("git", "status")]["representative_record_id"] == record_id
    assert rows[("git", "diff")]["original_token_sum"] == 42
    assert rows[("git", "commit")]["missing_original_token_count"] == 1
    assert rows[("git", "push")]["category"] == "remote_ref"
    assert rows[("gh", "pr")]["category"] == "pull_request"
    assert rows[("gh", "release")]["category"] == "release"
    assert rows[("gh", "run")]["category"] == "workflow"

    categories = {row["category"]: row["count"] for row in git_interactions["categories"]}
    assert categories["read_only"] == 2
    assert categories["local_mutation"] == 2
    assert categories["remote_ref"] == 1
    assert categories["pull_request"] == 1
    assert categories["release"] == 1
    assert categories["workflow"] == 1

    serialized = json.dumps(git_interactions, sort_keys=True)
    assert "SECRET" not in serialized
    assert "/tmp/private" not in serialized
    assert "src/private.py" not in serialized
    assert "feature/secret-branch" not in serialized
    assert "v0.9.0" not in serialized


def test_file_read_snapshots_allocate_tokens_and_correlate_later_modifications(
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
            _function_call("call-cat", "cat src/app.py /tmp/private/readme.md"),
            _function_output("call-cat", _terminal_output(90)),
            _function_call("call-sed", "sed -n '1,120p' src/app.py"),
            _function_output("call-sed", _terminal_output(30)),
            _function_call("call-nl", "nl -ba src/app.py"),
            _function_output("call-nl", _terminal_output(10)),
            _function_call("call-rg", "rg -n SECRET_PATTERN src tests"),
            _function_output("call-rg", _terminal_output(80)),
            _function_call("call-find", "find src -name '*.py'"),
            _function_output("call-find", _terminal_output(20)),
            _function_call("call-missing", "cat docs/notes.md"),
            _function_output("call-missing", "plain read output SECRET_OUTPUT"),
            _entry(
                "event_msg",
                {
                    "type": "patch_apply_end",
                    "changed_paths": ["src/app.py", "/tmp/private/readme.md"],
                    "patch": "SECRET PATCH TEXT",
                },
            ),
            _token_event(100, 100),
        ],
    )
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    record_id = query_session_usage(db_path=db_path, session_id=SESSION_ID)[0]["record_id"]

    missing = build_diagnostic_file_reads_report(db_path=db_path).payload
    file_reads = build_diagnostic_file_reads_report(db_path=db_path, refresh=True).payload
    read_productivity = build_diagnostic_read_productivity_report(
        db_path=db_path,
        refresh=True,
    ).payload

    _assert_contract(missing)
    _assert_contract(file_reads)
    _assert_contract(read_productivity)
    assert missing["status"] == "missing"
    assert file_reads["status"] == "ready"
    assert file_reads["summary"]["read_commands"] == 6
    assert file_reads["summary"]["read_events"] == 8
    assert file_reads["summary"]["unique_paths_read"] == 5
    assert file_reads["summary"]["read_events_with_output_count"] == 7
    assert file_reads["summary"]["read_events_missing_output_count"] == 1
    assert file_reads["summary"]["allocated_output_token_sum"] == 230

    by_reader = {row["reader"]: row for row in file_reads["by_reader"]}
    assert by_reader["direct_file_read:cat"]["read_events"] == 3
    assert by_reader["direct_file_read:cat"]["events_missing_output_count"] == 1
    assert by_reader["direct_file_read:cat"]["allocated_output_token_sum"] == 90
    assert by_reader["direct_file_read:cat"]["representative_record_id"] == record_id
    assert by_reader["search_path_scan:rg"]["allocated_output_token_sum"] == 80
    assert by_reader["search_path_scan:find"]["allocated_output_token_sum"] == 20

    paths = {row["path_label"]: row for row in file_reads["top_paths"]}
    assert paths["app.py"]["read_events"] == 3
    assert paths["app.py"]["allocated_output_token_sum"] == 85
    assert paths["app.py"]["representative_record_id"] == record_id
    assert paths["readme.md"]["allocated_output_token_sum"] == 45
    assert paths["src"]["allocated_output_token_sum"] == 60
    assert paths["tests"]["allocated_output_token_sum"] == 40

    assert file_reads["largest_read_commands"][0]["root"] == "cat"
    assert file_reads["largest_read_commands"][0]["original_token_count"] == 90
    assert file_reads["largest_read_commands"][0]["representative_record_id"] == record_id

    assert read_productivity["summary"]["read_events"] == 8
    assert read_productivity["summary"]["read_events_modified_later"] == 4
    assert read_productivity["summary"]["read_events_modified_later_pct"] == 0.5
    assert read_productivity["summary"]["unique_paths_modified_later"] == 2
    productivity_by_reader = {row["reader"]: row for row in read_productivity["by_reader"]}
    assert productivity_by_reader["direct_file_read:cat"]["read_events_modified_later"] == 2
    assert productivity_by_reader["direct_file_read:cat"]["representative_record_id"] == record_id
    assert productivity_by_reader["direct_file_read:sed"]["read_events_modified_later"] == 1
    assert productivity_by_reader["direct_file_read:nl"]["read_events_modified_later"] == 1
    modified_paths = {row["path_label"]: row for row in read_productivity["top_modified_paths"]}
    assert modified_paths["app.py"]["read_events_modified_later"] == 3
    assert modified_paths["app.py"]["representative_record_id"] == record_id
    assert modified_paths["readme.md"]["read_events_modified_later"] == 1
    assert "temporal correlations" in read_productivity["summary"]["correlation_note"]

    serialized = json.dumps([file_reads, read_productivity], sort_keys=True)
    assert "SECRET" not in serialized
    assert "src/app.py" not in serialized
    assert "/tmp/private" not in serialized
    assert "1,120p" not in serialized
    assert "SECRET PATCH TEXT" not in serialized


def test_file_modification_snapshot_uses_safe_path_aggregates(tmp_path: Path) -> None:
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
                "event_msg",
                {
                    "type": "patch_apply_end",
                    "changed_paths": ["src/app.py", "/tmp/private/notes.md"],
                    "patch": "SECRET PATCH TEXT",
                },
            ),
            _entry(
                "event_msg",
                {
                    "type": "patch_apply_end",
                    "changes": [
                        {"path": "docs/readme.md"},
                        {"old_path": "src/old.py", "new_path": "src/new.py"},
                    ],
                    "patch": "SECRET SECOND PATCH",
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "custom_tool_call",
                    "name": "apply_patch",
                    "input": (
                        "*** Begin Patch\n"
                        "*** Update File: src/tool.py\n"
                        "@@\n"
                        "-SECRET OLD\n"
                        "+SECRET NEW\n"
                        "*** Add File: docs/new.md\n"
                        "+SECRET NEW DOC\n"
                        "*** End Patch\n"
                    ),
                },
            ),
            _token_event(100, 100),
        ],
    )
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    record_id = query_session_usage(db_path=db_path, session_id=SESSION_ID)[0]["record_id"]

    missing = build_diagnostic_file_modifications_report(db_path=db_path).payload
    file_modifications = build_diagnostic_file_modifications_report(
        db_path=db_path,
        refresh=True,
    ).payload

    _assert_contract(missing)
    _assert_contract(file_modifications)
    assert missing["status"] == "missing"
    assert file_modifications["status"] == "ready"
    assert file_modifications["summary"]["modification_events"] == 3
    assert file_modifications["summary"]["modified_path_events"] == 7
    assert file_modifications["summary"]["unique_paths_modified"] == 7
    assert file_modifications["summary"]["largest_event_path_count"] == 3

    paths = {row["path_label"]: row for row in file_modifications["top_paths"]}
    assert paths["app.py"]["modification_events"] == 1
    assert paths["app.py"]["representative_record_id"] == record_id
    assert paths["notes.md"]["modification_events"] == 1
    assert paths["readme.md"]["modification_events"] == 1
    assert paths["old.py"]["modification_events"] == 1
    assert paths["new.py"]["modification_events"] == 1
    assert paths["tool.py"]["modification_events"] == 1
    assert paths["new.md"]["modification_events"] == 1

    extensions = {row["extension"]: row["count"] for row in file_modifications["by_extension"]}
    assert extensions[".py"] == 4
    assert extensions[".md"] == 3
    assert file_modifications["largest_events"][0]["modified_path_count"] == 3
    assert file_modifications["largest_events"][0]["representative_record_id"] == record_id

    serialized = json.dumps(file_modifications, sort_keys=True)
    assert "SECRET" not in serialized
    assert "/tmp/private" not in serialized
    assert "src/app.py" not in serialized
    assert "src/tool.py" not in serialized
    assert "docs/readme.md" not in serialized
    assert "SECRET PATCH TEXT" not in serialized


def test_concentration_snapshot_reports_top_shares_without_raw_paths(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [
            _concentration_event(
                record_id="r1",
                session_id=SESSION_ID,
                event_timestamp="2026-05-17T10:00:00Z",
                source_file="/tmp/private/session-a.jsonl",
                cwd="/tmp/private/project-a",
                total_tokens=30,
            ),
            _concentration_event(
                record_id="r2",
                session_id=SESSION_ID,
                event_timestamp="2026-05-17T11:00:00Z",
                source_file="/tmp/private/session-a.jsonl",
                cwd="/tmp/private/project-a",
                total_tokens=20,
            ),
            _concentration_event(
                record_id="r3",
                session_id="019e37d4-c1f1-71aa-b154-2d5d837af92c",
                event_timestamp="2026-05-18T10:00:00Z",
                source_file="/tmp/private/session-b.jsonl",
                cwd="/tmp/private/project-b",
                total_tokens=30,
            ),
            _concentration_event(
                record_id="r4",
                session_id="019e37d5-01fd-71df-87f4-ae3e8d60df7a",
                event_timestamp="2026-05-19T10:00:00Z",
                source_file="/tmp/private/session-c.jsonl",
                cwd="/tmp/private/project-b",
                total_tokens=20,
            ),
        ],
        db_path=db_path,
    )

    missing = build_diagnostic_concentration_report(db_path=db_path).payload
    refreshed = build_diagnostic_concentration_report(db_path=db_path, refresh=True).payload
    stored = build_diagnostic_concentration_report(db_path=db_path).payload

    _assert_contract(missing)
    _assert_contract(refreshed)
    _assert_contract(stored)
    assert missing["status"] == "missing"
    assert refreshed["status"] == "ready"
    assert stored["refreshed"] is False
    assert refreshed["snapshot"]["source_logs_scanned"] == 3
    assert refreshed["summary"]["usage_rows"] == 4
    assert refreshed["summary"]["total_tokens"] == 100
    metrics = {row["metric"]: row["share"] for row in refreshed["metrics"]}
    assert metrics["top_1_source_log_share"] == 0.5
    assert metrics["top_3_source_log_share"] == 1.0
    assert metrics["top_5_source_log_share"] == 1.0
    assert metrics["top_1_cwd_share"] == 0.5
    assert metrics["top_3_day_share"] == 1.0

    dimensions = {row["dimension"]: row for row in refreshed["dimensions"]}
    assert dimensions["source_log"]["group_count"] == 3
    assert dimensions["source_log"]["effective_group_count"] == 2.631579
    assert dimensions["cwd"]["group_count"] == 2
    assert dimensions["cwd"]["effective_group_count"] == 2.0
    assert dimensions["day"]["top_rows"][0]["label"] == "2026-05-17"
    assert dimensions["day"]["top_rows"][0]["largest_record_id"] == "r1"
    assert refreshed["largest_impact_rows"][0]["largest_record_id"] == "r1"
    assert refreshed["largest_impact_rows"][0]["session_id"] == SESSION_ID

    serialized = json.dumps(refreshed, sort_keys=True)
    assert "/tmp/private" not in serialized
    assert "session-a.jsonl" not in serialized
    assert "project-a" in serialized
    assert "source_log_label_policy" in serialized


def _concentration_event(
    *,
    record_id: str,
    session_id: str,
    event_timestamp: str,
    source_file: str,
    cwd: str,
    total_tokens: int,
):
    base = _usage_event(
        record_id=record_id,
        session_id=session_id,
        thread_key=f"thread:{record_id}",
        event_timestamp=event_timestamp,
        cumulative_total_tokens=total_tokens,
    )
    return replace(
        base,
        source_file=source_file,
        cwd=cwd,
        total_tokens=total_tokens,
        input_tokens=total_tokens,
        cached_input_tokens=0,
        output_tokens=0,
        reasoning_output_tokens=0,
    )


def _function_call(call_id: str, command: str) -> dict[str, object]:
    return _entry(
        "response_item",
        {
            "type": "function_call",
            "call_id": call_id,
            "name": "exec_command",
            "arguments": json.dumps({"cmd": command}),
        },
    )


def _function_output(call_id: str, output: str) -> dict[str, object]:
    return _entry(
        "response_item",
        {
            "type": "function_call_output",
            "call_id": call_id,
            "output": output,
        },
    )


def _terminal_output(count: int) -> str:
    return (
        "Chunk ID: abc123\n"
        "Wall time: 0.0000 seconds\n"
        "Process exited with code 0\n"
        f"Original token count: {count}\n"
        "Output:\n"
        "redacted by test fixture"
    )
