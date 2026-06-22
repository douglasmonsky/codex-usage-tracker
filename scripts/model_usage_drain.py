#!/usr/bin/env python3
"""Build a local aggregate-only usage-drain modeling report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from codex_usage_tracker.allowance import annotate_rows_with_allowance, load_allowance_config
from codex_usage_tracker.paths import DEFAULT_ALLOWANCE_PATH, DEFAULT_DB_PATH
from codex_usage_tracker.store import query_dashboard_events
from codex_usage_tracker.usage_drain_model import (
    build_usage_delta_spans,
    load_fast_proxy_annotations,
    summarize_usage_drain_model,
    write_usage_drain_spans_csv,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Model observed usage-drain deltas against aggregate token credits."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--allowance", type=Path, default=DEFAULT_ALLOWANCE_PATH)
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--model")
    parser.add_argument("--effort")
    parser.add_argument("--thread")
    parser.add_argument("--include-archived", action="store_true")
    parser.add_argument(
        "--fast-proxy-csv",
        type=Path,
        help="Optional CSV with record_id, fast_proxy_label, and timing_confidence columns.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/tmp/codex-usage-drain-model"),
    )
    parser.add_argument("--json", action="store_true", help="Print the summary JSON.")
    args = parser.parse_args()

    rows = query_dashboard_events(
        args.db,
        limit=0,
        since=args.since,
        until=args.until,
        model=args.model,
        effort=args.effort,
        thread=args.thread,
        include_archived=args.include_archived,
    )
    allowance = load_allowance_config(args.allowance)
    rows = annotate_rows_with_allowance(rows, allowance)
    annotations = load_fast_proxy_annotations(args.fast_proxy_csv)
    summary = summarize_usage_drain_model(rows, fast_proxy_annotations=annotations)
    spans, _stats = build_usage_delta_spans(rows, fast_proxy_annotations=annotations)

    output_dir = args.output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "usage_drain_model_summary.json"
    spans_path = output_dir / "usage_drain_spans.csv"
    summary["artifacts"] = {
        "summary_json": str(summary_path),
        "spans_csv": str(spans_path),
        "fast_proxy_csv": str(args.fast_proxy_csv) if args.fast_proxy_csv else None,
    }
    summary_path.write_text(json.dumps(_json_safe(summary), indent=2, sort_keys=True) + "\n")
    write_usage_drain_spans_csv(spans, spans_path)

    if args.json:
        print(json.dumps(_json_safe(summary), indent=2, sort_keys=True))
    else:
        print(f"Wrote {summary_path}")
        print(f"Wrote {spans_path}")
        span_stats = summary.get("span_stats") or {}
        print(
            "usage windows: five_hour_rows={five_hour} fallback_rows={fallback}".format(
                five_hour=span_stats.get("five_hour_usage_window_rows"),
                fallback=span_stats.get("fallback_usage_window_rows"),
            )
        )
        for result in summary["results"]:
            print(
                "{proxy}: spans={spans} candidate_spans={candidate_spans} "
                "implied={implied_candidate_multiplier} best_grid={best_grid_multiplier_by_r2} "
                "documented={documented_weighted_candidate_multiplier} r2={two_feature_r2}".format(
                    **result
                )
            )
        predictive = summary.get("predictive_modeling") or {}
        if predictive.get("models"):
            print(
                "predictive: best_r2={best_r2} best_mae={best_mae}".format(
                    best_r2=predictive.get("best_by_holdout_r2"),
                    best_mae=predictive.get("best_by_holdout_mae"),
                )
            )
            for result in predictive["models"]:
                holdout = result.get("holdout") or {}
                print(
                    "  {name}: r2={r2} mae={mae} pearson={pearson}".format(
                        name=result.get("name"),
                        r2=holdout.get("r2"),
                        mae=holdout.get("mae"),
                        pearson=holdout.get("pearson"),
                    )
                )
            attribution = predictive.get("feature_family_attribution") or {}
            _print_feature_attribution(
                "predictive cost/time",
                attribution,
                sequence_name="cost_and_time_controls",
                validation="interleaved_every_5th",
            )
            _print_feature_attribution(
                "predictive history",
                attribution,
                sequence_name="history_regime_controls",
                validation="interleaved_every_5th",
            )
        walk_forward = summary.get("walk_forward_prediction") or {}
        scopes = walk_forward.get("scopes") or {}
        if scopes:
            for scope_name in (
                "all_after_first",
                "time_ordered_holdout_20",
                "latest_100",
            ):
                scope = scopes.get(scope_name) or {}
                actual = scope.get("actual") or {}
                models = scope.get("models") or {}
                best_mae = _best_metric_model(models, "mae")
                best_rmse = _best_metric_model(models, "rmse")
                print(
                    "walk-forward {scope}: n={n} best_mae={best_mae} "
                    "best_rmse={best_rmse}".format(
                        scope=scope_name,
                        n=actual.get("n"),
                        best_mae=best_mae,
                        best_rmse=best_rmse,
                    )
                )
                state_models = {
                    name: values
                    for name, values in models.items()
                    if name.startswith("empirical_")
                }
                best_state = _best_metric_model(state_models, "mae")
                if best_state:
                    best_state_name = best_state.split(":", 1)[0]
                    diagnostics = (scope.get("state_bucket_diagnostics") or {}).get(
                        best_state_name
                    ) or {}
                    print(
                        "walk-forward state-bucket {scope}: best_mae={best_mae} "
                        "matched={matched} support={support}".format(
                            scope=scope_name,
                            best_mae=best_state,
                            matched=diagnostics.get("matched_state_share"),
                            support=diagnostics.get("mean_support"),
                        )
                    )
                transition_scope = (
                    ((walk_forward.get("transition_risk") or {}).get("scopes") or {})
                    .get(scope_name)
                    or {}
                )
                transition_target = transition_scope.get("non_one_percent_delta") or {}
                transition_models = transition_target.get("models") or {}
                best_transition = _best_metric_model(transition_models, "brier")
                if best_transition:
                    print(
                        "transition-risk {scope}: positives={positive_rate} "
                        "best_brier={best_brier}".format(
                            scope=scope_name,
                            positive_rate=transition_target.get("positive_rate"),
                            best_brier=best_transition,
                        )
                    )
        segments = summary.get("piecewise_regime_segments") or {}
        latest_segment = segments.get("latest_segment") or {}
        longest_segments = segments.get("longest_segments") or []
        if latest_segment:
            print(
                "regime segments: count={count} latest={latest_label}:{latest_count} "
                "best={latest_best}".format(
                    count=segments.get("segment_count"),
                    latest_label=latest_segment.get("label"),
                    latest_count=latest_segment.get("span_count"),
                    latest_best=latest_segment.get("best_by_mae"),
                )
            )
        if longest_segments:
            longest = longest_segments[0]
            print(
                "longest regime segment: {label}:{count} {start}->{end} best={best}".format(
                    label=longest.get("label"),
                    count=longest.get("span_count"),
                    start=longest.get("start_date"),
                    end=longest.get("end_date"),
                    best=longest.get("best_by_mae"),
                )
            )
        adaptation = (
            (segments.get("adaptation_by_position") or {}).get("all_segments") or {}
        )
        if adaptation:
            first = adaptation.get("first_span") or {}
            second = adaptation.get("second_span") or {}
            sixth = adaptation.get("sixth_plus_span") or {}
            print(
                "regime adaptation: first={first} second={second} sixth_plus={sixth}".format(
                    first=first.get("best_by_mae"),
                    second=second.get("best_by_mae"),
                    sixth=sixth.get("best_by_mae"),
                )
            )
        boundary = segments.get("boundary_diagnostics") or {}
        if boundary:
            long_one_percent = boundary.get("after_long_one_percent_run") or {}
            position_rows = (
                (boundary.get("by_context") or {}).get(
                    "previous_segment_position_bucket"
                )
                or []
            )
            position_rates = {
                row.get("previous_segment_position_bucket"): row.get("boundary_rate")
                for row in position_rows
                if isinstance(row, dict)
            }
            print(
                "regime boundaries: count={count} rate={rate} "
                "after_long_1pct_rate={long_rate}".format(
                    count=boundary.get("boundary_count"),
                    rate=boundary.get("boundary_rate"),
                    long_rate=long_one_percent.get("boundary_rate"),
                )
            )
            print(
                "boundary hazard: first={first} second={second} sixth_plus={sixth}".format(
                    first=position_rates.get("first_span"),
                    second=position_rates.get("second_span"),
                    sixth=position_rates.get("sixth_plus_span"),
                )
            )
        components = summary.get("token_component_regression") or {}
        variants = components.get("variants") or {}
        for variant_name in ("unweighted", "high_medium_fast_weighted"):
            variant = variants.get(variant_name) or {}
            visible = (
                (variant.get("visible_drain") or {})
                .get("with_intercept", {})
                .get("all", {})
            )
            credits = (
                (variant.get("credit_accounting") or {})
                .get("no_intercept", {})
                .get("all", {})
            )
            if visible or credits:
                print(
                    "component {variant}: visible_r2={visible_r2} "
                    "credit_r2={credit_r2} candidate_rows={candidate_rows}".format(
                        variant=variant_name,
                        visible_r2=visible.get("r2"),
                        credit_r2=credits.get("r2"),
                        candidate_rows=variant.get("candidate_rows"),
                    )
                )
        capacity = summary.get("one_percent_capacity_modeling") or {}
        if capacity.get("models"):
            print(
                "one-percent capacity: spans={spans} best_mae={best_mae} "
                "best_causal_mae={best_causal}".format(
                    spans=capacity.get("span_count"),
                    best_mae=capacity.get("best_by_holdout_mae"),
                    best_causal=capacity.get("best_causal_by_holdout_mae"),
                )
            )
            capacity_models = {
                str(model.get("name")): model
                for model in capacity.get("models", [])
                if isinstance(model, dict)
            }
            for model_name in (
                "capacity_rolling3__interleaved_every_5th",
                "capacity_history_state_buckets__interleaved_every_5th",
                "capacity_history_state_interactions__interleaved_every_5th",
                "capacity_history_state_interactions_ridge100__interleaved_every_5th",
                "capacity_same_span_shape_buckets__interleaved_every_5th",
                "capacity_same_span_shape_interactions__interleaved_every_5th",
                "capacity_same_span_shape_interactions_ridge30__interleaved_every_5th",
                "capacity_same_span_tokens__interleaved_every_5th",
            ):
                model = capacity_models.get(model_name) or {}
                holdout = model.get("holdout") or {}
                if holdout:
                    diagnostics = model.get("holdout_error_diagnostics") or {}
                    print(
                        "  {name}: r2={r2} mae={mae} within10={within10} "
                        "large={large}".format(
                            name=model_name,
                            r2=holdout.get("r2"),
                            mae=holdout.get("mae"),
                            within10=diagnostics.get("within_10_credits_share"),
                            large=diagnostics.get("large_error_share"),
                        )
                    )
            capacity_attribution = capacity.get("feature_family_attribution") or {}
            _print_feature_attribution(
                "capacity causal",
                capacity_attribution,
                sequence_name="causal_capacity_controls",
                validation="interleaved_every_5th",
            )
            _print_feature_attribution(
                "capacity same-span",
                capacity_attribution,
                sequence_name="same_span_capacity_controls",
                validation="interleaved_every_5th",
            )
            capacity_components = (
                (capacity.get("token_component_regression") or {}).get("variants") or {}
            )
            for variant_name in ("unweighted", "high_medium_fast_weighted"):
                variant = capacity_components.get(variant_name) or {}
                credits = (
                    (variant.get("capacity_credits") or {})
                    .get("no_intercept", {})
                    .get("all", {})
                )
                if credits:
                    print(
                        "one-percent component {variant}: credit_r2={credit_r2} "
                        "mae={mae} candidate_rows={candidate_rows}".format(
                            variant=variant_name,
                            credit_r2=credits.get("r2"),
                            mae=credits.get("mae"),
                            candidate_rows=variant.get("candidate_rows"),
                        )
                    )
    return 0


def _print_feature_attribution(
    label: str,
    attribution: dict[str, Any],
    *,
    sequence_name: str,
    validation: str,
) -> None:
    rows = (
        ((attribution.get("sequences") or {}).get(sequence_name) or {}).get(
            validation
        )
        or []
    )
    improvements = [
        row
        for row in rows
        if row.get("mae_improvement_vs_previous") is not None
    ]
    if not improvements:
        return
    improvements.sort(
        key=lambda row: float(row.get("mae_improvement_vs_previous") or 0.0),
        reverse=True,
    )
    top = ", ".join(
        "{family}:{delta}".format(
            family=row.get("family"),
            delta=row.get("mae_improvement_vs_previous"),
        )
        for row in improvements[:4]
    )
    print(f"{label} attribution {validation}: {top}")


def _best_metric_model(models: dict[str, Any], metric: str) -> str | None:
    candidates = [
        (name, values.get(metric))
        for name, values in models.items()
        if isinstance(values, dict) and values.get(metric) is not None
    ]
    if not candidates:
        return None
    name, value = min(candidates, key=lambda item: float(item[1]))
    return f"{name}:{value}"


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
