"""Strict JSON decoding and contract serialization for the HTTP adapter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from types import MappingProxyType
from typing import Any, BinaryIO


class HttpRequestError(ValueError):
    """A bounded client error safe to return through the localhost API."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def decode_json_object(body: bytes, *, content_type: str, max_bytes: int) -> dict[str, object]:
    """Decode one bounded JSON object without accepting transport ambiguity."""
    if content_type.split(";", 1)[0].strip().lower() != "application/json":
        raise HttpRequestError(
            415, "unsupported_media_type", "Content-Type must be application/json"
        )
    if len(body) > max_bytes:
        raise HttpRequestError(413, "request_too_large", f"request body exceeds {max_bytes} bytes")
    try:
        payload = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_non_finite,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise HttpRequestError(400, "invalid_json", "request body must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise HttpRequestError(400, "invalid_request", "request body must be a JSON object")
    return payload


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def read_bounded_body(
    stream: BinaryIO,
    *,
    content_length: str | None,
    max_bytes: int,
) -> bytes:
    """Read exactly one declared request body without an unbounded socket read."""
    if content_length is None:
        raise HttpRequestError(411, "length_required", "Content-Length is required")
    try:
        length = int(content_length)
    except ValueError as exc:
        raise HttpRequestError(400, "invalid_request", "Content-Length must be an integer") from exc
    if length < 0:
        raise HttpRequestError(400, "invalid_request", "Content-Length must be non-negative")
    if length > max_bytes:
        raise HttpRequestError(413, "request_too_large", f"request body exceeds {max_bytes} bytes")
    body = stream.read(length)
    if len(body) != length:
        raise HttpRequestError(400, "invalid_request", "request body ended before Content-Length")
    return body


def serialize_http_payload(value: object) -> dict[str, object]:
    """Convert one typed application result into plain deterministic JSON values."""
    converted = _json_value(value)
    if not isinstance(converted, dict):
        raise TypeError("HTTP application results must serialize to a JSON object")
    return converted


def _json_value(value: object) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, (Mapping, MappingProxyType)):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"unsupported HTTP result value: {type(value).__name__}")
