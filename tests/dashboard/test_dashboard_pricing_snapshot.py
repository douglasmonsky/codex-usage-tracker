from __future__ import annotations

from codex_usage_tracker.dashboard.pricing_snapshot import pricing_snapshot_warning


def test_pricing_snapshot_warning_handles_missing_or_unchanged_payloads() -> None:
    assert pricing_snapshot_warning(None, {"pricing_snapshot": {"fingerprint": "new"}}) is None
    assert (
        pricing_snapshot_warning(
            {"pricing_snapshot": {"fingerprint": "same"}},
            {"pricing_snapshot": {"fingerprint": "same"}},
        )
        is None
    )
    assert (
        pricing_snapshot_warning(
            {"pricing_snapshot": {}},
            {"pricing_snapshot": {"fingerprint": "new"}},
        )
        is None
    )


def test_pricing_snapshot_warning_prefers_timestamp_labels() -> None:
    warning = pricing_snapshot_warning(
        {"pricing_snapshot": {"fingerprint": "old", "pinned_at": "2026-06-01"}},
        {"pricing_snapshot": {"fingerprint": "new", "fetched_at": "2026-06-02"}},
    )

    assert warning == (
        "Pricing snapshot changed since the previous dashboard render: "
        "2026-06-01 -> 2026-06-02."
    )
