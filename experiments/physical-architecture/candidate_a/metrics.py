from __future__ import annotations

import os
import resource
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .schema import database


@dataclass(frozen=True)
class ArtifactMetrics:
    peak_rss_bytes: int
    fact_rows: int
    lifecycle_rows: int
    occurrence_rows: int
    sequence_rows: int
    projection_rows: int
    database_bytes: int
    table_bytes: int
    index_bytes: int
    free_list_bytes: int
    wal_bytes: int
    journal_bytes: int


def _peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if os.uname().sysname == "Darwin":
        return value
    return value * 1024


def _dbstat_bytes(
    connection: sqlite3.Connection,
) -> tuple[int, int]:
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    indexes = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        )
    }
    try:
        sizes = {
            str(row[0]): int(row[1])
            for row in connection.execute(
                "SELECT name, coalesce(sum(pgsize), 0) FROM dbstat GROUP BY name"
            )
        }
    except sqlite3.OperationalError:
        return 0, 0
    return (
        sum(sizes.get(name, 0) for name in tables),
        sum(sizes.get(name, 0) for name in indexes),
    )


def artifact_metrics(path: Path, *, occurrence_rows: int) -> ArtifactMetrics:
    with database(path, read_only=True) as connection:
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        free_pages = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
        table_bytes, index_bytes = _dbstat_bytes(connection)
        fact_rows = int(
            connection.execute(
                """
                SELECT
                    (SELECT count(*) FROM model_calls_visible) +
                    (SELECT count(*) FROM state_changes) +
                    (SELECT count(*) FROM compaction_boundaries) +
                    (SELECT count(*) FROM allowance_observations) +
                    (SELECT count(*) FROM allowance_compatibility) +
                    (SELECT count(*) FROM late_parent_edges)
                """
            ).fetchone()[0]
        )
        lifecycle_rows = int(
            connection.execute(
                """
                SELECT
                    (SELECT count(*) FROM sessions) +
                    (SELECT count(*) FROM turns) +
                    (SELECT count(*) FROM tool_invocations) +
                    (SELECT count(*) FROM activities)
                """
            ).fetchone()[0]
        )
        projection_rows = int(
            connection.execute(
                """
                SELECT
                    (SELECT count(*) FROM session_usage_current) +
                    (SELECT count(*) FROM usage_total_current) +
                    (SELECT count(*) FROM model_effort_usage_current) +
                    (SELECT count(*) FROM project_family_usage_current) +
                    (SELECT count(*) FROM model_usage_current) +
                    (SELECT count(*) FROM turn_action_current) +
                    (SELECT count(*) FROM resource_operation_current) +
                    (SELECT count(*) FROM evidence_page_anchor_current) +
                    (SELECT count(*) FROM tool_family_current)
                """
            ).fetchone()[0]
        )
    wal_path = path.with_name(path.name + "-wal")
    journal_path = path.with_name(path.name + "-journal")
    return ArtifactMetrics(
        peak_rss_bytes=_peak_rss_bytes(),
        fact_rows=fact_rows,
        lifecycle_rows=lifecycle_rows,
        occurrence_rows=occurrence_rows,
        sequence_rows=0,
        projection_rows=projection_rows,
        database_bytes=path.stat().st_size,
        table_bytes=table_bytes,
        index_bytes=index_bytes,
        free_list_bytes=free_pages * page_size,
        wal_bytes=wal_path.stat().st_size if wal_path.exists() else 0,
        journal_bytes=journal_path.stat().st_size if journal_path.exists() else 0,
    )
