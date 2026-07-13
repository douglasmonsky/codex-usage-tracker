from __future__ import annotations

from codex_usage_tracker.server.request_timing import server_timing_header


def test_server_timing_header_reports_only_bounded_duration() -> None:
    assert server_timing_header(started_at=10.0, finished_at=10.125) == "app;dur=125.000"
    assert server_timing_header(started_at=10.0, finished_at=9.0) == "app;dur=0.000"


def test_server_timing_header_is_absent_without_request_start() -> None:
    assert server_timing_header(started_at=None, finished_at=10.0) is None
