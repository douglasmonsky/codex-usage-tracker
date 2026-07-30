"""Database-v1 rate-card frontier loading and same-snapshot validation."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from typing import cast

from ..domain.valuation import (
    RateCardFrontier,
    RateCardRevision,
    validate_rate_card_frontier,
)


class RateCardFrontierError(ValueError):
    """A publication cannot reproduce its captured rate-card lineage."""


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _decode_json(value: object, field: str) -> object:
    if not isinstance(value, str):
        raise RateCardFrontierError(f"{field} must be canonical JSON text")

    def reject_non_finite(constant: str) -> object:
        raise ValueError(f"non-finite JSON constant: {constant}")

    try:
        return json.loads(value, parse_constant=reject_non_finite)
    except (json.JSONDecodeError, ValueError) as error:
        raise RateCardFrontierError(f"{field} must be canonical JSON text") from error


def _json_object(value: object, field: str) -> Mapping[str, object]:
    decoded = _decode_json(value, field)
    if not isinstance(decoded, Mapping):
        raise RateCardFrontierError(f"{field} must decode to an object")
    if _canonical_json(decoded) != value:
        raise RateCardFrontierError(f"{field} must be canonical JSON text")
    return decoded


def _json_rules(value: object) -> tuple[Mapping[str, object], ...]:
    decoded = _decode_json(value, "model_match_rules_json")
    if (
        isinstance(decoded, (str, bytes))
        or not isinstance(decoded, Sequence)
        or any(not isinstance(rule, Mapping) for rule in decoded)
    ):
        raise RateCardFrontierError("model_match_rules_json must decode to object rows")
    if _canonical_json(decoded) != value:
        raise RateCardFrontierError("model_match_rules_json must be canonical JSON text")
    return tuple(decoded)


def _json_rate_map(value: object, field: str) -> Mapping[str, str | None]:
    decoded = _json_object(value, field)
    if any(
        not isinstance(key, str)
        or (rate is not None and not isinstance(rate, str))
        for key, rate in decoded.items()
    ):
        raise RateCardFrontierError(f"{field} must map text fields to text or null")
    return {
        str(key): cast(str | None, rate)
        for key, rate in decoded.items()
    }


def load_publication_rate_card_frontier(
    connection: sqlite3.Connection,
    publication_id: str,
) -> RateCardFrontier | None:
    """Load only the immutable predecessor chain captured by one publication."""

    publication = connection.execute(
        "SELECT rate_card_digest FROM publications WHERE publication_id = ?",
        (publication_id,),
    ).fetchone()
    if publication is None:
        raise RateCardFrontierError("publication does not exist")
    head_digest = publication[0]
    if head_digest is None:
        return None
    if not isinstance(head_digest, str):
        raise RateCardFrontierError("publication rate-card digest is malformed")

    columns = (
        "rate_card_id",
        "digest",
        "predecessor_rate_card_id",
        "source_name",
        "source_url",
        "effective_at_us",
        "fetched_at_us",
        "currency",
        "model_match_rules_json",
        "four_class_rates_json",
        "credit_rates_json",
        "reasoning_in_output",
        "confidence",
        "validation_status",
    )
    rows = {
        str(row[0]): row
        for row in connection.execute(
            f"SELECT {', '.join(columns)} FROM rate_card_revisions"
        )
    }
    digest_to_id = {str(row[1]): rate_card_id for rate_card_id, row in rows.items()}
    current_id = digest_to_id.get(head_digest)
    if current_id is None:
        raise RateCardFrontierError("publication rate-card head is missing")

    ordered: list[RateCardRevision] = []
    seen: set[str] = set()
    while current_id is not None:
        if current_id in seen:
            raise RateCardFrontierError("rate-card lineage contains a cycle")
        seen.add(current_id)
        row = rows.get(current_id)
        if row is None:
            raise RateCardFrontierError("rate-card predecessor is missing")
        predecessor_id = row[2]
        predecessor_digest: str | None = None
        if predecessor_id is not None:
            predecessor = rows.get(str(predecessor_id))
            if predecessor is None:
                raise RateCardFrontierError("rate-card predecessor is missing")
            predecessor_digest = str(predecessor[1])
        ordered.append(
            RateCardRevision(
                rate_card_id=str(row[0]),
                digest=str(row[1]),
                predecessor_digest=predecessor_digest,
                source_name=str(row[3]),
                source_url=None if row[4] is None else str(row[4]),
                effective_at_us=row[5],
                fetched_at_us=row[6],
                currency=str(row[7]),
                model_match_rules=_json_rules(row[8]),
                four_class_rates=_json_rate_map(row[9], "four_class_rates_json"),
                credit_rates=_json_rate_map(row[10], "credit_rates_json"),
                reasoning_in_output=bool(row[11]),
                confidence=str(row[12]),
                validation_status=str(row[13]),
            )
        )
        current_id = None if predecessor_id is None else str(predecessor_id)
    return RateCardFrontier(head_digest=head_digest, revisions=tuple(ordered))


def validate_publication_rate_card_frontier(
    connection: sqlite3.Connection,
    publication_id: str,
) -> RateCardFrontier | None:
    """Validate the publication/head pair and its complete captured lineage."""

    publication = connection.execute(
        "SELECT rate_card_digest FROM publications WHERE publication_id = ?",
        (publication_id,),
    ).fetchone()
    if publication is None:
        raise RateCardFrontierError("publication does not exist")
    publication_digest = publication[0]
    active = connection.execute(
        """
        SELECT active.publication_id, revision.digest
        FROM active_rate_card AS active
        JOIN rate_card_revisions AS revision
          ON revision.rate_card_id = active.rate_card_id
        WHERE active.singleton = 1
        """
    ).fetchone()
    if publication_digest is None:
        if active is not None:
            raise RateCardFrontierError(
                "active rate-card head exists without publication capture"
            )
        return None
    if (
        active is None
        or str(active[0]) != publication_id
        or str(active[1]) != str(publication_digest)
    ):
        raise RateCardFrontierError("publication and active rate-card head disagree")
    frontier = load_publication_rate_card_frontier(connection, publication_id)
    assert frontier is not None
    reason = validate_rate_card_frontier(frontier, str(publication_digest))
    if reason is not None:
        raise RateCardFrontierError(reason.value)
    return frontier
