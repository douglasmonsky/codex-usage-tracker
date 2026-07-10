from __future__ import annotations

import pytest

from codex_usage_tracker.reports.hypothesis_classification import (
    classify_hypothesis_family,
    normalize_hypothesis_inputs,
)


@pytest.mark.parametrize(
    ("hypothesis", "expected"),
    [
        ("My weekly allowance changed", "allowance_change"),
        ("Cold resumes are expensive", "cache_failure"),
        ("The agent keeps rereading files", "repeated_file_rediscovery"),
        ("Repeated rg and sed commands dominate", "shell_churn"),
        ("High effort is overused", "effort_model_choice"),
        ("Large low-output calls waste tokens", "token_waste"),
    ],
)
def test_classify_hypothesis_family(hypothesis: str, expected: str) -> None:
    assert classify_hypothesis_family(hypothesis, "") == expected


def test_hypothesis_normalization_and_question_fallback() -> None:
    assert normalize_hypothesis_inputs([" first ", "", "second"]) == ["first", "second"]
    assert classify_hypothesis_family("unknown", "Check cache behavior") == "cache_failure"
