"""On-demand aggregate diagnostic report snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.diagnostic_snapshot_analysis import (
    analyze_indexed_source_logs,
    path_privacy_metadata,
)
from codex_usage_tracker.diagnostic_snapshot_concentration import (
    compute_concentration,
    concentration_privacy_metadata,
)
from codex_usage_tracker.diagnostic_snapshot_constants import (
    DIAGNOSTIC_BATCH_REFRESH_SCHEMA,
    DIAGNOSTIC_COMMANDS_SCHEMA,
    DIAGNOSTIC_COMMANDS_SECTION,
    DIAGNOSTIC_CONCENTRATION_SCHEMA,
    DIAGNOSTIC_CONCENTRATION_SECTION,
    DIAGNOSTIC_FILE_MODIFICATIONS_SCHEMA,
    DIAGNOSTIC_FILE_MODIFICATIONS_SECTION,
    DIAGNOSTIC_FILE_READS_SCHEMA,
    DIAGNOSTIC_FILE_READS_SECTION,
    DIAGNOSTIC_HISTORY_ACTIVE,
    DIAGNOSTIC_HISTORY_ALL,
    DIAGNOSTIC_OVERVIEW_SCHEMA,
    DIAGNOSTIC_OVERVIEW_SECTION,
    DIAGNOSTIC_READ_PRODUCTIVITY_SCHEMA,
    DIAGNOSTIC_READ_PRODUCTIVITY_SECTION,
    DIAGNOSTIC_SNAPSHOT_NOTES,
    DIAGNOSTIC_TOOL_OUTPUT_SCHEMA,
    DIAGNOSTIC_TOOL_OUTPUT_SECTION,
)
from codex_usage_tracker.diagnostic_snapshot_report import DiagnosticSnapshotReport
from codex_usage_tracker.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store import (
    connect,
    query_diagnostic_snapshot,
    upsert_diagnostic_snapshot,
)
from codex_usage_tracker.store_schema import init_db


def build_diagnostic_overview_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    refresh: bool = False,
) -> DiagnosticSnapshotReport:
    """Return the latest overview snapshot, optionally recomputing it first."""

    if refresh:
        return DiagnosticSnapshotReport(
            refresh_diagnostic_overview_snapshot(
                db_path=db_path,
                include_archived=include_archived,
            )
        )
    return DiagnosticSnapshotReport(
        diagnostic_overview_payload(
            db_path=db_path,
            include_archived=include_archived,
        )
    )


def build_diagnostic_tool_output_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    refresh: bool = False,
) -> DiagnosticSnapshotReport:
    """Return the latest tool-output snapshot, optionally recomputing it first."""

    return _build_source_log_snapshot_report(
        db_path=db_path,
        include_archived=include_archived,
        refresh=refresh,
        section=DIAGNOSTIC_TOOL_OUTPUT_SECTION,
        schema=DIAGNOSTIC_TOOL_OUTPUT_SCHEMA,
    )


def build_diagnostic_commands_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    refresh: bool = False,
) -> DiagnosticSnapshotReport:
    """Return the latest commands snapshot, optionally recomputing it first."""

    return _build_source_log_snapshot_report(
        db_path=db_path,
        include_archived=include_archived,
        refresh=refresh,
        section=DIAGNOSTIC_COMMANDS_SECTION,
        schema=DIAGNOSTIC_COMMANDS_SCHEMA,
    )


def build_diagnostic_file_reads_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    refresh: bool = False,
) -> DiagnosticSnapshotReport:
    """Return the latest file-read snapshot, optionally recomputing it first."""

    return _build_source_log_snapshot_report(
        db_path=db_path,
        include_archived=include_archived,
        refresh=refresh,
        section=DIAGNOSTIC_FILE_READS_SECTION,
        schema=DIAGNOSTIC_FILE_READS_SCHEMA,
    )


def build_diagnostic_file_modifications_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    refresh: bool = False,
) -> DiagnosticSnapshotReport:
    """Return the latest file-modification snapshot, optionally recomputing it first."""

    return _build_source_log_snapshot_report(
        db_path=db_path,
        include_archived=include_archived,
        refresh=refresh,
        section=DIAGNOSTIC_FILE_MODIFICATIONS_SECTION,
        schema=DIAGNOSTIC_FILE_MODIFICATIONS_SCHEMA,
    )


def build_diagnostic_read_productivity_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    refresh: bool = False,
) -> DiagnosticSnapshotReport:
    """Return the latest read-productivity snapshot, optionally recomputing it first."""

    return _build_source_log_snapshot_report(
        db_path=db_path,
        include_archived=include_archived,
        refresh=refresh,
        section=DIAGNOSTIC_READ_PRODUCTIVITY_SECTION,
        schema=DIAGNOSTIC_READ_PRODUCTIVITY_SCHEMA,
    )


def build_diagnostic_concentration_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    refresh: bool = False,
) -> DiagnosticSnapshotReport:
    """Return the latest concentration snapshot, optionally recomputing it first."""

    if refresh:
        return DiagnosticSnapshotReport(
            _refresh_concentration_snapshot(
                db_path=db_path,
                include_archived=include_archived,
            )
        )
    return DiagnosticSnapshotReport(
        _source_log_snapshot_payload(
            db_path=db_path,
            include_archived=include_archived,
            section=DIAGNOSTIC_CONCENTRATION_SECTION,
            schema=DIAGNOSTIC_CONCENTRATION_SCHEMA,
        )
    )


def refresh_diagnostic_overview_snapshot(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Recompute and persist the aggregate overview diagnostic snapshot."""

    history_scope = _history_scope(include_archived)
    computed_at = _utc_now()
    overview, source_logs_scanned = _compute_overview(
        db_path=db_path,
        include_archived=include_archived,
    )
    snapshot = _snapshot_metadata(
        computed_at=computed_at,
        history_scope=history_scope,
        source_logs_scanned=source_logs_scanned,
        usage_rows_scanned=int(overview["usage_rows"]),
    )
    payload = _ready_payload(
        schema=DIAGNOSTIC_OVERVIEW_SCHEMA,
        section=DIAGNOSTIC_OVERVIEW_SECTION,
        snapshot=snapshot,
        refreshed=True,
        overview=overview,
    )
    upsert_diagnostic_snapshot(
        db_path=db_path,
        section=DIAGNOSTIC_OVERVIEW_SECTION,
        history_scope=history_scope,
        payload=payload,
        computed_at=computed_at,
        source_logs_scanned=source_logs_scanned,
        usage_rows_scanned=int(overview["usage_rows"]),
        raw_content_included=False,
    )
    return payload


def refresh_diagnostic_snapshots(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Recompute and persist all dashboard diagnostic snapshots.

    Source-log-derived sections share one analyzer pass so the dashboard refresh
    button does not rescan the same logs once per panel.
    """

    history_scope = _history_scope(include_archived)
    overview_payload = refresh_diagnostic_overview_snapshot(
        db_path=db_path,
        include_archived=include_archived,
    )
    computed_at = _utc_now()
    analysis = analyze_indexed_source_logs(db_path=db_path, include_archived=include_archived)
    sections = {
        DIAGNOSTIC_TOOL_OUTPUT_SECTION: DIAGNOSTIC_TOOL_OUTPUT_SCHEMA,
        DIAGNOSTIC_COMMANDS_SECTION: DIAGNOSTIC_COMMANDS_SCHEMA,
        DIAGNOSTIC_FILE_READS_SECTION: DIAGNOSTIC_FILE_READS_SCHEMA,
        DIAGNOSTIC_FILE_MODIFICATIONS_SECTION: DIAGNOSTIC_FILE_MODIFICATIONS_SCHEMA,
        DIAGNOSTIC_READ_PRODUCTIVITY_SECTION: DIAGNOSTIC_READ_PRODUCTIVITY_SCHEMA,
    }
    source_payloads = {
        section: _persist_source_log_snapshot(
            db_path=db_path,
            section=section,
            schema=schema,
            history_scope=history_scope,
            computed_at=computed_at,
            analysis=analysis,
        )
        for section, schema in sections.items()
    }
    concentration_payload = _refresh_concentration_snapshot(
        db_path=db_path,
        include_archived=include_archived,
    )
    return {
        "schema": DIAGNOSTIC_BATCH_REFRESH_SCHEMA,
        "status": "ready",
        "refreshed": True,
        "raw_context_included": False,
        "history_scope": history_scope,
        "sections": {
            "overview": overview_payload,
            "toolOutput": source_payloads[DIAGNOSTIC_TOOL_OUTPUT_SECTION],
            "commands": source_payloads[DIAGNOSTIC_COMMANDS_SECTION],
            "fileReads": source_payloads[DIAGNOSTIC_FILE_READS_SECTION],
            "fileModifications": source_payloads[DIAGNOSTIC_FILE_MODIFICATIONS_SECTION],
            "readProductivity": source_payloads[DIAGNOSTIC_READ_PRODUCTIVITY_SECTION],
            "concentration": concentration_payload,
        },
        "meta": {
            "source_log_analysis_passes": 1,
            "source_logs_scanned": analysis["meta"]["source_logs_scanned"],
            "usage_rows_scanned": analysis["meta"]["usage_rows_scanned"],
        },
    }


def _build_source_log_snapshot_report(
    *,
    db_path: Path,
    include_archived: bool,
    refresh: bool,
    section: str,
    schema: str,
) -> DiagnosticSnapshotReport:
    if refresh:
        return DiagnosticSnapshotReport(
            _refresh_source_log_snapshot(
                db_path=db_path,
                include_archived=include_archived,
                section=section,
                schema=schema,
            )
        )
    return DiagnosticSnapshotReport(
        _source_log_snapshot_payload(
            db_path=db_path,
            include_archived=include_archived,
            section=section,
            schema=schema,
        )
    )


def _refresh_source_log_snapshot(
    *,
    db_path: Path,
    include_archived: bool,
    section: str,
    schema: str,
) -> dict[str, Any]:
    history_scope = _history_scope(include_archived)
    computed_at = _utc_now()
    analysis = analyze_indexed_source_logs(db_path=db_path, include_archived=include_archived)
    return _persist_source_log_snapshot(
        db_path=db_path,
        section=section,
        schema=schema,
        history_scope=history_scope,
        computed_at=computed_at,
        analysis=analysis,
    )


def _persist_source_log_snapshot(
    *,
    db_path: Path,
    section: str,
    schema: str,
    history_scope: str,
    computed_at: str,
    analysis: dict[str, Any],
) -> dict[str, Any]:
    snapshot = _snapshot_metadata(
        computed_at=computed_at,
        history_scope=history_scope,
        source_logs_scanned=analysis["meta"]["source_logs_scanned"],
        usage_rows_scanned=analysis["meta"]["usage_rows_scanned"],
    )
    if section == DIAGNOSTIC_TOOL_OUTPUT_SECTION:
        payload = _ready_payload(
            schema=schema,
            section=section,
            snapshot=snapshot,
            refreshed=True,
            summary=analysis["tool_output"]["summary"],
            functions=analysis["tool_output"]["functions"],
            command_roots=analysis["tool_output"]["command_roots"],
            missing_reasons=analysis["tool_output"]["missing_reasons"],
        )
    elif section == DIAGNOSTIC_COMMANDS_SECTION:
        payload = _ready_payload(
            schema=schema,
            section=section,
            snapshot=snapshot,
            refreshed=True,
            summary=analysis["commands"]["summary"],
            commands=analysis["commands"]["commands"],
        )
    elif section == DIAGNOSTIC_FILE_READS_SECTION:
        payload = _ready_payload(
            schema=schema,
            section=section,
            snapshot=snapshot,
            refreshed=True,
            summary=analysis["file_reads"]["summary"],
            by_reader=analysis["file_reads"]["by_reader"],
            top_paths=analysis["file_reads"]["top_paths"],
            largest_read_commands=analysis["file_reads"]["largest_read_commands"],
            path_privacy=analysis["file_reads"]["path_privacy"],
        )
    elif section == DIAGNOSTIC_FILE_MODIFICATIONS_SECTION:
        payload = _ready_payload(
            schema=schema,
            section=section,
            snapshot=snapshot,
            refreshed=True,
            summary=analysis["file_modifications"]["summary"],
            top_paths=analysis["file_modifications"]["top_paths"],
            by_extension=analysis["file_modifications"]["by_extension"],
            largest_events=analysis["file_modifications"]["largest_events"],
            path_privacy=analysis["file_modifications"]["path_privacy"],
        )
    elif section == DIAGNOSTIC_READ_PRODUCTIVITY_SECTION:
        payload = _ready_payload(
            schema=schema,
            section=section,
            snapshot=snapshot,
            refreshed=True,
            summary=analysis["read_productivity"]["summary"],
            by_reader=analysis["read_productivity"]["by_reader"],
            top_modified_paths=analysis["read_productivity"]["top_modified_paths"],
            path_privacy=analysis["read_productivity"]["path_privacy"],
        )
    else:
        raise ValueError(f"unknown diagnostic snapshot section: {section}")
    upsert_diagnostic_snapshot(
        db_path=db_path,
        section=section,
        history_scope=history_scope,
        payload=payload,
        computed_at=computed_at,
        source_logs_scanned=analysis["meta"]["source_logs_scanned"],
        usage_rows_scanned=analysis["meta"]["usage_rows_scanned"],
        raw_content_included=False,
    )
    return payload


def _refresh_concentration_snapshot(
    *,
    db_path: Path,
    include_archived: bool,
) -> dict[str, Any]:
    history_scope = _history_scope(include_archived)
    computed_at = _utc_now()
    analysis = compute_concentration(db_path=db_path, include_archived=include_archived)
    snapshot = _snapshot_metadata(
        computed_at=computed_at,
        history_scope=history_scope,
        source_logs_scanned=analysis["meta"]["source_logs_scanned"],
        usage_rows_scanned=analysis["summary"]["usage_rows"],
    )
    payload = _ready_payload(
        schema=DIAGNOSTIC_CONCENTRATION_SCHEMA,
        section=DIAGNOSTIC_CONCENTRATION_SECTION,
        snapshot=snapshot,
        refreshed=True,
        summary=analysis["summary"],
        metrics=analysis["metrics"],
        dimensions=analysis["dimensions"],
        largest_impact_rows=analysis["largest_impact_rows"],
        privacy=analysis["privacy"],
    )
    upsert_diagnostic_snapshot(
        db_path=db_path,
        section=DIAGNOSTIC_CONCENTRATION_SECTION,
        history_scope=history_scope,
        payload=payload,
        computed_at=computed_at,
        source_logs_scanned=analysis["meta"]["source_logs_scanned"],
        usage_rows_scanned=analysis["summary"]["usage_rows"],
        raw_content_included=False,
    )
    return payload


def diagnostic_overview_payload(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Return the latest persisted overview snapshot without recomputing it."""

    history_scope = _history_scope(include_archived)
    stored = query_diagnostic_snapshot(
        db_path=db_path,
        section=DIAGNOSTIC_OVERVIEW_SECTION,
        history_scope=history_scope,
    )
    if stored is None:
        return _missing_payload(history_scope=history_scope)
    payload = dict(stored["payload"])
    payload["status"] = "ready"
    payload["refreshed"] = False
    payload["snapshot"] = _snapshot_metadata(
        computed_at=str(stored["computed_at"]),
        history_scope=str(stored["history_scope"]),
        source_logs_scanned=int(stored["source_logs_scanned"]),
        usage_rows_scanned=int(stored["usage_rows_scanned"]),
    )
    payload["raw_context_included"] = bool(stored["raw_content_included"])
    return payload


def _source_log_snapshot_payload(
    *,
    db_path: Path,
    include_archived: bool,
    section: str,
    schema: str,
) -> dict[str, Any]:
    history_scope = _history_scope(include_archived)
    stored = query_diagnostic_snapshot(
        db_path=db_path,
        section=section,
        history_scope=history_scope,
    )
    if stored is None:
        return _missing_payload(schema=schema, section=section, history_scope=history_scope)
    payload = dict(stored["payload"])
    payload["status"] = "ready"
    payload["refreshed"] = False
    payload["snapshot"] = _snapshot_metadata(
        computed_at=str(stored["computed_at"]),
        history_scope=str(stored["history_scope"]),
        source_logs_scanned=int(stored["source_logs_scanned"]),
        usage_rows_scanned=int(stored["usage_rows_scanned"]),
    )
    payload["raw_context_included"] = bool(stored["raw_content_included"])
    return payload


def _compute_overview(
    *,
    db_path: Path,
    include_archived: bool,
) -> tuple[dict[str, Any], int]:
    usage_where = "" if include_archived else "WHERE is_archived = 0"
    source_where = "" if include_archived else "WHERE is_archived = 0"
    with connect(db_path) as conn:
        init_db(conn)
        usage_row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS usage_rows,
                COUNT(DISTINCT session_id) AS session_count,
                COUNT(DISTINCT thread_key) AS thread_count,
                COUNT(DISTINCT model) AS model_count,
                MIN(event_timestamp) AS first_event_timestamp,
                MAX(event_timestamp) AS latest_event_timestamp,
                coalesce(SUM(input_tokens), 0) AS input_tokens,
                coalesce(SUM(cached_input_tokens), 0) AS cached_input_tokens,
                coalesce(SUM(uncached_input_tokens), 0) AS uncached_input_tokens,
                coalesce(SUM(output_tokens), 0) AS output_tokens,
                coalesce(SUM(reasoning_output_tokens), 0) AS reasoning_output_tokens,
                coalesce(SUM(total_tokens), 0) AS total_tokens,
                AVG(cache_ratio) AS avg_cache_ratio
            FROM usage_events
            {usage_where}
            """
        ).fetchone()
        facts_row = conn.execute(
            f"""
            SELECT COUNT(*) AS diagnostic_fact_rows
            FROM call_diagnostic_facts AS facts
            JOIN usage_events ON usage_events.record_id = facts.record_id
            {usage_where}
            """
        ).fetchone()
        source_row = conn.execute(
            f"SELECT COUNT(*) AS source_logs_scanned FROM source_files {source_where}"
        ).fetchone()
    input_tokens = _int_value(usage_row["input_tokens"])
    cached_input_tokens = _int_value(usage_row["cached_input_tokens"])
    overview = {
        "usage_rows": _int_value(usage_row["usage_rows"]),
        "session_count": _int_value(usage_row["session_count"]),
        "thread_count": _int_value(usage_row["thread_count"]),
        "model_count": _int_value(usage_row["model_count"]),
        "first_event_timestamp": usage_row["first_event_timestamp"],
        "latest_event_timestamp": usage_row["latest_event_timestamp"],
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "uncached_input_tokens": _int_value(usage_row["uncached_input_tokens"]),
        "output_tokens": _int_value(usage_row["output_tokens"]),
        "reasoning_output_tokens": _int_value(usage_row["reasoning_output_tokens"]),
        "total_tokens": _int_value(usage_row["total_tokens"]),
        "cache_ratio": cached_input_tokens / input_tokens if input_tokens else 0.0,
        "avg_call_cache_ratio": float(usage_row["avg_cache_ratio"] or 0),
        "diagnostic_fact_rows": _int_value(facts_row["diagnostic_fact_rows"]),
    }
    return overview, _int_value(source_row["source_logs_scanned"])


def _ready_payload(
    *,
    schema: str,
    section: str,
    snapshot: dict[str, Any],
    refreshed: bool,
    **sections: object,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": schema,
        "section": section,
        "status": "ready",
        "refreshed": refreshed,
        "raw_context_included": False,
        "snapshot": snapshot,
        "notes": list(DIAGNOSTIC_SNAPSHOT_NOTES),
    }
    payload.update(sections)
    return payload


def _missing_payload(
    *,
    history_scope: str,
    schema: str = DIAGNOSTIC_OVERVIEW_SCHEMA,
    section: str = DIAGNOSTIC_OVERVIEW_SECTION,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": schema,
        "section": section,
        "status": "missing",
        "refreshed": False,
        "raw_context_included": False,
        "snapshot": None,
        "history_scope": history_scope,
        "notes": list(DIAGNOSTIC_SNAPSHOT_NOTES),
    }
    if section == DIAGNOSTIC_OVERVIEW_SECTION:
        payload["overview"] = None
    elif section == DIAGNOSTIC_TOOL_OUTPUT_SECTION:
        payload["summary"] = None
        payload["functions"] = []
        payload["command_roots"] = []
        payload["missing_reasons"] = []
    elif section == DIAGNOSTIC_COMMANDS_SECTION:
        payload["summary"] = None
        payload["commands"] = []
    elif section == DIAGNOSTIC_FILE_READS_SECTION:
        payload["summary"] = None
        payload["by_reader"] = []
        payload["top_paths"] = []
        payload["largest_read_commands"] = []
        payload["path_privacy"] = path_privacy_metadata()
    elif section == DIAGNOSTIC_FILE_MODIFICATIONS_SECTION:
        payload["summary"] = None
        payload["top_paths"] = []
        payload["by_extension"] = []
        payload["largest_events"] = []
        payload["path_privacy"] = path_privacy_metadata()
    elif section == DIAGNOSTIC_READ_PRODUCTIVITY_SECTION:
        payload["summary"] = None
        payload["by_reader"] = []
        payload["top_modified_paths"] = []
        payload["path_privacy"] = path_privacy_metadata()
    elif section == DIAGNOSTIC_CONCENTRATION_SECTION:
        payload["summary"] = None
        payload["metrics"] = []
        payload["dimensions"] = []
        payload["largest_impact_rows"] = []
        payload["privacy"] = concentration_privacy_metadata()
    return payload


def _snapshot_metadata(
    *,
    computed_at: str,
    history_scope: str,
    source_logs_scanned: int,
    usage_rows_scanned: int,
) -> dict[str, Any]:
    return {
        "computed_at": computed_at,
        "history_scope": history_scope,
        "source_logs_scanned": int(source_logs_scanned),
        "usage_rows_scanned": int(usage_rows_scanned),
        "raw_content_included": False,
    }


def _history_scope(include_archived: bool) -> str:
    return DIAGNOSTIC_HISTORY_ALL if include_archived else DIAGNOSTIC_HISTORY_ACTIVE


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _int_value(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value:
        return int(value)
    return 0
