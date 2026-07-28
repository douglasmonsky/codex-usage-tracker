from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

_TOKEN_FIELDS = (
    "uncached_input_tokens",
    "cached_input_tokens",
    "reasoning_tokens",
    "output_tokens",
)
_COMPATIBILITY_FIELDS = (
    "provider",
    "limit_id",
    "plan_identity",
    "window_kind",
    "cycle_id",
    "reset_identity",
)


class AllowanceContractError(ValueError):
    """Raised when allowance or valuation facts are logically incompatible."""


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _decimal(
    value: Any,
    field: str,
    *,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AllowanceContractError(f"{field} must be a canonical decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise AllowanceContractError(f"{field} is not a decimal") from exc
    if not parsed.is_finite():
        raise AllowanceContractError(f"{field} must be finite")
    if value != _decimal_text(parsed):
        raise AllowanceContractError(f"{field} is not a canonical decimal string")
    if minimum is not None and parsed < minimum:
        raise AllowanceContractError(f"{field} is below its allowed domain")
    if maximum is not None and parsed > maximum:
        raise AllowanceContractError(f"{field} is above its allowed domain")
    return parsed


def canonical_decimal(
    value: Any,
    field: str,
    *,
    minimum: str | None = None,
    maximum: str | None = None,
) -> str | None:
    """Validate and round-trip one canonical finite decimal string."""

    parsed = _decimal(
        value,
        field,
        minimum=None if minimum is None else Decimal(minimum),
        maximum=None if maximum is None else Decimal(maximum),
    )
    return None if parsed is None else _decimal_text(parsed)


def allowance_interval(
    start: dict[str, Any],
    end: dict[str, Any],
) -> dict[str, Any]:
    """Relate adjacent compatible observations with half-open event bounds."""

    incompatible = [
        field
        for field in _COMPATIBILITY_FIELDS
        if start.get(field) != end.get(field)
    ]
    if incompatible:
        raise AllowanceContractError(
            f"incompatible allowance observations: {','.join(incompatible)}"
        )
    missing_compatibility = [
        field
        for field in _COMPATIBILITY_FIELDS
        if start.get(field) is None or end.get(field) is None
    ]
    if missing_compatibility:
        raise AllowanceContractError(
            "allowance compatibility field is missing: "
            f"{','.join(missing_compatibility)}"
        )
    start_at = start["observed_at_us"]
    end_at = end["observed_at_us"]
    if end_at < start_at:
        raise AllowanceContractError("allowance observation time decreases")

    percentage_minimum = Decimal(0)
    percentage_maximum = Decimal(100)
    used_start = _decimal(
        start.get("used_percent"),
        "used_percent",
        minimum=percentage_minimum,
        maximum=percentage_maximum,
    )
    used_end = _decimal(
        end.get("used_percent"),
        "used_percent",
        minimum=percentage_minimum,
        maximum=percentage_maximum,
    )
    remaining_start = _decimal(
        start.get("remaining_percent"),
        "remaining_percent",
        minimum=percentage_minimum,
        maximum=percentage_maximum,
    )
    remaining_end = _decimal(
        end.get("remaining_percent"),
        "remaining_percent",
        minimum=percentage_minimum,
        maximum=percentage_maximum,
    )
    deltas: list[Decimal] = []
    if used_start is not None and used_end is not None:
        deltas.append(used_end - used_start)
    if remaining_start is not None and remaining_end is not None:
        deltas.append(remaining_start - remaining_end)
    if not deltas:
        percent_delta = None
    else:
        if any(delta != deltas[0] for delta in deltas[1:]):
            raise AllowanceContractError("used and remaining percentage deltas disagree")
        percent_delta = deltas[0]
    return {
        "start_selector": f"allowance-observation:{start['observation_id']}",
        "end_selector": f"allowance-observation:{end['observation_id']}",
        "event_bounds": {
            "start_us": start_at,
            "end_us": end_at,
            "semantics": "[start,end)",
        },
        "percent_delta": (
            None if percent_delta is None else _decimal_text(percent_delta)
        ),
        "ratio_eligible": percent_delta is not None and percent_delta > 0,
        "compatibility_basis": "exact_identity_tuple_v1",
    }


def _token_value(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AllowanceContractError(f"{field} must be nonnegative integer or null")
    return value


def current_valuation(
    tokens: dict[str, Any],
    rate_card: dict[str, Any],
) -> dict[str, Any]:
    """Apply one configured rate-card revision without rewriting canonical calls."""

    normalized = {
        field: _token_value(tokens.get(field), field) for field in _TOKEN_FIELDS
    }
    rates = rate_card.get("rates_per_million", {})
    credit_rates = rate_card.get("credit_rates_per_million", {})
    parsed_cost_rates = {
        field: _decimal(
            rates.get(field),
            f"{field} cost rate",
            minimum=Decimal(0),
        )
        for field in _TOKEN_FIELDS
    }
    parsed_credit_rates = {
        field: _decimal(
            credit_rates.get(field),
            f"{field} credit rate",
            minimum=Decimal(0),
        )
        for field in _TOKEN_FIELDS
    }
    reasoning_in_output = bool(rate_card.get("reasoning_in_output"))
    if reasoning_in_output:
        if parsed_cost_rates["reasoning_tokens"] not in {None, Decimal(0)}:
            raise AllowanceContractError(
                "reasoning cost rate would double-count output"
            )
        if parsed_credit_rates["reasoning_tokens"] not in {None, Decimal(0)}:
            raise AllowanceContractError(
                "reasoning credit rate would double-count output"
            )

    eligible_fields = [
        field
        for field in _TOKEN_FIELDS
        if not (field == "reasoning_tokens" and reasoning_in_output)
    ]
    observed_fields = [
        field for field in eligible_fields if normalized[field] is not None
    ]
    matched = bool(rate_card.get("matched", True))
    cost_rated_fields = (
        [
            field
            for field in observed_fields
            if parsed_cost_rates[field] is not None
        ]
        if matched
        else []
    )
    credit_rated_fields = (
        [
            field
            for field in observed_fields
            if parsed_credit_rates[field] is not None
        ]
        if matched
        else []
    )
    cost_unpriced_fields = [
        field for field in observed_fields if field not in cost_rated_fields
    ]
    credit_unpriced_fields = [
        field for field in observed_fields if field not in credit_rated_fields
    ]
    denominator = sum(normalized[field] or 0 for field in observed_fields)
    cost_numerator = sum(
        normalized[field] or 0 for field in cost_rated_fields
    )
    credit_numerator = sum(
        normalized[field] or 0 for field in credit_rated_fields
    )
    cost = sum(
        (
            Decimal(normalized[field] or 0)
            * (parsed_cost_rates[field] or Decimal(0))
            / Decimal(1_000_000)
            for field in cost_rated_fields
        ),
        Decimal(0),
    )
    credits = sum(
        (
            Decimal(normalized[field] or 0)
            * (parsed_credit_rates[field] or Decimal(0))
            / Decimal(1_000_000)
            for field in credit_rated_fields
        ),
        Decimal(0),
    )
    missing_fields = [
        field for field in eligible_fields if normalized[field] is None
    ]
    def unpriced_reason(unpriced_fields: list[str]) -> str | None:
        if not matched:
            return "model_unmatched"
        if unpriced_fields:
            return "partial_rate_card"
        if missing_fields:
            return "missing_measurement"
        return None

    cost_reason = unpriced_reason(cost_unpriced_fields)
    credit_reason = unpriced_reason(credit_unpriced_fields)
    return {
        "rate_card_digest": rate_card["digest"],
        "match_basis": rate_card["match_basis"],
        "configured_cost_usd": (
            None if not cost_rated_fields else _decimal_text(cost)
        ),
        "estimated_credits": (
            None if not credit_rated_fields else _decimal_text(credits)
        ),
        "cost_rated_token_fields": cost_rated_fields,
        "credit_rated_token_fields": credit_rated_fields,
        "cost_unpriced_token_fields": cost_unpriced_fields,
        "credit_unpriced_token_fields": credit_unpriced_fields,
        "missing_token_fields": missing_fields,
        "cost_coverage_numerator_tokens": cost_numerator,
        "cost_coverage_denominator_tokens": denominator,
        "cost_coverage": (
            None
            if denominator == 0
            else _decimal_text(Decimal(cost_numerator) / Decimal(denominator))
        ),
        "credit_coverage_numerator_tokens": credit_numerator,
        "credit_coverage_denominator_tokens": denominator,
        "credit_coverage": (
            None
            if denominator == 0
            else _decimal_text(Decimal(credit_numerator) / Decimal(denominator))
        ),
        "cost_unpriced_reason": cost_reason,
        "credit_unpriced_reason": credit_reason,
        "cost_grade": (
            "configured_estimate" if cost_rated_fields else "unsupported"
        ),
        "credit_grade": (
            "configured_estimate" if credit_rated_fields else "unsupported"
        ),
    }
