#!/usr/bin/env python3
"""Measure explicit kernel build, no-change, append, and replacement refreshes."""

from __future__ import annotations

import argparse
import json
import math
import platform
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger
from codex_usage_tracker.kernel.operational import (
    kernel_paths,
    load_cutover_control,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE_ROOT = _REPO_ROOT / "src" / "codex_usage_tracker" / "kernel"


def _token_line(event_id: str, value: int) -> str:
    return (
        '{"event_id":"'
        + event_id
        + '","timestamp":"2026-01-01T00:00:01Z","type":"event_msg",'
        '"payload":{"type":"token_count","info":{"last_token_usage":'
        '{"input_tokens":'
        + str(value)
        + ',"cached_input_tokens":1,"output_tokens":2,'
        '"reasoning_output_tokens":1,"total_tokens":'
        + str(value + 2)
        + '},"model_context_window":200000}}}\n'
    )


def _prefix() -> str:
    return (
        '{"timestamp":"2026-01-01T00:00:00Z","type":"session_meta",'
        '"payload":{"id":"synthetic-benchmark-session"}}\n'
        '{"timestamp":"2026-01-01T00:00:00Z","type":"turn_context",'
        '"payload":{"turn_id":"turn-1","model":"gpt-synthetic",'
        '"effort":"low"}}\n'
    )


def _p95(values: tuple[float, ...]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def _refresh(
    ingestor: KernelIngestor,
    source: Path,
    *,
    owner_id: str,
) -> dict[str, object]:
    started = time.perf_counter()
    result = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id=owner_id,
    )
    return {
        "elapsed_ms": round((time.perf_counter() - started) * 1_000, 3),
        "generation": result.generation,
        "inserted_calls": result.inserted_calls,
        "deleted_rows": result.deleted_rows,
        "planner_reason": result.planner_reason,
        "writer_p95_ms": round(_p95(result.writer_transaction_ms), 3),
        "writer_transactions": len(result.writer_transaction_ms),
    }


def run_benchmark(
    *,
    calls: int,
    seed: int,
    workspace: Path,
) -> dict[str, Any]:
    """Run one isolated synthetic kernel refresh lifecycle."""

    if calls <= 0:
        raise ValueError("calls must be positive")
    workspace.mkdir(parents=True, exist_ok=True)
    source = workspace / "sessions" / "rollout-synthetic.jsonl"
    if source.exists():
        raise FileExistsError(f"benchmark source already exists: {source}")
    source.parent.mkdir()
    source.write_text(
        _prefix()
        + "".join(
            _token_line(f"event-{index:08d}", (index + seed) % 1_000)
            for index in range(calls)
        ),
        encoding="utf-8",
    )
    paths = kernel_paths(workspace / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)

    initial = _refresh(ingestor, source, owner_id="benchmark-initial")
    analytical_before = paths.analytical.read_bytes()
    no_change = _refresh(ingestor, source, owner_id="benchmark-no-change")
    no_change_preserved_bytes = paths.analytical.read_bytes() == analytical_before

    with source.open("a", encoding="utf-8") as handle:
        handle.write(_token_line("event-append", seed % 1_000))
    append = _refresh(ingestor, source, owner_id="benchmark-append")

    source.write_text(
        _prefix() + _token_line("event-replacement", seed % 1_000),
        encoding="utf-8",
    )
    replacement = _refresh(
        ingestor,
        source,
        owner_id="benchmark-replacement",
    )
    active_path = load_cutover_control(paths.operational).active_kernel_path
    if active_path is None:
        raise RuntimeError("benchmark refresh did not publish an active generation")
    with sqlite3.connect(active_path) as connection:
        canonical_calls = int(
            connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0]
        )

    return {
        "calls": calls,
        "seed": seed,
        "database_bytes": active_path.stat().st_size,
        "canonical_calls_after_replacement": canonical_calls,
        "no_change_preserved_bytes": no_change_preserved_bytes,
        "phases": {
            "initial": initial,
            "no_change": no_change,
            "append": append,
            "replacement": replacement,
        },
    }


def _package_bytes() -> int:
    return sum(
        path.stat().st_size
        for path in _PACKAGE_ROOT.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def _environment() -> dict[str, str]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(),
        "commit": commit,
        "runtime": "0.26 explicit kernel refresh lifecycle",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--calls", type=int, action="append", required=True)
    parser.add_argument("--seed", type=int, default=20260726)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    rows = [
        run_benchmark(
            calls=calls,
            seed=arguments.seed,
            workspace=arguments.workspace / f"calls-{calls}",
        )
        for calls in arguments.calls
    ]
    payload = {
        "schema": "codex-usage-tracker.kernel-performance-qualification.v1",
        "acceptance_role": "synthetic_release_evidence",
        "seed": arguments.seed,
        "environment": _environment(),
        "package_bytes": _package_bytes(),
        "workloads": rows,
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(encoded)
    else:
        arguments.output.write_text(encoded, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
