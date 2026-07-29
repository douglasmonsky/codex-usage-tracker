"""Deterministic structural-record parsing for Candidate C."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import shared


@dataclass(frozen=True)
class ParsedRecord:
    source_path: str
    manifestation_id: str
    revision: str
    adapter_version: str
    source_state: str
    record_ordinal: int
    byte_start: int
    byte_end: int
    event_at_us: int
    event_kind_order: int
    source_order: int
    event_type: str
    payload: dict[str, Any]
    payload_sha256: str
    logical_id: str
    occurrence_id: str

    @property
    def total_order(self) -> tuple[int, int, int, str, str]:
        return (
            self.event_at_us,
            self.event_kind_order,
            self.source_order,
            self.logical_id,
            self.occurrence_id,
        )


@dataclass(frozen=True)
class ParseResult:
    records: tuple[ParsedRecord, ...]
    malformed_lines: int
    parsed_bytes: int


def parse_fixture_records(
    fixture: shared.FixtureBundle,
    *,
    parser_workers: int = 1,
) -> ParseResult:
    """Parse verified fixture sources and restore one deterministic total order."""
    if parser_workers < 1:
        raise ValueError("parser_workers must be positive")
    sources = tuple(sorted(fixture.sources, key=lambda item: item.relative_path.as_posix()))
    if parser_workers == 1:
        results = tuple(_parse_source(source) for source in sources)
    else:
        with ThreadPoolExecutor(max_workers=parser_workers) as executor:
            results = tuple(executor.map(_parse_source, sources))
    records = tuple(
        sorted(
            (record for result in results for record in result.records),
            key=lambda record: record.total_order,
        )
    )
    return ParseResult(
        records=records,
        malformed_lines=sum(result.malformed_lines for result in results),
        parsed_bytes=sum(result.parsed_bytes for result in results),
    )


def _parse_source(source: shared.SourceArtifact) -> ParseResult:
    records: list[ParsedRecord] = []
    malformed_lines = 0
    byte_start = 0
    payload = source.absolute_path.read_bytes()
    for ordinal, line in enumerate(payload.splitlines(keepends=True)):
        byte_end = byte_start + len(line)
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            malformed_lines += 1
            byte_start = byte_end
            continue
        if not isinstance(value, dict):
            malformed_lines += 1
            byte_start = byte_end
            continue
        record = _record_from_object(
            value,
            source=source,
            record_ordinal=ordinal,
            byte_start=byte_start,
            byte_end=byte_end,
        )
        if record is None:
            malformed_lines += 1
        else:
            records.append(record)
        byte_start = byte_end
    return ParseResult(
        records=tuple(records),
        malformed_lines=malformed_lines,
        parsed_bytes=len(payload),
    )


def _record_from_object(
    value: dict[str, Any],
    *,
    source: shared.SourceArtifact,
    record_ordinal: int,
    byte_start: int,
    byte_end: int,
) -> ParsedRecord | None:
    payload = value.get("payload")
    event_type = value.get("type")
    event_at_us = value.get("event_at_us")
    event_kind_order = value.get("event_kind_order")
    source_order = value.get("source_order")
    if (
        not isinstance(payload, dict)
        or not isinstance(event_type, str)
        or not isinstance(event_at_us, int)
        or not isinstance(event_kind_order, int)
        or not isinstance(source_order, int)
    ):
        return None
    logical_id = _logical_id(event_type, payload, event_at_us, source_order)
    payload_sha256 = shared.canonical_sha256(payload)
    occurrence_id = "occurrence:c:" + hashlib.sha256(
        shared.canonical_json_bytes(
            {
                "manifestation_id": source.manifestation_id,
                "revision": source.revision,
                "source_path": source.relative_path.as_posix(),
                "record_ordinal": record_ordinal,
                "payload_sha256": payload_sha256,
            }
        )
    ).hexdigest()
    return ParsedRecord(
        source_path=source.relative_path.as_posix(),
        manifestation_id=source.manifestation_id,
        revision=source.revision,
        adapter_version=source.adapter_version,
        source_state=source.state,
        record_ordinal=record_ordinal,
        byte_start=byte_start,
        byte_end=byte_end,
        event_at_us=event_at_us,
        event_kind_order=event_kind_order,
        source_order=source_order,
        event_type=event_type,
        payload=payload,
        payload_sha256=payload_sha256,
        logical_id=logical_id,
        occurrence_id=occurrence_id,
    )


def _logical_id(
    event_type: str,
    payload: dict[str, Any],
    event_at_us: int,
    source_order: int,
) -> str:
    for field in (
        "oracle_id",
        "call_id",
        "tool_id",
        "change_id",
        "activity_id",
        "compaction_id",
        "turn_id",
        "session_id",
        "logical_id",
        "manifestation_id",
    ):
        value = payload.get(field)
        if isinstance(value, str) and value:
            return value
    digest = shared.canonical_sha256(
        {
            "event_type": event_type,
            "event_at_us": event_at_us,
            "source_order": source_order,
            "payload": payload,
        }
    )
    return f"{event_type}:candidate-c:{digest}"
