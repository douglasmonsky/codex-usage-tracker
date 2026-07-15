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
