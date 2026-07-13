#!/usr/bin/env python3
"""Benchmark deterministic serial and parallel first-refresh ingestion."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import resource
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from benchmark_synthetic_history import _write_synthetic_source_logs  # noqa: E402

from codex_usage_tracker.store.refresh import refresh_usage_index  # noqa: E402

_STABLE_TABLES = (
    "usage_events",
    "thread_summaries",
    "source_files",
    "source_records",
    "call_diagnostic_facts",
    "content_index_features",
    "conversation_turns",
    "tool_calls",
    "command_runs",
    "file_events",
    "content_fragments",
    "content_fts",
    "allowance_observations",
    "compression_record_facts",
    "compression_sequence_facts",
    "compression_thread_facts",
    "compression_fact_state",
    "compression_revision_state",
)
_VOLATILE_COLUMNS = frozenset(
    {
        "created_at",
        "updated_at",
        "indexed_at",
        "last_indexed_at",
        "computed_at",
        "last_accessed_at",
    }
)
_PROCESS_TREE_RSS_SAMPLE_SECONDS = 1.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--db-dir", type=Path)
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--aggregate-only", action="store_true")
    parser.add_argument("--parallel-workers", type=int)
    parser.add_argument("--enforce-thresholds", action="store_true")
    parser.add_argument("--max-parallel-seconds", type=float, default=20.0)
    parser.add_argument("--max-parallel-p95-seconds", type=float, default=25.0)
    parser.add_argument("--min-speedup-percent", type=float, default=10.0)
    parser.add_argument("--max-peak-rss-mb", type=float, default=544.0)
    parser.add_argument("--max-process-tree-rss-mb", type=float, default=544.0)
    parser.add_argument("--run-refresh", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--db-path", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    _validate_args(parser, args)

    if args.run_refresh is not None:
        if args.db_path is None:
            parser.error("--db-path is required with --run-refresh")
        _print_json(_run_refresh(args.run_refresh, args.db_path, args.aggregate_only))
        return 0

    temp_dir: Path | None = None
    if args.db_dir is None:
        temp_dir = Path(tempfile.mkdtemp(prefix="refresh-ingestion-benchmark-"))
        db_dir = temp_dir
    else:
        db_dir = args.db_dir.expanduser()
        db_dir.mkdir(parents=True, exist_ok=True)

    try:
        source_root = db_dir / f"synthetic-codex-home-{args.rows}"
        if source_root.exists():
            shutil.rmtree(source_root)
        bundle = _write_synthetic_source_logs(source_root, args.rows)
        source_files = len(bundle.paths)
        source_bytes = bundle.bytes_written
        del bundle
        serial = _benchmark_mode(
            source_root,
            db_dir=db_dir,
            mode="serial",
            runs=args.runs,
            aggregate_only=args.aggregate_only,
        )
        parallel = _benchmark_mode(
            source_root,
            db_dir=db_dir,
            mode="parallel",
            runs=args.runs,
            aggregate_only=args.aggregate_only,
            parallel_workers=args.parallel_workers,
        )
        differing_tables = sorted(
            table
            for table in set(serial["table_fingerprints"]) | set(parallel["table_fingerprints"])
            if serial["table_fingerprints"].get(table) != parallel["table_fingerprints"].get(table)
        )
        failures = _threshold_failures(args, serial=serial, parallel=parallel)
        payload = {
            "schema_version": 2,
            "synthetic": True,
            "rows": args.rows,
            "source_files": source_files,
            "source_bytes": source_bytes,
            "runs": args.runs,
            "aggregate_only": args.aggregate_only,
            "serial": serial,
            "parallel": parallel,
            "speedup_percent": round(
                100.0
                * (serial["median_seconds"] - parallel["median_seconds"])
                / serial["median_seconds"],
                3,
            ),
            "equivalent": serial["fingerprints"] == parallel["fingerprints"],
            "differing_tables": differing_tables,
            "threshold_status": "fail" if failures else "pass",
            "threshold_failures": failures,
        }
        if args.as_json:
            _print_json(payload)
        else:
            print(
                f"{args.rows:,} calls across {source_files} files: "
                f"serial {serial['median_seconds']:.3f}s, "
                f"parallel {parallel['median_seconds']:.3f}s, "
                f"P95 {parallel['p95_seconds']:.3f}s, "
                f"speedup {payload['speedup_percent']:.1f}%"
            )
        return 1 if args.enforce_thresholds and failures else 0
    finally:
        if temp_dir is not None and not args.keep:
            shutil.rmtree(temp_dir, ignore_errors=True)


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    for name in (
        "rows",
        "runs",
        "max_parallel_seconds",
        "max_parallel_p95_seconds",
        "max_peak_rss_mb",
        "max_process_tree_rss_mb",
    ):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    if args.min_speedup_percent < 0:
        parser.error("--min-speedup-percent must be nonnegative")
    if args.parallel_workers is not None and args.parallel_workers <= 0:
        parser.error("--parallel-workers must be positive")


def _benchmark_mode(
    source_root: Path,
    *,
    db_dir: Path,
    mode: str,
    runs: int,
    aggregate_only: bool,
    parallel_workers: int | None = None,
) -> dict[str, Any]:
    results = [
        _run_child(
            source_root,
            db_path=db_dir / f"refresh-{mode}-{index}.sqlite3",
            mode=mode,
            aggregate_only=aggregate_only,
            parallel_workers=parallel_workers,
        )
        for index in range(runs)
    ]
    timings = [float(result["seconds"]) for result in results]
    fingerprints = sorted({str(result["fingerprint"]) for result in results})
    return {
        "timings_seconds": timings,
        "median_seconds": round(median(timings), 6),
        "p95_seconds": round(_percentile(timings, 0.95), 6),
        "max_peak_rss_mb": max(float(result["peak_rss_mb"]) for result in results),
        "max_process_tree_peak_rss_mb": max(
            float(result["process_tree_peak_rss_mb"]) for result in results
        ),
        "max_workers": max(int(result["max_workers"]) for result in results),
        "fingerprints": fingerprints,
        "row_counts": results[0]["row_counts"],
        "table_fingerprints": results[0]["table_fingerprints"],
        "progress_phase_elapsed_seconds": results[0]["progress_phase_elapsed_seconds"],
        "pipeline_timings_seconds": results[0]["pipeline_timings_seconds"],
    }


def _run_child(
    source_root: Path,
    *,
    db_path: Path,
    mode: str,
    aggregate_only: bool,
    parallel_workers: int | None,
) -> dict[str, Any]:
    db_path.unlink(missing_ok=True)
    env = dict(os.environ)
    env.pop("COVERAGE_PROCESS_START", None)
    for key in tuple(env):
        if key.startswith("COV_CORE_"):
            env.pop(key)
    if mode == "serial":
        env["CODEX_USAGE_TRACKER_REFRESH_WORKERS"] = "1"
        env["CODEX_USAGE_TRACKER_CONTENT_INDEX_WORKERS"] = "1"
    else:
        if parallel_workers is None:
            env.pop("CODEX_USAGE_TRACKER_REFRESH_WORKERS", None)
            env.pop("CODEX_USAGE_TRACKER_CONTENT_INDEX_WORKERS", None)
        else:
            workers = str(parallel_workers)
            env["CODEX_USAGE_TRACKER_REFRESH_WORKERS"] = workers
            env["CODEX_USAGE_TRACKER_CONTENT_INDEX_WORKERS"] = workers
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--run-refresh",
        str(source_root),
        "--db-path",
        str(db_path),
        "--json",
    ]
    if aggregate_only:
        command.append("--aggregate-only")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )
    process_tree_peak_rss_mb = 0.0
    while True:
        process_tree_peak_rss_mb = max(
            process_tree_peak_rss_mb,
            _process_tree_rss_mb(process.pid),
        )
        try:
            stdout, stderr = process.communicate(timeout=_PROCESS_TREE_RSS_SAMPLE_SECONDS)
            break
        except subprocess.TimeoutExpired:
            continue
    if process.returncode != 0:
        raise RuntimeError(f"{mode} refresh failed: {stderr.strip()}")
    payload = dict(json.loads(stdout))
    payload["process_tree_peak_rss_mb"] = round(process_tree_peak_rss_mb, 3)
    return payload


def _run_refresh(source_root: Path, db_path: Path, aggregate_only: bool) -> dict[str, Any]:
    progress: list[dict[str, Any]] = []
    phase_started: dict[str, float] = {}
    phase_timings: dict[str, float] = {}
    started = perf_counter()

    def record_progress(payload: dict[str, object]) -> None:
        progress.append(dict(payload))
        now = perf_counter()
        phase = str(payload.get("phase") or "unknown")
        phase_started.setdefault(phase, now)
        if payload.get("status") in {"completed", "skipped", "failed"}:
            phase_timings[phase] = now - phase_started[phase]

    result = refresh_usage_index(
        source_root,
        db_path,
        include_archived=True,
        aggregate_only=aggregate_only,
        progress_callback=record_progress,
    )
    seconds = perf_counter() - started
    peak_rss_mb = _peak_rss_mb()
    final_progress_result: dict[str, object] = {}
    for item in reversed(progress):
        if isinstance(item.get("result"), dict):
            final_progress_result = cast(dict[str, object], item["result"])
            break
    pipeline_timings = final_progress_result.get("stage_timings_seconds")
    if not isinstance(pipeline_timings, dict):
        pipeline_timings = {}
    fingerprint, row_counts, table_fingerprints = _database_fingerprint(db_path)
    return {
        "seconds": round(seconds, 6),
        "peak_rss_mb": round(peak_rss_mb, 3),
        "max_workers": max((int(item.get("workers") or 1) for item in progress), default=1),
        "scanned_files": result.scanned_files,
        "parsed_events": result.parsed_events,
        "inserted_or_updated_events": result.inserted_or_updated_events,
        "fingerprint": fingerprint,
        "row_counts": row_counts,
        "table_fingerprints": table_fingerprints,
        "progress_phase_elapsed_seconds": {
            phase: round(seconds, 6) for phase, seconds in sorted(phase_timings.items())
        },
        "pipeline_timings_seconds": pipeline_timings,
    }


def _database_fingerprint(
    db_path: Path,
) -> tuple[str, dict[str, int], dict[str, str]]:
    digest = hashlib.sha256()
    counts: dict[str, int] = {}
    table_fingerprints: dict[str, str] = {}
    with sqlite3.connect(db_path) as conn:
        for table in _STABLE_TABLES:
            if not _table_exists(conn, table):
                continue
            columns = _stable_columns(conn, table)
            count = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # nosec B608
            counts[table] = count
            digest.update(f"{table}:{count}".encode())
            table_digest = hashlib.sha256()
            table_digest.update(f"{table}:{count}".encode())
            select_columns = ", ".join(f'"{column}"' for column in columns)
            order_columns = ", ".join(str(index + 1) for index in range(len(columns)))
            query = f"SELECT {select_columns} FROM {table} ORDER BY {order_columns}"  # nosec B608
            for row in conn.execute(query):
                encoded = repr(tuple(row)).encode()
                digest.update(encoded)
                table_digest.update(encoded)
            table_fingerprints[table] = table_digest.hexdigest()
    return digest.hexdigest(), counts, table_fingerprints


def _stable_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()  # nosec B608
    return [str(row[1]) for row in rows if str(row[1]) not in _VOLATILE_COLUMNS]


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        is not None
    )


def _threshold_failures(
    args: argparse.Namespace,
    *,
    serial: dict[str, Any],
    parallel: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    parallel_median = float(parallel["median_seconds"])
    parallel_p95 = float(parallel["p95_seconds"])
    speedup = (
        100.0
        * (float(serial["median_seconds"]) - parallel_median)
        / float(serial["median_seconds"])
    )
    if parallel_median > args.max_parallel_seconds:
        failures.append("parallel median exceeded threshold")
    if parallel_p95 > args.max_parallel_p95_seconds:
        failures.append("parallel P95 exceeded threshold")
    if speedup < args.min_speedup_percent:
        failures.append("parallel speedup was below threshold")
    if float(parallel["max_peak_rss_mb"]) > args.max_peak_rss_mb:
        failures.append("parallel coordinator peak RSS exceeded threshold")
    if float(parallel["max_process_tree_peak_rss_mb"]) > args.max_process_tree_rss_mb:
        failures.append("parallel process-tree peak RSS exceeded threshold")
    if serial["fingerprints"] != parallel["fingerprints"]:
        failures.append("serial and parallel fingerprints differed")
    if len(serial["fingerprints"]) != 1 or len(parallel["fingerprints"]) != 1:
        failures.append("refresh fingerprints were not stable across runs")
    return failures


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def _peak_rss_mb() -> float:
    peak = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024


def _process_tree_rss_mb(root_pid: int) -> float:
    result = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,rss="],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return 0.0
    return _process_tree_rss_kib_from_ps_output(result.stdout, root_pid=root_pid) / 1024


def _process_tree_rss_kib_from_ps_output(output: str, *, root_pid: int) -> int:
    rss_by_pid: dict[int, int] = {}
    children_by_pid: dict[int, list[int]] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        try:
            pid, parent_pid, rss_kib = (int(part) for part in parts)
        except ValueError:
            continue
        rss_by_pid[pid] = rss_kib
        children_by_pid.setdefault(parent_pid, []).append(pid)
    descendants = {root_pid}
    pending = [root_pid]
    while pending:
        children = children_by_pid.get(pending.pop(), [])
        descendants.update(children)
        pending.extend(children)
    return sum(rss_by_pid.get(pid, 0) for pid in descendants)


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
