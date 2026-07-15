# Task 6 report

## RED

Command:

```bash
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/allowance_intelligence/test_estimation.py tests/allowance_intelligence/test_allowance_intelligence.py tests/allowance_intelligence/test_service.py -q
```

Result: failed during collection with `ModuleNotFoundError: No module named 'codex_usage_tracker.allowance_intelligence.estimation'`, proving the expected missing behavior before production edits.

## GREEN

Command:

```bash
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/allowance_intelligence/test_estimation.py tests/allowance_intelligence/test_allowance_intelligence.py tests/allowance_intelligence/test_service.py -q
```

Result: `28 passed in 0.45s`.

Additional check:

```bash
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m py_compile src/codex_usage_tracker/allowance_intelligence/estimation.py src/codex_usage_tracker/allowance_intelligence/model.py src/codex_usage_tracker/allowance_intelligence/service.py
git diff --check
```

Result: passed.

## Changed files

- `src/codex_usage_tracker/allowance_intelligence/estimation.py`
- `src/codex_usage_tracker/allowance_intelligence/model.py`
- `src/codex_usage_tracker/allowance_intelligence/service.py`
- `tests/allowance_intelligence/test_estimation.py`
- `tests/allowance_intelligence/test_service.py`

## Self-review

- The reconstruction is ordered by observation time and filters rows after injected `now`; each interval uses capacity from completed earlier cycles only.
- Cycle contributions are represented once, with a maximum normalized cycle weight of one.
- Missing pricing remains a coverage gap and cannot generate a numeric estimate.
- Five-hour data is excluded from this weekly estimator; observed status fields remain unchanged.
- Endpoint mismatch is retained as signed `anchor_correction`; it is not redistributed into historical points.

## Concerns

- Sparse history remains descriptive/observed-only by design. The sufficient-history synthetic fixture exercises calculated pace scenarios, residual quantiles, MAE/RMSE, 50/80/95 coverage, all four baseline comparisons, and the validated gate.

## Walk-forward correctness completion

### RED

Added numeric tests for a latest accepted observation at 40% with one covered
100-credit interval after it and a 10-credit/% capacity (expected 50%), and a
five-cycle sequence whose final 90% observation is a later holdout.  Before
the implementation change, the first produced 60% by reusing pre-observation
credits and the latter lacked a holdout payload entirely.  The focused test
run failed with those two assertions.

### GREEN

```bash
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/allowance_intelligence/test_estimation.py tests/allowance_intelligence/test_allowance_intelligence.py tests/allowance_intelligence/test_service.py -q
```

Result: `32 passed`.

Ruff passed for the touched production/test files and `git diff --check`
passed.

### Changed files

- `src/codex_usage_tracker/allowance_intelligence/estimation.py`
- `tests/allowance_intelligence/test_estimation.py`
- `.superpowers/sdd/task-6-report.md`

### Self-review

- Capacity is calculated per completed, accepted, quality-approved cycle; the
  total ratio is true selected-credit / selected-percent movement, while the
  robust median gives every cycle one vote.
- Each reconstruction selects only cycles completed before its endpoint.  The
  later holdout gets residual quantiles and 50/80/95 coverage calculated only
  from its earlier training residuals.
- Promotion requires a later holdout, three earlier residuals, coverage at all
  advertised levels, and a strict win over four separately computed numeric
  baselines.
- The live estimate starts at the newest accepted observation and adds only
  covered canonical interval credits with strictly later endpoints; it reports
  the source timestamp, credit sum, and 0--100 clipping. A missing-price later
  interval keeps the result observed-only rather than silently treating it as
  zero usage.
- Conditional pace reports all four requested windows, their sample count,
  robust median center, and combined residual/spread bounds. Five-hour rows
  never enter this weekly-only engine.

### Concerns

- The deliberately strict promotion gate leaves short or tied synthetic
  histories descriptive. This is intentional: a tied baseline is not evidence
  of a superior forecast.

## Correctness fix wave RED/GREEN

RED command:

```bash
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/allowance_intelligence/test_estimation.py -q
```

Result: failed: an explicitly open cycle was counted as completed calibration evidence and completed-cycle test expectations failed.

GREEN command:

```bash
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/allowance_intelligence/test_estimation.py tests/allowance_intelligence/test_allowance_intelligence.py tests/allowance_intelligence/test_service.py -q
```

Result: `29 passed in 0.47s` before formatting-only cleanup.

The fix requires explicit `status == "completed"` plus quality approval before a cycle may enter calibration. Dense/open cycles cannot influence the cycle-capped completed capacity summary.

## Direct completion and production-path audit

The final direct review found that the isolated estimator tests were not enough:
materialized intervals still had null pricing and disabled calibration flags, the
materializer retained only one globally selected window/cohort, and interval token
components represented only the endpoint call. Those defects would have left real
dashboard data observed-only or incomplete even though the synthetic estimator
tests passed.

### Added RED coverage

- `open`, `completed`, and `ambiguous` cycle states derived from reset chronology.
- historical reconstruction invariance when later evidence is added or `now` advances.
- cumulative-credit interpolation without fabricated timing when samples are absent.
- reset/censor boundaries suppressing post-observation estimates.
- recency, cycle quality, interval confidence, and pricing-coverage weighting.
- one real comparable prior cycle and explicit per-window sample counts.
- elapsed-time-normalized pace (`percent_per_hour`) with censored rows excluded.
- all canonical calls between anchors contributing token components and credits.
- unpriced intervals remaining ineligible below 95% coverage.
- materialized pricing reaching the status estimator with no hard-coded capacity default.
- weekly, five-hour, normal, and alternate cohorts all surviving materialization.

### Production behavior

- Rate-card enrichment is calculated from each canonical aggregate call between
  allowance anchors. Pricing confidence and token coverage are persisted; calibration,
  forecasting, and change-detection flags require at least 95% coverage and supported
  confidence.
- Capacity remains personal and data-derived. Synthetic ratios in tests are fixtures,
  never production defaults or claims.
- Calibration uses completed quality-approved weekly cycles only, one normalized
  contribution per cycle, with recency and support weights capped at one.
- Walk-forward reconstruction weights are evaluated at each historical endpoint, so
  merely running the model later cannot rewrite prior estimates.
- Pace is dimensionally consistent: both window rates and pace residuals use percentage
  points per hour.

### Final verification

```text
focused Task 6 gate: 47 passed
materialization/dedup gate: 13 passed
full pytest: 962 passed
ruff: passed
mypy: passed
compileall: passed
git diff --check: passed
JetBrains ERROR inspections: 0 problems
```

The broad suite also exposed stale migration-version assertions and an obsolete
`limit=0` benchmark request from earlier tasks; both were aligned with schema v27 and
the finite 1000-row interactive maximum.
