#!/usr/bin/env python3
"""Generate synthetic usage histories and time common SQLite query paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from codex_usage_tracker.context import load_call_context  # noqa: E402
from codex_usage_tracker.dashboard import dashboard_payload  # noqa: E402
from codex_usage_tracker.models import UsageEvent  # noqa: E402
from codex_usage_tracker.parser import PARSER_ADAPTER_VERSION  # noqa: E402
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
    refresh_usage_event_links,
    refresh_usage_index,
    upsert_usage_events,
)

DEFAULT_ROW_COUNTS = (10_000, 100_000, 500_000)
SYNTHETIC_THREAD_NAMES = (
    "Codex Usage Tracker Development",
    "BugsInPy Solve Campaign",
    "Algebra Steps Visual Model",
    "Dashboard Performance Audit",
    "Release Readiness Checklist",
    "Plugin Prompt UX Polish",
    "Thread Cost Leaderboard",
    "Context Drilldown Diagnostics",
    "Project Alias Cleanup",
    "Pricing Coverage Review",
    "Allowance Settings Calibration",
    "CSV Export Validation",
    "MCP Skill Smoke Test",
    "Parser Drift Investigation",
    "Subagent Usage Review",
    "Auto Review Cost Spike",
    "Synthetic Fixture Builder",
    "Long Chat Cache Study",
    "Documentation Screenshot Refresh",
    "Dashboard Mobile QA",
)
BENCHMARK_THRESHOLDS: dict[str, dict[str, float]] = {
    "populate_seconds": {"base_seconds": 1.0, "per_10k_seconds": 1.85},
    "active_dashboard_query_seconds": {"base_seconds": 0.25, "per_10k_seconds": 0.05},
    "all_history_dashboard_query_seconds": {"base_seconds": 0.25, "per_10k_seconds": 0.05},
    "since_until_query_seconds": {"base_seconds": 0.25, "per_10k_seconds": 0.05},
    "filtered_query_seconds": {"base_seconds": 0.25, "per_10k_seconds": 0.05},
    "filtered_count_seconds": {"base_seconds": 0.25, "per_10k_seconds": 0.04},
    "dashboard_payload_active_seconds": {"base_seconds": 0.75, "per_10k_seconds": 0.20},
    "thread_summary_seconds": {"base_seconds": 0.75, "per_10k_seconds": 0.12},
    "recommendations_report_seconds": {"base_seconds": 1.0, "per_10k_seconds": 1.05},
    "pricing_coverage_seconds": {"base_seconds": 0.50, "per_10k_seconds": 0.06},
    "project_summary_seconds": {"base_seconds": 1.0, "per_10k_seconds": 0.45},
    "dashboard_payload_with_source_logs_seconds": {
        "base_seconds": 0.75,
        "per_10k_seconds": 0.20,
    },
    "context_load_early_line_seconds": {"base_seconds": 0.50, "per_10k_seconds": 0.08},
    "context_load_middle_line_seconds": {"base_seconds": 0.75, "per_10k_seconds": 0.12},
    "context_load_late_line_seconds": {"base_seconds": 1.00, "per_10k_seconds": 0.16},
    "source_refresh_backfill_seconds": {"base_seconds": 1.00, "per_10k_seconds": 0.75},
}
T = TypeVar("T")


@dataclass(frozen=True)
class SourceLogRecord:
    source_file: Path
    line_number: int
    source_byte_start: int
    source_byte_end: int
    turn_start_line: int
    turn_start_byte: int


@dataclass(frozen=True)
class SourceLogBundle:
    records: list[SourceLogRecord]
    paths: frozenset[Path]
    line_counts: dict[Path, int]
    bytes_written: int


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
    parser.add_argument(
        "--with-source-logs",
        action="store_true",
        help=(
            "Generate synthetic JSONL source files and benchmark explicit context loading. "
            "Generated content is synthetic only and is never copied from real Codex logs."
        ),
    )
    parser.add_argument(
        "--refresh-workers",
        type=int,
        help=(
            "Maximum parser workers for the optional synthetic source refresh benchmark. "
            "Only used with --with-source-logs."
        ),
    )
    args = parser.parse_args()

    if any(count <= 0 for count in args.rows):
        parser.error("--rows values must be positive")
    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")
    if args.threshold_scale <= 0:
        parser.error("--threshold-scale must be positive")
    if args.refresh_workers is not None and args.refresh_workers <= 0:
        parser.error("--refresh-workers must be positive")

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
                with_source_logs=args.with_source_logs,
                refresh_workers=args.refresh_workers,
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
    with_source_logs: bool = False,
    refresh_workers: int | None = None,
) -> dict[str, Any]:
    db_path = db_dir / f"synthetic-{row_count}.sqlite3"
    if db_path.exists():
        db_path.unlink()
    config = _write_benchmark_config(db_dir)
    source_bundle = (
        _write_synthetic_source_logs(db_dir / f"source-logs-{row_count}", row_count)
        if with_source_logs
        else None
    )
    source_refresh_metrics = (
        _benchmark_source_refresh(
            db_dir=db_dir,
            source_bundle=source_bundle,
            row_count=row_count,
            refresh_workers=refresh_workers,
        )
        if source_bundle
        else {}
    )
    populate_start = time.perf_counter()
    for start in range(0, row_count, batch_size):
        end = min(start + batch_size, row_count)
        upsert_usage_events(
            _synthetic_events(
                start,
                end,
                source_records=source_bundle.records if source_bundle else None,
            ),
            db_path=db_path,
            refresh_links=False,
        )
    refresh_usage_event_links(db_path=db_path)
    if source_bundle:
        _insert_synthetic_source_metadata(db_path=db_path, source_bundle=source_bundle)
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
    def payload_action() -> dict[str, Any]:
        return dashboard_payload(
            db_path=db_path,
            limit=500,
            pricing_path=config["pricing_path"],
            allowance_path=config["allowance_path"],
            thresholds_path=config["thresholds_path"],
            projects_path=config["projects_path"],
            include_archived=False,
        )

    if source_bundle:
        active_payload, dashboard_payload_active_seconds = _time_call(
            lambda: _run_without_source_log_reads(source_bundle.paths, payload_action)
        )
    else:
        active_payload, dashboard_payload_active_seconds = _time_call(payload_action)
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
    context_metrics: dict[str, Any] = {}
    if source_bundle:
        timings["dashboard_payload_with_source_logs_seconds"] = (
            dashboard_payload_active_seconds
        )
        timings.update(source_refresh_metrics.get("timings", {}))
        context_metrics = _benchmark_context_loads(
            db_path=db_path,
            row_count=row_count,
        )
        timings.update(context_metrics["timings"])
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
        "source_logs_generated": len(source_bundle.paths) if source_bundle else 0,
        "source_log_bytes": source_bundle.bytes_written if source_bundle else 0,
        "source_refresh": source_refresh_metrics.get("refresh"),
        "context_loads": context_metrics.get("loads", {}),
        "context_load_seconds": context_metrics.get("context_load_seconds"),
        "context_payload_json_bytes": context_metrics.get("context_payload_json_bytes"),
        "source_scan_ms": context_metrics.get("source_scan_ms"),
        "serialized_estimate_ms": context_metrics.get("serialized_estimate_ms"),
        "threshold_status": "fail" if threshold_failures else "pass",
        "thresholds": threshold_results,
        "threshold_failures": threshold_failures,
        "query_plan": plan,
    }


def _benchmark_source_refresh(
    *,
    db_dir: Path,
    source_bundle: SourceLogBundle,
    row_count: int,
    refresh_workers: int | None,
) -> dict[str, Any]:
    refresh_db_path = db_dir / f"synthetic-{row_count}-source-refresh.sqlite3"
    if refresh_db_path.exists():
        refresh_db_path.unlink()
    result, seconds = _time_call(
        lambda: refresh_usage_index(
            codex_home=_synthetic_codex_home(source_bundle),
            db_path=refresh_db_path,
            include_archived=True,
            refresh_workers=refresh_workers,
        )
    )
    return {
        "timings": {"source_refresh_backfill_seconds": seconds},
        "refresh": {
            "db_path": str(refresh_db_path),
            "seconds": seconds,
            "scanned_files": result.scanned_files,
            "parsed_events": result.parsed_events,
            "inserted_or_updated_events": result.inserted_or_updated_events,
            "changed_source_files": result.changed_source_files,
            "append_source_files": result.append_source_files,
            "full_reparse_source_files": result.full_reparse_source_files,
            "affected_threads": result.affected_threads,
            "refresh_workers": result.refresh_workers,
            "parallel_parse_files": result.parallel_parse_files,
        },
    }


def _synthetic_codex_home(source_bundle: SourceLogBundle) -> Path:
    if not source_bundle.paths:
        raise ValueError("source_bundle must include at least one source log path")
    sample = next(iter(source_bundle.paths))
    for parent in sample.parents:
        if parent.name in {"sessions", "archived_sessions"}:
            return parent.parent
    raise ValueError(f"Could not identify synthetic Codex home for {sample}")


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


def _run_without_source_log_reads(
    source_paths: frozenset[Path],
    action: Callable[[], T],
) -> T:
    with _fail_on_source_log_open(source_paths):
        return action()


@contextmanager
def _fail_on_source_log_open(source_paths: frozenset[Path]) -> Iterator[None]:
    blocked = {path.resolve() for path in source_paths}
    original_open = Path.open

    def guarded_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        try:
            resolved = self.resolve()
        except OSError:
            resolved = self
        if resolved in blocked:
            raise RuntimeError(f"dashboard_payload opened synthetic source log: {self}")
        return original_open(self, *args, **kwargs)

    Path.open = guarded_open  # type: ignore[method-assign]
    try:
        yield
    finally:
        Path.open = original_open  # type: ignore[method-assign]


def _benchmark_context_loads(
    *,
    db_path: Path,
    row_count: int,
) -> dict[str, Any]:
    targets = {
        "early": 0,
        "middle": row_count // 2,
        "late": row_count - 1,
    }
    timings: dict[str, float] = {}
    loads: dict[str, dict[str, Any]] = {}
    context_load_seconds: float | None = None
    context_payload_json_bytes: int | None = None
    source_scan_ms: float | None = None
    serialized_estimate_ms: float | None = None
    for label, index in targets.items():
        record_id = f"record-{index:08d}"
        payload, elapsed = _time_call(
            lambda record_id=record_id: load_call_context(
                record_id=record_id,
                db_path=db_path,
                max_chars=0,
                max_entries=0,
                include_tool_output=True,
                include_compaction_history=False,
                diagnostics=True,
            )
        )
        timing_name = f"context_load_{label}_line_seconds"
        timings[timing_name] = elapsed
        diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
        loads[label] = {
            "record_id": record_id,
            "seconds": elapsed,
            "entries_returned": len(payload.get("entries") or []),
            "visible_char_count": payload.get("visible_char_count"),
            "visible_token_estimate": payload.get("visible_token_estimate"),
            "seek_used": diagnostics.get("seek_used"),
            "seek_fallback_reason": diagnostics.get("seek_fallback_reason"),
            "bytes_scanned": diagnostics.get("bytes_scanned"),
            "lines_scanned": diagnostics.get("lines_scanned"),
            "context_payload_json_bytes": diagnostics.get("json_bytes"),
            "source_scan_ms": diagnostics.get("source_scan_ms"),
            "serialized_estimate_ms": diagnostics.get("serialized_estimate_ms"),
        }
        if label == "middle":
            context_load_seconds = elapsed
            context_payload_json_bytes = _optional_int(diagnostics.get("json_bytes"))
            source_scan_ms = _optional_float(diagnostics.get("source_scan_ms"))
            serialized_estimate_ms = _optional_float(diagnostics.get("serialized_estimate_ms"))
    scan_payload, scan_elapsed = _time_call(
        lambda: load_call_context(
            record_id=f"record-{row_count - 1:08d}",
            db_path=db_path,
            max_chars=0,
            max_entries=0,
            include_tool_output=True,
            include_compaction_history=True,
            diagnostics=True,
        )
    )
    scan_diagnostics = (
        scan_payload.get("diagnostics")
        if isinstance(scan_payload.get("diagnostics"), dict)
        else {}
    )
    loads["late_scan_fallback"] = {
        "record_id": f"record-{row_count - 1:08d}",
        "seconds": scan_elapsed,
        "seek_used": scan_diagnostics.get("seek_used"),
        "seek_fallback_reason": scan_diagnostics.get("seek_fallback_reason"),
        "bytes_scanned": scan_diagnostics.get("bytes_scanned"),
        "lines_scanned": scan_diagnostics.get("lines_scanned"),
    }
    return {
        "timings": timings,
        "loads": loads,
        "context_load_seconds": context_load_seconds,
        "context_payload_json_bytes": context_payload_json_bytes,
        "source_scan_ms": source_scan_ms,
        "serialized_estimate_ms": serialized_estimate_ms,
    }


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


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _write_synthetic_source_logs(source_dir: Path, row_count: int) -> SourceLogBundle:
    events_per_file = 500
    records: list[SourceLogRecord | None] = [None] * row_count
    lines_by_path: dict[Path, list[str]] = {}
    byte_offsets_by_path: dict[Path, int] = {}
    for index in range(row_count):
        path = _synthetic_source_file(source_dir, index, events_per_file=events_per_file)
        lines = lines_by_path.setdefault(path, [])
        byte_offsets_by_path.setdefault(path, 0)
        if not lines:
            session_line = _jsonl_line("session_meta", {"id": f"session-{index % 2500:04d}"})
            lines.append(session_line)
            byte_offsets_by_path[path] += len(session_line.encode("utf-8"))
        turn_id = f"turn-{index:08d}"
        turn_start_line = len(lines) + 1
        turn_start_byte = byte_offsets_by_path[path]
        token_line_number = 0
        token_byte_start = 0
        token_byte_end = 0
        for envelope in _synthetic_source_envelopes(index, turn_id):
            line = json.dumps(envelope, separators=(",", ":"), sort_keys=True) + "\n"
            line_byte_start = byte_offsets_by_path[path]
            line_byte_end = line_byte_start + len(line.encode("utf-8"))
            lines.append(line)
            byte_offsets_by_path[path] = line_byte_end
            payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
            if envelope.get("type") == "event_msg" and payload.get("type") == "token_count":
                token_line_number = len(lines)
                token_byte_start = line_byte_start
                token_byte_end = line_byte_end
        records[index] = SourceLogRecord(
            source_file=path,
            line_number=token_line_number,
            source_byte_start=token_byte_start,
            source_byte_end=token_byte_end,
            turn_start_line=turn_start_line,
            turn_start_byte=turn_start_byte,
        )

    bytes_written = 0
    for path, lines in lines_by_path.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(lines)
        path.write_text(payload, encoding="utf-8")
        bytes_written += len(payload.encode("utf-8"))

    return SourceLogBundle(
        records=[record for record in records if record is not None],
        paths=frozenset(lines_by_path),
        line_counts={path: len(lines) for path, lines in lines_by_path.items()},
        bytes_written=bytes_written,
    )


def _insert_synthetic_source_metadata(
    *,
    db_path: Path,
    source_bundle: SourceLogBundle,
) -> None:
    rows: list[tuple[object, ...]] = []
    for path in sorted(source_bundle.paths):
        stat = path.stat()
        source_hash = hashlib.sha256(str(path).encode("utf-8")).hexdigest()
        rows.append(
            (
                source_hash,
                str(path),
                source_hash,
                1 if "/archived_sessions/" in str(path).replace("\\", "/") else 0,
                int(stat.st_size),
                int(stat.st_mtime_ns),
                int(source_bundle.line_counts.get(path, 0)),
                int(stat.st_size),
                None,
                None,
                PARSER_ADAPTER_VERSION,
                "{}",
                "{}",
                "2026-05-01T00:00:00+00:00",
            )
        )
    with connect(db_path) as conn:
        init_db(conn)
        conn.executemany(
            """
            INSERT INTO source_files (
                source_file_id, source_file, source_file_hash, is_archived,
                size_bytes, mtime_ns, parsed_until_line, parsed_until_byte,
                latest_record_id, latest_event_timestamp, parser_adapter,
                parser_diagnostics_json, parser_state_json, last_indexed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_file_id) DO UPDATE SET
                source_file = excluded.source_file,
                source_file_hash = excluded.source_file_hash,
                is_archived = excluded.is_archived,
                size_bytes = excluded.size_bytes,
                mtime_ns = excluded.mtime_ns,
                parsed_until_line = excluded.parsed_until_line,
                parsed_until_byte = excluded.parsed_until_byte,
                parser_adapter = excluded.parser_adapter,
                parser_diagnostics_json = excluded.parser_diagnostics_json,
                parser_state_json = excluded.parser_state_json,
                last_indexed_at = excluded.last_indexed_at
            """,
            rows,
        )


def _synthetic_source_file(
    source_dir: Path,
    index: int,
    *,
    events_per_file: int,
) -> Path:
    scope = "archived_sessions" if index % 11 == 0 else "sessions"
    return source_dir / scope / f"rollout-synthetic-{index // events_per_file:05d}.jsonl"


def _synthetic_source_envelopes(index: int, turn_id: str) -> list[dict[str, Any]]:
    metrics = _synthetic_token_metrics(index)
    day = (index % 28) + 1
    timestamp = f"2026-05-{day:02d}T12:{index % 60:02d}:00Z"
    thread_name = _synthetic_thread_name(index)
    envelopes = [
        _envelope(
            "turn_context",
            timestamp,
            {
                "turn_id": turn_id,
                "model": metrics["model"],
                "effort": metrics["effort"],
                "cwd": f"/tmp/project-{index % 50}",
                "current_date": f"2026-05-{day:02d}",
                "timezone": "UTC",
                "summary": f"Synthetic benchmark turn {index}",
            },
        ),
        _envelope(
            "response_item",
            timestamp,
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Synthetic user request for benchmark coverage. "
                            f"Thread {thread_name}, call {index}."
                        ),
                    }
                ],
            },
        ),
        _envelope(
            "response_item",
            timestamp,
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": (
                            "Synthetic assistant progress update for benchmark coverage. "
                            "No real transcript content is used."
                        ),
                    }
                ],
            },
        ),
        _envelope(
            "response_item",
            timestamp,
            {
                "type": "function_call_output",
                "name": "exec_command",
                "output": (
                    "Synthetic tool output placeholder. "
                    "This is deterministic benchmark text, not a real command result."
                ),
            },
        ),
    ]
    if index % 37 == 0:
        envelopes.append(
            _envelope(
                "compacted",
                timestamp,
                {
                    "message": "Synthetic compaction marker.",
                    "replacement_history": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "Synthetic compacted replacement summary.",
                                }
                            ],
                        }
                    ],
                },
            )
        )
    envelopes.append(_synthetic_token_envelope(index, timestamp, metrics))
    return envelopes


def _synthetic_token_envelope(
    index: int,
    timestamp: str,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    cumulative_input_tokens = metrics["input_tokens"] + index * 5
    cumulative_cached_input_tokens = metrics["cached_input_tokens"] + index
    cumulative_output_tokens = metrics["output_tokens"] + index
    cumulative_reasoning_output_tokens = metrics["reasoning_tokens"] + index // 2
    cumulative_total_tokens = metrics["total_tokens"] + index * 10
    return _envelope(
        "event_msg",
        timestamp,
        {
            "type": "token_count",
            "info": {
                "last_token_usage": {
                    "input_tokens": metrics["input_tokens"],
                    "cached_input_tokens": metrics["cached_input_tokens"],
                    "output_tokens": metrics["output_tokens"],
                    "reasoning_output_tokens": metrics["reasoning_tokens"],
                    "total_tokens": metrics["total_tokens"],
                },
                "total_token_usage": {
                    "input_tokens": cumulative_input_tokens,
                    "cached_input_tokens": cumulative_cached_input_tokens,
                    "output_tokens": cumulative_output_tokens,
                    "reasoning_output_tokens": cumulative_reasoning_output_tokens,
                    "total_tokens": cumulative_total_tokens,
                },
                "model_context_window": 200_000,
            },
        },
    )


def _jsonl_line(entry_type: str, payload: dict[str, Any]) -> str:
    return json.dumps(_envelope(entry_type, "2026-05-01T00:00:00Z", payload)) + "\n"


def _envelope(entry_type: str, timestamp: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "type": entry_type,
        "payload": payload,
    }


def _synthetic_token_metrics(index: int) -> dict[str, Any]:
    is_review = index % 17 == 0
    model = "codex-auto-review" if is_review else "gpt-5.5"
    effort = "high" if index % 3 == 0 else "low"
    input_tokens = 8_000 + (index % 9_000)
    cached_input_tokens = index % 2_500
    output_tokens = 80 + (index % 450)
    reasoning_tokens = 10 + (index % 120)
    return {
        "model": model,
        "effort": effort,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def _synthetic_events(
    start: int,
    end: int,
    *,
    source_records: list[SourceLogRecord] | None = None,
) -> Iterable[UsageEvent]:
    for index in range(start, end):
        day = (index % 28) + 1
        is_review = index % 17 == 0
        is_subagent = index % 13 == 0
        metrics = _synthetic_token_metrics(index)
        session_id = f"session-{index % 2500:04d}"
        source_record = source_records[index] if source_records is not None else None
        source_file = (
            str(source_record.source_file)
            if source_record is not None
            else (
                f"/tmp/synthetic/archived_sessions/{index % 2500}.jsonl"
                if index % 11 == 0
                else f"/tmp/synthetic/{index % 2500}.jsonl"
            )
        )
        thread_name = _synthetic_thread_name(index)
        call_initiator = "codex" if is_subagent or is_review else "user"
        call_reason = "thread_source" if is_subagent or is_review else "user_message"
        yield UsageEvent(
            record_id=f"record-{index:08d}",
            session_id=session_id,
            thread_name=thread_name,
            session_updated_at=f"2026-05-{day:02d}T23:00:00Z",
            event_timestamp=f"2026-05-{day:02d}T12:{index % 60:02d}:00Z",
            source_file=source_file,
            line_number=source_record.line_number if source_record is not None else index + 1,
            source_byte_start=(
                source_record.source_byte_start if source_record is not None else None
            ),
            source_byte_end=source_record.source_byte_end if source_record is not None else None,
            turn_start_line=source_record.turn_start_line if source_record is not None else None,
            turn_start_byte=source_record.turn_start_byte if source_record is not None else None,
            turn_id=f"turn-{index:08d}",
            turn_timestamp=f"2026-05-{day:02d}T12:{index % 60:02d}:00Z",
            cwd=f"/tmp/project-{index % 50}",
            model=metrics["model"],
            effort=metrics["effort"],
            current_date=f"2026-05-{day:02d}",
            timezone="UTC",
            call_initiator=call_initiator,
            call_initiator_reason=call_reason,
            call_initiator_confidence="medium" if call_initiator == "codex" else "high",
            is_archived=1 if "/archived_sessions/" in source_file else 0,
            thread_key=f"thread:{thread_name}",
            thread_call_index=None,
            previous_record_id=None,
            next_record_id=None,
            thread_source="subagent" if is_subagent or is_review else "user",
            subagent_type="guardian" if is_review else "thread_spawn" if is_subagent else None,
            agent_role="reviewer" if is_review else "worker" if is_subagent else None,
            agent_nickname=None,
            parent_session_id=f"session-{(index - 1) % 2500:04d}" if is_subagent or is_review else None,
            parent_thread_name=_synthetic_thread_name(index - 1) if is_subagent or is_review else None,
            parent_session_updated_at=f"2026-05-{day:02d}T22:00:00Z" if is_subagent or is_review else None,
            model_context_window=200_000,
            input_tokens=metrics["input_tokens"],
            cached_input_tokens=metrics["cached_input_tokens"],
            output_tokens=metrics["output_tokens"],
            reasoning_output_tokens=metrics["reasoning_tokens"],
            total_tokens=metrics["total_tokens"],
            cumulative_input_tokens=metrics["input_tokens"] + index * 5,
            cumulative_cached_input_tokens=metrics["cached_input_tokens"] + index,
            cumulative_output_tokens=metrics["output_tokens"] + index,
            cumulative_reasoning_output_tokens=metrics["reasoning_tokens"] + index // 2,
            cumulative_total_tokens=metrics["total_tokens"] + index * 10,
        )


def _synthetic_thread_name(index: int) -> str:
    return SYNTHETIC_THREAD_NAMES[index % len(SYNTHETIC_THREAD_NAMES)]


if __name__ == "__main__":
    raise SystemExit(main())
