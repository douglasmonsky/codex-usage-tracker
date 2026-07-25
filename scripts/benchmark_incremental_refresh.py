#!/usr/bin/env python3
"""Benchmark cold, incremental, and concurrent-read refresh behavior.

The fixture is synthetic. It never reads a user's Codex home or usage index.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from time import perf_counter
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from codex_usage_tracker.store.api import (  # noqa: E402
    query_dashboard_event_count,
    refresh_metadata,
    refresh_usage_index,
)

DEFAULT_ROWS = 10_000
DEFAULT_APPEND_ROWS = 100
THRESHOLDS_SECONDS = {
    "cold_refresh": 30.0,
    "no_change_refresh": 1.0,
    "append_refresh": 5.0,
    "tail_followup_refresh": 3.0,
    "read_during_writer": 0.25,
}
SESSION_ID = "019fa20a-9460-7e21-b38a-000000000025"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--append-rows", type=int, default=DEFAULT_APPEND_ROWS)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--enforce-thresholds", action="store_true")
    parser.add_argument("--threshold-scale", type=float, default=1.0)
    args = parser.parse_args()
    if args.rows <= 0:
        parser.error("--rows must be positive")
    if args.append_rows <= 0:
        parser.error("--append-rows must be positive")
    if args.threshold_scale <= 0:
        parser.error("--threshold-scale must be positive")

    temporary = args.work_dir is None
    work_dir = (
        Path(tempfile.mkdtemp(prefix="codex-usage-incremental-"))
        if temporary
        else args.work_dir.expanduser()
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = run_benchmark(
            work_dir,
            rows=args.rows,
            append_rows=args.append_rows,
            threshold_scale=args.threshold_scale,
        )
        if args.as_json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            _print_summary(result)
        return 1 if args.enforce_thresholds and result["threshold_failures"] else 0
    finally:
        if temporary and not args.keep:
            shutil.rmtree(work_dir, ignore_errors=True)


def run_benchmark(
    work_dir: Path,
    *,
    rows: int,
    append_rows: int,
    threshold_scale: float = 1.0,
) -> dict[str, Any]:
    codex_home = work_dir / ".codex"
    db_path = work_dir / "usage.sqlite3"
    source_path = (
        codex_home
        / "sessions"
        / "2026"
        / "07"
        / f"rollout-2026-07-25T09-00-00-{SESSION_ID}.jsonl"
    )
    _write_fixture(codex_home, source_path, rows)

    cold = _timed_refresh(codex_home, db_path)
    cold_count = query_dashboard_event_count(db_path=db_path, include_archived=True)
    no_change = _timed_refresh(codex_home, db_path)

    _append_events(source_path, start=rows, count=append_rows)
    append = _timed_refresh(codex_home, db_path)
    append_count = query_dashboard_event_count(db_path=db_path, include_archived=True)

    pending_row = _token_row(rows + append_rows)
    with source_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(pending_row))
    incomplete_tail = _timed_refresh(codex_home, db_path)
    with source_path.open("a", encoding="utf-8") as handle:
        handle.write("\n")
    tail_followup = _timed_refresh(codex_home, db_path)
    final_count = query_dashboard_event_count(db_path=db_path, include_archived=True)

    read_during_writer = _measure_last_committed_read(db_path)
    timings = {
        "cold_refresh": cold["elapsed_seconds"],
        "no_change_refresh": no_change["elapsed_seconds"],
        "append_refresh": append["elapsed_seconds"],
        "tail_followup_refresh": tail_followup["elapsed_seconds"],
        "read_during_writer": read_during_writer,
    }
    thresholds = {
        key: round(value * threshold_scale, 6)
        for key, value in THRESHOLDS_SECONDS.items()
    }
    failures = [
        f"{name} {elapsed:.6f}s exceeded {thresholds[name]:.6f}s"
        for name, elapsed in timings.items()
        if elapsed > thresholds[name]
    ]
    invariants = {
        "cold_rows": cold_count,
        "append_rows_added": append_count - cold_count,
        "incomplete_tail_parsed_events": incomplete_tail["parsed_events"],
        "tail_followup_rows_added": final_count - append_count,
        "no_change_parsed_events": no_change["parsed_events"],
        "no_change_writer_lock_seconds": no_change["stage_timings_seconds"].get(
            "writer_lock",
            0.0,
        ),
    }
    expected = {
        "cold_rows": rows,
        "append_rows_added": append_rows,
        "incomplete_tail_parsed_events": 0,
        "tail_followup_rows_added": 1,
        "no_change_parsed_events": 0,
        "no_change_writer_lock_seconds": 0.0,
    }
    for name, expected_value in expected.items():
        if invariants[name] != expected_value:
            failures.append(
                f"{name} was {invariants[name]!r}; expected {expected_value!r}"
            )
    return {
        "schema": "codex-usage-tracker.incremental-refresh-benchmark.v1",
        "fixture": {
            "synthetic": True,
            "rows": rows,
            "append_rows": append_rows,
        },
        "refreshes": {
            "cold": cold,
            "no_change": no_change,
            "append": append,
            "incomplete_tail": incomplete_tail,
            "tail_followup": tail_followup,
        },
        "timings_seconds": timings,
        "thresholds_seconds": thresholds,
        "invariants": invariants,
        "threshold_failures": failures,
        "threshold_status": "pass" if not failures else "fail",
    }


def _timed_refresh(codex_home: Path, db_path: Path) -> dict[str, Any]:
    completed: dict[str, Any] = {}

    def capture(payload: dict[str, object]) -> None:
        if payload.get("phase") != "finalizing" or payload.get("status") != "completed":
            return
        result = payload.get("result")
        if isinstance(result, Mapping):
            completed.update(result)

    started = perf_counter()
    result = refresh_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        include_archived=True,
        aggregate_only=True,
        progress_callback=capture,
    )
    return {
        "elapsed_seconds": round(perf_counter() - started, 6),
        "parsed_events": result.parsed_events,
        "inserted_or_updated_events": result.inserted_or_updated_events,
        "stage_timings_seconds": dict(completed.get("stage_timings_seconds", {})),
    }


def _measure_last_committed_read(db_path: Path) -> float:
    writer = sqlite3.connect(db_path, timeout=0.1)
    try:
        writer.execute("BEGIN IMMEDIATE")
        started = perf_counter()
        count = query_dashboard_event_count(db_path=db_path, include_archived=True)
        metadata = refresh_metadata(db_path)
        elapsed = perf_counter() - started
        if count <= 0 or not metadata:
            raise RuntimeError("last-committed read returned an empty snapshot")
        return round(elapsed, 6)
    finally:
        writer.rollback()
        writer.close()


def _write_fixture(codex_home: Path, source_path: Path, rows: int) -> None:
    source_path.parent.mkdir(parents=True, exist_ok=True)
    session_index = codex_home / "session_index.jsonl"
    session_index.write_text(
        json.dumps(
            {
                "id": SESSION_ID,
                "thread_name": "Synthetic incremental refresh benchmark",
                "updated_at": "2026-07-25T09:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with source_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(_entry("session_meta", {"id": SESSION_ID})) + "\n")
        handle.write(
            json.dumps(
                _entry(
                    "turn_context",
                    {
                        "turn_id": "synthetic-turn",
                        "model": "gpt-5.5",
                        "effort": "medium",
                        "cwd": "/synthetic/codex-usage-tracker",
                    },
                )
            )
            + "\n"
        )
        for index in range(rows):
            handle.write(json.dumps(_token_row(index)) + "\n")


def _append_events(source_path: Path, *, start: int, count: int) -> None:
    with source_path.open("a", encoding="utf-8") as handle:
        for index in range(start, start + count):
            handle.write(json.dumps(_token_row(index)) + "\n")


def _token_row(index: int) -> dict[str, object]:
    cumulative = (index + 1) * 100
    return _entry(
        "event_msg",
        {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": cumulative - 30,
                    "cached_input_tokens": 20,
                    "output_tokens": 30,
                    "reasoning_output_tokens": 5,
                    "total_tokens": cumulative,
                },
                "last_token_usage": {
                    "input_tokens": 70,
                    "cached_input_tokens": 20,
                    "output_tokens": 30,
                    "reasoning_output_tokens": 5,
                    "total_tokens": 100,
                },
                "model_context_window": 258_400,
            },
        },
        timestamp=f"2026-07-25T09:{index // 60 % 60:02d}:{index % 60:02d}Z",
    )


def _entry(
    entry_type: str,
    payload: dict[str, object],
    *,
    timestamp: str = "2026-07-25T09:00:00Z",
) -> dict[str, object]:
    return {"timestamp": timestamp, "type": entry_type, "payload": payload}


def _print_summary(result: Mapping[str, Any]) -> None:
    timings = result["timings_seconds"]
    invariants = result["invariants"]
    print(
        "incremental refresh: "
        f"cold={timings['cold_refresh']:.3f}s, "
        f"no-change={timings['no_change_refresh']:.3f}s, "
        f"append={timings['append_refresh']:.3f}s, "
        f"tail-followup={timings['tail_followup_refresh']:.3f}s, "
        f"read-during-writer={timings['read_during_writer']:.4f}s"
    )
    print(
        "hydration counters: "
        f"cold={invariants['cold_rows']}, "
        f"append={invariants['append_rows_added']}, "
        f"pending-tail={invariants['incomplete_tail_parsed_events']}, "
        f"followup={invariants['tail_followup_rows_added']}"
    )
    print(f"thresholds: {result['threshold_status']}")
    for failure in result["threshold_failures"]:
        print(f"  FAIL {failure}")


if __name__ == "__main__":
    raise SystemExit(main())
