"""Compatibility alias for the MCP dashboard implementation."""

from __future__ import annotations

import sys
from importlib import import_module

_dashboard = import_module("codex_usage_tracker.interfaces.mcp.mcp_dashboard")
_local_operations = import_module("codex_usage_tracker.interfaces.mcp.mcp_local_operations")
for _name in (
    "generate_usage_dashboard",
    "export_usage_csv",
    "init_usage_pricing_config",
    "init_usage_allowance_config",
    "update_usage_pricing_config",
):
    setattr(_dashboard, _name, getattr(_local_operations, _name))

sys.modules[__name__] = _dashboard
