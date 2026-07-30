"""Canonical integer-measurement domain validation."""

from __future__ import annotations

from .time import INT64_MAX


class MeasurementValueError(ValueError):
    """A measurement is not a nonnegative signed-64-bit integer."""


def validate_nonnegative_measurement(
    value: object,
    *,
    allow_none: bool = True,
) -> int | None:
    """Return a nonnegative int64 measurement while preserving missingness."""

    if value is None:
        if allow_none:
            return None
        raise MeasurementValueError("measurement is required")
    if type(value) is not int or not 0 <= value <= INT64_MAX:
        raise MeasurementValueError("measurement must be a nonnegative signed 64-bit integer")
    return value


validate_nonnegative_int64 = validate_nonnegative_measurement
