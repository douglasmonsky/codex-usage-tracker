"""Cost estimation and pricing coverage calculations for aggregate usage rows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_PRICING_PATH
from codex_usage_tracker.pricing.config import PricingConfig, load_pricing_config

EFFICIENCY_FLAG_KEYS = {
    "high context use": "flag.high_context_use",
    "elevated context use": "flag.elevated_context_use",
    "high reasoning share": "flag.high_reasoning_share",
    "low cache reuse": "flag.low_cache_reuse",
    "expensive low-output call": "flag.expensive_low_output_call",
    "high estimated cost": "flag.high_estimated_cost",
}


def summarize_pricing_coverage(
    rows: list[dict[str, Any]],
    pricing: PricingConfig | None = None,
    *,
    model_field: str = "group_key",
) -> dict[str, Any]:
    """Summarize which aggregate model rows have usable local pricing."""

    config = pricing or load_pricing_config()
    coverage_rows: list[dict[str, Any]] = []
    totals = {
        "model_count": 0,
        "priced_model_count": 0,
        "unpriced_model_count": 0,
        "total_tokens": 0.0,
        "priced_tokens": 0.0,
        "unpriced_tokens": 0.0,
        "estimated_cost_usd": 0.0,
    }

    for row in rows:
        model = row.get(model_field)
        priced_as = config.priced_as(model)
        copy = dict(row)
        copy["model"] = model
        copy["priced"] = priced_as is not None
        copy["priced_as"] = priced_as
        copy["pricing_estimated"] = config.is_estimated_model(model)
        copy["estimated_cost_usd"] = estimate_cost_usd(copy, config, model=model)
        total_tokens = _number(copy.get("total_tokens"))
        totals["model_count"] += 1
        totals["total_tokens"] += total_tokens
        if priced_as:
            totals["priced_model_count"] += 1
            totals["priced_tokens"] += total_tokens
        else:
            totals["unpriced_model_count"] += 1
            totals["unpriced_tokens"] += total_tokens
        if isinstance(copy["estimated_cost_usd"], int | float):
            totals["estimated_cost_usd"] += float(copy["estimated_cost_usd"])
        coverage_rows.append(copy)

    total_tokens = totals["total_tokens"]
    totals["priced_token_ratio"] = totals["priced_tokens"] / total_tokens if total_tokens else 0.0
    coverage_rows.sort(
        key=lambda row: (
            0 if row.get("priced") is False else 1,
            -_number(row.get("total_tokens")),
        )
    )
    return {
        "schema": "codex-usage-tracker-pricing-coverage-v1",
        **totals,
        "pricing_loaded": config.loaded and not config.error,
        "pricing_path": str(config.path),
        "pricing_source": config.source,
        "rows": coverage_rows,
    }


def annotate_rows_with_efficiency(
    rows: list[dict[str, Any]],
    pricing: PricingConfig | None = None,
    *,
    model_field: str = "model",
    pricing_path: Path = DEFAULT_PRICING_PATH,
) -> list[dict[str, Any]]:
    """Return copied rows with local cost estimates and efficiency flags."""

    config = pricing or load_pricing_config(pricing_path)
    annotated: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        model = copy.get(model_field)
        cost = estimate_cost_usd(copy, config, model=model)
        savings = estimate_cache_savings_usd(copy, config, model=model)
        copy["estimated_cost_usd"] = cost
        copy["estimated_cache_savings_usd"] = savings
        copy["pricing_model"] = config.priced_as(model)
        copy["pricing_estimated"] = config.is_estimated_model(model)
        copy["efficiency_flags"] = efficiency_flags(copy)
        copy["efficiency_flag_keys"] = [
            EFFICIENCY_FLAG_KEYS[flag]
            for flag in copy["efficiency_flags"]
            if flag in EFFICIENCY_FLAG_KEYS
        ]
        annotated.append(copy)
    return annotated


def estimate_cost_usd(
    row: dict[str, Any], pricing: PricingConfig, *, model: object | None = None
) -> float | None:
    """Estimate call cost from aggregate tokens and local model rates."""

    rates = pricing.rates_for(model if model is not None else row.get("model"))
    if not rates:
        return None

    input_rate = rates.get("input_per_million")
    cached_rate = rates.get("cached_input_per_million", input_rate)
    output_rate = rates.get("output_per_million")
    if input_rate is None or cached_rate is None or output_rate is None:
        return None

    cached_input = _number(row.get("cached_input_tokens"))
    uncached_input = _number(row.get("uncached_input_tokens"))
    if uncached_input <= 0:
        uncached_input = max(_number(row.get("input_tokens")) - cached_input, 0.0)
    output_tokens = _number(row.get("output_tokens"))

    return (
        (uncached_input * input_rate) + (cached_input * cached_rate) + (output_tokens * output_rate)
    ) / 1_000_000


def estimate_cache_savings_usd(
    row: dict[str, Any], pricing: PricingConfig, *, model: object | None = None
) -> float | None:
    """Estimate local cache savings when cached input has a lower configured rate."""

    rates = pricing.rates_for(model if model is not None else row.get("model"))
    if not rates:
        return None
    input_rate = rates.get("input_per_million")
    cached_rate = rates.get("cached_input_per_million")
    if input_rate is None or cached_rate is None or cached_rate >= input_rate:
        return None
    return (_number(row.get("cached_input_tokens")) * (input_rate - cached_rate)) / 1_000_000


def efficiency_flags(row: dict[str, Any]) -> list[str]:
    """Generate aggregate-only signals worth reviewing."""

    total_tokens = _number(row.get("total_tokens"))
    output_tokens = _number(row.get("output_tokens"))
    input_tokens = _number(row.get("input_tokens"))
    context = _number(row.get("context_window_percent"))
    cache = _number(row.get("cache_ratio"))
    reasoning = _number(row.get("reasoning_output_ratio"))
    cost = row.get("estimated_cost_usd")
    return [
        flag
        for flag in (
            _context_efficiency_flag(context),
            _reasoning_efficiency_flag(reasoning, output_tokens),
            _cache_reuse_efficiency_flag(input_tokens, cache),
            _low_output_cost_efficiency_flag(total_tokens, output_tokens),
            _estimated_cost_efficiency_flag(cost),
        )
        if flag is not None
    ]


def _context_efficiency_flag(context: float) -> str | None:
    if context >= 0.8:
        return "high context use"
    if context >= 0.5:
        return "elevated context use"
    return None


def _reasoning_efficiency_flag(reasoning: float, output_tokens: float) -> str | None:
    if reasoning >= 0.75 and output_tokens >= 100:
        return "high reasoning share"
    return None


def _cache_reuse_efficiency_flag(input_tokens: float, cache: float) -> str | None:
    if input_tokens >= 10_000 and cache < 0.1:
        return "low cache reuse"
    return None


def _low_output_cost_efficiency_flag(
    total_tokens: float,
    output_tokens: float,
) -> str | None:
    if total_tokens >= 20_000 and output_tokens <= 100:
        return "expensive low-output call"
    return None


def _estimated_cost_efficiency_flag(cost: object) -> str | None:
    if isinstance(cost, int | float) and cost >= 1:
        return "high estimated cost"
    return None


def _number(value: object) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value)
    return 0.0
