"""Typed metadata for declarative MCP tool registration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from codex_usage_tracker.core.contracts.common import ToolDataClass

McpProfile = Literal["core", "full", "developer"]
ToolMaturity = Literal["stable", "beta", "experimental"]
ToolLifecycle = Literal["active", "deprecated"]


@dataclass(frozen=True)
class ToolSpec:
    """Immutable registration metadata for one MCP tool."""

    name: str
    minimum_profile: McpProfile
    maturity: ToolMaturity
    lifecycle: ToolLifecycle
    data_class: ToolDataClass
    handler: Callable[..., object]
    replacement: str | None = None
    deprecated_since: str | None = None
    remove_after: str | None = None
