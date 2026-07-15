"""Bounded indexed reads for materialized allowance intelligence."""

from __future__ import annotations

import base64
import json
import sqlite3
from dataclasses import dataclass
from typing import Any


class AllowanceCursorError(ValueError):
    """A cursor cannot safely continue an allowance evidence query.

    ``reason`` is deliberately stable so HTTP adapters can map this error to
    a conflict response without parsing a human-facing message.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class AllowanceEvidencePage:
    """One bounded evidence page and an opaque continuation cursor."""

    rows: list[dict[str, Any]]
    next_cursor: str | None


def query_latest_allowance_state(
    connection: sqlite3.Connection,
    *,
    window_kind: str,
    cohort_id: str | None = None,
    include_archived: bool = False,
) -> dict[str, Any] | None:
    """Return the newest materialized cycle in the requested archive scope."""

    where, params = _cycle_scope(
        window_kind=window_kind, cohort_id=cohort_id, include_archived=include_archived
    )
    revision = _source_revision(connection)
    if revision is None:
        return None
    where.append("source_revision = ?")
    params.append(revision)
    row = connection.execute(
        f"""
        SELECT * FROM allowance_cycles
        WHERE {' AND '.join(where)}
        ORDER BY last_observed_at DESC, cycle_id DESC
        LIMIT 1
        """,  # nosec B608 - clauses are fixed internal query fragments
        params,
    ).fetchone()
    return _row_to_dict(row) if row is not None else None


def query_allowance_series(
    connection: sqlite3.Connection,
    *,
    start_at: str | None,
    end_at: str | None,
    window_kind: str,
    cohort_id: str | None = None,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """Return chronologically ordered cycles wholly inside a finite range."""

    if not start_at or not end_at:
        raise ValueError("start_at and end_at are required")
    where, params = _cycle_scope(
        window_kind=window_kind, cohort_id=cohort_id, include_archived=include_archived
    )
    revision = _source_revision(connection)
    if revision is None:
        return []
    where.extend(("source_revision = ?", "first_observed_at >= ?", "last_observed_at <= ?"))
    params.extend((revision, start_at, end_at))
    rows = connection.execute(
        f"""
        SELECT * FROM allowance_cycles
        WHERE {' AND '.join(where)}
        ORDER BY first_observed_at ASC, cycle_id ASC
        """,  # nosec B608 - clauses are fixed internal query fragments
        params,
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def query_allowance_evidence(
    connection: sqlite3.Connection,
    *,
    limit: int = 50,
    cursor: str | None = None,
    window_kind: str | None = None,
    cohort_id: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    order: str = "desc",
    include_archived: bool = False,
) -> AllowanceEvidencePage:
    """Return one revision-bound, keyset-paginated evidence page."""

    if order not in {"asc", "desc"}:
        raise ValueError("order must be 'asc' or 'desc'")
    normalized_limit = min(500, max(1, int(limit)))
    revision = _source_revision(connection)
    if revision is None:
        if cursor is not None:
            raise AllowanceCursorError("source_revision_mismatch")
        return AllowanceEvidencePage(rows=[], next_cursor=None)

    scope = {
        "window_kind": window_kind,
        "cohort_id": cohort_id,
        "start_at": start_at,
        "end_at": end_at,
        "order": order,
        "include_archived": include_archived,
    }
    position = _decode_cursor(cursor, revision=revision, scope=scope) if cursor else None
    where = ["source_revision = ?"]
    params: list[Any] = [revision]
    if not include_archived:
        where.append("is_archived = 0")
    if window_kind is not None:
        where.append("window_kind = ?")
        params.append(window_kind)
    if cohort_id is not None:
        where.append("cohort_key = ?")
        params.append(cohort_id)
    if start_at is not None:
        where.append("end_observed_at >= ?")
        params.append(start_at)
    if end_at is not None:
        where.append("end_observed_at <= ?")
        params.append(end_at)
    if position is not None:
        comparator = "<" if order == "desc" else ">"
        where.append(
            f"(end_observed_at {comparator} ? OR "
            f"(end_observed_at = ? AND interval_id {comparator} ?))"
        )
        params.extend((position["observed_at"], position["observed_at"], position["row_id"]))
    direction = "DESC" if order == "desc" else "ASC"
    rows = connection.execute(
        f"""
        SELECT * FROM allowance_intervals
        WHERE {' AND '.join(where)}
        ORDER BY end_observed_at {direction}, interval_id {direction}
        LIMIT ?
        """,  # nosec B608 - direction comes from validated enum; clauses are fixed
        [*params, normalized_limit + 1],
    ).fetchall()
    has_more = len(rows) > normalized_limit
    page_rows = [_row_to_dict(row) for row in rows[:normalized_limit]]
    next_cursor = (
        _encode_cursor(revision=revision, row=page_rows[-1], scope=scope) if has_more else None
    )
    return AllowanceEvidencePage(rows=page_rows, next_cursor=next_cursor)


def _cycle_scope(
    *, window_kind: str, cohort_id: str | None, include_archived: bool
) -> tuple[list[str], list[Any]]:
    where = ["window_kind = ?"]
    params: list[Any] = [window_kind]
    if not include_archived:
        where.insert(0, "is_archived = 0")
    if cohort_id is not None:
        where.append("cohort_key = ?")
        params.append(cohort_id)
    return where, params


def _source_revision(connection: sqlite3.Connection) -> str | None:
    row = connection.execute(
        "SELECT source_revision FROM allowance_source_state WHERE state_id = 1"
    ).fetchone()
    return None if row is None else str(row[0])


def _encode_cursor(*, revision: str, row: dict[str, Any], scope: dict[str, Any]) -> str:
    payload = {
        "source_revision": revision,
        "observed_at": row["end_observed_at"],
        "row_id": row["interval_id"],
        "order": scope["order"],
        "scope": scope,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str, *, revision: str, scope: dict[str, Any]) -> dict[str, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if not isinstance(payload, dict):
            raise TypeError
        if payload.get("source_revision") != revision:
            raise AllowanceCursorError("source_revision_mismatch")
        if payload.get("scope") != scope or payload.get("order") != scope["order"]:
            raise AllowanceCursorError("cursor_scope_mismatch")
        observed_at, row_id = payload["observed_at"], payload["row_id"]
        if not isinstance(observed_at, str) or not isinstance(row_id, str):
            raise TypeError
    except AllowanceCursorError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError):
        raise AllowanceCursorError("malformed_cursor") from None
    return {"observed_at": observed_at, "row_id": row_id}


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)
