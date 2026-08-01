# CK-16 — Publish documentation and release

**Status:** Blocked on CK-14-04; umbrella only

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Document, build once, promote, and verify the clean agent-first
release.

**Dependencies:** CK-14-04; selected CK-15 only. Child sequence: CK-16-01,
CK-16-02, CK-16-03, approval-gated CK-16-04.

**Non-goals:** This umbrella is never delegated directly; no unsupported
claims, local rebuild per target, or source repair during publication.

**Invariants:** Synthetic assets, exact candidate behavior, byte-identical
promotion, protected publication, normal patch release after publication.

**Required tests/checks:** Docs/commands, full release qualification, clean
public install, fresh-task smoke, CI/review/exact-main.
CK-16-04 owns the post-publication public-index download/install smoke.

**Acceptance:** CK-16-04 records verified public bytes and installs.

**Failure/rollback:** Stop before publication on any preflight failure; never
mutate published artifacts.

**Cleanup/docs:** Final evidence, URLs, hashes, roadmap and release status.

**Suggested commit:** `chore: publish clean cutover release`
