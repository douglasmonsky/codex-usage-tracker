from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOCS = _REPO_ROOT / "docs"
_AUTHORITY_PATHS = (
    "docs/decisions/PRODUCT_DIRECTION.md",
    "docs/product/SUPPORTED_QUESTION_CONTRACTS.md",
    "docs/architecture/LOGICAL_KERNEL_CONTRACT.md",
    "docs/architecture/PHYSICAL_ARCHITECTURE_BAKEOFF.md",
    "docs/architecture/TARGET_ARCHITECTURE.md",
    "docs/architecture/ADAPTER_CONTRACT.md",
    "docs/architecture/PUBLICATION_REFRESH_RECOVERY.md",
    "docs/architecture/QUERY_EVIDENCE_PROJECTION_CONTRACTS.md",
    "docs/product/AGENT_SETUP_AND_MCP_EXPERIENCE.md",
    "docs/quality/QUALIFICATION_PLAN.md",
    "docs/roadmap/AGENT_FIRST_CLEAN_CUTOVER.md",
    "docs/roadmap/TASK_PACKETS.md",
    "docs/roadmap/LINEAR_BACKLOG.md",
)
_ARCHIVE_PATHS = (
    "docs/archive/SPIKE_DISPOSITION.md",
    "docs/archive/SPIKE_PERFORMANCE_EVIDENCE.md",
    "docs/archive/spike/KERNEL_STABLE_CONTRACT_0_28.md",
    "docs/archive/spike/ALLOWANCE_EFFICIENCY_FINDINGS.md",
    "docs/archive/spike/OVERLAY_ADAPTER_CONTRACT_0_28.md",
)


def _read(path: str) -> str:
    return (_REPO_ROOT / path).read_text(encoding="utf-8")


def _active_markdown() -> list[Path]:
    return [
        path
        for path in _DOCS.rglob("*.md")
        if "archive" not in path.relative_to(_DOCS).parts
    ]


def test_authority_set_exists_and_has_one_roadmap() -> None:
    assert (_DOCS / "INDEX.md").is_file()
    assert all((_REPO_ROOT / path).is_file() for path in _AUTHORITY_PATHS)

    roadmap_marker = "**Status:** Only authoritative implementation roadmap"
    marked = [
        path
        for path in _active_markdown()
        if roadmap_marker in path.read_text(encoding="utf-8")
    ]
    assert marked == [_DOCS / "roadmap" / "AGENT_FIRST_CLEAN_CUTOVER.md"]

    index = _read("docs/INDEX.md")
    assert all(path in index for path in _AUTHORITY_PATHS)


def test_master_ledger_links_exactly_one_file_per_packet() -> None:
    ledger_path = _DOCS / "roadmap" / "TASK_PACKETS.md"
    ledger = ledger_path.read_text(encoding="utf-8")
    packet_ids = re.findall(r"^- \[[ xX]\] \*\*(CK-\d{2})\b", ledger, re.MULTILINE)
    packet_links = re.findall(
        r"\[packet\]\((tasks/ck-\d{2}-[^)]+\.md)\)",
        ledger,
    )

    assert len(packet_ids) == 17
    assert set(packet_ids) == {f"CK-{number:02d}" for number in range(17)}
    assert len(packet_links) == 17
    assert len(set(packet_links)) == 17
    assert all((ledger_path.parent / link).is_file() for link in packet_links)

    task_files = sorted((_DOCS / "roadmap" / "tasks").glob("ck-*.md"))
    assert {path.name for path in task_files} == {
        Path(link).name for link in packet_links
    }
    for path in task_files:
        body = path.read_text(encoding="utf-8")
        assert "**Status:**" in body
        assert "[TASK_PACKETS.md](../TASK_PACKETS.md)" in body
        assert "[AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)" in body
        assert all(
            marker in body
            for marker in (
                "**Goal:**",
                "**Dependencies:**",
                "**Non-goals:**",
                "**Invariants:**",
                "**Acceptance:**",
                "**Failure/rollback:**",
                "**Cleanup/docs:**",
                "**Suggested commit",
            )
        )
        assert (
            "**Required tests/checks:**" in body
            or "**Tests/benchmarks:**" in body
        )


def test_question_catalog_and_diagram_inventory_are_complete() -> None:
    catalog = _read("docs/product/SUPPORTED_QUESTION_CONTRACTS.md")
    question_ids = re.findall(r"^#### (Q-[A-Z]+-\d{2}):", catalog, re.MULTILINE)
    assert len(question_ids) == 40
    assert len(set(question_ids)) == 40

    mermaid_blocks = sum(
        path.read_text(encoding="utf-8").count("```mermaid")
        for path in _active_markdown()
    )
    assert mermaid_blocks >= 16


def test_archives_are_marked_non_authoritative() -> None:
    for path in _ARCHIVE_PATHS:
        body = _read(path)
        opening = "\n".join(body.splitlines()[:8]).lower()
        assert "historical" in opening
        assert "non-authoritative" in opening or "does not authorize" in opening
        lowered = body.lower()
        assert "the authoritative record" not in lowered
        assert "controlling document" not in lowered


def test_frozen_spike_guidance_points_replacement_work_to_active_packets() -> None:
    guidance = _read("src/codex_usage_tracker/kernel/AGENTS.md")

    assert "frozen 0.28 implementation spike" in guidance
    assert "src/codex_usage_tracker/agent_kernel/" in guidance
    assert "Do not add product features" in guidance
    assert "Preserve the integration publication guard through K9" not in guidance
    assert "Update disposition state" not in guidance


def test_runtime_retirement_and_public_install_have_distinct_owners() -> None:
    roadmap = _read("docs/roadmap/AGENT_FIRST_CLEAN_CUTOVER.md")
    ck14 = _read(
        "docs/roadmap/tasks/ck-14-delete-spike-console-obsolete-surfaces.md"
    )
    ck16 = _read("docs/roadmap/tasks/ck-16-publish-docs-and-release.md")

    assert "## Runtime-retirement gate" in roadmap
    assert "exact locally built candidate" in roadmap
    assert "post-publication check" in roadmap
    assert "exact locally built candidate" in ck14
    assert "public-index" not in ck14
    assert "post-publication public-index download/install smoke" in ck16


def test_linear_issue_rows_use_only_declared_labels() -> None:
    backlog = _read("docs/roadmap/LINEAR_BACKLOG.md")
    labels_section, issues_section = backlog.split("## Issue backlog", maxsplit=1)
    issue_table, _ = issues_section.split("## Linear issue template", maxsplit=1)
    declared = set(
        re.findall(r"^\| `([^`]+)` \|", labels_section, re.MULTILINE)
    )
    used: set[str] = set()
    for line in issue_table.splitlines():
        if not line.startswith("| CK-"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        used.update(label.strip() for label in cells[5].split(","))

    assert declared
    assert used
    assert used <= declared


def test_obsolete_planning_framework_is_absent_from_active_authority() -> None:
    retired_root = "super" + "powers"
    assert not (_REPO_ROOT / f".{retired_root}").exists()
    assert not (_DOCS / retired_root).exists()

    active_paths = [
        _REPO_ROOT / "AGENTS.md",
        _REPO_ROOT / "AGENTS.agent-maintainer.md",
        _REPO_ROOT / "README.md",
        _REPO_ROOT / "CONTRIBUTING.md",
        _REPO_ROOT / "SECURITY.md",
        *_active_markdown(),
    ]
    assert all(
        retired_root not in path.read_text(encoding="utf-8").lower()
        for path in active_paths
    )

    resolved_pull_request_refs = ("#" + "314", "pull/" + "314")
    assert all(
        not any(
            marker in path.read_text(encoding="utf-8")
            for marker in resolved_pull_request_refs
        )
        for path in active_paths
    )
