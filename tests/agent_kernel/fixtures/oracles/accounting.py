from __future__ import annotations

from typing import Any

from tests.agent_kernel.fixtures.generator.profile import (
    FixtureProfile,
    planned_distribution,
)
from tests.agent_kernel.fixtures.oracles.source_ledger import SourceLedger

_TOKEN_FIELDS = (
    "uncached_input_tokens",
    "cached_input_tokens",
    "reasoning_tokens",
    "output_tokens",
)


def build_accounting_oracle(
    profile: FixtureProfile,
    *,
    ledger: SourceLedger,
) -> dict[str, Any]:
    """Derive accounting from emitted source bytes, never candidate SQL."""

    distribution = planned_distribution(profile)
    inputs = ledger.accounting_inputs
    call_count = int(inputs["canonical_model_calls"])
    observed_counts = dict(inputs["observed_counts"])
    observed_sums = dict(inputs["observed_sums"])
    coverage = {
        field: {
            "complete": observed_counts[field] == call_count,
            "missing_count": call_count - observed_counts[field],
            "observed_count": observed_counts[field],
        }
        for field in _TOKEN_FIELDS
    }
    exact_totals: dict[str, int | None] = {
        field: observed_sums[field] if coverage[field]["complete"] else None
        for field in _TOKEN_FIELDS
    }
    total_components = [
        exact_totals[field]
        for field in (
            "uncached_input_tokens",
            "cached_input_tokens",
            "output_tokens",
        )
    ]
    default_total = (
        None
        if any(value is None for value in total_components)
        else sum(value for value in total_components if value is not None)
    )
    exact_totals["total_tokens"] = default_total
    return {
        "canonical_counts": {
            "activities": distribution["activities"],
            "allowance_observations": distribution["allowance_observations"],
            "model_calls": call_count,
            "sessions": distribution["sessions"],
            "state_changes": distribution["state_changes"],
            "tool_invocations": distribution["tool_invocations"],
            "turns": distribution["turns"],
        },
        "measurement_coverage": coverage,
        "rate_card": {
            "configured_cost_grade": "configured_estimate",
            "estimated_credit_grade": "configured_estimate",
            "priced_calls": call_count - distribution["unpriced_calls"],
            "rate_card_revision": "synthetic-rate-card-v1",
            "unpriced_calls": distribution["unpriced_calls"],
        },
        "source_reconciliation": {
            "canonical_model_calls": call_count,
            "model_call_occurrences": ledger.stream_aggregates[
                "model_call_occurrences"
            ],
            "source_manifestations": ledger.stream_aggregates[
                "source_manifestations"
            ],
        },
        "token_formula": {
            "default_total_fields": [
                "uncached_input_tokens",
                "cached_input_tokens",
                "output_tokens",
            ],
            "reasoning_in_default_total": False,
        },
        "token_observed_sums": observed_sums,
        "token_totals": exact_totals,
    }
