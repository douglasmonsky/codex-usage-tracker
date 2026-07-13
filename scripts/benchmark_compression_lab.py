#!/usr/bin/env python3
"""Benchmark Compression Lab cold and warm builds with synthetic data only."""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import shutil
import sqlite3
import subprocess
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

from benchmark_synthetic_history import _synthetic_events  # noqa: E402

from codex_usage_tracker.compression.models import CompressionScope  # noqa: E402
from codex_usage_tracker.compression.run_builder import build_compression_run  # noqa: E402
from codex_usage_tracker.store.api import (  # noqa: E402
    refresh_usage_event_links,
    upsert_usage_events,
)
from codex_usage_tracker.store.compression_facts import (  # noqa: E402
    backfill_compression_detector_facts,
)
from codex_usage_tracker.store.connection import connect  # noqa: E402
from codex_usage_tracker.store.schema import init_db  # noqa: E402

DEFAULT_ROWS = 100_000
DEFAULT_MAX_COLD_SECONDS = 20.0
DEFAULT_MAX_EVIDENCE_DETECTOR_SECONDS = 3.53
_VOLATILE_PROFILE_KEYS = {
    "cache",
    "completed_at",
    "created_at",
    "duration_ms",
    "progress",
    "run_id",
    "started_at",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--batch-size", type=int, default=5_000)
    parser.add_argument("--db-dir", type=Path)
    parser.add_argument("--keep-db", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--enforce-thresholds", action="store_true")
    parser.add_argument("--max-cold-seconds", type=float, default=DEFAULT_MAX_COLD_SECONDS)
    parser.add_argument(
        "--max-evidence-detector-seconds",
        type=float,
        default=DEFAULT_MAX_EVIDENCE_DETECTOR_SECONDS,
    )
    parser.add_argument("--max-peak-rss-mb", type=float)
    parser.add_argument("--with-normalized-evidence", action="store_true")
    parser.add_argument("--run-db", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--prepare-facts-db", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    _validate_args(parser, args)

    if args.prepare_facts_db is not None:
        print(json.dumps(_prepare_facts(args.prepare_facts_db), separators=(",", ":")))
        return 0
    if args.run_db is not None:
        print(json.dumps(_run_builds(args.run_db), separators=(",", ":")))
        return 0

    temp_dir: Path | None = None
    if args.db_dir is None:
        temp_dir = Path(tempfile.mkdtemp(prefix="compression-lab-benchmark-"))
        db_dir = temp_dir
    else:
        db_dir = args.db_dir.expanduser()
        db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / f"compression-synthetic-{args.rows}.sqlite3"

    try:
        populate_seconds, normalized_evidence_rows = _populate_database(
            db_path,
            rows=args.rows,
            batch_size=args.batch_size,
            with_normalized_evidence=args.with_normalized_evidence,
        )
        run_payload = _run_in_child(db_path)
        failures = _threshold_failures(
            run_payload,
            max_cold_seconds=args.max_cold_seconds,
            max_evidence_detector_seconds=args.max_evidence_detector_seconds,
            max_peak_rss_mb=args.max_peak_rss_mb,
        )
        payload = {
            "schema_version": 1,
            "synthetic": True,
            "rows": args.rows,
            "batch_size": args.batch_size,
            "populate_seconds": round(populate_seconds, 6),
            "normalized_evidence": args.with_normalized_evidence,
            "normalized_evidence_rows": normalized_evidence_rows,
            "max_cold_seconds": args.max_cold_seconds,
            "max_evidence_detector_seconds": args.max_evidence_detector_seconds,
            "max_peak_rss_mb": args.max_peak_rss_mb,
            **run_payload,
            "threshold_status": "fail" if failures else "pass",
            "threshold_failures": failures,
        }
        _print_payload(payload, as_json=args.as_json)
        return 1 if args.enforce_thresholds and failures else 0
    finally:
        if temp_dir is not None and not args.keep_db:
            shutil.rmtree(temp_dir, ignore_errors=True)


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.rows <= 0:
        parser.error("--rows must be positive")
    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")
    if args.max_cold_seconds <= 0:
        parser.error("--max-cold-seconds must be positive")
    if args.max_evidence_detector_seconds <= 0:
        parser.error("--max-evidence-detector-seconds must be positive")
    if args.max_peak_rss_mb is not None and args.max_peak_rss_mb <= 0:
        parser.error("--max-peak-rss-mb must be positive")


def _populate_database(
    db_path: Path,
    *,
    rows: int,
    batch_size: int,
    with_normalized_evidence: bool,
) -> tuple[float, int]:
    if db_path.exists():
        db_path.unlink()
    started = time.perf_counter()
    for start in range(0, rows, batch_size):
        upsert_usage_events(
            _synthetic_events(start, min(start + batch_size, rows)),
            db_path=db_path,
            refresh_links=False,
        )
    refresh_usage_event_links(db_path=db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE usage_events
            SET input_tokens = 25000,
                cached_input_tokens = 0,
                output_tokens = 100,
                total_tokens = 25100,
                uncached_input_tokens = 25000,
                cache_ratio = 0,
                context_window_percent = 0.8
            WHERE rowid % 10 = 0
            """
        )
        normalized_evidence_rows = (
            _seed_normalized_evidence(conn) if with_normalized_evidence else 0
        )
        backfill_compression_detector_facts(conn)
        conn.commit()
    return time.perf_counter() - started, normalized_evidence_rows


def _seed_normalized_evidence(conn: sqlite3.Connection) -> int:
    conn.executescript(
        """
        INSERT INTO tool_calls (
            tool_call_key, record_id, turn_key, tool_name, status,
            output_size_bytes, parser_adapter, parser_version, parse_warnings_json
        )
        SELECT
            'benchmark-tool-' || record_id,
            record_id,
            turn_id,
            'exec_command',
            'completed',
            CASE WHEN line_number % 20 = 0 THEN 20000 ELSE 800 END,
            'synthetic-benchmark',
            '1',
            '[]'
        FROM usage_events;

        INSERT INTO command_runs (
            command_run_key, record_id, turn_key, command_root, command_label,
            exit_code, status, output_size_bytes, retry_group,
            parser_adapter, parser_version, parse_warnings_json
        )
        SELECT
            'benchmark-command-' || record_id,
            record_id,
            turn_id,
            CASE WHEN line_number % 10 = 0 THEN 'rg' ELSE 'echo' END,
            'synthetic benchmark command',
            0,
            'completed',
            400,
            CASE
                WHEN line_number % 10 = 0 THEN 'rg-' || (line_number % 4)
                ELSE NULL
            END,
            'synthetic-benchmark',
            '1',
            '[]'
        FROM usage_events;

        INSERT INTO file_events (
            file_event_key, record_id, turn_key, operation, path_hash,
            path_basename, path_extension, path_identity,
            parser_adapter, parser_version, parse_warnings_json
        )
        SELECT
            'benchmark-file-' || record_id,
            record_id,
            turn_id,
            CASE WHEN line_number % 5 = 0 THEN 'read' ELSE 'write' END,
            'path-' || (line_number % 7),
            'synthetic.py',
            '.py',
            'path:path-' || (line_number % 7),
            'synthetic-benchmark',
            '1',
            '[]'
        FROM usage_events;

        INSERT INTO content_fragments (
            fragment_id, record_id, turn_key, fragment_kind, role, safe_label,
            content_hash, content_size_bytes, fragment_text, includes_raw_fragment,
            created_at
        )
        SELECT
            'benchmark-fragment-a-' || record_id,
            record_id,
            turn_id,
            'tool_output',
            'tool',
            'synthetic output',
            'content-a-' || record_id,
            400,
            '',
            0,
            event_timestamp
        FROM usage_events;

        INSERT INTO content_fragments (
            fragment_id, record_id, turn_key, fragment_kind, role, safe_label,
            content_hash, content_size_bytes, fragment_text, includes_raw_fragment,
            created_at
        )
        SELECT
            'benchmark-fragment-b-' || record_id,
            record_id,
            turn_id,
            'assistant_message',
            'assistant',
            'synthetic response',
            'content-b-' || record_id,
            240,
            '',
            0,
            event_timestamp
        FROM usage_events;
        """
    )
    row = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM tool_calls)
          + (SELECT COUNT(*) FROM command_runs)
          + (SELECT COUNT(*) FROM file_events)
          + (SELECT COUNT(*) FROM content_fragments)
        """
    ).fetchone()
    return int(row[0]) if row is not None else 0


def _run_in_child(db_path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--run-db", str(db_path)],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "compression benchmark child failed\n"
            f"returncode={result.returncode}\n"
            f"stdout={result.stdout}\n"
            f"stderr={result.stderr}"
        )
    return json.loads(result.stdout)


def _run_builds(db_path: Path) -> dict[str, Any]:
    scope = CompressionScope(include_archived=True)
    started = time.perf_counter()
    stages: dict[str, float] = {}

    def record_progress(payload: dict[str, Any]) -> None:
        stage = payload.get("stage")
        if isinstance(stage, str):
            stages[stage] = round(time.perf_counter() - started, 6)

    cold_profile = build_compression_run(
        db_path,
        scope,
        force=True,
        progress_callback=record_progress,
    )
    cold_payload = {
        "total_seconds": round(time.perf_counter() - started, 6),
        "peak_rss_mb": round(_peak_rss_mb(), 3),
        "candidate_count": int(cold_profile.get("candidate_count") or 0),
        "candidate_fingerprint": _candidate_fingerprint(db_path),
        "profile_fingerprint": _profile_fingerprint(cold_profile),
        "stage_timings_seconds": stages,
    }

    warm_started = time.perf_counter()
    warm_profile = build_compression_run(db_path, scope)
    warm_payload = {
        "total_seconds": round(time.perf_counter() - warm_started, 6),
        "cache_mode": str((warm_profile.get("cache") or {}).get("mode") or "unknown"),
        "profile_fingerprint": _profile_fingerprint(warm_profile),
    }
    return {"cold_build": cold_payload, "warm_build": warm_payload}


def _prepare_facts(db_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    stage_started = started
    stage_timings: dict[str, float] = {}

    def record_stage(stage: str) -> None:
        nonlocal stage_started
        now = time.perf_counter()
        stage_timings[stage] = round(now - stage_started, 6)
        stage_started = now

    with connect(db_path) as conn:
        init_db(conn)
        record_stage("init")
        backfill_compression_detector_facts(conn, stage_callback=record_stage)
        record_count = int(
            conn.execute("SELECT COUNT(*) FROM compression_record_facts").fetchone()[0]
        )
        sequence_count = int(
            conn.execute("SELECT COUNT(*) FROM compression_sequence_facts").fetchone()[0]
        )
        conn.commit()
    return {
        "total_seconds": round(time.perf_counter() - started, 6),
        "record_count": record_count,
        "sequence_count": sequence_count,
        "stage_timings_seconds": stage_timings,
    }


def _candidate_fingerprint(db_path: Path) -> str:
    digest = hashlib.sha256()
    with connect(db_path) as conn:
        run_row = conn.execute(
            "SELECT run_id FROM compression_runs WHERE status = 'completed' "
            "ORDER BY completed_at DESC, run_id DESC LIMIT 1"
        ).fetchone()
        if run_row is None:
            raise RuntimeError("completed compression run was not persisted")
        run_id = str(run_row[0])
        candidate_rows = conn.execute(
            """
            SELECT candidate_id, family, pattern_key, rank, confidence_grade,
                   confidence_score, observation_count, observed_exposure_json,
                   gross_low, gross_likely, gross_high, adjusted_low, adjusted_likely,
                   adjusted_high, detector_version, estimator_version, estimator_tier,
                   warnings_json, overlaps_json, thread_keys_json, first_seen, last_seen
            FROM compression_candidates
            WHERE run_id = ?
            ORDER BY candidate_id
            """,
            (run_id,),
        )
        _update_digest(digest, candidate_rows)
        claim_rows = conn.execute(
            """
            SELECT r.candidate_id, r.record_id, r.component, r.exposure_tokens,
                   r.estimate_low, r.estimate_likely, r.estimate_high,
                   r.evidence_role, r.trace_handle_json
            FROM compression_candidate_records AS r
            JOIN compression_candidates AS c ON c.candidate_id = r.candidate_id
            WHERE c.run_id = ?
            ORDER BY r.candidate_id, r.record_id, r.component
            """,
            (run_id,),
        )
        _update_digest(digest, claim_rows)
    return digest.hexdigest()


def _update_digest(digest: Any, rows: Iterable[Any]) -> None:
    for row in rows:
        digest.update(json.dumps(tuple(row), separators=(",", ":")).encode())
        digest.update(b"\n")


def _profile_fingerprint(profile: dict[str, Any]) -> str:
    stable = _without_volatile_fields(profile)
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _without_volatile_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_volatile_fields(item)
            for key, item in value.items()
            if key not in _VOLATILE_PROFILE_KEYS and not key.startswith("_")
        }
    if isinstance(value, list):
        return [_without_volatile_fields(item) for item in value]
    return value


def _peak_rss_mb() -> float:
    peak = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024


def _threshold_failures(
    payload: dict[str, Any],
    *,
    max_cold_seconds: float,
    max_evidence_detector_seconds: float,
    max_peak_rss_mb: float | None,
) -> list[str]:
    failures = []
    elapsed = float(payload["cold_build"]["total_seconds"])
    if elapsed > max_cold_seconds:
        failures.append(f"cold_build.total_seconds {elapsed:.3f} exceeded {max_cold_seconds:.3f}")
    evidence_detector_seconds = float(payload["cold_build"]["stage_timings_seconds"]["detectors"])
    if evidence_detector_seconds > max_evidence_detector_seconds:
        failures.append(
            "cold_build.stage_timings_seconds.detectors "
            f"{evidence_detector_seconds:.3f} exceeded "
            f"{max_evidence_detector_seconds:.3f}"
        )
    peak_rss_mb = float(payload["cold_build"]["peak_rss_mb"])
    if max_peak_rss_mb is not None and peak_rss_mb > max_peak_rss_mb:
        failures.append(f"cold_build.peak_rss_mb {peak_rss_mb:.3f} exceeded {max_peak_rss_mb:.3f}")
    return failures


def _print_payload(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    cold = payload["cold_build"]
    warm = payload["warm_build"]
    print(
        f"{payload['rows']:,} synthetic calls: cold {cold['total_seconds']:.3f}s, "
        f"warm {warm['total_seconds']:.6f}s, peak RSS {cold['peak_rss_mb']:.1f} MiB, "
        f"candidates {cold['candidate_count']:,}, thresholds {payload['threshold_status']}"
    )
    for failure in payload["threshold_failures"]:
        print(f"  FAIL {failure}")


if __name__ == "__main__":
    raise SystemExit(main())
