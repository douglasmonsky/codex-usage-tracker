from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from codex_usage_tracker.core.contracts import MessageV1, ScopeV1
from codex_usage_tracker.core.contracts.serialization import payload_mapping


def test_common_contracts_are_frozen_and_serialize_with_sorted_keys() -> None:
    scope = ScopeV1(
        since="2026-07-01T00:00:00Z",
        until=None,
        history="active",
        privacy_mode="strict",
        filters={"zeta": 2, "alpha": {"second": 2, "first": 1}},
    )

    with pytest.raises(FrozenInstanceError):
        scope.history = "all"  # type: ignore[misc]

    payload = payload_mapping(scope)

    assert list(payload) == sorted(payload)
    assert list(payload["filters"]) == ["alpha", "zeta"]
    assert list(payload["filters"]["alpha"]) == ["first", "second"]


def test_message_codes_are_stable_machine_codes() -> None:
    message = MessageV1(
        code="source.stale",
        severity="warning",
        message="The local index is stale.",
        remediation="Refresh the index.",
    )

    assert payload_mapping(message)["code"] == "source.stale"
    with pytest.raises(ValueError, match="stable message code"):
        MessageV1(code="Source Stale", severity="warning", message="stale")


def test_core_contracts_never_import_upward_layers() -> None:
    contract_root = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "codex_usage_tracker"
        / "core"
        / "contracts"
    )
    for path in contract_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("codex_usage_tracker"):
                    assert node.module.startswith("codex_usage_tracker.core")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("codex_usage_tracker"):
                        assert alias.name.startswith("codex_usage_tracker.core")
