"""R4 persisted-rollup and common-query contracts."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from codex_usage_tracker.kernel import ingest
from codex_usage_tracker.kernel.application import KernelApplication, RuntimePaths
from codex_usage_tracker.kernel.database import short_writer_transaction
from codex_usage_tracker.kernel.hydration import HydrationPreset
from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger
from codex_usage_tracker.kernel.operational import (
    kernel_paths,
    load_cutover_control,
)
from codex_usage_tracker.kernel.query import (
    Filter,
    Operation,
    QueryRequest,
    QueryService,
)
from codex_usage_tracker.kernel.query.plans import compile_plan
from codex_usage_tracker.kernel.rollups import (
    _LINK_UNRESOLVED_TOOL_CALLS_SQL,
    generation_rollups_ready,
)
from tests.kernel.interfaces.support import active_runtime, logical_split_runtime
from tests.kernel.test_ingest_pipeline import _token_line


def test_refresh_publishes_generation_scoped_rollups(tmp_path: Path) -> None:
    runtime = active_runtime(tmp_path)
    control = load_cutover_control(runtime.kernel.operational)
    assert control.active_kernel_path is not None

    with sqlite3.connect(control.active_kernel_path) as connection:
        generation = control.active_generation
        assert generation is not None
        assert connection.execute(
            "SELECT calls FROM rollup_global WHERE generation = ?",
            (generation,),
        ).fetchone() == (4,)
        assert connection.execute(
            "SELECT COUNT(*) FROM rollup_thread WHERE generation = ?",
            (generation,),
        ).fetchone() == (2,)
        assert connection.execute(
            "SELECT COUNT(*) FROM rollup_model_effort WHERE generation = ?",
            (generation,),
        ).fetchone() == (2,)


def test_top_threads_uses_bounded_rollup_plan(tmp_path: Path) -> None:
    runtime = active_runtime(tmp_path)
    result = QueryService(runtime.kernel.operational).execute(
        QueryRequest(
            dataset="calls",
            operation=Operation.AGGREGATE,
            dimensions=("thread",),
            measures=(
                "calls",
                "uncached_input_tokens",
                "cached_input_tokens",
                "reasoning_tokens",
                "output_tokens",
                "total_tokens",
            ),
            order_by="total_tokens",
            limit=25,
        )
    )

    assert result.plan_id == "calls.aggregate.rollup_thread.v1"
    assert result.scanned_count == 2
    assert result.returned_count == 2
    assert sum(int(row["calls"]) for row in result.rows) == 4


def test_top_threads_consolidates_physical_rows_by_logical_thread(
    tmp_path: Path,
) -> None:
    runtime = logical_split_runtime(tmp_path)
    control = load_cutover_control(runtime.kernel.operational)
    assert control.active_kernel_path is not None
    assert control.active_generation is not None
    request = QueryRequest(
        dataset="calls",
        operation=Operation.SHARE,
        dimensions=("thread",),
        measures=(
            "calls",
            "uncached_input_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
            "output_tokens",
            "total_tokens",
        ),
        order_by="total_tokens",
        limit=25,
    )
    result = QueryService(runtime.kernel.operational).execute(request)

    with sqlite3.connect(control.active_kernel_path) as connection:
        oracle_rows = connection.execute(
            """
            SELECT threads.logical_thread_id,
                   COUNT(*) AS calls,
                   SUM(model_calls.input_tokens) AS input_tokens,
                   SUM(
                       model_calls.input_tokens
                       - model_calls.cached_input_tokens
                   ) AS uncached_input_tokens,
                   SUM(model_calls.cached_input_tokens)
                       AS cached_input_tokens,
                   SUM(model_calls.reasoning_tokens) AS reasoning_tokens,
                   SUM(model_calls.output_tokens) AS output_tokens,
                   SUM(
                       model_calls.input_tokens
                       + model_calls.output_tokens
                   ) AS total_tokens
            FROM model_calls
            JOIN threads ON threads.thread_id = model_calls.thread_id
            WHERE model_calls.generation <= ?
              AND model_calls.duplicate_state = 'canonical'
            GROUP BY threads.logical_thread_id
            ORDER BY total_tokens DESC, threads.logical_thread_id
            """,
            (control.active_generation,),
        ).fetchall()
        copied_calls = connection.execute(
            "SELECT COUNT(*) FROM model_calls WHERE duplicate_state != 'canonical'"
        ).fetchone()

    actual_rows = {
        str(row["thread"]): {
            measure: int(row[measure])
            for measure in (
                "calls",
                "uncached_input_tokens",
                "cached_input_tokens",
                "reasoning_tokens",
                "output_tokens",
                "total_tokens",
            )
        }
        for row in result.rows
    }
    oracle = {
        str(row[0]): {
            "calls": int(row[1]),
            "uncached_input_tokens": int(row[3]),
            "cached_input_tokens": int(row[4]),
            "reasoning_tokens": int(row[5]),
            "output_tokens": int(row[6]),
            "total_tokens": int(row[7]),
        }
        for row in oracle_rows
    }

    assert result.plan_id == "calls.share.rollup_thread.v1"
    assert copied_calls == (1,)
    assert actual_rows == oracle
    assert result.returned_count == len(oracle)
    assert result.matched_count == len(oracle)
    assert result.scanned_count == len(oracle)
    assert len(result.rows) == len({str(row["thread"]) for row in result.rows})
    assert result.rows[0]["thread_label"] == "Current logical thread"
    assert sum(float(row["share_total_tokens"]) for row in result.rows) == pytest.approx(
        1.0
    )


@pytest.mark.parametrize(
    "query_request",
    (
        QueryRequest(
            "calls",
            Operation.SHARE,
            ("thread",),
            ("total_tokens", "configured_cost_usd"),
            order_by="total_tokens",
            limit=5,
        ),
        QueryRequest(
            "calls",
            Operation.AGGREGATE,
            ("thread",),
            ("total_tokens", "configured_cost_usd"),
            filters=(Filter("model", "eq", "gpt-synthetic"),),
            order_by="total_tokens",
            limit=5,
        ),
        QueryRequest(
            "calls",
            Operation.AGGREGATE,
            ("thread",),
            ("total_tokens", "configured_cost_usd"),
            order_by="configured_cost_usd",
            limit=5,
        ),
    ),
)
def test_thread_cost_plan_preserves_direct_fallbacks(
    query_request: QueryRequest,
) -> None:
    plan = compile_plan(query_request, generation=1, offset=0)

    assert plan.plan_id != "calls.aggregate.rollup_thread_cost.v1"


def test_thread_cost_plan_paginates_tied_threads_deterministically(
    tmp_path: Path,
) -> None:
    runtime = active_runtime(tmp_path)
    control = load_cutover_control(runtime.kernel.operational)
    assert control.active_kernel_path is not None
    assert control.active_generation is not None
    with sqlite3.connect(control.active_kernel_path) as connection:
        connection.execute(
            """
            UPDATE rollup_thread
            SET input_tokens = 100, output_tokens = 0
            WHERE generation = ?
            """,
            (control.active_generation,),
        )
        connection.commit()
    service = QueryService(runtime.kernel.operational)
    request = _thread_cost_request(limit=1)

    first = service.execute(request)
    second = service.execute(
        QueryRequest(
            dataset=request.dataset,
            operation=request.operation,
            dimensions=request.dimensions,
            measures=request.measures,
            order_by=request.order_by,
            limit=request.limit,
            cursor=first.next_cursor,
        )
    )

    assert first.truncated is True
    assert first.next_cursor is not None
    assert second.next_cursor is None
    assert str(first.rows[0]["thread"]) < str(second.rows[0]["thread"])


def test_thread_cost_plan_preserves_partial_pricing_coverage(
    tmp_path: Path,
) -> None:
    runtime = active_runtime(tmp_path)
    rate_card = tmp_path / "rates.json"
    _write_rate_card(rate_card, models=("gpt-5.3-codex",))

    result = QueryService(
        runtime.kernel.operational,
        rate_card_path=rate_card,
    ).execute(_thread_cost_request())

    for measure in ("configured_cost_usd", "estimated_credits"):
        coverage = result.coverage["measures"][measure]
        assert coverage["observed_count"] > 0
        assert coverage["missing_count"] > 0
        assert 0.0 < coverage["coverage_percent"] < 100.0


def test_thread_cost_plan_matches_direct_logical_split_oracle(
    tmp_path: Path,
) -> None:
    runtime = logical_split_runtime(tmp_path)
    rate_card = tmp_path / "rates.json"
    _write_rate_card(rate_card, models=("gpt-synthetic",))
    service = QueryService(
        runtime.kernel.operational,
        rate_card_path=rate_card,
    )
    direct = service.execute(
        QueryRequest(
            "calls",
            Operation.SHARE,
            ("thread",),
            (
                "total_tokens",
                "configured_cost_usd",
                "estimated_credits",
            ),
            order_by="total_tokens",
            limit=5,
        )
    )
    fast = service.execute(_thread_cost_request())

    assert fast.plan_id == "calls.aggregate.rollup_thread_cost.v1"
    assert fast.returned_count == direct.returned_count == 2
    for direct_row, fast_row in zip(direct.rows, fast.rows, strict=True):
        assert fast_row["thread"] == direct_row["thread"]
        assert fast_row["thread_label"] == direct_row["thread_label"]
        assert fast_row["total_tokens"] == direct_row["total_tokens"]
        assert fast_row["configured_cost_usd"] == pytest.approx(
            direct_row["configured_cost_usd"]
        )
        assert fast_row["estimated_credits"] == pytest.approx(
            direct_row["estimated_credits"]
        )
    assert fast.coverage == direct.coverage


def test_thread_cost_plan_label_is_bound_to_requested_generation(
    tmp_path: Path,
) -> None:
    runtime = logical_split_runtime(tmp_path)
    control = load_cutover_control(runtime.kernel.operational)
    assert control.active_kernel_path is not None
    assert control.active_generation == 1
    with sqlite3.connect(control.active_kernel_path) as connection:
        logical_thread_id = str(
            connection.execute(
                """
                SELECT logical_thread_id
                FROM threads
                WHERE display_label = 'Current logical thread'
                """
            ).fetchone()[0]
        )
        connection.execute(
            """
            INSERT INTO generations VALUES (
                2, 'future-revision', '2026-01-03T00:00:00Z',
                'future-high-water', 0, 0, 0, 3, 1,
                '2026-01-03T00:00:00Z', 'synthetic:1', 'valid'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO threads(
                thread_id, source_key, source_id, logical_thread_id,
                session_identity_hash, display_label, archive_state,
                first_generation, last_generation, identity_basis,
                identity_confidence
            )
            SELECT
                'future-physical-thread', source_key, source_id,
                logical_thread_id, 'future-session-hash',
                'Future logical thread label', 'active',
                2, 2, 'synthetic', 'exact'
            FROM threads
            WHERE logical_thread_id = ?
            LIMIT 1
            """,
            (logical_thread_id,),
        )
        connection.commit()
    service = QueryService(runtime.kernel.operational)
    tokens = service.execute(
        QueryRequest(
            "calls",
            Operation.SHARE,
            ("thread",),
            ("total_tokens",),
            order_by="total_tokens",
            limit=5,
        )
    )
    costs = service.execute(_thread_cost_request())
    token_row = next(
        row for row in tokens.rows if row["thread"] == logical_thread_id
    )
    cost_row = next(
        row for row in costs.rows if row["thread"] == logical_thread_id
    )

    assert token_row["thread_label"] == "Current logical thread"
    assert cost_row["thread_label"] == token_row["thread_label"]


def test_model_effort_and_global_queries_use_small_rollups(tmp_path: Path) -> None:
    runtime = active_runtime(tmp_path)
    service = QueryService(runtime.kernel.operational)

    model_effort = service.execute(
        QueryRequest(
            dataset="calls",
            operation=Operation.AGGREGATE,
            dimensions=("model", "effort"),
            measures=("calls", "total_tokens"),
            limit=25,
        )
    )
    global_totals = service.execute(
        QueryRequest(
            dataset="calls",
            operation=Operation.AGGREGATE,
            measures=(
                "calls",
                "uncached_input_tokens",
                "cached_input_tokens",
                "reasoning_tokens",
                "output_tokens",
            ),
            limit=1,
        )
    )

    assert model_effort.plan_id.endswith("rollup_model_effort.v1")
    assert model_effort.scanned_count == 2
    assert global_totals.plan_id.endswith("rollup_global.v1")
    assert global_totals.scanned_count == 1
    assert global_totals.rows[0]["calls"] == 4


def test_time_bands_and_tool_operations_use_bounded_rollups(
    tmp_path: Path,
) -> None:
    runtime = active_runtime(tmp_path)
    service = QueryService(runtime.kernel.operational)

    daily = service.execute(
        QueryRequest(
            dataset="calls",
            operation=Operation.TIME_SERIES,
            dimensions=("time_day",),
            measures=("calls", "total_tokens"),
            order_by="time_day",
            descending=False,
            limit=31,
        )
    )
    hourly = service.execute(
        QueryRequest(
            dataset="calls",
            operation=Operation.TIME_SERIES,
            dimensions=("time_hour",),
            measures=("calls", "total_tokens"),
            order_by="time_hour",
            descending=False,
            limit=168,
        )
    )
    tools = service.execute(
        QueryRequest(
            dataset="tools",
            operation=Operation.AGGREGATE,
            dimensions=("operation",),
            measures=("tools",),
            order_by="tools",
            limit=25,
        )
    )

    assert daily.plan_id.endswith("rollup_time_band.v1")
    assert daily.scanned_count == daily.matched_count
    assert sum(int(row["calls"]) for row in daily.rows) == 4
    assert hourly.plan_id.endswith("rollup_time_band.v1")
    assert hourly.scanned_count == hourly.matched_count
    assert sum(int(row["calls"]) for row in hourly.rows) == 4
    assert tools.plan_id == "tools.aggregate.rollup_tool_operation.v1"
    assert tools.scanned_count == tools.matched_count
    assert sum(int(row["tools"]) for row in tools.rows) > 0
    assert len(tools.rows) == len({str(row["operation"]) for row in tools.rows})

    nullable_metrics = service.execute(
        QueryRequest(
            dataset="tools",
            operation=Operation.AGGREGATE,
            dimensions=("operation",),
            measures=("tools", "duration_ms", "output_bytes"),
            order_by="tools",
            limit=25,
        )
    )
    assert nullable_metrics.plan_id == "tools.aggregate.v1"


def test_tool_relink_changed_turn_filter_is_set_based(tmp_path: Path) -> None:
    runtime = active_runtime(tmp_path)
    control = load_cutover_control(runtime.kernel.operational)
    assert control.active_kernel_path is not None
    assert control.active_generation is not None

    generation = control.active_generation
    with sqlite3.connect(control.active_kernel_path) as connection:
        plan = connection.execute(
            "EXPLAIN QUERY PLAN " + _LINK_UNRESOLVED_TOOL_CALLS_SQL,
            (
                generation,
                generation,
                generation,
                generation,
                generation,
                generation,
            ),
        ).fetchall()

    details = tuple(str(row[3]) for row in plan)
    assert any("idx_tool_calls_turn" in detail for detail in details)
    assert any("LIST SUBQUERY" in detail for detail in details)
    assert sum("CORRELATED SCALAR SUBQUERY" in detail for detail in details) == 2


def test_model_rollup_regroups_unselected_effort_and_tier(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sessions" / "model-groups.jsonl"
    source.parent.mkdir()
    source.write_text(
        '{"timestamp":"2026-01-01T00:00:00Z","type":"session_meta",'
        '"payload":{"id":"synthetic-model-groups"}}\n'
        '{"timestamp":"2026-01-01T00:00:00Z","type":"turn_context",'
        '"payload":{"turn_id":"turn-1","model":"gpt-synthetic",'
        '"effort":"low"}}\n'
        + _token_line("event-1", 10)
        + '{"timestamp":"2026-01-01T00:00:02Z","type":"turn_context",'
        '"payload":{"turn_id":"turn-2","model":"gpt-synthetic",'
        '"effort":"high"}}\n' + _token_line("event-2", 20),
        encoding="utf-8",
    )
    paths = kernel_paths(tmp_path / "cache")
    KernelIngestor(paths.analytical, paths.operational).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r4-model-regroup",
        hydration_preset=HydrationPreset.COMPLETE,
    )
    service = QueryService(paths.operational)
    by_model = service.execute(
        QueryRequest(
            dataset="calls",
            operation=Operation.AGGREGATE,
            dimensions=("model",),
            measures=("calls", "total_tokens"),
            limit=10,
        )
    )
    by_effort = service.execute(
        QueryRequest(
            dataset="calls",
            operation=Operation.AGGREGATE,
            dimensions=("model", "effort"),
            measures=("calls", "total_tokens"),
            limit=10,
        )
    )
    assert by_model.plan_id.endswith("rollup_model_effort.v1")
    assert by_model.rows == ({"model": "gpt-synthetic", "calls": 2, "total_tokens": 34},)
    assert len(by_effort.rows) == 2
    assert sum(int(row["calls"]) for row in by_effort.rows) == 2


def test_append_rollups_equal_published_canonical_facts(tmp_path: Path) -> None:
    source = _source(tmp_path)
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="rollup-owner",
    )
    with source.open("a", encoding="utf-8") as handle:
        handle.write(_token_line("event-2", 20))
        handle.write(_token_line("event-3", 30))

    result = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.MCP_USAGE_REFRESH,
        owner_id="rollup-owner",
    )

    with sqlite3.connect(paths.analytical) as connection:
        canonical_calls = connection.execute(
            """
            SELECT COUNT(*)
            FROM model_call_facts
            WHERE generation <= ? AND duplicate_state = 'canonical'
            """,
            (result.generation,),
        ).fetchone()[0]
        assert connection.execute(
            "SELECT calls FROM rollup_global WHERE generation = ?",
            (result.generation,),
        ).fetchone() == (canonical_calls,)
        for table, expected_calls in (
            ("rollup_thread", canonical_calls),
            ("rollup_model_effort", canonical_calls),
            ("rollup_time_band", canonical_calls * 2),
        ):
            assert (
                connection.execute(
                    f"SELECT SUM(calls) FROM {table} WHERE generation = ?",
                    (result.generation,),
                ).fetchone()[0]
                == expected_calls
            )


def test_interrupted_rollup_update_recovers_before_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(tmp_path)
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="rollup-owner",
    )
    with source.open("a", encoding="utf-8") as handle:
        handle.write(_token_line("event-2", 20))
    real_rebuild = ingest.rebuild_generation_rollups

    def interrupt_rollups(*args: object, **kwargs: object) -> float:
        raise RuntimeError("synthetic rollup interruption")

    monkeypatch.setattr(ingest, "rebuild_generation_rollups", interrupt_rollups)
    with pytest.raises(RuntimeError, match="synthetic rollup interruption"):
        ingestor.refresh(
            [source],
            trigger=RefreshTrigger.MCP_USAGE_REFRESH,
            owner_id="rollup-owner",
        )
    assert load_cutover_control(paths.operational).active_generation == 1

    monkeypatch.setattr(ingest, "rebuild_generation_rollups", real_rebuild)
    recovered = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.MCP_USAGE_REFRESH,
        owner_id="rollup-owner",
    )

    assert recovered.generation == 2
    assert load_cutover_control(paths.operational).active_generation == 2
    assert generation_rollups_ready(paths.analytical, 2)
    with sqlite3.connect(paths.analytical) as connection:
        assert connection.execute(
            "SELECT calls FROM rollup_global WHERE generation = 2"
        ).fetchone() == (2,)


def test_no_change_refresh_backfills_upgrade_rollups_off_active_path(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="rollup-owner",
    )
    prior_active = load_cutover_control(paths.operational).active_kernel_path
    assert prior_active is not None
    with short_writer_transaction(prior_active) as connection:
        for table in (
            "rollup_global",
            "rollup_thread",
            "rollup_model_effort",
            "rollup_time_band",
            "rollup_tool_operation",
        ):
            connection.execute(f"DELETE FROM {table} WHERE generation = 1")
    application = KernelApplication(
        RuntimePaths(tmp_path / "codex-home", tmp_path / "cache"),
        worker_launcher=lambda _paths, _preset: None,
    )
    query = {
        "requests": [
            {
                "dataset": "calls",
                "operation": "aggregate",
                "measures": ["calls", "total_tokens"],
                "limit": 1,
            }
        ]
    }
    before = application.query(query)

    result = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="rollup-owner",
    )
    control = load_cutover_control(paths.operational)

    assert result.planner_reason == "no_changes"
    assert control.active_generation == 1
    assert control.active_kernel_path is not None
    assert control.active_kernel_path != prior_active
    assert generation_rollups_ready(control.active_kernel_path, 1)
    after = application.query(query)
    assert before["results"][0]["rows"] == []
    assert after["cache"]["hit"] is False
    assert after["cache"]["key"] != before["cache"]["key"]
    assert after["results"][0]["rows"][0]["calls"] == 1


def _source(root: Path) -> Path:
    source = root / "sessions" / "rollout-r4.jsonl"
    source.parent.mkdir()
    source.write_text(
        '{"timestamp":"2026-01-01T00:00:00Z","type":"session_meta",'
        '"payload":{"id":"synthetic-r4-session"}}\n'
        '{"timestamp":"2026-01-01T00:00:00Z","type":"turn_context",'
        '"payload":{"turn_id":"turn-1","model":"gpt-synthetic","effort":"low"}}\n'
        + _token_line("event-1", 10),
        encoding="utf-8",
    )
    return source


def _thread_cost_request(*, limit: int = 5) -> QueryRequest:
    return QueryRequest(
        "calls",
        Operation.AGGREGATE,
        ("thread",),
        (
            "total_tokens",
            "configured_cost_usd",
            "estimated_credits",
        ),
        order_by="total_tokens",
        limit=limit,
    )


def _write_rate_card(path: Path, *, models: tuple[str, ...]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": "codex-usage-tracker.kernel-rate-card.v1",
                "source": {
                    "name": "Synthetic thread-cost rates",
                    "url": "https://example.invalid/thread-cost-rates",
                    "effective_at": "2026-01-01",
                    "fetched_at": "2026-01-01T00:00:00Z",
                },
                "models": {
                    model: {
                        "input_per_million": 1.0,
                        "cached_input_per_million": 0.5,
                        "output_per_million": 2.0,
                        "credits_input_per_million": 3.0,
                        "credits_cached_input_per_million": 1.0,
                        "credits_output_per_million": 4.0,
                        "confidence": "estimated",
                    }
                    for model in models
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_cross_preset_retry_recovers_appended_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(tmp_path)
    captured_at = datetime(2026, 1, 15, tzinfo=timezone.utc)
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r4-cross-preset",
        hydration_preset=HydrationPreset.RECENT_30D,
        captured_at=captured_at,
    )
    with source.open("a", encoding="utf-8") as handle:
        handle.write(_token_line("event-2", 20))

    monkeypatch.setattr(ingestor, "_promote", lambda *_args, **_kwargs: None)
    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r4-cross-preset",
        hydration_preset=HydrationPreset.RECENT_30D,
        captured_at=captured_at,
    )

    recovered = KernelIngestor(
        paths.analytical,
        paths.operational,
    ).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r4-cross-preset-retry",
        hydration_preset=HydrationPreset.RECENT_90D,
        captured_at=captured_at,
    )
    control = load_cutover_control(paths.operational)
    assert recovered.generation == 2
    assert control.active_generation == 2
    assert control.active_kernel_path is not None
    with sqlite3.connect(control.active_kernel_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM model_call_facts WHERE generation <= 2"
        ).fetchone() == (2,)
