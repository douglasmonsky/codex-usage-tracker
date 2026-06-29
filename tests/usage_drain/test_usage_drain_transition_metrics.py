from codex_usage_tracker.usage_drain.transition_metrics import binary_risk_metrics


def test_binary_risk_metrics_preserves_summary_contract() -> None:
    metrics = binary_risk_metrics([1, 0, 1, 0], [0.9, 0.8, 0.4, 0.1])

    assert metrics == {
        "n": 4,
        "brier": 0.255,
        "auc": 0.75,
        "average_precision": 0.833333,
        "precision_at_top_10pct": 1.0,
        "recall_at_top_10pct": 0.5,
        "top_10pct_positive_rate": 1.0,
        "mean_score_positive": 0.65,
        "mean_score_negative": 0.45,
    }


def test_binary_risk_metrics_handles_empty_or_misaligned_inputs() -> None:
    expected_empty = {
        "n": 0,
        "brier": None,
        "auc": None,
        "average_precision": None,
        "precision_at_top_10pct": None,
        "recall_at_top_10pct": None,
        "top_10pct_positive_rate": None,
        "mean_score_positive": None,
        "mean_score_negative": None,
    }

    assert binary_risk_metrics([], []) == expected_empty
    assert binary_risk_metrics([1], []) == {**expected_empty, "n": 1}
