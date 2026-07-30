from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from codex_usage_tracker.agent_kernel.domain.valuation import (
    RateCardFrontier,
    RateCardRevision,
    ValuationUnpricedReason,
    compile_current_valuation_matches,
)

_DIGEST = "sha256:" + "a" * 64


def _card(**updates: object) -> dict[str, object]:
    card: dict[str, object] = {
        "rate_card_id": "rate-card:synthetic",
        "digest": _DIGEST,
        "predecessor_digest": None,
        "effective_at_us": 0,
        "fetched_at_us": 999,
        "source_name": "synthetic",
        "source_url": None,
        "currency": "USD",
        "model_match_rules": [
            {
                "model_profile_id": "profile:exact",
                "match_basis": "exact_model_profile",
            },
            {
                "model_aliases": ["synthetic-alias"],
                "match_basis": "model_alias",
            },
        ],
        "four_class_rates": {
            "uncached_input_tokens": "1.25",
            "cached_input_tokens": "0.125",
            "reasoning_tokens": "2",
            "output_tokens": "10",
        },
        "credit_rates": {
            "uncached_input_tokens": "2",
            "cached_input_tokens": "0.2",
            "reasoning_tokens": "3",
            "output_tokens": "4",
        },
        "reasoning_in_output": False,
        "confidence": "synthetic",
        "validation_status": "valid",
    }
    card.update(updates)
    return card


def _frontier(card: object | None, *, head_digest: str = _DIGEST) -> dict[str, object]:
    return {
        "head_digest": head_digest,
        "revisions": [] if card is None else [card],
    }


def _profiles() -> list[dict[str, object]]:
    return [
        {
            "model_profile_id": "profile:alias",
            "model": "synthetic-alias",
            "reasoning_effort": "high",
            "service_tier": "priority",
        },
        {
            "model_profile_id": "profile:exact",
            "model": "synthetic-exact",
            "reasoning_effort": "medium",
            "service_tier": "standard",
        },
    ]


def _call(call_id: str, profile_id: str = "profile:exact", **tokens: object) -> dict[str, object]:
    call: dict[str, object] = {
        "call_id": call_id,
        "event_at_us": 100,
        "model_profile_id": profile_id,
        "uncached_input_tokens": 1,
        "cached_input_tokens": 2,
        "reasoning_tokens": 3,
        "output_tokens": 4,
    }
    call.update(tokens)
    return call


def test_compiles_exact_decimal_values_in_deterministic_call_order() -> None:
    matches = compile_current_valuation_matches(
        [_call("call:z"), _call("call:a", "profile:alias")],
        list(reversed(_profiles())),
        _frontier(_card()),
        publication_rate_card_digest=_DIGEST,
    )

    assert [match.call_id for match in matches] == ["call:a", "call:z"]
    assert [match.match_basis for match in matches] == [
        "model_alias",
        "exact_model_profile",
    ]
    assert matches[0].configured_cost_usd == "0.0000475"
    assert matches[0].estimated_credits == "0.0000274"
    assert matches[0].cost_coverage == "1"
    assert matches[0].cost_grade == "configured_estimate"
    assert matches[0].valuation_id is not None


def test_exact_match_wins_a_rule_tie_independent_of_authored_class_order() -> None:
    card = _card(
        model_match_rules=[
            {"model_alias": "synthetic-exact", "match_basis": "model_alias"},
            {
                "model_profile_id": "profile:exact",
                "match_basis": "exact_model_profile",
            },
        ]
    )

    match = compile_current_valuation_matches(
        [_call("call:tie")],
        _profiles(),
        _frontier(card),
        publication_rate_card_digest=_DIGEST,
    )[0]

    assert match.match_basis == "exact_model_profile"


def test_partial_rates_and_missing_tokens_remain_explicit_null_aware_facts() -> None:
    card = _card(
        four_class_rates={
            "uncached_input_tokens": "1",
            "cached_input_tokens": None,
            "reasoning_tokens": None,
            "output_tokens": None,
        },
        credit_rates={field: None for field in (
            "uncached_input_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
            "output_tokens",
        )},
    )
    match = compile_current_valuation_matches(
        [_call("call:partial", cached_input_tokens=None, reasoning_tokens=0)],
        _profiles(),
        _frontier(card),
        publication_rate_card_digest=_DIGEST,
    )[0]

    assert match.configured_cost_usd == "0.000001"
    assert match.estimated_credits is None
    assert match.cost_rated_token_fields == ("uncached_input_tokens",)
    assert match.cost_unpriced_token_fields == ("reasoning_tokens", "output_tokens")
    assert match.missing_token_fields == ("cached_input_tokens",)
    assert match.cost_coverage_numerator_tokens == 1
    assert match.cost_coverage_denominator_tokens == 5
    assert match.cost_coverage == "0.2"
    assert match.cost_unpriced_reason == "partial_rate_card"
    assert match.credit_unpriced_reason == "partial_rate_card"
    assert match.credit_grade == "unsupported"


def test_reasoning_in_output_excludes_reasoning_without_double_counting() -> None:
    card = _card(
        reasoning_in_output=True,
        four_class_rates={
            "uncached_input_tokens": "1",
            "cached_input_tokens": "1",
            "reasoning_tokens": None,
            "output_tokens": "1",
        },
        credit_rates={
            "uncached_input_tokens": "1",
            "cached_input_tokens": "1",
            "reasoning_tokens": "0",
            "output_tokens": "1",
        },
    )
    match = compile_current_valuation_matches(
        [_call("call:reasoning", reasoning_tokens=999)],
        _profiles(),
        _frontier(card),
        publication_rate_card_digest=_DIGEST,
    )[0]

    assert match.configured_cost_usd == "0.000007"
    assert "reasoning_tokens" not in match.cost_rated_token_fields
    assert "reasoning_tokens" not in match.missing_token_fields
    assert match.cost_coverage_denominator_tokens == 7


@pytest.mark.parametrize(
    ("card", "digest", "reason"),
    [
        (
            _frontier(None),
            _DIGEST,
            ValuationUnpricedReason.MISSING_RATE_CARD_FRONTIER,
        ),
        (
            _frontier(_card()),
            "not-a-digest",
            ValuationUnpricedReason.INVALID_RATE_CARD_DIGEST,
        ),
        (
            _frontier(_card()),
            "sha256:" + "b" * 64,
            ValuationUnpricedReason.RATE_CARD_HEAD_MISMATCH,
        ),
        (
            _frontier(_card(validation_status="invalid")),
            _DIGEST,
            ValuationUnpricedReason.INVALID_RATE_CARD_REVISION,
        ),
        (
            _frontier(_card(model_match_rules=["not-a-rule"])),
            _DIGEST,
            ValuationUnpricedReason.INVALID_RATE_CARD_REVISION,
        ),
        (
            _frontier(
                _card(
                    reasoning_in_output=True,
                    four_class_rates={
                        "uncached_input_tokens": "1",
                        "cached_input_tokens": "1",
                        "reasoning_tokens": "1",
                        "output_tokens": "1",
                    },
                )
            ),
            _DIGEST,
            ValuationUnpricedReason.INVALID_RATE_CARD_REVISION,
        ),
    ],
)
def test_missing_or_invalid_cards_fail_closed_without_false_zero(
    card: object, digest: str, reason: ValuationUnpricedReason
) -> None:
    match = compile_current_valuation_matches(
        [_call("call:unpriced")],
        _profiles(),
        card,  # type: ignore[arg-type]
        publication_rate_card_digest=digest,
    )[0]

    assert match.configured_cost_usd is None
    assert match.estimated_credits is None
    assert match.cost_rated_token_fields == ()
    assert match.cost_unpriced_token_fields == (
        "uncached_input_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "output_tokens",
    )
    assert match.cost_coverage_numerator_tokens == 0
    assert match.cost_coverage_denominator_tokens == 10
    assert match.cost_coverage == "0"
    assert match.cost_unpriced_reason == reason
    assert match.cost_grade == "unsupported"


def test_unmatched_and_missing_profiles_are_typed_unpriced_rows() -> None:
    matches = compile_current_valuation_matches(
        [
            _call("call:missing", "profile:missing"),
            _call("call:unmatched", "profile:unmatched"),
        ],
        _profiles()
        + [
            {
                "model_profile_id": "profile:unmatched",
                "model": "other",
                "reasoning_effort": None,
                "service_tier": None,
            }
        ],
        _frontier(_card()),
        publication_rate_card_digest=_DIGEST,
    )

    assert [match.cost_unpriced_reason for match in matches] == [
        "model_profile_missing",
        "model_unmatched",
    ]
    assert all(match.match_basis == "no_match" for match in matches)
    assert all(match.configured_cost_usd is None for match in matches)


def test_observed_rated_zero_is_a_real_zero_but_unrated_zero_is_null() -> None:
    zero = _call(
        "call:zero",
        uncached_input_tokens=0,
        cached_input_tokens=0,
        reasoning_tokens=0,
        output_tokens=0,
    )
    rated = compile_current_valuation_matches(
        [zero], _profiles(), _frontier(_card()), publication_rate_card_digest=_DIGEST
    )[0]
    unrated = compile_current_valuation_matches(
        [zero],
        _profiles(),
        _frontier(
            _card(
                four_class_rates={
                    field: None
                    for field in (
                        "uncached_input_tokens",
                        "cached_input_tokens",
                        "reasoning_tokens",
                        "output_tokens",
                    )
                }
            )
        ),
        publication_rate_card_digest=_DIGEST,
    )[0]

    assert rated.configured_cost_usd == "0"
    assert rated.cost_coverage is None
    assert unrated.configured_cost_usd is None
    assert unrated.cost_grade == "unsupported"


def test_dataclasses_are_frozen_and_duplicate_fact_ids_are_rejected() -> None:
    card = RateCardRevision(
        rate_card_id="rate-card:synthetic",
        digest=_DIGEST,
        predecessor_digest=None,
        effective_at_us=0,
        fetched_at_us=999,
        source_name="synthetic",
        source_url=None,
        currency="USD",
        model_match_rules=(
            {"model_profile_id": "profile:exact"},
        ),
        four_class_rates={field: "1" for field in (
            "uncached_input_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
            "output_tokens",
        )},
        credit_rates={field: "1" for field in (
            "uncached_input_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
            "output_tokens",
        )},
        reasoning_in_output=False,
        confidence="synthetic",
        validation_status="valid",
    )
    frontier = RateCardFrontier(head_digest=card.digest, revisions=(card,))
    with pytest.raises(FrozenInstanceError):
        card.digest = "sha256:" + "b" * 64  # type: ignore[misc]
    match = compile_current_valuation_matches(
        [_call("call:frozen")],
        _profiles(),
        frontier,
        publication_rate_card_digest=_DIGEST,
    )[0]
    with pytest.raises(FrozenInstanceError):
        match.configured_cost_usd = "0"  # type: ignore[misc]
    with pytest.raises(ValueError, match="duplicate call_id"):
        compile_current_valuation_matches(
            [_call("call:duplicate"), _call("call:duplicate")],
            _profiles(),
            frontier,
            publication_rate_card_digest=_DIGEST,
        )
