"""SQLite connection helpers for tracker persistence."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH


class DatabaseIntegrityError(RuntimeError):
    """Raised when a connection cannot enforce required SQLite safeguards."""


def configure_connection(
    conn: sqlite3.Connection,
    *,
    query_only: bool = False,
    enable_wal: bool = True,
    busy_timeout_ms: int = 5_000,
) -> sqlite3.Connection:
    """Apply and verify the tracker-wide SQLite connection policy."""
    if busy_timeout_ms < 0:
        raise ValueError("busy_timeout_ms must be non-negative")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()
    if foreign_keys is None or int(foreign_keys[0]) != 1:
        raise DatabaseIntegrityError("SQLite foreign-key enforcement is unavailable")

    conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")  # nosec B608
    if query_only:
        conn.execute("PRAGMA query_only = ON")
    if enable_wal and not query_only:
        with suppress(sqlite3.DatabaseError):
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            if str(journal_mode).lower() != "wal":
                conn.execute("PRAGMA journal_mode = WAL")
    return conn


def open_read_only_connection(
    db_path: Path,
    *,
    timeout: float = 5.0,
    busy_timeout_ms: int | None = None,
) -> sqlite3.Connection:
    """Open one configured read-only connection; the caller owns closing it."""
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=timeout)
    try:
        effective_busy_timeout_ms = (
            max(0, round(timeout * 1_000))
            if busy_timeout_ms is None
            else busy_timeout_ms
        )
        return configure_connection(
            conn,
            query_only=True,
            enable_wal=False,
            busy_timeout_ms=effective_busy_timeout_ms,
        )
    except BaseException:
        conn.close()
        raise


@contextmanager
def connect_read_only(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    timeout: float = 5.0,
    busy_timeout_ms: int | None = None,
) -> Iterator[sqlite3.Connection]:
    """Yield a configured read-only SQLite connection."""
    conn = open_read_only_connection(
        db_path,
        timeout=timeout,
        busy_timeout_ms=busy_timeout_ms,
    )
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def connect(db_path: Path = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    """Yield a configured writable SQLite connection with transaction cleanup."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5.0)
    try:
        configure_connection(conn)
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_script(conn: sqlite3.Connection, script: str) -> None:
    """Execute a SQL script without sqlite3.executescript's implicit COMMIT."""
    statement_lines: list[str] = []
    for line in script.splitlines(keepends=True):
        statement_lines.append(line)
        statement = "".join(statement_lines)
        if not sqlite3.complete_statement(statement):
            continue
        if statement.strip():
            conn.execute(statement)
        statement_lines.clear()

    remainder = "".join(statement_lines)
    if remainder.strip():
        raise sqlite3.OperationalError("incomplete SQL statement")
