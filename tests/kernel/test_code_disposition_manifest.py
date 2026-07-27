from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _REPO_ROOT / "config" / "kernel-code-disposition-v1.json"
_DISPOSITIONS = {"keep", "transplant", "retire", "historical"}
_VALID_STATUSES = {
    "keep": {"classified", "verified"},
    "transplant": {"classified", "removed", "implemented", "verified"},
    "retire": {"classified", "removed", "verified"},
    "historical": {"classified", "removed", "archived", "verified"},
}


def _manifest() -> dict[str, object]:
    assert _MANIFEST_PATH.is_file(), "K1 code-disposition manifest is missing"
    return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


def test_code_disposition_preserves_the_frozen_k1_tree_once() -> None:
    manifest = _manifest()
    entries = manifest["entries"]
    paths = [entry["path"] for entry in entries]

    assert manifest["schema"] == "codex-usage-tracker.kernel-code-disposition.v1"
    assert manifest["resolver"] == "git ls-files"
    assert len(paths) == len(set(paths))
    assert {entry["disposition"] for entry in entries} == _DISPOSITIONS
    expected_inventory_hash = __import__("hashlib").sha256(
        ("\n".join(sorted(paths)) + "\n").encode()
    ).hexdigest()
    assert manifest["resolver_input_sha256"] == expected_inventory_hash
    assert manifest["source_ref"] == "d8da9bccdb6674e7dca4c0872c36a1346949dc13"
    assert manifest["quarantine_base"] == manifest["source_ref"]


def test_code_disposition_entries_are_decision_complete() -> None:
    for entry in _manifest()["entries"]:
        assert entry.keys() >= {
            "path",
            "disposition",
            "reason",
            "owner_task",
            "source_ref",
            "target_path",
            "public_surfaces",
            "required_oracle_tests",
            "removal_or_absence_test",
            "status",
        }
        disposition = entry["disposition"]
        assert disposition in _DISPOSITIONS
        assert entry["status"] in _VALID_STATUSES[disposition]
        assert entry["reason"]
        assert re.fullmatch(r"K(?:1A|[1-9]|1[0-6])", entry["owner_task"])
        assert entry["source_ref"]
        assert entry["required_oracle_tests"]
        assert entry["removal_or_absence_test"]
        for test_path in [
            *entry["required_oracle_tests"],
            entry["removal_or_absence_test"],
        ]:
            assert (_REPO_ROOT / test_path).is_file(), (entry["path"], test_path)
        if disposition in {"keep", "transplant"}:
            target_path = entry["target_path"]
            assert target_path
            assert not Path(target_path).is_absolute()
        if disposition == "transplant":
            assert entry["target_path"].startswith(
                ("src/codex_usage_tracker/kernel/", "tests/kernel/")
            )
        else:
            assert entry["target_path"] in {"", entry["path"]}


def test_verified_is_the_only_terminal_status() -> None:
    manifest = _manifest()

    assert manifest["terminal_status"] == "verified"
    assert manifest["state_machines"] == {
        "keep": ["classified", "verified"],
        "transplant": ["classified", "removed", "implemented", "verified"],
        "retire": ["classified", "removed", "verified"],
        "historical": ["classified", ["removed", "archived"], "verified"],
    }


def test_code_disposition_manifest_matches_generator() -> None:
    from scripts.generate_kernel_manifests import (
        build_code_disposition_manifest,
        manifest_failures,
    )

    assert _manifest() == build_code_disposition_manifest()
    assert manifest_failures() == []


def test_code_disposition_rejects_immutable_k1_decision_drift() -> None:
    from scripts.generate_kernel_manifests import manifest_failures

    changed = deepcopy(_manifest())
    changed["entries"][0]["owner_task"] = "K9"

    failures = manifest_failures(changed)

    assert any("immutable K1 disposition decision changed" in item for item in failures)


def test_progressive_tasks_advance_non_keep_paths_without_restoring_source() -> None:
    for entry in _manifest()["entries"]:
        if entry["owner_task"] in {"K2", "K3", "K4", "K5", "K6"}:
            assert entry["status"] == "verified"
        elif entry["disposition"] != "keep":
            assert entry["status"] == "removed"


def test_k2_generic_assignments_resolve_to_clean_schema_contract() -> None:
    entries = [
        entry for entry in _manifest()["entries"] if entry["owner_task"] == "K2"
    ]
    transplanted = [
        entry for entry in entries if entry["disposition"] == "transplant"
    ]
    retired = [entry for entry in entries if entry["disposition"] == "retire"]

    assert len(entries) == 78
    assert len(transplanted) == 16
    assert len(retired) == 62
    assert all(entry["status"] == "verified" for entry in entries)
    assert {
        entry["target_path"] for entry in transplanted
    } <= {
        "src/codex_usage_tracker/kernel/database.py",
        "src/codex_usage_tracker/kernel/identity.py",
        "src/codex_usage_tracker/kernel/models.py",
        "src/codex_usage_tracker/kernel/operational.py",
        "src/codex_usage_tracker/kernel/schema.py",
        "tests/kernel/test_database_lifecycle.py",
        "tests/kernel/test_identity.py",
        "tests/kernel/test_schema.py",
    }
    by_path = {entry["path"]: entry for entry in entries}
    assert by_path["tests/store/test_compression_facts.py"]["disposition"] == "retire"
    assert by_path["tests/store/test_historical_integrity_migrations.py"][
        "disposition"
    ] == "retire"
    all_entries = {entry["path"]: entry for entry in _manifest()["entries"]}
    for path in (
        "tests/store/test_foreign_key_cascades.py",
        "tests/store/test_usage_deduplication.py",
    ):
        assert all_entries[path]["owner_task"] == "K3"
        assert all_entries[path]["status"] == "verified"


def test_k3_assignments_resolve_to_bounded_ingestion_or_retirement() -> None:
    entries = [
        entry
        for entry in _manifest()["entries"]
        if entry["owner_task"] == "K3"
    ]
    transplanted = [
        entry for entry in entries if entry["disposition"] == "transplant"
    ]
    retired = [entry for entry in entries if entry["disposition"] == "retire"]

    assert len(entries) == 48
    assert len(transplanted) == 33
    assert len(retired) == 15
    assert all(entry["status"] == "verified" for entry in entries)
    assert {
        entry["target_path"] for entry in transplanted
    } <= {
        "src/codex_usage_tracker/kernel/discovery.py",
        "src/codex_usage_tracker/kernel/ingest.py",
        "src/codex_usage_tracker/kernel/lease.py",
        "src/codex_usage_tracker/kernel/normalize.py",
        "src/codex_usage_tracker/kernel/operational.py",
        "src/codex_usage_tracker/kernel/parser.py",
        "src/codex_usage_tracker/kernel/schema.py",
        "src/codex_usage_tracker/kernel/watcher.py",
        "src/codex_usage_tracker/kernel/writer.py",
        "tests/kernel/test_ingest_concurrency.py",
        "tests/kernel/test_ingest_jobs.py",
        "tests/kernel/test_ingest_oracle.py",
        "tests/kernel/test_ingest_pipeline.py",
        "tests/kernel/test_ingest_privacy.py",
        "tests/kernel/test_ingest_reconciliation.py",
        "tests/kernel/test_watcher.py",
    }


def test_k4_assignments_resolve_to_bounded_queries_or_retirement() -> None:
    entries = [
        entry
        for entry in _manifest()["entries"]
        if entry["owner_task"] == "K4"
    ]
    transplanted = [
        entry for entry in entries if entry["disposition"] == "transplant"
    ]
    retired = [entry for entry in entries if entry["disposition"] == "retire"]

    assert len(entries) == 18
    assert len(transplanted) == 13
    assert len(retired) == 5
    assert all(entry["status"] == "verified" for entry in entries)
    assert {
        entry["target_path"] for entry in transplanted
    } <= {
        "src/codex_usage_tracker/kernel/query/catalog.py",
        "src/codex_usage_tracker/kernel/query/contracts.py",
        "src/codex_usage_tracker/kernel/query/plans.py",
        "src/codex_usage_tracker/kernel/query/service.py",
        "src/codex_usage_tracker/kernel/schema.py",
        "tests/kernel/query/test_contracts.py",
        "tests/kernel/query/test_performance.py",
        "tests/kernel/query/test_service.py",
    }


def test_k5_assignment_resolves_to_exact_evidence() -> None:
    entries = [
        entry
        for entry in _manifest()["entries"]
        if entry["owner_task"] == "K5"
    ]

    assert len(entries) == 1
    assert entries[0]["disposition"] == "transplant"
    assert entries[0]["status"] == "verified"
    assert entries[0]["target_path"] == (
        "src/codex_usage_tracker/kernel/evidence/service.py"
    )


def test_k6_assignments_resolve_to_the_six_tool_interface_cutover() -> None:
    entries = [
        entry
        for entry in _manifest()["entries"]
        if entry["owner_task"] == "K6"
    ]

    assert len(entries) == 40
    assert all(entry["disposition"] == "transplant" for entry in entries)
    assert all(entry["status"] == "verified" for entry in entries)
    assert {
        entry["target_path"] for entry in entries
    } <= {
        "src/codex_usage_tracker/kernel/application/codec.py",
        "src/codex_usage_tracker/kernel/application/runtime.py",
        "src/codex_usage_tracker/kernel/application/service.py",
        "src/codex_usage_tracker/kernel/interfaces/cli/main.py",
        "src/codex_usage_tracker/kernel/interfaces/http/app.py",
        "src/codex_usage_tracker/kernel/interfaces/mcp/catalog.py",
        "src/codex_usage_tracker/kernel/interfaces/mcp/server.py",
        "src/codex_usage_tracker/kernel/plugin_manifest.py",
    }


def test_code_disposition_preserves_and_retires_semantic_boundaries() -> None:
    by_path = {entry["path"]: entry for entry in _manifest()["entries"]}

    expected = {
        "src/codex_usage_tracker/store/compression_facts.py": ("retire", "K1A"),
        "src/codex_usage_tracker/store/content_index.py": ("retire", "K1A"),
        "src/codex_usage_tracker/interfaces/mcp/compatibility_tools.py": ("retire", "K1A"),
        "src/codex_usage_tracker/application/analyze.py": ("retire", "K1A"),
        "src/codex_usage_tracker/pricing/api.py": ("transplant", "K8"),
        "src/codex_usage_tracker/release/artifact_manifest.py": ("keep", "K10"),
        "src/codex_usage_tracker/plugin_installer.py": ("transplant", "K6"),
    }
    for path, decision in expected.items():
        assert (by_path[path]["disposition"], by_path[path]["owner_task"]) == decision
