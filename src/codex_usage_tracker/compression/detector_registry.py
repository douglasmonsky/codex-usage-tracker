"""Stable registry for Compression Lab detector families."""

from __future__ import annotations

from collections.abc import Iterable

from codex_usage_tracker.compression.context_detectors import (
    CacheBreakResumeDetector,
    StaleContextDetector,
)
from codex_usage_tracker.compression.detector_protocol import CompressionDetector
from codex_usage_tracker.compression.output_detectors import ToolOutputBloatDetector
from codex_usage_tracker.compression.repetition_detectors import (
    FileRediscoveryDetector,
    ShellRetryDetector,
    ValidationRepetitionDetector,
)

DETECTOR_SET_VERSION = "compression-detectors-v1"
DETECTOR_FAMILIES = (
    "stale_context",
    "cache_break_resume",
    "file_rediscovery",
    "shell_retry",
    "validation_repetition",
    "tool_output_bloat",
)


def default_detectors() -> tuple[CompressionDetector, ...]:
    return (
        StaleContextDetector(),
        CacheBreakResumeDetector(),
        FileRediscoveryDetector(),
        ShellRetryDetector(),
        ValidationRepetitionDetector(),
        ToolOutputBloatDetector(),
    )


def select_detectors(families: Iterable[str] | None) -> tuple[CompressionDetector, ...]:
    detectors = default_detectors()
    if families is None:
        return detectors
    requested = set(families)
    unknown = requested.difference(DETECTOR_FAMILIES)
    if unknown:
        raise ValueError(f"unknown compression detector families: {sorted(unknown)}")
    return tuple(detector for detector in detectors if detector.family in requested)
