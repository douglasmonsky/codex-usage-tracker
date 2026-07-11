"""Dashboard page and static-response handling for the local server."""

from __future__ import annotations

import json
import os
import sqlite3
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from codex_usage_tracker.dashboard.api import render_dashboard_html
from codex_usage_tracker.server import utils as server_utils
from codex_usage_tracker.server.context_settings import ContextApiState
from codex_usage_tracker.server.dashboard_shell import dashboard_shell_payload
from codex_usage_tracker.server.responses import send_html_response

_first = server_utils.first_query_value

_DASHBOARD_ASSET_MIME_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}
_REACT_DASHBOARD_PATH = "/react-dashboard.html"
_REACT_DASHBOARD_INDEX_PATH = "/codex-usage-tracker-assets/react/index.html"


class DashboardPageMixin(SimpleHTTPRequestHandler):
    """Serve dashboard HTML and assets for the configured usage database."""

    if TYPE_CHECKING:
        _db_path: Path
        _pricing_path: Path
        _allowance_path: Path
        _rate_card_path: Path
        _thresholds_path: Path
        _projects_path: Path
        _dashboard_path: Path
        _dashboard_name: str
        _privacy_mode: str
        _since: str | None
        _api_token: str
        _context_api_state: ContextApiState
        _include_archived: bool
        _language: str
        _limit: int

        def _send_exception(self, prefix: str, exc: BaseException) -> None: ...

    def end_headers(self) -> None:
        if self._is_dashboard_html_request():
            self.send_header("Cache-Control", "no-store")
        elif urlparse(self.path).path.startswith("/codex-usage-tracker-assets/react/assets/"):
            self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; "
            "style-src 'self'; connect-src 'self'; "
            "img-src 'self' data:; object-src 'none'; base-uri 'none'",
        )
        super().end_headers()

    def guess_type(self, path: str | os.PathLike[str]) -> str:
        forced_type = _DASHBOARD_ASSET_MIME_TYPES.get(Path(path).suffix.lower())
        if forced_type is not None:
            return forced_type
        return super().guess_type(path)

    def _is_dashboard_html_request(self) -> bool:
        path = urlparse(self.path).path
        return path in {"/", f"/{self._dashboard_name}", _REACT_DASHBOARD_PATH} or bool(
            getattr(self, "_serving_react_dashboard", False),
        )

    def _handle_react_dashboard(self, query: str) -> None:
        payload = self._dashboard_shell_payload(query)
        if payload is None:
            return
        payload["pricing_snapshot_warning"] = ""
        index_path = Path(self.translate_path(_REACT_DASHBOARD_INDEX_PATH))
        try:
            html = index_path.read_text(encoding="utf-8")
        except OSError as exc:
            self._send_exception("Could not read React dashboard shell", exc)
            return
        usage_data = json.dumps(payload, ensure_ascii=True).replace("</", "<\\/")
        usage_script = f'<script id="usage-data" type="application/json">{usage_data}</script>'
        if '<div id="root"></div>' in html:
            html = html.replace(
                '<div id="root"></div>', f'<div id="root"></div>\n    {usage_script}', 1
            )
        elif "</head>" in html:
            html = html.replace("</head>", f"  {usage_script}\n</head>", 1)
        else:
            html = f"{html}\n{usage_script}"
        original_path = self.path
        self._serving_react_dashboard = True
        try:
            self._send_html(html.encode("utf-8"))
        finally:
            self.path = original_path
            self._serving_react_dashboard = False

    def _is_investigator_dashboard_request(self, path: str, query: str) -> bool:
        if path != f"/{self._dashboard_name}":
            return False
        params = parse_qs(query)
        return _first(params.get("view")) == "call" and bool(_first(params.get("record")))

    def _handle_investigator_dashboard(self, query: str) -> None:
        payload = self._dashboard_shell_payload(query)
        if payload is None:
            return
        payload["investigator_boot"] = True
        payload["pricing_snapshot_warning"] = ""
        body = render_dashboard_html(
            payload,
            output_path=self._dashboard_path,
            guide_href="codex-usage-tracker-guide/dashboard-guide.html",
            body_attrs={
                "data-active-view": "call",
                "data-investigator-boot": "true",
                "data-dashboard-shell": "true",
            },
        ).encode("utf-8")
        self._send_html(body)

    def _handle_dashboard_shell(self, query: str) -> None:
        payload = self._dashboard_shell_payload(query)
        if payload is None:
            return
        payload["pricing_snapshot_warning"] = ""
        body = render_dashboard_html(
            payload,
            output_path=self._dashboard_path,
            guide_href="codex-usage-tracker-guide/dashboard-guide.html",
            body_attrs={"data-dashboard-shell": "true"},
        ).encode("utf-8")
        self._send_html(body)

    def _dashboard_shell_payload(self, query: str) -> dict[str, object] | None:
        try:
            return dashboard_shell_payload(
                query,
                db_path=self._db_path,
                pricing_path=self._pricing_path,
                allowance_path=self._allowance_path,
                rate_card_path=self._rate_card_path,
                thresholds_path=self._thresholds_path,
                projects_path=self._projects_path,
                privacy_mode=self._privacy_mode,
                since=self._since,
                api_token=self._api_token,
                context_api_enabled=self._context_api_state.enabled,
                include_archived_default=self._include_archived,
                language_default=self._language,
                limit_default=self._limit,
            )
        except sqlite3.Error as exc:
            self._send_exception("Database error while preparing dashboard shell", exc)
            return None
        except OSError as exc:
            self._send_exception("Could not prepare dashboard shell", exc)
            return None

    def _send_html(self, body: bytes) -> None:
        send_html_response(self, body)
