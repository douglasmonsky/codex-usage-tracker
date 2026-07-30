# Clean-Cutover Task Accounting

This file is the master completion ledger for the
[Agent-First Clean-Cutover Roadmap](AGENT_FIRST_CLEAN_CUTOVER.md). Detailed
scope, contracts, checks, acceptance criteria, and rollback instructions live
in the linked files under [`docs/roadmap/tasks/`](tasks/).

## Overall

- Completed packets: **7 / 17**
- In progress: **None**
- Not started: **10**
- Critical-path completion: **7 / 16**
- Optional packets: **CK-15**

A packet may be checked only after its acceptance criteria and required checks
pass, measurements and residual risks are recorded, and any required review is
resolved. Updating a checkbox also requires updating the packet's `Status`
line and the milestone accounting below.

## Milestones

- [x] **M0 — Authority Ready** · 1 / 1 · CK-00 complete
- [x] **M1 — Architecture Selected** · 4 / 4 · CK-01–CK-04 complete
- [ ] **M2 — Kernel Alpha** · 2 / 5 · CK-05–CK-06 complete; CK-07–CK-09 not started
- [ ] **M3 — Codex MVP Qualified** · 0 / 3 · CK-10–CK-12 not started
- [ ] **M4 — Clean Cutover** · 0 / 2 · CK-13–CK-14 not started
- [ ] **M5 — Public Release** · 0 / 1 required · CK-16 not started
- [ ] **Optional enhancement** · 0 / 1 · CK-15 not started

## Packet checklist

### M0 — Authority Ready

- [x] **CK-00 — Clean authority and freeze the spike** · **Completed** ·
  depends on frozen `origin/main`
  · [packet](tasks/ck-00-clean-authority-and-freeze-spike.md)

### M1 — Architecture Selected

- [x] **CK-01 — Make the question catalog executable** · **Completed** ·
  depends on CK-00
  · [packet](tasks/ck-01-make-question-catalog-executable.md)
- [x] **CK-02 — Freeze logical contract vectors** · **Completed** ·
  depends on CK-01
  · [packet](tasks/ck-02-freeze-logical-contract-vectors.md)
- [x] **CK-03 — Build synthetic fixtures and oracles** · **Completed** ·
  depends on CK-02
  · [packet](tasks/ck-03-build-synthetic-fixtures-and-oracles.md)
- [x] **CK-04 — Run the physical-architecture bakeoff** · **Completed with an
  explicit growth-evidence exception** ·
  depends on CK-03
  · [packet](tasks/ck-04-run-physical-architecture-bakeoff.md)

### M2 — Kernel Alpha

- [x] **CK-05 — Implement the canonical storage kernel** · **Completed** ·
  depends on CK-04
  · [packet](tasks/ck-05-implement-canonical-storage-kernel.md)
- [x] **CK-06 — Implement the Codex adapter and ingestion** · **Completed** ·
  depends on CK-05
  · [packet](tasks/ck-06-implement-codex-adapter-and-ingestion.md)
- [ ] **CK-07 — Implement publication, refresh, and recovery** · Not started ·
  depends on CK-06
  · [packet](tasks/ck-07-implement-publication-refresh-recovery.md)
- [ ] **CK-08 — Implement query and evidence** · Not started ·
  depends on CK-07
  · [packet](tasks/ck-08-implement-query-and-evidence.md)
- [ ] **CK-09 — Admit projections and named plans** · Not started ·
  depends on CK-08
  · [packet](tasks/ck-09-admit-projections-and-named-plans.md)

### M3 — Codex MVP Qualified

- [ ] **CK-10 — Deliver setup, MCP, CLI, and skill** · Not started ·
  depends on CK-09
  · [packet](tasks/ck-10-deliver-setup-mcp-cli-skill.md)
- [ ] **CK-11 — Build the installed-agent harness** · Not started ·
  depends on CK-10
  · [packet](tasks/ck-11-build-installed-agent-harness.md)
- [ ] **CK-12 — Qualify and harden the MVP** · Not started ·
  depends on CK-11
  · [packet](tasks/ck-12-qualify-and-harden-mvp.md)

### M4 — Clean Cutover

- [ ] **CK-13 — Execute the clean cutover** · Not started ·
  depends on CK-12
  · [packet](tasks/ck-13-execute-clean-cutover.md)
- [ ] **CK-14 — Delete the spike, Console, and obsolete surfaces** ·
  Not started · depends on CK-13
  · [packet](tasks/ck-14-delete-spike-console-obsolete-surfaces.md)

### M5 — Public Release

- [ ] **CK-16 — Publish documentation and release** · Not started ·
  depends on CK-14
  · [packet](tasks/ck-16-publish-docs-and-release.md)

### Optional enhancement

- [ ] **CK-15 — Add optional native presentation** · Not started ·
  depends on CK-14; does not block CK-16 unless explicitly selected
  · [packet](tasks/ck-15-add-optional-native-presentation.md)

## Critical path

`CK-00 → CK-01 → CK-02 → CK-03 → CK-04 → CK-05 → CK-06 → CK-07 → CK-08
→ CK-09 → CK-10 → CK-11 → CK-12 → CK-13 → CK-14 → CK-16`

CK-15 remains outside the critical path unless the maintainer explicitly
promotes it into the release.
