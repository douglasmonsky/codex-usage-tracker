from codex_usage_tracker.diagnostics import api, snapshots
from codex_usage_tracker.diagnostics.doctor_checks import find_project_root
from codex_usage_tracker.diagnostics.snapshot_overview import diagnostic_overview_payload


def test_diagnostic_facades_preserve_public_exports() -> None:
    assert api.find_project_root is find_project_root
    assert snapshots.diagnostic_overview_payload is diagnostic_overview_payload
