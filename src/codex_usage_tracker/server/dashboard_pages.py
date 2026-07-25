"""Dashboard page and static-response handling for the local server."""

from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlparse

from codex_usage_tracker.server.context_settings import ContextApiState
from codex_usage_tracker.server.dashboard_shell import (
    react_dashboard_boot_payload,
)
from codex_usage_tracker.server.responses import send_html_response
from codex_usage_tracker.server.routes import (
    HTTP_V1_DEPRECATION_LINK,
    is_deprecated_http_v1_path,
)

_DASHBOARD_ASSET_MIME_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}
_REACT_DASHBOARD_PATH = "/react-dashboard.html"
_REACT_DASHBOARD_INDEX_PATH = "/codex-usage-tracker-assets/react/index.html"
_DASHBOARD_ASSET_PATH_PREFIX = "/codex-usage-tracker-assets/"
_REMOVED_DASHBOARD_PATH = "/dashboard.html"
_REMOVED_DASHBOARD_BODY = b"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>Static dashboard removed</title>
<body>
<h1>Static dashboard removed</h1>
<p>The live Evidence Console is available at
<a href="/react-dashboard.html">/react-dashboard.html</a>.</p>
</body>
</html>
"""


class DashboardPageMixin(SimpleHTTPRequestHandler):
    """Serve dashboard HTML and assets for the configured usage database."""

    if TYPE_CHECKING:
        _codex_home: Path
        _db_path: Path
        _pricing_path: Path
        _allowance_path: Path
        _rate_card_path: Path
        _thresholds_path: Path
        _projects_path: Path
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
        request_path = urlparse(self.path).path
        if self._is_dashboard_html_request():
            self.send_header("Cache-Control", "no-store")
        elif request_path.startswith("/codex-usage-tracker-assets/react/assets/"):
            self.send_header("Cache-Control", "no-cache")
        if is_deprecated_http_v1_path(request_path):
            self.send_header("Deprecation", "true")
            self.send_header("Link", HTTP_V1_DEPRECATION_LINK)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
            "img-src 'self' data:; object-src 'none'; base-uri 'none'",
        )
        super().end_headers()

    def guess_type(self, path: str | os.PathLike[str]) -> str:
        forced_type = _DASHBOARD_ASSET_MIME_TYPES.get(Path(path).suffix.lower())
        if forced_type is not None:
            return forced_type
        return super().guess_type(path)

    def translate_path(self, path: str) -> str:
        request_path = urlparse(path).path
        if request_path.startswith(_DASHBOARD_ASSET_PATH_PREFIX):
            relative_path = unquote(
                request_path.removeprefix(_DASHBOARD_ASSET_PATH_PREFIX)
            ).replace("\\", "/")
            relative = PurePosixPath(relative_path)
            asset_root = Path(self.directory).resolve()
            if (
                relative.is_absolute()
                or PureWindowsPath(relative_path).drive
                or ".." in relative.parts
            ):
                return str(asset_root / "__invalid_asset_path__")
            candidate = asset_root.joinpath(*relative.parts).resolve()
            if not candidate.is_relative_to(asset_root):
                return str(asset_root / "__invalid_asset_path__")
            return str(candidate)
        return super().translate_path(path)

    def _is_dashboard_html_request(self) -> bool:
        path = urlparse(self.path).path
        return path in {"/", _REMOVED_DASHBOARD_PATH, _REACT_DASHBOARD_PATH} or bool(
            getattr(self, "_serving_react_dashboard", False),
        )

    def _redirect_to_react_dashboard(self) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", _REACT_DASHBOARD_PATH)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _handle_removed_dashboard(self, *, include_body: bool = True) -> None:
        self._send_html(
            _REMOVED_DASHBOARD_BODY,
            status=HTTPStatus.GONE,
            include_body=include_body,
        )

    def _handle_react_dashboard(self, query: str) -> None:
        payload = react_dashboard_boot_payload(
            query,
            api_token=self._api_token,
            context_api_enabled=self._context_api_state.enabled,
            include_archived_default=self._include_archived,
            language_default=self._language,
            limit_default=self._limit,
            privacy_mode=self._privacy_mode,
            since=self._since,
        )
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

    def _send_html(
        self,
        body: bytes,
        *,
        status: HTTPStatus = HTTPStatus.OK,
        include_body: bool = True,
    ) -> None:
        send_html_response(self, body, status=status, include_body=include_body)
