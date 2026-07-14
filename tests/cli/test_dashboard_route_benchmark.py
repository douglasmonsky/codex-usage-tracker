from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.benchmark_dashboard_routes import _evaluate_budgets


def test_dashboard_route_benchmark_emits_compact_synthetic_measurements(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "scripts/benchmark_dashboard_routes.py",
            "--sizes",
            "40",
            "--iterations",
            "1",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=repo_root,
        env={**os.environ, "PYTHONPATH": str(repo_root / "src")},
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["schema"] == "codex-usage-tracker-dashboard-route-benchmark-v1"
    assert payload["thresholds_enforced"] is False
    assert payload["budget_violations"] == []
    assert payload["fixtures"][0]["rows"] == 40
    routes = {row["path"]: row for row in payload["fixtures"][0]["routes"]}
    assert set(routes) == {
        "/api/summary",
        "/api/recommendations",
        "/api/threads",
        "/api/thread-calls",
        "/api/diagnostics/facts",
        "/api/diagnostics/tools",
        "/api/allowance/history",
        "/api/allowance/diagnostics",
    }
    assert routes["/api/summary"]["cold_seconds"] >= 0
    assert routes["/api/summary"]["cold_samples_seconds"]
    assert routes["/api/summary"]["cold_p95_seconds"] >= 0
    assert (
        routes["/api/summary"]["samples_seconds"] == routes["/api/summary"]["cold_samples_seconds"]
    )
    assert routes["/api/summary"]["median_seconds"] == routes["/api/summary"]["cold_median_seconds"]
    assert routes["/api/summary"]["p95_seconds"] == routes["/api/summary"]["cold_p95_seconds"]
    assert routes["/api/summary"]["warm_samples_seconds"]
    assert routes["/api/summary"]["warm_p95_seconds"] >= 0
    assert routes["/api/summary"]["cache_statuses"] == ["miss", "hit"]
    assert routes["/api/summary"]["payload_bytes"] > 0
    assert routes["/api/recommendations"]["result_rows"] <= 20
    assert routes["/api/threads"]["result_rows"] > 0
    assert routes["/api/thread-calls"]["result_rows"] > 0
    assert routes["/api/diagnostics/facts"]["cache_statuses"] == ["miss", "hit"]
    assert routes["/api/diagnostics/tools"]["result_rows"] > 0
    assert routes["/api/allowance/history"]["cache_statuses"] == ["miss", "hit"]
    assert routes["/api/allowance/diagnostics"]["cache_statuses"] == ["miss", "hit"]
    compression = payload["fixtures"][0]["compression_job"]
    assert compression["run_status"] in {"completed", "completed_with_warnings"}
    assert compression["cold_start_seconds"] >= 0
    assert compression["poll_samples_seconds"]
    assert compression["poll_p95_seconds"] <= compression["poll_max_seconds"]
    compression_routes = {row["path"]: row for row in compression["routes"]}
    assert set(compression_routes) == {
        "/api/compression/start",
        "/api/compression/status",
        "/api/compression/profile",
    }
    assert compression_routes["/api/compression/status"]["payload_bytes"] > 0
    assert compression_routes["/api/compression/status"]["p95_seconds"] >= 0
    assert str(tmp_path) not in result.stdout


def test_dashboard_route_budget_reports_metric_regressions() -> None:
    benchmark = {
        "fixtures": [
            {
                "rows": 100_000,
                "routes": [
                    {"path": "/api/threads", "p95_seconds": 1.25},
                ],
            }
        ]
    }
    budgets = {
        "fixture_rows": 100_000,
        "routes": {"/api/threads": {"p95_seconds": 1.0}},
    }

    assert _evaluate_budgets(benchmark, budgets) == [
        "/api/threads: p95_seconds 1.250000s exceeds 1.000000s"
    ]
