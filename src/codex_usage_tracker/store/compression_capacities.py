"""Bounded reads of detector-ready record/component token capacities."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db

_COMPONENT_COLUMNS = {
    "cached_input": "cached_input_tokens",
    "uncached_input": "uncached_input_tokens",
    "output": "output_tokens",
    "reasoning_output": "reasoning_output_tokens",
    "content_fragment": "content_exposure_tokens",
    "tool_output": "tool_output_exposure_tokens",
}


def load_record_component_capacities(
    db_path: Path,
    record_ids: Iterable[str],
) -> dict[tuple[str, str], int]:
    """Return exact persisted capacities for selected record IDs."""
    normalized = sorted({str(record_id) for record_id in record_ids if record_id})
    capacities: dict[tuple[str, str], int] = {}
    with connect(db_path) as conn:
        init_db(conn)
        for offset in range(0, len(normalized), 500):
            batch = normalized[offset : offset + 500]
            placeholders = ",".join("?" for _value in batch)
            query = "\n".join(
                (
                    "SELECT record_id,",
                    ", ".join(_COMPONENT_COLUMNS.values()),
                    "FROM compression_record_facts",
                    "WHERE record_id IN (",
                    placeholders,
                    ")",
                )
            )
            rows = conn.execute(query, batch).fetchall()
            for row in rows:
                capacities.update(_row_capacities(row))
    return capacities


def _row_capacities(row) -> dict[tuple[str, str], int]:
    record_id = str(row["record_id"])
    return {
        (record_id, component): max(0, int(row[column] or 0))
        for component, column in _COMPONENT_COLUMNS.items()
    }
