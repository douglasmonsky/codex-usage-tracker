"""Documented Codex Fast credit multipliers for exact-tier accounting."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache

from codex_usage_tracker.pricing.allowance_rate_card import (
    FastMultiplierRate,
    load_bundled_rate_card,
    parse_fast_multipliers,
    parse_rate_card_source,
)


@dataclass(frozen=True)
class FastMultiplierMatch:
    """A model-family multiplier match with independent numeric provenance."""

    multiplier: float
    model_family: str
    source_name: str
    source_url: str | None
    fetched_at: str | None
    confidence: str


def documented_fast_credit_multiplier(
    model: object,
    multipliers: Mapping[str, FastMultiplierRate] | None = None,
) -> float | None:
    """Return the documented Fast multiplier for a model family label."""

    match = match_fast_credit_multiplier(model, multipliers)
    return match.multiplier if match is not None else None


def match_fast_credit_multiplier(
    model: object,
    multipliers: Mapping[str, FastMultiplierRate] | None = None,
) -> FastMultiplierMatch | None:
    """Resolve the longest configured model-family prefix."""

    normalized = str(model or "").strip().lower().replace("_", "-")
    configured = multipliers if multipliers is not None else _bundled_fast_multipliers()
    for family in sorted(configured, key=len, reverse=True):
        if (
            normalized == family
            or normalized.startswith(f"{family}-")
            or normalized.startswith(f"{family} ")
        ):
            rate = configured[family]
            return FastMultiplierMatch(
                multiplier=rate.multiplier,
                model_family=family,
                source_name=rate.source_name,
                source_url=rate.source_url,
                fetched_at=rate.fetched_at,
                confidence=rate.confidence,
            )
    return None


def credit_multiplier_for_row(
    row: Mapping[str, object],
    multipliers: Mapping[str, FastMultiplierRate] | None = None,
) -> tuple[float, FastMultiplierMatch | None, str]:
    """Return the applied multiplier, available scenario match, and fallback label."""

    match = match_fast_credit_multiplier(row.get("model"), multipliers)
    if row.get("fast") != 1:
        fallback = "confirmed_standard" if row.get("fast") == 0 else "tier_unknown"
        return 1.0, match, str(row.get("service_tier_source") or fallback)
    if match is None:
        return 1.0, None, "no_documented_fast_multiplier"
    return match.multiplier, match, match.source_name


@lru_cache(maxsize=1)
def _bundled_fast_multipliers() -> dict[str, FastMultiplierRate]:
    raw = load_bundled_rate_card()
    return parse_fast_multipliers(
        raw.get("fast_multipliers", {}), source=parse_rate_card_source(raw)
    )


DOCUMENTED_FAST_CREDIT_MULTIPLIERS = {
    family: rate.multiplier for family, rate in _bundled_fast_multipliers().items()
}
