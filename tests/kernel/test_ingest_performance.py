"""Synthetic large-history ingestion budgets."""

from __future__ import annotations

import json
import math
import sqlite3
import time
from pathlib import Path

from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger
from codex_usage_tracker.kernel.operational import kernel_paths
from tests.kernel.test_ingest_pipeline import _token_line

_CALL_COUNT = 100_000
_WRITER_P95_BUDGET_MS = 50.0


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
    assert p95 <= _WRITER_P95_BUDGET_MS, (
        f"writer p95 {p95:.3f} ms exceeded "
        f"{_WRITER_P95_BUDGET_MS:.1f} ms; total={elapsed:.3f}s"
    )
    with sqlite3.connect(paths.analytical) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0]
            == _CALL_COUNT
        )
