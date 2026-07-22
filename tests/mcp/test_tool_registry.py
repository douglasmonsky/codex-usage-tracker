from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from codex_usage_tracker.core.contracts.common import ToolDataClass as CoreToolDataClass
from codex_usage_tracker.interfaces.mcp import core_tools
from codex_usage_tracker.interfaces.mcp.models import ToolDataClass as InterfaceToolDataClass
from codex_usage_tracker.interfaces.mcp.models import ToolSpec
from codex_usage_tracker.interfaces.mcp.registry import (
    CORE_TOOL_NAMES,
    ToolCatalogError,
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
    remove_after: str | None = None,
) -> ToolSpec:
    return ToolSpec(
        name=name,
        minimum_profile=minimum_profile,  # type: ignore[arg-type]
        maturity="stable",
        lifecycle=lifecycle,  # type: ignore[arg-type]
        data_class="aggregate",
        handler=_handler,
        replacement=replacement,
        deprecated_since=deprecated_since,
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
