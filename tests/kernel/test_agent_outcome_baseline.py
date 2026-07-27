from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import shutil
import subprocess
import sys
import warnings
import zipfile
from pathlib import Path
from typing import Any

import pytest

from scripts.benchmark_agent_outcome import (
    _timestamp,
    candidate_identity,
    generate_history,
    load_contract,
    prompt_oracle,
    run_lifecycle_baseline,
    run_storage_baseline,
    scorecard_failures,
    stable_scorecard_shape,
    summarize_cli_observation,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTRACT = _REPO_ROOT / "config" / "product-recovery-agent-baseline-v1.json"
_ANSWER_SCHEMA = _REPO_ROOT / "config" / "product-recovery-agent-answer-v1.schema.json"
_RESULTS = _REPO_ROOT / "config" / "product-recovery-agent-baseline-results-v1.json"


@pytest.fixture(scope="module")
def candidate_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("r1-wheel")
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(output)],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return next(output.glob("*.whl"))


def _cached_bundle(root: Path) -> Path:
    cache = root / "cache"
    shutil.copytree(_REPO_ROOT / ".codex-plugin", cache / ".codex-plugin")
    shutil.copyfile(_REPO_ROOT / ".mcp.json", cache / ".mcp.json")
    shutil.copytree(_REPO_ROOT / "skills", cache / "skills")
    return cache


def _rewrite_wheel_version(source: Path, target: Path, version: str) -> None:
    with zipfile.ZipFile(source) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    metadata_name = next(name for name in members if name.endswith(".dist-info/METADATA"))
    record_name = next(name for name in members if name.endswith(".dist-info/RECORD"))
    metadata = members[metadata_name].decode().replace("Version: 0.28.0", f"Version: {version}")
    members[metadata_name] = metadata.encode()
    rows: list[list[str]] = []
    for name, payload in sorted(members.items()):
        if name == record_name:
            rows.append([name, "", ""])
            continue
        digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=").decode()
        rows.append([name, f"sha256={digest}", str(len(payload))])
    stream = io.StringIO()
    csv.writer(stream, lineterminator="\n").writerows(rows)
    members[record_name] = stream.getvalue().encode()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)


def _valid_scorecard(contract: dict[str, Any]) -> dict[str, Any]:
    digest = "sha256:abc"
    tools = [
        "usage_status",
        "usage_refresh",
        "usage_query",
        "usage_evidence",
        "usage_allowance",
        "usage_job_status",
    ]
    selector_prompts = {
        item["id"] for item in contract["prompt_suite"] if item["selector_required"]
    }
    runs = []
    for host in contract["supported_hosts"]:
        for prompt in contract["prompt_suite"]:
            runs.append(
                {
                    "accuracy": 1.0,
                    "candidate_digest": digest,
                    "candidate_registration": "candidate-marketplace",
                    "candidate_version": "0.28.0",
                    "catalog_observed": True,
                    "catalog_tools": tools,
                    "claim_grades": ["fact", "inference"],
                    "error_code": None,
                    "exposure_observed": True,
                    "final_answer_ms": 10.0,
                    "first_tool_ms": 1.0,
                    "fresh_task": True,
                    "generation": 1,
                    "handshake_observed": True,
                    "host": host["id"],
                    "host_version": "synthetic 1.0",
                    "human_labels": True,
                    "launch_method": host["launch_method"],
                    "mcp_calls": 2,
                    "polls": 0,
                    "prompt_id": prompt["id"],
                    "query_batches": 1,
                    "refresh_joins": 0,
                    "refresh_starts": 0,
                    "registration_observed": True,
                    "response_bytes": 500,
                    "retries": 0,
                    "scenario": "warm_generation",
                    "selector_validity": (
                        1.0 if prompt["id"] in selector_prompts else "not_applicable"
                    ),
                    "success": True,
                    "terminal_state": "completed",
                    "tracker_ms": 2.0,
                    "usefulness": 4,
                }
            )
    scenario_runs = [
        {
            "elapsed_ms": 1.0,
            "error_code": None,
            "measurement_source": "storage_runner",
            "outcome": "observed_pass",
            "scenario": item["id"],
        }
        for item in contract["scenarios"]
    ]
    return {
        "candidate": {
            "bundle_digest": digest,
            "source_revision": "abc",
            "version": "0.28.0",
            "wheel_sha256": "abc",
        },
        "profile_evidence": {
            "profiler": "scalene 2.3.0",
            "run_id": "synthetic-run",
            "status": "attribution_only",
        },
        "runs": runs,
        "scenario_runs": scenario_runs,
        "schema": "codex-usage-tracker.agent-outcome-scorecard.v1",
        "small_ci": {
            "database_bytes": 1,
            "source_sha256": "abc",
            "stable_result_sha256": "abc",
        },
        "storage": {
            "database_bytes": 1,
            "phase_ms": {
                "append_safe_tail": 1.0,
                "cold_build": 1.0,
                "no_change": 1.0,
            },
            "source_sha256": "abc",
        },
    }


def test_contract_freezes_prompts_hosts_scenarios_and_targets() -> None:
    contract = load_contract(_CONTRACT)

    assert contract["schema"] == "codex-usage-tracker.agent-outcome-baseline.v1"
    assert [item["id"] for item in contract["prompt_suite"]] == [
        "top_threads",
        "weekly_drivers",
        "week_over_week",
        "model_effort_cost",
        "four_token_classes",
        "allowance_drain",
        "tool_context",
        "evidence_timeline",
        "expensive_thread_calls",
        "latest_incremental_change",
    ]
    assert {item["id"] for item in contract["supported_hosts"]} == {
        "codex_cli",
        "codex_desktop",
    }
    assert {item["id"] for item in contract["scenarios"]} == {
        "no_index",
        "warm_generation",
        "no_change_refresh",
        "append_safe_tail",
        "bounded_tail",
        "moving_tail",
        "refresh_in_progress",
        "browser_reopen",
        "plugin_upgrade",
        "fresh_host_task",
        "stale_task_catalog",
    }
    assert contract["gates"] == {
        "cold_build_ms": 240_000,
        "console_render_ms": 500,
        "database_bytes": 700 * 1024 * 1024,
        "deterministic_accuracy": 1.0,
        "selector_validity": 1.0,
        "tail_refresh_ms": 500,
        "top_threads_final_answer_ms": 15_000,
        "top_threads_tracker_ms": 1_000,
        "warm_status_ms": 100,
    }
    answer_schema = json.loads(_ANSWER_SCHEMA.read_text(encoding="utf-8"))
    assert answer_schema["additionalProperties"] is False
    assert answer_schema["properties"]["facts"]["maxItems"] == 12
    assert (
        not {
            "prompt",
            "response",
            "reasoning",
            "transcript",
        }
        & answer_schema["properties"].keys()
    )


def test_small_history_is_byte_deterministic_and_manifested(tmp_path: Path) -> None:
    first = generate_history(tmp_path / "first", profile="small_ci", seed=20260727)
    second = generate_history(tmp_path / "second", profile="small_ci", seed=20260727)

    assert first == second
    assert first["profile"] == "small_ci"
    assert first["source_files"] == 8
    assert first["threads"] == 8
    assert first["turns"] == 32
    assert first["model_calls"] == 96
    assert first["tool_calls"] == 64
    assert first["activity_events"] == 32
    assert first["allowance_observations"] == 12
    assert (
        first["source_sha256"]
        == "c49ca558ca0b768e976e6d556ac62925e66e429192718e433944167c87294546"
    )
    assert first["source_sha256"] == second["source_sha256"]
    different = generate_history(
        tmp_path / "different",
        profile="small_ci",
        seed=20260728,
    )
    assert different["source_sha256"] != first["source_sha256"]


def test_multi_year_profile_spreads_source_high_waters_across_history(
) -> None:
    profile = next(
        item
        for item in load_contract(_CONTRACT)["history_profiles"]
        if item["id"] == "production_multi_year"
    )

    assert _timestamp(
        20_727,
        255,
        profile=profile,
        source_ordinal=0,
    ) == "2023-07-29T00:04:15.000Z"
    assert _timestamp(
        21_369,
        255,
        profile=profile,
        source_ordinal=642,
    ) == "2026-07-26T00:04:15.000Z"


def test_small_storage_baseline_covers_cold_no_change_and_tail(
    tmp_path: Path,
) -> None:
    baseline = run_storage_baseline(
        tmp_path / "baseline",
        profile="small_ci",
        seed=20260727,
    )

    assert baseline["schema"] == "codex-usage-tracker.storage-baseline.v1"
    assert baseline["manifest"]["model_calls"] == 96
    assert baseline["phases"]["cold_build"]["generation"] == 1
    assert baseline["phases"]["cold_build"]["inserted_calls"] == 96
    assert baseline["phases"]["no_change"]["generation"] == 1
    assert baseline["phases"]["no_change"]["inserted_calls"] == 0
    assert baseline["phases"]["append_safe_tail"]["generation"] == 2
    assert baseline["phases"]["append_safe_tail"]["inserted_calls"] == 1
    assert baseline["fact_rows"]["model_calls"] == 97
    assert baseline["database_bytes"] > 0


def test_every_prompt_has_an_executable_deterministic_oracle(tmp_path: Path) -> None:
    run_storage_baseline(tmp_path / "oracle", profile="small_ci", seed=20260727)
    contract = load_contract(_CONTRACT)

    first = {
        item["id"]: prompt_oracle(tmp_path / "oracle" / "cache", item["id"])
        for item in contract["prompt_suite"]
    }
    second = {
        item["id"]: prompt_oracle(tmp_path / "oracle" / "cache", item["id"])
        for item in contract["prompt_suite"]
    }

    assert first == second
    assert set(first) == {item["id"] for item in contract["prompt_suite"]}
    assert all(facts for facts in first.values())
    assert all(
        fact["selector"]
        for prompt in ("evidence_timeline", "expensive_thread_calls")
        for fact in first[prompt]
    )


def test_lifecycle_runner_measures_or_explicitly_terminalizes_every_scenario(
    tmp_path: Path,
) -> None:
    contract = load_contract(_CONTRACT)
    results = run_lifecycle_baseline(tmp_path / "lifecycle", seed=20260727)

    assert {item["scenario"] for item in results} == {
        item["id"] for item in contract["scenarios"]
    }
    assert all(item["outcome"] != "observed_fail" for item in results)
    assert all(
        item["elapsed_ms"] is not None
        for item in results
        if item["outcome"] == "observed_pass"
    )
    assert all(
        item["error_code"]
        for item in results
        if item["outcome"] == "unsupported"
    )


def test_candidate_identity_binds_wheel_plugin_mcp_skill_cache_and_revision(
    tmp_path: Path,
    candidate_wheel: Path,
) -> None:
    identity = candidate_identity(
        repo_root=_REPO_ROOT,
        wheel=candidate_wheel,
        cached_bundle=_cached_bundle(tmp_path),
    )

    assert identity["version"] == "0.28.0"
    assert identity["source_revision"]
    assert identity["wheel"]["sha256"]
    assert identity["plugin"]["digest"].startswith("sha256:")
    assert identity["mcp"]["server"] == "codex-usage-tracker"
    assert identity["mcp"]["tools"] == 6
    assert identity["mcp"]["catalog"] == [
        "usage_status",
        "usage_refresh",
        "usage_query",
        "usage_evidence",
        "usage_allowance",
        "usage_job_status",
    ]
    assert identity["skill"]["name"] == "usage-kernel"
    assert identity["cached_bundle"]["digest"] == identity["plugin"]["digest"]
    assert not any(
        "/" in str(value)
        for value in (
            identity["wheel"]["name"],
            identity["cached_bundle"]["registration"],
        )
    )


def test_candidate_identity_rejects_corrupt_and_mismatched_wheels(
    tmp_path: Path,
    candidate_wheel: Path,
) -> None:
    corrupt = tmp_path / candidate_wheel.name
    shutil.copyfile(candidate_wheel, corrupt)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(corrupt, "a") as archive:
            archive.writestr(
                "codex_usage_tracker/kernel/__init__.py",
                b"__version__ = '0.28.0'\n",
            )
    with pytest.raises(ValueError, match="RECORD digest mismatch"):
        candidate_identity(
            repo_root=_REPO_ROOT,
            wheel=corrupt,
            cached_bundle=_cached_bundle(tmp_path / "corrupt-cache"),
        )

    mismatch = tmp_path / "mismatch.whl"
    _rewrite_wheel_version(candidate_wheel, mismatch, "9.9.9")
    with pytest.raises(ValueError, match="wheel runtime version differs"):
        candidate_identity(
            repo_root=_REPO_ROOT,
            wheel=mismatch,
            cached_bundle=_cached_bundle(tmp_path / "mismatch-cache"),
        )


def test_cli_observation_reduces_ephemeral_events_to_safe_metrics() -> None:
    expected = [
        {
            "key": "thread_total_tokens",
            "label": "Synthetic thread",
            "selector": "thread:thr_a",
            "value": 42,
        }
    ]
    events = [
        (
            10.0,
            {
                "type": "item.started",
                "item": {
                    "id": "tool-1",
                    "type": "mcp_tool_call",
                    "tool": "usage_status",
                },
            },
        ),
        (
            14.0,
            {
                "type": "item.completed",
                "item": {
                    "id": "tool-1",
                    "type": "mcp_tool_call",
                    "tool": "usage_status",
                    "result": {"structured_content": {"generation": 1}},
                },
            },
        ),
        (
            20.0,
            {
                "type": "item.started",
                "item": {
                    "id": "tool-2",
                    "type": "mcp_tool_call",
                    "tool": "usage_query",
                },
            },
        ),
        (
            27.0,
            {
                "type": "item.completed",
                "item": {
                    "id": "tool-2",
                    "type": "mcp_tool_call",
                    "tool": "usage_query",
                    "result": {"structured_content": {"results": []}},
                },
            },
        ),
        (
            30.0,
            {
                "type": "item.completed",
                "item": {
                    "id": "answer",
                    "type": "agent_message",
                    "text": json.dumps(
                        {
                            "claim_grades": ["fact"],
                            "error_code": None,
                            "generation": 1,
                            "prompt_id": "top_threads",
                            "facts": expected,
                            "success": True,
                            "tool_calls": 2,
                        }
                    ),
                },
            },
        ),
        (31.0, {"type": "turn.completed"}),
    ]

    summary = summarize_cli_observation(
        events,
        total_ms=31.0,
        host_version="codex-cli synthetic",
        candidate_registration="candidate-marketplace",
        candidate_digest="sha256:abc",
        candidate_version="0.28.0",
        catalog_tools=[
            "usage_status",
            "usage_refresh",
            "usage_query",
            "usage_evidence",
            "usage_allowance",
            "usage_job_status",
        ],
        registration_observed=True,
        handshake_observed=True,
        exposure_observed=True,
        prompt_id="top_threads",
        expected_facts=expected,
    )

    assert summary["success"] is True
    assert summary["accuracy"] == 1.0
    assert summary["mcp_calls"] == 2
    assert summary["query_batches"] == 1
    assert summary["tracker_ms"] == 11.0
    assert summary["first_tool_ms"] == 10.0
    assert summary["usefulness"] == 4
    assert summary["selector_validity"] == "not_applicable"
    assert summary["fresh_task"] is True
    assert "text" not in summary


def test_scorecard_rejects_private_text_paths_and_incomplete_host_proof() -> None:
    contract = load_contract(_CONTRACT)
    scorecard = _valid_scorecard(contract)
    scorecard["notes"] = "verbatim private transcript"
    scorecard["runs"][0]["candidate_registration"] = "/Volumes/Private/session.jsonl"
    scorecard["runs"][1]["fresh_task"] = True
    scorecard["runs"][1]["handshake_observed"] = False

    failures = scorecard_failures(scorecard, contract)

    assert "scorecard has unexpected property notes" in failures
    assert (
        "forbidden local path-like value: runs[0].candidate_registration"
        in failures
    )
    assert "runs[1] fresh-task proof is inconsistent" in failures


@pytest.mark.parametrize(
    "private_value",
    [
        "~/session.jsonl",
        "../session.jsonl",
        "file:///tmp/session.jsonl",
        "https://private.example/session",
        "C:\\Users\\example\\session.jsonl",
        "%2FUsers%2Fexample%2Fsession.jsonl",
    ],
)
def test_scorecard_rejects_path_uri_and_home_aliases(private_value: str) -> None:
    contract = load_contract(_CONTRACT)
    scorecard = _valid_scorecard(contract)
    scorecard["runs"][0]["candidate_registration"] = private_value

    failures = scorecard_failures(scorecard, contract)

    assert any("forbidden local path-like value" in failure for failure in failures)


def test_scorecard_shape_ignores_measurements_but_not_outcomes() -> None:
    first = {
        "schema": "codex-usage-tracker.agent-outcome-scorecard.v1",
        "candidate": {"version": "0.28.0", "source_revision": "abc"},
        "runs": [
            {
                "host": "codex_cli",
                "prompt_id": "top_threads",
                "success": True,
                "accuracy": 1.0,
                "final_answer_ms": 1200.0,
                "tracker_ms": 8.0,
                "response_bytes": 500,
            }
        ],
    }
    second = json.loads(json.dumps(first))
    second["runs"][0]["final_answer_ms"] = 1400.0
    second["runs"][0]["tracker_ms"] = 9.0
    second["runs"][0]["response_bytes"] = 520

    assert stable_scorecard_shape(first) == stable_scorecard_shape(second)

    second["runs"][0]["accuracy"] = 0.0
    assert stable_scorecard_shape(first) != stable_scorecard_shape(second)


def test_valid_scorecard_is_bounded_and_has_every_fresh_host() -> None:
    contract = load_contract(_CONTRACT)
    scorecard = _valid_scorecard(contract)

    assert scorecard_failures(scorecard, contract) == []
    assert len(json.dumps(scorecard, sort_keys=True).encode()) <= 64 * 1024
    assert {
        (run["host"], run["prompt_id"]) for run in scorecard["runs"]
    } == {
        (host["id"], prompt["id"])
        for host in contract["supported_hosts"]
        for prompt in contract["prompt_suite"]
    }


def test_recorded_baseline_is_privacy_safe_and_keeps_failed_targets() -> None:
    contract = load_contract(_CONTRACT)
    results = json.loads(_RESULTS.read_text(encoding="utf-8"))

    assert scorecard_failures(results, contract) == []
    assert results["storage"]["phase_ms"]["cold_build"] > contract["gates"]["cold_build_ms"]
    assert results["storage"]["database_bytes"] > contract["gates"]["database_bytes"]
    assert results["storage"]["phase_ms"]["append_safe_tail"] > contract["gates"]["tail_refresh_ms"]
    assert {run["host"] for run in results["runs"]} == {
        "codex_cli",
        "codex_desktop",
    }
    assert all(run["accuracy"] == 0.0 for run in results["runs"])


@pytest.mark.parametrize("profile", ["unknown", ""])
def test_history_rejects_unknown_profiles(tmp_path: Path, profile: str) -> None:
    with pytest.raises(ValueError, match="unknown history profile"):
        generate_history(tmp_path / "history", profile=profile, seed=1)
