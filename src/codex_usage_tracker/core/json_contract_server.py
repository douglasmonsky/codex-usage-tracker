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
    "codex-usage-tracker-status-v1": {
        "required": {
            "payload_schema": str,
            "latest_refresh_at": (str, NoneType),
            "include_archived": bool,
            "row_counts": dict,
            "max_event_timestamp": (str, NoneType),
            "parser_diagnostics": dict,
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
