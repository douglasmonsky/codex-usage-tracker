# CK-00 — Clean authority and freeze the spike

**Status:** Completed
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Replace contradictory active planning with the complete authority set
and remove obsolete workflow artifacts.

**Why:** Implementation agents cannot safely build a clean replacement while
old roadmaps, UI plans, sanitization rules, and reset-era governance still look
current.

**Controls:** `docs/INDEX.md`, `PRODUCT_DIRECTION.md`.
**Dependencies:** `origin/main` at frozen spike commit
`827be57663f9ac469f299ffdc5a3fc3e14694225`.

**Scope and expected files:**

- create the indexed authority, roadmap, packet, backlog, and archive set;
- archive only spike contract/performance/allowance evidence with ongoing
  value;
- delete old roadmap, task, plan-framework, and change-plan documents;
- update `AGENTS.md`, `AGENTS.agent-maintainer.md`, `README.md`,
  `SECURITY.md`, and `CONTRIBUTING.md`;
- update the 0.28 release/scope manifest machinery only enough to recognize the
  deliberate authority cleanup and new docs;
- add an automated documentation-authority/obsolete-reference ratchet.

**Schema/API changes:** None to runtime, database, MCP, CLI, or plugin.
**Non-goals:** Production rewrite, spike runtime deletion, Console deletion,
Linear issue creation, package/version release.

**Invariants:**

- spike code and essential oracle fixtures remain byte-unmodified;
- no obsolete workflow artifacts/references remain active;
- only one roadmap and docs index exist;
- archives are unmistakably non-authoritative.

**Required tests/checks:**

- documentation authority test;
- obsolete path/reference scan;
- scope and frozen-manifest focused tests;
- `python scripts/check_release.py`;
- Mermaid syntax/parser check if repository tooling supports it;
- Markdown link/path validation;
- `git diff --check`.

**Acceptance:**

- every required authority path exists and is indexed;
- every major requirement maps to a packet;
- every question maps to facts/plans/evidence/budgets;
- all 16 required diagram subjects compile;
- exact created/modified/deleted/archived lists are reportable;
- no active reference treats an already-resolved prerequisite as outstanding.

**Failure/rollback:** Revert the documentation branch; no runtime state changed.
Do not partially merge cleanup without its replacement authority docs.

**Cleanup/docs:** This packet is the cleanup. Update its completion state in the
roadmap PR summary, not a second execution ledger.

**Suggested commits:**

1. `docs: retire superseded tracker plans`
2. `docs: define agent-first kernel authority`
3. `test: ratchet documentation authority`
