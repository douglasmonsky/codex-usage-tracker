# CK-11 — Build exact installed-agent qualification harness

**Status:** Not started
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Automate clean wheel/plugin/skill install and fresh Codex CLI/Desktop
prompt trials.

**Why:** The core metric is user-visible installed-agent behavior.

**Controls:** `QUALIFICATION_PLAN.md`, CK-01/CK-03/CK-10.
**Dependencies:** CK-10.

**Scope and expected files:**

- `src/.../qualification/**` only if reusable runtime-independent helpers are
  justified;
- `scripts/qualify_installed_agent.py`;
- closed scorecard/result schemas;
- synthetic isolated source/cache setup;
- fresh CLI and Desktop launcher adapters;
- deterministic prompt/oracle suite and bounded retained evidence.

**Schema/API changes:** Qualification artifact schemas only.
**Non-goals:** Product narrative logic, real user data, source-checkout
fallback, automatic external publication.

**Invariants:** Exact built artifacts; fresh tasks; separate install/handshake/
exposure checks; MCP-only trials use only structured tracker evidence; no
private prompts/results persisted beyond synthetic test records.

**Tests/benchmarks:** Harness self-tests, fake-host lifecycle, timeout/cancel,
tool ledger, token/byte counters, oracle scoring, lower-model lane, repeat
determinism.

**Acceptance:** One command builds or accepts exact artifact hashes, installs,
runs the full prompt matrix, and emits a closed aggregate scorecard with no
manual transcript interpretation.

**Failure/rollback:** Preserve bounded synthetic logs and terminal scorecard;
do not retry by reinstalling or refreshing unless the scenario specifies it.

**Cleanup/docs:** Document exact operator prerequisites and artifact locations.

**Suggested commit:** `test: add installed Codex qualification harness`
