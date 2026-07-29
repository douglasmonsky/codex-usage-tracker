from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import shared

from .schema import MODEL_CALL_TAIL_MAX_ROWS, open_database


@dataclass(frozen=True)
class MaintenanceStats:
    facts_inserted: int = 0
    facts_updated: int = 0
    facts_recanonicalized: int = 0
    facts_unchanged: int = 0
    dirty_keys: int = 0
    projection_rows_read: int = 0
    projection_rows_written: int = 0
    ordinary_tail_latency_ns: int = 0
    pages_written: int = 0
    writer_transactions: int = 0
    source_files_rescanned: int = 0
    source_bytes_rescanned: int = 0


class TailFoldRequired(RuntimeError):
    def __init__(self, *, current_rows: int, requested_rows: int) -> None:
        self.current_rows = current_rows
        self.requested_rows = requested_rows
        self.maximum_rows = MODEL_CALL_TAIL_MAX_ROWS
        super().__init__(
            "candidate A model-call tail would exceed "
            f"{self.maximum_rows} rows "
            f"({self.current_rows} current + {self.requested_rows} requested); "
            "isolated artifact fold required"
        )


@dataclass(frozen=True)
class _UsageDelta:
    session_id: str
    model: str
    reasoning_effort: str | None
    calls: int
    uncached_input_tokens: int
    cached_input_tokens: int
    reasoning_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class _ToolStartDelta:
    transport_name: str
    semantic_operation: str
    turn_id: str
    resource_id: str
    start_at_us: int
    mutation_at_us: int | None


@dataclass(frozen=True)
class _ToolTerminalDelta:
    transport_name: str
    semantic_operation: str
    turn_id: str
    terminal_at_us: int
    duration_us: int
    output_bytes: int


def _tail_identity(connection: sqlite3.Connection) -> tuple[str, str, sqlite3.Row]:
    call = connection.execute(
        """
        WITH latest_base AS (
            SELECT
                session_id, turn_id, event_at_us, source_rank,
                source_order, event_kind_order, call_id
            FROM model_calls INDEXED BY model_calls_timeline
            ORDER BY
                event_at_us DESC, source_rank DESC, source_order DESC,
                event_kind_order DESC, call_id DESC
            LIMIT 1
        ),
        latest_tail AS (
            SELECT
                session_id, turn_id, event_at_us, source_rank,
                source_order, event_kind_order, call_id
            FROM model_call_tail INDEXED BY model_call_tail_timeline
            ORDER BY
                event_at_us DESC, source_rank DESC, source_order DESC,
                event_kind_order DESC, call_id DESC
            LIMIT 1
        )
        SELECT session_id, turn_id
        FROM (
            SELECT * FROM latest_base
            UNION ALL
            SELECT * FROM latest_tail
        )
        ORDER BY
            event_at_us DESC, source_rank DESC, source_order DESC,
            event_kind_order DESC, call_id DESC
        LIMIT 1
        """
    ).fetchone()
    source = connection.execute(
        """
        SELECT *
        FROM source_manifestations
        WHERE selected=1 AND state='active'
        ORDER BY source_rank, source_path
        LIMIT 1
        """
    ).fetchone()
    if call is None or source is None:
        raise ValueError("candidate A tail requires one canonical call and source")
    return str(call["session_id"]), str(call["turn_id"]), source


def _refresh_session(
    connection: sqlite3.Connection,
    delta: _UsageDelta,
) -> tuple[int, int]:
    connection.execute(
        """
        INSERT INTO session_usage_current(
            session_id, calls, uncached_input_tokens, cached_input_tokens,
            reasoning_tokens, output_tokens
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            calls=calls + excluded.calls,
            uncached_input_tokens=uncached_input_tokens
                + excluded.uncached_input_tokens,
            cached_input_tokens=cached_input_tokens
                + excluded.cached_input_tokens,
            reasoning_tokens=reasoning_tokens + excluded.reasoning_tokens,
            output_tokens=output_tokens + excluded.output_tokens
        """,
        (
            delta.session_id,
            delta.calls,
            delta.uncached_input_tokens,
            delta.cached_input_tokens,
            delta.reasoning_tokens,
            delta.output_tokens,
        ),
    )
    return 1, 1


def _root_session_id(connection: sqlite3.Connection, session_id: str) -> str:
    row = connection.execute(
        """
        WITH RECURSIVE ancestor(session_id, parent_session_id) AS (
            SELECT session_id, parent_session_id
            FROM sessions
            WHERE session_id = ?
            UNION ALL
            SELECT parent.session_id, parent.parent_session_id
            FROM sessions AS parent
            JOIN ancestor ON parent.session_id = ancestor.parent_session_id
        )
        SELECT session_id
        FROM ancestor
        WHERE parent_session_id IS NULL
        LIMIT 1
        """,
        (session_id,),
    ).fetchone()
    if row is None:
        raise ValueError("candidate A session has no rooted project family")
    return str(row["session_id"])


def _increment_call_projections(
    connection: sqlite3.Connection,
    delta: _UsageDelta,
) -> tuple[int, int]:
    reads, writes = _refresh_session(connection, delta)
    values = (
        delta.calls,
        delta.uncached_input_tokens,
        delta.cached_input_tokens,
        delta.reasoning_tokens,
        delta.output_tokens,
    )
    connection.execute(
        """
        INSERT INTO usage_total_current(
            singleton, calls, uncached_input_tokens, cached_input_tokens,
            reasoning_tokens, output_tokens
        ) VALUES (1, ?, ?, ?, ?, ?)
        ON CONFLICT(singleton) DO UPDATE SET
            calls=calls + excluded.calls,
            uncached_input_tokens=uncached_input_tokens
                + excluded.uncached_input_tokens,
            cached_input_tokens=cached_input_tokens
                + excluded.cached_input_tokens,
            reasoning_tokens=reasoning_tokens + excluded.reasoning_tokens,
            output_tokens=output_tokens + excluded.output_tokens
        """,
        values,
    )
    connection.execute(
        """
        INSERT INTO model_effort_usage_current(
            model, reasoning_effort_is_null, reasoning_effort_value,
            calls, uncached_input_tokens, cached_input_tokens,
            reasoning_tokens, output_tokens
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(
            model, reasoning_effort_is_null, reasoning_effort_value
        ) DO UPDATE SET
            calls=calls + excluded.calls,
            uncached_input_tokens=uncached_input_tokens
                + excluded.uncached_input_tokens,
            cached_input_tokens=cached_input_tokens
                + excluded.cached_input_tokens,
            reasoning_tokens=reasoning_tokens + excluded.reasoning_tokens,
            output_tokens=output_tokens + excluded.output_tokens
        """,
        (
            delta.model,
            int(delta.reasoning_effort is None),
            delta.reasoning_effort or "",
            *values,
        ),
    )
    connection.execute(
        """
        INSERT INTO model_usage_current(model, calls, rated_calls)
        VALUES (?, ?, ?)
        ON CONFLICT(model) DO UPDATE SET
            calls=calls + excluded.calls,
            rated_calls=rated_calls + excluded.rated_calls
        """,
        (
            delta.model,
            delta.calls,
            0 if delta.model == "synthetic-unpriced" else delta.calls,
        ),
    )
    connection.execute(
        """
        INSERT INTO project_family_usage_current(
            root_session_id, calls, uncached_input_tokens,
            cached_input_tokens, reasoning_tokens, output_tokens
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(root_session_id) DO UPDATE SET
            calls=calls + excluded.calls,
            uncached_input_tokens=uncached_input_tokens
                + excluded.uncached_input_tokens,
            cached_input_tokens=cached_input_tokens
                + excluded.cached_input_tokens,
            reasoning_tokens=reasoning_tokens + excluded.reasoning_tokens,
            output_tokens=output_tokens + excluded.output_tokens
        """,
        (_root_session_id(connection, delta.session_id), *values),
    )
    return reads + 4, writes + 4


def _increment_turn_action_start(
    connection: sqlite3.Connection,
    delta: _ToolStartDelta,
) -> tuple[int, int]:
    updated = connection.execute(
        """
        UPDATE turn_action_current
        SET
            first_action_at_us = CASE
                WHEN first_action_at_us IS NULL THEN ?
                ELSE min(first_action_at_us, ?)
            END,
            first_mutation_at_us = CASE
                WHEN ? IS NULL THEN first_mutation_at_us
                WHEN first_mutation_at_us IS NULL THEN ?
                ELSE min(first_mutation_at_us, ?)
            END
        WHERE turn_id = ?
        """,
        (
            delta.start_at_us,
            delta.start_at_us,
            delta.mutation_at_us,
            delta.mutation_at_us,
            delta.mutation_at_us,
            delta.turn_id,
        ),
    ).rowcount
    if updated != 1:
        raise ValueError("candidate A tool start has no current turn projection")
    return 1, 1


def _increment_turn_action_terminal(
    connection: sqlite3.Connection,
    delta: _ToolTerminalDelta,
) -> tuple[int, int]:
    updated = connection.execute(
        """
        UPDATE turn_action_current
        SET first_success_at_us = CASE
            WHEN first_success_at_us IS NULL THEN ?
            ELSE min(first_success_at_us, ?)
        END
        WHERE turn_id = ?
        """,
        (delta.terminal_at_us, delta.terminal_at_us, delta.turn_id),
    ).rowcount
    if updated != 1:
        raise ValueError("candidate A tool terminal has no current turn projection")
    return 1, 1


def _refresh_resource_operation(
    connection: sqlite3.Connection,
    resource_id: str,
) -> tuple[int, int]:
    connection.execute(
        """
        INSERT INTO resource_operation_current(
            resource_id, operation_count, first_at_us, last_at_us
        )
        SELECT resource_id, count(*), min(start_at_us), max(start_at_us)
        FROM tool_invocations
        WHERE resource_id = ?
        GROUP BY resource_id
        ON CONFLICT(resource_id) DO UPDATE SET
            operation_count=excluded.operation_count,
            first_at_us=excluded.first_at_us,
            last_at_us=excluded.last_at_us
        """,
        (resource_id,),
    )
    return 1, 1


def _invalidate_evidence_anchors(connection: sqlite3.Connection) -> tuple[int, int]:
    connection.execute(
        """
        INSERT OR REPLACE INTO metadata(key, value)
        VALUES ('evidence_anchors_valid', 'false')
        """
    )
    return 1, 1


def _increment_tool_family_start(
    connection: sqlite3.Connection,
    delta: _ToolStartDelta,
) -> tuple[int, int]:
    connection.execute(
        """
        INSERT INTO tool_family_current(
            transport_name, semantic_operation, calls, failures,
            duration_us, output_bytes
        )
        VALUES (?, ?, 1, 0, NULL, NULL)
        ON CONFLICT(transport_name, semantic_operation) DO UPDATE SET
            calls=tool_family_current.calls + 1
        """,
        (delta.transport_name, delta.semantic_operation),
    )
    return 1, 1


def _increment_tool_family_terminal(
    connection: sqlite3.Connection,
    delta: _ToolTerminalDelta,
) -> tuple[int, int]:
    updated = connection.execute(
        """
        UPDATE tool_family_current
        SET
            duration_us=coalesce(duration_us, 0) + ?,
            output_bytes=coalesce(output_bytes, 0) + ?
        WHERE transport_name=? AND semantic_operation=?
        """,
        (
            delta.duration_us,
            delta.output_bytes,
            delta.transport_name,
            delta.semantic_operation,
        ),
    ).rowcount
    if updated != 1:
        raise ValueError("candidate A tool terminal has no current family projection")
    return 1, 1


def _insert_calls(
    connection: sqlite3.Connection,
    *,
    count: int,
    late: bool = False,
) -> tuple[int, _UsageDelta]:
    session_id, turn_id, source = _tail_identity(connection)
    tail_state = connection.execute(
        """
        SELECT
            row_count, minimum_event_at_us,
            maximum_event_at_us, maximum_source_order
        FROM model_call_tail_state
        WHERE singleton = 1
        """
    ).fetchone()
    if tail_state is None or tail_state["maximum_event_at_us"] is None:
        raise ValueError("candidate A model-call tail cursor is unavailable")
    tail_rows = int(tail_state["row_count"])
    if tail_state["maximum_source_order"] is None:
        raise ValueError("candidate A model-call source-order cursor is unavailable")
    if tail_state["minimum_event_at_us"] is None:
        raise ValueError("candidate A model-call minimum cursor is unavailable")
    if tail_rows + count > MODEL_CALL_TAIL_MAX_ROWS:
        raise TailFoldRequired(current_rows=tail_rows, requested_rows=count)
    if late:
        event_at = int(tail_state["minimum_event_at_us"]) - 1
    else:
        event_at = int(tail_state["maximum_event_at_us"]) + 1
    source_order = int(tail_state["maximum_source_order"]) + 1
    rows = []
    for ordinal in range(count):
        digest = shared.canonical_sha256(
            {
                "candidate": "A",
                "change": "late" if late else "tail",
                "session": session_id,
                "ordinal": ordinal,
                "event_at_us": event_at + ordinal,
            }
        )
        rows.append(
            (
                f"call:candidate-a:{digest}",
                session_id,
                turn_id,
                "synthetic-tail-model",
                "medium",
                128_000,
                100 + ordinal % 17,
                1_000 + ordinal % 31,
                25 + ordinal % 7,
                50 + ordinal % 11,
                event_at + ordinal,
                int(source["source_rank"]),
                int(source["occurrence_source_key"]),
                source_order + ordinal,
                30,
                int(source["record_count"]) + ordinal,
                int(source["byte_count"]),
                int(source["byte_count"]),
            )
        )
    row_placeholders = "(" + ", ".join("?" for _ in rows[0]) + ")"
    connection.execute(
        f"""
        INSERT INTO model_call_tail(
            call_id, session_id, turn_id, model, reasoning_effort,
            context_window_tokens, uncached_input_tokens, cached_input_tokens,
            reasoning_tokens, output_tokens, event_at_us, source_rank,
            occurrence_source_key, source_order, event_kind_order,
            record_ordinal, byte_start, byte_end
        ) VALUES {", ".join(row_placeholders for _ in rows)}
        """,
        tuple(value for row in rows for value in row),
    )
    return (
        len(rows),
        _UsageDelta(
            session_id=session_id,
            model="synthetic-tail-model",
            reasoning_effort="medium",
            calls=len(rows),
            uncached_input_tokens=sum(int(row[6]) for row in rows),
            cached_input_tokens=sum(int(row[7]) for row in rows),
            reasoning_tokens=sum(int(row[8]) for row in rows),
            output_tokens=sum(int(row[9]) for row in rows),
        ),
    )


def _insert_tool(
    connection: sqlite3.Connection,
    *,
    include_state_change: bool,
) -> tuple[int, int, _ToolStartDelta]:
    session_id, turn_id, source = _tail_identity(connection)
    event_at = (
        int(
            connection.execute(
                """
            SELECT max(value) FROM (
                SELECT maximum_event_at_us AS value
                FROM model_call_tail_state
                WHERE singleton=1
                UNION ALL SELECT max(start_at_us) FROM tool_invocations
                UNION ALL SELECT max(event_at_us) FROM state_changes
            )
            """
            ).fetchone()[0]
        )
        + 1
    )
    digest = shared.canonical_sha256({"candidate": "A", "change": "tool", "event_at_us": event_at})
    tool_id = f"tool:candidate-a:{digest}"
    resource_id = f"resource:candidate-a:{digest}"
    connection.execute(
        """
        INSERT INTO tool_invocations(
            tool_id, session_id, turn_id, transport_name,
            semantic_operation, resource_id, write_intent, state,
            start_at_us, start_source_rank, start_occurrence_source_key,
            start_source_order, start_event_kind_order,
            start_record_ordinal, start_byte_start, start_byte_end
        ) VALUES (?, ?, ?, 'synthetic_write', 'write', ?, 1, 'running',
                  ?, ?, ?, ?, 40, ?, ?, ?)
        """,
        (
            tool_id,
            session_id,
            turn_id,
            resource_id,
            event_at,
            int(source["source_rank"]),
            int(source["occurrence_source_key"]),
            int(source["record_count"]) + 1,
            int(source["record_count"]) + 1,
            int(source["byte_count"]),
            int(source["byte_count"]),
        ),
    )
    inserted = 1
    if include_state_change:
        change_id = f"state-change:candidate-a:{digest}"
        connection.execute(
            """
            INSERT INTO state_changes(
                change_id, session_id, turn_id, resource_id, change_kind,
                preceding_activity_count, causal_attribution, event_at_us,
                source_rank, source_order, event_kind_order, manifestation_id,
                source_revision, adapter_version, source_path, record_ordinal,
                byte_start, byte_end
            ) VALUES (?, ?, ?, ?, 'content_revision', 2, NULL, ?, ?, ?, 60,
                      ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                change_id,
                session_id,
                turn_id,
                resource_id,
                event_at + 1,
                int(source["source_rank"]),
                int(source["record_count"]) + 2,
                str(source["manifestation_id"]),
                str(source["revision"]),
                str(source["adapter_version"]),
                str(source["source_path"]),
                int(source["record_count"]) + 2,
                int(source["byte_count"]),
                int(source["byte_count"]),
            ),
        )
        inserted += 1
    return (
        inserted,
        0,
        _ToolStartDelta(
            transport_name="synthetic_write",
            semantic_operation="write",
            turn_id=turn_id,
            resource_id=resource_id,
            start_at_us=event_at,
            mutation_at_us=event_at + 1 if include_state_change else None,
        ),
    )


_PENDING_TOOL_SQL = """
    SELECT
        tool_id, turn_id, transport_name, semantic_operation, start_at_us,
        start_source_rank, start_source_order, start_event_kind_order,
        start_occurrence_source_key,
        start_record_ordinal, start_byte_start, start_byte_end
    FROM tool_invocations
    WHERE terminal_at_us IS NULL
    ORDER BY
        start_at_us, start_source_rank, start_source_order,
        start_event_kind_order, tool_id
    LIMIT 1
"""


def _terminal_transition(
    connection: sqlite3.Connection,
) -> tuple[int, _ToolTerminalDelta]:
    tool = connection.execute(_PENDING_TOOL_SQL).fetchone()
    if tool is None:
        raise ValueError("candidate A fixture has no open tool lifecycle")
    terminal_at_us = int(tool["start_at_us"]) + 1
    connection.execute(
        """
        UPDATE tool_invocations SET
            state='succeeded',
            terminal_at_us=?,
            terminal_source_rank=?,
            terminal_occurrence_source_key=?,
            terminal_source_order=?,
            terminal_event_kind_order=50,
            terminal_record_ordinal=?,
            terminal_byte_start=?,
            terminal_byte_end=?,
            duration_us=1,
            output_bytes=0
        WHERE tool_id=?
        """,
        (
            terminal_at_us,
            int(tool["start_source_rank"]),
            int(tool["start_occurrence_source_key"]),
            int(tool["start_source_order"]) + 1,
            int(tool["start_record_ordinal"]) + 1,
            int(tool["start_byte_end"]),
            int(tool["start_byte_end"]),
            str(tool["tool_id"]),
        ),
    )
    return (
        1,
        _ToolTerminalDelta(
            transport_name=str(tool["transport_name"]),
            semantic_operation=str(tool["semantic_operation"]),
            turn_id=str(tool["turn_id"]),
            terminal_at_us=terminal_at_us,
            duration_us=1,
            output_bytes=0,
        ),
    )


def apply_ordinary_change(path: Path, change: str) -> MaintenanceStats:
    connection = open_database(path)
    inserted = 0
    updated = 0
    unchanged = 0
    dirty_keys = 0
    projection_read = 0
    projection_written = 0
    try:
        _require_clean_wal_epoch(connection, "before ordinary operation")
        if change == "no_source_change":
            started = time.perf_counter_ns()
            connection.execute(
                """
                    SELECT
                        (
                            SELECT calls
                            FROM usage_total_current
                            WHERE singleton=1
                        ) +
                        (
                            SELECT coalesce(sum(calls), 0)
                            FROM tool_family_current
                        )
                    """
            ).fetchone()[0]
            latency = time.perf_counter_ns() - started
            if latency <= 0:
                raise RuntimeError("ordinary no-source-change latency is not positive")
            if _require_checkpointed_wal(connection, "after no-source-change read") != 0:
                raise RuntimeError("no-source-change read wrote WAL frames")
            _require_clean_wal_epoch(connection, "after no-source-change read")
            return MaintenanceStats(ordinary_tail_latency_ns=latency)
        started = time.perf_counter_ns()
        connection.execute("BEGIN IMMEDIATE")
        if change in {"one_model_call", "32_call_tail", "2000_call_tail", "late_event"}:
            count = {
                "one_model_call": 1,
                "32_call_tail": 32,
                "2000_call_tail": 2_000,
                "late_event": 1,
            }[change]
            inserted, usage_delta = _insert_calls(
                connection,
                count=count,
                late=change == "late_event",
            )
            projection_read, projection_written = _increment_call_projections(
                connection,
                usage_delta,
            )
            anchor_read, anchor_written = _invalidate_evidence_anchors(connection)
            projection_read += anchor_read
            projection_written += anchor_written
            dirty_keys = projection_written
        elif change in {"one_tool_start", "tool_plus_state_change"}:
            inserted, updated, tool_start_delta = _insert_tool(
                connection,
                include_state_change=change == "tool_plus_state_change",
            )
            projection_read, projection_written = _increment_tool_family_start(
                connection,
                tool_start_delta,
            )
            turn_read, turn_written = _increment_turn_action_start(
                connection,
                tool_start_delta,
            )
            resource_read, resource_written = _refresh_resource_operation(
                connection,
                tool_start_delta.resource_id,
            )
            anchor_read, anchor_written = _invalidate_evidence_anchors(connection)
            projection_read += turn_read + resource_read + anchor_read
            projection_written += turn_written + resource_written + anchor_written
            dirty_keys = projection_written
        elif change == "tool_terminal_transition":
            updated, tool_terminal_delta = _terminal_transition(connection)
            projection_read, projection_written = _increment_tool_family_terminal(
                connection,
                tool_terminal_delta,
            )
            turn_read, turn_written = _increment_turn_action_terminal(
                connection,
                tool_terminal_delta,
            )
            anchor_read, anchor_written = _invalidate_evidence_anchors(connection)
            projection_read += turn_read + anchor_read
            projection_written += turn_written + anchor_written
            dirty_keys = projection_written
        elif change == "rate_card_change":
            connection.execute(
                """
                INSERT OR REPLACE INTO metadata(key, value)
                VALUES ('rate_card_revision', 'synthetic-replacement-v2')
                """
            )
            updated = 1
            dirty_keys = 1
        else:
            raise ValueError(f"unknown candidate A ordinary change: {change}")
        connection.commit()
        latency = time.perf_counter_ns() - started
        pages_written = _require_checkpointed_wal(connection, "after ordinary operation")
        _require_clean_wal_epoch(connection, "after ordinary operation")
        return MaintenanceStats(
            facts_inserted=inserted,
            facts_updated=updated,
            facts_unchanged=unchanged,
            dirty_keys=dirty_keys,
            projection_rows_read=projection_read,
            projection_rows_written=projection_written,
            ordinary_tail_latency_ns=latency,
            pages_written=pages_written,
            writer_transactions=1,
        )
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _checkpoint(connection: sqlite3.Connection, mode: str) -> tuple[int, int, int]:
    row = connection.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
    if row is None or len(row) != 3 or any(type(value) is not int for value in row):
        raise RuntimeError(f"SQLite {mode} checkpoint returned ambiguous result")
    return tuple(int(value) for value in row)


def _require_clean_wal_epoch(connection: sqlite3.Connection, stage: str) -> None:
    result = _checkpoint(connection, "TRUNCATE")
    if result != (0, 0, 0):
        raise RuntimeError(f"SQLite WAL is not clean {stage}: {result!r}")


def _require_checkpointed_wal(connection: sqlite3.Connection, stage: str) -> int:
    busy, log_frames, checkpointed = _checkpoint(connection, "PASSIVE")
    if busy != 0 or log_frames != checkpointed:
        raise RuntimeError(
            f"SQLite WAL checkpoint is ambiguous {stage}: {(busy, log_frames, checkpointed)!r}"
        )
    return log_frames


def apply_source_phase(
    connection: sqlite3.Connection,
    fixture: shared.FixtureBundle,
    *,
    group: str,
    phase: str,
) -> tuple[str, ...]:
    selected = [
        artifact
        for artifact in fixture.phases
        if artifact.group == group and artifact.phase == phase
    ]
    if len(selected) != 1:
        raise ValueError(f"candidate A phase is not unique: {group}/{phase}")
    artifact = selected[0]
    occurrence_ids: list[str] = []
    for line in artifact.absolute_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        payload = record["payload"]
        occurrence_id = str(payload["occurrence_id"])
        occurrence_ids.append(occurrence_id)
        connection.execute(
            """
            INSERT OR REPLACE INTO source_phase_occurrences(
                phase_id, occurrence_id, revision, structural_case,
                event_at_us, source_order, event_kind_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact.phase_id,
                occurrence_id,
                str(payload["revision"]),
                str(payload["structural_case"]),
                int(record["event_at_us"]),
                int(record["source_order"]),
                int(record["event_kind_order"]),
            ),
        )
    _invalidate_evidence_anchors(connection)
    return tuple(occurrence_ids)
