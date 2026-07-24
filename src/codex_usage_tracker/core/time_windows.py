"""Timezone-aware request window normalization without application dependencies."""

from __future__ import annotations

from datetime import datetime, timezone

from codex_usage_tracker.core.errors import RequestValidationError


def normalize_timestamp_window(
    since: str | None,
    until: str | None,
    *,
    field_prefix: str = "",
    error_type: type[RequestValidationError] = RequestValidationError,
) -> tuple[str | None, str | None]:
    """Validate, order, and UTC-normalize a bounded timestamp window."""
    since_value = _timestamp(since, f"{field_prefix}since", error_type)
    until_value = _timestamp(until, f"{field_prefix}until", error_type)
    if since_value is not None and until_value is not None and since_value > until_value:
        raise error_type(f"{field_prefix}since must not be after {field_prefix}until")
    return _canonical_timestamp(since_value), _canonical_timestamp(until_value)


def _timestamp(
    value: str | None,
    field_name: str,
    error_type: type[RequestValidationError],
) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise error_type(f"{field_name} must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise error_type(f"{field_name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise error_type(f"{field_name} must include a timezone")
    return parsed


def _canonical_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
