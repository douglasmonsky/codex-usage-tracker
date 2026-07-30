"""Integer UTC-microsecond domain validation."""

from __future__ import annotations

INT64_MIN = -(1 << 63)
INT64_MAX = (1 << 63) - 1


class TimeValueError(ValueError):
    """A timestamp is not a signed 64-bit UTC-microsecond value."""


def validate_utc_microseconds(
    value: object,
    *,
    allow_none: bool = True,
) -> int | None:
    """Return a valid signed int64 timestamp while preserving missingness."""

    if value is None:
        if allow_none:
            return None
        raise TimeValueError("UTC microseconds are required")
    if type(value) is not int or not INT64_MIN <= value <= INT64_MAX:
        raise TimeValueError("UTC microseconds must be a signed 64-bit integer")
    return value
