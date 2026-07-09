"""CLI rendering for persisted diagnostic snapshot reports."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from codex_usage_tracker.diagnostics.snapshot_constants import (
    DIAGNOSTIC_COMMANDS_SECTION,
    DIAGNOSTIC_CONCENTRATION_SECTION,
    DIAGNOSTIC_FILE_MODIFICATIONS_SECTION,
    DIAGNOSTIC_FILE_READS_SECTION,
    DIAGNOSTIC_GIT_INTERACTIONS_SECTION,
    DIAGNOSTIC_GUIDED_SUMMARY_SECTION,
    DIAGNOSTIC_READ_PRODUCTIVITY_SECTION,
    DIAGNOSTIC_TOOL_OUTPUT_SECTION,
    DIAGNOSTIC_USAGE_DRAIN_SECTION,
)
from codex_usage_tracker.diagnostics.snapshot_events import READ_PRODUCTIVITY_NOTE, int_value


@dataclass(frozen=True)
class DiagnosticSnapshotReport:
    """Resolved diagnostic snapshot payload for CLI and API surfaces."""

    payload: dict[str, Any]

    def render(self) -> str:
        if self.payload.get("status") != "ready":
            return _unavailable_snapshot_message(self.payload)
        section = self.payload.get("section")
        return self._section_renderers().get(section, self._render_overview)()

    def _section_renderers(self) -> dict[object, Callable[[], str]]:
        return {
            DIAGNOSTIC_TOOL_OUTPUT_SECTION: self._render_tool_output,
            DIAGNOSTIC_COMMANDS_SECTION: self._render_commands,
            DIAGNOSTIC_GIT_INTERACTIONS_SECTION: self._render_git_interactions,
            DIAGNOSTIC_FILE_READS_SECTION: self._render_file_reads,
            DIAGNOSTIC_FILE_MODIFICATIONS_SECTION: self._render_file_modifications,
            DIAGNOSTIC_READ_PRODUCTIVITY_SECTION: self._render_read_productivity,
            DIAGNOSTIC_CONCENTRATION_SECTION: self._render_concentration,
            DIAGNOSTIC_GUIDED_SUMMARY_SECTION: self._render_guided_summary,
            DIAGNOSTIC_USAGE_DRAIN_SECTION: self._render_usage_drain,
        }

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

    def _render_file_modifications(self) -> str:
        snapshot = self.payload.get("snapshot") or {}
        summary = self.payload.get("summary") or {}
        return "\n".join(
            [
                "Diagnostic file-modifications snapshot",
                f"Computed: {snapshot.get('computed_at')}",
                f"History scope: {snapshot.get('history_scope')}",
                f"Modification events: {_int_text(summary.get('modification_events'))}",
                f"Modified path events: {_int_text(summary.get('modified_path_events'))}",
                f"Unique paths modified: {_int_text(summary.get('unique_paths_modified'))}",
                f"Largest event path count: {_int_text(summary.get('largest_event_path_count'))}",
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

    def _render_guided_summary(self) -> str:
        snapshot = self.payload.get("snapshot") or {}
        summary = self.payload.get("summary") or {}
        drivers = self.payload.get("drivers") or []
        signals = self.payload.get("signals") or []
        lines = [
            "Diagnostic guided-summary snapshot",
            f"Computed: {snapshot.get('computed_at')}",
            f"History scope: {snapshot.get('history_scope')}",
            f"Usage rows: {_int_text(summary.get('usage_rows'))}",
            f"Total tokens: {_int_text(summary.get('total_tokens'))}",
            f"Cache ratio: {_pct_text(summary.get('cache_ratio'))}",
            "Top drivers:",
        ]
        lines.extend(_driver_lines(drivers))
        lines.append("Signals:")
        lines.extend(_signal_lines(signals))
        return "\n".join(lines)

    def _render_usage_drain(self) -> str:
        snapshot = self.payload.get("snapshot") or {}
        summary = self.payload.get("summary") or {}
        curves = self.payload.get("thread_cost_curves") or {}
        return "\n".join(
            [
                "Diagnostic usage-drain snapshot",
                f"Computed: {snapshot.get('computed_at')}",
                f"History scope: {snapshot.get('history_scope')}",
                f"Usage rows: {_int_text(summary.get('usage_rows'))}",
                f"Positive usage spans: {_int_text(summary.get('positive_usage_spans'))}",
                f"Estimated cost: ${_float_text(summary.get('estimated_cost_usd'))}",
                f"Usage credits: {_float_text(summary.get('usage_credits'))}",
                f"Threads shown: {_int_text(curves.get('shown_threads'))}",
                f"Top thread cost share: {_pct_text(summary.get('top_thread_cost_share'))}",
                f"Best predictive model: {summary.get('best_predictive_model') or 'n/a'}",
            ]
        )


def _int_text(value: object) -> str:
    return f"{int_value(value):,}"


def _driver_lines(drivers: object) -> list[str]:
    rows = drivers if isinstance(drivers, list) else []
    if not rows:
        return ["- No driver rows available."]
    return [
        (
            f"- {row.get('title')}: {row.get('label')} "
            f"({_driver_value(row)}, share {_pct_text(row.get('share'))})"
        )
        for row in rows
        if isinstance(row, dict)
    ] or ["- No driver rows available."]


def _signal_lines(signals: object) -> list[str]:
    rows = signals if isinstance(signals, list) else []
    if not rows:
        return ["- No signals available."]
    return [
        f"- {row.get('title')}: {row.get('finding')}" for row in rows if isinstance(row, dict)
    ] or ["- No signals available."]


def _driver_value(row: dict[str, Any]) -> str:
    value = row.get("value")
    if row.get("value_kind") == "ratio":
        return _pct_text(value)
    return _int_text(value)


def _unavailable_snapshot_message(payload: dict[str, Any]) -> str:
    section = str(payload.get("section") or "snapshot")
    return f"No diagnostic {section} snapshot. Run diagnostics {section} --refresh first."


def _pct_text(value: object) -> str:
    try:
        ratio = float(value) if isinstance(value, int | float | str) and value != "" else 0.0
    except (TypeError, ValueError):
        ratio = 0.0
    return f"{ratio:.1%}"


def _float_text(value: object) -> str:
    try:
        number = float(value) if isinstance(value, int | float | str) and value != "" else 0.0
    except (TypeError, ValueError):
        number = 0.0
    return f"{number:,.2f}"
