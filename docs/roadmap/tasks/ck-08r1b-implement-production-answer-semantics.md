# CK-08R1B — Implement production answer semantics
**Status:** Ready after exact join-authority merge; resume existing worker only
**Recommended owner:** `worker production-semantics`; Sol-class
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md); [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md); [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)
**Goal:** Implement R1A Q-REV-03/Q-WF-02 semantics.
**Dependencies:** R1A accepted/merged/exact-main.
**Owned files/interfaces:** The exact 18-path successor cohort in the [join authority](../../decisions/evidence/ck08r1b/answer-semantics-join-authority.json), plus focused tests for those paths. Query compiler admission, synthetic materialization, R1C's stale Q-WF-02 seam, deterministic fixture generation, database/reference parity, and Candidate A plan requalification are allowed only as bound there; public API, EvidenceService, cursor, projection, and unrelated evaluator changes remain forbidden.
**Produces:** Exact comparison/boundaries/nulls and closure.
**Independent truth source:** R1A plus R1C's preserved recursive closure and facts-only evaluator, requalified at the exact stale Q-WF-02 seam; no grading source or copied expected rows in production.
**Consumer seam:** `compile_plan_operands` emits final-R1 materializations.
**Parallelism:** Resume only existing worker `019fc419-0dab-73e3-a6cc-ce574f18c89f`; no replacement implementation or authority task.
**Non-goals:** Query/public/projection/R3/R4/RG/09.
**Invariants:** Complete acyclic session hierarchy; explicit complete tool start/terminal coordinates; exact canonical-call `measurement_mask` and four token classes; no placeholders; malformed/null/mismatch fails closed; CK-08R2 and 19 fail-closed residual plans unchanged; synthetic; sdist <=2,000,000.
**Required tests/checks:** Recompute authority identities; R1A vectors; formula/operand/query/database/closure; deterministic fixture regeneration with unchanged source JSONL; full 80-case independent-versus-production rows/grades/order/provenance/null replay; all authority negative mutations; `just vp`; `just v/vc`; reviewer/CI/merge/exact-main.
**Acceptance:** Facts alone drive output; no grading source.
**Failure/rollback:** Any cohort, closure, hierarchy, coordinate, measurement, row, grade, provenance, or regeneration mismatch fails closed; keep R1 blocked and request new authority only for a genuinely new policy decision.
**Handoff:** SHA/R1A digest/R1C closure/18-path cohort/full 80-case comparison/gates/risks; R1 remains blocked until implementation acceptance.
**Cleanup/docs:** Final R1 accounting.
**Suggested commit:** `fix: derive supported answer semantics`
