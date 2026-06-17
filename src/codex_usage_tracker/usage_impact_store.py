"""Persistent read model for estimated usage-impact rows."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store_schema import init_db

USAGE_IMPACT_SCHEMA_ID = "codex-usage-tracker-usage-impact-v1"
WINDOW_TYPES = ("primary", "secondary")
PENDING_REASON = "Usage-impact read model pending recalculation after refresh."
STALE_REASON = "Usage-impact read model stale after source refresh."
UNAVAILABLE_REASON = "No compatible observed usage snapshots for this call/window."

USAGE_IMPACT_COLUMNS = [
    "record_id",
    "window_type",
    "plan_type",
    "limit_id",
    "observed_used_percent",
    "observed_window_minutes",
    "observed_resets_at",
    "previous_observed_record_id",
    "previous_observed_used_percent",
    "next_observed_record_id",
    "delta_used_percent",
    "tokens_since_previous",
    "estimated_tokens_per_percent",
    "estimated_usage_credits",
    "estimated_usage_percent",
    "lower_percent",
    "upper_percent",
    "basis",
    "source",
    "interval_call_count",
    "confidence",
    "status",
    "reason",
    "recalculated_at",
]


def usage_impact_payload(
    rows: list[dict[str, Any]],
    *,
    record_id: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Return a stable JSON usage-impact payload."""

    return {
        "schema": USAGE_IMPACT_SCHEMA_ID,
        "record_id": record_id,
        "limit": limit,
        "row_count": len(rows),
        "rows": rows,
        "raw_context_included": False,
    }


def replace_usage_impact_from_annotated_rows(
    db_path: Path = DEFAULT_DB_PATH,
    rows: Iterable[dict[str, Any]] = (),
) -> dict[str, int]:
    """Replace read-model rows for annotated aggregate usage rows."""

    materialized = materialize_usage_impact_rows(rows)
    record_ids = sorted({row["record_id"] for row in materialized})
    with _connect(db_path) as conn:
        init_db(conn)
        if record_ids:
            delete_usage_impact_for_records(conn, record_ids)
        upsert_usage_impact_rows(conn, materialized)
    return {
        "records": len(record_ids),
        "rows": len(materialized),
    }


def replace_usage_impact_for_records_from_annotated_rows(
    db_path: Path = DEFAULT_DB_PATH,
    rows: Iterable[dict[str, Any]] = (),
    *,
    record_ids: Iterable[str] = (),
) -> dict[str, int]:
    """Replace read-model rows only for selected records from annotated context."""

    target_ids = sorted({record_id for record_id in record_ids if record_id})
    if not target_ids:
        return {"records": 0, "rows": 0}
    target_set = set(target_ids)
    materialized = [
        row
        for row in materialize_usage_impact_rows(rows)
        if str(row.get("record_id") or "") in target_set
    ]
    with _connect(db_path) as conn:
        init_db(conn)
        delete_usage_impact_for_records(conn, target_ids)
        upsert_usage_impact_rows(conn, materialized)
    return {
        "records": len(target_ids),
        "rows": len(materialized),
    }


def materialize_usage_impact_rows(
    rows: Iterable[dict[str, Any]],
    *,
    recalculated_at: str | None = None,
) -> list[dict[str, Any]]:
    """Build persistent usage-impact rows from annotated aggregate rows."""

    timestamp = recalculated_at or _utc_now()
    materialized: list[dict[str, Any]] = []
    for row in rows:
        record_id = _optional_str(row.get("record_id"))
        if record_id is None:
            continue
        impact = row.get("usage_impact")
        impact_by_window = impact if isinstance(impact, dict) else {}
        for window_type in WINDOW_TYPES:
            window_impact = impact_by_window.get(window_type)
            window = window_impact if isinstance(window_impact, dict) else None
            materialized.append(
                _materialize_window(
                    row,
                    record_id=record_id,
                    window_type=window_type,
                    impact=window,
                    recalculated_at=timestamp,
                )
            )
    return materialized


def upsert_usage_impact_rows(
    conn: sqlite3.Connection,
    rows: Iterable[dict[str, Any]],
) -> int:
    """Upsert usage-impact read-model rows."""

    materialized = list(rows)
    if not materialized:
        return 0
    placeholders = ", ".join("?" for _column in USAGE_IMPACT_COLUMNS)
    updates = ", ".join(
        f"{column}=excluded.{column}"
        for column in USAGE_IMPACT_COLUMNS
        if column not in {"record_id", "window_type"}
    )
    conn.executemany(
        f"""
        INSERT INTO usage_impact ({', '.join(USAGE_IMPACT_COLUMNS)})
        VALUES ({placeholders})
        ON CONFLICT(record_id, window_type) DO UPDATE SET {updates}
        """,
        [[row.get(column) for column in USAGE_IMPACT_COLUMNS] for row in materialized],
    )
    return len(materialized)


def delete_usage_impact_for_records(
    conn: sqlite3.Connection,
    record_ids: Iterable[str],
) -> int:
    """Delete read-model rows for usage record ids."""

    ids = sorted({record_id for record_id in record_ids if record_id})
    if not ids:
        return 0
    placeholders = ", ".join("?" for _record_id in ids)
    before = conn.total_changes
    conn.execute(
        f"DELETE FROM usage_impact WHERE record_id IN ({placeholders})",
        ids,
    )
    return conn.total_changes - before


def invalidate_usage_impact_for_delta(
    conn: sqlite3.Connection,
    *,
    inserted_record_ids: Iterable[str] = (),
    deleted_record_ids: Iterable[str] = (),
    changed_time_start: str | None = None,
    changed_time_end: str | None = None,
) -> int:
    """Mark usage-impact rows affected by a refresh delta as pending/stale."""

    deleted = sorted({record_id for record_id in deleted_record_ids if record_id})
    inserted = sorted({record_id for record_id in inserted_record_ids if record_id})
    changed = 0
    changed += delete_usage_impact_for_records(conn, deleted)
    changed += _mark_usage_impact_stale_for_time_range(
        conn,
        changed_time_start=changed_time_start,
        changed_time_end=changed_time_end,
        exclude_record_ids=inserted,
    )
    changed += _insert_pending_usage_impact_rows(conn, inserted)
    return changed


def query_usage_impact_rows(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    record_id: str | None = None,
    limit: int | None = 100,
    offset: int = 0,
    window_type: str | None = None,
) -> list[dict[str, Any]]:
    """Query persisted usage-impact rows."""

    clauses: list[str] = []
    params: list[Any] = []
    if record_id:
        clauses.append("record_id = ?")
        params.append(record_id)
    if window_type:
        if window_type not in WINDOW_TYPES:
            raise ValueError("window_type must be one of: primary, secondary")
        clauses.append("window_type = ?")
        params.append(window_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    normalized_limit = None if limit is None or limit <= 0 else int(limit)
    limit_clause = ""
    if normalized_limit is not None:
        limit_clause = "LIMIT ? OFFSET ?"
        params.extend([normalized_limit, int(offset)])
    elif offset:
        limit_clause = "LIMIT -1 OFFSET ?"
        params.append(int(offset))
    with _connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            f"""
            SELECT *
            FROM usage_impact
            {where}
            ORDER BY recalculated_at DESC, record_id, window_type
            {limit_clause}
            """,
            params,
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def query_usage_impact_map_for_records(
    db_path: Path = DEFAULT_DB_PATH,
    record_ids: Iterable[str] = (),
) -> tuple[dict[str, dict[str, Any]], bool]:
    """Return dashboard-shaped usage-impact values and whether any are pending."""

    ids = sorted({record_id for record_id in record_ids if record_id})
    if not ids:
        return {}, False
    placeholders = ", ".join("?" for _record_id in ids)
    with _connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            f"""
            SELECT *
            FROM usage_impact
            WHERE record_id IN ({placeholders})
            """,
            ids,
        ).fetchall()
    mapped: dict[str, dict[str, Any]] = {}
    pending = False
    for row in rows:
        item = _row_to_dict(row)
        record_id = str(item["record_id"])
        window_type = str(item["window_type"])
        mapped.setdefault(record_id, {"primary": None, "secondary": None})
        mapped[record_id][window_type] = _dashboard_impact(item)
        if item.get("status") in {"pending", "stale"}:
            pending = True
    return mapped, pending


def query_usage_impact_recalculation_record_ids(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    include_archived: bool = False,
    limit: int | None = None,
) -> list[str]:
    """Return records whose persisted usage-impact rows need recalculation."""

    archive_clause = "" if include_archived else "WHERE usage_events.is_archived = 0"
    normalized_limit = None if limit is None or limit <= 0 else int(limit)
    limit_clause = "LIMIT ?" if normalized_limit is not None else ""
    params: list[Any] = []
    if normalized_limit is not None:
        params.append(normalized_limit)
    with _connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            f"""
            SELECT usage_events.record_id
            FROM usage_events
            LEFT JOIN usage_impact
                ON usage_impact.record_id = usage_events.record_id
            {archive_clause}
            GROUP BY usage_events.record_id
            HAVING
                SUM(CASE WHEN usage_impact.window_type = 'primary' THEN 1 ELSE 0 END) = 0
                OR SUM(CASE WHEN usage_impact.window_type = 'secondary' THEN 1 ELSE 0 END) = 0
                OR SUM(
                    CASE WHEN usage_impact.status IN ('pending', 'stale') THEN 1 ELSE 0 END
                ) > 0
            ORDER BY MAX(usage_events.event_timestamp) ASC,
                MAX(usage_events.cumulative_total_tokens) ASC,
                usage_events.record_id ASC
            {limit_clause}
            """,
            params,
        ).fetchall()
    return [str(row["record_id"]) for row in rows]


def _materialize_window(
    row: dict[str, Any],
    *,
    record_id: str,
    window_type: str,
    impact: dict[str, Any] | None,
    recalculated_at: str,
) -> dict[str, Any]:
    estimate = _optional_float((impact or {}).get("estimate_percent"))
    status, confidence, reason = _classify_impact(impact)
    observed_used = _optional_float(row.get(f"rate_limit_{window_type}_used_percent"))
    observed_minutes = _optional_int(row.get(f"rate_limit_{window_type}_window_minutes"))
    observed_resets = _optional_int(row.get(f"rate_limit_{window_type}_resets_at"))
    delta = _optional_float((impact or {}).get("observed_delta_percent"))
    total_tokens = _optional_int(row.get("total_tokens"))
    estimated_tokens_per_percent = (
        total_tokens / estimate
        if total_tokens is not None and estimate is not None and estimate > 0
        else None
    )
    return {
        "record_id": record_id,
        "window_type": window_type,
        "plan_type": _optional_str((impact or {}).get("plan_type"))
        or _optional_str(row.get("rate_limit_plan_type")),
        "limit_id": _optional_str((impact or {}).get("limit_id"))
        or _optional_str(row.get("rate_limit_limit_id")),
        "observed_used_percent": observed_used,
        "observed_window_minutes": observed_minutes,
        "observed_resets_at": observed_resets,
        "previous_observed_record_id": _optional_str((impact or {}).get("previous_observed_record_id")),
        "previous_observed_used_percent": _optional_float(
            (impact or {}).get("previous_used_percent")
        ),
        "next_observed_record_id": _optional_str((impact or {}).get("next_observed_record_id")),
        "delta_used_percent": delta,
        "tokens_since_previous": _optional_int((impact or {}).get("tokens_since_previous"))
        or total_tokens,
        "estimated_tokens_per_percent": estimated_tokens_per_percent,
        "estimated_usage_credits": _optional_float(row.get("usage_credits")),
        "estimated_usage_percent": estimate,
        "lower_percent": _optional_float((impact or {}).get("lower_percent")),
        "upper_percent": _optional_float((impact or {}).get("upper_percent")),
        "basis": _optional_str((impact or {}).get("basis")),
        "source": _optional_str((impact or {}).get("source")),
        "interval_call_count": _optional_int((impact or {}).get("interval_call_count"))
        or _optional_int((impact or {}).get("observed_interval_call_count")),
        "confidence": confidence,
        "status": status,
        "reason": reason,
        "recalculated_at": recalculated_at,
    }


def _classify_impact(impact: dict[str, Any] | None) -> tuple[str, str, str]:
    if not impact:
        return "unavailable", "unknown", UNAVAILABLE_REASON
    estimate = _optional_float(impact.get("estimate_percent"))
    source_note = _public_source_note(_optional_str(impact.get("source_note")))
    if estimate is None:
        return "pending", "low", source_note or PENDING_REASON
    lower = _optional_float(impact.get("lower_percent"))
    upper = _optional_float(impact.get("upper_percent"))
    spread = (upper - lower) if lower is not None and upper is not None else None
    sample_count = _optional_int(impact.get("calibration_sample_count")) or 0
    interval_count = _optional_int(impact.get("interval_call_count")) or 0
    if impact.get("source") == "observed_interval" and interval_count <= 3:
        confidence = "high"
    elif sample_count >= 20 or (spread is not None and spread <= max(0.05, estimate)):
        confidence = "medium"
    else:
        confidence = "low"
    return "fresh", confidence, source_note or "Estimated from observed local usage snapshots."


def _public_source_note(source_note: str | None) -> str | None:
    if source_note is None:
        return None
    known = {
        "calibrated_from_codex_limit_family": (
            "Estimated from compatible Codex limit-family calibration."
        ),
        "calibrated_from_codex_limit_family_after_noisy_observed_interval": (
            "Noisy observed interval replaced with compatible Codex limit-family calibration."
        ),
        "calibrated_after_noisy_observed_interval": (
            "Noisy observed interval replaced with calibrated history."
        ),
        "suppressed_unvalidated_single_call_observed_jump": (
            "Single-call observed jump suppressed until calibrated by more local history."
        ),
    }
    return known.get(source_note, "Estimated from observed local usage snapshots.")


def _mark_usage_impact_stale_for_time_range(
    conn: sqlite3.Connection,
    *,
    changed_time_start: str | None,
    changed_time_end: str | None,
    exclude_record_ids: list[str],
) -> int:
    if not changed_time_start or not changed_time_end:
        return 0
    params: list[Any] = [STALE_REASON, _utc_now(), changed_time_start, changed_time_end]
    exclude_clause = ""
    if exclude_record_ids:
        placeholders = ", ".join("?" for _record_id in exclude_record_ids)
        exclude_clause = f"AND usage_impact.record_id NOT IN ({placeholders})"
        params.extend(exclude_record_ids)
    before = conn.total_changes
    conn.execute(
        f"""
        UPDATE usage_impact
        SET status = 'stale',
            confidence = CASE WHEN confidence = 'unknown' THEN 'unknown' ELSE 'low' END,
            reason = ?,
            recalculated_at = ?
        WHERE record_id IN (
            SELECT record_id
            FROM usage_events
            WHERE event_timestamp BETWEEN ? AND ?
        )
        {exclude_clause}
        """,
        params,
    )
    return conn.total_changes - before


def _insert_pending_usage_impact_rows(
    conn: sqlite3.Connection,
    record_ids: list[str],
) -> int:
    if not record_ids:
        return 0
    now = _utc_now()
    rows = [
        {
            "record_id": record_id,
            "window_type": window_type,
            "plan_type": None,
            "limit_id": None,
            "observed_used_percent": None,
            "observed_window_minutes": None,
            "observed_resets_at": None,
            "previous_observed_record_id": None,
            "previous_observed_used_percent": None,
            "next_observed_record_id": None,
            "delta_used_percent": None,
            "tokens_since_previous": None,
            "estimated_tokens_per_percent": None,
            "estimated_usage_credits": None,
            "estimated_usage_percent": None,
            "lower_percent": None,
            "upper_percent": None,
            "basis": None,
            "source": None,
            "interval_call_count": None,
            "confidence": "unknown",
            "status": "pending",
            "reason": PENDING_REASON,
            "recalculated_at": now,
        }
        for record_id in record_ids
        for window_type in WINDOW_TYPES
    ]
    return upsert_usage_impact_rows(conn, rows)


def _dashboard_impact(row: dict[str, Any]) -> dict[str, Any] | None:
    if row.get("status") == "unavailable":
        return None
    return {
        "schema": "codex-usage-tracker-usage-impact-estimate-v1",
        "label": _window_label(_optional_int(row.get("observed_window_minutes"))),
        "window_minutes": row.get("observed_window_minutes"),
        "estimate_percent": row.get("estimated_usage_percent"),
        "lower_percent": row.get("lower_percent"),
        "upper_percent": row.get("upper_percent"),
        "observed_delta_percent": row.get("delta_used_percent"),
        "interval_call_count": row.get("interval_call_count"),
        "basis": row.get("basis"),
        "source": row.get("source"),
        "plan_type": row.get("plan_type"),
        "limit_id": row.get("limit_id"),
        "resets_at": row.get("observed_resets_at"),
        "confidence": row.get("confidence"),
        "status": row.get("status"),
        "reason": row.get("reason"),
    }


def _window_label(minutes: int | None) -> str | None:
    if minutes is None:
        return None
    if minutes == 300:
        return "5h"
    if minutes == 10080:
        return "Weekly"
    if minutes % 1440 == 0:
        return f"{minutes // 1440}d"
    if minutes % 60 == 0:
        return f"{minutes // 60}h"
    return f"{minutes}m"


@contextmanager
def _connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {str(key): value for key, value in dict(row).items()}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _optional_str(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
