from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import codex_usage_tracker.application.evidence as evidence_application
from codex_usage_tracker.application.evidence import get_evidence
from codex_usage_tracker.core.contracts import serialized_size
from codex_usage_tracker.evidence.models import EvidenceNotFoundError, EvidenceRequest
from codex_usage_tracker.interfaces.mcp.core_tools import build_usage_evidence, usage_evidence
from tests.evidence.test_service import _analysis_service, seed_evidence


def test_application_facade_builds_matching_context(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    seed_evidence(db_path)
    result = get_evidence(EvidenceRequest("call", "record-1"), db_path=db_path)
    assert result.selector == {"kind": "call", "id": "record-1", "section": "summary"}
    assert result.dashboard_target["target_id"].startswith("evidence:")


def test_exact_call_evidence_skips_global_request_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    seed_evidence(db_path)

    def unexpected_context(**_kwargs: object) -> None:
        raise AssertionError("exact call evidence should not scan global request context")

    monkeypatch.setattr(evidence_application, "build_request_context", unexpected_context)

    result = get_evidence(EvidenceRequest("call", "record-1"), db_path=db_path)

    assert result.records[0].evidence_id == "call:record-1"


def test_core_transport_returns_bounded_versioned_envelope(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    seed_evidence(db_path)
    payload = build_usage_evidence(
        selector_kind="call",
        selector_id="record-1",
        db_path=db_path,
        pricing_path=tmp_path / "pricing.json",
    )
    assert payload["schema"] == "codex-usage-tracker.mcp-envelope.v1"
    assert payload["result_schema"] == "codex-usage-tracker.evidence-result.v1"
    assert payload["data_class"] == "aggregate"
    assert payload["dashboard_targets"][0]["schema"] == (  # type: ignore[index]
        "codex-usage-tracker-dashboard-target-v2"
    )
    assert serialized_size(payload) <= 128 * 1024
    assert tuple(inspect.signature(usage_evidence).parameters) == (
        "selector_kind",
        "selector_id",
        "section",
        "limit",
        "cursor",
        "history",
        "analysis_id",
    )
    with pytest.raises(ValueError, match="selector_id"):
        build_usage_evidence(selector_kind="call", selector_id="../bad", db_path=db_path)
    with pytest.raises(EvidenceNotFoundError):
        build_usage_evidence(selector_kind="call", selector_id="record-999", db_path=db_path)
    qualified = build_usage_evidence(
        selector_kind="finding",
        selector_id="finding-1",
        analysis_id="compatibility.token_waste:generation:1",
        db_path=db_path,
        job_service=_analysis_service(),
    )
    assert qualified["result"]["selector"]["analysis_id"] == (  # type: ignore[index]
        "compatibility.token_waste:generation:1"
    )


def test_analysis_qualifier_is_finding_only_and_validated() -> None:
    with pytest.raises(ValueError, match="only supported for finding"):
        EvidenceRequest("call", "record-1", analysis_id="analysis-1")
    with pytest.raises(ValueError, match="analysis"):
        EvidenceRequest("finding", "finding-1", analysis_id="../bad")
