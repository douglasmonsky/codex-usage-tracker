"""Complete-record framing and source cursor classification."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ..contracts import CursorOutcome, SourceCursor, SourceInventory


@dataclass(frozen=True, slots=True)
class FramedRecord:
    body: bytes
    record_ordinal: int
    byte_start: int
    byte_end: int


@dataclass(frozen=True, slots=True)
class CursorClassification:
    outcome: CursorOutcome
    reason: str


def _sha256_prefix(path: Path, length: int) -> str:
    digest = hashlib.sha256()
    remaining = length
    with path.open("rb") as handle:
        while remaining:
            chunk = handle.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            digest.update(chunk)
            remaining -= len(chunk)
    if remaining:
        raise ValueError("cursor prefix exceeds the source size")
    return digest.hexdigest()


def _sha256_suffix(path: Path, *, size: int, width: int = 4096) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        handle.seek(max(0, size - width))
        digest.update(handle.read(width))
    return digest.hexdigest()


def iter_complete_records(path: Path, *, start_offset: int = 0, start_ordinal: int = 0) -> Iterator[FramedRecord]:
    """Yield newline-terminated records and leave a partial final line unread."""

    if start_offset < 0 or start_ordinal < 0:
        raise ValueError("cursor coordinates must be nonnegative")
    with path.open("rb") as handle:
        handle.seek(start_offset)
        ordinal = start_ordinal
        while True:
            byte_start = handle.tell()
            body = handle.readline()
            if not body:
                return
            if not body.endswith(b"\n"):
                return
            byte_end = handle.tell()
            yield FramedRecord(body, ordinal, byte_start, byte_end)
            ordinal += 1


def build_cursor(
    path: Path,
    *,
    inventory: SourceInventory,
    byte_offset: int,
    record_ordinal: int,
    latest_source_order: int,
    parser_version: str,
    adapter_version: str,
) -> SourceCursor:
    """Create a cursor from the last complete record boundary."""

    size = path.stat().st_size
    if byte_offset < 0 or byte_offset > size:
        raise ValueError("cursor offset is outside the source")
    return SourceCursor(
        manifestation_id=inventory.manifestation_id,
        manifestation_key=inventory.manifestation_key,
        source_revision=inventory.content_revision,
        byte_offset=byte_offset,
        record_ordinal=record_ordinal,
        source_size_bytes=size,
        prefix_through_cursor_sha256=_sha256_prefix(path, byte_offset),
        suffix_sha256=_sha256_suffix(path, size=size),
        latest_source_order=latest_source_order,
        parser_version=parser_version,
        adapter_version=adapter_version,
    )


def classify_cursor(
    path: Path | None,
    *,
    inventory: SourceInventory,
    cursor: SourceCursor | None,
    parser_version: str,
    adapter_version: str,
) -> CursorClassification:
    """Classify a source before hydration, using only bounded fingerprints."""

    if path is None or inventory.state.value == "missing":
        return CursorClassification(CursorOutcome.MISSING, "source is unavailable")
    if cursor is None:
        return CursorClassification(CursorOutcome.APPEND_SAFE, "no committed cursor")
    if (
        cursor.manifestation_id != inventory.manifestation_id
        or cursor.manifestation_key != inventory.manifestation_key
    ):
        return CursorClassification(CursorOutcome.REPLACED, "cursor belongs to a different source manifestation")
    if cursor.parser_version != parser_version or cursor.adapter_version != adapter_version:
        return CursorClassification(CursorOutcome.RECANONICALIZE, "parser or adapter version changed")
    size = path.stat().st_size
    if size < cursor.byte_offset:
        return CursorClassification(CursorOutcome.TRUNCATED, "source is smaller than the cursor")
    if inventory.content_revision != cursor.source_revision and size == cursor.source_size_bytes:
        return CursorClassification(CursorOutcome.REPLACED, "content revision changed")
    if _sha256_prefix(path, cursor.byte_offset) != cursor.prefix_through_cursor_sha256:
        return CursorClassification(CursorOutcome.REPLACED, "prefix through cursor changed")
    current_suffix = _sha256_suffix(path, size=size)
    if size == cursor.source_size_bytes and current_suffix == cursor.suffix_sha256:
        return CursorClassification(CursorOutcome.NO_CHANGE, "source bytes and metadata are unchanged")
    if size >= cursor.byte_offset:
        return CursorClassification(CursorOutcome.APPEND_SAFE, "cursor prefix remains a complete-record prefix")
    return CursorClassification(CursorOutcome.REPLACED, "source revision cannot be resumed safely")
