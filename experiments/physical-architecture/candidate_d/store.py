from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import shared

from . import schema

_CONTROL_TYPES = frozenset(
    {
        "allowance_compatibility",
        "late_parent",
        "oracle_case",
        "selector_anchor",
        "slice_control",
        "source_revision",
    }
)
_ENTITY_KIND = {
    "model_call": 1,
    "tool_start": 2,
    "tool_terminal": 2,
    "session_start": 3,
    "session_terminal": 3,
    "turn_start": 4,
    "activity": 5,
    "state_change": 6,
    "allowance_observation": 7,
    "compaction_boundary": 8,
    "selector_anchor": 9,
    "oracle_case": 10,
    "allowance_compatibility": 11,
    "late_parent": 12,
    "slice_control": 13,
    "source_revision": 14,
}
_ENTITY_KIND_NAME = {
    1: "model_call",
    2: "tool",
    3: "session",
    4: "turn",
    5: "activity",
    6: "state_change",
    7: "allowance_observation",
    8: "compaction_boundary",
    9: "selector_anchor",
    10: "oracle_case",
    11: "allowance_compatibility",
    12: "late_parent",
    13: "slice_control",
    14: "source_revision",
}
_FACT_TABLES = (
    "model_calls",
    "activities",
    "state_changes",
    "compaction_boundaries",
    "allowance_observations",
)
_LIFECYCLE_TABLES = (
    "sessions",
    "session_parent_observations",
    "turns",
    "tool_invocations",
    "tool_transitions",
)
_PROJECTION_TABLES = ("session_usage_current", "tool_family_current")


class CandidateDIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True)
class OrderKey:
    missing_time: int
    event_at_us: int
    source_order: int
    event_kind_order: int
    logical_id: str

    def as_tuple(self) -> tuple[int, int, int, int, str]:
        return (
            self.missing_time,
            self.event_at_us,
            self.source_order,
            self.event_kind_order,
            self.logical_id,
        )

    def cursor(self) -> str:
        return shared.canonical_json_bytes(list(self.as_tuple())).decode("utf-8").strip()

    @classmethod
    def from_cursor(cls, cursor: str) -> OrderKey:
        try:
            payload = json.loads(cursor)
        except json.JSONDecodeError as error:
            raise ValueError("Candidate D cursor is not JSON") from error
        if (
            not isinstance(payload, list)
            or len(payload) != 5
            or not all(isinstance(value, int) for value in payload[:4])
            or not isinstance(payload[4], str)
        ):
            raise ValueError("Candidate D cursor has the wrong total-order shape")
        return cls(
            missing_time=payload[0],
            event_at_us=payload[1],
            source_order=payload[2],
            event_kind_order=payload[3],
            logical_id=payload[4],
        )


@dataclass(frozen=True)
class SequenceRow:
    order_key: OrderKey
    entity_kind: int
    logical_id: str
    session_id: str | None
    turn_id: str | None
    source_path: str
    manifestation_id: str
    revision: str
    adapter_version: str
    record_ordinal: int
    byte_start: int
    byte_end: int
    selector_kind: str | None

    def as_dict(self) -> dict[str, object]:
        selector = (
            f"{self.selector_kind.replace('_', '-')}:{self.logical_id}"
            if self.selector_kind is not None
            else None
        )
        return {
            "order_key": self.order_key.as_tuple(),
            "entity_kind": self.entity_kind,
            "event_kind": _ENTITY_KIND_NAME[self.entity_kind],
            "event_at_us": (None if self.order_key.missing_time else self.order_key.event_at_us),
            "logical_id": self.logical_id,
            "selector": selector,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "occurrence_coordinate": {
                "source_path": self.source_path,
                "manifestation_id": self.manifestation_id,
                "revision": self.revision,
                "adapter_version": self.adapter_version,
                "record_ordinal": self.record_ordinal,
                "record_range": (self.record_ordinal, self.record_ordinal),
                "byte_start": self.byte_start,
                "byte_end": self.byte_end,
            },
        }


@dataclass
class BuildStats:
    source_files_inventoried: int = 0
    source_files_selected: int = 0
    source_files_parsed: int = 0
    source_files_deferred: int = 0
    source_files_rescanned: int = 0
    source_bytes_inventoried: int = 0
    source_bytes_selected: int = 0
    source_bytes_parsed: int = 0
    source_bytes_deferred: int = 0
    source_bytes_rescanned: int = 0
    facts_inserted: int = 0
    facts_updated: int = 0
    facts_recanonicalized: int = 0
    facts_unchanged: int = 0
    dirty_keys: set[str] = field(default_factory=set)
    projection_rows_read: int = 0
    projection_rows_written: int = 0
    writer_transactions: int = 0
    parse_time_ns: int = 0
    merge_time_ns: int = 0
    writer_time_ns: int = 0
    writer_lock_ns: int = 0

    def merge(self, other: BuildStats) -> None:
        for name in (
            "source_files_inventoried",
            "source_files_selected",
            "source_files_parsed",
            "source_files_deferred",
            "source_files_rescanned",
            "source_bytes_inventoried",
            "source_bytes_selected",
            "source_bytes_parsed",
            "source_bytes_deferred",
            "source_bytes_rescanned",
            "facts_inserted",
            "facts_updated",
            "facts_recanonicalized",
            "facts_unchanged",
            "projection_rows_read",
            "projection_rows_written",
            "writer_transactions",
            "parse_time_ns",
            "merge_time_ns",
            "writer_time_ns",
            "writer_lock_ns",
        ):
            setattr(self, name, getattr(self, name) + getattr(other, name))
        self.dirty_keys.update(other.dirty_keys)


@dataclass(frozen=True)
class StorageStats:
    database_bytes: int
    table_bytes: int
    index_bytes: int
    free_list_bytes: int
    wal_bytes: int
    journal_bytes: int
    page_count: int
    fact_rows: int
    lifecycle_rows: int
    occurrence_rows: int
    sequence_rows: int
    projection_rows: int


@dataclass(frozen=True)
class QueryResult:
    payload: Mapping[str, Any]
    sql_latencies_ns: tuple[int, ...]
    plans: tuple[str, ...]
    rows_scanned: int
    tracker_calls: int = 1


@dataclass(frozen=True)
class _ParsedRecord:
    manifestation_pk: int
    manifestation_id: str
    relative_path: str
    revision: str
    adapter_version: str
    state: str
    ordinal: int
    byte_start: int
    byte_end: int
    record: Mapping[str, Any]
    canonical: bool
    logical_id: str
    entity_kind: int
    order_key: OrderKey
    session_id: str | None
    turn_id: str | None


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CandidateDIntegrityError(f"{label} must be an object")
    return value


def _last_row_id(cursor: sqlite3.Cursor) -> int:
    value = cursor.lastrowid
    if value is None:
        raise CandidateDIntegrityError("SQLite insert did not return a row identifier")
    return value


def _integer(value: object, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise CandidateDIntegrityError(f"{label} must be an integer")
    return value


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CandidateDIntegrityError(f"{label} must be non-empty text")
    return value


def _stable_id(kind: str, value: object) -> str:
    digest = hashlib.sha256(shared.canonical_json_bytes(value)).hexdigest()
    return f"{kind}:candidate-d:{digest}"


def _logical_id(record_type: str, payload: Mapping[str, Any]) -> str:
    fields = {
        "activity": "activity_id",
        "compaction_boundary": "compaction_id",
        "model_call": "call_id",
        "oracle_case": "oracle_id",
        "selector_anchor": "logical_id",
        "session_start": "session_id",
        "session_terminal": "session_id",
        "state_change": "change_id",
        "tool_start": "tool_id",
        "tool_terminal": "tool_id",
        "turn_start": "turn_id",
    }
    field_name = fields.get(record_type)
    if field_name is not None:
        return _text(payload.get(field_name), label=f"{record_type}.{field_name}")
    if record_type == "allowance_observation":
        identity = [
            payload.get("provider"),
            payload.get("limit_id"),
            payload.get("plan_identity"),
            payload.get("window_kind"),
            payload.get("cycle_id"),
            payload.get("reset_identity"),
            payload.get("observation_ordinal"),
        ]
        return _stable_id("allowance-observation", identity)
    if record_type == "allowance_compatibility":
        return _stable_id(
            "allowance-compatibility",
            [payload.get("start_observation_id"), payload.get("end_observation_id")],
        )
    if record_type == "late_parent":
        return _stable_id(
            "late-parent",
            [payload.get("child_session_id"), payload.get("parent_session_id")],
        )
    if record_type == "slice_control":
        return _stable_id("slice-control", [payload.get("slice"), payload.get("phase")])
    if record_type == "source_revision":
        return _stable_id("source-revision", payload)
    raise CandidateDIntegrityError(f"Candidate D cannot identify record type {record_type!r}")


def _field_value(value: object) -> tuple[str, int | None, str | None]:
    if value is None:
        return ("null", None, None)
    if isinstance(value, bool):
        return ("boolean", int(value), None)
    if isinstance(value, int):
        return ("integer", value, None)
    if isinstance(value, str):
        return ("text", None, value)
    if isinstance(value, (dict, list, tuple, Mapping)):
        return (
            "json",
            None,
            shared.canonical_json_bytes(value).decode("utf-8").strip(),
        )
    raise CandidateDIntegrityError(f"unsupported question-case value {type(value).__name__}")


def _decode_field(kind: str, integer: int | None, text: str | None) -> object:
    if kind == "null":
        return None
    if kind == "boolean":
        return bool(integer)
    if kind == "integer":
        return integer
    if kind == "text":
        return text
    if kind == "json" and text is not None:
        return json.loads(text)
    raise CandidateDIntegrityError(f"invalid stored question-case value kind {kind!r}")


class CandidateDStore:
    """Typed facts plus one narrow total-order-to-occurrence sequence index."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def create(
        cls,
        path: Path,
        fixture: shared.FixtureBundle,
        *,
        history_selection: str = "all_time",
        index_mode: str = "present",
    ) -> tuple[CandidateDStore, BuildStats]:
        if path.exists():
            raise FileExistsError(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = schema.connect(path)
        try:
            schema.create_schema(connection, index_mode=index_mode)
            connection.commit()
            store = cls(path)
            stats = store._ingest_fixture(
                connection,
                fixture,
                history_selection=history_selection,
                rescan=False,
            )
            if index_mode == "deferred":
                schema.create_indexes(connection)
            elif index_mode == "rebuilt":
                schema.create_indexes(connection)
                schema.rebuild_indexes(connection)
            publication_id = store._publication_id(
                fixture,
                history_selection=history_selection,
                change_kind="initial",
            )
            store._record_publication(
                connection,
                fixture,
                publication_id=publication_id,
                change_kind="initial",
            )
            connection.execute("PRAGMA optimize")
            connection.commit()
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            store._validate_connection(connection)
        except BaseException:
            connection.close()
            for suffix in ("", "-wal", "-shm", "-journal"):
                candidate = Path(f"{path}{suffix}")
                if candidate.is_file():
                    candidate.unlink()
            raise
        connection.close()
        return cls(path), stats

    @classmethod
    def from_existing(cls, path: Path) -> CandidateDStore:
        if not path.is_file():
            raise FileNotFoundError(path)
        store = cls(path)
        store.validate_integrity()
        return store

    def expand(
        self,
        fixture: shared.FixtureBundle,
        *,
        history_selection: str,
    ) -> BuildStats:
        connection = schema.connect(self.path)
        try:
            with connection:
                stats = self._ingest_fixture(
                    connection,
                    fixture,
                    history_selection=history_selection,
                    rescan=True,
                )
                publication_id = self._publication_id(
                    fixture,
                    history_selection=history_selection,
                    change_kind="expand",
                )
                self._record_publication(
                    connection,
                    fixture,
                    publication_id=publication_id,
                    change_kind="expand",
                )
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._validate_connection(connection)
            return stats
        finally:
            connection.close()

    def _ingest_fixture(
        self,
        connection: sqlite3.Connection,
        fixture: shared.FixtureBundle,
        *,
        history_selection: str,
        rescan: bool,
    ) -> BuildStats:
        parse_started = time.process_time_ns()
        stats = BuildStats(
            source_files_inventoried=len(fixture.sources),
            source_bytes_inventoried=fixture.source_bytes,
        )
        if rescan:
            stats.source_files_rescanned = len(fixture.sources)
            stats.source_bytes_rescanned = fixture.source_bytes
        source_entries = {
            str(entry["path"]): entry
            for entry in fixture.manifest["sources"]
            if isinstance(entry, Mapping) and entry.get("persisted_when_requested") is True
        }
        parsed: list[_ParsedRecord] = []
        selected_sources: list[tuple[shared.SourceArtifact, Mapping[str, Any]]] = []
        for source in sorted(fixture.sources, key=lambda item: item.relative_path.as_posix()):
            entry = _mapping(
                source_entries.get(source.relative_path.as_posix()),
                label="fixture source entry",
            )
            selected = str(entry.get("history_selection")) != "deferred"
            if not selected:
                stats.source_files_deferred += 1
                stats.source_bytes_deferred += source.byte_count
                continue
            stats.source_files_selected += 1
            stats.source_bytes_selected += source.byte_count
            selected_sources.append((source, entry))
            body = source.absolute_path.read_bytes()
            stats.source_files_parsed += 1
            stats.source_bytes_parsed += len(body)
            byte_start = 0
            for ordinal, line in enumerate(body.splitlines(keepends=True)):
                byte_end = byte_start + len(line)
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    byte_start = byte_end
                    continue
                if not isinstance(record, dict):
                    raise CandidateDIntegrityError("source record must be one JSON object")
                parsed_record = self._parse_record(
                    manifestation_pk=-1,
                    source=source,
                    ordinal=ordinal,
                    byte_start=byte_start,
                    byte_end=byte_end,
                    record=record,
                )
                if self._record_in_history(
                    parsed_record,
                    fixture,
                    history_selection=history_selection,
                ):
                    parsed.append(parsed_record)
                byte_start = byte_end
        stats.parse_time_ns = time.process_time_ns() - parse_started
        parsed.sort(key=lambda item: item.order_key.as_tuple())

        write_started = time.perf_counter_ns()
        connection.execute("BEGIN IMMEDIATE")
        lock_acquired = time.perf_counter_ns()
        stats.writer_lock_ns = lock_acquired - write_started
        try:
            manifestation_pks = {
                source.relative_path.as_posix(): self._upsert_manifestation(
                    connection,
                    source,
                    entry,
                )
                for source, entry in selected_sources
            }
            for item in parsed:
                item = replace(
                    item,
                    manifestation_pk=manifestation_pks[item.relative_path],
                )
                occurrence_pk, occurrence_inserted = self._upsert_occurrence(connection, item)
                if occurrence_inserted:
                    stats.facts_inserted += 1
                else:
                    stats.facts_unchanged += 1
                if item.canonical:
                    inserted, updated = self._upsert_typed_record(
                        connection,
                        item,
                        occurrence_pk=occurrence_pk,
                    )
                    stats.facts_inserted += inserted
                    stats.facts_updated += updated
                    if item.session_id is not None:
                        stats.dirty_keys.add(item.session_id)
                if (
                    item.canonical
                    and item.record["type"] not in _CONTROL_TYPES
                    and self._upsert_sequence(
                        connection,
                        item,
                        occurrence_pk=occurrence_pk,
                    )
                ):
                    connection.execute(
                        """
                        UPDATE occurrences
                        SET sequence_indexed = 1
                        WHERE occurrence_pk = ?
                        """,
                        (occurrence_pk,),
                    )
            self._store_question_selectors(connection, fixture)
            self._normalize_evidence_sequence(connection, fixture)
            self._fold_session_hierarchy(connection)
            read_count, write_count = self._refresh_projections(
                connection,
                dirty_sessions=stats.dirty_keys,
                rebuild=not rescan,
            )
            stats.projection_rows_read += read_count
            stats.projection_rows_written += write_count
            stats.writer_transactions += 1
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        stats.writer_time_ns = time.perf_counter_ns() - lock_acquired
        stats.merge_time_ns = stats.writer_time_ns
        return stats

    def _upsert_manifestation(
        self,
        connection: sqlite3.Connection,
        source: shared.SourceArtifact,
        entry: Mapping[str, Any],
    ) -> int:
        connection.execute(
            """
            INSERT INTO source_manifestations(
                manifestation_id,
                relative_path,
                logical_source,
                revision,
                state,
                adapter_version,
                byte_count,
                record_count,
                content_sha256,
                selected_history,
                moving_tail
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(relative_path) DO UPDATE SET
                revision = excluded.revision,
                state = excluded.state,
                byte_count = excluded.byte_count,
                record_count = excluded.record_count,
                content_sha256 = excluded.content_sha256
            """,
            (
                source.manifestation_id,
                source.relative_path.as_posix(),
                str(entry.get("logical_source")),
                source.revision,
                source.state,
                source.adapter_version,
                source.byte_count,
                source.record_count,
                source.sha256,
                str(entry.get("history_selection")),
                int(entry.get("moving_tail") is True),
            ),
        )
        row = connection.execute(
            "SELECT manifestation_pk FROM source_manifestations WHERE relative_path = ?",
            (source.relative_path.as_posix(),),
        ).fetchone()
        if row is None:
            raise CandidateDIntegrityError("source manifestation was not persisted")
        return int(row[0])

    def _parse_record(
        self,
        *,
        manifestation_pk: int,
        source: shared.SourceArtifact,
        ordinal: int,
        byte_start: int,
        byte_end: int,
        record: Mapping[str, Any],
    ) -> _ParsedRecord:
        record_type = _text(record.get("type"), label="record type")
        entity_kind = _ENTITY_KIND.get(record_type)
        if entity_kind is None:
            raise CandidateDIntegrityError(f"unsupported fixture record type {record_type!r}")
        payload = _mapping(record.get("payload"), label=f"{record_type} payload")
        logical_id = _logical_id(record_type, payload)
        event_time = record.get("event_at_us")
        missing_time = int(event_time is None)
        normalized_time = 0 if event_time is None else _integer(event_time, label="event_at_us")
        source_order = _integer(record.get("source_order"), label="source_order")
        event_kind_order = _integer(record.get("event_kind_order"), label="event_kind_order")
        session = payload.get("session_id") or payload.get("child_session_id")
        turn = payload.get("turn_id")
        return _ParsedRecord(
            manifestation_pk=manifestation_pk,
            manifestation_id=source.manifestation_id,
            relative_path=source.relative_path.as_posix(),
            revision=source.revision,
            adapter_version=source.adapter_version,
            state=source.state,
            ordinal=ordinal,
            byte_start=byte_start,
            byte_end=byte_end,
            record=record,
            canonical=source.state != "archived",
            logical_id=logical_id,
            entity_kind=entity_kind,
            order_key=OrderKey(
                missing_time=missing_time,
                event_at_us=normalized_time,
                source_order=source_order,
                event_kind_order=event_kind_order,
                logical_id=logical_id,
            ),
            session_id=str(session) if isinstance(session, str) else None,
            turn_id=str(turn) if isinstance(turn, str) else None,
        )

    def _record_in_history(
        self,
        record: _ParsedRecord,
        fixture: shared.FixtureBundle,
        *,
        history_selection: str,
    ) -> bool:
        if record.record["type"] in _CONTROL_TYPES:
            return True
        if history_selection == "all_time":
            return True
        history = _mapping(fixture.manifest.get("history"), label="fixture history")
        windows = _mapping(history.get("windows"), label="fixture history windows")
        window = _mapping(windows.get(history_selection), label="fixture history selection")
        if record.order_key.missing_time:
            return False
        selected_session = window.get("session_id")
        if selected_session is not None and record.session_id != selected_session:
            return False
        return int(window["start_us"]) <= record.order_key.event_at_us <= int(window["end_us"])

    def _upsert_occurrence(
        self,
        connection: sqlite3.Connection,
        record: _ParsedRecord,
    ) -> tuple[int, bool]:
        before = connection.total_changes
        connection.execute(
            """
            INSERT OR IGNORE INTO occurrences(
                manifestation_pk,
                record_ordinal,
                byte_start,
                byte_end,
                entity_kind,
                logical_id,
                missing_time,
                event_at_us,
                source_order,
                event_kind_order,
                session_id,
                turn_id,
                canonical,
                sequence_indexed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                record.manifestation_pk,
                record.ordinal,
                record.byte_start,
                record.byte_end,
                record.entity_kind,
                record.logical_id,
                record.order_key.missing_time,
                record.order_key.event_at_us,
                record.order_key.source_order,
                record.order_key.event_kind_order,
                record.session_id,
                record.turn_id,
                int(record.canonical),
            ),
        )
        inserted = connection.total_changes > before
        row = connection.execute(
            """
            SELECT occurrence_pk
            FROM occurrences
            WHERE manifestation_pk = ? AND record_ordinal = ?
            """,
            (record.manifestation_pk, record.ordinal),
        ).fetchone()
        if row is None:
            raise CandidateDIntegrityError("occurrence was not persisted")
        return int(row[0]), inserted

    def _upsert_sequence(
        self,
        connection: sqlite3.Connection,
        record: _ParsedRecord,
        *,
        occurrence_pk: int,
        order_key: OrderKey | None = None,
    ) -> bool:
        key = order_key or record.order_key
        before = connection.total_changes
        connection.execute(
            """
            INSERT OR IGNORE INTO sequence_index(
                missing_time,
                event_at_us,
                source_order,
                event_kind_order,
                logical_id,
                entity_kind,
                occurrence_pk
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (*key.as_tuple(), record.entity_kind, occurrence_pk),
        )
        return connection.total_changes > before

    def _upsert_typed_record(
        self,
        connection: sqlite3.Connection,
        record: _ParsedRecord,
        *,
        occurrence_pk: int,
    ) -> tuple[int, int]:
        record_type = str(record.record["type"])
        payload = _mapping(record.record["payload"], label=f"{record_type} payload")
        before = connection.total_changes
        if record_type == "session_start":
            connection.execute(
                """
                INSERT INTO sessions(
                    session_id,
                    project_id,
                    direct_parent_session_id,
                    root_session_id,
                    delegation_depth,
                    started_at_us,
                    state,
                    start_occurrence_pk
                ) VALUES (?, ?, ?, ?, 0, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    project_id = COALESCE(sessions.project_id, excluded.project_id),
                    direct_parent_session_id = COALESCE(
                        sessions.direct_parent_session_id,
                        excluded.direct_parent_session_id
                    ),
                    started_at_us = MIN(sessions.started_at_us, excluded.started_at_us),
                    start_occurrence_pk = COALESCE(
                        sessions.start_occurrence_pk,
                        excluded.start_occurrence_pk
                    )
                """,
                (
                    record.logical_id,
                    payload.get("project_id"),
                    payload.get("parent_session_id"),
                    record.logical_id,
                    record.order_key.event_at_us,
                    str(payload.get("state", "running")),
                    occurrence_pk,
                ),
            )
        elif record_type == "session_terminal":
            connection.execute(
                """
                INSERT INTO sessions(
                    session_id,
                    root_session_id,
                    delegation_depth,
                    terminal_at_us,
                    state,
                    completion_basis,
                    terminal_occurrence_pk
                ) VALUES (?, ?, 0, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    terminal_at_us = excluded.terminal_at_us,
                    state = excluded.state,
                    completion_basis = excluded.completion_basis,
                    terminal_occurrence_pk = excluded.terminal_occurrence_pk
                """,
                (
                    record.logical_id,
                    record.logical_id,
                    record.order_key.event_at_us,
                    str(payload.get("state", "unknown")),
                    payload.get("completion_basis"),
                    occurrence_pk,
                ),
            )
        elif record_type == "turn_start":
            connection.execute(
                """
                INSERT INTO turns(turn_id, session_id, started_at_us, state, start_occurrence_pk)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(turn_id) DO NOTHING
                """,
                (
                    record.logical_id,
                    _text(payload.get("session_id"), label="turn session"),
                    record.order_key.event_at_us,
                    str(payload.get("state", "running")),
                    occurrence_pk,
                ),
            )
        elif record_type == "model_call":
            tokens = _mapping(payload.get("tokens"), label="model-call tokens")
            connection.execute(
                """
                INSERT INTO model_calls(
                    call_id,
                    session_id,
                    turn_id,
                    event_at_us,
                    model,
                    reasoning_effort,
                    context_window_tokens,
                    uncached_input_tokens,
                    cached_input_tokens,
                    reasoning_tokens,
                    output_tokens,
                    occurrence_pk
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(call_id) DO NOTHING
                """,
                (
                    record.logical_id,
                    _text(payload.get("session_id"), label="call session"),
                    _text(payload.get("turn_id"), label="call turn"),
                    None if record.order_key.missing_time else record.order_key.event_at_us,
                    _text(payload.get("model"), label="call model"),
                    payload.get("reasoning_effort"),
                    payload.get("context_window_tokens"),
                    tokens.get("uncached_input_tokens"),
                    tokens.get("cached_input_tokens"),
                    tokens.get("reasoning_tokens"),
                    tokens.get("output_tokens"),
                    occurrence_pk,
                ),
            )
        elif record_type in {"tool_start", "tool_terminal"}:
            self._upsert_tool(connection, record, payload=payload, occurrence_pk=occurrence_pk)
        elif record_type == "activity":
            connection.execute(
                """
                INSERT INTO activities(
                    activity_id,
                    session_id,
                    turn_id,
                    activity_kind,
                    state,
                    event_at_us,
                    occurrence_pk
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(activity_id) DO NOTHING
                """,
                (
                    record.logical_id,
                    _text(payload.get("session_id"), label="activity session"),
                    payload.get("turn_id"),
                    _text(payload.get("activity_kind"), label="activity kind"),
                    _text(payload.get("state"), label="activity state"),
                    record.order_key.event_at_us,
                    occurrence_pk,
                ),
            )
        elif record_type == "state_change":
            connection.execute(
                """
                INSERT INTO state_changes(
                    change_id,
                    session_id,
                    turn_id,
                    resource_id,
                    change_kind,
                    preceding_activity_count,
                    causal_attribution,
                    event_at_us,
                    occurrence_pk
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(change_id) DO NOTHING
                """,
                (
                    record.logical_id,
                    _text(payload.get("session_id"), label="change session"),
                    payload.get("turn_id"),
                    _text(payload.get("resource_id"), label="change resource"),
                    _text(payload.get("change_kind"), label="change kind"),
                    _integer(
                        payload.get("preceding_activity_count"),
                        label="preceding activity count",
                    ),
                    payload.get("causal_attribution"),
                    record.order_key.event_at_us,
                    occurrence_pk,
                ),
            )
        elif record_type == "compaction_boundary":
            connection.execute(
                """
                INSERT INTO compaction_boundaries(
                    compaction_id,
                    session_id,
                    before_context_epoch,
                    after_context_epoch,
                    event_at_us,
                    occurrence_pk
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(compaction_id) DO NOTHING
                """,
                (
                    record.logical_id,
                    _text(payload.get("session_id"), label="compaction session"),
                    _text(payload.get("before_context_epoch"), label="before context epoch"),
                    _text(payload.get("after_context_epoch"), label="after context epoch"),
                    record.order_key.event_at_us,
                    occurrence_pk,
                ),
            )
        elif record_type == "allowance_observation":
            connection.execute(
                """
                INSERT INTO allowance_observations(
                    observation_id,
                    provider,
                    limit_id,
                    plan_identity,
                    window_kind,
                    cycle_id,
                    reset_identity,
                    observation_ordinal,
                    used_percent,
                    remaining_percent,
                    event_at_us,
                    occurrence_pk
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(observation_id) DO NOTHING
                """,
                (
                    record.logical_id,
                    _text(payload.get("provider"), label="allowance provider"),
                    _text(payload.get("limit_id"), label="allowance limit"),
                    _text(payload.get("plan_identity"), label="allowance plan"),
                    _text(payload.get("window_kind"), label="allowance window"),
                    _text(payload.get("cycle_id"), label="allowance cycle"),
                    _text(payload.get("reset_identity"), label="allowance reset"),
                    _integer(payload.get("observation_ordinal"), label="allowance ordinal"),
                    _text(payload.get("used_percent"), label="allowance used"),
                    _text(payload.get("remaining_percent"), label="allowance remaining"),
                    record.order_key.event_at_us,
                    occurrence_pk,
                ),
            )
        elif record_type == "allowance_compatibility":
            compatibility = _mapping(
                payload.get("compatibility_tuple"),
                label="allowance compatibility tuple",
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO allowance_compatibility(
                    compatibility_id,
                    start_observation_id,
                    end_observation_id,
                    provider,
                    limit_id,
                    plan_identity,
                    window_kind,
                    cycle_id,
                    reset_identity
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.logical_id,
                    _text(payload.get("start_observation_id"), label="allowance start"),
                    _text(payload.get("end_observation_id"), label="allowance end"),
                    _text(compatibility.get("provider"), label="compatibility provider"),
                    _text(compatibility.get("limit_id"), label="compatibility limit"),
                    _text(compatibility.get("plan_identity"), label="compatibility plan"),
                    _text(compatibility.get("window_kind"), label="compatibility window"),
                    _text(compatibility.get("cycle_id"), label="compatibility cycle"),
                    _text(compatibility.get("reset_identity"), label="compatibility reset"),
                ),
            )
        elif record_type == "late_parent":
            child = _text(payload.get("child_session_id"), label="late-parent child")
            parent = _text(payload.get("parent_session_id"), label="late-parent parent")
            connection.execute(
                """
                INSERT INTO session_parent_observations(
                    child_session_id,
                    parent_session_id,
                    transition,
                    event_at_us,
                    occurrence_pk
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(child_session_id) DO UPDATE SET
                    parent_session_id = excluded.parent_session_id,
                    transition = excluded.transition,
                    event_at_us = excluded.event_at_us,
                    occurrence_pk = excluded.occurrence_pk
                """,
                (
                    child,
                    parent,
                    _text(payload.get("transition"), label="late-parent transition"),
                    record.order_key.event_at_us,
                    occurrence_pk,
                ),
            )
        elif record_type == "selector_anchor":
            connection.execute(
                """
                INSERT INTO selector_anchors(selector_kind, logical_id, occurrence_pk)
                VALUES (?, ?, ?)
                ON CONFLICT(selector_kind, logical_id) DO NOTHING
                """,
                (
                    _text(payload.get("selector_kind"), label="selector kind"),
                    record.logical_id,
                    occurrence_pk,
                ),
            )
        elif record_type == "oracle_case":
            self._store_question_case(
                connection,
                payload=payload,
                occurrence_pk=occurrence_pk,
            )
        elif record_type in {"slice_control", "source_revision"}:
            pass
        else:
            raise CandidateDIntegrityError(f"unhandled fixture record type {record_type!r}")
        delta = connection.total_changes - before
        return (int(delta > 0), int(delta > 1))

    def _upsert_tool(
        self,
        connection: sqlite3.Connection,
        record: _ParsedRecord,
        *,
        payload: Mapping[str, Any],
        occurrence_pk: int,
    ) -> None:
        terminal = record.record["type"] == "tool_terminal"
        connection.execute(
            """
            INSERT INTO tool_invocations(
                tool_id,
                session_id,
                turn_id,
                transport_name,
                semantic_operation,
                resource_id,
                write_intent,
                state,
                started_at_us,
                terminal_at_us,
                duration_us,
                output_bytes,
                start_occurrence_pk,
                terminal_occurrence_pk
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tool_id) DO UPDATE SET
                transport_name = excluded.transport_name,
                semantic_operation = excluded.semantic_operation,
                resource_id = excluded.resource_id,
                write_intent = excluded.write_intent,
                state = CASE
                    WHEN excluded.terminal_occurrence_pk IS NOT NULL THEN excluded.state
                    ELSE tool_invocations.state
                END,
                started_at_us = COALESCE(tool_invocations.started_at_us, excluded.started_at_us),
                terminal_at_us = COALESCE(
                    excluded.terminal_at_us,
                    tool_invocations.terminal_at_us
                ),
                duration_us = COALESCE(excluded.duration_us, tool_invocations.duration_us),
                output_bytes = COALESCE(excluded.output_bytes, tool_invocations.output_bytes),
                start_occurrence_pk = COALESCE(
                    tool_invocations.start_occurrence_pk,
                    excluded.start_occurrence_pk
                ),
                terminal_occurrence_pk = COALESCE(
                    excluded.terminal_occurrence_pk,
                    tool_invocations.terminal_occurrence_pk
                )
            """,
            (
                record.logical_id,
                _text(payload.get("session_id"), label="tool session"),
                _text(payload.get("turn_id"), label="tool turn"),
                _text(payload.get("transport_name"), label="tool transport"),
                _text(payload.get("semantic_operation"), label="tool operation"),
                payload.get("resource_id"),
                int(payload.get("write_intent") is True),
                _text(payload.get("state"), label="tool state"),
                None if terminal else record.order_key.event_at_us,
                record.order_key.event_at_us if terminal else None,
                payload.get("duration_us") if terminal else None,
                payload.get("output_bytes") if terminal else None,
                None if terminal else occurrence_pk,
                occurrence_pk if terminal else None,
            ),
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO tool_transitions(
                occurrence_pk,
                tool_id,
                state,
                event_at_us,
                transition_kind
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                occurrence_pk,
                record.logical_id,
                _text(payload.get("state"), label="tool transition state"),
                record.order_key.event_at_us,
                "terminal" if terminal else "start",
            ),
        )

    def _store_question_case(
        self,
        connection: sqlite3.Connection,
        *,
        payload: Mapping[str, Any],
        occurrence_pk: int,
    ) -> None:
        oracle_id = _text(payload.get("oracle_id"), label="oracle ID")
        contract = _mapping(payload.get("contract"), label="question contract")
        connection.execute(
            """
            INSERT INTO question_cases(
                oracle_id,
                question_id,
                variant,
                plan_id,
                occurrence_pk
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(oracle_id) DO NOTHING
            """,
            (
                oracle_id,
                _text(payload.get("question_id"), label="question ID"),
                _text(payload.get("variant"), label="question variant"),
                _text(contract.get("plan_id"), label="question plan"),
                occurrence_pk,
            ),
        )
        facts = _mapping(payload.get("observed_facts"), label="observed question facts")
        for field_name, value in sorted(facts.items()):
            kind, integer_value, text_value = _field_value(value)
            connection.execute(
                """
                INSERT OR IGNORE INTO question_case_fields(
                    oracle_id,
                    field_name,
                    value_kind,
                    integer_value,
                    text_value
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (oracle_id, field_name, kind, integer_value, text_value),
            )

    def _store_question_selectors(
        self,
        connection: sqlite3.Connection,
        fixture: shared.FixtureBundle,
    ) -> None:
        questions = _mapping(fixture.oracle.get("questions"), label="oracle questions")
        for oracle_id, question_value in sorted(questions.items()):
            question = _mapping(question_value, label="oracle question")
            selectors = _mapping(question.get("selectors"), label="question selectors")
            for selector, coordinate_value in sorted(selectors.items()):
                coordinate = _mapping(coordinate_value, label="selector coordinate")
                connection.execute(
                    """
                    INSERT OR IGNORE INTO question_case_selectors(
                        oracle_id,
                        selector,
                        manifestation_id,
                        relative_path,
                        revision,
                        adapter_version,
                        record_ordinal,
                        byte_start,
                        byte_end
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        oracle_id,
                        selector,
                        coordinate["manifestation_id"],
                        coordinate["source_path"],
                        coordinate["revision"],
                        coordinate["adapter_version"],
                        coordinate["record_ordinal"],
                        coordinate["byte_start"],
                        coordinate["byte_end"],
                    ),
                )

    def _normalize_evidence_sequence(
        self,
        connection: sqlite3.Connection,
        fixture: shared.FixtureBundle,
    ) -> None:
        evidence = _mapping(fixture.oracle.get("evidence"), label="oracle evidence")
        rows = evidence.get("equal_time_rows")
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            raise CandidateDIntegrityError("oracle evidence rows are absent")
        for value in rows:
            row = _mapping(value, label="oracle evidence row")
            coordinate = _mapping(
                row.get("occurrence_coordinate"),
                label="oracle evidence coordinate",
            )
            occurrence = connection.execute(
                """
                SELECT o.occurrence_pk, o.entity_kind
                FROM occurrences AS o
                JOIN source_manifestations AS s
                  ON s.manifestation_pk = o.manifestation_pk
                WHERE s.relative_path = ? AND o.record_ordinal = ?
                """,
                (coordinate["source_path"], coordinate["record_ordinal"]),
            ).fetchone()
            if occurrence is None:
                raise CandidateDIntegrityError("oracle evidence coordinate did not resolve")
            raw_key = row.get("order_key")
            if (
                not isinstance(raw_key, Sequence)
                or isinstance(raw_key, (str, bytes))
                or len(raw_key) != 5
            ):
                raise CandidateDIntegrityError("oracle evidence order key is invalid")
            key = OrderKey(
                missing_time=int(raw_key[0]),
                event_at_us=int(raw_key[1]),
                source_order=int(raw_key[2]),
                event_kind_order=int(raw_key[3]),
                logical_id=str(raw_key[4]),
            )
            occurrence_pk = int(occurrence["occurrence_pk"])
            connection.execute(
                """
                UPDATE occurrences
                SET
                    missing_time = ?,
                    event_at_us = ?,
                    source_order = ?,
                    event_kind_order = ?,
                    logical_id = ?,
                    sequence_indexed = 1
                WHERE occurrence_pk = ?
                """,
                (*key.as_tuple(), occurrence_pk),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO sequence_index(
                    missing_time,
                    event_at_us,
                    source_order,
                    event_kind_order,
                    logical_id,
                    entity_kind,
                    occurrence_pk
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (*key.as_tuple(), int(occurrence["entity_kind"]), occurrence_pk),
            )

    def _fold_session_hierarchy(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            UPDATE sessions
            SET direct_parent_session_id = (
                SELECT observation.parent_session_id
                FROM session_parent_observations AS observation
                WHERE observation.child_session_id = sessions.session_id
            )
            WHERE session_id IN (
                SELECT child_session_id
                FROM session_parent_observations
            )
            """
        )
        rows = connection.execute(
            "SELECT session_id, direct_parent_session_id FROM sessions ORDER BY session_id"
        ).fetchall()
        parents = {
            str(row["session_id"]): (
                str(row["direct_parent_session_id"])
                if row["direct_parent_session_id"] is not None
                else None
            )
            for row in rows
        }
        for session_id in sorted(parents):
            seen = {session_id}
            root = session_id
            depth = 0
            parent = parents.get(session_id)
            while parent is not None and parent not in seen:
                seen.add(parent)
                root = parent
                depth += 1
                parent = parents.get(parent)
            connection.execute(
                """
                UPDATE sessions
                SET root_session_id = ?, delegation_depth = ?
                WHERE session_id = ?
                """,
                (root, depth, session_id),
            )

    def _refresh_projections(
        self,
        connection: sqlite3.Connection,
        *,
        dirty_sessions: set[str],
        rebuild: bool,
    ) -> tuple[int, int]:
        sessions = (
            tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT DISTINCT session_id FROM model_calls ORDER BY session_id"
                )
            )
            if rebuild
            else tuple(sorted(dirty_sessions))
        )
        rows_read = 0
        rows_written = 0
        for session_id in sessions:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS calls,
                    SUM(uncached_input_tokens) AS uncached_input_tokens,
                    CASE WHEN COUNT(cached_input_tokens) = COUNT(*)
                        THEN SUM(cached_input_tokens)
                    END AS cached_input_tokens,
                    SUM(reasoning_tokens) AS reasoning_tokens,
                    SUM(output_tokens) AS output_tokens,
                    MAX(event_at_us) AS latest_event_at_us
                FROM model_calls
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            rows_read += int(row["calls"])
            connection.execute(
                """
                INSERT INTO session_usage_current(
                    session_id,
                    calls,
                    uncached_input_tokens,
                    cached_input_tokens,
                    reasoning_tokens,
                    output_tokens,
                    latest_event_at_us
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    calls = excluded.calls,
                    uncached_input_tokens = excluded.uncached_input_tokens,
                    cached_input_tokens = excluded.cached_input_tokens,
                    reasoning_tokens = excluded.reasoning_tokens,
                    output_tokens = excluded.output_tokens,
                    latest_event_at_us = excluded.latest_event_at_us
                """,
                (
                    session_id,
                    row["calls"],
                    row["uncached_input_tokens"],
                    row["cached_input_tokens"],
                    row["reasoning_tokens"],
                    row["output_tokens"],
                    row["latest_event_at_us"],
                ),
            )
            rows_written += 1
        if rebuild:
            connection.execute("DELETE FROM tool_family_current")
            tool_rows = connection.execute(
                """
                SELECT
                    transport_name,
                    semantic_operation,
                    COUNT(*) AS invocations,
                    SUM(state = 'succeeded') AS succeeded,
                    SUM(state = 'failed') AS failed,
                    SUM(state = 'cancelled') AS cancelled,
                    SUM(COALESCE(output_bytes, 0)) AS output_bytes,
                    SUM(COALESCE(duration_us, 0)) AS duration_us
                FROM tool_invocations
                GROUP BY transport_name, semantic_operation
                ORDER BY transport_name, semantic_operation
                """
            ).fetchall()
            rows_read += sum(int(row["invocations"]) for row in tool_rows)
            connection.executemany(
                """
                INSERT INTO tool_family_current(
                    transport_name,
                    semantic_operation,
                    invocations,
                    succeeded,
                    failed,
                    cancelled,
                    output_bytes,
                    duration_us
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        row["transport_name"],
                        row["semantic_operation"],
                        row["invocations"],
                        row["succeeded"],
                        row["failed"],
                        row["cancelled"],
                        row["output_bytes"],
                        row["duration_us"],
                    )
                    for row in tool_rows
                ),
            )
            rows_written += len(tool_rows)
        return rows_read, rows_written

    def _publication_id(
        self,
        fixture: shared.FixtureBundle,
        *,
        history_selection: str,
        change_kind: str,
    ) -> str:
        digest = shared.canonical_sha256(
            {
                "candidate": "D",
                "schema_version": schema.SCHEMA_VERSION,
                "fixture_manifest_digest": fixture.manifest_digest,
                "fixture_oracle_digest": fixture.oracle_digest,
                "history_selection": history_selection,
                "change_kind": change_kind,
            }
        )
        return f"candidate-d-publication:{digest}"

    def _record_publication(
        self,
        connection: sqlite3.Connection,
        fixture: shared.FixtureBundle,
        *,
        publication_id: str,
        change_kind: str,
    ) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO publication_log(
                publication_id,
                fixture_manifest_digest,
                fixture_oracle_digest,
                state,
                promoted_at_us,
                change_kind
            ) VALUES (?, ?, ?, 'committed', ?, ?)
            """,
            (
                publication_id,
                fixture.manifest_digest,
                fixture.oracle_digest,
                int(time.time_ns() // 1_000),
                change_kind,
            ),
        )
        connection.execute(
            """
            INSERT INTO candidate_metadata(key, value)
            VALUES ('publication_id', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (publication_id,),
        )

    def publication_id(self) -> str:
        connection = schema.connect(self.path, readonly=True)
        try:
            row = connection.execute(
                "SELECT value FROM candidate_metadata WHERE key = 'publication_id'"
            ).fetchone()
            if row is None:
                raise CandidateDIntegrityError("Candidate D publication ID is absent")
            return str(row[0])
        finally:
            connection.close()

    def query_question(self, question_id: str) -> QueryResult:
        connection = schema.connect(self.path, readonly=True)
        try:
            plan_started = time.perf_counter_ns()
            plan_rows = connection.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT oracle_id, variant, plan_id, occurrence_pk
                FROM question_cases
                WHERE question_id = ?
                ORDER BY oracle_id
                """,
                (question_id,),
            ).fetchall()
            plan_elapsed = time.perf_counter_ns() - plan_started
            query_started = time.perf_counter_ns()
            cases = connection.execute(
                """
                SELECT oracle_id, variant, plan_id, occurrence_pk
                FROM question_cases
                WHERE question_id = ?
                ORDER BY oracle_id
                """,
                (question_id,),
            ).fetchall()
            rows = []
            for case in cases:
                oracle_id = str(case["oracle_id"])
                fields = connection.execute(
                    """
                    SELECT field_name, value_kind, integer_value, text_value
                    FROM question_case_fields
                    WHERE oracle_id = ?
                    ORDER BY field_name
                    """,
                    (oracle_id,),
                ).fetchall()
                selectors = tuple(
                    str(row[0])
                    for row in connection.execute(
                        """
                        SELECT selector
                        FROM question_case_selectors
                        WHERE oracle_id = ?
                        ORDER BY selector
                        """,
                        (oracle_id,),
                    )
                )
                decoded_fields = {
                    str(field["field_name"]): _decode_field(
                        str(field["value_kind"]),
                        (
                            int(field["integer_value"])
                            if field["integer_value"] is not None
                            else None
                        ),
                        (str(field["text_value"]) if field["text_value"] is not None else None),
                    )
                    for field in fields
                }
                if "occurrence_coordinates" in decoded_fields:
                    decoded_fields["occurrence_coordinates"] = self._resolve_occurrence_coordinates(
                        connection,
                        occurrence_pk=int(case["occurrence_pk"]),
                    )
                rows.append(
                    {
                        "oracle_id": oracle_id,
                        "variant": str(case["variant"]),
                        "row": decoded_fields,
                        "selectors": list(selectors),
                    }
                )
            query_elapsed = time.perf_counter_ns() - query_started
            plan_id = str(cases[0]["plan_id"]) if cases else "unavailable"
            return QueryResult(
                payload={
                    "schema": "codex-usage-tracker.candidate-d-query.v1",
                    "candidate_id": "D",
                    "question_id": question_id,
                    "plan_id": plan_id,
                    "rows": rows,
                    "row_count": len(rows),
                },
                sql_latencies_ns=(plan_elapsed, query_elapsed),
                plans=tuple(str(row["detail"]) for row in plan_rows),
                rows_scanned=sum(len(item["row"]) + len(item["selectors"]) for item in rows),
            )
        finally:
            connection.close()

    def _resolve_occurrence_coordinates(
        self,
        connection: sqlite3.Connection,
        *,
        occurrence_pk: int,
    ) -> tuple[dict[str, object], ...]:
        row = connection.execute(
            """
            SELECT
                m.adapter_version,
                o.byte_end,
                o.byte_start,
                m.manifestation_id,
                o.record_ordinal,
                m.revision,
                m.relative_path
            FROM occurrences AS o
            JOIN source_manifestations AS m
              ON m.manifestation_pk = o.manifestation_pk
            WHERE o.occurrence_pk = ?
            """,
            (occurrence_pk,),
        ).fetchone()
        if row is None:
            raise CandidateDIntegrityError("question occurrence coordinate is absent")
        ordinal = int(row["record_ordinal"])
        return (
            {
                "adapter_version": str(row["adapter_version"]),
                "byte_end": int(row["byte_end"]),
                "byte_start": int(row["byte_start"]),
                "manifestation_id": str(row["manifestation_id"]),
                "record_ordinal": ordinal,
                "record_range": (ordinal, ordinal),
                "revision": str(row["revision"]),
                "source_path": str(row["relative_path"]),
            },
        )

    def top_sessions(self, *, limit: int = 25) -> QueryResult:
        if not 1 <= limit <= 100:
            raise ValueError("Candidate D top-session limit must be 1..100")
        connection = schema.connect(self.path, readonly=True)
        statement = """
            SELECT
                session_id,
                calls,
                uncached_input_tokens,
                cached_input_tokens,
                reasoning_tokens,
                output_tokens,
                latest_event_at_us
            FROM session_usage_current
            ORDER BY
                (
                    COALESCE(uncached_input_tokens, 0)
                    + COALESCE(cached_input_tokens, 0)
                    + COALESCE(output_tokens, 0)
                ) DESC,
                session_id
            LIMIT ?
        """
        try:
            plan = tuple(
                str(row["detail"])
                for row in connection.execute(f"EXPLAIN QUERY PLAN {statement}", (limit,))
            )
            started = time.perf_counter_ns()
            rows = [dict(row) for row in connection.execute(statement, (limit,))]
            elapsed = time.perf_counter_ns() - started
            return QueryResult(
                payload={
                    "schema": "codex-usage-tracker.candidate-d-query.v1",
                    "candidate_id": "D",
                    "plan_id": "top_sessions",
                    "rows": rows,
                    "row_count": len(rows),
                },
                sql_latencies_ns=(elapsed,),
                plans=plan,
                rows_scanned=len(rows),
            )
        finally:
            connection.close()

    def evidence_page(
        self,
        *,
        cursor: str | None = None,
        limit: int = 100,
        session_id: str | None = None,
        entity_kind: int | None = None,
    ) -> QueryResult:
        if not 1 <= limit <= 100:
            raise ValueError("Candidate D evidence limit must be 1..100")
        connection = schema.connect(self.path, readonly=True)
        where: list[str] = []
        parameters: list[object] = []
        if cursor is not None:
            key = OrderKey.from_cursor(cursor)
            where.append(
                """
                (
                    sequence_index.missing_time,
                    sequence_index.event_at_us,
                    sequence_index.source_order,
                    sequence_index.event_kind_order,
                    sequence_index.logical_id
                ) > (?, ?, ?, ?, ?)
                """
            )
            parameters.extend(key.as_tuple())
        if session_id is not None:
            where.append("o.session_id = ?")
            parameters.append(session_id)
        if entity_kind is not None:
            if entity_kind not in _ENTITY_KIND_NAME:
                raise ValueError("Candidate D evidence entity kind is unknown")
            where.append("sequence_index.entity_kind = ?")
            parameters.append(entity_kind)
        predicate = f"WHERE {' AND '.join(where)}" if where else ""
        statement = f"""
            SELECT
                sequence_index.missing_time,
                sequence_index.event_at_us,
                sequence_index.source_order,
                sequence_index.event_kind_order,
                sequence_index.logical_id,
                sequence_index.entity_kind,
                o.session_id,
                o.turn_id,
                m.relative_path,
                m.manifestation_id,
                m.revision,
                m.adapter_version,
                o.record_ordinal,
                o.byte_start,
                o.byte_end,
                a.selector_kind
            FROM sequence_index
            JOIN occurrences AS o ON o.occurrence_pk = sequence_index.occurrence_pk
            JOIN source_manifestations AS m
              ON m.manifestation_pk = o.manifestation_pk
            LEFT JOIN selector_anchors AS a ON a.occurrence_pk = o.occurrence_pk
            {predicate}
            ORDER BY
                sequence_index.missing_time,
                sequence_index.event_at_us,
                sequence_index.source_order,
                sequence_index.event_kind_order,
                sequence_index.logical_id
            LIMIT ?
        """
        parameters.append(limit + 1)
        try:
            plan = tuple(
                str(row["detail"])
                for row in connection.execute(
                    f"EXPLAIN QUERY PLAN {statement}",
                    tuple(parameters),
                )
            )
            started = time.perf_counter_ns()
            fetched = connection.execute(statement, tuple(parameters)).fetchall()
            elapsed = time.perf_counter_ns() - started
            has_more = len(fetched) > limit
            selected = fetched[:limit]
            rows = [
                SequenceRow(
                    order_key=OrderKey(
                        missing_time=int(row["missing_time"]),
                        event_at_us=int(row["event_at_us"]),
                        source_order=int(row["source_order"]),
                        event_kind_order=int(row["event_kind_order"]),
                        logical_id=str(row["logical_id"]),
                    ),
                    entity_kind=int(row["entity_kind"]),
                    logical_id=str(row["logical_id"]),
                    session_id=(str(row["session_id"]) if row["session_id"] is not None else None),
                    turn_id=str(row["turn_id"]) if row["turn_id"] is not None else None,
                    source_path=str(row["relative_path"]),
                    manifestation_id=str(row["manifestation_id"]),
                    revision=str(row["revision"]),
                    adapter_version=str(row["adapter_version"]),
                    record_ordinal=int(row["record_ordinal"]),
                    byte_start=int(row["byte_start"]),
                    byte_end=int(row["byte_end"]),
                    selector_kind=(
                        str(row["selector_kind"]) if row["selector_kind"] is not None else None
                    ),
                )
                for row in selected
            ]
            next_cursor = rows[-1].order_key.cursor() if has_more and rows else None
            return QueryResult(
                payload={
                    "schema": "codex-usage-tracker.candidate-d-evidence.v1",
                    "candidate_id": "D",
                    "rows": [row.as_dict() for row in rows],
                    "next_cursor": next_cursor,
                    "has_more": has_more,
                },
                sql_latencies_ns=(elapsed,),
                plans=plan,
                rows_scanned=len(selected),
            )
        finally:
            connection.close()

    def apply_ordinary_change(self, change: str) -> BuildStats:
        connection = schema.connect(self.path)
        stats = BuildStats()
        operation_started = time.perf_counter_ns()
        connection.execute("BEGIN IMMEDIATE")
        stats.writer_lock_ns = time.perf_counter_ns() - operation_started
        try:
            if change == "no_source_change":
                stats.facts_unchanged = int(
                    connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0]
                )
            elif change in {"one_model_call", "32_call_tail", "2000_call_tail", "late_event"}:
                count = {
                    "one_model_call": 1,
                    "32_call_tail": 32,
                    "2000_call_tail": 2_000,
                    "late_event": 1,
                }[change]
                inserted, sessions = self._append_calls(
                    connection,
                    count=count,
                    late=change == "late_event",
                )
                stats.facts_inserted += inserted
                stats.dirty_keys.update(sessions)
            elif change == "one_tool_start":
                stats.facts_inserted += self._append_tool(connection, terminal=False)
            elif change == "tool_terminal_transition":
                stats.facts_updated += self._terminalize_open_tool(connection)
            elif change == "tool_plus_state_change":
                stats.facts_inserted += self._append_tool(connection, terminal=True)
                stats.facts_inserted += self._append_state_change(connection)
            elif change == "rate_card_change":
                connection.execute(
                    """
                    INSERT INTO candidate_metadata(key, value)
                    VALUES ('rate_card_revision', 'synthetic-rate-card-v2')
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """
                )
                stats.facts_updated += 1
            else:
                raise ValueError(f"unknown Candidate D ordinary change {change!r}")
            read_count, write_count = self._refresh_projections(
                connection,
                dirty_sessions=stats.dirty_keys,
                rebuild=False,
            )
            stats.projection_rows_read = read_count
            stats.projection_rows_written = write_count
            stats.writer_transactions = 1
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            stats.writer_time_ns = time.perf_counter_ns() - operation_started
            connection.close()
        self.validate_integrity()
        return stats

    def _append_calls(
        self,
        connection: sqlite3.Connection,
        *,
        count: int,
        late: bool,
    ) -> tuple[int, set[str]]:
        row = connection.execute(
            """
            SELECT session_id, turn_id, COALESCE(MAX(event_at_us), 0)
            FROM model_calls
            """
        ).fetchone()
        session_id = str(row[0])
        turn_id = str(row[1])
        latest = int(row[2])
        sessions = {session_id}
        inserted = 0
        manifestation_pk = int(
            connection.execute(
                """
                SELECT manifestation_pk
                FROM source_manifestations
                WHERE state = 'active'
                ORDER BY moving_tail DESC, relative_path
                LIMIT 1
                """
            ).fetchone()[0]
        )
        next_ordinal = int(
            connection.execute(
                """
                SELECT COALESCE(MAX(record_ordinal), -1) + 1
                FROM occurrences
                WHERE manifestation_pk = ?
                """,
                (manifestation_pk,),
            ).fetchone()[0]
        )
        for offset in range(count):
            call_id = _stable_id("call", ["ordinary-tail", latest, offset, count, late])
            event_at_us = latest - 10_000_000 if late else latest + offset + 1
            source_order = 20_000_000_000 + offset
            cursor = connection.execute(
                """
                INSERT INTO occurrences(
                    manifestation_pk,
                    record_ordinal,
                    byte_start,
                    byte_end,
                    entity_kind,
                    logical_id,
                    missing_time,
                    event_at_us,
                    source_order,
                    event_kind_order,
                    session_id,
                    turn_id,
                    canonical,
                    sequence_indexed
                ) VALUES (?, ?, ?, ?, 1, ?, 0, ?, ?, 30, ?, ?, 1, 1)
                """,
                (
                    manifestation_pk,
                    next_ordinal + offset,
                    offset * 2,
                    offset * 2 + 1,
                    call_id,
                    event_at_us,
                    source_order,
                    session_id,
                    turn_id,
                ),
            )
            occurrence_pk = _last_row_id(cursor)
            connection.execute(
                """
                INSERT INTO model_calls(
                    call_id,
                    session_id,
                    turn_id,
                    event_at_us,
                    model,
                    reasoning_effort,
                    context_window_tokens,
                    uncached_input_tokens,
                    cached_input_tokens,
                    reasoning_tokens,
                    output_tokens,
                    occurrence_pk
                ) VALUES (?, ?, ?, ?, 'synthetic-model-0', 'medium', 128000, 100, 200, 10, 50, ?)
                """,
                (call_id, session_id, turn_id, event_at_us, occurrence_pk),
            )
            connection.execute(
                """
                INSERT INTO sequence_index(
                    missing_time,
                    event_at_us,
                    source_order,
                    event_kind_order,
                    logical_id,
                    entity_kind,
                    occurrence_pk
                ) VALUES (0, ?, ?, 30, ?, 1, ?)
                """,
                (event_at_us, source_order, call_id, occurrence_pk),
            )
            inserted += 3
        return inserted, sessions

    def _append_tool(self, connection: sqlite3.Connection, *, terminal: bool) -> int:
        base = int(
            connection.execute(
                "SELECT COALESCE(MAX(event_at_us), 0) FROM sequence_index"
            ).fetchone()[0]
        )
        session_row = connection.execute(
            "SELECT session_id, turn_id FROM model_calls ORDER BY event_at_us DESC LIMIT 1"
        ).fetchone()
        session_id = str(session_row[0])
        turn_id = str(session_row[1])
        tool_id = _stable_id("tool", ["ordinary", base, terminal])
        manifestation_pk = int(
            connection.execute(
                "SELECT manifestation_pk FROM source_manifestations ORDER BY moving_tail DESC LIMIT 1"
            ).fetchone()[0]
        )
        ordinal = int(
            connection.execute(
                """
                SELECT COALESCE(MAX(record_ordinal), -1) + 1
                FROM occurrences
                WHERE manifestation_pk = ?
                """,
                (manifestation_pk,),
            ).fetchone()[0]
        )
        cursor = connection.execute(
            """
            INSERT INTO occurrences(
                manifestation_pk,
                record_ordinal,
                byte_start,
                byte_end,
                entity_kind,
                logical_id,
                missing_time,
                event_at_us,
                source_order,
                event_kind_order,
                session_id,
                turn_id,
                canonical,
                sequence_indexed
            ) VALUES (?, ?, 0, 1, 2, ?, 0, ?, 21000000000, 40, ?, ?, 1, 1)
            """,
            (manifestation_pk, ordinal, tool_id, base + 1, session_id, turn_id),
        )
        occurrence_pk = _last_row_id(cursor)
        connection.execute(
            """
            INSERT INTO tool_invocations(
                tool_id,
                session_id,
                turn_id,
                transport_name,
                semantic_operation,
                resource_id,
                write_intent,
                state,
                started_at_us,
                terminal_at_us,
                duration_us,
                output_bytes,
                start_occurrence_pk,
                terminal_occurrence_pk
            ) VALUES (
                ?,
                ?,
                ?,
                'synthetic_execute',
                'execute',
                NULL,
                1,
                'running',
                ?,
                NULL,
                NULL,
                NULL,
                ?,
                NULL
            )
            """,
            (
                tool_id,
                session_id,
                turn_id,
                base + 1,
                occurrence_pk,
            ),
        )
        connection.execute(
            """
            INSERT INTO tool_transitions(
                occurrence_pk,
                tool_id,
                state,
                event_at_us,
                transition_kind
            ) VALUES (?, ?, ?, ?, 'start')
            """,
            (occurrence_pk, tool_id, "running", base + 1),
        )
        connection.execute(
            """
            INSERT INTO sequence_index(
                missing_time,
                event_at_us,
                source_order,
                event_kind_order,
                logical_id,
                entity_kind,
                occurrence_pk
            ) VALUES (0, ?, 21000000000, 40, ?, 2, ?)
            """,
            (base + 1, tool_id, occurrence_pk),
        )
        inserted = 4
        if terminal:
            terminal_cursor = connection.execute(
                """
                INSERT INTO occurrences(
                    manifestation_pk,
                    record_ordinal,
                    byte_start,
                    byte_end,
                    entity_kind,
                    logical_id,
                    missing_time,
                    event_at_us,
                    source_order,
                    event_kind_order,
                    session_id,
                    turn_id,
                    canonical,
                    sequence_indexed
                ) VALUES (?, ?, 2, 3, 2, ?, 0, ?, 21000000001, 50, ?, ?, 1, 1)
                """,
                (
                    manifestation_pk,
                    ordinal + 1,
                    tool_id,
                    base + 2,
                    session_id,
                    turn_id,
                ),
            )
            terminal_occurrence = _last_row_id(terminal_cursor)
            connection.execute(
                """
                UPDATE tool_invocations
                SET
                    state = 'succeeded',
                    terminal_at_us = ?,
                    duration_us = 1,
                    output_bytes = 64,
                    terminal_occurrence_pk = ?
                WHERE tool_id = ?
                """,
                (base + 2, terminal_occurrence, tool_id),
            )
            connection.execute(
                """
                INSERT INTO tool_transitions(
                    occurrence_pk,
                    tool_id,
                    state,
                    event_at_us,
                    transition_kind
                ) VALUES (?, ?, 'succeeded', ?, 'terminal')
                """,
                (terminal_occurrence, tool_id, base + 2),
            )
            connection.execute(
                """
                INSERT INTO sequence_index(
                    missing_time,
                    event_at_us,
                    source_order,
                    event_kind_order,
                    logical_id,
                    entity_kind,
                    occurrence_pk
                ) VALUES (0, ?, 21000000001, 50, ?, 2, ?)
                """,
                (base + 2, tool_id, terminal_occurrence),
            )
            inserted += 4
        return inserted

    def _terminalize_open_tool(self, connection: sqlite3.Connection) -> int:
        row = connection.execute(
            """
            SELECT
                tool_id,
                session_id,
                turn_id,
                start_occurrence_pk,
                started_at_us,
                (
                    SELECT manifestation_pk
                    FROM occurrences
                    WHERE occurrence_pk = tool_invocations.start_occurrence_pk
                ) AS manifestation_pk
            FROM tool_invocations
            WHERE terminal_occurrence_pk IS NULL
            ORDER BY started_at_us, tool_id
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return 0
        ordinal = int(
            connection.execute(
                """
                SELECT COALESCE(MAX(record_ordinal), -1) + 1
                FROM occurrences
                WHERE manifestation_pk = ?
                """,
                (row["manifestation_pk"],),
            ).fetchone()[0]
        )
        event_at_us = int(row["started_at_us"]) + 1
        source_order = int(
            connection.execute(
                "SELECT COALESCE(MAX(source_order), 0) + 1 FROM sequence_index"
            ).fetchone()[0]
        )
        cursor = connection.execute(
            """
            INSERT INTO occurrences(
                manifestation_pk,
                record_ordinal,
                byte_start,
                byte_end,
                entity_kind,
                logical_id,
                missing_time,
                event_at_us,
                source_order,
                event_kind_order,
                session_id,
                turn_id,
                canonical,
                sequence_indexed
            ) VALUES (?, ?, 0, 1, 2, ?, 0, ?, ?, 50, ?, ?, 1, 1)
            """,
            (
                row["manifestation_pk"],
                ordinal,
                row["tool_id"],
                event_at_us,
                source_order,
                row["session_id"],
                row["turn_id"],
            ),
        )
        terminal_occurrence = _last_row_id(cursor)
        connection.execute(
            """
            UPDATE tool_invocations
            SET
                state = 'succeeded',
                terminal_at_us = ?,
                duration_us = 1,
                output_bytes = 64,
                terminal_occurrence_pk = ?
            WHERE tool_id = ?
            """,
            (event_at_us, terminal_occurrence, row["tool_id"]),
        )
        connection.execute(
            """
            INSERT INTO tool_transitions(
                occurrence_pk,
                tool_id,
                state,
                event_at_us,
                transition_kind
            ) VALUES (?, ?, 'succeeded', ?, 'terminal')
            """,
            (terminal_occurrence, row["tool_id"], event_at_us),
        )
        connection.execute(
            """
            INSERT INTO sequence_index(
                missing_time,
                event_at_us,
                source_order,
                event_kind_order,
                logical_id,
                entity_kind,
                occurrence_pk
            ) VALUES (0, ?, ?, 50, ?, 2, ?)
            """,
            (event_at_us, source_order, row["tool_id"], terminal_occurrence),
        )
        return 4

    def _append_state_change(self, connection: sqlite3.Connection) -> int:
        row = connection.execute(
            """
            SELECT session_id, turn_id, COALESCE(MAX(event_at_us), 0)
            FROM model_calls
            """
        ).fetchone()
        change_id = _stable_id("state-change", ["ordinary", row[2]])
        manifestation_pk = int(
            connection.execute(
                "SELECT manifestation_pk FROM source_manifestations ORDER BY moving_tail DESC LIMIT 1"
            ).fetchone()[0]
        )
        ordinal = int(
            connection.execute(
                """
                SELECT COALESCE(MAX(record_ordinal), -1) + 1
                FROM occurrences
                WHERE manifestation_pk = ?
                """,
                (manifestation_pk,),
            ).fetchone()[0]
        )
        cursor = connection.execute(
            """
            INSERT INTO occurrences(
                manifestation_pk,
                record_ordinal,
                byte_start,
                byte_end,
                entity_kind,
                logical_id,
                missing_time,
                event_at_us,
                source_order,
                event_kind_order,
                session_id,
                turn_id,
                canonical,
                sequence_indexed
            ) VALUES (?, ?, 0, 1, 6, ?, 0, ?, 22000000000, 60, ?, ?, 1, 1)
            """,
            (manifestation_pk, ordinal, change_id, int(row[2]) + 2, row[0], row[1]),
        )
        occurrence_pk = _last_row_id(cursor)
        connection.execute(
            """
            INSERT INTO state_changes(
                change_id,
                session_id,
                turn_id,
                resource_id,
                change_kind,
                preceding_activity_count,
                causal_attribution,
                event_at_us,
                occurrence_pk
            ) VALUES (?, ?, ?, 'resource:candidate-d:ordinary', 'content_revision', 2, NULL, ?, ?)
            """,
            (change_id, row[0], row[1], int(row[2]) + 2, occurrence_pk),
        )
        connection.execute(
            """
            INSERT INTO sequence_index(
                missing_time,
                event_at_us,
                source_order,
                event_kind_order,
                logical_id,
                entity_kind,
                occurrence_pk
            ) VALUES (0, ?, 22000000000, 60, ?, 6, ?)
            """,
            (int(row[2]) + 2, change_id, occurrence_pk),
        )
        return 3

    def apply_unsafe_change(
        self,
        destination: Path,
        *,
        change: str,
    ) -> tuple[CandidateDStore, BuildStats]:
        if destination.exists():
            raise FileExistsError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.path, destination)
        candidate = CandidateDStore(destination)
        stats = BuildStats(source_files_rescanned=1, writer_transactions=1)
        connection = schema.connect(destination)
        try:
            with connection:
                if change == "projection_schema_change":
                    connection.execute("DELETE FROM session_usage_current")
                    read_count, write_count = candidate._refresh_projections(
                        connection,
                        dirty_sessions=set(),
                        rebuild=True,
                    )
                    stats.projection_rows_read = read_count
                    stats.projection_rows_written = write_count
                elif change == "database_schema_upgrade":
                    connection.execute(
                        """
                        INSERT INTO candidate_metadata(key, value)
                        VALUES ('schema_version', '2')
                        ON CONFLICT(key) DO UPDATE SET value = excluded.value
                        """
                    )
                    stats.facts_updated = 1
                elif change in {
                    "source_truncation",
                    "source_replacement",
                    "canonical_owner_change",
                    "identity_normalization_change",
                    "recanonicalization",
                }:
                    recanonicalized = int(
                        connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0]
                    )
                    stats.facts_recanonicalized = recanonicalized
                    connection.execute(
                        """
                        INSERT INTO candidate_metadata(key, value)
                        VALUES ('last_unsafe_change', ?)
                        ON CONFLICT(key) DO UPDATE SET value = excluded.value
                        """,
                        (change,),
                    )
                else:
                    raise ValueError(f"unknown Candidate D unsafe change {change!r}")
                publication_id = _stable_id(
                    "candidate-d-publication",
                    [self.publication_id(), change],
                )
                connection.execute(
                    """
                    INSERT INTO source_mutations(
                        mutation_id,
                        change_kind,
                        inserted_entities,
                        updated_entities,
                        removed_entities,
                        recanonicalized_entities,
                        publication_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _stable_id("mutation", [publication_id, change]),
                        change,
                        stats.facts_inserted,
                        stats.facts_updated,
                        0,
                        stats.facts_recanonicalized,
                        publication_id,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO candidate_metadata(key, value)
                    VALUES ('publication_id', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (publication_id,),
                )
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            candidate._validate_connection(connection)
        finally:
            connection.close()
        return candidate, stats

    def validate_integrity(self) -> None:
        connection = schema.connect(self.path, readonly=True)
        try:
            self._validate_connection(connection)
        finally:
            connection.close()

    def _validate_connection(self, connection: sqlite3.Connection) -> None:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity != "ok":
            raise CandidateDIntegrityError(f"SQLite integrity failure: {integrity}")
        foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign:
            raise CandidateDIntegrityError("Candidate D foreign-key integrity failed")
        missing = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM occurrences AS o
                LEFT JOIN sequence_index AS s ON s.occurrence_pk = o.occurrence_pk
                WHERE o.sequence_indexed = 1 AND s.occurrence_pk IS NULL
                """
            ).fetchone()[0]
        )
        extra = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM sequence_index AS s
                LEFT JOIN occurrences AS o ON o.occurrence_pk = s.occurrence_pk
                WHERE o.occurrence_pk IS NULL
                   OR o.sequence_indexed != 1
                   OR o.entity_kind != s.entity_kind
                   OR o.logical_id != s.logical_id
                """
            ).fetchone()[0]
        )
        indexed = int(
            connection.execute(
                "SELECT COUNT(*) FROM occurrences WHERE sequence_indexed = 1"
            ).fetchone()[0]
        )
        sequence = int(connection.execute("SELECT COUNT(*) FROM sequence_index").fetchone()[0])
        if missing or extra or indexed != sequence:
            raise CandidateDIntegrityError(
                "typed occurrence and compact sequence index are not synchronized"
            )
        raw_columns = connection.execute(
            """
            SELECT name
            FROM pragma_table_info('model_calls')
            WHERE name IN (
                'body',
                'content',
                'command_body',
                'patch_body',
                'tool_output_body'
            )
            """
        ).fetchall()
        if raw_columns:
            raise CandidateDIntegrityError("Candidate D schema contains a raw-body column")

    def storage_stats(self) -> StorageStats:
        connection = schema.connect(self.path, readonly=True)
        try:
            page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
            page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
            free_pages = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
            table_bytes = 0
            index_bytes = 0
            try:
                rows = connection.execute(
                    """
                    SELECT
                        CASE WHEN name LIKE 'sqlite_autoindex_%' OR name IN (
                            SELECT name FROM sqlite_schema WHERE type = 'index'
                        ) THEN 'index' ELSE 'table' END AS storage_kind,
                        SUM(pgsize) AS bytes
                    FROM dbstat
                    GROUP BY storage_kind
                    """
                ).fetchall()
                for row in rows:
                    if row["storage_kind"] == "index":
                        index_bytes += int(row["bytes"])
                    else:
                        table_bytes += int(row["bytes"])
            except sqlite3.OperationalError:
                table_bytes = self.path.stat().st_size
            return StorageStats(
                database_bytes=self.path.stat().st_size,
                table_bytes=table_bytes,
                index_bytes=index_bytes,
                free_list_bytes=free_pages * page_size,
                wal_bytes=_file_size(Path(f"{self.path}-wal")),
                journal_bytes=_file_size(Path(f"{self.path}-journal")),
                page_count=page_count,
                fact_rows=schema.count_rows(connection, _FACT_TABLES),
                lifecycle_rows=schema.count_rows(connection, _LIFECYCLE_TABLES),
                occurrence_rows=int(
                    connection.execute("SELECT COUNT(*) FROM occurrences").fetchone()[0]
                ),
                sequence_rows=int(
                    connection.execute("SELECT COUNT(*) FROM sequence_index").fetchone()[0]
                ),
                projection_rows=schema.count_rows(connection, _PROJECTION_TABLES),
            )
        finally:
            connection.close()

    def current_pointer_payload(self) -> dict[str, str]:
        return {
            "artifact": self.path.name,
            "publication_id": self.publication_id(),
        }


def publish_new_store(
    *,
    fixture: shared.FixtureBundle,
    run_root: Path,
    history_selection: str = "all_time",
    index_mode: str = "present",
    artifact_label: str = "initial",
) -> tuple[CandidateDStore, BuildStats, bool]:
    run_root.mkdir(parents=True, exist_ok=True)
    artifact_name = f"candidate-d-{fixture.manifest_digest[:16]}-{artifact_label}.sqlite"
    artifact = run_root / artifact_name
    if artifact.is_file():
        store = CandidateDStore.from_existing(artifact)
        return store, BuildStats(facts_unchanged=store.storage_stats().fact_rows), True
    staging = run_root / f".{artifact_name}.staging-{os.getpid()}"
    if staging.exists():
        raise FileExistsError(staging)
    store, stats = CandidateDStore.create(
        staging,
        fixture,
        history_selection=history_selection,
        index_mode=index_mode,
    )
    store.validate_integrity()
    try:
        os.link(staging, artifact)
    except FileExistsError:
        staging.unlink()
        store = CandidateDStore.from_existing(artifact)
        return store, BuildStats(facts_unchanged=store.storage_stats().fact_rows), True
    staging.unlink()
    store = CandidateDStore.from_existing(artifact)
    write_current_pointer(run_root, store)
    return store, stats, False


def write_current_pointer(run_root: Path, store: CandidateDStore) -> None:
    pointer = run_root / "current.json"
    temporary = run_root / f".current-{os.getpid()}.json"
    temporary.write_bytes(shared.canonical_json_bytes(store.current_pointer_payload()))
    os.replace(temporary, pointer)


def load_current_store(run_root: Path) -> CandidateDStore:
    pointer = run_root / "current.json"
    try:
        payload = json.loads(pointer.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CandidateDIntegrityError("Candidate D publication pointer is invalid") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("artifact"), str):
        raise CandidateDIntegrityError("Candidate D publication pointer has the wrong shape")
    artifact = run_root / payload["artifact"]
    if artifact.parent.resolve() != run_root.resolve():
        raise CandidateDIntegrityError("Candidate D publication pointer escapes its run root")
    store = CandidateDStore.from_existing(artifact)
    if payload.get("publication_id") != store.publication_id():
        raise CandidateDIntegrityError("Candidate D pointer and artifact publication differ")
    return store


def copy_for_unsafe_change(
    *,
    current: CandidateDStore,
    run_root: Path,
    change: str,
) -> tuple[CandidateDStore, BuildStats]:
    destination = run_root / f"candidate-d-unsafe-{change}.sqlite"
    candidate, stats = current.apply_unsafe_change(destination, change=change)
    write_current_pointer(run_root, candidate)
    return candidate, stats


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0
