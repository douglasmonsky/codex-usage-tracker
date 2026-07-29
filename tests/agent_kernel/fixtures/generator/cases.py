from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Any

from tests.agent_kernel.contracts.reference.identity import semantic_id
from tests.agent_kernel.fixtures.generator.profile import FixtureProfile

VERTICAL_SLICES = {
    "V1": "context_deterioration",
    "V2": "workflow_sequence_first_mutation",
    "V3": "allowance_interval_accounting",
    "V4": "parent_subagent_aggregation",
    "V5": "evidence_source_lifecycle",
}
_QUESTION_SLICE = {
    "ACC": "allowance_interval_accounting",
    "ALW": "allowance_interval_accounting",
    "CTX": "context_deterioration",
    "DEL": "parent_subagent_aggregation",
    "OPS": "evidence_source_lifecycle",
    "REV": "evidence_source_lifecycle",
    "WF": "workflow_sequence_first_mutation",
}
_SELECTOR_IDENTITY_KINDS = {
    "allowance_interval": "allowance-interval",
    "allowance_observation": "allowance-observation",
    "call": "call",
    "model_profile": "model-profile",
    "project": "project",
    "publication": "publication",
    "rate_card": "rate-card",
    "resource": "resource",
    "session": "session",
    "source_manifestation": "source-manifestation",
    "state_change": "state-change",
    "tool": "tool",
    "turn": "turn",
    "window": "window",
}
_BOOLEAN_FIELDS = {
    "included_in_interval",
    "mutation_observed",
}
_DECIMAL_FIELDS = {
    "allowance_delta",
    "allowance_percent",
    "cached_output_ratio",
    "cached_share",
    "calls_per_point",
    "context_growth",
    "context_pressure",
    "cost_per_point",
    "credits_per_point",
    "failure_coverage",
    "later_earlier_ratio",
    "mutation_coverage",
    "pricing_coverage",
    "remainder_share",
    "session_concentration",
    "share",
    "tokens_per_completed_turn",
    "tokens_per_point",
    "top_share",
    "turns_per_point",
    "valuation_coverage",
}
_LIST_FIELDS = {
    "capabilities",
    "change_drivers",
    "representative_selectors",
    "structural_features",
}
_OBJECT_FIELDS = {
    "allowance_facts",
    "allowance_movement",
    "baseline",
    "boundary_compatibility",
    "candidate_features",
    "context_facts",
    "context_features",
    "delegation_metrics",
    "model_mix",
    "mutation_features",
    "observed_mutations",
    "resource_metrics",
    "state_change_metrics",
    "token_deltas",
    "tool_metrics",
    "tool_mix",
    "turn_call_counts",
    "usage_features",
    "usage_totals",
}
_STRING_FIELDS = {
    "canonical_basis": "canonical_occurrence",
    "completion_state": "succeeded",
    "current_profile": "synthetic-model-high",
    "event_kind": "model_call",
    "lifecycle_basis": "observed_terminal",
    "previous_profile": "synthetic-model-medium",
    "terminal_status": "succeeded",
}


def _stable_int(key: str, *, minimum: int = 1, width: int = 10_000) -> int:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return minimum + int.from_bytes(digest[:8], "big") % width


def selector_identities(profile: FixtureProfile) -> dict[str, str]:
    """Return the closed selector identity set emitted as real source records."""

    identities = {
        kind: semantic_id(
            identity_kind,
            ["fixture-selector", profile.seed, kind],
        )
        for kind, identity_kind in sorted(_SELECTOR_IDENTITY_KINDS.items())
    }
    identities["source_manifestation"] = semantic_id(
        "source-manifestation",
        [
            profile.seed,
            "sources/active/source-0000.jsonl",
            "revision-1",
        ],
    )
    return identities


def _case_inputs(oracle_id: str, variant_index: int) -> dict[str, Any]:
    base = _stable_int(oracle_id, minimum=101, width=8_000) + variant_index
    missing_cached = "missing" in oracle_id
    cached = None if missing_cached else base * 2
    uncached = base
    reasoning = base // 3
    output = base // 2
    current = base * 7
    previous = base * 5
    return {
        "base": base,
        "cohort_count": 2 + base % 9,
        "current": current,
        "denominator": base * 2 + variant_index + 1,
        "duration_us": base * 1_000,
        "event_time_us": 1767225600000000 + variant_index * 1_000_000 + base,
        "numerator": base,
        "previous": previous,
        "tokens": {
            "cached_input_tokens": cached,
            "output_tokens": output,
            "reasoning_tokens": reasoning,
            "uncached_input_tokens": uncached,
        },
        "variant_index": variant_index,
    }


def _decimal(value: Decimal) -> str:
    rendered = format(value.normalize(), "f")
    return "0" if rendered == "-0" else rendered


def _generic_field_value(field: str, inputs: dict[str, Any]) -> Any:
    base = int(inputs["base"])
    if field in _BOOLEAN_FIELDS:
        return field != "mutation_observed" or base % 2 == 0
    if field in _DECIMAL_FIELDS or field.endswith(("_coverage", "_ratio", "_share")):
        return _decimal(Decimal(inputs["numerator"]) / Decimal(inputs["denominator"]))
    if field in _LIST_FIELDS:
        return [f"{field}:observed:{base}", f"{field}:observed:{base + 1}"]
    if field in _OBJECT_FIELDS or field.endswith(
        ("_facts", "_features", "_metrics", "_mix", "_totals")
    ):
        return {"basis": "observed_case", "count": 1 + base % 17}
    if field in _STRING_FIELDS:
        return _STRING_FIELDS[field]
    if field.endswith(("_basis", "_state", "_status")):
        return "observed"
    if field.endswith("_profile"):
        return f"synthetic-profile-{base % 3}"
    return base


def observed_facts(
    question: dict[str, Any],
    oracle_id: str,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    """Build explicit observed case facts, preserving formula relationships."""

    fields = question["answers"]["fields"]
    values = {
        field: _generic_field_value(field, inputs)
        for field in fields
    }
    tokens = inputs["tokens"]
    uncached = tokens["uncached_input_tokens"]
    cached = tokens["cached_input_tokens"]
    reasoning = tokens["reasoning_tokens"]
    output = tokens["output_tokens"]
    total_input = None if cached is None else uncached + cached
    total = None if total_input is None else total_input + output

    direct: dict[str, Any] = {
        "after_tokens": inputs["current"],
        "before_tokens": inputs["previous"],
        "cached_input_tokens": cached,
        "calls": 1 + inputs["base"] % 23,
        "configured_cost_usd": _decimal(Decimal(inputs["base"]) / Decimal(100)),
        "context_delta": inputs["current"] - inputs["previous"],
        "current_total_tokens": inputs["current"],
        "current_uncached_input_tokens": uncached + 10,
        "driver_contribution": inputs["current"] - inputs["previous"],
        "estimated_credits": _decimal(Decimal(inputs["base"]) / Decimal(20)),
        "event_time_us": inputs["event_time_us"],
        "following_cached_input_tokens": cached,
        "following_output_tokens": output,
        "following_tokens": total,
        "following_uncached_input_tokens": uncached,
        "freshness_age_us": inputs["base"],
        "guaranteed_complete_from_us": inputs["event_time_us"],
        "input_delta": 10,
        "indexed_from_us": inputs["event_time_us"],
        "ordered_input_tokens": total_input,
        "output_tokens": output,
        "previous_total_tokens": inputs["previous"],
        "previous_uncached_input_tokens": uncached,
        "reasoning_tokens": reasoning,
        "token_delta": inputs["current"] - inputs["previous"],
        "token_measurements": dict(tokens),
        "total_delta": inputs["current"] - inputs["previous"],
        "total_input_tokens": total_input,
        "total_tokens": total,
        "uncached_input_tokens": uncached,
    }
    for field, value in direct.items():
        if field in values:
            values[field] = value
    if "cached_share" in values:
        values["cached_share"] = (
            None
            if total_input is None or cached is None
            else _decimal(Decimal(cached) / Decimal(total_input))
        )
    if "cached_output_ratio" in values:
        values["cached_output_ratio"] = (
            None
            if cached is None or output == 0
            else _decimal(Decimal(cached) / Decimal(output))
        )
    if "following_input_delta" in values:
        values["following_input_delta"] = 10
    if "second_difference" in values:
        values["second_difference"] = 0
    if "allowance_delta" in values:
        values["allowance_delta"] = _decimal(Decimal(inputs["base"]) / Decimal(100))
    if "allowance_percent" in values:
        values["allowance_percent"] = "12.75"
    return dict(sorted(values.items()))


def _parameter_inputs(
    question: dict[str, Any],
    selectors: dict[str, str],
    variant_index: int,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for parameter in question["parameters"]["required"]:
        if parameter in {"window", "current_window", "previous_window"}:
            offset = variant_index * 86_400_000_000
            values[parameter] = {
                "end_us": 1767312000000000 + offset,
                "start_us": 1767225600000000 + offset,
                "timezone": "UTC",
            }
        elif parameter in {"start_observation", "end_observation"}:
            values[parameter] = selectors["allowance_observation"]
        elif parameter.endswith(("_selector", "_session")):
            values[parameter] = selectors["session"]
        elif parameter == "timezone":
            values[parameter] = "UTC"
        elif parameter == "limit":
            values[parameter] = 10
        else:
            values[parameter] = f"synthetic-{parameter}-{variant_index}"
    return values


def question_case_records(
    profile: FixtureProfile,
    catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    """Emit one explicit structural input case for every CK-01 oracle variant."""

    identities = selector_identities(profile)
    records: list[dict[str, Any]] = []
    ordinal = 0
    for question in catalog["questions"]:
        family = question["question_id"].split("-")[1]
        for variant_index, oracle_id in enumerate(question["oracle_ids"]):
            inputs = _case_inputs(oracle_id, variant_index)
            required_kinds = question["evidence"]["selector_kinds"]
            selector_ids = {kind: identities[kind] for kind in required_kinds}
            records.append(
                {
                    "event_at_us": inputs["event_time_us"],
                    "event_kind_order": 90,
                    "payload": {
                        "caveats": [
                            f"synthetic variant: {oracle_id.rsplit(':', 1)[-1]}",
                            *question["prohibited_claims"],
                        ],
                        "contract": {
                            "answer_grades": question["answers"]["fields"],
                            "compiler_id": question["logical_plan"]["compiler_id"],
                            "formulas": question["answers"]["formulas"],
                            "logical_operations": question["logical_plan"]["operations"],
                            "logical_primitives": question["logical_plan"]["primitives"],
                            "plan_id": question["plan_id"],
                            "projection_consumers": question["projection_consumers"],
                        },
                        "inputs": {
                            **inputs,
                            "parameters": _parameter_inputs(
                                question,
                                identities,
                                variant_index,
                            ),
                        },
                        "observed_facts": observed_facts(question, oracle_id, inputs),
                        "oracle_id": oracle_id,
                        "question_id": question["question_id"],
                        "selector_ids": selector_ids,
                        "slice": _QUESTION_SLICE[family],
                        "variant": oracle_id.rsplit(":", 1)[-1],
                    },
                    "source_order": 10_000_000_000 + ordinal,
                    "type": "oracle_case",
                }
            )
            ordinal += 1
    return records


def selector_anchor_records(profile: FixtureProfile) -> list[dict[str, Any]]:
    """Emit each public selector as a coordinate-bearing structural record."""

    records: list[dict[str, Any]] = []
    for ordinal, (kind, logical_id) in enumerate(selector_identities(profile).items()):
        payload: dict[str, Any] = {
            "logical_id": logical_id,
            "selector_kind": kind,
        }
        if kind == "publication":
            payload.update(
                {
                    "publication_id": logical_id,
                    "state": "committed",
                }
            )
        elif kind == "rate_card":
            payload.update(
                {
                    "match_basis": "exact_model_profile",
                    "rate_card_id": logical_id,
                    "revision": "synthetic-rate-card-v1",
                }
            )
        elif kind == "tool":
            payload.update(
                {
                    "semantic_operation": "execute",
                    "tool_id": logical_id,
                    "transport_name": "exec_command",
                }
            )
        records.append(
            {
                "event_at_us": profile.start_at_us + ordinal,
                "event_kind_order": 5,
                "payload": payload,
                "source_order": ordinal,
                "type": "selector_anchor",
            }
        )
    return records


def control_records(profile: FixtureProfile) -> list[dict[str, Any]]:
    """Emit cross-slice contract facts that are not implied by scale ratios."""

    identities = selector_identities(profile)
    records = [
        {
            "event_at_us": profile.start_at_us + index,
            "event_kind_order": 6,
            "payload": {
                "phase": f"phase-{index + 1}",
                "slice": slice_name,
            },
            "source_order": 100 + index,
            "type": "slice_control",
        }
        for index, slice_name in enumerate(VERTICAL_SLICES.values())
    ]
    records.extend(
        [
            {
                "event_at_us": profile.start_at_us + 10,
                "event_kind_order": 7,
                "payload": {
                    "compatibility_tuple": {
                        "cycle_id": "cycle-0000",
                        "limit_id": "weekly",
                        "plan_identity": "synthetic-plan",
                        "provider": "openai",
                        "reset_identity": "reset-0000",
                        "window_kind": "rolling_week",
                    },
                    "end_observation_id": identities["allowance_observation"],
                    "start_observation_id": identities["allowance_observation"],
                },
                "source_order": 110,
                "type": "allowance_compatibility",
            },
            {
                "event_at_us": profile.start_at_us + 11,
                "event_kind_order": 8,
                "payload": {
                    "child_session_id": semantic_id(
                        "session",
                        ["late-child", profile.seed],
                    ),
                    "parent_session_id": identities["session"],
                    "transition": "parent_observed_late",
                },
                "source_order": 111,
                "type": "late_parent",
            },
        ]
    )
    return records
