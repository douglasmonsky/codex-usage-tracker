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
    parse_usage_events,
)
from codex_usage_tracker.paths import DEFAULT_CODEX_HOME, DEFAULT_DB_PATH
from codex_usage_tracker.projects import apply_project_privacy_to_rows, validate_privacy_mode
from codex_usage_tracker.schema import (
    USAGE_EVENT_COLUMN_NAMES,
    USAGE_EVENT_CREATE_COLUMNS_SQL,
    USAGE_EVENT_REPAIR_COLUMNS,
    USAGE_EVENT_SCHEMA_CHECKSUM,
)

EVENT_COLUMNS = list(USAGE_EVENT_COLUMN_NAMES)

SCHEMA_VERSION = 2
MIGRATION_NAMES = {
    1: "create usage_events aggregate fact table",
    2: "track schema migration checksum metadata",
}
_ARCHIVED_SOURCE_PATTERNS = (
    "%/archived_sessions/%",
    "archived_sessions/%",
    "%\\archived_sessions\\%",
    "archived_sessions\\%",
)


class SchemaMigrationError(RuntimeError):
    """Raised when a persisted aggregate schema cannot be repaired safely."""


def refresh_usage_index(
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
) -> RefreshResult:
    """Scan Codex logs and upsert aggregate usage events."""

    logs = find_session_logs(codex_home=codex_home, include_archived=include_archived)
    session_index = load_session_index(codex_home)
    stats: dict[str, int] = {}
    events = parse_usage_events(logs, session_index=session_index, stats=stats)
    inserted = upsert_usage_events(events, db_path=db_path)
    skipped_events = stats.get("skipped_events", 0)
    diagnostics = compact_parser_diagnostics(stats)
    record_refresh_metadata(
        db_path=db_path,
        scanned_files=len(logs),
        parsed_events=len(events),
        skipped_events=skipped_events,
        inserted_or_updated_events=inserted,
        parser_diagnostics=diagnostics,
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


def init_db(conn: sqlite3.Connection) -> None:
    user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    _ensure_migrations_table(conn)
    if user_version < 1:
        _migrate_v1(conn)
        _record_migration(conn, 1)
    else:
        _migrate_v1(conn)
        _record_migration_if_missing(conn, 1)
    if user_version < 2:
        _migrate_v2(conn)
        _record_migration(conn, 2)
    else:
        _migrate_v2(conn)
        _record_migration_if_missing(conn, 2)
    _validate_usage_events_schema(conn)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def _migrate_v1(conn: sqlite3.Connection) -> None:
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS usage_events (
            {USAGE_EVENT_CREATE_COLUMNS_SQL}
        );

        CREATE TABLE IF NOT EXISTS refresh_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    _ensure_columns(conn, USAGE_EVENT_REPAIR_COLUMNS)
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_usage_session ON usage_events(session_id);
        CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON usage_events(event_timestamp);
        CREATE INDEX IF NOT EXISTS idx_usage_model_effort ON usage_events(model, effort);
        CREATE INDEX IF NOT EXISTS idx_usage_thread ON usage_events(thread_name);
        CREATE INDEX IF NOT EXISTS idx_usage_parent_thread ON usage_events(parent_thread_name);
        CREATE INDEX IF NOT EXISTS idx_usage_parent_session ON usage_events(parent_session_id);
        CREATE INDEX IF NOT EXISTS idx_usage_total_tokens ON usage_events(total_tokens);
        """
    )


def _migrate_v2(conn: sqlite3.Connection) -> None:
    _ensure_migrations_table(conn)


def _record_migration(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        """
        INSERT INTO schema_migrations (version, name, checksum, applied_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(version) DO UPDATE SET
            name = excluded.name,
            checksum = excluded.checksum
        """,
        (
            version,
            MIGRATION_NAMES[version],
            USAGE_EVENT_SCHEMA_CHECKSUM,
            datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        ),
    )


def _record_migration_if_missing(conn: sqlite3.Connection, version: int) -> None:
    exists = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ?",
        (version,),
    ).fetchone()
    if exists is None:
        _record_migration(conn, version)


def record_refresh_metadata(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    scanned_files: int,
    parsed_events: int,
    skipped_events: int,
    inserted_or_updated_events: int,
    parser_diagnostics: dict[str, int] | None = None,
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


def _ensure_columns(conn: sqlite3.Connection, columns: dict[str, str]) -> None:
    existing = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(usage_events)").fetchall()
    }
    for column, column_type in columns.items():
        if column not in existing:
            try:
                conn.execute(f"ALTER TABLE usage_events ADD COLUMN {column} {column_type}")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise


def _validate_usage_events_schema(conn: sqlite3.Connection) -> None:
    existing = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(usage_events)").fetchall()
    }
    missing = [column for column in EVENT_COLUMNS if column not in existing]
    if missing:
        missing_text = ", ".join(missing)
        raise SchemaMigrationError(
            "usage_events schema is missing required columns: "
            f"{missing_text}. Run codex-usage-tracker rebuild-index after confirming your "
            "local aggregate index can be regenerated; raw Codex logs are not touched by "
            "rebuild-index."
        )


def upsert_usage_events(
    events: Iterable[UsageEvent], db_path: Path = DEFAULT_DB_PATH
) -> int:
    rows = [event.to_row() for event in events]
    with connect(db_path) as conn:
        init_db(conn)
        if not rows:
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
        return len(rows)


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


def _group_expression(group_by: str) -> str:
    mapping = {
        "date": "substr(event_timestamp, 1, 10)",
        "model": "coalesce(model, 'Unknown model')",
        "effort": "coalesce(effort, 'Unknown effort')",
        "cwd": "coalesce(cwd, 'Unknown cwd')",
        "thread": "coalesce(thread_name, parent_thread_name, session_id)",
        "session": "session_id",
        "thread_source": "coalesce(thread_source, 'user')",
        "subagent_type": "coalesce(subagent_type, 'not subagent')",
        "agent_role": "coalesce(agent_role, 'not agent role')",
        "parent_session": "coalesce(parent_session_id, 'no parent session')",
        "parent_thread": "coalesce(parent_thread_name, 'no parent thread')",
    }
    try:
        return mapping[group_by]
    except KeyError as exc:
        allowed = ", ".join(sorted(mapping))
        raise ValueError(f"group_by must be one of: {allowed}") from exc


def _since_where_clause(since: str | None) -> tuple[str, list[Any]]:
    return _usage_where_clause(since=since)


def _usage_where_clause(
    *,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    min_tokens: int | None = None,
    table_alias: str | None = None,
    include_archived: bool = True,
) -> tuple[str, list[Any]]:
    prefix = f"{table_alias}." if table_alias else ""
    clauses: list[str] = []
    params: list[Any] = []
    if since:
        clauses.append(f"{prefix}event_timestamp >= ?")
        params.append(since)
    if until:
        clauses.append(f"{prefix}event_timestamp <= ?")
        params.append(until)
    if model:
        clauses.append(f"{prefix}model = ?")
        params.append(model)
    if effort:
        clauses.append(f"{prefix}effort = ?")
        params.append(effort)
    if thread:
        clauses.append(
            "("
            f"{prefix}thread_name = ? OR "
            f"{prefix}parent_thread_name = ? OR "
            f"{prefix}session_id = ?"
            ")"
        )
        params.extend([thread, thread, thread])
    if min_tokens is not None:
        clauses.append(f"{prefix}total_tokens >= ?")
        params.append(min_tokens)
    if not include_archived:
        clauses.extend([f"{prefix}source_file NOT LIKE ?"] * len(_ARCHIVED_SOURCE_PATTERNS))
        params.extend(_ARCHIVED_SOURCE_PATTERNS)
    if not clauses:
        return "", []
    return "WHERE " + " AND ".join(clauses), params


def _normalize_limit(limit: int | None) -> int | None:
    if limit is None or limit <= 0:
        return None
    return int(limit)


def _normalize_offset(offset: int | None) -> int:
    if offset is None or offset <= 0:
        return 0
    return int(offset)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)
