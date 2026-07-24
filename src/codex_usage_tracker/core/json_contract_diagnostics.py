"""Diagnostic Json Payload Contracts JSON payload contracts."""

from __future__ import annotations

from typing import Any

NoneType = type(None)
Number = (int, float)

DIAGNOSTIC_JSON_PAYLOAD_CONTRACTS: dict[str, dict[str, Any]] = {
    "codex-usage-tracker-conversational-readiness-v1": {
        "required": {
            "state": str,
            "summary": str,
            "next_action": (str, NoneType),
            "configured_profile": str,
            "runtime_version_matches": bool,
            "evidence": list,
        }
    },
    "codex-usage-tracker-dedupe-diagnostics-v1": {
        "required": {
            "summary": dict,
            "row_count": int,
            "limit": int,
            "truncated": bool,
            "rows": list,
            "provenance": dict,
        },
        "nested": {
            "summary": {
                "dedupe_enabled": bool,
                "fingerprint_version": str,
                "physical_rows": int,
                "canonical_rows": int,
                "excluded_copied_rows": int,
                "excluded_total_tokens": int,
                "canonical_total_tokens": int,
                "duplicate_reasons": dict,
            },
            "provenance": {
                "physical_rows_preserved": bool,
                "raw_content_included": bool,
            },
        },
    },
    "codex-usage-tracker-diagnostics-v1": {
        "required": {
            "view": str,
            "filters": dict,
            "row_count": int,
            "total_matched_rows": int,
            "truncated": bool,
            "raw_context_included": bool,
            "rows": list,
            "notes": list,
        },
        "nested": {
            "filters": {
                "since": (str, NoneType),
                "until": (str, NoneType),
                "model": (str, NoneType),
                "effort": (str, NoneType),
                "thread": (str, NoneType),
                "min_tokens": (int, NoneType),
                "fact_type": (str, NoneType),
                "fact_name": (str, NoneType),
                "fact_category": (str, NoneType),
                "fact_group": (str, NoneType),
                "include_archived": bool,
                "sort": str,
                "direction": str,
                "limit": (int, NoneType),
                "offset": int,
                "privacy_mode": str,
            }
        },
    },
    "codex-usage-tracker-diagnostic-overview-v1": {
        "required": {
            "section": str,
            "status": str,
            "refreshed": bool,
            "raw_context_included": bool,
            "snapshot": (dict, NoneType),
            "overview": (dict, NoneType),
            "notes": list,
        }
    },
    "codex-usage-tracker-diagnostic-tool-output-v1": {
        "required": {
            "section": str,
            "status": str,
            "refreshed": bool,
            "raw_context_included": bool,
            "snapshot": (dict, NoneType),
            "summary": (dict, NoneType),
            "functions": list,
            "command_roots": list,
            "missing_reasons": list,
            "notes": list,
        }
    },
    "codex-usage-tracker-diagnostic-commands-v1": {
        "required": {
            "section": str,
            "status": str,
            "refreshed": bool,
            "raw_context_included": bool,
            "snapshot": (dict, NoneType),
            "summary": (dict, NoneType),
            "commands": list,
            "notes": list,
        }
    },
    "codex-usage-tracker-diagnostic-git-interactions-v1": {
        "required": {
            "section": str,
            "status": str,
            "refreshed": bool,
            "raw_context_included": bool,
            "snapshot": (dict, NoneType),
            "summary": (dict, NoneType),
            "interactions": list,
            "categories": list,
            "mutability": list,
            "notes": list,
        }
    },
    "codex-usage-tracker-diagnostic-file-reads-v1": {
        "required": {
            "section": str,
            "status": str,
            "refreshed": bool,
            "raw_context_included": bool,
            "snapshot": (dict, NoneType),
            "summary": (dict, NoneType),
            "by_reader": list,
            "top_paths": list,
            "largest_read_commands": list,
            "path_privacy": dict,
            "notes": list,
        }
    },
    "codex-usage-tracker-diagnostic-file-modifications-v1": {
        "required": {
            "section": str,
            "status": str,
            "refreshed": bool,
            "raw_context_included": bool,
            "snapshot": (dict, NoneType),
            "summary": (dict, NoneType),
            "top_paths": list,
            "by_extension": list,
            "largest_events": list,
            "path_privacy": dict,
            "notes": list,
        }
    },
    "codex-usage-tracker-diagnostic-read-productivity-v1": {
        "required": {
            "section": str,
            "status": str,
            "refreshed": bool,
            "raw_context_included": bool,
            "snapshot": (dict, NoneType),
            "summary": (dict, NoneType),
            "by_reader": list,
            "top_modified_paths": list,
            "path_privacy": dict,
            "notes": list,
        }
    },
    "codex-usage-tracker-diagnostic-concentration-v1": {
        "required": {
            "section": str,
            "status": str,
            "refreshed": bool,
            "raw_context_included": bool,
            "snapshot": (dict, NoneType),
            "summary": (dict, NoneType),
            "metrics": list,
            "dimensions": list,
            "largest_impact_rows": list,
            "privacy": dict,
            "notes": list,
        }
    },
    "codex-usage-tracker-diagnostic-guided-summary-v1": {
        "required": {
            "section": str,
            "status": str,
            "refreshed": bool,
            "raw_context_included": bool,
            "snapshot": (dict, NoneType),
            "summary": (dict, NoneType),
            "drivers": list,
            "top_threads": list,
            "top_models": list,
            "top_efforts": list,
            "token_mix": (dict, NoneType),
            "signals": list,
            "notes": list,
        }
    },
    "codex-usage-tracker-diagnostic-usage-drain-v1": {
        "required": {
            "section": str,
            "status": str,
            "refreshed": bool,
            "raw_context_included": bool,
            "snapshot": (dict, NoneType),
            "summary": (dict, NoneType),
            "thread_cost_curves": dict,
            "time_series": dict,
            "model_highlights": dict,
            "pricing": dict,
            "notes": list,
        }
    },
}
