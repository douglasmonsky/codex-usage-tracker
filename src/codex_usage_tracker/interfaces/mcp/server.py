"""Selected-profile MCP server factory and process entrypoint."""

from __future__ import annotations

import os
from collections.abc import Mapping
from inspect import getdoc
from typing import cast

from codex_usage_tracker.application.container import (
    ApplicationContainer,
    build_application_container,
)
from codex_usage_tracker.application.paths import ApplicationPaths
from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_CODEX_HOME,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_PROJECTS_PATH,
    DEFAULT_RATE_CARD_PATH,
    DEFAULT_THRESHOLDS_PATH,
)
from codex_usage_tracker.interfaces.mcp.models import McpProfile, ToolSpec
from codex_usage_tracker.interfaces.mcp.transports import run_stdio
from mcp.server.fastmcp import FastMCP

PROFILE_ENV = "CODEX_USAGE_TRACKER_MCP_PROFILE"
DEFAULT_PROFILE: McpProfile = "core"
VALID_PROFILES = ("core", "full", "developer")


def create_mcp_server(
    *,
    profile: McpProfile,
    container: ApplicationContainer | None = None,
) -> FastMCP:
    """Build an isolated server containing exactly one selected profile."""
    from codex_usage_tracker.interfaces.mcp.profiles import tools_for_profile
    from codex_usage_tracker.interfaces.mcp.registry import (
        bound_core_handlers,
        handler_for_profile,
    )

    server = FastMCP("codex-usage-tracker")
    bound = bound_core_handlers(container) if profile == "core" and container is not None else None
    for spec in tools_for_profile(profile):
        handler = bound[spec.name] if bound is not None else handler_for_profile(spec, profile)
        server.add_tool(
            handler,
            name=spec.name,
            description=_tool_description(spec, handler),
        )
    return server


def build_mcp_server(
    profile: McpProfile,
    *,
    container: ApplicationContainer | None = None,
) -> FastMCP:
    """Retain the pre-0.24 factory name for compatibility."""
    return create_mcp_server(profile=profile, container=container)


def configured_profile(environ: Mapping[str, str] | None = None) -> McpProfile:
    """Return the selected profile, rejecting unknown values before MCP startup."""
    source = os.environ if environ is None else environ
    value = source.get(PROFILE_ENV, DEFAULT_PROFILE)
    if value not in VALID_PROFILES:
        choices = ", ".join(VALID_PROFILES)
        raise ValueError(f"Invalid {PROFILE_ENV}={value!r}; expected one of: {choices}.")
    return cast(McpProfile, value)


def main(profile: McpProfile | None = None) -> None:
    """Run exactly one MCP profile selected explicitly or through the environment."""
    try:
        selected_profile = configured_profile() if profile is None else profile
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    container = build_application_container(
        ApplicationPaths(
            codex_home=DEFAULT_CODEX_HOME,
            db_path=DEFAULT_DB_PATH,
            pricing_path=DEFAULT_PRICING_PATH,
            allowance_path=DEFAULT_ALLOWANCE_PATH,
            rate_card_path=DEFAULT_RATE_CARD_PATH,
            thresholds_path=DEFAULT_THRESHOLDS_PATH,
            projects_path=DEFAULT_PROJECTS_PATH,
        )
    )
    run_stdio(create_mcp_server(profile=selected_profile, container=container))


def _tool_description(spec: ToolSpec, handler: object) -> str:
    description = getdoc(handler) or f"Run {spec.name}."
    if spec.lifecycle != "deprecated":
        return description
    return (
        f"{description} Deprecated since {spec.deprecated_since}; use "
        f"{spec.replacement} instead. Supported through {spec.final_supported}; "
        f"earliest removal is {spec.remove_after}."
    )


if __name__ == "__main__":
    main()
