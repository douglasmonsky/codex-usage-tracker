from __future__ import annotations

from concurrent.futures import Future
from concurrent.futures import wait as futures_wait
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.store import content_index_parallel as content_parallel_module
from codex_usage_tracker.store import refresh as refresh_module
from codex_usage_tracker.store import refresh_parse as parse_module
from codex_usage_tracker.store import refresh_stream as stream_module
from codex_usage_tracker.store.api import connect, init_db
from codex_usage_tracker.store.sources import SourceParsePlan
from tests.store_dashboard_helpers import _make_codex_home


class RecordingProcessPoolExecutor:
    instances: list[RecordingProcessPoolExecutor] = []

    def __init__(self, *, max_workers: int) -> None:
        self.max_workers = max_workers
        self.submitted = 0
        self.instances.append(self)

    def __enter__(self) -> RecordingProcessPoolExecutor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def submit(self, fn: Any, *args: object, **kwargs: object) -> Future[Any]:
        future: Future[Any] = Future()
        self.submitted += 1
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:
            future.set_exception(exc)
        return future


class BrokenProcessPoolExecutor:
    def __init__(self, *, max_workers: int) -> None:
        self.max_workers = max_workers

    def __enter__(self) -> BrokenProcessPoolExecutor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def submit(self, fn: Any, *args: object, **kwargs: object) -> Future[Any]:
        future: Future[Any] = Future()
        future.set_exception(BrokenProcessPool("worker pool unavailable"))
        return future


def test_refresh_parses_multiple_sources_with_worker_pool(tmp_path: Path, monkeypatch) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    RecordingProcessPoolExecutor.instances.clear()
    monkeypatch.setenv("CODEX_USAGE_TRACKER_REFRESH_WORKERS", "2")
    monkeypatch.setattr(
        parse_module,
        "ProcessPoolExecutor",
        RecordingProcessPoolExecutor,
    )

    result = refresh_module.refresh_usage_index(codex_home=codex_home, db_path=db_path)

    assert result.parsed_events > 0
    assert len(RecordingProcessPoolExecutor.instances) == 1
    assert RecordingProcessPoolExecutor.instances[0].max_workers == 2
    assert RecordingProcessPoolExecutor.instances[0].submitted >= 2
    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute("SELECT COUNT(*) AS event_count FROM usage_events").fetchone()
    assert row is not None
    assert row["event_count"] == result.inserted_or_updated_events


def test_refresh_persists_bounded_source_batches(tmp_path: Path, monkeypatch) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    batch_sizes: list[int] = []
    original_upsert = stream_module._upsert_usage_events_in_connection

    def recording_upsert(conn, events, **kwargs):
        event_batch = list(events)
        if event_batch:
            batch_sizes.append(len(event_batch))
        return original_upsert(conn, event_batch, **kwargs)

    monkeypatch.setenv("CODEX_USAGE_TRACKER_REFRESH_WORKERS", "1")
    monkeypatch.setattr(stream_module, "_STREAM_SOURCE_BATCH_SIZE", 2)
    monkeypatch.setattr(
        stream_module,
        "_upsert_usage_events_in_connection",
        recording_upsert,
    )

    result = refresh_module.refresh_usage_index(codex_home=codex_home, db_path=db_path)

    parsed_sources = refresh_module.find_session_logs(
        codex_home=codex_home,
        include_archived=False,
    )
    assert 1 < len(batch_sizes) <= len(parsed_sources)
    assert sum(batch_sizes) == result.parsed_events
    assert max(batch_sizes) < result.parsed_events


def test_full_refresh_defers_and_restores_bulk_load_indexes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    observed_source_indexes: list[list[str]] = []
    original_upsert = stream_module.upsert_source_records_from_events

    def recording_upsert(conn, *, events):
        observed_source_indexes.append(
            [
                str(row["name"])
                for row in conn.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'index'
                      AND tbl_name = 'source_records'
                      AND sql IS NOT NULL
                    ORDER BY name
                    """
                )
            ]
        )
        return original_upsert(conn, events=events)

    monkeypatch.setenv("CODEX_USAGE_TRACKER_REFRESH_WORKERS", "1")
    monkeypatch.setattr(
        stream_module,
        "upsert_source_records_from_events",
        recording_upsert,
    )

    refresh_module.refresh_usage_index(codex_home=codex_home, db_path=db_path)

    assert observed_source_indexes
    assert all(not names for names in observed_source_indexes)
    with connect(db_path) as conn:
        restored = {
            str(row["name"])
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'index'
                  AND tbl_name IN ('call_diagnostic_facts', 'source_records')
                  AND sql IS NOT NULL
                """
            )
        }
    assert restored == {
        "idx_call_diagnostic_facts_record",
        "idx_call_diagnostic_facts_lookup",
        "idx_call_diagnostic_facts_type_name",
        "idx_source_records_event_timestamp",
        "idx_source_records_shape_adapter",
        "idx_source_records_source_line",
    }


def test_parallel_parse_submission_queue_is_bounded(tmp_path: Path, monkeypatch) -> None:
    codex_home = _make_codex_home(tmp_path)
    source_path = refresh_module.find_session_logs(
        codex_home=codex_home,
        include_archived=True,
    )[0]
    plans = [SourceParsePlan(path=source_path) for _index in range(10)]
    pending_sizes: list[int] = []
    RecordingProcessPoolExecutor.instances.clear()
    monkeypatch.setattr(
        parse_module,
        "ProcessPoolExecutor",
        RecordingProcessPoolExecutor,
    )

    def recording_wait(futures, *, return_when):
        pending_sizes.append(len(futures))
        return futures_wait(futures, return_when=return_when)

    monkeypatch.setattr(parse_module, "wait", recording_wait)

    results = parse_module.parse_refresh_plans_parallel(
        plans,
        session_index={},
        worker_count=2,
        progress_callback=None,
    )

    assert len(results) == len(plans)
    assert max(pending_sizes) <= 4
    assert RecordingProcessPoolExecutor.instances[0].submitted == len(plans)


def test_automatic_worker_count_requires_material_pending_bytes(tmp_path: Path) -> None:
    small_plans = _sparse_parse_plans(tmp_path / "small", count=8, bytes_per_file=1_024)
    large_plans = _sparse_parse_plans(
        tmp_path / "large",
        count=8,
        bytes_per_file=5 * 1024 * 1024,
    )

    assert parse_module.parallel_parse_worker_count(small_plans) == 1
    assert parse_module.parallel_parse_worker_count(large_plans) > 1


def test_refresh_falls_back_to_serial_parse_when_worker_pool_breaks(
    tmp_path: Path, monkeypatch
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    monkeypatch.setenv("CODEX_USAGE_TRACKER_REFRESH_WORKERS", "2")
    monkeypatch.setattr(
        parse_module,
        "ProcessPoolExecutor",
        BrokenProcessPoolExecutor,
    )

    result = refresh_module.refresh_usage_index(codex_home=codex_home, db_path=db_path)

    assert result.parsed_events > 0
    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute("SELECT COUNT(*) AS event_count FROM usage_events").fetchone()
    assert row is not None
    assert row["event_count"] == result.inserted_or_updated_events


def test_refresh_serial_retry_disables_broken_content_pool(tmp_path: Path, monkeypatch) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    monkeypatch.setenv("CODEX_USAGE_TRACKER_CONTENT_INDEX_WORKERS", "2")
    monkeypatch.setattr(parse_module, "default_parser_is_active", lambda: False)
    monkeypatch.setattr(stream_module, "default_parser_is_active", lambda: False)
    monkeypatch.setattr(
        content_parallel_module,
        "ProcessPoolExecutor",
        BrokenProcessPoolExecutor,
    )

    result = refresh_module.refresh_usage_index(codex_home=codex_home, db_path=db_path)

    assert result.parsed_events > 0
    with connect(db_path) as conn:
        init_db(conn)
        assert conn.execute("SELECT COUNT(*) FROM content_fragments").fetchone()[0] > 0


def test_refresh_rolls_back_aggregate_rows_when_content_sync_fails(
    tmp_path: Path, monkeypatch
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"

    def fail_sync(*args: object, **kwargs: object) -> None:
        raise RuntimeError("synthetic fact sync failure")

    monkeypatch.setattr(stream_module.IngestionFactWriter, "finish", fail_sync)

    with pytest.raises(RuntimeError, match="synthetic fact sync failure"):
        refresh_module.refresh_usage_index(codex_home=codex_home, db_path=db_path)

    with connect(db_path) as conn:
        init_db(conn)
        assert conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 0


def test_refresh_reports_phase_progress(tmp_path: Path, monkeypatch) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    events: list[dict[str, object]] = []
    monkeypatch.setenv("CODEX_USAGE_TRACKER_REFRESH_WORKERS", "1")

    result = refresh_module.refresh_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        progress_callback=events.append,
    )

    phases = [event["phase"] for event in events]
    assert "discovering" in phases
    assert "parsing" in phases
    assert "upserting" in phases
    assert "metadata" in phases
    assert "indexing_content" in phases
    assert "syncing_facts" in phases
    assert phases[-1] == "finalizing"
    assert events[-1]["status"] == "completed"
    final_result = events[-1]["result"]
    assert isinstance(final_result, dict)
    assert final_result["parsed_events"] == result.parsed_events
    content_events = [event for event in events if event["phase"] == "indexing_content"]
    assert content_events
    assert content_events[-1]["status"] == "completed"
    assert content_events[-1]["percent"] == 100.0
    content_fragments = content_events[-1]["content_fragments"]
    assert isinstance(content_fragments, (int, float))
    assert content_fragments > 0


def test_unchanged_refresh_completes_every_started_phase(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_module.refresh_usage_index(codex_home=codex_home, db_path=db_path)
    events: list[dict[str, object]] = []

    refresh_module.refresh_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        progress_callback=events.append,
    )

    terminal = {"completed", "skipped", "failed"}
    for phase in {str(event["phase"]) for event in events}:
        phase_events = [event for event in events if event["phase"] == phase]
        assert phase_events[-1]["status"] in terminal


def _sparse_parse_plans(
    root: Path,
    *,
    count: int,
    bytes_per_file: int,
) -> list[SourceParsePlan]:
    root.mkdir(parents=True)
    plans: list[SourceParsePlan] = []
    for index in range(count):
        path = root / f"source-{index}.jsonl"
        with path.open("wb") as handle:
            handle.truncate(bytes_per_file)
        plans.append(SourceParsePlan(path=path))
    return plans
