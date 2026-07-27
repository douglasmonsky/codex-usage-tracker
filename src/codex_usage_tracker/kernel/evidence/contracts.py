"""Typed adapter-independent evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

MAX_EVIDENCE_LIMIT = 500
MAX_SELECTOR_LENGTH = 256
_SELECTOR_KINDS = frozenset({"thread", "turn", "call", "tool", "allowance"})


class EvidenceView(str, Enum):
    SUMMARY = "summary"
    TIMELINE = "timeline"
    CALLS = "calls"
    TOOLS = "tools"
    ACTIVITIES = "activities"
    ALLOWANCE = "allowance"


@dataclass(frozen=True)
class EvidenceSelector:
    kind: str
    logical_id: str

    @classmethod
    def parse(cls, value: str) -> EvidenceSelector:
        text = value.strip()
        if not text or len(text) > MAX_SELECTOR_LENGTH or ":" not in text:
            raise ValueError("evidence selector is invalid")
        kind, logical_id = text.split(":", 1)
        if (
            kind not in _SELECTOR_KINDS
            or not logical_id
            or logical_id != logical_id.strip()
            or any(character in logical_id for character in ("\x00", "\n", "\r"))
            or logical_id.startswith(("/", "~"))
            or "/Users/" in logical_id
        ):
            raise ValueError("evidence selector is invalid")
        return cls(kind=kind, logical_id=logical_id)

    @property
    def value(self) -> str:
        return f"{self.kind}:{self.logical_id}"


@dataclass(frozen=True)
class EvidenceRequest:
    selector: EvidenceSelector | str
    view: EvidenceView | str = EvidenceView.SUMMARY
    limit: int = 100
    cursor: str | None = None
    live: bool = False

    def normalized(self) -> EvidenceRequest:
        selector = (
            self.selector
            if isinstance(self.selector, EvidenceSelector)
            else EvidenceSelector.parse(self.selector)
        )
        try:
            view = EvidenceView(self.view)
        except ValueError as exc:
            raise ValueError("evidence view is not allowlisted") from exc
        if not 1 <= self.limit <= MAX_EVIDENCE_LIMIT:
            raise ValueError(
                f"evidence limit must be between 1 and {MAX_EVIDENCE_LIMIT}"
            )
        return replace(
            self,
            selector=selector,
            view=view,
            cursor=self.cursor.strip() if self.cursor else None,
        )


@dataclass(frozen=True)
class EvidenceResult:
    generation: int
    selector: str
    view: str
    rows: tuple[dict[str, Any], ...]
    matched_count: int
    returned_count: int
    truncated: bool
    next_cursor: str | None
    destination: str
    live: bool
    grade: str
    coverage: dict[str, Any]
