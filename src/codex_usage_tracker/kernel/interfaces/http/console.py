"""Deterministic, read-only K7 Evidence Console assets and routes."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .app import HttpResponse

CONSOLE_AREAS = ("live", "explore", "evidence", "limits", "settings")
_CONTENT_TYPES = {
    "app.js": "text/javascript; charset=utf-8",
    "index.html": "text/html; charset=utf-8",
    "model.js": "text/javascript; charset=utf-8",
    "styles.css": "text/css; charset=utf-8",
}
_SECURITY_HEADERS = (
    (
        "Content-Security-Policy",
        "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
    ),
    ("Referrer-Policy", "no-referrer"),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
)


def asset_root() -> Path:
    return Path(__file__).with_name("console_assets")


def _load_manifest() -> dict[str, str]:
    payload = json.loads(
        (asset_root() / "asset-manifest.json").read_text(encoding="utf-8")
    )
    return dict(payload["assets"])


ASSET_MANIFEST = _load_manifest()


def console_response(method: str, target: str) -> HttpResponse | None:
    """Return one console response without calling any application use case."""

    if method != "GET":
        return None
    path = urlsplit(target).path
    if path == "/":
        return HttpResponse(
            302,
            "text/plain; charset=utf-8",
            b"",
            (("Location", "/live"), ("Cache-Control", "no-store"), *_SECURITY_HEADERS),
        )
    asset_prefix = "/assets/kernel-console/"
    if path.startswith(asset_prefix):
        name = unquote(path.removeprefix(asset_prefix))
        if name not in ASSET_MANIFEST or "/" in name or "\\" in name:
            return None
        return _asset_response(name)
    if _is_console_route(path):
        return _asset_response("index.html", cache_control="no-store")
    return None


def _is_console_route(path: str) -> bool:
    if path in {f"/{area}" for area in CONSOLE_AREAS}:
        return True
    if path.startswith("/evidence/"):
        encoded = path.removeprefix("/evidence/")
        selector = unquote(encoded)
        return bool(encoded and ":" in selector and len(selector) <= 256)
    return False


def _asset_response(
    name: str,
    *,
    cache_control: str = "public, max-age=0, must-revalidate",
) -> HttpResponse:
    return HttpResponse(
        200,
        _CONTENT_TYPES[name],
        (asset_root() / name).read_bytes(),
        (
            ("Cache-Control", cache_control),
            ("ETag", f'"sha256:{ASSET_MANIFEST[name]}"'),
            *_SECURITY_HEADERS,
        ),
    )
