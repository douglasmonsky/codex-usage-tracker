"""Validation for the canonical interactive query allowlist."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import cast

from codex_usage_tracker.application.errors import RequestValidationError
from codex_usage_tracker.application.query_models import (
    ALL_QUERY_MEASURES,
    QUERY_ENTITY_CAPABILITIES,
    QueryEntity,
    QueryFilters,
    QueryMeasure,
    QueryRequest,
)

MAX_CURSOR_CHARS = 2048


class QueryValidationError(RequestValidationError):
    """Raised when an interactive query escapes the declared allowlist."""


def validate_query_request(request: QueryRequest) -> QueryRequest:
    capability = QUERY_ENTITY_CAPABILITIES.get(request.entity)
    if capability is None:
        raise QueryValidationError(f"unsupported entity: {request.entity}")
    if not request.measures:
        raise QueryValidationError("measures must not be empty")
    for measure in request.measures:
        if measure not in ALL_QUERY_MEASURES or measure not in capability.measures:
            raise QueryValidationError(f"unsupported measure for {request.entity}: {measure}")
    if len(set(request.measures)) != len(request.measures):
        raise QueryValidationError("measures must not contain duplicates")
    unsupported_groups = set(request.group_by) - capability.group_by
    if unsupported_groups:
        raise QueryValidationError(f"unsupported group_by for {request.entity}")
    sortable_measures = tuple(
        measure
        for measure in request.measures
        if measure not in {"estimated_cost", "estimated_credits"}
    )
    allowed_order = {capability.identity, *request.group_by, *sortable_measures}
    order_by = request.order_by or (
        sortable_measures[0] if sortable_measures else capability.identity
    )
    if order_by not in allowed_order:
        raise QueryValidationError(f"unsupported order_by for {request.entity}: {order_by}")
    if request.order not in {"asc", "desc"}:
        raise QueryValidationError("order must be asc or desc")
    if request.history not in {"active", "all"}:
        raise QueryValidationError("history must be active or all")
    if type(request.limit) is not int or not 1 <= request.limit <= 200:
        raise QueryValidationError("limit must be between 1 and 200")
    filters = _normalized_filters(request)
    if request.cursor is not None:
        decode_cursor(request.cursor)
    return replace(
        request,
        entity=cast(QueryEntity, request.entity),
        measures=cast(tuple[QueryMeasure, ...], tuple(request.measures)),
        filters=filters,
        order_by=order_by,
    )


def _normalized_filters(request: QueryRequest) -> QueryFilters:
    filters = request.filters
    if filters.range is not None:
        raise QueryValidationError("range filters are not supported")
    since = _timestamp(filters.since, "since")
    until = _timestamp(filters.until, "until")
    if since is not None and until is not None and since > until:
        raise QueryValidationError("since must not be after until")
    return replace(
        filters,
        since=_canonical_timestamp(since),
        until=_canonical_timestamp(until),
        model=_text(filters.model),
        effort=_text(filters.effort),
        thread_key=_text(filters.thread_key),
        project=_text(filters.project),
        origin=_text(filters.origin),
        service_tier=_text(filters.service_tier),
        subagent_role=_text(filters.subagent_role),
        subagent_type=_text(filters.subagent_type),
        parent_thread_key=_text(filters.parent_thread_key),
    )


def _timestamp(value: str | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise QueryValidationError(f"{field_name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise QueryValidationError(f"{field_name} must include a timezone")
    return parsed


def _canonical_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def decode_cursor(token: str) -> dict[str, object]:
    if not token or len(token) > MAX_CURSOR_CHARS:
        raise QueryValidationError("cursor is malformed")
    try:
        padding = "=" * (-len(token) % 4)
        decoded = base64.b64decode(token + padding, altchars=b"-_", validate=True)
        payload = json.loads(decoded)
    except (binascii.Error, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QueryValidationError("cursor is malformed") from exc
    if not isinstance(payload, dict) or payload.get("v") != 1:
        raise QueryValidationError("cursor is malformed")
    return payload
