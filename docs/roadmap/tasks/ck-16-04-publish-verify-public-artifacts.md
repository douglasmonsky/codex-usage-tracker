# CK-16-04 — Publish and verify public artifacts

**Status:** Blocked on CK-16-03 and maintainer approval

**Parent:** CK-16 umbrella

**Recommended owner:** `default protected-publication`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Promote the approved build-once bytes through protected targets and
verify public installation.

**Why:** Public visibility and immutable package indexes require a separate,
approval-gated external task.

**Controls:** CK-16-03 artifact manifest, release policy, maintainer approval.

**Dependencies:** CK-16-03 accepted, exact merged main/tag, explicit release
authority.

**Owned files/interfaces:** Protected release run and post-publication evidence;
no source edits during publication.

**Produces:** Public URLs, hashes, sizes, install smoke, and final release
evidence.

**Independent truth source:** Downloaded public artifacts compared byte-for-byte
with the approved manifest.

**Consumer seam:** Public index/GitHub artifact to clean installed
CLI/plugin/skill/MCP.

**Parallelism:** Strictly serialized external gate.

**Non-goals:** Source repair, artifact rebuild, mutable replacement, unrelated
deployment.

**Invariants:** Published bytes equal promoted bytes; failures after publication
use a normal patch release.

**Required tests/checks:** Preflight, protected promotion, downloaded hash
comparison, clean public install, fresh CLI/Desktop synthetic smoke.

**Acceptance:** Public bytes, catalog, versions, setup, and fresh-task behavior
match the approved candidate.

**Failure/rollback:** Stop before publication on any preflight failure; after
publication never mutate bytes.

**Handoff:** Public URLs, hashes, checks, final roadmap/release closeout.

**Cleanup/docs:** Mark release evidence and future optional work accurately.

**Suggested commit:** `chore: verify public clean cutover release`
