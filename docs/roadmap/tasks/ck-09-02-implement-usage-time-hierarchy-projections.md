# CK-09-02 — Implement usage, time, and hierarchy projections

**Status:** Blocked on CK-09-01 and family admission

**Parent:** CK-09 umbrella

**Recommended owner:** `feature_worker usage-projections`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Implement only admitted session, time, model, valuation, and root
family projection families through the frozen maintainer port.

**Why:** These consumers share usage/time facts but can be isolated from
workflow, allowance, and evidence maintenance.

**Controls:** Frozen projection registry, formula, valuation, hierarchy, and
publication contracts.

**Dependencies:** CK-09-01 plus explicit family eligibility.

**Owned files/interfaces:** New family maintainer modules and focused tests; no
shared DDL, registry, writer, or query binding edits.

**Produces:** Family-specific equivalence and maintenance evidence.

**Independent truth source:** Canonical facts, independent expected answers,
and projection-specific reference aggregation.

**Consumer seam:** Frozen maintainer port to publication-validation reads.

**Parallelism:** May run with CK-09-03/04 from one exact base.

**Non-goals:** Unadmitted families, tool/allowance/evidence projections, call
price cache, or shared integration edits.

**Invariants:** Effective-dated valuation, missing tokens, late parents,
replacement, bounded fanout/WAL/storage/tail.

**Required tests/checks:** Every mutation type, valuation-only changes,
calendar boundaries, late parent, standard/production scale, `just v/vc`.

**Acceptance:** Exact equivalence and every family budget pass.

**Failure/rollback:** Family remains unadmitted; preserve failed measurements
and no fallback projection use.

**Handoff:** Accepted family IDs, evidence digests, residuals to CK-09-05.

**Cleanup/docs:** Family evidence only; integrator updates shared authority.

**Suggested commit:** `feat: add admitted usage projections`
