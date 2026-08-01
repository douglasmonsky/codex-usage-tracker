# CK-14-04 — Integrate package and CI cleanup

**Status:** Blocked on CK-14-02 and CK-14-03

**Parent:** CK-14 umbrella

**Recommended owner:** `default retirement-integration`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Reconcile package membership, CI, release checks, retained tests and
configuration into the sole replacement candidate.

**Why:** Parallel deletion lanes must converge under one package/release owner.

**Controls:** CK-14-01 manifest and both deletion evidence sets.

**Dependencies:** CK-14-02/03 accepted from the same base.

**Owned files/interfaces:** `pyproject.toml`, `justfile`, workflows, package
data, release checks, disposition manifests, integration tests.

**Produces:** Exact clean package manifest and CK-14 qualification evidence.

**Independent truth source:** Static scans, exact artifact members, complete
replacement qualification.

**Consumer seam:** Clean build/install and CK-15/CK-16 candidate.

**Parallelism:** Serialized package/CI lock and final reviewer.

**Non-goals:** Product features, optional presentation, public publication.

**Invariants:** No partial legacy shim; catalog counts exact; package/CI/source
budgets shrink with only permitted ratchet headroom.

**Required tests/checks:** Full qualification, import/path/absence scans,
wheel/sdist/plugin/skill members, clean install, `just v/vc`, CI, exact-main.

**Acceptance:** Replacement is the sole packaged runtime and all hard gates
remain green.

**Failure/rollback:** Restore deletion lanes together; do not ship partial
cleanup.

**Handoff:** PR, merged SHA, clean artifact hashes, CK-15-01/CK-16-01 readiness.

**Cleanup/docs:** Reconcile parent, ledger, roadmap, disposition and packaging.

**Suggested commit:** `refactor: integrate clean replacement package`
