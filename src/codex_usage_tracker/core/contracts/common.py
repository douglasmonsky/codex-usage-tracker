"""Shared MCP scope, freshness, accounting, message, and action contracts."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, TypeAlias, cast

ToolDataClass: TypeAlias = Literal["aggregate", "local_index", "raw_context", "administrative"]
FreshnessState: TypeAlias = Literal["fresh", "aging", "stale", "empty", "unknown"]
MessageSeverity: TypeAlias = Literal["info", "warning", "blocking"]
MetricValue: TypeAlias = int | float | str | None

_MESSAGE_CODE_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*\Z")


def immutable_snapshot(value: object) -> object:
    """Recursively detach JSON-like mappings and sequences from caller-owned values."""
    if isinstance(value, Mapping):
        snapshot: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("mapping keys must be strings")
            snapshot[key] = immutable_snapshot(item)
        return MappingProxyType(snapshot)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(immutable_snapshot(item) for item in value)
    return value


def _require_choice(value: str, choices: set[str], name: str) -> None:
    if value not in choices:
        raise ValueError(f"{name} must be one of {sorted(choices)}")


def _require_nonnegative(value: int | None, name: str) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{name} must be non-negative")


def _require_coverage(value: float | None, name: str) -> None:
    if value is not None and not 0 <= value <= 1:
        raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True)
class ScopeV1:
    """Normalized time, history, privacy, and filter scope."""

    schema: Literal["codex-usage-tracker.scope.v1"] = field(
        default="codex-usage-tracker.scope.v1", init=False
    )
    since: str | None
    until: str | None
    history: str
    privacy_mode: str
    filters: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "filters",
            cast(Mapping[str, object], immutable_snapshot(self.filters)),
        )


@dataclass(frozen=True)
class FreshnessV1:
    """Source freshness and recommended refresh behavior."""

    schema: Literal["codex-usage-tracker.freshness.v1"] = field(
        default="codex-usage-tracker.freshness.v1", init=False
    )
    latest_indexed_event_at: str | None
    source_revision: str | None
    refresh_completed_at: str | None
    state: FreshnessState
    reason: str | None
    threshold_seconds: int | None
    recommended_refresh_action: str | None

    def __post_init__(self) -> None:
        _require_choice(self.state, {"fresh", "aging", "stale", "empty", "unknown"}, "state")
        _require_nonnegative(self.threshold_seconds, "threshold_seconds")


@dataclass(frozen=True)
class AccountingContextV1:
    """Canonical accounting, coverage, history, and privacy context."""

    schema: Literal["codex-usage-tracker.accounting-context.v1"] = field(
        default="codex-usage-tracker.accounting-context.v1", init=False
    )
    physical_rows: int | None
    canonical_rows: int | None
    copied_rows_excluded: int | None
    pricing_coverage: float | None
    credit_coverage: float | None
    service_tier_coverage: float | None
    history_scope: str | None
    privacy_mode: str | None

    def __post_init__(self) -> None:
        _require_nonnegative(self.physical_rows, "physical_rows")
        _require_nonnegative(self.canonical_rows, "canonical_rows")
        _require_nonnegative(self.copied_rows_excluded, "copied_rows_excluded")
        _require_coverage(self.pricing_coverage, "pricing_coverage")
        _require_coverage(self.credit_coverage, "credit_coverage")
        _require_coverage(self.service_tier_coverage, "service_tier_coverage")


@dataclass(frozen=True)
class MessageV1:
    """Stable warning or limitation message."""

    schema: Literal["codex-usage-tracker.message.v1"] = field(
        default="codex-usage-tracker.message.v1", init=False
    )
    code: str
    severity: MessageSeverity
    message: str
    remediation: str | None = None

    def __post_init__(self) -> None:
        if not _MESSAGE_CODE_PATTERN.fullmatch(self.code):
            raise ValueError("code must be a stable message code")
        _require_choice(self.severity, {"info", "warning", "blocking"}, "severity")
        if not self.message:
            raise ValueError("message must not be empty")


@dataclass(frozen=True)
class NextActionV1:
    """Bounded next action suitable for an agent or client."""

    schema: Literal["codex-usage-tracker.next-action.v1"] = field(
        default="codex-usage-tracker.next-action.v1", init=False
    )
    code: str
    label: str
    tool: str | None
    arguments: Mapping[str, object]

    def __post_init__(self) -> None:
        if not _MESSAGE_CODE_PATTERN.fullmatch(self.code):
            raise ValueError("code must be a stable message code")
        object.__setattr__(
            self,
            "arguments",
            cast(Mapping[str, object], immutable_snapshot(self.arguments)),
        )
