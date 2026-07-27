"""Privacy-safe source observation and incremental parse planning."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .identity import source_id

_FINGERPRINT_BYTES = 4096
_SCAN_BYTES = 64 * 1024


class PlanKind(str, Enum):
    NEW_SOURCE = "new_source"
    APPEND_SAFE = "append_safe"
    REPLACE_SOURCE = "replace_source"
    TRUNCATE_SOURCE = "truncate_source"


@dataclass(frozen=True)
class SourceObservation:
    path: Path
    source_id: str
    device_identity_hash: str
    file_identity_hash: str
    size_bytes: int
    complete_size: int
    modified_ns: int
    is_archived: bool
    prefix_fingerprint: str
    trailing_incomplete_bytes: int
    trailing_incomplete_hash: str | None


@dataclass(frozen=True)
class SourceCursor:
    source_id: str
    parsed_byte_offset: int
    parsed_line_number: int
    size_bytes: int
    prefix_fingerprint: str
    is_archived: bool

    @classmethod
    def from_plan(cls, plan: SourcePlan) -> SourceCursor:
        return cls(
            source_id=plan.observation.source_id,
            parsed_byte_offset=plan.end_byte,
            parsed_line_number=plan.end_line,
            size_bytes=plan.observation.size_bytes,
            prefix_fingerprint=plan.observation.prefix_fingerprint,
            is_archived=plan.observation.is_archived,
        )


@dataclass(frozen=True)
class SourcePlan:
    kind: PlanKind
    observation: SourceObservation
    prior_source_id: str | None
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    replace_existing: bool


def observe_source(path: Path) -> SourceObservation:
    """Capture bounded source metadata and the last complete-line boundary."""

    target = path.resolve()
    stat = target.stat()
    complete_size = _complete_size(target, stat.st_size)
    trailing = stat.st_size - complete_size
    device = _opaque_stat_part("device", stat.st_dev)
    file_identity = _opaque_stat_part("file", stat.st_ino)
    return SourceObservation(
        path=target,
        source_id=source_id(
            source_kind="session",
            device_identity=device,
            file_identity=file_identity,
        ),
        device_identity_hash=device,
        file_identity_hash=file_identity,
        size_bytes=stat.st_size,
        complete_size=complete_size,
        modified_ns=stat.st_mtime_ns,
        is_archived="archived_sessions" in target.parts,
        prefix_fingerprint=_bounded_digest(target, complete_size),
        trailing_incomplete_bytes=trailing,
        trailing_incomplete_hash=_tail_digest(target, complete_size, trailing),
    )


def plan_source(
    observation: SourceObservation,
    cursor: SourceCursor | None,
) -> SourcePlan | None:
    """Choose one conservative parse action without opening SQLite."""

    if cursor is None:
        return _replacement_plan(observation, PlanKind.NEW_SOURCE, None)
    if observation.complete_size <= cursor.parsed_byte_offset:
        if _is_replaced(observation, cursor):
            same_file = observation.source_id == cursor.source_id
            kind = (
                PlanKind.TRUNCATE_SOURCE
                if same_file
                and observation.size_bytes < cursor.parsed_byte_offset
                else PlanKind.REPLACE_SOURCE
            )
            return _replacement_plan(observation, kind, cursor.source_id)
        return None
    if _is_replaced(observation, cursor):
        return _replacement_plan(
            observation,
            PlanKind.REPLACE_SOURCE,
            cursor.source_id,
        )
    added_lines = _count_lines(
        observation.path,
        cursor.parsed_byte_offset,
        observation.complete_size,
    )
    return SourcePlan(
        kind=PlanKind.APPEND_SAFE,
        observation=observation,
        prior_source_id=cursor.source_id,
        start_byte=cursor.parsed_byte_offset,
        end_byte=observation.complete_size,
        start_line=cursor.parsed_line_number,
        end_line=cursor.parsed_line_number + added_lines,
        replace_existing=False,
    )


def _replacement_plan(
    observation: SourceObservation,
    kind: PlanKind,
    prior_source_id: str | None,
) -> SourcePlan:
    return SourcePlan(
        kind=kind,
        observation=observation,
        prior_source_id=prior_source_id,
        start_byte=0,
        end_byte=observation.complete_size,
        start_line=0,
        end_line=_count_lines(observation.path, 0, observation.complete_size),
        replace_existing=True,
    )


def _is_replaced(observation: SourceObservation, cursor: SourceCursor) -> bool:
    return (
        observation.source_id != cursor.source_id
        or observation.is_archived != cursor.is_archived
        or _bounded_digest(
            observation.path,
            min(cursor.parsed_byte_offset, observation.complete_size),
        )
        != cursor.prefix_fingerprint
    )


def _complete_size(path: Path, size: int) -> int:
    if size == 0:
        return 0
    with path.open("rb") as handle:
        position = size
        remainder = b""
        while position:
            length = min(position, _SCAN_BYTES)
            position -= length
            handle.seek(position)
            remainder = handle.read(length) + remainder
            newline = remainder.rfind(b"\n")
            if newline >= 0:
                return position + newline + 1
            remainder = remainder[:_SCAN_BYTES]
    return 0


def _count_lines(path: Path, start: int, end: int) -> int:
    count = 0
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = end - start
        while remaining:
            chunk = handle.read(min(remaining, _SCAN_BYTES))
            if not chunk:
                break
            count += chunk.count(b"\n")
            remaining -= len(chunk)
    return count


def _bounded_digest(path: Path, committed_size: int) -> str:
    """Fingerprint bounded first/middle/last samples of committed content."""

    sample_size = min(_FINGERPRINT_BYTES, committed_size)
    offsets = {
        0,
        max(0, (committed_size - sample_size) // 2),
        max(0, committed_size - sample_size),
    }
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for offset in sorted(offsets):
            handle.seek(offset)
            payload = handle.read(sample_size)
            digest.update(offset.to_bytes(8, "big"))
            digest.update(len(payload).to_bytes(8, "big"))
            digest.update(payload)
    return "sha256:" + digest.hexdigest()


def _tail_digest(path: Path, start: int, length: int) -> str | None:
    if length == 0:
        return None
    with path.open("rb") as handle:
        handle.seek(start)
        payload = handle.read(length)
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _opaque_stat_part(kind: str, value: int) -> str:
    payload = f"{kind}:{value}".encode()
    return hashlib.sha256(payload).hexdigest()
