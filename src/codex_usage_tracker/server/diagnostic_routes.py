"""Diagnostic route methods for the local dashboard server."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any
from urllib.parse import urlparse

from codex_usage_tracker.diagnostics.snapshots import (
    build_diagnostic_commands_report,
    build_diagnostic_concentration_report,
    build_diagnostic_file_modifications_report,
    build_diagnostic_file_reads_report,
    build_diagnostic_git_interactions_report,
    build_diagnostic_overview_report,
    build_diagnostic_read_productivity_report,
    build_diagnostic_tool_output_report,
)
from codex_usage_tracker.server.diagnostic_facts import (
    handle_diagnostics_fact_calls_request,
    handle_diagnostics_facts_request,
    handle_diagnostics_summary_request,
)
from codex_usage_tracker.server.diagnostic_snapshots import (
    handle_diagnostic_refresh_request,
    handle_diagnostic_snapshot_request,
    handle_usage_drain_snapshot_request,
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
}


class DiagnosticRouteMixin:
    """Diagnostic route adapters for ``_UsageDashboardHandler``."""

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
        handle_diagnostic_refresh_request(
            query,
            db_path=self._db_path,
            pricing_path=self._pricing_path,
            allowance_path=self._allowance_path,
            rate_card_path=self._rate_card_path,
            include_archived_default=self._include_archived,
            refresh_lock=self._refresh_lock,
            reject_missing_refresh_token=self._reject_missing_diagnostic_refresh_token,
            send_exception=self._send_exception,
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
        self._handle_diagnostic_snapshot(
            query,
            build_report=build_report,
            refresh=refresh,
            label=label,
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
