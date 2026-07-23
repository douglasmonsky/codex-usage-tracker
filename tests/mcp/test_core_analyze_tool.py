from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from codex_usage_tracker.core.contracts import serialized_size
from codex_usage_tracker.interfaces.mcp.core_tools import (
    build_usage_analyze,
    build_usage_job_status,
    usage_analyze,
)
from codex_usage_tracker.interfaces.mcp.query_analysis_tools import _semantic_fingerprints


def test_analyze_real_completed_and_async_job_are_bounded_and_pollable(tmp_path: Path) -> None:
    kwargs = {
        "goal": "token_waste",
        "db_path": tmp_path / "missing.sqlite3",
        "pricing_path": tmp_path / "pricing.json",
        "rate_card_path": tmp_path / "rate-card.json",
        "thresholds_path": tmp_path / "thresholds.json",
    }
    completed = build_usage_analyze(**kwargs, execution="sync")
    queued = build_usage_analyze(**kwargs, execution="async")
    job_id = queued["result"]["job_id"]  # type: ignore[index]
    polled = build_usage_job_status(
        job_id=job_id, db_path=kwargs["db_path"], pricing_path=kwargs["pricing_path"]
    )
    assert completed["result_schema"] == "codex-usage-tracker.analysis.v2"
    assert completed["result"]["strategy_id"] == "compatibility.token_waste"  # type: ignore[index]
    assert queued["result_schema"] == "codex-usage-tracker.analysis-job.v1"
    assert queued["result"]["schema"] == "codex-usage-tracker.analysis-job.v1"  # type: ignore[index]
    assert queued["next_actions"][0]["tool"] == "usage_job_status"  # type: ignore[index]
    assert polled["result_schema"] == "codex-usage-tracker.job.v1"
    assert polled["result"]["job_id"] == job_id  # type: ignore[index]
    assert serialized_size(completed) <= 64 * 1024
    assert serialized_size(queued) <= 16 * 1024


def test_effective_config_fingerprints_ignore_file_location(tmp_path: Path) -> None:
    left, right = tmp_path / "left", tmp_path / "right"
    left.mkdir()
    right.mkdir()
    pricing = '{"_schema":"codex-usage-tracker-pricing-v2","models":{}}'
    thresholds = '{"high_cost_usd":2.0}'
    for root in (left, right):
        (root / "pricing.json").write_text(pricing, encoding="utf-8")
        (root / "thresholds.json").write_text(thresholds, encoding="utf-8")
    from codex_usage_tracker.analytics.analysis_catalog import ANALYSIS_CATALOG

    first = _semantic_fingerprints(
        left / "pricing.json",
        left / "missing-rate.json",
        left / "thresholds.json",
        ANALYSIS_CATALOG,
    )
    second = _semantic_fingerprints(
        right / "pricing.json",
        right / "missing-rate.json",
        right / "thresholds.json",
        ANALYSIS_CATALOG,
    )
    assert first == second
    assert all(value.startswith("sha256:") for value in first)


def test_analyze_errors_and_public_signature_are_field_specific() -> None:
    with pytest.raises(ValueError, match="comparison.until is required"):
        build_usage_analyze(goal="thread_comparison", comparison={"since": "2026-07-01"})
    assert tuple(inspect.signature(usage_analyze).parameters) == (
        "goal",
        "filters",
        "history",
        "evidence_limit",
        "comparison",
        "execution",
    )
    description = inspect.getdoc(usage_analyze) or ""
    assert "'range'" not in description
    assert "'since'" in description and "'until'" in description
