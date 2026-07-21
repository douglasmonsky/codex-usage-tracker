"""Cli Json Payload Contracts JSON payload contracts."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker.core.json_contract_common import (
    PATH_CREATED_FIELDS,
    PLUGIN_INSTALL_FIELDS,
    REFRESH_RESULT_FIELDS,
)
from codex_usage_tracker.core.json_contract_summary import SUMMARY_JSON_PAYLOAD_CONTRACTS

NoneType = type(None)
Number = (int, float)

CLI_JSON_PAYLOAD_CONTRACTS: dict[str, dict[str, Any]] = {
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
            "environment": dict,
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
    **SUMMARY_JSON_PAYLOAD_CONTRACTS,
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
    "codex-usage-tracker-recommendations-v1": {
        "required": {
            "filters": dict,
            "row_count": int,
            "total_matched_rows": int,
            "truncated": bool,
            "threads": list,
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
                "include_archived": bool,
                "min_score": (int, float, NoneType),
                "limit": (int, NoneType),
                "privacy_mode": str,
            }
        },
    },
    "codex-usage-tracker-allowance-history-v1": {
        "required": {
            "generated_at": str,
            "privacy_mode": str,
            "include_archived": bool,
            "window_kind": (str, NoneType),
            "row_count": int,
            "rows": list,
            "notes": list,
        },
    },
    "codex-usage-tracker-allowance-diagnostics-v1": {
        "required": {
            "generated_at": str,
            "privacy_mode": str,
            "include_archived": bool,
            "window_kind": (str, NoneType),
            "summary": dict,
            "windows": list,
            "spans": list,
            "change_candidates": list,
            "notes": list,
        },
    },
    "codex-usage-tracker-allowance-evidence-export-v1": {
        "required": {
            "generated_at": str,
            "privacy_mode": str,
            "include_archived": bool,
            "summary": dict,
            "windows": list,
            "change_candidates": list,
            "notes": list,
        },
    },
    "codex-usage-tracker-dashboard-v1": {
        "required": {
            "dashboard_path": str,
            "file_url": str,
            "opened": bool,
            "limit": (int, NoneType),
            "since": (str, NoneType),
            "privacy_mode": str,
            "include_archived": bool,
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
            "include_archived": bool,
        }
    },
    "codex-usage-tracker-serve-dashboard-v1": {
        "required": {
            "host": str,
            "port": int,
            "dashboard_path": str,
            "dashboard_url": str,
            "legacy_dashboard_url": str,
            "limit": (int, NoneType),
            "since": (str, NoneType),
            "context_api": str,
            "refresh_before_start": bool,
            "privacy_mode": str,
            "include_archived": bool,
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
    "codex-usage-tracker-source-coverage-v1": {
        "required": {
            "content_mode": str,
            "includes_indexed_content": bool,
            "includes_raw_fragments": bool,
            "include_archived": bool,
            "source_record_count": int,
            "source_file_count": int,
            "parser_version_count": int,
            "warning_record_count": int,
            "rows": list,
        }
    },
    "codex-usage-tracker-content-search-v1": {
        "required": {
            "content_mode": str,
            "includes_indexed_content": bool,
            "includes_raw_fragments": bool,
            "privacy_mode": str,
            "query": str,
            "filters": dict,
            "search_mode": str,
            "row_count": int,
            "total_matched_rows": int,
            "truncated": bool,
            "has_more": bool,
            "next_offset": (int, NoneType),
            "rows": list,
        },
        "nested": {
            "filters": {
                "since": (str, NoneType),
                "until": (str, NoneType),
                "model": (str, NoneType),
                "effort": (str, NoneType),
                "thread": (str, NoneType),
                "include_archived": bool,
                "limit": (int, NoneType),
                "offset": int,
                "max_snippet_chars": (int, NoneType),
            }
        },
    },
    "codex-usage-tracker-thread-trace-v1": {
        "required": {
            "content_mode": str,
            "includes_indexed_content": bool,
            "includes_raw_fragments": bool,
            "privacy_mode": str,
            "filters": dict,
            "call_count": int,
            "total_matched_calls": int,
            "truncated": bool,
            "has_more": bool,
            "next_offset": (int, NoneType),
            "calls": list,
        },
        "nested": {
            "filters": {
                "thread": (str, NoneType),
                "thread_key": (str, NoneType),
                "session_id": (str, NoneType),
                "record_id": (str, NoneType),
                "since": (str, NoneType),
                "until": (str, NoneType),
                "include_archived": bool,
                "limit": (int, NoneType),
                "offset": int,
                "max_snippet_chars": (int, NoneType),
            }
        },
    },
    "codex-usage-tracker-pattern-scan-v1": {
        "required": {
            "content_mode": str,
            "includes_indexed_content": bool,
            "includes_raw_fragments": bool,
            "privacy_mode": str,
            "scan_type": str,
            "scan_types": list,
            "filters": dict,
            "pattern_count": int,
            "total_patterns": int,
            "patterns": list,
        },
        "nested": {
            "filters": {
                "since": (str, NoneType),
                "until": (str, NoneType),
                "thread": (str, NoneType),
                "include_archived": bool,
                "min_occurrences": int,
                "limit": (int, NoneType),
            }
        },
    },
    "codex-usage-tracker-repeated-file-rediscovery-v1": {
        "required": {
            "content_mode": str,
            "includes_indexed_content": bool,
            "includes_raw_fragments": bool,
            "privacy_mode": str,
            "filters": dict,
            "row_count": int,
            "total_candidates": int,
            "rows": list,
        },
        "nested": {
            "filters": {
                "since": (str, NoneType),
                "until": (str, NoneType),
                "thread": (str, NoneType),
                "include_archived": bool,
                "min_occurrences": int,
                "limit": (int, NoneType),
                "sample_limit": int,
            }
        },
    },
    "codex-usage-tracker-shell-churn-v1": {
        "required": {
            "content_mode": str,
            "includes_indexed_content": bool,
            "includes_raw_fragments": bool,
            "privacy_mode": str,
            "filters": dict,
            "row_count": int,
            "total_candidates": int,
            "rows": list,
        },
        "nested": {
            "filters": {
                "since": (str, NoneType),
                "until": (str, NoneType),
                "thread": (str, NoneType),
                "include_archived": bool,
                "min_occurrences": int,
                "limit": (int, NoneType),
                "sample_limit": int,
            }
        },
    },
    "codex-usage-tracker-large-low-output-v1": {
        "required": {
            "content_mode": str,
            "includes_indexed_content": bool,
            "includes_raw_fragments": bool,
            "privacy_mode": str,
            "filters": dict,
            "row_count": int,
            "total_candidates": int,
            "rows": list,
        },
        "nested": {
            "filters": {
                "since": (str, NoneType),
                "until": (str, NoneType),
                "thread": (str, NoneType),
                "include_archived": bool,
                "min_total_tokens": int,
                "max_output_tokens": int,
                "limit": (int, NoneType),
            }
        },
    },
    "codex-usage-tracker-investigation-suggestions-v1": {
        "required": {
            "content_mode": str,
            "includes_indexed_content": bool,
            "includes_raw_fragments": bool,
            "privacy_mode": str,
            "goal": (str, NoneType),
            "available_goals": list,
            "filters": dict,
            "summary": dict,
            "suggestions": list,
        },
        "nested": {
            "filters": {
                "since": (str, NoneType),
                "until": (str, NoneType),
                "thread": (str, NoneType),
                "include_archived": bool,
                "limit": (int, NoneType),
            }
        },
    },
    "codex-usage-tracker-agentic-investigation-v1": {
        "required": {
            "content_mode": str,
            "includes_indexed_content": bool,
            "includes_raw_fragments": bool,
            "privacy_mode": str,
            "goal": str,
            "filters": dict,
            "summary": dict,
            "findings": list,
            "recommended_next_tools": list,
            "caveats": list,
        },
        "nested": {
            "filters": {
                "since": (str, NoneType),
                "until": (str, NoneType),
                "thread": (str, NoneType),
                "include_archived": bool,
                "evidence_limit": int,
                "detail_mode": str,
            }
        },
    },
    "codex-usage-tracker-action-brief-v1": {
        "required": {
            "content_mode": str,
            "includes_indexed_content": bool,
            "includes_raw_fragments": bool,
            "privacy_mode": str,
            "goal": str,
            "filters": dict,
            "summary": dict,
            "actions": list,
            "recommended_next_tools": list,
            "caveats": list,
        },
        "nested": {
            "filters": {
                "since": (str, NoneType),
                "until": (str, NoneType),
                "thread": (str, NoneType),
                "include_archived": bool,
                "evidence_limit": int,
            }
        },
    },
    "codex-usage-tracker-hypothesis-test-v1": {
        "required": {
            "content_mode": str,
            "includes_indexed_content": bool,
            "includes_raw_fragments": bool,
            "privacy_mode": str,
            "question": str,
            "filters": dict,
            "summary": dict,
            "hypotheses": list,
            "recommended_next_tools": list,
            "caveats": list,
        },
        "nested": {
            "filters": {
                "since": (str, NoneType),
                "until": (str, NoneType),
                "thread": (str, NoneType),
                "include_archived": bool,
                "evidence_limit": int,
            }
        },
    },
    "codex-usage-tracker-investigation-walk-v1": {
        "required": {
            "content_mode": str,
            "includes_indexed_content": bool,
            "includes_raw_fragments": bool,
            "privacy_mode": str,
            "question": str,
            "filters": dict,
            "summary": dict,
            "branches": list,
            "recommended_next_tools": list,
        },
        "nested": {
            "filters": {
                "since": (str, NoneType),
                "until": (str, NoneType),
                "thread": (str, NoneType),
                "include_archived": bool,
                "min_occurrences": int,
                "evidence_limit": int,
            }
        },
    },
    "codex-usage-tracker-local-evidence-export-v1": {
        "required": {
            "content_mode": str,
            "includes_indexed_content": bool,
            "includes_raw_fragments": bool,
            "privacy_mode": str,
            "question": str,
            "filters": dict,
            "summary": dict,
            "branches": list,
            "omitted_fields": list,
            "caveats": list,
        },
        "nested": {
            "filters": {
                "since": (str, NoneType),
                "until": (str, NoneType),
                "thread": (str, NoneType),
                "include_archived": bool,
                "min_occurrences": int,
                "evidence_limit": int,
            }
        },
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
            "issue_report": dict,
        },
        "nested": {
            "privacy": {
                "contains_raw_logs": bool,
                "contains_prompts": bool,
                "contains_assistant_messages": bool,
                "contains_tool_output": bool,
                "project_metadata_mode": str,
            },
            "issue_report": {
                "recommended_privacy_mode": str,
                "current_privacy_mode": str,
                "safe_to_paste_after_review": bool,
                "safe_sections": list,
                "safe_fields": list,
                "cli_hint_fields": list,
                "do_not_add": list,
                "note": str,
            },
        },
    },
}
