"""Release-policy coverage for packaged JavaScript validation."""

from __future__ import annotations

from pathlib import Path

from scripts.release_quality import check_publish_workflow

ROOT = Path(__file__).resolve().parents[2]


def test_release_check_rejects_removed_dashboard_javascript_path(
    tmp_path: Path,
) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    workflow = workflow.replace(
        "find src/codex_usage_tracker/kernel/interfaces/http/console_assets \\\n"
        "            -type f -name '*.js' -exec node --check '{}' ';'",
        "for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do\n"
        '            node --check "$file"\n'
        "          done",
        1,
    )
    (workflow_dir / "publish.yml").write_text(workflow, encoding="utf-8")

    failures = check_publish_workflow(tmp_path)

    assert any("packaged kernel Console" in failure for failure in failures)


def test_kernel_ci_qualifies_release_pull_requests_against_audited_main() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "- main" in workflow
    assert "github.head_ref == 'release/0.27.0'" in workflow
    assert "github.event.pull_request.base.sha" in workflow
    assert "config/kernel-release-qualification-v1.json" in workflow
    assert "python -m pytest -p no:tach" in workflow
    assert "scripts/smoke_installed_package.py" in workflow
