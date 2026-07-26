from __future__ import annotations

import threading
from pathlib import Path

import pytest

from codex_usage_tracker.kernel import writer
from codex_usage_tracker.kernel.database import (
    initialize_analytical_database,
    open_read_snapshot,
    short_writer_transaction,
)
from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger
from codex_usage_tracker.kernel.operational import (
    kernel_paths,
    load_cutover_control,
)
from tests.kernel.test_ingest_pipeline import _token_line


def _publish_synthetic_generation(
    path: Path,
    generation: int,
    *,
    writer_started: threading.Event,
    allow_commit: threading.Event,
) -> None:
    with short_writer_transaction(path) as connection:
        connection.execute(
            """
            INSERT INTO generations(
                generation, source_revision_digest, created_at,
                high_water_digest, inserted_count, updated_count,
                deleted_count, canonical_count, excluded_count,
                parser_versions, integrity_status
            )
            VALUES (?, 'sha256:synthetic', CURRENT_TIMESTAMP,
                    'sha256:synthetic', 0, 0, 0, 0, 0, '{}', 'valid')
            """,
            (generation,),
        )
        writer_started.set()
        if not allow_commit.wait(timeout=2):
            raise TimeoutError("synthetic commit was not released")


def test_reader_snapshot_sees_one_complete_generation(tmp_path: Path) -> None:
    path = tmp_path / "kernel.sqlite3"
    initialize_analytical_database(path)
    writer_started = threading.Event()
    allow_commit = threading.Event()

    thread = threading.Thread(
        target=_publish_synthetic_generation,
        args=(path, 1),
        kwargs={
            "writer_started": writer_started,
            "allow_commit": allow_commit,
        },
    )
    thread.start()
    assert writer_started.wait(timeout=2)
    with open_read_snapshot(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM generations").fetchone()[0] == 0
        allow_commit.set()
        thread.join(timeout=2)
        assert connection.execute("SELECT COUNT(*) FROM generations").fetchone()[0] == 0
    with open_read_snapshot(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM generations").fetchone()[0] == 1


def test_active_generation_hides_committed_batches_until_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "sessions" / "rollout-concurrent.jsonl"
    source.parent.mkdir()
    source.write_text(
        '{"timestamp":"2026-01-01T00:00:00Z","type":"session_meta",'
        '"payload":{"id":"synthetic-concurrent-session"}}\n'
        '{"timestamp":"2026-01-01T00:00:00Z","type":"turn_context",'
        '"payload":{"turn_id":"turn-1","model":"gpt-synthetic","effort":"low"}}\n'
        + _token_line("event-0", 1),
        encoding="utf-8",
    )
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-1",
    )
    with open_read_snapshot(paths.analytical) as connection:
        before_threads = connection.execute(
            "SELECT * FROM threads ORDER BY thread_id"
        ).fetchall()
        before_turns = connection.execute(
            "SELECT * FROM turns ORDER BY turn_id"
        ).fetchall()
    with source.open("a", encoding="utf-8") as handle:
        handle.write(
            "".join(
                _token_line(f"event-{index}", index)
                for index in range(1, 401)
            )
        )

    first_batch_committed = threading.Event()
    release_writer = threading.Event()
    real_insert = writer._insert_rows
    calls = 0

    def pause_before_second_batch(connection, table, rows):
        nonlocal calls
        calls += 1
        if calls == 2:
            first_batch_committed.set()
            if not release_writer.wait(timeout=5):
                raise TimeoutError("synthetic reader did not release writer")
        return real_insert(connection, table, rows)

    monkeypatch.setattr(writer, "_insert_rows", pause_before_second_batch)
    errors: list[BaseException] = []

    def refresh() -> None:
        try:
            ingestor.refresh(
                [source],
                trigger=RefreshTrigger.MCP_USAGE_REFRESH,
                owner_id="owner-2",
            )
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=refresh)
    thread.start()
    assert first_batch_committed.wait(timeout=5)
    try:
        control = load_cutover_control(paths.operational)
        assert control.active_generation == 1
        assert control.active_kernel_path is not None
        with open_read_snapshot(control.active_kernel_path) as connection:
            assert connection.execute(
                """
                SELECT COUNT(*)
                FROM model_calls
                WHERE generation <= ?
                """,
                (control.active_generation,),
            ).fetchone()[0] == 1
            assert connection.execute(
                "SELECT * FROM threads WHERE first_generation <= ? "
                "ORDER BY thread_id",
                (control.active_generation,),
            ).fetchall() == before_threads
            assert connection.execute(
                "SELECT * FROM turns WHERE first_generation <= ? "
                "ORDER BY turn_id",
                (control.active_generation,),
            ).fetchall() == before_turns
            assert connection.execute(
                """
                SELECT MAX(generation)
                FROM generations
                WHERE integrity_status = 'valid'
                """
            ).fetchone()[0] == 1
    finally:
        release_writer.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert errors == []
    promoted = load_cutover_control(paths.operational)
    assert promoted.active_generation == 2
    assert promoted.active_kernel_path is not None
    with open_read_snapshot(promoted.active_kernel_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM model_calls"
        ).fetchone()[0] == 401
