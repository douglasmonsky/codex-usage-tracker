from __future__ import annotations

import shutil
from pathlib import Path

from codex_usage_tracker import __version__
from codex_usage_tracker.cli.plugin_installer import install_plugin
from codex_usage_tracker.diagnostics.api import run_doctor
from codex_usage_tracker.pricing.api import (
    annotate_rows_with_efficiency,
    load_pricing_config,
)
from codex_usage_tracker.store.api import query_most_expensive_calls, refresh_usage_index
from tests.store_dashboard_helpers import _make_codex_home, _write_pricing


def test_pricing_annotation_and_doctor_pass(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    rows = query_most_expensive_calls(db_path=db_path, limit=1)
    annotated = annotate_rows_with_efficiency(
        rows, pricing=load_pricing_config(tmp_path / "missing-pricing.json")
    )
    assert annotated[0]["estimated_cost_usd"] is None
    annotated = annotate_rows_with_efficiency(rows, pricing=load_pricing_config(pricing_path))
    assert annotated[0]["estimated_cost_usd"] > 0

    plugin_link = tmp_path / "plugins" / "codex-usage-tracker"
    marketplace_path = tmp_path / "marketplace.json"
    install_plugin(
        plugin_dir=plugin_link,
        marketplace_path=marketplace_path,
    )
    cached_plugin = (
        codex_home
        / "plugins"
        / "cache"
        / "local"
        / "codex-usage-tracker"
        / __version__
    )
    cached_plugin.parent.mkdir(parents=True)
    shutil.copytree(plugin_link, cached_plugin)

    report = run_doctor(
        codex_home=codex_home,
        db_path=db_path,
        pricing_path=pricing_path,
        plugin_link=plugin_link,
        marketplace_path=marketplace_path,
        repo_root=plugin_link,
    )

    assert report["status"] == "pass", [
        check for check in report["checks"] if check["status"] != "pass"
    ]
