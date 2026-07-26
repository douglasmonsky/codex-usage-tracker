import builtins
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from codex_usage_tracker.allowance_intelligence import (
    materialization,
    materialization_support,
)
from codex_usage_tracker.allowance_intelligence.cycles import MODEL_VERSION
from codex_usage_tracker.allowance_intelligence.service import build_allowance_status
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
        rate_limit_plan_type="pro",
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
            rate_limit_plan_type="pro",
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
        state = conn.execute(
            "SELECT quality_grade, status, cycle_state, plan_type FROM allowance_cycles "
            "WHERE is_archived = 0"
        ).fetchone()
        assert tuple(state) == ("high", "open", "open", "pro")
        conn.execute(
            "UPDATE allowance_source_state SET model_version = 'reset-aware-v2' WHERE state_id = 1"
        )
        assert materialize_allowance_intelligence(
            conn, now=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        generation, model_version = conn.execute(
            "SELECT allowance_generation, model_version FROM allowance_source_state"
        ).fetchone()
        assert (generation, model_version) == (2, MODEL_VERSION)
        assert not materialize_allowance_intelligence(
            conn, now=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )


def test_materialized_interval_sums_all_calls_between_allowance_anchors(tmp_path):
    db = tmp_path / "usage.sqlite3"
    events = [
        replace(
            _allowance_event("anchor", 10, 100, event_timestamp="2026-01-01T00:00:00Z"),
            input_tokens=80,
            output_tokens=20,
            total_tokens=100,
        ),
        replace(
            _allowance_event("middle", 10, 300, event_timestamp="2026-01-01T00:01:00Z"),
            input_tokens=150,
            output_tokens=50,
            total_tokens=200,
        ),
        replace(
            _allowance_event("end", 20, 600, event_timestamp="2026-01-01T00:02:00Z"),
            input_tokens=200,
            output_tokens=100,
            total_tokens=300,
        ),
    ]
    upsert_usage_events(events, db)
    with connect(db) as conn:
        assert materialize_allowance_intelligence(conn, now=_NOW)
        interval = conn.execute(
            "SELECT input_tokens, output_tokens, total_tokens, estimated_credits, "
            "price_coverage, eligible_for_calibration FROM allowance_intervals "
            "WHERE point_kind = 'positive'"
        ).fetchone()
        assert tuple(interval[:3]) == (350, 150, 500)
        assert interval[3] > 0
        assert interval[4:] == (1.0, 1)
        cycle = conn.execute(
            "SELECT canonical_credits, priced_credits, unpriced_credits, price_coverage "
            "FROM allowance_cycles WHERE is_archived = 0"
        ).fetchone()
        assert cycle[0] == cycle[1] and cycle[0] > 0
        assert tuple(cycle[2:]) == (0.0, 1.0)


def test_materialization_indexes_interval_anchors_once_per_cycle(tmp_path, monkeypatch):
    db = tmp_path / "usage.sqlite3"
    events = [
        _allowance_event(
            f"record-{index}",
            float(index % 100),
            (index + 1) * 100,
            event_timestamp=f"2026-01-01T{index // 3600:02d}:{index // 60 % 60:02d}:{index % 60:02d}Z",
        )
        for index in range(240)
    ]
    upsert_usage_events(events, db)
    visited = 0

    def counting_enumerate(iterable):
        nonlocal visited
        for item in builtins.enumerate(iterable):
            visited += 1
            yield item

    monkeypatch.setattr(
        materialization_support,
        "enumerate",
        counting_enumerate,
        raising=False,
    )
    with connect(db) as conn:
        assert materialize_allowance_intelligence(conn, now=_NOW)

    assert visited <= len(events) * 2


def test_unchanged_refresh_allowance_sync_stays_read_only_during_writer(tmp_path):
    db = tmp_path / "usage.sqlite3"
    upsert_usage_events([_allowance_event("current", 10, 100)], db)
    with connect(db) as conn:
        assert materialize_allowance_intelligence(conn, now=_NOW)

    writer = sqlite3.connect(db, timeout=0)
    writer.execute("BEGIN IMMEDIATE")
    try:
        with connect(db) as reader:
            materialization.sync_refresh_allowance_intelligence(
                reader,
                (),
                frozenset(),
                False,
            )
    finally:
        writer.rollback()
        writer.close()


def test_no_change_and_append_sync_do_not_run_history_aggregate_scans(tmp_path):
    db = tmp_path / "usage.sqlite3"
    initial = [
        _allowance_event(
            f"history-{index}",
            10 + index / 100,
            100 + index,
            event_timestamp=f"2026-01-01T00:{index:02d}:00Z",
        )
        for index in range(60)
    ]
    upsert_usage_events(initial, db)
    with connect(db) as conn:
        assert materialize_allowance_intelligence(conn, now=_NOW)

    with connect(db) as conn:
        statements: list[str] = []
        progress_steps = 0

        def count_step() -> int:
            nonlocal progress_steps
            progress_steps += 1
            return 0

        conn.set_trace_callback(statements.append)
        conn.set_progress_handler(count_step, 1)
        materialization.sync_refresh_allowance_intelligence(
            conn,
            (),
            frozenset(),
            False,
        )
        conn.set_progress_handler(None, 0)
        conn.set_trace_callback(None)

    assert progress_steps < 100
    assert not any(
        "COUNT(*)" in statement.upper()
        and "ALLOWANCE_OBSERVATIONS" in statement.upper()
        for statement in statements
    )
    assert not any(
        "MAX(EVENT_TIMESTAMP)" in statement.upper()
        and "ALLOWANCE_OBSERVATIONS" in statement.upper()
        for statement in statements
    )

    appended = _allowance_event(
        "history-tail",
        11,
        500,
        event_timestamp="2026-01-01T01:00:00Z",
    )
    upsert_usage_events([appended], db)
    with connect(db) as conn:
        statements = []
        conn.set_trace_callback(statements.append)
        materialization.sync_refresh_allowance_intelligence(
            conn,
            (appended.record_id,),
            frozenset(),
            False,
        )
        conn.set_trace_callback(None)
        state = conn.execute(
            "SELECT observation_count, latest_observed_at "
            "FROM allowance_source_state WHERE state_id = 1"
        ).fetchone()

    assert state is not None
    assert tuple(state) == (61, appended.event_timestamp)
    assert not any(
        (
            "COUNT(*)" in statement.upper()
            or "MAX(EVENT_TIMESTAMP)" in statement.upper()
        )
        and "ALLOWANCE_OBSERVATIONS" in statement.upper()
        for statement in statements
    )


def test_append_refresh_matches_full_allowance_materialization(tmp_path, monkeypatch):
    fast_db = tmp_path / "fast.sqlite3"
    full_db = tmp_path / "full.sqlite3"
    initial = [
        _allowance_event("anchor", 10, 100, event_timestamp="2026-01-01T00:00:00Z"),
        _allowance_event("prior-positive", 15, 200, event_timestamp="2026-01-01T00:01:00Z"),
        _allowance_event("prior-flat", 15, 300, event_timestamp="2026-01-01T00:02:00Z"),
    ]
    appended = [
        _allowance_event("positive", 20, 500, event_timestamp="2026-01-01T00:03:00Z"),
        _allowance_event("new-flat", 20, 800, event_timestamp="2026-01-01T00:04:00Z"),
        _allowance_event("reversal", 15, 1000, event_timestamp="2026-01-01T00:05:00Z"),
    ]
    for db in (fast_db, full_db):
        upsert_usage_events(initial, db)
        with connect(db) as conn:
            assert materialize_allowance_intelligence(conn, now=_NOW)
        upsert_usage_events(appended, db)

    def unexpected_full_materialization(*_args, **_kwargs):
        raise AssertionError("append-safe refresh fell back to full materialization")

    with connect(fast_db) as conn:
        monkeypatch.setattr(
            materialization,
            "materialize_allowance_intelligence",
            unexpected_full_materialization,
        )
        materialization.sync_refresh_allowance_intelligence(
            conn,
            tuple(event.record_id for event in appended),
            frozenset(),
            False,
        )
        fast_snapshot = _derived_allowance_snapshot(conn)

    with connect(full_db) as conn:
        assert materialize_allowance_intelligence(conn, now=_NOW)
        full_snapshot = _derived_allowance_snapshot(conn)

    assert fast_snapshot == full_snapshot


def test_unpriced_interval_stays_ineligible_for_calibration(tmp_path):
    db = tmp_path / "usage.sqlite3"
    events = [
        replace(
            _allowance_event("anchor", 10, 100, event_timestamp="2026-01-01T00:00:00Z"),
            model="synthetic-unpriced-model",
        ),
        replace(
            _allowance_event("end", 20, 300, event_timestamp="2026-01-01T00:01:00Z"),
            model="synthetic-unpriced-model",
        ),
    ]
    upsert_usage_events(events, db)
    with connect(db) as conn:
        assert materialize_allowance_intelligence(conn, now=_NOW)
        interval = conn.execute(
            "SELECT estimated_credits, price_coverage, eligible_for_calibration "
            "FROM allowance_intervals WHERE point_kind = 'positive'"
        ).fetchone()
        assert tuple(interval) == (None, 0.0, 0)


def test_materialized_pricing_reaches_the_status_estimator(tmp_path):
    db = tmp_path / "usage.sqlite3"
    events = [
        replace(
            _allowance_event("first-a", 10, 100, event_timestamp="2026-01-01T00:00:00Z"),
            rate_limit_primary_resets_at=1_767_227_400,
        ),
        replace(
            _allowance_event("first-b", 20, 300, event_timestamp="2026-01-01T00:01:00Z"),
            rate_limit_primary_resets_at=1_767_227_400,
        ),
        replace(
            _allowance_event("second-a", 5, 400, event_timestamp="2026-01-01T00:02:00Z"),
            rate_limit_primary_resets_at=1_767_229_200,
        ),
        replace(
            _allowance_event("second-b", 15, 700, event_timestamp="2026-01-01T00:03:00Z"),
            rate_limit_primary_resets_at=1_767_229_200,
        ),
    ]
    upsert_usage_events(events, db)
    now = datetime(2026, 1, 1, 2, tzinfo=timezone.utc)
    with connect(db) as conn:
        assert materialize_allowance_intelligence(conn, now=now)
        estimation = build_allowance_status(conn, now=now)["estimation"]
        assert estimation["capacity"]["completed_cycle_count"] == 2
        assert estimation["capacity"]["price_coverage"] == 1.0
        assert estimation["capacity"]["credits_per_percent"] > 0
        assert estimation["weekly_estimate"]["used_percent"] == 15.0


def test_materialization_preserves_each_window_and_cohort(tmp_path):
    db = tmp_path / "usage.sqlite3"
    normal = replace(
        _allowance_event("normal", 10, 100),
        rate_limit_secondary_used_percent=5,
        rate_limit_secondary_window_minutes=300,
        rate_limit_secondary_resets_at=2_000_000_000,
    )
    alternate = replace(
        _allowance_event(
            "alternate",
            15,
            200,
            event_timestamp="2026-01-01T00:01:00Z",
        ),
        rate_limit_limit_id="alternate",
    )
    upsert_usage_events([normal, alternate], db)
    with connect(db) as conn:
        assert materialize_allowance_intelligence(conn, now=_NOW)
        scopes = {
            tuple(row)
            for row in conn.execute("SELECT window_kind, cohort_key FROM allowance_cycles")
        }
        assert scopes == {
            ("weekly", "codex"),
            ("five_hour", "codex"),
            ("weekly", "alternate"),
        }


def test_allowance_package_retains_report_exports_after_store_imports():
    from codex_usage_tracker.allowance_intelligence import build_allowance_export_report

    assert callable(build_allowance_export_report)


def test_reconciliation_removes_noncanonical_evidence_without_mutating_physical_usage(tmp_path):
    db = tmp_path / "usage.sqlite3"
    canonical = _allowance_event("canonical", 10.0, 100)
    copied = replace(
        canonical, record_id="copied", session_id="copied", source_file="/tmp/copy.jsonl"
    )
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
        real_materialize = materialization.materialize_allowance_intelligence

        def counted_materialize(connection):
            nonlocal calls
            calls += 1
            return real_materialize(connection, now=_NOW)

        monkeypatch.setattr(
            materialization,
            "materialize_allowance_intelligence",
            counted_materialize,
        )
        result = store_api._upsert_usage_events_in_connection(
            conn, [], replace_source_files=[event.source_file]
        )
        assert result.record_ids == ()
        finalized = store_api._finalize_streamed_usage_event_upserts(
            conn, record_ids=result.record_ids, affected_thread_keys=result.affected_thread_keys
        )
        materialization.sync_refresh_allowance_intelligence(
            conn,
            finalized.record_ids,
            finalized.affected_thread_keys,
            True,
        )
        assert finalized.inserted_or_updated_events == 0
        assert calls == 1
        assert conn.execute("SELECT COUNT(*) FROM allowance_observations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM allowance_cycles").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM allowance_intervals").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM allowance_source_state").fetchone()[0] == 1


_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _allowance_event(
    record_id: str,
    used_percent: float,
    total: int,
    *,
    event_timestamp: str = "2026-01-01T00:00:00Z",
):
    return _usage_event(
        record_id=record_id,
        session_id=f"session-{record_id}",
        thread_key="thread:allowance",
        event_timestamp=event_timestamp,
        cumulative_total_tokens=total,
        rate_limit_limit_id="codex",
        rate_limit_plan_type="pro",
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


def _derived_allowance_snapshot(conn):
    interval_rows = []
    for row in conn.execute(
        "SELECT intervals.*, cycles.source_revision AS current_source_revision "
        "FROM allowance_intervals AS intervals "
        "JOIN allowance_cycles AS cycles ON cycles.cycle_id = intervals.cycle_id "
        "ORDER BY intervals.interval_id"
    ):
        interval = dict(row)
        interval["source_revision"] = interval.pop("current_source_revision")
        interval_rows.append(tuple(interval.values()))
    return {
        "cycles": [
            tuple(row) for row in conn.execute("SELECT * FROM allowance_cycles ORDER BY cycle_id")
        ],
        "intervals": interval_rows,
        "state": [
            tuple(row)
            for row in conn.execute(
                "SELECT allowance_generation, source_revision, observation_count, "
                "latest_observed_at, model_version FROM allowance_source_state"
            )
        ],
    }
