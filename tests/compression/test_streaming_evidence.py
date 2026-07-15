from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from codex_usage_tracker.compression import streaming_evidence as streaming_evidence_module
from codex_usage_tracker.compression.detector_registry import default_detectors
from codex_usage_tracker.compression.estimators import (
    build_estimator_index,
    estimate_candidate,
)
from codex_usage_tracker.compression.evidence import load_compression_evidence
from codex_usage_tracker.compression.models import CompressionScope
from codex_usage_tracker.compression.run_builder import build_compression_run
from codex_usage_tracker.compression.run_cache import record_manifest
from codex_usage_tracker.compression.streaming_evidence import (
    load_streaming_compression_evidence,
)
from codex_usage_tracker.core.models import UsageEvent
from codex_usage_tracker.store.api import upsert_usage_events
from codex_usage_tracker.store.compression_fact_queries import (
    fold_compression_detector_facts,
)
from codex_usage_tracker.store.compression_fact_sync import (
    sync_content_plan_compression_facts,
)
from codex_usage_tracker.store.compression_facts import backfill_compression_detector_facts
from codex_usage_tracker.store.compression_schema import read_compression_source_generation
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.content_index_models import ContentIndexPlan
from codex_usage_tracker.store.schema import init_db


def test_streaming_evidence_preserves_manifest_and_detector_output(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(_usage_events(), db_path=db_path)
    _seed_normalized_evidence(db_path)
    scope = CompressionScope(include_archived=True)

    legacy = load_compression_evidence(db_path, scope)
    streamed = load_streaming_compression_evidence(db_path, scope, batch_size=2)
    with connect(db_path) as conn:
        backfill_compression_detector_facts(conn)
        fact_indexes = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx_compression_%_facts_%'"
            )
        }
    assert {
        "idx_compression_record_facts_scope",
        "idx_compression_record_facts_thread",
        "idx_compression_sequence_facts_scope",
        "idx_compression_sequence_facts_category",
        "idx_compression_thread_facts_activity",
    } <= fact_indexes
    fact_loader = getattr(streaming_evidence_module, "load_fact_compression_evidence", None)
    assert fact_loader is not None, "fact-backed compression loader is missing"
    fact_backed = fact_loader(db_path, scope)

    assert streamed.record_manifest == record_manifest(legacy)
    assert streamed.snapshot.coverage == legacy.coverage
    assert streamed.snapshot.source_revision == legacy.source_revision
    assert streamed.snapshot.calls == legacy.calls
    assert len(streamed.snapshot.tool_calls) < len(legacy.tool_calls)
    assert len(streamed.snapshot.content_fragments) < len(legacy.content_fragments)
    assert _detected_candidates(streamed.snapshot, scope) == _detected_candidates(legacy, scope)
    assert fact_backed.snapshot == streamed.snapshot
    assert fact_backed.record_manifest == streamed.record_manifest
    assert _detected_candidates(fact_backed.snapshot, scope) == _detected_candidates(
        streamed.snapshot, scope
    )


def test_v16_migration_defers_detector_fact_backfill(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(_usage_events(), db_path=db_path)
    _seed_normalized_evidence(db_path)
    expected_manifest = load_streaming_compression_evidence(
        db_path, CompressionScope(include_archived=True)
    ).record_manifest

    with connect(db_path) as conn:
        conn.executescript(
            """
            DROP TABLE compression_record_facts;
            DROP TABLE compression_sequence_facts;
            DROP TABLE compression_thread_facts;
            DELETE FROM schema_migrations WHERE version = 16;
            PRAGMA user_version = 15;
            """
        )
        init_db(conn)
        assert conn.execute("SELECT COUNT(*) FROM compression_record_facts").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM compression_sequence_facts").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM compression_thread_facts").fetchone()[0] == 0

        backfill_compression_detector_facts(conn)
        backfill_compression_detector_facts(conn)
        record_count = conn.execute("SELECT COUNT(*) FROM compression_record_facts").fetchone()[0]
        sequence_count = conn.execute("SELECT COUNT(*) FROM compression_sequence_facts").fetchone()[
            0
        ]
        thread_count = conn.execute("SELECT COUNT(*) FROM compression_thread_facts").fetchone()[0]
        thread_fact = conn.execute(
            """
            SELECT manifest_count, manifest_revision
            FROM compression_thread_facts
            WHERE manifest_key = 'thread:thread:one'
            """
        ).fetchone()

    assert record_count == 3
    assert sequence_count == 13
    assert thread_count == 1
    assert thread_fact is not None
    assert thread_fact["manifest_count"] == 21
    assert thread_fact["manifest_revision"] == expected_manifest["thread:thread:one"]["revision"]


def test_usage_upsert_keeps_detector_facts_at_the_current_generation(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"

    upsert_usage_events(_usage_events(), db_path=db_path)

    with connect(db_path) as conn:
        record_count = conn.execute("SELECT COUNT(*) FROM compression_record_facts").fetchone()[0]
        state = conn.execute(
            """
            SELECT facts_version, source_generation
            FROM compression_fact_state WHERE singleton = 1
            """
        ).fetchone()
        generation = read_compression_source_generation(conn)

    assert record_count == 3
    assert state is not None
    assert state["source_generation"] == generation


def test_usage_append_only_rebuilds_the_affected_record_facts(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    events = _usage_events()
    upsert_usage_events(events, db_path=db_path)
    with connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TRIGGER protect_existing_compression_facts
            BEFORE DELETE ON compression_record_facts
            WHEN OLD.record_id != 'call-3'
            BEGIN
                SELECT RAISE(ABORT, 'existing fact was rebuilt');
            END;
            """
        )

    appended_at = "2026-07-10T10:03:00+00:00"
    appended = replace(
        events[-1],
        record_id="call-3",
        event_timestamp=appended_at,
        line_number=4,
        previous_record_id="call-2",
        session_updated_at=appended_at,
        thread_call_index=4,
        turn_id="turn-3",
        turn_timestamp=appended_at,
    )
    upsert_usage_events([appended], db_path=db_path)

    with connect(db_path) as conn:
        record_ids = {
            str(row[0]) for row in conn.execute("SELECT record_id FROM compression_record_facts")
        }
    assert record_ids == {"call-0", "call-1", "call-2", "call-3"}


def test_content_fact_sync_invalidates_an_exact_cached_run(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(_usage_events(), db_path=db_path)
    _seed_normalized_evidence(db_path)
    with connect(db_path) as conn:
        backfill_compression_detector_facts(conn)

    scope = CompressionScope(include_archived=True)
    first = build_compression_run(db_path, scope)
    with connect(db_path) as conn:
        generation_before = read_compression_source_generation(conn)
        conn.execute(
            """
            INSERT INTO content_fragments (
                fragment_id, record_id, turn_key, fragment_kind, role, safe_label,
                content_hash, content_size_bytes, fragment_text, includes_raw_fragment,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "fragment-cache-invalidation",
                "call-2",
                "turn-2",
                "tool_output",
                "tool",
                "tool_output",
                "hash-cache-invalidation",
                20_000,
                "",
                0,
                "2026-07-10T10:02:10+00:00",
            ),
        )
        sync_content_plan_compression_facts(
            conn,
            plans=(ContentIndexPlan(source_path=Path("/tmp/synthetic/session.jsonl")),),
        )
        generation_after = read_compression_source_generation(conn)

    second = build_compression_run(db_path, scope)
    assert generation_after > generation_before
    assert second["run_id"] != first["run_id"]
    assert second["cache"]["mode"] != "exact"


def test_source_replacement_removes_orphaned_detector_facts(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(_usage_events(), db_path=db_path)

    upsert_usage_events(
        [],
        db_path=db_path,
        replace_source_files=[Path("/tmp/synthetic/session.jsonl")],
    )

    with connect(db_path) as conn:
        counts = {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "compression_record_facts",
                "compression_sequence_facts",
                "compression_thread_facts",
            )
        }
    assert counts == {
        "compression_record_facts": 0,
        "compression_sequence_facts": 0,
        "compression_thread_facts": 0,
    }


def test_partial_sequence_facts_fall_back_to_streaming_evidence(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(_usage_events(), db_path=db_path)
    _seed_normalized_evidence(db_path)
    scope = CompressionScope(include_archived=True)
    expected = load_streaming_compression_evidence(db_path, scope)
    with connect(db_path) as conn:
        backfill_compression_detector_facts(conn)
        conn.execute("DELETE FROM compression_sequence_facts WHERE fact_key = 'command:rg-0'")

    loaded = streaming_evidence_module.load_fact_compression_evidence(db_path, scope)
    assert loaded.snapshot == expected.snapshot
    assert loaded.record_manifest == expected.record_manifest


def test_fact_fold_excludes_copied_rows_from_all_history(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    events = _usage_events()
    copied = replace(
        events[0],
        record_id="call-copy",
        session_id="session-copy",
        source_file="/tmp/synthetic/copy.jsonl",
    )
    upsert_usage_events([*events, copied], db_path=db_path)
    _seed_normalized_evidence(db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO tool_calls (
                tool_call_key, record_id, turn_key, tool_name, status,
                output_size_bytes, parser_adapter, parser_version, parse_warnings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "tool-copy",
                "call-copy",
                "turn-0",
                "exec",
                "completed",
                20_000,
                "test",
                "1",
                "[]",
            ),
        )
        backfill_compression_detector_facts(conn)

    record_ids: list[str] = []
    sequence_record_ids: list[str] = []

    def collect(category: str, rows: list[Any]) -> None:
        target = record_ids if category == "records" else sequence_record_ids
        target.extend(str(row[0] if category == "records" else row[1]) for row in rows)

    metadata = fold_compression_detector_facts(
        db_path,
        scope=CompressionScope(include_archived=True).as_dict(),
        batch_size=2,
        consumer=collect,
    )

    assert metadata["ready"] is True
    assert record_ids == ["call-0", "call-1", "call-2"]
    assert "call-copy" not in sequence_record_ids


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
            ]
            + [
                (
                    "fragment-compaction-history",
                    "call-2",
                    "turn-2",
                    "compaction_history",
                    "system",
                    "compaction_history",
                    "hash-compaction-history",
                    800,
                    "",
                    0,
                    "2026-07-10T10:02:09+00:00",
                )
            ],
        )
