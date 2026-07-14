"""Evidence model for observed Codex allowance changes."""

from __future__ import annotations

from collections import Counter
from statistics import median
from typing import Any

from codex_usage_tracker.allowance_intelligence.statistics import (
    _PUBLIC_CLAIM_MIN_SPLIT_SPANS,
    _PUBLIC_CLAIM_P_VALUE_THRESHOLD,
    _candidate_split_specs,
    _number,
    _rounded,
    _statistical_evidence,
)

WINDOW_KIND_CHOICES = ("weekly", "five_hour", "custom", "unknown")
EVIDENCE_GRADES = (
    "insufficient_data",
    "counter_noise_likely",
    "no_change_detected",
    "possible_regime_change",
    "strong_local_evidence",
    "inconclusive_other_usage_possible",
)

_CHANGE_RATIO_THRESHOLD = 0.75
_STRONG_CHANGE_RATIO_THRESHOLD = 0.67
_MIN_BASELINE_CHANGE_SPANS = 6
_MIN_RECENT_CHANGE_SPANS = 2
_MIN_CHANGE_SPANS = _MIN_BASELINE_CHANGE_SPANS + _MIN_RECENT_CHANGE_SPANS


def build_allowance_analysis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build aggregate allowance-change evidence from normalized observations."""

    observation_rows = _normalized_observations(rows)
    window_reports = _grouped_window_reports(observation_rows)
    spans = _flatten_window_rows(window_reports, "spans")
    candidates = _flatten_window_rows(window_reports, "change_candidates")
    primary = _primary_window_report(window_reports)
    return {
        "summary": _allowance_analysis_summary(
            observation_rows=observation_rows,
            window_reports=window_reports,
            spans=spans,
            candidates=candidates,
            primary=primary,
        ),
        "windows": window_reports,
        "spans": spans,
        "change_candidates": candidates,
        "notes": [
            "Weekly windows are treated as the primary signal for allowance-change claims.",
            "Five-hour windows are rolling counters and are downgraded unless supported by weekly evidence.",
            "Unexplained movement can mean allowance behavior changed, but it can also mean usage outside these local Codex logs.",
        ],
    }


def _normalized_observations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in sorted(rows, key=_observation_sort_key)
        if _number(row.get("used_percent")) is not None
    ]


def _grouped_window_reports(
    observation_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in observation_rows:
        grouped.setdefault(_analysis_key(row), []).append(row)
    return [_window_report(key, group_rows) for key, group_rows in sorted(grouped.items())]


def _flatten_window_rows(
    window_reports: list[dict[str, Any]],
    field: str,
) -> list[dict[str, Any]]:
    return [
        row for report in window_reports for row in report.get(field, []) if isinstance(row, dict)
    ]


def _allowance_analysis_summary(
    *,
    observation_rows: list[dict[str, Any]],
    window_reports: list[dict[str, Any]],
    spans: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    primary: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "observation_count": len(observation_rows),
        "window_report_count": len(window_reports),
        "positive_span_count": len(spans),
        "candidate_change_count": len(candidates),
        "primary_window_kind": primary.get("window_kind") if primary else None,
        "primary_evidence_grade": (
            primary.get("evidence_grade") if primary else "insufficient_data"
        ),
        "weekly_observation_count": _window_observation_count(
            observation_rows,
            "weekly",
        ),
        "five_hour_observation_count": _window_observation_count(
            observation_rows,
            "five_hour",
        ),
        "research_readiness": _research_readiness(window_reports, candidates),
    }


def _window_observation_count(
    observation_rows: list[dict[str, Any]],
    window_kind: str,
) -> int:
    return sum(1 for row in observation_rows if row.get("window_kind") == window_kind)


def _window_report(key: tuple[str, str, str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    window_kind, plan_type, limit_id = key
    spans, span_stats = _positive_spans(rows)
    candidate = _change_candidate(window_kind, spans)
    evidence_grade = _evidence_grade(
        window_kind=window_kind,
        observation_count=len(rows),
        span_count=len(spans),
        candidate=candidate,
    )
    return {
        "window_kind": window_kind,
        "plan_type": plan_type or None,
        "limit_id": limit_id or None,
        "observation_count": len(rows),
        "positive_span_count": len(spans),
        "evidence_grade": evidence_grade,
        "span_stats": span_stats,
        "change_candidates": [candidate] if candidate else [],
        "spans": spans,
    }


def _positive_spans(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    spans: list[dict[str, Any]] = []
    stats = {
        "baseline_rows": 0,
        "unchanged_rows": 0,
        "reset_or_negative_delta_rows": 0,
        "missing_used_percent_rows": 0,
    }
    previous: dict[str, Any] | None = None
    pending_rows: list[dict[str, Any]] = []

    for row in rows:
        used = _number(row.get("used_percent"))
        if used is None:
            stats["missing_used_percent_rows"] += 1
            continue
        if previous is None:
            previous = row
            pending_rows = []
            stats["baseline_rows"] += 1
            continue

        pending_rows.append(row)
        previous_used = _number(previous.get("used_percent"))
        if previous_used is None:
            previous = row
            pending_rows = []
            stats["missing_used_percent_rows"] += 1
            continue

        delta = used - previous_used
        if delta < 0:
            stats["reset_or_negative_delta_rows"] += 1
            previous = row
            pending_rows = []
            continue
        if delta == 0:
            stats["unchanged_rows"] += 1
            continue

        spans.append(_span(previous, row, pending_rows, delta))
        previous = row
        pending_rows = []

    return spans, stats


def _span(
    start: dict[str, Any],
    end: dict[str, Any],
    rows: list[dict[str, Any]],
    delta_usage_percent: float,
) -> dict[str, Any]:
    estimated_credits = _sum_number(rows, "usage_credits")
    credits_per_percent = (
        estimated_credits / delta_usage_percent if delta_usage_percent > 0 else None
    )
    return {
        "window_kind": end.get("window_kind"),
        "plan_type": end.get("plan_type"),
        "limit_id": end.get("limit_id"),
        "start_observed_at": start.get("event_timestamp"),
        "end_observed_at": end.get("event_timestamp"),
        "start_used_percent": _rounded(_number(start.get("used_percent"))),
        "end_used_percent": _rounded(_number(end.get("used_percent"))),
        "delta_usage_percent": _rounded(delta_usage_percent),
        "estimated_usage_credits": _rounded(estimated_credits),
        "credits_per_percent": _rounded(credits_per_percent),
        "row_count": len(rows),
        "credit_confidence_mix": dict(Counter(_credit_confidence(row) for row in rows)),
        "record_id": end.get("record_id"),
    }


def _change_candidate(window_kind: str, spans: list[dict[str, Any]]) -> dict[str, Any] | None:
    if window_kind != "weekly" or len(spans) < _MIN_CHANGE_SPANS:
        return None

    exact, deferred = _candidate_split_specs(
        spans,
        min_baseline_spans=_MIN_BASELINE_CHANGE_SPANS,
        min_recent_spans=_MIN_RECENT_CHANGE_SPANS,
        ratio_threshold=_CHANGE_RATIO_THRESHOLD,
    )
    best: dict[str, Any] | None = None
    specs = exact if deferred is None else [*exact, deferred]
    for split, previous_median, recent_median, ratio in specs:
        candidate = _candidate_payload(
            previous=spans[:split],
            recent=spans[split:],
            split_index=split,
            previous_median=previous_median,
            recent_median=recent_median,
            ratio=ratio,
        )
        if best is None or _candidate_score(candidate) < _candidate_score(best):
            best = candidate
    return best


def _candidate_score(candidate: dict[str, Any]) -> tuple[int, float, float, int, int]:
    statistical_evidence = candidate.get("statistical_evidence") or {}
    p_value = _number(statistical_evidence.get("p_value_one_sided"))
    capacity_ratio = _number(candidate.get("capacity_ratio"))
    previous_count = int(candidate.get("previous_span_count") or 0)
    recent_count = int(candidate.get("recent_span_count") or 0)
    return (
        0 if candidate.get("evidence_grade") == "strong_local_evidence" else 1,
        p_value if p_value is not None else float("inf"),
        capacity_ratio if capacity_ratio is not None else float("inf"),
        -min(previous_count, recent_count),
        abs(previous_count - recent_count),
    )


def _candidate_payload(
    *,
    previous: list[dict[str, Any]],
    recent: list[dict[str, Any]],
    split_index: int,
    previous_median: float,
    recent_median: float,
    ratio: float,
) -> dict[str, Any]:
    observed_recent_delta = _sum_number(recent, "delta_usage_percent")
    expected_recent_delta = (
        _sum_number(recent, "estimated_usage_credits") / previous_median if previous_median else 0.0
    )
    unexplained = max(observed_recent_delta - expected_recent_delta, 0.0)
    statistical_evidence = _statistical_evidence(previous, recent)
    return {
        "evidence_grade": _candidate_evidence_grade(
            recent=recent,
            ratio=ratio,
            statistical_evidence=statistical_evidence,
        ),
        "window_kind": "weekly",
        "candidate_start_observed_at": recent[0].get("start_observed_at"),
        "candidate_end_observed_at": recent[-1].get("end_observed_at"),
        "split_index": split_index,
        "previous_span_count": len(previous),
        "recent_span_count": len(recent),
        "previous_median_credits_per_percent": _rounded(previous_median),
        "recent_median_credits_per_percent": _rounded(recent_median),
        "capacity_ratio": _rounded(ratio),
        "observed_recent_delta_percent": _rounded(observed_recent_delta),
        "expected_recent_delta_percent_from_prior_baseline": _rounded(expected_recent_delta),
        "unexplained_usage_percent": _rounded(unexplained),
        "outside_usage_possible": unexplained >= max(1.0, observed_recent_delta * 0.5),
        "statistical_evidence": statistical_evidence,
    }


def _candidate_evidence_grade(
    *,
    recent: list[dict[str, Any]],
    ratio: float,
    statistical_evidence: dict[str, Any],
) -> str:
    effect_size = _number(statistical_evidence.get("effect_size_cliffs_delta"))
    p_value = _number(statistical_evidence.get("p_value_one_sided"))
    has_directional_stat = effect_size is not None and effect_size <= -0.8
    has_small_sample_signal = p_value is not None and p_value <= 0.2
    if (
        len(recent) >= 3
        and ratio <= _STRONG_CHANGE_RATIO_THRESHOLD
        and has_directional_stat
        and has_small_sample_signal
    ):
        return "strong_local_evidence"
    return "possible_regime_change"


def _evidence_grade(
    *,
    window_kind: str,
    observation_count: int,
    span_count: int,
    candidate: dict[str, Any] | None,
) -> str:
    if observation_count < 3 or span_count < 2:
        return "insufficient_data"
    if window_kind == "five_hour":
        return "counter_noise_likely"
    if candidate is None:
        return "no_change_detected"
    if candidate.get("outside_usage_possible") and span_count < 5:
        return "inconclusive_other_usage_possible"
    return str(candidate["evidence_grade"])


def _research_readiness(
    windows: list[dict[str, Any]], candidates: list[dict[str, Any]]
) -> dict[str, Any]:
    weekly_span_count = sum(
        int(window.get("positive_span_count") or 0)
        for window in windows
        if window.get("window_kind") == "weekly"
    )
    best_candidate = _best_candidate_for_public_claim(candidates)
    ready = bool(best_candidate and _candidate_public_claim_ready(best_candidate))
    reasons = _research_readiness_reasons(
        weekly_span_count=weekly_span_count,
        best_candidate=best_candidate,
        ready=ready,
    )
    return {
        "detector_version": "nonparametric-v1",
        "ready_for_public_claim": ready,
        "weekly_positive_span_count": weekly_span_count,
        "minimum_split_spans_for_public_claim": _PUBLIC_CLAIM_MIN_SPLIT_SPANS,
        "p_value_threshold_for_public_claim": _PUBLIC_CLAIM_P_VALUE_THRESHOLD,
        "best_candidate_capacity_ratio": (
            best_candidate.get("capacity_ratio") if best_candidate else None
        ),
        "reasons": reasons,
    }


def _best_candidate_for_public_claim(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    weekly_candidates = [
        candidate for candidate in candidates if candidate.get("window_kind") == "weekly"
    ]
    if not weekly_candidates:
        return None
    return min(weekly_candidates, key=_public_candidate_score)


def _public_candidate_score(candidate: dict[str, Any]) -> tuple[float, float]:
    evidence = candidate.get("statistical_evidence") or {}
    capacity_ratio = _number(candidate.get("capacity_ratio"))
    p_value = _number(evidence.get("p_value_one_sided"))
    return (
        capacity_ratio if capacity_ratio is not None else float("inf"),
        p_value if p_value is not None else float("inf"),
    )


def _candidate_public_claim_ready(candidate: dict[str, Any]) -> bool:
    evidence = candidate.get("statistical_evidence") or {}
    return evidence.get("public_claim_ready") is True


def _research_readiness_reasons(
    *,
    weekly_span_count: int,
    best_candidate: dict[str, Any] | None,
    ready: bool,
) -> list[str]:
    if best_candidate is None:
        return [
            "No weekly candidate shift was detected.",
            "Public allowance-change claims need repeated weekly spans before and after a candidate split.",
        ]
    evidence = best_candidate.get("statistical_evidence") or {}
    before_count = int(evidence.get("sample_size_before") or 0)
    after_count = int(evidence.get("sample_size_after") or 0)
    p_value = _number(evidence.get("p_value_one_sided"))
    rules = (
        (
            before_count < _PUBLIC_CLAIM_MIN_SPLIT_SPANS,
            "Too few weekly spans before the candidate split.",
        ),
        (
            after_count < _PUBLIC_CLAIM_MIN_SPLIT_SPANS,
            "Too few weekly spans after the candidate split.",
        ),
        (
            _p_value_not_ready(p_value),
            "Nonparametric p-value is not yet strong enough for a public claim.",
        ),
        (
            bool(best_candidate.get("outside_usage_possible")),
            "Observed movement could still reflect usage outside these local logs; disclose this caveat.",
        ),
    )
    reasons = [message for failed, message in rules if failed]
    if ready:
        reasons.insert(
            0,
            "Candidate has repeated weekly spans, strong effect size, and exact nonparametric support.",
        )
    if weekly_span_count < _PUBLIC_CLAIM_MIN_SPLIT_SPANS * 2:
        reasons.append("More weekly spans would improve stability of change-point estimates.")
    return reasons


def _p_value_not_ready(p_value: float | None) -> bool:
    return p_value is None or p_value > _PUBLIC_CLAIM_P_VALUE_THRESHOLD


def _primary_window_report(windows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not windows:
        return None
    weekly = [window for window in windows if window.get("window_kind") == "weekly"]
    if weekly:
        return max(weekly, key=lambda window: int(window.get("observation_count") or 0))
    return max(windows, key=lambda window: int(window.get("observation_count") or 0))


def _analysis_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("window_kind") or "unknown"),
        str(row.get("plan_type") or ""),
        str(row.get("limit_id") or ""),
    )


def _observation_sort_key(row: dict[str, Any]) -> tuple[str, int, str]:
    return (
        str(row.get("event_timestamp") or ""),
        int(_number(row.get("cumulative_total_tokens")) or 0),
        str(row.get("window_key") or ""),
    )


def _median_credits_per_percent(spans: list[dict[str, Any]]) -> float | None:
    values = [
        value
        for value in (_number(span.get("credits_per_percent")) for span in spans)
        if value is not None and value > 0
    ]
    return median(values) if values else None


def _sum_number(rows: list[dict[str, Any]], field: str) -> float:
    return sum(_number(row.get(field)) or 0.0 for row in rows)


def _credit_confidence(row: dict[str, Any]) -> str:
    value = row.get("usage_credit_confidence")
    return str(value) if value else "unpriced"
