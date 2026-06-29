from __future__ import annotations

from codex_usage_tracker.usage_drain_boundary_delta_summary import (
    _boundary_delta_top_error_groups,
)


def test_boundary_delta_top_error_groups_summarizes_error_concentration() -> None:
    errors = [
        {
            "error": 4.0,
            "abs_error": 4.0,
            "actual": 6.0,
            "predicted": 2.0,
            "metadata": {"transition": "same_to_boundary", "is_boundary": True},
        },
        {
            "error": 2.0,
            "abs_error": 2.0,
            "actual": 5.0,
            "predicted": 3.0,
            "metadata": {"transition": "same_to_boundary", "is_boundary": True},
        },
        {
            "error": 1.0,
            "abs_error": 1.0,
            "actual": 2.0,
            "predicted": 1.0,
            "metadata": {"transition": "stable", "is_boundary": False},
        },
    ]

    result = _boundary_delta_top_error_groups(errors, "transition")

    assert result == [
        {
            "transition": "same_to_boundary",
            "count": 2,
            "count_share": 0.666667,
            "share_abs_error": 0.857143,
            "mean_abs_error": 3.0,
            "rmse": 3.162278,
            "max_abs_error": 4.0,
            "mean_actual": 5.5,
            "mean_predicted": 2.5,
        },
        {
            "transition": "stable",
            "count": 1,
            "count_share": 0.333333,
            "share_abs_error": 0.142857,
            "mean_abs_error": 1.0,
            "rmse": 1.0,
            "max_abs_error": 1.0,
            "mean_actual": 2.0,
            "mean_predicted": 1.0,
        },
    ]


def test_boundary_delta_top_error_groups_maps_boundary_state() -> None:
    errors = [
        {
            "error": 2.0,
            "abs_error": 2.0,
            "actual": 3.0,
            "predicted": 1.0,
            "metadata": {"is_boundary": True},
        },
        {
            "error": 1.0,
            "abs_error": 1.0,
            "actual": 1.0,
            "predicted": 0.0,
            "metadata": {"is_boundary": False},
        },
    ]

    result = _boundary_delta_top_error_groups(errors, "boundary_state")

    assert [row["boundary_state"] for row in result] == ["boundary", "same_label"]
