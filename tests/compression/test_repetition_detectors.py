from __future__ import annotations

from codex_usage_tracker.compression.models import CompressionScope
from codex_usage_tracker.compression.repetition_detectors import (
    FileRediscoveryDetector,
    ShellRetryDetector,
    ValidationRepetitionDetector,
)
from tests.compression.compression_helpers import (
    call,
    command,
    file_event,
    fragment,
    snapshot,
)


def test_file_rediscovery_uses_fragment_exposure_not_whole_call_tokens() -> None:
    calls = tuple(call(f"call-{index}", index=index) for index in range(1, 4))
    files = tuple(file_event(f"file-{index}", f"call-{index}") for index in range(1, 4))
    fragments = tuple(
        fragment(f"fragment-{index}", f"call-{index}", size_bytes=400) for index in range(1, 4)
    )

    candidates = FileRediscoveryDetector(min_occurrences=3).detect(
        snapshot(calls=calls, files=files, fragments=fragments),
        CompressionScope(),
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.family == "file_rediscovery"
    assert candidate.observed_exposure.content_fragment == 300
    assert candidate.observed_exposure.uncached_input == 0
    assert {claim.component for claim in candidate.claims} == {"content_fragment"}
    assert candidate.evidence_handles[0]["path_hash"] == "hash-a"


def test_file_rediscovery_requires_indexed_fragment_exposure() -> None:
    calls = tuple(call(f"call-{index}", index=index) for index in range(1, 4))
    files = tuple(file_event(f"file-{index}", f"call-{index}") for index in range(1, 4))

    assert (
        FileRediscoveryDetector(min_occurrences=3).detect(
            snapshot(calls=calls, files=files),
            CompressionScope(),
        )
        == []
    )


def test_file_rediscovery_does_not_multiply_one_turns_fragment_exposure() -> None:
    evidence = snapshot(
        calls=(call("call-1"),),
        files=tuple(file_event(f"file-{index}", "call-1") for index in range(3)),
        fragments=(fragment("fragment-1", "call-1", size_bytes=400),),
    )

    candidates = FileRediscoveryDetector(min_occurrences=3).detect(
        evidence,
        CompressionScope(),
    )

    assert len(candidates) == 1
    assert candidates[0].observation_count == 3
    assert candidates[0].observed_exposure.content_fragment == 100


def test_shell_retry_deduplicates_event_keys_and_claims_command_output() -> None:
    calls = tuple(call(f"call-{index}", index=index) for index in range(1, 4))
    commands = tuple(
        command(f"command-{index}", f"call-{index}", "rg", retry_group="retry-a")
        for index in range(1, 4)
    )
    evidence = snapshot(calls=calls, commands=(*commands, commands[-1]))

    candidates = ShellRetryDetector(min_occurrences=3).detect(
        evidence,
        CompressionScope(),
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.family == "shell_retry"
    assert candidate.observation_count == 3
    assert candidate.observed_exposure.tool_output == 300
    assert len(candidate.claims) == 3


def test_validation_repetition_is_separate_and_overlap_ready() -> None:
    calls = tuple(call(f"call-{index}", index=index) for index in range(1, 4))
    commands = tuple(command(f"pytest-{index}", f"call-{index}", "pytest") for index in range(1, 4))

    candidates = ValidationRepetitionDetector(min_occurrences=3).detect(
        snapshot(calls=calls, commands=commands),
        CompressionScope(),
    )

    assert len(candidates) == 1
    assert candidates[0].family == "validation_repetition"
    assert candidates[0].intervention["family"] == "validation_checkpoint"
    assert {claim.component for claim in candidates[0].claims} == {"tool_output"}
