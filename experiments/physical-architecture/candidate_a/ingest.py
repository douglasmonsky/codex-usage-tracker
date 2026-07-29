from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import shared

from .schema import (
    PREPUBLICATION_VALIDATION,
    create_database,
    finalize_unpublished_database,
    validate_database,
)

_CONTROL_EVENT_KINDS = frozenset(
    {
        "allowance_compatibility",
        "late_parent",
        "oracle_case",
        "selector_anchor",
        "slice_control",
        "source_revision",
    }
)
_SELECTOR_PREFIXES = {
    "allowance_interval": "allowance-interval",
    "allowance_observation": "allowance-observation",
    "call": "call",
    "model_profile": "model-profile",
    "project": "project",
    "publication": "publication",
    "rate_card": "rate-card",
    "resource": "resource",
    "session": "session",
    "source_manifestation": "source-manifestation",
    "state_change": "state-change",
    "tool": "tool",
    "turn": "turn",
    "window": "window",
}


@cache
def _occurrence_source_key(
    *,
    manifestation_id: str,
    source_revision: str,
    adapter_version: str,
    source_path: str,
) -> int:
    digest = shared.canonical_sha256(
        {
            "adapter_version": adapter_version,
            "manifestation_id": manifestation_id,
            "source_path": source_path,
            "source_revision": source_revision,
        }
    )
    key = int(digest[:16], 16) & ((1 << 63) - 1)
    return key or 1


@dataclass(frozen=True)
class Coordinate:
    event_at_us: int
    source_rank: int
    occurrence_source_key: int
    source_order: int
    event_kind_order: int
    manifestation_id: str
    source_revision: str
    adapter_version: str
    source_path: str
    record_ordinal: int
    byte_start: int
    byte_end: int

    def values(self) -> tuple[int | str, ...]:
        return (
            self.event_at_us,
            self.source_rank,
            self.source_order,
            self.event_kind_order,
            self.manifestation_id,
            self.source_revision,
            self.adapter_version,
            self.source_path,
            self.record_ordinal,
            self.byte_start,
            self.byte_end,
        )

    def compact_values(self) -> tuple[int, ...]:
        return (
            self.event_at_us,
            self.source_rank,
            self.occurrence_source_key,
            self.source_order,
            self.event_kind_order,
            self.record_ordinal,
            self.byte_start,
            self.byte_end,
        )

    def oracle_coordinate(self) -> dict[str, object]:
        return {
            "adapter_version": self.adapter_version,
            "byte_end": self.byte_end,
            "byte_start": self.byte_start,
            "manifestation_id": self.manifestation_id,
            "record_ordinal": self.record_ordinal,
            "record_range": [self.record_ordinal, self.record_ordinal],
            "revision": self.source_revision,
            "source_path": self.source_path,
        }


@dataclass
class IngestStats:
    source_files_inventoried: int = 0
    source_files_selected: int = 0
    source_files_parsed: int = 0
    source_files_deferred: int = 0
    source_bytes_inventoried: int = 0
    source_bytes_selected: int = 0
    source_bytes_parsed: int = 0
    source_bytes_deferred: int = 0
    facts_inserted: int = 0
    facts_updated: int = 0
    facts_unchanged: int = 0
    occurrence_rows: int = 0
    diagnostic_rows: int = 0
    writer_transactions: int = 0
    secondary_indexes_deferred: int = 0
    secondary_indexes_restored: int = 0
    index_maintenance_ns: int = 0
    staging_journal_mode: str = ""
    staging_synchronous: int = 0
    final_journal_mode: str = ""
    final_synchronous: int = 0
    durability_transition_ns: int = 0
    validation_mode: str = ""
    validation_ns: int = 0


@dataclass(frozen=True)
class BuildArtifact:
    path: Path
    publication_id: str
    observed_through_us: int | None
    stats: IngestStats


def _drop_secondary_indexes(connection: sqlite3.Connection) -> tuple[str, ...]:
    rows = connection.execute(
        """
        SELECT name, sql
        FROM sqlite_schema
        WHERE type = 'index'
          AND sql IS NOT NULL
        ORDER BY name
        """
    ).fetchall()
    statements: list[str] = []
    for row in rows:
        name = str(row["name"])
        statement = str(row["sql"])
        if not name.replace("_", "").isalnum():
            raise ValueError(f"candidate A index name is not safely quoted: {name}")
        connection.execute(f'DROP INDEX "{name}"')
        statements.append(statement)
    return tuple(statements)


def _restore_secondary_indexes(
    connection: sqlite3.Connection,
    statements: tuple[str, ...],
) -> int:
    started = time.perf_counter_ns()
    for statement in statements:
        connection.execute(statement)
    return time.perf_counter_ns() - started


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _window(
    fixture: shared.FixtureBundle,
    history_selection: str,
) -> tuple[int, int, str | None]:
    history = fixture.manifest.get("history")
    if not isinstance(history, Mapping):
        raise ValueError("fixture history contract is missing")
    windows = history.get("windows")
    if not isinstance(windows, Mapping):
        raise ValueError("fixture history windows are missing")
    selected = windows.get(history_selection)
    if not isinstance(selected, Mapping):
        selected = windows.get("all_time")
    if not isinstance(selected, Mapping):
        raise ValueError("fixture all-time window is missing")
    return (
        int(selected["start_us"]),
        int(selected["end_us"]),
        str(selected["session_id"]) if selected.get("session_id") is not None else None,
    )


def _selected(
    record_type: str,
    payload: Mapping[str, Any],
    coordinate: Coordinate,
    *,
    start_us: int,
    end_us: int,
    selected_session_id: str | None,
) -> bool:
    if record_type in _CONTROL_EVENT_KINDS:
        return True
    if not start_us <= coordinate.event_at_us <= end_us:
        return False
    if selected_session_id is None:
        return True
    session_id = payload.get("session_id")
    return session_id is None or session_id == selected_session_id


def _source_entries(fixture: shared.FixtureBundle) -> list[dict[str, Any]]:
    entries = fixture.manifest.get("sources")
    if not isinstance(entries, tuple):
        raise ValueError("fixture source inventory is missing")
    result: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError("fixture source entry is invalid")
        result.append({str(key): _thaw(value) for key, value in entry.items()})
    return result


def _selected_sources(
    fixture: shared.FixtureBundle,
    *,
    history_selection: str,
    start_us: int,
    end_us: int,
) -> tuple[shared.SourceArtifact, ...]:
    entries = {
        str(entry["path"]): entry
        for entry in _source_entries(fixture)
    }
    selected: list[shared.SourceArtifact] = []
    for source in fixture.sources:
        source_path = source.relative_path.as_posix()
        entry = entries[source_path]
        persisted = bool(entry["persisted_when_requested"])
        explicitly_deferred = str(entry["history_selection"]) == "deferred"
        if not persisted or explicitly_deferred:
            continue
        if history_selection == "all_time":
            selected.append(source)
            continue
        if (
            source.time_range_confidence != "trusted"
            or source.time_range_hint is None
        ):
            selected.append(source)
            continue
        hint_start_us, hint_end_us = source.time_range_hint
        if hint_start_us <= end_us and hint_end_us > start_us:
            selected.append(source)
    return tuple(selected)


def _insert_manifestations(
    connection: sqlite3.Connection,
    fixture: shared.FixtureBundle,
    stats: IngestStats,
    *,
    selected_paths: frozenset[str],
) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for rank, source in enumerate(_source_entries(fixture)):
        source_path = str(source["path"])
        ranks[source_path] = rank
        deferred = source_path not in selected_paths
        stats.source_files_inventoried += 1
        stats.source_bytes_inventoried += int(source["bytes"])
        if deferred:
            stats.source_files_deferred += 1
            stats.source_bytes_deferred += int(source["bytes"])
        else:
            stats.source_files_selected += 1
            stats.source_bytes_selected += int(source["bytes"])
        connection.execute(
            """
            INSERT INTO source_manifestations(
                source_path, occurrence_source_key, manifestation_id, revision,
                adapter_version, source_rank, state, byte_count, record_count,
                content_sha256, logical_source, duplicate_of, selected
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_path,
                _occurrence_source_key(
                    manifestation_id=str(source["manifestation_id"]),
                    source_revision=str(source["revision"]),
                    adapter_version=str(source["adapter_version"]),
                    source_path=source_path,
                ),
                str(source["manifestation_id"]),
                str(source["revision"]),
                str(source["adapter_version"]),
                rank,
                str(source["state"]),
                int(source["bytes"]),
                int(source["records"]),
                str(source["content_sha256"]),
                str(source["logical_source"]),
                str(source["duplicate_of"]) if source["duplicate_of"] is not None else None,
                int(not deferred),
            ),
        )
    return ranks


def _record_coordinate(
    *,
    source: shared.SourceArtifact,
    source_rank: int,
    record: Mapping[str, Any],
    ordinal: int,
    byte_start: int,
    byte_end: int,
) -> Coordinate:
    return Coordinate(
        event_at_us=int(record["event_at_us"]),
        source_rank=source_rank,
        occurrence_source_key=_occurrence_source_key(
            manifestation_id=source.manifestation_id,
            source_revision=source.revision,
            adapter_version=source.adapter_version,
            source_path=source.relative_path.as_posix(),
        ),
        source_order=int(record["source_order"]),
        event_kind_order=int(record["event_kind_order"]),
        manifestation_id=source.manifestation_id,
        source_revision=source.revision,
        adapter_version=source.adapter_version,
        source_path=source.relative_path.as_posix(),
        record_ordinal=ordinal,
        byte_start=byte_start,
        byte_end=byte_end,
    )


def _selector(payload: Mapping[str, Any]) -> str:
    selector_kind = str(payload["selector_kind"])
    try:
        prefix = _SELECTOR_PREFIXES[selector_kind]
    except KeyError as error:
        raise ValueError(f"unknown selector kind: {selector_kind}") from error
    return f"{prefix}:{payload['logical_id']}"


def _observation_id(payload: Mapping[str, Any], coordinate: Coordinate) -> str:
    digest = shared.canonical_sha256(
        {
            "provider": payload["provider"],
            "limit_id": payload["limit_id"],
            "cycle_id": payload["cycle_id"],
            "reset_identity": payload["reset_identity"],
            "observation_ordinal": payload["observation_ordinal"],
            "event_at_us": coordinate.event_at_us,
            "manifestation_id": coordinate.manifestation_id,
            "record_ordinal": coordinate.record_ordinal,
        }
    )
    return f"allowance-observation:observed:{digest}"


def _question_expected(
    fixture: shared.FixtureBundle,
    oracle_id: str,
    coordinate: Coordinate,
) -> tuple[str, str, str]:
    questions = fixture.oracle.get("questions")
    if not isinstance(questions, Mapping):
        raise ValueError("fixture question oracle is missing")
    question = questions.get(oracle_id)
    if not isinstance(question, Mapping):
        raise ValueError(f"fixture question oracle is missing {oracle_id}")
    expected = question.get("expected")
    if not isinstance(expected, Mapping):
        raise ValueError(f"fixture expected result is missing {oracle_id}")
    expected_row = _thaw(expected.get("row"))
    if isinstance(expected_row, dict) and "occurrence_coordinates" in expected_row:
        expected_row["occurrence_coordinates"] = [coordinate.oracle_coordinate()]
    return (
        str(question["question_id"]),
        str(question["variant"]),
        shared.canonical_sha256(expected_row),
    )


def _insert_record(
    connection: sqlite3.Connection,
    fixture: shared.FixtureBundle,
    record_type: str,
    payload: Mapping[str, Any],
    coordinate: Coordinate,
) -> tuple[int, int]:
    inserted = 0
    updated = 0
    if record_type == "selector_anchor":
        inserted += connection.execute(
            """
            INSERT OR IGNORE INTO selector_anchors(
                selector, selector_kind, logical_id, event_at_us, source_rank,
                source_order, event_kind_order, manifestation_id,
                source_revision, adapter_version, source_path, record_ordinal,
                byte_start, byte_end
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _selector(payload),
                str(payload["selector_kind"]),
                str(payload["logical_id"]),
                *coordinate.values(),
            ),
        ).rowcount
    elif record_type == "session_start":
        inserted += connection.execute(
            """
            INSERT OR IGNORE INTO sessions(
                session_id, project_id, parent_session_id, state,
                start_at_us, start_source_rank, start_source_order,
                start_event_kind_order, start_manifestation_id,
                start_source_revision, start_adapter_version, start_source_path,
                start_record_ordinal, start_byte_start, start_byte_end
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(payload["session_id"]),
                str(payload["project_id"]) if payload.get("project_id") is not None else None,
                (
                    str(payload["parent_session_id"])
                    if payload.get("parent_session_id") is not None
                    else None
                ),
                str(payload["state"]),
                *coordinate.values(),
            ),
        ).rowcount
    elif record_type == "session_terminal":
        updated += connection.execute(
            """
            UPDATE sessions SET
                state=?, terminal_at_us=?, terminal_source_rank=?,
                terminal_source_order=?, terminal_event_kind_order=?,
                terminal_manifestation_id=?, terminal_source_revision=?,
                terminal_adapter_version=?, terminal_source_path=?,
                terminal_record_ordinal=?, terminal_byte_start=?,
                terminal_byte_end=?, completion_basis=?
            WHERE session_id=?
            """,
            (
                str(payload["state"]),
                *coordinate.values(),
                str(payload["completion_basis"]),
                str(payload["session_id"]),
            ),
        ).rowcount
    elif record_type == "turn_start":
        inserted += connection.execute(
            """
            INSERT OR IGNORE INTO turns(
                turn_id, session_id, state, start_at_us, source_rank,
                occurrence_source_key, source_order, event_kind_order,
                record_ordinal, byte_start, byte_end
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(payload["turn_id"]),
                str(payload["session_id"]),
                str(payload["state"]),
                *coordinate.compact_values(),
            ),
        ).rowcount
    elif record_type == "model_call":
        tokens = payload["tokens"]
        inserted += connection.execute(
            """
            INSERT OR IGNORE INTO model_calls(
                call_id, session_id, turn_id, model, reasoning_effort,
                context_window_tokens, uncached_input_tokens,
                cached_input_tokens, reasoning_tokens, output_tokens,
                event_at_us, source_rank, occurrence_source_key, source_order,
                event_kind_order, record_ordinal, byte_start, byte_end
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(payload["call_id"]),
                str(payload["session_id"]),
                str(payload["turn_id"]),
                str(payload["model"]),
                (
                    str(payload["reasoning_effort"])
                    if payload.get("reasoning_effort") is not None
                    else None
                ),
                (
                    int(payload["context_window_tokens"])
                    if payload.get("context_window_tokens") is not None
                    else None
                ),
                (
                    int(tokens["uncached_input_tokens"])
                    if tokens.get("uncached_input_tokens") is not None
                    else None
                ),
                (
                    int(tokens["cached_input_tokens"])
                    if tokens.get("cached_input_tokens") is not None
                    else None
                ),
                (
                    int(tokens["reasoning_tokens"])
                    if tokens.get("reasoning_tokens") is not None
                    else None
                ),
                (
                    int(tokens["output_tokens"])
                    if tokens.get("output_tokens") is not None
                    else None
                ),
                *coordinate.compact_values(),
            ),
        ).rowcount
    elif record_type == "tool_start":
        inserted += connection.execute(
            """
            INSERT OR IGNORE INTO tool_invocations(
                tool_id, session_id, turn_id, transport_name,
                semantic_operation, resource_id, write_intent, state,
                start_at_us, start_source_rank, start_occurrence_source_key,
                start_source_order, start_event_kind_order,
                start_record_ordinal, start_byte_start, start_byte_end
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(payload["tool_id"]),
                str(payload["session_id"]),
                str(payload["turn_id"]),
                str(payload["transport_name"]),
                str(payload["semantic_operation"]),
                str(payload["resource_id"]) if payload.get("resource_id") is not None else None,
                int(bool(payload["write_intent"])),
                str(payload["state"]),
                *coordinate.compact_values(),
            ),
        ).rowcount
    elif record_type == "tool_terminal":
        updated += connection.execute(
            """
            UPDATE tool_invocations SET
                transport_name=?, semantic_operation=?, resource_id=?,
                write_intent=?, state=?, terminal_at_us=?,
                terminal_source_rank=?, terminal_occurrence_source_key=?,
                terminal_source_order=?, terminal_event_kind_order=?,
                terminal_record_ordinal=?,
                terminal_byte_start=?, terminal_byte_end=?, duration_us=?,
                output_bytes=?
            WHERE tool_id=?
            """,
            (
                str(payload["transport_name"]),
                str(payload["semantic_operation"]),
                str(payload["resource_id"]) if payload.get("resource_id") is not None else None,
                int(bool(payload["write_intent"])),
                str(payload["state"]),
                *coordinate.compact_values(),
                int(payload["duration_us"]) if payload.get("duration_us") is not None else None,
                int(payload["output_bytes"]) if payload.get("output_bytes") is not None else None,
                str(payload["tool_id"]),
            ),
        ).rowcount
    elif record_type == "activity":
        inserted += connection.execute(
            """
            INSERT OR IGNORE INTO activities(
                activity_id, session_id, turn_id, activity_kind, state,
                event_at_us, source_rank, source_order, event_kind_order,
                manifestation_id, source_revision, adapter_version, source_path,
                record_ordinal, byte_start, byte_end
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(payload["activity_id"]),
                str(payload["session_id"]),
                str(payload["turn_id"]) if payload.get("turn_id") is not None else None,
                str(payload["activity_kind"]),
                str(payload["state"]),
                *coordinate.values(),
            ),
        ).rowcount
    elif record_type == "state_change":
        inserted += connection.execute(
            """
            INSERT OR IGNORE INTO state_changes(
                change_id, session_id, turn_id, resource_id, change_kind,
                preceding_activity_count, causal_attribution, event_at_us,
                source_rank, source_order, event_kind_order, manifestation_id,
                source_revision, adapter_version, source_path, record_ordinal,
                byte_start, byte_end
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(payload["change_id"]),
                str(payload["session_id"]),
                str(payload["turn_id"]) if payload.get("turn_id") is not None else None,
                str(payload["resource_id"]),
                str(payload["change_kind"]),
                int(payload["preceding_activity_count"]),
                (
                    str(payload["causal_attribution"])
                    if payload.get("causal_attribution") is not None
                    else None
                ),
                *coordinate.values(),
            ),
        ).rowcount
    elif record_type == "compaction_boundary":
        inserted += connection.execute(
            """
            INSERT OR IGNORE INTO compaction_boundaries(
                compaction_id, session_id, before_context_epoch,
                after_context_epoch, event_at_us, source_rank, source_order,
                event_kind_order, manifestation_id, source_revision,
                adapter_version, source_path, record_ordinal, byte_start,
                byte_end
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(payload["compaction_id"]),
                str(payload["session_id"]),
                str(payload["before_context_epoch"]),
                str(payload["after_context_epoch"]),
                *coordinate.values(),
            ),
        ).rowcount
    elif record_type == "allowance_observation":
        observation_id = _observation_id(payload, coordinate)
        inserted += connection.execute(
            """
            INSERT OR IGNORE INTO allowance_observations(
                observation_id, provider, limit_id, cycle_id, plan_identity,
                window_kind, reset_identity, observation_ordinal, used_percent,
                remaining_percent, event_at_us, source_rank, source_order,
                event_kind_order, manifestation_id, source_revision,
                adapter_version, source_path, record_ordinal, byte_start,
                byte_end
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation_id,
                str(payload["provider"]),
                str(payload["limit_id"]),
                str(payload["cycle_id"]),
                str(payload["plan_identity"]),
                str(payload["window_kind"]),
                str(payload["reset_identity"]),
                int(payload["observation_ordinal"]),
                str(payload["used_percent"]) if payload.get("used_percent") is not None else None,
                (
                    str(payload["remaining_percent"])
                    if payload.get("remaining_percent") is not None
                    else None
                ),
                *coordinate.values(),
            ),
        ).rowcount
    elif record_type == "allowance_compatibility":
        compatibility = payload["compatibility_tuple"]
        compatibility_id = (
            "allowance-compatibility:"
            + shared.canonical_sha256(
                {
                    "start": payload["start_observation_id"],
                    "end": payload["end_observation_id"],
                    "tuple": _thaw(compatibility),
                }
            )
        )
        inserted += connection.execute(
            """
            INSERT OR IGNORE INTO allowance_compatibility(
                compatibility_id, start_observation_id, end_observation_id,
                provider, limit_id, cycle_id, plan_identity, window_kind,
                reset_identity, event_at_us, source_rank, source_order,
                event_kind_order, manifestation_id, source_revision,
                adapter_version, source_path, record_ordinal, byte_start,
                byte_end
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                compatibility_id,
                str(payload["start_observation_id"]),
                str(payload["end_observation_id"]),
                str(compatibility["provider"]),
                str(compatibility["limit_id"]),
                str(compatibility["cycle_id"]),
                str(compatibility["plan_identity"]),
                str(compatibility["window_kind"]),
                str(compatibility["reset_identity"]),
                *coordinate.values(),
            ),
        ).rowcount
    elif record_type == "late_parent":
        inserted += connection.execute(
            """
            INSERT OR IGNORE INTO late_parent_edges(
                child_session_id, parent_session_id, transition, event_at_us,
                source_rank, source_order, event_kind_order, manifestation_id,
                source_revision, adapter_version, source_path, record_ordinal,
                byte_start, byte_end
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(payload["child_session_id"]),
                str(payload["parent_session_id"]),
                str(payload["transition"]),
                *coordinate.values(),
            ),
        ).rowcount
        updated += connection.execute(
            "UPDATE sessions SET parent_session_id=? WHERE session_id=?",
            (str(payload["parent_session_id"]), str(payload["child_session_id"])),
        ).rowcount
    elif record_type == "oracle_case":
        oracle_id = str(payload["oracle_id"])
        question_id, variant, expected_digest = _question_expected(
            fixture,
            oracle_id,
            coordinate,
        )
        observed = _thaw(payload["observed_facts"])
        if isinstance(observed, dict) and "occurrence_coordinates" in observed:
            observed["occurrence_coordinates"] = [coordinate.oracle_coordinate()]
        if shared.canonical_sha256(observed) != expected_digest:
            raise ValueError(f"candidate A source/oracle mismatch: {oracle_id}")
        inserted += connection.execute(
            """
            INSERT OR IGNORE INTO question_cases(
                oracle_id, question_id, variant, expected_digest, event_at_us,
                source_rank, source_order, event_kind_order, manifestation_id,
                source_revision, adapter_version, source_path, record_ordinal,
                byte_start, byte_end
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (oracle_id, question_id, variant, expected_digest, *coordinate.values()),
        ).rowcount
    return inserted, updated


def _refresh_projections(
    connection: sqlite3.Connection,
    hook: Callable[[str], None] | None,
) -> int:
    connection.execute("DELETE FROM session_usage_current")
    if hook is not None:
        hook("during_projection_update")
    connection.execute(
        """
        INSERT INTO session_usage_current(
            session_id, calls, uncached_input_tokens, cached_input_tokens,
            reasoning_tokens, output_tokens
        )
        SELECT
            session_id,
            count(*),
            coalesce(sum(uncached_input_tokens), 0),
            coalesce(sum(cached_input_tokens), 0),
            coalesce(sum(reasoning_tokens), 0),
            coalesce(sum(output_tokens), 0)
        FROM model_calls
        GROUP BY session_id
        """
    )
    connection.execute("DELETE FROM tool_family_current")
    connection.execute(
        """
        INSERT INTO tool_family_current(
            transport_name, semantic_operation, calls, failures,
            duration_us, output_bytes
        )
        SELECT
            transport_name,
            semantic_operation,
            count(*),
            sum(CASE WHEN state = 'failed' THEN 1 ELSE 0 END),
            sum(duration_us),
            sum(output_bytes)
        FROM tool_invocations
        GROUP BY transport_name, semantic_operation
        """
    )
    return int(
        connection.execute(
            """
            SELECT
                (SELECT count(*) FROM session_usage_current) +
                (SELECT count(*) FROM tool_family_current)
            """
        ).fetchone()[0]
    )


def _publication_id(
    fixture: shared.FixtureBundle,
    history_selection: str,
    parent_publication_id: str | None,
) -> str:
    digest = shared.canonical_sha256(
        {
            "candidate": "A",
            "fixture": fixture.manifest_digest,
            "history_selection": history_selection,
            "parent_publication_id": parent_publication_id,
        }
    )
    return f"publication:candidate-a:{digest}"


def build_artifact(
    fixture: shared.FixtureBundle,
    path: Path,
    *,
    history_selection: str = "all_time",
    parent_publication_id: str | None = None,
    hook: Callable[[str], None] | None = None,
    defer_secondary_indexes: bool = True,
) -> BuildArtifact:
    connection = create_database(path, unpublished_staging=True)
    stats = IngestStats()
    stats.staging_journal_mode = str(
        connection.execute("PRAGMA journal_mode").fetchone()[0]
    )
    stats.staging_synchronous = int(
        connection.execute("PRAGMA synchronous").fetchone()[0]
    )
    try:
        if defer_secondary_indexes:
            index_drop_started = time.perf_counter_ns()
            deferred_index_sql = _drop_secondary_indexes(connection)
            stats.index_maintenance_ns += (
                time.perf_counter_ns() - index_drop_started
            )
            stats.secondary_indexes_deferred = len(deferred_index_sql)
        else:
            deferred_index_sql = ()
        start_us, end_us, selected_session_id = _window(fixture, history_selection)
        selected_sources = _selected_sources(
            fixture,
            history_selection=history_selection,
            start_us=start_us,
            end_us=end_us,
        )
        selected_paths = frozenset(
            source.relative_path.as_posix()
            for source in selected_sources
        )
        connection.execute("BEGIN IMMEDIATE")
        ranks = _insert_manifestations(
            connection,
            fixture,
            stats,
            selected_paths=selected_paths,
        )
        parse_hook_called = False
        fact_hook_called = False
        for source in selected_sources:
            source_path = source.relative_path.as_posix()
            stats.source_files_parsed += 1
            stats.source_bytes_parsed += source.byte_count
            body = source.absolute_path.read_bytes()
            byte_start = 0
            for ordinal, line in enumerate(body.splitlines(keepends=True)):
                byte_end = byte_start + len(line)
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    connection.execute(
                        """
                        INSERT INTO source_diagnostics(
                            source_path, record_ordinal, byte_start, byte_end,
                            diagnostic_code
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            source_path,
                            ordinal,
                            byte_start,
                            byte_end,
                            "malformed_json",
                        ),
                    )
                    stats.diagnostic_rows += 1
                    byte_start = byte_end
                    continue
                if not isinstance(record, dict) or not isinstance(record.get("payload"), dict):
                    raise ValueError(f"candidate A source record is invalid: {source_path}")
                coordinate = _record_coordinate(
                    source=source,
                    source_rank=ranks[source_path],
                    record=record,
                    ordinal=ordinal,
                    byte_start=byte_start,
                    byte_end=byte_end,
                )
                if hook is not None and not parse_hook_called:
                    parse_hook_called = True
                    hook("during_parse")
                stats.occurrence_rows += 1
                payload = record["payload"]
                record_type = str(record["type"])
                canonical = source.state != "archived"
                if canonical and _selected(
                    record_type,
                    payload,
                    coordinate,
                    start_us=start_us,
                    end_us=end_us,
                    selected_session_id=selected_session_id,
                ):
                    inserted, updated = _insert_record(
                        connection,
                        fixture,
                        record_type,
                        payload,
                        coordinate,
                    )
                    if hook is not None and not fact_hook_called and (inserted or updated):
                        fact_hook_called = True
                        hook("during_fact_writes")
                    stats.facts_inserted += inserted
                    stats.facts_updated += updated
                    if inserted == 0 and updated == 0:
                        stats.facts_unchanged += 1
                byte_start = byte_end
        if hook is not None:
            hook("after_facts_before_projections")
        projection_rows = _refresh_projections(connection, hook)
        if deferred_index_sql:
            stats.index_maintenance_ns += _restore_secondary_indexes(
                connection,
                deferred_index_sql,
            )
            stats.secondary_indexes_restored = len(deferred_index_sql)
        publication_id = _publication_id(
            fixture,
            history_selection,
            parent_publication_id,
        )
        observed_through = connection.execute(
            "SELECT max(event_at_us) FROM model_calls"
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO publications(
                publication_id, parent_publication_id,
                fixture_manifest_digest, fixture_oracle_digest,
                committed_at_us, observed_through_us, status
            ) VALUES (?, ?, ?, ?, ?, ?, 'committed')
            """,
            (
                publication_id,
                parent_publication_id,
                fixture.manifest_digest,
                fixture.oracle_digest,
                end_us,
                observed_through,
            ),
        )
        connection.executemany(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
            (
                ("fixture_revision", fixture.fixture_revision),
                ("fixture_profile", fixture.profile),
                ("fixture_manifest_digest", fixture.manifest_digest),
                ("fixture_oracle_digest", fixture.oracle_digest),
                ("history_selection", history_selection),
                ("projection_rows", str(projection_rows)),
                (
                    "prepublication_validation",
                    PREPUBLICATION_VALIDATION,
                ),
                ("raw_content_stored", "false"),
            ),
        )
        connection.commit()
        stats.writer_transactions += 1
        connection.execute("PRAGMA optimize")
        durability_started = time.perf_counter_ns()
        finalize_unpublished_database(connection)
        stats.durability_transition_ns = (
            time.perf_counter_ns() - durability_started
        )
        stats.final_journal_mode = str(
            connection.execute("PRAGMA journal_mode").fetchone()[0]
        )
        stats.final_synchronous = int(
            connection.execute("PRAGMA synchronous").fetchone()[0]
        )
        stats.validation_mode = "prepublication"
        validation_started = time.perf_counter_ns()
        validate_database(connection, mode="prepublication")
        stats.validation_ns = time.perf_counter_ns() - validation_started
        return BuildArtifact(
            path=path,
            publication_id=publication_id,
            observed_through_us=int(observed_through) if observed_through is not None else None,
            stats=stats,
        )
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
