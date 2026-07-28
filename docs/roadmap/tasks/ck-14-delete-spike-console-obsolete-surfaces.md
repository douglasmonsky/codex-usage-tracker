# CK-14 — Delete the spike, Console, and obsolete package surface

**Status:** Not started
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Remove the disposable implementation and every maintenance-heavy
surface the replacement does not use.

**Why:** Keeping dead code would recreate agentic-development collisions and
package/startup burden.

**Controls:** Roadmap Gate G6 and runtime-retirement gate, CK-13 approval.
**Dependencies:** CK-13.

**Scope and expected files:**

- delete `src/codex_usage_tracker/kernel/**` after needed release primitives/
  fixtures are cleanly ported;
- delete `frontend/**`, Console assets/routes/tests/scripts, Node/Vite/
  Playwright/frontend dependencies and CI;
- delete obsolete configs/manifests/schemas/benchmarks/tests/skills/tools;
- remove compatibility and old database handling;
- tighten package/data/source and CI allowlists;
- preserve only ported synthetic oracles with current owners.

**Schema/API changes:** Retires spike schemas/tools/routes/CLI and Console.
Replacement v1 is sole surface.
**Non-goals:** Legacy support, redirect pages, migration, UI replacement.

**Invariants:** No import/string/path can restore spike dependency; exact
public replacement tools remain; previous public version is external rollback.

**Tests/benchmarks:** Absence ratchets, distribution member set, runtime import
scan, package/CI/source bytes, no frontend/Node files, full replacement
qualification, and clean-install smoke of the exact locally built candidate.

**Acceptance:** Retired paths/surfaces absent; package and CI budgets decrease
with <=3% headroom; no useful oracle lost; full L0–L5 remains green.

**Failure/rollback:** Revert CK-14 before release. Do not retain partial legacy
shims to make deletion tests pass.

**Cleanup/docs:** Update disposition with exact removals and retained ports.

**Parallelism:** Runtime deletion, frontend/Node removal, and package/CI cleanup
may be disjoint lanes; one owner controls manifests/release checks.

**Suggested commits:**

1. `refactor: remove retired spike runtime`
2. `refactor: remove Console and frontend toolchain`
3. `chore: ratchet clean kernel package`
