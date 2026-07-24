"""SQL row and bounded JSON helpers for durable analysis jobs."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

_RAW_CONTEXT_KEYS = frozenset(
    {
        "arguments",
        "chat_history",
        "command",
        "content",
        "conversation",
        "input_text",
        "output_text",
        "prompt",
        "raw_context",
        "raw_excerpt",
        "stderr",
        "stdout",
        "tool_output",
        "tool_outputs",
        "transcript",
        "turns",
    }
)


def _select_job(conn: sqlite3.Connection, job_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM analysis_jobs WHERE job_id = ?",
        (job_id,),
    ).fetchone()


def _select_active(
    conn: sqlite3.Connection,
    job_kind: str,
    semantic_key: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM analysis_jobs
        WHERE job_kind = ?
          AND semantic_key = ?
          AND status IN ('queued', 'running')
        LIMIT 1
        """,
        (job_kind, semantic_key),
    ).fetchone()


def _select_reusable(
    conn: sqlite3.Connection,
    *,
    job_kind: str,
    semantic_key: str,
    source_revision: str,
    result_schema: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM analysis_jobs
        WHERE job_kind = ?
          AND semantic_key = ?
          AND source_revision = ?
          AND result_schema = ?
          AND status = 'completed'
          AND result_json IS NOT NULL
        ORDER BY completed_at DESC, job_id DESC
        LIMIT 1
        """,
        (job_kind, semantic_key, source_revision, result_schema),
    ).fetchone()


def _compatible(
    row: sqlite3.Row,
    *,
    source_revision: str,
    request_schema: str,
    result_schema: str,
) -> bool:
    return (
        str(row["source_revision"]) == source_revision
        and str(row["request_schema"]) == request_schema
        and str(row["result_schema"]) == result_schema
    )


def _interrupt_row(conn: sqlite3.Connection, job_id: str, timestamp: str) -> None:
    conn.execute(
        """
        UPDATE analysis_jobs
        SET
            status = 'interrupted',
            progress_json = ?,
            result_json = NULL,
            error_json = ?,
            completed_at = ?,
            updated_at = ?,
            last_accessed_at = ?
        WHERE job_id = ?
        """,
        (
            _json_dump({"percent": 0, "stage": "interrupted"}),
            _json_dump(
                {
                    "code": "job.interrupted",
                    "severity": "warning",
                    "message": "The previous process stopped before this job completed.",
                    "remediation": "Start the analysis again if the result is still needed.",
                }
            ),
            timestamp,
            timestamp,
            timestamp,
            job_id,
        ),
    )


def _touch(conn: sqlite3.Connection, job_id: str, timestamp: str) -> None:
    conn.execute(
        "UPDATE analysis_jobs SET last_accessed_at = ? WHERE job_id = ?",
        (timestamp, job_id),
    )


def _bounded_json(
    value: object,
    *,
    budget: int,
    label: str,
    reject_raw_context: bool = False,
    allowed_root_keys: frozenset[str] | None = None,
) -> str:
    if reject_raw_context and _contains_raw_context(value):
        raise ValueError("generic jobs must not contain raw context")
    if allowed_root_keys is not None:
        _validate_root_keys(value, allowed_root_keys, label=label)
    payload = _json_dump(value)
    if len(payload.encode("utf-8")) > budget:
        raise ValueError(f"{label} exceeds {budget}-byte persistence budget")
    return payload


def _optional_bounded_json(
    value: object,
    *,
    budget: int,
    label: str,
    allowed_root_keys: frozenset[str] | None = None,
) -> str | None:
    if value is None:
        return None
    return _bounded_json(
        value,
        budget=budget,
        label=label,
        reject_raw_context=True,
        allowed_root_keys=allowed_root_keys,
    )


def _require_completed_result(
    state: str,
    result_schema: str | None,
    result_json: str | None,
) -> None:
    if state == "completed" and (result_schema is None or result_json is None):
        raise ValueError("completed analysis jobs require a schema and result")


def _validate_root_keys(
    value: object,
    allowed: frozenset[str],
    *,
    label: str,
) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    unknown = {str(key) for key in value} - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"{label} contains unsupported fields: {names}")


def _contains_raw_context(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).lower() in _RAW_CONTEXT_KEYS or _contains_raw_context(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_raw_context(item) for item in value)
    return False


def _json_dump(value: object) -> str:
    try:
        return json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise ValueError("job persistence values must be JSON-safe") from error


def _json_safe(value: object) -> object:
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("job persistence mapping keys must be strings")
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"unsupported job persistence value: {type(value).__name__}")


def _json_load(value: object) -> Any:
    if not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _decode(row: sqlite3.Row) -> dict[str, object]:
    decoded: dict[str, object] = dict(row)
    for column, output in (
        ("request_json", "request"),
        ("progress_json", "progress"),
        ("result_json", "result"),
        ("error_json", "error"),
    ):
        value = decoded.pop(column)
        decoded[output] = _json_load(value) if value is not None else None
    return decoded


def _timestamp(now: datetime | None) -> str:
    return _as_utc(now).isoformat().replace("+00:00", "Z")


def _as_utc(now: datetime | None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("job timestamps must be timezone-aware")
    return current.astimezone(timezone.utc)
