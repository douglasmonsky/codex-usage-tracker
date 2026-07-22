from __future__ import annotations

from pathlib import Path


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
