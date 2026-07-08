from __future__ import annotations

from codex_usage_tracker.reports.api import _classify_hypothesis_family


def test_hypothesis_family_routing_handles_exploratory_usage_phrases() -> None:
    question = (
        "Test newer MCP investigation hypotheses around repeated files, shell churn, "
        "local evidence, and allowance readiness."
    )

    assert (
        _classify_hypothesis_family(
            "Large low-output calls are the highest-leverage near-term cleanup target.",
            question,
        )
        == "token_waste"
    )
    assert (
        _classify_hypothesis_family(
            "Cache misses and cold resumes are inflating large calls.",
            question,
        )
        == "cache_failure"
    )
    assert (
        _classify_hypothesis_family(
            "The MCP needs local content-index or thread-trace follow-up to explain intent "
            "behind repeated reads.",
            question,
        )
        == "repeated_file_rediscovery"
    )
    assert (
        _classify_hypothesis_family(
            "Repeated file rediscovery is wasting tokens.",
            question,
        )
        == "repeated_file_rediscovery"
    )
    assert (
        _classify_hypothesis_family(
            "Allowance-change claims are not ready for public posting without more weekly positive spans.",
            question,
        )
        == "allowance_change"
    )
    assert (
        _classify_hypothesis_family(
            "High effort is driving a disproportionate share of usage.",
            question,
        )
        == "effort_model_choice"
    )
