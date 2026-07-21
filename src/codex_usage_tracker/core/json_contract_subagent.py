"""Observed-subagent JSON payload contract."""

from __future__ import annotations

from typing import Any

NoneType = type(None)

SUBAGENT_JSON_PAYLOAD_CONTRACTS: dict[str, dict[str, Any]] = {
    "codex-usage-tracker.subagent-usage.v1": {
        "required": {
            "schema_id": str,
            "generated_at": str,
            "filters": dict,
            "definitions": dict,
            "summary": dict,
            "comparison": dict,
            "by_role": list,
            "by_type": list,
            "top_parent_threads": list,
            "coverage": dict,
            "warnings": list,
        },
        "nested": {
            "filters": {
                "since": (str, NoneType),
                "parent_thread": (str, NoneType),
                "agent_role": (str, NoneType),
                "subagent_type": (str, NoneType),
                "include_archived": bool,
                "limit": int,
                "privacy_mode": str,
            }
        },
    }
}
