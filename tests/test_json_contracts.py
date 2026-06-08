from __future__ import annotations

from codex_usage_tracker.json_contracts import (
    JSON_PAYLOAD_CONTRACTS,
    validate_json_payload_contract,
)


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
            "source_provider": "anthropic",
            "source_app": "claude-code",
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
    }

    assert validate_json_payload_contract(payload) == []


def test_json_contract_validation_tracks_source_filters() -> None:
    query_filters = JSON_PAYLOAD_CONTRACTS["codex-usage-tracker-query-v1"]["nested"][
        "filters"
    ]
    recommendation_filters = JSON_PAYLOAD_CONTRACTS[
        "codex-usage-tracker-recommendations-v1"
    ]["nested"]["filters"]

    assert query_filters["source_provider"] == (str, type(None))
    assert query_filters["source_app"] == (str, type(None))
    assert recommendation_filters["source_provider"] == (str, type(None))
    assert recommendation_filters["source_app"] == (str, type(None))


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
