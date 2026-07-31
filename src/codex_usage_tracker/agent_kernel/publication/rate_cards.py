"""Pure preparation for publication-captured immutable rate-card frontiers."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, cast

from ..domain.valuation import (
    RateCardFrontier,
    RateCardRevision,
    ValuationDirtyInterval,
    compile_current_valuation_matches,
    derive_frontier_dirty_intervals,
    validate_rate_card_frontier,
)
from .writer import IdentityMutation, PreparedRow, PublicationRequest, PublicationWriteSet


@dataclass(frozen=True, slots=True)
class PreparedRateCardFrontier:
    """New immutable rows plus the exact valuation interval they dirty."""

    frontier: RateCardFrontier
    identities: tuple[IdentityMutation, ...]
    rows: tuple[PreparedRow, ...]
    dirty_intervals: tuple[ValuationDirtyInterval, ...]


@dataclass(frozen=True, slots=True)
class CurrentValuationInputs:
    """Complete current inputs used to derive publication coverage outside the lock."""

    calls: tuple[Mapping[str, Any], ...]
    profiles: tuple[Mapping[str, Any], ...]
    context_component_count: int

    def __post_init__(self) -> None:
        if self.context_component_count < 0:
            raise ValueError("context-component coverage count cannot be negative")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _revision_row(
    revision: RateCardRevision,
    *,
    predecessor_rate_card_id: str | None,
    publication_id: str,
) -> PreparedRow:
    return PreparedRow(
        "rate_card_revisions",
        {
            "rate_card_id": revision.rate_card_id,
            "digest": revision.digest,
            "predecessor_rate_card_id": predecessor_rate_card_id,
            "source_name": revision.source_name,
            "source_url": revision.source_url,
            "effective_at_us": revision.effective_at_us,
            "fetched_at_us": revision.fetched_at_us,
            "currency": revision.currency,
            "model_match_rules_json": _canonical_json(revision.model_match_rules),
            "four_class_rates_json": _canonical_json(revision.four_class_rates),
            "credit_rates_json": _canonical_json(revision.credit_rates),
            "reasoning_in_output": int(revision.reasoning_in_output),
            "confidence": revision.confidence,
            "validation_status": revision.validation_status,
            "first_seen_publication_id": publication_id,
        },
    )


def prepare_rate_card_frontier(
    frontier: RateCardFrontier,
    *,
    publication_id: str,
    previous: RateCardFrontier | None = None,
) -> PreparedRateCardFrontier:
    """Validate one immutable extension and prepare only newly admitted rows."""

    reason = validate_rate_card_frontier(frontier, frontier.head_digest)
    if reason is not None:
        raise ValueError(f"rate-card frontier invalid: {reason.value}")
    if any(not isinstance(revision, RateCardRevision) for revision in frontier.revisions):
        raise ValueError("publication preparation requires typed rate-card revisions")
    current_revisions = cast(tuple[RateCardRevision, ...], frontier.revisions)
    if previous is not None:
        previous_reason = validate_rate_card_frontier(previous, previous.head_digest)
        if previous_reason is not None:
            raise ValueError(f"previous rate-card frontier invalid: {previous_reason.value}")
        if any(not isinstance(revision, RateCardRevision) for revision in previous.revisions):
            raise ValueError("previous frontier requires typed rate-card revisions")
        previous_revisions = cast(tuple[RateCardRevision, ...], previous.revisions)
    else:
        previous_revisions = ()

    current_by_digest = {revision.digest: revision for revision in current_revisions}
    previous_by_digest = {revision.digest: revision for revision in previous_revisions}
    for digest, revision in previous_by_digest.items():
        current = current_by_digest.get(digest)
        if current is None:
            raise ValueError("rate-card frontier cannot remove an admitted revision")
        if current != revision:
            raise ValueError("rate-card revision is immutable once admitted")

    ids_by_digest = {revision.digest: revision.rate_card_id for revision in current_revisions}
    added = tuple(
        revision for revision in current_revisions if revision.digest not in previous_by_digest
    )
    identities = tuple(
        IdentityMutation(
            logical_id=revision.rate_card_id,
            entity_kind="rate-card",
            identity_tuple=[revision.digest],
        )
        for revision in added
    )
    rows = tuple(
        _revision_row(
            revision,
            predecessor_rate_card_id=(
                None
                if revision.predecessor_digest is None
                else ids_by_digest[revision.predecessor_digest]
            ),
            publication_id=publication_id,
        )
        for revision in added
    )
    return PreparedRateCardFrontier(
        frontier=frontier,
        identities=identities,
        rows=rows,
        dirty_intervals=derive_frontier_dirty_intervals(previous, frontier),
    )


def read_current_valuation_inputs(
    connection: sqlite3.Connection,
    write_set: PublicationWriteSet,
) -> CurrentValuationInputs:
    """Read the complete current valuation inventory and overlay pending rows.

    This is an outside-lock query-time derivation.  It deliberately does not
    persist a call-price cache: each publication recompiles coverage from the
    current canonical calls, profiles, captured frontier, and pending changes.
    """

    def rows(statement: str) -> list[dict[str, Any]]:
        cursor = connection.execute(statement)
        columns = tuple(str(item[0]) for item in cursor.description or ())
        return [dict(zip(columns, row, strict=True)) for row in cursor]

    current_calls = {
        str(row["call_id"]): row
        for row in rows(
            """
            SELECT call_id, model_profile_id, uncached_input_tokens,
                   cached_input_tokens, reasoning_tokens, output_tokens,
                   event_at_us
              FROM model_calls_visible
             ORDER BY call_id
            """
        )
    }
    current_profiles = {
        str(row["model_profile_id"]): row
        for row in rows(
            """
            SELECT model_profile_id, model, reasoning_effort, service_tier
              FROM model_profiles
             ORDER BY model_profile_id
            """
        )
    }
    context_component_ids = {
        str(row[0])
        for row in connection.execute(
            "SELECT component_id FROM context_components ORDER BY component_id"
        )
    }
    for row in write_set.rows:
        values = dict(row.values)
        if row.table == "model_call_tail":
            current_calls[str(values["call_id"])] = {
                "call_id": values["call_id"],
                "model_profile_id": values["model_profile_id"],
                "uncached_input_tokens": values["uncached_input_tokens"],
                "cached_input_tokens": values["cached_input_tokens"],
                "reasoning_tokens": values["reasoning_tokens"],
                "output_tokens": values["output_tokens"],
                "event_at_us": values["event_at_us"],
            }
        elif row.table == "model_profiles":
            current_profiles[str(values["model_profile_id"])] = {
                "model_profile_id": values["model_profile_id"],
                "model": values["model"],
                "reasoning_effort": values["reasoning_effort"],
                "service_tier": values["service_tier"],
            }
        elif row.table == "context_components":
            context_component_ids.add(str(values["component_id"]))
    return CurrentValuationInputs(
        calls=tuple(current_calls[key] for key in sorted(current_calls)),
        profiles=tuple(current_profiles[key] for key in sorted(current_profiles)),
        context_component_count=len(context_component_ids),
    )


def _initial_valuation_inputs(write_set: PublicationWriteSet) -> CurrentValuationInputs:
    """Derive complete inputs for an initial publication from its full write set."""

    calls: dict[str, Mapping[str, Any]] = {}
    profiles: dict[str, Mapping[str, Any]] = {}
    context_component_ids: set[str] = set()
    for row in write_set.rows:
        values = dict(row.values)
        if row.table == "model_call_tail":
            call_id = str(values["call_id"])
            calls[call_id] = {
                "call_id": call_id,
                "model_profile_id": values["model_profile_id"],
                "uncached_input_tokens": values["uncached_input_tokens"],
                "cached_input_tokens": values["cached_input_tokens"],
                "reasoning_tokens": values["reasoning_tokens"],
                "output_tokens": values["output_tokens"],
                "event_at_us": values["event_at_us"],
            }
        elif row.table == "model_profiles":
            profile_id = str(values["model_profile_id"])
            profiles[profile_id] = {
                "model_profile_id": profile_id,
                "model": values["model"],
                "reasoning_effort": values["reasoning_effort"],
                "service_tier": values["service_tier"],
            }
        elif row.table == "context_components":
            context_component_ids.add(str(values["component_id"]))
    return CurrentValuationInputs(
        calls=tuple(calls[key] for key in sorted(calls)),
        profiles=tuple(profiles[key] for key in sorted(profiles)),
        context_component_count=len(context_component_ids),
    )


def attach_rate_card_frontier(
    write_set: PublicationWriteSet,
    request: PublicationRequest,
    prepared: PreparedRateCardFrontier,
    *,
    current_inputs: CurrentValuationInputs | None = None,
) -> PublicationWriteSet:
    """Attach frontier rows and accurately derived current capability coverage."""

    if request.rate_card_digest != prepared.frontier.head_digest:
        raise ValueError("publication request rate-card digest differs from prepared frontier")
    if current_inputs is None:
        if request.parent_publication_id is not None:
            raise ValueError(
                "incremental and rate-card-only publications require complete current "
                "valuation inputs"
            )
        current_inputs = _initial_valuation_inputs(write_set)
    matches = compile_current_valuation_matches(
        current_inputs.calls,
        current_inputs.profiles,
        prepared.frontier,
        publication_rate_card_digest=request.rate_card_digest,
    )
    priced_calls = sum(
        match.cost_grade == "configured_estimate" and match.configured_cost_usd is not None
        for match in matches
    )
    eligible_calls = len(current_inputs.calls)
    coverage_rows = (
        PreparedRow(
            "publication_capability_coverage",
            {
                "publication_id": request.publication_id,
                "capability_id": "context_components",
                "eligible_entity_count": current_inputs.context_component_count,
                "observed_entity_count": current_inputs.context_component_count,
                "unavailable_entity_count": 0,
                "measurement_mask": 0,
                "grade": "exact",
                "basis": "current_canonical_inventory_v1",
            },
        ),
        PreparedRow(
            "publication_capability_coverage",
            {
                "publication_id": request.publication_id,
                "capability_id": "valuation",
                "eligible_entity_count": eligible_calls,
                "observed_entity_count": priced_calls,
                "unavailable_entity_count": eligible_calls - priced_calls,
                "measurement_mask": 0,
                "grade": "configured_estimate",
                "basis": "effective_dated_frontier_recompile_v1",
            },
        ),
    )
    return replace(
        write_set,
        identities=(*write_set.identities, *prepared.identities),
        rows=(*write_set.rows, *prepared.rows, *coverage_rows),
    )
