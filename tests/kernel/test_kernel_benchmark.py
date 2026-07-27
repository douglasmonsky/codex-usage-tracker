from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUDGET_PATH = _REPO_ROOT / "config" / "kernel-performance-budget.json"


def test_kernel_baseline_records_required_comparison_workloads() -> None:
    assert _BUDGET_PATH.is_file(), "K1 performance evidence is missing"
    payload = json.loads(_BUDGET_PATH.read_text(encoding="utf-8"))

    assert payload["schema"] == "codex-usage-tracker.kernel-performance-baseline.v1"
    assert payload["acceptance_role"] == "comparison_evidence_only"
    assert payload["seed"] == 20260726
    assert {row["calls"] for row in payload["workloads"]} == {10_000, 100_000}
    for row in payload["workloads"]:
        assert row.keys() >= {
            "calls",
            "rows",
            "tables",
            "database_bytes",
            "package_bytes",
            "wall_seconds",
            "writer_lock_seconds",
            "environment",
        }


def test_benchmark_small_workload_is_seeded_and_structured(tmp_path: Path) -> None:
    from scripts.benchmark_kernel import run_benchmark

    first = run_benchmark(calls=100, seed=20260726, workspace=tmp_path / "first")
    second = run_benchmark(calls=100, seed=20260726, workspace=tmp_path / "second")

    stable_fields = {
        "calls",
        "seed",
        "canonical_calls_after_replacement",
        "no_change_preserved_bytes",
    }
    assert {key: first[key] for key in stable_fields} == {
        key: second[key] for key in stable_fields
    }
    assert first["calls"] == 100
    assert first["canonical_calls_after_replacement"] == 1
    assert first["no_change_preserved_bytes"] is True
    phases = first["phases"]
    assert set(phases) == {"initial", "no_change", "append", "replacement"}
    assert phases["initial"]["inserted_calls"] == 100
    assert phases["no_change"]["inserted_calls"] == 0
    assert phases["no_change"]["planner_reason"] == "no_changes"
    assert phases["append"]["inserted_calls"] == 1
    assert phases["append"]["planner_reason"] == "append_safe"
    assert phases["replacement"]["deleted_rows"] == 101
    assert phases["replacement"]["inserted_calls"] == 1
    assert phases["replacement"]["planner_reason"] == "truncate_source"
    for phase in phases.values():
        assert phase["elapsed_ms"] >= phase["writer_p95_ms"] >= 0
        assert phase["writer_transactions"] >= 0
