#!/usr/bin/env python3
"""Benchmark representative dashboard routes with deterministic synthetic data."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from benchmark_synthetic_history import (  # noqa: E402
    _synthetic_events,
    _write_benchmark_config,
)

from codex_usage_tracker.server.recommendations import recommendations_payload  # noqa: E402
from codex_usage_tracker.server.summary import summary_payload  # noqa: E402
from codex_usage_tracker.store.api import (  # noqa: E402
    refresh_usage_event_links,
    upsert_usage_events,
)

DEFAULT_SIZES = (10_000, 100_000, 400_000)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure dashboard route baselines without enforcing thresholds.",
    )
    parser.add_argument("--sizes", nargs="+", type=_positive_int, default=DEFAULT_SIZES)
    parser.add_argument("--iterations", type=_positive_int, default=3)
    parser.add_argument("--batch-size", type=_positive_int, default=10_000)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    fixtures = [
        benchmark_fixture(
            rows=rows,
            output_dir=args.output_dir,
            iterations=args.iterations,
            batch_size=args.batch_size,
        )
        for rows in args.sizes
    ]
    print(
        json.dumps(
            {
                "schema": "codex-usage-tracker-dashboard-route-benchmark-v1",
                "thresholds_enforced": False,
                "fixtures": fixtures,
            },
            sort_keys=True,
        )
    )
    return 0


def benchmark_fixture(
    *,
    rows: int,
    output_dir: Path,
    iterations: int,
    batch_size: int,
) -> dict[str, object]:
    fixture_dir = output_dir / f"rows-{rows}"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    db_path = fixture_dir / "usage.sqlite3"
    if db_path.exists():
        db_path.unlink()
    config = _write_benchmark_config(fixture_dir)

    populate_started = time.perf_counter()
    for start in range(0, rows, batch_size):
        upsert_usage_events(
            _synthetic_events(start, min(start + batch_size, rows)),
            db_path=db_path,
            refresh_links=False,
        )
    refresh_usage_event_links(db_path=db_path)
    populate_seconds = round(time.perf_counter() - populate_started, 6)

    route_actions: tuple[tuple[str, Callable[[], dict[str, object]]], ...] = (
        (
            "/api/summary",
            lambda: summary_payload(
                "group_by=date&limit=20&include_archived=true",
                db_path=db_path,
                pricing_path=config["pricing_path"],
                projects_path=config["projects_path"],
                privacy_mode="normal",
            ),
        ),
        (
            "/api/recommendations",
            lambda: recommendations_payload(
                "limit=20&include_archived=true",
                db_path=db_path,
                pricing_path=config["pricing_path"],
                allowance_path=config["allowance_path"],
                projects_path=config["projects_path"],
                privacy_mode="normal",
            ),
        ),
    )
    return {
        "rows": rows,
        "populate_seconds": populate_seconds,
        "routes": [
            _benchmark_route(path, action, iterations=iterations) for path, action in route_actions
        ],
    }


def _benchmark_route(
    path: str,
    action: Callable[[], dict[str, object]],
    *,
    iterations: int,
) -> dict[str, object]:
    samples: list[float] = []
    payload: dict[str, object] = {}
    for _ in range(iterations):
        started = time.perf_counter()
        payload = action()
        samples.append(round(time.perf_counter() - started, 6))
    return {
        "path": path,
        "samples_seconds": samples,
        "median_seconds": round(statistics.median(samples), 6),
        "result_rows": _result_rows(payload),
    }


def _result_rows(payload: dict[str, object]) -> int:
    row_count = payload.get("row_count")
    if isinstance(row_count, int):
        return row_count
    rows = payload.get("rows")
    return len(rows) if isinstance(rows, list) else 0


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
