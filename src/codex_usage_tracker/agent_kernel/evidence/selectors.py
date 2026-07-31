"""Owner-dispatched, typed evidence selector resolution."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from codex_usage_tracker.agent_kernel.domain.identity import semantic_id
from codex_usage_tracker.agent_kernel.domain.valuation import validate_rate_card_frontier
from codex_usage_tracker.agent_kernel.query.compiler import request_digest
from codex_usage_tracker.agent_kernel.storage.rate_cards import (
    RateCardFrontierError,
    load_publication_rate_card_frontier,
)


class EvidenceSelectorError(ValueError):
    """A selector or its owner-provided provenance is not admissible."""


SelectorResolutionError = EvidenceSelectorError

_SELECTOR_KIND_ORDER = (
    "allowance_interval",
    "allowance_observation",
    "call",
    "model_profile",
    "project",
    "publication",
    "rate_card",
    "resource",
    "session",
    "source_manifestation",
    "state_change",
    "tool",
    "turn",
    "window",
)
_PROVENANCE_KIND_ORDER = (
    "configured_artifact",
    "derived_boundary_pair",
    "publication_commit",
    "request_derivation",
    "source_inventory",
    "source_occurrence",
)
SELECTOR_KINDS = frozenset(_SELECTOR_KIND_ORDER)
PROVENANCE_KINDS = frozenset(_PROVENANCE_KIND_ORDER)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """One exact ordered selector and the provenance supplied by its owner."""

    role: str
    selector_kind: str
    selector: str
    logical_id: str
    provenance_kind: str
    provenance: Mapping[str, Any]

    def __post_init__(self) -> None:
        for label, value in (
            ("role", self.role),
            ("selector_kind", self.selector_kind),
            ("selector", self.selector),
            ("logical_id", self.logical_id),
            ("provenance_kind", self.provenance_kind),
        ):
            if not isinstance(value, str) or not value:
                raise EvidenceSelectorError(f"evidence {label} is missing")
        if not isinstance(self.provenance, Mapping):
            raise EvidenceSelectorError("evidence provenance must be a mapping")
        object.__setattr__(self, "provenance", _freeze(dict(self.provenance)))


EvidenceReferenceV1 = EvidenceReference


@dataclass(frozen=True, slots=True)
class EvidenceSelection:
    """A normalized ordered selector request."""

    references: tuple[EvidenceReference, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.references, tuple) or not self.references:
            raise EvidenceSelectorError("evidence selection must not be empty")

    @property
    def evidence_references(self) -> tuple[EvidenceReference, ...]:
        return self.references


_STATEMENTS: Mapping[str, str] = MappingProxyType(
    {
        "head": """
            SELECT p.publication_id, p.rate_card_digest, p.status,
                   p.committed_at_us
              FROM publication_head AS h
              JOIN publications AS p ON p.publication_id = h.publication_id
             WHERE h.singleton = 1
        """,
        "alias": """
            SELECT canonical_selector, logical_id, reason
              FROM selector_aliases
             WHERE alias_selector = ?
        """,
        "allowance_interval": """
            SELECT interval_id, start_observation_id, end_observation_id,
                   compatibility_basis
              FROM allowance_intervals
             WHERE interval_id = ?
        """,
        "rate_card": """
            SELECT digest, source_name, fetched_at_us, validation_status,
                   rate_card_id
              FROM rate_card_revisions
             WHERE digest = ? OR rate_card_id = ?
             ORDER BY digest
        """,
        "active_rate_card": """
            SELECT a.publication_id, a.rate_card_id, r.digest,
                   r.validation_status
              FROM active_rate_card AS a
              JOIN rate_card_revisions AS r ON r.rate_card_id = a.rate_card_id
             WHERE a.singleton = 1
        """,
        "publication": """
            SELECT operation_id, artifact_manifest_sha256, committed_at_us,
                   status
              FROM publications
             WHERE publication_id = ?
        """,
        "source_manifestation": """
            SELECT sm.source_id, sm.content_revision, sm.state,
                   sm.selected, sm.first_seen_publication_id,
                   sm.last_seen_publication_id
              FROM source_manifestations AS sm
             WHERE sm.manifestation_id = ?
        """,
        "occurrences": """
            SELECT o.occurrence_id, o.semantic_logical_id,
                   sm.manifestation_id, o.source_revision,
                   o.record_ordinal, o.byte_start, o.byte_end,
                   o.adapter_version
              FROM source_occurrences AS o
              JOIN source_manifestations AS sm
                ON sm.manifestation_key = o.manifestation_key
             WHERE o.semantic_logical_id = ?
             ORDER BY o.record_ordinal, o.byte_start, o.byte_end, o.occurrence_id
        """,
        "profile": """
            SELECT model, reasoning_effort, service_tier
              FROM model_profiles
             WHERE model_profile_id = ?
        """,
        "profile_calls": """
            SELECT call_id
              FROM model_calls_visible
             WHERE model_profile_id = ?
             ORDER BY call_id
        """,
        "allowance_observation": """
            SELECT 1
              FROM allowance_observations
             WHERE observation_id = ?
             LIMIT 1
        """,
        "call": """
            SELECT 1
              FROM model_calls_visible
             WHERE call_id = ?
             LIMIT 1
        """,
        "project": """
            SELECT 1 FROM projects WHERE project_id = ? LIMIT 1
        """,
        "resource": """
            SELECT 1 FROM resources WHERE resource_id = ? LIMIT 1
        """,
        "session": """
            SELECT 1 FROM sessions WHERE session_id = ? LIMIT 1
        """,
        "state_change": """
            SELECT 1 FROM state_changes WHERE change_id = ? LIMIT 1
        """,
        "tool": """
            SELECT 1 FROM tool_invocations WHERE tool_id = ? LIMIT 1
        """,
        "turn": """
            SELECT 1 FROM turns WHERE turn_id = ? LIMIT 1
        """,
    }
)

SELECTOR_STATEMENTS = _STATEMENTS

_PREFIXES = MappingProxyType({kind: kind.replace("_", "-") for kind in SELECTOR_KINDS})
_SOURCE_OWNER_KINDS = frozenset(
    {
        "allowance_observation",
        "call",
        "project",
        "resource",
        "session",
        "state_change",
        "tool",
        "turn",
        "model_profile",
    }
)


def _row_dict(row: Any, description: Sequence[Any] | None = None) -> dict[str, Any]:
    if isinstance(row, sqlite3.Row):
        return {key: row[key] for key in row.keys()}  # noqa: SIM118
    if isinstance(row, Mapping):
        return dict(row)
    if description is None:
        raise EvidenceSelectorError("owner query returned no description")
    return {column[0]: value for column, value in zip(description, row, strict=True)}


def _execute(connection: sqlite3.Connection, statement_id: str, parameters: Sequence[Any] = ()) -> Any:
    sql = _STATEMENTS.get(statement_id)
    if sql is None:
        raise EvidenceSelectorError(f"unknown owner statement: {statement_id}")
    return connection.execute(sql, tuple(parameters))


def _placeholder(value: str) -> bool:
    return value.strip().lower() in {
        "",
        "missing",
        "none",
        "null",
        "placeholder",
        "todo",
        "unknown",
        "not-set",
        "not-the-derived-window",
    }


def _selector_parts(selector: Any, kind: str) -> tuple[str, str]:
    if (
        not isinstance(selector, str)
        or selector != selector.strip()
        or _placeholder(selector)
    ):
        raise EvidenceSelectorError("selector is missing or is a placeholder")
    prefix, separator, logical_id = selector.partition(":")
    if (
        not separator
        or prefix != _PREFIXES[kind]
        or logical_id != logical_id.strip()
        or _placeholder(logical_id)
    ):
        raise EvidenceSelectorError(f"selector prefix does not match {kind}")
    return prefix, logical_id


def _exact_sequence(value: Any, expected: tuple[str, ...], label: str) -> tuple[str, ...]:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or tuple(value) != expected
    ):
        raise EvidenceSelectorError(f"{label} must match the ordered contract exactly")
    return expected


def _exact_mapping_keys(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    keys = set(value)
    if keys != expected:
        missing = sorted(expected - keys)
        extra = sorted(keys - expected)
        details = []
        if missing:
            details.append(f"missing={missing}")
        if extra:
            details.append(f"extra={extra}")
        raise EvidenceSelectorError(f"{label} has an invalid shape ({', '.join(details)})")


def _owner_rules(contract: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    if not isinstance(contract, Mapping):
        raise EvidenceSelectorError("selector-provenance contract mapping is missing")
    _exact_mapping_keys(
        contract,
        frozenset(
            {
                "schema",
                "version",
                "logical_contract",
                "database_contract",
                "resolution",
                "selector_kinds",
                "comparison",
                "provenance_kinds",
                "provenance_contracts",
                "ownership",
                "plan_scope_sources",
            }
        ),
        "selector-provenance contract",
    )
    _exact_sequence(contract.get("selector_kinds"), _SELECTOR_KIND_ORDER, "selector_kinds")
    _exact_sequence(contract.get("provenance_kinds"), _PROVENANCE_KIND_ORDER, "provenance_kinds")
    provenance_contracts = contract.get("provenance_contracts")
    if (
        isinstance(provenance_contracts, (str, bytes))
        or not isinstance(provenance_contracts, Sequence)
        or len(provenance_contracts) != len(_PROVENANCE_KIND_ORDER)
    ):
        raise EvidenceSelectorError("selector provenance contracts are malformed")
    declared_provenance: list[str] = []
    for item in provenance_contracts:
        if not isinstance(item, Mapping):
            raise EvidenceSelectorError("selector provenance contract row is malformed")
        _exact_mapping_keys(
            item,
            frozenset({"kind", "required_fields", "stable_identity_fields"}),
            "selector provenance contract row",
        )
        kind = item.get("kind")
        if not isinstance(kind, str):
            raise EvidenceSelectorError("selector provenance contract kind is malformed")
        declared_provenance.append(kind)
    if tuple(declared_provenance) != _PROVENANCE_KIND_ORDER:
        raise EvidenceSelectorError("selector provenance contracts are out of order")
    ownership = contract.get("ownership")
    if (
        isinstance(ownership, (str, bytes))
        or not isinstance(ownership, Sequence)
        or len(ownership) != len(_SELECTOR_KIND_ORDER)
    ):
        raise EvidenceSelectorError("selector ownership is malformed")
    rules: dict[str, Mapping[str, Any]] = {}
    for item in ownership:
        if not isinstance(item, Mapping):
            raise EvidenceSelectorError("selector ownership row is malformed")
        _exact_mapping_keys(
            item,
            frozenset(
                {
                    "kind",
                    "owner",
                    "resolution_source",
                    "identity_basis",
                    "materialization",
                    "provenance_kind",
                    "required_provenance_fields",
                    "conditional_absence",
                }
            ),
            "selector ownership row",
        )
        kind = item.get("kind")
        if not isinstance(kind, str) or kind in rules or kind not in SELECTOR_KINDS:
            raise EvidenceSelectorError("selector ownership has an invalid or duplicate kind")
        provenance_kind = item.get("provenance_kind")
        required = item.get("required_provenance_fields")
        if provenance_kind not in PROVENANCE_KINDS or (
            isinstance(required, (str, bytes)) or not isinstance(required, Sequence)
        ):
            raise EvidenceSelectorError(f"selector owner rule is malformed for {kind}")
        if any(not isinstance(field, str) or not field for field in required):
            raise EvidenceSelectorError(f"selector owner rule fields are malformed for {kind}")
        rules[kind] = item
    if set(rules) != SELECTOR_KINDS:
        raise EvidenceSelectorError("selector ownership contract does not cover all 14 kinds")
    return rules


def _normalize_entries(
    required: Any,
    selector_ids: Mapping[str, str] | None,
) -> tuple[dict[str, Any], ...]:
    """Normalize accepted request shapes without losing caller order."""

    selector_values: Mapping[str, str] = selector_ids or {}
    if not isinstance(selector_values, Mapping) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in selector_values.items()
    ):
        raise EvidenceSelectorError("selector_ids are malformed")
    value = required
    if isinstance(value, EvidenceSelection):
        return tuple(
            {
                "role": item.role,
                "selector_kind": item.selector_kind,
                "selector": item.selector,
                "logical_id": item.logical_id,
            }
            for item in value.references
        )
    if isinstance(value, Mapping):
        for key in ("selections", "required", "evidence"):
            if key in value:
                if set(value) - {key, "selector_ids"}:
                    raise EvidenceSelectorError("evidence selection wrapper has extra fields")
                return _normalize_entries(value[key], value.get("selector_ids", selector_values))
        if "required_role_kinds" in value:
            if set(value) - {"required_role_kinds", "selector_ids"}:
                raise EvidenceSelectorError("required role-kind selection has extra fields")
            selector_values = value.get("selector_ids", selector_values)
            if not isinstance(selector_values, Mapping) or any(
                not isinstance(key, str) or not isinstance(item, str)
                for key, item in selector_values.items()
            ):
                raise EvidenceSelectorError("selector_ids are malformed")
            pairs = value["required_role_kinds"]
            if isinstance(pairs, (str, bytes)) or not isinstance(pairs, Sequence):
                raise EvidenceSelectorError("required role-kind selection is malformed")
            normalized_pairs: list[dict[str, Any]] = []
            for pair in pairs:
                if (
                    isinstance(pair, (str, bytes))
                    or not isinstance(pair, Sequence)
                    or len(pair) != 2
                    or not isinstance(pair[0], str)
                    or not isinstance(pair[1], str)
                ):
                    raise EvidenceSelectorError("required role-kind row is malformed")
                normalized_pairs.append(
                    {
                        "role": pair[0],
                        "selector_kind": pair[1],
                        "selector": selector_values.get(pair[0], selector_values.get(pair[1])),
                    }
                )
            value = normalized_pairs
        elif all(isinstance(key, str) for key in value):
            if any(not isinstance(selected, str) for selected in value.values()):
                raise EvidenceSelectorError("role-to-selector mapping is malformed")
            value = [
                {
                    "role": role,
                    "selector": selected,
                }
                for role, selected in value.items()
            ]
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise EvidenceSelectorError("ordered evidence selection is missing")
    entries: list[dict[str, Any]] = []
    roles: set[str] = set()
    for item in value:
        entry: dict[str, Any]
        if isinstance(item, EvidenceReference):
            entry = {
                "role": item.role,
                "selector_kind": item.selector_kind,
                "selector": item.selector,
                "logical_id": item.logical_id,
            }
        elif isinstance(item, Mapping):
            entry = dict(item)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)) and len(item) == 2:
            entry = {"role": item[0], "selector_kind": item[1]}
        else:
            raise EvidenceSelectorError("ordered evidence selection row is malformed")
        if isinstance(item, Mapping):
            allowed = {"role", "selector_kind", "kind", "selector", "logical_id"}
            if set(entry) - allowed:
                raise EvidenceSelectorError("evidence selection row has extra fields")
            if "selector_kind" in entry and "kind" in entry:
                raise EvidenceSelectorError("evidence selection row has duplicate selector kind fields")
        role = entry.get("role")
        kind = entry.get("selector_kind", entry.get("kind"))
        if not isinstance(role, str) or not role or role in roles:
            raise EvidenceSelectorError("evidence roles must be nonempty and unique")
        if not isinstance(kind, str) or kind not in SELECTOR_KINDS:
            # A role-to-selector mapping is intentionally not inferred: doing
            # so would hide a reordered or mismatched selector kind.
            raise EvidenceSelectorError(f"{role} has no valid selector kind")
        selector = entry.get("selector")
        if selector is None:
            selected = selector_values.get(role, selector_values.get(kind))
            if isinstance(selected, str):
                selector = selected if ":" in selected else f"{_PREFIXES[kind]}:{selected}"
        if selector is not None and (not isinstance(selector, str) or not selector):
            raise EvidenceSelectorError(f"{role} has a malformed selector")
        entry["role"] = role
        entry["selector_kind"] = kind
        entry["selector"] = selector
        roles.add(role)
        entries.append(entry)
    if not entries:
        raise EvidenceSelectorError("ordered evidence selection must not be empty")
    return tuple(entries)


def _window(request: Any, role: str) -> Mapping[str, Any]:
    value = request.parameters.get(role)
    if not isinstance(value, Mapping):
        raise EvidenceSelectorError(f"{role} has no typed request window")
    start, end, timezone = value.get("start_us"), value.get("end_us"), value.get("timezone", "UTC")
    if (
        isinstance(start, bool)
        or not isinstance(start, int)
        or isinstance(end, bool)
        or not isinstance(end, int)
        or end < start
        or not isinstance(timezone, str)
        or not timezone
    ):
        raise EvidenceSelectorError(f"{role} has invalid request window bounds")
    return {"start_us": start, "end_us": end, "timezone": timezone}


def _occurrences(connection: sqlite3.Connection, logical_id: str) -> list[dict[str, Any]]:
    cursor = _execute(connection, "occurrences", (logical_id,))
    result: list[dict[str, Any]] = []
    for row in cursor:
        value = _row_dict(row, cursor.description)
        record_ordinal = value.get("record_ordinal")
        byte_start, byte_end = value.get("byte_start"), value.get("byte_end")
        if (
            not isinstance(value.get("occurrence_id"), str)
            or not isinstance(value.get("semantic_logical_id"), str)
            or not isinstance(value.get("manifestation_id"), str)
            or not isinstance(value.get("source_revision"), str)
            or isinstance(record_ordinal, bool)
            or not isinstance(record_ordinal, int)
            or record_ordinal < 0
            or isinstance(byte_start, bool)
            or not isinstance(byte_start, int)
            or isinstance(byte_end, bool)
            or not isinstance(byte_end, int)
            or byte_start < 0
            or byte_end <= byte_start
            or not isinstance(value.get("adapter_version"), str)
            or not value.get("adapter_version")
            or value["semantic_logical_id"] != logical_id
        ):
            raise EvidenceSelectorError("source occurrence provenance is malformed")
        result.append(
            {
                "adapter_version": value["adapter_version"],
                "byte_end": byte_end,
                "byte_start": byte_start,
                "occurrence_id": value["occurrence_id"],
                "record_ordinal": record_ordinal,
                "semantic_logical_id": value["semantic_logical_id"],
                "source_manifestation_id": value["manifestation_id"],
                "source_revision": value["source_revision"],
            }
        )
    return result


def _require_nonempty(value: Any, label: str) -> None:
    if value in (None, "", [], {}, ()):
        raise EvidenceSelectorError(f"{label} provenance is incomplete")


def _validate_provenance(
    kind: str,
    provenance_kind: str,
    provenance: Mapping[str, Any],
    rules: Mapping[str, Mapping[str, Any]],
) -> None:
    if not isinstance(provenance, Mapping):
        raise EvidenceSelectorError(f"{kind} provenance is not a mapping")
    rule = rules.get(kind)
    if rule is None or rule.get("provenance_kind") != provenance_kind:
        raise EvidenceSelectorError(f"{kind} uses unsupported provenance {provenance_kind}")
    required = rule.get("required_provenance_fields")
    if (
        isinstance(required, (str, bytes))
        or not isinstance(required, Sequence)
        or not required
        or any(not isinstance(field, str) or not field for field in required)
        or len(set(required)) != len(required)
    ):
        raise EvidenceSelectorError(f"owner rule is malformed for {kind}")
    for field in required:
        _require_nonempty(provenance.get(field), f"{kind}.{field}")


def _current_head(connection: sqlite3.Connection) -> tuple[str, str | None]:
    cursor = _execute(connection, "head")
    rows = [_row_dict(row, cursor.description) for row in cursor]
    if len(rows) != 1:
        raise EvidenceSelectorError("publication head is missing or ambiguous")
    row = rows[0]
    if row.get("status") != "committed":
        raise EvidenceSelectorError("publication head is not committed")
    publication_id = row.get("publication_id")
    if not isinstance(publication_id, str) or not publication_id or publication_id != publication_id.strip():
        raise EvidenceSelectorError("publication head has no identity")
    digest = row.get("rate_card_digest")
    if digest is not None and (not isinstance(digest, str) or not digest):
        raise EvidenceSelectorError("publication rate-card digest is malformed")
    return publication_id, digest


def _alias(
    connection: sqlite3.Connection,
    selector: str,
) -> tuple[str, str, str] | None:
    cursor = _execute(connection, "alias", (selector,))
    rows = [_row_dict(row, cursor.description) for row in cursor]
    if not rows:
        return None
    if len(rows) != 1:
        raise EvidenceSelectorError("selector alias is ambiguous")
    row = rows[0]
    canonical = row.get("canonical_selector")
    logical_id = row.get("logical_id")
    reason = row.get("reason")
    if (
        not isinstance(canonical, str)
        or not canonical
        or not isinstance(logical_id, str)
        or not logical_id
        or reason not in {"identity_correction", "recanonicalization"}
        or canonical == selector
    ):
        raise EvidenceSelectorError("selector alias is malformed")
    return canonical, logical_id, reason


def _source_provenance(
    connection: sqlite3.Connection,
    kind: str,
    logical_id: str,
) -> Mapping[str, Any]:
    if kind == "model_profile":
        profile_cursor = _execute(connection, "profile", (logical_id,))
        profiles = [_row_dict(row, profile_cursor.description) for row in profile_cursor]
        if len(profiles) != 1:
            raise EvidenceSelectorError("model profile selector does not resolve")
        profile = profiles[0]
        calls_cursor = _execute(connection, "profile_calls", (logical_id,))
        calls = [row[0] for row in calls_cursor]
        if not calls or any(not isinstance(call_id, str) or not call_id for call_id in calls):
            raise EvidenceSelectorError("model profile has no representative call")
        representative: list[Mapping[str, Any]] = []
        for call_id in calls:
            occurrences = _occurrences(connection, call_id)
            if not occurrences:
                raise EvidenceSelectorError("model profile representative call has no occurrence")
            representative.extend(occurrences)
        profile_tuple = {
            "model": profile.get("model"),
            "reasoning_effort": profile.get("reasoning_effort"),
            "service_tier": profile.get("service_tier"),
        }
        if any(
            not isinstance(value, str) or not value
            for value in profile_tuple.values()
        ):
            raise EvidenceSelectorError("model profile provenance is incomplete")
        representative.sort(
            key=lambda item: (
                item["record_ordinal"],
                item["byte_start"],
                item["byte_end"],
                item["occurrence_id"],
            )
        )
        return {
            "profile_tuple": profile_tuple,
            "representative_call_occurrences": representative,
            "representative_call_selectors": [f"call:{call_id}" for call_id in calls],
        }

    exists_cursor = _execute(connection, kind, (logical_id,))
    if exists_cursor.fetchone() is None:
        raise EvidenceSelectorError(f"{kind} selector does not resolve")
    occurrences = _occurrences(connection, logical_id)
    if not occurrences:
        raise EvidenceSelectorError(f"{kind} selector has no source occurrence")
    return {"occurrences": occurrences}


def _rate_card_provenance(
    connection: sqlite3.Connection,
    publication_id: str,
    publication_digest: str | None,
    logical_id: str,
) -> Mapping[str, Any]:
    if publication_digest is None or logical_id != publication_digest:
        raise EvidenceSelectorError("rate-card selector is not the selected publication frontier")
    active_cursor = _execute(connection, "active_rate_card")
    active_rows = [_row_dict(row, active_cursor.description) for row in active_cursor]
    if (
        len(active_rows) != 1
        or active_rows[0].get("publication_id") != publication_id
        or active_rows[0].get("digest") != publication_digest
        or active_rows[0].get("validation_status") != "valid"
    ):
        raise EvidenceSelectorError("selected rate-card authority is not active")
    try:
        frontier = load_publication_rate_card_frontier(connection, publication_id)
    except RateCardFrontierError as error:
        raise EvidenceSelectorError("selected rate-card frontier is invalid") from error
    if frontier is None or validate_rate_card_frontier(frontier, publication_digest) is not None:
        raise EvidenceSelectorError("selected rate-card frontier is invalid")
    cursor = _execute(connection, "rate_card", (logical_id, logical_id))
    rows = [_row_dict(row, cursor.description) for row in cursor]
    matches = [row for row in rows if row.get("digest") == logical_id]
    if len(matches) != 1 or matches[0].get("validation_status") != "valid":
        raise EvidenceSelectorError("rate-card selector does not resolve")
    row = matches[0]
    if not any(
        (
            revision.digest
            if not isinstance(revision, Mapping)
            else revision.get("digest")
        )
        == logical_id
        for revision in frontier.revisions
    ):
        raise EvidenceSelectorError("rate-card selector is outside the captured frontier")
    return {
        "digest": row.get("digest"),
        "source_name": row.get("source_name"),
        "fetched_at_us": row.get("fetched_at_us"),
        "validation_status": row.get("validation_status"),
    }


def _publication_provenance(
    connection: sqlite3.Connection,
    publication_id: str,
    current_publication_id: str,
) -> Mapping[str, Any]:
    if publication_id != current_publication_id:
        raise EvidenceSelectorError("publication selector is not the committed head")
    cursor = _execute(connection, "publication", (publication_id,))
    rows = [_row_dict(row, cursor.description) for row in cursor]
    if len(rows) != 1 or rows[0].get("status") != "committed":
        raise EvidenceSelectorError("publication selector does not resolve to committed head")
    row = rows[0]
    return {
        "operation_id": row.get("operation_id"),
        "artifact_manifest_sha256": row.get("artifact_manifest_sha256"),
        "committed_at_us": row.get("committed_at_us"),
    }


def _source_inventory_provenance(
    connection: sqlite3.Connection,
    logical_id: str,
    current_publication_id: str,
) -> Mapping[str, Any]:
    cursor = _execute(connection, "source_manifestation", (logical_id,))
    rows = [_row_dict(row, cursor.description) for row in cursor]
    if len(rows) != 1:
        raise EvidenceSelectorError("source manifestation selector does not resolve")
    row = rows[0]
    if row.get("selected") != 1:
        raise EvidenceSelectorError("source manifestation selector is not selected")
    return {
        "source_id": row.get("source_id"),
        "content_revision": row.get("content_revision"),
        "state": row.get("state"),
        "selected_publication_id": current_publication_id,
    }


def _boundary_provenance(connection: sqlite3.Connection, logical_id: str) -> Mapping[str, Any]:
    cursor = _execute(connection, "allowance_interval", (logical_id,))
    rows = [_row_dict(row, cursor.description) for row in cursor]
    if len(rows) != 1:
        raise EvidenceSelectorError("allowance interval selector does not resolve")
    row = rows[0]
    start_id, end_id = row.get("start_observation_id"), row.get("end_observation_id")
    if (
        not isinstance(start_id, str)
        or not isinstance(end_id, str)
        or start_id == end_id
        or not isinstance(row.get("compatibility_basis"), str)
        or not row.get("compatibility_basis")
    ):
        raise EvidenceSelectorError("allowance interval boundary provenance is incomplete")
    start_occurrences = _occurrences(connection, start_id)
    end_occurrences = _occurrences(connection, end_id)
    if not start_occurrences or not end_occurrences:
        raise EvidenceSelectorError("allowance interval boundaries have no source occurrences")
    return {
        "compatibility_version": "allowance-compatibility-v1",
        "end_observation_selector": f"allowance-observation:{end_id}",
        "end_occurrences": end_occurrences,
        "start_observation_selector": f"allowance-observation:{start_id}",
        "start_occurrences": start_occurrences,
    }


def _resolve_one(
    connection: sqlite3.Connection,
    request: Any,
    entry: Mapping[str, Any],
    rules: Mapping[str, Mapping[str, Any]],
    current_publication_id: str,
    publication_digest: str | None,
    digest: str,
) -> EvidenceReference:
    role = entry.get("role")
    kind = entry.get("selector_kind", entry.get("kind"))
    if not isinstance(role, str) or not role or not isinstance(kind, str) or kind not in SELECTOR_KINDS:
        raise EvidenceSelectorError("evidence role or selector kind is invalid")

    if kind == "window":
        value = _window(request, role)
        logical_id = semantic_id(
            "window",
            [digest, role, value["start_us"], value["end_us"], value["timezone"]],
        )
        expected_selector = f"window:{logical_id}"
        selector = entry.get("selector")
        if selector is not None and selector != expected_selector:
            raise EvidenceSelectorError(f"{role} window selector does not match request identity")
        supplied = entry.get("logical_id")
        if supplied is not None and supplied != logical_id:
            raise EvidenceSelectorError(f"{role} window logical ID does not match request identity")
        window_provenance = {
            "end_us": value["end_us"],
            "parameter_role": role,
            "request_digest": digest,
            "start_us": value["start_us"],
            "timezone": value["timezone"],
        }
        _validate_provenance(kind, "request_derivation", window_provenance, rules)
        return EvidenceReference(
            role,
            kind,
            expected_selector,
            logical_id,
            "request_derivation",
            window_provenance,
        )

    selector = entry.get("selector")
    if selector is None:
        raise EvidenceSelectorError(f"{role} has no exact selector")
    _selector_parts(selector, kind)
    _, selector_id = _selector_parts(selector, kind)
    alias = _alias(connection, selector)
    canonical_selector = selector
    canonical_id = selector_id
    alias_reason: str | None = None
    if alias is not None:
        canonical_selector, alias_logical_id, alias_reason = alias
        _selector_parts(canonical_selector, kind)
        _, canonical_suffix = _selector_parts(canonical_selector, kind)
        if canonical_suffix != alias_logical_id:
            raise EvidenceSelectorError("selector alias canonical identity does not match its row")
        canonical_id = alias_logical_id
    supplied_id = entry.get("logical_id")
    if supplied_id is not None and (
        not isinstance(supplied_id, str)
        or supplied_id not in {selector_id, canonical_id}
    ):
        raise EvidenceSelectorError(f"{role} logical ID does not match its selector")

    provenance: Mapping[str, Any]
    if kind == "rate_card":
        provenance_kind = "configured_artifact"
        provenance = _rate_card_provenance(
            connection, current_publication_id, publication_digest, canonical_id
        )
    elif kind == "publication":
        provenance_kind = "publication_commit"
        provenance = _publication_provenance(connection, canonical_id, current_publication_id)
    elif kind == "source_manifestation":
        provenance_kind = "source_inventory"
        provenance = _source_inventory_provenance(
            connection, canonical_id, current_publication_id
        )
    elif kind == "allowance_interval":
        provenance_kind = "derived_boundary_pair"
        provenance = _boundary_provenance(connection, canonical_id)
    else:
        provenance_kind = "source_occurrence"
        provenance = _source_provenance(connection, kind, canonical_id)

    if alias is not None:
        disclosed = dict(provenance)
        disclosed["alias"] = {
            "alias_applied": True,
            "canonical_selector": canonical_selector,
            "reason": alias_reason,
            "requested_selector": selector,
        }
        provenance = disclosed
    _validate_provenance(kind, provenance_kind, provenance, rules)
    return EvidenceReference(
        role,
        kind,
        selector,
        canonical_id,
        provenance_kind,
        provenance,
    )


def resolve_evidence_references(
    connection: sqlite3.Connection,
    request: Any,
    selector_provenance: Mapping[str, Any],
    required: Any,
    *,
    selector_ids: Mapping[str, str] | None = None,
    publication_id: str | None = None,
) -> tuple[EvidenceReference, ...]:
    """Resolve exactly the supplied ordered requirements through their owners."""

    if not isinstance(connection, sqlite3.Connection):
        raise EvidenceSelectorError("connection must be a sqlite3.Connection")
    if not getattr(connection, "in_transaction", False):
        raise EvidenceSelectorError(
            "evidence selector resolution requires one caller-owned active read transaction"
        )
    try:
        query_only = connection.execute("PRAGMA query_only").fetchone()[0]
    except sqlite3.DatabaseError as error:
        raise EvidenceSelectorError("connection is not a SQLite query surface") from error
    if int(query_only) != 1:
        raise EvidenceSelectorError("evidence selector resolution requires PRAGMA query_only=1")
    if not hasattr(request, "parameters") or not hasattr(request, "plan_id"):
        raise EvidenceSelectorError("request must be a production PlanRequest")
    rules = _owner_rules(selector_provenance)
    entries = _normalize_entries(required, selector_ids)
    digest = request_digest(request)
    current_publication_id, publication_digest = _current_head(connection)
    if publication_id is not None and publication_id != current_publication_id:
        raise EvidenceSelectorError("evidence publication does not match committed head")
    resolved = tuple(
        _resolve_one(
            connection,
            request,
            entry,
            rules,
            current_publication_id,
            publication_digest,
            digest,
        )
        for entry in entries
    )
    expected = tuple(
        (
            entry["role"],
            entry["selector_kind"],
            resolved[index].selector if entry.get("selector") is None else entry["selector"],
        )
        for index, entry in enumerate(entries)
    )
    actual = tuple((item.role, item.selector_kind, item.selector) for item in resolved)
    if expected != actual:
        raise EvidenceSelectorError("required and materialized evidence sequences differ")
    for item in resolved:
        _validate_provenance(item.selector_kind, item.provenance_kind, item.provenance, rules)
    return resolved


resolve_selectors = resolve_evidence_references


class EvidenceSelectorResolver:
    """Object boundary for dependency-injected selector ownership."""

    def __init__(self, selector_provenance: Mapping[str, Any]) -> None:
        self.selector_provenance = selector_provenance

    def resolve(
        self,
        connection: sqlite3.Connection,
        request: Any,
        required: Any,
        *,
        selector_ids: Mapping[str, str] | None = None,
        publication_id: str | None = None,
    ) -> tuple[EvidenceReference, ...]:
        return resolve_evidence_references(
            connection,
            request,
            self.selector_provenance,
            required,
            selector_ids=selector_ids,
            publication_id=publication_id,
        )


__all__ = [
    "EvidenceReference",
    "EvidenceReferenceV1",
    "EvidenceSelection",
    "EvidenceSelectorError",
    "EvidenceSelectorResolver",
    "PROVENANCE_KINDS",
    "SELECTOR_KINDS",
    "SELECTOR_STATEMENTS",
    "SelectorResolutionError",
    "resolve_evidence_references",
    "resolve_selectors",
]
