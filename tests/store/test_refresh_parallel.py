from __future__ import annotations

from concurrent.futures import Future
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import Any

from codex_usage_tracker.store import refresh as refresh_module
from codex_usage_tracker.store.api import connect, init_db
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
        refresh_module,
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


def test_refresh_falls_back_to_serial_parse_when_worker_pool_breaks(
    tmp_path: Path, monkeypatch
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    monkeypatch.setenv("CODEX_USAGE_TRACKER_REFRESH_WORKERS", "2")
    monkeypatch.setattr(
        refresh_module,
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
    assert phases[-1] == "finalizing"
    assert events[-1]["status"] == "completed"
    assert events[-1]["result"]["parsed_events"] == result.parsed_events
    content_events = [event for event in events if event["phase"] == "indexing_content"]
    assert content_events
    assert content_events[-1]["status"] == "completed"
    assert content_events[-1]["percent"] == 100.0
    assert content_events[-1]["content_fragments"] > 0
