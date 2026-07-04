from __future__ import annotations

from codex_usage_tracker.usage_drain.thread_curves import thread_cost_curves


def test_thread_cost_curves_sort_and_sample_aggregate_costs() -> None:
    rows = [
        _row("thread-b", "Thread B", "2026-06-02T00:00:00Z", 5.0, 200),
        _row("thread-a", "Thread A", "2026-06-01T00:00:00Z", 1.0, 100),
        _row("thread-a", "Thread A", "2026-06-03T00:00:00Z", 2.0, 300),
        _row("thread-b", "Thread B", "2026-06-04T00:00:00Z", 5.0, 400),
    ]

    curves = thread_cost_curves(rows, max_threads=2, max_curve_points=1)

    assert curves["total_threads"] == 2
    assert curves["shown_threads"] == 2
    assert curves["estimated_cost_usd"] == 13.0
    assert curves["top_thread_share"] == round(10.0 / 13.0, 6)
    assert [row["thread"] for row in curves["threads"]] == ["Thread B", "Thread A"]
    assert curves["threads"][0]["points"] == [{"call_index": 1, "cumulative_cost_usd": 5.0}]
    assert curves["threads"][0]["largest_record_id"] == "thread-b-400"
    assert curves["threads"][0]["representative_record_id"] == "thread-b-400"
    assert curves["threads"][0]["largest_call_tokens"] == 400
    assert curves["threads"][0]["largest_call_cost_usd"] == 5.0
    assert curves["threads"][1]["estimated_cost_usd"] == 3.0


def _row(
    thread_key: str,
    thread_name: str,
    timestamp: str,
    estimated_cost: float,
    total_tokens: int,
) -> dict[str, object]:
    return {
        "thread_key": thread_key,
        "thread_name": thread_name,
        "event_timestamp": timestamp,
        "record_id": f"{thread_key}-{total_tokens}",
        "estimated_cost_usd": estimated_cost,
        "total_tokens": total_tokens,
        "cumulative_total_tokens": total_tokens,
    }
