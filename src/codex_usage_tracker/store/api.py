"""SQLite persistence and aggregate queries for Codex usage data."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.models import DiagnosticFact, RefreshResult, UsageEvent
from codex_usage_tracker.core.paths import DEFAULT_CODEX_HOME, DEFAULT_DB_PATH
from codex_usage_tracker.core.schema import (
    DIAGNOSTIC_FACT_COLUMN_NAMES,
    USAGE_EVENT_COLUMN_NAMES,
    USAGE_EVENT_SCHEMA_CHECKSUM,
)
from codex_usage_tracker.parser.state import (
    PARSER_ADAPTER_VERSION,
    PARSER_DIAGNOSTIC_KEYS,
)
from codex_usage_tracker.store.allowance_observations import (
    query_allowance_observations as query_allowance_observations,
)
from codex_usage_tracker.store.allowance_observations import (
    sync_allowance_observations_for_record_ids,
)
from codex_usage_tracker.store.compression_fact_sync import (
    clear_compression_detector_facts,
    sync_compression_detector_facts,
)
from codex_usage_tracker.store.compression_revisions import touch_compression_revisions
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.content_index import (
    clear_content_index_rows,
    search_content_fragments,
    trace_thread_content,
)
from codex_usage_tracker.store.content_patterns import query_local_pattern_scan
from codex_usage_tracker.store.dashboard_queries import (
    query_dashboard_event_count as query_dashboard_event_count,
)
from codex_usage_tracker.store.dashboard_queries import (
    query_dashboard_events as query_dashboard_events,
)
from codex_usage_tracker.store.dashboard_queries import (
    query_dashboard_token_summary as query_dashboard_token_summary,
)
from codex_usage_tracker.store.dashboard_queries import (
    query_latest_observed_usage as query_latest_observed_usage,
)
from codex_usage_tracker.store.dashboard_queries import (
    query_usage_status as query_usage_status,
)
from codex_usage_tracker.store.diagnostic_api import (
    query_large_low_output_calls as query_large_low_output_calls,
)
from codex_usage_tracker.store.diagnostic_api import (
    query_repeated_file_rediscovery as query_repeated_file_rediscovery,
)
from codex_usage_tracker.store.diagnostic_api import query_shell_churn as query_shell_churn
from codex_usage_tracker.store.diagnostic_call_queries import (
    query_diagnostic_fact_call_count as query_diagnostic_fact_call_count,
)
from codex_usage_tracker.store.diagnostic_call_queries import (
    query_diagnostic_fact_calls as query_diagnostic_fact_calls,
)
from codex_usage_tracker.store.diagnostic_queries import (
    query_diagnostic_facts as query_diagnostic_facts,
)
from codex_usage_tracker.store.diagnostic_queries import (
    query_diagnostic_summary as query_diagnostic_summary,
)
from codex_usage_tracker.store.exports import export_usage_csv as export_usage_csv
from codex_usage_tracker.store.investigation_runs import insert_investigation_run
from codex_usage_tracker.store.recommendation_schema import clear_recommendation_fact_tables
from codex_usage_tracker.store.refresh_callbacks import DerivedFactSyncCallback
from codex_usage_tracker.store.rows import (
    row_to_dict as _row_to_dict,
)
from codex_usage_tracker.store.schema import (
    SCHEMA_VERSION,
    SchemaMigrationError,
    init_db,
)
from codex_usage_tracker.store.deduplication import classify_usage_rows, promote_orphaned_fingerprints
from codex_usage_tracker.store.source_records import (
    query_source_record_coverage as query_source_record_coverage,
)
from codex_usage_tracker.store.source_records import (
    query_source_record_totals as query_source_record_totals,
)
from codex_usage_tracker.store.source_records import (
    query_source_records as query_source_records,
)
from codex_usage_tracker.store.source_records import (
    sync_source_records,
)
from codex_usage_tracker.store.source_replacement import (
    delete_usage_events_for_source_files as _delete_usage_events_for_source_files,
)
from codex_usage_tracker.store.source_replacement import (
    source_file_strings as _source_file_strings,
)
from codex_usage_tracker.store.source_replacement import (
    thread_keys_for_source_files as _thread_keys_for_source_files,
)
from codex_usage_tracker.store.source_replacement import (
    thread_keys_for_usage_rows as _thread_keys_for_usage_rows,
)
from codex_usage_tracker.store.sources import (
    ParsedSourceFile,
    upsert_source_file_metadata,
)
from codex_usage_tracker.store.summary_queries import query_summary as query_summary
from codex_usage_tracker.store.thread_summaries import (
    query_thread_summaries as query_thread_summaries,
)
from codex_usage_tracker.store.thread_summaries import rebuild_thread_summaries
from codex_usage_tracker.store.usage_api_queries import (
    query_usage_api_event_count as query_usage_api_event_count,
)
from codex_usage_tracker.store.usage_api_queries import (
    query_usage_api_events as query_usage_api_events,
)
from codex_usage_tracker.store.usage_record_queries import (
    query_most_expensive_calls as query_most_expensive_calls,
)
from codex_usage_tracker.store.usage_record_queries import (
    query_session_usage as query_session_usage,
)
from codex_usage_tracker.store.usage_record_queries import (
    query_usage_record as query_usage_record,
)

EVENT_COLUMNS = list(USAGE_EVENT_COLUMN_NAMES)
DIAGNOSTIC_FACT_COLUMNS = list(DIAGNOSTIC_FACT_COLUMN_NAMES)
__all__ = ["EVENT_COLUMNS", "SCHEMA_VERSION", "SchemaMigrationError", "init_db"]
SQLITE_VARIABLE_BATCH_SIZE = 500
RefreshProgressCallback = Callable[[dict[str, object]], None]


def refresh_usage_index(
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    aggregate_only: bool = False,
    progress_callback: RefreshProgressCallback | None = None,
    derived_fact_sync: DerivedFactSyncCallback | None = None,
) -> RefreshResult:
    """Scan Codex logs and upsert aggregate usage events."""

    from codex_usage_tracker.store.refresh import (
        refresh_usage_index as _refresh_usage_index,
    )

    return _refresh_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        include_archived=include_archived,
        aggregate_only=aggregate_only,
        progress_callback=progress_callback,
        derived_fact_sync=derived_fact_sync,
    )


def rebuild_usage_index(
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    aggregate_only: bool = False,
    derived_fact_sync: DerivedFactSyncCallback | None = None,
) -> RefreshResult:
    """Drop and rebuild the usage index from all selected Codex logs."""

    from codex_usage_tracker.store.refresh import (
        rebuild_usage_index as _rebuild_usage_index,
    )

    return _rebuild_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        include_archived=include_archived,
        aggregate_only=aggregate_only,
        derived_fact_sync=derived_fact_sync,
    )


def reset_usage_database(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Clear tracker-owned aggregate rows and refresh metadata."""

    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute("SELECT COUNT(*) AS count FROM usage_events").fetchone()
        deleted_rows = int(row["count"] if row is not None else 0)
        clear_content_index_rows(conn)
        clear_compression_detector_facts(conn)
        clear_recommendation_fact_tables(conn)
        conn.execute("DELETE FROM call_diagnostic_facts")
        conn.execute("DELETE FROM diagnostic_snapshots")
        conn.execute("DELETE FROM allowance_observations")
        conn.execute("DELETE FROM source_records")
        conn.execute("DELETE FROM usage_events")
        conn.execute("DELETE FROM thread_summaries")
        conn.execute("DELETE FROM source_files")
        conn.execute("DELETE FROM refresh_meta")
        touch_compression_revisions(conn)
    return {"db_path": str(db_path), "deleted_usage_events": deleted_rows}


def query_content_search(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    query: str,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    limit: int | None = 20,
    offset: int = 0,
    max_snippet_chars: int | None = 800,
) -> dict[str, Any]:
    """Search explicit local content index snippets."""

    with connect(db_path) as conn:
        init_db(conn)
        result = search_content_fragments(
            conn,
            query=query,
            since=since,
            until=until,
            model=model,
            effort=effort,
            thread=thread,
            include_archived=include_archived,
            limit=limit,
            offset=offset,
            max_snippet_chars=max_snippet_chars,
        )
    return {
        "rows": result.rows,
        "total_matched_rows": result.total_matched_rows,
        "search_mode": result.search_mode,
    }


def query_thread_trace(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    thread: str | None = None,
    thread_key: str | None = None,
    session_id: str | None = None,
    record_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    include_archived: bool = False,
    limit: int | None = 100,
    offset: int = 0,
    max_snippet_chars: int | None = 800,
) -> dict[str, Any]:
    """Return explicit local content-index trace for one thread/session."""

    with connect(db_path) as conn:
        init_db(conn)
        result = trace_thread_content(
            conn,
            thread=thread,
            thread_key=thread_key,
            session_id=session_id,
            record_id=record_id,
            since=since,
            until=until,
            include_archived=include_archived,
            limit=limit,
            offset=offset,
            max_snippet_chars=max_snippet_chars,
        )
    return {
        "calls": result.calls,
        "total_matched_calls": result.total_matched_calls,
    }


def query_pattern_scan(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    scan_type: str = "all",
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    limit: int | None = 20,
) -> dict[str, Any]:
    """Return local content/event-index pattern scan rows."""

    with connect(db_path) as conn:
        init_db(conn)
        return query_local_pattern_scan(
            conn,
            scan_type=scan_type,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            min_occurrences=min_occurrences,
            limit=limit,
        )


def record_investigation_run(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    run_kind: str,
    payload: dict[str, Any],
) -> str:
    """Persist bounded investigation run metadata."""

    with connect(db_path) as conn:
        init_db(conn)
        return insert_investigation_run(conn, run_kind=run_kind, payload=payload)


def record_refresh_metadata(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    scanned_files: int,
    parsed_events: int,
    skipped_events: int,
    inserted_or_updated_events: int,
    parser_diagnostics: dict[str, int] | None = None,
    parsed_source_files: int | None = None,
    skipped_source_files: int | None = None,
) -> None:
    """Record the latest refresh counters in refresh_meta."""

    values = {
        "latest_refresh_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "scanned_files": str(scanned_files),
        "parsed_events": str(parsed_events),
        "skipped_events": str(skipped_events),
        "inserted_or_updated_events": str(inserted_or_updated_events),
        "parser_adapter": PARSER_ADAPTER_VERSION,
        "schema_version": str(SCHEMA_VERSION),
        "usage_events_schema_checksum": USAGE_EVENT_SCHEMA_CHECKSUM,
    }
    if parsed_source_files is not None:
        values["parsed_source_files"] = str(parsed_source_files)
    if skipped_source_files is not None:
        values["skipped_source_files"] = str(skipped_source_files)
    diagnostics = parser_diagnostics or {}
    for key in PARSER_DIAGNOSTIC_KEYS:
        values[f"parser_{key}"] = str(int(diagnostics.get(key, 0)))
    with connect(db_path) as conn:
        init_db(conn)
        conn.executemany(
            """
            INSERT INTO refresh_meta (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            values.items(),
        )


def refresh_metadata(db_path: Path = DEFAULT_DB_PATH) -> dict[str, str]:
    """Return latest refresh metadata and parser diagnostics."""

    if not db_path.exists():
        return {}
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute("SELECT key, value FROM refresh_meta").fetchall()
    return {str(row["key"]): str(row["value"]) for row in rows}


def upsert_diagnostic_snapshot(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    section: str,
    history_scope: str,
    payload: dict[str, Any],
    computed_at: str,
    source_logs_scanned: int,
    usage_rows_scanned: int,
    raw_content_included: bool = False,
) -> None:
    """Persist one aggregate diagnostic report snapshot."""

    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    with connect(db_path) as conn:
        init_db(conn)
        conn.execute(
            """
            INSERT INTO diagnostic_snapshots (
                section,
                history_scope,
                payload_json,
                computed_at,
                source_logs_scanned,
                usage_rows_scanned,
                raw_content_included
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(section, history_scope) DO UPDATE SET
                payload_json = excluded.payload_json,
                computed_at = excluded.computed_at,
                source_logs_scanned = excluded.source_logs_scanned,
                usage_rows_scanned = excluded.usage_rows_scanned,
                raw_content_included = excluded.raw_content_included
            """,
            (
                section,
                history_scope,
                payload_json,
                computed_at,
                int(source_logs_scanned),
                int(usage_rows_scanned),
                1 if raw_content_included else 0,
            ),
        )


def query_diagnostic_snapshot(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    section: str,
    history_scope: str,
) -> dict[str, Any] | None:
    """Return one persisted aggregate diagnostic report snapshot."""

    if not db_path.exists():
        return None
    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute(
            """
            SELECT
                section,
                history_scope,
                payload_json,
                computed_at,
                source_logs_scanned,
                usage_rows_scanned,
                raw_content_included
            FROM diagnostic_snapshots
            WHERE section = ? AND history_scope = ?
            """,
            (section, history_scope),
        ).fetchone()
    if row is None:
        return None
    payload = json.loads(str(row["payload_json"]))
    return {
        "section": str(row["section"]),
        "history_scope": str(row["history_scope"]),
        "payload": payload if isinstance(payload, dict) else {},
        "computed_at": str(row["computed_at"]),
        "source_logs_scanned": int(row["source_logs_scanned"]),
        "usage_rows_scanned": int(row["usage_rows_scanned"]),
        "raw_content_included": bool(row["raw_content_included"]),
    }


def schema_state(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Return database migration and usage_events checksum state."""

    if not db_path.exists():
        return {
            "exists": False,
            "schema_version": None,
            "expected_schema_version": SCHEMA_VERSION,
            "expected_checksum": USAGE_EVENT_SCHEMA_CHECKSUM,
            "migrations": [],
            "checksum_matches": False,
        }
    with connect(db_path) as conn:
        init_db(conn)
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        rows = conn.execute(
            """
            SELECT version, name, checksum, applied_at
            FROM schema_migrations
            ORDER BY version
            """
        ).fetchall()
    migrations = [_row_to_dict(row) for row in rows]
    latest_checksum = migrations[-1]["checksum"] if migrations else None
    return {
        "exists": True,
        "schema_version": version,
        "expected_schema_version": SCHEMA_VERSION,
        "expected_checksum": USAGE_EVENT_SCHEMA_CHECKSUM,
        "latest_checksum": latest_checksum,
        "checksum_matches": latest_checksum == USAGE_EVENT_SCHEMA_CHECKSUM,
        "migrations": migrations,
    }


def record_source_file_metadata(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    parsed_files: Iterable[ParsedSourceFile],
) -> None:
    """Record metadata for source files parsed during refresh."""

    parsed = list(parsed_files)
    if not parsed:
        return
    with connect(db_path) as conn:
        init_db(conn)
        upsert_source_file_metadata(conn, parsed_files=parsed)
        record_ids = [event.record_id for _path, events, *_rest in parsed for event in events]
        if record_ids:
            sync_source_records(conn, record_ids=record_ids)


def upsert_usage_events(
    events: Iterable[UsageEvent],
    db_path: Path = DEFAULT_DB_PATH,
    *,
    refresh_links: bool = True,
    replace_source_files: Iterable[Path] | None = None,
    diagnostic_facts: Iterable[DiagnosticFact] | None = None,
) -> int:
    with connect(db_path) as conn:
        init_db(conn)
        result = _upsert_usage_events_in_connection(
            conn,
            events,
            refresh_links=refresh_links,
            replace_source_files=replace_source_files,
            diagnostic_facts=diagnostic_facts,
        )
    return result.inserted_or_updated_events


@dataclass(frozen=True)
class _UsageEventUpsertResult:
    inserted_or_updated_events: int
    record_ids: tuple[str, ...]
    affected_thread_keys: frozenset[str]


def _upsert_usage_events_in_connection(
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
) -> _UsageEventUpsertResult:
    rows = _usage_event_rows(events)
    fact_rows = _diagnostic_fact_rows(diagnostic_facts)
    source_files_to_replace = _source_file_strings(replace_source_files)
    affected_thread_keys = _thread_keys_for_source_files(conn, source_files_to_replace)
    replaced_fingerprints = _fingerprints_for_source_files(conn, source_files_to_replace)
    _delete_usage_events_for_source_files(
        conn,
        source_files_to_replace,
        sync_content_fts=sync_content_fts_on_replace,
    )
    affected_thread_keys.update(promote_orphaned_fingerprints(conn, replaced_fingerprints))
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
                    record_ids=(),
                    affected_thread_keys=affected_thread_keys,
                )
        return _UsageEventUpsertResult(0, (), frozenset(affected_thread_keys))

    affected_thread_keys.update(_thread_keys_for_usage_rows(rows))
    record_ids = _usage_event_record_ids(rows)
    _delete_diagnostic_facts_for_record_ids(conn, record_ids)
    with _deferred_usage_event_indexes(conn, enabled=defer_usage_indexes):
        _insert_usage_event_rows(conn, rows)
    if maintain_allowance_observations:
        sync_allowance_observations_for_record_ids(conn, record_ids)
    if maintain_source_records:
        sync_source_records(conn, record_ids=record_ids)
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
    return _UsageEventUpsertResult(
        len(rows),
        tuple(record_ids),
        frozenset(affected_thread_keys),
    )


def _finalize_streamed_usage_event_upserts(
    conn: sqlite3.Connection,
    *,
    record_ids: Iterable[str],
    affected_thread_keys: Iterable[str],
    maintain_source_records: bool = True,
    stage_callback: Callable[[str], None] | None = None,
) -> _UsageEventUpsertResult:
    """Finalize derived state once after bounded source-batch upserts."""

    unique_record_ids = tuple(dict.fromkeys(record_ids))
    unique_thread_keys = frozenset(affected_thread_keys)
    if unique_record_ids:
        sync_allowance_observations_for_record_ids(conn, list(unique_record_ids))
        if maintain_source_records:
            sync_source_records(conn, record_ids=unique_record_ids)
    if stage_callback is not None:
        stage_callback("allowance_and_sources")
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
    return _UsageEventUpsertResult(
        len(unique_record_ids),
        unique_record_ids,
        unique_thread_keys,
    )


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


def _fingerprints_for_source_files(conn: sqlite3.Connection, source_files: list[str]) -> set[str]:
    if not source_files:
        return set()
    placeholders = ", ".join("?" for _ in source_files)
    return {str(row[0]) for row in conn.execute(f"SELECT DISTINCT usage_fingerprint FROM usage_events WHERE source_file IN ({placeholders}) AND usage_fingerprint IS NOT NULL", source_files)}


def _usage_event_upsert_sql() -> str:
    placeholders = ", ".join("?" for _column in EVENT_COLUMNS)
    update_clause = ", ".join(
        f"{column}=excluded.{column}" for column in EVENT_COLUMNS if column != "record_id"
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


@contextmanager
def _deferred_usage_event_indexes(
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


def refresh_usage_event_links(db_path: Path = DEFAULT_DB_PATH) -> int:
    """Recompute per-thread chronological adjacency for aggregate usage rows."""

    with connect(db_path) as conn:
        init_db(conn)
        changed = _refresh_usage_event_links(conn)
        rebuild_thread_summaries(conn)
        return changed


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


def _refresh_usage_event_links(conn: sqlite3.Connection) -> int:
    return _refresh_usage_event_links_scoped(conn)


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


def refresh_thread_summaries(db_path: Path = DEFAULT_DB_PATH) -> int:
    """Rebuild materialized per-thread aggregate summaries."""

    with connect(db_path) as conn:
        init_db(conn)
        return rebuild_thread_summaries(conn)
