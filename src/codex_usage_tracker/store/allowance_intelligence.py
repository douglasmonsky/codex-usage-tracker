"""Bounded indexed reads for materialized allowance intelligence."""

from __future__ import annotations

import base64
import binascii
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

    revision = _source_revision(connection)
    if revision is None:
        return None
    rows = _cycle_partition_rows(
        connection,
        revision=revision,
        window_kind=window_kind,
        cohort_id=cohort_id,
        include_archived=include_archived,
        time_range=None,
        limit=1,
        newest_first=True,
    )
    return rows[0] if rows else None


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
    revision = _source_revision(connection)
    if revision is None:
        return []
    return _cycle_partition_rows(
        connection,
        revision=revision,
        window_kind=window_kind,
        cohort_id=cohort_id,
        include_archived=include_archived,
        time_range=(start_at, end_at),
        limit=None,
        newest_first=False,
    )


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
    rows = _evidence_partition_rows(
        connection,
        revision=revision,
        scope=scope,
        position=position,
        limit=normalized_limit + 1,
    )
    has_more = len(rows) > normalized_limit
    page_rows = rows[:normalized_limit]
    next_cursor = (
        _encode_cursor(revision=revision, row=page_rows[-1], scope=scope) if has_more else None
    )
    return AllowanceEvidencePage(rows=page_rows, next_cursor=next_cursor)


def _cycle_partition_rows(
    connection: sqlite3.Connection,
    *,
    revision: str,
    window_kind: str,
    cohort_id: str | None,
    include_archived: bool,
    time_range: tuple[str, str] | None,
    limit: int | None,
    newest_first: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    direction = "DESC" if newest_first else "ASC"
    ordering = "last_observed_at" if newest_first else "first_observed_at"
    for is_archived in _archive_partitions(include_archived):
        where = ["is_archived = ?", "source_revision = ?", "window_kind = ?"]
        params: list[Any] = [is_archived, revision, window_kind]
        if cohort_id is not None:
            where.append("cohort_key = ?")
            params.append(cohort_id)
        if time_range is not None:
            where.extend(("first_observed_at >= ?", "last_observed_at <= ?"))
            params.extend(time_range)
        limit_sql = " LIMIT ?" if limit is not None else ""
        if limit is not None:
            params.append(limit)
        partition = connection.execute(
            f"SELECT * FROM allowance_cycles WHERE {' AND '.join(where)} "
            f"ORDER BY {ordering} {direction}, cycle_id {direction}{limit_sql}",
            params,  # nosec B608 - query fragments are selected from fixed enums
        ).fetchall()
        rows.extend(_row_to_dict(row) for row in partition)
    return sorted(
        rows,
        key=lambda row: (str(row[ordering] or ""), str(row["cycle_id"])),
        reverse=newest_first,
    )[:limit]


def _evidence_partition_rows(
    connection: sqlite3.Connection,
    *,
    revision: str,
    scope: dict[str, Any],
    position: dict[str, str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    direction = "DESC" if scope["order"] == "desc" else "ASC"
    comparator = "<" if scope["order"] == "desc" else ">"
    for is_archived in _archive_partitions(bool(scope["include_archived"])):
        where = ["is_archived = ?", "source_revision = ?", "end_observed_at IS NOT NULL"]
        params: list[Any] = [is_archived, revision]
        for column, scope_key in (("window_kind", "window_kind"), ("cohort_key", "cohort_id")):
            if scope[scope_key] is not None:
                where.append(f"{column} = ?")
                params.append(scope[scope_key])
        if scope["start_at"] is not None:
            where.append("end_observed_at >= ?")
            params.append(scope["start_at"])
        if scope["end_at"] is not None:
            where.append("end_observed_at <= ?")
            params.append(scope["end_at"])
        if position is not None:
            where.append(
                f"(end_observed_at {comparator} ? OR "
                f"(end_observed_at = ? AND interval_id {comparator} ?))"
            )
            params.extend((position["observed_at"], position["observed_at"], position["row_id"]))
        partition = connection.execute(
            f"SELECT * FROM allowance_intervals WHERE {' AND '.join(where)} "
            f"ORDER BY end_observed_at {direction}, interval_id {direction} LIMIT ?",
            [*params, limit],  # nosec B608 - query fragments are selected from fixed enums
        ).fetchall()
        rows.extend(_row_to_dict(row) for row in partition)
    return sorted(
        rows,
        key=lambda row: (str(row["end_observed_at"]), str(row["interval_id"])),
        reverse=scope["order"] == "desc",
    )[:limit]


def _archive_partitions(include_archived: bool) -> tuple[int, ...]:
    return (0, 1) if include_archived else (0,)


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
        if not isinstance(cursor, str):
            raise TypeError
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True))
        if not isinstance(payload, dict) or set(payload) != {
            "source_revision", "observed_at", "row_id", "order", "scope"
        }:
            raise TypeError
        source_revision = payload["source_revision"]
        observed_at, row_id, order, cursor_scope = (
            payload["observed_at"],
            payload["row_id"],
            payload["order"],
            payload["scope"],
        )
        if (
            not isinstance(source_revision, str)
            or not isinstance(observed_at, str)
            or not observed_at
            or not isinstance(row_id, str)
            or not row_id
            or order not in {"asc", "desc"}
            or not _valid_cursor_scope(cursor_scope)
        ):
            raise TypeError
        if source_revision != revision:
            raise AllowanceCursorError("source_revision_mismatch")
        if cursor_scope != scope or order != scope["order"]:
            raise AllowanceCursorError("cursor_scope_mismatch")
    except AllowanceCursorError:
        raise
    except (binascii.Error, KeyError, TypeError, ValueError, UnicodeError):
        raise AllowanceCursorError("malformed_cursor") from None
    return {"observed_at": observed_at, "row_id": row_id}


def _valid_cursor_scope(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "window_kind", "cohort_id", "start_at", "end_at", "order", "include_archived"
    }:
        return False
    return (
        all(value[key] is None or isinstance(value[key], str) for key in ("window_kind", "cohort_id", "start_at", "end_at"))
        and value["order"] in {"asc", "desc"}
        and type(value["include_archived"]) is bool
    )


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)
