# Limits Intelligence Redesign

## Goal

Turn Limits from a fragile historical change-point experiment into a trustworthy, reset-aware allowance workspace that answers:

1. What allowance percentage was most recently observed?
2. When will the active window reset?
3. What likely happened between observations?
4. Where could the counter finish if the current pace continues?
5. Has the relationship between local usage and visible allowance movement changed?

The dashboard, API, CLI, and MCP surfaces must share the same canonical data, inference, quality, and polling semantics. Direct observations, historical estimates, and forward projections must remain visibly and contractually distinct.

## Why The Current Design Must Change

The live-data and code audit found correctness and operability failures that cannot be repaired in the browser alone:

- allowance history is ordered oldest-first before SQL `LIMIT`, so bounded history and diagnostics analyze the oldest rows while calling some of them recent;
- the dashboard avoids that defect with two unbounded `limit=0` requests, which can load the entire allowance history and diagnostic input into the browser;
- full-history diagnostics can overflow while constructing exact median intervals for large samples;
- previously materialized `allowance_observations` can retain rows later classified as copied duplicates, even though normal incremental sync now reads canonical usage;
- the detector searches many candidate change points and reports the selected split's unadjusted p-value, which does not control false positives after split selection;
- reset identity, simultaneous conflicting observations, percent quantization, price coverage, and unexplained outside usage are not eligibility gates;
- the current primary cohort is selected by historical row/span count rather than the newest valid status;
- refresh rereads the same reports without proving that a newer allowance observation exists;
- MCP has synchronous history/diagnostic reads but no compact revisioned polling contract;
- the page emphasizes research-readiness and a deterministic hypothesis button instead of remaining percentage, reset time, observation freshness, or current pace.

The local aggregate dataset also demonstrates why these are material rather than theoretical issues: active allowance observations contain stale rows backed by now-excluded copied usage, current rate-limit events may expose only a weekly window, reset timestamps can jitter by a few seconds across sessions, and concurrent logs can briefly report adjacent percentages out of order.

## Product Principles

- **Now first.** Current observed state is the primary product; historical inference and regime analysis are secondary.
- **Observed is not estimated.** Every payload and visual distinguishes upstream observations, anchored historical estimates, and forecasts.
- **Reset aware.** No interpolation, aggregation, or test crosses an allowance reset boundary.
- **Canonical by default.** All allowance accounting uses canonical billable usage. Physical usage rows remain provenance only.
- **Quality gated.** Conflicts, reset ambiguity, poor pricing coverage, sparse sampling, and unexplained movement reduce or disable inference.
- **Prior-only prediction.** Forecasting and validation never use future observations.
- **Finite interactive work.** Dashboard and MCP reads are bounded, indexed, revisioned, and cursor paginated.
- **Graceful degradation.** A failure in forecasting or change analysis never hides the most recent direct observation.
- **Local evidence only.** The tracker cannot claim access to OpenAI's internal allowance ledger or usage outside the indexed local sources.

## Scope

This redesign includes:

- canonical allowance observation reconciliation;
- reset-cycle and interval materialization;
- a compact current-status contract;
- reset-aware daily, weekly, monthly, and custom time series;
- historical interpolation, conditional forecasting, walk-forward validation, and selection-corrected change detection;
- latest-first evidence pagination;
- dashboard and MCP polling mechanics;
- migration, privacy, documentation, and comprehensive validation.

It does not include:

- transcript, prompt, response, or tool-output analysis;
- claiming an official allowance total or billing reconciliation;
- automatically reading another product's account ledger;
- promoting the entire exploratory `usage_drain` model into the primary product;
- treating model-generated estimates as replacement observations;
- automatic background monitoring when no dashboard or MCP caller requests it.

## Truth Hierarchy

The system exposes three first-class series layers.

### Observed

An observed point is a canonical `token_count.rate_limits` snapshot recorded by Codex. The reported used percentage, window length, reset timestamp, plan, and limit ID are preserved exactly. The tracker may classify an observation as stale, conflicting, or superseded, but it does not rewrite the physical observed value.

### Estimated

An estimated point describes likely movement between two accepted observed anchors within one reset cycle. It is derived from canonical local activity and the two known endpoints. It is never allowed to cross a reset, cohort change, unresolved conflict, or censored interval.

### Forecast

A forecast begins after the latest accepted observed anchor and describes the conditional outcome if the measured local pace continues. It uses only earlier eligible intervals and prior observed activity. It always includes a range and the phrase-equivalent semantic `if_current_pace_continues`.

Contracts use an explicit `point_kind` of `observed`, `estimated`, `forecast`, `reset`, `conflict`, or `anchor_correction`. Anchor corrections carry a reason such as `unexplained_positive_movement`, `model_overprediction`, or `quantization`. The dashboard uses distinct markers, line treatments, and legend labels for each kind.

## Canonical Observation Repair

`allowance_observations` remains the normalized observation table, but it is rebuilt and maintained exclusively from `canonical_usage_events`.

The next schema migration must transactionally:

1. remove all existing derived allowance observations;
2. repopulate both primary and secondary observations from canonical usage only;
3. rebuild reset-cycle and interval derivatives;
4. update allowance source state and revision metadata;
5. invalidate persisted allowance analyses and aggregate query-cache entries;
6. verify that every observation joins to one canonical usage row before commit.

This rebuild intentionally deletes only derived observation/analysis rows. Physical `usage_events`, `source_records`, and dedupe provenance remain intact.

The same reconciliation is idempotent and available to schema repair. Incremental ingestion synchronizes affected canonical record IDs, removes derivatives for records whose canonical status changed, and advances the allowance revision only when the canonical allowance source changes.

The diagnostic contract reports:

- stored canonical observation count;
- stale/noncanonical observation count found during reconciliation;
- rebuilt observation count;
- latest canonical observation time;
- source revision and model version.

After migration, the stale/noncanonical persisted count must be zero.

## Cohorts And Active Selection

An allowance cohort is identified by:

- `window_kind` and `window_minutes`;
- `plan_type`;
- `limit_id`;
- normalized reset-cycle identity.

The current status response returns every currently relevant cohort, but one cohort per window kind may be selected for primary display.

Primary selection is based on the newest valid canonical observation, not historical sample size. A valid observation has a percentage in `[0, 100]`, a recognized window kind, and no exclusion reason. A valid normal `codex` cohort remains primary while its newest observation is `fresh` or `aging` under the window-specific thresholds. An alternate `codex_*` cohort never silently replaces that normal cohort. If the normal cohort is stale, an alternate may become an explicit selectable cohort only after at least three canonical observations in one reset cycle include more than one distinct percentage. Otherwise status is `partial` and requests reconciliation. An alternate `0%` is preserved as an observation but a constant-zero series cannot establish primary-cohort eligibility.

Within one eligible cohort, rows are ordered by event timestamp descending and then physical record ID ascending. When normal and alternate observations have the same timestamp, normal `codex` wins the display tie. These rules are deterministic and returned in cohort-selection diagnostics.

When an alternate cohort is repeatedly newer than the selected normal cohort, status becomes `partial` and returns a reconciliation recommendation. The UI explains the discrepancy instead of presenting the alternate as an official replacement.

## Reset-Cycle Identity

Weekly analysis assumes monotonic use only inside a confirmed reset cycle. Five-hour rolling windows do not use that assumption.

Reset timestamps from the same window/cohort within 60 seconds are treated as jitter around one proposed reset epoch. A deterministic rebuild clusters timestamps in chronological order, uses the median timestamp as the display value, and chooses the nearest existing epoch within tolerance during incremental ingestion. Ties choose the earlier epoch.

A weekly reset is confirmed when either:

- the normalized reset epoch changes beyond tolerance; or
- the prior reset time has passed and a materially lower counter begins a new cycle.

A weekly decrease while the same future reset epoch remains active is classified as a reversal/conflict. It censors pending inference and is not labeled a confirmed reset. Five-hour decreases are normal rolling-window behavior unless other metadata proves a reset.

Every reset cycle has a stable derived `cycle_id` based on window/cohort identity and normalized reset epoch. A cycle is `open`, `completed`, or `ambiguous`.

## Derived Storage

The redesign adds four derived storage surfaces.

### `allowance_source_state`

A singleton state record stores:

- monotonic allowance generation;
- revision string;
- canonical observation count;
- latest observed timestamp;
- last successful reconciliation timestamp;
- active detector/model version.

This table enables constant-size revision checks without scanning the usage database.

### `allowance_cycles`

One row per reset cycle stores:

- cycle/window/cohort identity;
- normalized reset timestamp and raw reset range;
- first and last observation times;
- starting, latest, and peak observed percentages;
- observation, conflict, reversal, and censored-interval counts;
- canonical, priced, and unpriced credit totals;
- price coverage and quality grade;
- open/completed/ambiguous state;
- source revision.

### `allowance_intervals`

One row per pair of accepted anchors or censored boundary stores:

- start/end observation and physical record provenance;
- cycle/window/cohort identity;
- start/end times and percentages;
- visible percent delta and detected percent resolution;
- canonical local tokens and estimated credits between anchors;
- priced-credit coverage and confidence mix;
- interval kind and censor reason;
- simultaneous-conflict count;
- explained and unexplained movement diagnostics;
- eligibility flags for interpolation, calibration, forecasting, and change detection;
- source revision and model version.

### `allowance_analysis_snapshots`

Versioned persisted analysis stores a compact JSON result keyed by:

- source revision;
- detector/model version;
- archive scope;
- cohort/window scope;
- analysis horizon.

Only completed results are served as current analysis. A failed or running job never replaces the last completed compatible result.

Indexes support latest cohort/window status, cycle ranges, descending interval evidence, and exact analysis-snapshot lookup.

## Interval Construction And Quality

The new interval builder adapts only the defensible censoring pattern from `usage_drain`:

- retain canonical calls while the visible percentage is unchanged;
- close a positive interval only when an accepted later anchor increases;
- censor pending attribution on reset, cohort/window change, unresolved conflict, or invalid decrease;
- preserve calls with missing observations as local activity when they belong between valid anchors;
- never use alternate limit snapshots as boundaries for the normal cohort.

It does not import the Usage Drain breakpoint leaderboard, five-hour preference, or in-sample piecewise fits.

An interval is calibration eligible only when:

- both anchors belong to the same non-ambiguous weekly cycle and cohort;
- the end percentage is greater than the start percentage;
- no simultaneous conflict or reversal intersects the interval;
- at least 95% of positive local credits are priced with supported confidence;
- the interval contains positive local activity;
- reset identity remains stable;
- observation timing and missing-activity diagnostics do not classify it as censored.

An interval that fails a gate stays available for provenance and descriptive history but cannot train or confirm the model. Quality reasons are additive and exposed rather than collapsed into an opaque score.

## Percent Resolution And Conflicts

Observed percentages are coarse and often integer-valued. The tracker determines an empirical resolution per cohort/window from positive observed steps and reports it with each analysis. The raw observed percentage remains exact-as-reported; underlying precision is represented as a quantization band rather than fabricated decimals.

Near-simultaneous observations from the same cohort/cycle are grouped into a conflict window. Equal values become one accepted state with multiple provenance sources. Different values create a conflict fact. For monotonic weekly cycles, stale lower values may be superseded for the quality-controlled state path, but they remain in physical provenance and increment conflict diagnostics. No conflicting group is used as an interpolation or change-detection boundary until the monotonic state is unambiguous.

## Historical Usage-Percent Approximation

For an eligible interval with observed delta `D`, positive local credits `C`, and a prior-only capacity calibration `K`, the locally explained movement is:

`explained_delta = C / K`

The estimated historical path distributes only that explained movement in proportion to cumulative canonical local credits:

`estimated_used(t) = start_used + explained_delta * cumulative_credits(t) / C`

At the later observed anchor, the signed correction is `D - explained_delta`. A positive remainder is locally unexplained movement; a negative remainder is model overprediction or quantization error. The correction is emitted as an `anchor_correction`, widens the interval band, and participates in model-health diagnostics. This prevents the chart from attributing the full observed delta to local calls and then separately claiming the same movement was unexplained.

If prior capacity or eligible local credits are unavailable, the interval remains observed-only between anchors and the full endpoint movement is an anchor correction. The system never time-smooths unexplained movement merely to make the chart attractive.

No interpolation crosses a reset or censored boundary.

## Capacity Calibration

Capacity is represented as estimated local credits per visible percentage point. It is a local calibration proxy, not an official allowance total.

For each prediction point, the calibration pool contains only earlier eligible intervals. Estimates are grouped by reset cycle so many intervals from one cycle cannot masquerade as independent weekly evidence. The primary calibration is a robust, recency-weighted median of interval credit-per-percent ratios, with cycle weights normalized so each completed cycle contributes at most one unit of weight.

The response also reports:

- total-ratio estimate across eligible credits and movement;
- median and interquartile range;
- completed cycle count and eligible interval count;
- price coverage;
- unexplained movement share;
- prior-only backtest errors.

If fewer than two completed quality-approved cycles exist, capacity remains `descriptive` and cannot support a sustained-shift conclusion.

## Forecasting

The current-cycle estimate begins at the latest accepted observation:

`estimated_current_used = observed_used + credits_since_observation / prior_capacity`

It is clipped only to `[0, 100]`; clipping is disclosed. If prior capacity is unavailable or quality gated, the page remains observed-only.

The end-of-cycle forecast is conditional, not a behavioral promise. It combines:

- recent 6-hour local credit pace when sufficiently sampled;
- trailing 24-hour pace;
- current-cycle pace;
- comparable prior-cycle pace when available.

The central scenario uses the robust median of available prior-valid pace estimates. Low/high scenarios use empirical walk-forward residual quantiles and the spread among eligible pace windows. The payload always reports the contributing windows, sample counts, and semantic `if_current_pace_continues` caveat.

Five-hour status may show observed remaining percentage, age, and reset metadata. It does not receive the weekly monotonic capacity forecast. Rolling-window decay is shown as context until a separate validated rolling model exists.

## Walk-Forward Validation

Every promoted estimator is evaluated sequentially. At historical interval `i`, calibration and pace features may use only intervals before `i`. Results include:

- mean and median absolute percent error;
- root mean square error;
- empirical 50%, 80%, and 95% interval coverage;
- error by observation gap, reset phase, price coverage, and unexplained-movement band;
- comparison with simple baselines: unchanged counter, previous interval, recent observed pace, and previous-cycle pace.

The estimator is `validated` only when it beats the relevant simple baseline on a time-ordered holdout and its interval coverage is not materially below its advertised level. Otherwise the UI uses `descriptive` or observed-only mode.

The existing Usage Drain prior-only online-capacity and walk-forward mechanics may be adapted behind this narrow interface. Its exploratory transition gates, breakpoint optimization, and predictive leaderboard remain diagnostic-only.

## Allowance-Change Detection

Change analysis is weekly and secondary to current status.

Candidate boundaries occur only between reset cycles. Interval-level ratios remain inputs, but inference resamples or permutes whole cycle blocks so within-cycle intervals are not treated as independent observations.

The detector scans eligible cycle boundaries using one declared effect statistic. The reported p-value is calibrated against the maximum scan statistic for every permutation, thereby accounting for candidate selection. Exact enumeration is used only when bounded and numerically safe; otherwise a deterministic Monte Carlo permutation with a documented seed, iteration count, and Monte Carlo uncertainty is used.

Median confidence intervals use numerically stable order-statistic calculations. They must not compute enormous integer powers through float conversion. Cycle-block bootstrap intervals may be used for effect sizes when exact independent-sample assumptions do not hold.

Evidence grades are:

- `descriptive`: direct history exists but inference is not quality-ready;
- `estimated`: calibrated historical/forecast inference passes minimum validation;
- `possible_shift`: a large exploratory effect exists but persistence, quality, or corrected significance is incomplete;
- `sustained_local_shift`: at least four completed baseline cycles and two completed recent cycles support a capacity ratio at or below `0.75`, a strong cycle-block effect, selection-corrected support, adequate price coverage, and no dominant unexplained-usage/conflict warning;
- `indeterminate`: data quality or outside usage prevents a directional conclusion.

The phrase `public claim ready` is removed. Even `sustained_local_shift` remains explicitly local evidence.

## Current Status And Freshness

The primary status includes:

- used and remaining percentage;
- reset timestamp and countdown;
- observed timestamp and age;
- selected cohort plus alternate-cohort disclosures;
- observed, estimated-current, and projected-at-reset values where available;
- data state: `fresh`, `aging`, `stale`, `partial`, or `empty`;
- quality reasons;
- source revision and model version;
- recommended next action and poll delay.

Freshness is window aware. Passing a reset timestamp always makes an older observation stale. By default, an observation is `fresh` for five minutes. A weekly observation is `aging` until six hours old and then `stale`; a five-hour observation is `aging` until fifteen minutes old and then `stale` because rolling expiry can change it without new local work. These thresholds are centralized model-version constants and are returned in the status payload. Weekly observations may remain the last known value longer, but their age is always shown. A refresh that scans logs without finding a newer allowance event reports `index_refreshed_observation_unchanged` rather than claiming the allowance itself refreshed.

Missing windows are `unavailable`; they never become synthetic `0%` values.

## Time-Series Semantics

The primary chart defaults to the current cycle plus seven prior weekly cycles. The user-facing resolution modes are `Day`, `Week`, `Month`, and `Custom`; each chooses an initial range and can still be zoomed or brushed:

- `Day` starts at `24h`, with `7d` available as a quick range for day-to-day comparison;
- `Week` starts at `8w` for the default week-to-week cycle comparison;
- `Month` starts at `6m` and supports month-to-month summaries;
- `Custom` accepts explicit start/end timestamps and bucket selection.

The series endpoint uses `range=24h|7d|8w|6m|custom` and `granularity=auto|raw|hour|day|week|month|cycle`. Automatic granularity preserves all reset, observed, conflict, and correction anchors while downsampling only eligible estimated activity. It never averages percentages across resets. Month/custom views summarize completed cycles with peak/final percentage, local credits, quality, and forecast error.

Chart data is chronological for rendering. Every table/evidence list is latest-first by default.

## Dashboard Experience

### Now

The top section shows weekly used/remaining percentage, reset countdown, last-observed age, current-cycle pace, projected percentage at reset, and quality. A separate five-hour card appears only when that window is present.

### Timeline

The reset-aware chart supports range presets, custom dates, zoom, brush selection, and previous-cycle comparison. Observations are markers, estimates are a distinct line, forecasts are dashed with a band, and resets/conflicts/unexplained corrections are annotated.

### Intelligence Panels

- **Current pace:** recent burn, projected reset position, contributing pace windows, and forecast confidence.
- **Cycle comparison:** current progress versus comparable prior cycles.
- **Change evidence:** effect, persistence, corrected test result, and caveats.
- **Model health:** walk-forward error, interval coverage, pricing coverage, conflicts, observation density, and unexplained movement.

The current deterministic `Test weekly claim` interaction is removed. Change evidence updates from the shared server analysis rather than relabeling an already loaded result.

### Supporting Evidence

Evidence is latest-first and follows the selected chart range. The first page contains 50 meaningful transitions rather than repeated raw snapshots. Rows distinguish observations, estimates, forecasts, resets, conflicts, censored intervals, and unexplained corrections. Cursor pagination loads older rows. An explicit all-history provenance mode remains bounded per page and links to physical call/source records when available.

## API Contracts

The primary v2 HTTP contracts are:

- `GET /api/allowance/status`
- `GET /api/allowance/series`
- `GET /api/allowance/evidence`
- `GET /api/allowance/analysis`

### Status

Status accepts `include_archived` and optional `since_revision`. It always returns a constant-size JSON payload with schema, generation time, data-as-of time, revision, changed flag, data state, selected cohorts/windows, latest observations, current estimate/forecast, quality, and `next` action. When `since_revision` matches, `changed` is false and the compact payload still includes the next polling delay. Status uses `Cache-Control: no-store`; ETag/HTTP 304 is intentionally not part of v2 so HTTP and MCP callers share one polling semantic.

### Series

Series requires a finite range or a supported range preset and accepts window/cohort, granularity, and archive scope. It returns chronological points, cycle summaries, quality metadata, returned range, available range, truncation/downsampling disclosure, revision, and model version.

### Evidence

Evidence accepts window/cohort, range, `before` cursor, finite `limit`, and `order`. Default order is descending, default limit is 50, and normal interactive limit is capped. The cursor includes the source revision plus the deterministic timestamp/transition/record tie-break needed for stable pagination. A cursor from an older revision receives HTTP 409 `allowance_revision_changed`, and the client restarts from the newest page; rows are never silently skipped or duplicated across revisions.

### Analysis

`GET /api/allowance/analysis` accepts a finite horizon and window/cohort scope and returns only a compatible persisted result or `status=missing`. `POST /api/allowance/analysis/jobs` starts or reuses a job keyed by source revision, model version, archive scope, cohort/window scope, and horizon. `GET /api/allowance/analysis/jobs?job_id=...` returns `queued`, `running`, `completed`, or `failed`, progress, and `poll_after_ms`; completed jobs instruct the caller to reload the persisted result. Job IDs are in-process handles, while completed results survive server restarts in `allowance_analysis_snapshots`.

All contracts include canonical/dedupe status, source revision, model version, data quality, and physical provenance links where privacy mode permits them.

The v1 history, diagnostics, and export contracts remain temporarily available. Their SQL newest-tail defect and numerical crash are fixed, their defaults become finite, and they are documented as compatibility/diagnostic surfaces. Full strict evidence export remains an explicit offline action rather than an interactive unbounded request.

## MCP Contracts And Polling

New MCP tools mirror the v2 contracts:

- `usage_allowance_status(...)`
- `usage_allowance_series(...)`
- `usage_allowance_evidence(...)`
- `usage_allowance_analysis(...)`
- `usage_allowance_analysis_status(job_id)`

`usage_allowance_status` is the polling entry point. It returns `revision`, `changed`, `data_state`, and `next = {action, poll_after_ms, ...}`. It never recomputes full diagnostics.

When local logs need ingestion, the response directs callers to the existing `usage_refresh_start` and `usage_refresh_status` workflow. After completion, the caller reloads allowance status and can distinguish a new observation from an unchanged indexed snapshot.

The dashboard polls allowance status only while Limits is visible. Fresh or aging status recommends 30-second polling; stale or empty status recommends 60 seconds. The separate scoped analysis-job status recommends 500-millisecond polling while queued or running. Hidden tabs stop browser polling. Transient failures back off from 30 seconds to a maximum of five minutes. A changed revision invalidates the selected series/evidence query and requests or reuses analysis for that revision. MCP callers use the returned delay rather than repeatedly requesting 10,000 diagnostic rows.

## Query And Performance Requirements

- Status reads are constant-size indexed reads against derived state/latest observations.
- Allowance revision lookup performs no schema write or migration.
- Evidence limits are applied after descending order, never before a client-side reverse.
- Series reads are bounded by date range and granularity.
- Analysis is persisted by exact revision/scope/model key and does not run on every status poll.
- Dashboard and MCP never send `limit=0`.
- Full-history analysis/export runs outside the persistent dashboard request path.
- Query plans must use allowance cohort/time, cycle/time, interval/time, and analysis-key indexes.

## Privacy And Provenance

The redesign uses aggregate/provenance fields only. It does not read or index transcript content.

Normal local mode may include physical `record_id`, session ID, line number, and source link for Call Investigator. Strict mode removes local identifiers and buckets timestamps consistently with existing strict exports. Model inputs and quality diagnostics contain tokens, estimated credits, percent movement, reset metadata, model/effort, and aggregate timing only.

Observed, canonical, estimated, and physical counts are disclosed so users can understand why provenance rows differ from modeled billable activity.

## Failure Handling

- A status query can succeed while analysis is running or failed.
- The last compatible completed analysis remains available with an explicit stale-analysis flag.
- Missing price data disables affected inference but preserves observations.
- Missing reset metadata creates an ambiguous cycle and prevents cross-boundary inference.
- Missing five-hour data is unavailable, not zero.
- Source revision changes during analysis cause the result to be stored under its original revision and not promoted as current.
- Migration/reconciliation is transactional and rolls back on validation failure.
- Corrupt derived rows can be rebuilt from canonical usage without modifying physical usage provenance.

## Testing Strategy

### Storage And Migration

Synthetic databases cover:

1. pre-dedupe allowance rows backed by copied clone events;
2. canonical rebuild removing stale derived rows while preserving physical usage provenance;
3. idempotent repeated reconciliation;
4. incremental representative promotion/demotion;
5. revision changes only when canonical allowance sources change;
6. migration rollback on validation failure;
7. required indexes and query plans.

### Reset And Interval Semantics

Fixtures cover:

- reset timestamps with seconds of jitter;
- a confirmed weekly reset;
- a same-cycle weekly decrease/conflict;
- normal five-hour rolling decreases;
- simultaneous equal and conflicting observations;
- cohort/plan/limit changes;
- missing reset metadata;
- long observation gaps;
- alternate `codex_*` snapshots;
- percent quantization;
- missing and partial price coverage;
- untracked/outside usage;
- no local credits despite an observed increase.

### Statistical Validation

Deterministic tests prove:

- historical interpolation reaches both observed anchors and never crosses resets;
- forecasts use only prior observations;
- cycle weights prevent one dense cycle from dominating calibration;
- low-quality intervals cannot train or confirm the model;
- advertised prediction-band coverage is measured from walk-forward residuals;
- the estimator falls back when it does not beat a simple baseline;
- null simulations control false positives after candidate selection;
- sustained synthetic shifts remain detectable;
- block inference respects cycle dependence;
- large samples do not overflow exact interval calculations;
- deterministic Monte Carlo results expose seed, iterations, and uncertainty.

### API, MCP, And Polling

Tests cover:

- latest-first SQL limit before pagination;
- stable descending cursors and chronological chart series;
- finite limits and rejected unbounded interactive requests;
- unchanged revisions returning compact `changed=false` status;
- revision-bound evidence cursors and 409 restart behavior;
- status polling without analysis recomputation;
- analysis start/status/result semantics, job reuse, and revision isolation;
- refresh completed with and without a newer allowance observation;
- stale, partial, empty, and observed-only states;
- API/MCP schema parity and compatibility v1 behavior.

### Dashboard

Component and browser tests cover:

- Now cards and missing-window behavior;
- observed/estimated/forecast visual distinction;
- Day, Week, Month, and Custom modes mapped to `24h`, `7d`, `8w`, `6m`, and explicit ranges;
- reset boundaries, zoom, brush, and cycle comparison;
- latest-first first page of 50 evidence rows;
- cursor loading and chart-range synchronization;
- model health and quality reasons;
- loading, partial failure, stale analysis, and full failure states;
- keyboard, screen-reader, responsive, and 200% layout behavior.

### Live Aggregate Audit

After focused and full automated gates pass, run a read-only aggregate/provenance audit against the local database. Confirm:

- zero persisted allowance rows backed by excluded usage;
- current weekly status matches the latest valid canonical snapshot;
- reset jitter is clustered without merging materially different epochs;
- latest-first evidence begins at the data tail;
- interactive payloads remain bounded;
- model health metrics and caveats are populated;
- no transcript/content surface participates.

## Rollout And Compatibility

Implementation proceeds in correctness-first slices:

1. canonical observation repair, newest-tail queries, numerical safety, and regression tests;
2. source revision, reset cycles, intervals, and compact status;
3. bounded series/evidence contracts and MCP parity;
4. prior-only estimation, walk-forward validation, and persisted analysis;
5. dashboard Now/timeline/evidence redesign;
6. compatibility cleanup, documentation, performance, and live audit.

The dashboard switches to v2 only after status, series, evidence, analysis, and migration tests pass together. V1 contracts remain for one compatibility window and never remain the dashboard polling path.

## Documentation

Update allowance intelligence, usage-drain modeling boundaries, dashboard guide, MCP guide, CLI/JSON schemas, database schema, architecture, privacy, and release notes. Documentation must explain:

- observed versus estimated versus forecast values;
- reset-aware time ranges;
- canonical usage and preserved physical provenance;
- conditional forecast semantics;
- quality gates and model health;
- local-evidence limits;
- the status/refresh/poll workflow;
- migration repair of stale copied allowance observations.

## Acceptance Criteria

The redesign is complete when:

- Limits opens with current weekly status, reset countdown, age, quality, and conditional forecast when validated;
- daily, weekly, monthly, and custom reset-aware series are usable and truthful;
- all supporting lists are latest-first and the default evidence window is 50 meaningful rows;
- copied/noncanonical usage cannot participate in allowance accounting;
- bounded queries operate on the newest tail;
- the statistical model passes prior-only, false-positive, coverage, and large-sample safety gates;
- status polling is constant-size and revision based;
- MCP can poll status and analysis without repeatedly loading full history;
- observed-only mode remains useful under missing/poor data;
- API, MCP, dashboard, and exports disclose provenance, quality, revision, and model version consistently;
- the full repository verifier and live aggregate audit pass.
