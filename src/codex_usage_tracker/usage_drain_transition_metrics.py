"""Transition-risk metric helpers for usage-drain modeling."""

from __future__ import annotations

import math
from typing import Any

from codex_usage_tracker.usage_drain_feature_history import is_one_percent_delta
from codex_usage_tracker.usage_drain_state_buckets import (
    transition_risk_detail_diagnostics,
)
from codex_usage_tracker.usage_drain_utils import number, rounded


def transition_target_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    actual = [
        0 if is_one_percent_delta(number(row.get("actual"))) else 1
        for row in rows
    ]
    risk_models = transition_risk_model_names(rows)
    return {
        "n": len(rows),
        "positive_count": sum(actual),
        "positive_rate": rounded(sum(actual) / len(actual) if actual else None),
        "models": {
            model_name: binary_risk_metrics(
                actual,
                [
                    number((row.get("transition_risks") or {}).get(model_name))
                    for row in rows
                ],
            )
            for model_name in risk_models
        },
        "risk_detail_diagnostics": {
            model_name: transition_risk_detail_diagnostics(rows, model_name)
            for model_name in risk_models
            if model_name not in {"overall_prior_rate", "stable_one_percent_rule"}
        },
    }

def transition_risk_model_names(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    names: list[str] = []
    for row in rows:
        for name in (row.get("transition_risks") or {}):
            if name not in names:
                names.append(str(name))
    return names

def binary_risk_metrics(actual: list[int], scores: list[float]) -> dict[str, Any]:
    if not actual or len(actual) != len(scores):
        return {
            "n": len(actual),
            "brier": None,
            "auc": None,
            "average_precision": None,
            "precision_at_top_10pct": None,
            "recall_at_top_10pct": None,
            "top_10pct_positive_rate": None,
            "mean_score_positive": None,
            "mean_score_negative": None,
        }
    clipped_scores = [min(max(score, 0.0), 1.0) for score in scores]
    positives = [score for value, score in zip(actual, clipped_scores, strict=True) if value]
    negatives = [
        score for value, score in zip(actual, clipped_scores, strict=True) if not value
    ]
    top_count = max(1, math.ceil(len(actual) * 0.1))
    ranked = sorted(
        zip(actual, clipped_scores, strict=True),
        key=lambda item: item[1],
        reverse=True,
    )
    top = ranked[:top_count]
    positive_count = sum(actual)
    top_positive_count = sum(value for value, _score in top)
    return {
        "n": len(actual),
        "brier": rounded(
            sum((score - value) ** 2 for value, score in zip(actual, clipped_scores, strict=True))
            / len(actual)
        ),
        "auc": rounded(binary_auc(actual, clipped_scores)),
        "average_precision": rounded(average_precision(actual, clipped_scores)),
        "precision_at_top_10pct": rounded(top_positive_count / len(top)),
        "recall_at_top_10pct": rounded(
            top_positive_count / positive_count if positive_count else None
        ),
        "top_10pct_positive_rate": rounded(top_positive_count / len(top)),
        "mean_score_positive": rounded(
            sum(positives) / len(positives) if positives else None
        ),
        "mean_score_negative": rounded(
            sum(negatives) / len(negatives) if negatives else None
        ),
    }

def binary_auc(actual: list[int], scores: list[float]) -> float | None:
    positive_count = sum(actual)
    negative_count = len(actual) - positive_count
    if positive_count == 0 or negative_count == 0:
        return None
    ranked = sorted(zip(scores, actual, strict=True), key=lambda item: item[0])
    rank_sum = 0.0
    index = 0
    while index < len(ranked):
        end = index
        while end + 1 < len(ranked) and ranked[end + 1][0] == ranked[index][0]:
            end += 1
        average_rank = ((index + 1) + (end + 1)) / 2.0
        positives_in_tie = sum(value for _score, value in ranked[index : end + 1])
        rank_sum += positives_in_tie * average_rank
        index = end + 1
    return (rank_sum - (positive_count * (positive_count + 1) / 2.0)) / (
        positive_count * negative_count
    )

def average_precision(actual: list[int], scores: list[float]) -> float | None:
    positive_count = sum(actual)
    if positive_count == 0:
        return None
    ranked = sorted(
        zip(actual, scores, strict=True), key=lambda item: item[1], reverse=True
    )
    seen_positive = 0
    precision_sum = 0.0
    for rank, (value, _score) in enumerate(ranked, start=1):
        if not value:
            continue
        seen_positive += 1
        precision_sum += seen_positive / rank
    return precision_sum / positive_count
