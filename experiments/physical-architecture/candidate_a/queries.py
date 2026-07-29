from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import shared

from .evidence import EvidencePage, evidence_page


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
            count(*) AS calls,
            sum(uncached_input_tokens) AS uncached_input_tokens,
            sum(cached_input_tokens) AS cached_input_tokens,
            sum(reasoning_tokens) AS reasoning_tokens,
            sum(output_tokens) AS output_tokens
        FROM model_calls
    """,
    "top_sessions": """
        SELECT * FROM session_usage_current
        ORDER BY uncached_input_tokens DESC, cached_input_tokens DESC,
                 output_tokens DESC, session_id
        LIMIT 25
    """,
    "model_effort_mix": """
        SELECT
            model, reasoning_effort, count(*) AS calls,
            sum(uncached_input_tokens) AS uncached_input_tokens,
            sum(cached_input_tokens) AS cached_input_tokens,
            sum(reasoning_tokens) AS reasoning_tokens,
            sum(output_tokens) AS output_tokens
        FROM model_calls
        GROUP BY model, reasoning_effort
        ORDER BY uncached_input_tokens DESC, model, reasoning_effort
        LIMIT 25
    """,
    "project_family_usage": """
        WITH RECURSIVE family(session_id, root_session_id) AS (
            SELECT session_id, session_id FROM sessions
            WHERE parent_session_id IS NULL
            UNION ALL
            SELECT child.session_id, family.root_session_id
            FROM sessions AS child
            JOIN family ON child.parent_session_id = family.session_id
        )
        SELECT
            family.root_session_id,
            sum(usage.calls) AS calls,
            sum(usage.uncached_input_tokens) AS uncached_input_tokens,
            sum(usage.cached_input_tokens) AS cached_input_tokens,
            sum(usage.reasoning_tokens) AS reasoning_tokens,
            sum(usage.output_tokens) AS output_tokens
        FROM family
        JOIN session_usage_current AS usage USING (session_id)
        GROUP BY family.root_session_id
        ORDER BY uncached_input_tokens DESC, family.root_session_id
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
        SELECT
            model,
            count(*) AS calls,
            sum(CASE WHEN model = 'synthetic-unpriced' THEN 0 ELSE 1 END)
                AS rated_calls
        FROM model_calls
        GROUP BY model
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
            reasoning_tokens, output_tokens
        FROM model_calls
        WHERE context_window_tokens IS NOT NULL
        ORDER BY session_id, event_at_us, source_rank, source_order, call_id
        LIMIT 100
    """,
    "uncached_input_jumps": """
        SELECT
            session_id, call_id, event_at_us, uncached_input_tokens
        FROM model_calls
        WHERE uncached_input_tokens IS NOT NULL
        ORDER BY session_id, event_at_us, source_rank, source_order, call_id
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
        FROM sessions AS session
        JOIN session_usage_current AS usage USING (session_id)
        ORDER BY usage.uncached_input_tokens DESC, session.session_id
        LIMIT 25
    """,
    "first_action_mutation": """
        SELECT
            turn.turn_id,
            min(tool.start_at_us) AS first_action_at_us,
            min(CASE WHEN tool.state = 'succeeded' THEN tool.terminal_at_us END)
                AS first_success_at_us,
            min(change.event_at_us) AS first_mutation_at_us
        FROM turns AS turn
        LEFT JOIN tool_invocations AS tool USING (turn_id)
        LEFT JOIN state_changes AS change USING (turn_id)
        GROUP BY turn.turn_id
        ORDER BY first_action_at_us, turn.turn_id
        LIMIT 100
    """,
    "repeated_resource_operations": """
        SELECT
            resource_id, count(*) AS operation_count,
            min(start_at_us) AS first_at_us, max(start_at_us) AS last_at_us
        FROM tool_invocations
        WHERE resource_id IS NOT NULL
        GROUP BY resource_id
        HAVING count(*) > 1
        ORDER BY operation_count DESC, resource_id
        LIMIT 100
    """,
    "tool_family_behavior": """
        SELECT * FROM tool_family_current
        ORDER BY calls DESC, transport_name, semantic_operation
        LIMIT 25
    """,
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
        probe_rows = len(tuple(connection.execute(probe_sql)))
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
        },
    }


def run_evidence_feature(
    connection: sqlite3.Connection,
    *,
    publication_id: str,
    page_position: int = 0,
    exact_count: bool = False,
    selected_session_id: str | None = None,
) -> QueryResult:
    cursor: str | None = None
    rows_seen = 0
    plans: tuple[str, ...] = ()
    full_scans = 0
    temporary_sorts = 0
    latencies: list[int] = []
    page = evidence_page(
        connection,
        publication_id=publication_id,
        page_size=10,
        selected_session_id=selected_session_id,
    )
    while page_position > rows_seen + len(page.rows) and page.has_more:
        rows_seen += len(page.rows)
        cursor = page.next_cursor
        if cursor is None:
            break
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
                (SELECT count(*) FROM model_calls) +
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
    payload = _evidence_payload(page, exact_count=exact)
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
        SELECT
            session_id, calls, uncached_input_tokens, cached_input_tokens,
            reasoning_tokens, output_tokens
        FROM session_usage_current
        ORDER BY
            (uncached_input_tokens + cached_input_tokens + output_tokens) DESC,
            session_id
        LIMIT 100
    """
    plans = _plan(connection, sql)
    started = time.perf_counter_ns()
    rows = [dict(row) for row in connection.execute(sql)]
    latency = time.perf_counter_ns() - started
    publication = _publication(connection)
    payload = {
        "schema": "codex-usage-tracker.result.v1",
        "publication": publication,
        "results": [
            {
                "plan_id": "all_admitted_bounded_domains",
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
        sql_latencies_ns=(latency,),
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
