"""Batch-safe cleanup helpers for replaced source logs."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path

from codex_usage_tracker.store.compression_fact_sync import (
    delete_compression_facts_for_source_files,
)
from codex_usage_tracker.store.content_index import (
    _clear_content_fts,
    _rebuild_content_fts,
    delete_content_index_rows_for_source_files,
)

_SOURCE_FILE_SQL_BATCH_SIZE = 400
OTEL_ENRICHMENT_COLUMNS = frozenset(
    {"service_tier", "fast", "service_tier_source", "service_tier_confidence"}
)
OtelEnrichment = tuple[object | None, object | None, object | None, object | None]


def source_file_strings(replace_source_files: Iterable[Path] | None) -> list[str]:
    return list(dict.fromkeys(str(path) for path in replace_source_files or []))


def delete_usage_events_for_source_files(
    conn: sqlite3.Connection,
    source_files_to_replace: list[str],
    *,
    sync_content_fts: bool = True,
) -> None:
    if not source_files_to_replace:
        return
    if sync_content_fts:
        _clear_content_fts(conn)
    for source_batch in _source_file_batches(source_files_to_replace):
        _delete_source_batch(conn, source_batch)
    if sync_content_fts:
        _rebuild_content_fts(conn)


def capture_otel_enrichment_for_source_files(
    conn: sqlite3.Connection,
    source_files_to_replace: list[str],
) -> dict[str, OtelEnrichment]:
    """Capture one internally consistent non-null tier tuple per affected group."""

    group_ids: set[str] = set()
    for source_batch in _source_file_batches(source_files_to_replace):
        placeholders = ", ".join("?" for _source in source_batch)
        rows = conn.execute(
            f"""
            SELECT DISTINCT coalesce(nullif(canonical_record_id, ''), record_id) AS group_id
            FROM usage_events
            WHERE source_file IN ({placeholders})
            """,  # nosec B608 - generated placeholders
            source_batch,
        ).fetchall()
        group_ids.update(str(row["group_id"]) for row in rows)

    tuples_by_group: dict[str, set[OtelEnrichment]] = {}
    for group_batch in _value_batches(sorted(group_ids)):
        placeholders = ", ".join("?" for _group in group_batch)
        rows = conn.execute(
            f"""
            SELECT coalesce(nullif(canonical_record_id, ''), record_id) AS group_id,
                   service_tier, fast, service_tier_source, service_tier_confidence
            FROM usage_events
            WHERE coalesce(nullif(canonical_record_id, ''), record_id) IN ({placeholders})
            """,  # nosec B608 - generated placeholders
            group_batch,
        ).fetchall()
        for row in rows:
            enrichment: OtelEnrichment = (
                row["service_tier"],
                row["fast"],
                row["service_tier_source"],
                row["service_tier_confidence"],
            )
            tuples_by_group.setdefault(str(row["group_id"]), set()).add(enrichment)

    captured: dict[str, OtelEnrichment] = {}
    for group_id, enrichments in tuples_by_group.items():
        if len(enrichments) != 1:
            continue
        enrichment = next(iter(enrichments))
        if any(value is not None for value in enrichment):
            captured[group_id] = enrichment
    return captured


def restore_otel_enrichment(
    conn: sqlite3.Connection,
    captured: Mapping[str, OtelEnrichment],
) -> None:
    """Restore captured tiers to reparsed clones without overwriting fresh values."""

    conn.executemany(
        """
        UPDATE usage_events
        SET service_tier = coalesce(service_tier, ?),
            fast = coalesce(fast, ?),
            service_tier_source = coalesce(service_tier_source, ?),
            service_tier_confidence = coalesce(service_tier_confidence, ?)
        WHERE coalesce(nullif(canonical_record_id, ''), record_id) = ?
        """,
        [(*enrichment, group_id) for group_id, enrichment in captured.items()],
    )


def thread_keys_for_source_files(
    conn: sqlite3.Connection,
    source_files_to_replace: list[str],
) -> set[str]:
    thread_keys: set[str] = set()
    for source_batch in _source_file_batches(source_files_to_replace):
        placeholders = ", ".join("?" for _source in source_batch)
        rows = conn.execute(
            f"""
            SELECT thread_key, session_id
            FROM usage_events
            WHERE source_file IN ({placeholders})
            """,  # nosec B608 - generated placeholders
            source_batch,
        ).fetchall()
        thread_keys.update(thread_keys_for_usage_rows(rows))
    return thread_keys


def thread_keys_for_usage_rows(
    rows: Iterable[Mapping[str, object] | sqlite3.Row],
) -> set[str]:
    keys: set[str] = set()
    for row in rows:
        session_id = _usage_row_value(row, "session_id")
        thread_key = _usage_row_value(row, "thread_key") or (
            f"session:{session_id}" if session_id else None
        )
        if thread_key:
            keys.add(str(thread_key))
    return keys


def _delete_source_batch(conn: sqlite3.Connection, source_batch: list[str]) -> None:
    placeholders = ", ".join("?" for _source in source_batch)
    delete_content_index_rows_for_source_files(
        conn,
        placeholders=placeholders,
        source_files_to_replace=source_batch,
        sync_fts=False,
    )
    delete_compression_facts_for_source_files(conn, source_files=source_batch)
    for table_name in (
        "allowance_observations",
        "source_records",
        "call_diagnostic_facts",
        "recommendation_facts",
    ):
        conn.execute(
            f"""
            DELETE FROM {table_name}
            WHERE record_id IN (
                SELECT record_id
                FROM usage_events
                WHERE source_file IN ({placeholders})
            )
            """,  # nosec B608 - fixed table names and generated placeholders
            source_batch,
        )
    conn.execute(
        f"DELETE FROM usage_events WHERE source_file IN ({placeholders})",  # nosec B608
        source_batch,
    )


def _source_file_batches(source_files: list[str]) -> Iterator[list[str]]:
    for start in range(0, len(source_files), _SOURCE_FILE_SQL_BATCH_SIZE):
        yield source_files[start : start + _SOURCE_FILE_SQL_BATCH_SIZE]


def _value_batches(values: list[str]) -> Iterator[list[str]]:
    for start in range(0, len(values), _SOURCE_FILE_SQL_BATCH_SIZE):
        yield values[start : start + _SOURCE_FILE_SQL_BATCH_SIZE]


def _usage_row_value(
    row: Mapping[str, object] | sqlite3.Row,
    key: str,
) -> object | None:
    if isinstance(row, sqlite3.Row):
        try:
            return row[key]
        except (IndexError, KeyError, TypeError):
            return None
    return row.get(key)
