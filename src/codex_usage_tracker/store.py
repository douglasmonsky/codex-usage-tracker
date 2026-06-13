"""SQLite persistence and aggregate queries for Codex usage data."""

from __future__ import annotations

import csv
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.models import RefreshResult, UsageEvent
from codex_usage_tracker.parser import (
    PARSER_DIAGNOSTIC_KEYS,
    compact_parser_diagnostics,
    find_session_logs,
    load_session_index,
    parse_usage_events_from_file_with_state,
)
from codex_usage_tracker.paths import DEFAULT_CODEX_HOME, DEFAULT_DB_PATH
from codex_usage_tracker.projects import apply_project_privacy_to_rows, validate_privacy_mode
from codex_usage_tracker.schema import (
    USAGE_EVENT_COLUMN_NAMES,
    USAGE_EVENT_SCHEMA_CHECKSUM,
)
from codex_usage_tracker.store_query_sql import (
    _group_expression,
    _normalize_limit,
    _normalize_offset,
    _normalize_sort_direction,
    _since_where_clause,
    _usage_api_sort_expression,
    _usage_api_where_clause,
    _usage_where_clause,
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
from codex_usage_tracker.store_thread_summaries import rebuild_thread_summaries

EVENT_COLUMNS = list(USAGE_EVENT_COLUMN_NAMES)
__all__ = ["EVENT_COLUMNS", "SCHEMA_VERSION", "SchemaMigrationError", "init_db"]


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
        parsed_files.append((plan.path, file_events, file_stats, parsed_file.state))
        for key, value in file_stats.items():
            stats[key] = stats.get(key, 0) + int(value)
    inserted = upsert_usage_events(
        events,
        db_path=db_path,
        replace_source_files=(plan.path for plan in parse_plans if plan.replace_existing),
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
        conn.execute("DELETE FROM usage_events")
        conn.execute("DELETE FROM thread_summaries")
        conn.execute("DELETE FROM source_files")
        conn.execute("DELETE FROM refresh_meta")
    return {"db_path": str(db_path), "deleted_usage_events": deleted_rows}


@contextmanager
def connect(db_path: Path = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    with suppress(sqlite3.DatabaseError):
        conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


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
        "parser_adapter": "codex-jsonl-v1",
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
) -> int:
    rows = [event.to_row() for event in events]
    source_files_to_replace = [str(path) for path in replace_source_files or []]
    with connect(db_path) as conn:
        init_db(conn)
        if source_files_to_replace:
            placeholders = ", ".join("?" for _source in source_files_to_replace)
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
        conn.executemany(sql, [[row[column] for column in EVENT_COLUMNS] for row in rows])
        if refresh_links:
            _refresh_usage_event_links(conn)
            rebuild_thread_summaries(conn)
        return len(rows)


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


def query_summary(
    db_path: Path = DEFAULT_DB_PATH,
    group_by: str = "thread",
    limit: int = 20,
    since: str | None = None,
) -> list[dict[str, Any]]:
    group_expr = _group_expression(group_by)
    where_clause, raw_params = _since_where_clause(since)
    params: list[Any] = list(raw_params)
    sql = f"""
        SELECT
            {group_expr} AS group_key,
            COUNT(*) AS model_calls,
            COUNT(DISTINCT session_id) AS sessions,
            COUNT(DISTINCT turn_id) AS turns,
            SUM(input_tokens) AS input_tokens,
            SUM(cached_input_tokens) AS cached_input_tokens,
            SUM(uncached_input_tokens) AS uncached_input_tokens,
            SUM(output_tokens) AS output_tokens,
            SUM(reasoning_output_tokens) AS reasoning_output_tokens,
            SUM(total_tokens) AS total_tokens,
            AVG(cache_ratio) AS avg_cache_ratio,
            AVG(reasoning_output_ratio) AS avg_reasoning_output_ratio,
            AVG(context_window_percent) AS avg_context_window_percent,
            MAX(event_timestamp) AS latest_event
        FROM usage_events
        {where_clause}
        GROUP BY group_key
        ORDER BY total_tokens DESC
        LIMIT ?
    """
    params.append(limit)
    with connect(db_path) as conn:
        init_db(conn)
        return [_row_to_dict(row) for row in conn.execute(sql, params)]


def query_session_usage(
    db_path: Path = DEFAULT_DB_PATH,
    session_id: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        init_db(conn)
        if session_id is None:
            row = conn.execute(
                """
                SELECT session_id
                FROM usage_events
                GROUP BY session_id
                ORDER BY MAX(event_timestamp) DESC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return []
            session_id = str(row["session_id"])
        rows = conn.execute(
            """
            SELECT *
            FROM usage_events
            WHERE session_id = ?
            ORDER BY event_timestamp, cumulative_total_tokens
            LIMIT ?
            """,
            (session_id, limit),
        )
        return [_row_to_dict(row) for row in rows]


def query_usage_record(
    db_path: Path = DEFAULT_DB_PATH,
    record_id: str | None = None,
) -> dict[str, Any] | None:
    """Return one aggregate usage row by stable record id."""

    if not record_id:
        return None
    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute(
            """
            SELECT *
            FROM usage_events
            WHERE record_id = ?
            LIMIT 1
            """,
            (record_id,),
        ).fetchone()
        return _row_to_dict(row) if row is not None else None


def query_dashboard_events(
    db_path: Path = DEFAULT_DB_PATH,
    limit: int | None = 5000,
    offset: int = 0,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    min_tokens: int | None = None,
    include_archived: bool = True,
) -> list[dict[str, Any]]:
    where_clause, params = _usage_where_clause(
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        min_tokens=min_tokens,
        table_alias="usage_events",
        include_archived=include_archived,
    )
    parent_where_clause, parent_params = _usage_where_clause(include_archived=include_archived)
    parent_thread_filter = (
        f"{parent_where_clause} AND thread_name IS NOT NULL"
        if parent_where_clause
        else "WHERE thread_name IS NOT NULL"
    )
    normalized_limit = _normalize_limit(limit)
    normalized_offset = _normalize_offset(offset)
    limit_clause = ""
    query_params = [*parent_params, *params]
    if normalized_limit is not None:
        limit_clause = "LIMIT ?"
        query_params.append(normalized_limit)
        if normalized_offset:
            limit_clause += " OFFSET ?"
            query_params.append(normalized_offset)
    elif normalized_offset:
        limit_clause = "LIMIT -1 OFFSET ?"
        query_params.append(normalized_offset)
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            f"""
            SELECT
                usage_events.*,
                coalesce(
                    usage_events.parent_thread_name,
                    parent_threads.thread_name
                ) AS resolved_parent_thread_name,
                coalesce(
                    usage_events.parent_session_updated_at,
                    parent_threads.session_updated_at
                ) AS resolved_parent_session_updated_at
            FROM usage_events
            LEFT JOIN (
                SELECT
                    session_id,
                    max(thread_name) AS thread_name,
                    max(session_updated_at) AS session_updated_at
                FROM usage_events
                {parent_thread_filter}
                GROUP BY session_id
            ) AS parent_threads
            ON usage_events.parent_session_id = parent_threads.session_id
            {where_clause}
            ORDER BY usage_events.event_timestamp DESC, usage_events.cumulative_total_tokens DESC
            {limit_clause}
            """,
            query_params,
        )
        return [_row_to_dict(row) for row in rows]


def query_dashboard_event_count(
    db_path: Path = DEFAULT_DB_PATH,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    min_tokens: int | None = None,
    include_archived: bool = True,
) -> int:
    """Return total aggregate usage rows available for the dashboard window."""

    where_clause, params = _usage_where_clause(
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        min_tokens=min_tokens,
        include_archived=include_archived,
    )
    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS row_count
            FROM usage_events
            {where_clause}
            """,
            params,
        ).fetchone()
        return int(row["row_count"] if row is not None else 0)


def query_dashboard_token_summary(
    db_path: Path = DEFAULT_DB_PATH,
    since: str | None = None,
    include_archived: bool = True,
) -> dict[str, Any]:
    """Return cheap aggregate token totals for the dashboard shell."""

    where_clause, params = _usage_where_clause(
        since=since,
        include_archived=include_archived,
    )
    with connect(db_path) as conn:
        init_db(conn)
        total_row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS row_count,
                coalesce(SUM(input_tokens), 0) AS input_tokens,
                coalesce(SUM(cached_input_tokens), 0) AS cached_input_tokens,
                coalesce(SUM(uncached_input_tokens), 0) AS uncached_input_tokens,
                coalesce(SUM(output_tokens), 0) AS output_tokens,
                coalesce(SUM(reasoning_output_tokens), 0) AS reasoning_output_tokens,
                coalesce(SUM(total_tokens), 0) AS total_tokens
            FROM usage_events
            {where_clause}
            """,
            params,
        ).fetchone()
        model_rows = [
            _row_to_dict(row)
            for row in conn.execute(
                f"""
                SELECT
                    coalesce(model, 'Unknown model') AS model,
                    COUNT(*) AS row_count,
                    coalesce(SUM(input_tokens), 0) AS input_tokens,
                    coalesce(SUM(cached_input_tokens), 0) AS cached_input_tokens,
                    coalesce(SUM(uncached_input_tokens), 0) AS uncached_input_tokens,
                    coalesce(SUM(output_tokens), 0) AS output_tokens,
                    coalesce(SUM(reasoning_output_tokens), 0) AS reasoning_output_tokens,
                    coalesce(SUM(total_tokens), 0) AS total_tokens
                FROM usage_events
                {where_clause}
                GROUP BY coalesce(model, 'Unknown model')
                """,
                params,
            )
        ]
    summary = _row_to_dict(total_row) if total_row is not None else {}
    return {
        "row_count": int(summary.get("row_count") or 0),
        "input_tokens": int(summary.get("input_tokens") or 0),
        "cached_input_tokens": int(summary.get("cached_input_tokens") or 0),
        "uncached_input_tokens": int(summary.get("uncached_input_tokens") or 0),
        "output_tokens": int(summary.get("output_tokens") or 0),
        "reasoning_output_tokens": int(summary.get("reasoning_output_tokens") or 0),
        "total_tokens": int(summary.get("total_tokens") or 0),
        "model_rows": model_rows,
    }


def query_usage_status(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Return cheap row-count metadata for live dashboard status checks."""

    scoped_where, scoped_params = _usage_where_clause(include_archived=include_archived)
    active_where, active_params = _usage_where_clause(include_archived=False)
    with connect(db_path) as conn:
        init_db(conn)
        total_row = conn.execute("SELECT COUNT(*) AS count FROM usage_events").fetchone()
        active_row = conn.execute(
            f"SELECT COUNT(*) AS count FROM usage_events {active_where}",
            active_params,
        ).fetchone()
        scoped_row = conn.execute(
            f"SELECT COUNT(*) AS count FROM usage_events {scoped_where}",
            scoped_params,
        ).fetchone()
        max_row = conn.execute(
            f"SELECT MAX(event_timestamp) AS max_event_timestamp FROM usage_events {scoped_where}",
            scoped_params,
        ).fetchone()
    return {
        "total_rows": int(total_row["count"] if total_row is not None else 0),
        "active_rows": int(active_row["count"] if active_row is not None else 0),
        "scoped_rows": int(scoped_row["count"] if scoped_row is not None else 0),
        "max_event_timestamp": (
            max_row["max_event_timestamp"] if max_row is not None else None
        ),
    }


def query_usage_api_events(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    limit: int | None = 100,
    offset: int = 0,
    search: str | None = None,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    thread_key: str | None = None,
    include_archived: bool = False,
    sort: str = "time",
    direction: str = "desc",
) -> list[dict[str, Any]]:
    """Return a SQL-backed slice for live dashboard call APIs."""

    where_clause, params = _usage_api_where_clause(
        search=search,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        thread_key=thread_key,
        include_archived=include_archived,
        table_alias="usage_events",
    )
    order_expr = _usage_api_sort_expression(sort)
    direction_sql = _normalize_sort_direction(direction)
    normalized_limit = _normalize_limit(limit)
    normalized_offset = _normalize_offset(offset)
    limit_clause = ""
    query_params = list(params)
    if normalized_limit is not None:
        limit_clause = "LIMIT ?"
        query_params.append(normalized_limit)
        if normalized_offset:
            limit_clause += " OFFSET ?"
            query_params.append(normalized_offset)
    elif normalized_offset:
        limit_clause = "LIMIT -1 OFFSET ?"
        query_params.append(normalized_offset)
    parent_where_clause, parent_params = _usage_where_clause(include_archived=include_archived)
    parent_thread_filter = (
        f"{parent_where_clause} AND thread_name IS NOT NULL"
        if parent_where_clause
        else "WHERE thread_name IS NOT NULL"
    )
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            f"""
            SELECT
                usage_events.*,
                coalesce(
                    usage_events.parent_thread_name,
                    parent_threads.thread_name
                ) AS resolved_parent_thread_name,
                coalesce(
                    usage_events.parent_session_updated_at,
                    parent_threads.session_updated_at
                ) AS resolved_parent_session_updated_at
            FROM usage_events
            LEFT JOIN (
                SELECT
                    session_id,
                    max(thread_name) AS thread_name,
                    max(session_updated_at) AS session_updated_at
                FROM usage_events
                {parent_thread_filter}
                GROUP BY session_id
            ) AS parent_threads
            ON usage_events.parent_session_id = parent_threads.session_id
            {where_clause}
            ORDER BY {order_expr} {direction_sql},
                usage_events.event_timestamp DESC,
                usage_events.cumulative_total_tokens DESC
            {limit_clause}
            """,
            [*parent_params, *query_params],
        )
        return [_row_to_dict(row) for row in rows]


def query_usage_api_event_count(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    search: str | None = None,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    thread_key: str | None = None,
    include_archived: bool = False,
) -> int:
    """Return count for SQL-backed live dashboard call APIs."""

    where_clause, params = _usage_api_where_clause(
        search=search,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        thread_key=thread_key,
        include_archived=include_archived,
    )
    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute(
            f"SELECT COUNT(*) AS row_count FROM usage_events {where_clause}",
            params,
        ).fetchone()
        return int(row["row_count"] if row is not None else 0)


def query_thread_summaries(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    limit: int | None = 100,
    offset: int = 0,
    search: str | None = None,
    include_archived: bool = False,
    sort: str = "tokens",
    direction: str = "desc",
) -> list[dict[str, Any]]:
    """Return materialized thread summaries for live dashboard APIs."""

    clauses = ["is_archived_scope = ?"]
    params: list[Any] = ["all-history" if include_archived else "active"]
    if search:
        like = f"%{search}%"
        clauses.append("(thread_key LIKE ? OR thread_label LIKE ?)")
        params.extend([like, like])
    where_clause = "WHERE " + " AND ".join(f"({clause})" for clause in clauses)
    sort_map = {
        "tokens": "total_tokens",
        "time": "latest_event_timestamp",
        "calls": "call_count",
        "cache": "avg_cache_ratio",
        "thread": "thread_label",
    }
    if sort not in sort_map:
        allowed = ", ".join(sorted(sort_map))
        raise ValueError(f"sort must be one of: {allowed}")
    direction_sql = _normalize_sort_direction(direction)
    normalized_limit = _normalize_limit(limit)
    normalized_offset = _normalize_offset(offset)
    limit_clause = ""
    query_params = list(params)
    if normalized_limit is not None:
        limit_clause = "LIMIT ?"
        query_params.append(normalized_limit)
        if normalized_offset:
            limit_clause += " OFFSET ?"
            query_params.append(normalized_offset)
    elif normalized_offset:
        limit_clause = "LIMIT -1 OFFSET ?"
        query_params.append(normalized_offset)
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            f"""
            SELECT *
            FROM thread_summaries
            {where_clause}
            ORDER BY {sort_map[sort]} {direction_sql}, latest_event_timestamp DESC
            {limit_clause}
            """,
            query_params,
        )
        return [_row_to_dict(row) for row in rows]


def query_most_expensive_calls(
    db_path: Path = DEFAULT_DB_PATH, limit: int = 20, since: str | None = None
) -> list[dict[str, Any]]:
    """Return the largest aggregate model calls by last-call token count."""

    where_clause, params = _since_where_clause(since)
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            f"""
            SELECT *
            FROM usage_events
            {where_clause}
            ORDER BY total_tokens DESC, event_timestamp DESC
            LIMIT ?
            """,
            (*params, limit),
        )
        return [_row_to_dict(row) for row in rows]


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



def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)
