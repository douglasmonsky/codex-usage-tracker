"""Exact, JSON-safe normalization shared by CK-07A test-only consumers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any


def normalize_exact(value: Any) -> Any:
    if isinstance(value, Decimal):
        rendered = format(value.normalize(), "f")
        return "0" if rendered == "-0" else rendered
    if isinstance(value, Mapping):
        return {
            str(key): normalize_exact(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [normalize_exact(item) for item in value]
    return value


def exact_sha256(value: Any) -> str:
    payload = json.dumps(
        normalize_exact(value),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
