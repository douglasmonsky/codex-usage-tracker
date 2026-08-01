# CK-11-04 — Integrate installed-agent scorecard

**Status:** Blocked on CK-11-02 and CK-11-03

**Parent:** CK-11 umbrella

**Recommended owner:** `default installed-scorecard`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Score the complete installed trial matrix and close CK-11 from one
exact artifact bundle.

**Why:** Individual host records need deterministic privacy-safe aggregation.

**Controls:** CK-11-01 schema and all runner records.

**Dependencies:** CK-11-02/03 accepted.

**Owned files/interfaces:** Scorer, top-level command, evidence aggregate,
operator docs, parent/ledger status.

**Produces:** Closed installed-agent scorecard.

**Independent truth source:** Question oracle and immutable artifact manifest.

**Consumer seam:** Runner observations to CK-12 candidate freeze.

**Parallelism:** Serialized integration and one final reviewer.

**Non-goals:** Harness redesign, transcript grading, runtime fixes, CK-12 work.

**Invariants:** Exact matrix, deterministic aggregates, no raw prompts or
responses persisted, unavailable is not pass.

**Required tests/checks:** Complete records, score schema, privacy, accuracy,
calls/polls/retries/bytes/tokens, `just v/vc`, CI, exact-main.

**Acceptance:** One command emits a valid scorecard for exact installed
artifacts and all required fresh trials.

**Failure/rollback:** Keep CK-11 blocked and bundle unqualified.

**Handoff:** PR, merged SHA, scorecard/artifact digests, residuals, CK-12-01
readiness.

**Cleanup/docs:** Reconcile parent, ledger, roadmap, qualification plan.

**Suggested commit:** `test: integrate installed agent scorecard`
