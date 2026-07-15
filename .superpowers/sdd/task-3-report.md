# Task 3 report: reset-aware allowance cycles

## RED

Added focused tests for reset clustering, weekly reversal censoring, five-hour
rolling decreases, conflicts, alternate constant-zero cohort selection, archive
scope separation, canonical materialization, and idempotent source generation.
The first focused run failed on archive-scope cohort selection and fixture
construction; both failures were corrected within this task's scope.

## GREEN

Implemented immutable structural contracts and deterministic reset-aware cycle
derivation (`reset-aware-v2`). Reset epochs within 60 seconds coalesce by
median. Cohorts use injected `now`, favor active normal `codex`, keep
constant-zero alternates diagnostic, and prevent archive-scope boundaries from
joining. Materialization reads normalized canonical observations, removes stale
noncanonical observations, replaces derived rows transactionally, propagates
`is_archived`, and advances a stable hash revision/generation only when the
canonical allowance observation payload changes. Pricing-dependent fields stay
NULL/false; interpolation is limited to structurally valid weekly positive
intervals.

## Verification

`PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/allowance_intelligence/test_cycles.py tests/store/test_allowance_materialization.py tests/store/test_usage_deduplication.py -q`

Result: `8 passed`.

`git diff --check` passed.

## Self-review

Reviewed changed source and tests. Derived rows are sourced only from
`allowance_observations`, which are reconciled against `canonical_usage_events`;
physical usage, source records, and dedupe provenance are not mutated. Cycles
and intervals receive consistent archive scope, never span reset clusters, and
all cost/calibration/forecast/change fields remain disabled for this task.
