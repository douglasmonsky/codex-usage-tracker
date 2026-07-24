from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from codex_usage_tracker.application.container import build_application_container
from codex_usage_tracker.application.paths import ApplicationPaths
from codex_usage_tracker.jobs.adapters import AnalysisJobAdapter, request_hash
from codex_usage_tracker.jobs.service import JobService
from codex_usage_tracker.store.analysis_job_repository import AnalysisJobRepository

_NOW = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)


def test_analysis_job_repository_imports_in_a_cold_process() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            ("from codex_usage_tracker.store.analysis_job_repository import AnalysisJobRepository"),
        ],
        cwd=Path(__file__).parents[2],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def _payload(job_id: str, state: str, *, result: object = None) -> dict[str, object]:
    return {
        "job_id": job_id,
        "status": state,
        "stage": "complete" if state == "completed" else state,
        "source_revision": "generation:1",
        "created_at": "2026-07-24T12:00:00Z",
        "updated_at": "2026-07-24T12:01:00Z",
        "completed_at": ("2026-07-24T12:01:00Z" if state in {"completed", "failed"} else None),
        "progress": {"percent": 100 if state == "completed" else 10},
        "result": result,
    }


def test_completed_result_survives_a_new_job_service(tmp_path: Path) -> None:
    repository = AnalysisJobRepository(tmp_path / "usage.sqlite3")
    semantic_key = request_hash("same-analysis")
    payload = _payload(
        "analysis-one",
        "completed",
        result={"schema": "analysis.result.v1", "finding_count": 3},
    )
    service = JobService(repository=repository)
    registration = service.register_semantic(
        semantic_key,
        kind="analysis",
        job_id="analysis-one",
        adapter=AnalysisJobAdapter(
            lambda _job_id, *, include_result=False: {
                **payload,
                "result": payload["result"] if include_result else None,
            },
            kind="analysis",
            request_hash=semantic_key,
            result_schema="analysis.result.v1",
        ),
        source_revision="generation:1",
        request_schema="analysis.request.v1",
        request={"goal": "optimize_usage"},
    )
    assert registration.should_start is True
    service.checkpoint("analysis-one")

    restarted = JobService(repository=repository, recover_interrupted=True)
    reusable = restarted.reusable(
        semantic_key,
        source_revision="generation:1",
        result_schema="analysis.result.v1",
    )

    assert reusable is not None
    assert reusable.state == "completed"
    assert reusable.result == {
        "finding_count": 3,
        "schema": "analysis.result.v1",
    }


def test_completed_result_survives_a_new_application_container(tmp_path: Path) -> None:
    paths = ApplicationPaths(
        codex_home=tmp_path / ".codex",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
        thresholds_path=tmp_path / "thresholds.json",
        projects_path=tmp_path / "projects.json",
    )
    first = build_application_container(paths)
    semantic_key = request_hash("container-analysis")
    payload = _payload(
        "analysis-container",
        "completed",
        result={"schema": "analysis.result.v1", "finding_count": 1},
    )
    first.jobs.register_semantic(
        semantic_key,
        kind="analysis",
        job_id="analysis-container",
        adapter=AnalysisJobAdapter(
            lambda _job_id, *, include_result=False: {
                **payload,
                "result": payload["result"] if include_result else None,
            },
            kind="analysis",
            request_hash=semantic_key,
            result_schema="analysis.result.v1",
        ),
        source_revision="generation:1",
        request_schema="analysis.request.v1",
        request={"goal": "optimize_usage"},
    )
    first.jobs.checkpoint("analysis-container")

    restarted = build_application_container(paths)
    reusable = restarted.jobs.reusable(
        semantic_key,
        source_revision="generation:1",
        result_schema="analysis.result.v1",
    )

    assert reusable is not None
    assert reusable.state == "completed"
    assert reusable.result == {
        "finding_count": 1,
        "schema": "analysis.result.v1",
    }


def test_restart_marks_orphaned_active_job_interrupted(tmp_path: Path) -> None:
    repository = AnalysisJobRepository(
        tmp_path / "usage.sqlite3",
        owner_id="original-process",
    )
    semantic_key = request_hash("running-analysis")
    service = JobService(repository=repository)
    service.register_semantic(
        semantic_key,
        kind="analysis",
        job_id="analysis-running",
        adapter=AnalysisJobAdapter(
            lambda _job_id, *, include_result=False: _payload("analysis-running", "running"),
            kind="analysis",
            request_hash=semantic_key,
            result_schema="analysis.result.v1",
        ),
        source_revision="generation:1",
        request_schema="analysis.request.v1",
        request={"goal": "optimize_usage"},
    )
    service.checkpoint("analysis-running")

    restarted_repository = AnalysisJobRepository(
        repository.db_path,
        owner_id="restarted-process",
    )
    restarted_repository.recover_interrupted(now=datetime.now(timezone.utc) + timedelta(minutes=1))
    restarted = JobService(repository=restarted_repository)
    status = restarted.status("analysis-running")

    assert status.state == "failed"
    assert status.error is not None
    assert status.error.code == "job.interrupted"
    assert (
        restarted.reusable(
            semantic_key,
            source_revision="generation:1",
            result_schema="analysis.result.v1",
        )
        is None
    )


def test_persisted_registration_deduplicates_competing_services(tmp_path: Path) -> None:
    repository = AnalysisJobRepository(tmp_path / "usage.sqlite3")
    semantic_key = request_hash("deduplicated")

    def register(job_id: str) -> tuple[str, bool]:
        service = JobService(repository=repository)
        registration = service.register_semantic(
            semantic_key,
            kind="analysis",
            job_id=job_id,
            adapter=AnalysisJobAdapter(
                lambda selected, *, include_result=False: _payload(selected, "queued"),
                kind="analysis",
                request_hash=semantic_key,
                result_schema="analysis.result.v1",
            ),
            source_revision="generation:1",
            request_schema="analysis.request.v1",
            request={"goal": "optimize_usage"},
        )
        return registration.status.job_id, registration.should_start

    first = register("analysis-one")
    second = register("analysis-two")

    assert first == ("analysis-one", True)
    assert second == ("analysis-one", False)
