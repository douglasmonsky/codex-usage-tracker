"""Lean public catalogs used by installed-package smoke tests."""

from __future__ import annotations

CLI_HELP_SUBCOMMANDS = (
    "setup",
    "status",
    "refresh",
    "query",
    "export",
    "open",
    "service",
    "config",
    "repair",
    "package",
)

MCP_TOOLS = (
    "usage_status",
    "usage_refresh",
    "usage_query",
    "usage_evidence",
    "usage_allowance",
    "usage_job_status",
)

RESOURCE_PATHS = (
    "codex_usage_tracker/kernel/interfaces/schemas/usage_allowance.json",
    "codex_usage_tracker/kernel/interfaces/schemas/usage_evidence.json",
    "codex_usage_tracker/kernel/interfaces/schemas/usage_job_status.json",
    "codex_usage_tracker/kernel/interfaces/schemas/usage_query.json",
    "codex_usage_tracker/kernel/interfaces/schemas/usage_refresh.json",
    "codex_usage_tracker/kernel/interfaces/schemas/usage_status.json",
    "codex_usage_tracker/kernel/interfaces/http/console_assets/app.js",
    "codex_usage_tracker/kernel/interfaces/http/console_assets/asset-manifest.json",
    "codex_usage_tracker/kernel/interfaces/http/console_assets/index.html",
    "codex_usage_tracker/kernel/interfaces/http/console_assets/model.js",
    "codex_usage_tracker/kernel/interfaces/http/console_assets/styles.css",
)
