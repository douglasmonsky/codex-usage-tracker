# K8 Allowance Efficiency

## Outcome

Expose exact allowance observations and deterministic, reset-aware efficiency
ratios without claiming that locally observed usage caused the allowance
movement.

## Owned paths

- `src/codex_usage_tracker/kernel/allowance/**`
- K8 allowance integration in `src/codex_usage_tracker/kernel/application/**`
- K8 allowance query measures and public schema descriptions
- Limits presentation in `frontend/kernel-console/**` and packaged assets
- `tests/kernel/allowance/**` and focused K8 interface/Console contracts
- K8 disposition, scope, verification, roadmap, and efficiency-ledger wiring

## Observable contracts

1. Observed used/remaining percentages and timestamps remain exact facts.
2. Ratios use only adjacent observations from the same logical window and
   reset; incompatible windows are never interpolated.
3. Local tokens, calls, and turns are counted in the observed interval and
   divided only by a positive observed percentage-point delta.
4. Outside usage, missing observations, resets, and unchanged or non-monotonic
   percentages remain explicit caveats.
5. Cost and credit estimates require a source-stamped local rate card and
   expose rated-token coverage.
6. Allowance reads never refresh or write the analytical cache; a newly
   appended observation becomes visible through the ordinary incremental
   ingest path.

## Verification

- Synthetic reset, missing, outside-usage, unchanged, and mixed-window fixtures
- Retained v0.25.1 observation-selection oracle comparison
- Query, MCP/HTTP, and Limits grade/coverage assertions
- Incremental appended-observation visibility without full rebuild
- Pricing/rate-card provenance and partial-coverage tests
- Focused performance/privacy/package checks, `just v`, exact distributions,
  installed-wheel smoke, and one final read-only reviewer
