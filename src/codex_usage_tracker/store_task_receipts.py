"""Materialized task receipt signals for aggregate usage rows."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.models import TaskReceiptSignal, UsageEvent
from codex_usage_tracker.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store_query_sql import (
    _normalize_limit,
    _normalize_offset,
    _normalize_sort_direction,
)
from codex_usage_tracker.store_schema import init_db
from codex_usage_tracker.task_receipt_signals import strongest_confidence

TASK_RECEIPTS_SCHEMA_ID = "codex-usage-tracker-task-receipts-v1"

TASK_RECEIPT_COLUMNS = [
    "receipt_id",
    "record_id",
    "thread_key",
    "work_session_id",
    "context_epoch_id",
    "receipt_category",
    "receipt_confidence",
    "event_count",
    "first_event_timestamp",
    "last_event_timestamp",
    "first_source_line",
    "last_source_line",
    "evidence_scope",
    "reason",
    "updated_at",
]


def task_receipts_payload(
    rows: list[dict[str, Any]],
    *,
    record_id: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, Any]:
    """Return the stable aggregate-only task receipt payload."""

    return {
        "schema": TASK_RECEIPTS_SCHEMA_ID,
        "row_count": len(rows),
        "rows": rows,
        "record_id": record_id,
        "limit": limit,
        "offset": offset,
        "raw_context_included": False,
    }


def replace_task_receipts_for_events(
    conn: sqlite3.Connection,
    events: Iterable[UsageEvent],
) -> int:
    """Replace receipt rows for the provided aggregate events."""

    event_list = list(events)
    if not event_list:
        return 0
    record_ids = [event.record_id for event in event_list]
    before = conn.total_changes
    delete_task_receipts_for_record_ids(conn, record_ids)
    metadata = _usage_metadata_for_records(conn, record_ids)
    rows: list[dict[str, Any]] = []
    updated_at = _utc_now()
    for event in event_list:
        event_metadata = metadata.get(event.record_id, {})
        rows.extend(_receipt_rows_for_event(event, event_metadata, updated_at=updated_at))
    if rows:
        placeholders = ", ".join("?" for _column in TASK_RECEIPT_COLUMNS)
        conn.executemany(
            f"""
            INSERT INTO task_receipts ({', '.join(TASK_RECEIPT_COLUMNS)})
            VALUES ({placeholders})
            """,
            [[row.get(column) for column in TASK_RECEIPT_COLUMNS] for row in rows],
        )
    return conn.total_changes - before


def delete_task_receipts_for_record_ids(
    conn: sqlite3.Connection,
    record_ids: Iterable[str],
) -> int:
    """Delete receipt rows for aggregate usage record ids."""

    ids = sorted({record_id for record_id in record_ids if record_id})
    if not ids:
        return 0
    before = conn.total_changes
    placeholders = ", ".join("?" for _record_id in ids)
    conn.execute(
        f"DELETE FROM task_receipts WHERE record_id IN ({placeholders})",
        ids,
    )
    return conn.total_changes - before


def query_task_receipts(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    record_id: str | None = None,
    thread_key: str | None = None,
    work_session_id: str | None = None,
    context_epoch_id: str | None = None,
    category: str | None = None,
    limit: int | None = 100,
    offset: int = 0,
    sort: str = "latest",
    direction: str = "desc",
) -> list[dict[str, Any]]:
    """Return aggregate-only task receipt rows."""

    clauses: list[str] = []
    params: list[Any] = []
    if record_id:
        clauses.append("record_id = ?")
        params.append(record_id)
    if thread_key:
        clauses.append("thread_key = ?")
        params.append(thread_key)
    if work_session_id:
        clauses.append("work_session_id = ?")
        params.append(work_session_id)
    if context_epoch_id:
        clauses.append("context_epoch_id = ?")
        params.append(context_epoch_id)
    if category:
        clauses.append("receipt_category = ?")
        params.append(category)
    where_clause = "WHERE " + " AND ".join(f"({clause})" for clause in clauses) if clauses else ""
    sort_map = {
        "latest": "last_event_timestamp",
        "first": "first_event_timestamp",
        "category": "receipt_category",
        "confidence": "receipt_confidence",
        "count": "event_count",
        "record": "record_id",
    }
    if sort not in sort_map:
        allowed = ", ".join(sorted(sort_map))
        raise ValueError(f"sort must be one of: {allowed}")
    direction_sql = _normalize_sort_direction(direction)
    normalized_limit = _normalize_limit(limit)
    normalized_offset = _normalize_offset(offset)
    limit_clause = ""
    query_params = list(params)
    if normalized_limit is not None:
        limit_clause = "LIMIT ?"
        query_params.append(normalized_limit)
        if normalized_offset:
            limit_clause += " OFFSET ?"
            query_params.append(normalized_offset)
    elif normalized_offset:
        limit_clause = "LIMIT -1 OFFSET ?"
        query_params.append(normalized_offset)
    with _connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            f"""
            SELECT *
            FROM task_receipts
            {where_clause}
            ORDER BY {sort_map[sort]} {direction_sql}, receipt_id ASC
            {limit_clause}
            """,
            query_params,
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _receipt_rows_for_event(
    event: UsageEvent,
    metadata: dict[str, Any],
    *,
    updated_at: str,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[TaskReceiptSignal]] = {}
    for signal in event.task_receipt_signals:
        grouped.setdefault((signal.category, signal.evidence_scope), []).append(signal)
    rows: list[dict[str, Any]] = []
    for (category, scope), signals in sorted(grouped.items()):
        first_line = min(
            (signal.first_source_line for signal in signals if signal.first_source_line is not None),
            default=None,
        )
        last_line = max(
            (signal.last_source_line for signal in signals if signal.last_source_line is not None),
            default=None,
        )
        first_timestamp = min(
            (signal.first_event_timestamp for signal in signals if signal.first_event_timestamp),
            default=None,
        )
        last_timestamp = max(
            (signal.last_event_timestamp for signal in signals if signal.last_event_timestamp),
            default=None,
        )
        reasons = sorted({signal.reason for signal in signals if signal.reason})
        rows.append(
            {
                "receipt_id": _receipt_id(event.record_id, category, scope),
                "record_id": event.record_id,
                "thread_key": metadata.get("thread_key") or event.thread_key,
                "work_session_id": metadata.get("work_session_id"),
                "context_epoch_id": metadata.get("context_epoch_id"),
                "receipt_category": category,
                "receipt_confidence": strongest_confidence(
                    [signal.confidence for signal in signals]
                ),
                "event_count": sum(signal.event_count for signal in signals),
                "first_event_timestamp": first_timestamp,
                "last_event_timestamp": last_timestamp,
                "first_source_line": first_line,
                "last_source_line": last_line,
                "evidence_scope": scope,
                "reason": ", ".join(reasons) if reasons else None,
                "updated_at": updated_at,
            }
        )
    return rows


def _usage_metadata_for_records(
    conn: sqlite3.Connection,
    record_ids: list[str],
) -> dict[str, dict[str, Any]]:
    if not record_ids:
        return {}
    placeholders = ", ".join("?" for _record_id in record_ids)
    rows = conn.execute(
        f"""
        SELECT record_id, thread_key, thread_call_index
        FROM usage_events
        WHERE record_id IN ({placeholders})
        """,
        record_ids,
    ).fetchall()
    metadata: dict[str, dict[str, Any]] = {}
    for row in rows:
        values = _row_to_dict(row)
        thread_key = values.get("thread_key")
        thread_call_index = values.get("thread_call_index")
        values.update(
            _work_session_and_epoch_for_call(
                conn,
                thread_key=thread_key if isinstance(thread_key, str) else None,
                thread_call_index=(
                    int(thread_call_index)
                    if isinstance(thread_call_index, int) and not isinstance(thread_call_index, bool)
                    else None
                ),
            )
        )
        metadata[str(values["record_id"])] = values
    return metadata


def _work_session_and_epoch_for_call(
    conn: sqlite3.Connection,
    *,
    thread_key: str | None,
    thread_call_index: int | None,
) -> dict[str, Any]:
    if not thread_key or thread_call_index is None:
        return {}
    session_row = conn.execute(
        """
        SELECT ws.work_session_id
        FROM thread_work_sessions AS ws
        JOIN usage_events AS start_row
          ON start_row.record_id = ws.start_record_id
        JOIN usage_events AS end_row
          ON end_row.record_id = ws.end_record_id
        WHERE ws.thread_key = ?
          AND ? BETWEEN start_row.thread_call_index AND end_row.thread_call_index
        ORDER BY ws.session_index ASC
        LIMIT 1
        """,
        (thread_key, thread_call_index),
    ).fetchone()
    if session_row is None:
        return {}
    work_session_id = str(session_row["work_session_id"])
    epoch_row = conn.execute(
        """
        SELECT epoch.context_epoch_id
        FROM thread_context_epochs AS epoch
        JOIN usage_events AS start_row
          ON start_row.record_id = epoch.start_record_id
        JOIN usage_events AS end_row
          ON end_row.record_id = epoch.end_record_id
        WHERE epoch.work_session_id = ?
          AND ? BETWEEN start_row.thread_call_index AND end_row.thread_call_index
        ORDER BY epoch.epoch_index ASC
        LIMIT 1
        """,
        (work_session_id, thread_call_index),
    ).fetchone()
    return {
        "work_session_id": work_session_id,
        "context_epoch_id": (
            str(epoch_row["context_epoch_id"]) if epoch_row is not None else None
        ),
    }


def _receipt_id(record_id: str, category: str, scope: str) -> str:
    raw = "|".join([record_id, category, scope])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


@contextmanager
def _connect(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
