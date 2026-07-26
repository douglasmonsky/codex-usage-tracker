from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from codex_usage_tracker.application.analyze import AnalyzeResult
from codex_usage_tracker.interfaces.mcp.query_analysis_tools import build_usage_analyze
from tests.application.fixtures.analysis_cases import synthetic_analysis_report
from tests.application.test_analyze import _context, _Strategy


def test_stale_analysis_uses_committed_generation_without_starting_refresh(
    tmp_path: Path,
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
    seen: list[object] = []

    def analysis_service(request, _analysis_context):
        seen.append(request)
        return AnalyzeResult(
            completed=synthetic_analysis_report("token_waste", stale_context)
        )

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
        analysis_service=analysis_service,
        enable_refresh_dependency=True,
    )

    assert len(seen) == 1
    assert payload["result_schema"] == "codex-usage-tracker.analysis.v2"
    assert payload["source_revision"] == stale_context.source_revision
    assert payload["result"]["evidence"]
    assert any(
        item["code"] == "analysis.stale_generation"
        for item in payload["limitations"]
    )


def test_fresh_analysis_uses_exact_committed_generation(tmp_path: Path) -> None:
    context = _context(_Strategy("token_waste"), revision="generation:8")
    seen: list[object] = []

    def analysis_service(request, _analysis_context):
        seen.append(request)
        return AnalyzeResult(completed=synthetic_analysis_report("token_waste", context))

    payload = build_usage_analyze(
        goal="token_waste",
        filters={"model": "gpt-5.5"},
        history="active",
        evidence_limit=4,
        execution="auto",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        context_builder=lambda **_kwargs: context,
        analysis_service=analysis_service,
    )

    assert len(seen) == 1
    assert payload["result_schema"] == "codex-usage-tracker.analysis.v2"
    assert payload["source_revision"] == "generation:8"
    assert payload["result"]["evidence"]
