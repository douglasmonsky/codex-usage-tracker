"""Aggregate query helpers for observed subagent usage."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.query_sql import usage_where_clause
from codex_usage_tracker.store.rows import row_to_dict
from codex_usage_tracker.store.schema import init_db

SUBAGENT_PREDICATE = """(
    usage_events.thread_source = 'subagent'
    OR nullif(trim(usage_events.subagent_type), '') IS NOT NULL
    OR nullif(trim(usage_events.parent_session_id), '') IS NOT NULL
)"""

BREAKDOWN_EXPRESSIONS = {
    "role": "coalesce(nullif(trim(usage_events.agent_role), ''), 'unknown')",
    "type": "coalesce(nullif(trim(usage_events.subagent_type), ''), 'unknown')",
    "parent": ("coalesce(nullif(trim(usage_events.parent_thread_name), ''), 'unknown parent')"),
}

_CANONICAL_SOURCE = "canonical_usage_events AS usage_events"

_METRIC_EXPRESSIONS = """
    COUNT(*) AS calls,
    COUNT(DISTINCT session_id || ':' || coalesce(turn_id, '')) AS turns,
    COUNT(DISTINCT CASE
      WHEN nullif(trim(session_id), '') IS NOT NULL THEN session_id
    END) AS observed_spawns,
    coalesce(SUM(input_tokens), 0) AS input_tokens,
    coalesce(SUM(cached_input_tokens), 0) AS cached_input_tokens,
    coalesce(SUM(uncached_input_tokens), 0) AS uncached_input_tokens,
    coalesce(SUM(output_tokens), 0) AS output_tokens,
    coalesce(SUM(reasoning_output_tokens), 0) AS reasoning_output_tokens,
    coalesce(SUM(total_tokens), 0) AS total_tokens,
    MAX(event_timestamp) AS latest_event
"""

_MODEL_METRIC_EXPRESSIONS = """
    COUNT(*) AS calls,
    coalesce(SUM(input_tokens), 0) AS input_tokens,
    coalesce(SUM(cached_input_tokens), 0) AS cached_input_tokens,
    coalesce(SUM(uncached_input_tokens), 0) AS uncached_input_tokens,
    coalesce(SUM(output_tokens), 0) AS output_tokens,
    coalesce(SUM(reasoning_output_tokens), 0) AS reasoning_output_tokens,
    coalesce(SUM(total_tokens), 0) AS total_tokens
"""


def query_subagent_usage_buckets(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    since: str | None = None,
    parent_thread: str | None = None,
    agent_role: str | None = None,
    subagent_type: str | None = None,
    include_archived: bool = False,
    limit: int = 10,
) -> dict[str, Any]:
    """Return aggregate direct and observed-subagent usage cohorts."""
    _validate_limit(limit)
    where_sql, base_params = usage_where_clause(
        since=since,
        thread=parent_thread,
        table_alias="usage_events",
        include_archived=include_archived,
    )
    direct_where = _append_clause(where_sql, f"NOT coalesce({SUBAGENT_PREDICATE}, 0)")
    subagent_where, subagent_params = _subagent_where(
        where_sql,
        list(base_params),
        agent_role=agent_role,
        subagent_type=subagent_type,
    )
    attributed_where = _append_clause(
        subagent_where,
        "nullif(trim(usage_events.session_id), '') IS NOT NULL",
    )

    with connect(db_path) as conn:
        init_db(conn)
        cohorts = {
            "direct": _usage_bucket(conn, direct_where, list(base_params)),
            "subagent": _usage_bucket(conn, subagent_where, subagent_params),
            "attributable_subagent": _usage_bucket(conn, attributed_where, subagent_params),
        }
        breakdowns = {
            dimension: _breakdown_buckets(
                conn,
                expression,
                subagent_where,
                subagent_params,
                limit,
                include_role_mix=dimension == "parent",
            )
            for dimension, expression in BREAKDOWN_EXPRESSIONS.items()
        }
        coverage = _coverage(conn, subagent_where, subagent_params)

    return {
        "cohorts": cohorts,
        "breakdowns": breakdowns,
        "coverage": coverage,
    }


def _validate_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer from 1 through 100")


def _append_clause(where_sql: str, clause: str) -> str:
    if where_sql:
        return f"{where_sql} AND ({clause})"
    return f"WHERE ({clause})"


def _subagent_where(
    where_sql: str,
    params: list[Any],
    *,
    agent_role: str | None,
    subagent_type: str | None,
) -> tuple[str, list[Any]]:
    result = _append_clause(where_sql, SUBAGENT_PREDICATE)
    if agent_role is not None:
        result = _append_clause(result, "usage_events.agent_role = ?")
        params.append(agent_role)
    if subagent_type is not None:
        result = _append_clause(result, "usage_events.subagent_type = ?")
        params.append(subagent_type)
    return result, params


def _usage_bucket(
    conn: sqlite3.Connection,
    where_sql: str,
    params: list[Any],
) -> dict[str, Any]:
    metrics = row_to_dict(
        conn.execute(
            f"SELECT {_METRIC_EXPRESSIONS} FROM {_CANONICAL_SOURCE} {where_sql}",  # nosec B608
            params,
        ).fetchone()
    )
    model_rows = conn.execute(
        f"""
        SELECT model, service_tier, {_MODEL_METRIC_EXPRESSIONS}
        FROM {_CANONICAL_SOURCE}
        {where_sql}
        GROUP BY model, service_tier
        ORDER BY total_tokens DESC, model ASC, service_tier ASC
        """,  # nosec B608
        params,
    ).fetchall()
    return {
        "metrics": metrics,
        "model_buckets": [row_to_dict(row) for row in model_rows],
    }


def _breakdown_buckets(
    conn: sqlite3.Connection,
    expression: str,
    where_sql: str,
    params: list[Any],
    limit: int,
    *,
    include_role_mix: bool = False,
) -> list[dict[str, Any]]:
    group_rows = conn.execute(
        f"""
        SELECT {expression} AS group_key, {_METRIC_EXPRESSIONS}
        FROM {_CANONICAL_SOURCE}
        {where_sql}
        GROUP BY group_key
        ORDER BY total_tokens DESC, group_key ASC
        LIMIT ?
        """,  # nosec B608
        [*params, limit],
    ).fetchall()
    group_keys = [str(row["group_key"]) for row in group_rows]
    if not group_keys:
        return []

    placeholders = ", ".join("?" for _ in group_keys)
    selected_where = _append_clause(where_sql, f"{expression} IN ({placeholders})")
    selected_params = [*params, *group_keys]
    model_rows = conn.execute(
        f"""
        SELECT {expression} AS group_key, model, service_tier,
               {_MODEL_METRIC_EXPRESSIONS}
        FROM {_CANONICAL_SOURCE}
        {selected_where}
        GROUP BY group_key, model, service_tier
        ORDER BY total_tokens DESC, group_key ASC, model ASC, service_tier ASC
        """,  # nosec B608
        selected_params,
    ).fetchall()
    models_by_group: dict[str, list[dict[str, Any]]] = {}
    for row in model_rows:
        model_bucket = row_to_dict(row)
        group_key = str(model_bucket.pop("group_key"))
        models_by_group.setdefault(group_key, []).append(model_bucket)

    role_mix_by_group = (
        _parent_role_mix(conn, where_sql, params, group_keys) if include_role_mix else {}
    )
    result: list[dict[str, Any]] = []
    for row in group_rows:
        group_key = str(row["group_key"])
        bucket = {
            "group_key": str(row["group_key"]),
            "metrics": {
                key: value for key, value in row_to_dict(row).items() if key != "group_key"
            },
            "model_buckets": models_by_group.get(group_key, []),
        }
        if include_role_mix:
            bucket["role_mix"] = role_mix_by_group.get(group_key, [])
        result.append(bucket)
    return result


def _parent_role_mix(
    conn: sqlite3.Connection,
    where_sql: str,
    params: list[Any],
    parent_keys: list[str],
) -> dict[str, list[dict[str, Any]]]:
    parent_expression = BREAKDOWN_EXPRESSIONS["parent"]
    role_expression = BREAKDOWN_EXPRESSIONS["role"]
    placeholders = ", ".join("?" for _ in parent_keys)
    selected_where = _append_clause(
        where_sql,
        f"{parent_expression} IN ({placeholders})",
    )
    rows = conn.execute(
        f"""
        SELECT {parent_expression} AS group_key,
               {role_expression} AS agent_role,
               COUNT(DISTINCT CASE
                 WHEN nullif(trim(session_id), '') IS NOT NULL THEN session_id
               END) AS observed_spawns,
               COUNT(*) AS calls,
               coalesce(SUM(total_tokens), 0) AS total_tokens
        FROM {_CANONICAL_SOURCE}
        {selected_where}
        GROUP BY group_key, agent_role
        ORDER BY group_key ASC, total_tokens DESC, agent_role ASC
        """,  # nosec B608
        [*params, *parent_keys],
    ).fetchall()
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        role = row_to_dict(row)
        group_key = str(role.pop("group_key"))
        result.setdefault(group_key, []).append(role)
    return result


def _coverage(
    conn: sqlite3.Connection,
    where_sql: str,
    params: list[Any],
) -> dict[str, int]:
    row = conn.execute(
        f"""
        SELECT
            COUNT(CASE
              WHEN nullif(trim(session_id), '') IS NULL THEN 1
            END) AS missing_session_rows,
            coalesce(SUM(CASE
              WHEN nullif(trim(session_id), '') IS NULL THEN total_tokens ELSE 0
            END), 0) AS missing_session_tokens,
            COUNT(DISTINCT CASE
              WHEN nullif(trim(session_id), '') IS NOT NULL
               AND nullif(trim(agent_role), '') IS NULL THEN session_id
            END) AS missing_role_spawns,
            COUNT(DISTINCT CASE
              WHEN nullif(trim(session_id), '') IS NOT NULL
               AND nullif(trim(subagent_type), '') IS NULL THEN session_id
            END) AS missing_type_spawns
        FROM {_CANONICAL_SOURCE}
        {where_sql}
        """,  # nosec B608
        params,
    ).fetchone()
    return {key: int(value) for key, value in row_to_dict(row).items()}
