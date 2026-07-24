from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from codex_usage_tracker.diagnostics.api import _check_analysis_jobs
from codex_usage_tracker.store.analysis_job_codec import (
    _as_utc,
    _bounded_json,
    _json_dump,
    _json_load,
)
from codex_usage_tracker.store.analysis_job_repository import AnalysisJobRepository

_NOW = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
_SEMANTIC_KEY = f"sha256:{'a' * 64}"


def _repository(
    tmp_path: Path,
    *,
    max_request_bytes: int = 16 * 1024,
    max_result_bytes: int = 1024 * 1024,
    max_terminal_jobs: int = 256,
    terminal_retention: timedelta = timedelta(days=30),
) -> AnalysisJobRepository:
    return AnalysisJobRepository(
        tmp_path / "usage.sqlite3",
        max_request_bytes=max_request_bytes,
        max_result_bytes=max_result_bytes,
        max_terminal_jobs=max_terminal_jobs,
        terminal_retention=terminal_retention,
    )


def _create(
    repository: AnalysisJobRepository,
    *,
    job_id: str = "analysis-one",
    semantic_key: str = _SEMANTIC_KEY,
    source_revision: str = "generation:1",
) -> tuple[dict[str, object], bool]:
    return repository.create_or_reuse(
        job_id=job_id,
        job_kind="analysis",
        semantic_key=semantic_key,
        source_revision=source_revision,
        request_schema="analysis.request.v1",
        request={"goal": "optimize_usage"},
        result_schema="analysis.result.v1",
        now=_NOW,
    )


def test_create_and_active_semantic_deduplication(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    first, created = _create(repository)
    second, second_created = _create(repository, job_id="analysis-two")

    assert created is True
    assert second_created is False
    assert second["job_id"] == first["job_id"] == "analysis-one"
    assert repository.counts() == {
        "active": 1,
        "queued": 1,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "interrupted": 0,
        "pruned": 0,
    }


def test_concurrent_creators_claim_one_active_semantic_job(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(
            pool.map(
                lambda index: _create(repository, job_id=f"analysis-{index}"),
                range(8),
            )
        )

    assert sum(created for _row, created in outcomes) == 1
    assert len({str(row["job_id"]) for row, _created in outcomes}) == 1
    assert repository.counts()["active"] == 1


def test_live_foreign_owner_is_not_interrupted_and_heartbeat_extends_lease(
    tmp_path: Path,
) -> None:
    owner = AnalysisJobRepository(
        tmp_path / "usage.sqlite3",
        owner_id="live-owner",
        lease_ttl=timedelta(seconds=30),
    )
    observer = AnalysisJobRepository(owner.db_path, owner_id="observer")
    _create(owner)

    reused, created = _create(observer, job_id="observer-job")
    assert created is False
    assert reused["job_id"] == "analysis-one"
    assert observer.recover_interrupted(now=_NOW + timedelta(seconds=20)) == 0

    assert owner.heartbeat("analysis-one", now=_NOW + timedelta(seconds=20)) is True
    assert observer.recover_interrupted(now=_NOW + timedelta(seconds=40)) == 0
    assert observer.recover_interrupted(now=_NOW + timedelta(seconds=51)) == 1
    recovered = observer.get("analysis-one")
    assert recovered is not None
    assert recovered["status"] == "interrupted"


def test_completed_result_is_reused_only_when_compatible(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _create(repository)
    repository.update_status(
        "analysis-one",
        state="completed",
        progress={"percent": 100, "stage": "complete"},
        result_schema="analysis.result.v1",
        result={"schema": "analysis.result.v1", "finding_count": 2},
        now=_NOW + timedelta(seconds=3),
    )

    reusable = repository.find_reusable(
        job_kind="analysis",
        semantic_key=_SEMANTIC_KEY,
        source_revision="generation:1",
        result_schema="analysis.result.v1",
        now=_NOW + timedelta(seconds=4),
    )
    stale = repository.find_reusable(
        job_kind="analysis",
        semantic_key=_SEMANTIC_KEY,
        source_revision="generation:2",
        result_schema="analysis.result.v1",
        now=_NOW + timedelta(seconds=4),
    )
    wrong_schema = repository.find_reusable(
        job_kind="analysis",
        semantic_key=_SEMANTIC_KEY,
        source_revision="generation:1",
        result_schema="codex-usage-tracker.analysis.v3",
        now=_NOW + timedelta(seconds=4),
    )

    assert reusable is not None
    assert reusable["result"] == {
        "finding_count": 2,
        "schema": "analysis.result.v1",
    }
    assert stale is None
    assert wrong_schema is None


def test_persisted_transitions_are_owner_scoped_and_monotonic(tmp_path: Path) -> None:
    owner = _repository(tmp_path)
    _create(owner)
    running = owner.update_status(
        "analysis-one",
        state="running",
        progress={"percent": 50, "stage": "analyzing"},
        now=_NOW + timedelta(seconds=1),
    )
    regressed_progress = owner.update_status(
        "analysis-one",
        state="running",
        progress={"percent": 10, "stage": "queued"},
        now=_NOW + timedelta(seconds=2),
    )
    completed = owner.update_status(
        "analysis-one",
        state="completed",
        progress={"percent": 100, "stage": "complete"},
        result_schema="analysis.result.v1",
        result={"finding_count": 1},
        now=_NOW + timedelta(seconds=3),
    )
    stale = owner.update_status(
        "analysis-one",
        state="running",
        progress={"percent": 75, "stage": "analyzing"},
        now=_NOW + timedelta(seconds=4),
    )
    foreign = AnalysisJobRepository(owner.db_path, owner_id="foreign-owner")
    foreign_update = foreign.update_status(
        "analysis-one",
        state="failed",
        progress={"percent": 100, "stage": "failed"},
        now=_NOW + timedelta(seconds=5),
    )

    assert running["progress"] == {"percent": 50, "stage": "analyzing"}
    assert regressed_progress["progress"] == {"percent": 50, "stage": "analyzing"}
    assert completed["status"] == "completed"
    assert stale["status"] == foreign_update["status"] == "completed"
    assert stale["result"] == foreign_update["result"] == {"finding_count": 1}


def test_failure_and_interrupted_recovery_are_persisted(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _create(repository, job_id="running-job")
    repository.update_status(
        "running-job",
        state="running",
        progress={"percent": 25, "stage": "analyzing"},
        now=_NOW + timedelta(seconds=1),
    )
    _create(
        repository,
        job_id="failed-job",
        semantic_key=f"sha256:{'b' * 64}",
    )
    repository.update_status(
        "failed-job",
        state="failed",
        progress={"percent": 10, "stage": "failed"},
        error={
            "code": "job.failed",
            "severity": "warning",
            "message": "The analysis job failed.",
        },
        now=_NOW + timedelta(seconds=2),
    )

    restarted = AnalysisJobRepository(repository.db_path, owner_id="restarted-process")
    recovered = restarted.recover_interrupted(now=_NOW + timedelta(minutes=1))

    assert recovered == 1
    running = repository.get("running-job")
    failed = repository.get("failed-job")
    assert running is not None
    assert running["status"] == "interrupted"
    error = running["error"]
    assert isinstance(error, dict)
    assert error["code"] == "job.interrupted"
    assert failed is not None
    assert failed["status"] == "failed"
    diagnostic = _check_analysis_jobs(repository.db_path)
    assert diagnostic.status == "warn"
    assert "interrupted=1" in diagnostic.detail
    assert "failed=1" in diagnostic.detail


def test_retention_prunes_old_and_excess_terminal_rows_transactionally(
    tmp_path: Path,
) -> None:
    repository = _repository(
        tmp_path,
        max_terminal_jobs=2,
        terminal_retention=timedelta(days=7),
    )
    for index in range(4):
        semantic_key = f"sha256:{index:064x}"
        _create(
            repository,
            job_id=f"analysis-{index}",
            semantic_key=semantic_key,
        )
        repository.update_status(
            f"analysis-{index}",
            state="completed",
            progress={"percent": 100, "stage": "complete"},
            result_schema="analysis.result.v1",
            result={"index": index},
            now=_NOW + timedelta(days=index),
        )

    assert repository.counts()["completed"] == 2
    assert repository.counts()["pruned"] == 2
    pruned = repository.prune(now=_NOW + timedelta(days=10))

    assert pruned == 1
    assert repository.get("analysis-0") is None
    assert repository.get("analysis-1") is None
    assert repository.get("analysis-2") is None
    assert repository.get("analysis-3") is not None
    assert repository.counts()["pruned"] == 3


def test_concurrent_readers_observe_complete_json(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _create(repository)
    repository.update_status(
        "analysis-one",
        state="completed",
        progress={"percent": 100, "stage": "complete"},
        result_schema="analysis.result.v1",
        result={"values": list(range(50))},
        now=_NOW + timedelta(seconds=1),
    )

    with ThreadPoolExecutor(max_workers=12) as pool:
        rows = list(pool.map(lambda _index: repository.get("analysis-one"), range(100)))

    assert all(row is not None for row in rows)
    assert all(row["result"] == {"values": list(range(50))} for row in rows if row)


def test_requests_and_results_are_bounded_and_raw_context_is_rejected(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path, max_request_bytes=128, max_result_bytes=128)

    with pytest.raises(ValueError, match="raw context"):
        repository.create_or_reuse(
            job_id="unsafe",
            job_kind="analysis",
            semantic_key=_SEMANTIC_KEY,
            source_revision="generation:1",
            request_schema="analysis.request.v1",
            request={"raw_context": "private"},
            result_schema="analysis.result.v1",
            now=_NOW,
        )
    with pytest.raises(ValueError, match="request exceeds"):
        repository.create_or_reuse(
            job_id="oversized",
            job_kind="analysis",
            semantic_key=_SEMANTIC_KEY,
            source_revision="generation:1",
            request_schema="analysis.request.v1",
            request={"filters": "x" * 512},
            result_schema="analysis.result.v1",
            now=_NOW,
        )

    _create(repository)
    with pytest.raises(ValueError, match="raw context"):
        repository.update_status(
            "analysis-one",
            state="completed",
            progress={"percent": 100, "stage": "complete"},
            result_schema="analysis.result.v1",
            result={"raw_excerpt": "private"},
            now=_NOW + timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="result exceeds"):
        repository.update_status(
            "analysis-one",
            state="completed",
            progress={"percent": 100, "stage": "complete"},
            result_schema="analysis.result.v1",
            result={"summary": "x" * 512},
            now=_NOW + timedelta(seconds=1),
        )


def test_all_persisted_json_columns_reject_context_shaped_payloads(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    with pytest.raises(ValueError, match="raw context"):
        repository.create_or_reuse(
            job_id="message-content",
            job_kind="analysis",
            semantic_key=_SEMANTIC_KEY,
            source_revision="generation:1",
            request_schema="job.request.v1",
            request={"messages": [{"content": "private prompt"}]},
            result_schema="analysis.result.v1",
            now=_NOW,
        )
    with pytest.raises(ValueError, match="unsupported fields"):
        repository.create_or_reuse(
            job_id="unknown-request",
            job_kind="analysis",
            semantic_key=_SEMANTIC_KEY,
            source_revision="generation:1",
            request_schema="analysis.request.v1",
            request={"goal": "optimize_usage", "unexpected": True},
            result_schema="analysis.result.v1",
            now=_NOW,
        )

    _create(repository)
    with pytest.raises(ValueError, match="raw context"):
        repository.update_status(
            "analysis-one",
            state="running",
            progress={"percent": 10, "stage": "running", "content": "private"},
            now=_NOW + timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="raw context"):
        repository.update_status(
            "analysis-one",
            state="failed",
            progress={"percent": 10, "stage": "failed"},
            error={
                "code": "job.failed",
                "severity": "warning",
                "message": "failed",
                "stdout": "private",
            },
            now=_NOW + timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="raw context"):
        repository.update_status(
            "analysis-one",
            state="completed",
            progress={"percent": 100, "stage": "complete"},
            result_schema="analysis.result.v1",
            result={"tool_output": "private"},
            now=_NOW + timedelta(seconds=1),
        )


def test_repository_rejects_invalid_retention_and_json_configuration(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"

    with pytest.raises(ValueError, match="JSON budgets"):
        AnalysisJobRepository(db_path, max_request_bytes=0)
    with pytest.raises(ValueError, match="max_terminal_jobs"):
        AnalysisJobRepository(db_path, max_terminal_jobs=0)
    with pytest.raises(ValueError, match="terminal_retention"):
        AnalysisJobRepository(db_path, terminal_retention=timedelta(0))
    with pytest.raises(ValueError, match="owner_id"):
        AnalysisJobRepository(db_path, owner_id="")
    with pytest.raises(ValueError, match="lease_ttl"):
        AnalysisJobRepository(db_path, lease_ttl=timedelta(0))

    repository = AnalysisJobRepository(db_path)
    with pytest.raises(ValueError, match="JSON-safe"):
        repository.create_or_reuse(
            job_id="unsafe-json",
            job_kind="analysis",
            semantic_key=_SEMANTIC_KEY,
            source_revision="generation:1",
            request_schema="analysis.request.v1",
            request={"goal": object()},
            result_schema="analysis.result.v1",
            now=_NOW,
        )


def test_job_json_codec_rejects_ambiguous_or_malformed_values() -> None:
    with pytest.raises(ValueError, match="must be a JSON object"):
        _bounded_json([], budget=1024, label="request", allowed_root_keys=frozenset())
    with pytest.raises(ValueError, match="JSON-safe"):
        _json_dump({1: "invalid"})

    assert _json_load(None) is None
    assert _json_load("{") is None
    with pytest.raises(ValueError, match="timezone-aware"):
        _as_utc(datetime(2026, 7, 24, 12, 0))
