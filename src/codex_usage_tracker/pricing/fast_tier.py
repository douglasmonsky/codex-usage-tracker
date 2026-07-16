"""Documented Codex Fast credit multipliers for exact-tier accounting."""

from __future__ import annotations

from collections.abc import Mapping

DOCUMENTED_FAST_CREDIT_MULTIPLIERS = {
    "gpt-5.6": 2.5,
    "gpt-5.5": 2.5,
    "gpt-5.4": 2.0,
}


def documented_fast_credit_multiplier(model: object) -> float | None:
    """Return the documented Fast multiplier for a model family label."""

    normalized = str(model or "").strip().lower()
    for family, multiplier in DOCUMENTED_FAST_CREDIT_MULTIPLIERS.items():
        if (
            normalized == family
            or normalized.startswith(f"{family}-")
            or normalized.startswith(f"{family} ")
        ):
            return multiplier
    return None


def credit_multiplier_for_row(row: Mapping[str, object]) -> tuple[float, str]:
    """Return an effective credit multiplier and bounded provenance label."""

    if row.get("fast") != 1:
        fallback = "confirmed_standard" if row.get("fast") == 0 else "tier_unknown"
        return 1.0, str(row.get("service_tier_source") or fallback)
    multiplier = documented_fast_credit_multiplier(row.get("model"))
    if multiplier is None:
        return 1.0, "no_documented_fast_multiplier"
    return multiplier, str(row.get("service_tier_source") or "confirmed_fast")
