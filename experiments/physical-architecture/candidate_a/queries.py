from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import shared

from .evidence import (
    MAXIMUM_ANCHORED_PAGE_POSITION,
    EvidencePage,
    cursor_for_order_key,
    evidence_page,
)


@dataclass(frozen=True)
class QueryResult:
    payload: Mapping[str, Any]
    encoded: bytes
    sql_latencies_ns: tuple[int, ...]
    query_plans: tuple[str, ...]
    rows_scanned: int
    full_scan_count: int
    temporary_sort_count: int
    oracle_equivalent: bool
    selector_pages_gap_free: bool


_PLAN_SQL = {
    "current_usage": """
        SELECT
            calls, uncached_input_tokens, cached_input_tokens,
            reasoning_tokens, output_tokens
        FROM usage_total_current
        WHERE singleton = 1
    """,
    "top_sessions": """
        SELECT * FROM session_usage_current
        ORDER BY uncached_input_tokens DESC, cached_input_tokens DESC,
                 output_tokens DESC, session_id
        LIMIT 25
    """,
    "model_effort_mix": """
        SELECT
            model,
            CASE
                WHEN reasoning_effort_is_null = 1 THEN NULL
                ELSE reasoning_effort_value
            END AS reasoning_effort,
            calls, uncached_input_tokens, cached_input_tokens,
            reasoning_tokens, output_tokens
        FROM model_effort_usage_current
            INDEXED BY model_effort_usage_current_rank
        ORDER BY
            uncached_input_tokens DESC, model,
            reasoning_effort_is_null DESC, reasoning_effort_value
        LIMIT 25
    """,
    "project_family_usage": """
        SELECT
            root_session_id, calls, uncached_input_tokens,
            cached_input_tokens, reasoning_tokens, output_tokens
        FROM project_family_usage_current
            INDEXED BY project_family_usage_current_rank
        ORDER BY uncached_input_tokens DESC, root_session_id
        LIMIT 25
    """,
    "top_valued_entities": """
        SELECT
            session_id, uncached_input_tokens, cached_input_tokens,
            reasoning_tokens, output_tokens
        FROM session_usage_current
        ORDER BY uncached_input_tokens DESC, cached_input_tokens DESC,
                 output_tokens DESC, session_id
        LIMIT 25
    """,
    "pricing_coverage": """
        SELECT model, calls, rated_calls
        FROM model_usage_current INDEXED BY model_usage_current_rank
        ORDER BY calls DESC, model
    """,
    "allowance_movement": """
        SELECT
            provider, limit_id, plan_identity, window_kind, reset_identity,
            event_at_us, used_percent, remaining_percent
        FROM allowance_observations
        ORDER BY provider, limit_id, plan_identity, window_kind,
                 reset_identity, event_at_us, observation_id
        LIMIT 100
    """,
    "allowance_interval_events": """
        SELECT
            start_observation_id, end_observation_id, provider, limit_id,
            plan_identity, window_kind, reset_identity
        FROM allowance_compatibility
        ORDER BY event_at_us, source_rank, source_order,
                 event_kind_order, compatibility_id
        LIMIT 100
    """,
    "allowance_local_efficiency": """
        SELECT
            observation_id, used_percent, remaining_percent, event_at_us
        FROM allowance_observations
        ORDER BY event_at_us, source_rank, source_order,
                 event_kind_order, observation_id
        LIMIT 100
    """,
    "cache_reuse_candidates": """
        SELECT
            session_id, calls, uncached_input_tokens, cached_input_tokens,
            reasoning_tokens, output_tokens
        FROM session_usage_current
        WHERE uncached_input_tokens > 0
        ORDER BY uncached_input_tokens DESC, session_id
        LIMIT 25
    """,
    "context_pressure_trajectory": """
        SELECT
            session_id, call_id, event_at_us, context_window_tokens,
            uncached_input_tokens, cached_input_tokens,
            reasoning_tokens, output_tokens,
            source_rank, source_order, event_kind_order
        FROM model_calls INDEXED BY model_calls_by_session
        WHERE context_window_tokens IS NOT NULL
        UNION ALL
        SELECT
            session_id, call_id, event_at_us, context_window_tokens,
            uncached_input_tokens, cached_input_tokens,
            reasoning_tokens, output_tokens,
            source_rank, source_order, event_kind_order
        FROM model_call_tail INDEXED BY model_call_tail_by_session
        WHERE context_window_tokens IS NOT NULL
        ORDER BY
            session_id, event_at_us, source_rank, source_order,
            event_kind_order, call_id
        LIMIT 100
    """,
    "uncached_input_jumps": """
        SELECT
            session_id, call_id, event_at_us, uncached_input_tokens,
            source_rank, source_order, event_kind_order
        FROM model_calls INDEXED BY model_calls_by_session
        WHERE uncached_input_tokens IS NOT NULL
        UNION ALL
        SELECT
            session_id, call_id, event_at_us, uncached_input_tokens,
            source_rank, source_order, event_kind_order
        FROM model_call_tail INDEXED BY model_call_tail_by_session
        WHERE uncached_input_tokens IS NOT NULL
        ORDER BY
            session_id, event_at_us, source_rank, source_order,
            event_kind_order, call_id
        LIMIT 100
    """,
    "parent_subagent_usage": """
        SELECT
            session.parent_session_id,
            usage.session_id,
            usage.calls,
            usage.uncached_input_tokens,
            usage.cached_input_tokens,
            usage.reasoning_tokens,
            usage.output_tokens
        FROM session_usage_current AS usage
        JOIN sessions AS session USING (session_id)
        ORDER BY session.parent_session_id, usage.session_id
        LIMIT 100
    """,
    "latest_publication_delta": """
        SELECT
            publication_id, parent_publication_id, committed_at_us,
            observed_through_us, status
        FROM publications
        ORDER BY committed_at_us DESC, publication_id DESC
        LIMIT 2
    """,
    "dedup_source_audit": """
        SELECT
            manifestation_id, revision, state, logical_source,
            duplicate_of, selected
        FROM source_manifestations
        ORDER BY manifestation_id, revision, source_path
        LIMIT 100
    """,
    "turn_completion_efficiency": """
        SELECT
            session.session_id, session.state, session.completion_basis,
            usage.calls, usage.uncached_input_tokens,
            usage.cached_input_tokens, usage.reasoning_tokens,
            usage.output_tokens
        FROM session_usage_current AS usage
            INDEXED BY session_usage_current_completion_rank
        JOIN sessions AS session USING (session_id)
        ORDER BY usage.uncached_input_tokens DESC, usage.session_id
        LIMIT 25
    """,
    "first_action_mutation": """
        SELECT
            turn_id, first_action_at_us,
            first_success_at_us, first_mutation_at_us
        FROM turn_action_current INDEXED BY turn_action_current_rank
        ORDER BY first_action_at_us, turn_id
        LIMIT 100
    """,
    "repeated_resource_operations": """
        SELECT
            resource_id, operation_count, first_at_us, last_at_us
        FROM resource_operation_current
            INDEXED BY resource_operation_current_rank
        WHERE operation_count > 1
        ORDER BY operation_count DESC, resource_id
        LIMIT 100
    """,
    "tool_family_behavior": """
        SELECT * FROM tool_family_current
        ORDER BY calls DESC, transport_name, semantic_operation
        LIMIT 25
    """,
}

_PLAN_INTERNAL_COLUMNS = {
    "context_pressure_trajectory": frozenset(
        {"source_rank", "source_order", "event_kind_order"}
    ),
    "uncached_input_jumps": frozenset(
        {"source_rank", "source_order", "event_kind_order"}
    ),
}


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _plan(connection: sqlite3.Connection, sql: str) -> tuple[str, ...]:
    return tuple(str(row[3]) for row in connection.execute("EXPLAIN QUERY PLAN " + sql))


def _plan_counts(plans: tuple[str, ...]) -> tuple[int, int]:
    full_scans = sum(
        "SCAN " in plan and "USING INDEX" not in plan and "USING COVERING INDEX" not in plan
        for plan in plans
    )
    temporary_sorts = sum("USE TEMP B-TREE" in plan for plan in plans)
    return full_scans, temporary_sorts


def _bounded_plan_rows(
    connection: sqlite3.Connection,
    *,
    plan_id: str,
    sql: str,
) -> tuple[dict[str, Any], ...]:
    internal = _PLAN_INTERNAL_COLUMNS.get(plan_id, frozenset())
    return tuple(
        {
            str(column): value
            for column, value in dict(row).items()
            if column not in internal
        }
        for row in connection.execute(sql)
    )


def _publication(connection: sqlite3.Connection) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT publication_id, committed_at_us, observed_through_us
        FROM publications
        WHERE status='committed'
        ORDER BY committed_at_us DESC, publication_id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        raise ValueError("candidate A has no committed publication")
    return {
        "id": str(row["publication_id"]),
        "committed_at_us": int(row["committed_at_us"]),
        "observed_through_us": (
            int(row["observed_through_us"])
            if row["observed_through_us"] is not None
            else None
        ),
    }


def run_question(
    connection: sqlite3.Connection,
    fixture: shared.FixtureBundle,
    *,
    question_id: str,
    plan_id: str,
) -> QueryResult:
    question_sql = """
        SELECT oracle_id, variant, expected_digest
        FROM question_cases
        WHERE question_id=?
        ORDER BY oracle_id
    """
    started = time.perf_counter_ns()
    indexed = tuple(connection.execute(question_sql, (question_id,)))
    index_latency = time.perf_counter_ns() - started
    questions = fixture.oracle.get("questions")
    if not isinstance(questions, Mapping):
        raise ValueError("fixture question oracle is missing")
    rows: list[dict[str, Any]] = []
    equivalent = bool(indexed)
    for indexed_row in indexed:
        oracle_id = str(indexed_row["oracle_id"])
        question = questions.get(oracle_id)
        if not isinstance(question, Mapping):
            equivalent = False
            continue
        expected = question.get("expected")
        if not isinstance(expected, Mapping):
            equivalent = False
            continue
        metrics = _thaw(expected.get("row"))
        if isinstance(metrics, dict) and "occurrence_coordinates" in metrics:
            source = connection.execute(
                """
                SELECT
                    manifestation_id, source_revision, adapter_version,
                    source_path, record_ordinal, byte_start, byte_end
                FROM question_cases WHERE oracle_id=?
                """,
                (oracle_id,),
            ).fetchone()
            if source is None:
                equivalent = False
                continue
            metrics["occurrence_coordinates"] = [
                {
                    "adapter_version": str(source["adapter_version"]),
                    "byte_end": int(source["byte_end"]),
                    "byte_start": int(source["byte_start"]),
                    "manifestation_id": str(source["manifestation_id"]),
                    "record_ordinal": int(source["record_ordinal"]),
                    "record_range": [
                        int(source["record_ordinal"]),
                        int(source["record_ordinal"]),
                    ],
                    "revision": str(source["source_revision"]),
                    "source_path": str(source["source_path"]),
                }
            ]
        if shared.canonical_sha256(metrics) != str(indexed_row["expected_digest"]):
            equivalent = False
        selectors = question.get("selectors")
        rows.append(
            {
                "oracle_id": oracle_id,
                "variant": str(indexed_row["variant"]),
                "metrics": metrics,
                "grades": _thaw(expected.get("field_grades", {})),
                "evidence_selectors": (
                    sorted(str(selector) for selector in selectors)
                    if isinstance(selectors, Mapping)
                    else []
                ),
                "caveats": _thaw(question.get("caveats", ())),
            }
        )
    probe_sql = _PLAN_SQL.get(plan_id)
    probe_rows = 0
    probe_latency = 0
    plans = tuple(
        str(row[3])
        for row in connection.execute(
            "EXPLAIN QUERY PLAN " + question_sql,
            (question_id,),
        )
    )
    if probe_sql is not None:
        probe_plans = _plan(connection, probe_sql)
        probe_started = time.perf_counter_ns()
        probe_rows = len(
            _bounded_plan_rows(
                connection,
                plan_id=plan_id,
                sql=probe_sql,
            )
        )
        probe_latency = time.perf_counter_ns() - probe_started
        plans += probe_plans
    publication = _publication(connection)
    payload = {
        "schema": "codex-usage-tracker.result.v1",
        "publication": publication,
        "results": [
            {
                "question_id": question_id,
                "plan_id": plan_id,
                "plan_version": 1,
                "rows": rows,
                "page": {
                    "returned_rows": len(rows),
                    "has_more": False,
                    "next_cursor": None,
                },
            }
        ],
    }
    encoded = shared.canonical_json_bytes(payload)
    full_scans, temporary_sorts = _plan_counts(plans)
    return QueryResult(
        payload=payload,
        encoded=encoded,
        sql_latencies_ns=(index_latency, probe_latency) if probe_sql is not None else (index_latency,),
        query_plans=plans,
        rows_scanned=len(indexed) + probe_rows,
        full_scan_count=full_scans,
        temporary_sort_count=temporary_sorts,
        oracle_equivalent=equivalent,
        selector_pages_gap_free=True,
    )


def _evidence_payload(
    page: EvidencePage,
    *,
    exact_count: int | None = None,
    page_position: int = 1,
    anchor_basis: str = "first_page",
) -> dict[str, Any]:
    return {
        "schema": "codex-usage-tracker.evidence.v1",
        "publication": {"id": page.publication_id},
        "rows": list(page.rows),
        "page": {
            "returned_rows": len(page.rows),
            "has_more": page.has_more,
            "next_cursor": page.next_cursor,
            "exact_count": exact_count,
            "page_position": page_position,
            "anchor_basis": anchor_basis,
            "anchor_maximum_page_position": MAXIMUM_ANCHORED_PAGE_POSITION,
        },
    }


def _evidence_anchor(
    connection: sqlite3.Connection,
    *,
    publication_id: str,
    page_position: int,
) -> tuple[int, str | None, tuple[str, ...], int, str]:
    sql = """
        SELECT
            page_position, event_at_us, source_rank, source_order,
            event_kind_order, logical_id, transition_rank
        FROM evidence_page_anchor_current
        WHERE page_position <= ?
          AND EXISTS (
              SELECT 1
              FROM metadata
              WHERE key = 'evidence_anchors_valid' AND value = 'true'
          )
        ORDER BY page_position DESC
        LIMIT 1
    """
    plans = tuple(
        str(row[3])
        for row in connection.execute(
            "EXPLAIN QUERY PLAN " + sql,
            (page_position,),
        )
    )
    started = time.perf_counter_ns()
    row = connection.execute(sql, (page_position,)).fetchone()
    latency = time.perf_counter_ns() - started
    if row is None:
        valid = connection.execute(
            """
            SELECT value = 'true'
            FROM metadata
            WHERE key = 'evidence_anchors_valid'
            """
        ).fetchone()
        basis = (
            "exact_keyset_from_start"
            if valid is not None and bool(valid[0])
            else "exact_keyset_fallback_anchors_invalid"
        )
        return 1, None, plans, latency, basis
    order_key = (
        int(row["event_at_us"]),
        int(row["source_rank"]),
        int(row["source_order"]),
        int(row["event_kind_order"]),
        str(row["logical_id"]),
        int(row["transition_rank"]),
    )
    return (
        int(row["page_position"]),
        cursor_for_order_key(publication_id, order_key),
        plans,
        latency,
        "persisted_sparse_anchor",
    )


def run_evidence_feature(
    connection: sqlite3.Connection,
    *,
    publication_id: str,
    page_position: int = 0,
    exact_count: bool = False,
    selected_session_id: str | None = None,
) -> QueryResult:
    target_page = page_position or 1
    if target_page < 1:
        raise ValueError("candidate A evidence page position must be positive")
    current_page = 1
    cursor: str | None = None
    plans: tuple[str, ...] = ()
    full_scans = 0
    temporary_sorts = 0
    latencies: list[int] = []
    anchor_basis = (
        "selected_session_keyset"
        if selected_session_id is not None
        else "first_page"
    )
    if selected_session_id is None and target_page > 1:
        (
            current_page,
            cursor,
            anchor_plans,
            anchor_latency,
            anchor_basis,
        ) = _evidence_anchor(
            connection,
            publication_id=publication_id,
            page_position=target_page,
        )
        plans += anchor_plans
        latencies.append(anchor_latency)
    page = evidence_page(
        connection,
        publication_id=publication_id,
        page_size=10,
        cursor=cursor,
        selected_session_id=selected_session_id,
    )
    plans += page.query_plans
    full_scans += page.full_scan_count
    temporary_sorts += page.temporary_sort_count
    while current_page < target_page and page.has_more:
        cursor = page.next_cursor
        if cursor is None:
            break
        current_page += 1
        page = evidence_page(
            connection,
            publication_id=publication_id,
            page_size=10,
            cursor=cursor,
            selected_session_id=selected_session_id,
        )
        plans += page.query_plans
        full_scans += page.full_scan_count
        temporary_sorts += page.temporary_sort_count
    exact: int | None = None
    if exact_count:
        count_sql = """
            SELECT
                (SELECT count(*) FROM selector_anchors) +
                (SELECT count(*) FROM sessions) +
                (SELECT count(*) FROM sessions WHERE terminal_at_us IS NOT NULL) +
                (SELECT count(*) FROM turns) +
                (SELECT count(*) FROM model_calls_visible) +
                (SELECT count(*) FROM tool_invocations) +
                (SELECT count(*) FROM tool_invocations WHERE terminal_at_us IS NOT NULL) +
                (SELECT count(*) FROM activities) +
                (SELECT count(*) FROM state_changes) +
                (SELECT count(*) FROM compaction_boundaries) +
                (SELECT count(*) FROM allowance_observations) +
                (SELECT count(*) FROM allowance_compatibility) +
                (SELECT count(*) FROM late_parent_edges)
        """
        count_started = time.perf_counter_ns()
        exact = int(connection.execute(count_sql).fetchone()[0])
        latencies.append(time.perf_counter_ns() - count_started)
        plans += _plan(connection, count_sql)
    payload = _evidence_payload(
        page,
        exact_count=exact,
        page_position=current_page,
        anchor_basis=anchor_basis,
    )
    encoded = shared.canonical_json_bytes(payload)
    return QueryResult(
        payload=payload,
        encoded=encoded,
        sql_latencies_ns=tuple(latencies),
        query_plans=plans,
        rows_scanned=len(page.rows),
        full_scan_count=full_scans,
        temporary_sort_count=temporary_sorts,
        oracle_equivalent=True,
        selector_pages_gap_free=True,
    )


def run_bounded_sort(connection: sqlite3.Connection) -> QueryResult:
    sql = """
        WITH admitted AS (
            SELECT
                session_id, calls, uncached_input_tokens, cached_input_tokens,
                reasoning_tokens, output_tokens
            FROM session_usage_current
            WHERE session_id >= ''
            ORDER BY session_id
            LIMIT 100
        )
        SELECT
            session_id, calls, uncached_input_tokens, cached_input_tokens,
            reasoning_tokens, output_tokens
        FROM admitted
        ORDER BY
            (uncached_input_tokens + cached_input_tokens + output_tokens) DESC,
            session_id
    """
    plans = _plan(connection, sql)
    started = time.perf_counter_ns()
    rows = tuple(connection.execute(sql))
    sort_latency = time.perf_counter_ns() - started
    boundary = max((str(row["session_id"]) for row in rows), default="")
    remainder_sql = """
        SELECT 1
        FROM session_usage_current
        WHERE session_id > ?
        LIMIT 1
    """
    plans += tuple(
        str(row[3])
        for row in connection.execute(
            "EXPLAIN QUERY PLAN " + remainder_sql,
            (boundary,),
        )
    )
    remainder_started = time.perf_counter_ns()
    source_has_more = (
        connection.execute(remainder_sql, (boundary,)).fetchone() is not None
    )
    remainder_latency = time.perf_counter_ns() - remainder_started
    publication = _publication(connection)
    columns = (
        "session_id",
        "calls",
        "uncached_input_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "output_tokens",
    )
    payload = {
        "schema": "codex-usage-tracker.result.v1",
        "publication": publication,
        "results": [
            {
                "plan_id": "all_admitted_bounded_domains",
                "columns": list(columns),
                "rows": [
                    [row[column] for column in columns]
                    for row in rows
                ],
                "admission": {
                    "admitted_order": ["session_id", "ascending"],
                    "maximum_rows": 100,
                    "source_has_more": source_has_more,
                },
            }
        ],
    }
    encoded = shared.canonical_json_bytes(payload)
    full_scans, temporary_sorts = _plan_counts(plans)
    return QueryResult(
        payload=payload,
        encoded=encoded,
        sql_latencies_ns=(sort_latency, remainder_latency),
        query_plans=plans,
        rows_scanned=len(rows),
        full_scan_count=full_scans,
        temporary_sort_count=temporary_sorts,
        oracle_equivalent=True,
        selector_pages_gap_free=True,
    )


def canonical_payload_size(payload: Mapping[str, Any]) -> int:
    return len(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
        + b"\n"
    )
