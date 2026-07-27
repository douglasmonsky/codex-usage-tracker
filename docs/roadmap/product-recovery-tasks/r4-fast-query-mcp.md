# R4 — Build Persisted Rollups And Fast MCP/API Paths

## Objective

Make routine agent and Console questions read small generation-scoped rollups
or bounded indexes instead of scanning hundreds of thousands of foundational
facts.

## Depends On

R2.

## Owned Areas

- rollup algorithms, frozen updater interface, and generation publication
  validation;
- query catalog, plans, contracts, and service;
- application-level generation/request result cache;
- MCP, HTTP, and CLI query adapters;
- common-query performance tests;
- response-size and selector contracts.

R4 does not edit ingestion-owned files or frontend assets.

## Contract Added First

Add failing contracts for:

- global Live summary;
- top threads;
- top calls;
- Threads and Calls listings;
- model × effort;
- hourly and daily token bands;
- allowance interval reads;
- one-thread evidence first page;
- stable generation/request cache reuse.
- coverage envelopes and fail-closed all-history behavior on partial
  generations.

Each contract asserts a scanned-row or query-plan budget in addition to wall
time and result correctness.

## Required Behavior

- Keep exactly six MCP tools.
- Preserve bounded `usage_query` for composition.
- Provide curated query plans inside the existing tool contract.
- Preserve typed extension points for the human labels, costs, and credits that
  R5 will populate; R4 does not claim those values as an acceptance gate.
- Cache normalized responses by active generation and request hash.
- Include the coverage revision in cache keys and return the active preset,
  cutoff, completeness, and hydrated/deferred counts in status/query
  envelopes.
- Extend `usage_refresh` within the existing six-tool surface to accept
  `recent_30d`, `recent_90d`, or `complete`. Do not add a hydration tool.
- Reject all-history queries on partial generations unless the request
  explicitly sets `allow_partial=true`; label accepted results as partial.
- Invalidate only when a new generation publishes or relevant configuration
  changes.
- Never start refresh from query execution.
- Never start deferred-history hydration from query, evidence, or Console
  navigation.
- Batch compatible questions against one committed generation.
- Return one structured representation; do not duplicate the payload in a
  second textual form.
- Keep selectors concise and resolve evidence only when requested.

## Common Warm Path

“List my top threads by usage” must require:

1. one fresh-task tool call;
2. one bounded query batch;
3. no refresh when the generation is current;
4. no polling;
5. four token classes and stable selectors.

Tracker time must be ≤1 second, stretch ≤500 ms.

R5 adds human labels and cost/credit coverage to this same bounded path. R7
owns the final end-to-end gate that requires those populated values.

## Parallel Execution

R4 may run in parallel with R3 and the R7 harness from the R2 schema SHA.

R4 exclusively owns query, application, MCP, and query-performance files.
R3 owns ingest and writer. R7 may invoke public interfaces but may not patch
them. Early R6 frontend prototyping may use frozen fixtures only after R4
publishes its response contract; it cannot modify generated assets concurrently
with R4 interface changes.

R4 first publishes a tested rollup-updater interface and fixture checkpoint.
R4 owns that updater module; R3 later owns the ingestion call site that invokes
it inside the fact-writing transaction. Neither lane edits the other's files,
and the coordinator validates atomic fact-and-rollup publication after
integration.

One R4 implementation owner should integrate the updater and query reads to
avoid cache-coherence races. Read-only SQL-plan and response-budget audits may
run as parallel subagents.

## Validation

- exact query oracle;
- generation consistency;
- result-cache invalidation;
- response-byte ceilings;
- evidence selector resolution;
- SQL plan and scanned-row budgets;
- latency distributions on production-shaped synthetic data;
- MCP/HTTP/CLI parity;
- concurrent refresh read behavior;
- no implicit refresh assertion;
- broader interface and release gates.

## Acceptance

- All common warm routes pass required latency.
- Top threads is one bounded tool call.
- No common landing query scans all calls.
- Cache reuse is observable and generation-safe.
- Response payloads remain concise.
- R5 receives frozen extension points for labels, costs, and credits; R6
  receives the core bounded-query contract after R5 populates those fields.

## Handoff

Record every curated plan, cache key, invalidation event, scan budget, and
latency in the ledger. R5 extends values without changing the six-tool surface.
