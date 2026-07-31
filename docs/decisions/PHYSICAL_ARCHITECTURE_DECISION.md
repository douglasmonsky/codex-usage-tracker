# Physical Architecture Decision

**Status:** Accepted with an explicit growth-evidence exception
**Decision date:** 2026-07-30
**Selected direction:** Candidate A mechanisms
**Decision evidence commit:** `95492032373beeaa700af90b542a0a07f4220c74`
**Production schema contract:**
[AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md](../architecture/AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md)
(`1a2dcffe778633457bbeb60dd3a41c233a78c15af2a3393bf9cacc1d9e645bb5`)
**Evidence exception:**
[aggregate-evidence.json](evidence/ck04/aggregate-evidence.json)

## Decision

Candidate A is the selected physical direction for the agent-kernel v1
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
transplant. CK-05 starts a clean implementation under
`src/codex_usage_tracker/agent_kernel/` and imports nothing from the
experimental candidates or the spike runtime.

## Acceptance outcome

The first qualification pass selected Candidate A after eliminating Candidates
C and D. The final read-only review found seven gaps that prevented acceptance.
Six remediations remain accepted. CK-07B supplies executable formula and
selector-provenance authority. CK-07C supplies the executable plan-to-operand
and direct-fact bindings plus the smallest missing canonical fact surfaces
discovered during CK-07A. CK-07A now replaces the query-correctness
remediation because its
database-resident answer source did not prove canonical-fact lineage:

| Review gap | Remediation |
| --- | --- |
| Recovery used simulated outcomes | The 25-case matrix now observes real termination or injected faults, inspects persistent state, proves rollback, and performs a subsequent publication. |
| Query results were assembled from oracle rows | CK-07A replaced the candidate-only `question_cases` lane with 80 / 80 structural-v2 replays through permitted database-v1 facts, executable plans, and independent evaluators. |
| Planner checks were aggregate-only | Every query case now fails on unapproved full scans, automatic indexes, or temporary sorts. |
| Parser-worker cases ignored worker count | The worker cases now execute bounded spawned 1/2/4/8-worker parsing with deterministic parent-writer merge. |
| CPU profile did not match the speed workload | Agent Perf now profiles the exact checked-in standard-build workload; repeated unprofiled runs remain the speed authority. |
| Production DDL was incomplete | A complete database-v1 schema, index, cursor, coverage, delta, and publication contract is frozen separately. |
| Decision evidence was not reproducible enough | A strict bounded v2 manifest validator rejects missing, stale, non-canonical, private, or invented evidence. |

Candidates C and D are eliminated by current evidence:
Candidate C did not perform the required process termination, and Candidate D
exceeded the production 30-day `5 s` hard gate.

Candidate A passed the current-commit standard, production, history, expansion,
ordinary-tail, crash/recovery, Agent Perf, and DBHub lanes. Its query planner
and performance measurements completed; CK-07A now accepts query correctness
after replaying the corrected fixture and recomputing affected selection
evidence. The
maintainer directed CK-04 to stop after growth repetition 2, yielding three
successful current-commit growth samples. Repetitions 3 and 4 are explicitly
waived because their additional runtime was disproportionate to the remaining
decision value.

This exception does not rewrite the evidence contract. The strict canonical v2
aggregate is intentionally not emitted because its five-current-repetition
growth requirement is unsatisfied. The exception artifact authenticates the
three current samples and the earlier complete five-run bundle. Candidate A's
experimental implementation and shared implementation have identical Git tree
identities across those two commits. The earlier bundle is corroboration, not
a same-commit substitute.

## Requalification record

The accepted evidence at
`95492032373beeaa700af90b542a0a07f4220c74` records:

| Lane | Result | Canonical summary digest |
| --- | --- | --- |
| Standard workload | 365 / 365 passed | `496336d432557a6feb227950bef81465e9f22df0917f1d5dbf27794e3d7038db` |
| Production scale and tail | 395 / 395 passed | `f74688fa78352589563536c339c3da09e97fadf0da310055642d474234e3b50c` |
| Short history | 15 / 15 passed | `147a00de01af36a7349259582c81654fb4f5a3709ab9262a36da907d5ee30d9b` |
| All-time history | 5 / 5 passed | `4a531a455b35b5b6d7f09b12bd4be242abb73fd41f1192646cf7e2c34b1c5157` |
| History expansion | 15 / 15 passed | `2d65a5f2b420e14b496acf50ba45f1e9fcab5a0c3803e9f23076d597c5955ba2` |
| Query correctness | 80 / 80 fact-backed variants passed; eligible-only score `100`, rank 1; standard/production/growth sensitivity remains Candidate A | [CK-07A evidence](evidence/ck07a/fact-backed-oracle-and-seam-qualification-evidence.json) |
| Crash and recovery | 25 / 25 passed | `9b697b6f882056a3cb393d3f10ac9f3954f933f6b74a86c23a39e4d3c0c1fc71` |
| Candidate C elimination | Expected process-termination observation absent | retained current-commit artifact |
| Candidate D elimination | Expected production build watchdog failure | retained current-commit artifact |
| Agent Perf | Five unprofiled runs plus one attribution profile | retained current-commit artifact |
| DBHub 0.24.0 | Ten alternating samples; identical snapshot | retained current-commit artifact |
| Growth sensitivity | Three current samples passed; two waived | exception artifact |

Profiled measurements are attribution only. Raw outputs remain ignored under
`experiments/physical-architecture/.measurements/`. No canonical aggregate is
claimed. The committed bounded exception artifact records exact input hashes,
current and prior commits, tree identities, completed repetitions, the
explicit limitation, and the risks carried into CK-05 and CK-06.

## Selected physical contract

### Identity and order

Stable public logical IDs remain collision-checked hashes defined by the
logical contract. SQLite row IDs are never evidence selectors.

The authoritative evidence order is:

```text
(
  event_at_us IS NULL ASC,
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

The bake-off query adapter's original answer path read candidate-only
`question_cases` rows populated from `oracle_case.observed_facts`. CK-07A
replaced that invalid correctness lane with Candidate A's query-only,
authorizer-enforced database-v1 fact/planner entry point and 80 / 80 exact
structural-v2 comparisons. Historical planner/performance evidence remains
physical evidence; current correctness authority is the CK-07A artifact.

Candidate A remains an experimental physical-plan reference, not production
code to transplant. CK-08 may now implement production query code from the
requalified contracts. Any false-zero, expected-answer table, or oracle-backed
runtime answer remains a release blocker.

## Agent Perf result

The Agent Perf contract is the exact checked-in 100,000-call
`build.scale.standard` workload. The accepted attribution run used Agent Perf
with Scalene `2.3.0`; `_insert_record` was the largest Python hotspot at
`6.21%`. Its five matching unprofiled samples ranged from `7.13 s` to
`7.28 s`. The unprofiled samples are the speed authority; the profile is
attribution only.

## DBHub disposition

DBHub `0.24.0` remains a pinned dev-only schema and query-plan research tool.
CK-04 owns exactly two deliberately executed local routes: generic schema
search plus read SQL, and the named `top_sessions` preset. The final v2
manifest must record five samples for each route, global sequence indexes
`0..9` in alternating route order, wall time, process CPU, response bytes,
result rows/hash, correctness, and exact MCP calls (two generic, one named).
Scanned rows and SQL statements are observed/unavailable provenance objects;
returned rows and assumed route shape are not substitutes. Whenever unavailable
or deferred, `limitations` explicitly names `dbhub.scanned_rows`,
`dbhub.sql_statements`, or `dbhub.model_operability`, respectively.

Generic SQL is not a product dependency. The named-plan registry remains the
runtime direction because it requires fewer calls and schema bytes, preserves
grades and formulas, and bounds rows.

This benchmark does not establish model route selection or installed-model
operability: the current runner invokes no model. Exact model identity,
host/runtime versions, reasoning effort, exact synthetic-prompt artifact
identity/hash, token source, and authorization for billed calls were never
frozen. The manifest records this as a deferred CK-11 operability requirement.

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
| Growth-scale build cost and I/O variance | Three current-commit repetitions and one prior complete bundle passed, but two current repetitions were waived. CK-05/CK-06 benchmark streaming, batching, compact SQLite, and truthful progress against the same fixture. |
| Build RSS | CK-06 proves bounded streaming and queue depth; no whole-history materialization. |
| Fact-backed query qualification | CK-07B freezes formula and provenance authority. CK-07C freezes executable plan operands/direct facts and the required valuation, context, allowance, hierarchy, total-order, and publication fact representations. CK-07D makes that valuation effective-dated per call and requalifies the affected CK-05/CK-07/CK-07C seams. CK-07A then replaces Candidate A's `question_cases` proof, reconciles independent expected rows to canonical published facts, and requalifies CK-03–CK-07 before CK-08/CK-09. |
| Tail overlay has no production fold path | CK-07 implements and crash-qualifies threshold-driven fold or isolated-artifact selection. |
| Experimental promotion is not durably atomic | CK-07 implements fsync, pointer, lease, rollback, reconciliation, and protected cleanup. |
| Installed-model DBHub operability is deferred | CK-11 records exact model identity, host/runtime versions, reasoning effort, synthetic-prompt artifact identity/hash, token source, and authorization before any billed call. |

No residual risk permits weakening a roadmap hard gate.
