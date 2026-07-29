from __future__ import annotations

from typing import Any

from tests.agent_kernel.contracts.reference.identity import semantic_id
from tests.agent_kernel.contracts.reference.selectors import format_selector
from tests.agent_kernel.fixtures.generator.profile import FixtureProfile
from tests.agent_kernel.fixtures.oracles.common import canonical_json_bytes
from tests.agent_kernel.fixtures.oracles.source_ledger import SourceLedger

_PREFIXES = {
    "allowance_interval": "allowance-interval",
    "allowance_observation": "allowance-observation",
    "call": "call",
    "model_profile": "model-profile",
    "project": "project",
    "publication": "publication",
    "rate_card": "rate-card",
    "resource": "resource",
    "session": "session",
    "source_manifestation": "source-manifestation",
    "state_change": "state-change",
    "tool": "tool",
    "turn": "turn",
    "window": "window",
}
_IDENTITY_KINDS = dict(_PREFIXES)


def selector_sample(kind: str, ordinal: int = 0) -> str:
    """Return a deterministic selector for pure contract-only tests."""

    logical_id = semantic_id(
        _IDENTITY_KINDS[kind],
        ["selector-oracle", kind, ordinal],
    )
    return format_selector(kind, logical_id, _PREFIXES, _IDENTITY_KINDS)


def paginate_total_order(
    rows: list[dict[str, Any]],
    *,
    page_size: int,
) -> list[dict[str, Any]]:
    """Paginate a total order without gaps or duplicate rows."""

    if page_size <= 0:
        raise ValueError("page_size must be positive")
    pages: list[dict[str, Any]] = []
    for start in range(0, len(rows), page_size):
        selected_rows = rows[start : start + page_size]
        cursor = (
            canonical_json_bytes(selected_rows[-1]["order_key"])
            .decode("utf-8")
            .strip()
            if start + page_size < len(rows)
            else None
        )
        pages.append({"cursor": cursor, "rows": selected_rows})
    return pages


def build_evidence_oracle(
    profile: FixtureProfile,
    *,
    ledger: SourceLedger,
) -> dict[str, Any]:
    """Build evidence truth entirely from resolvable emitted coordinates."""

    selected = sorted(ledger.selector_coordinates.items())[:8]
    equal_time = profile.start_at_us
    rows: list[dict[str, Any]] = []
    for ordinal, (selector, coordinate) in enumerate(selected):
        logical_id = selector.partition(":")[2]
        rows.append(
            {
                "event_at_us": equal_time,
                "event_kind": "selector_anchor",
                "logical_id": logical_id,
                "occurrence_coordinate": coordinate,
                "order_key": [
                    0,
                    equal_time,
                    ordinal,
                    5,
                    logical_id,
                ],
                "selector": selector,
            }
        )
    rows.sort(key=lambda row: tuple(row["order_key"]))
    selectors_by_kind = {
        selector.partition(":")[0].replace("-", "_"): selector
        for selector in ledger.selector_coordinates
    }
    stable = selectors_by_kind["session"]
    return {
        "boundary_pairs": {
            "allowance_interval": [
                selectors_by_kind["allowance_observation"],
                selectors_by_kind["allowance_observation"],
            ],
            "delta": [
                selectors_by_kind["publication"],
                selectors_by_kind["publication"],
            ],
        },
        "equal_time_rows": rows,
        "raw_body_present": False,
        "selector_coordinates": dict(sorted(ledger.selector_coordinates.items())),
        "selector_rebuild": {
            "after": stable,
            "before": stable,
            "stable": True,
        },
        "selector_samples": selectors_by_kind,
    }
