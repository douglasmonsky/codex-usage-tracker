"""Immutable structural evidence contracts for allowance intelligence."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AllowancePointKind(StrEnum):
    BASELINE = "baseline"
    POSITIVE = "positive"
    CENSORED = "censored"
    CONFLICT = "conflict"


class AllowanceConfidence(StrEnum):
    HIGH = "high"
    LOW = "low"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class AllowanceCohort:
    key: str
    window_kind: str
    window_key: str
    is_archived: bool
    selected: bool = False


@dataclass(frozen=True)
class AllowanceCycle:
    cycle_id: str
    cohort: AllowanceCohort
    reset_at: int | None
    observations: tuple[dict[str, object], ...]
    status: str = "accepted"


@dataclass(frozen=True)
class AllowanceInterval:
    interval_id: str
    cycle_id: str
    start: dict[str, object] | None
    end: dict[str, object] | None
    point_kind: AllowancePointKind
    censor_reason: str | None = None
    eligible_for_interpolation: bool = False
