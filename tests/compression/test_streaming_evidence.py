from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.compression.detector_registry import default_detectors
from codex_usage_tracker.compression.estimators import (
    build_estimator_index,
    estimate_candidate,
)
from codex_usage_tracker.compression.evidence import load_compression_evidence
from codex_usage_tracker.compression.models import CompressionScope
from codex_usage_tracker.compression.run_cache import record_manifest
from codex_usage_tracker.compression.streaming_evidence import (
    load_streaming_compression_evidence,
)
from codex_usage_tracker.core.models import UsageEvent
from codex_usage_tracker.store.api import upsert_usage_events
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db


def test_streaming_evidence_preserves_manifest_and_detector_output(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(_usage_events(), db_path=db_path)
    _seed_normalized_evidence(db_path)
    scope = CompressionScope(include_archived=True)

    legacy = load_compression_evidence(db_path, scope)
    streamed = load_streaming_compression_evidence(db_path, scope, batch_size=2)

    assert streamed.record_manifest == record_manifest(legacy)
    assert streamed.snapshot.coverage == legacy.coverage
    assert streamed.snapshot.source_revision == legacy.source_revision
    assert streamed.snapshot.calls == legacy.calls
    assert len(streamed.snapshot.tool_calls) < len(legacy.tool_calls)
    assert len(streamed.snapshot.content_fragments) < len(legacy.content_fragments)
    assert _detected_candidates(streamed.snapshot, scope) == _detected_candidates(legacy, scope)


def _detected_candidates(snapshot: Any, scope: CompressionScope) -> list[dict[str, Any]]:
    index = build_estimator_index(snapshot)
    return sorted(
        (
            estimate_candidate(candidate, snapshot, index=index).as_dict()
            for detector in default_detectors()
            for candidate in detector.detect(snapshot, scope)
        ),
        key=lambda candidate: str(candidate["candidate_id"]),
    )


def _usage_events() -> list[UsageEvent]:
    events = []
    for index in range(3):
        timestamp = f"2026-07-10T10:0{index}:00+00:00"
        events.append(
            UsageEvent(
                record_id=f"call-{index}",
                session_id="session-1",
                thread_name="one",
                session_updated_at=timestamp,
                event_timestamp=timestamp,
                source_file="/tmp/synthetic/session.jsonl",
                line_number=index + 1,
                turn_id=f"turn-{index}",
                turn_timestamp=timestamp,
                cwd="/tmp/project",
                model="gpt-5.5",
                effort="high",
                current_date="2026-07-10",
                timezone="UTC",
                call_initiator="user",
                call_initiator_reason="user_message",
                call_initiator_confidence="high",
                is_archived=0,
                thread_key="thread:one",
                thread_call_index=index + 1,
                previous_record_id=f"call-{index - 1}" if index else None,
                next_record_id=f"call-{index + 1}" if index < 2 else None,
                thread_source="user",
                subagent_type=None,
                agent_role=None,
                agent_nickname=None,
                parent_session_id=None,
                parent_thread_name=None,
                parent_session_updated_at=None,
                model_context_window=100_000,
                input_tokens=80_000,
                cached_input_tokens=70_000 if index == 0 else 1_000,
                output_tokens=100,
                reasoning_output_tokens=20,
                total_tokens=80_100,
                cumulative_input_tokens=80_000 * (index + 1),
                cumulative_cached_input_tokens=70_000 + (1_000 * index),
                cumulative_output_tokens=100 * (index + 1),
                cumulative_reasoning_output_tokens=20 * (index + 1),
                cumulative_total_tokens=80_100 * (index + 1),
            )
        )
    return events


def _seed_normalized_evidence(db_path: Path) -> None:
    with connect(db_path) as conn:
        init_db(conn)
        conn.executemany(
            """
            INSERT INTO tool_calls (
                tool_call_key, record_id, turn_key, tool_name, status,
                output_size_bytes, parser_adapter, parser_version, parse_warnings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("tool-small", "call-0", "turn-0", "exec", " ", 400, "test", "1", "[]"),
                (
                    "tool-large",
                    "call-1",
                    "turn-1",
                    "exec",
                    "completed",
                    20_000,
                    "test",
                    "1",
                    "[]",
                ),
            ],
        )
        command_rows = []
        for root, group in (("rg", "shell-group"), ("pytest", "test-group")):
            for index in range(3):
                command_rows.append(
                    (
                        f"{root}-{index}",
                        f"call-{index}",
                        f"turn-{index}",
                        root,
                        f"{root} synthetic",
                        0,
                        "completed",
                        400,
                        group,
                        "test",
                        "1",
                        "[]",
                    )
                )
        conn.executemany(
            """
            INSERT INTO command_runs (
                command_run_key, record_id, turn_key, command_root, command_label,
                exit_code, status, output_size_bytes, retry_group,
                parser_adapter, parser_version, parse_warnings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            command_rows,
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
                    f"file-{index}",
                    f"call-{index}",
                    f"turn-{index}",
                    "read",
                    "path-hash",
                    "example.py",
                    ".py",
                    "path:path-hash",
                    "test",
                    "1",
                    "[]",
                )
                for index in range(3)
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
                    f"fragment-{index}-{part}",
                    f"call-{index}",
                    f"turn-{index}",
                    "tool_output",
                    "tool",
                    "synthetic",
                    f"hash-{index}-{part}",
                    400 + part,
                    "",
                    0,
                    f"2026-07-10T10:0{index}:0{part}+00:00",
                )
                for index in range(3)
                for part in range(2)
            ],
        )
