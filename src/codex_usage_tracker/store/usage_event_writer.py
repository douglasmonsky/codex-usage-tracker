"""Lower-level SQLite write kernel for usage events and derived links."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from codex_usage_tracker.core.models import DiagnosticFact, UsageEvent
from codex_usage_tracker.core.schema import (
    DIAGNOSTIC_FACT_COLUMN_NAMES,
    USAGE_EVENT_COLUMN_NAMES,
)
from codex_usage_tracker.store.allowance_observations import (
    sync_allowance_observations_for_record_ids,
)
from codex_usage_tracker.store.compression_fact_sync import sync_compression_detector_facts
from codex_usage_tracker.store.compression_revision_state import touch_compression_revisions
from codex_usage_tracker.store.deduplication import (
    classify_usage_rows,
    fingerprints_for_source_files,
    promote_orphaned_fingerprints,
)
from codex_usage_tracker.store.source_records import sync_source_records
from codex_usage_tracker.store.source_replacement import (
    OTEL_ENRICHMENT_COLUMNS,
    capture_otel_enrichment_for_source_files,
    delete_usage_events_for_source_files,
    restore_otel_enrichment,
    source_file_strings,
    thread_keys_for_source_files,
    thread_keys_for_usage_rows,
)
from codex_usage_tracker.store.thread_summaries import rebuild_thread_summaries

EVENT_COLUMNS = list(USAGE_EVENT_COLUMN_NAMES)
DIAGNOSTIC_FACT_COLUMNS = list(DIAGNOSTIC_FACT_COLUMN_NAMES)
SQLITE_VARIABLE_BATCH_SIZE = 500


@dataclass(frozen=True)
class UsageEventUpsertResult:
    inserted_or_updated_events: int
    record_ids: tuple[str, ...]
    affected_thread_keys: frozenset[str]


def upsert_usage_events_in_connection(
    conn: sqlite3.Connection,
    events: Iterable[UsageEvent],
    *,
    refresh_links: bool = True,
    replace_source_files: Iterable[Path] | None = None,
    diagnostic_facts: Iterable[DiagnosticFact] | None = None,
    maintain_source_records: bool = True,
    maintain_compression_facts: bool = True,
    maintain_allowance_observations: bool = True,
    touch_revisions: bool = True,
    sync_content_fts_on_replace: bool = True,
    defer_usage_indexes: bool = False,
) -> UsageEventUpsertResult:
    rows = _usage_event_rows(events)
    fact_rows = _diagnostic_fact_rows(diagnostic_facts)
    source_files_to_replace = source_file_strings(replace_source_files)
    affected_thread_keys = thread_keys_for_source_files(conn, source_files_to_replace)
    replaced_fingerprints = fingerprints_for_source_files(conn, source_files_to_replace)
    preserved_otel_enrichment = capture_otel_enrichment_for_source_files(
        conn, source_files_to_replace
    )
    delete_usage_events_for_source_files(
        conn,
        source_files_to_replace,
        sync_content_fts=sync_content_fts_on_replace,
    )
    promotion = promote_orphaned_fingerprints(conn, replaced_fingerprints)
    promoted_record_ids, promoted_thread_keys = promotion
    affected_thread_keys.update(promoted_thread_keys)
    if not rows:
        _refresh_after_empty_source_replacement(
            conn,
            refresh_links=refresh_links,
            affected_thread_keys=affected_thread_keys,
        )
        if source_files_to_replace:
            if touch_revisions:
                touch_compression_revisions(conn, {"calls", "threads"})
            if maintain_compression_facts:
                sync_compression_detector_facts(
                    conn,
                    record_ids=promoted_record_ids,
                    affected_thread_keys=affected_thread_keys,
                )
        promoted_ids = tuple(sorted(promoted_record_ids))
        return UsageEventUpsertResult(0, promoted_ids, frozenset(affected_thread_keys))

    affected_thread_keys.update(thread_keys_for_usage_rows(rows))
    inserted_record_ids = _usage_event_record_ids(rows)
    record_ids = list(dict.fromkeys([*promoted_record_ids, *inserted_record_ids]))
    _delete_diagnostic_facts_for_record_ids(conn, inserted_record_ids)
    with deferred_usage_event_indexes(conn, enabled=defer_usage_indexes):
        _insert_usage_event_rows(conn, rows)
    restore_otel_enrichment(conn, preserved_otel_enrichment)
    if maintain_allowance_observations:
        sync_allowance_observations_for_record_ids(conn, record_ids)
    if maintain_source_records:
        sync_source_records(conn, record_ids=inserted_record_ids)
    _insert_diagnostic_facts(conn, fact_rows)
    _refresh_after_usage_event_upsert(
        conn,
        refresh_links=refresh_links,
        affected_thread_keys=affected_thread_keys,
    )
    if touch_revisions:
        touch_compression_revisions(conn, {"calls", "threads"})
    if maintain_compression_facts:
        sync_compression_detector_facts(
            conn,
            record_ids=record_ids,
            affected_thread_keys=affected_thread_keys,
        )
    return UsageEventUpsertResult(
        len(rows),
        tuple(record_ids),
        frozenset(affected_thread_keys),
    )


def finalize_streamed_usage_event_upserts(
    conn: sqlite3.Connection,
    *,
    record_ids: Iterable[str],
    affected_thread_keys: Iterable[str],
    maintain_source_records: bool = True,
    stage_callback: Callable[[str], None] | None = None,
) -> UsageEventUpsertResult:
    """Finalize derived state once after bounded source-batch upserts."""

    unique_record_ids = tuple(dict.fromkeys(record_ids))
    unique_thread_keys = frozenset(affected_thread_keys)
    if unique_record_ids:
        sync_allowance_observations_for_record_ids(conn, list(unique_record_ids))
        if maintain_source_records:
            sync_source_records(conn, record_ids=unique_record_ids)
    if stage_callback is not None:
        stage_callback("sources")
    _refresh_after_usage_event_upsert(
        conn,
        refresh_links=True,
        affected_thread_keys=set(unique_thread_keys),
    )
    if stage_callback is not None:
        stage_callback("links_and_thread_summaries")
    if unique_record_ids or unique_thread_keys:
        touch_compression_revisions(conn, {"calls", "threads"})
    if stage_callback is not None:
        stage_callback("revisions")
    return UsageEventUpsertResult(
        len(unique_record_ids),
        unique_record_ids,
        unique_thread_keys,
    )


@contextmanager
def deferred_usage_event_indexes(
    conn: sqlite3.Connection,
    *,
    enabled: bool,
    additional_tables: tuple[str, ...] = (),
) -> Iterator[None]:
    if not enabled:
        yield
        return
    table_names = ("usage_events", *additional_tables)
    placeholders = ", ".join("?" for _table_name in table_names)
    indexes = [
        (str(row["name"]), str(row["sql"]))
        for row in conn.execute(
            f"""
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'index'
              AND tbl_name IN ({placeholders})
              AND sql IS NOT NULL
            ORDER BY name
            """,  # nosec B608 - placeholders are generated, values remain parameterized
            table_names,
        )
    ]
    for name, _sql in indexes:
        quoted_name = name.replace('"', '""')
        conn.execute(f'DROP INDEX "{quoted_name}"')  # nosec B608 - schema-owned identifier
    try:
        yield
    finally:
        for _name, sql in indexes:
            conn.execute(sql)


def refresh_usage_event_links(conn: sqlite3.Connection) -> int:
    return _refresh_usage_event_links_scoped(conn)


def _usage_event_rows(events: Iterable[UsageEvent]) -> list[dict[str, object]]:
    return [event.to_row() for event in events]


def _diagnostic_fact_rows(
    diagnostic_facts: Iterable[DiagnosticFact] | None,
) -> list[dict[str, object]]:
    return [fact.to_row() for fact in diagnostic_facts or []]


def _refresh_after_empty_source_replacement(
    conn: sqlite3.Connection,
    *,
    refresh_links: bool,
    affected_thread_keys: set[str],
) -> None:
    if affected_thread_keys and refresh_links:
        _refresh_usage_event_links_for_threads(conn, affected_thread_keys)
        rebuild_thread_summaries(conn, thread_keys=affected_thread_keys)


def _usage_event_record_ids(rows: list[dict[str, object]]) -> list[str]:
    return [str(row["record_id"]) for row in rows]


def _usage_event_upsert_sql() -> str:
    placeholders = ", ".join("?" for _column in EVENT_COLUMNS)
    update_clause = ", ".join(
        f"{column}=COALESCE(usage_events.{column}, excluded.{column})"
        if column in OTEL_ENRICHMENT_COLUMNS
        else f"{column}=excluded.{column}"
        for column in EVENT_COLUMNS
        if column != "record_id"
    )
    return (
        f"INSERT INTO usage_events ({', '.join(EVENT_COLUMNS)}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT(record_id) DO UPDATE SET {update_clause}"
    )


def _insert_usage_event_rows(
    conn: sqlite3.Connection,
    rows: list[dict[str, object]],
) -> None:
    rows = classify_usage_rows(conn, rows)
    conn.executemany(
        _usage_event_upsert_sql(),
        [[row[column] for column in EVENT_COLUMNS] for row in rows],
    )


def _refresh_after_usage_event_upsert(
    conn: sqlite3.Connection,
    *,
    refresh_links: bool,
    affected_thread_keys: set[str],
) -> None:
    if refresh_links and affected_thread_keys:
        _refresh_usage_event_links_for_threads(conn, affected_thread_keys)
        rebuild_thread_summaries(conn, thread_keys=affected_thread_keys)


def _delete_diagnostic_facts_for_record_ids(
    conn: sqlite3.Connection,
    record_ids: list[str],
) -> None:
    if not record_ids:
        return
    unique_record_ids = list(dict.fromkeys(record_ids))
    for start in range(0, len(unique_record_ids), SQLITE_VARIABLE_BATCH_SIZE):
        chunk = unique_record_ids[start : start + SQLITE_VARIABLE_BATCH_SIZE]
        placeholders = ", ".join("?" for _record_id in chunk)
        conn.execute(
            f"DELETE FROM call_diagnostic_facts WHERE record_id IN ({placeholders})",
            chunk,
        )


def _insert_diagnostic_facts(
    conn: sqlite3.Connection,
    rows: list[dict[str, object]],
) -> None:
    if not rows:
        return
    placeholders = ", ".join("?" for _column in DIAGNOSTIC_FACT_COLUMNS)
    update_clause = ", ".join(
        f"{column}=excluded.{column}"
        for column in DIAGNOSTIC_FACT_COLUMNS
        if column not in {"record_id", "fact_type", "fact_name"}
    )
    sql = (
        f"INSERT INTO call_diagnostic_facts ({', '.join(DIAGNOSTIC_FACT_COLUMNS)}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT(record_id, fact_type, fact_name) DO UPDATE SET {update_clause}"
    )
    conn.executemany(
        sql,
        [[row[column] for column in DIAGNOSTIC_FACT_COLUMNS] for row in rows],
    )


def _refresh_usage_event_links_for_threads(
    conn: sqlite3.Connection,
    affected_thread_keys: Iterable[str],
) -> int:
    thread_keys = sorted({key for key in affected_thread_keys if key})
    if not thread_keys:
        return 0
    changed = 0
    for start in range(0, len(thread_keys), SQLITE_VARIABLE_BATCH_SIZE):
        chunk = thread_keys[start : start + SQLITE_VARIABLE_BATCH_SIZE]
        placeholders = ", ".join("?" for _key in chunk)
        changed += _refresh_usage_event_links_scoped(
            conn,
            where_clause=(
                "WHERE coalesce(nullif(thread_key, ''), 'session:' || session_id) "
                f"IN ({placeholders})"
            ),
            params=chunk,
        )
    return changed


def _refresh_usage_event_links_scoped(
    conn: sqlite3.Connection,
    *,
    where_clause: str = "",
    params: Iterable[object] = (),
) -> int:
    before = conn.total_changes
    conn.execute(
        f"""
        WITH usage_event_links AS (
            SELECT
                record_id,
                ROW_NUMBER() OVER (
                    PARTITION BY coalesce(nullif(thread_key, ''), 'session:' || session_id)
                    ORDER BY event_timestamp, cumulative_total_tokens, line_number, record_id
                ) AS next_thread_call_index,
                LAG(record_id) OVER (
                    PARTITION BY coalesce(nullif(thread_key, ''), 'session:' || session_id)
                    ORDER BY event_timestamp, cumulative_total_tokens, line_number, record_id
                ) AS previous_id,
                LEAD(record_id) OVER (
                    PARTITION BY coalesce(nullif(thread_key, ''), 'session:' || session_id)
                    ORDER BY event_timestamp, cumulative_total_tokens, line_number, record_id
                ) AS next_id
            FROM usage_events
            {where_clause}
        )
        UPDATE usage_events AS target
        SET
            thread_call_index = links.next_thread_call_index,
            previous_record_id = links.previous_id,
            next_record_id = links.next_id
        FROM usage_event_links AS links
        WHERE target.record_id = links.record_id
        """,
        list(params),
    )
    return conn.total_changes - before
