"""Lightweight JSON payload contracts for CLI, MCP, and API surfaces."""

from __future__ import annotations

from codex_usage_tracker.core.json_contract_cli import CLI_JSON_PAYLOAD_CONTRACTS
from codex_usage_tracker.core.json_contract_diagnostics import DIAGNOSTIC_JSON_PAYLOAD_CONTRACTS
from codex_usage_tracker.core.json_contract_server import SERVER_JSON_PAYLOAD_CONTRACTS
from codex_usage_tracker.core.json_contract_subagent import SUBAGENT_JSON_PAYLOAD_CONTRACTS
from codex_usage_tracker.core.json_contract_validation import (
    validate_json_payload_contract as _validate_json_payload_contract,
)
from codex_usage_tracker.core.json_contract_visualization import (
    VISUALIZATION_JSON_PAYLOAD_CONTRACTS,
)

NoneType = type(None)

QUERY_JSON_PAYLOAD_CONTRACTS = {
    "codex-usage-tracker.query.v2": {
        "required": {
            "entity": str,
            "columns": (list, tuple),
            "rows": (list, tuple),
            "next_cursor": (str, NoneType),
            "total_matched": (int, NoneType),
            "dashboard_target": (dict, NoneType),
        }
    }
}

ANALYSIS_JSON_PAYLOAD_CONTRACTS = {
    "codex-usage-tracker.analysis.v2": {
        "required": {
            "analysis_id": str,
            "goal": str,
            "summary": str,
            "findings": (list, tuple),
            "evidence": (list, tuple),
            "methodology": (list, tuple),
            "suggested_questions": (list, tuple),
            "strategy_id": str,
            "strategy_version": str,
            "source_revision": (str, NoneType),
            "accounting": dict,
            "messages": (list, tuple),
            "limitations": (list, tuple),
            "dashboard_destinations": (list, tuple),
        }
    },
    "codex-usage-tracker.analysis-job.v1": {
        "required": {
            "job_id": str,
            "kind": str,
            "state": str,
            "progress_percent": int,
            "stage": str,
            "source_revision": (str, NoneType),
            "request_hash": str,
            "created_at": str,
            "updated_at": str,
            "completed_at": (str, NoneType),
            "retryable": bool,
            "error": (dict, NoneType),
            "result_schema": (str, NoneType),
            "result": (dict, NoneType),
        }
    },
}

MCP_EVIDENCE_JSON_PAYLOAD_CONTRACTS = {
    "codex-usage-tracker.scope.v1": {
        "required": {
            "since": (str, NoneType),
            "until": (str, NoneType),
            "history": str,
            "privacy_mode": str,
            "filters": dict,
        }
    },
    "codex-usage-tracker.freshness.v1": {
        "required": {
            "latest_indexed_event_at": (str, NoneType),
            "source_revision": (str, NoneType),
            "refresh_completed_at": (str, NoneType),
            "state": str,
            "reason": (str, NoneType),
            "threshold_seconds": (int, NoneType),
            "recommended_refresh_action": (str, NoneType),
        }
    },
    "codex-usage-tracker.accounting-context.v1": {
        "required": {
            "physical_rows": (int, NoneType),
            "canonical_rows": (int, NoneType),
            "copied_rows_excluded": (int, NoneType),
            "pricing_coverage": (float, NoneType),
            "credit_coverage": (float, NoneType),
            "service_tier_coverage": (float, NoneType),
            "history_scope": (str, NoneType),
            "privacy_mode": (str, NoneType),
        }
    },
    "codex-usage-tracker.message.v1": {
        "required": {
            "code": str,
            "severity": str,
            "message": str,
            "remediation": (str, NoneType),
        }
    },
    "codex-usage-tracker.recommendation.v1": {
        "required": {
            "recommendation_id": str,
            "action": str,
            "rationale": str,
            "supporting_claim_ids": list,
        }
    },
    "codex-usage-tracker.finding.v1": {
        "required": {
            "finding_id": str,
            "title": str,
            "claim_type": str,
            "severity": str,
            "confidence": str,
            "statement": str,
            "metrics": dict,
            "evidence_ids": list,
            "caveat_codes": list,
            "recommendation": (dict, NoneType),
        }
    },
    "codex-usage-tracker.evidence.v1": {
        "required": {
            "evidence_id": str,
            "kind": str,
            "label": str,
            "selectors": dict,
            "metrics": dict,
            "source_schema": str,
            "dashboard_target": (dict, NoneType),
        }
    },
    "codex-usage-tracker.next-action.v1": {
        "required": {
            "code": str,
            "label": str,
            "tool": (str, NoneType),
            "arguments": dict,
        }
    },
    "codex-usage-tracker.mcp-envelope.v1": {
        "required": {
            "tool": str,
            "request_id": str,
            "generated_at": str,
            "source_revision": (str, NoneType),
            "freshness": dict,
            "scope": dict,
            "data_class": str,
            "accounting": dict,
            "warnings": list,
            "limitations": list,
            "result_schema": str,
            "result": (dict, list, str, int, float, bool, NoneType),
            "dashboard_targets": list,
            "next_actions": list,
        }
    },
}

MCP_EVIDENCE_SCHEMA_IDS = tuple(MCP_EVIDENCE_JSON_PAYLOAD_CONTRACTS)

JSON_PAYLOAD_CONTRACTS = {
    **QUERY_JSON_PAYLOAD_CONTRACTS,
    **ANALYSIS_JSON_PAYLOAD_CONTRACTS,
    **CLI_JSON_PAYLOAD_CONTRACTS,
    **DIAGNOSTIC_JSON_PAYLOAD_CONTRACTS,
    **SERVER_JSON_PAYLOAD_CONTRACTS,
    **SUBAGENT_JSON_PAYLOAD_CONTRACTS,
    **VISUALIZATION_JSON_PAYLOAD_CONTRACTS,
    **MCP_EVIDENCE_JSON_PAYLOAD_CONTRACTS,
}


def known_json_schemas() -> tuple[str, ...]:
    """Return stable JSON schema ids known to the CLI/MCP contracts."""
    return tuple(sorted(JSON_PAYLOAD_CONTRACTS))


def validate_json_payload_contract(payload: object) -> list[str]:
    """Validate a known stable payload shape; return human-readable errors."""
    return _validate_json_payload_contract(payload, JSON_PAYLOAD_CONTRACTS)
