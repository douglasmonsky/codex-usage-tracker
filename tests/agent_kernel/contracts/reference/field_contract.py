from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tests.agent_kernel.contracts.reference.allowance import canonical_decimal
from tests.agent_kernel.contracts.reference.time import ensure_int64

_LOGICAL_ID = re.compile(r"^[a-z][a-z0-9-]*:v1:[a-z2-7]{52}$")
_DIGEST = re.compile(r"^(?:sha256:)?[a-f0-9]{64}$")
_LIFECYCLE_STATES = frozenset(
    {
        "pending",
        "running",
        "succeeded",
        "failed",
        "cancelled",
        "rolled_back",
        "open",
        "unknown",
    }
)


class FieldContractError(ValueError):
    """Raised when one locked entity field lacks executable semantic coverage."""


def _nonnegative_integer(value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FieldContractError("expected a nonnegative integer")


def _utc_microseconds(value: Any) -> None:
    if value is not None:
        ensure_int64(value)


def _logical_id(value: Any) -> None:
    if not isinstance(value, str) or _LOGICAL_ID.fullmatch(value) is None:
        raise FieldContractError("expected an exact v1 logical ID")


def _logical_id_or_null(value: Any) -> None:
    if value is not None:
        _logical_id(value)


def _nonempty_text(value: Any) -> None:
    if not isinstance(value, str) or not value:
        raise FieldContractError("expected nonempty text")


def _boolean(value: Any) -> None:
    if not isinstance(value, bool):
        raise FieldContractError("expected a boolean")


def _mapping(value: Any) -> None:
    if not isinstance(value, dict):
        raise FieldContractError("expected a mapping")


def _sequence(value: Any) -> None:
    if not isinstance(value, list):
        raise FieldContractError("expected a sequence")


def _source_order(value: Any) -> None:
    _sequence(value)
    if not value:
        raise FieldContractError("source order must not be empty")
    if any(isinstance(part, (dict, list)) for part in value):
        raise FieldContractError("source order parts must be scalar")


def _half_open_bounds(value: Any) -> None:
    if isinstance(value, list):
        if len(value) != 2:
            raise FieldContractError("half-open bounds need two members")
        start, end = value
    elif isinstance(value, dict):
        start = value.get("start_us")
        end = value.get("end_us")
        if value.get("semantics", "[start,end)") != "[start,end)":
            raise FieldContractError("bounds must be half-open")
    else:
        raise FieldContractError("half-open bounds need a list or mapping")
    if start is not None:
        ensure_int64(start)
    if end is not None:
        ensure_int64(end)
    if start is not None and end is not None and end < start:
        raise FieldContractError("half-open bounds decrease")


def _source_coordinate(value: Any) -> None:
    _mapping(value)
    required = {
        "source_manifestation_id",
        "source_revision",
        "record_ordinal",
        "adapter_version",
    }
    if not required <= set(value):
        raise FieldContractError("source coordinate is incomplete")
    _logical_id(value["source_manifestation_id"])
    _nonnegative_integer(value["record_ordinal"])


def _source_coordinates(value: Any) -> None:
    _sequence(value)
    for coordinate in value:
        _source_coordinate(coordinate)


def _measurement_mask(value: Any) -> None:
    _nonnegative_integer(value)


def _lifecycle_state(value: Any) -> None:
    if value not in _LIFECYCLE_STATES:
        raise FieldContractError("invalid lifecycle state")


def _decimal_percentage(value: Any) -> None:
    canonical_decimal(value, "percentage", minimum="0", maximum="100")


def _decimal_value(value: Any) -> None:
    canonical_decimal(value, "decimal")


def _decimal_rate_map(value: Any) -> None:
    _mapping(value)
    for field, rate in value.items():
        canonical_decimal(rate, f"{field} rate", minimum="0")


def _digest_text(value: Any) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise FieldContractError("expected a SHA-256 digest")


def _iana_timezone(value: Any) -> None:
    _nonempty_text(value)
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise FieldContractError("expected an IANA timezone") from exc


def _token_count(value: Any) -> None:
    if value is not None:
        _nonnegative_integer(value)


def _status_enum(value: Any) -> None:
    _nonempty_text(value)


def _structural(value: Any) -> None:
    if value is None:
        raise FieldContractError("structural sample must be observed")


_CHECKS: dict[str, Callable[[Any], None]] = {
    "boolean": _boolean,
    "decimal_percentage": _decimal_percentage,
    "decimal_rate_map": _decimal_rate_map,
    "decimal_value": _decimal_value,
    "derived_identity": _logical_id,
    "digest_text": _digest_text,
    "half_open_bounds": _half_open_bounds,
    "identity_input": _structural,
    "iana_timezone": _iana_timezone,
    "lifecycle_state": _lifecycle_state,
    "logical_id": _logical_id,
    "logical_id_or_null": _logical_id_or_null,
    "mapping": _mapping,
    "measurement_mask": _measurement_mask,
    "nonempty_text": _nonempty_text,
    "nonnegative_integer": _nonnegative_integer,
    "sequence": _sequence,
    "source_coordinate": _source_coordinate,
    "source_coordinates": _source_coordinates,
    "source_order": _source_order,
    "status_enum": _status_enum,
    "structural": _structural,
    "token_count": _token_count,
    "utc_microseconds": _utc_microseconds,
}


def missing_probe_for_rule(rule: str) -> str:
    """Classify the exact sentinel required by one missingness rule."""

    if rule.startswith("null_"):
        return "allow_null"
    if rule.startswith("empty_collection") or rule.startswith("empty_rules"):
        return "empty_collection"
    if rule.startswith("empty_mask"):
        return "zero_mask"
    if rule.startswith("zero_"):
        return "zero_observed"
    if rule.startswith("false_"):
        return "false_observed"
    if rule.startswith("open_"):
        return "open_state"
    if rule.startswith("unknown_"):
        return "unknown_state"
    if rule.startswith("explicit_unknown"):
        return "explicit_unknown"
    return "reject_null"


_BOOLEAN_FIELDS = frozenset(
    {"causal_attribution", "ratio_eligible", "reasoning_in_output", "write_intent"}
)
_MAPPING_FIELDS = frozenset(
    {
        "absolute_fields",
        "capability_coverage",
        "coverage",
        "entity_counts",
        "filesystem_identity",
        "first_boundary_coordinates",
        "membership",
        "publication_delta",
        "schema_versions",
        "source_coverage",
        "token_delta",
    }
)
_SEQUENCE_FIELDS = frozenset(
    {
        "cost_rated_token_fields",
        "cost_unpriced_token_fields",
        "credit_rated_token_fields",
        "credit_unpriced_token_fields",
        "label_candidates",
        "missing_token_fields",
        "model_match_rules",
        "parse_diagnostics",
        "resource_links",
        "source_order_range",
    }
)
_SOURCE_COORDINATE_FIELDS = frozenset(
    {
        "last_transition_coordinate",
        "occurrence_coordinate",
        "source_occurrence",
        "start_coordinate",
        "terminal_coordinate",
    }
)
_SOURCE_COORDINATES_FIELDS = frozenset({"evidence_coordinates", "provenance"})
_STATUS_FIELDS = frozenset(
    {
        "completion_status",
        "state",
        "status",
        "validation_status",
    }
)
_LIFECYCLE_FIELDS = frozenset({"lifecycle", "lifecycle_state"})
_DIGEST_FIELDS = frozenset(
    {
        "after_revision",
        "artifact_digest",
        "before_revision",
        "content_revision",
        "digest",
        "rate_card_digest",
        "source_revision",
    }
)
_DECIMAL_FIELDS = frozenset(
    {
        "confidence",
        "configured_cost_usd",
        "cost_coverage",
        "credit_coverage",
        "estimated_credits",
        "percent_delta",
    }
)
_NONNEGATIVE_FIELDS = frozenset(
    {
        "after_context_epoch",
        "before_context_epoch",
        "ordinal",
        "transition_version",
    }
)
_TEXT_FIELDS = frozenset(
    {
        "account_local_identity",
        "activity_kind",
        "adapter_id",
        "adapter_native_call_key",
        "adapter_native_invocation_key",
        "adapter_native_session_key",
        "adapter_native_source_key",
        "adapter_version",
        "basis",
        "capability_basis",
        "category",
        "change_kind",
        "compatibility_basis",
        "completion_basis",
        "cost_grade",
        "cost_unpriced_reason",
        "credit_grade",
        "credit_unpriced_reason",
        "currency",
        "delta_key",
        "display_label",
        "error_category",
        "estimator",
        "event_kind",
        "history_preset",
        "identity_version",
        "inclusion_basis",
        "kind",
        "match_basis",
        "measurement_basis",
        "model",
        "normalization_version",
        "normalized_key",
        "plan_identity",
        "preset",
        "provider",
        "publication_key",
        "reasoning_effort",
        "relationship_basis",
        "reset_basis",
        "reset_identity",
        "selected_history_coverage",
        "semantic_operation",
        "service_tier",
        "source_kind",
        "source_name",
        "source_url",
        "state_basis",
        "technical_path_key",
        "terminal_error_category",
        "token_basis",
        "tool_family",
        "transport_name",
        "window_kind",
        "workspace_key",
    }
)


def semantic_checks_for_field(
    entity: dict[str, Any],
    field: dict[str, Any],
) -> list[str]:
    """Return the maintained semantic assertions for one admitted field."""

    name = field["name"]
    checks: list[str] = []
    if field["identity_participation"] == "included":
        checks.append("identity_input")
    if entity["identity"]["derived_id_field"] == name:
        checks.append("derived_identity")
    if name in _SOURCE_COORDINATE_FIELDS:
        checks.append("source_coordinate")
    elif name in _SOURCE_COORDINATES_FIELDS:
        checks.append("source_coordinates")
    elif name == "source_order":
        checks.append("source_order")
    elif name in {"event_bounds", "record_byte_range"}:
        checks.append("half_open_bounds")
    elif name in _DIGEST_FIELDS:
        checks.append("digest_text")
    elif name == "timezone":
        checks.append("iana_timezone")
    elif name in {"used_percent", "remaining_percent"}:
        checks.append("decimal_percentage")
    elif name in {"four_class_rates", "credit_rates"}:
        checks.append("decimal_rate_map")
    elif name in _DECIMAL_FIELDS:
        checks.append("decimal_value")
    elif name in _BOOLEAN_FIELDS:
        checks.append("boolean")
    elif name in _LIFECYCLE_FIELDS:
        checks.append("lifecycle_state")
    elif name in _STATUS_FIELDS:
        checks.append("status_enum")
    elif name in _MAPPING_FIELDS:
        checks.append("mapping")
    elif name in _SEQUENCE_FIELDS:
        checks.append("sequence")
    elif (
        name.endswith("_id") and name != "adapter_id"
    ) or name in {
        "first_seen_publication",
        "last_seen_publication",
        "logical_id",
    }:
        checks.append("logical_id")
    elif name.endswith("_duration_us") or name in {
        "configured_duration_us",
        "duration_us",
    }:
        checks.append("nonnegative_integer")
    elif name.endswith("_us"):
        checks.append("utc_microseconds")
    elif name.endswith("_tokens"):
        checks.append("token_count")
    elif (
        name.endswith("_count")
        or name.endswith("_bytes")
        or name.endswith("_ordinal")
        or name.endswith("_offset")
        or name.endswith("_depth")
        or name in _NONNEGATIVE_FIELDS
    ):
        checks.append("nonnegative_integer")
    elif name in {"capability_mask", "measurement_mask"}:
        checks.append("measurement_mask")
    elif name in _TEXT_FIELDS:
        checks.append("nonempty_text")
    else:
        raise FieldContractError(
            f"{entity['id']}.{name} lacks a maintained semantic classifier"
        )
    return list(dict.fromkeys(checks))


def _sample_for_checks(
    checks: list[str],
    *,
    logical_id: str,
    coordinate: dict[str, Any],
) -> Any:
    if "derived_identity" in checks or "logical_id" in checks:
        return logical_id
    if "source_coordinate" in checks:
        return coordinate
    if "source_coordinates" in checks:
        return [coordinate]
    if "source_order" in checks:
        return ["fixture", 1]
    if "half_open_bounds" in checks:
        return [0, 1]
    if "digest_text" in checks:
        return "sha256:" + "a" * 64
    if "iana_timezone" in checks:
        return "UTC"
    if "decimal_percentage" in checks:
        return "50"
    if "decimal_rate_map" in checks:
        return {
            "uncached_input_tokens": "1",
            "cached_input_tokens": "0.1",
            "reasoning_tokens": "1",
            "output_tokens": "2",
        }
    if "decimal_value" in checks:
        return "1"
    if "boolean" in checks:
        return True
    if "lifecycle_state" in checks:
        return "succeeded"
    if "status_enum" in checks:
        return "active"
    if "mapping" in checks:
        return {"fixture": "value"}
    if "sequence" in checks:
        return ["fixture"]
    if "utc_microseconds" in checks:
        return 100
    if (
        "nonnegative_integer" in checks
        or "measurement_mask" in checks
        or "token_count" in checks
    ):
        return 1
    if "nonempty_text" in checks:
        return "fixture"
    raise FieldContractError(f"no sample builder for checks {checks}")


def build_field_contract_cases(
    entities: list[dict[str, Any]],
    identity_vectors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build the reviewable table that is checked into the vector bundle."""

    identity_by_entity = {
        vector["entity"]: vector for vector in identity_vectors
    }
    fallback_logical_id = identity_by_entity["session"]["expected_id"]
    manifestation_id = identity_by_entity["source_manifestation"]["expected_id"]
    coordinate = {
        "source_manifestation_id": manifestation_id,
        "source_revision": "sha256:" + "b" * 64,
        "record_ordinal": 1,
        "adapter_version": "codex-jsonl.v1",
    }
    cases: list[dict[str, Any]] = []
    for entity in entities:
        identity_vector = identity_by_entity[entity["id"]]
        identity_values = dict(
            zip(
                identity_vector["identity_input_fields"],
                identity_vector["identity_tuple"],
                strict=True,
            )
        )
        record: dict[str, Any] = {}
        assertions: dict[str, Any] = {}
        for field in entity["fields"]:
            checks = semantic_checks_for_field(entity, field)
            name = field["name"]
            if name in identity_values:
                value = identity_values[name]
            elif entity["identity"]["derived_id_field"] == name:
                value = identity_vector["expected_id"]
            else:
                value = _sample_for_checks(
                    checks,
                    logical_id=fallback_logical_id,
                    coordinate=coordinate,
                )
            record[name] = value
            assertions[name] = {
                "checks": checks,
                "basis": field["basis"],
                "missing_probe": missing_probe_for_rule(field["missing"]),
                "identity_participation": field["identity_participation"],
            }
        cases.append(
            {
                "id": f"field.{entity['id']}",
                "entity": entity["id"],
                "record": record,
                "assertions": assertions,
            }
        )
    return cases


def validate_field_contract_cases(
    entities: list[dict[str, Any]],
    identity_vectors: list[dict[str, Any]],
    cases: list[dict[str, Any]],
) -> int:
    """Execute every declared semantic assertion exactly once per locked field."""

    entity_by_id = {entity["id"]: entity for entity in entities}
    identity_by_entity = {
        vector["entity"]: vector for vector in identity_vectors
    }
    case_by_entity = {case["entity"]: case for case in cases}
    if set(case_by_entity) != set(entity_by_id):
        raise FieldContractError("field cases do not exactly cover logical entities")
    assertion_count = 0
    for entity_id, entity in entity_by_id.items():
        case = case_by_entity[entity_id]
        fields = {field["name"]: field for field in entity["fields"]}
        record = case["record"]
        assertions = case["assertions"]
        if set(record) != set(fields) or set(assertions) != set(fields):
            raise FieldContractError(f"{entity_id} field coverage is not exact")
        identity = entity["identity"]
        identity_vector = identity_by_entity[entity_id]
        extracted_tuple = [
            record[field_name] for field_name in identity["input_fields"]
        ]
        if extracted_tuple != identity_vector["identity_tuple"]:
            raise FieldContractError(f"{entity_id} identity tuple order drifted")
        for field_name, field in fields.items():
            assertion = assertions[field_name]
            if assertion["basis"] != field["basis"]:
                raise FieldContractError(f"{entity_id}.{field_name} basis drifted")
            if assertion["missing_probe"] != missing_probe_for_rule(field["missing"]):
                raise FieldContractError(
                    f"{entity_id}.{field_name} missingness drifted"
                )
            if (
                assertion["identity_participation"]
                != field["identity_participation"]
            ):
                raise FieldContractError(
                    f"{entity_id}.{field_name} identity participation drifted"
                )
            checks = assertion["checks"]
            if not checks:
                raise FieldContractError(
                    f"{entity_id}.{field_name} has no semantic assertion"
                )
            if field["identity_participation"] == "included":
                if "identity_input" not in checks:
                    raise FieldContractError(
                        f"{entity_id}.{field_name} identity input is not consumed"
                    )
            elif "identity_input" in checks:
                raise FieldContractError(
                    f"{entity_id}.{field_name} invents identity participation"
                )
            if (
                identity["derived_id_field"] == field_name
                and "derived_identity" not in checks
            ):
                raise FieldContractError(
                    f"{entity_id}.{field_name} derived identity is not asserted"
                )
            for check in checks:
                validator = _CHECKS.get(check)
                if validator is None:
                    raise FieldContractError(
                        f"{entity_id}.{field_name} has unknown check {check}"
                    )
                validator(record[field_name])
            assertion_count += 1
    return assertion_count
