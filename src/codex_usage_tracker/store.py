"""SQLite persistence and aggregate queries for Codex usage data."""

from __future__ import annotations

import csv
import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.models import DiagnosticFact, RefreshResult, UsageEvent
from codex_usage_tracker.parser import (
    PARSER_ADAPTER_VERSION,
    PARSER_DIAGNOSTIC_KEYS,
    compact_parser_diagnostics,
    find_session_logs,
    load_session_index,
    parse_usage_events_from_file_with_state,
)
from codex_usage_tracker.paths import DEFAULT_CODEX_HOME, DEFAULT_DB_PATH
from codex_usage_tracker.projects import apply_project_privacy_to_rows, validate_privacy_mode
from codex_usage_tracker.schema import (
    DIAGNOSTIC_FACT_COLUMN_NAMES,
    USAGE_EVENT_COLUMN_NAMES,
    USAGE_EVENT_SCHEMA_CHECKSUM,
)
from codex_usage_tracker.store_connection import connect
from codex_usage_tracker.store_dashboard_queries import (
    query_dashboard_event_count as query_dashboard_event_count,
)
from codex_usage_tracker.store_dashboard_queries import (
    query_dashboard_events as query_dashboard_events,
)
from codex_usage_tracker.store_dashboard_queries import (
    query_dashboard_token_summary as query_dashboard_token_summary,
)
from codex_usage_tracker.store_dashboard_queries import (
    query_latest_observed_usage as query_latest_observed_usage,
)
from codex_usage_tracker.store_dashboard_queries import (
    query_usage_status as query_usage_status,
)
from codex_usage_tracker.store_diagnostic_call_queries import (
    query_diagnostic_fact_call_count as query_diagnostic_fact_call_count,
)
from codex_usage_tracker.store_diagnostic_call_queries import (
    query_diagnostic_fact_calls as query_diagnostic_fact_calls,
)
from codex_usage_tracker.store_diagnostic_queries import (
    query_diagnostic_facts as query_diagnostic_facts,
)
from codex_usage_tracker.store_diagnostic_queries import (
    query_diagnostic_summary as query_diagnostic_summary,
)
from codex_usage_tracker.store_query_sql import (
    _normalize_limit,
)
from codex_usage_tracker.store_rows import (
    row_to_dict as _row_to_dict,
)
from codex_usage_tracker.store_schema import (
    SCHEMA_VERSION,
    SchemaMigrationError,
    init_db,
)
from codex_usage_tracker.store_sources import (
    ParsedSourceFile,
    source_logs_requiring_parse,
    upsert_source_file_metadata,
)
from codex_usage_tracker.store_summary_queries import query_summary as query_summary
from codex_usage_tracker.store_thread_summaries import (
    query_thread_summaries as query_thread_summaries,
)
from codex_usage_tracker.store_thread_summaries import rebuild_thread_summaries
from codex_usage_tracker.store_usage_api_queries import (
    query_usage_api_event_count as query_usage_api_event_count,
)
from codex_usage_tracker.store_usage_api_queries import (
    query_usage_api_events as query_usage_api_events,
)
from codex_usage_tracker.store_usage_record_queries import (
    query_most_expensive_calls as query_most_expensive_calls,
)
from codex_usage_tracker.store_usage_record_queries import (
    query_session_usage as query_session_usage,
)
from codex_usage_tracker.store_usage_record_queries import (
    query_usage_record as query_usage_record,
)

EVENT_COLUMNS = list(USAGE_EVENT_COLUMN_NAMES)
DIAGNOSTIC_FACT_COLUMNS = list(DIAGNOSTIC_FACT_COLUMN_NAMES)
__all__ = ["EVENT_COLUMNS", "SCHEMA_VERSION", "SchemaMigrationError", "init_db"]
SQLITE_VARIABLE_BATCH_SIZE = 500
def refresh_usage_index(
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
) -> RefreshResult:
    """Scan Codex logs and upsert aggregate usage events."""

    logs = find_session_logs(codex_home=codex_home, include_archived=include_archived)
    session_index = load_session_index(codex_home)
    with connect(db_path) as conn:
        init_db(conn)
        parse_plans = source_logs_requiring_parse(conn, logs)
    stats: dict[str, int] = {}
    events: list[UsageEvent] = []
    diagnostic_facts: list[DiagnosticFact] = []
    parsed_files: list[ParsedSourceFile] = []
    for plan in parse_plans:
        file_stats: dict[str, int] = {}
        parsed_file = parse_usage_events_from_file_with_state(
            plan.path,
            session_index=session_index,
            stats=file_stats,
            start_byte=plan.start_byte,
            start_line=plan.start_line,
            initial_state=plan.initial_state,
        )
        file_events = parsed_file.events
        events.extend(file_events)
        diagnostic_facts.extend(parsed_file.diagnostic_facts)
        parsed_files.append((plan.path, file_events, file_stats, parsed_file.state))
        for key, value in file_stats.items():
            stats[key] = stats.get(key, 0) + int(value)
    inserted = upsert_usage_events(
        events,
        db_path=db_path,
        replace_source_files=(plan.path for plan in parse_plans if plan.replace_existing),
        diagnostic_facts=diagnostic_facts,
    )
    record_source_file_metadata(db_path=db_path, parsed_files=parsed_files)
    skipped_events = stats.get("skipped_events", 0)
    diagnostics = compact_parser_diagnostics(stats)
    record_refresh_metadata(
        db_path=db_path,
        scanned_files=len(logs),
        parsed_events=len(events),
        skipped_events=skipped_events,
        inserted_or_updated_events=inserted,
        parser_diagnostics=diagnostics,
        parsed_source_files=len(parse_plans),
        skipped_source_files=len(logs) - len(parse_plans),
    )
    return RefreshResult(
        scanned_files=len(logs),
        parsed_events=len(events),
        inserted_or_updated_events=inserted,
        db_path=str(db_path),
        skipped_events=skipped_events,
        parser_diagnostics=diagnostics,
    )


def rebuild_usage_index(
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
) -> RefreshResult:
    """Clear aggregate rows and rescan local Codex logs."""

    with connect(db_path) as conn:
        init_db(conn)
        conn.execute("DELETE FROM call_diagnostic_facts")
        conn.execute("DELETE FROM diagnostic_snapshots")
        conn.execute("DELETE FROM usage_events")
        conn.execute("DELETE FROM thread_summaries")
        conn.execute("DELETE FROM source_files")
        conn.execute("DELETE FROM refresh_meta")
    return refresh_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        include_archived=include_archived,
    )


def reset_usage_database(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Clear tracker-owned aggregate rows and refresh metadata."""

    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute("SELECT COUNT(*) AS count FROM usage_events").fetchone()
        deleted_rows = int(row["count"] if row is not None else 0)
        conn.execute("DELETE FROM call_diagnostic_facts")
        conn.execute("DELETE FROM diagnostic_snapshots")
        conn.execute("DELETE FROM usage_events")
        conn.execute("DELETE FROM thread_summaries")
        conn.execute("DELETE FROM source_files")
        conn.execute("DELETE FROM refresh_meta")
    return {"db_path": str(db_path), "deleted_usage_events": deleted_rows}




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


def upsert_usage_events(
    events: Iterable[UsageEvent],
    db_path: Path = DEFAULT_DB_PATH,
    *,
    refresh_links: bool = True,
    replace_source_files: Iterable[Path] | None = None,
    diagnostic_facts: Iterable[DiagnosticFact] | None = None,
) -> int:
    rows = [event.to_row() for event in events]
    fact_rows = [fact.to_row() for fact in diagnostic_facts or []]
    source_files_to_replace = [str(path) for path in replace_source_files or []]
    with connect(db_path) as conn:
        init_db(conn)
        if source_files_to_replace:
            placeholders = ", ".join("?" for _source in source_files_to_replace)
            conn.execute(
                f"""
                DELETE FROM call_diagnostic_facts
                WHERE record_id IN (
                    SELECT record_id
                    FROM usage_events
                    WHERE source_file IN ({placeholders})
                )
                """,
                source_files_to_replace,
            )
            conn.execute(
                f"DELETE FROM usage_events WHERE source_file IN ({placeholders})",
                source_files_to_replace,
            )
        if not rows:
            if source_files_to_replace and refresh_links:
                _refresh_usage_event_links(conn)
                rebuild_thread_summaries(conn)
            return 0
        placeholders = ", ".join("?" for _ in EVENT_COLUMNS)
        update_clause = ", ".join(
            f"{column}=excluded.{column}"
            for column in EVENT_COLUMNS
            if column != "record_id"
        )
        sql = (
            f"INSERT INTO usage_events ({', '.join(EVENT_COLUMNS)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT(record_id) DO UPDATE SET {update_clause}"
        )
        _delete_diagnostic_facts_for_record_ids(
            conn,
            [str(row["record_id"]) for row in rows],
        )
        conn.executemany(sql, [[row[column] for column in EVENT_COLUMNS] for row in rows])
        _insert_diagnostic_facts(conn, fact_rows)
        if refresh_links:
            _refresh_usage_event_links(conn)
            rebuild_thread_summaries(conn)
        return len(rows)


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


def _refresh_usage_event_links(conn: sqlite3.Connection) -> int:
    before = conn.total_changes
    conn.execute("DROP TABLE IF EXISTS temp_usage_event_links")
    conn.execute(
        """
        CREATE TEMP TABLE temp_usage_event_links AS
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
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX temp_usage_event_links_record_id ON temp_usage_event_links(record_id)"
    )
    conn.execute(
        """
        UPDATE usage_events
        SET
            thread_call_index = (
                SELECT next_thread_call_index
                FROM temp_usage_event_links
                WHERE temp_usage_event_links.record_id = usage_events.record_id
            ),
            previous_record_id = (
                SELECT previous_id
                FROM temp_usage_event_links
                WHERE temp_usage_event_links.record_id = usage_events.record_id
            ),
            next_record_id = (
                SELECT next_id
                FROM temp_usage_event_links
                WHERE temp_usage_event_links.record_id = usage_events.record_id
            )
        WHERE record_id IN (
            SELECT record_id
            FROM temp_usage_event_links
        )
        """
    )
    conn.execute("DROP TABLE IF EXISTS temp_usage_event_links")
    return conn.total_changes - before


def refresh_thread_summaries(db_path: Path = DEFAULT_DB_PATH) -> int:
    """Rebuild materialized per-thread aggregate summaries."""

    with connect(db_path) as conn:
        init_db(conn)
        return rebuild_thread_summaries(conn)


def export_usage_csv(
    output_path: Path,
    db_path: Path = DEFAULT_DB_PATH,
    limit: int | None = None,
    privacy_mode: str = "normal",
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    privacy_mode = validate_privacy_mode(privacy_mode)
    sql = "SELECT * FROM usage_events ORDER BY event_timestamp, cumulative_total_tokens"
    params: tuple[int, ...] = ()
    normalized_limit = _normalize_limit(limit)
    if normalized_limit is not None:
        sql += " LIMIT ?"
        params = (normalized_limit,)
    with connect(db_path) as conn:
        init_db(conn)
        rows = [_row_to_dict(row) for row in conn.execute(sql, params)]
    rows = apply_project_privacy_to_rows(rows, privacy_mode=privacy_mode)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVENT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column) for column in EVENT_COLUMNS})
    return len(rows)
