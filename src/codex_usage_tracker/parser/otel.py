"""Pure, aggregate-only parsing for Codex OTLP completion logs."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast

OTEL_DIAGNOSTIC_KEYS = (
    "otel_invalid_json",
    "otel_invalid_record",
    "otel_invalid_integer",
    "otel_unsupported_version",
    "otel_non_completion",
)

_ALLOWED_ATTRIBUTES = frozenset(
    {
        "event.name",
        "event.kind",
        "conversation.id",
        "input_token_count",
        "cached_token_count",
        "output_token_count",
        "reasoning_token_count",
        "model",
        "model_reasoning_effort",
        "service_tier",
        "app.version",
    }
)
_TOKEN_FIELDS = (
    "input_token_count",
    "cached_token_count",
    "output_token_count",
    "reasoning_token_count",
)
_STRING_FIELDS = frozenset(
    {
        "event.name",
        "event.kind",
        "conversation.id",
        "model",
        "model_reasoning_effort",
        "service_tier",
        "app.version",
    }
)
_VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$")
_STANDARD_BY_OMISSION_VERSION = (0, 143, 0)
_INVALID = object()


@dataclass(frozen=True)
class OtelCompletion:
    fingerprint: str
    conversation_id: str | None
    event_timestamp: str | None
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    reasoning_output_tokens: int | None
    model: str | None
    effort: str | None
    service_tier: str | None
    fast: int | None
    service_tier_source: str | None
    service_tier_confidence: str | None
    app_version: str | None
    match_status: str


@dataclass(frozen=True)
class OtelParseResult:
    completions: Sequence[OtelCompletion]
    diagnostics: dict[str, int]


def parse_otlp_json_line(raw: str) -> OtelParseResult:
    """Parse one OTLP JSON line without retaining bodies or arbitrary attributes."""

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return OtelParseResult((), {"otel_invalid_json": 1})
    if not isinstance(payload, dict):
        return OtelParseResult((), {"otel_invalid_record": 1})

    completions: list[OtelCompletion] = []
    diagnostics: Counter[str] = Counter()
    for record in _log_records(cast(dict[str, object], payload), diagnostics):
        attributes, invalid_fields = _allowlisted_attributes(
            record.get("attributes"), diagnostics
        )
        semantic_type_errors = {
            key
            for key in _STRING_FIELDS
            if key in attributes and not isinstance(attributes[key], str)
        }
        if semantic_type_errors:
            diagnostics["otel_invalid_record"] += len(semantic_type_errors)
            invalid_fields.update(semantic_type_errors)
        if (
            _text(attributes, "event.name") != "codex.sse_event"
            or _text(attributes, "event.kind") != "response.completed"
        ):
            diagnostics["otel_non_completion"] += 1
            continue
        completion, completion_diagnostics = _completion_from_attributes(
            record, attributes, invalid_fields
        )
        diagnostics.update(completion_diagnostics)
        completions.append(completion)
    return OtelParseResult(tuple(completions), dict(diagnostics))


def _log_records(
    payload: dict[str, object], diagnostics: Counter[str]
) -> Iterator[dict[str, object]]:
    resource_logs = payload.get("resourceLogs")
    if not isinstance(resource_logs, list):
        diagnostics["otel_invalid_record"] += 1
        return
    for resource_log in resource_logs:
        if not isinstance(resource_log, dict):
            diagnostics["otel_invalid_record"] += 1
            continue
        scope_logs = resource_log.get("scopeLogs")
        if not isinstance(scope_logs, list):
            diagnostics["otel_invalid_record"] += 1
            continue
        for scope_log in scope_logs:
            if not isinstance(scope_log, dict):
                diagnostics["otel_invalid_record"] += 1
                continue
            log_records = scope_log.get("logRecords")
            if not isinstance(log_records, list):
                diagnostics["otel_invalid_record"] += 1
                continue
            for record in log_records:
                if not isinstance(record, dict):
                    diagnostics["otel_invalid_record"] += 1
                    continue
                yield cast(dict[str, object], record)


def _allowlisted_attributes(
    raw_attributes: object, diagnostics: Counter[str]
) -> tuple[dict[str, object], set[str]]:
    values: dict[str, object] = {}
    invalid_fields: set[str] = set()
    if not isinstance(raw_attributes, list):
        diagnostics["otel_invalid_record"] += 1
        return values, invalid_fields
    for raw_attribute in raw_attributes:
        if not isinstance(raw_attribute, dict):
            diagnostics["otel_invalid_record"] += 1
            continue
        key = raw_attribute.get("key")
        if not isinstance(key, str) or key not in _ALLOWED_ATTRIBUTES:
            continue
        value = _otlp_value(raw_attribute.get("value"))
        if value is _INVALID:
            diagnostics["otel_invalid_record"] += 1
            invalid_fields.add(key)
            continue
        values[key] = value
    return values, invalid_fields


def _otlp_value(raw_value: object) -> object:
    if not isinstance(raw_value, dict):
        return _INVALID
    for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if key not in raw_value:
            continue
        value = raw_value[key]
        if key == "stringValue" and isinstance(value, str):
            return value
        if key == "intValue" and isinstance(value, (str, int)) and not isinstance(value, bool):
            try:
                return int(value)
            except ValueError:
                return value
        if key == "doubleValue" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
        if key == "boolValue" and isinstance(value, bool):
            return value
        return _INVALID
    return _INVALID


def _completion_from_attributes(
    record: dict[str, object],
    attributes: dict[str, object],
    invalid_fields: set[str],
) -> tuple[OtelCompletion, Counter[str]]:
    diagnostics: Counter[str] = Counter()
    conversation_id = _text(attributes, "conversation.id")
    token_values = tuple(_integer(attributes, key, diagnostics) for key in _TOKEN_FIELDS)
    input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens = token_values
    model = _text(attributes, "model")
    effort = _text(attributes, "model_reasoning_effort")
    app_version = _text(attributes, "app.version")
    service_tier, fast, service_tier_source, service_tier_confidence = _normalize_tier(
        attributes, invalid_fields, app_version, diagnostics
    )
    event_timestamp, timestamp_invalid = _event_timestamp(record)

    has_identity = conversation_id is not None and all(value is not None for value in token_values)
    has_tier = service_tier is not None and fast in (0, 1)
    match_status = "pending"
    if not has_identity or not has_tier or invalid_fields or timestamp_invalid:
        match_status = "invalid"
        diagnostics["otel_invalid_record"] += 1

    normalized: dict[str, object] = {
        "conversation_id": conversation_id,
        "event_timestamp": event_timestamp,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning_output_tokens,
        "model": model,
        "effort": effort,
        "service_tier": service_tier,
        "fast": fast,
        "service_tier_source": service_tier_source,
        "service_tier_confidence": service_tier_confidence,
        "app_version": app_version,
    }
    return (
        OtelCompletion(
            fingerprint=_semantic_fingerprint(normalized),
            conversation_id=conversation_id,
            event_timestamp=event_timestamp,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            reasoning_output_tokens=reasoning_output_tokens,
            model=model,
            effort=effort,
            service_tier=service_tier,
            fast=fast,
            service_tier_source=service_tier_source,
            service_tier_confidence=service_tier_confidence,
            app_version=app_version,
            match_status=match_status,
        ),
        diagnostics,
    )


def _text(attributes: dict[str, object], key: str) -> str | None:
    value = attributes.get(key)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _integer(
    attributes: dict[str, object], key: str, diagnostics: Counter[str]
) -> int | None:
    value = attributes.get(key)
    if isinstance(value, bool) or value is None:
        diagnostics["otel_invalid_integer"] += 1
        return None
    if not isinstance(value, str | int | float):
        diagnostics["otel_invalid_integer"] += 1
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        diagnostics["otel_invalid_integer"] += 1
        return None
    if parsed < 0 or (isinstance(value, float) and not value.is_integer()):
        diagnostics["otel_invalid_integer"] += 1
        return None
    return parsed


def _normalize_tier(
    attributes: dict[str, object],
    invalid_fields: set[str],
    app_version: str | None,
    diagnostics: Counter[str],
) -> tuple[str | None, int | None, str | None, str | None]:
    if "service_tier" in invalid_fields:
        return None, None, None, None
    raw_tier = _text(attributes, "service_tier")
    if "service_tier" in attributes:
        if raw_tier is None:
            return None, None, None, None
        normalized = raw_tier.lower()
        if normalized in {"priority", "fast"}:
            return normalized, 1, "otel_response_completed", "exact"
        return normalized, 0, "otel_response_completed", "exact"

    parsed_version = _parse_version(app_version)
    if parsed_version is None:
        diagnostics["otel_unsupported_version"] += 1
        return None, None, None, None
    if parsed_version >= _STANDARD_BY_OMISSION_VERSION:
        return "standard", 0, "otel_response_completed", "protocol"
    return None, None, None, None


def _parse_version(value: str | None) -> tuple[int, int, int] | None:
    if value is None:
        return None
    match = _VERSION_PATTERN.fullmatch(value)
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def _event_timestamp(record: dict[str, object]) -> tuple[str | None, bool]:
    raw = record.get("timeUnixNano")
    if isinstance(raw, bool) or not isinstance(raw, (str, int)):
        return None, raw is not None
    try:
        nanoseconds = int(raw)
        seconds, remainder = divmod(nanoseconds, 1_000_000_000)
        timestamp = datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None, True
    base = timestamp.strftime("%Y-%m-%dT%H:%M:%S")
    if remainder:
        return f"{base}.{remainder:09d}Z", False
    return f"{base}Z", False


def _semantic_fingerprint(normalized: dict[str, object]) -> str:
    payload = {"fingerprint_version": 1, **normalized}
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
