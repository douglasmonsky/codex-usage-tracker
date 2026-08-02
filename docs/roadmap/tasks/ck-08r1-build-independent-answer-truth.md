# CK-08R1 — Requalify independent answer truth

**Status:** Blocked on CK-08R1B; CK-08R1C accepted

**Parent:** Corrective prerequisite for CK-09

**Recommended owner:** `test_engineer answer-requalification`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Requalify all 80 variants through separately merged production and
independent semantics, executable transitive closure, and grading isolation.

**Controls:** Exact R1A/B/C identities and digests, CK-07A contracts, CK-08R2
support matrix, and answer-truth requalification v2.

**Dependencies:** CK-08R1B/C accepted, merged, and exact-main verified from the
same R1A contract frontier.

**Owned files/interfaces:** Cross-lane query-only harness, closure verifier,
grading mutation/inaccessibility tests, v2 collector/artifact, scope allowlist,
and linked accounting. Neither implementation is editable.

**Produces:** Schema-valid `answer-truth-requalification.v2` for 80 variants.

**Independent truth source:** Exact merged R1C closure over structural-v2 and
R1A. Computed operands/rows, grading, production code, and SQLite are forbidden.

**Consumer seam:** Compare R1C with R1B `compile_plan_operands` /
`evaluate_plan` over database-v1 facts for all 80. Also run QueryService for
R2's two supported plans and prove the 19 residuals still fail closed.

**Parallelism:** Serialized join after B/C; disjoint R3, 07R1, and QG1 work may
continue.

**Non-goals:** Editing implementations, physical support, R2 changes,
projections, public surfaces, R3/R4/RG, or 09.

**Invariants:** Exact Decimal/`NULL`/grade/order/selector/valuation, no
production import of truth, executable closure rejection, synthetic privacy,
and 2,000,000-byte sdist ceiling.

**Required tests/checks:** Enforce every closure/authority digest before 80
comparisons; corrected vectors; rerun both lanes with grading sentinel-mutated
and inaccessible; fact and production mutations; R2 support matrix; focused
oracles; `just v`; `just vc`.

**Acceptance:** 80/80 exact rows/grades/order/evidence; closure current; both
lanes grading-independent; facts change both; production mutation cannot
change independent truth; R2 remains unchanged.

**Failure/rollback:** Preserve the first mismatch, stale closure, forbidden
dependency, or mutation failure; keep R4/RG/09 blocked and spawn none.

**Handoff:** Exact SHA and implementation SHAs, semantic/closure/artifact
digests, 80/mutation/R2 results, CI/review/exact-main, and join readiness.

**Cleanup/docs:** Preserve CK-03–CK-08 and dirty blocker history; link only the
new v2 amendment.

**Suggested commit:** `test: requalify independent answer truth`
