from __future__ import annotations

import json
import sqlite3
import statistics
import time
from pathlib import Path

from codex_usage_tracker.kernel.evidence import (
    EvidenceRequest,
    EvidenceService,
    EvidenceView,
)
from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger
from codex_usage_tracker.kernel.operational import kernel_paths
from tests.kernel.test_ingest_pipeline import _token_line

_CALL_COUNT = 100_000
_TIMELINE_P95_BUDGET_MS = 500.0


def test_100k_timeline_first_page_meets_budget(tmp_path: Path) -> None:
    source = tmp_path / "sessions" / "rollout-evidence-100k.jsonl"
    source.parent.mkdir()
    source.write_text(
        '{"timestamp":"2026-01-01T00:00:00Z","type":"session_meta",'
        '"payload":{"id":"synthetic-evidence-100k"}}\n'
        '{"timestamp":"2026-01-01T00:00:00Z","type":"turn_context",'
        '"payload":{"turn_id":"turn-1","model":"gpt-synthetic","effort":"low"}}\n'
        + "".join(
            _token_line(f"event-{index}", index % 100)
            for index in range(_CALL_COUNT)
        ),
        encoding="utf-8",
    )
    paths = kernel_paths(tmp_path / "cache")
    KernelIngestor(paths.analytical, paths.operational).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="evidence-performance",
    )
    with sqlite3.connect(paths.analytical) as connection:
        logical_thread_id = connection.execute(
            "SELECT logical_thread_id FROM threads LIMIT 1"
        ).fetchone()[0]
    service = EvidenceService(paths.operational)
    request = EvidenceRequest(
        selector=f"thread:{logical_thread_id}",
        view=EvidenceView.TIMELINE,
        limit=100,
    )

    service.read(request)
    timings: list[float] = []
    for _ in range(7):
        started = time.perf_counter()
        result = service.read(request)
        timings.append((time.perf_counter() - started) * 1000)
    p95 = sorted(timings)[-1]
    print(
        json.dumps(
            {
                "calls": _CALL_COUNT,
                "timeline_first_page_p95_ms": round(p95, 3),
                "timeline_first_page_median_ms": round(
                    statistics.median(timings),
                    3,
                ),
            },
            sort_keys=True,
        )
    )

    assert result.returned_count == 100
    assert result.matched_count == _CALL_COUNT
    assert p95 <= _TIMELINE_P95_BUDGET_MS
