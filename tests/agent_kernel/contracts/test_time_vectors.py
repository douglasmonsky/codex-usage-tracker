from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.agent_kernel.contracts.reference.time import (
    TimeContractError,
    ensure_int64,
    event_order_key,
    local_datetime_to_utc_us,
    parse_instant_us,
)

_VECTOR_PATH = Path(__file__).with_name("vectors") / "time-v1.json"


def _vectors() -> dict[str, Any]:
    payload = json.loads(_VECTOR_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_exact_instants_use_signed_utc_microseconds() -> None:
    for vector in _vectors()["instant_vectors"]:
        if "error" in vector:
            with pytest.raises(TimeContractError, match=vector["error"]):
                parse_instant_us(vector["instant"])
        else:
            assert parse_instant_us(vector["instant"]) == vector["expected_us"]


def test_calendar_conversion_handles_dst_ambiguity_and_gaps_explicitly() -> None:
    for vector in _vectors()["calendar_vectors"]:
        if "error" in vector:
            with pytest.raises(TimeContractError, match=vector["error"]):
                local_datetime_to_utc_us(
                    vector["local"],
                    vector["timezone"],
                    fold=vector.get("fold"),
                )
        else:
            assert (
                local_datetime_to_utc_us(
                    vector["local"],
                    vector["timezone"],
                    fold=vector.get("fold"),
                )
                == vector["expected_us"]
            )


def test_int64_boundaries_and_overflow_fail_closed() -> None:
    for vector in _vectors()["integer_vectors"]:
        if vector["valid"]:
            assert ensure_int64(vector["value"]) == vector["value"]
        else:
            with pytest.raises(TimeContractError, match="signed 64-bit"):
                ensure_int64(vector["value"])


def test_total_order_is_stable_for_ties_late_events_and_missing_time() -> None:
    for vector in _vectors()["ordering_vectors"]:
        ordered = sorted(vector["events"], key=event_order_key)
        assert [event["logical_id"] for event in ordered] == vector["expected_ids"]
