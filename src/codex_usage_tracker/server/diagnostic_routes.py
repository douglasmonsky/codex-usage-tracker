"""Diagnostic route methods for the local dashboard server."""

from __future__ import annotations

import threading
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from codex_usage_tracker.diagnostics.snapshots import (
    build_diagnostic_commands_report,
    build_diagnostic_concentration_report,
    build_diagnostic_file_modifications_report,
    build_diagnostic_file_reads_report,
    build_diagnostic_git_interactions_report,
    build_diagnostic_guided_summary_report,
    build_diagnostic_overview_report,
    build_diagnostic_read_productivity_report,
    build_diagnostic_tool_output_report,
)
from codex_usage_tracker.server.analysis_jobs import AnalysisJobRegistry
from codex_usage_tracker.server.diagnostic_facts import (
    handle_diagnostics_fact_calls_request,
    handle_diagnostics_facts_request,
    handle_diagnostics_summary_request,
)
from codex_usage_tracker.server.diagnostic_jobs import (
    handle_diagnostic_job_start_request,
    handle_diagnostic_job_status_request,
)
from codex_usage_tracker.server.diagnostic_snapshots import (
    diagnostic_refresh_payload,
    diagnostic_snapshot_payload,
    handle_diagnostic_snapshot_request,
    handle_usage_drain_snapshot_request,
    usage_drain_snapshot_payload,
)

_DIAGNOSTIC_REFRESH_AUTH_ERROR = "Valid API token is required for diagnostic refresh"

_DIAGNOSTIC_SNAPSHOT_REPORTS: dict[str, tuple[Any, str]] = {
    "overview": (build_diagnostic_overview_report, "diagnostic overview"),
    "tool-output": (build_diagnostic_tool_output_report, "diagnostic tool output"),
    "commands": (build_diagnostic_commands_report, "diagnostic commands"),
    "git-interactions": (
        build_diagnostic_git_interactions_report,
        "diagnostic git interactions",
    ),
    "file-reads": (build_diagnostic_file_reads_report, "diagnostic file reads"),
    "file-modifications": (
        build_diagnostic_file_modifications_report,
        "diagnostic file modifications",
    ),
    "read-productivity": (
        build_diagnostic_read_productivity_report,
        "diagnostic read productivity",
    ),
    "concentration": (build_diagnostic_concentration_report, "diagnostic concentration"),
    "guided-summary": (
        build_diagnostic_guided_summary_report,
        "diagnostic guided summary",
    ),
}


class DiagnosticRouteMixin:
    """Diagnostic route adapters for ``_UsageDashboardHandler``."""

    if TYPE_CHECKING:
        path: str
        _db_path: Path
        _pricing_path: Path
        _allowance_path: Path
        _rate_card_path: Path
        _include_archived: bool
        _privacy_mode: str
        _refresh_lock: threading.Lock
        _analysis_jobs: AnalysisJobRegistry

        def _has_valid_api_token(self, params: dict[str, list[str]]) -> bool: ...

        def _send_error(
            self,
            status: HTTPStatus,
            message: str,
            **extra: object,
        ) -> None: ...

        def _send_exception(self, prefix: str, exc: BaseException) -> None: ...

        def _send_json(
            self,
            status: HTTPStatus,
            payload: dict[str, object],
        ) -> None: ...

    def _handle_diagnostics_summary(self, query: str) -> None:
        handle_diagnostics_summary_request(
            query,
            db_path=self._db_path,
            include_archived_default=self._include_archived,
            send_error=self._send_error,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _handle_diagnostics_facts(
        self,
        query: str,
        *,
        fact_type: str | None = None,
        fact_group: str | None = None,
    ) -> None:
        handle_diagnostics_facts_request(
            query,
            db_path=self._db_path,
            include_archived_default=self._include_archived,
            request_path=urlparse(self.path).path,
            fact_type=fact_type,
            fact_group=fact_group,
            send_error=self._send_error,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _handle_diagnostics_fact_calls(self, query: str) -> None:
        handle_diagnostics_fact_calls_request(
            query,
            db_path=self._db_path,
            include_archived_default=self._include_archived,
            privacy_mode=self._privacy_mode,
            send_error=self._send_error,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _handle_diagnostics_overview(self, query: str) -> None:
        self._handle_named_diagnostic_snapshot(query, "overview", refresh=False)

    def _handle_diagnostics_refresh(self, query: str) -> None:
        def refresh_all(include_archived: bool, progress: Any) -> dict[str, object]:
            payload = diagnostic_refresh_payload(
                "",
                db_path=self._db_path,
                pricing_path=self._pricing_path,
                allowance_path=self._allowance_path,
                rate_card_path=self._rate_card_path,
                include_archived_default=include_archived,
                refresh_lock=self._refresh_lock,
                progress_callback=progress,
            )
            sections = payload.get("sections")
            refreshed = list(sections) if isinstance(sections, dict) else []
            return {"refreshed_sections": refreshed}

        self._start_diagnostic_job(query, "all", 10, refresh_all)

    def _handle_diagnostics_refresh_status(self, query: str) -> None:
        handle_diagnostic_job_status_request(
            query,
            registry=self._analysis_jobs,
            has_valid_api_token=self._has_valid_api_token,
            send_error=self._send_error,
            send_json=self._send_json,
        )

    def _handle_diagnostics_overview_refresh(self, query: str) -> None:
        self._handle_named_diagnostic_snapshot(query, "overview", refresh=True)

    def _handle_diagnostics_tool_output(self, query: str) -> None:
        self._handle_named_diagnostic_snapshot(query, "tool-output", refresh=False)

    def _handle_diagnostics_tool_output_refresh(self, query: str) -> None:
        self._handle_named_diagnostic_snapshot(query, "tool-output", refresh=True)

    def _handle_diagnostics_commands(self, query: str) -> None:
        self._handle_named_diagnostic_snapshot(query, "commands", refresh=False)

    def _handle_diagnostics_commands_refresh(self, query: str) -> None:
        self._handle_named_diagnostic_snapshot(query, "commands", refresh=True)

    def _handle_diagnostics_git_interactions(self, query: str) -> None:
        self._handle_named_diagnostic_snapshot(query, "git-interactions", refresh=False)

    def _handle_diagnostics_git_interactions_refresh(self, query: str) -> None:
        self._handle_named_diagnostic_snapshot(query, "git-interactions", refresh=True)

    def _handle_diagnostics_file_reads(self, query: str) -> None:
        self._handle_named_diagnostic_snapshot(query, "file-reads", refresh=False)

    def _handle_diagnostics_file_reads_refresh(self, query: str) -> None:
        self._handle_named_diagnostic_snapshot(query, "file-reads", refresh=True)

    def _handle_diagnostics_file_modifications(self, query: str) -> None:
        self._handle_named_diagnostic_snapshot(query, "file-modifications", refresh=False)

    def _handle_diagnostics_file_modifications_refresh(self, query: str) -> None:
        self._handle_named_diagnostic_snapshot(query, "file-modifications", refresh=True)

    def _handle_diagnostics_read_productivity(self, query: str) -> None:
        self._handle_named_diagnostic_snapshot(query, "read-productivity", refresh=False)

    def _handle_diagnostics_read_productivity_refresh(self, query: str) -> None:
        self._handle_named_diagnostic_snapshot(query, "read-productivity", refresh=True)

    def _handle_diagnostics_concentration(self, query: str) -> None:
        self._handle_named_diagnostic_snapshot(query, "concentration", refresh=False)

    def _handle_diagnostics_concentration_refresh(self, query: str) -> None:
        self._handle_named_diagnostic_snapshot(query, "concentration", refresh=True)

    def _handle_diagnostics_guided_summary(self, query: str) -> None:
        self._handle_named_diagnostic_snapshot(query, "guided-summary", refresh=False)

    def _handle_diagnostics_guided_summary_refresh(self, query: str) -> None:
        self._handle_named_diagnostic_snapshot(query, "guided-summary", refresh=True)

    def _handle_diagnostics_usage_drain(self, query: str) -> None:
        self._handle_diagnostic_usage_drain_snapshot(query, refresh=False)

    def _handle_diagnostics_usage_drain_refresh(self, query: str) -> None:
        self._handle_diagnostic_usage_drain_snapshot(query, refresh=True)

    def _handle_diagnostic_usage_drain_snapshot(
        self,
        query: str,
        *,
        refresh: bool,
    ) -> None:
        if refresh:
            self._start_usage_drain_refresh(query)
            return
        handle_usage_drain_snapshot_request(
            query,
            db_path=self._db_path,
            pricing_path=self._pricing_path,
            allowance_path=self._allowance_path,
            rate_card_path=self._rate_card_path,
            include_archived_default=self._include_archived,
            refresh=refresh,
            refresh_lock=self._refresh_lock,
            reject_missing_refresh_token=self._reject_missing_diagnostic_refresh_token,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _handle_named_diagnostic_snapshot(
        self,
        query: str,
        key: str,
        *,
        refresh: bool,
    ) -> None:
        build_report, label = _DIAGNOSTIC_SNAPSHOT_REPORTS[key]
        if refresh:
            self._start_named_diagnostic_refresh(query, key, build_report)
            return
        self._handle_diagnostic_snapshot(
            query,
            build_report=build_report,
            refresh=refresh,
            label=label,
        )

    def _start_named_diagnostic_refresh(
        self,
        query: str,
        key: str,
        build_report: Any,
    ) -> None:
        def refresh_one(include_archived: bool, progress: Any) -> dict[str, object]:
            progress(
                stage="refreshing_snapshot",
                completed_units=0,
                total_units=1,
                current_unit=key,
            )
            diagnostic_snapshot_payload(
                db_path=self._db_path,
                include_archived=include_archived,
                refresh=True,
                refresh_lock=self._refresh_lock,
                build_report=build_report,
            )
            return {"refreshed_sections": [key]}

        self._start_diagnostic_job(query, key, 1, refresh_one)

    def _start_usage_drain_refresh(self, query: str) -> None:
        def refresh_one(include_archived: bool, progress: Any) -> dict[str, object]:
            progress(
                stage="refreshing_snapshot",
                completed_units=0,
                total_units=1,
                current_unit="usage-drain",
            )
            usage_drain_snapshot_payload(
                db_path=self._db_path,
                pricing_path=self._pricing_path,
                allowance_path=self._allowance_path,
                rate_card_path=self._rate_card_path,
                include_archived=include_archived,
                refresh=True,
                refresh_lock=self._refresh_lock,
            )
            return {"refreshed_sections": ["usage-drain"]}

        self._start_diagnostic_job(query, "usage-drain", 1, refresh_one)

    def _start_diagnostic_job(
        self,
        query: str,
        job_name: str,
        total_units: int,
        work: Any,
    ) -> None:
        handle_diagnostic_job_start_request(
            query,
            db_path=self._db_path,
            job_name=job_name,
            total_units=total_units,
            work=work,
            registry=self._analysis_jobs,
            has_valid_api_token=self._has_valid_api_token,
            send_error=self._send_error,
            send_json=self._send_json,
            include_archived_default=self._include_archived,
        )

    def _handle_diagnostic_snapshot(
        self,
        query: str,
        *,
        build_report: Any,
        refresh: bool,
        label: str,
    ) -> None:
        handle_diagnostic_snapshot_request(
            query,
            db_path=self._db_path,
            include_archived_default=self._include_archived,
            refresh=refresh,
            refresh_lock=self._refresh_lock,
            build_report=build_report,
            label=label,
            reject_missing_refresh_token=self._reject_missing_diagnostic_refresh_token,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _reject_missing_diagnostic_refresh_token(
        self,
        params: dict[str, list[str]],
    ) -> bool:
        if self._has_valid_api_token(params):
            return False
        self._send_error(HTTPStatus.FORBIDDEN, _DIAGNOSTIC_REFRESH_AUTH_ERROR)
        return True
