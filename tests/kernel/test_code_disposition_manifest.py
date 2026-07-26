from __future__ import annotations

import json
import re
import subprocess
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


def _tracked_paths() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return set(result.stdout.splitlines())


def _non_ignored_untracked_paths() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return set(result.stdout.splitlines())


def test_code_disposition_resolves_entire_tracked_tree_once() -> None:
    manifest = _manifest()
    entries = manifest["entries"]
    paths = [entry["path"] for entry in entries]

    assert manifest["schema"] == "codex-usage-tracker.kernel-code-disposition.v1"
    assert manifest["resolver"] == "git ls-files"
    assert len(paths) == len(set(paths))
    assert set(paths) == _tracked_paths()
    assert {entry["disposition"] for entry in entries} == _DISPOSITIONS
    expected_inventory_hash = __import__("hashlib").sha256(
        ("\n".join(sorted(_tracked_paths())) + "\n").encode()
    ).hexdigest()
    assert manifest["resolver_input_sha256"] == expected_inventory_hash
    assert not _non_ignored_untracked_paths()


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
    from scripts.generate_kernel_manifests import build_code_disposition_manifest

    assert _manifest() == build_code_disposition_manifest()


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
