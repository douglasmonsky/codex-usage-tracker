from __future__ import annotations

from pathlib import Path

from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db
from codex_usage_tracker.store.source_replacement import delete_usage_events_for_source_files

EXPECTED_FOREIGN_KEYS = {
    ("allowance_intervals", "cycle_id", "allowance_cycles", "cycle_id", "CASCADE"),
    ("allowance_observations", "record_id", "usage_events", "record_id", "CASCADE"),
    ("call_diagnostic_facts", "record_id", "usage_events", "record_id", "CASCADE"),
    ("command_runs", "record_id", "usage_events", "record_id", "CASCADE"),
    ("command_runs", "turn_key", "conversation_turns", "turn_key", "SET NULL"),
    (
        "compression_candidate_records",
        "candidate_id",
        "compression_candidates",
        "candidate_id",
        "CASCADE",
    ),
    ("compression_candidates", "run_id", "compression_runs", "run_id", "CASCADE"),
    ("compression_record_facts", "record_id", "usage_events", "record_id", "CASCADE"),
    ("compression_sequence_facts", "record_id", "usage_events", "record_id", "CASCADE"),
    ("content_fragments", "record_id", "usage_events", "record_id", "CASCADE"),
    ("content_fragments", "turn_key", "conversation_turns", "turn_key", "SET NULL"),
    ("conversation_turns", "record_id", "usage_events", "record_id", "CASCADE"),
    ("file_events", "record_id", "usage_events", "record_id", "CASCADE"),
    ("file_events", "turn_key", "conversation_turns", "turn_key", "SET NULL"),
    ("recommendation_facts", "record_id", "usage_events", "record_id", "CASCADE"),
    ("source_records", "record_id", "usage_events", "record_id", "CASCADE"),
    ("tool_calls", "record_id", "usage_events", "record_id", "CASCADE"),
    ("tool_calls", "turn_key", "conversation_turns", "turn_key", "SET NULL"),
}


def test_current_schema_declares_the_reviewed_foreign_key_inventory(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    with connect(db_path) as connection:
        init_db(connection)
        tables = [
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
        actual = {
            (
                table,
                str(row["from"]),
                str(row["table"]),
                str(row["to"]),
                str(row["on_delete"]),
            )
            for table in tables
            for row in connection.execute(f'PRAGMA foreign_key_list("{table}")')
        }

    assert actual == EXPECTED_FOREIGN_KEYS


def test_usage_cleanup_cascades_derived_rows_and_resets_otel_mapping(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    with connect(db_path) as connection:
        init_db(connection)
        _insert_usage_event(connection, record_id="record-1", source_file="/synthetic/one.jsonl")
        connection.execute(
            """
            INSERT INTO content_fragments (
                fragment_id, record_id, fragment_kind, content_hash, created_at
            ) VALUES ('fragment-1', 'record-1', 'message', 'hash-1', '2026-07-23T00:00:00Z')
            """
        )
        connection.execute(
            """
            INSERT INTO compression_record_facts (
                record_id, source_file, session_id, event_timestamp, facts_version, updated_at
            ) VALUES (
                'record-1', '/synthetic/one.jsonl', 'session-1',
                '2026-07-23T00:00:00Z', 1, '2026-07-23T00:00:00Z'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO recommendation_facts (
                record_id, event_timestamp, recommended_action_key, facts_version,
                algorithm_version, source_generation, generation_fingerprint,
                config_fingerprint, updated_at
            ) VALUES (
                'record-1', '2026-07-23T00:00:00Z', 'none', 1,
                1, 1, 'generation-1', 'config-1', '2026-07-23T00:00:00Z'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO allowance_observations (
                observation_id, record_id, session_id, event_timestamp,
                line_number, source, window_key, window_kind
            ) VALUES (
                'observation-1', 'record-1', 'session-1', '2026-07-23T00:00:00Z',
                1, 'synthetic', 'primary', 'rolling'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO otel_completion_events (
                fingerprint, source_path, source_line, match_status, matched_record_id
            ) VALUES ('otel-1', '/synthetic/otel.jsonl', 1, 'matched', 'record-1')
            """
        )

        delete_usage_events_for_source_files(connection, ["/synthetic/one.jsonl"])

        for table in (
            "usage_events",
            "content_fragments",
            "compression_record_facts",
            "recommendation_facts",
            "allowance_observations",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        otel = connection.execute(
            "SELECT match_status, matched_record_id FROM otel_completion_events"
        ).fetchone()
        assert tuple(otel) == ("pending", None)


def test_analysis_run_deletion_cascades_candidates_and_evidence(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    with connect(db_path) as connection:
        init_db(connection)
        connection.execute(
            """
            INSERT INTO compression_runs (
                run_id, status, source_revision, scope_hash, detector_set_version,
                estimator_version, compression_schema_version, scope_json,
                created_at, last_accessed_at
            ) VALUES (
                'run-1', 'completed', 'generation:1', 'scope-1', 'detectors-1',
                'estimator-1', 1, '{}', '2026-07-23T00:00:00Z', '2026-07-23T00:00:00Z'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO compression_candidates (
                candidate_id, run_id, family, pattern, pattern_key, rank,
                confidence_grade, confidence_score, observation_count,
                observed_exposure_tokens, observed_exposure_json,
                gross_low, gross_likely, gross_high, adjusted_low,
                adjusted_likely, adjusted_high, detector_version,
                estimator_version, estimator_tier, estimator_name,
                confidence_reasons_json, estimator_assumptions_json,
                evidence_handles_json, intervention_json, verification_json,
                warnings_json, overlaps_json, thread_keys_json
            ) VALUES (
                'candidate-1', 'run-1', 'synthetic', 'pattern', 'pattern-1', 1,
                'high', 1.0, 1, 10, '{}', 1, 2, 3, 1, 2, 3,
                'detector-1', 'estimator-1', 'exact', 'synthetic',
                '[]', '[]', '[]', '{}', '{}', '[]', '[]', '[]'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO compression_candidate_records (
                candidate_id, record_id, component, exposure_tokens,
                estimate_low, estimate_likely, estimate_high,
                evidence_role, trace_handle_json
            ) VALUES ('candidate-1', 'record-1', 'input', 10, 1, 2, 3, 'example', '{}')
            """
        )

        connection.execute("DELETE FROM compression_runs WHERE run_id = 'run-1'")

        assert connection.execute("SELECT COUNT(*) FROM compression_candidates").fetchone()[0] == 0
        assert (
            connection.execute("SELECT COUNT(*) FROM compression_candidate_records").fetchone()[0]
            == 0
        )


def _insert_usage_event(connection, *, record_id: str, source_file: str) -> None:
    connection.execute(
        """
        INSERT INTO usage_events (
            record_id, session_id, event_timestamp, source_file, line_number,
            input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens,
            total_tokens, cumulative_input_tokens, cumulative_cached_input_tokens,
            cumulative_output_tokens, cumulative_reasoning_output_tokens,
            cumulative_total_tokens, uncached_input_tokens, cache_ratio,
            reasoning_output_ratio, context_window_percent
        ) VALUES (
            ?, 'session-1', '2026-07-23T00:00:00Z', ?, 1,
            10, 4, 2, 1, 13, 10, 4, 2, 1, 13, 6, 0.4, 0.1, 0.01
        )
        """,
        (record_id, source_file),
    )
