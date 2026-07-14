"""On-demand aggregate diagnostic report snapshots."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_RATE_CARD_PATH,
)
from codex_usage_tracker.diagnostics.guided_summary import refresh_guided_summary_snapshot
from codex_usage_tracker.diagnostics.snapshot_analysis import analyze_indexed_source_logs
from codex_usage_tracker.diagnostics.snapshot_concentration import compute_concentration
from codex_usage_tracker.diagnostics.snapshot_constants import (
    DIAGNOSTIC_BATCH_REFRESH_SCHEMA,
    DIAGNOSTIC_COMMANDS_SCHEMA,
    DIAGNOSTIC_COMMANDS_SECTION,
    DIAGNOSTIC_CONCENTRATION_SCHEMA,
    DIAGNOSTIC_CONCENTRATION_SECTION,
    DIAGNOSTIC_FILE_MODIFICATIONS_SCHEMA,
    DIAGNOSTIC_FILE_MODIFICATIONS_SECTION,
    DIAGNOSTIC_FILE_READS_SCHEMA,
    DIAGNOSTIC_FILE_READS_SECTION,
    DIAGNOSTIC_GIT_INTERACTIONS_SCHEMA,
    DIAGNOSTIC_GIT_INTERACTIONS_SECTION,
    DIAGNOSTIC_GUIDED_SUMMARY_SCHEMA,
    DIAGNOSTIC_GUIDED_SUMMARY_SECTION,
    DIAGNOSTIC_OVERVIEW_SCHEMA,
    DIAGNOSTIC_OVERVIEW_SECTION,
    DIAGNOSTIC_READ_PRODUCTIVITY_SCHEMA,
    DIAGNOSTIC_READ_PRODUCTIVITY_SECTION,
    DIAGNOSTIC_TOOL_OUTPUT_SCHEMA,
    DIAGNOSTIC_TOOL_OUTPUT_SECTION,
    DIAGNOSTIC_USAGE_DRAIN_SCHEMA,
    DIAGNOSTIC_USAGE_DRAIN_SECTION,
)
from codex_usage_tracker.diagnostics.snapshot_overview import (
    _compute_overview,
)
from codex_usage_tracker.diagnostics.snapshot_overview import (
    diagnostic_overview_payload as diagnostic_overview_payload,
)
from codex_usage_tracker.diagnostics.snapshot_payloads import (
    history_scope as history_scope_label,
)
from codex_usage_tracker.diagnostics.snapshot_payloads import (
    ready_payload,
    snapshot_metadata,
    utc_now,
)
from codex_usage_tracker.diagnostics.snapshot_progress import (
    DiagnosticProgressCallback,
    emit_refresh_progress,
)
from codex_usage_tracker.diagnostics.snapshot_report import DiagnosticSnapshotReport
from codex_usage_tracker.diagnostics.snapshot_source_logs import (
    build_source_log_snapshot_report,
    persist_source_log_snapshot,
    source_log_snapshot_payload,
)
from codex_usage_tracker.store.api import (
    upsert_diagnostic_snapshot,
)
from codex_usage_tracker.usage_drain.reports import build_usage_drain_dashboard_report


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

    return build_source_log_snapshot_report(
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

    return build_source_log_snapshot_report(
        db_path=db_path,
        include_archived=include_archived,
        refresh=refresh,
        section=DIAGNOSTIC_COMMANDS_SECTION,
        schema=DIAGNOSTIC_COMMANDS_SCHEMA,
    )


def build_diagnostic_git_interactions_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    refresh: bool = False,
) -> DiagnosticSnapshotReport:
    """Return the latest Git interaction snapshot, optionally recomputing it first."""

    return build_source_log_snapshot_report(
        db_path=db_path,
        include_archived=include_archived,
        refresh=refresh,
        section=DIAGNOSTIC_GIT_INTERACTIONS_SECTION,
        schema=DIAGNOSTIC_GIT_INTERACTIONS_SCHEMA,
    )


def build_diagnostic_file_reads_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    refresh: bool = False,
) -> DiagnosticSnapshotReport:
    """Return the latest file-read snapshot, optionally recomputing it first."""

    return build_source_log_snapshot_report(
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

    return build_source_log_snapshot_report(
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

    return build_source_log_snapshot_report(
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
        source_log_snapshot_payload(
            db_path=db_path,
            include_archived=include_archived,
            section=DIAGNOSTIC_CONCENTRATION_SECTION,
            schema=DIAGNOSTIC_CONCENTRATION_SCHEMA,
        )
    )


def build_diagnostic_guided_summary_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    refresh: bool = False,
) -> DiagnosticSnapshotReport:
    """Return guided usage-driver summary snapshot, optionally recomputing it."""

    if refresh:
        return DiagnosticSnapshotReport(
            refresh_guided_summary_snapshot(
                db_path=db_path,
                include_archived=include_archived,
            )
        )

    return DiagnosticSnapshotReport(
        source_log_snapshot_payload(
            db_path=db_path,
            include_archived=include_archived,
            section=DIAGNOSTIC_GUIDED_SUMMARY_SECTION,
            schema=DIAGNOSTIC_GUIDED_SUMMARY_SCHEMA,
        )
    )


def build_diagnostic_usage_drain_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    include_archived: bool = False,
    refresh: bool = False,
) -> DiagnosticSnapshotReport:
    """Return the latest usage-drain snapshot, optionally recomputing it first."""

    if refresh:
        return DiagnosticSnapshotReport(
            _refresh_usage_drain_snapshot(
                db_path=db_path,
                pricing_path=pricing_path,
                allowance_path=allowance_path,
                rate_card_path=rate_card_path,
                include_archived=include_archived,
            )
        )
    return DiagnosticSnapshotReport(
        source_log_snapshot_payload(
            db_path=db_path,
            include_archived=include_archived,
            section=DIAGNOSTIC_USAGE_DRAIN_SECTION,
            schema=DIAGNOSTIC_USAGE_DRAIN_SCHEMA,
        )
    )


def refresh_diagnostic_overview_snapshot(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Recompute and persist the aggregate overview diagnostic snapshot."""

    history_scope = history_scope_label(include_archived)
    computed_at = utc_now()
    overview, source_logs_scanned = _compute_overview(
        db_path=db_path,
        include_archived=include_archived,
    )
    snapshot = snapshot_metadata(
        computed_at=computed_at,
        history_scope=history_scope,
        source_logs_scanned=source_logs_scanned,
        usage_rows_scanned=int(overview["usage_rows"]),
    )
    payload = ready_payload(
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
    pricing_path: Path = DEFAULT_PRICING_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    include_archived: bool = False,
    progress_callback: DiagnosticProgressCallback | None = None,
) -> dict[str, Any]:
    """Recompute and persist all dashboard diagnostic snapshots.

    Source-log-derived sections share one analyzer pass so the dashboard refresh
    button does not rescan the same logs once per panel.
    """

    history_scope = history_scope_label(include_archived)
    overview_payload = refresh_diagnostic_overview_snapshot(
        db_path=db_path,
        include_archived=include_archived,
    )
    emit_refresh_progress(progress_callback, 1, "overview")
    computed_at = utc_now()
    analysis = analyze_indexed_source_logs(db_path=db_path, include_archived=include_archived)
    sections = {
        DIAGNOSTIC_TOOL_OUTPUT_SECTION: DIAGNOSTIC_TOOL_OUTPUT_SCHEMA,
        DIAGNOSTIC_COMMANDS_SECTION: DIAGNOSTIC_COMMANDS_SCHEMA,
        DIAGNOSTIC_GIT_INTERACTIONS_SECTION: DIAGNOSTIC_GIT_INTERACTIONS_SCHEMA,
        DIAGNOSTIC_FILE_READS_SECTION: DIAGNOSTIC_FILE_READS_SCHEMA,
        DIAGNOSTIC_FILE_MODIFICATIONS_SECTION: DIAGNOSTIC_FILE_MODIFICATIONS_SCHEMA,
        DIAGNOSTIC_READ_PRODUCTIVITY_SECTION: DIAGNOSTIC_READ_PRODUCTIVITY_SCHEMA,
    }
    source_payloads = {}
    for completed_units, (section, schema) in enumerate(sections.items(), start=2):
        source_payloads[section] = persist_source_log_snapshot(
            db_path=db_path,
            section=section,
            schema=schema,
            history_scope=history_scope,
            computed_at=computed_at,
            analysis=analysis,
        )
        emit_refresh_progress(progress_callback, completed_units, section)
    concentration_payload = _refresh_concentration_snapshot(
        db_path=db_path,
        include_archived=include_archived,
    )
    emit_refresh_progress(progress_callback, 8, "concentration")
    guided_summary_payload = refresh_guided_summary_snapshot(
        db_path=db_path,
        include_archived=include_archived,
    )
    emit_refresh_progress(progress_callback, 9, "guided-summary")
    usage_drain_payload = _refresh_usage_drain_snapshot(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        include_archived=include_archived,
    )
    emit_refresh_progress(progress_callback, 10, "usage-drain")
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
            "gitInteractions": source_payloads[DIAGNOSTIC_GIT_INTERACTIONS_SECTION],
            "fileReads": source_payloads[DIAGNOSTIC_FILE_READS_SECTION],
            "fileModifications": source_payloads[DIAGNOSTIC_FILE_MODIFICATIONS_SECTION],
            "readProductivity": source_payloads[DIAGNOSTIC_READ_PRODUCTIVITY_SECTION],
            "concentration": concentration_payload,
            "guidedSummary": guided_summary_payload,
            "usageDrain": usage_drain_payload,
        },
        "meta": {
            "source_log_analysis_passes": 1,
            "source_logs_scanned": analysis["meta"]["source_logs_scanned"],
            "usage_rows_scanned": analysis["meta"]["usage_rows_scanned"],
        },
    }


def _refresh_concentration_snapshot(
    *,
    db_path: Path,
    include_archived: bool,
) -> dict[str, Any]:
    history_scope = history_scope_label(include_archived)
    computed_at = utc_now()
    analysis = compute_concentration(db_path=db_path, include_archived=include_archived)
    snapshot = snapshot_metadata(
        computed_at=computed_at,
        history_scope=history_scope,
        source_logs_scanned=analysis["meta"]["source_logs_scanned"],
        usage_rows_scanned=analysis["summary"]["usage_rows"],
    )
    payload = ready_payload(
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


def _refresh_usage_drain_snapshot(
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    include_archived: bool,
) -> dict[str, Any]:
    history_scope = history_scope_label(include_archived)
    computed_at = utc_now()
    analysis = build_usage_drain_dashboard_report(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        include_archived=include_archived,
    )
    overview, source_logs_scanned = _compute_overview(
        db_path=db_path,
        include_archived=include_archived,
    )
    usage_rows_scanned = int(analysis["summary"]["usage_rows"])
    snapshot = snapshot_metadata(
        computed_at=computed_at,
        history_scope=history_scope,
        source_logs_scanned=source_logs_scanned,
        usage_rows_scanned=usage_rows_scanned,
    )
    payload = ready_payload(
        schema=DIAGNOSTIC_USAGE_DRAIN_SCHEMA,
        section=DIAGNOSTIC_USAGE_DRAIN_SECTION,
        snapshot=snapshot,
        refreshed=True,
        summary=analysis["summary"],
        thread_cost_curves=analysis["thread_cost_curves"],
        time_series=analysis["time_series"],
        model_highlights=analysis["model_highlights"],
        pricing=analysis["pricing"],
    )
    payload["notes"].extend(analysis["notes"])
    upsert_diagnostic_snapshot(
        db_path=db_path,
        section=DIAGNOSTIC_USAGE_DRAIN_SECTION,
        history_scope=history_scope,
        payload=payload,
        computed_at=computed_at,
        source_logs_scanned=source_logs_scanned,
        usage_rows_scanned=usage_rows_scanned,
        raw_content_included=False,
    )
    # Keep static type checkers aware that overview is intentionally only used
    # for the source-log count returned by _compute_overview.
    _ = overview
    return payload
