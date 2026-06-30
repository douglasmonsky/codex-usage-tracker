from __future__ import annotations

import pytest

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
from codex_usage_tracker.diagnostics.snapshot_report import DiagnosticSnapshotReport


@pytest.mark.parametrize(
    ("section", "heading"),
    [
        (DIAGNOSTIC_TOOL_OUTPUT_SECTION, "Diagnostic tool-output snapshot"),
        (DIAGNOSTIC_COMMANDS_SECTION, "Diagnostic commands snapshot"),
        (DIAGNOSTIC_GIT_INTERACTIONS_SECTION, "Diagnostic git-interactions snapshot"),
        (DIAGNOSTIC_FILE_READS_SECTION, "Diagnostic file-reads snapshot"),
        (
            DIAGNOSTIC_FILE_MODIFICATIONS_SECTION,
            "Diagnostic file-modifications snapshot",
        ),
        (DIAGNOSTIC_READ_PRODUCTIVITY_SECTION, "Diagnostic read-productivity snapshot"),
        (DIAGNOSTIC_CONCENTRATION_SECTION, "Diagnostic concentration snapshot"),
        (DIAGNOSTIC_GUIDED_SUMMARY_SECTION, "Diagnostic guided-summary snapshot"),
        (DIAGNOSTIC_USAGE_DRAIN_SECTION, "Diagnostic usage-drain snapshot"),
    ],
)
def test_diagnostic_snapshot_report_dispatches_sections(
    section: str,
    heading: str,
) -> None:
    rendered = DiagnosticSnapshotReport(
        {
            "status": "ready",
            "section": section,
            "snapshot": {"computed_at": "2026-06-29T00:00:00Z", "history_scope": "all"},
            "summary": {},
            "thread_cost_curves": {},
        }
    ).render()

    assert rendered.splitlines()[0] == heading


def test_diagnostic_snapshot_report_defaults_to_overview() -> None:
    rendered = DiagnosticSnapshotReport(
        {
            "status": "ready",
            "snapshot": {"computed_at": "2026-06-29T00:00:00Z", "history_scope": "all"},
            "overview": {},
        }
    ).render()

    assert rendered.splitlines()[0] == "Diagnostic overview snapshot"


def test_diagnostic_snapshot_report_renders_unavailable_snapshot() -> None:
    rendered = DiagnosticSnapshotReport(
        {"status": "missing", "section": DIAGNOSTIC_TOOL_OUTPUT_SECTION}
    ).render()

    assert rendered == (
        "No diagnostic tool-output snapshot. "
        "Run diagnostics tool-output --refresh first."
    )
