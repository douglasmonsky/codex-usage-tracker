"""R4 coverage-aware interface contracts."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from codex_usage_tracker.kernel.application import (
    KernelApplication,
    RuntimePaths,
    build_application,
)
from codex_usage_tracker.kernel.application import service as application_service
from codex_usage_tracker.kernel.hydration import HydrationPreset
from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger

from .support import active_runtime


def test_status_and_query_expose_committed_history_coverage(tmp_path: Path) -> None:
    runtime = active_runtime(tmp_path)
    application = KernelApplication(
        runtime,
        worker_launcher=lambda _paths, _preset: None,
    )

    status = application.status()
    query = application.query(
        {
            "requests": [
                {
                    "dataset": "calls",
                    "operation": "aggregate",
                    "dimensions": ["thread"],
                    "measures": [
                        "uncached_input_tokens",
                        "cached_input_tokens",
                        "reasoning_tokens",
                        "output_tokens",
                    ],
                    "limit": 10,
                }
            ]
        }
    )

    expected = {
        "preset": "complete",
        "cutoff_at": None,
        "complete_history": True,
        "cataloged_source_count": 3,
        "hydrated_source_count": 3,
        "deferred_source_count": 0,
    }
    assert status["history_coverage"] | expected == status["history_coverage"]
    assert (
        query["history_coverage"]["coverage_revision"]
        == status["history_coverage"]["coverage_revision"]
    )
    assert query["history_coverage"] | expected == query["history_coverage"]


def test_status_reads_pre_coverage_sidecar_conservatively_without_migration(
    tmp_path: Path,
) -> None:
    runtime = active_runtime(tmp_path)
    with sqlite3.connect(runtime.kernel.operational) as connection:
        connection.execute("DROP TABLE coverage_control")
        connection.execute("DROP TABLE staged_coverage_control")
        connection.execute("PRAGMA user_version = 2")
    before = runtime.kernel.operational.read_bytes()

    status = KernelApplication(
        runtime,
        worker_launcher=lambda _paths, _preset: None,
    ).status()

    assert status["state"] == "active"
    assert status["generation"] == 1
    assert status["history_coverage"]["complete_history"] is False
    assert status["history_coverage"]["coverage_revision"] is None
    assert runtime.kernel.operational.read_bytes() == before


def test_partial_history_requires_explicit_query_opt_in(tmp_path: Path) -> None:
    runtime = _partial_runtime(tmp_path)
    application = KernelApplication(
        runtime,
        worker_launcher=lambda _paths, _preset: None,
    )
    request = {
        "dataset": "calls",
        "operation": "aggregate",
        "dimensions": ["thread"],
        "measures": ["calls", "total_tokens"],
        "limit": 10,
    }

    with pytest.raises(ValueError, match="allow_partial"):
        application.query({"requests": [request]})

    accepted = application.query({"requests": [{**request, "allow_partial": True}]})

    assert accepted["history_coverage"]["complete_history"] is False
    assert accepted["results"][0]["grade"] == "partial"
    assert accepted["results"][0]["coverage"]["history_complete"] is False


def test_query_never_launches_refresh_for_partial_history(tmp_path: Path) -> None:
    launches: list[tuple[RuntimePaths, HydrationPreset]] = []
    application = KernelApplication(
        _partial_runtime(tmp_path),
        worker_launcher=lambda paths, preset: launches.append((paths, preset)),
    )

    with pytest.raises(ValueError, match="allow_partial"):
        application.query(
            {
                "requests": [
                    {
                        "dataset": "calls",
                        "operation": "aggregate",
                        "dimensions": ["thread"],
                        "measures": ["calls"],
                    }
                ]
            }
        )

    assert launches == []


def test_query_binds_generation_and_coverage_to_one_publication_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _partial_runtime(tmp_path)
    application = KernelApplication(
        runtime,
        worker_launcher=lambda _paths, _preset: None,
    )
    real_snapshot = application_service.load_publication_snapshot
    promoted = False

    def promote_after_snapshot(path: Path):
        nonlocal promoted
        snapshot = real_snapshot(path)
        if not promoted:
            promoted = True
            KernelIngestor(
                runtime.kernel.analytical,
                runtime.kernel.operational,
            ).refresh(
                [
                    runtime.codex_home / "sessions" / "recent.jsonl",
                    runtime.codex_home / "archived_sessions" / "old.jsonl",
                ],
                trigger=RefreshTrigger.CLI_REFRESH,
                owner_id="r4-publication-interleave",
                hydration_preset=HydrationPreset.COMPLETE,
            )
        return snapshot

    monkeypatch.setattr(
        application_service,
        "load_publication_snapshot",
        promote_after_snapshot,
    )
    with pytest.raises(ValueError, match="allow_partial"):
        application.query(
            {
                "requests": [
                    {
                        "dataset": "calls",
                        "operation": "aggregate",
                        "dimensions": ["thread"],
                        "measures": ["calls"],
                    }
                ]
            }
        )
    assert real_snapshot(runtime.kernel.operational)[1]["complete_history"] is True


def test_partial_history_comparisons_must_stay_inside_coverage(
    tmp_path: Path,
) -> None:
    application = KernelApplication(
        _partial_runtime(tmp_path),
        worker_launcher=lambda _paths, _preset: None,
    )
    base = {
        "dataset": "calls",
        "operation": "comparison",
        "dimensions": ["model"],
        "measures": ["calls", "total_tokens"],
        "limit": 10,
    }

    covered = application.query(
        {
            "requests": [
                {
                    **base,
                    "comparison": {
                        "current_start": "2026-07-25T00:00:00Z",
                        "current_end": "2026-07-27T00:00:00Z",
                        "previous_start": "2026-07-23T00:00:00Z",
                        "previous_end": "2026-07-25T00:00:00Z",
                    },
                }
            ]
        }
    )
    with pytest.raises(ValueError, match="allow_partial"):
        application.query(
            {
                "requests": [
                    {
                        **base,
                        "comparison": {
                            "current_start": "2026-01-03T00:00:00Z",
                            "current_end": "2026-01-04T00:00:00Z",
                            "previous_start": "2026-01-01T00:00:00Z",
                            "previous_end": "2026-01-02T00:00:00Z",
                        },
                    }
                ]
            }
        )

    assert covered["results"][0]["grade"] == "exact"


def test_repeated_query_reports_generation_safe_cache_reuse(tmp_path: Path) -> None:
    application = KernelApplication(
        active_runtime(tmp_path),
        worker_launcher=lambda _paths, _preset: None,
    )
    payload = {
        "requests": [
            {
                "dataset": "calls",
                "operation": "aggregate",
                "dimensions": ["thread"],
                "measures": ["calls", "total_tokens"],
            }
        ]
    }

    first = application.query(payload)
    second = application.query(payload)

    assert first["cache"]["hit"] is False
    assert second["cache"]["hit"] is True
    assert first["cache"]["key"] == second["cache"]["key"]
    assert first["results"] == second["results"]


def test_query_cache_invalidates_when_coverage_generation_changes(
    tmp_path: Path,
) -> None:
    runtime = _partial_runtime(tmp_path)
    application = KernelApplication(
        runtime,
        worker_launcher=lambda _paths, _preset: None,
    )
    payload = {
        "requests": [
            {
                "dataset": "calls",
                "operation": "aggregate",
                "dimensions": ["thread"],
                "measures": ["calls"],
                "allow_partial": True,
            }
        ]
    }

    first = application.query(payload)
    assert application.query(payload)["cache"]["hit"] is True
    KernelIngestor(
        runtime.kernel.analytical,
        runtime.kernel.operational,
    ).refresh(
        [
            runtime.codex_home / "sessions" / "recent.jsonl",
            runtime.codex_home / "archived_sessions" / "old.jsonl",
        ],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r4-cache-invalidation",
        hydration_preset=HydrationPreset.COMPLETE,
    )
    after_expansion = application.query(payload)

    assert after_expansion["cache"]["hit"] is False
    assert after_expansion["cache"]["key"] != first["cache"]["key"]
    assert after_expansion["history_coverage"]["complete_history"] is True


def test_new_install_defaults_recent_then_retains_explicit_complete(
    tmp_path: Path,
) -> None:
    runtime = RuntimePaths(tmp_path / "codex-home", tmp_path / "cache")
    _write_source(
        runtime.codex_home / "sessions" / "recent.jsonl",
        thread_id="recent-thread",
        timestamp="2026-07-26T00:00:00Z",
    )
    _write_source(
        runtime.codex_home / "archived_sessions" / "old.jsonl",
        thread_id="old-thread",
        timestamp="2025-01-01T00:00:00Z",
    )
    application = build_application(runtime)

    first = application.refresh(wait_seconds=30)
    recent = application.status()["history_coverage"]
    expanded = application.refresh(
        wait_seconds=30,
        hydration_preset=HydrationPreset.COMPLETE,
    )
    complete = application.status()["history_coverage"]
    retained = application.refresh(wait_seconds=30)

    assert first["job"]["state"] == "completed"
    assert recent["preset"] == "recent_30d"
    assert recent["hydrated_source_count"] == 1
    assert recent["deferred_source_count"] == 1
    assert expanded["job"]["state"] == "completed"
    assert complete["preset"] == "complete"
    assert complete["complete_history"] is True
    assert retained["job"]["result"]["planner_reason"] == "no_changes"
    assert application.status()["history_coverage"]["preset"] == "complete"


def test_refresh_transports_requested_hydration_preset(tmp_path: Path) -> None:
    runtime = RuntimePaths(tmp_path / "codex-home", tmp_path / "cache")
    runtime.codex_home.mkdir(parents=True)
    launches: list[tuple[RuntimePaths, HydrationPreset]] = []

    application = KernelApplication(
        runtime,
        worker_launcher=lambda paths, preset: launches.append((paths, preset)),
        source_provider=lambda _home: (),
    )

    with pytest.raises(RuntimeError, match="did not start"):
        application.refresh(
            wait_seconds=0,
            hydration_preset=HydrationPreset.RECENT_30D,
        )

    assert launches == [(runtime, HydrationPreset.RECENT_30D)]


def _partial_runtime(root: Path) -> RuntimePaths:
    runtime = RuntimePaths(root / "codex-home", root / "cache")
    recent = runtime.codex_home / "sessions" / "recent.jsonl"
    old = runtime.codex_home / "archived_sessions" / "old.jsonl"
    _write_source(recent, thread_id="recent-thread", timestamp="2026-07-26T00:00:00Z")
    _write_source(old, thread_id="old-thread", timestamp="2025-01-01T00:00:00Z")
    KernelIngestor(
        runtime.kernel.analytical,
        runtime.kernel.operational,
    ).refresh(
        [recent, old],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="r4-coverage-contract",
        hydration_preset=HydrationPreset.RECENT_30D,
    )
    return runtime


def _write_source(path: Path, *, thread_id: str, timestamp: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'{{"timestamp":"{timestamp}","type":"session_meta",'
        f'"payload":{{"id":"{thread_id}"}}}}\n'
        f'{{"timestamp":"{timestamp}","type":"turn_context",'
        f'"payload":{{"turn_id":"turn-1","model":"gpt-synthetic",'
        '"effort":"low"}}}\n'
        f'{{"event_id":"event-1","timestamp":"{timestamp}",'
        '"type":"event_msg","payload":{"type":"token_count","info":'
        '{"last_token_usage":{"input_tokens":10,"cached_input_tokens":2,'
        '"output_tokens":3,"reasoning_output_tokens":1,"total_tokens":13},'
        '"model_context_window":200000}}}\n',
        encoding="utf-8",
    )
