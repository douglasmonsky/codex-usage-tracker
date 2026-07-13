"""Immutable evidence metadata captured when compression candidates publish."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

RecordMetadata = tuple[str | None, str | None, str | None]


def record_metadata_by_id(
    conn: sqlite3.Connection,
    record_ids: Iterable[str],
) -> dict[str, RecordMetadata]:
    """Return model, thread, and timestamp metadata for persisted evidence claims."""
    normalized = sorted({record_id for record_id in record_ids if record_id})
    result: dict[str, RecordMetadata] = {}
    for offset in range(0, len(normalized), 500):
        batch = normalized[offset : offset + 500]
        placeholders = ",".join("?" for _value in batch)
        query = "\n".join(
            (
                "SELECT record_id, model,",
                "       COALESCE(thread_key, thread_name, session_id) AS thread_key,",
                "       event_timestamp",
                "FROM usage_events",
                "WHERE record_id IN (",
                placeholders,
                ")",
            )
        )
        rows = conn.execute(query, batch).fetchall()
        result.update(_metadata_mapping(rows))
    return result


def _metadata_mapping(rows: Iterable[sqlite3.Row]) -> dict[str, RecordMetadata]:
    return {
        str(row["record_id"]): (
            row["model"],
            row["thread_key"],
            row["event_timestamp"],
        )
        for row in rows
    }
