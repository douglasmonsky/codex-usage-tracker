from __future__ import annotations

import json

import pytest

from codex_usage_tracker.parser.otel import OTEL_DIAGNOSTIC_KEYS, parse_otlp_json_line
from tests.otel_helpers import completion_attributes, synthetic_otlp_line


def test_parse_otlp_batch_extracts_only_completion_allowlist() -> None:
    raw = synthetic_otlp_line(
        attributes={
            "event.name": "codex.sse_event",
            "event.kind": "response.completed",
            "conversation.id": "synthetic-conversation",
            "input_token_count": 120,
            "cached_token_count": 40,
            "output_token_count": 30,
            "reasoning_token_count": 10,
            "model": "gpt-5.6-sol",
            "model_reasoning_effort": "high",
            "service_tier": "priority",
            "app.version": "0.143.0",
            "secret.attribute": "must-not-survive",
        },
        body="synthetic private body that must not survive",
    )

    result = parse_otlp_json_line(raw)

    assert len(result.completions) == 1
    completion = result.completions[0]
    assert completion.conversation_id == "synthetic-conversation"
    assert completion.service_tier == "priority"
    assert completion.fast == 1
    assert completion.service_tier_source == "otel_response_completed"
    assert completion.service_tier_confidence == "exact"
    assert completion.match_status == "pending"
    assert "private body" not in repr(completion)
    assert "secret.attribute" not in repr(completion)


@pytest.mark.parametrize(
    ("version", "tier", "fast", "confidence", "status"),
    [
        ("0.143.0", "standard", 0, "protocol", "pending"),
        ("0.142.9", None, None, None, "invalid"),
        ("bad", None, None, None, "invalid"),
    ],
)
def test_missing_service_tier_uses_versioned_protocol_semantics(
    version: str,
    tier: str | None,
    fast: int | None,
    confidence: str | None,
    status: str,
) -> None:
    result = parse_otlp_json_line(
        synthetic_otlp_line(
            attributes=completion_attributes(app_version=version, service_tier=None)
        )
    )

    completion = result.completions[0]
    assert (completion.service_tier, completion.fast, completion.service_tier_confidence) == (
        tier,
        fast,
        confidence,
    )
    assert completion.match_status == status


@pytest.mark.parametrize(
    ("raw_tier", "normalized_tier", "fast"),
    [
        ("priority", "priority", 1),
        ("fast", "fast", 1),
        ("default", "default", 0),
        ("standard", "standard", 0),
        ("flex", "flex", 0),
        ("batch", "batch", 0),
    ],
)
def test_explicit_tier_names_are_preserved(
    raw_tier: str, normalized_tier: str, fast: int
) -> None:
    attributes = completion_attributes(service_tier=raw_tier)

    completion = parse_otlp_json_line(
        synthetic_otlp_line(attributes=attributes)
    ).completions[0]

    assert (completion.service_tier, completion.fast) == (normalized_tier, fast)


def test_multiple_resource_and_scope_groups_are_traversed() -> None:
    first = json.loads(
        synthetic_otlp_line(attributes=completion_attributes(conversation_id="a"))
    )
    second = json.loads(
        synthetic_otlp_line(attributes=completion_attributes(conversation_id="b"))
    )
    first["resourceLogs"].extend(second["resourceLogs"])

    result = parse_otlp_json_line(json.dumps(first))

    assert [item.conversation_id for item in result.completions] == ["a", "b"]


@pytest.mark.parametrize("raw", ["{", "[]", json.dumps({"resourceLogs": "bad"})])
def test_malformed_payloads_return_bounded_diagnostics(raw: str) -> None:
    result = parse_otlp_json_line(raw)

    assert not result.completions
    assert sum(result.diagnostics.values()) >= 1
    assert set(result.diagnostics) <= set(OTEL_DIAGNOSTIC_KEYS)


def test_non_completion_and_missing_identity_never_become_pending_matches() -> None:
    unrelated = completion_attributes()
    unrelated["event.kind"] = "response.created"
    missing_identity = completion_attributes()
    missing_identity.pop("conversation.id")

    assert not parse_otlp_json_line(
        synthetic_otlp_line(attributes=unrelated)
    ).completions
    completion = parse_otlp_json_line(
        synthetic_otlp_line(attributes=missing_identity)
    ).completions[0]
    assert completion.match_status == "invalid"


def test_present_invalid_tier_is_not_treated_as_protocol_omission() -> None:
    attributes = completion_attributes(service_tier=None)
    attributes["service_tier"] = 7

    result = parse_otlp_json_line(synthetic_otlp_line(attributes=attributes))

    completion = result.completions[0]
    assert (completion.service_tier, completion.fast) == (None, None)
    assert completion.match_status == "invalid"
    assert result.diagnostics["otel_invalid_record"] >= 1


def test_semantic_fingerprint_is_stable_and_changes_with_aggregate_identity() -> None:
    attributes = completion_attributes()
    reversed_attributes = dict(reversed(list(attributes.items())))
    changed_attributes = completion_attributes(tokens=(121, 40, 30, 10))

    first = parse_otlp_json_line(
        synthetic_otlp_line(attributes=attributes)
    ).completions[0]
    reordered = parse_otlp_json_line(
        synthetic_otlp_line(attributes=reversed_attributes)
    ).completions[0]
    changed = parse_otlp_json_line(
        synthetic_otlp_line(attributes=changed_attributes)
    ).completions[0]

    assert first.fingerprint == reordered.fingerprint
    assert first.fingerprint != changed.fingerprint
