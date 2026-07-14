"""Reusable runtime helpers for the dashboard route benchmark."""

from __future__ import annotations

import json
import math
import statistics
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from codex_usage_tracker.compression.api import (
    compression_profile,
    compression_status,
    start_compression_analysis,
)
from codex_usage_tracker.compression.jobs import CompressionJobRegistry
from codex_usage_tracker.compression.models import CompressionScope
from codex_usage_tracker.core.models import DiagnosticFact, UsageEvent
from codex_usage_tracker.server.allowance import (
    handle_allowance_diagnostics_request as handle_allowance_diagnostics_request,
)
from codex_usage_tracker.server.allowance import (
    handle_allowance_history_request as handle_allowance_history_request,
)
from codex_usage_tracker.server.diagnostic_facts import (
    handle_diagnostics_facts_request as handle_diagnostics_facts_request,
)
from codex_usage_tracker.server.threads import threads_payload as threads_payload
from codex_usage_tracker.store.api import (
    query_usage_api_event_count,
    query_usage_api_events,
)


def benchmark_route(
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
        "p95_seconds": percentile(samples, 0.95),
        "result_rows": result_rows(payload),
        "payload_bytes": len(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
    }


def thread_calls_benchmark_payload(db_path: Path, thread_key: str) -> dict[str, object]:
    rows = query_usage_api_events(
        db_path=db_path,
        thread_key=thread_key,
        include_archived=True,
        limit=100,
        sort="time",
        direction="desc",
    )
    return {
        "rows": rows,
        "row_count": len(rows),
        "total_matched_rows": query_usage_api_event_count(
            db_path=db_path,
            thread_key=thread_key,
            include_archived=True,
        ),
    }


def synthetic_diagnostic_facts(events: list[UsageEvent]) -> list[DiagnosticFact]:
    facts: list[DiagnosticFact] = []
    for index, event in enumerate(events):
        facts.extend(
            (
                DiagnosticFact(
                    record_id=event.record_id,
                    fact_type="tool",
                    fact_name=("exec_command", "read_file", "apply_patch")[index % 3],
                    fact_category="tool_activity",
                ),
                DiagnosticFact(
                    record_id=event.record_id,
                    fact_type="command_family",
                    fact_name=("rg", "git", "pytest", "sed")[index % 4],
                    fact_category="command_activity",
                ),
            )
        )
    return facts


def synthetic_allowance_event(event: UsageEvent, index: int) -> UsageEvent:
    return replace(
        event,
        rate_limit_plan_type="pro",
        rate_limit_limit_id="synthetic-codex",
        rate_limit_primary_used_percent=float(index % 100),
        rate_limit_primary_window_minutes=10_080,
        rate_limit_primary_resets_at=1_783_000_000 + (index // 100) * 604_800,
        rate_limit_secondary_used_percent=float((index * 3) % 100),
        rate_limit_secondary_window_minutes=300,
        rate_limit_secondary_resets_at=1_783_000_000 + (index // 100) * 18_000,
    )


def benchmark_compression_job(
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
        benchmark_route(
            "/api/compression/start",
            lambda: start_compression_analysis(db_path, scope, registry=registry),
            iterations=iterations,
        ),
        benchmark_route(
            "/api/compression/status",
            lambda: compression_status(db_path, run_id=run_id, registry=registry),
            iterations=iterations,
        ),
        benchmark_route(
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
        "poll_p95_seconds": percentile(poll_samples, 0.95),
        "poll_max_seconds": max(poll_samples),
        "routes": routes,
    }


def result_rows(payload: dict[str, object]) -> int:
    row_count = payload.get("row_count")
    if isinstance(row_count, int):
        return row_count
    rows = payload.get("rows")
    return len(rows) if isinstance(rows, list) else 0


def percentile(samples: list[float], percentile: float) -> float:
    ordered = sorted(samples)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 6)
