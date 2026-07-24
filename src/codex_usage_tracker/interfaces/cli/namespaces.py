"""Public CLI inventory and compatibility aliases."""

from __future__ import annotations

STABLE_TOP_LEVEL_COMMANDS = (
    "setup",
    "status",
    "doctor",
    "refresh",
    "analyze",
    "query",
    "open",
    "export",
    "config",
    "service",
    "admin",
)

CONFIG_COMMANDS = ("pricing", "allowance", "rate-card", "projects", "thresholds")
SERVICE_COMMANDS = ("install", "status", "uninstall", "serve")
ADMIN_COMMANDS = (
    "integrity",
    "inspect-log",
    "rebuild-index",
    "reset-db",
    "dedupe-diagnostics",
    "source-coverage",
    "support-bundle",
    "dogfood",
    "mcp",
)

# These names remain accepted through 0.24, but are intentionally absent from
# the primary help inventory. Existing stable spellings are not aliases.
LEGACY_TOP_LEVEL_ALIASES = (
    "install-plugin",
    "upgrade-plugin",
    "uninstall-plugin",
    "inspect-log",
    "rebuild-index",
    "dogfood-agentic",
    "reset-db",
    "summary",
    "subagents",
    "recommendations",
    "action-brief",
    "diagnostics",
    "session",
    "context",
    "dashboard",
    "open-dashboard",
    "serve-dashboard",
    "dashboard-service",
    "dedupe-diagnostics",
    "expensive",
    "pricing-coverage",
    "source-coverage",
    "init-pricing",
    "update-pricing",
    "pin-pricing",
    "init-allowance",
    "parse-allowance",
    "allowance-history",
    "allowance-diagnostics",
    "allowance-export",
    "update-rate-card",
    "init-thresholds",
    "init-projects",
    "support-bundle",
)
