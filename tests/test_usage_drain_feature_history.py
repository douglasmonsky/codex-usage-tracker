from __future__ import annotations

import pytest

from codex_usage_tracker.usage_drain_feature_history import add_causal_history_features


def _feature_row(
    *,
    target: float,
    credits: float,
    limit_id: str = "limit-a",
    date: str = "2026-06-01",
    hour: str = "09",
    day: str = "Monday",
) -> dict[str, object]:
    return {
        "target": target,
        "standard_usage_credits": credits,
        "rate_limit_plan_type": "pro",
        "rate_limit_limit_id": limit_id,
        "date": date,
        "hour_bucket": hour,
        "day_of_week": day,
    }


def test_add_causal_history_features_only_uses_prior_rows() -> None:
    rows = [
        _feature_row(target=1.0, credits=100.0),
        _feature_row(target=2.0, credits=200.0),
        _feature_row(target=1.0, credits=150.0, limit_id="limit-b", date="2026-06-02", hour="10", day="Tuesday"),
        _feature_row(target=1.0, credits=100.0),
    ]

    add_causal_history_features(rows)

    assert rows[0]["previous_delta_percent"] == 0.0
    assert rows[0]["same_bucket_seen_count"] == 0.0
    assert rows[0]["ewma_delta_percent"] == 0.0

    assert rows[1]["previous_delta_percent"] == 1.0
    assert rows[1]["rolling3_delta_percent"] == 1.0
    assert rows[1]["rolling10_median_delta_percent"] == 1.0
    assert rows[1]["one_percent_streak"] == 1.0
    assert rows[1]["previous_capacity_credits_per_percent"] == 100.0
    assert rows[1]["ewma_capacity_credits_per_percent"] == 100.0
    assert rows[1]["previous_capacity_delta_prediction"] == 2.0
    assert rows[1]["same_bucket_seen_count"] == 1.0
    assert rows[1]["same_bucket_rolling10_delta_percent"] == 1.0
    assert rows[1]["same_date_seen_count"] == 1.0
    assert rows[1]["same_hour_seen_count"] == 1.0
    assert rows[1]["same_day_of_week_seen_count"] == 1.0

    assert rows[2]["same_bucket_seen_count"] == 0.0
    assert rows[2]["same_date_seen_count"] == 0.0
    assert rows[2]["same_hour_seen_count"] == 0.0
    assert rows[2]["same_day_of_week_seen_count"] == 0.0
    assert rows[2]["ewma_delta_percent"] == pytest.approx(1.2)

    assert rows[3]["same_bucket_seen_count"] == 2.0
    assert rows[3]["same_bucket_rolling10_delta_percent"] == 1.5
    assert rows[3]["same_date_seen_count"] == 2.0
    assert rows[3]["same_hour_seen_count"] == 2.0
    assert rows[3]["same_day_of_week_seen_count"] == 2.0
