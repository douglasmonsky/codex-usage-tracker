from codex_usage_tracker.allowance_intelligence.statistics import (
    _cliffs_delta,
    _exact_permutation_p_value,
    _statistical_evidence,
)


def test_exact_permutation_detects_lower_recent_capacity() -> None:
    p_value, method, combinations_evaluated = _exact_permutation_p_value(
        [4.0, 5.0],
        [1.0, 2.0],
    )

    assert p_value == 1 / 6
    assert method == "exact_permutation_mean_shift"
    assert combinations_evaluated == 6
    assert _cliffs_delta([4.0, 5.0], [1.0, 2.0]) == -1.0


def test_statistical_evidence_preserves_nonparametric_payload() -> None:
    evidence = _statistical_evidence(
        [{"credits_per_percent": value} for value in (7.0, 8.0, 9.0, 10.0)],
        [{"credits_per_percent": value} for value in (1.0, 2.0, 3.0, 4.0)],
    )

    assert evidence["detector_version"] == "nonparametric-v1"
    assert evidence["effect_size_cliffs_delta"] == -1.0
    assert evidence["effect_direction"] == "recent_lower_credits_per_percent"
    assert evidence["signal"] == "directionally_consistent_small_sample"
