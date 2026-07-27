# K7 Focused Evidence Console

## Outcome

Ship a dependency-light, snapshot-first browser client for exactly Live,
Explore, Evidence, Limits, and Settings. Browser navigation must never start a
refresh or replace a valid committed generation with zero.

## Owned paths

- `frontend/kernel-console/**`
- `src/codex_usage_tracker/kernel/interfaces/http/console.py`
- `src/codex_usage_tracker/kernel/interfaces/http/console_assets/**`
- `tests/kernel/console/**`
- `tests/frontend/**`
- `scripts/build_kernel_console.mjs`
- `scripts/check_kernel_console.mjs`
- K7 packaging, scope, verification, roadmap, and efficiency-ledger wiring

## Observable contracts

1. `/` redirects to `/live`; only the five approved console areas route.
2. A console GET is read-only and does not start or join refresh work.
3. `/evidence/<encoded-selector>` round-trips K5/K6 exact deep links.
4. The browser renders the committed generation before any freshness action.
5. Live reconnect deduplicates generations; refresh remains explicit.
6. Generated assets are deterministic, package-owned, privacy-safe, and
   bounded by the K7 bundle budget.

## Verification

- Focused Python route, read-only, packaging, and privacy contracts
- Frontend lint, typecheck, unit, accessibility, localization, governance,
  deterministic-assets, and bundle checks
- Playwright fresh, warm, stale, active-refresh, restart, reconnect, and exact
  deep-link flows with synthetic fixtures
- Identical unprofiled warm-render workload and attribution-only profiling
- `just v`, exact distributions, isolated installed-wheel console smoke
- One final read-only reviewer after the diff is stable
