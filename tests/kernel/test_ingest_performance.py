"""Synthetic large-history ingestion budgets."""

from __future__ import annotations

import json
import math
import shutil
import sqlite3
import time
from pathlib import Path

import pytest

from codex_usage_tracker.kernel import ingest, writer
from codex_usage_tracker.kernel.database import initialize_analytical_database
from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger
from codex_usage_tracker.kernel.operational import kernel_paths, load_cutover_control
from tests.kernel.performance_qualification import record_wall_clock_budget
from tests.kernel.test_ingest_pipeline import _token_line

_CALL_COUNT = 100_000
_ACTIVE_WRITER_APPEND_CALLS = 2_000
_ACTIVE_WRITER_MEASURED_REFRESHES = 5
# Preserve the 50 ms sustained SLO while bounding one isolated lock separately.
_ACTIVE_WRITER_P95_BUDGET_MS = 50.0
_ACTIVE_WRITER_MAX_BUDGET_MS = 150.0
_ACTIVE_WRITER_MIN_SAMPLES = 40
_INITIAL_WRITER_P95_BUDGET_MS = 2_000.0
_INITIAL_BUILD_TRANSACTION_BUDGET = 10


def _assert_active_writer_latency_budget(
    timings: tuple[float, ...],
) -> tuple[float, float]:
    assert len(timings) >= _ACTIVE_WRITER_MIN_SAMPLES, (
        f"active writer p95 requires at least {_ACTIVE_WRITER_MIN_SAMPLES} samples; "
        f"observed={len(timings)}"
    )
    ordered = sorted(timings)
    p95 = ordered[math.ceil(len(ordered) * 0.95) - 1]
    maximum = ordered[-1]
    assert p95 <= _ACTIVE_WRITER_P95_BUDGET_MS, (
        f"active writer p95 {p95:.3f} ms exceeded "
        f"{_ACTIVE_WRITER_P95_BUDGET_MS:.1f} ms"
    )
    assert maximum <= _ACTIVE_WRITER_MAX_BUDGET_MS, (
        f"active writer maximum {maximum:.3f} ms exceeded "
        f"{_ACTIVE_WRITER_MAX_BUDGET_MS:.1f} ms"
    )
    return p95, maximum


def _append_token_lines(source: Path, prefix: str, *, count: int) -> None:
    with source.open("a", encoding="utf-8") as handle:
        handle.write(
            "".join(
                _token_line(f"{prefix}-{index}", index % 100)
                for index in range(count)
            )
        )


def test_active_writer_latency_budget_distinguishes_noise_from_regressions() -> None:
    one_runner_pause = (30.0,) * 99 + (98.0,)
    sustained_regression = (30.0,) * 94 + (51.0,) * 6
    catastrophic_lock = (30.0,) * 99 + (151.0,)

    assert _assert_active_writer_latency_budget(one_runner_pause) == (30.0, 98.0)
    with pytest.raises(AssertionError, match="p95"):
        _assert_active_writer_latency_budget(sustained_regression)
    with pytest.raises(AssertionError, match="maximum"):
        _assert_active_writer_latency_budget(catastrophic_lock)


def test_checkpointed_clone_uses_copy_on_write_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "destination.sqlite3"
    initialize_analytical_database(source)
    with sqlite3.connect(source) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    clone_calls: list[tuple[Path, Path]] = []

    def clone_file(current: Path, staging: Path) -> bool:
        clone_calls.append((current, staging))
        shutil.copyfile(current, staging)
        return True

    monkeypatch.setattr(ingest, "_copy_on_write_clone", clone_file)
    ingest._clone_database(source, destination)

    assert clone_calls == [(source, destination)]
    with sqlite3.connect(destination) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (3,)


def test_nonempty_wal_uses_sqlite_snapshot_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "destination.sqlite3"
    initialize_analytical_database(source)
    connection = sqlite3.connect(source)
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA wal_autocheckpoint = 0")
        connection.execute(
            """
            INSERT INTO generations VALUES (
                1, 'sha256:source', CURRENT_TIMESTAMP, 'sha256:water',
                0, 0, 0, 0, 0, NULL, '{}', 'valid'
            )
            """
        )
        connection.commit()
        wal = source.with_name(source.name + "-wal")
        assert wal.stat().st_size > 0

        def unexpected_clone(_source: Path, _destination: Path) -> bool:
            raise AssertionError("nonempty WAL must use SQLite backup")

        monkeypatch.setattr(ingest, "_copy_on_write_clone", unexpected_clone)
        ingest._clone_database(source, destination)
    finally:
        connection.close()

    with sqlite3.connect(destination) as copied:
        assert copied.execute("SELECT generation FROM generations").fetchone() == (1,)


def test_tail_backfills_tool_turn_index_on_unpublished_clone(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sessions" / "rollout-index-upgrade.jsonl"
    source.parent.mkdir()
    source.write_text(
        '{"timestamp":"2026-01-01T00:00:00Z","type":"session_meta",'
        '"payload":{"id":"synthetic-index-upgrade"}}\n'
        '{"timestamp":"2026-01-01T00:00:00Z","type":"turn_context",'
        '"payload":{"turn_id":"turn-1","model":"gpt-synthetic","effort":"low"}}\n'
        + _token_line("event-1", 10),
        encoding="utf-8",
    )
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="index-upgrade-initial",
    )
    prior = load_cutover_control(paths.operational).active_kernel_path
    assert prior is not None
    with sqlite3.connect(prior) as connection:
        connection.execute("DROP INDEX idx_tool_calls_turn")
    with source.open("a", encoding="utf-8") as handle:
        handle.write(_token_line("event-2", 20))

    result = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="index-upgrade-tail",
    )
    current = load_cutover_control(paths.operational).active_kernel_path

    assert result.generation == 2
    assert current is not None
    assert current != prior
    with sqlite3.connect(current) as connection:
        assert connection.execute(
            """
            SELECT 1 FROM sqlite_schema
            WHERE type = 'index' AND name = 'idx_tool_calls_turn'
            """
        ).fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM model_calls").fetchone() == (2,)


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
    record_wall_clock_budget(
        "initial_writer_p95_ms",
        p95,
        _INITIAL_WRITER_P95_BUDGET_MS,
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
    _append_token_lines(
        source,
        "event-tail-warmup",
        count=_ACTIVE_WRITER_APPEND_CALLS,
    )
    warmup = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="performance-owner",
    )
    assert warmup.planner_reason == "append_safe"
    assert warmup.inserted_calls == _ACTIVE_WRITER_APPEND_CALLS

    # One refresh currently yields only 15 timings, where nearest-rank p95 is
    # the single maximum. Aggregate independent tails so p95 is meaningful.
    timings: list[float] = []
    for sample in range(_ACTIVE_WRITER_MEASURED_REFRESHES):
        _append_token_lines(
            source,
            f"event-tail-measured-{sample}",
            count=_ACTIVE_WRITER_APPEND_CALLS,
        )
        result = ingestor.refresh(
            [source],
            trigger=RefreshTrigger.CLI_REFRESH,
            owner_id="performance-owner",
        )
        assert result.planner_reason == "append_safe"
        assert result.inserted_calls == _ACTIVE_WRITER_APPEND_CALLS
        timings.extend(result.writer_transaction_ms)

    assert len(timings) >= _ACTIVE_WRITER_MIN_SAMPLES
    ordered = sorted(timings)
    p95 = ordered[math.ceil(len(ordered) * 0.95) - 1]
    maximum = ordered[-1]
    print(
        json.dumps(
            {
                "active_calls": _CALL_COUNT,
                "appended_calls_per_refresh": _ACTIVE_WRITER_APPEND_CALLS,
                "measured_refreshes": _ACTIVE_WRITER_MEASURED_REFRESHES,
                "writer_max_ms": round(maximum, 3),
                "writer_p95_ms": round(p95, 3),
                "writer_transactions": len(timings),
            },
            sort_keys=True,
        )
    )
    record_wall_clock_budget(
        "active_writer_p95_ms",
        p95,
        _ACTIVE_WRITER_P95_BUDGET_MS,
    )
    record_wall_clock_budget(
        "active_writer_max_ms",
        maximum,
        _ACTIVE_WRITER_MAX_BUDGET_MS,
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
