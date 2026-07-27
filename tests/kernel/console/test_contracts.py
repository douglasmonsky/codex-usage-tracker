from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import quote

from codex_usage_tracker.kernel.application import KernelApplication
from codex_usage_tracker.kernel.interfaces.http.app import HttpApp
from codex_usage_tracker.kernel.interfaces.http.console import (
    ASSET_MANIFEST,
    CONSOLE_AREAS,
    asset_root,
)

from ..interfaces.support import active_runtime, synthetic_sources


def _application(tmp_path: Path, launches: list[object]) -> KernelApplication:
    return KernelApplication(
        active_runtime(tmp_path),
        worker_launcher=launches.append,
        source_provider=lambda _home: synthetic_sources(),
    )


def test_console_exposes_exactly_five_approved_areas() -> None:
    assert CONSOLE_AREAS == ("live", "explore", "evidence", "limits", "settings")


def test_console_navigation_is_read_only_and_root_redirects(tmp_path: Path) -> None:
    launches: list[object] = []
    application = _application(tmp_path, launches)
    operational_before = application.paths.kernel.operational.read_bytes()
    analytical_before = application.paths.kernel.analytical.read_bytes()
    adapter = HttpApp(application)

    root = adapter.handle("GET", "/", headers={"Host": "127.0.0.1:8765"})
    live = adapter.handle("GET", "/live", headers={"Host": "127.0.0.1:8765"})
    retired = adapter.handle(
        "GET",
        "/insights",
        headers={"Host": "127.0.0.1:8765"},
    )

    assert root.status == 302
    assert ("Location", "/live") in root.headers
    assert live.status == 200
    assert b"<main" in live.body
    assert retired.status == 404
    assert launches == []
    assert application.paths.kernel.operational.read_bytes() == operational_before
    assert application.paths.kernel.analytical.read_bytes() == analytical_before


def test_exact_evidence_deep_link_is_owned_by_the_new_console(tmp_path: Path) -> None:
    application = _application(tmp_path, [])
    query = application.query(
        {
            "requests": [
                {
                    "dataset": "calls",
                    "operation": "rows",
                    "dimensions": ["call"],
                    "measures": ["total_tokens"],
                    "limit": 1,
                }
            ]
        }
    )
    selector = query["results"][0]["evidence_selectors"][0]
    target = f"/evidence/{quote(selector, safe='')}?view=timeline&live=1"

    response = HttpApp(application).handle(
        "GET",
        target,
        headers={"Host": "127.0.0.1:8765"},
    )

    assert response.status == 200
    assert response.content_type.startswith("text/html")
    assert b"data-console-shell" in response.body


def test_console_assets_match_the_committed_deterministic_manifest() -> None:
    root = asset_root()
    assert tuple(sorted(ASSET_MANIFEST)) == (
        "app.js",
        "index.html",
        "model.js",
        "styles.css",
    )
    for name, expected_digest in ASSET_MANIFEST.items():
        payload = (root / name).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == expected_digest

    manifest = json.loads((root / "asset-manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "codex-usage-tracker.kernel-console-assets.v1"
    assert manifest["assets"] == ASSET_MANIFEST


def test_console_shell_contains_no_retired_product_navigation() -> None:
    html = (asset_root() / "index.html").read_text(encoding="utf-8")
    for route in CONSOLE_AREAS:
        assert f'href="/{route}' in html
    for retired in ("home", "insights", "reports", "diagnostics", "compression-lab"):
        assert f'href="/{retired}' not in html


def test_explore_uses_kernel_guidance_and_emits_typed_requests() -> None:
    source = (
        Path(__file__).resolve().parents[3]
        / "frontend"
        / "kernel-console"
        / "app.js"
    ).read_text(encoding="utf-8")

    assert "include_guidance: true" in source
    assert '"guided-template"' in source
    assert 'text: "Copy typed request"' in source
    assert "materializeTemplate" in source
