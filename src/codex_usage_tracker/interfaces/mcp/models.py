"""Typed metadata for declarative MCP tool registration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from codex_usage_tracker.core.contracts.common import ToolDataClass

McpProfile = Literal["core", "full", "developer"]
ToolMaturity = Literal["stable", "beta", "experimental"]
ToolLifecycle = Literal["active", "deprecated"]
ToolDisposition = Literal["core", "compatibility", "advanced", "developer", "deprecated"]
WorkProofKind = Literal["constant", "rows", "sources", "evidence", "job"]


@dataclass(frozen=True)
class WorkProofContract:
    """Declare how a successful tool response proves useful work."""

    kind: WorkProofKind
    minimum_when_applicable: int
    applicability_field: str | None
    processed_field: str | None


@dataclass(frozen=True)
class ToolSpec:
    """Immutable registration metadata for one MCP tool."""

    name: str
    minimum_profile: McpProfile
    maturity: ToolMaturity
    lifecycle: ToolLifecycle
    disposition: ToolDisposition
    data_class: ToolDataClass
    handler: Callable[..., object]
    work_proof: WorkProofContract
    replacement: str | None = None
    deprecated_since: str | None = None
    final_supported: str | None = None
    remove_after: str | None = None
