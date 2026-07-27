"""Reset-aware ratios between observed allowance movement and local facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AllowanceObservation:
    """One exact upstream allowance observation."""

    allowance_observation_id: str
    observed_at: datetime
    window_kind: str
    limit_id: str | None
    plan_type: str | None
    used_percent: float
    duration_minutes: int | None
    resets_at: str | None
    model: str | None
    service_tier: str | None
    provenance: str
    validation_warnings: tuple[str, ...]

    @property
    def remaining_percent(self) -> float:
        return 100.0 - self.used_percent


@dataclass(frozen=True)
class LocalUsage:
    """Exact local facts observed inside one allowance interval."""

    uncached_input_tokens: int = 0
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    turns: int = 0

    @property
    def total_tokens(self) -> int:
        return (
            self.uncached_input_tokens
            + self.cached_input_tokens
            + self.output_tokens
        )


@dataclass(frozen=True)
class AllowanceInterval:
    """One exact or deterministic observation interval."""

    current: AllowanceObservation
    previous: AllowanceObservation | None
    grade: str
    delta_used_percent: float | None
    elapsed_hours: float | None
    percentage_points_per_hour: float | None
    local_total_tokens: int
    local_calls: int
    local_turns: int
    local_tokens_per_percentage_point: float | None
    local_calls_per_percentage_point: float | None
    local_turns_per_percentage_point: float | None
    limitations: tuple[str, ...]


def build_interval(
    previous: AllowanceObservation | None,
    current: AllowanceObservation,
    usage: LocalUsage,
) -> AllowanceInterval:
    """Calculate ratios only for one valid adjacent observation pair."""

    limitation = _invalid_interval(previous, current)
    if limitation is not None:
        return _interval_without_ratios(
            previous,
            current,
            usage,
            limitation=limitation,
        )
    assert previous is not None
    elapsed_hours = (
        current.observed_at - previous.observed_at
    ).total_seconds() / 3600
    delta = current.used_percent - previous.used_percent
    limitations = ["outside_usage_possible"]
    if current.resets_at is None:
        limitations.append("reset_timestamp_unobserved")
    return AllowanceInterval(
        current=current,
        previous=previous,
        grade="deterministic",
        delta_used_percent=delta,
        elapsed_hours=elapsed_hours,
        percentage_points_per_hour=delta / elapsed_hours,
        local_total_tokens=usage.total_tokens,
        local_calls=usage.calls,
        local_turns=usage.turns,
        local_tokens_per_percentage_point=usage.total_tokens / delta,
        local_calls_per_percentage_point=usage.calls / delta,
        local_turns_per_percentage_point=usage.turns / delta,
        limitations=tuple(limitations),
    )


def _invalid_interval(
    previous: AllowanceObservation | None,
    current: AllowanceObservation,
) -> str | None:
    if previous is None:
        return "missing_previous_observation"
    if (
        previous.window_kind != current.window_kind
        or previous.limit_id != current.limit_id
        or previous.plan_type != current.plan_type
        or previous.duration_minutes != current.duration_minutes
    ):
        return "incompatible_window"
    if previous.resets_at != current.resets_at:
        return "reset_boundary"
    elapsed = (current.observed_at - previous.observed_at).total_seconds()
    if elapsed <= 0:
        return "non_positive_interval"
    if (
        current.duration_minutes is not None
        and elapsed > current.duration_minutes * 60
    ):
        return "missing_interval"
    delta = current.used_percent - previous.used_percent
    if delta == 0:
        return "unchanged_percentage"
    if delta < 0:
        return "non_monotonic_percentage"
    return None


def _interval_without_ratios(
    previous: AllowanceObservation | None,
    current: AllowanceObservation,
    usage: LocalUsage,
    *,
    limitation: str,
) -> AllowanceInterval:
    return AllowanceInterval(
        current=current,
        previous=previous,
        grade="exact",
        delta_used_percent=None,
        elapsed_hours=None,
        percentage_points_per_hour=None,
        local_total_tokens=usage.total_tokens,
        local_calls=usage.calls,
        local_turns=usage.turns,
        local_tokens_per_percentage_point=None,
        local_calls_per_percentage_point=None,
        local_turns_per_percentage_point=None,
        limitations=(limitation,),
    )
