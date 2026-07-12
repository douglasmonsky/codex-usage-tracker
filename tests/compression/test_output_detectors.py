from __future__ import annotations

from codex_usage_tracker.compression.detector_registry import (
    DETECTOR_FAMILIES,
    default_detectors,
)
from codex_usage_tracker.compression.models import CompressionScope
from codex_usage_tracker.compression.output_detectors import ToolOutputBloatDetector
from tests.compression.compression_helpers import call, snapshot, tool


def test_tool_output_bloat_claims_only_bounded_tool_output() -> None:
    evidence = snapshot(
        calls=(call("call-1", output=50),),
        tools=(tool("tool-large", "call-1", output_bytes=4_000),),
    )

    candidates = ToolOutputBloatDetector(min_output_tokens=500).detect(
        evidence,
        CompressionScope(),
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.family == "tool_output_bloat"
    assert candidate.observed_exposure.tool_output == 1_000
    assert candidate.claims[0].component == "tool_output"
    assert candidate.claims[0].exposure_tokens == 1_000
    assert candidate.observed_exposure.uncached_input == 0
    assert candidate.confidence_grade == "medium"


def test_tool_output_detector_deduplicates_and_ignores_small_outputs() -> None:
    small = tool("tool-small", "call-1", output_bytes=200)
    evidence = snapshot(calls=(call("call-1"),), tools=(small, small))

    assert (
        ToolOutputBloatDetector(min_output_tokens=500).detect(
            evidence,
            CompressionScope(),
        )
        == []
    )


def test_default_detector_registry_has_stable_order() -> None:
    assert DETECTOR_FAMILIES == (
        "stale_context",
        "cache_break_resume",
        "file_rediscovery",
        "shell_retry",
        "validation_repetition",
        "tool_output_bloat",
    )
    assert tuple(detector.family for detector in default_detectors()) == DETECTOR_FAMILIES
