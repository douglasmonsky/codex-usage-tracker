from __future__ import annotations

import importlib
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_EXPERIMENT_ROOT = _REPO_ROOT / "experiments" / "physical-architecture"
sys.path.insert(0, str(_EXPERIMENT_ROOT))

shared = importlib.import_module("shared")
candidate_a = importlib.import_module("candidate_a")
adapter_module = importlib.import_module("candidate_a.adapter")
evidence_module = importlib.import_module("candidate_a.evidence")
maintenance_module = importlib.import_module("candidate_a.maintenance")
queries_module = importlib.import_module("candidate_a.queries")
schema_module = importlib.import_module("candidate_a.schema")

apply_ordinary_change = maintenance_module.apply_ordinary_change
database = schema_module.database

_TINY_FIXTURE = _REPO_ROOT / "tests" / "agent_kernel" / "fixtures" / "tiny-v1"


@pytest.fixture
def fixture() -> Any:
    return shared.load_fixture_bundle(_TINY_FIXTURE)


def _tool_family_rows(connection: Any) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(
            """
            SELECT
                transport_name, semantic_operation,
                count(*) AS calls,
                sum(CASE WHEN state='failed' THEN 1 ELSE 0 END) AS failures,
                sum(duration_us) AS duration_us,
                sum(output_bytes) AS output_bytes
            FROM tool_invocations
            GROUP BY transport_name, semantic_operation
            ORDER BY transport_name, semantic_operation
            """
        )
    ]


def _tool_family_projection_rows(connection: Any) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(
            """
            SELECT
                transport_name, semantic_operation, calls, failures,
                duration_us, output_bytes
            FROM tool_family_current
            ORDER BY transport_name, semantic_operation
            """
        )
    ]


def test_model_call_indexes_only_cover_live_query_consumers(
    fixture: Any,
    tmp_path: Path,
) -> None:
    artifact = candidate_a.build_artifact(fixture, tmp_path / "candidate-a.sqlite")
    with database(artifact.path, read_only=True) as connection:
        indexes = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_schema
                WHERE type='index' AND tbl_name='model_calls'
                """
            )
        }

    assert {"model_calls_timeline", "model_calls_by_session"} <= indexes
    assert "model_calls_by_turn" not in indexes
    assert "model_calls_by_model_effort" not in indexes


def test_pending_tool_lookup_stays_indexed_with_closed_history(
    fixture: Any,
    tmp_path: Path,
) -> None:
    artifact = candidate_a.build_artifact(fixture, tmp_path / "candidate-a.sqlite")
    with database(artifact.path) as connection:
        connection.execute(
            """
            WITH RECURSIVE sequence(value) AS (
                VALUES (1)
                UNION ALL
                SELECT value + 1 FROM sequence WHERE value < 2000
            ),
            base AS (
                SELECT *
                FROM tool_invocations
                WHERE terminal_at_us IS NOT NULL
                LIMIT 1
            )
            INSERT INTO tool_invocations(
                tool_id, session_id, turn_id, transport_name,
                semantic_operation, resource_id, write_intent, state,
                start_at_us, start_source_rank,
                start_occurrence_source_key, start_source_order,
                start_event_kind_order, start_record_ordinal,
                start_byte_start, start_byte_end,
                terminal_at_us, terminal_source_rank,
                terminal_occurrence_source_key, terminal_source_order,
                terminal_event_kind_order, terminal_record_ordinal,
                terminal_byte_start, terminal_byte_end,
                duration_us, output_bytes
            )
            SELECT
                printf('tool:synthetic-closed:%06d', sequence.value),
                base.session_id, base.turn_id, base.transport_name,
                base.semantic_operation, base.resource_id,
                base.write_intent, base.state,
                base.start_at_us + sequence.value,
                base.start_source_rank,
                base.start_occurrence_source_key,
                base.start_source_order + sequence.value,
                base.start_event_kind_order,
                base.start_record_ordinal + sequence.value,
                base.start_byte_start, base.start_byte_end,
                base.terminal_at_us + sequence.value,
                base.terminal_source_rank,
                base.terminal_occurrence_source_key,
                base.terminal_source_order + sequence.value,
                base.terminal_event_kind_order,
                base.terminal_record_ordinal + sequence.value,
                base.terminal_byte_start, base.terminal_byte_end,
                base.duration_us, base.output_bytes
            FROM sequence CROSS JOIN base
            """
        )
        plans = tuple(
            str(row[3])
            for row in connection.execute(
                "EXPLAIN QUERY PLAN " + maintenance_module._PENDING_TOOL_SQL  # noqa: SLF001
            )
        )
        pending = connection.execute(
            maintenance_module._PENDING_TOOL_SQL  # noqa: SLF001
        ).fetchone()

    assert pending is not None
    assert any("tools_pending_start" in plan for plan in plans), plans
    assert not any(
        plan == "SCAN tool_invocations"
        or (
            plan.startswith("SCAN tool_invocations USING INDEX")
            and "tools_pending_start" not in plan
        )
        for plan in plans
    ), plans
    assert not any("USE TEMP B-TREE" in plan for plan in plans), plans


def test_bulk_call_tail_uses_one_set_sized_bounded_tail_insert(
    fixture: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = candidate_a.build_artifact(fixture, tmp_path / "bulk-tail.sqlite")
    statements: list[str] = []
    original_open_database = maintenance_module.open_database

    def traced_open_database(*args: Any, **kwargs: Any) -> Any:
        connection = original_open_database(*args, **kwargs)

        def capture_bulk_insert(statement: str) -> None:
            if not statements and "INSERT INTO MODEL_CALL_TAIL" in " ".join(
                statement.upper().split()
            ):
                statements.append(statement)
                connection.set_trace_callback(None)

        connection.set_trace_callback(capture_bulk_insert)
        return connection

    monkeypatch.setattr(maintenance_module, "open_database", traced_open_database)
    stats = apply_ordinary_change(artifact.path, "2000_call_tail")
    model_call_inserts = [
        statement
        for statement in statements
        if "INSERT INTO MODEL_CALL_TAIL" in " ".join(statement.upper().split())
    ]

    assert len(model_call_inserts) == 1
    assert stats.facts_inserted == 2_000
    assert stats.dirty_keys == 6


def test_model_call_tail_is_append_only_and_cross_table_unique(
    fixture: Any,
    tmp_path: Path,
) -> None:
    artifact = candidate_a.build_artifact(fixture, tmp_path / "tail-contract.sqlite")
    with database(artifact.path, read_only=True) as connection:
        base_before = int(connection.execute("SELECT count(*) FROM model_calls").fetchone()[0])
        visible_before = int(
            connection.execute("SELECT count(*) FROM model_calls_visible").fetchone()[0]
        )

    stats = apply_ordinary_change(artifact.path, "2000_call_tail")
    assert stats.facts_inserted == 2_000

    with database(artifact.path) as connection:
        assert connection.execute("SELECT count(*) FROM model_calls").fetchone()[0] == base_before
        assert connection.execute("SELECT count(*) FROM model_call_tail").fetchone()[0] == 2_000
        assert (
            connection.execute("SELECT count(*) FROM model_calls_visible").fetchone()[0]
            == visible_before + 2_000
        )
        assert (
            connection.execute(
                "SELECT row_count FROM model_call_tail_state WHERE singleton=1"
            ).fetchone()[0]
            == 2_000
        )
        with pytest.raises(sqlite3.IntegrityError, match="cross-table"):
            connection.execute("INSERT INTO model_call_tail SELECT * FROM model_calls LIMIT 1")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE model_call_tail SET model=model WHERE call_id=("
                "SELECT call_id FROM model_call_tail LIMIT 1)"
            )


def test_model_call_tail_ceiling_requests_an_isolated_fold_and_keeps_gates(
    fixture: Any,
    tmp_path: Path,
) -> None:
    artifact = candidate_a.build_artifact(fixture, tmp_path / "tail-ceiling.sqlite")
    batch_count = schema_module.MODEL_CALL_TAIL_MAX_ROWS // 2_000
    assert batch_count * 2_000 == schema_module.MODEL_CALL_TAIL_MAX_ROWS
    for _ in range(batch_count):
        apply_ordinary_change(artifact.path, "2000_call_tail")

    with database(artifact.path, read_only=True) as connection:
        tail_count = int(connection.execute("SELECT count(*) FROM model_call_tail").fetchone()[0])
        total_calls = int(
            connection.execute("SELECT count(*) FROM model_calls_visible").fetchone()[0]
        )
        projected_calls = int(
            connection.execute(
                "SELECT calls FROM usage_total_current WHERE singleton=1"
            ).fetchone()[0]
        )
        context_rows = queries_module._bounded_plan_rows(  # noqa: SLF001
            connection,
            plan_id="context_pressure_trajectory",
            sql=queries_module._PLAN_SQL[  # noqa: SLF001
                "context_pressure_trajectory"
            ],
        )
        context_columns = tuple(context_rows[0])
        jump_rows = queries_module._bounded_plan_rows(  # noqa: SLF001
            connection,
            plan_id="uncached_input_jumps",
            sql=queries_module._PLAN_SQL["uncached_input_jumps"],  # noqa: SLF001
        )
        jump_columns = tuple(jump_rows[0])
        question_result = queries_module.run_question(
            connection,
            fixture,
            question_id="Q-CTX-02",
            plan_id="context_pressure_trajectory",
        )
        page = evidence_module.evidence_page(
            connection,
            publication_id=artifact.publication_id,
            page_size=100,
        )

    assert tail_count == schema_module.MODEL_CALL_TAIL_MAX_ROWS
    assert projected_calls == total_calls
    assert context_columns == (
        "session_id",
        "call_id",
        "event_at_us",
        "context_window_tokens",
        "uncached_input_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "output_tokens",
    )
    assert jump_columns == (
        "session_id",
        "call_id",
        "event_at_us",
        "uncached_input_tokens",
    )
    assert question_result.rows_scanned <= 102
    assert len(question_result.encoded) <= 16_384
    assert question_result.full_scan_count == 0
    assert question_result.temporary_sort_count == 0
    assert page.full_scan_count == 0
    assert page.temporary_sort_count == 0
    with pytest.raises(
        maintenance_module.TailFoldRequired,
        match="isolated artifact fold required",
    ):
        apply_ordinary_change(artifact.path, "one_model_call")
    with (
        database(artifact.path) as connection,
        pytest.raises(
            sqlite3.IntegrityError,
            match="isolated artifact fold required",
        ),
    ):
        connection.execute(
            """
            INSERT INTO model_call_tail
            SELECT
                'overflow:' || call_id,
                session_id, turn_id, model, reasoning_effort,
                context_window_tokens, uncached_input_tokens,
                cached_input_tokens, reasoning_tokens, output_tokens,
                event_at_us, source_rank, occurrence_source_key,
                source_order, event_kind_order,
                record_ordinal, byte_start, byte_end
            FROM model_calls
            LIMIT 1
            """
        )


def test_adapter_reports_tail_fold_as_a_measured_outcome(
    fixture: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = next(
        case
        for case in shared.build_workload_matrix(physical_cores=4).cases
        if case.parameter("change") == "one_model_call"
    )
    run_root = tmp_path / "adapter-fold"
    run_root.mkdir()
    request = shared.CandidateRequest(
        case=case,
        fixture=fixture,
        run_root=run_root,
        repetition=0,
        stop=shared.EarlyStopController(case.case_id, case.early_stop_limits),
    )

    def require_fold(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise maintenance_module.TailFoldRequired(
            current_rows=schema_module.MODEL_CALL_TAIL_MAX_ROWS,
            requested_rows=1,
        )

    monkeypatch.setattr(adapter_module, "apply_ordinary_change", require_fold)
    result = adapter_module.Adapter().execute(request)

    assert result.outcome is shared.RunOutcome.FAILED
    assert result.detail_code == "candidate_a.tail_fold_required"
    assert result.measurements.sql_statements == 1
    assert result.publication is not None
    assert result.oracle_results == {
        "change": "one_model_call",
        "tail_fold_required": True,
        "tail_rows": schema_module.MODEL_CALL_TAIL_MAX_ROWS,
        "requested_rows": 1,
        "maximum_rows": schema_module.MODEL_CALL_TAIL_MAX_ROWS,
        "fold_mode": "isolated_artifact",
    }


@pytest.mark.parametrize(
    ("change", "expected_dirty_keys"),
    [
        ("one_tool_start", 4),
        ("tool_plus_state_change", 4),
        ("tool_terminal_transition", 3),
    ],
)
def test_tool_tails_use_deltas_without_fact_projection_rescans(
    fixture: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
    expected_dirty_keys: int,
) -> None:
    artifact = candidate_a.build_artifact(fixture, tmp_path / f"{change}.sqlite")
    statements: list[str] = []
    original_open_database = maintenance_module.open_database

    def traced_open_database(*args: Any, **kwargs: Any) -> Any:
        connection = original_open_database(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(maintenance_module, "open_database", traced_open_database)
    stats = apply_ordinary_change(artifact.path, change)

    normalized = (" ".join(statement.upper().split()) for statement in statements)
    projection_statements = tuple(
        statement
        for statement in normalized
        if "TOOL_FAMILY_CURRENT" in statement or "TURN_ACTION_CURRENT" in statement
    )
    assert not any(
        "FROM TOOL_INVOCATIONS" in statement or "FROM STATE_CHANGES" in statement
        for statement in projection_statements
    ), projection_statements
    assert stats.dirty_keys == expected_dirty_keys
    assert stats.projection_rows_read == expected_dirty_keys
    assert stats.projection_rows_written == expected_dirty_keys

    with database(artifact.path, read_only=True) as connection:
        assert _tool_family_projection_rows(connection) == _tool_family_rows(connection)
