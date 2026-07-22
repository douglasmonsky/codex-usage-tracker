"""Stable adapters for the core MCP tool profile."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from codex_usage_tracker.application.requests import StatusRequest
from codex_usage_tracker.application.status import STATUS_SCHEMA, _build_status
from codex_usage_tracker.core.contracts import (
    MessageV1,
    NextActionV1,
    enforce_payload_budget,
    envelope_payload,
)
from codex_usage_tracker.core.paths import DEFAULT_CODEX_HOME, DEFAULT_DB_PATH, DEFAULT_PRICING_PATH
from codex_usage_tracker.interfaces.mcp.models import McpProfile

MAX_STATUS_PAYLOAD_BYTES = 16 * 1024


def usage_status() -> dict[str, object]:
    """Return McpEnvelopeV1 containing status.v2."""
    return build_usage_status()


def build_usage_status(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    codex_home: Path = DEFAULT_CODEX_HOME,
    home: Path | None = None,
    profile: str = "core",
) -> dict[str, object]:
    """Build the core status envelope with explicit testable local dependencies."""
    request = StatusRequest(
        db_path=db_path,
        pricing_path=pricing_path,
        codex_home=codex_home,
        home=home or Path.home(),
        mcp_profile=cast(McpProfile, profile),
    )
    result, context = _build_status(request)
    next_action = cast(dict[str, object], result["next_action"])
    payload = envelope_payload(
        tool="usage_status",
        result_schema=STATUS_SCHEMA,
        result=result,
        scope=context.scope,
        freshness=context.freshness,
        accounting=context.accounting,
        data_class="administrative",
        limitations=(
            MessageV1(
                code="mcp.current_task_exposure_unverified",
                severity="info",
                message="Current-task MCP tool exposure is not verified by this status call.",
            ),
        ),
        next_actions=(
            NextActionV1(
                code=cast(str, next_action["code"]),
                label=cast(str, next_action["label"]),
                tool=cast(str | None, next_action["tool"]),
                arguments=cast(dict[str, object], next_action["arguments"]),
            ),
        ),
    )
    enforce_payload_budget(payload, MAX_STATUS_PAYLOAD_BYTES, "usage_status")
    return payload
