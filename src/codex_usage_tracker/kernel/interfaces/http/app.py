"""Versioned transport-independent HTTP application."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit

from ...application import KernelApplication
from ...live import parse_last_event_id, validate_loopback_origin

API_PREFIX = "/api/kernel/v1"
ROUTES = {
    ("GET", f"{API_PREFIX}/status"): "status",
    ("POST", f"{API_PREFIX}/refresh"): "refresh",
    ("POST", f"{API_PREFIX}/query"): "query",
    ("POST", f"{API_PREFIX}/evidence"): "evidence",
    ("GET", f"{API_PREFIX}/allowance"): "allowance",
    ("GET", f"{API_PREFIX}/jobs/{{job_id}}"): "job_status",
    ("GET", f"{API_PREFIX}/events"): "events",
}
MAX_BODY_BYTES = 1_048_576


@dataclass(frozen=True)
class HttpResponse:
    status: int
    content_type: str
    body: bytes
    headers: tuple[tuple[str, str], ...] = ()


class HttpApp:
    def __init__(self, application: KernelApplication) -> None:
        self._application = application

    def handle(
        self,
        method: str,
        target: str,
        *,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        request_headers = {key.lower(): value for key, value in (headers or {}).items()}
        try:
            validate_loopback_request(
                request_headers.get("host"),
                request_headers.get("origin"),
            )
            return self._dispatch(
                method.upper(),
                target,
                body=body,
                headers=request_headers,
            )
        except sqlite3.Error:
            return _json_response(503, {"error": "kernel cache is unavailable"})
        except (json.JSONDecodeError, OSError, RuntimeError, ValueError) as exc:
            return _json_response(400, {"error": str(exc)})

    def _dispatch(
        self,
        method: str,
        target: str,
        *,
        body: bytes,
        headers: dict[str, str],
    ) -> HttpResponse:
        parsed = urlsplit(target)
        path = parsed.path
        query = parse_qs(parsed.query, keep_blank_values=True)
        if method == "GET" and path == f"{API_PREFIX}/status":
            return _json_response(200, self._application.status())
        if method == "POST" and path == f"{API_PREFIX}/refresh":
            payload = _json_body(body)
            return _json_response(
                202,
                self._application.refresh(
                    wait_seconds=_float(payload.get("wait_seconds", 0))
                ),
            )
        if method == "POST" and path == f"{API_PREFIX}/query":
            return _json_response(200, self._application.query(_json_body(body)))
        if method == "POST" and path == f"{API_PREFIX}/evidence":
            return _json_response(200, self._application.evidence(_json_body(body)))
        if method == "GET" and path == f"{API_PREFIX}/allowance":
            return _json_response(
                200,
                self._application.allowance(
                    {
                        "limit": _query_int(query, "limit", 100),
                        "cursor": _query_optional(query, "cursor"),
                    }
                ),
            )
        job_prefix = f"{API_PREFIX}/jobs/"
        if method == "GET" and path.startswith(job_prefix):
            job_id = path.removeprefix(job_prefix)
            return _json_response(
                200,
                self._application.job_status(
                    job_id,
                    wait_seconds=_query_float(query, "wait_seconds", 0),
                    include_result=_query_bool(query, "include_result", False),
                ),
            )
        if method == "GET" and path == f"{API_PREFIX}/events":
            frames = self._application.live(
                last_event_id=parse_last_event_id(headers.get("last-event-id")),
                limit=_query_int(query, "limit", 100),
                origin=headers.get("origin"),
            )
            return HttpResponse(
                200,
                "text/event-stream",
                "".join(frames).encode(),
                (
                    ("Cache-Control", "no-cache"),
                    ("X-Accel-Buffering", "no"),
                ),
            )
        return _json_response(404, {"error": "kernel route not found"})


def validate_loopback_request(host: str | None, origin: str | None) -> None:
    if host is None:
        raise ValueError("Host header is required")
    parsed = urlsplit(f"//{host}")
    if (
        parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("kernel HTTP requires a loopback Host")
    validate_loopback_origin(origin)


def _json_body(body: bytes) -> dict[str, Any]:
    if len(body) > MAX_BODY_BYTES:
        raise ValueError("request body is too large")
    payload = json.loads(body or b"{}")
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    return payload


def _json_response(status: int, payload: dict[str, Any]) -> HttpResponse:
    return HttpResponse(
        status,
        "application/json",
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode() + b"\n",
        (("Cache-Control", "no-store"),),
    )


def _query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    if len(values) != 1:
        raise ValueError(f"{key} must appear once")
    return values[0]


def _query_optional(query: dict[str, list[str]], key: str) -> str | None:
    return _query_value(query, key)


def _query_int(query: dict[str, list[str]], key: str, default: int) -> int:
    raw = _query_value(query, key)
    if raw is None:
        return default
    if not raw.isascii() or not raw.isdigit():
        raise ValueError(f"{key} must be an integer")
    return int(raw)


def _query_float(query: dict[str, list[str]], key: str, default: float) -> float:
    raw = _query_value(query, key)
    return default if raw is None else _float(raw)


def _query_bool(query: dict[str, list[str]], key: str, default: bool) -> bool:
    raw = _query_value(query, key)
    if raw is None:
        return default
    if raw not in {"0", "1", "false", "true"}:
        raise ValueError(f"{key} must be boolean")
    return raw in {"1", "true"}


def _float(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("wait_seconds must be numeric")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("wait_seconds must be numeric") from exc
