#!/usr/bin/env python3
"""Measure the v0.25.1 persistence path on fixed synthetic call workloads."""

from __future__ import annotations

import argparse
import json
import platform
import random
import sqlite3
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.models import UsageEvent
from codex_usage_tracker.core.usage_identity import usage_identity_from_values
from codex_usage_tracker.store.connection import configure_connection
from codex_usage_tracker.store.schema import init_db
from codex_usage_tracker.store.usage_event_writer import upsert_usage_events_in_connection

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE_ROOT = _REPO_ROOT / "src" / "codex_usage_tracker"


def run_benchmark(*, calls: int, seed: int, workspace: Path) -> dict[str, Any]:
    """Run one isolated old-runtime write and return bounded comparison evidence."""

    if calls <= 0:
        raise ValueError("calls must be positive")
    workspace.mkdir(parents=True, exist_ok=True)
    db_path = workspace / "usage.sqlite3"
    if db_path.exists():
        raise FileExistsError(f"benchmark database already exists: {db_path}")
    started = time.perf_counter()
    events = _synthetic_events(calls=calls, seed=seed)

    conn = sqlite3.connect(db_path, timeout=60.0)
    try:
        configure_connection(conn, busy_timeout_ms=60_000)
        init_db(conn)
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        writer_started = time.perf_counter()
        upsert_usage_events_in_connection(conn, events)
        conn.commit()
        writer_lock_seconds = time.perf_counter() - writer_started
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        physical = int(conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0])
        canonical = int(
            conn.execute("SELECT COUNT(*) FROM canonical_usage_events").fetchone()[0]
        )
        tables = int(
            conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
        )
    finally:
        conn.close()

    return {
        "calls": calls,
        "seed": seed,
        "rows": {"physical": physical, "canonical": canonical},
        "tables": tables,
        "database_bytes": db_path.stat().st_size,
        "package_bytes": _package_bytes(),
        "wall_seconds": round(time.perf_counter() - started, 6),
        "writer_lock_seconds": round(writer_lock_seconds, 6),
        "environment": _environment(),
    }


def _synthetic_events(*, calls: int, seed: int) -> list[UsageEvent]:
    randomizer = random.Random(seed)
    events: list[UsageEvent] = []
    prior: UsageEvent | None = None
    for index in range(calls):
        duplicate = index > 0 and index % 20 == 0 and prior is not None
        if duplicate:
            event = replace(
                prior,
                record_id=f"physical-{index:09d}",
                session_id=f"copy-{index:09d}",
                source_file=f"archived_sessions/synthetic-{index % 32:02d}.jsonl",
                line_number=index + 1,
                is_archived=1,
            )
        else:
            input_tokens = randomizer.randint(80, 8_000)
            cached_input_tokens = randomizer.randint(0, input_tokens)
            output_tokens = randomizer.randint(8, 800)
            reasoning_output_tokens = randomizer.randint(0, output_tokens)
            thread_index = index % 250
            cumulative = (index // 250 + 1) * (input_tokens + output_tokens)
            event = UsageEvent(
                record_id=f"physical-{index:09d}",
                session_id=f"session-{thread_index:04d}",
                thread_name=f"Synthetic thread {thread_index:04d}",
                session_updated_at="2026-01-01T00:00:00Z",
                event_timestamp=f"2026-01-{1 + (index % 28):02d}T{index % 24:02d}:00:00Z",
                source_file=f"sessions/synthetic-{index % 32:02d}.jsonl",
                line_number=index + 1,
                turn_id=f"turn-{index:09d}",
                turn_timestamp=f"2026-01-{1 + (index % 28):02d}T{index % 24:02d}:00:00Z",
                cwd="workspaces/kernel-benchmark",
                model=("gpt-5.4" if index % 3 else "gpt-5.3-codex"),
                effort=("high" if index % 2 else "medium"),
                current_date="2026-01-01",
                timezone="UTC",
                call_initiator="user",
                call_initiator_reason="synthetic_benchmark",
                call_initiator_confidence="high",
                is_archived=0,
                thread_key=f"thread:synthetic-{thread_index:04d}",
                thread_call_index=None,
                previous_record_id=None,
                next_record_id=None,
                thread_source="cli",
                subagent_type=None,
                agent_role=None,
                agent_nickname=None,
                parent_session_id=None,
                parent_thread_name=None,
                parent_session_updated_at=None,
                model_context_window=200_000,
                input_tokens=input_tokens,
                cached_input_tokens=cached_input_tokens,
                output_tokens=output_tokens,
                reasoning_output_tokens=reasoning_output_tokens,
                total_tokens=input_tokens + output_tokens,
                cumulative_input_tokens=cumulative - output_tokens,
                cumulative_cached_input_tokens=min(cached_input_tokens, cumulative),
                cumulative_output_tokens=output_tokens,
                cumulative_reasoning_output_tokens=reasoning_output_tokens,
                cumulative_total_tokens=cumulative,
                service_tier=("fast" if index % 10 == 0 else "standard"),
                fast=(1 if index % 10 == 0 else 0),
                service_tier_source="synthetic_benchmark",
                service_tier_confidence="high",
            )
            identity = usage_identity_from_values(event.to_row())
            event = replace(
                event,
                usage_fingerprint=identity.usage_fingerprint,
                canonical_record_id=identity.canonical_record_id,
            )
            prior = event
        events.append(event)
    return events


def _package_bytes() -> int:
    return sum(
        path.stat().st_size
        for path in _PACKAGE_ROOT.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
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
        "runtime": "v0.25.1 persistence including derived-state maintenance",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--calls", type=int, action="append", required=True)
    parser.add_argument("--seed", type=int, default=20260726)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rows = [
        run_benchmark(
            calls=calls,
            seed=args.seed,
            workspace=args.workspace / f"calls-{calls}",
        )
        for calls in args.calls
    ]
    payload = {
        "schema": "codex-usage-tracker.kernel-performance-baseline.v1",
        "acceptance_role": "comparison_evidence_only",
        "seed": args.seed,
        "workloads": rows,
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(encoded)
    else:
        args.output.write_text(encoded, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
