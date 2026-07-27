from __future__ import annotations

from datetime import datetime, timezone

import pytest

from codex_usage_tracker.kernel.allowance import (
    AllowanceObservation,
    LocalUsage,
    build_interval,
)

UTC = timezone.utc


def _observation(
    observation_id: str,
    *,
    hour: int,
    used_percent: float,
    resets_at: str | None = "2026-01-02T00:00:00Z",
    window_kind: str = "five_hour",
    limit_id: str | None = "synthetic-limit",
    duration_minutes: int | None = 300,
) -> AllowanceObservation:
    return AllowanceObservation(
        allowance_observation_id=observation_id,
        observed_at=datetime(2026, 1, 1, hour, tzinfo=UTC),
        window_kind=window_kind,
        limit_id=limit_id,
        plan_type="synthetic",
        used_percent=used_percent,
        duration_minutes=duration_minutes,
        resets_at=resets_at,
        model="gpt-synthetic",
        service_tier="standard",
        provenance="synthetic fixture",
        validation_warnings=(),
    )


def test_adjacent_compatible_observations_produce_deterministic_ratios() -> None:
    interval = build_interval(
        _observation("previous", hour=10, used_percent=10),
        _observation("current", hour=12, used_percent=14),
        LocalUsage(
            uncached_input_tokens=200,
            cached_input_tokens=100,
            reasoning_tokens=20,
            output_tokens=100,
            calls=4,
            turns=2,
        ),
    )

    assert interval.grade == "deterministic"
    assert interval.delta_used_percent == 4
    assert interval.elapsed_hours == 2
    assert interval.percentage_points_per_hour == 2
    assert interval.local_total_tokens == 400
    assert interval.local_tokens_per_percentage_point == 100
    assert interval.local_calls_per_percentage_point == 1
    assert interval.local_turns_per_percentage_point == 0.5
    assert interval.limitations == ("outside_usage_possible",)


def test_missing_reset_timestamp_is_disclosed_on_deterministic_ratio() -> None:
    interval = build_interval(
        _observation(
            "previous",
            hour=10,
            used_percent=10,
            resets_at=None,
        ),
        _observation(
            "current",
            hour=12,
            used_percent=14,
            resets_at=None,
        ),
        LocalUsage(),
    )

    assert interval.grade == "deterministic"
    assert interval.limitations == (
        "outside_usage_possible",
        "reset_timestamp_unobserved",
    )


@pytest.mark.parametrize(
    ("previous", "current", "limitation"),
    [
        (
            None,
            _observation("current", hour=12, used_percent=14),
            "missing_previous_observation",
        ),
        (
            _observation("previous", hour=10, used_percent=10),
            _observation(
                "current",
                hour=12,
                used_percent=14,
                resets_at="2026-01-03T00:00:00Z",
            ),
            "reset_boundary",
        ),
        (
            _observation("previous", hour=10, used_percent=14),
            _observation("current", hour=12, used_percent=14),
            "unchanged_percentage",
        ),
        (
            _observation("previous", hour=10, used_percent=14),
            _observation("current", hour=12, used_percent=10),
            "non_monotonic_percentage",
        ),
        (
            _observation("previous", hour=10, used_percent=10),
            _observation(
                "current",
                hour=12,
                used_percent=14,
                window_kind="weekly",
            ),
            "incompatible_window",
        ),
        (
            _observation(
                "previous",
                hour=10,
                used_percent=10,
                duration_minutes=60,
            ),
            _observation(
                "current",
                hour=12,
                used_percent=14,
                duration_minutes=60,
            ),
            "missing_interval",
        ),
        (
            _observation(
                "previous",
                hour=10,
                used_percent=10,
                duration_minutes=300,
            ),
            _observation(
                "current",
                hour=12,
                used_percent=14,
                duration_minutes=60,
            ),
            "incompatible_window",
        ),
    ],
)
def test_invalid_intervals_never_interpolate(
    previous: AllowanceObservation | None,
    current: AllowanceObservation,
    limitation: str,
) -> None:
    interval = build_interval(previous, current, LocalUsage())

    assert interval.grade == "exact"
    assert interval.percentage_points_per_hour is None
    assert interval.local_tokens_per_percentage_point is None
    assert limitation in interval.limitations
