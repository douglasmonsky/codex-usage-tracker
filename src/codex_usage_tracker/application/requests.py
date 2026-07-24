"""Validated transport-independent requests for the core application services."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TypeAlias, cast

from codex_usage_tracker.analytics.analysis_models import AnalysisRequest as AnalysisRequest
from codex_usage_tracker.application.allowance_models import AllowanceRequest as AllowanceRequest
from codex_usage_tracker.application.errors import RequestValidationError
from codex_usage_tracker.application.query_models import QueryRequest as QueryRequest
from codex_usage_tracker.core.contracts import ScopeV1
from codex_usage_tracker.core.contracts.serialization import payload_mapping
from codex_usage_tracker.core.requests import ExecutionMode, HistoryScope
from codex_usage_tracker.evidence.models import EvidenceRequest as EvidenceRequest

PrivacyMode: TypeAlias = Literal["normal", "redacted", "strict"]
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
    freshness_threshold_seconds: int | float = 300
    db_path: Path | None = None
    pricing_path: Path | None = None
    codex_home: Path | None = None
    home: Path | None = None
    mcp_profile: McpProfile = "core"

    def __post_init__(self) -> None:
        threshold = self.freshness_threshold_seconds
        if type(threshold) not in (int, float):
            raise RequestValidationError("freshness_threshold_seconds must be a number")
        if not math.isfinite(threshold):
            raise RequestValidationError("freshness_threshold_seconds must be finite")
        if threshold < 0:
            raise RequestValidationError("freshness_threshold_seconds must be non-negative")
        if threshold != int(threshold):
            raise RequestValidationError("freshness_threshold_seconds must be a whole number")
        object.__setattr__(self, "freshness_threshold_seconds", int(threshold))
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
class JobStatusRequest:
    job_id: str
    include_result: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "job_id", _safe_identifier(self.job_id, "job_id"))
