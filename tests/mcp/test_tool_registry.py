from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from codex_usage_tracker.core.contracts.common import ToolDataClass as CoreToolDataClass
from codex_usage_tracker.interfaces.mcp import core_tools
from codex_usage_tracker.interfaces.mcp.models import ToolDataClass as InterfaceToolDataClass
from codex_usage_tracker.interfaces.mcp.models import ToolSpec, WorkProofContract
from codex_usage_tracker.interfaces.mcp.registry import (
    CORE_TOOL_NAMES,
    ToolCatalogError,
    _work_proof,
    tool_specs,
    validate_tool_specs,
)


def _handler() -> object:
    return {}


def _spec(
    name: str,
    minimum_profile: str,
    *,
    lifecycle: str = "active",
    replacement: str | None = None,
    deprecated_since: str | None = None,
    final_supported: str | None = None,
    remove_after: str | None = None,
    work_proof: WorkProofContract | None = None,
) -> ToolSpec:
    return ToolSpec(
        name=name,
        minimum_profile=minimum_profile,  # type: ignore[arg-type]
        maturity="stable",
        lifecycle=lifecycle,  # type: ignore[arg-type]
        disposition=(
            "core"
            if minimum_profile == "core"
            else "developer"
            if minimum_profile == "developer"
            else "compatibility"
        ),
        data_class="aggregate",
        handler=_handler,
        work_proof=work_proof or WorkProofContract("constant", 0, None, None),
        replacement=replacement,
        deprecated_since=deprecated_since,
        final_supported=final_supported,
        remove_after=remove_after,
    )


def test_tool_specs_are_frozen_and_catalog_names_are_unique() -> None:
    specs = tool_specs()

    assert len({spec.name for spec in specs}) == len(specs)
    with pytest.raises(FrozenInstanceError):
        specs[0].name = "changed"  # type: ignore[misc]


def test_tool_data_class_is_reexported_from_the_core_contract() -> None:
    assert InterfaceToolDataClass is CoreToolDataClass


def test_deprecated_specs_have_complete_migration_metadata() -> None:
    for spec in tool_specs():
        if spec.lifecycle == "deprecated":
            assert spec.replacement
            assert spec.deprecated_since
            assert spec.final_supported
            assert spec.remove_after


def test_all_seven_core_handlers_are_concrete_stable_adapters() -> None:
    core_specs = [spec for spec in tool_specs() if spec.minimum_profile == "core"]

    assert len(core_specs) == 7
    assert [spec.name for spec in core_specs] == list(CORE_TOOL_NAMES)
    assert all(callable(spec.handler) for spec in core_specs)
    assert all(spec.handler is getattr(core_tools, spec.name) for spec in core_specs)


@pytest.mark.parametrize(
    ("specs", "match"),
    [
        ((_spec("same", "core"), _spec("same", "full")), "duplicate tool name: same"),
        (
            (_spec("negative", "core", work_proof=WorkProofContract("rows", -1, None, "rows")),),
            "invalid work-proof minimum: negative",
        ),
        (
            (
                _spec(
                    "constant",
                    "core",
                    work_proof=WorkProofContract("constant", 0, None, "result"),
                ),
            ),
            "invalid constant work proof: constant",
        ),
        (
            (_spec("rows", "core", work_proof=WorkProofContract("rows", 0, None, None)),),
            "invalid measured work proof: rows",
        ),
        ((_spec("old", "full", lifecycle="deprecated"),), "missing replacement: old"),
        ((_spec("advanced", "developer"), _spec("basic", "core")), "invalid minimum-profile order"),
        (
            (
                _spec(
                    "old",
                    "full",
                    lifecycle="deprecated",
                    replacement="usage_query",
                    deprecated_since="0.24.0",
                    final_supported="0.24.x",
                    remove_after="0.23.0",
                ),
            ),
            "removal release precedes deprecation release: old",
        ),
    ],
)
def test_catalog_validation_reports_specific_errors(
    specs: tuple[ToolSpec, ...],
    match: str,
) -> None:
    with pytest.raises(ToolCatalogError, match=match):
        validate_tool_specs(specs)


def test_unknown_tool_cannot_silently_fall_back_to_constant_work() -> None:
    with pytest.raises(ToolCatalogError, match="missing work-proof contract: unknown"):
        _work_proof("unknown")
