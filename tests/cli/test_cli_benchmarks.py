"""Release-gate coverage for synthetic history benchmarks."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def test_synthetic_history_benchmark_script_smoke(tmp_path: Path) -> None:
    payload = _run_benchmark_json(
        [
            "scripts/benchmark_synthetic_history.py",
            "--rows",
            "100",
            "--batch-size",
            "25",
            "--db-dir",
            str(tmp_path),
            "--json",
            "--enforce-thresholds",
            "--threshold-scale",
            "5",
        ],
    )

    assert payload["threshold_scale"] == 5.0
    assert payload["benchmarks"][0]["rows"] == 100
    assert payload["benchmarks"][0]["filtered_rows"] <= 50
    assert "idx_usage_model_effort" in payload["benchmarks"][0]["query_plan"]
    assert payload["benchmarks"][0]["threshold_status"] == "pass"
    assert payload["benchmarks"][0]["threshold_failures"] == []
    assert {
        "populate_seconds",
        "active_dashboard_query_seconds",
        "all_history_dashboard_query_seconds",
        "since_until_query_seconds",
        "filtered_query_seconds",
        "filtered_count_seconds",
        "dashboard_payload_active_seconds",
        "thread_summary_seconds",
        "recommendations_report_seconds",
        "pricing_coverage_seconds",
        "project_summary_seconds",
    } <= set(payload["benchmarks"][0]["timings"])


def test_synthetic_history_benchmark_with_source_logs_smoke(tmp_path: Path) -> None:
    payload = _run_benchmark_json(
        [
            "scripts/benchmark_synthetic_history.py",
            "--rows",
            "100",
            "--batch-size",
            "25",
            "--db-dir",
            str(tmp_path),
            "--with-source-logs",
            "--json",
            "--enforce-thresholds",
            "--threshold-scale",
            "10",
        ],
    )
    benchmark = payload["benchmarks"][0]

    assert payload["threshold_scale"] == 10.0
    assert benchmark["threshold_status"] == "pass"
    assert benchmark["threshold_failures"] == []
    assert benchmark["source_logs_generated"] > 0
    assert benchmark["source_log_bytes"] > 0
    assert benchmark["context_load_seconds"] is not None
    assert benchmark["context_payload_json_bytes"] > 0
    assert benchmark["source_scan_ms"] >= 0
    assert benchmark["serialized_estimate_ms"] >= 0
    assert {
        "dashboard_payload_with_source_logs_seconds",
        "context_load_early_line_seconds",
        "context_load_middle_line_seconds",
        "context_load_late_line_seconds",
    } <= set(benchmark["timings"])
    assert {"early", "middle", "late"} == set(benchmark["context_loads"])
    assert benchmark["context_loads"]["middle"]["context_payload_json_bytes"] > 0
    assert benchmark["context_loads"]["middle"]["source_scan_ms"] >= 0


def _run_benchmark_json(args: list[str]) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=repo_root,
        env=_subprocess_env(),
    )
    try:
        payload: dict[str, Any] = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            "benchmark did not emit JSON\n"
            f"returncode={result.returncode}\n"
            f"stdout={result.stdout}\n"
            f"stderr={result.stderr}"
        ) from exc
    if result.returncode != 0:
        failures = [
            failure
            for benchmark in payload.get("benchmarks", [])
            if isinstance(benchmark, dict)
            for failure in benchmark.get("threshold_failures", [])
        ]
        raise AssertionError(
            "benchmark exited nonzero\n"
            f"returncode={result.returncode}\n"
            f"threshold_failures={failures}\n"
            f"stderr={result.stderr}\n"
            f"payload={json.dumps(payload, indent=2)}"
        )
    return payload


def _subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    repo_root = Path(__file__).resolve().parents[2]
    src_path = str(repo_root / "src")
    env["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else src_path
    )
    return env
