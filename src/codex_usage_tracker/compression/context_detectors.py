"""Detectors for stale context and cache-break resume overhead."""

from __future__ import annotations

from dataclasses import dataclass

from codex_usage_tracker.compression.detector_protocol import build_candidate
from codex_usage_tracker.compression.evidence import CallEvidence, CompressionEvidenceSnapshot
from codex_usage_tracker.compression.models import CandidateDraft, CompressionScope


@dataclass(frozen=True, slots=True)
class StaleContextDetector:
    family = "stale_context"
    version = "stale-context-v1"

    min_uncached_input_tokens: int = 20_000
    max_output_tokens: int = 1_500
    min_context_window_percent: float = 0.35

    def detect(
        self,
        snapshot: CompressionEvidenceSnapshot,
        scope: CompressionScope,
    ) -> list[CandidateDraft]:
        candidates: list[CandidateDraft] = []
        for call in snapshot.calls:
            if not self._qualifies(call):
                continue
            confidence_score = 0.82 if call.context_window_percent >= 0.7 else 0.68
            candidates.append(
                build_candidate(
                    snapshot=snapshot,
                    scope=scope,
                    family=self.family,
                    pattern="Large context exposure with little downstream output",
                    pattern_key=f"record:{call.record_id}",
                    detector_version=self.version,
                    claims=((call.record_id, "uncached_input", call.exposure.uncached_input),),
                    observation_count=1,
                    confidence_grade="high" if confidence_score >= 0.8 else "medium",
                    confidence_score=confidence_score,
                    confidence_reasons=(
                        "uncached input exceeded the stale-context threshold",
                        "downstream output remained comparatively small",
                    ),
                    evidence_handles=(
                        {
                            "record_id": call.record_id,
                            "uncached_input_tokens": call.exposure.uncached_input,
                            "output_tokens": call.exposure.output,
                            "context_window_percent": call.context_window_percent,
                        },
                    ),
                    intervention={
                        "family": "fresh_thread_handoff",
                        "action": "Start a focused thread with a compact handoff before continuing.",
                    },
                    verification={
                        "metric": "uncached_input_tokens",
                        "expected_direction": "decrease",
                    },
                    first_seen=call.event_timestamp,
                    last_seen=call.event_timestamp,
                )
            )
        return candidates

    def _qualifies(self, call: CallEvidence) -> bool:
        exposure = call.exposure
        return all(
            (
                exposure.uncached_input >= self.min_uncached_input_tokens,
                exposure.output <= self.max_output_tokens,
                call.context_window_percent >= self.min_context_window_percent,
            )
        )


@dataclass(frozen=True, slots=True)
class CacheBreakResumeDetector:
    family = "cache_break_resume"
    version = "cache-break-resume-v1"

    min_uncached_input_tokens: int = 10_000
    max_cache_ratio: float = 0.5
    min_previous_cache_ratio: float = 0.7

    def detect(
        self,
        snapshot: CompressionEvidenceSnapshot,
        scope: CompressionScope,
    ) -> list[CandidateDraft]:
        calls = {call.record_id: call for call in snapshot.calls}
        candidates = (
            _cache_break_candidate(
                detector=self,
                snapshot=snapshot,
                scope=scope,
                call=call,
                previous=calls.get(call.previous_record_id or ""),
            )
            for call in snapshot.calls
        )
        return [candidate for candidate in candidates if candidate is not None]

    def _qualifies(self, call: CallEvidence, previous: CallEvidence | None) -> bool:
        if previous is None:
            return False
        return all(
            (
                previous.thread_key == call.thread_key,
                previous.cache_ratio >= self.min_previous_cache_ratio,
                call.cache_ratio <= self.max_cache_ratio,
                call.exposure.uncached_input >= self.min_uncached_input_tokens,
            )
        )


def _cache_break_candidate(
    *,
    detector: CacheBreakResumeDetector,
    snapshot: CompressionEvidenceSnapshot,
    scope: CompressionScope,
    call: CallEvidence,
    previous: CallEvidence | None,
) -> CandidateDraft | None:
    if not detector._qualifies(call, previous):
        return None
    assert previous is not None
    return build_candidate(
        snapshot=snapshot,
        scope=scope,
        family=detector.family,
        pattern="Warm thread resumed with a sharp cache-reuse drop",
        pattern_key=f"resume:{call.record_id}",
        detector_version=detector.version,
        claims=((call.record_id, "uncached_input", call.exposure.uncached_input),),
        observation_count=1,
        confidence_grade="high",
        confidence_score=0.84,
        confidence_reasons=(
            "the preceding call had high cache reuse",
            "the resumed call had low cache reuse and high uncached input",
        ),
        evidence_handles=(
            {
                "record_id": call.record_id,
                "previous_record_id": previous.record_id,
                "cache_ratio": call.cache_ratio,
                "previous_cache_ratio": previous.cache_ratio,
            },
        ),
        intervention={
            "family": "resume_handoff",
            "action": "Use a compact handoff instead of reviving a cold thread.",
        },
        verification={
            "metric": "cache_ratio",
            "expected_direction": "increase",
        },
        first_seen=call.event_timestamp,
        last_seen=call.event_timestamp,
    )
