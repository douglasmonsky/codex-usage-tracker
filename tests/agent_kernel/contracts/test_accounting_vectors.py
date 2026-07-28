from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.agent_kernel.contracts.reference.accounting import (
    AccountingContractError,
    aggregate_measurement,
    measurement_mask,
    token_totals,
    tool_outcome_counts,
    validate_measurement_record,
)

_VECTOR_PATH = Path(__file__).with_name("vectors") / "accounting-v1.json"


def _vectors() -> dict[str, Any]:
    payload = json.loads(_VECTOR_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_four_token_classes_never_double_count_cached_or_reasoning() -> None:
    for vector in _vectors()["token_vectors"]:
        if "error" in vector:
            with pytest.raises(AccountingContractError, match=vector["error"]):
                token_totals(vector["tokens"])
        else:
            assert token_totals(vector["tokens"]) == vector["expected"]


def test_missing_measurements_never_become_zero() -> None:
    for vector in _vectors()["aggregation_vectors"]:
        assert aggregate_measurement(vector["values"]) == vector["expected"]


def test_measurement_masks_grades_and_bases_are_consistent() -> None:
    payload = _vectors()
    bit_positions = payload["measurement_bits"]

    for vector in payload["measurement_vectors"]:
        mask = measurement_mask(vector["available"], bit_positions)
        assert mask == vector["expected_mask"]
        if vector["valid"]:
            validate_measurement_record(
                vector["record"],
                mask=mask,
                bit_positions=bit_positions,
            )
        else:
            with pytest.raises(AccountingContractError, match=vector["error"]):
                validate_measurement_record(
                    vector["record"],
                    mask=mask,
                    bit_positions=bit_positions,
                )


def test_tool_intent_completion_and_observed_mutation_stay_separate() -> None:
    for vector in _vectors()["tool_outcome_vectors"]:
        assert tool_outcome_counts(vector["records"]) == vector["expected"]
