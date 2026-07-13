"""Persist detector-ready compression facts during bounded ingestion."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable

from codex_usage_tracker.core.models import UsageEvent
from codex_usage_tracker.store.compression_fact_contract import COMPRESSION_FACTS_VERSION
from codex_usage_tracker.store.compression_fact_rows import (
    RECORD_FACT_COLUMNS,
    SEQUENCE_FACT_COLUMNS,
    IngestionFactRows,
    build_ingestion_fact_rows,
    source_order_group,
)
from codex_usage_tracker.store.compression_facts import (
    _insert_thread_facts,
    _update_thread_manifests,
)
from codex_usage_tracker.store.compression_schema import (
    create_compression_fact_indexes,
    drop_compression_fact_indexes,
    stamp_compression_fact_state,
)
from codex_usage_tracker.store.content_index_models import _ExtractedContentRows


class IngestionFactWriter:
    """Persist full-build facts without rescanning normalized SQLite tables."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._source_orders = {"tool": 0, "command": 0, "file": 0, "fragment": 0}
        drop_compression_fact_indexes(conn)
        conn.execute("DELETE FROM compression_sequence_facts")
        conn.execute("DELETE FROM compression_thread_facts")
        conn.execute("DELETE FROM compression_record_facts")

    def add(
        self,
        *,
        events: Iterable[UsageEvent],
        content_rows: Iterable[_ExtractedContentRows],
    ) -> None:
        self.add_prebuilt(build_ingestion_fact_rows(events=events, content_rows=content_rows))

    def add_prebuilt(self, rows: IngestionFactRows) -> None:
        """Persist worker-built rows after rebasing their local source order."""

        for row in rows.sequence_rows:
            group = source_order_group(str(row[5]))
            row[4] = int(str(row[4])) + self._source_orders[group]
        for group, count in rows.source_order_counts.items():
            self._source_orders[group] += count
        _insert_rows(
            self._conn,
            "compression_record_facts",
            RECORD_FACT_COLUMNS,
            rows.record_rows,
        )
        _insert_rows(
            self._conn,
            "compression_sequence_facts",
            SEQUENCE_FACT_COLUMNS,
            rows.sequence_rows,
        )

    def finish(self, *, stage_callback: Callable[[str], None] | None = None) -> None:
        _sync_record_links(self._conn)
        if stage_callback is not None:
            stage_callback("record_links")
        _insert_thread_facts(self._conn)
        if stage_callback is not None:
            stage_callback("thread_facts")
        _update_thread_manifests(self._conn)
        if stage_callback is not None:
            stage_callback("thread_manifests")
        create_compression_fact_indexes(self._conn)
        if stage_callback is not None:
            stage_callback("indexes")
        stamp_compression_fact_state(self._conn, facts_version=COMPRESSION_FACTS_VERSION)
        if stage_callback is not None:
            stage_callback("state")


def _sync_record_links(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE compression_record_facts AS facts
        SET
            thread_call_index = usage.thread_call_index,
            previous_record_id = usage.previous_record_id
        FROM usage_events AS usage
        WHERE facts.record_id = usage.record_id
        """
    )


def _insert_rows(
    conn: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
    rows: list[list[object]],
) -> None:
    if not rows:
        return
    placeholders = ", ".join("?" for _column in columns)
    conn.executemany(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",  # nosec B608
        rows,
    )
