# Limits Intelligence Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the inaccurate, oldest-first Limits tab with a reset-aware, statistically defensible system that reports current allowance status, historical estimates, forecasts, and evidence through consistent dashboard, HTTP, and MCP contracts.

**Architecture:** Preserve canonical allowance observations as the immutable evidence layer; materialize reset cycles and intervals into indexed SQLite tables; compute status and bounded series synchronously; compute calibrated forecasts and selection-corrected change analysis asynchronously and persist results by source revision and model version. Additive v2 contracts become the dashboard/MCP default while v1 remains compatible.

**Tech Stack:** Python 3.10+, SQLite, stdlib HTTP server, MCP Python SDK, React 19, TypeScript, TanStack Query, Recharts, pytest, Vitest.

## Global Constraints

- Work only in `/Users/Monsky/Developer/Codex/codex-usage-tracker-limits-intelligence` on `feature/limits-intelligence-redesign`.
- Use `ALLOWANCE_MODEL_VERSION = "reset-aware-v2"` everywhere a derived result is cached or persisted.
- Keep physical source rows for provenance, but derive Limits data only from canonical usage and canonical allowance observations.
- Never interpolate across resets. Emit explicit `reset`, `conflict`, and `anchor_correction` points.
- Only label direct allowance snapshots as `observed`; token/rate-card reconstructions are `estimated`; future values are `forecast`.
- Interactive history is finite. Defaults: status latest only, series by requested range, evidence 50 transitions, evidence hard cap 500.
- Status responses use `Cache-Control: no-store`. Evidence cursors bind to the source revision and fail closed after a revision change.
- Rate-card coverage and observation conflicts lower confidence and block strong claims; they are never hidden.
- Do not hand-edit generated dashboard assets. Run the frontend build to regenerate package-owned assets.
- Use synthetic fixtures only. Do not expose raw prompts, messages, or transcript content.

---

## Task 1: Establish the v1 correctness floor

**Files:**
- Create: `tests/store/test_allowance_observations.py`
- Modify: `src/codex_usage_tracker/store/allowance_observations.py`
- Modify: `src/codex_usage_tracker/allowance_intelligence/statistics.py`
- Modify: `src/codex_usage_tracker/server/allowance.py`
- Modify: `tests/allowance_intelligence/test_statistics.py`
- Modify: `tests/server/test_server_allowance.py`

- [ ] Write a failing store test proving `limit=2` returns the two newest observations in chronological display order:

```python
rows = query_allowance_observations(db_path, limit=2)
assert [row["event_timestamp"] for row in rows] == ["2026-07-13T00:00:00Z", "2026-07-14T00:00:00Z"]
```

- [ ] Run `PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/store/test_allowance_observations.py -q`; expect FAIL because the current SQL limits an ascending scan.
- [ ] Change the query to select the newest tail through an indexed descending inner query and return it ascending only when explicitly requested:

```sql
SELECT * FROM (
    SELECT ... FROM allowance_observations
    WHERE ...
    ORDER BY event_timestamp DESC, cumulative_total_tokens DESC, window_key DESC
    LIMIT ?
) AS newest
ORDER BY event_timestamp ASC, cumulative_total_tokens ASC, window_key ASC
```

- [ ] Add `newest_first: bool = False` to the store query, with evidence callers using `True` and legacy history retaining chronological order.
- [ ] Add a failing large-sample confidence-interval test with at least 2,000 values and assert finite bounds, then replace direct `2.0 ** sample_size` probability construction with a recurrence/log-safe binomial calculation.
- [ ] Add a server regression test that rejects `limit=0` for interactive allowance history and documents the finite maximum.
- [ ] Run:

```bash
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/store/test_allowance_observations.py tests/allowance_intelligence/test_statistics.py tests/server/test_server_allowance.py -q
```

Expected: PASS.

- [ ] Stage exact files and commit: `fix: harden allowance history correctness`.

## Task 2: Add allowance intelligence storage and migration

**Files:**
- Create: `src/codex_usage_tracker/store/allowance_schema.py`
- Modify: `src/codex_usage_tracker/store/schema.py`
- Modify: `src/codex_usage_tracker/store/deduplication_schema.py`
- Modify: `tests/store/test_store_migrations.py`
- Modify: `tests/store/test_usage_deduplication_migration.py`

- [ ] Write migration tests expecting schema version 26 and these tables:

```text
allowance_source_state
allowance_cycles
allowance_intervals
allowance_analysis_snapshots
```

- [ ] Assert indexes exist for latest cohort/window cycle status, cycle time ranges, descending interval evidence, source-revision lookup, and exact snapshot cache-key lookup.
- [ ] Run the migration tests; expect FAIL because migration 26 is absent.
- [ ] Implement `migrate_allowance_intelligence_v2(connection)` in the new focused module. Use structural columns only during migration; pricing-dependent estimates remain nullable until service/analysis enrichment.
- [ ] Store source state as one row containing `source_revision`, `observation_count`, `latest_observed_at`, `model_version`, and `rebuilt_at`.
- [ ] Store cycles with window/cohort identity, reset bounds, observed start/end percentages, conflict count, canonical observation count, and source revision.
- [ ] Store intervals with cycle id, endpoint observation ids, token components, nullable credits, coverage/confidence, point kind, and source revision.
- [ ] Store analysis snapshots by a unique semantic key composed of source revision, model version, archive scope, window, cohort, and forecast horizon.
- [ ] Register migration 26 without changing older migrations. Ensure canonical deduplication rebuild invokes derived allowance rebuild rather than preserving stale derived rows.
- [ ] Run:

```bash
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/store/test_store_migrations.py tests/store/test_usage_deduplication_migration.py -q
```

Expected: PASS from a blank database and a version-25 database.

- [ ] Stage exact files and commit: `feat: add allowance intelligence storage`.

## Task 3: Derive reset cycles and canonical intervals

**Files:**
- Create: `src/codex_usage_tracker/allowance_intelligence/contracts.py`
- Create: `src/codex_usage_tracker/allowance_intelligence/cycles.py`
- Create: `src/codex_usage_tracker/store/allowance_materialization.py`
- Modify: `src/codex_usage_tracker/store/allowance_observations.py`
- Modify: `src/codex_usage_tracker/store/api.py`
- Create: `tests/allowance_intelligence/test_cycles.py`
- Create: `tests/store/test_allowance_materialization.py`

- [ ] Define typed immutable contracts for `AllowanceCohort`, `AllowanceCycle`, `AllowanceInterval`, `AllowancePointKind`, and `AllowanceConfidence`.
- [ ] Write failing cycle tests for: reset timestamps within 60 seconds coalescing; weekly reset boundaries; five-hour used-percent decreases; conflicting snapshots; an alternate constant-zero cohort not replacing a progressing primary cohort; and no interval crossing a reset.
- [ ] Write failing materialization tests proving copied physical usage rows cannot create duplicate allowance intervals and a canonical rebuild removes stale derived rows.
- [ ] Implement deterministic cohort selection from the newest valid canonical observation. A fresh/aging normal `codex` cohort remains primary; an alternate becomes explicitly selectable only when normal is stale and the alternate has at least three observations with more than one distinct percentage in one cycle. Same-timestamp ties prefer normal `codex`; constant-zero alternates remain diagnostic.
- [ ] Implement cycle derivation that clusters reset timestamps within 60 seconds, uses their median display epoch, chooses the nearest existing epoch during incremental ingestion, emits `conflict` evidence instead of averaging contradictory snapshots, and marks missing reset metadata ambiguous. A weekly same-epoch decrease is a reversal/conflict; a five-hour decrease is normal rolling behavior unless metadata proves a reset.
- [ ] Implement transactional materialization: read canonical observations, derive all affected cycles/intervals in memory, delete derived rows for the affected window/source revision, insert replacements, and atomically update `allowance_source_state`.
- [ ] Update the store refresh hook so a canonical-revision change marks materialized intelligence stale and rebuilds once after streaming refresh, not once per record.
- [ ] Run:

```bash
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/allowance_intelligence/test_cycles.py tests/store/test_allowance_materialization.py tests/store/test_usage_deduplication.py -q
```

Expected: PASS with no cross-reset interval and no copied-row double counting.

- [ ] Stage exact files and commit: `feat: derive reset-aware allowance cycles`.

## Task 4: Add bounded indexed queries and revision-bound evidence cursors

**Files:**
- Create: `src/codex_usage_tracker/store/allowance_intelligence.py`
- Create: `tests/store/test_allowance_intelligence_queries.py`

- [ ] Write failing tests for latest status lookup, bounded range lookup, latest-first evidence, cursor continuation, cursor revision mismatch, and query plans using the new indexes.
- [ ] Define an opaque cursor as URL-safe JSON containing `source_revision`, `observed_at`, and stable row id; reject malformed or stale-revision cursors with a typed `AllowanceCursorError`.
- [ ] Implement O(log n + k) SQLite queries:

```python
query_latest_allowance_state(connection, *, window_kind, cohort_id=None)
query_allowance_series(connection, *, start_at, end_at, window_kind, cohort_id=None)
query_allowance_evidence(connection, *, limit=50, cursor=None, window_kind=None)
```

- [ ] Clamp evidence limit to 1–500 and return `next_cursor=None` at exhaustion.
- [ ] Run the new store test module; expect PASS and indexed query-plan assertions.
- [ ] Stage exact files and commit: `feat: add indexed allowance intelligence queries`.

## Task 5: Build v2 status, series, and evidence services

**Files:**
- Create: `src/codex_usage_tracker/allowance_intelligence/service.py`
- Modify: `src/codex_usage_tracker/allowance_intelligence/__init__.py`
- Create: `tests/allowance_intelligence/test_service.py`

- [ ] Write contract tests for schema ids:

```text
codex-usage-tracker-allowance-status-v2
codex-usage-tracker-allowance-series-v2
codex-usage-tracker-allowance-evidence-v2
```

- [ ] Test freshness exactly: weekly is `fresh` through 5 minutes and `aging` through 6 hours; five-hour is `fresh` through 5 minutes and `aging` through 15 minutes; older values are `stale`, and passing the reported reset timestamp makes an older observation stale immediately.
- [ ] Test range/granularity presets: Day=`24h`, Week=`7d`, Month=`8w`, six-month overview=`6m`, plus validated custom start/end and granularity.
- [ ] Implement status with weekly first, optional five-hour, used/remaining, reset countdown, `observed_at`, freshness, cohort/conflict diagnostics, pricing coverage, canonical source revision, copied-row exclusion diagnostics, `changed`, and a compact `next` action. Accept `include_archived` and `since_revision`; matching revisions return `changed=false` without expanding the payload.
- [ ] Implement reset-aware series with explicit point kinds `observed`, `estimated`, `forecast`, `reset`, `conflict`, and `anchor_correction`. Never connect points across cycle ids.
- [ ] Implement evidence newest first, default 50 meaningful transitions, physical provenance fields when local privacy mode permits them, canonical/dedupe fields, strict-mode identifier removal, and revision-bound pagination. Keep full strict evidence export as an explicit offline action.
- [ ] Run the service tests; expect PASS with exact payload snapshots.
- [ ] Stage exact files and commit: `feat: expose allowance status series and evidence`.

## Task 6: Add prior-only estimation and walk-forward forecast validation

**Files:**
- Create: `src/codex_usage_tracker/allowance_intelligence/estimation.py`
- Modify: `src/codex_usage_tracker/allowance_intelligence/model.py`
- Create: `tests/allowance_intelligence/test_estimation.py`

- [ ] Write failing tests proving historical estimates use only capacity available before each interval, future observations cannot change older estimates, missing pricing produces explicit coverage gaps, and endpoint mismatch becomes a signed `anchor_correction` rather than being spread backward.
- [ ] Implement per-cycle reconstruction:

```python
explained_delta = interval_credits / prior_capacity_credits_per_percent
estimated_used = start_used + explained_delta * cumulative_credits / interval_credits
anchor_correction = observed_delta - explained_delta
```

- [ ] Weight calibration by cycle, recency, interval quality, and pricing coverage; cap any single cycle's influence.
- [ ] Produce forecast quantiles from walk-forward residuals only. Report sample size, evaluation horizon, median absolute error, interval coverage, and calibration window.
- [ ] Suppress a numerical forecast when there is insufficient prior-cycle evidence; return a structured reason instead. Five-hour windows remain observed context and do not receive the weekly monotonic-capacity forecast.
- [ ] Run:

```bash
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/allowance_intelligence/test_estimation.py tests/allowance_intelligence/test_allowance_intelligence.py -q
```

Expected: PASS and no future-data leakage.

- [ ] Stage exact files and commit: `feat: calibrate reset-aware allowance forecasts`.

## Task 7: Add selection-corrected change analysis and persisted snapshots

**Files:**
- Create: `src/codex_usage_tracker/allowance_intelligence/change_detection.py`
- Create: `src/codex_usage_tracker/allowance_intelligence/analysis.py`
- Modify: `src/codex_usage_tracker/allowance_intelligence/statistics.py`
- Create: `tests/allowance_intelligence/test_change_detection.py`
- Create: `tests/allowance_intelligence/test_analysis.py`

- [ ] Write failing tests showing an unadjusted best split is not presented as significant, cycle-block permutations control false positives, a planted regime change is detected, conflicts/low coverage block strong claims, and identical cache keys reuse snapshots.
- [ ] Implement max-statistic candidate selection across eligible cycle boundaries, then calculate a permutation p-value from the distribution of the maximum statistic under cycle-block permutations.
- [ ] Use exact enumeration only when bounded and safe; otherwise use a deterministic seed derived from the semantic cache key. Persist the seed, candidate count, permutation count, Monte Carlo uncertainty, effect size, adjusted p-value, confidence interval, caveats, and validation metrics.
- [ ] Use stable recurrence/log-space math for all large-sample statistics. Never construct `2**n` as a float.
- [ ] Implement snapshot read-through caching keyed by source/model/rate-card revisions and analysis parameters. Payloads must say `insufficient_evidence`, `no_supported_change`, or `supported_change`; never say `public claim ready`.
- [ ] Run the two new analysis test modules; expect PASS and deterministic results.
- [ ] Stage exact files and commit: `feat: add defensible allowance change analysis`.

## Task 8: Expose v2 HTTP routes and asynchronous analysis jobs

**Files:**
- Create: `src/codex_usage_tracker/server/allowance_v2.py`
- Modify: `src/codex_usage_tracker/server/routes.py`
- Modify: `src/codex_usage_tracker/server/handler.py`
- Modify: `src/codex_usage_tracker/server/route_inventory.py`
- Modify: `src/codex_usage_tracker/server/responses.py`
- Create: `tests/server/test_server_allowance_v2.py`
- Modify: `tests/server/test_route_inventory.py`
- Modify: `tests/server/test_analysis_jobs.py`

- [ ] Write failing route tests for:

```text
GET  /api/allowance/status
GET  /api/allowance/series
GET  /api/allowance/evidence
GET  /api/allowance/analysis
POST /api/allowance/analysis/jobs
GET  /api/allowance/analysis/jobs?job_id=...
```

- [ ] Test validation errors, `Cache-Control: no-store` on status, finite range caps, stale cursor conflict, and localhost/token protections inherited from existing aggregate routes.
- [ ] Extend `send_json_response` with optional response headers so status can set no-store without duplicating response machinery.
- [ ] Route sync calls to the v2 service and analysis starts through the existing `AnalysisJobRegistry`. `GET /api/allowance/analysis` returns a compatible persisted result or `status=missing`; completed jobs tell callers to reload that endpoint. Reuse `codex-usage-tracker-analysis-job-v1`, polling every 500 ms while active.
- [ ] Deduplicate concurrent jobs by semantic request key and persist completed analysis before returning the terminal result.
- [ ] Keep all v1 routes unchanged and inventory both generations.
- [ ] Run:

```bash
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/server/test_server_allowance_v2.py tests/server/test_route_inventory.py tests/server/test_analysis_jobs.py tests/server/test_server_allowance.py -q
```

Expected: PASS.

- [ ] Stage exact files and commit: `feat: add allowance intelligence v2 API`.

## Task 9: Make deduped v2 Limits intelligence the MCP default

**Files:**
- Modify: `src/codex_usage_tracker/cli/mcp_allowance.py`
- Modify: `src/codex_usage_tracker/cli/mcp_server.py`
- Modify: `tests/cli/test_allowance_intelligence_cli_mcp.py`

- [ ] Write failing MCP tests for `usage_allowance_status`, `usage_allowance_series`, `usage_allowance_evidence`, `usage_allowance_analysis`, and `usage_allowance_analysis_status`.
- [ ] Assert status/series/evidence use canonical rows by default, disclose copied physical rows excluded, preserve provenance in evidence, and never accept unbounded history.
- [ ] Implement thin MCP wrappers over the same v2 application services and analysis registry used by HTTP. `usage_allowance_status` is the polling entry point and directs stale indexes through the existing `usage_refresh_start`/`usage_refresh_status` flow. Keep legacy tools as documented compatibility aliases where names already exist.
- [ ] Keep default MCP payloads concise: status has no full series; series is bounded; evidence defaults to 50; analysis returns a job and is polled separately.
- [ ] Run the MCP test module; expect PASS.
- [ ] Stage exact files and commit: `feat: make deduped limits intelligence the mcp default`.

## Task 10: Add frontend v2 API and polling lifecycle

**Files:**
- Create: `frontend/dashboard/src/api/allowanceIntelligence.ts`
- Create: `frontend/dashboard/src/api/allowanceIntelligence.test.ts`
- Modify: `frontend/dashboard/src/api/types.ts`
- Modify: `frontend/dashboard/src/features/limits/LimitsPage.tsx`
- Modify: `frontend/dashboard/src/features/limits/LimitsPage.test.tsx`

- [ ] Define discriminated TypeScript unions for confidence/freshness/point kinds and exact v2 payload types.
- [ ] Write failing API tests for parameter encoding, finite defaults, evidence cursors, analysis POST, and job status.
- [ ] Implement typed loaders without `limit=0`.
- [ ] In the page test, assert polling intervals: status 30 seconds while `fresh`/`aging`, 60 seconds while `stale`/empty, hidden tabs stop polling, transient failures back off to at most five minutes, series/evidence refetch only after revision changes, and analysis status 500 ms only while pending/running.
- [ ] Replace the current fake refresh and ten-minute status cache with TanStack Query keys containing window/range/granularity/source revision.
- [ ] Run:

```bash
npm --workspace frontend/dashboard run test -- src/api/allowanceIntelligence.test.ts src/features/limits/LimitsPage.test.tsx
```

Expected: PASS with no unbounded request.

- [ ] Stage exact files and commit: `feat: connect limits dashboard to v2 intelligence`.

## Task 11: Redesign the Limits tab around now, history, and evidence

**Files:**
- Create: `frontend/dashboard/src/features/limits/LimitsNow.tsx`
- Create: `frontend/dashboard/src/features/limits/LimitsTimeline.tsx`
- Create: `frontend/dashboard/src/features/limits/LimitsModelHealth.tsx`
- Modify: `frontend/dashboard/src/features/limits/AllowanceEvidenceLedger.tsx`
- Modify: `frontend/dashboard/src/features/limits/allowanceVisualization.ts`
- Modify: `frontend/dashboard/src/features/limits/allowanceModel.ts`
- Modify: `frontend/dashboard/src/features/limits/LimitsPage.tsx`
- Modify: `frontend/dashboard/src/styles.css`
- Modify: `frontend/dashboard/src/features/limits/LimitsPage.test.tsx`
- Modify: `frontend/dashboard/src/features/limits/allowanceModel.test.ts`

- [ ] Write failing component/model tests for: weekly-first current status; optional five-hour card; freshness/reset countdown; Day/Week/Month/Custom controls; reset-separated line segments; observed/estimated/forecast styling; latest-first 50-row evidence; load-more cursor; conflict/coverage warnings; and honest insufficient-evidence states.
- [ ] Implement `LimitsNow` with used/remaining, reset time, freshness, pace, and forecast quantiles when available.
- [ ] Implement a zoomable timeline with brush selection and previous-cycle comparison whose default modes map to 24h, 7d, 8w, and 6m/custom; reset boundaries must visibly break segments.
- [ ] Replace the current hypothesis-centric model with model health: observation coverage, priced-credit coverage, validation error/coverage, conflict count, copied rows excluded, last model revision, and caveats.
- [ ] Update the evidence ledger to newest-first transitions with physical provenance opt-in details and canonical/dedupe status visible.
- [ ] Remove misleading claims and the obsolete hypothesis interaction from the primary tab.
- [ ] Run targeted frontend tests plus `npm --workspace frontend/dashboard run typecheck`; expect PASS.
- [ ] Stage exact files and commit: `feat: redesign limits intelligence dashboard`.

## Task 12: Document, regenerate, and verify end to end

**Files:**
- Modify: `docs/allowance-intelligence.md`
- Modify: `docs/dashboard-guide.md`
- Modify: `docs/mcp.md`
- Modify: `docs/cli-json-schemas.md`
- Modify: `docs/usage-drain-modeling.md`
- Create: `docs/database-schema.md`
- Modify: `docs/architecture.md`
- Modify: `docs/privacy.md`
- Modify: `CHANGELOG.md`
- Modify generated dashboard assets produced by `npm run dashboard:build`

- [ ] Document truth layers, reset semantics, freshness thresholds, confidence/coverage gates, v2 schemas, evidence pagination, analysis polling, v1 compatibility, and physical-provenance opt-in behavior.
- [ ] Add synthetic contract examples for every v2 HTTP/MCP payload. State that copied clone rows are excluded from default totals and disclosed diagnostically.
- [ ] Run frontend generation and governance:

```bash
npm run dashboard:build
/Users/Monsky/.codex/bin/codex-task dashboard-verify --json
/Users/Monsky/.codex/bin/codex-task dashboard-governance --json
/Users/Monsky/.codex/bin/codex-task dashboard-source-budget --json
/Users/Monsky/.codex/bin/codex-task dashboard-route-budget --json
```

- [ ] Run the full repository gates:

```bash
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m ruff check .
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m mypy
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m compileall src
for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python scripts/check_release.py
git diff --check
```

- [ ] Run a bounded live aggregate audit against the local database without printing raw records: compare canonical token totals, physical totals, copied-row exclusion count, latest weekly/five-hour status, source revision, range query latency, evidence latency, conflict count, and pricing coverage. Do not start a dashboard with `--limit 0`.
- [ ] Review `git status --short --branch`, `git diff --stat`, the complete task diff, and staged paths for private data or secrets.
- [ ] Stage exact generated/docs files and commit: `docs: document limits intelligence v2`.
- [ ] Run `superpowers:verification-before-completion`, then `superpowers:requesting-code-review`. Address any correctness findings and rerun the smallest affected gates plus the full release-relevant gate.

## Definition of Done

- [ ] The newest allowance evidence appears first, with finite pagination.
- [ ] Dashboard, API, reports, recommendations, diagnostics, thread summaries, and MCP use canonical/deduped allowance usage by default.
- [ ] Copied clone rows excluded are explicitly counted; physical provenance is opt-in and preserved.
- [ ] Current status is fast and polling-safe; expensive analysis is asynchronous, revision-keyed, and persisted.
- [ ] History never interpolates across resets and distinguishes observed, estimated, forecast, conflict, reset, and anchor correction.
- [ ] Forecasts are prior-only and walk-forward validated; change claims are selection-corrected and coverage-gated.
- [ ] v1 contracts remain compatible and all v2 contracts are documented and synthetically tested.
- [ ] Targeted tests, frontend governance, full pytest, type checking, compilation, release checks, and diff checks pass.
