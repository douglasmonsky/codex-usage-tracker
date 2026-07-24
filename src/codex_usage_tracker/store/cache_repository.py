"""Single transaction-bound owner for refresh cache persistence."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping


class SQLiteCacheRepository:
    """Read and mutate refresh cache keys on the caller's transaction."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM refresh_meta WHERE key = ?",
            (key,),
        ).fetchone()
        return None if row is None else str(row["value"])

    def set_many(self, values: Mapping[str, str]) -> None:
        self._conn.executemany(
            """
            INSERT INTO refresh_meta (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            values.items(),
        )

    def delete(self, key: str) -> None:
        self._conn.execute("DELETE FROM refresh_meta WHERE key = ?", (key,))

    def clear(self) -> None:
        self._conn.execute("DELETE FROM refresh_meta")
