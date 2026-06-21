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
