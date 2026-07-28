"""Frozen six-tool MCP catalog and public input schemas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..schema_catalog import SCHEMAS

FORBIDDEN_TOOL_NAMES = frozenset(
    {
        "usage_analyze",
        "generate_usage_dashboard",
        "usage_admin",
        "usage_export",
        "usage_open_dashboard",
    }
)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


TOOL_SPECS = tuple(
    ToolSpec(name, description, SCHEMAS[name])
    for name, description in (
        (
            "usage_status",
            "Return the current committed kernel generation and refresh state.",
        ),
        (
            "usage_refresh",
            "Start or join one durable incremental refresh job.",
        ),
        (
            "usage_query",
            "Run one bounded generation-consistent query batch using closed "
            "named templates such as top_threads or explicit typed requests; "
            "optionally return compact guidance.",
        ),
        (
            "usage_evidence",
            "Resolve one logical selector to bounded exact evidence.",
        ),
        (
            "usage_allowance",
            "Return exact allowance observations, deterministic reset-aware "
            "local ratios, and source-stamped estimates.",
        ),
        (
            "usage_job_status",
            "Return one internally consistent refresh job snapshot.",
        ),
    )
)
