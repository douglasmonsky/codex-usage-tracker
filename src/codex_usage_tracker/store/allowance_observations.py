"""Queries and compatibility exports for normalized allowance observations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.allowance_observation_sync import (
    ALLOWANCE_OBSERVATION_COLUMNS,
    rebuild_allowance_observations,
    sync_allowance_observations_for_record_ids,
)
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.rows import row_to_dict
from codex_usage_tracker.store.schema import init_db

__all__ = [
    "ALLOWANCE_OBSERVATION_COLUMNS",
    "query_allowance_observations",
    "rebuild_allowance_observations",
    "sync_allowance_observations_for_record_ids",
]


def query_allowance_observations(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    include_archived: bool = False,
    window_kind: str | None = None,
    limit: int | None = 1000,
    newest_first: bool = False,
) -> list[dict[str, Any]]:
    """Return normalized allowance observations from the newest limited tail."""

    with connect(db_path) as conn:
        init_db(conn)
        where: list[str] = []
        params: list[Any] = []
        if not include_archived:
            where.append("is_archived = 0")
        if window_kind:
            where.append("window_kind = ?")
            params.append(window_kind)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        columns = ", ".join(ALLOWANCE_OBSERVATION_COLUMNS)
        ascending_order = "event_timestamp ASC, cumulative_total_tokens ASC, window_key ASC"
        descending_order = "event_timestamp DESC, cumulative_total_tokens DESC, window_key DESC"
        display_order = descending_order if newest_first else ascending_order
        if limit is None:
            rows = conn.execute(
                f"""
                SELECT {columns}
                FROM allowance_observations
                {where_sql}
                ORDER BY {display_order}
                """,
                params,
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                SELECT * FROM (
                    SELECT {columns}
                    FROM allowance_observations
                    {where_sql}
                    ORDER BY {descending_order}
                    LIMIT ?
                ) AS newest
                ORDER BY {display_order}
                """,
                [*params, max(int(limit), 0)],
            ).fetchall()
    return [row_to_dict(row) for row in rows]
