"""Shared CLI output helpers."""

from __future__ import annotations

import json
from typing import Any


def print_json(payload: dict[str, Any]) -> None:
    """Print a stable JSON payload for CLI consumers."""
    print(json.dumps(payload, indent=2, sort_keys=True, default=str), flush=True)
