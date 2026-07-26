from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.core.json_contracts import known_json_schemas
from tests.release_catalog import (
    CANONICAL_DATA_POSTURE,
    CANONICAL_PACKAGE_DESCRIPTION,
    CORE_MCP_TOOL_NAMES,
    FULL_MCP_TOOL_NAMES,
    MCP_PROFILE_TOOL_COUNTS,
    RELEASE_022_SCHEMA_IDS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_product_kernel_reset_names_the_normative_release_sequence() -> None:
    roadmap = (REPO_ROOT / "docs/roadmap/product-kernel-reset.md").read_text(
        encoding="utf-8"
    )

    releases = ["0.25.x", "0.26.0", "0.27.0", "0.28.0"]
    positions = [roadmap.index(release) for release in releases]

    assert positions == sorted(positions)
    assert "after Release 0.25.1" in roadmap


def test_product_kernel_reset_freezes_the_six_tool_factual_surface() -> None:
    roadmap = (REPO_ROOT / "docs/roadmap/product-kernel-reset.md").read_text(
        encoding="utf-8"
    )
    execution = (
        REPO_ROOT / "docs/roadmap/product-kernel-reset-execution.md"
    ).read_text(encoding="utf-8")
    plan = (
        REPO_ROOT / "docs/superpowers/plans/2026-07-26-product-kernel-reset.md"
    ).read_text(encoding="utf-8")
    design = (
        REPO_ROOT / "docs/superpowers/specs/2026-07-26-product-kernel-reset-design.md"
    ).read_text(encoding="utf-8")

    target_tools = [
        "usage_status",
        "usage_refresh",
        "usage_query",
        "usage_evidence",
        "usage_allowance",
        "usage_job_status",
    ]
    mcp_section = roadmap.split("### MCP", maxsplit=1)[1].split(
        "### Evidence Console", maxsplit=1
    )[0]
    numbered_tools = [
        line.split("`", maxsplit=2)[1]
        for line in mcp_section.splitlines()
        if line[:1].isdigit() and ". `" in line
    ]
    assert numbered_tools == target_tools
    assert "`usage_analyze` is removed" in roadmap
    assert "The tracker owns:" in roadmap
    assert "Codex owns:" in roadmap
    assert "## 7. Query Contract" in design
    assert "## 13. Deletion Boundary" in design
    assert "**Published baseline:** `codex-usage-tracking==0.25.1`" in design
    assert "## Task K6 — Build Kernel Interfaces In The Integration Tree" in plan
    assert "| K1A | 0.26 integration | Not started | K1 |" in execution
    assert "2026-07-26-kernel-code-quarantine-design.md" in roadmap
    assert "| K16 | 0.28.0 | Not started" in execution


def test_archived_mcp_first_program_remains_available_without_authority() -> None:
    redirect_paths = [
        "docs/roadmap/mcp-first-pivot.md",
        "docs/roadmap/mcp-first-pivot-execution.md",
        "docs/superpowers/plans/2026-07-21-mcp-first-product-pivot.md",
        "docs/superpowers/specs/2026-07-21-mcp-first-product-pivot-design.md",
        ".agent-maintainer/change-plans/mcp-first-product-pivot.md",
    ]
    for relative_path in redirect_paths:
        redirect = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "Archived" in redirect
        assert "product-kernel-reset" in redirect

    roadmap_redirect = (REPO_ROOT / redirect_paths[0]).read_text(encoding="utf-8")
    assert "does not authorize new MCP-first pivot tasks" in " ".join(
        roadmap_redirect.split()
    )

    archived_markers = {
        "docs/roadmap/archive/2026-07-21-mcp-first-pivot/README.md": (
            "# MCP-First Product Pivot Archive"
        ),
        "docs/roadmap/archive/2026-07-21-mcp-first-pivot/roadmap.md": (
            "## Release Sequence"
        ),
        "docs/roadmap/archive/2026-07-21-mcp-first-pivot/execution-ledger.md": (
            "## Task 27.5 - Foundation Audit and 0.24 Plan Confirmation"
        ),
        "docs/roadmap/archive/2026-07-21-mcp-first-pivot/deprecations.md": (
            "# Archived MCP-First Deprecation Ledger"
        ),
        "docs/superpowers/plans/archive/2026-07-21-mcp-first-product-pivot.md": (
            "**Program size:** 46 tasks"
        ),
        "docs/superpowers/specs/archive/2026-07-21-mcp-first-product-pivot-design.md": (
            "## 1. Executive decision"
        ),
        ".agent-maintainer/change-plans/archive/mcp-first-product-pivot.md": (
            "# Archived: MCP-First Product Pivot Change Plan"
        ),
    }
    for relative_path, marker in archived_markers.items():
        archive = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert marker in archive


def test_kernel_reset_design_and_plan_are_decision_complete() -> None:
    plan = (
        REPO_ROOT / "docs/superpowers/plans/2026-07-26-product-kernel-reset.md"
    ).read_text(encoding="utf-8")
    design = (
        REPO_ROOT / "docs/superpowers/specs/2026-07-26-product-kernel-reset-design.md"
    ).read_text(encoding="utf-8")
    quarantine = (
        REPO_ROOT
        / "docs/superpowers/specs/2026-07-26-kernel-code-quarantine-design.md"
    ).read_text(encoding="utf-8")
    release_checklist = (REPO_ROOT / "docs/release-checklist.md").read_text(
        encoding="utf-8"
    )

    task_headings = [
        line.split(" — ", maxsplit=1)[0].removeprefix("## ")
        for line in plan.splitlines()
        if line.startswith("## ") and "Task K" in line
    ]
    assert task_headings == [
        "Task K0",
        "Task K1",
        "Task K1A",
        *[f"Task K{index}" for index in range(2, 17)],
    ]
    assert "A query never starts a refresh." in plan
    assert "Browser open or reopen never starts an initial build." in plan
    assert "New cache, not migration 40" in design
    assert "The old source remains available through Git history" in design
    assert "kernel/0.26-integration" in quarantine
    assert "non-publishable" in quarantine
    assert "policy-read-only" in quarantine
    assert "v0.25.1" in quarantine
    for disposition in ("keep", "transplant", "retire", "historical"):
        assert f"`{disposition}`" in quarantine
        assert f"| `{disposition}` |" in quarantine
    assert "exactly every path returned by `git ls-files`" in quarantine
    assert "`verified` is the only terminal status" in quarantine
    assert "`kernel/k<owner>-mainline-port-<issue>`" in quarantine
    assert "branch/ref publication guard" in quarantine
    assert "`release/0.26.0` from an audited current-`main` SHA" in quarantine
    assert plan.index("## Task K1A") < plan.index("## Task K2")
    assert "Build Kernel Interfaces In The Integration Tree" in plan
    assert "config/kernel-code-disposition-v1.json" in plan
    assert "**Branch:** `release/0.26.0`, created from the audited" in plan
    assert "**PR:** `release/0.26.0` -> `main`" in plan
    assert "publication rejection from the K9 integration release candidate" in plan
    assert "branch/ref publication-rejection" in release_checklist
    assert "If `main` moves, restart the audit" in release_checklist
    assert "2026-07-26-kernel-code-quarantine-design.md" in design


def test_deprecation_ledger_has_required_compatibility_columns() -> None:
    deprecations = (REPO_ROOT / "docs/deprecations.md").read_text(
        encoding="utf-8"
    )
    normalized_deprecations = " ".join(deprecations.split())

    for column in (
        "Public name or route",
        "Replacement",
        "Owner",
        "Deprecated release",
        "Final supported release",
        "Removal release",
        "Compatibility test",
        "Migration example",
    ):
        assert f"| {column} " in deprecations
    assert "does not ship runtime adapters" in deprecations
    assert "`usage_analyze` and `analysis.v2`" in deprecations
    assert "config/kernel-retired-surfaces-v1.json" in deprecations
    assert "config/kernel-code-disposition-v1.json" in deprecations
    assert "kernel/0.26-integration" in deprecations
    assert "Every path returned by `git ls-files` at K1" in normalized_deprecations
    assert "`verified` is the only terminal" in normalized_deprecations
    assert "creates `release/0.26.0` from audited current" in normalized_deprecations
    assert "## Cutover State Machine" in deprecations


def test_agent_branch_prefixes_allow_the_required_kernel_branches() -> None:
    guidance = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    allowed_prefixes = next(
        line for line in guidance.splitlines() if line.startswith("- Use branch prefixes ")
    )

    assert "`kernel/`" in allowed_prefixes
    assert "`pivot/`" not in allowed_prefixes
    assert "kernel/0.26-integration" in guidance
    assert "non-publishable" in guidance
    assert "policy-read-only" in guidance
    assert "K1A–K9" in guidance
    assert "kernel/k<owner>-mainline-port-<issue>" in guidance
    assert "`release/0.26.0` from an audited current-`main` SHA" in guidance
    assert "branch/ref publication guard" in guidance


def test_architecture_declares_facts_below_model_inference() -> None:
    architecture = (REPO_ROOT / "docs/architecture.md").read_text(encoding="utf-8")
    normalized_architecture = " ".join(architecture.split())

    assert "The tracker owns exact facts" in architecture
    assert "Codex owns inference" in architecture
    assert "Queries and browser opens never start refresh" in normalized_architecture
    assert "`usage_analyze` and runtime compatibility profiles are" in architecture


def test_package_and_readme_position_mcp_before_the_evidence_console() -> None:
    metadata = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    title_paragraph = readme.split("# Codex Usage Tracker\n", maxsplit=1)[1].split(
        "\n\n", maxsplit=1
    )[0]

    assert f'description = "{CANONICAL_PACKAGE_DESCRIPTION}"' in metadata
    assert "MCP conversational analysis" in title_paragraph
    assert title_paragraph.index("MCP conversational analysis") < title_paragraph.index(
        "Evidence Console"
    )


def test_public_docs_do_not_claim_dashboard_first_or_aggregate_only_storage() -> None:
    public_docs = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs/first-five-minutes.md",
        REPO_ROOT / "docs/dashboard-guide.md",
        REPO_ROOT / "docs/mcp.md",
        REPO_ROOT / "docs/privacy.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in public_docs)

    assert "The dashboard is the core product surface" not in combined
    assert "SQLite stores aggregate metrics only" not in combined


def test_022_release_and_upgrade_docs_define_the_profile_transition() -> None:
    release = (REPO_ROOT / "docs/releases/0.22.0.md").read_text(encoding="utf-8")
    upgrade = (REPO_ROOT / "docs/upgrading-to-0.22.0.md").read_text(encoding="utf-8")
    historical_counts = {"core": 7, "full": 59}

    assert "Release 0.22.0" in release
    assert f"exactly {historical_counts['core']}" in release
    assert f"{historical_counts['full']} tools" in release
    assert "CODEX_USAGE_TRACKER_MCP_PROFILE=full" in upgrade
    assert "No dashboard navigation changed" in release
    assert len(CORE_MCP_TOOL_NAMES) == MCP_PROFILE_TOOL_COUNTS["core"]
    assert len(FULL_MCP_TOOL_NAMES) == historical_counts["full"] - 1
    assert "tracks 96 JSON schema identifiers" in release
    assert set(known_json_schemas()) >= RELEASE_022_SCHEMA_IDS
    assert all(f"`{schema}`" in release for schema in RELEASE_022_SCHEMA_IDS)


def test_023_release_docs_define_the_evidence_console_and_cli_transition() -> None:
    release = (REPO_ROOT / "docs/releases/0.23.0.md").read_text(encoding="utf-8")
    upgrade = (REPO_ROOT / "docs/upgrading-to-0.23.0.md").read_text(encoding="utf-8")
    routes = (REPO_ROOT / "docs/evidence-console-route-migration.md").read_text(encoding="utf-8")

    assert "Release 0.23.0" in release
    assert "Home, Explore, and Limits" in release
    assert "exactly 11" in release
    assert "codex-usage-tracker-dashboard-target-v2" in release
    assert "codex-usage-tracker open" in upgrade
    assert "through 0.25.x" in upgrade
    for legacy, replacement in (
        ("view=overview", "view=home"),
        ("view=calls", "view=explore&mode=calls"),
        ("view=threads", "view=explore&mode=threads"),
        ("view=call", "view=evidence&kind=call"),
    ):
        assert legacy in routes
        assert replacement in routes


def test_024_release_docs_define_the_hardening_and_compatibility_release() -> None:
    release = (REPO_ROOT / "docs/releases/0.24.0.md").read_text(encoding="utf-8")
    upgrade = (REPO_ROOT / "docs/upgrading-to-0.24.0.md").read_text(encoding="utf-8")
    audit = (REPO_ROOT / "docs/superpowers/reports/0.24-foundation-audit.md").read_text(
        encoding="utf-8"
    )
    manifest = json.loads(
        (REPO_ROOT / "docs/releases/0.24.0-artifact-manifest-example.json").read_text(
            encoding="utf-8"
        )
    )

    assert "Decision: **PROCEED**" in audit
    assert "Release 0.24.0" in release
    assert "schema version 37" in release
    assert "notice-only" in release
    assert "0.25.0" in release
    assert "0.26.0" in release
    assert "No manual database step is required" in upgrade
    assert manifest["schema"] == "codex-usage-tracker.release-artifact-manifest.v1"
    assert manifest["version"] == "0.24.0"
    assert manifest["contract_inventory"]["database_schema_version"] == 37
    assert len(manifest["contract_inventory"]["mcp_tools"]["core"]) == 7


def test_025_release_docs_define_reliability_and_static_sunset() -> None:
    release = (REPO_ROOT / "docs/releases/0.25.0.md").read_text(encoding="utf-8")
    upgrade = (REPO_ROOT / "docs/upgrading-to-0.25.0.md").read_text(encoding="utf-8")

    assert "Release 0.25.0" in release
    assert "usage.jobs.sqlite3" in release
    assert "0.005-second no-change refresh" in release
    assert "data-free `410`" in release
    assert "Reopening a browser tab" in upgrade
    assert "does not refresh or" in upgrade
    assert "tail_pending" in upgrade


def test_source_distribution_excludes_python_bytecode() -> None:
    manifest = (REPO_ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    assert "global-exclude __pycache__ *.py[cod]" in manifest


def test_data_posture_and_evidence_console_docs_define_the_stable_product() -> None:
    data_posture = (REPO_ROOT / "docs/data-posture.md").read_text(encoding="utf-8")
    evidence_console = (REPO_ROOT / "docs/evidence-console.md").read_text(encoding="utf-8")

    assert CANONICAL_DATA_POSTURE in data_posture
    for surface in ("Home", "Explore", "Limits", "Settings", "Evidence"):
        assert f"`{surface}`" in evidence_console
