"""Canonical requests and outcomes for allowance application operations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias

from codex_usage_tracker.application.errors import RequestValidationError

AllowanceOperation: TypeAlias = Literal["status", "series", "evidence", "analysis"]
AllowanceWindow: TypeAlias = Literal["weekly", "five_hour"]
ExecutionMode: TypeAlias = Literal["auto", "sync", "async"]
FINITE_ALLOWANCE_RANGES = frozenset({"24h", "7d", "8w", "6m"})


@dataclass(frozen=True)
class AllowanceRequest:
    operation: AllowanceOperation
    window: AllowanceWindow = "weekly"
    range: str = "8w"
    cursor: str | None = None
    limit: int = 50
    analysis_id: str | None = None
    execution: ExecutionMode = "auto"

    def __post_init__(self) -> None:
        if self.operation not in {"status", "series", "evidence", "analysis"}:
            raise RequestValidationError(f"unsupported operation: {self.operation}")
        if self.window not in {"weekly", "five_hour"}:
            raise RequestValidationError(f"unsupported window: {self.window}")
        if self.range not in FINITE_ALLOWANCE_RANGES:
            raise RequestValidationError("range must be a finite preset: 24h, 7d, 8w, or 6m")
        if type(self.limit) is not int or not 1 <= self.limit <= 200:
            raise RequestValidationError("limit must be between 1 and 200")
        if self.execution not in {"auto", "sync", "async"}:
            raise RequestValidationError(f"unsupported execution: {self.execution}")
        if self.cursor is not None:
            if self.operation != "evidence":
                raise RequestValidationError("cursor is supported only for evidence")
            if not isinstance(self.cursor, str) or not self.cursor or len(self.cursor) > 4096:
                raise RequestValidationError("cursor must be a bounded non-empty string")
        if self.analysis_id is not None:
            if self.operation != "analysis":
                raise RequestValidationError("analysis_id is supported only for analysis")
            if not _safe_identifier(self.analysis_id):
                raise RequestValidationError("analysis_id contains unsafe characters")
        if self.operation != "analysis" and self.execution != "auto":
            raise RequestValidationError("execution is supported only for analysis")
        if self.operation == "analysis" and self.window != "weekly":
            raise RequestValidationError("analysis currently supports weekly windows only")


@dataclass(frozen=True)
class AllowanceResult:
    payload: Mapping[str, object]
    result_schema: str
    range_start: str | None
    range_end: str | None
    dashboard_target: Mapping[str, object]
    analysis_id: str | None = None


def _safe_identifier(value: str) -> bool:
    return (
        bool(value)
        and len(value) <= 256
        and value[0].isalnum()
        and all(character.isalnum() or character in "_.:@+-" for character in value)
    )
