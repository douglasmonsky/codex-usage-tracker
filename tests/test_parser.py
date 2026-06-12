from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from codex_usage_tracker.models import SessionInfo
from codex_usage_tracker.parser import (
    find_session_logs,
    inspect_log,
    load_session_index,
    parse_usage_events_from_file,
)

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
    assert "SECRET COMPACTION TEXT" not in json.dumps([event.to_row() for event in events])


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

    assert payload["adapter"] == "codex-jsonl-v1"
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

    assert "Adapter: codex-jsonl-v1" in result.stdout
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
    repo_root = Path(__file__).resolve().parents[1]
    src_path = str(repo_root / "src")
    env["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
        if env.get("PYTHONPATH")
        else src_path
    )
    return env
