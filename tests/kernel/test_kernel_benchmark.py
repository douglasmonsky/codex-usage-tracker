from __future__ import annotations

import json
from pathlib import Path

import pytest

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

    stable_fields = {"calls", "rows", "tables", "seed"}
    assert {key: first[key] for key in stable_fields} == {
        key: second[key] for key in stable_fields
    }
    assert first["calls"] == 100
    assert first["rows"]["physical"] == 100
    assert first["rows"]["canonical"] <= 100
    assert first["wall_seconds"] >= first["writer_lock_seconds"] >= 0

    with pytest.raises(FileExistsError, match="benchmark database already exists"):
        run_benchmark(calls=100, seed=20260726, workspace=tmp_path / "first")
