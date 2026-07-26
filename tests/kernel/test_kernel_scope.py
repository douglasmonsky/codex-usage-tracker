from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.check_kernel_scope import (
    INTEGRATION_ADDITIONS,
    K1A_ADDITIONS,
    K2_ADDITIONS,
    K3_ADDITIONS,
    load_disposition_manifest,
    publication_ref_failure,
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


def test_k1a_additions_are_explicit_and_bounded() -> None:
    assert frozenset(
        {
            ".agent-maintainer/change-plans/k1a-legacy-quarantine.md",
            "docs/kernel-development-scope.md",
            "scripts/check_kernel_scope.py",
            "src/codex_usage_tracker/kernel/AGENTS.md",
            "src/codex_usage_tracker/kernel/__init__.py",
            "tests/kernel/test_kernel_scope.py",
        }
    ) == K1A_ADDITIONS


def test_k2_additions_are_explicit_and_bounded() -> None:
    assert {
        ".agent-maintainer/change-plans/k2-schema-identity.md",
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
        ".agent-maintainer/change-plans/k3-incremental-ingestion.md",
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
    assert INTEGRATION_ADDITIONS == K1A_ADDITIONS | K2_ADDITIONS | K3_ADDITIONS


def test_kernel_skeleton_imports_without_legacy_runtime() -> None:
    import codex_usage_tracker.kernel as kernel

    assert kernel.__version__ == "0.26.0.dev0"


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
    assert publication_ref_failure("refs/heads/main", "0.26.0") is None


def test_publish_workflow_calls_persistent_kernel_guard() -> None:
    workflow = (_REPO_ROOT / ".github" / "workflows" / "publish.yml").read_text(
        encoding="utf-8"
    )

    assert "Reject kernel integration publication" in workflow
    assert "scripts/check_kernel_scope.py" in workflow
    assert '--publication-ref "$GITHUB_REF"' in workflow
