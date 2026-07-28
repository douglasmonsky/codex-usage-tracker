from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.agent_kernel.contracts.reference.lifecycle import (
    LifecycleContractError,
    fold_lifecycle,
    hierarchy_usage,
)

_VECTOR_PATH = Path(__file__).with_name("vectors") / "lifecycle-v1.json"


def _vectors() -> dict[str, Any]:
    payload = json.loads(_VECTOR_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_lifecycle_fold_is_deterministic_across_publications() -> None:
    for vector in _vectors()["lifecycle_vectors"]:
        if "error" in vector:
            with pytest.raises(LifecycleContractError, match=vector["error"]):
                fold_lifecycle(vector["transitions"])
        else:
            assert fold_lifecycle(vector["transitions"]) == vector["expected"]


def test_late_parent_discovery_preserves_identity_and_reconciles_scopes() -> None:
    for vector in _vectors()["hierarchy_vectors"]:
        before = hierarchy_usage(
            vector["session_id"],
            vector["before_parent_by_session"],
            vector["exclusive_usage"],
        )
        after = hierarchy_usage(
            vector["session_id"],
            vector["after_parent_by_session"],
            vector["exclusive_usage"],
        )
        assert before == vector["expected_before"]
        assert after == vector["expected_after"]
        assert vector["session_identity_before"] == vector["session_identity_after"]


def test_hierarchy_cycles_fail_closed() -> None:
    for vector in _vectors()["invalid_hierarchy_vectors"]:
        with pytest.raises(LifecycleContractError, match=vector["error"]):
            hierarchy_usage(
                vector["session_id"],
                vector["parent_by_session"],
                vector["exclusive_usage"],
            )
