from __future__ import annotations

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


def test_mcp_first_roadmap_names_the_normative_release_sequence() -> None:
    roadmap = (REPO_ROOT / "docs/roadmap/mcp-first-pivot.md").read_text(encoding="utf-8")

    releases = ["0.22.0", "0.23.0", "0.24.0", "0.25.0", "0.26.0"]
    positions = [roadmap.index(release) for release in releases]

    assert positions == sorted(positions)


def test_mcp_first_roadmap_gates_024_on_foundation_audit() -> None:
    summary = (REPO_ROOT / "docs/roadmap/mcp-first-pivot.md").read_text(encoding="utf-8")
    execution = (REPO_ROOT / "docs/roadmap/mcp-first-pivot-execution.md").read_text(
        encoding="utf-8"
    )
    plan = (REPO_ROOT / "docs/superpowers/plans/2026-07-21-mcp-first-product-pivot.md").read_text(
        encoding="utf-8"
    )
    design = (
        REPO_ROOT / "docs/superpowers/specs/2026-07-21-mcp-first-product-pivot-design.md"
    ).read_text(encoding="utf-8")

    task_headings = [
        line.split(":", maxsplit=1)[0].removeprefix("### Task ")
        for line in plan.splitlines()
        if line.startswith("### Task ")
    ]
    expected_task_headings = [
        *(str(task_number) for task_number in range(1, 28)),
        "27.5",
        *(str(task_number) for task_number in range(28, 46)),
    ]

    assert task_headings == expected_task_headings
    assert "**Stable task ID:** `ARCH-AUDIT-00`" in plan
    assert "**Program size:** 46 tasks" in plan
    assert (
        "**Depends on:** Task 27.5 with a `PROCEED` decision or a\nmaintainer-approved `AMEND`"
    ) in plan

    assert "## Pre-0.24 Foundation Gate" in summary
    assert "No Task 28-39 implementation work may begin" in summary
    assert "## Task 27.5 - Foundation Audit and 0.24 Plan Confirmation" in execution
    assert "### 13.4 Pre-0.24 foundation audit" in design


def test_deprecation_ledger_has_required_compatibility_columns() -> None:
    deprecations = (REPO_ROOT / "docs/deprecations.md").read_text(encoding="utf-8")

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


def test_agent_branch_prefixes_allow_the_required_pivot_branches() -> None:
    guidance = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    allowed_prefixes = next(
        line for line in guidance.splitlines() if line.startswith("- Use branch prefixes ")
    )

    assert "`pivot/`" in allowed_prefixes


def test_architecture_declares_mcp_primary_and_evidence_console_supporting() -> None:
    architecture = (REPO_ROOT / "docs/architecture.md").read_text(encoding="utf-8")

    assert "MCP is the primary analysis interface" in architecture
    assert "Evidence Console is the supporting verification interface" in architecture


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

    assert "Release 0.22.0" in release
    assert f"exactly {MCP_PROFILE_TOOL_COUNTS['core']}" in release
    assert f"{MCP_PROFILE_TOOL_COUNTS['full']} tools" in release
    assert "CODEX_USAGE_TRACKER_MCP_PROFILE=full" in upgrade
    assert "No dashboard navigation changed" in release
    assert len(CORE_MCP_TOOL_NAMES) == MCP_PROFILE_TOOL_COUNTS["core"]
    assert len(FULL_MCP_TOOL_NAMES) == MCP_PROFILE_TOOL_COUNTS["full"]
    assert f"tracks {len(known_json_schemas())} JSON schema identifiers" in release
    assert set(known_json_schemas()) >= RELEASE_022_SCHEMA_IDS
    assert all(f"`{schema}`" in release for schema in RELEASE_022_SCHEMA_IDS)


def test_023_release_docs_define_the_evidence_console_and_cli_transition() -> None:
    release = (REPO_ROOT / "docs/releases/0.23.0.md").read_text(encoding="utf-8")
    upgrade = (REPO_ROOT / "docs/upgrading-to-0.23.0.md").read_text(encoding="utf-8")
    routes = (REPO_ROOT / "docs/evidence-console-route-migration.md").read_text(
        encoding="utf-8"
    )

    assert "Release 0.23.0" in release
    assert "Home, Explore, and Limits" in release
    assert "exactly 11" in release
    assert "codex-usage-tracker-dashboard-target-v2" in release
    assert "codex-usage-tracker open" in upgrade
    assert "through 0.24.x" in upgrade
    for legacy, replacement in (
        ("view=overview", "view=home"),
        ("view=calls", "view=explore&mode=calls"),
        ("view=threads", "view=explore&mode=threads"),
        ("view=call", "view=evidence&kind=call"),
    ):
        assert legacy in routes
        assert replacement in routes


def test_data_posture_and_evidence_console_docs_define_the_stable_product() -> None:
    data_posture = (REPO_ROOT / "docs/data-posture.md").read_text(encoding="utf-8")
    evidence_console = (REPO_ROOT / "docs/evidence-console.md").read_text(encoding="utf-8")

    assert CANONICAL_DATA_POSTURE in data_posture
    for surface in ("Home", "Explore", "Limits", "Settings", "Evidence"):
        assert f"`{surface}`" in evidence_console
