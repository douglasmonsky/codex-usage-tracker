#!/usr/bin/env python3
"""Validate and transition the frozen Product Kernel Reset manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_RETIRED_PATH = _REPO_ROOT / "config" / "kernel-retired-surfaces-v1.json"
_DISPOSITION_PATH = _REPO_ROOT / "config" / "kernel-code-disposition-v1.json"
_K1_MERGE = "d8da9bccdb6674e7dca4c0872c36a1346949dc13"
_K2_DEFERRED = {
    "tests/store/test_foreign_key_cascades.py": (
        "tests/kernel/test_ingest_reconciliation.py",
        "tests/kernel/test_source_lifecycle_oracle.py",
    ),
    "tests/store/test_usage_deduplication.py": (
        "tests/kernel/test_ingest_deduplication.py",
        "tests/kernel/test_oracle_equivalence.py",
    ),
}
_K2_TRANSPLANTS = {
    "src/codex_usage_tracker/core/call_origin.py": (
        "src/codex_usage_tracker/kernel/models.py",
        ("tests/kernel/test_schema.py",),
    ),
    "src/codex_usage_tracker/core/models.py": (
        "src/codex_usage_tracker/kernel/models.py",
        ("tests/kernel/test_schema.py",),
    ),
    "src/codex_usage_tracker/core/paths.py": (
        "src/codex_usage_tracker/kernel/operational.py",
        (
            "tests/kernel/test_cutover_control.py",
            "tests/kernel/test_source_registry_privacy.py",
        ),
    ),
    "src/codex_usage_tracker/core/projects.py": (
        "src/codex_usage_tracker/kernel/identity.py",
        ("tests/kernel/test_identity.py",),
    ),
    "src/codex_usage_tracker/core/redaction.py": (
        "src/codex_usage_tracker/kernel/identity.py",
        ("tests/kernel/test_identity.py",),
    ),
    "src/codex_usage_tracker/core/schema.py": (
        "src/codex_usage_tracker/kernel/models.py",
        ("tests/kernel/test_schema.py",),
    ),
    "src/codex_usage_tracker/core/threads.py": (
        "src/codex_usage_tracker/kernel/identity.py",
        ("tests/kernel/test_identity.py",),
    ),
    "src/codex_usage_tracker/core/usage_identity.py": (
        "src/codex_usage_tracker/kernel/identity.py",
        ("tests/kernel/test_identity.py",),
    ),
    "src/codex_usage_tracker/store/cache_repository.py": (
        "src/codex_usage_tracker/kernel/operational.py",
        ("tests/kernel/test_cutover_control.py",),
    ),
    "src/codex_usage_tracker/store/connection.py": (
        "src/codex_usage_tracker/kernel/database.py",
        ("tests/kernel/test_database_lifecycle.py",),
    ),
    "src/codex_usage_tracker/store/deduplication.py": (
        "src/codex_usage_tracker/kernel/identity.py",
        ("tests/kernel/test_identity.py",),
    ),
    "src/codex_usage_tracker/store/deduplication_schema.py": (
        "src/codex_usage_tracker/kernel/schema.py",
        ("tests/kernel/test_schema.py",),
    ),
    "src/codex_usage_tracker/store/integrity.py": (
        "src/codex_usage_tracker/kernel/database.py",
        ("tests/kernel/test_database_lifecycle.py",),
    ),
    "src/codex_usage_tracker/store/rows.py": (
        "src/codex_usage_tracker/kernel/models.py",
        ("tests/kernel/test_schema.py",),
    ),
    "src/codex_usage_tracker/store/schema.py": (
        "src/codex_usage_tracker/kernel/schema.py",
        ("tests/kernel/test_schema.py",),
    ),
    "tests/store/test_connection_integrity.py": (
        "tests/kernel/test_database_lifecycle.py",
        ("tests/kernel/test_database_lifecycle.py",),
    ),
}

_K3_TRANSPLANTS = {
    "src/codex_usage_tracker/application/job_status.py": (
        "src/codex_usage_tracker/kernel/lease.py",
        ("tests/kernel/test_ingest_jobs.py",),
    ),
    "src/codex_usage_tracker/application/refresh.py": (
        "src/codex_usage_tracker/kernel/ingest.py",
        ("tests/kernel/test_ingest_pipeline.py",),
    ),
    "src/codex_usage_tracker/ingest/fact_classifiers.py": (
        "src/codex_usage_tracker/kernel/normalize.py",
        ("tests/kernel/test_ingest_oracle.py",),
    ),
    "src/codex_usage_tracker/ingest/facts.py": (
        "src/codex_usage_tracker/kernel/normalize.py",
        ("tests/kernel/test_ingest_oracle.py",),
    ),
    "src/codex_usage_tracker/parser/api.py": (
        "src/codex_usage_tracker/kernel/parser.py",
        ("tests/kernel/test_ingest_oracle.py",),
    ),
    "src/codex_usage_tracker/parser/jsonl_v1.py": (
        "src/codex_usage_tracker/kernel/parser.py",
        ("tests/kernel/test_ingest_oracle.py",),
    ),
    "src/codex_usage_tracker/parser/jsonl_values.py": (
        "src/codex_usage_tracker/kernel/parser.py",
        ("tests/kernel/test_ingest_privacy.py",),
    ),
    "src/codex_usage_tracker/parser/state.py": (
        "src/codex_usage_tracker/kernel/parser.py",
        ("tests/kernel/test_ingest_pipeline.py",),
    ),
    "src/codex_usage_tracker/store/refresh.py": (
        "src/codex_usage_tracker/kernel/writer.py",
        ("tests/kernel/test_ingest_pipeline.py",),
    ),
    "src/codex_usage_tracker/store/refresh_metadata.py": (
        "src/codex_usage_tracker/kernel/lease.py",
        ("tests/kernel/test_ingest_jobs.py",),
    ),
    "src/codex_usage_tracker/store/refresh_parse.py": (
        "src/codex_usage_tracker/kernel/parser.py",
        ("tests/kernel/test_ingest_oracle.py",),
    ),
    "src/codex_usage_tracker/store/refresh_stream.py": (
        "src/codex_usage_tracker/kernel/watcher.py",
        ("tests/kernel/test_watcher.py",),
    ),
    "src/codex_usage_tracker/store/source_record_schema.py": (
        "src/codex_usage_tracker/kernel/schema.py",
        ("tests/kernel/test_ingest_reconciliation.py",),
    ),
    "src/codex_usage_tracker/store/source_record_sync.py": (
        "src/codex_usage_tracker/kernel/writer.py",
        ("tests/kernel/test_ingest_reconciliation.py",),
    ),
    "src/codex_usage_tracker/store/source_records.py": (
        "src/codex_usage_tracker/kernel/discovery.py",
        ("tests/kernel/test_source_lifecycle_oracle.py",),
    ),
    "src/codex_usage_tracker/store/source_replacement.py": (
        "src/codex_usage_tracker/kernel/writer.py",
        ("tests/kernel/test_ingest_reconciliation.py",),
    ),
    "src/codex_usage_tracker/store/sources.py": (
        "src/codex_usage_tracker/kernel/discovery.py",
        ("tests/kernel/test_ingest_pipeline.py",),
    ),
    "tests/application/test_refresh.py": (
        "tests/kernel/test_ingest_pipeline.py",
        ("tests/kernel/test_ingest_pipeline.py",),
    ),
    "tests/cli/test_cli_parser_diagnostics.py": (
        "tests/kernel/test_ingest_privacy.py",
        ("tests/kernel/test_ingest_privacy.py",),
    ),
    "tests/interfaces/cli/test_parser.py": (
        "tests/kernel/test_ingest_oracle.py",
        ("tests/kernel/test_ingest_oracle.py",),
    ),
    "tests/parser/test_parser.py": (
        "tests/kernel/test_ingest_oracle.py",
        ("tests/kernel/test_ingest_oracle.py",),
    ),
    "tests/parser/test_parser_deduplication.py": (
        "tests/kernel/test_ingest_reconciliation.py",
        ("tests/kernel/test_oracle_equivalence.py",),
    ),
    "tests/parser/test_parser_observer.py": (
        "tests/kernel/test_watcher.py",
        ("tests/kernel/test_watcher.py",),
    ),
    "tests/parser/test_parser_state.py": (
        "tests/kernel/test_ingest_pipeline.py",
        ("tests/kernel/test_ingest_pipeline.py",),
    ),
    "tests/reliability/test_read_during_refresh.py": (
        "tests/kernel/test_ingest_concurrency.py",
        ("tests/kernel/test_ingest_concurrency.py",),
    ),
    "tests/reliability/test_refresh_locking.py": (
        "tests/kernel/test_ingest_jobs.py",
        ("tests/kernel/test_ingest_jobs.py",),
    ),
    "tests/server/test_refresh_jobs.py": (
        "tests/kernel/test_ingest_jobs.py",
        ("tests/kernel/test_ingest_jobs.py",),
    ),
    "tests/store/test_foreign_key_cascades.py": (
        "tests/kernel/test_ingest_reconciliation.py",
        ("tests/kernel/test_ingest_reconciliation.py",),
    ),
    "tests/store/test_refresh_parallel.py": (
        "tests/kernel/test_ingest_jobs.py",
        ("tests/kernel/test_ingest_jobs.py",),
    ),
    "tests/store/test_refresh_workflow.py": (
        "tests/kernel/test_ingest_pipeline.py",
        ("tests/kernel/test_ingest_pipeline.py",),
    ),
    "tests/store/test_source_records.py": (
        "tests/kernel/test_ingest_reconciliation.py",
        ("tests/kernel/test_ingest_reconciliation.py",),
    ),
    "tests/store/test_store_sources.py": (
        "tests/kernel/test_ingest_pipeline.py",
        ("tests/kernel/test_ingest_pipeline.py",),
    ),
    "tests/store/test_usage_deduplication.py": (
        "tests/kernel/test_ingest_reconciliation.py",
        ("tests/kernel/test_oracle_equivalence.py",),
    ),
}


def build_retired_surface_manifest() -> dict[str, Any]:
    """Return the immutable K1 public-surface inventory."""

    return _load(_RETIRED_PATH)


def build_code_disposition_manifest() -> dict[str, Any]:
    """Return the K1 path inventory with its current transition states."""

    return _load(_DISPOSITION_PATH)


def apply_quarantine_transition() -> None:
    """Advance every K1 non-keep path to the K1A removed state."""

    payload = build_code_disposition_manifest()
    payload["source_ref"] = _K1_MERGE
    payload["quarantine_base"] = _K1_MERGE
    for entry in payload["entries"]:
        if entry["disposition"] != "keep":
            entry["status"] = "removed"
    _DISPOSITION_PATH.write_text(_compact_manifest(payload), encoding="utf-8")


def apply_k2_transition() -> None:
    """Resolve every generic K2 assignment to one clean schema-v1 decision."""

    payload = build_code_disposition_manifest()
    base = _load_from_git(_K1_MERGE, "config/kernel-code-disposition-v1.json")
    base_by_path = {entry["path"]: entry for entry in base["entries"]}
    payload["entries"] = [
        _expected_k2_entry(base_by_path[entry["path"]])
        if entry["owner_task"] == "K2"
        else entry
        for entry in payload["entries"]
    ]
    _DISPOSITION_PATH.write_text(_compact_manifest(payload), encoding="utf-8")


def apply_k3_transition() -> None:
    """Resolve every K3 assignment to bounded ingestion or explicit retirement."""

    payload = build_code_disposition_manifest()
    base = _load_from_git(_K1_MERGE, "config/kernel-code-disposition-v1.json")
    base_by_path = {entry["path"]: entry for entry in base["entries"]}
    payload["entries"] = [
        _expected_current_entry(base_by_path[entry["path"]])
        if entry["owner_task"] == "K3"
        else entry
        for entry in payload["entries"]
    ]
    _DISPOSITION_PATH.write_text(_compact_manifest(payload), encoding="utf-8")


def manifest_failures(
    disposition: dict[str, Any] | None = None,
) -> list[str]:
    """Return deterministic failures for both frozen inventories."""

    current = disposition or build_code_disposition_manifest()
    base = _load_from_git(_K1_MERGE, "config/kernel-code-disposition-v1.json")
    retired = build_retired_surface_manifest()
    failures: list[str] = []

    paths = [entry["path"] for entry in current["entries"]]
    if len(paths) != len(set(paths)):
        failures.append("code disposition contains duplicate paths")
    base_paths = _git_lines("ls-tree", "-r", "--name-only", _K1_MERGE)
    if sorted(paths) != base_paths:
        failures.append("code disposition paths differ from the merged K1 tree")
    digest = hashlib.sha256(
        ("\n".join(sorted(paths)) + "\n").encode("utf-8")
    ).hexdigest()
    if current["resolver_input_sha256"] != digest:
        failures.append("code disposition resolver hash does not match frozen paths")
    if current.get("quarantine_base") != _K1_MERGE:
        failures.append("code disposition does not name the merged K1 quarantine base")
    if current.get("source_ref") != _K1_MERGE:
        failures.append("code disposition source ref is not the merged K1 commit")

    base_by_path = {entry["path"]: entry for entry in base["entries"]}
    for entry in current["entries"]:
        path = entry["path"]
        base_entry = base_by_path.get(path)
        if base_entry is None:
            continue
        expected_entry = _expected_current_entry(base_entry)
        immutable = {key: value for key, value in entry.items() if key != "status"}
        base_immutable = {
            key: value for key, value in expected_entry.items() if key != "status"
        }
        if immutable != base_immutable:
            failures.append(f"{path}: immutable K1 disposition decision changed")
        if (
            expected_entry["owner_task"] == "K2"
            and entry["status"] != "verified"
        ):
            failures.append(f"{path}: K2 disposition is not verified")
        if (
            expected_entry["owner_task"] == "K3"
            and entry["status"] != "verified"
        ):
            failures.append(f"{path}: K3 disposition is not verified")

    surface_keys = [
        (entry["surface_type"], entry["public_name"])
        for entry in retired["entries"]
    ]
    if len(surface_keys) != len(set(surface_keys)):
        failures.append("retired-surface inventory contains duplicate names")

    for path, payload in (
        (_DISPOSITION_PATH, current),
        (_RETIRED_PATH, retired),
    ):
        if disposition is None and path.read_text(
            encoding="utf-8"
        ) != _compact_manifest(payload):
            failures.append(f"{path.name} is not canonical")
    return failures


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_from_git(ref: str, path: str) -> dict[str, Any]:
    payload = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "show", f"{ref}:{path}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(payload)


def _expected_k2_entry(base_entry: dict[str, Any]) -> dict[str, Any]:
    entry = dict(base_entry)
    path = entry["path"]
    deferred = _K2_DEFERRED.get(path)
    if deferred is not None:
        target, oracle = deferred
        entry.update(
            {
                "owner_task": "K3",
                "reason": "Ingestion must prove this accounting lifecycle behavior.",
                "required_oracle_tests": [oracle],
                "removal_or_absence_test": oracle,
                "status": "removed",
                "target_path": target,
            }
        )
        return entry
    transplant = _K2_TRANSPLANTS.get(path)
    if transplant is None:
        entry.update(
            {
                "disposition": "retire",
                "reason": (
                    "Retired K2 spike behavior is not required by the "
                    "schema-v1 contract."
                ),
                "required_oracle_tests": [
                    "tests/kernel/test_code_disposition_manifest.py"
                ],
                "removal_or_absence_test": (
                    "tests/kernel/test_code_disposition_manifest.py"
                ),
                "status": "verified",
                "target_path": "",
            }
        )
        return entry
    target, tests = transplant
    entry.update(
        {
            "reason": (
                "Schema-v1 behavior survives through one clean kernel owner."
            ),
            "required_oracle_tests": list(tests),
            "removal_or_absence_test": tests[0],
            "status": "verified",
            "target_path": target,
        }
    )
    return entry


def _expected_k3_entry(base_entry: dict[str, Any]) -> dict[str, Any]:
    entry = dict(base_entry)
    transplant = _K3_TRANSPLANTS.get(entry["path"])
    if transplant is None:
        entry.update(
            {
                "disposition": "retire",
                "reason": (
                    "Legacy refresh, content-index, or interface orchestration "
                    "is not required by the bounded K3 ingestion contract."
                ),
                "required_oracle_tests": [
                    "tests/kernel/test_code_disposition_manifest.py"
                ],
                "removal_or_absence_test": (
                    "tests/kernel/test_code_disposition_manifest.py"
                ),
                "status": "verified",
                "target_path": "",
            }
        )
        return entry
    target, tests = transplant
    entry.update(
        {
            "reason": (
                "Incremental ingestion behavior survives through one bounded "
                "kernel owner."
            ),
            "required_oracle_tests": list(tests),
            "removal_or_absence_test": tests[0],
            "status": "verified",
            "target_path": target,
        }
    )
    return entry


def _expected_current_entry(base_entry: dict[str, Any]) -> dict[str, Any]:
    entry = (
        _expected_k2_entry(base_entry)
        if base_entry["owner_task"] == "K2"
        else dict(base_entry)
    )
    if entry["owner_task"] == "K3":
        return _expected_k3_entry(entry)
    return entry


def _git_lines(*args: str) -> list[str]:
    return subprocess.run(
        ["git", "-C", str(_REPO_ROOT), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()


def _compact_manifest(payload: dict[str, Any]) -> str:
    entries = payload["entries"]
    header = {key: value for key, value in payload.items() if key != "entries"}
    lines = ["{"]
    for key, value in header.items():
        lines.append(f"  {json.dumps(key)}: {json.dumps(value, sort_keys=True)},")
    lines.append('  "entries": [')
    for index, entry in enumerate(entries):
        suffix = "," if index + 1 < len(entries) else ""
        lines.append(
            f"    {json.dumps(entry, sort_keys=True, separators=(',', ':'))}{suffix}"
        )
    lines.extend(["  ]", "}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply-quarantine", action="store_true")
    parser.add_argument("--apply-k2", action="store_true")
    parser.add_argument("--apply-k3", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.apply_quarantine:
        apply_quarantine_transition()
    if args.apply_k2:
        apply_k2_transition()
    if args.apply_k3:
        apply_k3_transition()
    failures = manifest_failures()
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    if args.check:
        print("Kernel manifests are canonical and frozen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
