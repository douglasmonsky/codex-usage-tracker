"""Transactional materialization of reset-aware allowance evidence."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

from codex_usage_tracker.allowance_intelligence.cycles import MODEL_VERSION, derive_allowance_cycles


def materialize_allowance_intelligence(
    conn: sqlite3.Connection, *, now: datetime | None = None
) -> bool:
    """Reconcile canonical observations and replace derived evidence atomically.

    Returns whether canonical allowance input changed.  Derived rows are always
    rebuilt from that canonical input, never from physical copied usage rows.
    """
    now = now or datetime.now(timezone.utc)
    conn.execute("SAVEPOINT allowance_materialization")
    try:
        changed = _materialize(conn, now)
    except Exception:
        conn.execute("ROLLBACK TO allowance_materialization")
        conn.execute("RELEASE allowance_materialization")
        raise
    conn.execute("RELEASE allowance_materialization")
    return changed


def _materialize(conn: sqlite3.Connection, now: datetime) -> bool:
    conn.execute(
        "DELETE FROM allowance_observations WHERE record_id NOT IN (SELECT record_id FROM canonical_usage_events)"
    )
    rows = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM allowance_observations ORDER BY event_timestamp, cumulative_total_tokens, observation_id"
        )
    ]
    revision = _revision(rows)
    old = conn.execute(
        "SELECT source_revision, allowance_generation FROM allowance_source_state WHERE state_id=1"
    ).fetchone()
    changed = old is None or str(old[0]) != revision
    if not changed:
        return False
    existing_epochs: dict[tuple[bool, str, str, str], list[int]] = {}
    for row in conn.execute(
        "SELECT is_archived, window_kind, window_key, cohort_key, reset_at "
        "FROM allowance_cycles WHERE reset_at IS NOT NULL"
    ):
        existing_epochs.setdefault(
            (bool(row[0]), str(row[1]), str(row[2]), str(row[3])), []
        ).append(int(row[4]))
    cycles = []
    intervals = []
    for archived in (False, True):
        scope_cycles, scope_intervals = derive_allowance_cycles(
            [row for row in rows if bool(row.get("is_archived")) is archived],
            now=now,
            existing_reset_epochs=existing_epochs,
        )
        cycles.extend(scope_cycles)
        intervals.extend(scope_intervals)
    conn.execute("DELETE FROM allowance_analysis_snapshots")
    conn.execute("DELETE FROM allowance_intervals")
    conn.execute("DELETE FROM allowance_cycles")
    for cycle in cycles:
        observations = cycle.observations
        conn.execute(
            """INSERT INTO allowance_cycles (cycle_id,window_kind,window_key,cohort_key,is_archived,reset_at,reset_lower_bound,reset_upper_bound,first_observed_at,last_observed_at,start_used_percent,end_used_percent,latest_used_percent,peak_used_percent,observation_count,conflict_count,reversal_count,censored_interval_count,canonical_observation_count,canonical_tokens,canonical_credits,priced_credits,unpriced_credits,price_coverage,quality_grade,status,cycle_state,source_revision,model_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                cycle.cycle_id,
                cycle.cohort.window_kind,
                cycle.cohort.window_key,
                cycle.cohort.key,
                int(cycle.cohort.is_archived),
                cycle.reset_at,
                cycle.reset_at,
                cycle.reset_at,
                observations[0].get("event_timestamp"),
                observations[-1].get("event_timestamp"),
                observations[0].get("used_percent"),
                observations[-1].get("used_percent"),
                observations[-1].get("used_percent"),
                max(float(r.get("used_percent") or 0) for r in observations),
                len(observations),
                int(cycle.status == "conflict"),
                0,
                sum(i.censor_reason is not None for i in intervals if i.cycle_id == cycle.cycle_id),
                len(observations),
                sum(int(r.get("total_tokens") or 0) for r in observations),
                None,
                None,
                None,
                None,
                None,
                cycle.status,
                cycle.status,
                revision,
                MODEL_VERSION,
            ),
        )
    for interval in intervals:
        start, end = interval.start or {}, interval.end or {}
        conn.execute(
            """INSERT INTO allowance_intervals (interval_id,cycle_id,window_kind,window_key,cohort_key,is_archived,start_observation_id,end_observation_id,start_record_id,end_record_id,start_observed_at,end_observed_at,start_used_percent,end_used_percent,visible_percent_delta,percent_resolution,input_tokens,cached_input_tokens,uncached_input_tokens,output_tokens,reasoning_output_tokens,total_tokens,estimated_credits,price_coverage,confidence,confidence_mix,point_kind,interval_kind,censor_reason,simultaneous_conflict_count,explained_movement,unexplained_movement,eligible_for_interpolation,eligible_for_calibration,eligible_for_forecasting,eligible_for_change_detection,source_revision,model_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                interval.interval_id,
                interval.cycle_id,
                next(c.cohort.window_kind for c in cycles if c.cycle_id == interval.cycle_id),
                next(c.cohort.window_key for c in cycles if c.cycle_id == interval.cycle_id),
                next(c.cohort.key for c in cycles if c.cycle_id == interval.cycle_id),
                int(next(c.cohort.is_archived for c in cycles if c.cycle_id == interval.cycle_id)),
                start.get("observation_id"),
                end.get("observation_id"),
                start.get("record_id"),
                end.get("record_id"),
                start.get("event_timestamp"),
                end.get("event_timestamp"),
                start.get("used_percent"),
                end.get("used_percent"),
                float(end.get("used_percent") or 0) - float(start.get("used_percent") or 0),
                None,
                int(end.get("input_tokens") or 0),
                int(end.get("cached_input_tokens") or 0),
                int(end.get("uncached_input_tokens") or 0),
                int(end.get("output_tokens") or 0),
                int(end.get("reasoning_output_tokens") or 0),
                int(end.get("total_tokens") or 0),
                None,
                None,
                None,
                None,
                interval.point_kind.value,
                "observed",
                interval.censor_reason,
                0,
                None,
                None,
                int(interval.eligible_for_interpolation),
                0,
                0,
                0,
                revision,
                MODEL_VERSION,
            ),
        )
    generation = (int(old[1]) + 1) if old else 1
    conn.execute(
        "INSERT OR REPLACE INTO allowance_source_state (state_id,allowance_generation,source_revision,observation_count,latest_observed_at,model_version,rebuilt_at) VALUES (1,?,?,?,?,?,?)",
        (
            generation,
            revision,
            len(rows),
            rows[-1].get("event_timestamp") if rows else None,
            MODEL_VERSION,
            now.isoformat(),
        ),
    )
    return True


def _revision(rows: list[dict[str, object]]) -> str:
    fields = (
        "observation_id",
        "record_id",
        "event_timestamp",
        "window_key",
        "window_kind",
        "used_percent",
        "resets_at",
        "limit_id",
        "is_archived",
        "total_tokens",
        "cumulative_total_tokens",
    )
    canonical = [[row.get(field) for field in fields] for row in rows]
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
