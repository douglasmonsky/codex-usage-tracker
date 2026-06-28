"""Call-detail payload helpers for the dashboard server."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from urllib.parse import parse_qs

from codex_usage_tracker.server_utils import first_query_value
from codex_usage_tracker.store import query_usage_record


class MissingRecordIdError(ValueError):
    """Raised when a call-detail request omits a record id."""


class UsageRecordNotFoundError(LookupError):
    """Raised when a requested usage record does not exist."""


AnnotateRows = Callable[[list[dict[str, object]]], list[dict[str, object]]]


def call_detail_payload(
    query: str,
    *,
    db_path: Path,
    annotate_rows: AnnotateRows,
) -> dict[str, object]:
    """Build the call-detail API payload."""
    record_id = _required_record_id(query)
    row = _load_usage_record(db_path, record_id)
    rows_by_id = _annotated_rows_by_id(
        [row, *_load_adjacent_records(db_path, row)],
        annotate_rows,
    )
    selected_row = rows_by_id.get(record_id, row)
    previous_record, next_record = _adjacent_records(rows_by_id, row)
    return {
        "schema": "codex-usage-tracker-call-v1",
        "record": selected_row,
        "previous_record": previous_record,
        "next_record": next_record,
        "adjacent_records": [
            candidate
            for candidate in (previous_record, selected_row, next_record)
            if candidate
        ],
        "previous_record_id": row.get("previous_record_id"),
        "next_record_id": row.get("next_record_id"),
        "raw_context_included": False,
    }


def _required_record_id(query: str) -> str:
    params = parse_qs(query)
    record_id = first_query_value(params.get("record_id")) or first_query_value(params.get("record"))
    if not record_id:
        raise MissingRecordIdError("record_id required")
    return record_id


def _load_usage_record(db_path: Path, record_id: str) -> dict[str, object]:
    row = query_usage_record(db_path=db_path, record_id=record_id)
    if row is None:
        raise UsageRecordNotFoundError(f"No usage record found: {record_id}")
    return row


def _load_adjacent_records(
    db_path: Path,
    row: dict[str, object],
) -> list[dict[str, object] | None]:
    return [
        query_usage_record(db_path=db_path, record_id=adjacent_id)
        for adjacent_id in _adjacent_ids(row)
    ]


def _annotated_rows_by_id(
    rows: list[dict[str, object] | None],
    annotate_rows: AnnotateRows,
) -> dict[str, dict[str, object]]:
    return {
        str(candidate["record_id"]): candidate
        for candidate in annotate_rows([candidate for candidate in rows if candidate])
        if candidate.get("record_id")
    }


def _adjacent_records(
    rows_by_id: dict[str, dict[str, object]],
    row: dict[str, object],
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    return (
        rows_by_id.get(str(row.get("previous_record_id") or "")),
        rows_by_id.get(str(row.get("next_record_id") or "")),
    )


def _adjacent_ids(row: dict[str, object]) -> Iterable[str]:
    for adjacent_id in (row.get("previous_record_id"), row.get("next_record_id")):
        if adjacent_id:
            yield str(adjacent_id)
