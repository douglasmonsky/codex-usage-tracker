"""Selected-profile MCP process entrypoint."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import cast

from codex_usage_tracker.application.container import build_application_container
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
from codex_usage_tracker.interfaces.mcp.models import McpProfile
from codex_usage_tracker.interfaces.mcp.runtime import build_mcp_server

PROFILE_ENV = "CODEX_USAGE_TRACKER_MCP_PROFILE"
DEFAULT_PROFILE: McpProfile = "core"
VALID_PROFILES = ("core", "full", "developer")


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
    build_mcp_server(selected_profile, container=container).run()


if __name__ == "__main__":
    main()
