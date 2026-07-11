from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.core.json_contracts import validate_json_payload_contract
from codex_usage_tracker.reports.visualization import (
    build_visualization_result,
    suggest_visualizations,
)


def test_visualization_suggestions_rank_question_cues() -> None:
    allowance = suggest_visualizations("Did my weekly allowance change?", scope="allowance")
    waste = suggest_visualizations("Show large low-output token waste")

    assert allowance["summary"]["top_kind"] == "allowance_change"
    assert waste["summary"]["top_kind"] == "token_waste"
    assert allowance["includes_raw_fragments"] is False
    assert validate_json_payload_contract(allowance) == []


def test_token_waste_visualization_is_bounded_and_table_equivalent() -> None:
    result = build_visualization_result(
        "token_waste",
        _report_pack(),
        evidence_limit=1,
    )

    assert result["schema"] == "codex-usage-tracker-visualization-result-v1"
    assert result["visualization"]["schema"] == "codex-usage-visualization/v1"
    assert result["visualization"]["scope"]["rowCount"] == 1
    assert result["visualization"]["data"]["rows"] == result["evidence"]["rows"]
    assert result["visualization"]["data"]["rows"][0]["record_id"] == "call-large"
    assert result["artifact_rendering"]["supported_formats"] == ["spec"]
    assert result["includes_raw_fragments"] is False
    assert validate_json_payload_contract(result) == []


def test_token_waste_visualization_matches_dashboard_contract_fixture() -> None:
    result = build_visualization_result("token_waste", _report_pack(), evidence_limit=1)
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "frontend/dashboard/src/visualization/fixtures/mcpTokenWasteSpec.json"
    )

    assert result["visualization"] == json.loads(fixture_path.read_text(encoding="utf-8"))


def test_allowance_visualization_preserves_backend_grade_and_candidate() -> None:
    result = build_visualization_result(
        "allowance_change",
        _allowance_diagnostics(),
        include_archived=True,
    )
    spec = result["visualization"]

    assert result["narrative"]["headline"] == "possible regime change"
    assert spec["scope"]["historyScope"] == "all"
    assert spec["data"]["rows"][0]["capacity_proxy"] == 800.0
    assert spec["annotations"][0]["id"] == "candidate-regime-shift"


def test_thread_call_visualization_uses_chronological_call_shape() -> None:
    result = build_visualization_result(
        "thread_lifecycle",
        {
            "schema": "codex-usage-tracker-calls-v1",
            "rows": [
                {
                    "record_id": "call-1",
                    "call_started_at": "2026-07-01T10:00:00Z",
                    "input_tokens": 100,
                    "cached_input_tokens": 75,
                    "output_tokens": 20,
                    "total_tokens": 120,
                    "estimated_cost_usd": 0.01,
                }
            ],
        },
    )

    spec = result["visualization"]
    assert spec["title"] == "Thread call lifecycle"
    assert spec["axes"]["x"]["type"] == "time"
    assert spec["data"]["rows"][0]["cached_percent"] == 75.0


def test_visualization_contract_rejects_unknown_kind_and_unbounded_evidence() -> None:
    try:
        build_visualization_result("unknown", _report_pack())
    except ValueError as exc:
        assert "kind must be one of" in str(exc)
    else:
        raise AssertionError("unknown visualization kind should fail")

    try:
        build_visualization_result("token_waste", _report_pack(), evidence_limit=51)
    except ValueError as exc:
        assert "between 1 and 50" in str(exc)
    else:
        raise AssertionError("unbounded visualization evidence should fail")


def _report_pack() -> dict[str, object]:
    return {
        "schema": "codex-usage-tracker-reports-pack-v1",
        "generated_at": "2026-07-01T12:00:00Z",
        "evidence": {
            "usage-drain-model": {
                "rows": [
                    {
                        "record_id": "call-small",
                        "thread_name": "small-thread",
                        "input_tokens": 100,
                        "cached_input_tokens": 80,
                        "output_tokens": 40,
                        "total_tokens": 140,
                        "estimated_cost_usd": 0.01,
                        "usage_credits": 0.25,
                    },
                    {
                        "record_id": "call-large",
                        "thread_name": "large-thread",
                        "input_tokens": 10_000,
                        "cached_input_tokens": 500,
                        "output_tokens": 25,
                        "total_tokens": 10_025,
                        "estimated_cost_usd": 0.75,
                        "usage_credits": 18.75,
                    },
                ]
            }
        },
    }


def _allowance_diagnostics() -> dict[str, object]:
    return {
        "schema": "codex-usage-tracker-allowance-diagnostics-v1",
        "generated_at": "2026-07-01T12:00:00Z",
        "summary": {"primary_evidence_grade": "possible_regime_change"},
        "windows": [
            {
                "window_kind": "weekly",
                "evidence_grade": "possible_regime_change",
                "spans": [
                    {
                        "record_id": "span-1",
                        "end_observed_at": "2026-06-30T12:00:00Z",
                        "credits_per_percent": 8.0,
                        "delta_usage_percent": 2.5,
                        "estimated_usage_credits": 20.0,
                    }
                ],
            }
        ],
        "change_candidates": [
            {
                "candidate_start_observed_at": "2026-06-30T12:00:00Z",
                "statistical_evidence": {"public_claim_ready": False},
            }
        ],
    }
