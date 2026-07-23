"""Live usage API read queries."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, TypedDict

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.home_queries import query_home_usage_metrics
from codex_usage_tracker.store.query_sql import (
    normalize_limit,
    normalize_offset,
    normalize_sort_direction,
    render_sql_template,
    usage_api_sort_expression,
    usage_api_where_clause,
)
from codex_usage_tracker.store.rows import usage_row_to_dict
from codex_usage_tracker.store.schema import init_db
from codex_usage_tracker.store.usage_timing import (
    USAGE_TIMING_JOIN_SQL,
    USAGE_TIMING_SELECT_SQL,
    usage_parent_select_sql,
)

_MATERIALIZED_SORT_INDEXES = {
    "attention": "idx_recommendation_facts_attention_sort",
    "cost": "idx_recommendation_facts_cost_sort",
    "credits": "idx_recommendation_facts_credits_sort",
    "context": "idx_recommendation_facts_context_sort",
}


class _UsageApiFilterKwargs(TypedDict):
    search: str | None
    since: str | None
    until: str | None
    model: str | None
    effort: str | None
    source: str | None
    cwds: Sequence[str] | None
    thread: str | None
    thread_key: str | None
    include_archived: bool
    table_alias: str | None
    legacy_archive_path_fallback: bool


class _UsageApiCountFilterKwargs(TypedDict):
    search: str | None
    since: str | None
    until: str | None
    model: str | None
    effort: str | None
    source: str | None
    cwds: Sequence[str] | None
    thread: str | None
    thread_key: str | None
    include_archived: bool
    table_alias: str | None
    legacy_archive_path_fallback: bool


def query_usage_api_events(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    limit: int | None = 100,
    offset: int = 0,
    search: str | None = None,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    source: str | None = None,
    cwds: Sequence[str] | None = None,
    thread: str | None = None,
    thread_key: str | None = None,
    include_archived: bool = False,
    sort: str = "time",
    direction: str = "desc",
    pricing_status: str | None = None,
    credit_confidence: str | None = None,
    legacy_archive_path_fallback: bool = True,
) -> list[dict[str, Any]]:
    """Return SQL-backed live dashboard call API rows."""

    filter_kwargs: _UsageApiFilterKwargs = {
        "search": search,
        "since": since,
        "until": until,
        "model": model,
        "effort": effort,
        "source": source,
        "cwds": cwds,
        "thread": thread,
        "thread_key": thread_key,
        "include_archived": include_archived,
        "table_alias": "usage_events",
        "legacy_archive_path_fallback": legacy_archive_path_fallback,
    }
    order_expr = usage_api_sort_expression(sort)
    direction_sql = normalize_sort_direction(direction)
    normalized_limit = normalize_limit(limit)
    normalized_offset = normalize_offset(offset)
    materialized_sort_index = _MATERIALIZED_SORT_INDEXES.get(sort)
    if sort == "attention" and not include_archived:
        materialized_sort_index = "idx_recommendation_facts_scope"
    fact_filter_clauses, fact_filter_params = _recommendation_fact_filters(
        pricing_status=pricing_status,
        credit_confidence=credit_confidence,
    )
    fact_filter_index = _recommendation_fact_filter_index(
        pricing_status=pricing_status,
        credit_confidence=credit_confidence,
    )
    fact_source_index = materialized_sort_index or (fact_filter_index if sort == "time" else None)
    if fact_source_index is not None and sort == "time":
        order_expr = "recommendation_facts.event_timestamp"
    order_tail = (
        "recommendation_facts.event_timestamp DESC, recommendation_facts.record_id"
        if fact_source_index is not None
        else "usage_events.event_timestamp DESC, usage_events.cumulative_total_tokens DESC"
    )
    needs_fact_join = fact_source_index is not None or bool(fact_filter_clauses)
    usage_source = "canonical_usage_events AS usage_events"
    limit_clause = ""
    if thread_key and normalized_limit is not None and fact_source_index is None:
        candidate_limit = normalized_limit + normalized_offset
        indexed_where, indexed_params = usage_api_where_clause(
            **filter_kwargs,
            thread_key_mode="indexed",
        )
        legacy_where, legacy_params = usage_api_where_clause(
            **filter_kwargs,
            thread_key_mode="legacy",
        )
        where_clause = render_sql_template(
            """
            WHERE usage_events.record_id IN (
                SELECT record_id FROM (
                    SELECT usage_events.record_id
                    FROM usage_events AS usage_events
                        INDEXED BY idx_usage_thread_key_timestamp
                    $timing_join
                    $indexed_where
                        AND usage_events.is_duplicate = 0
                    ORDER BY $order_expr $direction,
                        usage_events.event_timestamp DESC,
                        usage_events.cumulative_total_tokens DESC
                    LIMIT ?
                ) AS indexed_thread_rows
                UNION ALL
                SELECT record_id FROM (
                    SELECT usage_events.record_id
                    FROM usage_events AS usage_events
                        INDEXED BY idx_canonical_usage_legacy_thread
                    $timing_join
                    $legacy_where
                        AND usage_events.is_duplicate = 0
                    ORDER BY $order_expr $direction,
                        usage_events.event_timestamp DESC,
                        usage_events.cumulative_total_tokens DESC
                    LIMIT ?
                ) AS legacy_thread_rows
            )
            """,
            {
                "timing_join": USAGE_TIMING_JOIN_SQL,
                "indexed_where": indexed_where,
                "legacy_where": legacy_where,
                "order_expr": order_expr,
                "direction": direction_sql,
            },
        )
        where_clause += "\nAND usage_events.is_duplicate = 0"
        usage_source = "usage_events AS usage_events INDEXED BY idx_canonical_usage_record_id"
        query_params = [
            *indexed_params,
            candidate_limit,
            *legacy_params,
            candidate_limit,
        ]
    else:
        where_clause, params = usage_api_where_clause(**filter_kwargs)
        query_params = list(params)
        if not legacy_archive_path_fallback:
            usage_source = (
                "usage_events AS usage_events INDEXED BY idx_canonical_usage_archived_timestamp"
            )
            where_clause = (
                f"{where_clause} AND usage_events.is_duplicate = 0"
                if where_clause
                else "WHERE usage_events.is_duplicate = 0"
            )
        if fact_source_index is not None:
            usage_source = (
                "recommendation_facts AS recommendation_facts "
                f"INDEXED BY {fact_source_index} "
                "JOIN usage_events AS usage_events "
                "INDEXED BY idx_canonical_usage_record_id "
                "ON usage_events.record_id = recommendation_facts.record_id"
            )
            where_clause = (
                f"{where_clause} AND usage_events.is_duplicate = 0"
                if where_clause
                else "WHERE usage_events.is_duplicate = 0"
            )
            if not include_archived:
                where_clause += " AND recommendation_facts.is_archived = 0"
        elif needs_fact_join:
            usage_source += (
                " JOIN recommendation_facts AS recommendation_facts "
                "ON recommendation_facts.record_id = usage_events.record_id"
            )
        if fact_filter_clauses:
            fact_filter_sql = " AND ".join(fact_filter_clauses)
            where_clause = (
                f"{where_clause} AND {fact_filter_sql}"
                if where_clause
                else f"WHERE {fact_filter_sql}"
            )
            query_params.extend(fact_filter_params)
    if normalized_limit is not None:
        limit_clause = "LIMIT ?"
        query_params.append(normalized_limit)
        if normalized_offset:
            limit_clause += " OFFSET ?"
            query_params.append(normalized_offset)
    elif normalized_offset:
        limit_clause = "LIMIT -1 OFFSET ?"
        query_params.append(normalized_offset)

    with connect(db_path) as conn:
        init_db(conn)
        query = render_sql_template(
            """
            SELECT
                usage_events.*,
                $timing_select,
                $parent_select
            FROM $usage_source
            $timing_join
            $where_clause
            ORDER BY $order_expr $direction,
                $order_tail
            $limit_clause
            """,
            {
                "timing_select": USAGE_TIMING_SELECT_SQL,
                "parent_select": usage_parent_select_sql(include_archived=include_archived),
                "usage_source": usage_source,
                "timing_join": USAGE_TIMING_JOIN_SQL,
                "where_clause": where_clause,
                "order_expr": order_expr,
                "direction": direction_sql,
                "order_tail": order_tail,
                "limit_clause": limit_clause,
            },
        )
        rows = conn.execute(query, query_params).fetchall()
    return [usage_row_to_dict(row) for row in rows]


def query_usage_api_event_count(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    search: str | None = None,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    source: str | None = None,
    cwds: Sequence[str] | None = None,
    thread: str | None = None,
    thread_key: str | None = None,
    include_archived: bool = False,
    pricing_status: str | None = None,
    credit_confidence: str | None = None,
    legacy_archive_path_fallback: bool = True,
) -> int:
    """Return count for SQL-backed live dashboard call APIs."""

    has_filters = any(
        value
        for value in (
            search,
            since,
            until,
            model,
            effort,
            source,
            cwds,
            thread,
            thread_key,
            pricing_status,
            credit_confidence,
        )
    )
    if not has_filters and not legacy_archive_path_fallback:
        metrics = query_home_usage_metrics(db_path=db_path)
        if metrics is not None:
            key = "materialized_calls" if include_archived else "calls"
            return int(metrics[key])

    filter_kwargs: _UsageApiCountFilterKwargs = {
        "search": search,
        "since": since,
        "until": until,
        "model": model,
        "effort": effort,
        "source": source,
        "cwds": cwds,
        "thread": thread,
        "thread_key": thread_key,
        "include_archived": include_archived,
        "table_alias": "usage_events",
        "legacy_archive_path_fallback": legacy_archive_path_fallback,
    }
    fact_filter_clauses, fact_filter_params = _recommendation_fact_filters(
        pricing_status=pricing_status,
        credit_confidence=credit_confidence,
    )
    fact_filter_index = _recommendation_fact_filter_index(
        pricing_status=pricing_status,
        credit_confidence=credit_confidence,
    )
    with connect(db_path) as conn:
        init_db(conn)
        if (
            fact_filter_clauses
            and fact_filter_index is not None
            and not any((search, source, cwds, thread))
        ):
            fact_clauses = list(fact_filter_clauses)
            fact_params = list(fact_filter_params)
            for value, clause in (
                (since, "recommendation_facts.event_timestamp >= ?"),
                (until, "recommendation_facts.event_timestamp <= ?"),
                (model, "recommendation_facts.model = ?"),
                (effort, "recommendation_facts.effort = ?"),
                (thread_key, "recommendation_facts.thread_key = ?"),
            ):
                if value is not None:
                    fact_clauses.append(clause)
                    fact_params.append(value)
            if not include_archived:
                fact_clauses.append("recommendation_facts.is_archived = 0")
            fact_where = " AND ".join(fact_clauses)
            row = conn.execute(
                "SELECT COUNT(*) AS row_count "
                "FROM recommendation_facts AS recommendation_facts "
                f"INDEXED BY {fact_filter_index} "
                f"WHERE {fact_where}",
                fact_params,
            ).fetchone()
            return int(row["row_count"] if row is not None else 0)
        if thread_key and not fact_filter_clauses:
            total = 0
            for mode in ("indexed", "legacy"):
                where_clause, params = usage_api_where_clause(
                    **filter_kwargs,
                    thread_key_mode=mode,
                )
                if mode == "indexed":
                    usage_source = "usage_events INDEXED BY idx_usage_thread_key_timestamp"
                    where_clause += " AND is_duplicate = 0"
                else:
                    usage_source = "usage_events INDEXED BY idx_canonical_usage_legacy_thread"
                    where_clause += " AND is_duplicate = 0"
                row = conn.execute(
                    f"SELECT COUNT(*) AS row_count FROM {usage_source} {where_clause}",
                    params,
                ).fetchone()
                total += int(row["row_count"] if row is not None else 0)
            return total
        where_clause, params = usage_api_where_clause(**filter_kwargs)
        if fact_filter_clauses:
            fact_filter_sql = " AND ".join(fact_filter_clauses)
            where_clause = (
                f"{where_clause} AND {fact_filter_sql}"
                if where_clause
                else f"WHERE {fact_filter_sql}"
            )
            params.extend(fact_filter_params)
        usage_source = "canonical_usage_events AS usage_events"
        if fact_filter_clauses and fact_filter_index is not None and cwds is None:
            usage_source = (
                "recommendation_facts AS recommendation_facts "
                f"INDEXED BY {fact_filter_index} "
                "JOIN usage_events AS usage_events "
                "INDEXED BY idx_canonical_usage_record_id "
                "ON usage_events.record_id = recommendation_facts.record_id"
            )
            where_clause = (
                f"{where_clause} AND usage_events.is_duplicate = 0"
                if where_clause
                else "WHERE usage_events.is_duplicate = 0"
            )
        elif fact_filter_clauses and cwds is not None:
            usage_source = (
                "usage_events AS usage_events "
                "INDEXED BY idx_usage_cwd_scope "
                "JOIN recommendation_facts AS recommendation_facts "
                "INDEXED BY idx_recommendation_facts_record_filter_cover "
                "ON recommendation_facts.record_id = usage_events.record_id"
            )
            where_clause = (
                f"{where_clause} AND usage_events.is_duplicate = 0"
                if where_clause
                else "WHERE usage_events.is_duplicate = 0"
            )
        row = conn.execute(
            f"SELECT COUNT(*) AS row_count FROM {usage_source} {where_clause}",
            params,
        ).fetchone()
        return int(row["row_count"] if row is not None else 0)


def query_usage_api_distinct_cwds(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    search: str | None = None,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    thread_key: str | None = None,
    include_archived: bool = False,
    legacy_archive_path_fallback: bool = True,
) -> list[str]:
    """Return the distinct project directories in the requested call scope."""
    where_clause, params = usage_api_where_clause(
        search=search,
        since=since,
        until=until,
        model=model,
        effort=effort,
        source="project",
        thread=thread,
        thread_key=thread_key,
        include_archived=include_archived,
        table_alias="usage_events",
        legacy_archive_path_fallback=legacy_archive_path_fallback,
    )
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            "SELECT DISTINCT usage_events.cwd "
            "FROM canonical_usage_events AS usage_events "
            f"{where_clause} "
            "ORDER BY usage_events.cwd",
            params,
        ).fetchall()
    return [str(row["cwd"]) for row in rows if row["cwd"]]


def query_usage_api_filter_options(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    since: str | None = None,
    until: str | None = None,
    include_archived: bool = False,
) -> dict[str, list[str]]:
    """Return complete model and effort choices for a focused call scope."""
    clauses: list[str] = []
    params: list[object] = []
    if since is not None:
        clauses.append("event_timestamp >= ?")
        params.append(since)
    if until is not None:
        clauses.append("event_timestamp <= ?")
        params.append(until)
    if not include_archived:
        clauses.append("is_archived = 0")
    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect(db_path) as conn:
        init_db(conn)
        models = conn.execute(
            f"SELECT DISTINCT model FROM recommendation_facts {where_clause} ORDER BY model",
            params,
        ).fetchall()
        efforts = conn.execute(
            f"SELECT DISTINCT effort FROM recommendation_facts {where_clause} ORDER BY effort",
            params,
        ).fetchall()
    return {
        "models": [str(row["model"]) for row in models if row["model"]],
        "efforts": [str(row["effort"]) for row in efforts if row["effort"]],
    }


def _recommendation_fact_filters(
    *,
    pricing_status: str | None,
    credit_confidence: str | None,
) -> tuple[list[str], list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if pricing_status == "priced":
        clauses.append(
            "(recommendation_facts.pricing_model IS NOT NULL) = 1 "
            "AND recommendation_facts.pricing_estimated = 0"
        )
    elif pricing_status == "estimated":
        clauses.append("recommendation_facts.pricing_estimated = 1")
    elif pricing_status == "unpriced":
        clauses.append("(recommendation_facts.pricing_model IS NOT NULL) = 0")
    elif pricing_status:
        raise ValueError("pricing_status must be one of: priced, estimated, unpriced")
    if credit_confidence:
        clauses.append("recommendation_facts.usage_credit_confidence = ?")
        params.append(credit_confidence)
    return clauses, params


def _recommendation_fact_filter_index(
    *,
    pricing_status: str | None,
    credit_confidence: str | None,
) -> str | None:
    if credit_confidence:
        return "idx_recommendation_facts_credit_confidence_scope"
    if pricing_status == "estimated":
        return "idx_recommendation_facts_pricing_estimated_scope"
    if pricing_status in {"priced", "unpriced"}:
        return "idx_recommendation_facts_pricing_coverage_scope"
    return None
