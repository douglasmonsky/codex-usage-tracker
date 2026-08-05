# CK-08R4 — Reclassify physical named plans

**Status:** Blocked on CK-08R1 and CK-07R1; CK-08R2 and CK-08R3 are complete

**Parent:** Corrective prerequisite for CK-09

**Recommended owner:** `default physical-reclassification`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Produce the sole CK-09 admission input from corrected runtime and
publication-valid measurements.

**Why:** The provisional 18-plan list combines stages and cannot authorize
write-amplifying projections.

**Controls:** CK-08R0 benchmark-v2 schema and all completed corrective evidence.

**Dependencies:** CK-08R1/R2/R3 and CK-07R1 merged and exact-main verified.

**Owned files/interfaces:** Benchmark/collector v2, scale evidence v2,
projection-admission record, affected packet claims; no projections.

**Produces:** Immutable `projection-admission-v2`.

**Independent truth source:** CK-08R1 answers and publication-valid synthetic
databases.

**Consumer seam:** Actual runtime query/evidence services and CK-09 registry
freeze.

**Parallelism:** Serialized integration task.

**Non-goals:** Projection implementation, guessed counts, standard-only
classification, or compiler time labeled as SQLite time.

**Invariants:** Preserve first noisy/failing runs; bind commit, fixture/schema
digests, SQL, EXPLAIN, rows, bytes, RSS, storage/WAL, and repetitions.

**Required tests/checks:** All 21 plans at standard and production shape,
stage-separated p95, direct/evidence/projection classes, admission rules,
`just v/vc`.

**Acceptance:** Every plan is measured and classified as direct-page,
evidence-page, or projection-required; every proposed projection satisfies all
admission rules.

**Failure/rollback:** Any unmeasured/unbounded plan keeps CK-09 blocked.

**Handoff:** Exact admitted candidates, consumers, dirty keys, budgets, and
evidence digest.

**Cleanup/docs:** Preserve v1 as superseded history and link amendments.

**Suggested commit:** `test: reclassify physical named plans`
