from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

_PROFILE_ROOT = Path(__file__).resolve().parents[1] / "profiles"
_REPO_ROOT = Path(__file__).resolve().parents[4]
_PRODUCTION_SHAPE_PATH = _PROFILE_ROOT / "production-shape-v1.json"
_PRODUCTION_SHAPE_SCHEMA_PATH = (
    _REPO_ROOT / "config" / "agent-kernel" / "production-shape-profile-v1.schema.json"
)
_SCHEMA = "codex-usage-tracker.synthetic-fixture-profile.v1"
_PROFILE_NAMES = ("tiny", "small", "standard", "production", "growth")
_RATIO_KEYS = frozenset(
    {
        "activities",
        "allowance_observations",
        "compaction_boundaries",
        "duplicate_call_occurrences",
        "late_events",
        "missing_cached_input_calls",
        "state_changes",
        "tool_invocations",
        "unpriced_calls",
    }
)
_SEMANTIC_CASES = (
    "context_deterioration",
    "workflow_sequence_first_mutation",
    "allowance_interval_accounting",
    "parent_subagent_aggregation",
    "evidence_source_lifecycle",
)


@dataclass(frozen=True)
class FixtureProfile:
    """Closed input to the deterministic structural fixture generator."""

    name: str
    seed: int
    model_calls: int
    source_manifestations: int
    history_days: int
    timezone: str
    start_at_us: int
    semantic_cases: tuple[str, ...]
    ratios_basis_points: tuple[tuple[str, int], ...]
    distribution_override: tuple[tuple[str, int], ...] = ()

    def ratio(self, name: str) -> int:
        values = dict(self.ratios_basis_points)
        return values[name]


def _object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain one object")
    return payload


def _positive_integer(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{key} must be a positive integer")
    return value


def _profile_from_payload(payload: dict[str, Any], *, path: Path) -> FixtureProfile:
    required = {
        "schema",
        "version",
        "name",
        "seed",
        "model_calls",
        "source_manifestations",
        "history_days",
        "timezone",
        "start_at_us",
        "semantic_cases",
        "ratios_basis_points",
    }
    if set(payload) != required:
        raise ValueError(
            f"{path.name} profile keys differ: "
            f"missing={sorted(required - set(payload))}, "
            f"extra={sorted(set(payload) - required)}"
        )
    if payload["schema"] != _SCHEMA or payload["version"] != 1:
        raise ValueError(f"{path.name} has an unsupported fixture profile version")
    name = payload["name"]
    if not isinstance(name, str) or name not in _PROFILE_NAMES:
        raise ValueError(f"{path.name} has an unknown profile name")
    if path.stem != f"{name}-v1":
        raise ValueError(f"{path.name} does not match profile name {name}")
    seed = _positive_integer(payload, "seed")
    model_calls = _positive_integer(payload, "model_calls")
    source_manifestations = _positive_integer(payload, "source_manifestations")
    history_days = _positive_integer(payload, "history_days")
    start_at_us = _positive_integer(payload, "start_at_us")
    timezone = payload["timezone"]
    if timezone != "UTC":
        raise ValueError("CK-03 scale fixtures use UTC; query vectors own timezone cases")
    semantic_cases = payload["semantic_cases"]
    if (
        not isinstance(semantic_cases, list)
        or tuple(semantic_cases) != _SEMANTIC_CASES
    ):
        raise ValueError(f"{path.name} must use the complete semantic case library")
    ratios = payload["ratios_basis_points"]
    if not isinstance(ratios, dict) or set(ratios) != _RATIO_KEYS:
        raise ValueError(f"{path.name} ratio keys differ from the closed registry")
    normalized_ratios: list[tuple[str, int]] = []
    for key in sorted(ratios):
        value = ratios[key]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
            raise ValueError(f"{path.name} ratio {key} must be 0..10000 basis points")
        normalized_ratios.append((key, value))
    if source_manifestations < 12:
        raise ValueError("fixture profiles need at least twelve source manifestations")
    return FixtureProfile(
        name=name,
        seed=seed,
        model_calls=model_calls,
        source_manifestations=source_manifestations,
        history_days=history_days,
        timezone=timezone,
        start_at_us=start_at_us,
        semantic_cases=tuple(semantic_cases),
        ratios_basis_points=tuple(normalized_ratios),
    )


def load_profile(name: str) -> FixtureProfile:
    """Load and fail-closed validate one versioned fixture profile."""

    if name not in _PROFILE_NAMES:
        raise ValueError(f"unknown fixture profile {name!r}")
    path = _PROFILE_ROOT / f"{name}-v1.json"
    profile = _profile_from_payload(_object(path), path=path)
    if name != "production":
        return profile
    shape = load_production_shape()
    contract = shape["generation_contract"]
    if profile.model_calls != contract["model_calls"]:
        raise ValueError("production shape model_calls differ from scale profile")
    if profile.source_manifestations != contract["source_manifestations"]:
        raise ValueError(
            "production shape source_manifestations differ from scale profile"
        )
    return replace(
        profile,
        distribution_override=tuple(sorted(contract["distribution"].items())),
    )


def load_all_profiles() -> tuple[FixtureProfile, ...]:
    """Return profiles in ascending scale order."""

    return tuple(load_profile(name) for name in _PROFILE_NAMES)


def _ratio_count(profile: FixtureProfile, name: str, *, minimum: int) -> int:
    return max(minimum, profile.model_calls * profile.ratio(name) // 10_000)


def planned_distribution(profile: FixtureProfile) -> dict[str, int]:
    """Return exact scale counts without materializing any fixture bytes."""

    if profile.distribution_override:
        return dict(profile.distribution_override)
    return {
        "activities": _ratio_count(profile, "activities", minimum=4),
        "allowance_observations": _ratio_count(
            profile,
            "allowance_observations",
            minimum=4,
        ),
        "compaction_boundaries": _ratio_count(
            profile,
            "compaction_boundaries",
            minimum=2,
        ),
        "duplicate_call_occurrences": _ratio_count(
            profile,
            "duplicate_call_occurrences",
            minimum=2,
        ),
        "late_events": _ratio_count(profile, "late_events", minimum=2),
        "missing_cached_input_calls": _ratio_count(
            profile,
            "missing_cached_input_calls",
            minimum=2,
        ),
        "model_calls": profile.model_calls,
        "sessions": (profile.model_calls + 9) // 10,
        "state_changes": _ratio_count(profile, "state_changes", minimum=4),
        "tool_invocations": _ratio_count(
            profile,
            "tool_invocations",
            minimum=8,
        ),
        "turns": (profile.model_calls + 1) // 2,
        "unpriced_calls": _ratio_count(profile, "unpriced_calls", minimum=2),
    }


def _range_histogram_count(items: list[dict[str, Any]]) -> int:
    return sum(int(item["count"]) for item in items)


def _exact_histogram_totals(
    items: list[dict[str, Any]],
    *,
    name: str,
) -> tuple[int, int]:
    values = [int(item["value"]) for item in items]
    if len(values) != len(set(values)):
        raise ValueError(f"{name} histogram contains duplicate values")
    count = sum(int(item["count"]) for item in items)
    weighted = sum(int(item["count"]) * int(item["value"]) for item in items)
    return count, weighted


def validate_production_shape(payload: dict[str, Any]) -> None:
    """Validate aggregate-only production shape and cross-field semantics."""

    schema = _object(_PRODUCTION_SHAPE_SCHEMA_PATH)
    try:
        Draft202012Validator(schema).validate(payload)
    except ValidationError as exc:
        raise ValueError(f"production shape schema: {exc.message}") from exc

    source = payload["source_shape"]
    if sum(source["source_kind_counts"].values()) != source["total_files"]:
        raise ValueError("source kind counts do not equal total_files")
    if _range_histogram_count(source["age_buckets"]) != source["total_files"]:
        raise ValueError("source age histogram does not equal total_files")

    storage = payload["storage_shape"]
    if storage["database_bytes"] != storage["table_bytes"] + storage["index_bytes"]:
        raise ValueError("storage bytes do not reconcile")

    timings = payload["phase_timings_us"]
    if timings["total"] != sum(
        value for key, value in timings.items() if key != "total"
    ):
        raise ValueError("phase timing total does not reconcile")

    cardinality = payload["cardinality"]
    histograms = payload["cardinality_histograms"]
    call_sessions, calls = _exact_histogram_totals(
        histograms["calls_per_session"],
        name="calls_per_session",
    )
    tool_sessions, tools = _exact_histogram_totals(
        histograms["tools_per_session"],
        name="tools_per_session",
    )
    projects, resources = _exact_histogram_totals(
        histograms["resources_per_project"],
        name="resources_per_project",
    )
    if call_sessions != cardinality["sessions"] or calls != cardinality["model_calls"]:
        raise ValueError("calls_per_session histogram does not reconcile")
    if tool_sessions != cardinality["sessions"] or tools != cardinality["tools"]:
        raise ValueError("tools_per_session histogram does not reconcile")
    if projects != 1 or resources != cardinality["resources"]:
        raise ValueError("resources_per_project histogram does not reconcile")

    contract = payload["generation_contract"]
    distribution = contract["distribution"]
    if contract["model_calls"] != cardinality["model_calls"]:
        raise ValueError("generation model_calls do not match cardinality")
    if contract["source_manifestations"] != source["total_files"]:
        raise ValueError("generation source_manifestations do not match source shape")
    for key in (
        "activities",
        "model_calls",
        "sessions",
        "state_changes",
        "tool_invocations",
        "turns",
    ):
        cardinality_key = "tools" if key == "tool_invocations" else key
        if distribution[key] != cardinality[cardinality_key]:
            raise ValueError(f"generation distribution differs for {key}")

    allowance = payload["allowance_shape"]
    if distribution["allowance_observations"] != allowance["observations"]:
        raise ValueError("allowance observation counts do not reconcile")
    if not (
        allowance["repeated_observations"] <= allowance["observations"]
        and allowance["reset_boundaries"] < allowance["cycles"]
    ):
        raise ValueError("allowance repetition/reset counts are invalid")

    expected = contract["expected_stream_aggregates"]
    required_equal = {
        "allowance_observations": distribution["allowance_observations"],
        "canonical_model_calls": distribution["model_calls"],
        "model_call_occurrences": (
            distribution["model_calls"] + distribution["duplicate_call_occurrences"]
        ),
        "resources": cardinality["resources"],
        "source_manifestations": contract["source_manifestations"],
        "tool_invocations": distribution["tool_invocations"],
    }
    for key, value in required_equal.items():
        if expected[key] != value:
            raise ValueError(f"expected stream aggregate differs for {key}")
    if expected["allowance_repeated_observations"] != allowance[
        "repeated_observations"
    ]:
        raise ValueError("allowance repeated observations do not reconcile")
    if expected["allowance_reset_boundaries"] != allowance["reset_boundaries"]:
        raise ValueError("allowance reset boundaries do not reconcile")
    if expected["open_tool_invocations"] > expected["tool_invocations"]:
        raise ValueError("open tool count exceeds tool invocations")

    capabilities = payload["authorized_capability_counts"]
    capability_limits = {
        "allowance_observation": distribution["allowance_observations"],
        "model_call_usage": distribution["model_calls"],
        "session_hierarchy": distribution["sessions"],
        "state_change_observation": distribution["state_changes"],
        "tool_lifecycle": distribution["tool_invocations"],
        "valuation": distribution["model_calls"],
    }
    for key, limit in capability_limits.items():
        if capabilities[key] > limit:
            raise ValueError(f"authorized capability count exceeds {key} facts")


def load_production_shape() -> dict[str, Any]:
    """Load the aggregate-only production shape driving production fixtures."""

    payload = _object(_PRODUCTION_SHAPE_PATH)
    validate_production_shape(payload)
    return payload


def validate_production_aggregates(
    shape: dict[str, Any],
    actual: dict[str, int],
) -> None:
    """Fail when streamed fixture aggregates differ from the frozen shape."""

    expected = shape["generation_contract"]["expected_stream_aggregates"]
    if set(actual) != set(expected):
        raise ValueError(
            "stream aggregate keys differ: "
            f"missing={sorted(set(expected) - set(actual))}, "
            f"extra={sorted(set(actual) - set(expected))}"
        )
    for key in sorted(expected):
        if actual[key] != expected[key]:
            raise ValueError(
                f"stream aggregate {key} differs: "
                f"expected={expected[key]}, actual={actual[key]}"
            )
