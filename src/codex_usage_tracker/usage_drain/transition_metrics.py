"""Transition-risk metric helpers for usage-drain modeling."""

from __future__ import annotations

import math
from typing import Any

from codex_usage_tracker.usage_drain.feature_history import is_one_percent_delta
from codex_usage_tracker.usage_drain.grace import REGIME_GRACE_STREAK_THRESHOLD
from codex_usage_tracker.usage_drain.state_buckets import (
    TRANSITION_RISK_MODEL_SIGNATURES,
    state_bucket_transition_risk,
    transition_rate,
    transition_risk_detail_diagnostics,
)
from codex_usage_tracker.usage_drain.utils import number, rounded


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
        return _empty_binary_risk_metrics(len(actual))

    clipped_scores = _clipped_scores(scores)
    positives, negatives = _score_groups(actual, clipped_scores)
    top = _top_risk_rows(actual, clipped_scores)
    positive_count = sum(actual)
    top_positive_count = _top_positive_count(top)
    return {
        "n": len(actual),
        "brier": rounded(_brier_score(actual, clipped_scores)),
        "auc": rounded(binary_auc(actual, clipped_scores)),
        "average_precision": rounded(average_precision(actual, clipped_scores)),
        "precision_at_top_10pct": rounded(top_positive_count / len(top)),
        "recall_at_top_10pct": rounded(
            top_positive_count / positive_count if positive_count else None
        ),
        "top_10pct_positive_rate": rounded(top_positive_count / len(top)),
        "mean_score_positive": _mean_score(positives),
        "mean_score_negative": _mean_score(negatives),
    }


def _empty_binary_risk_metrics(actual_count: int) -> dict[str, Any]:
    return {
        "n": actual_count,
        "brier": None,
        "auc": None,
        "average_precision": None,
        "precision_at_top_10pct": None,
        "recall_at_top_10pct": None,
        "top_10pct_positive_rate": None,
        "mean_score_positive": None,
        "mean_score_negative": None,
    }


def _clipped_scores(scores: list[float]) -> list[float]:
    return [min(max(score, 0.0), 1.0) for score in scores]


def _score_groups(
    actual: list[int], scores: list[float]
) -> tuple[list[float], list[float]]:
    positives: list[float] = []
    negatives: list[float] = []
    for value, score in zip(actual, scores, strict=True):
        if value:
            positives.append(score)
        else:
            negatives.append(score)
    return positives, negatives


def _top_risk_rows(actual: list[int], scores: list[float]) -> list[tuple[int, float]]:
    top_count = max(1, math.ceil(len(actual) * 0.1))
    ranked = sorted(
        zip(actual, scores, strict=True), key=lambda item: item[1], reverse=True
    )
    return ranked[:top_count]


def _top_positive_count(top_rows: list[tuple[int, float]]) -> int:
    return sum(value for value, _score in top_rows)


def _brier_score(actual: list[int], scores: list[float]) -> float:
    return sum(
        (score - value) ** 2 for value, score in zip(actual, scores, strict=True)
    ) / len(actual)


def _mean_score(scores: list[float]) -> float | None:
    if not scores:
        return None
    return rounded(sum(scores) / len(scores))

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


def transition_risk_predictions(
    previous_state_rows: list[dict[str, Any]],
    state: dict[str, Any],
) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    prior_rate = transition_rate(previous_state_rows)
    risks: dict[str, float] = {
        "overall_prior_rate": prior_rate,
        "stable_one_percent_rule": (
            0.0
            if int(state.get("one_percent_streak_count") or 0)
            >= REGIME_GRACE_STREAK_THRESHOLD
            else prior_rate
        ),
    }
    details: dict[str, dict[str, Any]] = {
        "overall_prior_rate": {
            "source": "all_prior_spans",
            "support": len(previous_state_rows),
        },
        "stable_one_percent_rule": {
            "source": "long_one_percent_streak"
            if int(state.get("one_percent_streak_count") or 0)
            >= REGIME_GRACE_STREAK_THRESHOLD
            else "fallback_prior_rate",
            "support": len(previous_state_rows),
        },
    }
    for model_name, signatures in TRANSITION_RISK_MODEL_SIGNATURES.items():
        risk, detail = state_bucket_transition_risk(
            previous_state_rows,
            state,
            signatures=signatures,
            fallback_rate=prior_rate,
        )
        risks[model_name] = risk
        details[model_name] = detail
    return risks, details


def transition_risk_summary(
    rows: list[dict[str, Any]], scopes: dict[str, int]
) -> dict[str, Any]:
    target_definitions = {
        "non_one_percent_delta": (
            "Next visible positive delta is not exactly 1%, across all scoped spans."
        ),
        "break_after_long_one_percent_run": (
            "Scoped to rows whose prior state has at least the configured long "
            "1% streak; target is whether the next delta breaks away from 1%."
        ),
    }
    return {
        "risk_models": {
            "overall_prior_rate": "Historical non-1% rate before the current span.",
            "stable_one_percent_rule": (
                "Predicts zero break risk after the configured long 1% streak; "
                "otherwise uses the historical prior rate."
            ),
            "history_state_risk": "Empirical non-1% rate for matching history/streak buckets.",
            "calendar_state_risk": "Empirical non-1% rate for matching calendar buckets.",
            "reset_state_risk": "Empirical non-1% rate for matching reset/window buckets.",
            "previous_work_state_risk": (
                "Empirical non-1% rate for matching previous-span work-duration buckets."
            ),
        },
        "target_definitions": target_definitions,
        "scopes": {
            scope_name: transition_risk_scope(rows, start_index=start_index)
            for scope_name, start_index in scopes.items()
        },
    }


def transition_risk_scope(
    rows: list[dict[str, Any]], *, start_index: int
) -> dict[str, Any]:
    scope_rows = [row for row in rows if int(row["index"]) >= start_index]
    long_run_rows = [
        row
        for row in scope_rows
        if int((row.get("metadata") or {}).get("one_percent_streak_count") or 0)
        >= REGIME_GRACE_STREAK_THRESHOLD
    ]
    return {
        "non_one_percent_delta": transition_target_metrics(scope_rows),
        "break_after_long_one_percent_run": transition_target_metrics(
            long_run_rows
        ),
    }
