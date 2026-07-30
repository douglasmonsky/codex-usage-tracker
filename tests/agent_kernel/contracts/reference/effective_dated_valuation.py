"""Independent synthetic reference evaluator for CK-07D boundary cases."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def select_revision(
    *,
    event_at_us: int,
    model_profile: dict[str, object],
    revisions: list[dict[str, Any]],
) -> tuple[str, str, str]:
    """Select one revision by effective time, then same-time match precedence."""

    for effective_at_us in sorted(
        {
            int(revision["effective_at_us"])
            for revision in revisions
            if int(revision["effective_at_us"]) <= event_at_us
        },
        reverse=True,
    ):
        matches: list[tuple[int, dict[str, Any]]] = []
        for revision in revisions:
            if revision["effective_at_us"] != effective_at_us:
                continue
            rule = revision["rule"]
            if rule.get("model_profile_id") == model_profile["model_profile_id"]:
                matches.append((0, revision))
            elif model_profile.get("model") in rule.get("model_aliases", []):
                matches.append((1, revision))
        if not matches:
            continue
        precedence = min(item[0] for item in matches)
        winners = [revision for rank, revision in matches if rank == precedence]
        if len(winners) != 1:
            raise ValueError("ambiguous synthetic valuation boundary")
        selected = winners[0]
        return (
            str(selected["digest"]),
            "exact_model_profile" if precedence == 0 else "model_alias",
            canonical_cost(selected["rate"], selected["tokens"]),
        )
    raise LookupError("no effective synthetic valuation revision")


def canonical_cost(rate: str, tokens: int) -> str:
    amount = Decimal(rate) * Decimal(tokens) / Decimal(1_000_000)
    if amount == 0:
        return "0"
    text = format(amount.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text
