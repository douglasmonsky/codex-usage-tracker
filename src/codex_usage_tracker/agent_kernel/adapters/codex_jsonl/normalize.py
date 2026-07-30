"""Normalize structural Codex JSONL records into adapter observations."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from typing import Any

from ...domain.identity import semantic_id
from ...domain.time import validate_utc_microseconds
from ..contracts import (
    AdapterObservation,
    Capability,
    SourceRange,
)

EVENT_KIND_ORDER = {
    "session_start": 10,
    "late_parent": 15,
    "turn_start": 20,
    "model_call": 30,
    "compaction_boundary": 35,
    "tool_start": 40,
    "tool_terminal": 50,
    "activity": 55,
    "state_change": 60,
    "allowance_observation": 70,
    "session_terminal": 80,
    "oracle_case": 90,
}

CONTROL_RECORD_TYPES = frozenset(
    {
        "allowance_compatibility",
        "oracle_case",
        "selector_anchor",
        "slice_control",
        "source_phase_occurrence",
        "source_revision",
    }
)

_BODY_KEYS = frozenset(
    {
        "body",
        "command",
        "content",
        "diff",
        "patch",
        "prompt",
        "reasoning",
        "response",
        "stderr",
        "stdout",
        "tool_output",
    }
)
_OPERATIONS = frozenset(
    {"read", "search", "list", "execute", "write", "patch", "test", "navigate", "delegate", "wait", "unknown"}
)
_TRANSPORT_OPERATION_HINTS = {
    "read": "read",
    "search": "search",
    "list": "list",
    "exec": "execute",
    "command": "execute",
    "write": "write",
    "patch": "patch",
    "test": "test",
    "navigate": "navigate",
    "delegate": "delegate",
    "wait": "wait",
}
_MEASUREMENT_BITS = {
    "uncached_input_tokens": 1 << 0,
    "cached_input_tokens": 1 << 1,
    "reasoning_tokens": 1 << 2,
    "output_tokens": 1 << 3,
    "context_window_tokens": 1 << 4,
    "event_at_us": 1 << 5,
    "duration_us": 1 << 6,
    "output_bytes": 1 << 7,
}

_NORMALIZED_RECORD_TYPES = frozenset(
    {
        "activity",
        "allowance_observation",
        "compaction_boundary",
        "late_parent",
        "model_call",
        "session_start",
        "session_terminal",
        "state_change",
        "tool_start",
        "tool_terminal",
        "turn_start",
        *CONTROL_RECORD_TYPES,
    }
)
_ENVELOPE_TYPES = {
    "session_meta": "session_start",
    "session.started": "session_start",
    "turn_context": "turn_start",
    "turn.started": "turn_start",
    "model.completed": "model_call",
    "response.completed": "model_call",
    "codex.model_call": "model_call",
    "tool.started": "tool_start",
    "tool.start": "tool_start",
    "tool.completed": "tool_terminal",
    "tool.finished": "tool_terminal",
    "tool.terminal": "tool_terminal",
    "tool.ended": "tool_terminal",
    "codex.tool_start": "tool_start",
    "codex.tool_terminal": "tool_terminal",
}


class NormalizationError(ValueError):
    """A source record cannot be represented by the adapter contract."""


def _reject_body_key(key: str) -> None:
    lowered = key.lower()
    if lowered in _BODY_KEYS or lowered.endswith("_body") or lowered.startswith("raw_"):
        raise NormalizationError(f"raw body field is not admissible: {key}")


def _string(value: object, field: str, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not value:
        raise NormalizationError(f"{field} must be a nonempty string")
    _reject_body_key(field)
    return value


def _integer(value: object, field: str, *, allow_none: bool = True, nonnegative: bool = False) -> int | None:
    if value is None and allow_none:
        return None
    if type(value) is not int:
        raise NormalizationError(f"{field} must be an integer")
    if nonnegative and value < 0:
        raise NormalizationError(f"{field} must be nonnegative")
    return value


def normalize_timestamp(value: object) -> tuple[int | None, str]:
    """Normalize exact integer microseconds or timezone-aware ISO timestamps."""

    if value is None:
        return None, "unavailable"
    if type(value) is int:
        validate_utc_microseconds(value, allow_none=False)
        return value, "upstream_utc_microseconds"
    if not isinstance(value, str):
        raise NormalizationError("timestamp must be integer microseconds or ISO-8601 text")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if "." in text:
        fraction = text.split(".", 1)[1].split("+", 1)[0].split("-", 1)[0]
        if len(fraction) > 6:
            raise NormalizationError("timestamp precision would be lossy")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise NormalizationError("invalid ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise NormalizationError("timestamp must include a timezone offset")
    utc = parsed.astimezone(timezone.utc)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = utc - epoch
    micros = (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
    validate_utc_microseconds(micros, allow_none=False)
    return micros, "upstream_iso8601"


def _canonical_decimal(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise NormalizationError(f"{field} must be canonical decimal text")
    try:
        decimal = Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise NormalizationError(f"{field} must be finite decimal text") from error
    if not decimal.is_finite():
        raise NormalizationError(f"{field} must be finite decimal text")
    normalized = format(decimal.normalize(), "f")
    if normalized == "-0":
        normalized = "0"
    if normalized != value:
        raise NormalizationError(f"{field} is not canonical decimal text")
    return value


def _session_id(native_key: str) -> str:
    return semantic_id("session", [native_key, "identity-v1"])


def _turn_ordinal(payload: Mapping[str, Any], source_order: int) -> int:
    explicit = payload.get("turn_ordinal", payload.get("ordinal"))
    if type(explicit) is int and explicit >= 0:
        return explicit
    # The synthetic Codex source records use ten source-order units per model
    # call and two calls per turn.  This is also a deterministic fallback for
    # envelopes that expose source order but omit a separate turn ordinal.
    return source_order // 20


def _turn_id(session_id: str, payload: Mapping[str, Any], source_order: int) -> str:
    return semantic_id("turn", [session_id, _turn_ordinal(payload, source_order)])


def _logical_id(kind: str, value: object, identity_tuple: tuple[Any, ...]) -> str:
    """Derive CK-02 IDs locally; upstream IDs are native keys only."""

    return semantic_id(kind, identity_tuple)


def _envelope(record: Mapping[str, Any]) -> dict[str, Any]:
    """Translate documented Codex event envelopes to adapter-native records.

    Synthetic tests use both the normalized adapter-native shape and the
    envelope shape.  The adapter never copies unbounded envelope fields into
    the normalized payload; only structural keys needed by the contract cross
    this boundary.
    """

    record_type = record.get("type")
    if not isinstance(record_type, str):
        return dict(record)
    normalized_type = _ENVELOPE_TYPES.get(record_type)
    if normalized_type is None or record_type in _NORMALIZED_RECORD_TYPES:
        return dict(record)
    raw_payload = record.get("payload")
    payload = dict(raw_payload) if isinstance(raw_payload, dict) else {}
    structural_keys = (
        "session_id", "turn_id", "turn_ordinal", "call_id", "tool_id",
        "tool_call_id", "model", "reasoning_effort", "service_tier",
        "transport_name", "tool_name", "name", "state", "project_id",
        "duration_us", "output_bytes", "tokens", "usage", "resource_id",
        "path", "resource_kind", "semantic_operation", "write_intent",
    )
    for key in structural_keys:
        if key not in payload and key in record:
            payload[key] = record[key]
    if normalized_type == "model_call":
        payload.setdefault("call_id", record.get("id", record.get("event_id")))
        payload.setdefault("session_id", record.get("session_id"))
        payload.setdefault("turn_id", record.get("turn_id"))
        payload.setdefault("model", record.get("model"))
    elif normalized_type in {"tool_start", "tool_terminal"}:
        payload.setdefault("tool_id", record.get("tool_call_id", record.get("id", record.get("event_id"))))
        payload.setdefault("session_id", record.get("session_id"))
        payload.setdefault("turn_id", record.get("turn_id"))
        payload.setdefault("transport_name", record.get("tool_name", record.get("name")))
    elif normalized_type == "session_start":
        payload.setdefault("session_id", record.get("session_id", record.get("id")))
    elif normalized_type == "turn_start":
        payload.setdefault("session_id", record.get("session_id"))
        payload.setdefault("turn_id", record.get("turn_id", record.get("id")))
    return {
        "type": normalized_type,
        "payload": payload,
        "event_at_us": record.get("event_at_us", record.get("timestamp")),
        "source_order": record.get("source_order"),
        "event_kind_order": record.get("event_kind_order"),
    }


def _payload(record: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = record.get("payload")
    if not isinstance(raw, dict):
        raise NormalizationError("payload must be an object")
    return raw


def _tokens(payload: Mapping[str, Any]) -> tuple[dict[str, int | None], int, str]:
    raw = payload.get("tokens", payload.get("usage", {}))
    if not isinstance(raw, dict):
        raise NormalizationError("tokens must be an object")
    result: dict[str, int | None] = {}
    basis = "upstream_separate_classes"
    for field in ("uncached_input_tokens", "cached_input_tokens", "reasoning_tokens", "output_tokens"):
        result[field] = _integer(raw.get(field), field, nonnegative=True)
    if result["uncached_input_tokens"] is None and raw.get("input_tokens") is not None:
        total = _integer(raw.get("input_tokens"), "input_tokens", nonnegative=True)
        cached = result["cached_input_tokens"]
        if total is not None and cached is not None and cached <= total:
            result["uncached_input_tokens"] = total - cached
            basis = "derived_from_input_minus_cached"
    measurement_mask = sum(
        bit for field, bit in _MEASUREMENT_BITS.items() if field in result and result[field] is not None
    )
    return result, measurement_mask, basis


def _operation(payload: Mapping[str, Any]) -> str:
    explicit = payload.get("semantic_operation")
    if isinstance(explicit, str) and explicit in _OPERATIONS:
        return explicit
    transport = str(payload.get("transport_name", "unknown")).lower()
    for marker, operation in _TRANSPORT_OPERATION_HINTS.items():
        if marker in transport:
            return operation
    return "unknown"


def _resource(payload: Mapping[str, Any]) -> tuple[str | None, dict[str, Any]]:
    resource_id = payload.get("resource_id")
    path = payload.get("path")
    if isinstance(path, str) and path:
        normalized = PurePosixPath(path).as_posix()
    elif isinstance(resource_id, str) and resource_id:
        # A native resource key is structural evidence, not a canonical ID.
        normalized = resource_id
    else:
        return None, {}
    if normalized.startswith("/") or ".." in normalized.split("/"):
        raise NormalizationError("resource path is ambiguous")
    project_id = str(payload.get("project_id", "unknown-project"))
    resource_kind = str(payload.get("resource_kind", "file"))
    return semantic_id("resource", [project_id, resource_kind, normalized, "resource-normalization-v1"]), {
        "normalized_resource_key": normalized,
        "resource_kind": resource_kind,
        "resource_project_id": project_id,
    }


def _base(record: Mapping[str, Any], source_range: SourceRange) -> tuple[str, Mapping[str, Any], int | None, str, int, int]:
    record = _envelope(record)
    record_type = _string(record.get("type"), "type")
    assert record_type is not None
    payload = _payload(record)
    event_at_us, time_basis = normalize_timestamp(record.get("event_at_us", record.get("timestamp")))
    source_order = _integer(
        record.get("source_order") if record.get("source_order") is not None else source_range.record_ordinal,
        "source_order",
        allow_none=False,
        nonnegative=True,
    )
    event_kind_order = _integer(
        record.get("event_kind_order")
        if record.get("event_kind_order") is not None
        else EVENT_KIND_ORDER.get(record_type),
        "event_kind_order",
        allow_none=False,
        nonnegative=True,
    )
    assert source_order is not None and event_kind_order is not None
    return record_type, payload, event_at_us, time_basis, source_order, event_kind_order


def normalize_record(record: Mapping[str, Any], source_range: SourceRange, *, source_rank: int = 0, late_cutoff_us: int | None = None) -> AdapterObservation:
    """Normalize one complete record and discard all unapproved fields."""

    record = _envelope(record)
    record_type, payload, event_at_us, time_basis, source_order, event_kind_order = _base(record, source_range)
    if record_type in CONTROL_RECORD_TYPES:
        coordinate = source_range.coordinate_tuple
        control_id = semantic_id("diagnostic", [record_type, coordinate])
        return AdapterObservation(
            observation_type="AdapterDiagnosticObserved",
            logical_id=control_id,
            identity_tuple=(record_type, coordinate),
            source_range=source_range,
            source_rank=source_rank,
            event_at_us=event_at_us,
            source_order=source_order,
            event_kind_order=event_kind_order,
            payload={"diagnostic_code": "control_record_ignored", "record_type": record_type},
            capability_mask=0,
            measurement_mask=_MEASUREMENT_BITS["event_at_us"] if event_at_us is not None else 0,
            basis=time_basis,
        )
    if record_type not in {
        "activity",
        "allowance_observation",
        "compaction_boundary",
        "late_parent",
        "model_call",
        "session_start",
        "session_terminal",
        "state_change",
        "tool_start",
        "tool_terminal",
        "turn_start",
    }:
        raise NormalizationError(f"unknown record kind: {record_type}")

    values: dict[str, Any] = {}
    capability = 0
    measurement_mask = _MEASUREMENT_BITS["event_at_us"] if event_at_us is not None else 0
    entity_kind = "observation"
    identity: tuple[Any, ...]
    logical_value: object = None
    observation_type: str
    if record_type in {"session_start", "session_terminal"}:
        session = _string(payload.get("session_id"), "session_id")
        assert session is not None
        entity_kind, logical_value = "session", session
        identity = (session, "identity-v1")
        values = {
            "session_id": semantic_id("session", identity),
            "state": _string(payload.get("state"), "state"),
            "project_id": payload.get("project_id"),
            "parent_session_id": payload.get("parent_session_id"),
            "completion_basis": payload.get("completion_basis"),
        }
        observation_type = "SessionObserved"
        capability = int(Capability.SESSION_HIERARCHY)
    elif record_type == "late_parent":
        child = _string(payload.get("session_id", payload.get("child_session_id")), "session_id")
        parent = _string(payload.get("parent_session_id"), "parent_session_id")
        assert child is not None and parent is not None
        identity = (child, parent, payload.get("relationship_basis", "late_discovery"))
        entity_kind, logical_value = "session-relationship", None
        values = {"session_id": _session_id(child), "parent_session_id": _session_id(parent), "relationship_basis": payload.get("relationship_basis", "late_discovery")}
        observation_type = "SessionRelationshipObserved"
        capability = int(Capability.SESSION_HIERARCHY)
    elif record_type == "turn_start":
        turn = _string(payload.get("turn_id"), "turn_id")
        session = _string(payload.get("session_id"), "session_id")
        assert turn is not None and session is not None
        canonical_session = _session_id(session)
        identity = (canonical_session, _turn_ordinal(payload, source_order))
        entity_kind, logical_value = "turn", turn
        values = {"turn_id": semantic_id("turn", identity), "session_id": canonical_session, "state": payload.get("state", "open")}
        observation_type = "TurnBoundaryObserved"
        capability = int(Capability.SESSION_HIERARCHY)
    elif record_type == "model_call":
        call = _string(payload.get("call_id"), "call_id")
        session = _string(payload.get("session_id"), "session_id")
        turn = _string(payload.get("turn_id"), "turn_id")
        model = _string(payload.get("model"), "model")
        assert call is not None and session is not None and turn is not None and model is not None
        token_values, token_mask, token_basis = _tokens(payload)
        canonical_session = _session_id(session)
        canonical_turn = _turn_id(canonical_session, payload, source_order)
        profile_identity = (model, payload.get("reasoning_effort"), payload.get("service_tier"))
        identity = (call, canonical_session, canonical_turn)
        entity_kind, logical_value = "call", call
        values = {
            "call_id": semantic_id("call", identity),
            "session_id": canonical_session,
            "turn_id": canonical_turn,
            "model_profile_id": semantic_id("model-profile", profile_identity),
            "model": model,
            "reasoning_effort": payload.get("reasoning_effort"),
            "service_tier": payload.get("service_tier"),
            "context_window_tokens": _integer(payload.get("context_window_tokens"), "context_window_tokens", nonnegative=True),
            **token_values,
            "token_basis": token_basis,
        }
        observation_type = "ModelCallObserved"
        capability = int(Capability.MODEL_CALL_USAGE | Capability.VALUATION)
        measurement_mask |= token_mask
        if values["context_window_tokens"] is not None:
            measurement_mask |= _MEASUREMENT_BITS["context_window_tokens"]
    elif record_type in {"tool_start", "tool_terminal"}:
        tool = _string(payload.get("tool_id"), "tool_id")
        session = _string(payload.get("session_id"), "session_id")
        turn = _string(payload.get("turn_id"), "turn_id")
        transport = _string(payload.get("transport_name"), "transport_name")
        assert tool is not None and session is not None and turn is not None and transport is not None
        resource_id, resource_values = _resource(payload)
        canonical_session = _session_id(session)
        canonical_turn = _turn_id(canonical_session, payload, source_order)
        identity = (tool, canonical_session, canonical_turn)
        entity_kind, logical_value = "tool", tool
        values = {
            "tool_id": semantic_id("tool", identity),
            "session_id": canonical_session,
            "turn_id": canonical_turn,
            "transport_name": transport,
            "semantic_operation": _operation(payload),
            "resource_id": resource_id,
            **resource_values,
            "state": _string(payload.get("state"), "state"),
            "write_intent": 1 if payload.get("write_intent", False) else 0,
            "duration_us": _integer(payload.get("duration_us"), "duration_us", nonnegative=True),
            "output_bytes": _integer(payload.get("output_bytes"), "output_bytes", nonnegative=True),
        }
        observation_type = "ToolLifecycleObserved"
        capability = int(Capability.TOOL_LIFECYCLE)
        if values["duration_us"] is not None:
            measurement_mask |= _MEASUREMENT_BITS["duration_us"]
        if values["output_bytes"] is not None:
            measurement_mask |= _MEASUREMENT_BITS["output_bytes"]
    elif record_type == "activity":
        activity = _string(payload.get("activity_id"), "activity_id")
        session = _string(payload.get("session_id"), "session_id")
        assert activity is not None and session is not None
        canonical_session = _session_id(session)
        canonical_turn = _turn_id(canonical_session, payload, source_order)
        activity_kind = _string(payload.get("activity_kind"), "activity_kind")
        assert activity_kind is not None
        identity = (canonical_session, canonical_turn, activity_kind)
        entity_kind, logical_value = "activity", activity
        values = {"activity_id": semantic_id("activity", identity), "session_id": canonical_session, "turn_id": canonical_turn, "activity_kind": activity_kind, "state": payload.get("state", "unknown")}
        observation_type = "ActivityLifecycleObserved"
        capability = int(Capability.TOOL_LIFECYCLE)
    elif record_type == "compaction_boundary":
        compaction = _string(payload.get("compaction_id"), "compaction_id")
        session = _string(payload.get("session_id"), "session_id")
        before = _string(payload.get("before_context_epoch"), "before_context_epoch")
        after = _string(payload.get("after_context_epoch"), "after_context_epoch")
        assert compaction is not None and session is not None and before is not None and after is not None
        if before == after:
            raise NormalizationError("compaction boundary must change context epoch")
        canonical_session = _session_id(session)
        identity = (canonical_session, source_order)
        entity_kind, logical_value = "compaction", compaction
        values = {"compaction_id": semantic_id("compaction", identity), "session_id": canonical_session, "before_context_epoch": before, "after_context_epoch": after}
        observation_type = "CompactionObserved"
        capability = int(Capability.MODEL_CALL_USAGE)
    elif record_type == "state_change":
        change = _string(payload.get("change_id"), "change_id")
        session = _string(payload.get("session_id"), "session_id")
        resource_id, resource_values = _resource(payload)
        if change is None or session is None or resource_id is None:
            raise NormalizationError("state change requires change, session, and resource identities")
        canonical_session = _session_id(session)
        canonical_turn = _turn_id(canonical_session, payload, source_order)
        change_kind = _string(payload.get("change_kind"), "change_kind")
        assert change_kind is not None
        identity = (change_kind, resource_id, event_at_us, canonical_session, canonical_turn)
        entity_kind, logical_value = "state-change", change
        values = {"change_id": semantic_id("state-change", identity), "session_id": canonical_session, "turn_id": canonical_turn, "resource_id": resource_id, **resource_values, "change_kind": change_kind, "preceding_activity_count": _integer(payload.get("preceding_activity_count"), "preceding_activity_count", nonnegative=True), "causal_attribution": 0}
        observation_type = "StateChangeObserved"
        capability = int(Capability.STATE_CHANGE_OBSERVATION)
    else:
        limit = _string(payload.get("limit_id"), "limit_id")
        cycle = _string(payload.get("cycle_id"), "cycle_id")
        plan = _string(payload.get("plan_identity"), "plan_identity")
        window = _string(payload.get("window_kind"), "window_kind")
        reset = _string(payload.get("reset_identity"), "reset_identity")
        provider = _string(payload.get("provider"), "provider")
        assert limit is not None and cycle is not None and plan is not None and window is not None and reset is not None and provider is not None
        entity_kind, logical_value = "allowance-observation", None
        upstream_observation_ordinal = _integer(
            payload.get("observation_ordinal"),
            "observation_ordinal",
            allow_none=False,
            nonnegative=True,
        )
        assert upstream_observation_ordinal is not None
        observation_ordinal = upstream_observation_ordinal + 1
        account = _string(payload.get("account_local_identity", "unknown-account"), "account_local_identity")
        assert account is not None
        limit_identity = (provider, account, plan, window)
        canonical_limit = semantic_id("allowance-limit", limit_identity)
        cycle_start = _integer(payload.get("cycle_start_us"), "cycle_start_us")
        cycle_end = _integer(payload.get("cycle_end_us"), "cycle_end_us")
        cycle_identity = (canonical_limit, reset, cycle_start, cycle_end)
        canonical_cycle = semantic_id("allowance-cycle", cycle_identity)
        observed_at_us = payload.get("observed_at_us", event_at_us)
        validate_utc_microseconds(observed_at_us)
        source_occurrence = {
            "source_manifestation_id": source_range.manifestation_id,
            "source_revision": source_range.source_revision,
            "record_ordinal": source_range.record_ordinal,
            "adapter_version": source_range.adapter_version,
        }
        identity = (canonical_limit, canonical_cycle, observed_at_us, source_occurrence)
        values = {"limit_id": canonical_limit, "cycle_id": canonical_cycle, "provider": provider, "account_local_identity": account, "plan_identity": plan, "window_kind": window, "reset_identity": reset, "observation_ordinal": observation_ordinal, "observation_ordinal_basis": "upstream_zero_based_plus_one", "used_percent": _canonical_decimal(payload.get("used_percent"), "used_percent"), "remaining_percent": _canonical_decimal(payload.get("remaining_percent"), "remaining_percent"), "reset_time_us": normalize_timestamp(payload.get("reset_time_us"))[0] if payload.get("reset_time_us") is not None else None}
        observation_type = "AllowanceObservationObserved"
        capability = int(Capability.ALLOWANCE_OBSERVATION)
        for field in ("used_percent", "remaining_percent", "reset_time_us"):
            if values[field] is not None:
                measurement_mask |= _MEASUREMENT_BITS["event_at_us"]

    logical_id = _logical_id(entity_kind, logical_value, identity) if logical_value is not None else semantic_id(entity_kind, identity)
    if late_cutoff_us is not None and event_at_us is not None and event_at_us < late_cutoff_us:
        values["cursor_outcome"] = "late_event"
    return AdapterObservation(
        observation_type=observation_type,
        logical_id=logical_id,
        identity_tuple=identity,
        source_range=source_range,
        source_rank=source_rank,
        event_at_us=event_at_us,
        source_order=source_order,
        event_kind_order=event_kind_order,
        payload=values,
        capability_mask=capability,
        measurement_mask=measurement_mask,
        basis=time_basis,
        confidence="exact",
    )


def assert_body_free(observation: AdapterObservation) -> None:
    """Fail closed if a proposed observation accidentally carries a body."""

    def walk(value: object, key: str = "") -> None:
        _reject_body_key(key)
        if isinstance(value, Mapping):
            for child_key, child_value in value.items():
                if not isinstance(child_key, str):
                    raise NormalizationError("observation payload keys must be strings")
                walk(child_value, child_key)
        elif isinstance(value, (bytes, bytearray)):
            raise NormalizationError("observation payload cannot contain bytes")

    walk(observation.payload)


def related_observations(observation: AdapterObservation) -> tuple[AdapterObservation, ...]:
    """Emit bounded typed relations implied by one structural observation."""

    related: list[AdapterObservation] = []
    payload = observation.payload
    if observation.observation_type == "SessionObserved" and isinstance(payload.get("project_id"), str):
        project_id = str(payload["project_id"])
        related.append(
            AdapterObservation(
                observation_type="ProjectObserved",
                logical_id=semantic_id("project", [project_id]),
                identity_tuple=(project_id,),
                source_range=observation.source_range,
                source_rank=observation.source_rank,
                event_at_us=observation.event_at_us,
                source_order=observation.source_order,
                event_kind_order=observation.event_kind_order,
                payload={"project_id": project_id},
                capability_mask=observation.capability_mask,
                measurement_mask=observation.measurement_mask,
                basis=observation.basis,
                confidence=observation.confidence,
                transition_rank=observation.transition_rank + 1,
            )
        )
    if observation.observation_type == "ToolLifecycleObserved":
        resource_id = payload.get("resource_id")
        tool_id = payload.get("tool_id")
        if isinstance(resource_id, str) and isinstance(tool_id, str):
            related.append(
                AdapterObservation(
                    observation_type="ResourceObserved",
                    logical_id=resource_id,
                    identity_tuple=(
                        payload.get("resource_project_id", "unknown-project"),
                        payload.get("resource_kind", "file"),
                        payload.get("normalized_resource_key", resource_id),
                        "resource-normalization-v1",
                    ),
                    source_range=observation.source_range,
                    source_rank=observation.source_rank,
                    event_at_us=observation.event_at_us,
                    source_order=observation.source_order,
                    event_kind_order=observation.event_kind_order,
                    payload={
                        key: payload[key]
                        for key in ("resource_id", "normalized_resource_key", "resource_kind")
                        if key in payload
                    },
                    capability_mask=observation.capability_mask,
                    measurement_mask=observation.measurement_mask,
                    basis=observation.basis,
                    confidence=observation.confidence,
                    transition_rank=observation.transition_rank + 1,
                )
            )
            related.append(
                AdapterObservation(
                    observation_type="ToolResourceLinkObserved",
                    logical_id=semantic_id("tool-resource-link", [tool_id, resource_id]),
                    identity_tuple=(tool_id, resource_id),
                    source_range=observation.source_range,
                    source_rank=observation.source_rank,
                    event_at_us=observation.event_at_us,
                    source_order=observation.source_order,
                    event_kind_order=observation.event_kind_order,
                    payload={"tool_id": tool_id, "resource_id": resource_id},
                    capability_mask=observation.capability_mask,
                    measurement_mask=observation.measurement_mask,
                    basis=observation.basis,
                    confidence=observation.confidence,
                    transition_rank=observation.transition_rank + 2,
                )
            )
    if observation.observation_type == "AllowanceObservationObserved":
        limit_id = payload.get("limit_id")
        cycle_id = payload.get("cycle_id")
        if isinstance(limit_id, str) and isinstance(cycle_id, str):
            identity = (
                payload.get("provider"),
                payload.get("account_local_identity", "unknown-account"),
                payload.get("plan_identity"),
                payload.get("window_kind"),
            )
            related.append(
                AdapterObservation(
                    observation_type="AllowanceLimitObserved",
                    logical_id=semantic_id("allowance-limit", identity),
                    identity_tuple=identity,
                    source_range=observation.source_range,
                    source_rank=observation.source_rank,
                    event_at_us=observation.event_at_us,
                    source_order=observation.source_order,
                    event_kind_order=observation.event_kind_order,
                    payload={key: payload[key] for key in ("limit_id", "cycle_id", "provider", "account_local_identity", "plan_identity", "window_kind", "reset_identity") if key in payload},
                    capability_mask=observation.capability_mask,
                    measurement_mask=observation.measurement_mask,
                    basis=observation.basis,
                    confidence=observation.confidence,
                    transition_rank=observation.transition_rank + 1,
                )
            )
    return tuple(related)
