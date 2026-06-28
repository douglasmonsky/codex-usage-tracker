"""Value conversion and redaction helpers for context evidence."""

from __future__ import annotations

import json

from codex_usage_tracker.redaction import redact_secrets


def redact_text(text: str) -> str:
    return redact_secrets(text)


def redact_json_value(value: object) -> object:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): redact_json_value(item) for key, item in value.items()}
    return value


def compact_json(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return str(value)


def content_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return _content_list_text(value)
    return jsonish(value)


def jsonish(value: object) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True)
    except TypeError:
        return str(value)


def positive_int(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def nonnegative_int(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def nonnegative_float(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _content_list_text(value: list[object]) -> str:
    pieces: list[str] = []
    for item in value:
        if isinstance(item, str):
            pieces.append(item)
        if isinstance(item, dict):
            text = item.get("text") or item.get("content")
            if isinstance(text, str):
                pieces.append(text)
    return "\n".join(piece for piece in pieces if piece)
