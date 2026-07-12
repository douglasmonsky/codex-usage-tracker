"""Detector for large tool outputs with weak downstream yield."""

from __future__ import annotations

from dataclasses import dataclass

from codex_usage_tracker.compression.detector_protocol import build_candidate
from codex_usage_tracker.compression.evidence import (
    CallEvidence,
    CompressionEvidenceSnapshot,
    ToolCallEvidence,
)
from codex_usage_tracker.compression.models import CandidateDraft, CompressionScope


@dataclass(frozen=True, slots=True)
class ToolOutputBloatDetector:
    family = "tool_output_bloat"
    version = "tool-output-bloat-v1"

    min_output_tokens: int = 4_096

    def detect(
        self,
        snapshot: CompressionEvidenceSnapshot,
        scope: CompressionScope,
    ) -> list[CandidateDraft]:
        calls = {call.record_id: call for call in snapshot.calls}
        unique_tools = {row.tool_call_key: row for row in snapshot.tool_calls}
        candidates = (
            _tool_output_candidate(
                detector=self,
                snapshot=snapshot,
                scope=scope,
                tool_call=tool_call,
                call=calls.get(tool_call.record_id),
            )
            for tool_call in unique_tools.values()
        )
        return [candidate for candidate in candidates if candidate is not None]


def _tool_output_candidate(
    *,
    detector: ToolOutputBloatDetector,
    snapshot: CompressionEvidenceSnapshot,
    scope: CompressionScope,
    tool_call: ToolCallEvidence,
    call: CallEvidence | None,
) -> CandidateDraft | None:
    output_tokens = (tool_call.output_size_bytes + 3) // 4
    if output_tokens < detector.min_output_tokens:
        return None
    low_yield = _is_low_yield(call, output_tokens)
    confidence_grade, confidence_score = _confidence(low_yield)
    return build_candidate(
        snapshot=snapshot,
        scope=scope,
        family=detector.family,
        pattern="Large tool output produced limited downstream response",
        pattern_key=f"tool:{tool_call.tool_call_key}",
        detector_version=detector.version,
        claims=((tool_call.record_id, "tool_output", output_tokens),),
        observation_count=1,
        confidence_grade=confidence_grade,
        confidence_score=confidence_score,
        confidence_reasons=(
            "tool output exceeded the configured size threshold",
            _yield_reason(low_yield),
        ),
        evidence_handles=(
            {
                "tool_call_key": tool_call.tool_call_key,
                "tool_name": tool_call.tool_name,
                "output_tokens": output_tokens,
            },
        ),
        intervention={
            "family": "bounded_tool_output",
            "action": "Use targeted queries, limits, or summarized tool output.",
        },
        verification={
            "metric": "tool_output_tokens",
            "expected_direction": "decrease",
        },
        first_seen=_event_timestamp(call),
        last_seen=_event_timestamp(call),
        data_quality_warnings=_quality_warnings(low_yield),
    )


def _is_low_yield(call: CallEvidence | None, output_tokens: int) -> bool:
    return call is not None and call.exposure.output <= max(200, output_tokens // 10)


def _confidence(low_yield: bool) -> tuple[str, float]:
    return ("medium", 0.7) if low_yield else ("low", 0.48)


def _yield_reason(low_yield: bool) -> str:
    if low_yield:
        return "downstream response was small relative to tool output"
    return "downstream reuse could not be established"


def _quality_warnings(low_yield: bool) -> tuple[str, ...]:
    if low_yield:
        return ()
    return ("downstream reuse of the tool output is unknown",)


def _event_timestamp(call: CallEvidence | None) -> str | None:
    return call.event_timestamp if call is not None else None
