# CK-16-03 — Build once and qualify release candidate

**Status:** Blocked on CK-16-02 and selected CK-15-02

**Parent:** CK-16 umbrella

**Recommended owner:** `default release-candidate`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Integrate release metadata, build one artifact set from exact merged
main/tag, and qualify the bytes without publishing.

**Why:** Qualification must apply to the exact bytes later promoted.

**Controls:** CK-16-01, public docs, release workflow and qualification policy.

**Dependencies:** CK-16-02 and CK-15-02 only when selected.

**Owned files/interfaces:** Version constants, changelog, publish workflow,
release code/config/tests, artifact manifest.

**Produces:** Build-once wheel/sdist/plugin/skill manifest and promotion record.

**Independent truth source:** Exact merged SHA, artifact hashes, clean install
and synthetic smoke.

**Consumer seam:** Unchanged bytes to protected publication targets.

**Parallelism:** Serialized release lock and final reviewer.

**Non-goals:** Public publication, source repair during promotion, rebuilding
per target.

**Invariants:** One build, exact tag/version/hash, protected workflow only,
byte-identical targets.

**Required tests/checks:** Full release/qualification, package members, clean
install, fresh CLI/Desktop smoke, docs, `just v/vc`, hosted CI, exact-main.

**Acceptance:** G7 preflight passes and immutable release bytes are approved.

**Failure/rollback:** Discard candidate and fix through a new source commit;
never mutate/reuse partial bytes.

**Handoff:** Artifact URLs/paths, hashes, sizes, CI, approval request to
CK-16-04.

**Cleanup/docs:** Finalize changelog/release manifest.

**Suggested commit:** `chore: prepare clean cutover release`
