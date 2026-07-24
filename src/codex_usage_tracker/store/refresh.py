"""Refresh orchestration for the aggregate usage index."""

from __future__ import annotations

from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

from codex_usage_tracker.core.models import RefreshResult
from codex_usage_tracker.core.paths import (
    DEFAULT_CODEX_HOME,
    DEFAULT_DB_PATH,
    DEFAULT_OTEL_COMPLETIONS_DIR,
)
from codex_usage_tracker.parser.api import find_session_logs, load_session_index
from codex_usage_tracker.parser.state import compact_parser_diagnostics
from codex_usage_tracker.store.compression_revisions import touch_compression_revisions
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.content_index import clear_content_index_rows
from codex_usage_tracker.store.otel_ingest import ingest_otel_completion_files
from codex_usage_tracker.store.otel_reconciliation import (
    reconcile_otel_completions,
    reset_otel_completion_matches,
)
from codex_usage_tracker.store.refresh_callbacks import DerivedFactSyncCallback
from codex_usage_tracker.store.refresh_metadata import (
    OTEL_REFRESH_COUNTER_KEYS,
    record_refresh_metadata,
)
from codex_usage_tracker.store.refresh_parse import (
    RefreshProgressCallback,
    emit_refresh_progress,
)
from codex_usage_tracker.store.refresh_stream import write_refresh_stream
from codex_usage_tracker.store.schema import init_db
from codex_usage_tracker.store.sources import source_logs_requiring_parse


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
        phase="otel",
        status="running",
        completed=0,
        total=1,
        message="Reconciling aggregate OTel completion tiers",
    )
    resolved_otel_dir = otel_dir or db_path.parent / DEFAULT_OTEL_COMPLETIONS_DIR.name
    otel_diagnostics = _refresh_otel_completions(db_path=db_path, otel_dir=resolved_otel_dir)
    emit_refresh_progress(
        progress_callback,
        phase="otel",
        status="completed",
        completed=1,
        total=1,
        message="Reconciled aggregate OTel completion tiers",
        **otel_diagnostics,
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
        otel_diagnostics=otel_diagnostics,
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
    otel_diagnostics: dict[str, int],
) -> RefreshResult:
    skipped_events = stats.get("skipped_events", 0)
    diagnostics = {
        **compact_parser_diagnostics(stats),
        **{key: value for key, value in otel_diagnostics.items() if value},
    }
    record_refresh_metadata(
        db_path=db_path,
        scanned_files=scanned_files,
        parsed_events=parsed_events,
        skipped_events=skipped_events,
        inserted_or_updated_events=inserted,
        parser_diagnostics=diagnostics,
        otel_diagnostics=otel_diagnostics,
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


def _refresh_otel_completions(*, db_path: Path, otel_dir: Path) -> dict[str, int]:
    with connect(db_path) as conn:
        init_db(conn)
        ingest = ingest_otel_completion_files(conn, otel_dir)
        reconciled = reconcile_otel_completions(conn)
        if reconciled.updated_usage_rows:
            touch_compression_revisions(conn, {"calls", "threads"})
    counters = {
        "otel_files_scanned": ingest.files_scanned,
        "otel_imported": ingest.imported,
        "otel_duplicates": ingest.duplicates,
        "otel_matched": reconciled.matched,
        "otel_pending": reconciled.pending,
        "otel_ambiguous": reconciled.ambiguous,
        "otel_conflicts": reconciled.conflicts,
        **ingest.diagnostics,
    }
    return {key: int(counters.get(key, 0)) for key in OTEL_REFRESH_COUNTER_KEYS}


def rebuild_usage_index(
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    aggregate_only: bool = False,
    otel_dir: Path | None = None,
    derived_fact_sync: DerivedFactSyncCallback | None = None,
) -> RefreshResult:
    """Clear aggregate rows and rescan local Codex logs."""

    with connect(db_path) as conn:
        init_db(conn)
        reset_otel_completion_matches(conn)
        clear_content_index_rows(conn)
        for table in (
            "allowance_observations",
            "call_diagnostic_facts",
            "diagnostic_snapshots",
            "recommendation_fact_state",
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
        otel_dir=otel_dir,
        derived_fact_sync=derived_fact_sync,
    )
