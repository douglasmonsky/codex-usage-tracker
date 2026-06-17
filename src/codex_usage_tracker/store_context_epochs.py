"""Materialized context epoch maintenance for aggregate work sessions."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store_query_sql import (
    _normalize_limit,
    _normalize_offset,
    _normalize_sort_direction,
    _thread_key_expression,
)
from codex_usage_tracker.store_schema import init_db

CONTEXT_EPOCHS_SCHEMA_ID = "codex-usage-tracker-context-epochs-v1"

CONTEXT_EPOCH_COLUMNS = [
    "context_epoch_id",
    "work_session_id",
    "thread_key",
    "epoch_index",
    "start_record_id",
    "end_record_id",
    "start_reason",
    "compaction_before_record_id",
    "compaction_detected_at",
    "started_at",
    "ended_at",
    "duration_minutes",
    "call_count",
    "input_tokens",
    "cached_input_tokens",
    "uncached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
    "avg_cache_ratio",
    "min_cache_ratio",
    "max_context_window_percent",
    "largest_uncached_record_id",
    "largest_uncached_input_tokens",
    "first_call_cache_ratio",
    "first_call_uncached_input_tokens",
    "post_compaction_uncached_spike",
    "subagent_call_count",
    "auto_review_call_count",
    "compaction_effectiveness",
    "updated_at",
]


def context_epochs_payload(
    rows: list[dict[str, Any]],
    *,
    work_session_id: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, Any]:
    """Return stable aggregate-only context epoch rows."""

    return {
        "schema": CONTEXT_EPOCHS_SCHEMA_ID,
        "row_count": len(rows),
        "rows": rows,
        "work_session_id": work_session_id,
        "limit": limit,
        "offset": offset,
        "raw_context_included": False,
    }


def rebuild_thread_context_epochs(
    conn: sqlite3.Connection,
    *,
    thread_keys: Iterable[str] | None = None,
    work_session_ids: Iterable[str] | None = None,
) -> int:
    """Rebuild context epochs for all, selected threads, or selected work sessions."""

    before = conn.total_changes
    normalized_thread_keys = sorted({key for key in thread_keys or [] if key})
    normalized_work_session_ids = sorted({key for key in work_session_ids or [] if key})
    if thread_keys is not None and not normalized_thread_keys:
        return 0
    if work_session_ids is not None and not normalized_work_session_ids:
        return 0
    if normalized_work_session_ids:
        placeholders = ", ".join("?" for _key in normalized_work_session_ids)
        conn.execute(
            f"DELETE FROM thread_context_epochs WHERE work_session_id IN ({placeholders})",
            normalized_work_session_ids,
        )
    elif thread_keys is None:
        conn.execute("DELETE FROM thread_context_epochs")
    else:
        placeholders = ", ".join("?" for _key in normalized_thread_keys)
        conn.execute(
            f"DELETE FROM thread_context_epochs WHERE thread_key IN ({placeholders})",
            normalized_thread_keys,
        )
    rows = _query_usage_rows_for_epochs(
        conn,
        thread_keys=normalized_thread_keys if thread_keys is not None else None,
        work_session_ids=normalized_work_session_ids if work_session_ids is not None else None,
    )
    materialized = materialize_thread_context_epochs(rows)
    if materialized:
        placeholders = ", ".join("?" for _column in CONTEXT_EPOCH_COLUMNS)
        conn.executemany(
            f"""
            INSERT INTO thread_context_epochs ({', '.join(CONTEXT_EPOCH_COLUMNS)})
            VALUES ({placeholders})
            """,
            [[row.get(column) for column in CONTEXT_EPOCH_COLUMNS] for row in materialized],
        )
    return conn.total_changes - before


def materialize_thread_context_epochs(
    rows: Iterable[Mapping[str, Any] | sqlite3.Row],
    *,
    updated_at: str | None = None,
) -> list[dict[str, Any]]:
    """Split work-session usage rows into context epochs."""

    timestamp = updated_at or _utc_now()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in rows:
        row = dict(raw)
        work_session_id = str(row.get("work_session_id") or "")
        if not work_session_id:
            continue
        grouped.setdefault(work_session_id, []).append(row)
    materialized: list[dict[str, Any]] = []
    for work_session_id in sorted(grouped):
        session_rows = sorted(grouped[work_session_id], key=_row_order_key)
        if not session_rows:
            continue
        epochs: list[tuple[list[dict[str, Any]], str, str | None, str | None]] = []
        current: list[dict[str, Any]] = [session_rows[0]]
        current_reason = "session_start"
        compaction_before_record_id: str | None = None
        compaction_detected_at: str | None = None
        for row in session_rows[1:]:
            if _is_post_compaction(row):
                epochs.append(
                    (
                        current,
                        current_reason,
                        compaction_before_record_id,
                        compaction_detected_at,
                    )
                )
                current = [row]
                current_reason = "post_compaction"
                compaction_before_record_id = _optional_str(row.get("previous_record_id"))
                compaction_detected_at = _optional_str(row.get("event_timestamp"))
            else:
                current.append(row)
        epochs.append(
            (
                current,
                current_reason,
                compaction_before_record_id,
                compaction_detected_at,
            )
        )
        for index, (epoch_rows, start_reason, before_id, detected_at) in enumerate(epochs, start=1):
            materialized.append(
                _materialize_epoch(
                    work_session_id,
                    index,
                    epoch_rows,
                    start_reason=start_reason,
                    compaction_before_record_id=before_id,
                    compaction_detected_at=detected_at,
                    updated_at=timestamp,
                )
            )
    return materialized


def query_context_epochs(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    work_session_id: str | None = None,
    thread_key: str | None = None,
    limit: int | None = 100,
    offset: int = 0,
    sort: str = "started",
    direction: str = "asc",
) -> list[dict[str, Any]]:
    """Return materialized context epochs for APIs and dashboard details."""

    clauses: list[str] = []
    params: list[Any] = []
    if work_session_id:
        clauses.append("work_session_id = ?")
        params.append(work_session_id)
    if thread_key:
        clauses.append("thread_key = ?")
        params.append(thread_key)
    where_clause = "WHERE " + " AND ".join(f"({clause})" for clause in clauses) if clauses else ""
    sort_map = {
        "started": "started_at",
        "ended": "ended_at",
        "duration": "duration_minutes",
        "calls": "call_count",
        "tokens": "total_tokens",
        "uncached": "uncached_input_tokens",
        "context": "max_context_window_percent",
        "effectiveness": "compaction_effectiveness",
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
            FROM thread_context_epochs
            {where_clause}
            ORDER BY {sort_map[sort]} {direction_sql}, epoch_index ASC
            {limit_clause}
            """,
            query_params,
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _query_usage_rows_for_epochs(
    conn: sqlite3.Connection,
    *,
    thread_keys: list[str] | None,
    work_session_ids: list[str] | None,
) -> list[sqlite3.Row]:
    usage_thread_key_expr = _thread_key_expression("ue.")
    clauses: list[str] = []
    params: list[Any] = []
    if thread_keys is not None:
        placeholders = ", ".join("?" for _key in thread_keys)
        clauses.append(f"ws.thread_key IN ({placeholders})")
        params.extend(thread_keys)
    if work_session_ids is not None:
        placeholders = ", ".join("?" for _key in work_session_ids)
        clauses.append(f"ws.work_session_id IN ({placeholders})")
        params.extend(work_session_ids)
    where_clause = "WHERE " + " AND ".join(f"({clause})" for clause in clauses) if clauses else ""
    return conn.execute(
        f"""
        WITH session_bounds AS (
            SELECT
                ws.work_session_id,
                ws.thread_key,
                ws.session_index,
                start_row.thread_call_index AS start_index,
                end_row.thread_call_index AS end_index
            FROM thread_work_sessions AS ws
            JOIN usage_events AS start_row
              ON start_row.record_id = ws.start_record_id
            JOIN usage_events AS end_row
              ON end_row.record_id = ws.end_record_id
            {where_clause}
        )
        SELECT
            ue.*,
            sb.work_session_id,
            sb.session_index,
            {usage_thread_key_expr} AS resolved_thread_key
        FROM session_bounds AS sb
        JOIN usage_events AS ue
          ON {usage_thread_key_expr} = sb.thread_key
         AND ue.thread_call_index >= sb.start_index
         AND ue.thread_call_index <= sb.end_index
        ORDER BY sb.thread_key, sb.session_index, ue.thread_call_index, ue.event_timestamp, ue.line_number, ue.record_id
        """,
        params,
    ).fetchall()


def _materialize_epoch(
    work_session_id: str,
    epoch_index: int,
    rows: list[dict[str, Any]],
    *,
    start_reason: str,
    compaction_before_record_id: str | None,
    compaction_detected_at: str | None,
    updated_at: str,
) -> dict[str, Any]:
    first = rows[0]
    last = rows[-1]
    input_tokens = sum(_int(row.get("input_tokens")) for row in rows)
    cached_tokens = sum(_int(row.get("cached_input_tokens")) for row in rows)
    uncached_tokens = sum(_int(row.get("uncached_input_tokens")) for row in rows)
    output_tokens = sum(_int(row.get("output_tokens")) for row in rows)
    reasoning_tokens = sum(_int(row.get("reasoning_output_tokens")) for row in rows)
    total_tokens = sum(_int(row.get("total_tokens")) for row in rows)
    largest_uncached = max(rows, key=lambda row: _int(row.get("uncached_input_tokens")))
    started_at = str(first.get("event_timestamp") or "")
    ended_at = str(last.get("event_timestamp") or started_at)
    first_uncached = _int(first.get("uncached_input_tokens"))
    first_cache_ratio = _float(first.get("cache_ratio"))
    return {
        "context_epoch_id": _context_epoch_id(work_session_id, epoch_index, str(first.get("record_id"))),
        "work_session_id": work_session_id,
        "thread_key": str(first.get("resolved_thread_key") or first.get("thread_key") or ""),
        "epoch_index": epoch_index,
        "start_record_id": first.get("record_id"),
        "end_record_id": last.get("record_id"),
        "start_reason": start_reason,
        "compaction_before_record_id": compaction_before_record_id,
        "compaction_detected_at": compaction_detected_at,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_minutes": _minutes_between(_parse_timestamp(started_at), _parse_timestamp(ended_at)) or 0.0,
        "call_count": len(rows),
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "uncached_input_tokens": uncached_tokens,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
        "avg_cache_ratio": cached_tokens / input_tokens if input_tokens else 0.0,
        "min_cache_ratio": min((_float(row.get("cache_ratio")) for row in rows), default=0.0),
        "max_context_window_percent": max(
            (_float(row.get("context_window_percent")) for row in rows),
            default=0.0,
        ),
        "largest_uncached_record_id": largest_uncached.get("record_id"),
        "largest_uncached_input_tokens": _int(largest_uncached.get("uncached_input_tokens")),
        "first_call_cache_ratio": first_cache_ratio,
        "first_call_uncached_input_tokens": first_uncached,
        "post_compaction_uncached_spike": first_uncached if start_reason == "post_compaction" else 0,
        "subagent_call_count": sum(_is_subagent(row) for row in rows),
        "auto_review_call_count": sum(_is_auto_review(row) for row in rows),
        "compaction_effectiveness": _compaction_effectiveness(start_reason, first_uncached, first_cache_ratio),
        "updated_at": updated_at,
    }


def _context_epoch_id(work_session_id: str, epoch_index: int, start_record_id: str) -> str:
    digest = hashlib.sha256(f"{work_session_id}|{epoch_index}|{start_record_id}".encode()).hexdigest()
    return f"context-epoch-{digest[:24]}"


def _is_post_compaction(row: Mapping[str, Any]) -> bool:
    return str(row.get("call_initiator_reason") or "").lower() == "post_compaction"


def _compaction_effectiveness(start_reason: str, first_uncached: int, first_cache_ratio: float) -> str:
    if start_reason != "post_compaction":
        return "unknown"
    if first_uncached <= 20_000 or first_cache_ratio >= 0.60:
        return "effective"
    if first_uncached <= 75_000 or first_cache_ratio >= 0.25:
        return "mixed"
    return "ineffective"


def _row_order_key(row: Mapping[str, Any]) -> tuple[int, str, int, str]:
    return (
        _int(row.get("thread_call_index")),
        str(row.get("event_timestamp") or ""),
        _int(row.get("line_number")),
        str(row.get("record_id") or ""),
    )


def _is_subagent(row: Mapping[str, Any]) -> bool:
    return bool(
        row.get("thread_source") == "subagent"
        or row.get("subagent_type")
        or row.get("parent_session_id")
    )


def _is_auto_review(row: Mapping[str, Any]) -> bool:
    return bool(row.get("model") == "codex-auto-review" or row.get("subagent_type") == "guardian")


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _minutes_between(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return max((end - start).total_seconds() / 60, 0.0)


def _int(value: object) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if not isinstance(value, int | float | str):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(value: object) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    if not isinstance(value, int | float | str):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def _connect(db_path: Path) -> Any:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)
