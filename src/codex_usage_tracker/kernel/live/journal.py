"""Small persistent post-commit generation journal."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_RETENTION = 2_048
MAX_RETENTION = 100_000
MAX_REPLAY = 500
_SAFE_PAYLOAD_KEYS = frozenset(
    {
        "changed_sources",
        "deleted_rows",
        "inserted_calls",
        "inserted_tools",
    }
)
_EVENT_KINDS = frozenset({"generation_committed"})


@dataclass(frozen=True)
class JournalEvent:
    event_id: int
    publication_id: str
    generation: int
    event_kind: str
    selector: str | None
    occurred_at: str
    payload: dict[str, Any]

    def to_sse(self) -> str:
        data = json.dumps(
            {
                "generation": self.generation,
                "kind": self.event_kind,
                "publication_id": self.publication_id,
                "selector": self.selector,
                "occurred_at": self.occurred_at,
                "payload": self.payload,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return f"id: {self.event_id}\nevent: {self.event_kind}\ndata: {data}\n\n"


@dataclass(frozen=True)
class JournalReplay:
    events: tuple[JournalEvent, ...]
    earliest_event_id: int | None
    latest_event_id: int | None
    latest_generation: int | None
    latest_publication_id: str | None
    truncated: bool


class GenerationJournal:
    """Append and replay bounded privacy-safe events in the operational DB."""

    def __init__(self, operational_path: Path, *, retention: int = DEFAULT_RETENTION):
        if not 1 <= retention <= MAX_RETENTION:
            raise ValueError("journal retention is out of bounds")
        self._path = operational_path.resolve()
        self._retention = retention

    def publish_generation(
        self,
        generation: int,
        *,
        publication_id: str,
        changed_sources: int,
        inserted_calls: int,
        inserted_tools: int,
        deleted_rows: int,
    ) -> JournalEvent:
        return self.append(
            generation=generation,
            event_kind="generation_committed",
            selector=None,
            payload={
                "changed_sources": changed_sources,
                "inserted_calls": inserted_calls,
                "inserted_tools": inserted_tools,
                "deleted_rows": deleted_rows,
            },
            event_key=f"publication:{publication_id}",
            publication_id=publication_id,
        )

    def append(
        self,
        *,
        generation: int,
        event_kind: str,
        selector: str | None,
        payload: dict[str, Any],
        event_key: str | None = None,
        publication_id: str | None = None,
    ) -> JournalEvent:
        if generation < 1 or event_kind not in _EVENT_KINDS:
            raise ValueError("journal event identity is invalid")
        if selector is not None:
            raise ValueError("journal selector is not supported")
        publication = publication_id or event_key
        if publication is None or not _safe_identity(publication):
            raise ValueError("journal publication identity is invalid")
        _validate_payload(payload)
        key = event_key or f"{generation}:{event_kind}:{selector or '-'}"
        if not _safe_identity(key):
            raise ValueError("journal event identity is invalid")
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM live_events WHERE event_key = ?",
                (key,),
            ).fetchone()
            if existing is not None:
                return _event(existing)
            event_id = int(
                connection.execute(
                    "SELECT COALESCE(MAX(event_id), 0) + 1 FROM live_events"
                ).fetchone()[0]
            )
            connection.execute(
                """
                INSERT INTO live_events(
                    event_id, event_key, publication_id, generation, event_kind,
                    selector, occurred_at, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                """,
                (
                    event_id,
                    key,
                    publication,
                    generation,
                    event_kind,
                    selector,
                    json.dumps(
                        payload,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                ),
            )
            connection.execute(
                "DELETE FROM live_events WHERE event_id <= ?",
                (event_id - self._retention,),
            )
            row = connection.execute(
                "SELECT * FROM live_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("journal event was not committed")
        return _event(row)

    def replay(self, last_event_id: int | None, *, limit: int) -> JournalReplay:
        if last_event_id is not None and last_event_id < 0:
            raise ValueError("Last-Event-ID is invalid")
        if not 1 <= limit <= MAX_REPLAY:
            raise ValueError("journal replay limit is out of bounds")
        with closing(self._connect()) as connection:
            bounds = connection.execute(
                """
                SELECT MIN(event_id), MAX(event_id), MAX(generation)
                FROM live_events
                """
            ).fetchone()
            latest = connection.execute(
                """
                SELECT publication_id
                FROM live_events
                ORDER BY event_id DESC
                LIMIT 1
                """
            ).fetchone()
            rows = connection.execute(
                """
                SELECT *
                FROM live_events
                WHERE event_id > ?
                ORDER BY event_id
                LIMIT ?
                """,
                (last_event_id or 0, limit + 1),
            ).fetchall()
        return JournalReplay(
            events=tuple(_event(row) for row in rows[:limit]),
            earliest_event_id=bounds[0],
            latest_event_id=bounds[1],
            latest_generation=bounds[2],
            latest_publication_id=latest[0] if latest is not None else None,
            truncated=len(rows) > limit,
        )

    def _connect(self) -> sqlite3.Connection:
        if not self._path.is_file():
            raise ValueError("operational journal is unavailable")
        connection = sqlite3.connect(self._path, isolation_level="DEFERRED")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection


def _event(row: sqlite3.Row) -> JournalEvent:
    return JournalEvent(
        event_id=int(row["event_id"]),
        publication_id=str(row["publication_id"]),
        generation=int(row["generation"]),
        event_kind=str(row["event_kind"]),
        selector=row["selector"],
        occurred_at=str(row["occurred_at"]),
        payload=dict(json.loads(row["payload_json"])),
    )


def _validate_payload(payload: dict[str, Any]) -> None:
    if not set(payload) <= _SAFE_PAYLOAD_KEYS:
        raise ValueError("journal payload contains private or unsupported fields")
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in payload.values()
    ):
        raise ValueError("journal payload counters must be nonnegative integers")


def _safe_identity(value: str) -> bool:
    return (
        1 <= len(value) <= 256
        and value == value.strip()
        and "\n" not in value
        and "\r" not in value
        and "\x00" not in value
        and "/Users/" not in value
    )
