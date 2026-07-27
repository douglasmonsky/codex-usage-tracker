# Product Recovery Roadmap

**Status:** Approved direction; active when this roadmap merges

**Target:** `0.29.0`

**Authority:** This document, its [task packets](product-recovery-tasks/README.md),
and the [execution ledger](product-recovery-execution.md) govern post-`0.28`
product work.

The [Product Kernel Reset](product-kernel-reset.md) remains historical evidence
for the `0.26`–`0.28` rewrite. It no longer governs new implementation.

## Executive Decision

Codex Usage Tracker will optimize for one outcome:

> A fresh Codex task returns a fast, accurate, useful, evidence-grounded answer
> about the user's usage through the installed plugin, MCP server, and skill.

The kernel rewrite established the correct product boundary: local structural
facts below model inference. Dogfood then exposed that the current
implementation is not yet a good product experience at production scale.
Common queries can be slow, persisted facts and indexes are larger than
necessary, Console tables are database-shaped, useful cost and allowance views
regressed, and installed agent workflows can take minutes.

`0.29.0` is therefore a recovery release, not a feature expansion. It will:

- make reopen and common warm queries immediate;
- make refresh genuinely append-oriented and observable;
- compact the metadata store without weakening accounting;
- restore the high-value token, cost, credit, allowance, turn, and tool facts;
- make MCP results and Console views understandable to humans;
- qualify the complete installed agent outcome, not only isolated endpoints;
- publish public documentation only after the experience is proven.

## Current Release Boundary

As of 2026-07-27:

- repository and plugin metadata identify `0.28.0`;
- tag `v0.28.0` and a GitHub release exist;
- that GitHub release has no attached package assets;
- public PyPI still serves `0.27.0` as latest;
- at the adoption base, the old execution ledger still left K16 in progress.

R0 records this accurately and supersedes the incomplete K16 publication path.
The project will not quietly promote stale `0.28.0` package bytes after the
recovery program begins. The next fully qualified public package is `0.29.0`
unless the maintainer approves a different release decision.

## Evidence Behind the Recovery

The aggregate production-shaped audit read no prompts, responses, commands,
tool output, or private paths. It measured:

| Measure | Observed |
| --- | ---: |
| Source history | 14.955 GiB |
| Cold build | 1,096.357 seconds |
| Parsed JSONL lines | 3,806,301 |
| Stored fact rows | about 2.40 million |
| Analytical database | about 1.17 GB |
| Table storage | 615.02 MiB |
| Index storage | 501.21 MiB |
| Model-call rows | 608,694 |
| Tool-call rows | 589,568 |
| Allowance rows | 1,051,496 |
| Exact same-timestamp allowance repeats | 518,900 |
| Allowance state-change rows in measured sequence | 133,587 |

The active database is metadata-only. Its size is caused by row and index
amplification, especially per-call allowance snapshots and repeated text
identifiers. No legacy cache is configured, no optional content database is
present, the SQLite freelist is empty, and rebuilding the same schema would
recreate approximately the same cost.

User-facing evidence adds the more important product failures:

- reopening Live feels like a rebuild instead of a cached read;
- common warm API and MCP questions feel slower than the retired product;
- “list my top threads by usage” took 5 minutes 45 seconds end to end;
- Explore can return no rows for apparently valid selections;
- Limits is slow and lost the useful usage-over-time graph;
- cost and credits are absent from core views;
- thread selectors and internal IDs appear where human names belong;
- Evidence lacks turn order and useful tool-impact context;
- table columns are poorly ordered and cannot be sorted;
- low-value “Snapshot truth” and “Tool-independent facts” displace useful data.

## Product Contract

### North-star outcome

Every milestone is evaluated through fresh installed Codex tasks. Unit tests,
SQL benchmarks, and browser tests are necessary supporting evidence, but they
do not replace the agent outcome.

The north-star scorecard records:

- successful useful answers;
- end-to-end wall time;
- tracker-tool time;
- MCP call and query-batch count;
- refresh jobs, joins, polls, retries, and duplicate work;
- response bytes and agent context cost;
- accuracy against deterministic synthetic truth;
- evidence-selector validity;
- human readability;
- correct separation of fact, estimate, and model inference.

### Facts below inference

The tracker owns deterministic facts, calculations, provenance, coverage,
freshness, and evidence. Codex owns explanation, hypotheses, and
recommendations.

The tracker will not restore server-authored narrative diagnostics,
OpenTelemetry ingestion, Compression Lab, or another MCP tool.

### Metadata-first storage

The default analytical store may retain:

- source cursors and generations;
- threads and human display labels;
- turns;
- model calls and four token classes;
- tool operation, bounded target label, duration, output bytes, and status;
- structured lifecycle activity;
- allowance state observations and intervals;
- cost and credit calculations with rate-card provenance;
- compact persisted rollups.

It must not retain prompts, responses, reasoning text, raw tool arguments, raw
tool output, full shell commands, secrets, or full local paths.

### Allowance attribution

An allowance state observed after a call is not attributed to that call. The
delta belongs to the interval since the preceding observation and can include
multiple local calls or out-of-band activity.

The schema must distinguish:

- observation trigger from causal attribution;
- exact upstream allowance state from local interval calculations;
- deterministic token-rate cost from estimated allowance/credit allocation;
- unchanged state from proof of zero consumption.

### One cache, one append path

- Opening the Console never starts refresh.
- A compatible committed generation renders immediately.
- Query execution never starts refresh implicitly.
- No-change refresh performs no fact or rollup writes.
- Ordinary refresh parses only complete appended lines.
- Moving-tail catch-up includes lines appended during refresh.
- One durable worker owns refresh; compatible callers join it.
- Readers stay on the prior committed generation until atomic promotion.

## Performance Gates

All timings use identical unprofiled synthetic workloads. CPU profiles
attribute work but do not prove speedup.

| Scenario | Required | Stretch |
| --- | ---: | ---: |
| Console useful render from committed generation | ≤500 ms | ≤250 ms |
| Live, Explore defaults, Limits, Evidence first page | ≤1 s | ≤500 ms |
| Warm top-threads tracker response | ≤1 s | ≤500 ms |
| Warm top-threads fresh-task final answer | ≤15 s | ≤10 s |
| Warm status | ≤100 ms | ≤50 ms |
| Ordinary moving-tail refresh | ≤500 ms | ≤250 ms |
| Larger bounded tail | ≤2 s | ≤1 s |
| Complete production-shaped cold build | ≤240 s | ≤180 s |
| Production-shaped database | <700 MiB | <500 MiB |

Common warm routes must read bounded indexes or persisted rollups. They may not
scan every foundational fact to render a landing page or answer a routine
question.

## Restored Analytical Value

`0.29.0` restores or completes:

- total calls and total tokens with four-class breakdown;
- cache reuse and context pressure with explicit coverage;
- configured dollar cost and Codex credit estimates;
- observed allowance drain and usage-over-time graphs;
- time-first token and allowance bands;
- thread and call rankings with human labels;
- turn ordinal, elapsed time, and completion basis;
- tool read/write/search/test operation and bounded target label;
- tool duration, output bytes, and provenance-graded context impact;
- exact evidence selectors that remain copyable but do not dominate tables.

Per-call dollar cost may be deterministic when configured token rates cover the
model. Per-call allowance consumption remains estimated unless upstream data
provides causal attribution.

## Console Contract

### Live

Render persisted committed summaries immediately. Show calls, four token
classes, cache reuse, cost, credits, and a recent usage/allowance graph. Remove
“Snapshot truth” and “Tool-independent facts.”

### Explore

Open on useful Threads and Calls views. Every selectable default must return a
valid bounded result or a specific actionable explanation. Keep the generic
query composer secondary to curated views.

### Evidence

Default columns begin with time, turn, event or tool, token impact, cost or
credits, and duration. Human labels precede selectors. Long IDs live in
expandable details or copy actions. Tables support sorting, pagination,
filtering, and stable evidence navigation.

### Limits

Read compact allowance intervals. Restore the usage-over-time graph and expose
observed drain, local tokens, estimated credits, credits per usage unit,
coverage, and reset boundaries.

## Program Tasks

| Task | Depends on | Outcome |
| --- | --- | --- |
| [R0](product-recovery-tasks/r0-adopt-recovery-roadmap.md) | — | Adopt recovery authority and close the incomplete reset program accurately |
| [R1](product-recovery-tasks/r1-agent-outcome-baseline.md) | R0 | Freeze fresh-task agent scorecard and production-shaped baselines |
| [R2](product-recovery-tasks/r2-schema-v3-storage.md) | R1 | Approve compact schema v3, allowance intervals, rollups, and side-by-side upgrade |
| [R3](product-recovery-tasks/r3-build-refresh-performance.md) | R2 | Accelerate cold build and prove incremental moving-tail refresh |
| [R4](product-recovery-tasks/r4-fast-query-mcp.md) | R2 | Persist rollups and make common API/MCP questions bounded and fast |
| [R5](product-recovery-tasks/r5-analytical-primitives.md) | R3, R4 | Restore human labels, costs, credits, allowance, turns, and tool impact |
| [R6](product-recovery-tasks/r6-console-usability.md) | R4, R5 | Rebuild all Console areas around fast human workflows |
| [R7](product-recovery-tasks/r7-installed-agent-qualification.md) | R1; final gate after R3–R6 | Qualify installed wheel, plugin, MCP, skill, browser, and fresh-task outcomes |
| [R8](product-recovery-tasks/r8-public-docs.md) | R0; final gate after R6, R7 | Publish benefit-led docs, conversations, and final synthetic screenshots |
| [R9](product-recovery-tasks/r9-release-0.29.0.md) | R7, R8 | Release exact qualified `0.29.0` bytes |

## Dependency And Parallelization Map

```text
R0 → R1 → R2 ─┬→ R3 ─┐
              └→ R4 ─┼→ R5 → R6 ─┐
R1 ─────────────────────→ R7 ─────┼→ R9
R0 ─────────────────────→ R8 ─────┘
```

R7 begins as a harness after R1 and continuously measures each candidate. It
cannot complete until R3–R6 pass. R8 may draft durable copy after R0 but cannot
finalize claims or screenshots until R6 and R7 pass.

After R2 freezes schema and ownership, the following lanes are technically safe
to parallelize if the user or maintainer explicitly authorizes subagents for
that current task:

- R3 ingestion work in `ingest`, `writer`, `discovery`, and refresh tests;
- R4 rollup/query work in query, application, MCP, and query tests;
- the R7 harness in isolated synthetic fixtures and installed-task runners;
- early R8 copy audit in documentation-only files.

R3 and R4 must not both edit schema files. R7 must not patch product behavior.
R8 must not publish screenshots or performance claims from an unqualified
candidate.

R4 publishes the frozen rollup-updater interface before R3 connects it to the
fact-writing transaction. R4 owns the updater implementation; R3 owns its
ingestion call site. That named checkpoint is sequential even while the
remaining ingestion and query work proceeds in parallel.

Parallel execution follows these rules:

1. Task packets and coordinators identify candidates but do not grant
   authorization; only an explicit current-task user or maintainer instruction
   can activate subagents.
2. One writing agent owns one branch and worktree.
3. Every writing task has an explicit file allowlist.
4. The coordinator alone updates the execution ledger and shared contracts.
5. Schema, public JSON, generated Console assets, and package manifests each
   have one owner at a time.
6. Subagents do not rebase, force-push, delete worktrees, or modify another
   agent's files.
7. Each task finishes primary validation before one final read-only review.
8. Parallel branches integrate only at named contract checkpoints.

## Non-Goals

- No new MCP tool.
- No automatic narrative-analysis service.
- No OpenTelemetry or legacy dashboard revival.
- No default raw-content database.
- No attribution of cumulative allowance drain to one call.
- No compatibility adapter for retired beta databases.
- No public documentation claim that has not passed installed qualification.
- No destructive deletion of the old cache during side-by-side validation.

## Program Completion

The recovery program completes only when:

- R0–R9 have terminal ledger entries;
- the production-shaped cold build and database-size gates pass;
- common warm API and Console routes pass without broad fact scans;
- the fixed fresh-task prompt suite passes correctness and latency gates;
- package, plugin, MCP, skill, and cached bundle identities agree;
- human labels and exact selectors coexist across agent and Console surfaces;
- cost, credits, allowance, four-token, turn, and tool-impact views pass;
- reopen and ordinary refresh never rebuild compatible history;
- final public screenshots use only deterministic synthetic fixtures;
- exact wheel and sdist bytes pass protected publication and public verification.
