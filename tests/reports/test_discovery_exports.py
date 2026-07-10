from __future__ import annotations

from codex_usage_tracker.reports import api, discovery


def test_report_api_reexports_discovery_family() -> None:
    names = (
        "build_pricing_coverage_report",
        "build_source_coverage_report",
        "build_content_search_report",
        "build_thread_trace_report",
        "build_pattern_scan_report",
        "build_repeated_file_rediscovery_report",
        "build_shell_churn_report",
        "build_large_low_output_report",
    )

    assert all(getattr(api, name) is getattr(discovery, name) for name in names)
