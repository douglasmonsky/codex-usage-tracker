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

## Revision advancement assertion

Added a direct assertion that a canonical allowance update changes
`source_revision` as well as advancing `allowance_generation`; copied physical
row changes remain asserted stable.

## Reconciliation safety test hardening

### RED

Added end-to-end coverage for canonical reconciliation with a noncanonical
allowance observation and stale cycles, intervals, analysis snapshots, and
source state; copied physical allowance rows; savepoint rollback on a real
SQLite interval-insert trigger failure; and empty streamed-finalization source
replacement. The first run could not collect the Task 3 tests because importing
the materializer eagerly loaded allowance reports, which imported `store.api`
back during initialization.

### GREEN

Preserved the public allowance report exports with lazy package resolution,
breaking that import cycle without changing report callers. The tests prove
reconciliation deletes noncanonical/stale derived evidence without mutating
physical `usage_events`, `source_records`, or canonical/duplicate identity
fields; only canonical rows contribute allowance tokens/intervals; copied-row
changes leave source revision and generation stable; canonical allowance input
advances generation; failed interval writes roll back observations, all derived
rows, and source state; and an empty streamed source replacement materializes
cleanup exactly once.

Files changed:

- `src/codex_usage_tracker/allowance_intelligence/__init__.py`
- `tests/store/test_allowance_materialization.py`
- `tests/store/test_usage_deduplication.py`

Verification:

`PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/allowance_intelligence/test_cycles.py tests/store/test_allowance_materialization.py tests/store/test_usage_deduplication.py -q`

Result: `16 passed`.

`/Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m ruff check src/codex_usage_tracker/allowance_intelligence/__init__.py tests/store/test_allowance_materialization.py tests/store/test_usage_deduplication.py`

Result: `All checks passed!`.

`git diff --check` passed.

## Final boundary hardening

Added a RED/GREEN regression proving existing reset epochs are scoped by exact
archive/window/cohort identity, so nearby epochs from another scope cannot pin
cycle identity. GREEN: focused Task 3 suite passed (`11 passed`), Ruff passed,
and `git diff --check` passed.

## Self-review

Reviewed changed source and tests. Derived rows are sourced only from
`allowance_observations`, which are reconciled against `canonical_usage_events`;
physical usage, source records, and dedupe provenance are not mutated. Cycles
and intervals receive consistent archive scope, never span reset clusters, and
all cost/calibration/forecast/change fields remain disabled for this task.

## Review hardening RED/GREEN

RED additions covered stale-normal alternate selection (including constant-zero
and split-reset evidence), reuse of an existing reset epoch, and missing-reset
metadata censoring. The review also required empty streamed finalization and
savepoint rollback hardening; these are implemented in the materialization and
stream-finalization paths.

GREEN commands and results:

`PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/allowance_intelligence/test_cycles.py tests/store/test_allowance_materialization.py tests/store/test_usage_deduplication.py -q`

Result: `10 passed`.

`/Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m ruff check src/codex_usage_tracker/allowance_intelligence/contracts.py src/codex_usage_tracker/allowance_intelligence/cycles.py src/codex_usage_tracker/store/allowance_materialization.py src/codex_usage_tracker/store/api.py tests/allowance_intelligence/test_cycles.py tests/store/test_allowance_materialization.py`

Result: `All checks passed!`.

`git diff --check` passed.
