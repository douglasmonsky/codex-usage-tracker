"""Declarative MCP tool catalog and validation."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from functools import cache, lru_cache

from codex_usage_tracker.interfaces.mcp.compatibility_tools import (
    ADVANCED_TOOL_NAMES,
    COMPATIBILITY_TOOL_NAMES,
    OVERLAPPING_CORE_TOOL_NAMES,
    compatibility_handler,
)
from codex_usage_tracker.interfaces.mcp.core_tools import (
    usage_allowance,
    usage_analyze,
    usage_evidence,
    usage_job_status,
    usage_query,
    usage_refresh,
    usage_status,
)
from codex_usage_tracker.interfaces.mcp.developer_tools import (
    DEVELOPER_TOOL_NAMES,
    developer_handler,
)
from codex_usage_tracker.interfaces.mcp.models import McpProfile, ToolDataClass, ToolSpec

PROFILE_ORDER: dict[McpProfile, int] = {"core": 0, "full": 1, "developer": 2}

CORE_TOOL_NAMES = (
    "usage_status",
    "usage_refresh",
    "usage_analyze",
    "usage_query",
    "usage_evidence",
    "usage_allowance",
    "usage_job_status",
)


class ToolCatalogError(ValueError):
    """Raised when tool metadata cannot form a safe ordered catalog."""


class CoreToolNotImplemented(NotImplementedError):
    """Compatibility exception retained for callers importing the old placeholder type."""


_CORE_HANDLERS: dict[str, Callable[..., object]] = {
    "usage_status": usage_status,
    "usage_refresh": usage_refresh,
    "usage_analyze": usage_analyze,
    "usage_query": usage_query,
    "usage_evidence": usage_evidence,
    "usage_allowance": usage_allowance,
    "usage_job_status": usage_job_status,
}


def _release_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError as exc:
        raise ToolCatalogError(f"invalid release: {value}") from exc


def validate_tool_specs(specs: Iterable[ToolSpec]) -> None:
    """Validate uniqueness, profile ordering, and deprecation metadata."""
    names: set[str] = set()
    previous_rank = -1
    for spec in specs:
        if spec.name in names:
            raise ToolCatalogError(f"duplicate tool name: {spec.name}")
        names.add(spec.name)

        rank = PROFILE_ORDER.get(spec.minimum_profile)
        if rank is None or rank < previous_rank:
            raise ToolCatalogError(f"invalid minimum-profile order: {spec.name}")
        previous_rank = rank

        if spec.minimum_profile == "core":
            if spec.disposition != "core":
                raise ToolCatalogError(f"invalid core disposition: {spec.name}")
        elif spec.disposition not in {"compatibility", "advanced", "developer", "deprecated"}:
            raise ToolCatalogError(f"missing catalog disposition: {spec.name}")
        if spec.disposition == "developer" and spec.minimum_profile != "developer":
            raise ToolCatalogError(f"invalid developer disposition: {spec.name}")

        if spec.lifecycle != "deprecated":
            continue
        if not spec.replacement:
            raise ToolCatalogError(f"missing replacement: {spec.name}")
        if not spec.deprecated_since or not spec.final_supported or not spec.remove_after:
            raise ToolCatalogError(f"missing deprecation release: {spec.name}")
        if _release_tuple(spec.remove_after) < _release_tuple(spec.deprecated_since):
            raise ToolCatalogError(f"removal release precedes deprecation release: {spec.name}")


def _data_class(name: str) -> ToolDataClass:
    if name == "usage_call_context":
        return "raw_context"
    if any(
        marker in name
        for marker in (
            "content",
            "thread_trace",
            "repetition",
            "command_loop",
            "file_churn",
            "rediscovery",
            "shell_churn",
            "investigat",
            "context_bloat",
            "local_evidence",
            "compression",
        )
    ):
        return "local_index"
    if any(
        marker in name for marker in ("refresh", "doctor", "generate", "export", "init_", "update_")
    ):
        return "administrative"
    return "aggregate"


def _replacement(name: str) -> str:
    if name in {
        "usage_refresh_status",
        "usage_allowance_analysis_status",
        "usage_compression_status",
    }:
        return "usage_job_status"
    if "allowance" in name:
        return "usage_allowance"
    if "refresh" in name:
        return "usage_refresh"
    if name == "usage_doctor" or name.endswith("status"):
        return "usage_status"
    if any(marker in name for marker in ("detail", "context", "evidence")):
        return "usage_evidence"
    if any(
        marker in name
        for marker in (
            "recommend",
            "investigat",
            "compression",
            "dogfood",
            "hypoth",
            "scan",
            "brief",
        )
    ):
        return "usage_analyze"
    return "usage_query"


@cache
def _lazy_profile_handler(name: str) -> Callable[..., object]:
    """Return a callable proxy without importing non-core handler modules."""

    def invoke(*args: object, **kwargs: object) -> object:
        if name in DEVELOPER_TOOL_NAMES:
            return developer_handler(name)(*args, **kwargs)
        return compatibility_handler(name)(*args, **kwargs)

    invoke.__name__ = name
    return invoke


@lru_cache(maxsize=1)
def tool_specs() -> tuple[ToolSpec, ...]:
    """Return the validated immutable tool catalog in registration order."""
    specs = (
        tuple(
            ToolSpec(
                name=name,
                minimum_profile="core",
                maturity="stable",
                lifecycle="active",
                disposition="core",
                data_class=(
                    "administrative"
                    if name in {"usage_status", "usage_refresh", "usage_job_status"}
                    else "aggregate"
                ),
                handler=_CORE_HANDLERS[name],
            )
            for name in CORE_TOOL_NAMES
        )
        + tuple(_full_tool_spec(name) for name in COMPATIBILITY_TOOL_NAMES)
        + tuple(
            ToolSpec(
                name=name,
                minimum_profile="developer",
                maturity="experimental",
                lifecycle="active",
                disposition="developer",
                data_class=_data_class(name),
                handler=_lazy_profile_handler(name),
            )
            for name in DEVELOPER_TOOL_NAMES
        )
    )
    validate_tool_specs(specs)
    return specs


def handler_for_profile(spec: ToolSpec, profile: McpProfile) -> Callable[..., object]:
    """Preserve existing overlapping handlers outside the core-only server."""
    if profile == "core":
        return spec.handler
    if spec.name in OVERLAPPING_CORE_TOOL_NAMES or spec.minimum_profile == "full":
        return compatibility_handler(spec.name)
    if spec.minimum_profile == "developer":
        return developer_handler(spec.name)
    return spec.handler


def _full_tool_spec(name: str) -> ToolSpec:
    advanced = name in ADVANCED_TOOL_NAMES
    return ToolSpec(
        name=name,
        minimum_profile="full",
        maturity="beta",
        lifecycle="active" if advanced else "deprecated",
        disposition="advanced" if advanced else "compatibility",
        data_class=_data_class(name),
        handler=_lazy_profile_handler(name),
        replacement=None if advanced else _replacement(name),
        deprecated_since=None if advanced else "0.22.0",
        final_supported=None if advanced else "0.24.x",
        remove_after=None if advanced else "0.25.0",
    )
