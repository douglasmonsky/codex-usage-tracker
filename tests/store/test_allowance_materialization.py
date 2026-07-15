import sqlite3
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from codex_usage_tracker.store import api as store_api
from codex_usage_tracker.store.allowance_materialization import materialize_allowance_intelligence
from codex_usage_tracker.store.api import connect, upsert_usage_events
from tests.store_dashboard_helpers import _usage_event


def test_materialization_is_canonical_idempotent_and_archive_safe(tmp_path):
    db = tmp_path / "usage.sqlite3"
    active = _usage_event(
        record_id="active",
        session_id="s",
        thread_key="t",
        event_timestamp="2025-12-31T23:58:00Z",
        cumulative_total_tokens=10,
        rate_limit_primary_used_percent=10.0,
        rate_limit_primary_window_minutes=10080,
        rate_limit_primary_resets_at=2_000_000_000,
    )
    archived = replace(
        _usage_event(
            record_id="archived",
            session_id="s2",
            thread_key="t2",
            event_timestamp="2025-12-31T23:59:00Z",
            cumulative_total_tokens=20,
            rate_limit_primary_used_percent=20.0,
            rate_limit_primary_window_minutes=10080,
            rate_limit_primary_resets_at=2_000_000_000,
        ),
        is_archived=True,
    )
    upsert_usage_events([active, archived], db)
    with connect(db) as conn:
        assert materialize_allowance_intelligence(
            conn, now=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert not materialize_allowance_intelligence(
            conn, now=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert (
            conn.execute("SELECT COUNT(*) FROM allowance_cycles WHERE is_archived=0").fetchone()[0]
            == 1
        )
        assert (
            conn.execute("SELECT COUNT(*) FROM allowance_cycles WHERE is_archived=1").fetchone()[0]
            == 1
        )
        assert (
            conn.execute("SELECT allowance_generation FROM allowance_source_state").fetchone()[0]
            == 1
        )


def test_allowance_package_retains_report_exports_after_store_imports():
    from codex_usage_tracker.allowance_intelligence import build_allowance_export_report

    assert callable(build_allowance_export_report)


def test_reconciliation_removes_noncanonical_evidence_without_mutating_physical_usage(tmp_path):
    db = tmp_path / "usage.sqlite3"
    canonical = _allowance_event("canonical", 10.0, 100)
    copied = replace(canonical, record_id="copied", session_id="copied", source_file="/tmp/copy.jsonl")
    upsert_usage_events([canonical, copied], db)

    with connect(db) as conn:
        physical_before = _physical_snapshot(conn)
        conn.execute(
            """
            INSERT INTO allowance_observations (
                observation_id, record_id, session_id, event_timestamp, line_number, source,
                window_key, window_kind, is_archived, input_tokens, cached_input_tokens,
                uncached_input_tokens, output_tokens, reasoning_output_tokens, total_tokens,
                cumulative_total_tokens
            ) VALUES ('copied:primary', 'copied', 'copied', '2026-01-01T00:00:00Z', 1,
                'test', 'primary', 'weekly', 0, 100, 20, 80, 10, 5, 110, 100)
            """
        )
        conn.execute(
            """INSERT INTO allowance_source_state
            VALUES (1, 99, 'stale', 99, '2000-01-01T00:00:00Z', 'stale', '2000-01-01T00:00:00Z')"""
        )
        conn.execute(
            """INSERT INTO allowance_cycles
            (cycle_id, window_kind, window_key, cohort_key, source_revision)
            VALUES ('stale-cycle', 'weekly', 'primary', 'codex', 'stale')"""
        )
        conn.execute(
            """INSERT INTO allowance_intervals
            (interval_id, cycle_id, window_kind, window_key, cohort_key, point_kind, source_revision)
            VALUES ('stale-interval', 'stale-cycle', 'weekly', 'primary', 'codex', 'observed', 'stale')"""
        )
        conn.execute(
            """INSERT INTO allowance_analysis_snapshots
            (snapshot_id, source_revision, model_version, archive_scope, window_kind, cohort_key,
             forecast_horizon, created_at)
            VALUES ('stale-snapshot', 'stale', 'stale', 'active', 'weekly', 'codex', 1,
                    '2000-01-01T00:00:00Z')"""
        )

        assert materialize_allowance_intelligence(conn, now=_NOW)
        assert [
            tuple(row) for row in conn.execute("SELECT record_id FROM allowance_observations")
        ] == [("canonical",)]
        assert [tuple(row) for row in conn.execute("SELECT cycle_id FROM allowance_cycles")] != [
            ("stale-cycle",)
        ]
        assert conn.execute("SELECT COUNT(*) FROM allowance_intervals").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM allowance_analysis_snapshots").fetchone()[0] == 0
        state = conn.execute(
            "SELECT allowance_generation, source_revision, observation_count FROM allowance_source_state"
        ).fetchone()
        assert tuple(state)[0] == 100
        assert tuple(state)[2] == 1
        assert _physical_snapshot(conn) == physical_before


def test_materialization_rolls_back_everything_when_interval_insert_fails(tmp_path):
    db = tmp_path / "usage.sqlite3"
    first = _allowance_event("first", 10.0, 100)
    upsert_usage_events([first], db)
    with connect(db) as conn:
        assert materialize_allowance_intelligence(conn, now=_NOW)

    second = _allowance_event("second", 20.0, 200, event_timestamp="2026-01-01T00:01:00Z")
    upsert_usage_events([second], db)
    with connect(db) as conn:
        before = _allowance_snapshot(conn)
        conn.execute(
            """CREATE TRIGGER fail_allowance_interval_insert
            BEFORE INSERT ON allowance_intervals
            BEGIN SELECT RAISE(ABORT, 'synthetic interval failure'); END"""
        )
        with pytest.raises(sqlite3.IntegrityError, match="synthetic interval failure"):
            materialize_allowance_intelligence(conn, now=_NOW)
        assert _allowance_snapshot(conn) == before


def test_empty_stream_finalization_reconciles_replaced_source_once(tmp_path, monkeypatch):
    db = tmp_path / "usage.sqlite3"
    event = _allowance_event("only", 10.0, 100)
    upsert_usage_events([event], db)
    with connect(db) as conn:
        assert materialize_allowance_intelligence(conn, now=_NOW)
        calls = 0
        real_materialize = store_api.materialize_allowance_intelligence

        def counted_materialize(connection):
            nonlocal calls
            calls += 1
            return real_materialize(connection, now=_NOW)

        monkeypatch.setattr(store_api, "materialize_allowance_intelligence", counted_materialize)
        result = store_api._upsert_usage_events_in_connection(
            conn, [], replace_source_files=[event.source_file]
        )
        assert result.record_ids == ()
        finalized = store_api._finalize_streamed_usage_event_upserts(
            conn, record_ids=result.record_ids, affected_thread_keys=result.affected_thread_keys
        )
        assert finalized.inserted_or_updated_events == 0
        assert calls == 1
        assert conn.execute("SELECT COUNT(*) FROM allowance_observations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM allowance_cycles").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM allowance_intervals").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM allowance_source_state").fetchone()[0] == 1


_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _allowance_event(
    record_id: str, used_percent: float, total: int, *, event_timestamp: str = "2026-01-01T00:00:00Z"
):
    return _usage_event(
        record_id=record_id,
        session_id=f"session-{record_id}",
        thread_key="thread:allowance",
        event_timestamp=event_timestamp,
        cumulative_total_tokens=total,
        rate_limit_limit_id="codex",
        rate_limit_primary_used_percent=used_percent,
        rate_limit_primary_window_minutes=10080,
        rate_limit_primary_resets_at=2_000_000_000,
    )


def _physical_snapshot(conn):
    return {
        table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY record_id")]
        for table in ("usage_events", "source_records")
    } | {
        "identity": [
            tuple(row)
            for row in conn.execute(
                """SELECT record_id, is_duplicate, canonical_record_id, duplicate_reason,
                          usage_fingerprint FROM usage_events ORDER BY record_id"""
            )
        ]
    }


def _allowance_snapshot(conn):
    return {
        table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1")]
        for table in (
            "allowance_observations",
            "allowance_cycles",
            "allowance_intervals",
            "allowance_analysis_snapshots",
            "allowance_source_state",
        )
    }
