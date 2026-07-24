"""Compatibility alias for the MCP compression implementation."""

from __future__ import annotations

import sys
from importlib import import_module

sys.modules[__name__] = import_module("codex_usage_tracker.interfaces.mcp.mcp_compression")
