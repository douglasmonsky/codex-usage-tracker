"""R2 contract for the compact metadata-first analytical schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from codex_usage_tracker.kernel.database import initialize_analytical_database
from codex_usage_tracker.kernel.schema import (
    ANALYTICAL_TABLES,
    REQUIRED_SCHEMA_OBJECTS,
    SCHEMA_CAPABILITIES,
    SCHEMA_VERSION,
)
from codex_usage_tracker.kernel.writer import _insert_allowance_state

_FACT_TABLES = {
    "model_call_facts",
    "tool_call_facts",
    "activity_facts",
    "allowance_states",
}
_ROLLUP_TABLES = {
    "rollup_allowance",
    "rollup_cost_credits",
    "rollup_global",
    "rollup_model_effort",
    "rollup_thread",
    "rollup_time_band",
    "rollup_tool_operation",
}
_SELECTOR_VIEWS = {
    "activity_events",
    "allowance_intervals",
    "allowance_observations",
    "model_calls",
    "tool_calls",
}
_FORBIDDEN_SCHEMA_TERMS = {
    "prompt_text",
    "raw_arguments",
    "raw_content",
    "raw_output",
    "reasoning_text",
    "response_text",
    "shell_command",
}


def _columns(connection: sqlite3.Connection, table: str) -> dict[str, str]:
    return {
        str(row[1]): str(row[2]).upper()
        for row in connection.execute(f"PRAGMA table_info({table})")
    }


def _seed_generation_and_source(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO generations VALUES (
            1, 'revision', '2026-01-01T00:00:00Z', 'high-water',
            0, 0, 0, 0, 0, NULL, 'synthetic', 'valid'
        )
        """
    )
    connection.execute(
        """
        INSERT INTO sources(
            source_id,
            source_kind,
            archive_state,
            safe_label,
            size_bytes,
            parsed_byte_offset,
            parsed_line_number,
            trailing_incomplete_bytes,
            replacement_fingerprint,
            parser_adapter,
            parser_version,
            parser_state_json,
            last_generation,
            parse_warning_count,
            unsupported_shape_count
        )
        VALUES (
            'src_schema_v3', 'session', 'active', 'Synthetic source',
            100, 100, 2, 0, 'replacement', 'synthetic', '1', '{}',
            1, 0, 0
        )
        """
    )


def _seed_thread_and_call(connection: sqlite3.Connection) -> str:
    call_id = "call_" + ("04" * 16)
    connection.execute(
        """
        INSERT INTO threads(
            thread_id,
            source_key,
            source_id,
            logical_thread_id,
            session_identity_hash,
            display_label,
            archive_state,
            first_generation,
            last_generation,
            identity_basis,
            identity_confidence
        )
        SELECT
            'srcthr_06060606060606060606060606060606',
            source_key,
            source_id,
            'thr_07070707070707070707070707070707',
            'session-hash',
            'Synthetic thread',
            'active',
            1,
            1,
            'synthetic',
            'exact'
        FROM sources
        WHERE source_id = 'src_schema_v3'
        """
    )
    thread_id = str(
        connection.execute("SELECT thread_id FROM threads").fetchone()[0]
    )
    connection.execute(
        """
        INSERT INTO model_calls(
            model_call_id,
            canonical_call_id,
            source_id,
            thread_id,
            turn_id,
            event_at,
            turn_ordinal,
            model,
            effort,
            service_tier,
            origin,
            context_window,
            input_tokens,
            cached_input_tokens,
            output_tokens,
            reasoning_tokens,
            upstream_total_tokens,
            upstream_cumulative_tokens,
            rate_limit_observation_id,
            duplicate_state,
            duplicate_reason,
            fingerprint_version,
            source_offset,
            generation
        )
        VALUES (
            ?, ?, 'src_schema_v3', ?, NULL, '2026-01-01T00:01:00Z',
            1, 'gpt-synthetic', 'high', NULL, 'response_item', 100000,
            100, 75, 20, 5, 120, 120, NULL, 'canonical', NULL, 1, 10, 1
        )
        """,
        (call_id, "fp_" + ("05" * 32), thread_id),
    )
    return call_id


def test_schema_v3_declares_compact_metadata_and_rollup_contract(
    tmp_path: Path,
) -> None:
    path = tmp_path / "kernel.sqlite3"
    initialize_analytical_database(path)

    with sqlite3.connect(path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
            )
        }
        views = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'view'"
            )
        }
        objects = tables | views | {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'index'"
            )
        }

        assert SCHEMA_VERSION == 3
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert tables == ANALYTICAL_TABLES
        assert _FACT_TABLES <= tables
        assert _ROLLUP_TABLES <= tables
        assert _SELECTOR_VIEWS <= views
        assert REQUIRED_SCHEMA_OBJECTS <= objects
        assert {
            "compact-integer-foreign-keys",
            "generation-rollups",
            "allowance-state-intervals",
            "observation-trigger-not-causation",
            "metadata-only",
        } <= SCHEMA_CAPABILITIES


def test_fact_tables_use_integer_keys_and_keep_selectors_at_boundaries(
    tmp_path: Path,
) -> None:
    path = tmp_path / "kernel.sqlite3"
    initialize_analytical_database(path)

    with sqlite3.connect(path) as connection:
        source_columns = _columns(connection, "sources")
        thread_columns = _columns(connection, "threads")
        turn_columns = _columns(connection, "turns")
        call_columns = _columns(connection, "model_call_facts")
        tool_columns = _columns(connection, "tool_call_facts")

        assert source_columns["source_key"] == "INTEGER"
        assert source_columns["source_id"] == "TEXT"
        assert thread_columns["thread_key"] == "INTEGER"
        assert thread_columns["thread_id"] == "TEXT"
        assert thread_columns["source_key"] == "INTEGER"
        assert turn_columns["turn_key"] == "INTEGER"
        assert turn_columns["turn_id"] == "TEXT"
        assert turn_columns["thread_key"] == "INTEGER"

        assert {
            "model_call_key",
            "source_key",
            "thread_key",
            "turn_key",
        } <= call_columns.keys()
        assert {
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_tokens",
        } <= call_columns.keys()
        assert {"source_id", "thread_id", "turn_id"} - call_columns.keys() == {
            "source_id",
            "thread_id",
            "turn_id",
        }

        assert {"tool_call_key", "source_key", "thread_key", "turn_key"} <= (
            tool_columns.keys()
        )
        assert {"tool_profile_key", "target_label"} <= tool_columns.keys()
        assert {"operation", "tool_name"} <= _columns(
            connection,
            "tool_profiles",
        ).keys()
        assert {"source_id", "thread_id", "turn_id"} - tool_columns.keys() == {
            "source_id",
            "thread_id",
            "turn_id",
        }

        foreign_keys = {
            (str(row[2]), str(row[3]), str(row[4]))
            for table in _FACT_TABLES
            for row in connection.execute(f"PRAGMA foreign_key_list({table})")
        }
        assert ("sources", "source_key", "source_key") in foreign_keys
        assert ("threads", "thread_key", "thread_key") in foreign_keys
        assert ("turns", "turn_key", "turn_key") in foreign_keys


def test_allowance_state_contract_separates_trigger_from_causation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "kernel.sqlite3"
    initialize_analytical_database(path)

    with sqlite3.connect(path) as connection:
        columns = _columns(connection, "allowance_states")
        assert {
            "allowance_state_key",
            "first_observed_at",
            "last_observed_at",
            "observation_count",
            "observation_trigger_call_key",
            "generation",
        } <= columns.keys()
        assert "source_model_call_id" not in columns
        assert "causal_model_call_key" not in columns

        interval_columns = _columns(connection, "allowance_intervals")
        assert {
            "previous_state_key",
            "delta_used_percent",
            "elapsed_hours",
            "local_calls",
            "local_turns",
            "local_total_tokens",
        } <= interval_columns.keys()


def test_every_rollup_is_generation_scoped_and_schema_is_metadata_only(
    tmp_path: Path,
) -> None:
    path = tmp_path / "kernel.sqlite3"
    initialize_analytical_database(path)

    with sqlite3.connect(path) as connection:
        for table in _ROLLUP_TABLES:
            assert _columns(connection, table)["generation"] == "INTEGER"

        schema_sql = "\n".join(
            str(row[0] or "").lower()
            for row in connection.execute(
                "SELECT sql FROM sqlite_schema WHERE sql IS NOT NULL"
            )
        )
        assert not (_FORBIDDEN_SCHEMA_TERMS & set(schema_sql.split()))
        for forbidden in _FORBIDDEN_SCHEMA_TERMS:
            assert forbidden not in schema_sql


def test_unchanged_allowance_snapshots_compact_into_one_state(
    tmp_path: Path,
) -> None:
    path = tmp_path / "kernel.sqlite3"
    initialize_analytical_database(path)
    first = {
        "allowance_observation_id": "allow_" + ("01" * 16),
        "source_id": "src_schema_v3",
        "observed_at": "2026-01-01T00:00:00Z",
        "window_kind": "weekly",
        "limit_id": "synthetic-limit",
        "plan_type": "synthetic",
        "used_percent": 25.0,
        "duration_minutes": 10_080,
        "resets_at": "2026-01-08T00:00:00Z",
        "model": "gpt-synthetic",
        "service_tier": None,
        "source_model_call_id": None,
        "generation": 1,
        "duplicate_state": "canonical",
        "provenance": "synthetic",
        "validation_warnings": "[]",
    }
    second = {
        **first,
        "allowance_observation_id": "allow_" + ("02" * 16),
        "observed_at": "2026-01-01T00:05:00Z",
    }
    changed = {
        **second,
        "allowance_observation_id": "allow_" + ("03" * 16),
        "observed_at": "2026-01-01T00:10:00Z",
        "used_percent": 27.0,
    }

    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _seed_generation_and_source(connection)
        assert _insert_allowance_state(connection, first) == 1
        assert _insert_allowance_state(connection, second) == 0
        assert _insert_allowance_state(connection, changed) == 1
        connection.commit()

        states = connection.execute(
            """
            SELECT
                first_observed_at,
                last_observed_at,
                observation_count,
                used_percent
            FROM allowance_states
            ORDER BY allowance_state_key
            """
        ).fetchall()
        assert states == [
            (
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:05:00Z",
                2,
                25.0,
            ),
            (
                "2026-01-01T00:10:00Z",
                "2026-01-01T00:10:00Z",
                1,
                27.0,
            ),
        ]
        interval = connection.execute(
            """
            SELECT previous_state_key, delta_used_percent
            FROM allowance_intervals
            WHERE used_percent = 27.0
            """
        ).fetchone()
        assert interval is not None
        assert interval[0] is not None
        assert interval[1] == 2.0


def test_stable_selectors_and_generation_rollups_recompute_exactly(
    tmp_path: Path,
) -> None:
    path = tmp_path / "kernel.sqlite3"
    initialize_analytical_database(path)

    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _seed_generation_and_source(connection)
        call_id = _seed_thread_and_call(connection)
        stored = connection.execute(
            """
            SELECT
                model_call_id,
                input_tokens,
                cached_input_tokens,
                output_tokens,
                reasoning_tokens
            FROM model_calls
            """
        ).fetchone()
        assert stored == (call_id, 100, 75, 20, 5)

        manual = connection.execute(
            """
            SELECT
                COUNT(*),
                SUM(input_tokens),
                SUM(cached_input_tokens),
                SUM(output_tokens),
                SUM(reasoning_tokens)
            FROM model_calls
            WHERE generation = 1
              AND duplicate_state = 'canonical'
            """
        ).fetchone()
        connection.execute(
            """
            INSERT INTO rollup_global VALUES (?, ?, ?, ?, ?, ?)
            """,
            (1, *manual),
        )
        recomputed = connection.execute(
            """
            SELECT
                calls,
                input_tokens,
                cached_input_tokens,
                output_tokens,
                reasoning_tokens
            FROM rollup_global
            WHERE generation = 1
            """
        ).fetchone()
        assert recomputed == manual
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO rollup_global VALUES (2, 0, 0, 0, 0, 0)
                """
            )
