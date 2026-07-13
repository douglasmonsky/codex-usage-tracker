# Dashboard Route Inventory

Status: Measured baseline for the dashboard query-pipeline refactor
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

Current count: 48 routes: 16 interactive, 12 bounded reports, and 20 heavy analyses.

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
| `GET /api/recommendations` | Heavy analysis | Ranks all matches before default 20-row limit | Recomputed per request |
| `GET /api/allowance/history` | Bounded report | Default 1,000 normalized observations | SQLite plus local config |
| `GET /api/allowance/diagnostics` | Heavy analysis | Default 10,000 observations; may analyze all history | Recomputed per request |
| `GET /api/allowance/export` | Bounded report | Schema-bounded strict aggregate export | SQLite plus local config |
| `GET /api/reports/pack` | Bounded report | Default 100 rows and 8 evidence rows | Recomputed per request |
| `GET /api/investigations/agentic` | Heavy analysis | All-scope analysis; default 5 evidence rows | Recomputed per request |
| `GET /api/investigations/repeated-files` | Heavy analysis | All-scope ranking; default 20 patterns | Recomputed per request |
| `GET /api/investigations/shell-churn` | Heavy analysis | All-scope ranking; default 20 patterns | Recomputed per request |
| `GET /api/investigations/large-low-output` | Heavy analysis | All-scope ranking; default 20 calls | Recomputed per request |
| `GET /api/investigations/walk` | Heavy analysis | All-scope hypothesis walk; default 5 evidence rows | Recomputed per request |
| `GET /api/diagnostics/summary` | Bounded report | Default 20 groups over persisted facts | Live SQLite query |
| `GET /api/diagnostics/facts` | Bounded report | Default 50 persisted facts | Live SQLite query |
| `GET /api/diagnostics/fact-calls` | Heavy analysis | Resolves request-bounded supporting calls | Live SQLite query |
| `GET /api/diagnostics/compactions` | Bounded report | Default 50 persisted compaction facts | Live SQLite query |
| `GET /api/diagnostics/tools` | Bounded report | Default 50 persisted tool facts | Live SQLite query |
| `GET /api/diagnostics/{overview,tool-output,commands,git-interactions,file-reads,file-modifications,read-productivity,concentration,guided-summary}` | Interactive | One fixed named diagnostic snapshot | Persisted until refresh |
| `GET /api/diagnostics/usage-drain` | Interactive | One fixed diagnostic snapshot | Persisted until refresh |
| `GET /api/usage` | Bounded report | Configured row window; optional refresh may scan all logs | SQLite index; optional refresh |
| `GET /api/refresh/start` | Heavy analysis | Starts all-scope asynchronous refresh | SQLite plus in-process job state |
| `GET /api/refresh/status` | Interactive | One compact job status | In-process job registry |
| `POST /api/diagnostics/refresh` | Heavy analysis | Rebuilds every diagnostic snapshot | Serialized and persisted |
| `POST /api/diagnostics/{overview,tool-output,commands,git-interactions,file-reads,file-modifications,read-productivity,concentration,guided-summary}/refresh` | Heavy analysis | Rebuilds the named snapshot | Serialized and persisted |
| `POST /api/diagnostics/usage-drain/refresh` | Heavy analysis | Rebuilds the named snapshot | Serialized and persisted |

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
