# Dashboard Route Inventory

Status: Maintained inventory for the dashboard query-pipeline refactor
Tracking: [#244](https://github.com/douglasmonsky/codex-usage-tracker/issues/244)

## Purpose

This inventory classifies every registered local dashboard API route by its
execution behavior. The machine-readable source of truth is
`codex_usage_tracker.server.route_inventory`; tests require it to cover every
GET, POST, and diagnostic-fact route exactly once.

The classifications are:

- **Interactive:** selected-record or persisted-snapshot reads expected to be
  immediately responsive.
- **Bounded report:** response rows are bounded, although aggregation or
  derived filtering may still inspect an all-history scope.
- **Heavy analysis:** detector, ranking, refresh, or investigation work that
  may walk the complete selected history.

Current count: 52 routes: 18 interactive, 21 bounded reports, and 13 heavy
analyses. All 13 heavy-analysis routes start background work and return a job
handle; none performs the detector or refresh walk on the request thread. The
three status routes are read-only polls.

## Route Matrix

| Method and path | Class | Scope and result behavior | Cache or persistence |
| --- | --- | --- | --- |
| `GET /api/context` | Interactive | One selected record; configured character window | On-demand source read |
| `GET /api/context-settings` | Interactive | One compact settings payload | In-memory server state |
| `GET /api/open-investigator` | Interactive | One selected investigator action | Not persisted |
| `GET /api/status` | Interactive | Aggregate refresh metadata | SQLite metadata |
| `GET /api/calls` | Bounded report | Default 100; derived filters may scan all matches | Live SQLite query |
| `GET /api/call` | Interactive | One call and bounded adjacent context | Live SQLite query |
| `GET /api/threads` | Bounded report | Default 100 aggregate rows; all-scope aggregation | Live SQLite query |
| `GET /api/thread-calls` | Bounded report | Default 100; derived filters may load a complete thread | Live SQLite query |
| `GET /api/summary` | Bounded report | Default 20 groups over all matching rows | Generation/config-keyed server response cache over a live report query |
| `GET /api/recommendations` | Bounded report | Ranks persisted facts before hydrating default 20 rows | Generation/config-keyed server response cache over persisted SQLite facts |
| `GET /api/allowance/history` | Bounded report | Default 1,000 normalized observations | Generation/config-keyed large-payload cache over SQLite plus local config |
| `GET /api/allowance/diagnostics` | Bounded report | Evaluates at most the configured 10,000-observation window | Generation/config-keyed large-payload cache over SQLite plus local config |
| `GET /api/allowance/export` | Bounded report | Schema-bounded strict aggregate export | SQLite plus local config |
| `GET /api/reports/pack` | Bounded report | Default 100 rows and 8 evidence rows | Recomputed per request |
| `GET /api/investigations/agentic` | Bounded report | Composes bounded indexed reports; default 5 evidence rows | Recomputed from persisted facts |
| `GET /api/investigations/repeated-files` | Bounded report | Ranks persisted file-event facts; default 20 patterns | Recomputed from persisted facts |
| `GET /api/investigations/shell-churn` | Bounded report | Ranks persisted command facts; default 20 patterns | Recomputed from persisted facts |
| `GET /api/investigations/large-low-output` | Bounded report | Uses indexed token predicates; default 20 calls | Live bounded SQLite query |
| `GET /api/investigations/walk` | Bounded report | Composes bounded indexed hypotheses; default 5 evidence rows | Recomputed from persisted facts |
| `GET /api/diagnostics/summary` | Bounded report | Default 20 groups over persisted facts | Live SQLite query |
| `GET /api/diagnostics/facts` | Bounded report | Default 50 persisted facts | Generation-keyed response cache over indexed SQLite facts |
| `GET /api/diagnostics/fact-calls` | Bounded report | Resolves one request-bounded page of supporting calls | Live SQLite query |
| `GET /api/diagnostics/compactions` | Bounded report | Default 50 persisted compaction facts | Generation-keyed response cache over indexed SQLite facts |
| `GET /api/diagnostics/tools` | Bounded report | Default 50 persisted tool facts | Generation-keyed response cache over indexed SQLite facts |
| `GET /api/diagnostics/{overview,tool-output,commands,git-interactions,file-reads,file-modifications,read-productivity,concentration,guided-summary}` | Interactive | One fixed named diagnostic snapshot | Persisted until refresh |
| `GET /api/diagnostics/usage-drain` | Interactive | One fixed diagnostic snapshot | Persisted until refresh |
| `GET /api/usage` | Bounded report | Configured row window; optional refresh may scan all logs | SQLite index; optional refresh |
| `GET /api/refresh/start` | Heavy analysis | Starts an all-scope refresh and returns immediately | Background worker plus in-process job state |
| `GET /api/refresh/status` | Interactive | Read-only compact refresh status | In-process job registry |
| `GET /api/diagnostics/refresh/status` | Interactive | Read-only compact diagnostic job status | Shared in-process analysis registry |
| `GET /api/compression/status` | Interactive | Read-only compact status for one persistent Compression Lab run | Shared process registry plus SQLite run state |
| `GET /api/compression/profile` | Bounded report | One exact-scope compact aggregate profile; never starts analysis | Persisted Compression Lab run in SQLite |
| `POST /api/compression/start` | Heavy analysis | Starts or reuses one exact-scope detector run and returns HTTP 202 | Background worker persists the shared MCP/dashboard profile |
| `POST /api/diagnostics/refresh` | Heavy analysis | Starts a 10-unit snapshot rebuild and returns HTTP 202 | Background worker persists snapshots in SQLite |
| `POST /api/diagnostics/{overview,tool-output,commands,git-interactions,file-reads,file-modifications,read-productivity,concentration,guided-summary}/refresh` | Heavy analysis | Starts a one-unit named snapshot rebuild | Background worker persists the snapshot in SQLite |
| `POST /api/diagnostics/usage-drain/refresh` | Heavy analysis | Starts a one-unit usage-drain rebuild | Background worker persists the snapshot in SQLite |

## Heavy Analysis Lifecycle

Diagnostic refresh starts return the shared
`codex-usage-tracker-analysis-job-v1` envelope with a source revision, stage,
completed and total units, percentage, and a suggested next action. Identical
active requests reuse one worker. Polling never performs analysis or writes
results; completed jobs direct consumers to reload the normal persisted GET
route. Browser navigation can stop observing a job without cancelling its
server worker.

Compression Lab uses the same observer-safe lifecycle. `POST
/api/compression/start` reserves or reuses a persistent run,
`GET /api/compression/status` reads measurable detector progress, and
`GET /api/compression/profile` returns the exact compact
`codex-usage-tracker-compression-api-v1` profile also exposed by MCP. Leaving
the dashboard aborts only its local polling request; the shared worker continues
and publishes its profile to SQLite.

## Aggregate Response Cache

Summary, recommendation, and bounded diagnostic fact-list responses use one
server-process LRU with at most 64 serialized entries and 256 KiB per stored
payload. Keys contain the route, canonical query, source generation, privacy
mode, and SHA-256 revisions of every local configuration file used by the route.
A source write or relevant configuration change therefore produces a new key
without manual cache clearing. Identical in-flight requests share one builder;
every caller receives a detached decoded copy. Explicit responses larger than
the storage bound are still returned but are marked `bypass` and never retained.

The response `query_cache` block reports hit, miss, coalesced, or bypass status,
the source revision, serialized size, and whether the entry was retained. Raw
context and indexed-content endpoints do not use this cache. Browser persistence
also rejects any payload containing raw/indexed content keys or affirmative
content-inclusion markers.

## Timing Evidence

JSON API responses include a privacy-safe `Server-Timing` header such as
`app;dur=140.428`. It measures server-side handler work before response-body
serialization. It intentionally omits query strings, filters, record IDs, and
payload content.

The deterministic route benchmark exercises the summary and recommendation
adapters with synthetic SQLite histories:

```bash
python scripts/benchmark_dashboard_routes.py \
  --sizes 100000 \
  --iterations 3 \
  --skip-compression \
  --enforce-thresholds \
  --output-dir /tmp/codex-dashboard-route-benchmark
```

The command emits compact JSON with repeated route-handler cold and warm
samples. Every cold sample uses a fresh process cache; warm samples reuse one
seeded cache. Timings include request parsing, cache provenance, and final JSON
serialization. CI reads the checked-in thresholds from
`config/dashboard-route-budgets.json`. The pre-refactor baseline is
[`benchmarks/dashboard-route-baseline.json`](benchmarks/dashboard-route-baseline.json).

| Synthetic calls | Summary median | Recommendations median |
| ---: | ---: | ---: |
| 10,000 | 0.011 s | 0.492 s |
| 100,000 | 0.140 s | 6.791 s |
| 400,000 | 0.668 s | 38.819 s |

The near-linear recommendation cost validates the first migration target in
the refactor roadmap. These numbers establish evidence only; PR0 does not add
or relax a CI performance threshold.

PR 5's clean 400,000-call candidate run measured the current indexed and cached
paths:

| Route | Cold median | Cold p95 | Warm median | Warm p95 | Payload |
| --- | ---: | ---: | ---: | ---: | ---: |
| Summary | 0.581 s | 0.591 s | 1.13 ms | 1.64 ms | 8.7 KiB |
| Recommendations | 0.149 s | 0.150 s | 2.66 ms | 2.87 ms | 151.4 KiB |

The summary date-expression index considered during this work was rejected: it
removed one temporary grouping B-tree but regressed the representative warm SQL
query from roughly 0.56 seconds to 0.81-0.92 seconds. Schema version 22 instead
adds `idx_call_diagnostic_facts_lookup(fact_type, fact_name, record_id)`, which
SQLite selects as a covering index for the correlated diagnostic-fact lookup.

PR 6 removes that correlated representative-call scan and schema version 23 adds
`idx_call_diagnostic_facts_aggregate`, which covers every persisted fact field
consumed by the grouped query. The enforced 100,000-call fixture measured:

| Route | Cold p95 | Warm p95 |
| --- | ---: | ---: |
| Summary | 0.141 s | 1.60 ms |
| Recommendations | 0.041 s | 2.97 ms |
| Diagnostic facts | 0.411 s | 1.29 ms |
| Diagnostic tools | 0.285 s | 1.18 ms |
| Allowance history | 0.411 s | 52.0 ms |
| Allowance diagnostics | 0.392 s | 62.1 ms |
| Threads | 3.51 ms | Not cached |
| Bounded thread calls | 6.90 ms | Not cached |

On the maintainer's 404,176-call local database, the diagnostic fact route
measured 5.5 seconds on its first generation-keyed request and 4 ms on repeat;
the tools route measured 3.3 seconds cold and 2 ms warm. These are diagnostic
observations, not universal performance guarantees.

The allowance change-point scan uses exact running prefix/suffix medians instead
of rebuilding every candidate slice. On the 100,000-call fixture this reduced
allowance diagnostics cold p95 from 8.32 seconds to 0.377 seconds. On the same
local database, all-scope diagnostics measured 1.43 seconds after server
initialization and 17 ms on repeat; history measured 0.35 seconds cold and 59 ms
warm. The dedicated four-entry cache permits payloads up to 8 MiB without
loosening the 256-KiB cache bound for normal dashboard aggregates.
