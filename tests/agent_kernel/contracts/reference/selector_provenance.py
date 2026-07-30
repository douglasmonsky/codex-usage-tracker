from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


class SelectorProvenanceError(ValueError):
    """Raised when an evidence-reference comparison fails closed."""


@dataclass(frozen=True)
class EvidenceReferenceV1:
    role: str
    selector_kind: str
    selector: str
    logical_id: str
    provenance_kind: str
    provenance: Mapping[str, Any]


def validate_evidence_references_v1(
    required_role_kinds: Sequence[tuple[str, str]],
    materialized: Sequence[EvidenceReferenceV1],
    owner_rules: Mapping[str, Mapping[str, Any]],
    resolve_owner_entity: Callable[[str, str], bool],
) -> tuple[EvidenceReferenceV1, ...]:
    """Require exact ordered roles/kinds, real entities, and typed provenance."""

    actual = [(item.role, item.selector_kind) for item in materialized]
    if list(required_role_kinds) != actual:
        raise SelectorProvenanceError(
            "required and materialized evidence role/kind sequences differ"
        )
    for item in materialized:
        if not resolve_owner_entity(item.selector_kind, item.logical_id):
            raise SelectorProvenanceError(
                f"{item.role} references no logical entity"
            )
        if not item.selector or not item.logical_id:
            raise SelectorProvenanceError(
                f"{item.role} has an empty selector or logical ID"
            )
        if not item.provenance_kind:
            raise SelectorProvenanceError(f"{item.role} has no provenance kind")
        rule = owner_rules.get(item.selector_kind)
        if rule is None or item.provenance_kind != rule.get("provenance_kind"):
            raise SelectorProvenanceError(
                f"{item.role} uses unsupported provenance {item.provenance_kind}"
            )
        expected_fields = rule.get("required_provenance_fields")
        if not isinstance(expected_fields, Sequence):
            raise SelectorProvenanceError(f"{item.role} owner rule is malformed")
        missing = [
            field
            for field in expected_fields
            if item.provenance.get(field) in (None, "", [], {})
        ]
        if missing:
            raise SelectorProvenanceError(
                f"{item.role} provenance is incomplete: {missing}"
            )
    return tuple(materialized)


def validate_reference_stability_v1(
    baseline: Sequence[EvidenceReferenceV1],
    replayed: Sequence[EvidenceReferenceV1],
    stable_provenance_fields: Mapping[str, Sequence[str]],
) -> tuple[EvidenceReferenceV1, ...]:
    """Keep semantic references stable while allowing occurrence relocation."""

    if len(baseline) != len(replayed):
        raise SelectorProvenanceError("evidence reference count changed during replay")
    for before, after in zip(baseline, replayed, strict=True):
        before_identity = (
            before.role,
            before.selector_kind,
            before.selector,
            before.logical_id,
            before.provenance_kind,
        )
        after_identity = (
            after.role,
            after.selector_kind,
            after.selector,
            after.logical_id,
            after.provenance_kind,
        )
        if before_identity != after_identity:
            raise SelectorProvenanceError(
                f"{before.role} semantic selector changed during replay"
            )
        fields = stable_provenance_fields.get(before.provenance_kind)
        if fields is None:
            raise SelectorProvenanceError(
                f"{before.role} uses unsupported provenance {before.provenance_kind}"
            )
        if any(before.provenance.get(field) != after.provenance.get(field) for field in fields):
            raise SelectorProvenanceError(
                f"{before.role} stable provenance identity changed during replay"
            )
    return tuple(replayed)
