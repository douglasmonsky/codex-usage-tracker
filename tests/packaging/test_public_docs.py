from __future__ import annotations

from pathlib import Path

from tests.release_catalog import CANONICAL_DATA_POSTURE, CANONICAL_PACKAGE_DESCRIPTION


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_mcp_first_roadmap_names_the_normative_release_sequence() -> None:
    roadmap = (REPO_ROOT / "docs/roadmap/mcp-first-pivot.md").read_text(encoding="utf-8")

    releases = ["0.22.0", "0.23.0", "0.24.0", "0.25.0", "0.26.0"]
    positions = [roadmap.index(release) for release in releases]

    assert positions == sorted(positions)


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
    title_paragraph = readme.split("# Codex Usage Tracker\n", maxsplit=1)[1].split("\n\n", maxsplit=1)[0]

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


def test_data_posture_and_evidence_console_docs_define_the_stable_product() -> None:
    data_posture = (REPO_ROOT / "docs/data-posture.md").read_text(encoding="utf-8")
    evidence_console = (REPO_ROOT / "docs/evidence-console.md").read_text(encoding="utf-8")

    assert CANONICAL_DATA_POSTURE in data_posture
    for surface in ("Home", "Explore", "Limits", "Settings", "Evidence"):
        assert f"`{surface}`" in evidence_console
