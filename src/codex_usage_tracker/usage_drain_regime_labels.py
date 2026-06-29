"""Regime label helpers for usage-drain diagnostics."""

from __future__ import annotations

from codex_usage_tracker.usage_drain_feature_history import is_one_percent_delta


def segment_position_bucket(position: int) -> str:
    if position <= 1:
        return "first_span"
    if position == 2:
        return "second_span"
    if position == 3:
        return "third_span"
    if position <= 5:
        return "fourth_fifth_span"
    return "sixth_plus_span"


def delta_regime_label(value: float) -> str:
    if is_one_percent_delta(value):
        return "stable_one_percent"
    if value <= 2.0:
        return "small_blip"
    if value <= 5.0:
        return "moderate_delta"
    if value <= 10.0:
        return "high_delta"
    return "very_high_delta"
