from __future__ import annotations

from pathlib import Path

from codex_usage_tracker.core.models import UsageEvent
from codex_usage_tracker.store.api import upsert_usage_events
from codex_usage_tracker.store.compression_evidence import query_compression_evidence
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db


def test_evidence_query_deduplicates_calls_and_reports_normalized_coverage(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [
            usage_event("call-1", timestamp="2026-07-10T10:00:00+00:00"),
            usage_event(
                "call-archived",
                timestamp="2026-07-10T11:00:00+00:00",
                archived=True,
            ),
        ],
        db_path=db_path,
    )
    seed_normalized_evidence(db_path)

    payload = query_compression_evidence(
        db_path,
        scope={"include_archived": False, "thread": "thread:one"},
    )

    assert [row["record_id"] for row in payload["calls"]] == ["call-1"]
    assert len(payload["turns"]) == 1
    assert len(payload["tool_calls"]) == 1
    assert len(payload["command_runs"]) == 1
    assert len(payload["file_events"]) == 2
    assert len(payload["content_fragments"]) == 2
    assert [row["fragment_id"] for row in payload["compactions"]] == ["fragment-compaction"]
    assert payload["coverage"] == {
        "call_count": 1,
        "turn_count": 1,
        "tool_call_count": 1,
        "command_run_count": 1,
        "file_event_count": 2,
        "content_fragment_count": 2,
        "compaction_count": 1,
        "indexed_call_count": 1,
        "source_record_count": 1,
        "parser_warning_record_count": 1,
        "parser_adapters": ["codex-jsonl"],
        "parser_versions": ["codex-jsonl-v2"],
        "content_index_enabled": True,
    }


def test_evidence_query_applies_time_model_effort_and_archived_scope(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [
            usage_event("old", timestamp="2026-07-01T10:00:00+00:00"),
            usage_event(
                "recent",
                timestamp="2026-07-10T10:00:00+00:00",
                model="gpt-5.6",
                effort="medium",
            ),
            usage_event(
                "recent-archived",
                timestamp="2026-07-10T11:00:00+00:00",
                model="gpt-5.6",
                effort="medium",
                archived=True,
            ),
        ],
        db_path=db_path,
    )

    payload = query_compression_evidence(
        db_path,
        scope={
            "since": "2026-07-09T00:00:00+00:00",
            "model": "gpt-5.6",
            "effort": "medium",
            "include_archived": True,
        },
    )

    assert [row["record_id"] for row in payload["calls"]] == [
        "recent",
        "recent-archived",
    ]


def seed_normalized_evidence(db_path: Path) -> None:
    with connect(db_path) as conn:
        init_db(conn)
        conn.execute(
            """
            UPDATE source_records
            SET parse_warnings_json = '["synthetic warning"]'
            WHERE record_id = 'call-1'
            """
        )
        conn.execute(
            """
            INSERT INTO content_index_features(feature_key, enabled, detail, updated_at)
            VALUES ('fts5', 1, 'synthetic', '2026-07-10T10:00:00+00:00')
            ON CONFLICT(feature_key) DO UPDATE SET enabled = excluded.enabled
            """
        )
        conn.execute(
            """
            INSERT INTO conversation_turns (
                turn_key, record_id, session_id, turn_id, turn_index, role,
                event_timestamp, content_size_bytes, indexed_content_included,
                parser_adapter, parser_version, parse_warnings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "turn-1",
                "call-1",
                "session-1",
                "turn-call-1",
                1,
                "user",
                "2026-07-10T10:00:00+00:00",
                400,
                1,
                "codex-jsonl-v2",
                "2",
                "[]",
            ),
        )
        conn.execute(
            """
            INSERT INTO tool_calls (
                tool_call_key, record_id, turn_key, tool_name, status,
                output_size_bytes, parser_adapter, parser_version, parse_warnings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "tool-1",
                "call-1",
                "turn-1",
                "exec_command",
                "completed",
                800,
                "codex-jsonl-v2",
                "2",
                "[]",
            ),
        )
        conn.execute(
            """
            INSERT INTO command_runs (
                command_run_key, record_id, turn_key, command_root, command_label,
                exit_code, status, output_size_bytes, retry_group,
                parser_adapter, parser_version, parse_warnings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "command-1",
                "call-1",
                "turn-1",
                "rg",
                "rg tests",
                0,
                "completed",
                200,
                "retry-1",
                "codex-jsonl-v2",
                "2",
                "[]",
            ),
        )
        conn.executemany(
            """
            INSERT INTO file_events (
                file_event_key, record_id, turn_key, operation, path_hash,
                path_basename, path_extension, path_identity,
                parser_adapter, parser_version, parse_warnings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "file-1",
                    "call-1",
                    "turn-1",
                    "read",
                    "hash-a",
                    "one.py",
                    ".py",
                    "path:hash-a",
                    "codex-jsonl-v2",
                    "2",
                    "[]",
                ),
                (
                    "file-2",
                    "call-1",
                    "turn-1",
                    "read",
                    "hash-a",
                    "one.py",
                    ".py",
                    "path:hash-a",
                    "codex-jsonl-v2",
                    "2",
                    "[]",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO content_fragments (
                fragment_id, record_id, turn_key, fragment_kind, role, safe_label,
                content_hash, content_size_bytes, fragment_text, includes_raw_fragment,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "fragment-compaction",
                    "call-1",
                    "turn-1",
                    "compaction",
                    "system",
                    "compaction",
                    "content-a",
                    400,
                    "",
                    0,
                    "2026-07-10T10:00:00+00:00",
                ),
                (
                    "fragment-tool-output",
                    "call-1",
                    "turn-1",
                    "tool_output",
                    "tool",
                    "tool output",
                    "content-b",
                    800,
                    "",
                    0,
                    "2026-07-10T10:00:01+00:00",
                ),
            ],
        )


def usage_event(
    record_id: str,
    *,
    timestamp: str,
    model: str = "gpt-5.5",
    effort: str = "high",
    archived: bool = False,
) -> UsageEvent:
    return UsageEvent(
        record_id=record_id,
        session_id=f"session-{record_id}",
        thread_name="one",
        session_updated_at=timestamp,
        event_timestamp=timestamp,
        source_file=f"/tmp/synthetic/{record_id}.jsonl",
        line_number=1,
        turn_id=f"turn-{record_id}",
        turn_timestamp=timestamp,
        cwd="/tmp/project",
        model=model,
        effort=effort,
        current_date="2026-07-10",
        timezone="UTC",
        call_initiator="user",
        call_initiator_reason="user_message",
        call_initiator_confidence="high",
        is_archived=int(archived),
        thread_key="thread:one",
        thread_call_index=1,
        previous_record_id=None,
        next_record_id=None,
        thread_source="user",
        subagent_type=None,
        agent_role=None,
        agent_nickname=None,
        parent_session_id=None,
        parent_thread_name=None,
        parent_session_updated_at=None,
        model_context_window=200_000,
        input_tokens=1_000,
        cached_input_tokens=800,
        output_tokens=100,
        reasoning_output_tokens=20,
        total_tokens=1_100,
        cumulative_input_tokens=1_000,
        cumulative_cached_input_tokens=800,
        cumulative_output_tokens=100,
        cumulative_reasoning_output_tokens=20,
        cumulative_total_tokens=1_100,
    )
