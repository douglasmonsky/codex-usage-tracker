"""Refresh orchestration for the aggregate usage index."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker import store as store_facade
from codex_usage_tracker.core.models import DiagnosticFact, RefreshResult, UsageEvent
from codex_usage_tracker.core.paths import DEFAULT_CODEX_HOME, DEFAULT_DB_PATH
from codex_usage_tracker.parser.api import (
    find_session_logs,
    load_session_index,
)
from codex_usage_tracker.parser.api import (
    parse_usage_events_from_file_with_state as _parse_usage_events_from_file_with_state,
)
from codex_usage_tracker.parser.state import compact_parser_diagnostics
from codex_usage_tracker.store.api import (
    init_db,
    record_refresh_metadata,
    record_source_file_metadata,
    upsert_usage_events,
)
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.sources import ParsedSourceFile, source_logs_requiring_parse

vars(store_facade)["parse_usage_events_from_file_with_state"] = (
    _parse_usage_events_from_file_with_state
)


def _parse_usage_events_from_file(*args: Any, **kwargs: Any) -> Any:
    parser = getattr(
        store_facade,
        "parse_usage_events_from_file_with_state",
        _parse_usage_events_from_file_with_state,
    )
    return parser(*args, **kwargs)


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
        parsed_file = _parse_usage_events_from_file(
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
