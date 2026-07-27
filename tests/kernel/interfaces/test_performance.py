from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from pathlib import Path

from codex_usage_tracker.kernel.application import KernelApplication

from .support import active_runtime, synthetic_sources

_STATUS_P95_BUDGET_MS = 50.0
_QUERY_P95_BUDGET_MS = 500.0
_GUIDANCE_P95_BUDGET_MS = 5.0
_GUIDANCE_RESPONSE_BUDGET_BYTES = 24_000


def test_warm_status_and_batched_query_adapter_budgets(tmp_path: Path) -> None:
    application = KernelApplication(
        active_runtime(tmp_path),
        worker_launcher=lambda _paths: None,
        source_provider=lambda _home: synthetic_sources(),
    )
    query = {
        "requests": [
            {
                "dataset": "calls",
                "operation": "aggregate",
                "dimensions": ["model", "effort"],
                "measures": ["calls", "total_tokens"],
                "limit": 25,
            }
        ]
    }

    status_p95 = _p95(application.status, repeats=40)
    query_p95 = _p95(lambda: application.query(query), repeats=20)
    guidance = {"requests": [], "include_guidance": True}
    guidance_p95 = _p95(lambda: application.query(guidance), repeats=40)
    guidance_bytes = len(
        json.dumps(
            application.query(guidance),
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )

    print(
        json.dumps(
            {
                "guidance_bytes": guidance_bytes,
                "guidance_p95_ms": round(guidance_p95, 3),
                "query_p95_ms": round(query_p95, 3),
                "status_p95_ms": round(status_p95, 3),
            },
            sort_keys=True,
        )
    )
    assert status_p95 <= _STATUS_P95_BUDGET_MS
    assert query_p95 <= _QUERY_P95_BUDGET_MS
    assert guidance_p95 <= _GUIDANCE_P95_BUDGET_MS
    assert guidance_bytes <= _GUIDANCE_RESPONSE_BUDGET_BYTES


def _p95(operation: Callable[[], object], *, repeats: int) -> float:
    operation()
    elapsed = []
    for _index in range(repeats):
        started = time.perf_counter()
        operation()
        elapsed.append((time.perf_counter() - started) * 1_000)
    ordered = sorted(elapsed)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]
