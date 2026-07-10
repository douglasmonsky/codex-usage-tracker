from __future__ import annotations

from codex_usage_tracker.reports import api, query


def test_report_api_reexports_query_family() -> None:
    names = (
        "QUERY_CREDIT_CONFIDENCE_CHOICES",
        "QUERY_PRICING_STATUS_CHOICES",
        "build_query_report",
        "build_recommendations_report",
    )

    assert all(getattr(api, name) is getattr(query, name) for name in names)
