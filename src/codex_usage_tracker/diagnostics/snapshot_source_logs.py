"""Source-log diagnostic snapshot refresh and payload helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.diagnostics.snapshot_analysis import analyze_indexed_source_logs
from codex_usage_tracker.diagnostics.snapshot_constants import (
    DIAGNOSTIC_COMMANDS_SECTION,
    DIAGNOSTIC_FILE_MODIFICATIONS_SECTION,
    DIAGNOSTIC_FILE_READS_SECTION,
    DIAGNOSTIC_GIT_INTERACTIONS_SECTION,
    DIAGNOSTIC_READ_PRODUCTIVITY_SECTION,
    DIAGNOSTIC_TOOL_OUTPUT_SECTION,
)
from codex_usage_tracker.diagnostics.snapshot_payloads import (
    history_scope as history_scope_label,
)
from codex_usage_tracker.diagnostics.snapshot_payloads import (
    missing_payload,
    ready_payload,
    snapshot_metadata,
    utc_now,
)
from codex_usage_tracker.diagnostics.snapshot_report import DiagnosticSnapshotReport
from codex_usage_tracker.store.api import query_diagnostic_snapshot, upsert_diagnostic_snapshot


def build_source_log_snapshot_report(
    *,
    db_path: Path,
    include_archived: bool,
    refresh: bool,
    section: str,
    schema: str,
) -> DiagnosticSnapshotReport:
    """Return latest source-log snapshot, optionally recomputing it first."""
    if refresh:
        return DiagnosticSnapshotReport(
            refresh_source_log_snapshot(
                db_path=db_path,
                include_archived=include_archived,
                section=section,
                schema=schema,
            ),
        )
    return DiagnosticSnapshotReport(
        source_log_snapshot_payload(
            db_path=db_path,
            include_archived=include_archived,
            section=section,
            schema=schema,
        ),
    )


def refresh_source_log_snapshot(
    *,
    db_path: Path,
    include_archived: bool,
    section: str,
    schema: str,
) -> dict[str, Any]:
    """Recompute and persist one source-log diagnostic snapshot section."""
    history_scope = history_scope_label(include_archived)
    computed_at = utc_now()
    analysis = analyze_indexed_source_logs(db_path=db_path, include_archived=include_archived)
    return persist_source_log_snapshot(
        db_path=db_path,
        section=section,
        schema=schema,
        history_scope=history_scope,
        computed_at=computed_at,
        analysis=analysis,
    )


def persist_source_log_snapshot(
    *,
    db_path: Path,
    section: str,
    schema: str,
    history_scope: str,
    computed_at: str,
    analysis: dict[str, Any],
) -> dict[str, Any]:
    """Persist one source-log diagnostic snapshot section."""
    snapshot = snapshot_metadata(
        computed_at=computed_at,
        history_scope=history_scope,
        source_logs_scanned=analysis["meta"]["source_logs_scanned"],
        usage_rows_scanned=analysis["meta"]["usage_rows_scanned"],
    )
    if section == DIAGNOSTIC_TOOL_OUTPUT_SECTION:
        payload = ready_payload(
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
        payload = ready_payload(
            schema=schema,
            section=section,
            snapshot=snapshot,
            refreshed=True,
            summary=analysis["commands"]["summary"],
            commands=analysis["commands"]["commands"],
        )
    elif section == DIAGNOSTIC_GIT_INTERACTIONS_SECTION:
        payload = ready_payload(
            schema=schema,
            section=section,
            snapshot=snapshot,
            refreshed=True,
            summary=analysis["git_interactions"]["summary"],
            interactions=analysis["git_interactions"]["interactions"],
            categories=analysis["git_interactions"]["categories"],
            mutability=analysis["git_interactions"]["mutability"],
        )
    elif section == DIAGNOSTIC_FILE_READS_SECTION:
        payload = ready_payload(
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
        payload = ready_payload(
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
        payload = ready_payload(
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
        msg = f"Unsupported diagnostic snapshot section: {section}"
        raise ValueError(msg)

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


def source_log_snapshot_payload(
    *,
    db_path: Path,
    include_archived: bool,
    section: str,
    schema: str,
) -> dict[str, Any]:
    """Return latest persisted source-log snapshot without recomputing it."""
    history_scope = history_scope_label(include_archived)
    stored = query_diagnostic_snapshot(
        db_path=db_path,
        section=section,
        history_scope=history_scope,
    )
    if stored is None:
        return missing_payload(schema=schema, section=section, history_scope=history_scope)
    payload = dict(stored["payload"])
    payload["status"] = "ready"
    payload["refreshed"] = False
    payload["snapshot"] = snapshot_metadata(
        computed_at=str(stored["computed_at"]),
        history_scope=str(stored["history_scope"]),
        source_logs_scanned=int(stored["source_logs_scanned"]),
        usage_rows_scanned=int(stored["usage_rows_scanned"]),
    )
    payload["raw_context_included"] = bool(stored["raw_content_included"])
    return payload
