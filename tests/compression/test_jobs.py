from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.compression import run_builder
from codex_usage_tracker.compression.api import compression_status
from codex_usage_tracker.compression.jobs import CompressionJobRegistry
from codex_usage_tracker.compression.models import CompressionScope
from codex_usage_tracker.compression.request import prepare_compression_request
from codex_usage_tracker.compression.run_cache import record_manifest
from codex_usage_tracker.compression.streaming_evidence import StreamingEvidenceBundle
from codex_usage_tracker.store.compression_candidates import list_compression_candidates
from codex_usage_tracker.store.compression_runs import (
    create_compression_run,
    get_compression_run,
    update_compression_run,
)
from tests.compression.compression_helpers import call, snapshot


def test_status_missing_database_returns_not_found_payload(tmp_path: Path) -> None:
    db_path = tmp_path / "missing.sqlite3"

    payload = compression_status(
        db_path,
        run_id="missing-run",
        registry=CompressionJobRegistry(),
    )

    error = payload["error"]
    assert isinstance(error, dict)
    assert error["code"] == "compression_run_not_found"
    assert not db_path.exists()


def test_start_returns_immediately_and_deduplicates_active_request(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    started = threading.Event()
    release = threading.Event()

    def blocking_builder(
        path: Path,
        _scope: CompressionScope,
        **kwargs: Any,
    ) -> dict[str, Any]:
        run_id = str(kwargs["reserved_run_id"])
        started.set()
        assert release.wait(timeout=5)
        update_compression_run(
            path,
            run_id=run_id,
            status="completed",
            stage="complete",
            progress_percent=100,
            public_profile={"run_id": run_id, "status": "completed"},
        )
        return {"run_id": run_id, "status": "completed"}

    registry = CompressionJobRegistry(builder=blocking_builder)
    began = time.perf_counter()
    first = registry.start(
        db_path,
        CompressionScope(),
        detector_families=("stale_context",),
    )

    assert time.perf_counter() - began < 0.5
    assert started.wait(timeout=1)
    duplicate = registry.start(
        db_path,
        CompressionScope(),
        detector_families=("stale_context",),
        force=True,
    )
    assert duplicate["run_id"] == first["run_id"]
    assert duplicate["request_reused"] == "active"

    release.set()
    terminal = _wait_for_terminal(registry, db_path, str(first["run_id"]))
    assert terminal["status"] == "completed"
    assert terminal["progress_percent"] == 100


def test_start_reuses_exact_completed_profile_without_launching_worker(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    scope = CompressionScope()
    request = prepare_compression_request(
        db_path,
        scope,
        detector_families=("stale_context",),
    )
    create_compression_run(
        db_path,
        run_id="completed-run",
        source_revision="source-revision",
        scope_hash=request.scope_hash,
        detector_set_version=request.detector_set_version,
        estimator_version=request.estimator_version,
        compression_schema_version=request.compression_schema_version,
        source_generation=request.source_generation,
        revision_key=request.revision_key,
        scope=scope.as_dict(),
    )
    update_compression_run(
        db_path,
        run_id="completed-run",
        status="completed",
        progress_percent=100,
        stage="complete",
        public_profile={"run_id": "completed-run", "status": "completed"},
    )

    def unexpected_builder(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("completed cache reuse must not launch a worker")

    began = time.perf_counter()
    handle = CompressionJobRegistry(builder=unexpected_builder).start(
        db_path,
        scope,
        detector_families=("stale_context",),
    )

    assert handle["run_id"] == "completed-run"
    assert handle["status"] == "completed"
    assert handle["request_reused"] == "completed"
    assert time.perf_counter() - began < 0.5


def test_status_reports_unowned_active_run_as_interrupted(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    create_compression_run(
        db_path,
        run_id="orphaned-run",
        source_revision="source-revision",
        scope_hash="scope",
        detector_set_version="detectors",
        estimator_version="estimator",
        compression_schema_version=1,
        scope={},
        status="running",
    )

    status = CompressionJobRegistry().status(db_path, "orphaned-run")

    assert status is not None
    assert status["status"] == "interrupted"
    assert status["persisted_status"] == "running"
    assert status["error_summary"] == {"code": "compression_worker_not_owned"}
    persisted = get_compression_run(db_path, run_id="orphaned-run")
    assert persisted is not None
    assert persisted["status"] == "running"


def test_owned_status_poll_does_not_wait_for_an_active_writer(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    started = threading.Event()
    release = threading.Event()

    def blocking_builder(
        _path: Path,
        _scope: CompressionScope,
        **kwargs: Any,
    ) -> dict[str, Any]:
        run_id = str(kwargs["reserved_run_id"])
        started.set()
        assert release.wait(timeout=5)
        return {"run_id": run_id, "status": "completed"}

    registry = CompressionJobRegistry(builder=blocking_builder)
    handle = registry.start(db_path, CompressionScope())
    assert started.wait(timeout=1)
    writer = sqlite3.connect(db_path, timeout=0.1)
    try:
        writer.execute("PRAGMA journal_mode = WAL")
        writer.execute("BEGIN IMMEDIATE")
        writer.execute(
            "UPDATE compression_runs SET stage = stage WHERE run_id = ?",
            (handle["run_id"],),
        )
        began = time.perf_counter()

        status = registry.status(db_path, str(handle["run_id"]))

        assert time.perf_counter() - began < 0.25
        assert status is not None
        assert status["status"] in {"pending", "running"}
    finally:
        writer.rollback()
        writer.close()
        release.set()
    _wait_for_terminal(registry, db_path, str(handle["run_id"]))


def test_worker_failure_is_terminal_and_omits_exception_message(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"

    def failing_builder(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("private local failure detail")

    registry = CompressionJobRegistry(builder=failing_builder)
    handle = registry.start(
        db_path,
        CompressionScope(),
        detector_families=("stale_context",),
    )
    terminal = _wait_for_terminal(registry, db_path, str(handle["run_id"]))

    assert terminal["status"] == "failed"
    assert terminal["error_summary"] == {
        "code": "compression_run_failed",
        "type": "RuntimeError",
    }
    assert "private local failure detail" not in str(terminal)


def test_reserved_run_id_owns_profile_and_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    evidence = replace(
        snapshot(
            calls=(
                call(
                    "thread-a-1",
                    thread="thread-a",
                    uncached=25_000,
                    output=100,
                    context_percent=0.8,
                ),
            )
        ),
        source_revision="source-revision",
    )
    monkeypatch.setattr(
        run_builder,
        "load_fact_compression_evidence",
        lambda _db_path, _scope: StreamingEvidenceBundle(
            evidence,
            record_manifest(evidence),
        ),
    )
    registry = CompressionJobRegistry(builder=run_builder.build_compression_run)

    handle = registry.start(
        db_path,
        CompressionScope(),
        detector_families=("stale_context",),
    )
    terminal = _wait_for_terminal(registry, db_path, str(handle["run_id"]))

    assert terminal["status"] == "completed"
    assert terminal["public_profile"]["run_id"] == handle["run_id"]
    page = list_compression_candidates(db_path, run_id=str(handle["run_id"]))
    assert page["total"] == 1


def test_reserved_run_reuses_racing_completed_run_without_duplicate_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    scope = CompressionScope()
    evidence = replace(
        snapshot(
            calls=(
                call(
                    "thread-a-1",
                    thread="thread-a",
                    uncached=25_000,
                    output=100,
                    context_percent=0.8,
                ),
            )
        ),
        source_revision="source-revision",
    )
    monkeypatch.setattr(
        run_builder,
        "load_fact_compression_evidence",
        lambda _db_path, _scope: StreamingEvidenceBundle(
            evidence,
            record_manifest(evidence),
        ),
    )
    canonical = run_builder.build_compression_run(
        db_path,
        scope,
        detector_families=("stale_context",),
    )
    request = prepare_compression_request(
        db_path,
        scope,
        detector_families=("stale_context",),
    )
    create_compression_run(
        db_path,
        run_id="reserved-alias",
        source_revision="",
        scope_hash=request.scope_hash,
        detector_set_version=request.detector_set_version,
        estimator_version=request.estimator_version,
        compression_schema_version=request.compression_schema_version,
        source_generation=request.source_generation,
        revision_key=request.revision_key,
        scope=scope.as_dict(),
    )

    reused = run_builder.build_compression_run(
        db_path,
        scope,
        detector_families=("stale_context",),
        reserved_run_id="reserved-alias",
        prepared_request=request,
    )

    assert reused["run_id"] == canonical["run_id"]
    alias = get_compression_run(db_path, run_id="reserved-alias")
    assert alias is not None
    assert alias["status"] == "completed"
    assert alias["revision_key"] == "alias:reserved-alias"
    assert alias["public_profile"]["run_id"] == canonical["run_id"]
    assert list_compression_candidates(db_path, run_id="reserved-alias")["total"] == 0
    assert list_compression_candidates(db_path, run_id=canonical["run_id"])["total"] == 1


def test_overlapping_detector_selections_persist_distinct_candidate_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    evidence = replace(
        snapshot(
            calls=(
                call(
                    "thread-a-1",
                    thread="thread-a",
                    uncached=25_000,
                    output=100,
                    context_percent=0.8,
                ),
            )
        ),
        source_revision="source-revision",
    )
    monkeypatch.setattr(
        run_builder,
        "load_fact_compression_evidence",
        lambda _db_path, _scope: StreamingEvidenceBundle(
            evidence,
            record_manifest(evidence),
        ),
    )

    subset = run_builder.build_compression_run(
        db_path,
        CompressionScope(),
        detector_families=("stale_context",),
    )
    complete = run_builder.build_compression_run(db_path, CompressionScope())
    subset_page = list_compression_candidates(db_path, run_id=subset["run_id"])
    complete_page = list_compression_candidates(db_path, run_id=complete["run_id"])

    assert subset_page["total"] == 1
    assert complete_page["total"] >= 1
    assert {row["candidate_id"] for row in subset_page["rows"]}.isdisjoint(
        {row["candidate_id"] for row in complete_page["rows"]}
    )


def _wait_for_terminal(
    registry: CompressionJobRegistry,
    db_path: Path,
    run_id: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = registry.status(db_path, run_id)
        if status is not None and status["status"] not in {"pending", "running"}:
            return status
        time.sleep(0.01)
    raise AssertionError(f"compression run did not finish: {run_id}")
