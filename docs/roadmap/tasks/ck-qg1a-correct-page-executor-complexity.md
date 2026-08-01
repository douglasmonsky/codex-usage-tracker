# CK-QG1A — Correct page-executor complexity

**Status:** Conditional Ready after CK-QG1A0 merge is exact-main verified

**Parent:** Corrective prerequisite for CK-QG1

**Recommended owner:** `refactorer page-executor-complexity`; Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Remove only R2's two Xenon C/B/B violations, preserving behavior.

**Dependencies:** CK-08R2 plus CK-QG1A0 accepted, merged, and exact-main verified.

**Owned files/interfaces:** Only `agent_kernel/query/page_executor.py` and its
focused tests; no baseline/checker, registry/compiler, cursor version, R1/R3,
evidence/publication, authority, or PR #392 files.

**Produces:** `PageExecutionRequest` and `__post_init__` below C/B/B without exemptions.

**Independent truth source:** R2 validation/query-only/cursor/order/plan/EXPLAIN
vectors and Xenon against frozen baseline
`c490d954a5e9d09c61f884d51e3b9d3196af5615887f409c36f8469d1b2b6cf9`.

**Consumer seam:** Existing QueryService/page-executor tests remain
semantically exact; QG1 then refreshes PR #392 from corrected main.

**Parallelism:** Disjoint from answer semantics and R3A; may run with both.

**Non-goals:** Exemptions, baseline/threshold changes, request/cursor/query
admission changes, unrelated refactors, R1/R3/R4/RG/09.

**Invariants:** Preserve validation, selector/window, keyset cursor/order,
query-only SQLite, R2 support/evidence, synthetic privacy, sdist <= 2,000,000.

**Required tests/checks:** Reproduce `PageExecutionRequest` rank D score
23/count 1 and `__post_init__` rank D score 22/count 1; focused R2
request/cursor/order/query-only/EXPLAIN; exact baseline C/B/B; `just v`; `just vc`.

**Acceptance:** Both findings disappear; no new/worsened finding; baseline,
threshold, exemptions, R2 behavior/evidence, and unrelated source are unchanged.

**Failure/rollback:** Retain first mismatch; keep QG1/RG/09 blocked; never weaken gate.

**Handoff:** SHA, before/after findings, baseline digest, R2 seam, checks/CI/
review/exact-main; notify QG1 task `019fbb41-79b6-7760-8e7f-e68fc381422a` to
refresh retained commit `29f18ae`/PR #392 (failed run `30684568886`).

**Cleanup/docs:** QG1 owns baseline enforcement and PR refresh.

**Suggested commit:** `refactor: reduce page executor complexity`
