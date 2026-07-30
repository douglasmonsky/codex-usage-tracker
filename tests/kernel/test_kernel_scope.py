from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from scripts.check_kernel_scope import (
    CI_PERFORMANCE_QUALIFICATION_ADDITIONS,
    CK01_AGENT_KERNEL_CONTRACT_ADDITIONS,
    CK02_LOGICAL_CONTRACT_ADDITIONS,
    CK03_SYNTHETIC_ORACLE_ADDITIONS,
    CK04_PHYSICAL_BAKEOFF_ADDITIONS,
    CLEAN_CUTOVER_DOCUMENTATION_ADDITIONS,
    DEV_ENVIRONMENT_BOOTSTRAP_ADDITIONS,
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
    K15_ADDITIONS,
    K16_ADDITIONS,
    R1_ADDITIONS,
    R2_ADDITIONS,
    R3_ADDITIONS,
    R4_ADDITIONS,
    R5_ADDITIONS,
    active_paths,
    load_disposition_manifest,
    publication_ref_failure,
    publication_source_failure,
    scope_failures,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_integration_tree_matches_quarantine_manifest() -> None:
    manifest = load_disposition_manifest(_REPO_ROOT / "config" / "kernel-code-disposition-v1.json")

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
    assert (
        frozenset(
            {
                "scripts/check_kernel_scope.py",
                "src/codex_usage_tracker/kernel/AGENTS.md",
                "src/codex_usage_tracker/kernel/__init__.py",
                "tests/kernel/test_kernel_scope.py",
            }
        )
        == K1A_ADDITIONS
    )


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


def test_r3_additions_are_explicit_and_bounded() -> None:
    assert {
        "src/codex_usage_tracker/kernel/hydration.py",
        "tests/kernel/test_hydration_policy.py",
    } == R3_ADDITIONS


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
        "src/codex_usage_tracker/kernel/allowance/service.py",
        "tests/kernel/allowance/test_service.py",
    } <= K8_ADDITIONS
    assert {
        "config/kernel-release-candidate-budget.json",
        "scripts/check_kernel_release_candidate.py",
        "tests/kernel/test_release_candidate.py",
    } == K9_ADDITIONS
    assert {
        "config/kernel-release-cutover-v1.json",
        ".agents/plugins/marketplace.json",
        "tests/kernel/test_release_cutover.py",
    } == K10_ADDITIONS
    assert {
        "src/codex_usage_tracker/kernel/content.py",
        "tests/kernel/content/__init__.py",
        "tests/kernel/content/test_cli.py",
        "tests/kernel/content/test_service.py",
    } == K12_ADDITIONS
    assert {
        "config/kernel-overlay-adapter-v1.json",
        "tests/kernel/fixtures/overlay-adapter-v1.json",
        "tests/kernel/live/test_overlay_adapter_contract.py",
    } == K13_ADDITIONS
    assert {
        "config/kernel-release-qualification-v1.json",
    } == K14_ADDITIONS
    assert {
        "config/kernel-fault-recovery-scale-v1.json",
        "tests/kernel/test_fault_recovery_scale.py",
    } == K15_ADDITIONS
    assert {
        "config/kernel-stable-contract-v1.json",
        "tests/kernel/test_release_028_qualification.py",
        "tests/kernel/test_stable_contract_028.py",
    } == K16_ADDITIONS
    task_packets = {
        path
        for path in CLEAN_CUTOVER_DOCUMENTATION_ADDITIONS
        if path.startswith("docs/roadmap/tasks/")
    }
    assert len(CLEAN_CUTOVER_DOCUMENTATION_ADDITIONS) == 40
    assert len(task_packets) == 17
    assert {
        "docs/INDEX.md",
        "docs/architecture/AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md",
        "docs/decisions/PHYSICAL_ARCHITECTURE_DECISION.md",
        "docs/decisions/PRODUCT_DIRECTION.md",
        "docs/decisions/evidence/ck04/aggregate-evidence.json",
        "docs/product/SUPPORTED_QUESTION_CONTRACTS.md",
        "docs/architecture/LOGICAL_KERNEL_CONTRACT.md",
        "docs/quality/QUALIFICATION_PLAN.md",
        "docs/roadmap/AGENT_FIRST_CLEAN_CUTOVER.md",
        "docs/roadmap/TASK_PACKETS.md",
        "docs/roadmap/LINEAR_BACKLOG.md",
        "tests/kernel/test_documentation_authority.py",
    } <= CLEAN_CUTOVER_DOCUMENTATION_ADDITIONS
    assert {
        "config/product-recovery-agent-answer-v1.schema.json",
        "config/product-recovery-agent-baseline-v1.json",
        "config/product-recovery-agent-baseline-results-v1.json",
        "config/product-recovery-agent-scorecard-v1.schema.json",
        "scripts/benchmark_agent_outcome.py",
        "tests/kernel/test_agent_outcome_baseline.py",
    } == R1_ADDITIONS
    assert {"tests/kernel/test_schema_v3.py"} == R2_ADDITIONS
    assert {
        "src/codex_usage_tracker/kernel/rollups.py",
        "tests/kernel/interfaces/test_r4_coverage_contract.py",
        "tests/kernel/query/test_r4_rollups.py",
    } == R4_ADDITIONS
    assert {
        "src/codex_usage_tracker/kernel/thread_labels.py",
        "tests/kernel/test_r5_analytical_primitives.py",
    } == R5_ADDITIONS
    assert {
        "config/agent-kernel/question-catalog-v1.json",
        "config/agent-kernel/question-catalog-v1.schema.json",
        "config/agent-kernel/question-guidance-v1.json",
        "scripts/check_agent_kernel_contracts.py",
        "tests/agent_kernel/contracts/__init__.py",
        "tests/agent_kernel/contracts/test_question_catalog.py",
    } == CK01_AGENT_KERNEL_CONTRACT_ADDITIONS
    assert {
        "config/agent-kernel/logical-contract-v1.json",
        "tests/agent_kernel/contracts/reference/__init__.py",
        "tests/agent_kernel/contracts/reference/accounting.py",
        "tests/agent_kernel/contracts/reference/allowance.py",
        "tests/agent_kernel/contracts/reference/contract.py",
        "tests/agent_kernel/contracts/reference/field_contract.py",
        "tests/agent_kernel/contracts/reference/identity.py",
        "tests/agent_kernel/contracts/reference/lifecycle.py",
        "tests/agent_kernel/contracts/reference/selectors.py",
        "tests/agent_kernel/contracts/reference/time.py",
        "tests/agent_kernel/contracts/test_accounting_vectors.py",
        "tests/agent_kernel/contracts/test_allowance_vectors.py",
        "tests/agent_kernel/contracts/test_identity_vectors.py",
        "tests/agent_kernel/contracts/test_lifecycle_vectors.py",
        "tests/agent_kernel/contracts/test_selector_vectors.py",
        "tests/agent_kernel/contracts/test_time_vectors.py",
        "tests/agent_kernel/contracts/vectors/accounting-v1.json",
        "tests/agent_kernel/contracts/vectors/allowance-v1.json",
        "tests/agent_kernel/contracts/vectors/field-contract-v1.json",
        "tests/agent_kernel/contracts/vectors/identity-v1.json",
        "tests/agent_kernel/contracts/vectors/lifecycle-v1.json",
        "tests/agent_kernel/contracts/vectors/selector-v1.json",
        "tests/agent_kernel/contracts/vectors/time-v1.json",
    } == CK02_LOGICAL_CONTRACT_ADDITIONS
    assert {
        "config/agent-kernel/production-shape-profile-v1.schema.json",
        "tests/agent_kernel/fixtures/README.md",
        "tests/agent_kernel/fixtures/__init__.py",
        "tests/agent_kernel/fixtures/generator/__init__.py",
        "tests/agent_kernel/fixtures/generator/cases.py",
        "tests/agent_kernel/fixtures/generator/cli.py",
        "tests/agent_kernel/fixtures/generator/generate.py",
        "tests/agent_kernel/fixtures/generator/profile.py",
        "tests/agent_kernel/fixtures/generator/semantic.py",
        "tests/agent_kernel/fixtures/generator/sources.py",
        "tests/agent_kernel/fixtures/oracles/__init__.py",
        "tests/agent_kernel/fixtures/oracles/accounting.py",
        "tests/agent_kernel/fixtures/oracles/bundle.py",
        "tests/agent_kernel/fixtures/oracles/common.py",
        "tests/agent_kernel/fixtures/oracles/crash.py",
        "tests/agent_kernel/fixtures/oracles/evidence.py",
        "tests/agent_kernel/fixtures/oracles/lifecycle.py",
        "tests/agent_kernel/fixtures/oracles/questions.py",
        "tests/agent_kernel/fixtures/oracles/source_ledger.py",
        "tests/agent_kernel/fixtures/oracles/source_lifecycle.py",
        "tests/agent_kernel/fixtures/profiles/growth-v1.json",
        "tests/agent_kernel/fixtures/profiles/production-shape-v1.json",
        "tests/agent_kernel/fixtures/profiles/production-v1.json",
        "tests/agent_kernel/fixtures/profiles/small-v1.json",
        "tests/agent_kernel/fixtures/profiles/standard-v1.json",
        "tests/agent_kernel/fixtures/profiles/tiny-v1.json",
        "tests/agent_kernel/fixtures/tiny-v1/manifest.json",
        "tests/agent_kernel/fixtures/tiny-v1/oracle-bundle.json",
        "tests/agent_kernel/fixtures/tiny-v1/phases/archive/copy.jsonl",
        "tests/agent_kernel/fixtures/tiny-v1/phases/archive/original.jsonl",
        "tests/agent_kernel/fixtures/tiny-v1/phases/moving_tail/after.jsonl",
        "tests/agent_kernel/fixtures/tiny-v1/phases/moving_tail/before.jsonl",
        "tests/agent_kernel/fixtures/tiny-v1/phases/replacement/after.jsonl",
        "tests/agent_kernel/fixtures/tiny-v1/phases/replacement/before.jsonl",
        "tests/agent_kernel/fixtures/tiny-v1/phases/truncation/after.jsonl",
        "tests/agent_kernel/fixtures/tiny-v1/phases/truncation/before.jsonl",
        "tests/agent_kernel/fixtures/tiny-v1/sources/active/source-0000.jsonl",
        "tests/agent_kernel/fixtures/tiny-v1/sources/active/source-0001.jsonl",
        "tests/agent_kernel/fixtures/tiny-v1/sources/active/source-0002.jsonl",
        "tests/agent_kernel/fixtures/tiny-v1/sources/active/source-0003.jsonl",
        "tests/agent_kernel/fixtures/tiny-v1/sources/active/source-0004.jsonl",
        "tests/agent_kernel/fixtures/tiny-v1/sources/active/source-0005.jsonl",
        "tests/agent_kernel/fixtures/tiny-v1/sources/active/source-0006.jsonl",
        "tests/agent_kernel/fixtures/tiny-v1/sources/archived/exact-copy.jsonl",
        "tests/agent_kernel/fixtures/tiny-v1/sources/malformed/malformed.jsonl",
        "tests/agent_kernel/fixtures/tiny-v1/sources/replaced/revision-1.jsonl",
        "tests/agent_kernel/fixtures/tiny-v1/sources/truncated/truncated.jsonl",
        "tests/agent_kernel/test_fixture_generator.py",
        "tests/agent_kernel/test_fixture_oracles.py",
        "tests/agent_kernel/test_fixture_profiles.py",
        "tests/agent_kernel/test_fixture_reconciliation.py",
    } == CK03_SYNTHETIC_ORACLE_ADDITIONS
    assert {
        "scripts/bootstrap_dev_environment.py",
        "tests/agent_kernel/test_dev_environment_bootstrap.py",
        "tools/gitnexus/package-lock.json",
        "tools/gitnexus/package.json",
    } == DEV_ENVIRONMENT_BOOTSTRAP_ADDITIONS
    assert {
        ".gitignore",
        "experiments/physical-architecture/README.md",
        "experiments/physical-architecture/aggregate_decision_evidence.py",
        "experiments/physical-architecture/decision_evidence.py",
        "experiments/physical-architecture/qualification.py",
        "experiments/physical-architecture/run_agent_perf_evidence.py",
        "experiments/physical-architecture/run_bakeoff.py",
        "experiments/physical-architecture/run_ck04_qualification.py",
        "experiments/physical-architecture/run_dbhub_research.py",
        "experiments/physical-architecture/shared/__init__.py",
        "experiments/physical-architecture/shared/adapter.py",
        "experiments/physical-architecture/shared/agent-perf-workload-v1.schema.json",
        "experiments/physical-architecture/shared/agent_perf.py",
        "experiments/physical-architecture/shared/agent_perf_runner.py",
        "experiments/physical-architecture/shared/canonical.py",
        "experiments/physical-architecture/shared/crash.py",
        "experiments/physical-architecture/shared/dbhub-v0.24.0.contract.json",
        "experiments/physical-architecture/shared/dbhub.py",
        "experiments/physical-architecture/shared/dbhub_runner.py",
        "experiments/physical-architecture/shared/fixture.py",
        "experiments/physical-architecture/shared/measurement.py",
        "experiments/physical-architecture/shared/outcomes.py",
        "experiments/physical-architecture/shared/scoring.py",
        "experiments/physical-architecture/shared/stop.py",
        "experiments/physical-architecture/shared/workload.py",
        "experiments/physical-architecture/candidate_a/__init__.py",
        "experiments/physical-architecture/candidate_a/adapter.py",
        "experiments/physical-architecture/candidate_a/agent-perf-workload.json",
        "experiments/physical-architecture/candidate_a/crash_worker.py",
        "experiments/physical-architecture/candidate_a/evidence.py",
        "experiments/physical-architecture/candidate_a/ingest.py",
        "experiments/physical-architecture/candidate_a/maintenance.py",
        "experiments/physical-architecture/candidate_a/metrics.py",
        "experiments/physical-architecture/candidate_a/prepared_artifact.py",
        "experiments/physical-architecture/candidate_a/publication.py",
        "experiments/physical-architecture/candidate_a/queries.py",
        "experiments/physical-architecture/candidate_a/schema.py",
        "experiments/physical-architecture/candidate_a/workload.py",
        "experiments/physical-architecture/candidate_c/__init__.py",
        "experiments/physical-architecture/candidate_c/adapter.py",
        "experiments/physical-architecture/candidate_c/database.py",
        "experiments/physical-architecture/candidate_c/records.py",
        "experiments/physical-architecture/candidate_c/schema.py",
        "experiments/physical-architecture/candidate_c/workload.py",
        "experiments/physical-architecture/candidate_d/__init__.py",
        "experiments/physical-architecture/candidate_d/adapter.py",
        "experiments/physical-architecture/candidate_d/agent-perf-workload.json",
        "experiments/physical-architecture/candidate_d/crash.py",
        "experiments/physical-architecture/candidate_d/schema.py",
        "experiments/physical-architecture/candidate_d/store.py",
        "experiments/physical-architecture/candidate_d/workload.py",
        "tests/experiments/physical-architecture/candidate_a/test_candidate_a.py",
        "tests/experiments/physical-architecture/candidate_a/test_candidate_a_parser_workers.py",
        "tests/experiments/physical-architecture/candidate_a/test_candidate_a_query_eligibility.py",
        "tests/experiments/physical-architecture/candidate_a/test_candidate_a_query_hardening.py",
        "tests/experiments/physical-architecture/candidate_a/test_candidate_a_recovery.py",
        "tests/experiments/physical-architecture/candidate_a/test_candidate_a_tail_hardening.py",
        "tests/experiments/physical-architecture/candidate_a/test_prepared_artifact.py",
        "tests/experiments/physical-architecture/candidate_c/test_candidate_c.py",
        "tests/experiments/physical-architecture/candidate_d/test_candidate_d.py",
        "tests/experiments/physical-architecture/test_agent_perf_evidence.py",
        "tests/experiments/physical-architecture/test_aggregate_decision_evidence.py",
        "tests/experiments/physical-architecture/test_decision_evidence.py",
        "tests/experiments/physical-architecture/test_bakeoff_runner.py",
        "tests/experiments/physical-architecture/test_dbhub_runner.py",
        "tests/experiments/physical-architecture/test_qualification_suite.py",
        "tests/experiments/physical-architecture/test_shared_harness.py",
        "tests/agent_kernel/contracts/test_database_v1_schema_contract.py",
    } == CK04_PHYSICAL_BAKEOFF_ADDITIONS
    assert {
        ".github/workflows/performance-qualification.yml",
        "docs/quality/CI_PERFORMANCE_QUALIFICATION.md",
        "scripts/aggregate_performance_qualification.py",
        "scripts/performance_budget_contract.py",
        "scripts/run_performance_suite.py",
        "tests/kernel/performance_qualification.py",
        "tests/kernel/test_ci_performance_qualification.py",
    } == CI_PERFORMANCE_QUALIFICATION_ADDITIONS
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
        | K15_ADDITIONS
        | K16_ADDITIONS
        | CLEAN_CUTOVER_DOCUMENTATION_ADDITIONS
        | R1_ADDITIONS
        | R2_ADDITIONS
        | R3_ADDITIONS
        | R4_ADDITIONS
        | R5_ADDITIONS
        | CK01_AGENT_KERNEL_CONTRACT_ADDITIONS
        | CK02_LOGICAL_CONTRACT_ADDITIONS
        | CK03_SYNTHETIC_ORACLE_ADDITIONS
        | DEV_ENVIRONMENT_BOOTSTRAP_ADDITIONS
        | CK04_PHYSICAL_BAKEOFF_ADDITIONS
        | CI_PERFORMANCE_QUALIFICATION_ADDITIONS
    )


def test_kernel_skeleton_imports_without_legacy_runtime() -> None:
    import codex_usage_tracker.kernel as kernel

    assert kernel.__version__ == "0.28.0"


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
    assert publication_ref_failure("refs/heads/release/0.28.0", "0.28.0")
    assert publication_ref_failure("refs/heads/main", "0.28.0") is None


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
    git("tag", "v0.28.0")

    failure = publication_source_failure(
        repo,
        ref="refs/tags/v0.28.0",
        sha=unmerged_sha,
        package_version="0.28.0",
    )

    assert failure == (f"publication SHA {unmerged_sha} is not merged into origin/main")


def test_publish_workflow_calls_persistent_kernel_guard() -> None:
    workflow = (_REPO_ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")

    assert "Enforce kernel publication source" in workflow
    assert "scripts/check_kernel_scope.py" in workflow
    assert '--publication-ref "$GITHUB_REF"' in workflow
    assert "git fetch --no-tags origin main:refs/remotes/origin/main" in workflow
    assert '--publication-sha "$GITHUB_SHA"' in workflow
    assert "--main-ref origin/main" in workflow
