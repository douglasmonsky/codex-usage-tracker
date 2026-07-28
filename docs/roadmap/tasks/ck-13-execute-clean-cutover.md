# CK-13 — Execute side-by-side clean cutover

**Status:** Not started
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Select the qualified replacement as the only default entry point
while preserving a tested pre-deletion rollback.

**Why:** Cutover must prove packaging and recovery, not merely switch imports.

**Controls:** Roadmap Gate G6 and runtime-retirement gate, CK-12.
**Dependencies:** CK-12.

**Scope and expected files:**

- CLI/plugin/MCP entry-point selection;
- new cache/database identity defaults;
- cutover config and smoke tests;
- previous-public-version reinstall rollback drill;
- deprecation/upgrade message stating no DB migration.

**Schema/API changes:** Replacement v1 becomes public candidate; obsolete
surface removal is completed in CK-14.
**Non-goals:** Compatibility views, old DB migration, dual-write, hidden
fallback.

**Invariants:** Separate databases; exact candidate artifacts; failure never
opens/mutates spike DB; user can reinstall prior public release before CK-14
merge.

**Tests/benchmarks:** Clean install, upgrade from public 0.28 with untouched old
cache, two fresh MCP processes, all named smokes, candidate rollback/reinstall,
publication failure.

**Acceptance:** Replacement handles every public path; rollback drill passes;
maintainer approves deletion checkpoint.

**Failure/rollback:** Revert entry points and reinstall/select public 0.28.

**Cleanup/docs:** Record explicit no-migration behavior and user-facing
cutover message.

**Suggested commit:** `feat: cut over to agent-first kernel`
