from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from codex_usage_tracker.application.query import query_usage
from codex_usage_tracker.application.query_models import QueryFilters, QueryRequest
from codex_usage_tracker.application.query_validation import QueryValidationError
from codex_usage_tracker.store.api import connect, query_canonical_usage_v2, upsert_usage_events
from tests.store_dashboard_helpers import _usage_event


def _seed(db_path: Path) -> None:
    events = [
        _usage_event(
            record_id=f"call-{index}",
            session_id=f"session-{index}",
            thread_key=f"thread:{'alpha' if index < 2 else 'beta'}",
            event_timestamp=f"2026-07-{20 + index}T12:00:00Z",
            cumulative_total_tokens=110 * (index + 1),
        )
        for index in range(4)
    ]
    events[1] = replace(events[1], is_duplicate=1, canonical_record_id="call-0")
    events[2] = replace(events[2], is_archived=1, agent_role="explorer", subagent_type="delegate")
    events[3] = replace(events[3], model="unpriced-model")
    upsert_usage_events(events, db_path)
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE usage_events SET is_duplicate=1, canonical_record_id='call-0' "
            "WHERE record_id='call-1'"
        )


def test_query_uses_canonical_rows_and_explicit_history(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _seed(db_path)

    active = query_usage(
        QueryRequest(entity="thread", measures=("tokens", "call_count"), filters=QueryFilters()),
        db_path=db_path,
    )
    all_history = query_usage(
        QueryRequest(
            entity="thread",
            measures=("tokens", "call_count"),
            filters=QueryFilters(),
            history="all",
        ),
        db_path=db_path,
    )

    assert sum(row["call_count"] for row in active.rows) == 2
    assert sum(row["call_count"] for row in all_history.rows) == 3


@pytest.mark.parametrize("order", ["asc", "desc"])
def test_query_has_stable_keyset_pagination_and_no_matches(tmp_path: Path, order: str) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _seed(db_path)
    request = QueryRequest(
        entity="call",
        measures=("tokens",),
        filters=QueryFilters(),
        order_by="tokens",
        order=order,  # type: ignore[arg-type]
        limit=1,
    )

    record_ids: list[str] = []
    cursor = None
    while True:
        page = query_usage(replace(request, cursor=cursor), db_path=db_path)
        record_ids.extend(str(row["record_id"]) for row in page.rows)
        cursor = page.next_cursor
        if cursor is None:
            break
    empty = query_usage(
        QueryRequest(entity="model", measures=("tokens",), filters=QueryFilters(model="missing")),
        db_path=db_path,
    )

    assert record_ids == ["call-0", "call-3"]
    assert empty.rows == ()
    assert empty.next_cursor is None


def test_query_rejects_scope_mismatched_and_stale_cursors(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _seed(db_path)
    request = QueryRequest(entity="call", measures=("tokens",), filters=QueryFilters(), limit=1)
    first = query_usage(request, db_path=db_path)
    assert first.next_cursor is not None

    with pytest.raises(QueryValidationError, match="scope"):
        query_usage(
            replace(
                request,
                filters=QueryFilters(model="gpt-5.5"),
                cursor=first.next_cursor,
            ),
            db_path=db_path,
        )

    upsert_usage_events(
        [
            _usage_event(
                record_id="call-new",
                session_id="session-new",
                thread_key="thread:new",
                event_timestamp="2026-07-25T12:00:00Z",
                cumulative_total_tokens=999,
            )
        ],
        db_path,
    )
    with pytest.raises(QueryValidationError, match="stale"):
        query_usage(replace(request, cursor=first.next_cursor), db_path=db_path)


def test_subagent_grouping_and_unpriced_estimates_remain_unknown(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _seed(db_path)

    subagents = query_usage(
        QueryRequest(
            entity="subagent",
            measures=("tokens",),
            filters=QueryFilters(),
            history="all",
        ),
        db_path=db_path,
    )
    unpriced = query_usage(
        QueryRequest(
            entity="model",
            measures=("estimated_cost", "estimated_credits"),
            filters=QueryFilters(model="unpriced-model"),
        ),
        db_path=db_path,
    )

    assert [row["subagent"] for row in subagents.rows] == ["explorer"]
    assert unpriced.rows[0]["estimated_cost"] is None
    assert unpriced.rows[0]["estimated_cost_coverage"] == 0.0
    assert unpriced.rows[0]["estimated_credits"] is None


def test_query_supports_subagent_grouping_dimension(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _seed(db_path)

    result = query_usage(
        QueryRequest(
            entity="thread",
            measures=("call_count",),
            filters=QueryFilters(),
            group_by=("subagent",),
            history="all",
        ),
        db_path=db_path,
    )

    assert {row["subagent"] for row in result.rows} == {"explorer", "not-subagent"}


def test_query_prices_known_models_and_preserves_coverage(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(
        '{"models":{"gpt-5.5":{"input_per_million":1,'
        '"cached_input_per_million":0.1,"output_per_million":2}}}',
        encoding="utf-8",
    )
    _seed(db_path)

    result = query_usage(
        QueryRequest(
            entity="model",
            measures=("estimated_cost", "estimated_credits"),
            filters=QueryFilters(model="gpt-5.5"),
        ),
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=tmp_path / "allowance.json",
    )

    assert result.rows[0]["estimated_cost"] is not None
    assert result.rows[0]["estimated_cost_coverage"] == 1.0
    assert result.rows[0]["estimated_cost_confidence"] == "exact"
    assert result.rows[0]["estimated_credits"] is not None
    assert result.rows[0]["estimated_credits_coverage"] == 1.0
    assert result.rows[0]["estimated_credits_confidence"] == "exact"


def test_store_adapter_rejects_raw_identifiers(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="order_by"):
        query_canonical_usage_v2(
            db_path=tmp_path / "usage.sqlite3",
            entity="call",
            measures=("tokens",),
            filters={},
            group_by=(),
            order_by="tokens DESC; SELECT 1",
            order="desc",
            include_archived=False,
            limit=20,
            cursor_sort=None,
            cursor_identity=None,
        )
