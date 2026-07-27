from __future__ import annotations

import sqlite3
from pathlib import Path

from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger
from codex_usage_tracker.kernel.live.journal import GenerationJournal
from codex_usage_tracker.kernel.live.stream import LiveStream
from codex_usage_tracker.kernel.operational import kernel_paths, load_cutover_control
from tests.kernel.test_ingest_pipeline import _token_line


def test_refresh_publishes_after_commit_and_no_change_emits_nothing(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    paths = kernel_paths(tmp_path / "cache")
    journal = GenerationJournal(paths.operational)
    ingestor = KernelIngestor(
        paths.analytical,
        paths.operational,
        journal=journal,
    )

    first = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="live-owner",
    )
    unchanged = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.WATCHER,
        owner_id="live-owner",
    )

    assert first.live_event_id == 1
    assert first.live_journal_status == "published"
    assert unchanged.planner_reason == "no_changes"
    assert unchanged.live_event_id is None
    replay = LiveStream(journal).read(
        last_event_id=None,
        active_generation=first.generation,
    )
    assert [event.generation for event in replay.events] == [1]
    assert replay.events[0].payload["inserted_calls"] == 1


def test_journal_failure_preserves_generation_and_forces_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = _source(tmp_path)
    paths = kernel_paths(tmp_path / "cache")
    journal = GenerationJournal(paths.operational)

    def fail_publish(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic journal failure")

    monkeypatch.setattr(journal, "publish_generation", fail_publish)
    result = KernelIngestor(
        paths.analytical,
        paths.operational,
        journal=journal,
    ).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="live-owner",
    )

    assert result.live_journal_status == "snapshot_required"
    assert load_cutover_control(paths.operational).active_generation == 1
    batch = LiveStream(journal).read(
        last_event_id=None,
        active_generation=1,
    )
    assert batch.snapshot_required


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "sessions" / "rollout-live-synthetic.jsonl"
    source.parent.mkdir()
    source.write_text(
        '{"timestamp":"2026-01-01T00:00:00Z","type":"session_meta",'
        '"payload":{"id":"synthetic-live-session"}}\n'
        '{"timestamp":"2026-01-01T00:00:00Z","type":"turn_context",'
        '"payload":{"turn_id":"turn-1","model":"gpt-synthetic","effort":"low"}}\n'
        + _token_line("event-1", 10),
        encoding="utf-8",
    )
    return source
