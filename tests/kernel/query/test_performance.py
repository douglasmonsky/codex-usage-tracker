"""Synthetic 100,000-call query-budget qualification."""

from __future__ import annotations

import json
import math
import sqlite3
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

import pytest

from codex_usage_tracker.kernel.database import (
    analytical_digest,
    initialize_analytical_database,
    short_writer_transaction,
)
from codex_usage_tracker.kernel.models import CutoverState
from codex_usage_tracker.kernel.operational import (
    initialize_operational_database,
    kernel_paths,
    transition_cutover,
)
from codex_usage_tracker.kernel.query import (
    ComparisonWindow,
    Operation,
    QueryRequest,
    QueryService,
)
from codex_usage_tracker.kernel.rollups import rebuild_generation_rollups

_CALL_COUNT = 100_000
_TOOL_COUNT = 25_000


@pytest.fixture(scope="module")
def large_rollup_metrics() -> dict[str, float]:
    return {}


@pytest.fixture(scope="module")
def large_service(
    tmp_path_factory: pytest.TempPathFactory,
    large_rollup_metrics: dict[str, float],
) -> QueryService:
    root = tmp_path_factory.mktemp("query-performance")
    paths = kernel_paths(root)
    initialize_analytical_database(paths.analytical)
    initialize_operational_database(paths.operational)
    _populate_calls(paths.analytical)
    large_rollup_metrics["elapsed_ms"] = rebuild_generation_rollups(paths.analytical, 1)
    rate_card = root / "rates.json"
    _write_rate_card(rate_card)
    with sqlite3.connect(paths.operational) as connection:
        connection.execute(
            """
            INSERT INTO coverage_control(
                singleton, preset, captured_at, cutoff_at, complete_history,
                coverage_revision, cataloged_source_count,
                hydrated_source_count, deferred_source_count,
                cataloged_bytes, hydrated_bytes, deferred_bytes,
                uncertain_source_count
            )
            VALUES (
                1, 'complete', '2026-01-29T00:00:00Z', NULL, 1,
                'sha256:synthetic-complete', 1, 1, 0, 1, 1, 0, 0
            )
            """
        )
    transition_cutover(
        paths.operational,
        CutoverState.BUILDING,
        staging_kernel_path=paths.analytical,
        refresh_run_id="query-performance",
    )
    transition_cutover(
        paths.operational,
        CutoverState.READY,
        integrity_digest=analytical_digest(paths.analytical),
    )
    transition_cutover(
        paths.operational,
        CutoverState.ACTIVE,
        active_kernel_path=paths.analytical,
        generation=1,
    )
    return QueryService(paths.operational, rate_card_path=rate_card)


def test_100k_rollup_rebuild_budget(
    large_service: QueryService,
    large_rollup_metrics: dict[str, float],
) -> None:
    assert large_service is not None
    assert large_rollup_metrics["elapsed_ms"] <= 5_500


def test_100k_common_comparison_and_concentration_budgets(
    large_service: QueryService,
) -> None:
    common = QueryRequest(
        "calls",
        Operation.AGGREGATE,
        ("effort", "model"),
        ("calls", "total_tokens"),
        limit=25,
    )
    comparison = QueryRequest(
        "calls",
        Operation.COMPARISON,
        ("model",),
        ("calls", "total_tokens"),
        comparison=ComparisonWindow(
            "2026-01-15T00:00:00Z",
            "2026-01-29T00:00:00Z",
            "2026-01-01T00:00:00Z",
            "2026-01-15T00:00:00Z",
        ),
        limit=25,
    )
    concentration = QueryRequest(
        "calls",
        Operation.SHARE,
        ("thread",),
        ("calls", "total_tokens"),
        limit=25,
    )
    daily = QueryRequest(
        "calls",
        Operation.TIME_SERIES,
        ("time_day",),
        ("calls", "total_tokens"),
        order_by="time_day",
        descending=False,
        limit=31,
    )

    common_p95 = _p95(lambda: large_service.execute(common), repeats=20)
    comparison_p95 = _p95(
        lambda: large_service.execute(comparison),
        repeats=12,
    )
    concentration_p95 = _p95(
        lambda: large_service.execute(concentration),
        repeats=12,
    )
    daily_p95 = _p95(lambda: large_service.execute(daily), repeats=12)
    common_result = large_service.execute(common)
    concentration_result = large_service.execute(concentration)
    daily_result = large_service.execute(daily)

    print(
        json.dumps(
            {
                "calls": _CALL_COUNT,
                "common_p95_ms": round(common_p95, 3),
                "comparison_p95_ms": round(comparison_p95, 3),
                "concentration_p95_ms": round(concentration_p95, 3),
                "daily_p95_ms": round(daily_p95, 3),
            },
            sort_keys=True,
        )
    )
    assert common_p95 <= 500.0
    assert comparison_p95 <= 1_000.0
    assert concentration_p95 <= 1_000.0
    assert daily_p95 <= 500.0
    assert common_result.plan_id.endswith("rollup_model_effort.v1")
    assert common_result.scanned_count == 4
    assert concentration_result.plan_id.endswith("rollup_thread.v1")
    assert concentration_result.scanned_count == 250
    assert daily_result.plan_id.endswith("rollup_time_band.v1")
    assert daily_result.scanned_count == 28


def test_100k_r5_analytical_primitive_budgets(
    large_service: QueryService,
) -> None:
    top_threads = QueryRequest(
        "calls",
        Operation.SHARE,
        ("thread",),
        (
            "calls",
            "uncached_input_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
            "output_tokens",
            "total_tokens",
            "configured_cost_usd",
            "estimated_credits",
        ),
        order_by="total_tokens",
        limit=25,
    )
    top_thread_costs = QueryRequest(
        "calls",
        Operation.AGGREGATE,
        ("thread",),
        (
            "total_tokens",
            "configured_cost_usd",
            "estimated_credits",
        ),
        order_by="total_tokens",
        limit=5,
    )
    tool_impact = QueryRequest(
        "tools",
        Operation.ROWS,
        ("tool_call", "operation", "target"),
        (
            "adjacent_uncached_input_tokens",
            "adjacent_cached_input_tokens",
            "adjacent_reasoning_tokens",
            "adjacent_output_tokens",
            "adjacent_total_tokens",
        ),
        order_by="adjacent_total_tokens",
        limit=25,
    )

    top_threads_p95 = _p95(
        lambda: large_service.execute(top_threads),
        repeats=12,
    )
    top_thread_costs_p95 = _p95(
        lambda: large_service.execute(top_thread_costs),
        repeats=12,
    )
    tool_impact_p95 = _p95(
        lambda: large_service.execute(tool_impact),
        repeats=12,
    )
    top_threads_result = large_service.execute(top_threads)
    top_thread_costs_result = large_service.execute(top_thread_costs)
    tool_impact_result = large_service.execute(tool_impact)
    top_threads_bytes = len(
        json.dumps(
            asdict(top_threads_result),
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )
    tool_impact_bytes = len(
        json.dumps(
            asdict(tool_impact_result),
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )

    print(
        json.dumps(
            {
                "calls": _CALL_COUNT,
                "tools": _TOOL_COUNT,
                "tool_impact_bytes": tool_impact_bytes,
                "tool_impact_p95_ms": round(tool_impact_p95, 3),
                "top_threads_bytes": top_threads_bytes,
                "top_threads_p95_ms": round(top_threads_p95, 3),
                "top_thread_costs_p95_ms": round(
                    top_thread_costs_p95,
                    3,
                ),
            },
            sort_keys=True,
        )
    )
    assert top_threads_p95 <= 1_000.0
    assert top_thread_costs_p95 <= 100.0
    assert tool_impact_p95 <= 500.0
    assert top_threads_bytes <= 64_000
    assert tool_impact_bytes <= 64_000
    assert top_threads_result.returned_count == 25
    assert top_thread_costs_result.returned_count == 5
    assert top_thread_costs_result.plan_id == (
        "calls.aggregate.rollup_thread_cost.v1"
    )
    for direct_row, fast_row in zip(
        top_threads_result.rows[:5],
        top_thread_costs_result.rows,
        strict=True,
    ):
        assert fast_row["thread"] == direct_row["thread"]
        assert fast_row["thread_label"] == direct_row["thread_label"]
        assert fast_row["total_tokens"] == direct_row["total_tokens"]
        assert fast_row["configured_cost_usd"] == pytest.approx(
            direct_row["configured_cost_usd"]
        )
        assert fast_row["estimated_credits"] == pytest.approx(
            direct_row["estimated_credits"]
        )
    for measure in ("configured_cost_usd", "estimated_credits"):
        assert (
            top_thread_costs_result.coverage["measures"][measure]
            == top_threads_result.coverage["measures"][measure]
        )
    assert tool_impact_result.returned_count == 25
    assert tool_impact_result.plan_id == "tools.rows.direct_tool_impact.v1"
    assert all("thread_label" in row for row in top_threads_result.rows)
    assert (
        top_threads_result.coverage["measures"]["configured_cost_usd"]["coverage_percent"] == 100.0
    )


def _p95(operation: Callable[[], object], *, repeats: int) -> float:
    operation()
    elapsed: list[float] = []
    for _index in range(repeats):
        started = time.perf_counter()
        operation()
        elapsed.append((time.perf_counter() - started) * 1000)
    ordered = sorted(elapsed)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def _populate_calls(path: Path) -> None:
    with short_writer_transaction(path) as connection:
        connection.execute(
            """
            INSERT INTO generations VALUES (
                1, 'synthetic-query-revision', '2026-01-29T00:00:00Z',
                'synthetic-high-water', 100000, 0, 0, 100000, 0,
                '2026-01-28T23:59:59Z', '{}', 'valid'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO sources VALUES (
                NULL,
                'source-1', 'active', 'active', NULL, NULL, 'synthetic-source',
                1, '2026-01-29T00:00:00Z', 1, 1, 0, NULL,
                'synthetic-replacement', 'synthetic', '1', '{}',
                '2026-01-01T00:00:00Z', '2026-01-29T00:00:00Z', 1, 0, 0
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO threads VALUES (
                NULL,
                ?, 1, 'source-1', ?, ?, ?, 'synthetic-project',
                '2026-01-01T00:00:00Z', '2026-01-29T00:00:00Z', NULL,
                'active', NULL, NULL, NULL, NULL, 1, 1, 'synthetic', 'exact'
            )
            """,
            (
                (
                    f"thread-row-{index:03d}",
                    f"thread-{index:03d}",
                    f"session-{index:03d}",
                    f"Synthetic thread {index:03d}",
                )
                for index in range(250)
            ),
        )
        connection.executemany(
            """
            INSERT INTO turns VALUES (
                NULL,
                ?, NULL, ?, ?, 0, '2026-01-01T00:00:00Z',
                '2026-01-29T00:00:00Z', 'completed', 'synthetic',
                'synthetic', 'exact', 0, 1, 400, 0, 0, 0, 0, 0, 1, 1
            )
            """,
            (
                (
                    f"turn-{index:03d}",
                    index + 1,
                    f"thread-row-{index:03d}",
                )
                for index in range(250)
            ),
        )
        connection.executemany(
            """
            INSERT INTO model_calls VALUES (
                ?, ?, 'source-1', ?, ?, ?, 0, ?, ?, 'standard', 'user',
                200000, ?, ?, ?, ?, NULL, NULL, NULL, 'canonical', NULL, 1, ?, 1
            )
            """,
            (_call_row(index) for index in range(_CALL_COUNT)),
        )
        connection.execute(
            """
            INSERT INTO tool_profiles(
                tool_profile_key, tool_name, server_name_key, namespace_key,
                tool_category, operation
            )
            VALUES (1, 'functions.read_file', '', 'functions', 'function', 'read')
            """
        )
        connection.executemany(
            """
            INSERT INTO tool_call_facts(
                tool_call_id, upstream_call_id_hash, source_key, thread_key,
                turn_key, tool_profile_key, nearest_model_call_key,
                target_label, started_at, ended_at, duration_ms, status,
                error_category, output_bytes, argument_shape,
                first_source_offset, last_source_offset, generation,
                observation_confidence
            )
            VALUES (
                ?, ?, 1, ?, ?, 1, ?, ?, ?, ?, ?, 'completed',
                NULL, ?, '["path"]', ?, ?, 1, 'exact'
            )
            """,
            (_tool_row(index) for index in range(_TOOL_COUNT)),
        )


def _call_row(index: int) -> tuple[object, ...]:
    thread = index % 250
    day = 1 + (index % 28)
    input_tokens = 100 + index % 900
    cached_tokens = input_tokens // 2
    output_tokens = 10 + index % 90
    return (
        f"call_{index:032x}",
        f"fp_{index:064x}",
        f"thread-row-{thread:03d}",
        f"turn-{thread:03d}",
        f"2026-01-{day:02d}T{index % 24:02d}:00:00Z",
        "gpt-synthetic-a" if index % 3 else "gpt-synthetic-b",
        "high" if index % 2 else "medium",
        input_tokens,
        cached_tokens,
        output_tokens,
        output_tokens // 3,
        index,
    )


def _tool_row(index: int) -> tuple[object, ...]:
    thread_key = index % 250 + 1
    call_key = index + 1
    timestamp = f"2026-01-{1 + (index % 28):02d}T{index % 24:02d}:00:00Z"
    return (
        index.to_bytes(16, "big"),
        f"upstream-{index:08d}",
        thread_key,
        thread_key,
        call_key,
        f"src/synthetic_{index % 50:02d}.py",
        timestamp,
        timestamp,
        float(index % 1_000),
        index % 8_192,
        index,
        index + 1,
    )


def _write_rate_card(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": "codex-usage-tracker.kernel-rate-card.v1",
                "source": {
                    "name": "Synthetic performance rates",
                    "url": "https://example.invalid/performance-rates",
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
                    for model in ("gpt-synthetic-a", "gpt-synthetic-b")
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
