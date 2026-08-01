# CK-12-05 — Run exact-artifact and fresh-agent qualification

**Status:** Blocked on CK-12-01

**Parent:** CK-12 umbrella

**Recommended owner:** `test_engineer artifact-agent-lane`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Qualify final wheel/sdist/plugin/skill membership, clean install, and
fresh CLI/Desktop default/lower-model behavior.

**Why:** Source tests and fake harnesses cannot substitute for exact installed
artifacts and fresh agents.

**Controls:** CK-12 candidate and CK-11 scorecard contract.

**Dependencies:** CK-12-01.

**Owned files/interfaces:** Read-only package/install/host execution and lane
evidence; no candidate edits.

**Produces:** Exact-artifact and fresh-agent lane artifact.

**Independent truth source:** Build manifest, prompt oracle, and clean
synthetic workspace.

**Consumer seam:** Exact installed bytes to CLI/Desktop tasks.

**Parallelism:** May run with CK-12-02/03/04.

**Non-goals:** Harness redesign, source fallback, manual grading, public
publication.

**Invariants:** Byte identity, fresh tasks, no real logs, exact catalog/version,
bounded calls/polls/tokens/bytes.

**Required tests/checks:** Wheel/sdist/plugin/skill members, clean install,
default/lower-model matrix, accuracy/usefulness, fresh-answer latency.

**Acceptance:** Exact artifacts install cleanly and every required fresh-agent
gate passes.

**Failure/rollback:** Mark lane unqualified and preserve host availability
limits honestly.

**Handoff:** Lane/artifact hashes and host residuals to CK-12-06.

**Cleanup/docs:** Evidence only.

**Suggested commit:** `test: qualify exact installed candidate`
