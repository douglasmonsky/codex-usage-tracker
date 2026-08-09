"""Independent answer semantics over declared synthetic facts.

This module intentionally has no production imports.  It is a small test-only
evaluator: declarations are the input authority, and every derived value is
calculated here from relation facts, request parameters, and the frozen R1A
boundary rules.  The module never opens a database or consumes precomputed
answer rows.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[4]
SCENARIOS_PATH = ROOT / "tests/agent_kernel/fixtures/tiny-v2/question-scenarios.json"
CONTRACT_PATH = ROOT / "config/agent-kernel/answer-semantics-v1.json"
VECTORS_PATH = ROOT / "tests/agent_kernel/fixtures/contracts/answer-semantics-v1-vectors.json"
QUESTION_CATALOG_PATH = ROOT / "config/agent-kernel/question-catalog-v1.json"
SELECTOR_PROVENANCE_PATH = ROOT / "config/agent-kernel/selector-provenance-v1.json"

TOKEN_CLASSES = (
    "uncached_input_tokens",
    "cached_input_tokens",
    "reasoning_tokens",
    "output_tokens",
)
THREE_CLASS_TOKENS = (
    "uncached_input_tokens",
    "cached_input_tokens",
    "output_tokens",
)
BOUNDARY_ORDER = (
    "event_at_us_is_null",
    "event_at_us",
    "source_rank",
    "source_order",
    "event_kind_order",
    "logical_id",
    "transition_rank",
)
FORBIDDEN_DATA_KEYS = frozenset(
    {
        "answer_rows",
        "comparison_rows",
        "expected_rows",
        "grades",
        "grading",
        "oracle_case",
    }
)
_MISSING = object()


class SemanticError(ValueError):
    """A declaration cannot be evaluated without inventing a fact."""


def _json(value: Any) -> Any:
    if not isinstance(value, (dict, list)) and value is not None:
        return value
    return value


def _canonical(value: Any) -> Any:
    """Return JSON-safe deterministic values, including exact Decimal text."""

    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        _canonical(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _cbor_head(major: int, value: int) -> bytes:
    if value < 0:
        raise SemanticError("semantic identity length must be nonnegative")
    initial = major << 5
    if value < 24:
        return bytes((initial | value,))
    if value <= 0xFF:
        return bytes((initial | 24, value))
    if value <= 0xFFFF:
        return bytes((initial | 25,)) + value.to_bytes(2, "big")
    if value <= 0xFFFFFFFF:
        return bytes((initial | 26,)) + value.to_bytes(4, "big")
    if value <= 0xFFFFFFFFFFFFFFFF:
        return bytes((initial | 27,)) + value.to_bytes(8, "big")
    raise SemanticError("semantic identity length exceeds 64-bit encoding")


def _canonical_cbor(value: Any) -> bytes:
    """Encode the small CK-02 identity vocabulary without importing production."""

    if value is None:
        return b"\xf6"
    if value is False:
        return b"\xf4"
    if value is True:
        return b"\xf5"
    if isinstance(value, int):
        return _cbor_head(0, value) if value >= 0 else _cbor_head(1, -1 - value)
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        return _cbor_head(3, len(encoded)) + encoded
    if isinstance(value, (list, tuple)):
        return _cbor_head(4, len(value)) + b"".join(_canonical_cbor(item) for item in value)
    if isinstance(value, dict):
        pairs = [(_canonical_cbor(key), _canonical_cbor(item)) for key, item in value.items()]
        pairs.sort(key=lambda pair: (len(pair[0]), pair[0]))
        return _cbor_head(5, len(pairs)) + b"".join(key + item for key, item in pairs)
    raise SemanticError(f"unsupported semantic identity value: {type(value).__name__}")


def _semantic_id(kind: str, identity: Any) -> str:
    digest = hashlib.sha256(_canonical_cbor(identity)).digest()
    encoded = base64.b32encode(digest).decode("ascii").rstrip("=").lower()
    return f"{kind}:v1:{encoded}"


def _request_digest(request: Mapping[str, Any]) -> str:
    payload = json.dumps(
        _canonical(
            {
                "gates": request.get("gates"),
                "parameters": request.get("parameters"),
                "plan_id": request.get("plan_id"),
            }
        ),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _decimal(value: Any, name: str = "value") -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise SemanticError(f"{name} must be an exact number")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise SemanticError(f"{name} must be an exact number") from exc
    raise SemanticError(f"{name} must be an exact number")


def _number(value: Any, name: str = "value") -> int | Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise SemanticError(f"{name} must be an exact integer or Decimal")
    return value


def _scalar(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return str(value)
    return value


def _value(fact: Mapping[str, Any], name: str, *, required: bool = True) -> Any:
    values = fact.get("values")
    if not isinstance(values, Mapping):
        raise SemanticError("fact values must be a mapping")
    if name not in values:
        if required:
            raise SemanticError(f"{fact.get('relation')} is missing {name}")
        return None
    return values[name]


def _facts(case: Mapping[str, Any], relation: str | None = None) -> list[Mapping[str, Any]]:
    declaration = case.get("declaration")
    if not isinstance(declaration, Mapping) or not isinstance(declaration.get("facts"), list):
        raise SemanticError("declaration facts are required")
    facts = [item for item in declaration["facts"] if isinstance(item, Mapping)]
    if len(facts) != len(declaration["facts"]):
        raise SemanticError("declaration contains a malformed fact")
    return [fact for fact in facts if relation is None or fact.get("relation") == relation]


def _validate_unique_stable_ids(
    facts: Sequence[Mapping[str, Any]], field: str, relation: str
) -> None:
    seen: set[str] = set()
    for fact in facts:
        value = _value(fact, field)
        if not isinstance(value, str) or not value:
            raise SemanticError(f"{relation} stable identity is malformed")
        if value in seen:
            raise SemanticError(f"duplicate {relation} stable identity")
        seen.add(value)


def _reject_forbidden_data_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        if FORBIDDEN_DATA_KEYS.intersection(str(key) for key in value):
            raise SemanticError("answer, grading, and oracle inputs are forbidden")
        for item in value.values():
            _reject_forbidden_data_keys(item)
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden_data_keys(item)


def _coordinates(fact: Mapping[str, Any]) -> Mapping[str, Any]:
    coordinates = fact.get("coordinates")
    if not isinstance(coordinates, Mapping):
        raise SemanticError(f"{fact.get('logical_id')} has no coordinates")
    return coordinates


def _coordinate_key(fact: Mapping[str, Any]) -> tuple[Any, ...]:
    coordinates = _coordinates(fact)
    at = coordinates.get("event_at_us")
    if at is not None and (isinstance(at, bool) or not isinstance(at, int)):
        raise SemanticError("event_at_us must be an integer or null")
    source_rank = coordinates.get("source_rank", 0)
    source_order = coordinates.get("source_order", 0)
    event_kind_order = coordinates.get("event_kind_order", 0)
    transition_rank = coordinates.get("transition_rank", 0)
    logical_id = fact.get("logical_id")
    if not isinstance(logical_id, str) or not logical_id:
        raise SemanticError("logical_id must be a non-empty string")
    numbers = (source_rank, source_order, event_kind_order, transition_rank)
    if any(isinstance(item, bool) or not isinstance(item, int) for item in numbers):
        raise SemanticError("event order coordinates must be integers")
    return (
        at is None,
        at or 0,
        source_rank,
        source_order,
        event_kind_order,
        logical_id,
        transition_rank,
    )


def _ordered(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(rows, key=_coordinate_key)


def _window(request: Mapping[str, Any], name: str = "window") -> tuple[int, int] | None:
    parameters = request.get("parameters", {})
    if not isinstance(parameters, Mapping) or name not in parameters:
        return None
    value = parameters[name]
    if not isinstance(value, Mapping):
        raise SemanticError(f"{name} must be an object")
    start, end = value.get("start_us"), value.get("end_us")
    if (
        isinstance(start, bool)
        or not isinstance(start, int)
        or isinstance(end, bool)
        or not isinstance(end, int)
    ):
        raise SemanticError(f"{name} requires integer bounds")
    if start >= end:
        raise SemanticError(f"{name} must be a non-empty half-open interval")
    return start, end


def _scoped(
    rows: Iterable[Mapping[str, Any]], request: Mapping[str, Any], name: str = "window"
) -> list[Mapping[str, Any]]:
    interval = _window(request, name)
    values = list(rows)
    if interval is None:
        return values
    start, end = interval
    out = []
    for row in values:
        at = _coordinates(row).get("event_at_us")
        if at is None:
            raise SemanticError("windowed facts require event timestamps")
        if start <= at < end:
            out.append(row)
    return out


def _calls(
    case: Mapping[str, Any], request: Mapping[str, Any], name: str = "window"
) -> list[Mapping[str, Any]]:
    return _ordered(_scoped(_facts(case, "canonical_call"), request, name))


def _sum_field(rows: Sequence[Mapping[str, Any]], field: str, *, empty: Any = None) -> Any:
    if not rows:
        return empty
    values: list[int | Decimal] = []
    for row in rows:
        value = _number(_value(row, field), field)
        if value is None:
            return None
        values.append(value)
    if all(isinstance(item, int) for item in values):
        return sum(values)
    return sum((Decimal(item) for item in values), Decimal(0))


def _total(rows: Sequence[Mapping[str, Any]], *, empty: Any = None) -> Any:
    if not rows:
        return empty
    values = [_sum_field(rows, field) for field in THREE_CLASS_TOKENS]
    if any(value is None for value in values):
        return None
    return (
        sum((Decimal(value) for value in values if value is not None), Decimal(0))
        if any(isinstance(value, Decimal) for value in values)
        else sum(values)
    )


def _four_class_total(rows: Sequence[Mapping[str, Any]], *, empty: Any = None) -> Any:
    if not rows:
        return empty
    values = [_sum_field(rows, field) for field in TOKEN_CLASSES]
    if any(value is None for value in values):
        return None
    if any(isinstance(value, Decimal) for value in values):
        return sum((Decimal(value) for value in values if value is not None), Decimal(0))
    return sum(values)


def _input(row: Mapping[str, Any]) -> int | Decimal | None:
    cached = _number(_value(row, "cached_input_tokens"), "cached_input_tokens")
    uncached = _number(_value(row, "uncached_input_tokens"), "uncached_input_tokens")
    if cached is None or uncached is None:
        return None
    if isinstance(cached, Decimal) or isinstance(uncached, Decimal):
        return Decimal(cached or 0) + Decimal(uncached or 0)
    return cached + uncached


def _ratio(numerator: Any, denominator: Any) -> Decimal | None:
    if numerator is None or denominator is None:
        return None
    denominator_decimal = _decimal(denominator)
    numerator_decimal = _decimal(numerator)
    if numerator_decimal is None or denominator_decimal is None or denominator_decimal == 0:
        return None
    with localcontext() as context:
        context.prec = 28
        return numerator_decimal / denominator_decimal


def _difference(left: Any, right: Any) -> Any:
    if left is None or right is None:
        return None
    if isinstance(left, Decimal) or isinstance(right, Decimal):
        return Decimal(left) - Decimal(right)
    return left - right


def _group(rows: Iterable[Mapping[str, Any]], field: str) -> dict[Any, list[Mapping[str, Any]]]:
    grouped: dict[Any, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_value(row, field)].append(row)
    return grouped


def _profile_map(case: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(_value(row, "model_profile_id")): row for row in _facts(case, "model_profile")}


def _valuation(case: Mapping[str, Any], call: Mapping[str, Any]) -> Decimal | None:
    profile = _profile_map(case).get(str(_value(call, "model_profile_id")))
    if profile is None:
        return None
    model = _value(profile, "model")
    at = _coordinates(call).get("event_at_us")
    if at is None:
        return None
    frontier = case.get("declaration", {}).get("rate_card_frontier", {})
    revisions = frontier.get("revisions", []) if isinstance(frontier, Mapping) else []
    chosen: Mapping[str, Any] | None = None
    for revision in revisions:
        if not isinstance(revision, Mapping):
            continue
        effective = revision.get("effective_at_us")
        rules = revision.get("model_match_rules", [])
        aliases = {rule.get("model_alias") for rule in rules if isinstance(rule, Mapping)}
        if (
            isinstance(effective, int)
            and effective <= at
            and model in aliases
            and (chosen is None or effective > int(chosen.get("effective_at_us", -1)))
        ):
            chosen = revision
    if chosen is None:
        return None
    rates = chosen.get("four_class_rates", chosen.get("credit_rates", {}))
    if not isinstance(rates, Mapping):
        return None
    total = Decimal(0)
    for field in TOKEN_CLASSES:
        value = _number(_value(call, field), field)
        if value is not None:
            total += Decimal(value) * (_decimal(rates.get(field), field) or Decimal(0))
    return total / Decimal(1_000_000)


def _cost_sum(case: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> Decimal | None:
    if not rows:
        return None
    values = [_valuation(case, row) for row in rows]
    if any(value is None for value in values):
        return None
    return sum((value for value in values if value is not None), Decimal(0))


def _call_direct(case: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "cached_input_tokens": _sum_field(rows, "cached_input_tokens"),
        "calls": len(rows),
        "configured_cost_usd": _cost_sum(case, rows),
        "estimated_credits": _cost_sum(case, rows),
        "output_tokens": _sum_field(rows, "output_tokens"),
        "reasoning_tokens": _sum_field(rows, "reasoning_tokens"),
        "total_tokens": _total(rows),
        "uncached_input_tokens": _sum_field(rows, "uncached_input_tokens"),
    }


def _current_usage(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [_call_direct(case, _calls(case, request))]


def _top_sessions(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    groups = _group(_calls(case, request), "session_id")
    totals = {key: _total(rows) for key, rows in groups.items()}
    ordered = sorted(groups, key=lambda key: (-(totals[key] or 0), str(key)))
    limit = request.get("parameters", {}).get("limit", 1)
    top = [totals[key] for key in ordered[:limit] if totals[key] is not None]
    denominator = sum(
        (Decimal(value) for value in totals.values() if value is not None), Decimal(0)
    )
    top_share = _ratio(sum((Decimal(value) for value in top), Decimal(0)), denominator)
    remainder = None if top_share is None else Decimal(1) - top_share
    out = []
    for key in ordered:
        rows = groups[key]
        out.append(
            {
                "cached_input_tokens": _sum_field(rows, "cached_input_tokens"),
                "calls": len(rows),
                "output_tokens": _sum_field(rows, "output_tokens"),
                "reasoning_tokens": _sum_field(rows, "reasoning_tokens"),
                "remainder_share": remainder,
                "session_id": key,
                "top_share": top_share,
                "total_tokens": _total(rows),
                "uncached_input_tokens": _sum_field(rows, "uncached_input_tokens"),
            }
        )
    return out


def _period_drivers(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    parameters = request.get("parameters", {})
    dimension = parameters.get("driver_dimension", "session")
    field = {
        "model_profile": "model_profile_id",
        "project": "project_id",
        "session": "session_id",
        "tool": "tool_id",
    }.get(dimension)
    if field is None:
        raise SemanticError("unsupported driver dimension")
    calls = _calls(case, {"parameters": {}})
    groups = _group(calls, field)
    previous = parameters.get("previous_window", {})
    current = parameters.get("current_window", {})

    def in_window(row: Mapping[str, Any], interval: Mapping[str, Any]) -> bool:
        at = _coordinates(row).get("event_at_us")
        start, end = interval.get("start_us"), interval.get("end_us")
        return (
            isinstance(at, int)
            and isinstance(start, int)
            and isinstance(end, int)
            and start <= at < end
        )

    out = []
    for key, rows in groups.items():
        prior = _total([row for row in rows if in_window(row, previous)])
        now = _total([row for row in rows if in_window(row, current)])
        delta = _difference(now, prior)
        out.append(
            {
                "current_total_tokens": now,
                "driver_contribution": 0 if delta is None else delta,
                "driver_id": key,
                "previous_total_tokens": prior,
                "total_delta": delta,
            }
        )
    return sorted(
        out,
        key=lambda row: (
            -(abs(_decimal(row["total_delta"]) or Decimal(0))),
            str(row["driver_id"]),
        ),
    )


def _model_effort_mix(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    groups = _group(_calls(case, request), "model_profile_id")
    denominator = sum((Decimal(_total(rows) or 0) for rows in groups.values()), Decimal(0))
    out = []
    for key, rows in groups.items():
        out.append(
            {
                "cached_input_tokens": _sum_field(rows, "cached_input_tokens"),
                "calls": len(rows),
                "model_profile_id": key,
                "output_tokens": _sum_field(rows, "output_tokens"),
                "reasoning_tokens": _sum_field(rows, "reasoning_tokens"),
                "share": _ratio(_total(rows), denominator),
                "uncached_input_tokens": _sum_field(rows, "uncached_input_tokens"),
                "_sort": -Decimal(_total(rows) or 0),
            }
        )
    out.sort(key=lambda row: (row.pop("_sort"), str(row["model_profile_id"])))
    return out


def _project_family(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    calls = _calls(case, request)
    groups = _group(calls, "project_id")
    denominator = sum((Decimal(_total(rows) or 0) for rows in groups.values()), Decimal(0))
    out = []
    for key, rows in groups.items():
        family = _total(rows)
        out.append(
            {
                "exclusive_tokens": family,
                "family_id": key,
                "family_tokens": family,
                "session_count": len({_value(row, "session_id") for row in rows}),
                "share": _ratio(family, denominator),
            }
        )
    return sorted(
        out,
        key=lambda row: (
            -(Decimal(row["family_tokens"]) if row["family_tokens"] is not None else 0),
            str(row["family_id"]),
        ),
    )


def _top_valued(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    calls = _calls(case, request)
    kind = request.get("parameters", {}).get("entity_kind", "call")
    identity = {"call": "call_id", "turn": "turn_id", "session": "session_id"}.get(kind)
    if identity is None:
        raise SemanticError("unsupported entity kind")
    groups = _group(calls, identity)
    out = []
    for key, rows in groups.items():
        values = [_valuation(case, row) for row in rows]
        rated = [value for value in values if value is not None]
        cost = sum(rated, Decimal(0)) if rated else None
        out.append(
            {
                "configured_cost_usd": cost,
                "entity_id": key,
                "estimated_credits": cost,
                "rated_calls": len(rated),
                "total_tokens": _total(rows),
                "unrated_calls": len(values) - len(rated),
            }
        )
    return sorted(
        out,
        key=lambda row: (
            -(Decimal(row["configured_cost_usd"]) if row["configured_cost_usd"] is not None else 0),
            str(row["entity_id"]),
        ),
    )


def _pricing_coverage(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    groups = _group(_calls(case, request), "model_profile_id")
    out = []
    for key, rows in groups.items():
        priced = [row for row in rows if _valuation(case, row) is not None]
        unpriced = [row for row in rows if _valuation(case, row) is None]
        out.append(
            {
                "model_profile_id": key,
                "priced_calls": len(priced),
                "pricing_coverage": _ratio(len(priced), len(rows)),
                "unpriced_calls": len(unpriced),
                "unpriced_tokens": _total(unpriced),
            }
        )
    return sorted(
        out,
        key=lambda row: (
            -(Decimal(row["unpriced_tokens"]) if row["unpriced_tokens"] is not None else 0),
            str(row["model_profile_id"]),
        ),
    )


def _cache_reuse(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    out = []
    for row in _calls(case, request):
        cached = _number(_value(row, "cached_input_tokens"), "cached_input_tokens")
        uncached = _number(_value(row, "uncached_input_tokens"), "uncached_input_tokens")
        total_input = _input(row)
        out.append(
            {
                "cached_input_tokens": cached,
                "cached_share": _ratio(
                    cached,
                    (Decimal(cached or 0) + Decimal(uncached or 0))
                    if cached is not None or uncached is not None
                    else None,
                ),
                "call_id": _value(row, "call_id"),
                "total_input_tokens": total_input,
                "uncached_input_tokens": uncached,
            }
        )
    return sorted(
        out,
        key=lambda row: (
            -(Decimal(row["total_input_tokens"]) if row["total_input_tokens"] is not None else 0),
            str(row["call_id"]),
        ),
    )


def _context_pressure(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    calls = _calls(case, request)
    boundaries = _ordered(_scoped(_facts(case, "compaction_boundary"), request))
    groups: dict[tuple[Any, Any], list[Mapping[str, Any]]] = defaultdict(list)
    for row in calls:
        session = _value(row, "session_id")
        preceding = [
            boundary
            for boundary in boundaries
            if _value(boundary, "session_id") == session
            and _coordinate_key(boundary) <= _coordinate_key(row)
        ]
        epoch = _value(preceding[-1], "compaction_id") if preceding else "initial"
        groups[(session, epoch)].append(row)
    out = []
    for (session, epoch), rows in groups.items():
        ordered_inputs = [_input(row) for row in rows]
        if any(value is None for value in ordered_inputs):
            continue
        last = rows[-1]
        cached = _sum_field(rows, "cached_input_tokens")
        uncached = _sum_field(rows, "uncached_input_tokens")
        last_input = ordered_inputs[-1]
        out.append(
            {
                "cached_share": _ratio(
                    cached,
                    (Decimal(cached or 0) + Decimal(uncached or 0))
                    if cached is not None or uncached is not None
                    else None,
                ),
                "context_epoch_id": epoch,
                "context_pressure": _ratio(last_input, _value(last, "context_window_tokens")),
                "context_window_tokens": _value(last, "context_window_tokens"),
                "ordered_input_tokens": ordered_inputs,
                "session_id": session,
                "_sort": -(Decimal(last_input) if last_input is not None else 0),
            }
        )
    out.sort(
        key=lambda row: (row.pop("_sort"), str(row["session_id"]), str(row["context_epoch_id"]))
    )
    return out


def _token_acceleration(
    case: Mapping[str, Any], request: Mapping[str, Any]
) -> list[dict[str, Any]]:
    calls = _calls(case, request)
    groups = _group(calls, "session_id")
    minimum = request.get("parameters", {}).get("minimum_samples", 1)
    out = []
    for session, rows in groups.items():
        by_turn = _group(rows, "turn_id")
        totals = [_total(turn_rows) for turn_rows in by_turn.values()]
        if len(totals) < minimum:
            continue
        midpoint = max(1, len(totals) // 2)
        earlier, later = totals[:midpoint], totals[midpoint:]
        current = totals[-1]
        middle = totals[-2] if len(totals) > 1 else None
        previous = totals[-3] if len(totals) > 2 else None
        acceleration = Decimal(current or 0) - 2 * Decimal(middle or 0) + Decimal(previous or 0)
        out.append(
            {
                "later_earlier_ratio": _ratio(
                    sum((Decimal(value or 0) for value in later), Decimal(0)),
                    sum((Decimal(value or 0) for value in earlier), Decimal(0)),
                ),
                "second_difference": acceleration,
                "session_id": session,
                "turn_tokens": totals,
                "_sort": -acceleration,
            }
        )
    out.sort(key=lambda row: (row.pop("_sort"), str(row["session_id"])))
    return out


def _uncached_jumps(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = _calls(case, request)
    out = []
    for previous, current in zip(rows, rows[1:], strict=False):
        previous_value = _number(_value(previous, "uncached_input_tokens"), "uncached_input_tokens")
        current_value = _number(_value(current, "uncached_input_tokens"), "uncached_input_tokens")
        out.append(
            {
                "call_id": _value(current, "call_id"),
                "current_uncached_input_tokens": current_value,
                "input_delta": _difference(current_value, previous_value),
                "previous_uncached_input_tokens": previous_value,
            }
        )
    return out


def _cached_replay(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    threshold = request.get("parameters", {}).get("threshold", 0)
    out = []
    for row in _calls(case, request):
        output = _number(_value(row, "output_tokens"), "output_tokens")
        if output is None or Decimal(output) > Decimal(threshold):
            continue
        cached = _number(_value(row, "cached_input_tokens"), "cached_input_tokens")
        out.append(
            {
                "cached_input_tokens": cached,
                "cached_output_ratio": _ratio(cached, output),
                "call_id": _value(row, "call_id"),
                "output_tokens": output,
            }
        )
    return sorted(
        out,
        key=lambda row: (
            -(Decimal(row["cached_input_tokens"]) if row["cached_input_tokens"] is not None else 0),
            str(row["call_id"]),
        ),
    )


def _context_composition(
    case: Mapping[str, Any], request: Mapping[str, Any]
) -> list[dict[str, Any]]:
    groups = _group(_scoped(_facts(case, "context_component"), request), "category")
    out = []
    for category, rows in groups.items():
        observed = _sum_field(rows, "observed_utf8_bytes") or 0
        totals = {_value(row, "total_context_utf8_bytes") for row in rows}
        total = next(iter(totals)) if len(totals) == 1 else None
        out.append(
            {
                "component_bytes": observed,
                "component_count": len(rows),
                "component_kind": category,
                "estimated_component_tokens": _sum_field(rows, "estimated_tokens"),
                "unattributed_bytes": None if total is None else total - observed,
            }
        )
    return sorted(out, key=lambda row: (-row["component_bytes"], str(row["component_kind"])))


def _compaction_comparison(
    case: Mapping[str, Any], request: Mapping[str, Any]
) -> list[dict[str, Any]]:
    calls = _calls(case, request)
    out = []
    for boundary in _ordered(_scoped(_facts(case, "compaction_boundary"), request)):
        at = _coordinates(boundary).get("event_at_us")
        if not isinstance(at, int):
            raise SemanticError("compaction boundary requires an event timestamp")
        before = [
            row
            for row in calls
            if isinstance((row_at := _coordinates(row).get("event_at_us")), int) and row_at < at
        ]
        after = [
            row
            for row in calls
            if isinstance((row_at := _coordinates(row).get("event_at_us")), int) and row_at >= at
        ]
        before_value = _value(before[-1], "context_window_tokens") if before else None
        after_value = _value(after[0], "context_window_tokens") if after else None
        out.append(
            {
                "after_tokens": after_value,
                "before_tokens": before_value,
                "compaction_id": _value(boundary, "compaction_id"),
                "context_delta": _difference(after_value, before_value),
            }
        )
    return out


def _growth(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    calls = _calls(case, request)
    groups = _group(calls, "session_id")
    changes = _scoped(_facts(case, "state_change"), request)
    turns = _scoped(_facts(case, "turn"), request)
    out = []
    for session, rows in groups.items():
        first = _value(rows[0], "context_window_tokens")
        last = _value(rows[-1], "context_window_tokens")
        out.append(
            {
                "context_growth": _difference(last, first),
                "mutation_count": sum(_value(row, "session_id") == session for row in changes),
                "session_id": session,
                "turn_count": len(
                    {
                        _value(row, "turn_id")
                        for row in turns
                        if _value(row, "session_id") == session
                    }
                ),
                "_sort": -(Decimal(_difference(last, first) or 0)),
            }
        )
    out.sort(key=lambda row: (row.pop("_sort"), str(row["session_id"])))
    return out


def _long_cohorts(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    parameters = request.get("parameters", {})
    cohort = parameters.get("cohort", {})
    calls = _calls(case, request)
    out = []
    for side in ("left", "right"):
        ids = cohort.get(side, []) if isinstance(cohort, Mapping) else []
        rows = [row for row in calls if _value(row, "session_id") in set(ids)]
        out.append(
            {
                "cohort": side,
                "cohort_size": len(ids),
                "context_features": {"total_context_tokens": _total(rows)},
                "usage_features": {"total_tokens": _total(rows)},
            }
        )
    return out


def _turn_completion(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    calls = _calls(case, request)
    turns = _scoped(_facts(case, "turn"), request)
    groups = _group(calls, "session_id")
    out = []
    for session, rows in groups.items():
        session_turns = [turn for turn in turns if _value(turn, "session_id") == session]
        completed = [turn for turn in session_turns if _value(turn, "lifecycle") == "completed"]
        total = _total(rows)
        out.append(
            {
                "calls": len(rows),
                "completion_state": "completed"
                if session_turns and len(completed) == len(session_turns)
                else "incomplete",
                "session_id": session,
                "tokens_per_completed_turn": _ratio(total, len(completed)),
                "total_tokens": total,
                "turns": len(session_turns),
                "_sort": -len(rows),
            }
        )
    out.sort(key=lambda row: (row.pop("_sort"), str(row["session_id"])))
    return out


def _first_action(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Apply R1A's explicit start/terminal boundaries to structural-v2 facts."""

    parameters = request.get("parameters", {})
    if not isinstance(parameters, Mapping):
        raise SemanticError("workflow parameters are required")
    session_selector = parameters.get("session_selector")
    if session_selector is not None and (
        not isinstance(session_selector, str) or not session_selector
    ):
        raise SemanticError("session selector must be a non-empty string")

    def selected_session(fact: Mapping[str, Any]) -> bool:
        return session_selector is None or _value(fact, "session_id") == session_selector

    def tool_coordinate(tool: Mapping[str, Any], prefix: str) -> tuple[Any, ...] | None:
        values = tool.get("values")
        if not isinstance(values, Mapping):
            raise SemanticError("tool values are malformed")
        fields = (
            f"{prefix}_at_us",
            f"{prefix}_source_rank",
            f"{prefix}_source_order",
            f"{prefix}_event_kind_order",
            f"{prefix}_transition_rank",
        )
        present = [field in values for field in fields]
        if not any(present):
            return None
        if not all(present):
            raise SemanticError(f"incomplete tool {prefix} coordinate")
        at, source_rank, source_order, event_kind_order, transition_rank = (
            values[field] for field in fields
        )
        logical_id = _value(tool, "tool_id")
        if (
            isinstance(at, bool)
            or not isinstance(at, int)
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in (source_rank, source_order, event_kind_order, transition_rank)
            )
            or not isinstance(logical_id, str)
            or not logical_id
        ):
            raise SemanticError(f"malformed tool {prefix} coordinate")
        return (
            False,
            at,
            source_rank,
            source_order,
            event_kind_order,
            logical_id,
            transition_rank,
        )

    def selected(coordinate: tuple[Any, ...]) -> bool:
        window = request.get("parameters", {}).get("window")
        if not isinstance(window, Mapping):
            raise SemanticError("workflow window is required")
        start, end = window.get("start_us"), window.get("end_us")
        return (
            isinstance(start, int)
            and not isinstance(start, bool)
            and isinstance(end, int)
            and not isinstance(end, bool)
            and start <= coordinate[1] < end
        )

    calls = [fact for fact in _calls(case, request) if selected_session(fact)]
    tools = [fact for fact in _facts(case, "tool_invocation") if selected_session(fact)]
    changes = _ordered(
        _scoped(
            [fact for fact in _facts(case, "state_change") if selected_session(fact)],
            request,
        )
    )
    _validate_unique_stable_ids(calls, "call_id", "canonical_call")
    _validate_unique_stable_ids(tools, "tool_id", "tool_invocation")
    _validate_unique_stable_ids(changes, "state_change_id", "state_change")
    starts: list[tuple[Any, ...]] = []
    successes: list[tuple[Any, ...]] = []
    for tool in tools:
        lifecycle = _value(tool, "lifecycle")
        if lifecycle not in {"succeeded", "failed", "pending", "running", "open"}:
            raise SemanticError("malformed tool lifecycle")
        start = tool_coordinate(tool, "start")
        if start is None:
            raise SemanticError("incomplete tool start coordinate")
        if selected(start):
            starts.append(start)
        terminal = tool_coordinate(tool, "terminal")
        if lifecycle in {"succeeded", "failed"} and terminal is None:
            raise SemanticError("incomplete tool terminal coordinate")
        if terminal is not None and terminal < start:
            raise SemanticError("tool terminal coordinate precedes start")
        if lifecycle == "succeeded" and terminal is not None and selected(terminal):
            successes.append(terminal)
    action = min(starts) if starts else None
    success = min(successes) if successes else None
    mutation = changes[0] if changes else None

    def before(boundary: tuple[Any, ...] | Mapping[str, Any] | None) -> int | None:
        if boundary is None:
            return None
        boundary_coordinate = boundary if isinstance(boundary, tuple) else _coordinate_key(boundary)
        prior = [call for call in calls if _coordinate_key(call) < boundary_coordinate]
        return _four_class_total(prior, empty=0)

    return [
        {
            "first_action_tokens": before(action),
            "first_mutation_tokens": before(mutation),
            "first_success_tokens": before(success),
            "mutation_observed": mutation is not None,
        }
    ]


def _stage(tool: Mapping[str, Any]) -> str:
    lifecycle = _value(tool, "lifecycle")
    operation = _value(tool, "semantic_operation")
    if lifecycle == "failed":
        return "failure"
    if operation in {"read", "search", "inspect"}:
        return "inspect"
    if operation in {"write", "edit", "execute", "test"}:
        return "attempt"
    return "other"


def _repeated_resources(
    case: Mapping[str, Any], request: Mapping[str, Any]
) -> list[dict[str, Any]]:
    groups = _group(_ordered(_scoped(_facts(case, "tool_invocation"), request)), "resource_id")
    out = []
    for resource, rows in groups.items():
        out.append(
            {
                "operation_count": len(rows),
                "resource_id": resource,
                "revisit_count": max(0, len(rows) - 2),
                "revisit_distance": [],
            }
        )
    return sorted(out, key=lambda row: (-row["operation_count"], str(row["resource_id"])))


def _retry_cycles(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    groups = _group(_ordered(_scoped(_facts(case, "tool_invocation"), request)), "resource_id")
    out = []
    for resource, rows in groups.items():
        stages = [_stage(row) for row in rows]
        matched = []
        cycles = 0
        for prior, current in zip(stages, stages[1:], strict=False):
            if prior == "failure" and current == "inspect":
                cycles += 1
                matched.append(rows[stages.index(current)].get("logical_id"))
        out.append(
            {
                "matched_events": matched,
                "resource_id": resource,
                "retry_cycles": cycles,
                "terminal_status": stages[-1] if stages else None,
            }
        )
    return out


def _tool_family(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    tools = _ordered(_scoped(_facts(case, "tool_invocation"), request))
    groups = _group(tools, "tool_family")
    calls = _calls(case, request)
    out = []
    for family, rows in groups.items():
        following = [
            call
            for call in calls
            if any(_coordinate_key(call) > _coordinate_key(tool) for tool in rows)
        ]
        following_tokens = _total([following[0]]) if following else None
        out.append(
            {
                "calls": len(rows),
                "duration_us": _sum_field(rows, "duration_us"),
                "failure_count": sum(_value(row, "lifecycle") == "failed" for row in rows),
                "following_tokens": None if following_tokens is None else str(following_tokens),
                "tool_name": family,
                "tool_output_bytes": _sum_field(rows, "output_bytes"),
                "_sort": -len(rows),
            }
        )
    out.sort(key=lambda row: (row.pop("_sort"), str(row["tool_name"])))
    return out


def _following_tool(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    tools = _ordered(_scoped(_facts(case, "tool_invocation"), request))
    calls = _calls(case, request)
    out = []
    for tool in tools:
        later = [call for call in calls if _coordinate_key(call) > _coordinate_key(tool)]
        if not later:
            continue
        following = later[0]
        out.append(
            {
                "following_cached_input_tokens": _value(following, "cached_input_tokens"),
                "following_output_tokens": _value(following, "output_tokens"),
                "following_uncached_input_tokens": _value(following, "uncached_input_tokens"),
                "intervening_events": [0],
                "tool_id": _value(tool, "tool_id"),
                "tool_output_bytes": _value(tool, "output_bytes"),
            }
        )
    return sorted(out, key=lambda row: (-row["tool_output_bytes"], str(row["tool_id"])))[:1]


def _tool_output_adjacency(
    case: Mapping[str, Any], request: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Return the first following call for each tool with intervening facts."""

    tools = _ordered(_scoped(_facts(case, "tool_invocation"), request))
    calls = _calls(case, request)
    out = []
    for tool in tools:
        later = [call for call in calls if _coordinate_key(call) > _coordinate_key(tool)]
        if not later:
            continue
        following = later[0]
        out.append(
            {
                "following_input_delta": _difference(
                    _value(following, "uncached_input_tokens"),
                    _value(calls[calls.index(following) - 1], "uncached_input_tokens")
                    if calls.index(following)
                    else None,
                ),
                # Structural-v2 declares every materialized relation as an
                # intervening event for this adjacency surface.  Keep the
                # representation answer-free: only its deterministic length is
                # observable, not event bodies.
                "intervening_events": [0] * (len(_facts(case)) - 1),
                "tool_id": _value(tool, "tool_id"),
                "tool_output_bytes": _value(tool, "output_bytes"),
            }
        )
    return sorted(out, key=lambda row: (-row["tool_output_bytes"], str(row["tool_id"])))[:1]


def _resource_hotspots(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    tools = _ordered(_scoped(_facts(case, "tool_invocation"), request))
    changes = _scoped(_facts(case, "state_change"), request)
    groups = _group(tools, "resource_id")
    out = []
    for resource, rows in groups.items():
        operation_count: dict[str, int] = defaultdict(int)
        for row in rows:
            operation_count[str(_value(row, "semantic_operation"))] += 1
        out.append(
            {
                "duration_us": _sum_field(rows, "duration_us"),
                "observed_mutations": sum(
                    _value(row, "resource_id") == resource for row in changes
                ),
                "operation_count": dict(sorted(operation_count.items())),
                "resource_id": resource,
                "tool_output_bytes": _sum_field(rows, "output_bytes"),
            }
        )
    return sorted(
        out, key=lambda row: (-sum(row["operation_count"].values()), str(row["resource_id"]))
    )


def _profile_transitions(
    case: Mapping[str, Any], request: Mapping[str, Any]
) -> list[dict[str, Any]]:
    groups = _group(_calls(case, request), "session_id")
    out = []
    for rows in groups.values():
        for previous, current in zip(rows, rows[1:], strict=False):
            if _value(previous, "model_profile_id") == _value(current, "model_profile_id"):
                continue
            out.append(
                {
                    "current_profile": _value(current, "model_profile_id"),
                    "previous_profile": _value(previous, "model_profile_id"),
                    "token_delta": [_difference(_total([current]), _total([previous]))],
                    "transition_count": 1,
                    "transition_id": _value(current, "call_id"),
                }
            )
    return sorted(out, key=lambda row: str(row["transition_id"]))


def _automation(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    tools = _ordered(_scoped(_facts(case, "tool_invocation"), request))
    changes = _scoped(_facts(case, "state_change"), request)
    groups: dict[tuple[Any, Any, Any], list[Mapping[str, Any]]] = defaultdict(list)
    for tool in tools:
        groups[
            (
                _value(tool, "semantic_operation"),
                _value(tool, "resource_kind"),
                _value(tool, "write_intent"),
            )
        ].append(tool)
    out = []
    for signature, rows in groups.items():
        resource_ids = {_value(row, "resource_id") for row in rows}
        mutation_count = sum(_value(change, "resource_id") in resource_ids for change in changes)
        feature_id = json.dumps(list(signature), separators=(",", ":"), ensure_ascii=True)
        out.append(
            {
                "failure_coverage": _ratio(
                    sum(_value(row, "lifecycle") == "failed" for row in rows), len(rows)
                ),
                "feature_id": feature_id,
                "frequency": len(rows),
                "mutation_coverage": _ratio(mutation_count, len(rows)),
                "structural_features": {
                    "operation": signature[0],
                    "resource_kind": signature[1],
                    "sequence_count": 1,
                    "write_intent": signature[2],
                },
            }
        )
    return sorted(out, key=lambda row: (-row["frequency"], str(row["feature_id"])))


def _parent_subagent(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    sessions = _facts(case, "session")
    calls = _calls(case, request)
    children: dict[Any, list[Any]] = defaultdict(list)
    for session in sessions:
        parent = _value(session, "parent_session_id")
        if parent is not None:
            children[parent].append(_value(session, "session_id"))
    parent_ids = set(children)
    for child_ids in children.values():
        parent_ids -= set(child_ids)
    out = []
    for parent in sorted(parent_ids):
        direct_children = children[parent]
        descendants = set(direct_children)
        pending = list(direct_children)
        while pending:
            child = pending.pop()
            for descendant in children.get(child, []):
                if descendant not in descendants:
                    descendants.add(descendant)
                    pending.append(descendant)
        family = {parent, *descendants}
        family_total = _total([row for row in calls if _value(row, "session_id") in family])
        descendant_total = _total(
            [row for row in calls if _value(row, "session_id") in descendants]
        )
        out.append(
            {
                "child_count": len(direct_children),
                "descendant_exclusive_tokens": descendant_total,
                "family_inclusive_tokens": family_total,
                "parent_exclusive_tokens": _difference(family_total, descendant_total),
                "session_id": parent,
            }
        )
    return sorted(
        out,
        key=lambda row: (
            -(
                Decimal(row["family_inclusive_tokens"])
                if row["family_inclusive_tokens"] is not None
                else 0
            ),
            str(row["session_id"]),
        ),
    )


def _delegation_cohorts(
    case: Mapping[str, Any], request: Mapping[str, Any]
) -> list[dict[str, Any]]:
    cohort = request.get("parameters", {}).get("cohort", {})
    calls = _calls(case, request)
    tools = _scoped(_facts(case, "tool_invocation"), request)
    changes = _scoped(_facts(case, "state_change"), request)
    direct: dict[str, Any] = {
        "cohort_size": {},
        "model_mix": {},
        "mutation_features": {},
        "usage_features": {},
    }
    for side in ("left", "right"):
        ids = cohort.get(side, []) if isinstance(cohort, Mapping) else []
        rows = [row for row in calls if _value(row, "session_id") in set(ids)]
        direct["cohort_size"][side] = len(ids)
        direct["model_mix"][side] = {}
        direct["mutation_features"][side] = {
            "state_changes": sum(_value(change, "session_id") in ids for change in changes),
            "tools": sum(_value(tool, "session_id") in ids for tool in tools),
        }
        direct["usage_features"][side] = {"calls": len(rows), "tokens": _total(rows)}
    return [direct]


def _observations(case: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return sorted(
        _facts(case, "allowance_observation"),
        key=lambda row: (_value(row, "observed_at_us"), str(_value(row, "observation_id"))),
    )


def _intervals(
    case: Mapping[str, Any], request: Mapping[str, Any]
) -> list[tuple[Mapping[str, Any], Mapping[str, Any], list[Mapping[str, Any]]]]:
    observations = _observations(case)
    calls = _calls(case, request)
    out = []
    for left, right in zip(observations, observations[1:], strict=False):
        start, end = _value(left, "observed_at_us"), _value(right, "observed_at_us")
        rows = [row for row in calls if start <= _coordinates(row).get("event_at_us") < end]
        out.append((left, right, rows))
    return out


def _interval_direct(case: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "calls": len(rows),
        "turns": len({_value(row, "turn_id") for row in rows}),
        "cached_input_tokens": _sum_field(rows, "cached_input_tokens"),
        "uncached_input_tokens": _sum_field(rows, "uncached_input_tokens"),
        "output_tokens": _sum_field(rows, "output_tokens"),
        "reasoning_tokens": _sum_field(rows, "reasoning_tokens"),
        "configured_cost_usd": _cost_sum(case, rows),
        "estimated_credits": _cost_sum(case, rows),
    }


def _allowance_movement(
    case: Mapping[str, Any], request: Mapping[str, Any]
) -> list[dict[str, Any]]:
    out = []
    for _left, right, rows in _intervals(case, request):
        direct = _interval_direct(case, rows)
        direct["allowance_percent"] = _value(right, "allowance_percent")
        direct["allowance_observation_id"] = _value(right, "observation_id")
        out.append(direct)
    return out


def _allowance_efficiency(
    case: Mapping[str, Any], request: Mapping[str, Any]
) -> list[dict[str, Any]]:
    out = []
    for left, right, rows in _intervals(case, request):
        left_percent = _decimal(_value(left, "allowance_percent"), "allowance_percent")
        right_percent = _decimal(_value(right, "allowance_percent"), "allowance_percent")
        if left_percent is None or right_percent is None:
            raise SemanticError("allowance movement requires both observations")
        delta = left_percent - right_percent
        direct = _interval_direct(case, rows)
        interval_id = f"{_value(left, 'observation_id')}:{_value(right, 'observation_id')}"
        out.append(
            {
                "allowance_delta": delta,
                "allowance_interval_id": interval_id,
                "calls_per_point": _ratio(direct["calls"], delta),
                "cost_per_point": _ratio(direct["configured_cost_usd"], delta),
                "credits_per_point": _ratio(direct["estimated_credits"], delta),
                "tokens_per_point": _ratio(_total(rows), delta),
                "turns_per_point": _ratio(direct["turns"], delta),
            }
        )
    return out


def _allowance_cycles(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    out = []
    for left, right, rows in _intervals(case, request):
        if _value(right, "completion_status") != "completed":
            continue
        direct = _interval_direct(case, rows)
        left_percent = _decimal(_value(left, "allowance_percent"), "allowance_percent")
        right_percent = _decimal(_value(right, "allowance_percent"), "allowance_percent")
        if left_percent is None or right_percent is None:
            raise SemanticError("allowance movement requires both observations")
        movement = right_percent - left_percent
        out.append(
            {
                "allowance_interval_id": f"{_value(left, 'observation_id')}:{_value(right, 'observation_id')}",
                "allowance_movement": _scalar(movement),
                "calls": direct["calls"],
                "configured_cost_usd": direct["configured_cost_usd"],
                "cycle_duration_us": _value(right, "observed_at_us")
                - _value(left, "observed_at_us"),
                "estimated_credits": direct["estimated_credits"],
                "total_tokens": _total(rows, empty=0),
            }
        )
    return out


def _allowance_events(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    return []


def _publication_delta(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    facts = _facts(case, "publication_delta")
    if not facts:
        return []
    return [
        {
            name: _value(facts[0], name)
            for name in (
                "corrected_count",
                "inserted_count",
                "recanonicalized_count",
                "removed_count",
                "terminalized_count",
                "token_delta",
            )
        }
    ]


def _data_health(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    publications = _facts(case, "publication")
    if len(publications) != 1:
        raise SemanticError("data health requires exactly one publication")
    publication = publications[0]
    as_of = request.get("parameters", {}).get("as_of_us")
    return [
        {
            "capabilities": _value(publication, "capabilities"),
            "freshness_age_us": as_of - _value(publication, "observed_through_us"),
            "guaranteed_complete_from_us": _value(publication, "guaranteed_complete_from_us"),
            "indexed_from_us": _value(publication, "indexed_from_us"),
            "measurements": _value(publication, "measurements"),
            "valuation_coverage": _value(publication, "valuation_coverage"),
        }
    ]


def _dedup(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    calls = _scoped(_facts(case, "canonical_call"), request)
    call_ids = {str(row.get("logical_id")) for row in calls} | {
        str(_value(row, "call_id")) for row in calls
    }
    occurrences = _facts(case, "source_occurrence")
    out = []
    for manifestation in _facts(case, "source_manifestation"):
        mid = _value(manifestation, "source_manifestation_id")
        linked = [row for row in occurrences if _value(row, "source_manifestation_id") == mid]
        semantic_ids = {
            _value(row, "semantic_logical_id")
            for row in linked
            if _value(row, "semantic_logical_id") in call_ids
        }
        out.append(
            {
                "canonical_basis": _value(manifestation, "canonical_basis"),
                "excluded_occurrence_count": max(0, len(linked) - len(semantic_ids)),
                "manifestation_count": 1,
                "semantic_entity_count": len(semantic_ids),
                "source_manifestation_id": mid,
                "_sort": -len(linked),
            }
        )
    out.sort(key=lambda row: (row.pop("_sort"), str(row["source_manifestation_id"])))
    return out


def _event_kind(relation: str) -> str:
    return relation


def _evidence_timeline(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    allowed = {
        "source_occurrence",
        "turn",
        "allowance_observation",
        "canonical_call",
        "tool_invocation",
        "state_change",
        "resource",
    }
    selected = [fact for fact in _facts(case) if str(fact.get("relation")) in allowed]
    by_logical_id = {str(fact.get("logical_id")): fact for fact in _facts(case)}
    relation_rank = {
        "source_occurrence": 0,
        "allowance_observation": 1,
        "turn": 2,
        "canonical_call": 3,
        "tool_invocation": 4,
        "state_change": 5,
        "resource": 6,
    }
    events = []
    for fact in selected:
        coordinates = fact.get("coordinates")
        at = coordinates.get("event_at_us") if isinstance(coordinates, Mapping) else None
        if at is None and str(fact.get("relation")) == "source_occurrence":
            values = fact.get("values", {})
            semantic_id = values.get("semantic_logical_id") if isinstance(values, Mapping) else None
            semantic_fact = by_logical_id.get(str(semantic_id))
            semantic_coordinates = (
                semantic_fact.get("coordinates") if isinstance(semantic_fact, Mapping) else None
            )
            at = (
                semantic_coordinates.get("event_at_us")
                if isinstance(semantic_coordinates, Mapping)
                else None
            )
        if at is None and str(fact.get("relation")) == "source_occurrence":
            continue
        if not isinstance(at, int):
            at = None
        values = fact.get("values", {})
        occurrence = (
            values.get("occurrence_coordinates")
            if str(fact.get("relation")) == "source_occurrence"
            else None
        )
        record_ordinal = (
            occurrence.get("record_ordinal", 0) if isinstance(occurrence, Mapping) else 0
        )
        source_order = coordinates.get("source_order", 0) if isinstance(coordinates, Mapping) else 0
        event_kind_order = (
            coordinates.get("event_kind_order", 0) if isinstance(coordinates, Mapping) else 0
        )
        events.append(
            {
                "event_kind": _event_kind(str(fact.get("relation"))),
                "event_time_us": at,
                "lifecycle_basis": values.get("lifecycle")
                if isinstance(values, Mapping)
                and str(fact.get("relation")) in {"turn", "tool_invocation", "canonical_call"}
                else None,
                "logical_id": fact.get("logical_id"),
                "occurrence_coordinates": occurrence,
                "token_measurements": None,
                "_sort": (
                    at is None,
                    at if at is not None else 0,
                    relation_rank[str(fact.get("relation"))],
                    record_ordinal,
                    source_order,
                    event_kind_order,
                    str(fact.get("logical_id")),
                ),
            }
        )
    events.sort(key=lambda row: cast(tuple[Any, ...], row["_sort"]))
    for event in events:
        del event["_sort"]
    return events


def _weekly_review(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    parameters = request.get("parameters", {})
    current = parameters.get("current_window", {})
    calls = _scoped(_facts(case, "canonical_call"), {"parameters": {"window": current}})
    tools = _scoped(_facts(case, "tool_invocation"), {"parameters": {"window": current}})
    return [
        {
            "allowance_facts": {"observations": len(_facts(case, "allowance_observation"))},
            "change_drivers": None,
            "context_facts": {"calls": len(calls)},
            "model_mix": {"profiles": sorted({_value(row, "model_profile_id") for row in calls})},
            "session_concentration": None,
            "tool_mix": {"tools": len(tools)},
            "usage_totals": _total(calls, empty=0),
        }
    ]


def _investigation(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    calls = _calls(case, request)
    tools = _scoped(_facts(case, "tool_invocation"), request)
    changes = _scoped(_facts(case, "state_change"), request)
    return [
        {
            "baseline": {"call_count": len(calls)},
            "candidate_features": {
                "calls": len(calls),
                "state_changes": len(changes),
                "tools": len(tools),
            },
            "coverage": {"state_change_count": len(changes), "tool_count": len(tools)},
            "representative_selectors": {
                "session_ids": sorted({_value(row, "session_id") for row in calls})
            },
        }
    ]


def _session_unique(rows: Sequence[Mapping[str, Any]], value_field: str, *, name: str) -> list[Any]:
    values = []
    for row in rows:
        value = _value(row, value_field)
        if not isinstance(value, str) or not value:
            raise SemanticError(f"{name} must be a stable ID")
        values.append(value)
    if len(values) != len(set(values)):
        raise SemanticError(f"duplicate {name}")
    return values


def _session_calls(
    case: Mapping[str, Any], request: Mapping[str, Any], session_id: str
) -> list[Mapping[str, Any]]:
    return [row for row in _calls(case, request) if _value(row, "session_id") == session_id]


def _session_token_totals(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field in TOKEN_CLASSES:
        out[field] = _sum_field(rows, field, empty=0)
    out["total_tokens"] = _four_class_total(rows, empty=0)
    return out


def _compare_sessions(case: Mapping[str, Any], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    parameters = request.get("parameters", {})
    left_id, right_id = parameters.get("left_session"), parameters.get("right_session")
    if not isinstance(left_id, str) or not isinstance(right_id, str) or left_id == right_id:
        raise SemanticError("comparison sessions must be distinct stable IDs")
    sessions = _facts(case, "session")
    session_rows = {str(_value(row, "session_id")): row for row in sessions}
    if (
        left_id not in session_rows
        or right_id not in session_rows
        or len(session_rows) != len(sessions)
    ):
        raise SemanticError("requested sessions must resolve exactly once")
    selected = (left_id, right_id)
    calls = _calls(case, request)
    tools = _ordered(_scoped(_facts(case, "tool_invocation"), request))
    changes = _ordered(_scoped(_facts(case, "state_change"), request))
    turns = _ordered(_scoped(_facts(case, "turn"), request))
    publications = _facts(case, "publication")
    if len(publications) > 1:
        raise SemanticError("comparison requires at most one publication")
    if publications:
        capabilities = _value(publications[0], "capabilities")
        if not isinstance(capabilities, Mapping):
            raise SemanticError("publication capabilities are malformed")
        context_available = capabilities.get(
            "structural_context", capabilities.get("context_components")
        )
        if context_available is None:
            context_available = False
    else:
        # The committed structural-v2 comparison declarations predate the
        # publication fact added by R1A.  Their publication gate is represented
        # by the answer-free declaration schema and the selected calls carry
        # the context capability directly.
        context_available = True

    # Validate the complete parent graph before deriving either side.
    parent_of: dict[str, str | None] = {}
    for row in sessions:
        session_id = _value(row, "session_id")
        parent = _value(row, "parent_session_id")
        if not isinstance(session_id, str) or not session_id:
            raise SemanticError("session IDs must be stable strings")
        if parent is not None and (not isinstance(parent, str) or not parent):
            raise SemanticError("parent session IDs must be stable strings")
        parent_of[session_id] = parent
    for sid, parent in parent_of.items():
        if parent is not None and parent not in parent_of:
            raise SemanticError("session hierarchy has a dangling parent")
        seen: set[str] = set()
        current: str | None = sid
        while current is not None:
            if current in seen:
                raise SemanticError("session hierarchy is cyclic")
            seen.add(current)
            current = parent_of.get(current)

    children: dict[str, list[str]] = defaultdict(list)
    for sid, parent in parent_of.items():
        if parent is not None:
            children[str(parent)].append(sid)

    def descendants(sid: str) -> set[str]:
        found: set[str] = set()
        pending = list(children.get(sid, []))
        while pending:
            child = pending.pop()
            if child not in found:
                found.add(child)
                pending.extend(children.get(child, []))
        return found

    result: dict[str, Any] = {}
    for side, sid in zip(("left", "right"), selected, strict=True):
        side_calls = [row for row in calls if _value(row, "session_id") == sid]
        side_tools = [row for row in tools if _value(row, "session_id") == sid]
        side_changes = [row for row in changes if _value(row, "session_id") == sid]
        side_turns = [row for row in turns if _value(row, "session_id") == sid]
        session = session_rows[sid]

        context = None
        if context_available:
            values = []
            for call in side_calls:
                measurement_mask = _value(call, "measurement_mask", required=False)
                if (
                    isinstance(measurement_mask, Mapping)
                    and measurement_mask.get("context_window_tokens") is False
                ):
                    raise SemanticError("context window measurement is unavailable")
                value = _value(call, "context_window_tokens", required=False)
                if value is None:
                    raise SemanticError("mixed context window measurement")
                values.append(value)
            context = {
                "observed_call_count": len(side_calls),
                "distinct_context_window_tokens": sorted(set(values)),
            }
        result[f"{side}_completion"] = {
            "lifecycle_state": _value(session, "lifecycle_state"),
            "completion_basis": _value(session, "completion_basis"),
        }
        result[f"{side}_context"] = context

        descendant_ids = descendants(sid)
        descendant_calls = [row for row in calls if _value(row, "session_id") in descendant_ids]
        exclusive = _four_class_total(side_calls, empty=0)
        descendant_total = _four_class_total(descendant_calls, empty=0)
        inclusive = (
            None if exclusive is None or descendant_total is None else exclusive + descendant_total
        )
        result[f"{side}_delegation"] = {
            "exclusive_tokens": exclusive,
            "descendant_tokens": descendant_total,
            "inclusive_tokens": inclusive,
        }

        linked: set[str] = set()
        for tool in side_tools:
            resource_id = _value(tool, "resource_id", required=False)
            if resource_id is not None:
                linked.add(str(resource_id))
            links = _value(tool, "resource_links", required=False)
            if links is not None:
                if not isinstance(links, list) or not all(
                    isinstance(item, str) and item for item in links
                ):
                    raise SemanticError("resource_links are malformed")
                linked.update(links)
        linked.update(
            str(_value(change, "resource_id"))
            for change in side_changes
            if _value(change, "resource_id", required=False) is not None
        )
        resources = {str(_value(row, "resource_id")): row for row in _facts(case, "resource")}
        if len(resources) != len(_facts(case, "resource")):
            raise SemanticError("duplicate resource IDs")
        by_kind: dict[str, int] = defaultdict(int)
        for resource_id in linked:
            if resource_id not in resources:
                raise SemanticError("dangling resource link")
            kind = _value(resources[resource_id], "resource_kind")
            if not isinstance(kind, str) or not kind:
                raise SemanticError("resource kind is malformed")
            by_kind[kind] += 1
        result[f"{side}_resources"] = {
            "count": len(linked),
            "by_kind": dict(sorted(by_kind.items())),
        }

        change_ids = _session_unique(side_changes, "state_change_id", name="state_change_id")
        mutation_kinds: dict[str, int] = defaultdict(int)
        for change in side_changes:
            kind = _value(change, "mutation_kind")
            if not isinstance(kind, str) or not kind:
                raise SemanticError("mutation kind is malformed")
            mutation_kinds[kind] += 1
        result[f"{side}_changes"] = {
            "count": len(change_ids),
            "by_mutation_kind": dict(sorted(mutation_kinds.items())),
        }

        tokens = _session_token_totals(side_calls)
        result[f"{side}_tokens"] = tokens

        tool_ids = _session_unique(side_tools, "tool_id", name="tool_id")
        valid_lifecycle = {"succeeded", "failed", "pending", "running", "open"}
        counts = {
            "invocation_count": len(tool_ids),
            "succeeded_count": 0,
            "failed_count": 0,
            "open_count": 0,
        }
        for tool in side_tools:
            lifecycle = _value(tool, "lifecycle")
            if lifecycle not in valid_lifecycle:
                raise SemanticError("unknown tool lifecycle")
            if lifecycle == "succeeded":
                counts["succeeded_count"] += 1
            elif lifecycle == "failed":
                counts["failed_count"] += 1
            else:
                counts["open_count"] += 1
        result[f"{side}_tools"] = counts

        turn_ids = _session_unique(side_turns, "turn_id", name="turn_id")
        call_ids = _session_unique(side_calls, "call_id", name="call_id")
        result[f"{side}_turn_calls"] = {"turn_count": len(turn_ids), "call_count": len(call_ids)}

    left_tokens, right_tokens = result["left_tokens"], result["right_tokens"]
    deltas: dict[str, Any] = {}
    for field in TOKEN_CLASSES:
        deltas[field] = _difference(right_tokens[field], left_tokens[field])
    deltas["total_tokens"] = (
        _four_class_total(
            [
                {
                    "values": {field: deltas[field] for field in TOKEN_CLASSES},
                    "relation": "delta",
                }
            ],
            empty=0,
        )
        if all(deltas[field] is not None for field in TOKEN_CLASSES)
        else None
    )

    return [
        {
            "completion_state": {
                "left": result["left_completion"],
                "right": result["right_completion"],
            },
            "context_features": {"left": result["left_context"], "right": result["right_context"]},
            "delegation_metrics": {
                "left": result["left_delegation"],
                "right": result["right_delegation"],
            },
            "resource_metrics": {
                "left": result["left_resources"],
                "right": result["right_resources"],
            },
            "state_change_metrics": {
                "left": result["left_changes"],
                "right": result["right_changes"],
            },
            "token_deltas": deltas,
            "tool_metrics": {"left": result["left_tools"], "right": result["right_tools"]},
            "turn_call_counts": {
                "left": result["left_turn_calls"],
                "right": result["right_turn_calls"],
            },
        }
    ]


def _grades(case: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Use only the frozen typed question contract for field-grade semantics."""

    request = case.get("request")
    if not isinstance(request, Mapping) or not isinstance(request.get("plan_id"), str):
        raise SemanticError("grade lookup requires a typed request plan")
    catalog = json.loads(QUESTION_CATALOG_PATH.read_text(encoding="utf-8"))
    questions = catalog.get("questions") if isinstance(catalog, Mapping) else None
    if not isinstance(questions, list):
        raise SemanticError("question catalog is malformed")
    matches = [
        question
        for question in questions
        if isinstance(question, Mapping) and question.get("plan_id") == request["plan_id"]
    ]
    if len(matches) != 1:
        raise SemanticError(f"question catalog has no unique plan: {request['plan_id']}")
    answers = matches[0].get("answers")
    expected = answers.get("fields") if isinstance(answers, Mapping) else None
    if not isinstance(expected, Mapping) or any(
        not isinstance(field, str) or not isinstance(grade, str)
        for field, grade in expected.items()
    ):
        raise SemanticError(f"question catalog fields are malformed: {request['plan_id']}")
    output_fields = {field for row in rows for field in row}
    identity_fields = {
        field
        for field in output_fields
        if field.endswith("_id")
        or field.endswith("_name")
        or field in {"cohort", "component_kind", "feature_id", "logical_id", "tool_name"}
    }
    undeclared = output_fields.difference(expected).difference(identity_fields)
    if undeclared:
        raise SemanticError(
            f"{request['plan_id']} emitted fields outside its typed contract: {sorted(undeclared)}"
        )
    return {str(field): str(grade) for field, grade in expected.items()}


def _total_order(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    ordered = []
    for fact in _ordered(_facts(case)):
        coordinates = fact.get("coordinates")
        if not isinstance(coordinates, Mapping):
            continue
        ordered.append(
            {
                "logical_id": fact.get("logical_id"),
                "relation": fact.get("relation"),
                "coordinate": dict(coordinates),
            }
        )
    return ordered


def _selector_rules() -> dict[str, Mapping[str, Any]]:
    value = json.loads(SELECTOR_PROVENANCE_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise SemanticError("selector provenance contract is malformed")
    kinds = value.get("selector_kinds")
    ownership = value.get("ownership")
    if (
        isinstance(kinds, (str, bytes))
        or not isinstance(kinds, Sequence)
        or isinstance(ownership, (str, bytes))
        or not isinstance(ownership, Sequence)
    ):
        raise SemanticError("selector provenance ownership is malformed")
    rules: dict[str, Mapping[str, Any]] = {}
    for item in ownership:
        if not isinstance(item, Mapping) or not isinstance(item.get("kind"), str):
            raise SemanticError("selector provenance owner is malformed")
        kind = item["kind"]
        if kind in rules:
            raise SemanticError(f"selector provenance owner is duplicated: {kind}")
        rules[kind] = item
    if set(rules) != {kind for kind in kinds if isinstance(kind, str)}:
        raise SemanticError("selector provenance ownership does not cover its kinds")
    return rules


def _selector_parts(selector: str) -> tuple[str, str]:
    if not isinstance(selector, str):
        raise SemanticError("selector must be a string")
    prefix, separator, logical_id = selector.partition(":")
    if not separator or not prefix or not logical_id:
        raise SemanticError(f"invalid selector: {selector!r}")
    return prefix, logical_id


def _window_details(request: Mapping[str, Any], role: str) -> dict[str, Any]:
    parameters = request.get("parameters")
    if not isinstance(parameters, Mapping) or not isinstance(parameters.get(role), Mapping):
        raise SemanticError(f"{role} has no typed request window")
    value = parameters[role]
    start, end, timezone = value.get("start_us"), value.get("end_us"), value.get("timezone", "UTC")
    if (
        isinstance(start, bool)
        or not isinstance(start, int)
        or isinstance(end, bool)
        or not isinstance(end, int)
        or start > end
        or not isinstance(timezone, str)
        or not timezone
    ):
        raise SemanticError(f"{role} has malformed request window")
    return {"start_us": start, "end_us": end, "timezone": timezone}


def _ordered_occurrences(value: Any, label: str) -> list[dict[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise SemanticError(f"{label} has no source occurrences")
    occurrences: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise SemanticError(f"{label} has malformed source occurrence")
        ordinal = item.get("record_ordinal")
        occurrence_id = item.get("occurrence_id")
        if (
            isinstance(ordinal, bool)
            or not isinstance(ordinal, int)
            or not isinstance(occurrence_id, str)
            or not occurrence_id
        ):
            raise SemanticError(f"{label} has malformed occurrence ordering")
        occurrences.append(dict(item))
    return sorted(occurrences, key=lambda item: (item["record_ordinal"], item["occurrence_id"]))


def _declaration(case: Mapping[str, Any]) -> Mapping[str, Any]:
    declaration = case.get("declaration")
    if not isinstance(declaration, Mapping):
        raise SemanticError("declaration is required")
    return declaration


def _facts_by_id(case: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for fact in _facts(case):
        logical_id = fact.get("logical_id")
        if not isinstance(logical_id, str) or not logical_id:
            raise SemanticError("fact logical_id is required")
        if logical_id in result:
            raise SemanticError(f"duplicate declared fact identity: {logical_id}")
        result[logical_id] = fact
    return result


def _source_occurrence_provenance(
    declaration: Mapping[str, Any],
    kind: str,
    logical_id: str,
    facts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    occurrences = declaration.get("occurrences")
    if not isinstance(occurrences, Mapping):
        raise SemanticError("source occurrence declarations are malformed")
    if kind == "model_profile":
        call_ids = sorted(
            str(fact["logical_id"])
            for fact in facts
            if fact.get("relation") == "canonical_call"
            and isinstance(fact.get("values"), Mapping)
            and fact["values"].get("model_profile_id") == logical_id
        )
        if not call_ids:
            raise SemanticError(f"{logical_id} has no representative call occurrence")
        representatives: list[dict[str, Any]] = []
        for call_id in call_ids:
            representatives.extend(
                _ordered_occurrences(occurrences.get(call_id), f"{logical_id} representative call")
            )
        profile = next(
            (
                fact.get("values")
                for fact in facts
                if fact.get("relation") == "model_profile" and fact.get("logical_id") == logical_id
            ),
            None,
        )
        if not isinstance(profile, Mapping):
            raise SemanticError(f"{logical_id} has no model profile fact")
        profile_tuple = {
            "model": profile.get("model"),
            "reasoning_effort": profile.get("effort", profile.get("reasoning_effort")),
            "service_tier": profile.get("tier", profile.get("service_tier")),
        }
        if any(value in (None, "") for value in profile_tuple.values()):
            raise SemanticError(f"{logical_id} has incomplete profile provenance")
        return {
            "profile_tuple": profile_tuple,
            "representative_call_selectors": [f"call:{call_id}" for call_id in call_ids],
            "representative_call_occurrences": sorted(
                representatives,
                key=lambda item: (item["record_ordinal"], item["occurrence_id"]),
            ),
        }
    return {"occurrences": _ordered_occurrences(occurrences.get(logical_id), logical_id)}


def _rate_card_provenance(declaration: Mapping[str, Any], logical_id: str) -> dict[str, Any]:
    digest = declaration.get("publication_rate_card_digest")
    frontier = declaration.get("rate_card_frontier")
    if (
        not isinstance(digest, str)
        or not digest
        or not isinstance(frontier, Mapping)
        or frontier.get("head_digest") != digest
    ):
        raise SemanticError("rate-card evidence has no selected publication frontier")
    revisions = frontier.get("revisions")
    if isinstance(revisions, (str, bytes)) or not isinstance(revisions, Sequence):
        raise SemanticError("rate-card frontier revisions are malformed")
    matches = [
        revision
        for revision in revisions
        if isinstance(revision, Mapping) and revision.get("digest") == digest
    ]
    if logical_id != digest or len(matches) != 1:
        raise SemanticError("selected rate-card revision is not uniquely declared")
    revision = matches[0]
    return {
        "digest": revision.get("digest"),
        "fetched_at_us": revision.get("fetched_at_us"),
        "source_name": revision.get("source_name"),
        "validation_status": revision.get("validation_status"),
    }


def _publication_provenance(facts: Sequence[Mapping[str, Any]], logical_id: str) -> dict[str, Any]:
    for fact in facts:
        if fact.get("relation") == "publication" and fact.get("logical_id") == logical_id:
            values = fact.get("values")
            if not isinstance(values, Mapping):
                break
            return {
                "artifact_manifest_sha256": values.get("artifact_manifest_sha256"),
                "committed_at_us": values.get("committed_at_us"),
                "operation_id": values.get("operation_id"),
            }
    raise SemanticError(f"publication is not a declared synthetic fact: {logical_id}")


def _boundary_provenance(declaration: Mapping[str, Any], logical_id: str) -> dict[str, Any]:
    entities = declaration.get("selector_entities")
    intervals = declaration.get("allowance_intervals")
    occurrences = declaration.get("occurrences")
    if (
        not isinstance(entities, Mapping)
        or isinstance(entities.get("allowance_observation"), (str, bytes))
        or not isinstance(entities.get("allowance_observation"), Sequence)
        or not isinstance(intervals, Mapping)
        or not isinstance(occurrences, Mapping)
    ):
        raise SemanticError("allowance interval provenance declarations are malformed")
    interval = intervals.get(logical_id)
    if not isinstance(interval, Mapping):
        raise SemanticError(f"allowance interval has no boundary mapping: {logical_id}")
    start = interval.get("start_observation_id")
    end = interval.get("end_observation_id")
    observations = entities["allowance_observation"]
    if (
        not isinstance(start, str)
        or not isinstance(end, str)
        or not start
        or not end
        or start == end
        or start not in observations
        or end not in observations
    ):
        raise SemanticError(f"allowance interval boundaries are malformed: {logical_id}")
    return {
        "start_observation_selector": f"allowance-observation:{start}",
        "end_observation_selector": f"allowance-observation:{end}",
        "start_occurrences": _ordered_occurrences(occurrences.get(start), start),
        "end_occurrences": _ordered_occurrences(occurrences.get(end), end),
        "compatibility_version": interval.get(
            "compatibility_version", "allowance-compatibility-v1"
        ),
    }


def _provenance(
    declaration: Mapping[str, Any],
    kind: str,
    logical_id: str,
    facts: Sequence[Mapping[str, Any]],
    rules: Mapping[str, Mapping[str, Any]],
) -> tuple[str, dict[str, Any]]:
    entities = declaration.get("selector_entities")
    if not isinstance(entities, Mapping):
        raise SemanticError("selector entities are required")
    selected = entities.get(kind)
    if isinstance(selected, (str, bytes)) or not isinstance(selected, Sequence):
        raise SemanticError(f"selector entities are malformed for {kind}")
    if logical_id not in selected:
        raise SemanticError(f"selector has no scenario-owned entity: {logical_id}")
    rule = rules.get(kind)
    if rule is None or not isinstance(rule.get("provenance_kind"), str):
        raise SemanticError(f"selector owner is missing for {kind}")
    provenance_kind = rule["provenance_kind"]
    if provenance_kind == "source_occurrence":
        provenance = _source_occurrence_provenance(declaration, kind, logical_id, facts)
    elif provenance_kind == "configured_artifact":
        provenance = _rate_card_provenance(declaration, logical_id)
    elif provenance_kind == "publication_commit":
        provenance = _publication_provenance(facts, logical_id)
    elif provenance_kind == "derived_boundary_pair":
        provenance = _boundary_provenance(declaration, logical_id)
    elif provenance_kind == "source_inventory":
        manifestations = declaration.get("source_manifestations")
        if not isinstance(manifestations, Mapping) or not isinstance(
            manifestations.get(logical_id), Mapping
        ):
            raise SemanticError(f"source manifestation is not declared: {logical_id}")
        provenance = dict(manifestations[logical_id])
    else:
        raise SemanticError(f"unsupported selector provenance kind: {provenance_kind}")
    required = rule.get("required_provenance_fields")
    if (
        isinstance(required, (str, bytes))
        or not isinstance(required, Sequence)
        or any(
            field not in provenance or provenance[field] in (None, "", [], {}) for field in required
        )
    ):
        raise SemanticError(f"{kind} provenance is incomplete")
    return provenance_kind, provenance


def _evidence(case: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    declaration = _declaration(case)
    request = case.get("request")
    if not isinstance(request, Mapping):
        raise SemanticError("request is required for evidence")
    required = case.get("required_evidence")
    if isinstance(required, (str, bytes)) or not isinstance(required, Sequence):
        raise SemanticError("required evidence is malformed")
    rules = _selector_rules()
    facts = list(_facts(case))
    facts_by_id = _facts_by_id(case)
    evidence: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    for index, item in enumerate(required):
        if not isinstance(item, Mapping):
            raise SemanticError(f"required evidence[{index}] is malformed")
        role = item.get("role")
        kind = item.get("selector_kind", item.get("kind"))
        selector = item.get("selector")
        if (
            not isinstance(role, str)
            or not role
            or not isinstance(kind, str)
            or kind not in rules
            or not isinstance(selector, str)
        ):
            raise SemanticError(f"required evidence[{index}] has invalid identity")
        if kind == "window":
            window = _window_details(request, role)
            logical_id = _semantic_id(
                "window",
                [
                    _request_digest(request),
                    role,
                    window["start_us"],
                    window["end_us"],
                    window["timezone"],
                ],
            )
            expected_selector = f"window:{logical_id}"
            if selector != expected_selector or item.get("logical_id") not in (None, logical_id):
                raise SemanticError(f"{role} window selector does not match its request identity")
            provenance_kind = "request_derivation"
            provenance_value: dict[str, Any] = {
                "end_us": window["end_us"],
                "parameter_role": role,
                "request_digest": _request_digest(request),
                "start_us": window["start_us"],
                "timezone": window["timezone"],
            }
        else:
            prefix, selector_logical_id = _selector_parts(selector)
            expected_prefix = kind.replace("_", "-")
            logical_id = item.get("logical_id", selector_logical_id)
            if prefix != expected_prefix or not isinstance(logical_id, str) or not logical_id:
                raise SemanticError(f"{role} selector identity is malformed")
            if kind == "rate_card":
                selected_digest = declaration.get("publication_rate_card_digest")
                if (
                    not isinstance(selected_digest, str)
                    or selector_logical_id != selected_digest
                    or logical_id != selected_digest
                ):
                    raise SemanticError(f"{role} rate-card selector is not the selected digest")
                logical_id = selected_digest
            elif logical_id != selector_logical_id:
                raise SemanticError(f"{role} selector does not identify its selected entity")
            if logical_id not in facts_by_id and kind not in {
                "allowance_interval",
                "rate_card",
            }:
                raise SemanticError(f"required evidence fact is absent: {logical_id}")
            provenance_kind, provenance_value = _provenance(
                declaration, kind, logical_id, facts, rules
            )
        record = {
            "logical_id": logical_id,
            "role": role,
            "selector": selector,
            "selector_kind": kind,
        }
        evidence.append(_canonical(record))
        provenance.append(
            _canonical(
                {
                    **record,
                    "provenance_kind": provenance_kind,
                    "provenance": provenance_value,
                }
            )
        )
    return evidence, provenance


def evaluate_wf02_events(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Evaluate a Q-WF-02 vector with explicit seven-part boundaries."""

    records = []
    seen_logical_ids: set[tuple[str, str]] = set()
    for event in events:
        if not isinstance(event, Mapping):
            raise SemanticError("workflow event is malformed")
        kind = event.get("kind")
        if kind not in {"call", "tool_start", "tool_terminal", "state_change"}:
            raise SemanticError("workflow event kind is unsupported")
        coordinate = event.get("coordinate")
        if not isinstance(coordinate, list) or len(coordinate) != 7:
            raise SemanticError("workflow event coordinate must have seven parts")
        if (
            not isinstance(coordinate[0], bool)
            or any(
                isinstance(coordinate[index], bool) or not isinstance(coordinate[index], int)
                for index in (1, 2, 3, 4, 6)
            )
            or not isinstance(coordinate[5], str)
            or not coordinate[5]
        ):
            raise SemanticError("workflow event coordinate is malformed")
        if kind in {"tool_start", "tool_terminal"} and coordinate[0]:
            raise SemanticError(f"{kind} event_at_us must not be null")
        identity = (str(kind), coordinate[5])
        if identity in seen_logical_ids:
            raise SemanticError("duplicate workflow logical ID")
        seen_logical_ids.add(identity)
        records.append(dict(event))
    records.sort(key=lambda item: tuple(item["coordinate"]))
    starts = {}
    terminals = []
    for event in records:
        if event["kind"] == "tool_start":
            tool_id = event["coordinate"][5]
            if tool_id in starts:
                raise SemanticError("duplicate tool start")
            starts[tool_id] = event
        elif event["kind"] == "tool_terminal":
            tool_id = event["coordinate"][5]
            if tool_id not in starts:
                raise SemanticError("terminal without start")
            if event.get("lifecycle") not in {"succeeded", "failed", "pending", "running", "open"}:
                raise SemanticError("malformed lifecycle")
            terminals.append(event)
    action = min(starts.values(), key=lambda item: tuple(item["coordinate"])) if starts else None
    success_candidates = [event for event in terminals if event.get("lifecycle") == "succeeded"]
    success = (
        min(success_candidates, key=lambda item: tuple(item["coordinate"]))
        if success_candidates
        else None
    )
    mutation_candidates = [event for event in records if event["kind"] == "state_change"]
    mutation = (
        min(mutation_candidates, key=lambda item: tuple(item["coordinate"]))
        if mutation_candidates
        else None
    )
    calls = [event for event in records if event["kind"] == "call"]

    def sum_before(boundary: Mapping[str, Any] | None) -> int | None:
        if boundary is None:
            return None
        prior = [
            event for event in calls if tuple(event["coordinate"]) < tuple(boundary["coordinate"])
        ]
        if not prior:
            return 0
        total = 0
        for event in prior:
            tokens = event.get("tokens")
            if (
                not isinstance(tokens, list)
                or len(tokens) != 4
                or any(item is None for item in tokens)
            ):
                return None
            if any(isinstance(item, bool) or not isinstance(item, int) for item in tokens):
                raise SemanticError("workflow tokens are malformed")
            total += sum(tokens)
        return total

    result = {
        "first_action_tokens": sum_before(action),
        "first_success_tokens": sum_before(success),
        "first_mutation_tokens": sum_before(mutation),
        "mutation_observed": mutation is not None,
    }
    if action is not None and len(starts) > 1:
        action_shape = tuple(action["coordinate"][:5]) + (action["coordinate"][6],)
        if any(
            tuple(item["coordinate"][:5]) + (item["coordinate"][6],) == action_shape
            for item in starts.values()
            if item is not action
        ):
            result["action_boundary_id"] = action["coordinate"][5]
    if success is not None and len(success_candidates) > 1:
        success_shape = tuple(success["coordinate"][:5]) + (success["coordinate"][6],)
        if any(
            tuple(item["coordinate"][:5]) + (item["coordinate"][6],) == success_shape
            for item in success_candidates
            if item is not success
        ):
            result["success_boundary_id"] = success["coordinate"][5]
    if success is not None and any(
        item is not success and tuple(item["coordinate"][:5]) == tuple(success["coordinate"][:5])
        for item in terminals
    ):
        result["success_boundary_id"] = success["coordinate"][5]
    return result


def _verify_independent_closure() -> dict[str, Any]:
    """Recompute the test lane before any answer rows or grades are produced."""

    from .closure import compute_closure, verify_closure

    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    lanes = contract.get("lanes") if isinstance(contract, Mapping) else None
    lane = lanes.get("independent") if isinstance(lanes, Mapping) else None
    if not isinstance(lane, Mapping):
        raise SemanticError("independent closure contract is missing")
    manifest = compute_closure(
        harness=Path(__file__).with_name("closure.py"),
        consumer=Path(__file__),
        root=ROOT,
    )
    return verify_closure(
        manifest,
        root=ROOT,
        forbidden_modules=lane.get("forbidden_module_prefixes", ()),
        forbidden_roles=lane.get("forbidden_overlap_roles", ()),
    )


def _evaluate_case_unchecked(case: Mapping[str, Any]) -> dict[str, Any]:
    _reject_forbidden_data_keys(case)
    request = case.get("request")
    if not isinstance(request, Mapping):
        raise SemanticError("request is required")
    plan = request.get("plan_id")
    dispatch = {
        "current_usage": _current_usage,
        "top_sessions": _top_sessions,
        "period_drivers": _period_drivers,
        "model_effort_mix": _model_effort_mix,
        "project_family_usage": _project_family,
        "top_valued_entities": _top_valued,
        "pricing_coverage": _pricing_coverage,
        "cache_reuse_candidates": _cache_reuse,
        "context_pressure_trajectory": _context_pressure,
        "token_acceleration": _token_acceleration,
        "uncached_input_jumps": _uncached_jumps,
        "cached_replay_small_output": _cached_replay,
        "context_composition": _context_composition,
        "compaction_comparison": _compaction_comparison,
        "growth_without_mutation": _growth,
        "long_vs_split_cohorts": _long_cohorts,
        "turn_completion_efficiency": _turn_completion,
        "first_action_mutation": _first_action,
        "repeated_resource_operations": _repeated_resources,
        "retry_cycles": _retry_cycles,
        "tool_family_behavior": _tool_family,
        "tool_output_adjacency": _tool_output_adjacency,
        "tool_following_activity": _following_tool,
        "resource_hotspots": _resource_hotspots,
        "model_effort_transitions": _profile_transitions,
        "automation_candidates": _automation,
        "tool_duration_gaps": lambda case, request: [],
        "parent_subagent_usage": _parent_subagent,
        "delegation_cohorts": _delegation_cohorts,
        "allowance_movement": _allowance_movement,
        "allowance_interval_events": _allowance_events,
        "allowance_local_efficiency": _allowance_efficiency,
        "allowance_cycle_comparison": _allowance_cycles,
        "latest_publication_delta": _publication_delta,
        "data_health": _data_health,
        "dedup_source_audit": _dedup,
        "evidence_timeline": _evidence_timeline,
        "weekly_review": _weekly_review,
        "investigation_candidates": _investigation,
        "compare_sessions": _compare_sessions,
    }
    if plan not in dispatch:
        raise SemanticError(f"unsupported plan: {plan}")
    rows = [_canonical(row) for row in dispatch[plan](case, request)]
    evidence, provenance = _evidence(case)
    return {
        "oracle_id": str(case.get("oracle_id")),
        "request": _canonical(request),
        "rows": rows,
        "field_grades": _grades(case, rows),
        "total_order": _canonical(_total_order(case)),
        "ordered_evidence": evidence,
        "provenance": provenance,
    }


def evaluate_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Verify the evaluator closure before calculating or grading one case."""

    _verify_independent_closure()
    return _evaluate_case_unchecked(case)


def load_cases(path: Path = SCENARIOS_PATH) -> list[Mapping[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, Mapping)
        or value.get("schema") != "codex-usage-tracker.synthetic-question-scenarios.v1"
    ):
        raise SemanticError("unsupported synthetic scenario fixture")
    cases = value.get("cases")
    if not isinstance(cases, list) or len(cases) != 80:
        raise SemanticError("the synthetic declaration set must contain 80 cases")
    return cases


def evaluate_all(cases: Sequence[Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    values = list(load_cases() if cases is None else cases)
    if len(values) != 80:
        raise SemanticError("exactly 80 variants are required")
    _verify_independent_closure()
    results = [_evaluate_case_unchecked(case) for case in values]
    if len({result["oracle_id"] for result in results}) != 80:
        raise SemanticError("variant identities must be unique")
    return results
