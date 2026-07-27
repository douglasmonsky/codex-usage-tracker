"""Pure versioned phase segmentation over privacy-safe activity facts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

PHASE_SEGMENTER_VERSION = 1

_PHASES = {
    "user_input": ("user_input", "high"),
    "skill": ("planning_reasoning", "high"),
    "patch": ("implementation", "high"),
    "task": ("delivery", "high"),
    "rollback": ("compaction_recovery", "high"),
    "turn_aborted": ("compaction_recovery", "high"),
    "compaction": ("compaction_recovery", "high"),
}
_DISCOVERY_MARKERS = ("find", "list", "open", "read", "rg", "search", "status")
_VERIFICATION_MARKERS = ("build", "check", "lint", "pytest", "test", "verify")
_WAIT_MARKERS = ("job_status", "poll", "wait")
_IMPLEMENTATION_MARKERS = ("apply", "edit", "exec", "patch", "write")
_AMBIGUOUS_WRAPPERS = {
    "exec_command",
    "functions.exec_command",
    "functions__exec_command",
}


@dataclass(frozen=True)
class ActivityFact:
    event_at: str
    event_kind: str
    turn_id: str | None
    thread_id: str | None = None
    activity_event_id: str | None = None
    safe_label: str | None = None


@dataclass(frozen=True)
class TokenFact:
    event_at: str
    turn_id: str | None
    input_tokens: int
    cached_input_tokens: int
    reasoning_tokens: int
    output_tokens: int
    thread_id: str | None = None


@dataclass(frozen=True)
class PhaseSegment:
    category: str
    started_at: str
    ended_at: str
    thread_id: str | None
    turn_id: str | None
    activity_count: int
    basis: str
    confidence: str
    input_tokens: int = 0
    uncached_input_tokens: int = 0
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    token_attribution: str = "none"
    segmenter_version: int = PHASE_SEGMENTER_VERSION


def segment_phases(facts: tuple[ActivityFact, ...]) -> tuple[PhaseSegment, ...]:
    """Return deterministic consecutive activity-derived phase segments."""

    ordered = sorted(
        facts,
        key=lambda item: (
            _time_key(item.event_at),
            item.activity_event_id or "",
            item.event_kind,
        ),
    )
    segments: list[PhaseSegment] = []
    for fact in ordered:
        category, confidence = _classify(fact)
        if (
            segments
            and segments[-1].category == category
            and segments[-1].turn_id == fact.turn_id
            and segments[-1].thread_id == fact.thread_id
        ):
            prior = segments[-1]
            segments[-1] = PhaseSegment(
                category=prior.category,
                started_at=prior.started_at,
                ended_at=fact.event_at,
                thread_id=prior.thread_id,
                turn_id=prior.turn_id,
                activity_count=prior.activity_count + 1,
                basis=prior.basis,
                confidence=prior.confidence,
            )
        else:
            segments.append(
                PhaseSegment(
                    category=category,
                    started_at=fact.event_at,
                    ended_at=fact.event_at,
                    thread_id=fact.thread_id,
                    turn_id=fact.turn_id,
                    activity_count=1,
                    basis="activity_event",
                    confidence=confidence,
                )
            )
    return tuple(segments)


def attribute_tokens(
    segments: tuple[PhaseSegment, ...],
    facts: tuple[TokenFact, ...],
) -> tuple[PhaseSegment, ...]:
    """Assign each token fact to its deterministic preceding turn segment."""

    attributed = list(segments)
    for fact in sorted(facts, key=lambda item: _time_key(item.event_at)):
        candidates = [
            index
            for index, segment in enumerate(attributed)
            if segment.turn_id == fact.turn_id
            and segment.thread_id == fact.thread_id
        ]
        if not candidates:
            attributed.append(
                PhaseSegment(
                    category="unknown",
                    started_at=fact.event_at,
                    ended_at=fact.event_at,
                    thread_id=fact.thread_id,
                    turn_id=fact.turn_id,
                    activity_count=0,
                    basis="token_without_activity",
                    confidence="unknown",
                )
            )
            candidates = [len(attributed) - 1]
        preceding = [
            index
            for index in candidates
            if _time_key(attributed[index].started_at) <= _time_key(fact.event_at)
        ]
        target = preceding[-1] if preceding else candidates[0]
        segment = attributed[target]
        uncached = max(0, fact.input_tokens - fact.cached_input_tokens)
        attributed[target] = replace(
            segment,
            input_tokens=segment.input_tokens + fact.input_tokens,
            uncached_input_tokens=segment.uncached_input_tokens + uncached,
            cached_input_tokens=(
                segment.cached_input_tokens + fact.cached_input_tokens
            ),
            reasoning_tokens=segment.reasoning_tokens + fact.reasoning_tokens,
            output_tokens=segment.output_tokens + fact.output_tokens,
            total_tokens=(
                segment.total_tokens + fact.input_tokens + fact.output_tokens
            ),
            token_attribution="deterministic",
        )
    return tuple(
        sorted(
            attributed,
            key=lambda item: (
                _time_key(item.started_at),
                item.thread_id or "",
                item.turn_id or "",
                item.category,
            ),
        )
    )


def _classify(fact: ActivityFact) -> tuple[str, str]:
    fixed = _PHASES.get(fact.event_kind)
    if fixed is not None:
        return fixed
    if fact.event_kind != "tool":
        return "unknown", "unknown"
    label = (fact.safe_label or "").lower()
    if label in _AMBIGUOUS_WRAPPERS:
        return "unknown", "unknown"
    if any(marker in label for marker in _WAIT_MARKERS):
        return "waiting_external", "medium"
    if any(marker in label for marker in _VERIFICATION_MARKERS):
        return "verification", "medium"
    if any(marker in label for marker in _DISCOVERY_MARKERS):
        return "discovery", "medium"
    if any(marker in label for marker in _IMPLEMENTATION_MARKERS):
        return "implementation", "medium"
    return "discovery", "unknown"


def _time_key(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
