# CK-13-03 — Verify cutover and approve runtime retirement

**Status:** Blocked on CK-13-02

**Parent:** CK-13 umbrella

**Recommended owner:** `default cutover-verification`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Run side-by-side cutover/rollback and obtain the explicit CK-14
runtime-retirement checkpoint.

**Why:** Legacy deletion is irreversible enough to require proven rollback and
maintainer approval.

**Controls:** CK-13-01 drill and CK-13-02 configuration.

**Dependencies:** CK-13-02 merged and exact-main verified.

**Owned files/interfaces:** Drill execution, cutover evidence, parent/ledger
status, approval record; no deletion.

**Produces:** G6 cutover and retirement authorization.

**Independent truth source:** Synthetic question oracle plus file/database
hashes.

**Consumer seam:** New default surface, separate databases, 0.28 reinstall.

**Parallelism:** Serialized; blocks all CK-14 work.

**Non-goals:** Deletion, release, compatibility shim.

**Invariants:** Spike remains untouched; rollback is external reinstall/select,
not migration; identical synthetic source with separate databases.

**Required tests/checks:** Setup/tails/queries/catalog/errors, rollback
reinstall, path scans, `just v/vc`, hosted CI, reviewer, exact-main.

**Acceptance:** Cutover and rollback pass and maintainer explicitly approves
retirement.

**Failure/rollback:** Restore 0.28 default and keep CK-14 blocked.

**Handoff:** Approval, evidence digest, merged SHA, CK-14-01 readiness.

**Cleanup/docs:** Reconcile parent, ledger, roadmap, user cutover message.

**Suggested commit:** `test: verify clean cutover rollback`
