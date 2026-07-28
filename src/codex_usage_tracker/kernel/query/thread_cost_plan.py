"""Compile the bounded logical-thread cost rollup plan."""

from __future__ import annotations

from typing import Any, TypedDict

from .contracts import Operation, QueryRequest


class CompiledPlanParts(TypedDict):
    """Arguments required to construct the public compiled-plan value."""

    plan_id: str
    sql: str
    count_sql: str
    scan_sql: str
    coverage_sql: str | None
    parameters: tuple[Any, ...]
    count_parameters: tuple[Any, ...]
    scan_parameters: tuple[Any, ...]
    coverage_parameters: tuple[Any, ...]
    offset: int


def compile_thread_cost_plan(
    request: QueryRequest,
    *,
    generation: int,
    offset: int,
    plan_version: int,
) -> CompiledPlanParts | None:
    """Return the ranked-thread cost plan when the request is eligible."""

    if not _is_supported_request(request):
        return None
    selected = [
        "ranked_threads.thread AS thread",
        (
            "resolved_thread_label("
            "canonical_threads.session_identity_hash, "
            "canonical_threads.display_label) AS thread_label"
        ),
        *(_MEASURE_SQL[measure] for measure in request.measures),
        "ranked_threads.matched_count AS __matched_count",
        "ranked_threads.scanned_count AS __scanned_count",
    ]
    return CompiledPlanParts(
        plan_id=f"calls.aggregate.rollup_thread_cost.v{plan_version}",
        sql=_result_sql(selected),
        count_sql=_GROUPED_COUNT_SQL,
        scan_sql=_SCAN_SQL,
        coverage_sql=_coverage_sql(request.measures),
        parameters=(
            generation,
            request.limit + 1,
            offset,
            generation,
            generation,
        ),
        count_parameters=(generation,),
        scan_parameters=(generation,),
        coverage_parameters=(generation,),
        offset=offset,
    )


def _is_supported_request(request: QueryRequest) -> bool:
    requested_measures = set(request.measures)
    return (
        request.dataset == "calls"
        and Operation(request.operation) is Operation.AGGREGATE
        and request.dimensions == ("thread",)
        and not request.filters
        and request.comparison is None
        and request.descending is True
        and (request.order_by or "total_tokens") == "total_tokens"
        and requested_measures.issubset(_MEASURE_SQL)
        and bool(
            requested_measures.intersection(
                {"configured_cost_usd", "estimated_credits"}
            )
        )
    )


def _coverage_sql(measures: tuple[str, ...]) -> str:
    selected = ["SUM(calls) AS coverage_total"]
    for measure in measures:
        expression = _COVERAGE_FIELDS.get(measure)
        if expression is None:
            continue
        selected.extend(
            (
                (
                    f"SUM(CASE WHEN {expression} IS NOT NULL "
                    f"THEN calls ELSE 0 END) AS observed_{measure}"
                ),
                (
                    f"SUM(CASE WHEN {expression} IS NULL "
                    f"THEN calls ELSE 0 END) AS missing_{measure}"
                ),
            )
        )
    return (
        f"SELECT {', '.join(selected)} "
        "FROM rollup_model_effort WHERE generation = ?"
    )


def _result_sql(selected: list[str]) -> str:
    return (
        f"{_RANKED_THREADS_SQL} SELECT {', '.join(selected)} "
        "FROM ranked_threads "
        "JOIN canonical_threads "
        "ON canonical_threads.logical_thread_id = ranked_threads.thread "
        "AND canonical_threads.canonical_rank = 1 "
        "JOIN threads AS physical_threads "
        "ON physical_threads.logical_thread_id = ranked_threads.thread "
        "JOIN model_call_facts AS facts INDEXED BY idx_model_calls_thread_time "
        "ON facts.thread_key = physical_threads.thread_key "
        "JOIN model_profiles AS profiles "
        "ON profiles.model_profile_key = facts.model_profile_key "
        "WHERE facts.generation <= ? "
        "AND facts.duplicate_state = 'canonical' "
        "GROUP BY ranked_threads.thread, canonical_threads.logical_thread_id "
        "ORDER BY total_tokens DESC, thread"
    )


_MEASURE_SQL = {
    "total_tokens": "ranked_threads.total_tokens AS total_tokens",
    "configured_cost_usd": (
        "SUM(configured_cost_usd("
        "profiles.model, facts.input_tokens, "
        "facts.cached_input_tokens, facts.output_tokens"
        ")) AS configured_cost_usd"
    ),
    "estimated_credits": (
        "SUM(estimated_credits("
        "profiles.model, facts.input_tokens, "
        "facts.cached_input_tokens, facts.output_tokens"
        ")) AS estimated_credits"
    ),
}

_COVERAGE_FIELDS = {
    "configured_cost_usd": (
        "configured_cost_usd("
        "model, input_tokens, cached_input_tokens, output_tokens)"
    ),
    "estimated_credits": (
        "estimated_credits("
        "model, input_tokens, cached_input_tokens, output_tokens)"
    ),
}

_RANKED_THREADS_SQL = """
    WITH grouped_threads AS (
        SELECT threads.logical_thread_id AS thread,
               SUM(rollup.calls) AS calls,
               SUM(rollup.input_tokens) + SUM(rollup.output_tokens) AS total_tokens
        FROM rollup_thread AS rollup
        JOIN threads USING (thread_key)
        WHERE rollup.generation = ?
        GROUP BY threads.logical_thread_id
    ),
    ranked_threads AS (
        SELECT grouped_threads.*,
               COUNT(*) OVER () AS matched_count,
               SUM(calls) OVER () AS scanned_count
        FROM grouped_threads
        ORDER BY total_tokens DESC, thread
        LIMIT ? OFFSET ?
    ),
    canonical_threads AS (
        SELECT threads.logical_thread_id,
               threads.session_identity_hash,
               threads.display_label,
               ROW_NUMBER() OVER (
                   PARTITION BY threads.logical_thread_id
                   ORDER BY threads.archive_state = 'active' DESC,
                            threads.last_generation DESC,
                            threads.thread_key
               ) AS canonical_rank
        FROM threads
        WHERE threads.first_generation <= ?
    )
"""

_GROUPED_COUNT_SQL = (
    "SELECT COUNT(*) FROM ("
    "SELECT 1 FROM rollup_thread AS rollup "
    "JOIN threads USING (thread_key) "
    "WHERE rollup.generation = ? "
    "GROUP BY threads.logical_thread_id"
    ") AS grouped"
)

_SCAN_SQL = (
    "SELECT COALESCE(SUM(calls), 0) "
    "FROM rollup_thread WHERE generation = ?"
)
