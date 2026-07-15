"""Server Json Payload Contracts JSON payload contracts."""

from __future__ import annotations

from typing import Any

NoneType = type(None)
Number = (int, float)

SERVER_JSON_PAYLOAD_CONTRACTS: dict[str, dict[str, Any]] = {
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
    "codex-usage-tracker-context-settings-v1": {
        "required": {
            "context_api_enabled": bool,
            "raw_context_persisted": bool,
        }
    },
    "codex-usage-tracker-open-investigator-v1": {
        "required": {
            "opened": bool,
            "url": str,
        }
    },
    "codex-usage-tracker-live-api-v1": {"required": {}},
    "codex-usage-tracker-async-job-status-v1": {
        "required": {
            "job_id": str,
            "job_type": str,
            "status": str,
            "percent_complete": int,
        }
    },
    "codex-usage-tracker-analysis-job-v1": {
        "required": {
            "job_id": str,
            "status": str,
            "stage": str,
            "error": (dict, NoneType),
            "next": dict,
        },
        "nested": {
            "progress": {
                "completed_units": int,
                "total_units": (int, NoneType),
                "percent": (float, NoneType),
                "current_unit": (str, NoneType),
            },
            "cache": {"request_reused": str},
        },
    },
    "codex-usage-tracker-allowance-status-v2": {
        "required": {
            "revision": str,
            "changed": bool,
            "quality": dict,
            "next": dict,
        }
    },
    "codex-usage-tracker-allowance-series-v2": {
        "required": {
            "model_version": str,
            "generated_at": str,
            "revision": (str, NoneType),
            "requested_range": dict,
            "available_range": dict,
            "granularity": str,
            "truncated": bool,
            "downsampled": bool,
            "quality": dict,
            "points": list,
            "cycles": list,
            "capacity_history": dict,
        }
    },
    "codex-usage-tracker-allowance-evidence-v2": {
        "required": {
            "model_version": str,
            "generated_at": str,
            "revision": (str, NoneType),
            "privacy_mode": str,
            "rows": list,
            "next_cursor": (str, NoneType),
            "copied_rows_excluded": int,
            "provenance": str,
            "offline_export_action": str,
        }
    },
    "codex-usage-tracker-allowance-analysis-v2": {
        "required": {
            "status": str,
            "snapshot_id": str,
            "source_revision": str,
            "model_version": str,
            "rate_card_revision": str,
            "parameters": dict,
        }
    },
    "codex-usage-tracker-compression-api-v1": {
        "required": {
            "kind": str,
            "versions": dict,
            "run_id": (str, NoneType),
            "status": str,
            "source_revision": str,
            "scope": dict,
            "filters": dict,
            "include_archived": bool,
            "coverage": dict,
            "timing": dict,
            "cache": dict,
            "content_mode": str,
            "includes_indexed_content": bool,
            "includes_raw_fragments": bool,
            "warnings": list,
            "caveats": list,
            "payload_truncated": bool,
            "next": dict,
        }
    },
    "codex-usage-tracker-status-v1": {
        "required": {
            "payload_schema": str,
            "latest_refresh_at": (str, NoneType),
            "include_archived": bool,
            "row_counts": dict,
            "max_event_timestamp": (str, NoneType),
            "parser_diagnostics": dict,
            "dedupe": dict,
        }
    },
    "codex-usage-tracker-calls-v1": {
        "required": {
            "rows": list,
            "row_count": int,
            "total_matched_rows": int,
            "limit": (int, NoneType),
            "offset": int,
            "has_more": bool,
            "next_offset": (int, NoneType),
            "filters": dict,
            "raw_context_included": bool,
        }
    },
    "codex-usage-tracker-call-v1": {
        "required": {
            "record": dict,
            "previous_record_id": (str, NoneType),
            "next_record_id": (str, NoneType),
            "raw_context_included": bool,
        }
    },
    "codex-usage-tracker-threads-v1": {
        "required": {
            "rows": list,
            "row_count": int,
            "limit": (int, NoneType),
            "offset": int,
            "include_archived": bool,
            "raw_context_included": bool,
        }
    },
    "codex-usage-tracker-thread-calls-v1": {
        "required": {
            "thread_key": str,
            "rows": list,
            "row_count": int,
            "total_matched_rows": int,
            "limit": (int, NoneType),
            "offset": int,
            "has_more": bool,
            "next_offset": (int, NoneType),
            "raw_context_included": bool,
        }
    },
    "codex-usage-tracker-reports-pack-v1": {
        "required": {
            "reports": list,
            "evidence": dict,
            "row_count": int,
            "total_matched_rows": int,
            "limit": (int, NoneType),
            "offset": int,
            "filters": dict,
            "raw_context_included": bool,
        }
    },
}
