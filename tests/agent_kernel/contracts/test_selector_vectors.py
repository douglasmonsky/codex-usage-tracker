from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.agent_kernel.contracts.reference.selectors import (
    SelectorContractError,
    format_selector,
    parse_selector,
    resolve_alias,
    validate_publication_snapshot,
)

_VECTOR_PATH = Path(__file__).with_name("vectors") / "selector-v1.json"


def _vectors() -> dict[str, Any]:
    payload = json.loads(_VECTOR_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_selectors_round_trip_and_remain_stable_after_rebuild_or_replacement() -> None:
    for vector in _vectors()["selector_vectors"]:
        selector = format_selector(
            vector["kind"],
            vector["logical_id"],
            vector["prefixes"],
            vector["identity_kinds"],
        )
        assert selector == vector["expected_selector"]
        assert parse_selector(
            selector,
            vector["prefixes"],
            vector["identity_kinds"],
        ) == (vector["kind"], vector["logical_id"])
        assert selector == vector["selector_after_rebuild"]
        assert vector["old_coordinate"] != vector["replacement_coordinate"]


def test_selector_and_alias_shape_errors_fail_closed() -> None:
    payload = _vectors()
    for vector in payload["invalid_selector_vectors"]:
        with pytest.raises(SelectorContractError, match=vector["error"]):
            parse_selector(
                vector["selector"],
                payload["prefixes"],
                payload["identity_kinds"],
            )
    for vector in payload["alias_vectors"]:
        if "error" in vector:
            with pytest.raises(SelectorContractError, match=vector["error"]):
                resolve_alias(vector["selector"], vector["aliases"], vector["entities"])
        else:
            assert resolve_alias(
                vector["selector"],
                vector["aliases"],
                vector["entities"],
            ) == vector["expected"]


def test_publication_snapshot_reads_one_committed_truth_unit() -> None:
    for vector in _vectors()["publication_vectors"]:
        if "error" in vector:
            with pytest.raises(SelectorContractError, match=vector["error"]):
                validate_publication_snapshot(vector["publication"], vector["rows"])
        else:
            assert validate_publication_snapshot(
                vector["publication"],
                vector["rows"],
            ) == vector["expected_publication_id"]
