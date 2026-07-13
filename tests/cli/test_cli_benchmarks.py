"""Release-gate coverage for synthetic history benchmarks."""

from __future__ import annotations

import json
import os
import sqlite3
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


def test_compression_lab_benchmark_script_smoke(tmp_path: Path) -> None:
    args = [
        "scripts/benchmark_compression_lab.py",
        "--rows",
        "100",
        "--batch-size",
        "25",
        "--db-dir",
        str(tmp_path),
        "--json",
        "--enforce-thresholds",
        "--max-cold-seconds",
        "10",
    ]

    payload = _run_benchmark_json(args)
    repeated = _run_benchmark_json(args)

    assert payload["schema_version"] == 1
    assert payload["synthetic"] is True
    assert payload["rows"] == 100
    assert payload["cold_build"]["candidate_count"] == 10
    assert payload["cold_build"]["peak_rss_mb"] > 0
    assert payload["cold_build"]["candidate_fingerprint"]
    assert payload["cold_build"]["profile_fingerprint"]
    assert (
        payload["cold_build"]["candidate_fingerprint"]
        == "2dd80ca48382546f39943c4567124038e5e50f44d833a18073bf69aa7dd85de3"
    )
    assert (
        payload["cold_build"]["profile_fingerprint"]
        == "a04e19e6e6cb127ee3b879d963b8995d9426908dc25737078b61e2ba799e9983"
    )
    assert payload["cold_build"]["stage_timings_seconds"]["evidence_loaded"] >= 0
    assert payload["warm_build"]["cache_mode"] == "exact"
    assert payload["threshold_failures"] == []
    assert (
        repeated["cold_build"]["candidate_fingerprint"]
        == payload["cold_build"]["candidate_fingerprint"]
    )
    assert (
        repeated["cold_build"]["profile_fingerprint"]
        == payload["cold_build"]["profile_fingerprint"]
    )


def test_compression_lab_benchmark_with_normalized_evidence(tmp_path: Path) -> None:
    payload = _run_benchmark_json(
        [
            "scripts/benchmark_compression_lab.py",
            "--rows",
            "100",
            "--batch-size",
            "25",
            "--db-dir",
            str(tmp_path),
            "--with-normalized-evidence",
            "--max-peak-rss-mb",
            "512",
            "--json",
            "--enforce-thresholds",
            "--max-cold-seconds",
            "10",
        ],
    )

    assert payload["normalized_evidence"] is True
    assert payload["normalized_evidence_rows"] == 500
    assert payload["cold_build"]["candidate_count"] > 10
    assert payload["cold_build"]["peak_rss_mb"] <= 512
    assert payload["max_evidence_detector_seconds"] > 0
    assert (
        payload["cold_build"]["stage_timings_seconds"]["detectors"]
        <= payload["max_evidence_detector_seconds"]
    )
    assert payload["threshold_failures"] == []

    db_path = tmp_path / "compression-synthetic-100.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            DROP TABLE compression_fact_state;
            DROP TABLE compression_thread_facts;
            DROP TABLE compression_sequence_facts;
            DROP TABLE compression_record_facts;
            DELETE FROM schema_migrations WHERE version = 16;
            PRAGMA user_version = 15;
            """
        )

    fallback = _run_benchmark_json(
        ["scripts/benchmark_compression_lab.py", "--run-db", str(db_path)]
    )
    prepared = _run_benchmark_json(
        [
            "scripts/benchmark_compression_lab.py",
            "--prepare-facts-db",
            str(db_path),
        ],
    )
    assert prepared["record_count"] == 100
    assert prepared["sequence_count"] > 0
    assert set(prepared["stage_timings_seconds"]) == {
        "init",
        "clear",
        "record_facts",
        "record_manifests",
        "sequence_facts",
        "thread_facts",
        "indexes",
        "state",
    }
    fact_backed = _run_benchmark_json(
        ["scripts/benchmark_compression_lab.py", "--run-db", str(db_path)]
    )
    assert (
        fact_backed["cold_build"]["candidate_fingerprint"]
        == fallback["cold_build"]["candidate_fingerprint"]
    )
    assert (
        fact_backed["cold_build"]["profile_fingerprint"]
        == fallback["cold_build"]["profile_fingerprint"]
    )


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
