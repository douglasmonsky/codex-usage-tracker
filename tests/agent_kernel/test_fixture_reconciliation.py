from __future__ import annotations

import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

import tests.agent_kernel.fixtures.generator.generate as fixture_generator
from tests.agent_kernel.fixtures.generator.generate import generate_fixture
from tests.agent_kernel.fixtures.generator.profile import (
    load_production_shape,
    load_profile,
    planned_distribution,
    validate_production_aggregates,
    validate_production_shape,
)
from tests.agent_kernel.fixtures.oracles.bundle import build_oracle_bundle
from tests.agent_kernel.fixtures.oracles.questions import question_formula_failures
from tests.agent_kernel.fixtures.oracles.source_ledger import (
    coordinate_resolves,
    read_source_ledger,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CATALOG = (
    _REPO_ROOT / "config" / "agent-kernel" / "question-catalog-v1.json"
)


class _FakeCFunction:
    def __init__(self, result: int) -> None:
        self.argtypes: list[Any] | None = None
        self.restype: Any = None
        self.calls: list[tuple[Any, ...]] = []
        self.result = result

    def __call__(self, *args: Any) -> int:
        self.calls.append(args)
        return self.result


def _generated(tmp_path: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    root = tmp_path / "fixture"
    generate_fixture(load_profile("tiny"), root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    catalog = json.loads(_CATALOG.read_text(encoding="utf-8"))
    return root, manifest, catalog


def test_every_oracle_variant_is_derived_from_one_distinct_emitted_case(
    tmp_path: Path,
) -> None:
    root, manifest, catalog = _generated(tmp_path)
    ledger = read_source_ledger(root, manifest)
    bundle = build_oracle_bundle(load_profile("tiny"), catalog, ledger=ledger)

    expected_ids = {
        oracle_id
        for question in catalog["questions"]
        for oracle_id in question["oracle_ids"]
    }
    assert set(ledger.question_cases) == expected_ids
    assert set(bundle["questions"]) == expected_ids

    for question in catalog["questions"]:
        variants = [bundle["questions"][item] for item in question["oracle_ids"]]
        assert len({item["source_case"]["input_digest"] for item in variants}) == len(
            variants
        )
        assert len(
            {
                json.dumps(item["expected"]["row"], sort_keys=True)
                for item in variants
            }
        ) == len(variants)
        for item in variants:
            source = ledger.question_cases[item["oracle_id"]]
            assert item["source_case"]["coordinate"] == source.coordinate
            assert item["source_case"]["input_digest"] == source.input_digest
            assert item["expected"]["row"] == source.observed_facts
            assert item["contract"] == source.contract
            assert item["caveats"] == source.caveats
            assert item["selectors"]
            assert question_formula_failures(item) == []


def test_vertical_slice_control_records_capture_required_contract_facts(
    tmp_path: Path,
) -> None:
    root, manifest, _ = _generated(tmp_path)
    ledger = read_source_ledger(root, manifest)

    assert set(ledger.slice_records) == {
        "context_deterioration",
        "workflow_sequence_first_mutation",
        "allowance_interval_accounting",
        "parent_subagent_aggregation",
        "evidence_source_lifecycle",
    }
    allowance = ledger.control_records["allowance_compatibility"]
    assert allowance["compatibility_tuple"] == {
        "provider": "openai",
        "limit_id": "weekly",
        "plan_identity": "synthetic-plan",
        "window_kind": "rolling_week",
        "cycle_id": "cycle-0000",
        "reset_identity": "reset-0000",
    }
    assert ledger.control_records["rate_card"]["rate_card_id"]
    assert ledger.control_records["publication"]["publication_id"]
    assert ledger.control_records["late_parent"]["transition"] == "parent_observed_late"
    tool = ledger.control_records["tool_identity"]
    assert tool["tool_id"].startswith("tool:v1:")
    assert tool["transport_name"] == "exec_command"
    assert tool["semantic_operation"] == "execute"


def test_every_selector_resolves_to_complete_real_source_coordinates(
    tmp_path: Path,
) -> None:
    root, manifest, catalog = _generated(tmp_path)
    ledger = read_source_ledger(root, manifest)
    bundle = build_oracle_bundle(load_profile("tiny"), catalog, ledger=ledger)

    for record in bundle["questions"].values():
        for selector, coordinate in record["selectors"].items():
            assert {
                "adapter_version",
                "byte_end",
                "byte_start",
                "manifestation_id",
                "record_ordinal",
                "revision",
                "source_path",
            } <= set(coordinate)
            assert coordinate_resolves(root, selector, coordinate)


def test_lifecycle_phase_bytes_and_occurrence_mappings_are_real(
    tmp_path: Path,
) -> None:
    root, manifest, catalog = _generated(tmp_path)
    phases = {item["phase_id"]: item for item in manifest["lifecycle_phases"]}

    def body(phase_id: str) -> bytes:
        return (root / phases[phase_id]["path"]).read_bytes()

    assert body("archive-original") == body("archive-copy")
    assert body("replacement-before") != body("replacement-after")
    assert body("truncation-before").startswith(body("truncation-after"))
    assert body("moving-tail-after").startswith(body("moving-tail-before"))

    ledger = read_source_ledger(root, manifest)
    bundle = build_oracle_bundle(load_profile("tiny"), catalog, ledger=ledger)
    mappings = bundle["source_lifecycle"]["phase_occurrence_mappings"]
    assert mappings["archive"]["byte_identical"] is True
    assert mappings["replacement"]["removed"] and mappings["replacement"]["inserted"]
    assert mappings["truncation"]["removed"]
    assert mappings["moving_tail"]["preserved"] and mappings["moving_tail"]["inserted"]


def test_named_history_windows_reconcile_emitted_timestamps_and_turns(
    tmp_path: Path,
) -> None:
    root, manifest, _ = _generated(tmp_path)
    ledger = read_source_ledger(root, manifest)
    assert ledger.history == manifest["history"]["selections"]
    names = ["24_hours", "7_days", "30_days", "90_days", "one_year", "all_time"]
    call_counts = [ledger.history[name]["calls"] for name in names]
    assert call_counts == sorted(call_counts)
    for selection in ledger.history.values():
        assert selection["calls"] >= selection["turns"] >= selection["sessions"]
        assert selection["start_us"] <= selection["end_us"]


@pytest.mark.parametrize(
    ("platform_name", "symbol", "expected_argtypes", "flag"),
    [
        (
            "darwin",
            "renamex_np",
            [
                fixture_generator.ctypes.c_char_p,
                fixture_generator.ctypes.c_char_p,
                fixture_generator.ctypes.c_uint,
            ],
            fixture_generator._RENAME_EXCL,
        ),
        (
            "linux",
            "renameat2",
            [
                fixture_generator.ctypes.c_int,
                fixture_generator.ctypes.c_char_p,
                fixture_generator.ctypes.c_int,
                fixture_generator.ctypes.c_char_p,
                fixture_generator.ctypes.c_uint,
            ],
            fixture_generator._RENAME_NOREPLACE,
        ),
    ],
)
def test_atomic_no_replace_configures_platform_ctypes_signature(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform_name: str,
    symbol: str,
    expected_argtypes: list[Any],
    flag: int,
) -> None:
    staging = tmp_path / "staging"
    destination = tmp_path / "destination"
    staging.mkdir()
    function = _FakeCFunction(0)
    libc = type("_FakeLibc", (), {symbol: function})()

    monkeypatch.setattr(fixture_generator.sys, "platform", platform_name)
    monkeypatch.setattr(
        fixture_generator.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: libc,
    )

    fixture_generator._rename_directory_no_replace(staging, destination)

    assert function.argtypes == expected_argtypes
    assert function.restype is fixture_generator.ctypes.c_int
    assert len(function.calls) == 1
    assert function.calls[0][-1] == flag


@pytest.mark.parametrize(
    ("error", "error_type"),
    [
        (fixture_generator.errno.EEXIST, FileExistsError),
        (
            getattr(
                fixture_generator.errno,
                "ENOTSUP",
                fixture_generator.errno.EINVAL,
            ),
            NotImplementedError,
        ),
        (fixture_generator.errno.EACCES, OSError),
    ],
)
def test_atomic_no_replace_maps_platform_errno_without_touching_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: int,
    error_type: type[BaseException],
) -> None:
    staging = tmp_path / "staging"
    destination = tmp_path / "destination"
    staging.mkdir()
    destination.mkdir()
    sentinel = destination / "external-owner.txt"
    sentinel.write_text("preserve\n", encoding="utf-8")
    function = _FakeCFunction(-1)
    libc = type("_FakeLibc", (), {"renamex_np": function})()

    monkeypatch.setattr(fixture_generator.sys, "platform", "darwin")
    monkeypatch.setattr(
        fixture_generator.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: libc,
    )
    monkeypatch.setattr(fixture_generator.ctypes, "get_errno", lambda: error)

    with pytest.raises(error_type):
        fixture_generator._rename_directory_no_replace(staging, destination)

    assert staging.is_dir()
    assert sentinel.read_text(encoding="utf-8") == "preserve\n"


def test_publish_contender_never_removes_another_owners_lock(tmp_path: Path) -> None:
    destination = tmp_path / "owned-lock"
    lock = tmp_path / ".owned-lock.publish-lock"
    lock.write_text("external-owner\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        generate_fixture(load_profile("tiny"), destination)

    assert lock.read_text(encoding="utf-8") == "external-owner\n"
    assert not destination.exists()
    assert not list(tmp_path.glob(".owned-lock.staging-*"))


def test_publish_preserves_destination_created_after_lock_acquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "late-destination"
    lock = tmp_path / ".late-destination.publish-lock"
    real_rename = fixture_generator._rename_directory_no_replace

    def inject_destination(staging: Path, target: Path) -> None:
        assert lock.exists()
        target.mkdir()
        (target / "external-owner.txt").write_text("preserve\n", encoding="utf-8")
        real_rename(staging, target)

    monkeypatch.setattr(
        fixture_generator,
        "_rename_directory_no_replace",
        inject_destination,
    )

    with pytest.raises(FileExistsError):
        generate_fixture(load_profile("tiny"), destination)

    assert (destination / "external-owner.txt").read_text(encoding="utf-8") == "preserve\n"
    assert sorted(path.name for path in destination.iterdir()) == ["external-owner.txt"]
    assert not lock.exists()
    assert not list(tmp_path.glob(".late-destination.staging-*"))


def test_atomic_publication_race_has_exactly_one_winner_and_no_overwrite(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "race"
    barrier = threading.Barrier(2)

    def contender() -> str:
        barrier.wait()
        try:
            generate_fixture(load_profile("tiny"), destination)
        except FileExistsError:
            return "lost"
        return "won"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: contender(), range(2)))
    assert sorted(outcomes) == ["lost", "won"]
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["publication"]["atomic"] is True
    assert manifest["publication"]["no_replace"] is True
    assert (destination / "oracle-bundle.json").is_file()
    assert (destination / "sources").is_dir()
    assert not list(tmp_path.glob(".race.publish-*"))
    assert not list(tmp_path.glob(".race.staging-*"))


def test_production_shape_drives_distribution_and_rejects_semantic_drift() -> None:
    shape = load_production_shape()
    profile = load_profile("production")
    contract = shape["generation_contract"]

    assert profile.model_calls == contract["model_calls"]
    assert profile.source_manifestations == contract["source_manifestations"]
    assert planned_distribution(profile) == contract["distribution"]
    validate_production_aggregates(shape, contract["expected_stream_aggregates"])

    invalid = copy.deepcopy(shape)
    invalid["storage_shape"]["database_bytes"] += 1
    with pytest.raises(ValueError, match="storage bytes"):
        validate_production_shape(invalid)

    invalid = copy.deepcopy(shape)
    invalid["cardinality_histograms"]["tools_per_session"][0]["count"] += 1
    with pytest.raises(ValueError, match="histogram"):
        validate_production_shape(invalid)

    actual = copy.deepcopy(contract["expected_stream_aggregates"])
    actual["open_tool_invocations"] += 1
    with pytest.raises(ValueError, match="open_tool_invocations"):
        validate_production_aggregates(shape, actual)
