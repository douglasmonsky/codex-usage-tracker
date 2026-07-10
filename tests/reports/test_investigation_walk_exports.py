from __future__ import annotations

from codex_usage_tracker.reports import api, investigation_walk


def test_report_api_reexports_investigation_walk_family() -> None:
    assert api.build_investigation_walk_report is investigation_walk.build_investigation_walk_report
    assert (
        api.build_local_evidence_export_report
        is investigation_walk.build_local_evidence_export_report
    )
