# CK-08R2 — Implement bounded physical keyset execution

**Status:** Completed on merge; exact-main verification required in handoff

**Parent:** Corrective prerequisite for CK-09

**Recommended owner:** `default physical-paging`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Execute ordering, keyset predicates, and `LIMIT page_size + 1` before
Python materialization for every direct runtime plan.

**Why:** Slicing a fully evaluated result produces bounded responses but not
bounded deep-page work.

**Controls:** Frozen page-executor contract, plan operands, ordering, cursor,
query-only, and database-v1 contracts.

**Dependencies:** CK-08R0 merged and exact-main verified.

**Owned files/interfaces:** Query contracts, compiler, registry, service, and
focused query/cursor tests under the query physical lock.

**Produces:** Versioned page-execution seam and runtime plan evidence.

**Independent truth source:** R0-frozen structural paging/order vectors plus
direct SQL order and EXPLAIN assertions. CK-08R1 semantic comparison is
consumed later by CK-08R4, not by this parallel implementation lane.

**Consumer seam:** `QueryService` on one query-only snapshot.

**Parallelism:** May run with non-query Wave-2 lanes. No projection or shared
architecture edits.

**Non-goals:** Generic SQL, arbitrary fragments, new projections, complete
result sorting in Python, or public interface work.

**Invariants:** Stable signed cursor bindings, total order, no gaps/duplicates,
exact-count opt-in, fail-closed unknown plans, one read snapshot.

**Required tests/checks:** First/deep pages, ties, tamper/replacement/stale
cursors, count opt-in, query-only denial, EXPLAIN shapes, scale, `just v/vc`.

**Acceptance:** Runtime never calls full `evaluate_plan`; page work is
proportional; accepted direct plans meet correctness, payload, and latency.

**Failure/rollback:** Leave unsupported plans unimplemented and record the
exact index/physical gap; do not add a projection.

**Handoff:** Physical executor version, supported direct-plan list, plans and
measurements.

**Cleanup/docs:** Update query contracts and linked CK-08 evidence amendment.

**Suggested commit:** `feat: execute bounded query pages`

## Implementation and qualification record

CK-08R2 replaces the query service's production `evaluate_plan` and
complete-result Python slicing path with `PhysicalPageExecutor` version 2. The
service binds a signed cursor before SQL, executes one publication-bound
query in the caller-owned query-only snapshot, applies the authoritative total
order and `LIMIT page_size + 1`, and decodes at most 101 rows. Exact counts
remain opt-in and execute no `COUNT` statement by default.

The admitted direct runtime set is deliberately narrow:
`latest_publication_delta` and `data_health`. Both preserve their frozen answer
rows and direct primary-key EXPLAIN paths. They are single-row plans, so the
deep-page evidence validates the signed current anchor and returns the empty
page after it. The independent typed order vector separately proves
lexicographic traversal through equal primary-order values. No multi-row plan
is claimed physically supported.

The other 19 admitted plans fail closed with their plan ID, complete-order
physical/index gap, and `projection_added=false`. In particular,
`resource_hotspots` remains unimplemented because database-v1 has
resource-keyed indexes but no index for the complete
`operation_count_desc,resource_id_asc` aggregate order; executing it would
require a complete aggregate scan and temporary sort. CK-08R2 adds no
projection and does not classify those residual plans for CK-09.

Synthetic five-run evidence:

- [`data-health-page-executor-benchmark-v2.json`](../../decisions/evidence/ck08r2/data-health-page-executor-benchmark-v2.json)
  — SHA-256
  `8ca52e40ad03d8bb8056ec2ca0d8a3ac7f58d3a4f1adf8daad7d8df6d87a0a3f`;
- [`latest-publication-delta-page-executor-benchmark-v2.json`](../../decisions/evidence/ck08r2/latest-publication-delta-page-executor-benchmark-v2.json)
  — SHA-256
  `6f897a9ca6f7c52f39c31d56e7943a621758feac3df22d0f0b6dbdc50f0d5604`.

Both validate as `codex-usage-tracker.page-executor-benchmark.v2` through
`corrective-lane-evidence-v1.schema.json#/$defs/pageExecutor`, bind CK-08R0
dependency `306cef37eea2ae017aca824d898cc435f7e1bea0`, retain five separate
bind/SQL/decode/assembly/serialization samples, and preserve the known
Candidate A and allowance-read timing noise without weakening a gate.

The unprofiled synthetic collector completed in 0.30 seconds on the recorded
workstation. Pinned `agent-perf` run
`20260801T032354Z-9cb681f6` mapped the only reported application hotspot to
`PhysicalPageExecutor.execute` with 2.03% self/inclusive sample share. That
profile is attribution evidence, not a speedup claim.

The wheel remains below its unchanged 383,000-byte ceiling. Acceptance builds
observed 826,506 through 826,720-byte sdists, so the ratchet moves from 820,000
to 828,000 bytes with at least 0.154829% headroom over the largest observed
artifact and below the frozen 25% maximum. The bounded range avoids a false
self-referential exact-byte claim because embedding that number changes the
compressed artifact. The R2 manifest binds the before/after budget digests and
semantic attribution.

Focused qualification covers sizes 1 and 100, rejection at 101, first/deep
pages, tie order, HMAC tamper, publication replacement, stale anchors,
query-only denial, exact-count opt-in, EXPLAIN shape, all unsupported plan
gaps, and a guard that production `evaluate_plan` is never called. Broad
`just v` / `just vc`, the one final reviewer, hosted CI, merge, and retained
exact-main verification are recorded in the completion handoff.
