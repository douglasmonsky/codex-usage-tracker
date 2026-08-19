from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path

import pytest
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
    "CK-07R1A",
    "CK-07R1A0",
    "CK-08R0",
    "CK-08R1A",
    "CK-08R1B",
    "CK-08R1C",
    "CK-08R1",
    "CK-08R2",
    "CK-08R3A",
    "CK-08R3",
    "CK-08R4",
    "CK-08RG",
    "CK-QG1A0",
    "CK-QG1A",
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


def _portable_selected_support_hashes() -> dict[str, str]:
    authority = _json(
        "docs/decisions/evidence/ck08r3a/portable-plan-branch-ownership-authority.json"
    )
    return {
        item["path"]: item["sha256"] for item in authority["selected_cohort"]["support_identities"]
    }


def _ck08r1b_selected_hashes() -> dict[str, str]:
    authority = _json("docs/decisions/evidence/ck08r1b/answer-semantics-join-authority.json")
    return {
        item["path"]: item["sha256"] for item in authority["selected_successor_cohort"]["files"]
    }


def _active_markdown() -> list[Path]:
    return [path for path in _DOCS.rglob("*.md") if "archive" not in path.relative_to(_DOCS).parts]


def test_authority_set_exists_and_has_one_roadmap() -> None:
    assert (_DOCS / "INDEX.md").is_file()
    assert all((_REPO_ROOT / path).is_file() for path in _AUTHORITY_PATHS)

    roadmap_marker = "**Status:** Only authoritative implementation roadmap"
    marked = [
        path for path in _active_markdown() if roadmap_marker in path.read_text(encoding="utf-8")
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
    assert {path.name for path in task_files} == {Path(link).name for link in packet_links}
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
        assert "**Required tests/checks:**" in body or "**Tests/benchmarks:**" in body


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
    assert manifest["orchestration"] == {
        "mode": "self-propagating-convergence",
        "spawn": "newly_ready_distinct_packets_only",
        "join": "all_dependencies_complete",
        "duplicate_policy": "one_active_task_per_packet_and_dependency_frontier",
        "continuation_policy": "reuse_existing_task_for_same_packet",
        "authority_policy": "new_task_only_for_new_policy_or_contract_decision",
        "handoff_policy": "proactive_parent_handoff_from_repository_verified_state",
        "identity_policy": "worker_ownership_is_normative_coordinator_thread_binding_plus_exact_repository_evidence_not_runtime_authentication",
        "one_shot_policy": "real_non_consuming_preflight_before_authorized_attempt",
        "recovery_exit_policy": "return_to_convergence_after_integrity_restored",
        "blocked_policy": "spawn_none_and_report_to_orchestrator",
    }
    conditional_ready = {"CK-07R1"}
    blocked: set[str] = set()
    assert manifest["completed"] == [
        "CK-08R0",
        "CK-08R1A",
        "CK-08R1B",
        "CK-08R1C",
        "CK-08R1",
        "CK-08R2",
        "CK-08R3A",
        "CK-08R3",
        "CK-QG1A0",
        "CK-QG1A",
        "CK-QG1",
        "CK-07R1A",
        "CK-07R1A0",
    ]
    qg1a_authority = _json(
        "docs/decisions/evidence/ckqg1a0/page-executor-source-supersession-authority.json"
    )
    qg1a_source = _REPO_ROOT / qg1a_authority["source_path"]
    assert (
        hashlib.sha256(qg1a_source.read_bytes()).hexdigest()
        == (qg1a_authority["selected_successor"]["sha256"])
    )
    ready: set[str] = set()
    assert manifest["ready"] == []
    assert manifest["conditional_ready"] == [
        {
            "condition": (
                "prelaunch-recovery authority preserves the exact terminal v1 ledger, binds "
                "the corrected cohort and non-colliding v2 paths, merges and exact-main "
                "verifies; coordinator resumes exact existing worker "
                "019fbfe2-8fe4-7de2-9264-d58572366727; one corrected synthetic invocation "
                "may seek the first successful child launch under immediate preflight; no "
                "retry of a launched process, replacement, or downstream task"
            ),
            "tasks": ["CK-07R1"],
        },
    ]
    assert manifest["blocked"] == []
    parent_section = ledger.split("## Parent packets", 1)[1].split(
        "## Remaining delegated child tasks", 1
    )[0]
    parent_rows = [
        line for line in parent_section.splitlines() if line.startswith("- [") and "**CK-" in line
    ]
    parent_completed = sum(line.startswith("- [x]") for line in parent_rows)
    assert len(parent_rows) == 22
    assert parent_completed == 14
    assert f"Completed packets: **{parent_completed} / {len(parent_rows)}**" in ledger
    assert f"Not started: **{len(parent_rows) - parent_completed}**" in ledger
    assert f"Critical-path completion: **{parent_completed} / 21**" in ledger
    assert "Completed corrective child tasks: **13" in ledger
    remaining_delegable = len(manifest["tasks"]) - len(manifest["completed"])
    assert remaining_delegable == 37
    assert f"Remaining delegable child tasks: **{remaining_delegable}**" in ledger
    assert "Blocked child tasks: **36" in ledger
    assert f"Ready child tasks: **{len(manifest['ready'])}" in ledger
    assert (
        f"Conditional-ready child tasks: **{sum(len(item['tasks']) for item in manifest['conditional_ready'])}"
        in ledger
    )
    active_status_docs = "\n".join(
        [
            (_REPO_ROOT / "AGENTS.md").read_text(),
            (_DOCS / "INDEX.md").read_text(),
            (_DOCS / "architecture/QUERY_EVIDENCE_PROJECTION_CONTRACTS.md").read_text(),
            (_DOCS / "quality/QUALIFICATION_PLAN.md").read_text(),
            (_DOCS / "roadmap/AGENT_FIRST_CLEAN_CUTOVER.md").read_text(),
            central,
            ledger,
        ]
    )
    for stale_claim in (
        "R1B remains held",
        "R1B is Ready only",
        "R1B worker Ready",
        "R1 remains their blocked",
        "final R1 requalification is the sole Ready packet",
        "final R1 is now the sole Ready replay",
        "remain acceptance handoff requirements",
        "existing QG1 PR #392 is Ready to resume",
    ):
        assert stale_claim not in active_status_docs
    assert "PR #439" in central
    assert "0832b85411e68feb9cf1a7300ab14e4cc97d391a" in central

    tasks = manifest["tasks"]
    assert len(tasks) == 50
    manifest_by_id = {task["id"]: task for task in tasks}
    assert len(manifest_by_id) == 50
    assert set(manifest_by_id) == _DELEGATED_PACKET_IDS
    assert manifest_by_id["CK-08R3A"]["dependencies"] == ["CK-08R0"]
    assert manifest_by_id["CK-08R3"]["dependencies"] == ["CK-08R3A"]
    assert manifest_by_id["CK-08R1A"]["dependencies"] == ["CK-08R0"]
    assert manifest_by_id["CK-08R1B"]["dependencies"] == ["CK-08R1A"]
    assert manifest_by_id["CK-08R1C"]["dependencies"] == ["CK-08R1A"]
    assert manifest_by_id["CK-08R1"]["dependencies"] == ["CK-08R1B", "CK-08R1C"]
    assert manifest_by_id["CK-QG1A0"]["dependencies"] == ["CK-08R2"]
    assert manifest_by_id["CK-QG1A"]["dependencies"] == ["CK-QG1A0"]
    assert manifest_by_id["CK-QG1"]["dependencies"] == ["CK-QG1A"]
    assert manifest_by_id["CK-07R1A"]["dependencies"] == ["CK-08R0"]
    assert manifest_by_id["CK-07R1A0"]["dependencies"] == ["CK-QG1A0", "CK-07R1A"]
    assert manifest_by_id["CK-07R1"]["dependencies"] == ["CK-07R1A0"]
    assert manifest_by_id["CK-08R4"]["dependencies"] == [
        "CK-08R1",
        "CK-08R2",
        "CK-08R3",
        "CK-07R1",
    ]
    assert manifest_by_id["CK-08RG"]["dependencies"] == ["CK-08R4", "CK-QG1"]

    release_budget = _json("config/kernel-release-candidate-budget.json")
    package_policy = _json(
        "docs/decisions/evidence/kernel-release-candidate-package-budget-supersession.json"
    )
    assert release_budget["wheel_bytes"] == 1_000_000
    assert release_budget["sdist_bytes"] == 2_000_000
    assert release_budget["policy_artifact"] == (
        "docs/decisions/evidence/kernel-release-candidate-package-budget-supersession.json"
    )
    assert package_policy["status"] == "maintainer-approved"
    assert (
        "Package-size micro-optimization is no longer a roadmap objective"
        in package_policy["rationale"]
    )
    for packet_id in (
        "CK-08R1A",
        "CK-08R1B",
        "CK-08R1C",
        "CK-08R3A",
        "CK-07R1A",
        "CK-07R1A0",
        "CK-QG1A0",
        "CK-QG1A",
    ):
        packet = _read(f"docs/roadmap/{manifest_by_id[packet_id]['file']}").replace(",", "")
        assert str(release_budget["sdist_bytes"]) in packet
        if packet_id == "CK-07R1A0":
            assert str(release_budget["wheel_bytes"]) in packet

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
            if packet_id == "CK-07R1":
                assert "**Status:** `blocked_hold`" in body
            else:
                assert "**Status:** Conditional Ready after" in body
        elif packet_id in ready:
            assert "**Status:** Ready" in body
        elif packet_id in blocked:
            assert "**Status:** Blocked" in body
        elif packet_id in {
            "CK-08R0",
            "CK-08R1A",
            "CK-08R1B",
            "CK-08R1C",
            "CK-08R1",
            "CK-08R2",
            "CK-08R3A",
            "CK-08R3",
            "CK-QG1A0",
            "CK-QG1A",
            "CK-QG1",
            "CK-07R1A",
            "CK-07R1A0",
        }:
            assert "**Status:** Completed on merge" in body
        else:
            assert "**Status:** Blocked" in body

    path = "docs/decisions/evidence/ck08r0/corrective-gates-v1.json"
    contract = _json(path)
    contract_validator = Draft202012Validator(_json(f"{path.removesuffix('.json')}.schema.json"))
    contract_validator.validate(contract)
    r2_evidence = _json("docs/decisions/evidence/ck08r2/physical-page-executor-evidence.json")
    superseded = {item["path"]: item for item in r2_evidence["superseded_authority_artifacts"]}
    r3a = _json("docs/decisions/evidence/ck08r3a/evidence-service-supersession-authority.json")
    assert r3a["owner"] == "CK-08R3A"
    assert r3a["source_path"] == "src/codex_usage_tracker/agent_kernel/evidence/service.py"
    assert r3a["authority_base_sha"] == "7d5a4b1717db78891fd2c38d8803d7fe2f922986"
    assert r3a["base_transition"] == {
        "original_authority_base_sha": "ee4a064bf8850bceb362fbe73e40a57fe4af55d6",
        "integrated_origin_main_sha": "7d5a4b1717db78891fd2c38d8803d7fe2f922986",
        "upstream_change": "lifecycle session boundedness requalification from exact main",
    }
    assert r3a["selected_successor"]["status"] == "permitted_not_accepted"
    assert r3a["selected_successor"]["required_artifacts"] == [
        {
            "path": "src/codex_usage_tracker/agent_kernel/evidence/service.py",
            "role": "source",
            "sha256": r3a["selected_successor"]["sha256"],
        },
        {
            "path": "src/codex_usage_tracker/agent_kernel/storage/analytical.sql",
            "role": "evidence_order_indexes",
            "sha256": "34b6aab813dbd520f1894ac3ccbce1a1b3ff4552a11f0a83597a897a0c8f7486",
        },
        {
            "path": "src/codex_usage_tracker/agent_kernel/storage/schema.py",
            "role": "schema_contract_digest",
            "sha256": "9850a431729c7eb8d5347278d0434f0849d1843297645547ee2dcd66a0359b77",
        },
    ]
    assert r3a["schema_publication_transition_authority"] == {
        "path": "docs/decisions/evidence/ck08r3a/schema-publication-requalification-authority.json",
        "status": "permitted_not_accepted",
        "authority_base_sha": "7d5a4b1717db78891fd2c38d8803d7fe2f922986",
        "scope": "exact current session-leading lifecycle DDL/schema identities, linked synthetic publication fixtures, and tiny-accounting EXPLAIN transition",
    }
    assert len(r3a["rejected_successors"]) == 2
    assert r3a["rejected_successors"][0]["sha256"] == (
        "718ff7032d050b13cb7fac1f857d0c99879d0ef3b13c57c39b55514fc610a88b"
    )
    assert r3a["rejected_successors"][0]["status"] == "rejected_non_acceptable"
    assert "generic_digest_drift_forbidden" in r3a["constraints"]
    for artifact in contract["authority_artifacts"]:
        source = _REPO_ROOT / artifact["path"]
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        if replacement := superseded.get(artifact["path"]):
            assert replacement["from_sha256"] == artifact["sha256"]
            assert actual == replacement["to_sha256"]
        elif artifact["path"] == r3a["source_path"]:
            assert r3a["predecessor"]["sha256"] == artifact["sha256"]
            successor = r3a["selected_successor"]
            assert actual in {artifact["sha256"], successor["sha256"]}
            if actual == successor["sha256"]:
                for required in successor["required_artifacts"]:
                    required_path = _REPO_ROOT / required["path"]
                    assert (
                        hashlib.sha256(required_path.read_bytes()).hexdigest() == required["sha256"]
                    )
            else:
                assert actual == artifact["sha256"]
        elif artifact["path"] == "tests/agent_kernel/fixtures/tiny-v2/question-scenarios.json":
            transition = _json(r3a["schema_publication_transition_authority"]["path"])
            assert actual in {
                artifact["sha256"],
                transition["publication_fixture_transition"]["selected"]["question_scenarios"][
                    "sha256"
                ],
                _ck08r1b_selected_hashes()[artifact["path"]],
            }
        elif artifact["path"] == "src/codex_usage_tracker/agent_kernel/publication/preparation.py":
            final = _json("docs/decisions/evidence/ck08r3a/final-shared-authority.json")
            r3a_selected = final["ck07_shared_preparation"]["r3a_atomic_cohort"]["sha256"]
            source_authority = _json(
                "docs/decisions/evidence/ck07r1a0/lifecycle-source-digest-authority.json"
            )
            ck07_selected = source_authority["selected_successor"]
            assert actual in {
                artifact["sha256"],
                r3a_selected,
                source_authority["predecessor"]["sha256"],
                ck07_selected["sha256"],
            }
            if actual == r3a_selected:
                for required in (
                    final["r3a"]["selected"]["production_identities"]
                    + final["r3a"]["selected"]["support_identities"]
                ):
                    required_path = _REPO_ROOT / required["path"]
                    expected = {required["sha256"]}
                    if required["path"] == "tests/agent_kernel/evidence/test_service.py":
                        expected = {_portable_selected_support_hashes()[required["path"]]}
                    elif required["path"] == "tests/agent_kernel/fact_adapters/support.py":
                        expected.add(_ck08r1b_selected_hashes()[required["path"]])
                    assert hashlib.sha256(required_path.read_bytes()).hexdigest() in expected
            elif actual == ck07_selected["sha256"]:
                for required in ck07_selected["artifacts"]:
                    required_path = _REPO_ROOT / required["path"]
                    assert required_path.is_file()
                    assert (
                        hashlib.sha256(required_path.read_bytes()).hexdigest() == required["sha256"]
                    )
        elif artifact["path"] in {
            "config/agent-kernel/formula-contract-v1.json",
            "config/agent-kernel/plan-operand-contract-v1.json",
        }:
            assert actual in {
                artifact["sha256"],
                _ck08r1b_selected_hashes()[artifact["path"]],
            }
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
        evidence_bundle["$defs"][lane["evidence_schema"]["definition"].removeprefix("#/$defs/")][
            "properties"
        ]["schema"]["const"]
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


def _assert_ck08r3a_identity_binding(authority: dict) -> None:
    selected = authority["selected_successor"]
    artifacts = selected["required_artifacts"]
    assert authority["source_path"] == artifacts[0]["path"]
    assert selected["sha256"] == artifacts[0]["sha256"]
    assert artifacts[1]["path"] == "src/codex_usage_tracker/agent_kernel/storage/analytical.sql"
    assert artifacts[1]["role"] == "evidence_order_indexes"
    assert artifacts[1]["sha256"] == (
        "34b6aab813dbd520f1894ac3ccbce1a1b3ff4552a11f0a83597a897a0c8f7486"
    )
    assert artifacts[2]["path"] == "src/codex_usage_tracker/agent_kernel/storage/schema.py"
    assert artifacts[2]["role"] == "schema_contract_digest"
    assert artifacts[2]["sha256"] == (
        "9850a431729c7eb8d5347278d0434f0849d1843297645547ee2dcd66a0359b77"
    )
    assert authority["predecessor"]["sha256"] != selected["sha256"]
    assert authority["rejected_successors"][0]["sha256"] != selected["sha256"]
    assert authority["rejected_successors"][0]["status"] == "rejected_non_acceptable"
    assert "generic_digest_drift_forbidden" in authority["constraints"]


def test_ck08r3a_authority_rejects_identity_mutations() -> None:
    authority = _json(
        "docs/decisions/evidence/ck08r3a/evidence-service-supersession-authority.json"
    )
    _assert_ck08r3a_identity_binding(authority)

    for mutate in (
        lambda value: value["selected_successor"].__setitem__("sha256", "0" * 64),
        lambda value: value["selected_successor"]["required_artifacts"][1].__setitem__(
            "sha256", "0" * 64
        ),
        lambda value: value["rejected_successors"][0].__setitem__(
            "status", "permitted_not_accepted"
        ),
    ):
        mutated = deepcopy(authority)
        mutate(mutated)
        with pytest.raises(AssertionError):
            _assert_ck08r3a_identity_binding(mutated)


def test_ck08r3a_schema_publication_authority_is_exact_and_fixture_bound() -> None:
    authority_path = (
        "docs/decisions/evidence/ck08r3a/schema-publication-requalification-authority.json"
    )
    schema_path = authority_path.removesuffix(".json") + ".schema.json"
    authority = _json(authority_path)
    schema = _json(schema_path)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(authority)

    assert authority["schema"] == (
        "codex-usage-tracker.ck08r3a-schema-publication-requalification-authority.v3"
    )
    assert authority["authority_version"] == 3
    assert authority["authority_base_sha"] == ("7d5a4b1717db78891fd2c38d8803d7fe2f922986")
    assert authority["status"] == "permitted_not_accepted"
    assert authority["selected_production_identities"] == [
        {
            "path": "src/codex_usage_tracker/agent_kernel/evidence/service.py",
            "role": "selected EvidenceService source",
            "sha256": "4458ffb03adeed838fcda992747dbaeb192ccf59728b3a54e1527abc4d0651fb",
        },
        {
            "path": "src/codex_usage_tracker/agent_kernel/storage/analytical.sql",
            "role": "selected evidence-order DDL",
            "sha256": "34b6aab813dbd520f1894ac3ccbce1a1b3ff4552a11f0a83597a897a0c8f7486",
        },
        {
            "path": "src/codex_usage_tracker/agent_kernel/storage/schema.py",
            "role": "selected schema-contract digest binding",
            "sha256": "9850a431729c7eb8d5347278d0434f0849d1843297645547ee2dcd66a0359b77",
        },
    ]

    transition = authority["schema_contract_transition"]
    assert transition["selected"] == {
        "schema_contract_sha256": "998343ba4b52bb39decfcb436f8a862d41884fc6f6a6b4e88f7e8f8e42446295",
        "analytical_table_count": 42,
        "analytical_index_count": 57,
        "operational_table_count": 6,
        "operational_index_count": 6,
    }
    assert transition["selected_index_names"][8] == ("evidence_lifecycle_by_session_order")
    assert len(transition["selected_index_names"]) == 13

    fixture = authority["publication_fixture_transition"]
    assert fixture["selected"]["schema_contract_sha256"] == (
        "998343ba4b52bb39decfcb436f8a862d41884fc6f6a6b4e88f7e8f8e42446295"
    )
    assert fixture["selected"]["manifest"]["sha256"] == (
        "fb40a8a91d6ad537171e7a23e3f6fa9bd519080b513981b9483f9791e5e99e7d"
    )
    assert fixture["selected"]["question_scenarios"]["sha256"] == (
        "6ffca4917386c5bc13237952904d2a560a531e37c6eeba89b69ea53d76f35cd8"
    )
    assert len(authority["selected_artifact_manifest_sha256s"]) == 80
    assert (
        hashlib.sha256(
            (
                "".join(item + "\n" for item in authority["selected_artifact_manifest_sha256s"])
            ).encode()
        ).hexdigest()
        == "b825e940247a7ea15f34fd71d7aa7774c1acfff3b810676515e66d1f93dffb06"
    )
    assert authority["selected_published_v2"] == {
        "path": "tests/agent_kernel/fixtures/published_v2.py",
        "sha256": "eca815c5a47067bdc56759018e12fd7a25f446eb6d716236869cbef875ce8515",
    }
    assert authority["tiny_accounting_explain_transition"]["generic_explain_relaxation"] is False
    assert authority["preflight"] == {
        "worktree_role": "fresh exact-main integration worktree",
        "base_sha": "7d5a4b1717db78891fd2c38d8803d7fe2f922986",
        "reapplied_production_paths": authority["selected_production_identities"],
        "before_authority": {"just_v_failures": 2, "just_v_passed": 1401, "warnings": 1},
        "required_boundaries": [
            "schema-contract inventory and digest",
            "independent DDL execution and equality",
            "publication fixture and fact-backed 80-case replay",
            "selector/query/service compatibility",
            "tiny-accounting EXPLAIN index identity",
            "session-scoped lifecycle pages with 0/1000/5000 foreign rows",
        ],
        "authority_bytes_byte_identical": True,
        "status": "passed",
    }
    assert authority["no_live_operation"] is True


def test_corrective_seam_packet_is_critical_path_authority() -> None:
    agents = _read("AGENTS.md")
    index = _read("docs/INDEX.md")
    roadmap = _read("docs/roadmap/AGENT_FIRST_CLEAN_CUTOVER.md")
    central = _read("docs/roadmap/REMAINING_EXECUTION_PLAN.md")
    ledger = _read("docs/roadmap/TASK_PACKETS.md")
    backlog = _read("docs/roadmap/LINEAR_BACKLOG.md")
    qualification = _read("docs/quality/QUALIFICATION_PLAN.md")
    query_contract = _read("docs/architecture/QUERY_EVIDENCE_PROJECTION_CONTRACTS.md")
    physical_decision = _read("docs/decisions/PHYSICAL_ARCHITECTURE_DECISION.md")
    ck07a = _read("docs/roadmap/tasks/ck-07a-reconcile-fact-backed-oracles-and-qualify-seams.md")
    ck07d = _read("docs/roadmap/tasks/ck-07d-implement-effective-dated-rate-card-valuation.md")
    ck07e = _read("docs/roadmap/tasks/ck-07e-implement-independent-fact-adapters.md")
    ck08 = _read("docs/roadmap/tasks/ck-08-implement-query-and-evidence.md")
    ck08r3a = _read("docs/roadmap/tasks/ck-08r3a-implement-evidence-physical-query.md")
    ck08r3a_digest = _read(
        "docs/decisions/evidence/ck08r3a/evidence-service-supersession-authority.json"
    )
    ck08r3a_final = _read("docs/decisions/evidence/ck08r3a/final-shared-authority.json")
    ck08r3 = _read("docs/roadmap/tasks/ck-08r3-qualify-evidence-scale.md")
    ck08r1a = _read("docs/roadmap/tasks/ck-08r1a-freeze-answer-semantics.md")
    ck08r1b = _read("docs/roadmap/tasks/ck-08r1b-implement-production-answer-semantics.md")
    ck08r1c = _read("docs/roadmap/tasks/ck-08r1c-build-independent-semantic-evaluator.md")
    ck08r1 = _read("docs/roadmap/tasks/ck-08r1-build-independent-answer-truth.md")
    ckqg1a = _read("docs/roadmap/tasks/ck-qg1a-correct-page-executor-complexity.md")
    ckqg1a0 = _read("docs/roadmap/tasks/ck-qg1a0-authorize-page-executor-source-supersession.md")
    ckqg1 = _read("docs/roadmap/tasks/ck-qg1-enforce-agent-kernel-maintainability.md")
    ckqg1_authority = _read(
        "docs/decisions/evidence/ckqg1/maintainability-baseline-transition-authority.json"
    )
    ck07r1a = _read("docs/roadmap/tasks/ck-07r1a-correct-hosted-lifecycle-tail.md")
    ck07r1a0 = _read("docs/roadmap/tasks/ck-07r1a0-freeze-lifecycle-path-authority.md")
    ck07r1 = _read("docs/roadmap/tasks/ck-07r1-correct-lifecycle-preparation-scale.md")

    assert "## Cross-packet semantic continuity" in agents
    assert "producer artifact and exact identity" in agents
    assert "independent truth source or reference evaluator" in agents
    assert "CK-07A" in index
    assert "CK-07 -> CK-07B -> CK-07C -> CK-07D -> CK-07E -> CK-07A -> CK-08" in roadmap
    assert "CK-07 → CK-07B\n→ CK-07C → CK-07D → CK-07E → CK-07A → CK-08" in ledger
    assert "| CK-07D |" in backlog
    assert "| CK-07E |" in backlog
    assert "| CK-07A |" in backlog
    assert "### Evidence claim classes" in qualification
    assert "### Fact-backed plan admission" in query_contract
    for active_authority in (qualification, query_contract):
        assert "CK-QG1 PR #392 then passed" in active_authority
        assert "QG1 PR #392 is Ready" not in active_authority
        assert "QG1 PR #392 Ready" not in active_authority
    assert "**Dependencies:** CK-07, CK-07B, CK-07C, CK-07D, and CK-07E merged" in ck07a
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
    assert all(
        token in ck08r3a + ck08r3a_digest + ck08r3a_final
        for token in (
            "ea32223d1afd997f310419bff0b6b260193e527c8333c9f561bcab280447dfa3",
            "659c1957157bc36aecbc37824ef04479853ec7ae1ff6ddad5be5882d7ca844b3",
            "4458ffb03adeed838fcda992747dbaeb192ccf59728b3a54e1527abc4d0651fb",
            "718ff7032d050b13cb7fac1f857d0c99879d0ef3b13c57c39b55514fc610a88b",
            "998343ba4b52bb39decfcb436f8a862d41884fc6f6a6b4e88f7e8f8e42446295",
            "zero_based_nonnegative",
            "permitted_not_accepted",
            "generic_digest_drift_forbidden",
            "2,000,000",
        )
    )
    assert "CK-QG1A0" in ckqg1a0
    assert "explicit growth-evidence exception" in physical_decision
    assert "two current repetitions were waived" in physical_decision
    assert "**Dependencies:** CK-07A merged with exact-main seam evidence." in ck08
    assert "a28e9cdbff8e48d334712a449fdcee111c725673" in ck08r3a
    assert "ae9107eda155a21b9bd9ef5a77971007d00864b772c3a23bc521652b5b17d471" in ck08r3a
    assert all(
        plan_shape in ck08r3a
        for plan_shape in (
            "SCAN stream",
            "MATERIALIZE model_calls_visible",
            "AUTOMATIC COVERING INDEX",
            "USE TEMP B-TREE FOR ORDER BY",
        )
    )
    assert "**Dependencies:** CK-08R3A accepted, merged, and exact-main verified." in ck08r3
    for body, tokens in (
        (
            ck08r1a,
            (
                "tool_metrics",
                "state_change_metrics",
                "resource_metrics",
                "completion_state",
                "context_features",
                "delegation_metrics",
                "token_deltas",
                "turn_call_counts",
                "Open sessions remain explicitly open",
                "strict descendants",
                "terminal succeeded transition",
                "canonical call between one tool's start",
                "strictly",
                "reasoning",
                "sentinels",
                "inaccessible",
                "canonical closure digest",
            ),
        ),
        (ck08r1b, ("compile_plan_operands", "19 fail-closed residual plans")),
        (ck08r1c, ("Recursive closure", "production mutation cannot affect")),
        (ck08r1, ("sentinel-mutated",)),
        (
            ckqg1a,
            (
                "PageExecutionRequest",
                "23/count 1",
                "22/count 1",
                "c490d954a5e9d09c61f884d51e3b9d3196af5615887f409c36f8469d1b2b6cf9",
                "019fbb41-79b6-7760-8e7f-e68fc381422a",
            ),
        ),
        (
            ckqg1 + ckqg1_authority,
            (
                "Baseline transition authority",
                "PublicationWriter._validate_turn_provenance",
                "score 35/count 1",
                "fda777e28db7a0696f29b55c9d694f99d987413b206d8e323f217b4fa6a73ad5",
                "authorize_exact_writer_transition_only",
                "cross_packet_writer_transition",
                "exact_writer_successor_without_baseline_change",
                "d163e6c566665a65062952be1618b9f2c4032eabd841408e2f274bcd29748a73",
                "925270e6ad13074ddec756e0cd89165c29d9b144",
                "not_generic_baseline_growth",
                "implementation_acceptance",
                "new_authority_task",
            ),
        ),
        (
            ck07r1a,
            (
                "ordinary.2000_call_tail",
                "5000/120000/100/500/500",
                "30685780055",
                "019fbb41-804b-7fe2-8987-3d2b9e94a4d5",
            ),
        ),
        (
            ck07r1a0,
            (
                "plan_refresh",
                "PublicationWriter.publish_with_pointer",
                "fold_lifecycle",
                "935e4427b93e67c5ca649b773b0b3895dafac87f49bc76d7ed8917dff2f0250d",
                "one-run authorization condition",
                "blocked_hold",
                "e204e0da",
                "d192c858",
                "run-invocation authority",
                "The planner-valid receipt is a future successor acceptance",
                "stale failed PR #394 is explicitly superseded read-only",
            ),
        ),
    ):
        assert all(token in body for token in tokens)
    assert "exact-main verified at `519b503aa3b23019033b6481687c08b23fc6c31e`" in ck07r1a0
    assert "strict Authority v2" in ck07r1a0
    assert "supersedes earlier CK-07R1 wording" in central
    assert (
        "**Status:** Completed on merge — PR #392 hosted-green, squash-merged at\n"
        "`68050b93`, and exact-main verified"
    ) in ckqg1
    assert "**Status:** `blocked_hold`" in ck07r1
    assert "720-second wrapper timeout" in ck07r1a0
    assert "revoked, never authoritative, and never used" in ck07r1a0


def test_ck07r1a0_authority_is_strict_and_preserves_attempt_identity() -> None:
    authority_path = "docs/decisions/evidence/ck07r1a0/lifecycle-path-authority.json"
    schema = _json("docs/decisions/evidence/ck07r1a0/lifecycle-path-authority.schema.json")
    authority = _json(authority_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(authority)

    assert authority["owner"] == "CK-07R1A0"
    assert authority["schema"] == "codex-usage-tracker.lifecycle-path-authority.v2"
    assert authority["authority_version"] == 2
    assert authority["authority_base_sha"] == "979f88eca2f23f6225c0c7a530b8f36f793c5748"
    assert authority["blocked_requalification"] == {
        "packet": "CK-07R1",
        "status": "CONDITIONAL_READY",
        "reason": "planner_valid_lifecycle_receipt_is_successor_acceptance_output",
        "accepted_receipt_required": True,
        "receipt_required_before_dispatch": False,
    }
    assert authority["readiness_transition"] == {
        "packet": "CK-07R1",
        "from_status": "BLOCKED",
        "conditional_status": "CONDITIONAL_READY",
        "effective_ready_status": "READY",
        "activation": "this authority accepted merged and exact-main verified",
        "authority_base_sha": "519b503aa3b23019033b6481687c08b23fc6c31e",
        "receipt_role": "successor_acceptance_output_not_pre_dispatch_dependency",
        "receipt_required_before_dispatch": False,
        "receipt_required_for_acceptance": True,
        "maximum_new_end_to_end_runs": 1,
        "dispatch_rule": "create_exactly_one_fresh_CK-07R1_successor_from_activation_exact_main",
        "downstream_ready_tasks": [],
    }
    assert authority["pr_394_policy"] == {
        "number": 394,
        "head_sha": "98a9b5b82951d136644a5fe5f8a70d320131ba08",
        "base_sha": "bbd9eb990969a659376ea584c6d696d1715cc007",
        "workflow_run_id": "30685780055",
        "failed_job_id": "91331138768",
        "failed_check": "Kernel phase and package isolation (3.14)",
        "failure": "ordinary.2000_call_tail",
        "status": "stale_failed_superseded_read_only",
        "policy": "do_not_update_rerun_merge_or_reinterpret",
        "future_requalification": "fresh_CK-07R1_successor_from_authority_exact_main",
    }
    assert authority["run_authorization"]["status"] == "not_executed_by_this_packet"
    assert authority["run_authorization"]["maximum_new_end_to_end_runs"] == 1
    assert authority["reachable_path"]["ordering"] == (
        "recovery_read_first; planner_before_writer_lock; selected_plan_unchanged_through_writer"
    )
    assert authority["append_safe_small"]["approved_tail_limits"] == {
        "selected_bytes": 8_388_608,
        "selected_records": 32,
        "observations": 12_000,
        "occurrences": 12_000,
        "affected_sessions": 2_000,
        "affected_turns": 4_000,
        "affected_resources": 4_000,
        "affected_allowance_cycles": 512,
        "dirty_keys": 16_000,
        "projection_rows": 16_000,
        "expected_wal_bytes": 16_777_216,
        "planning_staleness_us": 5_000_000,
        "model_call_tail_rows": 32_000,
    }
    assert "planner_tail_limits" in authority["postconditions"]["required_receipt_fields"]
    assert "planner_change_estimate" in authority["postconditions"]["required_receipt_fields"]
    assert authority["reachable_path"]["identity_binding"] == {
        "same_publication_identity": [
            "ReadSelection.head.publication_id == RefreshIntent.parent_publication_id",
            "RefreshIntent.parent_publication_id == PublicationPlan.parent_publication_id",
            "PublicationPlan.parent_publication_id == SmallPublicationRequest.expected_active_publication_id",
            "SmallPublicationRequest.expected_active_publication_id == pre_commit_pointer.active.publication_id",
            "committed_AnalyticalHead.parent_publication_id == SmallPublicationRequest.expected_active_publication_id",
            "post_commit_pointer.active.publication_id == committed_AnalyticalHead.publication_id",
        ],
        "mismatch_result": "fail_closed_before_acceptance_no_stitched_artifacts_or_cross_run_identity_binding",
    }
    assert authority["independent_truth"]["oracle_symbol"] == "fold_lifecycle"
    assert authority["retained_evidence"]["writer_only_receipt_digest"] == (
        "935e4427b93e67c5ca649b773b0b3895dafac87f49bc76d7ed8917dff2f0250d"
    )
    assert {attempt["run_id"] for attempt in authority["prior_attempts"]} == {
        "all-profile-initial-serializer",
        "all-profile-corrected-serializer-tail-oracle",
        "all-profile-pid-60367-recovery",
        "production-only-valid-profile",
    }
    assert [item["path"] for item in authority["scope_additions"]] == [
        "scripts/benchmark_ck07r1_lifecycle_scale.py",
        "tests/agent_kernel/publication/test_lifecycle_scale.py",
    ]

    changed = json.loads(json.dumps(authority))
    changed["run_authorization"]["status"] = "authorized"
    assert list(validator.iter_errors(changed))

    changed = json.loads(json.dumps(authority))
    changed["readiness_transition"]["receipt_required_before_dispatch"] = True
    assert list(validator.iter_errors(changed))

    changed = json.loads(json.dumps(authority))
    changed["pr_394_policy"]["head_sha"] = "0" * 40
    assert list(validator.iter_errors(changed))

    changed = json.loads(json.dumps(authority))
    changed["reachable_path"]["identity_binding"]["same_publication_identity"][0] = "stitched"
    assert list(validator.iter_errors(changed))

    changed = json.loads(json.dumps(authority))
    changed["append_safe_small"]["approved_tail_limits"]["selected_records"] += 1
    assert list(validator.iter_errors(changed))
    changed = json.loads(json.dumps(authority))
    changed["postconditions"]["required_receipt_fields"].remove("planner_tail_limits")
    assert list(validator.iter_errors(changed))

    changed = json.loads(json.dumps(authority))
    changed["upstream_acceptance"][0]["sha"] = "0" * 40
    assert list(validator.iter_errors(changed))
    changed = json.loads(json.dumps(authority))
    changed["retained_evidence"]["fixture_digest"] = "0" * 64
    assert list(validator.iter_errors(changed))
    changed = json.loads(json.dumps(authority))
    changed["fail_closed_rules"][0] = "allow production qualification"
    assert list(validator.iter_errors(changed))

    for path, value in (
        ("observed_at_local", "2026-08-01T16:00"),
        ("failure_or_result", "changed historical cause"),
    ):
        changed = json.loads(json.dumps(authority))
        changed["prior_attempts"][0][path] = value
        assert list(validator.iter_errors(changed))
    changed = json.loads(json.dumps(authority))
    changed["prior_attempts"][2]["pid"] = 60368
    assert list(validator.iter_errors(changed))
    changed = json.loads(json.dumps(authority))
    changed["prior_attempts"][2]["receipt_digest"] = "0" * 64
    assert list(validator.iter_errors(changed))
    changed = json.loads(json.dumps(authority))
    changed["scope_additions"][1] = json.loads(json.dumps(changed["scope_additions"][0]))
    assert list(validator.iter_errors(changed))
    changed = json.loads(json.dumps(authority))
    changed["scope_additions"][0]["sha256"] = "0" * 64
    assert list(validator.iter_errors(changed))


def test_ck07r1a0_source_digest_authority_is_exact_and_fail_closed() -> None:
    authority_path = "docs/decisions/evidence/ck07r1a0/lifecycle-source-digest-authority.json"
    schema_path = authority_path.removesuffix(".json") + ".schema.json"
    authority = _json(authority_path)
    schema = _json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(authority)

    assert authority["schema"] == "codex-usage-tracker.lifecycle-source-digest-authority.v12"
    assert authority["authority_version"] == 12
    assert authority["authority_base_sha"] == "6c08ecd92a2c5166c1585be426e1ed437309a910"
    assert authority["status"] == "blocked_hold"
    assert authority["predecessor"]["sha256"] == (
        "7d1831ff5229e8e2a9819f0bd155d116ad97c3c3579bfa0444f791fe81e81feb"
    )
    assert authority["selected_successor"] == {
        "sha256": "66c015de949a6c380bd49964cb6c48c30dee64ecb14074b480837c44024328ea",
        "status": "permitted_not_accepted",
        "role": "selected_ck07_exact_candidate",
        "base_sha": "6c08ecd92a2c5166c1585be426e1ed437309a910",
        "requires_full_candidate_cohort": True,
        "direct_ck07_use": "worker_prequalification_only_after_authority_exact_main",
        "mixed_state": "fail_closed",
        "runtime_acceptance": "not_claimed",
        "launch_authorized": False,
        "artifacts": [
            {
                "path": "src/codex_usage_tracker/agent_kernel/publication/preparation.py",
                "sha256": "66c015de949a6c380bd49964cb6c48c30dee64ecb14074b480837c44024328ea",
                "role": "source",
            },
            {
                "path": "scripts/benchmark_ck07r1_lifecycle_scale.py",
                "sha256": "f108dbb45d7586a15eb370c94fc124268a249f2f6f1ee97e7b8b28a3874b737c",
                "role": "benchmark",
            },
            {
                "path": "tests/agent_kernel/publication/test_lifecycle_scale.py",
                "sha256": "4c51488988397e0ccaf40266a4f68bb1d6d342e4be1db36dd1cf36ab63aa335a",
                "role": "lifecycle_test",
            },
        ],
    }
    assert authority["acceptance_state"]["status"] == "exact_successor_selected_no_run"
    assert authority["acceptance_state"]["direct_use_of_d192"] == "forbidden"
    assert authority["superseded_r3a_candidate"]["sha256"].startswith("e204e0da")
    assert authority["historical_candidate"] == {
        "sha256": "d192c858b48e44b5aa7a7e39ef524e5ec2f08085655fe485639f5e875a727aa1",
        "status": "revoked_for_new_base",
        "direct_use": "forbidden",
        "retained_branch": "feature/ck-07r1-lifecycle-requalification-v5",
        "retained_worktree": "2026-08-01/codex-usage-tracker-ck07r1-lifecycle-requalification-v5",
        "base_sha": "955272c68548b82ea11eb65226ba0e6f3f570785",
        "witness_status": "retained_uncommitted_read_only",
        "reason": "built against the predecessor preparation base and not directly applicable after the R3A shared preparation transition",
    }
    assert authority["state_machine_binding"]["current_state"] == "authority_main"
    assert [state["name"] for state in authority["state_machine_binding"]["states"]] == [
        "authority_main",
        "r3a_accepted_predecessor",
        "worker_prequalification",
    ]
    assert authority["state_machine_binding"]["other_digest"] == "fail_closed"
    assert authority["state_machine_binding"]["launch_state"] == "blocked_hold_no_run"
    assert authority["maximum_new_end_to_end_runs"] == 1
    assert authority["run_status"] == "unspent_unavailable"
    assert (
        "src/codex_usage_tracker/agent_kernel/storage/"
        in authority["allowed_scope"]["forbidden_files"]
    )
    source = _REPO_ROOT / "src/codex_usage_tracker/agent_kernel/publication/preparation.py"
    actual_source = hashlib.sha256(source.read_bytes()).hexdigest()
    assert actual_source in {
        authority["predecessor"]["sha256"],
        authority["selected_successor"]["sha256"],
    }
    if actual_source == authority["selected_successor"]["sha256"]:
        for required in authority["selected_successor"]["artifacts"]:
            required_path = _REPO_ROOT / required["path"]
            assert required_path.is_file()
            assert hashlib.sha256(required_path.read_bytes()).hexdigest() == required["sha256"]

    mutations = [
        ("selected_successor", "sha256", "0" * 64),
        ("selected_successor", "direct_ck07_use", "allow"),
        ("selected_successor", "requires_full_candidate_cohort", False),
        ("selected_successor", "launch_authorized", True),
        ("selected_successor", "runtime_acceptance", "accepted"),
        (
            "selected_successor",
            "artifacts",
            authority["selected_successor"]["artifacts"][:-1],
        ),
        ("acceptance_state", "mixed_state", "allow"),
        ("state_machine_binding", "other_digest", "allow"),
        ("state_machine_binding", "launch_state", "ready"),
        (
            "allowed_scope",
            "files",
            authority["allowed_scope"]["files"]
            + ["src/codex_usage_tracker/agent_kernel/storage/database.py"],
        ),
    ]
    for section, field, value in mutations:
        changed = deepcopy(authority)
        changed[section][field] = value
        assert list(validator.iter_errors(changed))


def test_question_catalog_and_diagram_inventory_are_complete() -> None:
    catalog = _read("docs/product/SUPPORTED_QUESTION_CONTRACTS.md")
    question_ids = re.findall(r"^#### (Q-[A-Z]+-\d{2}):", catalog, re.MULTILINE)
    assert len(question_ids) == 40
    assert len(set(question_ids)) == 40

    mermaid_blocks = sum(
        path.read_text(encoding="utf-8").count("```mermaid") for path in _active_markdown()
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
    ck14 = _read("docs/roadmap/tasks/ck-14-delete-spike-console-obsolete-surfaces.md")
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
    declared = set(re.findall(r"^\| `([^`]+)` \|", labels_section, re.MULTILINE))
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
        retired_root not in path.read_text(encoding="utf-8").lower() for path in active_paths
    )

    resolved_pull_request_refs = ("#" + "314", "pull/" + "314")
    assert all(
        not any(marker in path.read_text(encoding="utf-8") for marker in resolved_pull_request_refs)
        for path in active_paths
    )


def test_ck07r1_consuming_boundary_is_documented_without_downstream_readiness() -> None:
    agents = _read("AGENTS.md")
    index = _read("docs/INDEX.md")
    central = _read("docs/roadmap/REMAINING_EXECUTION_PLAN.md")
    accounting = _read("docs/roadmap/TASK_PACKETS.md")
    packet = _read("docs/roadmap/tasks/ck-07r1-correct-lifecycle-preparation-scale.md")

    for body in (index, central, packet):
        assert "lifecycle-consuming-boundary-authority-v1" in body or (
            "consuming-boundary authority" in body
        )
    for body in (index, central, accounting, packet):
        assert "prelaunch-recovery" in body
    assert "019fbfe2-8fe4-7de2-9264-d58572366727" in central
    assert "019fbfe2-8fe4-7de2-9264-d58572366727" in packet
    assert "launch_authorized_once" in central
    assert "launch_authorized_once" in packet
    assert (
        "CK-08R4_CK-08RG_CK-09_blocked"
        in _json("docs/decisions/evidence/ck07r1a0/lifecycle-consuming-boundary-authority-v1.json")[
            "approval"
        ]["downstream"]
    )
    assert "Ready child tasks: **0**" in accounting
    assert "Conditional-ready child tasks: **1 — CK-07R1" in accounting
    assert "## Standing Repository Authorization" in agents
    assert "No additional user approval is required" in agents
    assert "normative coordinator/orchestration binding" in agents
    assert "cryptographic per-task authentication" in agents
    assert "force-pushes" in agents
    for body in (index, central, packet):
        assert "runtime" in body
        assert "cryptographic" in body
        assert "fast-forward" in body
        assert "67bb1a" in body


def test_ck07r1_prelaunch_recovery_is_documented_fail_closed() -> None:
    index = _read("docs/INDEX.md")
    central = _read("docs/roadmap/REMAINING_EXECUTION_PLAN.md")
    accounting = _read("docs/roadmap/TASK_PACKETS.md")
    packet = _read("docs/roadmap/tasks/ck-07r1-correct-lifecycle-preparation-scale.md")
    authority = _json(
        "docs/decisions/evidence/ck07r1a0/lifecycle-prelaunch-recovery-authority-v1.json"
    )
    for body in (index, central, accounting, packet):
        assert "prelaunch-recovery" in body
    for body in (index, central, packet):
        assert "5c2b42eca6a3e54cf4163226bc55f3c75aa35112c4ed0342c11f4e39cb9922be" in body
        assert "prelaunch_failed" in body
        assert "lifecycle-requalification-v2" in body
    assert authority["run_token"]["token_consumed"] is False
    assert authority["run_token"]["successful_launches_observed"] == 0
    assert authority["decision"]["new_invocation_is_launched_process_retry"] is False
    assert authority["decision"]["launch_authorized_in_authority_task"] is False
