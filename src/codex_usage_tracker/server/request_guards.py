"""Request guard helpers for the local dashboard HTTP server."""

from __future__ import annotations

import hmac
from typing import Protocol
from urllib.parse import urlparse

from codex_usage_tracker.server.utils import (
    allowed_loopback_host,
    first_query_value,
    host_header_name,
)


class HeaderLookup(Protocol):
    """Minimal header lookup protocol used by SimpleHTTPRequestHandler."""

    def get(self, name: str, default: str | None = None) -> str | None:
        """Return a header value when present."""


def request_origin_allowed(headers: HeaderLookup, server_port: int) -> bool:
    """Return whether Host and Origin headers are local-dashboard safe."""
    if not allowed_loopback_host(host_header_name(headers.get("Host"))):
        return False
    origin = headers.get("Origin")
    if not origin:
        return True
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"}:
        return False
    if not allowed_loopback_host(parsed.hostname):
        return False
    return parsed.port is None or parsed.port == server_port


def has_valid_api_token(
    headers: HeaderLookup,
    params: dict[str, list[str]],
    api_token: str,
) -> bool:
    """Validate API token from header first, then query string fallback."""
    provided = headers.get("X-Codex-Usage-Token") or first_query_value(params.get("api_token")) or ""
    return hmac.compare_digest(str(provided), api_token)
