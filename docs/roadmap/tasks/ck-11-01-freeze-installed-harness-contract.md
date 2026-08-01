# CK-11-01 — Freeze the installed harness contract

**Status:** Blocked on CK-10-05

**Parent:** CK-11 umbrella

**Recommended owner:** `default harness-contract`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Freeze exact artifact receipts, synthetic workspace boundaries,
host-observation ledger, scorecard, privacy rules, and trial matrix.

**Why:** Fake lifecycle tests, CLI trials, and Desktop trials need one immutable
definition of installed qualification.

**Controls:** CK-10 bundle, qualification plan, prompt/oracle catalog.

**Dependencies:** CK-10-05 merged and exact-main verified.

**Owned files/interfaces:** Harness schemas/interfaces and qualification
contract; no host launch implementation.

**Produces:** Versioned installed-harness contract.

**Independent truth source:** Qualification plan and synthetic lifecycle cases.

**Consumer seam:** Artifact/CLI runner, Desktop/lower-model runner, aggregator.

**Parallelism:** Serialized freeze.

**Non-goals:** Claiming installed qualification, real user data, transcript
storage, source-checkout fallback.

**Invariants:** Exact hashes, fresh tasks, separate install/handshake/exposure
states, bounded body-free observations.

**Required tests/checks:** Schema validation, complete run matrix, privacy
denylists, fake receipt fixtures, `just v/vc`, reviewer.

**Acceptance:** Every trial has closed inputs, observations, deadlines,
cleanup, and scoring rules.

**Failure/rollback:** Keep CK-11 blocked.

**Handoff:** Contract digest and disjoint runner ownership.

**Cleanup/docs:** Reconcile qualification authority.

**Suggested commit:** `docs: freeze installed harness contract`
