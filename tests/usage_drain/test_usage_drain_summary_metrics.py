from __future__ import annotations

from codex_usage_tracker.usage_drain.summary_metrics import model_family_attribution


def test_model_family_attribution_tracks_validation_sequences() -> None:
    models = [
        {
            "name": "baseline__time_ordered",
            "validation": "time_ordered",
            "holdout": {"mae": 5.0, "r2": 0.1},
        },
        {
            "name": "tokens__time_ordered",
            "validation": "time_ordered",
            "holdout": {"mae": 3.0, "r2": 0.4},
        },
        {
            "name": "baseline__interleaved",
            "validation": "interleaved",
            "holdout": {"mae": 4.0, "r2": 0.2},
        },
    ]

    result = model_family_attribution(
        models,
        {
            "main": [
                ("baseline family", "baseline"),
                ("token family", "tokens"),
                ("missing family", "not_present"),
            ]
        },
    )

    time_ordered = result["sequences"]["main"]["time_ordered"]
    interleaved = result["sequences"]["main"]["interleaved"]
    assert result["metric_notes"]
    assert time_ordered == [
        {
            "family": "baseline family",
            "model": "baseline__time_ordered",
            "holdout_mae": 5.0,
            "holdout_r2": 0.1,
            "mae_improvement_vs_previous": None,
            "r2_delta_vs_previous": None,
        },
        {
            "family": "token family",
            "model": "tokens__time_ordered",
            "holdout_mae": 3.0,
            "holdout_r2": 0.4,
            "mae_improvement_vs_previous": 2.0,
            "r2_delta_vs_previous": 0.3,
        },
    ]
    assert interleaved == [
        {
            "family": "baseline family",
            "model": "baseline__interleaved",
            "holdout_mae": 4.0,
            "holdout_r2": 0.2,
            "mae_improvement_vs_previous": None,
            "r2_delta_vs_previous": None,
        }
    ]
