from codex_usage_tracker.usage_drain_reports import _prediction_model_record


def test_prediction_model_record_reports_compact_metrics() -> None:
    assert _prediction_model_record(
        "demo",
        [1.0, 2.0, 3.0],
        [1.0, 4.0, 3.0],
    ) == {
        "name": "demo",
        "kind": "compact_dashboard_baseline",
        "validation": "same_series_compact",
        "mae": 0.666667,
        "rmse": 1.154701,
        "r2": -1.0,
        "pearson": 0.654654,
        "within_1pt": 0.666667,
        "within_5pts": 1.0,
    }


def test_prediction_model_record_handles_empty_series() -> None:
    assert _prediction_model_record("empty", [], []) == {
        "name": "empty",
        "kind": "compact_dashboard_baseline",
        "validation": "same_series_compact",
        "mae": None,
        "rmse": None,
        "r2": None,
        "pearson": None,
        "within_1pt": None,
        "within_5pts": None,
    }
