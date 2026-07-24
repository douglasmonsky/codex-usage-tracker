"""Read-only, bounded SQLite integrity diagnostics."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from codex_usage_tracker.store.connection import (
    DatabaseIntegrityError,
    connect_read_only,
)

INTEGRITY_SCHEMA = "codex-usage-tracker.database-integrity.v1"
MAX_INTEGRITY_ERRORS = 100
MAX_AFFECTED_TABLES = 20


def _unknown_report(error: str) -> dict[str, object]:
    return {
        "schema": INTEGRITY_SCHEMA,
        "state": "unknown",
        "readable": False,
        "foreign_keys_enabled": False,
        "integrity_error_count": 0,
        "foreign_key_violation_count": 0,
        "affected_tables": [],
        "affected_tables_truncated": False,
        "error": error,
    }


def check_database_integrity(db_path: Path) -> dict[str, object]:
    """Run bounded SQLite integrity checks without mutating or repairing the DB."""
    if not db_path.is_file():
        return _unknown_report("database_missing")

    try:
        with connect_read_only(db_path) as conn:
            foreign_keys_enabled = bool(conn.execute("PRAGMA foreign_keys").fetchone()[0])
            integrity_rows = conn.execute(
                f"PRAGMA integrity_check({MAX_INTEGRITY_ERRORS})"
            ).fetchall()
            integrity_errors = [
                str(row[0]) for row in integrity_rows if str(row[0]).lower() != "ok"
            ]

            violation_count = 0
            affected_tables: list[str] = []
            seen_tables: set[str] = set()
            affected_tables_truncated = False
            for row in conn.execute("PRAGMA foreign_key_check"):
                violation_count += 1
                table = str(row[0])
                if table in seen_tables:
                    continue
                seen_tables.add(table)
                if len(affected_tables) < MAX_AFFECTED_TABLES:
                    affected_tables.append(table)
                else:
                    affected_tables_truncated = True

            failed = bool(integrity_errors or violation_count or not foreign_keys_enabled)
            return {
                "schema": INTEGRITY_SCHEMA,
                "state": "fail" if failed else "pass",
                "readable": True,
                "foreign_keys_enabled": foreign_keys_enabled,
                "integrity_error_count": len(integrity_errors),
                "foreign_key_violation_count": violation_count,
                "affected_tables": affected_tables,
                "affected_tables_truncated": affected_tables_truncated,
                "error": None,
            }
    except (DatabaseIntegrityError, OSError, sqlite3.Error):
        return _unknown_report("database_unreadable")
