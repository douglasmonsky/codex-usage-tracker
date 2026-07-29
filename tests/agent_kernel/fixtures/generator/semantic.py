from __future__ import annotations

from typing import Any

from tests.agent_kernel.contracts.reference.identity import semantic_id
from tests.agent_kernel.fixtures.generator.profile import FixtureProfile

_DAY_US = 86_400_000_000
_OPERATIONS = (
    "read",
    "search",
    "execute",
    "write",
    "test",
    "delegate",
    "wait",
    "unknown",
)


def selected(ordinal: int, total: int, count: int) -> bool:
    """Select an exact, evenly distributed number of ordinals."""

    if not 0 <= ordinal < total:
        raise ValueError("ordinal is outside the source domain")
    if not 0 <= count <= total:
        raise ValueError("selection count is outside the source domain")
    return (ordinal + 1) * count // total > ordinal * count // total


def selection_rank(ordinal: int, total: int, count: int) -> int:
    """Return the zero-based rank of a selected ordinal."""

    if not selected(ordinal, total, count):
        raise ValueError("ordinal is not selected")
    return (ordinal + 1) * count // total - 1


def event_at_us(profile: FixtureProfile, ordinal: int, *, late: bool = False) -> int:
    """Spread calls across the declared history with deliberate timestamp ties."""

    turns = (profile.model_calls + 1) // 2
    turn_ordinal = ordinal // 2
    span = profile.history_days * _DAY_US
    observed = profile.start_at_us + turn_ordinal * span // max(1, turns)
    return observed - 5_000_000 if late else observed


def history_windows(
    profile: FixtureProfile,
    *,
    late_event_count: int,
) -> dict[str, dict[str, Any]]:
    """Return exact named windows anchored to emitted integer timestamps."""

    tail_start = max(0, profile.model_calls - 4)
    end_us = max(
        event_at_us(
            profile,
            ordinal,
            late=selected(ordinal, profile.model_calls, late_event_count),
        )
        for ordinal in range(tail_start, profile.model_calls)
    )
    latest_session_ordinal = (profile.model_calls - 1) // 10
    latest_session_start = latest_session_ordinal * 10
    windows: dict[str, dict[str, Any]] = {
        "current_session": {
            "end_us": end_us,
            "session_id": session_id(profile, latest_session_ordinal),
            "start_us": event_at_us(profile, latest_session_start),
        }
    }
    for name, days in (
        ("24_hours", 1),
        ("7_days", 7),
        ("30_days", 30),
        ("90_days", 90),
        ("one_year", 365),
    ):
        windows[name] = {
            "end_us": end_us,
            "start_us": end_us - days * _DAY_US,
        }
    windows["all_time"] = {
        "end_us": end_us,
        "start_us": event_at_us(
            profile,
            0,
            late=selected(0, profile.model_calls, late_event_count),
        ),
    }
    return windows


def project_id(profile: FixtureProfile) -> str:
    return semantic_id("project", ["synthetic-workspace", profile.seed])


def session_id(profile: FixtureProfile, session_ordinal: int) -> str:
    return semantic_id(
        "session",
        ["codex", "synthetic-jsonl-v1", f"session-{session_ordinal:08d}", "v1"],
    )


def turn_id(profile: FixtureProfile, turn_ordinal: int) -> str:
    session_ordinal = (turn_ordinal * 2) // 10
    return semantic_id(
        "turn",
        [session_id(profile, session_ordinal), turn_ordinal % 5],
    )


def call_id(profile: FixtureProfile, ordinal: int) -> str:
    return semantic_id(
        "call",
        [session_id(profile, ordinal // 10), f"call-{ordinal:09d}"],
    )


def tool_id(profile: FixtureProfile, ordinal: int) -> str:
    return semantic_id(
        "tool",
        [session_id(profile, ordinal // 10), f"tool-{ordinal:09d}"],
    )


def resource_id(profile: FixtureProfile, ordinal: int) -> str:
    return semantic_id(
        "resource",
        [project_id(profile), "file", f"synthetic/resource-{ordinal % 31:02d}"],
    )


def state_change_id(profile: FixtureProfile, ordinal: int) -> str:
    return semantic_id(
        "state-change",
        [resource_id(profile, ordinal), event_at_us(profile, ordinal), ordinal],
    )


def call_tokens(
    profile: FixtureProfile,
    ordinal: int,
    *,
    missing_cached: bool,
) -> dict[str, int | None]:
    """Return structural usage counters without any content body."""

    return {
        "uncached_input_tokens": 100 + (profile.seed + ordinal * 17) % 900,
        "cached_input_tokens": (
            None if missing_cached else 200 + (profile.seed + ordinal * 29) % 4_800
        ),
        "reasoning_tokens": (profile.seed + ordinal * 11) % 700,
        "output_tokens": 50 + (profile.seed + ordinal * 7) % 950,
    }


def model_call_record(
    profile: FixtureProfile,
    ordinal: int,
    *,
    missing_cached: bool,
    late: bool,
    unpriced: bool,
) -> dict[str, Any]:
    event_at = event_at_us(profile, ordinal, late=late)
    turn_ordinal = ordinal // 2
    return {
        "event_at_us": event_at,
        "event_kind_order": 30,
        "payload": {
            "call_id": call_id(profile, ordinal),
            "context_window_tokens": (
                None if ordinal % 100 == 0 else 128_000 + (ordinal % 3) * 64_000
            ),
            "model": "synthetic-unpriced" if unpriced else f"synthetic-model-{ordinal % 3}",
            "reasoning_effort": ("low", "medium", "high", None)[ordinal % 4],
            "session_id": session_id(profile, ordinal // 10),
            "tokens": call_tokens(
                profile,
                ordinal,
                missing_cached=missing_cached,
            ),
            "turn_id": turn_id(profile, turn_ordinal),
        },
        "source_order": ordinal * 10 + 3,
        "type": "model_call",
    }


def tool_records(
    profile: FixtureProfile,
    ordinal: int,
    *,
    tool_rank: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    event_at = event_at_us(profile, ordinal)
    identifier = tool_id(profile, ordinal)
    operation = _OPERATIONS[tool_rank % len(_OPERATIONS)]
    common = {
        "resource_id": resource_id(profile, ordinal),
        "semantic_operation": operation,
        "session_id": session_id(profile, ordinal // 10),
        "tool_id": identifier,
        "transport_name": f"synthetic_{operation}",
        "turn_id": turn_id(profile, ordinal // 2),
        "write_intent": operation in {"write", "execute"},
    }
    terminal_state = ("failed" if tool_rank % 10 == 8 else "cancelled" if tool_rank % 10 == 9 else "succeeded")
    return (
        {
            "event_at_us": event_at,
            "event_kind_order": 40,
            "payload": {**common, "state": "running"},
            "source_order": ordinal * 10 + 4,
            "type": "tool_start",
        },
        {
            "event_at_us": event_at + 1_000 + tool_rank % 997,
            "event_kind_order": 50,
            "payload": {
                **common,
                "duration_us": None if tool_rank % 10 == 9 else 1_000 + tool_rank % 50_000,
                "output_bytes": 64 + tool_rank % 16_384,
                "state": terminal_state,
            },
            "source_order": ordinal * 10 + 5,
            "type": "tool_terminal",
        },
    )


def state_change_record(profile: FixtureProfile, ordinal: int) -> dict[str, Any]:
    return {
        "event_at_us": event_at_us(profile, ordinal) + 2_500,
        "event_kind_order": 60,
        "payload": {
            "causal_attribution": None,
            "change_id": state_change_id(profile, ordinal),
            "change_kind": "content_revision",
            "preceding_activity_count": 2,
            "resource_id": resource_id(profile, ordinal),
            "session_id": session_id(profile, ordinal // 10),
            "turn_id": turn_id(profile, ordinal // 2),
        },
        "source_order": ordinal * 10 + 6,
        "type": "state_change",
    }


def activity_record(profile: FixtureProfile, ordinal: int) -> dict[str, Any]:
    return {
        "event_at_us": event_at_us(profile, ordinal) + 1_500,
        "event_kind_order": 55,
        "payload": {
            "activity_id": semantic_id(
                "activity",
                [session_id(profile, ordinal // 10), f"activity-{ordinal:09d}"],
            ),
            "activity_kind": "synthetic_phase",
            "session_id": session_id(profile, ordinal // 10),
            "state": "succeeded",
            "turn_id": turn_id(profile, ordinal // 2),
        },
        "source_order": ordinal * 10 + 5,
        "type": "activity",
    }


def compaction_record(profile: FixtureProfile, ordinal: int) -> dict[str, Any]:
    return {
        "event_at_us": event_at_us(profile, ordinal) + 500,
        "event_kind_order": 35,
        "payload": {
            "after_context_epoch": f"epoch-{ordinal + 1:09d}",
            "before_context_epoch": f"epoch-{ordinal:09d}",
            "compaction_id": semantic_id(
                "compaction",
                [session_id(profile, ordinal // 10), ordinal],
            ),
            "session_id": session_id(profile, ordinal // 10),
        },
        "source_order": ordinal * 10 + 4,
        "type": "compaction_boundary",
    }


def allowance_record(
    profile: FixtureProfile,
    ordinal: int,
    *,
    observation_rank: int,
) -> dict[str, Any]:
    cycle_ordinal = observation_rank // 100
    position = observation_rank % 100
    effective_position = position - 1 if position > 0 and position % 4 == 0 else position
    used_percent = min(100, effective_position)
    return {
        "event_at_us": event_at_us(profile, ordinal) + 3_000,
        "event_kind_order": 70,
        "payload": {
            "cycle_id": f"cycle-{cycle_ordinal:04d}",
            "limit_id": "weekly",
            "observation_ordinal": observation_rank,
            "plan_identity": "synthetic-plan",
            "provider": "openai",
            "remaining_percent": str(max(0, 100 - used_percent)),
            "reset_identity": f"reset-{cycle_ordinal:04d}",
            "used_percent": str(used_percent),
            "window_kind": "rolling_week",
        },
        "source_order": ordinal * 10 + 7,
        "type": "allowance_observation",
    }


def boundary_records(
    profile: FixtureProfile,
    ordinal: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    event_at = event_at_us(profile, ordinal)
    session_ordinal = ordinal // 10
    turn_ordinal = ordinal // 2
    session_start = None
    turn_start = None
    session_terminal = None
    if ordinal % 10 == 0:
        session_start = {
            "event_at_us": event_at,
            "event_kind_order": 10,
            "payload": {
                "parent_session_id": (
                    None
                    if session_ordinal == 0
                    else session_id(profile, max(0, session_ordinal // 3))
                ),
                "project_id": project_id(profile),
                "session_id": session_id(profile, session_ordinal),
                "state": "running",
            },
            "source_order": ordinal * 10 + 1,
            "type": "session_start",
        }
    if ordinal % 2 == 0:
        turn_start = {
            "event_at_us": event_at,
            "event_kind_order": 20,
            "payload": {
                "session_id": session_id(profile, session_ordinal),
                "state": "running",
                "turn_id": turn_id(profile, turn_ordinal),
            },
            "source_order": ordinal * 10 + 2,
            "type": "turn_start",
        }
    if ordinal % 10 == 9 and ordinal + 1 < profile.model_calls:
        session_terminal = {
            "event_at_us": event_at + 4_000,
            "event_kind_order": 80,
            "payload": {
                "completion_basis": "observed_terminal",
                "session_id": session_id(profile, session_ordinal),
                "state": ("failed" if session_ordinal % 11 == 10 else "succeeded"),
            },
            "source_order": ordinal * 10 + 8,
            "type": "session_terminal",
        }
    return session_start, turn_start, session_terminal
