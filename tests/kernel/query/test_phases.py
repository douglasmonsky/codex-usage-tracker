from __future__ import annotations

from codex_usage_tracker.kernel.query.phases import (
    PHASE_SEGMENTER_VERSION,
    ActivityFact,
    TokenFact,
    attribute_tokens,
    segment_phases,
)


def test_phase_segmenter_is_versioned_deterministic_and_has_unknown_fallback() -> None:
    facts = (
        ActivityFact("2026-01-01T00:00:00Z", "skill", "turn-1"),
        ActivityFact("2026-01-01T00:00:01Z", "patch", "turn-1"),
        ActivityFact("2026-01-01T00:00:02Z", "unmapped", "turn-1"),
        ActivityFact("2026-01-01T00:00:03Z", "compaction", "turn-1"),
    )

    first = segment_phases(facts)
    second = segment_phases(tuple(reversed(facts)))

    assert PHASE_SEGMENTER_VERSION == 1
    assert first == second
    assert [segment.category for segment in first] == [
        "planning_reasoning",
        "implementation",
        "unknown",
        "compaction_recovery",
    ]
    assert all(segment.basis == "activity_event" for segment in first)
    assert all(segment.confidence in {"high", "medium", "unknown"} for segment in first)


def test_phase_segmenter_classifies_tools_and_attributes_four_token_classes() -> None:
    segments = segment_phases(
        (
            ActivityFact(
                "2026-01-01T00:00:00Z",
                "user_input",
                "turn-1",
                activity_event_id="a0",
            ),
            ActivityFact(
                "2026-01-01T00:00:01Z",
                "tool",
                "turn-1",
                activity_event_id="a1",
                safe_label="rg",
            ),
            ActivityFact(
                "2026-01-01T00:00:02Z",
                "tool",
                "turn-1",
                activity_event_id="a2",
                safe_label="pytest",
            ),
            ActivityFact(
                "2026-01-01T00:00:03Z",
                "task",
                "turn-1",
                activity_event_id="a3",
            ),
        )
    )

    attributed = attribute_tokens(
        segments,
        (
            TokenFact(
                "2026-01-01T00:00:01.500Z",
                "turn-1",
                input_tokens=100,
                cached_input_tokens=60,
                reasoning_tokens=7,
                output_tokens=11,
            ),
            TokenFact(
                "2026-01-01T00:00:02.500Z",
                "turn-1",
                input_tokens=40,
                cached_input_tokens=10,
                reasoning_tokens=3,
                output_tokens=5,
            ),
        ),
    )

    assert [segment.category for segment in attributed] == [
        "user_input",
        "discovery",
        "verification",
        "delivery",
    ]
    assert attributed[1].uncached_input_tokens == 40
    assert attributed[1].cached_input_tokens == 60
    assert attributed[1].reasoning_tokens == 7
    assert attributed[1].output_tokens == 11
    assert attributed[1].token_attribution == "deterministic"
    assert attributed[2].total_tokens == 45


def test_ambiguous_exec_wrapper_is_not_invented_as_implementation() -> None:
    segment = segment_phases(
        (
            ActivityFact(
                "2026-01-01T00:00:00Z",
                "tool",
                "turn-1",
                safe_label="functions.exec_command",
            ),
        )
    )[0]

    assert segment.category == "unknown"
    assert segment.confidence == "unknown"
