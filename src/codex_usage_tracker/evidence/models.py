"""Immutable canonical evidence request and result models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, TypeAlias, cast

from codex_usage_tracker.core.contracts import EvidenceV1
from codex_usage_tracker.core.contracts.common import immutable_snapshot
from codex_usage_tracker.evidence.selectors import EvidenceSelector, EvidenceSelectorKind

EVIDENCE_RESULT_SCHEMA = "codex-usage-tracker.evidence-result.v1"
HistoryScope: TypeAlias = Literal["active", "all"]
_SECTIONS = {
    "finding": {"summary"},
    "call": {"summary"},
    "thread": {"summary", "calls"},
    "allowance": {"summary"},
    "analysis": {"summary"},
}


class EvidenceNotFoundError(LookupError):
    """Raised when an exact evidence selector is unavailable in the requested scope."""


class EvidenceHistoryMismatchError(EvidenceNotFoundError):
    """Raised when exact evidence exists only outside the requested history scope."""


class EvidenceAmbiguityError(LookupError):
    """Raised when a selector needs an additional qualifier to resolve exactly once."""


@dataclass(frozen=True)
class EvidenceRequest:
    selector_kind: EvidenceSelectorKind
    selector_id: str
    section: str = "summary"
    limit: int = 20
    cursor: str | None = None
    history: HistoryScope = "active"
    analysis_id: str | None = None

    def __post_init__(self) -> None:
        EvidenceSelector(self.selector_kind, self.selector_id)
        if self.section not in _SECTIONS[self.selector_kind]:
            raise ValueError(f"section is not supported for {self.selector_kind}")
        if type(self.limit) is not int or not 1 <= self.limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        if self.history not in {"active", "all"}:
            raise ValueError(f"unsupported history: {self.history}")
        if self.cursor is not None and not isinstance(self.cursor, str):
            raise ValueError("cursor must be a string")
        if self.analysis_id is not None:
            if self.selector_kind != "finding":
                raise ValueError("analysis_id is only supported for finding evidence")
            try:
                EvidenceSelector("analysis", self.analysis_id)
            except ValueError as exc:
                raise ValueError("analysis_id is invalid") from exc


@dataclass(frozen=True)
class EvidenceResult:
    schema: Literal["codex-usage-tracker.evidence-result.v1"] = field(
        default=EVIDENCE_RESULT_SCHEMA, init=False
    )
    selector: Mapping[str, str]
    records: tuple[EvidenceV1, ...]
    next_cursor: str | None
    dashboard_target: Mapping[str, object]
    subject: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if len(self.records) > 200:
            raise ValueError("evidence records exceed the maximum page size")
        object.__setattr__(
            self, "selector", cast(Mapping[str, str], immutable_snapshot(self.selector))
        )
        object.__setattr__(self, "records", tuple(self.records))
        if self.subject is not None:
            object.__setattr__(
                self,
                "subject",
                cast(Mapping[str, object], immutable_snapshot(self.subject)),
            )
        object.__setattr__(
            self,
            "dashboard_target",
            cast(Mapping[str, object], immutable_snapshot(self.dashboard_target)),
        )
