#!/usr/bin/env python3
"""Benchmark representative dashboard routes with deterministic synthetic data."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from benchmark_synthetic_history import (  # noqa: E402
    _synthetic_events,
    _write_benchmark_config,
)

from codex_usage_tracker.compression.api import (  # noqa: E402
    compression_profile,
    compression_status,
    start_compression_analysis,
)
from codex_usage_tracker.compression.jobs import CompressionJobRegistry  # noqa: E402
from codex_usage_tracker.compression.models import CompressionScope  # noqa: E402
from codex_usage_tracker.recommendation_engine.materialization import (  # noqa: E402
    backfill_recommendation_facts,
)
from codex_usage_tracker.server.query_cache import (  # noqa: E402
    AggregateQueryCache,
)
from codex_usage_tracker.server.recommendations import (  # noqa: E402
    handle_recommendations_request,
)
from codex_usage_tracker.server.summary import handle_summary_request  # noqa: E402
from codex_usage_tracker.store.api import (  # noqa: E402
    refresh_usage_event_links,
    upsert_usage_events,
)
from codex_usage_tracker.store.connection import connect  # noqa: E402

DEFAULT_SIZES = (10_000, 100_000, 400_000)

JsonSender = Callable[[HTTPStatus, dict[str, object]], None]
RouteAction = Callable[[AggregateQueryCache, JsonSender], None]


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
    rate_card_path = fixture_dir / "synthetic-rate-card.json"

    populate_started = time.perf_counter()
    for start in range(0, rows, batch_size):
        upsert_usage_events(
            _synthetic_events(start, min(start + batch_size, rows)),
            db_path=db_path,
            refresh_links=False,
        )
    refresh_usage_event_links(db_path=db_path)
    populate_seconds = round(time.perf_counter() - populate_started, 6)

    materialize_started = time.perf_counter()
    with connect(db_path) as conn:
        materialized_rows = backfill_recommendation_facts(
            conn,
            pricing_path=config["pricing_path"],
            allowance_path=config["allowance_path"],
            rate_card_path=rate_card_path,
            thresholds_path=config["thresholds_path"],
        )
    materialize_seconds = round(time.perf_counter() - materialize_started, 6)

    def benchmark_summary(cache: AggregateQueryCache, send_json: JsonSender) -> None:
        handle_summary_request(
            "group_by=date&limit=20&include_archived=true",
            db_path=db_path,
            pricing_path=config["pricing_path"],
            projects_path=config["projects_path"],
            privacy_mode="normal",
            query_cache=cache,
            send_error=_raise_route_error,
            send_exception=_raise_route_exception,
            send_json=send_json,
        )

    def benchmark_recommendations(cache: AggregateQueryCache, send_json: JsonSender) -> None:
        handle_recommendations_request(
            "limit=20&include_archived=true",
            db_path=db_path,
            pricing_path=config["pricing_path"],
            allowance_path=config["allowance_path"],
            rate_card_path=rate_card_path,
            thresholds_path=config["thresholds_path"],
            projects_path=config["projects_path"],
            privacy_mode="normal",
            query_cache=cache,
            send_error=_raise_route_error,
            send_exception=_raise_route_exception,
            send_json=send_json,
        )

    route_actions: tuple[tuple[str, RouteAction], ...] = (
        ("/api/summary", benchmark_summary),
        ("/api/recommendations", benchmark_recommendations),
    )
    return {
        "rows": rows,
        "populate_seconds": populate_seconds,
        "recommendation_materialization": {
            "rows": materialized_rows,
            "seconds": materialize_seconds,
        },
        "routes": [
            _benchmark_cached_route(
                path,
                action=action,
                iterations=iterations,
            )
            for path, action in route_actions
        ],
        "compression_job": _benchmark_compression_job(
            db_path,
            iterations=iterations,
        ),
    }


def _benchmark_cached_route(
    path: str,
    *,
    action: RouteAction,
    iterations: int,
) -> dict[str, object]:
    cold_samples: list[float] = []
    cold_statuses: list[str] = []
    payload: dict[str, object] = {}
    body = b""
    for _ in range(iterations):
        started = time.perf_counter()
        payload, body, status = _invoke_route(action, AggregateQueryCache())
        cold_samples.append(round(time.perf_counter() - started, 6))
        cold_statuses.append(status)

    warm_cache = AggregateQueryCache()
    _invoke_route(action, warm_cache)
    warm_samples: list[float] = []
    warm_statuses: list[str] = []
    for _ in range(iterations):
        started = time.perf_counter()
        payload, body, status = _invoke_route(action, warm_cache)
        warm_samples.append(round(time.perf_counter() - started, 6))
        warm_statuses.append(status)

    cold_median = round(statistics.median(cold_samples), 6)
    cold_p95 = _percentile(cold_samples, 0.95)
    return {
        "path": path,
        "cold_seconds": cold_median,
        "cold_samples_seconds": cold_samples,
        "cold_median_seconds": cold_median,
        "cold_p95_seconds": cold_p95,
        "warm_samples_seconds": warm_samples,
        "warm_median_seconds": round(statistics.median(warm_samples), 6),
        "warm_p95_seconds": _percentile(warm_samples, 0.95),
        "samples_seconds": cold_samples,
        "median_seconds": cold_median,
        "p95_seconds": cold_p95,
        "cache_statuses": [*cold_statuses, *warm_statuses],
        "result_rows": _result_rows(payload),
        "payload_bytes": len(body),
    }


def _invoke_route(
    action: RouteAction,
    cache: AggregateQueryCache,
) -> tuple[dict[str, object], bytes, str]:
    response: dict[str, object] = {}
    body = b""

    def capture(status: HTTPStatus, payload: dict[str, object]) -> None:
        nonlocal response, body
        if status != HTTPStatus.OK:
            raise RuntimeError(f"benchmark route returned HTTP {int(status)}")
        response = payload
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")

    action(cache, capture)
    metadata = response.get("query_cache")
    cache_status = str(metadata.get("status")) if isinstance(metadata, dict) else "missing"
    return response, body, cache_status


def _raise_route_error(status: HTTPStatus, message: str) -> None:
    raise RuntimeError(f"benchmark route returned HTTP {int(status)}: {message}")


def _raise_route_exception(prefix: str, exc: BaseException) -> None:
    raise RuntimeError(f"{prefix}: {exc}") from exc


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
        "p95_seconds": _percentile(samples, 0.95),
        "result_rows": _result_rows(payload),
        "payload_bytes": len(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
    }


def _benchmark_compression_job(
    db_path: Path,
    *,
    iterations: int,
) -> dict[str, object]:
    scope = CompressionScope(include_archived=True)
    registry = CompressionJobRegistry()
    started_at = time.perf_counter()
    started = start_compression_analysis(
        db_path,
        scope,
        refresh=True,
        registry=registry,
    )
    cold_start_seconds = round(time.perf_counter() - started_at, 6)
    run_id = str(started["run_id"])
    poll_samples: list[float] = []
    deadline = time.monotonic() + 120
    while True:
        poll_started = time.perf_counter()
        status = compression_status(db_path, run_id=run_id, registry=registry)
        poll_samples.append(round(time.perf_counter() - poll_started, 6))
        if status["status"] not in {"pending", "running"}:
            break
        if time.monotonic() >= deadline:
            raise TimeoutError("Compression Lab benchmark did not complete")
        time.sleep(0.005)
    completion_seconds = round(time.perf_counter() - started_at, 6)
    if status["status"] not in {"completed", "completed_with_warnings"}:
        raise RuntimeError(f"Compression Lab benchmark failed: {status['status']}")
    routes = (
        _benchmark_route(
            "/api/compression/start",
            lambda: start_compression_analysis(db_path, scope, registry=registry),
            iterations=iterations,
        ),
        _benchmark_route(
            "/api/compression/status",
            lambda: compression_status(db_path, run_id=run_id, registry=registry),
            iterations=iterations,
        ),
        _benchmark_route(
            "/api/compression/profile",
            lambda: compression_profile(db_path, run_id=run_id),
            iterations=iterations,
        ),
    )
    return {
        "run_status": status["status"],
        "cold_start_seconds": cold_start_seconds,
        "completion_seconds": completion_seconds,
        "poll_samples_seconds": poll_samples,
        "poll_p95_seconds": _percentile(poll_samples, 0.95),
        "poll_max_seconds": max(poll_samples),
        "routes": routes,
    }


def _result_rows(payload: dict[str, object]) -> int:
    row_count = payload.get("row_count")
    if isinstance(row_count, int):
        return row_count
    rows = payload.get("rows")
    return len(rows) if isinstance(rows, list) else 0


def _percentile(samples: list[float], percentile: float) -> float:
    ordered = sorted(samples)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 6)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
