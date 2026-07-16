"""Allowance credit annotation and summary helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_ALLOWANCE_PATH
from codex_usage_tracker.pricing.allowance_config import (
    UsageAllowanceConfig,
    load_allowance_config,
)
from codex_usage_tracker.pricing.allowance_rate_card import (
    normalize_model,
    number_value,
    optional_str,
)
from codex_usage_tracker.pricing.fast_tier import credit_multiplier_for_row

__all__ = (
    "annotate_rows_with_allowance",
    "estimate_standard_usage_credits",
    "estimate_usage_credits",
    "resolve_credit_rate",
    "summarize_allowance_usage",
)


def annotate_rows_with_allowance(
    rows: list[dict[str, Any]],
    config: UsageAllowanceConfig | None = None,
    *,
    model_field: str = "model",
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
) -> list[dict[str, Any]]:
    """Return copied rows with Codex credit usage annotations."""

    resolved = config or load_allowance_config(allowance_path)
    annotated: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        model = copy.get(model_field)
        match = resolve_credit_rate(model, resolved)
        multiplier, multiplier_source = credit_multiplier_for_row(copy)
        if match is None:
            copy.update(
                {
                    "usage_credits": None,
                    "standard_usage_credits": None,
                    "usage_credit_multiplier": multiplier,
                    "usage_credit_multiplier_source": multiplier_source,
                    "usage_credit_model": None,
                    "usage_credit_confidence": "unpriced",
                    "usage_credit_source": "No Codex credit rate",
                    "usage_credit_source_url": None,
                    "usage_credit_fetched_at": None,
                    "usage_credit_tier": None,
                    "usage_credit_note": "No bundled or configured credit rate matched this model.",
                }
            )
        else:
            rated_model, rates, confidence, note, metadata = match
            standard_credits = estimate_standard_usage_credits(copy, rates)
            copy.update(
                {
                    "usage_credits": standard_credits * multiplier,
                    "standard_usage_credits": standard_credits,
                    "usage_credit_multiplier": multiplier,
                    "usage_credit_multiplier_source": multiplier_source,
                    "usage_credit_model": rated_model,
                    "usage_credit_confidence": confidence,
                    "usage_credit_source": metadata.get("source_name")
                    or resolved.source.get("name", "Codex credit rates"),
                    "usage_credit_source_url": metadata.get("source_url"),
                    "usage_credit_fetched_at": metadata.get("fetched_at"),
                    "usage_credit_tier": metadata.get("tier"),
                    "usage_credit_note": note,
                }
            )
        annotated.append(copy)
    return annotated


def summarize_allowance_usage(
    rows: list[dict[str, Any]], config: UsageAllowanceConfig | None = None
) -> dict[str, Any]:
    """Summarize Codex credit usage against configured allowance windows."""

    resolved = config or load_allowance_config()
    totals = _allowance_usage_totals(rows)
    return {
        "usage_credits": totals["usage_credits"],
        "exact_usage_credits": totals["exact_usage_credits"],
        "estimated_usage_credits": totals["estimated_usage_credits"],
        "user_override_usage_credits": totals["user_override_usage_credits"],
        "rated_tokens": totals["rated_tokens"],
        "unrated_tokens": totals["unrated_tokens"],
        "credit_token_ratio": totals["credit_token_ratio"],
        "windows": [asdict(window) for window in resolved.windows],
        "source": resolved.source,
        "configured": resolved.loaded,
        "error": resolved.error,
        "rate_card_loaded": resolved.rate_card_loaded,
        "rate_card_error": resolved.rate_card_error,
    }


def _allowance_usage_totals(rows: list[dict[str, Any]]) -> dict[str, float]:
    total_tokens = _sum_numeric_field(rows, "total_tokens")
    rated_tokens = _sum_numeric_field(
        rows, "total_tokens", lambda row: row.get("usage_credits") is not None
    )
    usage_credits = _sum_numeric_field(
        rows, "usage_credits", lambda row: row.get("usage_credits") is not None
    )
    return {
        "usage_credits": usage_credits,
        "exact_usage_credits": _sum_credit_confidence(rows, "exact"),
        "estimated_usage_credits": _sum_credit_confidence(rows, "estimated"),
        "user_override_usage_credits": _sum_credit_confidence(rows, "user_override"),
        "rated_tokens": rated_tokens,
        "unrated_tokens": max(total_tokens - rated_tokens, 0.0),
        "credit_token_ratio": rated_tokens / total_tokens if total_tokens else 0.0,
    }


def _sum_credit_confidence(rows: list[dict[str, Any]], confidence: str) -> float:
    return _sum_numeric_field(
        rows,
        "usage_credits",
        lambda row: row.get("usage_credit_confidence") == confidence,
    )


def _sum_numeric_field(
    rows: list[dict[str, Any]],
    field: str,
    include: Callable[[dict[str, Any]], bool] | None = None,
) -> float:
    return sum(number_value(row.get(field)) for row in rows if include is None or include(row))


def resolve_credit_rate(
    model: object, config: UsageAllowanceConfig
) -> tuple[str, dict[str, float], str, str, dict[str, Any]] | None:
    """Resolve a model label into a credit rate, confidence, and note."""

    normalized = normalize_model(model)
    if not normalized:
        return None
    return _resolve_direct_credit_rate(normalized, config) or _resolve_alias_credit_rate(
        normalized, config
    )


def _resolve_direct_credit_rate(
    model: str, config: UsageAllowanceConfig
) -> tuple[str, dict[str, float], str, str, dict[str, Any]] | None:
    rates = config.credit_rates.get(model)
    if rates is None:
        return None
    metadata = config.rate_metadata.get(model, {})
    confidence = optional_str(metadata.get("confidence")) or "exact"
    note = optional_str(metadata.get("note")) or _direct_credit_rate_note(confidence)
    return model, rates, confidence, note, metadata


def _direct_credit_rate_note(confidence: str) -> str:
    if confidence == "user_override":
        return "Direct match to local user-provided Codex credit rate."
    return "Direct match to Codex credit rates."


def _resolve_alias_credit_rate(
    model: str, config: UsageAllowanceConfig
) -> tuple[str, dict[str, float], str, str, dict[str, Any]] | None:
    alias = config.aliases.get(model)
    if not alias:
        return None
    target = normalize_model(alias.get("model"))
    if not target:
        return None
    rates = config.credit_rates.get(target)
    if rates is None:
        return None
    metadata = {**config.rate_metadata.get(target, {}), **config.alias_metadata.get(model, {})}
    confidence = alias.get("confidence") or optional_str(metadata.get("confidence")) or "estimated"
    note = (
        alias.get("note")
        or optional_str(metadata.get("note"))
        or (f"Mapped from {model} to {target} by local alias.")
    )
    return target, rates, confidence, note, metadata


def estimate_standard_usage_credits(
    row: dict[str, Any], rates: dict[str, float]
) -> float:
    """Estimate Standard-tier Codex credits from aggregate token counters."""

    input_rate = rates["input_per_million"]
    cached_rate = rates["cached_input_per_million"]
    output_rate = rates["output_per_million"]
    cached_input = number_value(row.get("cached_input_tokens"))
    uncached_input = number_value(row.get("uncached_input_tokens"))
    if uncached_input <= 0:
        uncached_input = max(number_value(row.get("input_tokens")) - cached_input, 0.0)
    output_tokens = number_value(row.get("output_tokens"))
    return (
        (uncached_input * input_rate) + (cached_input * cached_rate) + (output_tokens * output_rate)
    ) / 1_000_000


def estimate_usage_credits(row: dict[str, Any], rates: dict[str, float]) -> float:
    """Estimate effective Codex credits, including confirmed Fast multipliers."""

    standard = estimate_standard_usage_credits(row, rates)
    multiplier, _source = credit_multiplier_for_row(row)
    return standard * multiplier
