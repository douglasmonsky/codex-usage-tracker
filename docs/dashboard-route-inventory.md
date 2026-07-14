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

Current count: 49 routes: 17 interactive, 20 bounded reports, and 12 heavy
analyses. All 12 heavy-analysis routes start background work and return a job
handle; none performs the detector or refresh walk on the request thread. The
two status routes are read-only polls.

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
| `GET /api/summary` | Bounded report | Default 20 groups over all matching rows | Live report query |
| `GET /api/recommendations` | Bounded report | Ranks persisted facts before hydrating default 20 rows | Source-generation keyed SQLite facts |
| `GET /api/allowance/history` | Bounded report | Default 1,000 normalized observations | SQLite plus local config |
| `GET /api/allowance/diagnostics` | Bounded report | Evaluates at most the configured 10,000-observation window | Recomputed per request |
| `GET /api/allowance/export` | Bounded report | Schema-bounded strict aggregate export | SQLite plus local config |
| `GET /api/reports/pack` | Bounded report | Default 100 rows and 8 evidence rows | Recomputed per request |
| `GET /api/investigations/agentic` | Bounded report | Composes bounded indexed reports; default 5 evidence rows | Recomputed from persisted facts |
| `GET /api/investigations/repeated-files` | Bounded report | Ranks persisted file-event facts; default 20 patterns | Recomputed from persisted facts |
| `GET /api/investigations/shell-churn` | Bounded report | Ranks persisted command facts; default 20 patterns | Recomputed from persisted facts |
| `GET /api/investigations/large-low-output` | Bounded report | Uses indexed token predicates; default 20 calls | Live bounded SQLite query |
| `GET /api/investigations/walk` | Bounded report | Composes bounded indexed hypotheses; default 5 evidence rows | Recomputed from persisted facts |
| `GET /api/diagnostics/summary` | Bounded report | Default 20 groups over persisted facts | Live SQLite query |
| `GET /api/diagnostics/facts` | Bounded report | Default 50 persisted facts | Live SQLite query |
| `GET /api/diagnostics/fact-calls` | Bounded report | Resolves one request-bounded page of supporting calls | Live SQLite query |
| `GET /api/diagnostics/compactions` | Bounded report | Default 50 persisted compaction facts | Live SQLite query |
| `GET /api/diagnostics/tools` | Bounded report | Default 50 persisted tool facts | Live SQLite query |
| `GET /api/diagnostics/{overview,tool-output,commands,git-interactions,file-reads,file-modifications,read-productivity,concentration,guided-summary}` | Interactive | One fixed named diagnostic snapshot | Persisted until refresh |
| `GET /api/diagnostics/usage-drain` | Interactive | One fixed diagnostic snapshot | Persisted until refresh |
| `GET /api/usage` | Bounded report | Configured row window; optional refresh may scan all logs | SQLite index; optional refresh |
| `GET /api/refresh/start` | Heavy analysis | Starts an all-scope refresh and returns immediately | Background worker plus in-process job state |
| `GET /api/refresh/status` | Interactive | Read-only compact refresh status | In-process job registry |
| `GET /api/diagnostics/refresh/status` | Interactive | Read-only compact diagnostic job status | Shared in-process analysis registry |
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

## Timing Evidence

JSON API responses include a privacy-safe `Server-Timing` header such as
`app;dur=140.428`. It measures server-side handler work before response-body
serialization. It intentionally omits query strings, filters, record IDs, and
payload content.

The deterministic route benchmark exercises the summary and recommendation
adapters with synthetic SQLite histories:

```bash
python scripts/benchmark_dashboard_routes.py \
  --sizes 10000 100000 400000 \
  --iterations 3 \
  --output-dir /tmp/codex-dashboard-route-benchmark
```

The command emits compact JSON and enforces no threshold in this measurement
phase. The checked-in baseline is
[`benchmarks/dashboard-route-baseline.json`](benchmarks/dashboard-route-baseline.json).

| Synthetic calls | Summary median | Recommendations median |
| ---: | ---: | ---: |
| 10,000 | 0.011 s | 0.492 s |
| 100,000 | 0.140 s | 6.791 s |
| 400,000 | 0.668 s | 38.819 s |

The near-linear recommendation cost validates the first migration target in
the refactor roadmap. These numbers establish evidence only; PR0 does not add
or relax a CI performance threshold.
