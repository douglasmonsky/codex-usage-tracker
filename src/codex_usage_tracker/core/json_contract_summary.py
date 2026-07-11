"""Stable JSON contract for aggregate usage summaries."""

from __future__ import annotations

SUMMARY_JSON_PAYLOAD_CONTRACTS = {
    "codex-usage-tracker-summary-v1": {
        "required": {
            "group_by": str,
            "is_expensive": bool,
            "include_archived": bool,
            "privacy_mode": str,
            "row_count": int,
            "rows": list,
        }
    }
}
