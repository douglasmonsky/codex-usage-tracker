"""Stable JSON contracts for spec-first visualization MCP tools."""

from __future__ import annotations

VISUALIZATION_JSON_PAYLOAD_CONTRACTS = {
    "codex-usage-tracker-visualization-suggestions-v1": {
        "required": {
            "question": str,
            "scope": str,
            "summary": dict,
            "suggestions": list,
            "includes_indexed_content": bool,
            "includes_raw_fragments": bool,
        },
    },
    "codex-usage-tracker-visualization-result-v1": {
        "required": {
            "format": str,
            "kind": str,
            "source_schema": str,
            "visualization": dict,
            "evidence": dict,
            "narrative": dict,
            "caveats": list,
            "artifact_rendering": dict,
            "includes_indexed_content": bool,
            "includes_raw_fragments": bool,
        },
    },
}
