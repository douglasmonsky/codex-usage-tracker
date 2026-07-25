"""Read-only observed-usage queries for the Evidence Console Home surface."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect_read_only
from codex_usage_tracker.store.dashboard_queries import (
    OBSERVED_USAGE_RECONCILIATION_THRESHOLD,
    _latest_observed_usage_row,
    observed_usage_reconciliation,
    observed_usage_window,
)
from codex_usage_tracker.store.query_sql import usage_where_clause
from codex_usage_tracker.store.rows import row_to_dict


def query_home_latest_observed_usage(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Return the latest committed usage-limit snapshot without database writes."""
    if not db_path.exists():
        return _empty_observed_usage()
    where_clause, params = usage_where_clause(
        include_archived=include_archived,
        legacy_archive_path_fallback=False,
    )
    observed_clause = (
        "rate_limit_primary_used_percent IS NOT NULL "
        "OR rate_limit_secondary_used_percent IS NOT NULL"
    )
    canonical_observed_clause = f"is_duplicate = 0 AND ({observed_clause})"
    scoped_where = (
        f"{where_clause} AND {canonical_observed_clause}"
        if where_clause
        else f"WHERE {canonical_observed_clause}"
    )
    with connect_read_only(db_path, timeout=1.0) as conn:
        try:
            row = _latest_observed_usage_row(
                conn,
                scoped_where=scoped_where,
                params=params,
            )
            reconciliation = observed_usage_reconciliation(
                conn,
                scoped_where=scoped_where,
                params=params,
                selected_row=row,
            )
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc).lower():
                raise
            return _empty_observed_usage()
    if row is None:
        return {"available": False, "windows": [], "reconciliation": reconciliation}
    data = row_to_dict(row)
    return {
        "available": True,
        "record_id": data.get("record_id"),
        "observed_at": data.get("event_timestamp"),
        "line_number": data.get("line_number"),
        "plan_type": data.get("rate_limit_plan_type"),
        "limit_id": data.get("rate_limit_limit_id"),
        "source": "token_count.rate_limits",
        "windows": [
            window
            for window in (
                observed_usage_window(data, "primary"),
                observed_usage_window(data, "secondary"),
            )
            if window is not None
        ],
        "reconciliation": reconciliation,
    }


def _empty_observed_usage() -> dict[str, Any]:
    return {
        "available": False,
        "windows": [],
        "reconciliation": {
            "recommended": False,
            "reason": None,
            "suggested_action": None,
            "consecutive_alternate_rows": 0,
            "threshold": OBSERVED_USAGE_RECONCILIATION_THRESHOLD,
            "latest_limit_id": None,
            "latest_plan_type": None,
            "latest_observed_at": None,
            "selected_observed_at": None,
            "selected_limit_id": None,
        },
    }
