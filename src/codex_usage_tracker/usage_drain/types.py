"""Shared usage-drain modeling types and constants."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from codex_usage_tracker.pricing.fast_tier import (
    DOCUMENTED_FAST_CREDIT_MULTIPLIERS as DOCUMENTED_FAST_CREDIT_MULTIPLIERS,
)
from codex_usage_tracker.pricing.fast_tier import (
    documented_fast_credit_multiplier as documented_fast_credit_multiplier,
)

DEFAULT_PROXY_NAMES = (
    "all_candidates",
    "strong_only",
    "high_medium_candidates",
    "high_confidence_only",
)

TOKEN_TOTAL_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "uncached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)

TOKEN_COMPONENT_FIELDS = (
    "uncached_input_tokens",
    "cached_input_tokens",
    "reasoning_output_tokens",
    "nonreasoning_output_tokens",
)

TIMING_TOTAL_FIELDS = (
    "call_duration_seconds",
    "previous_call_delta_seconds",
)

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "missing", "other")


def _span_optional_round(value: float | int | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


@dataclass(frozen=True)
class FastProxyAnnotation:
    """One aggregate fast-mode proxy label keyed by usage record id."""

    label: str = "not_fast_proxy"
    timing_confidence: str = "unknown"
    score: float | None = None

    @property
    def is_candidate(self) -> bool:
        return self.label in {"strong_proxy", "possible_proxy"}

    @property
    def is_strong(self) -> bool:
        return self.label == "strong_proxy"

    @property
    def is_high_or_medium(self) -> bool:
        return self.is_candidate and self.timing_confidence in {"high", "medium"}

    @property
    def is_high(self) -> bool:
        return self.is_candidate and self.timing_confidence == "high"


@dataclass
class UsageDeltaSpan:
    """A closed positive visible-usage delta and its aggregate call mix."""

    start_event_timestamp: str
    end_event_timestamp: str
    baseline_used_percent: float
    end_used_percent: float
    delta_usage_percent: float
    row_count: int
    standard_usage_credits: float
    non_candidate_standard_credits: dict[str, float]
    candidate_standard_credits: dict[str, float]
    documented_fast_weighted_credits: dict[str, float]
    candidate_row_counts: dict[str, int]
    documented_fast_weighted_token_totals: dict[str, dict[str, float]] = field(default_factory=dict)
    models: dict[str, int] = field(default_factory=dict)
    effort_counts: dict[str, int] = field(default_factory=dict)
    turn_count: int = 0
    multi_call_turn_count: int = 0
    max_calls_in_turn: int = 0
    token_totals: dict[str, float] = field(default_factory=dict)
    timing_totals: dict[str, float] = field(default_factory=dict)
    rate_limit_plan_type: str | None = None
    rate_limit_limit_id: str | None = None
    usage_window_source: str | None = None
    usage_window_minutes: float | None = None
    usage_window_resets_at: float | None = None
    rate_limit_primary_window_minutes: float | None = None
    rate_limit_primary_resets_at: float | None = None

    def to_row(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "start_event_timestamp": self.start_event_timestamp,
            "end_event_timestamp": self.end_event_timestamp,
            "baseline_used_percent": round(self.baseline_used_percent, 6),
            "end_used_percent": round(self.end_used_percent, 6),
            "delta_usage_percent": round(self.delta_usage_percent, 6),
            "row_count": self.row_count,
            "standard_usage_credits": round(self.standard_usage_credits, 6),
            "models": "|".join(f"{model}:{count}" for model, count in sorted(self.models.items())),
            "efforts": "|".join(
                f"{effort}:{count}" for effort, count in sorted(self.effort_counts.items())
            ),
            "turn_count": self.turn_count,
            "multi_call_turn_count": self.multi_call_turn_count,
            "max_calls_in_turn": self.max_calls_in_turn,
            "rate_limit_plan_type": self.rate_limit_plan_type,
            "rate_limit_limit_id": self.rate_limit_limit_id,
            "usage_window_source": self.usage_window_source,
            "usage_window_minutes": _span_optional_round(self.usage_window_minutes),
            "usage_window_resets_at": _span_optional_round(self.usage_window_resets_at),
            "rate_limit_primary_window_minutes": _span_optional_round(
                self.rate_limit_primary_window_minutes
            ),
            "rate_limit_primary_resets_at": _span_optional_round(self.rate_limit_primary_resets_at),
        }
        for field_name in TOKEN_TOTAL_FIELDS:
            row[field_name] = round(self.token_totals.get(field_name, 0.0), 6)
        for field_name in TIMING_TOTAL_FIELDS:
            row[field_name] = round(self.timing_totals.get(field_name, 0.0), 6)
        for proxy in DEFAULT_PROXY_NAMES:
            candidate = self.candidate_standard_credits.get(proxy, 0.0)
            documented = self.documented_fast_weighted_credits.get(proxy, 0.0)
            row[f"{proxy}_candidate_rows"] = self.candidate_row_counts.get(proxy, 0)
            row[f"{proxy}_candidate_standard_credits"] = round(candidate, 6)
            row[f"{proxy}_non_candidate_standard_credits"] = round(
                self.non_candidate_standard_credits.get(proxy, 0.0), 6
            )
            row[f"{proxy}_documented_fast_weighted_credits"] = round(documented, 6)
        return row


@dataclass(frozen=True)
class UsageDrainModelResult:
    """Fit result for one candidate proxy definition."""

    proxy: str
    spans: int
    candidate_spans: int
    candidate_span_share: float
    coef_non_candidate_usage_pct_per_credit: float | None
    coef_candidate_usage_pct_per_credit: float | None
    implied_candidate_multiplier: float | None
    documented_weighted_candidate_multiplier: float | None
    two_feature_r2: float | None
    grid: list[dict[str, float | None]]
    best_grid_multiplier_by_r2: float | None
    corr_candidate_credit_share_vs_drain_per_standard_credit: float | None
    spans_with_candidates: dict[str, float | int | None]
    spans_without_candidates: dict[str, float | int | None]
    with_vs_without_median_drain_ratio: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PredictiveModelSpec:
    """One exploratory usage-drain prediction feature family."""

    name: str
    numeric_features: tuple[str, ...]
    categorical_features: tuple[str, ...] = ()
    ridge_alpha: float = 1.0
