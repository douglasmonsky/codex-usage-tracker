# CK-QG1A0 — Authorize PageExecutor source supersession
**Status:** Completed on merge
**Recommended owner:** `default page-evidence-gate`;
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md) [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md) [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)
**Goal:** Authority.
**Dependencies:** CK-08R2.
**Owned files/interfaces:** docs/tests.
**Produces:** [Authority v1](../../decisions/evidence/ckqg1a0/page-executor-source-supersession-authority.json); strict schema.
**Independent truth source:** R2/hashes.
**Consumer seam:** `test_ck08r2_manifest_binds_superseded_and_current_artifacts`.
**Parallelism:** Sole owner.
**Non-goals:** Code, drift, baseline, projection.
**Invariants:** R2; synthetic; sdist <=2,000,000.
**Required tests/checks:** `just v/vc`; CI.
**Acceptance:** Predecessor/successor exact; drift fails.
**Failure/rollback:** Block downstream.
**Handoff:** Report; QG1A gated.
**Cleanup/docs:** PR #392 unchanged.
**Suggested commit:** `docs: authorize page executor source supersession`
