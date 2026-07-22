"""Typed metadata for declarative MCP tool registration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

McpProfile = Literal["core", "full", "developer"]
ToolMaturity = Literal["stable", "beta", "experimental"]
ToolLifecycle = Literal["active", "deprecated"]
ToolDataClass = Literal["aggregate", "local_index", "raw_context", "administrative"]


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
