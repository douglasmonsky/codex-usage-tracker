"""Materialize compact detector facts from normalized usage records."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from codex_usage_tracker.store.compression_fact_contract import (
    COMPRESSION_FACTS_VERSION,
    MIN_TOOL_OUTPUT_BYTES,
    ManifestAccumulator,
    call_revision_identity,
    command_revision_identity,
    file_revision_identity,
    fragment_revision_identity,
    tool_revision_identity,
)
from codex_usage_tracker.store.compression_fact_queries import (
    ensure_empty_target_tables,
    populate_relevant_command_roots,
    target_mode_sql,
)
from codex_usage_tracker.store.compression_schema import (
    create_compression_fact_indexes,
    drop_compression_fact_indexes,
    stamp_compression_fact_state,
)

FactStageCallback = Callable[[str], None]


def backfill_compression_detector_facts(
    conn: sqlite3.Connection,
    *,
    stage_callback: FactStageCallback | None = None,
) -> None:
    """Rebuild detector facts without reopening raw Codex logs."""
    ensure_empty_target_tables(conn)
    drop_compression_fact_indexes(conn)
    try:
        conn.execute("DELETE FROM compression_sequence_facts")
        conn.execute("DELETE FROM compression_thread_facts")
        conn.execute("DELETE FROM compression_record_facts")
        _mark_stage(stage_callback, "clear")
        _insert_record_facts(conn)
        _mark_stage(stage_callback, "record_facts")
        _update_record_manifests(conn)
        _mark_stage(stage_callback, "record_manifests")
        _insert_sequence_facts(conn)
        _mark_stage(stage_callback, "sequence_facts")
        _insert_thread_facts(conn)
        _update_thread_manifests(conn)
        _mark_stage(stage_callback, "thread_facts")
    finally:
        create_compression_fact_indexes(conn)
    _mark_stage(stage_callback, "indexes")
    stamp_compression_fact_state(conn, facts_version=COMPRESSION_FACTS_VERSION)
    _mark_stage(stage_callback, "state")


def _mark_stage(callback: FactStageCallback | None, stage: str) -> None:
    if callback is not None:
        callback(stage)


def _insert_record_facts(conn: sqlite3.Connection, *, targeted: bool = False) -> None:
    query = target_mode_sql(
        """
        INSERT INTO compression_record_facts (
            record_id, source_file, session_id, thread_key, event_timestamp,
            model, effort, is_archived, thread_call_index, previous_record_id,
            cached_input_tokens, uncached_input_tokens, output_tokens,
            reasoning_output_tokens, estimated_cost_usd, usage_credits,
            cache_ratio, context_window_percent, turn_count, indexed_call,
            tool_call_count, command_run_count, file_event_count,
            content_fragment_count, compaction_count, source_record_count,
            parser_warning_record_count, parser_adapter, parser_version,
            content_exposure_tokens,
            tool_output_exposure_tokens, manifest_count, manifest_sum_hex,
            manifest_xor_hex, facts_version, updated_at
        )
        WITH
        content AS (
            SELECT
                record_id,
                COUNT(*) AS fact_count,
                SUM((content_size_bytes + 3) / 4) AS tokens,
                SUM(CASE WHEN fragment_kind IN ('compaction', 'compaction_history')
                    THEN 1 ELSE 0 END)
                    AS compaction_count
            FROM content_fragments
                __TARGET_RECORD__
            GROUP BY record_id
        ),
        tools AS (
            SELECT
                record_id,
                COUNT(*) AS fact_count,
                SUM((output_size_bytes + 3) / 4) AS tokens
            FROM tool_calls
                __TARGET_RECORD__
            GROUP BY record_id
        ),
        commands AS (
            SELECT
                record_id,
                COUNT(*) AS fact_count,
                SUM((output_size_bytes + 3) / 4) AS tokens
            FROM command_runs
                __TARGET_RECORD__
            GROUP BY record_id
        ),
        files AS (
            SELECT record_id, COUNT(*) AS fact_count
            FROM file_events
                __TARGET_RECORD__
            GROUP BY record_id
        ),
        turns AS (
            SELECT
                record_id,
                COUNT(*) AS fact_count,
                MAX(indexed_content_included) AS indexed_call
            FROM conversation_turns
                __TARGET_RECORD__
            GROUP BY record_id
        ),
        sources AS (
            SELECT
                record_id,
                1 AS fact_count,
                CASE WHEN parse_warnings_json NOT IN ('', '[]') THEN 1 ELSE 0 END
                    AS warning_count,
                parser_adapter,
                parser_version
            FROM source_records
                __TARGET_RECORD__
        )
        SELECT
            u.record_id,
            u.source_file,
            u.session_id,
            COALESCE(u.thread_key, u.thread_name, u.session_id),
            u.event_timestamp,
            u.model,
            u.effort,
            u.is_archived,
            u.thread_call_index,
            u.previous_record_id,
            u.cached_input_tokens,
            u.uncached_input_tokens,
            u.output_tokens,
            u.reasoning_output_tokens,
            NULL,
            NULL,
            u.cache_ratio,
            u.context_window_percent,
            COALESCE(turns.fact_count, 0),
            COALESCE(turns.indexed_call, 0),
            COALESCE(tools.fact_count, 0),
            COALESCE(commands.fact_count, 0),
            COALESCE(files.fact_count, 0),
            COALESCE(content.fact_count, 0),
            COALESCE(content.compaction_count, 0),
            COALESCE(sources.fact_count, 0),
            COALESCE(sources.warning_count, 0),
            sources.parser_adapter,
            sources.parser_version,
            COALESCE(content.tokens, 0),
            MAX(COALESCE(tools.tokens, 0), COALESCE(commands.tokens, 0)),
            0,
            '',
            '',
            :facts_version,
            u.event_timestamp
        FROM usage_events AS u
        LEFT JOIN content ON content.record_id = u.record_id
        LEFT JOIN tools ON tools.record_id = u.record_id
        LEFT JOIN commands ON commands.record_id = u.record_id
        LEFT JOIN files ON files.record_id = u.record_id
        LEFT JOIN turns ON turns.record_id = u.record_id
        LEFT JOIN sources ON sources.record_id = u.record_id
            __TARGET_U_RECORD__
        """,
        targeted=targeted,
    )
    conn.execute(
        query,
        {"facts_version": COMPRESSION_FACTS_VERSION},
    )


def _insert_sequence_facts(conn: sqlite3.Connection, *, targeted: bool = False) -> None:
    populate_relevant_command_roots(conn)
    query = target_mode_sql(
        """
        INSERT INTO compression_sequence_facts (
            fact_key, record_id, thread_key, turn_key, source_order,
            fact_kind, category,
            status, duration_ms, output_size_bytes, command_label, exit_code,
            retry_group, path_identity, exposure_tokens, facts_version
        )
        SELECT
            'tool:' || t.tool_call_key,
            t.record_id,
            COALESCE(u.thread_key, u.thread_name, u.session_id),
            t.turn_key,
            t.rowid,
            'tool_output',
            t.tool_name,
            t.status,
            t.duration_ms,
            t.output_size_bytes,
            NULL,
            NULL,
            NULL,
            NULL,
            (t.output_size_bytes + 3) / 4,
            :facts_version
        FROM tool_calls AS t
        JOIN usage_events AS u ON u.record_id = t.record_id
        __TARGET_T_RECORD_AND__
        t.output_size_bytes >= :min_tool_output_bytes
        UNION ALL
        SELECT
            'command:' || c.command_run_key,
            c.record_id,
            COALESCE(u.thread_key, u.thread_name, u.session_id),
            c.turn_key,
            c.rowid,
            'command',
            c.command_root,
            c.status,
            NULL,
            c.output_size_bytes,
            c.command_root,
            c.exit_code,
            c.retry_group,
            NULL,
            (c.output_size_bytes + 3) / 4,
            :facts_version
        FROM command_runs AS c
        JOIN usage_events AS u ON u.record_id = c.record_id
        __TARGET_C_RECORD_AND__
        c.command_root IN (
            SELECT command_root FROM compression_relevant_command_roots
        )
        UNION ALL
        SELECT
            'file:' || f.file_event_key,
            f.record_id,
            COALESCE(u.thread_key, u.thread_name, u.session_id),
            f.turn_key,
            f.rowid,
            'file_read',
            f.path_hash,
            NULL,
            NULL,
            0,
            NULL,
            NULL,
            NULL,
            f.path_hash,
            0,
            :facts_version
        FROM file_events AS f
        JOIN usage_events AS u ON u.record_id = f.record_id
        __TARGET_F_RECORD_AND__
        f.operation = 'read' AND f.path_hash <> ''
        UNION ALL
        SELECT
            'content:' || f.record_id || ':' || f.turn_key,
            f.record_id,
            COALESCE(u.thread_key, u.thread_name, u.session_id),
            f.turn_key,
            MIN(f.rowid),
            'content_turn',
            '',
            NULL,
            NULL,
            SUM(f.content_size_bytes),
            NULL,
            NULL,
            NULL,
            NULL,
            SUM((f.content_size_bytes + 3) / 4),
            :facts_version
        FROM content_fragments AS f
        JOIN usage_events AS u ON u.record_id = f.record_id
        __TARGET_F_RECORD_AND__
        f.turn_key IS NOT NULL
        GROUP BY f.record_id, f.turn_key
        """,
        targeted=targeted,
    )
    conn.execute(
        query,
        {
            "facts_version": COMPRESSION_FACTS_VERSION,
            "min_tool_output_bytes": MIN_TOOL_OUTPUT_BYTES,
        },
    )


def _update_record_manifests(conn: sqlite3.Connection, *, targeted: bool = False) -> None:
    accumulators: dict[str, ManifestAccumulator] = {}
    call_query = target_mode_sql(
        """
        SELECT
            record_id, session_id, thread_key, event_timestamp, model, effort,
            is_archived, thread_call_index, previous_record_id,
            cached_input_tokens, uncached_input_tokens, output_tokens,
            reasoning_output_tokens, cache_ratio, context_window_percent
        FROM compression_record_facts
        __TARGET_RECORD__
        """,
        targeted=targeted,
    )
    call_rows = conn.execute(
        call_query,
    )
    for row in call_rows:
        record_id = str(row[0])
        accumulator = ManifestAccumulator()
        accumulator.add("call", call_revision_identity(row))
        accumulators[record_id] = accumulator

    evidence_queries = (
        (
            "tool",
            """
            SELECT tool_call_key, record_id, turn_key, tool_name, status,
                   duration_ms, output_size_bytes
            FROM tool_calls
            __TARGET_RECORD__
            """,
            tool_revision_identity,
        ),
        (
            "command",
            """
            SELECT command_run_key, record_id, turn_key, command_root,
                   command_root AS command_label, exit_code, status,
                   output_size_bytes, retry_group
            FROM command_runs
            __TARGET_RECORD__
            """,
            command_revision_identity,
        ),
        (
            "file",
            """
            SELECT file_event_key, record_id, turn_key, operation, path_hash,
                   path_hash AS path_identity
            FROM file_events
            __TARGET_RECORD__
            """,
            file_revision_identity,
        ),
        (
            "fragment",
            """
            SELECT fragment_id, record_id, turn_key, fragment_kind, role,
                   fragment_kind AS safe_label, content_hash, content_size_bytes,
                   includes_raw_fragment
            FROM content_fragments
            __TARGET_RECORD__
            """,
            fragment_revision_identity,
        ),
    )
    for kind, query, identity_builder in evidence_queries:
        scoped_query = target_mode_sql(query, targeted=targeted)
        for row in conn.execute(scoped_query):
            record_accumulator = accumulators.get(str(row[1]))
            if record_accumulator is not None:
                record_accumulator.add(kind, identity_builder(row))

    conn.executemany(
        """
        UPDATE compression_record_facts
        SET manifest_count = ?, manifest_sum_hex = ?, manifest_xor_hex = ?
        WHERE record_id = ?
        """,
        (
            (*accumulator.storage_values(), record_id)
            for record_id, accumulator in accumulators.items()
        ),
    )


def _insert_thread_facts(conn: sqlite3.Connection, *, targeted: bool = False) -> None:
    query = target_mode_sql(
        """
        INSERT INTO compression_thread_facts (
            manifest_key, thread_key, record_id, call_count, first_event_at,
            last_event_at, cached_input_tokens, uncached_input_tokens,
            output_tokens, reasoning_output_tokens, estimated_cost_usd,
            usage_credits, cache_break_count, manifest_count, manifest_sum_hex,
            manifest_xor_hex, manifest_revision, facts_version, updated_at
        )
        SELECT
            'thread:' || r.thread_key,
            r.thread_key,
            '',
            COUNT(*),
            MIN(event_timestamp),
            MAX(event_timestamp),
            SUM(cached_input_tokens),
            SUM(uncached_input_tokens),
            SUM(output_tokens),
            SUM(reasoning_output_tokens),
            SUM(estimated_cost_usd),
            SUM(usage_credits),
            0,
            SUM(manifest_count),
            '',
            '',
            '',
            :facts_version,
            MAX(updated_at)
        FROM compression_record_facts AS r
        __TARGET_R_THREAD__
        GROUP BY r.thread_key
        """,
        targeted=targeted,
    )
    conn.execute(
        query,
        {"facts_version": COMPRESSION_FACTS_VERSION},
    )


def _update_thread_manifests(conn: sqlite3.Connection, *, targeted: bool = False) -> None:
    accumulators: dict[str, ManifestAccumulator] = {}
    query = target_mode_sql(
        """
        SELECT r.record_id, r.thread_key, r.manifest_count, r.manifest_sum_hex,
               r.manifest_xor_hex
        FROM compression_record_facts AS r
        __TARGET_R_THREAD__
        """,
        targeted=targeted,
    )
    for row in conn.execute(
        query,
    ):
        thread_key = str(row[1])
        manifest_key = f"thread:{thread_key}" if thread_key else f"record:{row[0]}"
        accumulator = accumulators.setdefault(manifest_key, ManifestAccumulator())
        accumulator.merge(ManifestAccumulator.from_storage(row[2], row[3], row[4]))

    conn.executemany(
        """
        UPDATE compression_thread_facts
        SET manifest_count = ?, manifest_sum_hex = ?, manifest_xor_hex = ?,
            manifest_revision = ?
        WHERE manifest_key = ?
        """,
        (
            (*accumulator.storage_values(), accumulator.revision(), manifest_key)
            for manifest_key, accumulator in accumulators.items()
        ),
    )
