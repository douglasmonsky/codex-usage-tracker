from __future__ import annotations

import pytest

from codex_usage_tracker.kernel.evidence.contracts import (
    EvidenceRequest,
    EvidenceSelector,
    EvidenceView,
)


def test_logical_selectors_and_requests_are_bounded() -> None:
    selector = EvidenceSelector.parse("thread:logical-thread-1")

    assert selector.kind == "thread"
    assert selector.logical_id == "logical-thread-1"
    assert selector.value == "thread:logical-thread-1"
    assert EvidenceRequest(
        selector=selector,
        view=EvidenceView.TIMELINE,
        limit=25,
        live=True,
    ).normalized().live

    for invalid in ("", "row:1", "thread:", "thread:/Users/private"):
        with pytest.raises(ValueError):
            EvidenceSelector.parse(invalid)
    with pytest.raises(ValueError, match="limit"):
        EvidenceRequest(selector=selector, view="timeline", limit=501).normalized()
