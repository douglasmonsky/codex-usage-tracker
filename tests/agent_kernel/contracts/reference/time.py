from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MIN_INT64 = -(2**63)
_MAX_INT64 = 2**63 - 1
_FRACTIONAL_SECONDS = re.compile(
    r"[.,](?P<digits>[0-9]+)(?:Z|[+-][0-9]{2}:[0-9]{2})?$"
)


class TimeContractError(ValueError):
    """Raised when a timestamp cannot satisfy the logical time contract."""


def ensure_int64(value: int) -> int:
    """Return a non-boolean signed 64-bit integer or fail closed."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise TimeContractError("timestamp is not a signed 64-bit integer")
    if value < _MIN_INT64 or value > _MAX_INT64:
        raise TimeContractError("timestamp exceeds signed 64-bit range")
    return value


def _datetime_us(value: datetime) -> int:
    delta = value.astimezone(timezone.utc) - _EPOCH
    return ensure_int64(
        (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
    )


def _require_microsecond_precision(value: str) -> None:
    match = _FRACTIONAL_SECONDS.search(value)
    if match is not None and len(match.group("digits")) > 6:
        raise TimeContractError("timestamp exceeds exact microsecond precision")


def parse_instant_us(value: str) -> int:
    """Parse an exact offset-bearing ISO instant without floating-point math."""

    _require_microsecond_precision(value)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        instant = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise TimeContractError("invalid documented timestamp") from exc
    if instant.tzinfo is None:
        raise TimeContractError("timestamp lacks an explicit UTC offset")
    return _datetime_us(instant)


def local_datetime_to_utc_us(
    value: str,
    timezone_name: str,
    *,
    fold: int | None = None,
) -> int:
    """Resolve an IANA-zone wall time, requiring an explicit DST fold when needed."""

    _require_microsecond_precision(value)
    try:
        naive = datetime.fromisoformat(value)
    except ValueError as exc:
        raise TimeContractError("invalid local calendar timestamp") from exc
    if naive.tzinfo is not None:
        raise TimeContractError("calendar timestamp must not include an offset")
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise TimeContractError("unknown IANA timezone") from exc

    candidates: list[tuple[int, int]] = []
    for candidate_fold in (0, 1):
        aware = naive.replace(tzinfo=zone, fold=candidate_fold)
        utc = aware.astimezone(timezone.utc)
        round_trip = utc.astimezone(zone)
        if round_trip.replace(tzinfo=None) == naive:
            candidate = (candidate_fold, _datetime_us(utc))
            if candidate[1] not in {item[1] for item in candidates}:
                candidates.append(candidate)
    if not candidates:
        raise TimeContractError("nonexistent DST local time")
    if len(candidates) > 1 and fold is None:
        raise TimeContractError("ambiguous DST local time requires fold")
    if fold is not None and fold not in {0, 1}:
        raise TimeContractError("DST fold must be 0 or 1")
    if fold is None:
        return candidates[0][1]
    for candidate_fold, candidate_us in candidates:
        if candidate_fold == fold:
            return candidate_us
    raise TimeContractError("requested DST fold is not valid for local time")


def _source_order_key(source_order: list[Any]) -> tuple[tuple[int, Any], ...]:
    normalized: list[tuple[int, Any]] = []
    for part in source_order:
        if isinstance(part, bool):
            normalized.append((2, int(part)))
        elif isinstance(part, int):
            normalized.append((0, part))
        elif isinstance(part, str):
            normalized.append((1, part))
        else:
            raise TimeContractError("source order contains an unsupported type")
    return tuple(normalized)


def event_order_key(event: dict[str, Any]) -> tuple[Any, ...]:
    """Return the physical-independent total-order key.

    Missing event time remains missing and sorts after observed instants; source
    order then preserves deterministic adapter order without inventing a time.
    """

    event_at_us = event.get("event_at_us")
    time_key = (
        (1, 0) if event_at_us is None else (0, ensure_int64(event_at_us))
    )
    return (
        *time_key,
        _source_order_key(event["source_order"]),
        int(event["event_kind_order"]),
        str(event["logical_id"]),
    )
