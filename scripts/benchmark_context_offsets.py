"""Synthetic context-offset performance helpers."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from statistics import median
from typing import Any, Protocol, TypeVar

from codex_usage_tracker.context.api import load_call_context
from codex_usage_tracker.parser.state import ParserState
from codex_usage_tracker.store.api import connect, init_db
from codex_usage_tracker.store.sources import upsert_source_file_metadata

SYNTHETIC_CONTEXT_RATCHET_LINES = 100_000
T = TypeVar("T")


class SourceLogBundleLike(Protocol):
    @property
    def paths(self) -> frozenset[Path]: ...

    @property
    def line_counts(self) -> dict[Path, int]: ...


def record_synthetic_source_metadata(
    db_path: Path,
    source_bundle: SourceLogBundleLike,
) -> None:
    parsed_files = [
        (path, [], {}, ParserState(), source_bundle.line_counts[path])
        for path in sorted(source_bundle.paths)
    ]
    with connect(db_path) as conn:
        init_db(conn)
        upsert_source_file_metadata(conn, parsed_files=parsed_files)


def benchmark_context_loads(
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
                include_compaction_history=True,
                diagnostics=True,
            )
        )
        timing_name = f"context_load_{label}_line_seconds"
        timings[timing_name] = elapsed
        raw_diagnostics = payload.get("diagnostics")
        diagnostics: dict[str, Any] = raw_diagnostics if isinstance(raw_diagnostics, dict) else {}
        loads[label] = {
            "record_id": record_id,
            "seconds": elapsed,
            "entries_returned": len(payload.get("entries") or []),
            "visible_char_count": payload.get("visible_char_count"),
            "visible_token_estimate": payload.get("visible_token_estimate"),
            "context_payload_json_bytes": diagnostics.get("json_bytes"),
            "source_scan_ms": diagnostics.get("source_scan_ms"),
            "serialized_estimate_ms": diagnostics.get("serialized_estimate_ms"),
            "context_read_strategy": diagnostics.get("context_read_strategy"),
            "context_read_reason": diagnostics.get("context_read_reason"),
            "inspected_source_bytes": diagnostics.get("inspected_source_bytes"),
        }
        if label == "middle":
            context_load_seconds = elapsed
            context_payload_json_bytes = _optional_int(diagnostics.get("json_bytes"))
            source_scan_ms = _optional_float(diagnostics.get("source_scan_ms"))
            serialized_estimate_ms = _optional_float(diagnostics.get("serialized_estimate_ms"))
    offset_ratchet = _benchmark_context_offset_ratchet(
        db_path=db_path,
        record_id=f"record-{row_count - 1:08d}",
    )
    timings.update(offset_ratchet["timings"])
    return {
        "timings": timings,
        "loads": loads,
        "context_load_seconds": context_load_seconds,
        "context_payload_json_bytes": context_payload_json_bytes,
        "source_scan_ms": source_scan_ms,
        "serialized_estimate_ms": serialized_estimate_ms,
        "offset_ratchet": offset_ratchet["result"],
        "ratchet_failures": offset_ratchet["failures"],
    }


def _benchmark_context_offset_ratchet(
    *,
    db_path: Path,
    record_id: str,
    sample_count: int = 5,
) -> dict[str, Any]:
    def load() -> dict[str, Any]:
        return load_call_context(
            record_id=record_id,
            db_path=db_path,
            max_chars=0,
            max_entries=0,
            include_tool_output=True,
            include_compaction_history=True,
            diagnostics=True,
        )

    load()
    offset_samples = [_time_call(load) for _sample in range(sample_count)]
    offset_payload = offset_samples[-1][0]
    with connect(db_path) as conn:
        stored_offset = conn.execute(
            "SELECT source_byte_offset FROM usage_events WHERE record_id = ?",
            (record_id,),
        ).fetchone()[0]
        conn.execute(
            "UPDATE usage_events SET source_byte_offset = NULL WHERE record_id = ?",
            (record_id,),
        )
    try:
        load()
        sequential_samples = [_time_call(load) for _sample in range(sample_count)]
        sequential_payload = sequential_samples[-1][0]
    finally:
        with connect(db_path) as conn:
            conn.execute(
                "UPDATE usage_events SET source_byte_offset = ? WHERE record_id = ?",
                (stored_offset, record_id),
            )

    offset_seconds = median(sample[1] for sample in offset_samples)
    sequential_seconds = median(sample[1] for sample in sequential_samples)
    offset_diagnostics = offset_payload["diagnostics"]
    sequential_diagnostics = sequential_payload["diagnostics"]
    source_line_number = int(offset_diagnostics["source_line_number"])
    source_file_bytes = int(offset_diagnostics["source_file_bytes"])
    inspected_source_bytes = int(offset_diagnostics["inspected_source_bytes"])
    inspected_ratio = inspected_source_bytes / source_file_bytes if source_file_bytes else 1.0
    speedup = sequential_seconds / offset_seconds if offset_seconds else float("inf")
    comparable_offset = dict(offset_payload)
    comparable_offset.pop("diagnostics", None)
    comparable_sequential = dict(sequential_payload)
    comparable_sequential.pop("diagnostics", None)
    equivalent = comparable_offset == comparable_sequential
    applicable = source_line_number >= SYNTHETIC_CONTEXT_RATCHET_LINES
    failures: list[str] = []
    if applicable and inspected_ratio >= 0.05:
        failures.append(
            "context offset seek inspected "
            f"{inspected_ratio:.2%} of source bytes; expected less than 5%"
        )
    if applicable and speedup < 5.0:
        failures.append(f"context offset seek speedup {speedup:.2f}x was below required 5.00x")
    if applicable and not equivalent:
        failures.append("context offset and sequential payloads were not equivalent")
    result = {
        "status": (
            "pass" if applicable and not failures else "fail" if failures else "not_applicable"
        ),
        "sample_count": sample_count,
        "source_line_number": source_line_number,
        "source_file_bytes": source_file_bytes,
        "offset_inspected_source_bytes": inspected_source_bytes,
        "offset_inspected_ratio": round(inspected_ratio, 6),
        "offset_median_seconds": round(offset_seconds, 6),
        "sequential_median_seconds": round(sequential_seconds, 6),
        "speedup": round(speedup, 3),
        "payloads_equivalent": equivalent,
        "offset_strategy": offset_diagnostics.get("context_read_strategy"),
        "sequential_strategy": sequential_diagnostics.get("context_read_strategy"),
    }
    return {
        "timings": {
            "context_offset_seek_median_seconds": round(offset_seconds, 6),
            "context_sequential_fallback_median_seconds": round(
                sequential_seconds,
                6,
            ),
        },
        "result": result,
        "failures": failures,
    }


def _time_call(action: Callable[[], T]) -> tuple[T, float]:
    start = time.perf_counter()
    value = action()
    return value, round(time.perf_counter() - start, 6)


def _optional_int(value: object) -> int | None:
    if not isinstance(value, (str, int, float)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    if not isinstance(value, (str, int, float)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
