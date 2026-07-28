from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.agent_kernel.contracts.reference.allowance import (
    AllowanceContractError,
    allowance_interval,
    canonical_decimal,
    current_valuation,
)

_VECTOR_PATH = Path(__file__).with_name("vectors") / "allowance-v1.json"


def _vectors() -> dict[str, Any]:
    payload = json.loads(_VECTOR_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_allowance_intervals_require_compatible_adjacent_observations() -> None:
    for vector in _vectors()["interval_vectors"]:
        if "error" in vector:
            with pytest.raises(AllowanceContractError, match=vector["error"]):
                allowance_interval(vector["start"], vector["end"])
        else:
            assert allowance_interval(vector["start"], vector["end"]) == vector["expected"]


def test_zero_negative_reset_or_incompatible_deltas_have_no_ratio() -> None:
    for vector in _vectors()["ratio_vectors"]:
        interval = allowance_interval(vector["start"], vector["end"])
        assert interval["percent_delta"] == vector["expected_percent_delta"]
        assert interval["ratio_eligible"] is vector["expected_ratio_eligible"]


def test_current_valuation_reports_partial_and_unpriced_coverage() -> None:
    for vector in _vectors()["valuation_vectors"]:
        if "error" in vector:
            with pytest.raises(AllowanceContractError, match=vector["error"]):
                current_valuation(vector["tokens"], vector["rate_card"])
        else:
            assert current_valuation(vector["tokens"], vector["rate_card"]) == vector[
                "expected"
            ]


def test_decimal_strings_round_trip_and_enforce_domains() -> None:
    for vector in _vectors()["decimal_vectors"]:
        if "error" in vector:
            with pytest.raises(AllowanceContractError, match=vector["error"]):
                canonical_decimal(
                    vector["value"],
                    vector["field"],
                    minimum=vector.get("minimum"),
                    maximum=vector.get("maximum"),
                )
        else:
            assert canonical_decimal(
                vector["value"],
                vector["field"],
                minimum=vector.get("minimum"),
                maximum=vector.get("maximum"),
            ) == vector["expected"]
