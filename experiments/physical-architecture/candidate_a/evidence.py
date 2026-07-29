from __future__ import annotations

import base64
import hashlib
import heapq
import json
import sqlite3
from dataclasses import dataclass
from typing import Any

import shared

_CURSOR_SCHEMA = "candidate-a-keyset-v1"
_CURSOR_DOMAIN = b"codex-usage-tracker-ck04-candidate-a"
OrderKey = tuple[int, int, int, int, str, int]


class EvidenceContractError(ValueError):
    pass


@dataclass(frozen=True)
class EvidencePage:
    publication_id: str
    rows: tuple[dict[str, Any], ...]
    has_more: bool
    next_cursor: str | None
    query_plans: tuple[str, ...]
    full_scan_count: int
    temporary_sort_count: int


@dataclass(frozen=True)
class _Stream:
    sql: str
    parameters: tuple[object, ...]


def _cursor_payload(publication_id: str, order_key: OrderKey) -> bytes:
    return shared.canonical_json_bytes(
        {
            "schema": _CURSOR_SCHEMA,
            "publication_id": publication_id,
            "order_key": list(order_key),
        }
    )


def _encode_cursor(publication_id: str, order_key: OrderKey) -> str:
    payload = _cursor_payload(publication_id, order_key)
    signature = hashlib.sha256(_CURSOR_DOMAIN + b"\0" + payload).digest()
    return base64.urlsafe_b64encode(signature + payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str, publication_id: str) -> OrderKey:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
    except (ValueError, UnicodeEncodeError) as error:
        raise EvidenceContractError("candidate A evidence cursor is malformed") from error
    if len(raw) <= 32:
        raise EvidenceContractError("candidate A evidence cursor is incomplete")
    signature, payload = raw[:32], raw[32:]
    if signature != hashlib.sha256(_CURSOR_DOMAIN + b"\0" + payload).digest():
        raise EvidenceContractError("candidate A evidence cursor signature is invalid")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise EvidenceContractError("candidate A evidence cursor payload is invalid") from error
    if (
        not isinstance(value, dict)
        or value.get("schema") != _CURSOR_SCHEMA
        or value.get("publication_id") != publication_id
    ):
        raise EvidenceContractError("candidate A evidence cursor publication differs")
    key = value.get("order_key")
    if (
        not isinstance(key, list)
        or len(key) != 6
        or not all(isinstance(item, int) for item in key[:4])
        or not isinstance(key[4], str)
        or not isinstance(key[5], int)
    ):
        raise EvidenceContractError("candidate A evidence cursor key is invalid")
    return (int(key[0]), int(key[1]), int(key[2]), int(key[3]), key[4], int(key[5]))


def _select(
    *,
    table: str,
    occurrence_source_key: str | None = None,
    event_at: str,
    source_rank: str,
    source_order: str,
    event_kind_order: str,
    logical_id: str,
    transition_rank: int,
    event_kind: str,
    session_id: str = "NULL",
    turn_id: str = "NULL",
    transport_name: str = "NULL",
    semantic_operation: str = "NULL",
    resource_id: str = "NULL",
    state: str = "NULL",
    uncached_input_tokens: str = "NULL",
    cached_input_tokens: str = "NULL",
    reasoning_tokens: str = "NULL",
    output_tokens: str = "NULL",
    duration_us: str = "NULL",
    output_bytes: str = "NULL",
    manifestation_id: str,
    source_revision: str,
    adapter_version: str,
    source_path: str,
    record_ordinal: str,
    byte_start: str,
    byte_end: str,
    required: str | None = None,
    selected_session_id: str | None = None,
    session_filter_column: str | None = None,
    after: OrderKey | None,
    limit: int,
) -> _Stream | None:
    if occurrence_source_key is not None:
        table = (
            f"{table} AS event "
            "JOIN source_manifestations AS occurrence_source "
            "ON occurrence_source.occurrence_source_key="
            f"event.{occurrence_source_key}"
        )

        def fact(expression: str) -> str:
            if expression == "NULL" or expression.startswith("'"):
                return expression
            return f"event.{expression}"

        event_at = fact(event_at)
        source_rank = fact(source_rank)
        source_order = fact(source_order)
        event_kind_order = fact(event_kind_order)
        logical_id = fact(logical_id)
        session_id = fact(session_id)
        turn_id = fact(turn_id)
        transport_name = fact(transport_name)
        semantic_operation = fact(semantic_operation)
        resource_id = fact(resource_id)
        state = fact(state)
        uncached_input_tokens = fact(uncached_input_tokens)
        cached_input_tokens = fact(cached_input_tokens)
        reasoning_tokens = fact(reasoning_tokens)
        output_tokens = fact(output_tokens)
        duration_us = fact(duration_us)
        output_bytes = fact(output_bytes)
        record_ordinal = fact(record_ordinal)
        byte_start = fact(byte_start)
        byte_end = fact(byte_end)
        manifestation_id = "occurrence_source.manifestation_id"
        source_revision = "occurrence_source.revision"
        adapter_version = "occurrence_source.adapter_version"
        source_path = "occurrence_source.source_path"
        if session_filter_column is not None:
            session_filter_column = fact(session_filter_column)
        if required is not None:
            required = f"event.{required}"

    if selected_session_id is not None and session_filter_column is None:
        return None
    parameters: list[object] = []
    predicates: list[str] = []
    transition_expression = f"CAST({transition_rank} AS INTEGER)"
    if required is not None:
        predicates.append(required)
    if selected_session_id is not None and session_filter_column is not None:
        predicates.append(f"{session_filter_column} = ?")
        parameters.append(selected_session_id)
    if after is not None:
        predicates.append(
            f"({event_at}, {source_rank}, {source_order}, {event_kind_order}, "
            f"{logical_id}, {transition_expression}) > (?, ?, ?, ?, ?, ?)"
        )
        parameters.extend(after)
    where = " WHERE " + " AND ".join(predicates) if predicates else ""
    sql = f"""
        SELECT
            {event_at} AS event_at_us,
            {source_rank} AS source_rank,
            {source_order} AS source_order,
            {event_kind_order} AS event_kind_order,
            {logical_id} AS logical_id,
            {transition_expression} AS transition_rank,
            '{event_kind}' AS event_kind,
            {session_id} AS session_id,
            {turn_id} AS turn_id,
            {transport_name} AS transport_name,
            {semantic_operation} AS semantic_operation,
            {resource_id} AS resource_id,
            {state} AS lifecycle_state,
            {uncached_input_tokens} AS uncached_input_tokens,
            {cached_input_tokens} AS cached_input_tokens,
            {reasoning_tokens} AS reasoning_tokens,
            {output_tokens} AS output_tokens,
            {duration_us} AS duration_us,
            {output_bytes} AS output_bytes,
            {manifestation_id} AS manifestation_id,
            {source_revision} AS source_revision,
            {adapter_version} AS adapter_version,
            {source_path} AS source_path,
            {record_ordinal} AS record_ordinal,
            {byte_start} AS byte_start,
            {byte_end} AS byte_end
        FROM {table}
        {where}
        ORDER BY
            {event_at}, {source_rank}, {source_order},
            {event_kind_order}, {logical_id}
        LIMIT ?
    """
    parameters.append(limit)
    return _Stream(sql=sql, parameters=tuple(parameters))


def _streams(
    *,
    selected_session_id: str | None,
    after: OrderKey | None,
    limit: int,
) -> tuple[_Stream, ...]:
    specs = (
        _select(
            table="selector_anchors",
            event_at="event_at_us",
            source_rank="source_rank",
            source_order="source_order",
            event_kind_order="event_kind_order",
            logical_id="logical_id",
            transition_rank=0,
            event_kind="selector_anchor",
            manifestation_id="manifestation_id",
            source_revision="source_revision",
            adapter_version="adapter_version",
            source_path="source_path",
            record_ordinal="record_ordinal",
            byte_start="byte_start",
            byte_end="byte_end",
            selected_session_id=selected_session_id,
            after=after,
            limit=limit,
        ),
        _select(
            table="sessions",
            event_at="start_at_us",
            source_rank="start_source_rank",
            source_order="start_source_order",
            event_kind_order="start_event_kind_order",
            logical_id="session_id",
            transition_rank=0,
            event_kind="session_start",
            session_id="session_id",
            state="'running'",
            manifestation_id="start_manifestation_id",
            source_revision="start_source_revision",
            adapter_version="start_adapter_version",
            source_path="start_source_path",
            record_ordinal="start_record_ordinal",
            byte_start="start_byte_start",
            byte_end="start_byte_end",
            selected_session_id=selected_session_id,
            session_filter_column="session_id",
            after=after,
            limit=limit,
        ),
        _select(
            table="sessions",
            event_at="terminal_at_us",
            source_rank="terminal_source_rank",
            source_order="terminal_source_order",
            event_kind_order="terminal_event_kind_order",
            logical_id="session_id",
            transition_rank=1,
            event_kind="session_terminal",
            session_id="session_id",
            state="state",
            manifestation_id="terminal_manifestation_id",
            source_revision="terminal_source_revision",
            adapter_version="terminal_adapter_version",
            source_path="terminal_source_path",
            record_ordinal="terminal_record_ordinal",
            byte_start="terminal_byte_start",
            byte_end="terminal_byte_end",
            required="terminal_at_us IS NOT NULL",
            selected_session_id=selected_session_id,
            session_filter_column="session_id",
            after=after,
            limit=limit,
        ),
        _select(
            table="turns",
            occurrence_source_key="occurrence_source_key",
            event_at="start_at_us",
            source_rank="source_rank",
            source_order="source_order",
            event_kind_order="event_kind_order",
            logical_id="turn_id",
            transition_rank=0,
            event_kind="turn_start",
            session_id="session_id",
            turn_id="turn_id",
            state="state",
            manifestation_id="manifestation_id",
            source_revision="source_revision",
            adapter_version="adapter_version",
            source_path="source_path",
            record_ordinal="record_ordinal",
            byte_start="byte_start",
            byte_end="byte_end",
            selected_session_id=selected_session_id,
            session_filter_column="session_id",
            after=after,
            limit=limit,
        ),
        _select(
            table="model_calls",
            occurrence_source_key="occurrence_source_key",
            event_at="event_at_us",
            source_rank="source_rank",
            source_order="source_order",
            event_kind_order="event_kind_order",
            logical_id="call_id",
            transition_rank=0,
            event_kind="model_call",
            session_id="session_id",
            turn_id="turn_id",
            state="'observed'",
            uncached_input_tokens="uncached_input_tokens",
            cached_input_tokens="cached_input_tokens",
            reasoning_tokens="reasoning_tokens",
            output_tokens="output_tokens",
            manifestation_id="manifestation_id",
            source_revision="source_revision",
            adapter_version="adapter_version",
            source_path="source_path",
            record_ordinal="record_ordinal",
            byte_start="byte_start",
            byte_end="byte_end",
            selected_session_id=selected_session_id,
            session_filter_column="session_id",
            after=after,
            limit=limit,
        ),
        _select(
            table="tool_invocations",
            occurrence_source_key="start_occurrence_source_key",
            event_at="start_at_us",
            source_rank="start_source_rank",
            source_order="start_source_order",
            event_kind_order="start_event_kind_order",
            logical_id="tool_id",
            transition_rank=0,
            event_kind="tool_start",
            session_id="session_id",
            turn_id="turn_id",
            transport_name="transport_name",
            semantic_operation="semantic_operation",
            resource_id="resource_id",
            state="'running'",
            manifestation_id="start_manifestation_id",
            source_revision="start_source_revision",
            adapter_version="start_adapter_version",
            source_path="start_source_path",
            record_ordinal="start_record_ordinal",
            byte_start="start_byte_start",
            byte_end="start_byte_end",
            selected_session_id=selected_session_id,
            session_filter_column="session_id",
            after=after,
            limit=limit,
        ),
        _select(
            table="tool_invocations",
            occurrence_source_key="terminal_occurrence_source_key",
            event_at="terminal_at_us",
            source_rank="terminal_source_rank",
            source_order="terminal_source_order",
            event_kind_order="terminal_event_kind_order",
            logical_id="tool_id",
            transition_rank=1,
            event_kind="tool_terminal",
            session_id="session_id",
            turn_id="turn_id",
            transport_name="transport_name",
            semantic_operation="semantic_operation",
            resource_id="resource_id",
            state="state",
            duration_us="duration_us",
            output_bytes="output_bytes",
            manifestation_id="terminal_manifestation_id",
            source_revision="terminal_source_revision",
            adapter_version="terminal_adapter_version",
            source_path="terminal_source_path",
            record_ordinal="terminal_record_ordinal",
            byte_start="terminal_byte_start",
            byte_end="terminal_byte_end",
            required="terminal_at_us IS NOT NULL",
            selected_session_id=selected_session_id,
            session_filter_column="session_id",
            after=after,
            limit=limit,
        ),
        _select(
            table="activities",
            event_at="event_at_us",
            source_rank="source_rank",
            source_order="source_order",
            event_kind_order="event_kind_order",
            logical_id="activity_id",
            transition_rank=0,
            event_kind="activity",
            session_id="session_id",
            turn_id="turn_id",
            state="state",
            manifestation_id="manifestation_id",
            source_revision="source_revision",
            adapter_version="adapter_version",
            source_path="source_path",
            record_ordinal="record_ordinal",
            byte_start="byte_start",
            byte_end="byte_end",
            selected_session_id=selected_session_id,
            session_filter_column="session_id",
            after=after,
            limit=limit,
        ),
        _select(
            table="state_changes",
            event_at="event_at_us",
            source_rank="source_rank",
            source_order="source_order",
            event_kind_order="event_kind_order",
            logical_id="change_id",
            transition_rank=0,
            event_kind="state_change",
            session_id="session_id",
            turn_id="turn_id",
            resource_id="resource_id",
            state="'observed'",
            manifestation_id="manifestation_id",
            source_revision="source_revision",
            adapter_version="adapter_version",
            source_path="source_path",
            record_ordinal="record_ordinal",
            byte_start="byte_start",
            byte_end="byte_end",
            selected_session_id=selected_session_id,
            session_filter_column="session_id",
            after=after,
            limit=limit,
        ),
        _select(
            table="compaction_boundaries",
            event_at="event_at_us",
            source_rank="source_rank",
            source_order="source_order",
            event_kind_order="event_kind_order",
            logical_id="compaction_id",
            transition_rank=0,
            event_kind="compaction_boundary",
            session_id="session_id",
            state="'observed'",
            manifestation_id="manifestation_id",
            source_revision="source_revision",
            adapter_version="adapter_version",
            source_path="source_path",
            record_ordinal="record_ordinal",
            byte_start="byte_start",
            byte_end="byte_end",
            selected_session_id=selected_session_id,
            session_filter_column="session_id",
            after=after,
            limit=limit,
        ),
        _select(
            table="allowance_observations",
            event_at="event_at_us",
            source_rank="source_rank",
            source_order="source_order",
            event_kind_order="event_kind_order",
            logical_id="observation_id",
            transition_rank=0,
            event_kind="allowance_observation",
            state="'observed'",
            manifestation_id="manifestation_id",
            source_revision="source_revision",
            adapter_version="adapter_version",
            source_path="source_path",
            record_ordinal="record_ordinal",
            byte_start="byte_start",
            byte_end="byte_end",
            selected_session_id=selected_session_id,
            after=after,
            limit=limit,
        ),
        _select(
            table="allowance_compatibility",
            event_at="event_at_us",
            source_rank="source_rank",
            source_order="source_order",
            event_kind_order="event_kind_order",
            logical_id="compatibility_id",
            transition_rank=0,
            event_kind="allowance_compatibility",
            state="'observed'",
            manifestation_id="manifestation_id",
            source_revision="source_revision",
            adapter_version="adapter_version",
            source_path="source_path",
            record_ordinal="record_ordinal",
            byte_start="byte_start",
            byte_end="byte_end",
            selected_session_id=selected_session_id,
            after=after,
            limit=limit,
        ),
        _select(
            table="late_parent_edges",
            event_at="event_at_us",
            source_rank="source_rank",
            source_order="source_order",
            event_kind_order="event_kind_order",
            logical_id="child_session_id",
            transition_rank=0,
            event_kind="late_parent",
            session_id="child_session_id",
            state="'observed'",
            manifestation_id="manifestation_id",
            source_revision="source_revision",
            adapter_version="adapter_version",
            source_path="source_path",
            record_ordinal="record_ordinal",
            byte_start="byte_start",
            byte_end="byte_end",
            selected_session_id=selected_session_id,
            session_filter_column="child_session_id",
            after=after,
            limit=limit,
        ),
    )
    return tuple(stream for stream in specs if stream is not None)


def _query_plan(
    connection: sqlite3.Connection,
    stream: _Stream,
) -> tuple[str, ...]:
    return tuple(
        str(row[3])
        for row in connection.execute(
            "EXPLAIN QUERY PLAN " + stream.sql,
            stream.parameters,
        )
    )


def _row_order(row: sqlite3.Row) -> OrderKey:
    return (
        int(row["event_at_us"]),
        int(row["source_rank"]),
        int(row["source_order"]),
        int(row["event_kind_order"]),
        str(row["logical_id"]),
        int(row["transition_rank"]),
    )


def _result_row(row: sqlite3.Row) -> dict[str, Any]:
    token_fields = (
        "uncached_input_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "output_tokens",
    )
    tokens = {field: row[field] for field in token_fields}
    if all(value is None for value in tokens.values()):
        tokens = {}
    return {
        "order_key": list(_row_order(row)),
        "event_at_us": int(row["event_at_us"]),
        "event_kind": str(row["event_kind"]),
        "logical_id": str(row["logical_id"]),
        "session_id": row["session_id"],
        "turn_id": row["turn_id"],
        "transport_name": row["transport_name"],
        "semantic_operation": row["semantic_operation"],
        "resource_id": row["resource_id"],
        "lifecycle_state": row["lifecycle_state"],
        "tokens": tokens,
        "duration_us": row["duration_us"],
        "output_bytes": row["output_bytes"],
        "occurrence_coordinate": {
            "manifestation_id": str(row["manifestation_id"]),
            "revision": str(row["source_revision"]),
            "adapter_version": str(row["adapter_version"]),
            "source_path": str(row["source_path"]),
            "record_ordinal": int(row["record_ordinal"]),
            "byte_start": int(row["byte_start"]),
            "byte_end": int(row["byte_end"]),
        },
    }


def evidence_page(
    connection: sqlite3.Connection,
    *,
    publication_id: str,
    page_size: int = 100,
    cursor: str | None = None,
    selected_session_id: str | None = None,
) -> EvidencePage:
    if not 1 <= page_size <= 100:
        raise EvidenceContractError("candidate A evidence page size must be 1..100")
    after = _decode_cursor(cursor, publication_id) if cursor is not None else None
    streams = _streams(
        selected_session_id=selected_session_id,
        after=after,
        limit=page_size + 1,
    )
    plans = tuple(plan for stream in streams for plan in _query_plan(connection, stream))
    full_scans = sum(
        "SCAN " in plan and "USING INDEX" not in plan and "USING COVERING INDEX" not in plan
        for plan in plans
    )
    temporary_sorts = sum("USE TEMP B-TREE" in plan for plan in plans)
    iterators = [iter(connection.execute(stream.sql, stream.parameters)) for stream in streams]
    heap: list[tuple[OrderKey, int, sqlite3.Row]] = []
    for index, iterator in enumerate(iterators):
        first = next(iterator, None)
        if first is not None:
            heapq.heappush(heap, (_row_order(first), index, first))
    selected: list[sqlite3.Row] = []
    while heap and len(selected) <= page_size:
        _, index, row = heapq.heappop(heap)
        selected.append(row)
        following = next(iterators[index], None)
        if following is not None:
            heapq.heappush(heap, (_row_order(following), index, following))
    has_more = len(selected) > page_size
    visible = selected[:page_size]
    next_cursor = (
        _encode_cursor(publication_id, _row_order(visible[-1]))
        if has_more and visible
        else None
    )
    return EvidencePage(
        publication_id=publication_id,
        rows=tuple(_result_row(row) for row in visible),
        has_more=has_more,
        next_cursor=next_cursor,
        query_plans=plans,
        full_scan_count=full_scans,
        temporary_sort_count=temporary_sorts,
    )


def all_evidence_rows(
    connection: sqlite3.Connection,
    *,
    publication_id: str,
    page_size: int = 37,
    selected_session_id: str | None = None,
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        page = evidence_page(
            connection,
            publication_id=publication_id,
            page_size=page_size,
            cursor=cursor,
            selected_session_id=selected_session_id,
        )
        rows.extend(page.rows)
        if not page.has_more:
            return tuple(rows)
        if page.next_cursor is None:
            raise AssertionError("candidate A evidence page lost its keyset cursor")
        cursor = page.next_cursor


def resolve_selector(
    connection: sqlite3.Connection,
    selector: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT
            selector, selector_kind, logical_id, manifestation_id,
            source_revision, adapter_version, source_path, record_ordinal,
            byte_start, byte_end
        FROM selector_anchors
        WHERE selector = ?
        """,
        (selector,),
    ).fetchone()
    if row is None:
        return None
    return {
        "selector": str(row["selector"]),
        "selector_kind": str(row["selector_kind"]),
        "logical_id": str(row["logical_id"]),
        "occurrence_coordinate": {
            "manifestation_id": str(row["manifestation_id"]),
            "revision": str(row["source_revision"]),
            "adapter_version": str(row["adapter_version"]),
            "source_path": str(row["source_path"]),
            "record_ordinal": int(row["record_ordinal"]),
            "byte_start": int(row["byte_start"]),
            "byte_end": int(row["byte_end"]),
        },
    }
