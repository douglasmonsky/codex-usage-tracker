from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


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
    assert payload["fixtures"][0]["rows"] == 40
    routes = {row["path"]: row for row in payload["fixtures"][0]["routes"]}
    assert set(routes) == {"/api/summary", "/api/recommendations"}
    assert routes["/api/summary"]["samples_seconds"]
    assert routes["/api/recommendations"]["result_rows"] <= 20
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
