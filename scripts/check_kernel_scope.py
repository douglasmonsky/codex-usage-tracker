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
        ".agent-maintainer/change-plans/k1a-legacy-quarantine.md",
        "docs/kernel-development-scope.md",
        "scripts/check_kernel_scope.py",
        "src/codex_usage_tracker/kernel/AGENTS.md",
        "src/codex_usage_tracker/kernel/__init__.py",
        "tests/kernel/test_kernel_scope.py",
    }
)
K2_ADDITIONS = frozenset(
    {
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
    }
)
K3_ADDITIONS = frozenset(
    {
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
    }
)
K4_ADDITIONS = frozenset(
    {
        ".agent-maintainer/change-plans/k4-bounded-query-engine.md",
        "src/codex_usage_tracker/kernel/query/__init__.py",
        "src/codex_usage_tracker/kernel/query/catalog.py",
        "src/codex_usage_tracker/kernel/query/contracts.py",
        "src/codex_usage_tracker/kernel/query/phases.py",
        "src/codex_usage_tracker/kernel/query/plans.py",
        "src/codex_usage_tracker/kernel/query/service.py",
        "tests/kernel/query/__init__.py",
        "tests/kernel/query/test_contracts.py",
        "tests/kernel/query/test_performance.py",
        "tests/kernel/query/test_phases.py",
        "tests/kernel/query/test_service.py",
    }
)
K5_ADDITIONS = frozenset(
    {
        ".agent-maintainer/change-plans/k5-evidence-live.md",
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
        ".agent-maintainer/change-plans/k6-interface-cutover.md",
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
        ".agent-maintainer/change-plans/k7-evidence-console.md",
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
        ".agent-maintainer/change-plans/k8-allowance-efficiency.md",
        "docs/kernel-allowance-efficiency.md",
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

INTEGRATION_ADDITIONS = (
    K1A_ADDITIONS
    | K2_ADDITIONS
    | K3_ADDITIONS
    | K4_ADDITIONS
    | K5_ADDITIONS
    | K6_ADDITIONS
    | K7_ADDITIONS
    | K8_ADDITIONS
)
_BLOCKED_TASK_REF = re.compile(
    r"^refs/heads/kernel/(?:0\.26-integration|k(?:1a|[2-9])(?:-|$))"
)


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
    return {line for line in result.stdout.splitlines() if line}


def scope_failures(repo_root: Path, manifest: dict[str, Any]) -> list[str]:
    """Return deterministic violations of the K1A active-tree contract."""

    entries = manifest["entries"]
    current = active_paths(repo_root)
    classified = {entry["path"] for entry in entries}
    kept = {entry["path"] for entry in entries if entry["disposition"] == "keep"}
    removed = {
        entry["path"] for entry in entries if entry["disposition"] != "keep"
    }
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
        if (
            disposition != "keep"
            and status not in valid_absent_statuses[disposition]
        ):
            failures.append(
                f"{entry['path']}: invalid absent {disposition} status {status}"
            )
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    parser.add_argument("--publication-ref")
    parser.add_argument("--package-version")
    args = parser.parse_args()

    if args.publication_ref:
        if not args.package_version:
            parser.error("--package-version is required with --publication-ref")
        failure = publication_ref_failure(
            args.publication_ref,
            args.package_version,
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
