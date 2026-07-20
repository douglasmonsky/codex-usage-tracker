from __future__ import annotations

import json
import re
from pathlib import Path

from codex_usage_tracker.core.json_contracts import (
    JSON_PAYLOAD_CONTRACTS,
    known_json_schemas,
    validate_json_payload_contract,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATTERN = re.compile(r"codex-usage-tracker-[a-z0-9-]+-v[0-9]+")
RUNTIME_SCHEMA_SOURCE_PATHS = [
    REPO_ROOT / "src" / "codex_usage_tracker" / "core" / "api_payloads.py",
    REPO_ROOT / "src" / "codex_usage_tracker" / "core" / "dashboard_targets.py",
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
    documented = _documented_schema_ids()

    assert documented == set(known_json_schemas())


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
