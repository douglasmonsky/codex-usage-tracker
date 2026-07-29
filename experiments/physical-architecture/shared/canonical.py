from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_bytes(value: object) -> bytes:
    """Return the CK-03 canonical JSON representation."""
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def load_canonical_object(payload: bytes, *, artifact: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{artifact} is not valid UTF-8 canonical JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{artifact} must contain one JSON object")
    if payload != canonical_json_bytes(value):
        raise ValueError(f"{artifact} is not encoded as canonical JSON")
    return value
