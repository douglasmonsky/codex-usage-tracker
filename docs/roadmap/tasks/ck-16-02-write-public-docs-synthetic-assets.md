# CK-16-02 — Write public docs and synthetic assets

**Status:** Blocked on CK-16-01

**Parent:** CK-16 umbrella

**Recommended owner:** `worker public-documentation`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Explain the final product, setup, supported questions, grades,
limitations, rollback, and examples using exact candidate behavior.

**Why:** Public docs need a bounded owner and must not improvise product scope.

**Controls:** CK-16-01 claim allowlist and exact installed candidate.

**Dependencies:** CK-16-01; optional sections wait for selected CK-15-02.

**Owned files/interfaces:** README, public guides, examples, synthetic
screenshots/captures, docs checks; version/workflow files remain integrator-owned.

**Produces:** Candidate public documentation and synthetic assets.

**Independent truth source:** Exact installed commands/results and accepted
evidence.

**Consumer seam:** User copy/paste setup and installed catalog.

**Parallelism:** May overlap selected CK-15-02 with disjoint files.

**Non-goals:** Unsupported future claims, Console screenshots, real usage data,
release publication.

**Invariants:** Synthetic-only assets, exact commands/catalog, clear
supported/deferred/unsupported distinctions.

**Required tests/checks:** Links, commands, examples, asset privacy, clean
install copy/paste, docs/release checks.

**Acceptance:** Every example reproduces against the exact candidate and every
claim has accepted evidence.

**Failure/rollback:** Remove stale claims/assets and keep release blocked.

**Handoff:** Docs diff and validation to CK-16-03.

**Cleanup/docs:** Mark optional presentation accurately.

**Suggested commit:** `docs: explain agent first usage kernel`
