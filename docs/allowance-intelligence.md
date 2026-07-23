# Allowance Intelligence

Allowance Intelligence is a local, aggregate-only workflow for understanding the
weekly and 5-hour percentages observed in Codex logs. It is not an OpenAI ledger,
does not know the account's hidden allowance denominator, and cannot see usage
from other agentic surfaces.

The v2 workflow is deliberately conservative: current observations are facts;
reconstructed values, personal calibration, forecasts, and change claims remain
separate estimates with visible quality gates.

## Truth Layers

The dashboard and API keep five layers distinct:

1. **Observed allowance** is the percentage and reset metadata written in local
   `token_count.rate_limits` events or copied into the optional local allowance
   configuration.
2. **Canonical usage** is token and locally estimated credit activity after
   high-confidence copied-clone rows are excluded. This is the default input to
   reports, the dashboard, and MCP.
3. **Reconstructed usage** estimates movement between sparse observations using
   only calibration data available before each interval ended.
4. **Validated forecast** is shown numerically only after time-ordered holdout
   testing beats the relevant simple baselines and interval coverage is adequate.
5. **Physical provenance** preserves source rows and record identifiers for local
   debugging. It is opt-in and never changes billable totals.

Copied clone rows excluded from canonical totals are always disclosed through
`quality.copied_rows_excluded` or `copied_rows_excluded`. Similar token counts by
themselves never cause exclusion.

## Reset And Cohort Semantics

Allowance observations are grouped by window kind, limit identity, plan metadata,
and normalized reset time. Reset timestamps within 60 seconds are treated as the
same reset boundary. A reset starts a new cycle and produces a chart break; the
model never interpolates or fits a continuous line across it.

The normal Codex cohort is selected independently for weekly and 5-hour windows.
Conflicting simultaneous observations, ambiguous cohort changes, reversals, gaps,
and reset uncertainty remain visible as conflicts or censored intervals. They are
not silently converted into positive usage movement.

Weekly data is the primary long-range signal. The 5-hour value is useful current
context, but its rolling-window behavior makes it unsuitable as the primary
capacity or regime-change claim.

## Freshness

- Weekly and 5-hour observations are `fresh` through five minutes.
- Weekly observations are `aging` after five minutes through six hours.
- Five-hour observations are `aging` after five minutes through 15 minutes.
- Older observations are `stale`.
- Passing the reported reset time makes an older observation stale immediately,
  even when its age would otherwise be acceptable.

The status endpoint is constant size. Poll it every 30 seconds while data is fresh
or aging and every 60 seconds while it is stale, partial, empty, or unchanged.
Hidden browser tabs stop polling. Transient failures back off exponentially to a
maximum of five minutes.

## Personal Calibration And Forecasts

`credits_per_percent` is a personal, empirical calibration derived from local
history. A value such as `105.11` means the user's eligible completed reset windows
imply approximately 105.11 locally estimated credits per one observed percentage
point. It is not an official conversion, a hardcoded product rule, or the hidden
allowance denominator.

Calibration uses completed quality-approved weekly reset identities as the unit of
evidence. Interleaved observations carrying the same canonical reset timestamp are
coalesced into one reset window, so concurrent sessions cannot fragment one window
into many low-movement pseudo-cycles. Weights include recency, interval quality,
and price coverage, with each reset window's influence capped. At least two
completed approved reset windows are required before the
capacity can move beyond a descriptive result.

Each completed reset window also retains the explicitly logged subscription
`plan_type`. Capacity points and trailing statistics are separated by plan, so a
Pro Lite window cannot pull the Pro line up or down. Missing plan metadata is
reported as `unknown`, and a reset window containing multiple explicit plans is
reported as `mixed`; neither is guessed from its capacity value.

Each reconstructed interval sees only cycles completed before that interval ended.
Forecast validation is walk-forward and reports sample size, MAE, RMSE, empirical
50/80/95% interval coverage, and simple baselines. A numerical forecast is
`validated` only when the time-ordered holdout beats every relevant baseline and
all advertised interval coverages meet the minimum gate. A failed forecast is
reported with the specific failed validation gate; it does not make descriptive
capacity unavailable. The capacity-first Limits page does not foreground the
percentage forecast or conditional pace.

Missing price coverage is explicit. Change detection requires at least 95% priced
credit coverage for each eligible reset window. Forecast and calibration payloads
report their own coverage gaps and never substitute token-count similarity for
pricing. The Limits chart keeps an open methodology panel beside the evidence: it
states the ratio formula, explains every mark and filter, shows the observed plan
color key, and reports the current eligible, excluded, tested, and supported
counts rather than asking users to infer the method from the visualization.

## Change Analysis

Allowance change analysis is a persisted, revision-keyed background job. It tests
weekly cycle capacities with a hierarchical maximum-statistic cycle-block
permutation detector. The result is one of:

- `insufficient_evidence`
- `no_supported_change`
- `supported_changes`

A supported parent boundary may split the history into child segments. Each child
receives half its parent's alpha budget, so the discovered tree controls
family-wise false positives rather than treating recursive searches as independent
tests. Histories are first split at every explicitly observed subscription-plan
transition, and candidate boundaries are tested only within those continuous plan
segments. The family-wise alpha budget is divided across analyzable plan segments,
so a Pro Lite-to-Pro transition is visible provenance but can never itself become a
capacity-change claim. A boundary must also have an absolute Cliff's delta of at least `0.474`.
Exact permutations are used where bounded; otherwise the detector uses `1,999`
deterministic Monte Carlo permutations and requires the upper 95% Monte Carlo
uncertainty bound to clear the allocated alpha—not merely the point estimate.

A raw best split is never presented as significant. Conflict-heavy cycles,
insufficient samples, low price coverage, weak effects, or selection-corrected
uncertainty block strong claims. Results expose zero, one, or multiple supported
`boundaries` and the resulting `regimes`. Deprecated singular fields are populated
only when exactly one boundary is supported. Rejected candidate p-values and
before/after medians are omitted from default dashboard and MCP results.

The dashboard starts analysis automatically when a new semantic revision lacks a
result. MCP callers start or reuse the same job, poll every 500 milliseconds only
while it is pending, queued, or running, then reload the persisted result.
Identical source/model/rate-card keys reuse the same snapshot or in-flight job.

The release gate simulates 1,000 deterministic no-change histories across
Gaussian, skewed, outlier-contaminated, and heteroskedastic families. The detector
ships only when the upper 95% Wilson bound for its family-wise false-positive rate
is at most `0.05`.

## Dashboard Workflow

Open `Limits` from the live localhost dashboard to see:

- one compact row for weekly observed use, 5-hour observed context, weekly reset,
  and personal weekly capacity;
- weekly `credits / 1%` history with completed-cycle points, an eight-cycle rolling
  median and interquartile band, robust outlier display, and every supported change;
- 8-week, 6-month, all available aggregate-cycle, or bounded custom ranges;
- cycle, week, or month granularity;
- an automatic newest-first capacity-change timeline that suppresses rejected
  candidate statistics; and
- latest-first evidence in 50-row pages.

Physical source links are hidden by default. Enable **Show physical source links**
only for local provenance/debugging. Static dashboards show an aggregate fallback
because they cannot poll the v2 localhost services or analysis jobs.

## HTTP And MCP Contracts

The HTTP v2 endpoints remain operation-specific. The default MCP surface
consolidates them behind one bounded tool:

| Purpose | HTTP | MCP |
| --- | --- | --- |
| Poll current state | `GET /api/allowance/status` | `usage_allowance(operation="status")` |
| Query a finite timeline | `GET /api/allowance/series` | `usage_allowance(operation="series", window="weekly", range="8w")` |
| Page latest-first evidence | `GET /api/allowance/evidence` | `usage_allowance(operation="evidence", window="weekly", range="8w", limit=50)` |
| Read/start analysis | `GET`/`POST /api/allowance/analysis` | `usage_allowance(operation="analysis", execution="auto")` |
| Poll analysis job | `GET /api/allowance/analysis/jobs/{job_id}` | `usage_job_status(job_id, include_result=True)` |

The consolidated MCP tool accepts only the finite presets `24h`, `7d`, `8w`,
and `6m`; it rejects `all`. Its evidence limits are 1–200 and default to 50.
Existing HTTP and individual v2 compatibility surfaces retain their documented
bounded custom-range and aggregate-cycle behavior.

Consolidated results are aggregate-first and each successful operation includes
a bounded Limits v2 dashboard target. The individual v2 evidence tool retains its
explicit local-provenance opt-in. Full strict evidence export remains the offline
`usage_allowance_export(...)` compatibility workflow.

See [CLI, MCP, and Dashboard JSON Schemas](cli-json-schemas.md) for synthetic v2
payloads and [MCP And Codex Skills](mcp.md) for polling examples.

## Compatibility

`usage_allowance_history`, `usage_allowance_diagnostics`, and
`usage_allowance_export` remain available for compatibility and explicit offline
diagnostics. The individual `usage_allowance_status`, `usage_allowance_series`,
`usage_allowance_evidence`, `usage_allowance_analysis`, and
`usage_allowance_analysis_status` tools remain full-profile compatibility tools
through 0.24. New plugin and MCP workflows should use `usage_allowance` and generic
`usage_job_status`; interactive paths never use `limit=0` or `range="all"`.

## Privacy

Normal v2 payloads are aggregate-first and never include prompts, assistant text,
tool output, command output, or indexed transcript fragments. Strict mode also
removes stable local identifiers. Local physical provenance is a deliberate,
bounded opt-in for the owner of the local database.

This project is unofficial, independent, and local-first. Its estimates are tools
for personal investigation, not statements about OpenAI's internal billing or
allowance systems.
