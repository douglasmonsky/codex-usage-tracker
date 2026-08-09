# CK-QG1 — Enforce replacement-kernel maintainability

**Status:** Completed on merge — PR #392 hosted-green, squash-merged at
`68050b93`, and exact-main verified

**Baseline transition authority:** [CK-QG1 exact maintainability baseline
transition authority](../../decisions/evidence/ckqg1/maintainability-baseline-transition-authority.json)
permits only the accepted-main `PublicationWriter._validate_turn_provenance`
finding at score 35/count 1, bound to the exact predecessor and successor
digests. Its v2 cross-packet section additionally binds the current-main
writer `13da341f…` to the reviewed CK-08R1B PR #430 writer `d163e6c5…` with
the unchanged successor baseline and identical normalized findings. It does
not accept either implementation, authorize generic baseline growth, or
authorize any downstream packet.

**Parent:** Corrective quality gate for all remaining packets

**Recommended owner:** `refactorer maintainability-ratchet`; Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Make repository validation reject new or worsened complexity in
`agent_kernel` while recording existing debt honestly.

**Why:** The current checker defaults to the frozen spike and does not protect
the replacement implementation.

**Controls:** Repository validation profiles and measured Radon/Xenon output.

**Dependencies:** CK-QG1A accepted, merged, and exact-main verified; the
linked CK-QG1 baseline-transition authority must then be squash-merged and
exact-main verified before existing PR #392 is refreshed from that corrected
main with the exact selected successor baseline.

**Owned files/interfaces:** Maintainability checker, machine-readable baseline,
tests, and validation wiring.

**Produces:** `agent-kernel-maintainability-baseline-v1`.

**Independent truth source:** Normalized machine-readable complexity analysis
over exact source.

**Consumer seam:** `just vp`, `just v`, `just vc`, and later packet CI.

**Parallelism:** The CK-QG1 implementation is complete. Only existing
CK-08R1B task `019fc419-0dab-73e3-a6cc-ce574f18c89f` may resume PR #430 after
this v2 writer-transition authority is squash-merged and exact-main verified;
other corrective locks stay disjoint.

**Non-goals:** Clearing all historical findings or exempting new complexity.

**Invariants:** Spike checks remain through CK-14; improvements shrink the
baseline; new unlisted code meets the active thresholds.

**Required tests/checks:** Squash-merge and fresh exact-main verify the linked
baseline-transition authority, then refresh PR #392 (retained commit `29f18ae`, failed
run `30684568886`) on QG1A exact main; baseline
`c490d954a5e9d09c61f884d51e3b9d3196af5615887f409c36f8469d1b2b6cf9`
match/mismatch/improvement/new-finding tests; all profiles; GitNexus.

**Acceptance:** Refreshed PR #392 passes exact C/B/B baseline enforcement and
every new/worsened replacement finding fails without exemptions.

**Accepted evidence:** PR #392 reused its retained lineage and selected only
the exact authority-bound successor baseline
`fda777e28db7a0696f29b55c9d694f99d987413b206d8e323f217b4fa6a73ad5`.
Focused ratchet and authority checks, `just vc`, one bounded independent review,
and hosted Console/Python 3.10/3.14 passed before squash merge. Fresh exact-main
verification at `68050b9313ccc5be8e1fcd0ccd5b95cb4173f3ff` passed the focused
authority/scope/evidence checks and full repository validation. Thresholds,
text exemptions, release budgets, privacy rules, and spike semantics remain
unchanged.

**Failure/rollback:** Normalize tool output before enforcement if unstable;
never disable the gate or broadly refactor unrelated code.

**Handoff:** Baseline digest and CI invocation to CK-08RG.

**Cleanup/docs:** Record ownership and retirement behavior for CK-14.

**Suggested commit:** `ci: enforce agent kernel maintainability`
