"""Thin, deterministic payload services over materialized allowance queries."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from codex_usage_tracker.store.allowance_intelligence import (
    query_allowance_evidence,
    query_allowance_series,
    query_latest_allowance_state,
)

from .contracts import ALLOWANCE_EVIDENCE_SCHEMA, ALLOWANCE_SERIES_SCHEMA, ALLOWANCE_STATUS_SCHEMA
from .cycles import MODEL_VERSION
from .estimation import build_weekly_estimation

_PRESETS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "8w": timedelta(weeks=8), "6m": timedelta(days=183)}
_GRANULARITIES = {"auto", "raw", "hour", "day", "week", "month", "cycle"}
_AGING = {"weekly": 6 * 60 * 60, "five_hour": 15 * 60}


def build_allowance_status(connection: sqlite3.Connection, *, now: datetime, privacy_mode: str = "strict", include_archived: bool = False, since_revision: str | None = None) -> dict[str, Any]:
    """Return a constant-size current status; callers own connection lifetime."""
    revision = _revision(connection)
    if since_revision is not None and since_revision == revision:
        return {"schema": ALLOWANCE_STATUS_SCHEMA, "revision": revision, "changed": False}
    weekly = query_latest_allowance_state(connection, window_kind="weekly", include_archived=include_archived)
    five_hour = query_latest_allowance_state(connection, window_kind="five_hour", include_archived=include_archived)
    windows = {"weekly": _window(weekly, now), "five_hour": _window(five_hour, now) if five_hour else None}
    states = [entry["freshness"] for entry in windows.values() if entry]
    cohorts = _cohorts(connection, revision, include_archived, now)
    partial = bool(cohorts["reconciliation"]) or any(
        row["status"] in {"conflict", "reconciliation"}
        or row["cycle_state"] in {"conflict", "reconciliation"}
        or int(row["conflict_count"] or 0) > 0
        for row in cohorts["rows"]
    )
    data_state = "partial" if partial else _data_state(states)
    estimation = _weekly_estimation(connection, revision, include_archived, now)
    return {"schema": ALLOWANCE_STATUS_SCHEMA, "model_version": MODEL_VERSION, "generated_at": now.isoformat(), "data_as_of": _latest_at(windows), "revision": revision, "changed": True, "privacy_mode": privacy_mode, "include_archived": include_archived, "data_state": data_state, "weekly": windows["weekly"], "five_hour": windows["five_hour"], "estimation": estimation, "quality": {"canonical": True, "copied_rows_excluded": _copied_excluded(connection)}, "cohorts": {"selected": cohorts["selected"], "alternates": cohorts["alternates"], "reconciliation": cohorts["reconciliation"]}, "next": {"action": "poll_status", "poll_after_seconds": 30 if data_state in {"fresh", "aging", "partial"} else 60}}


def _weekly_estimation(connection: sqlite3.Connection, revision: str | None, include_archived: bool, now: datetime) -> dict[str, Any]:
    if revision is None:
        return build_weekly_estimation([], [], now=now)
    archive = "" if include_archived else "AND is_archived = 0"
    cycles = [dict(row) for row in connection.execute(f"SELECT * FROM allowance_cycles WHERE source_revision = ? {archive}", (revision,))]
    intervals = [dict(row) for row in connection.execute(f"SELECT * FROM allowance_intervals WHERE source_revision = ? {archive}", (revision,))]
    return build_weekly_estimation(cycles, intervals, now=now)


def build_allowance_series(connection: sqlite3.Connection, *, now: datetime, range_preset: str = "7d", start_at: str | None = None, end_at: str | None = None, granularity: str = "auto", window_kind: str = "weekly", cohort_id: str | None = None, include_archived: bool = False) -> dict[str, Any]:
    """Return observed cycle points only; estimates require later analysis services."""
    if granularity not in _GRANULARITIES:
        raise ValueError("granularity must be auto, raw, hour, day, week, month, or cycle")
    if range_preset not in _PRESETS and not (range_preset == "custom" and start_at and end_at):
        raise ValueError("range_preset must be 24h, 7d, 8w, 6m, or custom with start_at/end_at")
    end_at = end_at or now.isoformat()
    start_at = start_at or (now - _PRESETS[range_preset]).isoformat()
    start, end = _aware_timestamp(start_at), _aware_timestamp(end_at)
    if start >= end:
        raise ValueError("start_at must be before end_at")
    start_at, end_at = start.isoformat(), end.isoformat()
    cycles = query_allowance_series(connection, start_at=start_at, end_at=end_at, window_kind=window_kind, cohort_id=cohort_id, include_archived=include_archived)
    points = _series_points(cycles)
    return {"schema": ALLOWANCE_SERIES_SCHEMA, "model_version": MODEL_VERSION, "generated_at": now.isoformat(), "revision": _revision(connection), "requested_range": {"preset": range_preset, "start_at": start_at, "end_at": end_at}, "available_range": _available_range(cycles), "granularity": granularity, "truncated": False, "downsampled": False, "quality": {"observed_only": True}, "points": points, "cycles": [_cycle(row) for row in cycles]}


def build_allowance_evidence(connection: sqlite3.Connection, *, now: datetime | None = None, privacy_mode: str = "strict", limit: int = 50, cursor: str | None = None, window_kind: str | None = None, cohort_id: str | None = None, include_archived: bool = False) -> dict[str, Any]:
    """Return revision-bound local evidence, omitting identifiers in strict mode."""
    target = min(500, max(1, int(limit)))
    rows: list[dict[str, Any]] = []
    next_cursor = cursor
    while len(rows) < target:
        page = query_allowance_evidence(connection, limit=1, cursor=next_cursor, window_kind=window_kind, cohort_id=cohort_id, include_archived=include_archived)
        if not page.rows:
            next_cursor = None
            break
        raw = page.rows[0]
        next_cursor = page.next_cursor
        if raw.get("point_kind") in {"positive", "conflict", "censored"}:
            rows.append(_evidence_row(raw, privacy_mode))
        if next_cursor is None:
            break
    return {"schema": ALLOWANCE_EVIDENCE_SCHEMA, "model_version": MODEL_VERSION, "generated_at": (now or datetime.now(timezone.utc)).isoformat(), "revision": _revision(connection), "privacy_mode": privacy_mode, "rows": rows, "next_cursor": next_cursor, "copied_rows_excluded": _copied_excluded(connection), "provenance": "local" if privacy_mode != "strict" else "local_aggregate", "offline_export_action": "build_allowance_export_report"}


def _window(row: dict[str, Any] | None, now: datetime) -> dict[str, Any] | None:
    if row is None:
        return None
    observed = _parse(row["last_observed_at"])
    reset = row.get("reset_at")
    age = max(0, int((now - observed).total_seconds()))
    stale = age > _AGING[row["window_kind"]] or (
        isinstance(reset, (int, float)) and reset < now.timestamp()
    )
    freshness = "stale" if stale else ("fresh" if age <= 300 else "aging")
    used = row.get("latest_used_percent")
    return {"cohort_id": row["cohort_key"], "used_percent": used, "remaining_percent": None if used is None else max(0, 100 - float(used)), "reset_at": reset, "reset_countdown_seconds": max(0, int(reset - now.timestamp())) if isinstance(reset, (int, float)) else None, "observed_at": row["last_observed_at"], "age_seconds": age, "freshness": freshness, "status": row["status"], "pricing_coverage": row.get("price_coverage"), "quality": row.get("quality_grade"), "canonical_source_revision": row.get("source_revision")}


def _revision(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT source_revision FROM allowance_source_state WHERE state_id=1"
    ).fetchone()
    return str(row[0]) if row else None
def _parse(value: str) -> datetime: return datetime.fromisoformat(value.replace("Z", "+00:00"))
def _aware_timestamp(value: str) -> datetime:
    try:
        result = _parse(value)
    except (TypeError, ValueError) as error:
        raise ValueError("timestamps must be ISO-8601 timezone-aware values") from error
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timestamps must be ISO-8601 timezone-aware values")
    return result
def _data_state(states: list[str]) -> str: return "empty" if not states else ("stale" if all(s == "stale" for s in states) else ("aging" if "aging" in states else "fresh"))
def _latest_at(windows: dict[str, Any]) -> str | None: return max((entry["observed_at"] for entry in windows.values() if entry), default=None)
def _cohort(row: dict[str, Any] | None) -> dict[str, Any] | None: return None if row is None else {"id": row["cohort_key"], "window_kind": row["window_kind"], "window_key": row["window_key"], "archived": bool(row["is_archived"])}
def _cycle(row: dict[str, Any]) -> dict[str, Any]: return {key: row.get(key) for key in ("cycle_id", "reset_at", "first_observed_at", "last_observed_at", "latest_used_percent", "status", "quality_grade")}
def _available_range(rows: list[dict[str, Any]]) -> dict[str, str | None]: return {"start_at": rows[0]["first_observed_at"] if rows else None, "end_at": rows[-1]["last_observed_at"] if rows else None}
def _copied_excluded(conn: sqlite3.Connection) -> int:
    try:
        return int(
            conn.execute("SELECT count(*) FROM usage_events WHERE is_duplicate=1").fetchone()[0]
        )
    except sqlite3.OperationalError:
        return 0
def _evidence_row(row: dict[str, Any], privacy_mode: str) -> dict[str, Any]:
    keys = ("interval_id", "cycle_id", "window_kind", "cohort_key", "end_observed_at", "end_used_percent", "point_kind", "censor_reason", "source_revision")
    if privacy_mode == "strict":
        return {key: row.get(key) for key in ("window_kind", "end_observed_at", "end_used_percent", "point_kind", "censor_reason")}
    result = {key: row.get(key) for key in keys}
    if privacy_mode != "strict":
        result.update({key: row.get(key) for key in ("start_record_id", "end_record_id")})
    return result


def _series_points(cycles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for index, row in enumerate(cycles):
        if index:
            points.append({"kind": "reset", "cycle_id": row["cycle_id"], "observed_at": row["first_observed_at"], "reset_at": row["reset_at"]})
        points.append({"kind": "observed", "cycle_id": row["cycle_id"], "observed_at": row["last_observed_at"], "used_percent": row["latest_used_percent"], "reset_at": row["reset_at"]})
    return points


def _cohorts(
    connection: sqlite3.Connection,
    revision: str | None,
    include_archived: bool,
    now: datetime,
) -> dict[str, Any]:
    if revision is None:
        return {"selected": {}, "alternates": [], "reconciliation": [], "rows": []}
    archive = "" if include_archived else "AND is_archived = 0"
    rows = [dict(row) for row in connection.execute(f"SELECT * FROM allowance_cycles WHERE source_revision = ? {archive} ORDER BY last_observed_at DESC, cycle_id DESC", (revision,))]
    selected_rows: dict[str, dict[str, Any]] = {}
    for kind in ("weekly", "five_hour"):
        normal = next(
            (row for row in rows if row["window_kind"] == kind and row["cohort_key"] == "codex"),
            None,
        )
        fallback = next((row for row in rows if row["window_kind"] == kind), None)
        if normal or fallback:
            selected_rows[kind] = normal or fallback
    selected = {kind: _cohort(row) for kind, row in selected_rows.items()}
    alternates = []
    seen = {
        (row["cohort_key"], row["window_kind"], row["window_key"], bool(row["is_archived"]))
        for row in selected_rows.values()
    }
    for row in rows:
        diagnostic = _cohort(row)
        key = (diagnostic["id"], diagnostic["window_kind"], diagnostic["window_key"], diagnostic["archived"])
        if key not in seen:
            alternates.append(diagnostic)
            seen.add(key)
    reconciliation = []
    weekly = selected_rows.get("weekly")
    if weekly and weekly["cohort_key"] == "codex" and _window(weekly, now)["freshness"] == "stale":
        eligible = [
            row for row in rows
            if row["window_kind"] == "weekly"
            and row["cohort_key"] != "codex"
            and row["status"] == "accepted"
            and row["cycle_state"] == "accepted"
            and _window(row, now)["freshness"] != "stale"
            and _eligible_alternate(connection, row)
        ]
        if eligible:
            reconciliation.append({"window_kind": "weekly", "normal": _cohort(weekly), "eligible_alternate": _cohort(eligible[0]), "state": "normal_stale_alternate_available"})
    return {"selected": selected, "alternates": alternates, "reconciliation": reconciliation, "rows": rows}


def _eligible_alternate(connection: sqlite3.Connection, row: dict[str, Any]) -> bool:
    """Require Task 3's within-cycle, canonical observed movement evidence."""
    reset_at = row.get("reset_at")
    if not isinstance(reset_at, int):
        return False
    evidence = connection.execute(
        """
        SELECT COUNT(DISTINCT observation_id), COUNT(DISTINCT used_percent)
        FROM allowance_observations
        WHERE is_archived = ? AND window_kind = ? AND window_key = ?
          AND limit_id = ? AND resets_at = ?
        """,
        (
            int(bool(row["is_archived"])),
            row["window_kind"],
            row["window_key"],
            row["cohort_key"],
            reset_at,
        ),
    ).fetchone()
    return evidence is not None and int(evidence[0]) >= 3 and int(evidence[1]) > 1
