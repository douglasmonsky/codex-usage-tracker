"""Investigation report payload helpers for the localhost dashboard server."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs

from codex_usage_tracker.reports.api import (
    build_agentic_investigation_report,
    build_investigation_walk_report,
    build_large_low_output_report,
    build_repeated_file_rediscovery_report,
    build_shell_churn_report,
)
from codex_usage_tracker.server.utils import (
    first_query_value,
    parse_api_limit,
    parse_bool_query_value,
)

InvestigationKind = Literal[
    "agentic",
    "repeated-file-rediscovery",
    "shell-churn",
    "large-low-output",
    "walk",
]
ErrorSender = Callable[[HTTPStatus, str], None]
ExceptionSender = Callable[[str, BaseException], None]
JsonSender = Callable[[HTTPStatus, dict[str, object]], None]

_MAX_BOUNDED_FILTER = 10_000


def handle_investigation_request(
    kind: InvestigationKind,
    query: str,
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    projects_path: Path,
    include_archived_default: bool,
    privacy_mode: str,
    send_error: ErrorSender,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Handle investigation route errors and response writing."""
    try:
        payload = investigation_payload(
            kind,
            query,
            db_path=db_path,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            projects_path=projects_path,
            include_archived_default=include_archived_default,
            privacy_mode=privacy_mode,
        )
    except ValueError as exc:
        send_error(HTTPStatus.BAD_REQUEST, str(exc))
        return
    except sqlite3.Error as exc:
        send_exception("Database error while building investigation report", exc)
        return
    send_json(HTTPStatus.OK, payload)


def investigation_payload(
    kind: InvestigationKind,
    query: str,
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    projects_path: Path,
    include_archived_default: bool,
    privacy_mode: str,
) -> dict[str, object]:
    """Build one existing investigation report from bounded HTTP filters."""
    params = parse_qs(query)
    since = first_query_value(params.get("since"))
    until = first_query_value(params.get("until"))
    thread = first_query_value(params.get("thread"))
    include_archived = parse_bool_query_value(
        first_query_value(params.get("include_archived")),
        include_archived_default,
    )
    selected_privacy_mode = _selected_privacy_mode(params, privacy_mode)

    if kind == "agentic":
        return _agentic_investigation_payload(
            params,
            db_path=db_path,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            projects_path=projects_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            privacy_mode=selected_privacy_mode,
        )
    if kind == "repeated-file-rediscovery":
        return _repeated_file_investigation_payload(
            params,
            db_path=db_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            privacy_mode=selected_privacy_mode,
        )
    if kind == "shell-churn":
        return _shell_churn_investigation_payload(
            params,
            db_path=db_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            privacy_mode=selected_privacy_mode,
        )
    if kind == "large-low-output":
        return _large_low_output_investigation_payload(
            params,
            db_path=db_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            privacy_mode=selected_privacy_mode,
        )
    return _walk_investigation_payload(
        params,
        db_path=db_path,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        privacy_mode=selected_privacy_mode,
    )


def _selected_privacy_mode(
    params: dict[str, list[str]],
    privacy_mode: str,
) -> str:
    return first_query_value(params.get("privacy_mode")) or privacy_mode


def _agentic_investigation_payload(
    params: dict[str, list[str]],
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    projects_path: Path,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    privacy_mode: str,
) -> dict[str, object]:
    return dict(
        build_agentic_investigation_report(
            db_path=db_path,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            projects_path=projects_path,
            goal=first_query_value(params.get("goal")) or "token_waste",
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            evidence_limit=_bounded_int(params, "evidence_limit", 5),
            detail_mode=first_query_value(params.get("detail_mode")) or "compact",
            privacy_mode=privacy_mode,
        ).payload
    )


def _repeated_file_investigation_payload(
    params: dict[str, list[str]],
    *,
    db_path: Path,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    privacy_mode: str,
) -> dict[str, object]:
    return dict(
        build_repeated_file_rediscovery_report(
            db_path=db_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            min_occurrences=_bounded_int(params, "min_occurrences", 2),
            limit=parse_api_limit(first_query_value(params.get("limit")), 20),
            sample_limit=_bounded_int(params, "sample_limit", 3),
            privacy_mode=privacy_mode,
        ).payload
    )


def _shell_churn_investigation_payload(
    params: dict[str, list[str]],
    *,
    db_path: Path,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    privacy_mode: str,
) -> dict[str, object]:
    return dict(
        build_shell_churn_report(
            db_path=db_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            min_occurrences=_bounded_int(params, "min_occurrences", 3),
            limit=parse_api_limit(first_query_value(params.get("limit")), 20),
            sample_limit=_bounded_int(params, "sample_limit", 3),
            privacy_mode=privacy_mode,
        ).payload
    )


def _large_low_output_investigation_payload(
    params: dict[str, list[str]],
    *,
    db_path: Path,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    privacy_mode: str,
) -> dict[str, object]:
    return dict(
        build_large_low_output_report(
            db_path=db_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            min_total_tokens=_bounded_int(
                params,
                "min_total_tokens",
                20_000,
                maximum=1_000_000_000,
            ),
            max_output_tokens=_bounded_int(
                params,
                "max_output_tokens",
                1_000,
                maximum=1_000_000_000,
            ),
            limit=parse_api_limit(first_query_value(params.get("limit")), 20),
            privacy_mode=privacy_mode,
        ).payload
    )


def _walk_investigation_payload(
    params: dict[str, list[str]],
    *,
    db_path: Path,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    privacy_mode: str,
) -> dict[str, object]:
    question = first_query_value(params.get("question"))
    if not question:
        raise ValueError("question is required")
    return dict(
        build_investigation_walk_report(
            db_path=db_path,
            question=question,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            min_occurrences=_bounded_int(params, "min_occurrences", 2),
            evidence_limit=_bounded_int(params, "evidence_limit", 5),
            privacy_mode=privacy_mode,
        ).payload
    )


def _bounded_int(
    params: dict[str, list[str]],
    name: str,
    default: int,
    *,
    maximum: int = _MAX_BOUNDED_FILTER,
) -> int:
    value = first_query_value(params.get(name))
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a non-negative integer") from exc
    if parsed < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return min(parsed, maximum)
