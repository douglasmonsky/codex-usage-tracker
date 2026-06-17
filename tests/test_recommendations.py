from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.lifecycle_recommendations import (
    LIFECYCLE_RECOMMENDATIONS_SCHEMA_ID,
    lifecycle_recommendations_for_rows,
    lifecycle_recommendations_payload,
)
from codex_usage_tracker.recommendations import (
    DEFAULT_THRESHOLDS,
    action_recommendations,
    annotate_rows_with_recommendations,
    load_threshold_config,
    write_threshold_template,
)


def test_recommendations_explain_aggregate_usage_flags() -> None:
    row = {
        "pricing_model": None,
        "input_tokens": 30_000,
        "uncached_input_tokens": 25_000,
        "cached_input_tokens": 1_000,
        "cache_ratio": 0.02,
        "output_tokens": 80,
        "reasoning_output_ratio": 0.80,
        "total_tokens": 30_080,
        "context_window_percent": 0.70,
        "cumulative_total_tokens": 250_000,
        "thread_source": "subagent",
        "parent_session_id": "parent",
    }

    recommendations = action_recommendations(row)
    annotated = annotate_rows_with_recommendations([row])[0]

    assert [recommendation["key"] for recommendation in recommendations] == [
        "pricing-gap",
        "context-bloat",
        "low-cache",
        "low-output",
        "large-thread",
        "subagent-attribution",
    ]
    assert all("score" in recommendation for recommendation in recommendations)
    assert annotated["primary_signal"] == "pricing-gap"
    assert annotated["primary_recommendation"]["key"] == "pricing-gap"
    assert annotated["secondary_signals"] == [
        "context-bloat",
        "low-cache",
        "low-output",
        "large-thread",
        "subagent-attribution",
    ]
    assert annotated["recommendation_score"] > 0
    assert annotated["recommended_action"] == recommendations[0]["action"]
    assert annotated["recommended_action_key"] == recommendations[0]["action_key"]
    assert len(annotated["flag_explanations"]) == len(recommendations)
    assert annotated["flag_explanation_keys"] == [
        recommendation["why_key"] for recommendation in recommendations
    ]
    for recommendation in recommendations:
        prefix = recommendation["key"].replace("-", "_")
        assert recommendation["title_key"] == f"recommendation.{prefix}.title"
        assert recommendation["why_key"] == f"recommendation.{prefix}.why"
        assert recommendation["action_key"] == f"recommendation.{prefix}.action"


def test_threshold_template_and_overrides(tmp_path: Path) -> None:
    path = tmp_path / "thresholds.json"

    written = write_threshold_template(path)
    config = load_threshold_config(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["low_cache_ratio"] = 0.42
    payload["unknown"] = 999
    path.write_text(json.dumps(payload), encoding="utf-8")
    overridden = load_threshold_config(path)

    assert written == path
    assert config.loaded is True
    assert config.thresholds == DEFAULT_THRESHOLDS
    assert {
        "cold_resume_idle_minutes",
        "cold_resume_max_cache_ratio",
        "cold_resume_min_input_tokens",
        "cold_resume_min_uncached_tokens",
        "cold_resume_huge_uncached_tokens",
        "cold_resume_huge_max_cache_ratio",
        "cold_resume_cluster_suppression_minutes",
    }.issubset(payload)
    assert overridden.thresholds["low_cache_ratio"] == 0.42
    assert "unknown" not in overridden.thresholds


def test_lifecycle_recommendations_cover_core_lifecycle_actions() -> None:
    rows = [
        _lifecycle_row(
            "continue",
            cache_ratio=0.91,
            context_window_percent=0.20,
            receipt_event_count=2,
            receipt_confidences="high",
        ),
        _lifecycle_row(
            "summarize",
            cache_ratio=0.88,
            context_window_percent=0.55,
            receipt_event_count=1,
            receipt_confidences="medium",
        ),
        _lifecycle_row(
            "fresh",
            cache_ratio=0.10,
            context_window_percent=0.72,
            uncached_input_tokens=40_000,
        ),
        _lifecycle_row(
            "reasoning",
            reasoning_output_tokens=800,
            output_tokens=1000,
            reasoning_output_ratio=0.80,
            receipt_event_count=0,
        ),
        _lifecycle_row(
            "delegated",
            thread_source="subagent",
            parent_session_id="parent",
        ),
    ]

    recommendations = lifecycle_recommendations_for_rows(rows)
    keys = {row["recommendation_key"] for row in recommendations}

    assert {
        "continue_thread",
        "summarize_or_compact",
        "start_fresh",
        "lower_reasoning",
        "inspect_delegated_work",
    }.issubset(keys)
    assert all(row["raw_context_included"] is False for row in recommendations)
    assert all("source_chips" in row for row in recommendations)


def test_lifecycle_low_evidence_uses_usage_impact_and_receipts() -> None:
    recommendations = lifecycle_recommendations_for_rows(
        [
            _lifecycle_row(
                "low-evidence",
                total_tokens=80_000,
                uncached_input_tokens=70_000,
                primary_usage_percent=0.25,
                secondary_usage_percent=0.03,
                receipt_event_count=0,
            )
        ]
    )

    assert recommendations[0]["recommendation_key"] == "inspect_low_evidence"
    assert "usage_impact" in recommendations[0]["source_chips"]
    assert recommendations[0]["metrics"]["primary_usage_percent"] == 0.25


def test_lifecycle_payload_contract_excludes_raw_context() -> None:
    rows = lifecycle_recommendations_for_rows(
        [_lifecycle_row("payload", thread_name="SECRET RAW PROMPT")]
    )
    payload = lifecycle_recommendations_payload(rows, filters={"scope": None}, limit=10)

    assert payload["schema"] == LIFECYCLE_RECOMMENDATIONS_SCHEMA_ID
    assert payload["raw_context_included"] is False
    assert "SECRET RAW PROMPT" not in json.dumps(payload)


def _lifecycle_row(record_id: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "record_id": record_id,
        "thread_key": "thread:Lifecycle",
        "thread_name": "Lifecycle",
        "session_id": "session-lifecycle",
        "event_timestamp": "2026-06-15T12:00:00Z",
        "thread_source": "user",
        "parent_session_id": None,
        "subagent_type": None,
        "agent_role": None,
        "cache_ratio": 0.50,
        "context_window_percent": 0.20,
        "uncached_input_tokens": 1_000,
        "output_tokens": 200,
        "reasoning_output_tokens": 20,
        "reasoning_output_ratio": 0.10,
        "total_tokens": 2_000,
        "receipt_event_count": 0,
        "receipt_confidences": "",
        "primary_usage_percent": None,
        "secondary_usage_percent": None,
    }
    row.update(overrides)
    return row
