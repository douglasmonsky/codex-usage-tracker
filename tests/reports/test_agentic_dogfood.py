from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.reports.agentic_dogfood import build_agentic_dogfood_report
from tests.store_dashboard_helpers import _make_codex_home, _write_pricing


def test_agentic_dogfood_report_writes_compact_private_artifacts(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    output_dir = tmp_path / "dogfood"

    payload = build_agentic_dogfood_report(
        codex_home=codex_home,
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
        projects_path=tmp_path / "projects.json",
        output_dir=output_dir,
        evidence_limit=2,
        privacy_mode="strict",
    )

    assert payload["schema"] == "codex-usage-tracker-agentic-dogfood-v1"
    assert payload["content_mode"] == "compact_aggregate_dogfood_summary"
    assert payload["includes_indexed_content"] is False
    assert payload["includes_raw_fragments"] is False
    assert payload["family_checks"]["old_passed"] is True
    assert payload["family_checks"]["new_passed"] is True
    assert payload["privacy_checks"]["passed"] is True
    assert payload["progress"]["percent_complete"] == 100
    assert payload["progress"]["stages"][-1]["stage"] == "write_artifacts"
    assert payload["cache"]["scope"] == "single_run_shared_reports"
    assert payload["cache"]["hypotheses"] is False
    assert payload["cache"]["deep_investigations"] is False
    assert "large_low_output" in payload["cache"]["cache_keys"]
    assert payload["old_hypotheses"][0]["status"] == "skipped_quick_mode"
    assert "action_brief" in payload["direct_reports"]
    assert payload["direct_reports"]["action_brief"]["action_count"] is not None
    assert payload["refresh"]["parsed_events"] > 0
    assert Path(payload["artifacts"]["summary_json_path"]).exists()
    assert Path(payload["artifacts"]["summary_markdown_path"]).exists()

    serialized = json.dumps(payload)
    assert "SECRET" not in serialized
    assert "raw_command" not in serialized
    assert "raw_tool_output" not in serialized
    assert "full_path" not in serialized
