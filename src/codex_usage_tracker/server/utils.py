"""Pure helpers for the local dashboard HTTP server."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from ipaddress import ip_address
from time import perf_counter
from typing import Any


def first_query_value(values: list[str] | None) -> str | None:
    return values[0] if values else None


def truthy_query_value(value: str | None) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def parse_bool_query_value(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    normalized = value.lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def parse_dashboard_limit(value: str | None, default: int | None) -> int | None:
    if value is None or value == "":
        return default
    if value.lower() == "all":
        return None
    try:
        limit = int(value)
    except ValueError:
        return default
    if limit <= 0:
        return None
    return limit


def parse_dashboard_offset(value: str | None) -> int:
    if value is None or value == "":
        return 0
    try:
        offset = int(value)
    except ValueError:
        return 0
    return max(offset, 0)


def parse_api_limit(value: str | None, default: int) -> int | None:
    if value is None or value == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"all", "none", "null"}:
        return None
    try:
        limit = int(normalized)
    except ValueError as exc:
        raise ValueError("limit must be a positive integer, 0, all, or none") from exc
    if limit == 0:
        return None
    if limit < 0:
        raise ValueError("limit must be a positive integer, 0, all, or none")
    return min(limit, 10_000)


def parse_report_limit(value: str | None, default: int) -> int:
    limit = parse_api_limit(value, default)
    return 10_000 if limit is None else limit


def parse_api_offset(value: str | None) -> int:
    if value is None or value == "":
        return 0
    try:
        offset = int(value)
    except ValueError as exc:
        raise ValueError("offset must be a non-negative integer") from exc
    if offset < 0:
        raise ValueError("offset must be a non-negative integer")
    return offset


def parse_optional_float(value: str | None, name: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def optional_choice_filter(
    value: str | None,
    allowed: tuple[str, ...],
    name: str,
) -> str | None:
    if value is None or value == "":
        return None
    if value not in allowed:
        raise ValueError(f"{name} must be one of: {', '.join(allowed)}")
    return value


def matches_live_derived_filters(
    row: dict[str, Any],
    *,
    pricing_status: str | None,
    credit_confidence: str | None,
) -> bool:
    if pricing_status == "priced" and not row.get("pricing_model"):
        return False
    if pricing_status == "estimated" and not row.get("pricing_estimated"):
        return False
    if pricing_status == "unpriced" and row.get("pricing_model"):
        return False
    return not (credit_confidence and row.get("usage_credit_confidence") != credit_confidence)


def has_more_rows(limit: int | None, offset: int, row_count: int, total_matched: int) -> bool:
    return limit is not None and offset + row_count < total_matched


def next_row_offset(
    limit: int | None,
    offset: int,
    row_count: int,
    total_matched: int,
) -> int | None:
    return offset + row_count if has_more_rows(limit, offset, row_count, total_matched) else None


def parse_context_limit(value: str | None, default: int) -> int:
    if value is None or value == "":
        return default
    if value.lower() == "all":
        return 0
    try:
        limit = int(value)
    except ValueError:
        return default
    return max(limit, 0)


def elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 3)


def safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def json_response_body(payload: dict[str, object]) -> bytes:
    diagnostics = payload.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return json.dumps(payload, ensure_ascii=True).encode("utf-8")

    previous_size: int | None = None
    while True:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        current_size = len(body)
        if current_size == previous_size:
            return body
        diagnostics["json_bytes"] = current_size
        previous_size = current_size


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def validate_loopback_host(host: str) -> None:
    if host == "localhost":
        return
    try:
        address = ip_address(host)
    except ValueError as exc:
        raise ValueError("serve-dashboard --host must be localhost, 127.0.0.1, or ::1") from exc
    if not address.is_loopback:
        raise ValueError("serve-dashboard refuses to expose raw context off localhost")


def validate_context_api_mode(mode: str) -> None:
    if mode not in {"explicit", "disabled"}:
        raise ValueError("--context-api must be explicit or disabled")


def allowed_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def host_header_name(value: str | None) -> str | None:
    if not value:
        return None
    host = value.strip()
    if host.startswith("["):
        end = host.find("]")
        return host[1:end] if end > 0 else None
    return host.split(":", 1)[0]


def url_host(host: str) -> str:
    return f"[{host}]" if ":" in host and not host.startswith("[") else host
