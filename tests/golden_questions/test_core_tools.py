"""Deterministic routing checks for the 0.22 core MCP surface."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from codex_usage_tracker.allowance_intelligence.contracts import (
    ALLOWANCE_EVIDENCE_SCHEMA,
    ALLOWANCE_STATUS_SCHEMA,
)
from codex_usage_tracker.application.analyze import ANALYSIS_RESULT_SCHEMA
from codex_usage_tracker.application.query_models import QueryResult
from codex_usage_tracker.evidence.models import EVIDENCE_RESULT_SCHEMA
from codex_usage_tracker.interfaces.mcp.profiles import tools_for_profile

CASES_DIR = Path(__file__).with_name("cases")
REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "codex-usage-api" / "SKILL.md"
ENVELOPE_SCHEMA = "codex-usage-tracker.mcp-envelope.v1"
NON_BUDGETED_TOOLS = {"usage_refresh", "usage_job_status"}


def _load_cases() -> list[dict[str, object]]:
    return [
        json.loads(path.read_text(encoding="utf-8")) for path in sorted(CASES_DIR.glob("*.json"))
    ]


CASES = _load_cases()


def _expected_result_schema(call: dict[str, object]) -> str:
    tool = call["tool"]
    arguments = call["arguments"]
    assert isinstance(arguments, dict)
    if tool == "usage_analyze":
        return ANALYSIS_RESULT_SCHEMA
    if tool == "usage_query":
        return QueryResult.__dataclass_fields__["schema"].default
    if tool == "usage_evidence":
        return EVIDENCE_RESULT_SCHEMA
    if tool == "usage_allowance":
        return {
            "status": ALLOWANCE_STATUS_SCHEMA,
            "evidence": ALLOWANCE_EVIDENCE_SCHEMA,
        }[arguments["operation"]]
    raise AssertionError(f"golden case lacks a deterministic schema rule for {tool}")


def test_golden_question_catalog_has_exactly_ten_synthetic_cases() -> None:
    assert len(CASES) == 10
    assert len({case["id"] for case in CASES}) == 10
    assert all("synthetic" in str(case["question"]).lower() for case in CASES)


@pytest.mark.parametrize("case", CASES, ids=lambda case: str(case["id"]))
def test_golden_question_routes_are_supported_by_skill_and_core_metadata(
    case: dict[str, object],
) -> None:
    skill = SKILL_PATH.read_text(encoding="utf-8").lower()
    guidance_terms = case["guidance_terms"]
    assert isinstance(guidance_terms, list)
    assert all(str(term).lower() in skill for term in guidance_terms)

    sequence = case["expected_core_tool_sequence"]
    assert isinstance(sequence, list) and sequence
    budgeted_calls = [call for call in sequence if call["tool"] not in NON_BUDGETED_TOOLS]
    assert len(budgeted_calls) <= 3
    assert case["expected_envelope_schema"] == ENVELOPE_SCHEMA

    core_specs = {spec.name: spec for spec in tools_for_profile("core")}
    for call in sequence:
        spec = core_specs[call["tool"]]
        assert spec.minimum_profile == "core"
        assert spec.maturity == "stable"
        assert spec.lifecycle == "active"
        assert spec.disposition == "core"
        assert spec.data_class in {"aggregate", "administrative"}
        assert inspect.getdoc(spec.handler)
        inspect.signature(spec.handler).bind(**call["arguments"])
        assert call["result_schema"] == _expected_result_schema(call)
