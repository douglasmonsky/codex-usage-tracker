"""Generation-scoped persisted rollups for bounded common reads."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .database import open_read_snapshot, short_writer_transaction


def generation_rollups_ready(path: Path, generation: int) -> bool:
    """Return whether the atomic rollup marker exists for one generation."""

    if generation < 1 or not path.is_file():
        return False
    with open_read_snapshot(path) as connection:
        return (
            connection.execute(
                "SELECT 1 FROM rollup_global WHERE generation = ?",
                (generation,),
            ).fetchone()
            is not None
        )


def rebuild_generation_rollups(
    path: Path,
    generation: int,
    *,
    incremental_from: int | None = None,
) -> float:
    """Replace one unpublished generation's deterministic metadata rollups."""

    started = time.perf_counter()
    with short_writer_transaction(path) as connection:
        _link_unresolved_tool_calls(connection, generation)
        for table in (
            "rollup_global",
            "rollup_thread",
            "rollup_model_effort",
            "rollup_time_band",
            "rollup_tool_operation",
        ):
            connection.execute(
                f"DELETE FROM {table} WHERE generation = ?",
                (generation,),
            )
        if incremental_from is not None:
            marker = connection.execute(
                "SELECT 1 FROM rollup_global WHERE generation = ?",
                (incremental_from,),
            ).fetchone()
            if marker is None:
                raise ValueError("incremental rollup seed is unavailable")
            _seed_generation_rollups(
                connection,
                generation=generation,
                prior_generation=incremental_from,
            )
            _apply_generation_delta(connection, generation=generation)
            return (time.perf_counter() - started) * 1_000
        connection.execute(
            """
            INSERT INTO rollup_global(
                generation, calls, input_tokens, cached_input_tokens,
                output_tokens, reasoning_tokens
            )
            SELECT ?, COUNT(*), COALESCE(SUM(input_tokens), 0),
                   COALESCE(SUM(cached_input_tokens), 0),
                   COALESCE(SUM(output_tokens), 0),
                   COALESCE(SUM(reasoning_tokens), 0)
            FROM model_call_facts
            WHERE generation <= ? AND duplicate_state = 'canonical'
            """,
            (generation, generation),
        )
        connection.execute(
            """
            INSERT INTO rollup_thread(
                generation, thread_key, calls, input_tokens,
                cached_input_tokens, output_tokens, reasoning_tokens
            )
            SELECT ?, thread_key, COUNT(*), SUM(input_tokens),
                   SUM(cached_input_tokens), SUM(output_tokens),
                   SUM(reasoning_tokens)
            FROM model_call_facts
            WHERE generation <= ? AND duplicate_state = 'canonical'
            GROUP BY thread_key
            """,
            (generation, generation),
        )
        connection.execute(
            """
            INSERT INTO rollup_model_effort(
                generation, model, effort, service_tier, calls,
                input_tokens, cached_input_tokens, output_tokens,
                reasoning_tokens
            )
            SELECT ?, profiles.model, profiles.effort_key,
                   profiles.service_tier_key, COUNT(*), SUM(facts.input_tokens),
                   SUM(facts.cached_input_tokens), SUM(facts.output_tokens),
                   SUM(facts.reasoning_tokens)
            FROM model_call_facts AS facts
            JOIN model_profiles AS profiles USING (model_profile_key)
            WHERE facts.generation <= ?
              AND facts.duplicate_state = 'canonical'
            GROUP BY profiles.model, profiles.effort_key,
                     profiles.service_tier_key
            """,
            (generation, generation),
        )
        connection.execute(
            """
            INSERT INTO rollup_time_band(
                generation, band_kind, band_start, calls, input_tokens,
                cached_input_tokens, output_tokens, reasoning_tokens
            )
            SELECT ?, bands.band_kind, bands.band_start, COUNT(*),
                   SUM(bands.input_tokens), SUM(bands.cached_input_tokens),
                   SUM(bands.output_tokens), SUM(bands.reasoning_tokens)
            FROM (
                SELECT 'day' AS band_kind, substr(event_at, 1, 10) AS band_start,
                       input_tokens, cached_input_tokens, output_tokens,
                       reasoning_tokens
                FROM model_call_facts
                WHERE generation <= ? AND duplicate_state = 'canonical'
                UNION ALL
                SELECT 'hour', substr(event_at, 1, 13) || ':00:00Z',
                       input_tokens, cached_input_tokens, output_tokens,
                       reasoning_tokens
                FROM model_call_facts
                WHERE generation <= ? AND duplicate_state = 'canonical'
            ) AS bands
            GROUP BY bands.band_kind, bands.band_start
            """,
            (generation, generation, generation),
        )
        connection.execute(
            """
            INSERT INTO rollup_tool_operation(
                generation, operation, target_label, calls,
                duration_ms, output_bytes
            )
            SELECT ?, profiles.operation, COALESCE(facts.target_label, ''),
                   COUNT(*), COALESCE(SUM(facts.duration_ms), 0.0),
                   COALESCE(SUM(facts.output_bytes), 0)
            FROM tool_call_facts AS facts
            JOIN tool_profiles AS profiles USING (tool_profile_key)
            WHERE facts.generation <= ?
            GROUP BY profiles.operation, COALESCE(facts.target_label, '')
            """,
            (generation, generation),
        )
    return (time.perf_counter() - started) * 1_000


def _link_unresolved_tool_calls(
    connection: sqlite3.Connection,
    generation: int,
) -> None:
    connection.execute(
        """
        UPDATE tool_call_facts AS tools
        SET nearest_model_call_key = COALESCE(
            (
                SELECT calls.model_call_key
                FROM model_call_facts AS calls
                WHERE calls.turn_key = tools.turn_key
                  AND calls.generation <= ?
                  AND calls.duplicate_state = 'canonical'
                  AND calls.event_at >= COALESCE(
                      tools.ended_at,
                      tools.started_at,
                      ''
                  )
                ORDER BY calls.event_at, calls.model_call_key
                LIMIT 1
            ),
            (
                SELECT calls.model_call_key
                FROM model_call_facts AS calls
                WHERE calls.turn_key = tools.turn_key
                  AND calls.generation <= ?
                  AND calls.duplicate_state = 'canonical'
                  AND calls.event_at < COALESCE(
                      tools.ended_at,
                      tools.started_at,
                      ''
                  )
                ORDER BY calls.event_at DESC, calls.model_call_key DESC
                LIMIT 1
            )
        ),
            generation = ?
        WHERE tools.generation <= ?
          AND EXISTS (
              SELECT 1
              FROM model_call_facts AS changed_calls
              WHERE changed_calls.turn_key = tools.turn_key
                AND changed_calls.generation = ?
                AND changed_calls.duplicate_state = 'canonical'
          )
        """,
        (generation, generation, generation, generation, generation),
    )


def _seed_generation_rollups(
    connection: sqlite3.Connection,
    *,
    generation: int,
    prior_generation: int,
) -> None:
    connection.execute(
        """
        INSERT INTO rollup_global
        SELECT ?, calls, input_tokens, cached_input_tokens,
               output_tokens, reasoning_tokens
        FROM rollup_global
        WHERE generation = ?
        """,
        (generation, prior_generation),
    )
    connection.execute(
        """
        INSERT INTO rollup_thread
        SELECT ?, thread_key, calls, input_tokens, cached_input_tokens,
               output_tokens, reasoning_tokens
        FROM rollup_thread
        WHERE generation = ?
        """,
        (generation, prior_generation),
    )
    connection.execute(
        """
        INSERT INTO rollup_model_effort
        SELECT ?, model, effort, service_tier, calls, input_tokens,
               cached_input_tokens, output_tokens, reasoning_tokens
        FROM rollup_model_effort
        WHERE generation = ?
        """,
        (generation, prior_generation),
    )
    connection.execute(
        """
        INSERT INTO rollup_time_band
        SELECT ?, band_kind, band_start, calls, input_tokens,
               cached_input_tokens, output_tokens, reasoning_tokens
        FROM rollup_time_band
        WHERE generation = ?
        """,
        (generation, prior_generation),
    )
    connection.execute(
        """
        INSERT INTO rollup_tool_operation
        SELECT ?, operation, target_label, calls, duration_ms, output_bytes
        FROM rollup_tool_operation
        WHERE generation = ?
        """,
        (generation, prior_generation),
    )


def _apply_generation_delta(
    connection: sqlite3.Connection,
    *,
    generation: int,
) -> None:
    connection.execute(
        """
        INSERT INTO rollup_global(
            generation, calls, input_tokens, cached_input_tokens,
            output_tokens, reasoning_tokens
        )
        SELECT ?, COUNT(*), COALESCE(SUM(input_tokens), 0),
               COALESCE(SUM(cached_input_tokens), 0),
               COALESCE(SUM(output_tokens), 0),
               COALESCE(SUM(reasoning_tokens), 0)
        FROM model_call_facts
        WHERE generation = ? AND duplicate_state = 'canonical'
        ON CONFLICT(generation) DO UPDATE SET
            calls = calls + excluded.calls,
            input_tokens = input_tokens + excluded.input_tokens,
            cached_input_tokens =
                cached_input_tokens + excluded.cached_input_tokens,
            output_tokens = output_tokens + excluded.output_tokens,
            reasoning_tokens = reasoning_tokens + excluded.reasoning_tokens
        """,
        (generation, generation),
    )
    connection.execute(
        """
        INSERT INTO rollup_thread(
            generation, thread_key, calls, input_tokens,
            cached_input_tokens, output_tokens, reasoning_tokens
        )
        SELECT ?, thread_key, COUNT(*), SUM(input_tokens),
               SUM(cached_input_tokens), SUM(output_tokens),
               SUM(reasoning_tokens)
        FROM model_call_facts
        WHERE generation = ? AND duplicate_state = 'canonical'
        GROUP BY thread_key
        ON CONFLICT(generation, thread_key) DO UPDATE SET
            calls = calls + excluded.calls,
            input_tokens = input_tokens + excluded.input_tokens,
            cached_input_tokens =
                cached_input_tokens + excluded.cached_input_tokens,
            output_tokens = output_tokens + excluded.output_tokens,
            reasoning_tokens = reasoning_tokens + excluded.reasoning_tokens
        """,
        (generation, generation),
    )
    connection.execute(
        """
        INSERT INTO rollup_model_effort(
            generation, model, effort, service_tier, calls,
            input_tokens, cached_input_tokens, output_tokens,
            reasoning_tokens
        )
        SELECT ?, profiles.model, profiles.effort_key,
               profiles.service_tier_key, COUNT(*), SUM(facts.input_tokens),
               SUM(facts.cached_input_tokens), SUM(facts.output_tokens),
               SUM(facts.reasoning_tokens)
        FROM model_call_facts AS facts
        JOIN model_profiles AS profiles USING (model_profile_key)
        WHERE facts.generation = ?
          AND facts.duplicate_state = 'canonical'
        GROUP BY profiles.model, profiles.effort_key,
                 profiles.service_tier_key
        ON CONFLICT(generation, model, effort, service_tier) DO UPDATE SET
            calls = calls + excluded.calls,
            input_tokens = input_tokens + excluded.input_tokens,
            cached_input_tokens =
                cached_input_tokens + excluded.cached_input_tokens,
            output_tokens = output_tokens + excluded.output_tokens,
            reasoning_tokens = reasoning_tokens + excluded.reasoning_tokens
        """,
        (generation, generation),
    )
    connection.execute(
        """
        INSERT INTO rollup_time_band(
            generation, band_kind, band_start, calls, input_tokens,
            cached_input_tokens, output_tokens, reasoning_tokens
        )
        SELECT ?, bands.band_kind, bands.band_start, COUNT(*),
               SUM(bands.input_tokens), SUM(bands.cached_input_tokens),
               SUM(bands.output_tokens), SUM(bands.reasoning_tokens)
        FROM (
            SELECT 'day' AS band_kind, substr(event_at, 1, 10) AS band_start,
                   input_tokens, cached_input_tokens, output_tokens,
                   reasoning_tokens
            FROM model_call_facts
            WHERE generation = ? AND duplicate_state = 'canonical'
            UNION ALL
            SELECT 'hour', substr(event_at, 1, 13) || ':00:00Z',
                   input_tokens, cached_input_tokens, output_tokens,
                   reasoning_tokens
            FROM model_call_facts
            WHERE generation = ? AND duplicate_state = 'canonical'
        ) AS bands
        GROUP BY bands.band_kind, bands.band_start
        ON CONFLICT(generation, band_kind, band_start) DO UPDATE SET
            calls = calls + excluded.calls,
            input_tokens = input_tokens + excluded.input_tokens,
            cached_input_tokens =
                cached_input_tokens + excluded.cached_input_tokens,
            output_tokens = output_tokens + excluded.output_tokens,
            reasoning_tokens = reasoning_tokens + excluded.reasoning_tokens
        """,
        (generation, generation, generation),
    )
    connection.execute(
        "DELETE FROM rollup_tool_operation WHERE generation = ?",
        (generation,),
    )
    connection.execute(
        """
        INSERT INTO rollup_tool_operation(
            generation, operation, target_label, calls,
            duration_ms, output_bytes
        )
        SELECT ?, profiles.operation, COALESCE(facts.target_label, ''),
               COUNT(*), COALESCE(SUM(facts.duration_ms), 0.0),
               COALESCE(SUM(facts.output_bytes), 0)
        FROM tool_call_facts AS facts
        JOIN tool_profiles AS profiles USING (tool_profile_key)
        WHERE facts.generation <= ?
        GROUP BY profiles.operation, COALESCE(facts.target_label, '')
        """,
        (generation, generation),
    )
