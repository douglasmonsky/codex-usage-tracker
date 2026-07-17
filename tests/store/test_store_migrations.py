from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from codex_usage_tracker.diagnostics.api import run_doctor
from codex_usage_tracker.store import schema as schema_module
from codex_usage_tracker.store.api import (
    EVENT_COLUMNS,
    SchemaMigrationError,
    connect,
    export_usage_csv,
    init_db,
    query_dashboard_event_count,
    query_session_usage,
    query_source_records,
    refresh_metadata,
    refresh_usage_index,
    schema_state,
    upsert_usage_events,
)
from tests.store.test_usage_deduplication import _event

LEGACY_SESSION_ID = "019e3810-78be-7f32-a7d7-884d9bdba1fd"
NEW_SESSION_ID = "019e3811-5715-7018-a7bb-2232b46a5671"


def test_init_db_migrates_legacy_aggregate_table_without_data_loss(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _write_legacy_usage_database(db_path)

    with connect(db_path) as conn:
        init_db(conn)

    rows = query_session_usage(db_path=db_path, session_id=LEGACY_SESSION_ID)
    source_rows = query_source_records(db_path=db_path, limit=0)
    state = schema_state(db_path)
    metadata = refresh_metadata(db_path)

    assert len(rows) == 1
    assert rows[0]["record_id"] == "legacy-record"
    assert rows[0]["source_file"] == "/tmp/synthetic-session.jsonl"
    assert rows[0]["call_initiator"] is None
    assert rows[0]["call_initiator_reason"] is None
    assert rows[0]["call_initiator_confidence"] is None
    assert rows[0]["is_archived"] == 0
    assert rows[0]["thread_key"] is None
    assert rows[0]["thread_call_index"] is None
    assert rows[0]["previous_record_id"] is None
    assert rows[0]["next_record_id"] is None
    assert rows[0]["thread_source"] is None
    assert rows[0]["parent_thread_name"] is None
    assert rows[0]["model_context_window"] is None
    assert rows[0]["rate_limit_plan_type"] is None
    assert rows[0]["rate_limit_limit_id"] is None
    assert rows[0]["rate_limit_primary_used_percent"] is None
    assert rows[0]["rate_limit_secondary_used_percent"] is None
    assert len(source_rows) == 1
    assert source_rows[0]["record_id"] == "legacy-record"
    assert source_rows[0]["source_file"] == "/tmp/synthetic-session.jsonl"
    assert source_rows[0]["line_number"] == 12
    assert source_rows[0]["raw_shape_label"] == "token_count"
    assert source_rows[0]["parser_adapter"] == "codex-jsonl"
    assert source_rows[0]["parser_version"] == "codex-jsonl-v2"
    assert source_rows[0]["hash_basis"] == "source_file_id:line_number:record_id"
    assert len(str(source_rows[0]["source_record_hash"])) == 64
    assert metadata["parsed_events"] == "legacy"
    assert metadata["parser_invalid_integer"] == "2"
    assert state["schema_version"] == 31
    assert state["checksum_matches"] is True
    assert [row["version"] for row in state["migrations"]] == list(range(1, 32))
    with connect(db_path) as conn:
        init_db(conn)
        facts = conn.execute("SELECT COUNT(*) AS count FROM call_diagnostic_facts").fetchone()
        snapshots = conn.execute("SELECT COUNT(*) AS count FROM diagnostic_snapshots").fetchone()
        recommendation_facts = conn.execute(
            "SELECT COUNT(*) AS count FROM recommendation_facts"
        ).fetchone()
    assert facts is not None
    assert facts["count"] == 0
    assert snapshots is not None
    assert snapshots["count"] == 0
    assert recommendation_facts is not None
    assert recommendation_facts["count"] == 0


def test_refresh_is_idempotent_after_legacy_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    codex_home = _make_codex_home(tmp_path)
    _write_legacy_usage_database(db_path)

    first = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    first_count = query_dashboard_event_count(db_path=db_path)
    second = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    second_count = query_dashboard_event_count(db_path=db_path)
    legacy_rows = query_session_usage(db_path=db_path, session_id=LEGACY_SESSION_ID)
    new_rows = query_session_usage(db_path=db_path, session_id=NEW_SESSION_ID)
    metadata = refresh_metadata(db_path)

    assert first.parsed_events == 1
    assert second.parsed_events == 0
    assert second.inserted_or_updated_events == 0
    assert first_count == 2
    assert second_count == 2
    assert legacy_rows[0]["record_id"] == "legacy-record"
    assert new_rows[0]["thread_name"] == "Synthetic migration thread"
    assert metadata["schema_version"] == "31"
    assert metadata["parsed_events"] == "0"
    assert metadata["inserted_or_updated_events"] == "0"
    assert metadata["parsed_source_files"] == "0"
    assert metadata["skipped_source_files"] == "1"


def test_init_db_records_all_schema_migrations_for_new_database(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"

    with connect(db_path) as conn:
        init_db(conn)
        versions = [
            row[0]
            for row in conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
        ]
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        content_feature = conn.execute(
            "SELECT enabled FROM content_index_features WHERE feature_key = 'fts5'"
        ).fetchone()
        source_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(source_files)").fetchall()
        }
        revision_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(compression_revision_state)").fetchall()
        }
        thread_summary_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(thread_summaries)").fetchall()
        }
        usage_indexes = {
            row["name"] for row in conn.execute("PRAGMA index_list(usage_events)").fetchall()
        }
        recommendation_indexes = {
            row["name"]
            for row in conn.execute("PRAGMA index_list(recommendation_facts)").fetchall()
        }
        diagnostic_indexes = {
            row["name"]
            for row in conn.execute("PRAGMA index_list(call_diagnostic_facts)").fetchall()
        }
        allowance_observation_indexes = {
            row["name"]
            for row in conn.execute("PRAGMA index_list(allowance_observations)").fetchall()
        }
        cycle_indexes = {
            row["name"] for row in conn.execute("PRAGMA index_list(allowance_cycles)").fetchall()
        }
        interval_indexes = {
            row["name"] for row in conn.execute("PRAGMA index_list(allowance_intervals)").fetchall()
        }
        snapshot_indexes = {
            row["name"]
            for row in conn.execute("PRAGMA index_list(allowance_analysis_snapshots)").fetchall()
        }
        allowance_source_state_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(allowance_source_state)").fetchall()
        }
        allowance_cycle_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(allowance_cycles)").fetchall()
        }
        allowance_interval_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(allowance_intervals)").fetchall()
        }
        allowance_cycle_archive_column = conn.execute(
            "SELECT type, \"notnull\", dflt_value FROM pragma_table_info('allowance_cycles') "
            "WHERE name = 'is_archived'"
        ).fetchone()
        allowance_interval_archive_column = conn.execute(
            "SELECT type, \"notnull\", dflt_value FROM pragma_table_info('allowance_intervals') "
            "WHERE name = 'is_archived'"
        ).fetchone()
        cycle_latest_index_columns = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM pragma_index_info('idx_allowance_cycles_latest_cohort_window') "
                "ORDER BY seqno"
            ).fetchall()
        ]
        cycle_latest_window_index_columns = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM pragma_index_info('idx_allowance_cycles_latest_window') "
                "ORDER BY seqno"
            ).fetchall()
        ]
        cycle_series_index_columns = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM pragma_index_info('idx_allowance_cycles_series_cohort_window') "
                "ORDER BY seqno"
            ).fetchall()
        ]
        interval_evidence_index_columns = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM pragma_index_info('idx_allowance_intervals_evidence_cohort_window') "
                "ORDER BY seqno"
            ).fetchall()
        ]
        diagnostic_lookup_plan = [
            str(row["detail"])
            for row in conn.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT record_id
                FROM call_diagnostic_facts
                WHERE fact_type = ? AND fact_name = ?
                """,
                ("tool", "rg"),
            ).fetchall()
        ]
        allowance_newest_plan = [
            str(row["detail"])
            for row in conn.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT observation_id
                FROM allowance_observations
                WHERE is_archived = 0
                ORDER BY event_timestamp DESC, cumulative_total_tokens DESC, window_key DESC
                LIMIT 100
                """
            ).fetchall()
        ]
        allowance_window_newest_plan = [
            str(row["detail"])
            for row in conn.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT observation_id
                FROM allowance_observations
                WHERE is_archived = 0 AND window_kind = ?
                ORDER BY event_timestamp DESC, cumulative_total_tokens DESC, window_key DESC
                LIMIT 100
                """,
                ("primary",),
            ).fetchall()
        ]

    assert versions == list(range(1, 32))
    assert user_version == 31
    assert "idx_usage_source_file_line" in usage_indexes
    assert {
        "idx_recommendation_facts_rank_active",
        "idx_recommendation_facts_rank_all",
    } <= recommendation_indexes
    assert "idx_call_diagnostic_facts_lookup" in diagnostic_indexes
    assert "idx_call_diagnostic_facts_aggregate" in diagnostic_indexes
    assert {
        "idx_allowance_observations_active_newest",
        "idx_allowance_observations_active_window_newest",
    } <= allowance_observation_indexes
    assert {
        "idx_allowance_cycles_latest_cohort_window",
        "idx_allowance_cycles_latest_window",
        "idx_allowance_cycles_series_cohort_window",
        "idx_allowance_cycles_series_window",
        "idx_allowance_cycles_source_revision",
    } <= cycle_indexes
    assert {
        "idx_allowance_intervals_evidence_cohort_window",
        "idx_allowance_intervals_evidence_window",
    } <= interval_indexes
    assert "idx_allowance_intervals_source_revision" in interval_indexes
    assert "idx_allowance_analysis_snapshots_cache_key" in snapshot_indexes
    assert allowance_cycle_archive_column is not None
    assert tuple(allowance_cycle_archive_column) == ("INTEGER", 1, "0")
    assert allowance_interval_archive_column is not None
    assert tuple(allowance_interval_archive_column) == ("INTEGER", 1, "0")
    assert cycle_latest_index_columns == [
        "is_archived",
        "source_revision",
        "window_kind",
        "cohort_key",
        "last_observed_at",
        "cycle_id",
    ]
    assert cycle_latest_window_index_columns == [
        "is_archived",
        "source_revision",
        "window_kind",
        "last_observed_at",
        "cycle_id",
    ]
    assert cycle_series_index_columns == [
        "is_archived",
        "source_revision",
        "window_kind",
        "cohort_key",
        "first_observed_at",
        "cycle_id",
    ]
    assert interval_evidence_index_columns == [
        "is_archived",
        "source_revision",
        "window_kind",
        "cohort_key",
        "end_observed_at",
        "interval_id",
    ]
    assert {
        "allowance_generation",
        "source_revision",
        "observation_count",
        "latest_observed_at",
        "model_version",
        "rebuilt_at",
    } <= allowance_source_state_columns
    assert {
        "cycle_id",
        "window_kind",
        "window_key",
        "cohort_key",
        "reset_at",
        "reset_lower_bound",
        "reset_upper_bound",
        "first_observed_at",
        "last_observed_at",
        "start_used_percent",
        "latest_used_percent",
        "peak_used_percent",
        "observation_count",
        "conflict_count",
        "reversal_count",
        "censored_interval_count",
        "canonical_tokens",
        "canonical_credits",
        "priced_credits",
        "unpriced_credits",
        "price_coverage",
        "quality_grade",
        "cycle_state",
        "source_revision",
        "model_version",
        "is_archived",
    } <= allowance_cycle_columns
    assert {
        "interval_id",
        "cycle_id",
        "window_kind",
        "window_key",
        "cohort_key",
        "start_observation_id",
        "end_observation_id",
        "start_record_id",
        "end_record_id",
        "start_observed_at",
        "end_observed_at",
        "start_used_percent",
        "end_used_percent",
        "visible_percent_delta",
        "percent_resolution",
        "input_tokens",
        "cached_input_tokens",
        "uncached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
        "estimated_credits",
        "price_coverage",
        "confidence_mix",
        "interval_kind",
        "censor_reason",
        "simultaneous_conflict_count",
        "explained_movement",
        "unexplained_movement",
        "eligible_for_interpolation",
        "eligible_for_calibration",
        "eligible_for_forecasting",
        "eligible_for_change_detection",
        "source_revision",
        "model_version",
        "is_archived",
    } <= allowance_interval_columns
    assert any(
        "USING COVERING INDEX idx_call_diagnostic_facts_lookup" in detail
        for detail in diagnostic_lookup_plan
    )
    assert any(
        "idx_allowance_observations_active_newest" in detail
        for detail in allowance_newest_plan
    )
    assert any(
        "idx_allowance_observations_active_window_newest" in detail
        for detail in allowance_window_newest_plan
    )
    assert not any("USE TEMP B-TREE" in detail for detail in allowance_newest_plan)
    assert not any("USE TEMP B-TREE" in detail for detail in allowance_window_newest_plan)
    assert {
        "parsed_prefix_tail_hash",
        "parsed_row_count",
        "source_device",
        "source_generation",
        "source_inode",
    } <= source_columns
    assert {"call_generation", "command_generation", "file_generation"} <= revision_columns
    assert {
        "recommendation_score",
        "recommendation_total_tokens",
        "recommendation_summary_json",
    } <= thread_summary_columns
    assert {
        "content_index_features",
        "conversation_turns",
        "tool_calls",
        "command_runs",
        "file_events",
        "content_fragments",
        "investigation_runs",
        "compression_runs",
        "compression_candidates",
        "compression_candidate_records",
        "compression_record_facts",
        "compression_sequence_facts",
        "compression_thread_facts",
        "allowance_source_state",
        "allowance_cycles",
        "allowance_intervals",
        "allowance_analysis_snapshots",
    } <= tables
    assert content_feature is not None
    if int(content_feature["enabled"]):
        assert "content_fts" in tables


def test_init_db_upgrades_v25_database_without_changing_physical_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    event = _event("v25-record", "/synthetic/v25.jsonl")
    upsert_usage_events([event], db_path)

    with connect(db_path) as conn:
        before_usage = conn.execute(
            "SELECT record_id, source_file, line_number, event_timestamp FROM usage_events"
        ).fetchall()
        before_provenance = conn.execute(
            "SELECT record_id, source_file_id, line_number, source_record_hash FROM source_records"
        ).fetchall()
        conn.execute("DROP TABLE allowance_analysis_snapshots")
        conn.execute("DROP TABLE allowance_intervals")
        conn.execute("DROP TABLE allowance_cycles")
        conn.execute("DROP TABLE allowance_source_state")
        conn.execute("DROP INDEX idx_allowance_observations_active_newest")
        conn.execute("DROP INDEX idx_allowance_observations_active_window_newest")
        conn.execute("DELETE FROM schema_migrations WHERE version IN (26, 27, 28, 29, 30, 31)")
        conn.execute("PRAGMA user_version = 25")
        versions_before = [
            row[0]
            for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        ]

    with connect(db_path) as conn:
        init_db(conn)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        after_usage = conn.execute(
            "SELECT record_id, source_file, line_number, event_timestamp FROM usage_events"
        ).fetchall()
        after_provenance = conn.execute(
            "SELECT record_id, source_file_id, line_number, source_record_hash FROM source_records"
        ).fetchall()
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]

    assert versions_before == list(range(1, 26))
    assert user_version == 31
    assert {
        "allowance_source_state",
        "allowance_cycles",
        "allowance_intervals",
        "allowance_analysis_snapshots",
    } <= tables
    assert after_usage == before_usage
    assert after_provenance == before_provenance


def test_init_db_upgrades_v27_allowance_indexes_to_v28(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    with connect(db_path) as conn:
        init_db(conn)
        conn.executescript(
            """
            DROP INDEX idx_allowance_intervals_evidence_cohort;
            DROP INDEX idx_allowance_intervals_evidence_global;
            DELETE FROM schema_migrations WHERE version IN (28, 29, 30, 31);
            PRAGMA user_version = 27;
            """
        )
    with connect(db_path) as conn:
        init_db(conn)
        indexes = {
            row["name"] for row in conn.execute("PRAGMA index_list(allowance_intervals)")
        }
        versions = [
            row["version"]
            for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")
        ]
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]

    assert user_version == 31
    assert versions == list(range(1, 32))
    assert {
        "idx_allowance_intervals_evidence_cohort",
        "idx_allowance_intervals_evidence_global",
    } <= indexes


def test_init_db_upgrades_v28_with_allowance_plan_provenance(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    with connect(db_path) as conn:
        init_db(conn)
        conn.executescript(
            """
            ALTER TABLE allowance_cycles DROP COLUMN plan_type;
            DELETE FROM schema_migrations WHERE version IN (29, 30, 31);
            PRAGMA user_version = 28;
            """
        )

    with connect(db_path) as conn:
        init_db(conn)
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(allowance_cycles)")
        }
        versions = [
            row["version"]
            for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")
        ]
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]

    assert user_version == 31
    assert versions == list(range(1, 32))
    assert "plan_type" in columns


def test_init_db_does_not_rerun_applied_migrations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    with connect(db_path) as conn:
        init_db(conn)

    def fail_if_rerun(conn: sqlite3.Connection) -> None:
        raise AssertionError("init_db reran an applied migration")

    monkeypatch.setattr(
        schema_module,
        "_schema_migrations",
        lambda: tuple(
            (version, fail_if_rerun) for version in range(1, schema_module.SCHEMA_VERSION + 1)
        ),
    )

    with connect(db_path) as conn:
        init_db(conn)
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        recorded_count = conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]

    assert user_version == schema_module.SCHEMA_VERSION
    assert recorded_count == schema_module.SCHEMA_VERSION


def test_csv_export_keeps_current_columns_after_legacy_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    csv_path = tmp_path / "usage.csv"
    _write_legacy_usage_database(db_path)

    exported = export_usage_csv(csv_path, db_path=db_path)

    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert exported == 1
    assert rows[0]["record_id"] == "legacy-record"
    assert rows[0]["call_initiator"] == ""
    assert rows[0]["call_initiator_reason"] == ""
    assert rows[0]["call_initiator_confidence"] == ""
    assert rows[0]["is_archived"] == "0"
    assert rows[0]["thread_key"] == ""
    assert rows[0]["thread_call_index"] == ""
    assert rows[0]["previous_record_id"] == ""
    assert rows[0]["next_record_id"] == ""
    assert rows[0]["rate_limit_plan_type"] == ""
    assert rows[0]["rate_limit_primary_used_percent"] == ""
    assert rows[0]["service_tier"] == ""
    assert rows[0]["fast"] == ""
    assert rows[0]["service_tier_source"] == ""
    assert rows[0]["service_tier_confidence"] == ""
    assert list(rows[0]) == EVENT_COLUMNS


def test_malformed_legacy_schema_reports_actionable_error_without_data_loss(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _write_legacy_usage_database(db_path, omit_source_file=True)

    with (
        pytest.raises(SchemaMigrationError, match="missing required columns: source_file"),
        connect(db_path) as conn,
    ):
        init_db(conn)

    raw = sqlite3.connect(db_path)
    try:
        row_count = raw.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
        user_version = raw.execute("PRAGMA user_version").fetchone()[0]
    finally:
        raw.close()

    assert row_count == 1
    assert user_version == 1


def test_doctor_reports_malformed_legacy_schema_without_traceback(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _write_legacy_usage_database(db_path, omit_source_file=True)

    report = run_doctor(codex_home=tmp_path / ".codex", db_path=db_path)
    schema_check = _check_named(report, "Database schema")
    parser_check = _check_named(report, "Parser diagnostics")

    assert report["status"] == "fail"
    assert schema_check["status"] == "fail"
    assert "source_file" in str(schema_check["detail"])
    assert "rebuild-index" in str(schema_check["remediation"])
    assert parser_check["status"] == "fail"
    assert "database migration failed" in str(parser_check["detail"])


def _write_legacy_usage_database(db_path: Path, *, omit_source_file: bool = False) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        ("record_id", "TEXT PRIMARY KEY"),
        ("session_id", "TEXT NOT NULL"),
        ("event_timestamp", "TEXT NOT NULL"),
        ("source_file", "TEXT NOT NULL"),
        ("line_number", "INTEGER NOT NULL"),
        ("input_tokens", "INTEGER NOT NULL"),
        ("cached_input_tokens", "INTEGER NOT NULL"),
        ("output_tokens", "INTEGER NOT NULL"),
        ("reasoning_output_tokens", "INTEGER NOT NULL"),
        ("total_tokens", "INTEGER NOT NULL"),
        ("cumulative_input_tokens", "INTEGER NOT NULL"),
        ("cumulative_cached_input_tokens", "INTEGER NOT NULL"),
        ("cumulative_output_tokens", "INTEGER NOT NULL"),
        ("cumulative_reasoning_output_tokens", "INTEGER NOT NULL"),
        ("cumulative_total_tokens", "INTEGER NOT NULL"),
        ("uncached_input_tokens", "INTEGER NOT NULL"),
        ("cache_ratio", "REAL NOT NULL"),
        ("reasoning_output_ratio", "REAL NOT NULL"),
        ("context_window_percent", "REAL NOT NULL"),
    ]
    if omit_source_file:
        columns = [column for column in columns if column[0] != "source_file"]
    column_names = [name for name, _declaration in columns]
    values = {
        "record_id": "legacy-record",
        "session_id": LEGACY_SESSION_ID,
        "event_timestamp": "2026-05-17T18:58:27.000Z",
        "source_file": "/tmp/synthetic-session.jsonl",
        "line_number": 12,
        "input_tokens": 90,
        "cached_input_tokens": 20,
        "output_tokens": 10,
        "reasoning_output_tokens": 5,
        "total_tokens": 100,
        "cumulative_input_tokens": 90,
        "cumulative_cached_input_tokens": 20,
        "cumulative_output_tokens": 10,
        "cumulative_reasoning_output_tokens": 5,
        "cumulative_total_tokens": 100,
        "uncached_input_tokens": 70,
        "cache_ratio": 20 / 90,
        "reasoning_output_ratio": 0.5,
        "context_window_percent": 0.0,
    }
    raw = sqlite3.connect(db_path)
    try:
        raw.execute(f"CREATE TABLE usage_events ({_columns_sql(columns)})")
        raw.execute("CREATE TABLE refresh_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        raw.executemany(
            "INSERT INTO refresh_meta (key, value) VALUES (?, ?)",
            [
                ("parsed_events", "legacy"),
                ("parser_invalid_integer", "2"),
            ],
        )
        placeholders = ", ".join("?" for _name in column_names)
        raw.execute(
            f"INSERT INTO usage_events ({', '.join(column_names)}) VALUES ({placeholders})",
            [values[name] for name in column_names],
        )
        raw.execute("PRAGMA user_version = 1")
        raw.commit()
    finally:
        raw.close()


def _columns_sql(columns: list[tuple[str, str]]) -> str:
    return ", ".join(f"{name} {declaration}" for name, declaration in columns)


def _check_named(report: dict[str, object], name: str) -> dict[str, object]:
    checks = report["checks"]
    assert isinstance(checks, list)
    for check in checks:
        assert isinstance(check, dict)
        if check["name"] == name:
            return check
    raise AssertionError(f"missing doctor check: {name}")


def _make_codex_home(tmp_path: Path) -> Path:
    codex_home = tmp_path / ".codex"
    log_path = (
        codex_home
        / "sessions"
        / "2026"
        / "05"
        / "17"
        / f"rollout-2026-05-17T18-58-27-{NEW_SESSION_ID}.jsonl"
    )
    _write_jsonl(
        codex_home / "session_index.jsonl",
        [
            {
                "id": NEW_SESSION_ID,
                "thread_name": "Synthetic migration thread",
                "updated_at": "2026-05-17T19:00:00Z",
            }
        ],
    )
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": NEW_SESSION_ID}),
            _entry("turn_context", {"turn_id": "turn-a", "model": "gpt-5.5"}),
            _token_event(200, 200),
        ],
    )
    return codex_home


def _token_event(cumulative_total: int, last_total: int) -> dict[str, object]:
    return _entry(
        "event_msg",
        {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": cumulative_total - 20,
                    "cached_input_tokens": 40,
                    "output_tokens": 20,
                    "reasoning_output_tokens": 5,
                    "total_tokens": cumulative_total,
                },
                "last_token_usage": {
                    "input_tokens": last_total - 20,
                    "cached_input_tokens": 10,
                    "output_tokens": 20,
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
