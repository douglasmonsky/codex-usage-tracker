#!/usr/bin/env python3
"""Calibrate family-wise false positives for allowance capacity changes."""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from codex_usage_tracker.allowance_intelligence.change_detection import (
    MULTI_DETECTOR_VERSION,
    detect_cycle_changes,
)
from codex_usage_tracker.allowance_intelligence.statistics import _wilson_interval

_FAMILYWISE_ALPHA = 0.05
_CYCLE_COUNT = 24


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure null-history false positives for the allowance detector."
    )
    parser.add_argument("--simulations", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=20_260_715)
    parser.add_argument("--permutations", type=int, default=1_999)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.simulations < 1:
        parser.error("--simulations must be positive")
    if args.permutations < 99:
        parser.error("--permutations must be at least 99")

    generator = random.Random(args.seed)
    false_positives = 0
    family_counts: dict[str, int] = {}
    false_positives_by_family: dict[str, int] = {}
    for index in range(args.simulations):
        family, values = _null_history(generator, index)
        family_counts[family] = family_counts.get(family, 0) + 1
        result = detect_cycle_changes(
            _cycles(values),
            semantic_key=f"calibration:{args.seed}:{index}:{family}",
            permutation_count=args.permutations,
            familywise_alpha=_FAMILYWISE_ALPHA,
        )
        detected = bool(result["boundaries"])
        false_positives += detected
        false_positives_by_family.setdefault(family, 0)
        false_positives_by_family[family] += detected

    _, upper = _wilson_interval(false_positives, args.simulations)
    payload: dict[str, Any] = {
        "detector_version": MULTI_DETECTOR_VERSION,
        "simulations": args.simulations,
        "seed": args.seed,
        "permutations": args.permutations,
        "cycle_count": _CYCLE_COUNT,
        "familywise_alpha": _FAMILYWISE_ALPHA,
        "false_positive_count": false_positives,
        "false_positive_rate": round(false_positives / args.simulations, 6),
        "wilson_upper_95": round(upper, 6),
        "null_families": family_counts,
        "false_positives_by_family": false_positives_by_family,
        "passed": upper <= _FAMILYWISE_ALPHA,
    }
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(
            "Allowance change calibration: "
            f"{false_positives}/{args.simulations} false positives; "
            f"Wilson upper 95%={upper:.6f}; "
            f"{'PASS' if payload['passed'] else 'FAIL'}"
        )
    return 0 if payload["passed"] else 1


def _null_history(
    generator: random.Random, simulation_index: int
) -> tuple[str, list[float]]:
    family = simulation_index % 4
    if family == 0:
        return "gaussian", [generator.gauss(100.0, 12.0) for _ in range(_CYCLE_COUNT)]
    if family == 1:
        return "skewed", [
            80.0 + generator.expovariate(1 / 20.0) for _ in range(_CYCLE_COUNT)
        ]
    if family == 2:
        values = [generator.gauss(100.0, 8.0) for _ in range(_CYCLE_COUNT)]
        values[generator.randrange(_CYCLE_COUNT)] += generator.choice((-80.0, 120.0))
        return "outlier_contaminated", values
    return "heteroskedastic", [
        generator.gauss(100.0, 5.0 if index % 2 == 0 else 25.0)
        for index in range(_CYCLE_COUNT)
    ]


def _cycles(values: list[float]) -> list[dict[str, object]]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [
        {
            "cycle_id": f"cycle-{index:03d}",
            "last_observed_at": (start + timedelta(days=7 * index)).isoformat(),
            "credits_per_percent": max(0.001, value),
            "status": "completed",
            "quality_grade": "high",
            "price_coverage": 1.0,
            "conflict_count": 0,
        }
        for index, value in enumerate(values)
    ]


if __name__ == "__main__":
    raise SystemExit(main())
