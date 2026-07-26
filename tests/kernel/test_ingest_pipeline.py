from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from codex_usage_tracker.kernel import ingest, operational, writer
from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger
from codex_usage_tracker.kernel.models import CutoverState
from codex_usage_tracker.kernel.operational import (
    kernel_paths,
    load_cutover_control,
)


def _token_line(event_id: str, value: int) -> str:
    return (
        '{"event_id":"'
        + event_id
        + '","timestamp":"2026-01-01T00:00:01Z","type":"event_msg",'
        '"payload":{"type":"token_count","info":{"last_token_usage":'
        '{"input_tokens":'
        + str(value)
        + ',"cached_input_tokens":1,"output_tokens":2,'
        '"reasoning_output_tokens":1,"total_tokens":'
        + str(value + 2)
        + '},"model_context_window":200000}}}\n'
    )


def test_explicit_refresh_is_incremental_and_no_change_is_read_only(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sessions" / "rollout-synthetic.jsonl"
    source.parent.mkdir()
    source.write_text(
        '{"timestamp":"2026-01-01T00:00:00Z","type":"session_meta",'
        '"payload":{"id":"synthetic-session"}}\n'
        '{"timestamp":"2026-01-01T00:00:00Z","type":"turn_context",'
        '"payload":{"turn_id":"turn-1","model":"gpt-synthetic","effort":"low"}}\n'
        + _token_line("event-1", 10),
        encoding="utf-8",
    )
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)

    first = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-1",
    )
    before = paths.analytical.read_bytes()
    second = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.MCP_USAGE_REFRESH,
        owner_id="owner-1",
    )

    assert first.generation == 1
    assert first.inserted_calls == 1
    assert second.planner_reason == "no_changes"
    assert second.generation == 1
    assert paths.analytical.read_bytes() == before


def test_partial_tail_waits_then_moving_tail_catches_up(tmp_path: Path) -> None:
    source = tmp_path / "sessions" / "rollout-synthetic.jsonl"
    source.parent.mkdir()
    source.write_text(
        '{"timestamp":"2026-01-01T00:00:00Z","type":"session_meta",'
        '"payload":{"id":"synthetic-session"}}\n'
        '{"timestamp":"2026-01-01T00:00:00Z","type":"turn_context",'
        '"payload":{"turn_id":"turn-1","model":"gpt-synthetic","effort":"low"}}\n'
        + _token_line("event-1", 10),
        encoding="utf-8",
    )
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CONSOLE_REFRESH,
        owner_id="owner-1",
    )
    tail = _token_line("event-2", 20)
    with source.open("a", encoding="utf-8") as handle:
        handle.write(tail[:-1])

    waiting = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.MCP_USAGE_REFRESH,
        owner_id="owner-1",
    )
    assert waiting.planner_reason == "no_changes"

    with source.open("a", encoding="utf-8") as handle:
        handle.write("\n")
    caught_up = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.MCP_USAGE_REFRESH,
        owner_id="owner-1",
    )
    assert caught_up.planner_reason == "append_safe"
    assert caught_up.generation == 2
    with sqlite3.connect(paths.analytical) as connection:
        assert connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0] == 2


def test_non_refresh_trigger_cannot_initialize_cache(tmp_path: Path) -> None:
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)

    try:
        ingestor.refresh([], trigger="status", owner_id="owner-1")  # type: ignore[arg-type]
    except ValueError as exc:
        assert "explicit refresh" in str(exc)
    else:
        raise AssertionError("non-refresh trigger initialized the cache")
    assert not paths.analytical.exists()


def test_source_appended_during_hydration_is_caught_before_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "sessions" / "rollout-moving.jsonl"
    source.parent.mkdir()
    source.write_text(
        '{"timestamp":"2026-01-01T00:00:00Z","type":"session_meta",'
        '"payload":{"id":"synthetic-session"}}\n'
        '{"timestamp":"2026-01-01T00:00:00Z","type":"turn_context",'
        '"payload":{"turn_id":"turn-1","model":"gpt-synthetic","effort":"low"}}\n'
        + _token_line("event-1", 10),
        encoding="utf-8",
    )
    paths = kernel_paths(tmp_path / "cache")
    real_batches = ingest.iter_jsonl_batches
    appended = False

    def batches_then_append(plan, prior_state=None, *, max_lines=1000):
        nonlocal appended
        yield from real_batches(plan, prior_state, max_lines=max_lines)
        if not appended:
            with source.open("a", encoding="utf-8") as handle:
                handle.write(_token_line("event-2", 20))
            appended = True

    monkeypatch.setattr(ingest, "iter_jsonl_batches", batches_then_append)
    first = KernelIngestor(paths.analytical, paths.operational).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-1",
    )
    second = KernelIngestor(paths.analytical, paths.operational).refresh(
        [source],
        trigger=RefreshTrigger.MCP_USAGE_REFRESH,
        owner_id="owner-2",
    )

    assert first.inserted_calls == 2
    assert second.planner_reason == "no_changes"
    assert second.inserted_calls == 0
    with sqlite3.connect(paths.analytical) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM model_calls"
        ).fetchone()[0] == 2


def test_initial_hydration_normalizes_bounded_batches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "sessions" / "rollout-bounded.jsonl"
    source.parent.mkdir()
    source.write_text(
        '{"timestamp":"2026-01-01T00:00:00Z","type":"session_meta",'
        '"payload":{"id":"synthetic-bounded-session"}}\n'
        '{"timestamp":"2026-01-01T00:00:00Z","type":"turn_context",'
        '"payload":{"turn_id":"turn-1","model":"gpt-synthetic","effort":"low"}}\n'
        + "".join(_token_line(f"event-{index}", 1) for index in range(2500)),
        encoding="utf-8",
    )
    observed_batch_sizes: list[int] = []
    real_normalize = ingest.normalize_batch

    def record_batch(plan, parsed, *, generation):
        observed_batch_sizes.append(parsed.parsed_line_count)
        return real_normalize(plan, parsed, generation=generation)

    monkeypatch.setattr(ingest, "normalize_batch", record_batch)
    paths = kernel_paths(tmp_path / "cache")
    result = KernelIngestor(paths.analytical, paths.operational).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-1",
    )

    assert result.inserted_calls == 2500
    assert len(observed_batch_sizes) >= 3
    assert max(observed_batch_sizes) <= 1000


def test_append_promotion_never_hashes_full_analytical_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "sessions" / "rollout-bounded.jsonl"
    source.parent.mkdir()
    source.write_text(
        '{"timestamp":"2026-01-01T00:00:00Z","type":"session_meta",'
        '"payload":{"id":"synthetic-session"}}\n'
        '{"timestamp":"2026-01-01T00:00:00Z","type":"turn_context",'
        '"payload":{"turn_id":"turn-1","model":"gpt-synthetic","effort":"low"}}\n'
        + _token_line("event-1", 1),
        encoding="utf-8",
    )
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-1",
    )
    with source.open("a", encoding="utf-8") as handle:
        handle.write(_token_line("event-2", 2))

    def forbid_full_digest(_path):
        raise AssertionError("append promotion attempted a full artifact digest")

    monkeypatch.setattr(operational, "analytical_digest", forbid_full_digest)
    result = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.MCP_USAGE_REFRESH,
        owner_id="owner-2",
    )
    assert result.inserted_calls == 1


def test_partial_batch_crash_retries_same_generation_idempotently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "sessions" / "rollout-crash-synthetic.jsonl"
    source.parent.mkdir()
    source.write_text(
        '{"timestamp":"2026-01-01T00:00:00Z","type":"session_meta",'
        '"payload":{"id":"synthetic-crash-session"}}\n'
        '{"timestamp":"2026-01-01T00:00:00Z","type":"turn_context",'
        '"payload":{"turn_id":"turn-1","model":"gpt-synthetic","effort":"low"}}\n'
        + "".join(_token_line(f"event-{index}", index) for index in range(600)),
        encoding="utf-8",
    )
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    real_insert = writer._insert_rows
    calls = 0

    def fail_second_batch(connection, table, rows):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("synthetic process crash")
        return real_insert(connection, table, rows)

    monkeypatch.setattr(writer, "_insert_rows", fail_second_batch)
    with pytest.raises(RuntimeError, match="synthetic process crash"):
        ingestor.refresh(
            [source],
            trigger=RefreshTrigger.CLI_REFRESH,
            owner_id="crashed-owner",
        )
    assert load_cutover_control(paths.operational).state is CutoverState.FAILED

    monkeypatch.setattr(writer, "_insert_rows", real_insert)
    recovered = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="recovery-owner",
    )

    assert recovered.generation == 1
    assert recovered.inserted_calls == 600
    assert load_cutover_control(paths.operational).state is CutoverState.ACTIVE
    with sqlite3.connect(paths.analytical) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM generations"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM model_calls"
        ).fetchone()[0] == 600
