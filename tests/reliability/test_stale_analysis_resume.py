from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import codex_usage_tracker.interfaces.mcp.query_analysis_tools as analysis_tools
from codex_usage_tracker.application.analyze import AnalyzeResult
from codex_usage_tracker.application.refresh import CompletedOrJob
from codex_usage_tracker.interfaces.mcp.query_analysis_tools import build_usage_analyze
from codex_usage_tracker.jobs.adapters import request_hash
from codex_usage_tracker.jobs.models import JobStatusV1
from tests.application.fixtures.analysis_cases import synthetic_analysis_report
from tests.application.test_analyze import _context, _Strategy


def test_stale_analysis_names_durable_refresh_and_exact_resume(
    tmp_path: Path,
    monkeypatch,
) -> None:
    context = _context(_Strategy("token_waste"))
    stale_context = replace(
        context,
        freshness=replace(
            context.freshness,
            state="stale",
            reason="Synthetic index is stale.",
            recommended_refresh_action="usage_refresh",
        ),
    )
    refresh_job = _refresh_job()
    observed_requests: list[object] = []

    def fake_refresh(request, **_kwargs):
        observed_requests.append(request)
        return CompletedOrJob(job=refresh_job)

    def unexpected_analysis(*_args, **_kwargs):
        raise AssertionError("stale analysis must wait on refresh before executing")

    monkeypatch.setattr(analysis_tools, "refresh_usage", fake_refresh)
    payload = build_usage_analyze(
        goal="token_waste",
        filters={"model": "gpt-5.5"},
        history="active",
        evidence_limit=4,
        execution="auto",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        codex_home=tmp_path / ".codex",
        context_builder=lambda **_kwargs: stale_context,
        analysis_service=unexpected_analysis,
        enable_refresh_dependency=True,
    )

    assert len(observed_requests) == 1
    assert observed_requests[0].aggregate_only is True
    dependency = payload["result"]
    assert isinstance(dependency, dict)
    assert dependency["schema"] == ("codex-usage-tracker.analysis-refresh-dependency.v1")
    assert dependency["refresh_job"]["job_id"] == refresh_job.job_id
    resume = dependency["resume"]
    assert resume == {
        "tool": "usage_analyze",
        "arguments": {
            "goal": "token_waste",
            "filters": {"model": "gpt-5.5"},
            "history": "active",
            "evidence_limit": 4,
            "comparison": None,
            "execution": "auto",
        },
    }
    assert payload["next_actions"][0]["arguments"]["job_id"] == refresh_job.job_id
    assert payload["next_actions"][1]["arguments"] == resume["arguments"]


def test_exact_resume_runs_analysis_after_fresh_generation(tmp_path: Path) -> None:
    context = _context(_Strategy("token_waste"), revision="generation:8")
    seen: list[object] = []

    def completed_analysis(request, request_context):
        seen.append(request)
        return AnalyzeResult(completed=synthetic_analysis_report("token_waste", request_context))

    payload = build_usage_analyze(
        goal="token_waste",
        filters={"model": "gpt-5.5"},
        history="active",
        evidence_limit=4,
        execution="auto",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        codex_home=tmp_path / ".codex",
        context_builder=lambda **_kwargs: context,
        analysis_service=completed_analysis,
    )

    assert len(seen) == 1
    assert payload["result_schema"] == "codex-usage-tracker.analysis.v2"
    assert payload["result"]["source_revision"] == "generation:8"
    assert payload["result"]["evidence"]


def _refresh_job() -> JobStatusV1:
    return JobStatusV1(
        job_id="refresh_dependency_025",
        kind="refresh",
        state="running",
        progress_percent=35,
        stage="parsing",
        source_revision=request_hash("source"),
        request_hash=request_hash("refresh"),
        created_at="2026-07-25T12:00:00Z",
        updated_at="2026-07-25T12:00:01Z",
        completed_at=None,
        retryable=False,
        error=None,
        result_schema="codex-usage-tracker.refresh.v2",
        result=None,
    )
