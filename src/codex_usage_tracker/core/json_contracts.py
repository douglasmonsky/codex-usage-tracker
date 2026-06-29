"""Lightweight JSON payload contracts for CLI, MCP, and API surfaces."""

from __future__ import annotations

from codex_usage_tracker.core.json_contract_cli import CLI_JSON_PAYLOAD_CONTRACTS
from codex_usage_tracker.core.json_contract_diagnostics import DIAGNOSTIC_JSON_PAYLOAD_CONTRACTS
from codex_usage_tracker.core.json_contract_server import SERVER_JSON_PAYLOAD_CONTRACTS
from codex_usage_tracker.core.json_contract_validation import (
    validate_json_payload_contract as _validate_json_payload_contract,
)

JSON_PAYLOAD_CONTRACTS = {
    **CLI_JSON_PAYLOAD_CONTRACTS,
    **DIAGNOSTIC_JSON_PAYLOAD_CONTRACTS,
    **SERVER_JSON_PAYLOAD_CONTRACTS,
}


def known_json_schemas() -> tuple[str, ...]:
    """Return stable JSON schema ids known to the CLI/MCP contracts."""
    return tuple(sorted(JSON_PAYLOAD_CONTRACTS))


def validate_json_payload_contract(payload: object) -> list[str]:
    """Validate a known stable payload shape; return human-readable errors."""
    return _validate_json_payload_contract(payload, JSON_PAYLOAD_CONTRACTS)
