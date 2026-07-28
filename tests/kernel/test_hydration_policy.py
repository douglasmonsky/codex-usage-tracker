from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from codex_usage_tracker.kernel import hydration, ingest, operational
from codex_usage_tracker.kernel.hydration import (
    HydrationPreset,
    catalog_checkpoints,
    catalog_sources,
    select_hydration_sources,
)
from codex_usage_tracker.kernel.ingest import (
    KernelIngestor,
    RefreshTrigger,
    refresh_request_hash,
)
from codex_usage_tracker.kernel.operational import (
    hydrated_source_locations,
    kernel_paths,
    load_cutover_control,
    load_hydration_coverage,
    stage_hydration_catalog,
)

_AS_OF = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)


def _source(path: Path, *timestamps: str | None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for index, timestamp in enumerate(timestamps):
        timestamp_field = (
            f'"timestamp":"{timestamp}",'
            if timestamp is not None
            else ""
        )
        lines.append(
            "{"
            + timestamp_field
            + '"type":"event_msg","payload":{"type":"synthetic",'
            + f'"ordinal":{index}'
            + "}}\n"
        )
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _usage_source(
    path: Path,
    *,
    session_id: str,
    timestamp: str,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'{{"timestamp":"{timestamp}","type":"session_meta",'
        f'"payload":{{"id":"{session_id}"}}}}\n'
        f'{{"timestamp":"{timestamp}","type":"turn_context",'
        f'"payload":{{"turn_id":"turn-{session_id}",'
        '"model":"gpt-synthetic","effort":"low"}}\n'
        f'{{"event_id":"event-{session_id}","timestamp":"{timestamp}",'
        '"type":"event_msg","payload":{"type":"token_count","info":'
        '{"last_token_usage":{"input_tokens":10,"cached_input_tokens":2,'
        '"output_tokens":3,"reasoning_output_tokens":1,"total_tokens":13},'
        '"model_context_window":200000}}}\n',
        encoding="utf-8",
    )
    return path


def _token_line(event_id: str, timestamp: str) -> str:
    return (
        f'{{"event_id":"{event_id}","timestamp":"{timestamp}",'
        '"type":"event_msg","payload":{"type":"token_count","info":'
        '{"last_token_usage":{"input_tokens":10,"cached_input_tokens":2,'
        '"output_tokens":3,"reasoning_output_tokens":1,"total_tokens":13},'
        '"model_context_window":200000}}}\n'
    )


def test_recent_preset_selects_whole_recent_and_uncertain_sources(
    tmp_path: Path,
) -> None:
    old = _source(
        tmp_path / "sessions" / "old.jsonl",
        "2024-01-01T00:00:00Z",
    )
    recent = _source(
        tmp_path / "sessions" / "recent.jsonl",
        "2026-07-20T00:00:00Z",
    )
    uncertain = _source(
        tmp_path / "sessions" / "uncertain.jsonl",
        None,
    )

    catalog = catalog_sources((old, recent, uncertain))
    selection = select_hydration_sources(
        catalog,
        preset=HydrationPreset.RECENT_30D,
        captured_at=_AS_OF,
    )

    assert selection.cutoff_at.isoformat() == "2026-06-27T12:00:00+00:00"
    assert {item.path for item in selection.hydrate} == {
        recent.resolve(),
        uncertain.resolve(),
    }
    assert {item.path for item in selection.deferred} == {old.resolve()}
    assert selection.uncertain_source_count == 1
    assert selection.complete_history is False


def test_complete_preset_selects_every_source_without_a_cutoff(
    tmp_path: Path,
) -> None:
    sources = (
        _source(
            tmp_path / "sessions" / "2024.jsonl",
            "2024-01-01T00:00:00Z",
        ),
        _source(
            tmp_path / "sessions" / "2026.jsonl",
            "2026-07-20T00:00:00Z",
        ),
    )

    selection = select_hydration_sources(
        catalog_sources(sources),
        preset=HydrationPreset.COMPLETE,
        captured_at=_AS_OF,
    )

    assert selection.cutoff_at is None
    assert tuple(item.path for item in selection.hydrate) == tuple(
        source.resolve() for source in sources
    )
    assert selection.deferred == ()
    assert selection.complete_history is True


def test_unchanged_catalog_reuses_bounded_structural_timestamp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(
        tmp_path / "sessions" / "recent.jsonl",
        "2026-07-20T00:00:00Z",
    )
    first = catalog_sources((source,))

    def unexpected_tail_scan(_observation):
        raise AssertionError("unchanged source must reuse its catalog timestamp")

    monkeypatch.setattr(
        hydration,
        "_latest_structural_timestamp",
        unexpected_tail_scan,
    )
    second = catalog_sources(
        (source,),
        checkpoints=catalog_checkpoints(first),
    )

    assert second == first


def test_no_change_refresh_reuses_committed_coverage_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _usage_source(
        tmp_path / "sessions" / "unchanged.jsonl",
        session_id="unchanged",
        timestamp="2026-07-20T00:00:00Z",
    )
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="coverage-initial",
        captured_at=_AS_OF,
    )

    def unexpected_catalog_write(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("unchanged coverage must not be rewritten")

    monkeypatch.setattr(ingest, "stage_hydration_catalog", unexpected_catalog_write)
    monkeypatch.setattr(ingest, "record_hydration_catalog", unexpected_catalog_write)
    result = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="coverage-no-change",
        captured_at=_AS_OF,
    )

    assert result.planner_reason == "no_changes"
    assert result.writer_transaction_ms == ()


def test_previously_hydrated_source_stays_selected_when_window_narrows(
    tmp_path: Path,
) -> None:
    old = _source(
        tmp_path / "sessions" / "old.jsonl",
        "2024-01-01T00:00:00Z",
    )
    catalog = catalog_sources((old,))

    selection = select_hydration_sources(
        catalog,
        preset=HydrationPreset.RECENT_30D,
        captured_at=_AS_OF,
        hydrated_source_ids=frozenset({catalog[0].observation.source_id}),
    )

    assert selection.hydrate == catalog
    assert selection.deferred == ()
    assert selection.complete_history is True


def test_coverage_revision_is_stable_when_only_capture_time_moves(
    tmp_path: Path,
) -> None:
    source = _usage_source(
        tmp_path / "sessions" / "recent.jsonl",
        session_id="recent",
        timestamp="2026-07-20T00:00:00Z",
    )
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)

    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-first-capture",
        hydration_preset=HydrationPreset.RECENT_30D,
        captured_at=_AS_OF,
    )
    first = load_hydration_coverage(paths.operational)
    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-next-capture",
        hydration_preset=HydrationPreset.RECENT_30D,
        captured_at=datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc),
    )
    second = load_hydration_coverage(paths.operational)

    assert second["captured_at"] != first["captured_at"]
    assert second["coverage_revision"] == first["coverage_revision"]


def test_staged_catalog_exposes_hydrating_without_replacing_active_coverage(
    tmp_path: Path,
) -> None:
    old = _source(
        tmp_path / "sessions" / "old.jsonl",
        "2024-01-01T00:00:00Z",
    )
    recent = _source(
        tmp_path / "sessions" / "recent.jsonl",
        "2026-07-20T00:00:00Z",
    )
    paths = kernel_paths(tmp_path / "cache")
    operational.initialize_operational_database(paths.operational)
    selection = select_hydration_sources(
        catalog_sources((old, recent)),
        preset=HydrationPreset.RECENT_30D,
        captured_at=_AS_OF,
    )

    stage_hydration_catalog(paths.operational, selection)

    with sqlite3.connect(paths.operational) as connection:
        states = dict(
            connection.execute(
                "SELECT source_location, hydration_state FROM source_registry"
            )
        )
    assert states[str(old.resolve())] == "deferred"
    assert states[str(recent.resolve())] == "hydrating"
    assert load_hydration_coverage(paths.operational)["preset"] is None


def test_replaced_hydrated_path_stays_selected_under_recent_policy(
    tmp_path: Path,
) -> None:
    source = _usage_source(
        tmp_path / "sessions" / "source.jsonl",
        session_id="first",
        timestamp="2026-07-20T00:00:00Z",
    )
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-original",
        hydration_preset=HydrationPreset.RECENT_30D,
        captured_at=_AS_OF,
    )
    replacement = tmp_path / "replacement.jsonl"
    _usage_source(
        replacement,
        session_id="replacement",
        timestamp="2024-01-01T00:00:00Z",
    )
    replacement.replace(source)

    result = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-replacement",
        hydration_preset=HydrationPreset.RECENT_30D,
        captured_at=_AS_OF,
    )

    assert result.changed_sources == 1
    assert source.resolve() in hydrated_source_locations(paths.operational)
    with sqlite3.connect(paths.analytical) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM model_calls"
        ).fetchone()[0] == 1


def test_recent_append_makes_a_deferred_whole_source_eligible(
    tmp_path: Path,
) -> None:
    source = _source(
        tmp_path / "sessions" / "old-with-tail.jsonl",
        "2024-01-01T00:00:00Z",
    )
    first = select_hydration_sources(
        catalog_sources((source,)),
        preset=HydrationPreset.RECENT_30D,
        captured_at=_AS_OF,
    )
    with source.open("a", encoding="utf-8") as handle:
        handle.write(
            '{"timestamp":"2026-07-27T11:59:00Z","type":"event_msg",'
            '"payload":{"type":"synthetic","ordinal":1}}\n'
        )
    second = select_hydration_sources(
        catalog_sources((source,)),
        preset=HydrationPreset.RECENT_30D,
        captured_at=_AS_OF,
    )

    assert first.hydrate == ()
    assert tuple(item.path for item in first.deferred) == (source.resolve(),)
    assert tuple(item.path for item in second.hydrate) == (source.resolve(),)
    assert second.hydrate[0].observation.complete_size == source.stat().st_size


def test_refresh_identity_includes_deferred_catalog_and_preset(
    tmp_path: Path,
) -> None:
    old = _source(
        tmp_path / "sessions" / "old.jsonl",
        "2024-01-01T00:00:00Z",
    )
    recent = _source(
        tmp_path / "sessions" / "recent.jsonl",
        "2026-07-20T00:00:00Z",
    )
    first = refresh_request_hash(
        [old, recent],
        hydration_preset=HydrationPreset.RECENT_30D,
    )
    complete = refresh_request_hash(
        [old, recent],
        hydration_preset=HydrationPreset.COMPLETE,
    )
    with old.open("a", encoding="utf-8") as handle:
        handle.write(
            '{"timestamp":"2024-01-02T00:00:00Z","type":"event_msg",'
            '"payload":{"type":"synthetic","ordinal":1}}\n'
        )
    changed_deferred = refresh_request_hash(
        [old, recent],
        hydration_preset=HydrationPreset.RECENT_30D,
    )

    assert complete != first
    assert changed_deferred != first


def test_recent_preset_publishes_truthful_empty_generation_when_all_old(
    tmp_path: Path,
) -> None:
    old = _usage_source(
        tmp_path / "sessions" / "old.jsonl",
        session_id="old",
        timestamp="2024-01-01T00:00:00Z",
    )
    paths = kernel_paths(tmp_path / "cache")

    result = KernelIngestor(
        paths.analytical,
        paths.operational,
    ).refresh(
        [old],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-empty-partial",
        hydration_preset=HydrationPreset.RECENT_30D,
        captured_at=_AS_OF,
    )

    assert result.generation == 1
    assert result.inserted_calls == 0
    coverage = load_hydration_coverage(paths.operational)
    assert coverage["hydrated_source_count"] == 0
    assert coverage["deferred_source_count"] == 1
    assert coverage["complete_history"] is False
    with sqlite3.connect(paths.analytical) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM model_calls"
        ).fetchone()[0] == 0


def test_explicit_coverage_expansion_is_monotonic_and_deduplicated(
    tmp_path: Path,
) -> None:
    sources = [
        _usage_source(
            tmp_path / "sessions" / "old.jsonl",
            session_id="old",
            timestamp="2024-01-01T00:00:00Z",
        ),
        _usage_source(
            tmp_path / "sessions" / "mid.jsonl",
            session_id="mid",
            timestamp="2026-05-15T00:00:00Z",
        ),
        _usage_source(
            tmp_path / "sessions" / "recent.jsonl",
            session_id="recent",
            timestamp="2026-07-20T00:00:00Z",
        ),
    ]
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)

    recent = ingestor.refresh(
        sources,
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-recent",
        hydration_preset=HydrationPreset.RECENT_30D,
        captured_at=_AS_OF,
    )
    recent_coverage = load_hydration_coverage(paths.operational)
    broader = ingestor.refresh(
        sources,
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-broader",
        hydration_preset=HydrationPreset.RECENT_90D,
        captured_at=_AS_OF,
    )
    complete = ingestor.refresh(
        sources,
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-complete",
        hydration_preset=HydrationPreset.COMPLETE,
        captured_at=_AS_OF,
    )
    narrowed = ingestor.refresh(
        sources,
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-narrowed",
        hydration_preset=HydrationPreset.RECENT_30D,
        captured_at=_AS_OF,
    )
    final_coverage = load_hydration_coverage(paths.operational)

    assert recent.inserted_calls == 1
    assert recent_coverage["hydrated_source_count"] == 1
    assert recent_coverage["deferred_source_count"] == 2
    assert broader.inserted_calls == 1
    assert complete.inserted_calls == 1
    assert narrowed.planner_reason == "no_changes"
    assert narrowed.generation == complete.generation
    assert final_coverage["complete_history"] is True
    assert final_coverage["hydrated_source_count"] == 3
    assert final_coverage["deferred_source_count"] == 0
    with sqlite3.connect(paths.analytical) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM model_calls"
        ).fetchone()[0] == 3


def test_failed_bulk_expansion_keeps_prior_generation_and_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recent = _usage_source(
        tmp_path / "sessions" / "recent.jsonl",
        session_id="recent",
        timestamp="2026-07-20T00:00:00Z",
    )
    older = [
        _usage_source(
            tmp_path / "sessions" / f"older-{index}.jsonl",
            session_id=f"older-{index}",
            timestamp="2026-05-15T00:00:00Z",
        )
        for index in range(8)
    ]
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    first = ingestor.refresh(
        [recent, *older],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-before-bulk",
        hydration_preset=HydrationPreset.RECENT_30D,
        captured_at=_AS_OF,
    )
    prior_control = load_cutover_control(paths.operational)
    prior_coverage = load_hydration_coverage(paths.operational)

    def fail_promotion(*_args, **_kwargs):
        raise RuntimeError("synthetic bulk promotion failure")

    monkeypatch.setattr(ingestor, "_promote", fail_promotion)
    with pytest.raises(
        RuntimeError,
        match="synthetic bulk promotion failure",
    ):
        ingestor.refresh(
            [recent, *older],
            trigger=RefreshTrigger.CLI_REFRESH,
            owner_id="owner-failed-bulk",
            hydration_preset=HydrationPreset.RECENT_90D,
            captured_at=_AS_OF,
        )

    failed = load_cutover_control(paths.operational)
    assert first.generation == 1
    assert failed.active_generation == 1
    assert failed.active_kernel_path == prior_control.active_kernel_path
    assert load_hydration_coverage(paths.operational) == prior_coverage
    with sqlite3.connect(paths.operational) as connection:
        assert connection.execute(
            """
            SELECT COUNT(*) FROM source_registry
            WHERE hydration_state = 'hydrating'
            """
        ).fetchone()[0] == 0
    with sqlite3.connect(prior_control.active_kernel_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM model_calls"
        ).fetchone()[0] == 1


def test_large_expansion_with_concurrent_tail_uses_isolated_bulk_clone(
    tmp_path: Path,
) -> None:
    recent = _usage_source(
        tmp_path / "sessions" / "recent.jsonl",
        session_id="recent",
        timestamp="2026-07-20T00:00:00Z",
    )
    older = [
        _usage_source(
            tmp_path / "sessions" / f"older-{index}.jsonl",
            session_id=f"older-{index}",
            timestamp="2026-05-15T00:00:00Z",
        )
        for index in range(8)
    ]
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    ingestor.refresh(
        [recent, *older],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-before-mixed",
        hydration_preset=HydrationPreset.RECENT_30D,
        captured_at=_AS_OF,
    )
    prior_path = load_cutover_control(paths.operational).active_kernel_path
    with recent.open("a", encoding="utf-8") as handle:
        handle.write(
            _token_line(
                "event-recent-tail",
                "2026-07-27T11:59:00Z",
            )
        )

    result = ingestor.refresh(
        [recent, *older],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-mixed-expansion",
        hydration_preset=HydrationPreset.RECENT_90D,
        captured_at=_AS_OF,
    )
    control = load_cutover_control(paths.operational)

    assert result.inserted_calls == 9
    assert control.active_kernel_path != prior_path
    with sqlite3.connect(control.active_kernel_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM model_calls"
        ).fetchone()[0] == 10


def test_cross_preset_retry_does_not_publish_stale_partial_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recent = _usage_source(
        tmp_path / "sessions" / "recent.jsonl",
        session_id="recent",
        timestamp="2026-07-20T00:00:00Z",
    )
    old = _usage_source(
        tmp_path / "sessions" / "old.jsonl",
        session_id="old",
        timestamp="2024-01-01T00:00:00Z",
    )
    paths = kernel_paths(tmp_path / "cache")
    interrupted = KernelIngestor(paths.analytical, paths.operational)
    monkeypatch.setattr(
        interrupted,
        "_promote",
        lambda *_args, **_kwargs: None,
    )
    interrupted.refresh(
        [recent, old],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-interrupted-recent",
        hydration_preset=HydrationPreset.RECENT_30D,
        captured_at=_AS_OF,
    )

    completed = KernelIngestor(
        paths.analytical,
        paths.operational,
    ).refresh(
        [recent, old],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-retry-complete",
        hydration_preset=HydrationPreset.COMPLETE,
        captured_at=_AS_OF,
    )
    coverage = load_hydration_coverage(paths.operational)

    assert completed.generation == 1
    assert coverage["preset"] == "complete"
    assert coverage["complete_history"] is True
    assert coverage["hydrated_source_count"] == 2
    with sqlite3.connect(paths.analytical) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM model_calls"
        ).fetchone()[0] == 2


def test_incomplete_bulk_artifact_is_abandoned_and_rebuilt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recent = _usage_source(
        tmp_path / "sessions" / "recent.jsonl",
        session_id="recent",
        timestamp="2026-07-20T00:00:00Z",
    )
    older = [
        _usage_source(
            tmp_path / "sessions" / f"older-{index}.jsonl",
            session_id=f"older-{index}",
            timestamp="2026-05-15T00:00:00Z",
        )
        for index in range(8)
    ]
    paths = kernel_paths(tmp_path / "cache")
    interrupted = KernelIngestor(paths.analytical, paths.operational)
    interrupted.refresh(
        [recent, *older],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-before-incomplete",
        hydration_preset=HydrationPreset.RECENT_30D,
        captured_at=_AS_OF,
    )
    real_commit = interrupted._commit_initial_stream

    def fail_after_index_removal(path, *_args, **_kwargs):
        ingest.prepare_initial_refresh(path, [])
        raise RuntimeError("synthetic interrupted bulk stream")

    monkeypatch.setattr(
        interrupted,
        "_commit_initial_stream",
        fail_after_index_removal,
    )
    with pytest.raises(
        RuntimeError,
        match="synthetic interrupted bulk stream",
    ):
        interrupted.refresh(
            [recent, *older],
            trigger=RefreshTrigger.CLI_REFRESH,
            owner_id="owner-incomplete-bulk",
            hydration_preset=HydrationPreset.RECENT_90D,
            captured_at=_AS_OF,
        )
    monkeypatch.setattr(
        interrupted,
        "_commit_initial_stream",
        real_commit,
    )

    recovered = interrupted.refresh(
        [recent, *older],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-rebuild-bulk",
        hydration_preset=HydrationPreset.RECENT_90D,
        captured_at=_AS_OF,
    )

    assert recovered.generation == 2
    assert load_hydration_coverage(paths.operational)["complete_history"] is True


def test_deferred_source_with_recent_append_joins_the_active_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = _usage_source(
        tmp_path / "sessions" / "old.jsonl",
        session_id="old",
        timestamp="2024-01-01T00:00:00Z",
    )
    recent = _usage_source(
        tmp_path / "sessions" / "recent.jsonl",
        session_id="recent",
        timestamp="2026-07-20T00:00:00Z",
    )
    paths = kernel_paths(tmp_path / "cache")
    real_batches = ingest.iter_jsonl_batches
    appended = False

    def append_to_deferred_after_selected_parse(
        plan,
        prior_state=None,
        *,
        max_lines=1000,
    ):
        nonlocal appended
        yield from real_batches(plan, prior_state, max_lines=max_lines)
        if not appended:
            with old.open("a", encoding="utf-8") as handle:
                handle.write(
                    _token_line(
                        "event-old-recent-tail",
                        "2026-07-27T11:59:00Z",
                    )
                )
            appended = True

    monkeypatch.setattr(
        ingest,
        "iter_jsonl_batches",
        append_to_deferred_after_selected_parse,
    )
    result = KernelIngestor(paths.analytical, paths.operational).refresh(
        [old, recent],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-moving-deferred",
        hydration_preset=HydrationPreset.RECENT_30D,
        captured_at=_AS_OF,
    )
    coverage = load_hydration_coverage(paths.operational)

    assert result.inserted_calls == 3
    assert coverage["hydrated_source_count"] == 2
    assert coverage["deferred_source_count"] == 0
    assert coverage["complete_history"] is True


def test_coverage_publication_failure_does_not_activate_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _usage_source(
        tmp_path / "sessions" / "recent.jsonl",
        session_id="recent",
        timestamp="2026-07-20T00:00:00Z",
    )
    paths = kernel_paths(tmp_path / "cache")

    def fail_coverage(*_args, **_kwargs):
        raise RuntimeError("synthetic coverage publication failure")

    monkeypatch.setattr(
        operational,
        "_record_hydration_catalog_in_connection",
        fail_coverage,
    )
    with pytest.raises(
        RuntimeError,
        match="synthetic coverage publication failure",
    ):
        KernelIngestor(paths.analytical, paths.operational).refresh(
            [source],
            trigger=RefreshTrigger.CLI_REFRESH,
            owner_id="owner-coverage-failure",
            hydration_preset=HydrationPreset.RECENT_30D,
            captured_at=_AS_OF,
        )

    control = load_cutover_control(paths.operational)
    assert control.active_generation is None
    assert control.state.value == "failed"
