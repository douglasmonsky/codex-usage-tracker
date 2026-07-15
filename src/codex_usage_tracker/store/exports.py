"""Store export helpers."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.core.projects import apply_project_privacy_to_rows, validate_privacy_mode
from codex_usage_tracker.core.schema import USAGE_EVENT_COLUMN_NAMES
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.query_sql import normalize_limit
from codex_usage_tracker.store.rows import row_to_dict
from codex_usage_tracker.store.schema import init_db

EVENT_COLUMNS = list(USAGE_EVENT_COLUMN_NAMES)


def export_usage_csv(
    output_path: Path,
    db_path: Path = DEFAULT_DB_PATH,
    limit: int | None = None,
    privacy_mode: str = "normal",
) -> int:
    """Export aggregate usage rows as CSV."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    privacy_mode = validate_privacy_mode(privacy_mode)
    sql = "SELECT * FROM canonical_usage_events ORDER BY event_timestamp, cumulative_total_tokens"
    params: tuple[int, ...] = ()
    normalized_limit = normalize_limit(limit)
    if normalized_limit is not None:
        sql += " LIMIT ?"
        params = (normalized_limit,)
    with connect(db_path) as conn:
        init_db(conn)
        rows = [row_to_dict(row) for row in conn.execute(sql, params)]
    rows = apply_project_privacy_to_rows(rows, privacy_mode=privacy_mode)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVENT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(_csv_row(row))
    return len(rows)


def _csv_row(row: dict[str, Any]) -> dict[str, Any]:
    return {column: row.get(column) for column in EVENT_COLUMNS}
