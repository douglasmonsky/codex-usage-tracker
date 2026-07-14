# Dashboard Query Pipeline Refactor Roadmap

Status: Proposed  
Tracking issue: [#244](https://github.com/douglasmonsky/codex-usage-tracker/issues/244)  
Scope: Local dashboard API, persisted analytical facts, async report jobs, and frontend query orchestration

## Summary

The dashboard currently combines two generations of data access:

- indexed SQLite queries that return bounded aggregate data;
- report builders that load large call sets into Python, annotate them, sort them,
  and only then apply the requested result limit.

That split is visible at product scale. On a local database with 404,176 calls,
the all-history summary endpoint completed in roughly 1-2 seconds while the
all-history recommendations endpoint took roughly 47 seconds. The frontend
also bundled those requests into one query, which hid the completed summary,
made progress appear stuck, and discarded useful work when navigation
cancelled the bundle.

The first UI repair is tracked in #243. This roadmap addresses the underlying
query architecture. It is a route-by-route refactor, not a server rewrite.
SQLite remains canonical, existing public schemas remain compatible, and heavy
analyses use the Compression Lab style of asynchronous jobs with progress and
reusable results.

## Goals

1. Make normal dashboard navigation responsive on databases with hundreds of
   thousands of calls.
2. Ensure work proportional to result size whenever the endpoint contract
   allows it.
3. Persist reusable analytical facts during refresh instead of recomputing
   stable classifications on every request.
4. Separate interactive reads from heavy analytical jobs.
5. Give each frontend module an independent query, cancellation lifecycle,
   cache identity, progress state, and error boundary.
6. Preserve aggregate-only defaults and current response schemas throughout the
   migration.
7. Add performance budgets that prevent full-history scans from returning
   unnoticed.

## Non-Goals

- Replacing SQLite.
- Introducing GraphQL.
- Replacing the Python HTTP server framework solely for performance.
- Rewriting all report builders at once.
- Changing recommendation semantics while moving their execution path.
- Combining Compression Lab estimates with legacy recommendation scores.
- Exposing raw prompts, tool output, file paths, or indexed content through
  normal dashboard endpoints.
- Making mobile layout a primary optimization target.

## Execution Ledger

| Slice | Status | Tracking | Completion evidence |
| --- | --- | --- | --- |
| Loading and cancellation repair | Merged | #243 / #245 / `39fdcea` | Independent module cache/progress and real-data navigation QA |
| PR 0: Measurement and route inventory | Merged | #244 / #246 / `1c4685b` | Route inventory, benchmark artifact, and agent-perf run `20260713T231301Z-4a032512` |
| PR 1A: Derived-fact refresh hook | Merged | #244 / #247 / `a5681ba` | Transactional full/append callback coverage and 807-test CI matrix |
| PR 1B: Recommendation fact materialization | Merged | #244 / #248 / `f1dfc22` | Schema v20, parity/incremental/backfill tests, and agent-perf run `20260713T234304Z-bade89ff` |
| PR 1C: Product refresh wiring | Merged | #244 / #249 / `3e569c6` | CLI/server wiring, architecture decision, and 38 focused refresh-path tests |
| PR 2A: Indexed recommendations compatibility | Merged | #244 / #250 / `378a2d1` | Exact payload parity, freshness fallback, and public route/CLI/MCP wiring |
| PR 2B: Bounded recommendation hydration | Merged | #244 / #251 / `d9085e6` | 400k legacy 29.96 s; indexed median 135 ms / p95 151 ms; baseline agent-perf `20260714T011721Z-58ac3b4a` |
| PR 3A: Core frontend query registry | Merged | #244 / #252 / `3da6b29` | Central source/scope identity, data-class policy, module-state, coalescing, and focused lifecycle tests |
| PR 3B1: Shared module progress | Merged | #244 / #253 / `382d77f` | Updating-vs-loading state, Overview background-refresh coverage, and deterministic endpoint-cache tests |
| PR 3B2: Shell source identity | Merged | #244 / #254 / `d8aa426` | Stable credential-free source propagation for Overview, Calls, and Threads; same-route navigation preserves local state |
| PR 3B3: Cache and Reports migration | Merged | #244 / #255 / `bd1214c` | Shared source-aware policies, segmented module progress, request cancellation, and desktop return-navigation coverage |
| PR 3B4: Investigator migration | Merged | #244 / #256 / `4eb43a7` | Credential-free keys, source-revision invalidation, request cancellation, eleven-module progress, and desktop return-navigation coverage |
| PR 3C: Diagnostics query migration | Merged | #244 / #257 / `7d2306c` | Source-aware facts and snapshot queries, paginated evidence calls, thirteen-module progress, cancellation, and desktop interrupted-work retry coverage |
| PR 4A: Diagnostic refresh jobs | In review | #244 / #258 / `22ddfe8c` | Shared async analysis lifecycle, persisted-result reload, measurable 10-unit progress, and observer-safe polling |
| PR 4: Heavy-route job migration | Pending | #244 | Branch, PR, async progress/cache tests |
| PR 5: Query and cache hardening | Pending | #244 | Branch, PR, query plans and warm/cold budgets |
| PR 6: Cleanup and enforcement | Pending | #244 | Branch, PR, CI ratchets and final route audit |

Update this table in the same PR that completes each slice. A slice is complete
only after its acceptance checks pass and the PR is merged to `main`.

## Measured Baseline

The initial real-data trace used a local all-history scope with 404,176 calls:

| Surface | Current path | Observed behavior |
| --- | --- | --- |
| Summary | SQL-backed aggregate query | About 1-2 seconds |
| Recommendations | Load, annotate, filter, and sort in Python | About 47 seconds |
| Investigator diagnostics | Mostly persisted diagnostic endpoints | Commonly 1-2 seconds per module |
| Thread calls | SQL query, but duplicate requests were observed | Repeated identical in-flight reads |

These values are diagnostic baselines, not universal benchmarks. Automated
performance gates will use synthetic databases with stable sizes and shapes.

PR 2B's synthetic 400,000-row comparison reduced the same recommendation
request from 29.96 seconds on the legacy fallback to a 134.6 ms median and
151.1 ms p95 over 20 indexed runs. The request now reads materialized thread
rollups, hydrates only the top 20 rows, and keeps ranking index-backed.

## Architectural Principles

### 1. Materialize stable work once

Values that depend only on normalized usage records, tracker configuration, and
a versioned algorithm should be persisted during refresh or an explicit
backfill. Requests should not repeatedly classify the same 400,000 records.

### 2. Keep interactive and analytical workloads separate

Interactive endpoints return bounded indexed results. Work that must scan a
large scope, run multiple detectors, or build a portfolio uses an asynchronous
job with:

- start;
- status with percent and stage;
- compact profile;
- bounded evidence pages;
- stable cache identity.

### 3. Version derived facts

Persisted facts include the source generation plus algorithm, threshold,
pricing, and schema versions that affect their meaning. A version mismatch
invalidates or backfills the derived data without changing source records.

### 4. Preserve contracts at adapters

Existing API and MCP response schemas remain stable. New query services produce
the same payload through a compatibility adapter until callers have migrated.
Internal storage layout must not leak into public contracts.

### 5. Let the frontend expose real state

One visible module maps to one query lifecycle. Pages may compose modules, but
they do not hide several unrelated requests behind one boolean. Completed
modules remain usable while peers load or fail.

## Target Architecture

### Refresh and fact pipeline

The refresh pipeline continues to parse source logs into normalized SQLite
tables. A derived-fact stage then incrementally updates materialized records for
new or changed calls only.

Each derived fact set records:

- source generation;
- fact schema version;
- algorithm or detector version;
- threshold configuration fingerprint;
- pricing/rate-card fingerprint when relevant;
- update timestamp;
- aggregate-only fields needed by indexed queries.

Full historical backfills remain explicit. Normal schema initialization must
not unexpectedly perform an unbounded rebuild.

### Query services

Dashboard routes call focused query services rather than general report
builders. A query service:

- validates scope and limits;
- uses indexed predicates and ordering;
- returns only fields needed by the public adapter;
- reports source revision and cache metadata;
- never reopens raw logs;
- never returns indexed content unless a separate explicit content endpoint
  authorizes it.

### Heavy analysis jobs

Routes that cannot meet interactive budgets become asynchronous analyses. The
job registry and persisted run cache should reuse the Compression Lab lifecycle
instead of inventing route-specific polling protocols.

The common job status contract should expose:

- status;
- stage;
- completed units;
- total units when known;
- percent when defensible;
- source revision;
- cache mode;
- last update;
- structured error and exact next action.

### Frontend query orchestration

TanStack Query remains the client data layer. Each page module receives:

- a stable query key containing scope, filters, source revision, and contract
  version;
- its own abort signal;
- stale and retention policies appropriate to the endpoint;
- persisted cache only for aggregate payloads;
- a visible state of waiting, loading, ready, updating, or unavailable.

Navigation cancels only requests with no remaining observers. Completed sibling
queries stay cached and render immediately on return.

### Cache and invalidation

Cache identity is based on source revision and every input that changes payload
meaning. Refresh completion invalidates old source revisions naturally.

The preferred cache order is:

1. in-memory frontend query cache;
2. bounded aggregate browser cache;
3. server process cache for identical immutable payloads;
4. persisted derived facts and completed analysis runs;
5. normalized SQLite source tables.

Raw context and indexed content never enter browser persistence.

### Observability

Every dashboard endpoint should emit optional technical timing metadata or
structured server timing logs for:

- queue/wait time;
- database time;
- Python transformation time;
- serialization time;
- result rows;
- scanned rows when measurable;
- cache hit/miss;
- source generation.

Browser development tests should record request count, cancellation, response
status, and duration without logging private payloads.

## Recommendation Pipeline First Migration

The recommendations endpoint is the first backend target because it is both
user-visible and currently dominated by avoidable repeated work.

### Persisted facts

Add a versioned recommendation-fact representation containing the aggregate
inputs and outputs needed to reproduce current recommendation rows:

- record ID and event timestamp;
- active/archive scope;
- thread identity hash or existing aggregate thread key;
- model and effort labels;
- token and cache metrics;
- pricing/credit status needed by the current contract;
- primary and secondary recommendation keys;
- recommendation score;
- recommended action key;
- fact and configuration versions.

PR 1 resolves this as dedicated `recommendation_facts` and
`recommendation_fact_state` tables. Their indexes support ordering by scope,
recommendation score, recency, and record ID without introducing a generalized
derived-facts framework.

### Compatibility adapter

The new SQL path returns the existing
`codex-usage-tracker-recommendations-v1` payload. A temporary test-only
comparison mode runs legacy and indexed implementations over synthetic fixtures
and asserts:

- the same matched records;
- the same ranking and tie-breaking;
- the same recommendation keys and scores;
- the same filter semantics;
- the same privacy fields;
- the same limit and truncation behavior.

The legacy implementation remains available behind an internal fallback until
parity and migration tests pass, then is removed in a later cleanup PR.

## Phased Pull Requests

### PR 0: Measurement and route inventory

- Add a dashboard route inventory with execution path, scope behavior, cache
  behavior, result bounds, and owner.
- Add synthetic benchmark fixtures at small, medium, and large scales.
- Add endpoint timing instrumentation and compact benchmark output.
- Identify duplicate in-flight frontend requests and their query keys.

Acceptance:

- Baseline results are reproducible without private data.
- Every dashboard route is classified as interactive, bounded report, or heavy
  analysis.
- No performance threshold blocks CI yet; measurements establish budgets.

### PR 1: Recommendation facts and incremental maintenance

- Define the versioned recommendation-fact schema and indexes.
- Materialize facts during full refresh.
- Incrementally update only changed records during append refresh.
- Add explicit idempotent historical backfill.
- Record fact generation and configuration fingerprints.

Acceptance:

- Append refresh does not rebuild unchanged history.
- Backfill is idempotent and does not read raw logs.
- Migration tests cover existing databases with zero fact rows.
- Fact parity holds across recommendation edge-case fixtures.

### PR 2: Indexed recommendations API

- Add a focused query service over recommendation facts.
- Adapt results to the current recommendations schema.
- Preserve filters, ordering, limits, truncation, and privacy behavior.
- Add an internal fallback for stale or missing facts with an explicit
  diagnostic marker.

Acceptance:

- Contract tests pass unchanged.
- Legacy/indexed shadow comparison is exact on synthetic fixtures.
- Warm p95 is below 500 ms and cold p95 below 2 seconds on the agreed large
  synthetic fixture.
- The route does not construct the complete call object graph.

### PR 3: Frontend module query registry

- Standardize query-key construction and source-revision identity.
- Standardize module states and segmented page progress.
- Deduplicate identical in-flight calls.
- Define stale, retry, cancellation, and persisted-cache policy by data class.
- Migrate Overview, Investigator, Cache and Context, Diagnostics, and Reports.

Acceptance:

- Navigation never resets completed sibling modules.
- Identical requests share one in-flight query.
- Each page identifies the module still loading or unavailable.
- Browser tests cover rapid route switching and return navigation.

### PR 4: Heavy-route job migration

- Audit remaining routes against interactive budgets.
- Move unavoidable full-scope analysis to the common async job lifecycle.
- Reuse persisted run results across dashboard and MCP consumers.
- Add progress stages based on measurable work units.

Acceptance:

- No synchronous dashboard request performs an unbounded detector walk.
- Polling is read-only and does not block worker persistence.
- Dashboard and MCP render the same compact profile payload.
- Cancelled browser observers do not cancel shared server jobs.

### PR 5: Query and cache hardening

- Add server-side immutable response caching where persisted facts alone do not
  meet warm budgets.
- Add database indexes justified by query plans.
- Bound serialization and payload sizes.
- Add source-revision invalidation and stale-result messaging.
- Add request coalescing tests for expensive identical requests.

Acceptance:

- Warm/cold budgets pass at the route level.
- Cache keys include all semantic inputs.
- Cache invalidation follows source generation without manual clearing.
- No raw or indexed content is persisted in browser caches.

### PR 6: Cleanup and enforcement

- Remove retired full-scan compatibility paths after parity is proven.
- Turn selected benchmark budgets into CI ratchets.
- Document extension rules for new endpoints and modules.
- Update architecture diagrams, API docs, and maintainer guidance.

Acceptance:

- The route inventory has no unexplained unbounded interactive path.
- CI fails on duplicate query keys, schema drift, or budget regression where
  deterministic fixtures make the check reliable.
- Public documentation describes which analyses are immediate versus async.

## Performance Budgets

Initial targets for a synthetic database comparable to 400,000 calls:

| Class | Cold target | Warm target | Payload expectation |
| --- | ---: | ---: | --- |
| Interactive summary | <= 2 s p95 | <= 500 ms p95 | Bounded aggregates |
| Ranked list | <= 2 s p95 | <= 500 ms p95 | <= requested page |
| Selected detail | <= 1 s p95 | <= 250 ms p95 | One record/thread |
| Heavy analysis start | <= 500 ms p95 | <= 250 ms p95 | Job handle |
| Heavy analysis status | <= 250 ms p95 | <= 100 ms p95 | Compact progress |

Budgets should be adjusted only from repeatable synthetic evidence, not by
loosening thresholds after a regression.

## Test Strategy

### Contract and parity

- Snapshot public schemas before each route migration.
- Compare legacy and new implementations over synthetic edge cases.
- Test stable ordering under ties.
- Test `limit=0`, finite limits, offsets, time scopes, archived scope, and
  empty databases.

### Incremental refresh

- Start with a historical database lacking derived facts.
- Run explicit backfill twice and prove idempotence.
- Append one event and prove only affected facts and thread aggregates change.
- Replace or remove a source and prove orphaned facts disappear.
- Change threshold/configuration fingerprints and prove controlled
  invalidation.

### Frontend lifecycle

- Resolve page modules in different orders.
- Cancel one slow module through navigation and preserve completed peers.
- Return to the page and retry only unfinished work.
- Render partial failure without hiding successful modules.
- Prove identical query keys coalesce requests.
- Prove source revision changes invalidate prior aggregate cache entries.

### Browser and integration

- Run Overview, Investigator, Calls, Threads, Limits, Cache and Context,
  Diagnostics, and Reports against the large synthetic fixture.
- Assert no console/page errors.
- Assert no document-level overflow.
- Record request counts and module completion.
- Exercise rapid route switching while heavy modules are active.

### Privacy and security

- Assert aggregate endpoints contain no prompt, raw output, file path, command
  text, or indexed fragment.
- Assert browser-persisted cache stores aggregate payloads only.
- Keep support bundles and timing logs free of private records.

## Migration Safety and Rollback

Each route migration must be independently reversible:

- schema additions are additive;
- existing normalized tables remain canonical;
- adapters preserve public payloads;
- internal feature selection can return to the legacy builder while facts
  remain harmless;
- frontend modules can return to their prior query option without changing the
  API contract.

Do not remove a legacy path in the same PR that first introduces its
replacement. Removal follows parity, benchmark, and release soak evidence.

## Definition of Done

The refactor is complete when:

- all interactive dashboard routes are indexed and bounded;
- all heavy routes use reusable async jobs with meaningful progress;
- no normal page load rebuilds a full Python call object graph;
- frontend modules cache and cancel independently;
- repeated identical requests are coalesced;
- route-level performance budgets run in CI where deterministic;
- existing API/MCP schemas remain compatible or have documented versioned
  successors;
- dashboard, MCP, and CLI consumers share the same query/report services;
- privacy tests prove aggregate defaults remain aggregate-only;
- the route inventory has no unowned legacy full-scan path.

## Open Decisions

Resolve these during PR 0 and PR 1:

1. Whether recommendation facts belong in a dedicated table or a generalized
   versioned derived-facts table.
2. Whether server timing belongs in a response metadata block, the
   `Server-Timing` header, structured logs, or a combination.
3. Which completed async profiles should persist across process restarts.
4. Which aggregate browser caches should remain enabled by default and their
   size/retention limits.
5. Whether the existing thread summary recommendation approximation should be
   replaced by exact record-derived aggregation during the recommendation
   migration.
