# CK-08R3 — Qualify evidence service scale

**Status:** Blocked on CK-08R0

**Parent:** Corrective prerequisite for CK-09

**Recommended owner:** `test_engineer evidence-scale`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Prove bounded first/deep evidence pages at standard and
production-shaped scale.

**Why:** Current response bounds do not prove the outer UNION query remains
bounded physically.

**Controls:** Evidence selector/cursor, logical ordering, payload, index, and
query-only contracts.

**Dependencies:** CK-08R0 merged and exact-main verified.

**Owned files/interfaces:** Focused evidence tests, read-only benchmark
workloads, and the dedicated evidence artifact. Production evidence helpers and
service files are forbidden in this qualification task.

**Produces:** Evidence-scale qualification v1 with SQL, EXPLAIN, rows, bytes,
RSS, and p95 samples.

**Independent truth source:** Typed selector/order oracle over synthetic facts.

**Consumer seam:** Actual `EvidenceService` in one query-only snapshot.

**Parallelism:** May run with other Wave-2 lanes; owns only evidence reads.

**Non-goals:** Evidence projection, event backbone, public evidence API, new
indexes without a physical-contract amendment.

**Invariants:** Seven-part cursor order, typed non-placeholder provenance,
stable replacement/late-event behavior, at most 100 rows and 16 KB.

**Required tests/checks:** Every view/scope/direction, ties, late insertion,
replacement, byte truncation, 100k and 1,316,864-call fixtures, `just v/vc`.

**Acceptance:** No gaps/duplicates; first/deep pages and SQL plans meet frozen
budgets at both scales.

**Failure/rollback:** Preserve the first failure. Create a separate
implementation child with its own file and owner, merge it, then rerun this
qualification task. Request a narrow physical amendment when needed; do not
invent `evidence_timeline_current`.

**Handoff:** Evidence digest and direct-versus-projection classification input.

**Cleanup/docs:** Link measurements from CK-08R4 and qualification authority.

**Suggested commit:** `test: qualify evidence service scale`
