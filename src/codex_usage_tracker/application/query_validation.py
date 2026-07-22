"""Validation for the canonical interactive query allowlist."""

from __future__ import annotations

import base64
import binascii
import json
import math
import re
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
MAX_CURSOR_IDENTITY_CHARS = 1024
MAX_CURSOR_REVISION_CHARS = 256
MAX_CURSOR_SORT_TEXT_CHARS = 1024
_CURSOR_KEYS = {"v", "f", "r", "s", "i"}
_FINGERPRINT_PATTERN = re.compile(r"[0-9a-f]{64}")
_REVISION_PATTERN = re.compile(r"[!-~]{1,256}")


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
        cursor = decode_cursor(request.cursor)
        _validate_cursor_sort_for_order(cursor["s"], order_by, request.measures)
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
    since, until = normalize_timestamp_window(filters.since, filters.until)
    return replace(
        filters,
        since=since,
        until=until,
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


def normalize_timestamp_window(
    since: str | None, until: str | None, *, field_prefix: str = ""
) -> tuple[str | None, str | None]:
    """Validate, order, and UTC-normalize a bounded timestamp window."""
    since_value = _timestamp(since, f"{field_prefix}since")
    until_value = _timestamp(until, f"{field_prefix}until")
    if since_value is not None and until_value is not None and since_value > until_value:
        raise QueryValidationError(f"{field_prefix}since must not be after {field_prefix}until")
    return _canonical_timestamp(since_value), _canonical_timestamp(until_value)


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
    if not isinstance(token, str) or not token or len(token) > MAX_CURSOR_CHARS:
        raise QueryValidationError("cursor.encoding is malformed")
    try:
        padding = "=" * (-len(token) % 4)
        decoded = base64.b64decode(token + padding, altchars=b"-_", validate=True)
        payload = json.loads(decoded)
    except (binascii.Error, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QueryValidationError("cursor.encoding is malformed") from exc
    if not isinstance(payload, dict) or set(payload) != _CURSOR_KEYS:
        raise QueryValidationError("cursor.structure is malformed")
    if type(payload["v"]) is not int or payload["v"] != 1:
        raise QueryValidationError("cursor.v is malformed")
    fingerprint = payload["f"]
    if not isinstance(fingerprint, str) or _FINGERPRINT_PATTERN.fullmatch(fingerprint) is None:
        raise QueryValidationError("cursor.f is malformed")
    revision = payload["r"]
    if revision is not None and (
        not isinstance(revision, str)
        or len(revision) > MAX_CURSOR_REVISION_CHARS
        or _REVISION_PATTERN.fullmatch(revision) is None
    ):
        raise QueryValidationError("cursor.r is malformed")
    if not _valid_cursor_sort(payload["s"]):
        raise QueryValidationError("cursor.s is malformed")
    identity = payload["i"]
    if not isinstance(identity, str) or not identity or len(identity) > MAX_CURSOR_IDENTITY_CHARS:
        raise QueryValidationError("cursor.i is malformed")
    return payload


def _valid_cursor_sort(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return -(2**63) <= value <= 2**63 - 1
    if isinstance(value, float):
        return math.isfinite(value)
    return isinstance(value, str) and len(value) <= MAX_CURSOR_SORT_TEXT_CHARS


def _validate_cursor_sort_for_order(
    value: object, order_by: str, measures: tuple[QueryMeasure, ...]
) -> None:
    if value is None:
        return
    if order_by in measures:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise QueryValidationError("cursor.s is malformed for numeric ordering")
        return
    if not isinstance(value, str):
        raise QueryValidationError("cursor.s is malformed for text ordering")
