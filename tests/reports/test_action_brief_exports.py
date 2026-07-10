from __future__ import annotations

from codex_usage_tracker.reports import action_brief, api


def test_report_api_reexports_action_brief_family() -> None:
    assert api.build_action_brief_report is action_brief.build_action_brief_report
