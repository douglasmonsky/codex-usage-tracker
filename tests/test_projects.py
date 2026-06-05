from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.projects import (
    apply_project_privacy_to_rows,
    apply_project_privacy_to_summary_rows,
    annotate_rows_with_project_identity,
    load_project_config,
    project_privacy_metadata,
    project_identity_for_cwd,
    write_project_template,
)


def test_project_identity_derives_git_metadata_with_redacted_remote(tmp_path: Path) -> None:
    repo = tmp_path / "school-automation"
    subdir = repo / "tools" / "reports"
    git_dir = repo / ".git"
    subdir.mkdir(parents=True)
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/feature/usage\n", encoding="utf-8")
    (git_dir / "config").write_text(
        '[remote "origin"]\n\turl = git@github.com:district/school-automation.git\n',
        encoding="utf-8",
    )
    config_path = tmp_path / "projects.json"
    key = project_identity_for_cwd(str(subdir))["project_key"]
    config_path.write_text(
        json.dumps(
            {
                "aliases": {key: "School Automation"},
                "tags": {"School Automation": ["teacher-tools", "reports"]},
            }
        ),
        encoding="utf-8",
    )

    identity = project_identity_for_cwd(str(subdir), load_project_config(config_path))

    assert identity["project_name"] == "School Automation"
    assert identity["project_relative_cwd"] == "tools/reports"
    assert identity["git_branch"] == "feature/usage"
    assert identity["git_remote_label"] == "school-automation"
    assert identity["git_remote_hash"] is not None
    assert "github.com" not in str(identity["git_remote_hash"])
    assert identity["project_tags"] == ["reports", "teacher-tools"]


def test_project_template_ignored_paths_and_row_annotation(tmp_path: Path) -> None:
    project_config = tmp_path / "projects.json"
    ignored = tmp_path / "ignore-me"
    ignored.mkdir()

    written = write_project_template(project_config)
    payload = json.loads(project_config.read_text(encoding="utf-8"))
    payload["ignored_paths"] = [str(ignored)]
    project_config.write_text(json.dumps(payload), encoding="utf-8")
    rows = annotate_rows_with_project_identity(
        [{"cwd": str(ignored / "nested"), "total_tokens": 10}],
        load_project_config(project_config),
    )

    assert written == project_config
    assert rows[0]["project_ignored"] is True
    assert rows[0]["project_name"] == "nested"


def test_project_privacy_modes_redact_sensitive_metadata(tmp_path: Path) -> None:
    repo = tmp_path / "client-project"
    nested = repo / "private" / "workflow"
    git_dir = repo / ".git"
    nested.mkdir(parents=True)
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/client-secret\n", encoding="utf-8")
    (git_dir / "config").write_text(
        '[remote "origin"]\n\turl = git@github.com:client/client-project.git\n',
        encoding="utf-8",
    )
    rows = annotate_rows_with_project_identity(
        [{"cwd": str(nested), "source_file": str(tmp_path / ".codex" / "log.jsonl")}]
    )

    redacted = apply_project_privacy_to_rows(rows, privacy_mode="redacted")[0]
    strict = apply_project_privacy_to_rows(rows, privacy_mode="strict")[0]
    cwd_summary = apply_project_privacy_to_summary_rows(
        [{"group_key": str(nested), "total_tokens": 10}],
        group_by="cwd",
        privacy_mode="redacted",
    )[0]

    assert redacted["project_name"].startswith("Project ")
    assert redacted["cwd"].startswith("[redacted cwd:")
    assert redacted["source_file"].startswith("[redacted source:")
    assert redacted["project_relative_cwd"] == "private/workflow"
    assert redacted["git_branch"] == "client-secret"
    assert redacted["git_remote_label"] is None
    assert strict["project_relative_cwd"] is None
    assert strict["git_branch"] is None
    assert strict["project_tags"] == []
    assert cwd_summary["group_key"].startswith("[redacted cwd:")
    assert project_privacy_metadata("strict")["relative_cwd_hidden"] is True


def test_project_privacy_preserves_configured_aliases(tmp_path: Path) -> None:
    repo = tmp_path / "client-project"
    repo.mkdir()
    key = project_identity_for_cwd(str(repo))["project_key"]
    config_path = tmp_path / "projects.json"
    config_path.write_text(
        json.dumps({"aliases": {key: "Reviewed Alias"}}),
        encoding="utf-8",
    )
    rows = annotate_rows_with_project_identity(
        [{"cwd": str(repo)}],
        load_project_config(config_path),
    )

    redacted = apply_project_privacy_to_rows(rows, privacy_mode="redacted")[0]

    assert redacted["project_name"] == "Reviewed Alias"
    assert redacted["project_alias_configured"] is True
