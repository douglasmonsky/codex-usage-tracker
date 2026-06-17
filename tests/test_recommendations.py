from __future__ import annotations

import json
from pathlib import Path

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
