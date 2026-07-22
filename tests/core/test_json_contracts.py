# ruff: noqa: SIM905
from __future__ import annotations

import json
import re
from pathlib import Path

from codex_usage_tracker.core.json_contracts import (
    JSON_PAYLOAD_CONTRACTS,
    MCP_EVIDENCE_SCHEMA_IDS,
    known_json_schemas,
    validate_json_payload_contract,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATTERN = re.compile(r"codex-usage-tracker(?:-[a-z0-9-]+-v[0-9]+|\.[a-z0-9-]+\.v[0-9]+)")
RUNTIME_SCHEMA_SOURCE_PATHS = [
    REPO_ROOT / "src" / "codex_usage_tracker" / "core" / "api_payloads.py",
    REPO_ROOT / "src" / "codex_usage_tracker" / "core" / "dashboard_targets.py",
    REPO_ROOT / "src" / "codex_usage_tracker" / "application" / "query_models.py",
    REPO_ROOT / "src" / "codex_usage_tracker" / "application" / "analyze.py",
    REPO_ROOT / "src" / "codex_usage_tracker" / "application" / "status.py",
    REPO_ROOT / "src" / "codex_usage_tracker" / "application" / "refresh.py",
    REPO_ROOT / "src" / "codex_usage_tracker" / "jobs" / "models.py",
    REPO_ROOT / "src" / "codex_usage_tracker" / "interfaces" / "http" / "v2.py",
    REPO_ROOT / "src" / "codex_usage_tracker" / "cli" / "main.py",
    REPO_ROOT / "src" / "codex_usage_tracker" / "context" / "api.py",
    REPO_ROOT / "src" / "codex_usage_tracker" / "pricing" / "costing.py",
    REPO_ROOT / "src" / "codex_usage_tracker" / "allowance_intelligence" / "reports.py",
    REPO_ROOT / "src" / "codex_usage_tracker" / "diagnostics" / "reports.py",
    REPO_ROOT / "src" / "codex_usage_tracker" / "diagnostics" / "api.py",
    REPO_ROOT / "src" / "codex_usage_tracker" / "cli" / "mcp_server.py",
    REPO_ROOT / "src" / "codex_usage_tracker" / "compression" / "payloads.py",
    REPO_ROOT / "src" / "codex_usage_tracker" / "reports" / "api.py",
    REPO_ROOT / "src" / "codex_usage_tracker" / "server" / "api.py",
    REPO_ROOT / "src" / "codex_usage_tracker" / "server" / "analysis_jobs.py",
    REPO_ROOT / "src" / "codex_usage_tracker" / "server" / "reports.py",
]


def test_json_contract_validation_accepts_nested_query_contract() -> None:
    payload = {
        "schema": "codex-usage-tracker-query-v1",
        "filters": {
            "since": "2026-06-01",
            "until": None,
            "model": "gpt-5.5",
            "effort": None,
            "thread": None,
            "project": None,
            "pricing_status": None,
            "credit_confidence": None,
            "min_tokens": 100,
            "min_credits": None,
            "limit": 10,
            "privacy_mode": "strict",
        },
        "row_count": 0,
        "total_matched_rows": 0,
        "truncated": False,
        "rows": [],
        "dashboard_target": {
            "schema": "codex-usage-tracker-dashboard-target-v1",
            "view": "overview",
            "filters": {},
            "history": "active",
            "privacy_mode": "strict",
            "relative_url": "/react-dashboard.html?view=overview",
            "absolute_url": None,
            "fallback_instruction": "codex-usage-tracker serve-dashboard --open",
        },
    }

    assert validate_json_payload_contract(payload) == []


def test_allowance_v2_contracts_are_tracked() -> None:
    schemas = set(known_json_schemas())

    assert {
        "codex-usage-tracker-allowance-status-v2",
        "codex-usage-tracker-allowance-series-v2",
        "codex-usage-tracker-allowance-evidence-v2",
        "codex-usage-tracker-allowance-analysis-v2",
    } <= schemas


def test_http_v2_contracts_are_tracked_and_validate() -> None:
    schemas = set(known_json_schemas())
    assert {
        "codex-usage-tracker.status.v2",
        "codex-usage-tracker.refresh.v2",
        "codex-usage-tracker.job.v1",
        "codex-usage-tracker.capabilities.v2",
        "codex-usage-tracker.error.v1",
    } <= schemas
    assert (
        validate_json_payload_contract(
            {
                "schema": "codex-usage-tracker.capabilities.v2",
                "analysis_goals": [],
                "query_entities": {},
                "query_measures": [],
                "allowance_operations": [],
                "evidence_selector_kinds": [],
            }
        )
        == []
    )
    assert (
        validate_json_payload_contract(
            {
                "schema": "codex-usage-tracker.error.v1",
                "error": {"code": "invalid_request", "message": "invalid"},
            }
        )
        == []
    )


def test_dashboard_target_contract_is_tracked() -> None:
    payload = {
        "schema": "codex-usage-tracker-dashboard-target-v1",
        "view": "overview",
        "filters": {},
        "history": "active",
        "privacy_mode": "strict",
        "relative_url": "/react-dashboard.html?view=overview",
        "absolute_url": None,
        "fallback_instruction": "codex-usage-tracker serve-dashboard --open",
    }

    assert validate_json_payload_contract(payload) == []


def test_query_v2_contract_is_exactly_tracked() -> None:
    expected = {
        "required": {
            "entity": str,
            "columns": (list, tuple),
            "rows": (list, tuple),
            "next_cursor": (str, type(None)),
            "total_matched": (int, type(None)),
            "dashboard_target": (dict, type(None)),
        }
    }

    assert JSON_PAYLOAD_CONTRACTS["codex-usage-tracker.query.v2"] == expected
    assert (
        validate_json_payload_contract(
            {
                "schema": "codex-usage-tracker.query.v2",
                "entity": "model",
                "columns": ["model", "tokens"],
                "rows": [],
                "next_cursor": None,
                "total_matched": 0,
                "dashboard_target": None,
            }
        )
        == []
    )


def test_analysis_v2_and_analysis_job_contracts_are_exactly_tracked() -> None:
    analysis = JSON_PAYLOAD_CONTRACTS["codex-usage-tracker.analysis.v2"]["required"]
    job = JSON_PAYLOAD_CONTRACTS["codex-usage-tracker.analysis-job.v1"]["required"]

    assert set(analysis) == set(
        "analysis_id goal summary findings evidence methodology suggested_questions strategy_id "
        "strategy_version source_revision accounting messages limitations dashboard_destinations".split()
    )
    assert set(job) == set(
        "job_id kind state progress_percent stage source_revision request_hash created_at updated_at "
        "completed_at retryable error result_schema result".split()
    )


def test_evidence_result_and_dashboard_v2_contracts_are_non_colliding() -> None:
    result = JSON_PAYLOAD_CONTRACTS["codex-usage-tracker.evidence-result.v1"]["required"]
    target = JSON_PAYLOAD_CONTRACTS["codex-usage-tracker-dashboard-target-v2"]["required"]
    assert set(result) == {"selector", "records", "next_cursor", "dashboard_target"}
    assert {"target_id", "surface", "evidence_kind", "selectors", "scope"} <= set(target)
    assert "codex-usage-tracker.evidence.v1" in JSON_PAYLOAD_CONTRACTS


def test_subagent_usage_schema_id_contract_is_tracked() -> None:
    payload = {
        "schema_id": "codex-usage-tracker.subagent-usage.v1",
        "generated_at": "2026-07-21T12:00:00+00:00",
        "filters": {
            "since": None,
            "parent_thread": None,
            "agent_role": None,
            "subagent_type": None,
            "include_archived": False,
            "limit": 10,
            "privacy_mode": "normal",
        },
        "definitions": {},
        "summary": {},
        "comparison": {},
        "by_role": [],
        "by_type": [],
        "top_parent_threads": [],
        "coverage": {},
        "warnings": [],
    }

    assert validate_json_payload_contract(payload) == []
    assert payload["schema_id"] in known_json_schemas()


def test_json_contract_validation_reports_schema_and_type_errors() -> None:
    assert validate_json_payload_contract([]) == ["payload must be a JSON object"]
    assert validate_json_payload_contract({"schema": "unknown-v1"}) == [
        "payload.schema is not tracked: unknown-v1"
    ]

    payload = {
        "schema": "codex-usage-tracker-query-v1",
        "filters": {"privacy_mode": "normal"},
        "row_count": True,
        "total_matched_rows": 0,
        "truncated": False,
        "rows": [],
    }

    errors = validate_json_payload_contract(payload)

    assert "codex-usage-tracker-query-v1.row_count must be int, got bool" in errors
    assert "codex-usage-tracker-query-v1.filters.since is required" in errors

    nested_type_payload = {
        **payload,
        "row_count": 0,
        "filters": {
            "since": "2026-06-01",
            "until": None,
            "model": "gpt-5.5",
            "effort": None,
            "thread": None,
            "project": None,
            "pricing_status": None,
            "credit_confidence": None,
            "min_tokens": "100",
            "min_credits": None,
            "limit": 10,
            "privacy_mode": "strict",
        },
    }
    assert validate_json_payload_contract(nested_type_payload) == [
        "codex-usage-tracker-query-v1.filters.min_tokens must be int or null, got str"
    ]


def test_documented_schema_table_matches_tracked_contracts() -> None:
    documented = _documented_schema_ids() | _documented_mcp_schema_ids()

    assert documented == set(known_json_schemas())
    assert _documented_mcp_schema_ids() == set(MCP_EVIDENCE_SCHEMA_IDS)


def test_runtime_schema_ids_emitted_by_code_are_tracked() -> None:
    emitted: set[str] = set()
    for path in RUNTIME_SCHEMA_SOURCE_PATHS:
        emitted.update(SCHEMA_PATTERN.findall(path.read_text(encoding="utf-8")))

    assert emitted <= set(known_json_schemas())


def test_cli_json_schema_doc_examples_validate_against_contracts() -> None:
    docs = _schema_docs()
    examples = [
        json.loads(match.group(1))
        for match in re.finditer(r"```json\n(.*?)\n```", docs, flags=re.DOTALL)
    ]

    assert examples
    for payload in examples:
        assert validate_json_payload_contract(payload) == []


def test_minimal_payload_for_every_tracked_contract_validates() -> None:
    for schema, contract in JSON_PAYLOAD_CONTRACTS.items():
        payload: dict[str, object] = {"schema": schema}
        for field, expected in contract.get("required", {}).items():
            payload[field] = _example_value(expected)
        for field, nested in contract.get("nested", {}).items():
            nested_payload = payload.setdefault(field, {})
            assert isinstance(nested_payload, dict)
            for nested_field, expected in nested.items():
                nested_payload[nested_field] = _example_value(expected)

        assert validate_json_payload_contract(payload) == []


def _schema_docs() -> str:
    return (REPO_ROOT / "docs" / "cli-json-schemas.md").read_text(encoding="utf-8")


def _documented_schema_ids() -> set[str]:
    docs = _schema_docs()
    in_table = False
    schemas: set[str] = set()
    for line in docs.splitlines():
        if line.strip() == "| Schema | Surface |":
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            break
        if line.startswith("| ---"):
            continue
        match = SCHEMA_PATTERN.search(line)
        if match:
            schemas.add(match.group(0))
    return schemas


def _documented_mcp_schema_ids() -> set[str]:
    docs = (REPO_ROOT / "docs" / "contracts.md").read_text(encoding="utf-8")
    return set(SCHEMA_PATTERN.findall(docs))


def _example_value(expected: object) -> object:
    if isinstance(expected, tuple):
        non_null = next((item for item in expected if item is not type(None)), expected[0])
        return _example_value(non_null)
    if expected is str:
        return "value"
    if expected is int:
        return 1
    if expected is float:
        return 1.0
    if expected is bool:
        return False
    if expected is dict:
        return {}
    if expected is list:
        return []
    if expected is type(None):
        return None
    raise AssertionError(f"unsupported contract type: {expected!r}")
