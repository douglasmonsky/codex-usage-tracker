from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from scripts.check_kernel_scope import (
    INTEGRATION_ADDITIONS,
    K1A_ADDITIONS,
    K2_ADDITIONS,
    K3_ADDITIONS,
    K4_ADDITIONS,
    K5_ADDITIONS,
    K6_ADDITIONS,
    K7_ADDITIONS,
    K8_ADDITIONS,
    K9_ADDITIONS,
    K10_ADDITIONS,
    K12_ADDITIONS,
    K13_ADDITIONS,
    K14_ADDITIONS,
    active_paths,
    load_disposition_manifest,
    publication_ref_failure,
    publication_source_failure,
    scope_failures,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_integration_tree_matches_quarantine_manifest() -> None:
    manifest = load_disposition_manifest(
        _REPO_ROOT / "config" / "kernel-code-disposition-v1.json"
    )

    assert scope_failures(_REPO_ROOT, manifest) == []


def test_scope_checks_physical_keep_and_removed_paths(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    keep = tmp_path / "keep.py"
    removed = tmp_path / "removed.py"
    keep.write_text("keep\n", encoding="utf-8")
    manifest = {
        "entries": [
            {"path": "keep.py", "disposition": "keep", "status": "classified"},
            {"path": "removed.py", "disposition": "retire", "status": "removed"},
        ]
    }
    monkeypatch.setattr(
        "scripts.check_kernel_scope.active_paths",
        lambda _root: {"keep.py"},
    )
    assert scope_failures(tmp_path, manifest) == []

    keep.unlink()
    removed.write_text("retired\n", encoding="utf-8")
    failures = scope_failures(tmp_path, manifest)

    assert "required keep path is absent: keep.py" in failures
    assert "quarantined path remains active: removed.py" in failures


def test_active_paths_excludes_indexed_files_deleted_from_worktree(
    tmp_path: Path,
) -> None:
    removed = tmp_path / "phase-ledger.md"
    removed.write_text("temporary\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "phase-ledger.md"], check=True)
    removed.unlink()

    assert "phase-ledger.md" not in active_paths(tmp_path)


def test_k1a_additions_are_explicit_and_bounded() -> None:
    assert frozenset(
        {
            "docs/kernel-development-scope.md",
            "scripts/check_kernel_scope.py",
            "src/codex_usage_tracker/kernel/AGENTS.md",
            "src/codex_usage_tracker/kernel/__init__.py",
            "tests/kernel/test_kernel_scope.py",
        }
    ) == K1A_ADDITIONS


def test_k2_additions_are_explicit_and_bounded() -> None:
    assert {
        "src/codex_usage_tracker/kernel/database.py",
        "src/codex_usage_tracker/kernel/identity.py",
        "src/codex_usage_tracker/kernel/models.py",
        "src/codex_usage_tracker/kernel/operational.py",
        "src/codex_usage_tracker/kernel/schema.py",
        "tests/kernel/test_cutover_control.py",
        "tests/kernel/test_database_lifecycle.py",
        "tests/kernel/test_identity.py",
        "tests/kernel/test_schema.py",
        "tests/kernel/test_source_registry_privacy.py",
    } == K2_ADDITIONS


def test_k3_additions_are_explicit_and_bounded() -> None:
    assert {
        "src/codex_usage_tracker/kernel/discovery.py",
        "src/codex_usage_tracker/kernel/ingest.py",
        "src/codex_usage_tracker/kernel/lease.py",
        "src/codex_usage_tracker/kernel/normalize.py",
        "src/codex_usage_tracker/kernel/parser.py",
        "src/codex_usage_tracker/kernel/watcher.py",
        "src/codex_usage_tracker/kernel/writer.py",
        "tests/kernel/test_ingest_concurrency.py",
        "tests/kernel/test_ingest_jobs.py",
        "tests/kernel/test_ingest_lifecycle.py",
        "tests/kernel/test_ingest_oracle.py",
        "tests/kernel/test_ingest_performance.py",
        "tests/kernel/test_ingest_pipeline.py",
        "tests/kernel/test_ingest_privacy.py",
        "tests/kernel/test_ingest_reconciliation.py",
        "tests/kernel/test_watcher.py",
    } == K3_ADDITIONS


def test_k4_additions_are_explicit_and_bounded() -> None:
    assert {
        "src/codex_usage_tracker/kernel/query/service.py",
        "tests/kernel/query/test_performance.py",
    } <= K4_ADDITIONS


def test_k5_additions_are_explicit_and_bounded() -> None:
    assert {
        "src/codex_usage_tracker/kernel/evidence/service.py",
        "src/codex_usage_tracker/kernel/live/journal.py",
        "tests/kernel/evidence/test_performance.py",
        "tests/kernel/live/test_contracts.py",
    } <= K5_ADDITIONS


def test_k6_additions_are_explicit_and_bounded() -> None:
    assert {
        "scripts/generate_kernel_interfaces.py",
        "skills/usage-kernel/SKILL.md",
        "src/codex_usage_tracker/kernel/application/service.py",
        "src/codex_usage_tracker/kernel/interfaces/cli/main.py",
        "src/codex_usage_tracker/kernel/interfaces/http/app.py",
        "src/codex_usage_tracker/kernel/interfaces/mcp/catalog.py",
        "src/codex_usage_tracker/kernel/interfaces/mcp/server.py",
        "src/codex_usage_tracker/kernel/plugin_manifest.py",
        "tests/kernel/interfaces/test_application.py",
        "tests/kernel/interfaces/test_cli.py",
        "tests/kernel/interfaces/test_contracts.py",
        "tests/kernel/interfaces/test_http.py",
        "tests/kernel/interfaces/test_mcp.py",
        "tests/kernel/interfaces/test_performance.py",
        "tests/kernel/interfaces/test_plugin.py",
    } <= K6_ADDITIONS
    assert {
        "frontend/kernel-console/app.js",
        "scripts/build_kernel_console.mjs",
        "scripts/check_kernel_console.mjs",
        "scripts/smoke_installed_console.py",
        "src/codex_usage_tracker/kernel/interfaces/http/console.py",
        "src/codex_usage_tracker/kernel/interfaces/http/console_assets/index.html",
        "tests/frontend/kernel_console.test.mjs",
        "tests/kernel/console/test_contracts.py",
    } <= K7_ADDITIONS
    assert {
        "docs/kernel-allowance-efficiency.md",
        "src/codex_usage_tracker/kernel/allowance/service.py",
        "tests/kernel/allowance/test_service.py",
    } <= K8_ADDITIONS
    assert {
        "config/kernel-release-candidate-budget.json",
        "docs/upgrade-0.26.md",
        "scripts/check_kernel_release_candidate.py",
        "tests/kernel/test_release_candidate.py",
    } == K9_ADDITIONS
    assert {
        "config/kernel-release-cutover-v1.json",
        ".agents/plugins/marketplace.json",
        "tests/kernel/test_release_cutover.py",
    } == K10_ADDITIONS
    assert {
        "docs/kernel-context-composition.md",
        "src/codex_usage_tracker/kernel/content.py",
        "tests/kernel/content/__init__.py",
        "tests/kernel/content/test_cli.py",
        "tests/kernel/content/test_service.py",
    } == K12_ADDITIONS
    assert {
        "config/kernel-overlay-adapter-v1.json",
        "docs/kernel-overlay-adapter-contract.md",
        "tests/kernel/fixtures/overlay-adapter-v1.json",
        "tests/kernel/live/test_overlay_adapter_contract.py",
    } == K13_ADDITIONS
    assert {
        "config/kernel-release-qualification-v1.json",
        "tests/kernel/test_release_027_qualification.py",
    } == K14_ADDITIONS
    assert INTEGRATION_ADDITIONS == (
        K1A_ADDITIONS
        | K2_ADDITIONS
        | K3_ADDITIONS
        | K4_ADDITIONS
        | K5_ADDITIONS
        | K6_ADDITIONS
        | K7_ADDITIONS
        | K8_ADDITIONS
        | K9_ADDITIONS
        | K10_ADDITIONS
        | K12_ADDITIONS
        | K13_ADDITIONS
        | K14_ADDITIONS
    )


def test_kernel_skeleton_imports_without_legacy_runtime() -> None:
    import codex_usage_tracker.kernel as kernel

    assert kernel.__version__ == "0.27.0"


def test_retained_release_primitives_match_k1_and_import() -> None:
    from codex_usage_tracker.release.artifact_manifest import canonical_json_bytes
    from codex_usage_tracker.release.artifact_normalization import (
        normalize_sdist_directory,
    )
    from codex_usage_tracker.release.promotion_evidence import (
        PROMOTION_SCHEMA,
    )
    from scripts.check_release import _frozen_release_failures

    assert _frozen_release_failures() == []
    assert canonical_json_bytes({"b": 2, "a": 1}) == b'{"a":1,"b":2}\n'
    assert callable(normalize_sdist_directory)
    assert PROMOTION_SCHEMA.endswith(".v1")


def test_publication_guard_rejects_every_integration_ref() -> None:
    blocked = (
        "refs/heads/kernel/0.26-integration",
        "refs/heads/kernel/k1a-legacy-quarantine",
        "refs/heads/kernel/k2-schema-identity",
        "refs/heads/kernel/k3-ingest-tail",
        "refs/heads/kernel/k4-query-core",
        "refs/heads/kernel/k5-evidence-timeline",
        "refs/heads/kernel/k6-interface-adapters",
        "refs/heads/kernel/k7-evidence-console",
        "refs/heads/kernel/k8-allowance-efficiency",
        "refs/heads/kernel/k9-release-candidate",
    )

    assert all(publication_ref_failure(ref, "0.26.0.dev0") for ref in blocked)
    assert publication_ref_failure("refs/heads/release/0.27.0", "0.27.0")
    assert publication_ref_failure("refs/heads/main", "0.27.0") is None


def test_publication_guard_rejects_correct_tag_on_unmerged_commit(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    git("init", "-b", "main")
    git("config", "user.name", "Kernel Release Test")
    git("config", "user.email", "kernel-release@example.invalid")
    tracked = repo / "tracked.txt"
    tracked.write_text("main\n", encoding="utf-8")
    git("add", "tracked.txt")
    git("commit", "-m", "main")
    main_sha = git("rev-parse", "HEAD")
    git("update-ref", "refs/remotes/origin/main", main_sha)

    git("switch", "-c", "unmerged")
    tracked.write_text("unmerged\n", encoding="utf-8")
    git("commit", "-am", "unmerged")
    unmerged_sha = git("rev-parse", "HEAD")
    git("tag", "v0.27.0")

    failure = publication_source_failure(
        repo,
        ref="refs/tags/v0.27.0",
        sha=unmerged_sha,
        package_version="0.27.0",
    )

    assert failure == (
        f"publication SHA {unmerged_sha} is not merged into origin/main"
    )


def test_publish_workflow_calls_persistent_kernel_guard() -> None:
    workflow = (_REPO_ROOT / ".github" / "workflows" / "publish.yml").read_text(
        encoding="utf-8"
    )

    assert "Enforce kernel publication source" in workflow
    assert "scripts/check_kernel_scope.py" in workflow
    assert '--publication-ref "$GITHUB_REF"' in workflow
    assert 'git fetch --no-tags origin main:refs/remotes/origin/main' in workflow
    assert '--publication-sha "$GITHUB_SHA"' in workflow
    assert "--main-ref origin/main" in workflow
