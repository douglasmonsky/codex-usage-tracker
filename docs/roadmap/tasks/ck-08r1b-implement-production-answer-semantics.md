# CK-08R1B — Implement production answer semantics
**Status:** Ready after narrow selected-cohort acceptance correction merges; resume existing worker and PR #430 only
**Recommended owner:** `worker production-semantics`; Sol-class
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md); [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md); [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)
**Goal:** Implement R1A Q-REV-03/Q-WF-02 semantics.
**Dependencies:** R1A accepted/merged/exact-main.
**Owned files/interfaces:** The exact 21-path successor cohort in the [join authority](../../decisions/evidence/ck08r1b/answer-semantics-join-authority.json), superseding the preserved PR #430 head after reviewer findings. It adds production publication hierarchy ownership, production-compiler 80-case replay, Q-WF-02 straddling lifecycle correction, independent duplicate-ID rejection, and the explicit Q-REV-03 direct-fact/internal-formula binding decision. The selected-cohort acceptance correction requires every authoritative late relationship to apply before one complete acyclic hierarchy computation, rejects late cycles and ambiguous or missing parents, proves reverse-order chains through production publication and compiler replay, and rejects explicit null required start or terminal timestamps in production and independent truth. Query compiler admission, synthetic materialization, R1C's exact seams, deterministic fixture generation, database/reference parity, and Candidate A plan requalification are allowed only as bound there; public API, EvidenceService, cursor, projection, and unrelated evaluator changes remain forbidden.
**Produces:** Exact comparison/boundaries/nulls and closure.
**Independent truth source:** R1A plus R1C's preserved recursive closure and facts-only evaluator, requalified at the exact stale Q-WF-02 seam; no grading source or copied expected rows in production.
**Consumer seam:** `compile_plan_operands` emits final-R1 materializations.
**Parallelism:** Resume only existing worker `019fc419-0dab-73e3-a6cc-ce574f18c89f`; no replacement implementation or authority task.
**Non-goals:** Query/public/projection/R3/R4/RG/09.
**Invariants:** Production publication owns complete acyclic session hierarchy; no test fallback may manufacture it. Explicit complete tool start/terminal coordinates are selected independently at window boundaries. Canonical-call `measurement_mask` and four token classes remain exact. Q-REV-03 answer objects are direct facts and its named formulas are bound internal diagnostics. No placeholders; malformed/null/mismatch/duplicate fails closed; CK-08R2 and 19 fail-closed residual plans unchanged; synthetic; sdist <=2,000,000.
**Required tests/checks:** Recompute authority identities; R1A vectors; formula/operand/query/database/closure; deterministic fixture regeneration with unchanged source JSONL; full 80-case independent-versus-production rows/grades/order/provenance/null replay; all authority negative mutations; `just vp`; `just v/vc`; reviewer/CI/merge/exact-main.
**Acceptance:** Facts alone drive output; no grading source.
**Failure/rollback:** Any cohort, closure, hierarchy, coordinate, measurement, row, grade, provenance, or regeneration mismatch fails closed; keep R1 blocked and request new authority only for a genuinely new policy decision.
**Handoff:** SHA/R1A digest/R1C closure/21-path cohort/full 80-case production-compiler comparison/gates/risks; R1 remains blocked until implementation acceptance.
**Cleanup/docs:** Final R1 accounting.
**Suggested commit:** `fix: derive supported answer semantics`
