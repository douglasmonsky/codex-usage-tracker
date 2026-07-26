"""Transactional materialization of reset-aware allowance evidence."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from codex_usage_tracker.allowance_intelligence.contracts import (
    AllowanceCohort,
    AllowanceCycle,
    AllowanceInterval,
)
from codex_usage_tracker.allowance_intelligence.cycles import (
    MODEL_VERSION,
    derive_allowance_cycles,
    derive_appended_intervals,
    observed_plan_type,
)
from codex_usage_tracker.allowance_intelligence.materialization_support import (
    INTERVAL_INSERT_SQL,
    append_revision,
    cycle_pricing,
    float_value,
    int_value,
    interval_pricing,
    interval_storage_row,
    interval_usage_rows,
    observation_positions,
    revision,
)
from codex_usage_tracker.pricing.allowance_config import load_allowance_config


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


def sync_refresh_allowance_intelligence(
    conn: sqlite3.Connection,
    record_ids: tuple[str, ...],
    _affected_thread_keys: frozenset[str],
    full_rebuild: bool,
) -> None:
    """Adapt allowance materialization to the store refresh callback contract."""
    if not record_ids and not full_rebuild and _refresh_materialization_is_current(conn):
        return
    if record_ids and not full_rebuild and _append_materialization(conn, record_ids):
        return
    materialize_allowance_intelligence(conn)


def _refresh_materialization_is_current(conn: sqlite3.Connection) -> bool:
    state = conn.execute(
        "SELECT model_version FROM allowance_source_state WHERE state_id = 1"
    ).fetchone()
    return state is not None and str(state["model_version"]) == MODEL_VERSION


def _append_materialization(
    conn: sqlite3.Connection,
    record_ids: tuple[str, ...],
) -> bool:
    state = conn.execute(
        "SELECT allowance_generation, source_revision, observation_count, "
        "latest_observed_at, model_version "
        "FROM allowance_source_state WHERE state_id = 1"
    ).fetchone()
    if state is None or str(state["model_version"]) != MODEL_VERSION:
        return False
    new_rows = _target_allowance_observations(conn, record_ids)
    if not new_rows:
        return _refresh_materialization_is_current(conn)
    latest = state["latest_observed_at"]
    if latest is not None and min(str(row["event_timestamp"]) for row in new_rows) <= str(latest):
        return False

    old_revision = str(state["source_revision"])
    source_revision = append_revision(old_revision, new_rows)
    if source_revision is None:
        return False
    allowance_config = load_allowance_config()
    appended: list[
        tuple[
            sqlite3.Row,
            AllowanceCycle,
            dict[str, object],
            list[dict[str, object]],
            tuple[dict[str, object], ...],
            list[AllowanceInterval],
        ]
    ] = []
    grouped = _group_allowance_observations(new_rows)
    for scope, scope_rows in sorted(grouped.items()):
        cycle_row = _existing_cycle(conn, scope=scope, source_revision=old_revision)
        if cycle_row is None:
            return False
        if min(str(row["event_timestamp"]) for row in scope_rows) <= str(
            cycle_row["last_observed_at"]
        ):
            return False
        cycle = _cycle_contract(cycle_row)
        anchor = _cycle_anchor(conn, cycle_row)
        if anchor is None:
            return False
        derivation_rows = _cycle_tail_observations(conn, cycle_row, anchor)
        target_ids = {str(row["observation_id"]) for row in scope_rows}
        if not target_ids.issubset(
            {str(row["observation_id"]) for row in derivation_rows}
        ):
            return False
        intervals = derive_appended_intervals(
            cycle,
            anchor=anchor,
            observations=derivation_rows,
        )
        appended.append(
            (cycle_row, cycle, anchor, scope_rows, derivation_rows, intervals)
        )

    conn.execute("DELETE FROM allowance_analysis_snapshots")
    conn.execute(
        "UPDATE allowance_cycles SET source_revision = ?, model_version = ? "
        "WHERE source_revision = ?",
        (source_revision, MODEL_VERSION, old_revision),
    )
    for cycle_row, cycle, anchor, scope_rows, derivation_rows, intervals in appended:
        combined = (anchor, *derivation_rows)
        positions = observation_positions(combined)
        interval_rows = []
        for interval in intervals:
            usage_rows = interval_usage_rows(
                combined,
                interval.start or {},
                interval.end or {},
                positions=positions,
            )
            pricing = interval_pricing(usage_rows, allowance_config)
            interval_rows.append(
                interval_storage_row(
                    interval,
                    cycle=cycle,
                    usage_rows=usage_rows,
                    pricing=pricing,
                    revision=source_revision,
                )
            )
        conn.executemany(INTERVAL_INSERT_SQL, interval_rows)
        _update_appended_cycle(
            conn,
            cycle_row=cycle_row,
            observations=scope_rows,
            intervals=intervals,
            revision=source_revision,
        )
    conn.execute(
        "INSERT OR REPLACE INTO allowance_source_state "
        "(state_id,allowance_generation,source_revision,observation_count,"
        "latest_observed_at,model_version,rebuilt_at) VALUES (1,?,?,?,?,?,?)",
        (
            int(state["allowance_generation"]) + 1,
            source_revision,
            int(state["observation_count"]) + len(new_rows),
            max(str(row["event_timestamp"]) for row in new_rows),
            MODEL_VERSION,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    return True

def _target_allowance_observations(
    conn: sqlite3.Connection,
    record_ids: tuple[str, ...],
) -> list[dict[str, object]]:
    conn.execute(
        """
        CREATE TEMP TABLE IF NOT EXISTS allowance_materialization_targets (
            record_id TEXT PRIMARY KEY
        ) WITHOUT ROWID
        """
    )
    conn.execute("DELETE FROM allowance_materialization_targets")
    conn.executemany(
        "INSERT OR IGNORE INTO allowance_materialization_targets(record_id) VALUES (?)",
        ((record_id,) for record_id in record_ids),
    )
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM allowance_observations "
            "WHERE record_id IN (SELECT record_id FROM allowance_materialization_targets) "
            "ORDER BY event_timestamp, cumulative_total_tokens, observation_id"
        )
    ]


def _group_allowance_observations(
    rows: list[dict[str, object]],
) -> dict[tuple[int, str, str, str, int | None], list[dict[str, object]]]:
    grouped: dict[
        tuple[int, str, str, str, int | None],
        list[dict[str, object]],
    ] = {}
    for row in rows:
        reset = row.get("resets_at")
        key = (
            int(bool(row.get("is_archived"))),
            str(row.get("window_kind") or "unknown"),
            str(row.get("window_key") or "primary"),
            str(row.get("limit_id") or "codex"),
            int(reset) if isinstance(reset, int | float) else None,
        )
        grouped.setdefault(key, []).append(row)
    return grouped


def _existing_cycle(
    conn: sqlite3.Connection,
    *,
    scope: tuple[int, str, str, str, int | None],
    source_revision: str,
) -> sqlite3.Row | None:
    archived, window_kind, window_key, cohort_key, reset_at = scope
    return conn.execute(
        "SELECT * FROM allowance_cycles "
        "WHERE is_archived = ? AND window_kind = ? AND window_key = ? "
        "AND cohort_key = ? AND reset_at IS ? AND source_revision = ? "
        "ORDER BY last_observed_at DESC, cycle_id DESC LIMIT 1",
        (
            archived,
            window_kind,
            window_key,
            cohort_key,
            reset_at,
            source_revision,
        ),
    ).fetchone()


def _cycle_contract(row: sqlite3.Row) -> AllowanceCycle:
    return AllowanceCycle(
        str(row["cycle_id"]),
        AllowanceCohort(
            str(row["cohort_key"]),
            str(row["window_kind"]),
            str(row["window_key"]),
            bool(row["is_archived"]),
            selected=str(row["cohort_key"]) == "codex",
        ),
        int(row["reset_at"]) if row["reset_at"] is not None else None,
        (),
        str(row["status"]),
    )


def _cycle_anchor(
    conn: sqlite3.Connection,
    cycle_row: sqlite3.Row,
) -> dict[str, object] | None:
    row = conn.execute(
        "SELECT observations.* FROM allowance_intervals AS intervals "
        "JOIN allowance_observations AS observations "
        "ON observations.observation_id = intervals.end_observation_id "
        "WHERE intervals.cycle_id = ? "
        "ORDER BY intervals.end_observed_at DESC, intervals.interval_id DESC LIMIT 1",
        (cycle_row["cycle_id"],),
    ).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT * FROM allowance_observations "
            "WHERE is_archived = ? AND window_kind = ? AND window_key = ? "
            "AND limit_id = ? AND resets_at IS ? "
            "ORDER BY event_timestamp, cumulative_total_tokens, observation_id LIMIT 1",
            (
                cycle_row["is_archived"],
                cycle_row["window_kind"],
                cycle_row["window_key"],
                cycle_row["cohort_key"],
                cycle_row["reset_at"],
            ),
        ).fetchone()
    return dict(row) if row is not None else None


def _cycle_tail_observations(
    conn: sqlite3.Connection,
    cycle_row: sqlite3.Row,
    anchor: dict[str, object],
) -> tuple[dict[str, object], ...]:
    return tuple(
        dict(row)
        for row in conn.execute(
            "SELECT * FROM allowance_observations "
            "WHERE is_archived = ? AND window_kind = ? AND window_key = ? "
            "AND limit_id = ? AND resets_at IS ? "
            "AND (event_timestamp, cumulative_total_tokens, observation_id) > (?, ?, ?) "
            "ORDER BY event_timestamp, cumulative_total_tokens, observation_id",
            (
                cycle_row["is_archived"],
                cycle_row["window_kind"],
                cycle_row["window_key"],
                cycle_row["cohort_key"],
                cycle_row["reset_at"],
                anchor.get("event_timestamp"),
                anchor.get("cumulative_total_tokens"),
                anchor.get("observation_id"),
            ),
        )
    )


def _update_appended_cycle(
    conn: sqlite3.Connection,
    *,
    cycle_row: sqlite3.Row,
    observations: list[dict[str, object]],
    intervals: list[Any],
    revision: str,
) -> None:
    latest = observations[-1]
    conflict = any(interval.point_kind.value == "conflict" for interval in intervals)
    status = "ambiguous" if conflict else str(cycle_row["status"])
    plan_type = _merged_plan_type(
        str(cycle_row["plan_type"] or "unknown"),
        observed_plan_type(observations),
    )
    conn.execute(
        "UPDATE allowance_cycles SET plan_type = ?, last_observed_at = ?, "
        "end_used_percent = ?, latest_used_percent = ?, peak_used_percent = ?, "
        "observation_count = observation_count + ?, "
        "conflict_count = MAX(conflict_count, ?), "
        "censored_interval_count = censored_interval_count + ?, "
        "canonical_observation_count = canonical_observation_count + ?, "
        "canonical_tokens = canonical_tokens + ?, quality_grade = ?, "
        "status = ?, cycle_state = ?, source_revision = ?, model_version = ? "
        "WHERE cycle_id = ?",
        (
            plan_type,
            latest.get("event_timestamp"),
            latest.get("used_percent"),
            latest.get("used_percent"),
            max(
                float_value(cycle_row["peak_used_percent"]),
                *(float_value(row.get("used_percent")) for row in observations),
            ),
            len(observations),
            int(conflict),
            sum(interval.censor_reason is not None for interval in intervals),
            len(observations),
            sum(int_value(row.get("total_tokens")) for row in observations),
            "ambiguous" if status == "ambiguous" else "high",
            status,
            status,
            revision,
            MODEL_VERSION,
            cycle_row["cycle_id"],
        ),
    )
    aggregate = conn.execute(
        "SELECT COALESCE(SUM(total_tokens), 0) AS total_tokens, "
        "COALESCE(SUM(total_tokens * COALESCE(price_coverage, 0)), 0) "
        "AS priced_tokens, SUM(estimated_credits) AS priced_credits "
        "FROM allowance_intervals WHERE cycle_id = ?",
        (cycle_row["cycle_id"],),
    ).fetchone()
    total_tokens = int(aggregate["total_tokens"])
    priced_tokens = float(aggregate["priced_tokens"])
    coverage = priced_tokens / total_tokens if total_tokens else None
    priced_credits = aggregate["priced_credits"]
    fully_priced = coverage is not None and coverage >= 1.0
    conn.execute(
        "UPDATE allowance_cycles SET canonical_credits = ?, priced_credits = ?, "
        "unpriced_credits = ?, price_coverage = ? WHERE cycle_id = ?",
        (
            priced_credits if fully_priced else None,
            priced_credits,
            0.0 if fully_priced else None,
            coverage,
            cycle_row["cycle_id"],
        ),
    )


def _merged_plan_type(existing: str, appended: str) -> str:
    if existing == appended:
        return existing
    if existing in {"", "unknown"}:
        return appended
    if appended in {"", "unknown"}:
        return existing
    return "mixed"


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
    source_revision = revision(rows)
    old = conn.execute(
        "SELECT source_revision, allowance_generation, model_version "
        "FROM allowance_source_state WHERE state_id=1"
    ).fetchone()
    changed = (
        old is None
        or str(old[0]) != source_revision
        or str(old[2]) != MODEL_VERSION
    )
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
    scopes: dict[tuple[bool, str, str, str], list[dict[str, object]]] = {}
    for row in rows:
        scope = (
            bool(row.get("is_archived")),
            str(row.get("window_kind") or "unknown"),
            str(row.get("window_key") or "primary"),
            str(row.get("limit_id") or "codex"),
        )
        scopes.setdefault(scope, []).append(row)
    for (archived, window_kind, window_key, cohort_key), scope_rows in sorted(scopes.items()):
        scope_cycles, scope_intervals = derive_allowance_cycles(
            scope_rows,
            now=now,
            existing_reset_epochs=existing_epochs,
            cohort=AllowanceCohort(
                cohort_key,
                window_kind,
                window_key,
                archived,
                selected=cohort_key == "codex",
            ),
        )
        cycles.extend(scope_cycles)
        intervals.extend(scope_intervals)
    allowance_config = load_allowance_config()
    cycles_by_id = {cycle.cycle_id: cycle for cycle in cycles}
    positions_by_cycle = {
        cycle.cycle_id: observation_positions(cycle.observations) for cycle in cycles
    }
    usage_by_interval: dict[str, tuple[dict[str, object], ...]] = {}
    pricing_by_interval: dict[str, dict[str, object]] = {}
    pricing_by_cycle: dict[str, list[dict[str, object]]] = {}
    for interval in intervals:
        cycle = cycles_by_id[interval.cycle_id]
        usage_rows = interval_usage_rows(
            cycle.observations,
            interval.start or {},
            interval.end or {},
            positions=positions_by_cycle[interval.cycle_id],
        )
        usage_by_interval[interval.interval_id] = usage_rows
        pricing_by_interval[interval.interval_id] = interval_pricing(
            usage_rows,
            allowance_config,
        )
        pricing_by_cycle.setdefault(interval.cycle_id, []).append(
            pricing_by_interval[interval.interval_id]
        )
    conn.execute("DELETE FROM allowance_analysis_snapshots")
    conn.execute("DELETE FROM allowance_intervals")
    conn.execute("DELETE FROM allowance_cycles")
    for cycle in cycles:
        observations = cycle.observations
        pricing = cycle_pricing(pricing_by_cycle.get(cycle.cycle_id, []))
        conn.execute(
            """INSERT INTO allowance_cycles (cycle_id,window_kind,window_key,cohort_key,plan_type,is_archived,reset_at,reset_lower_bound,reset_upper_bound,first_observed_at,last_observed_at,start_used_percent,end_used_percent,latest_used_percent,peak_used_percent,observation_count,conflict_count,reversal_count,censored_interval_count,canonical_observation_count,canonical_tokens,canonical_credits,priced_credits,unpriced_credits,price_coverage,quality_grade,status,cycle_state,source_revision,model_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                cycle.cycle_id,
                cycle.cohort.window_kind,
                cycle.cohort.window_key,
                cycle.cohort.key,
                observed_plan_type(observations),
                int(cycle.cohort.is_archived),
                cycle.reset_at,
                cycle.reset_at,
                cycle.reset_at,
                observations[0].get("event_timestamp"),
                observations[-1].get("event_timestamp"),
                observations[0].get("used_percent"),
                observations[-1].get("used_percent"),
                observations[-1].get("used_percent"),
                max(float_value(row.get("used_percent")) for row in observations),
                len(observations),
                int(cycle.status == "ambiguous"),
                0,
                sum(i.censor_reason is not None for i in intervals if i.cycle_id == cycle.cycle_id),
                len(observations),
                sum(int_value(row.get("total_tokens")) for row in observations),
                pricing["canonical_credits"],
                pricing["priced_credits"],
                pricing["unpriced_credits"],
                pricing["price_coverage"],
                "high" if cycle.status != "ambiguous" else "ambiguous",
                cycle.status,
                cycle.status,
                source_revision,
                MODEL_VERSION,
            ),
        )
    conn.executemany(
        """INSERT INTO allowance_intervals (interval_id,cycle_id,window_kind,window_key,cohort_key,is_archived,start_observation_id,end_observation_id,start_record_id,end_record_id,start_observed_at,end_observed_at,start_used_percent,end_used_percent,visible_percent_delta,percent_resolution,input_tokens,cached_input_tokens,uncached_input_tokens,output_tokens,reasoning_output_tokens,total_tokens,estimated_credits,price_coverage,confidence,confidence_mix,point_kind,interval_kind,censor_reason,simultaneous_conflict_count,explained_movement,unexplained_movement,eligible_for_interpolation,eligible_for_calibration,eligible_for_forecasting,eligible_for_change_detection,source_revision,model_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            interval_storage_row(
                interval,
                cycle=cycles_by_id[interval.cycle_id],
                usage_rows=usage_by_interval[interval.interval_id],
                pricing=pricing_by_interval[interval.interval_id],
                revision=source_revision,
            )
            for interval in intervals
        ),
    )
    generation = (int(old[1]) + 1) if old else 1
    conn.execute(
        "INSERT OR REPLACE INTO allowance_source_state (state_id,allowance_generation,source_revision,observation_count,latest_observed_at,model_version,rebuilt_at) VALUES (1,?,?,?,?,?,?)",
        (
            generation,
            source_revision,
            len(rows),
            rows[-1].get("event_timestamp") if rows else None,
            MODEL_VERSION,
            now.isoformat(),
        ),
    )
    return True
