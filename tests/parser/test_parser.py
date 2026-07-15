from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from codex_usage_tracker.core.models import SessionInfo
from codex_usage_tracker.parser.api import (
    find_session_logs,
    inspect_log,
    load_session_index,
    parse_usage_events_from_file,
    parse_usage_events_from_file_with_state,
)
from codex_usage_tracker.parser.jsonl_v1 import KNOWN_NON_TOKEN_EVENT_MSG_TYPES

SESSION_ID = "019e374d-c19f-7da3-a44f-8de043a7a64e"


def test_parser_skips_missing_info_and_duplicate_snapshots(tmp_path: Path) -> None:
    log_path = tmp_path / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": SESSION_ID}),
            _entry(
                "session_meta",
                {
                    "id": SESSION_ID,
                    "thread_source": "subagent",
                    "source": {
                        "subagent": {
                            "thread_spawn": {
                                "parent_thread_id": "parent-session",
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
                    "turn_id": "turn-a",
                    "model": "gpt-5.5",
                    "effort": "xhigh",
                    "cwd": "/tmp/work",
                    "current_date": "2026-05-17",
                    "timezone": "America/New_York",
                },
            ),
            _entry("event_msg", {"type": "token_count", "info": None}),
            _token_event(100, 100),
            _entry(
                "response_item",
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "SECRET RAW PROMPT"}],
                },
            ),
            _token_event(100, 100),
            _token_event(150, 50),
            _entry(
                "turn_context",
                {
                    "turn_id": "turn-b",
                    "model": "gpt-5.5",
                    "effort": "high",
                    "cwd": "/tmp/work",
                },
            ),
            _token_event(150, 50),
            _token_event(210, 60),
        ],
    )

    events = parse_usage_events_from_file(
        log_path,
        {
            "parent-session": SessionInfo(
                session_id="parent-session",
                thread_name="Parent Thread",
                updated_at="2026-05-17T18:00:00Z",
            )
        },
    )

    assert [event.cumulative_total_tokens for event in events] == [100, 150, 210]
    assert [event.total_tokens for event in events] == [100, 50, 60]
    assert events[0].turn_id == "turn-a"
    assert events[-1].turn_id == "turn-b"
    assert events[-1].effort == "high"
    assert events[0].thread_source == "subagent"
    assert events[0].subagent_type == "thread_spawn"
    assert events[0].agent_role == "test_runner"
    assert events[0].agent_nickname == "Verifier"
    assert events[0].parent_session_id == "parent-session"
    assert events[0].parent_thread_name == "Parent Thread"
    assert events[0].parent_session_updated_at == "2026-05-17T18:00:00Z"
    assert all("SECRET" not in str(event.to_row()) for event in events)


def test_parser_persists_observed_usage_snapshot_fields(tmp_path: Path) -> None:
    log_path = tmp_path / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    token_event = _token_event(100, 100)
    token_event["payload"]["rate_limits"] = {  # type: ignore[index]
        "plan_type": "pro",
        "limit_id": "codex",
        "primary": {
            "used_percent": 2.5,
            "window_minutes": 300,
            "resets_at": 1781562696,
        },
        "secondary": {
            "used_percent": 29,
            "window_minutes": 10080,
            "resets_at": 1781887793,
        },
    }
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": SESSION_ID}),
            _entry(
                "turn_context",
                {"turn_id": "turn-a", "model": "gpt-5.5", "effort": "high"},
            ),
            token_event,
        ],
    )

    [event] = parse_usage_events_from_file(log_path, {})

    assert event.rate_limit_plan_type == "pro"
    assert event.rate_limit_limit_id == "codex"
    assert event.rate_limit_primary_used_percent == 2.5
    assert event.rate_limit_primary_window_minutes == 300
    assert event.rate_limit_primary_resets_at == 1781562696
    assert event.rate_limit_secondary_used_percent == 29.0
    assert event.rate_limit_secondary_window_minutes == 10080
    assert event.rate_limit_secondary_resets_at == 1781887793
    assert "rate_limits" not in event.to_row()


def test_parser_skips_corrupt_token_count_and_continues(tmp_path: Path) -> None:
    log_path = tmp_path / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    corrupt = _token_event(100, 100)
    corrupt["payload"]["info"]["last_token_usage"]["input_tokens"] = "not-a-number"  # type: ignore[index]
    optional_bad_window = _token_event(150, 50)
    optional_bad_window["payload"]["info"]["model_context_window"] = "huge"  # type: ignore[index]
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": SESSION_ID}),
            _entry(
                "turn_context",
                {"turn_id": "turn-a", "model": "gpt-5.5", "effort": "high"},
            ),
            corrupt,
            optional_bad_window,
            _token_event(210, 60),
        ],
    )

    stats: dict[str, int] = {}
    events = parse_usage_events_from_file(log_path, stats=stats)

    assert stats["skipped_events"] == 1
    assert stats["invalid_integer"] == 1
    assert stats["invalid_model_context_window"] == 1
    assert stats["partial_field_count"] == 2
    assert [event.cumulative_total_tokens for event in events] == [150, 210]
    assert events[0].model_context_window is None


def test_parser_ignores_known_non_token_context_compaction_event(tmp_path: Path) -> None:
    log_path = tmp_path / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": SESSION_ID}),
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
            _token_event(100, 100),
        ],
    )

    stats: dict[str, int] = {}
    events = parse_usage_events_from_file(log_path, stats=stats)

    assert len(events) == 1
    assert stats.get("unknown_event_shape", 0) == 0
    assert events[0].call_initiator == "codex"
    assert events[0].call_initiator_reason == "post_compaction"
    assert events[0].call_initiator_confidence == "high"
    assert "SECRET COMPACTION TEXT" not in json.dumps([event.to_row() for event in events])


def test_parser_ignores_known_non_token_event_messages(tmp_path: Path) -> None:
    log_path = tmp_path / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    known_event_types = KNOWN_NON_TOKEN_EVENT_MSG_TYPES
    assert {"agent_reasoning", "sub_agent_activity", "thread_settings_applied"} <= known_event_types
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": SESSION_ID}),
            *[_entry("event_msg", {"type": event_type}) for event_type in known_event_types],
            _token_event(100, 100),
        ],
    )

    stats: dict[str, int] = {}
    events = parse_usage_events_from_file(log_path, stats=stats)

    assert len(events) == 1
    assert stats.get("unknown_event_shape", 0) == 0


def test_parser_persists_call_origin_from_metadata_segments(tmp_path: Path) -> None:
    log_path = tmp_path / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": SESSION_ID}),
            _entry("turn_context", {"turn_id": "turn-a", "model": "gpt-5.5"}),
            _entry(
                "response_item",
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "SECRET USER TEXT"}],
                },
            ),
            _token_event(100, 100),
            _entry("response_item", {"type": "function_call_output", "output": "SECRET TOOL"}),
            _token_event(150, 50),
            _entry(
                "response_item",
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "SECRET ASSISTANT TEXT"}],
                },
            ),
            _token_event(210, 60),
            _token_event(280, 70),
        ],
    )

    events = parse_usage_events_from_file(log_path)

    assert [
        (
            event.call_initiator,
            event.call_initiator_reason,
            event.call_initiator_confidence,
        )
        for event in events
    ] == [
        ("user", "user_message", "high"),
        ("codex", "tool_result", "high"),
        ("codex", "agent_continuation", "medium"),
        ("unknown", "no_signal", "low"),
    ]
    assert "SECRET" not in json.dumps([event.to_row() for event in events])


def test_parser_collects_diagnostic_facts_between_token_counts(tmp_path: Path) -> None:
    log_path = tmp_path / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": SESSION_ID}),
            _entry("turn_context", {"turn_id": "turn-a", "model": "gpt-5.5"}),
            _entry(
                "response_item",
                {
                    "type": "function_call_output",
                    "output": "SECRET TOOL OUTPUT",
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "function_call_output",
                    "output": "SECRET SECOND TOOL OUTPUT",
                },
            ),
            _entry(
                "event_msg",
                {
                    "type": "patch_apply_end",
                    "patch": "SECRET PATCH TEXT",
                },
            ),
            _token_event(100, 100),
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
            _token_event(150, 50),
        ],
    )

    parsed = parse_usage_events_from_file_with_state(log_path)

    assert [event.cumulative_total_tokens for event in parsed.events] == [100, 150]
    facts = {(fact.fact_type, fact.fact_name): fact for fact in parsed.diagnostic_facts}
    assert set(facts) == {
        ("compaction", "post_compaction"),
        ("outcome", "patch_applied"),
        ("tool", "function_call_output"),
    }
    assert facts[("tool", "function_call_output")].record_id == parsed.events[0].record_id
    assert facts[("tool", "function_call_output")].event_count == 2
    assert facts[("outcome", "patch_applied")].record_id == parsed.events[0].record_id
    assert facts[("compaction", "post_compaction")].record_id == parsed.events[1].record_id
    assert all(fact.raw_content_included == 0 for fact in parsed.diagnostic_facts)
    assert "SECRET" not in json.dumps(
        [fact.to_row() for fact in parsed.diagnostic_facts],
        sort_keys=True,
    )


def test_parser_classifies_richer_diagnostic_detectors_without_raw_content(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": SESSION_ID}),
            _entry("turn_context", {"turn_id": "turn-a", "model": "gpt-5.5"}),
            _entry(
                "response_item",
                {
                    "type": "function_call",
                    "name": "functions.exec_command",
                    "arguments": json.dumps(
                        {"cmd": "pytest tests/test_private_customer.py -k SECRET_CUSTOMER"}
                    ),
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "function_call",
                    "name": "functions.exec_command",
                    "arguments": json.dumps({"cmd": "rg -n SECRET_CUSTOMER private"}),
                },
            ),
            _entry("response_item", {"type": "tool_search_call"}),
            _entry("response_item", {"type": "tool_search_output", "output": "SECRET SEARCH"}),
            _entry("event_msg", {"type": "web_search_end", "query": "SECRET SEARCH"}),
            _entry(
                "event_msg",
                {
                    "type": "mcp_tool_call_end",
                    "tool_name": "mcp__github__search_issues",
                    "server_name": "github",
                    "arguments": {"query": "SECRET MCP ARGUMENT"},
                },
            ),
            _entry(
                "event_msg",
                {"type": "skill_started", "skill_name": "codex-usage-tracker"},
            ),
            _entry("event_msg", {"type": "turn_aborted", "reason": "SECRET ABORT"}),
            _entry("event_msg", {"type": "thread_rolled_back", "reason": "SECRET ROLLBACK"}),
            _token_event(100, 100),
        ],
    )

    parsed = parse_usage_events_from_file_with_state(log_path)

    assert len(parsed.events) == 1
    facts = {(fact.fact_type, fact.fact_name): fact for fact in parsed.diagnostic_facts}
    assert {
        ("activity", "search_read_command"),
        ("command_family", "pytest"),
        ("command_family", "rg"),
        ("function", "functions.exec_command"),
        ("loop", "retry_or_abort_loop"),
        ("loop", "search_read_loop"),
        ("mcp_server", "github"),
        ("mcp_tool", "mcp__github__search_issues"),
        ("outcome", "thread_rolled_back"),
        ("outcome", "turn_aborted"),
        ("skill", "codex-usage-tracker"),
    } <= set(facts)
    assert facts[("function", "functions.exec_command")].event_count == 2
    assert facts[("loop", "search_read_loop")].event_count >= 3
    assert facts[("loop", "retry_or_abort_loop")].event_count == 2
    serialized = json.dumps(
        [fact.to_row() for fact in parsed.diagnostic_facts],
        sort_keys=True,
    )
    assert "SECRET" not in serialized
    assert "test_private_customer" not in serialized
    assert "rg -n" not in serialized
    assert all(fact.raw_content_included == 0 for fact in parsed.diagnostic_facts)


def test_parser_persists_dashboard_helper_metadata(tmp_path: Path) -> None:
    log_path = (
        tmp_path
        / ".codex"
        / "archived_sessions"
        / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    )
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": SESSION_ID}),
            _entry("turn_context", {"turn_id": "turn-a", "model": "gpt-5.5"}),
            _token_event(100, 100),
        ],
    )

    events = parse_usage_events_from_file(
        log_path,
        {
            SESSION_ID: SessionInfo(
                session_id=SESSION_ID,
                thread_name="Archived tracker thread",
                updated_at="2026-05-17T18:00:00Z",
            )
        },
    )

    assert len(events) == 1
    assert events[0].is_archived == 1
    assert events[0].thread_key == "thread:Archived tracker thread"
    assert events[0].thread_call_index is None
    assert events[0].previous_record_id is None
    assert events[0].next_record_id is None


def test_inspect_log_reports_aggregate_diagnostics_without_db_writes(tmp_path: Path) -> None:
    log_path = tmp_path / "unknown-name.jsonl"
    missing_counter = _token_event(100, 100)
    del missing_counter["payload"]["info"]["last_token_usage"]["total_tokens"]  # type: ignore[index]
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": SESSION_ID}),
            _entry("turn_context", {"turn_id": "turn-a", "model": "gpt-5.5"}),
            missing_counter,
            _token_event(150, 50),
        ],
    )

    payload = inspect_log(log_path)

    assert payload["adapter"] == "codex-jsonl-v2"
    assert payload["file_session_id"] is None
    assert payload["event_count"] == 1
    assert payload["session_ids"] == [SESSION_ID]
    assert payload["models"] == ["gpt-5.5"]
    assert payload["diagnostics"] == {
        "unknown_filename_format": 1,
        "partial_field_count": 1,
        "skipped_events": 1,
    }
    assert "SECRET" not in json.dumps(payload)


def test_cli_inspect_log_outputs_parser_summary(tmp_path: Path) -> None:
    log_path = tmp_path / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    _write_jsonl(log_path, [_entry("session_meta", {"id": SESSION_ID}), _token_event(100, 100)])

    result = subprocess.run(
        [sys.executable, "-m", "codex_usage_tracker", "inspect-log", str(log_path)],
        check=True,
        capture_output=True,
        text=True,
        env=_subprocess_env(),
    )

    assert "Adapter: codex-jsonl-v2" in result.stdout
    assert "Parsed events: 1" in result.stdout
    assert "Diagnostics: none" in result.stdout


def test_session_index_join_and_archived_log_discovery(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    session_dir = codex_home / "sessions" / "2026" / "05" / "17"
    archived_dir = codex_home / "archived_sessions"
    session_dir.mkdir(parents=True)
    archived_dir.mkdir(parents=True)
    session_log = session_dir / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    archive_log = archived_dir / f"rollout-2026-05-17T14-58-23-{SESSION_ID}.jsonl"
    _write_jsonl(session_log, [_entry("session_meta", {"id": SESSION_ID})])
    _write_jsonl(archive_log, [_entry("session_meta", {"id": SESSION_ID})])
    _write_jsonl(
        codex_home / "session_index.jsonl",
        [
            {
                "id": SESSION_ID,
                "thread_name": "Add Codex token tracking",
                "updated_at": "2026-05-17T18:58:27Z",
            }
        ],
    )

    index = load_session_index(codex_home)
    active_only = find_session_logs(codex_home, include_archived=False)
    with_archived = find_session_logs(codex_home, include_archived=True)

    assert index[SESSION_ID].thread_name == "Add Codex token tracking"
    assert active_only == [session_log]
    assert with_archived == [archive_log, session_log]


def test_parser_assigns_canonical_identity_to_copied_usage(tmp_path: Path) -> None:
    original_id = "019e374d-c19f-7da3-a44f-8de043a7a64e"
    clone_id = "019e374d-c19f-7da3-a44f-8de043a7a64f"
    original_path = tmp_path / f"rollout-2026-05-17T14-58-23-{original_id}.jsonl"
    clone_path = tmp_path / f"rollout-2026-05-17T14-58-23-{clone_id}.jsonl"
    copied = _token_event(100, 100)
    copied["event_id"] = "evt-123"
    new_event = _token_event(150, 50)
    new_event["timestamp"] = "2026-05-17T18:59:27.000Z"
    _write_jsonl(original_path, [_entry("session_meta", {"id": original_id}), copied])
    _write_jsonl(
        clone_path,
        [_entry("session_meta", {"id": clone_id}), copied, new_event],
    )

    [original] = parse_usage_events_from_file(original_path)
    copied_clone, new_clone = parse_usage_events_from_file(clone_path)

    assert original.record_id != copied_clone.record_id
    assert original.usage_fingerprint == copied_clone.usage_fingerprint
    assert original.canonical_record_id == copied_clone.canonical_record_id
    assert original.usage_fingerprint != new_clone.usage_fingerprint
    assert original.upstream_usage_id == "envelope.event_id:evt-123"


def _token_event(cumulative_total: int, last_total: int) -> dict[str, object]:
    return _entry(
        "event_msg",
        {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": cumulative_total - 10,
                    "cached_input_tokens": 20,
                    "output_tokens": 10,
                    "reasoning_output_tokens": 5,
                    "total_tokens": cumulative_total,
                },
                "last_token_usage": {
                    "input_tokens": last_total - 10,
                    "cached_input_tokens": 5,
                    "output_tokens": 10,
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


def _subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    repo_root = Path(__file__).resolve().parents[2]
    src_path = str(repo_root / "src")
    env["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else src_path
    )
    return env
