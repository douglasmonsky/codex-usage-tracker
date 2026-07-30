"""Invariant tests for the CK-07 synthetic performance harness.

Timing assertions intentionally live in the emitted qualification evidence;
shared CI validates the execution paths and bounded result shape instead.
"""

from scripts.benchmark_ck07_publication import run_benchmark


def test_synthetic_benchmark_exercises_all_required_tail_shapes() -> None:
    result = run_benchmark(repetitions=1)

    assert result["synthetic_only"] is True
    assert result["concurrent_reader_available"] is True
    assert set(result["scenarios"]) == {
        "no_change",
        "one_call",
        "one_tool_lifecycle_completion",
        "thirty_two_calls",
        "forced_unsafe_two_thousand_writer",
        "two_thousand_large_path_promotion",
    }
    assert result["planner_classes"] == {
        "thirty_two_calls": "append_safe_small",
        "two_thousand_calls": "append_safe_large",
    }
    unsafe = result["scenarios"]["forced_unsafe_two_thousand_writer"]
    assert unsafe["planner_rejected_for_short_writer"] is True
    assert unsafe["inserted_occurrences"] == 2_000
    assert "p95_ms" in result["scenarios"]["two_thousand_large_path_promotion"]["activation"]
