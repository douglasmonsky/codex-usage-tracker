# MCP-First Product Pivot

This document is the normative release sequence for the MCP-first product
pivot. The approved [design](../superpowers/specs/2026-07-21-mcp-first-product-pivot-design.md)
and [implementation roadmap](../superpowers/plans/2026-07-21-mcp-first-product-pivot.md)
remain the detailed contracts for the program.

The merged `2026-07-19` MCP-first dashboard transition is completed foundation
input. It is not the active roadmap and does not authorize work outside this
program.

## Product Direction

MCP is the primary analysis interface. Deterministic application services
perform calculations and classifications, and the live React dashboard becomes
a supporting Evidence Console for inspecting exact local evidence. The CLI
continues to support setup, automation, recovery, export, and compatibility.

## Release Sequence

| Release | Outcome | Compatibility state |
| --- | --- | --- |
| `0.22.0` | Stable MCP core profile, shared contracts, truthful positioning, and generic job facade | Existing dashboard and old tools still work; old tools move to the `full` profile. |
| `0.23.0` | Evidence Console becomes the default; CLI and HTTP v2 ship | Old pages remain direct-link routes and old CLI names remain aliases. |
| `0.24.0` | Task 27.5 foundation audit, then architecture, database integrity, context offsets, and infrastructure hardening | Implementation starts only after `PROCEED` or a maintainer-approved `AMEND`; old pages are notice-only and old APIs and aliases remain supported. |
| `0.25.0` | Central-product reliability, installed-bundle coherence, durable refresh ownership, incremental performance, and Task 40 static-dashboard sunset | The seven core tools become dependable across task restarts, concurrent use, and append-active logs; the live Evidence Console becomes the only dashboard product. |
| `0.26.0` | Core fast-path redesign removes hidden enrichment from canonical operations, then remaining expired workbench, MCP, CLI, and HTTP compatibility is removed after Task 41 parity gates | The seven core tools remain; legacy compression persistence and compatibility surfaces are removed. |
| `0.27.0` | Feature-free stabilization and pre-1.0 contract hardening | No new public surface; migration and package gates prove the final state. |

If another minor release ships before program execution begins, every planned
minor shifts by the same amount. Task order and compatibility duration do not
change.

## Surface-Growth Freeze

During the pivot, do not add a dashboard workspace, top-level MCP concept,
top-level CLI command, runtime dependency, or SQLite table unless the approved
roadmap names it. A design amendment is required before unplanned public-product
surface growth. The stabilization release is feature-free.

Existing raw-context controls, loopback request guards, deterministic
accounting, and aggregate-first shareable outputs remain unchanged unless a
roadmap task explicitly changes them. Examples, fixtures, and screenshots must
remain synthetic.

## Pre-0.25 Central Product Reliability Gate

Post-`0.24.0` installed dogfood exposed release-blocking operational failures in
the new primary product path:

- a large incremental refresh could hold the SQLite writer transaction through
  a long derived-state phase, blocking concurrent job recovery;
- asynchronous refresh ownership and progress were process-local, so a new task
  could not reliably observe, join, or recover work started by another task;
- refreshes over append-active JSONL sources lacked an explicit immutable input
  boundary and user-visible continuation contract;
- installed source and Codex's cached plugin copy could share version `0.24.0`
  while containing different skills and MCP surfaces; and
- stale-data analysis could abstain safely without linking the caller to the
  active refresh or automatically becoming useful after it completed.

These are central-product reliability defects, not optional stabilization work.
Stable program `OPS-REL-025` therefore ships as `0.25.0`. After its installed
two-task and synthetic incremental checkpoints passed, the maintainer approved
Task 40's static-dashboard sunset as the same release boundary. Neither program
adds an analytical goal, dashboard route, MCP tool, CLI namespace, or new
accounting semantics.

Task 40 may begin only after `OPS-REL-025` records its local runtime,
installed-package, and performance checkpoints as passing and commits that
checkpoint. Tasks 41-45 remain blocked until the complete `0.25.0` release gate
passes. Existing Task 40 and Task 41 branches created before this amendment are
retained as comparison artifacts; they do not become the `0.25.0` release base.

The reliability gate requires:

- one installed bundle identity across package metadata, plugin manifest,
  launcher, cached skills, and `usage_status`, with digest equality checks that
  fail closed on a mixed installation;
- one durable cross-process refresh owner per database and normalized request,
  with joinable job identity, heartbeat, stage, counters, bounded error details,
  restart recovery, and explicit poll guidance;
- responsive concurrent status and committed-generation queries without
  weakening transaction integrity, foreign keys, canonical accounting, or
  freshness semantics;
- an immutable newline-aligned source boundary per refresh plus an append-safe
  continuation checkpoint, so events written during analysis are handled by a
  later bounded increment instead of moving the active target;
- stale analysis responses that name the active refresh job and can be retried
  deterministically against its completed generation;
- synthetic large-index cold, no-change, small-append, and moving-tail budgets;
  and
- an installed two-task MCP acceptance test covering discovery, refresh join,
  progress, query availability, analysis, evidence, cache reuse, task exit, and
  restart.

## Performance And Freshness Preservation

Interface consolidation is a facade change, not permission to replace focused
Calls, Threads, thread-call, Home, or Limits query plans with broad history
materialization. Stable v2 services must preserve server-side filtering,
sorting, exact matched counts, bounded pagination/expansion, and persisted
cost/credit accounting before their compatibility routes can be removed.

Release gates use synthetic 100,000-row parity and route-budget fixtures for
these workflows. They also prove that an incremental refresh exposes a newly
appended source event and advances the source revision/latest-event timestamp.
A compatibility endpoint cannot be removed while its stable replacement fails
functional parity, performs an unbounded dashboard scan, or regresses the
recorded route budget.

## 0.26 Core Fast-Path Amendment

Public `0.25.1` dogfood proved that installed coherence and small synthetic
append tests were insufficient for a many-task large-index workload. Stable
program `OPS-CORE-026` therefore precedes Task 41 in `0.26.0` and follows the
approved
[core fast-path redesign](../superpowers/plans/2026-07-26-core-fast-path-redesign.md).

The amendment preserves the seven public core tools while:

- making job status operational-sidecar-only and host-waitable;
- making analysis read committed data without implicitly starting refresh;
- committing canonical refresh before optional analytical enrichment;
- adding focused common-query plans; and
- removing retired Compression Lab persistence and compatibility routing.

Canonical accounting, allowance integrity, exact evidence selectors and deep
links, source provenance, compact thread/Home summaries, privacy controls, and
append-active freshness remain required release gates.

## Pre-0.24 Foundation Gate

After Task 27 and the successful `0.23` release gate, Task 27.5
(`ARCH-AUDIT-00`) audits canonical accounting, migrations, table ownership,
transaction boundaries, dependency direction, and public-contract leakage. It
produces `docs/superpowers/reports/0.24-foundation-audit.md` and records exactly
one decision: `PROCEED`, `AMEND`, or `STOP`.

No Task 28-39 implementation work may begin or run in parallel with Task 27.5.
`PROCEED` opens the `0.24` implementation gate. `AMEND` opens it only after
maintainer approval and corresponding roadmap edits. `STOP` blocks the gate and
does not authorize an autonomous rewrite. The `0.24` release gate also requires
no unassigned `BLOCKER` or `HIGH` foundation finding and requires every approved
amendment to be represented in the roadmap.

The sequence is:

```text
Complete 0.23 gate
    -> Task 27.5 foundation audit
    -> PROCEED or approved AMEND
    -> Tasks 28-33 foundation refactor
    -> remaining 0.24 hardening and release gate
    -> OPS-REL-025 reliability and installed-coherence checkpoint
    -> Task 40 static-dashboard sunset and 0.25 gate
    -> 0.26 remaining deletion work beginning at Task 41
    -> 0.27 feature-free stabilization
```

## Compatibility Policy

Compatibility is bounded by [the deprecation ledger](../deprecations.md). An
item cannot be removed before its recorded removal release or while its
compatibility test fails. Semantic changes require an explicit contract revision
or breaking-change notice; aliases must not silently change meaning.

## Execution

Each task uses a focused `pivot/<task-number>-<slug>` branch, starts with the
named failing tests, implements only its declared interfaces, and records
verification and risks in the
[execution ledger](mcp-first-pivot-execution.md). Release, compatibility, schema,
and public-contract changes require an independent reviewer before merge.
Task 28 additionally depends on Task 27.5 recording `PROCEED` or a
maintainer-approved `AMEND`.
Task 40 depends on the committed local reliability checkpoint. Tasks 41-45
additionally depend on the combined `0.25.0` reliability and Task 40 release
completing its installed, concurrency, incremental-refresh, performance, and
exact-byte release gates.
