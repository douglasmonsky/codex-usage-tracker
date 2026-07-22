"""Shared MCP response envelope."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from codex_usage_tracker.core.contracts.common import (
    AccountingContextV1,
    FreshnessV1,
    MessageV1,
    NextActionV1,
    ScopeV1,
    ToolDataClass,
)
from codex_usage_tracker.core.contracts.serialization import payload_mapping

_REQUEST_ID_PATTERN = re.compile(r"req-[0-9a-f]{32}\Z")


@dataclass(frozen=True)
class McpEnvelopeV1:
    """Versioned additive wrapper around one core tool result."""

    schema: Literal["codex-usage-tracker.mcp-envelope.v1"] = field(
        default="codex-usage-tracker.mcp-envelope.v1", init=False
    )
    tool: str
    request_id: str
    generated_at: str
    source_revision: str | None
    freshness: FreshnessV1
    scope: ScopeV1
    data_class: ToolDataClass
    accounting: AccountingContextV1
    warnings: tuple[MessageV1, ...]
    limitations: tuple[MessageV1, ...]
    result_schema: str
    result: object
    dashboard_targets: tuple[Mapping[str, object], ...]
    next_actions: tuple[NextActionV1, ...]


def envelope_payload(
    *,
    tool: str,
    result_schema: str,
    result: object,
    scope: ScopeV1,
    freshness: FreshnessV1,
    accounting: AccountingContextV1,
    data_class: ToolDataClass,
    warnings: Sequence[MessageV1] = (),
    limitations: Sequence[MessageV1] = (),
    dashboard_targets: Sequence[Mapping[str, object]] = (),
    next_actions: Sequence[NextActionV1] = (),
    request_id: str | None = None,
) -> dict[str, object]:
    """Build a finite, recursively sorted MCP envelope payload."""
    resolved_request_id = request_id or f"req-{uuid.uuid4().hex}"
    if not _REQUEST_ID_PATTERN.fullmatch(resolved_request_id):
        raise ValueError("request_id must match req-[0-9a-f]{32}")
    if not tool or not result_schema:
        raise ValueError("tool and result_schema must not be empty")
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    envelope = McpEnvelopeV1(
        tool=tool,
        request_id=resolved_request_id,
        generated_at=generated_at,
        source_revision=freshness.source_revision,
        freshness=freshness,
        scope=scope,
        data_class=data_class,
        accounting=accounting,
        warnings=tuple(warnings),
        limitations=tuple(limitations),
        result_schema=result_schema,
        result=result,
        dashboard_targets=tuple(dashboard_targets),
        next_actions=tuple(next_actions),
    )
    return payload_mapping(envelope)
