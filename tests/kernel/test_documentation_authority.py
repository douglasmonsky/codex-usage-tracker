from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOCS = _REPO_ROOT / "docs"
_AUTHORITY_PATHS = (
    "docs/decisions/PRODUCT_DIRECTION.md",
    "docs/product/SUPPORTED_QUESTION_CONTRACTS.md",
    "docs/architecture/LOGICAL_KERNEL_CONTRACT.md",
    "docs/architecture/FORMULA_AND_SELECTOR_CONTRACT.md",
    "docs/architecture/PHYSICAL_ARCHITECTURE_BAKEOFF.md",
    "docs/architecture/TARGET_ARCHITECTURE.md",
    "docs/architecture/ADAPTER_CONTRACT.md",
    "docs/architecture/PUBLICATION_REFRESH_RECOVERY.md",
    "docs/architecture/QUERY_EVIDENCE_PROJECTION_CONTRACTS.md",
    "docs/product/AGENT_SETUP_AND_MCP_EXPERIENCE.md",
    "docs/quality/QUALIFICATION_PLAN.md",
    "docs/roadmap/AGENT_FIRST_CLEAN_CUTOVER.md",
    "docs/roadmap/REMAINING_EXECUTION_PLAN.md",
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
_PACKET_IDS = {
    *(f"CK-{number:02d}" for number in range(17)),
    "CK-07A",
    "CK-07B",
    "CK-07C",
    "CK-07D",
    "CK-07E",
    "CK-07R1",
    "CK-08R0",
    "CK-08R1",
    "CK-08R2",
    "CK-08R3",
    "CK-08R4",
    "CK-08RG",
    "CK-QG1",
    *(f"CK-09-{number:02d}" for number in range(1, 7)),
    *(f"CK-10-{number:02d}" for number in range(1, 6)),
    *(f"CK-11-{number:02d}" for number in range(1, 5)),
    *(f"CK-12-{number:02d}" for number in range(1, 7)),
    *(f"CK-13-{number:02d}" for number in range(1, 4)),
    *(f"CK-14-{number:02d}" for number in range(1, 5)),
    *(f"CK-15-{number:02d}" for number in range(1, 3)),
    *(f"CK-16-{number:02d}" for number in range(1, 5)),
}

_DELEGATED_PACKET_IDS = _PACKET_IDS - {
    *(f"CK-{number:02d}" for number in range(17)),
    "CK-07A",
    "CK-07B",
    "CK-07C",
    "CK-07D",
    "CK-07E",
}
def _read(path: str) -> str:
    return (_REPO_ROOT / path).read_text(encoding="utf-8")


def _json(path: str):
    return json.loads(_read(path))


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
    packet_ids = re.findall(
        r"^- \[[ xX]\] \*\*(CK-[A-Z0-9]+(?:-[A-Z0-9]+)*)\b",
        ledger,
        re.MULTILINE,
    )
    packet_links = re.findall(
        r"\[packet\]\((tasks/ck-[a-z0-9-]+\.md)\)",
        ledger,
    )

    assert len(packet_ids) == len(_PACKET_IDS)
    assert set(packet_ids) == _PACKET_IDS
    assert len(packet_links) == len(_PACKET_IDS)
    assert len(set(packet_links)) == len(_PACKET_IDS)
    assert all((ledger_path.parent / link).is_file() for link in packet_links)
    ledger_by_id = dict(zip(packet_ids, packet_links, strict=True))

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
        heading = re.search(r"^# (CK-[A-Z0-9]+(?:-[A-Z0-9]+)*)\b", body)
        assert heading is not None
        assert ledger_by_id[heading.group(1)] == f"tasks/{path.name}"
        if heading.group(1) in _DELEGATED_PACKET_IDS:
            assert all(
                marker in body
                for marker in (
                    "[REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)",
                    "**Recommended owner:**",
                    "**Owned files/interfaces:**",
                    "**Produces:**",
                    "**Independent truth source:**",
                    "**Consumer seam:**",
                    "**Parallelism:**",
                    "**Handoff:**",
                )
            )
        assert (
            "**Required tests/checks:**" in body
            or "**Tests/benchmarks:**" in body
        )


def test_remaining_execution_plan_is_complete_acyclic_and_fail_closed() -> None:
    central = _read("docs/roadmap/REMAINING_EXECUTION_PLAN.md")
    ledger = _read("docs/roadmap/TASK_PACKETS.md")

    manifest_match = re.search(
        r"<!-- delegated-task-dag:start -->\s*```json\s*(.*?)\s*```"
        r"\s*<!-- delegated-task-dag:end -->",
        central,
        re.DOTALL,
    )
    assert manifest_match is not None
    manifest = json.loads(manifest_match.group(1))
    assert manifest["schema"] == "codex-usage-tracker.remaining-delegation-dag.v1"
    assert manifest["orchestration"]["spawn"] == "all_newly_ready_successors"
    conditional_ready = {
        "CK-08R1",
        "CK-08R3",
        "CK-07R1",
        "CK-QG1",
    }
    assert manifest["completed"] == ["CK-08R0", "CK-08R2"]
    assert manifest["ready"] == []
    assert manifest["conditional_ready"] == [{
        "condition": "CK-08R0 merged and exact-main verified",
        "tasks": ["CK-08R1", "CK-08R3", "CK-07R1", "CK-QG1"],
    }]

    tasks = manifest["tasks"]
    assert len(tasks) == 42
    manifest_by_id = {task["id"]: task for task in tasks}
    assert len(manifest_by_id) == 42
    assert set(manifest_by_id) == _DELEGATED_PACKET_IDS

    ledger_rows = re.findall(
        r"^- \[[ xX]\] \*\*(CK-[A-Z0-9]+(?:-[A-Z0-9]+)*)\b.*?"
        r"\[packet\]\((tasks/ck-[a-z0-9-]+\.md)\)",
        ledger,
        re.MULTILINE,
    )
    ledger_by_id = dict(ledger_rows)
    for packet_id, task in manifest_by_id.items():
        file_path = task["file"]
        assert ledger_by_id[packet_id] == file_path
        assert set(task) == {"id", "file", "dependencies"}
        assert len(task["dependencies"]) == len(set(task["dependencies"]))
        assert set(task["dependencies"]) <= _PACKET_IDS

        body = _read(f"docs/roadmap/{file_path}")
        assert re.search(rf"^# {re.escape(packet_id)}\b", body, re.MULTILINE)
        owner_match = re.search(
            r"^\*\*Recommended owner:\*\* `([a-z_]+) [^`]+`;",
            body,
            re.MULTILINE,
        )
        assert owner_match is not None
        assert owner_match.group(1) in {
            "default",
            "feature_worker",
            "refactorer",
            "test_engineer",
            "worker",
        }
        if packet_id in conditional_ready:
            assert "**Status:** Conditional Ready after CK-08R0 merge" in body
        elif packet_id in {"CK-08R0", "CK-08R2"}:
            assert "**Status:** Completed on merge" in body
        else:
            assert "**Status:** Blocked" in body

    path = "docs/decisions/evidence/ck08r0/corrective-gates-v1.json"
    contract = _json(path)
    contract_validator = Draft202012Validator(
        _json(f"{path.removesuffix('.json')}.schema.json")
    )
    contract_validator.validate(contract)
    r2_evidence = _json(
        "docs/decisions/evidence/ck08r2/physical-page-executor-evidence.json"
    )
    superseded = {
        item["path"]: item for item in r2_evidence["superseded_authority_artifacts"]
    }
    for artifact in contract["authority_artifacts"]:
        source = _REPO_ROOT / artifact["path"]
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        if replacement := superseded.get(artifact["path"]):
            assert replacement["from_sha256"] == artifact["sha256"]
            assert actual == replacement["to_sha256"]
        else:
            assert actual == artifact["sha256"]
    locks = [lock for lane in contract["lanes"] for lock in lane["owned_lock"]]
    assert len(locks) == len(set(locks))
    changed = json.loads(json.dumps(contract))
    changed["lanes"][1]["id"] = "CK-08R1"
    assert list(contract_validator.iter_errors(changed))

    evidence_bundle = _json(
        "docs/decisions/evidence/ck08r0/corrective-lane-evidence-v1.schema.json"
    )
    Draft202012Validator.check_schema(evidence_bundle)
    bound = {
        evidence_bundle["$defs"][lane["evidence_schema"]["definition"].removeprefix("#/$defs/")]
        ["properties"]["schema"]["const"]
        for lane in contract["lanes"]
    }
    assert bound == {lane["evidence_schema"]["schema"] for lane in contract["lanes"]}
    assert list(Draft202012Validator(evidence_bundle).iter_errors({"schema": next(iter(bound))}))

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(packet_id: str) -> None:
        assert packet_id not in visiting, f"delegation cycle at {packet_id}"
        if packet_id in visited:
            return
        visiting.add(packet_id)
        for dependency in manifest_by_id[packet_id]["dependencies"]:
            if dependency in manifest_by_id:
                visit(dependency)
        visiting.remove(packet_id)
        visited.add(packet_id)

    for packet_id in manifest_by_id:
        visit(packet_id)

    assert visited == _DELEGATED_PACKET_IDS
    assert "architect / Sol" not in central
    assert "feature worker / Sol" not in central
def test_corrective_seam_packet_is_critical_path_authority() -> None:
    agents = _read("AGENTS.md")
    index = _read("docs/INDEX.md")
    roadmap = _read("docs/roadmap/AGENT_FIRST_CLEAN_CUTOVER.md")
    ledger = _read("docs/roadmap/TASK_PACKETS.md")
    backlog = _read("docs/roadmap/LINEAR_BACKLOG.md")
    qualification = _read("docs/quality/QUALIFICATION_PLAN.md")
    query_contract = _read(
        "docs/architecture/QUERY_EVIDENCE_PROJECTION_CONTRACTS.md"
    )
    physical_decision = _read(
        "docs/decisions/PHYSICAL_ARCHITECTURE_DECISION.md"
    )
    ck07a = _read(
        "docs/roadmap/tasks/"
        "ck-07a-reconcile-fact-backed-oracles-and-qualify-seams.md"
    )
    ck07d = _read(
        "docs/roadmap/tasks/"
        "ck-07d-implement-effective-dated-rate-card-valuation.md"
    )
    ck07e = _read(
        "docs/roadmap/tasks/ck-07e-implement-independent-fact-adapters.md"
    )
    ck08 = _read("docs/roadmap/tasks/ck-08-implement-query-and-evidence.md")

    assert "## Cross-packet semantic continuity" in agents
    assert "producer artifact and exact identity" in agents
    assert "independent truth source or reference evaluator" in agents
    assert "CK-07A" in index
    assert (
        "CK-07 -> CK-07B -> CK-07C -> CK-07D -> CK-07E -> CK-07A -> CK-08"
        in roadmap
    )
    assert (
        "CK-07 → CK-07B\n→ CK-07C → CK-07D → CK-07E → CK-07A → CK-08"
        in ledger
    )
    assert "| CK-07D |" in backlog
    assert "| CK-07E |" in backlog
    assert "| CK-07A |" in backlog
    assert "### Evidence claim classes" in qualification
    assert "### Fact-backed plan admission" in query_contract
    assert (
        "**Dependencies:** CK-07, CK-07B, CK-07C, CK-07D, and CK-07E merged"
        in ck07a
    )
    assert "greatest eligible" in ck07d
    assert "fetched_at_us" in ck07d
    assert "late-ingested" in ck07d
    assert "StructuralReferenceFactAdapter" in ck07e
    assert "DatabaseV1FactAdapter" in ck07e
    assert "0 / 80" in ck07e
    assert "## Frozen seam contracts" in ck07a
    assert "## Frozen correction formats" in ck07a
    assert "agent-kernel-structural-v2" in ck07a
    assert all(
        evidence_path in ck07a
        for evidence_path in (
            "docs/decisions/evidence/ck04/aggregate-evidence.json",
            "docs/decisions/evidence/ck05/canonical-storage-evidence.json",
            "docs/decisions/evidence/ck06/codex-adapter-ingestion-evidence.json",
            "docs/decisions/evidence/ck07/publication-refresh-recovery-evidence.json",
        )
    )
    assert "all 80 variants" in ck07a
    assert "all 80 question variants" in ck07a
    assert "aggregate score/sensitivity evidence" in ck07a
    assert "80 / 80 fact-backed variants passed" in physical_decision
    assert "explicit growth-evidence exception" in physical_decision
    assert "two current repetitions were waived" in physical_decision
    assert "**Dependencies:** CK-07A merged with exact-main seam evidence." in ck08


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
