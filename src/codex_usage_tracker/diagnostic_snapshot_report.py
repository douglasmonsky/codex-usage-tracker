"""CLI rendering for persisted diagnostic snapshot reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from codex_usage_tracker.diagnostic_snapshot_constants import (
    DIAGNOSTIC_COMMANDS_SECTION,
    DIAGNOSTIC_CONCENTRATION_SECTION,
    DIAGNOSTIC_FILE_READS_SECTION,
    DIAGNOSTIC_GIT_INTERACTIONS_SECTION,
    DIAGNOSTIC_READ_PRODUCTIVITY_SECTION,
    DIAGNOSTIC_TOOL_OUTPUT_SECTION,
)
from codex_usage_tracker.diagnostic_snapshot_events import READ_PRODUCTIVITY_NOTE, int_value


@dataclass(frozen=True)
class DiagnosticSnapshotReport:
    """Resolved diagnostic snapshot payload for CLI and API surfaces."""

    payload: dict[str, Any]

    def render(self) -> str:
        if self.payload.get("status") != "ready":
            section = str(self.payload.get("section") or "snapshot")
            return f"No diagnostic {section} snapshot. Run diagnostics {section} --refresh first."
        section = self.payload.get("section")
        if section == DIAGNOSTIC_TOOL_OUTPUT_SECTION:
            return self._render_tool_output()
        if section == DIAGNOSTIC_COMMANDS_SECTION:
            return self._render_commands()
        if section == DIAGNOSTIC_GIT_INTERACTIONS_SECTION:
            return self._render_git_interactions()
        if section == DIAGNOSTIC_FILE_READS_SECTION:
            return self._render_file_reads()
        if section == DIAGNOSTIC_READ_PRODUCTIVITY_SECTION:
            return self._render_read_productivity()
        if section == DIAGNOSTIC_CONCENTRATION_SECTION:
            return self._render_concentration()
        return self._render_overview()

    def _render_overview(self) -> str:
        snapshot = self.payload.get("snapshot") or {}
        overview = self.payload.get("overview") or {}
        return "\n".join(
            [
                "Diagnostic overview snapshot",
                f"Computed: {snapshot.get('computed_at')}",
                f"History scope: {snapshot.get('history_scope')}",
                f"Usage rows: {_int_text(overview.get('usage_rows'))}",
                f"Total tokens: {_int_text(overview.get('total_tokens'))}",
                f"Cached input: {_int_text(overview.get('cached_input_tokens'))}",
                f"Uncached input: {_int_text(overview.get('uncached_input_tokens'))}",
                f"Cache ratio: {_pct_text(overview.get('cache_ratio'))}",
            ]
        )

    def _render_tool_output(self) -> str:
        snapshot = self.payload.get("snapshot") or {}
        summary = self.payload.get("summary") or {}
        return "\n".join(
            [
                "Diagnostic tool-output snapshot",
                f"Computed: {snapshot.get('computed_at')}",
                f"History scope: {snapshot.get('history_scope')}",
                f"Function calls: {_int_text(summary.get('function_calls'))}",
                f"Function outputs: {_int_text(summary.get('function_outputs'))}",
                f"Outputs with Original token count: {_int_text(summary.get('outputs_with_original_token_count'))}",
                f"Terminal output tokens: {_int_text(summary.get('original_token_sum'))}",
            ]
        )

    def _render_commands(self) -> str:
        snapshot = self.payload.get("snapshot") or {}
        summary = self.payload.get("summary") or {}
        return "\n".join(
            [
                "Diagnostic commands snapshot",
                f"Computed: {snapshot.get('computed_at')}",
                f"History scope: {snapshot.get('history_scope')}",
                f"Shell calls: {_int_text(summary.get('shell_function_calls'))}",
                f"Command roots: {_int_text(summary.get('command_root_count'))}",
                f"Missing command text: {_int_text(summary.get('missing_command'))}",
            ]
        )

    def _render_git_interactions(self) -> str:
        snapshot = self.payload.get("snapshot") or {}
        summary = self.payload.get("summary") or {}
        return "\n".join(
            [
                "Diagnostic git-interactions snapshot",
                f"Computed: {snapshot.get('computed_at')}",
                f"History scope: {snapshot.get('history_scope')}",
                f"Git/GitHub shell calls: {_int_text(summary.get('git_shell_calls'))}",
                f"Git commands: {_int_text(summary.get('git_command_calls'))}",
                f"GitHub CLI commands: {_int_text(summary.get('github_cli_calls'))}",
                f"Interactions with Original token count: {_int_text(summary.get('interactions_with_original_token_count'))}",
                f"Terminal output tokens: {_int_text(summary.get('original_token_sum'))}",
            ]
        )

    def _render_file_reads(self) -> str:
        snapshot = self.payload.get("snapshot") or {}
        summary = self.payload.get("summary") or {}
        return "\n".join(
            [
                "Diagnostic file-reads snapshot",
                f"Computed: {snapshot.get('computed_at')}",
                f"History scope: {snapshot.get('history_scope')}",
                f"Read commands: {_int_text(summary.get('read_commands'))}",
                f"Read events: {_int_text(summary.get('read_events'))}",
                f"Allocated output tokens: {_int_text(summary.get('allocated_output_token_sum'))}",
                f"Missing output counts: {_int_text(summary.get('read_events_missing_output_count'))}",
            ]
        )

    def _render_read_productivity(self) -> str:
        snapshot = self.payload.get("snapshot") or {}
        summary = self.payload.get("summary") or {}
        return "\n".join(
            [
                "Diagnostic read-productivity snapshot",
                f"Computed: {snapshot.get('computed_at')}",
                f"History scope: {snapshot.get('history_scope')}",
                f"Read events: {_int_text(summary.get('read_events'))}",
                f"Read events modified later: {_int_text(summary.get('read_events_modified_later'))}",
                f"Read-to-modify rate: {_pct_text(summary.get('read_events_modified_later_pct'))}",
                READ_PRODUCTIVITY_NOTE,
            ]
        )

    def _render_concentration(self) -> str:
        snapshot = self.payload.get("snapshot") or {}
        summary = self.payload.get("summary") or {}
        return "\n".join(
            [
                "Diagnostic concentration snapshot",
                f"Computed: {snapshot.get('computed_at')}",
                f"History scope: {snapshot.get('history_scope')}",
                f"Usage rows: {_int_text(summary.get('usage_rows'))}",
                f"Total tokens: {_int_text(summary.get('total_tokens'))}",
                f"Dimensions: {_int_text(summary.get('dimension_count'))}",
            ]
        )


def _int_text(value: object) -> str:
    return f"{int_value(value):,}"


def _pct_text(value: object) -> str:
    try:
        ratio = float(value) if isinstance(value, int | float | str) and value != "" else 0.0
    except (TypeError, ValueError):
        ratio = 0.0
    return f"{ratio:.1%}"
