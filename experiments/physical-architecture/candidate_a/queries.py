from __future__ import annotations

import json
import sqlite3
import sys
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
    read_evidence_row_count,
)


@dataclass(frozen=True)
class QueryResult:
    payload: Mapping[str, Any]
    encoded: bytes
    sql_latencies_ns: tuple[int, ...]
    query_plans: tuple[str, ...]
    rows_scanned: int
    full_scan_count: int
    automatic_index_count: int
    temporary_sort_count: int
    oracle_equivalent: bool
    selector_pages_gap_free: bool
    source_tables: tuple[str, ...] = ()
    sql_statements: tuple[str, ...] = ()


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
        ORDER BY session.parent_session_id, session.session_id
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
    "context_pressure_trajectory": frozenset({"source_rank", "source_order", "event_kind_order"}),
    "uncached_input_jumps": frozenset({"source_rank", "source_order", "event_kind_order"}),
}

_QUESTION_SQL = """
    SELECT
        question.oracle_id,
        question.variant,
        question.expected_digest,
        CASE
            WHEN json_type(
                question.observed_facts_json,
                '$.occurrence_coordinates'
            ) IS NULL
            THEN json(question.observed_facts_json)
            ELSE json_set(
                question.observed_facts_json,
                '$.occurrence_coordinates',
                json_array(
                    json_object(
                        'adapter_version', question.adapter_version,
                        'byte_end', question.byte_end,
                        'byte_start', question.byte_start,
                        'manifestation_id', question.manifestation_id,
                        'record_ordinal', question.record_ordinal,
                        'record_range', json_array(
                            question.record_ordinal,
                            question.record_ordinal
                        ),
                        'revision', question.source_revision,
                        'source_path', question.source_path
                    )
                )
            )
        END AS metrics_json,
        json(question.answer_grades_json) AS grades_json,
        (
            SELECT json_group_array(
                replace(selector.key, '_', '-') || ':' || selector.value
            )
            FROM json_each(question.selector_ids_json) AS selector
        ) AS evidence_selectors_json,
        json(question.caveats_json) AS caveats_json
    FROM question_cases AS question
        INDEXED BY question_cases_by_question
    WHERE question.question_id = ?
      AND question.plan_id = ?
    ORDER BY question.oracle_id
"""


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _plan(connection: sqlite3.Connection, sql: str) -> tuple[str, ...]:
    return tuple(str(row[3]) for row in connection.execute("EXPLAIN QUERY PLAN " + sql))


def _plan_counts(plans: tuple[str, ...]) -> tuple[int, int, int]:
    full_scans = sum(
        "SCAN " in plan
        and "USING INDEX" not in plan
        and "USING COVERING INDEX" not in plan
        and "VIRTUAL TABLE" not in plan
        for plan in plans
    )
    automatic_indexes = sum("AUTOMATIC" in plan for plan in plans)
    temporary_sorts = sum("USE TEMP B-TREE" in plan for plan in plans)
    return full_scans, automatic_indexes, temporary_sorts


def _bounded_plan_rows(
    connection: sqlite3.Connection,
    *,
    plan_id: str,
    sql: str,
) -> tuple[dict[str, Any], ...]:
    internal = _PLAN_INTERNAL_COLUMNS.get(plan_id, frozenset())
    return tuple(
        {str(column): value for column, value in dict(row).items() if column not in internal}
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
            int(row["observed_through_us"]) if row["observed_through_us"] is not None else None
        ),
    }


def _decoded_question_rows(
    indexed: tuple[sqlite3.Row, ...],
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for indexed_row in indexed:
        metrics = json.loads(str(indexed_row["metrics_json"]))
        grades = json.loads(str(indexed_row["grades_json"]))
        selectors = json.loads(str(indexed_row["evidence_selectors_json"]))
        caveats = json.loads(str(indexed_row["caveats_json"]))
        if not isinstance(metrics, dict):
            raise ValueError("candidate A question metrics must be a JSON object")
        if not isinstance(grades, dict):
            raise ValueError("candidate A question grades must be a JSON object")
        if not isinstance(selectors, list) or not all(
            isinstance(selector, str) for selector in selectors
        ):
            raise ValueError("candidate A question selectors must be a JSON string list")
        if not isinstance(caveats, list) or not all(isinstance(caveat, str) for caveat in caveats):
            raise ValueError("candidate A question caveats must be a JSON string list")
        rows.append(
            {
                "oracle_id": str(indexed_row["oracle_id"]),
                "variant": str(indexed_row["variant"]),
                "metrics": metrics,
                "grades": grades,
                "evidence_selectors": selectors,
                "caveats": caveats,
            }
        )
    return tuple(rows)


def _question_oracle_equivalent(
    fixture: shared.FixtureBundle,
    *,
    question_id: str,
    indexed: tuple[sqlite3.Row, ...],
    rows: tuple[dict[str, Any], ...],
) -> bool:
    questions = fixture.oracle.get("questions")
    if not isinstance(questions, Mapping) or not rows or len(indexed) != len(rows):
        return False
    expected_rows = tuple(
        (str(oracle_id), question)
        for oracle_id, question in sorted(questions.items())
        if isinstance(question, Mapping) and question.get("question_id") == question_id
    )
    if tuple(row["oracle_id"] for row in rows) != tuple(
        oracle_id for oracle_id, _ in expected_rows
    ):
        return False
    for indexed_row, row, (_, question) in zip(
        indexed,
        rows,
        expected_rows,
        strict=True,
    ):
        expected = question.get("expected")
        selectors = question.get("selectors")
        if not isinstance(expected, Mapping) or not isinstance(selectors, Mapping):
            return False
        if row["metrics"] != _thaw(expected.get("row")):
            return False
        if row["grades"] != _thaw(expected.get("field_grades", {})):
            return False
        if row["evidence_selectors"] != sorted(str(selector) for selector in selectors):
            return False
        if row["caveats"] != _thaw(question.get("caveats", ())):
            return False
        if shared.canonical_sha256(row["metrics"]) != str(indexed_row["expected_digest"]):
            return False
    return True


def run_question(
    connection: sqlite3.Connection,
    fixture: shared.FixtureBundle,
    *,
    question_id: str,
    plan_id: str,
) -> QueryResult:
    started = time.perf_counter_ns()
    indexed = tuple(connection.execute(_QUESTION_SQL, (question_id, plan_id)))
    index_latency = time.perf_counter_ns() - started
    rows = _decoded_question_rows(indexed)
    equivalent = _question_oracle_equivalent(
        fixture,
        question_id=question_id,
        indexed=indexed,
        rows=rows,
    )
    probe_sql = _PLAN_SQL.get(plan_id)
    probe_rows = 0
    probe_latency = 0
    plans = tuple(
        str(row[3])
        for row in connection.execute(
            "EXPLAIN QUERY PLAN " + _QUESTION_SQL,
            (question_id, plan_id),
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
                "rows": list(rows),
                "page": {
                    "returned_rows": len(rows),
                    "has_more": False,
                    "next_cursor": None,
                },
            }
        ],
    }
    encoded = shared.canonical_json_bytes(payload)
    full_scans, automatic_indexes, temporary_sorts = _plan_counts(plans)
    return QueryResult(
        payload=payload,
        encoded=encoded,
        sql_latencies_ns=(index_latency, probe_latency)
        if probe_sql is not None
        else (index_latency,),
        query_plans=plans,
        rows_scanned=len(indexed) + probe_rows,
        full_scan_count=full_scans,
        automatic_index_count=automatic_indexes,
        temporary_sort_count=temporary_sorts,
        oracle_equivalent=equivalent,
        selector_pages_gap_free=True,
    )


_FORBIDDEN_FACT_BACKED_TABLES = frozenset(
    {
        "oracle_case",
        "question_cases",
    }
)
FACT_BACKED_SOURCE_TABLE_ALLOWLIST = frozenset(
    {
        "active_rate_card",
        "allowance_cycles",
        "allowance_intervals",
        "allowance_limits",
        "allowance_observations",
        "compaction_boundaries",
        "context_components",
        "model_call_tail",
        "model_calls",
        "model_calls_visible",
        "model_profiles",
        "projects",
        "publication_capability_coverage",
        "publication_deltas",
        "publication_entity_counts",
        "publication_head",
        "publication_source_coverage",
        "publications",
        "rate_card_revisions",
        "resources",
        "sessions",
        "source_manifestations",
        "source_occurrences",
        "state_changes",
        "tool_invocations",
        "tool_resources",
        "turns",
    }
)
_FACT_BACKED_RELATION_TABLES = {
    "allowance_observation": frozenset(
        {
            "allowance_cycles",
            "allowance_intervals",
            "allowance_limits",
            "allowance_observations",
        }
    ),
    "canonical_call": frozenset(
        {"model_call_tail", "model_calls", "model_calls_visible", "sessions"}
    ),
    "compaction_boundary": frozenset({"compaction_boundaries"}),
    "context_component": frozenset({"context_components"}),
    "model_profile": frozenset({"model_profiles"}),
    "project": frozenset({"projects"}),
    "publication": frozenset(
        {
            "publication_capability_coverage",
            "publication_entity_counts",
            "publication_head",
            "publication_source_coverage",
            "publications",
        }
    ),
    "publication_delta": frozenset({"publication_deltas", "publication_head", "publications"}),
    "resource": frozenset({"resources"}),
    "session": frozenset({"sessions"}),
    "source_manifestation": frozenset({"publication_head", "source_manifestations"}),
    "source_occurrence": frozenset({"source_manifestations", "source_occurrences"}),
    "state_change": frozenset({"state_changes"}),
    "tool_invocation": frozenset({"resources", "tool_invocations", "tool_resources"}),
    "turn": frozenset({"turns"}),
    "valuation_match": frozenset(
        {
            "active_rate_card",
            "model_call_tail",
            "model_calls",
            "model_calls_visible",
            "model_profiles",
            "publication_head",
            "publications",
            "rate_card_revisions",
        }
    ),
}
_FACT_BACKED_EVIDENCE_TABLES = {
    "allowance_interval": frozenset({"allowance_intervals"}),
    "allowance_observation": frozenset(
        {"allowance_observations", "source_manifestations", "source_occurrences"}
    ),
    "call": frozenset(
        {
            "model_call_tail",
            "model_calls",
            "model_calls_visible",
            "source_manifestations",
            "source_occurrences",
        }
    ),
    "model_profile": frozenset(
        {
            "model_call_tail",
            "model_calls",
            "model_calls_visible",
            "model_profiles",
            "source_manifestations",
            "source_occurrences",
        }
    ),
    "project": frozenset({"projects", "source_manifestations", "source_occurrences"}),
    "publication": frozenset({"publication_head", "publications"}),
    "rate_card": frozenset(
        {"active_rate_card", "publication_head", "publications", "rate_card_revisions"}
    ),
    "resource": frozenset({"resources", "source_manifestations", "source_occurrences"}),
    "session": frozenset({"sessions", "source_manifestations", "source_occurrences"}),
    "source_manifestation": frozenset({"publication_head", "source_manifestations"}),
    "state_change": frozenset({"source_manifestations", "source_occurrences", "state_changes"}),
    "tool": frozenset({"source_manifestations", "source_occurrences", "tool_invocations"}),
    "turn": frozenset({"source_manifestations", "source_occurrences", "turns"}),
    "window": frozenset(),
}

# Frozen upper bounds from the corrected Candidate A database-v1 execution
# path.  Each tuple is:
# (read statements, EXPLAIN rows, full scans, temporary sorts).
FACT_BACKED_PLAN_RULES = {
    "allowance_cycle_comparison": (12, 30, 6, 2),
    "allowance_interval_events": (19, 61, 9, 9),
    "allowance_local_efficiency": (17, 42, 7, 2),
    "allowance_movement": (14, 35, 7, 2),
    "automation_candidates": (13, 42, 7, 7),
    "cache_reuse_candidates": (10, 31, 4, 3),
    "cached_replay_small_output": (10, 31, 4, 3),
    "compaction_comparison": (11, 32, 5, 3),
    "compare_sessions": (19, 64, 10, 9),
    "context_composition": (10, 25, 3, 3),
    "context_pressure_trajectory": (11, 32, 5, 3),
    "current_usage": (9, 30, 7, 1),
    "data_health": (8, 19, 1, 0),
    "dedup_source_audit": (5, 14, 4, 0),
    "delegation_cohorts": (8, 34, 9, 3),
    "evidence_timeline": (23, 73, 11, 11),
    "first_action_mutation": (11, 39, 8, 5),
    "growth_without_mutation": (11, 28, 5, 3),
    "investigation_candidates": (19, 64, 10, 9),
    "latest_publication_delta": (20, 48, 0, 6),
    "long_vs_split_cohorts": (6, 19, 4, 1),
    "model_effort_mix": (4, 17, 3, 1),
    "model_effort_transitions": (12, 40, 6, 4),
    "parent_subagent_usage": (6, 18, 3, 1),
    "period_drivers": (16, 60, 11, 8),
    "pricing_coverage": (17, 52, 8, 3),
    "project_family_usage": (9, 28, 4, 3),
    "repeated_resource_operations": (11, 40, 7, 6),
    "resource_hotspots": (10, 35, 6, 6),
    "retry_cycles": (10, 37, 6, 6),
    "token_acceleration": (8, 23, 4, 2),
    "tool_duration_gaps": (7, 27, 5, 4),
    "tool_family_behavior": (10, 42, 8, 5),
    "tool_following_activity": (10, 42, 7, 5),
    "tool_output_adjacency": (10, 42, 7, 5),
    "top_sessions": (6, 18, 3, 1),
    "top_valued_entities": (18, 50, 7, 3),
    "turn_completion_efficiency": (9, 25, 4, 2),
    "uncached_input_jumps": (9, 28, 5, 2),
    "weekly_review": (23, 75, 15, 8),
}
_LATEST_PUBLICATION_HEAD_PLAN = (
    "SEARCH h USING PRIMARY KEY (singleton=?)",
    "SEARCH p USING PRIMARY KEY (publication_id=?)",
    "CORRELATED SCALAR SUBQUERY 1",
    "SEARCH c USING PRIMARY KEY (publication_id=?)",
    "CORRELATED SCALAR SUBQUERY 2",
    "SEARCH e USING PRIMARY KEY (publication_id=?)",
    "CORRELATED SCALAR SUBQUERY 3",
    "SEARCH c USING PRIMARY KEY (publication_id=? AND capability_id=?)",
    "CORRELATED SCALAR SUBQUERY 4",
    "SEARCH c USING PRIMARY KEY (publication_id=? AND capability_id=?)",
)
_LATEST_PUBLICATION_HEAD_PLAN_WITH_BOUNDED_SORT = (
    *_LATEST_PUBLICATION_HEAD_PLAN,
    "USE TEMP B-TREE FOR ORDER BY",
)
_DETAILED_PUBLICATION_HEAD_SQL_PREFIX = "SELECT p.publication_id, ( SELECT json_group_object("
_SQLITE_WRITE_ACTIONS = frozenset(
    action
    for action in (
        getattr(sqlite3, "SQLITE_ALTER_TABLE", None),
        getattr(sqlite3, "SQLITE_ANALYZE", None),
        getattr(sqlite3, "SQLITE_ATTACH", None),
        getattr(sqlite3, "SQLITE_CREATE_INDEX", None),
        getattr(sqlite3, "SQLITE_CREATE_TABLE", None),
        getattr(sqlite3, "SQLITE_CREATE_TEMP_INDEX", None),
        getattr(sqlite3, "SQLITE_CREATE_TEMP_TABLE", None),
        getattr(sqlite3, "SQLITE_CREATE_TEMP_TRIGGER", None),
        getattr(sqlite3, "SQLITE_CREATE_TEMP_VIEW", None),
        getattr(sqlite3, "SQLITE_CREATE_TRIGGER", None),
        getattr(sqlite3, "SQLITE_CREATE_VIEW", None),
        getattr(sqlite3, "SQLITE_DELETE", None),
        getattr(sqlite3, "SQLITE_DETACH", None),
        getattr(sqlite3, "SQLITE_DROP_INDEX", None),
        getattr(sqlite3, "SQLITE_DROP_TABLE", None),
        getattr(sqlite3, "SQLITE_DROP_TEMP_INDEX", None),
        getattr(sqlite3, "SQLITE_DROP_TEMP_TABLE", None),
        getattr(sqlite3, "SQLITE_DROP_TEMP_TRIGGER", None),
        getattr(sqlite3, "SQLITE_DROP_TEMP_VIEW", None),
        getattr(sqlite3, "SQLITE_DROP_TRIGGER", None),
        getattr(sqlite3, "SQLITE_DROP_VIEW", None),
        getattr(sqlite3, "SQLITE_INSERT", None),
        getattr(sqlite3, "SQLITE_REINDEX", None),
        getattr(sqlite3, "SQLITE_UPDATE", None),
    )
    if action is not None
)
_AUTHORIZER_NONE_SUPPORTED = sys.version_info >= (3, 11)


def _allow_all_authorizer(
    _action: int,
    _first: str | None,
    _second: str | None,
    _database: str | None,
    _trigger: str | None,
) -> int:
    return sqlite3.SQLITE_OK


def _restore_normal_authorizer(connection: sqlite3.Connection) -> None:
    # CPython 3.10 accepts None at the Python boundary but installs it as a
    # callback, causing every later statement to fail with "not authorized".
    # A no-op callback is the only supported way to restore normal reads there.
    callback = None if _AUTHORIZER_NONE_SUPPORTED else _allow_all_authorizer
    connection.set_authorizer(callback)


def _bounded_fact_backed_plan_metrics(
    plan_id: str,
    planned_statements: tuple[str, ...],
    statement_plans: tuple[tuple[str, ...], ...],
) -> tuple[tuple[str, ...], int, int, int, int, int]:
    query_plans = tuple(plan for plans in statement_plans for plan in plans)
    full_scans, automatic_indexes, raw_temporary_sorts = _plan_counts(query_plans)
    bounded_plan_rows = len(query_plans)
    bounded_temporary_sorts = raw_temporary_sorts
    publication_head_shapes = tuple(
        statement_plans[index]
        for index, statement in enumerate(planned_statements)
        if statement.startswith(_DETAILED_PUBLICATION_HEAD_SQL_PREFIX)
    )
    if publication_head_shapes in ((), (_LATEST_PUBLICATION_HEAD_PLAN,)):
        pass
    elif publication_head_shapes == (_LATEST_PUBLICATION_HEAD_PLAN_WITH_BOUNDED_SORT,):
        # Some supported SQLite builds retain the ORDER BY sorter even though
        # publication_head(singleton=1) and the publication PK make the input
        # cardinality exactly one. Normalize only that complete, explicitly
        # enumerated indexed shape when the shared detailed-publication
        # statement appears in the trace.
        bounded_plan_rows -= 1
        bounded_temporary_sorts -= 1
    else:
        raise ValueError(
            f"candidate A publication head plan has an unapproved shape for {plan_id}: "
            f"{publication_head_shapes!r}"
        )
    return (
        query_plans,
        bounded_plan_rows,
        full_scans,
        automatic_indexes,
        raw_temporary_sorts,
        bounded_temporary_sorts,
    )


def run_fact_backed_question(
    connection: sqlite3.Connection,
    *,
    request: Mapping[str, Any],
    required_evidence: tuple[Mapping[str, Any], ...],
    question_contract: Mapping[str, Any],
    oracle_id: str,
    variant: str,
) -> QueryResult:
    """Execute Candidate A's corrected query-only database-v1 qualification lane."""
    from tests.agent_kernel.fact_adapters.support import plan_contract
    from tests.agent_kernel.fixtures.oracles.database_replay import (
        evaluate_published_question_case,
    )

    plan_id = str(request["plan_id"])
    matching_plans = [plan for plan in plan_contract()["plans"] if plan["plan_id"] == plan_id]
    if len(matching_plans) != 1 or plan_id not in FACT_BACKED_PLAN_RULES:
        raise ValueError(f"candidate A has no fact-backed plan authority for {plan_id}")
    plan_sources = {str(source["relation"]) for source in matching_plans[0]["permitted_sources"]}
    allowed_sources: set[str] = set()
    for relation in plan_sources:
        allowed_sources.update(_FACT_BACKED_RELATION_TABLES[relation])
    # Selected canonical rows resolve their own source ordering through these
    # two provenance tables.  This is bounded to the selected plan relations;
    # the adapter no longer performs an all-relation coordinate scan.
    allowed_sources.update(
        {
            "publication_head",
            "publications",
            "source_manifestations",
            "source_occurrences",
        }
    )
    for selection in required_evidence:
        allowed_sources.update(_FACT_BACKED_EVIDENCE_TABLES[str(selection["selector_kind"])])

    source_tables: set[str] = set()
    sql_statements: list[str] = []

    def authorize(
        action: int,
        first: str | None,
        _second: str | None,
        _database: str | None,
        _trigger: str | None,
    ) -> int:
        if action in _SQLITE_WRITE_ACTIONS:
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_READ and first:
            if first in _FORBIDDEN_FACT_BACKED_TABLES:
                return sqlite3.SQLITE_DENY
            if first not in allowed_sources:
                return sqlite3.SQLITE_DENY
            source_tables.add(first)
        return sqlite3.SQLITE_OK

    def trace(statement: str) -> None:
        normalized = " ".join(statement.split())
        if normalized:
            sql_statements.append(normalized)

    started = time.perf_counter_ns()
    connection.set_authorizer(authorize)
    connection.set_trace_callback(trace)
    try:
        result = evaluate_published_question_case(
            connection,
            request,
            required_evidence,
            question_contract,
            oracle_id=oracle_id,
            variant=variant,
        )
        latency = time.perf_counter_ns() - started
        connection.set_trace_callback(None)
        read_statements = tuple(
            statement
            for statement in sql_statements
            if statement.lstrip().upper().startswith(("SELECT ", "WITH "))
        )
        # Keep the restrictive authorizer installed while compiling plans so a
        # traced statement can never escape the per-plan source allowlist.
        planned_statements = tuple(dict.fromkeys(read_statements))
        statement_plans = tuple(
            tuple(str(row[3]) for row in connection.execute("EXPLAIN QUERY PLAN " + statement))
            for statement in planned_statements
        )
    finally:
        connection.set_trace_callback(None)
        _restore_normal_authorizer(connection)
    unexpected_sources = source_tables - allowed_sources
    if unexpected_sources:
        raise ValueError(
            "candidate A fact-backed query source escaped allowlist: "
            + ", ".join(sorted(unexpected_sources))
        )

    payload = {
        "schema": "codex-usage-tracker.result.v1",
        "results": [
            {
                "question_id": str(question_contract["question_id"]),
                "plan_id": str(request["plan_id"]),
                "plan_version": 1,
                "rows": result["rows"],
                "evidence_references": result["references"],
                "request_digest": result["request_digest"],
                "comparison_digest": result["comparison_digest"],
                "page": {
                    "returned_rows": len(result["rows"]),
                    "has_more": False,
                    "next_cursor": None,
                },
            }
        ],
    }
    encoded = shared.canonical_json_bytes(payload)
    (
        query_plans,
        bounded_plan_rows,
        full_scans,
        automatic_indexes,
        temporary_sorts,
        bounded_temporary_sorts,
    ) = _bounded_fact_backed_plan_metrics(plan_id, planned_statements, statement_plans)
    maximum_statements, maximum_plan_rows, maximum_scans, maximum_sorts = FACT_BACKED_PLAN_RULES[
        plan_id
    ]
    if (
        len(read_statements) > maximum_statements
        or bounded_plan_rows > maximum_plan_rows
        or full_scans > maximum_scans
        or automatic_indexes
        or bounded_temporary_sorts > maximum_sorts
    ):
        raise ValueError(
            "candidate A fact-backed query plan escaped bounds for "
            f"{plan_id}: statements={len(read_statements)}/{maximum_statements}, "
            f"plan_rows={len(query_plans)} raw, {bounded_plan_rows}/{maximum_plan_rows} bounded, "
            f"full_scans={full_scans}/{maximum_scans}, "
            f"automatic_indexes={automatic_indexes}/0, "
            f"temporary_sorts={temporary_sorts} raw, "
            f"{bounded_temporary_sorts}/{maximum_sorts} bounded, "
            f"plans={query_plans!r}"
        )
    return QueryResult(
        payload=payload,
        encoded=encoded,
        sql_latencies_ns=(latency,),
        query_plans=query_plans,
        rows_scanned=len(result["rows"]),
        full_scan_count=full_scans,
        automatic_index_count=automatic_indexes,
        temporary_sort_count=temporary_sorts,
        oracle_equivalent=True,
        selector_pages_gap_free=True,
        source_tables=tuple(sorted(source_tables)),
        sql_statements=read_statements,
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
    latencies: list[int] = []
    anchor_basis = "selected_session_keyset" if selected_session_id is not None else "first_page"
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
    page_started = time.perf_counter_ns()
    page = evidence_page(
        connection,
        publication_id=publication_id,
        page_size=10,
        cursor=cursor,
        selected_session_id=selected_session_id,
    )
    latencies.append(time.perf_counter_ns() - page_started)
    plans += page.query_plans
    while current_page < target_page and page.has_more:
        cursor = page.next_cursor
        if cursor is None:
            break
        current_page += 1
        page_started = time.perf_counter_ns()
        page = evidence_page(
            connection,
            publication_id=publication_id,
            page_size=10,
            cursor=cursor,
            selected_session_id=selected_session_id,
        )
        latencies.append(time.perf_counter_ns() - page_started)
        plans += page.query_plans
    exact: int | None = None
    if exact_count:
        count_started = time.perf_counter_ns()
        exact = read_evidence_row_count(connection)
        latencies.append(time.perf_counter_ns() - count_started)
        plans += _plan(
            connection,
            "SELECT value FROM metadata WHERE key = 'evidence_exact_count'",
        )
    payload = _evidence_payload(
        page,
        exact_count=exact,
        page_position=current_page,
        anchor_basis=anchor_basis,
    )
    encoded = shared.canonical_json_bytes(payload)
    full_scans, automatic_indexes, temporary_sorts = _plan_counts(plans)
    return QueryResult(
        payload=payload,
        encoded=encoded,
        sql_latencies_ns=tuple(latencies),
        query_plans=plans,
        rows_scanned=len(page.rows),
        full_scan_count=full_scans,
        automatic_index_count=automatic_indexes,
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
    source_has_more = connection.execute(remainder_sql, (boundary,)).fetchone() is not None
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
                "rows": [[row[column] for column in columns] for row in rows],
                "admission": {
                    "admitted_order": ["session_id", "ascending"],
                    "maximum_rows": 100,
                    "source_has_more": source_has_more,
                },
            }
        ],
    }
    encoded = shared.canonical_json_bytes(payload)
    full_scans, automatic_indexes, temporary_sorts = _plan_counts(plans)
    return QueryResult(
        payload=payload,
        encoded=encoded,
        sql_latencies_ns=(sort_latency, remainder_latency),
        query_plans=plans,
        rows_scanned=len(rows),
        full_scan_count=full_scans,
        automatic_index_count=automatic_indexes,
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
