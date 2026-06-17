"""Materialized thread work-session maintenance for aggregate usage rows."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.paths import DEFAULT_DB_PATH
from codex_usage_tracker.recommendations import DEFAULT_THRESHOLDS
from codex_usage_tracker.store_query_sql import (
    _normalize_limit,
    _normalize_offset,
    _normalize_sort_direction,
    _thread_key_expression,
)
from codex_usage_tracker.store_schema import init_db

WORK_SESSIONS_SCHEMA_ID = "codex-usage-tracker-sessions-v1"
WORK_SESSION_SCHEMA_ID = "codex-usage-tracker-work-session-v1"

WORK_SESSION_COLUMNS = [
    "work_session_id",
    "thread_key",
    "thread_label",
    "session_index",
    "start_record_id",
    "end_record_id",
    "cold_start_record_id",
    "start_reason",
    "started_at",
    "ended_at",
    "duration_minutes",
    "idle_minutes_before",
    "call_count",
    "model_summary",
    "effort_summary",
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
    "cold_resume_uncached_tokens",
    "compaction_count",
    "subagent_call_count",
    "auto_review_call_count",
    "suggested_next_action",
    "recommendation_score",
    "recommendation_reasons_json",
    "updated_at",
]


def sessions_payload(
    rows: list[dict[str, Any]],
    *,
    limit: int | None = None,
    offset: int = 0,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Return the stable aggregate-only Sessions payload."""

    return {
        "schema": WORK_SESSIONS_SCHEMA_ID,
        "row_count": len(rows),
        "rows": rows,
        "limit": limit,
        "offset": offset,
        "include_archived": include_archived,
        "raw_context_included": False,
    }


def work_session_payload(row: dict[str, Any] | None) -> dict[str, Any]:
    """Return the stable aggregate-only payload for one work session."""

    return {
        "schema": WORK_SESSION_SCHEMA_ID,
        "record": row,
        "raw_context_included": False,
    }


def rebuild_thread_work_sessions(
    conn: sqlite3.Connection,
    *,
    thread_keys: Iterable[str] | None = None,
    thresholds: Mapping[str, float] | None = None,
) -> int:
    """Rebuild materialized work sessions for all or selected thread keys."""

    before = conn.total_changes
    normalized_thread_keys = sorted({key for key in thread_keys or [] if key})
    if thread_keys is None:
        conn.execute("DELETE FROM thread_work_sessions")
    elif not normalized_thread_keys:
        return 0
    else:
        placeholders = ", ".join("?" for _key in normalized_thread_keys)
        conn.execute(
            f"DELETE FROM thread_work_sessions WHERE thread_key IN ({placeholders})",
            normalized_thread_keys,
        )
    rows = _query_usage_rows_for_sessions(conn, thread_keys=normalized_thread_keys if thread_keys is not None else None)
    materialized = materialize_thread_work_sessions(rows, thresholds=thresholds)
    if materialized:
        placeholders = ", ".join("?" for _column in WORK_SESSION_COLUMNS)
        conn.executemany(
            f"""
            INSERT INTO thread_work_sessions ({', '.join(WORK_SESSION_COLUMNS)})
            VALUES ({placeholders})
            """,
            [[row.get(column) for column in WORK_SESSION_COLUMNS] for row in materialized],
        )
    return conn.total_changes - before


def materialize_thread_work_sessions(
    rows: Iterable[Mapping[str, Any] | sqlite3.Row],
    *,
    thresholds: Mapping[str, float] | None = None,
    updated_at: str | None = None,
) -> list[dict[str, Any]]:
    """Split aggregate usage rows into thread work sessions."""

    limits = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        limits.update(
            {
                key: float(value)
                for key, value in thresholds.items()
                if key in limits and isinstance(value, int | float) and not isinstance(value, bool)
            }
        )
    timestamp = updated_at or _utc_now()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in rows:
        row = dict(raw)
        thread_key = str(row.get("resolved_thread_key") or row.get("thread_key") or "")
        if not thread_key:
            continue
        grouped.setdefault(thread_key, []).append(row)
    materialized: list[dict[str, Any]] = []
    for thread_key in sorted(grouped):
        thread_rows = sorted(grouped[thread_key], key=_row_order_key)
        if not thread_rows:
            continue
        sessions: list[tuple[list[dict[str, Any]], str, float | None]] = []
        current: list[dict[str, Any]] = [thread_rows[0]]
        current_reason = "thread_start"
        current_idle: float | None = None
        last_boundary_at: datetime | None = None
        for previous, row in zip(thread_rows, thread_rows[1:], strict=False):
            boundary, idle_minutes = _is_cold_resume_boundary(
                row,
                previous,
                limits,
                last_boundary_at=last_boundary_at,
            )
            if boundary:
                sessions.append((current, current_reason, current_idle))
                current = [row]
                current_reason = "cold_resume"
                current_idle = idle_minutes
                last_boundary_at = _parse_timestamp(row.get("event_timestamp"))
            else:
                current.append(row)
        sessions.append((current, current_reason, current_idle))
        for index, (session_rows, start_reason, idle_minutes) in enumerate(sessions, start=1):
            materialized.append(
                _materialize_session(
                    thread_key,
                    index,
                    session_rows,
                    start_reason=start_reason,
                    idle_minutes_before=idle_minutes,
                    updated_at=timestamp,
                )
            )
    return materialized


def query_thread_work_sessions(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    limit: int | None = 100,
    offset: int = 0,
    search: str | None = None,
    thread_key: str | None = None,
    include_archived: bool = False,
    sort: str = "uncached",
    direction: str = "desc",
    cold_resumes_only: bool = False,
    high_uncached_only: bool = False,
    needs_handoff_only: bool = False,
    recent_only: bool = False,
) -> list[dict[str, Any]]:
    """Return materialized work sessions for CLI and dashboard APIs."""

    clauses: list[str] = []
    params: list[Any] = []
    if not include_archived:
        clauses.append(
            """
            EXISTS (
                SELECT 1
                FROM usage_events AS start_row
                WHERE start_row.record_id = thread_work_sessions.start_record_id
                  AND coalesce(start_row.is_archived, 0) = 0
            )
            """
        )
    if search:
        like = f"%{search}%"
        clauses.append("(thread_key LIKE ? OR thread_label LIKE ?)")
        params.extend([like, like])
    if thread_key:
        clauses.append("thread_key = ?")
        params.append(thread_key)
    if cold_resumes_only:
        clauses.append("start_reason = 'cold_resume'")
    if high_uncached_only:
        clauses.append("uncached_input_tokens >= ?")
        params.append(int(DEFAULT_THRESHOLDS["high_uncached_input_tokens"]))
    if needs_handoff_only:
        clauses.append("suggested_next_action IN ('handoff_or_start_fresh', 'inspect_cold_resume')")
    if recent_only:
        clauses.append("started_at >= datetime('now', '-7 days')")
    where_clause = "WHERE " + " AND ".join(f"({clause})" for clause in clauses) if clauses else ""
    sort_map = {
        "started": "started_at",
        "ended": "ended_at",
        "duration": "duration_minutes",
        "calls": "call_count",
        "tokens": "total_tokens",
        "uncached": "uncached_input_tokens",
        "cache": "avg_cache_ratio",
        "largest_miss": "largest_uncached_input_tokens",
        "context": "max_context_window_percent",
        "thread": "thread_label",
        "action": "suggested_next_action",
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
            FROM thread_work_sessions
            {where_clause}
            ORDER BY {sort_map[sort]} {direction_sql}, started_at DESC, session_index DESC
            {limit_clause}
            """,
            query_params,
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def query_thread_work_session(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    work_session_id: str | None = None,
    thread_key: str | None = None,
    session_index: int | None = None,
) -> dict[str, Any] | None:
    """Return one materialized thread work session."""

    clauses: list[str] = []
    params: list[Any] = []
    if work_session_id:
        clauses.append("work_session_id = ?")
        params.append(work_session_id)
    if thread_key:
        clauses.append("thread_key = ?")
        params.append(thread_key)
    if session_index is not None:
        clauses.append("session_index = ?")
        params.append(int(session_index))
    if not clauses:
        raise ValueError("work_session_id or thread_key/session_index is required")
    with _connect(db_path) as conn:
        init_db(conn)
        row = conn.execute(
            f"""
            SELECT *
            FROM thread_work_sessions
            WHERE {' AND '.join(f'({clause})' for clause in clauses)}
            ORDER BY session_index
            LIMIT 1
            """,
            params,
        ).fetchone()
    return _row_to_dict(row) if row is not None else None


def _query_usage_rows_for_sessions(
    conn: sqlite3.Connection,
    *,
    thread_keys: list[str] | None,
) -> list[sqlite3.Row]:
    thread_key_expr = _thread_key_expression("usage_events.")
    where = ""
    params: list[Any] = []
    if thread_keys is not None:
        placeholders = ", ".join("?" for _key in thread_keys)
        where = f"WHERE {thread_key_expr} IN ({placeholders})"
        params.extend(thread_keys)
    return conn.execute(
        f"""
        SELECT
            usage_events.*,
            {thread_key_expr} AS resolved_thread_key
        FROM usage_events
        {where}
        ORDER BY resolved_thread_key, event_timestamp, cumulative_total_tokens, line_number, record_id
        """,
        params,
    ).fetchall()


def _is_cold_resume_boundary(
    row: Mapping[str, Any],
    previous: Mapping[str, Any],
    thresholds: Mapping[str, float],
    *,
    last_boundary_at: datetime | None,
) -> tuple[bool, float | None]:
    current_at = _parse_timestamp(row.get("event_timestamp"))
    previous_at = _parse_timestamp(previous.get("event_timestamp"))
    idle_minutes = _minutes_between(previous_at, current_at)
    since_last_boundary = _minutes_between(last_boundary_at, current_at)
    if (
        since_last_boundary is not None
        and since_last_boundary < thresholds["cold_resume_cluster_suppression_minutes"]
    ):
        return False, idle_minutes
    input_tokens = _int(row.get("input_tokens"))
    uncached = _int(row.get("uncached_input_tokens"))
    cache_ratio = _float(row.get("cache_ratio"))
    idle_boundary = (
        idle_minutes is not None
        and idle_minutes >= thresholds["cold_resume_idle_minutes"]
        and input_tokens >= thresholds["cold_resume_min_input_tokens"]
        and uncached >= thresholds["cold_resume_min_uncached_tokens"]
        and cache_ratio <= thresholds["cold_resume_max_cache_ratio"]
    )
    huge_boundary = (
        uncached >= thresholds["cold_resume_huge_uncached_tokens"]
        and cache_ratio <= thresholds["cold_resume_huge_max_cache_ratio"]
    )
    return bool(idle_boundary or huge_boundary), idle_minutes


def _materialize_session(
    thread_key: str,
    session_index: int,
    rows: list[dict[str, Any]],
    *,
    start_reason: str,
    idle_minutes_before: float | None,
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
    avg_cache_ratio = cached_tokens / input_tokens if input_tokens else 0.0
    recommendation = _session_recommendation(
        rows,
        start_reason=start_reason,
        uncached_tokens=uncached_tokens,
        avg_cache_ratio=avg_cache_ratio,
    )
    return {
        "work_session_id": _work_session_id(thread_key, session_index, str(first.get("record_id"))),
        "thread_key": thread_key,
        "thread_label": _thread_label(rows),
        "session_index": session_index,
        "start_record_id": first.get("record_id"),
        "end_record_id": last.get("record_id"),
        "cold_start_record_id": first.get("record_id") if start_reason == "cold_resume" else None,
        "start_reason": start_reason,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_minutes": _minutes_between(_parse_timestamp(started_at), _parse_timestamp(ended_at)) or 0.0,
        "idle_minutes_before": idle_minutes_before,
        "call_count": len(rows),
        "model_summary": _compact_summary(row.get("model") for row in rows),
        "effort_summary": _compact_summary(row.get("effort") for row in rows),
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "uncached_input_tokens": uncached_tokens,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
        "avg_cache_ratio": avg_cache_ratio,
        "min_cache_ratio": min((_float(row.get("cache_ratio")) for row in rows), default=0.0),
        "max_context_window_percent": max(
            (_float(row.get("context_window_percent")) for row in rows),
            default=0.0,
        ),
        "largest_uncached_record_id": largest_uncached.get("record_id"),
        "largest_uncached_input_tokens": _int(largest_uncached.get("uncached_input_tokens")),
        "cold_resume_uncached_tokens": _int(first.get("uncached_input_tokens")) if start_reason == "cold_resume" else 0,
        "compaction_count": sum(_is_compaction_related(row) for row in rows),
        "subagent_call_count": sum(_is_subagent(row) for row in rows),
        "auto_review_call_count": sum(_is_auto_review(row) for row in rows),
        "suggested_next_action": recommendation["action"],
        "recommendation_score": recommendation["score"],
        "recommendation_reasons_json": json.dumps(recommendation["reasons"], sort_keys=True),
        "updated_at": updated_at,
    }


def _session_recommendation(
    rows: list[dict[str, Any]],
    *,
    start_reason: str,
    uncached_tokens: int,
    avg_cache_ratio: float,
) -> dict[str, Any]:
    max_context = max((_float(row.get("context_window_percent")) for row in rows), default=0.0)
    reasons: list[str] = []
    score = 0.0
    action = "monitor"
    if start_reason == "cold_resume":
        reasons.append("cold_resume_boundary")
        score += 35
        action = "inspect_cold_resume"
    if uncached_tokens >= 100_000:
        reasons.append("large_uncached_session")
        score += 30
        action = "handoff_or_start_fresh"
    elif uncached_tokens >= 20_000:
        reasons.append("elevated_uncached_session")
        score += 15
    if avg_cache_ratio < 0.25 and uncached_tokens >= 20_000:
        reasons.append("low_cache_reuse")
        score += 20
        action = "inspect_cold_resume"
    if max_context >= 0.60:
        reasons.append("high_context_pressure")
        score += 20
        action = "handoff_or_start_fresh"
    if len(rows) >= 50:
        reasons.append("long_session")
        score += 10
    return {"action": action, "score": score, "reasons": reasons}


def _work_session_id(thread_key: str, session_index: int, start_record_id: str) -> str:
    digest = hashlib.sha256(f"{thread_key}|{session_index}|{start_record_id}".encode()).hexdigest()
    return f"work-session-{digest[:24]}"


def _thread_label(rows: Sequence[Mapping[str, Any]]) -> str:
    for key in ("thread_name", "parent_thread_name", "session_id"):
        for row in rows:
            value = row.get(key)
            if value:
                return str(value)
    return "Unknown thread"


def _compact_summary(values: Iterable[Any]) -> str:
    unique = sorted({str(value) for value in values if value})
    if not unique:
        return "Unknown"
    if len(unique) == 1:
        return unique[0]
    return f"{unique[0]} +{len(unique) - 1}"


def _row_order_key(row: Mapping[str, Any]) -> tuple[str, int, int, str]:
    return (
        str(row.get("event_timestamp") or ""),
        _int(row.get("cumulative_total_tokens")),
        _int(row.get("line_number")),
        str(row.get("record_id") or ""),
    )


def _is_compaction_related(row: Mapping[str, Any]) -> bool:
    reason = str(row.get("call_initiator_reason") or "").lower()
    return "compaction" in reason or "compacted" in reason


def _is_subagent(row: Mapping[str, Any]) -> bool:
    return bool(
        row.get("thread_source") == "subagent"
        or row.get("subagent_type")
        or row.get("parent_session_id")
    )


def _is_auto_review(row: Mapping[str, Any]) -> bool:
    return bool(row.get("model") == "codex-auto-review" or row.get("subagent_type") == "guardian")


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
