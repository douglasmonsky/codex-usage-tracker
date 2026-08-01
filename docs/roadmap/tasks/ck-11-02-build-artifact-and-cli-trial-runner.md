# CK-11-02 — Build artifact and CLI trial runner

**Status:** Blocked on CK-11-01

**Parent:** CK-11 umbrella

**Recommended owner:** `test_engineer cli-trials`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Install one exact bundle into an isolated workspace and run bounded
fresh CLI trials with deterministic lifecycle cleanup.

**Why:** Source-level tests do not prove the installed artifact or fresh host.

**Controls:** CK-11-01 and exact CK-10 bundle.

**Dependencies:** CK-11-01 merged and exact-main verified.

**Owned files/interfaces:** Artifact/workspace helpers, fake lifecycle harness,
CLI adapter, focused tests.

**Produces:** Exact install receipts and CLI observation records.

**Independent truth source:** Build manifest and prompt/question oracle.

**Consumer seam:** Installed distribution to fresh Codex CLI task.

**Parallelism:** May run with CK-11-03; shared scorecard remains integrator-owned.

**Non-goals:** Desktop launch, aggregate scoring, checkout/symlink fallback, or
real logs.

**Invariants:** Timeouts, cancellation recheck, cleanup, no ambient database,
bounded body-free observations.

**Required tests/checks:** Fake timeout/crash/duplicate ID, exact hashes,
fresh-task exposure, calls/tokens/bytes/answers, `just v/vc`.

**Acceptance:** Every required CLI trial yields a valid terminal record or an
honest unavailable outcome.

**Failure/rollback:** Keep CLI lane unqualified; retain exact failure receipt.

**Handoff:** Install and CLI record digests to CK-11-04.

**Cleanup/docs:** Runner operator notes only.

**Suggested commit:** `test: add exact cli trial runner`
