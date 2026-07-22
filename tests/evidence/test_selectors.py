from __future__ import annotations

import pytest

from codex_usage_tracker.evidence.models import EvidenceRequest
from codex_usage_tracker.evidence.selectors import EvidenceSelector


@pytest.mark.parametrize(
    ("kind", "selector_id"),
    [
        ("finding", "finding-1"),
        ("call", "record-1"),
        ("thread", "thread:alpha"),
        ("allowance", "interval-1"),
        ("analysis", "compatibility.token_waste:generation:1"),
    ],
)
def test_selector_kinds_are_closed_and_ids_are_safe(kind: str, selector_id: str) -> None:
    selector = EvidenceSelector(kind, selector_id)  # type: ignore[arg-type]
    assert selector.kind == kind
    with pytest.raises(ValueError, match="selector_id"):
        EvidenceSelector(kind, "../private")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="selector_kind"):
        EvidenceSelector("raw", "fixture")  # type: ignore[arg-type]


def test_request_sections_and_bounds_are_allowlisted() -> None:
    assert EvidenceRequest("thread", "thread:alpha", section="calls").limit == 20
    with pytest.raises(ValueError, match="section"):
        EvidenceRequest("thread", "thread:alpha", section="trace")
    for limit in (0, 201):
        with pytest.raises(ValueError, match="limit"):
            EvidenceRequest("call", "record-1", limit=limit)
