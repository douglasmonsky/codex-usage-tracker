# CK-11-03 — Build Desktop and lower-model trial runner

**Status:** Blocked on CK-11-01

**Parent:** CK-11 umbrella

**Recommended owner:** `test_engineer desktop-trials`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Run fresh Desktop and required lower-model installed trials through
the frozen observation contract.

**Why:** CLI/default-model success cannot substitute for the remaining host and
model matrix.

**Controls:** CK-11-01 and exact CK-10 bundle.

**Dependencies:** CK-11-01 merged and exact-main verified; exact install helper
interface from the freeze.

**Owned files/interfaces:** Desktop host adapter, lower-model trial helper, and
focused tests.

**Produces:** Desktop/lower-model observation records.

**Independent truth source:** Prompt/question oracle and exact artifact receipt.

**Consumer seam:** Fresh Desktop task and selected lower-model hosts.

**Parallelism:** May run with CK-11-02; no scorecard schema/aggregate edits.

**Non-goals:** Manual transcript interpretation, fake-only pass, public
release, or real user data.

**Invariants:** Fresh task, bounded deadline, cleanup, no side channel, exact
artifact/catalog identity.

**Required tests/checks:** Launcher fakes, exposure, operation selection,
answers/grades/selectors, calls/polls/tokens/bytes, `just v/vc`.

**Acceptance:** Required records are complete; unavailable capability is
reported, never converted to pass.

**Failure/rollback:** Leave the affected host/model unqualified.

**Handoff:** Observation digests and residual capability limits to CK-11-04.

**Cleanup/docs:** Runner operator notes only.

**Suggested commit:** `test: add desktop agent trials`
