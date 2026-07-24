"""Small JSON serialization helpers shared by MCP adapters."""

from __future__ import annotations

import json
from collections.abc import Mapping


def copy_json_object(value: Mapping[str, object]) -> dict[str, object]:
    """Return a detached JSON-compatible object."""
    return json.loads(json.dumps(value))


def pretty_json(value: object) -> str:
    """Serialize an MCP text result with stable human-readable indentation."""
    return json.dumps(value, indent=2)
