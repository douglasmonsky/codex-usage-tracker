#!/usr/bin/env python3
"""Fail closed when the integration tree escapes the K1 quarantine contract."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
K1A_ADDITIONS = frozenset(
    {
        "scripts/check_kernel_scope.py",
        "src/codex_usage_tracker/kernel/AGENTS.md",
        "src/codex_usage_tracker/kernel/__init__.py",
        "tests/kernel/test_kernel_scope.py",
    }
)
K2_ADDITIONS = frozenset(
    {
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
    }
)
K3_ADDITIONS = frozenset(
    {
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
    }
)
K4_ADDITIONS = frozenset(
    {
        "src/codex_usage_tracker/kernel/query/__init__.py",
        "src/codex_usage_tracker/kernel/query/catalog.py",
        "src/codex_usage_tracker/kernel/query/contracts.py",
        "src/codex_usage_tracker/kernel/query/phases.py",
        "src/codex_usage_tracker/kernel/query/plans.py",
        "src/codex_usage_tracker/kernel/query/service.py",
        "src/codex_usage_tracker/kernel/query/thread_cost_plan.py",
        "tests/kernel/query/__init__.py",
        "tests/kernel/query/test_contracts.py",
        "tests/kernel/query/test_performance.py",
        "tests/kernel/query/test_phases.py",
        "tests/kernel/query/test_service.py",
    }
)
K5_ADDITIONS = frozenset(
    {
        "src/codex_usage_tracker/kernel/evidence/__init__.py",
        "src/codex_usage_tracker/kernel/evidence/contracts.py",
        "src/codex_usage_tracker/kernel/evidence/service.py",
        "src/codex_usage_tracker/kernel/live/__init__.py",
        "src/codex_usage_tracker/kernel/live/journal.py",
        "src/codex_usage_tracker/kernel/live/stream.py",
        "tests/kernel/evidence/__init__.py",
        "tests/kernel/evidence/test_contracts.py",
        "tests/kernel/evidence/test_performance.py",
        "tests/kernel/evidence/test_service.py",
        "tests/kernel/live/__init__.py",
        "tests/kernel/live/test_contracts.py",
        "tests/kernel/live/test_ingest_integration.py",
    }
)
K6_ADDITIONS = frozenset(
    {
        "scripts/generate_kernel_interfaces.py",
        "skills/usage-kernel/SKILL.md",
        "src/codex_usage_tracker/kernel/application/__init__.py",
        "src/codex_usage_tracker/kernel/application/codec.py",
        "src/codex_usage_tracker/kernel/application/jobs.py",
        "src/codex_usage_tracker/kernel/application/runtime.py",
        "src/codex_usage_tracker/kernel/application/service.py",
        "src/codex_usage_tracker/kernel/interfaces/__init__.py",
        "src/codex_usage_tracker/kernel/interfaces/cli/__init__.py",
        "src/codex_usage_tracker/kernel/interfaces/cli/main.py",
        "src/codex_usage_tracker/kernel/interfaces/http/__init__.py",
        "src/codex_usage_tracker/kernel/interfaces/http/app.py",
        "src/codex_usage_tracker/kernel/interfaces/http/server.py",
        "src/codex_usage_tracker/kernel/interfaces/mcp/__init__.py",
        "src/codex_usage_tracker/kernel/interfaces/mcp/catalog.py",
        "src/codex_usage_tracker/kernel/interfaces/mcp/server.py",
        "src/codex_usage_tracker/kernel/interfaces/schema_catalog.py",
        "src/codex_usage_tracker/kernel/interfaces/schemas/usage_allowance.json",
        "src/codex_usage_tracker/kernel/interfaces/schemas/usage_evidence.json",
        "src/codex_usage_tracker/kernel/interfaces/schemas/usage_job_status.json",
        "src/codex_usage_tracker/kernel/interfaces/schemas/usage_query.json",
        "src/codex_usage_tracker/kernel/interfaces/schemas/usage_refresh.json",
        "src/codex_usage_tracker/kernel/interfaces/schemas/usage_status.json",
        "src/codex_usage_tracker/kernel/plugin_manifest.py",
        "tests/kernel/interfaces/__init__.py",
        "tests/kernel/interfaces/support.py",
        "tests/kernel/interfaces/test_application.py",
        "tests/kernel/interfaces/test_cli.py",
        "tests/kernel/interfaces/test_contracts.py",
        "tests/kernel/interfaces/test_http.py",
        "tests/kernel/interfaces/test_mcp.py",
        "tests/kernel/interfaces/test_performance.py",
        "tests/kernel/interfaces/test_plugin.py",
    }
)
K7_ADDITIONS = frozenset(
    {
        "frontend/kernel-console/app.js",
        "frontend/kernel-console/index.html",
        "frontend/kernel-console/model.js",
        "frontend/kernel-console/styles.css",
        "frontend/kernel-console/tsconfig.json",
        "scripts/build_kernel_console.mjs",
        "scripts/check_kernel_console.mjs",
        "scripts/smoke_installed_console.py",
        "src/codex_usage_tracker/kernel/interfaces/http/console.py",
        "src/codex_usage_tracker/kernel/interfaces/http/console_assets/app.js",
        "src/codex_usage_tracker/kernel/interfaces/http/console_assets/asset-manifest.json",
        "src/codex_usage_tracker/kernel/interfaces/http/console_assets/index.html",
        "src/codex_usage_tracker/kernel/interfaces/http/console_assets/model.js",
        "src/codex_usage_tracker/kernel/interfaces/http/console_assets/styles.css",
        "tests/frontend/kernel_console.test.mjs",
        "tests/e2e/kernel-console.spec.mjs",
        "tests/kernel/console/__init__.py",
        "tests/kernel/console/serve_fixture.py",
        "tests/kernel/console/test_contracts.py",
    }
)
K8_ADDITIONS = frozenset(
    {
        "src/codex_usage_tracker/kernel/allowance/__init__.py",
        "src/codex_usage_tracker/kernel/allowance/efficiency.py",
        "src/codex_usage_tracker/kernel/allowance/rates.py",
        "src/codex_usage_tracker/kernel/allowance/service.py",
        "tests/kernel/allowance/__init__.py",
        "tests/kernel/allowance/test_efficiency.py",
        "tests/kernel/allowance/test_performance.py",
        "tests/kernel/allowance/test_rates.py",
        "tests/kernel/allowance/test_service.py",
    }
)
K9_ADDITIONS = frozenset(
    {
        "config/kernel-release-candidate-budget.json",
        "scripts/check_kernel_release_candidate.py",
        "tests/kernel/test_release_candidate.py",
    }
)

K10_ADDITIONS = frozenset(
    {
        "config/kernel-release-cutover-v1.json",
        ".agents/plugins/marketplace.json",
        "tests/kernel/test_release_cutover.py",
    }
)

K12_ADDITIONS = frozenset(
    {
        "src/codex_usage_tracker/kernel/content.py",
        "tests/kernel/content/__init__.py",
        "tests/kernel/content/test_cli.py",
        "tests/kernel/content/test_service.py",
    }
)

K13_ADDITIONS = frozenset(
    {
        "config/kernel-overlay-adapter-v1.json",
        "tests/kernel/fixtures/overlay-adapter-v1.json",
        "tests/kernel/live/test_overlay_adapter_contract.py",
    }
)

K14_ADDITIONS = frozenset(
    {
        "config/kernel-release-qualification-v1.json",
    }
)

K15_ADDITIONS = frozenset(
    {
        "config/kernel-fault-recovery-scale-v1.json",
        "tests/kernel/test_fault_recovery_scale.py",
    }
)

K16_ADDITIONS = frozenset(
    {
        "config/kernel-stable-contract-v1.json",
        "tests/kernel/test_release_028_qualification.py",
        "tests/kernel/test_stable_contract_028.py",
    }
)

CLEAN_CUTOVER_DOCUMENTATION_ADDITIONS = frozenset(
    {
        "docs/INDEX.md",
        "docs/architecture/ADAPTER_CONTRACT.md",
        "docs/architecture/AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md",
        "docs/architecture/LOGICAL_KERNEL_CONTRACT.md",
        "docs/architecture/PHYSICAL_ARCHITECTURE_BAKEOFF.md",
        "docs/architecture/PUBLICATION_REFRESH_RECOVERY.md",
        "docs/architecture/QUERY_EVIDENCE_PROJECTION_CONTRACTS.md",
        "docs/architecture/TARGET_ARCHITECTURE.md",
        "docs/archive/SPIKE_DISPOSITION.md",
        "docs/archive/SPIKE_PERFORMANCE_EVIDENCE.md",
        "docs/archive/spike/ALLOWANCE_EFFICIENCY_FINDINGS.md",
        "docs/archive/spike/KERNEL_STABLE_CONTRACT_0_28.md",
        "docs/archive/spike/OVERLAY_ADAPTER_CONTRACT_0_28.md",
        "docs/decisions/PHYSICAL_ARCHITECTURE_DECISION.md",
        "docs/decisions/PRODUCT_DIRECTION.md",
        "docs/decisions/evidence/ck04/aggregate-evidence.json",
        "docs/product/AGENT_SETUP_AND_MCP_EXPERIENCE.md",
        "docs/product/SUPPORTED_QUESTION_CONTRACTS.md",
        "docs/quality/QUALIFICATION_PLAN.md",
        "docs/roadmap/AGENT_FIRST_CLEAN_CUTOVER.md",
        "docs/roadmap/LINEAR_BACKLOG.md",
        "docs/roadmap/TASK_PACKETS.md",
        "docs/roadmap/tasks/ck-00-clean-authority-and-freeze-spike.md",
        "docs/roadmap/tasks/ck-01-make-question-catalog-executable.md",
        "docs/roadmap/tasks/ck-02-freeze-logical-contract-vectors.md",
        "docs/roadmap/tasks/ck-03-build-synthetic-fixtures-and-oracles.md",
        "docs/roadmap/tasks/ck-04-run-physical-architecture-bakeoff.md",
        "docs/roadmap/tasks/ck-05-implement-canonical-storage-kernel.md",
        "docs/roadmap/tasks/ck-06-implement-codex-adapter-and-ingestion.md",
        "docs/roadmap/tasks/ck-07-implement-publication-refresh-recovery.md",
        "docs/roadmap/tasks/ck-08-implement-query-and-evidence.md",
        "docs/roadmap/tasks/ck-09-admit-projections-and-named-plans.md",
        "docs/roadmap/tasks/ck-10-deliver-setup-mcp-cli-skill.md",
        "docs/roadmap/tasks/ck-11-build-installed-agent-harness.md",
        "docs/roadmap/tasks/ck-12-qualify-and-harden-mvp.md",
        "docs/roadmap/tasks/ck-13-execute-clean-cutover.md",
        "docs/roadmap/tasks/ck-14-delete-spike-console-obsolete-surfaces.md",
        "docs/roadmap/tasks/ck-15-add-optional-native-presentation.md",
        "docs/roadmap/tasks/ck-16-publish-docs-and-release.md",
        "tests/kernel/test_documentation_authority.py",
    }
)
R1_ADDITIONS = frozenset(
    {
        "config/product-recovery-agent-answer-v1.schema.json",
        "config/product-recovery-agent-baseline-v1.json",
        "config/product-recovery-agent-baseline-results-v1.json",
        "config/product-recovery-agent-scorecard-v1.schema.json",
        "scripts/benchmark_agent_outcome.py",
        "tests/kernel/test_agent_outcome_baseline.py",
    }
)
R2_ADDITIONS = frozenset({"tests/kernel/test_schema_v3.py"})
R3_ADDITIONS = frozenset(
    {
        "src/codex_usage_tracker/kernel/hydration.py",
        "tests/kernel/test_hydration_policy.py",
    }
)
R4_ADDITIONS = frozenset(
    {
        "src/codex_usage_tracker/kernel/rollups.py",
        "tests/kernel/interfaces/test_r4_coverage_contract.py",
        "tests/kernel/query/test_r4_rollups.py",
    }
)
R5_ADDITIONS = frozenset(
    {
        "src/codex_usage_tracker/kernel/thread_labels.py",
        "tests/kernel/test_r5_analytical_primitives.py",
    }
)

CK01_AGENT_KERNEL_CONTRACT_ADDITIONS = frozenset(
    {
        "config/agent-kernel/question-catalog-v1.json",
        "config/agent-kernel/question-catalog-v1.schema.json",
        "config/agent-kernel/question-guidance-v1.json",
        "scripts/check_agent_kernel_contracts.py",
        "tests/agent_kernel/contracts/__init__.py",
        "tests/agent_kernel/contracts/test_question_catalog.py",
    }
)

CK02_LOGICAL_CONTRACT_ADDITIONS = frozenset(
    {
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
    }
)

CK03_SYNTHETIC_ORACLE_ADDITIONS = frozenset(
    {
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
    }
)

DEV_ENVIRONMENT_BOOTSTRAP_ADDITIONS = frozenset(
    {
        "scripts/bootstrap_dev_environment.py",
        "tests/agent_kernel/test_dev_environment_bootstrap.py",
        "tools/gitnexus/package-lock.json",
        "tools/gitnexus/package.json",
    }
)

CK04_PHYSICAL_BAKEOFF_ADDITIONS = frozenset(
    {
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
    }
)

CI_PERFORMANCE_QUALIFICATION_ADDITIONS = frozenset(
    {
        ".github/workflows/performance-qualification.yml",
        "docs/quality/CI_PERFORMANCE_QUALIFICATION.md",
        "scripts/aggregate_performance_qualification.py",
        "scripts/performance_budget_contract.py",
        "scripts/run_performance_suite.py",
        "tests/kernel/performance_qualification.py",
        "tests/kernel/test_ci_performance_qualification.py",
    }
)

INTEGRATION_ADDITIONS = (
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
_BLOCKED_TASK_REF = re.compile(r"^refs/heads/kernel/(?:0\.26-integration|k(?:1a|[2-9])(?:-|$))")


def load_disposition_manifest(path: Path) -> dict[str, Any]:
    """Load the frozen K1 path inventory."""

    return json.loads(path.read_text(encoding="utf-8"))


def active_paths(repo_root: Path) -> set[str]:
    """Return tracked and non-ignored untracked paths in the active worktree."""

    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    paths = {line for line in result.stdout.splitlines() if line}
    return {
        path for path in paths if (repo_root / path).exists() or (repo_root / path).is_symlink()
    }


def scope_failures(repo_root: Path, manifest: dict[str, Any]) -> list[str]:
    """Return deterministic violations of the K1A active-tree contract."""

    entries = manifest["entries"]
    current = active_paths(repo_root)
    classified = {entry["path"] for entry in entries}
    kept = {entry["path"] for entry in entries if entry["disposition"] == "keep"}
    removed = {entry["path"] for entry in entries if entry["disposition"] != "keep"}
    failures: list[str] = []

    physically_present = {
        path
        for path in classified
        if (repo_root / path).exists() or (repo_root / path).is_symlink()
    }

    for path in sorted(kept - physically_present):
        failures.append(f"required keep path is absent: {path}")
    for path in sorted(removed & physically_present):
        failures.append(f"quarantined path remains active: {path}")
    for path in sorted(current - classified - INTEGRATION_ADDITIONS):
        failures.append(f"unclassified integration path: {path}")

    for entry in entries:
        disposition = entry["disposition"]
        status = entry["status"]
        valid_absent_statuses = {
            "historical": {"removed", "archived", "verified"},
            "retire": {"removed", "verified"},
            "transplant": {"removed", "implemented", "verified"},
        }
        if disposition != "keep" and status not in valid_absent_statuses[disposition]:
            failures.append(f"{entry['path']}: invalid absent {disposition} status {status}")
        if disposition == "transplant":
            if not entry["source_ref"].startswith("v0.25.1:"):
                failures.append(f"{entry['path']}: transplant lacks tag provenance")
            if not entry["target_path"] or not entry["owner_task"]:
                failures.append(f"{entry['path']}: transplant lacks owner or target")
    return failures


def publication_ref_failure(ref: str, package_version: str) -> str | None:
    """Explain why a ref/version combination must not publish."""

    if _BLOCKED_TASK_REF.match(ref):
        return f"publication is forbidden from integration ref {ref}"
    if ref.startswith("refs/heads/kernel/"):
        return f"publication is forbidden from kernel task ref {ref}"
    if ref in {"refs/heads/main"} or ref.startswith("refs/tags/"):
        if ".dev" in package_version:
            return f"development version {package_version} cannot publish from {ref}"
        return None
    return f"publication requires main or an exact tag ref, got {ref}"


def publication_source_failure(
    repo_root: Path,
    *,
    ref: str,
    sha: str,
    package_version: str,
    main_ref: str = "origin/main",
) -> str | None:
    """Fail closed unless the exact publication commit is merged into main."""
    ref_failure = publication_ref_failure(ref, package_version)
    if ref_failure:
        return ref_failure

    def resolve(commitish: str) -> str | None:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", f"{commitish}^{{commit}}"],
            cwd=repo_root,
            capture_output=True,
            check=False,
            text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    resolved_sha = resolve(sha)
    resolved_ref = resolve(ref)
    resolved_main = resolve(main_ref)
    if resolved_sha is None:
        return f"publication SHA is unavailable: {sha}"
    if resolved_ref != resolved_sha:
        return f"publication ref {ref} does not resolve exact SHA {sha}"
    if resolved_main is None:
        return f"publication main ref is unavailable: {main_ref}"
    if ref == "refs/heads/main" and resolved_sha != resolved_main:
        return f"main publication SHA {sha} differs {main_ref} at {resolved_main}"
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", resolved_sha, resolved_main],
        cwd=repo_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if ancestry.returncode != 0:
        return f"publication SHA {sha} is not merged into {main_ref}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    parser.add_argument("--publication-ref")
    parser.add_argument("--publication-sha")
    parser.add_argument("--main-ref", default="origin/main")
    parser.add_argument("--package-version")
    args = parser.parse_args()

    if args.publication_ref:
        if not args.package_version:
            parser.error("--package-version is required with --publication-ref")
        if not args.publication_sha:
            parser.error("--publication-sha is required with --publication-ref")
        failure = publication_source_failure(
            args.repo_root,
            ref=args.publication_ref,
            sha=args.publication_sha,
            package_version=args.package_version,
            main_ref=args.main_ref,
        )
        if failure:
            print(failure)
            return 1
        print("Publication ref is eligible.")
        return 0

    manifest = load_disposition_manifest(
        args.repo_root / "config" / "kernel-code-disposition-v1.json"
    )
    failures = scope_failures(args.repo_root, manifest)
    if failures:
        print("\n".join(failures))
        return 1
    print("Kernel integration scope passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
