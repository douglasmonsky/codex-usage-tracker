# Physical Architecture Decision

**Status:** Remediation implemented; clean requalification pending
**Decision date:** Pending final CK-04 qualification
**Provisional direction:** Candidate A mechanisms
**Decision commit:** Pending
**Production schema contract:**
[AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md](../architecture/AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md)
(`eecff68062a8d0cba0619058a6e660f565d9a96c2575ab0dc93d72b987f31543`)
**Aggregate evidence:** Pending canonical v2 manifest

## Provisional decision

Candidate A remains the provisional physical direction for the agent-kernel v1
production implementation:

- typed canonical fact and lifecycle tables;
- physical source occurrences distinct from canonical entities;
- integer UTC microseconds and an explicit composite total order;
- current-only dirty-key projections;
- a bounded append overlay for ordinary tails;
- indexed, keyset-paginated merging of typed evidence streams;
- a short WAL transaction for proven-small safe changes;
- isolated artifacts plus an atomic active pointer for large or unsafe work.

Candidate A is a **design and contract reference**, not production code to
transplant. If clean requalification confirms its eligibility, CK-05 starts a
clean implementation under `src/codex_usage_tracker/agent_kernel/` and imports
nothing from the experimental candidates or the spike runtime.

## Why the decision is not yet accepted

The first qualification pass selected Candidate A after eliminating Candidates
C and D. The final read-only review found seven gaps that prevented acceptance.
All seven remediations are implemented:

| Review gap | Remediation |
| --- | --- |
| Recovery used simulated outcomes | The 25-case matrix now observes real termination or injected faults, inspects persistent state, proves rollback, and performs a subsequent publication. |
| Query results were assembled from oracle rows | Candidate A now returns database-derived rows; fixture-oracle rows are comparison truth only. |
| Planner checks were aggregate-only | Every query case now fails on unapproved full scans, automatic indexes, or temporary sorts. |
| Parser-worker cases ignored worker count | The worker cases now execute bounded spawned 1/2/4/8-worker parsing with deterministic parent-writer merge. |
| CPU profile did not match the speed workload | Agent Perf now profiles the exact checked-in standard-build workload; repeated unprofiled runs remain the speed authority. |
| Production DDL was incomplete | A complete database-v1 schema, index, cursor, coverage, delta, and publication contract is frozen separately. |
| Decision evidence was not reproducible enough | A strict bounded v2 manifest validator rejects missing, stale, non-canonical, private, or invented evidence. |

Candidates C and D remain historically eliminated by unchanged evidence:
Candidate C did not perform the required process termination, and Candidate D
exceeded the production 30-day `5 s` hard gate. Candidate A is not called
eligible again until the remediated code is committed, the canonical clean
runner finishes, and the v2 evidence manifest validates.

## Requalification gate

The acceptance commit must record five unprofiled repetitions for every speed
claim on the exact clean code commit, including:

- the 100,000-call standard build;
- production 30-day, 90-day, one-year, and all-time builds;
- the required ordinary tails;
- all required SQL- and MCP-shaped query cases;
- the complete recovery matrix;
- the 2,500,000-call growth sensitivity;
- the pinned DBHub comparison;
- exact Agent Perf attribution for the checked-in standard workload.

Profiled measurements are attribution only. Raw outputs remain ignored under
`experiments/physical-architecture/.measurements/`. The committed aggregate
contains only bounded canonical evidence with exact input/output hashes,
environment identity, score derivation, plan allowances and observations,
crash proof, Agent Perf attribution, DBHub comparison, and explicit
limitations.

## Selected physical contract

### Identity and order

Stable public logical IDs remain collision-checked hashes defined by the
logical contract. SQLite row IDs are never evidence selectors.

The authoritative evidence order is:

```text
(
  event_at_us,
  source_rank,
  source_order,
  event_kind_order,
  logical_id,
  transition_rank
)
```

Every component is deterministic. An occurrence coordinate retains source
manifestation, source revision, adapter version, record ordinal, and byte
range. A canonical entity can have multiple physical occurrences without
becoming multiple usage facts.

### Production database-v1 authority

The production schema contract is
[`AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md`](../architecture/AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md).
It freezes the complete ordered analytical and operational inventories,
columns, types, nullability, defaults, keys, checks, indexes, cursor and
coverage semantics, lifecycle folds, publication deltas, pointer and rollback
semantics, and packet ownership.

Candidate A's `oracle_case` and source-phase instrumentation are harness-only
and forbidden from the production schema. Candidate A's physical schema digest
is `31b33e9efe24c458a528f2cc6930379028cd3bf40e9df0b79825290d61d85f09`;
it is evidence identity, not production DDL authority.

### Lifecycle representation

Sessions and tools retain typed start and terminal state in their canonical
rows. The terminal observation retains its own occurrence coordinate.
Open, complete, fail, and cancel are observations, not inferences from absence.

Late parent discovery is represented separately so hierarchy repair does not
rewrite activity timestamps or create usage. State changes remain observations
distinct from write intent and successful tool completion; they do not assign
causality to one adjacent call.

### Ordinary-tail overlay

CK-07 owns a bounded append-only overlay for ordinary tails. The experimental
`32,000`-row ceiling is an initial maximum, not permission to let every query
degrade to a permanent union. Reaching a measured row, byte, or fanout threshold
selects a folded or isolated-artifact path before the write begins.

Deletes or updates to the append overlay fail closed. Lifecycle terminalization
updates the typed lifecycle row inside the same short publication transaction.

### Evidence

Evidence pages merge indexed typed streams by the authoritative total order.
The merge is bounded by page size, uses a publication-bound keyset cursor, and
does not require a global event-backbone or sequence table.

Candidate A's measured page-anchor shape remains a conditional deep-page
optimization. CK-08 may add it only when a named consumer proves the need.
Stable logical selectors and occurrence coordinates are mandatory regardless
of whether anchors are admitted.

### Projections

Candidate A proved current-only candidate shapes for session usage, global
usage, model and effort, project family, turns, resource operations, tool
family, and optional evidence anchors. CK-09 admits a projection and rank index
only when an executable named-plan consumer demonstrates the latency benefit
and dirty-key maintenance passes the write-fanout gate.

No projection is copied per generation. Current projections, publication
identity, canonical facts, coverage, and evidence resolve from one SQLite read
snapshot.

### Publication and recovery

The production mechanism is two-path:

1. A no-change plan performs no analytical write.
2. A proven-small safe tail uses one short WAL transaction and updates bounded
   facts, lifecycle rows, dirty projections, coverage, and publication identity
   atomically.
3. A large append, history expansion, replacement, recanonicalization, or
   schema/projection upgrade builds a unique owner-only artifact while readers
   continue using the active artifact.
4. The candidate artifact is validated, checkpointed, digested, file-synced,
   and directory-synced before promotion.
5. Promotion atomically replaces a small active pointer, retains the prior
   valid artifact as rollback, and then reconciles the operational sidecar.

The operational sidecar remains separate from analytical truth. Startup
validates active and rollback pointer/artifact pairs before attempting sidecar
writes. Reads open first. An interrupted sidecar recovery can never make a
valid analytical publication unavailable.

The experiment's direct file replacement, POSIX-only lock, and simplified
sidecar are not production implementations. CK-07 owns durable pointer, lease,
fsync, rollback, reconciliation, and protected-cleanup behavior.

## Query qualification

The bake-off query adapter executes and profiles real Candidate A SQL and
constructs its returned envelope only from persisted, source-derived facts.
CK-03 fixture-oracle rows remain independent comparison truth used to grade
answer equivalence. Per-case planner allowances fail closed on unapproved full
scans, automatic indexes, and temporary sorts.

Candidate A remains an experimental physical-plan reference. CK-08 and CK-09
must implement production query code independently and rerun the unchanged
oracles; a false-zero or oracle-backed runtime answer remains a release
blocker.

## Agent Perf result

The remediated Agent Perf contract is the exact checked-in 100,000-call
`build.scale.standard` workload. The most recent attribution run used
Agent Perf with Scalene `2.3.0`; `_insert_record` was the largest Python
hotspot at `8.30%`. Its five matching unprofiled samples ranged from `7.07 s`
to `7.34 s`.

Those samples confirm that the remediation changed build cost materially and
invalidated the earlier production timing claims. The clean requalification
owns the authoritative speed baseline.

## DBHub disposition

DBHub `0.24.0` remains a pinned dev-only schema and query-plan research tool.
The earlier bakeoff returned the same bounded result through generic and named
routes, and both model classes selected the named route. The final v2 manifest
must record five samples for each route/model combination, wall time, process
CPU, scanned rows, SQL statements, MCP calls, response bytes, correctness, and
the explicit unavailability of model-token telemetry.

Generic SQL is not a product dependency. The named-plan registry remains the
runtime direction because it requires fewer calls and schema bytes, preserves
grades and formulas, bounds rows, and remains operable by less-capable models.

## Rejected alternatives

### Candidate C

Its immutable event backbone provides one sequence authority, but the candidate
failed the required process-termination crash contract. It also adds duplicated
order keys and backbone joins to common aggregate paths.

### Candidate D

Its compact sequence index makes evidence traversal straightforward, but the
additional synchronized write path did not meet the production 30-day
first-publication gate. Correctness and prior-publication survival do not
override the hard first-use gate.

### Semantic Kernel or another orchestration framework

Codex owns the model loop and tool orchestration. Another framework would add
dependencies and host coupling without improving the local fact kernel.
Typed contracts and adapter boundaries are retained ideas, not a dependency.

## Residual risks and required follow-ups

| Risk | Required owner |
| --- | --- |
| Growth-scale build cost and I/O variance | CK-04 reruns the remediated growth sensitivity; CK-05/CK-06 then benchmark streaming, batching, compact SQLite, and truthful progress against the same fixture. |
| Build RSS | CK-06 proves bounded streaming and queue depth; no whole-history materialization. |
| Production query implementation | CK-08/CK-09 independently return database-derived rows and rerun every CK-03 oracle. |
| Tail overlay has no production fold path | CK-07 implements and crash-qualifies threshold-driven fold or isolated-artifact selection. |
| Experimental promotion is not durably atomic | CK-07 implements fsync, pointer, lease, rollback, reconciliation, and protected cleanup. |
| Model tokens are unavailable in DBHub trials | CK-11 records exact installed-agent model and tool-call token telemetry. |

No residual risk permits weakening a roadmap hard gate.
