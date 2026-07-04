"""Open-investigator payload helpers for the dashboard server."""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

from codex_usage_tracker.server.utils import allowed_loopback_host, first_query_value

OPEN_INVESTIGATOR_SCHEMA = "codex-usage-tracker-open-investigator-v1"
REACT_DASHBOARD_PATH = "/react-dashboard.html"


class OpenInvestigatorRequestError(ValueError):
    """Raised when an open-investigator request is not safe or complete."""


def open_investigator_payload(
    query: str,
    *,
    request_host: str | None,
    server_port: int,
    dashboard_name: str,
    open_new_tab: Callable[[str], object],
) -> dict[str, object]:
    """Validate the target dashboard URL, open it, and return response JSON."""
    params = parse_qs(query)
    target = first_query_value(params.get("url"))
    if not target:
        raise OpenInvestigatorRequestError("url is required")

    parsed_target = urlparse(target)
    if parsed_target.scheme:
        _validate_absolute_target(parsed_target.scheme, parsed_target.hostname, parsed_target.port, server_port)
    allowed_paths = {f"/{dashboard_name}", REACT_DASHBOARD_PATH}
    if parsed_target.path not in allowed_paths:
        raise OpenInvestigatorRequestError("Only dashboard investigator URLs can be opened")

    target_params = parse_qs(parsed_target.query)
    if first_query_value(target_params.get("view")) != "call" or not first_query_value(
        target_params.get("record")
    ):
        raise OpenInvestigatorRequestError("Investigator URL must include view=call and record")

    host = request_host or f"127.0.0.1:{server_port}"
    safe_url = f"http://{host}{REACT_DASHBOARD_PATH}"
    if parsed_target.query:
        safe_url = f"{safe_url}?{parsed_target.query}"
    if parsed_target.fragment:
        safe_url = f"{safe_url}#{parsed_target.fragment}"

    opened = open_new_tab(safe_url)
    return {
        "schema": OPEN_INVESTIGATOR_SCHEMA,
        "opened": bool(opened),
        "url": safe_url,
    }


def _validate_absolute_target(
    scheme: str,
    hostname: str | None,
    port: int | None,
    server_port: int,
) -> None:
    if scheme not in {"http", "https"}:
        raise OpenInvestigatorRequestError("Only dashboard URLs can be opened")
    if not allowed_loopback_host(hostname):
        raise OpenInvestigatorRequestError("Only loopback dashboard URLs can be opened")
    if port not in {None, server_port}:
        raise OpenInvestigatorRequestError("Dashboard URL port is not allowed")
