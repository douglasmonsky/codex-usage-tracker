# Core Fast-Path Redesign

**Status:** Maintainer approved on 2026-07-26
**Tracking:** GitHub issue `#313`
**Release:** `0.26.0`
**Program ID:** `OPS-CORE-026`

## Goal

Make the seven-tool MCP profile dependable on an already-built large local
index by removing analytical enrichment and compatibility work from the
canonical request path.

After the first index build:

- status and job coordination read only compact persisted state;
- refresh hydrates only new canonical rows before committing a generation;
- analysis reads one committed generation and never starts refresh work;
- common product queries use focused or materialized plans;
- exact evidence remains bounded and on demand; and
- retired Compression Lab and compatibility persistence no longer consumes
  storage or refresh time.

## User Evidence

Public `0.25.1` dogfood required `29` MCP calls and `22` job polls over
`15m29s`. Two refreshes adding only `33` and `45` canonical rows took about
`379s` and `318s`, mostly in `syncing_facts`. Two analysis calls then consumed
`42.6s` and `61.2s` without returning findings, selectors, evidence, a job, or
an actionable limitation.

A later run showed:

- detached worker startup could fail before claiming the job;
- a grouped model/effort query took `13.6s` server-side and about `29.7s`
  wall-clock;
- identical analyses reused an in-progress refresh job but still could not
  produce analysis; and
- an incremental refresh committed its generation only after a long derived
  fact phase.

Aggregate-only storage inspection found approximately:

| Family | Footprint |
| --- | ---: |
| Compression | `2.36 GiB` |
| Canonical usage and indexes | `1.28 GiB` |
| Recommendation facts | `889 MiB` |
| Diagnostic facts | `771 MiB` |
| Content index | `350 MiB` |
| Source records | `302 MiB` |
| Thread summaries | `1.8 MiB` |

No raw local usage content, prompt, tool output, or source path is part of this
plan or its fixtures.

## Public Contract

The default MCP profile remains exactly:

1. `usage_status`
2. `usage_refresh`
3. `usage_analyze`
4. `usage_query`
5. `usage_evidence`
6. `usage_allowance`
7. `usage_job_status`

No new top-level MCP tool, CLI command, dashboard workspace, runtime
dependency, or analytical goal is introduced.

### `usage_status`

- Reads compact persisted readiness, freshness, accounting, and plugin identity.
- Does not discover or parse source logs.
- Does not validate or materialize optional analytical facts.
- Warm target: `<= 250ms` on the installed synthetic large-index gate.

### `usage_job_status`

- Reads only the operational sidecar row for the named job.
- Does not open the main usage database or load pricing configuration.
- Supports a bounded host-wait interval so the host waits while the model does
  not poll.
- Warm target: `<= 100ms` for an immediate snapshot.

### `usage_refresh`

- Plans against an immutable newline-aligned source boundary.
- A newly discovered source is additive, not a replacement requiring a
  history-wide derived rebuild.
- Commits canonical rows, source metadata, canonical links, compact thread
  summaries, allowance observations, and the canonical generation first.
- Does not block canonical completion on compression, recommendation,
  diagnostic, or compatibility enrichment.
- Equivalent refresh requests join one durable job.
- No-change target: `<= 100ms`; small append target: `<= 5s` at the synthetic
  `216,000`-row scale.

### `usage_analyze`

- Reads the latest committed generation or an explicitly supplied revision.
- Never calls or starts `usage_refresh`.
- Returns useful canonical findings with a staleness limitation when optional
  facts are unavailable.
- Optional enrichment may reduce confidence but may not suppress the entire
  result.
- Identical completed requests reuse one durable result.

### `usage_query`

- Preserves the existing validated query contract and exact counts.
- Common Home, Calls, Threads, model/effort, and Limits shapes use focused or
  materialized plans.
- A generic exact query remains a bounded fallback and declares when it uses a
  slower plan.

### `usage_evidence`

- Remains selector-driven, bounded, aggregate-first, and on demand.
- Exact Evidence Console deep links and raw-context controls are preserved.

### `usage_allowance`

- Remains independently usable.
- Allowance materialization and analysis do not run as a side effect of status,
  query, evidence, job status, or unrelated analysis.

## Persistence Decisions

### Keep

- canonical usage events and deduplication identity;
- source-file checkpoints and exact source-record provenance;
- bounded content fragments required for exact evidence;
- compact active/all-history thread summaries;
- allowance observations and interval integrity;
- persisted Home metrics;
- operational analysis/refresh job sidecar;
- pricing, credit, service-tier, privacy, and raw-context controls.

### Remove

- retired Compression Lab MCP/HTTP/CLI compatibility routers;
- compression runs, candidates, simulations, candidate-record mappings, and
  detector fact tables from the installed product;
- compression-owned source-generation state;
- compatibility-only report and payload adapters that are unreachable from
  the seven-tool profile.

The upgrade is one way. The migration drops retired compression tables and
indexes without scanning or rewriting canonical usage rows.

### Slim Or Defer

- per-call recommendation JSON and secondary-signal persistence;
- all-history diagnostic fact indexes;
- recommendation and diagnostic work not required for canonical accounting or
  exact selected evidence.

Compact thread-level summaries may remain persisted. Per-call recommendations
and workflow diagnostics are computed only for the requested bounded scope.

## Data Flow

```text
append-active JSONL
  -> fixed source boundary
  -> parse changed rows
  -> canonical upsert and source checkpoint
  -> canonical links + compact thread/Home/allowance state
  -> commit generation
  -> status/query/analyze/evidence read committed generation

optional bounded analysis request
  -> on-demand recommendation/diagnostic computation
  -> durable bounded analysis result
```

No optional enrichment phase retains the canonical writer transaction.

## Implementation Slices

### Slice A — Critical-path separation

- make new source plans additive for derived-fact reconciliation;
- make job status sidecar-only;
- remove implicit refresh from analysis;
- return canonical analysis with explicit stale/optional-fact limitations;
- add grouped model/effort query fast path;
- add bounded host-wait job status.

### Slice B — Compression product removal

- delete compatibility routers and package registration;
- remove compression refresh synchronization;
- replace compression generation with canonical refresh generation;
- add the one-way table/index drop migration;
- update deprecation, upgrade, support, and package inventories.

### Slice C — Derived-state slimming

- retain compact thread/Home facts;
- replace persisted per-call recommendation JSON with bounded computation;
- reduce diagnostic persistence to the exact evidence fields still required;
- ratchet schema, package, complexity, and database-footprint budgets.

Each slice starts from current `main`, has its own focused issue/branch/PR, and
must leave `main` releasable.

## Failing Tests First

1. A new synthetic task file after a completed cold build must not request a
   full derived rebuild.
2. `usage_job_status` fails if the main usage database or pricing loader is
   touched.
3. Stale `usage_analyze` fails if it calls the refresh service and must return
   canonical findings plus a stale-data limitation.
4. Grouped model/effort query plans must use the declared focused index or
   compact materialization and meet the synthetic route budget.
5. A schema-previous fixture containing compression tables upgrades without
   rewriting canonical rows and leaves retired tables absent.
6. Installed discovery exposes exactly seven core tools and no compression or
   compatibility tool.

## Performance Qualification

Use synthetic fixtures only.

- record identical unprofiled cold, no-change, new-task, append, moving-tail,
  concurrent-read, query, analysis, and job-status baselines;
- profile only the smallest repeatable synthetic failing workload with
  `agent-perf`;
- validate `100,000` and `216,000` canonical-row shapes with many distinct
  task/thread files;
- include calls arriving while refresh is bounded to its fixed source boundary;
- measure server time, wall time, scanned rows/pages, writer-lock duration,
  database bytes by family, MCP calls, and polling calls;
- use unprofiled results, not profiler overhead, for acceptance claims.

## Validation

- focused refresh, source-planning, job, query, analysis, evidence,
  recommendation, diagnostic, migration, and MCP tests;
- synthetic incremental and route-budget benchmarks;
- deterministic assets and frontend gates because the Evidence Console consumes
  the same APIs;
- Ruff, formatting, MyPy, Pyright, Tach, complexity budgets, compileall, and
  release checks;
- built wheel/sdist, clean installed-package smoke, exact seven-tool discovery,
  cross-process refresh join, host wait, query, analysis reuse, exact evidence,
  and moving-tail catch-up;
- one final read-only reviewer after the complete stable diff.

## Risks And Controls

- **Lost analytical confidence:** return explicit limitations and bounded
  canonical findings rather than inventing optional-fact conclusions.
- **Migration duration:** drop retired objects directly; do not copy or rebuild
  canonical rows.
- **Evidence regression:** preserve source records, selected content fragments,
  selectors, and exact deep links in focused parity tests.
- **Refresh integrity:** preserve foreign keys, deduplication, fixed source
  boundaries, canonical accounting, and atomic generation commit.
- **Scope growth:** no new surface or goal; follow-up improvements require a
  separate amendment.
