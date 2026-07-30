from __future__ import annotations

from dataclasses import replace

import pytest

from codex_usage_tracker.agent_kernel.domain.valuation import (
    RateCardFrontier,
    RateCardRevision,
    ValuationUnpricedReason,
    compile_current_valuation_matches,
    derive_frontier_dirty_intervals,
)
from tests.agent_kernel.contracts.reference.effective_dated_valuation import (
    select_revision,
)

_PROFILE = {
    "model_profile_id": "profile:exact",
    "model": "synthetic-model",
    "reasoning_effort": "high",
    "service_tier": "priority",
}
_OTHER_PROFILE = {
    "model_profile_id": "profile:other",
    "model": "other-model",
    "reasoning_effort": "medium",
    "service_tier": "standard",
}


def _digest(index: int) -> str:
    return "sha256:" + f"{index:x}" * 64


def _revision(
    index: int,
    effective_at_us: int | None,
    *,
    predecessor_digest: str | None = None,
    profile_id: str | None = "profile:exact",
    aliases: tuple[str, ...] = (),
    rate: str = "1",
    validation_status: str = "valid",
    fetched_at_us: int = 999_999,
) -> RateCardRevision:
    rules: list[dict[str, object]] = []
    if profile_id is not None:
        rules.append(
            {
                "model_profile_id": profile_id,
                "match_basis": "exact_model_profile",
            }
        )
    if aliases:
        rules.append(
            {
                "model_aliases": list(aliases),
                "match_basis": "model_alias",
            }
        )
    return RateCardRevision(
        rate_card_id=f"rate-card:{index}",
        digest=_digest(index),
        predecessor_digest=predecessor_digest,
        effective_at_us=effective_at_us,
        fetched_at_us=fetched_at_us,
        source_name="synthetic",
        source_url=None,
        currency="USD",
        model_match_rules=tuple(rules),
        four_class_rates={
            "uncached_input_tokens": rate,
            "cached_input_tokens": "0",
            "reasoning_tokens": "0",
            "output_tokens": "0",
        },
        credit_rates={
            "uncached_input_tokens": rate,
            "cached_input_tokens": "0",
            "reasoning_tokens": "0",
            "output_tokens": "0",
        },
        reasoning_in_output=False,
        confidence="synthetic",
        validation_status=validation_status,
    )


def _frontier(*revisions: RateCardRevision) -> RateCardFrontier:
    return RateCardFrontier(head_digest=revisions[-1].digest, revisions=revisions)


def _call(call_id: str, event_at_us: object, profile_id: str = "profile:exact") -> dict[str, object]:
    return {
        "call_id": call_id,
        "event_at_us": event_at_us,
        "model_profile_id": profile_id,
        "uncached_input_tokens": 1_000_000,
        "cached_input_tokens": 0,
        "reasoning_tokens": 0,
        "output_tokens": 0,
    }


def _compile(
    calls: list[dict[str, object]],
    frontier: RateCardFrontier,
    *,
    profiles: list[dict[str, object]] | None = None,
    publication_digest: str | None = None,
):
    return compile_current_valuation_matches(
        calls,
        profiles or [_PROFILE, _OTHER_PROFILE],
        frontier,
        publication_rate_card_digest=publication_digest or frontier.head_digest,
    )


def test_before_exact_and_after_boundary_match_independent_reference() -> None:
    old = _revision(1, 100)
    new = _revision(2, 200, predecessor_digest=old.digest, rate="2")
    frontier = _frontier(old, new)
    calls = [
        _call("call:before", 199),
        _call("call:exact", 200),
        _call("call:after", 201),
    ]

    matches = _compile(calls, frontier)

    by_call = {match.call_id: match for match in matches}
    expected_revisions = [
        {
            "digest": old.digest,
            "effective_at_us": 100,
            "rule": {"model_profile_id": "profile:exact"},
            "rate": "1",
            "tokens": 1_000_000,
        },
        {
            "digest": new.digest,
            "effective_at_us": 200,
            "rule": {"model_profile_id": "profile:exact"},
            "rate": "2",
            "tokens": 1_000_000,
        },
    ]
    for call in calls:
        digest, basis, cost = select_revision(
            event_at_us=int(call["event_at_us"]),
            model_profile=_PROFILE,
            revisions=expected_revisions,
        )
        actual = by_call[str(call["call_id"])]
        assert (actual.rate_card_digest, actual.match_basis, actual.configured_cost_usd) == (
            digest,
            basis,
            cost,
        )


def test_late_historical_call_and_later_revision_do_not_reprice_earlier_calls() -> None:
    old = _revision(1, 100)
    first = _frontier(old)
    calls = [_call("call:original", 150), _call("call:late-ingested", 125)]
    before = _compile(calls, first)

    later = _revision(2, 200, predecessor_digest=old.digest, rate="9")
    after = _compile(calls, _frontier(old, later))

    assert [
        (match.call_id, match.rate_card_digest, match.configured_cost_usd, match.valuation_id)
        for match in after
    ] == [
        (match.call_id, match.rate_card_digest, match.configured_cost_usd, match.valuation_id)
        for match in before
    ]


def test_model_subset_revision_keeps_older_match_for_unchanged_model() -> None:
    old = _revision(1, 100, profile_id="profile:other", rate="1")
    changed = _revision(
        2,
        200,
        predecessor_digest=old.digest,
        profile_id="profile:exact",
        rate="2",
    )

    matches = _compile(
        [
            _call("call:changed", 250),
            _call("call:unchanged", 250, "profile:other"),
        ],
        _frontier(old, changed),
    )

    by_call = {match.call_id: match for match in matches}
    assert by_call["call:changed"].rate_card_digest == changed.digest
    assert by_call["call:unchanged"].rate_card_digest == old.digest


@pytest.mark.parametrize(
    ("call_time", "frontier_factory", "publication_digest", "reason"),
    [
        (
            99,
            lambda: _frontier(_revision(1, 100)),
            None,
            ValuationUnpricedReason.RATE_CARD_NOT_YET_EFFECTIVE,
        ),
        (
            100,
            lambda: _frontier(_revision(1, 100, validation_status="invalid")),
            None,
            ValuationUnpricedReason.INVALID_RATE_CARD_REVISION,
        ),
        (
            100,
            lambda: _frontier(_revision(1, None)),
            None,
            ValuationUnpricedReason.MISSING_REVISION_EFFECTIVE_AT,
        ),
        (
            None,
            lambda: _frontier(_revision(1, 100)),
            None,
            ValuationUnpricedReason.MISSING_CALL_TIME,
        ),
        (
            "100",
            lambda: _frontier(_revision(1, 100)),
            None,
            ValuationUnpricedReason.INVALID_CALL_TIME,
        ),
        (
            100,
            lambda: _frontier(_revision(1, 100, profile_id="profile:other")),
            None,
            ValuationUnpricedReason.MODEL_UNMATCHED,
        ),
    ],
)
def test_future_missing_invalid_and_unmatched_inputs_are_typed_unpriced(
    call_time: object,
    frontier_factory,
    publication_digest: str | None,
    reason: ValuationUnpricedReason,
) -> None:
    frontier = frontier_factory()

    match = _compile(
        [_call("call:unpriced", call_time)],
        frontier,
        publication_digest=publication_digest,
    )[0]

    assert match.rate_card_digest is None
    assert match.configured_cost_usd is None
    assert match.estimated_credits is None
    assert match.cost_grade == "unsupported"
    assert match.cost_unpriced_reason is reason


def test_missing_predecessor_cycle_head_mismatch_and_ambiguity_fail_closed() -> None:
    missing = _revision(2, 200, predecessor_digest=_digest(1))
    left = _revision(3, 100, predecessor_digest=_digest(4))
    right = _revision(4, 200, predecessor_digest=left.digest)
    ambiguous_old = _revision(5, 100)
    ambiguous_new = _revision(
        6,
        100,
        predecessor_digest=ambiguous_old.digest,
    )
    cases = [
        (
            _frontier(missing),
            None,
            ValuationUnpricedReason.MISSING_RATE_CARD_PREDECESSOR,
        ),
        (
            RateCardFrontier(head_digest=right.digest, revisions=(left, right)),
            None,
            ValuationUnpricedReason.RATE_CARD_LINEAGE_CYCLE,
        ),
        (
            _frontier(_revision(7, 100)),
            _digest(8),
            ValuationUnpricedReason.RATE_CARD_HEAD_MISMATCH,
        ),
        (
            _frontier(ambiguous_old, ambiguous_new),
            None,
            ValuationUnpricedReason.AMBIGUOUS_RATE_CARD_MATCH,
        ),
    ]

    for frontier, publication_digest, reason in cases:
        match = _compile(
            [_call(f"call:{reason.value}", 200)],
            frontier,
            publication_digest=publication_digest,
        )[0]
        assert match.configured_cost_usd is None
        assert match.rate_card_digest is None
        assert match.cost_unpriced_reason is reason


def test_time_recency_precedes_same_time_exact_over_alias_precedence() -> None:
    older_exact = _revision(1, 100, rate="1")
    newer_alias = _revision(
        2,
        200,
        predecessor_digest=older_exact.digest,
        profile_id=None,
        aliases=("synthetic-model",),
        rate="2",
    )
    same_time_exact = _revision(
        3,
        200,
        predecessor_digest=newer_alias.digest,
        rate="3",
    )

    newer_alias_match = _compile(
        [_call("call:newer-alias", 250)],
        _frontier(older_exact, newer_alias),
    )[0]
    same_time_exact_match = _compile(
        [_call("call:same-time-exact", 250)],
        _frontier(older_exact, newer_alias, same_time_exact),
    )[0]

    assert (newer_alias_match.rate_card_digest, newer_alias_match.match_basis) == (
        newer_alias.digest,
        "model_alias",
    )
    assert (same_time_exact_match.rate_card_digest, same_time_exact_match.match_basis) == (
        same_time_exact.digest,
        "exact_model_profile",
    )


def test_fetched_at_is_provenance_only_and_never_selects_the_revision() -> None:
    older_effective = _revision(
        1,
        100,
        rate="1",
        fetched_at_us=9_000,
    )
    newer_effective = _revision(
        2,
        200,
        predecessor_digest=older_effective.digest,
        rate="2",
        fetched_at_us=1_000,
    )

    match = _compile(
        [_call("call:fetch-order", 250)],
        _frontier(older_effective, newer_effective),
    )[0]

    assert match.rate_card_digest == newer_effective.digest
    assert match.configured_cost_usd == "2"


def test_backdated_correction_changes_only_its_half_open_interval_and_dirty_range() -> None:
    old = _revision(1, 100, rate="1")
    later = _revision(2, 200, predecessor_digest=old.digest, rate="2")
    before = _frontier(old, later)
    correction = _revision(
        3,
        150,
        predecessor_digest=later.digest,
        rate="1.5",
    )
    after = _frontier(old, later, correction)
    calls = [
        _call("call:before", 149),
        _call("call:start", 150),
        _call("call:inside", 199),
        _call("call:end", 200),
        _call("call:after", 250),
    ]

    prior = {match.call_id: match for match in _compile(calls, before)}
    corrected = {match.call_id: match for match in _compile(calls, after)}
    dirty = derive_frontier_dirty_intervals(before, after)

    assert dirty == (
        replace(
            dirty[0],
            effective_at_us=150,
            next_effective_at_us=200,
        ),
    )
    assert dirty[0].revision_digest == correction.digest
    assert {
        call_id
        for call_id in corrected
        if corrected[call_id].valuation_id != prior[call_id].valuation_id
    } == {"call:start", "call:inside"}
    assert corrected["call:start"].rate_card_digest == correction.digest
    assert corrected["call:end"].rate_card_digest == later.digest
