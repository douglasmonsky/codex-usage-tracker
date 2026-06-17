"""Aggregate-only recommendations and review thresholds."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_usage_tracker.paths import DEFAULT_THRESHOLDS_PATH

DEFAULT_THRESHOLDS: dict[str, float] = {
    "low_cache_ratio": 0.30,
    "high_context_percent": 0.60,
    "elevated_context_percent": 0.50,
    "high_uncached_input_tokens": 10_000,
    "large_cumulative_tokens": 200_000,
    "high_reasoning_ratio": 0.75,
    "reasoning_min_output_tokens": 100,
    "expensive_low_output_total_tokens": 20_000,
    "low_output_tokens": 100,
    "high_cost_usd": 1.00,
    "cold_resume_idle_minutes": 45,
    "cold_resume_max_cache_ratio": 0.10,
    "cold_resume_min_input_tokens": 25_000,
    "cold_resume_min_uncached_tokens": 20_000,
    "cold_resume_huge_uncached_tokens": 100_000,
    "cold_resume_huge_max_cache_ratio": 0.15,
    "cold_resume_cluster_suppression_minutes": 10,
}

SEVERITY_POINTS = {
    "high": 80,
    "medium": 45,
    "review": 20,
}


@dataclass(frozen=True)
class ThresholdConfig:
    path: Path
    thresholds: dict[str, float]
    loaded: bool = False
    error: str | None = None


def load_threshold_config(path: Path = DEFAULT_THRESHOLDS_PATH) -> ThresholdConfig:
    """Load user-overridden recommendation thresholds."""

    path = path.expanduser()
    thresholds = dict(DEFAULT_THRESHOLDS)
    if not path.exists():
        return ThresholdConfig(path=path, thresholds=thresholds)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ThresholdConfig(path=path, thresholds=thresholds, loaded=False, error=str(exc))
    if not isinstance(payload, dict):
        return ThresholdConfig(
            path=path,
            thresholds=thresholds,
            loaded=False,
            error="Threshold config must be a JSON object.",
        )
    for key, value in payload.items():
        if key in thresholds and isinstance(value, int | float) and not isinstance(value, bool):
            thresholds[key] = float(value)
    return ThresholdConfig(path=path, thresholds=thresholds, loaded=True)


def write_threshold_template(path: Path = DEFAULT_THRESHOLDS_PATH, force: bool = False) -> Path:
    """Write a local template for recommendation thresholds."""

    path = path.expanduser()
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists. Use --force to replace it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(DEFAULT_THRESHOLDS, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def annotate_rows_with_recommendations(
    rows: list[dict[str, Any]],
    thresholds: ThresholdConfig | None = None,
) -> list[dict[str, Any]]:
    """Attach aggregate-only action recommendations to dashboard rows."""

    config = thresholds or load_threshold_config()
    annotated: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        recommendations = action_recommendations(copy, config.thresholds)
        copy["action_recommendations"] = recommendations
        copy["primary_recommendation"] = recommendations[0] if recommendations else None
        copy["secondary_recommendations"] = recommendations[1:]
        copy["primary_signal"] = recommendations[0]["key"] if recommendations else None
        copy["secondary_signals"] = [
            recommendation["key"] for recommendation in recommendations[1:]
        ]
        copy["recommendation_score"] = recommendation_severity_score(copy, recommendations)
        copy["recommended_action"] = (
            recommendations[0]["action"]
            if recommendations
            else "No aggregate action is flagged; continue monitoring usage patterns."
        )
        copy["recommended_action_key"] = (
            recommendations[0]["action_key"]
            if recommendations
            else "recommendation.none.action"
        )
        copy["flag_explanations"] = [recommendation["why"] for recommendation in recommendations]
        copy["flag_explanation_keys"] = [recommendation["why_key"] for recommendation in recommendations]
        annotated.append(copy)
    return annotated


def action_recommendations(
    row: dict[str, Any],
    thresholds: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Return ranked recommendations for one aggregate usage row."""

    limits = thresholds or DEFAULT_THRESHOLDS
    recommendations: list[dict[str, Any]] = []
    total_tokens = _number(row.get("total_tokens"))
    output_tokens = _number(row.get("output_tokens"))
    uncached_input = _number(row.get("uncached_input_tokens"))
    input_tokens = _number(row.get("input_tokens"))
    cache_ratio = _number(row.get("cache_ratio"))
    context = _number(row.get("context_window_percent"))
    reasoning = _number(row.get("reasoning_output_ratio"))
    cumulative = _number(row.get("cumulative_total_tokens"))
    cost = row.get("estimated_cost_usd")

    if not row.get("pricing_model"):
        recommendations.append(
            _recommendation(
                "pricing-gap",
                "review",
                "Pricing gap",
                "This model call has no configured price, so cost totals understate visible usage.",
                "Update pricing or add a local alias before trusting cost totals.",
            )
        )
    elif row.get("pricing_estimated"):
        recommendations.append(
            _recommendation(
                "estimated-pricing",
                "review",
                "Estimated pricing",
                "This cost uses an inferred model mapping rather than a direct pricing row.",
                "Review pricing coverage and pin or override the model rate if this call matters.",
            )
        )
    if isinstance(cost, int | float) and cost >= limits["high_cost_usd"]:
        recommendations.append(
            _recommendation(
                "high-cost",
                "high",
                "High estimated cost",
                "This call crossed the configured high-cost threshold.",
                "Open the thread timeline and inspect the preceding turn before continuing.",
            )
        )
    if context >= limits["high_context_percent"]:
        recommendations.append(
            _recommendation(
                "context-bloat",
                "high",
                "High context pressure",
                "This call is using a large share of the model context window.",
                "Consider starting a fresh Codex thread if older context is no longer relevant.",
            )
        )
    elif context >= limits["elevated_context_percent"]:
        recommendations.append(
            _recommendation(
                "elevated-context",
                "medium",
                "Elevated context pressure",
                "Context use is elevated and may become costly in later turns.",
                "Check whether the thread can be narrowed before adding more work.",
            )
        )
    if input_tokens > 0 and cache_ratio < limits["low_cache_ratio"] and uncached_input >= limits["high_uncached_input_tokens"]:
        recommendations.append(
            _recommendation(
                "low-cache",
                "medium",
                "Low cache reuse",
                "Fresh uncached input is high while cache reuse is low.",
                "Check whether files, tool output, or broad context were reintroduced unnecessarily.",
            )
        )
    if reasoning >= limits["high_reasoning_ratio"] and output_tokens >= limits["reasoning_min_output_tokens"]:
        recommendations.append(
            _recommendation(
                "reasoning-spike",
                "medium",
                "High reasoning share",
                "Reasoning output dominates visible output for this call.",
                "Review whether this task needs the selected reasoning effort.",
            )
        )
    if total_tokens >= limits["expensive_low_output_total_tokens"] and output_tokens <= limits["low_output_tokens"]:
        recommendations.append(
            _recommendation(
                "low-output",
                "medium",
                "Large low-output call",
                "The call consumed many tokens but produced little output.",
                "Inspect aggregate context first; load raw context only if the cause is unclear.",
            )
        )
    if cumulative >= limits["large_cumulative_tokens"]:
        recommendations.append(
            _recommendation(
                "large-thread",
                "medium",
                "Large cumulative thread",
                "The session cumulative total is high enough to make later turns expensive.",
                "Prefer a new thread for unrelated follow-up work.",
            )
        )
    if row.get("thread_source") == "subagent" or row.get("parent_session_id"):
        recommendations.append(
            _recommendation(
                "subagent-attribution",
                "review",
                "Subagent attribution",
                "This call is attached to delegated work and may explain parent-thread growth.",
                "Compare direct calls with attached subagent or review calls before changing workflow.",
            )
        )
    return recommendations


def recommendation_severity_score(
    row: dict[str, Any],
    recommendations: list[dict[str, Any]] | None = None,
) -> float:
    """Return a stable aggregate severity score for recommendation ranking."""

    recs = recommendations if recommendations is not None else action_recommendations(row)
    if not recs:
        return 0.0
    base = sum(SEVERITY_POINTS.get(str(rec.get("severity")), 0) for rec in recs)
    cost = min(_number(row.get("estimated_cost_usd")) * 25, 60)
    credits = min(_number(row.get("usage_credits")) * 2.5, 80)
    context = min(_number(row.get("context_window_percent")) * 60, 60)
    uncached = min(_number(row.get("uncached_input_tokens")) / 500, 50)
    cumulative = min(_number(row.get("cumulative_total_tokens")) / 10_000, 50)
    return round(base + cost + credits + context + uncached + cumulative, 2)


def _recommendation(
    key: str,
    severity: str,
    title: str,
    why: str,
    action: str,
) -> dict[str, Any]:
    key_prefix = f"recommendation.{key.replace('-', '_')}"
    return {
        "key": key,
        "severity": severity,
        "score": SEVERITY_POINTS.get(severity, 0),
        "title": title,
        "title_key": f"{key_prefix}.title",
        "why": why,
        "why_key": f"{key_prefix}.why",
        "action": action,
        "action_key": f"{key_prefix}.action",
    }


def _number(value: object) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0
