"""Synthetic large-history ingestion budgets."""

from __future__ import annotations

import json
import math
import sqlite3
import time
from pathlib import Path

import pytest

from codex_usage_tracker.kernel import writer
from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger
from codex_usage_tracker.kernel.operational import kernel_paths
from tests.kernel.test_ingest_pipeline import _token_line

_CALL_COUNT = 100_000
_ACTIVE_WRITER_P95_BUDGET_MS = 50.0
_INITIAL_WRITER_P95_BUDGET_MS = 2_000.0
_INITIAL_BUILD_TRANSACTION_BUDGET = 10


def test_100k_call_build_meets_bounded_writer_budget(tmp_path: Path) -> None:
    source = tmp_path / "sessions" / "rollout-large-synthetic.jsonl"
    source.parent.mkdir()
    source.write_text(
        '{"timestamp":"2026-01-01T00:00:00Z","type":"session_meta",'
        '"payload":{"id":"synthetic-large-session"}}\n'
        '{"timestamp":"2026-01-01T00:00:00Z","type":"turn_context",'
        '"payload":{"turn_id":"turn-1","model":"gpt-synthetic","effort":"low"}}\n'
        + "".join(
            _token_line(f"event-{index}", index % 100)
            for index in range(_CALL_COUNT)
        ),
        encoding="utf-8",
    )
    paths = kernel_paths(tmp_path / "cache")

    started = time.perf_counter()
    result = KernelIngestor(paths.analytical, paths.operational).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="performance-owner",
    )
    elapsed = time.perf_counter() - started

    ordered = sorted(result.writer_transaction_ms)
    p95 = ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]
    print(
        json.dumps(
            {
                "calls": result.inserted_calls,
                "elapsed_seconds": round(elapsed, 3),
                "writer_p95_ms": round(p95, 3),
                "writer_transactions": len(ordered),
            },
            sort_keys=True,
        )
    )
    assert result.inserted_calls == _CALL_COUNT
    assert len(ordered) <= _INITIAL_BUILD_TRANSACTION_BUDGET, (
        f"initial build used {len(ordered)} writer transactions; "
        f"budget={_INITIAL_BUILD_TRANSACTION_BUDGET}"
    )
    assert p95 <= _INITIAL_WRITER_P95_BUDGET_MS, (
        f"staging writer p95 {p95:.3f} ms exceeded "
        f"{_INITIAL_WRITER_P95_BUDGET_MS:.1f} ms; total={elapsed:.3f}s"
    )
    with sqlite3.connect(paths.analytical) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0]
            == _CALL_COUNT
        )


def test_append_safe_refresh_keeps_active_writer_lock_bounded(tmp_path: Path) -> None:
    source = tmp_path / "sessions" / "rollout-tail-synthetic.jsonl"
    source.parent.mkdir()
    source.write_text(
        '{"timestamp":"2026-01-01T00:00:00Z","type":"session_meta",'
        '"payload":{"id":"synthetic-tail-session"}}\n'
        '{"timestamp":"2026-01-01T00:00:00Z","type":"turn_context",'
        '"payload":{"turn_id":"turn-1","model":"gpt-synthetic","effort":"low"}}\n'
        + "".join(
            _token_line(f"event-initial-{index}", index % 100)
            for index in range(_CALL_COUNT)
        ),
        encoding="utf-8",
    )
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="performance-owner",
    )
    with source.open("a", encoding="utf-8") as handle:
        handle.write(
            "".join(
                _token_line(f"event-tail-{index}", index % 100)
                for index in range(2_000)
            )
        )

    result = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="performance-owner",
    )

    ordered = sorted(result.writer_transaction_ms)
    p95 = ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]
    print(
        json.dumps(
            {
                "active_calls": _CALL_COUNT,
                "appended_calls": result.inserted_calls,
                "writer_p95_ms": round(p95, 3),
                "writer_transactions": len(ordered),
            },
            sort_keys=True,
        )
    )
    assert result.planner_reason == "append_safe"
    assert result.inserted_calls == 2_000
    assert p95 <= _ACTIVE_WRITER_P95_BUDGET_MS, (
        f"active writer p95 {p95:.3f} ms exceeded "
        f"{_ACTIVE_WRITER_P95_BUDGET_MS:.1f} ms"
    )


def test_initial_build_defers_secondary_indexes_until_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "sessions" / "rollout-index-build.jsonl"
    source.parent.mkdir()
    source.write_text(
        '{"timestamp":"2026-01-01T00:00:00Z","type":"session_meta",'
        '"payload":{"id":"synthetic-index-session"}}\n'
        '{"timestamp":"2026-01-01T00:00:00Z","type":"turn_context",'
        '"payload":{"turn_id":"turn-1","model":"gpt-synthetic","effort":"low"}}\n'
        + _token_line("event-1", 1),
        encoding="utf-8",
    )
    paths = kernel_paths(tmp_path / "cache")
    observed_during_insert: list[tuple[bool, str, int]] = []
    real_insert = writer._insert_rows

    def record_index_state(
        connection: sqlite3.Connection,
        table: str,
        rows: tuple[dict[str, object], ...],
    ) -> int:
        if not observed_during_insert:
            observed_during_insert.append(
                (
                    connection.execute(
                        "SELECT 1 FROM sqlite_schema "
                        "WHERE type = 'index' AND name = 'idx_model_calls_time'"
                    ).fetchone()
                    is None,
                    str(connection.execute("PRAGMA journal_mode").fetchone()[0]),
                    int(connection.execute("PRAGMA synchronous").fetchone()[0]),
                )
            )
        return real_insert(connection, table, rows)

    monkeypatch.setattr(writer, "_insert_rows", record_index_state)
    KernelIngestor(paths.analytical, paths.operational).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="performance-owner",
    )

    assert observed_during_insert == [(True, "off", 0)]
    with sqlite3.connect(paths.analytical) as connection:
        assert connection.execute(
            "SELECT 1 FROM sqlite_schema "
            "WHERE type = 'index' AND name = 'idx_model_calls_time'"
        ).fetchone() is not None
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
