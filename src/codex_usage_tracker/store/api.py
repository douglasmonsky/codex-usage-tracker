"""SQLite persistence and aggregate queries for Codex usage data."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Collection, Iterable, Mapping
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.models import DiagnosticFact, RefreshResult, UsageEvent
from codex_usage_tracker.core.paths import (
    DEFAULT_CODEX_HOME,
    DEFAULT_DB_PATH,
)
from codex_usage_tracker.core.schema import (
    USAGE_EVENT_COLUMN_NAMES,
    USAGE_EVENT_SCHEMA_CHECKSUM,
)
from codex_usage_tracker.store.allowance_observations import (
    query_allowance_observations as query_allowance_observations,
)
from codex_usage_tracker.store.compression_fact_sync import (
    clear_compression_detector_facts,
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
    query_canonical_usage_v2 as query_canonical_usage_v2,
)
from codex_usage_tracker.store.dashboard_queries import (
    query_dashboard_event_count as query_dashboard_event_count,
)
from codex_usage_tracker.store.dashboard_queries import (
    query_dashboard_event_counts as query_dashboard_event_counts,
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
from codex_usage_tracker.store.refresh_metadata import (
    OTEL_REFRESH_COUNTER_KEYS as OTEL_REFRESH_COUNTER_KEYS,
)
from codex_usage_tracker.store.refresh_metadata import (
    record_refresh_metadata as record_refresh_metadata,
)
from codex_usage_tracker.store.rows import (
    row_to_dict as _row_to_dict,
)
from codex_usage_tracker.store.schema import (
    SCHEMA_VERSION,
    SchemaMigrationError,
    init_db,
)
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
    query_usage_api_distinct_cwds as query_usage_api_distinct_cwds,
)
from codex_usage_tracker.store.usage_api_queries import (
    query_usage_api_event_count as query_usage_api_event_count,
)
from codex_usage_tracker.store.usage_api_queries import (
    query_usage_api_events as query_usage_api_events,
)
from codex_usage_tracker.store.usage_api_queries import (
    query_usage_api_filter_options as query_usage_api_filter_options,
)
from codex_usage_tracker.store.usage_event_writer import (
    deferred_usage_event_indexes as _deferred_usage_event_indexes,
)
from codex_usage_tracker.store.usage_event_writer import (
    finalize_streamed_usage_event_upserts as _finalize_streamed_usage_event_upserts,
)
from codex_usage_tracker.store.usage_event_writer import (
    refresh_usage_event_links as _refresh_usage_event_links,
)
from codex_usage_tracker.store.usage_event_writer import (
    upsert_usage_events_in_connection as _upsert_usage_events_in_connection,
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
__all__ = [
    "EVENT_COLUMNS",
    "SCHEMA_VERSION",
    "SchemaMigrationError",
    "_deferred_usage_event_indexes",
    "_finalize_streamed_usage_event_upserts",
    "init_db",
]
RefreshProgressCallback = Callable[[dict[str, object]], None]


class InvalidDatabasePathError(ValueError):
    """Raised when a read-only database target is present but unusable."""


def refresh_usage_index(
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    aggregate_only: bool = False,
    otel_dir: Path | None = None,
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
        otel_dir=otel_dir,
        progress_callback=progress_callback,
        derived_fact_sync=_public_refresh_sync(derived_fact_sync),
    )


def rebuild_usage_index(
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    aggregate_only: bool = False,
    otel_dir: Path | None = None,
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
        otel_dir=otel_dir,
        derived_fact_sync=_public_refresh_sync(derived_fact_sync),
    )


def _public_refresh_sync(
    derived_fact_sync: DerivedFactSyncCallback | None,
) -> DerivedFactSyncCallback:
    """Preserve allowance materialization at the historical public facade."""
    if derived_fact_sync is not None:
        return derived_fact_sync
    from codex_usage_tracker.allowance_intelligence.materialization import (
        sync_refresh_allowance_intelligence,
    )

    return sync_refresh_allowance_intelligence


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
        conn.execute("DELETE FROM otel_completion_events")
        conn.execute("DELETE FROM otel_completion_sources")
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


def refresh_metadata(db_path: Path = DEFAULT_DB_PATH) -> dict[str, str]:
    """Return latest refresh metadata and parser diagnostics."""

    if not db_path.exists():
        return {}
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute("SELECT key, value FROM refresh_meta").fetchall()
    return {str(row["key"]): str(row["value"]) for row in rows}


def query_request_context_facts(
    db_path: Path,
    *,
    scope: Mapping[str, object],
    priced_models: Collection[str] = (),
    credit_models: Collection[str] = (),
) -> dict[str, object]:
    """Read scoped source and accounting facts in one read-only transaction."""
    if not db_path.exists() and not db_path.is_symlink():
        return _empty_request_context_facts()
    if not db_path.is_file():
        raise InvalidDatabasePathError(f"database path must be a regular file: {db_path}")
    physical_where, physical_params = _request_context_where(scope, alias="physical")
    canonical_where, canonical_params = _request_context_where(scope, alias="canonical")
    pricing_sql, pricing_params = _model_coverage_sql("canonical", priced_models)
    credit_sql, credit_params = _model_coverage_sql("canonical", credit_models)
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=1.0)
    except sqlite3.Error as exc:
        raise InvalidDatabasePathError(
            f"database path could not be opened read-only: {db_path}"
        ) from exc
    row: sqlite3.Row | None = None
    operation_error: BaseException | None = None
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        row = connection.execute(
            f"""
            WITH physical_facts AS (
                SELECT
                    COUNT(*) AS physical_rows,
                    COALESCE(SUM(CASE WHEN is_duplicate = 1 THEN 1 ELSE 0 END), 0)
                        AS copied_rows_excluded
                FROM usage_events AS physical
                {physical_where}
            ),
            canonical_facts AS (
                SELECT
                    COUNT(*) AS canonical_rows,
                    MAX(event_timestamp) AS latest_indexed_event_at,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(CASE WHEN {pricing_sql} THEN total_tokens ELSE 0 END), 0)
                        AS priced_tokens,
                    COALESCE(SUM(CASE WHEN {credit_sql} THEN total_tokens ELSE 0 END), 0)
                        AS credit_tokens,
                    COALESCE(SUM(CASE
                        WHEN service_tier IS NOT NULL AND TRIM(service_tier) != ''
                        THEN total_tokens ELSE 0 END), 0) AS tier_tokens
                FROM canonical_usage_events AS canonical
                {canonical_where}
            )
            SELECT
                physical_facts.physical_rows,
                physical_facts.copied_rows_excluded,
                canonical_facts.canonical_rows,
                canonical_facts.latest_indexed_event_at,
                canonical_facts.total_tokens,
                canonical_facts.priced_tokens,
                canonical_facts.credit_tokens,
                canonical_facts.tier_tokens,
                (SELECT generation FROM compression_source_state WHERE singleton = 1)
                    AS source_generation,
                (SELECT value FROM refresh_meta WHERE key = 'latest_refresh_at')
                    AS refresh_completed_at
            FROM physical_facts CROSS JOIN canonical_facts
            """,
            [
                *physical_params,
                *pricing_params,
                *credit_params,
                *canonical_params,
            ],
        ).fetchone()
    except BaseException as exc:
        operation_error = exc
    cleanup_error = _finish_request_context_connection(connection)
    if operation_error is not None:
        if cleanup_error is not None:
            operation_error.__context__ = cleanup_error
        if not isinstance(operation_error, sqlite3.Error):
            raise operation_error
        raise InvalidDatabasePathError(
            f"database path could not be read: {db_path}"
        ) from operation_error
    if cleanup_error is not None:
        if not isinstance(cleanup_error, sqlite3.Error):
            raise cleanup_error
        raise InvalidDatabasePathError(
            f"database path could not be read: {db_path}"
        ) from cleanup_error
    if row is None:
        return _empty_request_context_facts()
    total_tokens = int(row["total_tokens"] or 0)
    return {
        "physical_rows": int(row["physical_rows"] or 0),
        "canonical_rows": int(row["canonical_rows"] or 0),
        "copied_rows_excluded": int(row["copied_rows_excluded"] or 0),
        "source_revision": f"generation:{int(row['source_generation'] or 0)}",
        "latest_indexed_event_at": row["latest_indexed_event_at"],
        "refresh_completed_at": row["refresh_completed_at"],
        "pricing_coverage": _token_coverage(row["priced_tokens"], total_tokens),
        "credit_coverage": _token_coverage(row["credit_tokens"], total_tokens),
        "service_tier_coverage": _token_coverage(row["tier_tokens"], total_tokens),
    }


def query_status_context_facts(
    db_path: Path,
    *,
    scope: Mapping[str, object],
    priced_models: Collection[str] = (),
    credit_models: Collection[str] = (),
) -> dict[str, object]:
    """Read bounded status facts, preferring current persisted active aggregates."""
    if not db_path.exists() and not db_path.is_symlink():
        return _empty_request_context_facts()
    if not db_path.is_file():
        raise InvalidDatabasePathError(f"database path must be a regular file: {db_path}")
    focused_facts = _query_materialized_active_context_facts(db_path, scope)
    if focused_facts is not None:
        return focused_facts
    return query_request_context_facts(
        db_path,
        scope=scope,
        priced_models=priced_models,
        credit_models=credit_models,
    )


def _query_materialized_active_context_facts(
    db_path: Path,
    scope: Mapping[str, object],
) -> dict[str, object] | None:
    """Use current aggregate facts for the common unfiltered active status scope."""
    filters = scope.get("filters")
    if (
        scope.get("history", "active") != "active"
        or scope.get("since") is not None
        or scope.get("until") is not None
        or (isinstance(filters, Mapping) and any(filters.values()))
    ):
        return None
    from codex_usage_tracker.store.home_queries import query_home_usage_metrics

    metrics = query_home_usage_metrics(db_path=db_path)
    if metrics is None:
        return None
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=1.0) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            row = connection.execute(
                """
                SELECT
                    (
                        SELECT COUNT(*)
                        FROM usage_events INDEXED BY idx_usage_archived_timestamp
                        WHERE is_archived = 0
                    ) AS physical_rows,
                    (
                        SELECT event_timestamp
                        FROM usage_events INDEXED BY idx_canonical_usage_archived_timestamp
                        WHERE is_archived = 0 AND is_duplicate = 0
                        ORDER BY event_timestamp DESC, cumulative_total_tokens DESC
                        LIMIT 1
                    ) AS latest_indexed_event_at,
                    (
                        SELECT value
                        FROM refresh_meta
                        WHERE key = 'latest_refresh_at'
                    ) AS refresh_completed_at
                """
            ).fetchone()
    except sqlite3.Error as exc:
        raise InvalidDatabasePathError(f"database path could not be read: {db_path}") from exc
    if row is None:
        return None
    canonical_rows = int(metrics.get("calls") or 0)
    physical_rows = int(row["physical_rows"] or 0)
    return {
        "physical_rows": physical_rows,
        "canonical_rows": canonical_rows,
        "copied_rows_excluded": max(0, physical_rows - canonical_rows),
        "source_revision": f"generation:{int(metrics.get('source_generation') or 0)}",
        "latest_indexed_event_at": row["latest_indexed_event_at"],
        "refresh_completed_at": row["refresh_completed_at"],
        "pricing_coverage": _optional_metric_coverage(metrics.get("pricing_coverage")),
        "credit_coverage": _optional_metric_coverage(metrics.get("credit_coverage")),
        "service_tier_coverage": _optional_metric_coverage(metrics.get("service_tier_coverage")),
    }


def _optional_metric_coverage(value: object) -> float | None:
    if not isinstance(value, int | float):
        return None
    return min(1.0, max(0.0, float(value)))


def _finish_request_context_connection(
    connection: sqlite3.Connection,
) -> BaseException | None:
    """Always close and return the first rollback or close failure."""
    rollback_error: BaseException | None = None
    try:
        connection.rollback()
    except BaseException as exc:
        rollback_error = exc
    try:
        connection.close()
    except BaseException as exc:
        return rollback_error or exc
    return rollback_error


def _request_context_where(scope: Mapping[str, object], *, alias: str) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if scope.get("history") != "all":
        clauses.append(f"COALESCE({alias}.is_archived, 0) = 0")
    filters = scope.get("filters")
    values = filters if isinstance(filters, Mapping) else {}
    for key, column in (
        ("project", "cwd"),
        ("thread_key", "thread_key"),
        ("model", "model"),
        ("effort", "effort"),
    ):
        value = values.get(key)
        if isinstance(value, str) and value:
            clauses.append(f"{alias}.{column} = ?")
            params.append(value)
    for key, operator in (("since", ">="), ("until", "<=")):
        value = scope.get(key)
        if isinstance(value, str) and value:
            clauses.append(f"{alias}.event_timestamp {operator} ?")
            params.append(value)
    return ("WHERE " + " AND ".join(clauses) if clauses else ""), params


def _model_coverage_sql(alias: str, models: Collection[str]) -> tuple[str, list[object]]:
    normalized = sorted({model for model in models if model})
    if not normalized:
        return "0", []
    placeholders = ", ".join("?" for _model in normalized)
    params: list[object] = [*normalized]
    return f"{alias}.model IN ({placeholders})", params


def _token_coverage(covered: object, total: int) -> float | None:
    if total <= 0:
        return None
    covered_tokens = float(covered) if isinstance(covered, int | float) else 0.0
    return covered_tokens / total


def _empty_request_context_facts() -> dict[str, object]:
    return {
        "physical_rows": 0,
        "canonical_rows": 0,
        "copied_rows_excluded": 0,
        "source_revision": None,
        "latest_indexed_event_at": None,
        "refresh_completed_at": None,
        "pricing_coverage": None,
        "credit_coverage": None,
        "service_tier_coverage": None,
    }


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


def refresh_usage_event_links(db_path: Path = DEFAULT_DB_PATH) -> int:
    """Recompute per-thread chronological adjacency for aggregate usage rows."""

    with connect(db_path) as conn:
        init_db(conn)
        changed = _refresh_usage_event_links(conn)
        rebuild_thread_summaries(conn)
        return changed


def refresh_thread_summaries(db_path: Path = DEFAULT_DB_PATH) -> int:
    """Rebuild materialized per-thread aggregate summaries."""

    with connect(db_path) as conn:
        init_db(conn)
        return rebuild_thread_summaries(conn)
