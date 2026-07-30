"""Pure effective-dated valuation over canonical calls and a publication frontier."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from enum import Enum
from typing import cast

from .identity import semantic_id

_TOKEN_FIELDS = (
    "uncached_input_tokens",
    "cached_input_tokens",
    "reasoning_tokens",
    "output_tokens",
)
_DIGEST = re.compile(r"^(?:sha256:)?[a-f0-9]{64}$")
_RULE_FIELDS = frozenset(
    {
        "match_basis",
        "model_profile_id",
        "model",
        "reasoning_effort",
        "service_tier",
        "model_alias",
        "model_aliases",
    }
)


class ValuationUnpricedReason(str, Enum):
    """Stable fail-closed reasons emitted by the valuation relation."""

    MISSING_RATE_CARD_FRONTIER = "missing_rate_card_frontier"
    INVALID_RATE_CARD_DIGEST = "invalid_rate_card_digest"
    RATE_CARD_HEAD_MISMATCH = "rate_card_head_mismatch"
    INVALID_RATE_CARD_FRONTIER = "invalid_rate_card_frontier"
    MISSING_RATE_CARD_PREDECESSOR = "missing_rate_card_predecessor"
    RATE_CARD_LINEAGE_CYCLE = "rate_card_lineage_cycle"
    INVALID_RATE_CARD_REVISION = "invalid_rate_card_revision"
    MISSING_REVISION_EFFECTIVE_AT = "missing_revision_effective_at"
    MISSING_CALL_TIME = "missing_call_time"
    INVALID_CALL_TIME = "invalid_call_time"
    RATE_CARD_NOT_YET_EFFECTIVE = "rate_card_not_yet_effective"
    MODEL_PROFILE_MISSING = "model_profile_missing"
    MODEL_UNMATCHED = "model_unmatched"
    AMBIGUOUS_RATE_CARD_MATCH = "ambiguous_rate_card_match"
    PARTIAL_RATE_CARD = "partial_rate_card"
    MISSING_MEASUREMENT = "missing_measurement"


@dataclass(frozen=True, slots=True)
class RateCardRevision:
    """One immutable configured-pricing revision in a captured lineage."""

    rate_card_id: str
    digest: str
    predecessor_digest: str | None
    effective_at_us: int | None
    fetched_at_us: int | None
    source_name: str
    source_url: str | None
    currency: str
    model_match_rules: tuple[Mapping[str, object], ...]
    four_class_rates: Mapping[str, str | None]
    credit_rates: Mapping[str, str | None]
    reasoning_in_output: bool
    confidence: str
    validation_status: str


@dataclass(frozen=True, slots=True)
class RateCardFrontier:
    """The immutable rate-card lineage captured by one publication."""

    head_digest: str
    revisions: tuple[RateCardRevision | Mapping[str, object], ...]


@dataclass(frozen=True, slots=True)
class ValuationDirtyInterval:
    """One bounded valuation interval affected by a newly captured revision."""

    revision_digest: str
    effective_at_us: int
    next_effective_at_us: int | None
    model_match_rules: tuple[Mapping[str, object], ...]


@dataclass(frozen=True, slots=True)
class CurrentValuationMatch:
    """One current valuation result with explicit missingness and coverage."""

    valuation_id: str | None
    call_id: str
    rate_card_digest: str | None
    match_basis: str
    configured_cost_usd: str | None
    estimated_credits: str | None
    cost_rated_token_fields: tuple[str, ...]
    credit_rated_token_fields: tuple[str, ...]
    cost_unpriced_token_fields: tuple[str, ...]
    credit_unpriced_token_fields: tuple[str, ...]
    missing_token_fields: tuple[str, ...]
    cost_coverage_numerator_tokens: int
    cost_coverage_denominator_tokens: int
    cost_coverage: str | None
    credit_coverage_numerator_tokens: int
    credit_coverage_denominator_tokens: int
    credit_coverage: str | None
    cost_unpriced_reason: ValuationUnpricedReason | None
    credit_unpriced_reason: ValuationUnpricedReason | None
    cost_grade: str
    credit_grade: str


@dataclass(frozen=True, slots=True)
class _ValidatedRevision:
    revision: RateCardRevision
    rules: tuple[Mapping[str, object], ...]
    cost_rates: Mapping[str, Decimal | None]
    credit_rates: Mapping[str, Decimal | None]


def _canonical_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("rates must be canonical decimal strings or null")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("rate is not a decimal") from error
    if not parsed.is_finite() or parsed < 0 or value != _decimal_text(parsed):
        raise ValueError("rate must be a canonical nonnegative finite decimal")
    return parsed


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _coverage_text(numerator: int, denominator: int) -> str | None:
    if denominator == 0:
        return None
    with localcontext() as context:
        context.prec = 50
        return _decimal_text(Decimal(numerator) / Decimal(denominator))


def _token_value(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer or null")
    return value


def _text(value: object, field: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value:
        suffix = " or null" if nullable else ""
        raise ValueError(f"{field} must be nonempty text{suffix}")
    return value


def _rate_map(value: object) -> dict[str, Decimal | None]:
    if not isinstance(value, Mapping):
        raise ValueError("rate map must be an object")
    if not set(value).issubset(_TOKEN_FIELDS):
        raise ValueError("rate map contains an unknown token class")
    return {field: _canonical_decimal(value.get(field)) for field in _TOKEN_FIELDS}


def _rule_aliases(rule: Mapping[str, object]) -> tuple[str, ...]:
    singular = rule.get("model_alias")
    plural = rule.get("model_aliases")
    if singular is not None and plural is not None:
        raise ValueError("model rule cannot define both model_alias and model_aliases")
    if singular is not None:
        if not isinstance(singular, str) or not singular:
            raise ValueError("model_alias must be nonempty text")
        return (singular,)
    if plural is None:
        return ()
    if (
        isinstance(plural, (str, bytes))
        or not isinstance(plural, Sequence)
        or not plural
        or any(not isinstance(alias, str) or not alias for alias in plural)
    ):
        raise ValueError("model_aliases must be a nonempty sequence of text")
    if len(set(plural)) != len(plural):
        raise ValueError("model_aliases must not contain duplicates")
    return tuple(plural)


def _validated_rules(value: object) -> tuple[Mapping[str, object], ...]:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or not value
    ):
        raise ValueError("model_match_rules must be a nonempty sequence")
    rules: list[Mapping[str, object]] = []
    for rule in value:
        if not isinstance(rule, Mapping) or not set(rule).issubset(_RULE_FIELDS):
            raise ValueError("model match rule must be an object with known fields")
        aliases = _rule_aliases(rule)
        selectors = ("model_profile_id", "model", "reasoning_effort", "service_tier")
        if not aliases and not any(rule.get(field) is not None for field in selectors):
            raise ValueError("model match rule has no selector")
        for field in selectors:
            if field in rule:
                _text(rule[field], f"model rule {field}", nullable=True)
        expected_basis = "model_alias" if aliases else "exact_model_profile"
        basis = rule.get("match_basis", expected_basis)
        if basis != expected_basis:
            raise ValueError("model rule match_basis conflicts with its selectors")
        rules.append(rule)
    return tuple(rules)


def _coerce_revision(
    revision: RateCardRevision | Mapping[str, object],
) -> RateCardRevision:
    if isinstance(revision, RateCardRevision):
        return revision
    if not isinstance(revision, Mapping):
        raise TypeError("rate-card revisions must be RateCardRevision values or mappings")
    return RateCardRevision(
        rate_card_id=str(revision.get("rate_card_id", "")),
        digest=str(revision.get("digest", "")),
        predecessor_digest=revision.get("predecessor_digest"),  # type: ignore[arg-type]
        effective_at_us=revision.get("effective_at_us"),  # type: ignore[arg-type]
        fetched_at_us=revision.get("fetched_at_us"),  # type: ignore[arg-type]
        source_name=str(revision.get("source_name", "")),
        source_url=revision.get("source_url"),  # type: ignore[arg-type]
        currency=str(revision.get("currency", "")),
        model_match_rules=tuple(revision.get("model_match_rules", ())),  # type: ignore[arg-type]
        four_class_rates=revision.get("four_class_rates", {}),  # type: ignore[arg-type]
        credit_rates=revision.get("credit_rates", {}),  # type: ignore[arg-type]
        reasoning_in_output=revision.get("reasoning_in_output", False),  # type: ignore[arg-type]
        confidence=str(revision.get("confidence", "")),
        validation_status=str(revision.get("validation_status", "")),
    )


def _coerce_frontier(
    frontier: RateCardFrontier | Mapping[str, object] | None,
) -> RateCardFrontier | None:
    if frontier is None:
        return None
    if isinstance(frontier, RateCardFrontier):
        return frontier
    if not isinstance(frontier, Mapping):
        raise TypeError("rate_card_frontier must be a RateCardFrontier, mapping, or null")
    revisions = frontier.get("revisions", ())
    if isinstance(revisions, (str, bytes)) or not isinstance(revisions, Sequence):
        raise TypeError("rate-card frontier revisions must be a sequence")
    return RateCardFrontier(
        head_digest=str(frontier.get("head_digest", "")),
        revisions=tuple(revisions),  # type: ignore[arg-type]
    )


def _validate_revision(
    revision: RateCardRevision,
) -> tuple[ValuationUnpricedReason | None, _ValidatedRevision | None]:
    if (
        not revision.rate_card_id
        or not isinstance(revision.digest, str)
        or not _DIGEST.fullmatch(revision.digest)
    ):
        return ValuationUnpricedReason.INVALID_RATE_CARD_REVISION, None
    if revision.predecessor_digest is not None and (
        not isinstance(revision.predecessor_digest, str)
        or not _DIGEST.fullmatch(revision.predecessor_digest)
    ):
        return ValuationUnpricedReason.INVALID_RATE_CARD_REVISION, None
    if revision.effective_at_us is None:
        return ValuationUnpricedReason.MISSING_REVISION_EFFECTIVE_AT, None
    if isinstance(revision.effective_at_us, bool) or not isinstance(
        revision.effective_at_us, int
    ):
        return ValuationUnpricedReason.INVALID_RATE_CARD_REVISION, None
    if isinstance(revision.fetched_at_us, bool) or not isinstance(
        revision.fetched_at_us, int
    ):
        return ValuationUnpricedReason.INVALID_RATE_CARD_REVISION, None
    if (
        not revision.source_name
        or not revision.currency
        or not revision.confidence
        or revision.validation_status != "valid"
        or not isinstance(revision.reasoning_in_output, bool)
        or (revision.source_url is not None and not isinstance(revision.source_url, str))
    ):
        return ValuationUnpricedReason.INVALID_RATE_CARD_REVISION, None
    try:
        rules = _validated_rules(revision.model_match_rules)
        cost_rates = _rate_map(revision.four_class_rates)
        credit_rates = _rate_map(revision.credit_rates)
    except (TypeError, ValueError):
        return ValuationUnpricedReason.INVALID_RATE_CARD_REVISION, None
    if revision.reasoning_in_output and (
        cost_rates["reasoning_tokens"] not in (None, Decimal(0))
        or credit_rates["reasoning_tokens"] not in (None, Decimal(0))
    ):
        return ValuationUnpricedReason.INVALID_RATE_CARD_REVISION, None
    return None, _ValidatedRevision(revision, rules, cost_rates, credit_rates)


def _validated_frontier(
    frontier: RateCardFrontier | None,
    publication_digest: str | None,
) -> tuple[ValuationUnpricedReason | None, tuple[_ValidatedRevision, ...]]:
    if publication_digest is None:
        return ValuationUnpricedReason.MISSING_RATE_CARD_FRONTIER, ()
    if not isinstance(publication_digest, str) or not _DIGEST.fullmatch(
        publication_digest
    ):
        return ValuationUnpricedReason.INVALID_RATE_CARD_DIGEST, ()
    if frontier is None or not frontier.revisions:
        return ValuationUnpricedReason.MISSING_RATE_CARD_FRONTIER, ()
    if (
        not isinstance(frontier.head_digest, str)
        or not _DIGEST.fullmatch(frontier.head_digest)
    ):
        return ValuationUnpricedReason.INVALID_RATE_CARD_FRONTIER, ()
    if frontier.head_digest != publication_digest:
        return ValuationUnpricedReason.RATE_CARD_HEAD_MISMATCH, ()

    by_digest: dict[str, _ValidatedRevision] = {}
    rate_card_ids: set[str] = set()
    for value in frontier.revisions:
        try:
            revision = _coerce_revision(value)
        except (TypeError, ValueError):
            return ValuationUnpricedReason.INVALID_RATE_CARD_REVISION, ()
        reason, validated = _validate_revision(revision)
        if reason is not None or validated is None:
            return reason, ()
        if revision.digest in by_digest or revision.rate_card_id in rate_card_ids:
            return ValuationUnpricedReason.INVALID_RATE_CARD_FRONTIER, ()
        by_digest[revision.digest] = validated
        rate_card_ids.add(revision.rate_card_id)

    ordered: list[_ValidatedRevision] = []
    seen: set[str] = set()
    digest: str | None = frontier.head_digest
    while digest is not None:
        if digest in seen:
            return ValuationUnpricedReason.RATE_CARD_LINEAGE_CYCLE, ()
        current = by_digest.get(digest)
        if current is None:
            return ValuationUnpricedReason.MISSING_RATE_CARD_PREDECESSOR, ()
        seen.add(digest)
        ordered.append(current)
        digest = current.revision.predecessor_digest
    if len(seen) != len(by_digest):
        return ValuationUnpricedReason.INVALID_RATE_CARD_FRONTIER, ()
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if (
                left.revision.effective_at_us
                != right.revision.effective_at_us
            ):
                continue
            if any(
                bool(_rule_aliases(left_rule)) == bool(_rule_aliases(right_rule))
                and _rules_may_overlap(left_rule, right_rule)
                for left_rule in left.rules
                for right_rule in right.rules
            ):
                return ValuationUnpricedReason.AMBIGUOUS_RATE_CARD_MATCH, ()
    return None, tuple(ordered)


def _profile_matches(
    profile: Mapping[str, object],
    rules: tuple[Mapping[str, object], ...],
) -> str | None:
    # Exact selectors have stable precedence over aliases. Authored rule order
    # breaks ties inside each class.
    for alias_pass in (False, True):
        for rule in rules:
            aliases = _rule_aliases(rule)
            if bool(aliases) != alias_pass:
                continue
            if any(
                field in rule and profile.get(field) != rule[field]
                for field in (
                    "model_profile_id",
                    "model",
                    "reasoning_effort",
                    "service_tier",
                )
            ):
                continue
            if aliases and profile.get("model") not in aliases:
                continue
            return "model_alias" if aliases else "exact_model_profile"
    return None


def _valuation_id(call_id: str, digest: str | None) -> str | None:
    if digest is None or not _DIGEST.fullmatch(digest):
        return None
    return semantic_id("valuation", [call_id, digest])


def _unpriced_match(
    call_id: str,
    digest: str | None,
    tokens: Mapping[str, int | None],
    *,
    reason: ValuationUnpricedReason,
    reasoning_in_output: bool,
) -> CurrentValuationMatch:
    eligible = tuple(
        field
        for field in _TOKEN_FIELDS
        if not (field == "reasoning_tokens" and reasoning_in_output)
    )
    observed = tuple(field for field in eligible if tokens[field] is not None)
    missing = tuple(field for field in eligible if tokens[field] is None)
    denominator = sum(tokens[field] or 0 for field in observed)
    return CurrentValuationMatch(
        valuation_id=_valuation_id(call_id, digest),
        call_id=call_id,
        rate_card_digest=digest if digest and _DIGEST.fullmatch(digest) else None,
        match_basis="no_match",
        configured_cost_usd=None,
        estimated_credits=None,
        cost_rated_token_fields=(),
        credit_rated_token_fields=(),
        cost_unpriced_token_fields=observed,
        credit_unpriced_token_fields=observed,
        missing_token_fields=missing,
        cost_coverage_numerator_tokens=0,
        cost_coverage_denominator_tokens=denominator,
        cost_coverage=None if denominator == 0 else "0",
        credit_coverage_numerator_tokens=0,
        credit_coverage_denominator_tokens=denominator,
        credit_coverage=None if denominator == 0 else "0",
        cost_unpriced_reason=reason,
        credit_unpriced_reason=reason,
        cost_grade="unsupported",
        credit_grade="unsupported",
    )


def _value(
    fields: tuple[str, ...],
    tokens: Mapping[str, int | None],
    rates: Mapping[str, Decimal | None],
) -> str | None:
    if not fields:
        return None
    needed_precision = max(
        50,
        sum(len(str(tokens[field] or 0)) + len(str(rates[field])) for field in fields)
        + 10,
    )
    with localcontext() as context:
        context.prec = needed_precision
        amount = sum(
            (
                Decimal(tokens[field] or 0)
                * (rates[field] or Decimal(0))
                / Decimal(1_000_000)
                for field in fields
            ),
            Decimal(0),
        )
    return _decimal_text(amount)


def _unpriced_reason(
    unpriced: tuple[str, ...],
    missing: tuple[str, ...],
) -> ValuationUnpricedReason | None:
    if unpriced:
        return ValuationUnpricedReason.PARTIAL_RATE_CARD
    if missing:
        return ValuationUnpricedReason.MISSING_MEASUREMENT
    return None


def _profile_index(
    model_profiles: Sequence[Mapping[str, object]],
) -> dict[str, Mapping[str, object]]:
    profiles: dict[str, Mapping[str, object]] = {}
    for profile in model_profiles:
        profile_id = _text(profile.get("model_profile_id"), "model_profile_id")
        assert profile_id is not None
        if profile_id in profiles:
            raise ValueError(f"duplicate model_profile_id: {profile_id}")
        profiles[profile_id] = profile
    return profiles


def _ordered_calls(
    calls: Sequence[Mapping[str, object]],
) -> tuple[tuple[str, Mapping[str, object]], ...]:
    normalized_calls: list[tuple[str, Mapping[str, object]]] = []
    seen_calls: set[str] = set()
    for call in calls:
        call_id = _text(call.get("call_id"), "call_id")
        assert call_id is not None
        if call_id in seen_calls:
            raise ValueError(f"duplicate call_id: {call_id}")
        seen_calls.add(call_id)
        normalized_calls.append((call_id, call))
    return tuple(sorted(normalized_calls, key=lambda item: item[0]))


def _call_event_time(
    call: Mapping[str, object],
) -> tuple[int | None, ValuationUnpricedReason | None]:
    value = call.get("event_at_us")
    if value is None:
        return None, ValuationUnpricedReason.MISSING_CALL_TIME
    if isinstance(value, bool) or not isinstance(value, int):
        return None, ValuationUnpricedReason.INVALID_CALL_TIME
    return value, None


def _select_revision(
    *,
    call: Mapping[str, object],
    profiles: Mapping[str, Mapping[str, object]],
    revisions: tuple[_ValidatedRevision, ...],
) -> tuple[_ValidatedRevision | None, str | None, ValuationUnpricedReason | None]:
    event_at_us, time_reason = _call_event_time(call)
    if time_reason is not None:
        return None, None, time_reason
    profile_id = call.get("model_profile_id")
    profile = profiles.get(profile_id) if isinstance(profile_id, str) else None
    if profile is None:
        return None, None, ValuationUnpricedReason.MODEL_PROFILE_MISSING
    assert event_at_us is not None
    eligible = tuple(
        revision
        for revision in revisions
        if revision.revision.effective_at_us is not None
        and revision.revision.effective_at_us <= event_at_us
    )
    if not eligible:
        return None, None, ValuationUnpricedReason.RATE_CARD_NOT_YET_EFFECTIVE

    effective_times = sorted(
        {
            cast(int, revision.revision.effective_at_us)
            for revision in eligible
        },
        reverse=True,
    )
    for effective_at_us in effective_times:
        candidates: list[tuple[_ValidatedRevision, str]] = []
        for revision in eligible:
            if revision.revision.effective_at_us != effective_at_us:
                continue
            match_basis = _profile_matches(profile, revision.rules)
            if match_basis is not None:
                candidates.append((revision, match_basis))
        if not candidates:
            continue
        exact = [candidate for candidate in candidates if candidate[1] == "exact_model_profile"]
        selected = exact or candidates
        if len(selected) != 1:
            return None, None, ValuationUnpricedReason.AMBIGUOUS_RATE_CARD_MATCH
        return selected[0][0], selected[0][1], None
    return None, None, ValuationUnpricedReason.MODEL_UNMATCHED


def _eligible_fields(reasoning_in_output: bool) -> tuple[str, ...]:
    return tuple(
        field
        for field in _TOKEN_FIELDS
        if not (field == "reasoning_tokens" and reasoning_in_output)
    )


def _measurement_fields(
    tokens: Mapping[str, int | None],
    reasoning_in_output: bool,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    eligible = _eligible_fields(reasoning_in_output)
    return (
        tuple(field for field in eligible if tokens[field] is not None),
        tuple(field for field in eligible if tokens[field] is None),
    )


def _rate_fields(
    observed: tuple[str, ...],
    rates: Mapping[str, Decimal | None],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    rated = tuple(field for field in observed if rates[field] is not None)
    return rated, tuple(field for field in observed if field not in rated)


def _priced_match(
    *,
    call_id: str,
    digest: str,
    match_basis: str,
    tokens: Mapping[str, int | None],
    cost_rates: Mapping[str, Decimal | None],
    credit_rates: Mapping[str, Decimal | None],
    reasoning_in_output: bool,
) -> CurrentValuationMatch:
    observed, missing = _measurement_fields(tokens, reasoning_in_output)
    cost_rated, cost_unpriced = _rate_fields(observed, cost_rates)
    credit_rated, credit_unpriced = _rate_fields(observed, credit_rates)
    denominator = sum(tokens[field] or 0 for field in observed)
    cost_numerator = sum(tokens[field] or 0 for field in cost_rated)
    credit_numerator = sum(tokens[field] or 0 for field in credit_rated)
    return CurrentValuationMatch(
        valuation_id=_valuation_id(call_id, digest),
        call_id=call_id,
        rate_card_digest=digest,
        match_basis=match_basis,
        configured_cost_usd=_value(cost_rated, tokens, cost_rates),
        estimated_credits=_value(credit_rated, tokens, credit_rates),
        cost_rated_token_fields=cost_rated,
        credit_rated_token_fields=credit_rated,
        cost_unpriced_token_fields=cost_unpriced,
        credit_unpriced_token_fields=credit_unpriced,
        missing_token_fields=missing,
        cost_coverage_numerator_tokens=cost_numerator,
        cost_coverage_denominator_tokens=denominator,
        cost_coverage=_coverage_text(cost_numerator, denominator),
        credit_coverage_numerator_tokens=credit_numerator,
        credit_coverage_denominator_tokens=denominator,
        credit_coverage=_coverage_text(credit_numerator, denominator),
        cost_unpriced_reason=_unpriced_reason(cost_unpriced, missing),
        credit_unpriced_reason=_unpriced_reason(credit_unpriced, missing),
        cost_grade="configured_estimate" if cost_rated else "unsupported",
        credit_grade="configured_estimate" if credit_rated else "unsupported",
    )


def _compile_call(
    *,
    call_id: str,
    call: Mapping[str, object],
    profiles: Mapping[str, Mapping[str, object]],
    revisions: tuple[_ValidatedRevision, ...],
    frontier_reason: ValuationUnpricedReason | None,
) -> CurrentValuationMatch:
    tokens = {
        field: _token_value(call.get(field), field) for field in _TOKEN_FIELDS
    }
    if frontier_reason is not None:
        return _unpriced_match(
            call_id,
            None,
            tokens,
            reason=frontier_reason,
            reasoning_in_output=False,
        )
    selected, match_basis, unpriced_reason = _select_revision(
        call=call,
        profiles=profiles,
        revisions=revisions,
    )
    if unpriced_reason is not None:
        return _unpriced_match(
            call_id,
            None,
            tokens,
            reason=unpriced_reason,
            reasoning_in_output=False,
        )
    assert selected is not None
    assert match_basis is not None
    return _priced_match(
        call_id=call_id,
        digest=selected.revision.digest,
        match_basis=match_basis,
        tokens=tokens,
        cost_rates=selected.cost_rates,
        credit_rates=selected.credit_rates,
        reasoning_in_output=selected.revision.reasoning_in_output,
    )


def compile_current_valuation_matches(
    calls: Sequence[Mapping[str, object]],
    model_profiles: Sequence[Mapping[str, object]],
    rate_card_frontier: RateCardFrontier | Mapping[str, object] | None,
    *,
    publication_rate_card_digest: str | None,
) -> tuple[CurrentValuationMatch, ...]:
    """Compile deterministic effective-dated valuation rows without storage or a clock."""

    frontier = _coerce_frontier(rate_card_frontier)
    frontier_reason, revisions = _validated_frontier(
        frontier,
        publication_rate_card_digest,
    )
    profiles = _profile_index(model_profiles)
    return tuple(
        _compile_call(
            call_id=call_id,
            call=call,
            profiles=profiles,
            revisions=revisions,
            frontier_reason=frontier_reason,
        )
        for call_id, call in _ordered_calls(calls)
    )


def validate_rate_card_frontier(
    frontier: RateCardFrontier | Mapping[str, object] | None,
    publication_rate_card_digest: str | None,
) -> ValuationUnpricedReason | None:
    """Return the stable fail-closed reason for an invalid captured frontier."""

    reason, _revisions = _validated_frontier(
        _coerce_frontier(frontier),
        publication_rate_card_digest,
    )
    return reason


def _rules_may_overlap(
    left: Mapping[str, object],
    right: Mapping[str, object],
) -> bool:
    for field in ("model_profile_id", "model", "reasoning_effort", "service_tier"):
        if field in left and field in right and left[field] != right[field]:
            return False
    left_aliases = frozenset(_rule_aliases(left))
    right_aliases = frozenset(_rule_aliases(right))
    if left_aliases and right_aliases and left_aliases.isdisjoint(right_aliases):
        return False
    if left_aliases and "model" in right and right["model"] not in left_aliases:
        return False
    return not (
        right_aliases and "model" in left and left["model"] not in right_aliases
    )


def derive_frontier_dirty_intervals(
    previous: RateCardFrontier | Mapping[str, object] | None,
    current: RateCardFrontier | Mapping[str, object],
) -> tuple[ValuationDirtyInterval, ...]:
    """Return the bounded effective intervals changed by newly captured revisions."""

    current_frontier = _coerce_frontier(current)
    current_reason, current_revisions = _validated_frontier(
        current_frontier,
        None if current_frontier is None else current_frontier.head_digest,
    )
    if current_reason is not None:
        raise ValueError(f"current rate-card frontier is invalid: {current_reason.value}")
    previous_frontier = _coerce_frontier(previous)
    if previous_frontier is None:
        previous_digests: set[str] = set()
    else:
        previous_reason, previous_revisions = _validated_frontier(
            previous_frontier,
            previous_frontier.head_digest,
        )
        if previous_reason is not None:
            raise ValueError(
                f"previous rate-card frontier is invalid: {previous_reason.value}"
            )
        previous_digests = {
            revision.revision.digest for revision in previous_revisions
        }

    intervals: list[ValuationDirtyInterval] = []
    for added in current_revisions:
        revision = added.revision
        if revision.digest in previous_digests:
            continue
        assert revision.effective_at_us is not None
        next_effective_at_us = min(
            (
                candidate.revision.effective_at_us
                for candidate in current_revisions
                if candidate.revision.effective_at_us is not None
                and candidate.revision.effective_at_us > revision.effective_at_us
                and any(
                    _rules_may_overlap(rule, other_rule)
                    for rule in added.rules
                    for other_rule in candidate.rules
                )
            ),
            default=None,
        )
        intervals.append(
            ValuationDirtyInterval(
                revision_digest=revision.digest,
                effective_at_us=revision.effective_at_us,
                next_effective_at_us=next_effective_at_us,
                model_match_rules=added.rules,
            )
        )
    return tuple(
        sorted(
            intervals,
            key=lambda interval: (
                interval.effective_at_us,
                interval.revision_digest,
            ),
        )
    )
