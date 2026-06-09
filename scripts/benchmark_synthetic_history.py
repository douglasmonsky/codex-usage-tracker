#!/usr/bin/env python3
"""Generate synthetic usage histories and time common SQLite query paths."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, TypeVar

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from codex_usage_tracker.dashboard import dashboard_payload  # noqa: E402
from codex_usage_tracker.models import UsageEvent  # noqa: E402
from codex_usage_tracker.reports import (  # noqa: E402
    build_pricing_coverage_report,
    build_recommendations_report,
    build_summary_report,
)
from codex_usage_tracker.store import (  # noqa: E402
    connect,
    init_db,
    query_dashboard_event_count,
    query_dashboard_events,
    upsert_usage_events,
)

DEFAULT_ROW_COUNTS = (10_000, 100_000, 500_000)
BENCHMARK_THRESHOLDS: dict[str, dict[str, float]] = {
    "populate_seconds": {"base_seconds": 1.0, "per_10k_seconds": 0.60},
    "active_dashboard_query_seconds": {"base_seconds": 0.25, "per_10k_seconds": 0.05},
    "all_history_dashboard_query_seconds": {"base_seconds": 0.25, "per_10k_seconds": 0.05},
    "since_until_query_seconds": {"base_seconds": 0.25, "per_10k_seconds": 0.05},
    "filtered_query_seconds": {"base_seconds": 0.25, "per_10k_seconds": 0.05},
    "filtered_count_seconds": {"base_seconds": 0.25, "per_10k_seconds": 0.04},
    "dashboard_payload_active_seconds": {"base_seconds": 0.75, "per_10k_seconds": 0.20},
    "thread_summary_seconds": {"base_seconds": 0.75, "per_10k_seconds": 0.12},
    "recommendations_report_seconds": {"base_seconds": 1.0, "per_10k_seconds": 0.65},
    "pricing_coverage_seconds": {"base_seconds": 0.50, "per_10k_seconds": 0.06},
    "project_summary_seconds": {"base_seconds": 1.0, "per_10k_seconds": 0.45},
}
T = TypeVar("T")


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
    parser.add_argument(
        "--enforce-thresholds",
        action="store_true",
        help="Exit nonzero when any benchmark timing exceeds its documented threshold.",
    )
    parser.add_argument(
        "--threshold-scale",
        type=float,
        default=1.0,
        help="Multiplier for timing thresholds on slower local machines. Defaults to 1.0.",
    )
    args = parser.parse_args()

    if any(count <= 0 for count in args.rows):
        parser.error("--rows values must be positive")
    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")
    if args.threshold_scale <= 0:
        parser.error("--threshold-scale must be positive")

    temp_dir: Path | None = None
    if args.db_dir:
        db_dir = args.db_dir.expanduser()
        db_dir.mkdir(parents=True, exist_ok=True)
    else:
        temp_dir = Path(tempfile.mkdtemp(prefix="codex-usage-benchmark-"))
        db_dir = temp_dir

    try:
        results = [
            benchmark_size(
                row_count,
                db_dir=db_dir,
                batch_size=args.batch_size,
                threshold_scale=args.threshold_scale,
            )
            for row_count in args.rows
        ]
        if args.as_json:
            print(
                json.dumps(
                    {
                        "threshold_scale": args.threshold_scale,
                        "thresholds": BENCHMARK_THRESHOLDS,
                        "benchmarks": results,
                    },
                    indent=2,
                )
            )
        else:
            for result in results:
                print(
                    f"{result['rows']:,} rows: populate {result['populate_seconds']:.3f}s, "
                    f"active query {result['active_dashboard_query_seconds']:.4f}s, "
                    f"all-history query {result['all_history_dashboard_query_seconds']:.4f}s, "
                    f"dashboard payload {result['dashboard_payload_active_seconds']:.4f}s, "
                    f"recommendations {result['recommendations_report_seconds']:.4f}s, "
                    f"thresholds {result['threshold_status']}"
                )
                for failure in result["threshold_failures"]:
                    print(f"  FAIL {failure}")
        return 1 if args.enforce_thresholds and any(
            result["threshold_failures"] for result in results
        ) else 0
    finally:
        if temp_dir and not args.keep_dbs:
            shutil.rmtree(temp_dir, ignore_errors=True)


def benchmark_size(
    row_count: int,
    *,
    db_dir: Path,
    batch_size: int,
    threshold_scale: float = 1.0,
) -> dict[str, Any]:
    db_path = db_dir / f"synthetic-{row_count}.sqlite3"
    if db_path.exists():
        db_path.unlink()
    config = _write_benchmark_config(db_dir)
    populate_start = time.perf_counter()
    for start in range(0, row_count, batch_size):
        end = min(start + batch_size, row_count)
        upsert_usage_events(_synthetic_events(start, end), db_path=db_path)
    populate_seconds = time.perf_counter() - populate_start

    active_rows, active_dashboard_query_seconds = _time_call(
        lambda: query_dashboard_events(db_path=db_path, limit=500, include_archived=False)
    )
    all_history_rows, all_history_dashboard_query_seconds = _time_call(
        lambda: query_dashboard_events(db_path=db_path, limit=500, include_archived=True)
    )
    since_until_rows, since_until_query_seconds = _time_call(
        lambda: query_dashboard_events(
            db_path=db_path,
            limit=500,
            since="2026-05-10",
            until="2026-05-20T23:59:59Z",
            include_archived=True,
        )
    )
    filtered, filtered_seconds = _time_call(
        lambda: query_dashboard_events(
            db_path=db_path,
            limit=50,
            model="gpt-5.5",
            effort="high",
            min_tokens=9_000,
        )
    )
    filtered_count, count_seconds = _time_call(
        lambda: query_dashboard_event_count(
            db_path=db_path,
            model="gpt-5.5",
            effort="high",
            min_tokens=9_000,
        )
    )
    active_payload, dashboard_payload_active_seconds = _time_call(
        lambda: dashboard_payload(
            db_path=db_path,
            limit=500,
            pricing_path=config["pricing_path"],
            allowance_path=config["allowance_path"],
            thresholds_path=config["thresholds_path"],
            projects_path=config["projects_path"],
            include_archived=False,
        )
    )
    thread_summary, thread_summary_seconds = _time_call(
        lambda: build_summary_report(
            db_path=db_path,
            pricing_path=config["pricing_path"],
            group_by="thread",
            limit=50,
            projects_path=config["projects_path"],
        )
    )
    recommendations, recommendations_report_seconds = _time_call(
        lambda: build_recommendations_report(
            db_path=db_path,
            pricing_path=config["pricing_path"],
            allowance_path=config["allowance_path"],
            projects_path=config["projects_path"],
            min_score=20,
            limit=50,
        )
    )
    pricing_coverage, pricing_coverage_seconds = _time_call(
        lambda: build_pricing_coverage_report(
            db_path=db_path,
            pricing_path=config["pricing_path"],
        )
    )
    project_summary, project_summary_seconds = _time_call(
        lambda: build_summary_report(
            db_path=db_path,
            pricing_path=config["pricing_path"],
            group_by="project",
            limit=50,
            projects_path=config["projects_path"],
        )
    )

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

    timings = {
        "populate_seconds": round(populate_seconds, 6),
        "active_dashboard_query_seconds": active_dashboard_query_seconds,
        "all_history_dashboard_query_seconds": all_history_dashboard_query_seconds,
        "since_until_query_seconds": since_until_query_seconds,
        "filtered_query_seconds": filtered_seconds,
        "filtered_count_seconds": count_seconds,
        "dashboard_payload_active_seconds": dashboard_payload_active_seconds,
        "thread_summary_seconds": thread_summary_seconds,
        "recommendations_report_seconds": recommendations_report_seconds,
        "pricing_coverage_seconds": pricing_coverage_seconds,
        "project_summary_seconds": project_summary_seconds,
    }
    threshold_results, threshold_failures = _evaluate_thresholds(
        timings,
        row_count=row_count,
        threshold_scale=threshold_scale,
    )
    return {
        "rows": row_count,
        "db_path": str(db_path),
        "timings": timings,
        "populate_seconds": timings["populate_seconds"],
        "active_dashboard_query_seconds": timings["active_dashboard_query_seconds"],
        "all_history_dashboard_query_seconds": timings["all_history_dashboard_query_seconds"],
        "since_until_query_seconds": timings["since_until_query_seconds"],
        "filtered_query_seconds": timings["filtered_query_seconds"],
        "count_seconds": timings["filtered_count_seconds"],
        "filtered_count_seconds": timings["filtered_count_seconds"],
        "dashboard_payload_active_seconds": timings["dashboard_payload_active_seconds"],
        "thread_summary_seconds": timings["thread_summary_seconds"],
        "recommendations_report_seconds": timings["recommendations_report_seconds"],
        "pricing_coverage_seconds": timings["pricing_coverage_seconds"],
        "project_summary_seconds": timings["project_summary_seconds"],
        "active_rows": len(active_rows),
        "all_history_rows": len(all_history_rows),
        "since_until_rows": len(since_until_rows),
        "filtered_rows": len(filtered),
        "filtered_count": filtered_count,
        "dashboard_payload_rows": active_payload["loaded_row_count"],
        "thread_summary_rows": len(thread_summary.rows),
        "recommendations_rows": recommendations.payload["row_count"],
        "pricing_coverage_rows": len(pricing_coverage.payload["rows"]),
        "project_summary_rows": len(project_summary.rows),
        "threshold_status": "fail" if threshold_failures else "pass",
        "thresholds": threshold_results,
        "threshold_failures": threshold_failures,
        "query_plan": plan,
    }


def _write_benchmark_config(db_dir: Path) -> dict[str, Path]:
    pricing_path = db_dir / "synthetic-pricing.json"
    allowance_path = db_dir / "synthetic-allowance.json"
    thresholds_path = db_dir / "synthetic-thresholds.json"
    projects_path = db_dir / "synthetic-projects.json"
    pricing_path.write_text(
        json.dumps(
            {
                "_source": {
                    "name": "Synthetic benchmark pricing",
                    "fetched_at": "2026-06-08T00:00:00Z",
                },
                "models": {
                    "gpt-5.5": {
                        "input_per_million": 2.0,
                        "cached_input_per_million": 0.5,
                        "output_per_million": 10.0,
                    },
                    "codex-auto-review": {
                        "input_per_million": 2.0,
                        "cached_input_per_million": 0.5,
                        "output_per_million": 10.0,
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    allowance_path.write_text(json.dumps({"windows": []}) + "\n", encoding="utf-8")
    thresholds_path.write_text(json.dumps({"low_cache_ratio": 0.30}) + "\n", encoding="utf-8")
    projects_path.write_text(
        json.dumps({"aliases": {}, "ignored_paths": [], "tags": {}}) + "\n",
        encoding="utf-8",
    )
    return {
        "pricing_path": pricing_path,
        "allowance_path": allowance_path,
        "thresholds_path": thresholds_path,
        "projects_path": projects_path,
    }


def _time_call(action: Callable[[], T]) -> tuple[T, float]:
    start = time.perf_counter()
    value = action()
    return value, round(time.perf_counter() - start, 6)


def _evaluate_thresholds(
    timings: dict[str, float],
    *,
    row_count: int,
    threshold_scale: float,
) -> tuple[dict[str, dict[str, float | str]], list[str]]:
    results: dict[str, dict[str, float | str]] = {}
    failures: list[str] = []
    for name, seconds in timings.items():
        threshold = BENCHMARK_THRESHOLDS.get(name)
        if threshold is None:
            continue
        limit = round(
            (
                threshold["base_seconds"]
                + threshold["per_10k_seconds"] * (row_count / 10_000)
            )
            * threshold_scale,
            6,
        )
        status = "pass" if seconds <= limit else "fail"
        results[name] = {
            "seconds": seconds,
            "limit_seconds": limit,
            "status": status,
        }
        if status == "fail":
            failures.append(f"{name} {seconds:.6f}s exceeded {limit:.6f}s")
    return results, failures


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
        source_file = (
            f"/tmp/synthetic/archived_sessions/{index % 2500}.jsonl"
            if index % 11 == 0
            else f"/tmp/synthetic/{index % 2500}.jsonl"
        )
        yield UsageEvent(
            record_id=f"record-{index:08d}",
            session_id=session_id,
            thread_name=f"Thread {index % 500}",
            session_updated_at=f"2026-05-{day:02d}T23:00:00Z",
            event_timestamp=f"2026-05-{day:02d}T12:{index % 60:02d}:00Z",
            source_file=source_file,
            line_number=index + 1,
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
