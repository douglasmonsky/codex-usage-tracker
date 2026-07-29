from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_EXPERIMENT_ROOT = _REPO_ROOT / "experiments" / "physical-architecture"
sys.path.insert(0, str(_EXPERIMENT_ROOT))

shared = importlib.import_module("shared")
candidate_a = importlib.import_module("candidate_a")
evidence_module = importlib.import_module("candidate_a.evidence")
maintenance_module = importlib.import_module("candidate_a.maintenance")
metrics_module = importlib.import_module("candidate_a.metrics")
queries_module = importlib.import_module("candidate_a.queries")
schema_module = importlib.import_module("candidate_a.schema")

all_evidence_rows = evidence_module.all_evidence_rows
apply_ordinary_change = maintenance_module.apply_ordinary_change
database = schema_module.database
run_bounded_sort = queries_module.run_bounded_sort
run_evidence_feature = queries_module.run_evidence_feature

_TINY_FIXTURE = _REPO_ROOT / "tests" / "agent_kernel" / "fixtures" / "tiny-v1"

_FACT_SQL = {
    "current_usage": """
        SELECT
            count(*) AS calls,
            coalesce(sum(uncached_input_tokens), 0) AS uncached_input_tokens,
            coalesce(sum(cached_input_tokens), 0) AS cached_input_tokens,
            coalesce(sum(reasoning_tokens), 0) AS reasoning_tokens,
            coalesce(sum(output_tokens), 0) AS output_tokens
        FROM model_calls_visible
    """,
    "model_effort_mix": """
        SELECT
            model, reasoning_effort, count(*) AS calls,
            coalesce(sum(uncached_input_tokens), 0) AS uncached_input_tokens,
            coalesce(sum(cached_input_tokens), 0) AS cached_input_tokens,
            coalesce(sum(reasoning_tokens), 0) AS reasoning_tokens,
            coalesce(sum(output_tokens), 0) AS output_tokens
        FROM model_calls_visible
        GROUP BY model, reasoning_effort
        ORDER BY uncached_input_tokens DESC, model, reasoning_effort
        LIMIT 25
    """,
    "project_family_usage": """
        WITH RECURSIVE family(session_id, root_session_id) AS (
            SELECT session_id, session_id
            FROM sessions
            WHERE parent_session_id IS NULL
            UNION ALL
            SELECT child.session_id, family.root_session_id
            FROM sessions AS child
            JOIN family ON child.parent_session_id = family.session_id
        )
        SELECT
            family.root_session_id,
            coalesce(sum(usage.calls), 0) AS calls,
            coalesce(sum(usage.uncached_input_tokens), 0)
                AS uncached_input_tokens,
            coalesce(sum(usage.cached_input_tokens), 0)
                AS cached_input_tokens,
            coalesce(sum(usage.reasoning_tokens), 0) AS reasoning_tokens,
            coalesce(sum(usage.output_tokens), 0) AS output_tokens
        FROM family
        JOIN session_usage_current AS usage USING (session_id)
        GROUP BY family.root_session_id
        ORDER BY uncached_input_tokens DESC, family.root_session_id
        LIMIT 25
    """,
    "pricing_coverage": """
        SELECT
            model,
            count(*) AS calls,
            sum(CASE WHEN model = 'synthetic-unpriced' THEN 0 ELSE 1 END)
                AS rated_calls
        FROM model_calls_visible
        GROUP BY model
        ORDER BY calls DESC, model
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
}


@pytest.fixture
def fixture() -> Any:
    return shared.load_fixture_bundle(_TINY_FIXTURE)


@pytest.fixture
def built(
    fixture: Any,
    tmp_path: Path,
) -> tuple[Any, Any]:
    artifact = candidate_a.build_artifact(fixture, tmp_path / "candidate-a.sqlite")
    return fixture, artifact


def _rows(connection: Any, sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(sql)]


def _assert_projection_equivalence(connection: Any) -> None:
    for plan_id, fact_sql in _FACT_SQL.items():
        assert _rows(connection, queries_module._PLAN_SQL[plan_id]) == _rows(  # noqa: SLF001
            connection,
            fact_sql,
        )


def test_growth_sensitive_question_plans_use_exact_current_projections(
    built: tuple[Any, Any],
) -> None:
    _, artifact = built
    with database(artifact.path, read_only=True) as connection:
        expected_tables = {
            "usage_total_current",
            "model_effort_usage_current",
            "project_family_usage_current",
            "model_usage_current",
            "turn_action_current",
            "resource_operation_current",
        }
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            )
        }
        assert expected_tables <= tables
        _assert_projection_equivalence(connection)

        for plan_id in _FACT_SQL:
            plans = queries_module._plan(  # noqa: SLF001
                connection,
                queries_module._PLAN_SQL[plan_id],  # noqa: SLF001
            )
            full_scans, temporary_sorts = queries_module._plan_counts(plans)  # noqa: SLF001
            assert full_scans == 0, (plan_id, plans)
            assert temporary_sorts == 0, (plan_id, plans)

    metrics = metrics_module.artifact_metrics(artifact.path, occurrence_rows=0)
    with database(artifact.path, read_only=True) as connection:
        recorded_projection_rows = int(
            connection.execute(
                "SELECT value FROM metadata WHERE key='projection_rows'"
            ).fetchone()[0]
        )
    assert metrics.projection_rows == recorded_projection_rows


@pytest.mark.parametrize(
    ("change", "expected_dirty_keys", "expected_projection_writes"),
    [
        ("one_model_call", 6, 6),
        ("2000_call_tail", 6, 6),
        ("late_event", 6, 6),
        ("one_tool_start", 4, 4),
        ("tool_plus_state_change", 4, 4),
        ("tool_terminal_transition", 3, 3),
    ],
)
def test_ordinary_changes_keep_current_projections_exact_with_bounded_fanout(
    fixture: Any,
    tmp_path: Path,
    change: str,
    expected_dirty_keys: int,
    expected_projection_writes: int,
) -> None:
    artifact = candidate_a.build_artifact(fixture, tmp_path / f"{change}.sqlite")

    stats = apply_ordinary_change(artifact.path, change)

    assert stats.dirty_keys == expected_dirty_keys
    assert stats.projection_rows_read == expected_projection_writes
    assert stats.projection_rows_written == expected_projection_writes
    with database(artifact.path, read_only=True) as connection:
        _assert_projection_equivalence(connection)
        assert (
            connection.execute(
                "SELECT value FROM metadata WHERE key='evidence_anchors_valid'"
            ).fetchone()[0]
            == "false"
        )
        fallback = run_evidence_feature(
            connection,
            publication_id=artifact.publication_id,
            page_position=2,
        )
        assert (
            fallback.payload["page"]["anchor_basis"]
            == "exact_keyset_fallback_anchors_invalid"
        )


def test_source_phase_mutation_invalidates_evidence_anchors(
    built: tuple[Any, Any],
) -> None:
    fixture, artifact = built
    phase = fixture.phases[0]
    with database(artifact.path) as connection:
        assert (
            connection.execute(
                "SELECT value FROM metadata WHERE key='evidence_anchors_valid'"
            ).fetchone()[0]
            == "true"
        )
        maintenance_module.apply_source_phase(
            connection,
            fixture,
            group=phase.group,
            phase=phase.phase,
        )
        connection.commit()
        assert (
            connection.execute(
                "SELECT value FROM metadata WHERE key='evidence_anchors_valid'"
            ).fetchone()[0]
            == "false"
        )


def test_deep_page_uses_persisted_keyset_anchor_without_gaps(
    built: tuple[Any, Any],
) -> None:
    _, artifact = built
    with database(artifact.path, read_only=True) as connection:
        expected = all_evidence_rows(
            connection,
            publication_id=artifact.publication_id,
            page_size=37,
        )
        result = run_evidence_feature(
            connection,
            publication_id=artifact.publication_id,
            page_position=11,
        )

        assert result.payload["page"]["page_position"] == 11
        assert result.payload["page"]["anchor_basis"] == "persisted_sparse_anchor"
        assert result.payload["rows"] == list(expected[100:110])
        assert result.selector_pages_gap_free
        assert all("OFFSET" not in plan.upper() for plan in result.query_plans)
        assert any(
            "evidence_page_anchor_current" in plan
            for plan in result.query_plans
        )


def test_bounded_sort_is_complete_for_explicit_admission_and_compact(
    built: tuple[Any, Any],
) -> None:
    _, artifact = built
    with database(artifact.path) as connection:
        connection.executemany(
            """
            INSERT INTO session_usage_current(
                session_id, calls, uncached_input_tokens, cached_input_tokens,
                reasoning_tokens, output_tokens
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    f"admitted-session-{ordinal:03d}",
                    ordinal + 1,
                    (ordinal * 17) % 101,
                    (ordinal * 13) % 89,
                    (ordinal * 7) % 43,
                    (ordinal * 11) % 67,
                )
                for ordinal in range(120)
            ],
        )
        connection.commit()

        admitted = _rows(
            connection,
            """
            SELECT
                session_id, calls, uncached_input_tokens, cached_input_tokens,
                reasoning_tokens, output_tokens
            FROM session_usage_current
            WHERE session_id >= ''
            ORDER BY session_id
            LIMIT 100
            """,
        )
        expected = sorted(
            admitted,
            key=lambda row: (
                -int(row["uncached_input_tokens"])
                - int(row["cached_input_tokens"])
                - int(row["output_tokens"]),
                str(row["session_id"]),
            ),
        )
        result = run_bounded_sort(connection)

    columns = list(result.payload["results"][0]["columns"])
    observed = [
        dict(zip(columns, row, strict=True))
        for row in result.payload["results"][0]["rows"]
    ]
    admission = result.payload["results"][0]["admission"]
    assert observed == expected
    assert admission == {
        "admitted_order": ["session_id", "ascending"],
        "maximum_rows": 100,
        "source_has_more": True,
    }
    assert len(result.encoded) <= 16_384
