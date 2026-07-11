# Compression Lab Design

Status: approved in design review on 2026-07-11

## Summary

Build a measurement-first Compression Lab above the existing Codex Usage Tracker store and report APIs. The lab will identify context and workflow waste, estimate avoidable tokens for every candidate, prevent duplicate attribution across overlapping patterns, and give the MCP a compact path from overview to evidence to intervention simulation.

The first milestone includes a detector, persistent analysis cache, bounded evidence drilldown, and overlap-aware simulator. Persisted before/after intervention experiments are deferred until the detector metrics stabilize.

## Product Position

- Local-first and unofficial.
- Research-oriented, but explicit that estimates are heuristic rather than an OpenAI ledger.
- Automatic use of the local content index is allowed for analysis.
- Primary outputs contain structured summaries and evidence handles, not raw excerpts.
- Bounded unredacted local excerpts are available only through explicit detail requests.
- The lab itself must minimize MCP context use through compact defaults and drilldown.

## Goals

1. Produce a defensible inventory of compression opportunities across calls, threads, files, commands, tool output, and cache behavior.
2. Separate measured exposure from estimated avoidable tokens.
3. Return a low, likely, and high savings estimate for every candidate.
4. Prevent the same call and token component from being claimed repeatedly by overlapping findings.
5. Make a cold full-history run asynchronous, observable, and persistently cached.
6. Make warm profile, candidate, and detail queries fast enough for normal MCP iteration.
7. Give the skill a concise investigation path with concrete interventions and verification steps.
8. Preserve existing MCP tools and stable payload contracts while routing broad waste questions to the new lab.

## Non-Goals

- Reading or reproducing OpenAI's internal usage ledger.
- Declaring whether a model's reasoning was valuable.
- Persisting intervention experiments in the first milestone.
- Semantic effort-mismatch judgments in the first detector set.
- Replacing specialized diagnostics that remain useful as evidence providers.
- Returning unbounded transcripts, commands, tool output, or file content.

## Terminology

- `observed_exposure_tokens`: unique measured tokens associated with a pattern. Exposure is not automatically waste.
- `gross_estimated_savings`: one candidate's heuristic savings before overlap adjustment.
- `adjusted_estimated_savings`: a candidate's bounded savings after competing claims are allocated.
- `portfolio_estimated_savings`: the sum of adjusted candidate savings for a run.
- `eligible_tokens`: token components that a detector is permitted to claim.
- `candidate`: one deterministic compression opportunity with evidence, an estimator, and an intervention.
- `run`: a reproducible analysis for one source revision, scope, and detector/estimator configuration.

## Architecture

The Compression Lab is an application/report layer. MCP functions remain thin wrappers.

```text
SQLite usage and content evidence
  -> normalized observations
  -> pattern detectors
  -> attribution ledger
  -> versioned savings estimators
  -> overlap allocator
  -> cached compression run
  -> MCP/API profile, candidate, detail, and simulation payloads
```

### Components

1. **Observation adapters**
   - Read existing aggregate calls, content fragments, tool calls, command runs, file events, compaction events, and source coverage.
   - Normalize each source into immutable observations keyed by record, thread, event, and token component.
   - Never assign a whole call's tokens once per matching event.

2. **Pattern detectors**
   - Receive one shared scoped evidence snapshot.
   - Emit candidate drafts with unique record IDs, eligible component claims, evidence handles, and estimator inputs.
   - Do not calculate portfolio totals.

3. **Attribution ledger**
   - Deduplicates observations and candidate record membership.
   - Tracks per-record capacities for cached input, uncached input, output, reasoning output, and directly estimated tool/content fragments.
   - Rejects claims outside the detector's eligible components.

4. **Savings estimator registry**
   - Selects direct, matched-baseline, or fallback estimation for each candidate.
   - Stores estimator name, version, assumptions, inputs, and low/likely/high outputs.

5. **Overlap allocator**
   - Allocates competing candidate claims against each record/component capacity.
   - Produces adjusted candidate estimates and bounded portfolio totals.

6. **Run repository and job service**
   - Persists reproducible runs and candidates in SQLite.
   - Deduplicates identical active jobs.
   - Reuses exact valid runs and invalidates stale ones explicitly.

7. **Payload builders**
   - Enforce schemas, response budgets, pagination, disclosure fields, and stable terminology.

## Candidate Contract

Each internal candidate contains:

```text
candidate_id
run_id
family
pattern
scope_key
first_seen
last_seen
record_ids
thread_keys
observation_count
observed_exposure_by_component
eligible_claims_by_record_and_component
gross_estimated_savings {low, likely, high}
adjusted_estimated_savings {low, likely, high}
confidence {grade, score, reasons}
estimator {name, version, tier, assumptions, inputs}
evidence_handles
overlapping_candidate_ids
intervention
verification
data_quality_warnings
```

Candidate IDs are deterministic hashes of the source revision, scope hash, family, stable pattern key, detector version, and estimator version. IDs are stable only while those inputs remain identical.

## Attribution Rules

1. Call-level exposure is summed over unique `record_id` values.
2. Event-level estimates use directly estimated fragment or output tokens when available.
3. Repeated file and command events never each inherit the containing call's complete token total.
4. Each detector declares eligible token components.
5. A candidate's gross estimate cannot exceed its eligible exposure.
6. For each record, component, and estimate bound, competing claims are proportionally scaled to the available capacity.
7. Allocation is deterministic; `candidate_id` breaks numerical ties.
8. Portfolio estimates are sums of adjusted estimates and cannot exceed unique eligible exposure.
9. Cached and uncached input remain separate because their cost and credit implications differ.
10. Cost and Codex-credit estimates are derived after token allocation and retain the pricing/rate confidence of their source rows.

## Estimator Hierarchy

Every candidate receives an estimate. The selected tier is disclosed.

### Tier A: Direct Attribution

Use measured or locally estimated fragment/tool-output tokens. This is the preferred tier for repeated reads, command output, validation output, and duplicated tool output.

### Tier B: Local Matched Baseline

Match comparable calls by model, effort, task family, context state, and nearby time where coverage permits.

- Low savings: exposure above the matched 75th percentile.
- Likely savings: exposure above the matched median.
- High savings: exposure above the matched 25th percentile.
- Negative estimates clamp to zero.
- Baseline sample size and similarity are included in confidence reasons.

### Tier C: Versioned Heuristic Fallback

The initial `compression-estimator-v1` defaults are deliberately ranges:

| Family | Eligible exposure | Low | Likely | High |
| --- | --- | ---: | ---: | ---: |
| Stale context | Excess input above the family target | 10% | 30% | 55% |
| File rediscovery | Repeated fragment tokens after the first unchanged read | 50% | 75% | 90% |
| Shell retry churn | Repeated command/output tokens after two attempts | 25% | 50% | 75% |
| Validation repetition | Redundant validation output and continuation overhead | 40% | 70% | 90% |
| Tool-output bloat | Output above the configured retained-output target | 20% | 50% | 75% |
| Cache-break/resume | Uncached input above the nearby expected baseline | 25% | 50% | 75% |

These values live in one versioned estimator policy module, not scattered through detectors. Changing a value increments the estimator version and invalidates affected cached runs.

## First Detector Set

### 1. Stale-Context Continuation

Signals:

- high context-window share;
- very low output share;
- low tool/file/command activity;
- repeated continuation in the same thread;
- nearby smaller-context calls when available.

Eligible components: cached and uncached input above the selected baseline. Output and reasoning tokens are evidence, not claimable savings.

### 2. Repeated File Rediscovery

Signals:

- same normalized file identity or path hash;
- unchanged source/content identity where available;
- repeated reads in one thread or investigation window;
- no intervening write that would justify rereading.

Eligible components: repeated content-fragment token estimates after the first necessary read. Whole-call totals are exposure context only.

### 3. Shell Retry Churn

Signals:

- adjacent repeated command family or normalized label;
- failure loops;
- no intervening edit or narrowing action;
- repeated broad probes.

Eligible components: directly estimated repeated command/tool output and bounded continuation overhead after two attempts.

### 4. Validation Repetition

Signals:

- same test/build/status family repeated;
- no relevant source modification between runs;
- duplicate broad gates where a focused gate already passed;
- repeated failure with unchanged inputs.

Eligible components: redundant validation output and bounded continuation overhead.

### 5. Tool-Output Bloat

Signals:

- output above a versioned size threshold;
- duplicate fragment hashes;
- immediate narrower retries;
- little downstream reuse or reference evidence.

Eligible components: output above the retained-output target. Lack of downstream references lowers confidence rather than proving uselessness.

### 6. Cache-Break And Resume Overhead

Signals:

- uncached-input jump after a time gap, resume, compaction, or thread transition;
- cache ratio materially worse than nearby comparable calls;
- context rehydration or repeated content evidence.

Eligible components: uncached input above the nearby or fallback expected baseline.

## Persistent Run Cache

### Tables

`compression_runs`

- run ID and status;
- source revision and scope hash;
- detector and estimator versions;
- filters and coverage JSON;
- progress, stage, timing, error summary;
- aggregate profile JSON;
- created, started, completed, and last-accessed timestamps.

`compression_candidates`

- candidate ID and run ID;
- family, pattern, rank, confidence;
- observed exposure and gross/adjusted estimate JSON;
- estimator, intervention, verification, and warning JSON;
- compact evidence summary.

`compression_candidate_records`

- candidate ID and record ID;
- component capacities and claims;
- evidence role and trace handle.

No raw snippets are copied into these tables.

### Cache Key

A cached run is valid only when all of these match:

- source/index revision;
- normalized filters and archived scope;
- detector set and versions;
- estimator policy version;
- compression schema version.

### Incremental Behavior

- Refresh records which source files and threads changed.
- Recompute detector inputs only for new/changed records and affected threads when versions are unchanged.
- Rebuild affected candidates and then rerun the comparatively small global overlap allocation.
- Full rebuild remains available for policy/schema changes and explicit replacement.

## Async Lifecycle

`usage_compression_start`

- Starts or reuses an identical valid/active run.
- Arguments: standard scope filters, archived scope, `refresh`, and optional detector-family filters.
- Returns immediately with run ID, status, cache decision, and next poll arguments.

`usage_compression_status`

- Arguments: run ID and optional result inclusion.
- Returns monotonic percent, stage, current detector, completed/total detectors, records examined, candidate count, cache reuse, timing, and errors.

`usage_compression_profile`

- Arguments: run ID, or filters identifying the newest valid completed run.
- Returns the compact completed profile. It does not silently launch a long blocking analysis.

## Query And Simulation Tools

`usage_compression_candidates`

- Filters: run ID, family, confidence, model, thread, time range, minimum exposure, minimum likely savings.
- Sorts: adjusted likely savings (default), confidence, exposure, recency.
- Supports `limit=0`/`None` as documented unbounded local retrieval, but MCP defaults remain bounded and pageable.
- An explicit unbounded request may exceed the default candidate-page size target; it still excludes nested evidence.
- Returns no nested evidence rows.

`usage_compression_candidate_detail`

- Arguments: candidate ID, evidence mode, evidence limit, maximum excerpt characters.
- Evidence modes: `handles` (default), `summaries`, and `excerpts`.
- Returns calculation trace, assumptions, record/component claims, overlaps, intervention, and verification.

`usage_compression_simulate`

- Arguments: run ID plus candidate IDs and/or intervention families.
- Returns selected gross estimates, overlap-adjusted portfolio estimates, affected components, excluded/unknown candidates, assumptions, and a verification plan.
- Does not persist an intervention experiment in this milestone.

## Common Payload Envelope

All Compression Lab payloads include:

- schema and estimator versions;
- run ID, source revision, and scope;
- filters and archived state;
- evidence/parser coverage;
- pagination and truncation state;
- computation duration and cache hit;
- `content_mode`, `includes_indexed_content`, and `includes_raw_fragments`;
- warnings and caveats;
- exact recommended next-tool arguments.

## Response Budgets

- Status: target 4 KB.
- Profile: target 8 KB.
- Candidate page: target 16 KB.
- Candidate detail: target 24 KB.
- Excerpts are separately bounded by count and characters.
- Full evidence uses pagination rather than an unbounded nested response.

The profile contains only the direct answer, observed exposure, overlap-adjusted range, confidence/coverage, top five candidate IDs, primary caveats, and next calls.

## Skill Behavior

For broad token-waste or context-compression questions, the skill will:

1. Call `usage_compression_start` for the requested scope.
2. Poll `usage_compression_status` until complete or failed.
3. Read `usage_compression_profile`.
4. Inspect only the strongest candidate details needed to answer the question.
5. Optionally call `usage_compression_simulate` for proposed interventions.
6. Return evidence, heuristic range, assumptions, intervention, and verification.
7. Stop when sufficient evidence exists instead of expanding every candidate.

Existing `usage_investigate(goal="token_waste")` and `usage_action_brief` become concise routers to the newest valid compression profile. Specialized endpoints remain compatible and continue to serve evidence-level use cases.

## Error And Partial-Evidence Behavior

- A detector failure does not discard successful detector output.
- The run status becomes `completed_with_warnings` when usable partial evidence exists.
- Failed families are named with structured errors and excluded exposure.
- Missing parser/content coverage lowers confidence and appears in profile warnings.
- Unknown candidate IDs return a structured not-found result with the required source revision/run ID.
- Stale run requests return explicit stale metadata and the exact arguments for starting a replacement.
- Identical active jobs deduplicate rather than running twice.

## Validation

Blocking invariants:

- `0 <= low <= likely <= high`;
- adjusted estimates do not exceed gross estimates;
- gross estimates do not exceed eligible exposure;
- portfolio estimates do not exceed unique eligible token capacity;
- a record/component is not fully attributed more than once;
- candidate IDs are deterministic for identical inputs;
- cache invalidates for source, scope, schema, detector, or estimator changes;
- progress is monotonic;
- identical jobs deduplicate;
- default payloads stay within response budgets and omit raw excerpts.

Test matrix:

- one synthetic fixture per detector with manually calculated ranges;
- overlapping detector scenarios;
- duplicate event/session inputs;
- missing content and parser drift;
- archived and time-window scopes;
- zero-evidence and partial-failure runs;
- cold, warm, stale, and incrementally updated caches;
- MCP/API contract snapshots;
- skill-routing fixtures;
- real local dogfood using aggregate summaries only in committed evidence.

Performance targets on data near the maintainer's current scale:

- uncached full run under 60 seconds;
- warm profile and candidate queries under 500 ms;
- candidate detail under 1 second;
- immediate job/progress response rather than a blocking MCP timeout.

## Rollout

1. Attribution kernel, contracts, and cache schema.
2. Six detectors and versioned estimators.
3. Async MCP lifecycle, profile, candidates, and detail.
4. Overlap-aware simulator.
5. Skill/plugin routing, documentation, dogfood evaluation, and compatibility cleanup.

Each phase is a focused PR from current `main`, with source, tests, docs, and bundled plugin/skill copies updated together. Existing endpoints support shadow comparison until the new profile is validated.

## Deferred Work

- Persisted before/after intervention experiments.
- Calibrating heuristic ranges from opt-in shared aggregate evidence.
- Semantic task-value and effort-mismatch models.
- Dashboard Compression Lab surfaces.
- Automated intervention execution.
