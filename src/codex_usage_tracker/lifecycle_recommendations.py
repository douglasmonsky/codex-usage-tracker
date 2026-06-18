"""Aggregate-only lifecycle guidance for Codex usage investigation."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from codex_usage_tracker.paths import DEFAULT_DB_PATH
from codex_usage_tracker.recommendations import DEFAULT_THRESHOLDS
from codex_usage_tracker.store import connect
from codex_usage_tracker.store_query_sql import _normalize_limit, _normalize_offset
from codex_usage_tracker.store_schema import init_db

LIFECYCLE_RECOMMENDATIONS_SCHEMA_ID = "codex-usage-tracker-lifecycle-recommendations-v1"

VALID_LIFECYCLE_SCOPES = ("call", "work_session", "context_epoch", "thread")

CONFIDENCE_SCORE = {
    "high": 3,
    "medium": 2,
    "low": 1,
}


def lifecycle_recommendations_payload(
    rows: list[dict[str, Any]],
    *,
    filters: dict[str, Any] | None = None,
    limit: int | None = None,
    offset: int = 0,
    total_matched_rows: int | None = None,
) -> dict[str, Any]:
    """Return the stable aggregate-only lifecycle guidance payload."""

    total = len(rows) if total_matched_rows is None else total_matched_rows
    return {
        "schema": LIFECYCLE_RECOMMENDATIONS_SCHEMA_ID,
        "filters": filters or {},
        "row_count": len(rows),
        "total_matched_rows": total,
        "truncated": limit is not None and offset + len(rows) < total,
        "limit": limit,
        "offset": offset,
        "rows": rows,
        "raw_context_included": False,
    }


def query_lifecycle_recommendations(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    record_id: str | None = None,
    thread_key: str | None = None,
    work_session_id: str | None = None,
    context_epoch_id: str | None = None,
    scope: str | None = None,
    limit: int | None = 100,
    offset: int = 0,
    source_limit: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Return aggregate lifecycle recommendation rows and total matched count."""

    if scope and scope not in VALID_LIFECYCLE_SCOPES:
        allowed = ", ".join(VALID_LIFECYCLE_SCOPES)
        raise ValueError(f"scope must be one of: {allowed}")
    normalized_limit = _normalize_limit(limit)
    normalized_offset = _normalize_offset(offset)
    normalized_source_limit = _normalize_limit(source_limit)
    with connect(db_path) as conn:
        init_db(conn)
        rows = _query_lifecycle_source_rows(
            conn,
            record_id=record_id,
            thread_key=thread_key,
            work_session_id=work_session_id,
            context_epoch_id=context_epoch_id,
            source_limit=normalized_source_limit,
        )
    recommendations = lifecycle_recommendations_for_rows(rows)
    if scope:
        recommendations = [row for row in recommendations if row.get("scope") == scope]
    total = len(recommendations)
    if normalized_offset:
        recommendations = recommendations[normalized_offset:]
    if normalized_limit is not None:
        recommendations = recommendations[:normalized_limit]
    return recommendations, total


def lifecycle_recommendations_for_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derive lifecycle recommendation rows from aggregate source rows."""

    recommendations: list[dict[str, Any]] = []
    for row in rows:
        recommendations.extend(_recommendations_for_row(row))
    return sorted(
        recommendations,
        key=lambda item: (
            -float(item.get("score") or 0),
            str(item.get("event_timestamp") or ""),
            str(item.get("record_id") or ""),
            str(item.get("recommendation_key") or ""),
        ),
    )


def _query_lifecycle_source_rows(
    conn: sqlite3.Connection,
    *,
    record_id: str | None,
    thread_key: str | None,
    work_session_id: str | None,
    context_epoch_id: str | None,
    source_limit: int | None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if record_id:
        clauses.append("ue.record_id = ?")
        params.append(record_id)
    if thread_key:
        clauses.append(
            "("
            "ue.thread_key = ? OR "
            "'thread:' || ue.thread_name = ? OR "
            "'session:' || ue.session_id = ? OR "
            "ue.session_id = ?"
            ")"
        )
        params.extend([thread_key, thread_key, thread_key, thread_key])
    if work_session_id:
        clauses.append(
            """
            EXISTS (
                SELECT 1
                FROM thread_work_sessions AS ws_filter
                WHERE ws_filter.work_session_id = ?
                  AND ws_filter.thread_key = ue.thread_key
                  AND ue.event_timestamp >= ws_filter.started_at
                  AND ue.event_timestamp <= ws_filter.ended_at
            )
            """
        )
        params.append(work_session_id)
    if context_epoch_id:
        clauses.append(
            """
            EXISTS (
                SELECT 1
                FROM thread_context_epochs AS ce_filter
                WHERE ce_filter.context_epoch_id = ?
                  AND ce_filter.thread_key = ue.thread_key
                  AND ue.event_timestamp >= ce_filter.started_at
                  AND ue.event_timestamp <= ce_filter.ended_at
            )
            """
        )
        params.append(context_epoch_id)
    where_clause = "WHERE " + " AND ".join(f"({clause})" for clause in clauses) if clauses else ""
    limit_clause = ""
    query_params = list(params)
    if source_limit is not None:
        limit_clause = "LIMIT ?"
        query_params.append(source_limit)
    rows = conn.execute(
        f"""
        WITH receipt_rollup AS (
            SELECT
                record_id,
                COUNT(*) AS receipt_count,
                SUM(event_count) AS receipt_event_count,
                GROUP_CONCAT(receipt_category, ',') AS receipt_categories,
                GROUP_CONCAT(receipt_confidence, ',') AS receipt_confidences
            FROM task_receipts
            GROUP BY record_id
        )
        SELECT
            ue.*,
            receipt_rollup.receipt_count,
            receipt_rollup.receipt_event_count,
            receipt_rollup.receipt_categories,
            receipt_rollup.receipt_confidences,
            primary_impact.estimated_usage_percent AS primary_usage_percent,
            primary_impact.lower_percent AS primary_lower_percent,
            primary_impact.upper_percent AS primary_upper_percent,
            primary_impact.confidence AS primary_usage_confidence,
            primary_impact.status AS primary_usage_status,
            secondary_impact.estimated_usage_percent AS secondary_usage_percent,
            secondary_impact.lower_percent AS secondary_lower_percent,
            secondary_impact.upper_percent AS secondary_upper_percent,
            secondary_impact.confidence AS secondary_usage_confidence,
            secondary_impact.status AS secondary_usage_status,
            (
                SELECT ws.work_session_id
                FROM thread_work_sessions AS ws
                WHERE ws.thread_key = ue.thread_key
                  AND ue.event_timestamp >= ws.started_at
                  AND ue.event_timestamp <= ws.ended_at
                ORDER BY ws.session_index DESC
                LIMIT 1
            ) AS work_session_id,
            (
                SELECT ws.suggested_next_action
                FROM thread_work_sessions AS ws
                WHERE ws.thread_key = ue.thread_key
                  AND ue.event_timestamp >= ws.started_at
                  AND ue.event_timestamp <= ws.ended_at
                ORDER BY ws.session_index DESC
                LIMIT 1
            ) AS work_session_next_action,
            (
                SELECT ce.context_epoch_id
                FROM thread_context_epochs AS ce
                WHERE ce.thread_key = ue.thread_key
                  AND ue.event_timestamp >= ce.started_at
                  AND ue.event_timestamp <= ce.ended_at
                ORDER BY ce.epoch_index DESC
                LIMIT 1
            ) AS context_epoch_id,
            (
                SELECT ce.start_reason
                FROM thread_context_epochs AS ce
                WHERE ce.thread_key = ue.thread_key
                  AND ue.event_timestamp >= ce.started_at
                  AND ue.event_timestamp <= ce.ended_at
                ORDER BY ce.epoch_index DESC
                LIMIT 1
            ) AS context_epoch_start_reason
        FROM usage_events AS ue
        LEFT JOIN receipt_rollup
            ON receipt_rollup.record_id = ue.record_id
        LEFT JOIN usage_impact AS primary_impact
            ON primary_impact.record_id = ue.record_id
           AND primary_impact.window_type = 'primary'
        LEFT JOIN usage_impact AS secondary_impact
            ON secondary_impact.record_id = ue.record_id
           AND secondary_impact.window_type = 'secondary'
        {where_clause}
        ORDER BY ue.event_timestamp DESC, ue.cumulative_total_tokens DESC
        {limit_clause}
        """,
        query_params,
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _recommendations_for_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    receipt_events = int(_number(row.get("receipt_event_count")))
    strongest_receipt = _strongest_confidence(str(row.get("receipt_confidences") or ""))
    has_receipts = receipt_events > 0
    has_strong_receipts = has_receipts and CONFIDENCE_SCORE.get(strongest_receipt, 0) >= 2
    cache_ratio = _number(row.get("cache_ratio"))
    context = _number(row.get("context_window_percent"))
    uncached = _number(row.get("uncached_input_tokens"))
    reasoning = _number(row.get("reasoning_output_tokens"))
    reasoning_ratio = _number(row.get("reasoning_output_ratio"))
    total_tokens = _number(row.get("total_tokens"))
    primary_usage = _optional_number(row.get("primary_usage_percent"))
    secondary_usage = _optional_number(row.get("secondary_usage_percent"))
    usage_score = max(primary_usage or 0.0, secondary_usage or 0.0)
    is_delegated = (
        str(row.get("thread_source") or "user") != "user"
        or bool(row.get("parent_session_id"))
        or bool(row.get("subagent_type"))
        or bool(row.get("agent_role"))
    )
    if is_delegated:
        recommendations.append(
            _recommendation(
                row,
                key="inspect_delegated_work",
                scope="thread",
                confidence="medium",
                evidence_class="derived",
                score=58 + min(total_tokens / 10_000, 25),
                action="Compare this delegated or review work with direct calls before changing workflow.",
                reason="This call is attached to non-user initiated or delegated work, which can hide where usage grew.",
                source_chips=("usage_events",),
            )
        )
    if _is_high_usage_without_receipts(
        total_tokens=total_tokens,
        uncached=uncached,
        usage_score=usage_score,
        has_receipts=has_receipts,
    ):
        recommendations.append(
            _recommendation(
                row,
                key="inspect_low_evidence",
                scope="call",
                confidence="medium" if usage_score or total_tokens >= 50_000 else "low",
                evidence_class="derived",
                score=70 + min(total_tokens / 5_000, 40) + min(usage_score * 10, 30),
                action="Inspect the turn evidence and adjacent calls before continuing this path.",
                reason="Usage was material, but no nearby durable-output receipt signal was materialized for this call.",
                source_chips=("usage_events", "usage_impact", "task_receipts"),
            )
        )
    if reasoning >= DEFAULT_THRESHOLDS["reasoning_min_output_tokens"] and reasoning_ratio >= 0.65:
        recommendations.append(
            _recommendation(
                row,
                key="lower_reasoning",
                scope="call",
                confidence="medium" if not has_strong_receipts else "low",
                evidence_class="derived",
                score=50 + min(reasoning_ratio * 40, 35),
                action="Try a lower reasoning effort for similar follow-up work unless the result quality needs it.",
                reason="Reasoning tokens are a large share of output, so effort level is a likely usage lever.",
                source_chips=("usage_events", "task_receipts"),
            )
        )
    if context >= DEFAULT_THRESHOLDS["high_context_percent"] and cache_ratio < 0.75:
        recommendations.append(
            _recommendation(
                row,
                key="start_fresh",
                scope="thread",
                confidence="medium",
                evidence_class="derived",
                score=64 + min(context * 35, 30) + min(uncached / 2_000, 30),
                action="Start a fresh thread for unrelated follow-up and carry forward only the needed summary.",
                reason="Context pressure is high while fresh uncached input is still substantial.",
                source_chips=("usage_events", "thread_work_sessions", "thread_context_epochs"),
            )
        )
    elif (
        context >= DEFAULT_THRESHOLDS["elevated_context_percent"]
        and has_strong_receipts
    ):
        recommendations.append(
            _recommendation(
                row,
                key="summarize_or_compact",
                scope="context_epoch",
                confidence="medium",
                evidence_class="derived",
                score=54 + min(context * 30, 25),
                action="Summarize the useful outcome before adding more work to this context.",
                reason="The thread appears productive, but context pressure is elevated enough to make later turns expensive.",
                source_chips=("usage_events", "task_receipts", "thread_context_epochs"),
            )
        )
    elif (
        cache_ratio >= 0.75
        and context < DEFAULT_THRESHOLDS["elevated_context_percent"]
        and has_strong_receipts
    ):
        recommendations.append(
            _recommendation(
                row,
                key="continue_thread",
                scope="thread",
                confidence="medium",
                evidence_class="derived",
                score=35 + min(cache_ratio * 20, 15),
                action="Continue in this thread while monitoring context growth.",
                reason="Cache reuse is healthy, context pressure is not elevated, and durable-output receipt signals are present.",
                source_chips=("usage_events", "task_receipts"),
            )
        )
    return _dedupe_recommendations(recommendations)


def _is_high_usage_without_receipts(
    *,
    total_tokens: float,
    uncached: float,
    usage_score: float,
    has_receipts: bool,
) -> bool:
    if has_receipts:
        return False
    return (
        usage_score >= 0.10
        or uncached >= DEFAULT_THRESHOLDS["high_uncached_input_tokens"]
        or total_tokens >= DEFAULT_THRESHOLDS["expensive_low_output_total_tokens"]
    )


def _recommendation(
    row: dict[str, Any],
    *,
    key: str,
    scope: str,
    confidence: str,
    evidence_class: str,
    score: float,
    action: str,
    reason: str,
    source_chips: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema": LIFECYCLE_RECOMMENDATIONS_SCHEMA_ID,
        "record_id": row.get("record_id"),
        "thread_key": row.get("thread_key"),
        "thread_label": row.get("thread_name") or row.get("parent_thread_name") or row.get("session_id"),
        "work_session_id": row.get("work_session_id"),
        "context_epoch_id": row.get("context_epoch_id"),
        "event_timestamp": row.get("event_timestamp"),
        "scope": scope,
        "recommendation_key": key,
        "title": _title_for_key(key),
        "action": action,
        "reason": reason,
        "confidence": confidence,
        "evidence_class": evidence_class,
        "score": round(score, 2),
        "source_chips": list(source_chips),
        "metrics": _metrics_for_row(row),
        "raw_context_included": False,
    }


def _metrics_for_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_tokens": _optional_int(row.get("total_tokens")),
        "uncached_input_tokens": _optional_int(row.get("uncached_input_tokens")),
        "cache_ratio": _optional_number(row.get("cache_ratio")),
        "context_window_percent": _optional_number(row.get("context_window_percent")),
        "reasoning_output_tokens": _optional_int(row.get("reasoning_output_tokens")),
        "reasoning_output_ratio": _optional_number(row.get("reasoning_output_ratio")),
        "receipt_event_count": _optional_int(row.get("receipt_event_count")),
        "primary_usage_percent": _optional_number(row.get("primary_usage_percent")),
        "secondary_usage_percent": _optional_number(row.get("secondary_usage_percent")),
    }


def _title_for_key(key: str) -> str:
    return {
        "continue_thread": "Continue thread",
        "start_fresh": "Start fresh",
        "summarize_or_compact": "Summarize or compact",
        "lower_reasoning": "Lower reasoning",
        "inspect_low_evidence": "Inspect low-evidence usage",
        "inspect_delegated_work": "Inspect delegated work",
    }.get(key, key.replace("_", " ").title())


def _dedupe_recommendations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: -float(item.get("score") or 0)):
        key = str(row.get("recommendation_key") or "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _strongest_confidence(raw: str) -> str:
    strongest = "low"
    for value in (part.strip() for part in raw.split(",") if part.strip()):
        if CONFIDENCE_SCORE.get(value, 0) > CONFIDENCE_SCORE.get(strongest, 0):
            strongest = value
    return strongest


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


def _optional_number(value: object) -> float | None:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _number(value: object) -> float:
    return _optional_number(value) or 0.0
