from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger
from codex_usage_tracker.kernel.models import CutoverState
from codex_usage_tracker.kernel.operational import (
    kernel_paths,
    load_cutover_control,
)


def test_active_source_wins_canonical_copy_and_replacement_is_source_local(
    tmp_path: Path,
) -> None:
    active = tmp_path / "sessions" / "rollout-active.jsonl"
    archived = tmp_path / "archived_sessions" / "rollout-copy.jsonl"
    _write_usage(active, session="active-session", event="shared", tokens=10)
    _write_usage(archived, session="copy-session", event="shared", tokens=10)
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)

    ingestor.refresh(
        [archived, active],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-1",
    )

    with sqlite3.connect(paths.analytical) as connection:
        states = connection.execute(
            """
            SELECT sources.archive_state, model_calls.duplicate_state
            FROM model_calls
            JOIN sources USING (source_id)
            ORDER BY sources.archive_state
            """
        ).fetchall()
    assert states == [("active", "canonical"), ("archived", "copied")]

    replacement = active.with_suffix(".replacement")
    _write_usage(replacement, session="active-session", event="new", tokens=20)
    os.replace(replacement, active)
    result = ingestor.refresh(
        [archived, active],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-1",
    )

    assert result.deleted_rows == 1
    active_path = load_cutover_control(paths.operational).active_kernel_path
    assert active_path is not None
    with sqlite3.connect(active_path) as connection:
        rows = connection.execute(
            """
            SELECT input_tokens, duplicate_state
            FROM model_calls
            ORDER BY input_tokens
            """
        ).fetchall()
    assert rows == [(10, "canonical"), (20, "canonical")]


def test_same_logical_session_sources_replace_independently(
    tmp_path: Path,
) -> None:
    active = tmp_path / "sessions" / "rollout-active.jsonl"
    archived = tmp_path / "archived_sessions" / "rollout-copy.jsonl"
    _write_usage(active, session="shared-session", event="active", tokens=10)
    _write_usage(archived, session="shared-session", event="archive", tokens=20)
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    ingestor.refresh(
        [active, archived],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-1",
    )

    replacement = archived.with_suffix(".replacement")
    _write_usage(replacement, session="shared-session", event="new", tokens=30)
    os.replace(replacement, archived)
    ingestor.refresh(
        [active, archived],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-2",
    )

    control = load_cutover_control(paths.operational)
    assert control.active_kernel_path is not None
    with sqlite3.connect(control.active_kernel_path) as connection:
        assert connection.execute(
            "SELECT input_tokens FROM model_calls ORDER BY input_tokens"
        ).fetchall() == [(10,), (30,)]
        assert connection.execute(
            "SELECT COUNT(DISTINCT thread_id), COUNT(DISTINCT logical_thread_id) "
            "FROM threads"
        ).fetchone() == (2, 1)


def test_allowance_replacement_updates_value_and_source_provenance(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sessions" / "rollout-active.jsonl"
    _write_usage(
        source,
        session="allowance-session",
        event="before",
        tokens=10,
        allowance_used=10.0,
    )
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-1",
    )

    replacement = source.with_suffix(".replacement")
    _write_usage(
        replacement,
        session="allowance-session",
        event="after",
        tokens=20,
        allowance_used=80.0,
    )
    os.replace(replacement, source)
    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-2",
    )

    control = load_cutover_control(paths.operational)
    assert control.active_kernel_path is not None
    with sqlite3.connect(control.active_kernel_path) as connection:
        rows = connection.execute(
            """
            SELECT allowance_observations.used_percent,
                   allowance_observations.source_id,
                   sources.source_id
            FROM allowance_observations
            JOIN sources USING (source_id)
            """
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 80.0
    assert rows[0][1] == rows[0][2]


def test_failed_replacement_promotion_keeps_prior_active_and_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "sessions" / "rollout-active.jsonl"
    _write_usage(source, session="active-session", event="before", tokens=10)
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-1",
    )
    prior = load_cutover_control(paths.operational)
    assert prior.active_kernel_path is not None

    replacement = source.with_suffix(".replacement")
    _write_usage(replacement, session="active-session", event="after", tokens=20)
    os.replace(replacement, source)

    def fail_promotion(_path: Path, _generation: int) -> None:
        raise RuntimeError("synthetic promotion failure")

    monkeypatch.setattr(ingestor, "_promote", fail_promotion)
    with pytest.raises(RuntimeError, match="synthetic promotion failure"):
        ingestor.refresh(
            [source],
            trigger=RefreshTrigger.CLI_REFRESH,
            owner_id="owner-1",
        )

    failed = load_cutover_control(paths.operational)
    assert failed.state is CutoverState.FAILED
    assert failed.active_kernel_path == prior.active_kernel_path
    assert failed.active_generation == prior.active_generation
    with sqlite3.connect(prior.active_kernel_path) as connection:
        rows = connection.execute(
            "SELECT input_tokens FROM model_calls ORDER BY input_tokens"
        ).fetchall()
    assert rows == [(10,)]

    recovered = KernelIngestor(paths.analytical, paths.operational).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-2",
    )
    assert recovered.planner_reason == "no_changes"
    control = load_cutover_control(paths.operational)
    assert control.state is CutoverState.ACTIVE
    assert control.active_generation == 2
    assert control.active_kernel_path is not None
    with sqlite3.connect(control.active_kernel_path) as connection:
        rows = connection.execute(
            "SELECT input_tokens FROM model_calls ORDER BY input_tokens"
        ).fetchall()
    assert rows == [(20,)]


def test_interrupted_after_commit_promotes_valid_generation_on_next_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "sessions" / "rollout-active.jsonl"
    _write_usage(source, session="active-session", event="before", tokens=10)
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-1",
    )
    with source.open("a", encoding="utf-8") as handle:
        extra = source.with_suffix(".extra")
        _write_usage(extra, session="active-session", event="after", tokens=20)
        handle.write(extra.read_text(encoding="utf-8").splitlines()[-1] + "\n")

    monkeypatch.setattr(ingestor, "_promote", lambda _path, _generation: None)
    interrupted = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-2",
    )
    assert interrupted.generation == 2
    assert load_cutover_control(paths.operational).state is CutoverState.BUILDING

    recovered = KernelIngestor(paths.analytical, paths.operational).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-3",
    )
    control = load_cutover_control(paths.operational)
    assert recovered.planner_reason == "no_changes"
    assert recovered.generation == 2
    assert control.state is CutoverState.ACTIVE
    assert control.active_generation == 2


def test_same_source_move_to_archive_updates_only_that_source(
    tmp_path: Path,
) -> None:
    active = tmp_path / "sessions" / "rollout-moved.jsonl"
    _write_usage(active, session="moved-session", event="shared", tokens=10)
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    ingestor.refresh(
        [active],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-1",
    )

    archived = tmp_path / "archived_sessions" / active.name
    archived.parent.mkdir()
    os.replace(active, archived)
    moved = ingestor.refresh(
        [archived],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-2",
    )

    assert moved.planner_reason == "replace_source"
    control = load_cutover_control(paths.operational)
    assert control.active_kernel_path is not None
    with sqlite3.connect(control.active_kernel_path) as connection:
        rows = connection.execute(
            """
            SELECT sources.archive_state, model_calls.duplicate_state
            FROM model_calls
            JOIN sources USING (source_id)
            """
        ).fetchall()
    assert rows == [("archived", "canonical")]

    before = control.active_kernel_path.read_bytes()
    reopened = KernelIngestor(
        paths.analytical,
        paths.operational,
    ).refresh(
        [archived],
        trigger=RefreshTrigger.CONSOLE_REFRESH,
        owner_id="owner-3",
    )
    after = load_cutover_control(paths.operational)
    assert reopened.planner_reason == "no_changes"
    assert after.active_kernel_path == control.active_kernel_path
    assert after.active_kernel_path is not None
    assert after.active_kernel_path.read_bytes() == before


def test_unique_new_source_appends_without_cloning_active_database(
    tmp_path: Path,
) -> None:
    first = tmp_path / "sessions" / "rollout-first.jsonl"
    second = tmp_path / "sessions" / "rollout-second.jsonl"
    _write_usage(first, session="first-session", event="first", tokens=10)
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    ingestor.refresh(
        [first],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-1",
    )
    before = load_cutover_control(paths.operational)
    assert before.active_kernel_path is not None

    _write_usage(second, session="second-session", event="second", tokens=20)
    result = ingestor.refresh(
        [first, second],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-2",
    )

    after = load_cutover_control(paths.operational)
    assert result.planner_reason == "new_source"
    assert after.active_kernel_path == before.active_kernel_path
    with sqlite3.connect(before.active_kernel_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM model_calls"
        ).fetchone()[0] == 2


def test_late_active_duplicate_uses_isolated_canonical_promotion(
    tmp_path: Path,
) -> None:
    archived = tmp_path / "archived_sessions" / "rollout-copy.jsonl"
    active = tmp_path / "sessions" / "rollout-active.jsonl"
    _write_usage(archived, session="copy-session", event="shared", tokens=10)
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    ingestor.refresh(
        [archived],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-1",
    )
    before = load_cutover_control(paths.operational)
    assert before.active_kernel_path is not None

    _write_usage(active, session="active-session", event="shared", tokens=10)
    ingestor.refresh(
        [archived, active],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-2",
    )

    after = load_cutover_control(paths.operational)
    assert after.active_kernel_path is not None
    assert after.active_kernel_path != before.active_kernel_path
    with sqlite3.connect(after.active_kernel_path) as connection:
        states = connection.execute(
            """
            SELECT sources.archive_state, model_calls.duplicate_state
            FROM model_calls
            JOIN sources USING (source_id)
            ORDER BY sources.archive_state
            """
        ).fetchall()
    assert states == [("active", "canonical"), ("archived", "copied")]


def _write_usage(
    path: Path,
    *,
    session: str,
    event: str,
    tokens: int,
    allowance_used: float | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    envelopes = [
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "session_meta",
            "payload": {"id": session},
        },
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "turn_context",
            "payload": {
                "turn_id": "turn-1",
                "model": "gpt-synthetic",
                "effort": "low",
            },
        },
        {
            "event_id": event,
            "timestamp": "2026-01-01T00:00:01Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {
                        "input_tokens": tokens,
                        "cached_input_tokens": 1,
                        "output_tokens": 2,
                        "reasoning_output_tokens": 1,
                        "total_tokens": tokens + 2,
                    }
                },
                **(
                    {
                        "rate_limits": {
                            "primary": {
                                "used_percent": allowance_used,
                                "window_minutes": 300,
                            },
                            "plan_type": "synthetic",
                            "limit_id": "synthetic-limit",
                        }
                    }
                    if allowance_used is not None
                    else {}
                ),
            },
        },
    ]
    path.write_text(
        "".join(json.dumps(envelope) + "\n" for envelope in envelopes),
        encoding="utf-8",
    )
