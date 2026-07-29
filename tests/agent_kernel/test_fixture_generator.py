from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.agent_kernel.fixtures.generator.generate import (
    generate_fixture,
    tree_digest,
)
from tests.agent_kernel.fixtures.generator.profile import load_profile

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMMITTED_TINY = Path(__file__).with_name("fixtures") / "tiny-v1"
_TINY_MANIFEST_SHA256 = "a599cf149783af04d861699b0ff587a169f20dec4d372e4ffbe3f21c51995817"
_TINY_ORACLE_SHA256 = "9f78b8f87c17ef5e98810be6a4a01f4a13bfc055ac8eb74c9f147a7087d8e41b"
_TINY_TREE_SHA256 = "a5bd281d7553836d952b1930196a3ddfadceae00b8ff0425695bb26c433b20cd"


def _generated_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_tiny_fixture_is_exactly_reproducible_and_matches_committed_bytes(
    tmp_path: Path,
) -> None:
    profile = load_profile("tiny")
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_result = generate_fixture(profile, first)
    second_result = generate_fixture(profile, second)

    assert first_result.manifest_digest == second_result.manifest_digest
    assert first_result.oracle_digest == second_result.oracle_digest
    assert tree_digest(first) == tree_digest(second)
    assert first_result.manifest_digest == _TINY_MANIFEST_SHA256
    assert first_result.oracle_digest == _TINY_ORACLE_SHA256
    assert tree_digest(first) == _TINY_TREE_SHA256
    assert _generated_files(first) == _generated_files(second)
    assert _generated_files(first) == _generated_files(_COMMITTED_TINY)


def test_cli_is_process_and_hash_seed_deterministic(tmp_path: Path) -> None:
    outputs = [tmp_path / "process-a", tmp_path / "process-b"]
    envs = [
        {**os.environ, "PYTHONHASHSEED": "1"},
        {**os.environ, "PYTHONHASHSEED": "987654"},
    ]
    payloads: list[dict[str, object]] = []
    for output, env in zip(outputs, envs, strict=True):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.agent_kernel.fixtures.generator.cli",
                "--profile",
                "tiny",
                "--output",
                str(output),
            ],
            cwd=_REPO_ROOT,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        payloads.append(json.loads(completed.stdout))

    assert payloads[0]["manifest_digest"] == payloads[1]["manifest_digest"]
    assert payloads[0]["oracle_digest"] == payloads[1]["oracle_digest"]
    assert tree_digest(outputs[0]) == tree_digest(outputs[1])


def test_manifest_only_matches_full_generation_without_materializing_sources(
    tmp_path: Path,
) -> None:
    profile = load_profile("tiny")
    full = tmp_path / "full"
    manifest_only = tmp_path / "manifest-only"

    full_result = generate_fixture(profile, full)
    manifest_result = generate_fixture(profile, manifest_only, manifest_only=True)

    assert full_result.manifest_bytes == manifest_result.manifest_bytes
    assert full_result.oracle_bytes == manifest_result.oracle_bytes
    assert not (manifest_only / "sources").exists()
    assert sorted(path.name for path in manifest_only.iterdir()) == [
        "manifest.json",
        "oracle-bundle.json",
    ]


def test_generation_is_atomic_and_never_overwrites_an_existing_target(
    tmp_path: Path,
) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "owned.txt"
    sentinel.write_text("preserve\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        generate_fixture(load_profile("tiny"), output)

    assert sentinel.read_text(encoding="utf-8") == "preserve\n"
    assert sorted(path.name for path in output.iterdir()) == ["owned.txt"]


def test_generated_artifacts_contain_no_raw_content_or_private_paths(
    tmp_path: Path,
) -> None:
    output = tmp_path / "fixture"
    generate_fixture(load_profile("tiny"), output)
    forbidden_keys = {
        "command_body",
        "patch_body",
        "prompt",
        "raw_content",
        "reasoning_content",
        "response",
        "tool_output_body",
    }
    private_fragments = (
        b"/Users/",
        b"/home/",
        b"BEGIN PRIVATE KEY",
        b"sk-",
    )

    for relative, body in _generated_files(output).items():
        assert not Path(relative).is_absolute()
        assert all(fragment not in body for fragment in private_fragments)
        payloads: list[object] = []
        if relative.endswith(".jsonl"):
            for line in body.splitlines():
                try:
                    payloads.append(json.loads(line))
                except json.JSONDecodeError:
                    assert relative == "sources/malformed/malformed.jsonl"
        else:
            payloads.append(json.loads(body))
        for payload in payloads:
            stack = [payload]
            while stack:
                value = stack.pop()
                if isinstance(value, dict):
                    assert forbidden_keys.isdisjoint(value)
                    stack.extend(value.values())
                elif isinstance(value, list):
                    stack.extend(value)
