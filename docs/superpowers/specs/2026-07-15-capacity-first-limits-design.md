# Capacity-First Limits Intelligence

## Status And Relationship To The V2 Design

This design narrows and corrects the dashboard experience described in `2026-07-14-limits-intelligence-redesign-design.md`. The v2 storage, reconciliation, provenance, freshness, polling, and privacy contracts remain in force. Where the earlier design foregrounds usage-percent reconstruction and a single capacity split, this document supersedes it with a capacity-first history and multiple-change analysis.

## Goal

The Limits page should answer one primary historical question:

> How many estimated local credits have corresponded to one visible percentage point of weekly allowance over time, and when has that relationship changed?

Current upstream percentages remain useful status facts, but usage percentage over time is not the primary analytical chart. The page must not expose internal revision/cache mechanics, unsupported candidate effects, or generic data-volume explanations that contradict the available evidence.

## Diagnosed Problems

The current implementation has enough history to calculate a descriptive weekly capacity, but the promoted percentage forecast fails its validation gate. Describing that state as needing more data is false: model quality, rather than sample count, is the limiting factor.

The current change detector selects one best boundary and returns the selected before/after medians even when the corrected test rejects the change. Those selected descriptive values can look dramatic despite being unsupported. The dashboard compounds the problem by presenting an internal “current revision” recomputation as a primary button.

The four status facts at the top use full-width cards even though they are compact readouts. This consumes most of the first viewport before the user reaches the historical capacity question.

## Product Contract

### Compact Current Status

The top status area is one responsive row with four cells:

1. weekly observed usage and freshness;
2. five-hour observed usage and freshness;
3. weekly reset countdown and expected timestamp;
4. current weekly capacity calibration in `credits / 1%`, with evidence grade.

On narrow viewports the row may wrap to two columns and then one column. Each value retains a visible label, age or evidence detail, and a non-color status indicator. The large reconstructed-use answer band and the four oversized cards are removed.

### Capacity History

The primary chart is titled **Weekly limit capacity over time**. It uses completed, quality-approved weekly reset cycles as its statistical units. Each eligible cycle contributes at most one vote.

The chart contains:

- a light point for each eligible cycle’s `credits_per_percent` value;
- a prominent trailing-eight-cycle median line, emitted after at least four eligible cycles;
- a trailing-eight-cycle interquartile band wherever at least four eligible cycles exist;
- vertical annotations for every statistically supported capacity change;
- a clearly labeled current descriptive calibration.

The default range is eight weeks. Presets include eight weeks, six months, all available history, and custom dates. Granularity is cycle, week, or month. Week and month buckets summarize completed cycles; they never average raw percentages across resets. Zoom and brush remain available.

Extreme observations remain available in the table and chart detail. By default, the visible y-domain uses Tukey’s `1.5 × IQR` fences over the selected range so isolated extremes do not flatten the useful signal. Out-of-domain values render as edge markers, the chart discloses their count, and a **Show full range** control expands the domain. The dashboard never silently drops an outlier.

The chart is weekly-only because a rolling five-hour window includes expiry and decay that make the monotonic weekly credit-per-percent ratio invalid. Five-hour observations remain in the compact current-status row. A five-hour capacity history requires a separately validated rolling-decay model and is outside this change.

### Capacity Summary

Immediately below or beside the chart, a compact summary reports:

- current robust calibration;
- median for the current supported regime;
- completed eligible cycle count;
- price coverage;
- interquartile range;
- latest supported change, if any.

“Descriptive” means the value summarizes local historical evidence. It must not be labeled unavailable merely because a separate percentage forecast failed validation.

### Percentage Forecasts And Model Health

The foregrounded **Personal model**, reconstructed-use history, validated-percentage estimate, and conditional-pace cards are removed from the main workflow. Their validation results may remain under an expandable **Model and data quality** section for diagnostics and API compatibility.

When a diagnostic model is withheld, its explanation names the failed quality gate, such as “did not beat the simple holdout baseline” or “interval coverage was below target.” It never says “more data required” unless sample count is actually the failed gate.

## Multiple Capacity Changes

### Statistical Unit And Eligibility

Only completed weekly cycles with high or medium quality, at least 95% price coverage, no unresolved conflict, and a positive finite capacity participate. Cycles are ordered by completion time. Each cycle contributes one capacity value.

Every supported segment contains at least four eligible cycles. A tested boundary therefore requires four cycles on each side.

### Hierarchical Detection

The detector may return zero, one, or multiple supported boundaries. It uses conservative recursive segmentation:

1. Start with a family-wise alpha budget of `0.05`. Within the current segment, scan every eligible cycle boundary using the v1 detector’s balanced absolute mean-difference statistic: the absolute difference in segment means multiplied by `sqrt(n_left × n_right / n_total)`.
2. Calibrate the selected maximum statistic with exact cycle-block permutation when bounded, otherwise `1,999` deterministic Monte Carlo permutations.
3. Require both a selection-adjusted p-value below the segment’s allocated alpha and an absolute Cliff’s delta of at least `0.474`.
4. Only after a segment rejects its no-change hypothesis may the detector recurse into its left and right child segments.
5. Divide the parent’s alpha budget equally between the children. This hierarchical alpha spending controls family-wise false positives across the discovered tree rather than treating recursive searches as independent tests.
6. Stop when a segment is too small, fails its corrected test, fails quality gates, or has no strong effect.

The response records the alpha assigned and spent at each accepted boundary, the tested segment, selection-adjusted p-value, effect size, uncertainty, detector version, permutation method/count, and deterministic seed when applicable.

Synthetic calibration must cover no-change histories, one change, multiple separated changes, changes in opposite directions, nearby changes that cannot form valid regimes, outliers, missing pricing, conflicts, and large histories. Across at least 1,000 deterministic no-change simulations, the upper bound of the 95% binomial confidence interval for the family-wise false-positive rate must not exceed `0.05`; otherwise the detector does not ship.

This method is intentionally conservative. The dashboard describes detected boundaries as **supported local capacity changes**, not as every change that may have occurred.

### Regimes

Accepted boundaries partition history into chronological capacity regimes. Each regime contains:

- start and end timestamps;
- eligible cycle count;
- robust median credits per percentage point;
- interquartile range;
- price coverage and quality caveats;
- change from the previous regime, when applicable.

A response with no accepted boundary contains one current regime and no candidate before/after effect. Unsupported selected candidates remain internal diagnostics and are not returned in the default dashboard payload.

### Dashboard Presentation

Change analysis runs automatically and idempotently for each allowance source revision. The dashboard does not show a manual “run” or “re-run for current revision” button.

While a new revision is being analyzed, the page shows **Checking capacity history for changes…** and continues displaying the last analysis only when it is explicitly labeled as belonging to the previous data revision. The backend coalesces duplicate requests for the same revision.

When no boundary is supported, the panel says **No reliable capacity change detected** and shows eligible-cycle count plus analysis time. It does not show the best rejected split, before/after medians, or p-value.

When boundaries are supported, the panel becomes a latest-first timeline. Each row states the effective date, direction, magnitude, and regime medians in plain language. Selecting a row focuses the corresponding chart annotation. Technical statistics are available in expandable details.

## Data And API Changes

### Series

`GET /api/allowance/series` retains its existing schema identity and compatibility fields during the v2 compatibility window. It adds a weekly capacity-history section containing bounded, chronological cycle points and bucket summaries:

- cycle identifier or aggregate bucket identifier;
- completed timestamp;
- credits per percentage point;
- rolling robust median;
- rolling lower and upper quartiles;
- quality grade and price coverage;
- outlier-display metadata;
- supported regime and boundary identifiers when analysis is current.

Normal payloads remain aggregate-first and do not expose physical record IDs. Source-row provenance remains opt-in through the existing local evidence surface.

### Analysis

The analysis payload replaces singular `selected_boundary` and `effect_size` as the default contract with:

- `status`;
- `boundaries[]`;
- `regimes[]`;
- `eligible_cycle_count`;
- `familywise_alpha`;
- detector and permutation metadata;
- quality caveats;
- source revision and generation time.

Compatibility fields may remain for one release and map only when exactly one boundary is supported. With zero or multiple boundaries they are null and marked deprecated. Unsupported candidates are available only in an explicit diagnostic payload, never the default dashboard/MCP result.

### Polling And MCP

Status remains the inexpensive polling entry point. A changed allowance revision invalidates capacity series and analysis. The dashboard automatically starts or reuses the revision-keyed analysis job. MCP callers receive the same revision, analysis state, regimes, boundaries, and recommended polling delay; they do not need to understand dashboard cache revisions.

Default MCP summaries lead with current weekly capacity, current regime, and supported changes. Current observed weekly/five-hour percentages remain context.

## Empty, Partial, And Failure States

- No accepted weekly observations: show current status as empty and explain how to ingest allowance snapshots.
- Observations but no completed eligible cycles: show observed current status and “Capacity history begins after a quality-approved weekly cycle completes.”
- Descriptive capacity but no supported change: show the capacity chart and one regime; do not call the model unavailable.
- Analysis pending: preserve the chart and label boundary analysis pending.
- Analysis failed: preserve current status and capacity history, show a retryable background-analysis error, and avoid a full-page failure.
- Five-hour selected from legacy URLs: retain five-hour status context and route the historical chart to weekly capacity with an explanation that rolling-window capacity is not inferred.

## Accessibility And Responsive Behavior

The compact status row uses semantic descriptions and preserves logical reading order when wrapped. Chart annotations are duplicated in the regime timeline and exact-value table. Keyboard users can move between supported changes and focus the matching chart point. Screen-reader summaries report current capacity, range, eligible cycles, number of supported changes, and clipped-outlier count. Status and analysis completion updates use restrained live regions. No meaning relies on color alone.

## Testing Strategy

Implementation follows red-green-refactor.

Backend tests cover capacity-point construction, bounded chronological series, robust rolling summaries, outlier disclosure, zero/one/multiple supported changes, hierarchical alpha allocation, deterministic results, family-wise false-positive simulations, regime construction, quality exclusions, revision-keyed job coalescing, compatibility fields, and normal/local provenance.

Frontend tests cover the compact status row, credits-per-percent chart labels and units, weekly-only capacity explanation, responsive wrapping, unavailable-state explanations, automatic analysis startup, pending/error states, suppression of rejected split statistics, multiple-change timeline ordering, chart/timeline selection, accessibility summaries, and exact-value table output.

Contract tests verify API/MCP parity, bounded payloads, revision polling, deprecated singular fields, and aggregate-first defaults. The final live audit prints aggregates only and confirms current capacity, cycle counts, price coverage, supported-boundary count, and copied-row exclusion without exposing local record content.

## Rollout And Compatibility

The capacity-first dashboard may ship within the existing v2 endpoint family. Existing percentage-series fields and singular analysis fields remain for one documented compatibility window, but the dashboard and default MCP summaries stop consuming them immediately. Generated dashboard assets are rebuilt from the React source.

Documentation is updated to define credits per percentage point as a personal local proxy, explain why five-hour rolling limits require a different model, describe multiple-change false-positive control, and distinguish descriptive capacity from validated prediction.

## Acceptance Criteria

The change is complete when:

- the first viewport contains one compact current-status row and a weekly credits-per-percent history;
- usage percentage over time and unavailable forecast cards are no longer the primary workflow;
- descriptive capacity is usable whenever eligible completed cycles exist;
- every unavailable diagnostic names its actual failed gate;
- the detector can return zero, one, or multiple supported boundaries with controlled family-wise false positives;
- rejected candidate splits never appear as meaningful before/after values in default UI/API/MCP results;
- supported boundaries produce chronological regimes and chart annotations;
- analysis is automatic and revision-keyed, with no user-facing revision button;
- current status and capacity history remain usable while analysis is pending or failed;
- normal payloads remain canonical and aggregate-first, with physical provenance opt-in;
- focused statistical, API, MCP, frontend, accessibility, governance, and full repository gates pass.
