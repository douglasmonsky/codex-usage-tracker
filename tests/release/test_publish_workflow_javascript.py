"""Release-policy coverage for packaged JavaScript validation."""

from __future__ import annotations

from pathlib import Path

from scripts.release_quality import check_publish_workflow

ROOT = Path(__file__).resolve().parents[2]


def test_release_check_rejects_static_dashboard_only_javascript_glob(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    workflow = workflow.replace(
        "find src/codex_usage_tracker/plugin_data/dashboard \\\n"
        "            -type f -name '*.js' -exec node --check '{}' ';'",
        "for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do\n"
        '            node --check "$file"\n'
        "          done",
        1,
    )
    (workflow_dir / "publish.yml").write_text(workflow, encoding="utf-8")

    failures = check_publish_workflow(tmp_path)

    assert any("all packaged JavaScript" in failure for failure in failures)
