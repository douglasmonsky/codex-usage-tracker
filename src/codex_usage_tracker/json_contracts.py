"""Lightweight JSON payload contracts for CLI and MCP automation surfaces."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

NoneType = type(None)
Number = (int, float)
TypeSpec = type | tuple[type, ...]

REFRESH_RESULT_FIELDS = {
    "scanned_files": int,
    "parsed_events": int,
    "skipped_events": int,
    "inserted_or_updated_events": int,
    "db_path": str,
    "parser_diagnostics": dict,
}

PLUGIN_INSTALL_FIELDS = {
    "plugin_dir": str,
    "marketplace_path": str,
    "python_executable": str,
    "replaced_existing": bool,
    "restart_required": bool,
}

PATH_CREATED_FIELDS = {
    "created": bool,
}

JSON_PAYLOAD_CONTRACTS: dict[str, dict[str, Any]] = {
    "codex-usage-tracker-setup-v1": {
        "required": {
            "codex_home": str,
            "codex_home_exists": bool,
            "plugin": dict,
            "pricing": dict,
            "refresh": dict,
            "doctor": dict,
            "restart_required": bool,
        }
    },
    "codex-usage-tracker-doctor-v1": {
        "required": {
            "status": str,
            "failures": int,
            "warnings": int,
            "checks": list,
        }
    },
    "codex-usage-tracker-plugin-install-v1": {"required": PLUGIN_INSTALL_FIELDS},
    "codex-usage-tracker-plugin-upgrade-v1": {"required": PLUGIN_INSTALL_FIELDS},
    "codex-usage-tracker-plugin-uninstall-v1": {
        "required": {
            "plugin_dir": str,
            "marketplace_path": str,
            "removed_plugin_path": bool,
            "removed_marketplace_entry": bool,
            "restart_required": bool,
        }
    },
    "codex-usage-tracker-refresh-v1": {"required": REFRESH_RESULT_FIELDS},
    "codex-usage-tracker-rebuild-index-v1": {"required": REFRESH_RESULT_FIELDS},
    "codex-usage-tracker-reset-db-v1": {
        "required": {
            "db_path": str,
            "deleted_usage_events": int,
        }
    },
    "codex-usage-tracker-summary-v1": {
        "required": {
            "group_by": str,
            "is_expensive": bool,
            "privacy_mode": str,
            "row_count": int,
            "rows": list,
        }
    },
    "codex-usage-tracker-query-v1": {
        "required": {
            "filters": dict,
            "row_count": int,
            "total_matched_rows": int,
            "truncated": bool,
            "rows": list,
        },
        "nested": {
            "filters": {
                "since": (str, NoneType),
                "until": (str, NoneType),
                "model": (str, NoneType),
                "effort": (str, NoneType),
                "thread": (str, NoneType),
                "project": (str, NoneType),
                "pricing_status": (str, NoneType),
                "credit_confidence": (str, NoneType),
                "min_tokens": (int, NoneType),
                "min_credits": (int, float, NoneType),
                "limit": (int, NoneType),
                "privacy_mode": str,
            }
        },
    },
    "codex-usage-tracker-session-v1": {
        "required": {
            "requested_session_id": (str, NoneType),
            "resolved_session_id": (str, NoneType),
            "limit": int,
            "privacy_mode": str,
            "row_count": int,
            "rows": list,
        }
    },
    "codex-usage-tracker-context-v1": {
        "required": {
            "loaded_on_demand": bool,
            "raw_context_persisted": bool,
            "include_tool_output": bool,
            "record": dict,
            "source": dict,
            "entries": list,
            "omitted": dict,
        }
    },
    "codex-usage-tracker-context-disabled-v1": {
        "required": {
            "error": str,
            "raw_context_enabled": bool,
            "record_id": str,
        }
    },
    "codex-usage-tracker-dashboard-v1": {
        "required": {
            "dashboard_path": str,
            "file_url": str,
            "opened": bool,
            "limit": (int, NoneType),
            "since": (str, NoneType),
            "privacy_mode": str,
        }
    },
    "codex-usage-tracker-open-dashboard-v1": {
        "required": {
            "dashboard_path": str,
            "file_url": str,
            "opened": bool,
            "limit": (int, NoneType),
            "since": (str, NoneType),
            "refresh": (dict, NoneType),
            "privacy_mode": str,
        }
    },
    "codex-usage-tracker-serve-dashboard-v1": {
        "required": {
            "host": str,
            "port": int,
            "dashboard_path": str,
            "limit": (int, NoneType),
            "since": (str, NoneType),
            "context_api": str,
            "refresh_before_start": bool,
            "privacy_mode": str,
        }
    },
    "codex-usage-tracker-pricing-coverage-v1": {
        "required": {
            "model_count": int,
            "priced_model_count": int,
            "unpriced_model_count": int,
            "total_tokens": Number,
            "priced_tokens": Number,
            "unpriced_tokens": Number,
            "estimated_cost_usd": Number,
            "priced_token_ratio": Number,
            "pricing_loaded": bool,
            "pricing_path": str,
            "pricing_source": (dict, NoneType),
            "rows": list,
        }
    },
    "codex-usage-tracker-export-v1": {
        "required": {
            "rows": int,
            "csv_path": str,
            "limit": (int, NoneType),
            "privacy_mode": str,
        }
    },
    "codex-usage-tracker-init-pricing-v1": {
        "required": {"pricing_path": str, **PATH_CREATED_FIELDS}
    },
    "codex-usage-tracker-update-pricing-v1": {
        "required": {
            "pricing_path": str,
            "source_url": str,
            "tier": str,
            "fetched_at": str,
            "model_count": int,
            "estimated_model_count": int,
            "backup_path": (str, NoneType),
        }
    },
    "codex-usage-tracker-pin-pricing-v1": {
        "required": {
            "pricing_path": str,
            "source_pricing_path": str,
        }
    },
    "codex-usage-tracker-init-allowance-v1": {
        "required": {"allowance_path": str, **PATH_CREATED_FIELDS}
    },
    "codex-usage-tracker-parse-allowance-v1": {
        "required": {
            "allowance_path": str,
            "updated": bool,
        }
    },
    "codex-usage-tracker-update-rate-card-v1": {
        "required": {
            "rate_card_path": str,
            "source_url": (str, NoneType),
            "fetched_at": (str, NoneType),
            "model_count": int,
            "alias_count": int,
            "backup_path": (str, NoneType),
        }
    },
    "codex-usage-tracker-init-thresholds-v1": {
        "required": {"thresholds_path": str, **PATH_CREATED_FIELDS}
    },
    "codex-usage-tracker-init-projects-v1": {
        "required": {"projects_path": str, **PATH_CREATED_FIELDS}
    },
    "codex-usage-tracker-support-bundle-v1": {
        "required": {
            "support_bundle_path": str,
            "privacy": dict,
        },
        "nested": {
            "privacy": {
                "contains_raw_logs": bool,
                "contains_prompts": bool,
                "contains_assistant_messages": bool,
                "contains_tool_output": bool,
                "project_metadata_mode": str,
            }
        },
    },
}


def known_json_schemas() -> tuple[str, ...]:
    """Return schema identifiers that have a tracked contract."""

    return tuple(sorted(JSON_PAYLOAD_CONTRACTS))


def validate_json_payload_contract(payload: object) -> list[str]:
    """Return contract validation errors for one CLI or MCP JSON payload."""

    if not isinstance(payload, Mapping):
        return ["payload must be a JSON object"]
    schema = payload.get("schema")
    if not isinstance(schema, str) or not schema:
        return ["payload.schema must be a non-empty string"]
    contract = JSON_PAYLOAD_CONTRACTS.get(schema)
    if contract is None:
        return [f"payload.schema is not tracked: {schema}"]

    errors: list[str] = []
    for field, expected in contract.get("required", {}).items():
        if field not in payload:
            errors.append(f"{schema}.{field} is required")
            continue
        if not _matches_type(payload[field], expected):
            errors.append(
                f"{schema}.{field} must be {_describe_type(expected)}, "
                f"got {type(payload[field]).__name__}"
            )

    for field, nested in contract.get("nested", {}).items():
        value = payload.get(field)
        if not isinstance(value, Mapping):
            continue
        for nested_field, expected in nested.items():
            if nested_field not in value:
                errors.append(f"{schema}.{field}.{nested_field} is required")
                continue
            if not _matches_type(value[nested_field], expected):
                errors.append(
                    f"{schema}.{field}.{nested_field} must be {_describe_type(expected)}, "
                    f"got {type(value[nested_field]).__name__}"
                )
    return errors


def _matches_type(value: object, expected: object) -> bool:
    if expected is Number:
        return isinstance(value, int | float) and not isinstance(value, bool)
    if isinstance(expected, tuple):
        return any(_matches_type(value, item) for item in expected)
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected is float:
        return isinstance(value, float) and not isinstance(value, bool)
    if expected is bool:
        return isinstance(value, bool)
    if isinstance(expected, type):
        return isinstance(value, expected)
    return False


def _describe_type(expected: object) -> str:
    if expected is Number:
        return "number"
    if isinstance(expected, tuple):
        return " or ".join(_describe_type(item) for item in expected)
    if expected is NoneType:
        return "null"
    if isinstance(expected, type):
        return expected.__name__
    return str(expected)
