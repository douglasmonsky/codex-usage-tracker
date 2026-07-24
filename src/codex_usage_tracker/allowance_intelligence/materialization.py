"""Transactional materialization of reset-aware allowance evidence."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from codex_usage_tracker.allowance_intelligence.contracts import AllowanceCohort
from codex_usage_tracker.allowance_intelligence.cycles import (
    MODEL_VERSION,
    derive_allowance_cycles,
    observed_plan_type,
)
from codex_usage_tracker.pricing.allowance_config import load_allowance_config
from codex_usage_tracker.pricing.allowance_usage import annotate_rows_with_allowance


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
    _record_ids: tuple[str, ...],
    _affected_thread_keys: frozenset[str],
    _full_rebuild: bool,
) -> None:
    """Adapt allowance materialization to the store refresh callback contract."""
    materialize_allowance_intelligence(conn)


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
        "SELECT source_revision, allowance_generation, model_version "
        "FROM allowance_source_state WHERE state_id=1"
    ).fetchone()
    changed = old is None or str(old[0]) != revision or str(old[2]) != MODEL_VERSION
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
    usage_by_interval: dict[str, tuple[dict[str, object], ...]] = {}
    pricing_by_interval: dict[str, dict[str, object]] = {}
    pricing_by_cycle: dict[str, list[dict[str, object]]] = {}
    for interval in intervals:
        cycle = cycles_by_id[interval.cycle_id]
        usage_rows = _interval_usage_rows(
            cycle.observations,
            interval.start or {},
            interval.end or {},
        )
        usage_by_interval[interval.interval_id] = usage_rows
        pricing_by_interval[interval.interval_id] = _interval_pricing(
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
        cycle_pricing = _cycle_pricing(pricing_by_cycle.get(cycle.cycle_id, []))
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
                max(_float_value(row.get("used_percent")) for row in observations),
                len(observations),
                int(cycle.status == "ambiguous"),
                0,
                sum(i.censor_reason is not None for i in intervals if i.cycle_id == cycle.cycle_id),
                len(observations),
                sum(_int_value(row.get("total_tokens")) for row in observations),
                cycle_pricing["canonical_credits"],
                cycle_pricing["priced_credits"],
                cycle_pricing["unpriced_credits"],
                cycle_pricing["price_coverage"],
                "high" if cycle.status != "ambiguous" else "ambiguous",
                cycle.status,
                cycle.status,
                revision,
                MODEL_VERSION,
            ),
        )
    for interval in intervals:
        start, end = interval.start or {}, interval.end or {}
        cycle = cycles_by_id[interval.cycle_id]
        usage_rows = usage_by_interval[interval.interval_id]
        pricing = pricing_by_interval[interval.interval_id]
        conn.execute(
            """INSERT INTO allowance_intervals (interval_id,cycle_id,window_kind,window_key,cohort_key,is_archived,start_observation_id,end_observation_id,start_record_id,end_record_id,start_observed_at,end_observed_at,start_used_percent,end_used_percent,visible_percent_delta,percent_resolution,input_tokens,cached_input_tokens,uncached_input_tokens,output_tokens,reasoning_output_tokens,total_tokens,estimated_credits,price_coverage,confidence,confidence_mix,point_kind,interval_kind,censor_reason,simultaneous_conflict_count,explained_movement,unexplained_movement,eligible_for_interpolation,eligible_for_calibration,eligible_for_forecasting,eligible_for_change_detection,source_revision,model_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                interval.interval_id,
                interval.cycle_id,
                cycle.cohort.window_kind,
                cycle.cohort.window_key,
                cycle.cohort.key,
                int(cycle.cohort.is_archived),
                start.get("observation_id"),
                end.get("observation_id"),
                start.get("record_id"),
                end.get("record_id"),
                start.get("event_timestamp"),
                end.get("event_timestamp"),
                start.get("used_percent"),
                end.get("used_percent"),
                _float_value(end.get("used_percent")) - _float_value(start.get("used_percent")),
                None,
                sum(_int_value(row.get("input_tokens")) for row in usage_rows),
                sum(_int_value(row.get("cached_input_tokens")) for row in usage_rows),
                sum(_int_value(row.get("uncached_input_tokens")) for row in usage_rows),
                sum(_int_value(row.get("output_tokens")) for row in usage_rows),
                sum(_int_value(row.get("reasoning_output_tokens")) for row in usage_rows),
                sum(_int_value(row.get("total_tokens")) for row in usage_rows),
                pricing["estimated_credits"],
                pricing["price_coverage"],
                pricing["confidence"],
                pricing["confidence_mix"],
                interval.point_kind.value,
                "observed",
                interval.censor_reason,
                0,
                None,
                None,
                int(interval.eligible_for_interpolation),
                int(interval.eligible_for_interpolation and bool(pricing["supported"])),
                int(interval.eligible_for_interpolation and bool(pricing["supported"])),
                int(interval.eligible_for_interpolation and bool(pricing["supported"])),
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


def _interval_usage_rows(
    observations: tuple[dict[str, object], ...],
    start: dict[str, object],
    end: dict[str, object],
) -> tuple[dict[str, object], ...]:
    """Return canonical calls after the start anchor through the end anchor."""
    start_id = start.get("observation_id")
    end_id = end.get("observation_id")
    start_index = next(
        (index for index, row in enumerate(observations) if row.get("observation_id") == start_id),
        None,
    )
    end_index = next(
        (index for index, row in enumerate(observations) if row.get("observation_id") == end_id),
        None,
    )
    if start_index is None or end_index is None or end_index <= start_index:
        return (end,) if end else ()
    return observations[start_index + 1 : end_index + 1]


def _interval_pricing(
    rows: tuple[dict[str, object], ...], allowance_config: Any
) -> dict[str, object]:
    annotated = annotate_rows_with_allowance(
        [dict(row) for row in rows],
        allowance_config,
    )
    total_tokens = sum(int(row.get("total_tokens") or 0) for row in annotated)
    priced = [row for row in annotated if row.get("usage_credits") is not None]
    priced_tokens = sum(int(row.get("total_tokens") or 0) for row in priced)
    coverage = priced_tokens / total_tokens if total_tokens > 0 else 0.0
    credits = sum(float(row.get("usage_credits") or 0) for row in priced)
    mix: dict[str, int] = {}
    weighted_confidence = 0.0
    for row in annotated:
        label = str(row.get("usage_credit_confidence") or "unpriced")
        mix[label] = mix.get(label, 0) + 1
        tokens = int(row.get("total_tokens") or 0)
        weighted_confidence += tokens * _pricing_confidence_score(label)
    confidence = weighted_confidence / total_tokens if total_tokens > 0 else 0.0
    return {
        "estimated_credits": credits if priced else None,
        "price_coverage": coverage,
        "confidence": confidence,
        "confidence_mix": json.dumps(mix, sort_keys=True, separators=(",", ":")),
        "supported": coverage >= 0.95 and confidence >= 0.5,
        "total_tokens": total_tokens,
        "priced_tokens": priced_tokens,
    }


def _cycle_pricing(intervals: list[dict[str, object]]) -> dict[str, float | None]:
    total_tokens = sum(_int_value(row["total_tokens"]) for row in intervals)
    priced_tokens = sum(_int_value(row["priced_tokens"]) for row in intervals)
    coverage = priced_tokens / total_tokens if total_tokens > 0 else None
    priced_credits = sum(_float_value(row["estimated_credits"]) for row in intervals)
    has_priced = any(row["estimated_credits"] is not None for row in intervals)
    fully_priced = coverage is not None and coverage >= 1.0
    return {
        "canonical_credits": priced_credits if fully_priced else None,
        "priced_credits": priced_credits if has_priced else None,
        "unpriced_credits": 0.0 if fully_priced else None,
        "price_coverage": coverage,
    }


def _pricing_confidence_score(label: str) -> float:
    return {
        "exact": 1.0,
        "user_override": 1.0,
        "inferred": 0.85,
        "alias": 0.85,
        "estimated": 0.65,
        "unpriced": 0.0,
    }.get(label, 0.5)


def _int_value(value: object) -> int:
    return int(value) if isinstance(value, int | float) else 0


def _float_value(value: object) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


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
        "model",
        "effort",
        "input_tokens",
        "cached_input_tokens",
        "uncached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
        "cumulative_total_tokens",
    )
    canonical = [[row.get(field) for field in fields] for row in rows]
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
