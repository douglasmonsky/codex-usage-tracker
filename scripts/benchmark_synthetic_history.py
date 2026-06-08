#!/usr/bin/env python3
"""Generate synthetic usage histories and time common SQLite query paths."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from codex_usage_tracker.models import UsageEvent  # noqa: E402
from codex_usage_tracker.store import (  # noqa: E402
    connect,
    init_db,
    query_dashboard_event_count,
    query_dashboard_events,
    upsert_usage_events,
)

DEFAULT_ROW_COUNTS = (10_000, 100_000, 500_000)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rows",
        type=int,
        nargs="+",
        default=list(DEFAULT_ROW_COUNTS),
        help="Synthetic row counts to benchmark. Defaults to 10000 100000 500000.",
    )
    parser.add_argument("--batch-size", type=int, default=5_000)
    parser.add_argument("--db-dir", type=Path)
    parser.add_argument("--keep-dbs", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    if any(count <= 0 for count in args.rows):
        parser.error("--rows values must be positive")
    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")

    temp_dir: Path | None = None
    if args.db_dir:
        db_dir = args.db_dir.expanduser()
        db_dir.mkdir(parents=True, exist_ok=True)
    else:
        temp_dir = Path(tempfile.mkdtemp(prefix="codex-usage-benchmark-"))
        db_dir = temp_dir

    try:
        results = [
            benchmark_size(row_count, db_dir=db_dir, batch_size=args.batch_size)
            for row_count in args.rows
        ]
        if args.as_json:
            print(json.dumps({"benchmarks": results}, indent=2))
        else:
            for result in results:
                print(
                    f"{result['rows']:,} rows: populate {result['populate_seconds']:.3f}s, "
                    f"filtered query {result['filtered_query_seconds']:.4f}s "
                    f"({result['filtered_rows']} rows), count {result['count_seconds']:.4f}s"
                )
        return 0
    finally:
        if temp_dir and not args.keep_dbs:
            shutil.rmtree(temp_dir, ignore_errors=True)


def benchmark_size(row_count: int, *, db_dir: Path, batch_size: int) -> dict[str, Any]:
    db_path = db_dir / f"synthetic-{row_count}.sqlite3"
    if db_path.exists():
        db_path.unlink()
    populate_start = time.perf_counter()
    for start in range(0, row_count, batch_size):
        end = min(start + batch_size, row_count)
        upsert_usage_events(_synthetic_events(start, end), db_path=db_path)
    populate_seconds = time.perf_counter() - populate_start

    query_start = time.perf_counter()
    filtered = query_dashboard_events(
        db_path=db_path,
        limit=50,
        model="gpt-5.5",
        effort="high",
        min_tokens=9_000,
    )
    filtered_seconds = time.perf_counter() - query_start

    count_start = time.perf_counter()
    filtered_count = query_dashboard_event_count(
        db_path=db_path,
        model="gpt-5.5",
        effort="high",
        min_tokens=9_000,
    )
    count_seconds = time.perf_counter() - count_start

    with connect(db_path) as conn:
        init_db(conn)
        plan = " | ".join(
            str(row["detail"])
            for row in conn.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT *
                FROM usage_events
                WHERE model = ? AND effort = ? AND total_tokens >= ?
                """,
                ("gpt-5.5", "high", 9_000),
            )
        )

    return {
        "rows": row_count,
        "db_path": str(db_path),
        "populate_seconds": round(populate_seconds, 6),
        "filtered_query_seconds": round(filtered_seconds, 6),
        "count_seconds": round(count_seconds, 6),
        "filtered_rows": len(filtered),
        "filtered_count": filtered_count,
        "query_plan": plan,
    }


def _synthetic_events(start: int, end: int) -> Iterable[UsageEvent]:
    for index in range(start, end):
        day = (index % 28) + 1
        is_review = index % 17 == 0
        is_subagent = index % 13 == 0
        model = "codex-auto-review" if is_review else "gpt-5.5"
        effort = "high" if index % 3 == 0 else "low"
        input_tokens = 8_000 + (index % 9_000)
        cached_input_tokens = index % 2_500
        output_tokens = 80 + (index % 450)
        reasoning_tokens = 10 + (index % 120)
        total_tokens = input_tokens + output_tokens
        session_id = f"session-{index % 2500:04d}"
        yield UsageEvent(
            record_id=f"record-{index:08d}",
            session_id=session_id,
            thread_name=f"Thread {index % 500}",
            session_updated_at=f"2026-05-{day:02d}T23:00:00Z",
            event_timestamp=f"2026-05-{day:02d}T12:{index % 60:02d}:00Z",
            source_file=f"/tmp/synthetic/{index % 2500}.jsonl",
            line_number=index + 1,
            source_provider="openai",
            source_app="codex",
            source_format="codex-jsonl-v1",
            provider_request_id=None,
            turn_id=f"turn-{index:08d}",
            turn_timestamp=f"2026-05-{day:02d}T12:{index % 60:02d}:00Z",
            cwd=f"/tmp/project-{index % 50}",
            model=model,
            effort=effort,
            current_date=f"2026-05-{day:02d}",
            timezone="UTC",
            thread_source="subagent" if is_subagent or is_review else "user",
            subagent_type="guardian" if is_review else "thread_spawn" if is_subagent else None,
            agent_role="reviewer" if is_review else "worker" if is_subagent else None,
            agent_nickname=None,
            parent_session_id=f"session-{(index - 1) % 2500:04d}" if is_subagent or is_review else None,
            parent_thread_name=f"Thread {(index - 1) % 500}" if is_subagent or is_review else None,
            parent_session_updated_at=f"2026-05-{day:02d}T22:00:00Z" if is_subagent or is_review else None,
            model_context_window=200_000,
            cache_creation_input_tokens=0,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            reasoning_output_tokens=reasoning_tokens,
            total_tokens=total_tokens,
            cumulative_input_tokens=input_tokens + index * 5,
            cumulative_cached_input_tokens=cached_input_tokens + index,
            cumulative_output_tokens=output_tokens + index,
            cumulative_reasoning_output_tokens=reasoning_tokens + index // 2,
            cumulative_total_tokens=total_tokens + index * 10,
        )


if __name__ == "__main__":
    raise SystemExit(main())
