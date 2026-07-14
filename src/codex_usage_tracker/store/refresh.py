"""Refresh orchestration for the aggregate usage index."""

from __future__ import annotations

from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

from codex_usage_tracker.core.models import RefreshResult
from codex_usage_tracker.core.paths import DEFAULT_CODEX_HOME, DEFAULT_DB_PATH
from codex_usage_tracker.parser.api import find_session_logs, load_session_index
from codex_usage_tracker.parser.state import compact_parser_diagnostics
from codex_usage_tracker.store.api import (
    clear_content_index_rows,
    init_db,
    record_refresh_metadata,
)
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.refresh_callbacks import DerivedFactSyncCallback
from codex_usage_tracker.store.refresh_parse import (
    RefreshProgressCallback,
    emit_refresh_progress,
)
from codex_usage_tracker.store.refresh_stream import write_refresh_stream
from codex_usage_tracker.store.sources import source_logs_requiring_parse


def refresh_usage_index(
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    aggregate_only: bool = False,
    progress_callback: RefreshProgressCallback | None = None,
    derived_fact_sync: DerivedFactSyncCallback | None = None,
) -> RefreshResult:
    """Scan Codex logs and upsert aggregate usage events."""

    emit_refresh_progress(
        progress_callback,
        phase="discovering",
        status="running",
        completed=0,
        total=None,
        message="Finding Codex session logs",
    )
    logs = find_session_logs(codex_home=codex_home, include_archived=include_archived)
    session_index = load_session_index(codex_home)
    with connect(db_path) as conn:
        init_db(conn)
        parse_plans = source_logs_requiring_parse(conn, logs)
    emit_refresh_progress(
        progress_callback,
        phase="discovering",
        status="completed",
        completed=len(logs),
        total=len(logs),
        message="Planned source log refresh",
        scanned_files=len(logs),
        parsed_source_files=len(parse_plans),
        skipped_source_files=len(logs) - len(parse_plans),
    )
    try:
        stream_result = write_refresh_stream(
            db_path=db_path,
            parse_plans=parse_plans,
            session_index=session_index,
            aggregate_only=aggregate_only,
            progress_callback=progress_callback,
            force_serial=False,
            derived_fact_sync=derived_fact_sync,
        )
    except BrokenProcessPool:
        emit_refresh_progress(
            progress_callback,
            phase="parsing",
            status="running",
            completed=0,
            total=len(parse_plans),
            message="Parallel parser unavailable; retrying serially",
            workers=1,
        )
        stream_result = write_refresh_stream(
            db_path=db_path,
            parse_plans=parse_plans,
            session_index=session_index,
            aggregate_only=aggregate_only,
            progress_callback=progress_callback,
            force_serial=True,
            derived_fact_sync=derived_fact_sync,
        )
    emit_refresh_progress(
        progress_callback,
        phase="finalizing",
        status="running",
        completed=0,
        total=1,
        message="Recording refresh metadata",
    )
    result = _finalize_refresh_result(
        db_path=db_path,
        scanned_files=len(logs),
        parsed_source_files=len(parse_plans),
        stats=stream_result.stats,
        parsed_events=stream_result.parsed_events,
        inserted=stream_result.inserted_or_updated_events,
    )
    emit_refresh_progress(
        progress_callback,
        phase="finalizing",
        status="completed",
        completed=1,
        total=1,
        message="Refresh complete",
        result={
            "scanned_files": result.scanned_files,
            "parsed_events": result.parsed_events,
            "skipped_events": result.skipped_events,
            "inserted_or_updated_events": result.inserted_or_updated_events,
            "db_path": result.db_path,
            "parser_diagnostics": result.parser_diagnostics,
            "stage_timings_seconds": stream_result.stage_timings_seconds,
        },
    )
    return result


def _finalize_refresh_result(
    *,
    db_path: Path,
    scanned_files: int,
    parsed_source_files: int,
    stats: dict[str, int],
    parsed_events: int,
    inserted: int,
) -> RefreshResult:
    skipped_events = stats.get("skipped_events", 0)
    diagnostics = compact_parser_diagnostics(stats)
    record_refresh_metadata(
        db_path=db_path,
        scanned_files=scanned_files,
        parsed_events=parsed_events,
        skipped_events=skipped_events,
        inserted_or_updated_events=inserted,
        parser_diagnostics=diagnostics,
        parsed_source_files=parsed_source_files,
        skipped_source_files=scanned_files - parsed_source_files,
    )
    return RefreshResult(
        scanned_files=scanned_files,
        parsed_events=parsed_events,
        inserted_or_updated_events=inserted,
        db_path=str(db_path),
        skipped_events=skipped_events,
        parser_diagnostics=diagnostics,
    )


def rebuild_usage_index(
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    aggregate_only: bool = False,
    derived_fact_sync: DerivedFactSyncCallback | None = None,
) -> RefreshResult:
    """Clear aggregate rows and rescan local Codex logs."""

    with connect(db_path) as conn:
        init_db(conn)
        clear_content_index_rows(conn)
        for table in (
            "allowance_observations",
            "call_diagnostic_facts",
            "diagnostic_snapshots",
            "source_records",
            "usage_events",
            "thread_summaries",
            "source_files",
            "refresh_meta",
        ):
            conn.execute(f"DELETE FROM {table}")  # nosec B608 - fixed table names
    return refresh_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        include_archived=include_archived,
        aggregate_only=aggregate_only,
        derived_fact_sync=derived_fact_sync,
    )
