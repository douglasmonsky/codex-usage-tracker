# CK-12-03 — Run performance, storage, and payload qualification

**Status:** Blocked on CK-12-01

**Parent:** CK-12 umbrella

**Recommended owner:** `test_engineer performance-lane`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Measure build, tail, query, evidence, storage, WAL, package, response,
RSS, fanout, and payload gates on the immutable candidate.

**Why:** Speed claims and projection costs require stage-specific attribution.

**Controls:** CK-12 candidate, CI performance policy, physical and qualification
budgets.

**Dependencies:** CK-12-01.

**Owned files/interfaces:** Read-only workloads, profiles, and lane evidence;
no candidate edits.

**Produces:** Performance/storage/payload artifact with all raw samples.

**Independent truth source:** Deterministic synthetic workloads and fixed
budgets.

**Consumer seam:** Actual publication, query, packaging, and installed response
paths.

**Parallelism:** May run with CK-12-02/04/05 on identical candidate.

**Non-goals:** Optimization, rerun hiding, gate waiver, semantic fixes.

**Invariants:** Identical profiled/unprofiled workload, five required samples,
first breach retained, correct stage labels.

**Required tests/checks:** 100k/1.316M/growth, 30-day/all-time, p95, exact-count
cost, storage/WAL/fanout, bytes, Agent Perf attribution.

**Acceptance:** Every pinned hard budget and accepted ratchet passes.

**Failure/rollback:** Retain first result and stop; no automatic waiver.

**Handoff:** Lane digest, raw samples, profiles and breach attribution.

**Cleanup/docs:** Evidence only.

**Suggested commit:** `test: qualify candidate performance`
