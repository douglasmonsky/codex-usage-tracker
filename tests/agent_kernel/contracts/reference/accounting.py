from __future__ import annotations

from collections.abc import Iterable
from typing import Any

_TOKEN_FIELDS = (
    "uncached_input_tokens",
    "cached_input_tokens",
    "reasoning_tokens",
    "output_tokens",
)
_CANONICAL_GRADES = frozenset({"exact", "deterministic", "configured_estimate"})
_RESULT_ONLY_GRADES = frozenset({"model_inference", "unsupported"})


class AccountingContractError(ValueError):
    """Raised when accounting would lose missingness or double-count usage."""


def _optional_nonnegative_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AccountingContractError(f"{field} must be a nonnegative integer or null")
    return value


def token_totals(tokens: dict[str, Any]) -> dict[str, int | None]:
    """Derive default totals while keeping reasoning outside billed total."""

    unknown = set(tokens) - set(_TOKEN_FIELDS)
    if unknown:
        raise AccountingContractError(f"unknown token fields: {sorted(unknown)}")
    normalized = {
        field: _optional_nonnegative_int(tokens.get(field), field)
        for field in _TOKEN_FIELDS
    }
    uncached = normalized["uncached_input_tokens"]
    cached = normalized["cached_input_tokens"]
    output = normalized["output_tokens"]
    input_tokens = None if uncached is None or cached is None else uncached + cached
    total_tokens = None if input_tokens is None or output is None else input_tokens + output
    return {
        **normalized,
        "input_tokens": input_tokens,
        "total_tokens": total_tokens,
    }


def aggregate_measurement(values: Iterable[int | None]) -> dict[str, Any]:
    """Sum observed values and expose missing coverage instead of imputing zero."""

    selected = list(values)
    observed: list[int] = []
    for value in selected:
        if value is None:
            continue
        normalized = _optional_nonnegative_int(value, "aggregate value")
        if normalized is not None:
            observed.append(normalized)
    missing_count = len(selected) - len(observed)
    return {
        "value": sum(observed) if observed else None,
        "observed_count": len(observed),
        "missing_count": missing_count,
        "complete": missing_count == 0,
    }


def measurement_mask(
    available: Iterable[str],
    bit_positions: dict[str, int],
) -> int:
    """Encode the versioned measurement-availability mask."""

    mask = 0
    for measurement in available:
        if measurement not in bit_positions:
            raise AccountingContractError(f"unknown measurement bit: {measurement}")
        mask |= 1 << bit_positions[measurement]
    return mask


def validate_measurement_record(
    record: dict[str, dict[str, Any]],
    *,
    mask: int,
    bit_positions: dict[str, int],
) -> None:
    """Validate value/mask/grade/basis consistency for canonical measurements."""

    for measurement, details in record.items():
        if measurement not in bit_positions:
            raise AccountingContractError(f"unknown measurement: {measurement}")
        available = bool(mask & (1 << bit_positions[measurement]))
        value = details.get("value")
        grade = details.get("grade")
        basis = details.get("basis")
        if grade in _RESULT_ONLY_GRADES:
            raise AccountingContractError(
                "canonical measurement has a result-only grade"
            )
        if value is None:
            if available:
                raise AccountingContractError("missing measurement has availability bit")
            if grade is not None:
                raise AccountingContractError("missing measurement has a value grade")
            if basis not in {"unavailable", "unobserved", "inapplicable", "invalid"}:
                raise AccountingContractError("missing measurement lacks missing basis")
            continue
        if not available:
            raise AccountingContractError("observed measurement lacks availability bit")
        if grade not in _CANONICAL_GRADES:
            raise AccountingContractError("canonical measurement has invalid grade")
        if not isinstance(basis, str) or basis in {
            "",
            "unavailable",
            "unobserved",
            "inapplicable",
            "invalid",
        }:
            raise AccountingContractError("observed measurement lacks exact basis")


def tool_outcome_counts(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Count intent, lifecycle success, and mutation as independent facts."""

    mutation_ids = {
        record["state_change_id"]
        for record in records
        if record.get("state_change_id") is not None
    }
    return {
        "invocations": len(records),
        "write_intents": sum(bool(record.get("write_intent")) for record in records),
        "succeeded": sum(
            record.get("lifecycle_state") == "succeeded" for record in records
        ),
        "observed_mutations": len(mutation_ids),
        "causal_attribution": False,
    }
