"""Pure current-rate-card valuation over canonical call and model-profile facts."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext

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


@dataclass(frozen=True, slots=True)
class CurrentRateCard:
    """The selected logical rate-card revision used by the pure relation."""

    rate_card_id: str
    digest: str
    model_match_rules: tuple[Mapping[str, object], ...]
    four_class_rates: Mapping[str, str | None]
    credit_rates: Mapping[str, str | None]
    reasoning_in_output: bool
    validation_status: str


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
    cost_unpriced_reason: str | None
    credit_unpriced_reason: str | None
    cost_grade: str
    credit_grade: str


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


def _coerce_card(
    rate_card: CurrentRateCard | Mapping[str, object] | None,
) -> CurrentRateCard | None:
    if rate_card is None:
        return None
    if isinstance(rate_card, CurrentRateCard):
        return rate_card
    if not isinstance(rate_card, Mapping):
        raise TypeError("rate_card must be a CurrentRateCard, mapping, or null")
    return CurrentRateCard(
        rate_card_id=str(rate_card.get("rate_card_id", "")),
        digest=str(rate_card.get("digest", "")),
        model_match_rules=tuple(rate_card.get("model_match_rules", ())),  # type: ignore[arg-type]
        four_class_rates=(
            rate_card.get("four_class_rates", {})  # type: ignore[arg-type]
        ),
        credit_rates=rate_card.get("credit_rates", {}),  # type: ignore[arg-type]
        reasoning_in_output=rate_card.get("reasoning_in_output", False),  # type: ignore[arg-type]
        validation_status=str(rate_card.get("validation_status", "")),
    )


def _card_error(
    card: CurrentRateCard | None,
    publication_digest: str | None,
) -> tuple[str | None, tuple[Mapping[str, object], ...], dict[str, Decimal | None], dict[str, Decimal | None]]:
    if publication_digest is None:
        return "missing_rate_card", (), {}, {}
    if not isinstance(publication_digest, str) or not _DIGEST.fullmatch(
        publication_digest
    ):
        return "invalid_rate_card_digest", (), {}, {}
    if card is None:
        return "missing_rate_card", (), {}, {}
    if (
        not isinstance(card.digest, str)
        or not _DIGEST.fullmatch(card.digest)
        or card.digest != publication_digest
    ):
        return "rate_card_digest_mismatch", (), {}, {}
    if card.validation_status != "valid":
        return "invalid_rate_card", (), {}, {}
    if not isinstance(card.reasoning_in_output, bool):
        return "invalid_rate_card", (), {}, {}
    try:
        rules = _validated_rules(card.model_match_rules)
        cost_rates = _rate_map(card.four_class_rates)
        credit_rates = _rate_map(card.credit_rates)
    except (TypeError, ValueError):
        return "invalid_rate_card", (), {}, {}
    if card.reasoning_in_output and (
        cost_rates["reasoning_tokens"] not in (None, Decimal(0))
        or credit_rates["reasoning_tokens"] not in (None, Decimal(0))
    ):
        return "invalid_rate_card", (), {}, {}
    return None, rules, cost_rates, credit_rates


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
    reason: str,
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
) -> str | None:
    if unpriced:
        return "partial_rate_card"
    if missing:
        return "missing_measurement"
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


def _resolve_match(
    call: Mapping[str, object],
    profiles: Mapping[str, Mapping[str, object]],
    rules: tuple[Mapping[str, object], ...],
    card_reason: str | None,
) -> tuple[str | None, str | None]:
    if card_reason is not None:
        return None, card_reason
    profile_id = call.get("model_profile_id")
    profile = profiles.get(profile_id) if isinstance(profile_id, str) else None
    if profile is None:
        return None, "model_profile_missing"
    match_basis = _profile_matches(profile, rules)
    if match_basis is None:
        return None, "model_unmatched"
    return match_basis, None


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
    digest: str | None,
    profiles: Mapping[str, Mapping[str, object]],
    card: CurrentRateCard | None,
    card_reason: str | None,
    rules: tuple[Mapping[str, object], ...],
    cost_rates: Mapping[str, Decimal | None],
    credit_rates: Mapping[str, Decimal | None],
) -> CurrentValuationMatch:
    tokens = {
        field: _token_value(call.get(field), field) for field in _TOKEN_FIELDS
    }
    reasoning_in_output = bool(
        card_reason is None and card and card.reasoning_in_output
    )
    match_basis, unpriced_reason = _resolve_match(
        call, profiles, rules, card_reason
    )
    if unpriced_reason is not None:
        return _unpriced_match(
            call_id,
            digest,
            tokens,
            reason=unpriced_reason,
            reasoning_in_output=reasoning_in_output,
        )
    assert digest is not None
    assert match_basis is not None
    return _priced_match(
        call_id=call_id,
        digest=digest,
        match_basis=match_basis,
        tokens=tokens,
        cost_rates=cost_rates,
        credit_rates=credit_rates,
        reasoning_in_output=reasoning_in_output,
    )


def compile_current_valuation_matches(
    calls: Sequence[Mapping[str, object]],
    model_profiles: Sequence[Mapping[str, object]],
    rate_card: CurrentRateCard | Mapping[str, object] | None,
    *,
    publication_rate_card_digest: str | None,
) -> tuple[CurrentValuationMatch, ...]:
    """Compile deterministic current valuation rows without storage or a clock."""

    card = _coerce_card(rate_card)
    card_reason, rules, cost_rates, credit_rates = _card_error(
        card, publication_rate_card_digest
    )
    profiles = _profile_index(model_profiles)
    return tuple(
        _compile_call(
            call_id=call_id,
            call=call,
            digest=publication_rate_card_digest,
            profiles=profiles,
            card=card,
            card_reason=card_reason,
            rules=rules,
            cost_rates=cost_rates,
            credit_rates=credit_rates,
        )
        for call_id, call in _ordered_calls(calls)
    )
