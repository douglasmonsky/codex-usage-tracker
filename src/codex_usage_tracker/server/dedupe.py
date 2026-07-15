"""HTTP payload and handler for usage deduplication diagnostics."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

from codex_usage_tracker.diagnostics.dedupe import build_dedupe_diagnostics
from codex_usage_tracker.server.utils import first_query_value, safe_int

ExceptionSender = Callable[[str, BaseException], None]
JsonSender = Callable[[HTTPStatus, dict[str, object]], None]


class DedupeRouteMixin:
    """Read-only dedupe diagnostic route adapter."""

    if TYPE_CHECKING:
        _db_path: Path

        def _send_exception(self, prefix: str, exc: BaseException) -> None: ...

        def _send_json(
            self,
            status: HTTPStatus,
            payload: dict[str, object],
        ) -> None: ...

    def _handle_dedupe_diagnostics(self, query: str) -> None:
        handle_dedupe_request(
            query,
            db_path=self._db_path,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )


def dedupe_payload(query: str, *, db_path: Path) -> dict[str, object]:
    """Build a bounded dedupe diagnostic from an HTTP query string."""

    params = parse_qs(query)
    raw_limit = first_query_value(params.get("limit"))
    limit = safe_int(raw_limit) if raw_limit is not None else 100
    return build_dedupe_diagnostics(db_path=db_path, limit=limit)


def handle_dedupe_request(
    query: str,
    *,
    db_path: Path,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Handle the read-only dedupe diagnostic endpoint."""

    try:
        payload = dedupe_payload(query, db_path=db_path)
    except sqlite3.Error as exc:
        send_exception("Database error while reading dedupe diagnostics", exc)
        return
    send_json(HTTPStatus.OK, payload)
