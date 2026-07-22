"""Validated transport-independent requests for the core application services."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TypeAlias, cast

from codex_usage_tracker.application.errors import RequestValidationError
from codex_usage_tracker.core.contracts import ScopeV1
from codex_usage_tracker.core.contracts.common import immutable_snapshot
from codex_usage_tracker.core.contracts.serialization import payload_mapping
from codex_usage_tracker.core.paths import DEFAULT_CODEX_HOME, DEFAULT_DB_PATH, DEFAULT_PRICING_PATH

HistoryScope: TypeAlias = Literal["active", "all"]
PrivacyMode: TypeAlias = Literal["normal", "redacted", "strict"]
ExecutionMode: TypeAlias = Literal["auto", "sync", "async"]
McpProfile: TypeAlias = Literal["core", "full", "developer"]

MAX_INTERACTIVE_LIMIT = 200
_HISTORY_VALUES = {"active", "all"}
_PRIVACY_VALUES = {"normal", "redacted", "strict"}
_EXECUTION_VALUES = {"auto", "sync", "async"}
_MCP_PROFILE_VALUES = {"core", "full", "developer"}


def _choice(value: str, choices: set[str], field_name: str) -> None:
    if value not in choices:
        raise RequestValidationError(f"unsupported {field_name}: {value}")


def _bounded_limit(value: object, *, field_name: str = "limit") -> None:
    if type(value) is not int:
        raise RequestValidationError(f"{field_name} must be an integer")
    if not 1 <= cast(int, value) <= MAX_INTERACTIVE_LIMIT:
        raise RequestValidationError(f"{field_name} must be between 1 and {MAX_INTERACTIVE_LIMIT}")


def _safe_identifier(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise RequestValidationError(f"{field_name} must not be empty")
    if (
        len(normalized) > 512
        or any(ord(character) < 32 for character in normalized)
        or ".." in normalized
        or "/" in normalized
        or "\\" in normalized
    ):
        raise RequestValidationError(f"{field_name} contains unsafe characters")
    return normalized


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _parse_datetime(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RequestValidationError(f"{field_name} must be an ISO-8601 date or datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_datetime(value: str | None, field_name: str) -> tuple[str | None, datetime | None]:
    if value is None:
        return None, None
    parsed = _parse_datetime(value.strip(), field_name)
    normalized = parsed.isoformat().replace("+00:00", "Z")
    return normalized, parsed


def _mapping_snapshot(value: Mapping[str, object]) -> Mapping[str, object]:
    return cast(Mapping[str, object], immutable_snapshot(value))


@dataclass(frozen=True)
class RequestScope:
    """Normalized filters shared by application requests."""

    since: str | None = None
    until: str | None = None
    history: HistoryScope = "active"
    privacy_mode: PrivacyMode = "normal"
    project: str | None = None
    thread_key: str | None = None
    model: str | None = None
    effort: str | None = None

    def __post_init__(self) -> None:
        _choice(self.history, _HISTORY_VALUES, "history")
        _choice(self.privacy_mode, _PRIVACY_VALUES, "privacy_mode")
        since, since_value = _normalize_datetime(self.since, "since")
        until, until_value = _normalize_datetime(self.until, "until")
        if since_value is not None and until_value is not None and since_value > until_value:
            raise RequestValidationError("since must not be after until")
        object.__setattr__(self, "since", since)
        object.__setattr__(self, "until", until)
        object.__setattr__(self, "project", _optional_text(self.project))
        object.__setattr__(self, "model", _optional_text(self.model))
        object.__setattr__(self, "effort", _optional_text(self.effort))
        if self.thread_key is not None:
            object.__setattr__(
                self,
                "thread_key",
                _safe_identifier(self.thread_key, "thread_key"),
            )

    def to_contract(self) -> ScopeV1:
        """Return the shared deterministic envelope scope contract."""
        filters = {
            key: value
            for key, value in (
                ("project", self.project),
                ("thread_key", self.thread_key),
                ("model", self.model),
                ("effort", self.effort),
            )
            if value is not None
        }
        return ScopeV1(
            since=self.since,
            until=self.until,
            history=self.history,
            privacy_mode=self.privacy_mode,
            filters=filters,
        )

    def to_payload(self) -> dict[str, object]:
        """Serialize the normalized scope with deterministic key ordering."""
        return payload_mapping(self.to_contract())


@dataclass(frozen=True)
class StatusRequest:
    scope: RequestScope = field(default_factory=RequestScope)
    freshness_threshold_seconds: float = 300.0
    db_path: Path = DEFAULT_DB_PATH
    pricing_path: Path = DEFAULT_PRICING_PATH
    codex_home: Path = DEFAULT_CODEX_HOME
    home: Path = field(default_factory=Path.home)
    mcp_profile: McpProfile = "core"

    def __post_init__(self) -> None:
        threshold = self.freshness_threshold_seconds
        if type(threshold) not in (int, float):
            raise RequestValidationError("freshness_threshold_seconds must be a number")
        if not math.isfinite(threshold):
            raise RequestValidationError("freshness_threshold_seconds must be finite")
        if threshold < 0:
            raise RequestValidationError("freshness_threshold_seconds must be non-negative")
        _choice(self.mcp_profile, _MCP_PROFILE_VALUES, "mcp_profile")


@dataclass(frozen=True)
class RefreshRequest:
    history: HistoryScope = "active"
    aggregate_only: bool = True
    execution: ExecutionMode = "auto"

    def __post_init__(self) -> None:
        _choice(self.history, _HISTORY_VALUES, "history")
        _choice(self.execution, _EXECUTION_VALUES, "execution")


@dataclass(frozen=True)
class AnalysisRequest:
    goal: str
    filters: Mapping[str, object] = field(default_factory=dict)
    history: HistoryScope = "active"
    evidence_limit: int = 8
    comparison: Mapping[str, object] | None = None
    execution: ExecutionMode = "auto"

    def __post_init__(self) -> None:
        if not self.goal.strip():
            raise RequestValidationError("goal must not be empty")
        _choice(self.history, _HISTORY_VALUES, "history")
        _choice(self.execution, _EXECUTION_VALUES, "execution")
        _bounded_limit(self.evidence_limit, field_name="evidence_limit")
        object.__setattr__(self, "goal", self.goal.strip())
        object.__setattr__(self, "filters", _mapping_snapshot(self.filters))
        if self.comparison is not None:
            object.__setattr__(self, "comparison", _mapping_snapshot(self.comparison))


@dataclass(frozen=True)
class QueryRequest:
    entity: str
    measures: tuple[str, ...]
    filters: Mapping[str, object] = field(default_factory=dict)
    group_by: tuple[str, ...] = ()
    order_by: str | None = None
    order: Literal["asc", "desc"] = "desc"
    limit: int = 20
    cursor: str | None = None
    history: HistoryScope = "active"

    def __post_init__(self) -> None:
        if not self.entity.strip():
            raise RequestValidationError("entity must not be empty")
        if not self.measures:
            raise RequestValidationError("measures must not be empty")
        _choice(self.order, {"asc", "desc"}, "order")
        _choice(self.history, _HISTORY_VALUES, "history")
        _bounded_limit(self.limit)
        object.__setattr__(self, "entity", self.entity.strip())
        object.__setattr__(self, "measures", tuple(self.measures))
        object.__setattr__(self, "filters", _mapping_snapshot(self.filters))
        object.__setattr__(self, "group_by", tuple(self.group_by))
        object.__setattr__(self, "order_by", _optional_text(self.order_by))


@dataclass(frozen=True)
class EvidenceRequest:
    record_id: str
    section: str = "summary"
    limit: int = 20
    cursor: str | None = None
    history: HistoryScope = "active"

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_id", _safe_identifier(self.record_id, "record_id"))
        object.__setattr__(self, "section", _safe_identifier(self.section, "section"))
        _bounded_limit(self.limit)
        _choice(self.history, _HISTORY_VALUES, "history")


@dataclass(frozen=True)
class AllowanceRequest:
    operation: Literal["status", "series", "evidence", "analysis"]
    window: Literal["weekly", "five_hour"] = "weekly"
    range: str = "8w"
    cursor: str | None = None
    limit: int = 50
    analysis_id: str | None = None
    execution: ExecutionMode = "auto"

    def __post_init__(self) -> None:
        _choice(self.operation, {"status", "series", "evidence", "analysis"}, "operation")
        _choice(self.window, {"weekly", "five_hour"}, "window")
        _choice(self.execution, _EXECUTION_VALUES, "execution")
        _bounded_limit(self.limit)
        object.__setattr__(self, "range", _safe_identifier(self.range, "range"))
        if self.analysis_id is not None:
            object.__setattr__(
                self,
                "analysis_id",
                _safe_identifier(self.analysis_id, "analysis_id"),
            )


@dataclass(frozen=True)
class JobStatusRequest:
    job_id: str
    include_result: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "job_id", _safe_identifier(self.job_id, "job_id"))
