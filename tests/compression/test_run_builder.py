from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.compression import run_builder
from codex_usage_tracker.compression.context_detectors import StaleContextDetector
from codex_usage_tracker.compression.models import CompressionScope
from codex_usage_tracker.compression.run_cache import record_manifest
from codex_usage_tracker.store.compression_candidates import list_compression_candidates
from codex_usage_tracker.store.compression_runs import get_compression_run
from codex_usage_tracker.store.compression_schema import touch_compression_source_generation
from codex_usage_tracker.store.connection import connect
from tests.compression.compression_helpers import call, snapshot, tool


def _stale_snapshot(*record_ids: str, source_revision: str = "revision-1"):
    evidence = snapshot(
        calls=tuple(
            call(
                record_id,
                thread=record_id.split("-")[0],
                uncached=25_000,
                output=100,
                context_percent=0.8,
                index=index,
            )
            for index, record_id in enumerate(record_ids, start=1)
        )
    )
    return replace(evidence, source_revision=source_revision)


def _use_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    evidence: Any,
) -> None:
    monkeypatch.setattr(
        run_builder,
        "load_compression_evidence",
        lambda _db_path, _scope: evidence,
    )


def test_build_compression_run_persists_profile_candidates_and_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _use_snapshot(monkeypatch, _stale_snapshot("thread-a-1"))
    progress: list[dict[str, Any]] = []

    profile = run_builder.build_compression_run(
        db_path,
        CompressionScope(),
        progress_callback=progress.append,
        detector_families=("stale_context",),
    )

    assert profile["status"] == "completed"
    assert profile["candidate_count"] == 1
    assert profile["portfolio_estimate"]["likely"] > 0
    assert profile["cache"] == {"mode": "cold", "reused": False}
    assert progress[-1]["stage"] == "complete"
    assert progress[-1]["progress_percent"] == 100.0
    assert [row["progress_percent"] for row in progress] == sorted(
        row["progress_percent"] for row in progress
    )
    stored = get_compression_run(db_path, run_id=profile["run_id"])
    assert stored is not None
    assert stored["candidate_count"] == 1
    page = list_compression_candidates(db_path, run_id=profile["run_id"])
    assert page["total"] == 1


def test_build_compression_run_reuses_an_exact_persisted_cache_hit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _use_snapshot(monkeypatch, _stale_snapshot("thread-a-1"))

    cold = run_builder.build_compression_run(
        db_path,
        CompressionScope(),
        detector_families=("stale_context",),
    )

    def unexpected_evidence_load(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("exact cache hits must not rebuild normalized evidence")

    monkeypatch.setattr(run_builder, "load_compression_evidence", unexpected_evidence_load)
    warm = run_builder.build_compression_run(
        db_path,
        CompressionScope(),
        detector_families=("stale_context",),
    )

    assert warm["run_id"] == cold["run_id"]
    assert warm["cache"] == {"mode": "exact", "reused": True}


def test_forced_rebuild_atomically_supersedes_the_exact_cached_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _use_snapshot(monkeypatch, _stale_snapshot("thread-a-1"))
    first = run_builder.build_compression_run(
        db_path,
        CompressionScope(),
        detector_families=("stale_context",),
    )

    rebuilt = run_builder.build_compression_run(
        db_path,
        CompressionScope(),
        detector_families=("stale_context",),
        force=True,
    )

    assert rebuilt["run_id"] != first["run_id"]
    assert rebuilt["candidate_count"] == 1
    assert get_compression_run(db_path, run_id=first["run_id"]) is None


def test_build_compression_run_completes_with_structured_partial_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingDetector:
        family = "broken"
        version = "broken-v1"

        def detect(self, _snapshot: Any, _scope: CompressionScope):
            raise RuntimeError("private detector detail")

    db_path = tmp_path / "usage.sqlite3"
    _use_snapshot(monkeypatch, _stale_snapshot("thread-a-1"))
    monkeypatch.setattr(
        run_builder,
        "select_detectors",
        lambda _families: (FailingDetector(), StaleContextDetector()),
    )

    profile = run_builder.build_compression_run(db_path, CompressionScope())

    assert profile["status"] == "completed_with_warnings"
    assert profile["candidate_count"] == 1
    assert profile["warnings"][0]["family"] == "broken"
    assert profile["warnings"][0]["code"] == "detector_failed"
    assert "private detector detail" not in json.dumps(profile)


def test_build_compression_run_completes_with_zero_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _use_snapshot(monkeypatch, snapshot(calls=(call("ordinary"),)))

    profile = run_builder.build_compression_run(
        db_path,
        CompressionScope(),
        detector_families=("stale_context",),
    )

    assert profile["status"] == "completed"
    assert profile["candidate_count"] == 0
    assert profile["portfolio_estimate"] == {"low": 0, "likely": 0, "high": 0}


def test_record_manifest_is_stable_when_event_order_changes() -> None:
    first_tool = tool("tool-1", "call-1", output_bytes=100)
    second_tool = tool("tool-2", "call-1", output_bytes=200)
    forward = snapshot(
        calls=(call("call-1"),),
        tools=(first_tool, second_tool),
    )
    reversed_rows = snapshot(
        calls=(call("call-1"),),
        tools=(second_tool, first_tool),
    )

    assert record_manifest(forward) == record_manifest(reversed_rows)

    changed = snapshot(
        calls=(call("call-1"),),
        tools=(first_tool, tool("tool-2", "call-1", output_bytes=201)),
    )
    assert record_manifest(forward) != record_manifest(changed)


def test_appended_record_recomputes_only_its_affected_thread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _stale_snapshot("a-1", "b-1", source_revision="revision-1")
    second = _stale_snapshot("a-1", "b-1", "a-2", source_revision="revision-2")
    snapshots = iter((first, second))
    db_path = tmp_path / "usage.sqlite3"
    monkeypatch.setattr(
        run_builder,
        "load_compression_evidence",
        lambda _db_path, _scope: next(snapshots),
    )
    observed_scopes: list[set[str]] = []

    class RecordingDetector(StaleContextDetector):
        def detect(self, evidence: Any, scope: CompressionScope):
            observed_scopes.append({row.record_id for row in evidence.calls})
            return super().detect(evidence, scope)

    detector = RecordingDetector()
    monkeypatch.setattr(
        run_builder,
        "select_detectors",
        lambda _families: (detector,),
    )

    cold = run_builder.build_compression_run(db_path, CompressionScope())
    with connect(db_path) as conn:
        touch_compression_source_generation(conn)
    incremental = run_builder.build_compression_run(db_path, CompressionScope())

    assert cold["candidate_count"] == 2
    assert incremental["candidate_count"] == 3
    assert incremental["cache"] == {"mode": "incremental", "reused": True}
    assert observed_scopes == [{"a-1", "b-1"}, {"a-1", "a-2"}]
