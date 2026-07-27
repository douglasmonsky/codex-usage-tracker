"""Synthetic 100,000-call query-budget qualification."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
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

_CALL_COUNT = 100_000


@pytest.fixture(scope="module")
def large_service(tmp_path_factory: pytest.TempPathFactory) -> QueryService:
    root = tmp_path_factory.mktemp("query-performance")
    paths = kernel_paths(root)
    initialize_analytical_database(paths.analytical)
    initialize_operational_database(paths.operational)
    _populate_calls(paths.analytical)
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
    return QueryService(paths.operational)


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

    common_p95 = _p95(lambda: large_service.execute(common), repeats=20)
    comparison_p95 = _p95(
        lambda: large_service.execute(comparison),
        repeats=12,
    )
    concentration_p95 = _p95(
        lambda: large_service.execute(concentration),
        repeats=12,
    )

    print(
        json.dumps(
            {
                "calls": _CALL_COUNT,
                "common_p95_ms": round(common_p95, 3),
                "comparison_p95_ms": round(comparison_p95, 3),
                "concentration_p95_ms": round(concentration_p95, 3),
            },
            sort_keys=True,
        )
    )
    assert common_p95 <= 500.0
    assert comparison_p95 <= 1_000.0
    assert concentration_p95 <= 1_000.0


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
                ?, 'source-1', ?, ?, ?, 'synthetic-project',
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
                ?, NULL, ?, 0, '2026-01-01T00:00:00Z',
                '2026-01-29T00:00:00Z', 'completed', 'synthetic',
                'synthetic', 'exact', 0, 1, 400, 0, 0, 0, 0, 0, 1, 1
            )
            """,
            (
                (f"turn-{index:03d}", f"thread-row-{index:03d}")
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


def _call_row(index: int) -> tuple[object, ...]:
    thread = index % 250
    day = 1 + (index % 28)
    input_tokens = 100 + index % 900
    cached_tokens = input_tokens // 2
    output_tokens = 10 + index % 90
    return (
        f"call-{index:06d}",
        f"canonical-{index:06d}",
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
