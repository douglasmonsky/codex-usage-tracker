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
from tests.agent_kernel.fixtures.generator.profile import (
    load_profile,
    planned_distribution,
)
from tests.agent_kernel.fixtures.generator.semantic import (
    event_at_us,
    history_windows,
    selected,
)
from tests.agent_kernel.fixtures.generator.sources import (
    clustered_source_index,
    source_specs,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMMITTED_TINY = Path(__file__).with_name("fixtures") / "tiny-v1"
_TINY_MANIFEST_SHA256 = "91e0658f913c917bd8ce69fac9a1d75e881f41630eccc0f30f68bd9b6a972a35"
_TINY_ORACLE_SHA256 = "38787c3806be52a69ec03e7e8dcb0044b87dac4be826d620abf4cf34656da412"
_TINY_TREE_SHA256 = "2321918c18652fc617882aef5f9c8584d3d6d73576037b516a2c9f9dcbc0f656"


def _generated_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _source_timestamps(
    root: Path,
    relative_path: str,
    *,
    record_type: str | None = None,
) -> list[int]:
    timestamps: list[int] = []
    source_path = root / relative_path
    if not source_path.exists():
        return timestamps
    for line in source_path.read_bytes().splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(record, dict)
            and type(record.get("event_at_us")) is int
            and (record_type is None or record.get("type") == record_type)
        ):
            timestamps.append(record["event_at_us"])
    return timestamps


def _inventory_selects(
    entry: dict[str, object],
    *,
    start_us: int,
    end_us: int,
) -> bool:
    confidence = entry["time_range_confidence"]
    hint = entry["time_range_hint"]
    if confidence != "trusted":
        return True
    assert isinstance(hint, dict)
    return hint["end_us"] > start_us and hint["start_us"] <= end_us


def _include_planned_timestamp(
    bounds: list[list[int] | None],
    source_index: int,
    timestamp: int,
) -> None:
    bound = bounds[source_index]
    if bound is None:
        bounds[source_index] = [timestamp, timestamp + 1]
        return
    bound[0] = min(bound[0], timestamp)
    bound[1] = max(bound[1], timestamp + 1)


def test_source_time_hints_cover_every_emitted_timestamp_and_late_event() -> None:
    manifest = json.loads(
        (_COMMITTED_TINY / "manifest.json").read_text(encoding="utf-8")
    )
    entries = manifest["sources"]
    assert isinstance(entries, list)

    hinted_paths = 0
    for entry in entries:
        assert isinstance(entry, dict)
        timestamps = _source_timestamps(_COMMITTED_TINY, entry["path"])
        confidence = entry["time_range_confidence"]
        hint = entry["time_range_hint"]
        assert confidence in {"trusted", "uncertain", "unavailable"}
        if hint is None:
            assert confidence == "unavailable"
            assert not timestamps
            continue
        assert confidence in {"trusted", "uncertain"}
        assert set(hint) == {"end_us", "start_us"}
        assert hint["start_us"] < hint["end_us"]
        assert timestamps
        assert hint["start_us"] <= min(timestamps)
        assert max(timestamps) < hint["end_us"]
        hinted_paths += 1

    assert hinted_paths > 1
    unavailable_paths = {
        entry["path"]
        for entry in entries
        if entry["time_range_confidence"] == "unavailable"
    }
    assert unavailable_paths == {
        "sources/deferred/deferred.jsonl",
        "sources/malformed/malformed.jsonl",
        "sources/truncated/truncated.jsonl",
    }

    uncertain_entries = [
        entry
        for entry in entries
        if entry["time_range_confidence"] == "uncertain"
    ]
    assert {entry["path"] for entry in uncertain_entries} == {
        "sources/active/source-0000.jsonl",
        "sources/active/source-0001.jsonl",
        "sources/replaced/revision-1.jsonl",
    }
    for uncertain in uncertain_entries:
        uncertain_hint = uncertain["time_range_hint"]
        assert isinstance(uncertain_hint, dict)
        assert _inventory_selects(
            uncertain,
            start_us=uncertain_hint["end_us"] + 1,
            end_us=uncertain_hint["end_us"] + 2,
        )

    assert not _inventory_selects(
        {
            "time_range_confidence": "trusted",
            "time_range_hint": {"end_us": 100, "start_us": 99},
        },
        start_us=100,
        end_us=200,
    )
    assert _inventory_selects(
        {
            "time_range_confidence": "trusted",
            "time_range_hint": {"end_us": 201, "start_us": 200},
        },
        start_us=100,
        end_us=200,
    )

    profile = load_profile("tiny")
    distribution = planned_distribution(profile)
    expected_late_timestamps = {
        event_at_us(profile, ordinal, late=True)
        for ordinal in range(profile.model_calls)
        if selected(
            ordinal,
            profile.model_calls,
            distribution["late_events"],
        )
    }
    observed_late_timestamps = set()
    for entry in entries:
        if not entry["persisted_when_requested"]:
            continue
        timestamps = _source_timestamps(
            _COMMITTED_TINY,
            entry["path"],
            record_type="model_call",
        )
        hint = entry["time_range_hint"]
        if not isinstance(hint, dict):
            continue
        for timestamp in expected_late_timestamps.intersection(timestamps):
            assert hint["start_us"] <= timestamp < hint["end_us"]
            observed_late_timestamps.add(timestamp)
    assert observed_late_timestamps == expected_late_timestamps


def test_production_source_plan_limits_30_day_inventory_to_recent_clusters() -> None:
    profile = load_profile("production")
    distribution = planned_distribution(profile)
    specs = source_specs(profile)
    active_count = sum(spec.state == "active" for spec in specs)
    archived = next(spec for spec in specs if spec.state == "archived")
    replaced = next(spec for spec in specs if spec.state == "replaced")
    bounds: list[list[int] | None] = [None] * len(specs)

    for ordinal in range(profile.model_calls):
        source_index = clustered_source_index(
            ordinal,
            model_calls=profile.model_calls,
            active_sources=active_count,
        )
        timestamp = event_at_us(
            profile,
            ordinal,
            late=selected(
                ordinal,
                profile.model_calls,
                distribution["late_events"],
            ),
        )
        _include_planned_timestamp(bounds, source_index, timestamp)
        if selected(
            ordinal,
            profile.model_calls,
            distribution["duplicate_call_occurrences"],
        ):
            _include_planned_timestamp(bounds, archived.index, timestamp)
    _include_planned_timestamp(bounds, replaced.index, profile.start_at_us)
    uncertain_indices = {0, 1, replaced.index}

    window = history_windows(
        profile,
        late_event_count=distribution["late_events"],
    )["30_days"]
    entries = [
        {
            "time_range_confidence": (
                "unavailable"
                if bound is None
                else (
                    "uncertain"
                    if spec.index in uncertain_indices
                    else "trusted"
                )
            ),
            "time_range_hint": (
                None
                if bound is None
                else {"end_us": bound[1], "start_us": bound[0]}
            ),
        }
        for spec, bound in zip(specs, bounds, strict=True)
    ]
    selected_indices = {
        index
        for index, entry in enumerate(entries)
        if _inventory_selects(
            entry,
            start_us=window["start_us"],
            end_us=window["end_us"],
        )
    }

    assert selected_indices == {
        0,
        1,
        *range(620, 643),
    }
    assert len(selected_indices) == 25
    assert 0 in selected_indices
    assert 1 in selected_indices
    assert replaced.index in selected_indices
    assert len(selected_indices) < active_count // 20


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
