from __future__ import annotations

from codex_usage_tracker.reports import agentic, api


def test_report_api_reexports_agentic_family() -> None:
    assert (
        api.build_investigation_suggestions_report is agentic.build_investigation_suggestions_report
    )
    assert api.build_agentic_investigation_report is agentic.build_agentic_investigation_report
