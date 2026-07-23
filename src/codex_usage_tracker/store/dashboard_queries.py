"""Dashboard usage read queries."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.query_sql import (
    normalize_limit,
    normalize_offset,
    usage_where_clause,
)
from codex_usage_tracker.store.rows import row_to_dict, usage_row_to_dict
from codex_usage_tracker.store.schema import init_db
from codex_usage_tracker.store.subagent_usage_queries import SUBAGENT_PREDICATE
from codex_usage_tracker.store.usage_timing import (
    USAGE_TIMING_JOIN_SQL,
    USAGE_TIMING_SELECT_SQL,
    usage_parent_select_sql,
)

OBSERVED_USAGE_RECONCILIATION_THRESHOLD = 3

_SUBAGENT_LABEL_EXPRESSION = (
    "coalesce(nullif(trim(usage_events.agent_role), ''), "
    "nullif(trim(usage_events.subagent_type), ''), 'subagent')"
)
_SUBAGENT_DIMENSION_EXPRESSION = (
    f"CASE WHEN coalesce({SUBAGENT_PREDICATE}, 0) "
    f"THEN {_SUBAGENT_LABEL_EXPRESSION} ELSE 'not-subagent' END"
)


def query_dashboard_events(
    db_path: Path = DEFAULT_DB_PATH,
    limit: int | None = 5000,
    offset: int = 0,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    min_tokens: int | None = None,
    include_archived: bool = True,
) -> list[dict[str, Any]]:
    where_clause, params = usage_where_clause(
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        min_tokens=min_tokens,
        table_alias="usage_events",
        include_archived=include_archived,
    )
    normalized_limit = normalize_limit(limit)
    normalized_offset = normalize_offset(offset)
    limit_clause = ""
    query_params = list(params)
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
        rows = conn.execute(
            f"""
            SELECT
                usage_events.*,
                {USAGE_TIMING_SELECT_SQL},
                {usage_parent_select_sql(include_archived=include_archived)}
            FROM canonical_usage_events AS usage_events
            {USAGE_TIMING_JOIN_SQL}
            {where_clause}
            ORDER BY usage_events.event_timestamp DESC, usage_events.cumulative_total_tokens DESC
            {limit_clause}
            """,
            query_params,
        ).fetchall()
    return [usage_row_to_dict(row) for row in rows]


def query_dashboard_event_count(
    db_path: Path = DEFAULT_DB_PATH,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    min_tokens: int | None = None,
    include_archived: bool = True,
) -> int:
    """Return total aggregate usage rows available for the dashboard window."""

    where_clause, params = usage_where_clause(
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        min_tokens=min_tokens,
        include_archived=include_archived,
    )
    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS row_count
            FROM canonical_usage_events AS usage_events
            {where_clause}
            """,
            params,
        ).fetchone()
        return int(row["row_count"] if row is not None else 0)


def query_dashboard_event_counts(
    db_path: Path = DEFAULT_DB_PATH,
    since: str | None = None,
) -> dict[str, int]:
    """Return active and all-history dashboard counts in one aggregate query."""
    where_clause, params = usage_where_clause(since=since, include_archived=True)
    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute(
            f"""
            SELECT
                coalesce(SUM(CASE WHEN is_archived = 0 THEN 1 ELSE 0 END), 0)
                    AS active_available_rows,
                COUNT(*) AS all_history_available_rows
            FROM canonical_usage_events AS usage_events
            {where_clause}
            """,
            params,
        ).fetchone()
    return {
        "active_available_rows": int(row["active_available_rows"] if row else 0),
        "all_history_available_rows": int(row["all_history_available_rows"] if row else 0),
    }


def query_dashboard_token_summary(
    db_path: Path = DEFAULT_DB_PATH,
    since: str | None = None,
    include_archived: bool = True,
) -> dict[str, Any]:
    """Return cheap aggregate token totals for the dashboard shell."""

    where_clause, params = usage_where_clause(
        since=since,
        include_archived=include_archived,
    )
    with connect(db_path) as conn:
        init_db(conn)
        total_row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS row_count,
                coalesce(SUM(input_tokens), 0) AS input_tokens,
                coalesce(SUM(cached_input_tokens), 0) AS cached_input_tokens,
                coalesce(SUM(uncached_input_tokens), 0) AS uncached_input_tokens,
                coalesce(SUM(output_tokens), 0) AS output_tokens,
                coalesce(SUM(reasoning_output_tokens), 0) AS reasoning_output_tokens,
                coalesce(SUM(total_tokens), 0) AS total_tokens
            FROM canonical_usage_events AS usage_events
            {where_clause}
            """,
            params,
        ).fetchone()
        model_rows = [
            row_to_dict(row)
            for row in conn.execute(
                f"""
                SELECT
                    coalesce(model, 'Unknown model') AS model,
                    COUNT(*) AS row_count,
                    coalesce(SUM(input_tokens), 0) AS input_tokens,
                    coalesce(SUM(cached_input_tokens), 0) AS cached_input_tokens,
                    coalesce(SUM(uncached_input_tokens), 0) AS uncached_input_tokens,
                    coalesce(SUM(output_tokens), 0) AS output_tokens,
                    coalesce(SUM(reasoning_output_tokens), 0) AS reasoning_output_tokens,
                    coalesce(SUM(total_tokens), 0) AS total_tokens
                FROM canonical_usage_events AS usage_events
                {where_clause}
                GROUP BY coalesce(model, 'Unknown model')
                """,
                params,
            )
        ]
    summary = row_to_dict(total_row) if total_row is not None else {}
    return {
        "row_count": int(summary.get("row_count") or 0),
        "input_tokens": int(summary.get("input_tokens") or 0),
        "cached_input_tokens": int(summary.get("cached_input_tokens") or 0),
        "uncached_input_tokens": int(summary.get("uncached_input_tokens") or 0),
        "output_tokens": int(summary.get("output_tokens") or 0),
        "reasoning_output_tokens": int(summary.get("reasoning_output_tokens") or 0),
        "total_tokens": int(summary.get("total_tokens") or 0),
        "model_rows": model_rows,
    }


def query_usage_status(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    include_archived: bool = False,
    legacy_archive_path_fallback: bool = True,
) -> dict[str, Any]:
    """Return cheap row-count metadata for live dashboard status checks."""

    scoped_where, scoped_params = usage_where_clause(
        include_archived=include_archived,
        legacy_archive_path_fallback=legacy_archive_path_fallback,
    )
    active_where, active_params = usage_where_clause(
        include_archived=False,
        legacy_archive_path_fallback=legacy_archive_path_fallback,
    )
    with connect(db_path) as conn:
        init_db(conn)
        total_row = conn.execute("SELECT COUNT(*) AS count FROM canonical_usage_events").fetchone()
        active_row = conn.execute(
            f"SELECT COUNT(*) AS count FROM canonical_usage_events {active_where}",
            active_params,
        ).fetchone()
        scoped_row = total_row if include_archived else active_row
        max_row = conn.execute(
            f"SELECT MAX(event_timestamp) AS max_event_timestamp FROM canonical_usage_events {scoped_where}",
            scoped_params,
        ).fetchone()
    return {
        "total_rows": int(total_row["count"] if total_row is not None else 0),
        "active_rows": int(active_row["count"] if active_row is not None else 0),
        "scoped_rows": int(scoped_row["count"] if scoped_row is not None else 0),
        "max_event_timestamp": (max_row["max_event_timestamp"] if max_row is not None else None),
    }


def query_latest_observed_usage(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    include_archived: bool = False,
    legacy_archive_path_fallback: bool = True,
) -> dict[str, Any]:
    """Return the latest passive usage-limit snapshot from token-count rows."""

    where_clause, params = usage_where_clause(
        include_archived=include_archived,
        legacy_archive_path_fallback=legacy_archive_path_fallback,
    )
    observed_clause = (
        "rate_limit_primary_used_percent IS NOT NULL "
        "OR rate_limit_secondary_used_percent IS NOT NULL"
    )
    canonical_observed_clause = f"is_duplicate = 0 AND ({observed_clause})"
    scoped_where = (
        f"{where_clause} AND {canonical_observed_clause}"
        if where_clause
        else f"WHERE {canonical_observed_clause}"
    )
    with connect(db_path) as conn:
        init_db(conn)
        row = _latest_observed_usage_row(
            conn,
            scoped_where=scoped_where,
            params=params,
        )
        reconciliation = observed_usage_reconciliation(
            conn,
            scoped_where=scoped_where,
            params=params,
            selected_row=row,
        )
    if row is None:
        return {"available": False, "windows": [], "reconciliation": reconciliation}
    data = row_to_dict(row)
    return {
        "available": True,
        "record_id": data.get("record_id"),
        "observed_at": data.get("event_timestamp"),
        "line_number": data.get("line_number"),
        "plan_type": data.get("rate_limit_plan_type"),
        "limit_id": data.get("rate_limit_limit_id"),
        "source": "token_count.rate_limits",
        "windows": [
            window
            for window in (
                observed_usage_window(data, "primary"),
                observed_usage_window(data, "secondary"),
            )
            if window is not None
        ],
        "reconciliation": reconciliation,
    }


def _latest_observed_usage_row(
    conn: sqlite3.Connection,
    *,
    scoped_where: str,
    params: list[Any],
) -> sqlite3.Row | None:
    select = """
        SELECT
            record_id,
            event_timestamp,
            line_number,
            rate_limit_plan_type,
            rate_limit_limit_id,
            rate_limit_primary_used_percent,
            rate_limit_primary_window_minutes,
            rate_limit_primary_resets_at,
            rate_limit_secondary_used_percent,
            rate_limit_secondary_window_minutes,
            rate_limit_secondary_resets_at
        FROM usage_events AS usage_events
            INDEXED BY idx_usage_observed_rate_limit_timestamp
    """
    order = "ORDER BY event_timestamp DESC, cumulative_total_tokens DESC LIMIT 1"
    preferred = conn.execute(
        f"{select} {scoped_where} AND rate_limit_limit_id = 'codex' {order}",
        params,
    ).fetchone()
    if preferred is not None:
        return preferred
    return conn.execute(f"{select} {scoped_where} {order}", params).fetchone()


def observed_usage_reconciliation(
    conn: sqlite3.Connection,
    *,
    scoped_where: str,
    params: list[Any],
    selected_row: sqlite3.Row | None,
) -> dict[str, Any]:
    recent_rows = _recent_observed_usage_rows(
        conn,
        scoped_where=scoped_where,
        params=params,
    )
    consecutive_alternate_rows, latest_alternate = _alternate_usage_limit_streak(recent_rows)
    selected = row_to_dict(selected_row) if selected_row is not None else {}
    recommended = _observed_usage_reconciliation_recommended(
        consecutive_alternate_rows=consecutive_alternate_rows,
        latest_alternate=latest_alternate,
        selected=selected,
    )
    return _observed_usage_reconciliation_payload(
        recommended=recommended,
        consecutive_alternate_rows=consecutive_alternate_rows,
        latest_alternate=latest_alternate,
        selected=selected,
    )


def _recent_observed_usage_rows(
    conn: sqlite3.Connection,
    *,
    scoped_where: str,
    params: list[Any],
) -> list[dict[str, Any]]:
    return [
        row_to_dict(row)
        for row in conn.execute(
            f"""
            SELECT record_id, event_timestamp, rate_limit_plan_type, rate_limit_limit_id
            FROM usage_events AS usage_events
                INDEXED BY idx_usage_observed_rate_limit_timestamp

            {scoped_where}

            ORDER BY event_timestamp DESC, cumulative_total_tokens DESC
            LIMIT ?
            """,
            [*params, OBSERVED_USAGE_RECONCILIATION_THRESHOLD],
        ).fetchall()
    ]


def _alternate_usage_limit_streak(
    rows: list[dict[str, Any]],
) -> tuple[int, dict[str, Any] | None]:
    consecutive_rows = 0
    latest_alternate: dict[str, Any] | None = None
    for row in rows:
        if not is_alternate_codex_limit(row.get("rate_limit_limit_id")):
            break
        consecutive_rows += 1
        if latest_alternate is None:
            latest_alternate = row
    return consecutive_rows, latest_alternate


def _observed_usage_reconciliation_recommended(
    *,
    consecutive_alternate_rows: int,
    latest_alternate: dict[str, Any] | None,
    selected: dict[str, Any],
) -> bool:
    if consecutive_alternate_rows < OBSERVED_USAGE_RECONCILIATION_THRESHOLD:
        return False
    if latest_alternate is None:
        return False
    return latest_alternate.get("record_id") != selected.get("record_id")


def _observed_usage_reconciliation_payload(
    *,
    recommended: bool,
    consecutive_alternate_rows: int,
    latest_alternate: dict[str, Any] | None,
    selected: dict[str, Any],
) -> dict[str, Any]:
    return {
        "recommended": recommended,
        "reason": "latest_alternate_codex_limit_rows" if recommended else None,
        "suggested_action": "live_usage_check" if recommended else None,
        "consecutive_alternate_rows": consecutive_alternate_rows,
        "threshold": OBSERVED_USAGE_RECONCILIATION_THRESHOLD,
        "latest_limit_id": latest_alternate.get("rate_limit_limit_id")
        if latest_alternate
        else None,
        "latest_plan_type": latest_alternate.get("rate_limit_plan_type")
        if latest_alternate
        else None,
        "latest_observed_at": latest_alternate.get("event_timestamp") if latest_alternate else None,
        "selected_observed_at": selected.get("event_timestamp"),
        "selected_limit_id": selected.get("rate_limit_limit_id"),
    }


def is_alternate_codex_limit(limit_id: object) -> bool:
    if not isinstance(limit_id, str):
        return False
    return limit_id.startswith("codex_") and limit_id != "codex"


def observed_usage_window(row: dict[str, Any], key: str) -> dict[str, Any] | None:
    used_percent = row.get(f"rate_limit_{key}_used_percent")
    window_minutes = row.get(f"rate_limit_{key}_window_minutes")
    resets_at = row.get(f"rate_limit_{key}_resets_at")
    if used_percent is None and window_minutes is None and resets_at is None:
        return None
    return {
        "key": key,
        "label": observed_usage_window_label(window_minutes),
        "used_percent": used_percent,
        "window_minutes": window_minutes,
        "resets_at": resets_at,
    }


def observed_usage_window_label(window_minutes: object) -> str:
    if not isinstance(window_minutes, (int, float, str)):
        return "Usage"
    try:
        minutes = int(window_minutes)
    except (TypeError, ValueError):
        return "Usage"
    if minutes == 300:
        return "5h"
    if minutes == 10080:
        return "Weekly"
    if minutes % 1440 == 0:
        return f"{minutes // 1440}d"
    if minutes % 60 == 0:
        return f"{minutes // 60}h"
    return f"{minutes}m"


_QUERY_IDENTITIES = {
    "call": "usage_events.record_id",
    "thread": "coalesce(usage_events.thread_key, 'session:' || usage_events.session_id)",
    "project": "coalesce(usage_events.cwd, 'unknown')",
    "model": "coalesce(usage_events.model, 'unknown')",
    "effort": "coalesce(usage_events.effort, 'unknown')",
    "origin": "coalesce(usage_events.call_initiator, 'unknown')",
    "service_tier": "coalesce(usage_events.service_tier, 'unknown')",
    "subagent": _SUBAGENT_LABEL_EXPRESSION,
}
_QUERY_DIMENSIONS = {
    "model": "coalesce(usage_events.model, 'unknown')",
    "effort": "coalesce(usage_events.effort, 'unknown')",
    "origin": "coalesce(usage_events.call_initiator, 'unknown')",
    "service_tier": "coalesce(usage_events.service_tier, 'unknown')",
    "subagent_type": "coalesce(usage_events.subagent_type, 'not-subagent')",
    "subagent": _SUBAGENT_DIMENSION_EXPRESSION,
}
_QUERY_FILTERS = frozenset(
    {
        "since",
        "until",
        "model",
        "effort",
        "thread_key",
        "project",
        "origin",
        "service_tier",
        "subagent_role",
        "subagent_type",
        "parent_thread_key",
    }
)
_MATERIALIZED_MODEL_MEASURES = frozenset(
    {
        "tokens",
        "uncached_tokens",
        "cached_tokens",
        "output_tokens",
        "reasoning_tokens",
        "estimated_cost",
        "estimated_credits",
        "call_count",
        "cache_ratio",
        "context_pressure",
    }
)


def query_canonical_usage_v2(
    *,
    db_path: Path,
    entity: str,
    measures: tuple[str, ...],
    filters: dict[str, object],
    group_by: tuple[str, ...],
    order_by: str,
    order: str,
    include_archived: bool,
    limit: int,
    cursor_sort: object | None,
    cursor_identity: str | None,
) -> list[dict[str, Any]]:
    """Run one bounded allowlisted canonical query with stable keyset ordering."""
    if entity not in _QUERY_IDENTITIES:
        raise ValueError("unsupported canonical query entity")
    if any(name not in _QUERY_DIMENSIONS for name in group_by):
        raise ValueError("unsupported canonical query dimension")
    if any(name not in _QUERY_FILTERS for name, value in filters.items() if value is not None):
        raise ValueError("unsupported canonical query filter")
    if order not in {"asc", "desc"}:
        raise ValueError("unsupported canonical query order")
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("canonical query limit must be between 1 and 200")
    identity_expression = _QUERY_IDENTITIES[entity]
    dimension_expressions = [_QUERY_DIMENSIONS[name] for name in group_by]
    grouped = entity != "call" or bool(group_by)
    measure_expressions = _query_measure_expressions(grouped)
    if any(name not in measure_expressions for name in measures):
        raise ValueError("unsupported canonical query measure")
    selected_measures = [f"{measure_expressions[name]} AS {name}" for name in measures]
    dimensions = [f"{identity_expression} AS {entity}"] + [
        f"{expression} AS {name}"
        for name, expression in zip(group_by, dimension_expressions, strict=True)
    ]
    identity_alias = "record_id" if entity == "call" else entity
    if order_by in {"estimated_cost", "estimated_credits"}:
        raise ValueError("estimated measures cannot be used as canonical query order_by")
    allowed_order = {identity_alias, *group_by, *measures}
    if entity == "call" and not group_by:
        allowed_order.add("time")
    if order_by not in allowed_order:
        raise ValueError("unsupported canonical query order_by")
    if entity == "call":
        dimensions[0] = f"{identity_expression} AS record_id"
    if (
        entity == "call"
        and not group_by
        and order_by == "time"
        and not any(value is not None for value in filters.values())
    ):
        return _query_recent_calls(
            db_path=db_path,
            measures=measures,
            order=order,
            include_archived=include_archived,
            limit=limit,
            cursor_sort=cursor_sort,
            cursor_identity=cursor_identity,
        )
    if _can_query_materialized_models(
        entity=entity,
        measures=measures,
        filters=filters,
        group_by=group_by,
    ) and _has_materialized_recommendation_facts(db_path):
        return _query_materialized_models(
            db_path=db_path,
            measures=measures,
            filters=filters,
            order_by=order_by,
            order=order,
            include_archived=include_archived,
            limit=limit,
            cursor_sort=cursor_sort,
            cursor_identity=cursor_identity,
        )
    where, params = _canonical_query_where(entity, filters, include_archived=include_archived)
    grouping = ""
    if grouped:
        grouping = "GROUP BY " + ", ".join([identity_expression, *dimension_expressions])
    direction = "ASC" if order == "asc" else "DESC"
    cursor_where, cursor_params = _canonical_cursor_where(
        order_by, direction, identity_alias, cursor_sort, cursor_identity
    )
    sql = f"""
        WITH result_rows AS (
            SELECT {", ".join([*dimensions, *selected_measures, *_pricing_selects(grouped)])}
            FROM canonical_usage_events AS usage_events
            {USAGE_TIMING_JOIN_SQL}
            {where}
            {grouping}
        ), counted AS (
            SELECT result_rows.*, COUNT(*) OVER () AS _total_matched FROM result_rows
        )
        SELECT * FROM counted
        {cursor_where}
        ORDER BY ({order_by} IS NULL) ASC, {order_by} {direction}, {identity_alias} ASC
        LIMIT ?
    """  # nosec B608 - identifiers and clauses come from validated internal allowlists.
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(sql, [*params, *cursor_params, limit + 1]).fetchall()
    return [row_to_dict(row) for row in rows]


def _can_query_materialized_models(
    *,
    entity: str,
    measures: tuple[str, ...],
    filters: dict[str, object],
    group_by: tuple[str, ...],
) -> bool:
    active_filters = {name for name, value in filters.items() if value is not None}
    return (
        entity == "model"
        and not group_by
        and set(measures) <= _MATERIALIZED_MODEL_MEASURES
        and active_filters <= {"since", "until", "model", "effort"}
    )


def _has_materialized_recommendation_facts(db_path: Path) -> bool:
    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute(
            """
            SELECT recommendation_fact_state.record_count
            FROM recommendation_fact_state
            JOIN compression_source_state
                ON compression_source_state.singleton = 1
            WHERE recommendation_fact_state.singleton = 1
              AND recommendation_fact_state.source_generation =
                  compression_source_state.generation
            """
        ).fetchone()
    return row is not None and int(row["record_count"] or 0) > 0


def _query_recent_calls(
    *,
    db_path: Path,
    measures: tuple[str, ...],
    order: str,
    include_archived: bool,
    limit: int,
    cursor_sort: object | None,
    cursor_identity: str | None,
) -> list[dict[str, Any]]:
    measure_expressions = _query_measure_expressions(False)
    selected = [f"{measure_expressions[name]} AS {name}" for name in measures]
    direction = "ASC" if order == "asc" else "DESC"
    clauses = ["usage_events.is_duplicate = 0"]
    if not include_archived:
        clauses.append("usage_events.is_archived = 0")
    params: list[object] = []
    if cursor_identity is not None:
        comparison = ">" if direction == "ASC" else "<"
        if cursor_sort is None:
            clauses.extend(("usage_events.event_timestamp IS NULL", "usage_events.record_id > ?"))
            params.append(cursor_identity)
        else:
            clauses.append(
                "((usage_events.event_timestamp "
                f"{comparison} ?) OR (usage_events.event_timestamp = ? "
                "AND usage_events.record_id > ?))"
            )
            params.extend((cursor_sort, cursor_sort, cursor_identity))
    fallback_count = (
        "(SELECT COUNT(*) FROM usage_events AS count_events "
        "WHERE count_events.is_duplicate = 0)"
        if include_archived
        else "(SELECT COUNT(*) FROM usage_events AS count_events "
        "WHERE count_events.is_duplicate = 0 AND count_events.is_archived = 0)"
    )
    total_matched = (
        "coalesce((SELECT recommendation_fact_state.record_count "  # nosec B608
        "FROM recommendation_fact_state JOIN compression_source_state "
        "ON compression_source_state.singleton = 1 "
        "WHERE recommendation_fact_state.singleton = 1 "
        "AND recommendation_fact_state.source_generation = "
        f"compression_source_state.generation), {fallback_count})"
        if include_archived
        else "coalesce((SELECT json_extract(refresh_meta.value, '$.calls') "  # nosec B608
        "FROM refresh_meta JOIN recommendation_fact_state "
        "ON recommendation_fact_state.singleton = 1 "
        "JOIN compression_source_state ON compression_source_state.singleton = 1 "
        "WHERE refresh_meta.key = 'home_usage_metrics_v1' "
        "AND json_extract(refresh_meta.value, '$.source_generation') = "
        "compression_source_state.generation "
        "AND recommendation_fact_state.source_generation = "
        "compression_source_state.generation "
        "AND json_extract(refresh_meta.value, '$.materialized_calls') = "
        f"recommendation_fact_state.record_count), {fallback_count})"
    )
    sql = f"""
        SELECT
            usage_events.record_id,
            usage_events.event_timestamp AS time,
            {", ".join([*selected, *_pricing_selects(False)])},
            {total_matched} AS _total_matched
        FROM usage_events AS usage_events
            INDEXED BY idx_canonical_usage_archived_timestamp
        {USAGE_TIMING_JOIN_SQL}
        WHERE {" AND ".join(clauses)}
        ORDER BY
            usage_events.event_timestamp {direction},
            usage_events.record_id ASC
        LIMIT ?
        """  # nosec B608 - clauses are fixed or built from validated internal allowlists.
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(sql, [*params, limit + 1]).fetchall()
    return [row_to_dict(row) for row in rows]


def _query_materialized_models(
    *,
    db_path: Path,
    measures: tuple[str, ...],
    filters: dict[str, object],
    order_by: str,
    order: str,
    include_archived: bool,
    limit: int,
    cursor_sort: object | None,
    cursor_identity: str | None,
) -> list[dict[str, Any]]:
    expressions = {
        "tokens": "SUM(total_tokens)",
        "uncached_tokens": "SUM(uncached_input_tokens)",
        "cached_tokens": "SUM(cached_input_tokens)",
        "output_tokens": "SUM(output_tokens)",
        "reasoning_tokens": "SUM(reasoning_output_tokens)",
        "estimated_cost": "SUM(estimated_cost_usd)",
        "estimated_credits": "SUM(usage_credits)",
        "call_count": "COUNT(*)",
        "cache_ratio": (
            "CAST(SUM(cached_input_tokens) AS REAL) / NULLIF(SUM(input_tokens), 0)"
        ),
        "context_pressure": "MAX(context_window_percent)",
    }
    selected = [f"{expressions[name]} AS {name}" for name in measures]
    if "estimated_cost" in measures:
        selected.extend(
            (
                "CAST(SUM(estimated_cost_usd IS NOT NULL) AS REAL) / COUNT(*) "
                "AS _materialized_estimated_cost_coverage",
                "CASE WHEN SUM(estimated_cost_usd IS NOT NULL) = 0 THEN 'unknown' "
                "WHEN MAX(pricing_estimated) = 1 THEN 'estimated' ELSE 'exact' END "
                "AS _materialized_estimated_cost_confidence",
            )
        )
    if "estimated_credits" in measures:
        selected.extend(
            (
                "CAST(SUM(usage_credits IS NOT NULL) AS REAL) / COUNT(*) "
                "AS _materialized_estimated_credits_coverage",
                "CASE WHEN SUM(usage_credits IS NOT NULL) = 0 THEN 'unknown' "
                "WHEN SUM(usage_credit_confidence = 'user_override') > 0 THEN 'user_override' "
                "WHEN SUM(usage_credit_confidence = 'estimated') > 0 THEN 'estimated' "
                "ELSE 'exact' END AS _materialized_estimated_credits_confidence",
            )
        )
    clauses: list[str] = []
    params: list[object] = []
    if not include_archived:
        clauses.append("is_archived = 0")
    for name, column, operator in (
        ("since", "event_timestamp", ">="),
        ("until", "event_timestamp", "<="),
        ("model", "model", "="),
        ("effort", "effort", "="),
    ):
        value = filters.get(name)
        if isinstance(value, str):
            clauses.append(f"{column} {operator} ?")
            params.append(value)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    fact_source = (
        "recommendation_facts INDEXED BY idx_recommendation_facts_time_model"
        if filters.get("since") is not None or filters.get("until") is not None
        else "recommendation_facts NOT INDEXED"
    )
    direction = "ASC" if order == "asc" else "DESC"
    cursor_where, cursor_params = _canonical_cursor_where(
        order_by,
        direction,
        "model",
        cursor_sort,
        cursor_identity,
    )
    sql = f"""
        WITH result_rows AS (
            SELECT coalesce(model, 'unknown') AS model, {", ".join(selected)}
            FROM {fact_source}
            {where}
            GROUP BY coalesce(model, 'unknown')
        ), counted AS (
            SELECT result_rows.*, COUNT(*) OVER () AS _total_matched FROM result_rows
        )
        SELECT * FROM counted
        {cursor_where}
        ORDER BY ({order_by} IS NULL) ASC, {order_by} {direction}, model ASC
        LIMIT ?
    """  # nosec B608 - identifiers and clauses come from validated internal allowlists.
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(sql, [*params, *cursor_params, limit + 1]).fetchall()
    return [row_to_dict(row) for row in rows]


def _query_measure_expressions(grouped: bool) -> dict[str, str]:
    aggregate = "SUM" if grouped else ""

    def value(column: str) -> str:
        return f"{aggregate}(usage_events.{column})" if grouped else f"usage_events.{column}"

    cache_ratio = (
        "CAST(SUM(usage_events.cached_input_tokens) AS REAL) / "
        "NULLIF(SUM(usage_events.input_tokens), 0)"
        if grouped
        else "usage_events.cache_ratio"
    )
    context_pressure = (
        "MAX(usage_events.context_window_percent)"
        if grouped
        else "usage_events.context_window_percent"
    )
    duration_value = (
        "MAX((julianday(usage_events.event_timestamp) - "
        "julianday(coalesce(previous_usage.event_timestamp, usage_events.turn_timestamp))) "
        "* 86400.0, 0.0)"
    )
    duration = f"SUM({duration_value})" if grouped else duration_value
    return {
        "tokens": value("total_tokens"),
        "uncached_tokens": value("uncached_input_tokens"),
        "cached_tokens": value("cached_input_tokens"),
        "output_tokens": value("output_tokens"),
        "reasoning_tokens": value("reasoning_output_tokens"),
        "estimated_cost": "NULL",
        "estimated_credits": "NULL",
        "call_count": "COUNT(*)" if grouped else "1",
        "duration": duration,
        "cache_ratio": cache_ratio,
        "context_pressure": context_pressure,
    }


def _pricing_selects(grouped: bool) -> list[str]:
    if not grouped:
        return [
            "usage_events.model AS _pricing_model",
            "1 AS _pricing_model_count",
            "usage_events.service_tier AS _pricing_service_tier",
            "usage_events.input_tokens AS _pricing_input_tokens",
            "usage_events.cached_input_tokens AS _pricing_cached_input_tokens",
            "usage_events.uncached_input_tokens AS _pricing_uncached_input_tokens",
            "usage_events.output_tokens AS _pricing_output_tokens",
        ]
    return [
        "MIN(usage_events.model) AS _pricing_model",
        "COUNT(DISTINCT coalesce(usage_events.model, '')) AS _pricing_model_count",
        "MIN(usage_events.service_tier) AS _pricing_service_tier",
        "COUNT(DISTINCT coalesce(usage_events.service_tier, '')) AS _pricing_tier_count",
        "SUM(usage_events.input_tokens) AS _pricing_input_tokens",
        "SUM(usage_events.cached_input_tokens) AS _pricing_cached_input_tokens",
        "SUM(usage_events.uncached_input_tokens) AS _pricing_uncached_input_tokens",
        "SUM(usage_events.output_tokens) AS _pricing_output_tokens",
    ]


def _canonical_query_where(
    entity: str, filters: dict[str, object], *, include_archived: bool
) -> tuple[str, list[object]]:
    string_filters = {key: value for key, value in filters.items() if isinstance(value, str)}
    where, params = usage_where_clause(
        since=string_filters.get("since"),
        until=string_filters.get("until"),
        model=string_filters.get("model"),
        effort=string_filters.get("effort"),
        thread=string_filters.get("thread_key"),
        table_alias="usage_events",
        include_archived=include_archived,
    )
    clauses = [where.removeprefix("WHERE ")] if where else []
    if entity == "subagent":
        clauses.append(SUBAGENT_PREDICATE)
    for key, column in (
        ("project", "usage_events.cwd"),
        ("origin", "usage_events.call_initiator"),
        ("service_tier", "usage_events.service_tier"),
        ("subagent_role", "usage_events.agent_role"),
        ("subagent_type", "usage_events.subagent_type"),
        ("parent_thread_key", "usage_events.parent_thread_name"),
    ):
        value = filters.get(key)
        if isinstance(value, str):
            clauses.append(f"{column} = ?")
            params.append(value)
    return ("WHERE " + " AND ".join(clauses) if clauses else "", list(params))


def _canonical_cursor_where(
    order_by: str,
    direction: str,
    identity: str,
    cursor_sort: object | None,
    cursor_identity: str | None,
) -> tuple[str, list[object]]:
    if cursor_identity is None:
        return "", []
    if cursor_sort is None:
        return f"WHERE {order_by} IS NULL AND {identity} > ?", [cursor_identity]
    comparison = ">" if direction == "ASC" else "<"
    return (
        f"WHERE ({order_by} {comparison} ? OR "
        f"({order_by} = ? AND {identity} > ?) OR {order_by} IS NULL)",
        [cursor_sort, cursor_sort, cursor_identity],
    )
