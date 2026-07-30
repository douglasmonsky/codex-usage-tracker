"""Pure preparation for publication-captured immutable rate-card frontiers."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import cast

from ..domain.valuation import (
    RateCardFrontier,
    RateCardRevision,
    ValuationDirtyInterval,
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

    ids_by_digest = {
        revision.digest: revision.rate_card_id for revision in current_revisions
    }
    added = tuple(
        revision
        for revision in current_revisions
        if revision.digest not in previous_by_digest
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


def attach_rate_card_frontier(
    write_set: PublicationWriteSet,
    request: PublicationRequest,
    prepared: PreparedRateCardFrontier,
) -> PublicationWriteSet:
    """Attach prevalidated frontier rows to a fully materialized write set."""

    if request.rate_card_digest != prepared.frontier.head_digest:
        raise ValueError("publication request rate-card digest differs from prepared frontier")
    return replace(
        write_set,
        identities=(*write_set.identities, *prepared.identities),
        rows=(*write_set.rows, *prepared.rows),
    )
