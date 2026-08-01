# CK-10-04 — Build the plugin and usage skill

**Status:** Blocked on CK-10-01

**Parent:** CK-10 umbrella

**Recommended owner:** `worker usage-skill`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Implement the frozen intent-to-plan decision tree and candidate
installed guidance.

**Why:** The model-facing skill needs bounded, tested behavior separate from
transport implementation.

**Controls:** CK-10-01, supported questions, setup experience, and installed
skill rules.

**Dependencies:** CK-10-01; final command examples wait for CK-10-03.

**Owned files/interfaces:** Skill content, prompt/catalog fixtures, and skill
contract tests. Plugin manifest is integration-owned.

**Produces:** Versioned skill candidate.

**Independent truth source:** Closed supported-prompt catalog and expected plan
selection.

**Consumer seam:** Fresh agent intent to one CLI/MCP operation.

**Parallelism:** May draft beside CK-10-02; must rebase exact commands after
CK-10-03 and never edit shared manifests.

**Non-goals:** Narrative findings, polling, old Console routes, generic SQL, or
Data Analytics dependency.

**Invariants:** Query-first warm path, evidence only when required, no
missing-as-zero or causal/productivity overclaims.

**Required tests/checks:** Every Foundation/Cutover prompt, lower-model hints,
one-call warm flow, no polling text, copied examples, `just v/vc`.

**Acceptance:** Every prompt selects the correct operation/plan and stays
within call/token/byte budgets.

**Failure/rollback:** Skill remains unbundled.

**Handoff:** Skill hash and selection scorecard to CK-10-05.

**Cleanup/docs:** Update skill-owned setup guidance only.

**Suggested commit:** `docs: add bounded usage skill`
