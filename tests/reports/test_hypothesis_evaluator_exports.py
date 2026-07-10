from __future__ import annotations

from codex_usage_tracker.reports import api, hypothesis_evaluators


def test_report_api_uses_extracted_hypothesis_evaluator() -> None:
    assert api._evaluate_hypothesis_spec is hypothesis_evaluators.evaluate_hypothesis_spec
