# CK-12-06 — Integrate the hardening decision

**Status:** Blocked on CK-12-02, CK-12-03, CK-12-04, and CK-12-05

**Parent:** CK-12 umbrella

**Recommended owner:** `default hardening-decision`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Integrate lane evidence, correct only demonstrated defects through
narrow follow-ups, rerun affected gates, and accept or block the MVP.

**Why:** Qualification must not let workers modify the premise they measure or
convert hard failures to caveats.

**Controls:** Immutable candidate and all CK-12 lane artifacts.

**Dependencies:** CK-12-02/03/04/05 completed.

**Owned files/interfaces:** Defect routing, accepted focused integrations,
final evidence, parent/ledger status, one final review.

**Produces:** CK-12 qualification decision and exact candidate manifest.

**Independent truth source:** Lane artifacts and rerun evidence.

**Consumer seam:** CK-13 cutover preparation.

**Parallelism:** Serialized. A failed lane creates a new disjoint task; after a
semantic fix, affected lanes rerun on a newly frozen candidate.

**Non-goals:** Broad redesign, new features, gate weakening, CK-13 changes.

**Invariants:** No unresolved accepted review finding; exact artifacts; first
failures retained; all affected matrices rerun.

**Required tests/checks:** Full L0-L5 plus recovery, exact package, fresh-agent,
`just v/vc`, hosted CI, one reviewer, exact-main.

**Acceptance:** Every hard gate passes and residual host/model limits are
disclosed; otherwise CK-13 remains blocked.

**Failure/rollback:** Candidate stays disabled; create bounded corrective task.

**Handoff:** PR, merged SHA, all evidence hashes, reviewer status, CK-13-01
readiness or exact blocker.

**Cleanup/docs:** Reconcile qualification, parent, roadmap, ledger, index.

**Suggested commit:** `test: accept qualified agent kernel candidate`
