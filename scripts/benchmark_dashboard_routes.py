#!/usr/bin/env python3
"""Benchmark representative dashboard routes with deterministic synthetic data."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections.abc import Callable, Mapping
from http import HTTPStatus
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"
SCRIPT_PATH = REPO_ROOT / "scripts"
if str(SCRIPT_PATH) not in sys.path:
    sys.path.insert(0, str(SCRIPT_PATH))
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import dashboard_route_benchmark_support as route_support  # noqa: E402
from benchmark_synthetic_history import (  # noqa: E402
    SYNTHETIC_THREAD_NAMES,
    _synthetic_events,
    _write_benchmark_config,
)

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
        description="Measure dashboard route baselines and optionally enforce budgets.",
    )
    parser.add_argument("--sizes", nargs="+", type=_positive_int, default=DEFAULT_SIZES)
    parser.add_argument("--iterations", type=_positive_int, default=3)
    parser.add_argument("--batch-size", type=_positive_int, default=10_000)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--skip-compression", action="store_true")
    parser.add_argument("--enforce-thresholds", action="store_true")
    parser.add_argument(
        "--budget-file",
        type=Path,
        default=REPO_ROOT / "config" / "dashboard-route-budgets.json",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    fixtures = [
        benchmark_fixture(
            rows=rows,
            output_dir=args.output_dir,
            iterations=args.iterations,
            batch_size=args.batch_size,
            include_compression=not args.skip_compression,
        )
        for rows in args.sizes
    ]
    payload: dict[str, object] = {
        "schema": "codex-usage-tracker-dashboard-route-benchmark-v1",
        "thresholds_enforced": args.enforce_thresholds,
        "fixtures": fixtures,
    }
    violations = (
        _evaluate_budgets(payload, _load_budgets(args.budget_file))
        if args.enforce_thresholds
        else []
    )
    payload["budget_violations"] = violations
    print(json.dumps(payload, sort_keys=True))
    return 1 if violations else 0


def benchmark_fixture(
    *,
    rows: int,
    output_dir: Path,
    iterations: int,
    batch_size: int,
    include_compression: bool,
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
        events = [
            route_support.synthetic_allowance_event(event, start + index)
            for index, event in enumerate(_synthetic_events(start, min(start + batch_size, rows)))
        ]
        upsert_usage_events(
            events,
            db_path=db_path,
            refresh_links=False,
            diagnostic_facts=route_support.synthetic_diagnostic_facts(events),
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

    def benchmark_diagnostic_facts(cache: AggregateQueryCache, send_json: JsonSender) -> None:
        route_support.handle_diagnostics_facts_request(
            "limit=50&include_archived=true&sort=uncached&direction=desc",
            db_path=db_path,
            include_archived_default=True,
            request_path="/api/diagnostics/facts",
            fact_type=None,
            fact_group=None,
            privacy_mode="normal",
            query_cache=cache,
            send_error=_raise_route_error,
            send_exception=_raise_route_exception,
            send_json=send_json,
        )

    def benchmark_diagnostic_tools(cache: AggregateQueryCache, send_json: JsonSender) -> None:
        route_support.handle_diagnostics_facts_request(
            "limit=25&include_archived=true&sort=uncached&direction=desc",
            db_path=db_path,
            include_archived_default=True,
            request_path="/api/diagnostics/tools",
            fact_type=None,
            fact_group="tools",
            privacy_mode="normal",
            query_cache=cache,
            send_error=_raise_route_error,
            send_exception=_raise_route_exception,
            send_json=send_json,
        )

    def benchmark_allowance_history(cache: AggregateQueryCache, send_json: JsonSender) -> None:
        route_support.handle_allowance_history_request(
            "limit=1000&include_archived=true&privacy_mode=normal",
            db_path=db_path,
            allowance_path=config["allowance_path"],
            rate_card_path=rate_card_path,
            include_archived_default=True,
            privacy_mode="normal",
            query_cache=cache,
            send_error=_raise_route_error,
            send_exception=_raise_route_exception,
            send_json=send_json,
        )

    def benchmark_allowance_diagnostics(cache: AggregateQueryCache, send_json: JsonSender) -> None:
        route_support.handle_allowance_diagnostics_request(
            "limit=0&include_archived=true&privacy_mode=normal",
            db_path=db_path,
            allowance_path=config["allowance_path"],
            rate_card_path=rate_card_path,
            include_archived_default=True,
            privacy_mode="normal",
            query_cache=cache,
            send_error=_raise_route_error,
            send_exception=_raise_route_exception,
            send_json=send_json,
        )

    route_actions: tuple[tuple[str, RouteAction, int], ...] = (
        ("/api/summary", benchmark_summary, 256 * 1_024),
        ("/api/recommendations", benchmark_recommendations, 256 * 1_024),
        ("/api/diagnostics/facts", benchmark_diagnostic_facts, 256 * 1_024),
        ("/api/diagnostics/tools", benchmark_diagnostic_tools, 256 * 1_024),
        ("/api/allowance/history", benchmark_allowance_history, 8 * 1_024 * 1_024),
        ("/api/allowance/diagnostics", benchmark_allowance_diagnostics, 8 * 1_024 * 1_024),
    )
    routes = [
        _benchmark_cached_route(
            path,
            action=action,
            iterations=iterations,
            max_payload_bytes=max_payload_bytes,
        )
        for path, action, max_payload_bytes in route_actions
    ]
    routes.append(
        route_support.benchmark_route(
            "/api/calls",
            lambda: route_support.calls_filter_benchmark_payload(db_path),
            iterations=iterations,
        )
    )
    routes.append(
        route_support.benchmark_route(
            "/api/threads",
            lambda: route_support.threads_payload(
                "limit=250&include_archived=true&sort=tokens&direction=desc",
                db_path=db_path,
                include_archived_default=True,
            ),
            iterations=iterations,
        )
    )
    benchmark_thread_key = f"thread:{SYNTHETIC_THREAD_NAMES[0]}"
    routes.append(
        route_support.benchmark_route(
            "/api/thread-calls",
            lambda: route_support.thread_calls_benchmark_payload(db_path, benchmark_thread_key),
            iterations=iterations,
        )
    )
    result: dict[str, object] = {
        "rows": rows,
        "populate_seconds": populate_seconds,
        "recommendation_materialization": {
            "rows": materialized_rows,
            "seconds": materialize_seconds,
        },
        "routes": routes,
    }
    if include_compression:
        result["compression_job"] = route_support.benchmark_compression_job(
            db_path,
            iterations=iterations,
        )
    return result


def _benchmark_cached_route(
    path: str,
    *,
    action: RouteAction,
    iterations: int,
    max_payload_bytes: int = 256 * 1_024,
) -> dict[str, object]:
    cold_samples: list[float] = []
    cold_statuses: list[str] = []
    payload: dict[str, object] = {}
    body = b""
    for _ in range(iterations):
        started = time.perf_counter()
        payload, body, status = _invoke_route(
            action,
            AggregateQueryCache(max_payload_bytes=max_payload_bytes),
        )
        cold_samples.append(round(time.perf_counter() - started, 6))
        cold_statuses.append(status)

    warm_cache = AggregateQueryCache(max_payload_bytes=max_payload_bytes)
    _invoke_route(action, warm_cache)
    warm_samples: list[float] = []
    warm_statuses: list[str] = []
    for _ in range(iterations):
        started = time.perf_counter()
        payload, body, status = _invoke_route(action, warm_cache)
        warm_samples.append(round(time.perf_counter() - started, 6))
        warm_statuses.append(status)

    cold_median = round(statistics.median(cold_samples), 6)
    cold_p95 = route_support.percentile(cold_samples, 0.95)
    return {
        "path": path,
        "cold_seconds": cold_median,
        "cold_samples_seconds": cold_samples,
        "cold_median_seconds": cold_median,
        "cold_p95_seconds": cold_p95,
        "warm_samples_seconds": warm_samples,
        "warm_median_seconds": round(statistics.median(warm_samples), 6),
        "warm_p95_seconds": route_support.percentile(warm_samples, 0.95),
        "samples_seconds": cold_samples,
        "median_seconds": cold_median,
        "p95_seconds": cold_p95,
        "cache_statuses": [*cold_statuses, *warm_statuses],
        "result_rows": route_support.result_rows(payload),
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


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def _load_budgets(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("dashboard route budget file must contain an object")
    if payload.get("schema") != "codex-usage-tracker-dashboard-route-budgets-v1":
        raise ValueError("unsupported dashboard route budget schema")
    return payload


def _evaluate_budgets(
    benchmark: Mapping[str, object],
    budgets: Mapping[str, object],
) -> list[str]:
    fixture_rows = budgets.get("fixture_rows")
    if not isinstance(fixture_rows, int):
        raise ValueError("dashboard route budget fixture_rows must be an integer")
    fixtures = benchmark.get("fixtures")
    fixture = (
        next(
            (
                row
                for row in fixtures
                if isinstance(fixtures, list)
                and isinstance(row, dict)
                and row.get("rows") == fixture_rows
            ),
            None,
        )
        if isinstance(fixtures, list)
        else None
    )
    if fixture is None:
        return [f"missing benchmark fixture for {fixture_rows} rows"]
    routes = fixture.get("routes")
    route_results = (
        {
            str(row.get("path")): row
            for row in routes
            if isinstance(routes, list) and isinstance(row, dict)
        }
        if isinstance(routes, list)
        else {}
    )
    route_budgets = budgets.get("routes")
    if not isinstance(route_budgets, dict):
        raise ValueError("dashboard route budgets must contain a routes object")
    violations: list[str] = []
    for path, metrics in route_budgets.items():
        result = route_results.get(str(path))
        if result is None:
            violations.append(f"{path}: route result missing")
            continue
        if not isinstance(metrics, dict):
            raise ValueError(f"dashboard route budget for {path} must be an object")
        for metric, maximum in metrics.items():
            actual = result.get(str(metric))
            if not isinstance(maximum, int | float) or not isinstance(actual, int | float):
                violations.append(f"{path}: metric {metric} missing or non-numeric")
                continue
            if float(actual) > float(maximum):
                violations.append(
                    f"{path}: {metric} {float(actual):.6f}s exceeds {float(maximum):.6f}s"
                )
    return violations


if __name__ == "__main__":
    raise SystemExit(main())
