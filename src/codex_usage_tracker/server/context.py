"""Raw context payload helpers for the dashboard server."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qs

from codex_usage_tracker.context.api import (
    CONTEXT_MODE_QUICK,
    CONTEXT_MODES,
    DEFAULT_CONTEXT_ENTRIES,
    load_call_context,
)
from codex_usage_tracker.server.utils import (
    first_query_value,
    parse_bool_query_value,
    parse_context_limit,
    truthy_query_value,
)


class ContextRequestError(ValueError):
    """Raised for invalid context API request parameters."""


class ErrorSender(Protocol):
    def __call__(
        self,
        status: HTTPStatus,
        message: str,
        **extra: object,
    ) -> None: ...


JsonSender = Callable[[HTTPStatus, dict[str, object]], None]
ExceptionSender = Callable[[str, BaseException], None]
TokenValidator = Callable[[dict[str, list[str]]], bool]


def handle_context_request(
    query: str,
    *,
    db_path: Path,
    default_context_chars: int,
    context_api_enabled: bool,
    has_valid_api_token: TokenValidator,
    send_error: ErrorSender,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Handle the context route while keeping server.py as a thin dispatcher."""
    params = parse_qs(query)
    if not context_api_enabled:
        send_error(
            HTTPStatus.FORBIDDEN,
            "Context loading disabled for dashboard server.",
            context_api_enabled=False,
            can_enable_context_api=True,
        )
        return
    if not has_valid_api_token(params):
        send_error(HTTPStatus.FORBIDDEN, "Valid API token required")
        return
    try:
        payload = context_payload(
            query,
            db_path=db_path,
            default_context_chars=default_context_chars,
        )
    except ContextRequestError as exc:
        send_error(HTTPStatus.BAD_REQUEST, str(exc))
        return
    except sqlite3.Error as exc:
        send_exception("Database error while loading context", exc)
        return
    except ValueError as exc:
        send_error(HTTPStatus.NOT_FOUND, str(exc))
        return
    except FileNotFoundError as exc:
        send_error(HTTPStatus.NOT_FOUND, str(exc))
        return
    except OSError as exc:
        send_exception("Could not read source log", exc)
        return
    send_json(HTTPStatus.OK, payload)


def context_payload(
    query: str,
    *,
    db_path: Path,
    default_context_chars: int,
) -> dict[str, object]:
    """Build the raw context API payload after auth/enable checks."""
    params = parse_qs(query)
    record_id = first_query_value(params.get("record_id"))
    if not record_id:
        raise ContextRequestError("record_id required")

    context_mode = (first_query_value(params.get("mode")) or CONTEXT_MODE_QUICK).strip().lower()
    if context_mode not in CONTEXT_MODES:
        raise ContextRequestError("mode must be one of: " + ", ".join(sorted(CONTEXT_MODES)))

    return load_call_context(
        record_id=record_id,
        db_path=db_path,
        max_chars=parse_context_limit(
            first_query_value(params.get("max_chars")),
            default_context_chars,
        ),
        max_entries=parse_context_limit(
            first_query_value(params.get("max_entries")),
            DEFAULT_CONTEXT_ENTRIES,
        ),
        include_tool_output=truthy_query_value(
            first_query_value(params.get("include_tool_output"))
        ),
        include_compaction_history=truthy_query_value(
            first_query_value(params.get("include_compaction_history")),
        ),
        diagnostics=parse_bool_query_value(first_query_value(params.get("diagnostics")), False),
        mode=context_mode,
    )
