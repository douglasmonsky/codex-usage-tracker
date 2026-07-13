"""Detectors for repeated file, shell, and validation work."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from codex_usage_tracker.compression.detector_protocol import build_candidate
from codex_usage_tracker.compression.evidence import (
    CallEvidence,
    CommandRunEvidence,
    CompressionEvidenceSnapshot,
    FileEventEvidence,
)
from codex_usage_tracker.compression.models import (
    CandidateDraft,
    ComponentName,
    CompressionScope,
)

_SHELL_ROOTS = frozenset({"git", "nl", "rg", "sed"})
_VALIDATION_ROOTS = frozenset(
    {"mypy", "npm", "npx", "pytest", "pyright", "ruff", "test", "unittest"}
)


@dataclass(frozen=True, slots=True)
class FileRediscoveryDetector:
    family = "file_rediscovery"
    version = "file-rediscovery-v1"

    min_occurrences: int = 3

    def detect(
        self,
        snapshot: CompressionEvidenceSnapshot,
        scope: CompressionScope,
    ) -> list[CandidateDraft]:
        calls = {call.record_id: call for call in snapshot.calls}
        groups = _file_groups(snapshot.file_events, calls)
        fragment_index = _fragment_exposure_index(snapshot)
        candidates = (
            _file_candidate(
                detector=self,
                snapshot=snapshot,
                scope=scope,
                calls=calls,
                thread_key=thread_key,
                path_hash=path_hash,
                events=events,
                fragment_index=fragment_index,
            )
            for (thread_key, path_hash), events in sorted(groups.items())
        )
        return [candidate for candidate in candidates if candidate is not None]


@dataclass(frozen=True, slots=True)
class ShellRetryDetector:
    family = "shell_retry"
    version = "shell-retry-v1"

    min_occurrences: int = 3

    def detect(
        self,
        snapshot: CompressionEvidenceSnapshot,
        scope: CompressionScope,
    ) -> list[CandidateDraft]:
        return _command_candidates(
            snapshot=snapshot,
            scope=scope,
            family=self.family,
            version=self.version,
            commands=(
                command
                for command in _unique_commands(snapshot.command_runs)
                if command.command_root in _SHELL_ROOTS
            ),
            min_occurrences=self.min_occurrences,
            group_name="shell retry/churn",
            intervention_family="shell_checkpoint",
            successful_only=False,
        )


@dataclass(frozen=True, slots=True)
class ValidationRepetitionDetector:
    family = "validation_repetition"
    version = "validation-repetition-v1"

    min_occurrences: int = 3

    def detect(
        self,
        snapshot: CompressionEvidenceSnapshot,
        scope: CompressionScope,
    ) -> list[CandidateDraft]:
        return _command_candidates(
            snapshot=snapshot,
            scope=scope,
            family=self.family,
            version=self.version,
            commands=(
                command
                for command in _unique_commands(snapshot.command_runs)
                if command.command_root in _VALIDATION_ROOTS
            ),
            min_occurrences=self.min_occurrences,
            group_name="validation repetition",
            intervention_family="validation_checkpoint",
            successful_only=True,
        )


def _command_candidates(
    *,
    snapshot: CompressionEvidenceSnapshot,
    scope: CompressionScope,
    family: str,
    version: str,
    commands: Iterable[CommandRunEvidence],
    min_occurrences: int,
    group_name: str,
    intervention_family: str,
    successful_only: bool,
) -> list[CandidateDraft]:
    calls = {call.record_id: call for call in snapshot.calls}
    groups = _command_groups(commands, calls, successful_only=successful_only)
    candidates = (
        _command_candidate(
            snapshot=snapshot,
            scope=scope,
            calls=calls,
            family=family,
            version=version,
            group_name=group_name,
            intervention_family=intervention_family,
            min_occurrences=min_occurrences,
            thread_key=thread_key,
            group_key=group_key,
            commands=grouped,
        )
        for (thread_key, group_key), grouped in sorted(groups.items())
    )
    return [candidate for candidate in candidates if candidate is not None]


def _command_groups(
    commands: Iterable[CommandRunEvidence],
    calls: dict[str, CallEvidence],
    *,
    successful_only: bool,
) -> dict[tuple[str, str], list[CommandRunEvidence]]:
    groups: dict[tuple[str, str], list[CommandRunEvidence]] = defaultdict(list)
    for command in commands:
        call = calls.get(command.record_id)
        if call is None or not _accepted_command(command, successful_only):
            continue
        group_key = command.retry_group or command.command_root
        groups[(call.thread_key, group_key)].append(command)
    return groups


def _command_candidate(
    *,
    snapshot: CompressionEvidenceSnapshot,
    scope: CompressionScope,
    calls: dict[str, CallEvidence],
    family: str,
    version: str,
    group_name: str,
    intervention_family: str,
    min_occurrences: int,
    thread_key: str,
    group_key: str,
    commands: list[CommandRunEvidence],
) -> CandidateDraft | None:
    if len(commands) < min_occurrences:
        return None
    claims = _command_claims(commands)
    if not any(exposure > 0 for _, _, exposure in claims):
        return None
    timestamps = [calls[command.record_id].event_timestamp for command in commands]
    confidence_grade, confidence_score = _command_confidence(commands)
    return build_candidate(
        snapshot=snapshot,
        scope=scope,
        family=family,
        pattern=f"Repeated {group_name} produced avoidable tool output",
        pattern_key=f"{thread_key}:{group_key}",
        detector_version=version,
        claims=claims,
        thread_keys=(thread_key,),
        observation_count=len(commands),
        confidence_grade=confidence_grade,
        confidence_score=confidence_score,
        confidence_reasons=(
            f"{len(commands)} command runs shared a stable repetition key",
            "command output size bounds the attributable exposure",
        ),
        evidence_handles=(
            {
                "group_key": group_key,
                "command_roots": sorted({command.command_root for command in commands}),
                "occurrences": len(commands),
            },
        ),
        intervention={
            "family": intervention_family,
            "action": "Batch the repeated checks and preserve one compact result.",
        },
        verification={
            "metric": "repeated_command_count",
            "expected_direction": "decrease",
        },
        first_seen=min(timestamps),
        last_seen=max(timestamps),
    )


def _file_groups(
    events: tuple[FileEventEvidence, ...],
    calls: dict[str, CallEvidence],
) -> dict[tuple[str, str], list[FileEventEvidence]]:
    groups: dict[tuple[str, str], list[FileEventEvidence]] = defaultdict(list)
    for event in _unique_files(events):
        call = calls.get(event.record_id)
        if call is None or event.operation != "read" or not event.path_hash:
            continue
        groups[(call.thread_key, event.path_hash)].append(event)
    return groups


def _file_candidate(
    *,
    detector: FileRediscoveryDetector,
    snapshot: CompressionEvidenceSnapshot,
    scope: CompressionScope,
    calls: dict[str, CallEvidence],
    thread_key: str,
    path_hash: str,
    events: list[FileEventEvidence],
    fragment_index: _FragmentExposureIndex,
) -> CandidateDraft | None:
    if len(events) < detector.min_occurrences:
        return None
    claims = _fragment_claims(events, fragment_index)
    if not claims:
        return None
    timestamps = [calls[event.record_id].event_timestamp for event in events]
    return build_candidate(
        snapshot=snapshot,
        scope=scope,
        family=detector.family,
        pattern="The same file was rediscovered repeatedly in one thread",
        pattern_key=f"{thread_key}:{path_hash}",
        detector_version=detector.version,
        claims=claims,
        thread_keys=(thread_key,),
        observation_count=len(events),
        confidence_grade="medium",
        confidence_score=0.72,
        confidence_reasons=(
            "the same path hash appeared in repeated read events",
            "indexed fragment size bounds the attributable exposure",
        ),
        evidence_handles=({"path_hash": path_hash, "occurrences": len(events)},),
        intervention={
            "family": "file_summary_checkpoint",
            "action": "Keep a compact file summary or targeted symbol index.",
        },
        verification={
            "metric": "repeated_file_read_count",
            "expected_direction": "decrease",
        },
        first_seen=min(timestamps),
        last_seen=max(timestamps),
    )


def _accepted_command(command: CommandRunEvidence, successful_only: bool) -> bool:
    return not successful_only or command.exit_code in {0, None}


def _command_claims(
    commands: list[CommandRunEvidence],
) -> tuple[tuple[str, ComponentName, int], ...]:
    return tuple(
        (command.record_id, "tool_output", (command.output_size_bytes + 3) // 4)
        for command in commands
    )


def _command_confidence(commands: list[CommandRunEvidence]) -> tuple[str, float]:
    if any(command.retry_group for command in commands):
        return "high", 0.8
    return "medium", 0.66


def _fragment_claims(
    events: list[FileEventEvidence],
    fragment_index: _FragmentExposureIndex,
) -> tuple[tuple[str, ComponentName, int], ...]:
    claims: list[tuple[str, ComponentName, int]] = []
    evidence_keys = sorted(
        {(event.record_id, event.turn_key) for event in events},
        key=lambda row: (row[0], row[1] or ""),
    )
    for record_id, turn_key in evidence_keys:
        exposure = fragment_index.exposure(record_id, turn_key)
        if exposure > 0:
            claims.append((record_id, "content_fragment", exposure))
    return tuple(claims)


@dataclass(frozen=True, slots=True)
class _FragmentExposureIndex:
    by_record: dict[str, int]
    by_turn: dict[tuple[str, str], int]

    def exposure(self, record_id: str, turn_key: str | None) -> int:
        if turn_key is None:
            return self.by_record.get(record_id, 0)
        return self.by_turn.get((record_id, turn_key), 0)


def _fragment_exposure_index(
    snapshot: CompressionEvidenceSnapshot,
) -> _FragmentExposureIndex:
    if snapshot.content_exposure_by_record or snapshot.content_exposure_by_turn:
        return _FragmentExposureIndex(
            dict(snapshot.content_exposure_by_record),
            dict(snapshot.content_exposure_by_turn),
        )
    by_record: dict[str, int] = defaultdict(int)
    by_turn: dict[tuple[str, str], int] = defaultdict(int)
    for fragment in snapshot.content_fragments:
        by_record[fragment.record_id] += fragment.estimated_tokens
        if fragment.turn_key is not None:
            by_turn[(fragment.record_id, fragment.turn_key)] += fragment.estimated_tokens
    return _FragmentExposureIndex(dict(by_record), dict(by_turn))


def _unique_files(events: tuple[FileEventEvidence, ...]) -> tuple[FileEventEvidence, ...]:
    return tuple({event.file_event_key: event for event in events}.values())


def _unique_commands(
    commands: tuple[CommandRunEvidence, ...],
) -> tuple[CommandRunEvidence, ...]:
    return tuple({command.command_run_key: command for command in commands}.values())
